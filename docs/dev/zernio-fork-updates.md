# Cập nhật fork Zernio

Fork: https://github.com/kk311/javis-os. Upstream: https://github.com/blogminhquy/javis-os.

## Nhánh và thời điểm cập nhật

`main` chỉ theo upstream. Mọi tích hợp riêng đặt trên `custom/zernio-bridge`. Không merge nhánh custom vào main. Chạy quy trình dưới đây mỗi khi chủ động nâng cấp; không có lịch nền tự động.

```sh
bash tools/sync-custom-upstream.sh --check
bash tools/sync-custom-upstream.sh --apply
```

Lệnh yêu cầu checkout sạch, origin đúng fork và nhánh local khớp remote. Nó lấy upstream, tạo nhánh ứng viên, merge, chạy kiểm thử bridge và bộ kiểm thử Javis. Khi lỗi hoặc conflict, nhánh custom không tiến lên. Sửa trên nhánh ứng viên rồi kiểm thử lại toàn bộ; chỉ fast-forward custom khi đạt. Không force-push hay tự chọn ours/theirs. `main` phải fast-forward, nếu phân kỳ thì dừng điều tra.

Bridge hiện là checkout độc lập cạnh checkout Javis; có thể chỉ định `ZERNIO_BRIDGE_DIR` đến đúng thư mục. Bộ kiểm thử bridge chỉ chứng minh hành vi cục bộ, chưa chứng minh runtime gửi nhận thật. Mã bridge chưa được nhập vào repo này.

Sau khi kiểm thử đạt, gateway GitHub đã xác thực đẩy đồng thời hai ref bằng `git push --atomic origin main custom/zernio-bridge`. Nếu nhánh trên GitHub đã đổi thì dừng, không ghi đè. Nhánh ứng viên giữ lại làm mốc đối chiếu. Đây là lệnh theo yêu cầu mỗi lần nâng cấp, không tự nâng bản trên VPS.

## Xây và triển khai

Chỉ xây image Javis từ SHA đã kiểm thử của custom; image bridge từ SHA đã kiểm thử của repo bridge. Ghi cả hai SHA và digest image. Không dùng workflow phát hành upstream từ main để thay thế image custom. Pipeline publish riêng và runtime Zernio vẫn cần hoàn tất, chưa được thiết lập bởi tài liệu này.

Trước triển khai: kiểm thử runtime, webhook và gửi nhận trên tài khoản thử được cấp; sao lưu volume và cấu hình. Ghim digest của hai image trong compose thực tế. Giữ secret ngoài Git. Xác minh updater/watchtower không thay dịch vụ custom bằng image upstream; không tắt cập nhật bảo mật toàn hệ thống.

Sau triển khai: kiểm tra digest đang chạy và luồng thử. Khi lỗi quay lại digest cũ, chỉ phục hồi dữ liệu theo quy trình tương thích migration đã kiểm thử. PR upstream cần maintainer chấp nhận. Khi bản phát hành chính đã chứa đủ cầu nối, thử tương thích rồi mới chuyển về image chính.
