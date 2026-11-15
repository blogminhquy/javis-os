# T3 phần P: nhịp thích nghi lớp 3 (0.156.0)

Thiết kế gốc: `docs/superpowers/specs/2026-10-15-team-adaptive-design.md` mục 2, 3, 5, 6, 9, 9.1, 10, 12, 13. Hợp đồng với phần
J (phán xử) và L (học): `docs/dev/team-chat-t3-contract.md`. Phần này không tự gọi model nào trong test; mọi đường qua
`main.py` chặn engine thật ngay lúc dựng.

## 1. Bản đồ mã

| Phần | File | Việc |
|---|---|---|
| Chính sách thuần + kho | `server/agent_pulse.py` | `pulse.v1`: bậc, trạng thái, `decide`, `score`, `compute_k`, `attribute`, `effective_due`; bảng và thao tác kho (`record_signal`, `wake`, `set_state`, `evaluate`, `view`, `record_contrib`, cơ hội, đã xem, thay đổi chính sách) |
| Host | `server/agent_pulse_host.py` | nhịp 30 giây (`PulseHost.tick`), lần thức, lượt quét, bộ chuyển tới `agent_judge` và `agent_budget`, sổ đăng ký mục hiển thị và lý do, route |
| Bộ chiếu | `server/feedback_projector.py` | `record_pulse_signal` (móc T2 đã nối), `record_task_event`, `pulse_wake`, `void_task_event`, thay tín hiệu khi đổi reaction |
| Nhóm | `server/team_runner.py`, `server/team_api.py` | tín hiệu chấp nhận đề xuất, chốt quyết định, sửa sau kết quả, huỷ; thức khi chủ @ hay giao việc; dòng `max_tier`, dự trữ 20% trong bảng giới hạn |
| Kho Cộng hưởng | `server/resonance_store.py` | mở kho là tạo bảng nhịp và nâng cấp một lần; bật lại từ `off` về B3 |
| Máy chủ | `server/main.py` | `_pulse_tick` trong `_scheduler_loop` (cờ bận riêng), phụ thuộc thật, thức khi chủ nhắn chat riêng, xoá agent thì `void` tín hiệu, đăng ký route |
| Giao diện | `dashboard/agent-pulse.js`, `dashboard/pulse-seen.js`, `workspace.js`, `teams.js`, `console.css`, i18n | bảng Nhịp trên thẻ trợ lý và dòng thành viên, sổ `window.JavisPulseParts`, sự kiện đã xem |

## 2. Chính sách `pulse.v1`

Bậc: B0 15 phút, B1 1 giờ, B2 4 giờ, B3 1 ngày, B4 3 ngày, B5 1 tuần, B6 2 tuần, B7 1 tháng, bậc 8 là ngủ đông (không lịch).
Khởi tạo B3. Trạng thái theo bậc: `active` B0-B2, `awake` B3-B4, `slowed` B5-B7, `hibernating` bậc 8; ngoài ra `waiting_owner`,
`paused`, `off` do chủ hay host đặt và chỉ dừng phần chủ động.

Mỗi kỳ đánh giá (`decide`):

1. `dwell = max(2 x khoảng, 1 ngày)` tính từ lần đổi bậc trước (hay mốc bật lại): chưa đủ thì giữ.
2. Lên một bậc khi `u ≥ +0.25` và `new ≥ 1.0`, không nhanh hơn `max_tier` (mặc định B1; chỉ chủ đặt, tới B0).
3. Xuống một bậc (`unhelpful`) khi `u ≤ -0.25` và `new ≥ 1.0`; từ B7 không vào ngủ đông bằng luật này.
4. Xuống một bậc (`low_demand`, không ghi là agent sai) khi không có cơ hội chưa tiêu thụ lúc này và một trong hai:
   (A) không tín hiệu tương tác mới từ lần đổi trước và không cơ hội trong hai lần khoảng; (B) tín hiệu tương tác và cơ hội
   gần nhất đều cũ hơn `max(4 x khoảng, 3 ngày)`.
5. Còn lại giữ. Hysteresis: đổi chiều chỉ sau ít nhất một kỳ giữ.

`new = Σ w·share·decay` của tín hiệu sau `max(last_change_at, resumed_at)` (không tính tín hiệu khởi tạo ngữ cảnh). "Tương tác"
không gồm `seen_ignored`.

Công thức (6.3): `decay = 0.5^(tuổi ngày / 21)` (tuổi âm kẹp 0); `estimate = Σ w·share·v·decay / (Σ w·share·decay + 2)`;
`n_eff = Σ w·share·decay`; `confidence = n_eff / (n_eff + 4)`; `u = estimate x confidence`. Cá nhân hoá chỉ cho reaction
không lý do: `p_s(e) = (số lần e + 3)/(n + 18)`, `k = clamp(1 + 0.3 x (1/6 - p_s)/(1/6) x n/(n + 20), 0.75, 1.25)`, `n` là số
reaction không lý do của người đó trong loại ngữ cảnh (nhóm hay chat riêng), đếm mỗi nguồn một lần, tính lại mỗi kỳ.

Tín hiệu (6.1): ❤️ +0.8 w1, 😮 +0.6 w1, 👍 +0.4 w1, 😂 +0.2 w0.5, 😢 -0.2 w0.4, 😡 -0.4 w0.4; có lý do thì lý do thắng emoji
(đúng ý +0.8, quá dài -0.3, sai dữ kiện/thiếu ý/khó hiểu/lạc đề -0.6, w1, nhiều lý do lấy trung bình); trục nói/im và góp ý
chữ không tạo tín hiệu; chấp nhận đề xuất/chốt quyết định +0.6 w0.8; sửa sau kết quả, huỷ, bác đề xuất -0.4 w0.8; kiểm
khách quan ±0.5 w0.8 (mục 2a); tin chủ động đã xem, qua 24 giờ không tương tác -0.15 w0.6; reaction của agent không bao giờ. `pulse_signals` UNIQUE `(source_ref, agent_key)`; thay reaction thì dòng cũ `superseded_by`, xoá tin/agent thì `void`.

## 2a. Kiểm khách quan và đề xuất: sự kiện host nào được tính

- **Kiểm khách quan (±0.5 w 0.8), chỉ kết luận CUỐI**, một tín hiệu mỗi (mục tiêu, revision), nguồn `obj:<goal_id>:<revision>`:
  - đạt: `GoalStore.finish(..., "succeeded")`, tức A2 vừa đánh giá `met`, mọi guard `clear`, không ở bước khám phá, và (mục tiêu
    có đội) review A5 `pass` hợp lệ; đây là nơi duy nhất đóng mục tiêu là đạt;
  - không đạt: `GoalStore.finish(..., "failed")` (API có, hiện chưa đường nào gọi), hay revision bị gác `blocked/budget` trong
    `_settle` khi kiểm cuối là `not_met` (hết sạch lượt, không còn lần thử nào); kết luận `unknown` không tính;
  - KHÔNG tính: mọi `add_assessment` trong vòng làm việc (`not_met` trung gian), hạn chót qua (chỉ báo), chủ huỷ.
  - Cùng revision về sau có kết luận cuối khác (chủ nới hạn mức rồi đạt): sửa giá trị của chính tín hiệu đó, vẫn một dòng.
  - Người nhận: agent của mục tiêu (`goal_agents`), ngữ cảnh `dm:<agent_key>`, chỉ khi bật Cộng hưởng. Mục tiêu A2 có một tác
    giả sản phẩm, không có bước tổng hợp, nên luật 6.5 thu về tác giả.
  - Việc nhóm: host KHÔNG có kiểm khách quan khi chốt việc (`team_finish` chỉ ghi kết quả), nên không có tín hiệu kiểm.
- **Đề xuất** (`pulse_proposals`): lượt quét `propose` ghi sổ (nguồn, phiên bản). Cùng nguồn cùng phiên bản đã có đề xuất (chờ,
  đã nhận, đã bác) thì không đề xuất lại (5.5). Chủ quyết:
  - nhóm: thẻ trong khung chat (nút Tạo việc là nhận, +0.6, xếp việc vào hàng đợi chung của nhóm như cũ; nút Bỏ qua nay là bác,
    `POST /teams/{id}/messages/{mid}/reject`, -0.4); trạng thái ghi lên tin nên mọi tab thấy, thẻ hết nút;
  - bảng Nhịp: `POST /agents/{slug}/pulse/proposals/{id}/accept|reject`. Chat riêng: nhận thành việc giao cho trợ lý như nút
    Giao việc (Kanban, báo về chat riêng, khoá chống trùng `pp<id>`), +0.6; bác -0.4. Đề xuất trong nhóm từ bảng Nhịp đi đúng
    đường thẻ nhóm. Đã quyết rồi: 409.
  - Trưởng nhóm có Toàn quyền tự xếp việc được (enqueue của lượt quét) nên không cần duyệt đề xuất của chính mình.

## 3. Vectơ đồng hồ giả (`tests/python/test_agent_pulse_policy.py`, đều xanh)

| Kịch bản | Số đo trong test | Kết quả |
|---|---|---|
| 1 ❤️ | k 0.9962, u 0.0531 | giữ B3 |
| 2 ❤️ | k 0.9864, u 0.1315 | giữ B3 |
| 5 ❤️ ở ngày 0,5..2,5 | ngày 2: u 0.2494 (giữ); ngày 3: k 0.935, u 0.2861 | lên B2 đúng một lần, không lên B1 |
| 5 ❤️ cách nhau 3,5 ngày | u 0.2481 ở ngày 14 + 8 giờ, lớn nhất cả dải < 0.25 | giữ B3 suốt đợt |
| 10 ❤️ trong 1 phút | k 0.8214, u 0.3912 | B2 ở kỳ sau dwell, kỳ sau nữa không lên |
| rồi 10 ❤️ mỗi 1,4 ngày | | tới B1, không bao giờ B0, im lâu thì chậm lại |
| 3 👍 1 ❤️ 1 😮 | k 0.997 / 0.966 / chưa dùng 1.013 | k luôn trong 0.75-1.25 |
| Im lặng từ B3 | | ngày 2 B4, 8 B5, 22 B6, 50 B7, 110 ngủ đông (ngày 30 B6, 90 B7, 180 ngủ đông) |
| 3 tin chủ động đã xem bị bỏ qua | u -0.0221 | không `unhelpful`; `low_demand` khi không có gì khác, giữ khi có cơ hội |
| 5 / 6 "sai dữ kiện" | u -0.2378 / -0.2697 | giữ / xuống B4 (`unhelpful`) |
| Im lặng đúng (có cơ hội, phán xử im) | estimate 0 | không phạt, không `low_demand` trong hai lần khoảng |
| Gọi trực tiếp lúc ngủ đông | | về B3 ngay, giữ ước lượng |

## 4. Host (`tests/python/test_agent_pulse_host.py`)

- `_scheduler_loop` tạo `_pulse_tick` mỗi 30 giây khi cờ bận của nó rảnh. Nhịp: chiếu outbox phản hồi (T2), tạo dòng ngữ cảnh
  theo phạm vi (mỗi 5 phút), quét `seen_ignored`, nhắc chờ chủ một lần sau 24 giờ, đóng cửa sổ thay đổi chính sách, tìm lịch
  tới hạn và nhận bằng CAS (`claim_token`, `claim_until` 10 phút), điều phối lý do cho phần đã đăng ký.
- Agent bận (khoá bận, việc nhóm chạy/xếp hàng, goal A2 đang chạy): dời đúng 60 giây, không nhận.
- Lần thức: lập cơ hội (việc nhóm của agent cũ hơn khoảng hiện tại, việc bị chặn có tin mới, đề xuất của trưởng nhóm chưa ai
  xử lý, goal của agent chờ chủ quá 24 giờ), lọc theo `pulse_opportunities` (tiêu thụ một lần cho tới phiên bản mới), đánh
  giá bậc, rồi chỉ khi có cơ hội mới (hay tới lượt quét giới hạn: mỗi 3 lần thức ở active/awake, tối đa một lần mỗi ngày mỗi
  ngữ cảnh) mới gọi model.
- Lượt quét: thử khoá bận KHÔNG chờ trước (bận: dời 60 giây, không tốn lần thử), hỏi `agent_budget.try_spend` (chưa có module
  thì qua), giữ chỗ `agent_calls` purpose `scan`, `obligation = 0`, `reason_ref = pulse:<agent>:<ngữ cảnh>:<mốc>` TRƯỚC engine.
  Lịch đó đã có lượt tới model (khởi động lại) thì không chạy lần hai. Đầu ra `{"action": none|propose|enqueue|say}`; enqueue
  chỉ khi là trưởng nhóm có Toàn quyền, không thì thành đề xuất; quét giới hạn không có nguồn thì không tạo gì; `say` luôn qua
  `agent_judge.judge_proactive`, thiếu module thì `silent` với lý do `judge_unavailable`.
- Nghĩa vụ không đi qua lớp 3: test chạy bộ chạy nhóm thật với agent đang tạm dừng, ngủ đông, tắt nhịp và kiểm lời gọi trực
  tiếp và việc nhóm vẫn chạy.

## 5. Di trú và quay về

- Mở `resonance.sqlite3` bằng mã này: tạo `agent_pulse_events`, `pulse_signals`, `pulse_contrib`, `message_seen`,
  `pulse_opportunities`, `pulse_proactive`, `pulse_policy_changes`, `pulse_proposals`, `pulse_meta`, thêm cột có mặc định cho
  `agent_pulse`. Lần
  đầu (mốc `pulse_v1_upgraded_at`): mọi dòng nhịp về B3, `resumed_at = lúc nâng cấp`, agent tắt Cộng hưởng ở `off`; reaction cũ
  không thành tín hiệu.
- Quay về 0.154.x: bản cũ bỏ qua bảng và cột mới (cột đều có mặc định). Khôi phục hẳn dùng bản chụp `.pre-0.154.0` như T2.

## 6. Quyết định khi làm

1. **Luật `low_demand` (B):** đọc đúng chữ luật 4 (không tín hiệu mới từ lần đổi, không cơ hội trong hai lần khoảng) thì một
   reaction ngay sau lần đổi giữ bậc nhanh mãi mãi, trái câu "im lâu thì chậm lại". Thêm (B) "im quá `max(4 x khoảng, 3
   ngày)`". Ngưỡng 4 lần khoảng là để vectơ "5 ❤️ rải 2 tuần" (cách 3,5 ngày) vẫn giữ B3 và vectơ "10 ❤️ mỗi 1,4 ngày" vẫn tới B1.
2. **Ở B1-B2 agent dao động một bậc** khi tương tác thưa hơn dwell (luật A). Có hysteresis và dwell nên mỗi lần đổi cách nhau ít
   nhất một ngày; test ghim điều đó.
3. **Giá trị khởi tạo ngữ cảnh mới "0,5 x tổng hợp"** là một tín hiệu khởi tạo (`context_init`) mang ước lượng tổng hợp với
   `w = min(1, 0.5 x n_eff tổng hợp)`, suy giảm như tín hiệu khác, không phải bằng chứng mới, không vào `k`.
4. **Nhiều lý do chất lượng** trên một reaction: lấy trung bình giá trị.
5. **`k` chỉ đếm reaction không lý do** (reaction có lý do dùng giá trị của lý do, `k = 1`).
6. **Kiểm khách quan chỉ tính kết luận cuối** (mục 2a), không bao giờ đánh giá trung gian.
7. **Bỏ qua trên thẻ đề xuất nhóm nay là bác** (ghi máy chủ, -0.4); trước đây chỉ ẩn ở trang.
8. **Bỏ chốt rồi chốt lại** cùng tin không tính lại (nguồn đã `void` giữ chỗ UNIQUE), chống bấm qua lại để nâng điểm.
9. **Lý do lớp 3 khi tạm dừng:** host không điều phối lý do của ngữ cảnh `paused`/`off`; ngủ đông và chờ chủ vẫn được.
10. **`POST /seen`** nhận thêm `context_ref = "session:<mã phiên>"` (trang không biết `agent_key`); máy chủ đổi sang
    `dm:<agent_key>` và trả `agent: false` cho phiên không phải của trợ lý để trang thôi gửi.
11. **Đề xuất ở chat riêng** là một tin đề xuất có nguồn (chưa có thẻ riêng); ở nhóm là tin mang `proposal` (nút Tạo việc sẵn có).
12. **Không có `agent_budget`** (phần L chưa có) thì lượt quét không bị trần ngày; trần chung máy chủ và dự trữ 20% vẫn áp.
13. **Đặt lại nhịp ngữ cảnh** giữ lịch sử và ước lượng, chỉ đưa về B3 và coi bằng chứng trước mốc là cũ.
14. **Khoá bận khi chưa có kho nhóm:** khoá trong tiến trình (chưa có lượt nhóm nào để tranh khoá).

### 6.1 Sửa sau review T3 (nhánh `claude/team-adaptive-t3-fix`)

15. **Phạm vi đã giao (P2-1):** `_code_pass` đọc `deps.contexts(key)` mỗi nhịp: dòng ngoài phạm vi bị gỡ lịch (sự kiện
    `out_of_scope`), lý do lớp 3 của nó không được phục vụ; trở lại phạm vi thì có lịch lại. Đọc phạm vi lỗi thì bỏ qua lần đó, không
    gỡ. `main._pulse_team_live` (nhóm hoạt động, thành viên đang tham gia) chặn mọi đường đăng/đề xuất/xếp việc tự phát.
16. **Tín hiệu "huỷ" (P2-2):** chỉ route chủ huỷ việc (`owner_cancel=True`); trưởng nhóm ngắt, lưu trữ nhóm, huỷ việc treo không ghi.
17. **Event loop (P2-3):** route reaction chat riêng, `_pulse_wake_dm` cuối lượt chat và `deps.store()` của route nhịp chạy ở luồng phụ.
18. **P3:** thức lại, dòng mới, đặt lại, bật lại kẹp theo `max_tier`; lease 15 phút, lượt quét tối đa 9 phút; `ledger_busy` nhả
    lịch; nhãn "Chờ hạn mức" gỡ khi hạn mức đủ; nguồn bịa ra `none` (`bad_source`); huỷ/sửa yêu cầu sau bản tổng hợp phân bổ theo
    6.5; xếp việc của lượt quét ghi `team_events` và tin hệ thống; `record_contrib` không hồi sinh dòng `void`; route chỉ nhận nhóm
    agent đang tham gia (hay đã có dòng); lý do lớp 3 theo `sort_by_priority`; bảng Nhịp có ô B0..B7 và nút quay lại đổi chính sách.

## 7. Chỗ phần J và L cắm vào

- `agent_pulse_host.register_view_part(name, fn(store, agent_key) -> dict)`: mục trong `GET /agents/{slug}/pulse` (`parts`).
- `window.JavisPulseParts.push({name, render(view) -> html})`: mục trên bảng Nhịp (tự escape).
- `agent_pulse_host.register_reason_handler(code, fn(host, reason))`: phục vụ `reaction_review` (L), `related_review`,
  `wait_unblocked` (J). Hàm tự nhận lý do bằng `WakeReasons.claim(reason_id, try_busy=..., release_busy=...)` với
  `host.busy_pair(agent_key)`.
- `agent_judge.judge_proactive(*, agent_key, context_ref, draft, source_event, engine)`: `engine` là hàm không đối số trả
  `(engine, model, run)` của host (dựng lười). Trả `Decision`; `speak` mới gửi.
- `agent_budget.try_spend(agent_key, purpose, at=None) -> (ok, reason)`: host gọi với purpose `scan` trước khi giữ chỗ.
- `agent_pulse.register_policy_reverter(kind, fn(change))`, `apply_policy_change`, `record_policy_labels`,
  `revert_policy_change`, `observe_policy_changes` (6.4).
- `agent_pulse.wake(store, agent_key, context_ref, why)` cho lượt xem xét liên quan và gỡ chờ; `agent_pulse.record_event(...)`
  ghi quyết định vào `agent_pulse_events`.

## 8. Kiểm

Engine giả ở mọi nơi; không lời gọi model thật. (Phiên làm việc không ghi được ra `exports/reviews/`, nên bằng chứng nằm ở đây.)

- `test_agent_pulse_policy.py` 100 kiểm, `test_agent_pulse_host.py` 66 kiểm (gồm chặn engine thật qua `main.py`, route,
  `POST /seen`, nhận/bác đề xuất), `test_pulse_contrib.py` 49 kiểm (gồm kiểm khách quan, bác đề xuất),
  `tests/js/test_agent_pulse_ui.js` 45 kiểm: đều xanh.
- `tests/run.py pulse team resonance feedback agent_calls i18n icons route_table`: 88/89, cái đỏ là `test_resonance_perf.py`
  (trễ event loop 0,114 giây > 0,1). So với `origin/claude/team-adaptive-t3` trong worktree sạch: bản gốc 4/4 xanh, nhánh 3/4 đỏ,
  nên là lỗi thật của nhánh: `GoalStore` dựng trong event loop ở GET đầu tiên và `agent_pulse.ensure` ghi nhiều lần. Sửa ở
  `865758bf` (kho đã đủ bảng thì không ghi gì; lần đầu tạo bảng trong một giao dịch): 4/4 xanh. Chạy lại `pulse feedback
  agent_calls team_adaptive rollback resonance_a1`: 20/20 xanh.
- `tests/run.py --js`: 193/193 xanh.
- Soi giao diện (khung tĩnh dùng đúng `console.css`, `style.css`, `agent-pulse.js`, i18n; phục vụ cục bộ; 375x812): tối và
  sáng, vi và en, không cuộn ngang (scrollWidth 375), chữ nhỏ nhất 16px, nút và ô chọn cao 44px. Chưa soi trên dashboard thật
  (sandbox cổng 7788) và chưa soi trên điện thoại thật.

## 9. Hiệu năng (sửa sau bench T4)

GOAL mục 10: học, lưu lịch, tìm kiếm hay tự rà soát không được làm lag các tab. Quy ước R5 của T1: mọi đọc/ghi SQLite và
file trong đường async chạy ở luồng phụ (`run_io` / `asyncio.to_thread`). Bench T4 thấy hai chỗ vi phạm: lô phán xử ghi kho
ngay trên event loop, và nhịp pulse 0,5 tới 3,4 giây mỗi nhịp, trễ loop tới 217 ms chỉ với nhịp.

### 9.1 Đã chuyển khỏi event loop

- `io_offload.py` (mới): `run_io` (dời từ `team_runner`, tên `team_runner.run_io` giữ nguyên), `run_io_quiet` cho bước dọn ở
  nhánh huỷ, `call_hook` (hàm móc thường chạy ở luồng phụ, coroutine function chạy trên loop), `LoopMarker` (mốc engine do
  engine gọi đồng bộ được ghi ở luồng phụ, chờ xong trước khi chốt dòng sổ).
- Bộ phán xử: `judge_team_message`, `judge_proactive`, xét lại chat riêng (`serve_reason`, `_rejudge_dm`,
  `_rejudge_with_call`), hết hạn chờ (`_expire_dm`) tách thành phần ĐỒNG BỘ `_..._prepare` / `_..._finish` chạy qua `run_io`;
  coroutine chỉ còn phần chờ model. Kho phán xử, `resonance_on` (`agent_any`), giữ chỗ/mốc/chốt/hoàn sổ lượt, lý do thức,
  lịch sử, hạn mức, chờ, người gửi thường (`_judge_send`) đều ở luồng phụ. Ngữ nghĩa giữ nguyên: giữ chỗ TRƯỚC engine, hoàn
  khi engine chưa dựng được hay chờ chỗ quá hạn, `interrupted` khi bị huỷ sau mốc engine. Mới: bị huỷ ngay sau khi giữ chỗ
  (đang ở bước chuẩn bị, hay đang chờ chỗ trong 2 lô) thì dòng sổ được hoàn (`_undo_reserve`, như mẫu `undo` của `run_io`);
  bị huỷ ngay sau khi nhận lý do thì lý do được trả về (`_undo_claim`).
- Nhịp pulse: `tick` kiểm kho ở luồng phụ và chạy hàm `project_pending` thường ở luồng phụ; `wake_step` gom toàn bộ phần code
  (cơ hội, ước lượng, đếm lý do, nhả lịch) vào MỘT lần chuyển luồng (`_wake_code`); hạn mức, `engine_for`, `persona`,
  `can_enqueue` và lần ghi cuối của lượt quét ở luồng phụ. `_learn_tick` đọc danh sách agent ở luồng phụ; lượt xem xét
  reaction và tự rà soát (`agent_review`) đọc kho, hạn mức, nguồn, sự kiện và nhả khoá bận ở luồng phụ. Gỡ chờ khi chủ nhắn
  chat riêng (`_judge_dm_owner_message`) chạy nền ở luồng phụ, lượt chat không chờ. `_reply_turn` đọc nhóm qua `_io`.
- `_pulse_busy`: trước đây mỗi agent tới hạn quét lại MỌI việc nhóm hai lần. Nay `busy_snapshot` (dep mới của `PulseHostDeps`,
  `main._pulse_busy_snapshot`) đọc khoá bận (`team_store.busy_keys`), việc nhóm đang chạy/xếp hàng và goal đang chạy MỘT lần
  mỗi nhịp.

### 9.2 Bộ chiếu: có làm lại việc không

Đã kiểm: `project_pending` CHỈ chiếu dòng `effect_state = 'pending'` (dòng `pending_author` của chat riêng đi
`_dm_resolve_pending_authors` trước rồi mới về `pending`); dòng `done` không bao giờ được chiếu lại; ghi ngược trạng thái chỉ
ghi khi trạng thái tính ra khác trạng thái đang có. Phần lặp là ĐỌC: mỗi nhịp 30 giây, với tối đa 200 reaction đang "Chờ xem
xét"/"Đang xem xét", đọc lại từng dòng (dòng nhật ký, nguồn lý do, reaction hiện tại: ba kết nối SQLite mỗi dòng). Nay đối soát
theo lô (`_refresh_open`): một câu đọc reaction (`open_reaction_rows`), một câu đọc nhật ký (`reaction_log_rows`), một câu đọc
nguồn (`WakeReasons.sources_by_ref`), rồi chỉ ghi reaction có trạng thái lý do đổi. Kho không có hàm đọc theo lô (kho giả của
test cũ) đi đường từng dòng như trước. Giới hạn 200 dòng mỗi nhịp giữ nguyên (đã có từ T2: quá 200 reaction mở thì các dòng
sau không được đối soát; đọc theo lô làm việc nâng giới hạn này về sau rẻ).

### 9.3 Số đo (bench T4, engine giả)

Điều kiện: `tools/team_adaptive_bench.py` của nhánh `claude/team-adaptive-t4-work` (không commit vào nhánh này), chạy ngoài
repo bằng wrapper trỏ `ROOT` vào mã cần đo; tham số mặc định (12 nhóm x 1.500 tin, 1.500 reaction seed, 8 trợ lý, 30 lần mỗi
API, 8 luồng, 24 tin mở lô phán xử, 5 nhịp, engine giả 5 ms), `--no-ui`. Máy local Windows 11, Python 3.12.10, 8 CPU; KHÔNG
phải số đo VPS. Gốc = mã `server/` của `origin/claude/team-adaptive-t3` (`92202224`), nhánh = `46b49f1f`. Hai vòng chạy xen kẽ
gốc/nhánh liền nhau trên cùng máy (máy có tải nền từ phiên khác, nên so trong cùng vòng):

| Chỉ số | Gốc v1 | Nhánh v1 | Gốc v2 | Nhánh v2 |
|---|---|---|---|---|
| Một lần chiếu outbox ổn định (ms) | 788-837 | 13-16 | 1.408-2.069 | 12-13 |
| Nhịp pulse riêng: thời gian mỗi nhịp (ms) | 3.198-6.093 | 237-3.197 | 6.011-8.230 | 321-2.718 |
| Nhịp pulse riêng: trễ loop lớn nhất (ms) | 172 | 68 | 715 | 51 |
| Pha đồng thời: trễ loop lớn nhất (ms) | 477 | 103 | 331 | 139 |
| Pha đồng thời: request p95 (ms) | 1.572 | 822 | 1.454 | 966 |
| Sóng lô phán xử riêng: trễ loop lớn nhất (ms) | 36 | 116 | 40 | 53 |
| Chỉ request: trễ loop lớn nhất (ms) | 31 | 46 | 62 | 29 |

Nhịp đầu tiên của mỗi lần chạy dài hơn (làm mới phạm vi `CONTEXT_REFRESH_S` cho mọi agent). Chẩn đoán `--stall-watch` (chụp
ngăn xếp luồng loop mỗi lần bị giữ quá 50 ms, một lần chạy mỗi bên): gốc có 40 lần trong mã phán xử và sổ lượt (`add_decision`,
`get_decision`, `agent_any`, `_reserve`, `mark_engine`, `settle`, `cases`, `get_offset`); nhánh không còn lần nào trong mã phán
xử hay nhịp. Còn lại ngoài phạm vi: `team_runner._reply_turn` và nhả khoá trong `agent_review` (đã chuyển sau lần đo, commit
kế tiếp) và route `POST /sessions/{id}/messages/{mid}/reaction` (ghi kho trên loop, chưa sửa ở đây). Trễ loop còn lại ở pha
đồng thời (khoảng 100 tới 140 ms, một hai mẫu) không có ngăn xếp trong mã Javis: tranh GIL giữa nhiều luồng phụ cùng chạy.
Sóng lô phán xử riêng dao động (một lần 116 ms) cùng lý do. Số lô phán xử giả trong pha đồng thời có lúc dưới 24 vì bench chỉ
chờ việc nền của bộ phán xử, không chờ tác vụ `run_message` do route sinh ra (cửa sổ đo, không phải mất lượt).

Test hồi quy: `tests/python/test_t3_event_loop.py` (kho phán xử và kho resonance chậm ở MỖI lần mở kết nối 110 ms và ở hàm kho
chính 250 ms: lô nhóm có lượt tự lên tiếng, tin chủ động + chờ + gỡ chờ + xét lại + gửi ở chat riêng, nhịp pulse với mọi hàm
host chậm: khoảng trống loop < 100 ms và không hàm kho nào chạy trên luồng loop; huỷ ngay sau giữ chỗ thì hoàn; bộ chiếu hai
nhịp không chiếu lại, không ghi lại, đọc theo lô). Trên mã gốc test này đỏ (trễ 4,1 giây ở lô nhóm, 2,8 giây ở chat riêng).

## 10. Auto toàn quyền: lượt tự thức có công cụ, mốc tự hẹn (2026-11-14)

Chủ repo 14/11/2026, so với tin chủ động của ChatGPT (nhắc lấy BIB sáng hôm trước giải chạy, báo bãi xe đổi tối hôm trước):
"bật auto là chấp nhận cho full quyền, kể cả quyền hành động"; agent "sẽ quét các tool, tự đặt lịch nhắc, và tìm những gì
hữu ích"; tin "không phải là thông báo nữa, mà kiểu như gợi ý và nhắc nhở", ngắn, dễ hiểu.

- **Ở đâu:** `PulseHostDeps.tool_scan(key, ctx)`. `main._pulse_tool_scan`: chỉ `dm:<agent_key>` (nhịp chỉ chạy cho trợ lý
  bật Auto). Nhóm giữ lượt chỉ chữ của mục 4: quyền trong nhóm do Toàn quyền của nhóm quyết. `JAVIS_PULSE_TOOLS=0` tắt hẳn.
- **Mọi lần thức đều quét** (bỏ luật "mỗi 3 lần thức, tối đa một lần mỗi ngày" cho ngữ cảnh này). Số lần do bậc (học từ
  phản hồi, mặc định 1 ngày, nhanh nhất `max_tier`), hạn mức ngày của agent và trần chung giữ.
- **Lượt:** `req["tool_turn"] = True` qua `_team_engine_for` (hub `full`, thư mục brain, như bước Work của nhóm). Hệ thống là
  persona + `TOOL_SCAN_RULES`; lời nhắc là `scan_context` (giờ của chủ có thứ và múi giờ, hồ sơ, chỉ mục bộ nhớ 6.000 ký tự,
  nhật ký hội thoại hôm qua và hôm nay 5.000 ký tự cuối, 12 tin chat riêng gần nhất đánh dấu tin chủ động và phản hồi, mốc
  đang chờ) + lý do thức. `_pulse_engine_for` gắn danh tính lượt `pulse` (chat_id `web:<phiên chat riêng>`, `job`
  `pulse:<mã lượt>` cho `once_ledger`); `team_dispatch.SCHEDULED` nhận `pulse` như nhắc hẹn và việc Kanban.
- **Đầu ra:** `{"action": none|say, "kind": reminder|suggestion, "text", "did": [...], "follow_ups": [{"at", "note"}],
  "cancel_follow_ups": [id]}`. `parse_action` lấy khối JSON cuối có `action` hợp lệ.
- **Việc đã làm luôn được báo:** `did` khác rỗng thì tin đi thẳng, KHÔNG qua bộ phán xử (`verdict = "acted"`); chọn none hay
  propose mà có `did` thì vẫn gửi một tin liệt kê việc đã làm. Tin không kèm việc vẫn qua `judge_proactive` như mục 4.
- **Mốc tự hẹn** (`pulse_followups`, tạo cùng các bảng T3 trong `ensure`): giờ không múi giờ hiểu theo múi giờ của chủ; kẹp
  [10 phút, 60 ngày]; bỏ trùng (cùng ghi chú, cách dưới 30 phút); tối đa 3 mốc mỗi lượt, 8 mốc đang chờ mỗi ngữ cảnh.
  `followup_wakes` (chỉ đọc) tìm dòng có mốc tới giờ chưa kích hoạt ở trạng thái có lịch; host nhận bằng CAS như lịch theo
  bậc, đang bận thì để nhịp sau (không ghi gì). `take_due_followups` đưa mốc vào danh sách cơ hội (`followup:<id>`) và đánh
  dấu `fired_at`; lượt chạy xong thì `close_followups`. Lượt lỗi: mốc vẫn chờ nhưng không kích hoạt lại mỗi nhịp, đi theo
  lần thức theo bậc kế tiếp. Tạm dừng, tắt, ngủ đông, chờ chủ: mốc không đánh thức.
- **Gửi:** `meta.kind` theo tin. `main._PULSE_KIND_GROUP`: nhắc nhở vào nhóm `reminder` (khẩn), gợi ý vào nhóm mới `suggest`
  ("Gợi ý của trợ lý", `notify_policy.GROUP_DEFAULT_MODE` = đáng chú ý). Tin không loại (lượt chỉ chữ) giữ đường cũ.
- **Giao diện:** bật Auto hỏi lại một lần (`resonance.t0_on_confirm`); câu "Auto không phải Toàn quyền" thay bằng
  `resonance.auto_full`.
- **Test:** `tests/python/test_pulse_auto_full.py` (host, engine giả), `tests/python/test_pulse_auto_full_main.py` (nối ở
  main, chặn engine thật).
