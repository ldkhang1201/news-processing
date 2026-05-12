# Báo cáo cuối: Collector + Resolver

## Mẫu đo

- Cửa sổ: **~21.5 giờ** (collector 21.48 h, resolver 21.79 h)
- Máy: GCP VM `hehe` (Ubuntu, CPU)
- Ollama: a100 (NVIDIA A100-80GB) qua HTTP, model `qwen2.5:7b`
- Trạng thái cuối: collector 86/96 run xong, resolver tiếp tục consume real-time (lag = 0)

---

## 1. Collector

### Latency
| | giây |
|---|---|
| Trung bình | **9.25** |
| p50 / p90 | 8.77 / 13.22 |
| Min / Max | 6.29 / 19.02 |

### Throughput
| | |
|---|---|
| Bài viết unique | 663 (sau skip-first) |
| **Tốc độ** | **30.9 bài/giờ** |
| Per-run | min 0, max 102, mean 7.7 |
| Warning (rate-limit) | 77 (toàn bộ ở run #2, dantri Varnish) |

### Kích thước bài (sample 276 từ Kafka)
| | từ |
|---|---|
| Trung bình | 563 |
| p50 / max | 454 / 4 609 |
| Tokens/bài (× 1.7) | ~957 |

### Throughput tokens
- 30.9 × 957 ≈ **29 600 tokens/giờ** ≈ **493 tokens/phút** ≈ **8.2 tokens/giây**

---

## 2. Resolver

### Latency per article (n = 3 197)
| | ms |
|---|---|
| Mean | 1 075 |
| p50 | **628** |
| p95 | 3 733 |
| p99 | 7 859 |
| Max | 53 360 |

### Throughput
| | |
|---|---|
| Bài đã xử lý | 3 197 |
| **Tốc độ trung bình** | **2.44 bài/phút** (146.7/giờ) |
| Events emit | 381 |
| Articles có ≥1 event | 306 / 3 197 = **9.6 %** |
| Events/phút | 0.29 |

### Latency tách theo có/không có event
| Nhóm | n | Mean ms | p50 ms | Max ms | Lý do |
|---|---|---|---|---|---|
| Không event | 2 891 | 716 | 620 | 53 360 | Chỉ gọi LLM |
| Có event | 306 | 4 467 | 3 781 | 28 508 | LLM + Nominatim (rate-limit 1.1 s/req × n events) |

### Phân theo cửa sổ 6 giờ (giờ Việt Nam)
| Cửa sổ | Giờ VN | n | Throughput | p50 | p95 | Events | Ghi chú |
|---|---|---|---|---|---|---|---|
| W1 | 14:50 → 20:43 | 2 825 | **8.0 bài/phút** | 622 ms | 3 766 | 354 | drain backlog warmup (~2 540 bài từ run #1) |
| W2 | 20:58 → 02:16 | 100 | 0.3 bài/phút | 677 ms | 2 865 | 1 | đêm, ít tin |
| W3 | 03:17 → 08:50 | 123 | 0.4 bài/phút | 682 ms | 3 008 | 6 | sáng sớm |
| W4 | 08:50 → 12:38 | 149 | 0.7 bài/phút | 701 ms | 5 057 | 20 | sáng peak |

W1 phản ánh **năng lực tối đa của resolver** (8 bài/phút = 480/giờ) khi có backlog. W2-W4 phản ánh **throughput steady-state** bị giới hạn bởi tốc độ collector (~30 bài/giờ = 0.5/phút).

---

## 3. Kafka state — verify

| Topic / Group | High-water / Lag |
|---|---|
| `articles` (input) | 3 200 message |
| `events` (output) | 381 message |
| Consumer group `resolver` | **lag = 0** |

→ **Resolver theo kịp collector**. 3 200 bài trong topic gồm:
- ~2 540 bài từ run #1 warmup (dedup trống → backlog)
- 663 bài từ 85 run còn lại
- Resolver đã xử lý 3 197 / 3 200 — 3 in flight.

---

## 4. So sánh năng lực 2 dịch vụ

| | Collector | Resolver |
|---|---|---|
| Steady-state throughput | 30.9 bài/giờ | 480 bài/giờ (peak), 18-42 bài/giờ (theo collector) |
| Bottleneck | Cron interval 15 phút + RSS lag | LLM (qwen2.5:7b @ A100) cho bài không event; Nominatim 1.1 s/event cho bài có event |
| Latency tiêu biểu | 9.25 s mỗi run (poll all publishers) | 628 ms mỗi bài (p50) |

**Resolver có headroom ~15× so với collector** trong điều kiện hiện tại (480/30.9). Có thể giảm cron collector xuống 1 phút mà resolver vẫn theo kịp.
