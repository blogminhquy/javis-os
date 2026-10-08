# Resonance A2: nhịp tim thích nghi theo lý do

**Trạng thái:** thiết kế để review, chưa có mã A2. Nhánh `claude/resonance-a2-heartbeat`, đặt số 0.88.0.

- **Nền:** nhánh A1 `claude/resonance-a1-agent-scope` tại `077bcf73` (0.87.0, chưa merge). A2 dùng `agent_gate` và sổ trợ lý của A1, nên nhánh chồng lên A1. A1 merge thì nhánh này rebase lên `main`.
- **Lộ trình:** [agent scope roadmap](2026-10-08-resonance-agent-scope-roadmap.md), mục 5.
- Không gọi model để làm thiết kế này. Chưa có pilot A2; nếu cần, gói duyệt riêng ở mục 12.

## 1. Mục tiêu và ngoài phạm vi

**Mục tiêu:** trợ lý chỉ thức khi có lý do cụ thể. Chỉ gọi model khi có thông tin mới hoặc bước tiếp theo thật sự có ích. Đang chờ thì ngủ. Mỗi lần thức đều ghi lại lý do và quyết định.

**Giữ nguyên:**
- Một scheduler duy nhất: `tick` trong vòng lặp nền 30 giây, nhận lịch bằng CAS (`claim_wake`), khoá lượt (`claim_lease`), đối soát sau khi chết giữa chừng (`_reconcile`).
- Cổng `_gate`, cổng bàn giao, hạn mức lượt gọi, outbox chống báo lặp.
- Bảng cũ không đổi cột (test `PRE_A1` vẫn khoá). A2 chỉ thêm bảng phụ.

**Ngoài phạm vi:**
- Học từ reaction và phản hồi: để A3.
- Adapter nguồn sự kiện ngoài như MCP, webhook hay theo dõi file theo thời gian thực. A2 chỉ phát hiện thay đổi bằng code, khi kiểm định kỳ.
- Đường giao việc từ chat thường sang trợ lý.
- Hạn mức theo trợ lý hay theo ngày: mục 13, câu 3.

## 2. Hiện trạng và khoảng trống (mã tại `077bcf73`)

| # | Hiện trạng | Hệ quả |
|---|---|---|
| G1 | `tick` gọi `advance(..., {"kind": "wake"})` cho mọi lịch `work`. Lý do chỉ là câu chữ trong `wakeups.reason`, bị ghi đè mỗi lần hẹn | `advance` không biết vì sao mình thức, nên không phân biệt được "có tin mới" với "tới giờ xem lại" |
| G2 | Mọi lần thức `wake` mà kết quả chưa đạt và không chỉ chờ người dùng đều vào `_work_step`, tức là gọi model. Gồm cả lần xem lại có giới hạn (`_bounded_review`, 6 đến 24 giờ), lần kiểm lại sau khi trợ lý được bật lại, và lần phục hồi sau lượt bị ngắt | Gọi model khi không có gì mới, lặp tới hết hạn mức |
| G3 | `RETRY_NOT_MET_S` 15 phút lặp tới hết hạn mức, không xét lần thử trước có tiến bộ không | Tốn lượt khi bế tắc |
| G4 | `ERROR_BACKOFF_S` dừng ở 24 giờ rồi lặp mãi (`min(i, len-1)`). Số lần lỗi đếm trên mọi revision | Lỗi cố định vẫn gọi model mỗi ngày tới hết hạn mức |
| G5 | `due_wakeups` bỏ qua mục tiêu đang tạm dừng, nên lịch `observe` cũng dừng. `_gate` trả về sớm (trợ lý tắt, tạm dừng, cách hiểu bị bác) trước khi hẹn lại `observe` | Tạm dừng thì mất theo dõi guard mà không ai biết. Trợ lý tắt thì guard thôi được theo dõi lặng lẽ |
| G6 | Không có sổ ghi các lần thức. `goal_events` chỉ ghi khi `run_state` đổi | Không trả lời được "vì sao lúc 3 giờ sáng nó gọi model" |
| G7 | Thẻ mục tiêu hiện `next_wake.reason` là câu tiếng Việt thô, giao diện tiếng Anh cũng thấy | Lệch i18n |
| G8 | Lượt chat vừa lập mục tiêu vẫn gọi được `javis_schedule` tạo loop hay nhắc hẹn cho cùng việc | Hai bên cùng quản lịch một việc |

## 3. Lý do thức

Mọi chỗ hẹn lịch truyền một **mã lý do**. Kho ghi mã đó vào bảng phụ `wake_reasons` cùng giao dịch với `wakeups`. Nhiều lý do dồn vào cùng một lịch (cùng `goal_id`, `kind`) thì gộp: một lần thức xử lý tất cả, và chỉ một hành động logic.

| Mã | Từ đâu (mã hiện có) | Lớp |
|---|---|---|
| `created` | `create` | bước đầu |
| `revised` | `revise`, `drop_directive`, revision đổi giữa lượt | bước đầu (revision mới) |
| `handoff_wait` | `create`/`revise` khi lập trong lượt chat; `advance` chờ bàn giao | chỉ kiểm |
| `handoff_done` | `finish_handoff` | chỉ kiểm, rồi bước đầu nếu chat không để lại bản |
| `feedback` | `record_feedback`, trừ cách hiểu bị bác | tin mới |
| `user_schedule` | `advance` với `user_schedule` | tin mới |
| `resumed` | `set_paused(False)`, `clear_block` | chỉ kiểm (đăng đầu ra đã có) |
| `assigned` | `assign_goal` | chỉ kiểm, rồi bước đầu nếu chưa làm |
| `agent_enabled` | `wake_agent_goals` | chỉ kiểm, rồi bước đầu nếu chưa làm |
| `agent_recheck` | `_gate` khi trợ lý tắt, mất file, nghỉ | chỉ kiểm |
| `agent_changed` | công tắc đổi trong lúc model chạy | chỉ kiểm (xét lại đầu ra theo quyền hiện tại) |
| `guard_recheck` | `_gate` khi guard chưa xác định | chỉ kiểm |
| `recovery` | `begin_action` (lịch phục hồi nếu lượt bị ngắt) | chỉ kiểm, rồi theo luật lỗi |
| `retry_not_met` | chính sách (mục 4) | thử lại tự động |
| `error_retry` | chính sách (mục 4) | thử lại tự động |
| `source_changed` | kiểm định kỳ thấy sản phẩm đã đăng bị đổi (mục 4) | tin mới |
| `review` | xem lại có giới hạn, chân trời `review`/`deadline`/`maintain` | chỉ kiểm |
| `guard_observe` | lịch `observe` | quan sát guard |

Mã lạ (bản sau ghi, bản này đọc) coi như `review`: chỉ kiểm, không gọi model.

## 4. Chính sách `heartbeat.v1`

Một hàm thuần `decide(goal, pending, history, assessment, now, policy) -> Decision`, trong module mới `server/resonance_heartbeat.py`. Không I/O, test bằng đồng hồ giả.

**Đầu vào:**
- `pending`: các lý do chưa xử lý;
- `history`: các lượt việc của revision hiện tại cùng đánh giá sau mỗi lượt;
- `assessment`: kết quả đánh giá bằng code ngay lúc thức;
- `goal`: hạn mức còn lại, chân trời, chế độ, giai đoạn.

**Đầu ra:**
- `action`: `work` (một lượt model), `evaluate` (chỉ code: đăng đầu ra đã có, đánh giá, hẹn tiếp), `observe` hay `sleep`;
- lịch kế tiếp, kèm mã lý do;
- `why`: một câu ghi vào sổ.

### Khi nào được gọi model

Đi qua `_gate` rồi, `work` chỉ được chọn khi kết quả chưa đạt, không phải chỉ còn chờ người dùng, và có **một** trong ba điều kiện:

1. **Bước đầu:** revision hiện tại chưa có lượt việc nào, cũng chưa có bản tiếp nhận từ chat.
2. **Tin mới:** có lý do lớp "tin mới" (`feedback`, `user_schedule`, `source_changed`) ghi SAU lượt việc gần nhất của revision này.
3. **Thử lại tự động** còn được phép:
   - `retry_not_met`: chuỗi bế tắc `stall` nhỏ hơn `STALL_AFTER`, và lượt còn lại lớn hơn `AUTO_RESERVE_CALLS`.
   - `error_retry`: số lỗi của revision này (tính từ tin mới gần nhất) nhỏ hơn `ERROR_MAX_ATTEMPTS`, và mã lỗi không thuộc nhóm cố định.

Ngoài ba điều kiện trên, mọi lần thức là `evaluate`, `observe` hay `sleep`: **0 lượt model**.

- **Tiến bộ:** số tiêu chí đạt sau lượt mới lớn hơn sau lượt trước, trong cùng revision.
- **Chuỗi bế tắc** (`stall`): số lượt việc liên tiếp không tiến bộ, tính từ tin mới gần nhất. Tin mới đặt lại về 0.
- **Lượt còn lại** = `budget_calls - calls_used`. Thử lại tự động không dùng `AUTO_RESERVE_CALLS` lượt cuối, để dành cho lúc người dùng góp ý. Bước đầu và tin mới vẫn dùng được các lượt đó.

### Hẹn lịch kế tiếp

| Tình huống | Lịch | Mã |
|---|---|---|
| Chưa đạt, còn được thử lại | `RETRY_BASE_S × 2^stall` | `retry_not_met` |
| Chưa đạt, hết lượt thử tự động | Không hẹn `work`. `waiting`/`stalled`, báo **một lần** mỗi revision (`goal.stalled`) | |
| Lỗi tạm thời, còn được thử | Như MVP: chờ mốc mở lại hạn mức nếu biết, không thì lùi dần theo `ERROR_BACKOFF_S` | `error_retry` |
| Lỗi cố định, hay đã hết số lần thử | Không hẹn `work`. `blocked` theo mã lỗi, báo một lần | |
| Chờ người dùng (xác nhận, cách hiểu bị bác, khám phá xong) | Không hẹn `work` | |
| Đạt, chế độ duy trì | Xem lại có giới hạn, giãn dần (dưới đây) | `review` |
| Không nguồn sự kiện, chưa đạt, không được làm | Xem lại có giới hạn, giãn dần | `review` |

**Xem lại giãn dần:**
- Bắt đầu ở `REVIEW_MIN_S`. Mỗi lần xem lại không thấy gì đổi thì nhân đôi, tới tối đa `REVIEW_MAX_S`.
- Thấy thay đổi thì về lại `REVIEW_MIN_S`. Thay đổi gồm: kết quả đánh giá, hash sản phẩm, trạng thái guard.
- **Hạn chót gần:** lịch không vượt quá nửa thời gian còn lại tới hạn, và không ngắn hơn `CHECK_MIN_S`.
- Lần xem lại chỉ chạy code, nên giãn nhịp ở đây là để bớt việc vặt cho host, không phải để tiết kiệm lượt model.

**Phát hiện nguồn đổi (`source_changed`):**
- Lúc xem lại, host so hash file sản phẩm với hash đã đăng (bảng `published`).
- Khác hash mà đánh giá chưa đạt: ghi lý do `source_changed` (tin mới), rồi xử lý ngay trong cùng lần thức.
- Khác hash mà vẫn đạt: chỉ ghi nhận, coi là người dùng tự sửa. Không gọi model.

**Lỗi tạm thời và cố định:** bảng mã chốt lúc code, từ các mã engine thật trả về.
- **Cố định:** dựng engine hỏng (`engine_build`), vùng ghi sai (`output_scope`), hết hạn mức (`budget_exhausted`).
- **Tạm thời:** hết giờ, bị ngắt (`interrupted`), quá tải, hết hạn mức gói thuê bao có giờ mở lại.
- Mã chưa biết coi là tạm thời, nhưng vẫn bị trần `ERROR_MAX_ATTEMPTS`.

### Tham số (phiên bản `heartbeat.v1`)

| Tên | Mặc định | Ghi chú |
|---|---|---|
| `RETRY_BASE_S` | 900 | 15 phút như MVP |
| `STALL_AFTER` | 2 | hai lượt liên tiếp không tiến bộ thì dừng thử tự động |
| `AUTO_RESERVE_CALLS` | 1 | |
| `ERROR_MAX_ATTEMPTS` | 3 | theo revision, đặt lại khi có tin mới |
| `ERROR_BACKOFF_S` | 1, 4, 24 giờ | như MVP |
| `REVIEW_MIN_S` | 6 giờ | như MVP |
| `REVIEW_MAX_S` | 7 ngày | mới; MVP dừng ở 24 giờ |
| `CHECK_MIN_S` | 15 phút | khi gần hạn chót |
| `GUARD_OBSERVE_S` | 1 giờ | như MVP, không giãn |

- Tham số là hằng có phiên bản trong module chính sách, không phải ô cài đặt (Javis chủ trương ít cài đặt).
- Mỗi lần thức ghi `policy_version`. Đổi một tham số mặc định thì tăng phiên bản.
- Test được thay tham số qua đối số của `decide`.

## 5. Kho

Thêm hai bảng phụ. Không bảng cũ nào đổi cột.

```sql
CREATE TABLE IF NOT EXISTS wake_reasons(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, brain_id TEXT NOT NULL,
  kind TEXT NOT NULL,            -- work | observe, khớp wakeups.kind
  code TEXT NOT NULL, ref TEXT NOT NULL DEFAULT '',   -- ref: id phản hồi, id lượt, revision... để gộp trùng
  detail TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, consumed_at REAL,
  UNIQUE(goal_id, kind, code, ref));
CREATE TABLE IF NOT EXISTS wake_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, brain_id TEXT NOT NULL,
  revision INTEGER NOT NULL, wake_kind TEXT NOT NULL, reasons_json TEXT NOT NULL,
  policy_version TEXT NOT NULL, decision TEXT NOT NULL,   -- work | evaluate | observe | sleep | blocked
  why TEXT NOT NULL DEFAULT '', action_id TEXT NOT NULL DEFAULT '', model_calls INTEGER NOT NULL DEFAULT 0,
  next_due_at REAL, next_code TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
```

- **Gộp trùng:** `UNIQUE(goal_id, kind, code, ref)`. Cùng một phản hồi ghi hai lần (thử lại HTTP, hai tab) chỉ thành một lý do. Lý do còn chờ cùng mã không có `ref` cũng gộp làm một.
- **Tiêu thụ:**
  - Quyết định `work`: `begin_action` đánh dấu `consumed_at` cho các lý do đã xét, cùng giao dịch ghi ý định hành động. Ý định ghi kèm id các lý do.
  - Quyết định khác: đánh dấu trong cùng giao dịch ghi `wake_log`.
  - Chết trước lúc đó thì lý do vẫn còn. Lần sau xét lại, cùng quyết định, vì khoá lượt và sổ hành động chống trùng.
- **"Mới" theo thời điểm:** điều kiện 2 ở mục 4 so `created_at` của lý do với lượt việc gần nhất. Lý do sót lại sau khi quay về bản cũ rồi nâng lại không gây gọi model lần nữa.
- **Giữ sổ:**
  - `wake_log`: tối đa 200 dòng mỗi mục tiêu, cắt lúc ghi.
  - `wake_reasons` đã tiêu thụ: xoá dòng quá 30 ngày, làm lúc ghi lý do mới của cùng mục tiêu.
- **Sao lưu:** lần đầu mở kho ở 0.88.0 chép `resonance.sqlite3.pre-a2.bak`, chỉ một lần, như A1.

**Hàm `_wake`:**
- Thêm tham số `code` (bắt buộc ở mọi chỗ gọi mới) và `ref`.
- Ghi `wakeups` như cũ. Câu `reason` giữ cho bản 0.87 đọc được.
- Thêm một dòng `wake_reasons`.

**Hàm `claim_wake`:** không đổi. `due_wakeups` đổi điều kiện: lịch `observe` của mục tiêu đang tạm dừng vẫn được nhận (mục 7).

## 6. Luồng một lần thức

1. `tick` nhận lịch (không đổi), gọi `advance(goal_id, {"kind": "wake"|"observe"}, deps)`.
2. `advance` giữ khoá lượt, chạy `_reconcile`, rồi đi qua `_gate` (không đổi thứ tự).
   - `_gate` chặn: ghi `wake_log` (`decision=blocked`), hẹn lại theo mục 7, tiêu thụ lý do đã xét.
3. Cổng bàn giao còn chờ: hẹn `handoff_wait`, không tiêu thụ lý do khác.
4. `_publish_latest` (không gọi model), rồi đánh giá bằng code.
5. Kiểm nguồn đổi (mục 4) nếu sản phẩm đã đăng.
6. `decide(...)`. Ra `work` thì `_work_step` (một lượt model), rồi `_settle` hẹn tiếp theo chính sách. Ra lựa chọn khác thì `_settle` với `worked=False`.
7. Ghi `wake_log`: lý do, quyết định, `action_id`, số lượt model (0 hay 1), lịch kế tiếp.

**Các sự kiện `advance` nhận thẳng:**
- `reaction` vẫn không làm gì.
- `user_schedule` ghi lý do rồi hẹn, như MVP.
- `start`, `user_message`, `resume` giữ cho các chỗ gọi cũ, được đổi thành lý do tương ứng.

**Thông báo không tự kích hoạt:**
- `drain_outbox` và `_resonance_notify` không ghi `wake_reasons`.
- Tin báo của trợ lý đi vào cuộc trò chuyện như một tin `assistant`, không tạo lượt chat.
- Chỉ lời người dùng (lượt chat mới, nút phản hồi, lệnh) và trạng thái do chủ dự án đổi mới sinh lý do lớp "tin mới". Test khoá điều này.

## 7. Guard khi bên làm việc ngủ

- **Lịch riêng:** lịch `observe` tách khỏi lịch `work`, giữ `GUARD_OBSERVE_S`, không giãn theo chính sách xem lại.
- **Bên làm việc ngủ** (chờ người dùng, bế tắc, hết lượt, lỗi cố định): vẫn quan sát guard. Guard chạm thì `blocked`/`guard` và báo như MVP.
- **Người dùng tạm dừng:** vẫn quan sát. Tạm dừng chặn hành động, còn quan sát chỉ đọc file bằng code, không phải hành động. `due_wakeups` nhận lịch `observe` của mục tiêu đang tạm dừng. `advance` với `observe` khi tạm dừng chỉ chạy `observe_guards`, không qua phần làm việc.
- **Trợ lý tắt, mất file hay đã nghỉ:** đây là thu hồi quyền.
  - Ngừng quan sát (xoá lịch `observe`).
  - Nếu mục tiêu có guard, báo **một lần** `goal.monitoring_lost`: liệt kê guard không còn được theo dõi và lý do.
  - Bật lại thì `wake_agent_goals` hẹn lại `observe` cùng `work`.
  - Đây là đề xuất, chờ chủ dự án chốt (mục 13, câu 1).
- **Cách hiểu bị bác** (`fit_rejected`): vẫn quan sát, vì mục tiêu còn active và chủ dự án chưa thu hồi gì.
- **Không giả là ổn:** guard không đọc được vẫn là `unknown`, giữ `guard_unknown` và kiểm lại bằng code.

## 8. Một bên quản lịch

Việc đã gắn mục tiêu chỉ có lịch của Resonance.
- **Chặn ở host:** trong một lượt chat, `javis_goal create` hay `update` thành công thì `turn_context` ghi `goal_touched`. Lượt đó gọi `javis_schedule op=create` sẽ bị từ chối, kèm câu: "việc này đã là mục tiêu, Javis tự giữ lịch; muốn hẹn lần xem lại thì nói giờ cụ thể".
- **Hẹn giờ cho mục tiêu:** đi qua `javis_goal` (`user_schedule`), không qua `javis_schedule`.
- **Gợi ý cho model:** thêm một câu vào `_RESONANCE_GOAL_HINT` với cùng nội dung.
- **Giữ nguyên:** loop cũ cho việc khác, và nhắc hẹn giờ cố định do người dùng tạo ngoài lượt có mục tiêu. A2 không đổi gì ở hai thứ này.

## 9. API và giao diện

**`goal_view`** thêm:
- `next_wake.code`;
- `wakes_recent`: 5 dòng `wake_log` gần nhất, mỗi dòng có thời điểm, mã lý do, quyết định, có gọi model hay không;
- `observe_next`.

`next_wake.reason` (câu thô) giữ cho trang cũ.

**Thẻ mục tiêu** (`chat-resonance.js`, dùng chung ở khung trợ lý A1):
- dòng "Lần thức tới" hiện nhãn theo mã, qua `vi.json`/`en.json` (`resonance.wake.<code>`), hết câu tiếng Việt thô;
- mục gập "Các lần thức gần đây": tối đa 5 dòng, ví dụ "08/10 14:05 · có phản hồi mới · làm một lượt" hay "09/10 02:00 · xem lại định kỳ · không gọi model";
- trạng thái mới `stalled` có nhãn và câu báo riêng.

Không thêm ô cài đặt nào.

## 10. Quay về và nâng lại

- **Quay về 0.87.0:** chạy được trên kho đã nâng.
  - Bản cũ bỏ qua `wake_reasons` và `wake_log`. `wakeups` vẫn hợp lệ.
  - Bản 0.87 chạy lại chính sách MVP: có thể gọi model ở lần xem lại như trước A2. Ghi rõ điều này trong hướng dẫn quay về.
- **Nâng lại:** lý do cũ còn sót không gây gọi model thừa, nhờ so thời điểm ở mục 5.
- **Bản sao `pre-a2.bak`:** dùng như `pre-a1.bak` (`docs/dev/resonance-a1-migration.md`).

## 11. Nghiệm thu (đồng hồ giả, không model)

Mỗi ca đếm số lần dựng engine (`engine_factory`) và đọc `wake_log`.

| Ca | Kỳ vọng |
|---|---|
| Mục tiêu đạt và đang chờ người dùng, chạy giả 30 ngày | 0 lượt model. Chỉ có lịch `observe` (nếu có guard). Mọi lần thức có dòng trong sổ |
| Duy trì đạt, sản phẩm không đổi, 30 ngày | 0 lượt model. Lần xem lại giãn 6 giờ, 12 giờ, 24 giờ... tới 7 ngày |
| Duy trì đạt, người dùng sửa file làm hỏng tiêu chí | `source_changed`, đúng 1 lượt model |
| Chưa đạt, hai lượt không tiến bộ | Dừng thử tự động. `stalled`, báo một lần, 0 lượt sau đó |
| Chưa đạt, lượt hai có tiến bộ | Được thử thêm, chuỗi bế tắc về 0 |
| Còn 1 lượt | Thử lại tự động không dùng lượt cuối. Phản hồi của người dùng thì dùng được |
| Hai phản hồi giống nhau (cùng idempotency), hay ba lý do dồn cùng lúc | Một lần thức, tối đa 1 lượt model |
| Tin báo của trợ lý vào chat | Không sinh lý do, không lần thức nào |
| Hai `tick` chạy song song trên cùng kho | Một bên nhận lịch, tối đa 1 lượt model |
| Chết sau khi nhận lịch, trước khi ghi sổ; khởi động lại | Lý do còn, xử lý đúng một lần |
| Chết giữa lượt model (`recovery`) | Đối soát, tính là một lần lỗi, thử lại theo luật lỗi |
| Lỗi cố định | Không thử lại tự động, `blocked`, báo một lần |
| Lỗi tạm thời 3 lần | Dừng thử. Có phản hồi mới thì được thử lại |
| Guard chưa đọc được rồi đọc lại được (nguồn hồi phục) | Kiểm lại bằng code, 0 lượt model khi chưa đọc được, rồi chạy tiếp |
| Tạm dừng có guard, guard chạm khi đang dừng | Vẫn phát hiện, `blocked`/`guard`, báo |
| Bên làm việc ngủ (chờ xác nhận), guard chạm | Vẫn phát hiện |
| Trợ lý tắt, mục tiêu có guard | Báo `monitoring_lost` một lần, 0 lượt model, bật lại thì quan sát tiếp |
| Hết hạn mức | `blocked`/`budget`, không hẹn `work`, 0 lượt model |
| Lượt chat vừa lập mục tiêu gọi `javis_schedule create` | Bị từ chối, có câu giải thích |
| Quay về 0.87.0 trên kho đã nâng (mã 0.87.0 thật, như test rollback A1) | Chạy được, bỏ qua bảng mới |
| Mã lý do lạ | Chỉ kiểm, không gọi model |

Các test MVP đang khẳng định hành vi cũ, như `no_source_uses_bounded_review` hay thử lại 15 phút, được sửa theo chính sách mới. Mỗi chỗ sửa ghi rõ trong bàn giao, không xoá ca.

## 12. Pilot

- A2 nghiệm thu chủ yếu bằng đồng hồ giả. Một lần chạy thật không chứng minh được "30 ngày không gọi model".
- Nếu người review cần bằng chứng trên engine thật, đề xuất một pilot nhỏ, duyệt riêng:
  - một mục tiêu duy trì trong phiên trợ lý, tối đa 2 lượt chat;
  - tua đồng hồ nền bằng biến môi trường chỉ dành cho sandbox;
  - kiểm sổ thức và số lượt model.
- Hạn mức và câu duyệt viết lúc đó. Không dùng lại ngân sách pilot cũ.

## 13. Cần chủ dự án chốt

1. **Trợ lý tắt thì ngừng theo dõi guard và báo một lần (đề xuất), hay vẫn theo dõi bằng code?**
   - Theo dõi tiếp thì không tốn model, nhưng trái với ý "tắt là tắt".
   - Nếu theo dõi tiếp, guard chạm khi trợ lý đang tắt chỉ được báo, không có hành động nào.
2. **Bế tắc sau 2 lượt không tiến bộ thì dừng và báo.** Mặc định `STALL_AFTER=2` có hợp không, hay anh muốn cho thử nhiều hơn trong hạn mức?
3. **Hạn mức theo trợ lý** (ví dụ số lượt model mỗi ngày cho mọi mục tiêu của một trợ lý). Thay đổi này đụng chi phí, nên A2 **không** làm nếu anh chưa yêu cầu. Hiện mỗi mục tiêu vẫn có hạn mức riêng.

## 14. Kế hoạch code (sau khi thiết kế đạt review)

1. `resonance_heartbeat.py`: chính sách thuần và test bảng.
2. Kho: hai bảng phụ, `_wake(code, ref)`, gắn mã ở mọi chỗ hẹn, bản sao `pre-a2`, `due_wakeups` cho `observe` khi tạm dừng.
3. `advance`, `_settle`, `_work_step`: gọi `decide`, ghi sổ, tiêu thụ lý do, luật lỗi theo revision, nguồn đổi, `stalled`, `monitoring_lost`.
4. Chặn `javis_schedule` trong lượt có mục tiêu; câu gợi ý.
5. `goal_view`, thẻ, i18n.
6. Test nghiệm thu mục 11, sửa test MVP theo chính sách mới, test quay về 0.87.0.
7. Hướng dẫn: thêm mục A2 vào tài liệu cách dùng và quay về.
