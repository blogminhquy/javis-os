# Resonance A5: biên bản kiểm mã (12/10/2026)

Đội một agent làm, một agent review. Thiết kế đã chốt: [2026-10-11-resonance-a5-maker-reviewer-design.md](../superpowers/specs/2026-10-11-resonance-a5-maker-reviewer-design.md) (`56f7ab50`; phương án A cho file sửa tay). Hướng dẫn: [resonance-a5-team.md](resonance-a5-team.md).

**Trạng thái: mã đạt review mã vòng 2 tại `05e9b065` (Codex, 12/10/2026); cổng pilot đạt review vòng 3 tại `33cec518`; pilot thật real-2 tại `33cec518` được reviewer chấp nhận trong phạm vi một mẫu `pass_first` (1 lượt làm, 1 lượt review, 0 chat; chưa chứng minh vòng sửa bằng model thật). Đã tích hợp `main` 0.108.0 với số 0.109.0, chờ review tích hợp cuối. A5 chưa phát hành.** Kịch bản và bộ chạy pilot: [resonance-a5-pilot.md](resonance-a5-pilot.md). Chưa merge, chưa phát hành, không đụng VPS. Các mục kiểm mã dùng engine GIẢ; lượt model thật chỉ có ở mục [Pilot thật](#pilot-thật-13102026).

## Test mới

| File | Nội dung | Ca |
|---|---|---|
| `tests/python/test_resonance_a5_team.py` | Luồng chính, gắn đội qua đường host thật (plugin `javis_goal`, route `/goal-requests`), bộ ghim và lịch, đồng thời, khởi động lại, tắt/bật/mất/nghỉ reviewer, file sửa tay và ảnh chụp, quyền và dừng, tag | T1 tới T4, T10 tới T14, T17 tới T29, T31 tới T46, T55 tới T60; parse đóng khi lỗi (T5, T26) |
| `tests/python/test_resonance_a5_budget.py` | Sổ vai, bảng vết V1, V2, V3, V5, V8, hoàn lượt, bộ đếm thử lại, lịch đối soát, vòng sửa | T5 tới T9, T15, T16, T47 tới T54, T61 tới T67 |
| `tests/python/test_resonance_a5_rollback.py` | Mã 0.108.0 THẬT (`c4fb614d`, qua `git show`; trước tích hợp `main` là 0.100.0 `a02663cb`): nâng, hạ không khôi phục (ghi nhận giới hạn), script khôi phục, nâng lại | T30 |
| `tests/python/test_resonance_a5_api.py` | Route thật: chọn và bỏ chọn người review, từ chối trợ lý chưa bật hay chính nó, khối `team` của goal view, lệnh `team_detach` | 4.2, 11, 12 |
| `tests/python/test_resonance_a5_perf.py` | 200 mục tiêu có đội so với 200 không đội; timer 10 ms khi review lưu bằng chứng chậm | 14 |
| `tests/js/test_resonance_a5_ui.js` | Ô Người review (chỉ trợ lý đã bật, không theo tag), dòng đội, góp ý, hai nút và request của chúng, i18n | 11 |

Ca đi qua đường host thật dùng kho SQLite thật, `form_goal` thật (tool và API), cổng `_gate`, `R.advance` và `R.tick` thật; chỉ engine là giả (phân vai theo lời dặn hệ thống của lượt). Không chèn sẵn `goal_team` hay `reviews` vào fixture. Ngoại lệ có chủ đích, ghi rõ trong test: T12 sửa trực tiếp hàng review đang chạy để tạo kết luận lệch (chỉ có thể xảy ra khi dữ liệu bị can thiệp); T14, T15, T61, T62, T64, T66 gọi đúng các pha `_advance_prepare` và `_review_pre` của host rồi dừng giữa chừng để mô phỏng tiến trình chết hay huỷ ở đúng điểm đó.

## Bảng yêu cầu và test

| Yêu cầu (GOAL, thiết kế) | Test |
|---|---|
| Gắn đội trong giao dịch tạo, cả tool lẫn goal-requests; idempotent; không qua `assign_goal` | T31, T32, T33; T36 (mục tiêu cũ không có đội) |
| Danh tính bền hai vai, không chọn đội bằng tag | T46, T60; API (chọn theo slug, lưu mã); UI (ô không theo tag) |
| Cổng quyền, snapshot, bundle, parser đóng khi lỗi; kiểm lại bundle khi lưu kết quả và khi chốt | parse (T5, T26); T11, T12, T19, T43, T58, T59; `finish` từ chối không có review hợp lệ (chốt chặn ở kho) |
| Tổng 8, maker 4, reviewer 4, tối đa 2 vòng; không tự nâng | T1, T4, T7, T8, T47 tới T50 |
| `seq` chỉ lưu vết; trần 3 và backoff đếm `charged` của đúng bundle | T5, T14, T39, T61, T62, T63 |
| Chỉ hoàn khi chắc chưa gọi model; huỷ và engine không dựng được dùng chung đường hoàn, idempotent, không để `running` | T15, T53, T61, T64, T65 |
| Model có thể đã chạy thì tính lượt | T6, T14, T16, T23, T63 |
| Sau khởi động lại, đối soát bằng code, không thành lượt maker; thử lại đúng backoff và còn đủ lượt | T14, T39, T44, T66; T50 (không thử lượt cuối) |
| needs_changes thứ 1 và 2 cho sửa, thứ 3 dừng; lỗi thời/sai bản không tăng vòng | T3, T4, T47, T67, T12 |
| File sửa tay chờ, không gọi model, không chốt; chỉ dùng lại review khi bytes và bundle khớp; Bỏ yêu cầu review là thao tác chủ dự án | T10, T55, T56, T57; T24, T46 |
| Reviewer không có quyền ghi; trường lạ không đổi quyền hay hạn mức | T1 (file đích là bản của vai làm), T26 |
| Làn M của A3 bị kho chặn trên mục tiêu có đội | T51, T8 (không đề xuất phép thử) |
| I/O không chặn event loop; huỷ chờ pha ghi xong | perf (timer 10 ms); T16 (huỷ trong lúc gọi engine) |
| Hạ về 0.108.0 bằng snapshot | T30 |

## Kết quả chạy (máy local, `.venv` của checkout gốc, mã tại `0ae4cc2b`)

| Lệnh | Kết quả |
|---|---|
| `python tests/python/test_resonance_a5_team.py` | 86 ok, exit 0 |
| `python tests/python/test_resonance_a5_budget.py` | 31 ok, exit 0 |
| `python tests/python/test_resonance_a5_rollback.py` | 11 ok, exit 0 (mã 0.100.0 thật) |
| `python tests/python/test_resonance_a5_api.py` | 10 ok, exit 0 |
| `python tests/python/test_resonance_a5_perf.py` | 5 ok, exit 0 (200 thẻ có đội chậm hơn khoảng 7 ms mỗi thẻ so với không đội; timer 10 ms đúng giờ khi review lưu bằng chứng chậm 0,2 giây) |
| `node tests/js/test_resonance_a5_ui.js` | 32 ok, exit 0 |
| `tests/run.py resonance route_table i18n version_khop_changelog nhat_ky_song_ngu tai_lieu_song_ngu ignore_files phien_ban_moi_nhat prompt_budget prefix_slim agent_tags workspace` | 63/63 file xanh, exit 0 |
| Toàn repo `tests/run.py` (mã tại `5048fc4d`, trước các commit cuối chỉ đổi câu báo, test và tài liệu) | 639/654. 14 file đỏ trùng khít khi chạy cùng 14 file trên bản xuất `main` sạch `a02663cb` (các test phụ thuộc máy: agy_prompt_dai, antigravity_cli, ba_loi_mac_va_telegram, cai_windows, grok_cli, install_admin, khoi_dong_nhe, link_file_uri, machine_translations, memory_hoa_thuong, model_theo_phien, ollama_local, terminal, windows_no_console). File đỏ thứ 15 là `test_resonance_a2_ui.js`: đếm số nhãn lý do thức là 24, A5 thêm đúng 6 nhãn; đã cập nhật thành 30 và chạy xanh trong nhóm trên |

## Lỗi tìm ra khi viết mã, đã sửa, và đối chứng

Chạy test cuối trên đúng cây mã trước mỗi lần sửa (bản xuất `git archive`, chép test hiện tại vào):

| Lỗi | Sửa ở | Đỏ trên mã trước sửa |
|---|---|---|
| Kết luận `stale` hay `review_mismatch` không hẹn lần thức nào, mục tiêu đứng yên | `2b264122` (`record_review`, `review_interrupted` hẹn `review_done` chỉ-kiểm) | T12, T19, T43 trên `3c290b5c` |
| So bản sửa tay bằng `current_artifact_ref`, mà hàm này trả rỗng ở revision mới chưa có lượt làm, nên revision mới bị coi là sửa tay | `2b264122` (`_disk_sha`) | T11, T37 trên `3c290b5c` |
| Hẹn `action_recovery` chỉ-kiểm còn sau khi lượt review xong, kéo lịch vật lý sớm hơn backoff | `2b264122` (`_drop_idle_action_recovery`) | T39 trên `3c290b5c` |
| Tin mới của người dùng trên mục tiêu có đội vấp cờ `use_hold` (tiếp quản lượt giữ nếu có), lượt làm bị từ chối | `2b3ab099` (bỏ qua `use_hold` khi có đội, chỉ từ chối `require_hold`) | T8, T51 trên `2b264122` |
| Engine của lượt review không dựng được: hàng ghi lý do chung, và chờ kiểm lại so giờ kho (giờ thật) với giờ lần thức, nên lượt review thử dựng lại ngay | `2b3ab099` (lý do `engine_not_ready`; chờ theo hẹn `review_recheck` cùng đồng hồ với lần thức) | T53, T65 trên `2b264122` |

Output: `a5-control-team-on-3c290b5c.txt`, `a5-control-budget-on-2b264122.txt` (thư mục bằng chứng, ngoài git).

## Test cũ phải sửa vì hành vi đổi theo thiết kế

- `test_resonance_a3_learning.py`: phiên bản chính sách nhịp tim `heartbeat.v2` thành `heartbeat.v3` (thiết kế mục 10); kiểm thêm hai lớp của A3 giữ nguyên.
- `test_resonance_a2_ui.js`: số nhãn lý do thức trên thẻ 24 thành 30 (sáu mã A5).
- `tests/python/route_table.json`: thêm đúng một route ở cuối (`POST /resonance/agents/reviewer`), thứ tự route cũ không đổi.

## Smoke giao diện trên sandbox (engine giả)

Server sandbox cổng 7788 chạy mã của worktree; state và brain tạm (trong `.playwright-mcp/sbx`, đã gitignore, đường ngắn để tránh giới hạn 260 ký tự của Windows), nhịp Cộng hưởng chạy thật, `main._resonance_engine` thay bằng engine giả hai vai đọc kịch bản từ một file điều khiển. Chromium qua Playwright, tiếng Việt, desktop 1366x860 và khổ hẹp 375x812. Bật Cộng hưởng và chọn người review làm trên giao diện; mục tiêu gieo bằng `form_goal` thật (giả lập lượt chat lập mục tiêu, không có lượt chat thật).

Đạt, đối chiếu kho:
- Ô Người review chỉ liệt kê trợ lý đã bật Cộng hưởng (không có "Trợ lý tắt"); chọn xong host lưu cặp theo mã.
- Mục tiêu 1: bấm Cho phép trên thẻ; lượt làm đăng bản đầu, review "cần sửa"; thẻ hiện "Làm: nguoi-lam · Review: nguoi-duyet", "Bản đã review: 7cdeda8d · Cần sửa (vòng 1/2)", "Đang chờ nguoi-lam sửa theo góp ý", "Lượt còn: làm 3/4 · review 3/4" và góp ý. Lượt sửa đăng bản mới, review đạt, mục tiêu đạt; lượt (2, 2, 4); file đích là bản sửa.
- Mục tiêu 2: tắt người review trước nhịp đầu: `blocked/reviewer_off`, 0 lượt model; thẻ có hai nút. Bấm Bật lại người review, hộp xác nhận thật nói rõ "tính một lượt review", đồng ý: mục tiêu thức lại, làm, review, đạt; lượt (1, 1, 2).
- Mục tiêu 3: người review tắt, bấm Bỏ yêu cầu review: Huỷ ở hộp xác nhận không gửi gì (kho không đổi); Đồng ý: thẻ "Đã bỏ yêu cầu review", mục tiêu chốt theo luật thường với 1 lượt làm, 0 lượt review.
- Khổ 375 px: thẻ hiện đủ dòng đội, không cuộn ngang (`scrollWidth = innerWidth = 375`).

Ảnh: `a5-s01-reviewer-picker.png`, `a5-s02-needs-changes.png`, `a5-s03-reviewer-off.png`, `a5-s04-narrow-375.png`.

Chưa quan sát trên giao diện (đã có test hành vi): file sửa tay trên thẻ (T10, T55 tới T57), hết vòng (T4), hết lượt (T7, T8), review không đọc được (T5, T50). Lỗi console trong smoke là của trang có sẵn (`/tools/optional` 401, mã phiên cũ của sandbox trước 404), không liên quan A5.

## Ranh giới bằng chứng và giới hạn còn lại

- Mọi kiểm dùng engine giả; số lượt engine thật bằng 0. Chưa pilot, chưa đo VPS.
- (Vòng 1 ghi ở đây giới hạn "mục tiêu `maintain` không bị review chặn"; review mã vòng 1 xác định đó là lỗi R3, đã sửa ở vòng 2 bên dưới.)
- Sau `team_detach`, lượt mới tính vào tổng của mục tiêu nhưng không vào `team_calls` (sổ vai giữ nguyên làm hồ sơ), đúng thiết kế mục 6.2.
- Lượt VIỆC của mục tiêu có đội khi engine không dựng được giữ hành vi A2 (kết sổ lỗi cố định `engine_blocked`) cộng hoàn phần maker; chỉ lượt REVIEW đi qua `_refund_not_run` đầy đủ. Hai đường đều hoàn đúng một lần.

## Vòng 2: sửa ba P2 của review mã vòng 1 (nền được review `d22b6c66`)

Review: `exports/reviews/PR-616-A5-code-r1-review.md`. Hồi quy: `tests/python/test_resonance_a5_code_r1.py` (đường host thật, engine giả; request của nút dựng bằng `teamHtml`/`requestFor` thật qua node rồi gửi route FastAPI thật).

| Lỗi | Sửa | Test |
|---|---|---|
| R1: lỗi trong pha chuẩn bị sau `begin_action` làm mất lượt reviewer và ăn trần thử | Mốc `mark_engine` (ghi `engine_at` và `running` một giao dịch) là bước cuối trước engine; lỗi trước mốc đi `_prepare_failed`: `abort_action(code='prepare_error', recheck_at)` hoàn tổng, vai, `charged`, lý do chờ VÀ gác kèm hẹn kiểm lại trong cùng giao dịch. Hoàn cũng lỗi thì đối soát sau khi hết khoá hoàn nhờ thiếu `engine_at`. Áp cho cả lượt việc (`blocked/prepare_error`, hẹn `prepare_recheck`) | R1a lỗi thường, R1b lỗi ở điểm khác, R1c lỗi kèm huỷ lặp (lease nhả sau khi hoàn), R1d hoàn cũng lỗi, R1w/R1w2 lượt việc, R1wn tin mới vẫn mở lượt; đối chứng R1e (đã qua mốc thì `interrupted`, tính), R1f (hành động cũ không có cờ giữ luật cũ), T16/T63 có sẵn (huỷ trong lúc engine chạy vẫn tính) |
| R2: nút Bật lại người review trên thẻ cũ bật được agent mới cùng slug | Nút ghim `agent_key`; route `POST /goals/{id}/reviewer/enable`; `team_reviewer_enable` kiểm đội còn hiệu lực, vẫn ghim đúng mã, mã còn `active` trong một giao dịch rồi mới bật; sai thì 409 kèm goal view mới. Nút bật ở trang trợ lý không đổi | R2 thẻ cũ 409 (agent mới không bật, ghim giữ, sổ không đổi), R2 qua route cùng mã 200 không đổi sổ, bấm lại không tăng version, đội đã bỏ, mã sai, chỉ owner, toggle thường giữ hành vi; UI test `test_resonance_a5_ui.js` |
| R3: mục tiêu duy trì và bước khám phá có đội nhưng không có lượt review nào | `_settle` gọi `_team_settle` cho mọi bản đạt kiểm của mục tiêu có đội TRƯỚC nhánh khám phá, duy trì, kết thúc hay chờ người xác nhận; `goal.maintained` chỉ phát sau `pass`; cùng bộ ghim đã `pass` thì đi thẳng | R3 duy trì pass rồi healthy, nhiều nhịp kiểm định kỳ không review lại, sửa tay chờ `source_drift`, ba lần cần sửa thì `review_rounds`, review không đọc được thì `review_unknown`, reviewer tắt; khám phá pass rồi `discovery_done`, cần sửa rồi pass; đối chứng achieve |

Ghi chú không chặn đã làm cùng đợt (tách khỏi ba P2): receipt của lượt review giữ chẩn đoán engine (`engine`, `usage`, `tool_calls_observed`, `engine_error_code`, `engine_error_detail`), không dự phần quyết định; câu "Chưa có mã A5" ở đầu thiết kế đã sửa.

**Đổi theo hành vi mới (không nới kỳ vọng):**
- Ba fixture mô phỏng "chết giữa lời gọi engine" (`test_resonance_a2_heartbeat.py`, `test_resonance_a3_learning.py` R5d, `test_resonance_mvp_run.py` restart) tạo hành động bằng `begin_action` trực tiếp; thêm `mark_engine` như host thật làm trước lời gọi. Kỳ vọng `interrupted` giữ nguyên.
- `test_resonance_a2_ui.js`: số nhãn lý do thức 30 thành 31 (`prepare_recheck`).
- `test_resonance_a5_ui.js`: nút mang `agent_key`, request tới route của thẻ.
- `route_table.json`: thêm đúng một route ở cuối.

**Script độc lập của reviewer.** Bản gốc `PR-616-A5-code-r1-probe.py --expect-fixed` trên head mới: C1, R3 (2 ca), R1 mở lại kho, R2 PASS; ca R1 đầu FAIL vì điểm chèn `set_run_state(..., 'running')` không còn được gọi sau `begin_action` (`injected: false`, lượt review chạy thật nên sổ (1, 1, 2) là đúng). Bản chỉnh chỉ đổi điểm chèn sang `store.mark_engine` (cùng vị trí: sau giữ chỗ, trước engine), không đổi tình huống hay kỳ vọng: 6/6 PASS, exit 0.

**Đối chứng trên `d22b6c66`** (bản xuất `git archive`, chép test mới vào, chạy TỪNG CA): lỗi hành vi thật ở R1b (hàng `running`, `charged=1`, (1, 1, 2)), R2 thẻ cũ (request đi `/resonance/agents/toggle` theo slug, HTTP 200, agent mới được bật), R3 (8 kiểm: duy trì và khám phá không có lượt review). Các ca còn lại của R1 và hai ca R2 ném `AttributeError` vì thiếu API mới (`mark_engine`, `team_reviewer_enable`); hành vi của tình huống R1 đó trên `d22b6c66` đã được script của reviewer tái hiện. Đối chứng xanh như mong đợi trên mã cũ: R1e, R1f, toggle thường, reviewer tắt, achieve.

**Smoke giao diện (sandbox cổng 7788, engine giả, Chromium 1366x860).** Thao tác mô phỏng bằng script gieo (ghi rõ): lập mục tiêu qua `form_goal`, cho phép phạm vi, tắt người review, và "xoá người review rồi tạo trợ lý mới cùng slug" (`agent_retire` rồi bật, tắt mã mới). Bấm trên giao diện:
- Thẻ có nút Bật lại người review mang mã bền (`data-key="ag_…"`). Bấm, đồng ý hộp xác nhận: `POST /goals/{id}/reviewer/enable` 200, đúng mã cũ được bật, mục tiêu làm, review đạt, chốt với (1, 1, 2).
- Thẻ cũ (sau khi đổi người review cùng slug): bấm, đồng ý: 409; agent mới vẫn tắt; mục tiêu vẫn ghim mã cũ; 0 lượt model; thẻ vẽ lại với câu "Mục tiêu vừa đổi so với lúc bạn xem". Ảnh `a5r2-s01-stale-card-409.png`. Lỗi console: 409 của chính request đó và `/tools/optional` 401 có sẵn.
- Thẻ cũ vẫn hiện trạng thái `reviewer_off` cho tới lần thức kế tiếp của cổng (hẹn `agent_recheck`), khi đó thành `reviewer_retired`; bấm lại trong lúc đó tiếp tục nhận 409.
- R3 không có thay đổi giao diện riêng (thẻ dùng chung dòng đội); hành vi kiểm bằng test.

**Giới hạn còn lại.**
- Engine giả; số lượt engine thật bằng 0; chưa pilot, chưa đo VPS.
- Các lỗi cố định của `run_once` trước lời gọi (`output_scope`, `action_exists`, `invalid_action_id`) vẫn kết sổ `cancelled` theo A2, không hoàn lượt (không đổi ở vòng này; chúng là lỗi cố định, không phải ngoại lệ).
- Pha chuẩn bị lỗi thì mục tiêu gác tới hẹn kiểm lại `ERROR_BACKOFF_S[0]` (một giờ); tin mới của người dùng vẫn mở lượt làm ngay.

**Kết quả chạy vòng 2** (máy local, `.venv` của checkout gốc, mã tại `b10abf4b`):

| Lệnh | Kết quả |
|---|---|
| `test_resonance_a5_team.py` / `_budget` / `_rollback` / `_api` / `_perf` | 86 / 31 / 11 / 10 / 5 ok, đều exit 0 |
| `test_resonance_a5_code_r1.py` (mới) | 45 ok, exit 0 |
| `node tests/js/test_resonance_a5_ui.js` / `test_resonance_a2_ui.js` | 36 / 10 ok, exit 0 |
| Script reviewer bản chỉnh `--expect-fixed` | 6/6 PASS, exit 0 |
| Script reviewer bản gốc `--expect-fixed` | 5/6, exit 1 (ca R1 đầu không chèn được lỗi, xem trên) |
| Nhóm: resonance, route_table, i18n, version/changelog, tài liệu song ngữ, ignore_files, phiên bản, prompt_budget, prefix_slim, agent_tags, workspace | 63/64; đỏ duy nhất `test_ignore_files.py` vì file test mới lúc đó chưa `git add`; xanh trong lần chạy toàn repo sau commit |
| Toàn repo `tests/run.py` | 641/655; 14 file đỏ trùng khít danh sách đỏ trên `main` sạch `a02663cb` (test phụ thuộc máy), không có đỏ mới |

## Review mã vòng 2 và cổng pilot

**Review mã vòng 2 (Codex, 12/10/2026) đạt tại `05e9b065`.** Không có P1 hay P2 mới. Ba P2 của vòng 1 đã xử lý. Reviewer tự chạy:
- script độc lập, bản chỉnh điểm chèn: 6/6;
- năm kiểm bổ sung trên mục tiêu không có đội: 5/5;
- `tests/run.py resonance_a5`: 7/7 file;
- nhóm A2, A3, MVP, A2 UI, bảng route: 5/5 file.

Reviewer không chạy lại toàn repo, và không lặp smoke trình duyệt.

Giới hạn reviewer đã ghi nhận (không chặn cổng chuẩn bị pilot):
- bước chuẩn bị lỗi thì mục tiêu chờ một giờ;
- thẻ cũ chậm cập nhật;
- ba lỗi cố định trước engine (`output_scope`, `action_exists`, `invalid_action_id`) giữ đường cũ;
- hai vai dùng chung engine việc nền.

**A5 chưa nghiệm thu cuối, chưa phát hành.**

**Cổng pilot (không đổi mã sản phẩm).** Kịch bản, hạn mức và bằng chứng: [resonance-a5-pilot.md](resonance-a5-pilot.md). Các file mới, cùng commit `18b2ab60`:

| File | Vai trò |
|---|---|
| `tests/python/_a5_pilot_ledger.py` | Sổ lượt theo vai: giữ chỗ trước khi dựng engine; có trần vai, trần tổng, trần giai đoạn; kết cục khác `ok` đóng sổ; sổ hỏng không cấp lượt; lần bị chặn ghi `refused`; phân nhánh |
| `tests/python/_a5_pilot_server.py` | Chạy `main.app` của checkout, chỉ bọc `main._resonance_engine` bằng sổ; dry thay bằng engine giả, đường "thật" là bẫy |
| `tests/python/test_resonance_a5_pilot.py` | Bộ chạy real và dry (đặt `JAVIS_RESONANCE_A5_PILOT` mới chạy) |
| `tests/python/test_resonance_a5_pilot_gate.py` | Logic sổ, không cần server hay model |

**Kết quả** (máy local, mã tại `18b2ab60`, mã sản phẩm bằng `05e9b065`):

| Lệnh | Kết quả |
|---|---|
| `JAVIS_RESONANCE_A5_PILOT=dry python tests/python/test_resonance_a5_pilot.py` | 12/12 ca, exit 0. Mỗi ca: `commit 18b2ab60`, cây sạch, 0 lượt thật, sổ lượt engine của server sandbox đã xác minh bằng 0 |
| `python tests/python/test_resonance_a5_pilot_gate.py` | 35 ok, exit 0 |
| `tests/run.py resonance_a5 ignore_files tai_lieu_song_ngu version_khop_changelog nhat_ky_song_ngu route_table phien_ban_moi_nhat` | 15/15 file, exit 0 |

Chi tiết các ca dry:

| Ca dry | Nhánh | Sổ (làm, review) | Kết luận |
|---|---|---|---|
| `main_pass` | `pass_first` | (1, 1) | dry_ok |
| `main_fix` | `one_fix_then_pass` | (2, 2) | dry_ok |
| `fix_cap` | `pilot_cap_after_two_reviews`; trần kho chặn lượt sửa thứ ba lúc giữ chỗ | (2, 2) | dry_ok |
| `ledger_cap` | như trên; trần kho nâng lên 8 (chỉ dry), sổ chặn trước khi dựng engine, host hoàn lượt | (2, 2) | dry_ok |
| `review_unknown` | `review_unknown`; không thử lại | (1, 1) | dry_ok |
| `maker_error` | `maker_error`; sổ đóng | (1, 0) | dry_ok |
| `cost`, `auth`, `ledger_exists`, `precondition` | dừng trước việc nền | 0 | stopped |
| `ledger_corrupt` | sổ hỏng, không cấp lượt; sổ chưa xác minh | chưa xác minh | stopped |
| `tripwire` | bẫy ghi sự kiện; một dòng `not_built` vì sổ giữ chỗ trước khi dựng (bảo thủ) | (1, 0) | stopped |

Bộ chạy tìm thấy, chưa từng chạy real:
- Phân nhánh ban đầu không nhận lớp chặn là trần kho. Ca `fix_cap` cho thấy trần kho chặn trước sổ, nên mục tiêu thành `blocked/budget` mà sổ không thấy gì. Đã sửa hàm phân nhánh và thêm ca `ledger_cap` để vẫn chứng minh được lớp sổ.
- Kiểm hash ban đầu sai đích (`accepted_ref` là mốc đăng, không phải lượt làm). Đã đổi sang hai kiểm: hash là bytes chuẩn hoá của một đầu ra lượt làm, và ảnh chụp reviewer đã đọc băm lại đúng hash.

**Chưa chứng minh** (pilot thật mới trả lời được):
- model thật trên cả hai vai;
- nội dung review có ích;
- độ trễ thật;
- hành vi của engine việc nền `anthropic-cli` trong sandbox.

Hiệu năng cục bộ không phải bằng chứng VPS.

### Review cổng pilot vòng 1 (head `3378832d`): ba P2 ở bộ chạy, đã sửa

Review: `exports/reviews/PR-616-A5-pilot-gate-r1-review.md`. Mã sản phẩm không đổi; review mã vòng 2 vẫn giữ. Sửa ở commit `2468919c`, chỉ đụng bộ chạy, test và tài liệu.

| Lỗi | Sửa | Test |
|---|---|---|
| R1: sổ ghi `ok` cho kết quả mà host coi là lỗi (`final` có `is_error` hay `dua_token`, lỗi sau `final`, gọi công cụ trong lượt chỉ chữ) | `Counted` áp đúng luật lỗi của `_ask` trên từng khung. `ok` chỉ là tạm: lỗi đến sau hạ nó xuống, không bao giờ nâng ngược lại. Thêm lớp bọc `GoalDeps._ask` để đối chiếu kết luận cuối của host (`host_<mã>`). Host ngừng đọc sau một `final` hợp lệ thì `ok` giữ nguyên | Test cổng: các ca chạy qua `_ask` thật; `final` rồi huỷ, ngoại lệ hay ngừng đọc; không nâng lỗi; lớp đối chiếu thứ hai. Dry: `final_is_error`, `maker_error`, `reviewer_error` |
| R2: kết luận real không loại lỗi engine, hết giờ hay sổ mất ở lần đọc cuối | Hàm `decide_acceptance` có hợp đồng rõ: `stopped`, `technical_failed`, `pending_content_review`, `business_incomplete`; mã thoát 1, 1, 0, 2; đòi đủ bằng chứng của đúng nhánh. Thêm hai nhánh `maker_not_met` và `reviewer_error`. Real cũng đòi sổ usage xác minh được | Test cổng: 15 ca `technical_failed`, 3 nhánh nghiệp vụ, đối chứng. Dry: các ca âm đi qua đường điều phối và hàm kết luận thật |
| R3: dọn sandbox làm mất log và kho khi lỗi | `preserve_sandbox` chép kho (SQLite backup), log đã che khoá, sổ usage, brain tạm vào thư mục mới trên MỌI nhánh, sau khi server đã dừng; xử lý đường dẫn dài của Windows. Real luôn giữ sandbox; ngoài ra chỉ dọn khi kỹ thuật đạt trọn và bảo toàn đủ. Có `a5-pilot-recovery.txt` | Test cổng: bảo toàn, không ghi đè, che khoá, lỗi khi lưu, thiếu mục bắt buộc, file hỏng, đường dẫn trên 260 ký tự, quyền dọn. Dry: `save_error`, `early_crash`, `ledger_corrupt`, `ledger_lost_end`, `timeout` |
| Lưu ý 1: đơn gộp nền checkout với `main` | Đơn tách dòng: nền checkout pilot là 0.100.0 (`a02663cb`), `main` hiện tại là 0.102.0 (`57c40348`); pilot không phải nghiệm thu bản tích hợp | đơn |
| Lưu ý 2: SHA và cây sạch chỉ được ghi lại, không phải cổng | `preflight_source` ở bước 0, trước mọi server: HEAD phải đúng `JAVIS_RESONANCE_A5_APPROVED_SHA` và cả checkout phải sạch (gồm chính bộ chạy). Real bắt buộc | Test cổng: repo git tạm. Dry: `sha_mismatch` |

**Script của reviewer.** Bản gốc chạy trên head mới: năm kiểm R1 (gọi thẳng API của sổ) PASS, rồi dừng ở `StopIteration`, vì phép gán `rep["acceptance"] = <biểu thức>` và điều kiện quanh `rmtree` đã thành lời gọi `decide_acceptance` và `may_delete_sandbox`. Bản chỉnh chỉ đổi adapter để gọi đúng hai lời gọi đó lấy từ AST của bộ chạy, có nhánh lùi về cấu trúc cũ:
- Mẫu đối chứng thành công được bổ sung cho đủ bằng chứng của một lần `pass_first`.
- Mỗi mẫu R2 áp đúng tình huống của nó lên lần chạy đủ bằng chứng đó.
- Điều kiện dọn được thử với đầu vào dễ dọn nhất (bảo toàn đạt, hồ sơ ngoài sandbox).

Không đổi tình huống hay kỳ vọng. Kết quả bản chỉnh:
- trên `3378832d`: 9 tái hiện lỗi, 2 đối chứng đạt, exit 0, giống output gốc của reviewer;
- trên head mới với `--expect-fixed`: 11/11, exit 0.

**Đối chứng trên `3378832d`** (bản xuất `git archive`, chép test cổng mới vào, chạy từng khối): các khối R1, R2, R3 và kiểm nguồn ném lỗi vì thiếu API mới (`host_text_verdict`, `decide_acceptance`, `preserve_sandbox`, `preflight_source`, tham số `reviewer_failed`). Hành vi lỗi của các tình huống đó trên mã cũ đã được script tái hiện như trên.

**Kết quả vòng này** (máy local, bộ chạy tại `f4b79b58`, mã sản phẩm bằng `05e9b065`):

| Lệnh | Kết quả |
|---|---|
| `JAVIS_RESONANCE_A5_PILOT=dry python tests/python/test_resonance_a5_pilot.py` | 21/21 ca, exit 0. Mỗi báo cáo: `commit f4b79b58`, 0 lượt thật, sổ lượt engine của server đã xác minh bằng 0 |
| `python tests/python/test_resonance_a5_pilot_gate.py` | 90 ok, exit 0 |
| Script reviewer bản chỉnh `--expect-fixed` | 11/11, exit 0 |
| `tests/run.py resonance_a5 ignore_files tai_lieu_song_ngu version_khop_changelog nhat_ky_song_ngu route_table phien_ban_moi_nhat` (tại `2468919c`) | 15/15 file, exit 0 |

Kết luận của các ca dry:
- 2 ca `pending_content_review`: (1, 1) và (2, 2);
- 4 ca `business_incomplete`: `fix_cap`, `ledger_cap`, `review_unknown`, `maker_not_met`;
- 10 ca `technical_failed`, nhánh được giữ nguyên;
- 5 ca `stopped`.

Ca `save_error` giữ nguyên sandbox gốc (kho cùng WAL còn) và có `a5-pilot-recovery.txt`. Các ca sự cố khác đều có bản sao kho, log và brain trong hồ sơ.

Lỗi của bộ chạy mà dry tìm ra trong vòng này, đã sửa trước bản cuối:
- bảo toàn lỗi khi thư mục hồ sơ nằm sâu (giới hạn 260 ký tự của Windows);
- kiểm bộ ghim đòi hàng review cả ở nhánh không có review (`f4b79b58`).

### Review cổng pilot vòng 2 (head `4bcf3615`): một P2 ở pha ghi hồ sơ cuối, đã sửa

Review: `exports/reviews/PR-616-A5-pilot-gate-r2-review.md`. Ba lỗi của vòng 1 và hai lưu ý đã được kiểm lại và đóng. Mã sản phẩm không đổi.

**Lỗi.** Kết luận và quyền dọn sandbox được tính trước khi ghi báo cáo JSON và `a5-pilot-recovery.txt`. Lần ghi nào lỗi thì kết quả vẫn là `pending_content_review`, exit 0. Nếu file khôi phục hỏng, JSON đã ghi trước đó vẫn nói đạt. Ở dry, `sandbox_kept` còn ghi false trong khi sandbox thật được giữ.

**Sửa** (`2eb79253`, chỉ bộ chạy, test, tài liệu): `finalize_record`.
- Thứ tự ghi: file khôi phục trước, báo cáo JSON sau cùng.
- Lần ghi bắt buộc nào lỗi thì kết luận thành `technical_failed`, mã thoát 1, có nguyên nhân cụ thể; nhánh giữ nguyên; sandbox giữ với `sandbox_kept = true`.
- Báo cáo lỗi thì ghi lại file khôi phục với kết luận mới và thử ghi báo cáo đúng một lần nữa. Vẫn không được thì báo ra stdout và stderr kèm đường sandbox.
- Dòng `A5_PILOT` in sau khi chốt, kèm `report_saved`.
- Bộ điều phối dry đòi thêm: mã thoát đúng hợp đồng; báo cáo JSON bắt buộc có và khớp dòng `A5_PILOT`; dòng KEPT khớp `sandbox_kept`.

**Test.**
- Test cổng (100 kiểm) gọi `finalize_record` thật trên fixture pha kết thúc, real và dry, không engine. Các ca:
  - đối chứng lưu thành công, giữ kết luận và exit 0;
  - lỗi ghi báo cáo sau kết quả đạt;
  - lỗi ghi file khôi phục;
  - nghiệp vụ chưa đạt kèm lỗi ghi, không còn exit 2;
  - lỗi kỹ thuật vốn có kèm lỗi ghi;
  - lỗi tạm thời rồi ghi được: báo cáo lần hai vẫn nói `technical_failed`;
  - nơi lưu không tồn tại.
- Dry qua `run_case` với engine giả: `report_fault`, `recovery_fault`, `report_fault_technical`.

**Đối chứng trên `4bcf3615`:**
- Script finalization của reviewer ở chế độ tái hiện: 3 lỗi hành vi, 2 đối chứng, exit 0.
- Test cổng mới chạy từng khối: chỉ khối pha kết thúc thiếu API `finalize_record`; các khối khác xanh.

**Script của reviewer trên head mới:**
- Script finalization vòng 2 không cần chỉnh: điểm neo `delete = PL.may_delete_sandbox(...)` vẫn giữ. Kết quả `--expect-fixed` 5/5, exit 0.
- Script vòng 1 (adapter đã chỉnh ở vòng trước, không đổi thêm): `--expect-fixed` 11/11, exit 0.

**Lỗi khác của bộ chạy mà dry đủ ca tìm ra trong vòng này, đã sửa (`7211d4b7`).** Điều kiện "im lặng" để dừng giai đoạn việc nền bị xét đúng khe chuyển trạng thái: lượt làm vừa kết sổ, nhưng host còn giữ khoá mục tiêu để đăng bản và hẹn review, nên lịch thức tạm trống. Bốn ca dừng sớm, ra nhánh `maker_not_met` sai. Giờ bộ chạy chỉ coi là im lặng khi:
- không có lượt nào đang chạy;
- mục tiêu không ở `running`;
- không lần thức nào giữ khoá mục tiêu;
- điều kiện đó đúng ở hai lần quan sát liên tiếp.

Lần chạy thật cũng có thể gặp khe này.

**Kết quả vòng này** (máy local, bộ chạy tại `7211d4b7`, mã sản phẩm bằng `05e9b065`):

| Lệnh | Kết quả |
|---|---|
| `JAVIS_RESONANCE_A5_PILOT=dry python tests/python/test_resonance_a5_pilot.py` | 24/24 ca, exit 0. Mỗi ca: mã thoát đúng hợp đồng, báo cáo khớp dòng `A5_PILOT`, 0 lượt thật, sổ lượt engine của server đã xác minh bằng 0 |
| `python tests/python/test_resonance_a5_pilot_gate.py` | 100 ok, exit 0 |
| Script vòng 1 (adapter đã chỉnh) `--expect-fixed` | 11/11, exit 0 |
| Script finalization vòng 2 `--expect-fixed` | 5/5, exit 0 |
| Wrapper dry của reviewer (chặn ghi báo cáo `main_pass`, server thật, engine giả) | `technical_failed`, exit 1, sandbox giữ, không có báo cáo |
| `tests/run.py resonance_a5 ignore_files tai_lieu_song_ngu version_khop_changelog nhat_ky_song_ngu route_table phien_ban_moi_nhat` | 15/15 file, exit 0 |

## Pilot thật (13/10/2026)

Commit chạy: `33cec5184c7d825dfc08ba84a3ddf07f3b1d1424`, trên một checkout tách riêng, sạch trước và sau mỗi lần chạy; nền 0.100.0 (`a02663cb`), chưa tích hợp `main`. Đơn: bản cổng vòng 3 (review cổng vòng 3 đạt). Mỗi lần chạy có một lời duyệt riêng của chủ dự án.

| | |
|---|---|
| Đầu vào đóng băng | `d15720546f4d53d611735e9cf3bf0096f02b711f15bf246086a441f50e5f609e` |
| Engine | việc nền `anthropic-cli/sonnet`, gói thuê bao Claude (`claude.ai`, `firstParty`, `max`); không API trả phí |
| Trần | làm 2, review 2, tổng 4; 0 lượt chat |
| Bằng chứng | `exports/reviews/a5-pilot-real-1/` và `exports/reviews/a5-pilot-real-2/` (ngoài repo): báo cáo JSON, sổ, đầu ra từng lượt, đường khôi phục, `sandbox/` (bản sao kho, log đã che khoá, brain tạm) |

### real-1: `stopped` ở cổng token

Qua cổng nguồn, chi phí, xác thực và giai đoạn A (0 lượt). Cổng token trước việc nền hỏng: token gói thuê bao đã hết hạn 163 giây, cổng đòi còn ít nhất 30 phút. Kết luận `stopped`, mã thoát 1, **0 lượt model**; giai đoạn việc nền không bắt đầu. Hậu kiểm offline 19/19 kiểm. Lời duyệt của lần này đã dùng; real-2 có lời duyệt riêng sau khi chủ dự án làm mới đăng nhập.

| File | sha256 |
|---|---|
| `a5-pilot-real-1/a5-pilot-real-main.json` | `bb5a4b50184b20d8740b0536695e3d5fa3023587628dca523c7bdc97c661deb4` |
| `a5-pilot-real-1/a5-pilot-ledger.json` (rỗng) | `f588a20b079ca1d16a25d2c57d6ee07aa74ae07c1f1139fc9f63d0ad917e26dc` |
| `a5-pilot-real-1-console.txt` | `58426d373afb028e21c5de14fa0a3f9fa1d74b03c406d504d61fed891fc04009` |

### real-2: `pending_content_review`, nhánh `pass_first`

Token còn 28698 giây ở cổng. Vai làm viết bản tóm tắt; vai review (mã ghim, khác agent làm) đọc ảnh chụp đúng hash và revision, cho `pass`; host đăng đúng bytes vào file đích, mục tiêu `succeeded`. Giai đoạn việc nền 95,7 giây. Dựng lại server (trần sổ 0): không có dòng sổ, hành động hay hàng review mới. Bộ chạy: 26 kiểm đều đạt, mã thoát 0. Hậu kiểm offline 33/33; reviewer chạy lại độc lập, 33/33.

| Lượt | Vai | Kết cục | Token vào / ra |
|---|---|---|---|
| 1 | làm (`nguoi-lam-tom-tat`) | ok | 18447 / 291 |
| 2 | review (`nguoi-duyet-tom-tat`) | ok | 18651 / 258 |

Sổ pilot = sổ vai của kho (làm 1/4, review 1/4) = `calls_used` 2; một hàng review tính lượt.

| File | sha256 |
|---|---|
| `a5-maker-1.md` (đầu ra lượt làm) | `a37808c46962a97075cc63b51b5be11fde0dff78c18ee2f0f3e96c42fce3e253` |
| `a5-deliverable-final.md` (bản cuối, trùng bytes bản làm) | `a37808c46962a97075cc63b51b5be11fde0dff78c18ee2f0f3e96c42fce3e253` |
| `a5-reviewer-1.txt` (đầu ra thô lượt review) | `5c5a7b19d3b332e6b924545defbb5e1b7965fafa0a2dc9d80b4047c55d93da20` |
| `a5-pilot-real-main.json` | `3b935c3b23bc5f8f12b89c2c941214ea37219e0bce31262a91b4b037800e2b7b` |
| `a5-pilot-ledger.json` | `f8d406063b917899ceb04cf45b8672839bda36c4ca24daaff082f387ae29dc65` |
| `a5-pilot-real-2-console.txt` | `fe462dc6db1371ad9559a3f04d4b95d87c0556f690cb13910efcc6d7fe0e8c79` |

Báo cáo JSON, sổ, đầu ra và bản cuối của cả hai lần giữ nguyên như bộ chạy ghi; hậu kiểm là biên bản riêng, không sửa chúng.

### Review nội dung

Reviewer chấp nhận real-2 **trong phạm vi một mẫu `pass_first`**: bốn dữ kiện của cuộc họp (ra mắt 20/11; chị Lan gửi kế hoạch truyền thông trước thứ Sáu; anh Minh gửi bảng ngân sách quảng cáo trước thứ Năm; cả nhóm họp lại thứ Hai tuần sau) được giữ đúng người, việc và hạn.

Hai góp ý câu chữ, không chặn:
1. "Kế hoạch truyền thông và ngân sách quảng cáo sẽ được hoàn thiện trước cuộc họp tới" là suy diễn: lời giao chỉ nói hạn gửi.
2. "để rà soát tiến độ" là mục đích buổi họp do vai làm thêm, nguồn không nêu.

"Cả nhóm" làm người phụ trách việc họp lại là chấp nhận được (lời giao nói "cả nhóm họp lại"), nhưng không có nghĩa đã xác định người tổ chức. Bản pilot giữ nguyên làm bằng chứng; không sửa nó rồi dùng bản sửa để tuyên bố đạt.

**Giới hạn của vai review trong A5 hiện tại.** `_review_prompt` chỉ đưa mô tả vai, cách hiểu mục tiêu, tiêu chí, ràng buộc và bản cần review; không đưa lời giao gốc (đúng thiết kế, mục 4.3 và D8: không đưa lịch sử chat). Trong pilot, cách hiểu mục tiêu chỉ mô tả cấu trúc bản tóm tắt, nên các dữ kiện vai review thấy đến từ chính bản cần kiểm. Kết quả `pass` **không** có nghĩa vai review đã đối chiếu trung thành với nguồn, hay đã phát hiện thông tin thêm vào.

**Usage.** Sổ usage chung của server (`usage.json`) ghi 0 vì chỉ đếm lượt chat; lượt việc nền của Cộng hưởng nằm ở hành động và receipt của kho, và ở sổ pilot (2 lượt thật). Sổ usage chung báo 0 không có nghĩa lần chạy không tốn model.

### Giới hạn còn lại

- Một mẫu, nhánh đạt ngay. Nhánh yêu cầu sửa, chạm trần, review không đọc được và lỗi engine chỉ có bằng chứng bằng engine giả.
- Hai vai dùng chung model việc nền: độc lập về vai và ngữ cảnh, không phải hai model khác nhau.
- 0 lượt chat: không kiểm bộ não chat tự định tuyến tới `javis_goal`.
- Máy local, nền 0.100.0; chưa đo hiệu năng VPS. Tích hợp `main` là diff riêng, review riêng.

### Hai việc cải tiến riêng (chưa triển khai, ngoài PR này)

1. Nguồn yêu cầu tối thiểu do host ghim đúng mục tiêu và revision, đưa cho vai review để đối chiếu việc thêm hay bớt dữ kiện. Không phải toàn bộ lịch sử chat, và vẫn không cho xem suy luận của vai làm.
2. Đưa lượt và token việc nền của Cộng hưởng vào màn hình usage chung, không đếm trùng với sổ chat.

## Tích hợp `main` tới 0.108.0, đánh số 0.109.0 (13/10/2026)

`main` đi tiếp bốn lần trong lúc tích hợp (0.103.0, 0.105.0, 0.107.0, 0.108.0). Mọi lượt theo cùng quy tắc:
- merge `main` vào nhánh, không rebase;
- xung đột chỉ giải ở `VERSION` và hai changelog: khối A5 ở đầu, các khối của `main` giữ nguyên;
- đánh số lại và dời mốc quay về trong commit riêng, theo bản phát hành thật cuối cùng trước A5.

Mốc lịch sử (kết quả các vòng trước, nền checkout pilot, số dòng dẫn theo `a02663cb`) giữ số cũ.

| Commit | Lượt | Nội dung |
|---|---|---|
| `0840dc6e` | | Hồ sơ pilot real-1 và real-2 (chỉ tài liệu) |
| `ba591f4f`, `371ff0ab`, `1db1d570` | 1 | Merge `main` 0.103.0 (`eb733834`, #622); A5 0.104.0; biên bản |
| `d7276bc5`, `4b20001e` | 2 | `main` 0.105.0 (`1dd593ba`, #624) vượt 0.104.0, #623 cũng giữ 0.104.0; A5 0.106.0. **Đã review tích hợp tại `4b20001e`** |
| `ef18c9f5`, `fecbb63d` | cuối | `main` 0.107.0 (`49c795ab`, #623) vượt 0.106.0, #625 giữ 0.108.0; A5 lấy **0.109.0**; hậu tố `.pre-0.109.0` |
| `79724208` | cuối | Test mới `test_resonance_a5_engine_session_gate.py` (chỉ test) |
| `6c4f0b5a`, `20d7c063` | cuối | `main` 0.108.0 (`c4fb614d`, #625); 0.109.0 vẫn trống và lớn hơn `main` nên giữ số; mốc quay về sang 0.108.0 thật (CI và build image GHCR của `main`) |

Cả năm commit merge (`ba591f4f`, `d7276bc5`, `ef18c9f5`, `6c4f0b5a`): `--remerge-diff` chỉ có `VERSION`, `CHANGELOG.md`, `CHANGELOG.en.md`.

### Mã chạy

- **Mã A5 giữ nguyên.** Phần A5 thêm trên `main` trùng khít, từng file, với phần A5 đã review trên nền cũ (`a02663cb` tới `33cec518`): 9 file, cùng nội dung dòng thêm và bớt.
  - Kiểm ở lượt 1 (`eb733834` tới `ba591f4f`), lượt 2 (`1dd593ba` tới `d7276bc5`) và lượt cuối (`49c795ab` tới `ef18c9f5`, so với `1dd593ba` tới `4b20001e` đã review).
  - #625 (0.108.0) không đụng file nào của 9 file đó.
- **File tự gộp** giữ đủ thay đổi của cả hai phía: `server/main.py` ở mọi lượt có đổi (lượt cuối: A5 thêm 2 dòng, #623 thêm 137 và bớt 38 dòng), hai file i18n ở lượt 1.
- **Dòng mã chạy duy nhất đổi do tích hợp:** `A5_BACKUP_SUFFIX = ".pre-0.109.0"`, cùng chú thích. 0.104.0 và 0.106.0 chưa từng phát hành, nên đổi hậu tố không ảnh hưởng máy nào.

### Tác động gián tiếp của `main` 0.107.0 và 0.108.0

- **`claude_sdk_engine` (#623):** phiên có `allowed_tools` giờ được nạp plugin tool khi danh sách nêu đích danh `mcp__javis-plugins__<tên>`. Lượt làm và lượt review của A5 dựng bằng `main._resonance_engine`, với một tên canh gác không khớp công cụ nào. Test mới `tests/python/test_resonance_a5_engine_session_gate.py` dựng ĐÚNG đường đó (swap, `strip_tools`, `pick_text_only_link`) cho system prompt của hai vai, thay `ClaudeSDKClient` bằng client giả để bắt `options` thật đưa cho SDK. Kết quả, 26 kiểm:
  - MCP rỗng và strict: không hub, không server plugin;
  - `allowed_tools` chỉ có tên canh gác, cổng `can_use_tool` bật; không nạp settings máy người dùng; công cụ native bị cấm sẵn;
  - cổng từ chối 14 tên công cụ (native, hub, plugin có và không tiền tố);
  - không chuỗi dự phòng; provider đã chọn chưa sẵn sàng thì không chạy thay bằng provider khác;
  - đối chứng: phiên nêu đích danh một plugin tool thật thì có server plugin, nên test thấy được nếu A5 bị rò. Trên `4b20001e` (SDK 0.105.0), test dừng ở kiểm thứ hai vì `plugins_host.granted_plugin_tools` chưa có.
- **`sessions` (#623):** thêm bảng `cli_session_history` và ghi lịch sử trong `set_cli_session_id`. Cùng file test: kho phiên kiểu cũ (bỏ đúng bảng mới, vì CI chỉ fetch nông một commit nền) mở được, tạo bảng; dòng phiên giữ nguyên; phiên agent vẫn ra đúng danh tính (`agent:<slug>`, nguồn danh tính A5); gắn phiên CLI mới ghi lịch sử.
- **#625 (0.108.0):** chỉ đường Zalo, chatbot, hội thoại khách và danh mục MCP; không đụng file Cộng hưởng, `server/main.py`, engine hay `sessions`.

### Kết quả

| Lệnh | Head | Kết quả |
|---|---|---|
| `python tests/python/test_resonance_a5_rollback.py` | `20d7c063` | 11 ok, exit 0, mã 0.108.0 thật qua `git show c4fb614d` |
| `python tests/python/test_resonance_a5_engine_session_gate.py` | `20d7c063` | 26 ok, exit 0 |
| `tests/run.py` theo tác động: mọi `resonance_*`, `sdk_engine`, `aux`, `session`, `strip`, `kanban`, `workflow`, `agent_rules`, `learn`, `usage`, `plugin`, `reminder`, `task`, test mới của #623, phiên bản, changelog, route, i18n, `ignore_files` | `fecbb63d` + test mới | 101/102; file đỏ duy nhất `test_ignore_files` vì test mới chưa commit, xanh sau commit `79724208` |
| Theo tác động sau merge 0.108.0: test engine và kho phiên, phiên bản, changelog, route, tài liệu song ngữ, hai test mới của #625, `ignore_files` | `20d7c063` | 9/9 và 1/1, exit 0 |
| `JAVIS_RESONANCE_A5_PILOT=dry JAVIS_RESONANCE_A5_DRY_ONLY=main_pass,main_fix python tests/python/test_resonance_a5_pilot.py` | `79724208` | 2/2 ca, exit 0; đúng nhánh, sổ (1, 1) và (2, 2), sổ engine server 0, 0 lượt model thật |

**Không chạy lại** cả 24 ca dry hay toàn repo ở lượt cuối, vì:
- bộ chạy pilot không đổi kể từ `33cec518`;
- mã A5 không đổi ngoài hậu tố;
- các đường bị `main` đụng tới đã có kiểm riêng ở trên;
- các kiểm theo tác động không phát hiện lỗi mới.

CI trên head cuối chạy đủ bộ test của repo.

Lượt 2 (`4b20001e`, đã review) có: quay về 11 ok trên mã 0.105.0; dry 24/24; toàn repo 647/661 với 14 file đỏ phụ thuộc máy khớp `main` sạch `1dd593ba`; CI `push` 38342887031 và `pull_request` 38342891054 thành công. Lượt 1 (`371ff0ab`) tương đương trên 0.103.0. 14 file đỏ: agy_prompt_dai, antigravity_cli, ba_loi_mac_va_telegram, cai_windows, grok_cli, install_admin, khoi_dong_nhe, link_file_uri, machine_translations, memory_hoa_thuong, model_theo_phien, ollama_local, terminal, windows_no_console.

Không gọi model thật, không chạy lại pilot, không merge, không phát hành, không đụng VPS. Giới hạn của pilot real-2 giữ nguyên như mục "Pilot thật".
