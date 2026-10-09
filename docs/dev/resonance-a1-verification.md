# Resonance A1: biên bản nghiệm thu (08/10/2026)

Mốc A1 của lộ trình [agent scope](../superpowers/specs/2026-10-08-resonance-agent-scope-roadmap.md): Cộng hưởng bật theo từng trợ lý, mục tiêu gắn đúng trợ lý, tiến độ tối thiểu trên trang Cộng sự.

**Trạng thái: đã phát hành 0.87.0 (09/10/2026).** PR #590 squash vào `main` thành `fdfec7c5c84c2663276d088194844e058d9a22aa` (cây trùng head đã review `077bcf73`). CI và build Docker xanh; image `ghcr.io/blogminhquy/javis-os:0.87.0` (`sha256:bb437e0d0bfb...`).

## Mã và commit

- **PR:** #590, nhánh `claude/resonance-a1-agent-scope`, VERSION 0.87.0.
- **Gốc:** `origin/main` `71f9c5b9` (0.86.2). Nhánh đã chứa gốc này, không cần gộp thêm.
- **Review mã đạt:** `cc79deb2`.
- **Sau review mã:** `e01eb3c2` chỉ thêm test hồi quy, `e0a60352` chỉ thêm hồ sơ pilot. Commit cuối của nhánh chỉ sửa tài liệu.

## Bảng nghiệm thu

| Điều kiện (thiết kế A1) | Kết quả | Bằng chứng |
|---|---|---|
| Công tắc theo từng trợ lý, không còn công tắc theo brain | Đạt | `test_resonance_a1_registry.py`, `test_resonance_a1_transport.py` |
| Chat thường không lập được mục tiêu | Đạt | `test_resonance_a1_turn_agent.py`; pilot S0b: 403 |
| Mục tiêu gắn đúng trợ lý của phiên, phiên mở trước khi cấp mã bị chặn | Đạt | `test_resonance_a1_turn_agent.py`; pilot S1 |
| Tắt, xoá, mất file, đổi phiên bản trợ lý đều chặn ở mọi cửa (scheduler, bàn giao, đăng, phép thử) | Đạt | `test_resonance_a1_gates.py`, M2 đến M5 cập nhật |
| Đầu ra cũ được đăng lại sau khi bật lại mà không gọi model | Đạt | `test_resonance_a1_gates.py` |
| Phép thử hỏng kho trước khi gọi model thì hoàn lượt, sau khi gọi thì giữ lượt | Đạt | `test_resonance_mvp_trial.py` (mục 7d08, cc79) |
| Mục tiêu cũ sang Chờ gán, gán một lần | Đạt | `test_resonance_a1_registry.py`, `POST /goals/{id}/assign` |
| Quay về 0.86.1 trên kho đã nâng | Đạt | `test_resonance_a1_rollback.py` chạy mã 0.86.1 thật |
| Giao diện tối thiểu (công tắc, khung mục tiêu, Chờ gán, cảnh báo engine) | Đạt | `tests/js/test_resonance_a1_ui.js` |
| Pilot thật trong phiên trợ lý | Đạt kỹ thuật và nội dung, một kịch bản | [hồ sơ pilot](resonance-mvp-e2e-pilot-plan.md), mục A1-1 và hậu kiểm |

## Test đã chạy

- **Cục bộ, trên cây hiện tại:** `tests/run.py resonance turn_ route_table plugin hub chat_disconnect workflow agent settings`. **64/64 xanh** (57 Python, 7 JS), 228 giây.
- **CI:** xanh trên `e0a60352`. Commit cuối chỉ sửa tài liệu; xem PR cho CI của head cuối.
- Chưa chạy toàn bộ bộ test Python trên máy này. Trên máy này có sẵn khoảng 14 file đỏ giả, đỏ cả trên main sạch. CI là nơi chạy đủ.
- Test xanh không thay cho review độc lập. Review mã do người review làm riêng, ở `cc79deb2`.

## Pilot A1-1

- Chạy một lần, đúng gói đã duyệt, tại `e01eb3c2`.
- 2 lượt chat Opus, 0 lượt việc nền Sonnet, trên trần 4. Dùng gói thuê bao Claude Code, không dùng API trả phí.
- Xác nhận cuối S6 là mô phỏng qua API.
- Nội dung đạt: bản đầu 4/4, bản sửa 3/3.
- Hai góp ý câu chữ không chặn, ghi ở mục hậu kiểm. File bằng chứng giữ nguyên bytes.

## Giới hạn còn lại

- Một kịch bản thành công chưa phải tỷ lệ ổn định. Chưa đo trên Codex, các engine API, Grok, Antigravity.
- Đường việc nền tự sửa bản bằng model thật chưa được dùng ở pilot A1.
- Codex và engine API: lập được mục tiêu, nhưng bản viết trong chat chưa được nhận làm sản phẩm (để A4).
- Grok và Antigravity: chưa lập được mục tiêu.
- Chưa kiểm trên VPS (D0). Độ chậm qua Cloudflare là đường mạng, xử lý riêng ở PR #592 và phía hạ tầng.

## Tài liệu cho người dùng

- [Cách dùng, nâng cấp, quay về, khôi phục](resonance-a1-migration.md).
- [Thiết kế A1](../superpowers/specs/2026-10-08-resonance-a1-agent-scope-design.md).
- [Kế hoạch tích hợp](../superpowers/plans/2026-10-08-resonance-a1-integration-plan.md).
