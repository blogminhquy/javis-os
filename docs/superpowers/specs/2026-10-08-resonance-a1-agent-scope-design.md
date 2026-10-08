# Resonance A1: Cộng hưởng theo từng agent, công tắc và tiến độ tối thiểu (thiết kế)

- **Ngày:** 08/10/2026.
- **Nền mã:** `main` `09f254d0e4d009451dc58cb2e97788631c5acc1a` (0.86.1). Nhánh `claude/resonance-a1-agent-scope`.
- **Nguồn:** [phạm vi và lộ trình 08/10](2026-10-08-resonance-agent-scope-roadmap.md); review đề xuất A1 của ChatGPT (`exports/reviews/Resonance-A1-review-and-Claude-instructions-2026-10-08.md`, ngoài git).
- **Trạng thái:** thiết kế chờ review. Chưa code A1, chưa gọi model, chưa merge.

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
- **Đổi tên:** chưa có thao tác có quản lý. Đổi tên tay xem như file cũ biến mất (`missing`) cộng một agent chưa đăng ký. Chủ dự án chuyển mục tiêu bằng thao tác gán lại (mục 6), có dấu vết.
- **Hai brain cùng slug:** khác `brain_id` nên khác dòng, khác mã. Mọi truy vấn đều lọc theo cả hai.

## 2. Ràng buộc lời gọi tool với lượt và agent

Review chỉ ra: sổ `luot_dang_chay.doan_luot(vault)` đoán "lượt duy nhất của brain", không chứng minh ai gọi tool. A1 bỏ cách đó cho Resonance và dùng `turn_context` (có từ 0.85.8).

**Hạ tầng sẵn có:**
- Mỗi lượt gắn một ngữ cảnh lượt bằng `ContextVar`.
- Engine trong tiến trình (engine API, plugin trong SDK Claude) đọc thẳng ngữ cảnh đó.
- Engine CLI gọi hub qua HTTP (Codex) mang khoá `X-Javis-Turn`, hub đổi khoá về đúng ngữ cảnh. Khoá giả, khoá cũ hay thiếu khoá đều ra "không có lượt". Khoá chết theo lượt.

**Thay đổi:**
- `run_turn` (dashboard) gắn thêm vào ngữ cảnh lượt:
  - `session_id` và `message_id` của tin người dùng;
  - khối `agent = {"key", "slug", "config_version"}`, chỉ khi phiên có kênh `agent:<slug>` và sổ đăng ký có dòng `active` của đúng `(brain_id, slug)`. Ngược lại `agent = None`.
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
| `POST /goal-requests` | chủ dự án, brain bật | chủ dự án; tin phải thuộc phiên `agent:<slug>` của agent đang bật; mục tiêu thuộc agent đó |
| Scheduler (`tick` → `advance` → `_gate`) | công tắc brain | `goals.agent_key` của mục tiêu: rỗng thì `blocked/unassigned`; agent không `active` hay tắt thì `blocked/agent_off`. Kiểm lại bằng code, không gọi model. Không cần lượt chat nào đang sống |
| Bàn giao bản viết trong lượt (`finish_handoff`) | công tắc brain, pause, guard | thêm: agent của mục tiêu còn bật và version bằng version ghi lúc lập hay sửa trong lượt |
| Đăng sản phẩm (`_publish`), kết luận thành công | `_gate` | `_gate` gồm cổng agent; lệch version so với lúc giữ lượt (`begin_action` ghi version vào intent) thì giữ đầu ra trong vùng làm việc, không đăng |
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
- **Bật lại:** đối soát phần dở theo cơ chế M3 sẵn có. Đầu ra hợp lệ của đúng revision được đăng qua `_publish_latest` khi cổng mở, không gọi model lại.

## 5. Kho và migration

**Thay đổi schema** (chỉ thêm, không xoá hay đổi cột cũ):
- `goals.agent_key TEXT` (cho phép rỗng).
- Bảng `resonance_agents`, `resonance_agent_events`.
- `actions.intent_json` ghi thêm `agent_config_version`.
- `handoffs` ghi thêm `agent_key` và `agent_config_version`.

**Mục tiêu cũ** (đã có trước A1, `agent_key` rỗng):
- Lịch sử, bằng chứng, revision giữ nguyên.
- Trạng thái chạy thành `blocked/unassigned` ở lần cổng kế tiếp. Không tự chạy, không tự gán theo tên gần giống hay phiên gần nhất.
- Chủ dự án gán một lần bằng `POST /goals/{id}/assign {agent_key, expected_revision}`.
  - Chỉ gán cho agent `active` cùng brain.
  - Ghi sự kiện `agent_assigned` (ai gán, từ đâu sang đâu).
  - Gán xong thì cổng mở theo công tắc của agent mới.

**Sao lưu và khôi phục:**
- Lần đầu mở kho bằng mã A1, host chép `resonance.sqlite3` thành `resonance.sqlite3.pre-a1.bak` cạnh file gốc (chỉ một lần, không ghi đè bản sao đã có).
- Rollback về 0.86.x: mã cũ bỏ qua cột và bảng mới (SQLite chấp nhận), dữ liệu còn nguyên. Mục tiêu tạo sau A1 vẫn đọc được. Khi đó công tắc brain cũ lại có hiệu lực theo luật cũ: tài liệu migration ghi rõ hệ quả này.
- Khôi phục tay bằng bản `.pre-a1.bak` được mô tả trong hướng dẫn migration.
- Kiểm bằng bản sao kho có dữ liệu thật trước khi phát hành, không chạy trên kho thật.

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

**Test cũ M1 đến M5:** các test hiện bật Resonance bằng `resonance.json` sẽ chuyển sang bật agent qua sổ đăng ký bằng một helper chung. Nội dung kiểm của chúng giữ nguyên.

## 9. File, API, schema dự kiến đổi

- `server/resonance_store.py`:
  - bảng `resonance_agents`, `resonance_agent_events`; cột `goals.agent_key`;
  - hàm đăng ký, bật, tắt, xác nhận, gán;
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
