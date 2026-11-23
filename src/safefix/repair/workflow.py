"""The SafeFix product workflow: reproduce -> repair -> verify -> report.

1. Clone the target repo into a disposable workspace; record the base commit.
2. Run trusted preparation commands (dependency install) if configured.
3. Reproduce the failure (evidence recorded).
4. Run the AgentLoop with structured tools inside the execution backend.
5. Extract the git diff; verify independently (the verifier decides success).
6. Write outcome.json / patch.diff / events.jsonl; clean the workspace up.

The original repository is never modified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from safefix.agent.events import EventLog, EventSink, FanOutSink, JsonlSink
from safefix.agent.loop import AgentLoop, LoopDeps
from safefix.agent.prompt import build_system_prompt
from safefix.agent.state import Budgets
from safefix.feedback.classifier import FeedbackClassifier
from safefix.feedback.pytest_parser import PytestParser
from safefix.llm.base import LLMProvider
from safefix.memory.store import MemoryStore
from safefix.models import TokenUsage
from safefix.repair.verifier import VerificationReport, verify_patch
from safefix.runtime.executor import ExecutionBackend
from safefix.runtime.workspace import cleanup_workspace, prepare_workspace
from safefix.security.approval import ApprovalGateway
from safefix.tools.files import ListFilesTool, ReadFileTool, SearchCodeTool, _walk
from safefix.tools.git import GitDiffTool, GitStatusTool, full_candidate_diff
from safefix.tools.patch import ApplyPatchTool
from safefix.tools.registry import ToolRegistry
from safefix.tools.tests import RunTestsTool


@dataclass
class RepairTask:
    repo: str
    issue: str
    test_command: str = "python -m pytest -q"
    repro_command: str | None = None
    eval_dir: Path | None = None
    eval_command: str | None = None
    setup_commands: list[str] = field(default_factory=list)
    budgets: Budgets = field(default_factory=Budgets)
    tool_names: list[str] | None = None
    preseed_context: bool = False


class ExecSummary(BaseModel):
    exit_code: int
    passed: bool
    tail: str = ""


def _build_source_context(workspace: Path, repro_tail: str, cap: int = 20_000) -> str:
    """Source files + reproduction evidence for single-shot generation."""
    parts = ["Reproduction output (before repair):", repro_tail or "(empty)", "", "Workspace source:"]
    used = sum(len(p) for p in parts)
    for f in _walk(workspace):
        if not f.is_file() or f.suffix not in (".py", ".ini", ".cfg", ".toml", ".txt", ".md"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = f.relative_to(workspace).as_posix()
        chunk = f"\n--- {rel} ---\n{text}"
        if used + len(chunk) > cap:
            parts.append("\n...[context truncated]")
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts)


class RepairOutcome(BaseModel):
    status: Literal["verified", "unverified", "failed"]
    halt_reason: str
    iterations: int = 0
    llm_calls: int = 0
    steps: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    duration_s: float = 0.0
    base_commit: str = ""
    patch: str = ""
    repro_before: ExecSummary | None = None
    verification: VerificationReport = Field(default_factory=VerificationReport)
    failure_analysis: str | None = None


async def run_repair(
    task: RepairTask,
    *,
    provider: LLMProvider,
    executor: ExecutionBackend,
    approval: ApprovalGateway,
    report_dir: Path,
    sink: EventSink | None = None,
) -> RepairOutcome:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    ws = prepare_workspace(task.repo)
    try:
        for cmd in task.setup_commands:
            prep = getattr(executor, "run_trusted_prep", None)
            if prep is not None:
                result = await prep(cmd, cwd=ws.path, timeout=600)
            else:
                result = await executor.run(cmd, cwd=ws.path, timeout=600)
            if result.exit_code != 0 or result.timed_out:
                raise RuntimeError(
                    f"trusted preparation failed (exit {result.exit_code}): {cmd}\n"
                    f"{(result.stderr or result.stdout)[-400:]}"
                )

        repro_cmd = task.repro_command or task.test_command
        before = await executor.run(repro_cmd, cwd=ws.path, timeout=300)
        repro_before = ExecSummary(
            exit_code=before.exit_code,
            passed=before.exit_code == 0 and not before.timed_out,
            tail=(before.stdout + before.stderr)[-800:],
        )

        log = EventLog()
        sinks: list[EventSink] = [log, JsonlSink(report_dir / "events.jsonl", append=False)]
        if sink is not None:
            sinks.append(sink)
        registry = ToolRegistry(
            [
                ReadFileTool(),
                ListFilesTool(),
                SearchCodeTool(),
                ApplyPatchTool(),
                GitStatusTool(),
                GitDiffTool(),
                RunTestsTool(),
            ]
        )
        if task.tool_names is not None:
            registry = ToolRegistry([t for t in registry.tools() if t.name in task.tool_names])
        initial_context = None
        if task.preseed_context:
            # Fair single-shot baseline (review 4661696758): give the ONE generation
            # the same source + failure evidence iterative variants can gather.
            initial_context = _build_source_context(ws.path, repro_before.tail)
        loop = AgentLoop(
            LoopDeps(
                llm=provider,
                registry=registry,
                workspace=ws.path,
                approval=approval,
                feedback=FeedbackClassifier(PytestParser()),
                budgets=task.budgets,
                system_prompt=build_system_prompt(task.issue),
                memory=MemoryStore(report_dir / "memory"),
                sink=FanOutSink(sinks),
                executor=executor,
                initial_context=initial_context,
                git_dir=ws.git_dir,
            )
        )
        result = await loop.run()

        rc, patch, diff_err = await full_candidate_diff(ws.path, ws.git_dir)
        if rc != 0:
            raise RuntimeError(f"patch export failed: {diff_err}")
        # raw bytes: text-mode newline translation would corrupt binary patches
        (report_dir / "patch.diff").write_bytes(patch.encode("utf-8"))

        report = await verify_patch(
            ws.path,
            executor=executor,
            test_command=task.test_command,
            repro_command=task.repro_command,
            eval_dir=task.eval_dir,
            eval_command=task.eval_command,
            git_dir=ws.git_dir,
        )
        reproducible = not repro_before.passed
        verified = report.verified and reproducible and bool(patch.strip())
        status = "verified" if verified else ("unverified" if patch.strip() else "failed")

        analysis = None
        if not verified:
            reasons = [f"halt={result.halt_reason.value}"]
            if not reproducible:
                reasons.append("bug was not reproducible at base")
            if not patch.strip():
                reasons.append("empty patch")
            reasons.extend(f"{c.name} failed: {c.detail}" for c in report.checks if not c.passed)
            analysis = "; ".join(reasons)

        outcome = RepairOutcome(
            status=status,
            halt_reason=result.halt_reason.value,
            iterations=result.iterations,
            llm_calls=result.llm_calls,
            steps=result.steps,
            usage=result.usage,
            duration_s=result.duration_s,
            base_commit=ws.base_commit,
            patch=patch,
            repro_before=repro_before,
            verification=report,
            failure_analysis=analysis,
        )
        (report_dir / "outcome.json").write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
        return outcome
    finally:
        cleanup_workspace(ws)
