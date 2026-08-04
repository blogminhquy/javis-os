# Spec: Javis CLI

> Bản spec dev, viết 2026-08-03 trên nền v0.16.1. Mục tiêu: đưa Javis ra terminal mà KHÔNG
> nhân bản runtime, bằng cách coi CLI là một KÊNH thứ ba bên cạnh dashboard và Telegram.
>
> **Trạng thái: ĐÃ TRIỂN KHAI ĐỦ 4 PHASE ở v0.17.0** (2026-08-04). Ba chỗ lệch so với bản
> spec này, ghi lại ngay đây thay vì để người đọc tự đối chiếu:
>
> - **Phụ thuộc chỉ còn `httpx`, bỏ `rich`.** Xem mục 6.
> - **`render.py` là một file phẳng**, không tách thư mục `commands/` thành sáu file. Cả CLI
>   gói gọn trong năm file; chia nhỏ hơn nữa là thêm chỗ để lạc chứ không thêm gì.
> - **Ba câu hỏi ở mục 8 đã tự chốt** theo phương án tốt nhất, ghi ngay tại mục đó.

## 1. Quyết định cốt lõi và vì sao

**Javis CLI là CLIENT MỎNG, không phải agent độc lập.**

Javis hôm nay là một máy chủ 43 nghìn dòng Python. Giá trị của nó nằm ở brain trên đĩa, trung
tâm MCP, loop, việc Kanban, nhắc hẹn và runtime tiết kiệm token. Gần như toàn bộ những thứ đó
đòi một tiến trình SỐNG DÀI: loop chạy theo chu kỳ, nhắc hẹn chờ tới giờ, hub giữ kết nối MCP,
kho capability giữ registry. Một CLI gõ xong là thoát không phải chỗ cho chúng.

Viết "CLI tự chạy, không cần server" nghĩa là chép lại từng đó thứ sang một bản thứ hai. Đó
đúng là cái bẫy vừa mắc ở 0.15.0 với cây thư mục (viết bản thứ hai của thứ đã có, rồi hai bản
trôi lệch), nhưng ở quy mô gấp trăm lần. **Không làm.**

Cái làm phương án client mỏng rẻ hơn nhiều so với cảm giác ban đầu: Javis ĐÃ CÓ khái niệm
kênh. `channel_context.build_channel_block(source, meta, ...)` dựng khối ngữ cảnh theo kênh,
và `server/telegram_bot.py` được tách rời hẳn khỏi lõi - `main.py` chỉ cấp cho nó `answer_fn`
và `command_fn`. Telegram là kênh thứ hai. **CLI là kênh thứ ba, đi qua đúng lõi đó.**

## 2. Hai cái lợi, và cái thứ hai lớn hơn

**Lợi trực tiếp.** Gõ thẳng trong terminal, đưa vào đường ống Unix, cắm cron, hỏi brain trên
VPS từ laptop mà không mở trình duyệt.

**Lợi chiến lược: câu chuyện cài đặt.** Cửa vào Javis hôm nay là "dựng Docker trên VPS" - một
rào cản lớn với người mới. `pipx install javis-cli` rồi gõ `javis` là cửa nhẹ hơn hẳn. Với
lượng người đã fork repo, đây là đòn bẩy đáng giá hơn bản thân sự tiện tay.

## 3. Hiện trạng: bốn chỗ đang thiếu

Đã soi mã, không đoán.

**3.1. Không có đường chat qua HTTP.** Chat chỉ đi qua `@app.websocket("/ws")` (main.py:6817)
và đường long-polling của Telegram. Không có endpoint nào nhận một câu hỏi rồi trả một câu trả
lời. Hôm nay `curl` một câu hỏi vào Javis là không làm được.

**3.2. Xác thực chỉ nhận cookie.** `_auth_guard` (main.py:163) kiểm
`cfgmod.valid_session(request.cookies.get("javis_session"))`, và `/ws` cũng đọc `ws.cookies`.
Không có token cho client ngoài trình duyệt.

Có sẵn MỘT tiền lệ đúng hướng: `/hub/mcp` xác thực bằng `Bearer` với `hub_token()`
(mcp_hub.py:46) - token sinh ngẫu nhiên, lưu ở `STATE_DIR/.hub_token`, `chmod 600`, so bằng
`secrets.compare_digest`. Thiết kế token cho CLI đi theo tiền lệ này nhưng phải NHIỀU token,
THU HỒI được, và BĂM khi lưu.

Một chi tiết thuận lợi: `_csrf_guard` chạy TRƯỚC `_auth_guard` và cố ý bỏ qua client không
phải trình duyệt (không gửi `Origin`). CLI vì vậy không vướng CSRF.

**3.3. Không có đóng gói.** Repo không có `pyproject.toml`, không có `console_scripts`. Đường
chạy hiện tại là `.bat`, `.sh`, `.vbs` và Docker.

**3.4. Chưa có kênh `cli` trong hợp đồng đầu ra.**
`context_compiler.ContextCompiler._channel_contract` và `_output_contract_text` mới biết
`telegram` và `dashboard`. Thiếu nhánh `cli` thì câu trả lời ra định dạng của web: bảng
markdown, ảnh nhúng `![](...)`, link tương đối - vô nghĩa trong terminal.

## 4. Phạm vi

### 4.1. Có làm

- `POST /chat` một lượt (đồng bộ) và `POST /chat/stream` (SSE) cho phiên tương tác.
- Token cá nhân: tạo, liệt kê, thu hồi. Băm khi lưu.
- Gói `javis-cli` cài bằng `pipx`/`uvx`, lệnh `javis`.
- Kênh `cli` trong `channel_context` + hợp đồng đầu ra hợp terminal.
- Lệnh vận hành gọi endpoint SẴN CÓ: việc Kanban, phiên hội thoại, brain, loop, phiên bản.

### 4.2. KHÔNG làm, kể cả khi bị thúc

- **Không** agent độc lập chạy không cần server.
- **Không** nhân bản runtime tiết kiệm token, MCP hub hay bộ định tuyến skill sang CLI.
- **Không** bật token mặc định. Chưa ai tạo token thì không có token nào tồn tại.
- **Không** cho token đi qua query string trong URL (rò vào access log, lịch sử shell).

## 5. Thiết kế chi tiết

### 5.1. Token cá nhân

**Vì sao token chứ không dùng lại session:** session sinh ra cho trình duyệt, lưu trong
`.sessions.json` dạng `{token: created_ts}` với TTL 30 ngày và không có tên, không thu hồi
riêng lẻ được. Một credential dán vào máy khác cần: có tên để biết nó của máy nào, thu hồi
được từng cái, và không bao giờ nằm ở dạng đọc được trên đĩa.

**Mức quyền:** v1 token có quyền NGANG session dashboard. Nói thẳng chứ không giả vờ có phân
quyền: đây không phải mức quyền mới, chỉ là loại credential mới cho đúng cái quyền chủ máy
đã có. Phân quyền theo scope (`chat` với `admin`) để dành cho bản sau, và chỉ làm khi có nhu
cầu thật.

**Lưu trữ.** `STATE_DIR/.api_tokens.json`, `chmod 600`, mỗi mục:

```json
{
  "id": "tok_a1b2c3",
  "name": "laptop nhà",
  "hash": "<sha256 của token>",
  "prefix": "jvs_a1b2",
  "created_at": 1754246400.0,
  "last_used_at": 0.0
}
```

Token thô dạng `jvs_<43 ký tự token_urlsafe>`, **hiện đúng MỘT lần** lúc tạo. Về sau chỉ còn
`prefix` để người dùng nhận ra token nào là token nào.

**Endpoint** (tất cả nằm sau `_auth_guard`, tức phải đăng nhập bằng session mới tạo được token
- không cho phép dùng token để đẻ token, chặn chuỗi leo thang):

- `POST /auth/tokens` (form `name`) → `{"token": "jvs_...", "id": ..., "prefix": ...}`
- `GET /auth/tokens` → danh sách, KHÔNG có `hash`
- `POST /auth/tokens/revoke` (form `id`) → `{"ok": true}`

**Kiểm token trong `_auth_guard`.** Thêm một nhánh SAU nhánh cookie:

```
session hợp lệ  -> cho qua (như cũ)
Authorization: Bearer jvs_... hợp lệ -> cho qua, cập nhật last_used_at
còn lại -> 401 như cũ
```

So sánh bằng `secrets.compare_digest` trên SHA-256, không so chuỗi thô.

**Chống dò.** Đếm số lần sai theo IP trong cửa sổ trượt; quá 10 lần trong 5 phút thì trả 429
cho IP đó trong 15 phút. Ghi nhật ký mọi lần sai vào `STATE_DIR/auth_audit.jsonl` với IP,
thời điểm, `prefix` đã thử (không ghi token thô).

**WebSocket.** `/ws` nhận thêm header `Authorization`. KHÔNG nhận qua query string. Trình duyệt
không đặt được header cho WS nên vẫn dùng cookie như cũ; CLI thì đặt được.

### 5.2. `POST /chat` - một lượt, đồng bộ

Dùng lại ĐÚNG lõi mà Telegram đang chạy hằng ngày (`_tg_answer`, main.py:8711), nên không đẻ
thêm một đường dispatch thứ ba. Quy ước trả về của lõi đó đã rõ: **dict = câu trả lời thật
(đáng lưu), chuỗi = thông báo lỗi (không lưu)**.

Request:

```
POST /chat
  message   (bắt buộc)
  brain     (mặc định: brain đang chọn ở Settings)
  session   (id phiên; thiếu thì tạo phiên mới và trả id về)
```

Response:

```json
{
  "text": "...",
  "session": "sess_...",
  "engine": "ollama",
  "model": "gpt-oss:120b-cloud",
  "ctx_path": "fast",
  "ctx_in": 1288
}
```

`ctx_path` và `ctx_in` lấy đúng từ `_ctx_frame` - CLI in được dòng "Tức thì · 1.3k token" y như
dashboard.

**Về thời gian chờ.** Một lượt agentic có thể chạy vài phút. Endpoint này KHÔNG đặt trần thời
gian riêng; client tự chọn. Với phiên tương tác thì dùng `/chat/stream` bên dưới.

### 5.3. `POST /chat/stream` - SSE cho phiên tương tác

Cùng tham số, trả `text/event-stream`. Mỗi gói là một dòng `data: {...}` bọc CHÍNH các gói mà
WebSocket đang gửi cho dashboard, nên không phát minh giao thức thứ hai. Các loại gói đang có
trong `main.py`: `status`, `stream`, `tool_call`, `tool_result`, `response`, `error`,
`system`, `workflow`, `wait_user`, và nhóm `step_*` của workflow.

CLI chỉ cần hiểu bốn loại đầu tiên; loại lạ thì bỏ qua im lặng chứ không vỡ - đây là luật bắt
buộc để server thêm loại gói mới không làm chết CLI cũ.

### 5.4. Kênh `cli`

`channel_context.build_channel_block("cli", meta)` với `meta` gồm `host` (tên máy) và `tty`
(có phải terminal thật không). Khối này nói cho Javis biết nó đang trả lời qua terminal.

Hợp đồng đầu ra cho kênh `cli` (thêm nhánh vào `_channel_contract` và `_output_contract_text`):

- Không bảng markdown, không HTML.
- Không nhúng ảnh; có ảnh thì in ĐƯỜNG DẪN tuyệt đối.
- Đoạn văn ngắn, xuống dòng ở 100 cột.
- Khối mã vẫn dùng dấu ba backtick (CLI tô màu được).

### 5.5. Gói CLI

Thư mục `cli/` trong repo, tách hẳn khỏi `server/`:

```
cli/
  pyproject.toml         # tên gói javis-cli, lệnh javis
  javis_cli/
    __init__.py
    __main__.py          # điểm vào, phân tích tham số
    config.py            # đọc/ghi ~/.javis/config.json
    client.py            # HTTP + SSE, gắn Bearer
    render.py            # gói -> terminal (màu, spinner, dòng ngữ cảnh)
    commands/
      chat.py  task.py  brain.py  loop.py  status.py
```

Phụ thuộc tối thiểu: **chỉ `httpx`**. Bản spec ban đầu tính thêm `rich`, nhưng lúc viết thật
thì hoá ra không cần: cả CLI dùng đúng bốn mã màu ANSI và một dòng trạng thái, đủ gọn để viết
tay trong `render.py`. Kéo `rich` về là bắt người dùng tải một thư viện dựng bảng và cây thư
mục cho terminal, trong khi kênh CLI có luật CẤM bảng. Đã bỏ.

**Không** kéo `fastapi`, `uvicorn` hay bất cứ thứ gì của server vào - gói CLI phải cài được
trên máy chưa từng có Javis.

Cấu hình ở `~/.javis/config.json`, `chmod 600`:

```json
{
  "profiles": {
    "vps": {"url": "https://javis.example.com", "token": "jvs_...", "brain": "My Bullet Journal"}
  },
  "default": "vps"
}
```

Biến môi trường `JAVIS_URL`, `JAVIS_TOKEN`, `JAVIS_PROFILE` đè lên file - để cắm vào CI và
Docker mà không phải mount file.

### 5.6. Bộ lệnh

```
javis "câu hỏi"              một lượt, in stdout, pipe được
javis chat                   phiên tương tác (SSE)
javis login <url>            dán token, thử kết nối, lưu profile
javis status                 phiên bản, bộ não đang chạy, mức tiết kiệm
javis task add "..."         giao việc Kanban
javis tasks                  liệt kê việc
javis brain ls [thư mục]     duyệt brain
javis brain cat <file>       in nội dung file
javis loops                  liệt kê loop
```

Từ `status` trở xuống đều gọi endpoint SẴN CÓ (`/version`, `/runtime/diagnostics`,
`/kanban/task`, `/files/list`, `/files/read`), không cần thêm gì ở server.

Quy ước Unix bắt buộc: câu trả lời ra **stdout**, mọi thứ khác (spinner, trạng thái, dòng ngữ
cảnh) ra **stderr**, mã thoát khác 0 khi lỗi. Thiếu ba thứ này thì `javis "..." > file.md` sẽ
dính rác và cả CLI thành vô dụng cho việc kịch bản hoá.

## 6. Kế hoạch theo giai đoạn

Mỗi giai đoạn tự nó dùng được, và có thể dừng lại sau bất kỳ giai đoạn nào.

### Giai đoạn 0 - `POST /chat` (nửa ngày)

Chỉ thêm endpoint, chưa có CLI. Xong bước này đã `curl` được và cắm cron được.

Đạt khi: `curl -X POST .../chat -d 'message=chào'` trả về câu trả lời thật; lượt đó xuất hiện
ở `/sessions` và trong `brain/Memory/conversations` y như lượt Telegram; test kèm đột biến
chứng minh nó dùng chung lõi chứ không đẻ đường dispatch thứ ba.

### Giai đoạn 1 - Token cá nhân (1-2 ngày)

Phần nhạy cảm nhất của cả kế hoạch: nó mở thêm một cửa vào máy chủ đang phơi ra Internet.

Đạt khi: tạo/liệt kê/thu hồi chạy; token băm khi lưu và không có đường nào đọc lại được thô;
`_auth_guard` nhận Bearer; chặn dò hoạt động; test đột biến gồm ít nhất "so chuỗi thô thay vì
compare_digest", "quên băm", "token đã thu hồi vẫn vào được", "dùng token để tạo token".

### Giai đoạn 2 - CLI thật (2-3 ngày)

`javis "..."`, `javis chat`, `javis login`, kênh `cli`, đóng gói, `POST /chat/stream`.

Đạt khi: cài bằng `pipx` trên máy sạch rồi hỏi được brain trên VPS; `javis "..." | wc -l` ra
số đúng (không rác ở stdout); gói lạ không làm vỡ CLI.

### Giai đoạn 3 - Lệnh vận hành (2-3 ngày)

Việc, brain, loop, trạng thái. Không thêm endpoint mới.

### Giai đoạn 4 - `javis up`, tuỳ chọn (chưa ước lượng)

CLI tự bật server localhost nếu chưa chạy rồi tự gắn vào. Vẫn MỘT server, MỘT brain; CLI chỉ
là thứ khởi động nó. Đây mới là thứ đổi được cửa vào sản phẩm, nhưng cũng là giai đoạn dễ phình
nhất nên tách hẳn ra và chỉ làm khi ba giai đoạn trên đã đứng vững.

## 7. Rủi ro và cách chặn

**Mở thêm cửa vào máy chủ công khai.** Đây là rủi ro lớn nhất. Chặn bằng: token băm khi lưu,
thu hồi được, chặn dò theo IP, ghi nhật ký, không cho token đẻ token, và không có token nào
tồn tại cho tới khi chủ máy tự tạo.

**CLI và dashboard trôi lệch.** Chặn bằng nguyên tắc CLI chỉ được gọi endpoint có sẵn, và gói
SSE bọc chính gói WebSocket. Mọi tính năng mới vào server là CLI thấy ngay, không phải sửa hai
chỗ.

**Gói CLI phình theo server.** Chặn bằng thư mục `cli/` tách hẳn và luật phụ thuộc: chỉ
`httpx`. Có test soát ĐÚNG dòng `dependencies` trong `pyproject.toml` (không quét cả file -
chính lời chú thích ở đó có nhắc tên các gói bị cấm, quét cả file là test tự bắt chú thích của
mình; đã dính đúng bẫy này một lần ở 0.14.3).

**Người dùng tưởng CLI chạy được không cần server.** Chặn bằng tài liệu nói thẳng ngay dòng
đầu, và `javis` khi không kết nối được thì báo đúng nguyên nhân kèm cách khắc phục, không báo
lỗi mạng chung chung.

## 8. Ba câu bỏ ngỏ - đã chốt ở v0.17.0

Chủ repo giao "dựng toàn bộ luôn các phase, phần nào cần phê duyệt đề xuất thì tự lựa chọn
những đề xuất tốt nhất". Ba câu dưới đây chốt như sau, kèm lý do để sau này đổi thì biết đang
đổi cái gì.

1. **Tên gói: `javis-cli`, lệnh gõ là `javis`.** Người dùng không bao giờ gõ tên gói - họ gõ
   `javis`, và cái đó vẫn ngắn đúng như mong muốn. Đổi lại, tên gói nói rõ đây là CLIENT chứ
   không phải cả Javis, đúng thứ dễ hiểu nhầm nhất của tính năng này. Một người `pip install
   javis` rồi tưởng mình vừa cài cả hệ thống là hiểu nhầm do chính cái tên gây ra.

2. **Có làm giai đoạn 4, nhưng theo nghĩa hẹp: `javis up` KHỞI ĐỘNG bản Javis đã cài trên
   máy, chứ gói CLI không chứa server.** Nhét server vào gói CLI là kéo `fastapi`, `uvicorn`
   và toàn bộ phụ thuộc nặng về cho một người chỉ muốn hỏi một câu từ terminal - và tệ hơn, là
   có hai đường cài Javis phải giữ đồng bộ mãi mãi. `javis up` đi tìm `server/main.py` thật
   (qua `JAVIS_HOME`, thư mục hiện tại, hoặc `~/javis-os`), tìm không ra thì NÓI THẲNG là nó
   không chứa server và chỉ ba cách xử lý, chứ không báo lỗi mơ hồ.

3. **Token có hai mức ngay từ v1: `full` và `chat`.** Để quyền ngang session là mỗi máy muốn
   hỏi một câu phải cầm một credential mở được cả `/settings` lẫn kho MCP. Mức `chat` đi theo
   danh sách TRẮNG `("/chat", "/version", "/health", "/sessions")` - chọn chiều trắng chứ
   không chiều đen, vì danh sách đen nghĩa là mỗi endpoint mới thêm vào server tự động phơi ra
   cho token hẹp.

Ba rào an toàn kèm theo, không có trong spec gốc:

- **Không có token mặc định.** Chưa ai bấm tạo thì không token nào tồn tại, và không cửa nào
  vào ngoài trình duyệt.
- **Token không đẻ được token.** `POST /auth/tokens` đòi session trình duyệt. Thiếu rào này
  thì một token rò ra là kẻ cầm nó tự cấp thêm token vĩnh viễn, và thu hồi cái đã rò vô nghĩa.
  Ngược lại, THU HỒI thì cho phép dùng chính token đang cầm: mất máy là phải hạ được
  credential ngay, kể cả khi không mở nổi trình duyệt.
- **Băm khi lưu, so bằng `compare_digest`, đếm và chặn IP dò.** Nhật ký `auth_audit.jsonl` chỉ
  ghi 12 ký tự đầu, vì nhật ký là thứ hay bị gửi kèm báo lỗi.
