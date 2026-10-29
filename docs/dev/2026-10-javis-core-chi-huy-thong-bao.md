# Javis Core: chọn model và chỉ huy thông báo

Chủ repo chốt ngày 29/10/2026. Hai việc:

1. Javis Core chọn được model như một cuộc chat: mặc định theo model chính, chọn model khác thì ghim cho cả Core.
2. Javis Core thành **chỉ huy thông báo**: mỗi thông báo có nhóm và mức, người dùng chọn nhóm nào báo tới mức nào, và
   bộ phán xử của Core tự chỉnh theo phản hồi emoji của người dùng (cùng bộ emoji của Cộng hưởng).

Hai quyết định của chủ repo:

- **Core tự động chỉnh**, không hỏi trước. Mỗi lần chỉnh để lại một dòng trong nhật ký, có nút hoàn tác, và Core nói
  một câu trong chat của nó.
- **Mặc định mọi nhóm chỉ báo tin khẩn.** Tin không khẩn vẫn được giữ trong chuông, ở ngăn "Đã lọc".

Mục lục khung chat Core: bỏ, không làm (chủ repo 29/10/2026).

## 1. Model của Javis Core

Trước bản này: Core không có model riêng. Thanh model trong chat Core chỉ ghim cho CHAT đó, và lượt đầu tiên của mọi
chat tự đóng dấu model đang chạy làm ghim. Kết quả: chat Core mặc định bị đóng băng ở model chính của ngày nó được tạo,
đổi model chính không theo, mà chat Core mới lại về model chính. Người dùng thấy "Core không chọn được model".

Luật mới, giống cơ chế ghim của hội thoại nhưng cho cả Core:

- `settings.model.core_provider` + `core_model`. Rỗng = **theo model chính** (đổi model chính là Core đổi theo ngay).
- Mọi chat có kênh `agent:javis-core` chạy theo hai khoá đó, bỏ qua ghim riêng của từng chat
  (`_chat_provider_for_session`). Ghim hỏng (nhà không còn cấu hình, hết lượt) rơi về model chính như mọi ghim.
- Chọn model trên thanh model của một chat Core (`POST /sessions/{id}/model`) là ghi hai khoá đó: **ghim cho cả Core**.
  Dòng "Theo model chính" trong bảng chọn (đã có cho chat trợ lý) gỡ ghim.
- Chat Core không còn bị đóng dấu model ở lượt đầu.
- `GET /sessions/{id}/meta` của chat Core trả ghim của Core, để thanh model nói đúng.

## 2. Bớt báo sai về đăng nhập và kết nối (làm trước, trong cùng bản với mục 1)

Bốn nguồn báo lặp dù mọi thứ vẫn chạy:

1. **Đèn não dò chữ trong cả câu trả lời thành công.** `flag_engine_auth_error` chạy trên kết quả mọi lượt Claude, nên
   một câu trả lời có cụm "not logged in" thắp đèn đỏ và gửi "Javis chưa dùng được". Sửa: chỉ dò khi lượt kết thúc
   lỗi, hoặc khi cả kết quả là một dòng ngắn (lỗi đăng nhập thật luôn ngắn).
   Cờ "đã báo" của đèn não ghi xuống đĩa, nên khởi động lại không báo lại cùng một lần hỏng.
2. **Bàn sự cố mở sự cố mới cho mỗi lần hỏng sau khi đã báo "cần bạn".** Sửa: sự cố đang "cần bạn" cũng gom các lần
   hỏng tiếp theo của cùng việc (đếm thêm, không báo lại) trong `REOPEN_AFTER_S`.
3. **Kiểm tra sau khởi động tính kết nối đang tải lần đầu là hỏng.** Sửa: `starting` không tính là hỏng.
4. **Zalo bị giành phiên báo lại sau mỗi lần khởi động.** Mốc "đã báo" 6 tiếng ghi xuống đĩa.

## 3. Nhóm, mức và chế độ

### 3.1 Mức của một thông báo

| Mức | Nghĩa | Ví dụ |
|---|---|---|
| `info` | bình thường, chỉ để lưu | việc chạy xong, kết nối đã nối lại, có gói mới |
| `important` | đáng chú ý, có thứ hỏng hoặc đáng xem | loop lỗi và tự dừng, sự cố cần bạn, kết nối hỏng sau khởi động |
| `urgent` | khẩn, cần người ngay | nhắc lịch, câu hỏi đang chờ bạn, khách gọi người thật, bot chatbot đang lỗi, Javis không dùng được |

Nơi sinh tin truyền `level` khi biết rõ. Không truyền thì: `quiet=True` là `info`, còn lại là `important`.

### 3.2 Nhóm

| Khoá | Tên hiện | Gồm |
|---|---|---|
| `job` | Kết quả việc | loop, việc Kanban, lệnh nền, webhook, mục tiêu, GitHub |
| `reminder` | Nhắc lịch | nhắc hẹn |
| `question` | Câu hỏi chờ bạn | việc Kanban hỏi bạn, nhóm xin duyệt, nhóm gọi tên bạn |
| `agent` | Trợ lý chủ động | tin trợ lý tự gửi, trợ lý chờ bạn quá một ngày |
| `team` | Nhóm làm việc | việc nhóm bị chặn, bị trả lại |
| `incident` | Sự cố | bàn sự cố |
| `connection` | Kết nối và đăng nhập | đèn não, kiểm tra sau khởi động, Zalo giành phiên, theo dõi web hết đăng nhập |
| `chatbot` | Chatbot và khách | bot lỗi, bot báo chủ, khách gõ /nhanvien, bot kẹt, xin vào nhóm |
| `cost` | Chi phí | cảnh báo ngân sách, báo cáo token tuần |
| `update` | Cập nhật | gói Kho có bản mới |
| `other` | Khác | mọi thứ chưa xếp nhóm |

Nhóm suy từ `source` của tin khi nơi sinh không truyền `group` (`notify_policy.group_of`).

### 3.3 Chế độ mỗi nhóm

`all` (Tất cả) · `important` (Đáng chú ý trở lên) · `urgent` (Chỉ tin khẩn, **mặc định**) · `off` (Tắt).

Quyết định cho một tin (`notify_policy.decide`):

- Mức đạt ngưỡng của chế độ: **báo to** (chấm đỏ, đẩy lên điện thoại, chép vào chat Core và Telegram của chủ như cũ).
- Dưới ngưỡng: **lọc**. Vẫn vào chuông, đã đọc, mang cờ `filtered`, nằm ở ngăn "Đã lọc". Không đẩy, không chép vào
  chat Core, không gửi Telegram của chủ.
- Chế độ `off` do người dùng đặt: **bỏ**, không lưu (chỉ đếm). Do Core đặt: như `urgent`, tức tin khẩn vẫn báo to.
- Tin gửi tới một chat cụ thể (người dùng giao việc từ chat đó) vẫn rơi vào chat đó dù bị lọc hay bỏ: đó là câu trả
  lời người dùng đã hỏi, chỉ chuông là im.

Luật an toàn: **Core không bao giờ làm im tin khẩn.** Chỉ người dùng (chế độ `off`, hoặc tự bấm "Không cần báo" lên
đúng loại tin đó) mới làm im được tin khẩn.

## 4. Phản hồi emoji và bộ phán xử của Core

### 4.1 Phản hồi

Chủ repo chốt lại 29/10/2026: thẻ thông báo trên chuông chỉ có hai nút **Nên báo** / **Không cần báo**
(`POST /inbox/react`, trục `needed` / `not_needed`). Emoji không nằm trên chuông: bấm **Mở trong Javis Core** thì thông báo
thành một tin trong chat Javis Core (có dấu ẩn `javis-cite:inbox:<mã thư>`), người dùng thả emoji của Cộng hưởng
(`reaction_values.REACTION_EMOJI`: 👍 ❤️ 😂 😮 😢 😡) lên tin đó như mọi câu trả lời. Route reaction của chat
(`POST /sessions/{id}/messages/{mid}/reaction`) thấy dấu đó trên một chat Core thì chuyển emoji cho bộ phán xử của Core;
trục "Đáng lẽ nên nói" / "Nên im" của chat được hiểu là Nên báo / Không cần báo. Thông báo tự đổ vào chat Core cũng
mang dấu này, chỉ ở bản trong chat (chuông và Telegram không có).

Điểm của một phản hồi: 👍 ❤️ 😮 = +1, 😂 = 0, 😢 😡 = -1, Nên báo = +2, Không cần báo = -2.

### 4.2 Chữ ký của một loại tin

Hai tin là "cùng loại" khi cùng nhóm và cùng chữ ký: tiêu đề bỏ số, mã, giờ và đường dẫn (cùng cách
`sentinel.signature` che lỗi). "Việc 'Kiểm tra đơn' lỗi lần 3" và "lần 4" là một loại.

### 4.3 Core tự chỉnh

Chạy ngay sau mỗi phản hồi, và mỗi khi một tin bị chặn vì lặp:

1. **Không cần báo** lên một tin: loại tin đó (chữ ký) bị **lọc** từ nay. Nếu là tin khẩn thì đây là chính người dùng
   bấm, nên được phép.
2. **Nên báo** lên một tin đã lọc: loại tin đó luôn **báo to** từ nay (trừ khi người dùng tắt cả nhóm).
3. **Điểm nhóm** (tổng điểm phản hồi của nhóm trong 30 ngày, tính từ lần chỉnh trước của nhóm đó):
   - từ -4 trở xuống: hạ nhóm một nấc (`all` → `important` → `urgent` → `off` của Core);
   - từ +4 trở lên, tính trên tin đã lọc: nâng nhóm một nấc.
4. **Lặp lại**: cùng một loại tin báo to tới lần thứ 3 trong 6 tiếng thì các lần sau trong 6 tiếng đó bị lọc, ghi
   "lặp lại" trên thẻ thư. Không áp cho tin khẩn. Đây là chặn tạm, không phải một thay đổi luật, nên không vào nhật ký
   và Core không nói gì trong chat.

Mỗi lần chỉnh: một dòng trong nhật ký thay đổi (`notify_policy` giữ 100 dòng gần nhất) với lý do, ai chỉnh (`core` /
`owner`) và nút **Hoàn tác**, và một câu ngắn trong chat Javis Core của brain đang dùng. Ví dụ: "Em vừa chuyển nhóm
Kết nối và đăng nhập sang Chỉ tin khẩn. Hoàn tác ở Bộ lọc thông báo của chuông."

Thông báo hệ thống không gắn brain thì Core nói trong chat Core của brain mặc định.

### 4.4 Ra lệnh bằng lời

Công cụ `javis_notify` cho mọi bộ não (qua MCP Hub): `op=status` (chế độ từng nhóm, loại tin đang lọc, thay đổi gần
nhất), `op=set` (đặt chế độ một nhóm), `op=mute` / `op=unmute` (một loại tin, tìm theo chữ trong tiêu đề),
`op=undo` (hoàn tác một thay đổi). Người dùng nói "tắt thông báo đăng nhập Zalo" thì Core gọi công cụ này.

## 5. Giao diện

- Chuông, tab "Của tôi": tin bị lọc không nằm trong danh sách chính. Cuối danh sách có dòng "Đã lọc (N)" mở ngăn tin
  đã lọc. Mỗi thẻ thư có hai nút Nên báo / Không cần báo.
- Chuông có thêm tab **Bộ lọc** (thẻ Bộ lọc thông báo): mỗi nhóm một ô chọn bốn chế độ, danh sách loại tin đang bị lọc
  hoặc luôn báo (bỏ được), và nhật ký thay đổi gần đây với nút Hoàn tác. Chữ dài để sau nút (i).

## 6. Dữ liệu

`STATE_DIR/notify_policy.json`:

```
{"version": 1,
 "groups": {"<nhóm>": {"mode": "urgent", "set_by": "default|owner|core", "since": ts}},
 "signatures": {"<nhóm>|<chữ ký>": {"rule": "mute|always", "set_by": "owner|core", "label": "...", "at": ts}},
 "feedback": [{"ts", "group", "sig", "score", "filtered"}],   // 500 gần nhất
 "loud": {"<nhóm>|<chữ ký>": [ts, ...]},                       // mốc báo to để chặn lặp
 "changes": [{"id", "ts", "kind", "target", "from", "to", "reason", "set_by", "undone"}],
 "dropped": {"<nhóm>": n}}
```

Thư trong `inbox.json` có thêm `group`, `level`, `sig`, `filtered`, `reaction` (`{value, axis, ts}`).

## 7. Thứ tự giao

- **0.402.0**: mục 1 và mục 2.
- **0.403.0**: mục 3, 4, 5.
