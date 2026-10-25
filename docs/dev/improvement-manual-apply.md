# Áp dụng thử, canary và quay lại bản skill đã sửa (M2E, M3)

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

## Giới hạn hiện tại

- Canary live (7 ngày, 10 việc thật) và pilot nghiệp vụ 12/20/12 cần chủ giao dữ liệu và cho phép chạy model thật.
- Liên kết lesson với recipe/experiment (spec 15.2) để sang M5 cùng agent overlay.
- Phép thử tự động trên Claude native vẫn chưa chạy được ở production (registry phát hành rỗng), nên mọi ứng viên
  trên brain thật hiện chỉ có thể là `manual_trial`.
- Bằng chứng kỹ thuật: `tests/python/test_improvement_activation.py` và kịch bản mô phỏng
  `tests/python/test_improvement_feasibility_simulated.py` dùng kết quả tổng hợp có nhãn, không phải hiệu quả nghiệp vụ.
