# ChatGPT Web: một model của thẻ ChatGPT

**Phiên bản:** v2.1. Thay v2.0 (thiếu mục 2.2 và mục 7) và v1.0 (ChatGPT Web là một tool
`web_ask`, chọn bằng lệnh và chip).
**Trạng thái:** chốt phạm vi, **chưa viết mã**, và chưa được phép viết mã cho tới khi qua
Cổng 0 ở mục 12.
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

**Quyết định thứ hai, cùng ngày.** Bản v2.0 đầu tiên đặt trần vòng tool riêng là 6, sợ một
lượt ăn 31 tin nhắn. Chủ dự án cho biết **dung lượng gói chat của họ rất lớn, không cần lo số
tin nhắn**. Trần riêng bị bỏ, quay về trần chung 30.

Nhưng bỏ trần đó thì một ràng buộc khác lên thế chỗ, và ràng buộc mới cứng hơn: **thời gian**.
Mục 5 viết lại theo ràng buộc đó.

Giữ lại từ v1.0: transport (mục 9), sổ trạng thái và phân loại lỗi (mục 10), ranh giới an
toàn (mục 11), Cổng 0, spike và tiêu chí giết.

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

## 2. Hai cái bẫy phải xử lý trước mọi thứ khác

### 2.1. Ba chỗ dispatch, và `_codex_safe_model`

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

### 2.2. Tool file của engine API KHOÁ TRONG BRAIN, không thấy repo

Đây là chặn cứng, và nó lớn hơn mọi thứ còn lại trong tài liệu này. Phát hiện trong lượt rà
soát chéo 2026-09-22; đã đối chiếu bằng ba dòng code.

Trang Coding đổi `cwd` sang repo qua `_cwd_luot_chat` (`main.py:4800`), nhưng **chỉ engine CLI
hưởng**, vì chúng có tool file native chạy theo `cwd`.

Engine API thì không có tool file native. Chúng đọc ghi qua hub, và hub nhận vault_root từ
`main.py:2190`:

```python
vault_root = _brain_root(brain) if brain else None
```

**Vô điều kiện. Không hỏi `coding_store.cwd_cua_phien(sid)` một lần nào.** Còn
`_builtin_tools._read` (`mcp_hub.py:475`) chặn mọi đường dẫn ngoài vault và trả nguyên văn:

> `ERROR: '<path>' nằm ngoài bộ não đang làm việc nên tool này không đọc được.`

Hệ quả: **`chatgpt-web` ngồi trong một phiên Coding sẽ không đọc nổi một file nào của repo.**
Nó đọc được brain. Repo thì không.

Nghĩa là giao thức tool qua chữ có chạy hoàn hảo đi nữa, model vẫn không coding được. Cái này
phải sửa **trước** Phase 2, không phải để lần sau. Cách sửa ở mục 7.

Lưu ý ranh giới cũ có chủ ý, đừng phá nhầm: nhánh Codex ghi rõ "Hub vẫn trỏ BRAIN kể cả khi
cwd là repo: MCP, cron và nhắc hẹn thuộc về bộ não của người dùng, không thuộc về cây mã
nguồn đang mở" (`main.py` nhánh `openai-oauth`). Đúng cho MCP, cron, nhắc hẹn. Sai cho tool
**file**. Nên mục 7 tách hai thứ đó ra chứ không đổi vault_root của cả hub.

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

`chatgpt-web` nằm ở **hạng API**, không phải hạng CLI. Nó có
`javis_read_file` / `javis_list_dir` / `javis_write_file` / `javis_use_skill`, mọi MCP đã nối,
mọi plugin, `javis_task`, `javis_schedule`.

Hai thứ của hạng CLI nó vẫn **không** có, và mô tả model trên ô chọn phải nói thẳng:
**WebFetch/WebSearch** và **Task** (sub-agent song song).

Còn chạy lệnh thì **mục 7.2 gỡ**, bằng `javis_run_command` chứ không phải Bash native và
không phải PTY. Nhưng đúng như bản rà soát chéo nêu: cấp thế thì **cả sáu engine API cũng
có**, nên đó là quyết định của chủ dự án, không phải chi tiết thi công.

### 3.1. Kiểm đếm tool thật, để khỏi hứa mồm

Đếm từ `mcp_hub.py` và `system/plugins/` ngày 2026-09-22:

| Nhóm | Tool |
|---|---|
| Builtin vault | `javis_read_file`, `javis_list_dir`, `javis_write_file`, `javis_use_skill`, `javis_connections` |
| Điều phối | `javis_task`, `javis_schedule`, `javis_workflow`, `javis_ui` |
| Tiện ích | `javis_now`, `javis_date_add`, `javis_generate_image`, `javis_add_mcp`, `javis_tool_stats`, `javis_youtube_read` |
| Máy | `javis_app_list`, `javis_app_open`, `javis_app_close` |
| Meta, Zalo | `meta_ads_*` (4), `fb_pages_*` (6), `fb_monitor`, `zalo_send_image` |
| MCP | Mọi connector đã nối |

Khoảng **26 tool plugin bundled cộng 5 builtin**, cộng toàn bộ MCP.

Hai điểm dễ tưởng là thiếu mà thật ra có:

- **Đính kèm trong khung chat đọc được.** Hub cho `javis_read_file` đọc thêm vùng `.staging`
  khi `staging=True` (`mcp_hub.py:447`), nên file người dùng vừa kéo vào vẫn tới được model.
- **Tạo ảnh vẫn chạy.** `javis_generate_image` gọi Codex Responses bằng OAuth
  (`system/plugins/image-chatgpt/`), không phụ thuộc phiên trình duyệt.

### 3.2. Sáu thứ thiếu RIÊNG của bản web, ngoài bảng hạng

Đây là phần không nằm trong bảng hạng nào và dễ bị bỏ sót nhất.

1. **Không có function calling.** Không có gì ép model trả đúng khuôn ngoài lời dặn trong
   prompt. Sáu engine API được nhà cung cấp bảo đảm khuôn tool call; model này thì không. Đây
   là rủi ro kỹ thuật lớn nhất của cả dự án, và là tiêu chí giết thứ năm ở mục 13.
2. **Không có system role.** Toàn bộ system prompt của Javis (CLAUDE.md, MEMORY, router skill,
   danh sách tool) phải nhét vào **tin nhắn đầu tiên** như chữ thường. Codex có trường
   `instructions` riêng (`engine._codex_input`), web không có gì cả.
3. **Custom instructions và Memory của chính tài khoản sẽ trộn vào mọi lượt.** API không bao
   giờ có thứ này. Một dòng custom instruction kiểu "luôn trả lời thật ngắn" sẽ bóp mọi câu
   Javis hỏi, và triệu chứng sẽ trông như Javis hỏng. **Thẻ Models phải dặn tắt Memory và
   custom instructions, hoặc dùng một tài khoản riêng.**
4. **Không có số token.** `usage_store.record` sẽ ghi 0, nên trang Sử dụng và trang Tiết kiệm
   **mù với model này**. Bộ đếm tin nhắn ở mục 10 là thứ thay thế duy nhất, và nó là đơn vị
   khác, không so được với các model kia.
5. **Không chỉnh được mức suy nghĩ.** Không có `reasoning effort`, cũng không có prompt
   caching. Web tự quyết theo model chọn trong giao diện của nó.
6. **Ảnh thì ngược đời.** Hạng API của Javis hiện không gửi ảnh cho model (không có
   `image_url` hay `input_image` ở đâu trong `engine.py`), trong khi ChatGPT Web tự nó xem ảnh
   rất tốt. Khai thác được phải lái widget tải file lên; không thuộc tài liệu này, ghi ở mục 17.

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

### Chế độ lazy nhân đôi số vòng, phải biết trước

Hub có tầng lazy (`mcp_hub.py:612-669`): mặc định `auto`, bật khi pool vượt **40 tool** hoặc
**6000 ký tự schema**. Bật rồi thì tool MCP bị giấu sau hai meta-tool `javis_search_tools` và
`javis_run_tool`, nên **mỗi lần dùng một tool MCP tốn hai vòng**: tìm, rồi mới gọi.

Với engine API thì hai vòng đó là hai lời gọi HTTP, không ai để ý. Với `chatgpt-web` thì đó là
**hai lượt gõ vào ô chat**, tức gấp đôi cả thời gian lẫn số tin nhắn. Máy nào đã nối vài
connector là chạm ngưỡng ngay.

Bộ dịch **không được tự tắt lazy** để đi tắt: tắt là đẩy nguyên hàng trăm schema vào tin nhắn
đầu, mà tin nhắn đầu đã phải gánh cả system prompt (mục 3.2 điểm 2). Đây là đánh đổi có thật,
ghi ra để mục 5 tính đúng thời gian, chứ không phải thứ sửa được trong tài liệu này.

## 5. Giá một lượt: tin nhắn rẻ, thời gian mới đắt

Với model này, **một vòng tool là một tin nhắn web**. Một lượt chat tốn:

```
1 tin nhắn  +  số vòng tool
```

Chủ dự án đã chốt: gói chat rất lớn, **số tin nhắn không phải ràng buộc**. Nên giữ trần chung
30 vòng (`JAVIS_MAX_TOOL_ROUNDS`), không đặt trần riêng. Biến `JAVIS_WEB_MAX_TOOL_ROUNDS` vẫn
có, mặc định bằng trần chung, để ai dùng gói nhỏ hơn tự hạ.

### Ràng buộc thật là THỜI GIAN, không phải tin nhắn

Bỏ trần tin nhắn thì lộ ra con số đáng sợ hơn. Một vòng web mất **20 tới 40 giây**. Con số này
là **ƯỚC, chưa đo trên máy thật**; spike ở mục 13 mới cho số thật, và mọi phép nhân dưới đây
phải tính lại theo số đó. Không lấy nó làm giả định kiến trúc.

```
30 vòng × 30 giây  ≈  15 phút cho MỘT lượt chat
```

Và còn nhân hai nữa ở mục 4: chế độ lazy của hub biến mỗi lần dùng tool MCP thành **hai vòng**
(tìm rồi mới gọi). Nên 30 vòng thực tế chỉ là **15 lần gọi tool MCP**, trong 15 phút.

So sánh cho thấy vấn đề: Codex chạy cùng 30 vòng đó trong vài chục giây, vì mỗi vòng là một
lời gọi API chứ không phải một lượt gõ vào ô chat rồi chờ người ta stream ra.

Nên phanh đổi từ đếm tin nhắn sang **đếm giây**:

- `JAVIS_WEB_TURN_BUDGET_S`, **mặc định 600** (10 phút cho một lượt). Hết ngân sách thì dừng
  đúng như chạm trần vòng: trả phần đã có kèm lời giải thích, không cụt lặng lẽ.
- **Hiện tiến độ trong lúc chạy.** Vòng thứ mấy, đã mất bao lâu. Mười lăm phút im lặng thì
  người dùng sẽ tưởng treo và bấm Dừng, kể cả khi nó đang chạy đúng.
- Bộ đếm lượt (`so_luot_trong_ngay`, mục 10) **giữ lại**, nhưng hạ vai trò: nó không còn là
  phanh, chỉ là thứ duy nhất Javis biết về mức tiêu thụ, vì model này không trả số token
  (xem mục 3.2).

Hệ quả thiết kế, nói thẳng để sau khỏi ngạc nhiên: `chatgpt-web` hợp với **câu hỏi cần ít vòng
tool**. Việc nhiều bước vẫn chạy được, chỉ là lâu.

## 6. Mạch hội thoại

Một hội thoại trên chatgpt.com có id riêng và nối tiếp được, y như `codex_thread_id`.

`sessions.py:1160` đã có bảng ánh xạ engine sang cột giữ mạch, kèm lời dặn ngay trong mã:
"Thêm engine giữ phiên mới thì thêm một dòng ở đây, đừng rải thêm một lệnh clear nữa vào
`main.py` - đó chính là cách bảng này bị bỏ sót hai engine."

Làm đúng lời dặn đó: thêm cột `web_thread_id` và một dòng trong `_MACH_NATIVE`.

Bất biến của `clear_native_threads` giữ nguyên và áp dụng cho cả model này: lượt nào chạy bằng
engine khác thì mạch web thành khuyết, nên bị vô hiệu. Đổi model giữa phiên là mở luồng web
mới, không phải nối tiếp luồng cũ.

## 7. Coding Tool Context: thứ phải làm trước Phase 2

Mục 2.2 chỉ ra chặn cứng: engine API đọc ghi qua hub, mà hub khoá trong brain. Mục này là
cách gỡ.

### 7.1. Tách vault_root của TOOL FILE khỏi vault_root của hub

Ranh giới cũ đúng một nửa. MCP, cron và nhắc hẹn thuộc về brain, giữ nguyên. Tool **file** thì
phải theo nơi đang làm việc.

Nên `_builtin_tools` nhận thêm một gốc thứ hai, và `discover_all` truyền xuống:

```
vault_root      = brain          ← MCP, cron, nhắc hẹn, skill: KHÔNG ĐỔI
workspace_root  = cwd của phiên  ← tool file: repo/worktree khi ở trang Coding
```

`workspace_root` lấy đúng từ nguồn mà engine CLI đang dùng, không suy từ tên kênh:

```python
workspace_root = coding_store.cwd_cua_phien(sid)   # "" = không phải phiên coding
```

Rỗng thì `workspace_root = vault_root` và mọi thứ chạy y như hôm nay. Đây là điều kiện để thay
đổi này không đụng một lượt chat thường nào.

`_safe_read_path` cho qua đường dẫn nằm trong **một trong hai** gốc, và câu báo lỗi phải nói
rõ đang ở gốc nào, vì câu hiện tại ("nằm ngoài bộ não đang làm việc") sẽ sai nghĩa ngay khi có
gốc thứ hai.

### 7.2. `javis_run_command`, KHÔNG phải PTY của `terminal.py`

Bản rà soát chéo 2026-09-22 bác đề xuất cho model lái thẳng PTY của `terminal.py`, và bác
đúng. Chính docstring của file đó ghi:

> Shell thừa kế env của server (trong đó có API key trong .env) - đúng như mọi terminal khác
> của chủ máy, nhưng cần biết là nó ở đó. (`terminal.py:29`)

PTY còn là shell **sống lâu**, có trạng thái, sinh ra cho con người ngồi gõ. Giao nó cho model
là cấp cả env chứa khoá lẫn một phiên có trạng thái mà không ai kiểm được.

Nên tool riêng, một lệnh một lần, không trạng thái:

| Tham số | Ý nghĩa |
|---|---|
| `command` | Lệnh chạy |
| `cwd` | **Bỏ qua nếu nằm ngoài `workspace_root`.** Mặc định là `workspace_root` |
| `timeout` | Trần giây, có mặc định và có trần trên |

Bắt buộc: env **lọc trắng**, không thừa kế env server; trần kích thước output; huỷ được; ghi
audit; và mức quyền ánh xạ thẳng từ chip của phiên:

| Mức của `coding_store` | `javis_run_command` |
|---|---|
| `suggest` | Không chạy. Trả về lệnh đề xuất dưới dạng chữ |
| `auto` | Chỉ lệnh trong allowlist, và chỉ trong `workspace_root` |
| `full` | Chạy đầy đủ |

**Allowlist của mức `auto` phải viết ra thành danh sách**, không để mỗi lần đoán. Đây là lần
đầu Javis cần một allowlist lệnh thật: Codex không có allowlist per-call, nó chỉ chặn ở tầng
sandbox (`aux_engine.py:18-21`), còn Claude Code có allowlist nhưng của riêng CLI đó. Coi đây
là một hạng mục thiết kế, không phải một dòng cấu hình.

`min_mode` của tool này là `full` theo phân loại của hub, và mức quyền phiên siết thêm bên
trên. Hai lớp, không thay nhau.

### 7.3. Bộ tool coding tối thiểu

Có `workspace_root` và `javis_run_command` rồi thì bộ còn lại gần như miễn phí, vì chúng chỉ
là lệnh git gói lại:

```
đọc file, ghi file, liệt kê, tìm trong file   ← builtin, đổi gốc là xong
git status, git diff                          ← javis_run_command
chạy test                                     ← javis_run_command
```

Đây mới là thứ làm `chatgpt-web` coding được. Giao thức tool qua chữ chỉ là cách gọi; không có
mục này thì gọi xong cũng không chạm được vào repo.

### 7.4. Ranh giới

Thay đổi này **chạm tới cả sáu engine API**, không riêng `chatgpt-web`. Đó là điều tốt (chúng
cũng đang không coding được), nhưng phải nói ra: đây là nới năng lực cho một nhóm engine, nên
là quyết định của chủ dự án chứ không phải chi tiết thi công.

Ba thứ **không** đổi: vault_root của MCP, của cron, của nhắc hẹn.

## 8. Thẻ ChatGPT ở trang Models

Thẻ đã có, thêm vào đó:

- Dòng trạng thái phiên web: `Đã đăng nhập` / `Chưa đăng nhập` / `Đang nghỉ tới HH:MM`.
- Nút **Mở cửa sổ đăng nhập**. Không có ô nhập mật khẩu, không bao giờ.
- Bộ đếm `đã hỏi N lượt hôm nay` cộng mốc chạm trần gần nhất.
- Mô tả model `chatgpt-web` nói thẳng: không có WebFetch/WebSearch, không có Task, mỗi vòng
  tool mất 20 tới 40 giây (số ước, mục 5).
- **Lời dặn tắt Memory và Custom instructions** của chính tài khoản ChatGPT, hoặc dùng tài
  khoản riêng. Mục 3.2 điểm 3 là lý do: không tắt thì cài đặt cá nhân bóp mọi câu Javis hỏi,
  và triệu chứng trông như Javis hỏng.

Thẻ sẵn sàng khi Codex CLI dùng được **hoặc** phiên web đã đăng nhập (mục 1).

## 9. Transport: để trang tự xác thực, Javis chỉ đọc dây

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

## 10. Trạng thái và phân loại lỗi

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

## 11. Ranh giới an toàn và rủi ro

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

## 12. Cổng 0: trả lời trước khi viết dòng mã nào

**Pool Codex của chủ máy có thật sự đang cạn không?**

Mở `usage_store` / `usage_index` ra xem. Javis **đã** tiêu được quota gói ChatGPT không cần
API key (`engine.py:1005`, `engine.py:1022`), nên việc này chỉ thêm đúng một thứ: tiêu pool
tin nhắn chat thay vì pool Codex. Chưa cạn thì dự án không có lợi ích gì.

Ghi câu trả lời vào chính tài liệu này trước khi đi tiếp.

## 13. Spike một ngày, có tiêu chí giết

Đặt tiêu chí **trước** khi chạy:

- 10 câu hỏi liên tiếp trong 30 phút, **ít nhất 9 câu trả về đúng nội dung**
- **Không có thử thách nào** cần tay người trong 10 lượt đó
- Độ trễ trung vị **dưới 60 giây** với prompt khoảng 2.000 token
- Đoạn tee bắt được luồng ở **cả hai cảnh**: mở nguội và tab đã mở sẵn
- **Một vòng tool đi trọn**: model trả đúng khối ```` ```javis_tool ````, Javis bóc được, chạy
  được, gửi lại được, và model dùng kết quả đó trả lời

Tiêu chí cuối là tiêu chí mới của v2.0 và là tiêu chí dễ trượt nhất. Không đạt đủ năm thì
**dừng dự án**, ghi kết quả vào đây, và tài liệu này thành bản ghi vì sao không làm.

## 14. Lộ trình

| Bước | Nội dung | Ước lượng |
|---|---|---|
| Cổng 0 | Xem pool Codex đã cạn chưa | 30 phút, không mã |
| Spike | Tee fetch cộng một vòng tool đi trọn, chấm theo mục 13 | 1-2 ngày |
| **Phase 0** | **Coding Tool Context (mục 7): `workspace_root` cho tool file, `javis_run_command`, allowlist mức `auto`.** Chặn cứng, phải xong trước Phase 2 | 3-4 ngày |
| Phase 1 | `web_chat.py`: transport, sổ trạng thái, thẻ Models, nút đăng nhập. Chưa có tool, chat thuần | 2-3 ngày |
| Phase 2 | Bộ dịch tool qua chữ, trần vòng riêng, bộ đếm lượt. Đây là phần khó nhất | 3-4 ngày |
| Phase 3 | `web_thread_id`, nối tiếp luồng, `limit_resume` khi hết lượt giữa vòng tool | 1-2 ngày |

Phase 1 tự nó đã dùng được (chat thuần, không tool), nên nếu Phase 2 sa lầy thì vẫn có thứ
chạy được chứ không phải bỏ trắng.

## 15. Không làm

- Thêm provider mới. Mục 1 là lý do.
- DeepSeek Web. API DeepSeek rẻ hơn công sức xây và vá bridge; muốn DeepSeek thì thêm provider
  API OpenAI-compatible, một buổi chiều, không thuộc tài liệu này.
- Tự giải proof-of-work, tự dựng request `backend-api`, đụng cookie hay token.
- Ô nhập mật khẩu ChatGPT trong Javis.
- Chạy trên VPS.
- Việc nền tự chọn `chatgpt-web`.
- Cho model lái thẳng PTY của `terminal.py`. Mục 7.2 là lý do: PTY thừa kế env server chứa
  khoá, và là shell sống lâu có trạng thái.

## 16. Test

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
- `test_web_chat_ngan_sach_gio.py`: hết `JAVIS_WEB_TURN_BUDGET_S` thì dừng và trả phần đã có
  kèm lời giải thích, không cụt lặng lẽ; và trần vòng mặc định bằng `JAVIS_MAX_TOOL_ROUNDS`
  chứ không phải một con số riêng.
- `test_web_chat_state.py`: `HET_LUOT` đặt đúng `cooldown_until`; trong cooldown thì từ chối mà
  **không** mở trình duyệt; hết lượt giữa vòng tool thì giữ phần đã làm và vào `limit_resume`.
- `test_web_chat_tee.js`: chạy đoạn JS tee trên một trang tĩnh phát SSE giả, ghép lại đúng
  nguyên văn; luồng đứt giữa chừng thì `QUA_HAN` chứ không trả chuỗi cụt.
- `test_web_chat_viec_nen.py`: `_FallbackChain` và hàng đợi việc nền không bao giờ chọn
  `chatgpt-web`.
- `test_coding_tool_context.py`: phiên coding thì `javis_read_file` đọc được file trong repo;
  phiên thường thì `workspace_root` bằng `vault_root` và hành vi **không đổi một chút nào**;
  đường dẫn ngoài cả hai gốc vẫn bị chặn, và câu báo lỗi nói đúng gốc nào.
- `test_run_command_quyen.py`: `suggest` không chạy lệnh nào; `auto` chỉ chạy lệnh trong
  allowlist và từ chối `cwd` ngoài `workspace_root`; env truyền xuống **không** chứa biến của
  server; quá `timeout` thì bị giết và báo rõ.

## 17. Để lần sau

- Lệnh phiên `/web` và chip "hỏi Web lượt tới" trong phiên Coding, để hỏi một câu mà vẫn ở
  trên Codex. Đã đặc tả trong v1.0 mục 7 (bản cũ); rẻ, nhưng chỉ làm sau khi đường chọn model chạy ngon.
- Gửi ẢNH cho `chatgpt-web` bằng cách lái widget tải file của trang. Mục 3.2 điểm 6: hạng API
  của Javis hiện không gửi ảnh, trong khi ChatGPT Web tự nó xem ảnh rất tốt.
- **Chrome Extension Relay** thay cho việc server Javis tự giữ profile Chrome mãi:
  `Javis server ↕ relay có xác thực ↕ extension ↕ tab ChatGPT đã đăng nhập`. Hợp với VPS hơn
  hẳn Playwright, và chủ dự án vốn đã định làm extension. Playwright profile cố định vẫn là
  đường đúng cho spike. Cần kiểm trước: service worker MV3 bị kill khi rảnh, nên kết nối dài
  có thể phải qua offscreen document.
- Máy trạng thái provider dùng chung cho mọi nhà, bê từ sổ mục 10 ra.
- Task Handoff Packet (bản rà soát 2026-09-22).
- Version guard cho Codex CLI: `install.sh:143` và `update.sh:50` đang cài
  `@openai/codex@latest` vô điều kiện, không có supported range, không có smoke test.
