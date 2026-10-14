# Nhóm chat 0.142.0: hết im lặng, tạo nhóm kiểu Zalo, tab Công việc, Auto

Ngày 14/10/2026. Nhánh `claude/compassionate-wozniak-z5umfl`, PR [#651](https://github.com/blogminhquy/javis-os/pull/651).
Nền: `main` `063750a` (0.141.0). Số phiên bản giữ chỗ ngay đầu nhánh (commit đầu, PR nháp mang số 0.142.0).

**Đánh số lại khi phát hành:** trong lúc làm, `main` lên 0.145.0 (#652, #653 đang mở giữ 0.143.0, 0.144.0), nên bản này
phát hành là **0.146.0**. Tên file biên bản, tên test và các ghi chú "0.142.0" trong mã giữ nguyên như dấu mốc của tính
năng (hậu tố sao lưu `.pre-0.142.0` cũng giữ để khớp marker migration đã chạy ở các máy thử).

Goal gốc nằm ở máy của chủ repo (`exports/reviews/team-chat-zalo-ux-2026-10-14/goal-claude-v2.txt`, `audit.md`, ảnh
01 tới 08). Phiên này chạy trong container đám mây nên không đọc được thư mục đó; làm theo đúng nội dung goal được dán
trong lệnh `/goal` cùng năm ảnh chụp đính kèm. PR #645 (đã đóng) không bị đụng tới.

## 1. Chat nhóm im lặng: nguyên nhân gốc đã xác minh

Hai lỗi chồng nhau:

1. **Lượt nhóm đi qua hợp đồng của Cộng hưởng.** `main._team_engine_for` dựng engine bằng `_resonance_engine`: model
   VIỆC NỀN, và `resonance.pick_text_only_link` chỉ nhận hai cơ chế chỉ chữ (Claude có cổng `can_use_tool`, engine API có
   `no_tools`). Máy để model việc nền là Codex thì mọi lượt bị chặn trước mốc gọi model.
   Tái hiện trên mã `origin/main` cũ (worktree tạm, settings: chính Claude, việc nền Codex):
   `EngineUnavailable: model việc nền chưa chạy được lượt chỉ chữ: {... 'blocked': 'engine openai-oauth còn công cụ
   native, chưa có cơ chế chỉ chữ được kiểm; Resonance M1 chỉ nhận Claude (cổng can_use_tool) và engine API (no_tools)'}`,
   `engine_started` chưa từng được gọi.
2. **Kết cục lỗi bị bỏ đi.** `team_api.teams_send` chạy `runner.run_replies(sub)` nền và không ai đọc kết quả; lượt lỗi
   chỉ còn trong sổ lượt, khung chat không có dòng nào.

## 2. Đã làm

| Mục | Thay đổi | File chính |
|---|---|---|
| Hợp đồng engine | `team_engine.py`: model của trợ lý, thiếu hay chưa cấu hình được thì model chính (ghi chú trên tin vì sao). Không dùng model việc nền, không chuỗi dự phòng, không nâng quyền | `server/team_engine.py`, `main._team_engine_for` |
| Codex chỉ chữ | Không profile `-p`, `mcp_servers={}`, `web_search="disabled"`, tắt công cụ native bằng `features.*=false`, LUÔN `--sandbox read-only` (kể cả `JAVIS_CODEX_SANDBOX=off`) | `team_engine.codex_text_only` |
| Grok, Antigravity | Chưa có cơ chế chỉ chữ được kiểm: báo lý do, không chạy thay bằng provider khác | `team_engine.build` |
| Kết cục lượt trả lời | Bảng `team_replies` (queued, running/answering, done, error + lý do), gói WS `team_replies`, trang tin kèm `replies`, Thử lại bằng CAS `error -> queued`, khởi động lại đổi lượt dở thành `error/restart` | `team_store.py`, `team_runner.py`, `team_api.py`, `teams.js` |
| Việc nền bị chặn | Thêm tin hệ thống ngay trong khung chat (ngoài hộp thư) | `team_runner._block` |
| @ theo agent_key | Trùng tên thì phải chọn trong gợi ý (mã ghi theo thứ tự chọn); gõ tay tên trùng thì không gọi ai và báo | `teams.js mentionScan` |
| Tạo, thêm nhóm | Hộp chọn kiểu Zalo, lớp phủ gắn vào `<body>` | `team-picker.js`, `teams.js`, `console.css` |
| Tab Công việc | `GET/POST /agents/{slug}/jobs`; gom theo agent_key, đọc bản ghi gốc; Giao việc tạo một việc Kanban mang khoá `agent:<mã>:<slug>:<nonce>` | `agent_jobs.py`, `main.py`, `tasks.py`, `task_store.py`, `agent-jobs.js`, `workspace.js` |
| Bỏ reviewer cố định | Mục tiêu mới không gắn đội; migration một lần cho mục tiêu cũ | `resonance_store.py`, `resonance_api.py`, `resonance-agent.js`, `chat-resonance.js` |
| Auto | Đổi tên hiển thị, công tắc trong thẻ, mục trong menu ba chấm dùng chung `doiAuto` | i18n, `resonance-agent.js`, `workspace.js`, `console.css` |

### Bằng chứng Codex chỉ chữ (Codex CLI 0.153.4, bản Docker đang ghim)

Chạy `codex exec` thật trỏ vào một máy chủ Responses giả trên máy (không gọi OpenAI), ghi lại thân request:

- Mặc định: công cụ gửi cho model là `exec_command, write_stdin, request_user_input, apply_patch, view_image, get_goal,
  create_goal, update_goal, tool_search, web_search`.
- Với cờ của `codex_text_only`: chỉ còn `request_user_input` (chỉ dùng được ở Plan mode) và `apply_patch`.
- Máy chủ giả trả một `apply_patch` ghi file NGOÀI thư mục làm việc: Codex từ chối ở tầng chính sách (`patch rejected:
  writing is blocked by read-only sandbox; rejected by user approval settings`), file không được tạo.
- Tên `features.*` lạ với một bản Codex bị bỏ qua (đã thử), nên danh sách dư không làm hỏng bản khác.

### Tab Công việc: nguồn và trạng thái

- **Nhóm:** việc giao thẳng (`assignee_key`), việc điều phối (`coordinator_key`, bước plan, synthesize), và việc chỉ
  làm một bước con hay hỗ trợ (bước `work`, `help` trong `team_steps`). Tiến độ là số bước thật, vị trí thật trong hàng
  của nhóm, Huỷ đi route huỷ của nhóm.
- **Chat riêng:** việc Kanban có `chat_id` là phiên `agent:<slug>` đã ghim đúng mã (phiên ghim mã cũ cùng slug bị loại),
  và việc giao bằng nút Giao việc. Metadata của việc Kanban bị ghi đè khi việc chạy xong, nên quyền sở hữu nằm ở khoá
  idempotency (bền suốt đời việc). Tiêu đề kèm tên trợ lý để Kanban không gộp hai việc cùng chữ của hai trợ lý.
- **Auto:** mục tiêu của trợ lý (`goal_agents`) và mục tiêu cũ trợ lý đang là người review. Mã lý do `review_removed`,
  `paused` hiện bằng lời thường.
- **Hàng chờ trung thực:** brain tắt "AI tự vận hành" thì việc giao trực tiếp ghi rõ chỉ nằm chờ; chân tab nêu trần
  việc nền chạy cùng lúc (`JAVIS_KANBAN_MAX_WORKERS`).
- Việc Kanban giao cho trợ lý chạy với vai của trợ lý (lời nhắc như ở quy trình, nối vào lời nhắc hệ thống). Engine,
  quyền và trần của Kanban giữ nguyên. Đọc tab không tạo gì; chat thường không tự tạo việc.

### Migration bỏ người review cố định

Chạy một lần khi mở kho (dòng `review_migrations`), chép trước `resonance.sqlite3.pre-0.142.0`:

- Mọi cặp `team_pairs` tắt (`enabled=0`, tăng `config_version`), dòng giữ nguyên.
- Mỗi mục tiêu còn đội `active`: đội `detached` bởi `host:review_removed`, sự kiện `team_detached` ghi trạng thái chạy và
  lý do chặn trước đó, lý do thức của vai review chốt `superseded`. Mục tiêu đang mở bị **tạm dừng**, chặn thuộc đội gỡ
  về `ready`.
- Không dùng lại `team_detach` của chủ: lệnh đó hẹn thức ngay, và lần thức đó chốt theo luật A4, có thể kết thúc
  `succeeded` mà không ai review (test A5 T24, T46 khẳng định đúng điều này).
- Không xoá gì: `reviews`, `team_calls`, `goal_events`, bản nộp và file đích giữ nguyên. Chủ thấy mục tiêu ở ngăn Cần
  bạn và trên thẻ: Tiếp tục, sửa, huỷ, hay giao một việc kiểm chứng.

## 3. Kiểm

**Test mới:**
- `tests/python/test_team_chat_0142.py`: chọn model, dựng engine từng provider, Codex `read-only` khi tắt sandbox, kết
  cục lượt (chờ, đang trả lời, xong, lỗi), một lượt lỗi không mất lượt sau, Thử lại không nhân đôi tin, lượt hay kết
  quả, gửi lại cùng `client_msg_id`, nhóm tạm dừng, khởi động lại, việc bị chặn có tin trong chat.
- `tests/python/test_agent_jobs_0142.py`: route thật, vai trong việc nhóm (giao, điều phối, hỗ trợ), huỷ một việc không
  đụng việc khác, Giao việc chống trùng, không gộp theo tiêu đề giữa hai trợ lý, phiên chat riêng, vai khi chạy, không
  nguồn nào lỗi ngầm.
- `tests/python/test_review_removed_0142.py`: kho thời A5 có mục tiêu đang chờ review, giả lập kho trước 0.142.0, mở
  bằng mã mới; không tự đạt kể cả khi thức lại, lịch sử giữ nguyên, có bản sao, chạy lại không đổi gì.
- `tests/js/test_team_chat_0142.js`: @ trùng tên, dòng trạng thái lượt, hộp chọn, tab Công việc, Auto.

**Test cũ cập nhật theo thiết kế mới** (ghi rõ vì sao trong từng file): `test_team_t1_review.py` (điểm thay engine),
`test_teams_ui.js`, `test_workspace.js`, `test_tab_thu_muc.js`, `test_team_t0_toggle.js`, `test_resonance_a5_ui.js`,
`test_resonance_a5_api.py` (route đặt reviewer trả 410), `test_resonance_a5_team.py` (T31: đường `javis_goal` thật không
gắn đội), `test_resonance_a5_rollback.py` và helper `_resonance_team.py` (bật lại việc gắn đội để dựng kho thời A5).

**Kết quả trên container:** `tests/run.py --js` 187/187. `tests/run.py --py` 503/512 lần đầu; 9 file đỏ đều không do
thay đổi này (thiếu `pytest` trong `.venv` cho 7 file, `test_khoi_dong_nhe` đo thời gian lúc máy đang chạy nặng, và
`test_icons` bắt hai ký tự dự phòng trong `team-picker.js`, đã sửa). Cài `pytest` rồi chạy lại cả 9: xanh.

**Smoke trình duyệt thật** (Chromium qua Playwright, sandbox cổng 7788, state và brain tạm, model chính Claude `haiku`
thật, model việc nền đặt Codex để tái hiện ca lỗi gốc, không Telegram, Zalo hay kênh ngoài nào):

- 1366x860: tạo nhóm qua hộp chọn (tìm "muc tieu" ra Coach, lọc tag rồi đổi tag vẫn giữ người đã chọn, Điều phối mặc định
  là người đầu tiên), vào chat ngay. Tin thường: trưởng nhóm trả lời bằng model thật. @One khi có hai trợ lý tên One: chọn
  bản B, đúng bản B trả lời. Trợ lý có model không tồn tại: dòng "Chưa trả lời được" kèm câu lỗi thật và nút Thử lại;
  bấm Thử lại chạy đúng một lượt. Giao việc ngắn: kết quả về khung chat với nhãn "Kết quả việc", và hiện ở tab Công việc
  ngăn Đã xong. Tải lại trang: trạng thái lượt còn nguyên. Giao việc từ tab Công việc khi AI tự vận hành tắt: ghi rõ chỉ
  nằm chờ. Công tắc Auto trên thẻ và mục Auto trong menu ba chấm.
- 768x1024: khung chat nhóm, hộp chọn giữa màn hình.
- 375x812: hộp chọn đầy màn hình, footer cố định ở đáy (737 tới 806 trên 812), không tràn ngang; vùng chạm công tắc
  Auto 87x44; tab Công việc trong ngăn kéo phải.
- Lỗi tìm được nhờ smoke và đã sửa: lớp phủ hộp chọn bị thanh trên của app che trên điện thoại (nay gắn vào `<body>`),
  chi tiết lỗi hiện "(success)" thay vì câu lỗi thật, nhãn việc đã xong chỉ còn mã sau khi tải lại, ghi chú thừa dấu
  chấm, "Nhóm Nhóm ..." ở nguồn của việc.

## 4. Review độc lập toàn bộ thay đổi

Một agent review mới đọc cả `origin/main..HEAD` (không chỉ bản sửa cuối), tự chạy test nhóm, 0142, A5, i18n.
Kết luận: 1 Blocking, 2 Important, 6 Minor. Đã sửa hết, mỗi mục có test:

| Mức | Phát hiện | Sửa | Test |
|---|---|---|---|
| Blocking | Tab Công việc gắn lại trên cùng khung thì chồng trình nghe: một lần bấm Giao tạo nhiều việc, Huỷ hỏi nhiều lần | Trình nghe gắn một lần cho khung, chuyển cho lần gắn đang sống | `test_team_chat_0142.js` (gắn ba lần, một POST) |
| Important | Quyền "Không giới hạn" cũ (`anthropic-cli`) nay phủ cả lượt chạy model chính mà chủ chưa từng đồng ý | Quyền có `providers_v=2`; quyền cũ không cho provider nào Không giới hạn, trần về mức nhóm tới khi chủ cấp lại | `test_team_chat_0142.py` |
| Important | Lượt cũ về muộn ghi đè kết cục của lần Thử lại; phục hồi đánh "restart" cả lượt vừa gửi | `settle_reply` theo `attempt` và chỉ khi lượt còn mở; phục hồi chỉ đụng lượt ghi trước lúc tiến trình khởi động | `test_team_chat_0142.py` |
| Minor | Bị huỷ giữa chừng thì lượt phía sau nằm "đang chờ" mãi; việc nền không tạo được cũng vậy | Huỷ thì chốt cả lượt chưa chạy là lỗi `interrupted`; chờ quá 10 phút thì có Thử lại | `test_team_chat_0142.py`, `.js` |
| Minor | Lý do `leader_changed`, `superseded` không có nhãn | Thêm nhãn vi/en | `.js` |
| Minor | Enter ở ô tên nhóm không chuyển sang ô tìm (hộp chọn đã ra `<body>`) | Tìm trong lớp phủ | |
| Minor | Giao việc báo vào phiên của trợ lý cũ cùng slug | Chọn phiên đã ghim đúng mã, không có thì mở mới | `test_agent_jobs_0142.py` |
| Minor | Nonce toàn ký tự lạ thành rỗng, mọi lần giao chung một khoá | Kiểm sau khi lọc, 400 | `test_agent_jobs_0142.py` |
| Minor | Tham số `metadata` thừa | Bỏ | |

Đã kiểm không có lỗi: lượt nhóm không bao giờ có công cụ (Claude, Codex, API, Grok và Antigravity bị từ chối), không lẫn
dữ liệu giữa các brain, mọi HTML mới đều escape, migration không tự đạt và không xoá lịch sử, chat thường không tạo việc,
tắt Auto không đụng việc nhóm hay Kanban.

## 5. Hạn chế còn lại

- Smoke với provider thật chỉ có Claude (container không có đăng nhập ChatGPT). Đường Codex được kiểm bằng Codex CLI thật
  với máy chủ Responses giả, không phải một lượt ChatGPT thật.
- Grok Build và Antigravity chưa chạy được lượt nhóm: còn công cụ đọc native (Grok) hay MCP dùng chung file của máy
  (`agy`). Trợ lý đặt hai model này dùng model chính, kèm ghi chú trên tin.
- `apply_patch` của Codex không tắt được bằng cờ; lớp chặn là `--sandbox read-only` cộng kiểm sự kiện công cụ của
  `TextOnlyOutcome`.
- Việc giao bằng nút Giao việc chạy trên engine việc nền của Kanban (giữ nguyên quyền và trần), với vai của trợ lý; nó
  không dùng model riêng của trợ lý như lượt chat nhóm.
- Quyền "Không giới hạn lượt" cũ ghi `aux` không còn khớp lượt nào (lượt nhóm nay ghi provider thật): trần về mức của
  nhóm, tức chặt hơn.
- Chưa merge, chưa triển khai VPS.

## 6. Đối chiếu goal-claude-v2 và audit

Phiên thứ hai (14/10/2026, máy Windows của chủ repo, đọc được `exports/reviews/team-chat-zalo-ux-2026-10-14/`): đối chiếu
từng yêu cầu của `goal-claude-v2.txt`, từng phát hiện của `audit.md` và ảnh 01 tới 08 với mã trên nhánh (HEAD `f225ba1`).
Ba agent đọc mã song song theo nhóm mục (1-3 và 7, 4-5, 6 và 8-9), mỗi mục ghi Đạt, Thiếu hay Sai kèm `file:dòng`; phần
thiếu và sai sửa trên cùng nhánh, giữ số 0.142.0. Mục đã Đạt từ phiên trước là các mục ở phần 2 phía trên.

### Bảng đối chiếu (mục Thiếu hay Sai lúc đối chiếu)

| Mục goal / audit | Lúc đối chiếu | Đã sửa | Bằng chứng |
|---|---|---|---|
| 1. Ngữ cảnh nhóm nội bộ trong lời nhắc (không phải nhóm Zalo khách, không im theo luật chatbot, không gửi ra Zalo) | Thiếu | `INTERNAL_GROUP_NOTE` nối sau lời nhắc trợ lý trong mọi lượt nhóm | `team_runner._prepare`, `test_team_chat_0142_review.py` mục 1 |
| 1. Tin của AI không phải lệnh mới của chủ | Thiếu | Cùng đoạn trên: chỉ tin "Chủ nhóm" là yêu cầu | như trên |
| 1. Ghi rõ thay đổi hợp đồng T1/R3 | Thiếu ở tài liệu thiết kế | Ghi chú dưới R3 | `docs/dev/team-chat-t1.md` |
| 1. Grok/Antigravity | Sai so với biên bản (báo lỗi thay vì model chính) | Chạy model chính, ghi chú trên tin | `team_engine.text_only_supported`, test mục 5 |
| 2. Timeout | Thiếu: lượt treo nằm "đang trả lời" mãi | Trần `JAVIS_TEAM_TURN_TIMEOUT` (600 giây), lỗi `timeout` có Thử lại; giết đúng tiến trình engine của lượt trước khi nhả khoá bận | `team_runner._turn`, `main._team_engine_for.run` (tag theo lượt) |
| 2. Lỗi đăng nhập, model | Sai: chung một nhãn, chỉ có Thử lại | Lý do `auth`; nút Mở trang Models, Đổi model của trợ lý | `replyActions` (`teams.js`) |
| 2. Thiếu điều phối | Sai: tin không có dòng kết cục | Dòng `__leader__` lý do `no_leader`, nút Chọn điều phối; Thử lại giao đúng một lượt cho điều phối hiện tại | `team_runner.retry_reply`, test mục 3 |
| 2. Hết lượt, tạm dừng, điều phối rời | Sai: chỉ Thử lại | Mở giới hạn của nhóm, Chạy lại nhóm, Chọn điều phối; nhóm tạm dừng chưa có điều phối vẫn có dòng | như trên |
| 2. Bận việc khác | Yếu: chỉ "Đang chờ" | "Đang chờ: trợ lý đang làm việc ở nhóm X" | `_acquire(on_wait)`, test mục 4 |
| 2. Mất WebSocket | Sai: gói lỡ không tải lại | `hello` lần hai phát `team_resync`, trang Nhóm tải lại tin, hàng việc, nhóm | `app.js`, `onTeamEvent` |
| 3. Chọn từ gợi ý không suy lại theo tên | Sai | Lựa chọn lưu `{agent_key, label}`; token còn nguyên thì gọi đúng mã, sửa hay xoá token thì bỏ; lựa chọn mới nhất thắng | `mentionScan`, `pickMention` |
| 3. Token riêng trong composer, xoá token là bỏ gọi | Thiếu | Hàng "Gọi:" mỗi người một thẻ có nút x (xoá đúng token, không phá token dài hơn của người khác) | `callsHtml`, `removeMention` |
| 3. Tìm không dấu; lên/xuống, Enter, Escape; ảnh, tên, vai, slug | Sai, Thiếu | Tìm không dấu theo đầu từ bất kỳ (tên, slug, vai); listbox có `aria-activedescendant`; phím xử lý trước Escape của ngăn; bỏ qua khi đang gõ IME | `mentionMatches`, `sugKey`, `member_views.title` |
| 3. Email không mở gợi ý | Sai một phần | `emailBefore` | `test_team_chat_0142_review.js` |
| 4. Chip "Chưa có tag", ảnh ghép xem trước, mô tả thu gọn | Thiếu, Sai | Có | `team-picker.js` |
| 4. Điều phối chọn ngay trên danh sách đã chọn; bỏ điều phối thể hiện rõ | Sai (select riêng, chuyển ngầm) | Nút Điều phối trên chip; bỏ thì để trống, báo rõ, khoá nút Tạo tới khi chọn lại | `normalize`, `canSubmit` |
| 4. Chống tạo trùng phía server, ít nhất một trợ lý, một giao dịch | Thiếu | `client_req_id` (chỉ mục duy nhất theo brain), 400 khi không có trợ lý, nhóm + thành viên + điều phối trong một giao dịch, phiên mồ côi bị xoá | `team_store.create_team`, `team_api.teams_create`, test mục 6 |
| 4. Tạo xong focus composer; đang tải, lỗi tải | Sai, Thiếu | Có | `drawComposer`, `loadRoster` |
| 4. Thêm thành viên: "Đã tham gia", chỉ đếm người mới | Sai (ẩn người đã có) | Hiện, khoá ô chọn, "N người mới" | `team-picker.js` |
| 5. Người tạo lấy từ phiên xác thực server; nhóm cũ migration | Thiếu | Cột `created_by` (nhóm cũ nhận `owner`), `team.creator` do server điền, client khai thì bỏ qua | `team_store`, `team_api.creator` |
| 5. "Bạn + N trợ lý" ở đầu nhóm và danh sách thành viên | Sai | `headLine`, tiêu đề mục Thành viên | `teams.js` |
| 5. Không bị bàn phím che (hộp chọn) | Sai trên iOS | Hộp chọn co theo `--vv-h` khi `kb-open` | `console.css` |
| 6. Lọc nguồn, phân trang | Thiếu | Có (không còn trần ẩn việc) | `agent_jobs.collect`, `agent-jobs.js` |
| 6. Thẻ: cập nhật gần nhất, bước cần làm | Thiếu | `updated_at`, `next` (vị trí hàng, đang chờ nhóm khác, cần bạn, bật AI tự vận hành) | như trên |
| 6. Vai Điều phối, Thực hiện, Hỗ trợ, Kiểm chứng | Sai nhãn | Đổi | i18n `ajobs.role.*` |
| 6. Giao việc: tiêu chí xong, nơi nhận kết quả, xác nhận | Thiếu | Có; giao vào nhóm đi đúng `runner.submit` của nhóm; tiêu đề việc nhóm lấy đoạn đầu | `main.agent_jobs_assign`, `_enqueue_for` |
| 6. Tiếp tục, ưu tiên; Huỷ mục tiêu có revision | Thiếu | Tiếp tục (`resume` + `expected_revision`), Ưu tiên việc nhóm qua route sẵn có | `agent-jobs.js` |
| 6. Sửa ở một nơi đồng bộ nơi khác | Thiếu | Nghe sự kiện nhóm, mục tiêu, phiên, việc; không vẽ lại khi đang gõ form hay IME | `agent-jobs.js` |
| 7. Không mở nhiều lượt model chỉ vì nhiều việc | Thiếu ở việc giao từ Cộng sự | Kanban: một việc `agent:` đang chạy mỗi trợ lý, việc khác vẫn chạy (FIFO) | `task_store.next_candidate`, `claim` |
| 7. Vai theo nhân dạng | Sai: tra theo slug | `_agent_persona(root, slug, agent_key)` kiểm mã | `tasks._persona` |
| 8. Kiểm chứng là việc riêng, liên kết rõ | Thiếu | Kiểu "Kiểm chứng" trong Giao việc, bắt buộc tiêu chí, liên kết mục được kiểm, chặn tự kiểm việc của mình; nút "Giao kiểm chứng" trên thẻ | `agent_jobs.resolve_link`, `/agents/{slug}/jobs/verify-targets` |
| 8. Test migration đủ trạng thái | Thiếu | `review_changes`, đang chạy, bị chặn lý do khác, chưa bắt đầu, thất bại | `test_review_removed_0142.py` |
| 9. Còn chữ "Cộng hưởng", "trưởng nhóm" trên giao diện | Sai | "Auto" ở cài đặt và tin hệ thống; "trưởng nhóm" thành "điều phối" trong giao diện nhóm (vi/en) | i18n, `team_runner.py`, `index.html` |
| 9. Đồng bộ Auto với trang Nhóm; badge việc tách Auto | Thiếu | Trang Nhóm nghe `javis:resonance-agents-changed`; huy hiệu việc (đang làm, cần bạn) riêng trên thẻ | `teams.js`, `workspace.js`, `/agents/jobs/counts` |
| Ảnh 01 (khung chat im) | Đạt sau sửa | Smoke thật bên dưới | `smoke-0142/1366-error-row.png` |
| Ảnh 02, 04, 07 (form phẳng; luồng Zalo) | Đạt sau sửa | | `smoke-0142/1366-picker.png`, `375-picker.png`, `1366-add-members.png` |
| Ảnh 03, 05, 06 (thông tin nhóm Zalo) | Đạt trong phạm vi | Panel có người tạo, điều phối, thành viên, Thêm, ghim, trạng thái, quyền; link mời, bình chọn, xoá lịch sử ngoài phạm vi goal | `smoke-0142/1366-team-panel.png` |
| Ảnh 08 (hàng "Cộng hưởng: Bật" ngoài thẻ) | Đạt | Công tắc Auto trong thẻ, cam khi bật | `smoke-0142/375-auto-on.png`, `375-menu.png` |

### Review độc lập vòng 2 (phần thay đổi mới, `f225ba1..81eb61c8`)

Không có lỗi chặn. Đã sửa, mỗi mục có test:

| Mức | Phát hiện | Sửa |
|---|---|---|
| Important | Lựa chọn @ cũ giành token của lựa chọn mới ("Lan" rồi "Lan Anh") | Xét lựa chọn mới nhất trước; bỏ lựa chọn mất token khi chọn người mới |
| Important | Quá trần thời gian chỉ huỷ phía đọc, tiến trình Codex còn sống, khoá bận đã nhả | Tag theo lượt, `cancel_all(tag)` và `aclose()` trước khi nhả khoá |
| Important | Tab Công việc vẽ lại cả khung lúc đang gõ form | Hoãn tải lại khi form mở, ô nhập đang focus hay đang gõ IME |
| Minor | Bỏ gọi một người phá token dài hơn của người khác | Bỏ qua chỗ mà tên người khác dài hơn cũng khớp |
| Minor | Nhóm tạm dừng mà chưa có điều phối: tin không có dòng | Dòng `__leader__` lý do `team_paused` |
| Minor | Đếm việc cho huy hiệu chạy cả khi đang xem Quy trình hay tab ẩn | Chỉ khi danh sách trợ lý đang hiện |
| Minor | Đọc kho trên vòng sự kiện trong `waiting` | Đưa qua `_io` |
| Minor | Phiên mồ côi khi tạo nhóm lỗi | Xoá phiên |
| Minor | Tạo được nhóm không có điều phối | Khoá nút Tạo tới khi chọn |
| Minor | Kanban từ chat riêng (không có khoá `agent:`) và lượt nhóm vẫn có thể chạy cùng lúc với việc được giao | Ghi ở hạn chế, chưa sửa |

### Smoke với provider thật (sandbox cổng 7788, state và brain tạm, không Zalo, Telegram hay khách)

Cấu hình như máy thật trong audit: model chính và model việc nền đều OpenAI OAuth (Codex CLI 0.160.0 trên máy),
`gpt-6.1-sol`. Javis Vũ Zalo đặt riêng Codex `gpt-6.1-sol`, lời nhắc có luật chatbot Zalo "im lặng khi không được gọi";
Coach không đặt model (theo model chính); hai trợ lý cùng tên One đặt Claude `haiku`.

Năm lần gọi model, dừng ở đó:

1. Tin thường: Javis Vũ Zalo (điều phối) trả lời sau 10 giây bằng `openai-oauth gpt-6.1-sol`, không im theo luật chatbot.
2. @One chọn bản A bằng phím mũi tên: đúng bản A trả lời (`anthropic-cli haiku`).
3. Giao việc ngắn cho Coach: chạy bằng model chính Codex, kết quả về nhóm, hiện ở tab Công việc ngăn Đã xong sau tải lại;
   Mở đưa về đúng nhóm.
4. One bản B đặt model không tồn tại: dòng "Chưa trả lời được: Model báo lỗi..." kèm câu lỗi thật, nút Đổi model và Thử
   lại; tải lại trang vẫn còn. (Đính chính: biên bản ban đầu ghi "khởi động lại server rồi tải lại vẫn còn". Sai: lệnh tắt
   chỉ giết tiến trình vỏ của `.venv`, tiến trình Python con giữ cổng 7788, nên các lần "khởi động lại" sau đó không bind
   được và trình duyệt vẫn nói chuyện với server khởi động đầu tiên (mã `81eb61c8`). Phần server sửa sau đó, cùng việc lượt
   dở thành `restart` sau khởi động lại, chỉ được kiểm bằng test tự động, không bằng smoke.)
5. Sửa model rồi bấm đúp Thử lại: đúng một lượt mới, bản B trả lời.

Không gọi model: tạo nhóm bấm đúp (một nhóm), bỏ điều phối có cảnh báo, Thêm thành viên ("Đã tham gia", "0 người mới"),
Giao việc vào chat riêng có tiêu chí và bước xem lại (bấm đúp Xác nhận vẫn một việc; AI tự vận hành tắt nên ghi rõ chỉ nằm
chờ), email không mở gợi ý, token Gọi bỏ được, Auto bật trên thẻ và tắt trong menu ba chấm.

Số đo: 1366, 768, 375 không tràn ngang (`scrollWidth` bằng bề ngang); hộp chọn ở 375 đầy màn hình, footer 743 tới 812;
chữ nhỏ nhất trong hộp chọn 16px; công tắc Auto 87x44. Smoke bắt thêm hai lỗi, đã sửa: danh sách gợi ý @ ở giao diện tối
có nền gần trong suốt (`--surface-1`, lỗi có sẵn); thanh lọc theo việc đã xong hiện mã việc thay vì tên. Ảnh:
`exports/reviews/team-chat-zalo-ux-2026-10-14/smoke-0142/`.

### Hạn chế còn lại

- Kanban từ chat riêng và lượt nhóm chưa chung khoá bận với việc giao từ tab Công việc; trần chung vẫn là
  `JAVIS_KANBAN_MAX_WORKERS` và khoá bận của nhóm.
- Việc Kanban chưa có route ưu tiên nên tab Công việc chỉ có Ưu tiên cho việc nhóm. Lần chạy quy trình (`wf:`) chưa có
  định danh trợ lý nên chưa vào tab.
- Ảnh nhóm chưa đổi được (ghép từ ảnh trợ lý), nên không có nút đổi ảnh. Link mời, bình chọn, nhiều tài khoản ngoài phạm vi.
- Chưa merge, chưa triển khai VPS.

### Sau báo cáo: công tắc Auto lên hàng tag

Chủ repo xem ảnh 375 và yêu cầu (14/10/2026): công tắc Auto ở hàng riêng dưới đáy thẻ khó biết thuộc trợ lý nào. Nay công
tắc nằm trong thẻ, CÙNG HÀNG với tag, bên phải; nút ba chấm lên ngang hàng tên để tag còn đủ chỗ ở cột hẹp; trợ lý chưa có
tag thì công tắc giữ một hàng đáy riêng. Đo trên trình duyệt: tâm công tắc lệch tâm tag tối đa 1px, tag không bị cắt chữ ở
1366 và 375, không chồng nút ba chấm, vùng chạm 44px trên màn cảm ứng. Thẻ cũng gọn hơn một hàng.

### Sau báo cáo: bố cục trang Cộng sự

Chủ repo yêu cầu (14/10/2026, kèm ảnh danh sách chat có giờ):

- **Giờ nhắn gần nhất** trên thẻ trợ lý, cùng hàng tên (hôm nay giờ:phút, hôm qua "Hôm qua", xa hơn ngày/tháng). Dữ liệu là
  `last_chat_at` sẵn có của `/agents` (cũng là thứ tự danh sách); nay chỉ tính phiên đã có tin, vì bấm vào trợ lý là trang
  tạo sẵn một phiên trống. Xong một lượt chat thì giờ trên thẻ đổi ngay.
- **Cột phải mặc định ẩn** ở màn rộng; nút góc phải hiện lại và lựa chọn được nhớ (`javis_ws_right`). Mở Cài đặt để xác nhận
  trợ lý vẫn tự hiện cột mà không ghi đè lựa chọn. Màn hẹp giữ ngăn kéo như cũ.
- **Cột danh sách rộng hơn** (mặc định `clamp(240px, 24vw, 320px)` thay 210-260px) và **kéo được** ở đường biên, cả cột phải;
  có tay kéo bàn phím (mũi tên trái/phải 16px), nhấp đúp về mặc định, chặn 220-560px (trái) và 280-640px (phải), không quá
  45%/50% bề ngang trang; nhớ qua `javis_ws_left_w`, `javis_ws_right_w`.
- **Cột phải ẩn thì chữ rộng ra:** bong bóng trả lời giãn tới `min(120ch, 100%)` thay vì 72 ký tự.

Đo trên trình duyệt: 1366 cột trái 320px, kéo thêm 80px được 400px và còn sau tải lại; cột phải hiện, kéo 350 thành 430px;
bong bóng 846/850px của khoang giữa khi cột phải ẩn (1366), 1298px ở 1920 (trần 120 ký tự); 375 không có tay kéo, không tràn
ngang, giờ cùng hàng tên. Chữ giờ 14px để bằng tên trợ lý ở cột hẹp (ngoại lệ có chủ ý so với sàn 16px của phần mới).
Test: `tests/js/test_cong_su_bo_cuc_0142.js`, thêm một kiểm ở `test_sessions_kenh_cong_su.py`.

### Rà soát trước khi phát hành

Chủ repo yêu cầu rà lại toàn bộ trước khi merge. Hai agent đọc độc lập `origin/main...HEAD` (server và giao diện), tự chạy
mã và test; không có lỗi chặn. Kiểm thật: nâng cấp `team.sqlite3` dựng bằng mã `origin/main` (mở hai lần, mã cũ vẫn mở được
kho đã nâng cấp), migration Cộng hưởng, phục hồi lúc khởi động, khoá một việc mỗi trợ lý của Kanban, tag giết tiến trình theo
lượt. Khởi động lại server sandbox thật (tắt theo cổng): server lên lại, dòng trạng thái lượt trả lời còn nguyên.

Đã sửa, mỗi mục có test (`test_prerelease_0142.py`, `test_team_chat_0142_review.js`, `test_cong_su_bo_cuc_0142.js`):

| Mức | Phát hiện | Sửa |
|---|---|---|
| Important | Huy hiệu việc và danh sách kiểm chứng mở một kết nối kho Cộng hưởng cho MỖI phiên: 15 giây với 20 trợ lý x 150 phiên trên Windows, request chồng nhau làm nghẽn luồng phụ | `session_pins` đọc một lần; trang chỉ chạy một lượt đếm mỗi lúc |
| Important | Thu cửa sổ còn nửa màn hình thì cột phải bật ra đè khung chat (lớp `right-open` đổi nghĩa theo khổ) | Nghe đổi khổ màn, đặt lại theo nghĩa mới |
| Important | Nút "Vị trí file" ở trang Cộng sự bấm không ra gì (tab Thư mục đã bỏ) | Mở trang Tệp tin và soi file trong cây |
| Important | Dòng trạng thái của người đã rời nhóm hiện mã thay vì tên | Tra sổ tác giả |
| Minor | @ người đã rời nhóm: tin không ai trả lời và câu báo bị lọc mất (chứa mã có `_`) | Câu báo bằng tên; khung soạn chỉ lọc mã |
| Minor | Trần 10 phút áp cả bước của việc nhóm (trước không có trần) | Trả lời chat 10 phút, bước việc nhóm 60 phút (`JAVIS_TEAM_STEP_TIMEOUT`) |
| Minor | Việc giao báo về phiên đã lưu trữ hay phiên trống | Ưu tiên phiên chưa lưu trữ đã có tin |
| Minor | Chạy tay việc Kanban khi trợ lý đang bận trả `ok:false` không lý do | Câu lý do vi/en |
| Minor | Hộp chọn mất focus sau khi chọn, Escape không đóng; tab Công việc vẫn hỏi server sau khi rời tab; Thử lại có thể kẹt; lưu Cài đặt thu cột phải dù chủ chọn hiện; laptop 1061-1240px mất bề rộng cũ của cột phải; kéo hai cột có thể bóp khung chat còn ~100px | Sửa từng mục; khung chat luôn còn ít nhất 360px |
| Minor | Lỗi `nonce` trả mã thô | Câu vi/en |
