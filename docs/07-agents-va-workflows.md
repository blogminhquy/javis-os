# Agents & Workflows

***Tiếng Việt** · [English](en/07-agents-and-workflows.md)*

Đây là nơi bạn tạo ra các trợ lý AI chuyên biệt (Agent) và ghép chúng thành dây chuyền làm việc tự động (Workflow). Ví dụ: một agent chuyên nghiên cứu, một agent chuyên viết bài, một agent chuyên kiểm tra lại, nối thành chuỗi "nghiên cứu > viết > kiểm chứng" chạy một phát ra kết quả.

## Tính năng này là gì

- **Agent** là một "nhân viên AI" có vai trò cố định. Mỗi agent gồm: một cái tên, một mô tả vai trò, một hướng dẫn làm việc chi tiết (system prompt), danh sách kỹ năng (skill) được phép dùng, một **model chạy**, và một **bộ nhớ riêng** tích luỹ theo thời gian. Model chọn được từ **mọi nhà cung cấp bạn đã kết nối** ở trang Models: Claude (Claude Code), ChatGPT (Codex), Grok Build CLI, Antigravity CLI, OpenRouter, Anthropic API, OpenAI, Google Gemini, Groq. Danh sách trong ô chọn lấy thẳng từ các nhà đã kết nối, nên kết nối thêm là có thêm lựa chọn. Nhà nào cũng đọc/ghi được file trong vault và dùng được MCP; riêng Claude Code và Codex có thêm lệnh máy cùng khả năng tự mở web. Nhà đã chọn trục trặc lúc chạy thì Javis tự lùi sang bộ não khác thay vì để agent chết lặng. (Ollama chưa chạy được agent nên không xuất hiện ở đây.) Model của agent được áp THẬT khi workflow chạy.
  - Lưu ý an toàn: khi workflow chạy **nền tự động** (dispatcher Kanban, chế độ giới hạn công cụ file), agent luôn dùng Claude Code để giữ giới hạn công cụ an toàn - kể cả khi bạn chọn nhà khác. Model bạn chọn chỉ áp khi bạn gửi tin ở trang **Cộng sự**.
- **Workflow** là một chuỗi nhiều bước, mỗi bước giao cho một agent làm một nhiệm vụ. Kết quả bước trước có thể chảy sang bước sau. Bạn có thể gắn thêm một **bước kiểm chứng**: một agent khác đóng vai người soi lỗi, mặc định giả định kết quả đang sai và phải tự chứng minh; nếu chưa đạt, workflow tự sửa lại vài lần.
- Mọi agent và workflow được lưu thành **file .md trong vault** (bộ não đang chọn), nên bạn xem được, sửa tay được, và Javis cũng tạo được bằng lời qua chat.

Liên quan: chọn model cho agent xem [Models & engine](10-models-va-engine.md); tạo và bật/tắt skill để gán cho agent xem [Skills](06-skills.md).

## Mở ở đâu trong Javis

Mở **Năng lực > Cộng sự** trên thanh bên của dashboard (mặc định tại cổng 7777). Trang có hai tab **Trợ lý | Quy trình**. Skills và Plugins vẫn nằm trong nhóm Năng lực.

- Cột trái: chọn tab, tìm theo tên hoặc lọc nhóm, rồi chọn cộng sự. Trợ lý vừa trò chuyện và quy trình vừa chạy được xếp lên đầu.
- Cột giữa: khung chat của cộng sự đang chọn.
- Cột phải: cài đặt và hội thoại của trợ lý, hoặc tiến độ và lịch sử chạy của quy trình.

Trên màn hình hẹp, dùng nút mở danh sách hoặc cột chi tiết để xem ngăn kéo. Đổi brain sẽ đổi danh sách và hội thoại tương ứng.

## Trò chuyện với một trợ lý

1. Chọn tab **Trợ lý**, rồi chọn một trợ lý ở cột trái.
2. Gửi tin ở giữa trang. Trợ lý trả lời theo vai trò, hướng dẫn và bộ nhớ riêng đã cấu hình.
3. Sửa tên, vai trò, hướng dẫn, skills hoặc model ở cột phải rồi bấm **Lưu**.
4. Bấm nút tạo hội thoại mới để bắt đầu một cuộc trò chuyện riêng với cùng trợ lý. Mỗi trợ lý có nhiều hội thoại; mở lại hội thoại gần đây ở cột phải để tiếp tục.

Hội thoại cộng sự tách khỏi lịch sử chat chính của Javis. Quay lại một cộng sự sẽ mở tiếp phiên gần nhất của cộng sự đó.

## Tạo mới, tìm kiếm và Javis Store

Chọn tab cần dùng rồi bấm nút tạo trợ lý hoặc quy trình ở cuối cột trái. **Javis Store** mở kho gói tương ứng để thêm cộng sự có sẵn. Muốn xếp nhóm, điền trường **Nhóm** trong trình sửa.

Ô tìm lọc theo tên, slug, vai trò hoặc mô tả, hỗ trợ gõ không dấu. Bộ lọc nhóm kết hợp với ô tìm. Mục chưa có nhóm thuộc **Chung**; mục chưa dùng nằm sau các mục đã dùng và được xếp theo tên.

## Tạo một Agent (từng bước, qua form)

1. Mở **Cộng sự > Trợ lý**.
2. Bấm nút tạo trợ lý ở cuối cột trái. Một khung soạn thảo mở ra bên phải màn hình.
3. Điền các ô sau:

| Ô | Ý nghĩa | Gợi ý điền |
|---|---|---|
| **Tên** | Tên agent, hiện trên thẻ. Bắt buộc. | VD: "Chuyên viên email" |
| **Vai trò (mô tả ngắn)** | Một câu mô tả agent làm gì. | VD: "Viết email bán hàng, giọng thân mật" |
| **Nhóm** | Tên nhóm để dashboard xếp agent vào cùng một cột bên trái. Gõ tên mới hoặc chọn từ nhóm đang có (ô có gợi ý). Để trống thì agent rơi vào nhóm "Chung". | VD: Marketing, Bán hàng, Nội dung |
| **System prompt (cách làm việc chi tiết)** | Hướng dẫn dài, chi tiết cách agent làm việc, nguyên tắc, đầu ra mong muốn. | VD: quy tắc viết, cấm dùng từ nào, format đầu ra |
| **Skills** | Danh sách skill có sẵn trong vault, bấm tick để cho agent được dùng. | Chọn skill hợp với vai trò |
| **Model** | Ô chọn có 8 lựa chọn, xem bảng ngay dưới. | Sonnet cho cân bằng, Opus khi cần suy luận sâu, Haiku khi cần nhanh và rẻ |

4. Bấm **Lưu**. Nếu bạn quên nhập Tên, Javis sẽ nhắc "Nhập tên".
5. Thẻ agent mới hiện trong danh sách, có biểu tượng 🤖, kèm tên model và các nhãn skill đã gán. Nếu chưa gán skill nào, thẻ ghi "chưa gán skill".

Ghi chú về ô Skills: danh sách skill lấy từ thư mục skill của vault. Nếu vault chưa có skill nào, khung sẽ báo "Vault chưa có skill trong skills/ - vẫn tạo agent được, gán skill sau." Bạn vẫn tạo agent bình thường và quay lại gán sau. Cách tạo skill xem trang [Skills](06-skills.md).

### Ô Model có gì

| Lựa chọn | Thuộc nhóm | Chạy bằng |
|---|---|---|
| **Mặc định (theo CLI)** | (không nhóm) | Xem giải thích ngay dưới bảng |
| **Sonnet** | Claude (Claude Code) | Claude Code |
| **Opus** | Claude (Claude Code) | Claude Code |
| **Haiku** | Claude (Claude Code) | Claude Code |
| **Fable** | Claude (Claude Code) | Claude Code |
| **GPT-5.5** | ChatGPT (Codex - cần đăng nhập ChatGPT) | Codex CLI |
| **GPT-5.4** | ChatGPT (Codex - cần đăng nhập ChatGPT) | Codex CLI |
| **GPT-5.3 Codex** | ChatGPT (Codex - cần đăng nhập ChatGPT) | Codex CLI |

Dưới ô Model có dòng ghi chú: "Agent chạy qua CLI của nhà cung cấp: chọn Claude → Claude Code; chọn ChatGPT → Codex (cần đã đăng nhập ChatGPT ở máy/VPS). Cả hai đều đọc/ghi file vault + dùng MCP."

**"Mặc định (theo CLI)" thật ra làm gì:** để trống thì Javis lấy **model phụ** bạn đặt ở trang **Models** trước (chỉ khi model phụ là một model Claude); không có model phụ Claude nào thì mới rơi về model mặc định của CLI. Nếu bạn muốn một agent luôn chạy đúng một model bất kể cấu hình chung, hãy chọn thẳng model cho nó thay vì để trống.

### Bộ nhớ riêng và nhật ký chạy của agent

Ngoài file `.md`, mỗi agent còn có hai thứ nằm trong thư mục `memory/agents/<slug>/` của brain:

- **`MEMORY.md` - bộ nhớ riêng.** Mỗi lần agent chạy, Javis đọc file này và chèn thẳng vào system prompt của agent dưới tiêu đề `# Bộ nhớ của bạn:`. Đây là chỗ để tích luỹ những gì agent cần nhớ lâu dài: quy ước riêng, danh sách khách, những lỗi đã bị nhắc. File này có **hai nguồn ghi**: bạn viết tay, và chính agent **tự bồi đắp lúc chạy** - cuối một nhiệm vụ, nếu rút ra được bài học tái dùng, agent đề xuất và Javis ghi hộ vào mục `## Bài học (tự học)` của file. Javis (chứ không phải model) cầm bút nên có rào cứng: tự loại bài học trùng, chỉ giữ 15 dòng mới nhất để bộ nhớ đặc dần thay vì dài dần, và phần bạn viết tay ngoài mục đó không bao giờ bị chạm. Nghĩa là agent thông minh dần lên theo mỗi lần dùng, không có job nền nào quét hàng loạt.
- **`runs/` - nhật ký chạy.** Mỗi bước workflow chạy xong (kể cả bước kiểm chứng), Javis ghi thêm một mục vào `runs/<YYYY-MM-DD>.md` gồm giờ chạy, nhiệm vụ đã giao, và kết quả (cắt gọn). Đây là chỗ để soi lại "hôm qua agent này đã làm gì" mà không cần mở lại bảng theo dõi. Nhật ký thô này không đi vào git của brain.

Cả hai đều là file văn bản thường: mở, đọc và sửa tay được qua [Quản lý tệp tin](05-quan-ly-tep-tin.md). Muốn dạy một agent nhớ điều gì, cứ viết thẳng vào `memory/agents/<slug>/MEMORY.md` là lần chạy sau nó đã biết.

Phân biệt: bộ nhớ này là của **riêng một agent**; bộ nhớ chung của Javis về bạn và doanh nghiệp nằm ở `memory/MEMORY.md` và `memory/facts/`, xem [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

### Sửa hoặc xoá agent

- **Sửa**: trên thẻ agent, bấm **Sửa**, chỉnh rồi bấm **Lưu**.
- **⤓ Xuất**: đóng gói agent (kèm skill của nó) thành file `.zip` để chia sẻ, xem mục "Chia sẻ" cuối trang.
- **Xoá**: bấm **Xoá**, xác nhận ở hộp thoại "Xoá agent ...?". Lưu ý: nếu một workflow đang dùng agent này thì bước đó sẽ trỏ tới agent không còn tồn tại, nên xoá xong hãy kiểm tra lại các workflow liên quan. Xoá agent **không** xoá thư mục `memory/agents/<slug>/`, nên bộ nhớ và nhật ký cũ vẫn còn trên đĩa.

## Tạo một Workflow (từng bước, qua form)

Tạo ít nhất một trợ lý ở tab **Trợ lý** trước khi tạo quy trình.

1. Mở **Cộng sự > Quy trình**.
2. Bấm **+ Workflow** ở góc trên bên phải.
3. Điền:
   - **Tên**: tên workflow. Bắt buộc.
   - **Mô tả**: một dòng nói workflow này làm gì (không bắt buộc nhưng nên có; dòng này hiện trên thẻ workflow).
   - **Nhóm**: tên nhóm để xếp workflow vào cột nhóm bên trái, gõ tên mới hoặc chọn từ nhóm đang có. Để trống thì nó nằm ở nhóm "Chung".
4. Ở phần **Các bước (mỗi bước = 1 agent · dùng {{input}} và {{prev}})**, mỗi bước là một khối gồm:
   - Ô **Nhiệm vụ** (task): mô tả bước này phải làm gì. Trong nhiệm vụ, bạn dùng được hai biến đặc biệt:
     - `{{input}}` = đầu vào bạn gõ khi bấm chạy workflow.
     - `{{prev}}` = kết quả của bước ngay trước đó.
   - Phần **Kiểm chứng** (không bắt buộc): chọn một agent đóng vai người soi lỗi cho bước này, và số lần cho phép sửa lại. Để mặc định "- không kiểm chứng -" nếu không cần. Số lần sửa mặc định là 1, cho phép từ 0 đến 5.
5. Bấm **+ Bước** để thêm bước mới.
6. Bấm **Lưu**. Nếu quên nhập Tên, Javis nhắc "Nhập tên". Workflow mới lưu ở trạng thái sẵn sàng (active).

### Hàng tiêu đề của một bước

Mỗi bước có một hàng tiêu đề, đọc từ trái sang phải:

| Phần tử | Ý nghĩa |
|---|---|
| Số thứ tự | 1, 2, 3... theo đúng thứ tự chạy |
| Dòng tóm tắt | "tên agent · nhiệm vụ" rút gọn trên một dòng |
| Ô chọn agent | Đổi agent phụ trách bước này |
| **↑** | Đẩy bước lên trên một nấc (mờ ở bước đầu) |
| **↓** | Đẩy bước xuống dưới một nấc (mờ ở bước cuối) |
| **✕** | Xoá bước này (nằm ở CUỐI hàng tiêu đề) |

**Gập và mở bước:** bấm vào hàng tiêu đề (chỗ trống, không phải nút hay ô chọn) để gập hoặc mở phần thân của bước đó. Khi bạn mở một workflow đã có để **sửa**, tất cả các bước mặc định gập hết lại để bạn thấy toàn cảnh dây chuyền trước; bấm vào bước nào thì bước đó mở ra cho sửa. Workflow **mới tạo** chỉ có một bước nên mở sẵn.

Chữ đang gõ dở không bị mất khi bạn gập/mở, đổi thứ tự hay xoá bước khác - Javis lưu tạm nội dung mọi bước trước mỗi lần vẽ lại.

### Ví dụ một workflow 2 bước

- Bước 1: agent **Researcher**, nhiệm vụ: `Nghiên cứu kỹ chủ đề: {{input}}. Tìm nguồn, tổng hợp insight chính.`
- Bước 2: agent **Writer**, nhiệm vụ: `Viết một bài hoàn chỉnh về '{{input}}' dựa trên nghiên cứu sau:` rồi xuống dòng và thêm `{{prev}}`. Ở phần Kiểm chứng, chọn agent **Kiểm chứng viên**, số lần sửa 2.


### Sửa, xuất hoặc xoá quy trình

Chọn quy trình ở cột trái. Cột phải có nút **Sửa**, **Xuất** và **Xoá**, cùng danh sách các bước. Nút Sửa mở trình sửa quy trình; lưu xong danh sách và chi tiết được cập nhật.

## Chạy quy trình

1. Mở **Cộng sự > Quy trình**, chọn một quy trình ở cột trái.
2. Gửi yêu cầu vào khung chat. Mỗi tin nhắn bắt đầu một lần chạy; nội dung tin là đầu vào `{{input}}`.
3. Theo dõi tiến độ từng bước ở cột phải. Nếu quy trình có kiểm chứng, bước đó có thể chạy lại theo phản hồi của người kiểm chứng và số lần thử đã cấu hình.
4. Nếu cần duyệt, đọc yêu cầu và dùng nút duyệt ở cột phải để tiếp tục. Lỗi và trạng thái chờ cũng được báo trong chat.
5. Khi hoàn tất, kết quả về khung chat. Tin tiếp theo trong cùng hội thoại nhớ kết quả lần trước, nên bạn có thể góp ý và chạy lại, ví dụ: "Giữ ý chính, viết ngắn hơn".

**Lịch sử chạy** ở cột phải liệt kê các lần chạy gần nhất. Bấm một lần chạy để xem chi tiết và mở lại hội thoại nếu lần chạy có phiên chat. Quy trình vừa chạy tự lên đầu danh sách. Bạn cũng có thể hỏi Javis ở khung chat chính: "Quy trình chạy gần nhất ra sao?" để tra lịch sử đã lưu, bao gồm lần chạy từ Cộng sự và Kanban.

Mỗi bước vẫn ghi nhật ký của trợ lý tại `memory/agents/<slug>/runs/`. Nếu mất kết nối, kiểm tra lịch sử chạy trước khi gửi lại để tránh chạy trùng.

## Tạo agent và workflow bằng lời (qua chat)

Bạn không bắt buộc phải dùng form. Trong khung trò chuyện với Javis (xem [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md)), bạn có thể ra lệnh bằng lời, ví dụ:

- "Tạo agent chuyên viết email bán hàng."
- "Tạo workflow nghiên cứu rồi viết bài."
- "Thêm bước biên tập vào workflow X."

Khi đó Javis tự ghi file .md tương ứng vào vault, tự đặt slug không dấu, tự xếp nhóm (đọc nhóm đang dùng trong brain rồi lấy nhóm sát nhất), tự gán skill hợp lý từ skill có sẵn, và nếu workflow nhắc tới một agent chưa tồn tại thì tạo agent đó trước. Sau khi làm xong, Javis báo ngắn gọn đã tạo/sửa file nào. Bạn quay lại trang Cộng sự là thấy ngay, không cần thao tác thêm.

Cách này tiện khi bạn mô tả được ý định bằng lời nhưng ngại điền form, hoặc muốn chỉnh nhiều bước cùng lúc.

## Agent và workflow được lưu ở đâu

Trong brain theo cấu trúc mới, mỗi agent là một file `agents/<slug>.md` và mỗi workflow là một file `workflows/<slug>.md`. `slug` là tên viết thường, có gạch ngang, không dấu (ví dụ "viết email" thành `viet-email`).

**Brain cũ chưa chuyển cấu trúc** thì hai thư mục đó nằm ở `Javis/agents/` và `Javis/workflows/`. Javis tự dò: có thư mục mới thì dùng thư mục mới, không có thì dùng đường cũ. Nên nếu bạn mở trang Tệp tin mà không thấy `agents/` ở gốc brain, hãy tìm trong `Javis/`.

Vì là file văn bản, bạn có thể mở qua [Quản lý tệp tin](05-quan-ly-tep-tin.md) để xem hoặc sửa tay. Cấu trúc file:

- Agent: phần đầu (frontmatter) chứa tên, vai trò, nhóm (`group`), danh sách skill, model; phần thân là system prompt chi tiết. Bộ nhớ riêng và nhật ký chạy nằm ngoài file này, ở `memory/agents/<slug>/`.
- Workflow: phần đầu chứa tên, trạng thái (active hoặc off), nhóm (`group`), mô tả và danh sách các bước (mỗi bước có agent, task, và tuỳ chọn agent kiểm chứng cùng số lần sửa).

Trường `group` dùng chung một cách viết cho cả agent, workflow và skill, nên sửa tay trong file cũng được: ghi `group: Marketing` là lần tải lại trang sẽ thấy nó nằm đúng nhóm. Thiếu trường này thì nó vào nhóm "Chung".

Sửa file rồi lưu thì trang Cộng sự tự nhận nội dung mới ở lần tải lại.

## Mẹo

- **Luôn tách một bước kiểm chứng cho khâu quan trọng.** Đặt agent kiểm chứng là một agent khác với agent làm, vì nó được ép đóng vai "giả định kết quả đang sai". Đây là cách giảm chuyện AI viết ẩu hoặc bịa.
- **Mỗi bước làm đúng một việc.** Đừng nhồi "nghiên cứu và viết và đăng" vào một bước. Chia nhỏ để dễ kiểm soát và dễ sửa từng khâu.
- **Dùng `{{prev}}` để nối mạch.** Bước sau muốn dùng kết quả bước trước thì phải nhắc `{{prev}}` trong nhiệm vụ, nếu không agent sẽ không thấy đầu ra bước trước.
- **Dựng thứ tự bằng ↑/↓ thay vì xoá đi làm lại.** Sắp nhầm thứ tự thì chỉ cần đẩy bước lên xuống, nội dung đi theo nguyên vẹn.
- **Đặt số lần sửa vừa phải.** 1 đến 2 lần thường đủ. Đặt quá cao khiến workflow chạy lâu và tốn khi kết quả khó đạt.
- **Chọn model theo việc.** Bước nặng suy luận (phân tích, kiểm chứng) dùng Opus; bước đơn giản, số lượng nhiều dùng Haiku cho nhanh và tiết kiệm. Chi tiết ở [Models & engine](10-models-va-engine.md).
- **Gán skill đúng chỗ.** Agent chỉ mạnh khi có skill phù hợp. Ví dụ agent viết sales page nên gán skill viết sales page. Quản lý skill ở [Skills](06-skills.md).
- **Dùng bộ nhớ riêng cho thứ lặp đi lặp lại.** Cùng một lời dặn phải nhắc lại mỗi lần chạy thì viết thẳng vào `memory/agents/<slug>/MEMORY.md`, khỏi nhồi hết vào system prompt.

## Chia sẻ: Xuất / Nhập (agent, skill, workflow)

Bạn có thể đóng gói một agent, skill hoặc workflow thành **một file `.zip`** để gửi cho người khác, và nhận file của người khác về brain của mình.

- **Xuất:** mỗi thẻ agent / skill / workflow có nút **⤓ Xuất**. Bấm là tải về một gói `.zip`. Gói này **tự kèm phụ thuộc** để bên nhận chạy được ngay: xuất một workflow sẽ kèm luôn các agent mà workflow đó dùng và các skill của những agent đó; xuất một agent sẽ kèm skill của agent. Skill **hệ thống** không được đóng gói vì brain nào cũng đã có sẵn.
- **An toàn:** khi nhập, Javis chặn các đường dẫn bất thường trong gói (không cho ghi ra ngoài các thư mục agent/skill/workflow) và giới hạn dung lượng để tránh file độc. Dù vậy, chỉ nên nhập gói từ nguồn bạn tin tưởng, vì nội dung skill là hướng dẫn cho AI làm theo.

Lưu ý: gói xuất chỉ chứa file định nghĩa. **Bộ nhớ riêng và nhật ký chạy của agent không đi theo gói** - bên nhận có được vai trò và kỹ năng, không có ký ức.

## Thao tác nhanh và khắc phục sự cố

- **Tạo mới:** chọn tab rồi bấm nút tạo ở cuối cột trái; hoặc mở **Javis Store**.
- **Hội thoại mới:** bắt đầu phiên riêng với cộng sự đang chọn.
- **Sửa / Xuất / Xoá:** nằm ở cột phải của cộng sự.
- **Danh sách trống:** kiểm tra brain đang chọn, ô tìm và bộ lọc nhóm, rồi tạo cộng sự nếu chưa có.
- **Không thấy cài đặt hay lịch sử:** mở cột chi tiết bằng nút ở đầu khung chat, nhất là trên màn hình hẹp.
- **Thiếu trợ lý trong quy trình:** tạo trợ lý đó trước rồi sửa bước để chọn đúng trợ lý.
- **Mất kết nối hoặc chạy lỗi:** đọc thông báo trong chat và lịch sử chạy trước khi gửi lại yêu cầu.
- **Trang tải mãi:** kiểm tra server ở cổng 7777, rồi xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

## Liên quan

- [Skills](06-skills.md) - tạo, bật/tắt và gán kỹ năng cho agent.
- [Plugins](20-plugins.md) - mục trong nhóm Năng lực, dành cho tool chạy code thật.
- [Models & engine](10-models-va-engine.md) - chọn model chính, model phụ và các nhà cung cấp.
- [Việc / Kanban](21-viec-kanban.md) - nơi workflow chạy nền tự động theo task.
- [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) - phân biệt bộ nhớ riêng của agent với bộ nhớ chung của Javis.
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - mở và sửa tay file agent, workflow, bộ nhớ.
