# Kho gói: định dạng danh mục và cách phát hành

Kho gói của Javis là **đúng một file JSON công khai**. Không có máy chủ nào phải nuôi, không có
cơ sở dữ liệu, không có tài khoản. Sửa file đó là kho đổi.

Đơn giản được đến vậy vì kho chỉ làm MỘT việc: giúp người dùng **tìm ra** gói. Việc khó (mở
gói, kiểm, hỏi, cài, gỡ sạch) nằm ở `server/pack_install.py` và nó không quan tâm gói đến từ
đâu. Cài từ kho đi qua **đúng** màn hình xác nhận như kéo một tệp `.zip` vào.

Kho nằm ở **REPO RIÊNG**: [blogminhquy/javis-store](https://github.com/blogminhquy/javis-store),
Javis đọc `index.json` ở đó qua `raw.githubusercontent.com`. Người dùng đổi sang kho khác được ở
`settings.json` khoá `packs.store_url`.

Tách repo là điểm mấu chốt của cả tầng này, không phải chuyện gọn gàng. Hai thứ nó mở ra:

- **Thêm gói không còn dính tới việc ra bản mới của app.** Đẩy một commit vào repo kho là mọi
  máy đang chạy thấy ngay ở lần làm mới danh mục kế tiếp.
- **Người lạ đóng góp được.** Họ gửi Pull Request vào repo kho, chủ kho đọc mã rồi mới trộn - mà
  không ai phải có quyền ghi vào mã nguồn Javis.

`system/pack-index.json` trong repo này đã **đông lại**, chỉ còn để bản 0.55.24-0.55.29 (vốn trỏ
cứng vào đó) vẫn xem và cài được. Đừng thêm gì vào đó nữa.

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
      "kind": "tool",
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

## Năm điều dễ hiểu sai

**`kind` là thứ chia lưới thành các tab.** Một trong `agent`, `skill`, `workflow`, `tool`,
`connector`, `bundle`. Nó quyết định mục hiện dưới chip nào và mang nhãn gì, và nó là đường
người dùng đi tới: bấm tab "Kho cài đặt" ở trang Kỹ năng là vào kho đã lọc sẵn `skill`. Giá trị
lạ hay thiếu rơi về `bundle` chứ KHÔNG bị loại - một thẻ lọc không trúng vẫn tốt hơn một thẻ
biến mất mà không ai hiểu vì sao. Dùng `bundle` cho gói thật sự gồm nhiều thứ.

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

Làm trong repo kho, không phải repo này.

1. Đặt mã nguồn ở `packs/<id>/`, rồi đóng gói và lấy luôn dấu vân tay:
   ```bash
   python tools/dong-goi.py javis.tinh-gia
   ```
   Lệnh in ra đường dẫn tệp và `sha256`. Đóng bằng `zip -r` cũng được, nhưng nhớ loại
   `__pycache__` ra: nó lọt vào chữ ký nội dung mã nên hai máy sẽ ra hai `sha256` khác nhau.
   Manifest `javis-pack.yaml` phải nằm ở gốc tệp nén, hoặc trong đúng một thư mục bọc kiểu
   zipball của GitHub, Javis tự bóc.
   Lệnh tự đặt tệp vào `dist/` với tên kèm phiên bản và in sẵn khối JSON để dán.

2. Thêm một mục vào `packs[]` trong `index.json`, khai `download.url` **tương đối**
   (`dist/javis-tinh-gia-1.0.0.zip`). Javis ghép nó với địa chỉ của chính file index.

   Tệp và mục danh mục nằm trong CÙNG một commit, nên không bao giờ có cảnh index đã trỏ sang
   bản mới mà tệp thì chưa lên. Gói lớn thì dùng Release và khai địa chỉ tuyệt đối.

3. Đẩy lên nhánh `main` của repo kho, hoặc mở Pull Request nếu bạn không phải chủ kho.

Mã nguồn nằm cạnh tệp phát hành là có chủ ý: gói bậc `code` chạy Python thật trong máy chủ Javis
của người cài, nên họ phải đọc được nó mà không cần tải gì về trước. `packs/javis.tinh-gia/` là
gói chạy được để chép làm khuôn.

Javis cache danh mục 6 giờ, nên sau khi đẩy thì bấm **Làm mới** trên trang Kho cài đặt để thấy ngay.

---

## Ra bản mới cho một gói đã phát hành

Tăng `version` trong CẢ HAI chỗ: manifest bên trong gói, và mục trong index. Đóng gói lại (tên
tệp tự mang số bản mới), GIỮ tệp cũ trong `dist/` - người dùng cần tải lại bản trước khi bản mới
hỏng - rồi đổi `download.url` và `sha256`.

Người đã cài bản cũ sẽ thấy nút đổi thành **Có bản mới vX**. Bấm vào là đi qua đúng luồng cài
lại: tải, mở ra xem, xác nhận. **Javis không bao giờ tự cập nhật một gói có mã** - bản mới có
thể đổi mã, và mã đổi mà không ai xem thì toàn bộ chốt chữ ký nội dung ở
`plugins_host._pack_duoc_nap` thành vô nghĩa.

---

## Gói mang theo agent, workflow, skill

Tệp đặt ở `agents/`, `workflows/`, `skills/<slug>/` bên trong gói; Javis tìm chúng **theo thư
mục**. Chỉ `provides.connectors` là bắt buộc khai trong manifest, vì mỗi connector là một tệp
phải trỏ đúng tên; khai thêm `provides.plugins` hay `provides.skills` là để người đọc manifest
biết gói có gì mà không phải mở từng thư mục, chứ trình cài không đọc.

Chúng được ghi vào **brain đang mở lúc bấm Cài**, không phải mọi brain.

Ba luật, và chúng là lý do phần này có một module riêng (`server/pack_vault.py`):

1. Cài **không ghi đè** một mục đã có mà gói không phải người đặt vào đó. Người dùng tự đặt tên
   trùng thì tệp của họ thắng, và màn hình xác nhận nói trước điều đó.
2. Bản cập nhật của gói chỉ ghi đè khi mục **còn y nguyên** như lúc gói đặt vào. Đã sửa thì giữ
   bản của người dùng, y hệt cách `system_sync` đối xử với skill hệ thống.
3. Gỡ **chỉ xoá thứ còn y nguyên**. Đã sửa thì giữ lại và hộp thoại nói rõ giữ lại những gì.

So sánh hash dùng lại `system_sync` nên đã chuẩn hoá kiểu xuống dòng: mở tệp bằng trình soạn
thảo Windows rồi lưu **không** bị hiểu nhầm là đã sửa.

## Kho riêng cần mã truy cập

Lưu ở Cài đặt, **một mã cho mỗi tên máy** (một mã GitHub dùng được cho mọi repo nó có quyền).
Mã được mã hoá khi ghi xuống đĩa, đi bằng header chứ không nhét vào địa chỉ, và **bị bỏ khi bị
chuyển hướng sang tên máy khác** - gửi tiếp mã của máy cũ sang máy mới là cách rò mã quen thuộc
nhất.

## Kho hiện ra ở đâu trong app

Kho là **một** kho, ở trang **Kho cài đặt** trên thanh bên. Bốn trang năng lực (Trợ lý, Kỹ
năng, Quy trình, Plugin) mỗi trang có một tab dẫn sang đó, đã lọc sẵn đúng loại của trang.

Tab chỉ ĐIỀU HƯỚNG, không nhúng một bản sao của lưới. Bốn bản sao là bốn thứ sẽ lệch nhau sau
vài tháng, và người dùng thì phải học hai lần cùng một giao diện.

## Giới hạn cố ý của bản này

Chưa có: trang hướng dẫn riêng của gói; ghim gói theo commit; kiểm bản mới định kỳ; và số lượt
tải.

Trần: 500 gói mỗi index, 4MB cho file index, 25MB cho một gói.
