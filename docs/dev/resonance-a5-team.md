# Resonance A5: một agent làm, một agent review

Hướng dẫn cho người sửa mã. Thiết kế chốt: [2026-10-11-resonance-a5-maker-reviewer-design.md](../superpowers/specs/2026-10-11-resonance-a5-maker-reviewer-design.md) (đạt review thiết kế vòng 3 tại `56f7ab50`; chủ dự án chọn phương án A cho file sửa tay). Biên bản kiểm: [resonance-a5-verification.md](resonance-a5-verification.md).

## Một câu

Chủ dự án chọn một agent Cộng hưởng khác làm người review cho một agent làm. Từ đó mỗi mục tiêu MỚI của agent làm có đội: bản đạt kiểm khách quan phải được người review kết luận `pass` trên đúng bản đã tiếp nhận rồi mới được chốt. Review chạy ở việc nền, bằng engine chỉ chữ chung, trong sổ lượt riêng của từng vai (8 lượt, 4/4, tối đa 2 vòng sửa).

## Mã ở đâu

| Phần | File |
|---|---|
| Bốn bảng A5, snapshot `.pre-0.109.0`, gắn đội trong `create`, sổ vai trong `begin_action`, một đường hoàn `_refund_not_run`, `release_call` theo `action_id`, từ chối `begin_experiment` khi có đội, chốt chặn trong `finish`, `record_review`, `review_interrupted`, `team_detach`, `team_pair_set`, `team_reviewer_enable`, mốc `mark_engine` và `abort_action(..., recheck_at)`, `wake_agent_goals` cho reviewer | `server/resonance_store.py` (mục "A5" cuối class, cùng các chỗ nối) |
| `parse_review`, `accepted_snapshot`, `bundle_ref`, `_review_state`, `_team_review`, `_team_settle`, `_review_pre`/`_review_step`/`_review_post`, cổng người review trong `_gate`, nhánh đội trong `_wake_work` và `_settle`, góp ý vào `_work_prompt`, `_prepare_failed`, khối `team` của goal view, câu báo `goal.review_*`, lệnh `team_detach` | `server/resonance.py` |
| `heartbeat.v3`: mã `review_due` (START), `review_retry` (AUTO), `review_changes` (lớp mới `FIX`), `review_recheck`, `prepare_recheck`; lỗi cố định `too_large`, `snapshot_mismatch` | `server/resonance_heartbeat.py` |
| `POST /resonance/agents/reviewer` và `POST /goals/{id}/reviewer/enable` (đăng ký cuối, `register_a5`), trường `reviewer` của danh sách trợ lý | `server/resonance_api.py`, `server/main.py` |
| Ô Người review; dòng đội, góp ý, nút Bật lại người review và Bỏ yêu cầu review trên thẻ; khoá i18n | `dashboard/resonance-agent.js`, `dashboard/chat-resonance.js`, `dashboard/i18n/vi.json`, `en.json` |
| Hạ về 0.108.0 | `tools/resonance_restore_pre_a5.py` |

## Vòng đời

**Cặp và đội.** `team_pairs` lưu cặp theo `agent_key` (không theo slug, không theo tag), chỉ chủ dự án đổi. `create` gọi `_attach_team` NGAY sau dòng `goal_agents`, trong cùng giao dịch: cặp đang bật thì ghi `goal_team` (ghim mã bền của reviewer), hai dòng `team_calls` (4/4) và đặt `budget_calls = 8`. Tool `javis_goal` và `POST /goal-requests` đều đi qua `form_goal`, tức qua `create`. `assign_goal` (mục tiêu cũ) không gắn đội; sự kiện ghi `not_attached_legacy`.

**Sổ vai.** `begin_action` suy vai từ loại hành động (`work` thì `maker`, `review` thì `reviewer`), kiểm `team_calls` TRƯỚC khi trừ, rồi tăng `calls_used` và phần vai trong cùng giao dịch; ghi `role` vào ý định. Mọi đường hoàn dùng vai đã ghi.

**Hoàn lượt.** Chỉ khi host chắc engine chưa chạy:
- `abort_action` (huỷ trước lời gọi) và, với lượt review, `release_call(action_id)` (engine không dựng được) đi qua `_refund_not_run`: CAS hành động `running` sang `cancelled/not_run`, trừ tổng và vai, hàng review `cancelled` với `charged = 0`, lý do đã phục vụ về `pending`. Hoàn lặp không có tác dụng.
- Lượt VIỆC của mục tiêu có đội khi engine không dựng được giữ đúng hành vi A2 (hành động được kết sổ lỗi ngay sau đó) và trả thêm phần maker trong cùng giao dịch; cờ `refunded` trong ý định chặn trả hai lần.
- Pha chuẩn bị LỖI sau khi giữ chỗ (review mã vòng 1, R1): `_prepare_failed` gọi `abort_action(code='prepare_error', recheck_at=...)`, một giao dịch hoàn đúng hành động đó và gác kèm hẹn kiểm lại bằng code (lượt review: `blocked/review_engine` + `review_recheck`; lượt việc: `blocked/prepare_error` + `prepare_recheck`). Lần thức trước hạn không giữ chỗ lại; tin mới của người dùng vẫn mở lượt làm.
- **Mốc gọi engine.** Mọi hành động `work`/`review` mới mang `engine_mark = 1`. Bước cuối của pha chuẩn bị là `mark_engine`: ghi `engine_at` và đưa mục tiêu sang `running` trong một giao dịch; thiếu mốc thì không gọi engine. Đối soát sau khi hết khoá: có `engine_mark` mà chưa có `engine_at` thì engine CHẮC CHẮN chưa chạy, hoàn qua đường not-run (kể cả khi lần hoàn ngay lúc lỗi cũng hỏng); đã có `engine_at` hay hành động cũ không có cờ thì giữ luật cũ (có thể đã chạy).
- Model có thể đã chạy (huỷ trong lúc gọi, khởi động lại sau mốc gọi engine): không hoàn; hàng review `failed`, `charged = 1`.

**Bộ ghim và lượt review.** `accepted_snapshot` lấy bản ĐƯỢC TIẾP NHẬN (mốc đăng A4 của file sản phẩm và bằng chứng của đúng bytes đó, hay đầu ra mới nhất của revision khi không có file đích), băm lại; lệch là `snapshot_mismatch`, dài quá 60.000 ký tự là `too_large` (lỗi cố định, không giữ chỗ, chờ người xử lý). `bundle_ref` = `rb:<revision>:<mốc đăng>:<sha>:<hash tiêu chí>:<mã reviewer>:<version reviewer>`. `begin_action(kind='review')` chèn hàng `reviews` với `seq` tăng dần (lưu vết) và `charged = 1`. Trần thử (3) và chỉ số backoff đếm số hàng `charged = 1` của bộ ghim, không đếm `seq`.

**Ghi kết luận.** `parse_review` đóng khi lỗi (chỉ một đối tượng JSON, đủ mọi chỉ số tiêu chí, `ok` kiểu bool; mâu thuẫn là `inconsistent`). `record_review` CAS hàng từ `running`; kết luận lệch hành động là `review_mismatch`, lỗi thời so với bộ ghim hiện tại (revision, mốc đăng, version reviewer đổi) là `stale`: lưu nhưng không dùng, không tính vòng, chỉ hẹn một lần thức chỉ-kiểm. Kết luận hợp lệ:
- `pass`: lý do chỉ-kiểm `review_done`; lần thức sau chốt.
- `needs_changes`: đếm `k` SAU khi ghi; `k ≤ 2` thì `review_changes` (FIX), `k = 3` thì `blocked/review_rounds` và tin `goal.review_exhausted`.
- `unknown`: lỗi cố định thì `blocked/review_input`; lỗi tạm thời thì `review_retry rr:<id>` hẹn theo `ERROR_BACKOFF_S[n-1]` khi `n < 3` và vai review còn ít nhất 2 lượt, không thì `blocked/review_unknown`.

**Lịch.** Lượt review chỉ hẹn `action_recovery` (đối soát bằng code). `_reconcile` gặp lượt review dở thì gọi `review_interrupted`: chốt hàng `failed/interrupted` rồi mới xét luật thử lại. Không bao giờ thành lượt của vai làm. `decide` của vai làm không thấy `review_due`/`review_retry`; lớp `FIX` dùng được lượt cuối của vai làm, `AUTO` cần còn ít nhất 2 lượt của vai.

**Chốt.** `_settle` (cả từ lần thức lẫn sau lượt làm) gọi `_team_settle` cho MỌI bản đạt kiểm (hay chỉ còn chờ người xác nhận) của mục tiêu có đội, ở mọi mode và stage (review mã vòng 1, R3), trước bước kế tiếp: kết thúc, chờ người xác nhận, `discovery_done`, hay giữ mục tiêu `maintain` ở `healthy` (tin `goal.maintained` chỉ phát sau `pass`). Cùng bộ ghim đã có `pass` thì đi thẳng, nhịp kiểm định kỳ không review lại. Điều kiện: bytes đang ở đĩa phải đúng bản được tiếp nhận (phương án A: sửa tay thì `waiting/source_drift`, kể cả khi bản sửa đạt kiểm; khôi phục đúng bytes thì dùng lại kết luận cũ), và bộ ghim hiện tại phải có `pass` hợp lệ. `store.finish` kiểm lại trong chính giao dịch kết thúc (`_review_pass_block`).

**Cổng người review.** `_gate` kiểm `agent_gate(reviewer_agent_key)` không truyền version: tắt thì `blocked/reviewer_off`, mất file `reviewer_missing`, nghỉ mã `reviewer_retired`. Version chỉ ghim ở từng lần review; bật lại cùng mã thì kết luận cũ không còn hợp lệ (bộ ghim mang version mới) và bản hiện tại được review lại, tính một lượt; không đặt lại lượt, vòng hay lỗi. Agent mới cùng slug hay cùng tag là mã khác, không bao giờ thay. Nút Bật lại người review trên thẻ gửi mã bền tới `POST /goals/{id}/reviewer/enable`; `team_reviewer_enable` kiểm trong một giao dịch rằng đội còn hiệu lực, vẫn ghim đúng mã đó và mã còn `active` rồi mới bật; thẻ cũ nhận 409 kèm trạng thái mới (review mã vòng 1, R2). Nút bật ở trang trợ lý vẫn đi `/resonance/agents/toggle`.

**Làn M của A3.** Tắt trên mục tiêu có đội, kiểm ở kho: `begin_experiment` trả None, bài học `trial_pending` thành `skipped/team_goal`; `_settle` không đề xuất phép thử khi bế tắc.

**Tách đội.** `team_detach` (chỉ chủ dự án, nút Bỏ yêu cầu review): `goal_team` thành `detached`, `team_calls` giữ làm hồ sơ, gỡ chặn thuộc đội, bỏ lý do review đang chờ, thức một lần; từ đó mục tiêu chốt theo luật A4/A2.

## Hành vi đổi so với 0.108.0

- Agent có người review: mục tiêu mới có 8 lượt (4/4) thay vì 6, và chỉ chốt sau review `pass`.
- Mục tiêu có đội không chốt trên file bị sửa ngoài Javis dù bản sửa đạt kiểm (phương án A); muốn giữ thì Bỏ yêu cầu review.
- `heartbeat.v3` (test A3 khoá phiên bản chính sách được cập nhật theo).
- Mọi mục tiêu (có đội hay không): lượt hỏng ở pha chuẩn bị, trước mốc gọi engine, được hoàn thay vì kết sổ `interrupted` có tính; ba fixture A2, A3, MVP mô phỏng "chết giữa lời gọi engine" giờ ghi mốc `mark_engine` như host thật.
- Không đổi gì cho agent không có người review.

## Hạ phiên bản

Tắt Javis, chạy `python tools/resonance_restore_pre_a5.py --yes` (giữ bản kho hiện tại `post-0.109.0-<thời điểm>`, rồi ghi snapshot `.pre-0.109.0`), chạy 0.108.0. Hạ KHÔNG khôi phục là không hỗ trợ: mã 0.108.0 bỏ qua bảng A5 nên chốt đạt mục tiêu có đội mà không có review (test `test_resonance_a5_rollback.py` ghi nhận đúng điều này).
