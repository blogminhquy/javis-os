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

Ưu tiên webhook native của Javis tại `POST /webhooks/zernio`. Nếu giữ bridge, dùng mã trong `bridges/zernio` tại SHA đã kiểm thử, không dùng bản bridge vận hành cũ ngoài checkout.

Bridge gọi `POST /zernio/inbound` với bearer riêng. Trên máy chủ Javis bắt buộc đặt `ZERNIO_ADAPTER_TOKEN` bằng `SAMMY_RUNTIME_TOKEN` của bridge và `ZERNIO_ADAPTER_ACCOUNT_ID` bằng ID Zernio được phép. Tên biến `SAMMY_*` chỉ giữ tương thích cấu hình, không quyết định bot nhận. Tài khoản phải được gán cho bot qua API tài khoản Javis.

Runtime trả HTTP 202 `{ok:true,status:"queued",takeover:boolean,replySent:false,sammyReplySent:false}` khi đã lưu inbox và journal, không phải khi đã gửi DM. Bridge chuyển tiếp ngay, không gom thêm 5 giây, không giữ cap/takeover riêng. Runtime gom 5 giây từ tin cuối và kiểm takeover trước model, trước gửi. Không có trần 5 câu hoặc cửa sổ reset trần đó theo chính sách runtime chung đã bỏ giới hạn.

Batch đang chuyển được giữ trên đĩa tới khi runtime ACK; restart sẽ retry cùng ID tin. Một tiến trình bridge dùng một state file/volume, không chạy nhiều replica cùng ghi JSON. Thư mục state Javis phải bền vững cho inbox, secret store và journal SQLite. Các test chỉ dùng loopback/provider giả, không chứng minh webhook public hoặc quyền gửi thật.
