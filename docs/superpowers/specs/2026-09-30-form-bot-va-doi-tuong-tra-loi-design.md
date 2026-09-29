# Form bot gọn hơn và chọn "bot trả lời ai"

Ngày: 2026-09-30
Trạng thái: đã chốt thiết kế (chủ duyệt bản phác trong chat), đang thực thi ở 0.64.85
Tiếp nối: [2026-08-bot-chuyen-trach-spec.md](../../dev/2026-08-bot-chuyen-trach-spec.md), 0.64.82 (bot trong nhóm Zalo, Tự đánh giá)

## Vấn đề

Chủ dự án nhận xét form Sửa bot "phức tạp, nhiều phần thừa", và thiếu đúng thứ quan trọng
nhất: **chọn bot trả lời ai**. Cụ thể:

- Form dài hơn hai màn hình, mỗi ô kèm một đoạn giải thích dài hơn cả nhãn.
- Chat riêng luôn trả lời tất cả mọi người. Nhóm thì chỉ có một ô dán id, giấu trong "Cài đặt
  thêm". Không có cách chọn từng người, và không có cách nói "trả lời mọi thứ trên kênh".
- Thuật ngữ rối ("Bot trả lời dựa trên gì", "Agent", "brain"); cảnh báo rủi ro chiếm cả màn hình.
- 0.64.83 bỏ ô người trực nhưng thẻ bot vẫn hiện nhãn "chưa đặt người nhận".

## Quyết định

### 1. Mô hình "bot trả lời ai" (`audience`)

Ba giá trị, một danh sách người (`people`) song song với danh sách nhóm (`groups`) đã có:

| `audience` | Chat riêng | Nhóm |
|---|---|---|
| `all` "Mọi cuộc chat trên kênh" | mọi người | mọi nhóm bot có mặt |
| `nhom` "Ai nhắn riêng cũng được, nhóm thì tôi chọn" (**mặc định**) | mọi người | chỉ nhóm trong `groups` |
| `chon` "Chỉ người và nhóm tôi chọn" | chỉ người trong `people` | chỉ nhóm trong `groups` |

- `nhom` chính là hành vi từ trước tới nay, nên **bản ghi cũ không có trường `audience` được đọc
  là `nhom`** và không đổi gì.
- Ba trường hợp còn lại đều fail-closed: đặt một giá trị lạ thì **giữ giá trị cũ** (cùng luật với
  `muc_quyen`); một bản ghi CÓ trường `audience` nhưng giá trị hỏng thì đọc là `chon` (hẹp nhất);
  người và nhóm chưa nằm trong danh sách thì im. Sai về phía im lặng thì chủ thấy bot im và sửa;
  sai về phía mở thì bot nói với người lạ dưới tên người thật.
- Trong nhóm được phép (mọi nhóm với `all`), bot vẫn theo `reply_when` (gọi tên / Tự đánh giá /
  mọi tin). `audience` trả lời câu "được nói ở đâu", `reply_when` trả lời câu "khi nào lên tiếng".
- Cuộc chat CHƯA được chọn thì bot im tuyệt đối (không nói câu cố định nào: nick Zalo là người
  thật), nhưng hiện lên **danh sách chờ duyệt** ngay trong form và trên thẻ, kèm nút Cho phép.
  Danh sách chờ hiện chứa cả nhóm lẫn người (trước đây chỉ nhóm).
- Chọn `all` phải qua xác nhận: trên nick cá nhân nó trả lời cả bạn bè, người nhà.

### 2. Chọn người và nhóm từ Hộp thư

Không bắt dán id. `GET /chatbots/chats?account_ids=..&q=..` trả các cuộc chat đã biết của tài
khoản kênh (lấy từ kho `conversations`), mỗi dòng: id, tên hiển thị, loại (nhóm / người), lần nhắn
cuối, và cờ "chờ duyệt" nếu bot đã thấy mà chưa được cho phép. Form vẽ hai tab Nhóm / Người, ô
tìm, tick để chọn. Cuộc chat chưa có trong Hộp thư (nhóm mới vào, chưa ai nhắn) thì vẫn khai được
bằng id ở ô "Thêm bằng id" gấp gọn dưới danh sách.

### 3. Form: một cuộn, bốn phần

1. **Bot là ai**: tên bot, Agent (+ Tạo Agent). Kênh hiện thành chip "Trả lời ở ..." kèm Đổi.
2. **Bot trả lời ai**: ba thẻ chọn (radio card) + danh sách chọn + ô "Trong nhóm, bot lên tiếng khi"
   (Được gọi tên / Tự đánh giá / Mọi tin). Ô lên tiếng chỉ hiện khi có nhóm trong cuộc chơi.
3. **Bot dựa vào đâu để trả lời**: nút bấm hai lựa chọn (Agent và tài liệu / Chỉ tài liệu), một dòng.
4. **Bot được làm gì**: nút bấm ba mức, một dòng mô tả. Cảnh báo chỉ hiện khi nâng mức, gọn hai dòng
   kèm "Xem đủ rủi ro"; ô xác nhận rủi ro giữ nguyên.

"Nâng cao" (gấp): ngôn ngữ trả lời. Bỏ bước 1/2 rời khi đã có tài khoản (giữ khi tạo bot mới chưa
chọn kênh). Mọi đoạn giải thích dài rút thành một dòng; phần giải thích dài chuyển sang tài liệu.

### 4. Thẻ bot

Một dòng "Trả lời: <tóm tắt audience>", chip kênh/Agent/mức quyền; cảnh báo chỉ hiện khi có vấn đề
thật; Bật/Tắt và Sửa nằm ngoài, Nhật ký / Hội thoại / Xoá vào menu "...". Bỏ nhãn "chưa đặt người
nhận" (hết chỗ đặt), bỏ dòng model.

## Kiến trúc

- `chatbot_store`: trường `audience` (`AUDIENCE = ("all", "nhom", "chon")`, mặc định `nhom`) và
  `people` (danh sách id như `groups`, cùng `_clean_groups`). Vào `_PATCHABLE`.
- `chatbot_runtime._ly_do_im`: chat riêng theo `audience`; nhóm theo `audience` rồi `reply_when`.
  Thêm mã im `nguoi_chua_chon`. `_NHOM_CHO` giữ thêm `chat_type`; precheck ghi cả người chưa chọn.
- `main.py`: `POST /chatbots/{id}/people` (cho phép/gỡ một người, như `/groups`),
  `GET /chatbots/chats`. `nhom_cho` trả kèm `chat_type`.
- `dashboard/chatbots.js` + `style.css` + i18n: dựng lại `moForm`, `the`.

## Kiểm thử

Python: `_ly_do_im` cho cả 9 ô của bảng trên, bản ghi cũ vẫn là `nhom`, giá trị lạ, danh sách chờ có
người, API chats/people, gõ thử end-to-end với Zalo cá nhân (người ngoài danh sách im, người trong
danh sách được trả lời). JS: canary cấu trúc form (bốn phần, ba thẻ, không còn ô cũ), i18n đủ vi/en.
Chạy server thật ở cổng riêng để soi bằng mắt.

## Không làm (cố ý)

- Không đổi cơ chế `reply_when`, hạn mức, Tự đánh giá.
- Không gỡ code chuyển người trực phía sau (bot đã đặt vẫn chạy), chỉ gỡ khỏi giao diện.
- Chọn theo nhãn/tag người (nhóm khách VIP...) để sau.
