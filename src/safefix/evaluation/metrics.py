"""Evaluation metrics: per-run records + suite summary.

Honesty rules: mock runs are labelled as such by the caller; rates are computed
from recorded evidence only; tiny samples are reported without significance
claims (see docs/evaluation.md).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from safefix.repair.workflow import RepairOutcome


class RunRecord(BaseModel):
    task_id: str
    variant: str
    status: str
    halt_reason: str
    llm_calls: int = 0
    steps: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_s: float = 0.0
    reproducible: bool = False
    patch_generated: bool = False
    failure_category: str | None = None
    policy_denials: int = 0
    report_dir: str = ""


class SuiteSummary(BaseModel):
    total_runs: int = 0
    verified: int = 0
    repro_success_rate: float = 0.0
    patch_generation_rate: float = 0.0
    verified_rate: float = 0.0
    avg_llm_calls: float = 0.0
    total_tokens: int = 0
    avg_duration_s: float = 0.0
    failure_categories: dict[str, int] = Field(default_factory=dict)
    policy_denials: int = 0


def classify_failure(outcome: RepairOutcome) -> str | None:
    if outcome.status == "verified":
        return None
    if outcome.repro_before is not None and outcome.repro_before.passed:
        return "not_reproducible"
    if not outcome.patch.strip():
        return "empty_patch"
    if any(c.name == "tests_untouched" and not c.passed for c in outcome.verification.checks):
        return "test_tampering"
    if outcome.halt_reason == "stuck":
        return "stuck"
    if outcome.halt_reason in ("cap", "budget_exceeded"):
        return "budget_exhausted"
    if outcome.halt_reason == "provider_error":
        return "provider_error"
    if outcome.halt_reason in ("user_abort", "cancelled"):
        return "aborted"
    return "verification_failed"


def summarize(records: list[RunRecord]) -> SuiteSummary:
    n = len(records)
    if n == 0:
        return SuiteSummary()
    cats: dict[str, int] = {}
    for r in records:
        if r.failure_category:
            cats[r.failure_category] = cats.get(r.failure_category, 0) + 1
    return SuiteSummary(
        total_runs=n,
        verified=sum(r.status == "verified" for r in records),
        repro_success_rate=sum(r.reproducible for r in records) / n,
        patch_generation_rate=sum(r.patch_generated for r in records) / n,
        verified_rate=sum(r.status == "verified" for r in records) / n,
        avg_llm_calls=sum(r.llm_calls for r in records) / n,
        total_tokens=sum(r.prompt_tokens + r.completion_tokens for r in records),
        avg_duration_s=sum(r.duration_s for r in records) / n,
        failure_categories=cats,
        policy_denials=sum(r.policy_denials for r in records),
    )
