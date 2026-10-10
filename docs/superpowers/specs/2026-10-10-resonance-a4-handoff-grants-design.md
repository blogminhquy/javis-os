# Resonance A4: nộp sản phẩm đa engine qua một hợp đồng host, kèm quyền có phạm vi

**Trạng thái:** thiết kế **chốt** (vòng 5, phương án dự phòng D1), reviewer chấp thuận để code. **Mã A4 sửa theo review mã vòng 2, chờ review lại** (mục 17: I1, I2 đã được chấp nhận; I10 tới I15). Đổi cơ chế cấp quyền ngoài bản này thì gửi diff thiết kế review trước.

- **Nhánh:** `claude/resonance-a4-handoff-grants`, PR nháp #604, số **0.92.0** (đặt 0.90.0; `main` đi qua 0.91.0 nên đánh số lại).
- **Vòng 1** (`5edfc9b6`) chưa đạt: 3 P1, 2 P2 (`exports/reviews/PR-604-A4-design-r1-review.md`, ngoài git).
- **Vòng 2** (`99c88447`) chưa đạt: 1 P1, 3 P2, 6 lưu ý nhỏ (`exports/reviews/PR-604-A4-design-r2-review.md`, ngoài git).
- **Vòng 3** (`efa1fce3`) chưa đạt: 1 P1, 1 P2, 3 lưu ý nhỏ (`exports/reviews/PR-604-A4-design-r3-review.md`, ngoài git). Phần bản nháp, chấp thuận, `sealed`, tiếp nhận, khoá theo revision và legacy đã đạt ở mức thiết kế.
- **Vòng 4** (`bd6ad1d1`): thứ tự quyền và ba lưu ý đạt; bộ nhận chỉ thị còn nhận nhầm (`exports/reviews/PR-604-A4-design-r4-review.md`, ngoài git). Chốt phương án dự phòng D1: **A4 không cấp quyền từ lời chat**.
- Bảng đối chiếu từng điểm review ở mục 16. Kiến trúc và phạm vi giữ nguyên qua cả hai vòng.

**Nền và đầu vào:**

- **Nền:** thiết kế viết trên `main` `33a3c1aa` (0.89.0); mã đã merge `main` `1d0b515c` (0.91.0: 0.89.1, 0.89.2, DeepSeek). A1 0.87.0, A2 0.88.0, A3 0.89.0, bản hiệu năng 0.88.5 (#602) đã vào `main`.
- **Lộ trình:** [agent scope roadmap](2026-10-08-resonance-agent-scope-roadmap.md), mục 7 (A4, A5).
- **Đầu vào giao quyền** (ngoài git):
  - báo cáo Paperclip 08/10: `exports/reviews/paperclip-javis-assessment-2026-10-08.md`;
  - bản bổ sung 10/10: `exports/reviews/2026-10-10-resonance-delegation-paperclip-review-supplement.md`.

**Mức bằng chứng:**

- Đã khảo sát mã thật tại `9716cecf`, trùng `33a3c1aa` ở `server/`.
- Không gọi model. Chưa có mã hay test A4.
- Mục 2 là mã đã đọc. Mọi thứ khác là đề xuất.

## 1. Mục tiêu và ngoài phạm vi

**Mục tiêu A4:** mọi engine nộp sản phẩm của một mục tiêu theo **cùng một hợp đồng host**.

> Host xác định ai đang làm và ghim quyền của lượt đó. Engine nộp nội dung qua đường host kiểm. Host tự đọc và băm bytes, lưu thành bản nộp có biên nhận, rồi tự đăng vào đích qua quyền, guard và baseline thật.

Kèm theo là **quyền có phạm vi** học từ Paperclip, ở mức tối thiểu A4 cần:

- Phạm vi gốc do chủ dự án xác lập, độc lập với tiêu chí model sửa.
- Quyền của từng revision chỉ hẹp lại từ phạm vi gốc.
- Quyền được ghim vào từng lượt.
- Thu hồi bằng `generation`.
- Kiểm ở mọi điểm tác động.

A5 dùng lại đúng hợp đồng này cho cặp làm/review.

**Người dùng thấy:**

- Anh giao kết quả một lần.
- **Đích mới hay đổi phạm vi:** anh bấm Cho phép trên thẻ, kèm đúng đường file. Kể cả khi lời giao đã nêu đích, Javis vẫn hỏi một lần; A4 không suy quyền ghi từ lời chat.
- **Phạm vi đã cấp:** trợ lý tự làm tiếp, không hỏi lại từng bước hay từng lần sửa.
- **Bản nháp được giữ:** bản trợ lý soạn trước khi anh cho phép được giữ làm nháp. Anh bấm Cho phép thì Javis đăng đúng bản đó, bước này không gọi model. Mục tiêu chưa có bản nháp thì sau khi cho phép, việc nền chạy theo ngân sách lượt như thường.
- Thẻ mục tiêu hiện: được làm gì, trên file nào, tối đa bao nhiêu lượt, có được giao tiếp không, nút Thu hồi.

**Giữ nguyên:**

- **Luật hạn mức A1 tới A3:** giữ chỗ trong giao dịch, trần chung, "chưa gọi thì trả, đã gọi thì giữ", `call_holds`.
- **Luật đăng:**
  - đích hợp lệ: đường trong brain, đuôi `.md`/`.txt`, tối đa 1MB, không thuộc thư mục cấm;
  - guard kiểm trên bản ứng viên;
  - CAS theo `published`;
  - các cổng hiện có của `_gate`: mục tiêu active, không tạm dừng, guard, trợ lý, baseline.
- **Một sản phẩm mỗi mục tiêu.** Đích là `_deliverable_rel`, tức đường `artifact_contract` **đầu tiên** của revision. Đường thứ hai trong tiêu chí (nếu có) chỉ được evaluator của host đọc để chấm, không vào prompt, không được ghi.
- **Lượt việc nền** vẫn chỉ sinh chữ.
- **Kho:** bảng cũ không đổi cột. A4 chỉ thêm bảng mới.

**Ngoài phạm vi A4:**

- **Đội hai vai, việc con, quyền con thực sự được cấp:** thuộc A5. A4 có cơ chế cha/con vì chính quyền revision là con của phạm vi gốc (mục 5), nhưng không có đường giao việc cho trợ lý thứ hai.
- **Sandbox cho engine có công cụ native:** A4 không hứa chặn Bash/Write native (mục 6.3).
- **Mở việc nền cho Codex, Grok, Antigravity.**
- **Mô hình công ty, vai trò, trust rule, policy engine của Paperclip.**
- **Nhiều sản phẩm mỗi mục tiêu.**
- **Cấp quyền từ lời chat.** A4 không có bộ nhận chỉ thị và không có nguồn quyền `owner_message` (mục 5.2.1, D1).
- **Hạn dùng quyền (`expires_at`).** Không có trong A4 (D10).
- **Chạy tiếp mục tiêu có quyền A4 bằng mã 0.91.0 sau khi hạ phiên bản.** Không hỗ trợ (mục 7.4).

## 2. Hiện trạng: dùng lại và khoảng trống (mã tại `9716cecf`)

| Đã có | Chỗ trong mã | Khoảng trống A4 lấp |
|---|---|---|
| Danh tính lượt do host gắn: `kenh`, `session_id`, `message_id`, `agent{key, slug, config_version}`. Truyền qua `X-Javis-Turn` (Claude, Codex) hay trong tiến trình (engine API). Khoá lượt chỉ sống trong tiến trình và bị huỷ khi lượt kết thúc (`turn_context.reset`) | `turn_context.make/current/issue_key/resolve_key`, `main.run_turn`, `mcp_hub` | Lượt không mang mục tiêu, revision, quyền, `generation`, thời điểm bắt đầu. Grok và Antigravity không truyền khoá lượt |
| Cổng trợ lý hai lớp, ghim version | `resonance.agent_gate`, `resonance_store._agent_block`, `begin_action`, `finish_handoff` | Không có phạm vi theo đường hay thao tác |
| `CapabilityGrant` (replan workflow) | `agent_runtime.py` | Chỉ trong bộ nhớ, không lưu, không thu hồi. A4 không mở rộng lớp này |
| Hạn mức SQLite, hoàn lượt, `call_holds`, đối soát | `resonance_store.begin_action/finish_action/reconcile_holds` | Đủ. Quyền không thêm bộ đếm |
| Việc nền chỉ chữ: host ghi `output_root/<action_id>.md`, băm bằng đọc lại | `resonance.run_once`, `_work_post_core` | `_work_post_core` ghi receipt, đăng, chấm trong một mạch. Chưa có bản nộp trước bước đăng (mục 4.4) |
| Đăng: kiểm đường, guard, CAS | `resonance._publish`, `_gate` | **Nhánh file đích đã cùng hash gọi `set_published` rồi trả `same` trước `begin_action`.** Chưa có cổng quyền. Đọc rồi ghi không có điểm thứ tự với thu hồi |
| Bàn giao chat Claude: biên nhận Write theo id, so bytes | `note_turn_event`, `handoff_after_turn`, `finish_handoff` | **`finish_handoff` giả định file đã ở đích và ghi `published` ngay**; không chép bản nháp nào. Khoá sự kiện tiếp nhận là `adopt:<revision>` |
| Mở bàn giao khi lập hay sửa mục tiêu trong lượt chat | `resonance_store._open_handoff` (khoá `(goal, revision)`, `INSERT OR REPLACE`, `message_ref`) | Kho cho phép **hai mục tiêu cùng phiên, cùng đích, cùng `pending`**. Một tin lập rồi sửa cùng mục tiêu tạo hai dòng bàn giao theo revision |
| Bàn giao hết hạn sau khởi động lại | `handoff_gate` (chủ sở hữu theo tiến trình) | Chưa phân biệt "lượt hết nhận lời gọi" với "bản host đã nhận còn được hoàn tất" |
| Đối soát lượt nền dở | `resonance._reconcile` (chỉ chốt receipt), `_publish_latest` (đăng đầu ra trần) | Chưa có bản nộp, chưa có liên kết |
| Mô hình được sửa tiêu chí, đường đích khi có câu trích trong tin | `resonance.validate_proposal`, `revise_goal` | **Câu trích không phải chấp thuận mở quyền vào đường mới** |
| `resume` gỡ tạm dừng | `resonance.apply_command(..., "resume")` | Mã 0.91.0 không biết quyền: hạ phiên bản rồi bấm Tiếp tục là chạy lại |
| Helper đường dẫn: chặn đường tuyệt đối, đường resolve ra ngoài brain, symlink trỏ ra ngoài | `resonance._brain_file` | **Nhận `a/../a/x.md` và `./a/x.md`** vì chúng resolve vẫn trong brain (đã chạy thử). Chưa so khớp theo chữ hoa thường trên Windows |
| Snapshot khi nâng kho: SQLite backup API, lấy cả phần trong WAL, một lần, không ghi đè | `GoalStore._backup_before(marker_table, suffix)` | Dùng lại cho 0.92.0 (mục 7.4) |

- **Không có công cụ "nộp sản phẩm".**
- **Ý tưởng cũ chưa thành mã:** tài liệu 06/10 có `GoalGrant`, `AuthorityService`, `X-Javis-Run`, nhưng chưa có dòng mã nào.

## 3. Năm bất biến

Lấy từ bản bổ sung 10/10, mục 5. A4 hiện thực các bất biến 1 tới 4; bất biến 5 thuộc A5.

1. **Host giữ danh tính và cấp quyền.**
   - Model chỉ đề xuất.
   - Câu trích, nút "Đúng ý", revision do model sửa, hay **đường file chỉ xuất hiện trong tin** đều **không** phải chấp thuận mở quyền.
   - Chat thường không có quyền Resonance.
2. **Giao xuống chỉ thu hẹp.**
   - Quyền revision = phần giao của phạm vi gốc và cái revision cần.
   - Thiếu phạm vi, phạm vi lạ hay cấu hình hỏng thì không có quyền tác động.
3. **Chỉ lượt đang giữ đúng quyền được tác động.**
   - Quyền ghim vào lượt lúc host mở liên kết.
   - Tại điểm tác động, kiểm quyền đã ghim còn sống với đúng `generation` của nó **và** của phạm vi gốc.
   - Cấp lại hay chấp thuận giữa lượt không cho lượt cũ hưởng quyền mới.
4. **Chi phí và tác động có một nguồn ghi nhận.**
   - Cùng khoá và cùng dấu vân tay thao tác chỉ tạo một tác động.
   - Tác động đã qua điểm commit thì hoàn tất hay báo xung đột; không tự hoàn rồi chạy lại.
   - Hết quyền nhận lời gọi mới **không** xoá quyền hoàn tất bản host đã nhận, khi quyền đã ghim vẫn còn.
5. **Làm, review và chốt đạt là ba quyền khác nhau.** Đây là phần của A5.

## 4. Hợp đồng nộp sản phẩm

### 4.1 Bốn nguồn, một bảng bản nộp

| Nguồn | Engine | Nội dung đến từ | Bytes ở đâu khi thành bản nộp |
|---|---|---|---|
| `background_text` (đã có) | Claude, engine API | Model trả chữ | Host đã ghi `output_root/<action_id>.md` |
| `submit_tool` (mới) | Engine có khoá lượt tới hub: Claude, Codex, engine API | Model gọi `javis_submit_deliverable` | Host ghi `output_root/submissions/<id>.md` (vùng nháp) |
| `observed_write` (đã có, giữ làm đường phụ) | Claude trong chat | Model Write thẳng vào đích | Engine đã ghi ở đích |
| `approved_draft` (mới) | Không có engine | Chủ dự án Cho phép một bản nháp đã giữ (mục 5.3) | Chính file nháp cũ, không chép lại |

Mỗi bản nộp là một dòng `submissions` (mục 7.1), gắn với một **liên kết** (mục 4.2).

**Hai luật chung cho mọi bản nộp:**

- **Bản nộp chưa phải bản đã đăng.** Chỉ host đăng, theo mục 4.5. Riêng `observed_write` có một ngoại lệ (mục 4.4).
- **Bản chưa đăng không bao giờ được coi là bản người dùng đã xem hay đã duyệt** (mục 4.6). Bản nháp chờ chấp thuận chỉ hiện kích thước và nút xem trước trên thẻ; bấm Cho phép là duyệt phạm vi kèm đúng bản đó, không phải "Đạt yêu cầu".

### 4.2 Liên kết: ghim quyền vào từng lượt

Bảng `bindings` (mục 7.1). Mỗi dòng ghim cứng, không bao giờ sửa sang quyền khác:

- **Mục tiêu:** `goal_id`, `revision`.
- **Loại thẩm quyền** `authority`:
  - `grant`: ghim `grant_id`, `grant_generation`, `root_id`, `root_generation`;
  - `draft`: ghim `scope_request_id` đang chờ chủ dự án; không có quyền revision, không có phạm vi gốc.
- **Trợ lý:** `agent_key`, `agent_config_version`.
- **Nguồn:** `origin_kind` cộng `origin_ref`.
- **Trạng thái:** `status`.

Trường `origin_kind` nhận năm giá trị:

| `origin_kind` | `origin_ref` | Ai tạo, khi nào |
|---|---|---|
| `handoff` | `<session_id>:<message_id>` | Host, trong **cùng giao dịch** với `_open_handoff`, mỗi lần mục tiêu được lập hay sửa giữa lượt chat. Không đòi biết mục tiêu từ đầu lượt |
| `action` | `<action_id>` | Host, trong cùng giao dịch với `begin_action(work)` |
| `experiment` | `<experiment_id>` | Host, trong cùng giao dịch với `begin_experiment` (phép thử A3) |
| `followup` | `<action_id>` | Host, khi lượt làm sản phẩm A3 dùng lượt giữ (`begin_action` với `use_hold`) |
| `approval` | `<scope_request_id>` | Host, trong giao dịch `approve_scope` khi chủ dự án chọn một bản nháp (mục 5.3) |
| `republish` | mã mới mỗi lần | Host, khi file đích bị xoá mà revision hiện tại có bản ĐÃ đăng (I2): chép đúng bản đã đăng (cùng mục tiêu, revision, đích, sha) dưới liên kết mới ghim quyền revision ĐANG hiệu lực. Không bao giờ hợp thức hoá bản `candidate` hay `stale` chưa từng đăng |

**Khoá và lần mở.** `UNIQUE(goal_id, revision, origin_kind, origin_ref)`:

- Một tin lập mục tiêu (revision 1) rồi sửa nó (revision 2) có **hai** liên kết, mỗi revision một dòng.
- Mở lại đúng `(goal, revision, origin)` (phát lại lời gọi sửa không đổi gì): `INSERT ... ON CONFLICT DO NOTHING`, rồi đọc dòng có sẵn. Dòng còn `live` thì trả mã của nó; không còn `live` thì không có liên kết nào cho lượt này. **Không bao giờ `INSERT OR REPLACE`**, vì bản nộp và hành động đang tham chiếu dòng cũ.
- Mở liên kết revision mới làm, trong cùng giao dịch: bản nộp `candidate` và `awaiting_scope` của revision cũ thành `superseded`; liên kết revision cũ thành `closed`. Bản nộp đang `publishing` để bước 3 của mục 4.5 tự huỷ, vì revision không còn khớp.

**Ghim phạm vi gốc theo lượt chat** (chỉ `origin_kind=handoff`). Liên kết `grant` mới của một tin chỉ được mở khi đủ hai điều:

1. Mọi liên kết trước đó của cùng `(goal_id, origin_ref)` ghim **cùng** `root_id` và `root_generation` với phạm vi gốc đang `active`. Có một liên kết đã `dead`, hay gốc hiện hành khác gốc đã ghim, thì từ chối (`turn_authority_changed`).
2. Với liên kết đầu tiên của tin cho mục tiêu đó (lượt chưa từng chạm mục tiêu): gốc phải có `root.seq <= turn.authority_seq`. Không có ngoại lệ: A4 không có gốc nào do chính lượt chat tạo ra.

**Thứ tự quyền do kho quản lý, không dùng giờ máy.**

- Bảng một dòng `authority_clock(seq)`. Mọi giao dịch tạo gốc, thu hồi, chấp thuận, cấp lại (đều `BEGIN IMMEDIATE`) tăng `seq` thêm một trong chính giao dịch đó. Gốc mới mang `grants.seq` bằng giá trị vừa tăng.
- Lượt có trợ lý: `main.run_turn` đọc `authority_clock.seq` (một lần đọc theo khoá chính) **trước khi engine chạy**, ghi vào `turn.authority_seq`. Trường này do host đặt; model không thấy, không sửa được.
- Vì các giao dịch ghi được SQLite tuần tự hoá, lần đọc ở đầu lượt thấy kho **hoặc trước hoặc sau** một lần cấp lại. Gốc cấp lại sau lần đọc luôn có `seq` lớn hơn, nên lượt đó không nhận được, kể cả lần đầu chạm mục tiêu. Đồng hồ lùi hay hai thời điểm trùng nhau không ảnh hưởng.
- `seq` lưu trong kho, nên khởi động lại không làm nó lùi. Lượt của tiến trình cũ chết theo tiến trình.
- Không đọc được `seq` lúc dựng lượt: `authority_seq = -1`. Lượt vẫn chat bình thường, nhưng không mở được liên kết `grant` dưới gốc có sẵn (đóng khi lỗi); việc nền làm tiếp như thường.
- `created_at` của gốc chỉ để hiển thị và kiểm toán, không làm căn cứ quyền.

Hệ quả: thu hồi rồi cấp lại, hay chủ dự án Cho phép trong khi lượt cũ còn chạy, đều không cho lượt đó lấy liên kết dưới gốc mới, dù lượt đã có liên kết hay mới chạm mục tiêu lần đầu, qua lời sửa hay lời gọi đến muộn. Lời sửa mục tiêu vẫn được ghi; lượt đó chỉ không có quyền nộp, và việc nền làm tiếp dưới liên kết của nó.

**Vòng đời liên kết:**

| `status` | Nhận lời nộp mới | Hoàn tất bản host đã nhận | Vào trạng thái này khi |
|---|---|---|---|
| `live` | Có | Có | Host mở liên kết |
| `sealed` | **Không** | Có | Lượt chat kết thúc hay hết hạn (kể cả sau khởi động lại); lượt nền ghi xong đầu ra hay bị ngắt; phép thử kết thúc. Liên kết `approval` sinh ra ở `sealed` |
| `closed` | Không | Không | Mọi bản nộp của liên kết đã ở trạng thái cuối; hay revision mới thay chỗ |
| `dead` | Không | Không | Thu hồi |

**Hai phép kiểm**, đều chỉ đọc trong giao dịch:

- `binding_accepts(c, b)`: cổng của lời nộp mới.
  1. `b.status = live`.
  2. Thẩm quyền còn hiệu lực:
     - `grant`: dòng `b.grant_id` đang `active` với `generation = b.grant_generation`, **và** gốc `b.root_id` đang `active` với `generation = b.root_generation`;
     - `draft`: yêu cầu `b.scope_request_id` còn `pending`, đúng revision và trợ lý của liên kết.
  3. `_agent_block(b.agent_key, b.agent_config_version)` không báo gì.
  4. Revision hiện hành của mục tiêu bằng `b.revision`.
- `binding_may_finish(c, b)`: cổng hoàn tất một bản nộp đã nhận (đăng, tiếp nhận, đối soát).
  - Như trên, nhưng điều 1 là `b.status IN (live, sealed)`.
  - Thẩm quyền phải là `grant`. Liên kết `draft` **không bao giờ** đăng hay tiếp nhận được.

Hai phép kiểm này chỉ là kiểm quyền. Bước đăng vẫn chạy đủ cổng `_gate` hiện có (mục 4.5).

**Hệ quả:**

- **Cấp lại không cứu được lượt cũ.** Thu hồi tăng `generation` của gốc và chuyển liên kết thành `dead`. Cấp lại tạo gốc **mới** (`id` mới). Lượt cũ vẫn ghim gốc cũ.
- **Lời gọi từ lượt đã chết bị chặn hai lớp:**
  - khoá lượt của tiến trình cũ không còn (`no_turn`);
  - trong cùng tiến trình, liên kết đã `sealed` nên lời nộp bị từ chối (`turn_closed`).
- **Khởi động lại không làm mất bản đã nhận.** Bàn giao hết hạn chỉ chuyển liên kết sang `sealed`. Đối soát vẫn đăng được bản `candidate` đã nhận, dưới đúng quyền đã ghim, nếu quyền đó còn hiệu lực (mục 4.7).

### 4.3 Công cụ `javis_submit_deliverable`

**Đầu vào:**

- `path`: đường đích.
- `content`: toàn văn.
- `submission_key`: không bắt buộc.
- `handoff`: không bắt buộc. Đây là mã liên kết host đã trả trong kết quả công cụ lập hay sửa mục tiêu.

Model không truyền được mục tiêu, trợ lý hay quyền. `handoff` chỉ dùng để chọn giữa các liên kết của **chính lượt đang gọi**.

**Các bước.** Hỏng ở bước 1 tới 5 thì không có bản nộp nào được chấp nhận và không có tác động nào lên đích. File nháp hay bằng chứng mồ côi có thể còn lại ở bước 6; mục 4.7 nói cách đối soát.

1. **Danh tính lượt** (`turn_context` theo khoá lượt).
   - Không có lượt: `no_turn`.
   - Lượt không mang trợ lý (chat thường, kênh ngoài, workflow): `not_agent_turn`.
2. **Khoá đường** (`resonance_grants.path_key`).
   - Từ chối trước khi resolve nếu có đoạn `.` hay `..`, đường tuyệt đối, ký tự điều khiển. Không mở alias.
   - Rồi qua `_brain_file`: resolve thật, kiểm còn trong brain, chặn symlink trỏ ra ngoài. Thêm kiểm đuôi, kích thước, thư mục cấm.
   - Khoá so khớp là đường tương đối POSIX, qua `os.path.normcase` trên Windows. Không so tiền tố chuỗi.
3. **Tìm liên kết của lượt.**
   - Lấy mọi liên kết `origin_kind=handoff`, `origin_ref = <session_id>:<message_id>` **của đúng lượt đang gọi**, đúng `agent_key` và `config_version` của lượt, **ở mọi trạng thái**.
   - Có `handoff` thì phải là một trong số đó.
   - Lọc theo khoá đường của đích mà liên kết trỏ tới (quyền revision với `grant`, yêu cầu phạm vi với `draft`).
   - Hơn 1 dòng sau lọc: `ambiguous_handoff`, không đoán. Ví dụ: cùng tin sửa mục tiêu hai lần cùng đích thì có hai liên kết (một `closed`, một `live`); lời nộp không kèm `handoff` ra `ambiguous_handoff`. Công cụ lập và sửa mục tiêu luôn trả `handoff` **mới** của revision vừa tạo, và mô tả công cụ nộp dặn model gửi kèm mã đó. A4 không tự chọn dòng đầu hay dòng cuối.
4. **Nội dung.**
   - Đổi gạch dài thành "-", có đếm số lần đổi.
   - sha256 tính trên bytes sẽ ghi.
5. **Khoá, dấu vân tay, phát lại.** Thứ tự cố định: danh tính (bước 1) và liên kết của chính lượt (bước 3) **trước**, rồi mới tra biên nhận cũ.
   - Dấu vân tay `fp` = sha256 của `(binding_id, khoá đường, sha nội dung, source)`.
   - Khoá: `<binding_id>:<khoá đường>`, hay `<binding_id>:<submission_key>` nếu model đưa khoá.
   - Cùng khoá, cùng `fp`: trả biên nhận đã có, kèm trạng thái **hiện tại** của nó (có thể đã `stale`). Không tạo tác động mới. Đúng cả khi liên kết đã `sealed` hay `dead`.
   - Cùng khoá, khác `fp`: `submission_conflict`.
   - Khác đích mà cùng khoá tuỳ chọn cũng khác `fp`, nên ra xung đột.
   - Không có biên nhận cũ: cần đúng một liên kết qua `binding_accepts`. Không có thì trả lý do cụ thể: `turn_closed`, `grant_revoked`, `scope_decided`, `revision_changed`, `agent_changed`, `no_open_handoff`, `path_not_in_scope`.
6. **Ghi.**
   - Ghi file nháp `output_root/submissions/<submission_id>.md` (file tạm rồi `os.replace`), đọc lại để băm, lưu bằng chứng.
   - Rồi **một giao dịch** kiểm lại `binding_accepts` và quyền:
     - liên kết `grant`: quyền revision có `submit` và đúng đích; chèn `submissions` trạng thái `candidate`;
     - liên kết `draft`: đường bằng đường của yêu cầu; chèn trạng thái `awaiting_scope`.
   - Kho bằng chứng và hệ thống file không nằm trong giao dịch SQLite. Hỏng giữa chừng để lại file hay bằng chứng mồ côi, không có dòng.
7. **Trả biên nhận:** mã bản nộp, sha, kích thước, trạng thái. Không có nội dung.

### 4.4 Bảng chuyển trạng thái theo nguồn

**Trạng thái của `submissions`:**

| Trạng thái | Nghĩa | Cuối? |
|---|---|---|
| `awaiting_scope` | Bản nháp giữ dưới liên kết `draft`, chờ chủ dự án quyết phạm vi | Không |
| `candidate` | Bản nộp hợp lệ dưới liên kết `grant`, chưa đăng | Không |
| `publishing` | Đã có ý định đăng, đang chờ mốc commit | Không |
| `published` | Đã đăng, bytes ở đích đã đối chiếu khớp. `adopted_at` rỗng nghĩa là chưa tiếp nhận xong | Không, tới khi có `adopted_at` |
| `adopted_in_place` | Chỉ `observed_write` | Có |
| `promoted` | Bản nháp đã được chủ dự án chọn; dòng `approved_draft` mới mang nó đi tiếp | Có |
| `conflict` | Đích có bytes không khớp baseline | Có |
| `stale` | Quyền đã ghim hết hiệu lực trước mốc commit | Có |
| `superseded` | Có bản mới hơn cùng liên kết, hay revision mới thay chỗ | Có |
| `rejected` | Bị từ chối, gồm chủ dự án bấm Không | Có |

**`submit_tool`, liên kết `grant`:**

1. `candidate`: mục 4.3.
2. Cuối lượt chat, `handoff_after_turn` chuyển liên kết sang `sealed`, chọn bản `candidate` mới nhất của liên kết này (bản cũ hơn thành `superseded`) và gọi **đăng của host** (mục 4.5), đọc bytes từ file nháp.
3. Đăng xong: `published`, rồi `adopt_submission` (bản tách mới của `finish_handoff`):
   - nối bằng chứng `chat_output` đã lưu ở bước nộp (`INSERT OR IGNORE`);
   - sự kiện `artifact_adopted` với khoá `adopt:<submission_id>` (thay `adopt:<revision>` cũ, vì một revision có thể có nhiều bản qua nhiều lần);
   - đóng bàn giao; nhả lịch nếu cổng hiện có cho phép;
   - ghi `adopted_at`. Tất cả trong một giao dịch. **Không ghi `published` lần nữa**, vì đăng đã ghi.
4. Đăng gặp xung đột: `conflict`, báo thật. Bàn giao không tiếp nhận gì, giữ bản nháp.

**`submit_tool`, liên kết `draft`:** bản nộp ở `awaiting_scope`. Cuối lượt, liên kết thành `sealed`, không đăng, không giữ lượt nền. Đi tiếp theo mục 5.3 (Cho phép hay Không).

**`approved_draft`:** dòng mới do `approve_scope` tạo, liên kết `approval` (`sealed`), trạng thái `candidate`, `derived_from` trỏ về bản nháp cũ (đã `promoted`). Đăng và tiếp nhận như bước 2 tới 4 của `submit_tool`. Sự kiện tiếp nhận ghi nguồn `owner_approval`.

**`background_text`:** sắp lại thứ tự `_work_post_core`:

1. Receipt, rồi bằng chứng. Liên kết `action` chuyển `sealed`.
2. **Chèn bản nộp `candidate`** với liên kết `action` của lượt, qua `binding_may_finish`. Không qua thì `stale`.
3. Chấm trên bản ứng viên, như hôm nay.
4. Đăng **từ bản nộp** (mục 4.5).
5. `_publish_latest` (đăng lại khi lần trước bị chặn) chỉ lấy bản `candidate` của revision hiện hành có `binding_may_finish`. Không lấy đầu ra hành động trần như trước.

**`observed_write`:**

- Engine đã ghi bytes ở đích, nên đây là **ngoại lệ**: host tiếp nhận tại chỗ, không đăng lại.
- Điều kiện tiếp nhận:
  - biên nhận Write hợp lệ, theo luật cũ;
  - bytes ở đích khớp sha của biên nhận;
  - `binding_may_finish` của liên kết `handoff`, thẩm quyền `grant`;
  - quyền có `publish` cho đúng đích;
  - cổng `_gate` hiện có.
- Đạt thì ghi `adopted_in_place` và mốc `published`, kèm nguồn `observed_write`. Biên bản ghi rõ đây là file engine đã ghi, không phải file host vừa đăng.
- Liên kết `draft` không bao giờ tiếp nhận Write tại chỗ. File trợ lý tự Write khi chưa có phạm vi thành bytes lạ ở đích, xử lý như A2.

**Cùng lượt có Write A ở đích và nộp B (D3):**

1. Nếu A có biên nhận hợp lệ và tiếp nhận được, host tiếp nhận A tại chỗ trước, A thành baseline. Sau đó host đăng B đè lên A qua CAS và guard, vì baseline lúc này đã là A.
2. Nếu A không có biên nhận hợp lệ, đích đang mang bytes lạ không có baseline. Host báo `conflict` cho B.
3. **Không bao giờ ghi baseline của B lên file A** để ép đăng.

### 4.5 Đăng của host: thứ tự với thu hồi

Mọi đường thay mốc sản phẩm đi qua đúng một hàm `host_publish(submission)`:
- đăng thường;
- nhánh cùng nội dung (`same`);
- đăng lại;
- đối soát;
- lượt làm sản phẩm A3;
- bản nháp được chủ dự án chọn.

Bốn bước, không giữ khoá trong lúc gọi model hay ghi file:

1. **Ý định.** Giao dịch kiểm:
   - `binding_may_finish` của bản nộp;
   - quyền có `publish` và đích đúng;
   - **đủ cổng `_gate` hiện có:** mục tiêu active, không tạm dừng, guard trên bytes bản nộp, trợ lý;
   - đọc baseline (`published`) và hash hiện tại của đích.

   Đạt thì ghi `actions(kind=publish)` mang `binding_id`, `submission_id` và chuyển bản nộp sang `publishing`.
   - Đích đã cùng hash với bản nộp (nhánh `same`): tới bước 4 luôn, **trong chính giao dịch này**, sau khi đã kiểm quyền. Bỏ con đường đi vòng hiện có.
2. **Ghi tạm.** Ghi file tạm cạnh đích, ngoài giao dịch.
3. **Mốc commit.** Giao dịch `BEGIN IMMEDIATE`:
   - kiểm lại `binding_may_finish` và các cổng `_gate`;
   - đọc lại hash đích, so với baseline đã đọc ở bước 1.

   Đạt thì ghi `commit_at` vào hành động đăng. Thao tác thu hồi cũng dùng `BEGIN IMMEDIATE` trên cùng kho, nên hai việc được **tuần tự hoá**:
   - **Thu hồi commit trước:** bước 3 thấy liên kết chết, xoá file tạm, hành động thành `aborted`, bản nộp về `stale`.
   - **Bước 3 commit trước:** tác động đã được phép. Thu hồi sau đó chặn các tác động tiếp theo, không huỷ tác động này.
4. **Thay file và ghi mốc.**
   - `os.replace`, rồi đọc lại hash đích.
   - Khớp: giao dịch `set_published`, bản nộp `published`.
   - Không khớp: `conflict`.

**Luật tác động đã commit.** Từ lúc có `commit_at`, việc hoàn tất bước 4 (kể cả trong đối soát) **không** kiểm lại liên kết, quyền hay tạm dừng; chỉ kiểm baseline và hash. Đây là luật riêng của tác động đã commit, không áp cho bản `candidate` chưa có ý định.

**Thông báo khi thu hồi chen giữa:**

- Có `commit_at`, chưa có bằng chứng ở đích: "Lần đăng đã được chốt trước khi thu hồi; Javis đang hoàn tất." Chưa nói file đã đăng.
- Bước 4 khớp hash: "Đã hoàn tất lần đăng được chốt trước khi thu hồi" kèm sha. Không nói "đã đăng trước khi thu hồi", vì file có thể được thay sau lúc thu hồi.
- Bước 4 không khớp: báo xung đột như mọi lần đăng khác.

Thẻ mục tiêu và hướng dẫn ghi rõ luật này.

**Giới hạn (nói đúng phần phát hiện được):** không có tính nguyên tử giữa SQLite và hệ thống file.

- Người dùng sửa file **trước** bước 3: bước 3 thấy hash khác baseline, huỷ đăng, giữ bản nháp.
- Người dùng sửa file **sau** `os.replace` nhưng trước khi đọc lại: bước 4 thấy hash khác, ghi `conflict`.
- Người dùng sửa file **giữa bước 3 và `os.replace`**: `os.replace` ghi đè bản sửa đó, và hash đọc lại vẫn đúng bản nộp, nên **không phát hiện được**. Bản sửa ấy mất. Đây là khe TOCTOU đã công bố, giữ ngắn nhất có thể bằng cách để bước 3 và `os.replace` liền nhau trong cùng luồng.

### 4.6 Ai đọc gì ở từng trạng thái

| Bên đọc | Đọc |
|---|---|
| Evaluator `artifact_contract`, `_artifact_file`, `artifact_ref` | Bytes đã đăng ở đích (như hôm nay). Chấm ứng viên trước khi đăng dùng bytes bản nộp, giống luật guard trên ứng viên hiện có |
| "Bản hiện có" trong prompt việc nền | **Chỉ bytes đã đăng** ở đích thuộc `read_paths`. Không bao giờ dùng bản nộp chưa đăng hay bản nháp chờ chấp thuận |
| Xác nhận "Đạt yêu cầu" của người dùng | Gắn sha đã đăng; không gắn bản nháp |
| Thẻ mục tiêu | Bản đã đăng; số bản chờ đăng hay xung đột; bản nháp chờ chấp thuận (kích thước, sha rút gọn, nút xem trước) |
| `_publish_latest` | Bản `candidate` có `binding_may_finish`, không lấy đầu ra trần |

### 4.7 Điểm hỏng và đối soát (không gọi model)

Đối soát chạy ở lần thức sau, cùng chỗ `_reconcile` hiện có. Mọi bước chỉ dùng bytes, hash và dòng host đã nhận, dưới **quyền đã ghim** của liên kết; không lấy gốc mới, không ghim lại. Chạy hai lần không nhân đôi bằng chứng, sự kiện hay lần nhả lịch.

| Điểm hỏng | Trạng thái để lại | Đối soát |
|---|---|---|
| Đã ghi file nháp, chưa chèn dòng | File mồ côi trong `submissions/` | Bỏ qua. Không tự nhận file không có dòng. Dọn sau 7 ngày |
| Lượt chat: đã chèn `candidate`, tiến trình chết trước `handoff_after_turn` | `candidate`, liên kết `live`, bàn giao `pending` | Khởi động lại: bàn giao hết hạn, liên kết `sealed`. `binding_may_finish` qua thì đăng (mục 4.5) rồi tiếp nhận. Không qua thì `stale` (thu hồi), `superseded` (revision đổi), `stale` lý do trợ lý (trợ lý đổi) |
| Lượt chat: đã chèn `awaiting_scope`, tiến trình chết | `awaiting_scope`, liên kết `live` | Liên kết `sealed`. Bản nháp vẫn chờ chủ dự án; không đăng |
| Lượt nền: đã ghi đầu ra, chết trước khi chèn bản nộp | Hành động bị ngắt, có file đầu ra | `_reconcile` chốt receipt như hôm nay, liên kết `sealed`, rồi chèn bản nộp từ đầu ra **của host** nếu `binding_may_finish`, không thì `stale`. Đăng đi qua `_publish_latest` và mục 4.5 |
| Lượt nền: đã chèn `candidate`, chết trước khi đăng | `candidate`, liên kết `sealed` | `_publish_latest` đăng nếu `binding_may_finish` |
| Có ý định, chưa qua mốc commit | `publishing`, hành động chưa có `commit_at` | Xoá file tạm, hành động `aborted`. Bản nộp về `candidate` nếu `binding_may_finish`, không thì `stale` |
| Qua mốc commit, chưa `os.replace` | Hành động có `commit_at` | Luật tác động đã commit: đích vẫn bằng baseline thì thay file và ghi mốc. Đích đã khác: `conflict` |
| Đã thay file, chưa ghi mốc | Hành động có `commit_at` | Đích bằng sha bản nộp: ghi mốc, `published`. Khác: `conflict` |
| **Đã đăng và ghi mốc, chưa tiếp nhận** | `published`, `adopted_at` rỗng | Gọi lại `adopt_submission`: nối bằng chứng `INSERT OR IGNORE`, sự kiện theo khoá `adopt:<submission_id>` (bảng sự kiện đã có `UNIQUE(goal_id, idempotency_key)`), đóng bàn giao nếu còn mở, ghi `adopted_at`. Nhả lịch chỉ khi `adopted_at` đang rỗng và cổng hiện có cho phép, trong cùng giao dịch, nên đúng một lần. Bằng chứng và sự kiện vẫn ghi khi đã thu hồi sau commit, vì tác động là thật; khi đó không nhả lịch |
| Bản nháp được chọn, chết trước khi đăng | `approved_draft` ở `candidate`, liên kết `approval` `sealed` | Như dòng lượt nền đã chèn `candidate` |
| Lượt chat chết, Claude Write không còn biên nhận | Bàn giao hết hạn | Như hôm nay: đích lạ không có baseline thành drift hay `conflict` (A2). Không nhận làm sản phẩm |
| Đã commit, lỗi đọc hay ghi TẠM THỜI khi thay file hay khi đối soát (file đang mở) | Hành động có `commit_at`, `running` | Không phải bằng chứng đích đã đổi: giữ `running`, nới hạn có giãn cách (60 giây nhân đôi, tối đa 1 giờ), hẹn lịch `settle`. Chỉ chốt `conflict` khi đọc được đích và nó khác cả baseline lẫn bản nộp (I11) |
| Đã commit, rồi mục tiêu bị thu hồi, tạm dừng, huỷ hay kết thúc | Hành động có `commit_at` | Lịch `settle` riêng vẫn tới hạn: chỉ hoàn tất hay xác minh xung đột đúng hành động đó, không mở lượt việc, không cấp lại quyền, không đăng bản khác (I10) |
| File đích bị xoá sau khi đã đăng | Bản nộp `published` | Đăng lại bản đó qua nguồn `republish` khi quyền hiện tại còn hiệu lực, 0 lượt model (I2) |
| File NHÁP không đọc được tạm thời (khi đăng hay khi đối soát) | `candidate` hay hành động đã commit | Không phải xung đột đích: giữ nghĩa vụ, thử lại có giãn cách. File nháp mất hay sai hash: bản nộp `rejected` lý do `draft_missing`/`draft_hash_mismatch`, hành động `failed`, không đăng bytes sai (I13) |
| Đã đăng, bước tiếp nhận lỗi (khoá SQLite, chết giữa chừng), kể cả rồi thu hồi, tạm dừng, huỷ | `published`, `adopted_at` rỗng | Lịch `settle` còn tới khi tiếp nhận xong; lần thức `settle` tiếp nhận đúng một lần mọi trạng thái mục tiêu (I14) |
| Lần đăng đã chốt còn chờ thay file hay chờ tiếp nhận, trong lúc lịch làm việc tới hạn | Hành động đã commit hay bản chưa tiếp nhận | Lịch làm việc gác `publish_settling`, giữ mọi lý do, không mở lượt việc hay phép thử; xong thì gỡ gác và xét tiếp (I15) |

Liên kết `sealed` chuyển `closed` trong cùng giao dịch đưa bản nộp cuối cùng của nó về trạng thái cuối.

## 5. Quyền có phạm vi

### 5.1 Hai tầng: phạm vi gốc và quyền revision

Cả hai tầng nằm trong bảng `grants` (mục 7.1):

- **Phạm vi gốc** (`kind=root`, `parent_id` rỗng). Do chủ dự án xác lập. **Độc lập với tiêu chí model sửa.**
  - Mang đích được phép (một đường, vì A4 có một sản phẩm mỗi mục tiêu).
  - Mang tập thao tác: `read_deliverable`, `submit`, `publish`; `communicate` luôn tắt.
  - Mang bằng chứng nguồn (`source_ref_json`, mục 5.2).
  - Có `generation`, `status`.
- **Quyền revision** (`kind=revision`, cha là phạm vi gốc).
  - Bằng `narrow(gốc, cái revision cần)`.
  - Cái revision cần lấy từ `_deliverable_rel(revision)`, không phải mọi đường tiêu chí.
  - Ghi `parent_generation` = `generation` của gốc lúc cấp.

**Quyền revision hiệu lực** khi chính nó `active` **và** gốc `active` với đúng `parent_generation`. Liên kết ghim cả hai (mục 4.2).

### 5.2 Phạm vi gốc đến từ đâu

| `source` | Khi nào | Đích | Bằng chứng ghi kèm |
|---|---|---|---|
| `owner_approved` | Chủ dự án bấm "Cho phép" trên thẻ cho **một yêu cầu cụ thể** host đưa ra (mục 5.3) | Đường của yêu cầu | `scope_request_id`, người bấm |
| `legacy_frozen` | Giao dịch nâng kho lên 0.92.0, cho mục tiêu lập trước đó | `_deliverable_rel` của revision **tại lúc nâng** | Revision và sha khung lúc nâng. **Tương thích legacy**, không khẳng định chủ dự án đã duyệt |

**Mục tiêu mới lập trong lượt chat luôn chưa có phạm vi gốc**, dù lời giao có nêu đích hay không. Mục tiêu ở trạng thái **chờ chấp thuận phạm vi**:

- Host ghi `scope_requests` (kind `create` hay `expand`) mang đường, revision, trợ lý, version, tin gốc.
- Thẻ hiện "Trợ lý muốn ghi vào `Inbox/x.md`. Cho phép / Không".
- **Chưa giữ lượt việc nền nào.** Prompt không đọc đích.
- Lượt chat đang chạy nhận liên kết `draft` (mục 4.2): nộp được bản nháp vào vùng nháp, **không** đọc, **không** đăng.

**Đóng băng legacy ngay lúc nâng.** Giao dịch nâng kho (sau snapshot ở mục 7.4, trước khi bất kỳ mã A4 nào nhận lời gọi) tạo gốc `legacy_frozen` cho mỗi mục tiêu có trợ lý và có `_deliverable_rel`, đọc từ revision đang lưu. Không còn cấp lười ở "lần thức đầu", nên không có khe cho model sửa đích trước khi đóng băng. Mục tiêu chưa gán trợ lý hay không có đường sản phẩm không có gốc.

#### 5.2.1 Không cấp quyền từ lời chat (D1)

Vòng 2 tới vòng 4 thử một bộ nhận chỉ thị ghi thuần (khuôn mệnh lệnh, danh sách từ chặn). Mỗi vòng review vẫn tìm được câu thường bị nhận nhầm thành quyền ghi, như "Đây là ví dụ minh họa. Ghi vào `Inbox/x.md`." hay "Ghi vào `Inbox/x.md` là câu cần dịch.". Nguyên nhân là danh sách hữu hạn không phân biệt được **nhắc tới** một lệnh với **yêu cầu thực hiện** lệnh đó.

A4 chốt:

- **Không có nguồn `owner_message`.** Model vẫn hiểu lời giao và đề xuất đích trong khung mục tiêu; hiểu mục tiêu không phải cấp quyền ghi.
- Đích chỉ có quyền qua thẻ (`owner_approved`) hay đóng băng legacy (`legacy_frozen`).
- Không có module phân tích lời để cấp quyền. Nếu sau này cần gợi ý đường trên thẻ, phần gợi ý chỉ là đề xuất, không tạo gốc, không nâng quyền.
- "Giao một lần" giữ ở chỗ: đã cho phép một đích thì các revision sau cùng đích tự có quyền (mục 5.3), không hỏi lại.

### 5.3 Sửa mục tiêu, chấp thuận, thu hồi, cấp lại

**Revision mới cùng đích** (góp ý, nói lại, model sửa tiêu chí mà `_deliverable_rel` không đổi):
- Host cấp quyền revision mới bằng `narrow(gốc hiện hành, đích)`.
- Quyền revision cũ thành `superseded`; bản nộp và liên kết của revision cũ theo mục 4.2.

**Revision mới khác đích:**
- `narrow` cho phần giao rỗng ở thao tác ghi, dù lời sửa có nêu đích mới. Host ghi yêu cầu `expand`, mục tiêu chờ, thẻ hỏi một lần kèm đường cụ thể. Không giữ lượt nào. Lượt chat đang chạy nhận liên kết `draft` cho revision mới.

**Câu trích và nút "Đúng ý"** chỉ xác nhận cách hiểu, **không** mở phạm vi.

**Cho phép (`approve_scope`).** Một giao dịch `BEGIN IMMEDIATE`, kiểm hết rồi mới ghi:

1. Yêu cầu `request_id` tồn tại, còn `pending`.
2. `request.revision` bằng revision hiện hành; `path` gửi lên bằng `request.path` theo khoá đường.
3. Trợ lý của mục tiêu bằng `request.agent_key`, và `_agent_block` với `request.agent_config_version` không báo gì. Mục tiêu chưa lưu trữ hay xong.
4. Nếu thẻ gửi kèm `submission_id` và `sha256` (bản nháp anh đã thấy): bản đó còn `awaiting_scope`, thuộc liên kết `draft` của đúng yêu cầu, đúng sha, và là bản mới nhất của yêu cầu. Nếu thẻ không gửi bản nháp mà yêu cầu đang có bản nháp: từ chối, vì thẻ đã cũ.

Sai bất kỳ điều nào: `scope_request_stale`, **không tạo gốc nào**. Đạt thì trong cùng giao dịch:

- tạo gốc `owner_approved` (gốc cũ, nếu là `expand`, thành `superseded`) và quyền revision;
- yêu cầu thành `approved`;
- liên kết `draft` thành `closed`; các bản nháp khác của nó thành `superseded`;
- có bản nháp được chọn thì: bản đó thành `promoted`; tạo liên kết `approval` (`sealed`, ghim gốc và quyền mới); tạo bản nộp `approved_draft` ở `candidate` trỏ về cùng file nháp và sha.

Sau giao dịch, host gọi `host_publish` rồi `adopt_submission` cho bản `approved_draft`. **Không gọi model.** Không có bản nháp thì mục tiêu đi tiếp như bình thường: lần thức sau giữ lượt việc nền dưới gốc mới.

Lượt chat cũ không hưởng gì: liên kết `draft` của nó đã `closed`, nên lời nộp sau đó bị từ chối (`scope_decided`); sửa mục tiêu thêm lần nữa cũng không mở được liên kết dưới gốc mới (luật ghim gốc theo lượt, mục 4.2).

**Không (`deny_scope`).** Cùng các kiểm 1 tới 3. Yêu cầu `denied`, bản nháp `rejected`, liên kết `draft` `closed`. Mục tiêu vẫn chờ. Chủ dự án có thể nói lại để trợ lý sửa về đích cũ.

**Thẻ cũ.** Revision mới thay yêu cầu cũ bằng `superseded`; thu hồi không đụng yêu cầu đã quyết. Bấm Cho phép trên thẻ của yêu cầu đã `superseded`, `denied` hay `approved` luôn ra `scope_request_stale`. Bấm thẻ cũ không bao giờ là cấp lại.

**Thu hồi** (nút Thu hồi quyền trên thẻ). Tắt Cộng hưởng của trợ lý KHÔNG phải thu hồi (I1): gốc giữ nguyên, nhưng mọi liên kết đang dở chết ngay vì ghim version trợ lý (§4.2 điều 3) và không bao giờ hồi sinh; bật lại thì lượt MỚI làm tiếp dưới gốc cũ. Lần đăng đã qua mốc commit trước khi tắt vẫn hoàn tất theo luật tác động đã commit. Thu hồi là một giao dịch `BEGIN IMMEDIATE`:
- gốc thành `revoked` và `generation += 1`;
- bản nộp `candidate`, `awaiting_scope`, và `publishing` **chưa có** `commit_at` của mục tiêu thành `stale`. Bản có `commit_at` đi tiếp theo luật tác động đã commit;
- mục tiêu tạm dừng bằng lệnh `pause` có sẵn;
- liên kết `live` và `sealed` thành `dead`;
- yêu cầu phạm vi `pending` (nếu có) thành `withdrawn`.

**Cấp lại** là hành động owner riêng (Tiếp tục khi đang thu hồi), không phải hệ quả của thẻ nào:
- tạo phạm vi gốc **mới** (`owner_approved`, đích như gốc cũ) và quyền revision mới;
- không đảo dòng cũ, không đổi liên kết cũ;
- bản nộp `stale` không được đăng. Muốn dùng lại nội dung thì trợ lý nộp lại dưới liên kết mới.

### 5.4 `narrow` (dùng cho quyền revision trong A4, quyền con trong A5)

`narrow(parent, request) -> grant | reason`:
- Thao tác, đường ghi, đường đọc, người nhận đều là **phần giao**.
- `goal_id` và `brain_id` phải trùng.
- `communicate` chỉ có khi cha có.
- Yêu cầu thiếu trường hay có giá trị lạ: phần giao rỗng.
- So đường bằng khoá đường của mục 4.3 bước 2.

### 5.5 Mọi điểm kiểm

| Điểm | Kiểm (trong giao dịch) |
|---|---|
| Mở liên kết `handoff` | Gốc đang `active`, luật ghim gốc theo lượt (mục 4.2). Không có gốc thì liên kết `draft` theo yêu cầu đang chờ |
| `javis_submit_deliverable` | Liên kết của đúng lượt; phát lại trước, rồi `binding_accepts`; quyền `submit` + đích, hay đúng đường của yêu cầu |
| `begin_action(work)` | Quyền revision hiệu lực. Ghi liên kết `action`. Không có thì không giữ lượt (`grant_missing`, `scope_pending`, `grant_revoked`) |
| `begin_experiment` (phép thử A3) | Như trên, liên kết `experiment`. Mỗi lượt thử kiểm `binding_accepts` ở cổng lượt sẵn có (`_TrialCall`). Hỏng thì phép thử dừng `inconclusive` với lý do quyền, theo đường dừng sẵn có |
| Lượt làm sản phẩm A3 (`use_hold`) | Liên kết `followup` mới, kiểm quyền hiện hành, không kế thừa liên kết của phép thử |
| Dựng prompt việc nền | Chỉ bytes đã đăng ở `read_paths` của quyền đã ghim |
| `host_publish` bước 1 và 3 | `binding_may_finish` + `_gate` (mục 4.5), gồm nhánh `same` |
| `host_publish` bước 4 | Luật tác động đã commit: chỉ baseline và hash |
| Tiếp nhận Write tại chỗ | `binding_may_finish` (`grant`) + `publish` + đích + `_gate` |
| `approve_scope`, `deny_scope` | CAS yêu cầu, revision, đường, trợ lý, bản nháp (mục 5.3) |
| Đối soát, đăng lại | Dùng liên kết của bản nộp. Không ghim lại sang quyền mới |
| Giao diện | Chỉ hiển thị, không làm căn cứ |

## 6. Engine: khả năng thật và giới hạn

### 6.1 Bảng khả năng do host khai (`ENGINE_CAPS`)

| Provider | Khoá lượt tới hub | Nộp qua công cụ | Quan sát Write có biên nhận | Chặn ghi native | Việc nền chỉ chữ |
|---|---|---|---|---|---|
| `anthropic-cli` | Có (header) | Có | Có | Theo từng lời gọi (`can_use_tool`) khi có `allowed_tools` | Có |
| `openai-oauth` (Codex) | Có (`-c`) | **Có (mới)** | Không | Chỉ sandbox; tắt được bằng `JAVIS_CODEX_SANDBOX=off` | Không |
| `grok-cli` | **Không** | Không | Không | `--deny` theo mức | Không |
| `antigravity-cli` | **Không** | Không | Không | Chỉ sandbox | Không |
| Engine API | Có (trong tiến trình) | **Có (mới)** | Không | Không có công cụ native | Có |

Khi code, kiểm **đường truyền thật** của Claude, Codex và engine API: khoá lượt tới hub qua header, tham số `-c` và trong tiến trình. Không chỉ kiểm bằng ngữ cảnh lượt giả (review D4/D5).

### 6.2 Việc nền giữ nguyên danh sách

Codex và Grok còn công cụ native. Với Antigravity, `strip_tools` làm chuỗi lùi về Claude. Muốn mở việc nền cho các engine này cần bằng chứng chạy không công cụ; A4 không có.

### 6.3 Giới hạn phải nói thật

- **Hub không chặn được native.** Kiểm ở hub không chặn Bash hay Write native của engine có toàn quyền hệ điều hành. Trợ lý Write thẳng khi chưa có phạm vi thì file đó là bytes lạ, không thành sản phẩm.
- **Biên nhận chỉ chứng minh điều đã nộp.** A4 bảo đảm host chỉ tiếp nhận và đăng bản đi qua hợp đồng.
- **`communicate` tắt chỉ trong hợp đồng Resonance.** Không tuyên bố mọi công cụ workflow, task hay native ngoài hợp đồng đã bị chặn (D8).
- **`read_paths` chỉ là phạm vi prompt của việc nền A4.** Đây không phải hạn chế toàn bộ việc đọc của chat hay engine native (D9).

## 7. Kho

### 7.1 Bảng mới

```sql
CREATE TABLE IF NOT EXISTS grants(
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, parent_id TEXT NOT NULL DEFAULT '',
  parent_generation INTEGER NOT NULL DEFAULT 0,
  brain_id TEXT NOT NULL, goal_id TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
  agent_key TEXT NOT NULL, agent_config_version INTEGER NOT NULL,
  granted_by TEXT NOT NULL, source TEXT NOT NULL, source_ref_json TEXT NOT NULL DEFAULT '{}',
  actions_json TEXT NOT NULL, write_paths_json TEXT NOT NULL, read_paths_json TEXT NOT NULL,
  recipients_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL, generation INTEGER NOT NULL, seq INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS authority_clock(id INTEGER PRIMARY KEY CHECK(id=1), seq INTEGER NOT NULL);
INSERT OR IGNORE INTO authority_clock(id, seq) VALUES(1, 0);
CREATE UNIQUE INDEX IF NOT EXISTS grants_root_active ON grants(goal_id) WHERE kind='root' AND status='active';
CREATE UNIQUE INDEX IF NOT EXISTS grants_rev_active ON grants(goal_id, revision, parent_id)
  WHERE kind='revision' AND status='active';
CREATE INDEX IF NOT EXISTS grants_goal ON grants(goal_id, kind, status);
CREATE TABLE IF NOT EXISTS grant_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, grant_id TEXT NOT NULL, kind TEXT NOT NULL, by TEXT NOT NULL,
  generation INTEGER NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS scope_requests(
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL,
  path TEXT NOT NULL, agent_key TEXT NOT NULL, agent_config_version INTEGER NOT NULL,
  origin_ref TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
  decided_by TEXT NOT NULL DEFAULT '', decided_submission_id TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, decided_at REAL);
CREATE UNIQUE INDEX IF NOT EXISTS scope_requests_pending ON scope_requests(goal_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS bindings(
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, revision INTEGER NOT NULL, authority TEXT NOT NULL,
  grant_id TEXT NOT NULL DEFAULT '', grant_generation INTEGER NOT NULL DEFAULT 0,
  root_id TEXT NOT NULL DEFAULT '', root_generation INTEGER NOT NULL DEFAULT 0,
  scope_request_id TEXT NOT NULL DEFAULT '',
  agent_key TEXT NOT NULL, agent_config_version INTEGER NOT NULL,
  origin_kind TEXT NOT NULL, origin_ref TEXT NOT NULL, status TEXT NOT NULL,
  created_at REAL NOT NULL, closed_at REAL,
  UNIQUE(goal_id, revision, origin_kind, origin_ref));
CREATE INDEX IF NOT EXISTS bindings_origin ON bindings(origin_kind, origin_ref, status);
CREATE TABLE IF NOT EXISTS submissions(
  id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  binding_id TEXT NOT NULL, source TEXT NOT NULL, engine_json TEXT NOT NULL,
  path TEXT NOT NULL, draft_ref TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
  normalized_em_dash INTEGER NOT NULL DEFAULT 0, evidence_id TEXT NOT NULL DEFAULT '',
  idem_key TEXT NOT NULL, fingerprint TEXT NOT NULL, derived_from TEXT NOT NULL DEFAULT '',
  publish_action_id TEXT NOT NULL DEFAULT '', adopted_at REAL,
  status TEXT NOT NULL, status_reason TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(goal_id, idem_key));
CREATE INDEX IF NOT EXISTS submissions_goal ON submissions(goal_id, revision, status);
CREATE INDEX IF NOT EXISTS submissions_binding ON submissions(binding_id, status);
```

- Hành động đăng mang `binding_id`, `submission_id` và `commit_at` trong `intent_json` / `receipt_json` của bảng `actions` có sẵn, không thêm cột.
- `idem_key` của `approved_draft` là `approval:<scope_request_id>`, nên bấm Cho phép hai lần không tạo hai bản.
- `CHECK` trạng thái và `authority` để ở tầng mã (cùng kiểu các bảng A1 tới A3), có test riêng.

### 7.2 Nguồn chuẩn

- **Phạm vi:** dòng gốc `active` của mục tiêu. Không có dòng nào thì không có quyền.
- **Quyền của lượt:** chỉ liên kết đã ghim. Không suy từ quyền hiện hành lúc gọi.
- **Sản phẩm:** `published` và `evidence_links`, như A1 tới A3. `submissions` là sổ đầu vào.
- **Hạn mức:** `goals.calls_used` và sổ của A1 tới A3.

### 7.3 Đăng

Theo mục 4.5. Không hứa nguyên tử với hệ thống file.

### 7.4 Nâng cấp, hạ phiên bản, nâng lại (chọn chính sách giới hạn)

Review vòng 1 chỉ ra `apply_command(..., "resume")` của 0.91.0 gỡ tạm dừng mà không biết quyền. Vì vậy tạm dừng **không** bảo toàn được việc thu hồi khi chạy bằng mã cũ. A4 chọn chính sách giới hạn:

**Hạ về 0.91.0 chỉ hỗ trợ khôi phục snapshot hay đọc hồ sơ.** Không hỗ trợ chạy tiếp mục tiêu có quyền A4 bằng mã cũ.

- **Lúc nâng lên:**
  1. `GoalStore._backup_before("grants", ".pre-0.92.0")`: dùng lại helper có sẵn, SQLite backup API (lấy cả phần trong WAL), chỉ khi kho chưa có bảng `grants`, không ghi đè bản đã có.
  2. Tạo bảng mới.
  3. Đóng băng legacy (mục 5.2) trong cùng giao dịch tạo bảng, trước khi server nhận lời gọi.
- **Hạ đúng cách,** bằng script đi kèm `tools/resonance_restore_pre_a4.py`, chạy khi Javis đã tắt:
  1. Chép kho **hiện tại** sang `resonance.sqlite3.post-0.92.0-<thời điểm>` bằng SQLite backup API, để giữ hồ sơ sau nâng.
  2. Khôi phục snapshot vào đường kho bằng backup API, rồi dọn `-wal`/`-shm` cũ.
  3. Chạy 0.91.0.
  - Mọi thay đổi của mục tiêu sau lúc nâng bị mất khỏi kho chạy: lượt đã chạy, bản đã đăng ghi trong kho, phản hồi. Bản sao ở bước 1 vẫn đọc được.
  - File đã đăng trong brain vẫn còn, và 0.91.0 có thể thấy chúng là drift so với mốc cũ (A2).
  - Biên bản phát hành ghi rõ hậu quả này.
- **Hạ không khôi phục snapshot (không hỗ trợ):**
  - mã cũ không đọc `grants`, nên bấm Tiếp tục là chạy lại mục tiêu đã thu hồi;
  - A4 không hứa gì về trường hợp này.
- **Nâng lại sau khi mã cũ đã chạy** (bảng `grants` đã có, nên không đóng băng lại):
  - revision không có dòng quyền revision tương ứng là revision mã cũ tạo. A4 **không tự cấp** quyền cho nó: cùng đích với gốc đang `active` thì vẫn chờ chủ dự án như yêu cầu `expand` (mục 5.3);
  - mục tiêu mã cũ lập sau khi hạ không có gốc nào, nên chờ chấp thuận;
  - gốc đã `revoked` vẫn `revoked`, không có đường tự hồi sinh.

## 8. Giao diện

- **Thẻ mục tiêu**, dòng quyền: "Được: nộp và đăng `Inbox/x.md` · đọc `Inbox/x.md` · tối đa 6 lượt · không giao tiếp với trợ lý khác", kèm nút **Thu hồi quyền** (xác nhận một lần).
- **Chờ chấp thuận:** "Trợ lý muốn ghi vào `Private/y.md`. Cho phép / Không".
  - Có bản nháp: thêm "Trợ lý đã soạn sẵn một bản (3,2 KB). Cho phép sẽ đăng đúng bản này" và nút Xem trước.
  - Thẻ gửi `request_id`, `path`, `submission_id`, `sha256` đã hiển thị. Thẻ cũ nhận lời "Thẻ đã cũ, tải lại để xem yêu cầu hiện tại".
- **Bản nháp:** "1 bản nháp chờ đăng", hay "Bản nháp bị xung đột với file hiện có; xem trong lịch sử".
- **Thu hồi chen giữa lần đăng:** "Lần đăng đã được chốt trước khi thu hồi; Javis đang hoàn tất", rồi "Đã hoàn tất lần đăng được chốt trước khi thu hồi" khi có bằng chứng ở đích.
- **Trang Cộng sự:** bảng khả năng engine (mục 6.1).
- Chữ qua `vi.json` và `en.json`. Không có ô cấu hình quyền kỹ thuật.

## 9. Chốt dừng và lỗi

| Tình huống | Hành vi |
|---|---|
| Thu hồi khi lượt chat còn sống | Lời nộp sau đó hỏng `binding_accepts` (liên kết `dead`). Bản nộp trước đó thành `stale` ngay trong giao dịch thu hồi. Lượt đã chạy vẫn tính |
| Thu hồi rồi cấp lại khi cùng lượt chat còn sống | Lượt vẫn ghim gốc cũ, mọi lời nộp bị từ chối; sửa mục tiêu thêm cũng không mở được liên kết mới (`turn_authority_changed`). Trợ lý cần lượt mới |
| Chủ dự án Cho phép khi lượt chat có bản nháp còn sống | Bản nháp được chọn đăng qua liên kết `approval`. Lượt chat không nộp thêm được (`scope_decided`) |
| Thu hồi khi lượt nền đang gọi engine | Đầu ra ghi như hôm nay. Bản nộp chèn sau có liên kết `dead` nên `stale`. Không đăng. Lượt đã dùng giữ nguyên |
| Thu hồi sau ý định đăng, trước khi thay file | Thứ tự theo mốc commit (mục 4.5) |
| Cùng nội dung sau thu hồi | Nhánh `same` kiểm quyền trước, nên không tạo baseline |
| Đổi trợ lý hay phiên bản giữa lượt | Như A1: `agent_changed`, hỏng điều 3 của cả hai phép kiểm |
| Khởi động lại khi có bản đã nhận | Liên kết `sealed`; đối soát hoàn tất nếu quyền đã ghim còn hiệu lực (mục 4.7) |
| Phép thử A3 gặp quyền bị thu hồi | Dừng `inconclusive` (lý do quyền), hoàn lượt chưa ghi ý định theo luật A3 |

## 10. API và công cụ

- **`javis_submit_deliverable(path, content, submission_key?, handoff?)`:** công cụ hub.
  - Công cụ lập và sửa mục tiêu trả thêm `handoff` (mã liên kết) khi host mở liên kết, và `scope: "granted" | "pending"`.
- **`GET /goals/{id}`:** thêm các trường:
  - `scope`: gốc, đích, nguồn, trạng thái;
  - `grant`: quyền revision;
  - `scope_request`: nếu có, kèm bản nháp mới nhất (mã, sha, kích thước);
  - `submissions` gần nhất.
- **`POST /goals/{id}/commands`:**
  - `revoke_grant`: owner, CAS `expected_revision`;
  - `approve_scope`: owner, mang `request_id`, `path`, và `submission_id` + `sha256` khi thẻ có bản nháp; CAS theo mục 5.3;
  - `deny_scope`: owner, mang `request_id`;
  - `resume`: khi gốc `revoked` thì cấp lại theo mục 5.3.
- Không route nào cho model tạo, mở rộng, chấp thuận hay cấp lại quyền.

## 11. Hiệu năng

- Đọc quyền, liên kết và bản nộp theo chỉ mục; một truy vấn mỗi điểm kiểm. Không quét file hay trợ lý mỗi nhịp.
- I/O của công cụ nộp và của đăng chạy ở luồng phụ. Giao dịch `BEGIN IMMEDIATE` chỉ bọc đọc và ghi kho, không bọc lời gọi model.
- Mỗi lượt có trợ lý đọc thêm một dòng `authority_clock` theo khoá chính lúc dựng lượt. Lượt chat thường không đọc.
- Đóng băng legacy chạy một lần lúc nâng, trên số mục tiêu đang có.
- Thẻ đọc quyền trong `goal_view` đã giới hạn (0.88.5).

## 12. Ma trận nghiệm thu (đồng hồ giả, engine giả, không model thật)

Mỗi ca có đối chứng hợp lệ đi qua. Ca race chèn thay đổi ngay trước giao dịch cần bảo vệ. Ca âm kiểm cả ba thứ: không có quyền đọc đích vào prompt, không đăng, không giữ lượt nền.

### 12.1 Ca vòng 1 (giữ, sửa theo thiết kế mới)

| Ca | Kỳ vọng |
|---|---|
| G1 | `narrow` với người nhận không có quyền: phần giao rỗng |
| G2 | Quyền con xin đích rộng hơn hay mục tiêu khác: từ chối |
| G3 | Không có `communicate`: không đường nào trong hợp đồng tạo việc cho trợ lý thứ ba |
| G4 | Model tự khai mục tiêu, trợ lý, chủ dự án; MCP tên giống công cụ nộp: không nâng quyền |
| G5 | Thu hồi ngay trước giao dịch nộp: `grant_revoked`, không bản nộp |
| G6 | Cấp lại, lời nộp của liên kết cũ đến muộn: từ chối. Bản nộp cũ `stale`, không đăng |
| G7 | Thu hồi khi lượt nền đang gọi engine: `stale`, không đăng, lượt vẫn tính |
| G8 | Khởi động lại sau thu hồi: không tự hồi sinh, không hoàn hai lần |
| G9 | Lỗi trước hay sau khi engine có thể chạy: giữ luật A1 tới A3 |
| G10 | Cùng khoá, cùng dấu vân tay: trả biên nhận cũ. Cùng khoá, khác dấu vân tay: `submission_conflict` |
| G11 | Sửa file trợ lý để tự thêm quyền: quyền host không đổi; `agent_changed` |
| G12 | Prompt việc nền không chứa file ngoài `read_paths`, không chứa bản nháp chưa đăng hay chờ chấp thuận |
| G13 | Đích ngoài phạm vi, `..`, `.`, symlink ra ngoài, đuôi lạ, quá 1MB: từ chối trước khi ghi |
| G14 | Engine tự ghi native vào đích mà không nộp: không thành sản phẩm; đăng gặp `conflict` |
| G15 | Không có quyền, quyền hỏng, thao tác lạ: không giữ lượt |
| G17 | Nhiệm vụ hợp lệ trong phạm vi: nộp, đăng, tiếp nhận đúng một lần, không gọi thêm model |
| G18 | Nhiều mục tiêu chưa tới hạn: không đọc file, không đánh thức model; event loop không bị chặn khi nộp song song |
| G20 | Chat thường, kênh ngoài, workflow gọi công cụ nộp: `not_agent_turn` |
| G22 | Bảng khả năng engine. **Kiểm đường truyền thật**: header của Claude, `-c` của Codex, trong tiến trình của engine API. Grok và Antigravity bị từ chối |

### 12.2 Ca theo review vòng 1

| Ca | Tình huống | Kỳ vọng | Điểm review |
|---|---|---|---|
| G23 | Góp ý không nhắc đường, model đổi hay thêm đích (có câu trích hợp lệ) | Không cấp quyền vào đích mới; ghi `scope_requests`; không giữ lượt; không đọc đích mới vào prompt | r1 P1-1 |
| G24 | Revision mới cùng đích | Quyền revision mới tự cấp trong phạm vi, không hỏi | r1 P1-1 |
| G25 | Chủ dự án Cho phép đúng đường của yêu cầu; gửi đường khác với yêu cầu | Khớp: gốc mới `owner_approved`, làm tiếp. Lệch: `scope_request_stale`, không gốc | r1 P1-1 |
| G26 | Mục tiêu có hai đường tiêu chí | Quyền và đích chỉ là đường đầu (`_deliverable_rel`); đường hai chỉ được evaluator đọc | r1 P1-1 |
| G27 | Lập mục tiêu: lời chủ dự án nêu đích bằng lệnh trực tiếp; đích do trợ lý tự chọn | Cả hai chờ chấp thuận, chưa giữ lượt, không đọc đích vào prompt. Sau khi Cho phép thì chạy bình thường | r1 P1-1, r2 P1-1, r4 D1 |
| G28 | Mục tiêu cũ trước 0.92.0 | Gốc `legacy_frozen` đúng `_deliverable_rel` lúc nâng. Mục tiêu chờ gán không có quyền | r1 P1-1 |
| G29 | Thu hồi rồi cấp lại khi cùng lượt chat còn sống | Lượt đó không nộp được nữa | r1 P1-2 |
| G30 | Lời nộp cùng phiên nhưng khoá lượt là tin khác (đan xen hai tin) | Chỉ thấy liên kết của tin mình | r1 P1-2, P2-1 |
| G31 | Thu hồi sau bước 1 (ý định), trước bước 3 (mốc commit) | Đăng bị huỷ, file đích không đổi, bản nộp `stale` | r1 P1-2 |
| G32 | Mốc commit commit trước, thu hồi ngay sau, trước `os.replace` | Tác động hoàn tất. Lúc chưa thay file báo "đã được chốt trước khi thu hồi"; sau khi khớp hash mới báo "đã hoàn tất lần đăng được chốt trước khi thu hồi". Lần đăng sau bị chặn | r1 P1-2, r2 lưu ý 2 |
| G33 | Nhánh `same` sau thu hồi | Không tạo baseline | r1 P1-2 |
| G34 | Phép thử A3 khi quyền bị thu hồi giữa lượt thử | Dừng `inconclusive`, lý do quyền; lượt làm sản phẩm không chạy | r1 P1-2 |
| G35 | Đối soát hành động mang liên kết `generation` cũ | Không đăng, không ghim lại | r1 P1-2 |
| G36 | Nộp khi đích chưa có | Host đăng: file được tạo, mốc đúng sha | r1 P1-3 |
| G37 | Nộp khi đích có bản người dùng không có baseline | `conflict`, file người dùng nguyên vẹn, bản nháp giữ lại | r1 P1-3 |
| G38 | Cùng lượt: Write A hợp lệ, rồi nộp B | Tiếp nhận A tại chỗ, rồi đăng B qua CAS; mốc cuối là B | r1 P1-3 |
| G39 | Write A không có biên nhận, nộp B | `conflict`; không ghi baseline B lên A | r1 P1-3 |
| G40 | Hỏng ở từng điểm của mục 4.7 (chèn lỗi ngay trước và sau mỗi bước) | Đối soát đúng bảng; 0 lượt model; không nhận file mồ côi | r1 P1-3 |
| G41 | Bản nộp hợp lệ hoàn tất mà không cần model viết lại | Lượt nền và lượt chat đều đăng từ bản nộp | r1 P1-3 |
| G42 | `finish_handoff` cũ không còn được gọi với bản nháp chưa ở đích | Chỉ `adopt_submission` sau khi đăng, hay tiếp nhận tại chỗ khi có biên nhận Write | r1 P1-3 |
| G43 | Hai mục tiêu cùng phiên, cùng đích, cùng tin | `ambiguous_handoff`. Có `handoff` hợp lệ thì chọn đúng | r1 P2-1 |
| G44 | Cùng khoá tuỳ chọn, cùng bytes, khác đích | `submission_conflict` | r1 P2-1 |
| G45 | Đường alias: chữ hoa thường trên Windows; `./a/x.md`, `a/../a/x.md` | Chữ hoa thường về cùng khoá. `.` và `..` bị từ chối ở khoá đường, dù `_brain_file` nhận; symlink ra ngoài bị chặn | r1 P2-1, r2 lưu ý 4 |
| G46 | Phát lại sau khi thu hồi và cấp lại, trong cùng lượt còn sống | Trả biên nhận cũ với trạng thái `stale` (tra biên nhận trước cổng `binding_accepts`); không tác động mới. Lượt khác hay tiến trình mới: `no_turn` hay không thấy liên kết | r1 P2-1, r2 lưu ý 5 |
| G47 | Nâng lên A4 | Có `resonance.sqlite3.pre-0.92.0` đúng một bản, tạo bằng backup API, có cả dữ liệu còn trong WAL | r1 P2-2, r2 lưu ý 3 |
| G48 | A4 thu hồi, rồi chạy `resume` của mã 0.91.0 (lấy qua `git archive`) | Ghi nhận đúng là không hỗ trợ: mã cũ chạy lại. Test chứng minh giới hạn được ghi trong tài liệu là đúng sự thật, không chứng minh là được chặn | r1 P2-2 |
| G49 | Nâng lại sau khi mã cũ tạo revision mới và lập mục tiêu mới | Không tự cấp quyền cho revision hay mục tiêu đó; gốc `revoked` vẫn `revoked` | r1 P2-2 |
| G50 | Chạy script khôi phục rồi chạy 0.91.0 | Có bản `post-0.92.0-*` bằng kho trước khôi phục; kho mở được, mục tiêu ở trạng thái lúc nâng lên | r1 P2-2, r2 lưu ý 3 |

### 12.3 Ca theo review vòng 2

| Ca | Tình huống | Kỳ vọng | Điểm review |
|---|---|---|---|
| G51 | "Soạn ghi chú mới, đừng ghi vào `Private/giu-nguyen.md`", model chọn đúng đường đó làm đích | Chờ chấp thuận; ca âm ba mặt (không gốc, không đọc đích vào prompt, không đăng, không giữ lượt nền) | r2 P1-1, r4 D1 |
| G52 | "Đọc `Private/giu-nguyen.md` để tham khảo, ghi bản mới vào `Inbox/ban-moi.md`" | Đường nào cũng chờ chấp thuận, ca âm ba mặt | r2 P1-1, r4 D1 |
| G53 | Tin dán đoạn của người khác có "ghi vào `Private/giu-nguyen.md`" | Chờ chấp thuận, ca âm ba mặt | r2 P1-1, r4 D1 |
| G54 | Lệnh trực tiếp "Ghi vào `Inbox/x.md` bản tóm tắt" | Vẫn chờ chấp thuận. Cho phép đúng đường thì gốc `owner_approved`, chạy bình thường | r2 P1-1, r4 D1 |
| G55 | "ghi vào `x.md` được không?"; hai đường trong một tin | Chờ chấp thuận | r2 P1-1, r4 D1 |
| G56 | Mục tiêu legacy được model sửa sang đích mới bởi mã 0.91.0 ngay trước khi nâng, rồi sửa tiếp sau khi nâng | Gốc đóng băng theo revision lưu lúc nâng. Sửa sau nâng sang đích khác thì chờ `expand`; không đọc đích mới vào prompt | r2 P1-1 |
| G57 | Lập mục tiêu đích model chọn, nộp, kết thúc chat, chủ dự án Cho phép | 1 lượt model (của chat), 0 lượt sau duyệt. Bản nháp `promoted`, bản `approved_draft` `published`, gốc `owner_approved`, liên kết `approval`, tiếp nhận đúng một lần | r2 P2-1 |
| G58 | Như G57 nhưng chủ dự án bấm Không | Bản nháp `rejected`, không gốc, không đăng, không giữ lượt | r2 P2-1 |
| G59 | Bấm Cho phép trên thẻ cũ: sau revision mới; sau Không; sau khi có bản nháp mới hơn; sau thu hồi rồi cấp lại | `scope_request_stale`, không tạo gốc | r2 P2-1 |
| G60 | Lượt chat còn sống nộp tiếp sau khi chủ dự án đã Cho phép | `scope_decided`; lượt đó sửa mục tiêu thêm cũng không có liên kết dưới gốc mới | r2 P2-1, P2-3 |
| G61 | Liên kết `draft` cố đăng hay tiếp nhận Write tại chỗ | Bị chặn bởi `binding_may_finish` | r2 P2-1 |
| G62 | Khởi động lại sau khi chèn `candidate` của lượt chat | Liên kết `sealed`; đối soát đăng và tiếp nhận, 0 lượt model | r2 P2-2 |
| G63 | Khởi động lại sau receipt nền, trước khi chèn bản nộp; và sau khi chèn, trước khi đăng | Hoàn tất từ đầu ra của host, 0 lượt model | r2 P2-2 |
| G64 | Khởi động lại sau `published`, trước khi tiếp nhận | Tiếp nhận một lần: một bằng chứng, một sự kiện, nhả lịch một lần. Chạy đối soát hai lần không nhân đôi | r2 P2-2 |
| G65 | Như G62 nhưng thu hồi, đổi revision hay đổi trợ lý trước khi đối soát | Không đăng; `stale` hay `superseded`; không ghim sang quyền mới | r2 P2-2 |
| G66 | Lời nộp muộn từ lượt đã kết thúc (cùng tiến trình, khoá đã huỷ; và mô phỏng còn khoá nhưng liên kết `sealed`) | `no_turn`; `turn_closed` | r2 P2-2 |
| G67 | Cùng tin: lập mục tiêu (r1) rồi sửa (r2), nộp ở mỗi revision | Hai liên kết; bản r1 `superseded`; chỉ bản r2 được đăng | r2 P2-3 |
| G68 | Hai lần sửa có thay đổi trong một tin; và phát lại lời sửa không đổi gì | Ba liên kết theo revision; phát lại trả liên kết có sẵn, không dòng mới, không `REPLACE` | r2 P2-3 |
| G69 | Bản nộp r1 cố đăng sau khi mục tiêu sang r2 | Bị chặn ở điều 4 của `binding_may_finish` | r2 P2-3 |
| G70 | Thu hồi rồi cấp lại, lượt cũ sửa mục tiêu để lấy liên kết mới | `turn_authority_changed`, do cổng ghim gốc theo lượt, không do lỗi `UNIQUE` | r2 P2-3 |
| G71 | Người dùng sửa file giữa bước 3 và `os.replace` | Ca ghi nhận giới hạn: bản sửa mất, không báo xung đột. Hai ca đối chứng (sửa trước bước 3, sửa sau `os.replace`) đều phát hiện | r2 lưu ý 1 |
| G72 | `host_publish` khi mục tiêu tạm dừng, guard chặn, hay baseline lệch, dù liên kết hợp lệ | Không đăng; cổng `_gate` vẫn chạy | r2 lưu ý 6 |

### 12.4 Ca theo review vòng 3

| Ca | Tình huống | Kỳ vọng | Điểm review |
|---|---|---|---|
| G73 | "Nếu anh duyệt sau, ghi vào Inbox/x.md." | Chờ chấp thuận, ca âm ba mặt (không phụ thuộc bộ nhận nào) | r3 P1-1, r4 D1 |
| G74 | "Có nên ghi vào Inbox/x.md?" | Chờ chấp thuận, ca âm ba mặt (không phụ thuộc bộ nhận nào) | r3 P1-1, r4 D1 |
| G75 | "Anh định ghi vào Inbox/x.md." | Chờ chấp thuận, ca âm ba mặt (không phụ thuộc bộ nhận nào) | r3 P1-1, r4 D1 |
| G76 | "If I approve later, write to Inbox/x.md" | Chờ chấp thuận, ca âm ba mặt (không phụ thuộc bộ nhận nào) | r3 P1-1, r4 D1 |
| G77 | Điều kiện hay phủ định ở câu khác, không lặp đường: "Chưa chắc lắm, đừng vội. Ghi vào Inbox/x.md." | Chờ chấp thuận, ca âm ba mặt (không phụ thuộc bộ nhận nào) | r3 P1-1, r4 D1 |
| G78 | Lệnh trực tiếp có dấu chấm cuối, đường có dấu chấm trong tên (`Notes/a.b.md`) | Chờ chấp thuận; thẻ hiện đúng đường nguyên vẹn; Cho phép thì gốc mang đúng khoá đường | r3 P1-1, r4 D1 |
| G79 | Ba câu phản ví dụ vòng 4 (yêu cầu dịch, ví dụ minh họa, đuôi "là câu cần dịch") | Chờ chấp thuận; không có mã nào đọc lời chat để cấp quyền | r4 P1 |
| G80 | Lượt T chưa chạm mục tiêu G; trong lượt, thu hồi rồi cấp lại G; đồng hồ bị lùi trước lần cấp lại; T gọi sửa G lần đầu | Không có liên kết `grant` (`turn_authority_changed`), vì `root.seq > turn.authority_seq` | r3 P2-1 |
| G81 | Như G80 với đồng hồ bình thường, và với `created_at` của gốc mới bằng đúng thời điểm bắt đầu lượt | Cùng kết quả G80; giờ máy không tham gia quyết định | r3 P2-1 |
| G82 | Đối chứng: gốc có thật trước lượt (`owner_approved` hay `legacy_frozen`) | Mở được liên kết `grant` | r3 P2-1, r4 D1 |
| G83 | Lời sửa mục tiêu hay lời nộp **đến muộn** của lượt cũ sau cấp lại (cả khi lượt chưa từng có liên kết) | Lời sửa vẫn ghi; không liên kết, không nộp; G60, G70 giữ nguyên | r3 P2-1 |
| G84 | Không đọc được `authority_clock` lúc dựng lượt | `authority_seq = -1`; chat chạy, không mở liên kết `grant` dưới gốc có sẵn; việc nền không đổi | r3 P2-1 |
| G85 | Cùng tin sửa hai lần cùng đích, nộp không kèm `handoff`; rồi nộp kèm `handoff` mới | `ambiguous_handoff`; kèm mã thì đúng liên kết `live`. G67, G68 dùng mã do công cụ trả | r3 lưu ý 2 |
| G86 | Đối soát hoàn tất một lần đăng đã commit dưới quyền đã thu hồi | Chỉ hoàn tất đúng hành động đã commit; không mở hành động đăng mới, không chèn bản nộp mới, không đăng bản `candidate` khác dưới quyền cũ | r3 lưu ý 3 |

Bảng câu của `test_resonance_a4_directive.py` ghi kết quả thật của danh sách động từ, kể cả các câu bỏ sót (ví dụ "viết bản mới ở `x.md`" không có động từ trong danh sách nên đi qua thẻ). Bỏ sót được chấp nhận, nhận nhầm thì không.

### 12.5 Chuyển sang A5

| Ca | Lý do |
|---|---|
| Hai việc con tranh lượt cuối | A4 không có việc con |
| Đổi người nhận trước khi callback hoàn tất | A5 |
| Worker nộp review dưới danh tính reviewer | A5 |
| Hash, revision, tiêu chí đổi sau review | A5 |
| Approval công cụ, gửi kênh khác | A4 không có quyền gửi kênh |

## 13. Quyết định mặc định cần review

| # | Quyết định | Trạng thái |
|---|---|---|
| D1 | Phạm vi gốc độc lập với tiêu chí và **không cấp từ lời chat**. Đích mới hay đổi phạm vi đi qua thẻ; phạm vi đã cấp dùng tiếp tự động; bản nháp giữ, duyệt rồi đăng không gọi model | **Chốt** theo r4 (phương án dự phòng) |
| D2 | Đăng chỉ qua `host_publish`, giữ đủ `_gate` | Giữ, thêm r2 lưu ý 6 |
| D3 | Giữ quan sát Write; quy tắc Write A + nộp B ở mục 4.4 | Sửa theo r1 P1-3 |
| D4 | Grok và Antigravity không nhận bàn giao chat | Giữ; kiểm đường truyền thật khi code |
| D5 | Không mở việc nền thêm | Giữ |
| D6 | Thu hồi = gốc `revoked` + `stale` (trừ tác động đã commit) + tạm dừng, trong một giao dịch | Giữ; làm rõ tác động đã commit |
| D7 | Mở rộng qua yêu cầu có đường cụ thể, chủ dự án Cho phép bằng CAS | Sửa theo r2 P2-1 |
| D8 | `communicate` tắt trong hợp đồng Resonance | Giữ, phạm vi ghi đúng ở mục 6.3 |
| D9 | `read_paths` là phạm vi prompt việc nền | Giữ, phạm vi ghi đúng ở mục 6.3 |
| D10 | Không có hạn dùng quyền trong A4 | Giữ |
| D11 | Hạ phiên bản chỉ hỗ trợ khôi phục snapshot, có script giữ bản kho hiện tại | Sửa theo r2 lưu ý 3 |
| D12 | **Giữ bản nháp trước duyệt** (liên kết `draft`, không đọc, không đăng), Cho phép thì đăng đúng bản đó qua liên kết `approval`, 0 lượt model. Không chọn cách từ chối nộp trước duyệt, vì theo D1 mọi mục tiêu mới đều qua thẻ và cách đó tốn thêm một lượt model mỗi lần | Mới, r2 P2-1 |
| D13 | Liên kết có `sealed`: hết nhận lời nộp, còn hoàn tất bản đã nhận dưới quyền đã ghim | Mới, r2 P2-2 |
| D14 | Khoá liên kết theo revision; ghim gốc theo lượt bằng thứ tự `authority_clock.seq` do kho cấp, chụp lúc dựng lượt. Không dùng giờ máy | Mới ở r2 P2-3; sửa theo r3 P2-1 |
| D15 | Khoá đường từ chối `.` và `..`, không mở alias | Mới, r2 lưu ý 4 |

## 14. Kế hoạch code (sau khi thiết kế đạt review)

1. **Kho:**
   - bảng ở mục 7.1, gồm `authority_clock`; snapshot qua `_backup_before`; đóng băng legacy trong giao dịch nâng (gốc legacy nhận `seq` trong cùng giao dịch);
   - `scope_*` (gốc, yêu cầu, chấp thuận, từ chối, thu hồi, cấp lại), `grant_rev_*`;
   - `binding_open/seal/close`, `binding_accepts`, `binding_may_finish`, gắn vào `_open_handoff`, `begin_action`, `begin_experiment`;
   - `submission_*`, `adopt_submission` (khoá `adopt:<submission_id>`);
   - giao dịch `BEGIN IMMEDIATE` cho mốc commit, thu hồi, chấp thuận.
2. **Chính sách thuần** (`resonance_grants.py`): `path_key`, `narrow`, `allows`, dấu vân tay, `ENGINE_CAPS`. Không có bộ phân tích lời.
3. **Danh tính lượt:** `turn_context.make` thêm `authority_seq`; `main.run_turn` đọc `authority_clock` cho lượt có trợ lý trước khi engine chạy.
4. **Hợp đồng** (`resonance.py`):
   - `host_publish` bốn bước, thay mọi chỗ gọi `set_published` và `_publish`;
   - sắp lại `_work_post_core`;
   - `_publish_latest` theo bản nộp;
   - `handoff_after_turn` theo bản nộp, quy tắc A/B, niêm liên kết;
   - cổng trong phép thử A3;
   - đối soát theo mục 4.7.
5. **Công cụ hub** `javis_submit_deliverable` (plugin `javis-goal`). Công cụ lập và sửa mục tiêu trả `handoff` và `scope`.
6. **API** theo mục 10.
7. **Giao diện** theo mục 8.
8. **Script** `tools/resonance_restore_pre_a4.py` (repo không có thư mục `scripts/`).
9. **Test:**
   - `test_resonance_a4_grants.py`: ma trận 12.1 tới 12.3;
   - `test_resonance_a4_rollback.py`: G47 tới G50 với `33a3c1aa`;
   - `test_resonance_a4_ui.js`;
   - một test đường truyền khoá lượt thật cho Claude, Codex và engine API.
10. **Tài liệu:** hướng dẫn, biên bản, lộ trình, ghi chú phát hành về hạ phiên bản và luật tác động đã commit.

## 15. Ranh giới bằng chứng

- **17 ca Paperclip** là bằng chứng về Paperclip.
- **10 kiểm của reviewer vòng 1**, **13 kiểm vòng 2** và **16 kiểm vòng 3** chứng minh giả định về mã nền và mâu thuẫn trong văn bản thiết kế. Đó không phải test A4.
- **Mục 2:** đọc mã tại `9716cecf`. Dòng `_brain_file` nhận `a/../a/x.md` đã chạy thử trên mã đó; reviewer vòng 3 đã kiểm lại và đính chính nhận xét vòng 2. D15 là luật mới của `path_key`, không sửa helper dùng chung.
- **Phần còn lại** là đề xuất.

## 16. Thay đổi theo review

### 16.1 Sau review vòng 1 (`5edfc9b6`)

| Điểm | Sửa | Mục |
|---|---|---|
| P1-1: revision do model sửa tự cấp quyền vào đích mới | Phạm vi gốc độc lập với tiêu chí. Quyền revision = `narrow(gốc, _deliverable_rel)`. Đổi đích thì thành yêu cầu mở rộng chờ chủ dự án với đường cụ thể. Legacy đóng băng, ghi rõ là tương thích. Một sản phẩm mỗi mục tiêu | 1, 5.1 tới 5.3, 12.2 (G23 tới G28) |
| P1-2: chưa ghim quyền vào lượt; nhánh `same` đi vòng; chưa có thứ tự với thu hồi | Bảng `bindings` ghim quyền revision, gốc, `generation`, trợ lý, nguồn lượt. `host_publish` bốn bước có mốc commit `BEGIN IMMEDIATE` tuần tự với thu hồi. Mọi đường thay mốc qua đó | 4.2, 4.5, 5.5, 9, 12.2 (G29 tới G35) |
| P1-3: dùng `finish_handoff` như thể bản nháp đã ở đích; bản nộp nền chèn sau bước đăng | Bảng chuyển trạng thái theo nguồn. Đăng bytes từ bản nháp qua `host_publish`. `adopt_submission` tách khỏi ghi mốc. Sắp lại `_work_post_core`. Quy tắc Write A + nộp B. Bảng ai đọc gì. Bảng đối soát | 4.4, 4.6, 4.7, 12.2 (G36 tới G42) |
| P2-1: chọn mục tiêu theo phiên + đường; chống trùng chỉ theo sha | Chọn theo liên kết của đúng tin đang gọi; nhiều kết quả thì `ambiguous_handoff`. Dấu vân tay toàn thao tác. Khoá đường chuẩn hoá | 4.3, 12.2 (G43 tới G46) |
| P2-2: tạm dừng không bảo toàn thu hồi khi chạy mã 0.91.0 | Hạ phiên bản chỉ khôi phục snapshot. Nâng lại không tự cấp quyền cho revision mã cũ tạo. Bỏ `expires_at` | 7.4, D10, D11, 12.2 (G47 tới G50) |

### 16.2 Sau review vòng 2 (`99c88447`)

| Điểm | Sửa | Mục |
|---|---|---|
| P1-1: đường có mặt trong lời chủ dự án chưa chứng minh quyền ghi; legacy lấy revision hiện hành lúc thức | `owner_message` chỉ khi bộ nhận chỉ thị thuần tìm thấy đúng một chỉ thị ghi rõ ràng, bỏ phần trích và dán, chặn phủ định và động từ đọc; ghi bằng chứng mệnh đề. Không chắc thì chờ chấp thuận. Đóng băng legacy trong giao dịch nâng, đọc revision lưu lúc nâng | 1, 3, 5.2, 5.2.1, 5.3, 12.3 (G51 tới G56), D1 |
| P2-1: chờ chấp thuận không có root nhưng submit đòi root; chưa có đường dùng bản nháp sau duyệt; thẻ cũ | Chọn giữ bản nháp: liên kết `draft` ghim yêu cầu đang chờ, chỉ nộp vào vùng nháp (`awaiting_scope`), không đọc, không đăng. `approve_scope` CAS yêu cầu, revision, đường, trợ lý, bản nháp trong một giao dịch, tạo gốc mới, liên kết `approval` và bản `approved_draft`; 0 lượt model. Lượt chat cũ không hưởng quyền mới. Thẻ cũ không bao giờ cấp gốc | 4.1, 4.2, 4.4, 5.2, 5.3, 8, 10, 12.3 (G57 tới G61), D7, D12 |
| P2-2: đóng liên kết khi khởi động lại làm mất bản đã nhận; thiếu dòng đã đăng chưa tiếp nhận | Tách `live` (nhận lời nộp) với `sealed` (chỉ hoàn tất bản đã nhận dưới quyền đã ghim). Hai phép kiểm `binding_accepts` và `binding_may_finish`. Luật tác động đã commit riêng. Thêm dòng đã đăng chưa tiếp nhận, khoá `adopt:<submission_id>`, `adopted_at` giữ nhả lịch đúng một lần | 3, 4.2, 4.4, 4.5, 4.7, 9, 12.3 (G62 tới G66), D13 |
| P2-3: `UNIQUE(goal_id, origin_kind, origin_ref)` chặn hai revision trong một tin | Khoá `UNIQUE(goal_id, revision, origin_kind, origin_ref)`; mở lại cùng khoá trả dòng có sẵn, không `REPLACE`; revision mới làm bản cũ `superseded`. Ghim gốc theo lượt (vòng 3 dùng `turn.started_at`; vòng 4 thay bằng `authority_clock.seq`, mục 16.3) để lượt cũ không lấy gốc mới bằng cách sửa thêm | 4.2, 7.1, 12.3 (G67 tới G70), D14 |
| Lưu ý 1: đọc lại hash sau `os.replace` không phát hiện bản sửa bị ghi đè | Viết lại mục giới hạn theo ba khe thời gian; nói rõ khe không phát hiện được | 4.5, G71 |
| Lưu ý 2: "đã đăng" khi mới commit | Hai thông báo: "đã được chốt trước khi thu hồi" và "đã đăng trước khi thu hồi" khi có bằng chứng ở đích | 4.5, 8, G32 |
| Lưu ý 3: snapshot chép thô với WAL; giữ kho hiện tại trước khôi phục | Dùng `_backup_before`; script khôi phục chép kho hiện tại bằng backup API trước | 7.4, G47, G50, D11 |
| Lưu ý 4: luật `..` không thống nhất | Chạy thử: `_brain_file` thật ra nhận `a/../a/x.md`. Chốt khoá đường từ chối `.` và `..` | 2, 4.3, G13, G45, D15 |
| Lưu ý 5: thứ tự tra biên nhận và lọc liên kết sống | Danh tính và liên kết của lượt trước, tra biên nhận cũ, rồi mới cổng `binding_accepts` cho lời nộp mới | 4.3, G46 |
| Lưu ý 6: `binding_valid` không thay `_gate` | `host_publish` bước 1 và 3 chạy đủ `_gate`; ghi rõ ở mục 1, 4.2, 5.5 | 1, 4.2, 4.5, 5.5, G72 |

### 16.3 Sau review vòng 3 (`efa1fce3`)

| Điểm | Sửa | Mục |
|---|---|---|
| P1-1: bộ nhận chỉ thị cấp quyền từ câu điều kiện, câu hỏi, lời dự định; tách dấu chấm làm vỡ đường | Nhận token đường trước mọi bước tách. Cổng ngữ cảnh cả tin chạy trước khi tách câu: `?`, điều kiện, hỏi, dự định, phủ định ở bất kỳ đâu thì chờ. Không tách theo dấu phẩy. Câu phải khớp **trọn** một khuôn mệnh lệnh, phần mở đầu chỉ từ danh sách đóng. Bảng ví dụ dương và âm. Ghi phương án dự phòng bỏ cấp tự động trong D1 | 5.2.1, 12.4 (G73 tới G79), D1 |
| P2-1: so `created_at` với `started_at` cấp nhầm khi đồng hồ lùi hay trùng thời điểm, nhất là lần đầu lượt chạm mục tiêu | Thứ tự do kho cấp: `authority_clock.seq` tăng trong mọi giao dịch tạo gốc, thu hồi, chấp thuận, cấp lại; lượt có trợ lý chụp `seq` trước khi engine chạy; liên kết đầu tiên chỉ nhận gốc có `seq` không vượt ảnh chụp, trừ gốc do chính tin tạo. Đọc lỗi thì đóng. `created_at` chỉ để hiển thị | 4.2, 7.1, 11, 14, 12.4 (G80 tới G84), D14 |
| Lưu ý 1: "Đã đăng trước khi thu hồi" sai thời điểm | Đổi thành "Đã hoàn tất lần đăng được chốt trước khi thu hồi" | 4.5, 8, G32 |
| Lưu ý 2: không kèm `handoff` thì hai revision cùng tin ra `ambiguous_handoff` | Giữ hành vi đó, nói rõ; công cụ lập và sửa trả mã mới, mô tả công cụ nộp dặn gửi kèm; G67, G68 dùng mã | 4.3, G85 |
| Lưu ý 3: hoàn tất tác động đã commit khác mở tác động mới | Ca kiểm quyền cũ chỉ hoàn tất đúng hành động đã commit | G86 |
| Đính chính của reviewer về `_brain_file` | Ghi nhận ở mục 15; D15 giữ là luật mới của `path_key` | 15, D15 |

### 16.4 Sau review vòng 4 (`bd6ad1d1`): chốt D1

| Điểm | Sửa | Mục |
|---|---|---|
| P1: bộ nhận chỉ thị vẫn nhận câu nhắc tới lệnh (dịch, ví dụ, đuôi tự do) thành quyền ghi | Bỏ nguồn `owner_message` và bộ nhận khỏi A4. Mọi đích mới hay đổi phạm vi qua thẻ; phạm vi đã cấp và legacy giữ nguyên; bản nháp duyệt rồi đăng 0 lượt model | 1, 4.2, 5.2, 5.2.1, 5.3, 6.3, 11, 12, 13 (D1, D12), 14 |
| Ngoại lệ thứ tự cho gốc do chính tin tạo | Bỏ, vì không còn nguồn đó | 4.2 |
| Kỳ vọng ca cũ dựa trên `owner_message` | G27, G51 tới G55, G73 tới G79, G82 đổi sang chờ thẻ hay gốc có trước lượt | 12 |

## 17. Ghi chú triển khai

Các điểm dưới đây là chỗ mã phải chọn mà thiết kế chưa nói hết, hay chỗ hành vi cũ đổi theo thiết kế. Hai điểm đầu chạm cơ chế quyền nên **cần reviewer xác nhận** trước khi chốt mã; mã hiện chọn phương án được ghi.

| # | Điểm | Mã chọn | Vì sao |
|---|---|---|---|
| I1 | §5.3 ghi "Thu hồi (nút Thu hồi quyền, hay tắt Cộng hưởng của trợ lý)" | **Tắt Cộng hưởng KHÔNG thu hồi gốc.** Liên kết vẫn chết ngay vì ghim version trợ lý (§4.2 điều 3); bật lại thì lượt mới làm tiếp dưới gốc cũ | Giữ hành vi A1 "bật lại thì chạy tiếp". **Reviewer chấp nhận ở review mã vòng 1**; §5.3 đã sửa theo |
| I2 | §4.5 liệt kê "đăng lại" nhưng §4.2 không có nguồn cho nó | File đích bị xoá thì `_publish_latest` tạo bản nộp `republish` chép bản đã đăng, dưới liên kết **mới** `republish` ghim quyền revision ĐANG hiệu lực (không dùng lại liên kết cũ). Không có quyền hiệu lực thì không đăng lại | Giữ hành vi A2 "xoá file thì đăng lại bản hiệu lực, 0 lượt model". **Reviewer chấp nhận ở review mã vòng 1**; đã ghi vào §4.2 và §4.7 |
| I3 | Mục tiêu không có đường sản phẩm (chỉ có tiêu chí người dùng xác nhận) | `scope_state=none`: không cần phạm vi, việc nền chạy như 0.91.0, không có gì để đăng | Không có đích để cho phép; chặn chúng thì mục tiêu kẹt vĩnh viễn |
| I4 | Hệ quả của D1 với Claude | Write trong lượt LẬP mục tiêu không được tiếp nhận (bytes lạ ở đích). Chỉ bản nộp qua `javis_submit_deliverable` được giữ làm nháp. Gợi ý trong prompt và kết quả `javis_goal` dặn bộ não nộp qua công cụ, không Write thẳng | Đúng §4.4 ("liên kết draft không bao giờ tiếp nhận Write tại chỗ"). Câu hỏi mở cho A5: có nên chuyển một Write có biên nhận thành bản nháp không; mã chưa làm |
| I5 | A1 quyết định 4 (đăng lại đầu ra giữ sau khi tắt bật, ý định mới theo version hiện tại) | Thay bằng §4.2 điều 3: bản nộp `stale`, lần thức sau làm lại một lượt | "Host không bao giờ sửa liên kết đang dở sang quyền mới". Test A1 sửa kỳ vọng, có chú thích |
| I6 | Revision do mã cũ tạo, hay mục tiêu vừa gán, cần phạm vi mà chưa có yêu cầu | `_gate` gọi `ensure_scope_request`: chỉ ghi yêu cầu chờ, không cấp | Để thẻ có nút Cho phép; §7.4 |
| I7 | `origin_ref` của liên kết `handoff` | Dùng `message_ref` (`msg:<phiên>:<tin>`), cùng khoá với bảng `handoffs` | Tương đương `<session_id>:<message_id>` của §4.2 |
| I8 | Báo chờ cho phép | Không có tin outbox riêng; thẻ đẩy sau lượt chat đã hiện câu hỏi, thẻ và trang Cộng sự cũng hiện | Tránh hai tin cho cùng một việc |
| I9 | Bàn giao cuối lượt | `main` bàn giao MỌI mục tiêu tin đó lập hay sửa (trước chỉ mục tiêu đầu tiên), biên nhận Write lấy một lần | Mỗi mục tiêu có liên kết riêng phải được niêm |
| I10 | Đường tới đối soát của tác động đã commit (review mã vòng 1, P2-2) | Lịch vật lý riêng `kind=settle`, đặt trong giao dịch mốc commit (hạn khoá + 1), không bị gác bởi tạm dừng, thu hồi, huỷ, kết thúc; `due_wakeups` nhận nó mọi trạng thái; lần thức `settle` chỉ chạy `_reconcile_publish` cho hành động đã commit rồi dọn lịch khi không còn | Thu hồi tạm dừng mục tiêu và `_recompute_wake` gác mọi lịch làm việc, nên trước đó tác động đã chốt mất đường hoàn tất |
| I11 | Lỗi I/O tạm thời sau mốc commit (review mã vòng 1, P2-1) | `publish_retry`: giữ `running`, nới hạn giãn cách, hẹn `settle`; `conflict` chỉ khi đọc được đích và nó khác cả baseline lẫn bản nộp | Không đọc hay không ghi được không phải bằng chứng xung đột |
| I12 | Phản hồi "Chưa đúng ý" trước mốc commit (review mã vòng 1, P1-1) | `_publish_held` đọc phản hồi cách hiểu mới nhất của đúng revision TRONG giao dịch ý định (kể cả nhánh `same`) và giao dịch mốc commit; bị chặn thì bản nộp về `candidate`, đổi lại "Đúng ý" thì lần sau đăng | Can thiệp của người dùng ghi trước mốc commit phải thắng, như thu hồi |
| I13 | Lỗi đọc FILE NHÁP (review mã vòng 2, P2-1) | `_sub_read` tách `draft_unreadable` (I/O tạm thời: giữ nghĩa vụ, `publish_retry` hay giữ `candidate`) khỏi `draft_missing` và `draft_hash_mismatch` (`reject_submission`: lý do riêng, không phải `target_changed`, không đăng bytes sai) | Không đọc được bản nháp không phải bằng chứng file đích đổi |
| I14 | Nghĩa vụ tiếp nhận sau đăng (review mã vòng 2, P2-2) | Lịch `settle` chỉ bỏ khi không còn hành động đã commit đang chạy VÀ không còn bản `submit_tool`/`approved_draft` đã đăng chưa tiếp nhận; nhánh `same` đặt lịch ngay; lỗi ở bước tiếp nhận không văng ra ngoài; lần thức `settle` tiếp nhận các bản này | Đăng và tiếp nhận là hai giao dịch; khe giữa chúng phải có đường phục hồi kể cả khi lịch làm việc đã gác |
| I15 | Lịch làm việc khi còn nghĩa vụ hoàn tất (review mã vòng 2, P2-3) | `_wake_work` gác `waiting/publish_settling` (thuộc `_parked`) trước khi xét đăng lại hay mở lượt; `_settle_done` gỡ gác và tính lại lịch khi nghĩa vụ về 0 | Bản hợp lệ đã có, chỉ chưa vào đích; gọi model lúc này là tiêu hạn mức vô ích |
