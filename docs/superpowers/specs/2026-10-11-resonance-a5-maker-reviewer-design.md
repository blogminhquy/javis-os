# Resonance A5: một agent làm, một agent review (thiết kế)

**Trạng thái:** thiết kế **đã chốt** (review thiết kế vòng 3 đạt tại `56f7ab50`); **mã đạt review vòng 2 tại `05e9b065`; pilot thật real-2 tại `33cec518` được reviewer chấp nhận trong phạm vi một mẫu `pass_first` (1 lượt làm, 1 lượt review, 0 chat; chưa chứng minh vòng sửa bằng model thật); chưa phát hành** (hướng dẫn [resonance-a5-team](../../dev/resonance-a5-team.md), biên bản [resonance-a5-verification](../../dev/resonance-a5-verification.md)). Phần dưới giữ nguyên nội dung đã chốt; đã sửa theo review vòng 1 (R1 đến R5) và review vòng 2 (P2 bộ đếm thử lại, lịch đối soát, hai vòng sửa); chủ dự án chọn phương án A cho file sửa tay (mục 0). Mã A5 đạt review mã vòng 2 tại `05e9b065` (biên bản, kịch bản pilot [resonance-a5-pilot](../../dev/resonance-a5-pilot.md)); pilot thật real-2 dùng 2 lượt model việc nền trong trần 4; chưa merge, không đụng VPS. Review mã vòng 1 làm rõ hai điểm đã nằm trong thiết kế: cổng review áp cho MỌI bản đạt kiểm của mục tiêu có đội (cả `maintain` và bước khám phá, mục 4.2, 5.1), và lượt chưa tới mốc gọi engine là lượt chắc chắn chưa chạy (mục 5.6, 6.2). Các mặc định ở mục 16 theo khuyến nghị của review vòng 1; đó là cấu hình sản phẩm đề xuất, **không phải cấp phép chạy pilot**.

- **Nhánh:** `claude/resonance-a5-maker-reviewer`, PR nháp #616, số **0.109.0** sau khi tích hợp `main` 0.108.0 (lúc thiết kế giữ 0.101.0; 0.97.0 cũ đã thấp hơn `main`).
- **Nền:** lúc thiết kế và review mã là `main` `a02663cb` (0.100.0); tích hợp `main` `c4fb614d` (0.108.0) trước merge. A1 0.87.0, A2 0.88.0, A3 0.89.0, A4 0.96.0 (`d36ebb3e`) đã phát hành; 0.100.0 thêm tag cho agent (mục 4.5).
- **Đầu vào:**
  - [lộ trình agent](2026-10-08-resonance-agent-scope-roadmap.md) mục 7 và 8.
  - [thiết kế A4](2026-10-10-resonance-a4-handoff-grants-design.md): bất biến 5, mục 5.4 `narrow`, mục 12.5 các ca để lại cho A5.
  - [thiết kế A3](2026-10-09-resonance-a3-feedback-learning-design.md) mục 16.
  - Review vòng 1: `exports/reviews/PR-616-A5-design-r1-review.md`; review vòng 2: `exports/reviews/PR-616-A5-design-r2-review.md`.
  - Mã hiện tại của `server/resonance*.py`, `server/main.py` (workflow, `_resonance_engine`), `system/plugins/javis-goal`.
- **Mức bằng chứng:** đọc mã và tài liệu, cộng probe của reviewer chạy trên nền mới (mục 18). Chưa chạy thử gì cho A5.
- **Số dòng mã:** dẫn theo `a02663cb`. `server/resonance*.py` không đổi từ `dc18942e`, nên số dòng ở các file đó giữ như vòng 1. `server/main.py` đã đổi theo PR tag.

## 0. Thay đổi vòng 2 (theo review vòng 1)

| # | Lỗi review | Sửa ở mục | Ca nghiệm thu |
|---|---|---|---|
| R1 (P1) | Gắn đội ở `assign_goal` bỏ sót đường tạo chính (`form_goal` gọi `create`) | 4.2 (gắn đội trong giao dịch `create`), 9.2, 16 D11 (mục tiêu cũ qua `assign_goal` không có đội) | T31 đến T36 |
| R2 (P2) | Khoá chống trùng `review_due` thiếu revision và danh tính lần review | 5.6 (bảng định danh lịch review), 10 (mã và lớp), 9.1 (`reviews.bundle_ref`) | T11, T37 đến T41 |
| R3 (P2) | Tắt rồi bật reviewer không tiếp tục được vì version luôn tăng | 4.2 (ghim mã bền, không ghim version), 5.5, 7.3 (đường phục hồi), 11 (thao tác trên thẻ) | T18, T42 đến T46 |
| R4 (P2) | Ngân sách chưa phủ A3 (làn M) và không khớp lời hứa 4 + 4 | 6 (bảng mọi đường giữ, hoàn, tiếp quản; làn M tắt khi có đội; lớp `FIX`; bảng vết) | T5, T6, T47 đến T54 |
| R5 (P2) | T10 review bản sửa tay mà không có snapshot hợp lệ | 5.5 (bản sửa ngoài luồng chặn chốt, không review), 4.3 (kiểm hash snapshot) | T10, T55 đến T58 |

**Vòng 3 (theo review vòng 2):**

| # | Điểm | Sửa ở mục | Ca nghiệm thu |
|---|---|---|---|
| P2 | Huỷ trước engine vẫn ăn số lần thử review: tách số thứ tự hàng (`seq`) khỏi số lần tính (`charged`); một hàm hoàn duy nhất cho `abort_action` và `release_call` | 5.6, 6.2, 6.4, 6.5 (V8), 9.1, 9.2 | T61 đến T65 |
| Lịch | Hành động review chỉ hẹn `action_recovery` (đối soát bằng code, như mã nền cho hành động không phải `work`), không dùng `recovery` lớp AUTO của vai làm; `review_retry` chỉ thêm sau đối soát | 5.6, 9.2 | T66 |
| Vòng | Bất đẳng thức chính xác: kết luận `needs_changes` hợp lệ thứ k sinh lượt sửa khi k ≤ 2, thứ 3 chặn; kết luận `mismatch` hay `stale` không tính, không sinh lượt sửa | 5.4, 5.1 | T4, T67 |
| Quyết định | Chủ dự án chọn phương án A (12/10/2026): mục tiêu có đội không chốt trên bản sửa tay | 5.5, 16.2, D14 | T10, T55, T56 |

Các điểm "lưu ý" của review vòng 1 cũng được ghi vào nội dung chính:
- Lease không chặn chat maker: mục 7.2 và T59.
- `too_large` cần người xử lý: mục 5.2 và bảng dừng 5.1.

## 1. Mục tiêu và ngoài phạm vi

Lộ trình (mục 7) đặt các yêu cầu:
- "một agent làm và một agent review, một goal chịu trách nhiệm cuối";
- review gắn đúng hash và revision;
- reviewer không tự sửa tiêu chí;
- hạn mức chung có chia phần;
- bản đổi sau review phải được review lại;
- owner dừng thì cả hai dừng;
- không tự sinh agent mới để vượt chốt.

**Người dùng thấy:**
- Trên trang một agent đã bật Cộng hưởng, chủ dự án chọn một agent khác làm **người review**. Từ đó mục tiêu MỚI của agent này đi qua review trước khi được coi là đạt.
- Thẻ mục tiêu cho biết:
  - ai đang làm, ai đang review;
  - bản nào (mã ngắn của bản) đã được review, và kết luận;
  - vì sao đang chờ;
  - lượt còn lại của từng vai.
- Review đòi sửa thì agent làm tự sửa theo góp ý, có giới hạn số vòng. Hết vòng hay hết lượt thì dừng và báo, không tự nới.

**Giữ nguyên:**
- Chat thường vẫn là chat thường; không áp Cộng hưởng hay review lên cuộc trò chuyện không có mục tiêu.
- Hợp đồng nộp và đăng của A4 không đổi: `javis_submit_deliverable`, `host_publish` bốn bước, quyền theo phạm vi D1.
- Nhịp tim A2 (thức có lý do, không hỏi model định kỳ) và vòng phản hồi A3 (reaction không đổi lịch, không thay kết luận) không đổi. Riêng làn M của A3 tạm tắt trên mục tiêu có đội (mục 6.3).
- Tiêu chí `human_confirmation` và guard giữ nguyên quyền phủ quyết.

**Ngoài phạm vi:**
- Đội hơn hai agent, agent tự sinh agent, supervisor tổng quát, mục tiêu con.
- Giao việc từ chat thường chưa được chốt.
- Thay đổi hành vi file đích có sẵn (`target_occupied`), và tiếp nhận một file bất kỳ người dùng sửa (mục 5.5).
- Tối ưu VPS; tự sửa mã sản phẩm.
- Review chạy trong lượt chat (reviewer chỉ chạy ở việc nền).
- Lệnh nâng hạn mức (hiện chưa có; mục 16 D13).
- Chọn reviewer hay đội bằng tag (mục 4.5).

## 2. Hiện trạng: dùng lại và khoảng trống

| Cần cho A5 | Đã có | Ở đâu | Khoảng trống |
|---|---|---|---|
| Danh tính agent do host cấp | `agent_key` bền, `config_version`, `agent_gate` | `resonance_store.py` `agent_set_enabled` (:492), `_bump_agent` (:456); `resonance.py` `agent_gate` (:502); `_agent_block` (:680) | Chưa có vai thứ hai trên một mục tiêu |
| Đường tạo mục tiêu | `form_goal` gọi `store.create`; `create` ghi `goal_agents` trong cùng giao dịch | `resonance.py` :947-993; `resonance_store.py` :708-786. Hai lối vào: tool `javis_goal` (`system/plugins/javis-goal/plugin.py` :206) và `POST /goal-requests` (`resonance_api.py` :202-242) | Chưa gắn đội. `assign_goal` (:2114) chỉ cho mục tiêu CHƯA gán (mục tiêu cũ) |
| Giữ chỗ lượt trước khi gọi, ghi bền | `begin_action` trong `BEGIN IMMEDIATE`, `_ReservedCall`, `release_call`, `abort_action`, `_reconcile` | `resonance_store.py` :1439, :1856, :1148; `resonance.py` :1895, :2213 | Chưa chia phần theo vai; `release_call` không biết lượt của vai nào |
| Lượt của làn M (A3) | `begin_experiment` giữ cả lượt thử lẫn một lượt giữ (`call_holds`); hoàn qua `release_trial_call`, `finish_experiment(refund)`, `_release_hold` | `resonance_store.py` :1540-1615, :1617, :1622, :2505 | Đi thẳng vào `calls_used`, ngoài mọi sổ vai |
| Trần chung | `call_ceiling`, `_under_ceiling` | `resonance_store.py` :32, :53 | Dùng nguyên |
| Đánh thức có lý do | `wake_reasons` chống trùng vĩnh viễn theo (`goal_id`, `code`, `source_ref`), `CLASSES`, `HB.decide`, `auto_allowed` | `resonance_store.py` :153, :968-981, :1037; `resonance_heartbeat.py` :40, :112, :130 | Chưa có mã lý do review; `CLASSES` ánh xạ một mã thành một lớp cố định |
| Chống chạy chồng | lease mục tiêu, CAS `claim_wake`, CAS revision | `resonance_store.py` :1424, :1341 | Dùng nguyên; cả hai vai dùng chung một lease mục tiêu |
| Đánh giá theo revision | `evaluate_artifact`, `Assessment` met/not_met/unknown, `_human_verdict` gắn sha bytes hiện tại | `resonance.py` :1578, :1074, :1548-1571 | Chưa có điều kiện review |
| Sửa ngoài luồng | `_source_drift`, `observe_source` (mốc quan sát tách khỏi mốc đăng), `waiting/source_drift` | `resonance.py` :1756-1783, :2864-2880 | A2 vẫn chốt đạt khi bản sửa tay đạt kiểm khách quan; A5 phải chặn với mục tiêu có đội (mục 5.5) |
| Bản được tiếp nhận và ảnh chụp | `published(goal_id, path, sha256, action_id)`, `submissions` (A4, có `evidence_id`), `evidence_links(action_id, evidence_id, content_hash)`, `adopt_submission` | `resonance_store.py` :111, :296, :100, :3852 | Dùng nguyên làm nguồn ảnh chụp review |
| Engine việc nền chỉ chữ | `_resonance_engine`, `pick_text_only_link`, `SYSTEM_PROMPT` | `main.py` :2040; `resonance.py` :181, :46 | Dùng nguyên cho cả hai vai |
| Bằng chứng | `_ResonanceEvidence`, `_put_evidence` lỗi thì None | `main.py` :2281; `resonance.py` :1525 | Dùng nguyên |
| Quyền ghi theo phạm vi | grants root/revision, bindings, `authority_clock` | `resonance_store.py` A4 | Reviewer không nhận quyền ghi nào |
| Reviewer trong workflow | `verify_agent`, JSON `{pass, reason, fixes}`, vòng sửa | `main.py` :9384-9440, :9814-9880 | KHÔNG dùng nguyên khối (xem dưới) |

**Vì sao không chạy review qua workflow:**
- Bước `verify_agent` đọc kết luận từ chữ tự do bằng regex.
- Thiếu JSON hay lỗi engine đều tính là **đạt** (`main.py` :9406, :9414, :9872, :9880).
- Bước review không đạt vẫn hoàn tất và chuyển tiếp.
- Không đếm lượt gọi, không chạm trần Resonance.
- Chạy engine của agent, có công cụ và nhà cung cấp dự phòng.

A5 chỉ dùng lại **lời dặn review** ("mặc định coi kết quả là sai") và **mẫu góp ý cho vòng sửa** (bản trước kèm lý do và cách sửa). Kết luận đọc theo kiểu đóng khi lỗi, lượt đi qua sổ Resonance.

**Hai sự thật phải nói rõ:**
- **Việc nền KHÔNG chạy bằng engine của agent.** Cả lượt làm và lượt review đều chạy bằng model "việc nền" chung của người dùng, chỉ chữ, không công cụ (`resonance.py` :527-529). Hai vai dùng cùng một model (D3); khác nhau ở danh tính, lời dặn vai và dữ liệu được thấy, không phải ở bộ não độc lập.
- **Lời nhắc việc nền hiện không đưa nội dung file agent vào** (`_work_prompt`, `resonance.py` :1862). A5 thêm phần mô tả vai của reviewer: thân file agent, có giới hạn độ dài, đánh dấu là dữ liệu. Phía agent làm giữ nguyên.

## 3. Bất biến

1. **Host quyết định ai làm gì.** Vai và `agent_key` của mỗi vai do host ghim lúc tạo mục tiêu. Lời model không đổi được vai, tiêu chí, quyền hay hạn mức.
2. **Review gắn đúng bản.** Một kết luận review chỉ có giá trị cho đúng bộ ghim (mục 5.5):
   - `goal_id`, `revision`;
   - bản được tiếp nhận và sha của nó;
   - hash tiêu chí;
   - `reviewer_agent_key` và `reviewer_config_version` lúc review.

   Đổi bất kỳ thành phần nào thì kết luận cũ không dùng để chốt.
3. **Review không thay phủ quyết.** Review đạt không xoá guard, không thay `human_confirmation`, không bù cho tiêu chí khách quan chưa đạt.
4. **Đóng khi lỗi.** Không đọc được kết luận, lỗi engine, lỗi lưu bằng chứng, dữ liệu lệch, ảnh chụp không khớp hash đều là `unknown`, không bao giờ là đạt.
5. **Một sổ, chia phần, không đường vòng.** Mọi lượt model của mục tiêu có đội đi qua sổ vai trong cùng giao dịch với `calls_used` và trần chung.
   - Đường nào không mang được vai (làn M của A3) thì bị kho từ chối, không đi ngoài sổ.
   - Giữ chỗ trước khi gọi; chỉ hoàn khi chắc engine chưa chạy; không tự nới.
6. **Dừng thắng.** Tạm dừng, huỷ, thu hồi quyền, tắt agent có hiệu lực cho cả hai vai theo phạm vi; lượt cũ không hưởng quyền cấp lại.
7. **Chỉ chốt trên bản được tiếp nhận.** Mục tiêu có đội chỉ được chốt đạt khi bytes đang ở file đích khớp bản được tiếp nhận đã review. Bản sửa ngoài luồng không tự thành bản được tiếp nhận.

## 4. Mô hình đội

### 4.1 Hai vai

| Vai | Là ai | Được làm | Không được |
|---|---|---|---|
| Làm (`maker`) | Agent chịu trách nhiệm cuối của mục tiêu, đúng là agent của `goal_agents` | Lập và sửa mục tiêu trong chat (A1), nộp bản (A4), làm việc nền | Tự chấm đạt; đổi người review |
| Review (`reviewer`) | Một agent Cộng hưởng khác cùng brain, do chủ dự án chọn | Đọc ảnh chụp bản đã tiếp nhận và tiêu chí, trả kết luận | Ghi file, nộp bản, sửa tiêu chí, quyền hay hạn mức, chạy trong chat |

Reviewer không có grant nào (không root, không revision). Mọi hành động có tác động vẫn đi qua cổng A4 của vai làm.

### 4.2 Chọn hai agent, gắn đội vào mục tiêu

**Chọn cặp (bảng `team_pairs`, chỉ chủ dự án):**
- Chủ dự án bật trên trang agent làm. Ô **Người review** liệt kê các agent đã bật Cộng hưởng (`resonance_agents` `active`) trong cùng brain, trừ chính nó.
- Chọn một agent là bật chế độ đội cho agent này; bỏ chọn là tắt. Không có ô cài đặt nào khác: hạn mức và số vòng dùng mặc định (mục 6).
- Cặp lưu theo `agent_key` của hai bên, không theo slug hay tag. Mỗi lần đổi tăng `team_pairs.config_version`.

**Gắn đội vào mục tiêu MỚI (R1):** một hàm kho dùng chung `_attach_team(c, goal_id, brain_id, maker_key, now)`, gọi **trong chính giao dịch `create`**, ngay sau dòng `goal_agents` (`resonance_store.py` :757).
- `create` là đường duy nhất tạo mục tiêu có agent. Cả tool `javis_goal` và `POST /goal-requests` đi qua `form_goal` gọi `create`, nên cả hai lối vào được phủ mà không thêm giao dịch thứ hai. Không có khe nào để mục tiêu bắt đầu chạy trước khi có đội: lý do `created` được ghi cùng giao dịch.
- Cặp đang bật: ghi `goal_team(status='active')` ghim `reviewer_agent_key`; ghi hai dòng `team_calls` (maker 4, reviewer 4); đặt `goals.budget_calls = TEAM_DEFAULT_CALLS = 8`, thay mặc định 6 mà `form_goal` truyền vào.
- **Reviewer đang không dùng được lúc tạo** (tắt, `missing`, đã nghỉ) mà cặp vẫn bật: vẫn gắn đội. Cổng vai review (mục 7.3) chặn ở lần thức đầu với lý do cụ thể. Không lặng lẽ bỏ review.
- Cặp tắt hay không có cặp: không có `goal_team`; mục tiêu chạy như A4.
- **Idempotent:** cùng `idempotency_key` thì `create` trả mục tiêu cũ trước mọi lệnh ghi (:723-727). Tạo lặp cùng tin không thay reviewer, không thay budget, không thêm `team_calls`.
- Đổi cặp sau khi tạo không ảnh hưởng mục tiêu đã có: reviewer đã ghim trong `goal_team`.

**Mục tiêu cũ đi qua `assign_goal` (D11):** `assign_goal` (:2114) chỉ gán mục tiêu CHƯA có agent (tạo trước A1 hay bởi bản cũ), có thể đã tiêu lượt. A5 **không** gắn đội ở đường này.
- Mục tiêu đó chạy như A4. Thẻ ghi "Mục tiêu có từ trước, không có người review", và sự kiện `agent_assigned` ghi `team: "not_attached_legacy"`.
- Lý do: gắn đội lúc này buộc phải chia lại `calls_used` đã tiêu hay nâng hạn mức, đúng điều review cấm. Đây là thao tác của chủ dự án, hiện rõ trên thẻ, không phải đường agent tự bỏ review.
- Gọi `assign_goal` cho mục tiêu đã có agent vẫn bị từ chối như hiện tại (probe xác nhận).

**Tách đội khỏi một mục tiêu (`team_detach`, chỉ chủ dự án):**
- `goal_team.status` sang `detached`, ghi `detached_by` và sự kiện `team_detached`. Từ đó mục tiêu chốt theo luật A4.
- Lệnh nói rõ trên thẻ: "Bỏ yêu cầu review cho mục tiêu này". Không có tool hay đường model nào gọi được nó.
- `team_calls` giữ nguyên làm hồ sơ, lượt đã dùng không xoá.
- A5 không hỗ trợ gắn lại đội hay đổi reviewer giữa chừng.

### 4.3 Reviewer được thấy gì

Host dựng đầu vào review từ dữ liệu của chính host, không cho reviewer đọc file hay công cụ:
- **Hiểu biết mục tiêu và tiêu chí** của revision hiện tại, đánh dấu là dữ liệu. Bỏ qua tiêu chí `human_confirmation` (người dùng tự xác nhận).
- **Ràng buộc người dùng đã nêu.**
- **Ảnh chụp bản được tiếp nhận** (mục 5.5): bytes từ bằng chứng của bản đang ở mốc đăng (`published.action_id`).
  - Bằng chứng đó là `evidence_links.content_hash`, hay `submissions.evidence_id` của bản nộp A4.
  - Không đọc lại file đích.
  - Trước khi giữ chỗ, host băm lại bytes ảnh chụp. Khác `artifact_sha` của bộ ghim: `unknown/snapshot_mismatch`, không giữ chỗ, không gọi engine.
  - Dài hơn `REVIEW_INPUT_MAX_CHARS` (60.000): không cắt, không gọi engine, `unknown/too_large`.
- **Mô tả vai của reviewer:** thân file `agents/<slug>.md` của reviewer, tối đa 4.000 ký tự, đánh dấu là dữ liệu.
- **Không thấy:** lịch sử chat, lời nhắc của agent làm, kết luận review cũ (tránh neo theo kết luận trước), đường dẫn ngoài brain, tag của agent.

### 4.4 Ai đổi được gì

| Đối tượng | Đổi bởi | Không đổi bởi |
|---|---|---|
| Cặp `team_pairs` | Chủ dự án (Principal `owner`) | Agent, model, tag |
| `goal_team` của một mục tiêu | Host lúc `create`; chủ dự án tách đội | Đổi cặp sau đó, model |
| Tiêu chí, quyền, hạn mức | Như A1 đến A4 | Reviewer |

### 4.5 Tag không phải đội (0.100.0)

Từ 0.100.0 agent mang nhiều **tag** (`docs/dev/agent-tags.md`). Tag chỉ để phân loại và tìm agent:
- Tag **không** chọn người review, không lọc danh sách ô Người review, không ghép cặp.
  - Danh sách lấy theo trạng thái Cộng hưởng, không theo tag.
  - Ô chọn có thể hiện tag bên cạnh tên để dễ nhận, nhưng chỉ là nhãn.
- Tag **không** cấp quyền, không đổi hạn mức, không bật Cộng hưởng.
- Tag **không** là nhóm chat. Gắn tag không thêm agent vào nhóm chat của team, và đội A5 không tạo nhóm chat.
- Đổi tên hay xoá tag không chạm `team_pairs` hay `goal_team`, vì cả hai lưu theo `agent_key`.
- Xoá agent (A1 nghỉ mã) làm cặp trỏ tới mã đã nghỉ. Mục tiêu đang có đội với mã đó bị chặn `reviewer_retired` (mục 7.3). Agent mới cùng slug hay cùng tag không thay thế mã cũ.

## 5. Vòng làm và review

### 5.1 Trạng thái của đội trên một revision

Trạng thái của mục tiêu vẫn là `run_state`/`block_reason` hiện có. A5 thêm lý do chờ và lý do chặn mới, không thêm máy trạng thái song song.

| Trạng thái quan sát được | Nghĩa | Vào khi | Ra khi |
|---|---|---|---|
| `working` | Agent làm đang có lượt | Lý do làm việc hiện có (A2), hoặc `review_changes` | Lượt xong, bản được tiếp nhận |
| `waiting/review_pending` | Bản đạt kiểm khách quan, chờ review | `_settle` thấy tiêu chí khách quan đạt mà chưa có review hợp lệ cho bộ ghim hiện tại | Lý do `review_due` hay `review_retry` được phục vụ |
| `reviewing` | Reviewer đang có lượt | Hành động `review` bắt đầu | Kết luận được ghi |
| `waiting/review_changes` | Review đòi sửa, chờ lượt làm | Kết luận `needs_changes` còn vòng | Lượt làm mới |
| `waiting/human_confirmation` | Review đạt, còn chờ chủ xác nhận | Có tiêu chí `human_confirmation` | Như A4 hiện tại |
| `waiting/source_drift` | File đích khác bản được tiếp nhận | Mục 5.5 | File khôi phục đúng bytes, hay một bản mới được tiếp nhận hợp lệ qua A4 |
| `succeeded` | Đạt | Khách quan đạt, review hợp lệ `pass`, xác nhận người (nếu có) đạt, không sửa ngoài luồng | Cuối |
| `blocked/review_rounds` | Hết vòng sửa | Kết luận `needs_changes` hợp lệ thứ `max_rounds + 1` (thứ 3) của revision (mục 5.4) | Chủ dự án tách đội, huỷ, hay sửa mục tiêu (revision mới) |
| `blocked/review_unknown` | Review không ra kết luận | `unknown` thử lại hết luật (mục 6.4) | Như trên |
| `blocked/review_input` | Bản không review được bằng model | `too_large` hay `snapshot_mismatch` (lỗi cố định, mục 5.2) | Người xử lý: bản mới nhỏ hơn, sửa mục tiêu, tách đội |
| `blocked/budget_maker`, `blocked/budget_reviewer` | Hết phần lượt của một vai | `begin_action` không giữ được chỗ cho vai đó | Như `review_rounds` |
| `blocked/reviewer_off`, `reviewer_missing` | Người review tạm không dùng được | Cổng vai review (mục 7.3) | Chủ dự án bật lại (hay xác nhận file) cùng mã; review lại bản hiện tại (mục 7.3) |
| `blocked/reviewer_retired` | Mã người review đã nghỉ | Cổng vai review | Chỉ chủ dự án tách đội hay huỷ; mã mới cùng slug không thay |

Sơ đồ chuyển (một revision):

```
lượt làm -> bản tiếp nhận (A4) -> kiểm khách quan
   file đích khác bản tiếp nhận -> waiting/source_drift (mục 5.5), không review, không gọi model
   kiểm khách quan not_met      -> lượt làm (luật A2, phần lượt của vai làm)
   kiểm khách quan unknown      -> chờ hay thử lại như cũ, không review
   kiểm khách quan met          -> có review hợp lệ cho bộ ghim hiện tại?
        có, pass                -> human_confirmation? -> waiting_human : succeeded
        có, needs_changes       -> còn vòng? -> review_changes -> lượt làm : blocked/review_rounds
        có, unknown (cố định)   -> blocked/review_input
        có, unknown (tạm thời)  -> thử lại được? -> review_retry : blocked/review_unknown
        chưa có                 -> review_due -> lượt review -> ghi kết luận -> quay lại kiểm
```

Thứ tự này cố ý: **review chỉ chạy trên bản đã đạt kiểm khách quan và còn nguyên bytes**, nên không tốn lượt review cho bản còn thiếu ý kiểm được bằng code hay bản đang bị sửa tay.

### 5.2 Hợp đồng lượt review

**Đầu vào** (mục 4.3) cùng lời dặn cố định của host:
- Mặc định coi bản là chưa đạt; chỉ kết luận `pass` khi mọi tiêu chí đều đạt rõ ràng.
- Chỉ trả về MỘT đối tượng JSON, không gì khác.

**Đầu ra hợp lệ duy nhất:**

```json
{"verdict": "pass" | "needs_changes",
 "criteria": [{"index": 0, "ok": true, "reason": "..."}],
 "fixes": "..."}
```

**Đọc kết luận (đóng khi lỗi):**
1. Bỏ một lớp rào ```` ```json ```` nếu có; phần còn lại phải là đúng một đối tượng JSON. Không dò regex trong chữ tự do.
2. `verdict` thuộc hai giá trị trên. `criteria` phủ đúng mọi chỉ số tiêu chí đã gửi, mỗi mục có `ok` kiểu bool.
3. Mâu thuẫn thành `unknown/inconsistent`: `pass` mà có mục `ok: false`, hay `needs_changes` mà mọi mục `ok: true` và `fixes` rỗng.
4. Sai bất kỳ điều nào: `unknown/parse_error`. Lỗi engine: `unknown/engine_error`. Lưu bằng chứng hỏng: `unknown/storage_error`. Khởi động lại khi đang chạy: `unknown/interrupted`.
5. Trường lạ bị bỏ qua và ghi vào sự kiện. Không trường nào đổi được tiêu chí, quyền, hạn mức hay vai.

**Hai loại `unknown`:**
- **Tạm thời** (`parse_error`, `inconsistent`, `engine_error`, `storage_error`, `interrupted`): được thử lại theo mục 6.4.
- **Cố định** (`too_large`, `snapshot_mismatch`): phát hiện TRƯỚC khi giữ chỗ, không tốn lượt, không gọi engine, không bao giờ tự thử lại. Mục tiêu sang `blocked/review_input` chờ người xử lý. `HB.FIXED_ERRORS` thêm hai mã này.

**Ghim:** hành động `review` ghi khi bắt đầu đúng bộ ghim (mục 5.5) và `bundle_ref` (mục 5.6). `criteria_hash` là sha256 của JSON chuẩn hoá các tiêu chí của revision; host giữ, không lấy từ model.

**Ghi kết luận** (một giao dịch `BEGIN IMMEDIATE`):
- CAS hàng `reviews` từ `running` sang `done` theo `action_id`.
- Kiểm lại bộ ghim so với hành động. Lệch thì ghi `review_mismatch`, kết luận không được dùng.
- Ghi lần hai cùng `action_id` bị bỏ qua: kết quả gửi lại không nhân đôi, không tiêu thêm lượt.

### 5.3 Góp ý quay lại agent làm

- Kết luận `needs_changes` còn vòng thì thêm lý do `review_changes` (lớp `FIX`, mục 10; phần lượt của vai làm; `source_ref = rc:<review_id>`).
- Lượt làm kế tiếp dùng `_work_prompt` hiện có, thêm khối "Người review góp ý (dữ liệu)": các tiêu chí `ok: false` với lý do, và `fixes` (tối đa 4.000 ký tự). Bản trước đi qua `prev_text` như hiện tại.
- Trong chat, agent làm thấy góp ý trên thẻ (mục 11); lượt chat không tự mở.

### 5.4 Số vòng và kết thúc

- `max_rounds = 2`: bản đầu cộng hai lần sửa theo review. Ghim trong `goal_team` lúc tạo.
- **Đếm vòng.** Khi ghi một kết luận `needs_changes` HỢP LỆ, host đếm `k` = số hàng `reviews` `done`, `verdict='needs_changes'`, `reason_code` rỗng của revision hiện tại, **tính cả hàng vừa ghi**. Bộ đếm bền, không lấy từ nhật ký hiển thị.
  - `k ≤ max_rounds` (k = 1 hay 2): thêm `review_changes rc:<review_id>`. Hai kết luận `needs_changes` đầu cho lượt sửa thứ nhất và thứ hai.
  - `k > max_rounds` (k = 3): `blocked/review_rounds`, không thêm lượt sửa.
  - Kiểm `k ≤ max_rounds` sau khi đã đếm hàng vừa ghi. Không đếm trước rồi so `< 2`, vì như vậy mất lượt sửa thứ hai.
- **Kết luận không hợp lệ không tính vòng:**
  - `review_mismatch`: bộ ghim của kết luận lệch hành động.
  - `stale`: lúc ghi, bộ ghim đã khác trạng thái hiện tại vì revision, mốc đăng hay version reviewer đã đổi.
  - Hai loại này lưu với `reason_code` tương ứng, không tính vào `k`, không sinh `review_changes` cho bản đang dùng.
- Revision mới (chủ dự án sửa mục tiêu trong chat) đếm lại vòng từ 0 nhưng **không** hoàn lượt đã dùng.
- Hết vòng: `blocked/review_rounds`, tin `goal.review_exhausted` (loại phải gửi). Không tự nới vòng, không tự đổi reviewer.

### 5.5 Bộ ghim, review cũ và bản sửa ngoài luồng (R5)

**Bản được tiếp nhận** của revision hiện tại là mốc đăng A4 của file sản phẩm: hàng `published(goal_id, path)` với `sha256` và `action_id`.
- Ảnh chụp của nó là bằng chứng gắn với đúng `action_id` đó, hay với `sub:<id>` của bản nộp A4 mà `publish_action_id` trùng. Bằng chứng phải có `content_hash = sha256`.
- Không có ảnh chụp khớp thì không review được: `unknown/snapshot_mismatch` (cố định).

**Bộ ghim của một review** = (`goal_id`, `revision`, `accepted_ref` = `published.action_id`, `artifact_sha` = `published.sha256`, `criteria_hash`, `reviewer_agent_key`, `reviewer_config_version` lúc bắt đầu review).

**Review hợp lệ để chốt** chỉ khi mọi điều sau đúng ngay lúc chốt:
1. Hàng `reviews` `done`, `verdict = pass`, cùng bộ ghim với trạng thái hiện tại:
   - revision hiện tại;
   - mốc đăng hiện tại (cả `action_id` lẫn sha);
   - hash tiêu chí hiện tại;
   - `reviewer_agent_key` của `goal_team`;
   - `config_version` HIỆN TẠI của reviewer.
2. sha bytes đang ở file đích (cùng hàm `current_artifact_ref` mà `_human_verdict` dùng) bằng `artifact_sha` của bộ ghim.

**Các trường hợp làm review cũ hết giá trị:**
- Bản mới được tiếp nhận qua A4 (lượt việc nền hay bản nộp từ chat): mốc đăng đổi.
- Revision đổi khi đang review: kết luận ghi nhưng mang revision cũ.
- Tiêu chí đổi: hash đổi.
- Reviewer tắt rồi bật, file mất rồi xác nhận lại: `config_version` đổi (mục 7.3).

Review cũ vẫn giữ trong hồ sơ, không xoá.

**Bản sửa ngoài luồng** (người dùng hay chương trình khác sửa file đích, sha `H2` khác bản được tiếp nhận `H1`):
- Với mục tiêu có đội, `_settle` coi mọi trường hợp lệch là `waiting/source_drift`, **kể cả khi `H2` đạt kiểm khách quan**. Đây là điểm khác A2 (A2 chốt đạt khi bản sửa tay đạt). Lý do: review chỉ bảo đảm cho `H1`.
- Không gọi model: không làm lại, không review, không đăng đè. Bảo vệ file như A2/A4: mốc quan sát ghi riêng (`observe_source`), không đổi mốc đăng, không thành baseline.
- `H2` **không** tự thành bản được tiếp nhận. A5 không thêm đường tiếp nhận file bất kỳ.
- **Khôi phục đúng `H1`:** lệch hết. Review `pass` cũ của `H1` lại hợp lệ nếu bộ ghim còn khớp, mục tiêu chốt được mà không gọi model. Không còn khớp (ví dụ reviewer đã đổi version) thì `review_due` cho bộ mới, đọc ảnh chụp `H1`.
- **`H2` đi qua đường tiếp nhận hợp lệ của A4:** maker nộp bằng `javis_submit_deliverable`, hay một lượt việc nền làm lại. `host_publish` và `adopt_submission` ghi mốc đăng mới với bằng chứng của bytes đó, nên có bộ ghim mới và `review_due` mới.
- **Sửa tay trong lúc review đang chạy:** kết luận ghi cho `H1`. Lúc chốt thấy lệch thì chờ như trên. Kết luận chỉ dùng được nếu file quay về `H1`.
- **Người dùng muốn giữ `H2` mà không qua review:** tách đội (`team_detach`). Mục tiêu theo luật A4/A2 như cũ. Đây là lựa chọn của chủ dự án, hiện trên thẻ.

### 5.6 Định danh lịch review (R2)

Kho chống trùng lý do vĩnh viễn theo (`goal_id`, `code`, `source_ref`), kể cả lý do đã phục vụ (`resonance_store.py` :153, :968-981; probe xác nhận). Vì vậy mỗi mã review mang một `source_ref` đủ để phân biệt mọi lần đáng chạy, và đủ hẹp để một sự kiện gửi lặp không mở lượt thứ hai.

| Mã | Lớp | `source_ref` | Thêm khi | Sự kiện gửi lặp | Lần hợp lệ kế tiếp |
|---|---|---|---|---|---|
| `review_due` | `START` | `rb:<revision>:<accepted_ref>:<artifact_sha>:<criteria_hash>:<reviewer_key>:<reviewer_version>` (đủ bộ ghim) | `_settle` thấy khách quan đạt, không lệch, chưa có hàng `reviews` nào của `bundle_ref` này | Cùng ref, `add_reason_event` trả False, không thêm lượt | Revision mới cùng bytes và tiêu chí: ref khác (có revision), nên chạy. Reviewer bật lại (version mới): ref khác, nên chạy |
| `review_retry` | `AUTO` | `rr:<review_id>` (id hàng review vừa ra `unknown` tạm thời) | Ghi kết luận `unknown` tạm thời, hay `_reconcile` chốt hàng `running` là `interrupted` | Cùng hàng review chỉ sinh một ref | Lần thử sau lỗi kế tiếp có review id mới, nên ref mới. Bị giới hạn bởi mục 6.4 |
| `review_changes` | `FIX` | `rc:<review_id>` (hàng `needs_changes`) | Ghi kết luận `needs_changes` còn vòng | Cùng ref, không thêm | Mỗi kết luận `needs_changes` là một lượt sửa |

**Thời điểm được xét và lịch vật lý:**
- `review_due` và `review_changes` là lý do sự kiện, đến hạn ngay (`due_at = now`).
- `review_retry` hẹn theo `ERROR_BACKOFF_S[n-1]` như `error_retry`, với `n` là **số lần tính** của bộ ghim (định nghĩa ngay dưới).
- Ba mã có nghĩa vụ (slot) riêng `review`, không thay hẹn `retry` hay `check` của vai làm.

**Phục hồi sau khởi động lại:**
- Lý do và hàng `reviews` đều bền.
- Hành động `review` chỉ hẹn `action_recovery` lúc hết khoá: lịch **chỉ đối soát bằng code**, không bao giờ mở lượt model. Mã nền đã làm vậy cho mọi hành động không phải `work` (`resonance_store.py` :1524-1527). Không dùng `recovery` (lớp AUTO của vai làm), nên khởi động lại không gọi nhầm maker hay gọi review sớm.
- Khi `action_recovery` thức, `_reconcile` gặp hành động `review` còn `running` (khoá đã hết, không xác định được engine đã chạy hay chưa):
  - hàng `reviews` thành `failed/interrupted`, `charged` giữ 1 (vẫn tính lượt và tính lần);
  - **sau đó** mới thêm `review_retry rr:<id>`, hẹn theo backoff (idempotent theo ref), và chỉ khi luật 6.4 còn cho.
- Hai tiến trình đánh thức cùng lúc: CAS `claim_wake` và lease mục tiêu chỉ cho một hành động.

**Phân lớp:** `CLASSES` vẫn ánh xạ một mã một lớp. Lần đầu và lần thử lại dùng hai mã riêng, không suy lớp từ dữ liệu.

**Số thứ tự và số lần tính của một bộ ghim (vòng 3):** hai khái niệm tách riêng.
- **`reviews.seq`**: số thứ tự hàng, tăng dần, duy nhất theo (`bundle_ref`, `seq`). Mỗi `begin_action(review)` chèn một hàng mới. Dùng cho audit và idempotency; không bao giờ tái dùng hay xoá.
- **`reviews.charged`**: 1 khi hàng chèn (lượt đã giữ), về 0 **chỉ** khi host xác nhận engine chưa chạy, trong giao dịch hoàn (mục 6.2).
- **Số lần tính** `n` của bộ ghim = số hàng `charged = 1` của `bundle_ref` đó. Đây là bộ đếm duy nhất cho trần thử (`n ≤ 3`) và chỉ số backoff.
  - Hàng `cancelled/not_run` đã được host xác nhận thì bỏ ra.
  - Hàng có thể đã gọi engine (`done`, lỗi sau engine, `failed/interrupted`, huỷ khi engine có thể đã chạy) thì không bao giờ bỏ.
- Hoàn ngân sách, hạ `charged`, trả lý do về `pending` và đóng hành động nằm trong CÙNG một giao dịch, khoá bằng CAS trên hành động (`running` sang `cancelled`). Vì vậy hoàn lặp hay mở lại kho không trừ hai lần và không cấp thêm lần thử.

## 6. Hạn mức chia phần (R4)

### 6.1 Một sổ, hai phần

- **Một sổ:** `goals.budget_calls` và `calls_used` như hiện tại, cùng trần `JAVIS_RESONANCE_CALL_CEILING`.
- **Chia phần:** bảng `team_calls(goal_id, role, cap, used)`.
  - Mục tiêu có đội: `budget_calls = 8`, maker 4, reviewer 4. Tổng phần vai bằng `budget_calls`, nên không vai nào chạy được bằng lượt "dư" của vai kia.
  - Mục tiêu không có đội giữ `GOAL_DEFAULT_CALLS = 6`.
- **Vai ghi trong ý định hành động:** `begin_action` nhận và lưu `role` vào `intent_json` (`work` thì `maker`, `review` thì `reviewer`). Mọi đường hoàn dùng đúng vai đã lưu, không đoán theo trạng thái lúc hoàn.
- Không tự nâng trần, không tạo agent thay thế, không mượn phần của vai kia.

### 6.2 Bảng mọi đường giữ, hoàn và tiếp quản lượt

Áp cho mục tiêu có `goal_team` `active`. "Cùng giao dịch" nghĩa là trong giao dịch `BEGIN IMMEDIATE` đang có của đường đó.

| Đường | `goals.calls_used` | `team_calls` | Ghi chú |
|---|---|---|---|
| Bộ lập mục tiêu (`reserve_ledger_call` "framer") | Sổ riêng, không thuộc mục tiêu nào | Không | Chạy trước khi mục tiêu tồn tại, như hiện tại; không thuộc 8 lượt |
| `begin_action(kind='work')` không dùng lượt giữ: bản đầu, `retry_not_met`, `error_retry`, `recovery`, `feedback` (A3, lớp `NEW`), `review_changes` | +1 | maker +1, cùng giao dịch, điều kiện `used < cap` | Hỏng bất kỳ điều kiện nào (trần, `calls_used < budget_calls`, phần vai) thì không giữ gì, trả `budget_maker` |
| `begin_action(kind='review')` | +1 | reviewer +1, cùng giao dịch | Như trên, trả `budget_reviewer` |
| `begin_action(kind='work')` dùng lượt giữ A3 (`use_hold`, `require_hold`) | 0 (tiếp quản) | 0 | Không xảy ra với mục tiêu có đội: làn M tắt nên không có lượt giữ (6.3). Kho kiểm lại: có đội mà có `use_hold` thì `ConflictError` |
| `begin_experiment` (phép thử M5, lượt giữ `method_followup`) | Không đổi | Không | **Kho từ chối** khi có đội `active`: trả None, bài học `trial_pending` sang `skipped/team_goal` |
| `begin_action(kind='trial')` | 0 (phép thử đã giữ trước) | Không | Không xảy ra: không có phép thử |
| `abort_action` (huỷ sau ý định, trước engine) và `release_call(action_id)` (engine không dựng được hay bị chặn trước khi gọi, `_ReservedCall.release`) | −1 | vai trong ý định −1 | **Một hàm hoàn duy nhất** `_refund_not_run(c, action_id)` cho mục tiêu có đội, một giao dịch. CAS hành động `running` sang `cancelled/not_run`; không khớp thì không làm gì. Nếu khớp: trừ `calls_used` và vai; hàng `reviews` (nếu có) `running` sang `cancelled`, `charged = 0`; lý do đã phục vụ về `pending`; bỏ hẹn `action_recovery` của nó. Không bao giờ để hàng `running` sau khi đã hoàn. Mục tiêu không có đội giữ đường hiện tại |
| `release_trial_call`, `finish_experiment(refund)`, `_release_hold` | Không xảy ra | Không | Chỉ có trên phép thử và lượt giữ, mà mục tiêu có đội không có |
| Huỷ mục tiêu khi engine có thể đã chạy | Không hoàn | Không hoàn | Kết quả muộn không dùng |
| `_reconcile` gặp hành động `running` đã hết khoá | Không hoàn | Không hoàn | `work`: lượt lỗi `interrupted` như A2. `review`: `failed/interrupted`, `charged` giữ 1, rồi mới thêm `review_retry` (mục 5.6) |
| `team_detach` | Không đổi | Giữ nguyên làm hồ sơ, không xoá | Sau tách đội: mục tiêu chạy như A4 trong phần còn lại của `budget_calls` (8 − đã dùng); làn M chạy lại được theo luật A3 |
| Lượt chat của agent làm (A1, A4) | Không tính (như hiện tại) | Không | Review bản nộp từ chat tính vào phần reviewer |
| Reaction A3 trên thẻ | Không gọi model | Không | |

**Không tính hai lần:**
- Đường tiếp quản lượt giữ không có trên mục tiêu có đội.
- Mọi hoàn đi qua `_refund_not_run`, là CAS trên đúng hành động (`running` sang `cancelled`), nên hoàn lặp, hoàn sau khi mở lại kho, hay `abort_action` sau `release_call` cùng hành động không trừ hai lần.

### 6.3 Làn M của A3 khi có đội

**Chọn: tạm không tự thử cách làm mới trên mục tiêu có đội**, kiểm ở kho (`begin_experiment`), không chỉ ở bước quyết định.
- Lý do: phép thử giữ trước nhiều lượt cùng lúc và một lượt sản phẩm. Gộp vào phần maker 4 thì gần như luôn ăn hết lượt sửa theo review. Tách thêm phần thì phải nâng hạn mức, điều review cấm tự làm.
- Hiển thị: bài học làn M của mục tiêu có đội chuyển `skipped/team_goal`. Thẻ ghi "Đang làm theo đội làm và review: tạm không thử cách làm mới".
- Làn F (bài học ở phản hồi) không gọi model ngoài lượt làm thường, nên không đổi.
- Sau `team_detach`, làn M chạy lại theo luật A3.

### 6.4 Lượt dự phòng và thử lại

Luật A2 (`auto_allowed`): lượt `AUTO` chỉ chạy khi còn hơn `AUTO_RESERVE_CALLS = 1` lượt. Với mục tiêu có đội, "còn lại" là `min(budget_calls − calls_used, cap − used của vai đó)`.

| Lớp | Ví dụ | Dùng được lượt cuối của vai? | Giới hạn riêng |
|---|---|---|---|
| `START` | Bản đầu (`created`), `review_due` | Có | Một lần cho mỗi bộ ghim |
| `NEW` | Tin mới hay góp ý của người dùng (`feedback`) | Có | Như A2 |
| `FIX` (mới) | `review_changes` | **Có** | `max_rounds = 2` mỗi revision |
| `AUTO` | `retry_not_met`, `error_retry`, `recovery` (maker); `review_retry` (reviewer) | **Không**: phải còn ≥ 2 lượt của vai | maker: `ERROR_MAX_FAILS = 3` lỗi mỗi chuỗi, `STALL_AFTER = 2`. reviewer: tối đa 3 lần **tính** mỗi bộ ghim (số hàng `charged = 1`, mục 5.6); lượt huỷ trước engine không tính |

**Vì sao `review_changes` là lớp `FIX`, không phải `AUTO`:**
- Probe xác nhận: để `AUTO` thì vai còn đúng một lượt không chạy được lượt sửa, làm "hai lần sửa" thành lời hứa sai.
- Lượt sửa giống tin mới của người dùng: do một kết luận bên ngoài vai làm sinh ra, và đã có trần riêng (số vòng).
- Lượt dự phòng vẫn được giữ cho các lần thử lại tự động.

**Lời hứa đúng của 4 + 4** (thay câu D6 vòng 1):
- **Vai làm:** bản đầu và hai lần sửa theo review, cộng một lượt dự phòng.
  - Lượt dự phòng dùng cho một lần thử lại tự động khi còn ≥ 2 lượt, hay cho tin mới của người dùng.
  - Mỗi lỗi hay `not_met` phải thử lại trước khi có bản đạt sẽ ăn một lượt. Lượt dự phòng hết thì lỗi tiếp theo làm mất một vòng sửa.
- **Vai review:** review bản đầu và hai bản sửa, cộng một lượt dự phòng.
  - Lượt dự phòng dùng cho một lần thử lại `unknown` khi còn ≥ 2 lượt, hay cho review bản sau tin mới của người dùng.
  - Không có lần thử lại nào được dùng lượt cuối của vai.
- `ERROR_MAX_FAILS = 3` vẫn là trần lỗi của chuỗi vai làm. Với 4 lượt, chuỗi chạm trần lượt hay trần lỗi tuỳ cái nào đến trước. Thiết kế không hứa "đủ hai vòng sửa VÀ thử lại ba lần".

### 6.5 Bảng vết ngân sách

Cột: lượt thứ mấy của mục tiêu, vai, lý do (lớp), kết quả, (maker đã dùng/4, reviewer đã dùng/4, tổng/8), quyết định kế tiếp.

**V1. Thành công, hai vòng sửa, không lỗi**

| # | Vai | Lý do (lớp) | Kết quả | (m, r, tổng) | Kế tiếp |
|---|---|---|---|---|---|
| 1 | maker | `created` (START) | bản H1, khách quan đạt | (1, 0, 1) | `review_due rb:H1` |
| 2 | reviewer | `review_due` (START) | `needs_changes` (vòng 1/2) | (1, 1, 2) | `review_changes rc:1` |
| 3 | maker | `review_changes` (FIX) | H2, đạt | (2, 1, 3) | `review_due rb:H2` |
| 4 | reviewer | `review_due` (START) | `needs_changes` (vòng 2/2) | (2, 2, 4) | `review_changes rc:2` |
| 5 | maker | `review_changes` (FIX) | H3, đạt | (3, 2, 5) | `review_due rb:H3` |
| 6 | reviewer | `review_due` (START) | `pass` | (3, 3, 6) | `succeeded` |

Còn 1 + 1 dự phòng không dùng.

**V2. Một lỗi của vai làm trước bản đầu**

| # | Vai | Lý do | Kết quả | (m, r, tổng) | Kế tiếp |
|---|---|---|---|---|---|
| 1 | maker | `created` (START) | `engine_error` | (1, 0, 1) | `error_retry`: còn 3 ≥ 2, được |
| 2 | maker | `error_retry` (AUTO) | H1, đạt | (2, 0, 2) | review |
| 3 | reviewer | `review_due` | `needs_changes` 1/2 | (2, 1, 3) | |
| 4 | maker | `review_changes` (FIX) | H2, đạt | (3, 1, 4) | |
| 5 | reviewer | `review_due` | `needs_changes` 2/2 | (3, 2, 5) | |
| 6 | maker | `review_changes` (FIX), còn đúng 1 | H3, đạt | (4, 2, 6) | `FIX` dùng được lượt cuối |
| 7 | reviewer | `review_due` | `pass` | (4, 3, 7) | `succeeded` |

Đủ hai vòng sửa; dự phòng của maker đã bị lỗi dùng. Tin mới của người dùng sau đó: `blocked/budget_maker`.

**V3. Hai lỗi của vai làm**

| # | Vai | Lý do | Kết quả | (m, r, tổng) | Kế tiếp |
|---|---|---|---|---|---|
| 1 | maker | `created` | lỗi | (1, 0, 1) | `error_retry`: còn 3, được |
| 2 | maker | `error_retry` | lỗi | (2, 0, 2) | `error_retry`: còn 2 ≥ 2, fails 2 < 3, được |
| 3 | maker | `error_retry` | H1, đạt | (3, 0, 3) | |
| 4 | reviewer | `review_due` | `needs_changes` 1/2 | (3, 1, 4) | |
| 5 | maker | `review_changes` (FIX) | H2, đạt | (4, 1, 5) | |
| 6 | reviewer | `review_due` | `needs_changes` 2/2 | (4, 2, 6) | Không còn lượt maker |
| - | | | | | `blocked/budget_maker`, tin `goal.review_blocked` |

Hai lỗi làm mất một vòng sửa. Đây là hành vi đã nêu ở 6.4.

**V4. Review `unknown` rồi thử lại**

| # | Vai | Lý do | Kết quả | (m, r, tổng) | Kế tiếp |
|---|---|---|---|---|---|
| 1 | maker | `created` | H1, đạt | (1, 0, 1) | |
| 2 | reviewer | `review_due` (seq 1, lần tính 1) | `unknown/parse_error` | (1, 1, 2) | `review_retry rr:1`: còn 3 ≥ 2, n = 1 < 3, được |
| 3 | reviewer | `review_retry` (AUTO, seq 2, lần tính 2) | `pass` | (1, 2, 3) | `succeeded` |

**V5. Reviewer còn đúng một lượt khi gặp `unknown`**

| # | Vai | Lý do | Kết quả | (m, r, tổng) | Kế tiếp |
|---|---|---|---|---|---|
| 1 đến 5 | | như V1 tới hết lượt 5 | | (3, 2, 5) | |
| 6 | reviewer | `review_due` H3 | `unknown/engine_error` | (3, 3, 6) | `review_retry`: reviewer còn 1, AUTO cần ≥ 2, KHÔNG được |
| - | | | | | `blocked/review_unknown`. Lượt cuối của reviewer giữ cho review bản sau tin mới của người dùng |

**V6. Bản quá lớn**

- `review_due` của H1: kiểm `too_large` trước khi giữ chỗ.
- (m, r) không đổi; `blocked/review_input`; không gọi engine; không tự thử lại.

**V7. Huỷ, tiếp quản, tách đội, khởi động lại**
- Huỷ trước engine review: `_refund_not_run` hoàn (tổng −1, reviewer −1). Hàng review `cancelled/not_run`, `charged = 0`. `review_due` trở lại `pending`.
- Huỷ khi engine có thể đã chạy: không hoàn.
- Khởi động lại khi review đang chạy: không hoàn, `failed/interrupted`, `review_retry` theo luật AUTO.
- Tách đội ở trạng thái (3, 2, 5): `team_calls` giữ (3, 2). Mục tiêu còn 3 lượt theo luật A4/A3.

**V8. Huỷ trước engine không ăn trần thử (vòng 3)**

| Hành động | Kết quả | seq | charged | n (lần tính) | (m, r, tổng) | Kế tiếp |
|---|---|---|---|---|---|---|
| maker `created` | H1, đạt | | | | (1, 0, 1) | `review_due` |
| review 1 | Huỷ trước engine (`_refund_not_run`) | 1 | 0 | 0 | (1, 0, 1) | `review_due` về `pending` |
| review 2 | Engine không dựng được (`release_call(action_id)`) | 2 | 0 | 0 | (1, 0, 1) | `review_due` về `pending` |
| review 3 | Engine chạy, `unknown/engine_error` | 3 | 1 | 1 | (1, 1, 2) | `review_retry rr:3` hẹn `ERROR_BACKOFF_S[0]`: reviewer còn 3 ≥ 2, n = 1 < 3, được |
| review 4 (sau backoff) | `pass` | 4 | 1 | 2 | (1, 2, 3) | `succeeded` |

Trước lần thử lại, `team_calls.reviewer.used = 1`: chỉ lần gọi engine thật được tính.

## 7. Quyền, engine và giới hạn phải nói thật

### 7.1 Cái gì được thực thi ở đâu

| Giới hạn | Thực thi bởi | Mức chắc chắn |
|---|---|---|
| Reviewer không gọi công cụ, không đọc ghi file, không chạy lệnh | Engine việc nền dựng chỉ chữ, chặn công cụ, thư mục làm việc rỗng; `pick_text_only_link` trả None nếu không chặn được | Thực thi bằng cấu hình engine, như mọi lượt việc nền hiện nay |
| Lời reviewer không thành sản phẩm | Hành động `review` không có đường nộp: host chỉ đọc kết luận, không gọi `submission_from_output` | Thực thi bằng mã host |
| Reviewer không đổi tiêu chí, quyền, hạn mức, vai | Đầu ra chỉ có ba trường; host bỏ qua mọi trường khác | Thực thi bằng mã host |
| Agent làm chỉ ghi vào phạm vi được cho phép | Grant và binding A4 | Như A4: trong hợp đồng host. Lượt chat của engine CLI có công cụ gốc (Bash, Write); hub không chặn được công cụ gốc (thiết kế A4 mục 6.3) |
| Review gắn đúng bản | Ghim, CAS trong kho, kiểm hash ảnh chụp trước khi gửi | Thực thi bằng mã host |
| Không đường lượt nào ngoài sổ vai | `begin_action` (vai) và `begin_experiment` (từ chối khi có đội) | Thực thi bằng mã kho |

### 7.2 Không hứa quá

- Hai vai cùng một model việc nền; độc lập ở vai và dữ liệu, không ở bộ não.
- Review là ý kiến của model, có thể sai. Nó không thay kiểm khách quan, guard hay xác nhận của người.
- **Review không phải cổng chặn nội dung xấu xuất hiện ở file đích:** bản đã đăng theo A4 trước khi review (D1). Thẻ ghi "chưa nghiệm thu" tới khi review đạt.
- **Lease mục tiêu chỉ ngăn hai lượt VIỆC NỀN chạy cùng lúc.** Nó không khoá lượt chat của agent làm. Trong lúc review nền chạy, maker vẫn có thể nộp bản mới hay sửa mục tiêu trong chat. An toàn đến từ việc kiểm lại bộ ghim lúc ghi kết luận và lúc chốt (mục 5.5), không từ lease.
- A5 không làm engine nào có sandbox rộng hơn hiện nay. Engine khác Claude Code chỉ được kiểm bằng engine giả cho tới khi có pilot riêng.

### 7.3 Cổng vai review và đường phục hồi (R3)

**Danh tính bền:**
- `goal_team` ghim `reviewer_agent_key`, không ghim version.
- `agent_key` giữ nguyên qua tắt, bật, `missing`, xác nhận lại cùng file (`confirmed_same`, :555).
- Mã chỉ thay khi agent nghỉ (xoá qua host, hay xác nhận là agent khác `replaced`, :538, :556). Khi đó là mã mới, không bao giờ được coi là reviewer cũ.

**Cổng mỗi lần thức có hành động:** `agent_gate(reviewer_agent_key)` không truyền version.
- `agent_off`: `blocked/reviewer_off`.
- `agent_missing`: `blocked/reviewer_missing`.
- `agent_retired`, `agent_unknown`: `blocked/reviewer_retired`.
- Hẹn `agent_recheck` như agent làm. Không lặng lẽ bỏ review.

**Version chỉ nằm ở từng lần review:**
- Hành động `review` ghim `reviewer_config_version` lúc bắt đầu; kho kiểm lại trong `begin_action`.
- Kết quả chỉ hợp lệ khi version đó bằng version hiện tại lúc chốt (mục 5.5).

**Đường phục hồi khi tắt rồi bật lại cùng mã** (v1 bật, v2 tắt, v3 bật):
1. Chủ dự án bật lại Cộng hưởng cho reviewer, ở trang agent hay bằng nút trên thẻ (mục 11). `agent_set_enabled` tăng lên v3.
2. `wake_agent_goals` (mở rộng): hẹn thức các mục tiêu có `goal_team.reviewer_agent_key` là mã này, cùng các mục tiêu mà mã này làm maker.
3. Cổng qua. Review `pass` cũ mang v1 không còn hợp lệ (version khác), nên `_settle` thêm `review_due` với `bundle_ref` mang v3. Ref mới nên không bị chống trùng chặn.
4. Review lại tính một lượt reviewer.
   - Không reset `team_calls`, số vòng hay chuỗi lỗi.
   - Không dùng kết luận cũ.
   - Lượt review đang chạy lúc tắt: kết quả ghi với v1, không dùng.
5. Hết lượt reviewer: `blocked/budget_reviewer`. Chủ dự án tách đội, huỷ hay sửa mục tiêu.

**File agent mất rồi xác nhận lại:**
- `confirmed_same` giữ mã, tăng version: đi đúng đường trên.
- `replaced`: mã cũ nghỉ, `blocked/reviewer_retired`; agent mới cùng slug không thay.

**Khởi động lại khi reviewer đang tắt:** lý do và chặn đều bền; lần thức sau khởi động lại vẫn chặn đúng lý do.

## 8. Dừng, tắt, huỷ, thu hồi

| Thao tác của chủ dự án | Vai làm | Vai review | Lượt đang chạy |
|---|---|---|---|
| Tạm dừng mục tiêu | Không đánh thức `work` | Không đánh thức `review` (cùng điều kiện `paused`) | Chạy hết; kết quả ghi; không chốt đạt khi đang dừng (như hiện tại) |
| Huỷ mục tiêu | Dừng hẳn | Dừng hẳn | Trước engine: `abort_action`, hoàn đúng vai. Có thể đã chạy: không hoàn, kết quả không dùng |
| Thu hồi quyền ghi (A4) | Như A4: bản chưa commit thành `stale`, binding `dead`, mục tiêu tạm dừng | Không có quyền để thu hồi; dừng theo mục tiêu | Như A4 |
| Cấp lại quyền | Lượt cũ không hưởng quyền mới (A4 `authority_clock`) | Review cũ còn giá trị nếu bộ ghim vẫn khớp; bản mới cần review mới | |
| Tắt agent làm | `blocked/agent_off` như A1 | Không chạy (mục tiêu bị chặn) | Như A1 |
| Tắt agent review | Không được chốt đạt | `blocked/reviewer_off` | Kết luận của lượt đang chạy ghi nhưng không dùng (version đổi) |
| Bật lại agent review | | Mục 7.3: review lại bản hiện tại, tính một lượt | |
| `team_detach` | Tiếp tục theo luật A4 | Không còn vai | Lượt review đang chạy: kết quả ghi, không dùng |
| Guard chặn | Như hiện tại | Không review khi bị chặn | Review không xoá guard |

## 9. Kho

### 9.1 Bảng mới

Chỉ thêm bảng, không thêm cột vào bảng trước A1.

```sql
CREATE TABLE IF NOT EXISTS team_pairs (
  maker_agent_key TEXT PRIMARY KEY, brain_id TEXT NOT NULL,
  reviewer_agent_key TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  config_version INTEGER NOT NULL DEFAULT 1, updated_at REAL NOT NULL, by TEXT NOT NULL,
  CHECK (maker_agent_key <> reviewer_agent_key));

CREATE TABLE IF NOT EXISTS goal_team (
  goal_id TEXT PRIMARY KEY, maker_agent_key TEXT NOT NULL,
  reviewer_agent_key TEXT NOT NULL,              -- danh tính bền; KHÔNG ghim version (mục 7.3)
  reviewer_version_at_attach INTEGER NOT NULL,   -- chỉ để hiển thị và hồ sơ, không dùng ở cổng
  pair_config_version INTEGER NOT NULL, max_rounds INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','detached')),
  created_at REAL NOT NULL, detached_at REAL, detached_by TEXT);

CREATE TABLE IF NOT EXISTS team_calls (
  goal_id TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('maker','reviewer')),
  cap INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (goal_id, role),
  CHECK (used >= 0 AND used <= cap));

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  bundle_ref TEXT NOT NULL,                      -- rb:<revision>:<accepted_ref>:<sha>:<criteria>:<key>:<version>
  accepted_ref TEXT NOT NULL, artifact_sha TEXT NOT NULL, snapshot_evidence_id TEXT NOT NULL,
  criteria_hash TEXT NOT NULL,
  reviewer_agent_key TEXT NOT NULL, reviewer_config_version INTEGER NOT NULL,
  action_id TEXT NOT NULL UNIQUE,
  seq INTEGER NOT NULL,                          -- số thứ tự hàng, audit; không tái dùng
  charged INTEGER NOT NULL DEFAULT 1 CHECK (charged IN (0,1)),  -- 0 chỉ khi host xác nhận chưa chạy engine
  status TEXT NOT NULL CHECK (status IN ('running','done','failed','cancelled')),
  verdict TEXT CHECK (verdict IN ('pass','needs_changes','unknown')),
  reason_code TEXT, criteria_json TEXT, fixes TEXT, evidence_id TEXT,
  created_at REAL NOT NULL, finished_at REAL,
  UNIQUE (bundle_ref, seq));
CREATE INDEX IF NOT EXISTS reviews_bundle_charged ON reviews(bundle_ref, charged);
CREATE INDEX IF NOT EXISTS reviews_goal_rev ON reviews(goal_id, revision, status);
```

Hành động review dùng bảng `actions` hiện có với `kind = 'review'`: một giá trị mới của cột có sẵn, không đổi lược đồ. `intent_json` mang `role`, bộ ghim và `bundle_ref`.

### 9.2 Giao dịch và phục hồi

- **Gắn đội:** trong giao dịch `create` (mục 4.2), hàm `_attach_team`. Không gắn trong `assign_goal`.
- **Bắt đầu review:** `begin_action(kind='review')` làm trong một giao dịch:
  - lease mục tiêu;
  - cổng agent làm (như hiện tại) và cổng reviewer (mã, trạng thái, bật; version bằng version ghim trong ý định);
  - trần, `calls_used`, `team_calls` vai reviewer;
  - chèn `reviews(status='running', seq = seq lớn nhất của bộ ghim + 1, charged = 1)`;
  - phục vụ lý do;
  - hẹn `action_recovery` (chỉ đối soát, mục 5.6), không phải `recovery`.

  Kiểm `too_large` và `snapshot_mismatch` chạy TRƯỚC giao dịch này, không giữ chỗ.
- **Xong review:** lưu bằng chứng (đầu ra thô) trước. Rồi một giao dịch ghi kết luận (mục 5.2), đóng hành động, thêm lý do kế tiếp.
- **Huỷ trước engine, hay engine không dựng được:** `_refund_not_run` (mục 6.2), dùng chung cho `abort_action` và `release_call(action_id)`.
- **Khởi động lại:** `_reconcile` theo mục 5.6.
- **Lỗi lưu bằng chứng:** `unknown/storage_error`, lượt tính.

## 10. Lịch (A2) và phản hồi (A3)

- **Mã lý do mới:**
  - `review_due` (`START`), `review_retry` (`AUTO`), `review_changes` (`FIX`).
  - `CLASSES` thêm ba mã. `HB.decide` thêm lớp `FIX`: mở một lượt `work`, không bị lượt dự phòng chặn, bị chặn bởi `max_rounds` (kiểm khi thêm lý do).
  - `HB.FIXED_ERRORS` thêm `too_large`, `snapshot_mismatch`.
  - Không có lớp nào hỏi model định kỳ. Đổi chính sách thì tăng `POLICY_VERSION` lên `heartbeat.v3`.
- **Định danh và lịch vật lý:** mục 5.6.
- **Đồng thời:** CAS `claim_wake` và lease mục tiêu đảm bảo một hành động việc nền một lúc. Vai làm và vai review không chạy song song trên cùng mục tiêu (lease không chặn chat, mục 7.2).
- **Phản hồi A3:** reaction trên thẻ review chỉ đổi cách trình bày tin (như mọi reaction), không đổi kết luận review, không đổi lịch. Làn M tắt khi có đội (mục 6.3).

## 11. Giao diện tối thiểu

- **Trang agent:** ô chọn **Người review** (mục 4.2), chỉ hiện khi agent đã bật Cộng hưởng. Tag của từng agent có thể hiện bên tên chỉ như nhãn (mục 4.5).
- **Thẻ mục tiêu:** dùng khung thẻ A1 đến A4, thêm một dòng đội khi có `goal_team`:
  - "Làm: <tên agent> · Review: <tên agent>";
  - "Bản đã review: <8 ký tự sha> · Đạt / Cần sửa (vòng 1/2) / Chưa rõ";
  - lý do chờ bằng câu người đọc: "Đang chờ <reviewer> xem bản <sha>", "Đang chờ <maker> sửa theo góp ý", "File đích bị sửa ngoài Javis: chờ bản được tiếp nhận";
  - "Lượt còn: làm 3/4 · review 2/4".
- **Nút của chủ dự án trên thẻ** (chỉ hiện khi có lý do):
  - `blocked/reviewer_off`: **Bật lại người review**. Gọi đúng API bật Cộng hưởng hiện có cho mã reviewer. Thẻ nói trước "bản hiện tại sẽ được review lại, tính một lượt review".
  - `blocked/reviewer_missing`: dẫn tới trang agent để xác nhận file.
  - Mọi `blocked/review_*`, `blocked/budget_*`, `blocked/reviewer_*`, `waiting/source_drift`: **Bỏ yêu cầu review** (`team_detach`), có hộp xác nhận nói rõ từ đây chốt theo luật thường.
- **Góp ý review** hiện trong phần mở rộng của thẻ (lý do theo tiêu chí và `fixes`), không thành tin chat riêng.
- **Tin phải gửi mới:**
  - `goal.review_exhausted`;
  - `goal.review_blocked`: gộp các lý do `blocked/review_*`, `blocked/budget_*`, `blocked/reviewer_*`.

  Không thêm trang đội riêng.
- Mục tiêu cũ gán qua `assign_goal`: dòng "Mục tiêu có từ trước, không có người review".
- **Chữ mới đi qua i18n** (`vi.json`, `en.json`) theo quy ước repo; từ điển chỉ dashboard (ví dụ `de.json`) rơi về tiếng Anh như mọi khoá chưa dịch.

## 12. API, công cụ, file dự kiến

| Thay đổi | File |
|---|---|
| Bảng `_A5_SCHEMA`, nâng kho, snapshot `.pre-0.109.0` | `server/resonance_store.py` |
| `team_pair_set`/`team_pair_get`, `_attach_team` trong `create`, `team_calls` trong `begin_action`/`release_call` (theo `action_id`)/`abort_action`, từ chối `begin_experiment` khi có đội, `record_review`, `team_detach`, `wake_agent_goals` cho reviewer | `server/resonance_store.py` |
| `_review_prompt`, `parse_review` (hàm thuần), dựng và kiểm ảnh chụp, cổng 7.3, nhánh team trong `_settle` (gồm 5.5), `_review_step`, `_reconcile` cho `review`, `_ReservedCall` theo `action_id` | `server/resonance.py` |
| Mã lý do, lớp `FIX`, lỗi cố định mới, `heartbeat.v3` | `server/resonance_heartbeat.py` |
| `GET/PUT /resonance/agents/{slug}/reviewer`, `POST .../team-detach`, trường `team` trong goal view | `server/resonance_api.py` |
| Ô Người review; dòng đội và nút trên thẻ; khoá i18n | `dashboard/` (trang agent, `chat-resonance.js`), `dashboard/i18n/vi.json`, `en.json` |
| Khôi phục về 0.108.0 | `tools/resonance_restore_pre_a5.py` |
| Test | `tests/python/test_resonance_a5_team.py`, `test_resonance_a5_budget.py`, `test_resonance_a5_rollback.py`, `tests/js/test_resonance_a5_ui.js` |

Không thêm công cụ cho model: reviewer không gọi công cụ; agent làm dùng `javis_submit_deliverable` như A4.

## 13. Nâng và hạ phiên bản

- **Lúc nâng:** lần đầu mã A5 mở kho có từ trước, `_backup_before("team_pairs", ".pre-0.109.0")` chép kho bằng SQLite backup API một lần, rồi tạo bảng A5. Cùng mẫu với A1 đến A4: có bảng mốc thì không chép lại. Mục tiêu cũ không có `goal_team`, chạy như A4.
- **Hạ đúng cách:** tắt Javis, chạy `tools/resonance_restore_pre_a5.py`, rồi chạy 0.108.0. Script giữ bản kho hiện tại `post-0.109.0-<thời điểm>` rồi mới ghi snapshot.
- **Hạ không khôi phục: không hỗ trợ.** Ghi rõ trong CHANGELOG. Lý do:
  - Mã 0.108.0 bỏ qua bảng A5, nên mục tiêu có đội có thể được chốt đạt mà không có review.
  - Hành động `kind='review'` còn `running` bị `_reconcile` cũ coi là lượt việc thường bị ngắt.
- **Nâng lại sau khi mã cũ đã chạy:** snapshot đã có thì không chép lại; bảng A5 còn nguyên. Mục tiêu đã chốt bởi mã cũ giữ nguyên trạng thái, không review hồi tố.

## 14. Hiệu năng

- Review không thêm vòng hỏi định kỳ: chỉ chạy khi `_settle` thêm `review_due` hay `review_retry`.
- Kiểm review hợp lệ là truy vấn theo `reviews_goal_rev` và `bundle_ref`, trong cùng kết nối của `_settle`.
- Thẻ mục tiêu thêm một truy vấn `goal_team` và `team_calls` theo `goal_id` trong goal view có sẵn (đã chạy ở luồng phụ từ 0.88.5, #602); không thêm request từ trang.
- Đầu vào review lấy từ bằng chứng đã lưu, không đọc lại file lớn; giới hạn 60.000 ký tự. Một lần băm lại ảnh chụp mỗi lượt review.
- **Kiểm:**
  - Test đo thời gian goal view với 200 mục tiêu có đội nằm trong cùng ngưỡng với `test_resonance_perf.py`.
  - Event loop không bị chặn khi review đang chạy (đồng hồ hẹn 10 ms như test hiện có).

## 15. Ma trận nghiệm thu (trước khi code)

Đồng hồ giả, engine giả, không model thật. Mỗi ca có đối chứng hợp lệ.

**Cột:**
- **Lượt** là (maker, reviewer, tổng) đã dùng khi kết thúc.
- **Model** là số lần engine giả được gọi.
- "Kết quả dùng được" là kết luận hay bản nào được phép dùng để chốt.

**Ca qua đường host thật:** các ca đánh dấu (H) phải chạy qua đường host thật: `form_goal` với tool `javis_goal` hay `POST /goal-requests`, scheduler thật, kho thật. Không chèn `goal_team` hay `reviews` vào fixture.

### 15.1 Luồng chính

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T1 (H) | Làm, khách quan đạt, review `pass`, không xác nhận người | `succeeded` | (1, 1, 2) | 2 | Review `pass` của H1 |
| T2 (H) | Như T1, có `human_confirmation` | `waiting/human_confirmation`, rồi `succeeded` khi chủ xác nhận đúng sha | (1, 1, 2) | 2 | Review và xác nhận cùng H1 |
| T3 (H) | Review `needs_changes`, làm sửa, review bản mới `pass` | `succeeded`; hai hàng review gắn hai `bundle_ref` | (2, 2, 4) | 4 | Review của H2 |
| T4 | Review `needs_changes` ba lần liên tiếp (vết V1 với lượt 6 là `needs_changes`): k = 1, 2 sinh lượt sửa; k = 3 chặn | `blocked/review_rounds`, tin `goal.review_exhausted` | (3, 3, 6) | 6 | Không |
| T5 | Đầu ra review không phải JSON, thiếu trường, `pass` mâu thuẫn: ba lượt liên tiếp | `review_retry` hai lần (lần tính 2, 3), rồi `blocked/review_unknown` (n = 3) | (1, 3, 4) | 4 | Không bao giờ coi là đạt |
| T6 | Lỗi engine ở lượt review, lần thử sau đạt (vết V4) | `succeeded` | (1, 2, 3) | 3 | Review lần tính 2 |
| T7 | Hết phần reviewer khi còn phần maker | `blocked/budget_reviewer` | (k, 4, k+4) | k+4 | Không mượn phần maker |
| T8 | Bản đầu và hai lần thử lại tự động đều chưa đạt khách quan; lượt thứ tư chỉ mở bởi tin mới của người dùng (`NEW`), vẫn chưa đạt | Sau lượt 3: chờ theo luật dự phòng A2, không tự thử. Sau lượt 4: `blocked/budget_maker` | (4, 0, 4) | 4 | Không review bản chưa đạt khách quan |
| T9 | Trần chung chạm khi còn phần vai | Không giữ chỗ; chờ như hiện tại | không đổi | 0 thêm | Trần thắng phần vai |

### 15.2 Bộ ghim, lịch và đồng thời (R2)

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T11 | Revision đổi trong lúc review chạy | Kết luận ghi với revision cũ, không dùng. `review_due` mới (ref có revision mới) | (k, +1) | +1 | Review của revision mới |
| T12 | Kết luận ghi về sai goal, sai reviewer, sai sha, sai hash tiêu chí | `review_mismatch`, không dùng | lượt tính | +1 | Không |
| T13 | Kết quả review được gửi lại hai lần | Một hàng `done`, lần hai bỏ qua | không đổi | không đổi | Hàng đầu |
| T14 | Khởi động lại sau mỗi bước: giữ chỗ, đang gọi engine, đã có đầu ra chưa ghi kết luận, đã ghi kết luận chưa `settle` | Phục hồi đúng mục 5.6 và 9.2; không mất lượt, không nhân đôi kết luận | đúng sổ | đúng số | Như bước cuối đã bền |
| T37 | Revision 2 giữ nguyên bytes và tiêu chí của revision 1 đã review | `review_due` mới được thêm và phục vụ (ref khác); không chờ mãi | (1, 2, 3) | 3 | Review của revision 2 |
| T38 | Một sự kiện `review_due` gửi hai lần (hai lần `_settle` cùng bộ) | Một lý do, một lượt | (1, 1, 2) | 2 | Một review |
| T39 | `unknown` rồi thử lại, khởi động lại giữa hai lần | Lần thử sau chạy đúng một lần sau khởi động; `seq` liên tục, `n` đúng | (1, 2, 3) | 3 | Review lần tính 2 |
| T40 | Chủ dự án bật lại reviewer (version mới) sau `pass` | `review_due` mới với version mới chạy được | (1, 2, 3) | 3 | Review version mới |
| T41 | Kiểm cả lý do chờ, lịch vật lý (`wake_reasons`, `wakeups`) và số lượt sau mỗi ca 37 đến 40 | Không có lý do treo, không có hẹn mồ côi | | | |
| T22 | Hai lần đánh thức đồng thời (lý do làm và lý do review cùng đến hạn) | Một hành động chạy; cái kia chờ lease | đúng sổ | 1 | |
| T59 | Chat maker nộp bản mới qua A4 trong lúc review nền chạy | Kết luận ghi cho bản cũ, không dùng. `review_due` cho bản mới | (k, +1) | +1 | Review bản mới. Lease không chặn chat (mục 7.2) |

### 15.3 Gắn đội (R1)

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T31 (H) | Tạo qua tool `javis_goal` trong phiên agent có cặp bật | `goal_team active`, `team_calls` 4/4, `budget_calls = 8`, cùng giao dịch với `goal_agents`; `assign_goal` thay bằng hàm ném lỗi vẫn đạt | (0, 0, 0) lúc tạo | 0 | |
| T32 (H) | Tạo qua `POST /goal-requests` | Như T31 | | 0 (có đề xuất) hoặc 1 bộ lập (sổ riêng) | |
| T33 (H) | Tạo lặp cùng tin (cùng `idempotency_key`), giữa hai lần đổi cặp sang reviewer khác | Trả mục tiêu cũ; reviewer, budget, `team_calls` không đổi | không đổi | 0 | |
| T34 | Cặp tắt lúc tạo | Không có `goal_team`; chạy như A4 | như A4 | | |
| T35 | Reviewer bị tắt đúng lúc tạo (cặp bật) | `goal_team active`; lần thức đầu `blocked/reviewer_off`, không bỏ review | (1, 0, 1) nếu bản đầu đã làm | | |
| T36 | Mục tiêu cũ đã tiêu lượt, chủ dự án gán qua `assign_goal` cho agent có cặp | Không có đội; `calls_used` giữ nguyên; thẻ "không có người review"; sự kiện `not_attached_legacy` | giữ nguyên | | Theo A4 |
| T25 | Mục tiêu tạo khi không có cặp | Không có `goal_team`; như A4 | như A4 | | |

### 15.4 Reviewer tắt, bật, mất, nghỉ (R3)

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T18 | Tắt reviewer khi đang chờ review | `blocked/reviewer_off`, hẹn kiểm lại; bật lại cùng mã thì chạy tiếp theo mục 7.3 | không đổi tới khi bật | 0 khi tắt | |
| T42 | On v1, có `pass`, off v2, on v3 | Review lại một lượt; `team_calls`, số vòng, chuỗi lỗi không reset | (1, 2, 3) | 3 | Review v3 |
| T43 | Review đang chạy lúc tắt rồi bật | Kết quả ghi với v1, không dùng; review v3 | (1, 2, 3) | 3 | Review v3 |
| T44 | Khởi động lại khi reviewer đang tắt | Vẫn `blocked/reviewer_off` sau khởi động; không gọi model | không đổi | 0 | |
| T45 | File reviewer mất, chủ dự án xác nhận `confirmed_same` | Cùng mã, version mới, review lại | +1 reviewer | +1 | Review version mới |
| T46 | Reviewer bị xoá (nghỉ mã), tạo agent mới cùng slug và cùng tag | `blocked/reviewer_retired`; mã mới không được nhận; chỉ tách đội hay huỷ | không đổi | 0 | |
| T19 | Đổi trạng thái reviewer trong lúc review chạy | Kết luận là review cũ, không dùng; chặn hay review lại theo trạng thái mới | (k, +1) | +1 | |

### 15.5 Ngân sách (R4)

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T47 | Vết V1: thành công, hai vòng sửa | `succeeded` | (3, 3, 6) | 6 | Review lượt 6 |
| T48 | Vết V2: một lỗi maker | `succeeded`, lượt sửa thứ hai dùng lượt cuối của maker (`FIX`) | (4, 3, 7) | 7 | |
| T49 | Vết V3: hai lỗi maker | `blocked/budget_maker` sau vòng 2 | (4, 2, 6) | 6 | Không |
| T50 | Vết V5: reviewer còn đúng một lượt khi `unknown` | `blocked/review_unknown`, không `review_retry` | (3, 3, 6) | 6 | Không |
| T51 | Mục tiêu có đội có bài học làn M `trial_pending` | `begin_experiment` trả None ở kho; bài học `skipped/team_goal`; không thêm `calls_used` | không đổi | 0 | |
| T52 | Huỷ trước engine review; huỷ sau engine có thể đã chạy | Trước: hoàn tổng và reviewer, hàng `cancelled/not_run`. Sau: không hoàn | (k, 0) / (k, 1) | 0 / 1 | Kết quả muộn không dùng |
| T53 | `release_call` khi engine bị chặn trước lượt review | Hoàn đúng vai reviewer theo `action_id` | (k, 0) | 0 | |
| T54 | Tách đội ở (3, 2, 5) rồi khởi động lại | `team_calls` vẫn (3, 2); mục tiêu còn 3 lượt theo A4; làn M chạy lại được | giữ | | Theo A4 |
| T15 | Huỷ trước khi gọi engine review | `cancelled/not_run`, hoàn cả hai bộ đếm | (k, 0) | 0 | |
| T16 | Huỷ sau khi engine review có thể đã chạy | `failed/cancelled`, không hoàn | (k, 1) | 1 | Không |

### 15.6 Bản sửa ngoài luồng và ảnh chụp (R5)

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T10 | Chủ dự án sửa tay file thành H2 sau review `pass` của H1, H2 vẫn đạt kiểm khách quan | `waiting/source_drift`; không review, không chốt, không đăng đè | không đổi | 0 | Không (review H1 không áp cho H2) |
| T55 | Sửa tay trong lúc review H1 đang chạy | Kết luận ghi cho H1; lúc chốt thấy lệch, `waiting/source_drift` | (k, +1) | +1 | Chỉ nếu file về lại H1 |
| T56 | Sau T10, file được khôi phục đúng bytes H1 | `succeeded` bằng review H1 cũ, không gọi model | không đổi | 0 | Review H1 |
| T57 | Sau T10, maker nộp H2 qua `javis_submit_deliverable` hợp lệ (A4) | Mốc đăng mới; `review_due` cho H2; ảnh chụp đọc từ bằng chứng của H2 | (k, +1) | +1 | Review H2 |
| T58 | Bằng chứng ảnh chụp có hash khác `artifact_sha` (bị hỏng hay thay) | `unknown/snapshot_mismatch`, `blocked/review_input`, không giữ chỗ | không đổi | 0 | Không |
| T28 | Bản quá `REVIEW_INPUT_MAX_CHARS` (vết V6) | `unknown/too_large`, `blocked/review_input`; không tự thử lại, không nhịp thức sát nhau | không đổi | 0 | Không |

Mọi ca 15.6 kiểm thêm: hash của bytes thật sự gửi engine giả bằng `artifact_sha` của bộ ghim.

### 15.7 Quyền, dừng, phạm vi

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T17 | Thu hồi quyền ghi khi review đang chờ; cấp lại | Tạm dừng; sau cấp lại, review cũ dùng được nếu bộ ghim khớp; lượt làm cũ không hưởng quyền mới | không đổi | 0 | Theo A4 |
| T20 | Tắt agent làm | `blocked/agent_off` như A1; không review | không đổi | 0 | |
| T21 | Guard chặn bản đã review `pass` | `blocked/guard`; review không xoá guard; `host_publish` không ghi | không đổi | 0 | |
| T23 | Lỗi lưu bằng chứng của đầu ra review | `unknown/storage_error`, lượt tính, `review_retry` theo luật AUTO | (k, +1) | +1 | Không |
| T24 | `team_detach` khi đang chờ review | Chốt theo luật A4; review đang chạy không dùng | không đổi | | |
| T26 | Reviewer cố trả trường đổi tiêu chí hay hạn mức | Trường bị bỏ qua, ghi sự kiện; kết luận chỉ từ ba trường | như T1 | | |
| T27 | Bản nộp trong chat (A4) trên mục tiêu có đội | Đăng theo A4; review chạy ở việc nền, tính phần reviewer | (0, 1, 1) | 1 | |
| T29 | Chat thường không có mục tiêu với agent có đội | Không tạo mục tiêu, không review | (0, 0, 0) | 0 | |
| T60 | Đổi tên hay xoá một tag mà reviewer và maker đang mang | `team_pairs`, `goal_team` không đổi; ô Người review không đổi danh sách | không đổi | 0 | |
| T30 | Nâng kho từ 0.108.0; khôi phục về 0.108.0 bằng script | Snapshot đúng một bản; mã 0.108.0 thật mở được kho khôi phục | | | Ghi nhận giới hạn hạ không khôi phục |

### 15.8 Bộ đếm thử lại, lịch đối soát, vòng sửa (vòng 3)

| Ca | Tình huống | Trạng thái, lý do cuối | Lượt | Model | Kết quả dùng được |
|---|---|---|---|---|---|
| T61 | Vết V8: hai lần huỷ trước engine (một `abort_action`, một `release_call` do engine không dựng được), rồi `unknown` ở lần gọi đầu | `review_retry` hợp lệ sau đúng `ERROR_BACKOFF_S[0]`; trước lần thử lại `reviewer.used = 1`, `n = 1`; seq 1 đến 4 | (1, 2, 3) | 2 | Review seq 4 |
| T62 | Ba lần huỷ trước engine rồi `pass` | Không bị trần thử chặn; `n = 1` | (1, 1, 2) | 1 | Review lần gọi thật |
| T63 | Huỷ sau khi engine có thể đã chạy; khởi động lại khi không xác định được đã gọi chưa | `charged = 1`, tính vào trần thử và ngân sách; `failed/cancelled` hay `failed/interrupted` | (k, +1) | +1 hoặc 0 thật | Không |
| T64 | Hoàn lặp: `abort_action` hai lần, `release_call` rồi `abort_action` cùng hành động, mở lại kho rồi hoàn lại | Chỉ lần đầu có tác dụng; `calls_used`, `team_calls`, `charged`, lý do và trạng thái hàng nhất quán, không trừ hai lần | đúng sổ | 0 | |
| T65 | Engine không dựng được ở lượt review | Hàng `cancelled`, `charged = 0`, không còn `running`; lý do về `pending`; không có hẹn `action_recovery` mồ côi | (k, 0) | 0 | |
| T66 | Khởi động lại khi review đang chạy, rồi tới giờ `action_recovery` | Đối soát chỉ bằng code: không mở lượt `work` của maker, không gọi review trước backoff; `review_retry` thêm sau đối soát | (k, +1 đã tính) | 0 lúc đối soát | |
| T67 | Một kết luận `needs_changes` ghi sau khi revision hay mốc đăng đã đổi (`stale`), và một kết luận `review_mismatch` | Không tính vào `k`, không sinh `review_changes`; bản đang dùng vẫn cần review của riêng nó | (k, +1) | +1 | Không |

## 16. Quyết định

### 16.1 Mặc định đề xuất

D1 đến D5 theo khuyến nghị của review vòng 1, Q1 đến Q5. Đây là cấu hình sản phẩm, **chưa phải cấp phép chạy pilot**.

| # | Quyết định | Lý do |
|---|---|---|
| D1 (Q1) | Review chạy SAU khi đăng bản (luật A4 giữ nguyên), TRƯỚC khi chốt đạt. Thẻ ghi "chưa nghiệm thu" tới khi review đạt | Không đổi hợp đồng A4 đã pilot. Review không phải cổng chặn nội dung xấu ở file đích (mục 7.2) |
| D2 (Q2) | `budget_calls = 8`, maker 4, reviewer 4, `max_rounds = 2`, không có ô chỉnh | Ít cài đặt. Lời hứa đúng ở mục 6.4: lỗi làm giảm số vòng sửa thực hiện được khi đã hết dự phòng |
| D3 (Q3) | Hai vai dùng chung model việc nền; khác danh tính, lời dặn và dữ liệu | Không quảng cáo hai model độc lập |
| D4 (Q4) | Xác nhận sớm của chủ dự án không bỏ qua review. Xác nhận lưu theo đúng sha; bản đổi thì xác nhận không đi theo | Hai quyền khác nhau (A4 bất biến 5) |
| D5 (Q5) | Hết vòng hay hết lượt: chặn, báo, chờ. Chưa có lệnh nâng hạn mức. `team_detach` chỉ chủ dự án, nói rõ là bỏ yêu cầu review | Không biến tách đội thành đường agent tự bỏ kiểm |
| D6 | Review chỉ chạy trên bản đã đạt kiểm khách quan và còn nguyên bytes | Không tốn lượt review cho lỗi code tự bắt được hay bản đang bị sửa tay |
| D7 | Kết luận đóng khi lỗi; không đọc chữ tự do. `too_large`, `snapshot_mismatch` là lỗi cố định | Bước `verify_agent` hiện mặc định đạt khi lỗi |
| D8 | Reviewer chỉ thấy ảnh chụp đã kiểm hash, tiêu chí, ràng buộc, mô tả vai; không thấy chat, review cũ hay tag | Giảm neo theo người làm và theo kết luận trước |
| D9 | Ghim mã reviewer (bền) lúc tạo mục tiêu; version ghim theo từng lần review. Bật lại cùng mã thì review lại bản hiện tại, tính lượt, không reset. Mã mới cùng slug không thay | Sửa R3: công tắc tạm tắt dùng được mà không mở đường đổi người chấm |
| D10 | Hai vai dùng chung lease mục tiêu, không chạy song song ở việc nền | Dùng lại A2; lease không chặn chat (mục 7.2) |
| D11 | Đội gắn trong giao dịch `create`. Mục tiêu cũ gán qua `assign_goal` không có đội | Sửa R1; không chia lại lượt đã tiêu |
| D12 | Làn M của A3 tạm tắt trên mục tiêu có đội, kiểm ở kho | Sửa R4; không có đường lượt ngoài sổ vai |
| D13 | Không có lượt review trong chat | Lượt chat dùng engine có công cụ gốc; không thực thi được "chỉ đọc" ở đó |
| D14 | Bản sửa ngoài luồng không tự thành bản được tiếp nhận; mục tiêu có đội chờ, không chốt dù bản sửa đạt khách quan. **Chủ dự án đã chọn (phương án A, 12/10/2026)** | Sửa R5; không mở rộng hợp đồng A4. Muốn giữ bản sửa tay thì chủ dự án bấm "Bỏ yêu cầu review" |
| D15 | Tag không tham gia chọn reviewer, ghép cặp, quyền hay nhóm chat | Hợp đồng tag 0.100.0 |

### 16.2 Quyết định đã chốt

- **Bản sửa tay đạt kiểm khách quan trên mục tiêu có đội: phương án A** (chủ dự án chọn ngày 12/10/2026). Mục tiêu có đội không chốt trên bản sửa tay, chờ file về lại bản đã review hay một bản mới đi qua A4. Muốn giữ bản sửa tay thì chủ dự án bấm "Bỏ yêu cầu review" (`team_detach`). Không thêm tính năng tự nhận file sửa tay.
- Q1 đến Q5 vòng 1 đã giải quyết theo khuyến nghị (D1 đến D5).

Không còn điểm nào chờ chủ dự án quyết ở mức thiết kế. Các mặc định vẫn chưa phải cấp phép pilot.

## 17. Kế hoạch code và ranh giới bằng chứng

**Thứ tự** (một PR #616, nhiều commit, review mã theo vòng như A4):
1. **Kho:**
   - `_A5_SCHEMA`, nâng kho và snapshot.
   - `team_pairs`; `_attach_team` trong `create` (T31 đến T36 qua đường host).
   - `team_calls` trong `begin_action`; `release_call` theo `action_id`; `abort_action` cho `review`.
   - Từ chối `begin_experiment` khi có đội.
   - Test kho: T7 đến T9, T14 phần kho, T15, T16, T30, T51 đến T54, T61 đến T65.
2. **Review:**
   - `_review_prompt`, `parse_review`: test hàm thuần T5, T26, T28.
   - Dựng và kiểm ảnh chụp: T58.
   - `_review_step`, ghi kết luận có CAS (T12, T13), phục hồi (T14, T39).
3. **Chốt và lịch:**
   - Nhánh team trong `_settle` gồm 5.5; cổng 7.3; mã, lớp `FIX` và lỗi cố định trong A2.
   - Ca: T1 đến T4, T6, T10, T11, T17 đến T25, T27, T29, T37 đến T50, T55 đến T57, T59, T60, T66, T67.
4. **API và giao diện:**
   - Ô Người review, dòng đội và nút trên thẻ, `team_detach`.
   - Test JS và smoke sandbox bằng engine giả.
5. **Hiệu năng và hồi quy:** hiệu năng (mục 14) và hồi quy toàn bộ Resonance, gồm cả test tag 0.100.0.

**Ranh giới bằng chứng:**
- **Trước review mã:** chỉ engine giả và đọc mã. Không thử engine thật không có key (có thể rơi về CLI đã đăng nhập sẵn).
- **Pilot thật:** đơn riêng sau khi mã đạt review, chủ dự án duyệt bằng lời của mình.
  - Đề xuất sẽ nêu số lượt cụ thể: dự kiến tối đa 1 lượt chat cộng phần việc nền của đội.
  - Không dùng lại hạn mức pilot cũ.
- Một pilot không chứng minh mọi engine hay mọi kênh.

## 18. Kiểm mã nền (không phải kiểm A5)

Probe của reviewer `exports/reviews/PR-616-A5-design-r1-probe.py`, chạy nguyên văn trên nền mới (nhánh A5 sau khi nhập `main` `a02663cb`), kho SQLite tạm, không engine:
- `create` gắn agent mà không gọi `assign_goal`; gọi `assign_goal` sau đó bị từ chối.
- Bật/tắt/bật cho version 1, 2, 3; ghim version 1 bị `agent_changed`.
- `review_due` đã phục vụ chặn cùng `source_ref` cho revision mới.
- `auto_allowed` từ chối `review_changes` và `error_retry` khi còn đúng một lượt.

Probe exit 0. Đây là ngữ nghĩa của mã nền mà thiết kế vòng 2 dựa vào, không phải bằng chứng A5 đã sửa. Thiết kế không dùng probe để báo "hết tái hiện"; test hành vi A5 viết khi có mã.
