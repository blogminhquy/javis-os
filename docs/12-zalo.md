# Zalo Agent MCP

> **Javis có HAI đường vào Zalo, đừng lẫn.** Trang này nói về đường thứ nhất: đăng nhập
> **chính tài khoản Zalo của bạn** để Javis thao tác thay bạn. Đường thứ hai là **Zalo Bot**
> (API chính thức) ở trang [Chatbot](25-chatbot.md): một danh tính riêng, an toàn, để KHÁCH
> nói chuyện với Javis. Cái nào cũng dùng được, và dùng cả hai cũng được.
>
> | | Zalo Agent MCP (trang này) | [Zalo Bot](25-chatbot.md) |
> |---|---|---|
> | Là ai | Chính bạn | Một bot riêng |
> | API | Không chính thức (zca-js) | Chính thức |
> | Rủi ro khoá tài khoản | Có | Không |
> | Đọc được hội thoại cũ | Có | Chỉ tin nhắn gửi cho bot |
> | Nhắn cho người chưa quen bot | Được | Không |
> | Dùng để | Javis làm việc thay bạn | Khách nói chuyện với Javis |

Javis kết nối Zalo cá nhân bằng MCP chuẩn của dự án
[`zalo-agent-cli`](https://github.com/PhucMPham/zalo-agent-cli). Luồng mới chỉ có một
tiến trình MCP: đăng nhập QR, đọc hoặc tìm hội thoại và gửi tin qua các tool do dự án
gốc cung cấp.

> `zalo-agent-cli` dùng API Zalo không chính thức qua `zca-js`. Zalo không hỗ trợ cách
> kết nối này và tài khoản có thể bị hạn chế hoặc khoá. Nên dùng tài khoản phụ, tránh
> gửi tự động hàng loạt và tự chịu trách nhiệm khi sử dụng.

## Cần chuẩn bị

- Node.js 20 trở lên trên máy hoặc VPS chạy Javis.
- Điện thoại đã đăng nhập tài khoản Zalo cần kết nối.
- Javis đã được khởi động và bạn đăng nhập được dashboard.

Javis đang ghim `zalo-agent-cli` ở phiên bản `1.6.2`, là phiên bản đã được kiểm tra với
bảy tool MCP bên dưới.

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
| `zalo_get_messages` | Đọc tin mới trong bộ đệm, hỗ trợ cursor | Đọc |
| `zalo_get_history` | Lấy lịch sử một cuộc chat, có phân trang | Đọc |
| `zalo_list_threads` | Liệt kê các cuộc chat đang có trong bộ đệm | Đọc |
| `zalo_search_threads` | Tìm nhóm hoặc người theo tên | Đọc |
| `zalo_view_media` | Tải/mở ảnh, âm thanh hoặc video của tin nhắn | Đọc |
| `zalo_mark_read` | Đánh dấu đã xử lý đến một cursor | Ghi |
| `zalo_send_message` | Gửi tin cho cá nhân hoặc nhóm | Nguy hiểm |

Danh sách trên theo mã nguồn `zalo-agent-cli` 1.6.2. Tài liệu MCP của dự án gốc:

<https://github.com/PhucMPham/zalo-agent-cli/blob/main/skill/references/mcp-guide.md>

## Gửi ảnh và file

`zalo_send_message` ở trên **chỉ gửi được chữ**. Muốn gửi ảnh (ví dụ ảnh Javis vừa tạo) hay
file (báo cáo PDF, bảng tính) thì dùng tool `zalo_send_image` do plugin bundled `zalo-image`
cung cấp. Plugin bật sẵn, không cần cài gì thêm, và dùng đúng tài khoản Zalo bạn đã quét QR.

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
- **Toàn quyền**: cho phép gửi tin (cả `zalo_send_message` lẫn `zalo_send_image`).

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

- **Không hiện QR**: kiểm tra `node --version` phải từ 20 trở lên và máy truy cập được npm.
- **QR hết hạn**: đóng cửa sổ kết nối rồi bấm **Kết nối** để tạo mã mới.
- **Không thấy cuộc chat**: thử `zalo_search_threads`; nếu cần tin cũ, dùng
  `zalo_get_history` thay vì chỉ dùng `zalo_get_messages`.
- **Tool gửi bị chặn**: mở menu chip tài khoản và chuyển quyền sang **Toàn quyền**.
- **Báo phiên đang được dùng nơi khác**: đóng Zalo Web hoặc tiến trình
  `zalo-agent-cli` khác đang dùng cùng tài khoản, rồi thử lại.
- **Muốn đăng nhập lại từ đầu**: xoá connection trên dashboard, sau đó kết nối và quét QR
  lại. Thư mục phiên của connection khác không bị ảnh hưởng.

## Tham khảo

- [Repository `zalo-agent-cli`](https://github.com/PhucMPham/zalo-agent-cli)
- [Hướng dẫn MCP upstream](https://github.com/PhucMPham/zalo-agent-cli/blob/main/skill/references/mcp-guide.md)
- [Kết nối và phân quyền MCP trong Javis](09-mcp-va-so-lieu.md)
