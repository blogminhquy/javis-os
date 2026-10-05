# Zalo Agent MCP

***Tiếng Việt** · [English](en/12-zalo-agent-mcp.md)*

> **Javis có BA chỗ dính tới Zalo, đừng lẫn.** Trang này nói về chỗ thứ nhất: đăng nhập
> **chính tài khoản Zalo của bạn** để Javis thao tác thay bạn. Hai chỗ kia dùng API chính
> thức, an toàn, nhưng chỉ thấy được thứ người ta nhắn thẳng cho bot.
>
> | | Zalo Agent MCP (trang này) | [Kênh Zalo Bot](26-kenh-zalo-bot.md) | [Chatbot](25-chatbot.md) |
> |---|---|---|---|
> | Là ai | Chính bạn | Một bot riêng | Một bot riêng, đứng tên Agent |
> | API | Không chính thức (zca-js) | Chính thức | Chính thức |
> | Rủi ro khoá tài khoản | Có | Không | Không |
> | Đọc được hội thoại cũ | Có | Chỉ tin gửi cho bot | Chỉ tin gửi cho bot |
> | Nhắn cho người chưa quen bot | Được | Không | Không |
> | Dùng để | Javis làm việc thay bạn | **Bạn** nhắn cho Javis | **Khách** nhắn cho Javis |
>
> Dùng cả ba cùng lúc cũng được, chúng không đụng nhau.

Javis kết nối Zalo cá nhân bằng MCP của
[`javis-zalo`](https://github.com/blogminhquy/javis-zalo), bản CLI Zalo riêng của Javis. Chỉ có
một tiến trình MCP: đăng nhập QR, đọc hoặc tìm hội thoại và gửi tin qua các tool của nó.

> `javis-zalo` dùng API Zalo không chính thức qua `zca-js`. Zalo không hỗ trợ cách
> kết nối này và tài khoản có thể bị hạn chế hoặc khoá. Nên dùng tài khoản phụ, tránh
> gửi tự động hàng loạt và tự chịu trách nhiệm khi sử dụng.

## Cần chuẩn bị

- Node.js 20 trở lên trên máy hoặc VPS chạy Javis, và máy tải được từ GitHub (lần đầu).
- Điện thoại đã đăng nhập tài khoản Zalo cần kết nối.
- Javis đã được khởi động và bạn đăng nhập được dashboard.

Javis ghim `javis-zalo` theo tag phát hành (hiện là `v1.0.0`) và cài thẳng từ tarball của tag
đó trên GitHub, không cần tài khoản npm hay Git. Chỉ thư viện `zca-js` bên dưới đi theo bản chính
thức trên npm. Từ 0.83.0 Javis thay `zalo-agent-cli` 1.6.2 của tác giả ngoài bằng bản riêng này;
kết nối đã đăng nhập từ trước tự chuyển sang mà không phải quét QR lại.

## Kết nối bằng QR

1. Mở **Kết nối** → tìm **Zalo Agent MCP** → bấm **Kết nối**.
2. Đọc cảnh báo rủi ro, nhập tên gợi nhớ nếu cần rồi bấm **Hiện mã QR**.
3. Trong app Zalo trên điện thoại, mở trình quét QR và quét mã trên dashboard.
4. Khi thẻ tài khoản xuất hiện trong phần **Đã kết nối**, kết nối đã sẵn sàng.
5. Muốn nối thêm tài khoản, bấm **＋ Thêm tài khoản**. Mỗi tài khoản dùng một thư mục
   phiên riêng nên không ghi đè phiên của nhau.

Nút **Hướng dẫn trên GitHub** trong thẻ Zalo luôn mở trang tài liệu này:

<https://github.com/blogminhquy/javis-os/blob/main/docs/12-zalo.md>

## Các tool MCP

| Tool | Công dụng | Mức thao tác |
|---|---|---|
| `zalo_get_messages` | Đọc tin mới trong bộ đệm, đọc tiếp bằng `since` (số thứ tự) | Đọc |
| `zalo_get_history` | Lấy lịch sử một cuộc chat (kể cả nhóm), có phân trang, kèm `replyTo` và `mentions` | Đọc |
| `zalo_search_history` | Tìm trong lịch sử mọi cuộc chat theo người gửi hoặc khoảng ngày | Đọc |
| `zalo_list_threads` | Liệt kê các cuộc chat đang có trong bộ đệm | Đọc |
| `zalo_search_threads` | Tìm nhóm hoặc người theo tên | Đọc |
| `zalo_view_media` | Tải/mở ảnh, âm thanh hoặc video trên máy chủ (bộ não không thấy ảnh, xem `zalo_read_images` bên dưới) | Đọc |
| `zalo_mark_read` | Đánh dấu đã xử lý đến một cursor | Ghi |
| `zalo_send_message` | Gửi tin cho cá nhân hoặc nhóm | Nguy hiểm |

Danh sách trên theo mã nguồn `javis-zalo` 1.0.0. Tên tham số lấy từ mã nguồn: kiểu cuộc chat của
`zalo_send_message` là `threadType` (0 = chat riêng, 1 = nhóm), và `zalo_get_messages` đọc bằng
`since` chứ không có `cursor`. Lịch sử chỉ có từ lúc MCP kết nối, cộng phần Zalo gửi lại lúc kết
nối (khoảng hai tuần gần nhất); tin cũ hơn thì không API nào lấy được.

## Gói Zalo mở rộng (Javis Store)

Ba nhóm tool dưới đây (đọc ảnh, gửi ảnh và file, tag người cùng ghi chú, nhắc hẹn, poll) bù đúng
chỗ MCP chuẩn còn thiếu. Từ 0.73.0 chúng nằm trong gói **`javis.zalo`** trên Javis Store thay vì
đi sẵn trong app, để ai không dùng Zalo thì không phải mang theo:

- **Quét QR Zalo xong là Javis mời cài gói**, qua đúng màn hình đồng ý của kho: liệt kê từng tệp
  mã, công tắc "chạy ngay" bật sẵn vì bạn vừa tự đấu Zalo. Bấm Cài là có đủ tool.
- **Máy đã đấu Zalo từ trước** thì trang Kết nối hiện dải nhắc kèm nút **Cài gói đi kèm**.
  Javis không bao giờ tự cài gói có mã mà không hỏi.
- Kết nối Zalo, Hộp thư và chatbot Zalo vẫn ở trong app, chạy bình thường dù chưa cài gói. Thiếu
  gói thì chỉ thiếu các tool mở rộng.

## Đọc ảnh trong nhóm

MCP của Zalo chỉ trả **đường link** của ảnh, giữ tin trong 2 giờ, và `zalo_view_media` mở ảnh
bằng trình xem ảnh của máy chủ chứ không đưa cho bộ não. Nên gói `javis.zalo` có tool
`zalo_read_images`:

| Tool | Công dụng | Mức thao tác |
|---|---|---|
| `zalo_read_images` | Lấy ảnh người ta gửi trong nhóm về brain và cho bộ não biết trong ảnh có gì | Ghi (lưu ảnh vào brain) |

Nói trong chat như bình thường, ví dụ “xem ảnh hoá đơn chị Lan vừa gửi trong nhóm Kinh doanh”.

- **Ảnh lấy thẳng từ Zalo**, không phụ thuộc bộ đệm 2 giờ của MCP: Javis hỏi Zalo các tin gần
  nhất của nhóm (mặc định 30, tối đa 100) và lấy tối đa 8 ảnh mới nhất. Chat riêng thì chỉ lấy
  được ảnh còn trong bộ đệm MCP.
- **Ảnh lưu vào `attachments/zalo/<id nhóm>/`** của brain, nên hiện được ngay trong khung chat.
- **Mọi bộ não đều "thấy" ảnh.** Claude Code và Codex tự mở file ảnh. Các engine API (OpenRouter,
  Gemini...) không tự xem ảnh được, nên ChatGPT trên gói bạn đang đăng nhập nhìn ảnh rồi tả lại,
  chép nguyên văn chữ và số trong ảnh. Chưa đăng nhập ChatGPT ở trang Model thì vẫn tải được ảnh,
  chỉ thiếu phần tả.

Phần ChatGPT xem ảnh nằm trong app (plugin có sẵn `image-chatgpt`, tool `javis_describe_image`),
nên xem được cả mọi ảnh khác trong brain, có cài gói Zalo hay không.

## Gửi ảnh và file

`zalo_send_message` ở trên **chỉ gửi được chữ**. Muốn gửi ảnh (ví dụ ảnh Javis vừa tạo) hay
file (báo cáo PDF, bảng tính) thì dùng tool `zalo_send_image` trong gói `javis.zalo`. Nó dùng
đúng tài khoản Zalo bạn đã quét QR.

| Tool | Công dụng | Mức thao tác |
|---|---|---|
| `zalo_send_image` | Gửi ảnh hoặc file kèm lời nhắn | Nguy hiểm (mức Toàn quyền) |

Nói trong chat như bình thường, ví dụ “gửi ảnh này cho nhóm Kinh doanh” hoặc “gửi báo cáo
tháng 7 cho anh Nam qua Zalo”.

Ba điều nên biết:

- **Chỉ gửi được file nằm trong bộ não đang dùng.** Đây là rào an toàn cố ý: nếu không, một
  câu chat khéo léo có thể khiến Javis gửi file bất kỳ trên máy chủ ra ngoài, mà tin nhắn Zalo
  thì không thu hồi được.
- **Một lượt gửi cùng một loại**, hoặc toàn ảnh hoặc toàn file, tối đa 10 file. Trộn lẫn thì
  Zalo hiển thị sai kiểu nên Javis sẽ báo lại thay vì tự đoán.
- **Đấu nhiều tài khoản Zalo thì Javis hỏi lại** nên gửi bằng tài khoản nào. Gửi nhầm tài
  khoản là gửi dưới danh tính người khác, nên đây là chỗ không được đoán.

Cần Node.js 20+ trên máy chạy Javis, giống như phần kết nối Zalo.

## Tag người, ghi chú, nhắc hẹn và poll

`zalo_send_message` chỉ gửi chữ nên không tag được ai, và MCP của Zalo cũng không có ghi chú, nhắc hẹn hay poll. Gói
`javis.zalo` bù đúng các chỗ đó bằng năm tool, mọi bộ não đều gọi được:

| Tool | Công dụng | Mức thao tác |
|---|---|---|
| `zalo_group_members` | Liệt kê thành viên một nhóm (id kèm tên), hoặc tra một người theo tên | Đọc |
| `zalo_send_mention` | Gửi tin vào nhóm và tag đúng người | Nguy hiểm (mức Toàn quyền) |
| `zalo_create_note` | Tạo ghi chú nhóm, ghim được | Nguy hiểm (mức Toàn quyền) |
| `zalo_create_reminder` | Nhắc hẹn hiện trong Zalo, chọn giờ và lặp (hằng ngày, tuần, tháng) | Nguy hiểm (mức Toàn quyền) |
| `zalo_create_poll` | Poll cho nhóm: chọn nhiều đáp án, ẩn danh, hạn đóng | Nguy hiểm (mức Toàn quyền) |

Nói trong chat như bình thường, ví dụ “nhắn nhóm Kinh doanh tag @minhquy họp lúc 9h nhé” hoặc “tạo poll trưa nay ăn gì trong nhóm Lớp Javis”.

Bốn điều nên biết:

- **Tag chỉ cần nói tên.** “@minhquy” hay “Minh Quý” đều được, không phân biệt hoa thường hay dấu. Javis tìm ID Zalo thật trong
  những người đã nhắn ở nhóm đó trước, rồi tới danh sách thành viên của Zalo. **Trùng tên hoặc không thấy thì Javis hỏi lại kèm
  danh sách ứng viên**, không đoán, vì tag nhầm người thì không rút lại được. Tag cả nhóm (`@All`) chỉ khi bạn yêu cầu rõ.
- **Nhắc hẹn này khác nhắc hẹn riêng của Javis** (`javis_schedule`): nó hiện trong Zalo nên cả nhóm cùng thấy. Giờ tính theo múi giờ của Javis.
- **Nhóm khoá quyền tạo ghi chú hoặc poll của thành viên** thì Zalo từ chối và Javis báo thẳng lý do đó. Nếu lệnh quá giờ, Javis nói
  **không rõ đã tạo chưa** và dặn xem lại nhóm trước khi thử tiếp, để khỏi ra hai poll.
- **Đấu nhiều tài khoản Zalo thì Javis hỏi lại** nên dùng tài khoản nào, giống phần gửi ảnh.

Bot chuyên trách đứng trong nhóm Zalo thì **tự tag người nó đang trả lời**, không cần công cụ nào ở trên, xem [Chatbot](25-chatbot.md).

## Cách dùng trong chat

Có thể nói tự nhiên:

- “Tìm nhóm Kinh doanh trên Zalo.”
- “Đọc 20 tin gần nhất của nhóm Kinh doanh.”
- “Có tin Zalo nào mới không?”
- “Gửi nhóm Kinh doanh: 9 giờ sáng mai họp nhé.”

Khi gửi tin, nên nêu rõ tên hoặc `threadId`, nội dung và đó là cá nhân hay nhóm. Nếu kết
quả tìm kiếm có nhiều cuộc chat trùng tên, Javis phải hỏi lại thay vì tự đoán.
Nếu chỉ có một kết quả khớp chính xác, Javis gửi ngay bằng `zalo_send_message`; không cần
bật listener, không cần người nhận nhắn trước và không phụ thuộc danh sách theo dõi.

## Phân quyền

Kết nối mới mặc định ở mức **Toàn quyền** để có thể dùng `zalo_send_message`.

- **Chỉ đọc**: chỉ dùng năm tool đọc.
- **Ghi nháp**: thêm `zalo_mark_read`, vẫn chặn gửi tin.
- **Toàn quyền**: cho phép gửi tin (`zalo_send_message`, `zalo_send_image`) và các tool tag người, ghi chú, nhắc hẹn, poll.

Bạn đổi quyền trong menu của chip tài khoản ở trang **Kết nối**. Việc nền chạy ở chế độ
giới hạn vẫn bị MCP Hub chặn gửi tin, dù tài khoản đang đặt Toàn quyền.

## Khác với tích hợp Zalo cũ

Luồng mới đã bỏ sidecar `listen --webhook`, endpoint `/hook/zalo`, panel “Nghe tin liên
tục”, file luật theo từng cuộc chat và hai plugin `javis_zalo_rule`/`javis_zalo_send`.
Không còn việc một tiến trình listener tự tắt rồi bật lại connector MCP.

Do đó Javis không tự chuyển tiếp tin Zalo sang Telegram ở nền. Khi cần kiểm tra tin, hãy
hỏi Javis; MCP có thể dùng `zalo_get_messages` cho tin đang đệm hoặc
`zalo_get_history` cho lịch sử.

## Xử lý lỗi

- **Không hiện QR**: kiểm tra `node --version` phải từ 20 trở lên và máy truy cập được npm và
  GitHub (`codeload.github.com`).
- **QR hết hạn**: đóng cửa sổ kết nối rồi bấm **Kết nối** để tạo mã mới.
- **Không thấy cuộc chat**: thử `zalo_search_threads`; nếu cần tin cũ, dùng
  `zalo_get_history` thay vì chỉ dùng `zalo_get_messages`.
- **Tool gửi bị chặn**: mở menu chip tài khoản và chuyển quyền sang **Toàn quyền**.
- **Báo phiên đang được dùng nơi khác**: đóng Zalo Web hoặc tiến trình
  `javis-zalo` (hay `zalo-agent-cli` cũ) khác đang dùng cùng tài khoản, rồi thử lại.
- **Muốn đăng nhập lại từ đầu**: xoá connection trên dashboard, sau đó kết nối và quét QR
  lại. Thư mục phiên của connection khác không bị ảnh hưởng.

## Tham khảo

- [Repository `javis-zalo`](https://github.com/blogminhquy/javis-zalo)
- [zca-js](https://github.com/RFS-ADRENO/zca-js), thư viện nói chuyện với Zalo bên dưới
- [Kết nối và phân quyền MCP trong Javis](09-mcp-va-so-lieu.md)
