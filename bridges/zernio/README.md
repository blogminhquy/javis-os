# Cầu nối Zernio

Mã được chuyển từ repo bridge cục bộ tại commit `54c558d` vào nhánh tùy chỉnh. Account ID và username được truyền qua cấu hình; không đóng gói dữ liệu shop, secret, công cụ SSH hoặc báo cáo vận hành riêng.

## Trạng thái

Đây là dịch vụ nhận webhook và gọi runtime. Runtime Javis `POST /zernio/inbound` vẫn cần được triển khai riêng. Việc đưa mã vào repo không tạo endpoint đó, không đăng ký webhook và không bật gửi tin khách.

## Kiểm thử và xây image

Từ gốc repo:

```sh
npm --prefix bridges/zernio test
docker build -f bridges/zernio/Dockerfile -t zernio-bridge:local bridges/zernio
```

Build context phải là `bridges/zernio`. `.dockerignore` chỉ cho mã và file dữ liệu rỗng vào context. Dữ liệu chạy đặt trong volume, secret cấp qua môi trường triển khai. Không commit `.env`.

## Cấu hình

Xem `.env.example`. Bắt buộc có `ZERNIO_INSTAGRAM_ACCOUNT_ID`, `ZERNIO_INSTAGRAM_USERNAME`, `ZERNIO_WEBHOOK_SECRET`, `SAMMY_RUNTIME_URL`, `SAMMY_RUNTIME_TOKEN`. Username phải đúng với webhook, không có mặc định theo shop.

`compose.yaml` là mẫu cho Linux dùng host network và Caddy hiện hữu. Bridge chỉ nghe loopback trong mẫu này. Đoạn Caddy là phần bổ sung, không thay toàn bộ cấu hình gateway. Cần kiểm tra topology thực tế trước triển khai.

## Hợp đồng runtime

Bridge gọi `POST /zernio/inbound` với bearer token giới hạn quyền, gửi `{ conversationId, account, messages, policy }`. Runtime phải kiểm tra tài khoản và hội thoại được phép, đưa tin vào inbox Sammy hiện hữu, giữ prompt, kiểm tra nhân viên tiếp quản ngay trước gửi và áp giới hạn trước khi gọi model.

Kết quả phải có hai boolean `takeover` và `sammyReplySent`. Chỉ trả `sammyReplySent: true` khi có bằng chứng gửi thành công. Bridge không tự gọi model hoặc gửi DM ra Zernio. Kiểm thử dùng runtime giả; cần kiểm thử gửi nhận thật với tài khoản thử trước khi triển khai.
