# 33 - Cookies (Kho đăng nhập)

***Tiếng Việt** · [English](en/33-login-vault.md)*

Từ 0.251.0 Javis có trang **Cookies** (trước 0.261.0 tên là Kho đăng nhập): chỗ cất phiên đăng nhập riêng của bạn (cookie) để Javis dùng lại. Bạn đăng nhập một lần trên trình duyệt của mình, đưa cookie cho Javis, rồi Javis đọc được những trang chỉ hiện khi đã đăng nhập: kênh người bán Shopee, trang affiliate, trang quản trị web.

Kho này là tuỳ chọn. Không thêm đăng nhập nào thì Javis chạy y như cũ.

## Thêm một đăng nhập

1. Cài tiện ích **Cookie-Editor** cho Chrome hoặc Edge.
2. Mở trang đã đăng nhập, bấm biểu tượng Cookie-Editor, chọn **Export** rồi **JSON**. Cookie được chép vào bộ nhớ tạm.
3. Trong Javis vào thanh bên, nhóm **Kết nối**, mục **Cookies** (biểu tượng bánh quy). Bấm **Thêm cookie**.
4. Đặt tên dễ nhớ (ví dụ "Shopee bán hàng"), dán cookie vào ô, bấm **Lưu và kiểm tra**.

Đã có file cookie (Cookie-Editor xuất ra file JSON, hoặc `cookies.txt` từ tiện ích Get cookies.txt LOCALLY) thì bấm **Tải file lên** ở đầu trang, hoặc nút **Chọn file** trong form, hoặc kéo file thả vào ô. Javis đọc file ngay trên trình duyệt, tự điền tên theo tên file nếu ô Tên còn trống. File tối đa 1 MB.

Javis cũng nhận nội dung file `cookies.txt` và chuỗi `tên=giá trị; ...` (lúc đó điền thêm ô Trang web, ví dụ `shopee.vn`).

## Mỗi thẻ cho biết gì

| Phần | Nghĩa |
|---|---|
| **Còn đăng nhập** | Lần kiểm gần nhất mở được trang mà không bị đẩy về màn đăng nhập |
| **Đã hết hạn** | Trang chuyển về màn đăng nhập hoặc trả lỗi 401/403 |
| **Lỗi tải trang** | Không tải được trang (mạng, trang sập). Chưa chắc đã hết hạn |
| **Hạn tới / Còn N ngày** | Theo ngày hết hạn ghi trong cookie |
| **Cho Javis dùng** | Tắt đi thì AI và mục theo dõi không dùng đăng nhập này nữa, cookie vẫn giữ |

Nút **Kiểm tra** mở **trang kiểm tra** bằng đăng nhập đó. Mặc định là trang chủ của tên miền; đổi trong nút ba chấm sang một trang chỉ xem được khi đã đăng nhập (ví dụ trang đơn hàng) thì kết quả chính xác hơn. Nút **Cập nhật** để dán cookie mới khi phiên hết hạn.

## Javis dùng đăng nhập ở đâu

- **Trong chat:** mọi engine có tool `javis_login`. Nói "xem giúp anh trang đơn hàng Shopee" kèm link, Javis mở trang bằng đăng nhập đã cất và đọc nội dung. Đăng nhập hết hạn thì Javis nói thẳng và nhờ bạn cập nhật, không thử lại mãi.
- **Theo dõi trang:** form ở tab Theo dõi trang (trang Việc định kỳ) có ô **Đăng nhập**. Chọn một đăng nhập là Javis canh được trang cần đăng nhập. Phiên hết hạn thì mục theo dõi tự tạm dừng và báo bạn một lần.

Javis chỉ **đọc** trang (tải trang về và lấy chữ). Nó không bấm nút, không gửi form, không đăng bài bằng đăng nhập này. Trang dựng hoàn toàn bằng JavaScript có thể ra ít chữ.

## An toàn

- Cookie được **mã hoá** trên máy chủ. Máy chưa mã hoá được (thiếu thư viện `cryptography`) thì Javis từ chối lưu chứ không ghi trần ra đĩa.
- **AI không bao giờ thấy giá trị cookie.** Tool chỉ trả nội dung trang và tên đăng nhập.
- Cookie chỉ được gửi tới đúng tên miền nó thuộc về, kiểm lại ở **mọi bước chuyển hướng**: trang chuyển sang site khác thì cookie không đi theo.
- Trang Cookies đòi **đăng nhập dashboard thật**: API token không đọc hay thêm được đăng nhập.
- **Chatbot trả lời khách không thấy tool này.**

## Lưu ý thật

- Cookie là chìa khoá vào tài khoản. Đừng dán cookie của người khác, đừng gửi cookie cho ai.
- Facebook và Google hay bắt xác minh khi phiên được dùng từ IP khác với lúc đăng nhập (ví dụ Javis chạy trên VPS). Các trang nhỏ hơn thường dễ tính hơn.
- Phiên nào cũng có lúc hết hạn. Khi đó đăng nhập lại trên trình duyệt, xuất cookie và bấm **Cập nhật**.
- Trang nào có API hoặc MCP chính thức (Facebook Ads, Gmail, Lịch) thì nên dùng đường đó, bền và an toàn hơn cookie.

## Chi tiết kỹ thuật

Module `server/login_vault.py`, kho `login_vault.sqlite3` trong thư mục dữ liệu (quyền 600), route `/logins` và `/logins/action`, tool `javis_login` (plugin `javis-login`, mức `readonly`, nằm trong `OWNER_ONLY_TOOLS`), trang `dashboard/login-vault.js`. Mục theo dõi trang có thêm cột `login_id`.
