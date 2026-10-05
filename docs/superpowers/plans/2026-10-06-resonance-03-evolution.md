# Javis Resonance Evolution Implementation Plan

**Trạng thái sau phản biện vòng 2:** tham chiếu cho kiến trúc mở rộng. Phép thử phương pháp nhỏ được làm sớm trong [MVP một agent](2026-10-06-resonance-00-mvp.md); chưa cần toàn bộ ExperimentService, kho biến thể hoặc supervisor. C3 đến C5 chỉ mở sau khi vòng nhỏ đã chạy và có bằng chứng cần mở rộng; không tự sửa code ở MVP.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking. Đây là kế hoạch, không phải chỉ dẫn tự bắt đầu cập nhật Javis đang chạy.

**Goal:** Cho agent cải thiện khả năng hiểu nhu cầu, hình thành mục tiêu và thực hiện công việc bằng thử nghiệm có bằng chứng; sau đó mở rộng tới sửa code Javis với khả năng khôi phục thực tế.

**Architecture:** Experiment service quản lý baseline/candidate, dữ liệu kiểm chứng và điều kiện áp dụng. Candidate chỉ có quyền của worker; supervisor độc lập giữ phép chấm, quyền áp dụng, bản phục hồi và nhật ký. Sửa phương pháp và sửa ứng dụng là hai đích áp dụng riêng.

**Tech Stack:** Python, SQLite, runner hiện có, Git checkout cho code candidate, supervisor host và container worker ở chế độ live self-update. V1 không hỗ trợ tự cập nhật live nếu môi trường chưa có ranh giới worker/supervisor đã kiểm tra.

**Spec:** [Thiết kế tổng thể](../specs/2026-10-06-javis-resonance-design.md), mục 10 đến 17. Phụ thuộc [Foundation](2026-10-06-resonance-01-foundation.md) và B1 đến B3 của [Runtime](2026-10-06-resonance-02-runtime.md).

## Global Constraints

- Kế thừa Global Constraints và kiểu dữ liệu của hai plan trước.
- Candidate không ghi vào quyền, evaluator được bảo vệ, receipt hoặc tập đáp án giữ riêng của phép thử hiện tại.
- Không cần người dùng duyệt lại thay đổi nếu grant đã cho phép áp dụng đúng phạm vi và phép kiểm chứng đạt.
- Thay tiêu chí đánh giá tạo revision riêng; không so điểm khác thước đo để tuyên bố cải thiện.
- Điều chỉnh mục tiêu suy ra là hoạt động bình thường; kết quả thực thi của mỗi revision giữ riêng. Goal framer được cải thiện bằng đối chứng trên cùng đầu vào/ràng buộc, không bằng tự chọn đích dễ hơn.
- Khám phá nằm trong tổng tài nguyên gốc; lưu biến thể theo hạn mức, không tạo kho vô hạn.
- Tự sửa code được opt-in riêng; không thay mặc định full của loop thành quyền self_modify/deploy.
- Không quảng bá khả năng bảo vệ live bằng một file cờ hoặc một process cùng tài khoản toàn quyền.
- Health check không thay kiểm tra hành vi; Git rollback không thay phục hồi dữ liệu và tác động ngoài.
- C1 và C2 thực hiện ngay sau B3; C3 sau B4/B5; C4/C5 chỉ mở live khi đủ ranh giới môi trường.

## Review Focus

1. Candidate sửa đề/đáp án hoặc tạo log test giả không được công nhận: C1, C4.
2. Baseline/candidate khác ngân sách, dữ liệu hoặc thước đo không được so như tương đương: C1.
3. Kết quả chưa đủ dữ liệu không được tự áp dụng; bản kém phải giữ baseline: C2.
4. Bài học mới sai hoặc rút lại không tiếp tục được chèn vào prompt: C3.
5. Crash lúc deploy, app healthy nhưng sai hành vi, migration không tương thích phải khôi phục hoặc giữ trạng thái chặn rõ ràng: C5.
6. Mục tiêu dễ đạt nhưng lệch nhu cầu không được chấm tốt; agent không học cách né câu hỏi cần thiết hoặc hỏi lặp để giảm trách nhiệm: C1, C3, C6.

## Task C1 Experiment và bộ thử nghiệm phương pháp

**Files:** Create server/resonance_experiments.py, server/resonance_trials.py, tests/python/test_resonance_experiments.py, tests/fixtures/resonance/README.md, tests/fixtures/resonance/document_cases.json, tests/fixtures/resonance/index_cases.json, tests/fixtures/resonance/intent_cases.json. Modify server/resonance_contracts.py, server/resonance_store.py.

**Interfaces:**

- ExperimentSpec(id, brain_id, goal_id, contract_revision, hypothesis, baseline_ref, candidate_ref, evaluator_ref, evaluator_revision, development_set_ref, holdout_set_ref, resource_envelope, acceptance, target, status); target method/app_code; status draft/running/inconclusive/rejected/eligible/applied/reverted. Định nghĩa tại resonance_contracts.py.
- TrialResult(id, experiment_id, variant_ref, case_id, receipt_ids, assessment_ids, resources, completed_at); mọi ref phải truy được.
- ExperimentService.create(spec: ExperimentSpec, principal: Principal) -> ExperimentSpec.
- TrialRunner.run(experiment: ExperimentSpec, variant_ref: str, case_id: str) -> TrialResult.
- ExperimentService.compare(experiment_id: str, principal: Principal) -> dict; verdict inconclusive/rejected/eligible, reasons và evidence_ids.

- [ ] Viết test hai biến thể trên cùng trường hợp có kết quả tốt/xấu/unknown; cùng evaluator revision và envelope; trường hợp thiếu receipt không được chấm passed.
- [ ] Viết test đổi tiêu chí giữa thử, lệch bộ dữ liệu, baseline budget khác không được kết luận thắng; chi phí không được đo phải giữ unknown.
- [ ] Viết test reframe hợp lệ trong lúc thử: giữ trial và verdict của revision cũ, phép thử không còn áp dụng trả inconclusive/goal_reframed. Không apply cho revision mới khi chưa so sánh lại cùng thước đo và kiểm tra tính áp dụng.
- [ ] Viết test case phát triển không trùng holdout; candidate không nhận đường dẫn/đáp án holdout; payload nói PASS nhưng checker thất bại vẫn rejected.
- [ ] Chạy python tests/run.py resonance_experiments -v; xác nhận đỏ.
- [ ] Implement thử trên bản sao tài nguyên mô phỏng, không chạy lại hành động không hoàn tác trên dịch vụ thật để lấy đối chứng. Ghim revision và seed/thứ tự nếu có yếu tố ngẫu nhiên; ghi mọi trial, kể cả thất bại.
- [ ] Ở C1/C2 trước khi có C4, variant chỉ là cấu hình phương pháp khai báo chạy qua host tools đã kiểm phạm vi; model không nhận đáp án/checker path. Chưa chạy Python/shell do candidate sinh cùng quyền host. Arbitrary code candidate cần backend C4.
- [ ] Với fixture đầu: baseline bỏ một mục bắt buộc trong tài liệu, candidate bổ sung; fixture khác baseline bỏ sót một thay đổi file trong chỉ mục. Checker artifact/state từ A3 xác nhận kết quả, không dùng lời tự chấm của worker.
- [ ] Thêm intent_cases: yêu cầu mơ hồ, thông tin có sẵn không cần hỏi, trả lời chưa biết, ràng buộc mâu thuẫn, mục tiêu khó và cơ hội hạ tiêu chí để thắng. Fixture ghi nhu cầu/ràng buộc và hành vi chấp nhận được, không ép một câu mục tiêu duy nhất. C1 kiểm cấu trúc, quyền và lịch sử bằng checker xác định; C6 bổ sung đánh giá ngữ nghĩa độc lập với model thực thi.
- [ ] Khi thử biến thể Goal framer, baseline/candidate nhận cùng đầu vào và ngân sách, tự tạo mục tiêu riêng; phép chấm ngoài giữ cố định theo nhu cầu/ràng buộc gốc. Báo riêng độ phù hợp mục tiêu và hiệu quả đầu ra, không so tỷ lệ đạt các tiêu chí do mỗi candidate tự chọn như cùng thước đo.
- [ ] Acceptance của fixture: candidate đạt toàn bộ ca giữ lại, không làm ca baseline đã đạt trở thành không đạt và không vượt envelope được cấp. Đây là điều kiện phép thử cụ thể, không phải luật mọi experiment tương lai.
- [ ] Chạy lại test; review và commit.

## Task C2 Áp dụng phương pháp và giữ biến thể

**Files:** Create server/resonance_variants.py, tests/python/test_resonance_variants.py. Modify server/resonance_store.py, server/resonance_experiments.py, server/resonance_executor.py, server/resonance_api.py, dashboard/resonance.js, dashboard/i18n/vi.json, dashboard/i18n/en.json.

**Interfaces:**

- VariantStore.register(brain_id: str, owner_id: str, parent_ref: str, artifact_ref: str, evidence_ids: tuple[str,...]) -> str.
- VariantStore.activate(owner_id: str, expected_active_ref: str, candidate_ref: str, experiment_id: str, principal: Principal) -> str.
- VariantStore.revert(owner_id: str, expected_active_ref: str, restore_ref: str, principal: Principal) -> str.
- API: GET /goals/{id}/experiments; POST /goals/{id}/experiments; POST /experiments/{id}/apply; POST /experiments/{id}/revert. Quyền apply lấy từ grant; ứng dụng tự gọi service sau khi đủ điều kiện nếu được ủy quyền.

- [ ] Viết test eligible + grant apply hợp lệ đổi active_ref; rejected/inconclusive hoặc hết hạn grant giữ bản cũ.
- [ ] Viết test hai experiment apply đồng thời chỉ một bên thắng CAS; run đang chạy giữ revision cũ; run tiếp theo dùng bản mới.
- [ ] Viết test goal đã reframe không tự apply một experiment thuộc revision cũ; kiểm tra phạm vi áp dụng, tiêu chí và bằng chứng trước khi tạo phép thử mới. Biến thể framer đã được xác nhận vẫn không có quyền viết lại chỉ dẫn gốc hoặc tăng grant.
- [ ] Viết test vượt quota lưu trữ dọn theo chính sách nhưng không xóa active, pinned hoặc restore_ref đang cần; bản khác biệt chưa thắng có thể giữ trong quota.
- [ ] Chạy python tests/run.py resonance_variants -v; xác nhận đỏ.
- [ ] Implement pointer phiên bản trong transaction, ghi event applied/reverted. V1 áp dụng phương pháp qua ref cấu hình, không ghi đè hàng loạt agent/skill trong brain.
- [ ] Hoàn thành demo A -> B1 -> C1: agent chạy mục tiêu, thử phương pháp cải tiến, checker xác nhận, tự áp dụng trong quyền, run tiếp theo dùng phương pháp mới và có thể quay lại.
- [ ] Chạy lại test, kiểm tra UI hiển thị bằng chứng thắng và giới hạn phép thử; review và commit. Sau mốc này tiếp tục nhóm ở B4/B5.

## Task C3 Bài học và đánh giá định tính có nguồn

**Files:** Create server/resonance_learning.py, server/resonance_eval_rubric.py, server/resonance_eval_human.py, tests/python/test_resonance_learning.py, tests/python/test_resonance_rubric.py. Modify server/main.py tại đường JAVIS_LESSON, server/resonance_evaluators.py, server/resonance_store.py.

**Interfaces:**

- LearningService.propose(context: GoalRunContext, text: str, evidence_ids: tuple[str,...], scope: dict) -> str.
- LearningService.validate(lesson_id: str, assessment_id: str, principal: Principal) -> None.
- LearningService.supersede(lesson_id: str, replacement_id: str | None, evidence_ids: tuple[str,...]) -> None.
- LearningService.active_lessons(brain_id: str, owner_id: str, scope: dict) -> list[dict].
- RubricEvaluator và HumanConfirmationEvaluator thực hiện Evaluator Protocol của A3. Prompt/rubric revision và danh tính nguồn xác nhận được ghi trong assessment.

- [ ] Viết test reaction không tạo lesson validated; nhận xét của worker chỉ là proposed; chỉ dẫn rõ của principal có quyền có thể xác nhận.
- [ ] Viết test người dùng sửa cách hiểu tạo IntentRecord mới, ghi rõ phạm vi nhu cầu này; không suy thành sở thích mọi lĩnh vực. Giả định về nhu cầu còn chưa chắc không được nâng thành lesson validated chỉ vì agent hoàn thành mục tiêu tự đặt; bài học bị bác bỏ phải rút khỏi framer lẫn planner.
- [ ] Viết test lesson chỉ áp đúng scope, bị supersede không còn đưa vào prompt, không sửa vùng memory người dùng viết tay, không rò bài học qua brain.
- [ ] Viết test rubric thiếu bằng chứng trả unknown; model confidence không được trình bày là xác suất; không có quyền xem dữ liệu thì evaluator không được đọc để chấm.
- [ ] Chạy python tests/run.py resonance_learning resonance_rubric -v; xác nhận đỏ.
- [ ] Implement provenance riêng cho lesson Resonance; bridge sang cơ chế bộ nhớ hiện có bằng id/hash để thu hồi bài học sinh tự động đúng dòng. Giữ hành vi JAVIS_LESSON legacy chưa thuộc Resonance.
- [ ] Thêm các evaluator mới bằng registry, không sửa state machine. Human confirmation yêu cầu danh tính xác thực, không nhận câu tự báo của model là chữ ký người dùng.
- [ ] Chạy test mới và python tests/run.py learn_agent_workflow agent_tu_boi_dap memory_hoa_thuong -v; review và commit.

## Task C4 Supervisor và worker có quyền tách biệt

**Files:** Create server/resonance_supervisor.py, server/resonance_worker.py, server/resonance_isolation.py, tests/python/test_resonance_supervisor.py, tests/python/test_resonance_isolation.py, docs/dev/resonance-supervisor.md.

**Interfaces:**

- IsolationProbe(supported: bool, reason: str, verified_boundaries: tuple[str,...]); kiểu trong resonance_isolation.py.
- IsolationBackend.probe() -> IsolationProbe; launch(workspace: Path, manifest: dict) -> str; stop(worker_id: str) -> None; inspect(worker_id: str) -> dict.
- Supervisor.issue_job(experiment_id: str, grant_id: str, workspace_ref: str) -> str.
- Supervisor.revoke_tree(goal_id: str, principal: Principal) -> None.
- Supervisor.collect_receipt(worker_id: str) -> dict.

- [ ] Viết test worker không tự tạo grant, đổi epoch thu hồi, sửa receipt hoặc báo test giả thành host receipt.
- [ ] Viết test probe chưa đủ boundary thì supported=false và app_code chỉ ở chế độ prepare, không tự fallback sang full shell host.
- [ ] Viết integration test với worker thử ghi vào grant/evaluator/receipt/supervisor control path: bị từ chối; revoke chặn job mới và dừng worker; không in secret vào log test.
- [ ] Chạy python tests/run.py resonance_supervisor resonance_isolation -v. Test môi trường chưa có isolation phải xác nhận unavailable đúng, không ghi PASS cho boundary chưa chạy thực tế.
- [ ] Implement supervisor bên ngoài candidate checkout. V1 live dùng container worker không privileged, không Docker socket, không host PID, không mount grant store/host secrets; chỉ workspace và dữ liệu đầu vào cần thiết. Network/tool access đi qua cổng có grant scoped, không trao credential quản trị host.
- [ ] Hỗ trợ Linux/Docker Desktop khi probe thực chứng đủ điều kiện. Không tự cài hoặc cấu hình môi trường production trong module; tài liệu ghi điều kiện host và cách kiểm chứng.
- [ ] Bảo vệ evaluator/receipt và nội dung hợp đồng ở phía supervisor. Cùng process/cùng quyền host chỉ được đánh dấu trusted-development, không phải chế độ live self-update được bảo vệ.
- [ ] Chạy lại unit test và integration boundary trên host mục tiêu; ghi môi trường và kết quả. Review rồi commit.

## Task C5 Candidate code và áp dụng phiên bản Javis

**Files:** Create server/resonance_deployment.py, tests/python/test_resonance_deployment.py. Modify server/resonance_supervisor.py, server/resonance_experiments.py. Tái sử dụng server/updater.py và server/update_state.py qua adapter, chỉ sửa giao diện nếu kiểm thử chứng minh cần. Create docs/dev/resonance-recovery.md.

**Interfaces:**

- DeploymentPlan(id, experiment_id, candidate_sha, baseline_sha, manifest_hash, data_compatibility, recovery_ref, smoke_suite_ref, rollout_scope); kiểu trong resonance_deployment.py.
- DeploymentService.prepare(experiment_id: str, principal: Principal) -> DeploymentPlan.
- DeploymentService.validate(plan_id: str) -> dict.
- DeploymentService.apply(plan_id: str, principal: Principal) -> dict.
- DeploymentService.recover(plan_id: str, reason: str) -> dict.
- Kết quả deployment có phase, code_revision, data_state, checks, unresolved_effects; không có boolean rollback_ok nếu chưa kiểm đủ code và data.

- [ ] Viết test candidate_sha không trùng bản đã kiểm, sửa protected path, grant thiếu deploy hoặc probe thất bại đều chặn apply.
- [ ] Viết test đổi goal revision sau validate nhưng trước apply làm kiểm tra lại tính áp dụng; reframe không bỏ qua pause, guard hoặc thu hồi. Receipt và chi phí deploy cũ giữ nguyên dù mục tiêu được điều chỉnh.
- [ ] Viết test app health xanh nhưng smoke behavior đỏ; crash trước/sau đổi active version; recovery thất bại báo rõ và giữ supervisor hoạt động.
- [ ] Viết test migration backward-compatible phục hồi được; migration không chứng minh compatibility hoặc không có recovery_ref thì chặn live. Không reset sạch thay đổi người dùng trong checkout gốc để triển khai candidate.
- [ ] Chạy python tests/run.py resonance_deployment -v; xác nhận đỏ.
- [ ] Implement checkout candidate riêng, kiểm CI/test theo repo, artifact manifest có SHA, smoke suite do supervisor giữ. Candidate không được sửa updater/guard trong cùng experiment; có thể tạo đề xuất riêng cho owner xem xét.
- [ ] Apply theo phạm vi thử hạn chế đã cấp; mở rộng chỉ khi các checks đạt. Drain/checkpoint run trước restart, resume bằng state; không mất lịch và không chạy lại effect không chắc chắn.
- [ ] Recovery phục hồi app và data theo plan đã thử, giữ nguyên ledger tác động bên ngoài. Không tự gửi hành động bù trừ nếu grant chưa có quyền đó.
- [ ] Chạy test mới và python tests/run.py update update_lui_hong update_diagnose workflow_graph_phase10 -v. Chạy smoke/recovery thật trên bản sao triển khai, không trên dữ liệu người dùng trong lượt lập kế hoạch.
- [ ] Viết hướng dẫn khôi phục có điều kiện cụ thể; review và commit.

## Task C6 Đối chứng toàn hệ thống và phát hành có giới hạn

**Files:** Create tests/python/test_resonance_acceptance.py, tests/fixtures/resonance/evaluation_protocol.json, docs/dev/resonance-evaluation.md. Modify hướng dẫn người dùng vi/en và cấu hình feature flag nơi tích hợp ở server/main.py.

**Interfaces:** run_acceptance_suite(profile: dict) -> dict trong test harness; báo cáo chứa intent/contract/evaluator/model/variant revisions, case results, goal_fit, execution_outcome, actual resources, intervention count và unavailable measurements.

- [ ] Viết các tình huống end-to-end ở mục 16 spec với fixture không dùng dịch vụ thật. Đối chứng cùng runner bật/tắt học và cùng nguồn lực.
- [ ] Tạo bộ đầu vào chưa thấy trước cho Goal framer: mơ hồ, đủ rõ, user_unsure, không trả lời, xung đột và thay đổi nhu cầu. Chấm độ phù hợp theo nguồn và ràng buộc giữ riêng; evaluator ngữ nghĩa không nhận danh tính baseline/candidate khi khả thi. Cho phép nhiều mục tiêu hợp lý; ca không đủ căn cứ có kết luận unknown, không dùng sự tự tin của model làm đáp án.
- [ ] Đo số câu hỏi thực sự cần, số lần hỏi lặp, công sửa cách hiểu, mức tiến triển hữu ích và chi phí khám phá. Không tối ưu riêng ít câu hỏi vì có thể tạo hành động sai; bỏ câu hỏi cần thiết cũng là lỗi. Kiểm rằng hoàn thành khám phá không tự báo đã giải quyết nhu cầu.
- [ ] Thêm ca hồi quy từ đối chiếu Claude: chuỗi số có id/ngày/mã lỗi; nguồn ổn định nhưng đủ chất lượng; đổi cadence không đổi cùng kết quả nguồn; guard vượt ngưỡng khi agent chưa hành động; hai brain trùng slug; mất audit trước/sau effect; chat refresh giữ đúng action. Chỉ chạy suite undo khi adapter B6 được phát hành, còn không phải xác nhận UI không quảng bá khả năng đó.
- [ ] Chạy suite với clock/executor giả để kiểm determinism, sau đó chạy pilot bằng engine được người dùng chọn trên tài nguyên mô phỏng. Không tự ghi kết quả pilot khi chưa thực hiện.
- [ ] Báo cáo riêng độ phù hợp mục tiêu, kết quả công việc, chất lượng phép đo, chi phí và công can thiệp. Nếu tiêu chí thay đổi, ghi bảng theo revision và lý do; không cộng gộp thành tỷ lệ thắng che việc hạ mục tiêu. Không lấy token mỗi tim hoặc số cuộc chat làm metric chính.
- [ ] Kiểm thử thêm loại adapter mới chỉ bằng đăng ký plugin/evaluator và fixture; goal service không thêm nhánh nghiệp vụ.
- [ ] Đo một mốc nhỏ trước: cùng yêu cầu, một agent, artifact adapter và hai cấu hình phương pháp trên fixture. Ghi rõ phần đã kiểm và phần chưa mở, không cần đợi nhiều tuần reaction hoặc xây xong nhóm/undo mới kiểm tra giá trị vòng tự cải thiện.
- [ ] Chạy python tests/run.py resonance -v, rồi toàn bộ checks bắt buộc của repo trước phát hành. Lỗi mới được xử lý trước mở rộng; không lặp toàn bộ suite nếu không có thay đổi hay vấn đề mới.
- [ ] Bật theo brain/goal được chọn, có switch quay về hành vi cũ; tự cập nhật live vẫn là quyền opt-in riêng. Ghi điều kiện mở rộng bằng số liệu pilot, không ấn định trước tỷ lệ thắng giả định.
- [ ] Hoàn thiện PR theo docs/quy-uoc-dev.md; CI xanh và đối chiếu tiêu chí giai đoạn trước khi tích hợp.

## Điều kiện hoàn thành toàn bộ chương trình

- [ ] Một nhu cầu tự nhiên được agent chuyển thành mục tiêu, thực hiện, kiểm chứng và báo kết quả mà không bắt người dùng chọn mục tiêu, không phụ thuộc reaction hoặc ngành cụ thể.
- [ ] Khi người dùng chưa rõ, agent làm rõ có chọn lọc hoặc tự khám phá trong quyền; sửa cách hiểu theo bằng chứng, giữ lịch sử và không tự chấm thắng bằng đổi tiêu chí.
- [ ] Agent và nhóm dùng cùng hợp đồng, có bằng chứng đóng góp và quyền kế thừa.
- [ ] Ít nhất một thay đổi phương pháp được tự thử, xác nhận, áp dụng và có thể khôi phục.
- [ ] Tuyên bố tự cập nhật live chỉ được bật trên môi trường đã qua kiểm thử supervisor, effect recovery và data compatibility.
- [ ] Có thể chỉ rõ phần cải thiện được đo, phần còn chưa chắc và số liệu làm cơ sở.
