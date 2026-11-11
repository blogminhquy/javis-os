# Nhóm chat team T0: công tắc Cộng hưởng trên dòng trợ lý (0.110.0)

Spec: [2026-10-13-team-chat-design.md](../superpowers/specs/2026-10-13-team-chat-design.md) mục 10 (D1 tới D7 đã chốt). Kế hoạch: [2026-10-13-team-chat-t0-t1.md](../superpowers/plans/2026-10-13-team-chat-t0-t1.md) phần T0.

## Thay đổi

- **Trang Cộng sự** (`dashboard/workspace.js`):
  - Đọc `GET /resonance/agents` một lần, cùng lượt với `/agents`. Request này lỗi thì danh sách vẫn hiện và dòng không có công tắc (không đoán trạng thái).
  - Mỗi dòng trợ lý có "Cộng hưởng: Bật/Tắt" và công tắc (`rowToggleHtml`). Công tắc nằm ngoài nút chọn mục.
  - Trợ lý `missing` hay `retired` có nút "Cần xác nhận" / "Đã nghỉ", mở cột phải ở tab Cài đặt, nơi có hai nút xác nhận của A1.
- **Bấm công tắc** (`toggleAgent` trong `dashboard/resonance-agent.js`):
  - gọi đúng `POST /resonance/agents/toggle` của A1, không kèm `session_id`;
  - khoá trong lúc chờ; chỉ đổi khi server trả `ok`;
  - lỗi thì nói lý do dưới thanh lọc và tải lại trạng thái thật;
  - tắt trợ lý còn mục tiêu mở thì hỏi lại, kèm số mục tiêu.
- **Một nơi duy nhất:**
  - bảng Cộng hưởng ở cột phải chỉ còn chữ trạng thái và dòng "Bật, tắt ở danh sách trợ lý bên trái";
  - trang Cài đặt chỉ còn tóm tắt "N trợ lý đang bật Cộng hưởng", nút sang trang Cộng sự, danh sách trợ lý cần xác nhận bằng chữ, mục mồ côi, Chờ gán, ghi chú brain cũ.
- **Đồng bộ hai tab:**
  - route bật, tắt và xác nhận phát gói WS `{"type": "resonance_agents"}` (`ResonanceApiDeps.broadcast` gọi `ChatRuntime.publish`); lỗi của gói này không làm hỏng lệnh của chủ;
  - `app.js` đổi gói thành sự kiện `javis:resonance-agents-changed`; trang Cộng sự, bảng bên phải và trang Cài đặt tải lại trạng thái thật.
- **`.gitignore`:** thêm `server/resonance.sqlite3*` và `server/team.sqlite3*`, vì server chạy từ worktree mà không đặt `JAVIS_STATE_DIR` sẽ ghi các kho này vào `server/`.
- **Hợp đồng A1 giữ nguyên:** chỉ chủ đổi được; `missing` cần xác nhận; tắt luôn được; trạng thái của phiên đang mở vẫn do bảng bên phải hỏi host (`session_id` ở `GET`).
  Từ 2026-11-11 host tự nhận lại mã `missing` trong hai trường hợp không có gì để quyết, xem [auto-agent-restore.md](auto-agent-restore.md).

## Kiểm

| Lệnh | Kết quả |
|---|---|
| `python tests/run.py team_t0 resonance_a1 resonance_a5_ui workspace i18n route_table ignore_files` | 18/18 xanh |
| `tests/js/test_team_t0_toggle.js` | Trạng thái bằng chữ; công tắc trên dòng; `missing`/`retired` không có ô bật; đang lưu thì khoá; không có dữ liệu thì không vẽ; chống chèn HTML; hỏi lại khi tắt; bảng bên phải và trang Cài đặt không còn công tắc; `toggleAgent` với 200, 409, rớt mạng; dây nối ở trang Cộng sự, `app.js`, CSS |
| `tests/python/test_team_t0_broadcast.py` | Bật, tắt phát đúng một gói; 404 không phát; gói lỗi thì lệnh vẫn thành công |

**Smoke giao diện** (sandbox cổng 7788, state trong worktree, không lượt model nào). Ảnh ở `exports/reviews/team-t0-smoke/`, ngoài repo.
- Dòng hiện "Cộng hưởng: Tắt"; tên có ký tự HTML hiện nguyên văn.
- Bật Lan: đổi sang "Bật" sau khi server xác nhận.
- Cột phải chỉ còn chữ trạng thái.
- Tab thứ hai tự đổi khi tab đầu bật Minh, không F5.
- Chuyển file của Lan đi rồi trả lại: dòng ghi "Cần xác nhận"; bấm "Đúng trợ lý cũ" thì cả hai tab cùng về "Bật".
- Trang Cài đặt hiện "2 trợ lý đang bật Cộng hưởng.", không còn công tắc.
- Khung 510px: cột trái thành ngăn kéo, công tắc vẫn dùng được.

## Giới hạn

- Hộp hỏi lại khi tắt trợ lý còn mục tiêu mở chỉ được kiểm bằng test đơn vị: sandbox không có mục tiêu nào.
- Danh sách thành viên nhóm (spec mục 10.1) chưa có: thuộc T1.
