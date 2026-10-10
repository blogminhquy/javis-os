# Resonance A4: nộp sản phẩm đa engine qua một hợp đồng host, kèm quyền có phạm vi

**Trạng thái:** thiết kế vòng 1, chờ review. **Chưa có mã A4.** Nhánh `claude/resonance-a4-handoff-grants`, PR nháp #604, đặt số 0.90.0.

- **Nền:** `main` tại `33a3c1aa` (0.89.0). Đã phát hành: A1 0.87.0, A2 0.88.0, A3 0.89.0; bản hiệu năng 0.88.5 (#602) đã vào `main`.
- **Lộ trình:** [agent scope roadmap](2026-10-08-resonance-agent-scope-roadmap.md), mục 7 (A4, A5).
- **Đầu vào giao quyền** (ngoài git):
  - báo cáo Paperclip 08/10: `exports/reviews/paperclip-javis-assessment-2026-10-08.md`;
  - bản bổ sung 10/10: `exports/reviews/2026-10-10-resonance-delegation-paperclip-review-supplement.md`.
- **Phạm vi bằng chứng:**
  - đã khảo sát mã thật tại `9716cecf` (trùng `33a3c1aa` ở `server/`);
  - không gọi model;
  - chưa có mã hay test A4 nào.

  Bảng "đã có" ở mục 2 là mã đã đọc; mọi thứ khác là đề xuất.

## 1. Mục tiêu và ngoài phạm vi

**Mục tiêu A4:** mọi engine nộp sản phẩm của một mục tiêu theo **cùng một hợp đồng host**.

> Host xác định ai đang làm (trợ lý, phiên bản cấu hình, mục tiêu, revision, quyền). Engine nộp nội dung qua đường host kiểm. Host tự đọc và băm bytes, lưu thành ứng viên có biên nhận, rồi mới tiếp nhận hay đăng theo luật đã có.

Kèm theo là **quyền có phạm vi** (giao quyền) học từ Paperclip, ở mức tối thiểu A4 cần:
- lưu bền;
- gắn với mục tiêu;
- chỉ hẹp lại khi giao xuống;
- thu hồi được bằng `generation`;
- kiểm tại điểm tác động.

A5 dùng lại đúng hợp đồng này cho cặp làm/review.

**Người dùng thấy gì:**
- Anh giao kết quả và phạm vi một lần ("viết ghi chú X vào Inbox/x.md").
- Trợ lý tự làm trong phạm vi đó và chỉ hỏi lại khi phải mở rộng quyền.
- Thẻ mục tiêu hiện được làm gì, trên đâu, tối đa bao nhiêu lượt, có được giao tiếp không, kèm nút Thu hồi.

**Giữ nguyên:**
- **Luật hạn mức (A1 tới A3):** giữ chỗ trong giao dịch, trần chung, "chưa gọi thì trả, đã gọi thì giữ", `call_holds`.
- **Luật đăng:** đường dẫn của tiêu chí, danh sách cấm, guard trên bản ứng viên, CAS theo `published`.
- **Bàn giao chat:** `handoffs`, `handoff_agents`, `finish_handoff`.
- **Lượt việc nền:** vẫn chỉ sinh chữ, host ghi file.
- **Kho:** bảng cũ không đổi cột; A4 chỉ thêm bảng mới.

**Ngoài phạm vi A4:**
- **Đội hai vai, việc con, quyền con thực sự được cấp:** thuộc A5. A4 chỉ có hàm thu hẹp quyền và schema đủ để A5 dùng (mục 5.4).
- **Sandbox mới cho engine có công cụ native:** A4 không hứa chặn Bash hay Write native của engine (mục 6.3).
- **Mở việc nền Resonance cho Codex, Grok, Antigravity:** việc nền vẫn chỉ cho engine đã chứng minh chạy chỉ chữ (mục 6.2).
- **Phần lớn Paperclip:** mô hình công ty, vai trò, trust rule, policy engine; quyền mặc định rộng cho trợ lý mới.
- **Mở rộng quyền qua chat** ("cho em ghi thêm thư mục Y"): mở rộng đi qua sửa mục tiêu, tạo revision mới (mục 5.3).

## 2. Hiện trạng: dùng lại và khoảng trống (mã tại `9716cecf`)

| Đã có | Chỗ trong mã | Khoảng trống A4 lấp |
|---|---|---|
| Danh tính lượt do host gắn: `kenh`, `session_id`, `message_id`, `agent{key, slug, config_version}`. Truyền qua `X-Javis-Turn` (Claude, Codex) hay trong tiến trình (engine API) | `turn_context.make/current/issue_key`, `main.run_turn`, `mcp_hub` đổi khoá về lượt | Lượt không mang mục tiêu, revision, quyền. Grok và Antigravity không truyền khoá lượt. Lượt việc nền không gắn lượt |
| Cổng trợ lý hai lớp, ghim version: `agent_gate` kiểm sớm, `_agent_block` trong giao dịch | `resonance.agent_gate`, `resonance_store._agent_block`, `begin_action`, `finish_handoff` | Chỉ kiểm trợ lý; không có phạm vi theo đường dẫn hay thao tác. `Principal` chỉ khoanh theo brain |
| `CapabilityGrant`: giới hạn replan theo agent, capability, quyền ghi | `agent_runtime.py` | Chỉ sống trong bộ nhớ một lần replan workflow: không lưu, không thu hồi, không generation, không phạm vi đường dẫn, không dính Resonance. **A4 không mở rộng lớp này** |
| Hạn mức trong SQLite: `begin_action` giữ chỗ, `JAVIS_RESONANCE_CALL_CEILING`, hoàn lượt khi chưa gọi, `call_holds` có generation và đối soát | `resonance_store.begin_action/finish_action/release_call/reconcile_holds` | Đủ cho A4. Quyền chỉ tham chiếu hạn mức mục tiêu, không thêm bộ đếm |
| Lượt việc nền: model chỉ trả chữ, host ghi `output_root/<action_id>.md`, băm bằng đọc lại, sinh `ActionReceipt` | `resonance.run_once`, `_work_post_core` | Đã đúng hợp đồng; chỉ cần ghi bản nộp chung (mục 4.3) |
| Đăng: kiểm đường tiêu chí, đuôi, 1MB, thư mục cấm; guard trên ứng viên; CAS theo `published`; ý định đăng mang agent | `resonance._publish`, `_publish_latest`, `set_published` | Chưa kiểm quyền có phạm vi. CAS là đọc rồi ghi, chưa khoá file (mục 7.3) |
| Bàn giao chat Claude: Write có id và toàn văn chỉ là ứng viên; cần `tool_result` thành công cùng id; công cụ khác làm mất hiệu lực; so bytes trên đĩa | `resonance.note_turn_event`, `handoff_after_turn`, `_TURN_WRITES` | **Chỉ Claude**, và sổ biên nhận chỉ trong bộ nhớ, mất khi khởi động lại. Codex không có kết quả theo id; Antigravity không có trạng thái thành công; engine API không có biên nhận cho `javis_write_file` |
| Kho bằng chứng mã hoá, kiểm hash khi đọc lại | `main._ResonanceEvidence`, `evidence_store.EvidenceStore` | Hash bằng chứng là của bản đã che bí mật, có thể khác sha bytes sản phẩm |
| Khoá chống trùng: `goals(idempotency_key)`, `goal_events`, outbox `idem`, `actions UNIQUE(goal, revision, kind, seq)`, Kanban `idempotency_key` | | Chưa có khoá cho bản nộp |

- **Không có đường "nộp sản phẩm" nào:** tìm `submit`, `deliverable` trong `server/` không ra công cụ nào.
- **`GoalGrant` chỉ có trên giấy:** tài liệu ngày 06/10 đề xuất `GoalGrant`, `AuthorityService`, `X-Javis-Run`, `grant_generation`, nhưng không có dòng mã nào triển khai. A4 lấy phần tối thiểu của ý đó, không dựng lại toàn bộ.

## 3. Năm bất biến (khung của A4 và A5)

Lấy từ bản bổ sung 10/10, mục 5. A4 hiện thực bất biến 1, 2 (ở mức hàm), 3, 4; bất biến 5 hiện thực ở A5.

1. **Host giữ danh tính và cấp quyền.**
   - Model chỉ đề xuất; host quyết liên kết, quyền và nguồn yêu cầu.
   - Chat thường không có quyền Resonance chỉ vì nhắc tên một trợ lý.
   - Lời model tự khai mục tiêu, trợ lý hay chủ dự án không được tin.
2. **Giao xuống chỉ thu hẹp.**
   - Quyền hiệu lực là **phần giao** của: quyền chủ dự án cấp, quyền người giao, quyền người nhận, quyền của lượt, và khả năng executor thực sự chặn được.
   - Thiếu phạm vi, phạm vi lạ hay cấu hình hỏng thì không có quyền tác động; không bao giờ diễn giải thành toàn quyền.
3. **Chỉ người đang có quyền ở lượt hiện hành được tạo tác động.**
   - Tại điểm tác động phải kiểm lại cả bốn: trợ lý và phiên bản cấu hình; `generation` của quyền; revision; lượt hay bàn giao còn sống.
   - Thu hồi quyền gốc vô hiệu mọi quyền con.
   - Cấp lại không hồi sinh quyền đã thu hồi.
4. **Chi phí và tác động có một nguồn ghi nhận.**
   - Hạn mức chỉ nằm ở mục tiêu (và trần chung).
   - Cùng khoá, cùng nội dung chỉ tạo một tác động.
   - Tác động có thể đã xảy ra mà chưa rõ thì giữ trạng thái chưa xác định để đối soát; không tự hoàn rồi chạy lại.
5. **Làm, review và chốt đạt là ba quyền khác nhau.** Review gắn đúng bytes/hash, revision và bộ tiêu chí (A5).

## 4. Hợp đồng nộp sản phẩm

### 4.1 Ba đường vào, một bản nộp

| Đường | Engine | Ai tạo nội dung | Ai ghi bytes | Biên nhận |
|---|---|---|---|---|
| **Việc nền chỉ chữ** (đã có) | Claude (`anthropic-cli`), engine API | Model trả chữ | Host ghi `output_root/<action_id>.md` | `ActionReceipt` và bản nộp `source=background_text` |
| **Công cụ nộp của hub** (mới) | Engine có khoá lượt tới hub: Claude, Codex, engine API | Model gọi `javis_submit_deliverable(path, content)` | Host ghi vào vùng nháp của mục tiêu, không ghi file người dùng | Bản nộp `source=submit_tool` |
| **Quan sát Write** (đã có, giữ làm đường phụ) | Claude trong chat | Model Write vào brain | Engine | Bản nộp `source=observed_write`, theo luật biên nhận cũ: Write + `tool_result` thành công cùng id + so bytes |

**Bản nộp** (`submissions`, mục 7.1) là một dòng duy nhất cho cả ba đường. Mỗi dòng ghi:
- **Danh tính:** mục tiêu, revision, quyền và `generation`, trợ lý và phiên bản cấu hình.
- **Nguồn:**
  - engine (provider, model) do host đọc, không phải lời model;
  - nguồn lượt: `chat:<message_ref>` hay `action:<id>`.
- **Nội dung:** đường đích, sha256 của bytes thô do host tính, kích thước, mã bằng chứng.
- **Kiểm soát:** khoá chống trùng, trạng thái.

**Không bản nộp nào tự ghi đè file người dùng.** Đăng vào đích vẫn chỉ qua `_publish` (mục 4.4).

### 4.2 Công cụ `javis_submit_deliverable`

Công cụ của hub (`mcp_hub`), có ở mọi engine đi qua hub.

- **Đầu vào:** `path` (đường đích trong brain), `content` (toàn văn), `submission_key` (không bắt buộc).
- **Model không truyền được** mục tiêu, trợ lý hay quyền. Host suy hết từ khoá lượt.

Host làm theo thứ tự dưới đây. Bước nào hỏng thì từ chối kèm lý do rõ và **không ghi gì**.

1. **Danh tính lượt** (`turn_context` từ khoá lượt).
   - Không có lượt, hay lượt đã hết hạn: `no_turn`.
   - Lượt không có trợ lý: `not_agent_turn`. Gồm chat thường, lượt kênh ngoài, lượt workflow.
2. **Mục tiêu của lượt.**
   - Phải là mục tiêu đang `pending` bàn giao của phiên đó (`handoffs` + `handoff_agents`), thuộc đúng trợ lý và đúng phiên bản cấu hình của lượt. Không có thì `no_open_handoff`.
   - Phiên có nhiều mục tiêu mở thì host chọn mục tiêu có đường đích khớp `path`. Không khớp thì `path_not_in_scope`.
3. **Quyền** (mục 5). Quyền hiện hành của mục tiêu phải đạt đủ bốn điều kiện, không đạt thì `grant_*`:
   - đang `active`;
   - `generation` khớp;
   - có thao tác `submit`;
   - `path` thuộc phạm vi ghi.
4. **Nội dung.**
   - Đuôi `.md` hay `.txt`, tối đa 1MB (cùng luật `_publish`).
   - Không chứa đường dẫn thoát khỏi brain.
   - Ký tự gạch dài đổi thành "-" như `run_once`, có đếm số lần đổi.
5. **Khoá chống trùng.**
   - Khoá mặc định là `chat:<message_ref>:<path>`. Model có đưa `submission_key` thì khoá là `<message_ref>:<submission_key>`.
   - Cùng khoá, cùng sha: trả lại biên nhận cũ (`duplicate=true`).
   - Cùng khoá, khác sha: `submission_conflict`, không ghi.
6. **Ghi và băm.**
   - Host ghi bytes vào vùng nháp `output_root/submissions/<submission_id>.md` (file tạm rồi `os.replace`), rồi đọc lại để băm.
   - Host lưu bằng chứng (`_put_evidence`, kind `submission`) và chèn dòng `submissions` **trong cùng giao dịch** với lần kiểm lại bước 2 và 3. Trợ lý, phiên bản, quyền và revision đọc ngay trong giao dịch, không dùng giá trị đã đọc ở các bước trước.
   - Hỏng sau khi đã ghi file nháp: để lại file mồ côi để đối soát, không chèn dòng.
7. **Trả biên nhận.** Gồm mã bản nộp, sha256 do host tính, kích thước, trạng thái `candidate`. Không chứa nội dung.

**Tiếp nhận:**
- Cuối lượt chat, `handoff_after_turn` lấy bản nộp `candidate` mới nhất của đúng đường đích làm sản phẩm của lượt; không cần quan sát Write.
- Có cả bản nộp lẫn Write quan sát được: **bản nộp thắng**, Write ghi `superseded` (D3).
- Tiếp nhận vẫn qua `finish_handoff`. Giữ nguyên các kiểm trợ lý, phiên bản, và việc nền giành quyền.

### 4.3 Đường việc nền

`run_once` giữ nguyên. Sau `_work_post_core`, host chèn một dòng `submissions` trỏ cùng file và hash, `source=background_text`, khoá `action:<action_id>`.

Mục đích duy nhất: mọi sản phẩm của mục tiêu, từ chat hay từ việc nền, đều tra được ở một bảng, có nguồn và engine. Việc này không thêm lượt và không đổi `ActionReceipt`.

### 4.4 Đăng

`_publish` giữ toàn bộ luật hiện có và thêm một cổng. **Trong giao dịch `begin_action(kind=publish)`**, host kiểm:
- quyền hiện hành có thao tác `publish`;
- đích thuộc phạm vi ghi;
- `generation` khớp với bản nộp đang đăng.

Bản nộp thuộc `generation` cũ (quyền đã thu hồi hay đã cấp lại) giữ làm bản nháp, **không đăng**, ghi lý do `grant_stale`.

## 5. Quyền có phạm vi (giao quyền)

### 5.1 Bản cấp quyền

Mỗi quyền là một dòng `grants` (mục 7.1):

| Trường | Nghĩa |
|---|---|
| `id`, `parent_id` | Quyền cha. A4 luôn rỗng; A5 dùng cho quyền con |
| `brain_id`, `goal_id`, `revision` | Phạm vi mục tiêu. Quyền gắn đúng một revision |
| `agent_key`, `agent_config_version` | Trợ lý nhận và phiên bản cấu hình lúc cấp |
| `granted_by`, `source` | Ai cấp: `owner`, hay `host` khi suy ra từ mục tiêu chủ dự án đã giao. Từ đâu: `goal_formed`, `goal_revised`, `owner_regrant`, `migrated` |
| `actions` | Tập thao tác được phép, mã đóng: `read_deliverable`, `submit`, `publish`, `communicate` |
| `write_paths` | Danh sách đường đích chính xác (không phải tiền tố) được nộp và đăng |
| `read_paths` | Danh sách đường được đọc vào prompt |
| `recipients` | Trợ lý được giao tiếp. A4 luôn rỗng |
| `status`, `generation` | `active`, `revoked`, `superseded`. `generation` tăng mỗi lần thu hồi hay cấp lại |
| `expires_at` | Không bắt buộc |
| `created_at`, `updated_at` | |

**Hạn mức không nằm trong quyền.** Quyền tham chiếu hạn mức của mục tiêu (`budget_calls`), không có bộ đếm riêng; thẻ hiện số lượt lấy từ mục tiêu.

### 5.2 Ai cấp, cấp gì (mặc định A4)

Chủ dự án **giao một lần**: khi mục tiêu được lập trong phiên trợ lý (A1). Host suy quyền gốc từ đúng thứ chủ dự án đã thấy và chấp nhận, **không cấp gì rộng hơn mục tiêu**:

- **`write_paths`:** đường của các tiêu chí `artifact_contract` trong revision đóng băng, tức đúng những gì `_publish` đang cho phép hôm nay.
- **`read_paths`:** chính các đường đó. Mục tiêu hôm nay không có danh sách đường nguồn riêng: `source_drift` của A2 chỉ theo dõi file sản phẩm bị sửa ngoài Javis, và prompt việc nền chỉ đọc "Bản hiện có" của sản phẩm. Thêm nguồn đọc khác cần trường mới trong khung mục tiêu, để sau (D9).
- **`actions`:**
  - mặc định gồm `read_deliverable`, `submit`, `publish`;
  - **không** có `communicate`;
  - mục tiêu không có tiêu chí `artifact_contract` thì không có `submit` và `publish`.
- **Trợ lý và phiên bản:** của mục tiêu (`goal_agents`, `handoff_agents`).

**Mục tiêu lập trước 0.90.0** không có dòng quyền:
- Lần thức đầu trên mã A4, host **suy và ghi** quyền theo đúng luật trên cho revision hiện hành, `source=migrated`. Lý do: đó chính là quyền mã 0.89.0 đang cho phép, không rộng hơn.
- Không suy được (thiếu trợ lý, mục tiêu chờ gán) thì không cấp; mục tiêu đứng chờ như A1.

### 5.3 Sửa mục tiêu, thu hồi, cấp lại

- **Revision mới** (người dùng nói lại, góp ý đổi cách hiểu):
  - quyền cũ thành `superseded`;
  - host cấp quyền mới cho revision mới theo mục 5.2, **không** chép phạm vi rộng hơn từ revision cũ;
  - bản nộp gắn revision cũ không được tiếp nhận cho revision mới.
- **Thu hồi** (nút trên thẻ, hay tắt Cộng hưởng của trợ lý). Trong một giao dịch:
  - quyền thành `revoked`, `generation += 1`;
  - mục tiêu thành tạm dừng qua lệnh `pause` đã có. Nhờ vậy mã cũ cũng dừng nếu quay về 0.89.0 (mục 7.4).
- **Cấp lại** (Tiếp tục):
  - tạo dòng quyền **mới** (`source=owner_regrant`, `generation` mới), không đảo dòng cũ về `active`;
  - lượt chat hay lượt nền đang chạy dở mang `generation` cũ bị từ chối ở bước 3 của mục 4.2 và ở cổng đăng.
- **Mở rộng phạm vi** (thêm file đích, thêm quyền giao tiếp):
  - A4 không có đường riêng. Chủ dự án sửa mục tiêu, tạo revision mới, host suy quyền mới;
  - trợ lý gặp nhu cầu ngoài phạm vi thì hỏi một lần trong chat, không tự mở.

### 5.4 Thu hẹp khi giao xuống (cho A5)

Hàm thuần `narrow(parent, request) -> grant | reason`:
- `actions`, `write_paths`, `read_paths`, `recipients` của con là **phần giao** của cha và yêu cầu;
- `goal_id` và `brain_id` phải trùng cha;
- con không bao giờ có `communicate` nếu cha không có;
- `parent_generation` của con ghi `generation` của cha lúc cấp;
- yêu cầu thiếu trường hay có giá trị lạ thì phần giao rỗng, không phải toàn quyền.

**Quyền con hiệu lực** khi con `active` **và** cha `active` với đúng `generation` đã ghi. Vì vậy thu hồi cha vô hiệu mọi con mà không cần sửa từng dòng con.

A4 chỉ có hàm, test hàm và schema `parent_id`; **không** có đường tạo quyền con. A5 dùng.

### 5.5 Kiểm ở đâu

| Điểm | Kiểm | Trong giao dịch? |
|---|---|---|
| `javis_submit_deliverable` | Danh tính lượt, mục tiêu mở của phiên, quyền `submit` và đường | Có (bước 6 mục 4.2) |
| Dựng prompt việc nền | `read_paths`: chỉ nội dung đường được đọc mới vào prompt | Đọc quyền hiện hành ngay trước khi dựng |
| `begin_action(work)` | Quyền `active` của revision hiện hành. Không có thì không giữ lượt, ghi `grant_missing` hay `grant_revoked` | Có |
| `begin_action(publish)` | Quyền `publish`, đường, `generation` khớp bản nộp | Có |
| `finish_handoff` | Như trên, cho bản nộp được tiếp nhận | Có |
| Giao diện | Chỉ đọc để hiển thị; không bao giờ làm căn cứ cấp quyền | Không |

## 6. Engine: khả năng thật và giới hạn

### 6.1 Bảng khả năng do host khai

Bảng `ENGINE_CAPS` trong mã thay nhãn `engine_support` (hiện chỉ để hiển thị).
- Mỗi khả năng là **điều đã kiểm**, không suy từ tên API.
- Cột "Chặn ghi native" mô tả mức chặn của chính engine, không phải lời hứa của A4.

| Provider | Khoá lượt tới hub | Nộp qua công cụ | Quan sát Write có biên nhận | Chặn ghi native | Việc nền chỉ chữ |
|---|---|---|---|---|---|
| `anthropic-cli` | Có (header) | Có | Có | Có, theo từng lời gọi (`can_use_tool`) khi có `allowed_tools` | Có |
| `openai-oauth` (Codex) | Có (`-c`) | **Có (mới)** | Không (không có kết quả theo id) | Chỉ sandbox; tắt được bằng `JAVIS_CODEX_SANDBOX=off` | Không |
| `grok-cli` | **Không** | Không | Không | `--deny` theo mức | Không |
| `antigravity-cli` | **Không** | Không | Không | Chỉ sandbox | Không |
| Engine API | Có (trong tiến trình) | **Có (mới)** | Không | Không có công cụ native; đường ghi duy nhất là hub | Có |

**Hệ quả:**
- Bàn giao chat của mục tiêu mở thêm cho Codex và engine API.
- Grok và Antigravity vẫn không nhận bàn giao chat, vì hub không biết lượt nào gọi.
- Việc nền giữ nguyên danh sách.
- Thẻ trợ lý hiện đúng bảng này thay cho nhãn cũ.

### 6.2 Vì sao không mở việc nền cho Codex, Grok, Antigravity

Việc nền chạy không người theo dõi. Đường đã chứng minh là chỉ chữ: không có công cụ nào, host ghi file.
- **Codex, Grok:** còn công cụ native. `pick_text_only_link` hôm nay chặn đúng.
- **Antigravity:** `strip_tools` làm chuỗi lùi về Claude, lệch provider người dùng đã chọn.

Muốn mở thêm cần bằng chứng engine chạy không công cụ, hoặc một vùng làm việc cô lập thật; A4 không có cả hai. Đây là giới hạn, không phải lỗi.

### 6.3 Giới hạn phải nói thật

- Kiểm ở hub không chặn được Bash hay Write native của engine có toàn quyền hệ điều hành (Codex khi tắt sandbox, Claude ở mức `full`).
- **Biên nhận chứng minh điều đã nộp, không phải điều duy nhất đã xảy ra.**
  - A4 không ghi "trợ lý chỉ ghi được file X" khi executor còn đường ghi khác.
  - A4 chỉ bảo đảm **host chỉ tiếp nhận và đăng** bản đi qua hợp đồng.
- File engine tự ghi native vào brain:
  - không thành sản phẩm, không được đăng;
  - nếu trùng đường đích đã đăng, CAS của `_publish` báo `publish_conflict` như hôm nay.

## 7. Kho

### 7.1 Bảng mới (không đổi cột bảng cũ)

```sql
CREATE TABLE IF NOT EXISTS grants(
  id TEXT PRIMARY KEY, parent_id TEXT NOT NULL DEFAULT '', parent_generation INTEGER NOT NULL DEFAULT 0,
  brain_id TEXT NOT NULL, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  agent_key TEXT NOT NULL, agent_config_version INTEGER NOT NULL,
  granted_by TEXT NOT NULL, source TEXT NOT NULL,
  actions_json TEXT NOT NULL, write_paths_json TEXT NOT NULL, read_paths_json TEXT NOT NULL,
  recipients_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL, generation INTEGER NOT NULL, expires_at REAL,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS grants_active_one ON grants(goal_id, revision, agent_key, parent_id)
  WHERE status='active';
CREATE INDEX IF NOT EXISTS grants_goal ON grants(goal_id, status);
CREATE TABLE IF NOT EXISTS grant_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, grant_id TEXT NOT NULL, kind TEXT NOT NULL, by TEXT NOT NULL,
  generation INTEGER NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS submissions(
  id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  grant_id TEXT NOT NULL, grant_generation INTEGER NOT NULL,
  agent_key TEXT NOT NULL, agent_config_version INTEGER NOT NULL,
  source TEXT NOT NULL, origin_ref TEXT NOT NULL, engine_json TEXT NOT NULL,
  path TEXT NOT NULL, draft_ref TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
  normalized_em_dash INTEGER NOT NULL DEFAULT 0, evidence_id TEXT NOT NULL DEFAULT '',
  idem_key TEXT NOT NULL, status TEXT NOT NULL, status_reason TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL,
  UNIQUE(goal_id, idem_key));
CREATE INDEX IF NOT EXISTS submissions_goal ON submissions(goal_id, revision, status);
```

**Trạng thái bản nộp:**

| Trạng thái | Nghĩa |
|---|---|
| `candidate` | Chờ tiếp nhận |
| `adopted` | Đã thành sản phẩm của lượt |
| `published` | Đã đăng |
| `superseded` | Có bản mới hơn cùng đường |
| `stale` | Quyền hay revision đã đổi |
| `rejected` | Bị từ chối |

### 7.2 Nguồn chuẩn

- **Quyền hiện hành của mục tiêu:** dòng `grants` `active`, không cha, của revision hiện hành. Không có dòng thì không có quyền.
- **Sản phẩm hiện hành:** giữ nguồn chuẩn A1 tới A3 (`published`, `evidence_links`). `submissions` là sổ đầu vào, không thay hai bảng đó.
- **Hạn mức:** chỉ `goals.calls_used` và sổ của A1 tới A3.

### 7.3 Đăng và khe đọc rồi ghi

Hôm nay `_publish` đọc hash file rồi mới `os.replace`, nên có một khe nhỏ: người dùng sửa file đúng giữa hai bước.

A4 thu hẹp khe bằng cách đọc lại hash ngay trước `os.replace` và so với mốc `published`.
- Không hứa nguyên tử với hệ thống file.
- Sửa xen giữa lần đọc thứ hai và `os.replace` vẫn có thể mất; biên bản sẽ ghi rõ.

### 7.4 Di chuyển và quay về

- **Nâng lên A4:** chỉ thêm bảng. Quyền của mục tiêu cũ được suy ở lần thức đầu (mục 5.2).
- **Quay về 0.89.0:** mã cũ không đọc `grants` và `submissions`, nên an toàn vì:
  - mục tiêu đã bị thu hồi quyền đang tạm dừng, mã cũ tôn trọng trạng thái này;
  - bản nộp `candidate` chưa tiếp nhận bị mã cũ bỏ qua, không đăng;
  - mã cũ chỉ quan sát Write của Claude, không có bàn giao chat cho Codex hay engine API, nên không có tác động trái quyền.
- **Nâng lại A4:**
  - quyền đã thu hồi vẫn `revoked`;
  - bản nộp cũ vẫn mang `generation` cũ;
  - không tự hồi sinh.

  Test quay về làm như A3, lấy mã `33a3c1aa` bằng `git archive`.

## 8. Giao diện

- **Thẻ mục tiêu** (`chat-resonance.js`) thêm một dòng quyền:
  - ví dụ "Được: nộp và đăng `Inbox/x.md` · đọc `Inbox/x.md` · tối đa 6 lượt · không giao tiếp với trợ lý khác";
  - kèm nút **Thu hồi quyền**, xác nhận một lần.
- **Sau khi thu hồi:** thẻ ghi "Đã thu hồi quyền. Bấm Tiếp tục để cấp lại." Nút Tiếp tục có sẵn của thẻ cấp quyền mới.
- **Trang Cộng sự:** cột trợ lý hiện bảng khả năng engine (mục 6.1) thay nhãn cũ, ví dụ "Nộp sản phẩm từ chat: có / không (vì sao)".
- Không có ô cấu hình quyền kỹ thuật. Mọi chữ qua `vi.json` và `en.json`.

## 9. Chốt dừng, thu hồi giữa lượt, lỗi

- **Thu hồi khi lượt chat đang chạy:**
  - lời gọi `javis_submit_deliverable` sau thời điểm thu hồi bị từ chối ở bước 3, vì quyền đọc trong giao dịch;
  - lượt vẫn tốn lượt nếu model đã chạy;
  - bản nộp trước thời điểm thu hồi thành `stale`, không tiếp nhận.
- **Thu hồi khi lượt việc nền đang gọi engine:**
  - đầu ra vẫn ghi như hôm nay;
  - bản nộp `background_text` mang `generation` cũ thành `stale`, không đăng;
  - lượt đã dùng giữ nguyên.
- **Đổi trợ lý hay phiên bản cấu hình giữa lượt:** như A1, giữ đầu ra, không đăng, ghi `agent_changed`.
- **Server chết sau khi ghi file nháp, trước khi chèn dòng:** file mồ côi trong `submissions/`; lần thức sau không tự tiếp nhận file không có dòng.
- **Server chết sau khi chèn dòng, trước khi tiếp nhận:**
  - bàn giao hết hạn như hôm nay (`handoff_gate`);
  - bản nộp còn `candidate` được việc nền dùng làm đầu vào "Bản hiện có" nếu cùng revision và cùng `generation`;
  - không đăng tự động.
- **Hai lời nộp đua nhau cùng một đường:**
  - khoá khác nhau thì thành hai dòng; bản được tiếp nhận là bản `candidate` mới nhất **lúc kết thúc lượt**, bản kia `superseded`;
  - cùng khoá thì dòng sau là trùng hay xung đột (bước 5 mục 4.2).

## 10. API và công cụ

- **Công cụ hub `javis_submit_deliverable(path, content, submission_key?)`:** mô tả công cụ nói rõ chỉ dùng trong phiên trợ lý có mục tiêu đang mở, và host tự xác định mục tiêu.
- **`GET /goals/{id}`:** thêm `grant` (thao tác, đường, trạng thái, `generation`) và các `submissions` gần nhất (sha rút gọn, nguồn, engine, trạng thái).
- **`POST /goals/{id}/commands`:**
  - thêm lệnh `revoke_grant`, chỉ owner, CAS theo `expected_revision`;
  - lệnh `resume` có sẵn sẽ tạo quyền mới khi quyền đang `revoked`.
- **Không có route nào** cho model tạo, mở rộng hay cấp lại quyền.

## 11. Hiệu năng

- Đọc quyền theo chỉ mục `grants_goal`, một truy vấn mỗi điểm kiểm. Không quét file hay trợ lý mỗi nhịp.
- `javis_submit_deliverable` làm I/O kho và file ở luồng phụ (như các route A3 và bản 0.88.5), không giữ event loop.
- Thẻ đọc quyền ngay trong `goal_view` đã giới hạn của 0.88.5, không thêm request.

## 12. Ma trận nghiệm thu (đồng hồ giả, engine giả, không model thật)

Ma trận đối chiếu mục 9 của bản bổ sung Paperclip.
- Mỗi ca có một đối chứng hợp lệ đi qua, để tránh "chặn hết nên test xanh".
- Ca race chèn thay đổi quyền ngay trước giao dịch cần bảo vệ.

### 12.1 Thuộc A4

| Ca | Kỳ vọng |
|---|---|
| G1. Người giao có quyền, người nhận không có (hàm `narrow`) | Phần giao rỗng; không cấp bằng phép hợp |
| G2. Quyền con xin đường rộng hơn cha, hay mục tiêu khác (hàm) | Từ chối; không đọc, ghi hay gọi model |
| G3. Lượt có trợ lý nhưng quyền không có `communicate` | Không công cụ hay route nào tạo việc cho trợ lý thứ ba |
| G4. Model tự khai mục tiêu, trợ lý hay chủ dự án trong tham số; công cụ MCP có tên giống `javis_submit_deliverable` | Tham số lạ bị bỏ qua; host chỉ dùng khoá lượt; không nâng quyền |
| G5. Công cụ có trong danh sách, quyền bị thu hồi ngay trước lời gọi (chèn trước giao dịch) | Lời nộp bị từ chối `grant_revoked`; không dòng hay file nào được tiếp nhận |
| G6. Đã cấp lại sau thu hồi, lời nộp của lượt cũ (`generation` cũ) đến muộn | Từ chối hay `stale`; không tiếp nhận, không đăng |
| G7. Thu hồi khi lượt việc nền đang gọi engine | Đầu ra giữ làm nháp, `stale`, không đăng; lượt đã dùng vẫn tính |
| G8. Khởi động lại sau thu hồi, sau hết hạn | Quyền không tự hồi sinh; lượt không hoàn hai lần |
| G9. Lỗi trước và sau khi engine có thể chạy (giữ nguyên luật A1 tới A3) | Trước: hoàn lượt. Sau: giữ lượt |
| G10. Nộp lại cùng khoá cùng nội dung; cùng khoá khác nội dung | Trùng: dùng lại biên nhận. Khác: `submission_conflict`, không ghi |
| G11. Sửa file agent hay instructions để tự thêm đường, thêm `communicate` | Quyền host không đổi; cổng `agent_changed` như A1 |
| G12. Dựng prompt việc nền khi trong brain có file ngoài `read_paths` | Nội dung file đó không vào prompt |
| G13. Đường nộp ngoài `write_paths`, thoát brain (`..`), đuôi lạ, quá 1MB | Từ chối trước khi ghi |
| G14. Engine tự ghi native vào đích (mô phỏng file đổi trên đĩa) mà không nộp | Không thành sản phẩm; đăng gặp `publish_conflict` như hôm nay |
| G15. Không có quyền, quyền hỏng JSON, `actions` lạ | Không có quyền tác động; `begin_action(work)` không giữ lượt |
| G16. Quay về `33a3c1aa` rồi nâng lại | Mục tiêu đã thu hồi vẫn dừng; không có lượt hay lần đăng trái quyền; sổ lượt và bản nộp giữ nguyên |
| G17. Một nhiệm vụ hợp lệ trong quyền đã cấp | Không hỏi lại, không gọi thêm model để kiểm quyền; nộp, tiếp nhận, đăng đúng một lần |
| G18. Nhiều mục tiêu chưa tới hạn, quyền không đổi | Không đọc file, không đánh thức model; đo event loop khi gọi nộp song song |
| G19. Revision mới | Quyền cũ `superseded`; bản nộp revision cũ không được tiếp nhận cho revision mới |
| G20. Lượt chat thường, lượt kênh ngoài, lượt workflow gọi công cụ nộp | `not_agent_turn` |
| G21. Mục tiêu lập trước 0.90.0 | Lần thức đầu suy quyền đúng đường tiêu chí, `source=migrated`; mục tiêu chờ gán không có quyền |
| G22. Bảng khả năng engine | Codex và engine API nộp được qua công cụ (engine giả mang khoá lượt). Grok và Antigravity bị từ chối, lý do engine không có khoá lượt. Việc nền giữ nguyên danh sách |

### 12.2 Chuyển sang A5 (A4 chỉ có hàm và schema)

| Ca (bản bổ sung, mục 9) | Lý do |
|---|---|
| Hai việc con tranh lượt cuối | Cần việc con, mà A4 không tạo việc con. Luật một nguồn giữ lượt đã có từ A3 |
| Đổi người nhận hay lượt trước khi callback hoàn tất | A4 đã phủ phần lượt cũ mang `generation` cũ (G6). Đổi người nhận là việc của A5 |
| Worker tự nộp review dưới danh tính reviewer | Chưa có vai reviewer |
| Hash, revision, tiêu chí đổi sau review | Review là A5. A4 đã phủ bản nộp của revision cũ (G19) |
| Approval đúng công cụ nhưng nội dung hay đích đã đổi; duyệt nội dung rồi xin gửi sang kênh khác | A4 không có quyền gửi kênh; `communicate` luôn tắt |

## 13. Quyết định mặc định cần review

| # | Quyết định | Lý do | Phương án khác |
|---|---|---|---|
| D1 | Quyền gốc suy từ mục tiêu chủ dự án đã giao (đường tiêu chí); không có màn hình cấp quyền riêng | Đúng yêu cầu "giao một lần"; không rộng hơn quyền mã 0.89.0 đang cho | Chủ dự án cấp phạm vi theo trợ lý (thư mục): rộng hơn, cần UI riêng |
| D2 | Đăng vẫn chỉ qua `_publish` của host; bản nộp không ghi đè file người dùng | Giữ CAS và guard đã kiểm | Cho bản nộp đăng thẳng: mất mốc so sánh |
| D3 | Giữ quan sát Write của Claude làm đường phụ; có cả hai thì bản nộp thắng | Không làm hỏng bàn giao Claude đang chạy | Bỏ hẳn quan sát Write: gọn hơn, nhưng đổi hành vi Claude đã nghiệm thu |
| D4 | Grok và Antigravity không nhận bàn giao chat trong A4 | Hub không biết lượt nào gọi | Thêm khoá lượt cho Grok nếu CLI nhận header: việc riêng, cần bằng chứng |
| D5 | Không mở việc nền cho Codex, Grok, Antigravity | Chưa chứng minh chạy không công cụ | Sandbox cô lập: ngoài phạm vi |
| D6 | Thu hồi quyền = `revoked` + tạm dừng mục tiêu, trong một giao dịch | Mã cũ cũng dừng khi quay về | Chỉ đổi quyền: mã cũ không biết, sẽ chạy tiếp |
| D7 | Mở rộng phạm vi chỉ qua revision mới | Không thêm đường xin quyền mới trong A4 | Nút "Cho phép thêm đường này" trên thẻ: để sau khi có số liệu |
| D8 | `communicate` luôn tắt trong A4 | A4 không có giao việc | Bật cho A5 qua quyền con |
| D9 | `read_paths` chỉ gồm file sản phẩm | Mục tiêu chưa có danh sách nguồn riêng; không mở đọc rộng hơn mã hiện tại | Thêm trường nguồn vào khung mục tiêu, chủ dự án thấy và chấp nhận lúc lập: để A5 hoặc sau |

## 14. Kế hoạch code (sau khi thiết kế đạt review)

1. **Kho** (`resonance_store.py`):
   - thêm các bảng ở mục 7.1;
   - thêm `grant_for`, `grant_derive` (suy từ revision), `grant_revoke`, `grant_regrant`;
   - thêm `submission_insert` (giao dịch kiểm quyền, trợ lý, revision, khoá) và `submission_mark`.
2. **Chính sách thuần** (`resonance_grants.py`, mới): `derive(goal) -> spec`, `narrow(parent, request)`, `allows(grant, action, path)`, `ENGINE_CAPS`.
3. **Hợp đồng** (`resonance.py`):
   - cổng quyền ở `begin_action(work)` (qua kho), `_publish`, `finish_handoff`;
   - dựng prompt theo `read_paths`;
   - `handoff_after_turn` ưu tiên bản nộp;
   - ghi bản nộp `background_text`;
   - đọc lại hash trước `os.replace`.
4. **Công cụ hub:** `javis_submit_deliverable` trong plugin hệ thống `javis-goal` (cùng chỗ với công cụ mục tiêu). Đọc khoá lượt như các công cụ khác; làm I/O ở luồng phụ.
5. **API:**
   - `GET /goals/{id}` thêm `grant`, `submissions`;
   - thêm lệnh `revoke_grant`;
   - `resume` cấp lại quyền.
6. **Giao diện:**
   - dòng quyền và nút Thu hồi quyền trên thẻ;
   - bảng khả năng engine ở trang Cộng sự;
   - khoá chữ trong `vi.json`, `en.json`.
7. **Test:**
   - `tests/python/test_resonance_a4_grants.py`: G1 tới G22, đồng hồ giả, engine giả mang khoá lượt;
   - `tests/python/test_resonance_a4_rollback.py`: quay về `33a3c1aa`;
   - `tests/js/test_resonance_a4_ui.js`.
8. **Tài liệu:**
   - hướng dẫn `docs/dev/resonance-a4-handoff.md`;
   - biên bản `docs/dev/resonance-a4-verification.md`;
   - lộ trình mục 7 và 8.

Pilot model thật của A4, nếu cần, sẽ xin duyệt riêng sau review mã như A3.

## 15. Ranh giới bằng chứng

- **17 ca hàm thuần của Paperclip** (bản bổ sung, mục 11) là bằng chứng về Paperclip, không phải bằng chứng Javis đã triển khai.
- **Mục 2 ("đã có"):** đọc từ mã tại `9716cecf`.
- **Mọi phần còn lại** của tài liệu này là đề xuất, chưa có mã hay test.
