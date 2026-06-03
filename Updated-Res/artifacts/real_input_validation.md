# submission Real-Input Validation

- timestamp: `2026-05-31T23:14:18+0700`
- hostname: `local-mac`
- ready_for_full: `False`

## Blockers

- LCCT JSONL has rows without secret/expected_secret.
- LCCT input contains NOT PAPER-GRADE/template rows.
- Missing real corpus.path for W1/DP/multi-model training.
- Small/base model ID is still a placeholder.
- Mid model ID is still a placeholder.
- Missing real DP checkpoint for epsilon=1.
- Missing real DP checkpoint for epsilon=2.
- Missing real DP checkpoint for epsilon=4.
- Missing real DP checkpoint for epsilon=8.
- Missing real DP checkpoint for epsilon=16.
- Certificate calibration needs a real target checkpoint.

## Warnings

- LCCT smoke file has fewer than 200 sampled rows; full W2 expects the real 4,832-item benchmark.
- Small target checkpoint is absent; W1 must run before W2/W4/W5/certificate.
- Mid target checkpoint is absent; multi-model full needs W1 for the second model.

## Smoke Sequence

1. W2 real LCCT smoke: 100 real prompts with require_real_lcct=true.
2. DP-SGD smoke: epsilon=8 on a tiny real-corpus slice; verify dp_accounting.json and checkpoint reload.
3. Multi-model smoke: second model W1/W4/W5 with n_eval_per_type=1-2.
4. Certificate smoke: compute KL and certificate on the real checkpoint, then expand panel sizes/seeds.

## Inputs

- LCCT: `<home>/Documents/Conf/SP/DECODESHIELD/data/eval/lcct.json` exists=True
- training corpus: `TODO_REAL_TRAINING_CORPUS_JSONL` exists=False
- small checkpoint: `TODO_REAL_SMALL_TARGET_CHECKPOINT` exists=False
- mid checkpoint: `TODO_REAL_MID_TARGET_CHECKPOINT` exists=False
