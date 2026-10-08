# Javis Resonance MVP Implementation Plan

**Kế hoạch triển khai hiện hành.** Đọc cùng [danh mục chốt](../README-RESONANCE.md) và [bản review mới nhất](../specs/2026-10-06-resonance-revised-package-review.md). Phụ lục code của Claude là mẫu chưa nghiệm thu, được lưu trong gói lịch sử; không phải lộ trình triển khai song song.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans when the user requests implementation. Steps use checkbox (- [ ]) syntax. Đây là kế hoạch ưu tiên sau phản biện vòng 2; không khởi chạy agent hoặc công việc nền chỉ vì tài liệu tồn tại.

**Goal:** Một nhu cầu cần theo đuổi được agent tự chuyển thành mục tiêu, thực hiện, kiểm chứng và cải thiện phương pháp trong hạn mức, với công điều phối tối thiểu từ người dùng.

**Architecture:** Một lớp mỏng nối hội thoại/engine hiện có với SQLite và EvidenceStore hiện có. Ba module lõi mới: resonance.py chứa kiểu dữ liệu, phân luồng, hình thành mục tiêu, hai evaluator và vòng thực hiện nhỏ; resonance_store.py giữ revision/events/actions/outbox; resonance_api.py nối API/UI và scheduler đang có. Các vai trò là hàm trong cùng lớp nhỏ, chưa tách thành hàng loạt service.

**Tech Stack:** Python, FastAPI, SQLite, engine adapter hiện có, dashboard JavaScript và i18n vi/en. Test bằng tests/run.py. Không cần nhóm agent, message broker, container, dịch vụ mới hoặc tài khoản model mới.

**Spec:** [Thiết kế tổng thể](../specs/2026-10-06-javis-resonance-design.md), ưu tiên mục 2, 4.0, 4.6, 4.7, 6, 8, 10 và 12. Các plan 01/02/03 là tài liệu mở rộng, không phải ba luồng triển khai đồng thời.

## Global Constraints

- Giữ ba bất biến: quyền không tự mở rộng; kết quả có bằng chứng; người dùng can thiệp được và lịch sử có hiệu lực.
- Bắt đầu một agent, một goal mỗi lần chạy. Không goal tree, team, tự sinh agent hoặc tự sửa code. Số luồng sau này là cấu hình, không phải luật nền.
- Câu hỏi, tư vấn và việc hoàn thành ngay không tạo goal bền hoặc Kanban; phản hồi nối vào goal đang mở khi phù hợp. Không thêm một lượt gọi model để phân loại mọi tin nhắn.
- SMART là kiểm tra nội bộ của agent; không có biểu mẫu SMART hoặc bước bắt người dùng duyệt goal. Phản hồi nhanh là tùy chọn, không chặn bắt đầu.
- Artifact contract và human confirmation là hai evaluator đầu; chưa có model rubric tự chấm thắng. Artifact đạt không tự chứng minh đúng nhu cầu.
- Dùng engine/hạn mức đã chọn, ghi usage có thật; không coi gói thuê bao là vô hạn hoặc tự chuyển qua API trả phí.
- Feature mặc định off, bật một lần theo brain trong phạm vi thử; task/loop legacy không gắn goal giữ hành vi cũ. Không bắt cấu hình lại theo từng goal.
- Dữ liệu ở JAVIS_STATE_DIR; payload qua EvidenceStore đã kiểm retention/quota. Quyền hiện hành và scope phải được kiểm trước effect; log bắt buộc lỗi thì không gửi effect mới.
- Không em dash; UTF-8 và LF; chuỗi UI có vi/en. TestClient dùng http://127.0.0.1:8080. Tuân thủ docs/quy-uoc-dev.md khi bắt đầu triển khai code.
- Trước M1, kiểm main mới nhất từ remote, ghi commit nền và làm trên nhánh riêng. Khảo sát 5b4a9be1 là checkout cũ; main được kiểm ngày 06/10/2026 là 7d264236 (0.83.2) và đã có _reply_policy_sandbox_engine/_reply_policy_ask. Dò lại chữ ký và đường gọi trên commit nền thực tế, không dùng số dòng cũ làm hợp đồng.
- Người triển khai tự kiểm thử trước khi giao review. Review độc lập sau M1, theo từng PR trong M2-M4, rồi review tổng thể sau M5; sửa lỗi ảnh hưởng đến bước phụ thuộc trước khi xây tiếp. Người viết và người review phải đối chiếu cùng commit/PR.

## Review Focus

1. Chat thường hoặc kế hoạch do agent đề xuất tự biến thành việc nền: M2.
2. Người dùng xác nhận cách hiểu nhưng hệ thống báo đầu ra đã đạt; thẻ cũ xác nhận revision mới: M4.
3. Runtime có file nhưng chưa có đường thực thi thật phù hợp, hoặc native tool vượt phạm vi: M1, M3.
4. Restart, callback lặp, revision đổi hoặc quota hết tạo effect/model call lặp: M3.
5. Candidate thay mục tiêu hoặc tiêu chí để thắng: M5.

## Dữ liệu tối thiểu và giao diện chung

GoalRecord giữ id/brain/owner do host tạo, nguồn yêu cầu gốc, revision, cách hiểu/giả định, tiêu chí, ràng buộc/quyền, hạn mức còn lại, lịch và trạng thái. Đây là dữ liệu nội bộ; UI chỉ hiện cách hiểu, tiến triển và việc tiếp theo. Bản đầu không cần mọi trường của hợp đồng mở rộng.

Event gồm id, goal_id, revision, kind, source, payload_ref và thời điểm. Evidence gắn nguồn và phiên bản tài nguyên. Action gồm id, goal/revision/run, ý định, trạng thái, nguồn lực và receipt; trạng thái uncertain khác failed. Unique key và expected_revision/state_version bảo vệ thao tác nhận lại. Không dùng JSONL xoay làm nguồn chuẩn.

Các kiểu nằm trong resonance.py: RouteDecision (answer_now/task_now/continue_goal/create_goal), GoalRecord, Assessment (met/not_met/unknown), ActionReceipt và GoalDeps. Mở rộng sau bằng schema migration; không triển khai song song GoalRecord và bộ GoalContract của plan 01 cho cùng mục tiêu.

GoalDeps cung cấp engine đã cấu hình, quyền hiện hành, giới hạn gọi, EvidenceStore, clock, kênh báo và thao tác thực thi có receipt. Model chỉ đề xuất; host xác nhận context và thay đổi state. Dữ liệu tool/file không trở thành lệnh của người dùng.

## Task M1 Xác minh đường chạy nhỏ trước khi xây tiếp

**Files:** Create tests/python/test_resonance_mvp_integration.py. Inspect server/main.py, server/aux_engine.py, server/agent_runtime.py, server/evidence_store.py, server/self_improve.py và server/mcp_hub.py. Ghi bằng chứng triển khai vào docs/dev/resonance-mvp-verification.md.

- [ ] Kiểm main mới nhất và commit nền, dò lại điểm tích hợp và chữ ký hàm từ mã thật. Ghi SHA cùng môi trường vào báo cáo kiểm chứng; không chuyển nguyên giả định từ checkout cũ sang nhánh triển khai.
- [ ] Viết harness nhận một đầu vào mô phỏng, chạy một lần qua engine được chọn, lấy đầu ra và một receipt host quan sát được. Fake engine kiểm luồng; pilot thật kiểm khả năng tích hợp, báo cáo hai kết quả riêng.
- [ ] Kiểm các điểm nối hiện có _workflow_agent_helpers/_run_workflow_step trong main.py và đường aux_swap/engine adapter. Không mặc định AgentRunner canary là đường live; không bật canary toàn cục để vượt test.
- [ ] Chạy python tests/run.py resonance_mvp_integration -v. Với pilot thật, dùng dữ liệu mô phỏng và hạn mức đã cấp, ghi host/engine, invocation, đầu ra, thời gian và quyền quan sát được. Nếu engine không có đường đáp ứng phạm vi, ghi blocked cụ thể trước khi xây các lớp sau; không tự đổi provider.
- [ ] Chốt GoalDeps.run_once(goal: GoalRecord, prompt: str, action_id: str) -> ActionReceipt bằng adapter tới đường hiện có đã qua kiểm. Không có một agent runtime mới; MVP có thể cho model sinh nội dung và host ghi đầu ra vào vùng đã cấp thay vì cấp shell hoặc plugin tùy ý.

Đầu ra: biết chính xác đường nào chạy được trong môi trường mục tiêu và giới hạn của nó. Harness xanh với fake engine không thay bằng chứng pilot thật.

## Task M2 Phân luồng và tự hình thành mục tiêu

**Files:** Create server/resonance.py, server/resonance_store.py, tests/python/test_resonance_mvp_core.py. Modify server/main.py tại điểm điều phối hội thoại đã kiểm ở M1.

**Interfaces:** route_request(message_ref: str, turn_context: dict) -> RouteDecision; form_goal(message_ref: str, context: dict, deps: GoalDeps) -> GoalRecord; GoalStore.create/revise/get/append_event với principal, idempotency key và expected_revision. Hàm dùng engine là async; route_request chỉ tiêu thụ kết quả định tuyến và ngữ cảnh đã có.

- [ ] Viết test_chat_does_not_create_goal, test_inline_job_stays_inline, test_followup_reuses_goal, test_persistent_request_creates_once và test_proposed_plan_does_not_schedule. Không dùng duy nhất từ khóa “làm cho xong” để tạo việc nền.
- [ ] Viết test_ambiguous_goal_smart, test_user_unsure_discovers và test_no_invented_target_or_deadline. SMART điền bằng chứng nhận biết đạt và mốc xem lại hợp lý; không bịa chỉ tiêu. Ý định gốc và giả định có nguồn riêng.
- [ ] Chạy python tests/run.py resonance_mvp_core -v, xác nhận đỏ rồi implement. SQLite dùng transaction, version và outbox; sửa cách hiểu giữ quyền/ngân sách/guard/pause và kết quả cũ. Không tạo service hay bảng phục vụ nhóm ở MVP.
- [ ] Chạy lại test, kiểm cross-brain và hai lần gửi cùng message không tạo goal trùng; review và commit.

## Task M3 Thực thi, bằng chứng và lịch nhỏ

**Files:** Modify server/resonance.py, server/resonance_store.py, server/main.py và điểm nối scheduler hiện có. Create tests/python/test_resonance_mvp_run.py.

**Interfaces:** advance(goal_id: str, event: dict, deps: GoalDeps) -> Assessment; evaluate_artifact(goal: GoalRecord, evidence_refs: tuple[str,...], deps: GoalDeps) -> Assessment; next_wake(goal: GoalRecord, event: dict, now: float) -> dict. Model gọi qua GoalDeps.run_once của M1, không có client/provider riêng.

- [ ] Viết test_done_is_not_success, test_missing_evidence_unknown, test_restart_does_not_repeat_effect, test_old_revision_cannot_finish, test_pause_and_revoke và test_audit_failure_before_effect.
- [ ] Viết test_budget_reserved_before_call, test_limit_keeps_checkpoint và test_no_paid_provider_fallback: đếm mọi lần form/run/verify/experiment; khi token hoặc quota thuê bao không đo được vẫn giữ giới hạn lượt và thời gian có thật. Thiếu dữ liệu không ghi chi phí bằng 0.
- [ ] Viết test_idle_does_not_call_model, test_guard_wakes_without_worker và test_no_source_uses_bounded_review. Chỉ dẫn về lần xem lại sửa lịch, reaction không sửa tần suất. Guard đang cần đọc chỉ hoạt động khi có adapter và quyền phù hợp; chưa hỗ trợ nguồn nào phải nêu rõ.
- [ ] Chạy python tests/run.py resonance_mvp_run -v, xác nhận đỏ rồi implement một vòng có thể tiếp tục sau restart: kiểm quyền/giữ nguồn lực/lưu intent, thực hiện, lưu receipt, kiểm artifact, báo và chờ. Đường action có khóa/lease và idempotency; effect uncertain phải đối soát.
- [ ] Kết nối một loại wakeup vào scheduler hiện có, giữ riêng lịch quan sát cần thiết với lịch gọi worker trong cùng hàng đợi. Tận dụng outbox thay vì tạo scheduler thứ hai. Chạy lại test và pilot một goal có sự kiện tiếp tục, review và commit.

## Task M4 Thẻ mục tiêu và phản hồi có nghĩa rõ

**Files:** Create server/resonance_api.py, tests/python/test_resonance_mvp_feedback.py, tests/js/test_resonance_mvp_ui.js. Modify dashboard/app.js, dashboard/chat-acts.js, dashboard/console.js, dashboard/i18n/vi.json, dashboard/i18n/en.json, server/main.py và server/sessions.py khi cần liên kết tin bền.

**Interfaces:** POST /goal-requests nhận message_ref; GET /goals/{id}; POST /goals/{id}/feedback nhận expected_revision, kind, artifact_ref/criterion_id nếu xác nhận đầu ra, idempotency key; POST /goals/{id}/commands nhận pause/resume/cancel và revision. Host lấy principal từ auth. Kind: goal_fit_confirmed/goal_fit_rejected/outcome_accepted/outcome_rejected; mỗi kind validate payload riêng.

- [ ] Viết test_goal_fit_not_outcome, test_feedback_old_revision, test_feedback_cross_brain và test_silence_is_unknown. Bấm Đúng ý xác nhận cách hiểu; Đạt yêu cầu xác nhận đúng tiêu chí sản phẩm có revision. Không tự bỏ guard hoặc tạo grant.
- [ ] Viết test_reload_keeps_goal_action_links và test_report_replay_same_mid. Tin lưu trước phát, report key có idempotency tại kho tin; crash giữa hai kho có reconciliation. Không đổi chữ ký push_to_chat mà bỏ kiểm caller cũ.
- [ ] Chạy python tests/run.py resonance_mvp_feedback -v và python tests/run.py --js resonance_mvp_ui -v, xác nhận đỏ rồi implement thẻ Em đang hướng tới và timeline action/bằng chứng ngắn. Phản hồi bằng lời vẫn được; không cần thanh sáu emoji toàn ứng dụng.
- [ ] Implement human_confirmation trong resonance.py: xác nhận đã xác thực chỉ đóng criterion được chỉ định và hợp đồng cho phép, không phủ nhận lỗi khách quan. Thiếu xác nhận cần thiết giữ unknown/waiting, không đòi người dùng bấm lại theo nhịp.
- [ ] Chạy lại test và kiểm giao diện thật sau F5, reconnect, sửa ý, chuột/bàn phím. Undo tổng quát không nằm trong MVP; chỉ hiện “xem thay đổi” khi chưa có adapter undo đã kiểm. Review và commit.

## Task M5 Một phép thử cải thiện nhỏ và mốc phát hành

**Files:** Create tests/python/test_resonance_mvp_trial.py, tests/fixtures/resonance/mvp_cases.json. Modify server/resonance.py, server/resonance_store.py và tài liệu kiểm chứng của M1. Chưa tạo ExperimentService hoặc kho biến thể tổng quát.

**Interfaces:** compare_methods(goal_id: str, baseline_ref: str, candidate_ref: str, cases: dict, deps: GoalDeps) -> dict; verdict inconclusive/rejected/eligible, kèm revision, evidence_refs, usage và phạm vi áp dụng. Hai method ref là cấu hình khai báo, không phải code sinh tùy ý.

- [ ] Viết test_same_goal_and_rubric, test_holdout_not_visible, test_unknown_not_win và test_failed_candidate_not_applied. Host giữ tiêu chí và trường hợp kiểm riêng; tạo lại snapshot mô phỏng cho từng lượt, không lặp tác động ngoài để so sánh.
- [ ] Viết test_one_change_within_budget: baseline/candidate cùng đầu vào và nguồn lực, dùng artifact checker xác định; kết quả thua cũng được lưu. Không tự tạo experiment nếu đã hết phần nguồn lực cho khám phá hoặc chỉ vì đã đến timer.
- [ ] Chạy python tests/run.py resonance_mvp_trial -v, xác nhận đỏ rồi implement phép so sánh hẹp. Chỉ đổi method ref trong quyền đã có sau kiểm chứng, giữ ref cũ để quay lại; nếu goal đã đổi revision thì đánh giá lại tính áp dụng.
- [ ] Chạy python tests/run.py resonance_mvp -v rồi checks bắt buộc của repo khi thực sự triển khai. Pilot với engine được chọn trên dữ liệu mô phỏng; không ghi success chỉ vì fake engine xanh. Ghi rõ một tình huống đạt, một tình huống unknown và một tình huống candidate thua.
- [ ] Phát hành thử trong phạm vi đã cấp sau khi có bằng chứng end-to-end và khả năng tắt feature. Nhóm, tự sửa code, supervisor, metric chuỗi thời gian và undo tổng quát chỉ mở khi có nhu cầu thực và kế hoạch riêng được chọn.

## Điều kiện hoàn thành MVP

- [ ] Một yêu cầu cần theo đuổi đã đi hết vòng trên host thật: tự hình thành mục tiêu, hành động có receipt, kiểm chứng, tiếp tục sau gián đoạn và trả kết quả đúng phiên.
- [ ] Chat thường không tạo việc nền; không cần người dùng điền SMART hoặc xác nhận mọi mục tiêu.
- [ ] Goal-fit và outcome được tách; biết nói chưa đủ bằng chứng; xác nhận con người không bị bỏ phí hoặc bị dùng sai phạm vi.
- [ ] Một thay đổi phương pháp được thử trên cùng thước đo và chỉ áp dụng khi đủ căn cứ trong quyền; usage/hạn mức được ghi và có thể dừng.
- [ ] Báo cáo chỉ khẳng định phạm vi đã chạy. Không gọi MVP là đã chứng minh an toàn cho mọi native tool hoặc tự cập nhật live.
