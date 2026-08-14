# Bắt đầu & thiết lập lần đầu

***Tiếng Việt** · [English](en/01-getting-started.md)*

Trang này hướng dẫn bạn từ lúc mở Javis lần đầu tiên cho tới khi Javis sẵn sàng trò chuyện: tạo tài khoản admin, chọn nhà cung cấp AI làm "bộ não", chọn model, và kiểm tra trạng thái hệ thống ở trang Cài đặt.

## Tính năng này là gì

Javis OS là một lớp điều hành AI chạy trên máy hoặc VPS của bạn. Bộ não là nhà cung cấp AI mà bạn đấu vào: Claude Code, ChatGPT (qua Codex), Antigravity CLI, OpenRouter, OpenAI API, Anthropic API, Google Gemini, Groq hoặc Ollama Cloud. Bộ cài đặt lần đầu **chọn sẵn** Claude Code vì đó là lựa chọn được khuyên dùng, chứ Javis không bị khoá vào một nhà cung cấp nào.

Trước khi dùng được, Javis cần 3 thứ:

1. Một tài khoản admin (để chặn người lạ, bắt buộc khi chạy công khai trên VPS).
2. Một nhà cung cấp AI đã đăng nhập hoặc đã dán API key.
3. Một model chính để trả lời hội thoại.

Lần đầu mở app, một bộ cài đặt (wizard) sẽ hiện ra và dẫn bạn qua đúng 3 việc này. Mọi thứ đặt ở đây đều đổi lại được sau trong các trang quản lý.

## Mở ở đâu trong Javis

- Trên máy cá nhân, mở trình duyệt và vào `http://localhost:7777` (cổng mặc định là 7777).
- Trên VPS hoặc Docker, dùng địa chỉ mà nhà cung cấp cấp cho bạn, ví dụ `http://<ip-vps>:7777` hoặc link HTTPS dạng `https://<app>.<vps>.hstgr.cloud`.

Sau khi thiết lập xong, các mục liên quan nằm trên rail điều hướng bên trái. Rail gom thành 7 nhóm, **phải bấm mở nhóm mới thấy mục con**:

| Nhóm | Mục | Dùng để |
|---|---|---|
| Kết nối | **Models** | Đổi model chính, đăng nhập/ngắt các nhà cung cấp (xem [Models & engine](10-models-va-engine.md)) |
| Hệ thống | **Cài đặt** | Bốn nhóm cấu hình gập/mở: trạng thái hệ thống, giao diện & brain, giọng nói/thương hiệu, khởi động cùng Windows |
| Hệ thống | **Cập nhật** | Phiên bản đang chạy, nút cập nhật, tiến trình và nhật ký phiên bản |
| Hệ thống | **Tài khoản** | Đổi mật khẩu, đăng xuất, tắt đăng nhập (xem [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md)) |

## Cách dùng (từng bước)

### Bước 1: Mở app và gặp bộ cài đặt

Mở `http://localhost:7777` (hoặc địa chỉ VPS của bạn). Nếu đây là lần đầu và chưa có tài khoản, Javis hiện cửa sổ **Chào mừng tới Javis** với 3 mục đánh số sẵn.

Nếu bạn chạy trên máy cá nhân (localhost), mục mật khẩu và MÃ THIẾT LẬP là tùy chọn, có thể bỏ trống. Nếu bạn chạy công khai (VPS/Docker), Javis bắt buộc bạn đặt mật khẩu và nhập MÃ THIẾT LẬP mới cho qua; lúc đó dòng nhắc "Đặt tài khoản + mật khẩu (≥8 ký tự) + MÃ THIẾT LẬP để bảo vệ Javis trên server công khai." hiện ngay dưới nút.

### Bước 2: Đặt tên Workspace

Ở mục **1. Workspace**, gõ tên hiển thị vào ô **Tên hiển thị** (ví dụ tên cửa hàng hoặc tên bạn). Bỏ trống thì Javis dùng mặc định là "Javis OS". Đây chỉ là nhãn hiển thị, đổi lại bất cứ lúc nào.

### Bước 3: Tạo tài khoản admin (và MÃ THIẾT LẬP nếu cần)

Ở mục **2. Tài khoản admin**:

1. Gõ tên tài khoản vào ô **Tài khoản** (mặc định gợi ý là `admin`).
2. Gõ mật khẩu vào ô **Mật khẩu**. Mật khẩu phải dài tối thiểu 8 ký tự.
3. Nếu Javis chạy công khai, một ô **Mã thiết lập** sẽ hiện ra. Dán MÃ THIẾT LẬP vào đây (cách lấy xem mục "Khi nào cần MÃ THIẾT LẬP" bên dưới).

Trên máy cá nhân, nếu bạn để trống mật khẩu thì Javis không đặt tài khoản và ai mở link máy này cũng dùng được. Chỉ nên bỏ trống khi máy chỉ mình bạn dùng.

### Bước 4: Chọn nhà cung cấp AI (bộ não)

Ở mục **3. Nhà cung cấp AI (bộ não)**, chọn 1 trong 3 thẻ:

| Lựa chọn | Chữ trên thẻ | Cần gì để dùng |
|---|---|---|
| **🧠 Claude Code** (chọn sẵn) | "Đăng nhập subscription Claude → đủ MCP, skill, đọc/ghi file, vòng lặp tự cải thiện. Mạnh & đầy đủ nhất." | Đăng nhập subscription Claude 1 lần (không cần API key) |
| **💬 ChatGPT (gói subscription)** | "Đăng nhập ChatGPT Plus/Pro (qua Codex) → vẫn dùng được MCP của Javis." | Đăng nhập ChatGPT ở trang Models |
| **🌐 OpenRouter** | "Nhiều model giá rẻ một chỗ, vẫn đủ MCP Javis + skill + đọc/ghi file brain. Chỉ cần API key - không cần đăng nhập." | Dán API key OpenRouter (dán ngay hoặc để sau ở Models) |

Chọn cái nào cũng ra một Javis đủ chức năng: cả ba đều gọi được kho Kết nối (MCP), đọc/ghi file trong brain, chạy skill, giao việc và tạo loop. Khác biệt duy nhất là **chạy lệnh máy**, thứ chỉ các engine CLI (Claude Code, Codex, Antigravity CLI) làm được. Wizard chỉ hiện 3 thẻ cho gọn; vào trang **Models** còn Antigravity CLI, OpenAI API, Google Gemini, Anthropic API, Groq và Ollama, đổi lúc nào cũng được.

Nếu chọn **OpenRouter**, một ô nhập **OpenRouter API key** sẽ hiện ra, bạn có thể dán key ngay hoặc để trống rồi dán sau ở trang Models. Dưới danh sách còn một dòng gợi ý thay đổi theo thẻ bạn chọn, ví dụ chọn ChatGPT thì gợi ý "Sau khi vào: mục **Models** → đăng nhập ChatGPT".

Bấm **Bắt đầu dùng Javis →** để lưu và vào app. Wizard đồng thời đặt luôn một model mặc định cho nhà cung cấp bạn chọn: `sonnet` cho Claude Code, `gpt-5.5` cho ChatGPT, `openai/gpt-4o-mini` cho OpenRouter. Đổi lại ở trang Models bất cứ lúc nào.

### Bước 5: Đăng nhập Claude làm bộ não

Đây là bước quan trọng nhất nếu bạn chọn Claude Code. Wizard chỉ lưu lựa chọn nhà cung cấp, việc đăng nhập Claude thực hiện ở trang **Models** (nhóm **Kết nối**):

1. Vào mục **Models** trên rail bên trái.
2. Tìm thẻ **Anthropic OAuth (Claude Code)**. Trạng thái ban đầu là "○ Chưa đăng nhập".
3. Bấm nút **Đăng nhập Claude**.
4. Javis hiện một đường link. Bấm mở link đó (mở trong tab mới) để đăng nhập tại claude.ai.
5. Nếu sau khi đăng nhập trang hiện một mã code, dán mã đó vào ô **dán code (nếu có)** rồi bấm **Gửi code**. Một số luồng không cần dán code, Javis tự dò lại trạng thái mỗi 3 giây và cập nhật thẻ.
6. Khi xong, trạng thái thẻ đổi thành "● Đã kết nối" (kèm email/gói nếu có).

Đây là luồng device-code: bạn không cần nhập API key. Cách này chạy được cả trên VPS không có màn hình. Nếu bạn có quyền vào terminal của server, cũng có thể đăng nhập một lần bằng lệnh `claude auth login --claudeai` thay cho các bước trên.

Nút **↻ Kiểm tra lại** trên thẻ dùng để nạp lại trạng thái đăng nhập bất cứ lúc nào. Nút **Ngắt** dùng để đăng xuất Claude khỏi Javis.

Engine Claude của Javis chạy qua **Claude Agent SDK**, nhưng SDK vẫn gọi tới `claude` CLI trên máy, nên máy chạy Javis phải cài sẵn `claude` thì đăng nhập và MCP native mới hoạt động.

### Bước 6: Chọn model chính và model việc nền

Sau khi đã đăng nhập, kiểm tra và chọn model ở trang **Models**:

- Phần **◆ Main Model** hiển thị model đang dùng cho hội thoại. Bấm **Đổi model ▾** để chọn model khác.
- Phần **◆ Providers** liệt kê **mười** nhà cung cấp: Anthropic OAuth (Claude Code), OpenAI OAuth (ChatGPT), Google Antigravity CLI, Google Gemini CLI, OpenRouter, Anthropic (API), OpenAI (ChatGPT API), Google Gemini (API), Groq (API), Ollama Cloud. Thẻ nào cần key thì có ô dán key và nút **Kết nối** / **Đổi key** / **Ngắt**.
- Phần **◆ Model việc nền** (phụ đề "loop · việc Kanban · nhắc hẹn · tự học · tiêu hoá nguồn") cho phép chọn một model rẻ cho các việc chạy nền để đỡ hạn mức. Chưa đổi thì dòng trạng thái ghi "Mặc định của Claude Code". Bấm **Đổi model ▾** để chọn, bấm **Về mặc định** để trả lại. Nếu bạn chọn nhà cung cấp chưa kết nối, thẻ cảnh báo "⚠ nhà cung cấp này chưa kết nối - việc nền sẽ tự dùng lại Claude".
- Phần **◆ Suy nghĩ** (reasoning) đặt độ sâu suy nghĩ khi trả lời: **Tắt**, **Thấp**, **Vừa**, **Cao**. Mặc định là Tắt (trả lời nhanh).

Việc nền chạy được bằng cả nhà cung cấp API, không riêng Claude. Khác biệt thật nằm ở chỗ khác: Claude Code và Codex đọc/ghi file trực tiếp trong brain và chạy được lệnh máy, còn các model API đọc/ghi qua công cụ vault của Javis và không chạy lệnh máy, nên hợp với việc đọc, tổng hợp và ghi ghi chú.

Chi tiết đầy đủ về từng nhà cung cấp và model xem [Models & engine](10-models-va-engine.md).

## Trang Cài đặt: bốn nhóm cấu hình

Mở **Cài đặt** (nhóm **Hệ thống** trên rail). Trang chia thành bốn nhóm gập/mở, bấm tiêu đề nhóm để đóng hoặc mở.

### Nhóm 1: Hệ thống

Phụ đề: "Trạng thái hiện tại và lối tắt tới các nhóm chuyên sâu". Gồm bốn ô trạng thái:

| Ô | Cho biết |
|---|---|
| **Engine** | Nhãn nhà cung cấp đang làm model chính, ví dụ "Anthropic OAuth (Claude Code)", "OpenRouter", "Google Gemini (API)" |
| **Model** | Model chính đang dùng, hoặc "Mặc định" |
| **Workspace** | Tên workspace bạn đặt ở wizard |
| **Telegram** | "Đang bật" hoặc "Đang tắt" (xem [Kênh Telegram](11-telegram.md)) |

Bên dưới là bốn lối tắt bấm là nhảy thẳng sang trang tương ứng: **Models**, **Kênh**, **Tài khoản**, **Cập nhật**.

### Nhóm 2: Giao diện & Brain

Phụ đề: "Hiệu năng đồ thị và cấu trúc dữ liệu". Gồm ba thẻ.

**Thẻ Đồ thị não** cho biết đồ thị tri thức đang bật hay tắt.

- Bấm **Tắt đồ thị** để giảm tải tối đa; khi đang tắt, nút đổi thành **Bật đồ thị**.
- Nếu màn hình hẹp (dưới 860px, tức điện thoại), Javis tự vào chế độ nhẹ: đồ thị dừng chạy dù công tắc đang bật. App vẫn mở ở màn Javis như trên máy tính - màn đó đã có sẵn ô chat, chỉ khác là không vẽ khoang não.

Chi tiết về đồ thị xem [Đồ thị tri thức](03-do-thi-tri-thuc.md).

**Thẻ Chuẩn hóa brain** gom các thư mục `agents`, `workflows`, `memory`, `skills` của brain đang chọn về cấu trúc phẳng đồng nhất. Bấm **Chuẩn hóa brain đang chọn** để chạy.

Thao tác này an toàn: chỉ di chuyển khi thư mục đích chưa có, không ghi đè, chạy lại nhiều lần cũng vô hại (ví dụ chuyển `Javis/agents` sang `agents`, `Memory` sang `memory`). Sau khi chạy, Javis báo đã di chuyển gì hoặc "Không có gì cần di chuyển (đã chuẩn)".

**Thẻ Dấu nguồn gốc ảnh AI** quyết định ảnh Javis tạo ra có mang dấu nguồn gốc (Content Credentials, chuẩn C2PA) hay không. Nhãn góc phải là "Đang giữ" hoặc "Đang gỡ".

- Mặc định là **Giữ dấu**: ảnh mang sẵn dấu ghi rằng ảnh do AI sinh ra. Facebook đọc dấu này để gắn nhãn "Nội dung do AI tạo" lên bài.
- Bấm **Gỡ dấu** thì ảnh mới tạo không còn dấu, nhãn trên nền tảng thường không hiện nữa. Ảnh đã tạo trước đó không đổi.
- Dù bật hay tắt, nhãn tác giả `javisos.com` vẫn được giữ, và bạn vẫn phải tự chịu trách nhiệm công bố nội dung AI theo luật và điều khoản của nền tảng nơi bạn đăng.

### Nhóm 3: Giọng nói, thương hiệu & truy cập

Phụ đề: "TTS, avatar và tên miền riêng". Đây là nơi chứa bộ **⚙ CÀI ĐẶT NHANH**:

- Công tắc **🔊 Đọc trả lời bằng giọng**.
- Khối **NHÀ CUNG CẤP GIỌNG ĐỌC**: chọn "Edge TTS - miễn phí (mặc định)", "OpenAI - mượt, đa ngôn ngữ" hoặc "ElevenLabs - tự nhiên nhất", dán key tương ứng rồi bấm **Lưu nhà cung cấp**. Provider trả phí lỗi sẽ tự về Edge.
- **NGÔN NGỮ NGHE** (Tiếng Việt `vi-VN` hoặc Tiếng Anh `en-US`), **GIỌNG ĐỌC (Edge)** (Ngọc Thu hoặc Nam Minh), **TỐC ĐỘ** và nút **▶ Nghe thử**. Khối giọng Edge chỉ hiện khi nhà cung cấp là Edge.
- **ẢNH ĐẠI DIỆN**: **Tải ảnh lên** hoặc **Khôi phục mặc định**.
- **TÊN MIỀN & SSL**: nhập tên miền, bấm **Lưu & kiểm tra**, xem hai nhãn `DNS:` và `SSL:`, rồi **Bật SSL** hoặc **Kiểm tra lại**.

Chi tiết xem [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) và [Thương hiệu & tên miền](15-thuong-hieu-ten-mien.md).

### Nhóm 4: Khởi động cùng Windows

Nhóm này **chỉ hiện trên bản chạy Windows**; bản Docker/Linux ẩn hẳn. Thẻ **Tự bật Javis** cho biết trạng thái ("Bật" hoặc "Tắt") và có một nút duy nhất: **Bật tự khởi động** hoặc **Tắt tự khởi động**. Khi bật, Javis tự chạy nền lúc bạn đăng nhập Windows, mở `localhost:7777` là dùng được.

#### Khi thẻ ghi "Bật nhưng không chạy"

Mở máy lên mà `localhost:7777` báo **ERR_CONNECTION_REFUSED** thì mở lại trang này. Javis tự kiểm ba nguyên nhân và ghi thẳng nguyên nhân dưới thẻ, vì cả ba đều **không để lại lỗi ở đâu**:

- **Windows đang chặn mục khởi động này.** Task Manager, thẻ **Startup**, khi bạn bấm Disable thì nó không xoá gì cả, chỉ ghi một cờ để Windows bỏ qua. Nhiều phần mềm "dọn máy, tăng tốc khởi động" cũng tắt bằng đúng cờ đó mà không hỏi. Bấm **Bật tự khởi động** lại là Javis tự gỡ cờ.
- **Thư mục cài đặt đã đổi chỗ**, lệnh khởi động còn trỏ đường dẫn cũ. Bấm bật lại để cập nhật.
- **Thiếu `start-javis.vbs` hoặc `.venv\Scripts\python.exe`.** Chạy lại `setup.bat` để dựng lại phần thiếu.

Nếu thẻ ghi **Bật** không kèm cảnh báo nào mà mở máy vẫn không lên, mở `server\javis.log` trong thư mục cài đặt: đó là nơi server ghi lỗi khi nó có chạy nhưng chết giữa chừng.

Về Second Brain (bộ nhớ, Wiki, cấu trúc vault), xem [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

## Cập nhật phiên bản

Phần này nằm ở mục **Cập nhật** (nhóm **Hệ thống**). Khung Javis OS trên cùng hiển thị phiên bản đang chạy và cho biết có bản mới trên GitHub hay không.

- Có bản mới: "🆕 Có bản mới **v...** (đang chạy v...)" kèm nhãn môi trường (`Windows`, `Linux`, `macOS` hoặc `Docker / VPS`), và khối "Bản mới có gì" liệt kê tối đa 2 bản gần nhất.
- Đang mới nhất: "✅ Đang dùng bản mới nhất (v...)".
- Bấm **Kiểm tra lại** để so lại với bản mới nhất bất cứ lúc nào.

### Nút "⬆ Cập nhật ngay" hiện khi nào

Nút **⬆ Cập nhật ngay** chỉ hiện khi Javis tự cập nhật tại chỗ được. Javis không đoán theo tên nhà cung cấp: nó **dò thật** xem có container Watchtower đang lắng nghe không.

| Kiểu chạy | Cập nhật một chạm? |
|---|---|
| Windows | Có |
| Linux / macOS chạy trực tiếp | Có |
| Docker và Watchtower đang chạy | Có |
| Docker mà không có Watchtower | Không, khung nói rõ vì sao và cách bật |

**Vì sao máy này có nút mà máy kia không.** Gần như luôn là vì Watchtower nằm trong `profiles: ["update"]` của `docker-compose.yml`, nên lệnh `docker compose up -d` quen tay **không bật nó**. Bật một lần, ở thư mục chứa file compose:

```bash
docker compose --profile update up -d
```

Tải lại trang là nút hiện ra. Không muốn bật thì cập nhật tay vẫn được: `docker compose up -d --pull always`.

Riêng **stack Hostinger** (`docker-compose.hostinger.yml`) cố tình không kèm Watchtower - trên đó nó không đụng được Docker socket nên chạy là lỗi vòng lặp. Máy Hostinger cập nhật bằng **Redeploy** trong Docker Manager, không có gì để bật thêm.

Khung Cập nhật tự phân biệt hai trường hợp này và ghi đúng cách xử lý cho máy bạn.

### Thanh tiến trình 6 bước

Bấm **⬆ Cập nhật ngay**, Javis hỏi xác nhận ("Cập nhật Javis lên bản mới nhất? App sẽ tự khởi động lại; nếu lỗi hệ thống sẽ thử quay về bản cũ."). Đồng ý xong, một thanh tiến trình hiện ra và sáng dần qua 6 bước:

**Chuẩn bị → Tải code → Cài thư viện → Khởi động lại → Kiểm tra sức khoẻ → Xong**

Bước đang chạy có dấu ⏳, bước đã qua có ✅. Trong lúc chạy, dòng trạng thái ghi "⏳ Đang cập nhật… đừng tắt trang." Nếu mã nguồn trên máy có sửa đổi cục bộ, Javis báo "📦 Sửa đổi cục bộ đã được cất vào git stash." (cất đi chứ không xoá). Xong xuôi thì hiện "✅ Đã cập nhật xong. Đang tải lại trang…" và app tự tải lại sau khoảng 1,5 giây.

### Khi bản mới hỏng: lùi bản

Javis có sẵn đường lùi, không bỏ bạn kẹt ở bản lỗi:

- **Tự lùi:** nếu bản mới không qua được bước Kiểm tra sức khoẻ, Javis tự quay về bản cũ. Thanh tiến trình hiện "↩ Bản mới lỗi, đang tự quay về bản cũ…", xong thì báo "↩ Bản mới lỗi, đã **tự quay về bản cũ**."
- **Lùi tay trên Docker:** nếu sau một lúc phiên bản vẫn chưa đổi, Javis báo "⚠ Bản mới chưa lên sau một lúc - có thể lỗi." rồi hiện khối **Cách lùi bản Docker** với lệnh `docker compose pull && docker compose up -d`, kèm gợi ý pin image `ghcr.io/blogminhquy/javis-os:<phiên-bản-cũ>` rồi Redeploy.
- **Lỗi khác:** khung báo lỗi cụ thể và nhắc xem file `update.log`. Nếu server không lên lại sau khoảng 3 phút, khung ghi "Server chưa lên lại sau khoảng 3 phút - thử tải lại trang."

Bên dưới khung cập nhật là nhật ký phiên bản: từng bản có gì mới, chia trang, bản đang cài được đánh dấu.

## Khi nào cần MÃ THIẾT LẬP và lấy ở đâu

**MÃ THIẾT LẬP (setup token)** chỉ xuất hiện khi Javis chạy công khai (nghe trên `0.0.0.0`, tức VPS/Docker/Hostinger) và chưa có tài khoản admin. Vì lúc này bộ não chạy với toàn quyền trên máy, Javis không cho phép bất kỳ ai chỉ có đường link cũng tạo được tài khoản admin. MÃ THIẾT LẬP là chuỗi bí mật chỉ in ra log/terminal của server, nên chỉ người có quyền xem server mới lấy được.

Trên máy cá nhân (localhost), Javis không hỏi mã này.

Cách lấy mã:

| Tình huống | Lệnh chạy |
|---|---|
| Hostinger, vào App terminal (bên trong container `javis`) | `cat /data/state/.setup_token` |
| SSH vào host chạy Docker | `docker compose logs javis` rồi tìm dòng `SETUP TOKEN` |

Sau khi có mã, dán vào ô **Mã thiết lập** trong wizard rồi bấm **Bắt đầu dùng Javis →**. Mã được dùng một lần, sau khi tạo tài khoản thành công Javis xóa mã đi.

**Cách khỏi cần mã:** khi deploy, đặt sẵn hai biến môi trường `JAVIS_ADMIN_USER` và `JAVIS_ADMIN_PASSWORD`. Javis tự tạo tài khoản admin lúc khởi động, mở app ra là màn đăng nhập luôn, không hỏi MÃ THIẾT LẬP. Chi tiết biến môi trường xem [Cấu hình .env](16-cau-hinh-env.md).

## Bảng tra nhanh nút và trạng thái

| Nút / dòng chữ | Ở đâu | Làm gì |
|---|---|---|
| **Bắt đầu dùng Javis →** | Wizard | Lưu workspace, tài khoản, nhà cung cấp rồi vào app |
| **Đăng nhập Claude** | Models, thẻ Anthropic OAuth (Claude Code) | Bắt đầu luồng device-code, hiện link claude.ai |
| **Gửi code** | Models, sau khi bấm Đăng nhập Claude | Gửi mã code lấy từ trang claude.ai |
| **↻ Kiểm tra lại** | Models, thẻ Claude Code | Nạp lại trạng thái đăng nhập |
| **Ngắt** | Models | Đăng xuất nhà cung cấp khỏi Javis |
| **Đổi model ▾** | Models, mục Main Model và Model việc nền | Mở bảng chọn model |
| **Về mặc định** | Models, mục Model việc nền | Trả việc nền về model mặc định của Claude Code |
| "○ Chưa đăng nhập" / "● Đã kết nối" | Models | Trạng thái nhà cung cấp |
| **Bật đồ thị** / **Tắt đồ thị** | Cài đặt, thẻ Đồ thị não | Bật hoặc tắt đồ thị tri thức |
| **Chuẩn hóa brain đang chọn** | Cài đặt, thẻ Chuẩn hóa brain | Gom thư mục brain về cấu trúc phẳng |
| **Giữ dấu** / **Gỡ dấu** | Cài đặt, thẻ Dấu nguồn gốc ảnh AI | Bật/tắt dấu C2PA trên ảnh Javis tạo |
| **Bật tự khởi động** / **Tắt tự khởi động** | Cài đặt, nhóm Khởi động cùng Windows | Cho Javis chạy nền khi đăng nhập Windows |
| **Kiểm tra lại** | Cập nhật | So phiên bản với GitHub |
| **⬆ Cập nhật ngay** | Cập nhật (chỉ hiện khi tự cập nhật được) | Chạy cập nhật 6 bước rồi tự tải lại trang |

## Mẹo

- Nếu chỉ chạy máy cá nhân và không sợ người lạ, cứ để trống mật khẩu ở wizard để vào nhanh. Bạn có thể đặt mật khẩu sau ở trang **Tài khoản**.
- Sau khi vào app, nếu thấy báo chưa đăng nhập Claude, quay lại **Models** bấm **Đăng nhập Claude** một lần là xong.
- Đổi avatar, tên miền, giọng nói và tốc độ nằm ở **Cài đặt → Giọng nói, thương hiệu & truy cập**, không phải trong wizard lần đầu.
- Sau khi cập nhật phiên bản, nếu giao diện không đổi, nhấn Ctrl+Shift+R để tải lại trang sạch.
- Chọn một model rẻ ở **Model việc nền** ngay từ đầu: loop, việc Kanban, nhắc hẹn, tự học và tiêu hoá nguồn chạy khá nhiều, để chung model đắt là tốn hạn mức nhanh. Theo dõi con số thật ở trang [Mức dùng](23-muc-dung-token.md).

## Sự cố thường gặp

- **Mở app báo cần MÃ THIẾT LẬP nhưng không biết lấy đâu:** vào App terminal (Hostinger) chạy `cat /data/state/.setup_token`, hoặc trên host chạy `docker compose logs javis` tìm dòng `SETUP TOKEN`. Hoặc đặt sẵn env `JAVIS_ADMIN_PASSWORD` để khỏi cần mã.
- **Báo "Sai hoặc thiếu MÃ THIẾT LẬP":** mã dán vào sai hoặc thiếu. Lấy lại mã đúng từ log server rồi dán lại, chú ý không dính khoảng trắng thừa.
- **Báo "Mật khẩu tối thiểu 8 ký tự":** đặt mật khẩu dài từ 8 ký tự trở lên.
- **Báo "Đã có tài khoản - hãy đăng nhập":** admin đã được tạo trước đó (ví dụ qua env). Dùng màn đăng nhập với tài khoản/mật khẩu đã đặt.
- **Claude báo chưa đăng nhập:** vào **Models**, bấm **Đăng nhập Claude**, mở link, dán code nếu được hỏi. Hoặc chạy `claude auth login --claudeai` trong terminal server.
- **Quên mật khẩu admin:** ở màn đăng nhập bấm "Quên mật khẩu?" để xem hướng dẫn. Cách xử lý là mở file `server/settings.json`, xóa khối `"auth"` (hoặc đặt rỗng), rồi khởi động lại server; mở lại app sẽ về wizard để tạo tài khoản mới. Xem thêm [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).
- **Sai quá nhiều lần khi đăng nhập, bị báo "Quá nhiều lần sai":** Javis khóa tạm để chống dò mật khẩu. Đợi ít phút rồi thử lại.
- **Bấm cập nhật nhưng báo "Đang cập nhật rồi, chờ chút.":** một lần cập nhật khác đang chạy. Chờ tiến trình chạy xong rồi thử lại.
- **Không thấy nút "⬆ Cập nhật ngay":** bạn đang chạy Docker mà Watchtower chưa chạy. Khung Cập nhật nói rõ máy bạn thiếu gì. Trên VPS tự quản, chạy `docker compose --profile update up -d` một lần rồi tải lại trang - `docker compose up -d` thường lệ KHÔNG bật Watchtower vì nó nằm trong profile riêng. Trên Hostinger thì không bật được, dùng Redeploy.
- **Mở đúng cổng nhưng không thấy app:** kiểm tra địa chỉ có đúng `http://localhost:7777` (hoặc IP VPS kèm cổng 7777) không. Nếu vừa sửa code, khởi động lại server rồi thử lại.

Còn vướng, xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

## Liên quan

- [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) - việc đầu tiên nên làm sau khi thiết lập xong.
- [Models & engine](10-models-va-engine.md) - chi tiết từng nhà cung cấp và cách đổi model.
- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - đấu nguồn dữ liệu vào trang **Kết nối**.
- [Plugins](20-plugins.md) - thêm công cụ native cho mọi engine.
- [Việc / Kanban](21-viec-kanban.md) - giao việc chạy nền một lần.
- [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) - việc lặp theo chu kỳ và nhắc theo giờ.
- [Tự học](22-tu-hoc.md) - hợp nhất bộ nhớ và soát sức khoẻ Wiki.
- [Mức dùng: token & chi phí](23-muc-dung-token.md) - xem token đã tiêu theo ngày và theo nhà cung cấp.
- [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - siết quyền truy cập trước khi đưa lên VPS.
