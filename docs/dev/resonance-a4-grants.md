# Resonance A4: nộp sản phẩm qua hợp đồng host, phạm vi do chủ dự án cho phép

Hướng dẫn cho người sửa mã. Thiết kế chốt: [2026-10-10-resonance-a4-handoff-grants-design.md](../superpowers/specs/2026-10-10-resonance-a4-handoff-grants-design.md) (D1: **không cấp quyền ghi từ lời chat**). Biên bản kiểm: [resonance-a4-verification.md](resonance-a4-verification.md).

## Một câu

Mọi engine nộp sản phẩm qua cùng một cửa: host xác định lượt, ghim quyền vào lượt, tự đọc và băm bytes, lưu bản nộp có biên nhận, rồi tự đăng vào file đích theo bốn bước có mốc commit tuần tự với thu hồi. Đích chỉ có quyền khi chủ dự án bấm Cho phép trên thẻ (hay đóng băng legacy lúc nâng kho).

## Mã ở đâu

| Phần | File |
|---|---|
| Luật thuần: khoá đường, `narrow`, `allows`, dấu vân tay, bảng khả năng engine | `server/resonance_grants.py` (mới) |
| Kho: sáu bảng A4, snapshot `.pre-0.93.0`, đóng băng legacy, phạm vi theo revision, liên kết, bản nộp, bốn bước đăng, Cho phép, Không, Thu hồi, Cấp lại, đăng lại | `server/resonance_store.py` (mục "A4" cuối class) |
| `host_publish`, đối soát đăng, `_publish_latest` theo bản nộp, `_work_post_core` chèn bản nộp trước đăng, bàn giao cuối lượt, `submit_deliverable`, cổng phạm vi trong `_gate`, lệnh chủ dự án, khối `scope` của thẻ | `server/resonance.py` |
| Công cụ hub `javis_submit_deliverable`, ghi chú phạm vi và mã `handoff` trong kết quả `javis_goal` | `system/plugins/javis-goal/plugin.py`, `plugin.yaml` |
| Ảnh chụp thứ tự quyền đầu lượt, provider của lượt | `server/turn_context.py`, `server/main.py` (`_resonance_turn_agent`) |
| Bàn giao mọi mục tiêu của một tin; đăng ký phụ thuộc cho công cụ trong tiến trình | `server/main.py` (`_resonance_after_turn`, `resonance.set_deps_provider`) |
| Xem trước bản nháp | `server/resonance_api.py` (`GET /goals/{id}/drafts/{submission_id}`) |
| Thẻ: dòng quyền, Cho phép / Không / Xem trước / Thu hồi quyền | `dashboard/chat-resonance.js`, `dashboard/resonance-agent.js`, `dashboard/style.css`, `dashboard/i18n/*.json` |
| Hạ về 0.92.1 | `tools/resonance_restore_pre_a4.py` |

## Vòng đời

**Phạm vi.** `grants` có hai tầng: gốc (`kind=root`, một đích, nguồn `owner_approved` hay `legacy_frozen`) và quyền revision (`narrow` của gốc với đích của revision). `scope_state` trả một trong: `none` (mục tiêu chưa gán trợ lý hay không có đường sản phẩm: không cần phạm vi), `granted`, `pending`, `denied`, `revoked`, `missing`. `_gate` gác mọi trạng thái khác `none`/`granted` với `block_reason` `scope_pending`, `scope_denied`, `grant_revoked`, `grant_missing` (gác thật: `run_state=blocked`, không hẹn lịch, không gọi model).

**Revision mới.** Trong chính giao dịch tạo revision (`create`, `revise`, `drop_directive`, `assign_goal`), `_scope_sync`:
- cùng đích với gốc đang active: cấp quyền revision mới, không hỏi;
- khác đích, hay chưa có gốc: ghi `scope_requests` (`create`/`expand`), không cấp gì;
- quyền và yêu cầu của revision cũ thành `superseded`; `_retire_old_revision` đưa bản nộp chưa đăng của revision cũ về `superseded` và đóng liên kết cũ.

**Liên kết.** `bindings` ghim quyền vào một lượt: `handoff` (lượt chat, khoá `message_ref`), `action`, `followup`, `experiment`, `approval`, `republish`. Khoá `UNIQUE(goal_id, revision, origin_kind, origin_ref)`; mở lại cùng khoá trả dòng có sẵn, không bao giờ REPLACE. Trạng thái: `live` (nhận lời nộp), `sealed` (chỉ hoàn tất bản đã nhận), `closed`, `dead` (thu hồi). Hai phép kiểm: `_binding_block(finishing=False)` là `binding_accepts`, `finishing=True` là `binding_may_finish` (chỉ thẩm quyền `grant`).

**Thứ tự quyền.** `authority_clock.seq` tăng trong mọi giao dịch tạo gốc, thu hồi, chấp thuận, cấp lại. `_resonance_turn_agent` đọc nó trước khi engine chạy và đặt vào `turn.authority_seq`. Liên kết `grant` đầu tiên của một tin cho một mục tiêu chỉ nhận gốc có `seq` không vượt ảnh chụp; mọi liên kết sau của cùng tin phải ghim cùng gốc. Không có ngoại lệ (D1).

**Bản nộp.** `submissions`: `awaiting_scope` (nháp dưới liên kết `draft`), `candidate`, `publishing`, `published` (+ `adopted_at`), `adopted_in_place`, `promoted`, `conflict`, `stale`, `superseded`, `rejected`. Nguồn: `submit_tool`, `background_text`, `observed_write`, `approved_draft`, `republish`. Bytes đăng luôn đọc lại từ file nháp, chuẩn hoá gạch dài và phải khớp sha trong sổ.

**Đăng (`host_publish`).** Guard trên bytes bản nộp, rồi:
1. `publish_intent` (kiểm liên kết, quyền `publish`, tạm dừng, chốt guard, baseline; nhánh `same` ghi mốc ngay);
2. ghi file tạm `.<tên>.<action_id>.tmp`;
3. `publish_commit` (`BEGIN IMMEDIATE`, kiểm lại, đọc lại hash đích trong giao dịch, ghi `commit_at`);
4. `os.replace`, `publish_finish` (không kiểm lại quyền), rồi `adopt_submission` cho nguồn chat và bản nháp được duyệt.

**Đối soát** (`_reconcile`, `_reconcile_publish`): đăng chưa commit thì huỷ, bản nộp về `candidate` hay `stale`; đã commit thì hoàn tất từ bản nháp; bản đã đăng chưa tiếp nhận thì tiếp nhận đúng một lần (khoá sự kiện `adopt:<submission_id>`). Lỗi đọc hay ghi tạm thời sau commit không chốt xung đột: `publish_retry` giữ hành động chạy và hẹn lại có giãn cách. Mốc commit đặt lịch vật lý riêng `settle`, tới hạn cả khi mục tiêu tạm dừng, thu hồi, huỷ hay kết thúc; lần thức `settle` chỉ hoàn tất lần đăng đã chốt.

**Nghĩa vụ hoàn tất** (I13 tới I16): file nháp không đọc được tạm thời thì giữ nghĩa vụ, mất hay sai hash thì loại với lý do riêng (`draft_missing`, `draft_hash_mismatch`); lịch `settle` chỉ bỏ khi không còn lần đăng đã commit dở VÀ không còn bản đã đăng chưa tiếp nhận; trong lúc còn nghĩa vụ, lịch làm việc gác `publish_settling`, không gọi model. Lần thức làm việc xét lại nghĩa vụ cả SAU khi tự đăng: lỗi phát sinh ngay trong nhịp đó cũng gác. File nháp chưa đọc được trước mốc commit thì bản nộp được giữ (`hold_until`), lịch `settle` đọc lại có giãn cách, đọc được thì bỏ giữ để lịch làm việc đăng đúng bản đó.

**Can thiệp trước mốc commit** (`_publish_held`): tạm dừng, chốt guard, và phản hồi cách hiểu mới nhất là "Chưa đúng ý" đều chặn lần đăng chưa commit, kiểm ngay trong giao dịch ý định và giao dịch mốc commit.

**Lệnh chủ dự án** (`POST /goals/{id}/commands`): `approve_scope` (CAS yêu cầu, revision, đường, trợ lý, bản nháp mới nhất đúng sha), `deny_scope`, `revoke_grant`, `resume` (đang thu hồi thì cấp lại gốc mới).

## Hành vi đổi so với 0.92.1

- Mục tiêu mới có đường sản phẩm luôn chờ chủ dự án cho phép, kể cả khi lời giao nêu đích. Write của bộ não trong lượt LẬP mục tiêu không được tiếp nhận (lượt đó chưa có phạm vi lúc bắt đầu); bản nộp qua công cụ được giữ làm nháp và Cho phép đăng nó.
- Tắt Cộng hưởng của trợ lý không thu hồi phạm vi (I1): bật lại thì làm tiếp dưới gốc cũ. Nhưng tắt rồi bật giữa lượt làm bản nộp của lượt đó `stale`, không đăng lại dưới version mới (trước đây A1 đăng lại đầu ra giữ bằng ý định mới). Lần thức sau làm lại một lượt.
- `_publish_latest` chỉ đăng bản `candidate`; không còn đăng đầu ra hành động trần. File đích bị xoá thì đăng lại bản đã đăng dưới liên kết `republish` mới (quyền hiện hành).
- Codex và engine API nhận bàn giao chat qua `javis_submit_deliverable` (`engine_support` có thêm `submit_tool`, `observed_write`).

## Hạ phiên bản

Lần đầu mã A4 mở một kho có từ trước, `_backup_before("grants", ".pre-0.93.0")` chép kho bằng SQLite backup API, rồi một giao dịch tạo bảng và đóng băng legacy. Hạ về 0.92.1 chỉ hỗ trợ bằng `tools/resonance_restore_pre_a4.py --yes` khi Javis đã tắt: chép kho hiện tại sang `resonance.sqlite3.post-0.93.0-<thời điểm>`, rồi ghi snapshot vào. Chạy 0.92.1 trên kho A4 mà không khôi phục là không hỗ trợ (mã cũ gỡ tạm dừng của mục tiêu đã thu hồi; test G48 ghi nhận đúng giới hạn này).
