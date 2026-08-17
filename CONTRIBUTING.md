# Đóng góp cho Javis OS

Cảm ơn bạn đã muốn đóng góp. Repo này nhận Pull Request từ **fork** - bạn không cần quyền
ghi trực tiếp, chỉ cần fork về tài khoản của mình, code, rồi mở PR nhắm vào nhánh `main`.

## Quy trình

1. **Fork** repo này, clone bản fork về máy.
2. Tạo nhánh mới đặt tên gợi nhớ việc đang làm (vd `fix-zoom-mobile`, `them-mcp-notion`).
3. Code, rồi tự chạy test trước khi mở PR (xem mục Test bên dưới) - PR chưa chạy test
   local dễ vướng lỗi vặt mà CI mới bắt được.
4. Mở PR nhắm vào `main` của repo gốc (`blogminhquy/javis-os`), mô tả rõ **vì sao** cần
   thay đổi này, không chỉ **cái gì** đã đổi (cái gì thì đọc diff là thấy).
5. CI (GitHub Actions) tự chạy. PR xanh + được duyệt mới merge - không có merge tự động,
   người giữ repo sẽ tự xem qua từng PR.

## Chạy test trước khi mở PR

```bash
pip install -r requirements.txt
python tests/run.py          # chạy hết (Python + JS)
python tests/run.py --py     # chỉ Python
python tests/run.py --js     # chỉ JS
```

Script tự tìm `.venv` nếu có, chạy được từ bất kỳ thư mục nào trong repo.

## Quy ước code

Dự án theo các quy ước ghi trong `CLAUDE.md` ở gốc repo (dùng cho cả người lẫn AI agent
làm việc trên repo) - đáng đọc qua trước khi sửa nhiều, đặc biệt các mục:

- Không thêm tính năng/refactor ngoài phạm vi PR đang làm.
- Comment chỉ viết khi giải thích **vì sao** (constraint ẩn, workaround), không lặp lại
  cái code đã nói (**cái gì**).
- `CHANGELOG.md` viết cho người đọc trên điện thoại: vài gạch đầu dòng, nói người dùng
  **thấy gì khác**, không kể tên hàm/đường dẫn file (chi tiết kỹ thuật để trong PR).
- Không dùng ký tự em dash (—); thay bằng dấu gạch nối `-`.

## Báo lỗi / đề xuất tính năng trước khi code

Với thay đổi nhỏ, cứ mở PR thẳng. Với tính năng lớn hoặc đổi kiến trúc, nên mở **Issue**
mô tả trước để bàn hướng làm - tránh trường hợp code xong mà hướng không khớp với dự án.

## Vấn đề bảo mật

Đừng báo lỗi bảo mật qua Issue công khai. Liên hệ trực tiếp với người giữ repo.
