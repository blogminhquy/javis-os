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
- Toàn bộ bộ test của dự án (`python tests/run.py`, 626 file): 608 xanh, 18 đỏ trước khi sửa lỗi emoji. Phân định bằng cách chạy đúng 18 file đó trên bản sạch của `main` (`83bff6bc`, git archive):
  - 15 file cũng đỏ trên `main`: agy_prompt_dai, antigravity_cli, ba_loi_mac_va_telegram, cai_windows, grok_cli, ignore_files, install_admin, khoi_dong_nhe, link_file_uri, machine_translations, memory_hoa_thuong, model_theo_phien, ollama_local, terminal, windows_no_console.
  - `test_icons`: lỗi thật của A3 (emoji trên hàng phản hồi), đã sửa thành nhãn chữ, chạy lại xanh.
  - `test_project_khung`: chạy riêng trên nhánh A3 thì xanh, chỉ đỏ thoáng qua lúc chạy cả bộ.
  - `test_image_vision`: đỏ do thư mục `__pycache__` sót lại trong worktree (`system/plugins/zalo-image`), không do mã A3.
- Làn M sẽ thường bị bỏ qua trong dùng thật (cần hạn mức từ 9 và một cách hiểu trước cùng tiêu chí); đây là giới hạn đã chốt ở D4, không phải lỗi.

## Sau review mã vòng 1 (`5b4f48a6`)

Báo cáo: `exports/reviews/PR-598-A3-code-5b4f48a6-review.md` (ngoài git), 3 P2. Sửa ở `efdfb8a8`.

| Điểm | Sửa | Hồi quy |
|---|---|---|
| P2-1: dọn phép thử xoá cả nghĩa vụ `check`, mất `guard_recheck` vừa ghi | Hẹn đối soát của phép thử là mã riêng `trial_recovery` (nghĩa vụ `trial`), chỉ chốt đúng hẹn đó theo id | RV1: guard chưa xác định giữa phép thử, sửa nguồn, mục tiêu hết kẹt; đối chứng guard nhảy thật vẫn giữ chốt |
| P2-2: Áp dụng đề xuất đã hết hạn | `lesson_decide(apply)` kiểm `expires_at` và căn cứ còn sống trong giao dịch | RV2 ở kho (hết hạn, mất căn cứ, đối chứng còn hạn) và qua route thật (409 `expired`) |
| P2-3: kho và file của phép thử chạy trên event loop | Mọi bước kho, file, bằng chứng ở luồng phụ, chờ xong khi bị huỷ; lượt thử bị huỷ trước engine thành `not_run` và được hoàn; route A3 chạy kho ở luồng phụ | RV3: lưu trữ chậm 150 ms ở ba bước, loop không bị chặn; huỷ và huỷ lặp lúc giữ chỗ, lúc ghi ý định, lúc chốt (khoá nhả sau worker); lỗi lưu trữ lúc chốt |

Script kiểm độc lập của reviewer chạy với `--expect-fixed` trên `efdfb8a8`: kết quả ở `exports/reviews/A3-code-r2-review-script-output.txt`.

## Sau review mã vòng 2 (`61d0d8ca`)

Báo cáo: `exports/reviews/PR-598-A3-r2-61d0d8ca-review.md` (ngoài git), 2 P2. Sửa ở `52cf70e4`.

| Điểm | Sửa | Hồi quy |
|---|---|---|
| P2-1: mkdir lỗi sau khi giữ chỗ đã commit bị đọc thành "chưa tạo", hẹn đối soát bị chốt, 5 lượt kẹt | Tách giao dịch giữ chỗ khỏi tạo thư mục; lỗi sau commit chốt phép thử và hoàn đủ; chốt lỗi thì giữ phép thử `running` và hẹn đối soát; lỗi trước commit ghi `storage_error` | RV4: chặn bằng file thật, khôi phục, khởi động lại, đối soát lặp; chốt cũng lỗi rồi tự chốt sau; lỗi trước commit |
| P2-2: `_agent_intent` đọc SQLite trên event loop | Chạy qua `_off_loop` | RV5: mọi lần `agent_by_key` trong phép thử nằm ngoài loop, đồng hồ canh không khựng |

Hai script kiểm độc lập của reviewer chạy với `--expect-fixed` trên `52cf70e4`: `exports/reviews/A3-code-r3-script-r1-output.txt` và `exports/reviews/A3-code-r3-script-r2-output.txt`.

Giới hạn còn ghi rõ:
- `run_once` (dùng chung với lượt việc A2) vẫn có vài thao tác siêu dữ liệu file nhỏ (`resolve`, `is_dir`, `exists`) và việc dựng engine trên event loop.
- `_TrialCall.release` khi engine không dựng được vẫn gọi kho đồng bộ, như `_ReservedCall` của A2.
- Đây là đường đã có từ A2, không đổi trong A3.

## Soi giao diện trên sandbox (sau `b33f3e3b`)

Server sandbox port 7788, state và brain riêng trong `exports/sandbox-a3` (ngoài git), tick nền tắt, engine giả theo prompt (`exports/sandbox-a3/seed.py`). Trình duyệt trong app, desktop 1366x860 và khổ hẹp 375x812, tiếng Việt. 0 lượt model thật. Biên bản đầy đủ và ảnh: `exports/reviews/A3-ui-sandbox-record.md`, `exports/reviews/a3-ui/`.

Năm lỗi giao diện tìm ra và đã sửa, gộp thành bốn dòng (I12 tới I14 ở thiết kế mục 19):

| Lỗi | Sửa | Hồi quy |
|---|---|---|
| Hàng phản hồi không hiện ở trang Cộng sự (GET 400 vì phiên trống, rồi vì phiên của trợ lý trước) | Trang gửi phiên trống; server tra biên nhận theo khoá báo cáo và mục tiêu | UI1 (API): GET và POST theo bộ ba phiên trống; vẫn chặt với phiên sai, brain khác, khoá không có biên nhận. UI4 (JS) |
| Xem trước hiện markdown thô, bài học cách làm hiện mã `work.checklist.v1` | `plainMd`, `to_label`, `goal_label`; phép thử đang chờ có khối riêng với nút Bỏ qua | UI2 (API và JS) |
| Ghi chú xung đột 409 mất ngay khi danh sách vẽ lại | Giữ ghi chú qua một lần vẽ | UI3 (JS) |
| Mục Bài học không tải lại sau phản hồi | Sự kiện `javis:resonance-lessons` | UI5 (JS) |

Mười kiểm mới (4 Python, 6 JS) đều đỏ trên mã `b33f3e3b` và xanh trên mã đã sửa.

## Bộ chạy pilot A3 (chưa chạy thật)

`tests/python/test_resonance_a3_pilot.py`, sửa gói pilot theo review `224a109a` (ba P2). Không đặt biến thì bỏ qua.

- **Hai lớp trần.** Trần kho `JAVIS_RESONANCE_CALL_CEILING=8` đếm cả 3 lượt giả gieo bế tắc. Cổng lượt thật riêng ở biên gọi engine: tối đa 5, ghi sổ xuống đĩa trước mỗi lời gọi, không đặt lại, không hoàn.
- **Dừng ngay khi lỗi.** Lượt lỗi, hết giờ, bị huỷ, đầu ra hỏng hay token sắp hết hạn thì cổng đóng; mọi lời gọi sau bị từ chối trước engine (host thấy engine chưa sẵn sàng, không tính lượt). Tiến trình chết giữa lời gọi thì dòng `reserved` vẫn tính.
- **Luật M5 giữ nguyên.** Nhánh áp dụng chỉ khi `eligible` (hơn ở tập thử, không kém ở đâu, không unknown). Nhãn nhánh giữ nguyên nguyên nhân: `rejected/no_improvement`, `rejected/regression`, `inconclusive/unknown`, `technical_failed (...)`.

Dry chạy 13 kịch bản bằng hai tiến trình mỗi kịch bản (dựng và chạy, rồi mở lại kho với cổng đóng hẳn và đối soát hai lượt): thắng, no_improvement, regression, unknown, lỗi engine ở lượt đầu, lượt cuối phép thử và lượt sản phẩm, hết giờ, token sắp hết hạn, tiến trình chết giữa lời gọi, lỗi lưu trữ khi chốt, trần cổng giữa phép thử, trần kho thiếu. Kết quả và câu duyệt: `exports/reviews/A3-pilot-run-request.md` (ngoài git).

Review bộ chạy `ffcbc940` (ngoài git: `PR-598-A3-pilot-ffcbc940-review.md`), hai P2, sửa trong bộ chạy, không đổi `server/` hay kịch bản:

| Điểm | Sửa | Hồi quy (trong dry, qua mã thật) |
|---|---|---|
| P2-1: nhánh lỗi kỹ thuật vẫn ra `pending_content_review` | Một hàm tổng kết `finalize` cho lần chạy thật: tiền điều kiện, mã thoát hai tiến trình, cấu trúc báo cáo, cổng không đóng, sổ hợp lệ, giai đoạn 2 không gọi engine, số lượt khớp đúng nhánh nội dung. Còn lại là `technical_failed`, ghi FAIL nên thoát khác 0; nhánh gốc giữ nguyên | `finalize` trên 12 kịch bản; `main_real` thật với `run`/`auth` giả trên 8 ca (no_improvement, lỗi lượt đầu, token, chết giữa lượt, sai số lượt, giai đoạn 2 thoát 1, thiếu báo cáo, cổng xác thực hỏng) |
| P2-2: sổ lượt hỏng bị coi là sổ mới | Sổ rỗng chỉ tạo bằng `RealCallGate.create` lúc bắt đầu lần chạy, kèm file dấu `.started`. Đọc lỗi, JSON hỏng, sai cấu trúc, sai số thứ tự, trạng thái lạ, đổi trần, mất file sau khi bắt đầu, hay sổ ít lượt hơn biên nhận trong kho: cổng đóng, không giữ chỗ, không ghi đè, ghi nhật ký lỗi | 13 ca sổ, gồm đối chứng tạo mới và mở lại sau dòng `reserved` |
