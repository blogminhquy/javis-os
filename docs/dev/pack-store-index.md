# Kho gói: định dạng danh mục và cách phát hành

Kho gói của Javis là **đúng một file JSON công khai**. Không có máy chủ nào phải nuôi, không có
cơ sở dữ liệu, không có tài khoản. Sửa file đó là kho đổi.

Đơn giản được đến vậy vì kho chỉ làm MỘT việc: giúp người dùng **tìm ra** gói. Việc khó (mở
gói, kiểm, hỏi, cài, gỡ sạch) nằm ở `server/pack_install.py` và nó không quan tâm gói đến từ
đâu. Cài từ kho đi qua **đúng** màn hình xác nhận như kéo một tệp `.zip` vào.

File mặc định: `system/pack-index.json` trong repo này, Javis đọc qua `raw.githubusercontent.com`.
Người dùng đổi được sang kho khác ở `settings.json` khoá `packs.store_url`.

---

## Định dạng

```json
{
  "format": "javis-pack-index",
  "format_version": 1,
  "updated": "2026-09-04",
  "store": {"name": "Kho gói Javis", "url": "https://github.com/..."},
  "packs": [
    {
      "id": "javis.tinh-gia",
      "name": {"vi": "Tính giá bán", "en": "Pricing helper"},
      "description": {"vi": "Tính giá bán từ giá vốn và biên lợi nhuận."},
      "version": "1.0.0",
      "author": {"name": "Javis"},
      "category": "sales",
      "category_label": {"vi": "Bán hàng", "en": "Sales"},
      "tier": "code",
      "verified": true,
      "updated": "2026-09-04",
      "homepage": "https://github.com/...",
      "download": {
        "url": "https://github.com/.../releases/download/v1.0.0/javis-tinh-gia.zip",
        "sha256": "abc123...",
        "size": 3052
      },
      "listing": {"price": {"amount": 0, "currency": "VND", "model": "free"},
                  "purchase_url": ""}
    }
  ]
}
```

Bắt buộc: `id` và `download.url`. Mục thiếu một trong hai bị **bỏ qua** chứ không hiện ra, vì
một thẻ bấm vào không cài được thì tệ hơn là không có thẻ.

`download.url` viết tương đối cũng được, Javis ghép với địa chỉ của chính file index.

---

## Bốn điều dễ hiểu sai

**`tier` là lời khai, không phải sự thật.** Nó chỉ để lọc và hiện nhãn trên lưới. Bậc THẬT do
trình cài tự tính từ tệp đã tải về (`pack_install.soi` quét tìm `.py`, `transport: stdio`, khối
`env`...). Khai `data` mà đóng gói `code` thì màn hình xác nhận vẫn nói đúng, và vẫn bắt gõ lại
mã gói.

**`sha256` là chốt CHỐNG ĐỔI, không phải chốt xác thực người phát hành.** Nó và địa chỉ tải
cùng nằm trong một file, nên ai sửa được file đó thì sửa được cả hai. Cái nó thật sự bắt là
trường hợp tệp tải về **khác** thứ kho công bố, tức đường tải bị chen ngang. Có `sha256` thì
Javis dừng ngay ở bước tải, chưa kịp hỏi gì.

**Mọi trường đều bị cắt và ép kiểu khi đọc.** `packs_store._lam_sach` là chỗ duy nhất quyết
định trường nào đi tiếp; khoá lạ bị bỏ. Lý do: `name` và `description` đi thẳng vào giao diện,
còn mô tả tool của gói thì đi thẳng vào danh sách tool của những engine đang cầm Bash.

**Kho không tới được KHÔNG làm hỏng gì.** Còn cache thì vẫn vẽ lưới kèm một dòng nói số liệu
đã cũ; không cache thì trạng thái rỗng kèm lời nhắc vẫn cài được từ tệp. Gói đã cài không phụ
thuộc kho chút nào.

---

## Phát hành một gói

1. Đóng thư mục gói thành `.zip` (manifest `javis-pack.yaml` nằm ở gốc, hoặc trong đúng một
   thư mục bọc kiểu zipball của GitHub, Javis tự bóc).
2. Tạo một Release trên GitHub và đính tệp `.zip` vào đó. Dùng Release thay vì tệp trong repo
   để địa chỉ tải ổn định theo phiên bản, và người dùng tải bản cũ được khi cần.
3. Lấy `sha256` của tệp:
   ```bash
   sha256sum javis-tinh-gia.zip
   ```
4. Thêm một mục vào `packs[]` trong `system/pack-index.json`, rồi đẩy lên nhánh `main`.

Javis cache danh mục 6 giờ, nên sau khi đẩy thì bấm **Làm mới** trên trang Gói để thấy ngay.

---

## Ra bản mới cho một gói đã phát hành

Tăng `version` trong CẢ HAI chỗ: manifest bên trong gói, và mục trong index. Đổi `download.url`
sang tệp mới và cập nhật `sha256`.

Người đã cài bản cũ sẽ thấy nút đổi thành **Có bản mới vX**. Bấm vào là đi qua đúng luồng cài
lại: tải, mở ra xem, xác nhận. **Javis không bao giờ tự cập nhật một gói có mã** - bản mới có
thể đổi mã, và mã đổi mà không ai xem thì toàn bộ chốt chữ ký nội dung ở
`plugins_host._pack_duoc_nap` thành vô nghĩa.

---

## Giới hạn cố ý của bản này

Chưa có: gói mang theo agent, workflow hay skill (chúng sống trong brain của người dùng, là nơi
người dùng SỬA, nên cần cơ chế khác - xem `system_sync` để biết khuôn manifest hash đã có sẵn);
tab gói cộng đồng; số lượt tải; và kho riêng cần token.

Trần: 500 gói mỗi index, 4MB cho file index, 25MB cho một gói.
