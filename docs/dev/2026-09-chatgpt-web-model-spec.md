# ChatGPT Web: một model của thẻ ChatGPT

**Phiên bản:** v4.0. Gộp bản rà soát chéo `JAVIS_OS_WEB_ENGINE_SPEC.md` (2026-09-22) vào v3.0:
thêm mục 18-22, và ĐÍNH CHÍNH một chỗ v2.0/v3.0 nói quá (mục 3).
**Trạng thái:** chốt phạm vi và chốt mục đích. **Chưa viết mã**; cổng duy nhất là spike ở
mục 13.
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

**Làm rõ thứ ba, và đây là chỗ hai bản trước hiểu SAI mục đích.** v1.0 tới v2.1 đều viết như
thể `chatgpt-web` là đường dự phòng: Codex hết quota thì đổi sang. Chủ dự án nói thẳng **không
phải vậy**:

> Bản web là bản dùng để làm các task thông thường, vì nó unlimited quota. Chọn web hay Codex
> là tuỳ cái nào tiện hơn, không phải tuỳ cái nào còn quota. Bản web có một số hạn chế thì
> chấp nhận.

Việc thường ngày mà chủ dự án kể: hỏi đáp, tạo ảnh, nhắc lịch, đọc, hiểu, lên kế hoạch, triển
khai, lập trình.

Ba hệ quả, và chúng đổi cả lộ trình:

1. **Cổng 0 cũ chết.** Nó hỏi "pool Codex đã cạn chưa". Câu đó không còn liên quan. Cổng duy
   nhất còn lại là spike ở mục 13: giao thức có chạy không.
2. **Task Handoff Packet rời khỏi phạm vi dự án này.** Nó sinh ra cho cảnh "Codex chết giữa
   chừng thì web tiếp quản". Vẫn là việc đáng làm cho Javis, nhưng không phải việc của tài
   liệu này.
3. **Phần lớn việc chủ dự án kể tốn 1 tới 3 vòng tool, không phải 15.** Mục 5 tính lại theo
   đó, và lộ trình ở mục 14 xếp lại để thứ dùng nhiều nhất tới trước.

Giữ lại từ v1.0: transport (mục 9), sổ trạng thái và phân loại lỗi (mục 10), ranh giới an
toàn (mục 11), spike và tiêu chí giết.

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

Nghĩa là giao thức tool qua chữ có chạy hoàn hảo đi nữa, model vẫn không coding được. Cách sửa
ở mục 7.

Đây là chặn cứng **của riêng nhánh lập trình**, không chặn hỏi đáp, tạo ảnh, nhắc lịch, đọc
vault hay skill. Vì thế lộ trình xếp nó ở Phase 4 chứ không phải đầu (mục 14 giải thích).

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

**Đính chính của v4.0.** Bản v2.0 và v3.0 viết rằng sáu chỗ này "chi phối đường tắt fast-path,
ngân sách ngữ cảnh và nhãn thuê bao", và nếu `chatgpt-web` không có tool thì "cả sáu nói dối".
Đọc lại từng chỗ thì **nói quá**:

| Chỗ | Thật ra làm gì |
|---|---|
| `main.py:12101`, `main.py:16729` | Chỉ hẹn `_schedule_registry_discovery_shadow`, tức chạy SHADOW |
| `main.py:15091` | Nhãn `thue_bao` trên trang chẩn đoán |
| `main.py:15568` | Nhánh theo `kind_hien_tai` |
| `fast_path_runtime.py:282`, `adaptive_context_runtime.py:322` | Đổi hành vi thật, nhưng **canary allocation mặc định 0** |

Nên hậu quả của việc sai bất biến này là **nhỏ**: shadow và nhãn, không phải lượt chat hỏng.
Vẫn phải làm đúng, nhưng đừng lấy nó làm lý do chặn Phase 1.

Cho nó tool thì bất biến giữ nguyên, không đụng chỗ nào trong sáu chỗ đó. Cộng thêm: đó chính
là thứ chủ dự án muốn từ đầu, "vẫn dùng được tool như bản Codex".

**Hệ quả cho Phase 1 (chat thuần, chưa tool):** trong cửa sổ đó `chatgpt-web` mang
`kind: "oauth"` mà không có tool. Chấp nhận được vì hậu quả chỉ là shadow và nhãn, nhưng phải
có một dòng trong nhật ký chạy nói rõ, kẻo trang chẩn đoán nói sai mà không ai biết vì sao.

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

### Nhưng phần lớn việc thường ngày chỉ tốn 1 tới 3 vòng

Con số 15 phút ở trên là trường hợp XẤU NHẤT, và nó chỉ xảy ra với việc lập trình nhiều bước.
Đếm theo đúng danh sách việc mà chủ dự án kể:

| Việc | Vòng tool | Thời gian ước |
|---|---|---|
| Hỏi đáp, lên kế hoạch, đọc hiểu một đoạn | 0 | một lượt web |
| Tạo ảnh (`javis_generate_image`) | 1 | dưới 1 phút cộng thời gian dựng ảnh |
| Nhắc lịch (`javis_schedule`) | 1 | dưới 1 phút |
| Đọc file trong brain, dùng skill | 1-3 | 1-2 phút |
| Lập trình nhiều bước | 10-30 | 5-15 phút |

Nên **độ trễ không phải vấn đề cho phần lớn việc thường ngày**. Nó chỉ thành vấn đề ở nhánh
lập trình, và đó cũng chính là nhánh mà Codex tiện hơn. Chọn cái nào tiện hơn là đúng cách
dùng, không phải giải pháp tạm.

Một điều chính xác về tạo ảnh, để sau khỏi tưởng nhầm: `javis_generate_image` gọi
`image_gen.generate_chatgpt`, đi đường **OAuth Responses**, không đi qua phiên trình duyệt.
Nghĩa là nó tiêu hạn mức ảnh của gói qua đường API, không tiêu lượt chat web. Chạy được, chỉ
là đừng nhầm nó với quota web. Muốn ảnh sinh thẳng trong phiên web thì phải bóc ảnh từ trang
và tải về, ghi ở mục 17.

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

## 12. Đổi qua lại giữa web và Codex

Mục đích ở khối đầu tài liệu là "cái nào tiện hơn thì dùng", nên việc đổi phải nhẹ như đổi
model, không phải như đổi cấu hình.

**Cơ chế đã có sẵn, không phải làm mới:** kho phiên giữ model GHIM THEO TỪNG PHIÊN
(`sessions.set_pinned_model`, `sessions.py:740`; endpoint ở `main.py:14349`). Nên:

```
Phiên "hỏi đáp hằng ngày"   ghim chatgpt-web
Phiên "sửa repo javis-os"   ghim gpt-5-codex
```

Hai phiên sống song song, mỗi phiên nhớ model của nó, không ai đạp lên ai. Đổi trong một phiên
thì chọn lại ở ô chọn model như mọi model khác.

Đây cũng là lý do mục 2.1 quan trọng tới vậy: `_codex_safe_model` hiện **ghi đè cả model ghim
của phiên**. Không chặn nó thì đúng cơ chế đang phục vụ mục đích này bị hỏng.

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

Xếp theo **thứ tự việc chủ dự án dùng nhiều nhất**, không theo thứ tự kỹ thuật. Mỗi phase
phải tự nó dùng được.

| Bước | Nội dung | Mở khoá việc gì | Ước lượng |
|---|---|---|---|
| Spike | Tee fetch cộng một vòng tool đi trọn, chấm theo mục 13 | (cổng duy nhất) | 1-2 ngày |
| Phase 1 | `web_chat.py`: transport, sổ trạng thái, thẻ Models, nút đăng nhập, model vào ô chọn, chặn bẫy mục 2.1. Chat thuần | Hỏi đáp, lên kế hoạch, đọc hiểu | 2-3 ngày |
| Phase 2 | Bộ dịch tool qua chữ, ngân sách giờ, bộ đếm | **Tạo ảnh, nhắc lịch, đọc vault, skill, MCP.** Phần lớn giá trị nằm ở đây | 3-4 ngày |
| Phase 3 | `web_thread_id`, nối tiếp luồng, xoay mạch khi phình (mượn `compaction.nen_mach_thue_bao`) | Dùng hằng ngày không phải dựng lại ngữ cảnh mỗi lượt | 1-2 ngày |
| Phase 4 | Coding Tool Context (mục 7): `workspace_root`, `javis_run_command`, allowlist mức `auto` | Lập trình | 3-4 ngày |

**Vì sao Coding Tool Context xuống cuối, dù v2.1 xếp nó đầu:** v2.1 tưởng mục tiêu là "web thay
Codex khi Codex chết", nên coding là bắt buộc. Mục tiêu thật là việc thường ngày, mà trong đó
lập trình là một nhánh, và là đúng nhánh Codex tiện hơn. Nó vẫn là chặn cứng **cho nhánh lập
trình**, nhưng không chặn bốn nhóm việc kia.

Phase 3 lên trước Phase 4 cũng vì lý do đó: dùng hằng ngày mà mỗi lượt phải dựng lại ngữ cảnh
từ đầu thì vừa chậm vừa tốn, và cái đó chạm vào mọi lượt chứ không riêng lượt coding.

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

## 18. Nén kết quả tool trước khi gửi lại

Một vòng web đắt về thời gian, và tin nhắn đầu đã gánh cả system prompt. Nên kết quả tool
**không được đổ nguyên si** vào lượt sau.

| Tool | Trả về gì |
|---|---|
| Đọc file | Khoảng liên quan, hoặc cắt ở trần. Không bao giờ nguyên file lớn |
| Chạy test | Mã thoát, danh sách test hỏng, phần stderr/stdout cuối liên quan |
| Tìm trong file | Danh sách khớp đã xếp hạng, không phải mọi dòng |
| `git diff` | Cắt theo trần, quá thì tóm tắt số file và số dòng |

Model thiếu thì gọi lại xin thêm. Một vòng xin thêm rẻ hơn một lượt bị đầy ngữ cảnh.

## 19. Hợp đồng sự kiện chung giữa các engine

Javis đã có hợp đồng ngầm: mọi engine sinh dict `{"type": ...}` mà `CodexCLI.query` và
`claude_sdk_engine` cùng tuân theo (`type` nhận `session`, `text`, `tool_call`, `item`,
`final`, `error`, `usage`).

Web Engine **map vào đúng hợp đồng đó**, không đẻ hợp đồng thứ hai. Cụ thể:

```
transport nhận mảnh chữ      → {"type": "text"}
mở luồng web mới             → {"type": "session"}
bóc được khối javis_tool     → {"type": "tool_call"}
xong lượt                    → {"type": "final"}
lỗi transport / hết lượt     → {"type": "error"}
```

Không có `usage` vì web không trả số token (mục 3.2). Dashboard không phải sửa gì.

## 20. Cờ năng lực của engine

Để giao diện và bộ chọn tool khỏi đoán, mỗi engine khai năng lực thật. `chatgpt-web` theo
từng phase:

| Cờ | Phase 1 | Phase 2 | Phase 4 |
|---|---|---|---|
| `chat` | có | có | có |
| `tools` | **không** | có | có |
| `files` | không | có | có |
| `mcp` | không | có | có |
| `coding` | không | không | có |
| `shell` | không | không | có |
| `vision` | không | không | không |
| `web_image_generation` | không | không | không |
| `native_thread` | có (Phase 3) | có | có |
| `reasoning_control` | không | không | không |
| `usage_tokens` | không | không | không |
| `background` | không | không | không |

**Không khai một cờ chưa chạy được.** Khai thừa là hứa với chính bộ chọn tool của Javis, rồi
nó gửi xuống một tool mà engine không dùng nổi.

## 21. Sinh ảnh: hai đường, và phải nói rõ đường nào

Mục 5 đã nêu: `javis_generate_image` đi OAuth Responses, **không** qua trình duyệt. Nên khi
đang chọn `chatgpt-web` mà bảo tạo ảnh, ảnh vẫn ra, nhưng tiêu hạn mức ảnh qua API chứ không
tiêu lượt chat web.

Luật:

- Engine là `chatgpt-web` thì đường mặc định **nên** là sinh ảnh trong chính phiên web, khi
  năng lực đó có (cờ `web_image_generation`).
- Chưa có thì **được phép** dùng `javis_generate_image`, nhưng **phải nói ra**: "ảnh này tạo
  qua đường API của gói, không qua phiên web".
- **Không bao giờ** lặng lẽ tiêu hạn mức của túi khác. Chủ máy chọn engine nào là chọn cả túi
  quota của engine đó.

Đường web (để lần sau, mục 23): gọi luồng tạo ảnh của trang, chờ xong, bóc ảnh ra, tải về
`attachments/` rồi nhúng như mọi ảnh khác.

## 22. Đo đạc và versioning transport

**Đo được gì thì đo, đừng bịa cái không đo được.** Web không trả token, nên bỏ hẳn cột token
cho model này và đo thứ khác:

```
web_turns          tool_rounds        tool_batch_size
wall_time          repair_rounds      transport_errors
challenge_count    session_expiry     task_completed
```

Hai chỉ số đáng nhìn nhất: **thời gian trung vị một lượt** và **tỷ lệ lượt xong không cần vòng
sửa khuôn**. Cái thứ hai chính là thước đo sức khoẻ của giao thức tool qua chữ.

**Versioning.** Transport web mong manh theo bản chất, nên ghi phiên bản của ba thứ và để test
bắt được khi trang đổi:

```
transport_version        đoạn tee fetch
selector_version         selector DOM (ô soạn, nút gửi, nút tải file)
tool_protocol_version    khuôn khối javis_tool
```

Mọi selector DOM nằm **trong một chỗ duy nhất** của transport. Rải selector khắp nơi là lần
sau OpenAI đổi giao diện thì phải đi tìm.

## 23. Để lần sau

- Lệnh phiên `/web` và chip "hỏi Web lượt tới" trong phiên Coding, để hỏi một câu mà vẫn ở
  trên Codex. Đã đặc tả trong v1.0 mục 7 (bản cũ); rẻ, nhưng chỉ làm sau khi đường chọn model chạy ngon.
- Gửi ẢNH cho `chatgpt-web` bằng cách lái widget tải file của trang. Mục 3.2 điểm 6: hạng API
  của Javis hiện không gửi ảnh, trong khi ChatGPT Web tự nó xem ảnh rất tốt.
- **Chrome Extension Relay** thay cho việc server Javis tự giữ profile Chrome mãi:
  `Javis server ↕ relay có xác thực ↕ extension ↕ tab ChatGPT đã đăng nhập`. Hợp với VPS hơn
  hẳn Playwright, và chủ dự án vốn đã định làm extension. Playwright profile cố định vẫn là
  đường đúng cho spike. Cần kiểm trước: service worker MV3 bị kill khi rảnh, nên kết nối dài
  có thể phải qua offscreen document.
- **Sinh ảnh THẲNG trong phiên web** (mục 21): gọi luồng tạo ảnh của trang, chờ xong, bóc ảnh,
  tải về `attachments/`. Đây là điều kiện để cờ `web_image_generation` bật được.
- **Nhận ảnh và file đính kèm qua widget tải lên của trang**, để bật cờ `vision`.
- **Engine Registry**: gom việc dựng engine vào một chỗ thay cho 72 nhánh `provider ==` rải
  trong `main.py`. Là refactor dần, và KHÔNG được chặn Phase 1: bản rà soát chéo xếp nó thành
  bước 1, làm vậy thì nhiều tuần nữa mới có thứ chạy được.
- Máy trạng thái provider dùng chung cho mọi nhà, bê từ sổ mục 10 ra.
- Task Handoff Packet (bản rà soát 2026-09-22). Đáng làm cho Javis, nhưng KHÔNG thuộc dự án
  này: nó sinh ra cho cảnh chuyển engine giữa chừng, mà mục đích ở đây là chọn tay theo tiện.
- Sinh ảnh THẲNG trong phiên web (bóc ảnh từ trang rồi tải về) để tiêu quota web thay vì hạn
  mức ảnh qua API. Xem mục 5.
- Version guard cho Codex CLI: `install.sh:143` và `update.sh:50` đang cài
  `@openai/codex@latest` vô điều kiện, không có supported range, không có smoke test.
