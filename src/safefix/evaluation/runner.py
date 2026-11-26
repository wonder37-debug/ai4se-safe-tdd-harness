"""Reproducible benchmark runner with A/B/C baselines.

Variants (same model, dataset, environment and budgets where comparable):
- A-single-shot: one LLM call, no iterative test feedback;
- B-basic-loop: iterative loop with test feedback but a reduced toolset
  (read_file / apply_patch / run_tests only — no search or git tools);
- C-safefix: full structured toolset + sandbox + independent verification.

All variants still run inside the same execution backend and pass through the
same independent verifier — the comparison measures the loop/tooling, not the
safety net. Results are written as JSON + CSV + Markdown.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

import yaml

from safefix.agent.state import Budgets
from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.evaluation.metrics import RunRecord, classify_failure, summarize
from safefix.evaluation.reporter import write_csv, write_json, write_markdown
from safefix.llm.base import LLMProvider
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.executor import ExecutionBackend
from safefix.runtime.workspace import _on_rm_error
from safefix.security.approval import ApprovalGateway


class Variant(StrEnum):
    A = "A-single-shot"
    B = "B-basic-loop"
    C = "C-safefix"


_VARIANT_BUDGETS = {
    Variant.A: Budgets(max_llm_calls=1, max_steps=1),
    Variant.B: Budgets(),
    Variant.C: Budgets(),
}
_VARIANT_TOOLS: dict[Variant, list[str] | None] = {
    Variant.A: None,
    Variant.B: ["read_file", "apply_patch", "run_tests"],
    Variant.C: None,
}


def load_suite(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data.get("tasks", [])


def _count_denials(events_file: Path) -> int:
    if not events_file.exists():
        return 0
    n = 0
    for line in events_file.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "approval_decision" and ev.get("payload", {}).get("decision") == "deny":
            n += 1
    return n


async def run_suite(
    suite_path: str | Path,
    *,
    provider_for: Callable[[dict, Variant], LLMProvider],
    executor: ExecutionBackend,
    approval: ApprovalGateway,
    out_dir: Path,
    variants: tuple[Variant, ...] = (Variant.C,),
    mode_note: str = "",
    model: str = "",
    endpoint_host: str = "",
) -> list[RunRecord]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[RunRecord] = []
    try:
        code_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        code_commit = ""

    for spec in load_suite(suite_path):
        fx = load_fixture(spec["fixture"])
        for variant in variants:
            run_id = f"{spec['id']}__{variant.value}"
            run_dir = out_dir / run_id
            source_dir = out_dir / "src" / run_id
            # idempotent reruns: robustly remove leftovers (Windows git files are
            # read-only; plain rmtree(ignore_errors=True) silently leaks them)
            if source_dir.exists():
                shutil.rmtree(source_dir, onexc=_on_rm_error)
            source = materialize_fixture(spec["fixture"], source_dir)
            try:
                budget_data = _VARIANT_BUDGETS[variant].model_dump()
                if variant != Variant.A:
                    budget_data.update(spec.get("budget", {}))
                outcome = await run_repair(
                    RepairTask(
                        repo=str(source),
                        issue=fx.meta["issue"],
                        test_command=fx.meta["test_command"],
                        repro_command=fx.meta.get("repro_command"),
                        eval_dir=fx.eval_dir,
                        setup_commands=fx.meta.get("setup", []),
                        budgets=Budgets(**budget_data),
                        tool_names=_VARIANT_TOOLS[variant],
                        # fair single-shot: source + repro evidence preseeded so the
                        # one generation can actually emit a patch (review 4661696758)
                        preseed_context=variant == Variant.A,
                    ),
                    provider=provider_for(spec, variant),
                    executor=executor,
                    approval=approval,
                    report_dir=run_dir,
                )
            finally:
                if source.exists():
                    shutil.rmtree(source, onexc=_on_rm_error)

            records.append(
                RunRecord(
                    task_id=spec["id"],
                    variant=variant.value,
                    status=outcome.status,
                    halt_reason=outcome.halt_reason,
                    model=model,
                    endpoint_host=endpoint_host,
                    code_commit=code_commit,
                    llm_calls=outcome.llm_calls,
                    steps=outcome.steps,
                    prompt_tokens=outcome.usage.prompt_tokens,
                    completion_tokens=outcome.usage.completion_tokens,
                    duration_s=outcome.duration_s,
                    reproducible=outcome.repro_before is not None
                    and outcome.repro_before.classification == "test_failed",
                    patch_generated=bool(outcome.patch.strip()),
                    failure_category=classify_failure(outcome),
                    policy_denials=_count_denials(run_dir / "events.jsonl"),
                    report_dir=str(run_dir),
                )
            )

    summary = summarize(records)
    write_json(records, out_dir / "results.json")
    write_csv(records, out_dir / "summary.csv")
    write_markdown(summary, records, out_dir / "report.md", mode_note=mode_note)
    return records
