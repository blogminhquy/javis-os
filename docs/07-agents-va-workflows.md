# Agents & Workflows

Đây là nơi bạn tạo ra các trợ lý AI chuyên biệt (Agent) và ghép chúng thành dây chuyền làm việc tự động (Workflow). Ví dụ: một agent chuyên nghiên cứu, một agent chuyên viết bài, một agent chuyên kiểm tra lại, nối thành chuỗi "nghiên cứu > viết > kiểm chứng" chạy một phát ra kết quả.

## Tính năng này là gì

- **Agent** là một "nhân viên AI" có vai trò cố định. Mỗi agent gồm: một cái tên, một mô tả vai trò, một hướng dẫn làm việc chi tiết (system prompt), danh sách kỹ năng (skill) được phép dùng, một **model chạy**, và một **bộ nhớ riêng** tích luỹ theo thời gian. Model chọn được từ **mọi nhà cung cấp bạn đã kết nối** ở trang Models: Claude (Claude Code), ChatGPT (Codex), Gemini CLI, Antigravity CLI, OpenRouter, Anthropic API, OpenAI, Google Gemini, Groq. Danh sách trong ô chọn lấy thẳng từ các nhà đã kết nối, nên kết nối thêm là có thêm lựa chọn. Nhà nào cũng đọc/ghi được file trong vault và dùng được MCP; riêng Claude Code và Codex có thêm lệnh máy cùng khả năng tự mở web. Nhà đã chọn trục trặc lúc chạy thì Javis tự lùi sang bộ não khác thay vì để agent chết lặng. (Ollama chưa chạy được agent nên không xuất hiện ở đây.) Model của agent được áp THẬT khi workflow chạy.
  - Lưu ý an toàn: khi workflow chạy **nền tự động** (dispatcher Kanban, chế độ giới hạn công cụ file), agent luôn dùng Claude Code để giữ giới hạn công cụ an toàn - kể cả khi bạn chọn nhà khác. Model bạn chọn chỉ áp khi bạn bấm **▶ Chạy** trực tiếp ở trang Workflows.
- **Workflow** là một chuỗi nhiều bước, mỗi bước giao cho một agent làm một nhiệm vụ. Kết quả bước trước có thể chảy sang bước sau. Bạn có thể gắn thêm một **bước kiểm chứng**: một agent khác đóng vai người soi lỗi, mặc định giả định kết quả đang sai và phải tự chứng minh; nếu chưa đạt, workflow tự sửa lại vài lần.
- Mọi agent và workflow được lưu thành **file .md trong vault** (bộ não đang chọn), nên bạn xem được, sửa tay được, và Javis cũng tạo được bằng lời qua chat.

Liên quan: chọn model cho agent xem [Models & engine](10-models-va-engine.md); tạo và bật/tắt skill để gán cho agent xem [Skills](06-skills.md).

## Mở ở đâu trong Javis

Trên thanh điều hướng bên trái của dashboard (mặc định tại cổng 7777), mở nhóm **Năng lực**. Nhóm này có 4 mục, trong đó hai mục dùng ở trang này:

- **Agents**: quản lý các trợ lý AI.
- **Workflows**: quản lý các dây chuyền.

(Hai mục còn lại của nhóm là Skills và Plugins.) Bấm vào là mở đúng trang tương ứng. Toàn bộ nội dung của hai trang này thuộc về một bộ não (brain) đang được chọn: nếu bạn đổi brain, danh sách agent và workflow cũng đổi theo.

## Trước tiên: bấm "Tạo mẫu" để có ví dụ chạy được ngay

Nếu bạn mới bắt đầu và chưa có gì, cách nhanh nhất là dùng bộ mẫu có sẵn.

1. Mở trang **Workflows**.
2. Ở góc trên bên phải, bấm nút **Tạo mẫu**.
3. Javis sẽ tạo sẵn 3 agent và 1 workflow mẫu (cả 3 agent đều được đặt sẵn model **Sonnet**):
   - Agent **Researcher**: chuyên nghiên cứu, tìm tư liệu, tổng hợp nguồn (được gán sẵn skill deep-research).
   - Agent **Writer**: chuyên viết bài từ tư liệu nghiên cứu (được gán sẵn skill salepage-16-buoc).
   - Agent **Kiểm chứng viên**: đánh giá độc lập, luôn giả định kết quả sai và phải chứng minh; không tạo nội dung, chỉ chấm.
   - Workflow **Research → Write (có kiểm chứng)**: bước 1 nghiên cứu, bước 2 viết bài rồi kiểm chứng độc lập, tự sửa tối đa 2 lần nếu chưa đạt.

Sau khi có mẫu, bạn có thể chạy thử ngay (xem mục "Chạy một workflow" bên dưới), hoặc mở ra sửa lại theo ý mình để hiểu cách hoạt động.

Ghi chú: hai skill mà agent mẫu tham chiếu (deep-research, salepage-16-buoc) chỉ là tên gán sẵn. Nếu brain của bạn chưa có hai skill đó thì agent vẫn chạy bình thường, chỉ là không có hướng dẫn chuyên sâu kèm theo.

## Tạo một Agent (từng bước, qua form)

1. Mở trang **Agents**.
2. Bấm nút **+ Agent** ở góc trên bên phải. Một khung soạn thảo mở ra bên phải màn hình.
3. Điền các ô sau:

| Ô | Ý nghĩa | Gợi ý điền |
|---|---|---|
| **Tên** | Tên agent, hiện trên thẻ. Bắt buộc. | VD: "Chuyên viên email" |
| **Vai trò (mô tả ngắn)** | Một câu mô tả agent làm gì. | VD: "Viết email bán hàng, giọng thân mật" |
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

Cả hai đều là file văn bản thường: mở, đọc và sửa tay được qua [Quản lý tệp tin](05-quan-ly-tep-tin.md). Muốn dạy một agent nhớ điều gì, cứ viết thẳng vào `memory/agents/<slug>/MEMORY.md` là lần chạy sau nó đã biết. Đây là lý do trang Agents khi còn trống ghi "Chưa có agent. Bấm + Agent để tạo (vai trò + skills + bộ nhớ riêng)."

Phân biệt: bộ nhớ này là của **riêng một agent**; bộ nhớ chung của Javis về bạn và doanh nghiệp nằm ở `memory/MEMORY.md` và `memory/facts/`, xem [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

### Sửa hoặc xoá agent

- **Sửa**: trên thẻ agent, bấm **Sửa**, chỉnh rồi bấm **Lưu**.
- **⤓ Xuất**: đóng gói agent (kèm skill của nó) thành file `.zip` để chia sẻ, xem mục "Chia sẻ" cuối trang.
- **Xoá**: bấm **Xoá**, xác nhận ở hộp thoại "Xoá agent ...?". Lưu ý: nếu một workflow đang dùng agent này thì bước đó sẽ trỏ tới agent không còn tồn tại, nên xoá xong hãy kiểm tra lại các workflow liên quan. Xoá agent **không** xoá thư mục `memory/agents/<slug>/`, nên bộ nhớ và nhật ký cũ vẫn còn trên đĩa.

## Tạo một Workflow (từng bước, qua form)

Cần có ít nhất một agent trước khi tạo workflow. Nếu chưa có agent nào, khi bấm tạo workflow Javis sẽ báo "Chưa có agent nào. Hãy tạo Agent trước (tab Agents) hoặc bấm Tạo mẫu."

1. Mở trang **Workflows**.
2. Bấm **+ Workflow** ở góc trên bên phải.
3. Điền:
   - **Tên**: tên workflow. Bắt buộc.
   - **Mô tả**: một dòng nói workflow này làm gì (không bắt buộc nhưng nên có; dòng này hiện trên thẻ workflow).
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

Đây chính là workflow mẫu "Research → Write (có kiểm chứng)" mà nút Tạo mẫu sinh ra.

### Đọc thẻ workflow

Mỗi workflow hiện dạng một thẻ, gồm:

- Hàng tiêu đề: tên workflow, một huy hiệu trạng thái (**● Sẵn sàng** khi đang bật hoặc **Lưu trữ** khi đang tắt), và số bước dạng "N bước".
- Dòng mô tả workflow (nếu bạn có điền ô Mô tả).
- Sơ đồ dây chuyền: các bước đánh số 01, 02, ... Mỗi ô hiện **nhiệm vụ** làm chữ chính, tên agent làm chữ phụ bên dưới. Trong nhiệm vụ, biến được dịch thành lời cho dễ đọc: `{{input}}` hiện là "đầu vào", `{{prev}}` hiện là "kết quả bước trước"; biến nào khác thì hiện thẳng tên biến.
- Hàng nút: **▶ Chạy**, **Sửa**, **Lưu trữ** hoặc **Kích hoạt**, **⤓ Xuất**, **Xoá**.

### Bật, tắt, sửa, xoá workflow

- **Bật/tắt**: bấm **Lưu trữ** để tắt workflow (nút đổi thành **Kích hoạt**). Workflow đang lưu trữ không chạy được: nút **▶ Chạy** bị mờ. Bấm **Kích hoạt** để bật lại.
- **Sửa**: bấm **Sửa**, chỉnh các bước rồi **Lưu**.
- **Xoá**: bấm **Xoá**, xác nhận ở hộp thoại "Xoá workflow ...?".

## Chạy một workflow (từng bước)

1. Trên thẻ workflow đang ở trạng thái **● Sẵn sàng**, bấm **▶ Chạy**.
2. Một ô nhập hiện lên hỏi đầu vào, ví dụ "Đầu vào cho ... (vd: chủ đề bài viết)". Gõ nội dung bạn muốn đưa vào (chính là giá trị của `{{input}}`), rồi xác nhận. Nếu bấm huỷ, workflow không chạy.
3. Một bảng theo dõi trượt ra bên phải màn hình, hiển thị tiến trình theo thời gian thực:
   - Trên đầu ghi "▶ tên workflow", dòng dưới ghi tổng số bước.
   - Huy hiệu trên thẻ đổi thành **⏳ Đang chạy...**, rồi **⏳ Bước 1/N**, **⏳ Bước 2/N**, ...
   - Trong sơ đồ dây chuyền, bước đang chạy sáng lên; bước xong chuyển sang đánh dấu hoàn tất.
   - Với mỗi bước, bạn thấy tên agent, nhiệm vụ, và kết quả chữ đổ dần ra khi agent làm việc. Nếu agent gọi công cụ, sẽ có ghi chú ⚙ kèm tên công cụ.
4. Nếu bước có kiểm chứng, sau khi agent làm xong sẽ hiện dòng "🔍 ... đang kiểm chứng..." (kèm số lần thử nếu lặp lại). Kết quả kiểm chứng ra một trong hai:
   - **✓ Đạt**: bước qua, chảy sang bước sau.
   - **✗ Chưa đạt**: kèm lý do ngắn. Workflow tự chạy lại bước đó (dòng "↻ Sửa lại lần ...") theo phản hồi, tối đa bằng số lần bạn đặt. Lượt sửa THẤY kết quả cũ kèm phản hồi để cải thiện tiếp, không làm lại từ đầu.
   - Nếu sửa hết số lần vẫn chưa đạt, bước vẫn kết thúc nhưng gắn cảnh báo "⚠ Chưa đạt kiểm chứng sau số lần thử - xem lại kết quả". Lúc này bạn nên tự đọc lại đầu ra.
5. Khi xong toàn bộ, cuối bảng hiện "✓ Workflow hoàn tất".
6. Bấm nút đóng của bảng để tắt bảng theo dõi. Đóng bảng cũng dừng phần đang chạy.

Sau mỗi bước xong, Javis ghi kết quả vào nhật ký chạy của agent phụ trách bước đó (`memory/agents/<slug>/runs/`), nên bạn đọc lại được kể cả khi đã đóng bảng.

## Tạo agent và workflow bằng lời (qua chat)

Bạn không bắt buộc phải dùng form. Trong khung trò chuyện với Javis (xem [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md)), bạn có thể ra lệnh bằng lời, ví dụ:

- "Tạo agent chuyên viết email bán hàng."
- "Tạo workflow nghiên cứu rồi viết bài."
- "Thêm bước biên tập vào workflow X."

Khi đó Javis tự ghi file .md tương ứng vào vault, tự đặt slug không dấu, tự gán skill hợp lý từ skill có sẵn, và nếu workflow nhắc tới một agent chưa tồn tại thì tạo agent đó trước. Sau khi làm xong, Javis báo ngắn gọn đã tạo/sửa file nào. Bạn quay lại trang Agents hoặc Workflows là thấy ngay, không cần thao tác thêm.

Cách này tiện khi bạn mô tả được ý định bằng lời nhưng ngại điền form, hoặc muốn chỉnh nhiều bước cùng lúc.

## Agent và workflow được lưu ở đâu

Trong brain theo cấu trúc mới, mỗi agent là một file `agents/<slug>.md` và mỗi workflow là một file `workflows/<slug>.md`. `slug` là tên viết thường, có gạch ngang, không dấu (ví dụ "viết email" thành `viet-email`).

**Brain cũ chưa chuyển cấu trúc** thì hai thư mục đó nằm ở `Javis/agents/` và `Javis/workflows/`. Javis tự dò: có thư mục mới thì dùng thư mục mới, không có thì dùng đường cũ. Nên nếu bạn mở trang Tệp tin mà không thấy `agents/` ở gốc brain, hãy tìm trong `Javis/`.

Vì là file văn bản, bạn có thể mở qua [Quản lý tệp tin](05-quan-ly-tep-tin.md) để xem hoặc sửa tay. Cấu trúc file:

- Agent: phần đầu (frontmatter) chứa tên, vai trò, danh sách skill, model; phần thân là system prompt chi tiết. Bộ nhớ riêng và nhật ký chạy nằm ngoài file này, ở `memory/agents/<slug>/`.
- Workflow: phần đầu chứa tên, trạng thái (active hoặc off), mô tả và danh sách các bước (mỗi bước có agent, task, và tuỳ chọn agent kiểm chứng cùng số lần sửa).

Sửa file rồi lưu thì trang Agents / Workflows tự nhận nội dung mới ở lần tải lại.

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
- **Nhập:** mỗi trang **Agents / Skills / Workflows** có nút **⤒ Nhập**. Chọn file `.zip` (gói Javis), file `.md` lẻ (agent/workflow), hoặc **gói skill `.skill` của Claude** (Javis tự nhận diện `SKILL.md` trong gói và đưa vào đúng thư mục skill) để đưa vào brain đang chọn. Javis hỏi có **ghi đè** khi trùng tên không: bấm Huỷ để giữ nguyên cái đã có (chỉ nhập cái mới), bấm OK để ghi đè bằng bản trong gói. Sau khi nhập, Javis báo đã nhập gì, bỏ qua gì.
- **An toàn:** khi nhập, Javis chặn các đường dẫn bất thường trong gói (không cho ghi ra ngoài các thư mục agent/skill/workflow) và giới hạn dung lượng để tránh file độc. Dù vậy, chỉ nên nhập gói từ nguồn bạn tin tưởng, vì nội dung skill là hướng dẫn cho AI làm theo.

Lưu ý: gói xuất chỉ chứa file định nghĩa. **Bộ nhớ riêng và nhật ký chạy của agent không đi theo gói** - bên nhận có được vai trò và kỹ năng, không có ký ức.

## Bảng tra nhanh nút và trạng thái

| Bạn thấy | Ý nghĩa / thao tác |
|---|---|
| **+ Agent** / **+ Workflow** | Mở khung soạn thảo tạo mới |
| **Tạo mẫu** (trang Workflows) | Sinh 3 agent + 1 workflow ví dụ chạy được ngay |
| **⤒ Nhập** | Đưa gói `.zip` / `.md` / `.skill` vào brain đang chọn |
| **⤓ Xuất** | Tải về gói `.zip` kèm phụ thuộc để chia sẻ |
| **● Sẵn sàng** | Workflow đang bật, chạy được |
| **Lưu trữ** (huy hiệu) | Workflow đang tắt, nút ▶ Chạy bị mờ |
| **Lưu trữ** / **Kích hoạt** (nút) | Tắt / bật workflow |
| **N bước** | Số bước trong dây chuyền |
| **▶ Chạy** | Chạy workflow, hỏi đầu vào rồi mở bảng theo dõi |
| **↑** / **↓** (trong bước) | Đổi thứ tự bước |
| **✕** (cuối hàng tiêu đề bước) | Xoá bước đó |
| **⏳ Bước i/N** | Đang chạy tới bước thứ i |
| **✓ Đạt** / **✗ Chưa đạt** | Kết quả một lượt kiểm chứng |
| **↻ Sửa lại lần k** | Đang chạy lại bước theo phản hồi kiểm chứng |
| **⚠ Chưa đạt kiểm chứng sau số lần thử** | Hết lượt sửa mà vẫn chưa đạt, cần bạn đọc lại |
| **✓ Workflow hoàn tất** | Chạy xong toàn bộ |

## Sự cố thường gặp

- **Bấm + Workflow báo "Chưa có agent nào".** Bạn chưa tạo agent. Sang trang Agents tạo ít nhất một agent, hoặc bấm Tạo mẫu ở trang Workflows để có sẵn bộ ví dụ.
- **Nút ▶ Chạy bị mờ, không bấm được.** Workflow đang ở trạng thái Lưu trữ. Bấm **Kích hoạt** để đổi về ● Sẵn sàng rồi chạy lại.
- **Danh sách rỗng, ghi "Chưa có workflow" hoặc "Chưa có agent".** Đây là trạng thái ban đầu. Bấm **Tạo mẫu** (ở Workflows) hoặc **+ Agent** / **+ Workflow** để bắt đầu. Nếu vừa đổi brain mà thấy trống, kiểm tra bạn đang ở đúng brain.
- **Mở Sửa workflow thấy các bước gập hết, tưởng mất nội dung.** Không mất. Workflow đang sửa mặc định gập để thấy toàn cảnh; bấm vào hàng tiêu đề bước là mở ra.
- **Ô Skills trống khi tạo agent.** Vault chưa có skill nào trong thư mục skill. Tạo agent trước, tạo skill sau ở trang [Skills](06-skills.md) rồi quay lại gán.
- **Chọn model GPT-5.x mà agent vẫn chạy bằng Claude.** Đúng như thiết kế khi workflow chạy nền tự động: chế độ đó ép dùng Claude Code để giữ giới hạn công cụ. Muốn dùng Codex thì bấm **▶ Chạy** trực tiếp trên thẻ workflow, và máy phải đã đăng nhập ChatGPT.
- **Để trống ô Model mà agent chạy bằng model lạ.** Ô trống nghĩa là lấy model phụ ở trang Models trước. Muốn cố định thì chọn thẳng model cho agent.
- **Không tìm thấy thư mục `agents/` trong brain.** Brain cũ để ở `Javis/agents/` và `Javis/workflows/`. Mở trang Tệp tin và tìm trong thư mục `Javis`.
- **Bước hiện cảnh báo "⚠ Chưa đạt kiểm chứng sau số lần thử".** Agent làm đã sửa hết số lần cho phép mà agent kiểm chứng vẫn chấm chưa đạt. Đọc lại đầu ra bước đó bằng mắt; cân nhắc chỉnh lại nhiệm vụ cho rõ hơn, đổi model mạnh hơn, hoặc tăng số lần sửa rồi chạy lại.
- **Bảng theo dõi dừng giữa chừng.** Đóng bảng theo dõi sẽ ngắt phần đang chạy. Nếu mạng chập chờn, bảng cũng có thể dừng; mở lại workflow và bấm ▶ Chạy để chạy lại từ đầu.
- **Trang tải mãi ghi "Đang tải...".** Server chậm hoặc chưa chạy. Kiểm tra Javis đang bật ở cổng 7777, sau đó tải lại trang. Nếu vẫn lỗi, xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

## Liên quan

- [Skills](06-skills.md) - tạo, bật/tắt và gán kỹ năng cho agent.
- [Plugins](20-plugins.md) - mục thứ tư trong nhóm Năng lực, dành cho tool chạy code thật.
- [Models & engine](10-models-va-engine.md) - chọn model chính, model phụ và các nhà cung cấp.
- [Việc / Kanban](21-viec-kanban.md) - nơi workflow chạy nền tự động theo task.
- [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) - phân biệt bộ nhớ riêng của agent với bộ nhớ chung của Javis.
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - mở và sửa tay file agent, workflow, bộ nhớ.
