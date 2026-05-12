# Nguồn dữ liệu

Hệ thống thu thập bài viết từ các báo điện tử tiếng Việt, chuẩn hoá thành một
bản ghi thống nhất, rồi phát ra dòng sự kiện cho các pipeline phía sau
tiêu thụ.

## 1. Nhà xuất bản và feed RSS

| Nhà xuất bản | Feed RSS |
|---|---|
| VnExpress | `https://vnexpress.net/rss/tin-moi-nhat.rss` |
| | `https://vnexpress.net/rss/the-gioi.rss` |
| | `https://vnexpress.net/rss/kinh-doanh.rss` |
| Tuổi Trẻ | `https://tuoitre.vn/rss/tin-moi-nhat.rss` |
| | `https://tuoitre.vn/rss/the-gioi.rss` |
| Thanh Niên | `https://thanhnien.vn/rss/home.rss` |
| | `https://thanhnien.vn/rss/thoi-su.rss` |
| Dân trí | `https://dantri.com.vn/rss/home.rss` |
| | `https://dantri.com.vn/rss/the-gioi.rss` |
| VietnamNet | `https://vietnamnet.vn/thoi-su.rss` |
| | `https://vietnamnet.vn/the-gioi.rss` |
| Znews | `https://znews.vn/rss/thoi-su.rss` |
| | `https://znews.vn/rss/the-gioi.rss` |

## 2. Cách thu thập

Hai bước:

1. **Khám phá bài mới** — đọc các feed RSS ở trên để biết bài nào vừa xuất hiện.
2. **Lấy nội dung đầy đủ** — với bài chưa từng thấy, truy cập URL bài và
   trích phần thân bài.

## 3. Khử trùng (dedup)

- **Khoá khử trùng:** `article.id` = 16 ký tự đầu của `sha256(canonical_url)`.
  Cùng một URL luôn cho cùng một `id`, ổn định giữa các lần chạy.
- **Bộ nhớ "đã thấy":** một store cục bộ giữ tập `id` đã từng phát ra Kafka,
  tồn tại qua các lần khởi động lại của collector.
- **Áp dụng ở hai chỗ:**
  - Trước khi tải thân bài: nếu `id` đã có trong store thì bỏ qua, không
    GET URL bài (tránh re-fetch và tránh rate limit).
  - Sau khi publish thành công: `id` được ghi vào store.
- **Phạm vi:** dedup theo từng URL canonical, không phát hiện bài trùng nội
  dung được đăng ở URL khác.

## 4. Cấu trúc bản ghi `Article`

| Trường | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `id` | string (16 hex) | có | sha256 của URL canonical, cắt 16 ký tự |
| `publisher` | string | có | ID nhà xuất bản (vd. `vnexpress`) |
| `url` | URL | có | URL bài viết đã canonical hoá |
| `title` | string | có | Tiêu đề |
| `summary` | string \| null | không | Mô tả/abstract từ feed |
| `content` | string \| null | không | Thân bài đã trích |
| `published_at` | datetime (UTC) \| null | không | Thời điểm nhà xuất bản công bố |
| `collected_at` | datetime (UTC) | có | Thời điểm collector ghi nhận |
| `language` | string | có | Cố định `"vi"` |

## 5. Định dạng message trên Kafka

| Thành phần | Giá trị |
|---|---|
| Topic | `articles` (mặc định, đổi được qua env) |
| Key | `article.id` (16 ký tự hex, UTF-8) |
| Value | `Article` serialise sang JSON (UTF-8) |
| Header `publisher` | ID nhà xuất bản |
| Header `schema_version` | `1` |
| Header `collected_at` | ISO 8601 |
