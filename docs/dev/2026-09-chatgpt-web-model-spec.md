# ChatGPT Web: một model của thẻ ChatGPT

**Phiên bản:** v2.0. Thay v1.0 (ChatGPT Web là một tool `web_ask`, chọn bằng lệnh và chip).
**Trạng thái:** chốt phạm vi, **chưa viết mã**, và chưa được phép viết mã cho tới khi qua
Cổng 0 ở mục 11.
**Phạm vi:** một model id mới trong thẻ ChatGPT sẵn có, một module transport, một bộ dịch
tool qua chữ. Không thêm provider.
Tài liệu cho người sửa lõi.

---

## Quyết định của chủ dự án, 2026-09-22

v1.0 đề xuất ChatGPT Web làm **tool** chứ không làm **bộ não**, lấy lý do là quota web đếm
theo tin nhắn nên vòng lặp tool đốt rất nhanh.

Chủ dự án đã nghe lập luận đó hai lần và **chốt khác**: ChatGPT Web phải **chọn được trong ô
chọn model, nằm trong thẻ ChatGPT**, như một model bình thường. Đó là quyết định, và tài liệu
này làm theo.

Nỗi lo về giá không bị bỏ đi, nó chuyển thành **tham số thiết kế**: mục 5 đặt trần vòng tool
riêng cho model này cộng một bộ đếm lượt hiện ngay trên màn hình, để chủ máy nhìn thấy giá
mình đang trả thay vì bị chặn.

Giữ lại từ v1.0: transport (mục 8), sổ trạng thái và phân loại lỗi (mục 9), ranh giới an toàn
(mục 10), Cổng 0, spike và tiêu chí giết.

---

## 1. Hình dạng đúng: MODEL của thẻ ChatGPT, không phải provider mới

Đây là chỗ quyết định dự án này rẻ hay đắt.

Javis đã có provider `openai-oauth`, nhãn `OpenAI OAuth (ChatGPT)`, `kind: "oauth"`,
`catalog_key: "openai-oauth"` (`main.py:1520`). Provider đó **đã** được phủ sẵn ở mọi chỗ:
72 nhánh `provider == "..."`, ô chọn model, catalog, `/model` của Telegram, thẻ trang Models,
nhãn thuê bao, ngân sách ngữ cảnh.

Nên **không thêm provider**. Chỉ thêm **một model id** vào danh mục của provider đã có:

```
Thẻ ChatGPT
├── gpt-5.5            (qua Codex CLI)
├── gpt-5-codex        (qua Codex CLI)
└── chatgpt-web        (qua trình duyệt, gói chat)   ← thêm mỗi dòng này
```

`default_models` của thẻ này cố ý để rỗng vì `model/list` của Codex app-server là nguồn chân
lý (`main.py:1521`). Nên chỗ chèn là `_fetch_provider_models` (`main.py:4568`), sau khi
`openai_oauth.list_models` (`openai_oauth.py:470`) trả về: **nối thêm `chatgpt-web` vào cuối
danh sách**, và nối **kể cả khi `list_models` trả `None`**.

Câu "kể cả khi trả None" không phải chi tiết vụn. Hôm nay thẻ ChatGPT báo chưa sẵn sàng nếu
máy không có Codex CLI (`main.py:4643`). Sau thay đổi này, **ChatGPT Web chạy được trên máy
KHÔNG cài Codex CLI**, nên `_provider_ready_msg` phải coi thẻ là sẵn sàng khi **một trong hai**
đúng: Codex CLI dùng được, **hoặc** phiên trình duyệt đã đăng nhập.

## 2. Ba chỗ dispatch, và cái bẫy `_codex_safe_model`

Ba chỗ chạy một lượt của `openai-oauth`, đều phải rẽ nhánh khi model là `chatgpt-web`:

| Chỗ | Hiện làm gì |
|---|---|
| `main.py:12432` | Chat dashboard, dựng `CodexCLI` |
| `main.py:16848` | Telegram, dựng `CodexCLI` |
| `main.py:2153` | Luồng gọn, gọi `engine.openai_responses_stream` |

**Cái bẫy phải xử lý TRƯỚC mọi thứ khác.** Cả hai chỗ đầu mở bằng:

```python
actual_model = _codex_safe_model(api_model)
```

`_codex_safe_model` (`main.py:1737`) coerce mọi model không nằm trong catalog và không kết
thúc `-codex` về model Codex mặc định. Tệ hơn: khi nó coerce, chỗ gọi **ghi đè luôn cài đặt**
bằng `_set_main_model`, **và ghi đè cả model ghim của phiên** (`store.set_pinned_model`), rồi
báo "đã tự đổi sang ...".

Nghĩa là nếu không xử lý, chủ máy chọn `chatgpt-web` thì Javis **âm thầm đổi ngược về Codex
và ghi đè lựa chọn đó vào cài đặt**. Chọn một lần là mất luôn.

Hai việc bắt buộc:

1. `_codex_safe_model` coi `chatgpt-web` là hợp lệ (nó sẽ nằm trong catalog sau mục 1, nhưng
   phải có test khoá điều này lại, đừng dựa vào việc catalog tình cờ có nó).
2. Nhánh `chatgpt-web` rẽ **trước** khi chạm `_codex_safe_model`, vì model này không đi qua
   Codex chút nào.

`_is_codex_model` (`main.py:1749`) suy nhà từ tên model cho agent cũ. `chatgpt-web` nằm trong
catalog `openai-oauth` nên hàm này trả `True`, đúng như mong muốn: nó vẫn thuộc nhà ChatGPT.

## 3. Tool: model này PHẢI có tool, không phải để chiều ai

Sáu chỗ trong mã hỏi "đây có phải bộ não gói thuê bao có tool thật không" bằng đúng một câu
`kind in ("cli", "oauth")`:

```
main.py:12101   main.py:15091   main.py:15568   main.py:16729
fast_path_runtime.py:282        adaptive_context_runtime.py:322
```

Chúng chi phối đường tắt fast-path, ngân sách ngữ cảnh và nhãn thuê bao. `chatgpt-web` thuộc
provider `kind: "oauth"`, nên nếu nó **không** có tool thì sáu chỗ này nói dối, và phải sửa cả
sáu để hỏi theo model thay vì theo provider.

Cho nó tool thì bất biến giữ nguyên, không đụng chỗ nào trong sáu chỗ đó. Cộng thêm: đó chính
là thứ chủ dự án muốn từ đầu, "vẫn dùng được tool như bản Codex".

**Nhưng phải nói chính xác là tool NÀO.** `CLAUDE.md` đã chia sẵn hai hạng:

| Hạng | Có gì |
|---|---|
| CLI (Claude Code, Codex, Grok) | Tool file native, **Bash**, **WebFetch/WebSearch**, **Task**, resume phiên |
| API (sáu engine) | Tool vault qua hub, MCP, skill, `javis_task`, `javis_schedule`, plugin. Không Bash, không WebFetch, không Task |

`chatgpt-web` nằm ở **hạng API**, không phải hạng CLI. Nó sẽ có
`javis_read_file` / `javis_list_dir` / `javis_write_file` / `javis_use_skill`, mọi MCP đã nối,
mọi plugin, `javis_task`, `javis_schedule`. Nó **không** có Bash, nên không chạy được test,
không chạy được git.

Phải ghi câu đó vào mô tả model trên ô chọn, để lần sau chọn nó rồi giao việc cần chạy lệnh
thì biết ngay vì sao không được, chứ không tưởng Javis hỏng.

Muốn `chatgpt-web` có Bash là một quyết định khác hẳn: nó nghĩa là cấp tool shell qua hub, và
cấp thế thì **cả sáu engine API cũng có**. Việc đó không thuộc tài liệu này.

## 4. Giao thức tool qua chữ

ChatGPT Web không có function calling. Nên vòng tool phải chạy bằng chữ, đúng kiểu ReAct.

Javis **đã có sẵn vòng lặp**: `engine.openai_chat_with_mcp` (`engine.py:1740`), trần vòng
`_max_tool_rounds` (`engine.py:1680`), phanh chống kẹt `_LapGuard` (`engine.py:1697`), định
tuyến tool qua `mcp_hub`. Chỉ thiếu **bộ dịch** ở hai đầu:

**Đầu gửi:** thay vì đính `tools=[...]` dạng schema, dựng danh sách tool thành chữ và chèn vào
prompt, kèm luật: muốn gọi tool thì trả về **đúng một khối** rào bằng ```` ```javis_tool ````
chứa JSON `{"name": ..., "arguments": {...}}`, và **không viết gì khác** trong lượt đó.

**Đầu nhận:** bóc khối đó ra khỏi câu trả lời. Có khối thì chạy tool qua hub rồi gửi kết quả
lại như tin nhắn kế tiếp. Không có khối thì đó là câu trả lời cuối.

Ba ranh giới của bộ dịch:

- **Khối hỏng thì nói ra, đừng đoán.** JSON sai cú pháp, thiếu `name`, tool không tồn tại: gửi
  lại một tin nhắn nói rõ sai gì, tính là một vòng. Đoán ý model là cách chắc chắn để một ngày
  nào đó ghi nhầm file.
- **`_LapGuard` dùng nguyên.** Gọi lại y hệt tool với y hệt tham số là bệnh chung, không phải
  bệnh riêng của model nào.
- **Cưỡng chế `min_mode` ở hub như mọi engine khác.** Model gõ ra tên một tool mà mức quyền
  hiện tại không cho là hub chặn, không phải bộ dịch tự xét.

## 5. Giá một lượt, và cái phanh

Với model này, **một vòng tool là một tin nhắn web**. Một lượt chat tốn:

```
1 tin nhắn  +  số vòng tool
```

Trần chung của Javis là 30 vòng (`JAVIS_MAX_TOOL_ROUNDS`). Để nguyên 30 cho model này nghĩa là
một lượt có thể ăn 31 tin nhắn, tức cả cửa sổ quota chat.

Nên:

- Trần riêng `JAVIS_WEB_MAX_TOOL_ROUNDS`, **mặc định 6**, kẹp trên bằng trần chung. Chạm trần
  thì nói đúng như `_het_vong_msg` đang nói: còn dở, chia nhỏ yêu cầu, hoặc nâng trần.
- **Bộ đếm hiện trên màn hình.** Chạy xong một lượt, Javis nói đã tiêu bao nhiêu tin nhắn web
  trong lượt đó và tổng trong ngày (`so_luot_trong_ngay` ở mục 9).

Đây là cách xử lý nỗi lo của v1.0: không chặn chủ máy, mà để chủ máy **nhìn thấy giá** rồi tự
quyết. Trần 6 là con số mở đầu, chỉnh được bằng biến môi trường.

## 6. Mạch hội thoại

Một hội thoại trên chatgpt.com có id riêng và nối tiếp được, y như `codex_thread_id`.

`sessions.py:1160` đã có bảng ánh xạ engine sang cột giữ mạch, kèm lời dặn ngay trong mã:
"Thêm engine giữ phiên mới thì thêm một dòng ở đây, đừng rải thêm một lệnh clear nữa vào
`main.py` - đó chính là cách bảng này bị bỏ sót hai engine."

Làm đúng lời dặn đó: thêm cột `web_thread_id` và một dòng trong `_MACH_NATIVE`.

Bất biến của `clear_native_threads` giữ nguyên và áp dụng cho cả model này: lượt nào chạy bằng
engine khác thì mạch web thành khuyết, nên bị vô hiệu. Đổi model giữa phiên là mở luồng web
mới, không phải nối tiếp luồng cũ.

## 7. Thẻ ChatGPT ở trang Models

Thẻ đã có, thêm vào đó:

- Dòng trạng thái phiên web: `Đã đăng nhập` / `Chưa đăng nhập` / `Đang nghỉ tới HH:MM`.
- Nút **Mở cửa sổ đăng nhập**. Không có ô nhập mật khẩu, không bao giờ.
- Bộ đếm `đã hỏi N lượt hôm nay` cộng mốc chạm trần gần nhất.
- Mô tả model `chatgpt-web` nói thẳng: tiêu quota chat, không có Bash, không chạy được test.

Thẻ sẵn sàng khi Codex CLI dùng được **hoặc** phiên web đã đăng nhập (mục 1).

## 8. Transport: để trang tự xác thực, Javis chỉ đọc dây

Giữ nguyên từ v1.0. Ba đường khả dĩ, chọn đường thứ ba:

| Đường | Vì sao loại / chọn |
|---|---|
| Dựng lại request `backend-api/conversation` bằng cookie | Phải tự giải proof-of-work sentinel và qua Cloudflare. Hỏng vài tuần một lần. **Loại** |
| Scrape DOM, đọc bong bóng chat cuối | Hỏng mỗi lần đổi giao diện. **Loại** |
| **Tee `window.fetch` trong chính trang đã đăng nhập** | Trang tự lo auth, Cloudflare, PoW. Javis chỉ đọc luồng trang vốn đã nhận. **Chọn** |

Cơ chế:

1. Mở Chromium bằng `launch_persistent_context` trỏ vào `STATE_DIR/web-profiles/chatgpt/`.
   Chủ máy đăng nhập tay đúng một lần.
2. `add_init_script` bọc `window.fetch` của trang, tee luồng SSE ra một callback đăng ký bằng
   `expose_binding`. Khoảng 30 dòng JS.
3. Gõ prompt vào ô soạn, gửi, đọc từ luồng đã tee cho tới khi kết thúc.

Javis không chạm cookie, token hay proof-of-work. Đổi giao diện không gãy, đổi cơ chế auth
không gãy.

**Một lượt tại một thời điểm.** Cùng profile, cùng tài khoản, nên module giữ một khoá; lượt
thứ hai xếp hàng, quá `QUEUE_TIMEOUT` thì trả `DANG_BAN`, không mở context thứ hai.

Mượn lại, không dựng lại:

| Cần | Dùng lại |
|---|---|
| Chromium tải về, dò Chrome/Edge sẵn có, `PLAYWRIGHT_BROWSERS_PATH` | `optional_tools.py` |
| Vòng lặp tool, trần vòng, phanh kẹt | `engine.py:1680`, `engine.py:1697`, `engine.py:1740` |
| Định tuyến tool, cưỡng chế `min_mode` | `mcp_hub.py` |
| Lệnh con chạy câm trên Windows | `winproc.py` |
| Đọc câu "hết lượt" và mốc mở lại | `limit_learner.parse_subscription_limit`, `subscription_span` |
| Nơi lưu trạng thái | `config.STATE_DIR` |

**Bề mặt mã:** `server/web_chat.py` (transport cộng bộ dịch tool), ba nhánh dispatch ở mục 2,
một dòng ở `_fetch_provider_models`, một cột cộng một dòng ở `sessions.py`, phần thẻ Models.

## 9. Trạng thái và phân loại lỗi

Sổ `STATE_DIR/web_chat.json`:

```
last_success     last_error     failure_count
cooldown_until   auth_state     so_luot_trong_ngay
```

Đây là hiện thực đầu tiên của **máy trạng thái provider** mà bản rà soát kiến trúc 2026-09-22
nêu là còn thiếu (`aux_engine._FallbackChain` hiện thử mù, không nhớ mắt nào vừa chết). Viết ở
dạng tổng quát được, để sau bê nguyên sang nhà khác.

| Mã | Khi nào | Javis làm gì |
|---|---|---|
| `CHUA_DANG_NHAP` | profile chưa có phiên | Lỗi kèm câu mời bấm "Mở cửa sổ đăng nhập" |
| `HET_LUOT` | trang báo chạm trần tin nhắn | `parse_subscription_limit` lấy mốc mở lại, đặt `cooldown_until`. Trong cooldown thì từ chối ngay, không mở trình duyệt |
| `THU_THACH` | Cloudflare hoặc captcha | Cooldown ngắn, báo chủ máy mở cửa sổ qua tay |
| `QUA_HAN` | luồng không kết thúc trong `timeout` | Thử lại đúng MỘT lần rồi báo lỗi |
| `KHONG_CO_TRINH_DUYET` | chưa có Chromium/Chrome | Chỉ sang `optional_tools` để tải |
| `DANG_BAN` | lượt khác đang chạy | Xếp hàng, quá hạn thì báo bận |

`HET_LUOT` giữa một vòng tool là ca đặc biệt: **giữ lại phần đã làm**, báo rõ đang dở ở vòng
thứ mấy, và đưa vào `limit_resume.REGISTRY` để tự chạy lại khi gói mở lại, như các engine khác.

`failure_count` chạm `NGUONG_NGAT` thì vào cooldown dài. Không có vòng thử lại vô hạn.

## 10. Ranh giới an toàn và rủi ro

**Điều khoản dịch vụ.** OpenAI cấm truy cập tự động vào dịch vụ ngoài đường API. Đây là tài
khoản của chính chủ máy, trên máy của chính họ, nhưng nếu bị phát hiện thì thứ mất là **gói
thuê bao đang trả tiền**. Đúng cùng loại cảnh báo mà `CLAUDE.md` bắt Javis nói thẳng về việc
chạy nền gói Claude Pro/Max. Không bọc đường.

Vì vậy:

- Model `chatgpt-web` chỉ hiện trong ô chọn khi cổng môi trường `JAVIS_ENABLE_WEB_CHAT=true`
  được bật. Bật là một hành động có chủ ý.
- Mô tả model nói rõ nó chạy bằng phiên trình duyệt, để người bật biết mình bật gì.
- **Không việc nền nào được tự chọn model này.** Loop, nhắc hẹn, task Kanban, `_FallbackChain`
  đều loại nó ra. Nó chỉ chạy khi có người ngồi trước màn hình chọn nó.

**Ràng buộc VPS.** Cần trình duyệt có profile đăng nhập thật. Trên VPS
(`docker-compose.hostinger.yml`) phải xvfb, và IP trung tâm dữ liệu bị thử thách nhiều hơn
hẳn. Thực tế: **chỉ chạy ổn trên máy nhà hoặc bản desktop**. Trên VPS thì model tự ẩn khỏi ô
chọn và nói rõ lý do, chứ không hiện ra rồi lỗi.

**Dữ liệu.** Tool `javis_read_file` trả nội dung vault, và nội dung đó đi thẳng vào ô chat của
chatgpt.com. Javis in ra đã gửi những gì trước mỗi vòng tool.

## 11. Cổng 0: trả lời trước khi viết dòng mã nào

**Pool Codex của chủ máy có thật sự đang cạn không?**

Mở `usage_store` / `usage_index` ra xem. Javis **đã** tiêu được quota gói ChatGPT không cần
API key (`engine.py:1005`, `engine.py:1022`), nên việc này chỉ thêm đúng một thứ: tiêu pool
tin nhắn chat thay vì pool Codex. Chưa cạn thì dự án không có lợi ích gì.

Ghi câu trả lời vào chính tài liệu này trước khi đi tiếp.

## 12. Spike một ngày, có tiêu chí giết

Đặt tiêu chí **trước** khi chạy:

- 10 câu hỏi liên tiếp trong 30 phút, **ít nhất 9 câu trả về đúng nội dung**
- **Không có thử thách nào** cần tay người trong 10 lượt đó
- Độ trễ trung vị **dưới 60 giây** với prompt khoảng 2.000 token
- Đoạn tee bắt được luồng ở **cả hai cảnh**: mở nguội và tab đã mở sẵn
- **Một vòng tool đi trọn**: model trả đúng khối ```` ```javis_tool ````, Javis bóc được, chạy
  được, gửi lại được, và model dùng kết quả đó trả lời

Tiêu chí cuối là tiêu chí mới của v2.0 và là tiêu chí dễ trượt nhất. Không đạt đủ năm thì
**dừng dự án**, ghi kết quả vào đây, và tài liệu này thành bản ghi vì sao không làm.

## 13. Lộ trình

| Bước | Nội dung | Ước lượng |
|---|---|---|
| Cổng 0 | Xem pool Codex đã cạn chưa | 30 phút, không mã |
| Spike | Tee fetch cộng một vòng tool đi trọn, chấm theo mục 12 | 1-2 ngày |
| Phase 1 | `web_chat.py`: transport, sổ trạng thái, thẻ Models, nút đăng nhập. Chưa có tool, chat thuần | 2-3 ngày |
| Phase 2 | Bộ dịch tool qua chữ, trần vòng riêng, bộ đếm lượt. Đây là phần khó nhất | 3-4 ngày |
| Phase 3 | `web_thread_id`, nối tiếp luồng, `limit_resume` khi hết lượt giữa vòng tool | 1-2 ngày |

Phase 1 tự nó đã dùng được (chat thuần, không tool), nên nếu Phase 2 sa lầy thì vẫn có thứ
chạy được chứ không phải bỏ trắng.

## 14. Không làm

- Thêm provider mới. Mục 1 là lý do.
- DeepSeek Web. API DeepSeek rẻ hơn công sức xây và vá bridge; muốn DeepSeek thì thêm provider
  API OpenAI-compatible, một buổi chiều, không thuộc tài liệu này.
- Tự giải proof-of-work, tự dựng request `backend-api`, đụng cookie hay token.
- Ô nhập mật khẩu ChatGPT trong Javis.
- Chạy trên VPS.
- Việc nền tự chọn `chatgpt-web`.
- Cấp Bash cho model này. Mục 3 là lý do.

## 15. Test

Repo chạy test bằng cách gọi từng file như script, nên mỗi file phải có nhánh chạy thẳng.

- `test_web_chat_model_khong_bi_coerce.py`: **quan trọng nhất.** `_codex_safe_model("chatgpt-web")`
  trả về đúng `chatgpt-web`; và nhánh chat không gọi `_set_main_model` hay `set_pinned_model`
  khi model là `chatgpt-web`. Đây là cái bẫy ở mục 2, mất nó là lựa chọn của chủ máy bị ghi đè
  âm thầm.
- `test_web_chat_catalog.py`: `chatgpt-web` có trong danh sách model của thẻ ChatGPT **cả khi**
  `openai_oauth.list_models` trả `None`; và thẻ báo sẵn sàng khi chỉ có phiên web, không có
  Codex CLI.
- `test_web_chat_tool_protocol.py`: bóc đúng khối ```` ```javis_tool ````; JSON hỏng thì trả
  câu báo lỗi nói được chứ không ném exception và không đoán; tên tool không tồn tại thì báo rõ;
  `_LapGuard` vẫn cắt khi lặp y hệt.
- `test_web_chat_tran_vong.py`: trần mặc định là 6, kẹp trên bằng `JAVIS_MAX_TOOL_ROUNDS`, và
  chạm trần thì câu trả lời kèm lời giải thích chứ không cụt.
- `test_web_chat_state.py`: `HET_LUOT` đặt đúng `cooldown_until`; trong cooldown thì từ chối mà
  **không** mở trình duyệt; hết lượt giữa vòng tool thì giữ phần đã làm và vào `limit_resume`.
- `test_web_chat_tee.js`: chạy đoạn JS tee trên một trang tĩnh phát SSE giả, ghép lại đúng
  nguyên văn; luồng đứt giữa chừng thì `QUA_HAN` chứ không trả chuỗi cụt.
- `test_web_chat_viec_nen.py`: `_FallbackChain` và hàng đợi việc nền không bao giờ chọn
  `chatgpt-web`.

## 16. Để lần sau

- Lệnh phiên `/web` và chip "hỏi Web lượt tới" trong phiên Coding, để hỏi một câu mà vẫn ở
  trên Codex. Đã đặc tả trong v1.0 mục 7; rẻ, nhưng chỉ làm sau khi đường chọn model chạy ngon.
- Máy trạng thái provider dùng chung cho mọi nhà, bê từ sổ mục 9 ra.
- Task Handoff Packet (bản rà soát 2026-09-22).
- Version guard cho Codex CLI: `install.sh:143` và `update.sh:50` đang cài
  `@openai/codex@latest` vô điều kiện, không có supported range, không có smoke test.
