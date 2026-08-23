# A19 — Related-work positioning: Secret Sharer / Carlini extraction / DP (hand-off draft)

**Trạng thái:** viết lại từ đầu 2026-08-23 (không tìm thấy bản draft cũ trên máy này). Số hiệu
trích dẫn `[n]` bên dưới dùng lại đúng số đã xuất hiện trong code (`leakcert/attacks/`,
`leakcert/model/fine_tuner.py`) khi khớp được; những chỗ đánh `[TODO-cite]` nghĩa là paper liên
quan chưa có số hiệu trong code — cần điền đúng số theo `.bib` thật của bài (không có ở máy
này).

---

## 1. So với "The Secret Sharer" (Carlini et al. 2019) `[TODO-cite]`

**Điểm giống:** cả hai đều dùng **canary injection** + một độ đo dựa trên likelihood
("exposure" trong Secret Sharer, "LLR/exposure" $\hat\kappa_i$ ở đây — xem A8) để đo
memorization mà không cần mô hình sinh ra đúng chuỗi bí mật (khác exact-match).

**Điểm khác — đây là phần cần viết rõ trong Related Work:**

| | Secret Sharer (2019) | LeakCert (bài này) |
|---|---|---|
| Đơn vị đo | **Exposure** = rank của log-perplexity secret thật trong phân phối perplexity của các secret ứng viên cùng dạng (đo bằng **percentile/rank**, không cần reference model) | $\hat\kappa_i$ = **log-likelihood-ratio** so với reference model $q$ (Assumption 12), cần model tham chiếu |
| Cơ sở lý thuyết | Thực nghiệm + thống kê mô tả (không có định lý MI/certificate) | Có certificate hình thức (Định lý 5′/7′/10′/13′, Lemma 0) chặn $I(K;Y^B)$ |
| Reference cần | Không cần model tham chiếu — chỉ cần tập candidate cùng dạng để xếp hạng | Cần model tham chiếu $q$ (base hoặc D1); theo Lemma 0, **bất kỳ** $q$ nào cũng cho chặn hợp lệ (chỉ ảnh hưởng độ chặt), đây là khác biệt phương pháp luận quan trọng cần nêu |
| Guarantee | Không có guarantee hình thức, thuần thực nghiệm | Certificate có xác suất bảo đảm $1-\delta$ (concentration), nhưng — như A11 chỉ ra — **vacuous** ở hầu hết ngân sách truy vấn thực tế |
| Panel vs. per-secret | Exposure tính **per-secret**, không tổng hợp thành 1 số panel-level | Certificate hiện tại claim panel-average (sau khi sửa theo A10), nhưng vẫn báo cáo per-canary `max_kl` |

**Câu định vị đề xuất cho Related Work:**
> *"Exposure [Secret Sharer, TODO-cite] established rank-based memorization measurement without
> requiring a reference model, at the cost of no formal information-theoretic guarantee. We
> trade the model-free property for a certifiable (if often vacuous, §A11) upper bound on
> mutual information, using a reference model as a variational surrogate (Lemma 0) rather than
> exact rank statistics. The two measures are complementary: exposure is cheaper to compute
> and does not depend on reference-model quality, while our certificate is falsifiable
> (violated only with probability $\le\delta$) and composes formally across an adaptive query
> budget $B$ — a property exposure's rank-based definition does not have (rank does not
> naturally compose over repeated queries)."*

---

## 2. So với extraction attacks (Carlini et al. 2021, "Extracting Training Data from Large
## Language Models") `[1]`, `[55]` (đã dùng trong `a_carlini.py`)

**Điểm giống:** cùng dùng perplexity-ranking để phát hiện memorization qua nhiều completion
samples (`A-Carlini` trong `leakcert/attacks/a_carlini.py` implement trực tiếp protocol này,
B7 baseline).

**Điểm khác:**
- Carlini 2021 là một **attack** (extraction thành công/thất bại nhị phân trên corpus lớn,
  không kiểm soát được), không đi kèm certificate/upper-bound nào — mục tiêu của họ là chứng
  minh sự tồn tại (existence proof) của memorization ở quy mô lớn, không phải đo hay chặn nó.
- Bài này dùng attack cùng họ (`A-Carlini`, B7) như MỘT trong năm baseline attack **để kiểm
  định thực nghiệm** certificate (đối chiếu extraction rate quan sát được với chặn lý thuyết),
  chứ không phải đóng góp attack mới — cần nói rõ điều này để tránh reviewer hiểu nhầm `A-Carlini`
  là contribution.
- Certificate ở đây được thiết kế để **upper-bound** khả năng của MỌI attacker (kể cả
  Carlini-style), không riêng gì attack cụ thể nào — đây là lý do cần validate bằng nhiều attack
  khác nhau (A-fixed, A-grid, A-adaptive, A-greedy-LRT, A-Carlini) thay vì chỉ một.

**Câu định vị đề xuất:**
> *"[Carlini 2021] demonstrated that verbatim memorization is extractable at scale from large
> language models using perplexity-ranked sampling; we adopt the same ranking protocol as one
> of five attacker baselines (B7/A-Carlini, §4.2) used to empirically stress-test our
> certificate, rather than proposing it as a new attack. Where [Carlini 2021] is existential
> ('memorized examples exist and are extractable'), our certificate aims to be a falsifiable
> upper bound applicable before any specific attack is mounted — though, as we show, this bound
> is non-vacuous only in a narrow regime (§A11)."*

---

## 3. So với Differential Privacy (Abadi et al. DP-SGD `[5]`; Rényi DP composition)

**Đã có sẵn trong code:** `LeakageCertificate.dp_composition_certificate()` implement chặn
analytic cho model $(\varepsilon,\delta)$-DP: $I(K;Y^B) \le \min\{B\varepsilon^2/2, H(K)\}$
(dùng cho Table 8 so sánh). D4 (job DP-SGD ε=8, xem tracker NHÓM D) cung cấp **một điểm dữ liệu
thực nghiệm thực** để so với chặn analytic này — đây là đóng góp thật (trước resubmit chỉ có
bảng analytic-only, review đã yêu cầu ít nhất 1 checkpoint DP thật).

**Điểm khác biệt cần nêu rõ (đây là đóng góp định vị quan trọng nhất của A19):**
- DP cho guarantee **worst-case, không phụ thuộc dữ liệu** (holds for *any* neighboring
  dataset, *any* adversary) — rất mạnh nhưng thường rất lỏng (vacuous ở $\varepsilon$ thực tế
  dùng để giữ utility, đúng như D4 sẽ cho thấy qua so sánh utility/leakage thực đo).
- Certificate của bài này là **data- và model-dependent, thực nghiệm** (dùng $\hat\kappa$ đo
  được trên chính model đã train) — **chặt hơn DP trong trường hợp cụ thể đã quan sát**, nhưng
  **không phải worst-case guarantee** (không bảo vệ trước một canary/dataset khác chưa từng
  quan sát). Đây là trade-off cơ bản cần nói thẳng: "empirical, instance-specific, tighter" vs.
  "worst-case, dataset-agnostic, looser".
- **Không claim thay thế DP** — claim đúng là: certificate này là công cụ **audit bổ sung**
  cho các mô hình KHÔNG dùng DP (chi phí utility của DP thường quá cao để chấp nhận trong thực
  tế, xem D4 sẽ cho số liệu utility/leakage cụ thể), cung cấp một mức bảo đảm yếu hơn DP nhưng
  rẻ hơn nhiều về utility cost.

**Câu định vị đề xuất:**
> *"Unlike DP-SGD [Abadi et al., 5], which certifies a worst-case, dataset-independent bound at
> the cost of substantial utility degradation, our certificate is an **empirical, a-posteriori**
> bound computed from the actually-trained model's observed exposure. It is tighter in the
> instance we measure but offers no protection against canaries or datasets not covered by the
> audit panel (§A13) — it is best understood as a cheaper, weaker complement to DP for
> deployments where DP's utility cost (Table 8, D4 empirical DP-SGD checkpoint) is judged
> unacceptable, not a replacement for it."*

---

## Tổng kết vị trí trong không gian 3 trục

```
                    Formal guarantee ↑
                          │
                DP-SGD ●  │
   (worst-case,          │
    utility-costly)      │
                          │  ● LeakCert certificate (this paper)
                          │    (empirical, instance-specific,
                          │     often vacuous in practice — §A11)
     ─────────────────────┼───────────────────────────→
                          │              Extraction attacks
     Secret Sharer ●      │              (Carlini 2021, A-Carlini/B7)
   (rank-based,           │              (existential, no bound,
    model-free,           │               no formal guarantee)
    no bound)             │
                          │
                    No formal guarantee ↓
```

*(Sơ đồ minh hoạ ý tưởng, không phải để đưa nguyên vào bài — vẽ lại bằng tikz/tương đương nếu
muốn dùng trong bài.)*

## Việc cần làm tiếp
1. Điền đúng số hiệu `[TODO-cite]` cho Secret Sharer (Carlini et al. 2019) theo `.bib` thật —
   không có file `.bib` trên máy này để tra.
2. Xác nhận số hiệu `[1]`/`[55]` trong `a_carlini.py` đúng là Carlini et al. 2021 "Extracting
   Training Data" (suy luận từ tên biến/docstring, chưa đối chiếu `.bib`).
3. Sau khi D4 (DP-SGD ε=8, job đang chạy — xem tracker) hoàn tất, điền số liệu utility/leakage
   thực tế vào đoạn so sánh DP ở mục 3 (hiện đang viết dạng khung, chưa có số).
