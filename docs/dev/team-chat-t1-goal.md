# Nhóm chat team: chốt nền T1 theo GOAL thống nhất (0.152.0)

GOAL: `exports/reviews/GOAL-TEAM-CHAT-T1-T4-COMPLETE.md` mục 4.1, 4.2, 4.3, 5, 9, 12 (ca 1, 3, 11, 12, 13, 14). Nền: [team-chat-t1.md](team-chat-t1.md) (0.111.0) và các bản sau. Mọi kiểm ở đây chạy bằng engine GIẢ, không gọi model, không đụng VPS.

## 1. R1 tới R9 đã xác minh trên head thực tế

| Mã | Yêu cầu | Bằng chứng |
|---|---|---|
| R1 | Phân loại lỗi engine: final lỗi, final rỗng, gọi công cụ không thành sản phẩm | Script reviewer bản adapter `PASS fixed R1_engine_outcome`; `test_team_t1_review.py` |
| R2 | Lịch sử đúng nhóm trong lời nhắc | `PASS fixed R2_context` |
| R3 | Kiểm đầu ra muộn trước khi ghi bài học | `PASS fixed R3_late_learning` |
| R4 | Hoàn lượt chưa tới engine | `PASS fixed R4_before_engine` (lượt `refunded`, không đánh dấu engine) |
| R5 | I/O ngoài event loop, giữ lượt nguyên tử | `PASS fixed R5_event_loop`, khe lớn nhất 40,8 ms (ngưỡng 100 ms, máy cục bộ) |
| R6 | Khôi phục kho nhất quán | `PASS fixed R6_rollback`; `test_team_rollback.py` |
| R7 | Bản cũ không chốt bản mới | `PR-628-T1-r2-race-checks.py --expect-fixed`: `PASS fixed R7_stale_revision`; thêm ca thu hồi quyền ở cửa áp dụng (G1 dưới) |
| R8 | Nhiều kick không vượt pool, không nhận trùng, không rò chỗ | `PASS fixed R8_parallel_cap`; G2 (kick thứ hai lúc A chạy), G4 |
| R9 | Khôi phục hỏng sau ghi | `PASS fixed R9_restore_failed_destination` |

Output đầy đủ kèm lệnh và mã thoát: `exports/reviews/team-adaptive/t1-evidence.txt`.

**Script reviewer phải chạy bản adapter.** Từ 0.142.0 `main._team_engine_for` dựng engine qua `team_engine.build`, không còn qua `main._resonance_engine`, nên bản gốc `PR-628-T1-review-checks.py` không còn thay được engine và đã gọi engine THẬT. Bản `team-adaptive/PR-628-T1-review-checks.adapted.py` chỉ đổi điểm thay engine (diff: `PR-628-T1-review-checks.adapter.diff`), giữ nguyên mọi kịch bản và kỳ vọng, và thêm chốt chặn: dựng engine thật hay chạy CLI của engine (claude, codex, grok, agy, gemini, ollama) thì dừng với thông báo rõ, mã thoát 2; sau các kịch bản kiểm engine giả được gọi đúng một lần mỗi kịch bản. Chốt đã tự kiểm: bỏ phần thay engine thì script dừng ở `REAL ENGINE BLOCKED`.

## 2. Thay đổi

1. **Ghim quyền theo lượt** (GOAL 9 "lượt cũ không hưởng quyền cấp lại"). `team_turns.authority_id` ghi dòng Toàn quyền đang hiệu lực trong CÙNG giao dịch giữ chỗ lượt (`team_store.reserve_turn`), chỉ cho lượt của chính trưởng nhóm được cấp. `team_runner._apply_admin` so dòng đang hiệu lực với dòng đã ghim trong `accept_lock`; khác nhau (thu hồi rồi cấp lại, cấp mới, sửa hộp cấp quyền, cấp khi lượt bắt đầu ở Quyền giới hạn) thì lệnh bị bỏ kèm ghi chú. Lời nhắc cũng chỉ hiện khối Toàn quyền khi dòng đã ghim còn hiệu lực. Trưởng nhóm tự đổi trần trong dòng (`set_cap`) không đổi dòng nên không ảnh hưởng.
2. **Ưu tiên qua đường host**: hành vi đã đúng từ trước; thêm test chặn hồi quy (A đang chạy trong engine, ưu tiên C, thứ tự A, C, B; A một lần, không bị ngắt; kick thứ hai không mở việc vượt pool).
3. **Gia hạn khoá bận và hạn giữ việc trong lượt dài.** `TeamRunner._keep_leases` chạy suốt lượt, gia hạn `agent_busy` (`team_store.renew_busy`, chỉ UPDATE đúng lượt, không giành lại) và hạn giữ việc (`task_store.team_heartbeat`) mỗi `min(30 giây, hạn/3)`; dừng khi lượt xong hay bị huỷ, trước khi nhả khoá. Hạn chỉnh được trên bộ chạy (`busy_lease_s`, `job_lease_s`, `lease_renew_s`).
4. **`running_jobs` thành giới hạn máy chủ.** Pool chung bỏ qua nhóm đã có việc chạy (review T1 R8), nên số lớn hơn 1 trước đây nhận được mà không bao giờ có tác dụng. Chọn thay đổi nhỏ và an toàn: bỏ khỏi trần chủ chỉnh (`team_store.OWNER_CAPS`), cố định 1 (`FIXED_CAPS`), dòng cũ từng lưu số khác vẫn hiện 1. Mở song song trong một nhóm sẽ đụng khoá bận theo agent, thứ tự hàng đợi và ngữ cảnh chung, để cho mốc sau nếu cần. `no_progress` cùng cách: bộ chạy dừng ở hai kết quả giống hệt liên tiếp, con số chưa bao giờ được đọc.
5. **Bảng giới hạn** (`TeamRunner.limits_table`, trả trong `authority.limits` của khung nhìn nhóm) và mục "Bảng giới hạn" trong Nâng cao (`teams.js` `limitsHtml`, i18n vi/en, chữ 16px). Trần của chủ có ô **Không giới hạn** riêng ngay ở mục Giới hạn của nhóm (lưu `null`, không thay bằng số lớn).
6. **`set_resonance` của trưởng nhóm** gọi `wake_agent_goals` sau khi bật, như route bật của chủ (`_TeamAdmin.set_resonance`). Luật ghi trong `_apply_admin`: chỉ trợ lý do CHÍNH nhóm quản lý và chỉ dưới dòng Toàn quyền ghim cho lượt (Toàn quyền bao gồm quản lý trợ lý do nhóm quản lý, spec 13.3). Trợ lý chủ đã tắt mà nhóm chỉ có làm thành viên, hay do nhóm khác quản lý, thì trưởng nhóm không bật lại được. Nhật ký: `team_events` `agent_set_resonance` và `resonance_agent_events` by `leader:<mã>`.
7. **Đổi tag không đổi nhóm** (GOAL 12.1): thêm test qua route thật, hành vi đã đúng.

## 3. Bảng giới hạn

| Giới hạn | Mặc định | Ai đổi | Không giới hạn |
|---|---|---|---|
| Lần trả lời tối đa mỗi việc (`task_turns`) | 12 | Chủ; trưởng nhóm trong Toàn quyền, trong trần tối đa | Có (Toàn quyền: chỉ cho gói chủ tích, D6) |
| Bước tối đa mỗi việc (`task_steps`) | 8 | Chủ; trưởng nhóm trong Toàn quyền | Có |
| Số lần nhờ nhau lồng nhau (`help_depth`) | 2 | Chủ; trưởng nhóm trong Toàn quyền | Có |
| Lần trả lời tối đa mỗi ngày (`daily_turns`) | 100 | Chủ; trưởng nhóm trong Toàn quyền | Có (Toàn quyền: chỉ cho gói chủ tích, D6) |
| Số người gọi (@) mỗi tin (`mentions`) | 3 | Chủ | Không |
| Chờ trợ lý đang bận tối đa (`busy_wait_s`) | 1800 giây | Chủ | Không |
| Việc chạy cùng lúc trong một nhóm (`running_jobs`) | 1 | Máy chủ cố định | Không |
| Nhóm chạy việc cùng lúc trên cả máy (`max_parallel_teams`) | 4 (từ 0.257.0, trước đó 2) | Máy chủ (biến môi trường `JAVIS_TEAM_PARALLEL`) | Không |
| Lượt cùng lúc của một trợ lý trong MỘT nhóm (0.257.0: trước đó là trên mọi nhóm) | 1 | Máy chủ cố định | Không |
| Lượt nhóm gọi model cùng lúc, mỗi engine gói đăng ký (0.257.0) | 3 | Máy chủ (biến môi trường `JAVIS_TEAM_CLI_SLOTS`) | Không |
| Lượt nhóm gọi model cùng lúc, mỗi engine API key (0.257.0) | 6 | Máy chủ (biến môi trường `JAVIS_TEAM_API_SLOTS`) | Không |
| Bước Làm chạy cùng lúc trong một việc (0.260.0) | 3 | Máy chủ (biến môi trường `JAVIS_TEAM_JOB_PARALLEL`) | Không |
| Lượt có công cụ cùng lúc trong một thư mục làm việc (0.260.0, trước đó 1 mỗi brain) | 3 | Máy chủ (biến môi trường `JAVIS_TEAM_TOOL_SLOTS`) | Không |
| Nhiều @ trong một tin trả lời cùng lúc hay lần lượt (`reply_parallel`, 0.260.0) | Cùng lúc | Chủ | Không |
| Hạn khoá bận (`BUSY_LEASE_S`), tự gia hạn khi lượt còn chạy | 900 giây | Máy chủ cố định | Không |
| Kết quả giống hệt liên tiếp thì dừng (`no_progress`) | 2 | Máy chủ cố định | Không |
| Thời gian một lần trả lời (`JAVIS_TEAM_TURN_TIMEOUT`) | 600 giây | Máy chủ (biến môi trường) | Không |
| Thời gian một bước (`JAVIS_TEAM_STEP_TIMEOUT`) | 3600 giây | Máy chủ (biến môi trường) | Không |
| Lệnh quản trị mỗi lần trả lời của trưởng nhóm | 10 | Máy chủ cố định | Không |
| Tin gần đây trợ lý đọc mỗi lượt | 20 tin, 8000 ký tự | Máy chủ cố định | Không |
| Lượt nhóm chỉ chữ, không công cụ | luật | Máy chủ cố định | Không |
| Trần lượt toàn máy (`JAVIS_RESONANCE_CALL_CEILING`, đọc bằng `resonance_store.call_ceiling()`; giá trị hỏng hay âm là 0, chặn hết) | chưa đặt | Máy chủ (biến môi trường) | Không |
| Hạn mức gói thuê bao hay nhà cung cấp | luật | Nhà cung cấp | Không |
| Quyền của tài khoản model | luật | Nhà cung cấp | Không |

Không chế độ nào được mô tả là "bỏ mọi giới hạn": nhóm máy chủ và nhà cung cấp luôn áp, kể cả ở Toàn quyền mức 3.

## 4. Test

- `tests/python/test_team_t1_goal.py` (bộ chạy và kho thật, engine giả, Event có hạn chờ): G1 ghim quyền (bốn ca, gồm bước plan), G2 ưu tiên, G3 gia hạn khoá bận và hạn giữ việc (xong và huỷ), G4 `running_jobs`, G5 bảng giới hạn và Không giới hạn, G6 luật `set_resonance`. Trên head cũ `75e17400`: 24 ca đỏ (G1, G3, G4, G5), G2 và G6 xanh vì hành vi đã đúng (chặn hồi quy).
- `tests/python/test_team_t1_goal_host.py` (main.py, TestClient, engine giả, chốt chặn engine thật): H5 bảng giới hạn và Không giới hạn qua route, H6 `set_resonance` đánh thức mục tiêu và luật quản lý, H7 đổi tag. Trên head cũ: 4 ca đỏ (H5, đánh thức của H6), H7 xanh.
- `tests/js/test_teams_ui.js`: ô Không giới hạn của trần chủ, bảng giới hạn, i18n, CSS 16px.
- `tests/python/test_team_t1_review_fixes.py` (review độc lập T1, sau `af85ad71`): F1 mất quyền giữ (khoá sang lượt khác, việc đổi người giữ, kho lỗi quá kỳ hạn; đối chứng kho lỗi tạm một nhịp), F2 gia hạn hạn giữ việc khi còn chờ khoá bận, F3 trần máy chủ trong bảng bằng `call_ceiling()`, F4 bật Auto được mà đánh thức lỗi, F5 `set_caps` chặn NaN và vô cực. Host: H8 (đánh thức lỗi qua `main._TeamAdmin`), H9 (route caps trả 4xx với NaN, Infinity, 1e400). JS: `capsPayload` bỏ tích Không giới hạn mà chưa nhập số thì không gửi gì.

## 5. Sửa theo review độc lập T1

- **Mất quyền giữ giữa lượt** (`team_runner._keep_leases`, `_accept`): gia hạn trả False là mất quyền thật (`busy_taken`, `job_lost`); kho lỗi chỉ thành mất quyền (`store_error`) khi cả kỳ hạn trôi qua mà không gia hạn được lần nào. Trước khi nhả khoá còn kiểm lần cuối `TeamStore.busy_turn`. Lượt mất quyền có kết quả `lease_lost`: tin vẫn đăng làm bằng chứng, không ghi bài học, không áp lệnh quản trị hay kết quả bước. Việc đã sang tiến trình khác thì không đụng bước và dừng vòng; chỉ mất khoá agent thì bước chạy lại.
- **Chờ khoá bận** (`_keep_job_lease`): hạn giữ việc được gia hạn ngay trong lúc chờ, không đụng khoá agent của lượt khác.
- **Bảng giới hạn** đọc trần máy chủ bằng đúng `resonance_store.call_ceiling()`.
- **Bật Auto mà đánh thức lỗi** (`main._TeamAdmin.set_resonance` trả `wake_error`): Auto giữ bật, nhật ký nhóm có `agent_set_resonance` và `agent_wake_failed`, ghi chú nói rõ Auto đã bật.
- **`set_caps`** từ chối NaN, vô cực, kiểu sai trước khi ghi (cả `busy_wait_s` và trần trong hộp quyền), trả 4xx.
- **Câu chữ:** docstring `effective_caps` và ghi chú trần của người điều phối nói đúng khi chủ đặt trần Không giới hạn.
- **Vòng 2 của review bản sửa:** lần kiểm khoá cuối nằm trong `try/finally` nên huỷ lần hai vẫn nhả khoá (F6); việc mất người giữ ngay lúc chờ khoá thì không gọi engine, hoàn lượt (F7); mất việc thì vẫn giữ khoá agent tới hết lượt; `job_lost` thắng mọi nhãn đến muộn; mất khoá lặp lại tối đa `LEASE_REQUEUE_MAX = 2` lần chạy lại mỗi bước rồi chặn việc (F8), kể cả khi trần là Không giới hạn; lượt trả lời mất quyền trước engine có lý do `lease_lost`; nút Lưu giới hạn tách thành `saveCapsFlow` để test hành vi thật (không POST, focus đúng ô).

## 6. Bằng chứng đo dao động (không phải hồi quy)

- CI của `af85ad71` đỏ một kiểm độ trễ trong `test_resonance_perf.py` (0,102 s, ngưỡng 0,1 s). Commit đó chỉ đổi `teams.js` và i18n. Chạy lại cùng SHA trên CI: xanh (lần 2, run 38629547827). Cục bộ 5/5 đạt. Hồi quy thật (chặn event loop) cho khoảng 0,2 s, không phải 0,102 s. Ngưỡng giữ nguyên.
- `test_team_t1_review.py` R5 (event loop với kho chậm 250 ms): trên bản sửa đỏ 1/5 lần (114,6 ms), trên mã gốc `3240168f` đỏ 1/6 lần (237,8 ms), cùng lúc máy đang chạy test của hai agent khác. Quét AST mọi hàm async của `team_runner.py`: không có lời gọi kho đồng bộ nào trên event loop. Kết luận: dao động do tải máy, có sẵn từ trước; ngưỡng giữ nguyên.
