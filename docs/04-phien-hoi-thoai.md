# Phiên hội thoại

Mọi cuộc trò chuyện bạn nói với Javis đều được lưu lại tự động. Trang này hướng dẫn cách xem lại, tìm kiếm, đổi tên, xoá và mở tiếp một cuộc trò chuyện cũ, kể cả cuộc đã diễn ra từ nhiều ngày trước.

Nếu bạn chưa quen với màn hình chat, đọc trước [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md).

## Tính năng này là gì

Javis tự lưu lại từng lượt hỏi và trả lời vào một cơ sở dữ liệu trên máy của bạn. Nhờ vậy bạn không mất nội dung khi tắt trình duyệt hay khởi động lại máy chủ. Cụ thể bạn có thể:

- Xem danh sách các cuộc trò chuyện cũ, mới nhất nằm trên đầu.
- Tìm kiếm toàn văn: gõ một từ khoá và Javis tìm trong nội dung của mọi cuộc trò chuyện.
- Mở lại một cuộc cũ và trò chuyện tiếp đúng mạch cũ.
- Đổi tên cho dễ nhớ.
- **Ghim** cuộc quan trọng lên đầu danh sách.
- **Gom** nhiều cuộc vào một **Project** (nhóm).
- **Gắn icon cho từng Project** để phân loại nhóm bằng mắt.
- Xoá cuộc không cần nữa.

## Ghim, Project và icon

Danh sách xếp theo thời gian, nên một cuộc dùng đi dùng lại sẽ trôi dần xuống dưới. Ba công cụ
dưới đây để bạn tự sắp lại, tất cả đều nằm ở cột **Lịch sử** bên trái khung chat.

**Ghim.** Rê chuột vào một cuộc rồi bấm biểu tượng ghim. Cuộc đó chuyển lên nhóm **Đã ghim**
trên đầu danh sách và ở yên đó. Ghim không làm cuộc đó trông như "vừa nói chuyện" nên thứ tự
của các cuộc còn lại giữ nguyên. Bấm lại để bỏ ghim.

**Project.** Thanh ngay dưới nút "Hội thoại mới" là nơi chọn nhóm. Bấm vào để xem danh sách,
tạo nhóm mới, đổi tên, đổi icon hoặc xoá. Khi đang mở một project:

- Danh sách chỉ hiện các cuộc thuộc project đó.
- **Cuộc trò chuyện mới bạn bắt đầu sẽ tự rơi vào project đó**, không phải gắn tay.

Chọn "Tất cả hội thoại" để xem lại toàn bộ, hoặc "Chưa xếp nhóm" để tìm những cuộc còn sót.
Muốn chuyển một cuộc sang nhóm khác thì rê chuột vào nó và bấm biểu tượng thư mục.

**Xoá project KHÔNG xoá hội thoại.** Các cuộc bên trong chỉ được gỡ khỏi nhóm và quay về
"Chưa xếp nhóm". Hộp xác nhận cũng nói rõ điều này kèm số cuộc sẽ được gỡ.

**Icon cho Project.** Mở menu chọn nhóm, rê chuột vào một project rồi bấm biểu tượng bảng
màu. Bảng chọn hiện toàn bộ icon Javis đang dùng, kèm ô lọc theo tên (gõ `star`, `folder`,
`brain`...). Project chưa đặt icon thì mượn tạm icon thư mục, nên hàng nào cũng có icon và mắt
quét theo cột icon được.

Icon chỉ có ở **Project**, không có ở từng cuộc trò chuyện. Lý do: hàng nào trong danh sách
cũng là một cuộc trò chuyện nên icon ở đó chẳng phân loại được gì, chỉ thêm một nút phải bấm.
Còn mỗi project thật sự là một thứ khác nhau, nên icon ở đó mới có việc để làm.

Đây là **icon của chính Javis** chứ không phải emoji, và đó là chủ ý: icon Javis tự đổi màu
theo tông sáng hay tối bạn đang dùng, và vẽ giống hệt nhau trên mọi máy. Emoji thì mỗi hệ
điều hành vẽ một kiểu, lại có màu cứng nên nền tối nhìn chói.

Project gắn theo bộ não, nên đổi bộ não thì danh sách project đổi theo. Riêng "đang mở project
nào" được nhớ trên từng máy (trình duyệt), không đồng bộ sang máy khác.

Một điểm quan trọng: các cuộc trò chuyện được gắn theo "bộ não" (vault) đang chọn. Khi bạn đổi bộ não ở thanh chọn vault, danh sách lịch sử đổi theo để chỉ hiện các cuộc thuộc bộ não đó, **và khung chat cũng đổi theo**. Xem mục "Đổi bộ não giữa chừng" bên dưới, và cách chọn bộ não ở [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).

## Nơi lưu dữ liệu

Toàn bộ lịch sử nằm trong một tệp duy nhất tên `conversations.db`.

| Mục | Giá trị mặc định | Ghi chú |
|---|---|---|
| Tên tệp | `conversations.db` | Định dạng SQLite |
| Thư mục | Thư mục `server/` của Javis | Cùng chỗ với `settings.json` |
| Biến môi trường đổi vị trí tệp | `JAVIS_SESSIONS_DB` | Trỏ tới đường dẫn tệp `.db` khác |
| Biến môi trường đổi thư mục gốc | `JAVIS_STATE_DIR` | Đổi cả thư mục chứa trạng thái |

Nếu bạn muốn dời tệp lịch sử sang chỗ khác (ví dụ ổ dữ liệu riêng), đặt biến `JAVIS_SESSIONS_DB` trong tệp cấu hình. Chi tiết cách chỉnh biến môi trường xem [Cấu hình .env](16-cau-hinh-env.md).

Mỗi cuộc trò chuyện lưu kèm: tên (title), bộ não, engine đang dùng, model, kênh sinh ra nó, số tin nhắn, thời gian tạo và thời gian cập nhật gần nhất. Từng lượt hỏi và đáp lưu riêng để có thể tìm kiếm và mở lại chính xác.

## Cuộc trò chuyện đến từ Telegram

Danh sách này không chỉ có các cuộc bạn mở trên web. Những gì bạn nhắn với Javis qua **Telegram** cũng được lưu vào đây và mang nhãn **TG** trong danh sách, nên ngồi máy tính bạn vẫn đọc lại và tìm kiếm được cuộc đã nói lúc đang đi đường.

Vì trên Telegram gần như không ai bấm bắt đầu cuộc mới, Javis tự cắt sang cuộc mới khi bạn nghỉ quá 12 tiếng hoặc khi cuộc hiện tại đã dài khoảng 100 lượt. Việc cắt này chỉ để bản lưu dễ đọc, không làm Javis quên mạch trong lúc bạn đang trò chuyện trên Telegram. Các cuộc Telegram cũ hơn 30 ngày được tự cất vào kho lưu nên không hiện ở danh sách mặc định, nhưng vẫn tìm được bằng ô tìm kiếm. Chi tiết ở [Kênh Telegram](11-telegram.md).

## Mở ở đâu trong Javis

Sidebar lịch sử nằm ở trang **Trò chuyện**. Có ba đường vào, đều dẫn tới đúng chỗ đó:

- **Rail điều hướng.** Mở nhóm **Trợ lý** bên trái rồi bấm **Trò chuyện**.
- **Nút ⛶** trên khung **HỘI THOẠI** ở màn hình chính Javis.
- **Nút 🕘 Lịch sử** ở hàng nút góc trên bên phải màn hình.

Trang có hai cột: cột trái là **sidebar Lịch sử** gồm nút **＋ Hội thoại mới** trên cùng, ô tìm kiếm, và danh sách các cuộc trò chuyện nhóm theo thời gian (**Hôm nay / Hôm qua / 7 ngày qua / Cũ hơn**); cột phải là khung chat với tiêu đề "Trò chuyện với Javis". Cuộc đang mở được tô sáng trong danh sách để bạn biết mình đang ở đâu.

Nút **🕘** trên thanh tiêu đề (chú thích khi rê chuột: "Ẩn/hiện lịch sử") thu hoặc mở cột trái. Nút **‹ Thu nhỏ** đưa về lại màn Javis. Trên màn hình hẹp (dưới 860px), sidebar tự ẩn và mở dạng ngăn kéo nổi; chọn một cuộc là ngăn kéo tự đóng.

## Cách dùng (từng bước)

### Xem lại danh sách cuộc trò chuyện

1. Mở sidebar lịch sử theo một trong hai cách ở trên.
2. Danh sách hiện các cuộc thuộc bộ não đang chọn, nhóm theo thời gian, cuộc cập nhật gần nhất nằm trên cùng.
3. Mỗi dòng cho biết: tên cuộc trò chuyện, giờ (hoặc ngày), nhãn kênh nếu không phải web (ví dụ **TG**), engine đã dùng và số tin nhắn (ví dụ `12 tin`).
4. Danh sách hiện **20 cuộc** đầu tiên. Còn nữa thì cuối danh sách có nút **Xem thêm 20**, bấm một lần mở thêm 20 mục. Không có trần trên, bấm tiếp là ra tiếp.
5. Nếu chưa có cuộc nào, sidebar hiện dòng "Chưa có hội thoại nào." kèm dòng "Bấm ＋ để bắt đầu."

Cuộc chưa được đặt tên sẽ hiện tạm câu hỏi đầu tiên của bạn làm tên. Javis cũng tự đặt tên rút gọn từ câu hỏi đầu (khoảng 48 ký tự) ngay sau lượt trả lời đầu tiên.

### Nhận biết cuộc đang trả lời dở

Cuộc nào còn một lượt đang chạy nền sẽ có biểu tượng **⏳** đứng trước tên (chú thích khi rê chuột: "Đang trả lời") và cả dòng được làm nổi. Bạn cứ đi làm việc khác, câu trả lời vẫn chạy tiếp trên máy chủ và tự lưu vào cuộc đó.

Trong lúc đó nếu bạn gửi thêm một câu nữa vào chính cuộc đang chạy, Javis từ chối và báo: "Phiên này đang trả lời - đợi lượt hiện tại xong đã." Muốn hỏi việc khác ngay thì bấm **＋ Hội thoại mới** rồi hỏi ở cuộc mới.

### Tìm kiếm toàn văn

1. Mở sidebar Lịch sử.
2. Bấm vào ô có chữ mờ **Tìm trong mọi hội thoại…** ở phía trên.
3. Gõ từ khoá. Javis tự tìm sau khi bạn ngừng gõ một chút, không cần bấm Enter.
4. Trong lúc tìm, danh sách hiện "Đang tìm…".
5. Kết quả hiện các dòng khớp: tên cuộc trò chuyện, đoạn trích ngắn quanh từ khoá (phần trùng từ khoá được in đậm) và thời điểm của tin nhắn đó.
6. Bấm vào một kết quả để mở thẳng cuộc trò chuyện chứa đoạn đó.
7. Xoá hết chữ trong ô tìm kiếm để quay lại danh sách đầy đủ.

Nếu không có dòng nào khớp, sidebar hiện "Không tìm thấy." Tìm kiếm chỉ quét các cuộc thuộc bộ não đang chọn. Muốn tìm ở bộ não khác, đổi bộ não trước rồi tìm lại.

### Mở lại và trò chuyện tiếp một cuộc cũ

1. Trong danh sách (hoặc kết quả tìm kiếm), bấm vào cuộc bạn muốn mở.
2. Khung chat bên phải nạp lại NGAY toàn bộ lượt hỏi và đáp cũ, dòng đó được tô sáng trong danh sách.
3. Gõ câu mới như bình thường. Javis nối tiếp đúng mạch cuộc cũ, không bắt đầu lại từ đầu.

Cách Javis giữ mạch khác nhau theo engine, xem mục "Javis nhớ mạch cũ bằng cách nào" bên dưới và [Models & engine](10-models-va-engine.md).

### Bắt đầu một cuộc trò chuyện mới

1. Mở sidebar Lịch sử.
2. Bấm nút **＋ Hội thoại mới** trên cùng.
3. Khung chat được dọn trống, bạn bắt đầu cuộc mới. Cuộc mới chỉ được lưu vào lịch sử sau khi bạn gửi câu đầu tiên.

### Đổi tên một cuộc trò chuyện

1. Trong danh sách, đưa chuột vào dòng cuộc cần đổi tên. Hai biểu tượng nhỏ hiện ra bên phải.
2. Bấm biểu tượng cây bút **✎** (chú thích khi rê chuột: "Đổi tên").
3. Một ô nhập hiện ra với dòng "Tên mới cho hội thoại:". Gõ tên mới rồi bấm OK.
4. Danh sách tự cập nhật tên vừa đặt.

Tên tối đa khoảng 120 ký tự, phần thừa sẽ bị cắt bớt. Nếu bạn bấm Huỷ, tên giữ nguyên.

### Xoá một cuộc trò chuyện

1. Trong danh sách, đưa chuột vào dòng cuộc cần xoá.
2. Bấm biểu tượng thùng rác **🗑** (chú thích khi rê chuột: "Xoá").
3. Một hộp xác nhận hiện ra kèm tên cuộc: `Xoá hội thoại "<tên cuộc>"?`. Bấm OK để xoá, bấm Huỷ để giữ lại.
4. Cuộc và toàn bộ tin nhắn của nó bị xoá khỏi cơ sở dữ liệu, danh sách tự cập nhật.
5. Nếu cuộc vừa xoá đúng là cuộc bạn đang mở, khung chat tự chuyển sang một hội thoại mới trống.

Lưu ý: xoá là vĩnh viễn, không có thùng rác khôi phục. Cân nhắc kỹ trước khi xoá cuộc quan trọng. (Khác với xoá cả một bộ não - cái đó có thùng rác giữ 30 ngày, xem [Quản lý tệp tin](05-quan-ly-tep-tin.md).)

## Javis nhớ mạch cũ bằng cách nào

Ba engine giữ ngữ cảnh theo ba cách khác nhau, nên hành vi khi mở lại cuộc cũ cũng khác nhau.

**Engine Claude (Agent SDK).** Mỗi cuộc trò chuyện trên dashboard lưu kèm mã phiên gốc của Claude. Mở lại cuộc cũ là Javis nối đúng phiên đó, nên cả ngữ cảnh lẫn công cụ đã dùng đều còn nguyên.

**Engine Codex (gói ChatGPT).** Mỗi cuộc lưu kèm mã thread native riêng của Codex để lượt sau nối tiếp đúng thread. Nếu thread đó mất (máy được nâng cấp, rollout cũ bị dọn), Javis không bỏ mạch: nó dựng lại ngữ cảnh từ chính lịch sử đã lưu trong `conversations.db` rồi mở thread mới, và báo trong khung chat một dòng "Phiên Codex cũ không còn trên máy - Javis đang khôi phục ngữ cảnh từ lịch sử đã lưu." Phần lịch sử đưa vào có ngân sách khoảng 60.000 ký tự, ưu tiên giữ đoạn gần nhất.

Nếu bạn đổi sang engine khác rồi hỏi tiếp trong cùng một cuộc, liên kết thread Codex cũ được bỏ (vì thread đó không chứa lượt vừa rồi). Quay lại Codex, Javis dựng thread mới từ lịch sử đã lưu.

**Engine gọi qua API (OpenRouter, OpenAI, Anthropic API, Google Gemini).** Mỗi lượt Javis dựng lại lịch sử từ cơ sở dữ liệu rồi gửi kèm. Cuộc dài thì phần cũ **được nén chứ không bị cắt câm**: Javis tự tóm tắt gộp phần đầu hội thoại, lưu bản tóm tắt lại, rồi ở các lượt sau chèn nó vào đầu payload dưới dạng ghi chú "[Tóm tắt phần đầu hội thoại - đã nén để tiết kiệm context...]". Model vẫn nhớ chủ đề, quyết định đã chốt, con số và việc đang dang dở, trong khi payload không phình vô hạn.

Việc nén thường chạy nền sau mỗi lượt nên bạn không thấy chậm. Chỉ khi phần chưa nén dồn quá dài (hay gặp ở lượt API đầu tiên ngay sau một mạch chat bằng engine Claude) Javis mới nén ngay trong lượt, chậm thêm một nhịp. Nếu nhà cung cấp lỗi khiến bước tóm tắt hỏng, Javis mới rơi về cách cũ là cắt bớt phần rất cũ.

## Đổi bộ não giữa chừng

Đổi bộ não ở ô chọn trên thanh trên cùng không chỉ đổi danh sách lịch sử, mà đổi cả khung chat:

- Nội dung của bộ não cũ bị dọn khỏi khung chat ngay lập tức, để bạn không nhầm là đang nói chuyện trong bộ não mới.
- Bộ não nào bạn đã xem trong lần tải trang này thì Javis mở lại đúng cuộc bạn đang dở ở đó.
- Bộ não bạn chưa mở lần nào trong phiên trang này thì khung chat để trắng, coi như bắt đầu mới.
- Việc ghi nhớ này chỉ sống trong một lần tải trang. Tải lại trang (F5) là quay về luật chung: mỗi lần mở trang là một hội thoại mới. Cuộc cũ vẫn nằm nguyên trong danh sách lịch sử, bấm vào là mở lại được.

## Bảng thao tác nhanh

| Thao tác | Nút / phím | Vị trí |
|---|---|---|
| Mở trang Trò chuyện (có sidebar lịch sử) | Mục `Trò chuyện` | Rail điều hướng, nhóm Trợ lý |
| Mở trang Trò chuyện từ màn Javis | `⛶` hoặc `🕘 Lịch sử` | Khung HỘI THOẠI / hàng nút góc trên phải |
| Ẩn/hiện sidebar | `🕘` | Thanh tiêu đề "Trò chuyện với Javis" |
| Về lại màn Javis | `‹ Thu nhỏ` | Thanh tiêu đề |
| Tìm toàn văn | Ô "Tìm trong mọi hội thoại…" | Đầu sidebar |
| Cuộc mới | `＋ Hội thoại mới` | Đầu sidebar |
| Mở lại cuộc | Bấm vào dòng | Danh sách (cuộc đang mở được tô sáng) |
| Nạp thêm cuộc cũ | `Xem thêm 20` | Cuối danh sách |
| Đổi tên | `✎` | Hiện khi rê chuột vào dòng |
| Xoá | `🗑` | Hiện khi rê chuột vào dòng |
| Cuộc đang trả lời dở | `⏳` trước tên | Dấu hiệu, không bấm được |

## Mẹo

- Đặt tên rõ ràng cho các cuộc quan trọng ngay sau khi làm xong, để sau này tìm nhanh mà không phải đọc lại từng cuộc.
- Muốn giữ mạch cho một chủ đề dài, hãy mở lại đúng cuộc cũ thay vì bấm **＋ Hội thoại mới**. Như vậy Javis vẫn nhớ ngữ cảnh trước đó.
- Khi làm một việc mới hoàn toàn không liên quan, bấm **＋ Hội thoại mới** để Javis không lẫn ngữ cảnh cũ vào câu trả lời.
- Tìm kiếm quét cả nội dung tin nhắn, nên bạn có thể tìm theo một con số, một tên khách hàng hay một cụm từ đã trao đổi, không chỉ theo tên cuộc.
- Danh sách và tìm kiếm luôn theo bộ não đang chọn. Nếu không thấy cuộc cần tìm, kiểm tra xem bạn có đang ở đúng bộ não hay không.
- Cuộc rất dài vẫn dùng được, nhưng nếu bạn chuyển sang một chủ đề khác hẳn thì mở cuộc mới vẫn cho câu trả lời sắc hơn: phần cũ khi bị nén chỉ còn ở dạng tóm tắt, không còn nguyên chữ.

## Đồng bộ khi đổi máy

Lịch sử hội thoại nằm trong tệp `conversations.db` trên chính máy chủ chạy Javis. Tệp này không tự đồng bộ lên đám mây và không tự chuyển sang máy khác.

- Nếu bạn chuyển Javis sang máy hoặc VPS mới mà muốn giữ lịch sử, hãy sao chép tệp `conversations.db` (trong thư mục `server/`) sang cùng vị trí ở máy mới, làm khi máy chủ đang tắt để tránh tệp đang mở.
- Nếu bạn không sao chép tệp, máy mới sẽ bắt đầu với lịch sử trống. Đây là hành vi bình thường, không phải lỗi.
- Không nên mở cùng một tệp `conversations.db` từ hai máy chủ chạy song song, vì có thể gây tranh chấp ghi dữ liệu.
- Khi sao lưu định kỳ, chỉ cần sao lưu tệp `conversations.db` là đủ để giữ toàn bộ lịch sử trò chuyện.

## Sự cố thường gặp

**Bảng lịch sử trống dù trước đó có nhiều cuộc.**
Nhiều khả năng bạn đang ở một bộ não khác. Danh sách chỉ hiện cuộc thuộc bộ não đang chọn. Đổi lại đúng bộ não rồi mở bảng lần nữa.

**Bấm mở bảng nhưng hiện "Lỗi tải danh sách."**
Máy chủ Javis có thể chưa chạy hoặc vừa khởi động lại. Kiểm tra máy chủ đang chạy ở cổng mặc định (7777) rồi thử lại. Xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

**Không thấy cuộc trò chuyện từ tuần trước ở cuối danh sách.**
Danh sách chỉ nạp 20 cuộc một lần. Cuộn xuống cuối và bấm **Xem thêm 20** vài lần, hoặc nhanh hơn là gõ một từ khoá vào ô tìm kiếm.

**Tìm kiếm báo "Không tìm thấy" dù chắc chắn đã nói câu đó.**
Kiểm tra bạn có đang ở đúng bộ não chứa cuộc đó không. Nếu vẫn không ra, thử từ khoá ngắn hơn hoặc một từ đơn giản hơn thay vì cả câu dài.

**Gửi câu mới thì báo "Phiên này đang trả lời - đợi lượt hiện tại xong đã."**
Cuộc đó còn một lượt đang chạy (dòng tương ứng có ⏳). Đợi lượt đó xong, hoặc bấm **＋ Hội thoại mới** để hỏi việc khác song song.

**Mở lại cuộc cũ nhưng Javis không nhớ ngữ cảnh trước.**
Với engine Claude, khả năng nhớ đầy đủ phụ thuộc vào phiên gốc còn được lưu hay không. Với engine Codex, thread native có thể đã bị dọn khỏi máy - Javis sẽ tự khôi phục từ lịch sử đã lưu và báo một dòng trong khung chat. Với engine API, phần rất cũ có thể đã ở dạng tóm tắt nén thay vì nguyên văn, nên chi tiết vụn có thể mờ đi; khi đó nhắc lại ngắn gọn thông tin quan trọng trong câu hỏi mới là đủ.

**Đổi bộ não xong thì khung chat trắng trơn.**
Đúng như thiết kế: bộ não bạn chưa mở lần nào trong lần tải trang này thì khung chat bắt đầu trống. Cuộc cũ của bộ não đó vẫn nằm trong sidebar lịch sử, bấm vào là mở lại.

**Lỡ xoá nhầm một cuộc.**
Xoá là vĩnh viễn, không khôi phục được từ giao diện. Cách phòng ngừa duy nhất là sao lưu tệp `conversations.db` định kỳ (xem mục "Đồng bộ khi đổi máy").

**Đổi tên xong nhưng tên bị cắt ngắn.**
Tên cuộc trò chuyện giới hạn khoảng 120 ký tự. Nếu bạn nhập dài hơn, phần thừa bị bỏ. Hãy đặt tên ngắn gọn, súc tích.

## Liên quan

- [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) - cách gửi câu hỏi, đính kèm file, bật giọng nói.
- [Models & engine](10-models-va-engine.md) - chọn engine Claude, Codex hay một provider API.
- [Kênh Telegram](11-telegram.md) - cuộc trò chuyện sinh ra từ Telegram và nhãn TG.
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - chọn và quản lý bộ não.
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md)
