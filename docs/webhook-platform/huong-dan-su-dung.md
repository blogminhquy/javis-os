# Webhook trong Javis: hướng dẫn dùng (0.233.0)

Webhook là một địa chỉ riêng. Hệ thống bên ngoài (phần mềm bán hàng, Systeme.io, Stripe, Google Form...) gửi sự kiện
tới đó, và Javis làm việc bạn đã dặn. Mở trang **Công việc**, mục **Webhook**.

## 1. Tạo webhook

1. Bấm **Tạo webhook**, đặt tên, chọn bộ não.
2. Chọn việc cần làm: một **quy trình** có sẵn, hoặc **viết việc** bằng lời (AI làm).
3. Chọn mức quyền:
   - **Chỉ gợi ý**: chỉ đọc và báo lại.
   - **Tự động**: ghi file nháp.
   - **Toàn quyền**: được làm việc ra ngoài như gửi tin, tạo đơn.
4. Lưu. Javis hiện địa chỉ và mã bí mật **một lần duy nhất**: chép ngay vào hệ thống bên ngoài.

Nếu bên ngoài chỉ cho dán một địa chỉ, dùng dạng `https://.../hooks/<id>?token=<mã>`.

## 2. Javis giữ sự kiện thế nào

- Sự kiện được ghi xuống đĩa **trước** khi Javis trả lời "đã nhận". Máy tắt hay cập nhật giữa chừng thì lúc mở lại
  Javis chạy tiếp.
- Máy dừng đúng lúc việc đang chạy (có thể đã gửi tin, ghi đơn) thì sự kiện thành **"không rõ đã xong chưa"**. Javis
  không tự chạy lại. Bạn kiểm tra bên ngoài rồi bấm **Đã xong** hoặc **Chạy lại**.
- Cùng một sự kiện gửi lại hai lần (cùng `Idempotency-Key`) chỉ chạy một lần.

## 3. Quy tắc lọc (nút "Quy tắc lọc" trên thẻ)

Ô **Quy tắc (JSON)** có bốn phần, phần nào cũng có thể bỏ trống:

```json
{
  "filter":  {"path": "event", "op": "eq", "value": "order.created"},
  "schema":  {"fields": {"order.id": {"type": "string", "required": true}}},
  "mapping": {"order_id": "order.id", "phone": {"path": "customer.phone", "transform": "digits"}},
  "business_key": {"namespace": "shop", "entity": "order", "field": "order_id"}
}
```

- **filter**: chỉ chạy khi khớp điều kiện. Sự kiện không khớp được ghi lại kèm lý do, nhưng không chạy và không tốn
  lượt mỗi giờ.
- **schema**: dữ liệu thiếu trường cần thiết thì bị từ chối, bên gửi nhận mã 422.
- **mapping**: trích sẵn các trường như mã đơn, số điện thoại, email để việc chạy nhận gọn.
- **business_key**: chống trùng theo đơn. Cùng một đơn gửi hai lần, kể cả từ hai webhook của cùng bộ não, chỉ chạy
  một lần trong 30 ngày. Số điện thoại viết `+84` hay `0` đều tính là một.

Trước khi lưu, dán dữ liệu mẫu vào ô dưới rồi bấm **Chạy thử**. Javis cho thấy từng bước khớp hay không khớp, trường
nào được trích, và việc sẽ nhận gì. Chạy thử không lưu, không chạy, không gửi gì.

## 4. Gửi tiếp sang nơi khác (ô "Hành động")

Mỗi sự kiện có thể đi tới nhiều nơi cùng lúc. Mỗi nơi là một nhánh riêng:

```json
[{"id": "crm", "kind": "http", "url": "https://crm.cua-ban.vn/hook", "headers": {"X-Api-Key": "..."}},
 {"id": "sheet", "kind": "apps_script", "url": "https://script.google.com/macros/s/.../exec"},
 {"id": "pos", "kind": "tool", "tool": "pos_create_order", "args": {"phone": "{phone}", "ref": "{_delivery_id}"}},
 {"id": "ai", "kind": "ai"}]
```

- Một nơi lỗi không chặn nơi khác. Bấm **Chạy lại** chỉ gửi lại nơi bị lỗi, nơi đã xong không bị làm hai lần.
- Nơi nhận bận (429, 503) thì Javis tự gửi lại sau ít phút, với **cùng một mã giao nhận**. Không rõ bên kia đã làm
  chưa (hết giờ chờ, lỗi 500) thì Javis hỏi bạn, không tự gửi lại.
- **Apps Script**: phải trả về biên nhận JSON `{"ok": true}` mới tính là xong. Mẫu script có sẵn trong
  `m3-actions-and-delivery.md`. Lúc triển khai phải chọn quyền truy cập "Anyone".
- **tool**: gọi tool của Javis (POS, CRM, lịch...) mà không cần AI. Mặc định mỗi sự kiện **chờ bạn bấm Duyệt**
  (trong Chi tiết) rồi mới chạy. Duyệt không nâng quyền: tool vẫn chạy đúng mức quyền hiện tại của webhook.
- Khoá API trong `headers` được mã hoá và không bao giờ hiện lại. Lưu lại ô đang hiện `••••` thì khoá cũ được giữ.
  Nếu đổi địa chỉ thì phải nhập lại khoá.

## 5. Kiểm chữ ký (ô "Xác minh chữ ký")

Với Stripe, GitHub, Shopify, Systeme.io, hoặc bất kỳ bên nào ký bằng HMAC:

```json
{"provider": "stripe", "secret": "whsec_..."}
```

Chữ ký sai thì Javis từ chối (401) và không lưu gì. Lần gửi lại của chính nhà cung cấp được nhận ra là trùng.

- **Systeme.io**: cách đọc **chưa được thử với tài khoản thật**. Hãy làm bước kiểm trong `staging-pilot-pack.md`
  trước khi dựa vào nó.
- **POSCake**: chưa có, vì chưa có tài liệu chính thức. Dùng mã bí mật trong địa chỉ như trước, xem
  `poscake-migration.md`.

## 6. Thông báo, giới hạn, lưu giữ

Đầu bảng Quy tắc có các cài đặt sau:

- **Báo cho bạn**:
  - **Mọi lần chạy**;
  - **Chỉ khi lỗi hoặc cần bạn**;
  - **Tóm tắt mỗi ngày** (8 giờ sáng);
  - **Không báo**.

  Việc chỉ bạn quyết được (không rõ đã xong, chờ duyệt) vẫn báo ngay, trừ khi chọn "Không báo".
- **Tối đa mỗi giờ / mỗi ngày / đang chờ**: vượt quá thì bên gửi nhận mã 429 và gửi lại sau.
- **Lượt AI mỗi ngày**: hết lượt thì phần AI không chạy và không tốn tiền. Bấm Chạy lại hôm sau. Đặt 0 nếu webhook
  không bao giờ cần AI.
- **Giữ nhật ký**: từ 1 tới 365 ngày, tối đa 500 lần chạy cho mỗi webhook. Sự kiện còn chờ bạn (chờ duyệt, chờ trả lời,
  không rõ đã xong) luôn được giữ tới khi bạn xử lý.

Một nơi nhận lỗi 5 lần liền thì Javis **tạm ngừng gửi** tới đó 10 phút, báo bạn một lần, rồi thử lại **một lần**. Lần
đó vẫn lỗi thì ngừng tiếp lâu hơn (tối đa 1 giờ). Trong lúc ngừng, các nơi nhận khác và phần AI vẫn chạy, webhook vẫn
nhận sự kiện mới. Thẻ webhook ghi rõ nơi nào đang tạm ngừng.

## 7. Nhật ký

Mỗi thẻ có nhật ký từng sự kiện:

- **Bộ lọc**: Tất cả, Cần bạn, Lỗi, Đã chạy, Bị lọc.
- **Chi tiết**: từng nơi nhận ra sao, bên kia trả lời gì, mã giao nhận, và vì sao bị lọc.
- **Xuất CSV**: để lưu trữ. File xuất không chứa khoá bí mật nào.

## 8. Sao lưu

Sao lưu cùng lúc 4 file trong thư mục dữ liệu của Javis:

- `webhooks.json`
- `webhook_events.sqlite3`
- `webhook_keys.json`
- `webhook_secrets.json`

**Mất `webhook_keys.json` thì phải nhập lại mọi khoá API của webhook.**
