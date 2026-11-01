# Models & engine

***Tiếng Việt** · [English](en/10-models-and-engines.md)*

Trang **Models** là nơi bạn chọn "bộ não" cho Javis: đăng nhập vào nhà cung cấp AI, xếp thứ tự dùng các nhà đó (thẻ trên cùng là model chính, các thẻ sau là dự phòng), chọn model và mức suy nghĩ cho từng nhà, và chọn model rẻ cho việc chạy nền. Đây là trang quyết định Javis thông minh tới đâu và tiêu hạn mức của gói nào.

Nếu bạn mới bắt đầu, xem trước [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md). Khi cần gắn thêm công cụ ngoài cho Javis, xem [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md).

## Tính năng này là gì

Javis có thể chạy trên nhiều "engine" (nhà cung cấp AI) khác nhau. Các nhà bạn đã kết nối nằm trong một danh sách **Thứ tự dùng**: thẻ trên cùng là **MAIN** (model chính cho hội thoại), các thẻ sau là **Dự phòng 1, 2...**, chat tự chuyển xuống khi thẻ trên hết lượt. Ngoài ra:

- **Model việc nền**: model rẻ hơn cho những việc Javis tự chạy khi bạn không ngồi đó - loop, việc Kanban, nhắc hẹn, tự học, tiêu hoá nguồn.
- **Effort (mức suy nghĩ)**: mức độ model động não trước khi trả lời. Mỗi thẻ nhà cung cấp có mức riêng, model việc nền cũng có mức riêng.

Điểm quan trọng nhất cần hiểu: **đổi model KHÔNG làm Javis mất chức năng.** Mọi provider đều được cấp cùng một bộ đồ nghề qua trung tâm kết nối (MCP Hub) của Javis: gọi kho Kết nối đã đấu, đọc/ghi file trong brain, chạy skill, giao việc Kanban (tool `javis_task`), tạo agent/workflow/loop/nhắc hẹn (tool `javis_schedule`).

| Cách gọi | Provider | MCP Javis · tool file brain · skill | Chạy lệnh máy (Bash) |
|---|---|---|---|
| Qua **Claude Code** | Claude Code | Có - MCP native + skill native | **Có** |
| Qua **Codex** | OpenAI OAuth (ChatGPT) | Có - MCP qua hub (cả kết nối local như Zalo/Webcake) + kho MCP GỐC của Codex (server bạn tự `codex mcp add`) + skill qua router (`javis_use_skill` / đọc file `skills/`) | **Có** |
| Qua **Antigravity CLI** | Google Antigravity CLI (`agy`) | Có - MCP qua hub (ghi vào `~/.gemini/config/mcp_config.json`, xem B1b) + skill qua router | **Có** |
| **Gọi API thẳng** | OpenRouter | Có - MCP qua hub + tool file vault + skill qua router | Không |
| **Gọi API thẳng** | OpenAI (API) | Có - như trên | Không |
| **Gọi API thẳng** | Anthropic (API) | Có - như trên | Không |
| **Gọi API thẳng** | Google Gemini (API) | Có - như trên (từ 0.9.270 trang Kết nối cũng hết báo nhầm) | Không |
| **Gọi API thẳng** | Groq (API) | Có - như trên | Không |
| **Gọi API thẳng** | DeepSeek (API) | Có - như trên | Không |
| **Gọi API thẳng** | Ollama Cloud | Có - như trên | Không |

### Bốn thứ engine API không có

Trước 0.17.1 trang này ghi "khác biệt **duy nhất** là chạy được lệnh máy hay không". Nói vậy gọn nhưng không đúng. Danh sách thật:

- **Lệnh máy (Bash)** - chạy lệnh trên máy chủ.
- **WebFetch và WebSearch** - tự mở một URL lạ ra đọc, tự tra web. Engine API muốn lấy dữ liệu ngoài thì phải qua một MCP đã đấu.
- **Task** - đẻ agent con chạy song song trong cùng một lượt.
- **Nối lại phiên cũ của CLI** - engine API dựng lại ngữ cảnh mỗi lượt.

Thêm một giới hạn thực dụng của engine API: mỗi lượt có **trần số vòng gọi tool** (quá thì dừng và báo). Câu trả lời thì hiện dần từng chữ như engine CLI, kể cả khi lượt **có gọi tool** (từ 0.438.5).

Ngoài từng ấy, mọi năng lực còn lại là như nhau. Cụ thể là: gọi mọi MCP đã đấu, đọc và ghi file trong brain, đọc file bạn vừa đính kèm hoặc dán vào khung chat, chạy skill, giao việc Kanban, tạo loop và nhắc hẹn, tạo agent/workflow/skill (chúng chỉ là file `.md` trong vault), tạo ảnh, dùng tool của plugin.

> **Đọc file đính kèm trên engine API có từ 0.43.1.** Trước đó `javis_read_file` chỉ nhìn thấy bên trong brain, trong khi file bạn kéo-thả hay dán vào khung chat lại rơi xuống `.staging` ở ngoài - nên engine API báo lỗi rồi bảo bạn tự chép file vào thư mục Brain. Nay tool đó nhận cả đường dẫn file vừa đính kèm. Vẫn CHỈ đúng thư mục nhận file đó và CHỈ để đọc: ghi vẫn khoá trong brain, và chatbot nói chuyện với khách của bạn thì không thấy mấy file này.

> **Giao việc Kanban từ engine API có từ 0.17.1.** Trước đó đường duy nhất là `POST /kanban/task`, mà gọi được nó thì phải có Bash và curl - nên chỉ Claude Code với Codex làm được, dù tài liệu vẫn hứa mọi bộ não đều làm được. Nay có tool `javis_task` đi qua hub nên lời hứa đó thành đúng.

Nói ngắn gọn: **năng lực nằm ở Javis, không nằm ở model.** Ba engine CLI (**Claude Code** với gói Claude, **Codex** với gói ChatGPT, **Antigravity CLI** với gói Google) tận dụng chính gói subscription bạn đang trả và chạy thêm được lệnh máy; sáu provider API chỉ cần một API key và làm được mọi thứ còn lại - kể cả điều phối việc, tạo loop, chạy skill. Agent trong Workflow cũng chọn được model theo nhà cung cấp - xem [Agents & Workflows](07-agents-va-workflows.md).

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định ở cổng `7777`).
2. Ở thanh bên trái, mở nhóm **Kết nối**, rồi bấm mục **Models**.
3. Tab **Cloud Model** hiện 2 khối theo thứ tự: **◆ Thứ tự dùng** ("nhà đã đăng nhập, thẻ trên cùng là MAIN") và **◆ Model việc nền** ("loop · việc Kanban · nhắc hẹn · tự học"). Dưới cùng là nút **＋ Kết nối thêm nhà cung cấp (N)**, bấm vào mới hiện các nhà chưa kết nối. Từ 0.406.0, khi chưa có nhà nào đăng nhập (lần đầu vào), nút này lên **trên cùng** và danh sách các nhà mở sẵn để bắt đầu ngay. Mỗi khối có nút (i) bên cạnh tên, bấm để đọc giải thích ngắn.

> **Trang Models gọn lại ở 0.351.0.** Trước đó trang có 4 khối (**◆ Main Model**, **◆ Providers**, **◆ Model việc nền**, **◆ Suy nghĩ**) cộng một ô Model Telegram. Nay Main Model và Providers gộp thành **Thứ tự dùng**, mức Suy nghĩ chung thay bằng chip **Effort** trên từng thẻ, còn Telegram đi theo MAIN (xem [Telegram](11-telegram.md) để ghim model cho riêng một cuộc trò chuyện bằng `/model`).

## Mười provider có sẵn

Bảng dưới là các nhà cung cấp có sẵn. Nhà **đã kết nối** nằm trong khối **Thứ tự dùng** theo thứ tự bạn xếp. Nhà **chưa kết nối** không hiện ra cho đỡ rối: chúng nằm sau nút **＋ Kết nối thêm nhà cung cấp (N)** ở cuối trang (N là số nhà đang chờ), bấm vào là hiện thẻ của chúng kèm form đăng nhập hoặc ô dán key như thường. Kết nối xong, nhà đó vào **cuối** Thứ tự dùng.

| Provider (nhãn trên màn hình) | Kiểu kết nối | Ghi chú |
|---|---|---|
| **Claude Code** | Đăng nhập Claude Code, không cần key | Đầy đủ MCP/skill/tool máy. Thường là thẻ MAIN mặc định |
| **OpenAI OAuth (ChatGPT)** | Device code (đăng nhập gói ChatGPT) | Chạy qua Codex, đấu kho Kết nối qua hub + dùng skill qua router |
| **xAI Grok Build CLI** | Đăng nhập **ngay trên trang Models** (device code), không cần key | Dùng gói **SuperGrok / X Premium+** sẵn có. Chạy qua binary `grok`. Đầy đủ MCP/skill/tool máy, nối lại được mạch hội thoại. Là thẻ CLI **duy nhất đăng nhập được khi Javis chạy trên VPS** - xem [B1a](#b1a-kết-nối-grok-build-cli-dùng-gói-supergrok--x-premium) |
| **Google Antigravity CLI** | Gõ `agy` **một lần trong terminal**, không cần key | Bản Google chỉ định thay Gemini CLI. Chạy qua binary `agy`. Đầy đủ MCP/skill/tool máy, và chọn được **đúng dàn model của Antigravity IDE** (có cả model không phải của Google) |
| **OpenRouter** | Dán API key | Nhiều model 1 chỗ, MCP + tool file + skill qua hub |
| **Anthropic (API)** | Dán API key | MCP + tool file + skill qua hub (từ 0.9) |
| **OpenAI (ChatGPT API)** | Dán API key | MCP + tool file + skill qua hub |
| **Google Gemini (API)** | Dán API key | MCP + tool file + skill qua hub |
| **Groq (API)** | Dán API key | MCP + tool file + skill qua hub. Suy luận rất nhanh, hợp làm model việc nền. Key này còn là thứ cho phép **ra lệnh bằng ghi âm trên Telegram và Zalo** (Whisper nghe giọng thành chữ) - xem [Telegram](11-telegram.md) và [Kênh Zalo Bot](26-kenh-zalo-bot.md); đấu key là đủ, không bắt buộc đổi model chính sang Groq |
| **DeepSeek (API)** | Dán API key lấy ở platform.deepseek.com | MCP + tool file + skill qua hub. Model `deepseek-flash` (rẻ, nhận ảnh) và `deepseek-v4-pro`. Độ sâu suy nghĩ để **Tắt** thì DeepSeek trả lời thẳng; bật lên thì nó suy nghĩ trước, và nếu cuộc trò chuyện cũ không hợp chế độ đó Javis tự trả lời ở chế độ thường kèm một dòng báo |
| **Ollama Cloud** | Dán API key lấy ở ollama.com | MCP + tool file + skill qua hub. Model mã nguồn mở cỡ lớn (gpt-oss, qwen3-coder, deepseek) chạy trên máy chủ của Ollama |

Mỗi card provider hiển thị trạng thái **● Đã kết nối** hoặc **○ Chưa kết nối**, kèm số model khả dụng, và một nhãn kiểu bên cạnh tên: **MCP/skill** (Claude Code), **Device code** (ChatGPT), **MCP Javis** (các provider API). Trong Thứ tự dùng, card trên cùng có nhãn **MAIN**, các card sau ghi **Dự phòng 1**, **Dự phòng 2**... (xem mục D).

> Nhãn của các provider API trước 0.9.270 ghi là **chat**, khiến nhiều người tưởng chúng chỉ chat suông. Sai: chúng gọi kho Kết nối, đọc/ghi brain và chạy skill y như hai engine CLI. Nhãn giờ là **MCP Javis** cho đúng.

## Cách dùng (từng bước)

### A. Kết nối Claude Code (mặc định)

Đây là engine mặc định. Nó dùng được toàn bộ công cụ, skill và bộ nhớ, cộng thêm chạy lệnh máy. Không bắt buộc: nếu bạn không có gói Claude thì bỏ qua mục này và đi thẳng xuống mục B (ChatGPT) hoặc C (API key) - Javis chạy đủ chức năng như nhau, chỉ thiếu phần lệnh máy khi đi bằng API key.

1. Vào **Models**, tìm card **Claude Code** (chưa đăng nhập thì nó nằm sau nút **＋ Kết nối thêm nhà cung cấp** ở cuối trang).
2. Nếu chưa đăng nhập, card báo **○ Chưa đăng nhập** và có hai nút: **Đăng nhập Claude** và **↻ Kiểm tra lại**. Nếu máy chạy Javis chưa có lệnh `claude`, card báo **○ Chưa cài Claude Code**, hiện một khung hướng dẫn cài (bản Docker: cập nhật Javis; bản cài tay: một lệnh để chép) và chỉ có nút **↻ Kiểm tra lại**.
3. Bấm **Đăng nhập Claude**. Javis hiện dòng "**1)** Mở link này để đăng nhập claude.ai" kèm đường link.
4. Mở link đó để đăng nhập tài khoản claude.ai của bạn.
5. Nếu trang hiện **một mã code**, dán mã vào ô "dán code (nếu có)" rồi bấm **Gửi code**. Một số luồng không cần dán code - Javis vừa chờ vừa tự kiểm tra mỗi 3 giây, kết nối xong là card tự đổi. Quá 5 phút không xong thì báo "Hết thời gian, thử lại.".
6. Khi xong, card đổi sang **● Đã kết nối** kèm email và gói.

Nút **↻ Kiểm tra lại** chỉ có ở trạng thái chưa đăng nhập, dùng khi bạn vừa đăng nhập bằng terminal và muốn Javis nhìn lại. Khi đã kết nối, card chỉ còn đúng một nút **Ngắt**.

Cách này chạy được cả trên VPS không có màn hình. Nếu thích dùng dòng lệnh, bạn có thể chạy `claude auth login --claudeai` trong terminal.

### B. Kết nối ChatGPT bằng gói thuê bao

Dùng gói ChatGPT Plus/Pro của bạn thay cho API key. Cách này chạy qua Codex và Javis tự đẩy các kết nối của bạn (ví dụ POS bán hàng) sang Codex để ChatGPT cũng gọi được công cụ.

Card **OpenAI OAuth (ChatGPT)** khi chưa kết nối có **hai** nút, ứng với hai đường đăng nhập:

**Đường 1 - nút "Đăng nhập ChatGPT" (device code, dùng cho hầu hết mọi người):**

1. Bấm **Đăng nhập ChatGPT**. Javis mở trang xác thực của OpenAI và hiện một dòng dạng "Mở &lt;đường link&gt; · nhập mã **XXXX-XXXX** - đang chờ…".
2. Ở trang vừa mở, nhập đúng mã đó.
3. Javis tự động chờ và kiểm tra. Xong thì hiện **✓ Đã kết nối!** và card đổi sang **● Đã kết nối** kèm gói tài khoản.
4. Javis chờ tối đa khoảng 16 phút rồi bỏ cuộc với dòng "Hết hạn, thử lại." - lúc đó bấm **Đăng nhập ChatGPT** lại để lấy mã mới.

**Đường 2 - nút "Qua trình duyệt" (khi workspace của bạn CHẶN device code):**

Một số workspace ChatGPT tắt đường device code, bấm nút thứ nhất là báo lỗi. Đừng tưởng hỏng, dùng nút này:

1. Bấm **Qua trình duyệt**. Javis mở trang đăng nhập ChatGPT trong tab mới.
2. Đăng nhập xong, trình duyệt sẽ nhảy sang địa chỉ **localhost** và rất có thể **báo không tải được trang - chuyện bình thường**, vì Javis không thật sự mở cổng đó.
3. **Copy toàn bộ đường dẫn trên thanh địa chỉ** (dạng `http://localhost:1455/auth/callback?code=…`) rồi dán vào ô trong Javis, bấm **Xác nhận**.
4. Javis tách mã trong đường dẫn đó ra và đổi lấy token. Xong thì hiện **✓ Đã kết nối!**.

Vì chỉ cần dán lại đường dẫn nên đường này cũng chạy được khi Javis nằm trên VPS còn trình duyệt ở máy bạn.

Kết nối xong, thẻ ChatGPT vào cuối **Thứ tự dùng**. Muốn chat bằng nó thì kéo thẻ lên đầu (hoặc bấm **⇅ Đảo**) để nó thành MAIN, rồi chọn model bằng chip model trên thẻ (xem mục D).

Muốn ngắt: bấm **Ngắt** trên card này. ChatGPT rời khỏi Thứ tự dùng; nếu nó đang là MAIN thì thẻ kế tiếp lên làm MAIN để chat không bị gãy.

Lưu ý: đây là kênh thử nghiệm (chạy nền Codex). Nếu cần ổn định tối đa, dùng Claude Code hoặc OpenRouter.

### B1a. Kết nối Grok Build CLI (dùng gói SuperGrok / X Premium+)

Đây là đường **xAI** dùng gói bạn đang trả tiền, không phải mua API key riêng. Điểm khác biệt lớn nhất so với hai thẻ CLI của Google: **đăng nhập xong ngay trên trang Models**, kể cả khi Javis chạy trên VPS không có trình duyệt.

1. Cài CLI một lần trên máy chạy Javis:
   - Linux/macOS: `curl -fsSL https://x.ai/cli/install.sh | bash`
   - Windows PowerShell: `irm https://x.ai/cli/install.ps1 | iex`
   - Bản Docker (từ 0.85.1): **không cần làm bước này**, Javis tự cài lúc khởi động. Trong lúc đang cài, thẻ hiện "Javis đang tự cài"; khoảng một phút sau bấm **Kiểm tra lại**.
2. Vào **Models**, bấm **＋ Kết nối thêm nhà cung cấp** ở cuối trang, tìm thẻ **xAI Grok Build CLI**, bấm **Đăng nhập**. Nó hiện ra một đường link và một mã. Mở link đó trên máy bạn (điện thoại cũng được), nhập mã, xác nhận. Thẻ tự chuyển sang **● Đã đăng nhập**, không phải bấm gì thêm.
3. Thẻ vừa đăng nhập vào cuối **Thứ tự dùng**. Kéo nó lên đầu (hoặc bấm **⇅ Đảo**) để nó thành MAIN, rồi chọn model bằng chip model trên thẻ.

**Cần gói gì:** Grok Build đi kèm **SuperGrok** hoặc **X Premium+**. Có mỗi API key `XAI_API_KEY` thì CLI vẫn chạy được về mặt kỹ thuật, nhưng quyền dùng Grok Build gắn vào GÓI chứ không vào key - nên nếu thẻ báo *"Tài khoản đăng nhập không có quyền dùng Grok Build"* thì đó là chuyện gói, không phải lỗi cấu hình. Bấm **Kiểm tra lại** là biết chắc: nút đó chạy thử một lượt chat thật chứ không chỉ soi file.

**Chạy nền 24/7 bằng gói cá nhân:** xAI chưa nói rõ chuyện này, nên rủi ro giống hệt cảnh báo đã ghi cho gói Anthropic - muốn yên tâm thì trỏ model việc nền sang một provider API.

Vài chỗ đáng biết:

- **Tool của Javis đấu vào `<brain>/.grok/config.toml`**, mục `[mcp_servers.javis]`. Grok đọc cấu hình theo **thư mục làm việc**, mà Javis luôn chạy nó với thư mục làm việc là gốc brain - nên mỗi brain một hub riêng, và Javis **không đụng vào `~/.grok/config.toml`** cá nhân của bạn. Kiểm trong 10 giây: bấm **Kiểm tra lại** ở thẻ, nó ghi lại cấu hình rồi **đọc lại chính file đó** và báo *tool của Javis đã đấu* / *chưa đấu được tool của Javis* / *trung tâm kết nối đang tắt*.
- **File `config.toml` của bạn không bị đè hỏng.** Javis giữ nguyên mọi mục khác trong file (`[models]`, `[tools]`...). Và nếu file đang có lỗi cú pháp khiến Javis không đọc nổi, nó **không ghi đè** - thà chạy thiếu tool còn hơn xoá mất cấu hình của bạn; khi đó thẻ báo "chưa đấu được tool của Javis" chứ không báo xanh giả.
- **Có nối lại mạch hội thoại của CLI** (khác thẻ Antigravity). `grok` tự sinh id phiên rồi phát ra trong dòng sự kiện, Javis chỉ đọc lại id đó chứ không tự bịa - nên không có chuyện lưu nhầm rồi lượt sau nối vào một mạch không tồn tại. Mạch dài quá ngưỡng thì Javis tự mở mạch mới và mồi lại bằng lịch sử đã lưu.
- **Javis ĐO cờ của bản CLI đang cài, không đoán.** Trước mỗi lượt nó hỏi `grok --help` (nhớ 5 phút) rồi chỉ truyền những cờ mà binary tự khai. Bản cũ thiếu một cờ thì mất đúng tính năng đó, không làm hỏng cả lượt chat vì "unknown flag".
- **Prompt đi qua file, không qua dòng lệnh** (`--prompt-file`), cùng lý do với thẻ Antigravity: Windows chặn tổng dòng lệnh ở 32767 ký tự mà system prompt của Javis đã hơn 36.000.
- Danh sách model hỏi CLI chứ Javis không giữ bảng chép tay, nên xAI đổi tên model cũng không làm picker lạc hậu.
- **Javis tắt bộ tự cập nhật của CLI** ở mọi lượt (cờ `--no-auto-update` khi bản CLI có, cộng biến `GROK_DISABLE_AUTOUPDATER=1` luôn luôn). Lý do: Javis chạy `grok` headless trên VPS và trong container, để nó tự tải bản mới giữa lượt là in thêm chữ vào luồng kết quả rồi hỏng câu trả lời, hoặc ghi vào chỗ chỉ đọc rồi chết. Muốn nó tự cập nhật thì tự đặt `GROK_DISABLE_AUTOUPDATER=0` - Javis tôn trọng giá trị bạn đặt. Nâng cấp tay lúc nào cũng được: `grok update`.
- Lượt chạy quá lâu thì bị cắt ở **900 giây**; đổi bằng biến môi trường `JAVIS_GROK_TIMEOUT`. Binary nằm chỗ lạ thì trỏ bằng `JAVIS_GROK_BIN`.

### B1b. Kết nối Antigravity CLI (dùng gói Google của bạn)

Đây là đường **Google chỉ định** sau khi họ ngắt Gemini CLI với tài khoản cá nhân (18/06/2026), và Javis đã gỡ hẳn engine Gemini CLI ở bản 0.50.0. Ưu điểm lớn nhất: bạn chọn được **đúng dàn model hiện trong Antigravity IDE**, gồm cả model không phải của Google.

1. Cài CLI một lần trên máy chạy Javis:
   - Linux/macOS: `curl -fsSL https://antigravity.google/cli/install.sh | bash`
   - Windows PowerShell: `irm https://antigravity.google/cli/install.ps1 | iex`
   - Bản Docker (từ 0.85.1): **không cần làm bước này**, Javis tự cài lúc khởi động. Trong lúc đang cài, thẻ hiện "Javis đang tự cài"; khoảng một phút sau bấm **Kiểm tra lại**.
2. Gõ `agy` một lần **trong terminal của máy chạy Javis** (trang **Code** trong Javis là chắc ăn nhất - đúng user đang chạy Javis). Máy để bàn có màn hình thì nó tự mở trình duyệt. Máy chủ không có màn hình (VPS, Docker - kể cả Docker trên chính máy Mac của bạn) thì nó in ra một đường link: mở link đó bằng trình duyệt trên máy bạn, đăng nhập Google xong trình duyệt sẽ nhảy sang một địa chỉ `http://localhost:...` **báo không mở được - đó là bước đúng**, copy nguyên địa chỉ trên thanh URL rồi dán ngược vào terminal và Enter. Phiên lưu trong keyring của hệ điều hành nên chỉ phải làm một lần.

   > Vì sao phải dán tay: `agy` nhận mã về qua một cổng loopback trên chính máy chạy nó. Trình duyệt của bạn ở máy khác nên không với tới cổng đó. Từ 0.55.46, terminal của Javis tự khai đây là phiên từ xa (`SSH_CONNECTION`) để `agy` hỏi chỗ dán thay vì nằm chờ im lặng. Bản `agy` cũ không hỏi thì mở thêm một phiên terminal rồi chạy `curl "<địa chỉ localhost vừa copy>"` cũng xong. Bố trí lạ (X11 forwarding, máy để bàn có màn hình) muốn tắt hành vi này thì đặt `JAVIS_TERMINAL_REMOTE=0`.
3. Quay lại **Models**, bấm **＋ Kết nối thêm nhà cung cấp** ở cuối trang, tìm thẻ **Google Antigravity CLI**, bấm **Kiểm tra lại** (nó chạy thử một lượt chat thật). Thẻ đổi sang **● Đã đăng nhập**.
4. Thẻ vừa đăng nhập vào cuối **Thứ tự dùng**. Kéo nó lên đầu (hoặc bấm **⇅ Đảo**) để nó thành MAIN, rồi chọn model bằng chip model trên thẻ.

Danh sách model **hỏi thẳng `agy models`** chứ Javis không giữ bảng chép tay, nên tài khoản bạn được cấp model nào là thấy đúng model đó, và Google đổi tên model cũng không làm picker lạc hậu. Model mới chỉ hiện khi chính `agy` đã lên bản biết model đó, nên từ 0.137.0 Javis tự chạy `agy update` mỗi ngày một lần, cả trong bản Docker (tắt bằng biến môi trường `JAVIS_AGY_AUTO_UPDATE=0`). `agy` đã mới nhất mà vẫn không thấy một model thì tài khoản Google của bạn chưa được cấp model đó.

Vài chỗ đáng biết, nói trước cho khỏi hiểu nhầm:

- **Đăng nhập làm trong terminal, dashboard không có nút** (từ 0.32.2). Bản 0.30.0 từng dựng một luồng đăng nhập ngay trên trang: Javis mở `agy` trong một terminal giả rồi làm người đưa thư giữa nó và trình duyệt của bạn. Nó chạy được trên Linux, nhưng cái hiện ra trên trang là một ô terminal bấm vào không ăn nên rốt cuộc vẫn phải mở terminal thật, còn Windows thì không có pseudo-terminal nên chưa bao giờ dùng được. Người dùng `agy` đều là dân code sẵn terminal trong tay, nên gõ một lệnh gọn hơn hẳn một luồng UI nửa vời. Đổi lại, Javis không cầm token của ai - nó nằm trong keyring hệ điều hành.
- **Mức Chỉ đọc ở đây nhẹ hơn.** Bên Grok Build, mức `suggest` xuống thẳng cờ `--deny` nên chính CLI chặn. `agy` không có nấc tương đương, nên Javis siết bằng `--sandbox` cộng với lời dặn trong system prompt. Rào tiền/đơn/đăng bài vẫn nằm ở MCP Hub như mọi engine.
- **Mức `auto` KHÔNG kèm `--sandbox`** (từ 0.59.44). Đo trên agy 1.2.7: `--sandbox` đi cùng `--dangerously-skip-permissions` làm tool shell của agy chạy như một việc nền rồi bị chính agy huỷ sau 5 giây khi thoát chế độ in một lượt, nên việc Kanban/Loop mức auto không đọc thư mục hay ghi file được mà không có lấy một dòng lỗi. Bỏ cờ này không mất lớp phòng vệ nào vì rào hành động ra ngoài nằm ở MCP Hub.
- **Chưa nối lại mạch hội thoại của CLI.** Mỗi lượt mở mạch mới rồi mồi lại bằng lịch sử đã lưu, nên **không mất ngữ cảnh** nhưng tốn token hơn.
- Javis không tự cài `agy` lúc cài đặt (khác ba engine npm): trình cài của Google là một script tải về chạy thẳng, nên để bạn tự chạy khi muốn.
- **Trên Windows, prompt không đi qua dòng lệnh nữa** (từ 0.33.1, sửa tiếp ở 0.33.2). Windows chặn tổng dòng lệnh ở 32767 ký tự, mà riêng system prompt của Javis trên một brain trống đã hơn 36.000 - tức bộ não này từng chết hẳn trên Windows, và câu báo lỗi lại đổ cho "hội thoại quá dài" nên mở chat mới bao nhiêu lần cũng không thoát.
- **Javis ĐO xem bản `agy` của bạn nhận prompt kiểu gì, không đoán.** Đây là bài học phải trả giá hai lần: bản 0.33.1 suy cú pháp từ tài liệu chính chủ (CHANGELOG 1.1.1 nói `agy` đọc stdin khi prompt không cấp qua cờ) rồi gửi `--print ""`, và bản `agy` thật trả lại `Error: empty prompt` vì nó kiểm giá trị cờ trước khi ngó tới stdin. Tài liệu đúng về nguyên lý, sai về cú pháp. Nay lần chạy đầu tiên Javis thử ba cách bơm stdin bằng một prompt tí hon có mã riêng, cách nào vọng mã về thì dùng cách đó, rồi nhớ lại cho những lần sau. Không cách nào ăn thì nó ghi ngữ cảnh ra file và bảo model tự đọc; model không đọc được thì nó nói thẳng chứ không lặng lẽ trả lời thiếu luật.

- **Tool của Javis đấu vào đâu, và vì sao chỗ đó** (sửa ở 0.43.0). Đây là chỗ sai ba bản liên tiếp mà không bản nào lộ ra, vì hỏng kiểu này không có câu lỗi nào: `agy` vẫn chạy, vẫn trả lời trôi chảy, chỉ là không có lấy một tool nào của Javis - không MCP, không Kanban, không skill. Hai chỗ sai chồng lên nhau:
  - **Sai tên trường.** Javis ghi `httpUrl`, đó là schema của Gemini CLI (engine đã gỡ) chép nguyên sang. `agy` đọc `serverUrl` (tài liệu di trú của Google nói thẳng là trường `url` được đổi tên thành `serverUrl`). Entry không có trường nào nó hiểu thì server không có địa chỉ, và nó bỏ qua trong im lặng.
  - **Sai chỗ đặt.** Javis ghi vào trong brain. `agy` nạp MCP từ cấu hình **tầng HOME**: `~/.gemini/config/mcp_config.json` (hiện hành, dùng chung với Antigravity 2.0/IDE) và `~/.gemini/antigravity-cli/mcp_config.json` (đường cũ). Tầng workspace `<brain>/.agents/mcp_config.json` có thật trong tài liệu, nhưng issue #60 của chính repo `antigravity-cli` ghi nhận CLI **tìm thấy rồi bỏ qua** `mcpServers` trong đó. Nay Javis ghi cả hai tầng: HOME để chạy được ngay, workspace để bản nào vá xong issue đó thì tự có cách ly theo brain.

  Hệ quả phải biết: file HOME là **của bạn** và dùng chung với Antigravity IDE, nên IDE cũng sẽ thấy tool của Javis; và hai brain chạy `agy` cùng lúc thì brain sau ghi đè brain trước. Không muốn Javis đụng vào HOME thì đặt `JAVIS_AGY_MCP_HOME=0` (khi đó chỉ còn đường workspace, tức chỉ chạy trên bản `agy` đã vá issue #60). Muốn chỉ định một file khác thì đặt `JAVIS_AGY_MCP_CONFIG=/đường/dẫn/mcp_config.json`. Bản `agy` của bạn từ chối cấu hình vì có khoá lạ thì đặt `JAVIS_AGY_MCP_KEY=serverUrl` (hoặc `=url` cho bản 1.0.x cũ) để Javis chỉ ghi đúng một khoá.

  **Tự kiểm trong 10 giây:** vào **Models**, thẻ **Google Antigravity CLI**, bấm **Kiểm tra lại**. Nó ghi lại cấu hình rồi đọc lại chính file đó, và báo một trong ba câu: *tool của Javis đã đấu*, *chưa đấu được tool của Javis*, hoặc *trung tâm kết nối đang tắt*. Xem tận file thì: `cat ~/.gemini/config/mcp_config.json` - phải thấy một entry tên `javis` có `serverUrl` trỏ về `/hub/mcp`.

- **Dấu tiếng Việt không vỡ dọc đường** (từ 0.33.6). Triệu chứng cũ: chữ "gồm" thành `g<?><?>m`, mỗi ký tự tiếng Việt 3 byte hoá đúng 3 dấu `<?>`. Đó là chữ ký của một bên đọc cắt mẩu ống dẫn giữa một ký tự rồi giải mã từng mẩu rời. Đã đo và loại trừ phía Javis (bộ đọc của nó dùng giải mã tăng dần, cắt byte giữa ký tự vẫn ghép lại đúng), nên chỗ vỡ nằm ở bộ đọc của `agy`. Javis không vá được CLI, nhưng chỉnh được chỗ mình đặt ranh giới: nay nó bơm prompt theo từng mẩu kết thúc đúng biên ký tự, nên bên kia đọc kiểu gì cũng không vỡ. Chữ về mà vẫn có ký tự hỏng thì Javis tự đổi sang đường file rồi hỏi lại một lần; vẫn hỏng thì nó nói thẳng là lỗi nằm trong CLI.

- **Model đã kèm sẵn mức nghĩ thì Javis không gửi thêm Độ sâu suy nghĩ** (từ 0.55.55). `agy models` trả về những tên như `gemini-3.8-flash-medium`, tức chọn model cũng chính là chọn mức nghĩ, và `agy` từ chối chạy nếu nhận thêm mức nghĩ lần nữa: `invalid model selection ... conflicts with --effort=high`, thoát mã 1, cả lượt chat mất trắng chứ không phải chậm hay kém. Nay Javis nhận ra loại tên đó và bỏ phần gửi thừa, còn độ sâu bạn chọn thì chuyển thành một câu nhắc trong prompt. Bản `agy` nào từ chối vì lý do khác thì Javis đọc chính câu lỗi đó rồi chạy lại ngay trong lượt, không cờ.

**Nếu vẫn gặp lỗi trên Windows**, đặt biến môi trường `JAVIS_AGY_PROMPT_DAI=file` để ép đi thẳng đường file, rồi báo lại giúp kèm câu lỗi `agy` in ra.

### C. Kết nối provider bằng API key (OpenRouter / Anthropic API / OpenAI API / Gemini / Groq / DeepSeek)

1. Vào **Models**, bấm **＋ Kết nối thêm nhà cung cấp** ở cuối trang, tìm card provider tương ứng.
2. Dán API key vào ô nhập (ô ghi "Dán API key để kết nối").
3. Bấm **Kết nối**.
4. Card chuyển sang **● Đã kết nối** kèm số model, và vào cuối **Thứ tự dùng**. Muốn chat bằng nó thì kéo thẻ lên đầu (hoặc bấm **⇅ Đảo**) để nó thành MAIN, rồi chọn model bằng chip model trên thẻ.

Ollama Cloud cũng kết nối đúng cách này, key lấy ở ollama.com.

**Nhiều API key cho một nhà (từ 0.351.0).** Thẻ của nhà API trong Thứ tự dùng (OpenRouter, Anthropic API, OpenAI API, Gemini API, Groq, DeepSeek, Ollama Cloud) hiện một danh sách key đánh số 1, 2, 3...:

- Mỗi dòng có số thứ tự, tên key, 4 ký tự cuối của key và trạng thái: **Sẵn sàng**, **Đã tắt**, hoặc **Hết lượt, mở lại HH:MM**.
- Đổi thứ tự key bằng mũi tên lên/xuống hoặc kéo dòng. Nút **⋯** ở cuối dòng có **Tắt** / **Bật**, **Đổi key** (dán key mới rồi **Lưu**) và **Gỡ**.
- **＋ Thêm key**: đặt tên cho dễ nhận (ví dụ "Key dự án B"), dán key, bấm **Lưu**. Key mới vào cuối danh sách.
- Javis dùng key **từ trên xuống**: key 1 tới khi hết lượt thì sang key 2, key đang nghỉ thì bỏ qua ngay; dùng hết key của nhà này mới sang thẻ kế tiếp. Key 1 hồi lượt thì quay lại dùng nó trước.
- Key đang chạy được tô nổi: xanh lá **Chat đang dùng**, tím **Việc nền đang dùng**.
- Dòng trạng thái của thẻ tóm lại, ví dụ "Đã kết nối · 3 model · 2/2 key dùng được".
- Gỡ key cuối cùng là ngắt kết nối nhà đó: Javis hỏi lại ("Đây là key cuối cùng: nhà này rời khỏi thứ tự dùng."), đồng ý thì thẻ rời Thứ tự dùng, và nếu nó đang là MAIN thì thẻ kế tiếp lên làm MAIN.

Các cổng tự khai địa chỉ (OpenAI Compatible, Anthropic Compatible, Ollama Local) vẫn giữ form một địa chỉ, một key như cũ (xem C1 và G).

Lấy key ở đâu:

- **OpenRouter**: trang openrouter.ai (một key gọi được rất nhiều model của nhiều hãng).
- **Anthropic (API)**: console.anthropic.com.
- **OpenAI (ChatGPT API)**: platform.openai.com.
- **Google Gemini (API)**: key của Gemini API, lấy ở aistudio.google.com.

### C1. Kết nối Anthropic Compatible (key mua từ bên bán lại)

Dùng khi bạn mua key Claude (hoặc model khác) từ một bên bán lại, và bên bán có **cổng chuẩn Anthropic**. Nhiều bên bán có cả cổng OpenAI lẫn cổng Anthropic, và hay nói cổng Anthropic chạy ổn định hơn với Claude. Cổng "anthropic" của DeepSeek, Kimi, MiniMax cũng kết nối theo đúng cách này. Có từ bản 0.254.0.

**Chuẩn bị 3 thứ từ bên bán** (lấy thông tin của cổng ANTHROPIC, không phải cổng OpenAI):

- **Base URL**: địa chỉ bên bán ghi cho `ANTHROPIC_BASE_URL`, ví dụ `https://api.tenbenban.com` hoặc `https://api.tenbenban.com/anthropic`. Lỡ dán cả đuôi `/v1` hay `/v1/messages` cũng không sao, Javis tự cắt.
- **API key**: chuỗi bên bán cấp, thường bắt đầu bằng `sk-`.
- **Tên model**: ví dụ `claude-sonnet-4-6`. Hỏi bên bán gói của bạn dùng được model nào và chép đúng từng chữ.

**Kết nối:**

1. Vào **Models**, chọn tab **Cloud Model**, bấm **＋ Kết nối thêm nhà cung cấp** ở cuối trang, tìm thẻ **Anthropic Compatible**.
2. Điền 3 ô từ trên xuống: Base URL, tên model (nhiều model thì cách nhau bằng dấu phẩy), API key.
3. Bấm **Kết nối**. Javis gửi thử một tin rất ngắn tới bên bán để kiểm tra, xong thì thẻ hiện **● Đã kết nối** kèm số model.
4. Đặt làm model chính như mục D: thẻ **Anthropic Compatible** vừa vào cuối Thứ tự dùng, kéo nó lên đầu (hoặc bấm **⇅ Đảo**) rồi chọn tên model bằng chip model trên thẻ. Chat thử một câu, dưới câu trả lời có dòng nhỏ ghi "Anthropic Compatible · tên-model" là đã chạy đúng đường.

Javis chỉ lưu khi kiểm tra thành công, nên thấy báo lỗi tức là chưa lưu gì. Lý do cần ô tên model: đa số cổng kiểu này không trả danh sách model, Javis không tự biết bên bán có những model nào. Cổng nào có danh sách thì Javis tự nạp thêm.

**Gặp lỗi khi bấm Kết nối:**

| Câu báo | Nghĩa là | Làm gì |
|---|---|---|
| API key không hợp lệ (HTTP 401) hoặc (HTTP 403) | Key sai, hết hạn hoặc bị khoá | Chép lại key (không thừa dấu cách), hoặc xin bên bán key mới |
| Cổng này không trả danh sách model | Chưa điền tên model | Điền tên model bên bán đưa rồi bấm Kết nối lại |
| Không thấy .../v1/messages (HTTP 404) | Base URL chưa đúng | Hỏi lại bên bán địa chỉ cổng Anthropic; hay gặp nhất là lấy nhầm địa chỉ cổng OpenAI |
| Cổng trả HTTP 400 khi thử model ... | Thường là tên model sai, hoặc gói không có model đó | Kiểm tra chính tả tên model, hoặc hỏi bên bán tên đúng |
| Không gọi được ... | Máy chạy Javis không tới được địa chỉ đó | Kiểm tra Base URL, mạng, hoặc hỏi bên bán cổng còn chạy không |

Đã kết nối mà lúc chat báo **429** hoặc **529** nghĩa là bên bán đang quá tải hoặc bạn đã hết hạn mức: đợi một lúc rồi thử lại, hoặc hỏi bên bán về hạn mức gói.

**Nên biết:**

- Đổi key: điền key mới vào ô API key rồi bấm **Lưu**. Để trống ô key thì Javis giữ key cũ.
- Thêm hay bớt model: sửa ô tên model rồi bấm **Lưu**.
- Đổi sang Base URL khác thì phải nhập lại key: Javis không bao giờ gửi key cũ sang một địa chỉ mới.
- Thôi dùng: bấm **Ngắt** (xoá cả địa chỉ, key và tên model). Thẻ rời Thứ tự dùng; nếu nó đang là MAIN thì thẻ kế tiếp lên làm MAIN.
- Javis gửi key theo cả hai kiểu xác thực (`x-api-key` và `Bearer`), nên bên bán đọc kiểu nào cũng nhận.
- Cổng này có đủ MCP, đọc ghi brain, skill, agent, việc nền và chatbot như các engine API khác. Như mọi engine API, nó không chạy lệnh máy (xem mục "Bốn thứ engine API không có").

### D. Thứ tự dùng: chọn MAIN và dự phòng

Khối **◆ Thứ tự dùng** ở đầu tab Cloud Model chỉ có các nhà **đã đăng nhập / đã kết nối**, xếp thành từng thẻ theo thứ tự dùng:

- **Thẻ trên cùng là MAIN** (nhãn **MAIN**): đây là model chat của bạn.
- Các thẻ sau ghi **Dự phòng 1**, **Dự phòng 2**... MAIN hết lượt, hoặc lỗi trước khi kịp làm gì, thì chat chuyển xuống thẻ kế tiếp. Thẻ dự phòng nào đang gánh chat ngay lúc này có nhãn xanh **ĐANG DÙNG**.
- **Đã làm một bước rồi mới lỗi thì không chuyển.** Engine nào đã gọi công cụ (gửi tin, đăng bài, tạo đơn...) rồi mới hỏng thì Javis dừng lại và báo, không chạy lại bước đó ở nhà khác, để không có chuyện gửi tin hay đăng bài hai lần.
- Chuyển dự phòng chỉ đổi đường chạy của lượt đó, **không sửa** thứ tự hay model bạn đã lưu.

**Đổi thứ tự:**

- **Kéo thẻ**: trên máy tính, giữ chuột ở bất kỳ đâu trên phần đầu thẻ rồi kéo. Trên điện thoại, giữ nút 6 chấm ở đầu thẻ, hoặc nhấn giữ thẻ khoảng một phần ba giây rồi kéo.
- Hoặc bấm nút **⇅ Đảo** nằm giữa hai thẻ liền nhau để đổi chỗ hai thẻ đó.

Thẻ nào lên đầu là thành MAIN ngay, không phải bấm lưu.

**Model và Effort của từng thẻ.** Mỗi thẻ có hai chip giống hệt chip dưới khung chat:

- **Chip model** (chấm xanh, tên model, ▾): mở danh sách model của riêng nhà đó, có ô tìm ở trên. Dòng đầu **mặc định** nghĩa là dùng model mặc định của nhà cung cấp; Javis biết đó là model nào thì ghi tên trong ngoặc, ví dụ **mặc định (llama-3.3-70b-versatile)**. Thẻ gói (Claude Code, ChatGPT, Grok, Antigravity) chưa đặt model thì do chính CLI tự chọn theo gói, trang ghi **mặc định của CLI (tự chọn theo gói)**. Danh sách được nạp từ chính nhà cung cấp, nên mới đổi tên model là thấy ngay.
- **Chip Effort** (mức, ▾): mở thanh trượt 6 nấc **Off**, **Light**, **Medium**, **High**, **Extra**, **Ultra** (xem mục F).

Mỗi thẻ nhớ model và Effort riêng, nên đổi thứ tự không làm mất lựa chọn của thẻ nào. Effort của thẻ MAIN chính là mức hiện trên chip Effort ở khung chat.

**Liên hệ với khung chat.** Khung chat vẫn chạy như cũ: chọn model ở chip model dưới khung chat là ghim cho phiên đó và đổi luôn model chính. Chọn model của **một nhà khác** ở đó thì thẻ nhà ấy **tự lên đầu** thành MAIN, các thẻ còn lại giữ thứ tự, MAIN cũ thành Dự phòng 1. Danh sách model ở khung chat nay **chỉ liệt kê nhà đã kết nối**.

**Thẻ nhà chạy bằng gói** (Claude Code, ChatGPT, Grok Build, Antigravity) giữ nguyên phần đăng nhập ngay trong thẻ: lựa chọn **Chạy bằng** (gói đang đăng nhập hay API key Anthropic) và nút **↻ Cập nhật Claude Code** của thẻ Claude, nút **Kiểm tra lại**, **Ngắt**... như các mục A, B, B1a, B1b. Từ 0.353.0, thẻ ChatGPT, Grok Build và Claude Code nhận được nhiều tài khoản (xem mục D1), còn Antigravity vẫn một tài khoản; thẻ nhà API thì nhận được nhiều key (xem mục C).

Chưa có nhà nào đăng nhập thì khối này báo "Chưa có nhà nào đăng nhập. Bấm Kết nối thêm nhà cung cấp bên dưới."

Telegram cũng đi theo MAIN: đổi MAIN trên web là các cuộc trò chuyện Telegram đổi theo, trừ cuộc trò chuyện bạn đã tự ghim bằng `/model` (xem [Telegram](11-telegram.md)).

### D1. Nhiều tài khoản cho một gói (từ 0.353.0)

Thẻ của ba nhà chạy bằng gói **ChatGPT (Codex)**, **Grok Build** và **Claude Code** nhận được nhiều tài khoản. Tài khoản này hết lượt thì Javis chạy tiếp bằng tài khoản kế của cùng gói, rồi mới sang thẻ dự phòng.

**Tài khoản 1** là đăng nhập sẵn có trên máy, đăng nhập bằng chính các nút ở phần trên của thẻ như mục A, B, B1a. Không có gì thay đổi với nó.

**Thêm tài khoản.** Khi thẻ đã đăng nhập và nằm trong Thứ tự dùng, dưới phần đăng nhập có nút **＋ Thêm tài khoản**:

1. Bấm **＋ Thêm tài khoản** và gõ tên cho tài khoản (ví dụ "Gói Pro 2" hay "Gói Max 200").
2. Đọc dòng cảnh báo nhẹ: "Nhiều tài khoản cho một gói có nguy cơ bị khoá, dù Javis chưa ghi nhận ca nào. Nếu gặp, hãy báo cho nhà phát triển qua mục Issues trên GitHub của Javis."
3. Bấm **Lấy link đăng nhập**, mở link trên máy nào cũng được, rồi đăng nhập đúng tài khoản cần thêm.
   - **ChatGPT** và **Grok Build**: thẻ hiện link kèm một mã. Đăng nhập xong là tự hoàn tất: trang kiểm tra mỗi 3 giây, chờ tối đa 15 phút.
   - **Claude Code**: thẻ hiện link. Đăng nhập xong, dán mã hiện ra vào ô trên thẻ rồi bấm **Xác nhận**.
4. Muốn dừng một lần đăng nhập chưa xong thì bấm **Huỷ**.

**Danh sách Tài khoản.** Có từ 2 tài khoản trở lên thì thẻ hiện khối **Tài khoản** kèm nút (i):

- Mỗi dòng đánh số 1, 2, 3... kèm trạng thái: **Đã đăng nhập**, **Chưa đăng nhập**, **Đã tắt** hoặc **Hết lượt, mở lại HH:MM**.
- Tài khoản đang gánh việc có nhãn xanh **Chat đang dùng** hoặc nhãn tím **Việc nền đang dùng**.
- Đổi thứ tự bằng mũi tên lên / xuống, hoặc kéo dòng.
- Nút **⋯** cuối dòng: **Tắt** / **Bật**; với các tài khoản khác tài khoản 1 có thêm **Đăng nhập lại** và **Gỡ**. Gỡ là xoá thư mục đăng nhập của tài khoản đó trên máy này. Tài khoản 1 không gỡ ở đây được.
- Dòng trạng thái của thẻ ghi thêm "x/y tài khoản dùng được".

**Dùng lần lượt thế nào:**

- Từ trên xuống: tài khoản báo hết lượt thì nghỉ tới giờ mở lại và tài khoản kế chạy thay; hồi lượt thì nó lại được dùng trước.
- Dùng hết các tài khoản của một thẻ rồi mới sang thẻ kế trong Thứ tự dùng. Thẻ chỉ tính là hết lượt khi không còn tài khoản nào của nó chạy được.
- Áp như nhau cho chat (web và Telegram) và việc nền (mỗi tài khoản là một mắt dự phòng riêng).

**Bên dưới.** Mỗi tài khoản thêm có thư mục đăng nhập riêng trên máy (trong thư mục trạng thái của Javis, `accounts/<id>/codex`, `accounts/<id>/grok` hoặc `accounts/<id>/claude`), và CLI chạy trỏ vào đó (`CODEX_HOME`, `GROK_HOME`, `CLAUDE_CONFIG_DIR`). Javis chép cài đặt của tài khoản 1 sang (cấu hình Codex và hồ sơ hub của Javis, `config.toml` của Grok, `settings.json` của Claude); đăng nhập thì không bao giờ được chép.

**Giới hạn cần biết:**

- Đổi tài khoản giữa cuộc trò chuyện thì lượt đó mở một mạch CLI mới, Javis tự nạp lại lịch sử.
- Đồng hồ hạn mức, tạo ảnh, giọng nói và những đường ChatGPT không đi qua Codex CLI vẫn dùng tài khoản 1.
- Antigravity vẫn chỉ một tài khoản (token nằm trong keyring của hệ điều hành).
- Claude Code chạy bằng API key Anthropic không có danh sách tài khoản.
- Trên macOS, một tài khoản Claude được tính là đã đăng nhập khi Javis thấy bước đăng nhập hoàn tất (token nằm trong Keychain).

### D2. Hết lượt giữa một lượt chat (từ 0.354.0)

Đường đang chạy (một tài khoản hay một key) báo hết lượt **trước khi viết chữ nào hay gọi công cụ nào** thì Javis chạy lại ngay đúng câu hỏi đó bằng đường kế tiếp: tài khoản hay key kế của cùng thẻ trước, rồi tới thẻ kế trong Thứ tự dùng. Bạn không phải gửi lại.

- Trong khung chat hiện một dòng nhạt, ví dụ "Đang dùng ChatGPT vì Claude Code hết lượt." hoặc "Đang dùng ChatGPT (tài khoản 2) vì tài khoản 1 hết lượt.", rồi câu trả lời của đường mới hiện bên dưới như thường.
- Tối đa 3 lần đổi đường cho một câu hỏi. Hết đường thì Javis báo hết lượt và hẹn tự chạy lại như trước.
- **Hết lượt giữa chừng** (đã viết được một đoạn): câu trả lời dừng ở đó, kèm thẻ **Chạy lại ngay**. Bấm vào là hỏi lại câu đó bằng đường còn lượt, câu trả lời dở được thay bằng câu mới. Javis không tự chạy lại trường hợp này.
- **Đã gọi công cụ rồi mới hết lượt**: Javis dừng và báo, không chạy lại ở đường khác, để không gửi tin hay đăng bài hai lần.
- Telegram cũng tự đổi đường như vậy, dòng "Đang dùng..." hiện ở tin trạng thái. Bot chuyên trách nói với khách thì không đổi: nó luôn chạy model của Agent nó trỏ tới.
- Đổi đường không sửa thứ tự hay model đã lưu. Lượt sau bắt đầu lại từ MAIN, trừ khi MAIN vẫn đang nghỉ.

### E. Chọn model việc nền

Khối **◆ Model việc nền** quyết định model nào chạy những việc Javis làm khi bạn không ngồi trước máy: **loop · việc Kanban · nhắc hẹn · tự học · tiêu hoá nguồn**. Đây thường là phần đốt hạn mức âm thầm nhất, nên chọn model rẻ ở đây tiết kiệm thấy rõ.

1. Khối **◆ Model việc nền** nằm ngay dưới Thứ tự dùng. Dòng lớn màu cam là tên model, dòng nhỏ bên dưới là nhà cung cấp. Bên cạnh có chip **Effort** riêng của việc nền và nút **Đổi model ▾**.
2. Bấm **Đổi model ▾**. Trên máy tính, cửa sổ hai cột (nhà cung cấp | model) mở ra với tiêu đề **MODEL VIỆC NỀN**. Trên điện thoại (màn hình rộng tới 600px), nó mở một danh sách kiểu chip model của khung chat: ô tìm ở trên, tên nhà viết hoa bấm để mở hoặc thu, dấu ✓ ở model đang chọn. Cả hai **chỉ liệt kê nhà đã kết nối**.
3. Chọn nhà cung cấp rồi chọn model.
4. Chỉnh chip **Effort** cạnh đó nếu muốn việc nền nghĩ sâu hơn hoặc nhanh hơn.

Không còn nút **Về mặc định** (bỏ ở 0.351.0). Muốn quay về model mặc định của một nhà thì mở **Đổi model ▾** và chọn dòng **mặc định** của nhà đó.

Vài điều cần biết:

- **Model việc nền không chạy theo MAIN.** Lần đầu (máy mới, hoặc nâng cấp mà chưa từng đặt) Javis chọn sẵn cấu hình mặc định của nhà cung cấp: model mặc định và mức Effort mặc định của nó. Sau đó model nền **giữ cố định** tới khi bạn tự đổi; kéo thẻ khác lên làm MAIN không kéo model nền đổi theo.
- **Chọn được MỌI nhà bạn đã kết nối**, không riêng Claude: Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Gemini, Anthropic API... Chọn nhà cung cấp khác thì việc nền chạy bằng gói hoặc khoá của nhà đó, không ăn vào hạn mức Claude nữa.
- **Hết lượt thì đi theo Thứ tự dùng (từ 0.350.0, gắn với Thứ tự dùng từ 0.351.0).** Việc nền chạy model nền trước; model nền hết lượt thì lần lượt sang **Dự phòng 1, Dự phòng 2...**, và **MAIN sau cùng**, mỗi nhà chạy cấu hình mặc định của nó (không phải model bạn chọn cho chat). Một nhà có nhiều API key thì thử từng key trước khi sang nhà kế, và thẻ gói có nhiều tài khoản cũng thử từng tài khoản trước (xem mục D1). Javis không tự chen một nhà bạn chưa kết nối vào.
- **Trang chỉ lên tiếng khi cần.** Chuỗi thứ tự trên không hiện ra thường xuyên. Chỉ khi model nền hết lượt mới có một dòng, ví dụ "Haiku 5.5 đang hết lượt, việc nền chạy tạm ChatGPT · GPT-5.5." Nhà của model nền chưa kết nối thì có dòng cảnh báo "Nhà cung cấp này chưa kết nối, việc nền bắt đầu từ Dự phòng 1." Không còn nhà nào chạy được thì báo "Không còn tài khoản nào chạy được việc nền."
- **Không làm một việc hai lần.** Engine nào đã gọi công cụ (gửi tin, đăng bài, tạo đơn...) rồi mới hỏng thì việc đó dừng và báo lỗi, không chạy lại bằng engine khác.
- **Công cụ không giống nhau giữa các đường.** Claude Code và Codex đọc/ghi file trực tiếp trong brain. Các model API (OpenRouter, OpenAI, Gemini, Anthropic API) đọc/ghi qua công cụ vault của Javis và **không chạy được lệnh máy**, nên hợp với việc đọc - tổng hợp - ghi ghi chú; việc nền nào cần chạy lệnh thì cứ để Claude.
- Với đường API, công cụ ghi file tự khoá lại khi loop đang ở mức `suggest`, đúng như khi chạy bằng Claude.

### E1. Chỗ nào chạy model nào (bảng tra)

Javis có ba chỗ đặt model, và câu hỏi hay gặp nhất là "cái nào thắng cái nào". Thứ tự: **model của Agent** (ô Model trong Cài đặt trợ lý) thắng **model chính**, còn **model việc nền** chỉ dùng cho các đường chạy nền.

| Bạn đang ở đâu | Model chạy thật |
|---|---|
| Chat thường trên dashboard / Telegram | Thẻ MAIN của Thứ tự dùng, hết lượt thì xuống Dự phòng 1, 2... (hoặc ghim riêng của phiên web, hay của đúng cuộc trò chuyện Telegram đã gõ `/model`) |
| Chat với một trợ lý ở trang Cộng sự | Model của trợ lý đó; để **Mặc định** thì model chính |
| **Chatbot** trả lời khách ngoài | Model của trợ lý mà bot trỏ tới; để **Mặc định** thì model chính |
| Một bước trong quy trình (workflow) | Model của trợ lý ở bước đó; để **Mặc định** thì **model việc nền** |
| Loop, việc Kanban, nhắc hẹn, tự học, tiêu hoá nguồn | Model việc nền |

Nhà cung cấp mà trợ lý đã chọn nếu bị gỡ key thì Javis lui về model chính, chứ không để trợ lý hay bot chết câm.

Ô **Model** trong Cài đặt trợ lý dùng đúng bảng chọn của thanh model dưới khung chat: gõ để tìm, và nhà chưa cắm API key vẫn hiện ra kèm ổ khoá, bấm vào là sang trang Models để mở. (Riêng bảng chọn ở khung chat thì nay chỉ liệt kê nhà đã kết nối.)

### F. Đặt mức suy nghĩ (Effort)

Tăng lên để model động não kỹ hơn trước khi trả lời: chính xác hơn, nhưng chậm hơn và tốn token hơn.

1. Trên thẻ nhà cung cấp trong **◆ Thứ tự dùng**, bấm chip **Effort** (với việc nền thì bấm chip Effort trong khối **◆ Model việc nền**).
2. Kéo thanh trượt tới một trong 6 nấc: **Off**, **Light**, **Medium**, **High**, **Extra**, **Ultra**.

Mỗi thẻ nhớ mức riêng đi cùng model của nó. Effort của thẻ MAIN là mức hiện trên chip Effort ở khung chat, đổi ở chỗ nào thì chỗ kia đổi theo. Trợ lý (agent) nào có mức riêng thì giữ mức của nó.

> **Ô Suy nghĩ chung đã bỏ ở 0.351.0.** Trước đó khối **◆ Suy nghĩ** có 4 nút Tắt, Thấp, Vừa, Cao áp cho mọi engine cùng lúc. Nay mỗi nhà một mức, nên đổi MAIN sang nhà khác không còn kéo theo một mức không hợp với model mới.

Vài điều cần biết:

- **Off** nghĩa là không gửi tham số suy nghĩ. Model bắt buộc phải suy nghĩ thì tự chạy mức mặc định của nó; model không có suy nghĩ thì chạy như Off.
- Model không có đúng nấc bạn chọn thì chạy ở **nấc gần nhất** nó có (cách đều thì lấy nấc thấp hơn). Lựa chọn đã lưu không bị sửa, nên đổi lại model cũ là về đúng mức cũ.

Mức này áp dụng khác nhau tuỳ engine:

- **Claude API / OpenRouter**: dùng adaptive thinking + mức effort tương ứng.
- **OpenAI**: chỉ áp cho các model dòng o-series (o1/o3/o4) và gpt-5; model thường sẽ bỏ qua.
- **Gemini**: chỉ áp cho model 2.5 trở lên (và các model có chữ "thinking"). Model cũ hơn không được gửi tham số này để tránh lỗi.
- **Claude Code**: chèn gợi ý suy nghĩ vào câu hỏi (từ mức think tới ultrathink theo độ sâu tăng dần).

### G. Local Model - Ollama chạy trên máy bạn hoặc trên VPS

Tab **Local Model** (cạnh tab Cloud Model trên trang Models) nối Javis với một Ollama do bạn tự chạy: model mã nguồn mở, ngoại tuyến, không tốn lượt. Provider tương ứng trong ô chọn model là **Ollama (Local)**, khác với **Ollama Cloud** ở tab Cloud (bản trả phí qua ollama.com).

**Javis chạy thẳng trên máy (Windows/Mac/Linux):** cài Ollama bằng lệnh tab hiện sẵn, bấm Kết nối với địa chỉ `http://127.0.0.1:11434` đã điền sẵn. Xong.

**Javis chạy trong Docker/VPS:** ba bước, làm bằng SSH trên máy chủ thật, không phải terminal trong Javis (terminal đó nằm trong container, không có quyền root, và mọi thứ cài vào đó mất sạch ở lần cập nhật kế).

1. Cài Ollama trên máy chủ: `curl -fsSL https://ollama.com/install.sh | sh`.
2. Cho Ollama nghe ở địa chỉ cầu nối Docker. Tab Local đã dò sẵn địa chỉ và sinh sẵn lệnh, chỉ việc chép. Nó ghi một file override cho systemd với `OLLAMA_HOST=<địa chỉ cầu nối>:11434` rồi restart. Gắn vào đúng địa chỉ này thì chỉ container trên máy đó gọi được, không lộ ra Internet, không cần tường lửa. Chỉ khi Javis dò không ra địa chỉ thì lệnh mới rơi về `0.0.0.0`, lúc đó bắt buộc chặn cổng 11434 ở tường lửa vì Ollama không có mật khẩu.
3. Bấm **Kết nối** (địa chỉ đã điền sẵn).

Không nối được sau ba bước? Trên máy chủ chạy `ss -ltnp | grep 11434`: không ra dòng nào là Ollama chưa chạy (`systemctl status ollama`); ra dòng có `127.0.0.1` là bước 2 chưa ăn.

**Chọn model:** phần Khuyến nghị xếp theo cấu hình máy. Máy không GPU (VPS phổ thông) thì ưu tiên bản **instruct** (vd `qwen3:4b-instruct`): trả lời thẳng. Các bản suy nghĩ dài (qwen3 thường, deepseek-r1) trên CPU có thể mất nhiều phút chỉ để "nghĩ" trước khi ra chữ đầu tiên, tab ghi rõ ở từng thẻ. Tải xong bấm **Dùng làm model chính** ngay tại danh sách đã cài: thẻ **Ollama (Local)** lên đầu Thứ tự dùng thành MAIN, và ô chọn model dưới khung chat đổi theo luôn.

## Engine Claude chạy bằng gì bên dưới

Từ bản 0.9.37, engine Claude của Javis chạy **duy nhất qua Claude Agent SDK** (bộ thư viện chính chủ của Anthropic). Nhánh cũ tự gọi lệnh `claude` như một tiến trình rời đã bị gỡ hẳn. Hai điều người dùng cần biết:

- **Máy vẫn PHẢI có `claude` CLI.** SDK gọi chính CLI đó bên dưới, và toàn bộ phần đăng nhập lẫn MCP native đều đi qua nó. Chưa cài CLI thì card Claude Code báo lỗi và engine không chạy - xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).
- **Quyền công cụ ở phiên chạy nền được chặn theo TỪNG LẦN GỌI.** Khi loop hoặc workflow chạy trong chế độ nền an toàn, mỗi lần Javis định gọi một công cụ ngoài danh sách cho phép là bị từ chối ngay tại chỗ và ghi vào nhật ký, chứ không chỉ khai báo danh sách lúc khởi động. Thông báo từ chối nói rõ đây là rào quyền của phiên nền, **không phải** kết nối MCP hỏng - gặp dòng đó thì đừng đi đăng nhập lại connector.

## Claude Code (đầy đủ công cụ) và gọi API thẳng khác nhau ra sao

Đây là điểm dễ nhầm nhất, cần nắm rõ:

- **MAIN = Claude Code**: mạnh nhất - đọc/ghi file native, chạy lệnh máy, gọi MCP, skill native, loop tự động, session resume. Chế độ khai thác hết sức mạnh Javis OS.
- **MAIN = ChatGPT OAuth (Codex)**: gọi được toàn bộ kho Kết nối (hub tự đẩy sang Codex, gồm cả kết nối local như Zalo), có tool file của Codex, và dùng được skill qua router (Javis bơm danh sách skill vào system prompt + tool `javis_use_skill`; Codex chạy cwd=brain nên đọc thẳng `skills/<slug>/SKILL.md`). Ngoài ra Codex còn nạp kho MCP GỐC của chính nó (server bạn tự đăng ký bằng `codex mcp add`, xem trong khối gập "◆ Kết nối sẵn của Claude Code và Codex" ở trang Kết nối) - tương tự cách engine Claude dùng MCP gốc của Claude Code.
- **MAIN = OpenRouter / OpenAI (API) / Anthropic (API) / Gemini**: từ bản 0.9 cả bốn đều gọi được kho Kết nối qua vòng gọi tool, kèm tool đọc/ghi file trong vault và kích hoạt skill (`javis_use_skill`). **Việc nền cũng chạy được bằng những provider này** (xem mục E). Khác biệt còn lại so với Claude Code: không có tool chạy lệnh máy (Bash), không có WebFetch, và không resume được session CLI.

Kết luận thực dụng: để Javis "làm việc" trọn vẹn nhất, giữ thẻ **Claude Code** trên cùng (MAIN). Chuyển sang provider API khi bạn muốn thử một model cụ thể của hãng khác, hoặc muốn đẩy phần việc nền sang một gói rẻ hơn cho đỡ hạn mức Claude.

## Tiết kiệm token áp cho cả gói thuê bao

Khối **Chế độ tiết kiệm token** ở đầu trang **Mức dùng** (nhóm Hệ thống) cho Javis gửi ít chữ hơn mỗi lượt: chỉ nạp phần bộ nhớ liên quan tới câu hỏi, chỉ nạp skill khi cần thay vì liệt kê hết.

Từ bản 0.12.4, phần này chạy được cho **cả ba loại bộ não**, không riêng bộ não dùng API key:

| Loại bộ não | Vì sao vẫn đáng bật |
|---|---|
| API key (OpenRouter, OpenAI, Anthropic, Gemini, Groq) | Ít token là ít tiền, và tránh được lỗi vượt hạn mức token mỗi phút |
| Gói Claude (Claude Code) | Ít token là mỗi cửa sổ 5 tiếng dùng được nhiều lượt hơn |
| Gói ChatGPT (Codex) | Như trên |

Mở trang là thấy ngay khối **Bộ não đang dùng**: nó nói bộ não hiện tại thuộc loại nào, đang ăn được mấy mảng tiết kiệm, và mảng nào không áp cho nó cùng lý do. Có mảng cố ý chỉ chạy trên bộ não dùng API key - ví dụ phần gửi lại lịch sử hội thoại, vì Claude Code và Codex vốn tự nhớ mạch hội thoại của chúng, gửi thêm là gửi hai lần.

**Hết lượt gói thuê bao** thì chat đi theo **Thứ tự dùng** bạn đã xếp: MAIN hết lượt thì lượt đó chạy thẻ Dự phòng 1 (với model và Effort của thẻ đó), rồi Dự phòng 2... Thẻ gói có nhiều tài khoản thì dùng hết các tài khoản của nó trước khi chuyển (xem mục D1). Javis chỉ chuyển sang những nhà **chính bạn đã kết nối và xếp vào đó**, vì chuyển là tiêu hạn mức của một tài khoản khác, có khi mất tiền thật. Muốn một nhà không bao giờ được dùng thay thì ngắt nó, hoặc với nhà API thì **Tắt** các key của nó. Chuyển như vậy không sửa gì đã lưu: lượt sau Javis lại thử MAIN trước. Không còn thẻ nào chạy được thì Javis nói bằng tiếng Việt: hết lượt gói nào và còn khoảng bao lâu nữa. Lưu ý loại hạn mức này đếm **lượt dùng theo giờ** chứ không đếm độ dài, nên rút gọn câu hỏi không giúp gì.

Từ 0.55.44, khi nhà cung cấp nói rõ **mốc mở lại**, dưới câu báo có thẻ **"Tự chạy lại lúc HH:MM"**: đến giờ Javis tự hỏi lại đúng câu đó và trả lời vào cùng hội thoại, tab đóng hay điện thoại tắt màn hình vẫn chạy (việc nằm ở máy chủ). Trên thẻ có ô **"Tự tiếp tục khi hạn mức reset"** (tắt là chỉ nhắc giờ, không tự chạy; lựa chọn được nhớ cho lần sau) và nút **"Chạy lại ngay"**. Gửi tin mới trong lúc chờ là lịch tự huỷ. Javis chỉ hẹn khi biết mốc, tối đa 3 lần cho một câu hỏi, và không hẹn mốc xa hơn một ngày; khởi động lại máy chủ thì lịch đang chờ mất, câu báo hết lượt vẫn còn trong hội thoại để bạn bấm "Gửi lại".

## Đổi nhanh model

Trên trang Models: kéo thẻ nhà bạn muốn lên đầu **Thứ tự dùng** (hoặc bấm **⇅ Đảo**) và chọn model bằng chip model trên thẻ đó. Thẻ trên cùng thành MAIN ngay. Khối **◆ Model việc nền** có nút **Đổi model ▾** riêng của nó (mở bảng **MODEL VIỆC NỀN**), còn chip **Effort** trên từng thẻ áp dụng ngay khi chọn.

Không cần mở trang Models cũng được: chọn model ở chip model dưới khung chat. Chọn model của một nhà khác thì thẻ nhà đó tự lên đầu Thứ tự dùng.

## Đổi model giữa chừng một cuộc trò chuyện

Đổi model ngay trong lúc đang chat thì **cuộc trò chuyện đi tiếp liền mạch**: model mới đọc được toàn bộ những gì đã nói trước đó và trả lời tiếp, không hỏi lại từ đầu. Bạn đổi bao nhiêu lần trong một cuộc cũng được.

Bên dưới, Javis làm việc này theo hai cách tuỳ loại bộ não:

- **Bộ não dùng API key** (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) vốn không tự nhớ gì, nên mỗi lượt Javis gửi lại lịch sử hội thoại cho chúng.
- **Bộ não chạy bằng gói thuê bao** (Claude Code, ChatGPT/Codex, Grok Build) thì tự giữ mạch hội thoại của riêng chúng, và Javis nối lại đúng mạch đó cho rẻ. Nhưng ngay khi một lượt do bộ não khác trả lời, mạch cũ đó **thiếu đúng lượt vừa rồi**. Javis vì vậy bỏ liên kết mạch của mọi bộ não khác sau mỗi lượt; lần bạn quay lại bộ não đó, nó dựng lại ngữ cảnh từ lịch sử đã lưu thay vì nối tiếp một mạch khuyết.

Nói ngắn: đổi qua đổi lại vẫn liền mạch, chỉ là lượt đầu tiên sau khi đổi tốn thêm một chút vì phải gửi lại lịch sử.

Từ 0.42.1 trở về trước có lỗi ở đúng chỗ này: chỉ mạch của ChatGPT/Codex được bỏ liên kết, còn các engine giữ mạch khác thì không, nên quay lại một trong số đó là chúng nói như chưa hề có mấy lượt ở giữa.

## Bảng tra nhanh nút và trạng thái

| Nút / dòng chữ | Ở đâu | Nghĩa là gì |
|---|---|---|
| **MAIN** | Thẻ trên cùng của Thứ tự dùng | Nhà này đang là model chính của chat |
| **Dự phòng 1**, **Dự phòng 2**... | Các thẻ sau của Thứ tự dùng | Thứ tự chat chuyển xuống khi thẻ trên hết lượt |
| **ĐANG DÙNG** (xanh) | Thẻ dự phòng | Chat đang chạy tạm trên thẻ này vì thẻ trên không chạy được |
| **⇅ Đảo** | Giữa hai thẻ trong Thứ tự dùng | Đổi chỗ hai thẻ đó |
| Nút 6 chấm | Đầu thẻ (điện thoại) | Giữ để kéo thẻ hoặc kéo dòng key |
| Chip model / chip **Effort** | Trên từng thẻ | Chọn model (dòng **mặc định** = model mặc định của nhà) / chọn mức suy nghĩ của thẻ đó |
| **● Đã kết nối** / **○ Chưa kết nối** | Card provider | Trạng thái, kèm số model khả dụng (nhà nhiều key ghi thêm dạng "2/2 key dùng được") |
| **Sẵn sàng** / **Đã tắt** / **Hết lượt, mở lại HH:MM** | Dòng key trong thẻ nhà API | Trạng thái của từng key |
| **Chat đang dùng** (xanh) / **Việc nền đang dùng** (tím) | Dòng key trong thẻ nhà API | Key đang gánh chat / việc nền lúc này |
| **⋯** | Cuối dòng key | Tắt / Bật, Đổi key, Gỡ |
| **＋ Thêm key** | Thẻ nhà API | Thêm một key có tên, vào cuối danh sách |
| **＋ Thêm tài khoản** | Thẻ ChatGPT, Grok Build, Claude Code (đã đăng nhập) | Thêm một tài khoản nữa cho cùng gói (xem mục D1) |
| **Lấy link đăng nhập** | Ô thêm tài khoản | Lấy link (ChatGPT, Grok kèm mã) để đăng nhập tài khoản cần thêm; Claude Code thì dán mã rồi bấm **Xác nhận** |
| Danh sách **Tài khoản** | Thẻ nhà chạy bằng gói có từ 2 tài khoản | Dùng lần lượt từ trên xuống; trạng thái **Đã đăng nhập** / **Chưa đăng nhập** / **Đã tắt** / **Hết lượt, mở lại HH:MM**; **⋯** để Tắt / Bật, Đăng nhập lại, Gỡ |
| **＋ Kết nối thêm nhà cung cấp (N)** | Cuối trang | Hiện N nhà chưa kết nối để đăng nhập / dán key |
| **○ Chưa đăng nhập** | Card Claude Code | Chưa đăng nhập Claude Code trên máy |
| **○ Chưa cài Claude Code** | Card Claude Code | Máy chạy Javis chưa có lệnh `claude`, làm theo khung hướng dẫn cài trên card |
| **Đăng nhập Claude** | Card Claude Code | Bắt đầu luồng đăng nhập bằng link |
| **↻ Kiểm tra lại** | Card Claude Code (chỉ khi chưa đăng nhập) | Hỏi lại trạng thái đăng nhập |
| **Đăng nhập ChatGPT** | Card OpenAI OAuth | Đăng nhập bằng mã device code |
| **Qua trình duyệt** | Card OpenAI OAuth | Đường dự phòng khi workspace chặn device code |
| **Kết nối** | Card provider API chưa kết nối | Lưu key đầu tiên, nhà đó vào cuối Thứ tự dùng |
| **Lưu** / **Ngắt** | Card OpenAI Compatible, Anthropic Compatible | Lưu địa chỉ, key, model / xoá hết và rời Thứ tự dùng |
| **Đổi model ▾** | Model việc nền | Mở bảng chọn model việc nền (**MODEL VIỆC NỀN** trên máy tính, danh sách kiểu khung chat trên điện thoại) |

## Mẹo

- Nếu chỉ muốn Javis nhớ và làm việc trơn tru, cứ để thẻ Claude Code trên cùng (MAIN). Các provider khác dành cho nhu cầu đặc biệt.
- Xếp ít nhất một thẻ dự phòng dưới MAIN (ví dụ một nhà API key) để gói chính hết lượt thì chat vẫn chạy tiếp thay vì đứng chờ.
- Có nhiều API key cho cùng một nhà thì thêm hết vào thẻ đó bằng **＋ Thêm key**: Javis tự dùng lần lượt, key nào nghỉ thì bỏ qua.
- Có hơn một tài khoản ChatGPT, Grok hoặc Claude thì thêm vào thẻ đó bằng **＋ Thêm tài khoản** (xem mục D1): tài khoản trên hết lượt là tài khoản dưới chạy tiếp, chưa phải sang nhà khác. Đọc kỹ dòng cảnh báo về nguy cơ khoá trước khi thêm.
- Đặt **Model việc nền** là model rẻ để loop, việc Kanban, nhắc hẹn, tự học và tiêu hoá nguồn không ngốn hết hạn mức của gói chính. Muốn biết chỗ nào đang đốt nhiều nhất thì xem [Mức dùng: token & chi phí](23-muc-dung-token.md).
- Đẩy chip **Effort** lên Medium hoặc High khi hỏi việc khó (phân tích, chiến lược); để Off hoặc Light khi chỉ hỏi nhanh để đỡ chờ.
- OpenRouter là lựa chọn tiện nếu muốn thử nhiều model của nhiều hãng chỉ với một key.
- Muốn ChatGPT gọi được công cụ bán hàng của bạn: gắn kết nối trong trang [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) trước, Javis sẽ tự đẩy sang Codex.

## Sự cố thường gặp

- **Card Claude Code báo "Claude CLI chưa cài"**: máy chưa cài Claude Code CLI. Engine Claude bắt buộc phải có nó (SDK gọi chính CLI này bên dưới). Cài xong bấm **↻ Kiểm tra lại**. Xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).
- **Đăng nhập ChatGPT không ra mã, hoặc báo lỗi ngay**: workspace của bạn có thể đã chặn device code. Dùng nút **Qua trình duyệt** ở mục B.
- **Đăng nhập ChatGPT báo "Hết hạn, thử lại."**: Javis chờ khoảng 16 phút rồi bỏ cuộc. Bấm **Đăng nhập ChatGPT** lại để lấy mã mới.
- **Bấm chip model mà danh sách trống**: nhà đó chưa trả được danh sách model, hoặc chưa có model. Bấm **Kiểm tra lại** hoặc kết nối lại nhà đó, hoặc thêm model vào `settings.json` (mục `model.catalog`). Xem [Cấu hình .env](16-cau-hinh-env.md).
- **Không thấy một nhà trong Thứ tự dùng**: nhà đó chưa kết nối (hoặc Claude Code chưa đăng nhập). Bấm **＋ Kết nối thêm nhà cung cấp** ở cuối trang.
- **Model trả về rỗng**: thử lại hoặc chọn model khác bằng chip model trên thẻ MAIN. Với Anthropic API, thông báo còn kèm lý do (ví dụ hết max_tokens: nhắn "tiếp tục" để model viết tiếp).
- **Trang Kết nối hiện dòng vàng "⚠ Main Model đang là ... - chưa hỗ trợ gọi công cụ. Đổi ở trang Models."**: từ 0.9.270 **không provider có sẵn nào** làm nổ dòng này nữa. Trước đó Google Gemini bị sót khỏi danh sách nên báo nhầm dù bên dưới đã chạy MCP qua hub bình thường. Dòng vàng giờ chỉ còn để chặn provider lạ. Sáu provider Claude Code, OpenRouter, OpenAI, Anthropic API, Gemini và Groq hiện thẻ XANH; riêng ChatGPT OAuth có thẻ xanh riêng nói rõ nó chạy qua Codex CLI.

- **Banner đỏ "⚠ Bộ não claude mất đăng nhập" trên máy chưa từng cài Claude**: sửa ở 0.9.270. Đèn báo não giữ trạng thái trong RAM và không ai dọn, nên đèn đỏ thắp hồi Claude còn là Main Model treo mãi sau khi bạn đổi sang OpenRouter. Giờ đèn chỉ tính những bộ não bạn THẬT SỰ chọn (Main Model + model việc nền khi đặt rõ provider), và tự tắt ngay khi bạn đổi sang nhà cung cấp khác - không phải chờ vòng quét 10 phút.
- **Bấm Ngắt (hoặc gỡ key cuối) của nhà đang là MAIN**: nhà đó rời Thứ tự dùng và thẻ kế tiếp lên làm MAIN để chat không gãy. Đây là hành vi cố ý, không phải lỗi.
- **Chat trả lời bằng một nhà khác MAIN**: MAIN đang hết lượt (hoặc mọi key của nó đang nghỉ), nên lượt đó chạy thẻ dự phòng, thẻ đó có nhãn **ĐANG DÙNG**. Lượt sau Javis lại thử MAIN trước.
- **ChatGPT OAuth báo chưa cài Codex CLI**: kênh này cần Codex CLI trên máy. Từ 0.28.8 hai engine CLI npm (Claude Code, Codex) đều được cài sẵn lúc cài Javis - bản Docker, `install.sh` lẫn `setup.bat` - nên báo thiếu thường là bản cài cũ, **cập nhật Javis** một lần là có. Cài tay cũng được: `npm i -g @openai/codex`.

## Liên quan

- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - đấu nguồn dữ liệu và công cụ cho mọi engine dùng chung.
- [Mức dùng: token & chi phí](23-muc-dung-token.md) - xem model nào, việc nào đang đốt nhiều nhất.
- [Agents & Workflows](07-agents-va-workflows.md) - chọn model riêng cho từng agent.
- [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) - cài Claude Code CLI và Codex CLI.

Nếu vẫn kẹt, xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
