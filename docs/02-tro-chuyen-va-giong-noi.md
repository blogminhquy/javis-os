# Trò chuyện & giọng nói

***Tiếng Việt** · [English](en/02-chat-and-voice.md)*

Đây là chỗ bạn làm việc với Javis nhiều nhất: gõ chữ thì Javis trả lời bằng chữ, bấm mic gọi Javis thì nó nói thành tiếng. Trang này mô tả toàn bộ khung chat, từ phím tắt, lệnh gạch chéo, nút bấm dưới mỗi tin nhắn cho tới cách chọn giọng đọc và nhờ Javis tạo ảnh.

Nếu chưa cài đặt xong lần đầu, xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) trước.

## Tính năng này là gì

Một chỗ duy nhất để làm việc với Javis:

- Gõ tin nhắn như chat bình thường.
- Bấm mic để gọi Javis, nói chuyện như gọi điện thoại; Javis tự gửi khi bạn ngừng nói.
- Javis trả lời bằng chữ; trong cuộc gọi thì Javis nói thêm thành tiếng.
- Đính kèm file hoặc ảnh vào tin nhắn để Javis đọc.
- Javis nhúng ngược ảnh, file, sơ đồ và trang HTML vào câu trả lời để bạn xem tại chỗ.
- Xem quả cầu tri thức phản ứng theo âm thanh (sáng lên khi nghe / khi đọc).

Câu trả lời do **engine bạn đang chọn** xử lý chứ không mặc định là Claude: Claude Code, ChatGPT (Codex), OpenRouter, OpenAI API, Anthropic API hay Google Gemini API. Badge nhỏ cạnh chữ HỘI THOẠI cho biết engine + model THẬT vừa chạy lượt đó. Mọi engine đều gọi được công cụ và nguồn dữ liệu của Javis qua MCP Hub, không riêng Claude. Chi tiết ở [Models & engine](10-models-va-engine.md).

Trong lúc Javis suy nghĩ, một chip hoạt động hiện ngay cuối khung chat với ba chấm nhún, dòng trạng thái ("Javis đang suy nghĩ...", "✓ Nhận data - đang phân tích...", "✍ Đang soạn câu trả lời...") và đồng hồ đếm giây (số giây chỉ hiện từ giây thứ 3 trở đi).

## Mở ở đâu trong Javis

Có **hai** chỗ chat, dùng chung một cuộc hội thoại nên chuyển qua lại không mất gì.

### Màn chính "Javis"

Rail điều hướng bên trái, nhóm **Trợ lý** → mục **Javis**. Đây cũng là màn hình mặc định khi mở dashboard (mặc định ở cổng 7777), mở trang lên là đã ở đây.

| Khu vực | Vị trí | Nội dung |
|---|---|---|
| VAULT | Cột trái | Cây thư mục của brain đang chọn, ô **Tìm note...**, hai chế độ lọc **Tên** / **Nội dung**, ba nút **＋** (tạo file), **📁** (tạo thư mục), **⟳** (làm mới cây) |
| Đồ thị tri thức + trạng thái | Chính giữa | Mạng ghi chú, dòng chữ trạng thái (SẴN SÀNG, ĐANG NGHE...), dải số **AGENTS** / **SKILLS** / **WORKFLOWS** ở đáy |
| HỘI THOẠI | Cột phải | Lịch sử chat, badge engine, nút **⛶** sang trang Trò chuyện |
| Thanh model | Ngay trên thanh nhập | Chip chọn model + Effort, dải **HỆ THỐNG** và **MCP** đang dùng |
| Thanh nhập liệu | Dưới cùng | Nút mic, nút kẹp file, ô gõ chữ, nút gửi (đang chạy thì thành nút dừng) |

Cột trái **không còn** bảng thẻ số liệu kinh doanh; đó là Vault explorer, bấm một note là mở ra sửa ngay trên màn hình (xem [Quản lý tệp tin](05-quan-ly-tep-tin.md)). Bấm vào số AGENTS / SKILLS / WORKFLOWS thì nhảy thẳng sang trang tương ứng trong nhóm **Năng lực**.

### Trang "Trò chuyện" riêng

Rail, nhóm **Trợ lý** → mục **Trò chuyện**. Đây là một trang chat toàn màn hình, không có quả cầu và không có cây vault:

- Cột trái là **lịch sử hội thoại** (mở lại, tìm, đổi tên, xoá phiên cũ).
- Thanh trên cùng ghi **Trò chuyện với Javis**, bên phải là badge engine.
- Phần chat, chip file đính kèm, thanh model và thanh nhập là **chính** những thứ ở màn Javis được mượn sang, nên tin nhắn, file đang đính kèm và lượt đang chạy vẫn nguyên vẹn.

Dùng trang này khi bạn muốn màn hình rộng chỉ để chat. Muốn xem quả cầu và cây thư mục thì quay lại mục **Javis**.

## Cách dùng (từng bước)

### Bước 1 - Gõ chữ để hỏi

1. Bấm vào ô nhập ở dưới cùng (chỗ ghi "Nói với Javis, gõ ở đây, hoặc kéo/dán file vào...").
2. Gõ câu hỏi.
3. Nhấn phím **Enter** để gửi. Muốn xuống dòng trong cùng một tin nhắn thì nhấn **Shift + Enter**.
4. Hoặc bấm nút gửi (hình mũi tên) ở góc phải thanh nhập.

Câu trả lời của Javis hiện dần ở cột HỘI THOẠI bên phải, chữ chạy ra theo thời gian thực.

### Bước 2 - Gọi Javis bằng giọng: bấm nút mic

Nút mic (hình micro to, bên trái thanh nhập) là nút **gọi Javis**, như gọi điện thoại:

1. Bấm nút mic một lần. Nút đổi màu đỏ thành **Cúp máy**, và một **thanh gọi** hiện ngay trên khung chat: tên đường gọi (ví dụ **ChatGPT Live**), trạng thái (Đang nghe, Javis đang nói, Đang làm việc, Đang chờ), đồng hồ cuộc gọi, nút **Tắt mic** và nút **Cúp máy**.
2. Cứ nói tự nhiên. Lời hai bên hiện thành bong bóng chat như tin thường, nên bảng số, file hay kết quả việc vẫn hiện đầy đủ.
3. Muốn chen ngang lúc Javis đang nói thì cứ nói, Javis dừng lại nghe.
4. Kết thúc: bấm **Cúp máy** (trên thanh gọi hoặc chính nút mic), hoặc nhấn **Esc**.

Javis tự chọn đường gọi: **ChatGPT Live** khi bạn đã nối gói ChatGPT, rồi Live qua API key nếu có, không thì đường **Cơ bản** (nghe bằng trình duyệt, đọc bằng giọng Edge). Nếu ChatGPT Live chưa mở được, cuộc gọi tự chuyển sang đường Cơ bản và báo một dòng. Phím Cách (Space) không còn mở mic.

Lần đầu bấm mic, trình duyệt sẽ hỏi quyền dùng micro. Bấm cho phép. Nếu từ chối, Javis không nghe được và sẽ báo cần cấp quyền microphone cho trang này.

Trong cuộc gọi, khi bạn bắt đầu nói thì Javis **tạm dừng** phần nó đang đọc để lắng nghe. Nếu trong 2 giây bạn thật sự nói thành câu, Javis dừng hẳn và tin kế tiếp của bạn mang theo câu nó đang đọc dở, nên nó trả lời tiếp từ chỗ đó chứ không đọc lại từ đầu. Nếu chỉ là tiếng ho hay tiếng động, Javis đọc tiếp từ chỗ dừng. Cơ chế đo độ to của giọng qua luồng mic đã khử vọng (nói liên tục khoảng 0,5 giây, to hơn hẳn nền), nên tiếng loa của chính Javis không tự làm nó ngắt lời. Cơ chế này luôn bật.

Chen ngang chỉ hoạt động khi **mic đang mở**. Mic đã tắt thì dù Javis đang đọc, một tiếng động trong phòng cũng không bật mic trở lại.

### Nói "khoan", "thôi": Javis hiểu

- **"Khoan"**, **"đợi chút"**, **"từ từ"**, **"để mình nghĩ"** (hoặc "wait", "hold on"): Javis không gửi gì, dừng đọc nếu đang đọc, và hiện **ĐANG CHỜ BẠN**. Nói tiếp câu thật là nó gửi bình thường. Im lặng 90 giây thì nó thôi chờ.
- **"Thôi"**, **"dừng lại"**, **"đủ rồi"** (hoặc "stop"): đang đọc thì im ngay, đang suy nghĩ thì bấm hộ nút Dừng. Không gửi gì.
- Chỉ những câu **ngắn đúng cụm đó** mới được hiểu là lệnh. "Khoan, mở Chrome" là một tin nhắn bình thường.

Javis cũng tự chờ lâu hơn khi câu bạn nói kết bằng "và", "nhưng", "thì" hay dấu phẩy, vì lúc đó bạn thường chưa nói xong. Còn lại, Javis gửi câu sau 1,2 giây im lặng; mức bạn đã chọn ở bản cũ trên máy đó vẫn được dùng.

### Điều khiển Javis và máy tính bằng lời

Nói (hoặc gõ) là được, Javis dùng đúng công cụ và báo lại kết quả thật:

- **"Mở trang Việc"**, **"mở file tên X"**, **"cho xem việc vừa giao"**, **"cuộn xuống"**: dashboard tự mở đúng chỗ và Javis nói "đã mở". Việc này chỉ chạy khi có một tab Javis đang mở.
- **"Mở Chrome"**, **"bật Excel lên"**, **"mở trang youtube.com"**, **"tắt Chrome"**, **"đang mở app nào"**: Javis mở hay đóng app trên **chính máy đang chạy Javis**. Đóng app là đóng lịch sự (app có tài liệu chưa lưu sẽ tự hỏi lưu); nói "ép tắt" thì Javis tắt hẳn. Nếu Javis chạy trong Docker trên máy chủ thì nó nói rõ là không điều khiển được máy bạn.
- Đang bôi đen một đoạn chữ rồi nói "tóm tắt đoạn này": Javis biết bạn đang chỉ đoạn nào, không hỏi lại.

### Bước 3 - Nghe Javis trả lời bằng giọng

Trong cuộc gọi, Javis **nói thành tiếng** mọi câu trả lời. Đồ thị sáng theo nhịp giọng nói.

- Cúp máy (nút **Cúp máy**, nút mic hoặc **Esc**) là Javis im ngay.
- Gõ chữ ngoài cuộc gọi thì Javis chỉ trả lời bằng chữ.
- Không còn nút loa hay công tắc bật tắt giọng riêng: cuộc gọi quyết định Javis có nói hay không.

Đổi giọng ở **Cài đặt → Giọng nói**, xem mục **Cài đặt Giọng nói** bên dưới.

### Bước 4 - Dừng khi Javis đang trả lời

Khi Javis đang suy nghĩ hoặc đang đọc, nút gửi ở thanh nhập biến thành **nút dừng** (hình vuông). Bấm nút đó là ngắt lượt đang chạy và dừng đọc ngay, trạng thái về SẴN SÀNG. Gõ **`/stop`** rồi Enter cũng ra đúng kết quả đó.

**Phím Esc là cúp máy, không dừng câu trả lời.** Esc tắt mic và tắt giọng, còn câu trả lời vẫn được viết tiếp và hiện thành chữ. Esc cũng đóng popup đang mở. Chú thích trên nút dừng vẫn ghi "(Esc)" là chữ sót lại từ bản cũ.

Nút dừng chỉ dừng **phiên bạn đang xem**; phiên khác đang chạy nền vẫn tiếp tục. Xem [Phiên hội thoại](04-phien-hoi-thoai.md).

## Lệnh gạch chéo "/" trong ô chat

Gõ dấu **`/`** là một menu lệnh hiện lên ngay phía trên ô gõ - **ở đầu ô nhập hay giữa câu đều được**.

Ba lệnh phiên đứng đầu danh sách:

| Lệnh | Tên trong menu | Làm gì |
|---|---|---|
| `/new` | Hội thoại mới | Bắt đầu cuộc trò chuyện mới |
| `/reset` | Reset phiên | Xoá ngữ cảnh, bắt đầu lại |
| `/stop` | Dừng | Dừng lượt đang trả lời |

Trên bản web, `/new` và `/reset` cùng mở một hội thoại mới.

Ngay bên dưới là **mười hai lệnh hệ thống** (xem mục tiếp theo), rồi tới **toàn bộ skill của brain đang chọn**, mỗi dòng gồm `/slug`, tên skill và một dòng mô tả.

Cách điều khiển menu:

- Gõ tiếp vài chữ để lọc dần. Ưu tiên khớp theo slug trước, rồi mới tới tên skill.
- **Mũi tên lên / xuống** để chọn dòng, **Enter** hoặc **Tab** để chốt, **Esc** để đóng menu. Bấm chuột vào một dòng cũng được.
- Chọn một **lệnh phiên** hay một **lệnh hệ thống không cần nội dung kèm** thì nó chạy ngay, không cần Enter. Riêng `/plan` và `/goal` cần bạn gõ thêm nội dung, nên chọn chúng chỉ điền `/plan ` hay `/goal ` vào ô.
- Chọn một **skill** thì `/slug ` được chèn **đúng chỗ con trỏ**, chữ đã gõ hai bên giữ nguyên; bạn gõ tiếp rồi Enter để gửi.

Khi gửi một lệnh skill, Javis dịch câu đó thành lời nhắc: "Hãy dùng skill `<slug>` với yêu cầu: ... Nếu không có skill tên này thì cứ xử lý yêu cầu của tôi bình thường."

### Gọi skill ở giữa câu

Không phải lúc nào cũng nghĩ ra skill trước rồi mới viết. Cứ viết yêu cầu trước, tới đâu cần thì gõ `/` tới đó: *"test sử dụng skill giữa khung chat `/notes`"* chạy skill `notes` với yêu cầu là **phần chữ còn lại**. Chữ đứng trước và sau lệnh đều được gộp vào yêu cầu, nên *"viết cho anh `/notes` về cuộc họp"* thành yêu cầu "viết cho anh về cuộc họp".

Vài luật cho khỏi bắt nhầm:

- Dấu `/` phải đứng **đầu câu hoặc ngay sau khoảng trắng**. Nhờ vậy `https://vd.com/notes` và `3/4 cái bánh` không bị hiểu thành lệnh.
- Ở giữa câu, tên lệnh phải là **skill có thật** trong brain đang chọn. `/home/user/notes` hay `/khong-co-that` cứ đi thẳng vào chat như chữ thường.
- Có nhiều lệnh trong một câu thì lấy cái **cuối cùng** (ý định mới nhất). Riêng lệnh đứng ngay đầu ô nhập luôn được ưu tiên tuyệt đối.
- **Ba lệnh phiên (`/new`, `/reset`, `/stop`) và mười hai lệnh hệ thống chỉ chạy khi đứng ở đầu ô nhập**, và menu cũng không gợi ý chúng ở giữa câu - viết nửa câu rồi lỡ bấm `/reset` mà mất sạch ngữ cảnh thì hại hơn tiện. Skill nào tình cờ trùng tên với một lệnh hệ thống thì ở đầu ô nhập lệnh thắng, còn giữa câu skill vẫn gọi được như cũ.

Chi tiết về skill xem [Skills](06-skills.md).

### Lệnh hệ thống

Đây là các lệnh do **chính Javis xử lý**, không mượn lệnh có sẵn của Claude Code, nên chạy giống hệt nhau dù bạn đang dùng bộ não nào (Claude Code, ChatGPT, Grok, Antigravity hay một engine API). Kết quả hiện thành một bong bóng có viền màu ngay trong khung chat; bong bóng này chỉ ở trên màn hình của bạn, không gửi cho model và không lưu vào hội thoại.

| Lệnh | Làm gì |
|---|---|
| `/help` | Liệt kê các lệnh phiên và lệnh hệ thống |
| `/status` | Bộ não và model đang chạy cho hội thoại này (đã ghim riêng hay theo model chính), brain, số tin, mức ngữ cảnh gần nhất, có đang trả lời không, phiên bản |
| `/model` | Mở bảng chọn model. Gõ `/model tên-model` để đổi thẳng: tên khớp đúng thì đổi ngay, khớp nhiều model thì Javis liệt kê cho bạn chọn chứ không đoán |
| `/brain` | Liệt kê các brain. Gõ `/brain tên` để chuyển (tên khớp nhiều brain thì Javis hỏi lại) |
| `/retry` | Gửi lại câu bạn hỏi gần nhất |
| `/usage` | Token và chi phí Javis đã đo hôm nay và từ trước tới nay, kèm số dư OpenRouter nếu có key |
| `/tasks` | Việc nền đang chạy, chờ bạn duyệt, bị kẹt, đang xếp hàng. Có cảnh báo nếu "Tự vận hành" đang tắt (khi đó việc chỉ nằm chờ) |
| `/compact` | Nén hội thoại dài ngay, xem bên dưới |
| `/plan việc-cần-làm` | Một lượt chỉ đọc và đề xuất, chưa làm gì ra ngoài |
| `/memory` | Mục lục bộ nhớ dài hạn của brain đang chọn, bấm được vào từng ghi nhớ |
| `/export` | Tải hội thoại này về thành file markdown |
| `/goal mục-tiêu` | Javis tự làm tiếp cho tới khi đạt mục tiêu, xem bên dưới |

#### `/compact` - nén hội thoại

Hội thoại càng dài thì mỗi lượt càng tốn token và càng dễ loãng. Javis vẫn tự nén khi vượt ngưỡng lớn; `/compact` cho bạn nén **ngay** mà không đợi. Cách nén tuỳ bộ não của hội thoại, và Javis luôn nói đúng nó đã làm gì:

- **Engine API** (OpenRouter, OpenAI, Claude API, Gemini, Groq): các tin cũ được gấp vào một bản tóm tắt, chỉ giữ nguyên hai lượt hỏi đáp gần nhất. Từ lượt sau Javis gửi bản tóm tắt thay cho cả lịch sử.
- **Engine chạy bằng gói thuê bao** (Claude Code, ChatGPT/Codex, Grok): phần phình to nằm trong mạch mà engine tự giữ (kết quả công cụ, vòng lặp bên trong), không nằm trong lịch sử Javis lưu. `/compact` bỏ mạch đó đi; lượt sau Javis mở mạch mới và nạp lại lịch sử đã lưu. Không có bước tóm tắt vì gói thuê bao không có API key để gọi riêng một request tóm tắt.
- Hội thoại dưới 4 tin, hoặc bộ não không giữ mạch riêng (Antigravity dựng lại từ lịch sử ở mỗi lượt), thì Javis nói thẳng là chưa có gì để nén.
- Hội thoại đang trả lời thì bị từ chối: nén giữa chừng là đổi lịch sử ngay dưới chân một lượt đang đọc nó.

#### `/plan` - chỉ lập kế hoạch

Gõ `/plan dọn lại kho hàng cuối tháng`: Javis đọc dữ liệu cần thiết rồi đưa ra một kế hoạch ngắn (mục tiêu, các bước, việc nào cần bạn duyệt, rủi ro) và hỏi bạn có muốn làm theo không. Lượt đó **chưa được** ghi file, gửi tin, đăng bài, tạo đơn, sửa quảng cáo, xếp việc nền hay đặt nhắc hẹn. Bạn đồng ý ở tin sau thì Javis mới làm thật.

Mức chặn khác nhau theo bộ não, nên nói cho rõ: với **Claude Code, Grok và Antigravity**, lượt `/plan` chạy ở mức quyền `suggest` nên cổng công cụ chặn thật mọi hành động ra ngoài. Với **ChatGPT (Codex) và các engine API**, hiện chỉ có lời dặn trong tin gửi đi chứ chưa có cổng chặn riêng cho từng lượt.

#### `/goal` - làm tới khi đạt

Gõ `/goal mọi đơn hôm nay đã được đối soát xong`. Javis làm một vòng, tự kiểm tra bằng dữ liệu thật xem mục tiêu đã đúng chưa, và nếu chưa thì **tự gửi vòng kế tiếp** mà bạn không phải nhắc. Mỗi vòng có một dòng ghi chú ngắn nói còn thiếu gì.

Javis đề xuất "xong hay chưa", còn **việc có chạy tiếp hay không do mã quyết định**, để một mục tiêu không bao giờ đạt được không thành vòng lặp đốt token vô hạn. Vòng tự động dừng khi:

- mục tiêu đã đạt;
- đã chạy **8 vòng** mà chưa đạt;
- hai vòng liền báo còn thiếu y hệt nhau (không có tiến triển);
- Javis hỏi ngược bạn một câu cần bạn quyết;
- một vòng bị lỗi, hoặc Javis không báo được mục tiêu đã đạt hay chưa;
- **bạn gõ một tin mới, bấm Dừng, mở hội thoại khác hoặc gõ `/goal clear`** - lời của bạn luôn lên trước.

Chế độ này chạy trong **tab chat đang mở**: đóng tab hay tải lại trang thì dừng. Khác với `/plan`, `/goal` làm việc thật (đúng quyền hạn bạn đã cấp cho Javis), nên hãy viết mục tiêu cụ thể, kiểm chứng được.

#### Trên Telegram

Telegram có sẵn `/status`, `/model`, `/brain`, `/retry`, `/skills`, `/agents`, `/workflows`, `/reset`, `/stop` từ trước. Nay có thêm `/usage`, `/tasks`, `/memory` và `/plan việc-cần-làm`, cùng cách hoạt động, trả lời bằng chữ thường. Trên Telegram `/plan` chỉ có lời dặn (chưa có cổng chặn ở hub); `/compact`, `/goal`, `/export` chỉ có trên web.

## Khi Javis hỏi lại bằng nút bấm

Khi phải đoán một tham số mà đoán sai thì hại (kỳ thời gian, chọn shop nào, chọn kênh nào), Javis hỏi lại và đính một hàng nút bấm ngay dưới bong bóng trả lời:

- Một dòng câu hỏi, có thể kèm nhãn chủ đề ngắn ở đầu.
- Tối đa **4 nút** lựa chọn, cộng một nút **"Ý khác…"**.
- Bấm một nút = gửi **đúng chữ trên nút** đi như tin nhắn của bạn. Bấm "Ý khác…" thì không gửi gì, chỉ đặt con trỏ về ô gõ để bạn tự viết.
- Nhãn dài quá 40 ký tự bị cắt bớt và có dấu "…" ở cuối; nút hiện chữ gì thì gửi đi đúng chữ đó, không bao giờ khác.

Chỉ hàng nút **mới nhất** bấm được. Khi bạn trả lời (bấm nút hoặc gõ tay), mọi hàng nút cũ bị đông cứng, cuộn ngược lên bấm cũng không ăn gì. Javis luôn viết câu hỏi thành lời trong phần trả lời, nên bạn gõ tay được mà không cần bấm nút.

## Gửi file kèm trong chat

Bạn có thể đưa file hoặc ảnh vào tin nhắn để Javis đọc. Ba cách:

1. Bấm nút **kẹp giấy** (bên cạnh nút mic) rồi chọn file. Có thể chọn nhiều file.
2. **Kéo - thả** file từ máy vào cửa sổ Javis (một lớp phủ hiện lên báo chỗ thả).
3. **Dán** trực tiếp bằng Ctrl + V.

Chuyện dán có một mẹo riêng: dán **ảnh** thì thành file đính kèm như thường, còn dán **văn bản quá dài** (trên 1500 ký tự hoặc trên 25 dòng) vào ô chat thì Javis tự đóng gói thành file `.txt` đính kèm thay vì nhồi nguyên bài vào ô gõ. Javis vẫn đọc trọn vẹn, còn màn hình chỉ hiện một thẻ gọn. Việc này chỉ áp dụng cho ô chat; dán vào các ô nhập khác vẫn ra chữ bình thường.

File hiện thành thẻ nhỏ phía trên thanh nhập. Đợi thẻ báo tải xong, sau đó gõ hoặc nói yêu cầu rồi gửi như bình thường. Bấm dấu ✕ trên thẻ để bỏ file khỏi tin nhắn.

Quan trọng về cách Javis xử lý file:

- **Mặc định: chỉ đọc.** Javis đọc nội dung file (ảnh thì xem và mô tả) rồi trả lời, **không** tự lưu vào đâu. Nhãn trên lớp phủ kéo thả ghi "Thả file vào đây → lưu vào Sources" là chữ cũ, hành vi thật là chỉ đọc.
- **Chỉ lưu khi bạn yêu cầu rõ.** Muốn Javis cất file vào bộ nhớ (Second Brain), hãy nói rõ trong tin nhắn, ví dụ "lưu vào source", "ingest cái này", hoặc "ghi vào second brain". Khi đó Javis mới chuyển file thành ghi chú và lưu vào thư mục Sources của vault. Xem thêm [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) và [Quản lý tệp tin](05-quan-ly-tep-tin.md).

## Thẻ "đang mở": file bạn đang sửa tự thành đầu vào của cuộc trò chuyện

Ngoài file đính kèm, còn một loại thẻ nữa: khi bạn mở một file văn bản trong trình sửa (xem [Quản lý tệp tin](05-quan-ly-tep-tin.md)), Javis tự ghim file đó vào khung chat thành một thẻ màu cam ghi "đang mở - bấm để sửa tiếp".

Khác thẻ đính kèm ở chỗ: chỉ có **một** thẻ ghim (mở file khác thì đổi theo), và nó **không mất sau khi gửi** - file đó là đầu vào của cả cuộc trò chuyện chứ không phải dữ liệu kèm một lần. Nhờ vậy bạn nói "dọn lại phần quá hạn" hay "viết thêm phần kết" mà không cần nhắc tên file, Javis vẫn biết đang nói về file nào và ghi thẳng vào đó.

Thẻ ghim còn là **lối quay lại**: bấm vào thẻ là file mở lại trong trình sửa đúng chỗ đang làm dở (đang mở sẵn thì chỉ đưa mắt về, không nạp lại nên chữ chưa lưu vẫn còn). Bấm **✕** trên thẻ để bỏ ghim.

## Javis hiện ảnh, file và artifact trong câu trả lời

Chiều ngược lại cũng có: Javis đưa được ảnh và file trong brain vào thẳng câu trả lời.

- **Ảnh**: Javis viết `![mô tả](attachments/ten-anh.png)` và dashboard vẽ ra ảnh thật trong bong bóng chat. Bấm vào ảnh là mở đúng vị trí file đó trong trang **Tệp tin**.
- **File khác** (pdf, docx, xlsx...): Javis viết link markdown, bấm vào mở file trong trang Tệp tin.
- **Đường dẫn trong dấu nháy ngược** kiểu `Javis/loops/bao-cao-sang.md` cũng tự thành link mở file.
- **Wikilink** `[[Tên note]]` thành link điều hướng kiểu Wikipedia, bấm vào là Javis đi tìm đúng note trong vault rồi mở ra.
- Ảnh **không tải được nữa** (đã hết hạn trong vùng cache, bị xoá tay hoặc đổi tên) hiện thành một ô xám ghi **"Ảnh đã hết hạn"** thay cho icon vỡ. Thư mục `attachments/` và `inbox/` của brain là vùng cache: hết hạn 30 ngày hoặc chạm trần 300MB thì bị dọn.

### Khối artifact

Nội dung dài hoặc xem được bằng mắt sẽ không đổ tràn vào khung chat mà gom thành một **thẻ artifact** gọn:

| Loại | Thẻ ghi | Khi nào thành artifact |
|---|---|---|
| Trang HTML | Trang HTML | Khối ```` ```html ```` hoặc nội dung mở đầu bằng `<!doctype html>` / `<html>` |
| Ảnh SVG | Anh SVG | Khối ```` ```svg ```` hoặc mở đầu bằng `<svg` |
| Sơ đồ mermaid | So do | Khối ```` ```mermaid ```` |
| Mã nguồn dài | Ma + tên ngôn ngữ | Khối code từ 24 dòng hoặc từ 800 ký tự trở lên |

Thẻ ghi thêm số dòng và chữ "bam de xem", bên phải là nút **Mo ▸**. Bấm vào thẻ, một panel mở ra bên phải màn hình với:

- Hai tab **Xem truoc** và **Ma nguon** (mã nguồn dài thì chỉ có tab mã nguồn).
- Nút **⧉** copy mã nguồn, nút **⇩** tải về thành file, nút **✕** đóng panel.
- Nhấn **Esc** cũng đóng panel.

Sơ đồ mermaid cần tải thư viện vẽ từ mạng; đang offline thì panel báo không tải được thư viện và hiện thẳng mã nguồn. Khối ```` ```dataview ```` và ```` ```tasks ```` không thành artifact mà chạy thành bảng kết quả, xem [Task & Dataview trong note](19-task-va-dataview.md).

## Nhờ Javis tạo ảnh mới

Javis tạo được ảnh ngay trong chat bằng chính **gói ChatGPT bạn đã đăng nhập** (OAuth), không cần mua thêm OpenAI API key. Cứ nói bằng lời, ví dụ "tạo cho anh ảnh chai nước mắm đặt trên bàn gỗ, nền tối, ảnh ngang".

Bên dưới, Javis gọi tool `javis_generate_image` (thuộc plugin đi kèm app `image-chatgpt`) với ba tham số:

| Tham số | Giá trị | Mặc định |
|---|---|---|
| `prompt` | Mô tả ảnh, càng rõ càng tốt (bắt buộc) | không có |
| `aspect_ratio` | `square` (1024x1024), `landscape` (1536x1024), `portrait` (1024x1536) | `square` |
| `quality` | `low`, `medium`, `high` | `medium` |

Ảnh sinh ra được lưu vào thư mục `attachments/` của brain đang chọn, rồi Javis nhúng ngay `![...](attachments/...)` vào câu trả lời để bạn xem tại chỗ. Vì `attachments/` là vùng cache hết hạn sau 30 ngày, ảnh nào bạn muốn giữ lâu thì chép sang thư mục khác trong brain.

Vài điều cần biết:

- **Phải kết nối ChatGPT trước.** Chưa kết nối thì tool trả lời thẳng "Chưa kết nối ChatGPT (OAuth)." kèm hướng dẫn vào trang **Models** đăng nhập ChatGPT. Xem [Models & engine](10-models-va-engine.md).
- Tạo ảnh là thao tác mức `safe` (ghi file + tiêu quota), nên việc nền đang chạy ở chế độ chỉ-đọc sẽ không tự tạo ảnh.
- Ảnh do AI sinh ra mang sẵn dấu nguồn gốc (Content Credentials). Trong **Cài đặt → Giao diện & Brain → Dấu nguồn gốc ảnh AI** có hai nút **Giữ dấu** / **Gỡ dấu**; mặc định là giữ.
- Ngoài chat, còn gọi trực tiếp được qua `POST /image/generate` với các trường `prompt`, `aspect_ratio`, `quality`, `brain`.

## Tóm tắt video YouTube

Dán link video vào ô chat rồi nói bạn muốn gì, ví dụ "tóm tắt video này giúp mình" hoặc "video này có nói gì về giá không". Javis đọc **phụ đề** của video rồi trả lời dựa trên lời thoại thật, kèm mốc thời gian cho từng ý chính.

Nhận mọi kiểu link: `youtube.com/watch?v=...`, `youtu.be/...`, Shorts, link phát trực tiếp, link có kèm danh sách phát hay mốc thời gian, và cả link nằm lẫn trong câu bạn gõ.

Bên dưới, Javis gọi tool `javis_youtube_read` (plugin đi kèm app `youtube-read`). Đây là thao tác **chỉ đọc** nên việc nền ở chế độ chỉ-đọc cũng tóm tắt được video, và nó chạy trên **mọi engine** - kể cả sáu engine API vốn không tự mở được trang web.

Vài điều cần biết:

- **Video không có phụ đề thì không tóm tắt được.** Javis sẽ nói thẳng như vậy chứ không đoán nội dung từ tiêu đề. Phần lớn video tiếng Việt và tiếng Anh đều có phụ đề máy nghe, nhưng video vừa đăng vài phút thì phụ đề chưa kịp chạy xong.
- **Video riêng tư, giới hạn tuổi hoặc chặn theo vùng** cũng không đọc được, và Javis nói rõ lý do nào trong số đó.
- **Câu "YouTube nghi máy chủ này là robot" không phải lỗi video của bạn.** Gốc rễ là **danh tiếng địa chỉ IP**: YouTube đánh dấu dải IP của các nhà cung cấp máy chủ, nên cùng một video mở ở nhà thì được mà chạy trên VPS thì bị hỏi giấy. Javis tự đổi lần lượt qua tám kiểu trình phát rồi mới nhờ tới yt-dlp, nên phần lớn ca đó tự vượt. Gặp câu đó nghĩa là cả chín đường đều bị từ chối.
  - Thử lại sau vài phút thường là xong, vì YouTube siết theo đợt.
  - Lặp lại nhiều lần thì IP máy chủ đang bị đánh dấu nặng. Cách dứt điểm là đặt biến môi trường `JAVIS_YOUTUBE_PROXY` trỏ qua một proxy dân cư rồi khởi động lại, xem [Cấu hình .env](16-cau-hinh-env.md). Chỉ riêng lưu lượng YouTube đi qua đó.
- **Muốn biết chính xác đường nào hỏng** thì chạy ngay trên máy chủ:
  ```
  python server/youtube_read.py <link video>
  ```
  Nó thử từng đường một rồi in ra bảng: đường nào sống, đường nào chết, YouTube trả lý do gì, yt-dlp đã cài chưa. Một lần chạy là đủ để biết bệnh, khỏi đoán.
- **Video dài bị cắt bớt.** Một lần đọc lấy tối đa khoảng 40 nghìn ký tự lời thoại (đủ cho video 60-90 phút). Dài hơn thì Javis báo đã đọc tới phút mấy; bạn bảo "đọc tiếp" là nó đọc khúc sau.
- **Muốn phụ đề tiếng khác** thì nói ra, ví dụ "đọc bản tiếng Anh". Mặc định Javis ưu tiên phụ đề theo ngôn ngữ giao diện, sau đó tới tiếng Anh, và luôn chuộng bản do người làm hơn bản máy nghe vì bản người có dấu câu nên tóm tắt chuẩn hơn.
- Bản chép lời do máy nghe hay sai tên riêng và số liệu. Con số quan trọng thì nên mở video kiểm lại ở đúng mốc thời gian Javis dẫn.

## Hàng nút dưới mỗi tin nhắn

Rê chuột vào một tin nhắn (của bạn hay của Javis đều được) sẽ thấy một hàng nút nhỏ hiện ra bên dưới. Trên điện thoại thì **chạm** vào tin để hiện.

| Nút | Gợi ý khi rê chuột | Làm gì |
|---|---|---|
| Giờ gửi | Ngày đầy đủ, ví dụ "Thứ tư, 29/07/2026 14:05" | Chỉ để xem |
| ↻ | "Gửi lại câu này" (tin của bạn) hoặc "Trả lời lại câu hỏi phía trên" (tin của Javis) | Gửi lại đúng chữ gốc thành một lượt MỚI ở cuối hội thoại, không xoá gì của lượt cũ |
| ✎ | "Sửa lại rồi gửi" | Chỉ có ở tin của bạn. Đổ chữ gốc vào ô nhập để bạn sửa; **không** tự gửi |
| ⧉ | "Sao chép nội dung" | Copy cả tin nhắn, nút đổi thành "✓ Đã copy" trong giây lát |

Vài điểm hay gặp:

- Đang chạy một lượt thì nút ↻ mờ đi và không bấm được, tránh chồng lượt.
- Tin chỉ có ảnh mà không kèm chữ thì không có nút ↻ và ✎ (không có gì để gửi lại).
- Tin lưu từ trước bản có mốc giờ thì phần giờ được ẩn đi chứ không lấy giờ hiện tại đắp vào.
- Tin **dài** của bạn (trên 10 dòng hoặc trên 900 ký tự) được thu gọn, có nút **Xem thêm** / **Thu gọn** để mở ra đóng lại.
- Mỗi khối code có nút **⧉ Copy** riêng ở góc.
- Khi bạn đang cuộn lên đọc lại mà Javis trả lời tiếp, khung chat KHÔNG giật xuống; một nút **↓ Tin mới** hiện ở đáy để bấm nhảy xuống khi sẵn sàng.

## Chọn model, Effort và badge engine

Ngay trên thanh nhập có một dải riêng:

- **Chip model**: hiện tên rút gọn của nhà cung cấp và model đang dùng, kèm **Effort: Tắt / Thấp / Vừa / Cao** (độ sâu suy nghĩ). Bấm chip mở bảng chọn: ô **Tìm model...**, danh sách nhà cung cấp, mỗi cái bung ra danh sách model. Nhà cung cấp chưa cấu hình hiện ổ khoá 🔒 kèm dòng "+ Thêm API key ở trang Models để mở khoá". Hàng Effort nằm cuối bảng.
- **Dải HỆ THỐNG**: hai đèn trạng thái "⬤ Claude Code CLI" và "⬤ Voice (Edge TTS)".
- **Dải MCP**: các nguồn dữ liệu / công cụ Javis vừa gọi trong phiên. Chưa gọi gì thì ghi "Chưa có hoạt động". Xem [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md).

Badge cạnh chữ **HỘI THOẠI** (và ở góc phải trang Trò chuyện) hiện engine + model **thật** của lượt vừa chạy, lấy từ server chứ không phải model tự khai. Nếu badge khác cái bạn tưởng, tin badge.

Trên điện thoại, chip model dời lên header và bảng chọn mở ra giữa màn hình.

## Javis trình bày câu trả lời thế nào

Từ bản 0.26.9, câu trả lời trên khung chat web được viết cho **mắt đọc**, không phải cho tai nghe:

- Đoạn ngắn 2-4 câu rồi xuống dòng, thay vì mấy khối văn xuôi liền mạch.
- Liệt kê từ 3 ý trở lên thì gạch đầu dòng.
- **In đậm** con số, tên riêng và kết luận, tức là những thứ bạn lướt mắt tìm.
- Câu trả lời dài có nhiều phần rõ rệt thì mỗi phần một tiêu đề.
- Bảng khi so sánh cùng một bộ trường giữa nhiều mục, ví dụ doanh thu ba kênh theo tuần.

Trước đó Javis được dặn viết văn xuôi trơn vì Javis vốn hay được dùng bằng **giọng nói**. Nay không cần đánh đổi nữa: giọng đọc **tự bóc markdown** (tiêu đề, in đậm, gạch đầu dòng, link, khối mã) trước khi đọc thành tiếng, nên định dạng đẹp cho mắt không làm giọng đọc vấp.

Câu hỏi ngắn vẫn được trả lời bằng một câu. Định dạng là để dễ đọc, không phải để mọi câu trả lời trông như một bản báo cáo.

Các kênh chữ thuần thì siết hơn vì bản thân chúng không vẽ được: **Telegram** và **Zalo** không có bảng markdown, **terminal** thì không có bảng, ảnh nhúng lẫn link markdown. Cả ba vẫn dùng gạch đầu dòng bình thường. Xem [Telegram](11-telegram.md) và [CLI trong terminal](24-cli-terminal.md).

> Nếu Javis vẫn trả lời bằng văn xuôi dài: nhiều khả năng bộ nhớ dài hạn của brain còn một ký ức cũ kiểu "không thích bảng markdown, thích văn nói ngắn" từ thời bạn dùng bằng giọng nói, và ký ức đó được nạp vào **mọi** lượt chat. Mở `memory/MEMORY.md` trong trang **Tệp tin**, tìm dòng nói về cách trả lời rồi xoá dòng đó cùng file tương ứng trong `memory/facts/`. Xem [Second Brain, bộ nhớ & wiki](13-second-brain-bo-nho-wiki.md).

## Cài đặt Giọng nói

Mọi thứ về giọng nằm trong **Cài đặt → Giọng nói**. Trang chỉ còn một thẻ, ô nào cũng tự lưu ngay khi bạn đổi, không có nút Lưu.

Thẻ có ba thứ:

- **Dòng "Đang dùng: ..."**: đường gọi đang chạy là **ChatGPT Live**, **Live (tên hãng)** qua API key hay **Cơ bản**. Ở đường Cơ bản, dòng này nói thêm bộ não nào trả lời nhanh, ví dụ "Trả lời nhanh bằng Antigravity CLI (gói Google)".
- **Giọng Javis**: danh sách giọng đổi theo đường gọi, xem bên dưới.
- **Tập trung khi đàm thoại**: bật thì sau 20 giây im lặng, bạn phải gọi "Javis" mới nói tiếp được. Trong lúc chờ, Live tạm ngắt kết nối.

Khi Javis phải lùi xuống đường thấp hơn, dòng "Đang dùng" nói vì sao và cần làm gì, ví dụ nối ChatGPT ở trang **Models**, cài Codex CLI, hoặc cập nhật Codex CLI lên bản 0.153 trở lên.

### Giọng Javis

Danh sách giọng tuỳ đường gọi:

- **ChatGPT Live**: 9 giọng juniper (mặc định), maple, spruce, ember, vale, breeze, arbor, sol, cove. **▶ Nghe thử** phát một đoạn mẫu thu sẵn.
- **Live qua API key**: các giọng của hãng đang dùng, không có nút nghe thử.
- **Cơ bản**: 7 giọng Edge miễn phí là Emma (mặc định), Hoài My, Nam Minh, Ava, Andrew, Brian, William. Có OpenAI API key ở trang **Models** thì có thêm 11 giọng OpenAI (alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse). Cuối danh sách là **Giọng ElevenLabs của bạn**. **▶ Nghe thử** đọc một câu mẫu.

Chọn giọng là chọn luôn nhà cung cấp (Edge, OpenAI hay ElevenLabs). Giọng Edge và tốc độ đọc được lưu trên chính thiết bị này; cập nhật không ghi đè giọng bạn đã chọn.

Nếu giọng trả phí gặp lỗi (hết hạn mức, sai key, mất mạng), Javis báo lỗi để bạn thử lại hoặc chọn giọng khác; không tự chuyển giọng.

### Nâng cao

- **Đường gọi**: **Tự động (khuyên dùng)**, **ChatGPT Live**, **Live qua API key** hoặc **Cơ bản**. Tự động thử lần lượt ChatGPT Live, Live qua API key, rồi Cơ bản. Chọn tay một đường chưa chạy được thì Javis dùng đường kế tiếp và nói lý do ở dòng "Đang dùng".
- **Tốc độ đọc**: từ 0,85× tới 1,45×, mặc định 1,10×. Chỉ hiện ở đường Cơ bản.
- **API key ElevenLabs** và **Voice ID** (lấy ở ElevenLabs → Voices): chỉ hiện khi bạn chọn giọng ElevenLabs. Để trống ô key là giữ key đã lưu.

Giọng OpenAI cần OpenAI API key ở trang **Models**; trang giọng nói không còn ô nhập key OpenAI.

### ChatGPT Live: gọi Javis qua gói ChatGPT

**ChatGPT Live** dùng gói ChatGPT bạn đã nối ở trang **Models**, không cần API key. Javis tự chọn đường này khi gói ChatGPT đã nối và máy có Codex CLI bản 0.153 trở lên, bạn không phải chọn gì.

- Bấm mic là bắt đầu nói chuyện: Javis nghe liên tục, đáp sau chưa tới một giây, bạn chen ngang lúc nào cũng được.
- Chuyện trò thì Javis đáp ngay. Câu cần dữ liệu thật hay hành động (doanh thu, lịch, email, file, mở trang) thì Javis nói một câu đệm kiểu "để xem nhé", giao bộ não chính bạn đã chọn (Claude hay bộ khác) làm với đủ MCP và tool, rồi đọc tóm tắt; bản đầy đủ (có bảng) hiện thành bong bóng trong khung chat. Lời Javis đọc tóm tắt không hiện thành bong bóng thứ hai.
- Trong lúc Javis đang làm mà bạn nói thêm kiểu "ok, xong thì báo anh nhé", Javis không làm lại từ đầu. Câu có ý mới (ví dụ "thêm cả số đơn huỷ nữa") được làm tiếp ngay sau việc đang chạy.
- Đổi giọng ở ô **Giọng Javis** (9 giọng, xem ở trên).
- Âm thanh đi thẳng từ trình duyệt tới OpenAI, nên chạy được cả khi Javis nằm trên VPS.
- Cuộc gọi tính vào hạn mức gói ChatGPT của bạn.

### Live qua API key

Chưa có ChatGPT Live thì Javis dùng **Gemini Live**, **OpenAI Realtime** hoặc **OpenAI GPT-Live**, bằng API key Gemini hay OpenAI bạn đã dán ở trang **Models**. Giọng có cảm xúc, ngắt lời tự nhiên, bản ghi chữ hai chiều hiện trong khung chat. Khi cần dữ liệu thật, model giao cho bộ não chính chạy nền rồi vẫn trò chuyện tiếp, có kết quả thì thuật lại (Gemini dòng 3.1 còn im chờ vì Google chưa hỗ trợ việc nền).

### Đường Cơ bản và trả lời nhanh

Đường Cơ bản nghe bằng trình duyệt và đọc bằng giọng bạn chọn. Câu nói thường được một bộ não giọng trả lời nhanh trong 1 đến 2 giây ("làn nhanh"). Javis tự lấy bộ não đầu tiên sẵn sàng trên gói bạn đã đăng nhập, theo thứ tự:

1. Antigravity CLI
2. ChatGPT (qua Codex)
3. Claude Code
4. Grok Build

Không có cái nào thì lượt nói đi thẳng bộ não chính. Câu cần số liệu, file, việc vẫn được giao cho bộ não chính, tất cả trong cùng một hội thoại. Bộ não giọng bạn đã chọn ở bản cũ vẫn chạy tiếp.

### Tai nghe lại: câu Việt xen tiếng Anh

Ở đường Cơ bản, trình duyệt chỉ nghe được một ngôn ngữ, nên câu như "Mở dashboard Facebook ads" hay bị chép thành "Mở double Facebook add". **Tai nghe lại** là một model đa ngôn ngữ nghe lại chính âm thanh câu bạn vừa nói rồi mới chốt chữ vào bong bóng. Chữ tạm của trình duyệt vẫn hiện tức thì trong lúc bạn nói.

- Javis luôn tự chọn tai: có key Groq ở trang **Models** thì dùng **Groq Whisper**, không có thì dùng chữ của trình duyệt như trước.
- Đo trên 20 câu lệnh Việt xen Anh: trình duyệt sai 41% số từ, qua tai Groq còn 14%. Mỗi câu mất thêm chừng 1 giây.
- Tai lỗi, chậm quá 8 giây, hay ra câu lệch hẳn bản nháp (Whisper đôi khi bịa câu khi gặp tiếng ồn) thì Javis giữ chữ của trình duyệt, không mất lượt nói.
- Câu gửi đi là chữ của tai nếu có tai, không thì là chữ của trình duyệt lúc bạn kết thúc câu. Đã gửi rồi thì AI không sửa lại tin trong lịch sử.

### Máy tự lo

Các ô dưới đây đã bỏ khỏi trang vì máy tự quyết được:

- **Đọc trả lời bằng giọng**: bỏ vì trùng với nút mic. Trong cuộc gọi Javis nói mọi câu trả lời; cúp máy (nút **Cúp máy**, nút mic hoặc **Esc**) là im. Chat gõ chữ ngoài cuộc gọi chỉ trả lời bằng chữ.
- **Ngôn ngữ nghe**: theo ngôn ngữ giao diện (giao diện tiếng Anh thì nghe `en-US`, còn lại `vi-VN`). Câu Việt xen tiếng Anh đã có tai nghe lại lo.
- **Im lặng rồi gửi**: cố định 1,2 giây. Mức bạn đã chọn ở bản cũ trên máy đó vẫn được dùng. Javis vẫn chờ lâu hơn sau "và", "nhưng", "thì" hay dấu phẩy, và nói "khoan", "đợi chút" vẫn làm Javis chờ.
- **Ngắt lời Javis bằng giọng**: luôn bật.
- **Nhịp hội thoại (thử nghiệm)**: bỏ hẳn.
- **Tai nghe lại**: máy luôn tự chọn, xem mục ở trên.
- **Chế độ nói chuyện** (Chuẩn, Làn nhanh, Live) và **Bộ não giọng nói**: thay bằng đường gọi, xem mục **Đường Cơ bản và trả lời nhanh**.
- **Từ hay nghe nhầm**: Javis tự dựng danh sách từ tên trợ lý và tên các MCP đã nối. Từ bạn đã lưu trước đó vẫn được dùng.

## Phóng to khung chat

Khi làm việc lâu trong chat ở màn **Javis**, bấm nút **⛶** ở góc mục HỘI THOẠI để sang thẳng trang **Trò chuyện** - khung chat toàn màn hình, cột trái là **lịch sử hội thoại** (mở lại/tìm/đổi tên/xoá phiên cũ - xem [Phiên hội thoại](04-phien-hoi-thoai.md)), cột phải là nội dung chat căn giữa cho dễ đọc, ô nhập cao hơn để gõ dài.

Về lại màn Javis: bấm nút **‹ Thu nhỏ** trên thanh tiêu đề của trang Trò chuyện.

Đây vẫn là **một cuộc trò chuyện duy nhất**: chat ở màn Javis hay ở trang Trò chuyện đều là cùng một mạch, cùng một thanh model, cùng chỗ đính file. Từ bản 0.12.4, nút phóng to không còn mở một lớp nổi riêng nữa - trước đây có hai khung chat trông gần giống nhau mà hành xử khác nhau, dễ nhầm.

## Hỏi số liệu kinh doanh

Bảng thẻ số liệu cố định ở cột trái đã được gỡ (từ bản 0.9.166). Trước đây mỗi lần mở dashboard là Javis lại tự chạy một lượt quét các nguồn đã kết nối để đắp bảng đó, tốn hạn mức mà phần lớn thời gian không ai nhìn tới.

Giờ muốn xem số thì cứ hỏi thẳng trong chat ("doanh thu hôm nay thế nào", "so với tuần trước"). Javis gọi đúng nguồn đang đấu (POS, kênh, quảng cáo...) và trả lời bằng lời, nên chỉ chạy khi bạn thật sự cần. Chi tiết về nguồn số liệu xem [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md).

## Dùng trên điện thoại

Dưới 860px chiều ngang, giao diện đổi hẳn cho vừa màn hình:

- Điều hướng thu thành ngăn kéo: bấm nút **☰** để mở, bấm nền mờ, chọn một mục hoặc nhấn Esc để đóng.
- **Chip model** và nút **+** (hội thoại mới) dời lên header.
- Nhóm **Hệ thống** (chọn brain, nút đổi tông sáng/tối, dải HỆ THỐNG và MCP) dời xuống đáy ngăn kéo điều hướng.
- Ô nhập rút gọn lời nhắc thành "Nói hoặc gõ cho Javis…".
- Nút **🕘 Lịch sử** ở header bị ẩn (trang **Trò chuyện** có sẵn lịch sử).
- Không có nút loa ở đâu cả: cuộc gọi bằng nút mic quyết định Javis có nói thành tiếng hay không.
- Không có chuột để rê, nên **chạm vào một tin nhắn** để hiện hàng nút của đúng tin đó; chạm ra chỗ khác thì ẩn đi.
- Trong trang **Trò chuyện**, nút **🕘** ở thanh tiêu đề mở/đóng ngăn lịch sử trượt từ trái.

## Ý nghĩa dòng chữ trạng thái giữa màn hình

Dòng chữ ngay dưới quả cầu cho biết Javis đang làm gì:

| Chữ hiện | Nghĩa |
|---|---|
| SẴN SÀNG | Đang nghỉ, chờ bạn |
| ĐANG NGHE | Đang nghe bạn nói |
| ĐANG NGHE • LUÔN | Đang trong cuộc gọi, mic mở liên tục |
| ĐANG SUY NGHĨ | Bộ não đang xử lý câu hỏi |
| ĐANG GỌI <tên tool> | Bộ não đang gọi một công cụ (POS, lịch, mở trang...) |
| ĐANG NÓI | Javis đang đọc câu trả lời |
| ĐANG CHỜ BẠN | Bạn vừa nói "khoan" / "đợi chút", Javis im chờ bạn nói tiếp |
| TẠM DỪNG, ĐANG NGHE BẠN | Nghi bạn chen ngang, Javis dừng đọc 2 giây xem bạn có nói thật không |
| ĐANG KẾT NỐI LẠI | Mất kết nối với máy chủ, đang nối lại |
| · MẠNG CHẬM | Hậu tố: một khúc giọng đọc mất hơn 2,5 giây mới phát được |
| · N VIỆC NỀN | Hậu tố: đang có N việc chạy nền ở trang Việc |

## Bảng tra nhanh nút và phím tắt

Nút quanh khung chat:

| Nút | Ở đâu | Làm gì |
|---|---|---|
| Mic to | Trái thanh nhập | Gọi Javis; trong cuộc gọi nút thành **Cúp máy** |
| Kẹp giấy | Cạnh nút mic | Chọn file đính kèm |
| Mũi tên | Phải thanh nhập | Gửi tin nhắn |
| Ô vuông | Thay nút gửi khi đang chạy | Dừng lượt đang trả lời + dừng đọc |
| ⛶ | Góc mục HỘI THOẠI | Phóng to khung chat |
| 🕘 Lịch sử | Góc trên phải | Mở khung chat rộng kèm lịch sử hội thoại |
| Badge engine | Cạnh chữ HỘI THOẠI | Engine + model thật của lượt vừa chạy |
| Chip model · Effort | Trên thanh nhập | Đổi nhà cung cấp, model và độ sâu suy nghĩ |

Phím tắt:

| Thao tác | Kết quả |
|---|---|
| **Enter** | Gửi tin nhắn đang gõ |
| **Shift + Enter** | Xuống dòng trong tin nhắn |
| **Ctrl + V** | Dán ảnh, hoặc dán văn bản dài thành file .txt đính kèm |
| **/** (đầu ô nhập) | Mở menu lệnh; ↑ ↓ chọn, Enter hoặc Tab chốt |
| **Esc** | Cúp máy (kết thúc cuộc gọi bằng giọng); đóng menu lệnh; đóng panel artifact. **Không** dừng câu trả lời |

## Mẹo

- Muốn nói dài nhiều câu mà không sợ Javis gửi sớm, gọi Javis (nút mic) và nói liền mạch; chỉ ngừng hẳn khi thật sự nói xong.
- Muốn im lặng đọc chữ: cúp máy rồi gõ, Javis chỉ trả lời bằng chữ.
- Đưa nhiều ảnh chụp màn hình cùng lúc bằng cách kéo - thả tất cả vào cửa sổ, Javis xử lý từng cái.
- Nếu bạn quen nói tiếng Anh, đổi ngôn ngữ giao diện sang tiếng Anh (**Cài đặt → Chung**): Javis nghe theo ngôn ngữ giao diện.
- Dán nguyên một bài dài vào ô chat cứ dán thoải mái: Javis tự biến thành file `.txt` đính kèm, khung chat vẫn gọn.
- Hỏi lại một câu đã hỏi mà muốn đổi vài chữ: bấm **✎** trên tin cũ, sửa trong ô nhập rồi gửi, khỏi gõ lại từ đầu.
- Nút **⛶** trên mục HỘI THOẠI và mục **Trò chuyện** trong nhóm Trợ lý dẫn tới cùng một chỗ, dùng đường nào tiện hơn thì dùng.

## Sự cố thường gặp

- **Trong chat hiện ra một câu bạn không hề gõ.** Gần như chắc chắn là mic nghe được tiếng trong phòng (nhạc, TV, người khác nói) rồi chép thành chữ và gửi luôn, vì câu nói xong là Javis gửi ngay chứ không hỏi lại. Nhìn dòng chữ giữa màn hình: còn **ĐANG NGHE** hay **ĐANG NGHE • LUÔN** nghĩa là mic vẫn mở, bấm nút mic hoặc **Esc** để tắt. Javis đang đọc thành tiếng cũng không tự bật mic lại khi bạn đã cúp máy. Xoá câu lạ đó thì bắt đầu một hội thoại mới; Javis không có cách nào tự gõ vào ô chat của bạn, mọi kết quả chạy nền đều hiện ở bong bóng bên trái.
- **Trình duyệt không nghe được.** Javis báo "Trình duyệt không hỗ trợ giọng nói. Dùng Chrome/Edge." Hãy mở dashboard bằng Chrome hoặc Edge.
- **Micro không hoạt động.** Trình duyệt chặn quyền micro. Vào phần quyền của trang trong trình duyệt và cho phép micro, rồi tải lại trang.
- **Nhấn Esc rồi mà câu trả lời vẫn hiện tiếp.** Đúng như thiết kế: Esc là cúp máy, tắt mic và tắt giọng, còn câu trả lời vẫn viết tiếp thành chữ. Muốn dừng hẳn lượt thì bấm nút dừng (ô vuông) trên thanh nhập hoặc gõ `/stop`.
- **Không nghe thấy Javis nói.** Javis chỉ nói thành tiếng trong cuộc gọi, nên bấm mic để gọi. Đang gọi mà vẫn im: kiểm tra âm lượng máy, rồi bấm "▶ Nghe thử" trong **Cài đặt → Giọng nói** để thử riêng phần đọc. Nếu dùng giọng OpenAI hoặc ElevenLabs, xem Javis có báo lỗi giọng không (hết hạn mức, sai key, mất mạng); Javis không tự chuyển sang giọng khác.
- **Gõ "/" mà không thấy menu.** Menu chỉ mở khi dấu "/" đứng đầu ô nhập và chưa có dấu cách theo sau. Nếu vẫn không có dòng skill nào, brain đang chọn chưa có skill nào bật.
- **Bấm nút lựa chọn của Javis mà không ăn gì.** Đó là hàng nút của lượt cũ, đã bị đông cứng khi bạn gửi tin mới. Cứ gõ câu trả lời bằng tay.
- **Ảnh trong hội thoại thành ô xám "Ảnh đã hết hạn".** File nằm trong vùng cache `attachments/` đã quá 30 ngày hoặc bị dọn do chạm trần 300MB. Nhờ Javis tạo lại, hoặc lần sau chép ảnh quan trọng sang thư mục khác trong brain.
- **Sơ đồ không vẽ ra, chỉ thấy mã.** Thư viện vẽ sơ đồ tải từ mạng; máy đang offline hoặc bị chặn. Nội dung vẫn còn nguyên ở tab mã nguồn.
- **Nhờ tạo ảnh thì báo chưa kết nối ChatGPT.** Vào trang **Models** đăng nhập ChatGPT (OAuth), không cần API key, rồi thử lại.
- **Câu trả lời trống.** Nếu ô trả lời hiện dòng gợi ý thử lại hoặc đổi model, có thể do model đang chọn gặp trục trặc. Xem [Models & engine](10-models-va-engine.md) để đổi model/engine.
- **File tải mãi không xong.** File lớn hoặc mạng chậm; thẻ file sẽ báo lỗi cụ thể (quá thời gian tải, lỗi máy chủ). Thử lại với file nhỏ hơn hoặc kiểm tra kết nối.

## Liên quan

- [Phiên hội thoại](04-phien-hoi-thoai.md) - lưu, mở lại, đổi tên, xoá hội thoại cũ.
- [Skills](06-skills.md) - viết và gọi skill bằng lệnh `/slug`.
- [Models & engine](10-models-va-engine.md) - bảy nhà cung cấp model và cách đổi engine.
- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - đấu nguồn dữ liệu để hỏi số thật.
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - cột VAULT bên trái và trang Tệp tin.
- [Task & Dataview trong note](19-task-va-dataview.md) - khối `dataview` và `tasks` trong câu trả lời.
- [Kênh Telegram](11-telegram.md) và [Kênh Zalo](12-zalo.md) - chat với Javis ngoài dashboard.

Vẫn kẹt? Xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
