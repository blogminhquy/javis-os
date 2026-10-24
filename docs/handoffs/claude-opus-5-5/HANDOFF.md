# Bàn giao Javis cho Claude Opus 5.5

**Bản khởi tạo24/10/2026 — đang cập nhật, M2 engineering CHƯA hoàn tất.**
Đọc file này trước; kiểm Git/source/PR/CI thật trước mọi hành động. Không suy
trạng thái cuối từ bản bàn giao đang viết hoặc từ transcript cũ.

## Quyết định có hiệu lực

Chủ trực tiếp thu hẹp Goal hiện tại: **hoàn thành M2 engineering rồi kết thúc
Goal và bàn giao**, vì hạn mức token. Không tạo Goal mới, không chạy M3–M8.
Quyết định24/10 từ chat “Xác định bước harness2 tốn thời gian” thay yêu cầu
M0–M8 và mọi lệnh tiếp tục toàn bộ trước đó. [Goal18](../../superpowers/AGENT-SKILL-IMPROVEMENT-GOAL.md)
là nguồn quyền; [progress](../../superpowers/status/agent-skill-improvement-progress.md)
giữ toàn bộ lịch sử và evidence. Mục cũ mâu thuẫn là lịch sử, không phải lệnh mới.

Goal chỉ complete sau M2A–F/D1/D2 engineering, mọi gate kỹ thuật bắt buộc của
mã bàn giao, docs và tích hợp đạt. Business/live acceptance **PENDING**.
Không khởi động/đợi real-account/model/business feasibility/pilot/canary. M2F
phải có workflow feasibility mô phỏng, gồm candidate thua/unknown giữ baseline.
Không hạ qualification/source/runtime/CI/review hoặc đổi assert để tuyên bố đạt.

## Snapshot ban đầu — phải cập nhật khi M2 kết thúc

| Mục | Trạng thái xác minh lúc khởi tạo |
|---|---|
| Worktree được phép | `C:\Users\admin\.codex\worktrees\agent-skill-improvement-m2a\Javis-OS` |
| Checkout chính cần bảo toàn | `D:\Project\Javis-OS`, có thể bẩn; không reset/clean/checkout/ghi đè |
| Nhánh | `codex/agent-skill-improvement-m2d1` |
| HEAD docs trước scope override | `f2c8f3fe` (xác minh full SHA bằng Git) |
| PR | [draft803](https://github.com/blogminhquy/javis-os/pull/803) |
| Task branch remote đã kiểm | `4ba9624a76cd4bfb54d3d229263baa223944383b`; local code đi trước remote |
| VERSION | `0.299.0`, không tự coi đã phát hành |
| Schema đã commit | `10`; schema11 consent chưa triển khai |
| Goal lifecycle | ACTIVE; API hiện có không hỗ trợ sửa objective, scope mới ở Goal18/checkpoint |

Recipe-source Task1 đã chốt source `269d3892e2ae735245438795a59a7558e7aa1df6`,
đúng6source/test paths, final freeze09:15:05UTC. Windows43run/42pass+1skip;
Linux43PASS/0skip; scoped review specPASS/qualityApproved,0findings. Đây là
forward unit được bảo toàn, không phải nghiệm thu toàn M2. Worker đã terminal
và release sole serial test slot; audit09:20:15UTC có0owned process/temp/root.
36scratch roots Oct22 có trước task được giữ nguyên vì chưa xác định ownership.
Không có actual native/model process do Task1 tạo. Các PID server6936/5444 là
snapshot server thật ngoài task, không được đụng hoặc kill theo PID lịch sử.
Report/logs/review/root audit nằm trong ignored same-plan workspace được dẫn
ở public proof; giữ tại chỗ cho khôi phục và kiểm trace/hash.

## Hiện trạng và việc M2 cần chốt

| Phạm vi | Kỹ thuật | Business/live |
|---|---|---|
| M0/M1 | Nền đã tích hợp; reuse exact-source evidence, chỉ kiểm ảnh hưởng mới | Không suy adapter/engine readiness tổng quát |
| M2A/B/C | Đã tích hợp, không làm lại | Không biến fixture thành hiệu quả |
| M2D1 | Nhiều unit baseline/candidate/view/native/ownership đã review; owned same-pipeline dummy qualifier hiện tại chưa hoàn tất | Không gọi tài khoản/model thật |
| M2D2 | Routing foundation/named-skill snapshot có proof; coverage runtime/surface đã enable và effective-view/resume chưa đủ toàn bộ | Chưa xác minh rộng |
| M2E | Atomic manual one-scope apply/revert/recovery/UI cần đối chiếu và hoàn thiện | Không tự bật activation/live canary |
| M2F | Operator/evidence/report và full feasibility workflow mô phỏng còn mở | Feasibility thật/pilot/canary PENDING |
| M3–M8 | Backlog bàn giao; bảo toàn phần làm trước, không triển khai tiếp trong Goal này | Tất cả gate chưa đạt giữ pending |

Nguồn hợp đồng M2: [spec23](../../superpowers/specs/2026-10-22-agent-skill-evidence-improvement-design.md),
test matrix22/acceptance13/manual apply14/retention18/UI19/usage20 trong cùng file;
[M2D1 plan](../../superpowers/plans/2026-10-23-agent-skill-improvement-m2d1.md),
[D2 routing](../../superpowers/plans/2026-10-24-agent-skill-improvement-m2d2-routing-foundation.md).
Root phải lập closeout plan theo source hiện tại, giữ blocker thật và no-side-effect.

Đơn vị recipe-source đang chạy được chốt an toàn, review và bảo toàn; không mở
Task2 schema11/Task3 destination-consent/retrieval chỉ vì plan cũ ghi mandatory.
[Plan cũ](../../superpowers/plans/2026-10-24-recipe-destination-authority.md)
đã có owner override. Private brief Task2 chỉ được chuẩn bị, chưa dispatch/code;
schema11 trong brief đó chưa được triển khai/đặt chỗ, phải rebase theo schema
thật nếu được chủ cho làm sau này, không dùng số version dự kiến như authority.
Further owned Library/native/downstream consumers và orchestration comparison
để backlog, trừ một phụ thuộc M2 cụ thể được chứng minh và ghi quyết định nhỏ.

## Source, bằng chứng và các gate chưa đạt

- [Source observer proof](../../superpowers/evidence/2026-10-24-recipe-source-observer.json):
  source `269d3892`, review snapshot `429d9334`; Windows42pass+1skip và
  early Linux [40081705134](https://github.com/blogminhquy/javis-os/actions/runs/40081705134)
  exact6pins/43PASS. ProofSHA
  `a0ec009bb3eab3e53756cd37e560429f7f7dc8107de99760b4b6045a9fe43cf9`.
  Root verified69raw artifacts/frozen bytes/cleanup; no final M2/native claim.
- [Archive view proof](../../superpowers/evidence/2026-10-24-recipe-archive-views.json):
  implementation `bc1a3a68`, docs checkpoint `b3e8901a`; local64PASS,
  early Linux [40078670232](https://github.com/blogminhquy/javis-os/actions/runs/40078670232)
  exact13pins/76PASS. Independent scoped specPASS/qualityApproved.
  **Không phải full final-task-head CI hoặc native/business proof.**
- [Archive authoring proof](../../superpowers/evidence/2026-10-24-recipe-archive-authoring.json):
  `cbbbdacd` + test-only `aa1e0732`, encrypted original evidence/refs/cold states.
- [Library snapshot proof](../../superpowers/evidence/2026-10-24-harness2-library-snapshot.json):
  `9e098a52`, actual derived Library technical fixtures; chưa product consumer.
- Current native `PROFILE_SOURCES99` đã UNQUALIFIED/registries closed sau Task1.
  Không thừa hưởng qualification cũ. Profile seed list không đồng nghĩa toàn
  transitive closure: existing native_release._inventory còn pin local imports
  (gồm trial_semantics/resonance_store); full installed/runtime gate vẫn mở.
  `IC.PROFILE_VERSION=claude-isolated-roles-v2`; selected native format baseline5,
  view4, operation2; legacy1/3/1 được bảo toàn. Selector không là qualification.
- Dummy environment/session/record/startup/binding có các unit đã kiểm, nhưng
  shared Guardian/bootstrap/native capture/SDK/private ACK/drain/publisher/
  cold-read/cleanup và exact current footprint cần kiểm đủ actual pipeline.
- Protected `tests/python/test_improvement_view_reservations.py` rawSHA
  `0577b5181fb090ba897ec8c3d0fce10fe88d2d09d03839497150cdacf6e793e0`
  không được sửa để vượt gate. Historical actual309 proof không tự áp cho source mới.
- Deferred minors: compose panel `T2-R4` ambiguous labels/`T2-R5` old warning noise;
  recipe-archive-authority Task2 `T2-R1` asyncio timing diagnostics. Không suppress
  toàn cục. Future-schema-controls Task1 `T1-R1`: hashes ghi sau GREEN, không có
  timestamp freeze trước chạy; giữ limitation cho final whole-branch review.
  Hai future9 fixtures đã sửa tại `21a5c0b1` theo current+1, giữ nguyên asserts;
  actual2GREEN/scoped qualityApproved. [Proof](../../superpowers/evidence/2026-10-24-m2-future-schema-controls.json)
  SHA `74a92878248c7a22f3d49e13b06a7c57c88f88688406daf1760a5d02569cf6fa`.
- Fresh final exact-head full required CI và một whole-branch review mạnh nhất
  còn mở. Scoped reviews/early CI chỉ chứng minh đúng phạm vi/bytes đã ghi.

M2 qualification gap map mới nằm tại ignored
`.superpowers/m2-engineering-handoff/qualification-gap.md` (static/read-only,
không phải qualifier proof): startup3 chưa có production caller; SDK startup2/
environment/account verifier đúng là từ chối dummy; Session chưa attach native
owner; còn technical capability/reservation/ACK/drain/publisher/cold cleanup
joins. Dùng typed engineering authority account_ready=false, giữ production
gates; không giả subscription auth để chạy. Actual current source/CLI localhost
dummy pipeline vẫn là kỹ thuật bắt buộc nếu khả thi; account/model thật bị loại
khỏi Goal mới. Nếu dummy runtime thật đòi account inference thì ghi blocker thật.

Next design ở ignored `.superpowers/m2-engineering-handoff/qualification-next-design.md`:
P0 thêm false-readiness/domain fences tại4product boundaries; P1 nối actual
Session→parent→Guardian→startup3→worker/SDK technical preflight và proven drain.
Đây mới là thiết kế, chưa code/proof. P1 không query/model và không cấp capability;
full current-input dummy-query/accounting/typed publisher/cold cleanup vẫn mở.

## Google Harness² reuse đã có — giữ provenance/license

Upstream [google-research/harness2](https://github.com/google-research/harness2)
pin `1cfe254e8d25b15f37048c3730134686abe60335`, Apache-2.0/Google2026.
[PROVENANCE](../../../third_party/harness2/PROVENANCE.md),
[COMPOSE-PROVENANCE](../../../third_party/harness2/COMPOSE-PROVENANCE.json),
[LIBRARY-PROVENANCE](../../../third_party/harness2/LIBRARY-PROVENANCE.json),
[LICENSE](../../../third_party/harness2/LICENSE),
[reuse map](../../superpowers/plans/2026-10-24-harness2-reuse-map.md).

- Proposer: `improvement_generation_protocol._proposal_method` là adaptation
  phương pháp/prompt, không phải toàn Google executor.
- Compose: actual independent implementation trong
  `server/improvement_harness2_compose.py`, adapter
  `improvement_compose_protocol.py`, giữ baseline/KEEP_BASE/unknown, typed3
  candidate/comparison/view/owner pipeline. Source prompts.py SHA
  `d1f4f8db4ab4cb4addcbca175b548db2270375499fda727ac95d271c63cc2504`.
- Library: actual extracted Library/helpers trong
  `improvement_harness2_library.py`, `_tree.py`, `_context.py`;
  `improvement_recipe_snapshot.py` dùng Library thật với tối đa3 projections.
  Source library.py SHA
  `00219fda201a030f43b35b49c4e73ccf336aedc81164144c435b4b06a1256dd3`.
  Chỉ3 boundary adaptations cho POSIX keys/UTF-8/LF được ghi provenance.
  Temporary derived snapshot chưa là canonical authority hoặc full native integration.
- Javis vẫn giữ permission/brain/scope/evidence/ledger/leases/cleanup/state machine;
  không có runtime/ledger thứ hai. Chưa thay core orchestration hoặc đo token savings.

Giữ các addendum [Goal12–18](../../superpowers/AGENT-SKILL-IMPROVEMENT-GOAL.md):
test/review theo ảnh hưởng và exact bytes; thay chọn lọc theo tổng công/quality;
code-first; direct compose/Library reuse; **scope M2 mới ưu tiên trên lịch cũ**.

## Roadmap chuyển cho Claude — chưa được tự khởi động

1. M3 sau M2: một nghiệp vụ với bộ12/20/12, policy pin/two-repeat/reviewer/owner,
   recipe linkage, conditional activation/monitor/revert. Pilot/live chỉ khi chủ
   giao riêng; canary thật7ngày/10việc không thay bằng clock giả.
2. M4/M5 sau nền M3, chốt chung effective view/selector: skill routing/trigger
   regression/từng adapter và agent procedure overlay theo scope, owner lines,
   persona/model/reasoning/grants/disabled state giữ nguyên.
3. M6 sau các surface tương ứng: dependency graph/helper sandbox/atomic bundle,
   alias và interaction/ablation, qualification riêng.
4. M7 sau M5/M6 và Team acceptance/usage: roster/roles/handoff/aggregate evidence,
   recipe transfer là candidate chưa kiểm, không suy từ nhiều agent đồng ý.
5. M8 sau nền/evidence trước: nhu cầu theo lỗi/evidence, refinement tối đa2,
   controlled compose/consolidation/export/import/stop/revoke/restart/multiprocess.
   Forward code đã có: compose, derived Library, encrypted recipe schema9/10,
   authoring/views và source observer đang chốt. Còn consent/ranking/native
   Library lifecycle/downstream/grades/lesson/physical GC; **không báo M8 done**.

## Quyền, môi trường và bảo toàn tài nguyên

- Được tự sửa/test/review/internal subagents/commit/push/draft PR/merge khi đủ
  required CI/review theo Goal3 trong scope M2 mới; không hỏi duyệt routine.
- Không quyền real test mới trong Goal thu hẹp, deploy/restart server thật,
  activation/auto_scoped trên brain thật, gửi/đăng/thanh toán hoặc mở brain khác.
- Đổi coding assistant không đổi Javis selected engine. Last verified local
  config: Claude CLI2.1.309/SDK0.2.116/opus5.5/medium/fastfalse/subscription;
  đây là snapshot cần xác minh metadata cục bộ, không chạy model/auth query.
- PowerShell trong worktree trên. Dùng Python hiện có
  `D:\Project\Javis-OS\.venv\Scripts\python.exe -B` với cwd worktree;
  không ghi/cài vào checkout chính. `tests/run.py` là runner isolation thật.
  No-real flags: JAVIS_NO_REAL_JUDGE_ENGINE/REVIEW_ENGINE/TEAM_ENGINE=1.
- `.superpowers/` ignored trong worktree giữ logs/briefs/reports/review packages/
  source freezes/CI raw logs và checkpoint khôi phục. Giữ nguyên tại chỗ;
  không `git clean -fdx`, mass-copy blobs, xóa/move worktree/key.
  Public evidence dẫn hashes/log paths; private test key giữ cục bộ, không in/copy.
- Trước chạy test, kiểm live worker/process ownership và sole serial slot.
  Không lặp completed tasks/suites hoặc gọi model để kiểm trạng thái chờ.
  Chỉ settle/cleanup reservations/workspaces/process của chính Goal bằng owner
  API/locks/recovery; không kill process theo PID lịch sử, không xóa key/state.

Kiểm chỉ đọc ban đầu từ đúng worktree:

```powershell
git status --short
git branch --show-current
git log -5 --oneline
git worktree list
git ls-remote origin refs/heads/codex/agent-skill-improvement-m2d1
gh pr view 803 --repo blogminhquy/javis-os --json state,isDraft,headRefOid,url
```

Đừng chạy full suite trước khi đọc source/evidence và xác định ảnh hưởng.
Khi ổn định M2 phải chạy full required CI đúng final head, xử lý failures và
review đúng snapshot. Cập nhật checkpoint, resource/slot cleanup, final commits/
CI/review/version/release/pending real gates tại đây trước khi complete.

## Trạng thái chốt cuối — còn phải điền bằng bằng chứng thật

Final M2 source/commit: PENDING. Required final CI: PENDING.
Whole-branch review: PENDING. Integration/release: PENDING.
Owned processes/reservations/workspace settlement: PENDING audit.
Business/live: PENDING, không thực hiện trong Goal này.
