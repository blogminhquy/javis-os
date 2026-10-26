# Áp dụng thử, canary, định tuyến, quy trình trợ lý, gói, phép thử nhóm, quản trị và quay lại (M2E tới M8)

Tài liệu vận hành cho phần áp dụng thủ công của **Cải tiến có kiểm chứng**, phát hành ở 0.314.0.
Spec gốc: [agent-skill evidence improvement](../superpowers/specs/2026-10-22-agent-skill-evidence-improvement-design.md), mục 14, 18 và 19.

## Làm gì

Chủ chọn một ứng viên skill đã duyệt đúng phần sửa (quyền `exact_diff` đang hiệu lực) và một trợ lý. Từ lượt chat
kế tiếp trong khung chat riêng với trợ lý đó, mọi đường nạp skill được phủ sẽ thấy bytes của ứng viên thay cho file
`skills/<slug>/SKILL.md`. File gốc không bao giờ bị ghi.

- Phạm vi (selector): `{"context": "dm", "agent_key": ...}`. `scope_hash` chỉ phụ thuộc `agent_key`; slug chỉ để hiển thị.
- Mỗi target và phạm vi có tối đa một con trỏ `active`. Muốn đổi bản phải Quay lại trước.
- Bytes lấy từ blob đã mã hoá, định danh bằng SHA-256 của nội dung, nên con trỏ đã commit không thể thấy nội dung ghi dở.
  Không có bước materialize ra file, nên không cần đối soát `pending_materialization`.

## Đường nạp được phủ và không được phủ

| Đường | Có dùng bản thử |
|---|---|
| Tool `javis_use_skill` gọi trong tiến trình (engine API) | Có |
| Ảnh chụp skill theo lượt (`TaskSkillScope`, khi bật) | Có, bytes được ghim theo lượt |
| Hub qua HTTP từ CLI (Claude Code, Codex, Grok, Antigravity) | Không: các engine này còn tự đọc `.claude/skills`, phục vụ bản thử ở một đường sẽ chia lượt làm hai phiên bản |
| Router lười (`lazy_skill_runtime`) | Không: chạy cả cho engine CLI và không chạy cho chat trợ lý |
| Kênh khác (Telegram, Team, loop, việc Kanban, việc nhóm lồng trong lượt chat) | Không: resolver chỉ nhận lượt `dashboard` có `agent`, không có `job` hay `team_gate` |

Lượt đang chạy không đổi giữa chừng: chỉ lượt mới đọc con trỏ.

## Điều kiện áp dụng

1. Chủ sở hữu brain, policy khác `off`.
2. Ứng viên không phải `KEEP_BASE`, có quyền `exact_diff` đang hiệu lực. Quyền chọn vùng sửa thôi là chưa đủ.
3. Target còn `live`, skill đang bật, file gốc đúng bytes và đúng danh tính file (dev/inode) ứng viên dựa vào.
   Chủ đã sửa hoặc xoá rồi tạo lại file thì báo `candidate_base_changed`; không tự gộp.
   Giới hạn: trên hệ thống file dùng lại inode ngay (ext4), file tạo lại với đúng bytes cũ không phân biệt
   được với bản gốc; vì bytes trùng với nền của bản thử nên phục vụ tiếp là vô hại.
4. Trợ lý có file `agents/<slug>.md` trong brain; slug hợp lệ. Resolver chỉ cấp danh tính cho trợ lý có file.
5. Thí nghiệm chưa bị chủ chốt sang lựa chọn khác (giữ bản cũ hoặc nhánh kia).
6. Phần frontmatter giữ nguyên (bề mặt V1 chỉ là thân skill).
7. Không báo cáo so sánh nào của nhánh ứng viên có `mechanical_verdict = rejected`.

Mức bằng chứng ghi vào con trỏ: `qualified` chỉ khi có báo cáo `final` đạt `numeric_gate`; còn lại là `manual_trial`,
giao diện ghi "Áp dụng thử thủ công, chưa chứng minh tốt hơn". `business_eligibility` luôn `unverified`.

## Tạm ngừng và quay lại

Lúc đọc, resolver trả bản gốc ngay khi: file gốc đổi bytes, skill tắt hoặc bị xoá (trả `None`, không hồi sinh),
quyền `exact_diff` bị thu hồi, target bị ngừng, file bị thay bằng file khác. `GET /improvement-activations` gọi
`reconcile` để ghi trạng thái `suspended` kèm lý do (`canonical_changed`, `source_unavailable`, `authority_revoked`,
`target_retired`, `candidate_rejected` khi một báo cáo kém hơn được công bố sau khi áp dụng). Lỗi đọc file thoáng
qua không ghi tạm ngừng; chỉ dấu `.disabled` hoặc file vắng mặt mới tính là mất nguồn. Route bật/tắt và xoá skill
gọi `suspend_source` ngay, nên bật lại skill không hồi sinh bản thử. Các điều kiện kiểm lại trong giao dịch ghi:
policy, target, quyền, tập báo cáo, lựa chọn của thí nghiệm và bytes file gốc.

Quay lại (`POST /improvement-activations/{id}/revert`) chỉ đổi con trỏ sang `reverted`, kiểm `expected_generation`,
idempotent theo `event_key`. Không ghi đè file, không phát lại hành động nào. Trạng thái kết thúc không chuyển tiếp nữa
(trigger SQL chặn), dòng không xoá được.

## Lưu trữ, migration và quay về bản cũ

- Bảng `improvement_activations` trong `resonance.sqlite3`, schema improvement **11**. Bước 10→11 chỉ thêm bảng,
  sao lưu một lần thành `resonance.sqlite3.pre-improvement-m2-activations.bak`, lỗi giữa chừng thì quay về 10.
- Bản build cũ (schema ≤10) từ chối mở kho 11 ở đường ghi improvement. Đường đọc skill của bản cũ không biết con trỏ
  nên dùng bản gốc. Trước khi hạ phiên bản: Quay lại mọi con trỏ đang `active`, sao lưu DB cùng thư mục
  `state/improvement/`, rồi mới đổi build.
- Sao lưu phải gồm cả DB và blob: bản sao DB một mình không đọc được bytes của bản thử.

## API

| Route | Ý nghĩa |
|---|---|
| `GET /improvement-activations?brain=&target_id=` | Danh sách theo brain, đối soát tạm ngừng trước khi trả, kèm `coverage` |
| `POST /improvement-activations` `{candidate_id, agent_slug, event_key}` | Áp dụng; 409 khi phạm vi bận hoặc nền đã đổi, 403 khi thiếu quyền hoặc bị từ chối bởi bằng chứng |
| `POST /improvement-activations/{id}/revert` `{expected_generation, event_key}` | Quay lại; 409 khi generation cũ hoặc con trỏ không còn active |

`improvement_api.CAPABILITIES["manual_apply"] = True`; `activation` (tự áp dụng có điều kiện) vẫn `False`.

## Canary theo tỉ lệ (M3, 0.316.0)

- Áp dụng kèm `allocation_pct` 1..99 tạo một dòng `improvement_canaries` (schema 12, chỉ thêm bảng, sao lưu
  `.pre-improvement-m3-canaries.bak`). Mỗi phiên chat được băm với salt của canary vào ô 0..99; dưới tỉ lệ thì
  dùng bản mới, còn lại dùng bản gốc. Một cuộc chat luôn ở một nhóm.
- Mỗi lần đọc skill được phủ trong phạm vi canary ghi một dòng `improvement_canary_exposures` cho cả hai nhóm,
  một dòng mỗi tin nhắn. Chủ chấm Đạt/Chưa đạt trên từng dòng (`improvement_canary_verdicts`); emoji không tính.
- Hai phiên khác nhau thuộc nhóm bản mới bị chấm Chưa đạt thì activation `suspended` lý do `canary_regression`.
- Nâng cấp (`promote`) chỉ khi đủ 7 ngày VÀ 10 phiếu của nhóm bản mới, kiểm lại quyền, tập báo cáo và bytes
  gốc trong giao dịch ghi. Hết thời gian không tự nâng.
- Quyền tự áp dụng (`improvement_auto_scopes`): khi một báo cáo `final` đạt numeric gate được công bố, hook
  `after_report` của experiment API mở canary với tỉ lệ đã cấp, không bao giờ 100%. Thu hồi quyền không đóng
  canary đã mở.
- Kết luận pilot: `GET /improvement-pilot-reports/{report_id}` trả `improved_in_scope|equivalent|worse|
  insufficient_evidence` cùng khoảng Wilson của tỉ lệ thắng; `business_eligibility` luôn `unverified`.
- Đồng hồ giả trong test chỉ kiểm luật; cửa sổ canary thật cần ngày và phiếu thật.

## Định tuyến bằng mô tả skill (M4, 0.317.0)

- Mô tả skill chỉ quyết định việc chọn skill ở **khung chat chính** của brain: danh sách skill trong prompt Phase 8
  của bộ não API (`build_adaptive_source_prompt`) và bộ chọn tự động (`LazySkillSource`). Chat với trợ lý chỉ liệt
  kê tên skill nên không bị ảnh hưởng. Claude Code và Codex đọc `.claude/skills` nên không nhận mô tả áp dụng
  (canary Phase 8 bỏ qua khi `provider_kind` là cli/oauth, prompt thuê bao vẫn dùng `build_system_prompt`).
- `POST /improvement-routing/evaluate` dựng bytes mới bằng `patch_description` (chỉ dòng `description:` một dòng,
  thân và các khoá khác giữ nguyên), chấm bộ câu hỏi bằng đúng hàm chấm của bộ chọn Javis với mô tả cũ và mới, lưu
  ứng viên bất biến kèm báo cáo (`improvement_routing_candidates`, schema 13). Câu `negative`/`competing` đang đúng
  mà thành chọn sai/thừa thì `rejected`; đủ khác biệt theo phép kiểm dấu thì `eligible`; còn lại `inconclusive`.
- Áp dụng (`/improvement-routing/{id}/apply`) tạo một con trỏ `improvement_routing_overlays` phạm vi `main`;
  ứng viên bị loại không áp dụng được; một con trỏ đang dùng cho mỗi skill. Quay lại chỉ đổi con trỏ.
- Lúc đọc, `main_chat_descriptions` chỉ trả mô tả cho skill đang bật, đúng bytes gốc; sửa, tắt hay xoá skill là
  mô tả gốc quay lại ngay và `GET /improvement-routing` ghi tạm ngừng.
- Bộ chọn ghi `routing_description: overlay|canonical` vào metadata của skill được chọn.
- Bộ chấm dùng đúng bộ chọn thật (`LazySkillSource.resolve` trên sổ năng lực đang chạy) cho cả hai nhánh; khi có mô
  tả áp dụng, tập ứng viên vẫn là kết quả tìm kiếm của sổ, chỉ skill được áp dụng được chấm lại (thêm vào nếu tìm
  kiếm bỏ sót), nên định tuyến của skill khác không đổi. Cần ít nhất một câu negative hoặc competing.
- Skill có mô tả dịch (`description_<lang>`) chưa áp dụng được (V1 chỉ thay mô tả gốc). Mô tả trùng nội dung cũ bị
  từ chối. Khi phạm vi chụp skill theo lượt đang bật, khung chat dùng ảnh chụp, không trộn mô tả áp dụng.
- Giới hạn còn lại: mô tả trong tool `javis_use_skill` của hub vẫn là mô tả gốc (danh sách tool được cache theo
  brain, dùng chung cho mọi lượt), nên lượt API ở khung chat chính thấy mô tả mới trong danh sách skill của prompt
  và mô tả gốc trong mô tả tool.
- Chưa có: bộ chạy thử cho bộ não API với bộ công cụ do host kiểm soát (spec 10.3), và đo việc Claude Code/Codex tự
  chọn skill; cả hai cần lượt chạy model thật khi chủ cho phép.

## Quy trình cho trợ lý (M5, 0.321.0)

- Là gì: một đoạn cách làm do chủ duyệt (lập kế hoạch, kiểm nguồn, kiểm kết quả, cách bàn giao) nối vào cuối lời
  nhắc của MỘT trợ lý thành mục riêng `# Quy trình đã được chủ duyệt (Javis quản lý)`. Không sửa file trợ lý, bộ
  nhớ, mục `## Luật chủ dặn`, model, provider, mức suy nghĩ, skills, quyền, lịch hay công tắc Auto.
- Nơi dùng (chủ tick): `dm` (chat riêng ở dashboard, CLI, Telegram), `team` (lượt nhóm), `kanban` (việc giao bằng
  Giao việc), `workflow` (bước quy trình, cả trợ lý kiểm chứng). Nơi không tick không bao giờ thấy. Mục tiêu (goal) và
  chatbot khách không nạp lời nhắc trợ lý nên không được phủ. Mọi bộ não đều nhận vì đây là chữ trong lời nhắc.
- Host nói nơi chạy: `_agent_sysprompt(slug, surface, agent_key, session_created_at)`; không có `surface` thì lời
  nhắc y như trước. Mã trợ lý lấy từ ghim phiên, thành viên nhóm, khoá việc Kanban hoặc dòng sống của slug.
- Kiểm của host khi lưu: 20 tới 2000 ký tự; từ chối dấu hiệu `JAVIS_RULE/LESSON/ASK`, comment HTML, dòng đặt
  `model:`, `skills:`, `quyền:`..., câu bảo bỏ qua luật chủ hay đổi model. Mâu thuẫn về nghĩa với luật chủ do chủ
  tự đọc và tick xác nhận (`owner_confirmed`); duyệt mâu thuẫn tự động để Phase 2.
- Ghim phiên (I10): chat riêng bắt đầu TRƯỚC lúc áp dụng giữ lời nhắc cũ; phiên mới mới dùng quy trình. Gỡ và tạm
  ngừng có hiệu lực ngay ở lượt kế.
- Tạm ngừng: chủ sửa bất kỳ dòng nào của file trợ lý ngoài mục Javis quản lý (kể cả frontmatter) hoặc mục
  `## Luật chủ dặn` (`owner_rules_changed`), trợ lý bị tạo lại cùng slug (`agent_identity_changed`), hoặc bị xoá
  (`agent_unavailable`). Bài học tự học và mục `## Bổ sung (tự học)` không làm tạm ngừng.
- Nối đường học: trợ lý đang có quy trình hiệu lực thì `op=update` của learn.py (luật bổ sung) thành ứng viên
  `source=learn` chờ chủ, không ghi live; trợ lý chưa có thì như cũ. Ý tưởng ngoài phạm vi của tự rà soát
  (`agent_review_proposals` mở) hiện trong bảng làm bản nháp. Bài học chat riêng học được trong phiên có quy trình
  ghi `overlay:<id>` vào `source_refs`.
- Lưu trữ: schema 14 thêm `improvement_agent_procedures` (chữ bất biến, hash luật chủ lúc viết) và
  `improvement_agent_overlays` (một quy trình hiệu lực mỗi trợ lý; active -> reverted | suspended). Từ 13 lên 14
  sao lưu một lần `*.pre-improvement-m5-agents.bak`.
- API: `GET /improvement-agent-procedures?agent=<slug>`, `POST /improvement-agent-procedures`
  `{agent, text, event_key}`, `POST /improvement-agent-procedures/{id}/apply`
  `{surfaces, owner_confirmed, event_key}`, `POST /improvement-agent-overlays/{id}/revert`
  `{expected_generation, event_key}`.
- Chưa có (cần chủ): pilot một trợ lý theo phạm vi với brief chủ chấm, canary quy trình trợ lý, duyệt mâu thuẫn tự
  động bằng model.

## Gói bản sửa skill + quy trình (M6, 0.325.0)

- Là gì: một con trỏ chủ áp dụng trên hai phần đã có sẵn của MỘT trợ lý: bản sửa skill (M2E, chat riêng của trợ lý)
  và quy trình (M5). Hai phần bật và tắt cùng nhau.
- Kiểm trước khi ghi (A04): đúng hai thành phần khác loại, khoá thành phần duy nhất, phụ thuộc chỉ giữa các thành
  phần và không vòng, quy trình thuộc đúng trợ lý, quy trình chỉ ở `dm` vì bản sửa skill chỉ phục vụ chat riêng.
- Nơi gói thật sự chạy: lượt chat riêng ở dashboard trên bộ não API (chỗ duy nhất đọc được bản sửa skill). Ở CLI,
  Telegram hay bộ não gói thuê bao (Claude Code, Codex...) cả hai phần đều dùng bản gốc. Gói không ghim theo phiên:
  như phần skill, mọi lượt mới sau khi áp đều dùng gói. Nhãn bằng chứng của gói luôn là `manual_trial` (chưa có
  phép thử riêng của gói).
- Có thì có đủ (S02): lúc gói đang áp, mọi lớp phủ của trợ lý đó dùng bản gốc. Thành phần của gói chỉ được phục vụ
  khi gói `active` và mọi thành phần còn hiệu lực (skill còn đúng hash gốc). Gỡ lẻ một thành phần qua API bị từ
  chối (409 `bundle_member_revert_with_bundle`); nếu một thành phần rời đi bằng đường khác thì thành phần còn lại
  thôi phục vụ ngay ở lúc đọc và lượt đối soát kế tiếp đánh dấu gói `suspended` (`member_unavailable`), gỡ nốt.
  Điều kiện "còn hiệu lực" của skill giống hệt bộ phân giải skill: đích còn sống, quyền sửa đúng từng chữ còn,
  đúng hash và định danh file. Gói đã kết thúc mà còn sót con trỏ (đứt giữa lúc gỡ) thì lượt đối soát gỡ nốt, và
  lúc đó gỡ lẻ từng phần cũng mở lại.
- Đứt giữa chừng: gói kẹt `applying` quá 120 giây (không có nhịp tim) thì đối soát chiếm quyền bằng CAS, đánh dấu
  `failed` (`interrupted`) rồi mới gỡ các phần đã áp (tìm theo khoá sự kiện cố định của từng thành phần). Lượt áp
  đang chạy thấy mất quyền ở nhịp tim kế tiếp thì dừng và tự gỡ phần của mình. Một thành phần áp lỗi thì gỡ ngay và `failed`
  (`member_apply_failed`).
- Quy kết tác dụng (Q06, Q07): `improvement_bundle.attribution` chỉ là báo cáo thuần trên các nhánh chủ đã chạy;
  chỉ có gốc với cả gói thì phần agent và phần skill là `confounded`; cả gói không thừa hưởng kết quả của từng
  phần (tốt riêng mà hỏng khi ghép là `conflict`).
- Lưu trữ: schema 15 thêm `improvement_bundle_activations` (applying -> active|failed, active -> reverted|suspended,
  một gói đang áp hoặc đang dùng mỗi trợ lý) và `improvement_bundle_members` (ghi một lần). Từ 14 lên 15 sao lưu
  một lần `*.pre-improvement-m6-bundles.bak`.
- API: `GET /improvement-agent-bundles?agent=<slug>`, `POST /improvement-agent-bundles` `{agent, manifest, owner_confirmed,
  event_key}`, `POST /improvement-agent-bundles/{id}/revert` `{expected_generation, event_key}`.
- Chưa có: helper chạy được trong sandbox (cần chủ cấp quyền loại executable), tách/gộp skill có alias, phép thử
  nhánh agent-only/skill-only thật (cần chạy model).

## Phép thử nhóm và chuyển kinh nghiệm (M7, 0.327.0)

- Chốt nhóm (`POST /improvement-team-pins` `{team_id, task_id?, event_key}`): host chụp nhóm trưởng, chế độ nhóm
  trưởng, chế độ làm việc (gated/full), thành viên và vai trò; mỗi thành viên: hash file trợ lý và luật chủ, quy
  trình M5 đang phục vụ trên bề mặt `team`, hash nội dung từng skill được cấp, nhà cung cấp và model mà bộ chạy
  nhóm thật sự chọn (kể cả lùi về model chính), mức suy nghĩ. Có `task_id` thì chụp kèm tiêu chí nghiệm thu của
  đúng việc đó (`team_acceptance`), việc phải thuộc nhóm. Không hash cả lời nhắc vì nó chứa bài học tự học lớn dần.
  Cùng nền thì dùng lại bản chụp cũ; gửi lại đúng khoá sự kiện thì trả bản chụp đầu.
- So hai nhánh (T01): chỉ so khi khác đúng thay đổi đã khai `{kind, ref}`: `procedure` của một thành viên (chỉ
  quy trình người đó đổi) hoặc `skill` theo slug (chỉ nội dung skill đó đổi). Khác đội hình, vai trò, nhóm trưởng,
  chế độ, tiêu chí là `topology_changed`; khác model là `model_changed`; sửa file trợ lý hay luật chủ là
  `agent_changed`; cấp thêm/bớt skill là `skill_grant_changed`; đổi chỗ khác là `unexpected_change`; không thấy
  thay đổi đã khai là `change_not_observed`. Hai bản chụp của hai nhóm khác nhau bị từ chối.
- Báo cáo (`POST /improvement-team-trials`, T02): chủ ghi kết quả nhánh mới so với nhánh gốc; báo cáo chỉ có giá
  trị cho nhóm và thay đổi đó (`transfer: untested`, `production_effects: []`). Mô-đun không phụ thuộc bộ chạy
  nhóm nên ghi báo cáo không thể nghiệm thu việc thật hay gửi đầu ra. `learning_frozen: false`: chưa có bộ chạy
  phép thử nhóm nên bài học viết ra trong lúc chạy các nhánh chưa được đóng băng.
- Chuyển kinh nghiệm (`POST /improvement-recipe-transfers` `{recipe_id, target: {kind: agent|team|engine, ref}}`):
  luôn là ứng viên `untested` ở chỗ mới, không mang kết quả hay bằng chứng; kinh nghiệm gốc phải còn hiệu lực và
  chưa hết hạn. Danh sách (`GET ...?kind=&ref=`) lọc đúng đích và nguồn còn hiệu lực trước khi xếp, tối đa 3 mục;
  hiện chưa có đường truy hồi nào khác dùng danh sách này.
- Lưu trữ: schema 16 thêm `improvement_team_pins`, `improvement_team_trials`, `improvement_transfers` (đều bất
  biến). Từ 15 lên 16 sao lưu một lần `*.pre-improvement-m7-team.bak`.
- Chưa có: bộ chạy phép thử nhóm thật (cần chạy model và chủ chấm), bàn giao sản phẩm riêng theo bước, nghiệm thu
  tổng hợp của phép thử, chụp kế hoạch/đồ thị phụ thuộc và nguồn dữ liệu, giao diện. L02 theo nghĩa đầy đủ (không
  nâng bằng chứng của kinh nghiệm chỉ thắng ở bước chọn) vẫn nằm ở kho kinh nghiệm M2, không thêm ở đây.

## Ưu tiên có giới hạn, xuất/nhập và tạm ngừng tất cả (M8, 0.330.0)

- Xếp nhu cầu (`improvement_library.rank_needs`): chỉ nhận nguồn spec 8.1 cho phép (chủ yêu cầu, cùng lỗi ở ít nhất
  hai việc độc lập, chủ góp ý chỉ rõ lỗi, lượt rà soát có dấu vết). Cảm xúc, nhiều agent đồng tình, dùng nhiều, để
  lâu không tự mở việc; tín hiệu hỏng bị bỏ qua; không có nguồn thì hàng rỗng, không gọi model. Không lấy chi phí
  làm mục tiêu.
- Sổ tinh chỉnh (`improvement_refinements`): mỗi bước (một cặp tuning) của một loại lỗi trong một chu kỳ ghi một
  dòng. Tối đa hai bước liền; bước thứ ba cần bằng chứng mới, tức một phép thử hay báo cáo so sánh có thật của bộ
  não chưa dùng trong chu kỳ (chuỗi tự đặt không tính), hoặc chủ giao. Ba bước liền không đổi gì là `no_progress`;
  bộ kín đã tiêu không cho lặp, kể cả khi chủ giao. Bước bị từ chối không ghi. Hiện chưa có vòng V4 tự chạy nào gọi
  sổ này; khi có, `holdout_consumed` phải lấy từ trạng thái bộ case của host, không từ người gọi.
- Xuất (`POST /improvement-export` `{procedure_ids, event_key}`): host đọc đúng chữ quy trình đã lưu theo id, kèm
  phiên bản Javis; không có báo cáo, luật chủ, hội thoại. Chữ có khoá bí mật, số điện thoại, email hay chuỗi khoá dài
  bị TỪ CHỐI (không tự sửa chữ), để chủ thấy lý do. Hash gói chỉ để phát hiện hỏng, không phải chữ ký.
- Nhập (`POST /improvement-imports` `{package, event_key}`, `GET /improvement-imports`): gói lạ được kiểm định
  dạng, hash, tối đa 20 quy trình, slug hợp lệ, cùng quy tắc từ chối dữ liệu riêng; từng mục thành ứng viên
  `untested`, không áp dụng, không cấp quyền, không mang điểm.
- Tạm ngừng tất cả (`GET /improvement-governance`, `POST /improvement-governance/suspend-all` `{event_key}`):
  - Đối soát trước, rồi liệt kê mọi con trỏ đang dùng; thành phần của gói được tính dưới gói, không đếm hai lần.
  - Gói đang áp dở bị đánh dấu `failed` bằng CAS (lượt áp đang chạy mất nhịp tim và tự gỡ phần của nó); gói đang
    dùng và thành phần của nó, rồi mọi bản sửa skill, quy trình, mô tả định tuyến chuyển sang `suspended` với lý do
    `owner_pause` (lịch sử phân biệt được với gỡ lẻ); canary đang chạy của bản sửa skill kết thúc theo.
  - Mọi quyền tự áp (auto-scope) đang hiệu lực bị thu hồi, nên không canary nào tự mở sau khi tạm ngừng.
  - Ghi một sự kiện `governance_pause`. Trạng thái nằm trong kho nên giữ qua khởi động lại và nhiều tiến trình.
  - Khác `off`: theo spec 18.2, `off` dừng thử nghiệm mới nhưng giữ các bản chủ đã áp; tạm ngừng gỡ mọi bản đang
    dùng nhưng vẫn cho chủ áp bản mới sau đó. Chưa có nút "chạy lại" các bản đã tạm ngừng: áp lại từng bản.
- Không tự nâng phạm vi: không mã nào trong M2 tới M8 mở rộng phạm vi một bản cải tiến; chuyển sang chỗ khác luôn
  là ứng viên chưa kiểm (M7), áp dụng luôn do chủ.
- Lưu trữ: schema 17 thêm `improvement_refinements`, `improvement_imports` (bất biến). Từ 16 lên 17 sao lưu một lần
  `*.pre-improvement-m8-library.bak`.
- Chưa có: vòng V4 tự xếp và tự chạy (cần chạy model và quyền `trial`/`auto_scoped`), gộp kinh nghiệm có nguồn,
  compose có kiểm lại tự động, giao diện xuất/nhập, nút chạy lại sau tạm ngừng.

## Giới hạn hiện tại

- Canary live (7 ngày, 10 việc thật) và pilot nghiệp vụ 12/20/12 cần chủ giao dữ liệu và cho phép chạy model thật.
- Liên kết lesson: M5 ghi `overlay:<id>`; liên kết với experiment có đối chứng chờ có phép thử trợ lý thật.
- Phép thử tự động trên Claude native vẫn chưa chạy được ở production (registry phát hành rỗng), nên mọi ứng viên
  trên brain thật hiện chỉ có thể là `manual_trial`.
- Bằng chứng kỹ thuật: `tests/python/test_improvement_activation.py` và kịch bản mô phỏng
  `tests/python/test_improvement_feasibility_simulated.py` dùng kết quả tổng hợp có nhãn, không phải hiệu quả nghiệp vụ.
