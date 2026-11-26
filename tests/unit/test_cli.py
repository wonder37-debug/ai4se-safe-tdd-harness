"""CLI contract tests (Typer CliRunner, offline)."""

import json

from typer.testing import CliRunner

from safefix.cli import app
from safefix.evaluation.fixtures import materialize_fixture

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("demo", "fix", "eval", "report", "creds"):
        assert cmd in result.output


def test_demo_offline_verified(tmp_path):
    result = runner.invoke(app, ["demo", "--report-dir", str(tmp_path / "demo")])
    assert result.exit_code == 0, result.output
    assert "verified" in result.output.lower()
    assert (tmp_path / "demo" / "outcome.json").exists()
    assert (tmp_path / "demo" / "patch.diff").exists()


def test_fix_requires_issue(tmp_path):
    repo = materialize_fixture("paginate", tmp_path / "repo")
    result = runner.invoke(app, ["fix", "--repo", str(repo)])
    assert result.exit_code != 0


def test_fix_real_without_credentials_explicit_error(tmp_path, monkeypatch):
    for var in ("API_KEY", "API_BASE_URL", "MASTER_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    repo = materialize_fixture("paginate", tmp_path / "repo")
    result = runner.invoke(
        app,
        [
            "fix",
            "--repo",
            str(repo),
            "--issue",
            "bug",
            "--mode",
            "real",
            "--creds-file",
            str(tmp_path / "none.enc"),
            "--env-file",
            str(tmp_path / "no.env"),
            "--report-dir",
            str(tmp_path / "r"),
        ],
    )
    assert result.exit_code != 0
    assert "real mode" in result.output.lower() or "credentials" in result.output.lower()


def test_report_command(tmp_path):
    run = runner.invoke(app, ["demo", "--report-dir", str(tmp_path / "demo")])
    assert run.exit_code == 0
    result = runner.invoke(app, ["report", str(tmp_path / "demo")])
    assert result.exit_code == 0
    assert "verified" in result.output.lower()


def test_creds_set_status_clear(tmp_path, monkeypatch):
    import safefix.cli as cli_mod

    secrets = iter(["sk-unit-test-key", "master-pw-123", "master-pw-123"])
    monkeypatch.setattr(cli_mod, "_hidden_input", lambda prompt: next(secrets))
    creds_file = tmp_path / "creds.enc"

    result = runner.invoke(app, ["creds", "set", "--file", str(creds_file)])
    assert result.exit_code == 0, result.output
    assert creds_file.exists()
    assert "sk-unit-test-key" not in result.output
    assert b"sk-unit-test-key" not in creds_file.read_bytes()

    result = runner.invoke(app, ["creds", "status", "--file", str(creds_file)])
    assert result.exit_code == 0 and "present" in result.output.lower()

    result = runner.invoke(app, ["creds", "clear", "--file", str(creds_file)])
    assert result.exit_code == 0 and not creds_file.exists()


def test_eval_mock_pipeline(tmp_path):
    suite = tmp_path / "suite.yaml"
    suite.write_text("tasks:\n  - id: t1\n    fixture: paginate\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["eval", "--suite", str(suite), "--mode", "mock", "--variants", "C", "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out" / "results.json").exists()
    data = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    assert data[0]["status"] == "verified"
    assert "mock" in result.output.lower()


def test_demo_trace_exposes_progress_without_tool_arguments(tmp_path):
    result = runner.invoke(app, ["demo", "--trace", "--report-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "round 1 | run_tests" in result.output
    assert "test feedback: assertion" in result.output
    assert "round 6 | finish" in result.output
    assert "usage: 0 tokens" in result.output
    assert "python -m pytest" not in result.output


def test_fix_in_current_repository_without_repo_option(tmp_path, monkeypatch):
    import safefix.cli as cli_mod
    from safefix.repair.workflow import RepairOutcome

    repo = materialize_fixture("paginate", tmp_path / "repo")
    script = tmp_path / "script.json"
    script.write_text("[]", encoding="utf-8")
    monkeypatch.chdir(repo)

    async def run(task, **kwargs):
        assert task.repo == str(repo)
        return RepairOutcome(status="verified", halt_reason="finish")

    monkeypatch.setattr(cli_mod, "run_repair", run)
    result = runner.invoke(
        app, ["fix", "--issue", "Fix pagination", "--mode", "mock", "--script", str(script)]
    )
    assert result.exit_code == 0, result.output
