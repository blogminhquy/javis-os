# Tốc độ lượt chat Claude Code và Codex (0.382.0)

Spec này viết ngày 28/10/2026, sau khi khách phàn nàn Javis chậm hơn chạy Claude Code hay Codex trực tiếp.
Mọi con số dưới đây đo thật trên máy Windows của chủ repo (Claude Code 2.1.310, Codex 0.160.0).

## 1. Vì sao chậm

| Nguyên nhân | Đo được |
|---|---|
| Mỗi lượt Claude mở một tiến trình `claude` mới rồi resume phiên | mở mới mỗi lượt 3,4 đến 4,9 s; giữ sống thì lượt sau 1,3 đến 1,6 s |
| Mỗi lượt nối lại toàn bộ MCP (hub, plugin, MCP sẵn có của máy) | 4,4 đến 5,1 s với 85 MCP, 2,4 đến 2,8 s khi tắt MCP |
| Codex không hiện chữ dần: chỉ đẩy chữ khi xong cả đoạn | khách nhìn khung trống tới hết câu |
| Codex: system prompt (khoảng 21.500 ký tự) ghép vào ĐẦU MỌI tin nhắn, kể cả lượt resume | luồng phình thêm cả prompt sau mỗi lượt |
| Danh sách tool của hub hết hạn cứng sau 60 s | khách nghỉ quá một phút là lượt sau dò lại mọi nguồn |
| Codex trên Linux: hết lượt đợi 2 s ân hạn vì nhóm tiến trình còn sống | +2 s trước `turn_done` |

Phần Javis tự làm trước engine (dựng system prompt khoảng 70 đến 80 ms, recall, ghi SQLite) nhẹ, không phải thủ phạm.

## 2. Nguyên tắc

- **Cái chia sẻ được thì chia sẻ, cái không chia sẻ được thì giữ sống CÓ TRẦN.** Không có thứ gì tăng RAM theo số hội thoại.
- **Chỉ lượt chat trực tiếp của chủ được giữ ấm.** Việc nền (loop, Kanban, nhắc hẹn, workflow, nhóm) và bot khách giữ
  nguyên đường mở tiến trình mỗi lần: chúng cần chạy song song nhiều việc, không cần nhanh từng giây.
- **Trượt thì quay về đường cũ.** Không có tiến trình ấm, cấu hình đổi, lỗi bất kỳ: chạy đúng như 0.381.
- `server/claude_sdk_engine.py` bị ghim hash bởi bằng chứng kiểm định native (`tests/python/test_plan_limits.py`), nên
  không sửa file đó; đường ấm nằm ở module riêng và dùng lại hàm của nó.

## 3. Thiết kế

### 3.1 Đo trước (mốc thời gian lượt)

`runtime_events` thêm `engine.first_output` với `{"engine", "ms", "warm"}`: số mili giây từ lúc lượt bắt đầu tới sự kiện
đầu tiên engine trả về (chữ, tool hoặc lỗi), và lượt đó có chạy trên tiến trình ấm không. Stderr in một dòng
`[turn timing]` cùng nội dung. Có số này mới chứng minh được trên máy khách bước nào giúp bao nhiêu.

### 3.2 Kho tiến trình ấm (`server/warm_pool.py`)

Một kho dùng chung cho cả Claude và Codex, theo hội thoại:

- **Khoá ô** = id hội thoại. Mỗi ô ghi **dấu vân tay cấu hình** (binary và mtime của nó, cwd, model, mức suy nghĩ, fast,
  MCP đã đấu, tài khoản, tag). Lượt sau có dấu vân tay khác thì bỏ ô cũ, mở tiến trình mới.
- **Trần theo RAM**: ngân sách = một phần tư RAM trống, tối đa 1.200 MB. Ô Claude tính 300 MB, ô Codex 80 MB (đo:
  228 MB và 57 MB). `JAVIS_WARM_BUDGET_MB` đặt tay, `0` là tắt hẳn.
- **Hết chỗ** thì đuổi ô RẢNH lâu nhất (LRU). Không bao giờ đuổi ô đang chạy lượt. Không còn ô rảnh nào để đuổi thì lượt
  đó chạy đường cũ, không chờ.
- **Rảnh quá 300 s** (`JAVIS_WARM_IDLE_S`) thì tự đóng. 300 s khớp thời hạn đệm prompt 5 phút của nhà cung cấp: quá
  mốc đó lượt sau vẫn phải nạp lại ngữ cảnh, giữ tiến trình chỉ còn đỡ phần khởi động.
- **Lỗi bất kỳ** (tiến trình chết, hết giờ, ngắt giữa chừng mà không chốt được) thì bỏ ô.
- **Mở sẵn không bao giờ đuổi ai và không bao giờ thay ô có sẵn**: lượt thật nào đã tìm ô của hội thoại trong lúc đang mở
  sẵn thì tiến trình mở sẵn bị đóng (tiến trình của lượt đó mới hơn).
- **Mở sẵn khi gõ**: dashboard gửi `{"type": "typing"}` (tối đa một lần mỗi 20 s) khi chủ bắt đầu gõ. Hội thoại vừa có ô
  bị đóng vì rảnh thì kho mở lại tiến trình bằng đúng công thức của lượt trước (đã lưu lúc trả ô), resume đúng phiên.
  Lượt thật tới có dấu vân tay khớp thì dùng luôn, không khớp thì bỏ. Mở sẵn cũng chịu trần RAM như mọi ô.
- Server tắt thì đóng mọi ô.

### 3.3 Khoá lượt cho tiến trình ấm (`turn_context.Lane`)

Engine CLI gọi hub qua HTTP với header `X-Javis-Turn`. Trước đây mỗi lượt một khoá, chết theo lượt. Tiến trình ấm nối MCP
MỘT lần nên header cố định: ô giữ một **khoá làn** cố định, đầu mỗi lượt Javis gắn khoá đó vào lượt hiện tại, hết lượt
thì gỡ. Giữa hai lượt khoá làn giải ra "không ai" (None), đúng tính chất cũ "khoá chết theo lượt".

Claude Agent SDK chạy hook và tool plugin in-process trong task nền tạo lúc `connect()`, nên chúng thừa hưởng ngữ cảnh của
lượt ĐẦU. Ô ấm vì vậy `connect()` trong một ngữ cảnh riêng mà `_CURRENT` trỏ vào binding của làn; binding đó đổi `turn`
theo từng lượt, nên `turn_context.current()` trong plugin luôn thấy lượt đang chạy.

### 3.4 Claude (`server/claude_warm.py`)

- Chỉ áp cho lượt chat dashboard của chủ, engine Claude Code qua SDK, không có `allowed_tools`, không có `trial_profile`,
  CÓ phiên để nối (lượt đầu của hội thoại mới vẫn mở tiến trình như cũ, rồi giữ lại cho lượt sau).
- System prompt KHÔNG nằm trong dấu vân tay: Claude Code nối phiên đã giữ system prompt của lượt đầu phiên (đo ở 0.345.0),
  nên tiến trình ấm không làm đổi hành vi.
- Vòng đọc sự kiện dùng lại `map_message`, `_CompletionWatch`, `tran_watchdog`, `loi_de_hieu` của `claude_sdk_engine`, và
  đăng ký client vào `_ACTIVE` để nút Dừng (`cancel_all`) vẫn ngắt được.
- Sau lượt: client chỉ được giữ khi lượt chốt bằng `ResultMessage` tốt, không còn tác vụ nền (`task_*`), không dính tranh
  token làm mới. Lượt sau lấy ô ra thì xả hàng đợi tin của SDK: còn gì ngoài ghi chú hệ thống cuối lượt (tin của tác vụ
  nền, một lượt CLI tự chạy) là bỏ ô, chạy lạnh. Ô ấm hỏng ngay lúc gửi tin thì chạy lại lượt đó bằng đường lạnh.
- Dấu vân tay gồm thêm `strict_mcp_config`, file đăng nhập `.credentials.json`, các file settings và từng `SKILL.md`.

### 3.5 Codex (`server/codex_steer.py`)

1. **Hiện chữ dần**: đọc `item/agentMessage/delta`, đẩy từng mẩu. Đoạn đã có delta thì `item/completed` không đẩy lại.
2. **Chỉ dẫn hệ thống gửi một lần**: `developerInstructions` ở `thread/start`, không ghép vào tin nhắn nữa. Đo thật: tắt
   tiến trình, mở tiến trình mới, `thread/resume` không gửi lại chỉ dẫn, model vẫn trả đúng "mã bí mật" trong chỉ dẫn. Luồng
   cũ (tạo bằng `codex exec` hay bản trước) chỉ mang chỉ dẫn ở tin nhắn đầu, mà Codex tự nén hội thoại sớm hơn ngưỡng
   xoay mạch 1 triệu token của Javis, nên luồng nào KHÔNG có trong sổ `codex_instr_threads.json` (luồng mở bằng
   `developerInstructions`) vẫn được ghép chỉ dẫn vào đầu mỗi tin như trước. Đã thử: `thread/resume` kèm chỉ dẫn mới không
   thay được chỉ dẫn cũ. Đường dự phòng `codex exec` vẫn ghép như cũ vì exec không có trường này.
3. **Giữ ấm**: ô Codex giữ `app-server` và luồng đã mở; lượt sau gửi thẳng `turn/start`, không spawn, không resume. Lượt
   nào đã chạy lệnh shell thì trả tiến trình theo đường cũ (đóng stdin, ghi nhóm tiến trình), trên mọi hệ điều hành: lệnh
   có thể còn chạy ngầm, POSIX cần đường cũ để `tien_trinh_nen` nhận nuôi, Windows thì một lần bấm Dừng sau đó
   (`taskkill /T` lên tiến trình ấm) sẽ giết luôn lệnh đó.
4. Lượt chạy trên ô ấm không ghi nhóm tiến trình, nên không dính 2 s ân hạn.

### 3.6 Hub MCP: dùng bản đã lưu, làm mới ở nền

`mcp_hub.discover_all`: bản lưu ĐỦ (không thiếu nguồn) quá 60 s nhưng chưa quá 15 phút, `mtime` kho kết nối và `epoch`
chưa đổi, thì trả ngay bản đó và làm mới ở nền (mỗi khoá một lượt làm mới cùng lúc). Bản THIẾU nguồn giữ luật cũ (10 s,
dò lại đồng bộ). Đổi kết nối vẫn làm `mtime` đổi nên không bao giờ trả danh sách cũ sau khi chủ sửa kết nối.

## 4. Không làm

- Một `app-server` dùng chung cho mọi hội thoại: giao thức cho phép, nhưng MCP hub mang header theo tiến trình, và nhận
  nuôi lệnh chạy ngầm dựa vào nhóm tiến trình riêng của lượt. Ô theo hội thoại đã có trần RAM nên không cần mạo hiểm.
- Đưa phần chọn lọc bộ nhớ/skill ra khỏi system prompt: Claude Code đã đóng băng system prompt khi nối phiên, Codex giờ gửi
  chỉ dẫn một lần, nên lợi ích còn lại không đáng đổi hành vi.

## 5. Kiểm

- `tests/python/test_warm_pool.py`: trần, LRU, rảnh, dấu vân tay, mở sẵn, khoá làn.
- `tests/python/test_codex_steer_0213.py` mở rộng: delta, `developerInstructions`, hai lượt trên một tiến trình.
- `tests/python/test_hub_swr.py`: trả bản lưu, làm mới nền một lần, bản thiếu không dùng luật mới.
- Đo lại bằng tay trên máy thật: hai lượt liên tiếp Claude và Codex, đọc `engine.first_output`.

## 6. Bản vá 0.387.0 (29/10/2026)

Thử lại trên dashboard thật (server thử cổng 7788, `JAVIS_WARM_IDLE_S=15`) thì 0.382.0 **không dùng lại tiến trình nào**:
ba lượt liền nhau đều `warm=False`. Phép thử hôm trước chạy trên mã trước vòng sửa review, nên không bắt được. Dòng log
mới `[claude warm] ...: config changed (...)` chỉ đúng thủ phạm: `credentials`.

- Claude Code tự ghi lại `.credentials.json` mỗi lần chạy, nên dấu vân tay đổi theo từng lượt. Bỏ file đó khỏi dấu vân
  tay; thay vào, `/claude/login`, `/claude/login-code` và `/claude/logout` gọi `warm_pool.POOL.drop_kind("claude")`.
  Đổi tài khoản phụ (plan_accounts) vẫn đổi `CLAUDE_CONFIG_DIR` nên vẫn nằm trong dấu vân tay.
- Codex: `openai_oauth.write_codex_auth()` ghi lại `auth.json` mỗi lượt (đóng dấu `last_refresh`). Dấu vân tay lấy
  `tokens.account_id` thay cho stat của file; ngắt ChatGPT thì `drop_kind("codex")`.
- Công thức mở sẵn sống 12 giờ thay vì 1 giờ, tối đa 200 công thức (bỏ cái cũ nhất trước).
- Log mới: `[warm pool] closed idle ...` và `[warm pool] prewarmed ...`.

Đo sau bản vá, cùng một cuộc chat:

| | lạnh | lượt liền sau | nghỉ, đóng vì rảnh, gõ rồi gửi |
|---|---|---|---|
| Claude Code | 8,6 tới 9,0 s | 1,6 s | 2,0 s |
| Codex | 14,0 s | 2,5 s | 2,6 s |

Chưa làm, có chủ ý:
- **Cuộc chat mới tinh** và **ngay sau khi server khởi động lại**: không có công thức để mở lại. Muốn mở sẵn thì phải dựng
  đúng system prompt của lượt đầu, mà prompt đó mang id phiên, khối kênh trả kết quả và ngôn ngữ dò từ chính câu hỏi.
  Các bước dựng nằm rải trong `_do_turn` của main.py; tách chúng ra là một đợt tái cấu trúc riêng. Mở sẵn bằng prompt
  của cuộc chat khác thì model nhận sai id phiên, tức kết quả việc nền gửi nhầm chỗ.
- **7 engine API**: không có tiến trình để giữ; mỗi lượt là một request HTTP từ chính server.

