"""Evaluation: suite loading, variants, metrics, JSON/CSV/Markdown reports.

Offline deterministic run with scripted providers — results are labelled as
mock execution, never as live-model benchmark performance.
"""

import json

import yaml
from local_executor import TrustedLocalExecutor

from safefix.evaluation.metrics import RunRecord, classify_failure, summarize
from safefix.evaluation.runner import Variant, load_suite, run_suite
from safefix.llm.mock import ScriptedMock
from safefix.repair.workflow import ExecSummary, RepairOutcome
from safefix.security.approval import AutoApproveGateway

PAGINATE_FIX = (
    "--- a/shop/paginate.py\n"
    "+++ b/shop/paginate.py\n"
    "@@ -5,3 +5,3 @@\n"
    '     """Return the ``page``-th (1-based) slice of ``items`` with ``size`` per page."""\n'
    "-    start = page * size\n"
    "+    start = (page - 1) * size\n"
    "     return items[start : start + size]\n"
)
CLAMP_FIX = (
    "--- a/numtools/clamp.py\n"
    "+++ b/numtools/clamp.py\n"
    "@@ -2,8 +2,10 @@\n"
    " \n"
    " \n"
    " def clamp(value, lo, hi):\n"
    "+    if lo > hi:\n"
    '+        raise ValueError("lo must not exceed hi")\n'
    "     if value < lo:\n"
    "-        return hi\n"
    "+        return lo\n"
    "     if value > hi:\n"
    "         return hi\n"
    "     return value\n"
)


def action(tool, args):
    return "```action\n" + json.dumps({"tool": tool, "args": args}) + "\n```"


def scripted_provider_for(spec, variant):
    if spec["fixture"] == "paginate":
        responses = [action("apply_patch", {"diff": PAGINATE_FIX}), action("finish", {})]
    elif spec["fixture"] == "clamp":
        responses = [action("apply_patch", {"diff": CLAMP_FIX}), action("finish", {})]
    else:
        responses = [action("finish", {})]  # gives up -> failure category exercised
    if variant == Variant.A:
        responses = responses[:1]  # single shot: one LLM call only
    return ScriptedMock(responses)


def write_suite(tmp_path, tasks):
    p = tmp_path / "suite.yaml"
    p.write_text(yaml.safe_dump({"suite": "test", "tasks": tasks}), encoding="utf-8")
    return p


def test_load_shipped_suite():
    tasks = load_suite("benchmarks/suite.yaml")
    assert len(tasks) == 5
    assert tasks[0]["fixture"] == "paginate"


def test_summarize_rates():
    records = [
        RunRecord(
            task_id="a",
            variant="C",
            status="verified",
            halt_reason="finish",
            llm_calls=4,
            steps=4,
            prompt_tokens=100,
            completion_tokens=50,
            duration_s=2.0,
            reproducible=True,
            patch_generated=True,
            failure_category=None,
            report_dir="x",
        ),
        RunRecord(
            task_id="b",
            variant="C",
            status="failed",
            halt_reason="finish",
            llm_calls=1,
            steps=0,
            prompt_tokens=10,
            completion_tokens=5,
            duration_s=1.0,
            reproducible=True,
            patch_generated=False,
            failure_category="empty_patch",
            report_dir="y",
        ),
    ]
    s = summarize(records)
    assert s.total_runs == 2 and s.verified == 1
    assert s.verified_rate == 0.5 and s.patch_generation_rate == 0.5
    assert s.repro_success_rate == 1.0
    assert s.total_tokens == 165
    assert s.failure_categories == {"empty_patch": 1}


def test_classify_failure_categories():
    from safefix.repair.verifier import CheckResult, VerificationReport

    def outcome(**kw):
        base = dict(
            status="failed", halt_reason="finish", patch="", verification=VerificationReport(checks=[])
        )
        base.update(kw)
        return RepairOutcome(**base)

    assert classify_failure(outcome(status="verified")) is None
    assert classify_failure(outcome(repro_before=ExecSummary(exit_code=0, passed=True))) == "not_reproducible"
    assert classify_failure(outcome()) == "empty_patch"
    tamper = VerificationReport(checks=[CheckResult(name="tests_untouched", passed=False)])
    assert classify_failure(outcome(patch="diff", verification=tamper)) == "test_tampering"
    assert classify_failure(outcome(patch="diff", halt_reason="stuck")) == "stuck"
    assert classify_failure(outcome(patch="diff", halt_reason="cap")) == "budget_exhausted"


async def test_run_suite_offline(tmp_path):
    suite = write_suite(
        tmp_path,
        [
            {"id": "t-paginate", "fixture": "paginate"},
            {"id": "t-clamp", "fixture": "clamp"},
            {"id": "t-nofix", "fixture": "slugify"},
        ],
    )
    out = tmp_path / "eval-out"
    records = await run_suite(
        suite,
        provider_for=scripted_provider_for,
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        out_dir=out,
        variants=(Variant.C,),
    )
    assert len(records) == 3
    by_id = {r.task_id: r for r in records}
    assert by_id["t-paginate"].status == "verified"
    assert by_id["t-clamp"].status == "verified"
    assert by_id["t-nofix"].failure_category == "empty_patch"
    assert all(r.code_commit for r in records)  # provenance: code SHA recorded

    assert (out / "results.json").exists()
    assert (out / "summary.csv").exists()
    assert (out / "report.md").exists()
    csv_text = (out / "summary.csv").read_text(encoding="utf-8")
    assert "task_id" in csv_text and "t-paginate" in csv_text
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "verified" in md.lower()
    # per-run evidence preserved
    assert (out / "t-paginate__C-safefix" / "outcome.json").exists()


async def test_single_shot_variant_one_llm_call(tmp_path):
    suite = write_suite(tmp_path, [{"id": "t-paginate", "fixture": "paginate"}])
    records = await run_suite(
        suite,
        provider_for=scripted_provider_for,
        executor=TrustedLocalExecutor(),
        approval=AutoApproveGateway(),
        out_dir=tmp_path / "out",
        variants=(Variant.A,),
    )
    assert records[0].llm_calls == 1
    assert records[0].status == "verified"  # patch landed in the single call


async def test_suite_rerun_is_idempotent(tmp_path):
    """Regression: Windows read-only git files made rmtree(ignore_errors) leak
    source dirs, so a second run collided with 'destination already exists'."""
    suite = write_suite(tmp_path, [{"id": "t-paginate", "fixture": "paginate"}])
    out = tmp_path / "out"
    for _ in range(2):
        records = await run_suite(
            suite,
            provider_for=scripted_provider_for,
            executor=TrustedLocalExecutor(),
            approval=AutoApproveGateway(),
            out_dir=out,
            variants=(Variant.C,),
        )
        assert records[0].status == "verified"
    assert not (out / "src" / "t-paginate__C-safefix").exists()
