# Trang "Cộng sự": chat với trợ lý và quy trình, lưu lịch sử chạy

Ngày: 2026-09-15. Trạng thái: đã duyệt (chủ dự án chốt trong chat).

## 1. Vấn đề

- Trang Trợ lý hiện chỉ là danh sách thẻ (Sửa, Xuất, Xoá). Không chat được với một trợ lý.
- Trang Quy trình bấm Chạy thì hiện hộp `prompt()` của trình duyệt, kết quả stream vào một
  ngăn kéo tạm (`#runDrawer`). Đóng ngăn kéo là mất, không lưu ở đâu.
- Không có kho lịch sử chạy. Hỏi Javis "quy trình chạy gần nhất ra sao" thì Javis không có
  gì để tra, nên trả lời trống.

## 2. Quyết định đã chốt

1. Gộp hai trang Trợ lý và Quy trình thành MỘT trang "Cộng sự" (id máy: `workspace`), thay
   thế hai mục cũ trên thanh bên. Trong trang có nút chuyển Trợ lý | Quy trình.
2. Chat được với cả trợ lý lẫn quy trình, cùng một khung chat.
3. Trong khung chat của quy trình, mỗi tin nhắn là MỘT lần chạy mới; kết quả lần chạy trước
   trong cùng hội thoại được nối vào đầu vào làm ngữ cảnh, để tin góp ý ("sửa đoạn 2 ngắn
   lại") vẫn hiểu.
4. Danh sách quy trình xếp theo lần chạy gần nhất lên đầu. Danh sách trợ lý xếp theo lần chat
   gần nhất lên đầu. Chưa từng chạy/chat thì xếp sau, theo tên.
5. Hướng kỹ thuật A: mọi thứ là một phiên chat. Chat với trợ lý và chạy quy trình đều là một
   lượt WebSocket trên phiên có kênh riêng. Trang mới mượn khung chat có sẵn của app.

## 3. Giao diện

Bố cục ba cột, theo bản concept `javis-workspace-concept.html`:

- Cột trái: nút chuyển Trợ lý | Quy trình, ô tìm, ô lọc theo `group`, danh sách, nút Tạo
  mới, nút Javis Store (mở kho có sẵn qua `JavisPacks.moKho`, lọc đúng loại). Mỗi dòng: icon
  (trợ lý dùng icon `bot`, quy trình dùng icon `workflow`), tên, nhóm và vai trò/số bước.
- Cột giữa: khung chat MƯỢN từ app bằng `_borrowChatNodes` (đúng cách trang Trò chuyện đang
  làm). Thanh đầu có tên cộng sự, dòng phụ (nhóm và trạng thái với trợ lý; "Quy trình, N
  bước" với quy trình), nút Hội thoại mới, nút mở cột phải trên màn hẹp.
- Cột phải, khi chọn TRỢ LÝ: form cài đặt inline với đúng các ô của trình sửa hiện tại (tên,
  nhóm, vai trò, model, kỹ năng, hướng dẫn = thân file), nút Lưu, nút Xuất, nút Xoá, và mục
  "Hội thoại gần đây" (các phiên kênh `agent:<slug>`, bấm để mở).
- Cột phải, khi chọn QUY TRÌNH: tiêu đề, dải tiến độ, danh sách bước kèm trợ lý phụ trách và
  trạng thái (chờ, đang làm, xong, lỗi), mục "Lịch sử chạy" (các lần chạy gần nhất, bấm để mở
  đúng hội thoại của lần đó), nút Sửa các bước (mở modal sửa quy trình hiện có), Xuất, Xoá.
- Màn hẹp (dưới 900px): cột trái và cột phải thành ngăn kéo, khung chat chiếm toàn màn.
- Chữ hiển thị lấy từ từ điển `dashboard/i18n/vi.json` và `en.json`, tiếng Việt có dấu.

Đăng ký trang ở đúng ba chỗ: `RAIL_ITEMS` (console.js), `PAGES` (ui-actions.js), `PAGES`
(server/ui_targets.py), cộng `VIEW_ICON`, `RAIL_GROUPS` (nhóm `nang_luc`), `VIEW_META`, nhánh
trong `renderPage`. Bỏ `agents` và `workflows` khỏi cả ba danh sách; các bí danh giọng nói
("tro ly", "quy trinh", "agent", "workflow"...) trỏ về `workspace`. Các chỗ đang điều hướng
tới `agents`/`workflows` (chatbots.js, packs.js) đổi sang `workspace`. Trang `skills` giữ
nguyên.

## 4. Phiên chat theo cộng sự

- Kho phiên `conversations.db` đã có cột `channel`. Dùng giá trị `agent:<slug>` và
  `workflow:<slug>`.
- Thêm `POST /sessions/new` nhận `brain` và `channel`, trả `{id}`. Trang Cộng sự gọi nó khi
  bấm Hội thoại mới hoặc khi chọn một cộng sự chưa có phiên, rồi `openStoredSession(id)`.
  Phiên trợ lý ghim sẵn model của trợ lý (`model`, `model_provider` trong frontmatter) nếu có.
- `GET /sessions` thêm tham số `channel`: giá trị cụ thể lọc đúng kênh đó; bỏ trống thì
  KHÔNG trả các kênh có tiền tố `agent:` hay `workflow:` (thanh lịch sử trang Trò chuyện
  không lẫn phiên cộng sự). `list_sessions` trong sessions.py nhận tham số tương ứng.
- Tiêu đề tự đặt như phiên thường.

## 5. Chat với trợ lý

- Trong bộ điều phối lượt (`_do_turn` trong main.py), tách một hàm nhỏ
  `_persona_cua_phien(row, brain)` trả `(kind, slug)` từ cột `channel` của phiên. Hàm này
  test được độc lập.
- Nếu kind là `agent`: system prompt của lượt là prompt của chính trợ lý đó, dựng bằng
  `_agent_sysprompt` từ `_workflow_agent_helpers` (đã gồm bộ nhớ riêng
  `memory/agents/<slug>/MEMORY.md` và luật `JAVIS_LESSON`). Bỏ lớp prompt Javis (CLAUDE.md,
  bộ nhớ chủ, khối kênh) và bỏ bộ nén ngữ cảnh (`_subscription_system_prompt` trả về prompt
  trợ lý). Tool vẫn qua hub như lượt thường.
- Cuối lượt: bóc `JAVIS_LESSON` khỏi câu trả lời và ghi vào bộ nhớ trợ lý (dùng `_learn`),
  ghi nhật ký `memory/agents/<slug>/runs/` (dùng `_log_agent_run`), rồi lưu phiên qua
  `_persist_turn` như lượt thường.
- Trợ lý không còn file: lượt trả khung `error` "Trợ lý <slug> không còn trong brain này",
  không rơi về Javis.

## 6. Chạy quy trình như một lượt chat

- Nếu kind là `workflow`: bộ điều phối không gọi `run_turn` mà gọi `run_workflow_turn`
  (hàm mới, cùng chữ ký, đăng ký vào `_CHAT_RUNTIME` như lượt thường, nên nút Dừng và F5
  giữa chừng hoạt động).
- `run_workflow_turn`:
  1. Đầu vào = tin của người dùng. Nếu trong phiên có lần chạy trước đã xong, nối thêm khối
     `\n\n# Kết quả lần trước\n<kết quả cuối, cắt 8000 ký tự>` vào đầu vào.
  2. Lặp `execute_workflow(brain, slug, input, tools=None, session_id=conv_sid)`.
  3. Với mỗi sự kiện: `start`, `step_start`, `step_done`, `step_error`, `step_verify*`,
     `step_retry`, `step_model`, `wait_user`, `escalation`, `replan`, `resume` được đẩy nguyên
     dạng qua khung WebSocket mới `{"type":"wf_event", ...}` (cột phải vẽ tiến độ). Đồng thời
     `step_start` đẩy khung `status` "Bước i/N: <tên trợ lý> đang làm..." để khung chat hiện
     chip hoạt động. `step_text` của bước CUỐI đẩy thành khung `stream` để bong bóng hiện dần;
     các bước trước không stream vào bong bóng (đã có ở cột phải).
  4. `done`: tin trả lời lưu vào phiên = dòng đầu "Lần chạy #N · K bước · T giây" (N là số
     thứ tự lần chạy trong phiên) + dòng trống + kết quả bước cuối. Gửi `turn_done`.
  5. `error`: tin trả lời = "Quy trình dừng ở bước i (<tên trợ lý>): <lỗi>". Vẫn lưu vào
     phiên, vẫn gửi `turn_done`. Không bao giờ kết thúc mà không có tin.
  6. `wait_user`: tin trả lời lưu vào phiên = "Quy trình đang chờ duyệt bước <node>:
     <prompt>. Bấm Duyệt ở cột phải để chạy tiếp." (không có khối điều khiển nào trong tin).
     Khung `wf_event` mang `task_id`, `node`, `code`; cột phải vẽ nút Duyệt. Bấm Duyệt gửi
     tin WebSocket `{"type":"wf_resume", session_id, task_id, node, code}`; server chạy
     `execute_workflow_resume` qua cùng `run_workflow_turn` (nhánh resume) nên kết quả tiếp
     theo cũng là một tin trong cùng phiên và cũng được ghi vào kho lịch sử (cập nhật bản ghi
     `waiting` thành `done`/`error`).
- Kanban vẫn gọi `execute_workflow` như cũ; phần lưu lịch sử nằm trong `execute_workflow`
  nên Kanban, nhắc hẹn, loop đều được ghi.

## 7. Kho lịch sử chạy

Module mới `server/workflow_runs.py`, SQLite tại `<JAVIS_STATE_DIR>/workflow_runs.sqlite3`
(giống cách `task_store.py`). Một bảng `workflow_runs`:

| cột | ý nghĩa |
|---|---|
| id | uuid hex |
| brain | khoá brain |
| slug, name | quy trình |
| session_id | phiên chat nếu chạy từ trang Cộng sự, rỗng nếu từ Kanban |
| source | `web`, `kanban`, `reminder`, `loop`, `other` |
| input | đầu vào, cắt 4000 ký tự |
| status | `running`, `done`, `error`, `waiting` |
| started_at, finished_at | epoch |
| steps_json | danh sách bước: i, agent, task (cắt 2000), output (cắt 4000), verified, error |
| output | kết quả cuối, cắt 20000 ký tự |
| error | thông điệp lỗi |

API:
- `bat_dau(brain, slug, name, input, source, session_id) -> run_id`
- `ghi_buoc(run_id, i, **fields)`, `ket_thuc(run_id, status, output, error)`
- `gan_nhat(brain, slug=None, limit=20)`, `lay(run_id)`
- `lan_chay_moi_nhat_theo_slug(brain) -> {slug: started_at}` cho việc sắp xếp danh sách.

`execute_workflow` bọc bằng một generator tee: mở bản ghi ở đầu, cập nhật theo từng sự kiện,
đóng ở `done`/`error`/`wait_user` (waiting). Sự kiện `start` mang thêm `run_id`. `source`
suy từ tham số mới `source=""` của `execute_workflow` (Kanban truyền `kanban`, trang Cộng
sự truyền `web`, mặc định `other`).

HTTP:
- `GET /workflows/runs?slug=&brain=&limit=` trả danh sách (không kèm `output` đầy đủ, chỉ
  200 ký tự đầu).
- `GET /workflows/runs/{id}` trả một bản ghi đầy đủ.
- `GET /workflows` trả thêm `last_run_at` cho từng quy trình; `GET /agents` trả thêm
  `last_chat_at` (updated_at của phiên `agent:<slug>` mới nhất). Trang Cộng sự sắp xếp theo
  hai trường này, giảm dần, rỗng xếp sau theo tên.

## 8. Javis biết về lần chạy gần nhất

- Plugin hệ thống mới `system/plugins/javis-workflow/` (plugin.yaml + plugin.py) với tool
  `javis_workflow`, `min_mode: readonly`. Op `runs` (tham số `slug` tuỳ chọn, `limit` mặc
  định 10) trả danh sách gọn; op `show` (`id`) trả bản ghi đầy đủ gồm các bước và kết quả.
- `_javis_capability_summary` thêm một dòng sau dòng `Workflows:`:
  "Lần chạy quy trình gần nhất: <tên> lúc <giờ ngày> (<trạng thái>). Xem chi tiết hay các
  lần khác bằng tool javis_workflow (op=runs, op=show)." Không có lần chạy nào thì bỏ dòng.

## 9. Kiểm thử

- Python: `tests/test_workflow_runs.py` (kho: bắt đầu, ghi bước, kết thúc, gần nhất, cắt độ
  dài); test hai endpoint `/workflows/runs`; test plugin `javis_workflow`; test
  `_persona_cua_phien`; test `list_sessions` lọc kênh; test `run_workflow_turn` với
  `execute_workflow` giả (mock) kiểm tra đủ tin lưu vào phiên ở ba ca done/error/wait_user và
  đầu vào có nối "Kết quả lần trước".
- JS: `tests/test_ui_actions.js` cập nhật danh sách trang; test bí danh trong
  `tests/test_ui_targets.py` (nếu có) trỏ về `workspace`.
- Tay: chạy server cục bộ, mở trang Cộng sự, chat với một trợ lý, chạy một quy trình, F5 giữa
  chừng, xem lịch sử chạy, hỏi ở khung chat chính "quy trình chạy gần nhất ra sao".

## 10. Ngoài phạm vi

- Chợ mới: dùng Javis Store có sẵn.
- Avatar màu và hình dạng theo concept: dùng icon Lucide đang có.
- Sửa bước quy trình inline ở cột phải: giữ modal hiện có.
- Chạy quy trình từ khung chat chính bằng tool: vẫn đi đường Kanban `wf:<slug>` như cũ.

## 11. Tài liệu và phiên bản

- Cập nhật `docs/07-agents-va-workflows.md` theo trang mới.
- CHANGELOG cho người đọc trên điện thoại: 3 đến 4 gạch đầu dòng nói người dùng thấy gì khác.
- Bump VERSION theo số kế tiếp trên origin/main (fetch trước).
