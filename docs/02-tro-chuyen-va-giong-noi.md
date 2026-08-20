# Trò chuyện & giọng nói

Đây là chỗ bạn làm việc với Javis nhiều nhất: gõ chữ hoặc nói, Javis trả lời bằng chữ kèm đọc thành tiếng. Trang này mô tả toàn bộ khung chat, từ phím tắt, lệnh gạch chéo, nút bấm dưới mỗi tin nhắn cho tới cách chọn giọng đọc và nhờ Javis tạo ảnh.

Nếu chưa cài đặt xong lần đầu, xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) trước.

## Tính năng này là gì

Một chỗ duy nhất để làm việc với Javis:

- Gõ tin nhắn như chat bình thường.
- Nói bằng giọng, Javis nghe rồi tự gửi khi bạn ngừng nói.
- Javis trả lời bằng chữ, đồng thời đọc thành tiếng bằng giọng Việt.
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
| Thanh nhập liệu | Dưới cùng | Nút mic, nút kẹp file, nút loa, ô gõ chữ, nút gửi (đang chạy thì thành nút dừng) |

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

### Bước 2 - Nói bằng giọng: giữ phím Cách

Cách nhanh nhất để nói một câu:

1. Đảm bảo con trỏ **không** đang nằm trong ô gõ chữ hay ô nhập nào (nếu đang gõ thì phím Cách sẽ ra dấu cách chứ không bật mic).
2. **Giữ phím Cách (Space)**. Dòng chữ giữa màn hình đổi thành **ĐANG NGHE**, nút mic sáng lên.
3. Nói câu của bạn. Chữ bạn nói hiện ngay dưới trạng thái để bạn thấy Javis nghe đúng chưa.
4. **Thả phím Cách** ra. Javis tự gửi toàn bộ câu vừa nói và bắt đầu trả lời.

Lần đầu bấm mic, trình duyệt sẽ hỏi quyền dùng micro. Bấm cho phép. Nếu từ chối, Javis không nghe được và sẽ báo "Anh cần cấp quyền microphone cho trang này.".

### Bước 3 - Nói bằng giọng: bấm nút mic (chế độ rảnh tay)

Nút mic (hình micro to, bên trái thanh nhập) bật **chế độ luôn nghe**, tiện khi bạn không muốn giữ phím:

1. Bấm nút mic một lần. Trạng thái đổi thành **ĐANG NGHE • LUÔN** và nút mic sáng.
2. Cứ nói tự nhiên. Khi bạn ngừng nói một chút (khoảng 1,5 giây im lặng), Javis tự chốt câu và gửi đi.
3. Sau khi trả lời xong, Javis tự bật mic nghe lại, không cần bạn bấm.
4. Muốn tắt chế độ này: bấm lại nút mic, hoặc nhấn phím **Esc**.

Trong chế độ rảnh tay, khi bạn bắt đầu nói thì Javis tự ngắt phần nó đang đọc để lắng nghe, nên bạn có thể chen ngang bất cứ lúc nào. Cơ chế này đo độ to của giọng qua luồng mic đã khử vọng (nói liên tục khoảng 0,3 giây, to hơn hẳn nền), nên tiếng loa của chính Javis không tự làm nó ngắt lời.

### Bước 4 - Nghe Javis trả lời bằng giọng

Mặc định Javis **đọc thành tiếng** mọi câu trả lời bằng giọng Việt (Edge TTS chạy trên máy chủ). Đồ thị sáng theo nhịp giọng đọc.

Bật/tắt đọc bằng giọng có **3 chỗ** làm cùng một việc, luôn đồng bộ với nhau và nhớ lựa chọn sau khi tải lại trang:

- Nút hình **loa** ở góc trên phải (tên gợi ý khi rê chuột: "Bật/tắt giọng Javis"). Đang tắt tiếng thì nút mờ hẳn đi.
- Nút **loa** nằm ngay trên thanh nhập chat (gợi ý "Tắt giọng đọc" / "Bật giọng đọc"). Đang tắt tiếng thì nút chuyển đỏ và có một gạch chéo. Nút này bị ẩn trên điện thoại.
- Vào **Cài đặt → Giọng nói, thương hiệu & truy cập**, gạt công tắc **"🔊 Đọc trả lời bằng giọng"**.

### Bước 5 - Dừng khi Javis đang trả lời

Khi Javis đang suy nghĩ hoặc đang đọc, nút gửi ở thanh nhập biến thành **nút dừng** (hình vuông). Bấm nút đó là ngắt lượt đang chạy và dừng đọc ngay, trạng thái về SẴN SÀNG. Gõ **`/stop`** rồi Enter cũng ra đúng kết quả đó.

**Phím Esc KHÔNG còn dừng câu trả lời hay ngắt giọng đọc.** Esc chỉ thoát chế độ rảnh tay, tắt mic và đóng popup đang mở. Chú thích trên nút dừng vẫn ghi "(Esc)" là chữ sót lại từ bản cũ.

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

Bên dưới ba lệnh đó là **toàn bộ skill của brain đang chọn**, mỗi dòng gồm `/slug`, tên skill và một dòng mô tả.

Cách điều khiển menu:

- Gõ tiếp vài chữ để lọc dần. Ưu tiên khớp theo slug trước, rồi mới tới tên skill.
- **Mũi tên lên / xuống** để chọn dòng, **Enter** hoặc **Tab** để chốt, **Esc** để đóng menu. Bấm chuột vào một dòng cũng được.
- Chọn một **lệnh phiên** thì nó chạy ngay, không cần Enter.
- Chọn một **skill** thì `/slug ` được chèn **đúng chỗ con trỏ**, chữ đã gõ hai bên giữ nguyên; bạn gõ tiếp rồi Enter để gửi.

Khi gửi một lệnh skill, Javis dịch câu đó thành lời nhắc: "Hãy dùng skill `<slug>` với yêu cầu: ... Nếu không có skill tên này thì cứ xử lý yêu cầu của tôi bình thường."

### Gọi skill ở giữa câu

Không phải lúc nào cũng nghĩ ra skill trước rồi mới viết. Cứ viết yêu cầu trước, tới đâu cần thì gõ `/` tới đó: *"test sử dụng skill giữa khung chat `/notes`"* chạy skill `notes` với yêu cầu là **phần chữ còn lại**. Chữ đứng trước và sau lệnh đều được gộp vào yêu cầu, nên *"viết cho anh `/notes` về cuộc họp"* thành yêu cầu "viết cho anh về cuộc họp".

Vài luật cho khỏi bắt nhầm:

- Dấu `/` phải đứng **đầu câu hoặc ngay sau khoảng trắng**. Nhờ vậy `https://vd.com/notes` và `3/4 cái bánh` không bị hiểu thành lệnh.
- Ở giữa câu, tên lệnh phải là **skill có thật** trong brain đang chọn. `/home/user/notes` hay `/khong-co-that` cứ đi thẳng vào chat như chữ thường.
- Có nhiều lệnh trong một câu thì lấy cái **cuối cùng** (ý định mới nhất). Riêng lệnh đứng ngay đầu ô nhập luôn được ưu tiên tuyệt đối.
- **Ba lệnh phiên (`/new`, `/reset`, `/stop`) chỉ chạy khi đứng ở đầu ô nhập**, và menu cũng không gợi ý chúng ở giữa câu - viết nửa câu rồi lỡ bấm `/reset` mà mất sạch ngữ cảnh thì hại hơn tiện.

Chi tiết về skill xem [Skills](06-skills.md).

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

Trước đó Javis được dặn viết văn xuôi trơn vì Javis vốn hay được dùng bằng **giọng nói**. Nay không cần đánh đổi nữa: nút loa **tự bóc markdown** (tiêu đề, in đậm, gạch đầu dòng, link, khối mã) trước khi đọc thành tiếng, nên định dạng đẹp cho mắt không làm giọng đọc vấp.

Câu hỏi ngắn vẫn được trả lời bằng một câu. Định dạng là để dễ đọc, không phải để mọi câu trả lời trông như một bản báo cáo.

Các kênh chữ thuần thì siết hơn vì bản thân chúng không vẽ được: **Telegram** và **Zalo** không có bảng markdown, **terminal** thì không có bảng, ảnh nhúng lẫn link markdown. Cả ba vẫn dùng gạch đầu dòng bình thường. Xem [Telegram](11-telegram.md) và [CLI trong terminal](24-cli-terminal.md).

> Nếu Javis vẫn trả lời bằng văn xuôi dài: nhiều khả năng bộ nhớ dài hạn của brain còn một ký ức cũ kiểu "không thích bảng markdown, thích văn nói ngắn" từ thời bạn dùng bằng giọng nói, và ký ức đó được nạp vào **mọi** lượt chat. Mở `memory/MEMORY.md` trong trang **Tệp tin**, tìm dòng nói về cách trả lời rồi xoá dòng đó cùng file tương ứng trong `memory/facts/`. Xem [Second Brain, bộ nhớ & wiki](13-second-brain-bo-nho-wiki.md).

## Giọng đọc: nhà cung cấp, giọng, tốc độ

Mọi thứ về giọng nằm trong **Cài đặt → Giọng nói, thương hiệu & truy cập**.

### Chọn nhà cung cấp giọng đọc

Khối **NHÀ CUNG CẤP GIỌNG ĐỌC** có ba lựa chọn:

| Lựa chọn trong danh sách | Cần gì thêm |
|---|---|
| Edge TTS - miễn phí (mặc định) | Không cần gì |
| OpenAI - mượt, đa ngôn ngữ | OpenAI API key (dùng chung với chat) + chọn một trong 11 giọng: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse |
| ElevenLabs - tự nhiên nhất | ElevenLabs API key + **Voice ID** (lấy ở ElevenLabs → Voices) |

Chọn xong bấm **Lưu nhà cung cấp**. Dòng trạng thái bên dưới ghi đang dùng cái nào. Nếu nhà cung cấp trả phí gặp lỗi (hết hạn mức, sai key, mất mạng), Javis **tự quay về Edge TTS** để giọng không bao giờ tắt hẳn.

Khi chọn OpenAI hoặc ElevenLabs, khối hai giọng Edge (Ngọc Thu / Nam Minh) tự ẩn đi vì lúc đó giọng chọn ngay trong khối của nhà cung cấp.

### Chọn giọng Edge và tốc độ

| Tuỳ chọn | Giá trị | Ghi chú |
|---|---|---|
| Giọng đọc | **Ngọc Thu** | Nữ, tự nhiên và ấm áp (mặc định; mã Edge: `vi-VN-HoaiMyNeural`) |
| Giọng đọc | **Nam Minh** | Nam, trầm (mã Edge: `vi-VN-NamMinhNeural`) |
| Tốc độ | Thanh trượt 0.70× đến 1.80× | Mặc định 1.10× |
| Ngôn ngữ nghe | **Tiếng Việt** (vi-VN) | Mặc định |
| Ngôn ngữ nghe | **Tiếng Anh** (en-US) | Dùng khi bạn nói toàn tiếng Anh |

Các bước:

1. Chọn Ngọc Thu hoặc Nam Minh.
2. Kéo thanh **TỐC ĐỘ** để chỉnh nhanh/chậm; số bên cạnh hiện tốc độ hiện tại (ví dụ 1.10×).
3. Bấm **▶ Nghe thử** để nghe một câu chào mẫu bằng giọng vừa chọn.
4. "Ngôn ngữ nghe" là ngôn ngữ Javis dùng để nhận diện lời bạn nói, khác với giọng đọc trả lời. Để mặc định Tiếng Việt trừ khi bạn quen nói tiếng Anh.

Mọi lựa chọn giọng, tốc độ, ngôn ngữ nghe đều được ghi nhớ cho lần sau.

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
- Nhóm **Hệ thống** (chọn brain, nút đổi tông sáng/tối, nút loa, dải HỆ THỐNG và MCP) dời xuống đáy ngăn kéo điều hướng.
- Ô nhập rút gọn lời nhắc thành "Nói hoặc gõ cho Javis…".
- Nút loa trên thanh nhập và nút **🕘 Lịch sử** ở header bị ẩn (đã có nút loa trong ngăn kéo, và trang **Trò chuyện** có sẵn lịch sử).
- Không có chuột để rê, nên **chạm vào một tin nhắn** để hiện hàng nút của đúng tin đó; chạm ra chỗ khác thì ẩn đi.
- Trong trang **Trò chuyện**, nút **🕘** ở thanh tiêu đề mở/đóng ngăn lịch sử trượt từ trái.

## Ý nghĩa dòng chữ trạng thái giữa màn hình

Dòng chữ ngay dưới quả cầu cho biết Javis đang làm gì:

| Chữ hiện | Nghĩa |
|---|---|
| SẴN SÀNG | Đang nghỉ, chờ bạn |
| ĐANG NGHE | Đang nghe bạn nói (giữ phím Cách) |
| ĐANG NGHE • LUÔN | Chế độ rảnh tay đang bật |
| ĐANG SUY NGHĨ | Bộ não đang xử lý câu hỏi |
| ĐANG NÓI | Javis đang đọc câu trả lời |

## Bảng tra nhanh nút và phím tắt

Nút quanh khung chat:

| Nút | Ở đâu | Làm gì |
|---|---|---|
| Mic to | Trái thanh nhập | Bật/tắt chế độ rảnh tay (luôn nghe) |
| Kẹp giấy | Cạnh nút mic | Chọn file đính kèm |
| Loa | Cạnh nút kẹp giấy | Bật/tắt đọc trả lời (ẩn trên điện thoại) |
| Mũi tên | Phải thanh nhập | Gửi tin nhắn |
| Ô vuông | Thay nút gửi khi đang chạy | Dừng lượt đang trả lời + dừng đọc |
| ⛶ | Góc mục HỘI THOẠI | Phóng to khung chat |
| 🕘 Lịch sử | Góc trên phải | Mở khung chat rộng kèm lịch sử hội thoại |
| Badge engine | Cạnh chữ HỘI THOẠI | Engine + model thật của lượt vừa chạy |
| Chip model · Effort | Trên thanh nhập | Đổi nhà cung cấp, model và độ sâu suy nghĩ |

Phím tắt:

| Thao tác | Kết quả |
|---|---|
| Giữ **Space** (khi không ở ô nhập) | Bật mic, nghe cho tới khi thả phím |
| Thả **Space** | Gửi câu vừa nói |
| **Enter** | Gửi tin nhắn đang gõ |
| **Shift + Enter** | Xuống dòng trong tin nhắn |
| **Ctrl + V** | Dán ảnh, hoặc dán văn bản dài thành file .txt đính kèm |
| **/** (đầu ô nhập) | Mở menu lệnh; ↑ ↓ chọn, Enter hoặc Tab chốt |
| **Esc** | Thoát chế độ rảnh tay + tắt mic; đóng menu lệnh; đóng panel artifact. **Không** dừng câu trả lời |

## Mẹo

- Muốn nói dài nhiều câu mà không sợ Javis gửi sớm, dùng chế độ rảnh tay (nút mic) và nói liền mạch; chỉ ngừng hẳn khi thật sự nói xong.
- Nghe Javis đọc lâu, muốn im lặng đọc chữ: tắt công tắc "🔊 Đọc trả lời bằng giọng", câu trả lời vẫn hiện đầy đủ dạng chữ.
- Đưa nhiều ảnh chụp màn hình cùng lúc bằng cách kéo - thả tất cả vào cửa sổ, Javis xử lý từng cái.
- Nếu bạn quen nói tiếng Anh, đổi "Ngôn ngữ nghe" sang Tiếng Anh để nhận diện chính xác hơn.
- Dán nguyên một bài dài vào ô chat cứ dán thoải mái: Javis tự biến thành file `.txt` đính kèm, khung chat vẫn gọn.
- Hỏi lại một câu đã hỏi mà muốn đổi vài chữ: bấm **✎** trên tin cũ, sửa trong ô nhập rồi gửi, khỏi gõ lại từ đầu.
- Nút **⛶** trên mục HỘI THOẠI và mục **Trò chuyện** trong nhóm Trợ lý dẫn tới cùng một chỗ, dùng đường nào tiện hơn thì dùng.

## Sự cố thường gặp

- **Giữ phím Cách không bật mic.** Con trỏ đang nằm trong ô gõ chữ hoặc một ô nhập khác. Bấm ra vùng trống của trang rồi giữ lại phím Cách.
- **Trình duyệt không nghe được.** Javis báo "Trình duyệt không hỗ trợ giọng nói. Dùng Chrome/Edge." Hãy mở dashboard bằng Chrome hoặc Edge.
- **Micro không hoạt động.** Trình duyệt chặn quyền micro. Vào phần quyền của trang trong trình duyệt và cho phép micro, rồi tải lại trang.
- **Nhấn Esc mà Javis vẫn nói tiếp.** Đúng như thiết kế hiện tại: Esc không dừng lượt nữa. Bấm nút dừng (ô vuông) trên thanh nhập, hoặc bấm nút loa để tắt tiếng.
- **Không nghe thấy Javis đọc.** Kiểm tra nút loa (góc trên phải bị mờ, hoặc nút trên thanh nhập bị gạch chéo đỏ) có đang tắt tiếng không; kiểm tra âm lượng máy. Bấm "▶ Nghe thử" để kiểm tra riêng phần đọc. Nếu đang dùng OpenAI hoặc ElevenLabs mà giọng nghe lạ, nhiều khả năng nhà cung cấp đó lỗi và Javis đã tự quay về Edge.
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
