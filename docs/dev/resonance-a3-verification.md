# Resonance A3: biên bản kiểm mã (09/10/2026)

**Trạng thái:** mã A3 viết xong trên nhánh `claude/resonance-a3-feedback-learning` (PR #598, đặt số 0.89.0), **chờ review mã**. Thiết kế đạt review vòng 3 tại `d6239d54`. Chưa pilot model thật, chưa merge, chưa phát hành.

Thiết kế: [2026-10-09-resonance-a3-feedback-learning-design.md](../superpowers/specs/2026-10-09-resonance-a3-feedback-learning-design.md) (mục 13 là ma trận; mục 19 là ghi chú triển khai). Hướng dẫn: [resonance-a3-learning.md](resonance-a3-learning.md).

## Mã

| Phần | File |
|---|---|
| Chính sách thuần `learning.v1`, mục trình bày, tin bắt buộc, bộ học làn P | `server/resonance_learning.py` (mới) |
| Kho: năm bảng A3, hai chỉ mục bài học, sổ giữ lượt, CAS bài học trong giao dịch M5, đối soát lượt giữ | `server/resonance_store.py` |
| `heartbeat.v2`: lớp `FOLLOWUP`, `TRIAL` | `server/resonance_heartbeat.py` |
| Bộ tình huống do host dựng, phép thử trong lần thức A2, lượt làm sản phẩm, đường báo làn P, khối `learning` của thẻ | `server/resonance.py` |
| Route `/resonance/reactions`, `/resonance/lessons`, `/resonance/lessons/{id}/decision` | `server/resonance_api.py`, đăng ký ở cuối `server/main.py` |
| Tra biên nhận theo tin | `server/sessions.py` (`report_receipt_by_message`) |
| Giao diện | `dashboard/chat-resonance.js`, `dashboard/resonance-agent.js`, `dashboard/style.css`, `dashboard/i18n/vi.json`, `dashboard/i18n/en.json` (59 khoá mỗi thứ tiếng) |

## Test đã chạy (máy local, `.venv` của checkout gốc, không model thật)

| File | Kết quả |
|---|---|
| `tests/python/test_resonance_a3_learning.py` | 109 kiểm đạt |
| `tests/python/test_resonance_a3_api.py` (main.app, biên nhận thật) | 18 kiểm đạt |
| `tests/python/test_resonance_a3_rollback.py` (mã 0.88.1 thật, `83bff6bc`) | 11 kiểm đạt |
| `tests/js/test_resonance_a3_ui.js` | 24 kiểm đạt |
| 27 file test Resonance cũ (M1 tới M5, A1, A2), `test_route_table.py`, `test_version_khop_changelog.py`, `test_i18n.mjs`, ba test giao diện Resonance cũ | đều đạt |

Lệnh chạy lại:

```bash
python tests/run.py resonance -v
python tests/run.py --js resonance i18n
python tests/run.py route_table version_khop_changelog
```

## Đối chiếu ma trận (thiết kế mục 13)

**13.1, bộ tối thiểu theo GOAL:**

| Ca | Chỗ kiểm |
|---|---|
| G1 | `a3_learning` (reaction không mở lượt, không assessment, mục tiêu vẫn active) |
| G2a, G2b, G2c | `a3_learning` (agent không ghi reaction hay quyết bài học; sai brain; phản hồi M4 sai revision) |
| G2b, G2e | `a3_api` (phiên brain khác, tin người dùng, câu trả lời thường, khối thẻ do model tự viết) |
| G2d | Hành vi M4 không đổi, khoá ở `test_resonance_mvp_feedback.py` |
| G3a, G3b, G3c, G3d | `a3_learning` (đặt giá trị, nonce, đề xuất thứ hai, mở lại kho); G3d ở `a3_ui` |
| G4a, G4b, G4c | `a3_learning` |
| G5a, G5b | `a3_learning` (thu hồi làn P; thu hồi làn M ở R1b) |
| G6a, G6b, G6c, G6d, G6e | `a3_learning` (dừng giữa phép thử bằng engine giả gọi hành động ở lượt thứ 4) |
| G7a, G7b, G7c | `a3_learning` |

**13.2, bổ sung theo thiết kế:**

| Ca | Chỗ kiểm |
|---|---|
| A1, A2, A3 | `a3_learning` và `a3_api` (drain_outbox thật, cờ `quiet`) |
| A4 | Thay bằng R3a |
| A5, A6, A7 | `a3_learning` (A7 là R3d) |
| A8 | `a3_learning` (hash file trợ lý, sổ đăng ký) và `a3_api` |
| A9 | `a3_learning` và `a3_api` (xoá tin thật trong kho phiên) |
| A10, A11, A13 | `a3_learning` |
| A12 | `a3_rollback` |
| A14 | R5e |
| A15 | `a3_ui` |
| A16 | `a3_learning` và `a3_ui` |

**13.3, 13.4, theo review vòng 1 và 2:**

| Ca | Chỗ kiểm |
|---|---|
| R1a | `a3_learning`: móc chèn Bỏ qua sau cổng cuối, trước giao dịch chốt |
| R1b, R1c, R1d | `a3_learning` |
| R1e | Test M5 cũ (`test_resonance_mvp_trial*.py`) đạt nguyên |
| R2a tới R2f | `a3_learning`; R2a thêm ở `a3_api` |
| R3a tới R3i2 | `a3_learning` |
| R4a tới R4d | `a3_learning` (`JAVIS_RESONANCE_CALL_CEILING=8`); R4d trong R3a (lượt sản phẩm chạy khi `left` đúng bằng lượt dự phòng) |
| R5a, R5b, R5c | `a3_learning`, qua đường huỷ thật: huỷ lần thức đúng lúc pha chuẩn bị đang chạy |
| R5d, R5e | `a3_learning` |
| R6a tới R6d | `a3_rollback`, mã 0.88.1 thật |
| R7a tới R7d | `a3_learning` |

## Số liệu chính đã kiểm

- **Trọn vòng làn M, hạn mức 9 (R3a):**
  - 3 lượt việc, 4 lượt phép thử, 1 lượt làm sản phẩm bằng lượt giữ: tổng 8 lượt engine, `calls_used` = 8, còn 1 lượt dự phòng.
  - Lượt sản phẩm dùng cách mới, mục tiêu đạt.
  - Bốn action phép thử mang revision hiện tại; prompt của tình huống giữ riêng dựng từ lời của revision 1.
- **Hạn mức mặc định 6 (R3b):** `skipped/budget`, 0 lượt thêm.
- **Trần chung 8 (R4a):** góp ý tiếp quản lượt giữ, `calls_used` vẫn 8, `FOLLOWUP` không chạy thêm.
- **Huỷ trước engine (R5a):**
  - lượt giữ về `held` với `gen` 2, `calls_used` vẫn 8;
  - huỷ lặp trả False;
  - tick sau chạy đúng một lần.
- **Chết giữa phép thử (R5e):**
  - mở kho không chốt phép thử khi chưa có lần thức giữ khoá;
  - lần thức sau chốt `interrupted`, bài học `unknown`, lượt giữ trả một lần;
  - `calls_used` = 3 + số lượt thử đã ghi ý định.
- **A3 → 0.88.1 → A3 (R6a):**
  - mã cũ chốt lý do làm sản phẩm với 0 lượt engine, không đụng lượt giữ;
  - A3 dựng lại đúng một lý do (`gen` 2), chạy một lần;
  - mở lại lần ba không thêm gì.

## Lỗi thật tìm ra khi viết test

- **R5e:** phép thử bị ngắt giữa chừng không để lại lịch thức nào, nên lượt giữ kẹt `held` và phép thử kẹt `running`. Đã sửa bằng hẹn `action_recovery` (chỉ kiểm) ở lúc khoá phép thử hết hạn (thiết kế mục 19, I2).
- **Tin `goal.method_changed` không được gửi:** `begin_action` chưa trả `hold_id`. Đã sửa, R3a khoá.
- **Mục Bài học gắn trình nghe click mỗi lần vẽ lại:** một lần bấm sẽ gửi nhiều request. Đã chặn bằng cờ gắn một lần.

## Giới hạn

- Chưa có pilot model thật. Đề xuất pilot ở thiết kế mục 13.5: tối đa 8 lượt, hạn mức 9, cần anh duyệt riêng.
- Chưa soi giao diện trên trình duyệt thật; giao diện chỉ được kiểm bằng hàm thuần dưới node.
- Toàn bộ bộ test của dự án: kết quả ghi trong bàn giao review mã.
- Làn M sẽ thường bị bỏ qua trong dùng thật (cần hạn mức từ 9 và một cách hiểu trước cùng tiêu chí); đây là giới hạn đã chốt ở D4, không phải lỗi.
