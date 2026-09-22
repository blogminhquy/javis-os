# Hỏi ChatGPT Web (tool `web_ask`)

**Phiên bản:** v1.0. Thay cho bản "ChatGPT Web / DeepSeek Web làm provider" bàn trong chat
2026-09-22.
**Trạng thái:** chốt phạm vi, **chưa viết mã**, và **chưa được phép viết mã** cho tới khi
qua Cổng 0 ở mục 11.
**Phạm vi:** một plugin bundled cộng một module transport. Không đụng `engine.py`,
`main.py`, `sessions.py`, `aux_engine.py`.
Tài liệu cho người sửa lõi.

---

## Ba quyết định chi phối tài liệu này

1. **ChatGPT Web là một TOOL, không phải một engine.** Bản bàn đầu định thêm nó vào danh
   sách bộ não để agent loop chạy trên đó. Mục 2 chứng minh đó là cách tiêu quota tệ nhất có
   thể. Ở đây nó là một tool mà **mọi engine đều gọi được**, giống hệt
   `javis_generate_image`. Nhưng "tool" mặc định nghĩa là model tự quyết khi nào gọi, mà chủ
   dự án muốn **tự bấm**, nên mục 7 thêm ba nấc bấm tay tất định, không qua model.
2. **Không thêm một nhánh provider nào.** `main.py` đã có 72 nhánh `provider == "..."`. Thêm
   một provider nữa là thêm nhánh vào cả model picker, catalog model, đường chat, đường việc
   nền, Telegram `/model`, trang Models. Một plugin thì không đụng dòng nào trong số đó.
3. **Cổng 0 đứng trước mã.** Javis **đã** tiêu được quota gói ChatGPT không cần API key
   (`engine.py:1005`). Việc này chỉ thêm đúng một thứ: tiêu pool tin nhắn chat thay vì pool
   Codex. Nếu pool Codex chưa cạn thì dự án không có lợi ích gì và không được làm.

---

## 1. Vì sao

Mục tiêu của chủ dự án: dùng quota bản web của ChatGPT cho Javis, mà vẫn có đủ tool như bản
Codex.

Hai repo được nêu làm tiền lệ đều **không làm việc đó**, phải ghi lại để lần sau không ai
quay lại tra:

- `Niek/chatgpt-web` là giao diện chat một trang gọi **API chính thức bằng API key**
  (OpenAI, Anthropic, xAI, Gemini, Mistral). Không đụng phiên web. Repo cũ hay bị nhớ nhầm
  là `Chanzhaoyu/chatgpt-web`, từng có đường `accessToken` đi qua
  `backend-api/conversation`; đường đó chết khi OpenAI thêm Cloudflare cộng proof-of-work
  sentinel.
- `codelocal-cloud/codelocal` là một lớp **MCP cộng project brain** chạy native runtime, và
  README nói thẳng là không dùng browser automation. Nó gần với trang Coding 0.63.0 của
  Javis hơn là với việc này.

Nên không có tiền lệ nào để chép. Phải tự quyết kiến trúc, và quyết cho đúng ngay lần đầu.

## 2. Bài toán thật: quota web đếm theo TIN NHẮN

Đây là số liệu quyết định toàn bộ thiết kế.

Gói API tính theo **token**. Gói web tính theo **lượt tin nhắn trong một cửa sổ trượt**. Hai
đơn vị khác nhau.

Trần vòng gọi tool của một lượt chat Javis là **30** (`engine.py:1680`,
`JAVIS_MAX_TOOL_ROUNDS`). Một task sửa bug thật ăn 10 tới 30 vòng: đọc file, grep, sửa, chạy
test, đọc lỗi, sửa tiếp. **Mỗi vòng là một tin nhắn gửi vào bộ não.**

Hệ quả: lấy ChatGPT Web làm engine cho agent loop thì **một task coding đốt sạch quota chat
của cả cửa sổ**. Thêm nữa chat web không có prompt caching và luồng hội thoại dài dần, nên
vòng sau nặng hơn vòng trước.

Đảo lại vai trò thì số liệu đổi chiều:

```
Codex / Claude Code / Grok   ←  vẫn là agent, vẫn đủ Bash + file + git + MCP
        │
        │ gặp chỗ khó: bug lạ, thiết kế refactor, review diff
        ↓
   tool  web_ask(...)
        ↓
ChatGPT Web  →  1 tin nhắn, 1 câu trả lời dài
```

Một task khó tiêu 1 tới 3 tin nhắn web thay vì 30.

Và phần khó nhất của mọi bản kế hoạch trước **biến mất khỏi phạm vi**: agent vẫn là Codex,
nên Javis không phải giả lập tool calling qua chữ cho phía web. Streaming, turn lifecycle,
tool call, cancellation, apply-patch đều là việc của Codex như cũ. Mô hình web chỉ cần nhận
chữ và trả chữ.

## 3. Phạm vi

**Làm:** ChatGPT Web.

**Không làm: DeepSeek Web.** API DeepSeek rẻ tới mức tiền API một tháng dùng cá nhân thấp
hơn công sức xây cộng vá bridge, chưa kể rủi ro khoá tài khoản. Javis đã gọi DeepSeek qua
OpenRouter (`config.py:169`); muốn trực tiếp thì thêm provider API OpenAI-compatible là việc
của một buổi chiều, cắm thẳng vào `openai_chat_with_mcp`. Việc đó **không thuộc tài liệu
này**.

## 4. Luật mượn

Không viết bản thứ hai của bất kỳ dòng nào bên phải.

| Việc này cần | Dùng lại |
|---|---|
| Chromium tải về, dò Chrome/Edge sẵn có, `PLAYWRIGHT_BROWSERS_PATH` | `optional_tools.py` |
| Khuôn plugin đăng ký tool cho MỌI engine | `system/plugins/image-chatgpt/` (10 dòng yaml + 60 dòng py) |
| Cấp tool xuống engine, cưỡng chế `min_mode` | `mcp_hub.py` |
| Lệnh con chạy câm trên Windows | `winproc.py` |
| Đọc câu "hết lượt" và mốc mở lại | `limit_learner.parse_subscription_limit`, `subscription_span` |
| Phân loại lỗi sang tiếng người cho UI | khuôn `connect_health.classify_error` |
| Nơi lưu trạng thái | `config.STATE_DIR` |

## 5. Transport: để trang tự xác thực, Javis chỉ đọc dây

Ba đường khả dĩ, chọn đường thứ ba:

| Đường | Vì sao loại / chọn |
|---|---|
| Dựng lại request `backend-api/conversation` bằng cookie | Phải tự giải proof-of-work sentinel và qua Cloudflare. Hỏng vài tuần một lần. **Loại** |
| Scrape DOM, đọc bong bóng chat cuối | Hỏng mỗi lần OpenAI đổi giao diện. **Loại** |
| **Tee `window.fetch` trong chính trang đã đăng nhập** | Trang tự lo auth, Cloudflare, PoW. Javis chỉ đọc luồng trang vốn đã nhận. **Chọn** |

Cơ chế:

1. Mở Chromium bằng `launch_persistent_context` trỏ vào
   `STATE_DIR/web-profiles/chatgpt/`. Chủ máy **đăng nhập tay đúng một lần** vào profile đó.
2. `add_init_script` bọc `window.fetch` của trang, tee luồng SSE của câu trả lời ra một
   callback đăng ký bằng `expose_binding`. Khoảng 30 dòng JS.
3. Gõ prompt vào ô soạn, gửi, rồi đọc từ luồng đã tee cho tới khi kết thúc.

Javis **không bao giờ chạm vào cookie, token hay proof-of-work**. Đổi giao diện không gãy,
đổi cơ chế auth không gãy. Chỉ gãy nếu OpenAI đổi hẳn khuôn sự kiện SSE, và khi đó lỗi là
lỗi nói được chứ không phải trả về chuỗi rỗng.

Ở vai trò tool, **độ trễ 20 tới 40 giây một câu là chấp nhận được**. Đây là lý do nữa để
không làm engine: làm engine thì độ trễ đó nhân lên 30 vòng.

**Một lượt tại một thời điểm.** Cùng một profile, cùng một tài khoản, nên module giữ một
khoá; lượt thứ hai xếp hàng, quá `QUEUE_TIMEOUT` thì trả lỗi nói rõ là đang bận, không mở
context thứ hai.

## 6. Bề mặt mã

Bốn chỗ mới. Hai chỗ đầu là đường đi của câu hỏi, hai chỗ sau là cách anh BẤM để
chọn nó (mục 7). Không có chỗ thứ năm.

### 6.1. `server/web_ask.py`

Module transport. Stdlib cộng Playwright, **không import `main`, không import FastAPI**, test
được bằng một trang giả cục bộ.

```
trang_thai() -> dict          # đã đăng nhập chưa, lần chạy được gần nhất, cooldown
mo_cua_so_dang_nhap() -> dict # mở profile để chủ máy đăng nhập tay một lần
hoi(prompt, *, context="", new_thread=True, timeout=180) -> dict
ngat()                        # đóng context, dùng khi tắt server
```

`hoi` trả `{"ok": bool, "text": str, "error": str, "kind": str, "elapsed": float}`.

### 6.2. `system/plugins/web-ask/`

`plugin.yaml` cộng `plugin.py`, theo đúng khuôn `image-chatgpt`.

```yaml
name: Hỏi ChatGPT Web
slug: web-ask
version: 1.0.0
description: Hỏi một câu khó cho ChatGPT bản WEB bằng phiên trình duyệt đã đăng nhập, tiêu quota chat chứ không tiêu quota Codex hay API key. Trả về một câu trả lời dạng chữ.
author: Javis (bundled)
enabled: false
min_mode: safe
tools:
  - web_ask
hooks: []
```

**Hợp đồng tool:**

| Tham số | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `prompt` | string, bắt buộc | | Câu hỏi. Viết đủ bối cảnh vì phía kia không thấy repo |
| `context` | string | `""` | Đoạn mã, diff, log dán kèm. Cắt ở `CONTEXT_MAX` |
| `new_thread` | bool | `true` | `false` để hỏi tiếp trong cùng luồng vừa mở |

Trả về **chữ thuần**. Lỗi trả chuỗi mở đầu `ERROR: ` kèm câu nói được, đúng quy ước các tool
hiện có.

**`min_mode: safe`, không phải `readonly`:** tool này gửi nội dung repo ra ngoài và tiêu một
hạn mức dùng chung, nên chế độ `suggest` (chỉ đọc) không được tự gọi. Không đặt `full` vì nó
không thay đổi gì bên ngoài.

**`enabled: false` dù là plugin bundled**, khác `image-chatgpt`. Cộng thêm cổng môi trường
`JAVIS_ENABLE_WEB_ASK=true`. Lý do ở mục 10.

### 6.3. Lệnh `/web` trong `dashboard/chat-slash.js`

Thêm `"web"` vào `SESSION_COMMANDS` (hiện là `["new", "reset", "stop"]`), **không** đăng ký
nó như một skill.

Đây là điểm dễ làm sai nhất của cả tài liệu. Khung lệnh hiện có quy ước `/<slug>` nghĩa là
**gọi skill `<slug>`** (`main.py:5076`, `chat-slash.js:buildMenu`). Skill thì đi qua model,
và model vẫn có toàn quyền tự trả lời rồi bỏ qua skill. Như vậy `/web` sẽ **không tất định**,
mà tất định mới là thứ mục 7 cần.

Lệnh phiên thì khác: client chặn ngay trong `sendMessage()`, server gọi thẳng `web_ask`,
**model không được đụng vào lượt đó**.

Cũng vì thế `/web` **không** được nhận dạng ở GIỮA câu (`parseSlashAnywhere`), giống
`/new` `/reset` `/stop`. Một câu như "xem file /web-ask.js giúp anh" mà tự nhiên bắn ra ngoài
là hỏng.

### 6.4. Chip trong `dashboard/coding.js` và `#modelBar`

Bản 0.63.0 đã nhét **dải chip ngữ cảnh vào chính `#modelBar` đã mượn, đứng trước chip Model**.
Thêm một chip vào đúng dải đó theo cùng khuôn, không dựng thanh thứ hai.

## 7. Anh chủ động chọn thế nào

Mục 2 quyết định ChatGPT Web là tool. Nhưng "tool" theo mặc định nghĩa là **model tự quyết
khi nào gọi**, mà điều chủ dự án muốn là **tự bấm**. Hai chuyện khác nhau, và mục này lo
chuyện thứ hai.

Ba nấc, cùng chạy trên một `web_ask`, khác nhau ở độ dính:

| Nấc | Cách bấm | Phạm vi | Codex lúc đó |
|---|---|---|---|
| 1 | Gõ `/web <câu hỏi>` | Đúng một câu | Không chạy lượt đó |
| 2 | Bật chip **ChatGPT Web** trên thanh chat | Cả phiên tới khi tắt | Nghỉ cả phiên |
| 3 | Trong phiên Coding: chip **Hỏi Web lượt tới** | Một lượt, xong tự tắt | Giữ nguyên task, worktree, git |

Nấc 3 là nấc dùng nhiều nhất trong thực tế: Codex vẫn cầm task và cây mã, anh chỉ mượn não
web cho đúng câu khó. Câu trả lời rơi vào khung chat như một tin nhắn bình thường, nên lượt
sau Codex đọc lại được và làm tiếp.

### Tự đóng gói bối cảnh (không có cái này thì anh sẽ bỏ sau ba lần)

`/web` gõ **trong một phiên Coding** thì Javis tự đính kèm, không bắt anh copy paste:

- `git diff` hiện tại của worktree
- file đang mở trong trình sửa (khối `[FILE ĐANG MỞ...]` đã có sẵn)
- tên nhánh và repo
- đoạn lỗi test gần nhất trong phiên, nếu có

`coding_store.cwd_cua_phien` đã biết cwd và nhánh; `git diff` là một lệnh. Tổng gói cắt ở
`CONTEXT_MAX`, và Javis **in ra đã gửi đi những gì** trước khi gửi, vì đây là mã nguồn rời
khỏi máy.

### Bật chip thì mất gì, và phải nói ngay

Chip bật là Javis in một dòng ngay dưới thanh chat:

> Đang hỏi qua ChatGPT Web: không có Bash, không đọc ghi file, không MCP, không skill, không
> nhớ mạch phiên. Chỉ nhận chữ và trả chữ.

Không in dòng này thì sẽ có lần chủ máy bật chip rồi bảo "sửa giúp file này", nhận về một
đoạn chữ, và tưởng Javis hỏng.

### Vì sao KHÔNG cho vào ô chọn Model

Ô chọn Model là chỗ chọn **bộ não**, và `CLAUDE.md` hứa mọi bộ não trong đó có cùng bộ tool.
Nhét một thứ không có tool nào vào cùng danh sách là đặt bẫy: lần sau chọn nó rồi giao việc
cần sửa file, nó im lặng không làm được, và lỗi đó trông như lỗi của Javis chứ không như một
lựa chọn của người dùng.

Chip đứng **cạnh** picker, không **trong** picker, và tự nói mình là gì.

### Đếm lượt thay cho quota

Muốn chủ động thì phải thấy còn bao nhiêu, mà ChatGPT Web không phơi con số quota ra. Nên
Javis tự đếm trong sổ ở mục 8: `so_luot_trong_ngay`, cộng mốc chạm trần gần nhất. Đủ để tự
liệu, và **không bịa phần trăm** (đúng luật đã có trong `CLAUDE.md`).

## 8. Trạng thái và phân loại lỗi

Sổ `STATE_DIR/web_ask.json`:

```
last_success     last_error     failure_count
cooldown_until   auth_state     so_luot_trong_ngay
```

Đây là **hiện thực đầu tiên của máy trạng thái provider** mà bản rà soát kiến trúc
2026-09-22 nêu là còn thiếu (`_FallbackChain` hiện thử mù, không nhớ mắt nào vừa chết). Viết
sổ này ở dạng tổng quát được, để sau bê nguyên sang các provider khác.

| Mã | Khi nào | Javis làm gì |
|---|---|---|
| `CHUA_DANG_NHAP` | profile chưa có phiên | Trả lỗi kèm câu mời bấm "Mở cửa sổ đăng nhập". Không tự nhập gì |
| `HET_LUOT` | trang báo chạm trần tin nhắn | `parse_subscription_limit` lấy mốc mở lại, đặt `cooldown_until`. Trong cooldown thì tool từ chối ngay, không mở trình duyệt |
| `THU_THACH` | Cloudflare hoặc captcha | Cooldown ngắn, báo chủ máy mở cửa sổ qua tay |
| `QUA_HAN` | luồng không kết thúc trong `timeout` | Thử lại đúng MỘT lần rồi báo lỗi |
| `KHONG_CO_TRINH_DUYET` | chưa có Chromium/Chrome | Chỉ sang `optional_tools` để tải |
| `DANG_BAN` | lượt khác đang chạy | Xếp hàng, quá hạn thì báo bận |

`failure_count` tăng dần, chạm `NGUONG_NGAT` thì tự vào cooldown dài. Không có vòng thử lại
vô hạn.

## 9. Giao diện

Một thẻ trên trang **Kết nối**, không phải trang Models (nó không phải bộ não):

- Trạng thái: `Đã đăng nhập` / `Chưa đăng nhập` / `Đang nghỉ tới HH:MM`
- Lần hỏi được gần nhất
- Nút **Mở cửa sổ đăng nhập**
- Nút **Ngắt** (đóng context, xoá profile nếu chủ máy muốn)

Không có ô nhập mật khẩu. Không bao giờ.

## 10. Ranh giới an toàn và rủi ro

**Điều khoản dịch vụ.** OpenAI cấm truy cập tự động vào dịch vụ ngoài đường API. Đây là tài
khoản của chính chủ máy, trên máy của chính họ, nhưng nếu bị phát hiện thì thứ mất là **gói
thuê bao đang trả tiền**. Đúng cùng loại cảnh báo mà `CLAUDE.md` đã bắt Javis phải nói thẳng
về việc chạy nền gói Claude Pro/Max. Không bọc đường, không trấn an suông.

Vì vậy:

- `enabled: false` mặc định, cộng cổng `JAVIS_ENABLE_WEB_ASK=true`. Bật là một hành động có
  chủ ý, không phải thứ thừa hưởng mà không biết.
- Mô tả plugin nói rõ nó dùng phiên trình duyệt, để người bật biết mình đang bật gì.
- Không nhịp gọi tự động. Không loop nền nào được phép gọi `web_ask` theo lịch.

**Ràng buộc VPS.** Cái này cần một trình duyệt có profile đăng nhập thật. Trên VPS
(`docker-compose.hostinger.yml`) phải xvfb, và IP trung tâm dữ liệu bị thử thách nhiều hơn
hẳn. Thực tế: **chỉ chạy ổn trên máy nhà hoặc bản desktop**. Trên VPS tool phải tự tắt và
nói rõ lý do, chứ không thử rồi treo.

**Dữ liệu.** `context` là nội dung repo gửi ra ngoài. Mô tả tool phải nói điều đó để model
gọi nó có ý thức, và `min_mode: safe` để chế độ chỉ đọc không tự gửi gì.

## 11. Cổng 0: trả lời trước khi viết dòng mã nào

**Pool Codex của chủ máy có thật sự đang cạn không?**

Mở `usage_store` / `usage_index` ra xem. Nếu chưa cạn thì dừng ở đây: công sức nên đổ vào
Task Handoff Packet và version guard cho Codex, hai việc có lợi cho mọi bộ não chứ không
riêng ChatGPT.

Ghi câu trả lời vào chính tài liệu này trước khi đi tiếp.

## 12. Spike một ngày, có tiêu chí giết

Đặt tiêu chí **trước** khi chạy, không đặt sau khi đã lỡ viết mã:

- 10 câu hỏi liên tiếp trong 30 phút, **ít nhất 9 câu trả về đúng nội dung**
- **Không có thử thách nào** cần tay người trong 10 lượt đó
- Độ trễ trung vị **dưới 60 giây** với prompt khoảng 2.000 token
- Đoạn tee bắt được luồng ở **cả hai cảnh**: mở nguội và tab đã mở sẵn

Không đạt đủ bốn thì **dừng dự án**, ghi kết quả vào đây, và tài liệu này thành bản ghi vì
sao không làm. Đó là kết quả hợp lệ.

## 13. Lộ trình

| Bước | Nội dung | Ước lượng |
|---|---|---|
| Cổng 0 | Xem pool Codex đã cạn chưa | 30 phút, không mã |
| Spike | Tee fetch trên profile cố định, chấm theo mục 12 | 1 ngày |
| Phase 1 | `web_ask.py` cộng plugin `web-ask`, sổ trạng thái, thẻ trang Kết nối | 2-3 ngày |
| Phase 1B | Ba nấc bấm tay của mục 7: lệnh phiên `/web`, chip cả phiên, chip một lượt trong Coding, cộng tự đóng gói bối cảnh | 1-2 ngày |
| Phase 2 | Chỉ khi Phase 1 chạy ngon: cùng transport cắm làm provider `aux_engine` cho **việc nền một lượt** (viết bài, tóm tắt, ingest) | 2-3 ngày |

Phase 2 không được đụng đường chat và không được đụng vòng lặp coding. Nó cắm vào
`_FallbackChain` như một mắt xích và thừa hưởng sổ trạng thái mục 8.

## 14. Không làm

- Web làm engine cho agent loop coding. Mục 2 là lý do.
- DeepSeek Web. Mục 3 là lý do.
- Tự giải proof-of-work, tự dựng request `backend-api`, đụng cookie hay token.
- Ô nhập mật khẩu ChatGPT trong Javis.
- Chạy trên VPS.
- Loop nền tự gọi `web_ask` theo lịch.

## 15. Test

Repo chạy test bằng cách gọi từng file như script, nên mỗi file phải có nhánh chạy thẳng.

- `test_web_ask_plugin.py`: plugin load được, `enabled: false`, `min_mode: safe`, thiếu cổng
  môi trường thì tool báo câu nói được chứ không ném exception.
- `test_web_ask_state.py`: `HET_LUOT` đặt đúng `cooldown_until` từ mốc
  `parse_subscription_limit` trả về; trong cooldown thì `hoi()` từ chối mà **không** mở trình
  duyệt; `failure_count` chạm ngưỡng thì vào cooldown dài.
- `test_web_ask_tee.py`: chạy đoạn JS tee trên một trang tĩnh cục bộ phát SSE giả, khẳng định
  ghép lại đúng nguyên văn, và luồng đứt giữa chừng thì trả `QUA_HAN` chứ không trả chuỗi
  cụt.
- `test_web_ask_dong_thoi.py`: hai lượt cùng lúc thì lượt sau xếp hàng, quá hạn trả `DANG_BAN`,
  và không có context thứ hai nào được mở.
- `test_web_lenh_phien.js`: `/web` nằm trong `SESSION_COMMANDS` chứ không phải danh sách
  skill; `parseSlash("/web hỏi gì đó")` bắt đúng lệnh cùng arg; và
  `parseSlashAnywhere("xem file /web-ask.js giúp anh")` **không** bắt, vì lệnh phiên không
  được nhận dạng ở giữa câu.

## 16. Để lần sau

- Máy trạng thái provider dùng chung cho mọi nhà cung cấp, bê từ sổ mục 8 ra.
- Task Handoff Packet (bản rà soát 2026-09-22, mục 1 phần đề xuất).
- Version guard cho Codex CLI: `install.sh:143` và `update.sh:50` đang cài
  `@openai/codex@latest` vô điều kiện, không có supported range, không có smoke test.
