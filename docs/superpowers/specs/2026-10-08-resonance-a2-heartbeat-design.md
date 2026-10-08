# Resonance A2: nhịp tim thích nghi theo lý do

**Trạng thái:** thiết kế vòng 2, chưa có mã A2. Nhánh `claude/resonance-a2-heartbeat`, đặt số 0.88.0.

- **Nền:** nhánh A1 `claude/resonance-a1-agent-scope` tại `077bcf73` (0.87.0, chưa merge). A2 dùng `agent_gate` và sổ trợ lý của A1, nên nhánh chồng lên A1. A1 merge thì nhánh này rebase lên `main`.
- **Lộ trình:** [agent scope roadmap](2026-10-08-resonance-agent-scope-roadmap.md), mục 5.
- **Vòng 1** (`7504bf6a`) được review: 2 P1, 2 P2, 5 chỗ cần làm rõ. Mục 15 liệt kê từng điểm và chỗ sửa.
- Không gọi model để làm thiết kế này. Chưa có pilot A2.

## 1. Mục tiêu và ngoài phạm vi

**Mục tiêu:**
- Trợ lý chỉ thức khi có lý do cụ thể.
- Chỉ gọi model khi có bước đầu chưa làm, có tin mới từ người dùng, hoặc được thử lại trong trần.
- Đang chờ thì ngủ.
- Mỗi lần thức đều ghi lý do và quyết định.
- Lần thức không gọi model cũng phải rẻ cho máy chủ (mục 11).

**Giữ nguyên:**
- Một scheduler: `tick` trong vòng lặp nền 30 giây, nhận lịch bằng CAS (`claim_wake`), khoá lượt (`claim_lease`), đối soát khi tiến trình chết giữa chừng (`_reconcile`).
- Cổng bàn giao, hạn mức lượt gọi, outbox chống báo lặp, bảo vệ file của `_publish`.
- Bảng cũ không đổi cột (test `PRE_A1` vẫn khoá). A2 chỉ thêm bảng phụ.

**Ngoài phạm vi:**
- Học từ reaction và phản hồi: để A3.
- Adapter nguồn sự kiện ngoài (MCP, webhook, theo dõi file tức thời).
- Quyền thay file người dùng đã sửa, và bản đề xuất tự sinh khi có xung đột (mục 5).
- Liên kết lịch `javis_schedule` với mục tiêu, và chặn lịch trùng (mục 9).
- Hạn mức theo trợ lý hay theo ngày (mục 14, câu 3).
- Đường giao việc từ chat thường sang trợ lý.

## 2. Hiện trạng và khoảng trống (mã tại `077bcf73`)

| # | Hiện trạng | Hệ quả |
|---|---|---|
| G1 | `tick` gọi `advance(..., {"kind": "wake"})` cho mọi lịch `work`. Lý do chỉ là câu chữ trong `wakeups.reason`, bị ghi đè mỗi lần hẹn | `advance` không biết vì sao mình thức |
| G2 | Mọi lần thức `wake` có kết quả chưa đạt, và không phải chỉ chờ người dùng, đều vào `_work_step` (gọi model). Gồm cả lần xem lại (`_bounded_review`), lần kiểm lại sau khi bật trợ lý, lần phục hồi sau lượt bị ngắt | Gọi model khi không có gì mới |
| G3 | `RETRY_NOT_MET_S` 15 phút lặp tới hết hạn mức, không xét tiến bộ | Tốn lượt khi bế tắc |
| G4 | `ERROR_BACKOFF_S` dừng ở 24 giờ rồi lặp mãi. Lỗi đếm trên mọi revision | Lỗi cố định vẫn gọi model mỗi ngày |
| G5 | `due_wakeups` bỏ qua mục tiêu tạm dừng, nên lịch `observe` cũng dừng. `_gate` trả về sớm trước khi hẹn lại `observe` | Tạm dừng thì mất theo dõi guard mà không ai biết. Tắt trợ lý thì guard thôi được theo dõi lặng lẽ |
| G6 | Không có sổ ghi các lần thức | Không trả lời được vì sao một lần thức gọi model |
| G7 | Thẻ hiện `next_wake.reason` là câu tiếng Việt thô | Lệch i18n |
| G8 | Lần thức chạy trên event loop: SQLite và đọc file đồng bộ | Nhiều mục tiêu tới hạn cùng lúc có thể làm tab chậm, dù không gọi model |

## 3. Lý do thức: danh tính, lớp, vòng đời

### Hai nguồn lý do

**Sự kiện** (`origin=event`): do một việc đã xảy ra sinh ra.
- Mỗi sự kiện có `source_ref` ổn định, lấy từ chính nguồn: id dòng `goal_events`, `rev:<n>`, `handoff:<rev>`, id sự kiện trợ lý.
- Giao lại cùng sự kiện (thử lại HTTP, hai tab, khởi động lại) cho ra cùng `source_ref`. Chỉ mục duy nhất từng phần chặn dòng thứ hai, dù dòng đầu còn chờ hay đã phục vụ.
- Dòng đã phục vụ không bị xoá khi mục tiêu còn active, nên việc giao lại về sau vẫn bị nhận ra. Không dùng TTL để chống trùng.

**Hẹn giờ** (`origin=timer`): do chính sách hay cổng hẹn.
- Mỗi lần hẹn là một **lần mới**, `source_ref = tm_<ngẫu nhiên>`, không có ràng buộc duy nhất. Hai lần xem lại định kỳ liên tiếp là hai dòng khác nhau.
- Mỗi mục tiêu chỉ có **tối đa một** hẹn giờ đang chờ cho mỗi `wake_kind` (`work`, `observe`). Hẹn mới đánh dấu hẹn cũ đang chờ là `superseded`, trong cùng giao dịch.

### Lớp

| Lớp | Mã | Được mở lượt model? |
|---|---|---|
| Bước đầu | `created`, `revised`, `assigned` | Có, chỉ khi revision hiện tại chưa có lượt việc và chưa có bản tiếp nhận từ chat |
| Tin mới | `feedback` (mọi phản hồi trừ reaction), `user_schedule` | Có, trong hạn mức |
| Thử lại tự động | `retry_not_met`, `error_retry`, `recovery` | Có, theo trần ở mục 4 |
| Chỉ kiểm | `handoff_wait`, `handoff_done`, `resumed`, `agent_enabled`, `agent_recheck`, `agent_changed`, `guard_recheck`, `review`, `deadline`, **mã lạ** | Không bao giờ |
| Quan sát | `guard_observe` | Không bao giờ. Không đăng sản phẩm |

- **Chỉ lý do mở được lượt model.** Revision chưa có đầu ra không tự thành lý do: nếu ảnh chụp chỉ có `review`, `deadline`, quan sát hay mã lạ, thì không gọi model.
- **Mục tiêu có từ trước A2** không có dòng lý do. Lần đầu A2 mở kho, với mỗi mục tiêu active, kho dựng lại lý do từ chính `goal_events`:
  - revision hiện tại chưa có lượt việc: một lý do `created`, `source_ref = migrate:rev:<n>`;
  - phản hồi (`feedback.*`) ghi sau lượt việc gần nhất của revision: một lý do `feedback` mỗi phản hồi, `source_ref` là id dòng sự kiện, cùng khoá với lúc ghi thường.
  - Lịch `wakeups` cũ không có dòng lý do nào thì lần thức đó coi như `review` (chỉ kiểm).

### Vòng đời

`pending` sang `served` (có `settled_by`), hay `pending` sang `superseded` (chỉ hẹn giờ).

1. **Ảnh chụp:** `advance` giữ khoá lượt rồi đọc các lý do `pending` đã tới hạn: mọi sự kiện, cùng hẹn giờ có `due_at <= now`.
   - Chỉ id trong ảnh chụp được xét và được phục vụ.
   - Lý do đến trong lúc lượt đang chạy vẫn `pending` cho lần sau.
2. **Bị cổng chặn** (trợ lý tắt, tạm dừng, cách hiểu bị bác, guard `unknown`, đang chờ bàn giao): **không phục vụ gì**.
   - Ghi `wake_log` kèm id đã thấy.
   - Lý do còn nguyên. Khi gỡ chặn (`resumed`, `agent_enabled`, `guard_recheck` thấy guard đọc lại được), lần thức sau thấy lại chúng.
3. **Quyết định `work`:** `begin_action` đánh dấu `served` cho mọi id trong ảnh chụp, cùng giao dịch ghi ý định hành động. Ý định ghi kèm danh sách id.
   - Lượt model lỗi thì đi theo luật lỗi.
   - Nội dung góp ý không mất: prompt đọc chuỗi ý định và phản hồi từ kho, không đọc từ lý do.
4. **Quyết định khác** (qua cổng, không gọi model), trong cùng giao dịch ghi `wake_log`:
   - Lý do **chỉ kiểm** và **thử lại tự động** được phục vụ, vì đã xét xong.
   - Lý do **bước đầu** và **tin mới** chỉ được phục vụ khi kết luận là không cần làm: đã đạt, chỉ còn chờ người dùng xác nhận, hay bản chat vừa tiếp nhận đã đáp ứng.
   - Bị chặn vì hết hạn mức thì giữ `pending`.
5. **Quan sát** chỉ phục vụ đúng hẹn `guard_observe` của nó, không đụng lý do `work`.

**Lịch sau mỗi lần thức:**
- `wakeups.due_at` của `work` = sớm nhất giữa hẹn giờ mới và `now` (nếu còn sự kiện `pending` mà cổng không chặn).
- Sự kiện đến trong lúc chạy vì vậy không bị lịch kế tiếp đè mất.
- Bị chặn thì lịch là hẹn kiểm lại của cổng. Gỡ chặn tự hẹn `now`.

**Đối soát sau khi quay về bản cũ:**
- Bản 0.87 có thể đã làm việc mà không ghi id lý do. Lúc mở kho, sự kiện `pending` cũ hơn một lượt việc **không gắn lý do** của cùng revision được chốt `served`, với `settled_by` là lượt đó.
- Đây chỉ là đường đối soát cho trường hợp này, không thay luật ảnh chụp.

## 4. Chính sách `heartbeat.v1`

Một hàm thuần `decide(goal, snapshot, history, assessment, now, policy) -> Decision` trong module mới `server/resonance_heartbeat.py`. Không I/O, test bằng bảng.

### Thứ tự quyết định

1. `_gate` (mục 7) chặn: `blocked`, không phục vụ gì.
2. Cổng bàn giao còn chờ: hẹn `handoff_wait`, không phục vụ gì.
3. `_publish_latest`, rồi đánh giá bằng code, rồi kiểm sửa ngoài luồng (mục 5). Không bước nào gọi model.
4. Đã đạt, hay chỉ còn chờ người dùng: `evaluate`. Phục vụ cả ảnh chụp, hẹn theo bảng dưới.
5. Bị chờ do sửa ngoài luồng (mục 5): `evaluate`, giữ `pending` các lý do bước đầu và tin mới.
6. Ảnh chụp có **tin mới**: `work`, nếu còn lượt (bất kể dự phòng).
7. Ảnh chụp có **bước đầu** và revision chưa có lượt việc hay bản tiếp nhận: `work`, nếu còn lượt.
8. Ảnh chụp có **thử lại tự động** và trần cho phép: `work`.
9. Còn lại: `evaluate` hay `sleep`. **0 lượt model.**

Bước 6 hay 7 mà hết lượt: `blocked`/`budget`, giữ lý do `pending`, không hẹn `work`.

### Tiến bộ và bế tắc

- **Mốc tốt nhất:** số tiêu chí đạt cao nhất sau các lượt việc trong cùng revision, tính từ tin mới gần nhất (hay từ đầu revision).
- **Tiến bộ:** lượt mới vượt mốc tốt nhất. Lượt tụt rồi hồi lại bằng mốc cũ không tính là tiến bộ, nên dao động không đặt lại chuỗi.
- **Chuỗi bế tắc** (`stall`): số lượt việc liên tiếp không vượt mốc, cũng tính từ tin mới gần nhất.
- `stall >= STALL_AFTER` thì dừng thử tự động: `waiting`/`stalled`, báo **một lần** mỗi revision (`goal.stalled`).
  - Đây không phải thất bại. Mục tiêu vẫn active.
  - Tin mới (góp ý, revision mới) mở lại theo luật, chuỗi tính lại từ 0.
  - Tiêu chí thành công không đổi.

### Trần thử lại tự động (một luật chung)

Một lượt `retry_not_met`, `error_retry` hay `recovery` chỉ được chạy khi **cả hai** điều kiện đúng:

- **Còn lượt dự phòng:** `budget_calls - calls_used > AUTO_RESERVE_CALLS`. Lượt cuối để dành cho lúc người dùng góp ý. Tin mới và bước đầu dùng được lượt đó.
- **Chưa chạm trần riêng của nhánh:**
  - `retry_not_met`: `stall < STALL_AFTER`.
  - `error_retry` và `recovery`: số lượt việc lỗi tính từ tin mới gần nhất trong revision nhỏ hơn `ERROR_MAX_FAILS`, và lỗi gần nhất không thuộc nhóm cố định.
  - `ERROR_MAX_FAILS = 3` là **ba lượt lỗi tổng cộng**, gồm cả lượt đầu, tức tối đa hai lần thử lại. Lượt bị ngắt đã đối soát tính là một lượt lỗi.

**Lỗi cố định và tạm thời:** bảng mã chốt lúc code, từ mã engine thật trả về.
- Cố định: dựng engine hỏng (`engine_build`), vùng ghi sai (`output_scope`), hết hạn mức (`budget_exhausted`).
- Tạm thời: hết giờ, bị ngắt (`interrupted`), quá tải, hết hạn mức gói thuê bao có giờ mở lại.
- Mã chưa biết coi là tạm thời, vẫn bị trần.
- Hết trần hay lỗi cố định: `blocked` theo mã, báo một lần, không hẹn `work`. Tin mới mở lại.

### Hẹn lịch kế tiếp

| Tình huống | Lịch `work` | Mã |
|---|---|---|
| Chưa đạt, thử lại được | `now + RETRY_BASE_S × 2^stall` | `retry_not_met` |
| Lỗi tạm thời, thử lại được | Mốc mở lại hạn mức + 60 giây nếu biết; không thì `ERROR_BACKOFF_S[fails-1]` | `error_retry` |
| Bế tắc, hết trần, lỗi cố định, hết hạn mức | Không hẹn | |
| Chờ người dùng (xác nhận, cách hiểu bị bác, khám phá xong, sửa ngoài luồng) | Không hẹn | |
| Đạt ở chế độ duy trì, hay không có lý do làm | Xem lại giãn dần | `review` |
| Có hạn chót chưa tới | Xem phần gần hạn | `deadline` |

**Xem lại giãn dần:**
- Bắt đầu `REVIEW_MIN_S`. Lần xem lại không thấy gì đổi thì nhân đôi, tối đa `REVIEW_MAX_S`.
- Thấy đổi thì về lại `REVIEW_MIN_S`. "Đổi" gồm kết quả đánh giá, hash sản phẩm, trạng thái guard.
- Lần xem lại chỉ chạy code. Giãn nhịp để bớt việc vặt cho máy chủ, không phải để bớt lượt model.

**Gần hạn chót** (`horizon.kind = deadline`, `at` là hạn), ưu tiên theo thứ tự:
1. Còn hơn `2 × CHECK_MIN_S`: lịch là sớm nhất giữa lịch thường và `now + (at - now) / 2`.
2. Còn từ 0 tới `2 × CHECK_MIN_S`: một lần kiểm đúng `at`. Lịch có thể trễ tới một nhịp scheduler (30 giây).
3. Qua hạn mà chưa đạt:
   - ghi sự kiện `deadline_passed` và báo **một lần** mỗi revision (`goal.deadline_passed`);
   - không tự gia hạn, không kết luận thành công hay thất bại, không mở lượt model vì hạn;
   - sau đó về lịch xem lại thường.

`deadline` thuộc lớp chỉ kiểm.

### Tham số (phiên bản `heartbeat.v1`)

| Tên | Mặc định | Ghi chú |
|---|---|---|
| `RETRY_BASE_S` | 900 | 15 phút như MVP |
| `STALL_AFTER` | 2 | review chấp nhận làm mặc định |
| `AUTO_RESERVE_CALLS` | 1 | |
| `ERROR_MAX_FAILS` | 3 | ba lượt lỗi tổng cộng, tính từ tin mới gần nhất |
| `ERROR_BACKOFF_S` | 1, 4, 24 giờ | như MVP |
| `REVIEW_MIN_S` | 6 giờ | như MVP |
| `REVIEW_MAX_S` | 7 ngày | mới; MVP dừng ở 24 giờ |
| `CHECK_MIN_S` | 15 phút | gần hạn |
| `GUARD_OBSERVE_S` | 1 giờ | như MVP, không giãn |

- Đây là hằng có phiên bản trong module chính sách, không phải ô cài đặt.
- Mỗi lần thức ghi `policy_version`. Đổi mặc định thì tăng phiên bản.
- Test thay tham số qua đối số của `decide`.

## 5. File bị sửa ngoài luồng

Hiện tại, `_publish` không thay file khi hash trên đĩa khác mốc đã đăng (`published`), và báo `goal.publish_conflict` một lần cho mỗi hash. A2 giữ nguyên bảo vệ này, và **tách mốc quan sát khỏi mốc được phép thay file**.

- **Mốc được phép thay file:** vẫn là bảng `published`. A2 không bao giờ ghi bảng này chỉ vì quan sát, nên không lách được bảo vệ.
- **Mốc quan sát:** bảng phụ `source_observations(goal_id, path, sha256, first_seen_at, verdict)`.
  - Lần xem lại đọc hash file sản phẩm (mục 11 về chi phí). Hash khác `published` là **sửa ngoài luồng**.
  - Hash chưa có trong bảng: ghi một dòng (H1, rồi H2 là dòng khác), báo một lần theo idem sẵn có `publish_conflict:<path>:<hash>`.
  - Hash đã có: không ghi, không báo.
- **Quyết định:**
  - **Không gọi model** vì sửa ngoài luồng. Host không có quyền thay file đó, nên bản model viết ra cũng không đăng được.
  - Bản người dùng vẫn đạt tiêu chí: ghi nhận, `healthy`, xem lại như thường.
  - Bản người dùng không đạt: `waiting`/`source_drift`, không hẹn `work`. Lý do bước đầu và tin mới giữ `pending` (mục 4, bước 5).
- **Thoát trạng thái chờ:**
  - Người dùng đưa file về đúng mốc đã đăng: hết sửa ngoài luồng, đánh giá như thường.
  - Người dùng xoá file: không còn xung đột. Bản đang hiệu lực là lượt việc nền thì `_publish_latest` đăng lại mà không gọi model. Bản đang hiệu lực là bản tiếp nhận từ chat thì hiện chưa có đường đăng lại (`_publish_latest` trả `superseded`), nên A2 coi như sửa ngoài luồng: chờ, báo một lần, không gọi model.
  - Người dùng sửa cách hiểu, đổi đường dẫn: thành revision mới, đi luồng thường.
  - Bất kỳ lựa chọn nào trao quyền ghi đè, hay cho model viết bản đề xuất cạnh file, là quyền mới. A2 không làm, ghi ở ngoài phạm vi.
- **Guard** vẫn quan sát file đó theo quyền hiện có (mục 7).

## 6. Kho

Ba bảng phụ. Không bảng cũ nào đổi cột.

```sql
CREATE TABLE IF NOT EXISTS wake_reasons(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, brain_id TEXT NOT NULL,
  wake_kind TEXT NOT NULL,                 -- work | observe
  code TEXT NOT NULL, origin TEXT NOT NULL, -- event | timer
  source_ref TEXT NOT NULL, due_at REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',   -- pending | served | superseded
  created_at REAL NOT NULL, settled_at REAL, settled_by TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS wake_reasons_event
  ON wake_reasons(goal_id, code, source_ref) WHERE origin='event';
CREATE INDEX IF NOT EXISTS wake_reasons_pending ON wake_reasons(goal_id, state, due_at);
CREATE TABLE IF NOT EXISTS wake_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, brain_id TEXT NOT NULL,
  revision INTEGER NOT NULL, wake_kind TEXT NOT NULL,
  seen_json TEXT NOT NULL, served_json TEXT NOT NULL,     -- id lý do đã thấy và đã phục vụ
  policy_version TEXT NOT NULL,
  decision TEXT NOT NULL,                                 -- work | evaluate | observe | sleep | blocked
  why TEXT NOT NULL DEFAULT '', action_id TEXT NOT NULL DEFAULT '', model_calls INTEGER NOT NULL DEFAULT 0,
  next_due_at REAL, next_code TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS source_observations(
  goal_id TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, first_seen_at REAL NOT NULL,
  verdict TEXT NOT NULL DEFAULT '', PRIMARY KEY(goal_id, path, sha256));
```

**Ghi lý do:**
- Sự kiện: `INSERT OR IGNORE`. Chỉ mục từng phần chỉ áp cho `origin='event'`, nên chống giao lại không chặn hẹn giờ.
- Hẹn giờ: `UPDATE ... SET state='superseded'` các hẹn cùng `wake_kind` đang chờ, rồi `INSERT` lần mới, trong một giao dịch.
- Cả hai đều cập nhật `wakeups` (sớm nhất), cùng giao dịch.

**Giữ sổ:**
- `wake_log`: tối đa 200 dòng mỗi mục tiêu, cắt lúc ghi. Đây là sổ xem lại, không dùng để chống trùng.
- `wake_reasons`:
  - `superseded` và hẹn giờ `served` quá 30 ngày được xoá lúc ghi;
  - sự kiện giữ tới khi mục tiêu kết thúc, rồi xoá cùng lúc chuyển trạng thái cuối, vì mục tiêu đã kết thúc không nhận sự kiện nữa.
- **Sao lưu:** lần đầu mở kho ở 0.88.0 chép `resonance.sqlite3.pre-a2.bak`, chỉ một lần, như A1.

**`_wake`** nhận thêm `code`, `origin`, `source_ref`. Câu `reason` trong `wakeups` vẫn ghi cho bản 0.87 đọc.

**`due_wakeups`:** nhận lịch `observe` của mục tiêu đang tạm dừng (mục 7). Lịch `work` của mục tiêu tạm dừng vẫn bỏ qua như cũ.

## 7. Cổng: nhánh làm việc và nhánh quan sát

`_gate` tách thành hai cổng dùng chung các bước kiểm danh tính và quyền.

| Kiểm | Nhánh làm việc (`work`) | Nhánh quan sát (`observe`) |
|---|---|---|
| Mục tiêu còn active | chặn | chặn |
| Chưa gán trợ lý | chặn, không hẹn | dừng quan sát |
| Trợ lý tắt, mất file, nghỉ, đổi phiên bản | chặn, hẹn `agent_recheck` | dừng quan sát, báo `monitoring_lost` (dưới) |
| Người dùng tạm dừng | chặn | **đi tiếp** |
| Cách hiểu bị bác | chặn | **đi tiếp** |
| Guard đã chạm trước đó | chặn | dừng (đã báo) |
| Đang chờ bàn giao | chặn | **đi tiếp** |
| Đọc guard | có, rồi chặn nếu chạm hay `unknown` | có |

**Nhánh quan sát** chỉ chạy `observe_guards`:
- Guard chạm: `blocked`/`guard`, xoá lịch, báo như MVP.
- Guard `unknown`: ghi đánh giá, giữ `guard_unknown` nếu nhánh làm việc đã đặt.
- Không bao giờ đăng sản phẩm, gọi model, hay phục vụ lý do `work`.

**Tắt trợ lý** (review chấp nhận đề xuất, mục 14):
- Dừng quan sát và xoá lịch `observe`.
- Mục tiêu có guard thì báo **một lần mỗi đợt mất quyền** `goal.monitoring_lost`, idem theo sự kiện tắt hay mất file của trợ lý. Báo liệt kê guard không còn được theo dõi.
- Thẻ giữ dòng "Không còn theo dõi guard" cho tới khi được theo dõi lại. Không hiện như đang an toàn.
- Bật lại: `wake_agent_goals` hẹn `observe` ngay và lý do `agent_enabled`. Nhánh làm việc đọc guard trong cổng trước mọi tác động.

**Tạm dừng một mục tiêu:** khác tắt trợ lý. Vẫn quan sát bằng code, và guard chạm vẫn báo.

## 8. Luồng một lần thức

1. `tick` (mục 11) nhận tối đa `limit` lịch tới hạn, gọi `advance(goal_id, {"kind": "wake"|"observe"}, deps)`.
2. `advance` giữ khoá lượt, chạy `_reconcile` (chốt lượt dở; lượt `work` bị ngắt thành lỗi `interrupted`), rồi chụp ảnh lý do.
3. Nhánh quan sát: mục 7, ghi `wake_log`, hẹn `guard_observe` mới.
4. Nhánh làm việc: thứ tự quyết định ở mục 4, rồi `_work_step` nếu ra `work`, rồi `_settle`.
5. Ghi `wake_log`: đã thấy, đã phục vụ, quyết định, `action_id`, số lượt model (0 hay 1), lịch kế tiếp. Tính lại `wakeups` theo mục 3.

**`advance` nhận thẳng sự kiện:**
- `reaction` vẫn không làm gì.
- `user_schedule` ghi lý do sự kiện rồi hẹn.
- `start`, `user_message`, `resume` của các chỗ gọi cũ đổi thành lý do tương ứng.

**Thông báo không tự kích hoạt:**
- `drain_outbox` và `_resonance_notify` không ghi `wake_reasons`.
- Tin báo của trợ lý vào chat là tin `assistant`, không tạo lượt chat.
- Chỉ lời và thao tác của người dùng hay chủ dự án sinh lý do lớp tin mới.

## 9. Một bên quản lịch: thu hẹp cam kết

Review chỉ ra rằng chặn `javis_schedule` theo cờ toàn lượt (`goal_touched`) vừa chặn nhầm nhắc việc độc lập, vừa bỏ sót lịch trùng tạo ở lượt khác. A2 **bỏ** chặn đó.

**A2 bảo đảm:**
- Lịch theo đuổi một mục tiêu chỉ nằm ở `wakeups` của Resonance.
- Mỗi mục tiêu chỉ có một hẹn giờ `work` và một hẹn giờ `observe` đang chờ.
- Hai scheduler không cùng nhận một lịch.
- Hẹn giờ cho mục tiêu đi qua `javis_goal` (`user_schedule`).

**A2 không bảo đảm:** người dùng hay model tạo thêm loop hay nhắc hẹn riêng cho cùng việc.
- Chưa có liên kết lịch với mục tiêu do host kiểm, và không dùng model để đoán hai yêu cầu có cùng nghĩa không.
- `_RESONANCE_GOAL_HINT` thêm một câu gợi ý (không ràng buộc): "việc đã thành mục tiêu thì Javis tự giữ lịch; chỉ tạo nhắc hẹn khi đó là việc khác".
- Nhắc hẹn và loop độc lập dùng như cũ, ở mọi thứ tự.

Liên kết rõ từ lịch tới mục tiêu (trường `goal_id` do host kiểm trong `javis_schedule`) là hạng mục sau, nằm ngoài phạm vi.

## 10. API và giao diện

**`goal_view`** thêm:
- `next_wake.code`;
- `observe`: `{"state": "on"|"lost"|"none", "next_at", "lost_reason"}`;
- `wakes_recent`: 5 dòng `wake_log` gần nhất (thời điểm, mã lý do chính, quyết định, có gọi model không);
- `source_drift`: hash và thời điểm thấy nếu đang chờ do sửa ngoài luồng.

`next_wake.reason` (câu thô) giữ cho trang cũ.

**Thẻ mục tiêu** (`chat-resonance.js`, dùng chung ở khung trợ lý A1):
- "Lần thức tới" hiện nhãn theo mã, qua `vi.json`/`en.json` (`resonance.wake.<code>`).
- Mục gập "Các lần thức gần đây", ví dụ "09/10 02:00 · xem lại định kỳ · không gọi model".
- Nhãn và câu báo cho `stalled`, `source_drift`, `deadline_passed`, cùng dòng "Không còn theo dõi guard".

Không thêm ô cài đặt nào.

## 11. Hiệu năng

Không gọi model chưa có nghĩa là rẻ cho máy chủ. A2 phải giữ các bất biến sau:

- **Không quét khi chưa tới hạn.** Mỗi nhịp 30 giây chỉ có một truy vấn chỉ mục `wakeups_due`. Không đọc file, không hash, không đọc lý do của mục tiêu chưa tới hạn.
- **Giới hạn mỗi nhịp:** `tick` xử lý tối đa `TICK_LIMIT = 3` lịch như MVP. Mỗi lần thức chỉ kiểm:
  - một file sản phẩm (tối đa `PUBLISH_MAX_BYTES` 1 MB);
  - các file guard của chính mục tiêu (tối đa `GUARDS_MAX` 5);
  - một số câu SQLite cố định, không phụ thuộc số mục tiêu.
- **Không giữ event loop:** phần chỉ chạy code của lần thức (cổng, đọc file, hash, đánh giá, ghi sổ) chạy trong `asyncio.to_thread`. Chỉ lượt model là `await` trên loop, như hiện nay. Dùng cùng cách đo độ trễ timer với PR #592.
- **Hash có bộ nhớ đệm:** `(path, mtime_ns, size)` khớp lần trước thì dùng lại hash, không đọc lại file.
- **Không kéo thêm tối ưu toàn ứng dụng.** Phần khác của hiệu năng VPS ở PR #592 và việc hạ tầng.

**Kiểm:**
- 200 mục tiêu, chỉ 3 tới hạn: một nhịp không đọc file nào của 197 mục tiêu còn lại (đếm bằng cách vá `Path.read_bytes`/`open`).
- 50 mục tiêu cùng tới hạn: mỗi nhịp đúng 3.
- Trễ timer của event loop trong lúc nhịp xử lý 3 mục tiêu có file 1 MB: dưới 50 ms (so với đối chứng chạy thẳng trên loop).
- Số câu SQLite mỗi lần thức không tăng theo số mục tiêu.

## 12. Quay về và nâng lại

- **Quay về 0.87.0:** chạy được trên kho đã nâng.
  - Bản cũ bỏ qua ba bảng mới. `wakeups` vẫn hợp lệ.
  - Bản 0.87 chạy lại chính sách MVP: có thể gọi model ở lần xem lại như trước A2. Hướng dẫn quay về ghi rõ.
- **Nâng lại:** đối soát ở mục 3 chốt các sự kiện mà bản cũ đã xử lý bằng lượt việc không gắn lý do.
- **Bản sao `pre-a2.bak`:** dùng như `pre-a1.bak` (`docs/dev/resonance-a1-migration.md`).

## 13. Nghiệm thu (đồng hồ giả, không model)

Mỗi ca đếm số lần dựng engine (`engine_factory`) và đọc `wake_log`.

**Nhịp và lượt model**

| Ca | Kỳ vọng |
|---|---|
| Đạt và đang chờ người dùng, chạy giả 30 ngày | 0 lượt model. Mọi lần thức có dòng sổ |
| Duy trì đạt, sản phẩm không đổi, 30 ngày | 0 lượt model. Xem lại giãn 6 giờ, 12 giờ, 24 giờ... tới 7 ngày |
| Hai lần xem lại định kỳ liên tiếp | Cả hai đều chạy, hai dòng lý do khác nhau |
| Ảnh chụp chỉ có `review`, `deadline`, quan sát hay mã lạ, revision chưa có đầu ra | 0 lượt model |
| Hai lượt không vượt mốc tốt nhất | Dừng thử tự động, `stalled`, báo một lần, mục tiêu vẫn active |
| Lượt tụt rồi hồi về mốc cũ | Không tính là tiến bộ, chuỗi không đặt lại |
| Lượt vượt mốc tốt nhất | Được thử tiếp |
| Góp ý sau khi `stalled` | Đúng 1 lượt, chuỗi tính lại |
| Còn 1 lượt | Cả `retry_not_met` lẫn `error_retry` đều không dùng. Góp ý thì dùng được |
| Lỗi tạm thời | Tối đa 3 lượt lỗi tổng cộng, rồi `blocked`, báo một lần |
| Lỗi cố định | Không thử lại tự động |
| Chết giữa lượt model | Đối soát, tính một lượt lỗi, thử lại theo trần |
| Hạn chót còn 20 phút | Một lần kiểm đúng hạn, trễ tối đa một nhịp |
| Qua hạn chưa đạt | `deadline_passed` báo một lần, không gia hạn, không gọi model vì hạn |
| Hết hạn mức | `blocked`/`budget`, giữ lý do, 0 lượt model |

**Vòng đời lý do**

| Ca | Kỳ vọng |
|---|---|
| Góp ý, rồi tạm dừng trước lần thức, rồi tiếp tục | Góp ý được xử lý đúng một lần sau khi tiếp tục |
| Góp ý, rồi tắt trợ lý, rồi bật lại | Như trên |
| Góp ý trong lúc guard `unknown`, guard đọc lại được | Như trên |
| Quan sát chạy trong lúc tạm dừng | Góp ý vẫn `pending` |
| Góp ý đến trong lúc lượt model đang chạy | Còn `pending`, lịch về `now` sau lượt, xử lý ở lần sau |
| Giao lại cùng góp ý (trước và sau khi phục vụ) | Một dòng, xử lý một lần |
| Chết sau khi nhận lịch, trước khi ghi sổ; khởi động lại | Lý do còn, xử lý đúng một lần |
| Chết sau `begin_action` | Không làm lại lý do đã phục vụ; đối soát theo luật lỗi |
| Quay về 0.87 làm việc, rồi nâng lại | Sự kiện cũ được chốt theo lượt không gắn lý do, không gọi model thêm |
| Tin báo của trợ lý vào chat | Không sinh lý do, không lần thức nào |
| Hai `tick` song song trên cùng kho | Một bên nhận, tối đa 1 lượt model |

**Sửa ngoài luồng**

| Ca | Kỳ vọng |
|---|---|
| Sửa tay H1 làm hỏng tiêu chí, 10 lần xem lại | 0 lượt model, một dòng quan sát, báo một lần, `source_drift` |
| Sửa tiếp thành H2 | Dòng quan sát thứ hai, báo thêm một lần |
| Sửa tay vẫn đạt | Ghi nhận, `healthy`, 0 lượt model |
| Đưa file về mốc đã đăng | Hết `source_drift`, 0 lượt model |
| Xoá file, bản hiệu lực từ việc nền | Đăng lại đầu ra đã lưu, 0 lượt model |
| Xoá file, bản hiệu lực từ chat | `source_drift`, báo một lần, 0 lượt model |
| Nâng lên A2 khi đang có góp ý chưa xử lý | Lý do `feedback` dựng từ `goal_events`, xử lý đúng một lần |
| Bảng `published` sau mọi ca trên | Không đổi do quan sát |
| Guard trên file bị sửa tay | Vẫn quan sát |

**Guard**

| Ca | Kỳ vọng |
|---|---|
| Tạm dừng, guard chạm | Phát hiện, `blocked`/`guard`, báo |
| Chờ xác nhận, guard chạm | Phát hiện |
| Cách hiểu bị bác, guard chạm | Phát hiện |
| Tắt trợ lý có guard | `monitoring_lost` một lần, thẻ hiện "Không còn theo dõi guard". Tắt lần hai sau khi bật lại: báo thêm một lần |
| Bật lại | Quan sát ngay, đọc guard trước mọi tác động |
| Guard `unknown` rồi đọc lại được | Kiểm bằng code, 0 lượt model khi chưa đọc được |

**Lịch độc lập**

| Ca | Kỳ vọng |
|---|---|
| Lập mục tiêu X rồi tạo nhắc Y trong cùng lượt | Y tạo được |
| Tạo nhắc Y rồi lập X, ở lượt khác | Cả hai còn nguyên |

**Hiệu năng:** các ca ở mục 11.

**Quay về:** mã 0.87.0 thật chạy trên kho đã nâng, như test rollback A1.

Các test MVP khẳng định hành vi cũ (`no_source_uses_bounded_review`, thử lại 15 phút lặp tới hết hạn mức) được sửa theo chính sách mới. Mỗi chỗ sửa ghi trong bàn giao, không xoá ca.

## 14. Quyết định mặc định

Review vòng 1 đề xuất, khớp với đề xuất của thiết kế. Chủ dự án có thể đổi.

1. **Tắt trợ lý:** ngừng theo dõi guard, báo một lần mỗi đợt mất quyền, thẻ hiện rõ đã ngừng. Tạm dừng mục tiêu thì vẫn quan sát (mục 7).
2. **Hai lượt không tiến bộ:** dừng thử tự động và chuyển sang chờ, không kết luận thất bại (mục 4). Không thêm ô cài đặt.
3. **Hạn mức theo trợ lý:** không làm ở A2, giữ các trần hiện có.

## 15. Thay đổi sau review vòng 1

Review: `exports/reviews/PR-590-final-and-PR-593-A2-design-review.md` (ngoài git), tại `7504bf6a`.

| Điểm | Sửa |
|---|---|
| P1-1: sửa tay kích hoạt model mà không có quyền đăng | Bỏ `source_changed` khỏi lớp tin mới. Tách mốc quan sát (`source_observations`) khỏi mốc thay file (`published`). Sửa ngoài luồng chỉ ghi nhận, báo một lần mỗi hash, chờ; không gọi model (mục 5) |
| P1-2: tiêu thụ lý do khi bị chặn | Vòng đời `pending`/`served`/`superseded`, ảnh chụp theo id. Bị chặn không phục vụ gì. Bước đầu và tin mới chỉ được phục vụ bởi lượt việc hay kết luận không cần làm. Nhánh quan sát tách cổng, không đụng lý do `work` (mục 3, 7) |
| P2-1: khoá chống trùng chặn lần định kỳ sau | Tách sự kiện (chỉ mục duy nhất từng phần theo `source_ref` nguồn) khỏi hẹn giờ (mỗi lần một id, hẹn mới thay hẹn cũ). Không dùng TTL để chống trùng (mục 3, 6) |
| P2-2: `goal_touched` chặn cả lượt | Bỏ chặn. Thu hẹp cam kết về lịch nội bộ của mục tiêu; liên kết lịch với mục tiêu để sau (mục 9) |
| Đếm tiến bộ | Mốc tốt nhất trong revision, dao động không đặt lại chuỗi; bế tắc là chờ, không phải thất bại (mục 4) |
| Lượt dự phòng và lỗi | Một luật chung cho mọi thử lại tự động; ba lượt lỗi tổng cộng (mục 4) |
| Gần hạn | Thứ tự ưu tiên rõ, một lần kiểm đúng hạn, qua hạn báo một lần (mục 4) |
| Lý do lạ | Chỉ lý do mở được lượt model; mã lạ thuộc lớp chỉ kiểm (mục 3, 4) |
| Hiệu năng | Mục 11 mới: không quét khi chưa tới hạn, giới hạn mỗi nhịp, chạy ngoài event loop, ca kiểm đo được |

## 16. Kế hoạch code (sau khi thiết kế đạt review)

1. `resonance_heartbeat.py`: `decide` và test bảng.
2. Kho: ba bảng phụ, `_wake` theo nguồn, vòng đời lý do, đối soát khi nâng, bản sao `pre-a2`, `due_wakeups` cho `observe` khi tạm dừng.
3. `advance`: ảnh chụp, hai cổng, `decide`, ghi sổ, sửa ngoài luồng, `stalled`, `deadline_passed`, `monitoring_lost`, chạy phần code trong luồng phụ.
4. `goal_view`, thẻ, i18n, câu gợi ý trong `_RESONANCE_GOAL_HINT`.
5. Test nghiệm thu mục 13, sửa test MVP theo chính sách mới, test quay về 0.87.0.
6. Hướng dẫn: mục A2 trong tài liệu cách dùng và quay về.
