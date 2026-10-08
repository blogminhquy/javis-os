# Javis Resonance Foundation Implementation Plan

**Trạng thái sau phản biện vòng 2:** tham chiếu cho kiến trúc mở rộng. Bắt đầu bằng [MVP một agent](2026-10-06-resonance-00-mvp.md); không triển khai toàn bộ kế hoạch này trước demo. Những đường đã làm trong MVP được dùng lại, không tạo bản thứ hai. Giao diện/kiểu dữ liệu dưới đây được đối chiếu và migrate khi mở rộng.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking. Chỉ chọn phương thức thực thi sau khi người dùng quyết định triển khai; tài liệu này không khởi chạy công việc nền.

**Goal:** Từ nhu cầu bằng ngôn ngữ tự nhiên, agent tự hình thành và điều chỉnh mục tiêu; lưu hợp đồng có phiên bản, bằng chứng có nguồn và đánh giá độc lập với lĩnh vực. Người dùng không phải chọn mục tiêu hoặc tự điền tiêu chí.

**Architecture:** Goal framer dùng engine adapter hiện có để diễn giải nhu cầu, đưa ra câu hỏi hoặc bước khám phá và tạo hợp đồng. SQLite giữ đầu vào gốc, phiên bản cách hiểu, trạng thái mục tiêu và outbox; EvidenceStore hiện có giữ payload mã hóa. Hợp đồng, quyền, bằng chứng và assessment được ghim phiên bản, kiểm tra theo brain và principal.

**Tech Stack:** Python hiện có của repo, FastAPI, SQLite, standard-library unittest, dashboard JavaScript và i18n vi/en. Không thêm framework agent hoặc dịch vụ cơ sở dữ liệu.

**Spec:** [Javis Resonance thiết kế và lộ trình thực thi mục tiêu](../specs/2026-10-06-javis-resonance-design.md), đặc biệt mục 2 đến 7, 12 đến 17.

## Global Constraints

- Lõi không chứa điều kiện theo ngành hoặc nhà cung cấp model.
- Mục tiêu, quyền và tiêu chí có phiên bản; agent không tự tăng quyền.
- Người dùng giao nhu cầu, agent chịu trách nhiệm đặt mục tiêu. Bản diễn giải không ghi đè chỉ dẫn gốc; quyền và ràng buộc rõ không đổi theo suy đoán của model.
- Hỏi để giảm bất định đáng kể; trả lời chưa biết dẫn tới khám phá trong quyền, không bắt người dùng chọn mục tiêu hoặc duyệt mọi revision.
- Task/workflow hoàn thành không tự xác nhận mục tiêu đạt.
- Reaction không quyết định hiệu suất hoặc quyền hạn.
- Feature mới mặc định off; loop/cron legacy giữ hành vi khi chưa gắn mục tiêu.
- Thời gian lưu bằng UTC epoch seconds; giao diện dùng múi giờ đã cấu hình.
- State ở JAVIS_STATE_DIR; dữ liệu riêng không đưa vào Git hoặc prompt toàn cục.
- Không dùng em dash (U+2014); định danh mới bằng tiếng Anh, chuỗi UI có vi/en. File văn bản ghi UTF-8 và LF. TestClient dùng base_url http://127.0.0.1:8080 để đi qua web_security đúng như các test hiện có.
- Log giao tiếp tùy chọn có thể lỗi mà chat tiếp tục; lỗi sổ bắt buộc không được giả thành đã lưu. Không dùng actor slug hoặc thời gian gần nhau thay định danh brain/run/action.
- Dùng tests/run.py để chạy test; test mới dùng unittest và gọi unittest.main khi chạy trực tiếp, theo đường dẫn import tests/python/_paths.py.
- Tuân theo docs/quy-uoc-dev.md khi triển khai code; không đặt phiên bản phát hành cho riêng bản kế hoạch.

## Review Focus

1. Đánh giá dùng bằng chứng thuộc brain hoặc revision khác phải bị chặn, không trả metadata nhạy cảm: A2, A3, A4.
2. Cập nhật hợp đồng giữa lúc đánh giá không được dùng kết quả cũ để đóng phiên bản mới: A1, A4.
3. Sự kiện lặp/đến muộn/đính chính không được tạo hai kết quả độc lập: A2, A3.
4. Payload bằng chứng hết hạn hoặc bị người dùng xóa phải thành unavailable/unknown: A2, A3.
5. Tiêu chí định tính không có phần trăm giả; lỗi evaluator không bị tính thành thất bại của mục tiêu: A3, A5.
6. Agent đặt sai mục tiêu, hỏi lặp hoặc hạ tiêu chí để tự nhận thành công phải được phát hiện trong fixture: A1, A4, A5.
7. Chỉ số chứa id/ngày tháng/lỗi, mẫu đến muộn hoặc nhịp lấy mẫu thay đổi không được làm sai kết luận: A3. Một chỉ số ổn định không bị đánh đồng với dữ liệu kém tin cậy.

## Hợp đồng kiểu dữ liệu dùng chung

Tạo dataclass frozen trong server/resonance_contracts.py; serialize qua hàm tường minh, không serialize quyền từ object do model tự gửi.

| Kiểu | Trường bắt buộc và nghĩa |
|---|---|
| Principal | id: str; brain_ids: frozenset[str]; capabilities: frozenset[str]. Host tạo từ auth hiện có |
| CriterionSpec | id, description, evaluator_ref, evaluator_revision: str; parameters, evidence_selector, acceptance: dict |
| IntentRecord | id, brain_id, source_message_ref, author_id: str; revision: int; explicit_constraint_refs: tuple[str,...]; received_at: float; supersedes_id: str hoặc None. Host giữ bản ghi đầu vào có nguồn; nguồn gốc user phải được xác thực |
| GoalFraming | stage: discovery/delivery; assumptions, unknowns, alternatives: tuple[dict,...]; evidence_refs, constraint_refs, unresolved_conflicts: tuple[str,...]; rationale, reconsider_when: str. Các dict có schema riêng; phân loại từ model vẫn là diễn giải có thể sai |
| Clarification | id, intent_ref, question, impact, fallback: str; required_for: tuple[str,...]; status: open/answered/user_unsure/superseded; answer_ref: str hoặc None. Phân biệt làm rõ sở thích với yêu cầu cấp quyền |
| FramingResult | intent_ref: str; framing: GoalFraming; proposed_contract: dict hoặc None; clarification: Clarification hoặc None; next_step: proceed/discover/clarify/blocked; reason: str |
| GoalContract | id, brain_id, owner_id, intent_ref, intent: str; revision: int; framing: GoalFraming; mode: achieve/maintain; criteria: tuple[CriterionSpec,...]; criteria_mode: all/any; guards: tuple[CriterionSpec,...]; authority_ref: str; resources, timing, communication: dict; parent_goal_id: str hoặc None; dependencies: tuple[str,...] |
| GoalSnapshot | contract: GoalContract; status: draft/active/succeeded/failed/cancelled; run_state: ready/running/waiting/blocked/paused/dormant; state_version: int; reason: str |
| EvidenceEnvelope | id, brain_id, goal_id, source, source_event_id, resource_ref, content_hash, evidence_ref, trust_class: str; contract_revision: int; observed_at, received_at: float; action_id, resource_version, supersedes_id: str hoặc None; freshness: dict |
| CriterionResult | criterion_id: str; verdict: met/not_met/unknown; evidence_ids: tuple[str,...]; confidence: low/medium/high; rationale: str; error_code: str hoặc None |
| Assessment | id, goal_id, brain_id, evaluator_revision: str; contract_revision: int; criterion_results: tuple[CriterionResult,...]; verdict: met/not_met/unknown; guard_status: triggered/clear/unknown; confidence: low/medium/high; rationale: str; evaluated_at: float; next_observation_at: float hoặc None |
| GoalEvent | id, brain_id, goal_id, source, source_event_id, kind: str; contract_revision: int; occurred_at, received_at: float; payload: dict |
| ResourceEnvelope | limits: dict[str,int hoặc float]; units: dict[str,str]; accounting_policy: dict. Mọi số hữu hạn, không âm |
| WakePlan | reason, policy_revision: str; earliest_at, observation_due_at, expires_at: float hoặc None; wake_on: tuple[str,...] |
| Decision | id, goal_id: str; contract_revision: int; kind: act/delegate/experiment/clarify/reframe/wait/escalate/finish; rationale: str; payload: dict; resources: ResourceEnvelope; wake: WakePlan |
| GoalRunContext | goal_id, brain_id, run_id, actor_id, authority_ref: str; contract_revision, grant_generation: int; action_id, lease_id: str; turn_id: str hoặc None. Host xác nhận toàn bộ; invocation riêng nằm trong metadata evidence/receipt |
| MessageLink | brain_id, session_id, run_id, report_key: str; message_id: int; action_ids: tuple[str,...]. Liên kết tác động đúng lượt, không suy từ thời gian |

Các module sau import đúng kiểu này. Trường mở rộng do adapter sở hữu nằm trong parameters/metadata có schema riêng, không thêm tên nghiệp vụ vào GoalContract.

## Task A1 Hợp đồng có phiên bản và luật chuyển trạng thái

**Files:** Create server/resonance_contracts.py, tests/python/test_resonance_contracts.py.

**Interfaces:**

- validate_contract(raw: dict) -> GoalContract.
- validate_child(parent: GoalContract, child: GoalContract) -> None.
- transition(snapshot: GoalSnapshot, event: GoalEvent, assessment: Assessment | None) -> GoalSnapshot.
- Errors: ContractValidationError, RevisionConflict, AuthorityError; đặt trong resonance_contracts.py và tái sử dụng.

- [ ] Viết test đạt/chưa đạt/unknown, finite numeric values, all/any, parent cùng brain, dependency cycle, achieve/maintain, pause giữ nguyên trước sự kiện thông thường.
- [ ] Viết regression test_task_done_is_not_goal_success: sự kiện task.completed không có Assessment met giữ status active; test_maintain_met_stays_active giữ status active khi condition met.
- [ ] Viết test discovery đạt chỉ yêu cầu xem lại đích hoặc hoàn thành mục tiêu con khám phá, không tự đóng nhu cầu gốc; unresolved_conflicts ngăn tuyên bố giải quyết nhu cầu. Agent đổi framing không sửa IntentRecord, không xóa lịch sử kết quả hoặc pause.
- [ ] Chạy python tests/run.py resonance_contracts -v; xác nhận test mới thất bại vì chưa có implementation.
- [ ] Implement validate và transition thuần, không I/O. Chỉ transition được phép đóng goal khi assessment cùng goal/brain/revision, guards clear, không còn unresolved_conflicts và không dùng kết quả discovery để đóng nhu cầu gốc; finish của planner chưa đủ. Phân biệt nghiên cứu là sản phẩm user yêu cầu với khảo sát trung gian để tìm đích.
- [ ] Chạy lại test. PASS khi mọi trường hợp được chấp nhận/từ chối đúng và không phụ thuộc model/mạng.
- [ ] Review diff rồi commit riêng task sau khi test xanh.

## Task A2 Kho mục tiêu và liên kết bằng chứng

**Files:** Create server/resonance_store.py, server/resonance_evidence.py, tests/python/test_resonance_store.py, tests/python/test_resonance_evidence.py. Modify server/evidence_store.py, server/context_runtime.py để hỗ trợ giữ bằng chứng đang được tham chiếu.

**Interfaces:**

- GoalStore(path: Path); create(contract: GoalContract, principal: Principal, key: str) -> GoalSnapshot.
- GoalStore.get(goal_id: str, principal: Principal) -> GoalSnapshot.
- GoalStore.record_intent(record: IntentRecord, principal: Principal, key: str) -> IntentRecord; get_intent(intent_id: str, principal: Principal) -> IntentRecord. Revision từ người dùng nối nguồn xác thực, không nhận tác giả user do model tự khai.
- GoalStore.revise(goal_id: str, expected_revision: int, contract: GoalContract, principal: Principal) -> GoalSnapshot.
- GoalStore.append_event(event: GoalEvent, principal: Principal) -> bool, false nếu source_event_id đã xử lý.
- GoalStore.record_assessment(assessment: Assessment, expected_state_version: int) -> GoalSnapshot.
- GoalStore.pending_outbox(limit: int) -> list[dict]; acknowledge_outbox(event_id: str) -> None.
- EvidenceBridge.capture(context: GoalRunContext, source: str, source_event_id: str, value: object, metadata: dict) -> EvidenceEnvelope.
- EvidenceBridge.resolve(envelope: EvidenceEnvelope, principal: Principal, now: float) -> object.
- EvidenceStore.pin(evidence_id: str, owner_ref: str, until: float) -> None; unpin(evidence_id: str, owner_ref: str) -> None. Kiểm quyền ở bridge; kiểm tồn tại và storage quota ở store.

- [ ] Viết test hai connection SQLite cùng revise chỉ một bên thắng; create và append_event lặp không tạo dòng mới; crash trước acknowledge làm event được nhận lại mà không nhân effect.
- [ ] Viết test cross-brain bị từ chối; supersedes không xóa bản cũ; bằng chứng pin không bị cleanup; hết pin về retention cũ; xóa theo người dùng làm resolve báo unavailable.
- [ ] Viết test IntentRecord giữ nguồn, các goal revision tham chiếu đúng phiên bản; sửa cách hiểu không sửa đầu vào gốc. Câu hỏi và câu trả lời có id liên kết, nhận lại không nhân câu hỏi; payload đầu vào theo cùng redaction/retention và quyền đọc như evidence.
- [ ] Viết test lỗi SQLite/disk full không trả create/revise/append_event thành công; hai brain có slug giống nhau không chia sẻ bản ghi. Lịch sử còn được tham chiếu không mất do xoay log; snapshot phục hồi nếu có dùng EvidenceStore và quota hiện có.
- [ ] Chạy python tests/run.py resonance_store resonance_evidence -v; xác nhận đỏ theo hành vi thiếu.
- [ ] Implement SQLite WAL, transaction BEGIN IMMEDIATE, unique key theo brain/source/source_event_id, optimistic concurrency và outbox trong cùng transaction. Lưu payload qua EvidenceStore.put hiện có; tạo/resume trace qua runtime thật, không giả TurnTrace để bỏ kiểm tra.
- [ ] Bổ sung pin registry trong context_runtime và điều chỉnh snapshot retention để cleanup tôn trọng pin. Pin không kéo dài vô hạn mặc định; thời hạn đến từ hợp đồng/experiment. Crash giữa lưu payload và link được dọn bằng đối soát orphan, không coi payload rời là bằng chứng đã gắn mục tiêu.
- [ ] Chạy lại test mới và python tests/run.py adaptive_runtime_hardening context_runtime_phase01 -v. PASS khi không mất tính mã hóa/redaction/retention cũ.
- [ ] Review và commit task.

## Task A3 Giao diện đánh giá và hai evaluator đầu tiên

**Files:** Create server/resonance_evaluators.py, server/resonance_eval_artifact.py, server/resonance_eval_predicate.py, tests/python/test_resonance_evaluators.py.

**Interfaces:**

- Evaluator Protocol: async evaluate(contract: GoalContract, evidence: tuple[EvidenceEnvelope,...], now: float) -> Assessment.
- EvaluatorRegistry.register(evaluator_id: str, revision: str, evaluator: Evaluator) -> None; resolve(evaluator_id: str, revision: str) -> Evaluator.
- evaluate_goal(contract: GoalContract, evidence: tuple[EvidenceEnvelope,...], registry: EvaluatorRegistry, now: float) -> Assessment.
- artifact_contract/v1 parameters: required_resources và required_sections; dữ liệu file chỉ đọc từ evidence đã capture, không đọc đường dẫn tùy ý do model nhập.
- state_predicate/v1 parameters: path theo danh sách key/index; op trong exists/eq/ne/lt/lte/gt/gte; expected kiểu JSON. Không eval Python/JavaScript/string expression.

- [ ] Viết test cùng goal service đánh giá artifact và state; không có logic theo ngành trong evaluator registry.
- [ ] Viết test stale evidence, sai evaluator revision, missing source, NaN, đọc vượt brain, prompt injection trong artifact, evaluator timeout. Các ca thiếu dữ liệu trả unknown kèm lý do; timeout có error_code.
- [ ] Viết test correction đảo assessment mới nhưng giữ assessment cũ; nguồn trùng không tăng confidence; tất cả tiêu chí met nhưng guard triggered không đóng goal.
- [ ] Viết test dữ liệu có trường id/ngày tháng đứng trước value vẫn chọn đúng path; kết quả ERROR:/isError không được nhập thành số hoặc bằng chứng thành công. Adapter thu dữ liệu phải giữ trạng thái lỗi, không chỉ bắt exception.
- [ ] Chạy python tests/run.py resonance_evaluators -v; xác nhận đỏ.
- [ ] Implement registry và aggregation theo mục 6 spec. Giới hạn thời gian/bằng chứng do evaluation policy truyền vào; lỗi adapter được cô lập, không làm dừng toàn scheduler.
- [ ] Chạy lại test. PASS khi không cần LLM và một loại evaluator mới có thể đăng ký bằng giao diện mà không sửa goal state machine.
- [ ] Review và commit task.

Khi hợp đồng cần so sánh chuỗi thời gian, bổ sung adapter metric_series/v1 trong server/resonance_eval_metric.py với tests/python/test_resonance_metric.py, dùng cùng Evaluator Protocol. Không đưa công thức phần trăm vào goal service. Schema parameters gồm selector, unit, value_kind (gauge/period_total/counter), window/timezone, aggregation (last/sum/delta/time_weighted_mean), baseline, direction và missing_data_policy; validate tổ hợp phù hợp. Sample metadata có source_sample_id, observed_at, received_at, unit và quality. Baseline và giới hạn chất lượng được ghim theo hợp đồng; không mặc định giảm 30% cho mọi lĩnh vực.

- [ ] Viết test_metric_source_selection, test_metric_error_is_unknown, test_metric_constant_is_readable, test_metric_duplicate_samples và test_metric_sampling_cadence_does_not_reweight: dữ liệu nguồn giữ nguyên thì đổi lịch đọc không đổi phép tổng hợp; dữ liệu ổn định vẫn có đủ chất lượng.
- [ ] Viết test_metric_late_sample, test_metric_zero_baseline, test_metric_nonfinite, test_metric_unit_change và test_metric_window_policy: không đủ điều kiện thì unknown; cùng kỳ lịch khác rolling khi policy quy định khác; timestamp sau thời điểm bắt đầu đọc vẫn được xét ở lần đánh giá sau khi nhận.
- [ ] Chạy python tests/run.py resonance_metric -v để xác nhận đỏ; implement adapter theo mục 6.5 spec, không regex số đầu tiên; chạy lại cùng resonance_evaluators và commit khi xanh. Có thể làm sau mốc demo artifact đầu tiên; chưa dùng metric_series trong hợp đồng trước khi adapter được kiểm chứng.

## Task A4 Tự hình thành mục tiêu, goal service và API có kiểm quyền

**Files:** Create server/resonance_intent.py, server/resonance_service.py, server/resonance_api.py, tests/python/test_resonance_intent.py, tests/python/test_resonance_api.py. Modify server/main.py chỉ để dependency injection/router/lifecycle. Dùng engine adapter hiện có qua dependency injection, không tạo client model riêng.

**Interfaces:**

- GoalFramer.form(intent: IntentRecord, context_refs: tuple[str,...], current: GoalSnapshot | None, evidence: tuple[EvidenceEnvelope,...], policy: dict) -> FramingResult; async, đầu vào ngữ cảnh đã kiểm quyền, policy do host cấp và có phiên bản.
- GoalFramer.check_revision(current: GoalSnapshot, proposed: FramingResult, principal: Principal) -> dict trả permitted, conflicts, reasons. Kiểm quyền và trường bảo vệ bằng code; nhận định phù hợp ngữ nghĩa lưu dưới dạng có căn cứ, không giả chứng minh bằng schema validation.
- GoalService(store: GoalStore, evidence: EvidenceBridge, evaluators: EvaluatorRegistry, framer: GoalFramer).
- GoalService.accept_request(source_message_ref: str, principal: Principal, key: str) -> FramingResult; xác thực đầu vào đã lưu và tự tạo/kích hoạt hợp đồng đủ điều kiện trong phạm vi giai đoạn A.
- GoalService.clarify(clarification_id: str, answer_ref: str, expected_revision: int, principal: Principal) -> FramingResult.
- GoalService.reframe(goal_id: str, reason: str, evidence_ids: tuple[str,...], expected_revision: int, principal: Principal) -> GoalSnapshot; revision mới giữ tài nguyên đã tiêu, guard và trạng thái can thiệp.
- GoalService.create(raw: dict, principal: Principal, key: str) -> GoalSnapshot.
- GoalService.evaluate(goal_id: str, principal: Principal, now: float) -> Assessment.
- GoalService.command(goal_id: str, command: str, expected_revision: int, principal: Principal) -> GoalSnapshot; command trong activate/pause/resume/cancel.
- GoalDeps gồm service và get_principal(request) -> Principal lấy từ auth của Javis; register(app, deps: GoalDeps) -> None.
- API hội thoại: POST /goal-requests; POST /goal-clarifications/{id}/answers; POST /goals/{id}/reframe. Input chính là tham chiếu tin nhắn người dùng, không bắt client điền GoalContract. Nhu cầu thiếu thông tin vẫn được lưu và trả next_step/clarification, không lỗi 422 chỉ vì diễn đạt mơ hồ.
- API quản lý/chi tiết: POST /goals; GET /goals; GET /goals/{id}; POST /goals/{id}/revisions; POST /goals/{id}/commands; POST /goals/{id}/evaluate; GET /goals/{id}/events; GET /goals/{id}/assessments. Create cấu trúc dùng cho adapter/test hoặc người dùng nâng cao, không phải bước bắt buộc của giao diện.
- Mutation nhận idempotency key; revise/commands nhận expected_revision; 409 nếu stale, 422 nếu contract không hợp lệ, 404 cho id ngoài phạm vi, 403 cho thiếu quyền trong brain hợp lệ.

Giai đoạn A chỉ hỗ trợ hợp đồng observation-only với authority_ref do host tạo từ quyền đọc hiện có của principal. Active cho phép thu/đánh giá bằng chứng trong phạm vi này, chưa cấp quyền autonomous execution. Grant thực thi và ngân sách đầy đủ được bổ sung ở B1; không tạo dependency vòng từ A vào B.

- [ ] Viết test chủ hợp lệ tạo/đọc/sửa, người khác không đọc chéo brain, planner payload không tự cấp Principal hoặc authority_ref có thêm quyền.
- [ ] Viết test hợp đồng bị sửa trong lúc evaluator đang chạy: assessment cũ được lưu lịch sử nhưng không cập nhật active revision.
- [ ] Viết test engine giả nhận yêu cầu mơ hồ và ngữ cảnh: tự chọn mục tiêu cùng tiêu chí, không đòi người dùng chọn; thông tin thiếu không đáng kể dùng giả định có ghi nguồn. Khi có câu hỏi đáng hỏi, chỉ phần phụ thuộc chờ; câu trả lời chưa biết chuyển discover, không phát lại câu hỏi cũ.
- [ ] Viết test không có căn cứ hoặc nguồn truy cập: giữ unknown, chọn bước khám phá được phép hoặc trả blocked có lý do. Ràng buộc mâu thuẫn được nêu rõ; không tự bỏ chỉ dẫn trực tiếp hoặc lấy nội dung tài liệu làm chỉ dẫn user.
- [ ] Viết test reframe có bằng chứng mới giữ intent_ref và constraint_refs hợp lệ, supersede revision cũ, không tự đổi quyền hoặc reset ngân sách. Hạ chỉ tiêu đơn thuần để báo thắng không qua check_revision; thay mục tiêu hợp lý cũng không được ghi là cải thiện phương pháp khi thiếu đối chứng.
- [ ] Viết test resume không tự vượt guard yêu cầu quyền người dùng và activate bị chặn khi thiếu evaluator/source/grant cần thiết. Khi feature off, không tạo run nền.
- [ ] Chạy python tests/run.py resonance_intent resonance_api -v; xác nhận đỏ.
- [ ] Implement framer và service theo mục 4 spec: giữ nguồn gốc đầu vào, giả thuyết, câu hỏi đã hỏi, căn cứ sửa và giới hạn khám phá theo policy. Tái sử dụng engine adapter hiện có; output model qua schema validation và host authorization. Không cho model gọi endpoint nội bộ ghi assessment như một evaluator tin cậy. Chưa gắn scheduler thực thi ở giai đoạn A.
- [ ] Giới hạn xác minh: unit test engine giả chỉ kiểm luồng và ràng buộc. Đánh giá chất lượng suy ra mục tiêu bằng engine thật, rubric/fixture độc lập tại C6; không gọi unit test xanh là bằng chứng agent đã hiểu đúng mọi nhu cầu.
- [ ] Chạy lại nhóm test resonance; PASS nếu API hoạt động bằng fixture và không gọi engine thật.
- [ ] Review và commit task.

## Task A5 Giao diện nhận nhu cầu và hiển thị cách hiểu hiện tại

**Files:** Create dashboard/resonance.js, tests/js/test_resonance_ui.js. Modify dashboard/workspace.js, dashboard/console.js, dashboard/index.html, dashboard/i18n/vi.json, dashboard/i18n/en.json. Create docs/22-muc-tieu-va-resonance.md, docs/en/22-goals-and-resonance.md.

**Interfaces:** window.JavisResonance.render(container, {ownerType, ownerId, brain}); destroy(container). Module gọi API A4; không đọc SQLite/file trực tiếp.

- [ ] Viết test render các trạng thái chưa có mục tiêu, active, waiting, unknown, paused, succeeded; không tạo phần trăm từ số tiêu chí một cách tùy tiện.
- [ ] Viết test đổi brain xóa dữ liệu màn trước, hủy request cũ; tên/ý định/bằng chứng HTML được escape; request revise 409 không ghi đè thay đổi mới.
- [ ] Viết test giao nhu cầu bằng lời tạo mục tiêu tự động, không mở màn chọn mục tiêu/điền KPI/xác nhận hợp đồng; câu trả lời chưa biết được nhận và hiển thị bước khám phá. Sửa cách hiểu bằng hội thoại cập nhật revision, không xóa lời gốc.
- [ ] Chạy python tests/run.py --js resonance_ui -v; xác nhận đỏ.
- [ ] Implement điểm vào bằng hội thoại và thẻ Em đang hướng tới: cách hiểu, giả định quan trọng, việc đang làm, bằng chứng và lịch sử. Cho sửa cách hiểu bằng lời; chi tiết hợp đồng chỉ mở khi cần. Gắn vào Cộng sự/Việc; chưa biến field group phân loại hiện tại thành runtime group. Giai đoạn A ghi rõ mới quan sát/chuẩn bị, chưa tự thực thi các tác động ở giai đoạn B.
- [ ] Chạy lại test JS và mở dashboard với fixture để kiểm tra màn hình rộng/hẹp, thao tác bàn phím, câu chữ vi/en, trạng thái lỗi API. Không ghi rằng UI đã kiểm chứng nếu chỉ test string.
- [ ] Cập nhật hướng dẫn và commit task khi đạt.

## Nghiệm thu giai đoạn A

- [ ] Cùng API nhận nhu cầu tự nhiên, suy ra và đánh giá một tài liệu theo cấu trúc và một trạng thái dữ liệu mô phỏng; không bắt người dùng cung cấp mục tiêu chuẩn hóa.
- [ ] Yêu cầu mơ hồ và câu trả lời chưa biết tạo bước khám phá hợp lệ; thiếu quyền vẫn chặn phần cần quyền. Lịch sử tách được đầu vào gốc, giả định, revision và kết quả thực tế.
- [ ] Bằng chứng có thể mở lại; unknown, lỗi và stale revision hiển thị đúng.
- [ ] Không có reaction, số tin hoặc số lần gọi model trong logic thành công.
- [ ] Tất cả test resonance và hồi quy liên quan xanh; ghi kết quả thực tế vào PR.
- [ ] Tiếp tục B1; sau đó chạy C1 trước khi mở rộng nhóm.
