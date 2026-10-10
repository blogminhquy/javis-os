# Resonance A1: Cộng hưởng theo từng agent, công tắc và tiến độ tối thiểu (thiết kế)

- **Ngày:** 08/10/2026.
- **Nền mã:** `main` `09f254d0e4d009451dc58cb2e97788631c5acc1a` (0.86.1). Nhánh `claude/resonance-a1-agent-scope`.
- **Nguồn:** [phạm vi và lộ trình 08/10](2026-10-08-resonance-agent-scope-roadmap.md); review đề xuất A1 của ChatGPT (`exports/reviews/Resonance-A1-review-and-Claude-instructions-2026-10-08.md`, ngoài git).
- **Trạng thái:**
  - Thiết kế đã qua vòng review 1. Review đồng ý hướng và năm quyết định ở mục 11; có 2 P1 và 1 P2, đã sửa ở vòng 2 (mục 12).
  - Review vòng 2 cho tiếp tục, kèm một P2 về luồng bật (mục 1, 13).
  - Đã nối đủ: sổ đăng ký, liên kết phiên, bảng phụ, sao lưu, ngữ cảnh lượt, tool, cổng (scheduler, bàn giao, đăng, phép thử), API của chủ dự án, giao diện tối thiểu.
  - Review mã đạt ở `cc79deb2` (sau các vòng ở mục 12 đến 14). Pilot A1-1 đạt kỹ thuật và nội dung trong một kịch bản. Biên bản: `docs/dev/resonance-a1-verification.md`.
  - Hướng dẫn dùng, nâng cấp, quay về, khôi phục: `docs/dev/resonance-a1-migration.md`.
  - Chưa gọi model ở thời điểm đó. Đã phát hành 0.87.0 ngày 09/10/2026 (`fdfec7c5`).

## 0. Phạm vi

**Làm trong A1:**
- Mục tiêu chỉ được lập trong phiên trò chuyện với một agent đã bật Cộng hưởng.
- Mỗi mục tiêu thuộc đúng một agent.
- Mỗi agent có một công tắc riêng do chủ dự án điều khiển.
- Trang agent có màn hình tiến độ tối thiểu.

**Không làm trong A1:**
- Đường giao việc từ chat thường sang agent: hạng mục riêng, sau A1.
- Heartbeat thích nghi (A2), học từ phản hồi (A3), bàn giao đa engine (A4), đội làm và review (A5).
- Sandbox hệ điều hành cho engine có shell.

**Giữ nguyên:**
- Toàn bộ nền M1 đến M5: kho mục tiêu, revision, receipt, bằng chứng, guard, hạn mức, bàn giao bản viết trong lượt, thẻ, phép thử cách làm.
- Chat thường, loop, nhắc lịch, Kanban và mọi kênh khác chạy như trước.

## 1. Danh tính agent và sổ đăng ký

**Hiện trạng ở `09f254d0`:**
- Agent là file `<brain>/agents/<slug>.md`. Slug chính là tên file.
- Phiên trò chuyện với agent có kênh `agent:<slug>`, do host ghi lúc tạo phiên (`POST /sessions/new` kiểm định dạng và file tồn tại).
- Chưa có thao tác đổi tên. `POST /agents/delete` xoá file.
- File agent nằm trong brain, nên bộ não ghi được bằng công cụ `Write` của chính nó.

**Thiết kế:** host giữ một sổ đăng ký agent trong `resonance.sqlite3`, bảng mới `resonance_agents`:

| Cột | Ý nghĩa |
|---|---|
| `agent_key` | Mã do host cấp (`ag_` cộng 16 ký tự ngẫu nhiên), khoá chính, không suy từ slug |
| `brain_id` | Khoá brain (`_brain_key`, đường dẫn đã resolve), giống `goals.brain_id` |
| `slug` | Slug lúc đăng ký |
| `status` | `active`, `missing` (host thấy file biến mất), `retired` (xoá qua host hay chủ dự án cho nghỉ) |
| `enabled` | Công tắc Cộng hưởng, mặc định 0 |
| `config_version` | Tăng mỗi lần đổi công tắc hay trạng thái |
| `created_at`, `updated_at` | Mốc thời gian |

Mọi lần đổi đều có dòng trong bảng sự kiện mới `resonance_agent_events`: ai đổi, đổi gì, version trước và sau.

**Luật:**
- **Cấp mã:** khi chủ dự án bật Cộng hưởng lần đầu cho một agent, host cấp `agent_key`. Mỗi `(brain_id, slug)` có nhiều nhất một dòng `active`.
- **Sửa nội dung agent** (prompt, model, skill) không đổi mã.
- **Xoá qua host** (`POST /agents/delete`): dòng chuyển `retired`. Tạo lại cùng slug là agent MỚI, phải bật lại và được mã mới. Mục tiêu cũ giữ với mã cũ, không tự sang mã mới.
- **File biến mất ngoài host** (xoá tay, đổi tên tay): khi cổng thấy thiếu file, dòng chuyển `missing`, mọi mục tiêu của mã đó bị chặn.
  - File cùng slug xuất hiện lại không tự mở khoá. Chủ dự án chọn "xác nhận đúng trợ lý này" (giữ mã) hoặc "đây là trợ lý mới" (mã mới).
  - Giới hạn ghi rõ: nếu file bị xoá rồi tạo lại khi host không quan sát (ví dụ lúc server tắt), host không phân biệt được.
- **Đổi tên:** chưa có thao tác có quản lý. Đổi tên tay xem như file cũ biến mất (`missing`) cộng một agent chưa đăng ký. Mục tiêu và phiên của mã cũ KHÔNG chuyển sang agent mới trong A1 (mục 5).
- **Hai brain cùng slug:** khác `brain_id` nên khác dòng, khác mã. Mọi truy vấn đều lọc theo cả hai.

**Ghim phiên vào mã agent** (sửa review vòng 1, P1-1). Slug chỉ là tên file, nên tra "agent hiện tại của slug" sẽ để phiên cũ nhận nhầm agent tạo lại cùng tên. Host giữ bảng `session_agents(session_id, brain_id, agent_key)`:
- **Phiên đã ghim** vào mã A thì mãi là của A.
  - A còn `active`: lượt có danh tính A.
  - A `missing` hay `retired`: lượt không có danh tính. Không tự chuyển sang mã mới của cùng slug.
  - Lịch sử vẫn đọc được.
- **Phiên chưa ghim** được ghim ở lượt đầu vào dòng `active` hiện tại của slug, khi và chỉ khi chắc nó thuộc dòng đó:
  - đây là mã duy nhất từng có của `(brain, slug)`, gồm cả phiên mở trước lần bật đầu tiên; hoặc
  - phiên được tạo từ lúc mã đó được cấp trở đi.
- **Phiên tạo dưới thời một mã cũ mà chưa có lượt nào** thì không nhận mã mới.
- A1 chưa có thao tác nối lại phiên cũ sang agent khác. Muốn dùng agent mới thì mở phiên mới.
- **Bật trong một phiên chưa dùng được mã mới** (review vòng 2, P2). Ca hay gặp: agent tạo lại cùng tên, người dùng mở trò chuyện rồi mới bật. Phiên mở trước lúc cấp mã nên bị luật trên chặn.
  - Resolver giữ bảo thủ, không nới thành "cùng slug thì nhận".
  - API bật nhận `session_id` của phiên đang mở và trả `needs_new_session` khi phiên đó không dùng được mã hiện tại.
  - Giao diện nói rõ và có nút mở phiên mới của đúng agent qua host (`POST /sessions/new`, kênh `agent:<slug>`). Lịch sử cũ giữ nguyên.
  - Không báo "đã bật và dùng được trong phiên này" khi phiên đang bị chặn.
- Mỗi lần ghim có sự kiện `session_pinned`. Liên kết nằm trong kho nên giữ qua restart.

## 2. Ràng buộc lời gọi tool với lượt và agent

Review chỉ ra: sổ `luot_dang_chay.doan_luot(vault)` đoán "lượt duy nhất của brain", không chứng minh ai gọi tool. A1 bỏ cách đó cho Resonance và dùng `turn_context` (có từ 0.85.8).

**Hạ tầng sẵn có:**
- Mỗi lượt gắn một ngữ cảnh lượt bằng `ContextVar`.
- Engine trong tiến trình (engine API, plugin trong SDK Claude) đọc thẳng ngữ cảnh đó.
- Engine CLI gọi hub qua HTTP (Codex) mang khoá `X-Javis-Turn`, hub đổi khoá về đúng ngữ cảnh. Khoá giả, khoá cũ hay thiếu khoá đều ra "không có lượt". Khoá chết theo lượt.

**Thay đổi:**
- `run_turn` (dashboard) gắn thêm vào ngữ cảnh lượt:
  - `session_id` và `message_id` của tin người dùng;
  - khối `agent = {"key", "slug", "config_version"}`, chỉ khi phiên có kênh `agent:<slug>` của đúng brain, file agent còn đó, và mã GHIM của phiên (mục 1) còn `active`. Ngược lại `agent = None`.
- Host phân giải các giá trị này từ dòng phiên đã lưu và sổ đăng ký, không lấy gì từ lời model.
- Tool `javis_goal` lấy danh tính từ `turn_context.current()` ngay lúc gọi, không nhận `agent_id` trong tham số.
  - Thiếu ngữ cảnh, `agent = None`, agent không còn `active` hay đang tắt, hay `config_version` lệch: từ chối TRƯỚC mọi lần ghi kho, không gọi model.
- Lời người dùng dùng làm căn cứ được đọc từ kho phiên theo đúng `(session_id, message_id)` và phải là tin của người dùng. Không lấy từ sổ lượt.
- Hai lượt đồng thời có hai ngữ cảnh riêng, không mượn quyền nhau.
- `luot_dang_chay` giữ nguyên cho các tool khác (đoán `chat_id` của Kanban).

**Bảng hỗ trợ theo engine của phiên agent:**

| Engine | Ngữ cảnh lượt tới tool | A1 |
|---|---|---|
| Claude Code (SDK, plugin trong tiến trình) | `ContextVar` | Hỗ trợ |
| Engine API (OpenRouter, OpenAI, Anthropic API, Gemini, Groq, Ollama) | `ContextVar` (hub trong tiến trình) | Hỗ trợ lập và cập nhật mục tiêu. Bàn giao bản viết trong lượt chưa có (A4) |
| Codex | khoá `X-Javis-Turn` qua `-c` | Hỗ trợ lập và cập nhật mục tiêu. Bàn giao bản viết trong lượt chưa có (A4) |
| Grok, Antigravity | chưa mang khoá lượt | Chưa hỗ trợ: tool từ chối, giao diện ghi rõ |

## 3. Công tắc và quyền chủ dự án

**Nơi lưu:** cột `enabled` và `config_version` trong `resonance_agents`, chỉ đổi qua API của host.
- **Không có tool nào cho agent đổi công tắc.**
- Không đặt công tắc trong file agent, vì bộ não ghi được file trong brain.

**API mới:**
- `GET /resonance/agents?brain=` liệt kê agent của brain, kèm trạng thái sổ đăng ký.
- `POST /resonance/agents/toggle` với `{slug, enabled}` bật hay tắt; lần bật đầu thì cấp mã.
- `POST /resonance/agents/confirm` với `{agent_key, same: true|false}` xử lý agent `missing`.

Mọi API đi qua lớp bảo vệ web hiện có: kiểm Origin và CSRF, và phiên đăng nhập khi `JAVIS_REQUIRE_LOGIN` bật.

**Công tắc theo brain cũ** (`<brain>/Javis/resonance.json`): sau A1 KHÔNG còn cấp quyền nào.
- Không tự suy thành "mọi agent đều bật".
- Không xoá file.
- Trang cài đặt đổi khối công tắc brain cũ thành danh sách agent kèm công tắc, và ghi chú "công tắc theo brain cũ không còn dùng".
- Lý do: ít cài đặt hơn (một công tắc, ở đúng nơi), đúng ý chủ dự án.

**Giới hạn ghi rõ:**
- Engine có shell (Claude Code chạy với Bash) chạy cùng quyền hệ điều hành với server, nên về lý thuyết sửa được thẳng `resonance.sqlite3`, hoặc gọi API localhost khi tắt đăng nhập.
- A1 bảo vệ trên đường công cụ bình thường: không tool nào đổi công tắc, kho nằm ở thư mục state ngoài brain. A1 không hứa SQLite tự chống được shell; sandbox engine nằm ngoài phạm vi.

## 4. Các cổng

Cổng là một hàm của host, `agent_gate(goal hay ngữ cảnh lượt)`, gọi ở mọi đường dưới đây:

| Đường | Hiện nay | A1 |
|---|---|---|
| Tool `javis_goal` create, update, list | công tắc brain + `doan_luot` | ngữ cảnh lượt có agent `active`, `enabled`, version khớp; list chỉ trả mục tiêu của đúng agent |
| `POST /goal-requests` | chủ dự án, brain bật | chủ dự án; tin phải thuộc một phiên mà mã GHIM (mục 1, cùng hàm với `run_turn`) là agent đang bật; mục tiêu thuộc mã đó. Không phân giải tin cũ theo slug hiện tại |
| Scheduler (`tick` → `advance` → `_gate`) | công tắc brain | mã ở `goal_agents` của mục tiêu: không có thì `blocked/unassigned`; agent không `active` hay tắt thì `blocked/agent_off`. Kiểm lại bằng code, không gọi model. Không cần lượt chat nào đang sống |
| Bàn giao bản viết trong lượt (`finish_handoff`) | công tắc brain, pause, guard | thêm: agent của mục tiêu còn bật và version bằng version ghi lúc lập hay sửa trong lượt |
| Đăng sản phẩm (`_publish`), kết luận thành công | `_gate` | `_gate` gồm cổng agent; intent của hành động (`begin_action` ghi `agent_key` và version) lệch mã hay version hiện tại của mục tiêu thì giữ đầu ra trong vùng làm việc, không đăng |
| Phép thử và áp dụng cách làm (M5) | `_trial_gate` gọi `_gate` | như trên; `apply_method` kiểm lại cổng agent trong cùng giao dịch |
| Xem, tạm dừng, huỷ, bỏ chỉ dẫn, xác nhận | không đòi công tắc | giữ nguyên: chủ dự án luôn xem, dừng, huỷ được, kể cả khi agent tắt hay `missing` |
| Dòng gợi ý trong system prompt | brain bật | chỉ có trong phiên của agent đang bật |
| Hiện tool `javis_goal` | `visible_fn` theo brain | trong lượt (plugin dựng theo lượt): chỉ hiện cho agent đang bật; không có lượt (danh sách hub dùng chung): hiện nếu brain có ít nhất một agent bật. Chỉ để gợi ý, cổng thật nằm ở handler |

**Ngữ nghĩa khi tắt agent:**
- **Bật:** nhận và tiếp tục mục tiêu hợp lệ. Không mở lại pause, guard hay mục tiêu đã huỷ hay kết thúc. Host đặt lịch thức cho mục tiêu `active`, không pause, của agent đó; lần thức đầu là kiểm bằng code.
- **Tắt:** `config_version` tăng.
  - Không giữ thêm lượt mới; mọi tác động tiếp theo bị chặn.
  - Lượt model đang chạy vẫn chạy hết và vẫn tính vào hạn mức. Không hứa dừng tức thì hay hoàn chi phí. Kết quả của nó giữ trong vùng làm việc để đối soát khi bật lại.
  - Dữ liệu giữ nguyên.
- **Bật lại:** đối soát phần dở theo cơ chế M3 sẵn có.
- **Dùng lại đầu ra sau tắt/bật** (chốt theo review vòng 2):
  - Intent của lượt việc gốc giữ nguyên làm lịch sử, KHÔNG sửa version để biến thành đã duyệt từ trước.
  - Khi cổng mở lại, `_publish_latest` kiểm đủ: mã của lượt việc bằng mã đang gắn của mục tiêu; agent `active` và bật; revision; guard; baseline của file đích.
  - Qua hết thì host ghi một hành động `publish` MỚI. Intent của nó mang `agent_key` cùng version HIỆN TẠI và `source_action` trỏ về lượt việc cũ, rồi mới ghi file. Kiểm quyền lần cuối tại tác động như mọi lần đăng.
  - Không gọi model lại: số lượt engine không tăng.
  - Đầu ra của mã khác (trước lúc gán, hay agent khác) không bao giờ được dùng lại theo đường này.

## 5. Kho và migration

**Thay đổi schema** (sửa review vòng 1, P1-2). A1 KHÔNG thêm, xoá hay đổi cột của bảng nào có từ 0.86.x. Lý do: mã 0.86.1 ghi một số bảng theo vị trí cột (`INSERT INTO handoffs VALUES(?,...)`), nên thêm cột là bản cũ hết ghi được khi quay về. Mọi dữ liệu A1 nằm ở bảng riêng:
- `resonance_agents`, `resonance_agent_events`: sổ đăng ký và dấu vết.
- `session_agents(session_id, brain_id, agent_key)`: phiên ghim vào mã (mục 1).
- `goal_agents(goal_id, brain_id, agent_key)`: mục tiêu thuộc mã nào. Không có dòng nghĩa là chưa gán.
- `handoff_agents(goal_id, revision, agent_key, agent_config_version)`: agent và version lúc mở bàn giao trong lượt.
- `actions.intent_json` là JSON có sẵn, ghi thêm `agent_key` và `agent_config_version`. Không đổi cột.

Test khoá danh sách cột và thứ tự của 13 bảng 0.86.1, nên sau này ai thêm cột vào bảng cũ thì test đỏ.

**Mục tiêu cũ** (không có dòng `goal_agents`):
- Lịch sử, bằng chứng, revision giữ nguyên.
- Trạng thái chạy thành `blocked/unassigned` ở lần cổng kế tiếp. Không tự chạy, không tự gán theo tên gần giống hay phiên gần nhất.
- Chủ dự án gán một lần bằng `POST /goals/{id}/assign {agent_key, expected_revision}`.
  - Chỉ gán mục tiêu CHƯA gán, cho agent `active` cùng brain. CAS bằng `expected_revision` và bằng "chưa có dòng `goal_agents`" trong cùng giao dịch.
  - Ghi sự kiện `agent_assigned` (ai gán, cho mã nào).
  - Gán xong, lần thức đầu là kiểm bằng code; cổng mở theo công tắc của agent đó.
  - **Đầu ra và khoá lượt cũ mất hiệu lực:** hành động ghi trước lúc gán không có `agent_key` (hay mang mã khác) trong intent. Cổng đăng đòi intent mang đúng mã và version hiện tại của mục tiêu, nên đầu ra cũ chỉ nằm trong vùng làm việc, không được đăng. Khoá lượt (lease) cũ hết hạn theo luật M3; lượt sau giữ lại với intent mới.

**Chuyển mục tiêu giữa hai agent: chưa hỗ trợ trong A1.** Mục tiêu của mã đã `retired` hay `missing` nằm yên, bị chặn. Chủ dự án vẫn xem, tạm dừng, huỷ được. Thao tác chuyển (rename có quản lý, gán lại từ mã này sang mã khác) để sau A1, khi có thiết kế đủ cho lượt đang chạy và quyền trên đầu ra cũ.

**Đối soát trước tác động** (quyết định 4, chi tiết theo review): trước mỗi lần đăng, tiếp nhận bản chat hay áp dụng cách làm, host kiểm trong cùng giao dịch:
- `agent_key` ở intent của hành động bằng mã đang gắn của mục tiêu;
- `config_version` ở intent bằng version hiện tại của mã đó;
- mã còn `active` và bật;
- revision, guard, baseline như M3 đến M5.

Chỉ so số version là không đủ, vì hai agent khác nhau có thể trùng số.

**Sao lưu, quay về và khôi phục:**
- Lần đầu mã A1 mở kho có từ trước, host chép `resonance.sqlite3` thành `resonance.sqlite3.pre-a1.bak` bằng API backup của SQLite. Chỉ một lần, không ghi đè bản đã có.
- **Quay về 0.86.x mà giữ kho đã nâng:** mã 0.86.1 bỏ qua các bảng mới và ghi được như cũ.
  - Đã kiểm bằng mã 0.86.1 thật: tạo mục tiêu có bàn giao, sửa, sổ hành động, đăng, huỷ (`test_resonance_a1_rollback.py`).
  - Hệ quả: 0.86.x không biết công tắc theo agent, công tắc brain cũ lại có hiệu lực. Vì vậy TRƯỚC khi quay về, chủ dự án tắt `Javis/resonance.json` của mọi brain (hay giữ tắt), để không có mục tiêu nào tự chạy trong lúc chuyển. Chỉ bật lại theo quyết định của chủ dự án.
  - Nâng lại lên A1 sau đó: sổ đăng ký và liên kết phiên còn nguyên. Mục tiêu tạo trong lúc chạy 0.86.x không có dòng `goal_agents` nên chờ gán, không tự chạy.
- **Khôi phục bằng `.pre-a1.bak`:** bản này chỉ có dữ liệu tới lúc nâng. Mọi mục tiêu, sự kiện, bằng chứng phát sinh sau đó KHÔNG có trong bản sao. Trước khi khôi phục, dừng server và chép riêng kho hiện tại để giữ trạng thái mới.
- Kiểm migration bằng bản sao kho có dữ liệu thật trước khi phát hành, không chạy trên kho thật.

## 6. Giao diện tối thiểu

**Trang Cộng sự, phần đầu cuộc trò chuyện với một agent:**
- Công tắc "Cộng hưởng". Khi tắt, ghi ngắn: trợ lý vẫn trò chuyện và làm việc một lần như thường.
- Nếu engine của agent chưa hỗ trợ (Grok, Antigravity), công tắc vẫn bật được nhưng có dòng cảnh báo "engine này chưa lập được mục tiêu". Engine chưa có bàn giao bản viết trong lượt thì có dòng ghi chú tương ứng.

**Khung "Mục tiêu của trợ lý"** (đọc `GET /resonance/goals?agent_key=`), mỗi mục tiêu hiện:
- cách hiểu và revision;
- tiêu chí: đạt, chưa đạt, chưa biết, kèm căn cứ ngắn;
- bản sản phẩm đang có hiệu lực (đường dẫn, mã hash rút gọn);
- đang chờ ai hay bị chặn vì gì;
- lần thức kế tiếp và lý do;
- lượt đã dùng trên hạn mức;
- nút tạm dừng, huỷ.

Không có phần trăm do model đoán. Tỷ lệ tiêu chí đã xác minh, nếu hiện, gọi đúng tên.

**Chat thường:** vẫn hiện thẻ mục tiêu khi có (thẻ đọc `/goals/{id}` theo quyền chủ dự án). Các nút trên thẻ tác động đúng mục tiêu của agent sở hữu.

**Trang cài đặt:**
- Khối Resonance theo brain đổi thành danh sách agent với công tắc.
- Mục "Chờ gán" cho mục tiêu cũ, có ô chọn agent để gán.

Mọi chuỗi giao diện qua i18n `vi.json` và `en.json`.

## 7. Không đổi ngoài Resonance

- Chat thường không thấy dòng gợi ý mục tiêu. Gọi `javis_goal` (nếu model vẫn thấy qua hub) bị từ chối với câu hướng dẫn "trả lời bình thường".
- `javis_task`, `javis_schedule`, loop, nhắc lịch, kênh ngoài, chatbot: không đổi.
- Ngữ cảnh lượt thêm khoá `agent`, `session_id`, `message_id`. Các hook plugin hiện có đọc `turn` bằng khoá cũ nên không ảnh hưởng.

## 8. Ma trận hành vi và kiểm thử

Kiểm bằng engine giả, SQLite thật, mapper SDK thật khi cần, chạy thân thật của `run_turn` như các test M2 và pilot 4.

| # | Ca | Kỳ vọng |
|---|---|---|
| 1 | Chat thường gọi `javis_goal` create, hay `POST /goal-requests` trên tin của chat thường | Từ chối trước khi ghi kho, không gọi model; hỏi đáp, việc một lần, Kanban vẫn chạy |
| 2 | Agent A bật, B tắt, cùng brain | A lập được; B bị từ chối; list của A không thấy mục tiêu của B và ngược lại |
| 3 | Hai agent cùng chạy lượt đồng thời | Mỗi tool call lấy đúng agent của lượt mình; không mượn quyền |
| 4 | Hai brain cùng slug | Mã khác, mục tiêu, sản phẩm, nguồn tin không lẫn |
| 5 | Tool truyền `agent_id` hay `goal_id` của agent khác; gọi ngoài lượt; khoá `X-Javis-Turn` giả hay đã chết | Từ chối; không lấy quyền từ lượt duy nhất đang chạy |
| 6 | Tắt agent sau khi giữ lượt, trước khi đăng, trước khi tiếp nhận bản chat, trước khi áp dụng cách làm | Không tác động; lượt đã dùng vẫn ghi đúng; đầu ra giữ để đối soát |
| 7 | Bật lại | Không mở pause, guard, huỷ; đầu ra hợp lệ được đăng không gọi model lại; worker không cần lượt chat |
| 8 | Xoá qua host rồi tạo lại cùng slug; đổi tên tay; file biến mất rồi xuất hiện lại; restart | Không tự chuyển quyền hay mục tiêu; lịch sử đọc được; `missing` cần chủ dự án xác nhận |
| 9 | Migration trên bản sao kho có mục tiêu cũ | Không mất mục tiêu hay bằng chứng; mục tiêu chưa gán không tự chạy; gán xong chạy theo công tắc; có bản `.pre-a1.bak` |
| 10 | Giao diện và API | Trạng thái khớp kho; chủ dự án vẫn xem, dừng, huỷ khi agent tắt; xác nhận cũ không áp cho bản hay revision mới |
| 11 | Đường agent đi hết vòng với engine giả: prompt có dòng gợi ý, tool có trong danh sách, ngữ cảnh lượt tới tool, bàn giao bản viết | Lập mục tiêu đúng agent, tiếp nhận bản, chờ người dùng |
| 12 | Engine chưa hỗ trợ (Grok, Antigravity, lượt không có ngữ cảnh) | Tool từ chối rõ; giao diện báo chưa hỗ trợ |
| 13 | Phiên cũ của agent đã xoá, agent mới cùng slug; restart; đổi tên tay rồi đổi lại | Phiên cũ không nhận mã mới; phiên mới nhận mã mới; đổi tên tay mất danh tính tới khi chủ dự án xác nhận. Đi qua phần gắn ngữ cảnh của `run_turn` với kho phiên thật |
| 14 | Quay về 0.86.1 trên kho đã nâng, rồi nâng lại | Mã 0.86.1 thật ghi được mọi đường chính; nâng lại giữ dữ liệu A1; mục tiêu tạo lúc quay về chờ gán; bản `.pre-a1.bak` không bị ghi đè |
| 15 | Bật agent `missing` khi cờ còn bật | Từ chối, không báo thành công, không tăng version |

**Test cũ M1 đến M5:** các test hiện bật Resonance bằng `resonance.json` sẽ chuyển sang bật agent qua sổ đăng ký bằng một helper chung. Nội dung kiểm của chúng giữ nguyên.

## 9. File, API, schema dự kiến đổi

- `server/resonance_store.py`:
  - bảng `resonance_agents`, `resonance_agent_events`, `session_agents`, `goal_agents`, `handoff_agents`; không đổi cột bảng cũ;
  - hàm đăng ký, bật, tắt, xác nhận, ghim phiên, gán;
  - lọc theo agent; sao lưu `.pre-a1.bak`.
- `server/resonance.py`:
  - `agent_gate`;
  - `_gate` kiểm agent;
  - `form_goal` và `revise_goal` nhận `agent_key` và version;
  - `handoff_after_turn` và `finish_handoff` kiểm agent;
  - `enabled_for` (brain) chỉ còn dùng cho nhãn giao diện cũ.
- `server/main.py`:
  - `run_turn` gắn agent vào ngữ cảnh lượt;
  - dòng gợi ý chỉ trong phiên agent đang bật;
  - `/agents/delete` cho agent nghỉ;
  - `_resonance_after_turn` dùng agent của lượt.
- `server/resonance_api.py`: `/resonance/agents`, `/resonance/agents/toggle`, `/resonance/agents/confirm`, `/goals/{id}/assign`; cổng của `/goal-requests`; `?agent_key=` cho danh sách.
- `server/turn_context.py`: cho phép thêm khoá vào ngữ cảnh lượt, giữ hợp đồng cũ.
- `system/plugins/javis-goal/plugin.py`: danh tính từ ngữ cảnh lượt; `visible_fn` theo lượt.
- `dashboard/`:
  - công tắc và khung tiến độ trong trang Cộng sự (`workspace.js`, hoặc file mới `resonance-agent.js`);
  - khối cài đặt;
  - `i18n/vi.json`, `i18n/en.json`.
- `tests/python/`: `test_resonance_a1_agent_scope.py` (mới) theo mục 8; cập nhật test M1 đến M5 sang helper bật agent; `route_table.json`.
- `docs/`: hướng dẫn migration và khôi phục; CHANGELOG hai thứ tiếng.

## 10. Sau A1: pilot

- **Bộ chạy pilot achieve chuyển sang phiên agent:** tạo agent tạm trong brain tạm, bật qua API chủ dự án, tạo phiên `agent:<slug>`.
- **Rà lại các phần có thể khác pilot 5:** prompt của persona agent, provider và model của agent, danh sách tool, ngữ cảnh lượt, biên nhận ghi file.
- **Thứ tự:** chứng minh bằng engine giả trước, rồi đề xuất một pilot thật với cấu hình và hạn mức riêng. Không dùng lại hạn mức pilot cũ.

## 11. Quyết định đã tự chốt, cần reviewer xem

1. Công tắc theo brain cũ không còn cấp quyền. Chỉ còn công tắc theo agent.
2. Mã agent do host cấp lúc bật lần đầu. Không ghi mã vào file agent.
3. File biến mất rồi xuất hiện lại cần chủ dự án xác nhận. Không tự nhận lại quyền.
4. Lệch `config_version` giữa lúc giữ lượt và lúc tác động thì giữ đầu ra, không đăng. Lần thức sau xét lại theo quyền hiện tại.
5. Grok và Antigravity chưa hỗ trợ trong A1 vì chưa mang khoá lượt.

Review vòng 1 đồng ý cả năm quyết định. Bổ sung theo review:
- Quyết định 2 có thêm liên kết phiên bền vững (mục 1).
- Quyết định 4 đối soát đủ mã, version, revision, guard, baseline (mục 5).
- Quyết định 5: giao diện phân biệt ba khả năng (lập mục tiêu, nhận bản chat, engine việc nền). Bảng hỗ trợ engine chỉ được nghiệm thu khi có bằng chứng qua transport thật với dịch vụ giả, không chỉ đọc ngữ cảnh lượt trong `_do_turn` giả.

## 12. Sửa sau review vòng 1 (PR #590, head trước `5ed5a9e3`)

1. **P1-1 phiên cũ nhận nhầm agent mới.** Phiên được ghim vào mã agent ở bảng `session_agents` (mục 1). `run_turn` phân giải qua liên kết đó, không tra theo slug.
2. **P1-2 quay về 0.86.x hỏng đường ghi.** Bỏ hết cột thêm vào bảng cũ; dữ liệu A1 chuyển sang bảng riêng (mục 5).
   - Kiểm bằng mã 0.86.1 thật lấy qua `git show 09f254d0`.
   - CI lấy riêng commit đó để test không bị bỏ qua.
   - Hướng dẫn quay về và khôi phục ghi đúng giới hạn của bản sao.
3. **P2-1 bật agent `missing` báo thành công.** Kiểm trạng thái trước nhánh "giá trị không đổi".
4. **Chốt phạm vi gán:** A1 chỉ gán mục tiêu chưa gán. Chuyển giữa hai agent để sau A1 (mục 5).

## 13. Sau review vòng 2 (head `241fbb5d`)

- Ba lỗi vòng 1 được xác nhận đã sửa.
- P2 mới (phiên mở trước lần bật đầu của agent tạo lại cùng tên) xử lý ở API và giao diện bằng `needs_new_session` (mục 1). Resolver không nới.
- Chốt cách dùng lại đầu ra sau tắt/bật (mục 4).
- Kế hoạch nối phần còn lại: `docs/superpowers/plans/2026-10-08-resonance-a1-integration-plan.md`.

## 14. Sửa sau review tích hợp (head trước `52d841d1`)

1. **P1-1 prompt thật của phiên trợ lý.** Dòng gợi ý (`_RESONANCE_GOAL_HINT`, một bản) nối vào `_agent_chat_prompt`, đường dựng prompt mà MỌI engine của phiên trợ lý dùng.
   - Khi trợ lý đang bật, câu "chỉ hai lối" trong khối công cụ của trợ lý đổi thành ba lối.
   - Trợ lý tắt và chat thường giữ nguyên.
2. **P1-2 file trợ lý mất.** `agent_gate` đối soát file ngay tại cổng (cùng luật tìm thư mục với `_agents_dir`).
   - File mất thì chốt `missing` dù không có lượt chat nào. Áp dụng cho scheduler, `/goal-requests`, bàn giao, đăng, phép thử.
   - `GET /resonance/agents` cũng chốt `missing` cho mã mất file.
   - File có lại vẫn cần chủ dự án xác nhận.
3. **P1-3 phép thử.** Phép thử ghim mã và version ở bảng mới `experiment_agents`; kho kiểm trong giao dịch giữ hạn mức, mỗi lượt thử và bước áp dụng.
   - Tắt hay đổi version thì phép thử dừng, hoàn phần hạn mức chưa chạy, không áp dụng.
   - Mục tiêu đã thuộc trợ lý thì mọi `begin_action` và `begin_experiment` phải mang mã; thiếu thì từ chối, không ngầm bỏ kiểm.
   - Không có đường tái cấp quyền cho kết quả phép thử sau bật lại: phải chạy phép thử mới.
4. **P2 trạng thái phiên sau tải lại.** `GET /resonance/agents?slug=&session_id=` trả trạng thái phiên theo đúng luật của `run_turn`, chỉ đọc, không ghi liên kết. Khối giao diện hỏi lại host mỗi lần mở, tải lại hay đổi phiên.
5. **Pilot** chạy trong phiên trợ lý; có chặng kiểm ba cửa không gọi model (`docs/dev/resonance-mvp-e2e-pilot-plan.md`, mục A1).

**Giới hạn còn lại:**
- Danh sách tool của hub được đệm theo brain, nên `javis_search_tools` có thể vẫn trả `javis_goal` trong lượt của trợ lý đã tắt.
- Lời gọi khi đó bị hàm xử lý từ chối (`agent_off`), không ghi gì. Danh sách tool chỉ là gợi ý (mục 4).
