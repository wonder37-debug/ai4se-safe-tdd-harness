"""SafeFix CLI — Typer + Rich.

Commands: demo / fix / eval / report / creds / ui.
Mode separation is explicit: real tasks never silently fall back to a demo.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import os
import shutil
import tempfile
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from safefix.agent.state import Budgets
from safefix.config import ConfigError, Mode, build_provider, load_env_file
from safefix.creds.store import CredentialError, EncryptedFileStore
from safefix.evaluation.fixtures import load_fixture, materialize_fixture
from safefix.llm.demo import demo_responses
from safefix.llm.mock import ScriptedMock
from safefix.repair.workflow import RepairTask, run_repair
from safefix.runtime.demo_executor import DemoExecutor
from safefix.runtime.docker_executor import DockerExecutor
from safefix.runtime.executor import SandboxUnavailableError
from safefix.runtime.local_executor import LocalTrustedExecutor
from safefix.security.approval import AutoApproveGateway, AutoDenyGateway
from safefix.security.cli_approval import CliApprovalGateway

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="AI4SE SafeFix — test-driven, sandboxed bug repair agent.",
)
creds_app = typer.Typer(
    no_args_is_help=True, help="Manage the encrypted API-key store (never echoes plaintext)."
)
app.add_typer(creds_app, name="creds")
console = Console()

DEFAULT_CREDS = Path.home() / ".safefix" / "creds.enc"


def _hidden_input(prompt: str) -> str:
    return getpass.getpass(prompt)


def _fail(message: str) -> None:
    console.print(f"[bold red]error:[/bold red] {message}")
    raise typer.Exit(code=1)


@app.command()
def demo(
    report_dir: Path = typer.Option(
        Path(".safefix-runs/demo"), "--report-dir", help="Where to write the demo evidence."
    ),
):
    """Deterministic offline mechanism demo: guardrail denial + feedback loop + verified repair."""
    console.print(Panel("SafeFix mechanism demo (scripted, offline, simulated test execution)", style="cyan"))
    tmp = Path(tempfile.mkdtemp(prefix="safefix-demo-"))
    try:
        source = materialize_fixture("paginate", tmp / "source")
        fx = load_fixture("paginate")
        outcome = asyncio.run(
            run_repair(
                RepairTask(repo=str(source), issue=fx.meta["issue"], eval_dir=fx.eval_dir),
                provider=ScriptedMock(demo_responses()),
                executor=DemoExecutor(),
                approval=AutoDenyGateway(),
                report_dir=report_dir,
            )
        )
        console.print(
            f"status: [bold]{outcome.status}[/bold]  halt={outcome.halt_reason}  iterations={outcome.iterations}"
        )
        console.print(f"evidence: {report_dir / 'outcome.json'}")
        console.print("guardrail: dangerous 'rm -rf /' attempt was DENIED and fed back (see events.jsonl)")
        if outcome.status != "verified":
            _fail(outcome.failure_analysis or "demo did not verify")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.command()
def fix(
    repo: str = typer.Option(..., "--repo", help="Local git repository path or Git URL."),
    issue: str = typer.Option(None, "--issue", help="Natural-language bug report."),
    issue_file: Path = typer.Option(None, "--issue-file", help="Read the bug report from a file."),
    mode: Mode = typer.Option(Mode.REAL, "--mode", help="real | mock (scripted, sandboxed)."),
    script: Path = typer.Option(None, "--script", help="JSON list of scripted LLM responses (mock mode)."),
    test_command: str = typer.Option("python -m pytest -q", "--test-command"),
    repro_command: str = typer.Option(None, "--repro-command"),
    eval_dir: Path = typer.Option(
        None, "--eval-dir", help="Independent evaluation tests (kept from the agent)."
    ),
    eval_command: str = typer.Option(None, "--eval-command"),
    max_calls: int = typer.Option(20, "--max-calls"),
    max_steps: int = typer.Option(40, "--max-steps"),
    wall_seconds: float = typer.Option(600.0, "--wall-seconds"),
    model: str = typer.Option(None, "--model"),
    report_dir: Path = typer.Option(Path(".safefix-runs/fix"), "--report-dir"),
    creds_file: Path = typer.Option(DEFAULT_CREDS, "--creds-file"),
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    yes: bool = typer.Option(False, "--yes", help="Auto-approve high-risk actions (non-interactive)."),
):
    """Repair a bug in an isolated workspace; the verifier decides success."""
    if issue_file is not None:
        issue = issue_file.read_text(encoding="utf-8")
    if not issue or not issue.strip():
        _fail("provide --issue or --issue-file")
    if mode == Mode.DEMO:
        _fail("use `safefix demo` for the demonstration mode")

    async def _run():
        if mode == Mode.MOCK:
            if script is None:
                raise ConfigError("mock mode requires --script (JSON list of scripted responses)")
            provider = ScriptedMock(json.loads(script.read_text(encoding="utf-8")))
        else:
            provider = await build_provider(
                mode=Mode.REAL,
                creds=EncryptedFileStore(creds_file),
                config={},
                env_file=load_env_file(env_file),
                env=dict(os.environ),
                master_password=os.environ.get("MASTER_PASSWORD"),
                model=model,
            )
        approval = AutoApproveGateway() if yes else CliApprovalGateway()
        return await run_repair(
            RepairTask(
                repo=repo,
                issue=issue,
                test_command=test_command,
                repro_command=repro_command,
                eval_dir=eval_dir,
                eval_command=eval_command,
                budgets=Budgets(max_llm_calls=max_calls, max_steps=max_steps, max_wall_seconds=wall_seconds),
            ),
            provider=provider,
            executor=DockerExecutor(),
            approval=approval,
            report_dir=report_dir,
        )

    try:
        outcome = asyncio.run(_run())
    except (ConfigError, SandboxUnavailableError, CredentialError) as e:
        _fail(str(e))
    console.print(f"status: [bold]{outcome.status}[/bold]  halt={outcome.halt_reason}")
    console.print(f"report: {report_dir / 'outcome.json'}")
    if outcome.failure_analysis:
        console.print(f"[yellow]{outcome.failure_analysis}[/yellow]")
    if outcome.status != "verified":
        raise typer.Exit(code=2)


@app.command(name="eval")
def eval_suite(
    suite: Path = typer.Option(None, "--suite", help="Suite YAML (default: bundled benchmarks/suite.yaml)."),
    mode: str = typer.Option("real", "--mode", help="real | mock (labelled pipeline validation)."),
    variants: str = typer.Option("C", "--variants", help="Comma list of A,B,C."),
    out: Path = typer.Option(Path(".safefix-runs/eval"), "--out"),
    creds_file: Path = typer.Option(DEFAULT_CREDS, "--creds-file"),
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
    model: str = typer.Option(None, "--model"),
):
    """Run the benchmark suite and write JSON/CSV/Markdown reports."""
    from safefix.evaluation.demo_script import mock_provider_for
    from safefix.evaluation.fixtures import default_suite_path
    from safefix.evaluation.runner import Variant, run_suite

    suite = suite or default_suite_path()

    variant_map = {"A": Variant.A, "B": Variant.B, "C": Variant.C}
    try:
        chosen = tuple(variant_map[v.strip().upper()] for v in variants.split(",") if v.strip())
    except KeyError:
        _fail("--variants must be a comma list of A,B,C")
        return
    if mode == "mock":
        provider_for = mock_provider_for
        executor = LocalTrustedExecutor()
        note = "**MOCK PIPELINE VALIDATION** — scripted provider; NOT live-model benchmark performance."
        run_model, run_host = "scripted-mock", ""
        console.print(f"[yellow]{note}[/yellow]")
    elif mode == "real":
        try:
            provider = asyncio.run(
                build_provider(
                    mode=Mode.REAL,
                    creds=EncryptedFileStore(creds_file),
                    config={},
                    env_file=load_env_file(env_file),
                    env=dict(os.environ),
                    master_password=os.environ.get("MASTER_PASSWORD"),
                    model=model,
                )
            )
        except ConfigError as e:
            _fail(str(e))
        provider_for = lambda spec, variant: provider  # noqa: E731
        executor = DockerExecutor()
        note = "Live-model evaluation."
        run_model, run_host = provider.model, provider.endpoint_host
    else:
        _fail("--mode must be real or mock")
        return

    try:
        records = asyncio.run(
            run_suite(
                suite,
                provider_for=provider_for,
                executor=executor,
                approval=AutoDenyGateway(),
                out_dir=out,
                variants=chosen,
                mode_note=note,
                model=run_model,
                endpoint_host=run_host,
            )
        )
    except SandboxUnavailableError as e:
        _fail(str(e))
        return
    verified = sum(r.status == "verified" for r in records)
    console.print(f"runs={len(records)} verified={verified} -> {out / 'report.md'}")


@app.command()
def report(run_dir: Path = typer.Argument(..., help="Run directory containing outcome.json.")):
    """Pretty-print a recorded run outcome."""
    outcome_file = run_dir / "outcome.json"
    if not outcome_file.exists():
        _fail(f"no outcome.json in {run_dir}")
    data = json.loads(outcome_file.read_text(encoding="utf-8"))
    console.print(Panel(f"status: {data['status']}   halt: {data['halt_reason']}", title=str(run_dir)))
    table = Table("check", "passed", "detail")
    for c in data.get("verification", {}).get("checks", []):
        table.add_row(c["name"], "yes" if c["passed"] else "NO", c["detail"][:80])
    console.print(table)
    if data.get("failure_analysis"):
        console.print(f"[yellow]{data['failure_analysis']}[/yellow]")
    patch = data.get("patch", "")
    if patch:
        console.print(Panel(patch[:1500], title="patch (preview)"))


@creds_app.command("set")
def creds_set(file: Path = typer.Option(DEFAULT_CREDS, "--file")):
    """Store the API key encrypted (hidden input; plaintext never echoed)."""
    key = _hidden_input("API key (hidden): ")
    if not key.strip():
        _fail("empty API key")
    master = _hidden_input("Master password (hidden): ")
    confirm = _hidden_input("Confirm master password (hidden): ")
    if master != confirm:
        _fail("master passwords do not match")
    asyncio.run(EncryptedFileStore(file).set(key.strip(), master))
    console.print(f"encrypted credentials stored at {file}")


@creds_app.command("status")
def creds_status(file: Path = typer.Option(DEFAULT_CREDS, "--file")):
    """Show whether encrypted credentials are present (never the key itself)."""
    status = EncryptedFileStore(file).status()
    console.print(f"present: {status.present}  source: {status.source}  file: {file}")


@creds_app.command("clear")
def creds_clear(file: Path = typer.Option(DEFAULT_CREDS, "--file")):
    """Delete the encrypted credential file."""
    asyncio.run(EncryptedFileStore(file).clear())
    console.print("credentials cleared")


@app.command()
def ui(run_dir: Path = typer.Option(Path(".safefix-runs/demo"), "--run-dir")):
    """Optional Streamlit viewer for a recorded run (requires safefix[ui])."""
    try:
        import streamlit  # noqa: F401
    except ImportError:
        _fail("Streamlit is not installed. Install with: uv sync --extra ui  (or: pip install 'safefix[ui]')")
        return
    import subprocess
    import sys

    app_path = Path(__file__).parent / "ui_app.py"
    console.print(f"launching Streamlit viewer for {run_dir} (localhost only)")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--", str(run_dir)], check=False)


if __name__ == "__main__":
    app()
