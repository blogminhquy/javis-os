# Team làm việc nhiều ngày: cổng duyệt thật, mục tiêu phòng ban, nghiệm thu (0.207.0 tới 0.210.0)

Ngày: 2026-10-17. Nền: main 0.206.0. Khảo sát mã trước khi làm: tóm tắt ở mục 0.
Nguyên tắc chung: mở rộng cơ chế đang có (TeamRunner, làn team của Kanban, mức quyền suggest/auto/full của hub,
pulse, ledger, outbox, evidence_store), không dựng hệ thống song song. Engine giả trong mọi test.

## 0. Hiện trạng đã kiểm (bản 0.206.0, không mặc định lỗi cũ còn)

- Lỗi "hỏi duyệt mà vẫn done" CÒN: `asks_owner` (team_runner `_post`, regex `ASKS_OWNER_RE`, chỉ trưởng nhóm) chỉ là cờ hiển
  thị và báo máy. `_apply_step_locked` không đọc nó: bước `plan` không giao ai thì `_finish` lấy chính câu hỏi làm kết quả
  việc; bước `work` thì `finish_step(done)` rồi `_after_steps` chốt việc. Server chưa bao giờ phát block kind `waiting_user`
  dù spec 2026-10-13 và dashboard đã có nhãn, nút cho nó.
- Lượt Làm/Hỗ trợ chạy mức `full` cố định (`TEAM_WORK_MODE`), không có chốt trước công cụ: hub cho mọi tool, Claude ở
  bypassPermissions không có PreToolUse.
- `unblock("resume")` chỉ xếp lại việc: không còn bước chờ thì `_after_steps` chốt luôn bằng kết quả cũ. Duyệt phải THÊM bước.
- Pulse theo từng agent, nguồn cơ hội chỉ từ việc nhóm và mục tiêu (`_pulse_opportunities`: blocked_new_data, stale_job,
  proposal_open, goal_waiting). Không có nguồn file, test, MCP; không có hạn, cooldown, bằng chứng cho cơ hội.
- Kanban chốt done theo một lượt model đọc báo cáo (`_check_acceptance`), lỗi checker thì vẫn done (`unverified`). Làn team
  không nghiệm thu gì. Kho artifacts chỉ có đường dẫn, không hash. Resonance đã có mẫu tốt (artifact_contract,
  human_confirmation gắn sha256, source_drift) để tái dùng.

## 1. Cổng chờ duyệt thật (0.207.0)

### 1.1 Dữ liệu (team.sqlite3, bảng mới, không sửa bảng cũ)

`team_approvals(approval_id PK, team_id, task_id, step_id, team_rev, requested_by, kind, title, action_json, scope,
impact, evidence_json, deadline_at, fingerprints_json, status, decided_by, decision, decision_note, decision_key UNIQUE,
decided_at, consumed_at, created_at, updated_at)` và `team_approval_events(id, approval_id, at, kind, by, detail_json)`.

- `kind`: `action` (một hành động cụ thể bị cổng chặn, có dấu vân tay), `plan` (phương án do agent xin bằng lệnh có cấu trúc),
  `question` (agent hỏi chủ quyết mà không dùng lệnh: lưới an toàn, xem 1.3).
- `status`: `pending` → `approved` → `consumed`; hoặc `rejected`, `changes_requested`, `expired`, `superseded`
  (yêu cầu sửa/đổi phương án/thành viên rời), `cancelled` (huỷ việc), `revoked` (thu hồi quyền).
- Mỗi việc tối đa một yêu cầu `pending` (chỉ mục duy nhất một phần).

### 1.2 Vòng đời

- Khi một bước tạo yêu cầu: bước sang `waiting_owner`, việc sang `team_blocked` kind `waiting_user` (nhả suất chạy). Không
  `finish_step(done)`, không `_finish`, không thêm bước giao việc, không chạy bước phụ thuộc. Kế hoạch có lệnh giao việc kèm
  xin duyệt: lệnh giao việc được GIỮ trong yêu cầu, chỉ thêm bước sau khi duyệt.
- Quyết định chỉ qua `POST /teams/{id}/approvals/{aid}/decide` (chủ đã đăng nhập): `approve | reject | changes`, kèm
  `expected_rev`, `decision_key` (mỗi cú bấm một khoá). CAS: yêu cầu còn `pending`, `team_rev` của việc vẫn bằng revision của
  yêu cầu, việc còn chặn `waiting_user`. Cùng khoá gửi lại trả đúng kết quả cũ (retry sau mất mạng). Khoá khác khi đã quyết
  trả `already_decided` (tab thứ hai). Sai revision trả `stale`.
- Duyệt: thêm MỘT bước mới cho người xin (cùng loại bước), brief nói rõ đã duyệt gì; ghi chú bước `approval:<id>`; rồi mới bỏ
  chặn (như `extend_job`). Bước `plan` được duyệt thì thêm các bước giao việc đã giữ. Dấu vân tay của yêu cầu `action` chỉ
  dùng được trong đúng bước đó và bị tiêu (consume) NGAY lúc cổng cho qua, trong một giao dịch: restart hay chạy lại bước
  không làm lại tác động; cần làm lại thì phải xin duyệt mới.
- Từ chối: yêu cầu `rejected`, bước `cancelled`, việc giữ chặn với kind `rejected` và lý do của chủ. Chủ chọn: huỷ việc, sửa
  yêu cầu (revision mới) hay giao lại cho trưởng nhóm tìm hướng khác (thêm bước plan kèm lời từ chối).
- Yêu cầu sửa: yêu cầu `changes_requested`; thêm bước cho người xin với lời góp ý, bỏ chặn. Phương án sửa là một yêu cầu MỚI.
- Hết hiệu lực: `team_amend` (sửa yêu cầu) → mọi yêu cầu chưa tiêu của việc thành `superseded`; huỷ việc → `cancelled`; đổi
  quyền nhóm (thu hồi `work_mode=full`, thu hồi Toàn quyền) → yêu cầu đã duyệt chưa tiêu thành `revoked`; thành viên xin rời
  nhóm → `superseded`. Quá `deadline_at` → `expired`, việc chặn kind `approval_expired`.
- Tin của agent, đoạn trích trong tin hay lời chủ gõ trong chat KHÔNG phải lời duyệt: không có lệnh JAVIS_TEAM nào quyết định,
  và parser không đọc chữ để duyệt. Thẻ duyệt hiện trong chat với nút Duyệt, Từ chối, Yêu cầu sửa.

### 1.3 Ai được tạo yêu cầu, và lưới an toàn

- Lệnh có cấu trúc (giao thức chính): `<!-- JAVIS_TEAM: {"op": "ask_approval", "title", "action", "scope", "impact",
  "evidence": [...], "deadline"} -->` trong bước `plan`, `work`, `help`. Mọi thành viên dùng được trong bước của việc.
- Cổng công cụ (1.4) chặn một hành động: host tự tạo yêu cầu `action` từ chính lời gọi đã bị chặn (tên công cụ, tóm tắt tham
  số, dấu vân tay). Đây là dữ liệu host quan sát, không phải lời model.
- Lưới an toàn: kết quả bước gọi chủ nhóm (`ASKS_OWNER_RE`, mọi thành viên chứ không chỉ trưởng nhóm) hay xin quyết định mà
  không có lệnh: host tạo yêu cầu `question` với đoạn trích, ghi rõ "agent hỏi bằng chữ, chưa nêu phương án có cấu trúc". Bước
  không thành done. Regex chỉ là lưới, không phải giao thức.

### 1.4 Cổng trước công cụ (đã làm, team_gate.py)

Quyền làm việc của nhóm, cột mới `teams.work_mode`:
- `gated` (mặc định, cả nhóm cũ): làm việc trong phạm vi (đọc, tìm, ghi file trong bộ não và thư mục nhóm, đọc kết nối,
  lệnh shell chỉ đọc) không hỏi; hành động ra ngoài (công cụ hub hạng `danger`: gửi, đăng, xoá, thanh toán, đặt hàng;
  công cụ plugin cần mức `full`; lệnh shell ngoài danh sách chỉ đọc; connector tài khoản Claude không phải lệnh đọc; ghi file
  ngoài thư mục được phép) phải có yêu cầu đã duyệt cho đúng lời gọi đó.
- `full`: chủ bật "Nhóm tự làm, không hỏi" (quyền như chat riêng của 0.194.0, không có cổng).

Mức hub mới `gated`: liệt kê công cụ như `full` (để hành động bị chặn có thể thành yêu cầu và chạy được sau khi duyệt), trần
như `auto` (`mcp_catalog._MODE_CAP`), nên chỗ nào không biết cổng thì đóng lại, không bao giờ chạy ở `full`. Khi `_guard` của hub
hay `plugins_host._make_call` thấy lời gọi bị trần `gated` chặn mà kết nối cho phép ở `full`, nó hỏi cổng của lượt
(`turn_context` khoá `team_gate`, đến qua `X-Javis-Turn` hoặc ContextVar). Có dấu vân tay đã duyệt cho bước này thì tiêu ngay
trong một giao dịch rồi cho qua; không thì từ chối TRƯỚC khi gọi và ghi lại lời gọi (tên, tham số, dấu vân tay). Không có cổng
sống (thiếu hay giả khoá lượt) thì từ chối.

Theo provider (`team_gate.provider_support`, `main._team_gate_support` đọc cờ thật của máy):
- Claude: hook PreToolUse của SDK (bypassPermissions không bỏ qua hook). Read/Glob/Grep/WebSearch/WebFetch/Task cho qua;
  Write/Edit chỉ trong thư mục nhóm và bộ não; Bash chỉ lệnh chỉ đọc (ls, cat, grep, git status... không ký tự shell, `find`
  không `-exec`/`-delete`); `mcp__javis__*` để hub tự chặn; connector tài khoản chỉ lệnh đọc. SDK không có hook thì từ chối.
- Codex: dựng ở `auto` (sandbox `workspace-write`, không mạng), hub ghi đè thành `gated` và bật khoá lượt. Không có sandbox
  (`JAVIS_CODEX_SANDBOX=off`) thì từ chối.
- API: mọi công cụ qua hub trong tiến trình ở mức `gated`.
- Grok Build: dựng ở `auto` (cấm Bash, hub `auto`). Grok không mang được khoá lượt tới hub (file cấu hình MCP dùng chung cho cả
  bộ não), nên chỉ làm được phần trong phạm vi; hành động đã duyệt không chạy được trên Grok. Bản không có `--deny` thì từ chối.
- Antigravity: không chặn được công cụ của chính nó trước khi chạy. Khi `gated`: từ chối bước, báo rõ "đổi trợ lý sang Claude,
  Codex hay model API, hoặc bật quyền full cho nhóm".

Lời gọi được duyệt chỉ dùng được trong đúng bước được mở (`granted_step`), mỗi dấu vân tay một lần. Bước được duyệt bị ngắt
(restart, lỗi) thì "Chạy lại bước" chuyển phần duyệt CHƯA dùng sang bước chạy lại; phần đã dùng không bao giờ chạy lần hai.

### 1.5 Giao diện

Thẻ duyệt trong chat nhóm (meta `kind: approval_request`): đang xin gì, phạm vi, ảnh hưởng, bằng chứng, hạn; ba nút. Trạng
thái thẻ đọc từ server (không đoán): đang chờ, đã duyệt bởi..., đã từ chối, đã hết hiệu lực vì... Danh sách yêu cầu chờ ở tab
Việc. Cài đặt nhóm có công tắc `work_mode`.

## 2. Mục tiêu phòng ban và cơ hội (0.208.0)

### 2.1 Mandate (team.sqlite3, bảng mới `team_mandates` có version, `team_mandate_events`)

Trường: outcome, metrics[], sources[] (loại + tham chiếu: `folder:<rel>`, `kanban`, `mcp:<conn_id>`, `test:<lệnh an toàn>`),
scope, budget (lượt quan sát/ngày, lượt việc tự sinh/ngày), cadence_min, autonomy (`act` các loại việc được tự làm,
`propose`, `approve` cần duyệt), stop_conditions[], status `off|active|paused|revoked`, version. Nhóm cũ không có mandate
(tắt). Bật, sửa (version mới), tạm dừng, thu hồi chỉ bởi chủ qua API; thu hồi chặn mọi hành động mới từ mandate.

### 2.2 Quan sát và cơ hội

- Bộ quan sát code trước, model sau, chạy theo cadence và budget của mandate, chỉ trên nguồn đã cấp:
  `folder` (dấu vân tay mtime/size/sha các file trong thư mục được cấp, giới hạn số file), `kanban` (việc lỗi/chặn mới của
  bộ não, `sentinel`), `mcp` (trạng thái kết nối `connect_health`, thiếu thì ghi "thiếu nguồn"), `test` (lệnh an toàn qua
  `run_command`, mã thoát).
- Mỗi quan sát lưu bền (`mandate_observations`: source, ref, version/hash, observed_at, summary). Thay đổi so với lần trước
  sinh cơ hội (`mandate_opportunities`: nguồn, ref, version, lý do gắn mục tiêu, lợi ích dự kiến, trạng thái, expires_at,
  cooldown_until, decision, trace). Khoá chống trùng `(team, source, ref, version)`. Bị bác thì không mở lại tới khi version
  nguồn đổi. Hết hạn sau N giờ không xử lý.
- Phân loại (code + một lượt model chỉ chữ có giới hạn): `none | watch | propose | ask | enqueue`. `enqueue` chỉ khi loại
  việc nằm trong `autonomy.act` VÀ budget còn VÀ không cần hành động ra ngoài (nếu cần thì thành `ask` qua cổng duyệt).
  Không có cơ hội thì không tạo gì. Nguồn thiếu kết nối hiện trạng thái thiếu nguồn, không bịa vấn đề.
- Việc tự sinh mang trace `mandate:<id>@v` → `opp:<id>` → quyết định → (duyệt) → việc → sản phẩm → nghiệm thu.

## 3. Nghiệm thu (0.209.0)

- Tiêu chí nghiệm thu gắn việc và revision (`team_acceptance` : criteria_json, policy, revision, accepted_by_owner_at). Loại
  tiêu chí: `file_exists`, `file_contains` (min_chars, must_contain), `json_schema` (khoá bắt buộc), `command_ok` (lệnh an toàn
  qua `run_command`, mã thoát 0), `owner_confirm` (chủ xác nhận đúng hash sản phẩm). Model review chỉ là bằng chứng.
- Sản phẩm: đường dẫn, sha256, kích thước, mtime lúc kiểm (evidence). Kết quả mỗi tiêu chí: `pass | fail | unknown`. Việc chỉ
  done khi mọi tiêu chí `pass` theo chính sách chủ đã chấp thuận; `unknown` hay `owner_confirm` chưa có thì chờ chủ. `fail` mở
  vòng sửa có giới hạn (`fix_rounds`, mặc định 2), quá thì chặn `acceptance_failed`.
- Sửa file sản phẩm sau khi đạt làm bằng chứng cũ hết hiệu lực (so sha). Lịch sử lưu bền. Tín hiệu hữu ích (`result_used`,
  `objective_pass`) ghi đúng một lần mỗi (việc, revision) khi nghiệm thu đạt hay chủ xác nhận, không từ lời agent.

## 4. Kiểm thử, review, pilot (0.210.0)

Test host thật với engine giả (đã liệt kê trong GOAL), đồng hồ giả nhiều ngày, nhiều nhóm. Review độc lập từng mốc. Gói pilot
trong `pilot/team-multiday/`: state và brain riêng, 3 nhóm mẫu, kịch bản 7 ngày, ngân sách, cách dừng, rollback, chỉ số, mẫu
báo cáo, ma trận yêu cầu. Chưa chạy pilot.

## 5. Di trú và quay về

Bảng mới, cột mới có mặc định (bản cũ bỏ qua được). Snapshot một lần trước khi thêm cột (`team_migration.snapshot_once`).
Quay về bản cũ: các bảng mới bị bỏ qua; việc đang chặn `waiting_user` hiện nút "Tiếp tục" của bản cũ.
