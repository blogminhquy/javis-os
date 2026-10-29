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

- Cột trái: chọn tab, tìm theo tên hoặc lọc theo tag (quy trình: theo nhóm), rồi chọn cộng sự. Trợ lý vừa trò chuyện và quy trình vừa chạy được xếp lên đầu.
- Cột giữa: khung chat của cộng sự đang chọn.
- Cột phải: cài đặt và hội thoại của trợ lý, hoặc tiến độ và lịch sử chạy của quy trình.

Trên màn hình hẹp, dùng nút mở danh sách hoặc cột chi tiết để xem ngăn kéo. Đổi brain sẽ đổi danh sách và hội thoại tương ứng.

## Trò chuyện với một trợ lý

1. Chọn tab **Trợ lý**, rồi chọn một trợ lý ở cột trái.
2. Gửi tin ở giữa trang. Trợ lý trả lời theo vai trò, hướng dẫn và bộ nhớ riêng đã cấu hình.
3. Sửa tên, vai trò, hướng dẫn, skills hoặc model ở cột phải rồi bấm **Lưu thay đổi** (hoặc Ctrl+S). Thanh lưu luôn nằm ở cuối form: còn thay đổi chưa lưu thì ghi "Có thay đổi chưa lưu" kèm chấm vàng, lưu xong ghi "Đã lưu".
4. Bấm nút tạo hội thoại mới để bắt đầu một cuộc trò chuyện riêng với cùng trợ lý. Mỗi trợ lý có nhiều hội thoại; mở lại hội thoại gần đây ở cột phải để tiếp tục.

Hội thoại cộng sự tách khỏi lịch sử chat chính của Javis. Quay lại một cộng sự sẽ mở tiếp phiên gần nhất của cộng sự đó.

**Model của Javis Core** (từ 0.402.0): Javis Core mặc định chạy theo model chính, đổi model chính là Core đổi theo. Chọn một model khác trên thanh model của bất kỳ chat Javis Core nào là ghim model đó cho **cả Javis Core**: mọi chat Core, kể cả báo cáo mới về, dùng model đó cho tới khi bạn đổi. Chọn **Theo model của khung chat chính** trong danh sách để gỡ ghim.

### Javis Core chỉ huy thông báo

Từ 0.403.0 Javis Core quyết định thông báo nào được báo (chấm đỏ trên chuông, đẩy lên điện thoại, Telegram của bạn).

- Mỗi thông báo thuộc một **nhóm** (Nhắc lịch, Câu hỏi chờ bạn, Chatbot và khách, Kết nối và đăng nhập, Sự cố, Kết quả việc, Trợ lý chủ động, Nhóm làm việc, Chi phí, Cập nhật, Khác) và có một **mức**: bình thường, đáng chú ý hoặc khẩn.
- **Mặc định chỉ tin khẩn mới báo**: nhắc lịch, câu hỏi đang chờ bạn, khách cần người thật, bot chatbot đang lỗi, Javis không dùng được, trang bạn theo dõi có thay đổi. Tin khác vẫn nằm trong chuông, ở ngăn **Đã lọc (N)** cuối danh sách. Việc bạn giao từ một khung chat thì kết quả vẫn về đúng khung chat đó.
- Tab **Bộ lọc** của chuông: mỗi nhóm chọn **Tất cả**, **Đáng chú ý trở lên**, **Chỉ tin khẩn** hoặc **Tắt**; xem loại tin có luật riêng; xem và **Hoàn tác** các thay đổi gần đây.
- Mỗi thông báo có hai nút **Nên báo** và **Không cần báo**. Muốn chấm bằng emoji thì bấm **Mở trong Javis Core**: thông báo thành một tin trong chat Javis Core, thả emoji của Cộng hưởng (👍 ❤️ 😂 😮 😢 😡) lên tin đó như mọi câu trả lời, kèm "Đáng lẽ nên nói" hoặc "Nên im" nếu muốn. Javis Core tự chỉnh theo phản hồi: bấm Không cần báo là loại tin đó bị lọc; bấm Nên báo lên một tin đã lọc là loại đó luôn được báo; một nhóm bị chê nhiều thì hạ một nấc. Mỗi lần chỉnh, Javis Core nói một câu trong chat của nó.
- Một loại tin báo tới lần thứ 3 trong 6 tiếng thì các lần sau trong 6 tiếng đó bị lọc là "lặp lại".
- Javis Core **không bao giờ tự giấu tin khẩn**. Chỉ bạn làm được, bằng chế độ Tắt hoặc nút Không cần báo.
- Nói trong chat Javis Core cũng được, ví dụ "tắt thông báo đăng nhập Zalo" hay "báo hết cho tôi": Javis Core dùng công cụ `javis_notify` và trả kèm mã để hoàn tác.

### Tin chưa đọc và tắt thông báo

Từ 0.205.0 danh sách cộng sự chạy như danh sách tin nhắn:

- Cộng sự vừa có tin mới (bạn nhắn, cộng sự trả lời, hay một việc nền báo kết quả vào hội thoại của cộng sự) **tự lên đầu** danh sách. Javis Core và các mục **Đã ghim** vẫn đứng trước.
- Thẻ cộng sự hiện **số tin chưa đọc** ở góc dưới, cạnh giờ nhắn. Mở hội thoại của cộng sự đó là số này tự xoá, ở mọi tab đang mở.
- Nút **⋮** của mỗi thẻ có **Tắt thông báo**, chọn **Trong 1 giờ**, **Trong 4 giờ**, **Cho đến 8:00 sáng** hoặc **Cho đến khi được mở lại**. Thẻ đang tắt có biểu tượng chuông gạch và số chưa đọc màu xám. Tin vẫn vào hội thoại và chuông thông báo, chỉ là không kêu và không gửi thông báo đẩy. Bấm **Bật thông báo** để mở lại.

## Tạo mới, tìm kiếm và Javis Store

Chọn tab cần dùng rồi bấm nút tạo trợ lý hoặc quy trình ở cuối cột trái. **Javis Store** mở kho gói tương ứng để thêm cộng sự có sẵn. Trợ lý được phân loại bằng **tag**, quy trình bằng **nhóm** (xem dưới).

Ô tìm lọc theo tên, slug, vai trò, mô tả và tên tag, hỗ trợ gõ không dấu. Bộ lọc tag (ở tab Quy trình là bộ lọc nhóm) kết hợp với ô tìm. Mục chưa dùng nằm sau các mục đã dùng và được xếp theo tên.

## Tạo một Agent (từng bước, qua form)

1. Mở **Cộng sự > Trợ lý**.
2. Bấm nút tạo trợ lý ở cuối cột trái. Một khung soạn thảo mở ra bên phải màn hình.
3. Điền các ô sau:

| Ô | Ý nghĩa | Gợi ý điền |
|---|---|---|
| **Tên** | Tên agent, hiện trên thẻ. Bắt buộc. | VD: "Chuyên viên email" |
| **Vai trò (mô tả ngắn)** | Một câu mô tả agent làm gì. | VD: "Viết email bán hàng, giọng thân mật" |
| **Tài liệu & link** | Nút mở khung gắn file trong brain và đường link cho riêng trợ lý này. Xem mục ngay dưới. | Bảng giá, brief thương hiệu, link tài liệu sản phẩm |
| **System prompt (cách làm việc chi tiết)** | Hướng dẫn dài, chi tiết cách agent làm việc, nguyên tắc, đầu ra mong muốn. | VD: quy tắc viết, cấm dùng từ nào, format đầu ra |
| **Skills** | Danh sách skill có sẵn trong vault, bấm tick để cho agent được dùng. | Chọn skill hợp với vai trò |
| **Model** | Ô chọn có 8 lựa chọn, xem bảng ngay dưới. | Sonnet cho cân bằng, Opus khi cần suy luận sâu, Haiku khi cần nhanh và rẻ |

4. Bấm **Tạo agent** (agent đã có thì nút ghi **Lưu thay đổi**). Nếu bạn quên nhập Tên, Javis sẽ nhắc "Nhập tên".
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

### Tài liệu và link của một trợ lý

Mỗi trợ lý có một tủ tài liệu riêng: mở **Cài đặt trợ lý** ở cột phải rồi bấm **Mở khung tài liệu & link**. Khung mở ra đúng là khung bạn đã dùng cho project và cho một cuộc trò chuyện, chỉ khác phạm vi.

- **Tab File**: tìm một file có sẵn trong brain để gắn vào, hoặc tải file từ máy lên (file tải lên nằm ở thư mục `sources` của brain). Kéo thả file vào khung cũng được.
- **Tab Link**: dán một địa chỉ `http://` hoặc `https://` kèm tên gợi nhớ.
- **Nút ghim** trên mỗi file: ghim là Javis **nạp sẵn nội dung file** vào đầu mỗi lượt trợ lý làm việc (tối đa 2000 ký tự mỗi file, 6000 ký tự tổng), thay vì chỉ cho nó biết tên file rồi tự mở khi cần. Ghim bảng giá vào là trợ lý trả lời được ngay mà không phải đi đọc.
- **Nút X** gỡ khỏi trợ lý nhưng **không** xoá file trong brain. Muốn xoá hẳn thì dùng nút thùng rác bên cạnh.

Phạm vi: danh sách này thuộc về **trợ lý**, nên mọi cuộc trò chuyện với nó và mọi bước quy trình gọi tới nó đều thấy. Muốn gắn tài liệu cho riêng một cuộc trò chuyện thì dùng nút **File & link** ở thanh trên khung chat. Chỗ lưu là chính file `.md` của trợ lý (khoá `assets` trong frontmatter), nên xuất trợ lý ra hay copy brain sang máy khác thì danh sách đi theo.

Trợ lý mới chưa bấm Lưu lần nào thì nút này còn mờ: phải có trợ lý trước rồi mới gắn tài liệu vào được.

### Tag của một trợ lý

Từ bản 0.100.0 mỗi trợ lý gắn được **nhiều tag** (ví dụ Marketing, Viết nội dung, Kỹ thuật); nhóm cũ của trợ lý tự thành một tag. Tag chỉ để phân loại và tìm trợ lý:

- **Gắn tag, bỏ tag:** nút **...** trên từng trợ lý, mục **Gắn tag**. Bấm một tag để gắn hay bỏ đúng tag đó; ô **Tag mới** tạo và gắn tag mới. Các tag khác giữ nguyên.
- **Lọc:** thanh phía trên danh sách chọn **Tất cả agent**, **Chưa gắn tag** hay một tag. Trợ lý có nhiều tag hiện ở mọi tag của nó nhưng chỉ một lần trong danh sách.
- **Đổi tên, xoá tag:** nút **...** cạnh tên tag trong thanh lọc. Đổi tên áp cho mọi trợ lý mang tag đó; đổi sang tên đã có thì hai tag gộp làm một. Xoá tag chỉ gỡ nhãn, không xoá trợ lý, cuộc trò chuyện hay mục tiêu.
- Tag không nằm trong form cài đặt: bấm Lưu trong form không đổi tag.

Tag **khác** nhóm chat: gắn tag không thêm trợ lý vào cuộc trò chuyện nhóm nào. Tag cũng không chọn người review, không cấp quyền, không bật Cộng hưởng. Quy trình vẫn xếp theo **nhóm** như trước.

### Bộ nhớ riêng và nhật ký chạy của agent

Ngoài file `.md`, mỗi agent còn có hai thứ nằm trong thư mục `memory/agents/<slug>/` của brain:

- **`MEMORY.md` - bộ nhớ riêng.** Mỗi lần agent chạy, Javis đọc file này và chèn thẳng vào system prompt của agent dưới tiêu đề `# Bộ nhớ của bạn:`. Đây là chỗ để tích luỹ những gì agent cần nhớ lâu dài: quy ước riêng, danh sách khách, những lỗi đã bị nhắc. File này có **hai nguồn ghi**: bạn viết tay, và chính agent **tự bồi đắp lúc chạy** - cuối một nhiệm vụ, nếu rút ra được bài học tái dùng, agent đề xuất và Javis ghi hộ vào mục `## Bài học (tự học)` của file. Javis (chứ không phải model) cầm bút nên có rào cứng: tự loại bài học trùng, chỉ giữ 15 dòng mới nhất để bộ nhớ đặc dần thay vì dài dần, và phần bạn viết tay ngoài mục đó không bao giờ bị chạm. Nghĩa là agent thông minh dần lên theo mỗi lần dùng, không có job nền nào quét hàng loạt. Từ 0.105.0, luật bạn **dặn thẳng** agent trong chat (ví dụ "nhắn Zalo thì không dùng markdown") vào một mục riêng `## Luật chủ dặn`: không có trần, không bao giờ bị đẩy ra như bài học. Tự học cũng không còn viết lại cả thân agent, chỉ được thêm luật vào mục `## Bổ sung (tự học)` cuối thân, và mọi lần ghi phải giữ nguyên từng dòng bạn đã viết, thiếu một dòng là Javis không ghi.
- **`runs/` - nhật ký chạy.** Mỗi bước workflow chạy xong (kể cả bước kiểm chứng), Javis ghi thêm một mục vào `runs/<YYYY-MM-DD>.md` gồm giờ chạy, nhiệm vụ đã giao, và kết quả (cắt gọn). Đây là chỗ để soi lại "hôm qua agent này đã làm gì" mà không cần mở lại bảng theo dõi. Nhật ký thô này không đi vào git của brain.

Cả hai đều là file văn bản thường: mở, đọc và sửa tay được qua [Quản lý tệp tin](05-quan-ly-tep-tin.md). Muốn dạy một agent nhớ điều gì, cứ viết thẳng vào `memory/agents/<slug>/MEMORY.md` là lần chạy sau nó đã biết.

Phân biệt: bộ nhớ này là của **riêng một agent**; bộ nhớ chung của Javis về bạn và doanh nghiệp nằm ở `memory/MEMORY.md` và `memory/facts/`, xem [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

### Sửa hoặc xoá agent

- **Sửa**: chọn trợ lý, chỉnh ở cột phải rồi bấm **Lưu**.
- **⤓ Xuất**: đóng gói agent (kèm skill của nó) thành file `.zip` để chia sẻ, xem mục "Chia sẻ" cuối trang.
- **Xoá**: bấm **Xoá**, xác nhận ở hộp thoại "Xoá agent ...?". Lưu ý: nếu một workflow đang dùng agent này thì bước đó sẽ trỏ tới agent không còn tồn tại, nên xoá xong hãy kiểm tra lại các workflow liên quan. Xoá agent **không** xoá thư mục `memory/agents/<slug>/`, nên bộ nhớ và nhật ký cũ vẫn còn trên đĩa.

## Tạo một Workflow (từng bước, qua form)

Tạo ít nhất một trợ lý ở tab **Trợ lý** trước khi tạo quy trình.

1. Mở **Cộng sự > Quy trình**.
2. Bấm **Tạo quy trình** ở cuối cột trái.
3. Điền:
   - **Tên**: tên workflow. Bắt buộc.
   - **Mô tả**: một dòng nói workflow này làm gì (không bắt buộc nhưng nên có; dòng này hiện trên thẻ workflow).
   - **Nhóm**: tên nhóm để xếp workflow vào cột nhóm bên trái, gõ tên mới hoặc chọn từ nhóm đang có. Để trống thì nó nằm ở nhóm "Chung".
4. Ở phần **Các bước (mỗi bước = 1 agent · dùng {{input}} và {{prev}})**, mỗi bước là một khối gồm:
   - Ô **Nhiệm vụ** (task): mô tả bước này phải làm gì. Trong nhiệm vụ, bạn dùng được hai biến đặc biệt:
     - `{{input}}` = nội dung tin nhắn bạn gửi để chạy quy trình.
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

Khi đó Javis tự ghi file .md tương ứng vào vault, tự đặt slug không dấu, tự gắn tag cho agent hay xếp nhóm cho workflow (đọc tag và nhóm đang dùng trong brain rồi lấy cái sát nhất), tự gán skill hợp lý từ skill có sẵn, và nếu workflow nhắc tới một agent chưa tồn tại thì tạo agent đó trước. Sau khi làm xong, Javis báo ngắn gọn đã tạo/sửa file nào. Bạn quay lại trang Cộng sự là thấy ngay, không cần thao tác thêm.

Cách này tiện khi bạn mô tả được ý định bằng lời nhưng ngại điền form, hoặc muốn chỉnh nhiều bước cùng lúc.

## Agent và workflow được lưu ở đâu

Trong brain theo cấu trúc mới, mỗi agent là một file `agents/<slug>.md` và mỗi workflow là một file `workflows/<slug>.md`. `slug` là tên viết thường, có gạch ngang, không dấu (ví dụ "viết email" thành `viet-email`).

**Brain cũ chưa chuyển cấu trúc** thì hai thư mục đó nằm ở `Javis/agents/` và `Javis/workflows/`. Javis tự dò: có thư mục mới thì dùng thư mục mới, không có thì dùng đường cũ. Nên nếu bạn mở trang Tệp tin mà không thấy `agents/` ở gốc brain, hãy tìm trong `Javis/`.

Vì là file văn bản, bạn có thể mở qua [Quản lý tệp tin](05-quan-ly-tep-tin.md) để xem hoặc sửa tay. Cấu trúc file:

- Agent: phần đầu (frontmatter) chứa tên, vai trò, tag (`tags`, một danh sách), danh sách skill, model, và tài liệu đã gắn (`assets` gồm `files` và `links`); phần thân là system prompt chi tiết. Bộ nhớ riêng và nhật ký chạy nằm ngoài file này, ở `memory/agents/<slug>/`.
- Workflow: phần đầu chứa tên, trạng thái (active hoặc off), nhóm (`group`), mô tả và danh sách các bước (mỗi bước có agent, task, và tuỳ chọn agent kiểm chứng cùng số lần sửa).
  - Viết tay thì để `status: 'off'` CÓ dấu nháy: `off` trần bị YAML đọc thành giá trị đúng/sai. Từ 0.107.0 Javis hiểu được cả hai cách viết, nhưng giữ nháy cho chắc. Quy trình tắt không chạy nền từ Kanban hay nhắc hẹn; bấm Chạy ở Cộng sự thì vẫn chạy để bạn thử trước khi bật.
  - Một bước có thể khai `tools: [javis_generate_image, javis_describe_image]` để lấy đúng tool đó khi quy trình chạy nền dưới Toàn quyền (bình thường lúc đó agent chỉ có công cụ file). Nhận tên tool plugin và `WebFetch`, `WebSearch`; Bash không bao giờ được cấp theo cách này. Mức quyền riêng của tool vẫn được kiểm khi gọi, nên một bước không tự nâng mức được.

Sửa tay trong file cũng được. Agent: ghi `tags: [Marketing, Viết nội dung]`; có trường `tags` (kể cả `tags: []`) thì Javis chỉ đọc nó. File agent cũ chỉ có `group: Marketing` vẫn đọc thành một tag Marketing; lần lưu đầu Javis ghi thêm `tags` và giữ `group` bằng tag đầu tiên để bản cũ hơn vẫn đọc được. Workflow và skill dùng `group`; thiếu trường này thì vào nhóm "Chung".

Sửa file rồi lưu thì trang Cộng sự tự nhận nội dung mới ở lần tải lại.

## Mẹo

- **Luôn tách một bước kiểm chứng cho khâu quan trọng.** Đặt agent kiểm chứng là một agent khác với agent làm, vì nó được ép đóng vai "giả định kết quả đang sai". Đây là cách giảm chuyện AI viết ẩu hoặc bịa.
- **Agent kiểm chứng phải trả JSON** `{"pass": true|false, "reason": "...", "fixes": "..."}`. Từ 0.107.0 kiểm chứng là đóng-khi-lỗi: agent kiểm chứng lỗi, trả lời không đọc được, hay hết số lần sửa mà vẫn trượt đều tính là CHƯA ĐẠT, và quy trình dừng ở bước đó thay vì chạy tiếp như trước.
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

## Chia sẻ cả một Team

Ở trang Team, menu **⋯** của một team có **Chia sẻ team**: tải về một file `.team.javis.zip` gồm các cộng sự của team, kỹ năng của họ, trưởng nhóm và các tin đã ghim (thành hướng dẫn chung). File **không** có lịch sử chat, khoá, mật khẩu, model hay công tắc Auto; chữ trông giống khoá API, mã bot hay dòng `password: ...` bị thay bằng `[REDACTED]` trước khi ghi.

Người nhận bấm **Nhập team** ở đầu danh sách team, chọn file, xem trước có những cộng sự nào và bao nhiêu kỹ năng rồi xác nhận. Cộng sự trùng tên đã có trong brain thì giữ nguyên bản của người nhận; model và Auto người nhận tự chọn sau. File này vẫn mở được bằng nút Nhập ở trang Cộng sự của bản Javis cũ (khi đó chỉ nhập cộng sự, không dựng team).

Mỗi lượt chat tạo, sửa hay gỡ lịch, việc lặp, cộng sự, quy trình hay kỹ năng còn để lại một dòng nhỏ dưới câu trả lời ("Đã tạo lịch: ..."). Cái mới tạo có nút **Hoàn tác**: huỷ lịch, xoá việc lặp, cộng sự, quy trình hay kỹ năng vừa tạo.

## Team chờ bạn duyệt (từ 0.207.0)

Trong việc giao cho Team, một cộng sự cần bạn quyết (chọn phương án, chi tiền, gửi tin hay đăng bài ra ngoài) thì bước đó **dừng thật**: việc chuyển sang **Chờ bạn duyệt**, nhả chỗ cho việc khác của nhóm, và trong khung chat hiện một **thẻ Xin duyệt** ghi rõ sẽ làm gì, phạm vi, ảnh hưởng, bằng chứng và đúng các lời gọi sẽ chạy. Trước đây câu "@Chủ nhóm anh duyệt nhé?" vẫn bị coi là kết quả và việc tự chốt xong.

- **Duyệt**: cộng sự làm tiếp ở một bước mới, và chỉ đúng lời gọi đã duyệt được chạy, mỗi lời gọi một lần. Máy khởi động lại hay chạy lại bước cũng không làm lại hành động đã chạy.
- **Yêu cầu sửa**: ghi điều muốn đổi, cộng sự đưa phương án mới (thành một thẻ mới).
- **Từ chối**: ghi lý do, việc dừng ở đó; bạn sửa yêu cầu để giao hướng khác hoặc huỷ việc.
- **Thu hồi duyệt**: rút lại một duyệt chưa dùng tới.

Sửa yêu cầu của việc hay huỷ việc làm thẻ cũ hết hiệu lực. Chữ trong chat (của bạn hay của cộng sự) không bao giờ thay cho nút Duyệt. Mỗi lần bấm có mã riêng, nên mạng chập chờn bấm lại không làm hai lần, và mở hai tab thì tab sau được báo là đã quyết.

**Quyền của nhóm** (tab Nhóm, mục **Hành động ra ngoài của nhóm**):
- **Cần chủ duyệt** (mặc định, cả nhóm cũ): cộng sự tự đọc, tìm, ghi file trong bộ não và thư mục của nhóm, chạy lệnh chỉ đọc. Gửi, đăng, thanh toán, đặt hàng, xoá dữ liệu hay lệnh máy khác bị chặn TRƯỚC khi chạy và thành thẻ xin duyệt.
- **Nhóm tự làm, không hỏi**: quyền như khi bạn chat riêng với từng cộng sự (cách Team chạy ở 0.194.0 tới 0.206.0).

Ở chế độ Cần chủ duyệt, Claude Code, Codex (có sandbox riêng) và các bộ não dùng API key chặn được hành động trước khi chạy. Grok Build chỉ làm phần trong phạm vi (hành động đã duyệt không chạy được trên Grok). Antigravity không chặn được công cụ của chính nó nên bước đó bị từ chối kèm lời giải thích: đổi trợ lý sang bộ não khác hoặc bật "Nhóm tự làm".

## Mục tiêu phòng ban của Team (từ 0.208.0)

Ở tab Nhóm có mục **Mục tiêu phòng ban**. Nhóm cũ không có mục tiêu nên không có gì tự chạy cho tới khi bạn đặt và bấm **Bật**.

- **Mục tiêu**: nhóm này để làm gì. **Cách đo**: mỗi dòng một tiêu chí.
- **Nguồn được giao**, mỗi dòng một nguồn: `folder:bao-cao` (thư mục trong bộ não), `kanban` (việc Kanban lỗi của bộ não), `mcp:<mã kết nối>` (kết nối có đang lỗi không), `test:<lệnh kiểm tra>` (lệnh chạy ở mức Ghi nháp của trang Coding nên chạy được mã như `pytest` hay `npm test`, chỉ bạn đặt được; mã thoát khác 0 hay chạy quá 2 phút là lỗi).
- **Phạm vi**, **chu kỳ quan sát**, **số lần quan sát mỗi ngày**, **số việc tự mở mỗi ngày**, và **dừng mở việc khi đang có N việc**.
- Với mỗi loại cơ hội (tài liệu thay đổi, việc Kanban lỗi, lệnh kiểm tra báo lỗi, kết nối lỗi) chọn: **Chỉ ghi nhận**, **Đề xuất cho tôi**, **Mở việc, chờ tôi duyệt** hay **Tự mở việc**.

Javis đọc các nguồn bằng mã, không gọi model. Nguồn đọc không được thì hiện **thiếu nguồn** kèm lý do, không bịa ra vấn đề. Một thay đổi thành **cơ hội** có nguồn, phiên bản dữ liệu, lý do gắn mục tiêu và lợi ích. Cùng dữ liệu không mở lại lần hai, cơ hội bạn **Bỏ qua** chỉ quay lại khi dữ liệu đổi, mỗi nguồn có thời gian nghỉ, đề xuất để quá 48 giờ thì hết hạn. Hết số việc trong ngày hay chạm giới hạn việc đang mở thì chỉ đề xuất.

Việc do mục tiêu mở ghi dấu vết mục tiêu, bản, quan sát, cơ hội ngay trong yêu cầu, và mọi hành động ra ngoài của nó vẫn qua cổng duyệt. **Tạm dừng** ngừng quan sát; **Thu hồi** huỷ việc mục tiêu đã mở mà chưa chạy và đóng đề xuất đang mở. Mỗi lần sửa là một bản mới, có lịch sử.

## Nghiệm thu sản phẩm của Team (từ 0.209.0)

Ở tab Việc, việc đang chờ hay đang làm có nút **Nghiệm thu** để đặt tiêu chí, mỗi dòng một tiêu chí:

- `file: bao-cao/tuan.md`: file phải có.
- `contains: bai-viet/a.md | 300 | giá, liên hệ`: ít nhất 300 ký tự và có đủ các cụm chữ.
- `json: data.json | doanh_thu, don`: JSON hợp lệ, có đủ các khoá.
- `cmd: pytest -q`: lệnh kiểm tra phải trả mã 0 (chạy ở mức Ghi nháp của trang Coding).
- `confirm: bao-cao/tuan.md`: bạn tự xác nhận.

Khi cộng sự nộp kết quả, Javis kiểm chính sản phẩm (file) theo từng tiêu chí: **đạt**, **chưa đạt** hay **chưa rõ**, kèm bằng chứng (đường dẫn, mã băm sha256, kích thước, giờ sửa). Ý kiến của model không bao giờ là kết luận.

- Đạt hết: việc mới chốt **xong**.
- Có tiêu chí chưa đạt: cộng sự đó nhận một bước sửa ghi rõ chỗ chưa đạt. Quá số vòng sửa (mặc định 2) thì việc dừng ở **Chưa đạt tiêu chí**; bạn sửa yêu cầu để thử lại.
- Có tiêu chí chưa rõ hay cần bạn xác nhận: chat hiện thẻ **Nghiệm thu sản phẩm** với **Đạt, chốt việc** hoặc **Chưa đạt, trả lại** (kèm ghi chú). File đã đổi sau lần kiểm thì không chốt được, phải kiểm lại.

Sửa yêu cầu của việc làm bằng chứng cũ hết hiệu lực. Sau khi đã nghiệm thu, sửa file sản phẩm thì thẻ ghi "Sản phẩm đã đổi sau lần kiểm". Điểm học của cộng sự chỉ được cộng khi nghiệm thu đạt hay bạn xác nhận, mỗi việc một lần.

## Giao việc cho Team ngay từ chat (từ 0.357.0)

Bạn không cần mở trang Nhóm để giao việc. Cứ nói với Javis ở khung chat web, Telegram hay Zalo, ví dụ "giao cho Phòng nội dung viết 3 bài về nước mắm", Javis chọn đúng Team của brain đang mở và giao **một việc** vào Team đó. Việc chạy y như khi bạn tự giao ở trang Nhóm: trưởng nhóm điều phối, có hàng đợi, nghiệm thu và lịch sử của Team.

- **Kết quả tự báo về đúng khung chat đã giao**: khi việc xong, bị huỷ, bị chặn hay đang chờ bạn quyết. Mỗi trạng thái báo một lần, và luôn có một bản trong hòm thư.
- **XONG khác ĐẠT**: tin báo nói rõ việc đã qua nghiệm thu chưa. Team không bật nghiệm thu thì Javis nói thẳng là chưa ai xác nhận đạt.
- **Cổng duyệt vẫn là của bạn**: việc cần bạn duyệt hay xác nhận nghiệm thu vẫn dừng ở thẻ việc trên trang Nhóm. Javis chỉ báo, không bấm duyệt thay.
- **Không giao trùng**: Javis lỡ gọi lại cùng yêu cầu thì vẫn chỉ có một việc. Trong khung chat nhóm, tin giao việc có nhãn "qua Javis Core".
- Hỏi "việc đó tới đâu rồi" thì Javis đọc lại trạng thái, kết quả và nghiệm thu của việc.

Chỉ chủ (hoặc việc nền chủ đã lên lịch) mới giao được. Bot chăm khách, Team của brain khác hay một bước việc của chính Team đều bị từ chối trước khi có việc nào được tạo.

## Thao tác nhanh và khắc phục sự cố

- **Tạo mới:** chọn tab rồi bấm nút tạo ở cuối cột trái; hoặc mở **Javis Store**.
- **Hội thoại mới:** bắt đầu phiên riêng với cộng sự đang chọn.
- **Sửa / Xuất / Xoá:** nằm ở cột phải của cộng sự.
- **Danh sách trống:** kiểm tra brain đang chọn, ô tìm và bộ lọc tag (hay nhóm), rồi tạo cộng sự nếu chưa có.
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
