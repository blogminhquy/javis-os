# Resonance A4: nộp sản phẩm đa engine qua một hợp đồng host, kèm quyền có phạm vi

**Trạng thái:** thiết kế **vòng 2**, chờ review. **Chưa có mã A4.**

- **Nhánh:** `claude/resonance-a4-handoff-grants`, PR nháp #604, số 0.90.0.
- **Vòng 1** (`5edfc9b6`) chưa đạt: 3 P1, 2 P2 (`exports/reviews/PR-604-A4-design-r1-review.md`, ngoài git).
  - Sửa ở các mục 4, 5, 7.4, 12; xem tóm tắt ở mục 16.
  - Kiến trúc và phạm vi giữ nguyên.

**Nền và đầu vào:**

- **Nền:** `main` tại `33a3c1aa` (0.89.0). A1 0.87.0, A2 0.88.0, A3 0.89.0, bản hiệu năng 0.88.5 (#602) đã vào `main`.
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
- Đích anh nêu trong lời giao được dùng ngay. Đích trợ lý tự chọn hay muốn đổi thì Javis hỏi anh **một lần**, kèm đúng đường file.
- Trong phạm vi đã cho, trợ lý tự làm, không hỏi lại từng bước.
- Thẻ mục tiêu hiện: được làm gì, trên file nào, tối đa bao nhiêu lượt, có được giao tiếp không, nút Thu hồi.

**Giữ nguyên:**

- **Luật hạn mức A1 tới A3:** giữ chỗ trong giao dịch, trần chung, "chưa gọi thì trả, đã gọi thì giữ", `call_holds`.
- **Luật đăng:**
  - đích hợp lệ: đường trong brain, đuôi `.md`/`.txt`, tối đa 1MB, không thuộc thư mục cấm;
  - guard kiểm trên bản ứng viên;
  - CAS theo `published`.
- **Một sản phẩm mỗi mục tiêu.** Đích là `_deliverable_rel`, tức đường `artifact_contract` **đầu tiên** của revision. Đường thứ hai trong tiêu chí (nếu có) chỉ được evaluator của host đọc để chấm, không vào prompt, không được ghi.
- **Lượt việc nền** vẫn chỉ sinh chữ.
- **Kho:** bảng cũ không đổi cột. A4 chỉ thêm bảng mới.

**Ngoài phạm vi A4:**

- **Đội hai vai, việc con, quyền con thực sự được cấp:** thuộc A5. A4 có cơ chế cha/con vì chính quyền revision là con của phạm vi gốc (mục 5), nhưng không có đường giao việc cho trợ lý thứ hai.
- **Sandbox cho engine có công cụ native:** A4 không hứa chặn Bash/Write native (mục 6.3).
- **Mở việc nền cho Codex, Grok, Antigravity.**
- **Mô hình công ty, vai trò, trust rule, policy engine của Paperclip.**
- **Nhiều sản phẩm mỗi mục tiêu.**
- **Hạn dùng quyền (`expires_at`).** Không có trong A4 (D10).
- **Chạy tiếp mục tiêu có quyền A4 bằng mã 0.89.0 sau khi hạ phiên bản.** Không hỗ trợ (mục 7.4).

## 2. Hiện trạng: dùng lại và khoảng trống (mã tại `9716cecf`)

| Đã có | Chỗ trong mã | Khoảng trống A4 lấp |
|---|---|---|
| Danh tính lượt do host gắn: `kenh`, `session_id`, `message_id`, `agent{key, slug, config_version}`. Truyền qua `X-Javis-Turn` (Claude, Codex) hay trong tiến trình (engine API) | `turn_context.make/current/issue_key`, `main.run_turn`, `mcp_hub` | Lượt không mang mục tiêu, revision, quyền, `generation`. Grok và Antigravity không truyền khoá lượt |
| Cổng trợ lý hai lớp, ghim version | `resonance.agent_gate`, `resonance_store._agent_block`, `begin_action`, `finish_handoff` | Không có phạm vi theo đường hay thao tác |
| `CapabilityGrant` (replan workflow) | `agent_runtime.py` | Chỉ trong bộ nhớ, không lưu, không thu hồi. A4 không mở rộng lớp này |
| Hạn mức SQLite, hoàn lượt, `call_holds`, đối soát | `resonance_store.begin_action/finish_action/reconcile_holds` | Đủ. Quyền không thêm bộ đếm |
| Việc nền chỉ chữ: host ghi `output_root/<action_id>.md`, băm bằng đọc lại | `resonance.run_once`, `_work_post_core` | `_work_post_core` ghi receipt, đăng, chấm trong một mạch. Chưa có bản nộp trước bước đăng (mục 4.4) |
| Đăng: kiểm đường, guard, CAS | `resonance._publish` | **Nhánh file đích đã cùng hash gọi `set_published` rồi trả `same` trước `begin_action`.** Chưa có cổng quyền. Đọc rồi ghi không có điểm thứ tự với thu hồi |
| Bàn giao chat Claude: biên nhận Write theo id, so bytes | `note_turn_event`, `handoff_after_turn`, `finish_handoff` | **`finish_handoff` giả định file đã ở đích và ghi `published` ngay**; không chép bản nháp nào |
| Mở bàn giao khi lập hay sửa mục tiêu trong lượt chat | `resonance_store._open_handoff` (khoá `(goal, revision)`, `message_ref`) | Kho cho phép **hai mục tiêu cùng phiên, cùng đích, cùng `pending`** |
| Mô hình được sửa tiêu chí, đường đích khi có câu trích trong tin | `resonance.validate_proposal`, `revise_goal` | **Câu trích không phải chấp thuận mở quyền vào đường mới** |
| `resume` gỡ tạm dừng | `resonance.apply_command(..., "resume")` | Mã 0.89.0 không biết quyền: hạ phiên bản rồi bấm Tiếp tục là chạy lại |
| Helper đường dẫn: chặn đường tuyệt đối, `..`, symlink trỏ ra ngoài (resolve thật) | `resonance._brain_file` | Chưa so khớp theo chữ hoa thường trên Windows |

- **Không có công cụ "nộp sản phẩm".**
- **Ý tưởng cũ chưa thành mã:** tài liệu 06/10 có `GoalGrant`, `AuthorityService`, `X-Javis-Run`, nhưng chưa có dòng mã nào.

## 3. Năm bất biến

Lấy từ bản bổ sung 10/10, mục 5. A4 hiện thực các bất biến 1 tới 4; bất biến 5 thuộc A5.

1. **Host giữ danh tính và cấp quyền.**
   - Model chỉ đề xuất.
   - Câu trích, nút "Đúng ý", hay revision do model sửa **không** phải chấp thuận mở quyền.
   - Chat thường không có quyền Resonance.
2. **Giao xuống chỉ thu hẹp.**
   - Quyền revision = phần giao của phạm vi gốc và cái revision cần.
   - Thiếu phạm vi, phạm vi lạ hay cấu hình hỏng thì không có quyền tác động.
3. **Chỉ lượt đang giữ đúng quyền được tác động.**
   - Quyền ghim vào lượt lúc host mở liên kết.
   - Tại điểm tác động, kiểm quyền đã ghim còn sống với đúng `generation` của nó **và** của phạm vi gốc.
   - Cấp lại không cho lượt cũ hưởng quyền mới.
4. **Chi phí và tác động có một nguồn ghi nhận.**
   - Cùng khoá và cùng dấu vân tay thao tác chỉ tạo một tác động.
   - Tác động đã qua điểm commit thì hoàn tất hay báo xung đột; không tự hoàn rồi chạy lại.
5. **Làm, review và chốt đạt là ba quyền khác nhau.** Đây là phần của A5.

## 4. Hợp đồng nộp sản phẩm

### 4.1 Ba nguồn, một bảng bản nộp

| Nguồn | Engine | Nội dung đến từ | Bytes ở đâu khi thành bản nộp |
|---|---|---|---|
| `background_text` (đã có) | Claude, engine API | Model trả chữ | Host đã ghi `output_root/<action_id>.md` |
| `submit_tool` (mới) | Engine có khoá lượt tới hub: Claude, Codex, engine API | Model gọi `javis_submit_deliverable` | Host ghi `output_root/submissions/<id>.md` (vùng nháp) |
| `observed_write` (đã có, giữ làm đường phụ) | Claude trong chat | Model Write thẳng vào đích | Engine đã ghi ở đích |

Mỗi bản nộp là một dòng `submissions` (mục 7.1), gắn với một **liên kết lượt** (mục 4.2).

**Hai luật chung cho mọi bản nộp:**

- **Bản nộp chưa phải bản đã đăng.** Chỉ host đăng, theo mục 4.5. Riêng `observed_write` có một ngoại lệ (mục 4.4).
- **Bản chưa đăng không bao giờ được coi là bản người dùng đã xem hay đã duyệt** (mục 4.6).

### 4.2 Liên kết lượt: ghim quyền vào từng lượt

Bảng `bindings` (mục 7.1). Mỗi dòng ghim cứng các trường:

- **Mục tiêu:** `goal_id`, `revision`.
- **Quyền revision:** `grant_id`, `grant_generation`.
- **Phạm vi gốc:** `root_id`, `root_generation`.
- **Trợ lý:** `agent_key`, `agent_config_version`.
- **Nguồn:** `origin_kind` cộng `origin_ref`.
- **Trạng thái:** `status`.

Trường `origin_kind` nhận bốn giá trị:

| `origin_kind` | `origin_ref` | Ai tạo, khi nào |
|---|---|---|
| `handoff` | `<session_id>:<message_id>` | Host, trong **cùng giao dịch** với `_open_handoff`, lúc mục tiêu được lập hay sửa giữa lượt chat. Không đòi biết mục tiêu từ đầu lượt |
| `action` | `<action_id>` | Host, trong cùng giao dịch với `begin_action(work)` |
| `experiment` | `<experiment_id>` | Host, trong cùng giao dịch với `begin_experiment` (phép thử A3) |
| `followup` | `<action_id>` | Host, khi lượt làm sản phẩm A3 dùng lượt giữ (`begin_action` với `use_hold`) |

**Hiệu lực của liên kết.** `binding_valid(c, b)` chỉ đọc trong giao dịch và chỉ đúng khi đủ năm điều kiện:

1. `b.status = live`.
2. Dòng quyền `b.grant_id` đang `active` và có `generation = b.grant_generation`.
3. Phạm vi gốc `b.root_id` đang `active` và có `generation = b.root_generation`.
4. `_agent_block(b.agent_key, b.agent_config_version)` không báo gì.
5. Revision của mục tiêu bằng `b.revision`, với các tác động cần đúng revision: đăng, tiếp nhận.

**Hệ quả:**

- **Cấp lại không cứu được lượt cũ.**
  - Thu hồi tăng `generation` của phạm vi gốc.
  - Cấp lại tạo phạm vi gốc **mới** (`id` mới).
  - Lượt cũ vẫn ghim `root_id` và `root_generation` cũ, nên hỏng ở điều kiện 3.
  - Host không bao giờ sửa liên kết đang dở sang quyền mới.
- **Khởi động lại không đổi gì.** Liên kết lưu trong SQLite. Sau khi khởi động lại, liên kết `live` của bàn giao đã hết hạn (`handoff_gate`) chuyển `closed`; liên kết của lượt nền được `_reconcile` đóng cùng hành động.

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
2. **Đường chuẩn hoá.**
   - Qua `_brain_file`: resolve thật, kiểm còn trong brain, chặn symlink trỏ ra ngoài. Thêm kiểm đuôi, kích thước, thư mục cấm.
   - Khoá so khớp là đường tương đối POSIX, qua `os.path.normcase` trên Windows. Không dùng so tiền tố chuỗi.
3. **Chọn liên kết.**
   - Lấy các liên kết `live` có `origin_kind=handoff`, `origin_ref = <session_id>:<message_id>` **của đúng lượt đang gọi**, đúng `agent_key` và `config_version` của lượt.
   - Có `handoff` thì phải là một trong số đó.
   - Lọc tiếp theo đường đích đã chuẩn hoá của quyền revision.
   - Kết quả: 0 dòng thì `no_open_handoff` hay `path_not_in_scope`; hơn 1 dòng thì `ambiguous_handoff`, không đoán.
4. **Nội dung.**
   - Đổi gạch dài thành "-", có đếm số lần đổi.
   - sha256 tính trên bytes sẽ ghi.
5. **Khoá và dấu vân tay.**
   - Dấu vân tay `fp` = sha256 của `(binding_id, đường chuẩn hoá, sha nội dung, source)`.
   - Khoá: `<binding_id>:<đường chuẩn hoá>`, hay `<binding_id>:<submission_key>` nếu model đưa khoá.
   - Cùng khoá, cùng `fp`: trả biên nhận đã có, kèm trạng thái **hiện tại** của nó (có thể đã `stale`). Không tạo tác động mới.
   - Cùng khoá, khác `fp`: `submission_conflict`.
   - Khác đích mà cùng khoá tuỳ chọn cũng khác `fp`, nên ra xung đột.
6. **Ghi.**
   - Ghi file nháp `output_root/submissions/<submission_id>.md` (file tạm rồi `os.replace`), đọc lại để băm, lưu bằng chứng.
   - Rồi **một giao dịch** kiểm `binding_valid`, quyền có `submit` và đường; đạt thì chèn dòng `submissions` trạng thái `candidate`.
   - Kho bằng chứng và hệ thống file không nằm trong giao dịch SQLite. Hỏng giữa chừng để lại file hay bằng chứng mồ côi, không có dòng.
7. **Trả biên nhận:** mã bản nộp, sha, kích thước, trạng thái. Không có nội dung.

### 4.4 Bảng chuyển trạng thái theo nguồn

**Trạng thái của `submissions`:**

| Trạng thái | Nghĩa |
|---|---|
| `candidate` | Bản nộp hợp lệ, chưa đăng |
| `publishing` | Đã có ý định đăng, đang chờ mốc commit |
| `published` | Đã đăng, và bytes ở đích đã đối chiếu khớp |
| `adopted_in_place` | Chỉ `observed_write` |
| `conflict` | Đích có bytes không khớp baseline |
| `stale` | Liên kết hết hiệu lực |
| `superseded` | Có bản mới hơn cùng liên kết và cùng đích |
| `rejected` | Bị từ chối |

**`submit_tool`:**

1. `candidate`: mục 4.3.
2. Cuối lượt chat, `handoff_after_turn` chọn bản `candidate` mới nhất của liên kết này (bản cũ hơn thành `superseded`) và gọi **đăng của host** (mục 4.5), đọc bytes từ file nháp.
3. Đăng xong: `published`, và chỉ khi đó mới gọi `adopt_submission`. Đây là bản tách mới của `finish_handoff`: ghi bằng chứng `chat_output`, sự kiện `artifact_adopted`, đóng bàn giao. **Không ghi `published` lần nữa**, vì đăng đã ghi.
4. Đăng gặp xung đột: `conflict`, báo thật. Bàn giao không tiếp nhận gì, giữ bản nháp.

**`background_text`:** sắp lại thứ tự `_work_post_core`:

1. Receipt, rồi bằng chứng.
2. **Chèn bản nộp `candidate`** với liên kết `action` của lượt.
3. Chấm trên bản ứng viên, như hôm nay.
4. Đăng **từ bản nộp** (mục 4.5).
5. `_publish_latest` (đăng lại khi lần trước bị chặn) chỉ lấy bản nộp `candidate` của revision hiện hành có `binding_valid`. Không lấy đầu ra hành động trần như trước.

**`observed_write`:**

- Engine đã ghi bytes ở đích, nên đây là **ngoại lệ**: host tiếp nhận tại chỗ, không đăng lại.
- Điều kiện tiếp nhận:
  - biên nhận Write hợp lệ, theo luật cũ;
  - bytes ở đích khớp sha của biên nhận;
  - `binding_valid` của liên kết `handoff`;
  - quyền có `publish` cho đúng đích.
- Đạt thì ghi `adopted_in_place` và mốc `published`, kèm nguồn `observed_write`. Biên bản ghi rõ đây là file engine đã ghi, không phải file host vừa đăng.

**Cùng lượt có Write A ở đích và nộp B (D3):**

1. Nếu A có biên nhận hợp lệ, host tiếp nhận A tại chỗ trước, A thành baseline. Sau đó host đăng B đè lên A qua CAS và guard, vì baseline lúc này đã là A.
2. Nếu A không có biên nhận hợp lệ, đích đang mang bytes lạ không có baseline. Host báo `conflict` và giữ B ở `candidate`.
3. **Không bao giờ ghi baseline của B lên file A** để ép đăng.

### 4.5 Đăng của host: thứ tự với thu hồi

Mọi đường thay mốc sản phẩm đi qua đúng một hàm `host_publish(submission)`:
- đăng thường;
- nhánh cùng nội dung (`same`);
- đăng lại;
- đối soát;
- lượt làm sản phẩm A3.

Bốn giao dịch ngắn, không giữ khoá trong lúc gọi model:

1. **Ý định.** Giao dịch kiểm:
   - `binding_valid` của bản nộp;
   - quyền có `publish` và đích đúng;
   - guard trên bytes bản nộp;
   - đọc baseline (`published`) và hash hiện tại của đích.

   Đạt thì ghi `actions(kind=publish)` mang `binding_id` và chuyển bản nộp sang `publishing`.
   - Đích đã cùng hash với bản nộp (nhánh `same`): tới bước 4 luôn, **trong chính giao dịch này**, sau khi đã kiểm quyền. Bỏ con đường đi vòng hiện có.
2. **Ghi tạm.** Ghi file tạm cạnh đích, ngoài giao dịch.
3. **Mốc commit.** Giao dịch `BEGIN IMMEDIATE`:
   - kiểm lại `binding_valid`;
   - đọc lại hash đích, so với baseline đã đọc ở bước 1.

   Đạt thì ghi `commit_at` vào hành động đăng. Thao tác thu hồi cũng dùng `BEGIN IMMEDIATE` trên cùng kho, nên hai việc được **tuần tự hoá**:
   - **Thu hồi commit trước:** bước 3 thấy liên kết chết, xoá file tạm, hành động thành `aborted`, bản nộp về `stale`.
   - **Bước 3 commit trước:** tác động đã được phép. Thu hồi sau đó chặn các tác động tiếp theo. Javis báo đúng là "đã đăng trước khi thu hồi".
4. **Thay file và ghi mốc.**
   - `os.replace`, rồi đọc lại hash đích.
   - Khớp: giao dịch `set_published`, bản nộp `published`.
   - Không khớp: `conflict`.

**Giới hạn:** không có tính nguyên tử giữa SQLite và hệ thống file. Người dùng sửa file đúng giữa bước 3 và `os.replace` vẫn có thể mất bản sửa đó. Bước 4 phát hiện khi đọc lại hash không khớp, ghi `conflict`, giữ bản nháp.

### 4.6 Ai đọc gì ở từng trạng thái

| Bên đọc | Đọc |
|---|---|
| Evaluator `artifact_contract`, `_artifact_file`, `artifact_ref` | Bytes đã đăng ở đích (như hôm nay). Chấm ứng viên trước khi đăng dùng bytes bản nộp, giống luật guard trên ứng viên hiện có |
| "Bản hiện có" trong prompt việc nền | **Chỉ bytes đã đăng** ở đích thuộc `read_paths`. Không bao giờ dùng bản nộp chưa đăng |
| Xác nhận "Đạt yêu cầu" của người dùng | Gắn sha đã đăng; không gắn bản nháp |
| Thẻ mục tiêu | Bản đã đăng, cộng số bản nháp chờ đăng hay xung đột |
| `_publish_latest` | Bản nộp `candidate` có `binding_valid`, không lấy đầu ra trần |

### 4.7 Điểm hỏng và đối soát (không gọi model)

| Điểm hỏng | Trạng thái để lại | Đối soát ở lần thức sau |
|---|---|---|
| Đã ghi file nháp, chưa chèn dòng | File mồ côi trong `submissions/` | Bỏ qua. Không tự nhận file không có dòng. Dọn sau 7 ngày |
| Đã chèn `candidate`, chưa có ý định đăng | `candidate` | Liên kết còn sống: đăng (mục 4.5). Chết: `stale` |
| Có ý định, chưa qua mốc commit | `publishing`, hành động chưa có `commit_at` | Xoá file tạm, hành động `aborted`, bản nộp về `candidate` nếu liên kết còn sống, không thì `stale` |
| Qua mốc commit, chưa `os.replace` | Hành động có `commit_at` | Đích vẫn bằng baseline: thay file và ghi mốc. Tác động đã được phép trước mọi thu hồi sau đó. Đích đã khác: `conflict` |
| Đã thay file, chưa ghi mốc | Hành động có `commit_at` | Đích bằng sha bản nộp: ghi mốc, `published`. Khác: `conflict` |
| Lượt nền chết sau khi ghi đầu ra, trước khi chèn bản nộp | Hành động bị ngắt | `_reconcile` chèn bản nộp từ receipt của hành động nếu liên kết còn sống, không thì `stale`. Không tự đăng lại đầu ra trần |
| Lượt chat chết, Claude Write không còn biên nhận | Bàn giao hết hạn | Như hôm nay: đích lạ không có baseline thành drift hay `conflict` (A2). Không nhận làm sản phẩm |

## 5. Quyền có phạm vi

### 5.1 Hai tầng: phạm vi gốc và quyền revision

Cả hai tầng nằm trong bảng `grants` (mục 7.1):

- **Phạm vi gốc** (`kind=root`, `parent_id` rỗng). Do chủ dự án xác lập. **Độc lập với tiêu chí model sửa.**
  - Mang đích được phép (một đường, vì A4 có một sản phẩm mỗi mục tiêu).
  - Mang tập thao tác: `read_deliverable`, `submit`, `publish`; `communicate` luôn tắt.
  - Có `generation`, `status`.
- **Quyền revision** (`kind=revision`, cha là phạm vi gốc).
  - Bằng `narrow(gốc, cái revision cần)`.
  - Cái revision cần lấy từ `_deliverable_rel(revision)`, không phải mọi đường tiêu chí.
  - Ghi `parent_generation` = `generation` của gốc lúc cấp.

**Quyền revision hiệu lực** khi chính nó `active` **và** gốc `active` với đúng `parent_generation`. Liên kết lượt ghim cả hai (mục 4.2).

### 5.2 Phạm vi gốc đến từ đâu

| `source` | Khi nào | Đích | Ghi chú |
|---|---|---|---|
| `owner_message` | Lập mục tiêu trong phiên trợ lý, và đường đích **có trong chính lời chủ dự án** của tin lập mục tiêu (so sau chuẩn hoá) | Đường đó | Chủ dự án đã nêu đích; dùng ngay, không hỏi |
| `owner_approved` | Chủ dự án bấm "Cho phép" trên thẻ cho **một đường cụ thể** host đưa ra (mục 5.3) | Đường đó | Hành động owner có dữ liệu phạm vi cụ thể |
| `legacy_frozen` | Lần thức đầu trên mã A4, với mục tiêu lập trước 0.90.0 chưa có dòng quyền nào | `_deliverable_rel` của revision hiện hành | **Tương thích legacy**: đóng băng đúng phạm vi mã 0.89.0 đang cho phép. Không khẳng định chủ dự án đã duyệt |

**Không có phạm vi gốc** khi đích do trợ lý tự chọn lúc lập (không có trong lời chủ dự án). Trường hợp này mục tiêu ở trạng thái **chờ chấp thuận phạm vi**:
- Thẻ hiện "Trợ lý muốn ghi vào `Inbox/x.md`. Cho phép?".
- **Chưa giữ lượt việc nền nào.**
- Nếu trợ lý đã nộp trong lượt lập mục tiêu, bản nộp ở lại `candidate` dưới quyền revision chỉ có `submit`, không có `publish`.

### 5.3 Sửa mục tiêu, mở rộng, thu hồi, cấp lại

**Revision mới cùng đích** (góp ý, nói lại, model sửa tiêu chí mà `_deliverable_rel` không đổi):
- Host cấp quyền revision mới bằng `narrow(gốc hiện hành, đích)`.
- Quyền revision cũ thành `superseded`; liên kết của nó không còn đúng revision cho đăng và tiếp nhận.

**Revision mới khác đích** (model đổi hay thêm đích, dù có câu trích):
- `narrow` cho phần giao rỗng ở thao tác ghi.
- Host ghi **yêu cầu mở rộng** (`scope_requests`, mục 7.1), mục tiêu chờ, thẻ hỏi một lần kèm đường cụ thể. Không giữ lượt nào.
- **Chủ dự án Cho phép:**
  - host tạo phạm vi gốc mới (`owner_approved`) cho đích mới; gốc cũ thành `superseded`;
  - host cấp quyền revision từ gốc mới.
- **Từ chối hay bỏ qua:** yêu cầu đóng, mục tiêu vẫn chờ. Chủ dự án có thể nói lại để trợ lý sửa về đích cũ.

**Câu trích và nút "Đúng ý"** chỉ xác nhận cách hiểu, **không** mở phạm vi.

**Thu hồi** (nút Thu hồi quyền trên thẻ, hay tắt Cộng hưởng của trợ lý). Một giao dịch `BEGIN IMMEDIATE` làm cả bốn việc:
- gốc thành `revoked` và `generation += 1`;
- mọi bản nộp `candidate` hay `publishing` của mục tiêu thành `stale`;
- mục tiêu tạm dừng bằng lệnh `pause` có sẵn;
- liên kết `live` thành `dead`.

**Cấp lại** (Tiếp tục khi đang thu hồi):
- tạo phạm vi gốc **mới** (`owner_approved`, đích như gốc cũ) và quyền revision mới;
- không đảo dòng cũ, không đổi liên kết cũ;
- bản nộp `stale` không được đăng. Muốn dùng lại nội dung thì trợ lý nộp lại dưới liên kết mới.

### 5.4 `narrow` (dùng cho quyền revision trong A4, quyền con trong A5)

`narrow(parent, request) -> grant | reason`:
- Thao tác, đường ghi, đường đọc, người nhận đều là **phần giao**.
- `goal_id` và `brain_id` phải trùng.
- `communicate` chỉ có khi cha có.
- Yêu cầu thiếu trường hay có giá trị lạ: phần giao rỗng.
- So đường bằng khoá chuẩn hoá của mục 4.3 bước 2.

### 5.5 Mọi điểm kiểm

| Điểm | Kiểm (trong giao dịch) |
|---|---|
| `javis_submit_deliverable` | Liên kết của đúng lượt, `binding_valid`, quyền `submit` + đích |
| `begin_action(work)` | Quyền revision hiệu lực. Ghi liên kết `action`. Không có thì không giữ lượt (`grant_missing`, `scope_pending`, `grant_revoked`) |
| `begin_experiment` (phép thử A3) | Như trên, liên kết `experiment`. Mỗi lượt thử kiểm `binding_valid` ở cổng lượt sẵn có (`_TrialCall`). Hỏng thì phép thử dừng `inconclusive` với lý do quyền, theo đường dừng sẵn có |
| Lượt làm sản phẩm A3 (`use_hold`) | Liên kết `followup` mới, kiểm quyền hiện hành, không kế thừa liên kết của phép thử |
| Dựng prompt việc nền | Chỉ bytes đã đăng ở `read_paths` của quyền đã ghim |
| `host_publish` bước 1 và 3 | Mục 4.5, gồm nhánh `same` |
| Tiếp nhận Write tại chỗ | `binding_valid` + `publish` + đích |
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

- **Hub không chặn được native.** Kiểm ở hub không chặn Bash hay Write native của engine có toàn quyền hệ điều hành.
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
  granted_by TEXT NOT NULL, source TEXT NOT NULL,
  actions_json TEXT NOT NULL, write_paths_json TEXT NOT NULL, read_paths_json TEXT NOT NULL,
  recipients_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL, generation INTEGER NOT NULL,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS grants_root_active ON grants(goal_id) WHERE kind='root' AND status='active';
CREATE UNIQUE INDEX IF NOT EXISTS grants_rev_active ON grants(goal_id, revision, parent_id)
  WHERE kind='revision' AND status='active';
CREATE INDEX IF NOT EXISTS grants_goal ON grants(goal_id, kind, status);
CREATE TABLE IF NOT EXISTS grant_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, grant_id TEXT NOT NULL, kind TEXT NOT NULL, by TEXT NOT NULL,
  generation INTEGER NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS scope_requests(
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, revision INTEGER NOT NULL, path TEXT NOT NULL,
  reason TEXT NOT NULL, status TEXT NOT NULL, decided_by TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, decided_at REAL);
CREATE TABLE IF NOT EXISTS bindings(
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  grant_id TEXT NOT NULL, grant_generation INTEGER NOT NULL,
  root_id TEXT NOT NULL, root_generation INTEGER NOT NULL,
  agent_key TEXT NOT NULL, agent_config_version INTEGER NOT NULL,
  origin_kind TEXT NOT NULL, origin_ref TEXT NOT NULL, status TEXT NOT NULL,
  created_at REAL NOT NULL, closed_at REAL, UNIQUE(goal_id, origin_kind, origin_ref));
CREATE INDEX IF NOT EXISTS bindings_origin ON bindings(origin_kind, origin_ref, status);
CREATE TABLE IF NOT EXISTS submissions(
  id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  binding_id TEXT NOT NULL, source TEXT NOT NULL, engine_json TEXT NOT NULL,
  path TEXT NOT NULL, draft_ref TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
  normalized_em_dash INTEGER NOT NULL DEFAULT 0, evidence_id TEXT NOT NULL DEFAULT '',
  idem_key TEXT NOT NULL, fingerprint TEXT NOT NULL, publish_action_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL, status_reason TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(goal_id, idem_key));
CREATE INDEX IF NOT EXISTS submissions_goal ON submissions(goal_id, revision, status);
```

Hành động đăng mang `binding_id`, `submission_id` và `commit_at` trong `intent_json` / `receipt_json` của bảng `actions` có sẵn, không thêm cột.

### 7.2 Nguồn chuẩn

- **Phạm vi:** dòng gốc `active` của mục tiêu. Không có dòng nào thì không có quyền.
- **Quyền của lượt:** chỉ liên kết đã ghim. Không suy từ quyền hiện hành lúc gọi.
- **Sản phẩm:** `published` và `evidence_links`, như A1 tới A3. `submissions` là sổ đầu vào.
- **Hạn mức:** `goals.calls_used` và sổ của A1 tới A3.

### 7.3 Đăng

Theo mục 4.5. Không hứa nguyên tử với hệ thống file.

### 7.4 Nâng cấp, hạ phiên bản, nâng lại (chọn chính sách giới hạn)

Review vòng 1 chỉ ra `apply_command(..., "resume")` của 0.89.0 gỡ tạm dừng mà không biết quyền. Vì vậy tạm dừng **không** bảo toàn được việc thu hồi khi chạy bằng mã cũ. A4 chọn chính sách giới hạn:

**Hạ về 0.89.0 chỉ hỗ trợ khôi phục snapshot hay đọc hồ sơ.** Không hỗ trợ chạy tiếp mục tiêu có quyền A4 bằng mã cũ.

- **Lúc nâng lên:** lần đầu mở kho bằng mã A4 (chưa có bảng `grants`), host chép `resonance.sqlite3` thành `resonance.sqlite3.pre-0.90.0`, **một lần duy nhất**, rồi mới tạo bảng.
- **Hạ đúng cách:**
  - tắt Javis, khôi phục snapshot, chạy 0.89.0;
  - mọi thay đổi của mục tiêu sau lúc nâng lên bị mất: lượt đã chạy, bản đã đăng ghi trong kho, phản hồi;
  - file đã đăng trong brain vẫn còn, và 0.89.0 có thể thấy chúng là drift so với mốc cũ (A2).
  - Biên bản phát hành ghi rõ hậu quả này.
- **Hạ không khôi phục snapshot (không hỗ trợ):**
  - mã cũ không đọc `grants`, nên bấm Tiếp tục là chạy lại mục tiêu đã thu hồi;
  - A4 không hứa gì về trường hợp này.
- **Nâng lại sau khi mã cũ đã chạy:**
  - A4 **không tự cấp** quyền cho revision không có dòng quyền revision mà mục tiêu đã có phạm vi gốc, vì đó là revision mã cũ tạo. Revision như vậy chờ chủ dự án chấp thuận như mục 5.3.
  - Gốc đã `revoked` vẫn `revoked`, không có đường tự hồi sinh.
  - Chỉ mục tiêu chưa từng có dòng `grants` nào mới được đóng băng `legacy_frozen`.

## 8. Giao diện

- **Thẻ mục tiêu**, dòng quyền: "Được: nộp và đăng `Inbox/x.md` · đọc `Inbox/x.md` · tối đa 6 lượt · không giao tiếp với trợ lý khác", kèm nút **Thu hồi quyền** (xác nhận một lần).
- **Chờ chấp thuận:** "Trợ lý muốn ghi vào `Private/y.md`. Cho phép / Không".
- **Bản nháp:** "1 bản nháp chờ đăng", hay "Bản nháp bị xung đột với file hiện có; xem trong lịch sử".
- **Trang Cộng sự:** bảng khả năng engine (mục 6.1).
- Chữ qua `vi.json` và `en.json`. Không có ô cấu hình quyền kỹ thuật.

## 9. Chốt dừng và lỗi

| Tình huống | Hành vi |
|---|---|
| Thu hồi khi lượt chat còn sống | Lời nộp sau đó hỏng điều kiện 3 của `binding_valid`. Bản nộp trước đó thành `stale` ngay trong giao dịch thu hồi. Lượt đã chạy vẫn tính |
| Thu hồi rồi cấp lại khi cùng lượt chat còn sống | Lượt vẫn ghim gốc cũ, nên mọi lời nộp bị từ chối. Trợ lý cần lượt mới |
| Thu hồi khi lượt nền đang gọi engine | Đầu ra ghi như hôm nay. Bản nộp chèn sau có liên kết chết nên `stale`. Không đăng. Lượt đã dùng giữ nguyên |
| Thu hồi sau ý định đăng, trước khi thay file | Thứ tự theo mốc commit (mục 4.5) |
| Cùng nội dung sau thu hồi | Nhánh `same` kiểm quyền trước, nên không tạo baseline |
| Đổi trợ lý hay phiên bản giữa lượt | Như A1: `agent_changed`, điều kiện 4 của `binding_valid` hỏng |
| Phép thử A3 gặp quyền bị thu hồi | Dừng `inconclusive` (lý do quyền), hoàn lượt chưa ghi ý định theo luật A3 |

## 10. API và công cụ

- **`javis_submit_deliverable(path, content, submission_key?, handoff?)`:** công cụ hub.
  - Công cụ lập và sửa mục tiêu trả thêm `handoff` (mã liên kết) khi host mở bàn giao.
- **`GET /goals/{id}`:** thêm các trường:
  - `scope`: gốc, đích, trạng thái;
  - `grant`: quyền revision;
  - `scope_request`: nếu có;
  - `submissions` gần nhất.
- **`POST /goals/{id}/commands`:**
  - `revoke_grant`: owner, CAS `expected_revision`;
  - `approve_scope`: owner, mang `request_id` và `path` khớp yêu cầu;
  - `deny_scope`;
  - `resume`: khi gốc `revoked` thì cấp lại theo mục 5.3.
- Không route nào cho model tạo, mở rộng hay cấp lại quyền.

## 11. Hiệu năng

- Đọc quyền, liên kết và bản nộp theo chỉ mục; một truy vấn mỗi điểm kiểm. Không quét file hay trợ lý mỗi nhịp.
- I/O của công cụ nộp và của đăng chạy ở luồng phụ. Giao dịch `BEGIN IMMEDIATE` chỉ bọc đọc và ghi kho, không bọc lời gọi model.
- Thẻ đọc quyền trong `goal_view` đã giới hạn (0.88.5).

## 12. Ma trận nghiệm thu (đồng hồ giả, engine giả, không model thật)

Mỗi ca có đối chứng hợp lệ đi qua. Ca race chèn thay đổi ngay trước giao dịch cần bảo vệ.

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
| G12 | Prompt việc nền không chứa file ngoài `read_paths`, không chứa bản nháp chưa đăng |
| G13 | Đích ngoài phạm vi, `..`, symlink ra ngoài, đuôi lạ, quá 1MB: từ chối trước khi ghi |
| G14 | Engine tự ghi native vào đích mà không nộp: không thành sản phẩm; đăng gặp `conflict` |
| G15 | Không có quyền, quyền hỏng, thao tác lạ: không giữ lượt |
| G17 | Nhiệm vụ hợp lệ trong phạm vi: nộp, đăng, tiếp nhận đúng một lần, không gọi thêm model |
| G18 | Nhiều mục tiêu chưa tới hạn: không đọc file, không đánh thức model; event loop không bị chặn khi nộp song song |
| G20 | Chat thường, kênh ngoài, workflow gọi công cụ nộp: `not_agent_turn` |
| G22 | Bảng khả năng engine. **Kiểm đường truyền thật**: header của Claude, `-c` của Codex, trong tiến trình của engine API. Grok và Antigravity bị từ chối |

### 12.2 Ca thêm theo review vòng 1

| Ca | Tình huống | Kỳ vọng | Điểm review |
|---|---|---|---|
| G23 | Góp ý không nhắc đường, model đổi hay thêm đích (có câu trích hợp lệ) | Không cấp quyền vào đích mới; ghi `scope_requests`; không giữ lượt; không đọc đích mới vào prompt | P1-1 |
| G24 | Revision mới cùng đích | Quyền revision mới tự cấp trong phạm vi, không hỏi | P1-1 |
| G25 | Chủ dự án Cho phép đúng đường của yêu cầu; gửi đường khác với yêu cầu | Khớp: gốc mới `owner_approved`, làm tiếp. Lệch: từ chối | P1-1 |
| G26 | Mục tiêu có hai đường tiêu chí | Quyền và đích chỉ là đường đầu (`_deliverable_rel`); đường hai chỉ được evaluator đọc | P1-1 |
| G27 | Lập mục tiêu, đích có trong lời chủ dự án; đích do trợ lý tự chọn | Có trong lời: `owner_message`, làm ngay. Tự chọn: chờ chấp thuận, chưa giữ lượt | P1-1 |
| G28 | Mục tiêu cũ trước 0.90.0 | `legacy_frozen` đúng `_deliverable_rel`. Mục tiêu chờ gán không có quyền | P1-1 |
| G29 | Thu hồi rồi cấp lại khi cùng lượt chat còn sống | Lượt đó không nộp được nữa | P1-2 |
| G30 | Lời nộp cùng phiên nhưng khoá lượt là tin khác (đan xen hai tin) | Chỉ thấy liên kết của tin mình | P1-2, P2-1 |
| G31 | Thu hồi sau bước 1 (ý định), trước bước 3 (mốc commit) | Đăng bị huỷ, file đích không đổi, bản nộp `stale` | P1-2 |
| G32 | Mốc commit commit trước, thu hồi ngay sau, trước `os.replace` | Tác động hoàn tất. Báo "đã đăng trước khi thu hồi". Lần đăng sau bị chặn | P1-2 |
| G33 | Nhánh `same` sau thu hồi | Không tạo baseline | P1-2 |
| G34 | Phép thử A3 khi quyền bị thu hồi giữa lượt thử | Dừng `inconclusive`, lý do quyền; lượt làm sản phẩm không chạy | P1-2 |
| G35 | Đối soát hành động mang liên kết `generation` cũ | Không đăng, không ghim lại | P1-2 |
| G36 | Nộp khi đích chưa có | Host đăng: file được tạo, mốc đúng sha | P1-3 |
| G37 | Nộp khi đích có bản người dùng không có baseline | `conflict`, file người dùng nguyên vẹn, bản nháp giữ lại | P1-3 |
| G38 | Cùng lượt: Write A hợp lệ, rồi nộp B | Tiếp nhận A tại chỗ, rồi đăng B qua CAS; mốc cuối là B | P1-3 |
| G39 | Write A không có biên nhận, nộp B | `conflict`; không ghi baseline B lên A | P1-3 |
| G40 | Hỏng ở từng điểm của mục 4.7 (chèn lỗi ngay trước và sau mỗi bước) | Đối soát đúng bảng; 0 lượt model; không nhận file mồ côi | P1-3 |
| G41 | Bản nộp hợp lệ hoàn tất mà không cần model viết lại | Lượt nền và lượt chat đều đăng từ bản nộp | P1-3 |
| G42 | `finish_handoff` cũ không còn được gọi với bản nháp chưa ở đích | Chỉ `adopt_submission` sau khi đăng, hay tiếp nhận tại chỗ khi có biên nhận Write | P1-3 |
| G43 | Hai mục tiêu cùng phiên, cùng đích, cùng tin | `ambiguous_handoff`. Có `handoff` hợp lệ thì chọn đúng | P2-1 |
| G44 | Cùng khoá tuỳ chọn, cùng bytes, khác đích | `submission_conflict` | P2-1 |
| G45 | Đường alias: chữ hoa thường trên Windows, `./`, `a/../a` | Chuẩn hoá về cùng khoá; symlink ra ngoài bị chặn | P2-1 |
| G46 | Phát lại sau khi cấp lại | Trả biên nhận cũ với trạng thái `stale`; không tác động mới | P2-1 |
| G47 | Nâng lên A4 | Có `resonance.sqlite3.pre-0.90.0` đúng một bản, bằng kho trước nâng | P2-2 |
| G48 | A4 thu hồi, rồi chạy `resume` của mã 0.89.0 (lấy qua `git archive`) | Ghi nhận đúng là không hỗ trợ: mã cũ chạy lại. Test chứng minh giới hạn được ghi trong tài liệu là đúng sự thật, không chứng minh là được chặn | P2-2 |
| G49 | Nâng lại sau khi mã cũ tạo revision mới | Không tự cấp quyền cho revision đó; gốc `revoked` vẫn `revoked` | P2-2 |
| G50 | Khôi phục snapshot rồi chạy 0.89.0 | Kho mở được, mục tiêu ở trạng thái lúc nâng lên | P2-2 |

### 12.3 Chuyển sang A5

| Ca | Lý do |
|---|---|
| Hai việc con tranh lượt cuối | A4 không có việc con |
| Đổi người nhận trước khi callback hoàn tất | A5 |
| Worker nộp review dưới danh tính reviewer | A5 |
| Hash, revision, tiêu chí đổi sau review | A5 |
| Approval công cụ, gửi kênh khác | A4 không có quyền gửi kênh |

## 13. Quyết định mặc định cần review

| # | Quyết định | Sau review vòng 1 |
|---|---|---|
| D1 | Phạm vi gốc độc lập với tiêu chí. Đích chủ dự án nêu thì dùng ngay; đích trợ lý chọn hay đổi thì hỏi một lần | Sửa theo P1-1 |
| D2 | Đăng chỉ qua `host_publish` | Giữ, thứ tự ở mục 4.5 |
| D3 | Giữ quan sát Write; quy tắc Write A + nộp B ở mục 4.4 | Sửa theo P1-3 |
| D4 | Grok và Antigravity không nhận bàn giao chat | Giữ; kiểm đường truyền thật khi code |
| D5 | Không mở việc nền thêm | Giữ |
| D6 | Thu hồi = gốc `revoked` + `stale` + tạm dừng, trong một giao dịch | Giữ cho runtime A4; bỏ lời hứa quay về an toàn nhờ tạm dừng |
| D7 | Mở rộng qua yêu cầu có đường cụ thể, chủ dự án Cho phép | Sửa: revision chỉ là điều kiện liên kết, không phải thẩm quyền |
| D8 | `communicate` tắt trong hợp đồng Resonance | Giữ, phạm vi ghi đúng ở mục 6.3 |
| D9 | `read_paths` là phạm vi prompt việc nền | Giữ, phạm vi ghi đúng ở mục 6.3 |
| D10 | Không có hạn dùng quyền trong A4 | Mới. Mã cũ không thấy hạn dùng; để sau |
| D11 | Hạ phiên bản chỉ hỗ trợ khôi phục snapshot | Mới, theo P2-2 |

## 14. Kế hoạch code (sau khi thiết kế đạt review)

1. **Kho:**
   - bảng ở mục 7.1, snapshot khi nâng lên;
   - `scope_*` (gốc, yêu cầu, chấp thuận, thu hồi, cấp lại), `grant_rev_*`;
   - `binding_open/close/valid` gắn vào `_open_handoff`, `begin_action`, `begin_experiment`;
   - `submission_*`, `adopt_submission`;
   - giao dịch `BEGIN IMMEDIATE` cho mốc commit và thu hồi.
2. **Chính sách thuần** (`resonance_grants.py`): khoá đường chuẩn hoá, `narrow`, `allows`, dấu vân tay, `ENGINE_CAPS`, quy tắc nguồn gốc phạm vi.
3. **Hợp đồng** (`resonance.py`):
   - `host_publish` bốn bước, thay mọi chỗ gọi `set_published` và `_publish`;
   - sắp lại `_work_post_core`;
   - `_publish_latest` theo bản nộp;
   - `handoff_after_turn` theo bản nộp và quy tắc A/B;
   - cổng trong phép thử A3;
   - đối soát theo mục 4.7.
4. **Công cụ hub** `javis_submit_deliverable` (plugin `javis-goal`). Công cụ lập và sửa mục tiêu trả `handoff`.
5. **API** theo mục 10.
6. **Giao diện** theo mục 8.
7. **Test:**
   - `test_resonance_a4_grants.py`: ma trận 12.1 và 12.2;
   - `test_resonance_a4_rollback.py`: G47 tới G50 với `33a3c1aa`;
   - `test_resonance_a4_ui.js`;
   - một test đường truyền khoá lượt thật cho Claude, Codex và engine API.
8. **Tài liệu:** hướng dẫn, biên bản, lộ trình, ghi chú phát hành về hạ phiên bản.

## 15. Ranh giới bằng chứng

- **17 ca Paperclip** là bằng chứng về Paperclip.
- **10 kiểm của reviewer vòng 1** chứng minh giả định về mã nền. Đó không phải test A4.
- **Mục 2:** đọc mã tại `9716cecf`.
- **Phần còn lại** là đề xuất.

## 16. Thay đổi sau review vòng 1 (`5edfc9b6`)

| Điểm | Sửa | Mục |
|---|---|---|
| P1-1: revision do model sửa tự cấp quyền vào đích mới | Phạm vi gốc độc lập với tiêu chí. Quyền revision = `narrow(gốc, _deliverable_rel)`. Đổi đích thì thành yêu cầu mở rộng chờ chủ dự án với đường cụ thể. Đích lúc lập chỉ được ngay khi có trong lời chủ dự án. Legacy đóng băng, ghi rõ là tương thích. Một sản phẩm mỗi mục tiêu | 1, 5.1 tới 5.3, 12.2 (G23 tới G28) |
| P1-2: chưa ghim quyền vào lượt; nhánh `same` đi vòng; chưa có thứ tự với thu hồi | Bảng `bindings` ghim quyền revision, gốc, `generation`, trợ lý, nguồn lượt; tạo trong giao dịch mở bàn giao, giữ lượt, phép thử, lượt làm sản phẩm. `host_publish` bốn bước có mốc commit `BEGIN IMMEDIATE` tuần tự với thu hồi. Mọi đường thay mốc qua đó, gồm `same`, đối soát, A3 | 4.2, 4.5, 5.5, 9, 12.2 (G29 tới G35) |
| P1-3: dùng `finish_handoff` như thể bản nháp đã ở đích; bản nộp nền chèn sau bước đăng | Bảng chuyển trạng thái theo ba nguồn. Đăng bytes từ bản nháp qua `host_publish`. `adopt_submission` tách khỏi ghi mốc. Sắp lại `_work_post_core` (chèn bản nộp trước đăng). Quy tắc Write A + nộp B. Bảng ai đọc gì. Bảng đối soát điểm hỏng | 4.4, 4.6, 4.7, 12.2 (G36 tới G42) |
| P2-1: chọn mục tiêu theo phiên + đường; chống trùng chỉ theo sha | Chọn theo liên kết của đúng tin đang gọi; nhiều kết quả thì `ambiguous_handoff`, có `handoff` do host cấp. Dấu vân tay toàn thao tác. Đường chuẩn hoá qua `_brain_file` + `normcase` | 4.3, 12.2 (G43 tới G46) |
| P2-2: tạm dừng không bảo toàn thu hồi khi chạy mã 0.89.0 | Chọn chính sách giới hạn: hạ phiên bản chỉ khôi phục snapshot tạo lúc nâng lên. Không hỗ trợ chạy tiếp bằng mã cũ. Nâng lại không tự cấp quyền cho revision mã cũ tạo. Bỏ `expires_at` | 7.4, D10, D11, 12.2 (G47 tới G50) |
| Lưu ý chữ "không ghi gì" ở mục 4.2 cũ | Đổi thành "không có bản nộp được chấp nhận hay tác động lên đích"; ghi rõ ranh giới giao dịch với kho bằng chứng và hệ thống file | 4.3 |
