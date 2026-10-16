# Javis Core - kiến trúc thực tế và bàn giao

Spec gốc: yêu cầu của chủ repo ngày 16/10/2026 ("Javis Core thành trợ lý hệ thống mặc định, được ghim trong mọi
brain, nhận báo cáo đúng người, hỗ trợ trao đổi tiếp và thích nghi qua Second Brain"). Triển khai qua ba bản:

| Bản | Nội dung |
|---|---|
| 0.185.0 | Javis Core: định nghĩa chung, ghim, khoá ở máy chủ, chat mặc định mỗi brain |
| 0.186.0 | Định tuyến báo cáo về Javis Core, bỏ mọi kiểu gửi đoán |
| 0.187.0 | Tin hệ thống (đã đọc ở máy chủ, hỏi Javis Core), thông báo đẩy theo đăng nhập, kiểm soát trí nhớ |
| 0.188.0 | Sau rà soát: lượt chat theo brain của chat, Javis Core gọn hơn, chặn cứng ghi trí nhớ cho Claude Code, máy chủ tự ghi nguồn ghi nhớ |

## 1. Kiến trúc tìm thấy khi rà soát (trước 0.185.0)

- **Một tài khoản mỗi bản Javis.** `settings.json` có đúng một `auth` (chủ). Phiên đăng nhập là token trần, không
  gắn người. Nhiều người dùng = nhiều bản Javis độc lập (`docker-compose.multi.yml`). Các chat ID Telegram trong danh
  sách cho phép đều được coi là chủ.
- **Brain đang mở do trình duyệt chọn** và đi kèm mọi request; server không có danh sách thành viên theo brain.
- **Một cửa báo cáo duy nhất:** `_notify_owner` → hòm thư (`inbox.json`) + MỘT kênh ngoài. `owner_chat` rỗng thì gửi
  **ID Telegram đầu tiên**; chat ID lạ cũng dồn về ID đầu; Zalo rỗng/lạ thì gửi **mọi** ID; `_loop_notify` (loop tự
  dừng, bộ não chết) gửi **mọi** ID Telegram. Mục hòm thư có trường `brain` nhưng không ai điền.
- **Tin tức (bản phát hành, thông báo cộng đồng)** tính lại mỗi lần, đã-đọc nằm ở localStorage từng trình duyệt.
- **Thông báo đẩy** gửi tới mọi trình duyệt đã đăng ký, không gắn đăng nhập, còn nhận sau khi đăng xuất.
- **Trí nhớ** ở `<brain>/memory/` (MEMORY.md + facts/). Không có chỗ xem/sửa/quên, không có danh sách đã quên, công
  tắc tự học là một cờ chung cho mọi brain. Bài học trợ lý (`agent_lessons`) bị thu hồi vẫn học lại được.
- **Trợ lý** chỉ là file `<brain>/agents/<slug>.md`; skill hệ thống được CHÉP vào từng brain; plugin hệ thống thì đọc
  thẳng từ `system/plugins/` (mẫu dùng lại cho Javis Core).

## 2. Quyết định thiết kế

- **Javis Core không phải một agent persona.** Chat với nó là một lượt Javis đầy đủ (CLAUDE.md, MEMORY.md, mọi tool)
  cộng khối `# === JAVIS CORE ===` lấy từ `system/agents/javis-core.md`. Kênh phiên là `agent:javis-core` để trang Cộng
  sự, hòm thư và lịch sử coi nó như một trợ lý, còn `workflow_chat.persona_cua_phien` trả None cho kênh này.
- **Một định nghĩa ở cấp nền tảng**, không chép vào brain. Slug `javis-core` được giữ chỗ: file `agents/javis-core.md`
  lạc trong brain bị bỏ qua (`agents_index`, `_agent_file`), gói nhập không ghi được, tạo trợ lý trùng tên bị từ chối.
- **"Đúng người" = đúng tài khoản của bản Javis đó.** Với kiến trúc một-chủ-một-bản, người nhận là chủ; điều cần đúng
  là brain nguồn và kênh. Không dựng hệ thống tài khoản mới (xem mục 6).
- **Chat mặc định mỗi brain** do server giữ con trỏ trong `STATE_DIR/javis_core.json`; xoá hoặc lưu trữ thì lần sau
  tạo chat mới trống, không hồi sinh nội dung.
- **Không đoán người nhận.** `_report_route` quyết định nơi nhận từ đích + brain CỦA VIỆC (do nơi sinh việc truyền),
  không bao giờ dùng brain đang mở trên màn hình.

## 3. Ánh xạ spec → mã

| Spec | Chỗ trong mã |
|---|---|
| 3.1 định nghĩa chung | `system/agents/javis-core.md`, `server/javis_core.py` |
| 3.2, 11, 12, 14 vai trò, khởi đầu, tự học, giới hạn | thân file định nghĩa (khối JAVIS CORE trong prompt) |
| 3.3 quyền | Javis Core chạy bằng quyền của lượt; không có route nào cấp quyền theo nhãn |
| 4 ghim, khoá | `GET /agents?system=1`, `_core_refusal` (xoá, sửa, đổi tên, bỏ ghim, tag, Auto, tài sản, nhập gói, trưởng nhóm tạo) |
| 4, 5 chat mặc định | `POST /javis-core/session`, `javis_core.default_session` |
| 6 định tuyến | `_report_route`, `_notify_owner`, `_owner_telegram_id` |
| 6.4 thiếu thông tin | mục hòm thư `routing: no_target / lost_origin`, không gửi đi đâu |
| 7.1 tin chung, đã-đọc | `GET/POST /notifications/read`, `inbox.news_*` |
| 7.2 tin giới hạn | `_loop_notify` → hòm thư + Telegram của chính chủ, không còn phát cho mọi ID |
| 7.3, 15 hỏi tiếp | `POST /javis-core/cite` (chép thông báo kèm nguồn, thời điểm vào chat Javis Core riêng) |
| 8 đẩy, Telegram | `telegram.owner_chat_id`, `webpush` gắn `phien`, `/auth/logout` gỡ thiết bị, `push.preview` |
| 8 trùng khi thử lại | `inbox.add(dedup=...)`; khoá theo việc/lần chạy ở Kanban, loop, nhắc hẹn, việc chạy nền |
| 10.2 hồ sơ người dùng | `STATE_DIR/user_profile.md`, `GET/POST /profile`, tool `javis_memory op=profile`, nạp TRƯỚC bộ nhớ brain |
| 12, 13 xem/sửa/quên/tắt | `server/memory_control.py`, `/memory/items|edit|forget|learning`; từ 0.190.0 làm qua chat bằng tool `javis_memory` (`server/memory_chat.py`, plugin `system/plugins/javis-memory`) |
| 12.4 không học lại điều đã quên | `memory/forgotten.json` (dấu vân tay), `learn._promote_sync`, `agent_lessons.add` |

## 4. Kết quả kiểm thử theo nhóm nghiệm thu

Mỗi dòng là một phép kiểm có thật trong test (chạy `python tests/python/<file>`).

- **Trợ lý mặc định** (`test_javis_core.py`, 34 phép): brain cũ và mới đều có Javis Core đứng đầu; xoá, đổi tên, bỏ
  ghim, gắn tag, tắt Auto, sửa qua form, gắn tài sản, nhập gói, trưởng nhóm tạo trùng slug đều bị máy chủ từ chối;
  12 lời gọi đồng thời chỉ tạo một chat; xoá hay lưu trữ chat mặc định thì có chat mới trống, Javis Core vẫn còn.
  Giao diện: `tests/js/test_javis_core_ui.js`, kèm ảnh chụp thật trên máy tính và iPhone 13.
- **Định tuyến** (`test_javis_core_routing.py`): có chat gốc thì về đúng chat đó; không có thì về Javis Core của đúng
  brain của việc (hai brain hai nơi); chat gốc đã xoá thì về Javis Core khi biết brain, không biết thì chỉ giữ ở hòm
  thư; không đích không brain thì không gửi; Telegram/Zalo/Slack... không còn dồn về ID đầu hay phát cho mọi ID.
- **Tin hệ thống, đẩy** (`test_javis_core_notices.py`): đã-đọc ở máy chủ, đánh dấu một lần thấy ở mọi thiết bị; hỏi
  Javis Core chép đúng thông báo vào chat của brain đúng, hỏi lại không chép trùng, thông báo chung không đổi; thiết
  bị gắn với đăng nhập, đăng xuất là gỡ, đăng nhập hết hạn không nhận; ẩn nội dung thì bản đẩy không mang chữ.
- **Tự học và cá nhân hoá** (`test_javis_core_memory.py`, `test_memory_chat.py`): xem, sửa, quên; đã quên
  thì vòng tự học không ghi lại (cùng slug hay cùng chữ); quên không xoá chat; tắt tự học thì vòng học, bài học trợ
  lý và tool ghi file của model đều không ghi vào `memory/`, model được báo; model không sửa được công tắc hay danh
  sách đã quên; bài học bị thu hồi không học lại; hồ sơ dùng chung mọi brain, nằm trước bộ nhớ brain.

## 5. Chuyển đổi dữ liệu và quay lui

- Không có migration phá huỷ. File mới: `STATE_DIR/javis_core.json`, `news_read.json`, `user_profile.md`,
  `<brain>/memory/forgotten.json`, `<brain>/memory/learning.json`. Trường mới: `inbox` (`dedup`, `routing`),
  `push_subs` (`phien`), `settings.telegram.owner_chat_id`, `settings.push.preview`.
- Thông báo cũ trong hòm thư giữ nguyên, không phát lại thông báo đẩy cũ, không hồi sinh chat đã xoá. Mục cũ không có
  `brain` nên không chuyển sang Javis Core được: chúng vẫn mở như trước (chat gốc, nếu còn).
- Tin tức: lần đầu mở chuông sau khi cập nhật, danh sách đã-đọc trong localStorage của trình duyệt đó được đẩy lên
  máy chủ; trình duyệt chưa mở thì không có gì để đẩy.
- **Quay lui:** cài lại bản trước. Các file mới bị bỏ qua; chat Javis Core vẫn nằm trong kho với kênh
  `agent:javis-core` (bản cũ báo "trợ lý không còn" khi mở, nội dung đọc được qua lịch sử). Báo cáo không đích sẽ lại
  rơi về ID Telegram đầu tiên như hành vi cũ.

## 6. Giới hạn và phần chưa làm

- **Nhiều người dùng trên MỘT bản Javis chưa có.** Kiến trúc hiện tại là một chủ mỗi bản; các tiêu chí "hai người
  cùng brain giữ chat riêng", "trạng thái đọc riêng theo người", "thu hồi quyền theo brain" chỉ đúng ở dạng mỗi người
  một bản Javis. Làm thật cần: bảng người dùng, phiên gắn người, cột chủ sở hữu trên `sessions`, ACL theo brain chặn
  ở `_brain_root`, ánh xạ Telegram ID → người. Đây là dự án riêng, cần chủ repo quyết.
- **Mọi ID trong danh sách Telegram được phép vẫn là "chủ"** khi chat (như trước). 0.186.0 chỉ ngừng GỬI báo cáo
  không đích cho họ.
- **Tắt tự học chặn cứng ở hai đường:** tool ghi file của hub (engine API) và luật từ chối `Write/Edit/MultiEdit/
  NotebookEdit(memory/**)` cho Claude Code (0.188.0, giữ hiệu lực cả khi bypassPermissions). Chưa chặn: lệnh Bash
  của Claude Code tự ghi file, và tool file riêng của Codex, Grok, Antigravity; các đường này chỉ có lời dặn
  "GHI NHỚ MỚI ĐANG TẮT" trong prompt.
- **Quên có giới hạn:** brain lưu bằng git (tự học dùng git commit) vẫn còn bản cũ trong lịch sử git; bản sao lưu
  làm trước đó cũng vậy. Câu trả lời của tool nói rõ điều này sau khi quên.
- **Hồ sơ người dùng do người dùng tự viết.** Javis không tự suy diễn tính cách hay ghi vào hồ sơ này.
- Từ 0.188.0 ghi nhớ model viết trong một lượt chat mà thiếu `source` được máy chủ tự gắn "chat <ngày> (<mã chat>)".
  `status` (xác nhận hay suy luận) và `scope` vẫn chỉ có khi đường ghi tự điền.

## 7. Bổ sung 0.188.0 (sau rà soát)

- **Lượt chat theo brain của chat** (spec 9): mở chat của brain B khi đang chọn brain A thì lượt chạy trên B (máy chủ
  đổi brain theo phiên và báo `brain_follow`); chat hiện dòng "thuộc brain B" kèm nút chuyển; bấm thông báo của brain
  khác thì dashboard chuyển brain TRƯỚC rồi mới mở. Báo cáo đến thì không tự chuyển gì.
- **Javis Core gọn hơn:** vòng chạy trót lọt (`quiet`) chỉ ở chuông (nút "Hỏi Javis Core" vẫn đưa vào được); báo cáo
  gửi Telegram chỉ chép vào Javis Core khi đó là Telegram của chính chủ.
- **Ô "Telegram của bạn"** là ô chọn từ danh sách ID được phép.

## 8. Cài đặt tối giản, trí nhớ qua chat (0.190.0)

Chủ repo 16/10/2026, sau khi xem thẻ Javis Core và cột trợ lý: tự học của Core hiện quá nhiều thứ trong khi Javis đã có
ngữ cảnh trong brain; bài học cũ của trợ lý lòng vòng, nút Thu hồi và Dùng ở mọi nơi người dùng không biết dùng. "Thà
nhắn tin bảo xoá sửa thu hồi rồi AI làm giúp còn tốt hơn." Cài đặt chỉ giữ thứ thị trường quen dùng (đổi ảnh đại diện,
tên, mô tả, hướng dẫn, tài liệu, kỹ năng, model).

- **Thẻ Javis Core:** chỉ còn ảnh, tên, nhãn Hệ thống, vai trò và một câu "muốn nhớ, sửa hay quên thì nhắn trong chat".
  `dashboard/core-memory.js` đã gỡ.
- **Cột một trợ lý:** form cài đặt đứng đầu. Khối Auto (mục tiêu, nhịp, hạn mức tự chạy) nằm dưới và chỉ hiện khi Auto
  của trợ lý đang bật (`veAuto` trong `workspace.js`). Mục Bài học A3 (`resonance-agent.js`) và danh sách bài học theo
  phạm vi, bài học cũ, thay đổi tự rà soát, đề xuất (`agent-lessons-ui.js`) rời màn hình; mục còn lại là "Hạn mức tự
  chạy".
- **Tool `javis_memory`** (chỉ phiên của chủ, mức `safe`, mọi engine): `list`, `edit`, `forget`, `learning`, `profile`,
  `lessons`, `lesson_add`, `lesson_revoke`. Luật giữ nguyên: quên chỉ còn dấu vân tay và không học lại, bài học bị thu
  hồi không tự học lại, tool ghi file của model vẫn không ghi được công tắc.
- **Chưa đưa vào tool:** bài học trình bày A3 (báo gọn hay đủ) đã áp dụng trước đây; đề xuất mới loại này không còn
  nút Áp dụng nên không phát sinh thêm. Các route `/memory/*`, `/profile`, `/agents/{slug}/lessons/*` vẫn còn cho
  công cụ ngoài.
- **Dòng "Đã nhớ · Hoàn tác"** (`server/memory_receipt.py`, `dashboard/chat-nho.js`): đầu lượt chat dashboard chụp
  `memory/` (bỏ `conversations/`, `runs/`), cuối lượt so lại; ghi nhớ mới, đã sửa, đã quên thành một dòng đẩy vào
  chat (khối ẩn `JAVIS_NHO`, F5 vẫn còn). Hoàn tác gọi `/memory/forget` nên không học lại. Câu trả lời khai "đã nhớ,
  đã quên, đã thu hồi" (tập `MEMORY_CLAIM` trong `server/lexicon`) mà không file nào đổi và không tool trí nhớ nào ghi
  (`memory_control.note_change`) thì có dòng đính chính. Chỉ đường dashboard; Telegram chưa có dòng này.
- **Thẻ trợ lý:** giờ chat (12px) và công tắc Auto chung cụm `.ws-item-end` ở góc dưới phải, công tắc có trên mọi
  trợ lý (bỏ luật ẩn khi tắt của 0.175.0). Khối Auto trong cột Cài đặt dùng bảng Nhịp bản gọn (`compact`): một dòng
  hạn mức bằng lời thường và đề xuất đang chờ; bảng đầy đủ vẫn ở ngăn Nhóm.
- **Tin tức không vào Javis Core:** thẻ tab Tin tức bỏ nút "Hỏi Javis Core"; thông báo việc của chính chủ vẫn có.

