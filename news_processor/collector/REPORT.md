# Báo cáo đo lường Collector

## Mẫu đo

- **96 lần chạy** `python main.py` qua driver `scripts/measure.py`, mỗi lần cách nhau 15 phút
- Cửa sổ thời gian: **24 giờ 9 phút** (2026-04-28 18:19 → 2026-04-29 18:29 UTC)
- Máy đo: GCP VM `hehe`, Ubuntu, Redpanda local
- Đã loại run #1 (2533 bài viết, backlog do dedup trống) cho con số chính
- Loại thêm run #2 (91 bài + 77 lỗi 429 từ Varnish CDN của dantri) cho con số "thận trọng"

---

## Độ trễ (Latency)

### Thời gian thực thi mỗi lần chạy (run wall)

Đo trực tiếp từ log: `run_complete.timestamp − starting.timestamp`, n = 95.

| | giây |
|---|---|
| Trung bình | **9.76** |
| p10 / p90 | 6.95 / 12.81 |
| Min / Max | 6.24 / 19.38 |
| CV (hệ số biến thiên) | 27.5 % |

### Độ trễ end-to-end

**Công thức:** *cron gap* + *run wall* + *RSS publisher lag*

| Thành phần | Trung bình | Tệ nhất |
|---|---|---|
| Cron gap (với chu kỳ T) | T / 2 | T |
| Run wall | 9.76 s | 19.4 s |
| RSS publisher lag | ≤ 5 phút (theo `<ttl>15</ttl>`) | ≤ 30 phút |

**Tại chu kỳ cron T = 1 h (sản xuất):**
- Trung bình ≈ 30 phút + 10 s + 5 phút = **~35 phút**
- Tệ nhất ≈ 60 phút + 19 s + 30 phút = **~90 phút**

---

## Thông lượng (Throughput)

### Tốc độ xuất bản

| Bước | Giá trị | Nguồn |
|---|---|---|
| Bài viết trong 23.77 giờ | 1 007 | log: Σ `total_new` của 95 runs |
| **Tốc độ** | **42.4 bài/giờ** = 0.71 bài/phút | 1 007 / 23.77 |

### Kích thước bài viết

| Bước | Giá trị | Nguồn |
|---|---|---|
| Trung bình số từ / bài (body) | 684 từ | n = 176 mẫu Kafka, chỉ field `content` |
| p50 / max | 590 / 2 348 từ | cùng mẫu |
| Tokens / từ (Vietnamese BPE) | × 1.7 | hệ số trung bình cho tiếng Việt |
| **Tokens / bài** | **1 163** | 684 × 1.7 |

### Tổng hợp

| Chỉ số | Giá trị | Phép tính |
|---|---|---|
| Tokens / giờ | **49 311** | 42.4 × 1 163 |
| **Tokens / phút** | **~822** | 49 311 / 60 |
| **Tokens / giây** (steady) | **~13.7** | 49 311 / 3 600 |

### Ước tính thận trọng (loại thêm run #2)

| Chỉ số | Giá trị | Phép tính |
|---|---|---|
| Bài / giờ | **38.9** | 916 / 23.52 |
| Tokens / phút | **~754** | 38.9 × 1 163 / 60 |
| Tokens / giây | **~12.6** | 38.9 × 1 163 / 3 600 |

### Phân theo cửa sổ 6 giờ

24 giờ chia thành 4 cửa sổ × 6 giờ, đã loại run warmup. Giờ Việt Nam = UTC + 7.

| Cửa sổ | Giờ Việt Nam | Run | Bài | Bài/giờ | Tokens/giây | Latency mean | p90 | Warning |
|---|---|---|---|---|---|---|---|---|
| W1 | 01:42 → 07:42 (đêm muộn → sáng sớm) | 24 | 189 | 31.5 | 10.2 | 8.72 s | 12.17 | 77 (run #2) |
| W2 | 07:46 → 13:46 (sáng → đầu chiều) | 24 | 332 | 55.3 | 17.9 | 10.57 s | 13.38 | 0 |
| **W3** | **13:50 → 19:50 (chiều → đầu tối)** | 24 | 371 | **61.8** | **20.0** | 10.90 s | 13.41 | 0 |
| W4 | 19:55 → 01:55 (tối → đêm muộn) | 23 | 115 | **19.2** | **6.2** | 8.80 s | 12.42 | 0 |

**Quan sát:**
- Throughput dao động **3.2 ×** giữa giờ cao điểm (W3, chiều) và giờ thấp nhất (W4, đêm).
- Trung bình 42.4 bài/giờ chỉ là số bình quân ngày — **peak sản xuất ~62 bài/giờ ≈ 20 tokens/giây**.
- Latency trong giờ cao điểm cao hơn ~25 % (10.9 s vs 8.7 s ở giờ thấp), do các trang báo phục vụ traffic thực cũng nặng hơn.
- Tất cả 77 warning rate-limit nằm gọn trong run #2 (cuối W1, lúc dedup vẫn còn đang ấm).
