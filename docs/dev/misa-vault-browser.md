# Cầu nối render AMIS: nền tảng thử nghiệm, chưa dùng production

Cầu nối trong `server/login_browser.py` chỉ được gọi bởi `javis_login op=render_misa`.
Danh tính chủ lấy từ `turn_context` do host xác thực, không nhận cờ owner từ model.
Cần `JAVIS_MISA_BROWSER_ENABLED=1` ở server. Không tự bật cờ này khi cài hay cập nhật.

Hai URL đầu vào cố định: `https://amisapp.misa.vn/warehouse/stock-management/stock-list`
và `https://amisapp.misa.vn/warehouse/deskwork`. Tên đăng nhập mặc định `Kho Molli`.
Kiểm allow_ai, thời hạn và phạm vi cookie trước khi tạo browser. Cookie và origins được
đọc trong tiến trình server từ vault đã mã hóa, đưa thẳng vào context không bền vững;
không có endpoint hay file xuất storage state, HAR, ảnh hoặc protocol trace.

## Hàng rào mạng

Trình duyệt dùng proxy không hoạt động làm đường dự phòng đóng. Mọi HTTP request phải
qua route của context. Route chỉ phục vụ request khớp chính xác bộ `MISA_RULES` phía server.
WebSocket đóng, service worker tắt, download tắt, không click hoặc gửi form.
Transport stdlib chỉ nhận HTTPS tới đúng host, cổng 443; kiểm toàn bộ kết quả DNS là IP công
khai rồi kết nối tới IP số vừa kiểm, giữ hostname gốc cho TLS. Không dùng proxy môi trường,
không theo redirect, không trả chi tiết exception hoặc header. Không mặc định cho phép GET API:
GET có thể gây side effect. Mỗi rule cần kiểm chứng nghiệp vụ trước khi thêm.

## Phần chưa hoàn thành

`MISA_RULES` hiện chỉ có hai document được yêu cầu. CHƯA có manifest asset JavaScript/CSS
hay API đọc kho đã được xác minh. Vì vậy trang thật dự kiến bị chặn và KHÔNG được coi là đã
đọc kho. Không mở wildcard theo miền hay đuôi file để vượt chặn. Không chuyển POST thành GET,
không cho phép POST chỉ vì payload có vẻ là truy vấn.

Cần staging được quản trị cho phép, cơ chế triển khai từ fork và bộ endpoint đọc được xác minh
(tài liệu MISA hoặc quan sát phía server được quản trị, chỉ xuất phương thức/đường dẫn đã lọc,
không xuất query chứa bí mật, headers, body hay storage). Sau đó bổ sung rule chính xác và
kiểm thử tích hợp đọc dữ liệu kho thực tế. API có POST phải có adapter nghiệp vụ riêng được
kiểm duyệt về side effect, không mở POST chung.

Chặn output chứa giá trị cookie/localStorage đã biết, cả URL/base64. Đây là phòng vệ với bí mật
đầu vào, chưa chứng minh an toàn với token mới do JavaScript tạo hoặc mọi kiểu mã hóa tùy ý.
Trước production cần bộ trích xuất bảng kho có schema cố định thay vì xuất toàn bộ body text,
đánh giá token mới, xác minh timeout/cancellation và cơ chế cô lập mạng ở hạ tầng.

## Kiểm thử

Test unit dùng credential tổng hợp. Kiểm thử browser thật cần môi trường riêng:

```
JAVIS_BROWSER_INTEGRATION=1 PLAYWRIGHT_BROWSERS_PATH=<test-browser-dir> python tests/python/test_login_browser.py
python tests/python/test_login_vault.py
python tools/release.py check
```

Test browser dùng transport giả phục vụ HTML có JavaScript, không kết nối MISA. Không dùng
kho bí mật thật cho test. Context và browser đóng ở finally cả khi render lỗi.
Tài liệu nền: https://playwright.dev/python/docs/api/class-browsercontext
