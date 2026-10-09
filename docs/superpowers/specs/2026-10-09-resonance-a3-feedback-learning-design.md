# Resonance A3: vòng phản hồi và học có kiểm chứng

**Trạng thái:** bản thiết kế vòng 1, chờ review. Chưa có mã hành vi A3. Nhánh `claude/resonance-a3-feedback-learning`, đặt số 0.89.0.

- **Nền:** `main` tại `83bff6bc` (0.88.1). A1 đã phát hành 0.87.0 (`fdfec7c5`), A2 đã phát hành 0.88.0 (`c101d108`).
- **Lộ trình:** [agent scope roadmap](2026-10-08-resonance-agent-scope-roadmap.md), mục 6.
- **Hồ sơ #597:** phần tài liệu của PR #597 (biên bản phát hành A1/A2) đã gộp vào nhánh này, bỏ VERSION và CHANGELOG riêng của #597.
- Không gọi model để làm thiết kế này.

## 1. Mục tiêu và ngoài phạm vi

**Mục tiêu:** biến phản hồi có nguồn thành thay đổi nhỏ được kiểm chứng, theo vòng:

> ghi phản hồi có nguồn → đề xuất thay đổi nhỏ → thử trong hạn mức → so với cách cũ → áp dụng trong phạm vi đã kiểm, hoặc giữ nguyên → tiếp tục quan sát.

A3 có hai làn học tách riêng, vì hai loại thay đổi có thước đo khác nhau:

| Làn | Đổi cái gì | Tín hiệu mở đề xuất | Cách so với cách cũ | Ai quyết áp dụng | Lượt model |
|---|---|---|---|---|---|
| **P (trình bày)** | Cách host viết và báo tin của trợ lý: báo đầy đủ hay gọn, có rung chuông hay không | Reaction trên tin báo của trợ lý | Xem trước bản cũ và bản mới của CÙNG một tin, do host dựng bằng mẫu cố định | Người dùng bấm Áp dụng | 0, mãi mãi |
| **M (cách làm)** | Cách làm M5 (`METHODS`) của một mục tiêu, trong đúng revision | Bế tắc khách quan: tiêu chí host kiểm không tiến thêm (A2) | Phép thử M5 `compare_methods`, host chấm cả hai bên bằng cùng thước đo | Host, chỉ khi phép thử ra `eligible` | Trong phần khám phá của hạn mức mục tiêu đã có |

**Giữ nguyên:**
- Phản hồi M4 (Đúng ý / Hiểu chưa đúng, Đạt yêu cầu / Cần chỉnh) giữ nguyên nghĩa và đường ghi. A3 chỉ thêm nguồn tin nhắn vào dữ liệu ghi kèm.
- M5 giữ nguyên: `METHODS` khai báo sẵn, phép thử giữ chỗ hạn mức trước khi gọi, cổng kiểm trước mỗi lượt và trong giao dịch áp dụng, phạm vi goal + revision, `revert_method`.
- A2 giữ nguyên: lý do thức, lớp, vòng đời, `decide`. A3 thêm đúng một mã lý do (`method_trial`) và một lớp (mục 6.3).
- Bảng cũ không đổi cột. A3 chỉ thêm bảng mới (luật của A1).

**Ngoài phạm vi:**
- Reaction trên lời chat thường, trên câu trả lời của trợ lý trong phiên agent, và trên kênh ngoài (Telegram, Zalo, Lark). Chỉ tin báo do host ghi mới nhận reaction (mục 3.2).
- Chuyển cách làm đã học sang mục tiêu khác hay revision khác ("chuyển giao bài học"). Cần bộ tình huống giữ riêng nhiều mục tiêu; để sau.
- Dùng đầu ra của phép thử làm sản phẩm của mục tiêu (mục 14, D5).
- Tự sinh cách làm mới hay mẫu trình bày mới. Mọi lựa chọn là mục khai báo sẵn trong code.
- Bản tin gộp theo ngày (digest). "Ít làm phiền" trong A3 chỉ là tắt chuông cho loại tin không bắt buộc.
- Cơ chế `JAVIS_LESSON` hiện có (trợ lý tự ghi bài học vào `memory/agents/<slug>/MEMORY.md`) không đổi và không dùng cho A3: bài học ở đó không có phạm vi, bằng chứng hay đường thu hồi theo luật A3.

## 2. Hiện trạng và khoảng trống (mã tại `83bff6bc`)

| Đã có | Chỗ trong mã | Khoảng trống A3 lấp |
|---|---|---|
| Phản hồi M4 ghi vào `goal_events` (`feedback.*`), chỉ owner, CAS revision, khoá chống trùng theo lần bấm | `resonance_store.record_feedback`, `resonance.apply_feedback`, `POST /goals/{id}/feedback` | Chưa ghi tin nhắn nguồn; chưa có reaction |
| "Cần chỉnh" kèm ghi chú đi vào lượt việc kế tiếp qua lý do `not_met` | `resonance._human_verdict`, `_work_prompt` | Đủ cho sửa trong revision; A3 không đổi |
| Phép thử M5: giữ chỗ hạn mức, chạy hai bên, chấm bằng `artifact_contract`, áp dụng có CAS, quay lại | `compare_methods`, `begin_experiment`, `finish_experiment`, `_method_change_blocked`, `revert_method` | **Không có đường nào gọi `compare_methods` ngoài test.** Bộ tình huống phải do người gọi đưa vào |
| Bế tắc khách quan: hai lượt liên tiếp không vượt mốc thì dừng thử và chờ | `resonance_heartbeat.auto_allowed`, nhánh `goal.stalled` trong `_settle` | Chưa có bước "thử cách khác" |
| Tin báo của mục tiêu vào khung chat kèm biên nhận `report_receipts` cùng giao dịch | `drain_outbox`, `main._resonance_notify`, `sessions.report_receipts` | Chưa có nút phản hồi trên tin báo |
| `_notify_owner(quiet=True)`: vẫn vào khung chat và hộp thư, chỉ không rung chuông, không đẩy thông báo trình duyệt | `main._notify_owner` | Dùng làm giá trị "ít làm phiền" của làn P |
| `advance` bỏ qua `kind="reaction"` | `_advance_prepare` | Giữ nguyên: reaction không bao giờ đi qua `advance` |

**Hạn mức thực tế:** mục tiêu mặc định có 6 lượt (`GOAL_DEFAULT_CALLS`), phần khám phá 50% là 3 lượt, lượt dự phòng A2 là 1. Bế tắc theo `heartbeat.v1` xảy ra sớm nhất sau 3 lượt việc thành công. Khi đó còn 3 lượt: đủ đúng một phép thử một tình huống (2 lượt) và vẫn chừa 1 lượt dự phòng. Phép thử M5 có thêm tình huống giữ riêng (4 lượt) không bao giờ vừa hạn mức mặc định. Đây là lý do của quyết định D4 (mục 14).

## 3. Bốn loại tín hiệu

### 3.1 Nghĩa và nguồn chuẩn

| Tín hiệu | Nguồn chuẩn | Dùng cho | Không bao giờ suy ra |
|---|---|---|---|
| **Reaction** trên tin báo của trợ lý (👍; 👎 kèm lý do Dài quá / Báo nhiều quá / Khó hiểu) | Bảng mới `reactions` (giá trị hiện tại) và `reaction_log` (lịch sử) | Làn P: đề xuất cách báo | Mục tiêu đạt hay thất bại, đổi cách làm, quyền, hạn mức, lịch thức |
| **Đúng ý / Hiểu chưa đúng** | `goal_events` kind `feedback.goal_fit_*` (M4, không đổi) | Cách hiểu của đúng revision. "Hiểu chưa đúng" chặn mọi phép thử và áp dụng làn M (đã có trong `_method_change_blocked`) | Sản phẩm đạt |
| **Đạt yêu cầu / Cần chỉnh** | `goal_events` kind `feedback.outcome_*` (M4, không đổi), gắn `criterion_id` và `artifact_ref` | Tiêu chí `human_confirmation` của đúng bản sản phẩm; "Cần chỉnh" mở lượt sửa trong revision (M4/A2) | Vượt guard, thay kết quả kiểm khách quan, mở phép thử làn M (mục 14, D6) |
| **Bằng chứng khách quan và chi phí** | `assessments`, `evidence_links`, `heartbeat_state` (A2), `experiments` (M5), `calls_used` | Làn M: phát hiện bế tắc, chấm phép thử | Quy công cho hành động khi chưa có phép so |

Không có điểm tổng. Mỗi tín hiệu chỉ đi vào đúng ô "dùng cho" của nó, và mỗi đường đọc trong mã chỉ đọc nguồn chuẩn của nó.

### 3.2 Dữ liệu bắt buộc của mỗi tín hiệu

Mỗi tín hiệu A3 ghi: tin nhắn nguồn, người phản hồi đã được xác thực, trợ lý, brain, và mục tiêu, revision, sản phẩm khi liên quan.

| Trường | Reaction | Phản hồi M4 (thêm ở A3) |
|---|---|---|
| Tin nguồn | `session_id`, `message_id`, `report_key` lấy từ `report_receipts` | `source_ref` = `msg:<phiên>:<id>` của tin chứa thẻ, nếu dashboard gửi; kiểm như reaction. Thiếu thì ghi rỗng (dashboard cũ), M4 vẫn chạy như trước |
| Người phản hồi | `Principal.by` của owner brain | như M4 |
| Trợ lý | `agent_key` và `agent_config_version` tại lúc ghi, đọc từ `goal_agents` và `resonance_agents` | như reaction |
| Brain | `brain_id` của principal; phiên phải thuộc brain này | như M4 |
| Mục tiêu, revision | `goal_id` từ biên nhận; `revision` từ payload outbox của tin đó (revision lúc báo, không phải revision hiện tại) | như M4 (CAS revision hiện tại) |
| Sản phẩm | `content_sha` của nội dung tin lúc bấm | `artifact_ref` (M4, đã có) |

**Chỉ tin báo do host ghi mới nhận reaction.** Tin hợp lệ khi có dòng `report_receipts` trỏ tới đúng `message_id`, `role` là `assistant`, khoá dạng `outbox:<id>`, và mục tiêu thuộc một trợ lý (`goal_agents`). Lời chat thường, câu trả lời của model, hay một khối `JAVIS_RESONANCE` do model tự viết đều không có biên nhận, nên bị từ chối (400). Đây là cách A3 giữ chat thường ngoài vòng học: không có nguồn hợp lệ thì không có tín hiệu.

### 3.3 Thay thế, thu hồi, gửi lại, khởi động lại

- **Một người, một tin, một giá trị hiện tại.** Khoá duy nhất `(brain_id, session_id, message_id, responder)`. Bấm lại hay đổi ý ghi đè giá trị hiện tại và tăng `seq`; bấm đúng giá trị đang có lần nữa là thu hồi (`value='none'`). Lịch sử đầy đủ nằm ở `reaction_log`.
- **Gửi lại idempotent.** Mỗi lần bấm mang `nonce` (như M4). `reaction_log` có khoá duy nhất `(reaction_id, nonce)`: gửi lại cùng request không đổi gì và trả lại trạng thái hiện tại.
- **Không nhân điểm.** Bộ học chỉ đếm số TIN khác nhau có giá trị hiện tại khớp điều kiện (mục 5.3). Bấm mười lần trên một tin vẫn là một tin. Không có cột điểm cộng dồn nào.
- **Khởi động lại** không đổi gì: mọi trạng thái nằm trong SQLite; bộ học là hàm thuần của trạng thái đó; đề xuất có khoá duy nhất cho trạng thái mở (mục 7), nên chạy lại không sinh đề xuất trùng.

### 3.4 Phản hồi muộn, nguồn bị sửa hay bị xoá

| Trường hợp | Xử lý |
|---|---|
| Reaction trên tin báo của revision cũ | Ghi, gắn revision của tin. Làn P không phụ thuộc revision nên vẫn được tính. Không ảnh hưởng gì tới mục tiêu |
| Reaction trên tin của mục tiêu đã xong hay đã huỷ | Ghi bình thường, vẫn tính cho làn P của trợ lý đó |
| Reaction khi trợ lý đang tắt Cộng hưởng | Ghi (thụ động, không tác động). Bộ học không tạo đề xuất cho trợ lý đang tắt; đề xuất được xét lại ở lần ghi reaction tiếp theo sau khi bật |
| Trợ lý đã bị xoá (`status` khác `active`/`missing`) | Từ chối 409; không có chủ thể nhận bài học |
| Tin bị xoá (biên nhận mất theo `ON DELETE CASCADE`) | Reaction thành **mồ côi**: bộ học không đếm. Đề xuất đang mở mất đủ số tin thì tự hết hạn. Bài học đã áp dụng giữ nguyên (người dùng đã quyết), danh sách hiện "nguồn đã xoá" |
| Nội dung tin đổi so với `content_sha` lúc bấm | Như tin bị xoá: mồ côi, không đếm |
| Phản hồi M4 sai revision hay sai bản sản phẩm | Giữ nguyên M4: 409, không ghi |
| Phản hồi M4 cho mục tiêu không còn active | Giữ nguyên M4: 400, không ghi |

Kiểm mồ côi chạy lười (lúc bộ học đọc), chỉ trên các tin trong cửa sổ 30 ngày của một trợ lý, bằng một truy vấn theo khoá chính của `report_receipts` và `messages`.

### 3.5 Im lặng

Không có reaction nghĩa là chưa biết. Bộ học không đọc sự vắng mặt: không tính tỷ lệ, không phạt, không coi đề xuất hết hạn là "người dùng đồng ý". Đề xuất hết hạn thì giữ cách cũ.

## 4. Luật bất biến của A3

1. **Reaction không mở lượt model và không đổi lịch.** Đường ghi reaction không gọi `advance`, không ghi `wake_reasons`, không đụng `wakeups`, không dựng engine. Bộ học chạy bằng code ngay trong giao dịch ghi reaction.
2. **Phản hồi không làm mục tiêu đạt.** Chỉ `evaluate_artifact` theo tiêu chí và bằng chứng (M3) và xác nhận M4 đúng tiêu chí, đúng bản sản phẩm mới đổi được kết quả tiêu chí. Không đường nào của A3 ghi `assessments` hay đổi `status` mục tiêu.
3. **Học không mở chốt và không cấp quyền.** Không đường nào của A3 ghi file trợ lý, `resonance_agents`, `config_version`, công tắc brain, guard, pause, hạn mức (`budget_calls`), hạn chót hay tiêu chí.
4. **Ít làm phiền không giấu cảnh báo bắt buộc.** Làn P chỉ đổi được tin thuộc danh sách tuỳ chọn khai báo trong code (mục 5.1). Tin bắt buộc luôn đầy đủ và luôn rung chuông. Làn P không đụng lịch kiểm guard, lịch hạn chót hay lịch xem lại.
5. **Áp dụng chỉ trong phạm vi đã kiểm.** Làn M: đúng goal + revision của phép thử, qua `effective_method` của M5. Làn P: đúng trợ lý trong đúng brain.
6. **Ứng viên thua hay chưa rõ thì giữ cách cũ.** Đề xuất hết hạn, bị bỏ qua, phép thử `rejected` hay `inconclusive` đều không đổi gì.
7. **Thu hồi ngừng áp dụng ngay.** Làn P: lần dựng tin kế tiếp đã đọc trạng thái mới. Làn M: `revert_method` trong cùng giao dịch với việc đánh dấu bài học.

## 5. Làn P: cách trình bày tin báo

### 5.1 Mục khai báo sẵn

Hai khoá, mỗi khoá một tập giá trị cố định trong code (`PRESENTATION`, cạnh `METHODS`):

| Khoá | Mặc định | Giá trị khác | Áp cho loại tin |
|---|---|---|---|
| `notice_detail` | `full` (câu hiện tại của `notice_text`) | `brief`: một câu ngắn theo mẫu cố định, giữ tên mục tiêu và liên kết sản phẩm; thẻ mục tiêu vẫn đi kèm | `goal.succeeded`, `goal.maintained` |
| `notice_ping` | `ping` | `quiet`: tin vẫn vào khung chat và hộp thư, chỉ không rung chuông và không đẩy thông báo trình duyệt (`_notify_owner(quiet=True)`) | `goal.maintained` |

**Tin bắt buộc** (luôn `full`, luôn `ping`, làn P không đụng tới): `goal.guard`, `goal.monitoring_lost`, `goal.deadline_passed`, `goal.publish_conflict`, `goal.failed`, `goal.blocked`, `goal.waiting_human`, `goal.stalled`, `goal.discovery_done`, và tin mới `goal.method_changed` (mục 6.6). Danh sách này là hằng trong code; test khoá nó.

Lý do danh sách tuỳ chọn hẹp: chỉ hai loại tin trên không đòi người dùng làm gì. Mọi tin còn lại là cảnh báo, câu hỏi chờ người dùng, hay báo thay đổi hành vi.

### 5.2 Vòng đời bài học làn P

```
proposed ──(owner Áp dụng)──▶ active ──(owner Thu hồi)──▶ revoked
   │                            └──(owner áp dụng giá trị khác cùng khoá)──▶ superseded
   ├──(owner Bỏ qua)──▶ dismissed
   └──(quá hạn 14 ngày, hay mất đủ số tin vì mồ côi)──▶ expired
```

- **So với cách cũ:** đề xuất kèm bản xem trước dựng bằng code từ chính tin đã nhận phản hồi: câu cũ và câu mới cạnh nhau, cùng ghi chú "tin bắt buộc không đổi". Không gọi model.
- **Áp dụng:** chỉ owner, CAS theo `status='proposed'` và `updated_at` mà thẻ đang thấy. Một khoá chỉ có một bài học `active` cho mỗi trợ lý; áp dụng giá trị khác thì bài học cũ thành `superseded` trong cùng giao dịch.
- **Bài học có hiệu lực** của một trợ lý = bài học `active` mới nhất mỗi khoá. Không có thì dùng mặc định.

### 5.3 Bộ học làn P (`learning.v1`, hàm thuần)

Đầu vào: các reaction không mồ côi của một trợ lý trong 30 ngày, giá trị hiện tại; các bài học làn P hiện có. Đầu ra: không hay một đề xuất.

| Đề xuất | Điều kiện |
|---|---|
| `notice_detail: full → brief` | Ít nhất **2 tin khác nhau** thuộc loại áp được, có giá trị hiện tại `down` + `too_long`; khoá đang ở `full`; không có đề xuất mở hay bài học `dismissed` trong 14 ngày cho cùng khoá và giá trị |
| `notice_ping: ping → quiet` | Ít nhất 2 tin `goal.maintained` khác nhau có `down` + `too_often`; cùng các điều kiện còn lại |
| Đề xuất quay lại (`brief → full`) | Ít nhất 1 tin đã được dựng theo `brief` có `down` + `unclear` |

`up` và `down` không lý do được ghi và hiện ở thống kê, nhưng không mở đề xuất: không có lý do thì không biết nên đổi gì. Bộ học không bao giờ tự áp dụng. Đề xuất quay lại cũng chỉ là đề xuất; nút Thu hồi luôn có sẵn.

### 5.4 Áp vào đường báo

`drain_outbox` đọc bài học có hiệu lực của trợ lý sở hữu mục tiêu ngay trước khi dựng câu và gửi tin (một truy vấn theo chỉ mục, mục 11), rồi truyền `presentation` vào `notice_text` và cờ `quiet` vào `notify`. Payload outbox và biên nhận ghi thêm `presentation` đã dùng, để đề xuất quay lại biết tin nào là `brief`. Tin bắt buộc bỏ qua bước này.

## 6. Làn M: cách làm khi bế tắc khách quan

### 6.1 Khi nào có đề xuất

Đề xuất làn M được tạo **trong cùng giao dịch** với lúc A2 ghi `waiting/stalled` (nhánh bế tắc của `_settle`), khi đủ mọi điều kiện:

1. Lý do bế tắc là `stalled` (hai lượt liên tiếp không vượt mốc theo tiêu chí host kiểm), không phải `reserve`.
2. Revision hiện tại có ít nhất một tiêu chí `artifact_contract` có `min_chars` hay `must_contain`, tức host tự chấm được.
3. Có một ứng viên theo bảng ánh xạ `learning.v1`: cách làm có hiệu lực là `work.v1` thì ứng viên là `work.checklist.v1`. Các cách làm khác chưa có ứng viên (không đề xuất).
4. Chưa có phép thử nào của đúng revision với đúng cặp baseline, ứng viên (bảng `experiments`).
5. Trợ lý bật, mục tiêu active, không pause, không chốt guard, cách hiểu không bị "Hiểu chưa đúng".

Đủ điều kiện thì ghi bài học `trial_pending` và một lý do thức sự kiện `method_trial` (`source_ref = lesson:<id>`, `due_at` = bây giờ). Thiếu điều kiện 2 thì ghi bài học `skipped` với lý do `untestable` để người dùng thấy vì sao không thử; các điều kiện khác thiếu thì không ghi gì.

"Cần chỉnh" (tiêu chí người dùng chấm) không mở đề xuất làn M: host không chấm được phép thử cho tiêu chí đó, nên không có bằng chứng để so. Ghi chú "Cần chỉnh" vẫn đi vào lượt sửa trong revision như M4/A2 (mục 14, D6).

### 6.2 Bộ tình huống do host dựng

Không ai phải nhập tình huống. Host dựng bộ một tình huống từ chính revision:

- `id = "rev<revision>"`, `split = "tuning"`;
- `input` = lời người dùng của revision (bản ghi ý định, như lượt việc thường);
- `expect` = `min_chars`, `must_contain` của tiêu chí `artifact_contract` đầu tiên có tham số; mọi tiêu chí `artifact_contract` khác vẫn được chấm qua `rubric` như M5.

Bộ này không có tình huống giữ riêng. M5 hiện đòi ít nhất một tình huống `holdout`. A3 nới luật đó **chỉ** cho bộ do host dựng (cờ `origin="host_revision"` truyền vào `compare_methods`), với điều kiện phạm vi áp dụng là goal + revision của chính tình huống đó, đúng phạm vi M5 vốn cho phép. Bộ do người gọi đưa vào vẫn giữ luật cũ. Lý do và phương án khác ở mục 14, D4.

### 6.3 Lý do thức và quyết định (`heartbeat.v2`)

A3 thêm vào chính sách A2 (tăng `POLICY_VERSION` thành `heartbeat.v2`; `wake_log` cũ giữ phiên bản của nó):

- Mã `method_trial`, lớp mới `TRIAL`, nghĩa vụ `check` (một hẹn mới thay hẹn cũ cùng nghĩa vụ không áp dụng: đây là lý do sự kiện).
- Thứ tự `decide`: đạt hay chỉ chờ người dùng → `NEW` → `START` → **`TRIAL`** → `AUTO`. Tin mới từ người dùng luôn thắng phép thử.
- `trial_allowed(cost, left, explore_left)`: được khi `cost <= explore_left` và `left - cost >= AUTO_RESERVE_CALLS`. Không được thì lý do được chốt (`settled_by = trial_budget`), bài học thành `skipped` lý do `budget`, không gọi model. A3 không bao giờ xin hay tự nâng hạn mức.
- Mục tiêu ở trạng thái chặn (pause, guard, "Hiểu chưa đúng", trợ lý tắt, chờ bàn giao) thì lý do `method_trial` bị gác như mọi lý do khác của A2 (chỉ `UNPARK_CODES` được tính), không chạy.
- Có tin mới từ người dùng (`NEW`) trước khi phép thử chạy: lượt sửa chạy bằng cách làm cũ; chuỗi A2 đặt lại nên điều kiện bế tắc không còn; lý do `method_trial` được chốt `superseded`, bài học thành `skipped` lý do `new_feedback`.

### 6.4 Chạy phép thử

Quyết định `trial` đi qua đúng khung lần thức A2: pha chuẩn bị trong luồng phụ giữ khoá lượt, pha model trên event loop, `_finish_wake` nhả khoá và ghi `wake_log` (`decision='trial'`, `model_calls` = số lượt đã tính). Phần thân của `compare_methods` được tách thành hàm nhận khoá lượt có sẵn; `compare_methods` công khai vẫn tự giành khoá như cũ.

Mọi chốt của M5 giữ nguyên: giữ chỗ toàn bộ lượt trong phần khám phá trước khi gọi, ghim mã và version trợ lý, `_trial_gate` và `agent_gate` trước mỗi lượt và ngay trước khi kết luận, `_method_change_blocked` trong giao dịch áp dụng, hoàn lại lượt chưa bắt đầu. A3 thêm một điều kiện vào cổng mỗi lượt: bài học vẫn `trialing` (người dùng bấm Bỏ qua giữa chừng thì dừng, hoàn phần chưa chạy).

### 6.5 Kết quả

| Verdict M5 | Bài học | Cách làm | Tin báo |
|---|---|---|---|
| `eligible` và áp dụng được | `active`, phạm vi goal + revision, ghi `experiment_id` | Đổi trong cùng giao dịch `finish_experiment` (M5) | `goal.method_changed` (bắt buộc) |
| `eligible` nhưng áp dụng bị chặn | `inconclusive` (M5 đã đổi verdict) | Giữ | Không |
| `rejected` | `rejected` | Giữ | Không; thẻ hiện dòng "đã thử, cách cũ giữ nguyên" |
| `inconclusive` | `unknown` | Giữ | Không; thẻ hiện lý do |

Sau khi áp dụng, mục tiêu vẫn ở `waiting/stalled`: thường chỉ còn đúng lượt dự phòng nên A2 không tự thử lại. Lượt việc kế tiếp (do góp ý, sửa cách hiểu, hay lịch xem lại của mục tiêu duy trì) dùng cách làm mới. Đầu ra của phép thử không được đăng làm sản phẩm (D5).

### 6.6 Tin `goal.method_changed`

Bắt buộc, luôn đầy đủ: nói cách làm nào đã thử, đạt tiêu chí nào trên bản thử, chỉ áp dụng cho cách hiểu hiện tại, đã tốn bao nhiêu lượt, và có nút Quay lại cách cũ trên thẻ. Tin này không đổi lịch thức.

### 6.7 Thu hồi và hết phạm vi

- **Thu hồi:** owner bấm "Quay lại cách cũ" trên thẻ hay trong danh sách bài học. Một giao dịch: `revert_method` (M5, không đổi) và bài học thành `revoked`. Bấm lại khi đã thu hồi thì trả trạng thái hiện tại, không lỗi.
- **Hết phạm vi:** revision đổi thì `effective_method` của M5 tự rơi về mặc định. Bài học được ghi `out_of_scope` trong giao dịch tạo revision mới (`revise`), không chờ đọc lười.

## 7. Kho

### 7.1 Bảng mới

Chỉ thêm bảng; không thêm cột vào bảng cũ (test `PRE_A1` vẫn khoá).

**`reactions`**: giá trị hiện tại của một người trên một tin.
- Cột: `id`, `brain_id`, `agent_key`, `agent_config_version`, `goal_id`, `revision` (revision của tin), `session_id`, `message_id`, `report_key`, `notice_kind`, `presentation` (cách dựng tin lúc gửi), `content_sha`, `responder`, `value` (`up`/`down`/`none`), `reason` (rỗng/`too_long`/`too_often`/`unclear`), `seq`, `created_at`, `updated_at`.
- Khoá duy nhất `(brain_id, session_id, message_id, responder)`; chỉ mục `(brain_id, agent_key, updated_at)`.

**`reaction_log`**: mọi lần bấm. Cột `id`, `reaction_id`, `value`, `reason`, `nonce`, `created_at`. Khoá duy nhất `(reaction_id, nonce)`.

**`lessons`**: đề xuất và bài học của cả hai làn.
- Cột: `id`, `brain_id`, `agent_key`, `lane` (`presentation`/`method`), `key` (`notice_detail`, `notice_ping`, `method`), `from_value`, `to_value`, `scope` (`agent`/`goal_revision`), `goal_id` (rỗng với làn P), `revision` (0 với làn P), `status`, `status_reason`, `policy_version`, `evidence_json`, `experiment_id`, `expires_at`, `decided_by`, `decided_at`, `created_at`, `updated_at`.
- Chỉ mục duy nhất từng phần `(brain_id, agent_key, lane, key, goal_id, revision) WHERE status IN ('proposed','trial_pending','trialing','active')`: mỗi khoá, mỗi phạm vi chỉ có một bài học đang mở. Đây là chốt chống trùng khi chạy lại hay khởi động lại.

**`lesson_events`**: nhật ký thay đổi trạng thái. Cột `id`, `lesson_id`, `brain_id`, `kind`, `by`, `payload_json`, `created_at`.

`evidence_json` là ảnh chụp lúc tạo đề xuất: danh sách `reaction:<id>@<seq>` kèm `content_sha` (làn P), hay `assessment:<id>`, `heartbeat_state` và lý do bế tắc (làn M). Ảnh chụp không bị sửa về sau; trạng thái mồ côi được tính lúc đọc.

### 7.2 Nguồn chuẩn

| Câu hỏi | Nguồn chuẩn |
|---|---|
| Reaction hiện tại của một người trên một tin | `reactions` |
| Lịch sử bấm | `reaction_log` |
| Cách trình bày có hiệu lực của trợ lý | `lessons` làn P `active` |
| Cách làm có hiệu lực của mục tiêu | Cột M5 của `goals` qua `effective_method` (không đổi). `lessons` làn M chỉ là hồ sơ, luôn đối chiếu lại: bài học `active` mà cột M5 không còn khớp thì hiện trạng thái suy ra từ M5 |
| Phản hồi M4 | `goal_events` (không đổi) |

### 7.3 Di chuyển và quay về

- Lần đầu bản 0.89 mở một kho chưa có bảng A3: sao lưu `resonance.sqlite3` thành `.pre-a3.bak` (cùng hàm `_backup_before` của A2), rồi tạo bảng. Không di chuyển dữ liệu cũ nào.
- **Quay về 0.88.x:** bản cũ bỏ qua bảng lạ. Làn P mất hiệu lực (tin trở lại đầy đủ, rung chuông). Cách làm đã áp dụng ở làn M vẫn nằm ở cột M5 mà 0.88 đã hiểu, vẫn đúng phạm vi goal + revision. Bản cũ không biết lý do `method_trial`: mã lạ thuộc lớp `CHECK` của `heartbeat.v1`, chỉ kiểm, không gọi model; test quay về khoá điều này.
- **Nâng lại 0.89 sau khi quay về:** bảng A3 còn nguyên; bài học làn M có thể lệch cột M5 (người dùng quay lại cách cũ bằng bản cũ) và được hiện theo M5 như mục 7.2.

## 8. Chính sách `learning.v1`

Hằng có phiên bản, không phải ô cài đặt. Đổi mặc định thì tăng phiên bản; mỗi bài học ghi `policy_version`.

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `P_WINDOW_S` | 30 ngày | Reaction cũ hơn không mở đề xuất |
| `P_MIN_MESSAGES` | 2 | Số tin khác nhau tối thiểu cho đề xuất rút gọn hay tắt chuông |
| `P_REVERT_MIN_MESSAGES` | 1 | Số tin `brief` bị "Khó hiểu" để đề xuất quay lại |
| `P_PROPOSAL_TTL_S` | 14 ngày | Đề xuất không ai quyết thì hết hạn, giữ cách cũ |
| `P_DISMISS_COOLDOWN_S` | 14 ngày | Bỏ qua thì không đề xuất lại cùng thay đổi trong khoảng này |
| `M_CANDIDATES` | `work.v1 → work.checklist.v1` | Ứng viên duy nhất khi bế tắc |
| `M_TRIALS_PER_REVISION` | 1 mỗi cặp baseline, ứng viên | Không thử lại cùng cặp trong cùng revision |
| Chi phí phép thử | 2 lượt (một tình huống, hai bên) | Phải nằm trong phần khám phá còn lại và chừa lượt dự phòng |

## 9. Chốt dừng và giữa lượt

| Sự kiện | Làn P | Làn M |
|---|---|---|
| Owner tạm dừng mục tiêu | Không ảnh hưởng | Lý do bị gác; phép thử đang chạy dừng ở cổng lượt kế tiếp, kết luận `inconclusive/stopped`, hoàn phần chưa chạy (M5) |
| Tắt trợ lý | Không tạo đề xuất mới; bài học `active` vẫn áp (owner đã quyết; tin bắt buộc vẫn đầy đủ) | Như pause; ngoài ra version trợ lý đổi nên áp dụng bị chặn trong giao dịch (A1) |
| Guard nhảy | Không ảnh hưởng | Chặn ở cổng lượt và trong giao dịch áp dụng (M5) |
| Huỷ mục tiêu | Không ảnh hưởng | Lý do bị xoá cùng mục tiêu (A2); phép thử dừng ở cổng |
| Hết hạn mức | Không ảnh hưởng | `trial_allowed` sai: không chạy, bài học `skipped/budget` |
| Owner bấm Bỏ qua bài học đang thử | Không áp dụng (làn P không có thử) | Dừng ở cổng lượt kế tiếp; lượt đã bắt đầu vẫn tính, không hứa hoàn |
| Owner thu hồi | Lần dựng tin kế tiếp dùng mặc định | `revert_method` cùng giao dịch |
| Trần chung `JAVIS_RESONANCE_CALL_CEILING` | Không liên quan | Kiểm trong giao dịch giữ chỗ (M5, không đổi) |

## 10. API

Mọi route mới đi qua `_ctx(brain)` và principal owner như M4; agent không gọi được.

| Route | Thân | Trả | Lỗi |
|---|---|---|---|
| `POST /resonance/reactions?brain=` | `message_ref` (`msg:<phiên>:<id>`), `value` (`up`/`down`/`none`), `reason` (với `down`), `nonce` | `reaction` (giá trị hiện tại, `seq`), `proposal` (đề xuất vừa tạo, nếu có) | 400 tin không phải tin báo của trợ lý; 404 phiên hay tin không thuộc brain; 409 trợ lý đã xoá hay nội dung tin đã đổi |
| `GET /resonance/lessons?brain=&agent_key=` | | Bài học của trợ lý theo làn và trạng thái, kèm bằng chứng (đã đánh dấu mồ côi), bản xem trước làn P, liên kết phép thử làn M; thống kê reaction 30 ngày | 404 |
| `POST /resonance/lessons/{id}/decision?brain=` | `action` (`apply` / `dismiss` / `revoke`), `expected_status`, `expected_updated_at` | Bài học sau quyết định | 409 trạng thái đã đổi; 400 hành động không hợp với làn hay trạng thái (`apply` chỉ cho làn P `proposed`; `dismiss` cho `proposed`/`trial_pending`/`trialing`; `revoke` cho `active`) |
| `GET /goals/{id}` (đã có) | | Thêm khối `learning`: bài học làn M của revision hiện tại (trạng thái, lý do, phép thử, nút quay lại) | |

`POST /goals/{id}/feedback` nhận thêm `source_ref` không bắt buộc (mục 3.2). Không có route nào cho model tạo, áp dụng hay thu hồi bài học; tool `javis_goal` không đổi.

## 11. Giao diện

- **Tin báo trong khung chat** (`chat-resonance.js`): dưới thẻ của tin có biên nhận, một hàng nhỏ 👍 / 👎. Bấm 👎 mở ba chip lý do. Hiện giá trị hiện tại; bấm lại đúng giá trị là thu hồi. Không hiện trên tin thường. Sau khi bấm, nếu vừa có đề xuất thì hiện một dòng "Javis có một gợi ý cách báo, xem ở trang trợ lý".
- **Trang trợ lý** (`resonance-agent.js`, phần Cộng hưởng của A1): mục **Bài học** một cột (luật trang cài đặt xếp một cột):
  - Đề xuất làn P: câu cũ và câu mới cạnh nhau (xếp dọc trên điện thoại), số tin làm căn cứ, nút Áp dụng / Bỏ qua.
  - Bài học đang áp dụng: phạm vi, nguồn, ngày, nút Thu hồi.
  - Lịch sử ngắn: đã bỏ qua, hết hạn, đã thử mà thua, kèm lý do.
- **Thẻ mục tiêu**: dòng cách làm (đã có) thêm "đang thử cách X", "cách X đã học cho cách hiểu này · Quay lại cách cũ", hay "đã thử X, giữ cách cũ: <lý do>". Khi phép thử bị bỏ qua vì không chấm được hay thiếu hạn mức, hiện đúng lý do.
- Chuỗi mới qua `vi.json` và `en.json`, khoá `tw()` là chuỗi nguyên văn (bảng tra như `WAKE_KEYS` của A2).

## 12. Hiệu năng

- Ghi reaction: một giao dịch SQLite gồm kiểm biên nhận (khoá chính), upsert, ghi log, chạy bộ học trên reaction của một trợ lý trong 30 ngày (chỉ mục `(brain_id, agent_key, updated_at)`). Chạy trong luồng phụ như A2 mục 11. Không đọc file brain.
- `drain_outbox`: thêm một truy vấn bài học `active` của một trợ lý mỗi tin, theo chỉ mục `lessons_open`.
- `GET /goals/{id}`: thêm một truy vấn bài học làn M theo goal + revision.
- Không có vòng quét nền mới. Hết hạn đề xuất được tính lúc đọc và ghi bù lúc có reaction mới hay khi mở danh sách bài học.

## 13. Ma trận nghiệm thu (đồng hồ giả, engine giả, không model thật)

Mọi ca chạy trong khung thế giới giả của A2 (`World`, `reopen()` để khởi động lại thật). Cột "Kiểm" ghi điều test khẳng định.

### 13.1 Bộ tối thiểu theo GOAL

| ID | Kịch bản | Kiểm |
|---|---|---|
| G1 | Reaction không làm mục tiêu đạt: mục tiêu có tiêu chí host chưa đạt, owner bấm 👍 trên mọi tin báo, chạy tick | `status` vẫn active; không có `assessments` mới; tiêu chí vẫn `not_met`; engine giả 0 lượt |
| G2a | Sai người: principal `agent` gọi đường ghi reaction và quyết định bài học | `PermissionError` / 403; không có dòng nào |
| G2b | Sai brain: tin thuộc phiên của brain B, gọi bằng brain A | 404; không có dòng |
| G2c | Sai revision: phản hồi M4 với `expected_revision` cũ | 409; không ghi (khoá lại hành vi M4) |
| G2d | Sai hash: "Đạt yêu cầu" với `artifact_ref` cũ | 409; không ghi |
| G2e | Không phải tin báo: reaction trên câu trả lời chat thường, và trên tin có khối `JAVIS_RESONANCE` do model tự viết (không biên nhận) | 400; bộ học không thấy |
| G3a | Bấm lại: 10 lần `down/too_long` trên cùng một tin | Một dòng `reactions`, `seq` 10, 10 dòng log; bộ học đếm 1 tin; không đề xuất |
| G3b | Gửi lại cùng `nonce` | Không dòng log mới; trả cùng `seq` |
| G3c | Thu hồi rồi khởi động lại: 2 tin `too_long` tạo đề xuất; thu hồi một reaction; `reopen()`; bấm reaction khác | Không có đề xuất thứ hai (chỉ mục duy nhất); đề xuất cũ hết hạn khi chỉ còn 1 tin hợp lệ |
| G4a | Ứng viên thua: phép thử trả `rejected/regression` | `method_ref` không đổi; bài học `rejected`; không tin `method_changed` |
| G4b | Ứng viên chưa rõ: một bên `unknown` | `inconclusive`; cách làm giữ; bài học `unknown` |
| G4c | Đề xuất làn P hết hạn (đồng hồ giả qua 14 ngày) | Trạng thái `expired`; tin vẫn dựng `full` |
| G5a | Thu hồi làn P: bài học `brief` active, thu hồi, gửi tin `goal.succeeded` kế tiếp | Câu đầy đủ như mặc định; biên nhận ghi `presentation=full` |
| G5b | Thu hồi làn M | `effective_method` = cách cũ trong cùng giao dịch; bài học `revoked`; lượt việc kế tiếp dùng prompt không có phần thêm của ứng viên |
| G6a | Pause giữa phép thử: engine giả đặt pause sau lượt baseline | Bên ứng viên không chạy; `inconclusive/stopped`; hoàn 1 lượt |
| G6b | Tắt trợ lý giữa phép thử | Như G6a; áp dụng bị chặn kể cả khi tắt ngay trước giao dịch áp dụng |
| G6c | Guard nhảy giữa phép thử | Như G6a; chốt guard giữ nguyên |
| G6d | Hạn mức không đủ lúc lý do tới hạn | 0 lượt model; bài học `skipped/budget`; `calls_used` không đổi |
| G6e | Owner bấm Bỏ qua khi bài học đang `trialing` | Dừng ở cổng lượt kế; lượt đã bắt đầu vẫn tính |
| G7a | Không lý do hợp lệ thì 0 lượt: 50 reaction, 20 tick, không có bế tắc | Engine giả 0 lượt; `wake_reasons` và `wakeups` không đổi so với trước khi bấm |
| G7b | Bế tắc vì `reserve` (không phải `stalled`) | Không đề xuất; 0 lượt |
| G7c | Revision không có tiêu chí host chấm được | Bài học `skipped/untestable`; 0 lượt |

### 13.2 Bổ sung theo thiết kế

| ID | Kịch bản | Kiểm |
|---|---|---|
| A1 | Luồng làn P đủ: 2 tin `too_long` → đề xuất → xem trước → Áp dụng → tin `goal.succeeded` kế tiếp | Câu `brief`; tin bắt buộc (`goal.guard`, `goal.stalled`) vẫn đầy đủ |
| A2 | Tắt chuông: bài học `quiet` active | `goal.maintained` gửi với `quiet=True`; `goal.deadline_passed`, `goal.monitoring_lost` vẫn rung chuông |
| A3 | Ít làm phiền không đổi lịch | `wakeups`, lịch quan sát guard, lịch hạn chót giống hệt trước và sau khi áp dụng làn P |
| A4 | Luồng làn M đủ: 3 lượt việc không tiến → bế tắc → `method_trial` → phép thử eligible → áp dụng → tin `method_changed` | Lượt thử = 2; `calls_used` = 5; còn đúng 1 lượt dự phòng; A2 không tự thử lại |
| A5 | Tin mới thắng phép thử | Góp ý tới trước tick: lượt sửa dùng cách cũ; lý do `method_trial` chốt `superseded`; bài học `skipped/new_feedback` |
| A6 | "Hiểu chưa đúng" sau khi có đề xuất | Lý do bị gác; không chạy; áp dụng bị chặn nếu đang chạy |
| A7 | Đổi revision sau khi áp dụng | Bài học `out_of_scope`; `effective_method` mặc định |
| A8 | Học không ghi quyền | Hash file trợ lý, các dòng `resonance_agents` và `config_version` giống hệt trước và sau mọi ca của 13.1, 13.2 |
| A9 | Nguồn bị xoá hay bị sửa | Xoá tin (biên nhận mất) hay sửa nội dung: reaction mồ côi, không đếm; bài học đã áp dụng vẫn áp, danh sách hiện "nguồn đã xoá" |
| A10 | Phản hồi muộn | Reaction trên tin của revision cũ và của mục tiêu đã huỷ: ghi, tính cho làn P, mục tiêu không đổi |
| A11 | Trợ lý tắt | Reaction ghi được, không đề xuất; bật lại rồi bấm thêm thì đề xuất xuất hiện |
| A12 | Quay về 0.88.1 | Mở kho A3 bằng mã `83bff6bc` (git archive): không lỗi; lý do `method_trial` không gọi model; cách làm làn M vẫn đúng phạm vi |
| A13 | Di chuyển | Kho 0.88 lên 0.89: có `.pre-a3.bak`; bảng cũ không đổi cột; mở lần hai không sao lưu lại |
| A14 | Chạy lại sau khi chết giữa phép thử | `reopen()` giữa hai bên: `_reconcile` chốt lượt dở; không phép thử thứ hai cho cùng cặp và revision |
| A15 | Giao diện | Test JS: hàng reaction chỉ vẽ trên tin có biên nhận; request mang `nonce`; bấm lại đúng giá trị gửi `none`; khoá `tw()` nguyên văn; `test_i18n.mjs` xanh |
| A16 | Không ký tự gạch dài | Mọi chuỗi mới trong code, i18n, tài liệu |

### 13.3 Không có trong nghiệm thu A3

- Pilot model thật: chỉ chạy khi chủ dự án duyệt hạn mức riêng. Đề xuất pilot sau khi mã đạt review: tối đa 6 lượt gọi model, dùng engine hay gói thuê bao hiện có, một mục tiêu bế tắc thật đi hết làn M. Không tự chuyển sang API trả phí, không tự thử lại hoặc nâng trần.
- Đo hiệu năng VPS: không thuộc A3.

## 14. Quyết định mặc định cần review

| # | Câu hỏi | Mặc định đề xuất | Phương án khác |
|---|---|---|---|
| D1 | Reaction gắn vào đâu | Chỉ tin báo do host ghi có biên nhận | Thêm câu trả lời của trợ lý trong phiên agent: cần nguồn tin đáng tin và một cách áp dụng không đi qua prompt chat; để sau |
| D2 | Ai áp dụng làn P | Owner bấm Áp dụng sau khi xem trước; im lặng thì hết hạn | Tự áp dụng sau N tin: nhanh hơn nhưng đổi hành vi dựa trên emoji, trái mục tiêu "không chạy theo emoji" |
| D3 | Làn M có tự chạy không | Tự chạy khi bế tắc khách quan, trong phần khám phá có sẵn, chừa lượt dự phòng | Chờ owner bấm Thử: chắc hơn về chi phí, nhưng thêm một bước mỗi lần bế tắc |
| D4 | Bộ tình huống làn M | Một tình huống của chính revision, không holdout, phạm vi goal + revision | Thêm holdout từ mục tiêu đã đạt của cùng trợ lý: mạnh hơn nhưng tốn 4 lượt, không vừa hạn mức mặc định 6 |
| D5 | Đầu ra phép thử thắng | Không đăng làm sản phẩm; lượt việc sau dùng cách mới | Tiếp nhận đầu ra thử qua cổng bàn giao: tiết kiệm một lượt, nhưng cần hợp đồng bàn giao của A4; để sau A4 |
| D6 | "Cần chỉnh" có mở làn M | Không, vì host không chấm được phép thử cho tiêu chí người dùng chấm | Phép thử chấm tay: người dùng chấm bản thử. Đây gần với đội review của A5 |
| D7 | Tin tuỳ chọn của làn P | `goal.succeeded`, `goal.maintained` được rút gọn; chỉ `goal.maintained` được tắt chuông | Rộng hơn: dễ giấu tin cần người dùng làm gì |

## 15. Kế hoạch code (sau khi thiết kế đạt review)

Mỗi bước một commit có test; chạy test cũ của M4, M5, A1, A2 sau mỗi bước.

1. **Kho:** bảng, chỉ mục, sao lưu `.pre-a3.bak`, `A3_TABLES`; test di chuyển và test khoá cột cũ (`resonance_store.py`).
2. **Reaction:** `record_reaction` (kiểm biên nhận, upsert, log, mồ côi), `POST /resonance/reactions`; nguồn tin cho phản hồi M4 (`resonance_store.py`, `resonance_api.py`, `main.py` truyền tra cứu `report_receipts` vào kho).
3. **Bộ học làn P:** hàm thuần `resonance_learning.py` (mới, không I/O, như `resonance_heartbeat.py`), vòng đời bài học, `GET /resonance/lessons`, `POST .../decision`.
4. **Áp làn P:** `PRESENTATION`, `notice_text(..., presentation)`, `drain_outbox` đọc bài học, `quiet` trong `_resonance_notify`, ghi `presentation` vào biên nhận.
5. **Làn M:** đề xuất trong nhánh bế tắc, `heartbeat.v2` (`TRIAL`, `method_trial`, `trial_allowed`), tách thân `compare_methods`, bộ tình huống `host_revision`, quyết định `trial` trong khung lần thức, `goal.method_changed`, thu hồi kèm `revert_method`, `out_of_scope` khi `revise`.
6. **Giao diện:** hàng reaction (`chat-resonance.js`), mục Bài học (`resonance-agent.js`), khối `learning` trên thẻ, i18n.
7. **Test:** `tests/python/test_resonance_a3_learning.py` (ma trận 13.1, 13.2), `tests/python/test_resonance_a3_rollback.py` (`OLD_SHA` = `83bff6bc`), `tests/js/test_resonance_a3_ui.js`; CI lấy thêm commit `83bff6bc` cho test quay về.
8. **Tài liệu:** hướng dẫn `docs/dev/resonance-a3-learning.md`, biên bản `docs/dev/resonance-a3-verification.md`, lộ trình mục 6 và mục 8.

## 16. Phần chuyển sang A4, A5

- **A4:** tiếp nhận đầu ra thắng của phép thử làm sản phẩm (D5) sẽ dùng hợp đồng bàn giao chung.
- **A5:** phép thử chấm tay cho tiêu chí người dùng chấm (D6) gần với vai reviewer; review là một nguồn bằng chứng theo loại tiêu chí, không thay kiểm khách quan.
