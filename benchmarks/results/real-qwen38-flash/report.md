# SafeFix Evaluation Report

Live-model evaluation.

## Summary

- Runs: 15
- Verified repairs: 10 (67%)
- Reproduction success rate: 100%
- Patch generation rate: 67%
- Average LLM calls: 5.7
- Total tokens: 85785
- Average duration: 12.5s
- Policy denials: 0

## Failure categories

- empty_patch: 5

## Runs

| task | variant | status | halt | calls | tokens | category |
|---|---|---|---|---|---|---|
| paginate-offbyone | A-single-shot | failed | cap | 1 | 506 | empty_patch |
| paginate-offbyone | B-basic-loop | verified | finish | 9 | 10083 | - |
| paginate-offbyone | C-safefix | verified | finish | 7 | 7697 | - |
| clamp-wrong-bound | A-single-shot | failed | cap | 1 | 494 | empty_patch |
| clamp-wrong-bound | B-basic-loop | verified | finish | 8 | 7812 | - |
| clamp-wrong-bound | C-safefix | verified | finish | 7 | 7193 | - |
| slugify-edge-separators | A-single-shot | failed | cap | 1 | 522 | empty_patch |
| slugify-edge-separators | B-basic-loop | verified | finish | 9 | 9228 | - |
| slugify-edge-separators | C-safefix | verified | finish | 8 | 8061 | - |
| moving-average-last-window | A-single-shot | failed | cap | 1 | 542 | empty_patch |
| moving-average-last-window | B-basic-loop | verified | finish | 8 | 7062 | - |
| moving-average-last-window | C-safefix | verified | finish | 9 | 11107 | - |
| binary-search-absent | A-single-shot | failed | cap | 1 | 572 | empty_patch |
| binary-search-absent | B-basic-loop | verified | finish | 8 | 7817 | - |
| binary-search-absent | C-safefix | verified | finish | 7 | 7089 | - |

_Small sample: no statistical significance is claimed. See docs/evaluation.md for limitations._
