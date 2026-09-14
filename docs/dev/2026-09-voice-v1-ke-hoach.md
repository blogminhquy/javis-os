# Voice V1 - kế hoạch task (VOICE_V1_TASK_PLAN)

> Kèm `2026-09-voice-v1-spec.md`. Mỗi task nhỏ, có tiêu chí nghiệm thu, ghi phụ thuộc.
> Thứ tự dưới đây là thứ tự làm thật ngày 2026-09-14; trạng thái cập nhật ở cột cuối.

| # | Task | Phụ thuộc | Nghiệm thu | Trạng thái |
|---|---|---|---|---|
| S1 | `server/ui_bridge.py`: request/resolve/has_clients, hết giờ 4 s | - | `test_ui_bridge.py` xanh | làm |
| S2 | `/ws` nhận `ui_result` và gọi `ui_bridge.resolve`; main gắn runtime | S1 | test regex trong `test_ui_bridge.py` | làm |
| S3 | Plugin `system/plugins/javis-ui` (tool `javis_ui`) | S1 | `plugins_host.describe` thấy plugin, target lạ bị chặn | làm |
| S4 | Plugin `system/plugins/desktop-apps` (list/open/close) | - | `test_desktop_apps_plugin.py` xanh, không mở gì thật | làm |
| S5 | `GET /tts` Edge streaming + `Accept-Ranges: none` | - | `test_tts_stream.py` xanh | làm |
| S6 | Khối kênh web: 6 dòng về javis_ui, app, ngữ cảnh giao diện | - | `test_channel_ui_prompt.py` | làm |
| S7 | `sessions.py` lột `[NGỮ CẢNH GIAO DIỆN` khỏi tiêu đề | - | test tiêu đề | làm |
| F1 | `dashboard/voice-turn.js` đạo diễn thuần | - | `test_voice_turn.js` xanh | làm |
| F2 | `dashboard/ui-context.js` dựng khối ngữ cảnh | - | `test_ui_context.js` | làm |
| F3 | `dashboard/ui-actions.js` nhận `ui_action`, kiểm, chạy, ack | S2 | `test_ui_actions.js` | làm |
| F4 | `voice.js`: chen ngang 5 nhịp + pause/resume, phần đã đọc, đo mạng chậm, nối đạo diễn | F1 | 4 test mic cũ + `test_orb_trang_thai_that.js` | làm |
| F5 | `app.js`: orb theo đạo diễn, reconnecting, tool_call, hoãn tin nền, gửi khối ngữ cảnh, ack ui | F1-F4 | test orb | làm |
| F6 | `console.js` xuất `JavisKanbanShow`; index.html nạp module mới, bump `?v=`; CSS orb; i18n vi/en; 2 hàng Cài đặt nhanh | F3, F5 | mở dashboard bấm mic chạy được | làm |
| D1 | CHANGELOG, VERSION 0.56.0, docs/dev/README, docs/02 người dùng | tất cả | CI xanh, merge main | làm |

Kịch bản nghiệm thu tay (trên máy Windows của chủ dự án, Chrome):
1. Bấm mic, nói "mở trang Việc" → orb ĐANG NGHE → ĐANG SUY NGHĨ → ĐANG GỌI javis_ui → trang Việc mở, Javis nói "đã mở".
2. Nói "khoan" khi Javis đang đọc → dừng đọc, orb ĐANG CHỜ BẠN, không gửi gì; nói tiếp câu thật → gửi.
3. Ho một tiếng khi Javis đang đọc → audio dừng 2 giây rồi đọc tiếp.
4. Nói chen một câu thật → Javis dừng hẳn, tin kế tiếp mang ngắt_lời.
5. Nói "mở Chrome" → Chrome mở. "Đóng Chrome" → Chrome đóng (hỏi lưu nếu có tab dở).
6. Rút mạng → orb ĐANG KẾT NỐI LẠI; cắm lại → SẴN SÀNG.
