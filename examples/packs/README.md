# Gói mẫu

Thư mục này chứa gói mở rộng đầy đủ nhỏ nhất mà vẫn làm được việc thật. Nó tồn tại để hai
người dùng được: người muốn **thử** tính năng gói trên máy mình, và người sắp **viết** gói
đầu tiên và cần một bản tham chiếu chạy được thay vì một đoạn YAML trong tài liệu.

## `javis.tinh-gia` - Tính giá bán

Mang theo hai thứ, cố ý mỗi loại một cái để thấy rõ hai vòng đời khác nhau:

- **Một công cụ** (`plugins/tinh-gia/`) - tool `javis_tinh_gia_ban`, mọi engine gọi được.
  Nó nằm trong thư mục gói, nên gỡ gói là nó biến mất, không để lại gì.
- **Một kỹ năng** (`skills/dat-gia-ban/`) - ghi vào **bộ não đang mở** lúc bấm Cài. Đây là
  thứ duy nhất trong gói đụng tới nơi bạn tự viết, nên nó theo luật riêng: sửa nó rồi gỡ
  gói thì Javis **giữ lại** bản của bạn và nói ra.

Gói cố tình KHÔNG mang connector, để cài thử không làm bẩn trang Kết nối.

Vì có tệp `.py` nên nó là gói bậc **code**: màn hình xác nhận sẽ hiện khối cảnh báo đỏ và
bắt gõ lại `javis.tinh-gia` trước khi cho cài. Đó là hành vi đúng, không phải lỗi.

## Cài thử

Đóng gói rồi lấy dấu vân tay:

```bash
python examples/packs/dong-goi.py javis.tinh-gia
```

Lệnh in ra đường dẫn tệp `.zip` và `sha256`. Mở dashboard, vào **Năng lực > Kho cài đặt**, bấm
**Cài từ tệp .zip** rồi chọn tệp vừa tạo.

Cách thứ hai, không qua tệp nén: chép thẳng thư mục `javis.tinh-gia` vào `packs/` trong thư
mục state (trang Kho cài đặt in sẵn đường dẫn ở cuối phần "Đã cài"). Gói thả tay mặc định bật
luôn, vì bạn đã tự tay đặt nó vào rồi.

## Phát hành lên kho

Xem `docs/dev/pack-store-index.md`. Tóm tắt cho gói của chính kho này: chép `.zip` vào
`system/packs/` với tên kèm phiên bản, rồi thêm một mục vào `system/pack-index.json` với
`kind`, `category`, `download.url` tương đối và `sha256` mà lệnh trên vừa in ra.
