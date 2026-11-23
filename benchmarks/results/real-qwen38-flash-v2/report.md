# SafeFix Evaluation Report

Live-model evaluation.

## Summary

- Runs: 15
- Verified repairs: 12 (80%)
- Reproduction success rate: 100%
- Patch generation rate: 80%
- Average LLM calls: 5.7
- Total tokens: 92959
- Average duration: 18.3s
- Policy denials: 0

## Failure categories

- empty_patch: 3

## Runs

| task | variant | status | halt | calls | tokens | category |
|---|---|---|---|---|---|---|
| paginate-offbyone | A-single-shot | failed | cap | 1 | 1097 | empty_patch |
| paginate-offbyone | B-basic-loop | verified | finish | 11 | 12239 | - |
| paginate-offbyone | C-safefix | verified | finish | 7 | 7101 | - |
| clamp-wrong-bound | A-single-shot | verified | cap | 1 | 1554 | - |
| clamp-wrong-bound | B-basic-loop | verified | finish | 9 | 9950 | - |
| clamp-wrong-bound | C-safefix | verified | finish | 7 | 7249 | - |
| slugify-edge-separators | A-single-shot | failed | cap | 1 | 2330 | empty_patch |
| slugify-edge-separators | B-basic-loop | verified | finish | 7 | 6099 | - |
| slugify-edge-separators | C-safefix | verified | finish | 7 | 7064 | - |
| moving-average-last-window | A-single-shot | verified | cap | 1 | 3353 | - |
| moving-average-last-window | B-basic-loop | verified | finish | 9 | 8580 | - |
| moving-average-last-window | C-safefix | verified | finish | 9 | 10460 | - |
| binary-search-absent | A-single-shot | failed | cap | 1 | 1070 | empty_patch |
| binary-search-absent | B-basic-loop | verified | finish | 8 | 8163 | - |
| binary-search-absent | C-safefix | verified | finish | 7 | 6650 | - |

_Small sample: no statistical significance is claimed. See docs/evaluation.md for limitations._
