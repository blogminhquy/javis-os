# Models & engine

Trang **Models** là nơi bạn chọn "bộ não" cho Javis: dùng engine nào, model nào để trả lời, đăng nhập vào nhà cung cấp AI, chọn model rẻ cho việc chạy nền, và bật mức suy nghĩ sâu. Đây là trang quyết định Javis thông minh tới đâu và tiêu hạn mức của gói nào.

Nếu bạn mới bắt đầu, xem trước [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md). Khi cần gắn thêm công cụ ngoài cho Javis, xem [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md).

## Tính năng này là gì

Javis có thể chạy trên nhiều "engine" (nhà cung cấp AI) khác nhau. Bạn chọn 1 cái làm **Main Model** (model chính cho hội thoại), và tùy chọn thêm:

- **Model việc nền**: model rẻ hơn cho những việc Javis tự chạy khi bạn không ngồi đó - loop, việc Kanban, nhắc hẹn, tự học, tiêu hoá nguồn.
- **Suy nghĩ (reasoning)**: mức độ model động não trước khi trả lời.

Điểm quan trọng nhất cần hiểu: **đổi model KHÔNG làm Javis mất chức năng.** Mọi provider đều được cấp cùng một bộ đồ nghề qua trung tâm kết nối (MCP Hub) của Javis: gọi kho Kết nối đã đấu, đọc/ghi file trong brain, chạy skill, giao việc Kanban (tool `javis_task`), tạo agent/workflow/loop/nhắc hẹn (tool `javis_schedule`).

| Cách gọi | Provider | MCP Javis · tool file brain · skill | Chạy lệnh máy (Bash) |
|---|---|---|---|
| Qua **Claude Code** | Anthropic OAuth (Claude Code) | Có - MCP native + skill native | **Có** |
| Qua **Codex** | OpenAI OAuth (ChatGPT) | Có - MCP qua hub (cả kết nối local như Zalo/Webcake) + kho MCP GỐC của Codex (server bạn tự `codex mcp add`) + skill qua router (`javis_use_skill` / đọc file `skills/`) | **Có** |
| Qua **Antigravity CLI** | Google Antigravity CLI (`agy`) | Có - MCP qua hub (ghi vào `~/.gemini/config/mcp_config.json`, xem B1b) + skill qua router | **Có** |
| Qua **Gemini CLI** ⛔ | Google Gemini CLI (cá nhân đã bị Google cắt 18/06/2026) | Có - MCP qua hub (ghi vào `.gemini/settings.json` trong chính brain đang mở) + skill qua router | **Có** |
| **Gọi API thẳng** | OpenRouter | Có - MCP qua hub + tool file vault + skill qua router | Không |
| **Gọi API thẳng** | OpenAI (API) | Có - như trên | Không |
| **Gọi API thẳng** | Anthropic (API) | Có - như trên | Không |
| **Gọi API thẳng** | Google Gemini (API) | Có - như trên (từ 0.9.270 trang Kết nối cũng hết báo nhầm) | Không |
| **Gọi API thẳng** | Groq (API) | Có - như trên | Không |
| **Gọi API thẳng** | Ollama Cloud | Có - như trên | Không |

### Bốn thứ engine API không có

Trước 0.17.1 trang này ghi "khác biệt **duy nhất** là chạy được lệnh máy hay không". Nói vậy gọn nhưng không đúng. Danh sách thật:

- **Lệnh máy (Bash)** - chạy lệnh trên máy chủ.
- **WebFetch và WebSearch** - tự mở một URL lạ ra đọc, tự tra web. Engine API muốn lấy dữ liệu ngoài thì phải qua một MCP đã đấu.
- **Task** - đẻ agent con chạy song song trong cùng một lượt.
- **Nối lại phiên cũ của CLI** - engine API dựng lại ngữ cảnh mỗi lượt.

Thêm hai giới hạn thực dụng của engine API: mỗi lượt tối đa **8 vòng gọi tool** (quá thì dừng và báo), và khi lượt **có gọi tool** thì câu trả lời hiện một cục ở cuối chứ không chạy dần từng chữ (mỗi vòng là một request riêng).

Ngoài từng ấy, mọi năng lực còn lại là như nhau. Cụ thể là: gọi mọi MCP đã đấu, đọc và ghi file trong brain, đọc file bạn vừa đính kèm hoặc dán vào khung chat, chạy skill, giao việc Kanban, tạo loop và nhắc hẹn, tạo agent/workflow/skill (chúng chỉ là file `.md` trong vault), tạo ảnh, dùng tool của plugin.

> **Đọc file đính kèm trên engine API có từ 0.43.1.** Trước đó `javis_read_file` chỉ nhìn thấy bên trong brain, trong khi file bạn kéo-thả hay dán vào khung chat lại rơi xuống `.staging` ở ngoài - nên engine API báo lỗi rồi bảo bạn tự chép file vào thư mục Brain. Nay tool đó nhận cả đường dẫn file vừa đính kèm. Vẫn CHỈ đúng thư mục nhận file đó và CHỈ để đọc: ghi vẫn khoá trong brain, và chatbot nói chuyện với khách của bạn thì không thấy mấy file này.

> **Giao việc Kanban từ engine API có từ 0.17.1.** Trước đó đường duy nhất là `POST /kanban/task`, mà gọi được nó thì phải có Bash và curl - nên chỉ Claude Code với Codex làm được, dù tài liệu vẫn hứa mọi bộ não đều làm được. Nay có tool `javis_task` đi qua hub nên lời hứa đó thành đúng.

Nói ngắn gọn: **năng lực nằm ở Javis, không nằm ở model.** Ba engine CLI (**Claude Code** với gói Claude, **Codex** với gói ChatGPT, **Antigravity CLI** với gói Google) tận dụng chính gói subscription bạn đang trả và chạy thêm được lệnh máy; sáu provider API chỉ cần một API key và làm được mọi thứ còn lại - kể cả điều phối việc, tạo loop, chạy skill. Agent trong Workflow cũng chọn được model theo nhà cung cấp - xem [Agents & Workflows](07-agents-va-workflows.md).

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định ở cổng `7777`).
2. Ở thanh bên trái, mở nhóm **Kết nối**, rồi bấm mục **Models**.
3. Trang Models hiện 4 khối theo thứ tự: **◆ Main Model** ("model chính cho hội thoại"), **◆ Providers** ("đăng nhập / kết nối nhà cung cấp model"), **◆ Model việc nền** ("loop · việc Kanban · nhắc hẹn · tự học · tiêu hoá nguồn"), **◆ Suy nghĩ** ("độ sâu reasoning khi trả lời").

## Mười provider có sẵn

Khối **Providers** liệt kê 10 nhà cung cấp. **Cái nào đã kết nối được xếp lên đầu**, chưa kết nối dồn xuống dưới; trong mỗi nhóm giữ nguyên thứ tự gốc bên dưới. Nhờ vậy máy đã đấu vài nhà cung cấp thì mở trang ra là thấy ngay chúng, khỏi cuộn tìm.

| Provider (nhãn trên màn hình) | Kiểu kết nối | Ghi chú |
|---|---|---|
| **Anthropic OAuth (Claude Code)** | Đăng nhập Claude Code, không cần key | Đầy đủ MCP/skill/tool máy. Là Main Model mặc định |
| **OpenAI OAuth (ChatGPT)** | Device code (đăng nhập gói ChatGPT) | Chạy qua Codex, đấu kho Kết nối qua hub + dùng skill qua router |
| **Google Antigravity CLI** | Gõ `agy` **một lần trong terminal**, không cần key | Bản Google chỉ định thay Gemini CLI. Chạy qua binary `agy`. Đầy đủ MCP/skill/tool máy, và chọn được **đúng dàn model của Antigravity IDE** (có cả model không phải của Google) |
| **Google Gemini CLI** | Đăng nhập Google, hoặc `GEMINI_API_KEY` | ⛔ Google đã **ngắt mọi tài khoản cá nhân** từ 18/06/2026 (miễn phí, AI Pro, Ultra). Chỉ còn chạy được với giấy phép Code Assist doanh nghiệp hoặc API key - xem [B2](#b2-gemini-cli---google-đã-ngắt-với-tài-khoản-cá-nhân-18062026) |
| **OpenRouter** | Dán API key | Nhiều model 1 chỗ, MCP + tool file + skill qua hub |
| **Anthropic (API)** | Dán API key | MCP + tool file + skill qua hub (từ 0.9) |
| **OpenAI (ChatGPT API)** | Dán API key | MCP + tool file + skill qua hub |
| **Google Gemini (API)** | Dán API key | MCP + tool file + skill qua hub |
| **Groq (API)** | Dán API key | MCP + tool file + skill qua hub. Suy luận rất nhanh, hợp làm model việc nền. Key này còn là thứ cho phép **ra lệnh bằng ghi âm trên Telegram và Zalo** (Whisper nghe giọng thành chữ) - xem [Telegram](11-telegram.md) và [Kênh Zalo Bot](26-kenh-zalo-bot.md); đấu key là đủ, không bắt buộc đổi model chính sang Groq |
| **Ollama Cloud** | Dán API key lấy ở ollama.com | MCP + tool file + skill qua hub. Model mã nguồn mở cỡ lớn (gpt-oss, qwen3-coder, deepseek) chạy trên máy chủ của Ollama |

Mỗi card provider hiển thị trạng thái **● Đã kết nối** hoặc **○ Chưa kết nối**, kèm số model khả dụng, và một nhãn kiểu bên cạnh tên: **MCP/skill** (Claude Code), **Device code** (ChatGPT), **MCP Javis** (các provider API). Card nào đang là Main Model sẽ có nhãn **MAIN**.

> Nhãn của các provider API trước 0.9.270 ghi là **chat**, khiến nhiều người tưởng chúng chỉ chat suông. Sai: chúng gọi kho Kết nối, đọc/ghi brain và chạy skill y như hai engine CLI. Nhãn giờ là **MCP Javis** cho đúng.

## Cách dùng (từng bước)

### A. Kết nối Claude Code (mặc định)

Đây là engine mặc định. Nó dùng được toàn bộ công cụ, skill và bộ nhớ, cộng thêm chạy lệnh máy. Không bắt buộc: nếu bạn không có gói Claude thì bỏ qua mục này và đi thẳng xuống mục B (ChatGPT) hoặc C (API key) - Javis chạy đủ chức năng như nhau, chỉ thiếu phần lệnh máy khi đi bằng API key.

1. Vào **Models**, tìm card **Anthropic OAuth (Claude Code)**.
2. Nếu chưa đăng nhập, card báo **○ Chưa đăng nhập** và có hai nút: **Đăng nhập Claude** và **↻ Kiểm tra lại**.
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

Muốn ngắt: bấm **Ngắt** trên card này. Nếu ChatGPT đang là Main Model khi bạn ngắt, Javis tự chuyển Main Model về Claude Code để chat không bị gãy.

Lưu ý: đây là kênh thử nghiệm (chạy nền Codex). Nếu cần ổn định tối đa, dùng Claude Code hoặc OpenRouter.

### B1b. Kết nối Antigravity CLI (dùng gói Google của bạn)

Đây là đường **Google chỉ định** sau khi họ ngắt Gemini CLI với tài khoản cá nhân. Ưu điểm lớn nhất: bạn chọn được **đúng dàn model hiện trong Antigravity IDE**, gồm cả model không phải của Google.

1. Cài CLI một lần trên máy chạy Javis:
   - Linux/macOS: `curl -fsSL https://antigravity.google/cli/install.sh | bash`
   - Windows PowerShell: `irm https://antigravity.google/cli/install.ps1 | iex`
2. Gõ `agy` một lần **trong terminal của máy chạy Javis**. Máy có màn hình thì nó tự mở trình duyệt; qua SSH thì nó in ra một đường link - mở link đó trên máy bạn rồi đăng nhập Google. Phiên lưu trong keyring của hệ điều hành nên chỉ phải làm một lần.
3. Quay lại **Models**, thẻ **Google Antigravity CLI**, bấm **Kiểm tra lại** (nó chạy thử một lượt chat thật). Thẻ đổi sang **● Đã đăng nhập**.
4. Bấm **Đổi model ▾** ở khối Main Model, chọn nhà cung cấp này rồi chọn model.

Danh sách model **hỏi thẳng `agy models`** chứ Javis không giữ bảng chép tay, nên tài khoản bạn được cấp model nào là thấy đúng model đó, và Google đổi tên model cũng không làm picker lạc hậu.

Vài chỗ khác với Gemini CLI, nói trước cho khỏi hiểu nhầm:

- **Đăng nhập làm trong terminal, dashboard không có nút** (từ 0.32.2). Bản 0.30.0 từng dựng một luồng đăng nhập ngay trên trang: Javis mở `agy` trong một terminal giả rồi làm người đưa thư giữa nó và trình duyệt của bạn. Nó chạy được trên Linux, nhưng cái hiện ra trên trang là một ô terminal bấm vào không ăn nên rốt cuộc vẫn phải mở terminal thật, còn Windows thì không có pseudo-terminal nên chưa bao giờ dùng được. Người dùng `agy` đều là dân code sẵn terminal trong tay, nên gõ một lệnh gọn hơn hẳn một luồng UI nửa vời. Đổi lại, Javis không cầm token của ai - nó nằm trong keyring hệ điều hành.
- **Mức Chỉ đọc ở đây nhẹ hơn.** Bên Gemini CLI, mức `suggest` xuống thẳng `--approval-mode plan` nên chính CLI chặn. `agy` không có nấc tương đương, nên Javis siết bằng `--sandbox` cộng với lời dặn trong system prompt. Rào tiền/đơn/đăng bài vẫn nằm ở MCP Hub như mọi engine.
- **Chưa nối lại mạch hội thoại của CLI.** Mỗi lượt mở mạch mới rồi mồi lại bằng lịch sử đã lưu, nên **không mất ngữ cảnh** nhưng tốn token hơn.
- Javis không tự cài `agy` lúc cài đặt (khác ba engine npm): trình cài của Google là một script tải về chạy thẳng, nên để bạn tự chạy khi muốn.
- **Trên Windows, prompt không đi qua dòng lệnh nữa** (từ 0.33.1, sửa tiếp ở 0.33.2). Windows chặn tổng dòng lệnh ở 32767 ký tự, mà riêng system prompt của Javis trên một brain trống đã hơn 36.000 - tức bộ não này từng chết hẳn trên Windows, và câu báo lỗi lại đổ cho "hội thoại quá dài" nên mở chat mới bao nhiêu lần cũng không thoát.
- **Javis ĐO xem bản `agy` của bạn nhận prompt kiểu gì, không đoán.** Đây là bài học phải trả giá hai lần: bản 0.33.1 suy cú pháp từ tài liệu chính chủ (CHANGELOG 1.1.1 nói `agy` đọc stdin khi prompt không cấp qua cờ) rồi gửi `--print ""`, và bản `agy` thật trả lại `Error: empty prompt` vì nó kiểm giá trị cờ trước khi ngó tới stdin. Tài liệu đúng về nguyên lý, sai về cú pháp. Nay lần chạy đầu tiên Javis thử ba cách bơm stdin bằng một prompt tí hon có mã riêng, cách nào vọng mã về thì dùng cách đó, rồi nhớ lại cho những lần sau. Không cách nào ăn thì nó ghi ngữ cảnh ra file và bảo model tự đọc; model không đọc được thì nó nói thẳng chứ không lặng lẽ trả lời thiếu luật.

- **Tool của Javis đấu vào đâu, và vì sao chỗ đó** (sửa ở 0.43.0). Đây là chỗ sai ba bản liên tiếp mà không bản nào lộ ra, vì hỏng kiểu này không có câu lỗi nào: `agy` vẫn chạy, vẫn trả lời trôi chảy, chỉ là không có lấy một tool nào của Javis - không MCP, không Kanban, không skill. Hai chỗ sai chồng lên nhau:
  - **Sai tên trường.** Javis ghi `httpUrl`, đó là schema của Gemini CLI chép nguyên sang. `agy` đọc `serverUrl` (tài liệu di trú của Google nói thẳng là trường `url` được đổi tên thành `serverUrl`). Entry không có trường nào nó hiểu thì server không có địa chỉ, và nó bỏ qua trong im lặng.
  - **Sai chỗ đặt.** Javis ghi vào trong brain. `agy` nạp MCP từ cấu hình **tầng HOME**: `~/.gemini/config/mcp_config.json` (hiện hành, dùng chung với Antigravity 2.0/IDE) và `~/.gemini/antigravity-cli/mcp_config.json` (đường cũ). Tầng workspace `<brain>/.agents/mcp_config.json` có thật trong tài liệu, nhưng issue #60 của chính repo `antigravity-cli` ghi nhận CLI **tìm thấy rồi bỏ qua** `mcpServers` trong đó. Nay Javis ghi cả hai tầng: HOME để chạy được ngay, workspace để bản nào vá xong issue đó thì tự có cách ly theo brain.

  Hệ quả phải biết: file HOME là **của bạn** và dùng chung với Antigravity IDE, nên IDE cũng sẽ thấy tool của Javis; và hai brain chạy `agy` cùng lúc thì brain sau ghi đè brain trước. Không muốn Javis đụng vào HOME thì đặt `JAVIS_AGY_MCP_HOME=0` (khi đó chỉ còn đường workspace, tức chỉ chạy trên bản `agy` đã vá issue #60). Muốn chỉ định một file khác thì đặt `JAVIS_AGY_MCP_CONFIG=/đường/dẫn/mcp_config.json`. Bản `agy` của bạn từ chối cấu hình vì có khoá lạ thì đặt `JAVIS_AGY_MCP_KEY=serverUrl` (hoặc `=url` cho bản 1.0.x cũ) để Javis chỉ ghi đúng một khoá.

  **Tự kiểm trong 10 giây:** vào **Models**, thẻ **Google Antigravity CLI**, bấm **Kiểm tra lại**. Nó ghi lại cấu hình rồi đọc lại chính file đó, và báo một trong ba câu: *tool của Javis đã đấu*, *chưa đấu được tool của Javis*, hoặc *trung tâm kết nối đang tắt*. Xem tận file thì: `cat ~/.gemini/config/mcp_config.json` - phải thấy một entry tên `javis` có `serverUrl` trỏ về `/hub/mcp`.

- **Dấu tiếng Việt không vỡ dọc đường** (từ 0.33.6). Triệu chứng cũ: chữ "gồm" thành `g<?><?>m`, mỗi ký tự tiếng Việt 3 byte hoá đúng 3 dấu `<?>`. Đó là chữ ký của một bên đọc cắt mẩu ống dẫn giữa một ký tự rồi giải mã từng mẩu rời. Đã đo và loại trừ phía Javis (bộ đọc của nó dùng giải mã tăng dần, cắt byte giữa ký tự vẫn ghép lại đúng), nên chỗ vỡ nằm ở bộ đọc của `agy`. Javis không vá được CLI, nhưng chỉnh được chỗ mình đặt ranh giới: nay nó bơm prompt theo từng mẩu kết thúc đúng biên ký tự, nên bên kia đọc kiểu gì cũng không vỡ. Chữ về mà vẫn có ký tự hỏng thì Javis tự đổi sang đường file rồi hỏi lại một lần; vẫn hỏng thì nó nói thẳng là lỗi nằm trong CLI.

**Nếu vẫn gặp lỗi trên Windows**, đặt biến môi trường `JAVIS_AGY_PROMPT_DAI=file` để ép đi thẳng đường file, rồi báo lại giúp kèm câu lỗi `agy` in ra.

### B2. Gemini CLI - Google đã ngắt với tài khoản cá nhân (18/06/2026)

> ⛔ **Đọc trước khi làm theo mục này.** Ngày 18/06/2026 Google ngừng phục vụ Gemini CLI cho **mọi tài khoản cá nhân** - gói miễn phí, Google AI Pro và Google AI Ultra đều bị cắt. Đăng nhập vẫn xong, nhưng tới lúc chat thì CLI trả về `IneligibleTierError` kèm `reasonCode: UNSUPPORTED_CLIENT`. Đây là chặn ở phía máy chủ Google, **không phải lỗi cấu hình và Javis không vá được**.
>
> Còn dùng được nếu bạn có **giấy phép Gemini Code Assist doanh nghiệp**, hoặc chạy CLI bằng **API key** (`GEMINI_API_KEY`) - nhưng đã trả tiền theo lượt gọi thì thẻ **Google Gemini (API)** ở mục C gọn hơn.
>
> **Muốn model Gemini, hoặc muốn một trình chọn model nhiều như Antigravity:** dùng **OpenRouter** (nhiều model một chỗ, có cả Gemini lẫn Claude, một API key) hoặc **Google Gemini (API)**.
>
> Bản thay thế chính chủ của Google là **Antigravity CLI** (binary `agy`, cài bằng `curl -fsSL https://antigravity.google/cli/install.sh | bash`). Javis **chưa** đấu engine này.

> **Từ 0.29.1 thẻ này TỰ ẨN** ở trang Models khi máy không có binary `gemini` - tức là gần như mọi người sẽ không thấy nó nữa, khỏi vấp vào một lựa chọn đã chết. Máy nào có cài `gemini` (thường là máy dùng giấy phép doanh nghiệp hoặc chạy bằng API key) thì thẻ hiện lại như cũ, và ai đang ĐẶT nó làm Main Model cũng vẫn thấy để còn đổi sang engine khác. Javis cũng thôi cài sẵn `@google/gemini-cli` lúc cài đặt; cần thì tự cài một dòng `npm i -g @google/gemini-cli`.

Phần dưới giữ lại cho ai còn thuộc diện dùng được (doanh nghiệp / API key).

1. Kiểm CLI đã có chưa. Bản cài bằng Docker và bằng `install.sh` **đã cài sẵn** `@google/gemini-cli`, nên thường bỏ qua được bước này. Chỉ khi thẻ báo *"Chưa cài Gemini CLI"* mới cài tay trên máy chạy Javis: `npm install -g @google/gemini-cli`
2. Vào **Models**, thẻ **Google Gemini CLI (đăng nhập Google)**, bấm **Đăng nhập Google**.
3. Javis mở trang đồng ý của Google (hiện đúng tên ứng dụng **Gemini CLI**). Đăng nhập bằng tài khoản Google của bạn, đồng ý xong Google hiện ra **một mã**.
4. Chép mã đó dán vào ô trong Javis, bấm **Xong**. Thẻ đổi sang **● Đã đăng nhập Google** kèm email.
5. Bấm **Đổi model ▾** ở khối Main Model, chọn nhà cung cấp này và một model (mặc định `gemini-2.5-pro`).

Không có localhost nào ở giữa nên cách này chạy được **cả khi Javis nằm trên VPS còn trình duyệt ở máy bạn** - giống hệt luồng đăng nhập Claude Code. Javis dùng đúng client OAuth công khai của Gemini CLI, nên màn hình đồng ý của Google ghi tên **Gemini CLI**, đúng cái sẽ dùng token.

Đăng nhập xong Javis giữ refresh token (mã hoá trong `settings.json`) và **dựng lại file credential cho CLI trước mỗi lượt chạy** - cần vậy vì bản Gemini CLI mới nạp file đó vào keychain rồi xoá đi.

Bấm **Ngắt** để gỡ tài khoản Google khỏi Javis. Nút này chỉ hiện khi bạn đăng nhập qua dashboard; ai đã tự chạy `gemini` trong terminal thì token là của CLI, Javis không gỡ hộ.

Vẫn đăng nhập bằng terminal được nếu thích: chạy `gemini` rồi chọn **Login with Google**. Javis nhận ra cả tài khoản kiểu đó.

Cài ở chỗ lạ mà Javis không tìm ra binary thì đặt biến môi trường `JAVIS_GEMINI_BIN` trỏ thẳng vào nó rồi khởi động lại.

**Vì sao không nối thẳng vào Antigravity:** app đó là Electron thuần, không có cổng dòng lệnh nào để gọi ngầm, và token của nó nằm trong Keychain đã mã hoá. Kể cả moi ra được thì đó là API nội bộ Google không cam kết hỗ trợ bên thứ ba, hỏng lúc nào không biết. Gemini CLI cho đúng cái gói đó bằng đường Google công khai.

### C. Kết nối provider bằng API key (OpenRouter / Anthropic API / OpenAI API / Gemini / Groq)

1. Vào **Models**, tìm card provider tương ứng.
2. Dán API key vào ô nhập (ô ghi "dán API key để kết nối").
3. Bấm **Kết nối**.
4. Card chuyển sang **● Đã kết nối** kèm số model.

Muốn đổi key sau này: nhập key mới rồi bấm **Đổi key** (ô lúc này ghi "đổi key" kèm 4 ký tự cuối của key cũ). Muốn ngắt: bấm **Ngắt** (thao tác này xoá key). Nếu provider đang là Main Model khi bị ngắt, Javis tự chuyển về Claude Code.

Lấy key ở đâu:

- **OpenRouter**: trang openrouter.ai (một key gọi được rất nhiều model của nhiều hãng).
- **Anthropic (API)**: console.anthropic.com.
- **OpenAI (ChatGPT API)**: platform.openai.com.
- **Google Gemini (API)**: key của Gemini API, lấy ở aistudio.google.com.

### D. Đặt Main Model (chọn model chính)

1. Ở khối **◆ Main Model** trên cùng trang Models, bạn thấy model đang dùng và tên provider.
2. Bấm nút **Đổi model ▾**.
3. Cửa sổ **SET MAIN MODEL** hiện ra, dòng phụ ghi "hiện tại: &lt;model&gt; · &lt;provider&gt;":
   - Cột trái: danh sách provider. Provider chưa kết nối có ghi chú **⚠ cần kết nối**; provider đang dùng có ghi chú **ĐANG DÙNG**.
   - Cột phải: danh sách model của provider đang chọn.
   - Ô **Lọc provider / model…** ở trên để gõ tìm nhanh (lọc cả hai cột cùng lúc).
4. Bấm chọn provider ở cột trái, rồi bấm chọn model ở cột phải. Model đang dùng có nhãn **ĐANG DÙNG**.
5. Bấm **Switch** để áp dụng, hoặc **Huỷ** (hay nút ✕) để đóng.

Danh sách model được nạp động từ chính provider (có nhãn **· live**). Nếu không lấy được từ mạng, Javis dùng danh sách dự phòng (nhãn **· catalog**); đang tải thì hiện **· đang tải…**. Model bạn chọn được lưu và áp dụng cho phiên chat mới.

Khối Main Model cũng ghi một dòng về engine đang dùng, nói rõ đường đi và giới hạn thật: "Qua Claude Code - MCP Javis + skill + loop + chạy lệnh máy", "Qua Codex - MCP Javis + skill + loop + chạy lệnh máy", hoặc "Gọi API thẳng - MCP Javis + skill + loop (không chạy lệnh máy)". Trước 0.9.270 dòng cuối ghi "chat thuần (không MCP)" - sai và đã bỏ.

### E. Chọn model việc nền

Khối **◆ Model việc nền** quyết định model nào chạy những việc Javis làm khi bạn không ngồi trước máy: **loop · việc Kanban · nhắc hẹn · tự học · tiêu hoá nguồn**. Đây thường là phần đốt hạn mức âm thầm nhất, nên chọn model rẻ ở đây tiết kiệm thấy rõ.

1. Xuống khối **◆ Model việc nền**. Dòng lớn cho biết đang dùng gì: chưa đổi gì thì ghi **Mặc định của Claude Code** kèm dòng nhỏ "không đổi model, dùng model mặc định".
2. Bấm **Đổi model ▾**. Cửa sổ mở ra giống hệt bảng chọn Main Model nhưng tiêu đề là **MODEL VIỆC NỀN**, chân bảng ghi "Việc nền: loop · việc Kanban · nhắc hẹn · tự học · tiêu hoá nguồn", và nút áp dụng tên là **Chọn**.
3. Chọn provider ở cột trái, model ở cột phải, rồi bấm **Chọn**.
4. Muốn quay lại như cũ: bấm **Về mặc định** (nút này chỉ hiện khi bạn đã đặt một model riêng).

Vài điều cần biết:

- **Chọn được MỌI provider bạn đã đấu**, không riêng Claude: Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Gemini, Anthropic API. Chọn nhà cung cấp khác thì việc nền chạy bằng gói hoặc khoá của nhà đó, không ăn vào hạn mức Claude nữa.
- Nếu bạn chọn một provider **chưa kết nối**, khối này hiện cảnh báo "⚠ nhà cung cấp này chưa kết nối - việc nền sẽ tự dùng lại Claude". Việc nền không chết, chỉ là không tiết kiệm được.
- **Công cụ không giống nhau giữa các đường.** Claude Code và Codex đọc/ghi file trực tiếp trong brain. Các model API (OpenRouter, OpenAI, Gemini, Anthropic API) đọc/ghi qua công cụ vault của Javis và **không chạy được lệnh máy**, nên hợp với việc đọc - tổng hợp - ghi ghi chú; việc nền nào cần chạy lệnh thì cứ để Claude.
- Với đường API, công cụ ghi file tự khoá lại khi loop đang ở mức `suggest`, đúng như khi chạy bằng Claude.

### F. Đặt mức Suy nghĩ (reasoning)

Bật để model động não kỹ hơn trước khi trả lời: chính xác hơn, nhưng chậm hơn và tốn token hơn.

1. Xuống khối **◆ Suy nghĩ**.
2. Bấm một trong 4 mức: **Tắt**, **Thấp**, **Vừa**, **Cao**.

Mức này áp dụng khác nhau tuỳ engine:

- **Claude API / OpenRouter**: dùng adaptive thinking + mức effort tương ứng.
- **OpenAI**: chỉ áp cho các model dòng o-series (o1/o3/o4) và gpt-5; model thường sẽ bỏ qua.
- **Gemini**: chỉ áp cho model 2.5 trở lên (và các model có chữ "thinking"). Model cũ hơn không được gửi tham số này để tránh lỗi.
- **Claude Code**: chèn gợi ý suy nghĩ vào câu hỏi (từ mức think tới ultrathink theo độ sâu tăng dần).

## Engine Claude chạy bằng gì bên dưới

Từ bản 0.9.37, engine Claude của Javis chạy **duy nhất qua Claude Agent SDK** (bộ thư viện chính chủ của Anthropic). Nhánh cũ tự gọi lệnh `claude` như một tiến trình rời đã bị gỡ hẳn. Hai điều người dùng cần biết:

- **Máy vẫn PHẢI có `claude` CLI.** SDK gọi chính CLI đó bên dưới, và toàn bộ phần đăng nhập lẫn MCP native đều đi qua nó. Chưa cài CLI thì card Claude Code báo lỗi và engine không chạy - xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).
- **Quyền công cụ ở phiên chạy nền được chặn theo TỪNG LẦN GỌI.** Khi loop hoặc workflow chạy trong chế độ nền an toàn, mỗi lần Javis định gọi một công cụ ngoài danh sách cho phép là bị từ chối ngay tại chỗ và ghi vào nhật ký, chứ không chỉ khai báo danh sách lúc khởi động. Thông báo từ chối nói rõ đây là rào quyền của phiên nền, **không phải** kết nối MCP hỏng - gặp dòng đó thì đừng đi đăng nhập lại connector.

## Claude Code (đầy đủ công cụ) và gọi API thẳng khác nhau ra sao

Đây là điểm dễ nhầm nhất, cần nắm rõ:

- **Main Model = Claude Code**: mạnh nhất - đọc/ghi file native, chạy lệnh máy, gọi MCP, skill native, loop tự động, session resume. Chế độ khai thác hết sức mạnh Javis OS.
- **Main Model = ChatGPT OAuth (Codex)**: gọi được toàn bộ kho Kết nối (hub tự đẩy sang Codex, gồm cả kết nối local như Zalo), có tool file của Codex, và dùng được skill qua router (Javis bơm danh sách skill vào system prompt + tool `javis_use_skill`; Codex chạy cwd=brain nên đọc thẳng `skills/<slug>/SKILL.md`). Ngoài ra Codex còn nạp kho MCP GỐC của chính nó (server bạn tự đăng ký bằng `codex mcp add`, xem trong khối gập "◆ Kết nối sẵn của Claude Code và Codex" ở trang Kết nối) - tương tự cách engine Claude dùng MCP gốc của Claude Code.
- **Main Model = OpenRouter / OpenAI (API) / Anthropic (API) / Gemini**: từ bản 0.9 cả bốn đều gọi được kho Kết nối qua vòng gọi tool, kèm tool đọc/ghi file trong vault và kích hoạt skill (`javis_use_skill`). **Việc nền cũng chạy được bằng những provider này** (xem mục E). Khác biệt còn lại so với Claude Code: không có tool chạy lệnh máy (Bash), không có WebFetch, và không resume được session CLI.

Kết luận thực dụng: để Javis "làm việc" trọn vẹn nhất, giữ Main ở **Claude Code**. Chuyển sang provider API khi bạn muốn thử một model cụ thể của hãng khác, hoặc muốn đẩy phần việc nền sang một gói rẻ hơn cho đỡ hạn mức Claude.

## Tiết kiệm token áp cho cả gói thuê bao

Khối **Chế độ tiết kiệm token** ở đầu trang **Mức dùng** (nhóm Hệ thống) cho Javis gửi ít chữ hơn mỗi lượt: chỉ nạp phần bộ nhớ liên quan tới câu hỏi, chỉ nạp skill khi cần thay vì liệt kê hết.

Từ bản 0.12.4, phần này chạy được cho **cả ba loại bộ não**, không riêng bộ não dùng API key:

| Loại bộ não | Vì sao vẫn đáng bật |
|---|---|
| API key (OpenRouter, OpenAI, Anthropic, Gemini, Groq) | Ít token là ít tiền, và tránh được lỗi vượt hạn mức token mỗi phút |
| Gói Claude (Claude Code) | Ít token là mỗi cửa sổ 5 tiếng dùng được nhiều lượt hơn |
| Gói ChatGPT (Codex) | Như trên |

Mở trang là thấy ngay khối **Bộ não đang dùng**: nó nói bộ não hiện tại thuộc loại nào, đang ăn được mấy mảng tiết kiệm, và mảng nào không áp cho nó cùng lý do. Có mảng cố ý chỉ chạy trên bộ não dùng API key - ví dụ phần gửi lại lịch sử hội thoại, vì Claude Code và Codex vốn tự nhớ mạch hội thoại của chúng, gửi thêm là gửi hai lần.

**Hết lượt gói thuê bao** thì Javis nói bằng tiếng Việt: hết lượt gói nào, còn khoảng bao lâu nữa, và bộ não nào bạn đã cắm sẵn để chạy tạm trong lúc chờ. Javis **không tự đổi bộ não hộ** - đổi là tiêu hạn mức của một tài khoản khác, có khi mất tiền thật, nên đó là quyết định của bạn (đổi ở ngay trang này, hội thoại giữ nguyên). Lưu ý loại hạn mức này đếm **lượt dùng theo giờ** chứ không đếm độ dài, nên rút gọn câu hỏi không giúp gì.

## Đổi nhanh model

Bạn không cần rời trang Models để đổi model: bấm **Đổi model ▾** ở khối Main Model là mở ngay bảng **SET MAIN MODEL**, chọn provider + model rồi **Switch**. Thao tác này lưu lại và áp dụng cho phiên chat mới. Khối **◆ Model việc nền** có nút **Đổi model ▾** riêng của nó (mở bảng **MODEL VIỆC NỀN**), còn các nút mức ở khối **◆ Suy nghĩ** áp dụng ngay khi bấm.

## Đổi model giữa chừng một cuộc trò chuyện

Đổi model ngay trong lúc đang chat thì **cuộc trò chuyện đi tiếp liền mạch**: model mới đọc được toàn bộ những gì đã nói trước đó và trả lời tiếp, không hỏi lại từ đầu. Bạn đổi bao nhiêu lần trong một cuộc cũng được.

Bên dưới, Javis làm việc này theo hai cách tuỳ loại bộ não:

- **Bộ não dùng API key** (OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama) vốn không tự nhớ gì, nên mỗi lượt Javis gửi lại lịch sử hội thoại cho chúng.
- **Bộ não chạy bằng gói thuê bao** (Claude Code, ChatGPT/Codex, Gemini CLI) thì tự giữ mạch hội thoại của riêng chúng, và Javis nối lại đúng mạch đó cho rẻ. Nhưng ngay khi một lượt do bộ não khác trả lời, mạch cũ đó **thiếu đúng lượt vừa rồi**. Javis vì vậy bỏ liên kết mạch của mọi bộ não khác sau mỗi lượt; lần bạn quay lại bộ não đó, nó dựng lại ngữ cảnh từ lịch sử đã lưu thay vì nối tiếp một mạch khuyết.

Nói ngắn: đổi qua đổi lại vẫn liền mạch, chỉ là lượt đầu tiên sau khi đổi tốn thêm một chút vì phải gửi lại lịch sử.

Từ 0.42.1 trở về trước có lỗi ở đúng chỗ này: chỉ mạch của ChatGPT/Codex được bỏ liên kết, còn Claude Code và Gemini CLI thì không, nên quay lại một trong hai bộ não đó là chúng nói như chưa hề có mấy lượt ở giữa.

## Bảng tra nhanh nút và trạng thái

| Nút / dòng chữ | Ở đâu | Nghĩa là gì |
|---|---|---|
| **MAIN** | Góc card provider | Provider này đang là Main Model |
| **● Đã kết nối** / **○ Chưa kết nối** | Card provider | Trạng thái, kèm số model khả dụng |
| **○ Chưa đăng nhập** | Card Claude Code | Chưa đăng nhập Claude Code trên máy |
| **Đăng nhập Claude** | Card Claude Code | Bắt đầu luồng đăng nhập bằng link |
| **↻ Kiểm tra lại** | Card Claude Code (chỉ khi chưa đăng nhập) | Hỏi lại trạng thái đăng nhập |
| **Đăng nhập ChatGPT** | Card OpenAI OAuth | Đăng nhập bằng mã device code |
| **Qua trình duyệt** | Card OpenAI OAuth | Đường dự phòng khi workspace chặn device code |
| **Kết nối** / **Đổi key** / **Ngắt** | Card provider API | Lưu key mới / thay key / xoá key |
| **Đổi model ▾** | Main Model và Model việc nền | Mở bảng chọn model tương ứng |
| **Về mặc định** | Model việc nền | Trả việc nền về model mặc định của Claude Code |
| **ĐANG DÙNG** | Bảng chọn model | Provider hoặc model hiện đang được đặt |
| **⚠ cần kết nối** | Bảng chọn model, cột trái | Provider đó chưa có key / chưa đăng nhập |
| **· live** / **· catalog** | Bảng chọn model | Danh sách lấy được từ mạng / danh sách dự phòng |
| **Switch** / **Chọn** | Chân bảng chọn model | Áp dụng cho Main Model / cho model việc nền |

## Mẹo

- Nếu chỉ muốn Javis nhớ và làm việc trơn tru, đừng đổi Main khỏi Claude Code. Các provider khác dành cho nhu cầu đặc biệt.
- Đặt **Model việc nền** là model rẻ để loop, việc Kanban, nhắc hẹn, tự học và tiêu hoá nguồn không ngốn hết hạn mức của gói chính. Muốn biết chỗ nào đang đốt nhiều nhất thì xem [Mức dùng: token & chi phí](23-muc-dung-token.md).
- Bật **Suy nghĩ** mức Vừa hoặc Cao khi hỏi việc khó (phân tích, chiến lược); tắt khi chỉ hỏi nhanh để đỡ chờ.
- OpenRouter là lựa chọn tiện nếu muốn thử nhiều model của nhiều hãng chỉ với một key.
- Muốn ChatGPT gọi được công cụ bán hàng của bạn: gắn kết nối trong trang [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) trước, Javis sẽ tự đẩy sang Codex.

## Sự cố thường gặp

- **Card Claude Code báo "Claude CLI chưa cài"**: máy chưa cài Claude Code CLI. Engine Claude bắt buộc phải có nó (SDK gọi chính CLI này bên dưới). Cài xong bấm **↻ Kiểm tra lại**. Xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).
- **Đăng nhập ChatGPT không ra mã, hoặc báo lỗi ngay**: workspace của bạn có thể đã chặn device code. Dùng nút **Qua trình duyệt** ở mục B.
- **Đăng nhập ChatGPT báo "Hết hạn, thử lại."**: Javis chờ khoảng 16 phút rồi bỏ cuộc. Bấm **Đăng nhập ChatGPT** lại để lấy mã mới.
- **Chọn được provider nhưng cột model trống**: provider đó chưa kết nối, hoặc chưa có model. Kết nối lại ở khối Providers, hoặc thêm model vào `settings.json` (mục `model.catalog`). Xem [Cấu hình .env](16-cau-hinh-env.md).
- **Model trả về rỗng**: thử lại hoặc đổi sang model khác trong bảng SET MAIN MODEL. Với Anthropic API, thông báo còn kèm lý do (ví dụ hết max_tokens: nhắn "tiếp tục" để model viết tiếp).
- **Trang Kết nối hiện dòng vàng "⚠ Main Model đang là ... - chưa hỗ trợ gọi công cụ. Đổi ở trang Models."**: từ 0.9.270 **không provider có sẵn nào** làm nổ dòng này nữa. Trước đó Google Gemini bị sót khỏi danh sách nên báo nhầm dù bên dưới đã chạy MCP qua hub bình thường. Dòng vàng giờ chỉ còn để chặn provider lạ. Sáu provider Claude Code, OpenRouter, OpenAI, Anthropic API, Gemini và Groq hiện thẻ XANH; riêng ChatGPT OAuth có thẻ xanh riêng nói rõ nó chạy qua Codex CLI.

- **Banner đỏ "⚠ Bộ não claude mất đăng nhập" trên máy chưa từng cài Claude**: sửa ở 0.9.270. Đèn báo não giữ trạng thái trong RAM và không ai dọn, nên đèn đỏ thắp hồi Claude còn là Main Model treo mãi sau khi bạn đổi sang OpenRouter. Giờ đèn chỉ tính những bộ não bạn THẬT SỰ chọn (Main Model + model việc nền khi đặt rõ provider), và tự tắt ngay khi bạn đổi sang nhà cung cấp khác - không phải chờ vòng quét 10 phút.
- **Bấm Ngắt provider đang là Main**: Javis tự chuyển Main về Claude Code để chat không gãy. Đây là hành vi cố ý, không phải lỗi.
- **ChatGPT OAuth báo chưa cài Codex CLI**: kênh này cần Codex CLI trên máy. Từ 0.28.8 cả ba engine CLI (Claude Code, Codex, Gemini CLI) đều được cài sẵn lúc cài Javis - bản Docker, `install.sh` lẫn `setup.bat` - nên báo thiếu thường là bản cài cũ, **cập nhật Javis** một lần là có. Cài tay cũng được: `npm i -g @openai/codex`.

## Liên quan

- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - đấu nguồn dữ liệu và công cụ cho mọi engine dùng chung.
- [Mức dùng: token & chi phí](23-muc-dung-token.md) - xem model nào, việc nào đang đốt nhiều nhất.
- [Agents & Workflows](07-agents-va-workflows.md) - chọn model riêng cho từng agent.
- [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) - cài Claude Code CLI và Codex CLI.

Nếu vẫn kẹt, xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
