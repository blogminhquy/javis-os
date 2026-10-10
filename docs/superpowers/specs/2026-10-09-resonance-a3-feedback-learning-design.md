# Resonance A3: vòng phản hồi và học có kiểm chứng

**Trạng thái:** thiết kế ĐẠT review vòng 3 (`d6239d54`, báo cáo `exports/reviews/PR-598-A3-r3-d6239d54-review.md`, ngoài git). Đã triển khai trên cùng nhánh, chờ review mã; ghi chú triển khai ở mục 19. Vòng 1 (`a6418e45`): 1 P1, 2 P2, D4 chưa đạt (mục 17). Vòng 2 (`ef56b61f`): 2 P2 về sổ giữ lượt (mục 18). Nhánh `claude/resonance-a3-feedback-learning`, đặt số 0.89.0.

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
| **M (cách làm)** | Cách làm M5 (`METHODS`) của một mục tiêu, trong đúng revision | Bế tắc khách quan: tiêu chí host kiểm không tiến thêm (A2) | Phép thử M5 `compare_methods` giữ nguyên luật (có tình huống giữ riêng), host chấm cả hai bên bằng cùng thước đo | Host, chỉ khi phép thử ra `eligible` | Phép thử trong phần khám phá, cộng một lượt làm sản phẩm bằng cách mới được giữ sẵn, cộng lượt dự phòng; thiếu thì không thử |

**Giữ nguyên:**
- Phản hồi M4 (Đúng ý / Hiểu chưa đúng, Đạt yêu cầu / Cần chỉnh) giữ nguyên nghĩa và đường ghi. A3 chỉ thêm nguồn tin nhắn vào dữ liệu ghi kèm.
- M5 giữ nguyên luật: `METHODS` khai báo sẵn, bộ tình huống có tập thử và giữ riêng, phép thử giữ chỗ hạn mức trước khi gọi, cổng kiểm trước mỗi lượt và trong giao dịch áp dụng, phạm vi goal + revision, `revert_method`. A3 chỉ thêm vào M5: danh tính bài học trong hai giao dịch giữ chỗ và chốt (mục 6.4), lượt làm sản phẩm giữ sẵn (mục 6.3), và prompt theo revision của từng tình huống (mục 6.2).
- A2 giữ nguyên: lý do thức, lớp, vòng đời, `decide`. A3 thêm đúng hai mã lý do (`method_trial`, `method_followup`) và hai lớp (`TRIAL`, `FOLLOWUP`) (mục 6.3).
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

**Hạn mức thực tế:** mục tiêu mặc định có 6 lượt (`GOAL_DEFAULT_CALLS`), phần khám phá 50% là 3 lượt, lượt dự phòng A2 là 1. Bế tắc theo `heartbeat.v1` xảy ra sớm nhất sau 3 lượt việc thành công. Khi đó còn 3 lượt. Trọn vòng làn M theo luật M5 cần phép thử có tình huống giữ riêng (4 lượt), một lượt làm sản phẩm bằng cách mới và lượt dự phòng: tổng 6 lượt còn lại, tức hạn mức ít nhất 9 khi bế tắc ở lượt thứ 3. **Mục tiêu mặc định 6 lượt sẽ luôn bỏ qua làn M** (ghi `skipped/budget`, 0 lượt model). A3 nói rõ giới hạn này thay vì nới luật bằng chứng để vừa hạn mức (mục 14, D4). Làn P không tốn lượt nào nên chạy với mọi mục tiêu.

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

- **Một người, một tin, một giá trị hiện tại.** Khoá duy nhất `(brain_id, session_id, message_id, responder)`. API theo nghĩa **đặt giá trị**: mỗi request mang `value` rõ ràng; request mới (nonce mới) ghi đè giá trị hiện tại và tăng `seq`, kể cả khi giá trị không đổi. Thu hồi là gửi `value='none'`. Luật "bấm lại đúng nút đang sáng là thu hồi" là luật **giao diện**: trang tự gửi `none`, API không tự đảo. Lịch sử đầy đủ nằm ở `reaction_log`.
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
   ├──(quá hạn 14 ngày, hay mất đủ số tin vì mồ côi)──▶ expired
   └──(lúc Áp dụng, cấu hình nền đã đổi)──▶ stale
```

- **So với cách cũ:** đề xuất kèm bản xem trước dựng bằng code từ chính tin đã nhận phản hồi: câu cũ và câu mới cạnh nhau, cùng ghi chú "tin bắt buộc không đổi". Không gọi model.
- **Hai chốt tách riêng** cho mỗi khoá, mỗi phạm vi: tối đa **một** bài học `active` (cấu hình đang dùng) và tối đa **một** đề xuất đang chờ (`proposed`, hay `trial_pending`/`trialing` ở làn M). Hai chốt là hai chỉ mục duy nhất từng phần riêng (mục 7.1). Nhờ vậy cấu hình đang dùng `brief` và đề xuất quay lại `full` tồn tại cùng lúc; cấu hình đang dùng không bao giờ bị vô hiệu hoá chỉ để có chỗ lưu đề xuất.
- **Nền của đề xuất:** mỗi đề xuất ghi `base_lesson_id` (bài học `active` lúc tạo đề xuất; rỗng nếu lúc đó đang dùng mặc định) và `from_value` (giá trị lúc đó).
- **Áp dụng:** chỉ owner, trong một giao dịch:
  1. đề xuất vẫn `proposed` (CAS theo `expected_status`, `expected_updated_at` mà thẻ đang thấy);
  2. bài học `active` hiện tại của khoá đúng là `base_lesson_id` và còn mang `from_value` (hay không có bài học `active` nào khi `base_lesson_id` rỗng);
  3. bài học nền thành `superseded`, đề xuất thành `active`.

  Điều kiện 2 không đạt (owner đã thu hồi nền, hay đã áp dụng giá trị khác) thì đề xuất thành `stale`, trả 409 kèm cấu hình hiện tại; không áp dụng mù. Áp dụng đề xuất có `to_value` là giá trị mặc định (ví dụ quay lại `full`) vẫn tạo một bài học `active` mang giá trị đó: đây là lựa chọn rõ của owner, có nguồn và có thể thu hồi như mọi bài học khác.
- **Bỏ qua:** đề xuất thành `dismissed`; cấu hình đang dùng không đổi.
- **Thu hồi:** bài học `active` thành `revoked`; khoá về mặc định. Đề xuất đang chờ dựa trên nền này sẽ thành `stale` khi owner bấm Áp dụng. Từ `learning.v2` (sau pilot), Thu hồi chặn đề xuất lại cùng (trợ lý, khoá, giá trị) 14 ngày như Bỏ qua.
- **Bài học có hiệu lực** của một trợ lý = bài học `active` của mỗi khoá (nhiều nhất một). Không có thì dùng mặc định.

### 5.3 Bộ học làn P (`learning.v2`, hàm thuần)

Đầu vào: các reaction không mồ côi của một trợ lý trong 30 ngày, giá trị hiện tại; các bài học làn P hiện có. Đầu ra: không hay một đề xuất.

| Đề xuất | Điều kiện |
|---|---|
| `notice_detail: full → brief` | Ít nhất **2 tin khác nhau** thuộc loại áp được, có giá trị hiện tại `down` + `too_long`; khoá đang ở `full`; không có đề xuất mở, bài học `dismissed` hay `revoked` trong 14 ngày cho cùng khoá và giá trị của trợ lý này |
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
5. Có đủ bộ tình huống hợp lệ theo luật M5, gồm cả tình huống giữ riêng (mục 6.2).
6. Đủ **ngân sách trọn vòng** (mục 6.3): phép thử, một lượt làm sản phẩm bằng cách mới, và lượt dự phòng.
7. Trợ lý bật, mục tiêu active, không pause, không chốt guard, cách hiểu không bị "Hiểu chưa đúng".

Đủ điều kiện thì ghi bài học `trial_pending` và một lý do thức sự kiện `method_trial` (`source_ref = lesson:<id>`, `due_at` = bây giờ). Thiếu điều kiện 2, 5 hay 6 thì ghi bài học `skipped` với lý do `untestable`, `no_holdout` hay `budget` để người dùng thấy vì sao không thử; 0 lượt model. Các điều kiện khác thiếu thì không ghi gì.

"Cần chỉnh" (tiêu chí người dùng chấm) không mở đề xuất làn M: host không chấm được phép thử cho tiêu chí đó, nên không có bằng chứng để so. Ghi chú "Cần chỉnh" vẫn đi vào lượt sửa trong revision như M4/A2 (mục 14, D6).

### 6.2 Bộ tình huống: giữ luật M5

A3 **không nới** luật bằng chứng của M5: bộ tình huống phải có ít nhất một tình huống tập thử (`tuning`) và một tình huống giữ riêng (`holdout`). Không dựng tình huống giả và không chạy lặp cùng một đầu vào rồi gọi là giữ riêng.

Host dựng bộ từ hồ sơ của chính mục tiêu, không ai phải nhập:

- **Tập thử:** revision hiện tại. `input` = lời người dùng của revision; `expect` = tham số của tiêu chí `artifact_contract` đầu tiên có tham số.
- **Giữ riêng:** revision **trước** gần nhất của cùng mục tiêu mà bộ tiêu chí host chấm (danh sách `artifact_contract` cùng tham số, đã chuẩn hoá) **giống hệt** revision hiện tại. `input` = lời người dùng của revision đó. Tối đa một tình huống giữ riêng trong A3.
- Mỗi tình huống mang `revision` nguồn của nó; lời gọi model của tình huống dựng prompt từ bản ghi revision đó (cách hiểu, ràng buộc), còn thước đo là bộ tiêu chí chung đã ghim bằng `rubric_hash` như M5. Đây là thay đổi duy nhất A3 cần trong M5 (`_trial_run` nhận bản ghi revision theo tình huống); luật kết luận `_trial_verdict` giữ nguyên.
- **Đầu vào phải khác thật.** Khác số revision chưa đủ. Host tính `prompt_input_hash` của mỗi tình huống từ đúng phần dựng prompt ngoài tiêu chí (cách hiểu, lời người dùng, ràng buộc, giả định; chuẩn hoá khoảng trắng; không tính id, nhãn, lý do sửa hay thời điểm). Revision trước có `prompt_input_hash` trùng với tập thử thì không được chọn làm giữ riêng; host xét tiếp revision cũ hơn trong giới hạn `M_HOLDOUT_SCAN`.
- **Ghim:** payload phép thử ghi `prompt_input_hash` và hash bản ghi revision của từng tình huống, cùng `rubric_hash`.
- **Revision lịch sử chỉ dùng để dựng prompt.** Quyền thực thi, ngân sách, action, cổng lượt và giao dịch áp dụng đều thuộc phép thử ở revision hiện tại; revision lịch sử không được truyền vào các cổng đó. Lời người dùng cũ chỉ là dữ liệu, không phải lệnh tác động lên brain: phép thử vẫn chỉ sinh chữ trong vùng làm việc của phép thử, không đăng file.
- Không có revision trước nào hợp lệ thì bài học `skipped/no_holdout`, 0 lượt model.

**Mức bằng chứng:** `eligible` nghĩa là ở đúng lần thử này, ứng viên đạt tình huống tập thử mà cách cũ chưa đạt, và không tụt ở tình huống giữ riêng. Mỗi bên chỉ có một lần sinh mỗi tình huống, nên kết luận không loại hẳn được dao động giữa hai lần sinh. Vì vậy phạm vi áp dụng chỉ là goal + revision hiện tại (như M5), có đường quay lại, và lượt làm sản phẩm sau đó vẫn được host chấm như mọi lượt việc. Phạm vi goal + revision là phạm vi M5 vốn có, không phải bảo vệ mới bù cho bằng chứng.

**Hệ quả thực tế:** tình huống giữ riêng hợp lệ chỉ có khi mục tiêu đã sửa cách hiểu mà giữ nguyên tiêu chí host chấm. Trường hợp này hiếm, nên làn M sẽ thường ghi `skipped/no_holdout`. A3 chấp nhận giới hạn này; nguồn tình huống khác (owner tự thêm, hay reviewer của A5) để sau và phải qua cùng luật M5.

### 6.3 Ngân sách trọn vòng và lý do thức (`heartbeat.v2`)

**Ngân sách trọn vòng**, kiểm khi tạo đề xuất và kiểm lại trong giao dịch giữ chỗ của phép thử:

- `trial_cost` = 2 × số tình huống chạy được (A3: 2 × 2 = 4 lượt);
- phần khám phá: `explore_used + trial_cost <= int(budget_calls × EXPLORE_SHARE)` (luật M5);
- tổng: `calls_used + trial_cost + 1 + AUTO_RESERVE_CALLS <= budget_calls`. Số 1 là lượt làm sản phẩm bằng cách mới (mục 6.5).

Ví dụ: bế tắc sau 3 lượt việc thì cần hạn mức ít nhất 9 (và phần khám phá ít nhất 4, tức hạn mức ít nhất 8). Mục tiêu mặc định 6 lượt luôn ghi `skipped/budget`. A3 không bao giờ xin thêm hay tự nâng hạn mức.

**Giữ chỗ lượt làm sản phẩm:** giao dịch `begin_experiment` giữ cùng lúc `trial_cost` lượt khám phá (như M5) **và** một lượt làm sản phẩm. Lượt làm sản phẩm ghi ở bảng mới `call_holds` (mục 7.1), được cộng vào `calls_used` ngay lúc giữ, nên trần mục tiêu và trần chung `JAVIS_RESONANCE_CALL_CEILING` đã tính nó. Nó không cộng vào `explore_used`. Phép thử không áp dụng thì lượt giữ được trả lại trong giao dịch `finish_experiment`.

**Chính sách `heartbeat.v2`** (tăng `POLICY_VERSION`; `wake_log` cũ giữ phiên bản của nó) thêm hai mã sự kiện:

| Mã | Lớp mới | Mở lượt khi | Chi phí |
|---|---|---|---|
| `method_trial` | `TRIAL` | Bài học `trial_pending`, đủ ngân sách trọn vòng | `trial_cost` + giữ 1 |
| `method_followup` | `FOLLOWUP` | Có lượt giữ `held` cho đúng goal, revision, phép thử; bài học `active`; cách làm có hiệu lực đúng là ứng viên | Dùng lượt đã giữ, không giữ thêm |

- Thứ tự `decide`: đạt hay chỉ chờ người dùng → `NEW` → `START` → **`FOLLOWUP`** → **`TRIAL`** → `AUTO`. Tin mới từ người dùng luôn thắng.
- `waiting/stalled` **không** phải trạng thái bị gác trong A2 (gác chỉ gồm pause, `blocked`, "Hiểu chưa đúng", `source_drift`, chờ bàn giao, trợ lý tắt). Nên lý do sự kiện của mục tiêu đang bế tắc được phục vụ bình thường, và `FOLLOWUP` mở đúng một lượt việc.
- Mục tiêu ở trạng thái bị gác thì cả hai lý do bị gác như mọi lý do khác (chỉ `UNPARK_CODES` được tính), không chạy; lượt giữ vẫn giữ tới khi gỡ gác hay tới khi bị trả (mục 6.6).
- Có tin mới từ người dùng trước khi **phép thử** chạy: lượt sửa chạy bằng cách cũ; chuỗi A2 đặt lại nên điều kiện bế tắc không còn; lý do `method_trial` chốt `superseded`, bài học `skipped/new_feedback`.
- Có tin mới từ người dùng **sau khi áp dụng**, trước lượt `FOLLOWUP`: lượt sửa **tiếp quản** lượt đã giữ (mục 6.8), chạy bằng cách mới (cùng revision), tức chính là lượt làm sản phẩm đã hoạch định, nay có thêm góp ý. Không giữ thêm lượt, nên không bị trần chặn; lý do `method_followup` chốt `superseded`.
- Lịch xem lại và hạn chót vẫn là `CHECK`: không mở lượt model, kể cả sau khi áp dụng.

### 6.4 Chạy phép thử và chốt trạng thái bài học trong giao dịch

Quyết định `trial` đi qua đúng khung lần thức A2: pha chuẩn bị trong luồng phụ giữ khoá lượt, pha model trên event loop, `_finish_wake` nhả khoá và ghi `wake_log` (`decision='trial'`, `model_calls` = số lượt đã tính). Phần thân của `compare_methods` được tách thành hàm nhận khoá lượt có sẵn; `compare_methods` công khai vẫn tự giành khoá như cũ và không truyền bài học (hành vi M5 không đổi).

Mọi chốt của M5 giữ nguyên: giữ chỗ trước khi gọi, ghim mã và version trợ lý, `_trial_gate` và `agent_gate` trước mỗi lượt và ngay trước khi kết luận, `_method_change_blocked` trong giao dịch áp dụng, hoàn lại lượt chưa bắt đầu.

A3 thêm **danh tính bài học** vào hai giao dịch của M5, vì cổng ngoài giao dịch luôn để hở một khe trước giao dịch:

- **`begin_experiment(..., lesson_id)`:** trong cùng giao dịch giữ chỗ, `UPDATE lessons SET status='trialing', experiment_id=? WHERE id=? AND status='trial_pending' AND goal_id=? AND revision=?`. Không đúng một dòng thì không tạo phép thử, không giữ lượt nào.
- **`finish_experiment(..., lesson_id)`:** trong cùng giao dịch chốt, **trước** `_set_method`:
  - `UPDATE lessons SET status='active' ... WHERE id=? AND status='trialing' AND experiment_id=? AND goal_id=? AND revision=?`, chỉ khi verdict `eligible` và `_method_change_blocked` cho qua.
  - Không đúng một dòng (owner đã Bỏ qua, hay bài học đã đổi): không đổi cách làm; phép thử chốt `inconclusive`, lý do `lesson_dismissed`; giữ nguyên quyết định Bỏ qua của owner; lượt đã gọi vẫn tính; hoàn phần chưa bắt đầu; trả lượt giữ làm sản phẩm.
  - Verdict khác `eligible`: bài học `trialing` thành `rejected` hay `unknown` bằng cùng CAS; nếu bài học đã `dismissed` thì giữ `dismissed`. Lượt giữ được trả.

**Thứ tự với Bỏ qua.** Mọi giao dịch ghi của kho là `BEGIN IMMEDIATE`, nên hai giao dịch cùng bài học luôn có thứ tự commit rõ ràng:

| Commit trước | Kết quả |
|---|---|
| Bỏ qua (`trial_pending`/`trialing` → `dismissed`) | Cổng lượt kế tiếp dừng phép thử; nếu phép thử đã tới bước chốt thì CAS trong `finish_experiment` thất bại: cách làm giữ nguyên, phép thử `inconclusive/lesson_dismissed` |
| Chốt áp dụng (`trialing` → `active`) | Request Bỏ qua cũ nhận 409 kèm trạng thái `active`; giao diện đổi nút thành "Quay lại cách cũ" (thu hồi, mục 6.6) |

Bỏ qua không đòi `expected_updated_at` khớp (bài học đổi `trial_pending` → `trialing` giữa lúc owner nhìn thẻ), chỉ đòi trạng thái hiện tại thuộc `trial_pending` hay `trialing`.

### 6.5 Kết quả và lượt làm sản phẩm

| Verdict M5 | Bài học | Cách làm | Lượt giữ | Tiếp theo |
|---|---|---|---|---|
| `eligible`, CAS bài học và `_method_change_blocked` cho qua | `active`, phạm vi goal + revision, ghi `experiment_id` | Đổi trong cùng giao dịch `finish_experiment` (M5) | Giữ (`held`) | Ghi lý do `method_followup` cùng giao dịch |
| `eligible` nhưng bị chặn (M5) | `unknown` | Giữ | Trả | Không |
| `eligible` nhưng owner đã Bỏ qua | `dismissed` (giữ nguyên) | Giữ | Trả | Không |
| `rejected` | `rejected` | Giữ | Trả | Thẻ hiện "đã thử, cách cũ giữ nguyên" |
| `inconclusive` | `unknown` | Giữ | Trả | Thẻ hiện lý do |

**Lượt làm sản phẩm (`FOLLOWUP`):** một lượt việc thường của A2, chạy đúng một lần:

- `begin_action` của lượt này **dùng lượt giữ** (`held` → `attached` bằng CAS trong cùng giao dịch ghi ý định, không cộng `calls_used`, mức tăng ròng 0 khi kiểm trần) thay cho giữ lượt mới. Lượt giữ thành `used` khi action chốt kết quả mà model có thể đã chạy; huỷ trước engine thì trở về `held` để chạy lại (mục 6.8). Lượt giữ đã `used` thì lý do được chốt và không chạy lần hai, kể cả sau khi khởi động lại.
- Prompt dùng cách làm có hiệu lực (ứng viên), bản sản phẩm hiện có và các tiêu chí chưa đạt, như mọi lượt sửa.
- Đăng sản phẩm qua đúng cổng bàn giao hiện có: không ghi đè bản người dùng sửa tay (A2 mục 5), guard, quyền trợ lý và xác nhận đúng `artifact_ref` (M4) giữ nguyên.
- Kết quả được host chấm như mọi lượt (`evaluate_artifact`). Lượt này tính vào chuỗi A2 hiện có, không đặt lại chuỗi: vượt mốc cũ là tiến bộ; không vượt thì mục tiêu lại `waiting/stalled` và chờ góp ý.
- Tiến trình chết sau khi ghi ý định: đối soát của A2 chốt lượt dở như mọi lượt việc, rồi đối soát lượt giữ đổi nó sang `used` (mục 6.8). Không cấp lại lượt. Thử lại tự động của A2 vẫn chịu luật chừa lượt dự phòng, nên không tự tiêu thêm.

**Tổng chi phí trọn vòng** với ví dụ hạn mức 9, bế tắc sau 3 lượt: 3 + 4 (phép thử) + 1 (sản phẩm) = 8; còn đúng 1 lượt dự phòng cho góp ý của người dùng.

Đầu ra của phép thử không được đăng làm sản phẩm (D5); sản phẩm luôn đến từ lượt làm sản phẩm.

### 6.6 Tin `goal.method_changed`

Bắt buộc, luôn đầy đủ, gửi **sau** lượt làm sản phẩm (hay khi lượt giữ bị trả trước khi chạy). Nội dung:
- cách làm nào đã thử, trên mấy tình huống, kết quả từng bên;
- chỉ áp dụng cho cách hiểu hiện tại;
- tổng lượt đã tốn;
- kết quả của lượt làm sản phẩm bằng cách mới (đạt hay chưa đạt tiêu chí nào), hoặc lý do chưa làm lại sản phẩm;
- nút Quay lại cách cũ trên thẻ.

Khoá chống báo lặp `method_changed:<experiment_id>`. Tin này không đổi lịch thức.

### 6.7 Thu hồi, hết phạm vi, trả lượt giữ

| Sự kiện | Bài học | Cách làm | Lượt giữ, lý do `method_followup` |
|---|---|---|---|
| Owner "Quay lại cách cũ" | `revoked` | `revert_method` (M5, không đổi) | Trả lượt giữ nếu còn `held`; chốt lý do. Một giao dịch |
| Sửa cách hiểu (revision mới) | `out_of_scope`, ghi trong giao dịch `revise` | `effective_method` tự về mặc định (M5) | Trả lượt giữ; lý do thuộc revision cũ bị bỏ. Cách vừa học **không** dùng cho revision mới |
| Huỷ mục tiêu | giữ nguyên trạng thái để xem lại | không liên quan | Lượt giữ ghi `released` để sổ khớp; lý do bị xoá cùng mục tiêu (A2) |
| Tin mới từ người dùng cùng revision trước lượt `FOLLOWUP` | giữ `active` | cách mới | Lượt sửa tiếp quản lượt giữ (`attached`), không giữ thêm; chốt lý do `superseded` (mục 6.8) |
| Huỷ lần thức trước engine | giữ | giữ | Lượt giữ về `held`, lý do trở lại chờ; chạy lại một lần (mục 6.8) |
| Pause, tắt trợ lý, guard | giữ `active` | giữ | Lý do bị gác, lượt vẫn giữ; gỡ gác thì chạy. Guard đã chốt hay hết hạn mức thì không chạy |

Bấm thu hồi lần nữa khi đã thu hồi thì trả trạng thái hiện tại, không lỗi.

### 6.8 Sổ giữ lượt (`call_holds`): trạng thái, tiếp quản, huỷ, đối soát

**Trạng thái** (tách hai thời điểm mà vòng 2 còn gộp):

| Trạng thái | Nghĩa | `calls_used` |
|---|---|---|
| `held` | Đã giữ chỗ, chưa gắn lượt nào | Đã gồm lượt này |
| `attached` | Đã gắn cho một action (ý định đã ghi), action chưa chốt kết quả | Không đổi |
| `used` | Action gắn với nó đã chốt với bất kỳ kết quả nào khác `not_run`, tức model **có thể** đã được gọi | Không đổi (lượt đã tiêu) |
| `released` | Đã trả lại, đúng một lần | Trừ 1, trong cùng giao dịch đổi trạng thái |

Mọi chuyển trạng thái là CAS trên `(id, status, action_id)` trong một giao dịch, nên lặp lại hay chạy song song không trả hoặc giữ hai lần. Cột `gen` tăng mỗi lần lượt giữ quay về `held` sau khi đã gắn, hay được dựng lại lý do; lý do `method_followup` mang `source_ref = hold:<id>:<gen>`, nên dựng lại lý do không đụng chỉ mục duy nhất của lý do sự kiện cũ (A2).

**Ai được dùng lượt giữ.** Chỉ một lượt việc **cùng goal và cùng revision** của lượt giữ, khi lượt giữ đang `held` và còn hợp lệ: phép thử đã áp dụng, bài học `active`, cách làm có hiệu lực đúng là ứng viên. Hai đường:

- **`FOLLOWUP`:** lượt làm sản phẩm như mục 6.5.
- **`NEW` tiếp quản** (góp ý cùng revision tới trước `FOLLOWUP`): lượt sửa của người dùng **nhận thẳng** lượt giữ, không giữ lượt mới. Trong cùng giao dịch `begin_action`: ghi action, lượt giữ `held` → `attached` với `action_id` của lượt sửa, lý do `method_followup` chốt `superseded` với `settled_by` = action đó. Không cộng `calls_used`. Bước kiểm trần chung (`_under_ceiling`) và trần mục tiêu tính **mức tăng ròng** = 0 cho lượt dùng lượt giữ, nên mục tiêu đang chạm trần vẫn nhận được góp ý. Cổng quyền trợ lý, guard, revision và nội dung góp ý kiểm như mọi lượt `NEW`.
- Các cổng **ngoài** giao dịch (quyết định `decide` của A2: `left > 0`) coi lượt `held` hợp lệ của đúng revision là còn dùng được cho `NEW` và `FOLLOWUP`, không từ chối như một lượt mới.
- Lượt giữ của revision cũ, hay đã `used`/`released`, không bao giờ được mượn lại. Lượt `NEW` khi đó giữ lượt mới như thường, chịu trần như thường.

**Huỷ trước engine** (`abort_action`, bằng chứng chắc chắn `not_run`): mở rộng giao dịch có sẵn của A2. Action dùng lượt giữ thì:
- không trừ `calls_used` (lượt vẫn đang được giữ);
- lượt giữ `attached` → `held`, xoá `action_id`, tăng `gen`;
- lý do mà action đã phục vụ trở lại `pending` như A2 hiện làm (gồm lý do `NEW` và lý do `method_followup` đã chốt với `settled_by` = action đó).

Lượt sau chạy lại đúng một lần. Huỷ lặp thấy action không còn `running` nên không làm gì. Action không dùng lượt giữ giữ nguyên hành vi A2.

**Model có thể đã chạy** (action chốt `succeeded`, `failed`, `unknown`, hay `_reconcile` của A2 chốt lượt dở): lượt giữ `attached` → `used` trong cùng giao dịch chốt action. Không cấp lại lượt một cách suy đoán. Thử lại tự động sau đó vẫn theo luật A2 (chừa lượt dự phòng).

**Đối soát lượt giữ** (`reconcile_holds`): không có vòng quét nền mới. Chạy ở hai chỗ:
1. một lần khi mở kho, sau di chuyển (bắt cả trường hợp vừa nâng lại từ 0.88), trên các dòng `held`/`attached` (rất ít);
2. trong pha chuẩn bị của mỗi lần thức một mục tiêu, trước khi phục vụ lý do (chỉ các dòng của mục tiêu đó).

Luật, theo thứ tự, mỗi luật một giao dịch CAS:

| Tình trạng | Xử lý |
|---|---|
| `attached`, action `cancelled/not_run` | Như huỷ trước engine: về `held`, tăng `gen` |
| `attached`, action đã chốt kết quả khác | `used` |
| `attached`, action còn `running`, lease còn hạn | Để nguyên |
| `attached`, action `running`, lease hết hạn | `_reconcile` của A2 chốt action trước, rồi áp hai luật trên |
| `held`, phép thử còn `running`, có lease sống | Để nguyên |
| `held`, phép thử còn `running` mà không có lease sống (tiến trình chết giữa phép thử) | Chốt phép thử `inconclusive/interrupted` qua `finish_experiment` (hoàn các lượt thử chưa ghi ý định, như M5), bài học `trialing` → `unknown`, rồi lượt giữ `released` |
| `held`, không còn hợp lệ: mục tiêu không active, revision đã đổi, bài học không `active`, cách làm có hiệu lực khác ứng viên (ví dụ bản cũ đã `revert_method`), hay phép thử không áp dụng | `released` đúng một lần; chốt mọi lý do `method_followup` còn chờ của nó; bài học được ghi lại theo sự thật M5 (`revoked` lý do `reverted_outside`, hay `out_of_scope`) |
| `held`, còn hợp lệ, không có lý do `method_followup` nào đang chờ | Dựng lại **đúng một** lý do: tăng `gen`, `source_ref = hold:<id>:<gen>` |
| `held`, còn hợp lệ, đã có lý do chờ | Để nguyên |

Nhờ đó chu trình A3 → 0.88 → A3 khép kín: bản 0.88 coi `method_followup` là `CHECK`, chốt lý do mà không gọi model và không đụng lượt giữ; lần mở kho bằng A3 sau đó dựng lại lý do (hay trả lượt nếu bản cũ đã huỷ, sửa cách hiểu, hoặc quay lại cách cũ trong lúc chạy).

## 7. Kho

### 7.1 Bảng mới

Chỉ thêm bảng; không thêm cột vào bảng cũ (test `PRE_A1` vẫn khoá).

**`reactions`**: giá trị hiện tại của một người trên một tin.
- Cột: `id`, `brain_id`, `agent_key`, `agent_config_version`, `goal_id`, `revision` (revision của tin), `session_id`, `message_id`, `report_key`, `notice_kind`, `presentation` (cách dựng tin lúc gửi), `content_sha`, `responder`, `value` (`up`/`down`/`none`), `reason` (rỗng/`too_long`/`too_often`/`unclear`), `seq`, `created_at`, `updated_at`.
- Khoá duy nhất `(brain_id, session_id, message_id, responder)`; chỉ mục `(brain_id, agent_key, updated_at)`.

**`reaction_log`**: mọi lần bấm. Cột `id`, `reaction_id`, `value`, `reason`, `nonce`, `created_at`. Khoá duy nhất `(reaction_id, nonce)`.

**`lessons`**: đề xuất và bài học của cả hai làn.
- Cột: `id`, `brain_id`, `agent_key`, `lane` (`presentation`/`method`), `key` (`notice_detail`, `notice_ping`, `method`), `from_value`, `to_value`, `base_lesson_id` (bài học `active` làm nền lúc tạo đề xuất; rỗng = mặc định), `scope` (`agent`/`goal_revision`), `goal_id` (rỗng với làn P), `revision` (0 với làn P), `status`, `status_reason`, `policy_version`, `evidence_json`, `experiment_id`, `expires_at`, `decided_by`, `decided_at`, `created_at`, `updated_at`.
- Trạng thái: `proposed`, `trial_pending`, `trialing`, `active`, `superseded`, `revoked`, `dismissed`, `expired`, `stale`, `skipped`, `rejected`, `unknown`, `out_of_scope`.
- **Hai** chỉ mục duy nhất từng phần trên cùng bộ cột `(brain_id, agent_key, lane, key, goal_id, revision)`:
  - `lessons_active_one ... WHERE status='active'`: tối đa một cấu hình đang dùng;
  - `lessons_pending_one ... WHERE status IN ('proposed','trial_pending','trialing')`: tối đa một đề xuất đang chờ.

  Hai chỉ mục là chốt chống trùng khi chạy lại hay khởi động lại, và cho phép cấu hình đang dùng cùng đề xuất thay thế nó tồn tại song song (mục 5.2).

**`call_holds`**: lượt làm sản phẩm đã giữ cho làn M. Cột `id`, `goal_id`, `revision`, `experiment_id`, `lesson_id`, `purpose` (`method_followup`), `status` (`held`/`attached`/`used`/`released`), `action_id` (lượt đang gắn hay đã dùng nó), `gen`, `created_at`, `updated_at`. Khoá duy nhất `(experiment_id, purpose)`; chỉ mục `(goal_id, status)`. Lượt giữ được cộng vào `goals.calls_used` lúc giữ và trừ lại đúng một lần lúc `released`; `attached` và `used` không đổi bộ đếm. Vòng đời đầy đủ ở mục 6.8.

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
| Lượt làm sản phẩm đã giữ cho làn M | `call_holds`; số lượt đã tính vẫn là `goals.calls_used` (lượt giữ đã cộng vào đó) |

### 7.3 Di chuyển và quay về

- Lần đầu bản 0.89 mở một kho chưa có bảng A3: sao lưu `resonance.sqlite3` thành `.pre-a3.bak` (cùng hàm `_backup_before` của A2), rồi tạo bảng. Không di chuyển dữ liệu cũ nào.
- **Quay về 0.88.x:** bản cũ bỏ qua bảng lạ. Làn P mất hiệu lực (tin trở lại đầy đủ, rung chuông). Cách làm đã áp dụng ở làn M vẫn nằm ở cột M5 mà 0.88 đã hiểu, vẫn đúng phạm vi goal + revision. Bản cũ không biết lý do `method_trial`: mã lạ thuộc lớp `CHECK` của `heartbeat.v1`, chỉ kiểm, không gọi model; test quay về khoá điều này.
- Lượt giữ còn `held` lúc quay về: bản cũ không biết bảng `call_holds`, nên lượt đó vẫn nằm trong `calls_used` (tính dư một lượt, phía an toàn). Bản cũ coi `method_followup` là mã lạ lớp `CHECK`: **chốt lý do mà không gọi model và không đụng lượt giữ**. Bản cũ cũng có thể huỷ mục tiêu, sửa cách hiểu hay quay lại cách cũ trong lúc chạy.
- Nâng lại 0.89: `reconcile_holds` chạy khi mở kho (mục 6.8). Lượt giữ còn hợp lệ được dựng lại đúng một lý do `method_followup`; lượt không còn hợp lệ được trả đúng một lần; bài học được ghi lại theo sự thật M5.
- **Nâng lại 0.89 sau khi quay về:** bảng A3 còn nguyên; bài học làn M có thể lệch cột M5 (người dùng quay lại cách cũ bằng bản cũ) và được hiện theo M5 như mục 7.2.

## 8. Chính sách `learning.v2`

Hằng có phiên bản, không phải ô cài đặt. Đổi mặc định thì tăng phiên bản; mỗi bài học ghi `policy_version`. `learning.v1` là bản đã qua review mã và pilot; `learning.v2` chỉ thêm `P_REVOKE_COOLDOWN_S` (chủ dự án chốt sau pilot, 10/10/2026).

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `P_WINDOW_S` | 30 ngày | Reaction cũ hơn không mở đề xuất |
| `P_MIN_MESSAGES` | 2 | Số tin khác nhau tối thiểu cho đề xuất rút gọn hay tắt chuông |
| `P_REVERT_MIN_MESSAGES` | 1 | Số tin `brief` bị "Khó hiểu" để đề xuất quay lại |
| `P_PROPOSAL_TTL_S` | 14 ngày | Đề xuất không ai quyết thì hết hạn, giữ cách cũ |
| `P_DISMISS_COOLDOWN_S` | 14 ngày | Bỏ qua thì không đề xuất lại cùng thay đổi trong khoảng này |
| `P_REVOKE_COOLDOWN_S` | 14 ngày | `learning.v2`: Thu hồi cũng không đề xuất lại cùng (trợ lý, khoá, giá trị) trong khoảng này. Không chặn thay đổi khác, trợ lý khác hay làn cách làm; không đổi mục tiêu, lịch, quyền hay hạn mức. Hết thời gian chờ chỉ đề xuất lại khi vẫn đủ phản hồi còn sống trong cửa sổ 30 ngày, và không tự áp dụng |
| `M_CANDIDATES` | `work.v1 → work.checklist.v1` | Ứng viên duy nhất khi bế tắc |
| `M_TRIALS_PER_REVISION` | 1 mỗi cặp baseline, ứng viên | Không thử lại cùng cặp trong cùng revision |
| `M_HOLDOUT_MAX` | 1 | Một tình huống giữ riêng: revision trước gần nhất có cùng bộ tiêu chí host chấm và đầu vào prompt khác thật |
| `M_HOLDOUT_SCAN` | 5 | Số revision trước tối đa được xét khi tìm tình huống giữ riêng |
| Chi phí phép thử | 2 × số tình huống (A3: 4 lượt) | Phải nằm trong phần khám phá còn lại |
| Ngân sách trọn vòng | `calls_used + trial_cost + 1 + AUTO_RESERVE_CALLS <= budget_calls` | Thêm 1 lượt làm sản phẩm được giữ sẵn và lượt dự phòng; thiếu thì `skipped/budget` |

## 9. Chốt dừng và giữa lượt

| Sự kiện | Làn P | Làn M |
|---|---|---|
| Owner tạm dừng mục tiêu | Không ảnh hưởng | Lý do bị gác; phép thử đang chạy dừng ở cổng lượt kế tiếp, kết luận `inconclusive/stopped`, hoàn phần chưa chạy (M5) |
| Tắt trợ lý | Không tạo đề xuất mới; bài học `active` vẫn áp (owner đã quyết; tin bắt buộc vẫn đầy đủ) | Như pause; ngoài ra version trợ lý đổi nên áp dụng bị chặn trong giao dịch (A1) |
| Guard nhảy | Không ảnh hưởng | Chặn ở cổng lượt và trong giao dịch áp dụng (M5) |
| Huỷ mục tiêu | Không ảnh hưởng | Lý do bị xoá cùng mục tiêu (A2); phép thử dừng ở cổng |
| Hết hạn mức | Không ảnh hưởng | Không đủ ngân sách trọn vòng: không chạy, bài học `skipped/budget` |
| Owner bấm Bỏ qua bài học đang thử | Không áp dụng (làn P không có thử) | Dừng ở cổng lượt kế tiếp; nếu đã tới bước chốt thì CAS bài học trong `finish_experiment` chặn việc đổi cách làm (mục 6.4). Lượt đã bắt đầu vẫn tính; lượt giữ làm sản phẩm được trả |
| Owner thu hồi | Lần dựng tin kế tiếp dùng mặc định | `revert_method` và trả lượt giữ cùng giao dịch |
| Lần thức bị huỷ trước engine | Không liên quan | Lượt giữ về `held`, lý do trở lại chờ, không trả bộ đếm hai lần (mục 6.8) |
| Sửa cách hiểu | Không ảnh hưởng | Bài học `out_of_scope`, trả lượt giữ, cách làm về mặc định (mục 6.7) |
| Trần chung `JAVIS_RESONANCE_CALL_CEILING` | Không liên quan | Kiểm trong giao dịch giữ chỗ (M5, không đổi) |

## 10. API

Mọi route mới đi qua `_ctx(brain)` và principal owner như M4; agent không gọi được.

| Route | Thân | Trả | Lỗi |
|---|---|---|---|
| `POST /resonance/reactions?brain=` | `message_ref` (`msg:<phiên>:<id>`), `value` (`up`/`down`/`none`), `reason` (với `down`), `nonce` | `reaction` (giá trị hiện tại, `seq`), `proposal` (đề xuất vừa tạo, nếu có) | 400 tin không phải tin báo của trợ lý; 404 phiên hay tin không thuộc brain; 409 trợ lý đã xoá hay nội dung tin đã đổi |
| `GET /resonance/lessons?brain=&agent_key=` | | Bài học của trợ lý theo làn và trạng thái, kèm bằng chứng (đã đánh dấu mồ côi), bản xem trước làn P, liên kết phép thử làn M; thống kê reaction 30 ngày | 404 |
| `POST /resonance/lessons/{id}/decision?brain=` | `action` (`apply` / `dismiss` / `revoke`), `expected_status`, `expected_updated_at` | Bài học sau quyết định, kèm cấu hình có hiệu lực hiện tại | 409 trạng thái đã đổi (ví dụ Bỏ qua khi phép thử đã áp dụng: trả `status='active'` để giao diện đổi sang Thu hồi), hay cấu hình nền đã đổi (đề xuất thành `stale`); 400 hành động không hợp với làn hay trạng thái (`apply` chỉ cho làn P `proposed`; `dismiss` cho `proposed`/`trial_pending`/`trialing`; `revoke` cho `active`). `apply` đòi `expected_status` và `expected_updated_at`; `dismiss` chỉ đòi trạng thái hiện tại thuộc tập cho phép |
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
- `drain_outbox`: thêm một truy vấn bài học `active` của một trợ lý mỗi tin, theo chỉ mục `lessons_active_one`.
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
| G3a | Gửi 10 request `down/too_long` trên cùng một tin, mỗi request một nonce mới (API đặt giá trị, không tự đảo) | Một dòng `reactions`, `seq` 10, 10 dòng log, giá trị cuối `down/too_long`; bộ học đếm 1 tin; không đề xuất |
| G3d | Luật bấm lại của giao diện: bấm 👎 Dài quá, bấm lại đúng nút đó, bấm lần ba | Test JS: request lần hai mang `value='none'`, lần ba mang lại `down/too_long`; phía kho: giá trị cuối `down/too_long`, `seq` 3 |
| G3b | Gửi lại cùng `nonce` | Không dòng log mới; trả cùng `seq` |
| G3c | Thu hồi rồi khởi động lại: 2 tin `too_long` tạo đề xuất; thu hồi một reaction; `reopen()`; bấm reaction khác | Không có đề xuất thứ hai (chỉ mục duy nhất); đề xuất cũ hết hạn khi chỉ còn 1 tin hợp lệ |
| G4a | Ứng viên thua: phép thử trả `rejected/regression` | `method_ref` không đổi; bài học `rejected`; lượt giữ làm sản phẩm được trả trong cùng giao dịch (`calls_used` = trước + 4); không lý do `method_followup`; không tin `method_changed` |
| G4b | Ứng viên chưa rõ: một bên `unknown` | `inconclusive`; cách làm giữ; bài học `unknown`; lượt giữ được trả |
| G4c | Đề xuất làn P hết hạn (đồng hồ giả qua 14 ngày) | Trạng thái `expired`; tin vẫn dựng `full` |
| G5a | Thu hồi làn P: bài học `brief` active, thu hồi, gửi tin `goal.succeeded` kế tiếp | Câu đầy đủ như mặc định; biên nhận ghi `presentation=full` |
| G5b | Thu hồi làn M (trước và sau lượt làm sản phẩm) | `effective_method` = cách cũ trong cùng giao dịch; bài học `revoked`; lượt giữ còn `held` thì được trả và lý do `method_followup` được chốt; lượt việc kế tiếp dùng prompt không có phần thêm của ứng viên |
| G6a | Pause giữa phép thử: engine giả đặt pause ngay sau lượt baseline đầu tiên (phép thử 4 lượt cộng 1 lượt giữ) | Các lượt còn lại không chạy; `inconclusive/stopped`; 1 lượt đã tính, hoàn 3 lượt thử chưa ghi ý định, trả 1 lượt giữ: `calls_used` = trước + 1 |
| G6b | Tắt trợ lý giữa phép thử | Như G6a; áp dụng bị chặn kể cả khi tắt ngay trước giao dịch áp dụng |
| G6c | Guard nhảy giữa phép thử | Như G6a; chốt guard giữ nguyên |
| G6d | Hạn mức không đủ trọn vòng lúc lý do tới hạn (hạn mức bị owner hạ, hay trần chung) | 0 lượt model; bài học `skipped/budget`; `calls_used` không đổi; không tạo phép thử |
| G6e | Owner bấm Bỏ qua khi bài học đang `trialing`, giữa hai lượt | Dừng ở cổng lượt kế; lượt đã bắt đầu vẫn tính; xem thêm R1 cho khe trước giao dịch chốt |
| G7a | Không lý do hợp lệ thì 0 lượt: 50 reaction, 20 tick, không có bế tắc | Engine giả 0 lượt; `wake_reasons` và `wakeups` không đổi so với trước khi bấm |
| G7b | Bế tắc vì `reserve` (không phải `stalled`) | Không đề xuất; 0 lượt |
| G7c | Revision không có tiêu chí host chấm được | Bài học `skipped/untestable`; 0 lượt |

### 13.2 Bổ sung theo thiết kế

| ID | Kịch bản | Kiểm |
|---|---|---|
| A1 | Luồng làn P đủ: 2 tin `too_long` → đề xuất → xem trước → Áp dụng → tin `goal.succeeded` kế tiếp | Câu `brief`; tin bắt buộc (`goal.guard`, `goal.stalled`) vẫn đầy đủ |
| A2 | Tắt chuông: bài học `quiet` active | `goal.maintained` gửi với `quiet=True`; `goal.deadline_passed`, `goal.monitoring_lost` vẫn rung chuông |
| A3 | Ít làm phiền không đổi lịch | `wakeups`, lịch quan sát guard, lịch hạn chót giống hệt trước và sau khi áp dụng làn P |
| A4 | (thay bằng R3a) | |
| A5 | Tin mới thắng phép thử | Góp ý tới trước tick: lượt sửa dùng cách cũ; lý do `method_trial` chốt `superseded`; bài học `skipped/new_feedback` |
| A6 | "Hiểu chưa đúng" sau khi có đề xuất | Lý do bị gác; không chạy; áp dụng bị chặn nếu đang chạy |
| A7 | Đổi revision sau khi áp dụng | Bài học `out_of_scope`; `effective_method` mặc định |
| A8 | Học không ghi quyền | Hash file trợ lý, các dòng `resonance_agents` và `config_version` giống hệt trước và sau mọi ca của 13.1, 13.2 |
| A9 | Nguồn bị xoá hay bị sửa | Xoá tin (biên nhận mất) hay sửa nội dung: reaction mồ côi, không đếm; bài học đã áp dụng vẫn áp, danh sách hiện "nguồn đã xoá" |
| A10 | Phản hồi muộn | Reaction trên tin của revision cũ và của mục tiêu đã huỷ: ghi, tính cho làn P, mục tiêu không đổi |
| A11 | Trợ lý tắt | Reaction ghi được, không đề xuất; bật lại rồi bấm thêm thì đề xuất xuất hiện |
| A12 | Quay về 0.88.1 | Mở kho A3 bằng mã `83bff6bc` (git archive): không lỗi; lý do `method_trial` và `method_followup` không gọi model; cách làm làn M vẫn đúng phạm vi; lượt giữ `held` vẫn tính trong `calls_used` |
| A13 | Di chuyển | Kho 0.88 lên 0.89: có `.pre-a3.bak`; bảng cũ không đổi cột; mở lần hai không sao lưu lại |
| A14 | Chạy lại sau khi chết giữa phép thử | Xem R5e |
| A15 | Giao diện | Test JS: hàng reaction chỉ vẽ trên tin có biên nhận; request mang `nonce`; bấm lại đúng giá trị gửi `none`; khoá `tw()` nguyên văn; `test_i18n.mjs` xanh |
| A16 | Không ký tự gạch dài | Mọi chuỗi mới trong code, i18n, tài liệu |

### 13.3 Ca theo review vòng 1

Các ca này viết thành test hành vi trên mã A3 thật sau khi thiết kế đạt. Ca R1 chèn sự kiện bằng móc kiểm thử đặt **sau cổng cuối ngoài giao dịch và ngay trước `finish_experiment`**, không chỉ giữa hai lượt model.

| ID | Kịch bản | Kiểm |
|---|---|---|
| R1a | Bỏ qua thắng: phép thử eligible; móc chèn giao dịch Bỏ qua sau cổng cuối, trước `finish_experiment` | `method_ref` không đổi; bài học `dismissed`; phép thử `finished`, `inconclusive/lesson_dismissed`, `applied=0`; lượt đã gọi giữ nguyên trong `calls_used`; lượt giữ làm sản phẩm `released`; không lý do `method_followup`; không tin `method_changed` |
| R1b | Áp dụng thắng: `finish_experiment` commit trước, rồi gửi Bỏ qua với trạng thái cũ `trialing` | 409, `status='active'`; cách làm là ứng viên; sau đó Thu hồi: `revert_method` chạy, bài học `revoked`, lượt giữ `released`, lý do `method_followup` chốt |
| R1c | Bỏ qua lúc `trial_pending`, trước khi phép thử bắt đầu | `begin_experiment` không tạo phép thử, không giữ lượt nào (CAS `trial_pending` → `trialing` thất bại); 0 lượt model |
| R1d | Bài học bị sửa trạng thái ngoài luồng (giả lập `status='skipped'`) giữa hai lượt | Cổng lượt dừng; CAS chốt thất bại; cách làm giữ |
| R1e | `compare_methods` công khai, không truyền bài học | Hành vi M5 không đổi: bộ test M5 cũ xanh nguyên |
| R2a | Cấu hình `brief` đang `active` và đề xuất `full` `proposed` cùng tồn tại | Ghi cả hai không lỗi UNIQUE; tin `goal.succeeded` vẫn dựng `brief` trước khi owner quyết |
| R2b | Bỏ qua đề xuất `full` | Đề xuất `dismissed`; `brief` vẫn `active`; tin vẫn `brief` |
| R2c | Áp dụng đề xuất `full` | Trong một giao dịch: `brief` thành `superseded`, `full` thành `active`; đúng một dòng `active` cho khoá; tin kế tiếp dựng `full` |
| R2d | Owner thu hồi `brief` rồi mới bấm Áp dụng đề xuất `full` cũ | 409; đề xuất `stale`; cấu hình hiện tại là mặc định; không có dòng `active` nào được tạo |
| R2e | Owner áp dụng một đề xuất khác cùng khoá (nền đổi) rồi bấm Áp dụng đề xuất cũ | 409; đề xuất cũ `stale`; cấu hình đang dùng không đổi |
| R2f | Đề xuất thứ hai cho cùng khoá khi đã có một đề xuất chờ | Bộ học không tạo (chỉ mục chờ); khởi động lại không tạo thêm |
| R3a | Trọn vòng, hạn mức 9: 3 lượt việc không tiến → bế tắc → `method_trial` (tập thử + giữ riêng) → eligible → áp dụng → `method_followup` → lượt việc thật bằng cách mới → đăng sản phẩm → host chấm | Prompt lượt sản phẩm có phần thêm của ứng viên; sản phẩm đăng qua cổng bàn giao, assessment đúng revision; `calls_used` = 8 (3 + 4 + 1); còn 1 lượt dự phòng; A2 không tự thử lại; tin `method_changed` gửi sau lượt sản phẩm, kèm kết quả |
| R3b | Hạn mức mặc định 6, bế tắc ở 3 | Bài học `skipped/budget`; 0 lượt model; `calls_used` = 3; không tạo phép thử; thẻ hiện lý do |
| R3c | Đủ hạn mức nhưng không có revision trước cùng bộ tiêu chí | `skipped/no_holdout`; 0 lượt model |
| R3d | Sửa cách hiểu sau khi áp dụng, trước lượt sản phẩm | Revision mới: `effective_method` mặc định; bài học `out_of_scope`; lượt giữ `released` (`calls_used` trừ 1); lý do `method_followup` của revision cũ không chạy; lượt việc của revision mới dùng cách mặc định |
| R3e | Lịch xem lại và hạn chót sau khi áp dụng (lượt sản phẩm đã xong) | Lần thức `CHECK`: 0 lượt model |
| R3f | Tin mới từ người dùng cùng revision tới trước lượt sản phẩm | Lượt sửa tiếp quản lượt giữ (`attached`, rồi `used`), dùng cách mới; không giữ thêm lượt; lý do `method_followup` chốt `superseded`; `FOLLOWUP` không chạy; `calls_used` = 8 (3 + 4 + 1); engine giả: đúng 1 lượt sau phép thử |
| R3g | Khởi động lại giữa áp dụng và lượt sản phẩm | Lượt sản phẩm chạy đúng một lần; lượt giữ `used`; mở lại lần nữa không dựng lý do mới, không gọi model |
| R3h | Pause trước lượt sản phẩm, rồi resume | Lúc pause: lý do bị gác, 0 lượt, lượt giữ còn `held`; resume: lượt sản phẩm chạy một lần |
| R3i1 | Bản người dùng sửa tay đã được phát hiện **trước** khi `FOLLOWUP` mở lượt | A2 gác mục tiêu (`source_drift`): 0 lượt model; lượt giữ vẫn `held`; lý do chờ gỡ gác |
| R3i2 | Người dùng sửa tay **trong lúc** lượt sản phẩm đang chạy | Không ghi đè (A2 mục 5); đầu ra giữ ở vùng làm việc, chưa đăng; lượt giữ `used`; tin `method_changed` nói rõ chưa đăng được |

### 13.4 Ca theo review vòng 2

Mỗi ca R4 tới R6 kiểm đủ năm thứ: trạng thái và `gen` của lượt giữ, trạng thái action, `calls_used`, lý do đang chờ, số lượt engine giả. Bối cảnh chung: hạn mức 9, bế tắc sau 3 lượt việc, phép thử eligible 4 lượt, áp dụng, lượt giữ `held`, `calls_used` = 8.

| ID | Kịch bản | Kiểm |
|---|---|---|
| R4a | Trần chung đúng 8 (`JAVIS_RESONANCE_CALL_CEILING=8`); góp ý cùng revision tới trước `FOLLOWUP` | Lượt sửa nhận lượt giữ trong một giao dịch (mức tăng ròng 0, không bị trần chặn); `calls_used` = 8; engine 1 lượt; lượt giữ `used`; lý do `method_followup` `superseded`; `FOLLOWUP` không chạy thêm |
| R4b | Cùng trần 8; sửa cách hiểu (revision mới) rồi góp ý trên revision mới | Lượt giữ đã `released` khi `revise` (`calls_used` = 7); lượt của revision mới giữ lượt mới như thường (7 → 8, vừa trần); không mượn lượt giữ của revision cũ |
| R4c | Lượt giữ đã `used`; góp ý tiếp theo khi trần 8 và `calls_used` 8 | Lượt mới bị trần chặn như A2 hiện nay (0 lượt model); không mượn lại lượt giữ đã dùng |
| R4d | Cổng ngoài giao dịch: sau áp dụng `left` = 1, đúng bằng lượt dự phòng | `decide` không đòi phần dư trên lượt dự phòng cho `FOLLOWUP` (lượt đã giữ sẵn): chạy đúng 1 lượt bằng lượt giữ; sau đó `left` vẫn 1, lượt dự phòng còn nguyên |
| R5a | Huỷ lần thức `FOLLOWUP` sau pha chuẩn bị, trước engine (`abort_action`) | Action `cancelled/not_run`; lượt giữ về `held`, `gen` +1; `calls_used` vẫn 8 (không thành 7); lý do `method_followup` lại chờ; engine 0. Tick sau: chạy đúng 1 lượt, lượt giữ `used`, `calls_used` 8 |
| R5b | Gọi `abort_action` lần hai cho cùng action | Trả False; lượt giữ, bộ đếm, lý do không đổi |
| R5c | Huỷ trước engine một lượt góp ý đã tiếp quản lượt giữ | Lượt giữ `held`; lý do góp ý và lý do `method_followup` cùng trở lại chờ; `calls_used` 8. Tick sau: góp ý thắng và tiếp quản lại; `FOLLOWUP` không chạy; engine tổng 1 |
| R5d | Tiến trình chết sau khi lượt sản phẩm có thể đã gọi engine | Mở lại: `_reconcile` A2 chốt action; lượt giữ `used`; lý do chốt; không chạy lại; `calls_used` 8 |
| R5e | Tiến trình chết sau 2 trên 4 lượt của phép thử | Mở lại: phép thử `inconclusive/interrupted`, hoàn 2 lượt chưa ghi ý định; bài học `unknown`; lượt giữ `released`; `calls_used` = 3 + 2 = 5; không lý do `method_followup`; không phép thử thứ hai cho cùng cặp và revision |
| R6a | Chu trình A3 → 0.88 → A3: lượt giữ `held` và lý do chờ; chạy `tick` bằng mã `83bff6bc` thật (git archive) | Mã cũ: 0 lượt engine, lý do bị chốt, lượt giữ vẫn `held`, `calls_used` 8. Mở lại bằng A3: dựng đúng một lý do (`gen` +1, `source_ref` mới); tick: 1 lượt sản phẩm, lượt giữ `used`. Mở lại lần ba: không lý do mới |
| R6b | Như R6a, nhưng mã cũ đã huỷ mục tiêu | Mở lại bằng A3: lượt giữ `released` một lần (`calls_used` 7); không lý do chờ; engine 0; mở lại lần nữa không trả lần hai |
| R6c | Như R6a, nhưng mã cũ đã sửa cách hiểu (revision mới) | Lượt giữ `released`; bài học `out_of_scope`; cách làm mặc định; engine 0 cho lượt sản phẩm cũ |
| R6d | Như R6a, nhưng mã cũ đã `revert_method` | Cách làm có hiệu lực khác ứng viên: lượt giữ `released`; bài học `revoked`, lý do `reverted_outside`; engine 0 |
| R7a | Revision trước chỉ khác metadata (số revision, lý do sửa, thời điểm), cùng cách hiểu, lời người dùng, ràng buộc, giả định | `prompt_input_hash` trùng: không chọn làm giữ riêng; không còn ứng viên thì `skipped/no_holdout`, 0 lượt |
| R7b | Revision trước có cách hiểu và lời người dùng khác thật, cùng bộ tiêu chí host chấm | Được chọn; payload ghim hai `prompt_input_hash`, hash bản ghi revision và `rubric_hash`; prompt tình huống giữ riêng dựng từ revision cũ; action, cổng lượt, giao dịch áp dụng đều mang revision hiện tại; không file nào được đăng |
| R7c | Revision trước gần nhất chỉ khác metadata, revision cũ hơn nữa khác thật (trong `M_HOLDOUT_SCAN`) | Chọn revision cũ hơn |
| R7d | Revision trước khác thật nhưng bộ tiêu chí host chấm khác | Không chọn |

### 13.5 Không có trong nghiệm thu A3

- Pilot model thật: chỉ chạy khi chủ dự án duyệt hạn mức riêng. Đề xuất pilot sau khi mã đạt review: tối đa 8 lượt gọi model (3 lượt việc tới bế tắc, 4 lượt phép thử, 1 lượt làm sản phẩm), mục tiêu đặt hạn mức 9 để giữ lượt dự phòng, dùng engine hay gói thuê bao hiện có, một mục tiêu có revision trước cùng bộ tiêu chí để có tình huống giữ riêng. Không tự chuyển sang API trả phí, không tự thử lại hoặc nâng trần.
- Đo hiệu năng VPS: không thuộc A3.

## 14. Quyết định mặc định cần review

| # | Câu hỏi | Mặc định đề xuất | Phương án khác |
|---|---|---|---|
| D1 | Reaction gắn vào đâu | Chỉ tin báo do host ghi có biên nhận | Thêm câu trả lời của trợ lý trong phiên agent: cần nguồn tin đáng tin và một cách áp dụng không đi qua prompt chat; để sau |
| D2 | Ai áp dụng làn P | Owner bấm Áp dụng sau khi xem trước; im lặng thì hết hạn | Tự áp dụng sau N tin: nhanh hơn nhưng đổi hành vi dựa trên emoji, trái mục tiêu "không chạy theo emoji" |
| D3 | Làn M có tự chạy không | Tự chạy khi bế tắc khách quan, chỉ khi đủ ngân sách trọn vòng (phép thử, lượt làm sản phẩm giữ sẵn, lượt dự phòng) trong hạn mức đã cấp; qua đúng cổng A2/M5 (review vòng 1 đồng ý có điều kiện) | Chờ owner bấm Thử: thêm một bước mỗi lần bế tắc |
| D4 | Bộ tình huống làn M (**chốt lại sau review vòng 1**) | Giữ nguyên luật M5: có tập thử và giữ riêng. Giữ riêng duy nhất trong A3 là revision trước cùng bộ tiêu chí host chấm. Không có thì `skipped/no_holdout`. Mục tiêu mặc định 6 lượt luôn `skipped/budget` (mục 2, 6.3) | Bản vòng 1 bỏ holdout để vừa hạn mức: đã rút lại, vì vừa hạn mức không phải lý do đủ để giảm mức bằng chứng |
| D5 | Đầu ra phép thử thắng | Không đăng làm sản phẩm; một lượt làm sản phẩm bằng cách mới được giữ sẵn từ lúc bắt đầu phép thử và chạy đúng một lần (`method_followup`) | Tiếp nhận đầu ra thử qua cổng bàn giao: tiết kiệm một lượt, nhưng cần hợp đồng bàn giao của A4; để sau A4 |
| D6 | "Cần chỉnh" có mở làn M | Không, vì host không chấm được phép thử cho tiêu chí người dùng chấm | Phép thử chấm tay: người dùng chấm bản thử. Đây gần với đội review của A5 |
| D7 | Tin tuỳ chọn của làn P | `goal.succeeded`, `goal.maintained` được rút gọn; chỉ `goal.maintained` được tắt chuông | Rộng hơn: dễ giấu tin cần người dùng làm gì |

## 15. Kế hoạch code (sau khi thiết kế đạt review)

Mỗi bước một commit có test; chạy test cũ của M4, M5, A1, A2 sau mỗi bước.

1. **Kho:** bảng, chỉ mục, sao lưu `.pre-a3.bak`, `A3_TABLES`; test di chuyển và test khoá cột cũ (`resonance_store.py`).
2. **Reaction:** `record_reaction` (kiểm biên nhận, upsert, log, mồ côi), `POST /resonance/reactions`; nguồn tin cho phản hồi M4 (`resonance_store.py`, `resonance_api.py`, `main.py` truyền tra cứu `report_receipts` vào kho).
3. **Bộ học làn P:** hàm thuần `resonance_learning.py` (mới, không I/O, như `resonance_heartbeat.py`), vòng đời bài học, `GET /resonance/lessons`, `POST .../decision`.
4. **Áp làn P:** `PRESENTATION`, `notice_text(..., presentation)`, `drain_outbox` đọc bài học, `quiet` trong `_resonance_notify`, ghi `presentation` vào biên nhận.
5. **Làn M:**
   - đề xuất trong nhánh bế tắc, kiểm ngân sách trọn vòng và tình huống giữ riêng;
   - `heartbeat.v2` (`TRIAL`, `FOLLOWUP`, `method_trial`, `method_followup`);
   - tách thân `compare_methods`; `_trial_run` dựng prompt theo revision của từng tình huống;
   - CAS bài học trong `begin_experiment` và `finish_experiment`;
   - bảng `call_holds` và vòng đời mục 6.8: giữ, gắn (`FOLLOWUP` hay góp ý tiếp quản, mức tăng ròng 0 khi kiểm trần), dùng, trả; mở rộng `abort_action`; `reconcile_holds` khi mở kho và trong pha chuẩn bị;
   - chọn tình huống giữ riêng theo `prompt_input_hash`;
   - lượt làm sản phẩm qua khung lần thức A2 và cổng bàn giao hiện có;
   - `goal.method_changed` gửi sau lượt sản phẩm;
   - thu hồi kèm `revert_method`; `out_of_scope` và trả lượt giữ khi `revise`.
6. **Giao diện:** hàng reaction (`chat-resonance.js`), mục Bài học (`resonance-agent.js`), khối `learning` trên thẻ, i18n.
7. **Test:** `tests/python/test_resonance_a3_learning.py` (ma trận 13.1 tới 13.4; móc kiểm thử chèn quyết định ngay trước giao dịch chốt; R6 chạy `tick` bằng mã `83bff6bc` lấy qua git archive), `tests/python/test_resonance_a3_rollback.py` (`OLD_SHA` = `83bff6bc`), `tests/js/test_resonance_a3_ui.js`; CI lấy thêm commit `83bff6bc` cho test quay về.
8. **Tài liệu:** hướng dẫn `docs/dev/resonance-a3-learning.md`, biên bản `docs/dev/resonance-a3-verification.md`, lộ trình mục 6 và mục 8.

## 16. Phần chuyển sang A4, A5

- **A4:** tiếp nhận đầu ra thắng của phép thử làm sản phẩm (D5) sẽ dùng hợp đồng bàn giao chung.
- **A5:** phép thử chấm tay cho tiêu chí người dùng chấm (D6) gần với vai reviewer; review là một nguồn bằng chứng theo loại tiêu chí, không thay kiểm khách quan.

## 17. Thay đổi sau review vòng 1 (`a6418e45`)

Review: `exports/reviews/PR-598-A3-design-a6418e45-review.md` (ngoài git), kèm script kiểm độc lập trên SQLite thật, kho A2 thật với engine giả và giao dịch M5 thật.

| Điểm review | Sửa ở đâu | Cách sửa |
|---|---|---|
| **P1:** Bỏ qua bài học không được chốt trong giao dịch đổi cách làm; còn khe giữa cổng cuối và `finish_experiment` | Mục 6.4, 6.5, 9, 10; ca R1a tới R1e | Truyền `lesson_id` vào `begin_experiment` và `finish_experiment`. CAS `trial_pending` → `trialing` khi giữ chỗ, CAS `trialing` → `active` trước `_set_method` trong cùng giao dịch chốt. CAS thất bại thì giữ cách cũ, giữ quyết định Bỏ qua, tính lượt đã gọi, hoàn phần chưa gọi, trả lượt giữ. Thứ tự theo commit của `BEGIN IMMEDIATE`: Bỏ qua trước thì áp dụng thua; áp dụng trước thì Bỏ qua cũ nhận 409 `active` và giao diện chuyển sang Thu hồi |
| **P2:** chỉ mục chống trùng gộp `active` với `proposed`, chặn chính đề xuất đổi một sở thích đang dùng | Mục 5.2, 7.1, 10; ca R2a tới R2f | Hai chỉ mục duy nhất từng phần: một cho `active`, một cho đề xuất đang chờ. Đề xuất ghi `base_lesson_id` và `from_value`; Áp dụng kiểm nền trong cùng giao dịch, nền đổi thì `stale` và 409. Cấu hình đang dùng không bị vô hiệu hoá để lưu đề xuất |
| **P2:** sau phép thử thắng, câu "lượt kế tiếp do sửa cách hiểu hay lịch xem lại dùng cách mới" sai với A2/M5; chi phí làm sản phẩm chưa được hoạch định | Mục 2, 6.3, 6.5, 6.6, 6.7; ca R3a tới R3i | Bỏ câu sai. Thêm ngân sách trọn vòng; giữ sẵn một lượt làm sản phẩm (`call_holds`) trong giao dịch giữ chỗ phép thử; lý do `method_followup` (lớp `FOLLOWUP`) chạy đúng một lượt việc bằng cách mới qua cổng bàn giao hiện có. Nói rõ: sửa cách hiểu tạo revision mới nên cách vừa học hết hiệu lực; lịch xem lại là `CHECK`, không gọi model |
| **D4** chưa đạt: bỏ holdout chỉ để vừa hạn mức | Mục 6.2, 14 | Giữ luật M5. Nguồn giữ riêng hợp lệ duy nhất là revision trước cùng bộ tiêu chí; không có thì `skipped/no_holdout`. Ghi rõ mức bằng chứng và giới hạn; mục tiêu mặc định 6 lượt luôn bỏ qua làn M |
| D3, D5 đồng ý có điều kiện | Mục 14 | D3 gắn với ngân sách trọn vòng; D5 giữ, kèm lượt làm sản phẩm được giữ sẵn |

Các phần review đồng ý giữ nguyên: ranh giới reaction và M4, D1, D2, D6, D7, làn P không tốn model, phạm vi goal + revision kèm đường quay lại.

## 18. Thay đổi sau review vòng 2 (`ef56b61f`)

Review: `exports/reviews/PR-598-A3-r2-ef56b61f-review.md` (ngoài git). Ba điểm vòng 1 được chấp nhận ở cấp thiết kế; còn 2 P2 trên cơ chế giữ lượt.

| Điểm review | Sửa ở đâu | Cách sửa |
|---|---|---|
| **P2-1:** góp ý thay `FOLLOWUP` giữ lượt mới trước rồi mới trả lượt cũ, nên bị trần chung chặn ở 8/8 | Mục 6.3, 6.5, 6.7, 6.8; ca R3f, R4a tới R4d | Góp ý cùng revision **tiếp quản** lượt `held` hợp lệ trong một giao dịch `begin_action`: ghi action, chuyển lượt giữ sang `attached`, chốt lý do `method_followup`. Mức tăng ròng 0 khi kiểm trần chung và trần mục tiêu. Cổng ngoài giao dịch coi lượt giữ là dùng được. Lượt giữ của revision cũ hay đã dùng không bao giờ được mượn lại |
| **P2-2a:** huỷ trước engine trả bộ đếm nhưng lượt giữ kẹt `used` | Mục 6.8, 9; ca R5a tới R5c | Tách `attached` (đã gắn action) khỏi `used` (model có thể đã chạy). `abort_action` với action dùng lượt giữ: không trừ bộ đếm, lượt giữ về `held`, `gen` +1, lý do trở lại chờ. Huỷ lặp không làm gì |
| **P2-2b:** bản 0.88 chốt lý do `method_followup` mà không đụng lượt giữ; nâng lại không có gì dựng lại lịch | Mục 6.8, 7.3; ca R5d, R5e, R6a tới R6d | `reconcile_holds` chạy khi mở kho và trong pha chuẩn bị mỗi lần thức: dựng lại đúng một lý do (`source_ref = hold:<id>:<gen>`) cho lượt giữ còn hợp lệ; trả đúng một lần lượt không còn hợp lệ (huỷ, sửa cách hiểu, quay lại cách cũ, phép thử bị ngắt); không cấp lại lượt khi model có thể đã chạy |
| Holdout lịch sử: phải kiểm đầu vào khác thật | Mục 6.2, 8; ca R7a tới R7d | `prompt_input_hash` từ phần dựng prompt ngoài tiêu chí; trùng với tập thử thì bỏ qua và xét revision cũ hơn trong `M_HOLDOUT_SCAN`. Ghim hash hai bản ghi và `rubric_hash`. Revision lịch sử chỉ dùng dựng prompt, không đi vào cổng giữ lượt hay áp dụng |
| Lưu ý: G6a mang số của thiết kế một tình huống | Ca G6a | Kỳ vọng theo số lượt đã bắt đầu: 1 tính, hoàn 3, trả 1 lượt giữ |
| Lưu ý: G3a mâu thuẫn luật bấm lại | Mục 3.3; ca G3a, G3d | API đặt giá trị theo request; luật bấm lại là của giao diện (gửi `none`). Tách test gửi lặp khỏi test bấm lại |
| Lưu ý: §12 còn tên chỉ mục cũ | Mục 12 | `lessons_active_one` |
| Lưu ý: R3i gộp hai tình huống sửa tay | Ca R3i1, R3i2 | Phát hiện trước khi mở lượt: gác, 0 lượt model. Sửa trong lúc chạy: giữ đầu ra chưa đăng |

Không mở thêm tính năng: hai làn, D1 tới D7 và các sửa vòng 1 giữ nguyên.

## 19. Ghi chú triển khai (sau khi thiết kế đạt tại `d6239d54`)

Hành vi, quyền, ngân sách và chuẩn bằng chứng giữ đúng thiết kế đã chốt. Các chỗ dưới đây là cách hiện thực hoá hay một chỗ thêm mà test trên mã thật buộc phải có; reviewer mã xét lại từng chỗ.

| # | Chỗ | Thiết kế ghi | Mã làm | Lý do |
|---|---|---|---|---|
| I1 | Danh tính bài học trong giao dịch chốt | `finish_experiment(..., lesson_id)` | `begin_experiment(..., lesson_id)` như thiết kế; `finish_experiment` tìm bài học theo `experiment_id` ngay trong giao dịch chốt | Cùng một danh tính (bài học ghi `experiment_id` ở bước giữ chỗ). Nhờ vậy đường đối soát A2 (`_reconcile`, chốt phép thử bị ngắt) không phải truyền thêm tham số mà vẫn chạy CAS bài học. Phép thử không có bài học (`compare_methods` công khai) giữ hành vi M5 |
| I2 | Lần thức sau khi phép thử bị ngắt | Mục 6.8 nói đối soát chốt phép thử dở | Thêm một hẹn `trial_recovery` (lớp kiểm, không gọi model, nghĩa vụ riêng `trial`) ở lúc khoá của phép thử hết hạn; phép thử xong bình thường thì chỉ đúng hẹn đó được chốt theo id. Bản đầu dùng `action_recovery` rồi bỏ cả nghĩa vụ `check`, làm mất `guard_recheck` (review mã vòng 1, P2-1) | Test R5e trên mã thật cho thấy phép thử bị ngắt không để lại lịch nào (lý do đã phục vụ, lượt thử không có hẹn phục hồi), nên không lần thức nào đối soát, lượt giữ kẹt `held`. Đây là lỗi thật của hợp đồng, không phải chỉ của test |
| I3 | Nguồn của reaction | `message_ref` | Nhận `message_ref`, hoặc bộ ba (phiên, khoá báo cáo, mục tiêu) có sẵn trong khối thẻ; server tra bộ ba qua biên nhận `report_receipts` rồi kiểm như `message_ref` | Phần tử tin trong khung chat không mang id tin của kho phiên. Mọi kiểm (biên nhận, vai `assistant`, khối thẻ khớp khoá, brain, mục tiêu) giữ nguyên |
| I4 | Nút Bỏ qua lần thử trên thẻ | Mục 11 nêu nút Quay lại cách cũ | Thẻ có thêm nút Bỏ qua lần thử khi bài học đang `trial_pending`/`trialing`, gọi đúng route quyết định của mục 10 | Mục 9 và 10 đã có hành động Bỏ qua cho hai trạng thái này; thẻ là chỗ người dùng thấy phép thử đang chờ |
| I5 | Ca R5e | Ví dụ "sau 2 trên 4 lượt" | Test ngắt ở lượt thử thứ 3 và kiểm theo công thức `calls_used = 3 + số lượt thử đã ghi ý định` | Lượt đã ghi ý định thì model có thể đã chạy nên vẫn tính; công thức là bất biến cần khoá, con số chỉ là ví dụ |
| I6 | Test giao diện A2 | Không nói | `tests/js/test_resonance_a2_ui.js` đổi số mã lý do có nhãn từ 20 thành 22 | A3 thêm đúng hai mã `method_trial`, `method_followup` (mục 6.3); test vẫn kiểm mọi mã có nhãn ở hai thứ tiếng |
| I7 | Đề xuất làn P hết hạn | Ghi bù lúc có reaction mới hay khi mở danh sách | Như thiết kế; thêm hết hạn khi số tin làm căn cứ còn sống tụt dưới ngưỡng (`evidence_gone`) | Mục 3.4 nói đề xuất mất đủ số tin thì tự hết hạn |
| I8 | Phép thử trên event loop | Không nói | Mọi bước kho, file, bằng chứng của phép thử chạy ở luồng phụ, luôn chờ xong kể cả khi bị huỷ; lượt thử đã ghi ý định mà bị huỷ trước engine được chốt `not_run` và hoàn khi đối soát; bốn route A3 chạy phần kho ở luồng phụ | Review mã vòng 1, P2-3: phép thử nay do scheduler tự mở nên không được làm mất tính chất không chặn của A2 |
| I9 | Áp dụng đề xuất làn P | Hạn 14 ngày, mất căn cứ thì hết hạn | Kiểm hạn và căn cứ còn sống NGAY trong giao dịch Áp dụng (đồng hồ host), không chỉ khi đọc danh sách | Review mã vòng 1, P2-2 |
| I10 | Lỗi file hệ thống sau khi giữ chỗ | Không nói | Giao dịch giữ chỗ tách khỏi bước tạo thư mục phép thử. Thư mục lỗi sau commit thì phép thử được chốt `inconclusive/stopped` (hoàn mọi lượt đã giữ); chốt cũng lỗi thì phép thử còn `running` và hẹn `trial_recovery` được giữ (chỉ chốt hẹn khi không còn phép thử `running`). Lỗi trước commit ghi `storage_error`, không ghi nhầm là lỗi quyền | Review mã vòng 2, P2-1 |
| I11 | Ghim quyền trợ lý của phép thử | Không nói | Đọc sổ đăng ký agent (`_agent_intent`) chạy ở luồng phụ như mọi bước kho khác | Review mã vòng 2, P2-2 |
| I12 | Phiên của hàng phản hồi | I3: bộ ba (phiên, khoá báo cáo, mục tiêu) | Trang gửi phiên TRỐNG; server tra biên nhận theo khoá báo cáo và mục tiêu, chỉ dùng khi có đúng một biên nhận. Phiên ghi rõ thì vẫn kiểm chặt như cũ (sai phiên 400) | Soi giao diện trên sandbox: lúc vẽ tin, phiên "đang mở" ở trang Cộng sự có thể chưa có hay còn là phiên của trợ lý trước, server từ chối và hàng phản hồi biến mất. Khoá `outbox:<id>` chỉ thuộc một tin, nên bỏ phiên không nới quyền: brain, vai, khối thẻ vẫn kiểm |
| I13 | Mục Bài học sau khi phản hồi | Mục 11: dòng "xem ở trang trợ lý" | Phản hồi ghi xong thì trang chat phát sự kiện `javis:resonance-lessons`; ngăn trợ lý đang mở tải lại mục Bài học | Soi giao diện: không tải lại thì ngăn trợ lý vẫn ghi "Chưa có bài học" tới khi F5 |
| I14 | Hiển thị mục Bài học | Mục 11 | Câu xem trước bỏ cú pháp liên kết markdown; bài học cách làm hiện nhãn dịch (`to_label`) và cách hiểu của mục tiêu (`goal_label`); phép thử đang chờ có khối riêng kèm nút Bỏ qua; ghi chú xung đột 409 giữ qua lần tải lại | Soi giao diện: trước đó hiện `[Inbox/p.md](Inbox/p.md)`, mã `work.checklist.v1`, và ghi chú 409 mất ngay khi danh sách vẽ lại |
| I15 | Thời gian chờ sau Thu hồi | Mục 5.3: chỉ Bỏ qua chặn đề xuất lại | `learning.v2`: kho đưa cả bài học `revoked` của làn trình bày vào danh sách chặn; `P_REVOKE_COOLDOWN_S` 14 ngày | Soi giao diện (ảnh d06) thấy phản hồi cũ đề xuất lại đúng thay đổi vừa thu hồi; review khuyến nghị dùng chung quy tắc 14 ngày, chủ dự án chốt |

