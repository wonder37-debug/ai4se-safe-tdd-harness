# SafeFix Evaluation Report

**MOCK PIPELINE VALIDATION** — scripted provider with prewritten patches; trusted local test execution. NOT live-model benchmark performance.

## Summary

- Runs: 15
- Verified repairs: 15 (100%)
- Reproduction success rate: 100%
- Patch generation rate: 100%
- Average LLM calls: 1.7
- Total tokens: 0
- Average duration: 0.0s
- Policy denials: 0

## Failure categories

- none

## Runs

| task | variant | status | halt | calls | tokens | category |
|---|---|---|---|---|---|---|
| paginate-offbyone | A-single-shot | verified | cap | 1 | 0 | - |
| paginate-offbyone | B-basic-loop | verified | finish | 2 | 0 | - |
| paginate-offbyone | C-safefix | verified | finish | 2 | 0 | - |
| clamp-wrong-bound | A-single-shot | verified | cap | 1 | 0 | - |
| clamp-wrong-bound | B-basic-loop | verified | finish | 2 | 0 | - |
| clamp-wrong-bound | C-safefix | verified | finish | 2 | 0 | - |
| slugify-edge-separators | A-single-shot | verified | cap | 1 | 0 | - |
| slugify-edge-separators | B-basic-loop | verified | finish | 2 | 0 | - |
| slugify-edge-separators | C-safefix | verified | finish | 2 | 0 | - |
| moving-average-last-window | A-single-shot | verified | cap | 1 | 0 | - |
| moving-average-last-window | B-basic-loop | verified | finish | 2 | 0 | - |
| moving-average-last-window | C-safefix | verified | finish | 2 | 0 | - |
| binary-search-absent | A-single-shot | verified | cap | 1 | 0 | - |
| binary-search-absent | B-basic-loop | verified | finish | 2 | 0 | - |
| binary-search-absent | C-safefix | verified | finish | 2 | 0 | - |

_Small sample: no statistical significance is claimed. See docs/evaluation.md for limitations._
