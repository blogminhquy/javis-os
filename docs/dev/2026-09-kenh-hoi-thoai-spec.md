# Sổ đăng ký kênh, tài khoản kênh và trang Hội thoại gộp (0.61.0)

Tài liệu kỹ thuật cho người sửa lõi. Người dùng đọc `docs/28-hoi-thoai-khach.md` và `docs/25-chatbot.md`.

## Vì sao

Trước 0.61.0, "kiến thức về một kênh" nằm rải ở tám chỗ (`chatbot_store`, `chatbot_runtime`, `conversations`, `GET /chatbots`, route `/conversations/channels`, `icons.js`, `chatbots.js`, `conversations.js`). Thêm Zalo OA hay Facebook là sửa cả tám, và Zalo cá nhân là một "trường hợp đặc biệt" trong mỗi chỗ. Bot lại trộn hai thứ khác bản chất vào một bản ghi: TÀI KHOẢN (token, danh tính ở nền tảng) và PHÂN CÔNG (Agent, mức quyền). Chủ dự án yêu cầu (2026-09-21): gộp Chatbot và Hội thoại vào một tab, mọi kênh đối xử như nhau, và cấu trúc để thêm kênh sau này không đụng lõi.

## Ba lớp

1. **Sổ đăng ký kênh** `server/channels/`: mỗi kênh một module khai `SPEC: KenhSpec` (id, nhãn, logo, kind, năng lực, cách lấy token, tóm tắt) và một bộ hàm theo khế ước (xem docstring `channels/__init__.py`). Năng lực "trả lời từ Javis" và "gắn được bot" SUY từ module (có hàm `gui`, có `Transport`), không tin lời khai. Thứ tự `_MODULES` là thứ tự hiện trên giao diện; không có kênh nào "chính".
2. **Tài khoản kênh** `server/channel_accounts.py`: kho JSON cho tài khoản kind `bot` (token qua `secrets_store`). Tài khoản kind `account` (Zalo cá nhân) sống ở `mcp_store`, module kênh tự liệt kê. Id tài khoản di trú từ bot cũ = id bot, để khoá `f"{kenh}:{id}"` của kho hội thoại giữ nguyên.
3. **Bot** `server/chatbot_store.py`: chỉ còn PHÂN CÔNG, trỏ tới tài khoản qua `accounts: [id]`. `channel`/`bot_username` là ảnh của tài khoản đầu tiên (giữ cho chỗ đọc cũ). Di trú chạy trong `_load()` lần đọc đầu, ghi lại một lần, không cần script.

## Bộ giám sát

`chatbot_runtime._RUNNING[bot_id] = {"pollers": {account_id: transport}, ...}`: mỗi tài khoản một poller. Callback của poller được bọc bằng `_gan_tai_khoan` để MỌI meta mang `account_id`; `_su_kien_bot` ghi vào kho theo tài khoản đó, `che_do` (tiếp quản) cũng tra theo tài khoản đó. `status(bot_id)` trả trạng thái XẤU NHẤT làm trạng thái chung, kèm `accounts: [...]` từng poller.

## API

- `GET /channels`, `GET /channels/accounts` (một khuôn: `id`, `account_key`, `kind`, `channel`, `logo`, `label`, `state`, `watch`, `bot_id`, `so_hoi_thoai`, `chua_doc`, `nang_luc`, `xoa_duoc`).
- `POST /channels/verify-token`, `POST /channels/accounts`, `.../{id}/update`, `.../{id}/watch` (chỉ kind account, kind bot trả 400), `.../{id}/delete` (từ chối khi còn bot trực).
- `POST /conversations/{id}/reply`: gửi qua `channels.gui`, ghi tin `human`, cuộc có bot ở chế độ `ai` thì chuyển `human` (tiếp quản) và trả `tiep_quan: true`. Gửi hỏng thì 400 và KHÔNG ghi.
- Bí danh giữ lại: `/chatbots/verify-token`, `/conversations/channels`, `/conversations/zalo/{id}/watch`.
- `GET /chatbots` thêm `tai_khoan` (tài khoản rảnh) và `kenh` từ sổ; `POST /chatbots` và `/update` nhận `account_ids` (danh sách, phẩy) và vẫn nhận `token` + `channel` (tạo tài khoản mới rồi gắn).

## Giao diện

- `conversations.js` là vỏ trang: ba tab `TABS = ["inbox", "kenh", "chatbot"]`. Tab Chatbot uỷ quyền `JavisChatbots.render`. Id trang `chatbots` còn trong `RAIL_ITEMS` (icon, nhãn, bí danh giọng nói) nhưng nằm trong `RAIL_AN`; `navigateTo("chatbots")` gọi `JavisConversations.chonTab("chatbot", true)` rồi đi tới `conversations`.
- Luật: giao diện KHÔNG rẽ nhánh theo id kênh. Logo qua `kenhCua(id).logo`, nhãn qua `nhan`, năng lực qua `nang_luc`; tất cả từ `channels` server trả. Test `test_trang_chatbot.js` và `test_hoi_thoai_khach.js` có canary cho luật này.
- Thêm kênh: một file ở `server/channels/`, một dòng trong `_MODULES`, một logo trong `icons.js` (`KENH`). Không sửa gì khác.

## Kiểm thử

`tests/python/test_kenh_tai_khoan.py` (sổ, di trú, nhiều tài khoản, API, reply), `test_hoi_thoai_khach.py`, `test_chatbot_store.py`, `test_zalo_bot.py`; JS: `test_hoi_thoai_khach.js`, `test_trang_chatbot.js`.
