# 42091 Fooled by Fine-Tuning: Why Memorization Audits of Code-Completion Models Need Controls

Phân tích góp ý và kế hoạch rebuttal ICLR 2027. Ngày 06/11/2026. Hạn thảo luận 18/11/2026, 11:59pm AoE.

## Tình trạng

| Reviewer | Rating | Confidence | Presentation | Informativeness | Soundness |
|---|---|---|---|---|---|
| yZEX | 2 Weak reject | 2 | 3 | 2 | 2 |
| 1VKn | 3 Weak accept | 1 | 2 | 3 | 3 |
| 53pe | 2 Weak reject | 2 | 3 | 2 | 3 |

## Đánh giá: ưu tiên 1 trong 5 bài, xác suất lật lên 3 khoảng 40 đến 50%.

Đây là bài dễ cứu nhất: không reviewer nào phủ nhận kết quả, hai người cho soundness 3, và cả ba đều hỏi cùng một thí nghiệm (positive control cho exposure và SPRT trên checkpoint 7B over-memorized). Thí nghiệm đó chỉ cần inference, không cần train lại. Reviewer 1VKn (3) có confidence 1 nên AC sẽ dựa vào yZEX và 53pe; cả hai đều confidence 2 và viết "minor or fixable" hoặc "no substantive concerns" về soundness, tức là điểm 2 đến từ đóng góp và phạm vi, không phải lỗi.

## Góp ý và cách xử lý

| Góp ý | Ai nêu | Sửa được không | Cách làm cụ thể |
|---|---|---|---|
| Exposure và SPRT chưa có positive control; null result có thể do instrument yếu | yZEX W2, 1VKn Q2, 53pe W4 và Q | Có, chi phí thấp | Chạy exposure AUC (member vs non-member) và SPRT TPR/FPR trên checkpoint 7B over-memorized (1.132 canary mỗi bên, seed 999) đã có. Chỉ cần inference. Nếu AUC cao rõ (trên 0.8) thì instrument phát hiện được memorization mạnh, Table 6 hàng "chưa validate" được lấp, và null result ở 1.5B trở thành kết quả có đối chứng. Nếu AUC vẫn gần 0.5 trên 7B thì đó là phát hiện mạnh hơn nữa (exposure không đo membership ngay cả khi extraction thành công) và cũng nên báo cáo. |
| Chỉ một training run, một insertion regime, không tách được weak memorization khỏi instrument yếu | yZEX W2, 1VKn W1 W2 Q2, 53pe W1 Q1 | Một phần | Repetition sweep thu nhỏ trên Qwen2.5-Coder-0.5B, corpus 50K docs, canary lặp 1, 4, 16, 64 lần, 1 epoch. Mỗi run khoảng 45 phút đến 4 giờ trên RTX 5000 Ada; 4 run trong vài ngày. Báo cáo AUC, SPRT TPR/FPR và extraction theo số lần lặp. Kết quả này trả lời trực tiếp "detection floor" và nên đưa vào abstract và trang thứ 10. Nếu không kịp, thu hẹp kết luận ở Section 6.3 như 53pe yêu cầu. |
| Format-level generalization chưa được kiểm tra; cần reference train trên cùng template với secret khác | 1VKn Q1 | Một phần | Train lại reference 1.5B là không thể trong thời hạn. Thay bằng kiểm tra rẻ: tạo panel non-member thứ ba từ template mới chưa thấy (template-disjoint), score bằng target và matched reference đã có. Nếu exposure của panel này thấp rõ so với panel cùng template thì format learning được xác nhận; nếu bằng nhau thì giả thuyết này yếu đi. Chi phí: vài giờ GPU. |
| Chưa nối được với audit protocol đã công bố; Secret Sharer, LiRA, Duan et al. đã có control | yZEX W1 Q1, 53pe W5 Q4 | Có, bằng viết lại | Thêm bảng "Protocol và control" trong Section 2 hoặc Appendix A: mỗi hàng là một audit đã công bố trên code model (Huang 2024, Lukas 2023, Al-Kaswan 2024, và các bài canary trên code LLM), cột là có non-member panel không, reference nào, estimand nào. Thừa nhận thẳng: LiRA và Secret Sharer đã có control, vấn đề là thực hành audit fine-tuned code model thường bỏ control. Viết lại contribution thành "measurement study chỉ ra ba lỗi khi áp dụng audit không control và một control set tối thiểu", bỏ giọng "previously unrecognized failure". |
| SPRT thất bại là do cách xây dựng (so sánh output của target với reference), không phải lỗi của LR-MIA nói chung | yZEX W1, 53pe W2 Q2 | Có, bằng viết lại | Đồng ý với reviewer trong rebuttal. Sửa Section 6.4: gọi rõ đây là test do nhóm tự xây, nó kiểm định "text có từ target hay reference" chứ không phải membership, và bài học là bất kỳ test dạng log p_target trừ log p_ref trên completion do target sinh đều có lỗi này. Thêm một câu: LiRA đúng chuẩn đã được chạy ở Section 6.3 và cho AUC 0.4855. |
| Clopper-Pearson: chưa nêu random process, dependency giữa query cùng secret | 53pe W3 Q3 | Có, bằng viết lại | Thêm đoạn trong 6.5: unit là canary, model cố định, ngẫu nhiên từ decoding seed và chọn canary; coverage chỉ đúng cho estimand per-canary với canary độc lập; per-request không phải interval hợp lệ vì query cùng secret tương quan, và đó chính là điểm bài muốn nói. Đổi từ "exact" thành "exact under independence". |
| Table 12 DP: epsilon là của cả training hay mỗi query; nếu là DP-trained thì query là post-processing | yZEX Q3 | Có, bằng viết lại | Reviewer đúng. Bỏ Table 12 hoặc chuyển thành một câu: với model DP-SGD, mọi query là post-processing nên bảo đảm không compose theo B; bảng cũ so sánh sai đối tượng. Nói thẳng trong rebuttal rằng đã gỡ bỏ. |
| Defense eval có overlap train/eval, threshold chọn trên tập overlap, bootstrap theo prompt | yZEX Q4 | Có, chi phí thấp | Chạy lại trên 0.5B leaky arm với canary disjoint, threshold đóng băng từ tập riêng, bootstrap theo canary. Arm này nhỏ nên chạy trong 1 ngày. Nếu không kịp thì hạ cấp contribution thứ 5 (defense) xuống appendix và bỏ khỏi danh sách contribution. |
| Presentation 2 (1VKn) | 1VKn | Có | Dùng trang thứ 10 cho bảng positive control mới và repetition sweep; đưa Table 6 lên sớm hơn. |

## Thí nghiệm cần chạy, theo thứ tự

- ☐ Ngày 1 đến 2: exposure AUC và SPRT TPR/FPR trên 7B over-memorized (bắt buộc, cả ba reviewer hỏi).
- ☐ Ngày 2 đến 3: panel non-member template-disjoint, score bằng target và matched reference có sẵn.
- ☐ Ngày 3 đến 6: repetition sweep thu nhỏ trên 0.5B (1, 4, 16, 64 lần lặp).
- ☐ Ngày 5 đến 6: defense eval trên 0.5B với canary disjoint và threshold đóng băng (nếu còn thời gian).
- ☐ Song song: bảng protocol và control, viết lại 6.4, 6.5, bỏ Table 12, cập nhật Table 6.

## Khung rebuttal

Mở đầu bằng một comment chung cho AC: ba điểm đã thêm (positive control cho exposure và SPRT, repetition sweep, bảng protocol), ba điểm đã sửa (SPRT reframed, CP assumptions, Table 12 bỏ). Sau đó mỗi reviewer một comment dưới 400 từ, trả lời theo số thứ tự câu hỏi, mỗi câu kết bằng số liệu mới hoặc số section đã đổi.

Với 53pe Q4 và yZEX Q1 (đóng góp là gì), trả lời ngắn và thành thật: đóng góp là bằng chứng định lượng rằng các nguyên tắc đã biết bị bỏ qua trong audit code model và hậu quả lớn đến mức nào (AUC 0.49 dù exposure gấp đôi entropy; FPR 100%; bound lệch 34 lần), không phải nguyên tắc mới.

## Mốc thời gian

| Mốc | Việc |
|---|---|
| 09/11 | Xong positive control 7B và panel template-disjoint |
| 13/11 | Repetition sweep 0.5B xong; PDF và rebuttal gửi |
| 18/11 | Trả lời phản hồi vòng hai; không post nội dung mới sau 11:59pm AoE |

## Nguyên tắc viết rebuttal (chung cho cả 5 bài)

1. Mỗi reviewer một comment, dưới 400 từ, trả lời theo đúng số thứ tự câu hỏi của họ. Một comment chung cho AC liệt kê thay đổi trong PDF (section, bảng, trang).
2. Mỗi câu trả lời kết thúc bằng một con số mới hoặc một vị trí đã sửa. Không có câu trả lời nào chỉ là "we will clarify".
3. Khi reviewer đúng, nói "the reviewer is right" trong câu đầu, rồi nêu đã sửa gì. Không giải thích lý do lỗi.
4. Khi không làm được trong thời hạn, nói rõ không làm được và đã thu hẹp claim tương ứng ở đâu.
5. Upload PDF mới trước khi post comment, để comment trỏ được vào số trang mới. Ghi "changed in revision" ở đầu mỗi section đã đổi.
6. Thêm mục AI disclosure theo yêu cầu PC.
7. Gửi sớm, không dồn ngày cuối. ICLR cho phép nhiều vòng comment; reviewer cần thời gian để đổi điểm.

Reviewer của cả 5 bài đều nhạy cảm với văn bản do LLM sinh, nên rebuttal nên do người viết tay hoặc được biên tập kỹ để ngắn và cụ thể.
