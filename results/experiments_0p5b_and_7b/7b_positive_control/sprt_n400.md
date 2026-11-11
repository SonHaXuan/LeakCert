# 7B positive control: SPRT on 400 canaries (100 per type)

Same target and reference as `summary.md`. Members use seed 42, non-members seed 999. This larger panel narrows the intervals of the 100-canary panel in `summary.md`; it does not change the picture.

Detection rate (%) of the completion-based SPRT (A-greedy-LRT):

| Defense | members (TPR) | non-members (FPR) | verbatim rate on members | verbatim rate on non-members |
|---|---:|---:|---:|---:|
| B1 no defense | 100.00 | 100.00 | 10.75 | 10.75 |
| B5 content filter | 84.75 | 83.00 | 10.00 | 11.50 |
| LeakCert | 82.25 | 82.25 | 10.50 | 11.50 |

n = 400 canaries per side. Raw files: `sprt_n400_members.json`, `sprt_n400_nonmembers.json`.

Reading: the detection rate on non-members is within 2 points of the detection rate on members for every defense, so the SPRT hit rate does not separate members from non-members for the 7B checkpoint either.
