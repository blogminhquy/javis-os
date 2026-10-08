# D0: kiểm bản 0.86.0 trên localhost (08/10/2026)

**Mức bằng chứng: vận hành cục bộ.** Đây KHÔNG phải kiểm VPS, cũng không phải kiểm server đang chạy ở cổng 7777 của máy chủ dự án. VPS chưa kiểm vì kết nối Hostinger trong phiên làm việc bị ngắt.

| Mục | Giá trị |
|---|---|
| Mã chạy | Worktree sạch tách từ commit phát hành `438f83097db4ee64e96b7b4880deb581521f217a` (VERSION 0.86.0). Lúc kiểm, `main` đã lên 0.86.1 (#589) nhưng bản kiểm cố ý ghim 0.86.0 |
| Cách chạy | `python server/main.py` của worktree đó, cổng 7788, `JAVIS_STATE_DIR` và `BRAINS_DIR` tạm, `JAVIS_REQUIRE_LOGIN=0`, môi trường bỏ biến `CLAUDE*` / `ANTHROPIC*` của phiên Claude Code (giữ `CLAUDE_CONFIG_DIR`) |
| Claude Code trên máy | 2.1.293 (cùng bản build vào image Docker 0.86.0) |
| Script | `exports/reviews/D0-localhost-0860-smoke.py` (ngoài git). Log server và thư mục dữ liệu tạm đã xoá khi dọn; kết quả dưới đây chép từ đầu ra của lần chạy |

## Kết quả không gọi model: 13/13

1. Khởi động sạch, `/health` 200 sau 7 giây.
2. Dashboard `/` trả 200; `/app-version` báo `0.86.0`; asset gắn `?v=0.86.0`.
3. Công tắc Resonance mặc định tắt (`{"ok": true, "enabled": false}`).
4. WebSocket `/ws` nhận kết nối qua kiểm Origin.
5. Tắt tính năng, mở dashboard, chờ hơn một nhịp scheduler (35 giây): không tạo `resonance.sqlite3`.
6. Log server không có Traceback hay lỗi `[resonance`.
7. Bật Resonance cho brain tạm qua API.
8. Khởi động lại sau 7 giây.
9. Sau khởi động lại công tắc vẫn bật (giữ trong brain).
10. API danh sách mục tiêu chạy, trả rỗng.
11. Bật và qua một nhịp scheduler: log không lỗi.
12. Tắt lại Resonance.
13. WebSocket vẫn nhận kết nối sau khởi động lại.

Ghi chú:
- Gọi thẳng `GET /resonance/goals` thì kho `resonance.sqlite3` được tạo dù tính năng tắt. Đây là chủ ý của M4 (xem và dừng mục tiêu cũ không đòi công tắc). Dashboard không tự gọi API này.
- Trong trình duyệt, `/tools/optional` trả 401. Endpoint này đòi phiên đăng nhập, mà server thử tắt đăng nhập; không thuộc thay đổi Resonance.

## Một lượt chat thật: đạt

- Người dùng duyệt đúng 1 lượt. Engine chép từ settings thật chỉ phần chọn engine: `anthropic-cli` / `claude-opus-5-5`, gói Max; token còn khoảng 15.400 giây trước khi gửi.
- Tin: "Chào Javis, đây là tin thử sau khi nâng cấp. Em trả lời ngắn một câu: em đang chạy phiên bản nào và bằng bộ não gì?"
- Kết quả sau 10 giây: khung `turn_done` có `engine_status: ok`, `turn_status: completed`, không có lỗi engine. Câu trả lời nêu đúng Claude Code và `claude-opus-5-5`, nói không thấy số phiên bản trong ngữ cảnh nên không báo.
- Hội thoại được lưu vào danh sách phiên. Log server không có Traceback.

## Chưa có bằng chứng

- Một VPS cụ thể đã kéo image 0.86.0 và chạy ổn (phiên bản, chat, dữ liệu sau restart, log lỗi).
- Bật thử Cộng hưởng trên brain hoặc agent thật với việc thật.
