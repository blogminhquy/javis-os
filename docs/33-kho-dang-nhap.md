# 33 - Cookies (Kho đăng nhập)

***Tiếng Việt** · [English](en/33-login-vault.md)*

Từ 0.251.0 Javis có trang **Cookies** (trước 0.261.0 tên là Kho đăng nhập): chỗ cất phiên đăng nhập riêng của bạn (cookie) để Javis dùng lại. Bạn đăng nhập một lần trên trình duyệt của mình, đưa cookie cho Javis, rồi Javis đọc được những trang chỉ hiện khi đã đăng nhập: kênh người bán Shopee, trang affiliate, trang quản trị web. Từ 21/11/2026 Javis còn **bấm nút và điền form** được bằng phiên đó.

Kho này là tuỳ chọn. Không thêm đăng nhập nào thì Javis chạy y như cũ.

## Thêm một đăng nhập

1. Cài tiện ích **Cookie-Editor** cho Chrome hoặc Edge.
2. Mở trang đã đăng nhập, bấm biểu tượng Cookie-Editor, chọn **Export** rồi **JSON**. Cookie được chép vào bộ nhớ tạm.
3. Trong Javis vào thanh bên, nhóm **Kết nối**, mục **Cookies** (biểu tượng bánh quy). Bấm **Thêm cookie**.
4. Đặt tên dễ nhớ (ví dụ "Shopee bán hàng"), dán cookie vào ô, đọc dòng **cảnh báo rủi ro** ngay trên nút lưu, rồi bấm **Lưu và kiểm tra**.

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
| **Cho bấm và điền form** | Bật thì Javis được thao tác thật bằng đăng nhập này trong trình duyệt. Tắt thì Javis chỉ đọc |
| **Đang có trong trình duyệt của Javis** | Phiên này đang nằm trong trình duyệt mà Javis lái |

Nút **Kiểm tra** mở **trang kiểm tra** bằng đăng nhập đó. Mặc định là trang chủ của tên miền; đổi trong nút ba chấm sang một trang chỉ xem được khi đã đăng nhập (ví dụ trang đơn hàng) thì kết quả chính xác hơn. Nút **Cập nhật** để dán cookie mới khi phiên hết hạn.

## Javis dùng đăng nhập ở đâu

- **Trong chat:** mọi engine có tool `javis_login`. Nói "xem giúp anh trang đơn hàng Shopee" kèm link, Javis mở trang bằng đăng nhập đã cất và đọc nội dung. Đăng nhập hết hạn thì Javis nói thẳng và nhờ bạn cập nhật, không thử lại mãi.
- **Theo dõi trang:** form ở tab Theo dõi trang (trang Việc định kỳ) có ô **Đăng nhập**. Chọn một đăng nhập là Javis canh được trang cần đăng nhập. Phiên hết hạn thì mục theo dõi tự tạm dừng và báo bạn một lần.
- **Bấm nút và điền form:** nói "vào kênh người bán Shopee, điền form trả lời đánh giá này giúp anh". Javis nạp đăng nhập vào trình duyệt, mở trang rồi thao tác như một người dùng.

Đọc trang (hai mục đầu) chỉ tải trang về và lấy chữ, nên trang dựng hoàn toàn bằng JavaScript có thể ra ít chữ. Cần bấm, cần gõ, hoặc trang nặng JavaScript thì Javis dùng trình duyệt.

## Bấm nút và điền form bằng trình duyệt

Cần ba thứ:

1. **Kết nối Playwright** ở trang Kết nối (đây là trình duyệt mà Javis lái). Chưa có thì Javis nói thẳng là thiếu.
2. Công tắc **Cho bấm và điền form** ở thẻ đăng nhập đang bật. Đăng nhập thêm mới thì bật sẵn. Đăng nhập đã cất từ trước bản này thì **tắt sẵn**, vì lúc bạn cất Javis mới chỉ đọc: bật lên Javis sẽ hỏi lại bạn một lần.
3. Lượt chạy ở mức **Toàn quyền**. Việc nền đặt mức nhẹ hơn (chỉ đọc, chỉ viết nháp) không mở được trình duyệt đã đăng nhập.

Javis nạp cookie thẳng vào trình duyệt qua chính kết nối Playwright: không ghi file cookie nào ra đĩa, không phải khởi động lại kết nối.

Vài điều Javis tự lo:

- **Phiên tự gia hạn không bị đè.** Nhiều trang đổi cookie trong lúc dùng. Lần mở sau Javis chỉ bù cookie còn thiếu, không ghi bản cũ trong kho đè lên bản mới của trình duyệt. Sau mỗi lần vào trang thành công, bản mới được lưu ngược về kho (vẫn mã hoá), nên đọc trang và theo dõi trang cũng dùng được phiên đã gia hạn.
- **Dán cookie mới** (nút Cập nhật) thì lần mở kế tiếp thay hẳn bản trong trình duyệt.
- **Hai tài khoản cùng một trang** (hai shop Shopee): trình duyệt mỗi lúc chỉ giữ một. Gọi tài khoản nào thì Javis thay sang tài khoản đó.
- **Tắt công tắc hoặc Xoá** thì Javis gỡ luôn phiên đó khỏi trình duyệt. Gỡ không được, Javis báo ngay để bạn tự đăng xuất trên trang web.

## An toàn

- Cookie được **mã hoá** trên máy chủ. Máy chưa mã hoá được (thiếu thư viện `cryptography`) thì Javis từ chối lưu chứ không ghi trần ra đĩa.
- **Tool của Javis không bao giờ trả giá trị cookie cho AI.** Tool chỉ trả nội dung trang và tên đăng nhập, kể cả khi trình duyệt báo lỗi.
- Cookie chỉ được gửi tới đúng tên miền nó thuộc về, kiểm lại ở **mọi bước chuyển hướng**: trang chuyển sang site khác thì cookie không đi theo.
- Trang Cookies đòi **đăng nhập dashboard thật**: API token không đọc hay thêm được đăng nhập.
- **Chatbot trả lời khách không thấy tool này.** Và từ lúc trình duyệt đã từng giữ một đăng nhập của bạn, chatbot trả lời khách cũng **không còn dùng được kết nối trình duyệt đó**, để người lạ không lướt web bằng tài khoản của bạn.

## Lưu ý thật

- Cookie là chìa khoá vào tài khoản. Đừng dán cookie của người khác, đừng gửi cookie cho ai.
- **Rủi ro do bạn tự chịu.** Khi được phép bấm và điền form, Javis làm việc thật bằng tài khoản của bạn: gửi form, đăng bài, đặt hàng, đổi cài đặt, và việc đã làm không hoàn tác được. Nên dùng một tài khoản riêng cho Javis thay vì tài khoản chính.
- Một trang web có thể chứa chữ cố ý xúi AI làm việc ngoài ý bạn. Javis coi nội dung trang là dữ liệu chứ không phải lệnh, nhưng không có lớp chặn nào tuyệt đối.
- Khi Javis lái trình duyệt đã đăng nhập, AI thấy mọi thứ trong phiên đó như một người ngồi trước máy.
- Dịch vụ có thể bắt xác minh hoặc khoá tài khoản khi thấy phiên bị điều khiển tự động, và nhiều dịch vụ cấm việc này trong điều khoản.
- Facebook và Google hay bắt xác minh khi phiên được dùng từ IP khác với lúc đăng nhập (ví dụ Javis chạy trên VPS). Các trang nhỏ hơn thường dễ tính hơn.
- Phiên nào cũng có lúc hết hạn. Khi đó đăng nhập lại trên trình duyệt, xuất cookie và bấm **Cập nhật**.
- Trang nào có API hoặc MCP chính thức (Facebook Ads, Gmail, Lịch) thì nên dùng đường đó, bền và an toàn hơn cookie.

## Chi tiết kỹ thuật

Module `server/login_vault.py`, kho `login_vault.sqlite3` trong thư mục dữ liệu (quyền 600), route `/logins` và `/logins/action`, tool `javis_login` (plugin `javis-login`: `list` và `fetch` mức `readonly`, `browser` mức `full`; nằm trong `OWNER_ONLY_TOOLS`), trang `dashboard/login-vault.js`. Mục theo dõi trang có thêm cột `login_id`. Phần trình duyệt nằm ở `server/browser_login.py`: nạp, đọc và xoá cookie qua tool chạy mã của kết nối Playwright (`browser_run_code_unsafe`), hai cột `allow_act` và `browser_at` trong kho, và `mcp_hub.discover_all` bỏ kết nối trình duyệt khỏi danh sách tool của chatbot khách.
