# Trang Chatbot v5: Hội thoại, Bot, Kênh, Thống kê

Chủ repo duyệt ngày 28/10/2026 sau năm bản mẫu (v1 tới v5, mẫu cuối ở bản mẫu HTML "javis-chatbot-v5" gửi trong phiên
làm việc). Cảm hứng từ Pancake (khách bên trái, chat bên phải, chọn Page bằng hộp thả xuống, Lọc theo hai tầng) nhưng
sửa những chỗ Pancake bắt người dùng phải học: icon không có chữ, quá nhiều thẻ màu, không thấy ai đang lo cuộc chat.

Mục tiêu một câu: **nhìn là biết cuộc chat nào A.I. đang xử lý, cuộc nào cần bạn, và đổi được ngay tại chỗ.**

## 1. Luật chữ trên màn hình

- Gọi người dùng là **"bạn"**, không "anh". Màn hình này dùng cho mọi người dùng Javis.
- Viết **"A.I."** (có dấu chấm) trong chữ tiếng Việt của trang này, để không đọc lẫn với chữ "ai" (người nào).
  Bản tiếng Anh vẫn viết "AI".
- Các nút người dùng tự bấm để ngôi thứ nhất: "Tôi trả lời", "A.I. soạn, tôi duyệt".
- Không dùng gạch dài. Chữ tối thiểu 16px.

## 2. Bốn tab

`Hội thoại · Bot · Kênh · Thống kê`, mỗi tab có icon và chữ. Số trên tab: Hội thoại = số cuộc chat **Cần bạn**,
Kênh = số việc cần xử lý (kênh lỗi, nhóm chờ duyệt, tài khoản chưa có bot mà không đặt "Không cần bot").
Tab cũ `inbox` và `bot` vẫn nhận làm bí danh (`inbox` → Hội thoại, `bot` → Bot).

## 3. Ai đang xử lý cuộc chat (một trạng thái cho cả trang)

Server tính cho MỖI cuộc chat một trạng thái, mọi chỗ trên trang đọc đúng trạng thái này (viền màu dòng khách, dải
trạng thái trong khung chat, công tắc ở tab Kênh, số đếm trên tab). Không có chỗ nào tự tính lại ở trình duyệt.

| `who` | Màu | Tên hiện | Khi nào |
|---|---|---|---|
| `you` | vàng | Cần bạn | khách đang chờ mà không ai lo, nhóm có người gọi A.I. mà chưa cho phép, A.I. soạn xong chờ duyệt, bạn đang tiếp mà khách chờ |
| `ai` | tím | A.I. đang xử lý | A.I. được phép ở đây, bot đang chạy, chế độ A.I. tự trả lời hoặc A.I. soạn (chưa có bản nào chờ) |
| `owner` | xanh dương | Bạn đang xử lý | chế độ Tôi trả lời, khách không chờ |
| `log` | xám | Chỉ ghi lại | A.I. không được phép ở đây, hoặc kênh không có bot, hoặc bot tắt mà khách không chờ |

Kèm `who_code` để giao diện viết đúng một câu: `pending`, `draft_ready`, `waiting`, `waiting_you`, `bot_off_waiting`,
`ai`, `draft_mode`, `you`, `not_allowed`, `no_bot`, `bot_off`.

"Khách đang chờ" dùng lại đúng luật "cần trả lời" đã có (`can_tra_loi`): tin cuối của khách, chat riêng, hoặc nhóm mà
bộ phán xử vừa cân nhắc rồi im. Nhóm nói chuyện với nhau thì không tính là chờ.

Module: `server/inbox_state.py` (hàm thuần, test được không cần server).

## 4. Ai trả lời: ba chế độ mỗi cuộc chat, cộng công tắc cho phép

Hai thứ tách nhau:

1. **A.I. có được trả lời ở đây không** (cho phép). Lưu ở BOT như cũ: `groups`, `people` (audience `chon`), và mới:
   `blocked`, danh sách cuộc chat bạn tắt A.I. dù audience đang mở (ví dụ chat riêng khi audience là `nhom`, hay nhóm
   khi audience là `all`). `_ly_do_im_co_ban` trả `chat_tat` cho cuộc chat trong `blocked`, trước mọi luật khác.
2. **Ai trả lời khi A.I. được phép** (chế độ cuộc chat, cột `mode` của hội thoại):
   - `ai` = A.I. tự trả lời (như cũ).
   - `draft` = **A.I. soạn, tôi duyệt** (mới): lượt bot chạy như thường nhưng câu trả lời KHÔNG gửi; nó nằm trong
     `metadata.draft` của hội thoại (`text`, `ts`, `for_message_id`) và cuộc chat chuyển sang Cần bạn. Bạn bấm Gửi
     (gửi đúng chữ đang sửa, ghi vào Hộp thư là lời A.I.), Viết lại (nhờ soạn lần nữa) hoặc Bỏ. Tin khách mới tới khi
     bản cũ chưa duyệt thì bản mới thay bản cũ. Đổi chế độ KHÔNG xoá bản đang chờ (bấm Hoàn tác là có lại đủ); bạn
     tự gửi tay (`/reply`) thì bản đó bỏ đi vì đã có câu trả lời. Còn bản chờ là cuộc chat ở Cần bạn, ở chế độ nào cũng vậy.
   - `human` = Tôi trả lời (như cũ: A.I. im).

Đường mới `POST /conversations/{id}/ai` với `on=0|1`: bật thì gỡ khỏi `blocked`, thêm vào `groups`/`people` khi audience
cần danh sách, và bỏ khỏi hàng chờ duyệt; tắt thì làm ngược lại (audience đang mở thì thêm vào `blocked`). Trả về hội
thoại kèm trạng thái mới.

`POST /conversations/{id}/mode` nhận thêm `draft`. `POST /conversations/{id}/note` lưu ghi chú của bạn (vào khách nếu cuộc
chat có khách, không thì vào chính cuộc chat). Mỗi dòng danh sách còn kèm `reply_when` và `yield_min` (số phút nhường) của
bot để bảng Thông tin hiện đúng. `POST /conversations/{id}/draft` với `action=send|discard`
(gửi thì nhận `text` đã sửa).

## 5. Nút "A.I. trả lời" (ra lệnh cho A.I.)

Ô nhập có hai nút: **Gửi** (gửi nguyên văn cho khách) và **A.I. trả lời**. Bấm A.I. trả lời thì chữ trong ô là
**lệnh** cho A.I. (ví dụ "báo giá sỉ 20 thùng, hẹn giao thứ 5"); ô trống thì A.I. tự đọc cuộc chat mà soạn.
`POST /conversations/{id}/ai-reply` nhận thêm `instruction`. Lệnh đi vào lượt như một ghi chú của chủ chỉ model đọc
(cùng đường `ghi_chu_dau` đã có), không vào Hộp thư. Kết quả luôn là bản nháp hiện trong khung nét đứt, ghi rõ lệnh,
kèm Bỏ / Viết lại / Gửi. Không bao giờ tự gửi. Bản nháp này lưu ở server như bản của chế độ A.I. soạn (tải lại trang vẫn
còn), Gửi và Bỏ đi qua cùng đường `/draft`.

## 6. Tab Hội thoại

Máy tính: ba cột. **Trái** danh sách khách, **giữa** khung chat, **phải** bảng Thông tin (đóng được).

Cột trái, từ trên xuống:
- **Hộp chọn kênh** (thả xuống): ô tìm, "Tất cả kênh", rồi từng kênh có logo thật, mỗi nick/Page một ô tick (tick tên
  kênh = cả kênh), số Cần bạn từng nơi; dưới cùng Bỏ chọn / Xong, và "Quản lý kênh". Chọn lưu ở trình duyệt.
  Server nhận `account_ids` (danh sách khoá tài khoản, cách nhau dấu phẩy).
- **Ô tìm** và nút **Lọc** mở menu hai tầng: Thời gian (bộ chọn ngày `date-range.js`, gửi `from`/`to` dạng YYYY-MM-DD, tính theo tin cuối), Có chứa thẻ, Loại trừ thẻ, Loại cuộc chat, Bot trả lời, Thông tin khách
  (có SĐT, chỉ chat đã ghim: `pinned=1`), Tin cuối của ai (`last_by=customer|ai|human`), Đã ẩn. Bộ lọc đang bật hiện thành chip có dấu x.
- **Bốn nút lọc nhanh có chấm màu:** Cần bạn · A.I. đang xử lý · Bạn đang xử lý · Tất cả, có số. Server nhận `who`.
- **Dòng khách:** viền trái màu theo `who`, ảnh đại diện có logo kênh ở góc, tên, giờ, tin cuối (có "A.I.:" hoặc
  "Bạn:"), số chưa đọc, tối đa 2 thẻ cộng "+n", tên nick/Page khi đang xem nhiều nơi. Giữ menu dòng (ghim, ẩn, chưa
  đọc, thẻ, chép) như hiện tại.

Khung chat: đầu khung tên khách, kênh, nút Thông tin. Dưới đó **thanh "Ai trả lời"** cùng màu với `who`: ba nút
(A.I. tự trả lời / A.I. soạn, tôi duyệt / Tôi trả lời) khi A.I. được phép; "Cho A.I. trả lời ở đây" khi chưa; Cho phép /
Bỏ qua khi đang chờ duyệt; cạnh đó MỘT câu nói chuyện gì đang xảy ra. Tin A.I. có nhãn "A.I. · tên bot".

Bảng Thông tin: khách (SĐT, thẻ thêm bớt tại chỗ, ghi chú), **A.I. ở cuộc chat này** (Ai trả lời, A.I. được làm gì ở
đây = ngoại lệ mức quyền cho chat riêng, Bạn nhắn tay thì A.I. nhường bao lâu, Trong nhóm A.I. lên tiếng khi), Kênh.
Mọi ô là hộp thả xuống, đổi xong có Hoàn tác.

Điện thoại: danh sách → chạm mở chat → nút ⓘ mở bảng Thông tin toàn màn hình. Bốn tab chia đều, icon trên chữ.

## 7. Tab Kênh

Trái: các nick/Page xếp theo kênh, logo thật, nút "Kết nối kênh mới", mỗi kênh có "Gắn A.I. cho nhiều …" (tick, chọn
bot, **Lưu**). Phải: nick/Page đang chọn, **ô chọn "A.I. trực nick này" kèm Huỷ / Lưu khi đổi**, và danh sách nhóm/người
với công tắc "A.I. ở đây" (gọi `POST /conversations/{id}/ai`), trạng thái `who`, Cho phép, Mở chat. Có lựa chọn
"Không cần bot" để tài khoản không bị đếm vào việc cần xử lý.

Server (0.377.0): `POST /channels/accounts/{id}/bot` (`bot_id`, rỗng = không bot) gỡ tài khoản khỏi bot đang giữ (bot hết
tài khoản thì tắt, như khi xoá tài khoản) rồi gắn cho bot mới, và **các cuộc chat cũ của tài khoản đổi theo bot mới**
(không thì công tắc "A.I. ở đây" báo chưa có bot). `POST /channels/no-bot` (`account_key`, `on`) lưu cờ "Không cần bot"
trong `sync_state` của kho hội thoại (tài khoản Zalo cá nhân không có bản ghi trong `channel_accounts.json`); gắn bot là
cờ tự bỏ. `GET /channels/accounts` trả thêm `no_bot`. `POST /conversations/{id}/ai` báo lỗi `chat_id` khi danh sách của
bot không giữ được mã cuộc chat đó, thay vì báo xong mà không đổi gì. Số trên tab Kênh = tài khoản lỗi + tài khoản chưa
có bot mà không đặt "Không cần bot". Tab Bot không còn mục "Kênh chưa có bot": thẻ tài khoản (ghi hội thoại, nhập tin cũ,
sửa, xoá) nằm trong khung phải của tab Kênh.

## 8. Tab Bot

Lưới thẻ bot (tên, bật tắt, cộng sự, mức quyền, đang trực ở đâu kèm logo, số tin hôm nay). Bấm thẻ mở trang bot với
các mục gập: Vai trò, Trả lời ở đâu, Cách trả lời, A.I. được làm gì, Giờ trực, Nâng cao. Sửa trên bản nháp; có thay đổi
thì **thanh "Bạn có thay đổi chưa lưu" với Huỷ / Lưu** ở đáy. Lưu gọi `POST /chatbots/{id}/update` như form cũ. Form
cũ (wizard) vẫn dùng để tạo bot mới cho tới khi trang mới làm đủ.

## 9. Tab Thống kê

Kỳ chọn bằng bộ chọn ngày (chọn nhanh hoặc hai ngày trên lịch, nhớ trong trình duyệt). Bốn ô: A.I. đã trả lời (tin `ai`), Bạn đã trả lời (tin `human` gửi từ Javis; số lần tiếp
quản không được ghi lại nên không đếm được), Khách chờ trung bình (từ tin khách đầu tiên chưa ai đáp tới câu trả lời đầu
tiên, một chuỗi tin khách liền nhau tính một lần chờ), Đang chờ bạn (bấm vào là mở Hội thoại ở Cần bạn). Thanh ngang
một màu: A.I. trả lời theo kênh và theo bot, số ghi ở cuối thanh. Tính từ kho hội thoại, so với kỳ trước cùng độ dài.
Đường `GET /conversations/insights?from=YYYY-MM-DD&to=YYYY-MM-DD` (hai ngày đều tính, nửa đêm giờ máy chủ; `days=` cũ vẫn nhận).

## 10. Chia đợt phát hành

1. **0.371.0** Nền phía server: mục 3, 4, 5, `account_ids` và `who` cho danh sách, spec này.
2. **Đợt 2** Tab Hội thoại mới (mục 6).
3. **Đợt 3 (0.377.0)** Tab Kênh, Bot, Thống kê (mục 7, 8, 9).
4. **Đợt 4** Rà lỗi đầu cuối trên máy tính và điện thoại, sửa tới khi sạch.

Mỗi đợt một số phiên bản, merge khi CI xanh.
