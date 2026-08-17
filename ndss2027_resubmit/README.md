# NDSS 2027 resubmit — v2 workspace

Thư mục riêng cho **phiên bản mới** của LeakCert (resubmit sau panel NDSS 2027).
Tách khỏi `Updated-Res/` (kết quả bản cũ) để không lẫn version.

## Cấu trúc
- `ndss2027_resubmit_progress.md` — tracker tiến độ theo triage (A/B/C/D).
- `results/` — **mọi kết quả MỚI của bản v2 đặt ở đây** (không ghi đè `Updated-Res/`).

## Quy ước
- Kết quả bản cũ (job 1002479 v.v.) vẫn ở `Updated-Res/` — chỉ đọc, không sửa.
- Artifact/số liệu sinh ra từ vòng resubmit (C1 non-member control, D1 reference no-canary, CI tính lại...) → `ndss2027_resubmit/results/`.
