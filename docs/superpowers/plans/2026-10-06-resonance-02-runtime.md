# Javis Resonance Runtime Implementation Plan

**Trạng thái sau phản biện vòng 2:** tham chiếu cho kiến trúc mở rộng. Bắt đầu bằng [MVP một agent](2026-10-06-resonance-00-mvp.md); các phần context, bằng chứng và quyền cần cho MVP được làm ở phạm vi hẹp. Nhóm, transport đa worker và undo tổng quát không phải điều kiện của mốc đầu. Không dựng hai scheduler hoặc hai kho goal khi mở rộng.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking. Không triển khai chỉ vì tài liệu này tồn tại.

**Goal:** Cho agent và nhóm tự hình thành mục tiêu từ nhu cầu, thực thi, xem lại cách hiểu theo bằng chứng, điều chỉnh beat, cộng tác và tiếp tục sau gián đoạn trong đúng quyền và nguồn lực.

**Architecture:** Goal service dùng executor/Kanban/workflow hiện có, bổ sung authorization theo goal và scheduler dựa trên sự kiện. Một mục tiêu có một chủ sở hữu lịch. Group runtime giữ leader epoch và phân công bằng hợp đồng con.

**Tech Stack:** Python/FastAPI/SQLite, engine adapters và workflow graph của Javis, JavaScript dashboard. Dùng clock và executor giả trong test.

**Spec:** [Thiết kế tổng thể](../specs/2026-10-06-javis-resonance-design.md), mục 7 đến 10, 12 đến 17. Phụ thuộc [Foundation](2026-10-06-resonance-01-foundation.md).

## Global Constraints

- Kế thừa tất cả Global Constraints và kiểu dữ liệu của plan Foundation.
- Beat là lịch quyết định tiếp theo, không phải điểm thưởng hiệu suất.
- Tự phân công không tăng quyền/ngân sách; thu hồi quyền có hiệu lực trước tác động tiếp theo.
- Workflow legacy không có GoalRunContext giữ quy trình duyệt hiện tại.
- Goal gắn loop không đồng thời được loop timer và goal scheduler khởi chạy.
- Worker không tự bỏ user pause hoặc guard yêu cầu người dùng.
- Dữ liệu MCP/file không cấp quyền hoặc sửa hợp đồng.
- Agent tự đặt và điều chỉnh phần mục tiêu suy ra trong ràng buộc gốc; không cần thêm cổng người dùng chọn/duyệt mục tiêu. Làm rõ ý định và cấp quyền là hai việc riêng.
- Đổi mục tiêu không reset chi phí, guard, pause hoặc thu hồi; không tự ghi các revision trước thành thành công.
- B1 gồm B1 đến B3 dưới đây; sau đó làm C1/C2 trong plan Evolution rồi mới B4/B5.

## Review Focus

1. Restart sau khi tool đã tác động nhưng trước khi receipt được ghi không được tự chạy lại mù: B2.
2. Grant bị thu hồi trong lúc task nằm hàng đợi phải bị chặn ngay trước effect: B1, B2.
3. Parent/children cạnh tranh ngân sách không được vượt tổng: B1, B4.
4. Event storm hoặc hai scheduler không tạo hai run; nhiệm vụ chờ không làm tắc cron cũ: B3.
5. Leader chết rồi trở lại không thể chốt cùng leader mới; user pause áp dụng cả cây đã chọn: B4, B5.
6. Người dùng chưa biết hoặc không trả lời câu hỏi tùy chọn không tạo vòng hỏi vô hạn; reframe không làm hành động cũ tiếp tục theo mục tiêu hết hiệu lực: B2, B3, B4.
7. Context xuyên HTTP, cache route và các brain trùng slug không được gán sai tác nhân; lỗi tool dạng text không được thành receipt succeeded: B2.
8. Guard phải được quan sát khi worker giãn nhịp; refresh chat phải giữ đúng liên kết tác động: B3, B5. Hoàn tác file đã sửa tiếp phải trả conflict: B6.

## Task B1 Sự ủy quyền và giữ chỗ tài nguyên

**Files:** Create server/resonance_authority.py, tests/python/test_resonance_authority.py. Modify server/resonance_store.py, server/resonance_contracts.py.

**Interfaces:**

- GoalGrant(id, brain_id, principal_id, parent_grant_id, capabilities, resource_scope, envelope, generation, expires_at); kiểu frozen trong resonance_contracts.py.
- Authorization(allowed: bool, reason: str, grant_id: str, generation: int, reservation_id: str | None).
- AuthorityService.authorize(context: GoalRunContext, decision: Decision, principal: Principal, now: float) -> Authorization.
- AuthorityService.delegate(parent_id: str, requested: GoalGrant, principal: Principal) -> GoalGrant.
- AuthorityService.reserve(grant_id: str, action_id: str, estimate: ResourceEnvelope) -> str.
- AuthorityService.settle(reservation_id: str, actual: ResourceEnvelope) -> None.
- AuthorityService.revoke(grant_id: str, principal: Principal) -> int trả generation mới.
- AuthorityService.check_effect(context: GoalRunContext, resource: dict, effect: str, now: float) -> Authorization.

- [ ] Viết test con xin thêm capability/phạm vi bị từ chối; hết hạn và sai brain bị từ chối; grant full legacy không tự có self_modify/deploy.
- [ ] Viết test hai transaction reserve đồng thời: tổng spent + reserved không vượt hạn mức gốc; settle lặp không tính hai lần; tạo con không nhân ngân sách.
- [ ] Viết test hình thành mục tiêu không cần capability mới; các hành động khảo sát/thử nhỏ vẫn qua grant tương ứng. Reframe cùng goal hoặc tạo con không reset spent/reserved, không tự mở thêm tài nguyên hoặc bỏ ràng buộc user.
- [ ] Viết test giá tiền unknown không ghi là 0, vẫn chặn bằng trần token/lượt đã cấp; actual vượt estimate làm chặn phần cấp tiếp và ghi overrun thật, không sửa usage để vừa trần.
- [ ] Chạy python tests/run.py resonance_authority -v; xác nhận đỏ.
- [ ] Implement capability subset và budget transaction. Grant từ host, không từ prompt. Check generation ở mọi effect; policy và ngân sách là cấu hình có phiên bản.
- [ ] Chạy lại test; PASS khi kiểm tra concurrency thật bằng hai connection SQLite.
- [ ] Review và commit.

## Task B2 Thực thi một agent và bằng chứng tác động

**Files:** Create server/resonance_executor.py, server/resonance_run_context.py, tests/python/test_resonance_executor.py, tests/python/test_resonance_run_context.py. Modify server/agent_runtime.py, server/workflow_runtime.py, server/main.py, server/mcp_hub.py, server/mcp_client.py, server/tasks.py, server/task_store.py, server/resonance_store.py, server/resonance_contracts.py.

**Interfaces:**

- ActionReceipt(action_id, status, started_at, finished_at, evidence_ids, external_ref, error_code, invocation_ids); status succeeded/failed/uncertain/cancelled; định nghĩa trong resonance_contracts.py. Invocation id gắn đúng mỗi lần gọi và lần retry, không suy từ tên tool.
- RunContextRegistry.issue(context: GoalRunContext, ttl: float) -> str; resolve(credential: str, now: float) -> GoalRunContext; revoke(run_id: str) -> None. Credential ngắn hạn gắn run/grant, cấp bởi host và kiểm tra lại generation trước effect; không log credential hoặc đưa vào nội dung chat.
- Header X-Javis-Run mang credential tới Hub; X-Javis-Actor nếu có chỉ để chẩn đoán, không cấp quyền hoặc làm nguồn chuẩn quy công. Engine in-process dùng context đã resolve và reset ContextVar bằng token trong finally. Request legacy không có goal context giữ hành vi cũ và không được tự gán vào goal khác.
- GoalExecutor.execute(context: GoalRunContext, decision: Decision) -> ActionReceipt.
- GoalExecutor.reconcile(context: GoalRunContext, action_id: str) -> ActionReceipt.
- Thêm goal_context: GoalRunContext | None = None và effect_authorizer callback optional vào cuối chữ ký AgentRunner.run, WorkflowCanary.run/resume; giữ tương thích positional cũ.
- EffectAuthorizer: async (context: GoalRunContext, node: WorkflowNode) -> Authorization.
- TaskStore.enqueue bổ sung metadata: dict | None = None ở cuối chữ ký, dùng metadata_json hiện có; goal metadata gồm id/revision/action_id, không chứa grant tự khai.

- [ ] Viết test Decision act đi qua grant và tạo receipt; Decision finish chỉ gọi evaluate_goal; run COMPLETED nhưng assessment unknown giữ goal active.
- [ ] Viết test workflow write legacy vẫn WAITING_USER; goal write có grant hợp lệ đi tiếp; explicit wait_user luôn giữ hành vi chờ; grant bị thu hồi sau enqueue chặn effect.
- [ ] Viết test backend CLI có native shell ngoài cổng quyền nhưng chưa có isolation không được nhận action cần bảo vệ phạm vi. Chỉ đổi backend khi có backend khác đáp ứng cùng grant; nếu không thì blocked với lý do, không giảm bảo vệ âm thầm.
- [ ] Viết test crash sau external commit với receipt chưa ghi: có idempotency key thì reconcile/retry cùng key; không có bằng chứng xác nhận thì uncertain, không tạo effect lần hai.
- [ ] Viết test reframe giữa enqueue và effect: revision cũ không phát thêm effect; effect đã gửi được đối soát và lưu dưới revision gốc. Kế hoạch mới chỉ chạy từ checkpoint hợp lệ, không nhân hành động hoặc tự tính kết quả cũ cho tiêu chí mới.
- [ ] Viết test_context_cross_process_and_brain: hai run cùng actor và hai brain trùng slug gửi song song không trộn context; request lỗi/cancel reset ContextVar; giả X-Javis-Actor không nhận quyền hay công của người khác; credential hết hạn bị từ chối. Cache discovery được dùng lại không giữ run context cũ hoặc bọc ledger lặp.
- [ ] Viết test_tool_error_content_not_success và test_multiplexed_effect_at_call: ERROR:/isError giữ lỗi, effect xét arguments thực tế dù metadata lúc list là read. Các read tạo bằng chứng đánh giá có receipt/provenance; không log toàn bộ payload nhạy cảm.
- [ ] Viết test_call_route_receives_mapping bằng fake route: gọi mcp_client.call_route(route, fn, arguments), không truyền route[fn]; fake tool phải được gọi đúng một lần. Khi adapter thay đổi cách giữ kết quả cấu trúc, kiểm hồi quy client cũ nhận text.
- [ ] Viết test_required_audit_failure: không lưu intent/reservation thì không effect; mất receipt sau effect dẫn tới uncertain và đối soát; lỗi telemetry phụ không làm chat thất bại. Kiểm crash/timeout thực tế, không chỉ chmod vì phép thử quyền có thể không gây lỗi trên Windows.
- [ ] Chạy python tests/run.py resonance_executor resonance_run_context -v; xác nhận đỏ.
- [ ] Implement adapter đến engine/workflow hiện có, không tạo model loop thứ hai. Ghi intent và reservation trước effect; event/receipt sau effect. Task outbox enqueue dùng idempotency key ổn định.
- [ ] Clarify và reframe đi qua GoalService A4; thay revision trong transaction cùng hủy lịch/action chưa gửi và outbox. Giải phóng đúng reservation chưa dùng; giữ phần đang có tác động chưa xác định. Bằng chứng cũ chỉ tái sử dụng nếu bộ đánh giá mới kiểm tính phù hợp và độ mới, không tái sử dụng verdict cũ.
- [ ] Không bỏ kiểm tra lease/capability revision hiện có. Executor read-only hiện tại chỉ dùng cho read; write đi qua effect_authorizer và đường write được ủy quyền. Không set approved_nodes hàng loạt chỉ vì mode full.
- [ ] B1 trước C4 chỉ cho phép action qua tool do host cưỡng chế phạm vi. Plugin Python tùy ý cùng process host không phải ranh giới quyền; các action cần shell/candidate code chờ backend isolation đã kiểm tra.
- [ ] Snapshot sau khi native tool đã ghi chỉ chứng minh trạng thái sau nếu quan sát đủ, không tạo khả năng undo hoặc quy công chắc chắn. Không tuyên bố wrapper Hub thấy mọi hành động CLI; backend không kiểm soát được ghi phải giữ giới hạn ở spec mục 5.
- [ ] Chạy test mới và python tests/run.py agent_replan_phase11 workflow_graph_phase10 workflow_runs kanban_snapshot -v; xác nhận các đường legacy không đổi.
- [ ] Review và commit.

## Task B3 Beat theo sự kiện và tiếp tục sau gián đoạn

**Files:** Create server/resonance_scheduler.py, tests/python/test_resonance_scheduler.py. Modify server/self_improve.py, server/main.py, server/resonance_store.py, server/resonance_service.py.

**Interfaces:**

- BeatScheduler.on_event(event: GoalEvent) -> None.
- BeatScheduler.schedule(goal_id: str, revision: int, plan: WakePlan) -> str.
- BeatScheduler.schedule_observation(goal_id: str, revision: int, due_at: float, source_ref: str) -> str; loại wakeup observation dùng cùng store/lease, chỉ thu dữ liệu trong grant, không mặc nhiên gọi worker/model.
- BeatScheduler.tick(now: float) -> list[str] trả run ids đã được dispatch.
- BeatScheduler.cancel_tree(goal_id: str, principal: Principal, reason: str) -> None.
- decide_next_wake(snapshot: GoalSnapshot, assessment: Assessment | None, decision: Decision | None, now: float) -> WakePlan.

- [ ] Viết test fake clock: không có event/deadline đến hạn thì không gọi model; waiting thức đúng sự kiện; dormant nhận event phù hợp; paused không tự thức.
- [ ] Viết test hai scheduler claim cùng wakeup chỉ dispatch một lần; lặp event chỉ một logical action; revision cũ bị bỏ; event từ chính báo cáo không tạo vòng tự kích hoạt.
- [ ] Viết test loop gắn goal bỏ lịch legacy cho đúng loop, loop khác và reminder vẫn chạy; một task dài không block tick.
- [ ] Viết test user_unsure chuyển sang bước discover còn trong quyền; câu hỏi tùy chọn đang mở không chặn bước độc lập. Không phản hồi không được coi là cấp quyền; câu hỏi thiếu dữ liệu thiết yếu chỉ chặn đúng phần phụ thuộc. Không hỏi lại cùng điều chưa biết nếu không có bằng chứng mới.
- [ ] Viết test đủ dữ liệu mới thì reframe một lần có lý do; timer hoặc thông báo do chính agent sinh không gây chuỗi đổi mục tiêu. Hết ngân sách khám phá hoặc không còn bước hữu ích thì trả kết quả hiện có và waiting/dormant có điều kiện thức rõ, không gọi model liên tục.
- [ ] Viết test_guard_without_agent_action_stops và test_guard_observed_while_worker_dormant: điều kiện dừng đúng thì chặn scope đã khai dù chưa xác định nguyên nhân; cadence quan sát không phụ thuộc điểm, số lần hành động hoặc khoảng ngủ của worker.
- [ ] Viết test_guard_unknown_policy, test_guard_latched_resume và test_observation_revoked: thiếu nguồn không thành clear; mẫu tốt không tự bỏ chốt cần owner; rút quyền quan sát ngừng đọc và báo mất giám sát. Dedupe cảnh báo và chính sách chống dao động không tự hạ điều kiện dừng đã được đặt.
- [ ] Chạy python tests/run.py resonance_scheduler -v; xác nhận đỏ.
- [ ] Implement leases, coalescing và outbox. earliest_at không được vượt deadline hợp đồng khi deadline cần kiểm tra; timestamp không hợp lệ trả lỗi có lý do. Cấu hình giới hạn kỹ thuật có phiên bản, không gắn với điểm reaction.
- [ ] Xử lý blocked theo reason: source_reconnected/budget_replenished chỉ tự mở khi hợp đồng cho phép; user_pause/guard_requires_owner không tự mở. Thông báo guard và completion dedupe theo goal/revision/event.
- [ ] Lưu clarification id, required_for, fallback, câu trả lời và các giả định đã thử. Policy có phiên bản quyết định thời gian dành cho câu hỏi/khám phá theo bối cảnh và phần nguồn lực còn lại, không đặt số lần hỏi thành luật cố định toàn hệ thống. Chờ trả lời tùy chọn vẫn cho chạy việc độc lập; hết thời gian không tự đổi quyền.
- [ ] Tách observation wakeup khỏi worker wakeup trong cùng hàng đợi; giữ nguồn lực giám sát theo grant. Sau await thu mẫu mới lấy thời điểm đánh giá, không loại mẫu mới vì dùng timestamp lấy trước khi gọi tool. Lịch nguồn có sẵn giữ nguyên ngữ nghĩa dữ liệu dù worker đổi nhịp.
- [ ] Chạy test mới và python tests/run.py loop_goal_default loop_ambient kanban_het_luot -v.
- [ ] Review và commit. Đến đây chuyển sang Task C1 và C2 để kiểm chứng một vòng tự cải thiện nhỏ.

## Task B4 Nhóm và mục tiêu con

**Files:** Create server/resonance_groups.py, tests/python/test_resonance_groups.py. Modify server/resonance_store.py, server/resonance_contracts.py, server/resonance_executor.py.

**Interfaces:**

- GroupState(id, brain_id, goal_id, leader_id, epoch, members, status); định nghĩa trong resonance_contracts.py.
- GroupService.create(goal_id: str, leader_id: str, members: tuple[str,...], principal: Principal) -> GroupState.
- GroupService.delegate(group_id: str, child: GoalContract, principal: Principal) -> GoalSnapshot.
- GroupService.contribute(group_id: str, actor_id: str, kind: str, evidence_ids: tuple[str,...], content: str) -> str.
- GroupService.commit_decision(group_id: str, epoch: int, decision: Decision, principal: Principal) -> None.
- GroupService.replace_leader(group_id: str, expected_epoch: int, new_leader_id: str, principal: Principal) -> GroupState.
- kind đóng góp: proposal/objection/evidence/decision/ack; kind chỉ mô tả hội thoại, không là reward.

- [ ] Viết test goal con cùng brain, quyền subset, ngân sách từ cha, không cycle; tất cả con done nhưng parent criterion chưa đạt thì parent vẫn active.
- [ ] Viết test leader cũ commit sau failover bị từ chối; đóng góp trùng không nhân bằng chứng; leader không sửa phép chấm của experiment đang chạy hoặc tự tăng grant.
- [ ] Viết test thành viên im không bị trừ năng lực; event chỉ gọi subscription liên quan; cả nhóm có thể dừng chờ người dùng đúng phạm vi.
- [ ] Viết test leader tự đặt mục tiêu con từ nhu cầu cha; phản biện có bằng chứng dẫn tới reframe qua GoalService. Cha đổi revision làm con liên quan kiểm tra lại trước effect; con không đổi mục tiêu để che việc không đóng góp cho cha. Nhóm chỉ gửi một câu hỏi tổng hợp và tiếp tục phần độc lập khi user chưa biết.
- [ ] Chạy python tests/run.py resonance_groups -v; xác nhận đỏ.
- [ ] Implement membership bền với leader epoch. Không dùng field group phân loại trong workspace.js làm group runtime id. Không ép mọi thành viên chạy mỗi vòng.
- [ ] Kết nối delegation qua GoalService và AuthorityService; nhóm thảo luận dùng run budget chung, được tự chọn số vòng trong phần đã cấp.
- [ ] Ghim parent revision và IntentRecord liên quan trong metadata phân công; lưu đóng góp cho việc hình thành mục tiêu cùng bằng chứng. Leader epoch bảo vệ cả quyết định reframe, không chỉ quyết định thực thi. Mục tiêu con và khám phá cùng dùng tài nguyên gốc.
- [ ] Chạy lại test và hồi quy nhom_agent_workflow, agent_replan_phase11; review và commit.

## Task B5 Giao diện hoạt động và điều khiển nhóm

**Files:** Modify dashboard/resonance.js, dashboard/workspace.js, dashboard/console.js, dashboard/app.js, dashboard/chat-acts.js, server/main.py, server/sessions.py, server/resonance_store.py, server/resonance_api.py, dashboard/i18n/vi.json, dashboard/i18n/en.json, docs/22-muc-tieu-va-resonance.md, docs/en/22-goals-and-resonance.md. Create tests/js/test_resonance_runtime_ui.js, tests/python/test_resonance_runtime_api.py, tests/python/test_resonance_message_links.py.

**Interfaces:** API bổ sung POST /goals/{id}/run-now, GET /goals/{id}/actions, GET /goals/{id}/wake-plan, POST /goals/{id}/stop-tree, POST /goal-groups, GET /goal-groups/{id}, POST /goal-groups/{id}/contributions. Principal và expected_revision/epoch lấy cùng quy tắc A4.

- GoalStore.link_message(link: MessageLink, principal: Principal) -> None; message_links(brain_id: str, session_id: str, message_ids: tuple[int,...], principal: Principal) -> list[MessageLink]. Idempotency theo report_key/run, kiểm session và message thuộc brain cho phép.
- Khung response/push và API đọc lịch sử trả mid cùng liên kết run/action; dashboard giữ qua live stream, dữ liệu khôi phục và F5. Không đổi push_to_chat bool thành int mà không kiểm mọi caller; thêm đường gửi báo cáo có receipt trong adapter hoặc kiểu kết quả tương thích tường minh.
- Báo cáo có report_key bền, lưu tin trước phát và ghi liên kết có đối soát. Kho sessions và resonance là hai kho riêng: cần idempotency key trong kho tin và reconciliation sau crash, không giả là transaction chung chỉ bằng hai lệnh ghi nối tiếp. Publish thất bại được phát lại cùng mid, không tạo tin mới.

- [ ] Viết test trạng thái running/waiting/blocked/paused/dormant và lý do; không hiện queued thành running; stop-tree hiển thị đúng phạm vi.
- [ ] Viết test nguồn lực chưa đo được hiển thị chưa biết, không 0; nhóm phân loại hiện tại không tự có quyền tự chủ.
- [ ] Viết test sửa cách hiểu qua hội thoại, trả lời chưa biết và thông báo đổi hướng có lý do. UI không chuyển sang bắt chọn mục tiêu khi planner gặp bất định; không báo đã giải quyết nhu cầu chỉ vì một bước khám phá xong.
- [ ] Viết test_reload_restores_action_links, test_report_retry_same_mid, test_message_link_cross_brain và test_two_runs_same_actor: live/F5/reconnect giữ đúng tin và tác động; không gắn theo actor trong 10 phút gần nhất. Mất liên kết do crash được đối soát; không nhận session_id từ client là bằng chứng sở hữu message.
- [ ] Chạy python tests/run.py resonance_runtime_api -v và python tests/run.py --js resonance_runtime_ui -v; xác nhận đỏ.
- [ ] Implement timeline quyết định/bằng chứng và thay đổi cách hiểu, hội thoại nhóm gắn mục tiêu, nút dừng/tiếp tục, lý do lần thức kế tiếp. Thẻ Em đang hướng tới phân biệt giả định với chỉ dẫn người dùng, cho sửa bằng lời. Báo sự kiện quan trọng về đúng owner_chat bằng đường report hiện có; không yêu cầu duyệt từng revision.
- [ ] Chạy test, kiểm tra dashboard bằng fixture thật ở màn hình rộng/hẹp, kiểm tra refresh/reconnect không mất trạng thái hay gửi trùng.
- [ ] Cập nhật hướng dẫn, review và commit.

## Task B6 Hoàn tác file có điều kiện, tùy chọn sau mốc demo

Task này chỉ cần khi phát hành nút hoàn tác; không chặn vòng mục tiêu đầu tiên. Hoàn tác không tạo điểm phạt hiệu suất mặc định.

**Files:** Create server/resonance_undo.py, tests/python/test_resonance_undo.py. Modify server/resonance_executor.py, server/resonance_store.py, server/resonance_api.py, dashboard/resonance.js, dashboard/chat-acts.js, dashboard/i18n/vi.json, dashboard/i18n/en.json.

**Interfaces:**

- FileUndoAdapter.capture_before(context: GoalRunContext, resource_ref: str) -> str trả evidence ref được mã hóa; record_after(action_id: str, before_ref: str, after_version: str) -> None.
- FileUndoAdapter.preview(action_id: str, principal: Principal) -> dict trả available/conflict/expired/unsupported, reason và diff_ref trong phạm vi đọc được phép.
- FileUndoAdapter.undo(action_id: str, expected_after_version: str, principal: Principal, key: str) -> ActionReceipt; trả effect/action mới liên kết action gốc. API GET /actions/{id}/undo-preview và POST /actions/{id}/undo dùng kiểm quyền, expected version và idempotency.

- [ ] Viết test_undo_changed_file_conflicts, test_undo_created_then_edited_not_deleted, test_undo_cross_brain_denied và test_undo_symlink_escape: không mất thay đổi sau action, không ra khỏi scope.
- [ ] Viết test_undo_concurrent_requests_once, test_undo_crash_reconciles và test_undo_missing_backup: không bù hai lần, bản chụp hết hạn không được hiển thị có thể hoàn tác.
- [ ] Chạy python tests/run.py resonance_undo -v; xác nhận đỏ.
- [ ] Implement snapshot qua EvidenceStore, content/version preconditions, lock/CAS theo backend và receipt bền. Nếu không chứng minh chống thay đổi xen giữa kiểm tra/ghi với editor bên ngoài, tạo bản phục hồi riêng để so sánh, không ghi đè file gốc. Chỉ adapter đã có khả năng hoàn tác mới cung cấp nút; phân loại read/write/danger không đủ.
- [ ] Chạy lại test và kiểm giao diện sau F5, hai yêu cầu đồng thời, file do người dùng sửa tiếp. Khi đạt mới mở nút, cập nhật hướng dẫn và commit.

## Nghiệm thu giai đoạn B

- [ ] Một agent tự hoàn thành mục tiêu qua sự kiện thật, bằng chứng xác nhận độc lập với tin nhắn.
- [ ] Restart giữa các bước không lặp effect đã xác nhận; effect chưa rõ được đối soát.
- [ ] Nhóm phân công và chốt được, leader đổi không chạy hai luồng chốt.
- [ ] Người dùng vắng không làm hệ thống tự giảm năng lực; pause/thu hồi đúng hiệu lực.
- [ ] Agent/nhóm tự tìm mục tiêu từ đầu vào mơ hồ, tự điều chỉnh có căn cứ và chuyển revision không lặp effect. Người dùng chưa biết không gây hỏi lặp hoặc vượt quyền; mục tiêu khám phá không bị báo thành kết quả cuối.
- [ ] Không thay scheduler/permissions của các nhiệm vụ legacy chưa tham gia.
