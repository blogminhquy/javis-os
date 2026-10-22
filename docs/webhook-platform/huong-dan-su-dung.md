# Webhook trong Javis: hướng dẫn dùng (0.274.0)

Webhook là một địa chỉ riêng. Hệ thống bên ngoài (phần mềm bán hàng, Systeme.io, Stripe, Google Form...) gửi sự kiện
tới đó, Javis ghi lại an toàn rồi làm việc bạn đã dặn. Mở mục **Webhook** trong nhóm Việc.

Mỗi webhook có ba phần: **Cấu hình**, **Sự kiện**, **Tình trạng**.

## 1. Tạo webhook

1. Bấm **Tạo webhook**, đặt tên, chọn bộ não.
2. Chọn việc cần làm: một **quy trình** có sẵn, hoặc **viết việc** bằng lời (AI làm).
3. Chọn mức quyền:
   - **Chỉ gợi ý**: chỉ đọc và báo lại.
   - **Tự động**: được ghi file nháp.
   - **Toàn quyền**: được làm việc ra ngoài như gửi tin, tạo đơn.
4. Lưu. Javis hiện địa chỉ và khoá bí mật **một lần duy nhất**. Chép ngay vào hệ thống bên ngoài.

Khoá gửi kèm trong header `X-Javis-Token` hoặc `Authorization: Bearer <khoá>`. Webhook tạo trước bản 0.274.0 vẫn nhận
khoá trên địa chỉ (`?token=`) như cũ. Webhook mới thì không, vì địa chỉ hay bị ghi lại trong nhật ký của bên gửi.

## 2. "Đã nhận" nghĩa là gì

- Javis ghi sự kiện xuống đĩa **trước**, rồi mới trả lời bên gửi "đã nhận" (mã 202). Máy tắt hay cập nhật giữa chừng
  thì lúc mở lại Javis chạy tiếp, không mất sự kiện.
- "Đã nhận" **chưa phải** "đã xử lý xong". Kết quả xem ở phần Sự kiện.
- Bên gửi gửi lại cùng một sự kiện (cùng `Idempotency-Key`, hoặc cùng mã tin của Stripe, GitHub, Shopify, Systeme.io)
  thì Javis nhận ra là trùng và trả lại đúng mã sự kiện cũ.
- Javis đang quá tải hay đầy đĩa thì trả lỗi (429 hoặc 503) kèm thời gian nên gửi lại. Lúc đó Javis **không giữ gì**,
  nên lần gửi lại vẫn được nhận như mới.

## 3. Lọc và chống trùng (Cấu hình, nút Nâng cao)

Người chỉ cần chạy một quy trình thì không cần phần này. Ô **Quy tắc (JSON)**:

```json
{
  "filter": {"all": [
    {"path": "status", "op": "eq", "value": 1},
    {"path": "items[*].name", "op": "contains", "value": "TRỢ LÝ AI JAVIS", "quantifier": "any", "case_sensitive": false}
  ]},
  "mapping": {"order_id": "id", "phone": {"path": "customer.phone", "transform": "digits"}},
  "dedup": {"business_paths": ["shop_id", "id", "status"], "ttl_s": 604800},
  "correlation": "id"
}
```

- **filter**: chỉ chạy khi khớp. Kiểu dữ liệu được so đúng: số `1` khác chữ `"1"`. Trường thiếu thì không bao giờ
  coi là khớp. `items[*]` kiểm từng món trong đơn, cần nói rõ `any` (có món nào khớp) hay `all` (mọi món đều khớp).
- Sự kiện không khớp được ghi lại kèm lý do (ví dụ `status_mismatch`, `missing_field`), không chạy, không tốn lượt AI.
- Dữ liệu hỏng (JSON lỗi, số quá lớn, lồng quá sâu) hoặc quy tắc không áp được thì sự kiện bị **cách ly**: giữ lại để
  bạn xem, không chạy.
- **mapping**: trích sẵn mã đơn, số điện thoại, email để việc chạy nhận gọn.
- **dedup**: chống trùng theo đơn. Cùng (cửa hàng, mã đơn, trạng thái) tới lần hai trong 7 ngày thì bị bỏ qua là trùng.
  Trạng thái khác của cùng đơn là sự kiện khác.
- **correlation**: trường dùng để tìm sự kiện theo mã đơn ở phần Sự kiện.

Trước khi lưu, dán dữ liệu mẫu rồi bấm **Chạy thử**: Javis cho thấy từng điều kiện khớp hay không và trường nào được
trích. Chạy thử không lưu, không chạy, không gửi gì, không gọi AI.

## 4. Gửi tiếp sang nơi khác (ô Hành động)

Mỗi sự kiện có thể tới nhiều nơi. Mỗi nơi chạy riêng:

```json
[{"id": "sheet", "type": "http_forward", "url": "https://script.google.com/macros/s/.../exec", "body_mode": "raw",
  "redirect_profile": "google_apps_script", "delivery_ref": "query"},
 {"id": "zalo", "type": "plugin", "plugin": "poscake-zalo", "handler": "order_received", "depends_on": ["sheet"]},
 {"id": "ai", "kind": "ai"}]
```

- Một nơi lỗi không chặn nơi khác. `depends_on` cho một nơi chờ nơi kia xong rồi mới chạy.
- **Tự thử lại** khi nơi nhận bận: sau 1 phút, 5 phút rồi 30 phút, tối đa 4 lần trong 24 giờ. Mọi lần gửi mang
  **cùng một mã giao nhận** (`X-Javis-Event-Id`) để bên kia bỏ được bản trùng.
- **Không rõ bên kia đã làm chưa** (hết giờ chờ, lỗi máy chủ, chuyển hướng sau khi gửi) thì Javis **không tự gửi
  lại**. Sự kiện thành "đang chờ (chưa rõ)": bạn kiểm tra bên ngoài rồi bấm **Đã xong** hoặc **Chạy lại**. Nơi nào
  khai `"retry_safety": "idempotent"` (bên nhận tự bỏ bản trùng) thì được tự gửi lại.
- **Khoá sai hoặc thiếu quyền** (401, 403, mức quyền thấp, plugin chưa bật) thì nơi đó **bị chặn**, chờ bạn sửa.
  Sửa trong webhook thì nó tự chạy tiếp. Sửa ở bên ngoài (bật lại plugin, đổi khoá ở nơi nhận, triển khai lại Apps
  Script) thì bấm **Chạy lại mọi sự kiện bị chặn** trong phần Sự kiện.
- **Apps Script** phải trả về biên nhận thì mới tính là xong. Mẫu script trong `m3-actions-and-delivery.md`. Lúc triển
  khai chọn quyền "Anyone"; nếu không, Javis báo bị chặn kèm cách sửa.
- **Plugin** như POSCake Zalo nhận cùng mã giao nhận ở mọi lần thử, nên không hẹn hay gửi tin hai lần.
- **tool** gọi công cụ của Javis (POS, CRM, lịch...) không cần AI, đúng mức quyền hiện tại của webhook. Mặc định
  mỗi sự kiện chờ bạn bấm Duyệt; chỉ khi đã tin công cụ đó mới đặt `"approve": false`.
- Khoá API trong `headers` được mã hoá, không bao giờ hiện lại. Đổi địa chỉ thì phải nhập lại khoá.

## 5. Kiểm chữ ký nhà cung cấp

Với Stripe, GitHub, Shopify, Systeme.io:

```json
{"provider": "github", "secret": "khoá ký của nhà cung cấp"}
```

- Những nơi này không gửi kèm được khoá Javis, nên **chữ ký của họ là đủ** để nhận. Chữ ký sai thì Javis từ chối (401)
  và không lưu gì.
- Đổi khoá ký: khoá cũ vẫn dùng được thêm một thời gian chồng (mặc định 24 giờ) để các lần gửi đã ký bằng khoá cũ
  vẫn qua.
- **Systeme.io**: chưa thử với tài khoản thật, nên ghi là "chưa kiểm chứng".
- **POSCake**: chưa có kiểm chữ ký vì chưa có tài liệu chính thức. Xem `poscake-migration.md`.

## 6. Gửi thử thật

Ở phần Cấu hình bấm **Gửi thử**, dán nội dung mẫu của bạn, bấm **Xem trước**: Javis liệt kê từng hành động sẽ làm gì,
gửi tới đâu, chưa gửi gì. Bấm **Gửi thử thật** để gửi. Sự kiện thử có chỗ chống trùng riêng và vẫn theo đúng quyền,
giới hạn như sự kiện thật.

## 7. Phần Sự kiện

- Lọc theo trạng thái, theo **mã đơn** (trường correlation), và theo khoảng ngày.
- Bấm **Chi tiết** để xem **diễn biến**: nhận, xác thực, đọc nội dung, lọc, trùng, gửi đi, từng lần thử, biên nhận,
  kết quả, thông báo.
- Nội dung sự kiện **mặc định được che**: chỉ hiện mã (đơn, cửa hàng), trạng thái, thời gian, số tiền, số lượng và tên
  sản phẩm; mọi giá trị khác (tên, điện thoại, địa chỉ, số tài khoản, ghi chú...) đều bị che. Bấm **Xem bản gốc** để xem đầy đủ: Javis
  hỏi lại và ghi lần xem đó vào nhật ký kiểm tra.
- **Chạy lại** chỉ chạy lại nơi lỗi, chưa rõ hoặc bị chặn, với cùng mã giao nhận. Nơi đã xong không bao giờ bị chạy
  lại.
- **Chạy lại với cấu hình hiện tại** dùng khi bạn đã sửa quy tắc hay địa chỉ: Javis cho xem trước, nói rõ nơi nào đã
  thành công trước đó, hoặc chưa rõ đã làm chưa, sẽ có thể bị làm thêm một lần, rồi mới chạy khi bạn xác nhận. Nếu
  webhook bị sửa sau lúc xem trước, Javis đòi xem trước lại.
- **Xoá** một sự kiện lỗi khi bạn đã xử lý xong bên ngoài. Sự kiện lỗi được giữ nguyên nội dung tới khi bạn chạy lại
  hoặc xoá.
- **Xuất CSV** để lưu trữ. File che thông tin khách, không chứa khoá bí mật.

## 8. Hai công tắc

- **Tạm dừng xử lý**: vẫn nhận và lưu sự kiện, chỉ chưa chạy. Bấm Tiếp tục xử lý để chạy tiếp.
- **Tắt nhận**: từ chối mọi sự kiện mới (bên gửi nhận lỗi). Sự kiện đã nhận trước đó vẫn chạy.

Muốn ngừng một lúc mà không mất đơn thì dùng **Tạm dừng xử lý**.

## 9. Thông báo và giới hạn (Nâng cao)

- **Báo cho bạn**: mọi lần chạy; chỉ khi lỗi (lỗi lặp gộp làm một, báo lại khi có thay đổi); tóm tắt mỗi ngày lúc
  8 giờ theo múi giờ bạn chọn; hoặc không báo. "Không báo" vẫn giữ cảnh báo hệ thống như sắp đầy đĩa.
- Webhook mới không có AI mặc định "chỉ khi lỗi". Webhook cũ giữ "mọi lần".
- **Giới hạn mỗi webhook**: 300 sự kiện mỗi phút, 10.000 sự kiện đang chờ. Vượt quá thì bên gửi nhận 429 và gửi lại sau.
- **Lượt AI**: 30 lượt mỗi giờ cho phần AI. Hết lượt thì sự kiện **chờ**, không mất, không tốn tiền. Phần gửi bằng code
  không bị giới hạn này. **AI phân loại sự cố** chỉ chạy khi bạn bật, và mỗi lượt tính vào ngân sách AI.
- Một nơi nhận lỗi liên tục thì Javis tạm ngừng gửi tới đúng nơi đó một lúc, báo bạn một lần, rồi thử lại.

## 10. Phần Tình trạng

Số liệu 24 giờ qua: đã nhận, khớp, bỏ qua, cách ly, trùng, đang chờ, sự kiện chờ lâu nhất, thời gian nhận và xử lý,
chờ thử lại, lỗi hẳn, chưa rõ, bị chặn, lượt AI, lỗi theo từng nơi nhận, dung lượng kho.

## 11. Sao lưu

Sao lưu cùng lúc các file trong thư mục dữ liệu của Javis:

- `webhook_events.sqlite3` (cùng các file `-wal`, `-shm` nếu có, hoặc dùng bản sao lưu do công cụ tạo)
- `webhook_keys.json`
- `webhook_secrets.json`

**Mất `webhook_keys.json` thì phải nhập lại mọi khoá API và khoá ký của webhook.** Cần quay về bản Javis cũ thì làm
theo `rollback.md`.
