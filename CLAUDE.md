# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

This is the **AI4SE final project (Option A: Coding Agent Harness)**. The deliverable is a *self-coded harness kernel* that wraps an LLM into a reliable coding agent — not a configuration layer on top of an existing agent framework. Requirements live in two markdown files at the repo root, which together form the complete spec:

- `AI4SE 期末项目 · 通用要求（所有项目必读）.md` — shared requirements (workflow, deliverables, credentials, distribution, CI).
- `AI4SE_Final_Project_A_Coding_Agent_Harness.md` — harness-specific requirements (the four mechanisms, the "must be code not prompt" discipline).

**Read both before starting any implementation work.** The repo is currently greenfield: no source, no `SPEC.md`/`PLAN.md`, no language chosen. The README is still the GitLab template.

## Hard constraints (these are graded)

**Harness boundary (§A.4-A):** The delivered harness core must be your own code. You MAY use low-level parts (raw LLM completion API, HTTP, vector DB, parsers) and you MAY develop *with* Superpowers/Claude Code/etc. You may NOT build the harness on top of a high-level agent loop (LangChain `AgentExecutor`, AutoGen, CrewAI, LlamaIndex agents, or a coding-agent SDK's built-in runner). Assembling "loop + governance + feedback" from parts is the work being graded.

**Mechanisms must be code, not prompts (§A.4-B/C):** Every core mechanism — tool dispatch, governance interception, feedback re-injection, memory read/write, halt decision — must be a deterministic function you wrote, verifiable with a mock/stub LLM and **no network**. A "don't delete the database" line in the system prompt does not count; a `guardrail(action)` function that blocks `rm -rf /` does. The grading test: *remove the real LLM — how much of your repo is still independently verifiable?*

**TDD is mandatory (通用要求 §3.6):** red → green → refactor, enforced by the `test-driven-development` skill. Implementation written before its failing test is not accepted.

**Superpowers 7-step workflow (通用要求 §3.6/§4):** `brainstorming` → `writing-plans` → `using-git-worktrees` → `subagent-driven-development`/`executing-plans` → `test-driven-development` → `requesting-code-review` → `finishing-a-development-branch`. **No implementation code may be written until `SPEC.md` and `PLAN.md` exist and pass the cold-start verification (§4.5).** Deviations from the workflow must be recorded in `AGENT_LOG.md` with justification.

**Credential safety (通用要求 §3.1):** API keys are never hardcoded, never committed (including history), never logged or written to shell history / plaintext configs. Load via `.env` file (not `export`), and note `.env` is plaintext + process-env-visible. Implement at least one secure store (OS keyring / KMS / encrypted file with master password), with first-run guided entry (hidden input) and view/update/clear that never echoes plaintext. State the threat model in SPEC. **The current `.env` contains a live key — it is gitignored and must stay untracked; do not print or commit it.**

## Required deliverables (通用要求 §五 + A.7)

`SPEC.md` (with an extra "领域与机制设计" section per A.5), `PLAN.md`, `SPEC_PROCESS.md` (incl. cold-start verification diff), full source with mock-LLM unit tests, a **mechanism demo** (A.6: deterministic replay of ① guardrail blocking a dangerous action ② feedback loop changing the next action after an injected failure ③ one behavior from your chosen deep-dive dimension), distribution artifact + README, `AGENT_LOG.md` (chronological process evidence), `.gitlab-ci.yml` with a job literally named **`unit-test`**, `REFLECTION.md` (1500–2500 chars, self-written), and a deployed **public WebUI URL**.

CI note: the current `.gitlab-ci.yml` is the Auto-DevOps template with SAST + secret-detection but **no `unit-test` job** — this is a required deliverable and must be added once tests exist.

## Workflow conventions for this repo

- **One worktree per feature/module → one PR.** No single mega-commit. Commit messages / PR descriptions note which subagent did the work and what the human changed.
- **`PLAN.md` is living:** mark each task complete with its commit hash as it lands.
- **`AGENT_LOG.md`** gets a timestamped entry per key node: task #, Superpowers skill triggered, prompt/context config, subagent output / commit hash, human intervention, lessons.
- **Two-stage review per task:** spec-compliance check first, then code quality; critical issues block the next task.
- **No real credentials in the repo** — self-check `.env`, history, and config files before every commit.

## When work actually starts here

The next real step is `brainstorming` (via the skill) to produce `SPEC.md`, choosing a language/stack and a single "main contribution" dimension to go deep on (governance / feedback loop / tool-dispatch-multi-agent are recommended in A.4-D because they are inherently code). Until SPEC+PLAN exist and pass cold-start verification, do not write implementation.
