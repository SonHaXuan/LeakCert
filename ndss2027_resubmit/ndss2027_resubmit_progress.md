# LEAKCERT — NDSS 2027 resubmit progress tracker

Nguồn: `review_triage_plan (1).md` (panel triage). File này theo dõi **tiến độ thực thi**.
Cập nhật cột **Status** mỗi khi làm; ghi commit / job ID vào **Notes**.

- **Status legend:** ⬜ chưa bắt đầu · 🔄 đang làm · ✅ xong · ⏸ hoãn/đợi · ❌ bỏ (kèm lý do)
- **Priority:** P0 = không sửa thì reject lại · P1 = cần để đủ mạnh · P2 = trau chuốt
- **Cost:** WRITE = chỉ viết/toán · REANALYZE = tính lại số cũ · INFER = inference (checkpoint sẵn có) · TRAIN = phải train model mới

> Cập nhật lần cuối: 2026-08-22 · Branch: `feature/training-pipeline-aau-hpc`

---

## 0. Quyết định định vị bài (chốt trước khi viết)

Ba hệ quả từ review — **chốt sớm vì nó quyết định câu chữ toàn bài**:

- [ ] **Bỏ headline "first non-vacuous certificate".** Dạng min chứng minh được nhưng vẫn vacuous ở mọi budget trừ T4 @ B∈{1,2}. Reframe headline = *honest audit + memorization ≠ extraction + FP-control làm sập SPRT (retraction trung thực)*.
- [x] **Chốt mức resubmit (2026-08-17): CHUẨN — train đúng 1 model D1.** ⇒ giữ claim "memorization thật, tách khỏi fine-tuning shift"; D1 là bắt buộc, D2–D5 chỉ nếu kịp.
- [ ] **C1 và D1 là bổ sung, KHÔNG thay thế.** C1 = non-member control trên cùng model; D1 = sửa reference sai marginal. Giữ claim "memorization thật" ⇒ cần D1.
- [x] **⚠️ 2026-08-23 — ĐÃ AUDIT + CHỐT.** C1 D1-ref (job 1006733): AUC=0.4855, gap=-0.0149 — giống hệt pattern C1 base-ref (AUC=0.49). Đã audit kỹ `generator.py`/`types.py`/`injector.py` — **không có bug**, panel/estimator/injection đều đúng. Kết luận: **claim "memorization thật, tách khỏi fine-tuning shift" KHÔNG được dữ liệu ủng hộ** — ở cả 2 reference (base và D1) đều không phát hiện tách biệt member/non-member. Chi tiết đầy đủ + 2 giả thuyết (single-injection dưới ngưỡng phát hiện; format-generalization confound) + khuyến nghị hướng viết lại: `results/C1_D1ref_result.md`. **Quyết định: chọn phương án (b)** — báo cáo cả 2 kết quả C1 như một negative-result/limitations subsection trung thực, KHÔNG claim memorization tồn tại hay không tồn tại một cách dứt khoát, tách bạch "tool có thể phát hiện memorization khi có" (chưa test bằng positive control) khỏi "không phát hiện được ở cấu hình 1-lần-inject, 3-epoch này". Việc viết lại §0/A11 theo hướng này — chưa làm, cần cập nhật `results/A_theory_corrections_draft.md`.

---

## NHÓM A — Sửa bằng VIẾT / TOÁN (không chạy lại gì)

> ⚠️ Repo **không chứa source LaTeX** của paper → các mục WRITE được làm thành **bản draft hand-off** trong `results/` (bạn dán vào .tex), không edit trực tiếp bài.

| # | Việc | Prio | Cost | Status | Notes |
|:--|:--|:--|:--|:--|:--|
| A1 | Phát biểu lại định lý 5/7/10/12 ở dạng `I(K;Y^B) ≤ min{H(K), Σ E[KL]}` + chứng minh lại | P0 | WRITE | ✅ | **viết lại 2026-08-23** (draft cũ không có trên máy này) — `results/A_theory_corrections_draft.md`, thêm Lemma 0 (variational MI identity) làm nền cho A1/A6/A7/A17, đối chiếu đúng `certificate.py::_theorem5/_theorem7`. Còn dán vào .tex |
| A2 | Viết đầy đủ Appendix A, B (chứng minh) vào PDF nộp | P0 | WRITE | 🔄 | proof đầy đủ Lemma 0 + Định lý 5′/7′/10′/13′ đã có trong draft; A4 (Đlý 15) và A7 cần bản `.tex` gốc (không có ở đây) để viết full |
| A3 | Định nghĩa tường minh game rò rỉ + joint `P_{K,M,X^B,Y^B}` (K index cái gì, ai biết c_K) | P0 | WRITE | ✅ | tách rõ **Game A** (panel exposure audit, K=chỉ số panel, dùng cho Định lý 5-13) và **Game B** (local κ-ary discrimination, K=bí mật thật, dùng CHỈ cho Định lý 17/Fano) — phát hiện code hiện lẫn `canary_set_size` (N panel) vào cả `_theorem17` (cần κ cục bộ) → cần sửa code, chưa làm |
| A4 | Định lý 15: sửa "submartingale" → **supermartingale** | P0 | WRITE | ⏸ | không tìm thấy Định lý 15 trong code (`leakcert/runtime/`?); đã viết lý do toán học tổng quát (LR-martingale dưới H0) nhưng cần bản `.tex` gốc để viết proof chính xác — chưa có trên máy này |
| A5 | Bỏ/hạ mệnh đề nhảy từ "SPRT optimal stopping" → "optimal adaptive prompt design" | P0 | WRITE | ✅ | 3 phương án đã viết, khuyến nghị PA2 (hạ xuống "heuristic adaptive", khớp A-adaptive dùng UCB chứ không phải SPRT tối ưu Wald) |
| A6 | Fano prior không đều: sửa mẫu số `log|K|` | P0 | WRITE | ✅ | không chỉ đổi ký hiệu — viết lại Định lý 17′ đầy đủ theo `H(K)` thay `log|K|`, khớp `_theorem17`; cần kiểm tra bản gốc xem cấu trúc bất đẳng thức có sai không chỉ ký hiệu |
| A7 | Định lý utility–leakage: hạ thành "quan sát thực nghiệm" hoặc bỏ | P0 | WRITE | 🔄 | không có công thức này trong code → thuần .tex; đề xuất hạ thành Observation nối với A12/B4, nhưng cần bản gốc để sửa chính xác giả thiết |
| A8 | Đổi nhãn "KL divergence" → **exposure / LLR / memorization score** xuyên suốt | P0 | WRITE | ✅ | bảng phân biệt population KL/MI (lý thuyết) vs exposure/LLR (thực nghiệm, `PerCanaryKL.kl_estimate`) — nền tảng cho A17 |
| A9 | Định nghĩa lại threat model = **gray-box likelihood audit**, phân tầng sample/logprob/local | P0 | WRITE | ✅ | bảng 3 tầng sample/log-prob/white-box; nêu rõ certificate cần tầng log-prob (mạnh hơn API thường), không chỉ sample access |
| A10 | Đổi "per-secret certificate" → **panel-average / canary-panel audit** | P0 | WRITE | ✅ | gộp vào Game A (A3); câu thay thế chuẩn hoá đã viết |
| A11 | Bỏ "first non-vacuous certificate" tới khi định lý đã sửa + so literature | P1 | WRITE | ✅ | nối trực tiếp A3 (κ vs N nhầm lẫn) + A19 (so literature); câu headline thay thế đã đề xuất |
| A12 | "no utility cost" → "không phát hiện khác biệt utility ở độ phân giải này" | P1 | WRITE | ✅ | câu thay thế đã viết, nối với B4 (còn ⬜, cần CI non-inferiority thật) |
| A13 | Nói rõ: audit panel canary, không guarantee toàn deployment | P1 | WRITE | ✅ | đoạn scope đã viết, đề xuất đặt cuối §3 Threat Model |
| A14 | Trình bày 7B là **pipeline smoke test**, gỡ khỏi vai trò "bằng chứng scale" | P1 | WRITE | ✅ | disclaim confound corpus-size (700-doc vs 500k/40k) đã viết, câu thay thế cụ thể |
| A15 | Ghi rõ arm nào dùng checkpoint nào (1.5B/7B/0.5B) | P1 | WRITE | ✅ | bảng 5 arm × checkpoint × corpus × canary × epoch, rút từ tracker + HPC_PROGRESS.md; lưu ý D4 dùng corpus 40k khác target 500k |
| A16 | Rescope hệ thống = "offline audit monitor"; deployable → future work (latency 52s) | P1 | WRITE | ✅ | câu viết lại đầy đủ đã có |
| A17 | Sửa câu "1 completion mang >toàn bộ MI panel": LLR điểm có thể >H(K) nhưng ≠ MI | P1 | WRITE | ✅ | giải thích đầy đủ (per-instance stat vs population MI aggregate), khớp code (`max_kl` không bị cap, certificate mới bị cap) |
| A18 | Phân biệt exact / semantic extraction / MIA / likelihood exposure | P1 | WRITE | ✅ | bảng 4 khái niệm + cảnh báo exact-rate thấp ≠ likelihood exposure thấp |
| **A19** | **[THÊM từ review] Related-work: định vị so với Secret Sharer / Carlini extraction / DP** | P1 | WRITE | ✅ | **viết lại 2026-08-23** — `results/A19_related_work_positioning_draft.md`, so sánh 3 trục (Secret Sharer/Carlini extraction/DP-SGD) + sơ đồ định vị; cần điền số `[TODO-cite]` cho Secret Sharer theo .bib thật |

---

## NHÓM B — PHÂN TÍCH LẠI DỮ LIỆU ĐÃ CÓ (không train, không gen mới)

| # | Việc | Prio | Cost | Status | Notes |
|:--|:--|:--|:--|:--|:--|
| B1 | Tính lại **Clopper–Pearson theo canary** (0/100 → 3.62%); báo cáo 2 estimand; sửa mọi 0.55%/0.11% | P0 | REANALYZE | ✅ | `results/B1_extraction_ci_recompute.md` + `compute_cp_ci.awk`. Còn lại: sửa số trong doc/PDF |
| B2 | Báo cáo thẳng 1 hit sampled-decoding (nội dung, true/false/ambiguous) | P0 | REANALYZE | ✅ | `results/B2_sampled_hit_report.md` + row. 1/142632, T4 pattern, **ambiguous/false-pos**, chỉ B1 |
| B3 | **Cluster/hierarchical bootstrap** seed→canary→prompt-family; cập nhật bảng W5 multiseed | P0 | REANALYZE | 🔄 | audit rows là **single-seed**; cần raw multiseed (đang locate trên HPC) |
| B4 | "no utility cost" → non-inferiority độ phân giải thấp + CI (n=164, pass@1 6.1%) | P1 | REANALYZE | ⬜ | |
| B5 | Báo cáo max per-secret leakage + phân bố theo canary + P(any secret extracted) | P1 | REANALYZE | ⬜ | |
| B6 | Entropy-cap audit: trình raw vs capped vs vacuity flag cho mọi bảng | P2 | REANALYZE | ✅ | đã có |

---

## NHÓM C — INFERENCE (checkpoint sẵn có, không train)

| # | Việc | Prio | Cost | Status | Notes |
|:--|:--|:--|:--|:--|:--|
| C1 | **Non-member control**: chạy estimator exposure/LLR trên panel non-member seed 999; so phân bố member vs non-member | P0 | INFER (vài giờ GPU) | ✅ **XONG — kết luận: negative result, đã audit + viết vào bài** | base-ref (job 1004390): AUC=0.49, gap=0.001. D1-ref (job 1006733): AUC=0.4855, gap=-0.0149 — **cùng pattern**, không reference nào tách biệt được member/non-member. **Đã audit code (`generator.py`/`types.py`/`injector.py`) — không có bug.** Kết luận + 2 giả thuyết (dưới ngưỡng phát hiện do inject 1 lần; format-generalization confound) + khuyến nghị viết negative-result/limitations subsection: `results/C1_D1ref_result.md`. Xem §0 (đã chốt hướng xử lý) |
| C2 | Scorer **semantic/AST/data-flow/similarity** cho T2/T3, chấm lại output | P0 | INFER + code | ⬜ | |
| C3 | Chấm T4 theo **vulnerability-pattern / hành vi** thay vì exact | P1 | INFER + code | ⬜ | |
| C4 | Nested threshold: tune trên validation, freeze, đánh giá trên split disjoint | P1 | INFER | ⬜ | t=0.95 |
| C5 | 1 kịch bản certificate-budget/rate-limit đổi 1 quyết định an ninh (dùng runtime sẵn có) | P1 | INFER | ⬜ | |
| C6 | Nhiều sample/problem HumanEval + MBPP+ → pass@k + CI | P1 | INFER | ⬜ | |
| C7 | Attack mạnh hơn (prefix-ranking/beam/constrained) hoặc thu hẹp claim (hiện chỉ B=100) | P1 | INFER (tốn giờ) | ⬜ | W4 hiện 0% @ B=100, job 1002479 |
| C8 | Sample-complexity ước lượng logprob bằng sampling → định lượng claim black-box | P2 | INFER | ⬜ | |

---

## NHÓM D — TRAIN model mới (tốn GPU-giờ)

| # | Việc | Prio | Cost | Status | Notes |
|:--|:--|:--|:--|:--|:--|
| D1 | **Train 1 model corpus 500k KHÔNG canary** làm reference đúng | **P0** | TRAIN (1 lần) | ✅ **DONE** | **job 1005226 FAILED** (2026-08-19, 4h20m, chết ở step 9000/124014 ~7%, checkpoint-9000 ghi dở — thiếu rng_state_0.pth/scheduler.pt/trainer_state.json, không traceback rõ, có thể lỗi node/storage thoáng qua chứ không phải OOM). checkpoint-6000 **còn nguyên vẹn**. Đã thêm `--resume-from-checkpoint` vào `prepare_and_train_target.py`/`fine_tuner.py`/`train_multi.sbatch` (resume chuẩn qua HF Trainer). **job 1005979** (3×L40S, mem 240G, 72h, resume từ checkpoint-6000) — chạy từ 2026-08-20 20:31 (node a768-l40s-02) → **COMPLETED 2026-08-23 06:05** (State=COMPLETED, ExitCode=0:0, tổng 2 ngày 9h34m36s, 124014/124014 step). Model lưu tại `checkpoints/reference_nocanary/` (`model.safetensors` 3GB, `train_summary.json`). Trước đó: 1003719 1-GPU (timeout<1ep), 1004389 4-GPU (cancel). **Sẵn sàng cho C1 (D1-ref variant)** |
| D2 | Shadow models canary ngẫu nhiên cho concentration (mẫu độc lập) | P1→"nếu kịp" | TRAIN (nhiều) | ⏸ | phương án lui: hạ claim, giả thiết yếu hơn |
| D3 | Train nhiều matched models đo empirical coverage "99%" | P1→"nếu kịp" | TRAIN (nhiều) | ⏸ | rất tốn; nếu không → **bỏ claim 99% coverage** |
| D4 | ≥1 checkpoint DP-SGD (vd ε=8) so sánh thực thay bảng analytic | P1 | TRAIN (1 GPU) | 🔄 RUNNING | **5 lần fail liên tiếp**: 1004393/1005225/1005981 (OOM host RAM, root cause: `TextDataset` stride suy biến — xem lịch sử, đã fix). 1006157 FAILED sau 8m52' (2026-08-21) — qua được OOM nhưng crash mới: `get_epsilon()` gọi tại `global_step=0` trước khi có step nào → Opacus PRV accountant NaN. Fix: guard `global_step > 0` (`fine_tuner.py:387`). **1006284** (2026-08-21 18:16, cuối cùng lấy được GPU sau khi 9 job khác của account — `llada_m23_*`/`base_maskgr3`/... — nhả bớt quota 12-GPU/user) **FAILED sau 9m30'**: `torch.OutOfMemoryError: CUDA out of memory` thật (GPU, không phải host) trong `optimizer.step()`→Opacus `pre_step()`→`torch.cat(p.grad_sample)`. **Root cause**: vòng lặp DP không `zero_grad()` giữa các microbatch trong 1 nhóm `gradient_accumulation_steps=2`, nên Opacus giữ `p.grad_sample` là **list** tích lũy qua từng `backward()`, chỉ `torch.cat()` lúc `optimizer.step()` — nhân đôi bộ nhớ per-sample-gradient so với 1 microbatch. Model 1.5B, batch ảo=4 (2×2) đã tràn 44GB L40S. Fix: `gradient_accumulation_steps: 2→1` trong `aau_dp_eps8.yaml` (mỗi backward() step ngay, không tích lũy) — đồng thời sửa luôn 1 lệch nhỏ trong tính privacy budget (accountant trước đây chỉ step 1/2 số lần `make_private_with_epsilon` giả định). 1006646 (2026-08-22 22:06, chạy ngay vì có GPU trống) **FAILED sau 10m07'** — qua được bug grad_sample list (accum=1 đã đúng!) nhưng OOM ở bước KHÁC: `torch.OutOfMemoryError` trong `AdamW._init_group` lúc cấp phát `exp_avg_sq` lần đầu (44.38/44.39GB đã dùng trước đó). Root cause: model 1.5B fp32 + per-sample-grad buffer Opacus cho batch=2 + gradient tổng hợp đã sát trần 44GB L40S, không còn chỗ cho AdamW state (~12GB). Fix: `per_device_train_batch_size: 2→1` (loại bỏ phần overhead per-sample-gradient nhân đôi). 1006649 (2026-08-22 22:19) **FAILED sau 8m54'** — tiến thêm: qua được cấp phát `exp_avg_sq` (fix batch=1 đúng hướng), nhưng OOM **ngay trong phép tính** Adam foreach: `torch._foreach_sqrt(device_exp_avg_sqs)` cấp thêm ~6GB buffer tạm để tính sqrt gộp toàn bộ tensor 1 lượt, đúng lúc GPU chỉ còn 57MB trống. batch=1 đã là tối thiểu, không giảm thêm được. Fix: `optimizer = torch.optim.AdamW(..., foreach=False)` — bắt Adam tính per-tensor thay vì gộp hết thành 1 buffer lớn (chậm hơn, nhưng đỉnh bộ nhớ tạm chỉ bằng 1 tensor thay vì cả model). **Resubmit: job 1006651** (2026-08-22 22:32) — batch=1, accumulation=1, foreach=False. **THÀNH CÔNG lần đầu tiên**: qua hết OOM, đang training thật (log 2026-08-22 17:40+: `Step 50 loss=1.1774 ε=0.0227` → 2026-08-23 07:37, Step 90400, ε=5.07/8 mục tiêu). **Rủi ro phát hiện 2026-08-23**: DP loop trước đây chỉ save model **1 lần duy nhất sau khi hết cả 3 epoch** — nếu job chạm giới hạn wall-time 48h giữa chừng (job có 51,566 doc × batch=1, ước tính có thể sát hoặc vượt 48h), toàn bộ tiến độ mất trắng, không checkpoint. Đã fix: thêm `_save_dp_checkpoint()` + `_prune_dp_checkpoints()` vào `fine_tuner.py::_train_with_dp`, lưu checkpoint mỗi `cfg.save_steps` (2000) step, giữ tối đa `save_total_limit` (2) checkpoint gần nhất — cùng cơ chế `save_steps`/`save_total_limit` path non-DP đã dùng. Đã upload lên server 2026-08-23 12:41 — **không ảnh hưởng job 1006651 đang chạy** (Python đã nạp module cũ vào RAM), chỉ áp dụng cho lần chạy kế tiếp nếu cần resubmit. Job 1006651 vẫn đang RUNNING, còn 1 ngày 9h52m trong ngân sách wall-time (đã dùng 14h07m tại lần check) |
| D5 | 7B trên corpus tương đương 1.5B + đủ attack/utility, hoặc gỡ hẳn 7B | P1 | TRAIN | ⬜ | gắn A14 |
| D5-eval | **7B attack suite (W4/W5/LRT)** trên `target_mid_sub2/ckpt-20614` (smoke 7B) — 7B có verbatim-leak nơi 1.5B không? | P1 | INFER | ✅ W4/W5 | **CÓ leak: W4 10.3%, A-adaptive 16%, W5 ~8%** (vs 1.5B 0%). `results/D5eval_7B_extraction_result.md`. Caveat: corpus mismatch (A14). Defense KHÔNG giảm leak — cần điều tra. LRT có thể timeout (đã lưu W4/W5) |
| D6 | Lặp trên model code hữu dụng (instruction-tuned) | P1/P2 | TRAIN | ⬜ | |
| D7 | Inject secret cấu trúc repo-level (trùng lặp & tương quan) | P2 | TRAIN | ⬜ | |

---

## Thứ tự thực thi

- **Vòng 1 (viết + phân tích lại):** A1–A10, A17, A19 · B1, B2, B3 → cứu phần lớn phản biện lý thuyết & thống kê.
- **Vòng 2 (inference):** C1 → C2/C3 → C4 → C6 → C7 → C5.
- **Vòng 3 (train):** **D1 quan trọng nhất**; D2/D3 chỉ nếu kịp; rồi D4, D5, D6.

## "Sống còn" — bỏ là reject lại

- [ ] A1 + A2 (định lý đúng + chứng minh)
- [ ] A3 + A8/A17 (không gọi sai MI/KL)
- [ ] B1 (CI theo canary)
- [ ] **C1 tối thiểu** — lý tưởng là **D1** (tách memorization khỏi fine-tuning shift)

## Điểm mạnh — giữ & làm nổi bật

- FP-control làm sập SPRT completion-based (retraction trung thực) — đóng góp mạnh nhất, đưa lên đầu.
- memorization ≠ extraction (gọi đúng tên đại lượng).
- Báo cáo vacuity minh bạch. · Ethics tốt.
