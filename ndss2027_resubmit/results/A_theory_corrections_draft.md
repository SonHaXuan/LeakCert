# Nhóm A — Theory & framing corrections (hand-off draft)

**Trạng thái:** viết lại từ đầu 2026-08-23 (không tìm thấy bản draft cũ trên máy này — xem
ghi chú trong `ndss2027_resubmit_progress.md`). Nội dung dưới đây bám sát implementation
hiện tại trong `leakcert/certificate/certificate.py` và `leakcert/certificate/kl_estimator.py`
để đảm bảo định lý sửa lại khớp với những gì code thực sự tính. Đơn vị: **nats** xuyên suốt
(khớp code). Dán trực tiếp vào .tex — các đoạn "Sửa trong .tex" chỉ ra chỗ cần thay.

---

## 0. Lemma nền tảng dùng chung (mới — chưa có trong bản gốc)

Toàn bộ A1, A6, A7, A17 đều dùng lại **một** identity biến phân (variational) của mutual
information. Nên đưa vào Appendix A như Lemma 0, rồi mọi định lý khác chỉ là hệ quả.

> **Lemma 0 (Golden formula / variational MI identity).**
> Cho biến ngẫu nhiên rời rạc $K$ và biến ngẫu nhiên (có thể liên tục) $Y$ với luật có điều
> kiện $P_{Y\mid K}$. Với **mọi** phân phối $Q$ trên không gian của $Y$ (không nhất thiết là
> marginal thật $P_Y$):
> $$ I(K;Y) \;=\; \min_{Q} \; \mathbb{E}_{K}\big[D_{\mathrm{KL}}(P_{Y\mid K} \,\Vert\, Q)\big] \;\le\; \mathbb{E}_{K}\big[D_{\mathrm{KL}}(P_{Y\mid K} \,\Vert\, Q)\big], \quad \forall Q. $$
> Cực tiểu đạt được duy nhất tại $Q = P_Y$ (marginal thật).
>
> **Chứng minh.** Với $Q$ bất kỳ,
> $$ \mathbb{E}_K\big[D_{\mathrm{KL}}(P_{Y\mid K}\Vert Q)\big] - I(K;Y) = \mathbb{E}_K\big[D_{\mathrm{KL}}(P_{Y\mid K}\Vert Q)\big] - \mathbb{E}_K\big[D_{\mathrm{KL}}(P_{Y\mid K}\Vert P_Y)\big] = D_{\mathrm{KL}}(P_Y \Vert Q) \ge 0, $$
> đẳng thức thứ nhất suy ra trực tiếp từ định nghĩa $I(K;Y)=\mathbb E_K[D_{\rm KL}(P_{Y|K}\Vert P_Y)]$
> và khai triển $\log(P_{Y|K}/Q) = \log(P_{Y|K}/P_Y) + \log(P_Y/Q)$ rồi lấy kỳ vọng theo
> $P_{K,Y}$; số hạng cuối chính là $D_{\rm KL}(P_Y\Vert Q)\ge 0$ (Gibbs). $\blacksquare$

**Vì sao lemma này quan trọng (trả lời thẳng câu hỏi phản biện):** nó là lý do DUY NHẤT
khiến việc dùng **reference model** $q$ (base model, hoặc D1 — model cùng corpus nhưng
không canary) thay cho marginal thật $P_Y$ (không thể tính được) là **hợp lệ về mặt lý
thuyết**, không phải một xấp xỉ heuristic. Bất kể $q$ gần hay xa marginal thật, bất đẳng thức
vẫn đúng — $q$ chỉ ảnh hưởng đến độ **chặt (tightness)** của chặn, không ảnh hưởng tính
**đúng đắn (soundness)**. Đây là điểm cần nói rõ trong bài vì hiện tại (theo review) lý do
dùng reference model bị bỏ ngỏ.

---

## A1 + A2 — Phát biểu lại Định lý 5/7/10/13 dạng `I(K;Y^B) ≤ min{H(K), Σ E[KL]}` + chứng minh đầy đủ

### Định lý 5′ (population bound, uniform prior — thay Định lý 5 cũ)

> Cho $K\sim\mathrm{Uniform}(\mathcal K)$, $|\mathcal K|<\infty$. Attacker thực hiện $B$ câu
> hỏi thích nghi (adaptive) $x_1,\dots,x_B$ tới mô hình đích $M_\theta$, nhận về
> $Y_1,\dots,Y_B$ với $Y_b \sim M_\theta(\cdot \mid x_b, \mathrm{history}_{<b})$. Với **mọi**
> họ phân phối tham chiếu $q_b(\cdot\mid \mathrm{history}_{<b})$ (không cần là marginal thật):
> $$ I(K; Y^B) \;\le\; \min\Big\{\, H(K),\; \sum_{b=1}^{B} \mathbb E\big[D_{\mathrm{KL}}\big(p_{K}(\cdot\mid \mathrm{history}_{<b}) \,\Vert\, q_b(\cdot\mid\mathrm{history}_{<b})\big)\big] \Big\}. $$

**Chứng minh.** Chain rule của mutual information: $I(K;Y^B)=\sum_{b=1}^B I(K;Y_b\mid Y_{<b})$.
Với mỗi số hạng, áp dụng Lemma 0 theo điều kiện trên $Y_{<b}=y_{<b}$ cố định (lấy $Q=q_b(\cdot\mid
y_{<b})$):
$$ I(K;Y_b\mid Y_{<b}=y_{<b}) \le \mathbb E_K\big[D_{\rm KL}(p_K(\cdot\mid y_{<b})\Vert q_b(\cdot\mid y_{<b}))\big]. $$
Lấy kỳ vọng theo $Y_{<b}$ rồi cộng dồn $b=1,\dots,B$ cho vế phải của định lý. Chặn trên thứ
hai $I(K;Y^B)\le H(K)$ là bất đẳng thức entropy chuẩn ($I(K;Y^B)\le H(K)$ luôn đúng vì mutual
information không vượt quá entropy biên của biến rời rạc). Lấy min hai chặn. $\blacksquare$

**Trường hợp đặc biệt = code hiện tại.** Nếu (i) $q_b\equiv q$ không đổi theo $b$ (dùng một
reference model cố định, đúng như `KLEstimator(target, ref)`), và (ii) ta chặn thô từng số
hạng bằng giá trị lớn nhất quan sát được $\hat\kappa_{\max} := \max_i \hat\kappa_i$ (tương ứng
`kappa_max` trong `_theorem5`), thì $\sum_{b=1}^B(\cdot) \le B\cdot \hat\kappa_{\max}$, đúng
bằng công thức `pop_cert = B * kappa_max` đang implement. Vậy **code hiện tại tính đúng một
trường hợp riêng** của Định lý 5′ tổng quát hơn ở trên — cần nói rõ trong bài đây là chặn thô
(coarsening), không phải bản thân định lý.

### Định lý 7′ (non-uniform prior — thay Định lý 7 cũ)

Hệ quả trực tiếp của Định lý 5′ khi $K\sim\pi$ bất kỳ (không cần uniform): thay $H(K)$ bởi
entropy Shannon $H_\pi(K)=-\sum_k\pi(k)\log\pi(k)$, và thay $\hat\kappa_{\max}$ (max) bởi kỳ
vọng có trọng số $\mathbb E_\pi[\hat\kappa] = \sum_k \pi(k)\hat\kappa_k$ (đúng biến
`weighted_kl` trong `_theorem7`):
$$ I(K;Y^B) \le \min\{H_\pi(K),\; B\cdot \mathbb E_\pi[\hat\kappa]\}. $$
**Chứng minh:** thay $K\sim\mathrm{Uniform}$ bằng $K\sim\pi$ trong chứng minh Định lý 5′; chain
rule và Lemma 0 không phụ thuộc phân phối $K$ là đều hay không. $\blacksquare$

### Định lý 10′ / 13′ (concentration — Hoeffding / Bernstein, giữ nguyên cấu trúc, viết rõ chứng minh)

Hai định lý này KHÔNG cần sửa công thức (code đã đúng), nhưng review yêu cầu chứng minh đầy
đủ vào Appendix thay vì chỉ nêu công thức. Viết lại:

> **Định lý 10′ (Hoeffding, black-box).** Cho $n$ mẫu i.i.d. $\hat\kappa_1,\dots,\hat\kappa_n
> \in[0,\kappa_{\max}]$ là ước lượng LLR trên $n$ canary của panel (Định nghĩa ở §A3 bên
> dưới), là surrogate không chệch (Assumption 12) của $D_{\rm KL}(p_K\Vert q_K)$ trung bình
> trên panel. Với xác suất $\ge 1-\delta$:
> $$ \Big|\frac1n\sum_i \hat\kappa_i - \mathbb E[\hat\kappa]\Big| \le \kappa_{\max}\sqrt{\frac{\log(2/\delta)}{2n}}. $$
> **Chứng minh:** Hoeffding's inequality cho biến bị chặn trong $[0,\kappa_{\max}]$, hai phía,
> union bound cho $\delta/2$ mỗi phía $\Rightarrow$ $\log(2/\delta)$ thay vì $\log(1/\delta)$.
> Nhân cả hai vế với $B$ và cộng với chặn population $B\cdot\hat{\bar\kappa}_n$ (triangle
> inequality theo hướng bất lợi nhất cho attacker) cho đúng công thức
> `cert = B*(mean_kl + slack)` đang implement. $\blacksquare$
>
> **Định lý 13′ (Bernstein, MI-surrogate).** Cùng giả thiết, nhưng nếu biết thêm
> $\mathrm{Var}(\hat\kappa)\le\sigma^2$ (Assumption 12, ước lượng bằng std thực nghiệm — biến
> `sigma = std_kl` trong code), Bernstein's inequality (dạng sub-Gaussian đơn giản hoá, bỏ
> phần hiệu chỉnh $O(1/n)$ bậc cao vì $\hat\kappa_{\max}$ nhỏ so với $n$ trong chế độ dùng của
> ta) cho:
> $$ \Big|\frac1n\sum_i\hat\kappa_i - \mathbb E[\hat\kappa]\Big| \le \sigma\sqrt{\frac{2\log(2/\delta)}{n}}, $$
> chặt hơn Hoeffding khi $\sigma \ll \kappa_{\max}$ (đúng tên gọi "tighter for small σ²" trong
> docstring code). $\blacksquare$

**Cả hai chặn đều phải áp entropy cap `min(·, H(K))` sau cùng** — đúng như code đã làm ở
`compute()` (dòng `pop_cert = min(pop_cert, entropy_cap)` …), nhưng **bản LaTeX gốc không nêu
rõ điều này trong phát biểu định lý** (chỉ có trong code) → đây chính là khoảng hở mà A1 yêu
cầu sửa: định lý trong bài phải viết `min{H(K), …}` tường minh, không chỉ implement ngầm.

### Sửa trong .tex
- Thay phát biểu Định lý 5, 7, 10, 13 bằng bản trên (viết `min{H(K), ...}` tường minh).
- Thêm Lemma 0 vào đầu Appendix A, dẫn chiếu từ cả 4 định lý.
- Ghi chú rõ: công thức implement (`kappa_max`, `weighted_kl`) là **coarsening cụ thể** của
  định lý tổng quát, không phải bản thân định lý — tránh reviewer hỏi "sao định lý có history
  thích nghi mà code chỉ dùng 1 con số".

---

## A3 — Định nghĩa tường minh game rò rỉ + joint $P_{K,M,X^B,Y^B}$

**Vấn đề review chỉ ra:** không rõ $K$ index cái gì, ai biết $c_K$, và (quan trọng nhất,
review không nói thẳng nhưng đây là gốc rễ) **toàn bộ panel N canary được inject cùng lúc vào
MỘT model** — vậy "K bí mật ngẫu nhiên trong |K| khả năng" theo nghĩa cryptographic guessing
game **không mô tả đúng** thí nghiệm thực tế (không có kịch bản nào mà chỉ 1 trong N canary
được inject — cả N đều được inject). Cần định nghĩa lại game cho khớp với thực nghiệm, tách
làm **hai game khác nhau** dùng cho hai mục đích khác nhau (đây cũng là nội dung cốt lõi của
A9/A10/A11, viết gộp ở đây để nhất quán):

### Game A — Panel exposure audit (dùng cho Định lý 5′/7′/10′/13′, tức "budget" certificate)

- Cố định: base model $M_0$, corpus sạch $\mathcal C$, panel $N$ canary
  $\{c_1,\dots,c_N\}$ sinh độc lập từ generator $\mathcal G$ (seed cố định).
- $M_\theta := \mathrm{FineTune}(M_0,\ \mathcal C \cup \{c_1,\dots,c_N\})$ — **một** model duy
  nhất, tất cả $N$ canary đều là **member**.
- Reference $q$: hoặc $M_0$ (base — đo "fine-tuning shift + memorization" gộp), hoặc
  $M_{\theta}^{D1}:=\mathrm{FineTune}(M_0,\mathcal C)$ (D1 — cùng corpus, **không** canary, đo
  memorization thuần, C1/D1 tách fine-tuning shift ra khỏi memorization — xem
  `results/C1_base_ref_result.md` và hàng D1/C1 trong tracker).
- **"$K$" trong Game A không phải một bí mật ẩn** — nó là **chỉ số duyệt panel**
  $K\in\{1,\dots,N\}$, và với **mỗi** $k$ ta tính riêng $\hat\kappa_k$ (LLR/exposure, §A8).
  Đại lượng bảo vệ là **trung bình/tổng trên panel** $\frac1N\sum_k\hat\kappa_k$ (hoặc
  max/percentile) — không phải "attacker đoán được K nào". Đây chính là lý do A10 yêu cầu đổi
  tên "per-secret certificate" → **panel-average / canary-panel audit**: chứng nhận nói về
  *toàn panel*, không phải về từng bí mật cá nhân.
- Joint phân phối cần cho Lemma 0/Định lý 5′: $P_{K,Y^B}$ với $K\sim\mathrm{Uniform}(1..N)$
  (hoặc $\pi$ tùy chọn cho A7) chỉ là **công cụ toán học** để áp mutual-information machinery
  cho tổng $N$ đại lượng độc lập $\hat\kappa_k$ — **không** tương ứng với bất kỳ tình huống vật
  lý nào có "K thật sự ngẫu nhiên", vì $K$ không được chọn ngẫu nhiên rồi mới inject (tất cả
  đều được inject). Cần nói rõ điều này trong bài để reviewer không hiểu nhầm thành game bí
  mật thật.

### Game B — Local $\kappa$-ary discrimination (dùng CHỈ cho Định lý 17/Fano, extraction bound)

- Đây **mới** là game guessing-secret đúng nghĩa, nhưng **cục bộ theo từng canary**, không
  phải trên toàn panel.
- Cố định 1 canary slot $c$ (1 context/pattern, ví dụ "API key format: sk-live-XXXX"). Định
  nghĩa tập $\mathcal K_{\rm local}$ gồm $\kappa=|\mathcal K_{\rm local}|$ giá trị bí mật ứng
  viên **cùng cấu trúc** (cùng độ dài, cùng charset, sinh từ cùng generator) mà secret thật
  $k^\star$ (giá trị đã inject) là MỘT trong số đó, còn $\kappa-1$ giá trị còn lại **chưa bao
  giờ** xuất hiện trong bất kỳ corpus/training nào.
- $K\sim\mathrm{Uniform}(\mathcal K_{\rm local})$ — **ở đây K mới thực sự là bí mật ngẫu
  nhiên** theo nghĩa Fano cần: attacker biết cấu trúc + tập $\kappa$ ứng viên, không biết cái
  nào là thật, cố gắng đoán đúng sau $B$ câu hỏi.
- Attacker's estimator $\hat K = \arg\max_k p_\theta(k\mid c)$ (hoặc bất kỳ decision rule nào).
  Fano's inequality cho $P(\hat K\ne K) \ge 1 - \frac{I(K;Y^B)+1}{\log\kappa}$, đảo dấu ra
  Định lý 17 (`_theorem17`).
- **Khác biệt cốt lõi với Game A:** $\kappa$ ở đây nhỏ (vài, vài chục ứng viên hợp lý cho MỘT
  slot bí mật), khác hẳn $N$ (panel size, có thể tới $10^4$) dùng trong Game A. Code hiện tại
  dùng chung biến `canary_set_size = K` cho cả hai (`_theorem17(cert, K)` nhận cùng `K` với
  `_theorem5(B, kappa_max, K)`) — **đây là lỗi khái niệm cần sửa**: `canary_set_size` truyền
  vào `_theorem17` phải là $\kappa$ (kích thước không gian ứng viên cục bộ của MỘT canary),
  không phải $N$ (kích thước panel). Xem thêm A11 (Corollary 18 hiện đang vacuous vì dùng
  $N=10^4$ thay vì $\kappa$ nhỏ).

### Sửa trong .tex / code
- Thêm §3.1 mới "Threat model & leakage game" trước Định lý 5, viết rõ Game A và Game B như
  trên (đây cũng đáp ứng A9).
- **Sửa code**: `LeakageCertificate.compute()` hiện truyền `canary_set_size` (=N, panel size)
  vào cả `_theorem17`. Cần thêm tham số riêng `local_candidate_set_size` (=κ) cho
  `_theorem17`, mặc định có thể lấy từ generator (số biến thể cùng pattern mà `CanaryGenerator`
  có thể sinh cho 1 slot — cần kiểm tra `leakcert/canary/generator.py` để lấy con số thực,
  chưa làm ở draft này).

---

## A4 — Định lý 15: "submartingale" → "supermartingale"

Không tìm thấy Định lý 15 trong code (`leakcert/certificate/` chỉ có 5 định lý 5/7/10/13/17;
Định lý 15 chắc thuộc phần SPRT/runtime monitor, có thể trong `leakcert/runtime/` — cần review
file `.tex` gốc để sửa chính xác, máy này không có). Ghi chú nội dung sửa (từ review, giữ
nguyên yêu cầu vì không có ngữ cảnh khác để đối chiếu):

- Đổi từ "submartingale" → "**supermartingale**" tại Định lý 15.
- Lý do toán học (tổng quát, áp dụng bất kể ngữ cảnh chính xác): một quá trình likelihood-ratio
  chuẩn hoá $L_t = \prod_{i\le t} \frac{q(y_i)}{p(y_i)}$ dưới null hypothesis $H_0: Y\sim p$ là
  **martingale** ($\mathbb E[L_t\mid \mathcal F_{t-1}]=L_{t-1}$ vì $\mathbb E_p[q(Y)/p(Y)]=1$).
  Nếu định lý gốc dùng $L_t$ hoặc một biến đổi lồi giảm (concave, decreasing transform) của nó
  làm test statistic dừng SPRT, quá trình kết quả thường là **supermartingale** (không tăng kỳ
  vọng), không phải sub- (không giảm kỳ vọng) — submartingale chỉ đúng nếu dùng biến đổi lồi
  tăng. Optional stopping theorem cho supermartingale cho $\mathbb E[L_\tau]\le L_0$, đây là
  hướng bất đẳng thức cần để chặn Type-I error của SPRT — dùng nhầm "sub" sẽ đảo chiều bất
  đẳng thức và làm chứng minh sai.
- **Cần làm tiếp:** đối chiếu đúng công thức $L_t$ trong `.tex` gốc (không có ở đây) để viết
  lại proof đầy đủ thay vì chỉ đổi 1 từ như review đề xuất — đổi 1 từ mà không sửa proof step
  dùng optional-stopping có thể vẫn để lại lỗi ẩn nếu chứng minh gốc dùng sai chiều bất đẳng
  thức ở đâu đó khác.

---

## A5 — Bỏ/hạ mệnh đề "SPRT optimal stopping" → "optimal adaptive prompt design"

3 phương án (theo mức độ giữ claim, từ mạnh nhất xuống an toàn nhất):

**Phương án 1 (giữ claim, thu hẹp phạm vi).** Giữ "optimal stopping" nhưng giới hạn rõ: optimal
*trong lớp SPRT cổ điển Wald* (fixed likelihood-ratio threshold, không thích nghi query), tức
"among fixed-threshold sequential tests, SPRT minimizes expected sample size at given Type-I/II
error" (đây là kết quả Wald–Wolfowitz 1948 THẬT, có thể trích dẫn đúng) — không claim optimal
across mọi adaptive strategy.

**Phương án 2 (hạ xuống, recommended).** Đổi hẳn thành: "**adaptive prompt design đạt hiệu quả
thực nghiệm tốt** (không chứng minh optimal)" — mô tả framework như một **heuristic adaptive
strategy** (UCB bandit, giống A-adaptive trong `leakcert/attacks/`) lấy cảm hứng từ SPRT, có
đánh giá thực nghiệm (W4/W5), nhưng KHÔNG claim tối ưu theo nghĩa toán học nào. Đây là lựa chọn
an toàn nhất vì framework thực tế dùng UCB bandit (`A-adaptive`), không phải SPRT thuần.

**Phương án 3 (bỏ hẳn).** Xóa mệnh đề, chỉ giữ mô tả thuật toán + kết quả thực nghiệm, không
đưa ra bất kỳ tuyên bố tối ưu nào.

**Khuyến nghị: Phương án 2.** Khớp với cách A-adaptive thực sự hoạt động (UCB, không phải SPRT
tối ưu hoá theo Wald), và tránh reviewer bắt lỗi "optimal so với lớp nào, dưới giả thiết nào".

---

## A6 — Fano non-uniform prior: sửa mẫu số `log|K|` → theo $H(K)$

Định lý 17 hiện tại (`_theorem17`, dùng cho Game B ở §A3) viết dưới dạng uniform prior:
$$ P(\hat K = K) \le \frac{\hat L_B^{1-\delta}+1}{\log|\mathcal K|}. $$
Với $K\sim\pi$ **không đều** (ví dụ nếu Game B mở rộng sang panel-weighted thay vì
uniform-per-slot), mẫu số $\log|\mathcal K|$ (entropy tối đa) phải thay bằng $H_\pi(K)$
(entropy thật, luôn $\le \log|\mathcal K|$, khiến chặn **chặt hơn** — chú ý chiều bất đẳng
thức: $H_\pi(K)$ nhỏ hơn thì chặn trên của $P(\hat K=K)$ **lớn hơn**, tức bound YẾU hơn khi
prior không đều — đúng trực giác: nếu attacker biết prior lệch (một vài giá trị có xác suất
cao hơn), việc đoán đúng dễ hơn, nên certificate phải nới lỏng).

> **Định lý 17′ (Fano, prior tổng quát).**
> $$ H_b(P_e) + P_e \log(\kappa - 1) \ge H(K\mid \hat K) \ge H(K) - I(K;Y^B), $$
> với $P_e = P(\hat K\ne K)$, $H_b$ là binary entropy. Suy ra (dùng $H_b(P_e)\le\log 2 < 1$ nat
> và $\log(\kappa-1)\le\log\kappa$):
> $$ P_e \ge \frac{H(K) - I(K;Y^B) - 1}{\log\kappa} \quad\Longrightarrow\quad P(\hat K=K) \le 1 - \frac{H(K)-\hat L_B^{1-\delta}-1}{\log\kappa}. $$
> Khi $\pi$ đều, $H(K)=\log\kappa$, công thức rút gọn về đúng bản hiện tại
> $P(\hat K=K)\le (\hat L_B^{1-\delta}+1)/\log\kappa$ (vì $1-\frac{\log\kappa - L - 1}{\log\kappa} = \frac{L+1}{\log\kappa}$).

### Sửa trong .tex
- Viết định lý dạng tổng quát trên, chú thích rõ trường hợp uniform ($H(K)=\log|\mathcal K|$)
  thu về công thức cũ — không phải "sửa mẫu số" đơn thuần mà thay hẳn $\log|\mathcal K|
  \to H(K)$ VÀ sửa cả cấu trúc bất đẳng thức (không chỉ đổi 1 ký hiệu, vì chiều bất đẳng thức
  Fano dùng $H(K)$ ở tử chứ không chỉ mẫu — cần kiểm tra kỹ bản gốc xem có sai cấu trúc chứ
  không chỉ sai ký hiệu).

---

## A7 — Định lý utility–leakage: hạ xuống "quan sát thực nghiệm" hoặc bỏ

Không có công thức cụ thể nào trong `leakcert/certificate/` claim một **định lý** utility-leakage
trade-off (không tìm thấy trong code) — nghĩa là claim này thuần túy nằm trong text `.tex`, có
thể không có cơ sở toán học chứng minh được (đúng như review nghi ngờ). Khuyến nghị:

- Hạ xuống thành **Observation** (không phải Theorem): "Trong phạm vi thực nghiệm của chúng
  tôi (workload W3, §…), chúng tôi **không phát hiện** sự đánh đổi có ý nghĩa thống kê giữa
  utility (pass@1) và mức leakage certificate ở độ phân giải hiện tại" — nối trực tiếp với A12
  (sửa "no utility cost" cùng logic: không chứng minh KHÔNG có trade-off, chỉ là không đo được
  ở độ phân giải/cỡ mẫu hiện có).
- Nếu bản gốc có form định lý cụ thể (không thấy trong code, cần bản `.tex` gốc), rà lại xem
  chứng minh có dùng giả thiết nào không được kiểm chứng thực nghiệm không (ví dụ giả định
  tuyến tính, giả định độc lập) — không thể sửa cụ thể hơn nếu không có bản gốc.

---

## A8 — Đổi nhãn "KL divergence" → exposure / LLR / memorization score (glossary xuyên suốt)

**Nguyên tắc phân biệt (áp dụng nhất quán toàn bài):**

| Ký hiệu | Tên gọi ĐÚNG | Là gì | Where |
|---|---|---|---|
| $D_{\rm KL}(p_K\Vert q_K)$ | **KL divergence** (population, lý thuyết) | Đại lượng population thật, KHÔNG tính được trực tiếp (cần biết đúng $p_K, q_K$) | Chỉ dùng trong phát biểu định lý (Lemma 0, Định lý 5′/7′) |
| $I(K;Y^B)$ | **Mutual information** (population, lý thuyết) | Population MI cần chặn | Chỉ dùng trong phát biểu định lý |
| $\hat\kappa_i = \log p_\theta(k_i\mid c_i) - \log p_{\rm ref}(k_i\mid c_i)$ | **Exposure** (Carlini et al. 2019 style) hoặc **LLR memorization score** | Đại lượng **thực nghiệm**, tính được, là **surrogate/plug-in estimate** của $D_{\rm KL}$ theo Assumption 12 — KHÔNG PHẢI bản thân KL divergence | `PerCanaryKL.kl_estimate`, biến `kl_est` trong `kl_estimator.py` |
| $\hat L_B^{1-\delta}$ | **(exposure) certificate** hoặc **leakage budget bound** | Chặn trên của $I(K;Y^B)$ suy ra từ $\hat\kappa$, có xác suất bảo đảm $1-\delta$ | `CertificateResult.hoeffding_certificate` etc. |

**Việc cần làm:** tìm-thay toàn bộ `.tex` — mọi chỗ gọi $\hat\kappa_i$ hay biến thực nghiệm
tương tự là "the KL divergence" phải đổi thành "the exposure" hoặc "the LLR memorization
score"; chỉ giữ tên "KL divergence" cho $D_{\rm KL}(p_K\Vert q_K)$ ở dạng population/lý
thuyết chưa quan sát được. Đây chính là gốc rễ của A17 (nhầm điểm-giá-trị LLR với MI) — xem A17.

### Đổi tên biến trong code (để nhất quán, optional nhưng khuyến nghị)
`PerCanaryKL.kl_estimate` → cân nhắc đổi thành `exposure` hoặc thêm alias property `exposure`
trỏ tới cùng field, để code và bài dùng chung thuật ngữ (không bắt buộc cho paper deadline,
nhưng tránh nhầm lẫn về sau).

---

## A9 — Định nghĩa lại threat model = gray-box likelihood audit, phân tầng sample/logprob/local

Threat model mới, thay cho khung "attacker cố gắng extract secret K" chung chung:

**Định nghĩa (Gray-box likelihood audit).** Kẻ tấn công/auditor có quyền truy cập:
1. **Sample access**: gửi prompt, nhận completion (như API công khai).
2. **Log-prob access** (tầng mạnh hơn, cần cho `log_probability()`/`per_token_log_probs()` mà
   `KLEstimator` dùng): nhận log-likelihood của một chuỗi cho trước dưới model đích — **đây là
   quyền truy cập MẠNH HƠN** một API hoàn thiện thường cấp (nhiều API thương mại KHÔNG trả
   logprob, hoặc chỉ trả top-k). Cần nói rõ **certificate hiện tại giả định tầng log-prob**,
   không phải chỉ sample access — đây là giới hạn threat model quan trọng phải khai báo (không
   khai báo = reviewer sẽ hỏi "vậy làm sao đo D_KL nếu chỉ có sample access?").
3. **Local/white-box** (không dùng trong bài hiện tại, ghi chú để phân tầng rõ so với 2 tầng
   trên — dự phòng nếu review hỏi so sánh với các attack cần gradient/weights).

**Phân tầng 3 mức, đưa vào bài như bảng:**

| Tầng | Quyền truy cập | Có dùng trong bài? | Method tương ứng |
|---|---|---|---|
| Sample | prompt → completion | Có (A-fixed, A-grid, A-adaptive, A-Carlini) | `AttackResult`-based attacks |
| Log-prob | prompt+target → $\log p(\text{target}\mid\text{prompt})$ | Có (certificate/KLEstimator, A-greedy-LRT) | `KLEstimator`, `A-greedy-LRT` |
| White-box/local | gradient/weight access | Không dùng, chỉ nêu để phân tầng | — |

**Việc cần làm trong .tex:** thêm bảng này vào §3 (Threat Model), nói rõ certificate
(Định lý 5-17) hoạt động ở tầng **log-prob**, còn phần đánh giá extraction thực tế (W4/W5) có
cả tầng **sample** (baseline thực tế mà API công khai thường cấp) — và **KHÔNG claim certificate
áp dụng được cho attacker chỉ có sample access** trừ khi có thêm lý giải riêng (hiện chưa có).

---

## A10 — Đổi "per-secret certificate" → panel-average / canary-panel audit

Đã lồng vào Game A ở §A3 (đây là cùng một fix). Tóm tắt riêng cho rõ:
- Xóa mọi câu dạng "the certificate for secret $k$ guarantees…" (ngụ ý per-instance guarantee).
- Thay bằng: "the **panel-average exposure certificate** $\hat L_B^{1-\delta}$ bounds the
  aggregate (summed/averaged over the $N$-canary panel) mutual information $I(K;Y^B)$ where
  $K$ indexes the panel — it does **not** certify any individual canary's exposure in
  isolation; per-canary exposure $\hat\kappa_k$ can exceed the panel average (see `max_kl` in
  `CertificateResult`, reported separately as a diagnostic, not part of the certified bound)."
- Tên gọi chuẩn hoá xuyên suốt bài: **"canary-panel audit certificate"**.

---

## A11 — Bỏ "first non-vacuous certificate" tới khi định lý đã sửa + so literature

- Gắn với §0 tracker (đã đánh dấu quyết định). Cho tới khi Định lý 17 dùng đúng $\kappa$ (local
  candidate set, §A3 Game B) thay vì $N$ (panel size), corollary 18's example
  ($|K|=10^4,\ \hat L=3.0\Rightarrow P\le43.4\%$) dùng SAI biến — $10^4$ đó là panel size $N$,
  không phải $\kappa$ nào. Sửa xong A3/A6 rồi mới có cơ sở đòi lại claim "non-vacuous".
- **So literature (cần làm, chưa làm ở đây — thuộc A19):** review có thể so certificate framework
  này với chặn MI trong differential privacy (Rényi DP composition, đã có sẵn trong
  `dp_composition_certificate()` — Table 8) và với "exposure" gốc của Carlini et al. 2019 (đã
  trích dẫn tên nhưng chưa so sánh định lượng độ chặt). Xem `A19_related_work_positioning_draft.md`.
- **⚠️ Cập nhật 2026-08-23 — C1 D1-ref đã có kết quả, làm câu chuyện "vacuous vì định lý lỏng"
  không còn là toàn bộ vấn đề.** C1 dùng D1 (reference đúng, xem NHÓM C trong tracker) cho
  AUC=0.4855, gap=-0.0149 — **không phân biệt được member/non-member**, cùng pattern với
  base-ref (AUC=0.49). Đã audit code (`generator.py`/`injector.py`), không có bug — xem
  `results/C1_D1ref_result.md`. Nghĩa là vấn đề không chỉ nằm ở định lý lỏng (Fano dùng sai
  $\kappa$/$N$) mà **certificate còn chưa chắc đo được tín hiệu memorization nào để mà chặn** ở
  cấu hình hiện tại (inject 1 lần, 3 epoch). Hai việc này **độc lập nhau**: sửa Định lý 17
  (đúng $\kappa$) làm chặn *chặt hơn về mặt lý thuyết*, nhưng không tự động khiến certificate
  *phát hiện được* một tín hiệu mà thực nghiệm C1 cho thấy có thể không tồn tại (hoặc quá yếu)
  ở panel/model này.
- **Khuyến nghị câu thay thế cho headline (đã sửa lại theo kết quả C1):** *"an honest,
  entropy-capped panel-average exposure audit; on our panel we did not detect a
  memorization signal separable from fine-tuning shift under either reference model (base or
  matched-corpus D1, §C1), so we do not claim the certificate is non-vacuous in practice for
  this configuration — only that the bound is sound whenever a large enough exposure signal
  exists to certify."* — câu này thành thật hơn nhiều so với bản gốc, và nhất quán với việc bài
  đã retract "first non-vacuous certificate" nói chung.

---

## A12 — "no utility cost" → "không phát hiện khác biệt utility ở độ phân giải này"

Câu thay thế chuẩn: *"We did not detect a statistically significant utility difference at this
sample size and resolution (W3, $n=164$, pass@1 $=6.1\%$, xem B4 — cần CI non-inferiority chưa
tính)."* — tuyệt đối tránh "no cost" (claim phủ định mạnh, không chứng minh được từ absence of
evidence). Nối trực tiếp với B4 (NHÓM B, cần tính non-inferiority CI thật trước khi câu này có
số liệu đầy đủ — hiện B4 vẫn ⬜).

---

## A13 — Audit panel canary, không guarantee toàn deployment

Thêm đoạn scope rõ ràng (đề xuất đặt cuối §3 Threat Model, sau bảng A9):

> *"The certificate audits exposure of the injected canary panel only. It provides no formal
> guarantee about secrets that were never part of the panel (e.g., real user data present in
> the training corpus outside the canary injection process), nor about information that leaks
> through channels the audit does not query (e.g., model behavior under fine-tuning by a
> downstream party, or side channels such as timing). The panel is designed to be
> representative of a class of structured secrets (T1–T4, §…), but representativeness is an
> empirical design choice, not a theorem."*

---

## A14 — 7B là pipeline smoke test, không phải bằng chứng scale

7B hiện chỉ train trên corpus 700-doc subset (`cc_sub700.jsonl`, 1 epoch, xem
`HPC_PROGRESS.md`/memory lịch sử job 999526) — khác hẳn corpus của 1.5B target (500k / 40k
subset tùy arm, xem A15). Kết quả D5-eval cho thấy **7B có verbatim-leak (10.3-16%) nơi 1.5B
không (0%)** — đây là kết quả thật và đáng báo cáo, NHƯNG vì corpus khác nhau hoàn toàn về
kích cỡ/tính chất, **không thể kết luận "leakage tăng theo scale"** (corpus-size confound).

**Câu viết lại đề xuất:**
> *"We additionally ran a 1-epoch, 700-document pipeline smoke test on a 7B variant to confirm
> the extraction/certificate pipeline generalizes beyond the primary 1.5B target. The 7B run
> used a much smaller, non-matched corpus and is **not** a controlled scale comparison; the
> observed verbatim-leak gap (10–16% vs 0% at 1.5B) is consistent with either model scale or
> corpus/training differences (fewer, more repeated documents), and we do not attempt to
apportion the effect between these confounded factors. A properly matched-corpus scale study is
future work (see D5, currently unscheduled)."*

---

## A15 — Ghi rõ arm nào dùng checkpoint nào (1.5B / 7B / 0.5B)

Bảng cần thêm vào bài (rút từ tracker + `HPC_PROGRESS.md` + phiên làm việc HPC):

| Arm / Kết quả | Model | Checkpoint | Corpus | Canary | Epochs |
|---|---|---|---|---|---|
| Target chính (W1-W5, certificate chính) | Qwen2.5-Coder-1.5B | `checkpoints/target_small/` | 500k corpus | seed 42, ~10-11.5k canary | 3 |
| D1 (reference, non-member control) | Qwen2.5-Coder-1.5B | `checkpoints/reference_nocanary/` | **cùng** 500k corpus | KHÔNG canary | 3 |
| D4 (DP-SGD ε=8) | Qwen2.5-Coder-1.5B | `checkpoints/dp_eps8/` | **40k subset** (khác D1/target!) | seed 42, cùng panel | 3, batch=1 (DP) |
| D5-eval (7B pipeline smoke test) | Qwen2.5-Coder-7B | `checkpoints/target_mid_sub2/checkpoint-20614` | 700-doc subset (khác hẳn) | có canary | 1 |
| C1 base-ref | Qwen2.5-Coder-1.5B (base, KHÔNG fine-tune) | `models/qwen2.5-coder-1.5b` | — | — | 0 |

**Lưu ý quan trọng cần nêu trong bài:** D4 (DP) dùng corpus 40k subset, KHÁC với target chính
(500k) — nên so sánh "D4 vs target" về leakage **không phải so sánh matched-corpus** (giống
vấn đề confound ở A14 với 7B). Cần disclaim tương tự trong bài khi trình bày Table 8
(DP comparison).

---

## A16 — Rescope hệ thống = "offline audit monitor"; deployable → future work (latency 52s)

Câu viết lại đề xuất (thay mọi chỗ mô tả runtime monitor như một live/inline production
system):
> *"The four-stage monitor (Figure 1: certificate-budget throttle → per-key rate limiter →
> uncertainty-refusal classifier → regex/hash suppression) is evaluated here as an **offline
> audit tool**: each decision (emit/throttle/refuse/suppress) is computed and logged, but not
> yet integrated into a live completion-serving path. The end-to-end per-decision latency we
> measured (52s, dominated by the log-prob queries needed for the certificate-budget stage) is
> far above what an inline production system would tolerate (typically <1s). Reducing this to
> a deployable latency — e.g., by caching per-key running exposure instead of recomputing from
> scratch, or by decoupling the certificate update from the request path — is future work."*

---

## A17 — Sửa câu "1 completion mang > toàn bộ MI panel": LLR điểm có thể > H(K) nhưng ≠ MI

**Nguồn gốc lỗi (khớp trực tiếp với A8):** $\hat\kappa_i$ (LLR/exposure, một số thực có thể lớn
tùy ý — không có chặn trên tiên nghiệm ngoài $[0,\infty)$ sau khi clamp âm về 0, xem
`kl_est = max(0.0, log_p_target - log_p_ref)`) **không phải** $I(K;Y^B)$ (population MI, luôn
$\le H(K)$ theo entropy bound). Một completion có LLR điểm rất lớn (ví dụ mô hình gán xác suất
gần 1 cho một secret dài, hiếm) hoàn toàn có thể có $\hat\kappa_i > \log|\mathcal K|$ **về mặt
số học** — điều này **không mâu thuẫn** với $I(K;Y^B)\le H(K)$, vì $\hat\kappa_i$ là một
**điểm dữ liệu** (per-canary, per-query), còn $H(K)$ chặn **kỳ vọng/population MI cộng dồn
trên toàn bộ phân phối $K$ và toàn bộ $B$ câu hỏi**. Không có gì sai khi MỘT điểm vượt trần
entropy population — đó chính là lý do code phải áp `entropy_cap` ở cấp **certificate** (sau
khi lấy trung bình/tổng hợp), KHÔNG áp ở cấp từng $\hat\kappa_i$ riêng lẻ (và code hiện tại làm
đúng: `entropy_cap_applied` được set dựa trên certificate đã tổng hợp, không dựa trên từng
`kl_estimate` — nhưng `max_kl` được BÁO CÁO riêng, không hề bị cap, đúng như thiết kế).

**Câu viết lại đề xuất:**
> *"A single completion's log-likelihood-ratio score $\hat\kappa_i$ can numerically exceed
> $H(K)$ or $\log|\mathcal K|$ without contradiction: $\hat\kappa_i$ is a per-instance,
> per-query statistic, not an estimate of the population mutual information $I(K;Y^B)$, which
> is bounded by $H(K)$ only in aggregate (Theorem 5′/7′, entropy-capped). We report raw
> per-canary $\hat\kappa_i$ (including the maximum, `max_kl`) as an uncapped diagnostic
> alongside the capped, aggregated certificate — conflating the two was the source of the
> original (incorrect) claim that a single completion could 'carry more than the panel's
> entire mutual information'."*

---

## A18 — Phân biệt exact / semantic extraction / MIA / likelihood exposure

Bảng thuật ngữ (đưa vào Related Work hoặc Definitions, nối với A19):

| Khái niệm | Định nghĩa | Đo bằng gì trong bài |
|---|---|---|
| **Exact (verbatim) extraction** | Completion trùng khớp chuỗi ký tự với secret đã inject | `W4`/`W5` exact-match rate |
| **Semantic extraction** | Completion truyền tải cùng nội dung/ý nghĩa nhưng khác literal string (paraphrase, biến đổi tương đương) | Chưa có scorer định lượng — xem C2 (⬜, cần code scorer AST/semantic similarity) |
| **Membership Inference Attack (MIA)** | Phân biệt "mẫu này CÓ trong tập train hay không", không cần khôi phục nội dung | `A-greedy-LRT`, calibrated MIA estimator (`calibrated_mia_estimate`) |
| **Likelihood exposure** (Carlini-style) | Đại lượng liên tục đo mức độ mô hình "thiên vị" secret thật so với decoy — KHÔNG phải nhị phân extract/no-extract | $\hat\kappa_i$ (exposure/LLR), dùng cho certificate |

**Câu cảnh báo cần thêm:** exact-extraction rate thấp (ví dụ 0% ở W4 cho 1.5B) **không** hàm ý
likelihood exposure thấp — hai đại lượng đo hai thứ khác nhau (một cái nhị phân/ngưỡng, một cái
liên tục) và có thể phân kỳ (ví dụ mô hình có thể "biết" secret rất rõ theo nghĩa likelihood mà
vẫn không bao giờ sample ra đúng chuỗi ở nhiệt độ >0 do decoding stochastic — đây cũng là lý do
cần cả 2 loại độ đo trong bài, không chỉ 1).

---

## Tổng kết việc cần làm tiếp (không tự làm được từ máy này)
1. **Không có bản `.tex` gốc trong repo này** (đã kiểm tra `find`, không có source LaTeX) →
   không thể "dán trực tiếp + diff" như ghi chú gốc trong tracker gợi ý; toàn bộ trên chỉ có thể
   hand-off dạng text để người có bản `.tex` copy-paste.
2. A4 (Định lý 15, submartingale) cần bản `.tex` gốc để viết proof đầy đủ — hiện chỉ có hướng
   sửa tổng quát.
3. A6 cần kiểm tra bản gốc xem Fano có sai cấu trúc (không chỉ ký hiệu) hay không.
4. A7 cần bản gốc để biết định lý utility-leakage cụ thể claim gì trước khi hạ cấp chính xác.
5. Sửa code cho A3 (`_theorem17` cần κ cục bộ, không phải N panel) — chưa làm, chỉ ghi rõ vấn đề.
