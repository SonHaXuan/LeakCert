# LEAKCERT — NDSS 2027 resubmit progress tracker

Nguồn: `review_triage_plan (1).md` (panel triage). File này theo dõi **tiến độ thực thi**.
Cập nhật cột **Status** mỗi khi làm; ghi commit / job ID vào **Notes**.

- **Status legend:** ⬜ chưa bắt đầu · 🔄 đang làm · ✅ xong · ⏸ hoãn/đợi · ❌ bỏ (kèm lý do)
- **Priority:** P0 = không sửa thì reject lại · P1 = cần để đủ mạnh · P2 = trau chuốt
- **Cost:** WRITE = chỉ viết/toán · REANALYZE = tính lại số cũ · INFER = inference (checkpoint sẵn có) · TRAIN = phải train model mới

> Cập nhật lần cuối: 2026-08-17 · Branch: `feature/training-pipeline-aau-hpc`

---

## 0. Quyết định định vị bài (chốt trước khi viết)

Ba hệ quả từ review — **chốt sớm vì nó quyết định câu chữ toàn bài**:

- [ ] **Bỏ headline "first non-vacuous certificate".** Dạng min chứng minh được nhưng vẫn vacuous ở mọi budget trừ T4 @ B∈{1,2}. Reframe headline = *honest audit + memorization ≠ extraction + FP-control làm sập SPRT (retraction trung thực)*.
- [x] **Chốt mức resubmit (2026-08-17): CHUẨN — train đúng 1 model D1.** ⇒ giữ claim "memorization thật, tách khỏi fine-tuning shift"; D1 là bắt buộc, D2–D5 chỉ nếu kịp.
- [ ] **C1 và D1 là bổ sung, KHÔNG thay thế.** C1 = non-member control trên cùng model; D1 = sửa reference sai marginal. Giữ claim "memorization thật" ⇒ cần D1.

---

## NHÓM A — Sửa bằng VIẾT / TOÁN (không chạy lại gì)

> ⚠️ Repo **không chứa source LaTeX** của paper → các mục WRITE được làm thành **bản draft hand-off** trong `results/` (bạn dán vào .tex), không edit trực tiếp bài.

| # | Việc | Prio | Cost | Status | Notes |
|:--|:--|:--|:--|:--|:--|
| A1 | Phát biểu lại định lý 5/7/10/12 ở dạng `I(K;Y^B) ≤ min{H(K), Σ E[KL]}` + chứng minh lại | P0 | WRITE | 🔄 | draft `results/A_theory_corrections_draft.md`; còn dán vào .tex |
| A2 | Viết đầy đủ Appendix A, B (chứng minh) vào PDF nộp | P0 | WRITE | 🔄 | proof sketch A1/A6 đã có trong draft; còn viết full vào Appendix |
| A3 | Định nghĩa tường minh game rò rỉ + joint `P_{K,M,X^B,Y^B}` (K index cái gì, ai biết c_K) | P0 | WRITE | 🔄 | drafted (A3 trong file) |
| A4 | Định lý 15: sửa "submartingale" → **supermartingale** | P0 | WRITE | 🔄 | drafted; sửa 1 từ trong .tex |
| A5 | Bỏ/hạ mệnh đề nhảy từ "SPRT optimal stopping" → "optimal adaptive prompt design" | P0 | WRITE | 🔄 | drafted (3 phương án) |
| A6 | Fano prior không đều: sửa mẫu số `log|K|` | P0 | WRITE | 🔄 | drafted (viết theo H(K)) |
| A7 | Định lý utility–leakage: hạ thành "quan sát thực nghiệm" hoặc bỏ | P0 | WRITE | 🔄 | drafted |
| A8 | Đổi nhãn "KL divergence" → **exposure / LLR / memorization score** xuyên suốt | P0 | WRITE | 🔄 | glossary trong draft |
| A9 | Định nghĩa lại threat model = **gray-box likelihood audit**, phân tầng sample/logprob/local | P0 | WRITE | ⬜ | |
| A10 | Đổi "per-secret certificate" → **panel-average / canary-panel audit** | P0 | WRITE | 🔄 | glossary trong draft |
| A11 | Bỏ "first non-vacuous certificate" tới khi định lý đã sửa + so literature | P1 | WRITE | ⬜ | gắn với §0 |
| A12 | "no utility cost" → "không phát hiện khác biệt utility ở độ phân giải này" | P1 | WRITE | ⬜ | |
| A13 | Nói rõ: audit panel canary, không guarantee toàn deployment | P1 | WRITE | ⬜ | |
| A14 | Trình bày 7B là **pipeline smoke test**, gỡ khỏi vai trò "bằng chứng scale" | P1 | WRITE | ⬜ | |
| A15 | Ghi rõ arm nào dùng checkpoint nào (1.5B/7B/0.5B) | P1 | WRITE | ⬜ | |
| A16 | Rescope hệ thống = "offline audit monitor"; deployable → future work (latency 52s) | P1 | WRITE | ⬜ | |
| A17 | Sửa câu "1 completion mang >toàn bộ MI panel": LLR điểm có thể >H(K) nhưng ≠ MI | P1 | WRITE | 🔄 | drafted |
| A18 | Phân biệt exact / semantic extraction / MIA / likelihood exposure | P1 | WRITE | ⬜ | |
| **A19** | **[THÊM từ review] Related-work: định vị so với Secret Sharer / Carlini extraction / DP** | P1 | WRITE | 🔄 | draft `results/A19_related_work_positioning_draft.md` |

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
| C1 | **Non-member control**: chạy estimator exposure/LLR trên panel non-member seed 999; so phân bố member vs non-member | P0 | INFER (vài giờ GPU) | ✅ base-ref / 🔄 D1-ref | **base-ref DONE (job 1004390)**: AUC=0.49, gap=0.001 → 156-nat = fine-tuning shift, non chứng minh critique. `results/C1_base_ref_result.md`. D1-ref chờ 1004389 |
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
| D1 | **Train 1 model corpus 500k KHÔNG canary** làm reference đúng | **P0** | TRAIN (1 lần) | 🔄 PENDING | **job 1005226** (3×L40S, 72h, ~53h/3ep). Trước: 1003719 1-GPU (timeout<1ep), 1004389 4-GPU (cancel). Lower→3 GPU. **Cluster L40S+A40 100% full** → chờ free. Xong → C1 |
| D2 | Shadow models canary ngẫu nhiên cho concentration (mẫu độc lập) | P1→"nếu kịp" | TRAIN (nhiều) | ⏸ | phương án lui: hạ claim, giả thiết yếu hơn |
| D3 | Train nhiều matched models đo empirical coverage "99%" | P1→"nếu kịp" | TRAIN (nhiều) | ⏸ | rất tốn; nếu không → **bỏ claim 99% coverage** |
| D4 | ≥1 checkpoint DP-SGD (vd ε=8) so sánh thực thay bảng analytic | P1 | TRAIN (1 GPU) | 🔄 PENDING | **job 1005225** (retry2, mem 200G). 1004393 CUDA-OOM @batch4 → batch2; 1004396 host-RAM-OOM @mem80G → mem 200G. 40k, canary ON |
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
