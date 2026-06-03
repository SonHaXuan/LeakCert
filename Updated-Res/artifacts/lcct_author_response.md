# LCCT Author Response Summary

- recorded: `2026-06-01T13:28:00+0700`
- source: user-provided email response from LCCT authors

## Resolved

- `forbidden_questions.csv` is confirmed by the authors as the exact 80-question set used in the LCCT paper.
- Category order is confirmed as `Illegal`, `Hate`, `Pornography`, `Harmful`, matching four contiguous blocks of 20 rows.
- GPT-based judge construction follows Appendix B of arXiv:2310.03693: provide the usage policy, user instruction, generated response, and policy/rubric-based scoring prompt to the judge model.

## Still Unavailable

- The authors cannot release user-level training-data extraction artifacts or extracted results due privacy concerns.
- This includes anonymized/redacted versions because of re-identification risk.

## Evaluation Impact

- Forbidden-questions dataset and category mapping can now be treated as author-confirmed.
- ASR judge should be reported as a faithful reimplementation of the cited Appendix B construction unless exact model/API version and all policy text settings are also fixed.
- LCCT training-data extraction cannot be claimed as a full artifact reproduction from public data. Any replacement must be framed as a comparable reimplementation or supplementary benchmark with this limitation disclosed.
