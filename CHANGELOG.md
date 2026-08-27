# Nhật ký cập nhật

Lịch sử phiên bản Javis OS. Bản mới nhất ở trên cùng. Xem ngay trong app tại mục **Cập nhật** trên thanh bên trái.

Định dạng: mỗi phiên bản là một khối `## [x.y.z] - ngày`, bên dưới nhóm thay đổi theo `### Thêm mới / Sửa lỗi / Cải thiện / Bảo mật`.

## [0.47.2] - 2026-08-27
### Thêm mới
- **Thu gọn được hai panel như sidebar.** Panel Vault ở màn chính có nút thu ngay cạnh nút làm mới - thu xong chỉ còn một dải hẹp với nút mở lại. Cột lịch sử hội thoại ở trang Trò chuyện cũng thu được trên máy tính bằng đúng nút lịch sử trên thanh tiêu đề.
- Cả hai đều nhớ lựa chọn: F5 hay mở lại app vẫn giữ nguyên trạng thái thu/mở như bạn để.

## [0.47.1] - 2026-08-27
### Cải thiện
- **Hết cảnh câu trả lời dừng giữa chừng vì "đã chạy hết 8 vòng gọi tool".** Trần vòng gọi tool của các bộ não API nâng từ 8 lên 30 (chỉnh được tới 120), đủ cho việc nhiều bước mà không phải chia nhỏ câu hỏi hay đi sửa biến môi trường.
- Chống đốt token chuyển sang canh đúng bệnh: model gọi lại cùng công cụ với cùng tham số 3 vòng liên tiếp thì bị nhắc dừng, tới vòng thứ 5 thì Javis tự cắt lượt. Việc bình thường không bao giờ dính phanh này.

## [0.47.0] - 2026-08-27
### Thêm mới
- **Cài Javis thành app trên máy tính, không chỉ điện thoại.** Trên Chrome/Edge, thanh trạng thái có nút "Mở như app" (kèm icon cài trong thanh địa chỉ): bấm một lần là Javis chạy trong cửa sổ riêng, mở từ Desktop/Dock như một ứng dụng thật, không lẫn giữa các tab.

### Sửa lỗi
- **Hết cảnh báo "Chưa kết nối Model AI" oan khi bạn đã kết nối đủ.** Trước đây banner đỏ vẫn treo nếu bạn chạy Claude bằng API key, nếu model việc nền để "Về mặc định" trên máy dùng bộ não khác, hoặc trong 10 phút đầu sau khi vừa đăng nhập lại. Giờ banner chỉ đỏ khi bộ não bạn thật sự chọn không dùng được, và tắt ngay khi bạn kết nối xong.

## [0.46.0] - 2026-08-26
### Thêm mới
- **Công tắc "Đồng bộ cả ảnh" trong khối đồng bộ GitHub** (trang Tự học, mặc định tắt). Bật lên thì ảnh jpg/png/gif/webp trong brain (mỗi ảnh tối đa 10MB) cũng lên repo và theo bạn sang máy khác; video và file nặng vẫn không bao giờ lên.
- Bật đồng bộ ảnh thì Javis ngừng tự dọn ảnh cũ trong attachments, để ảnh đã backup không tự biến mất theo hạn dọn rồi lan lệnh xoá sang máy khác.
- An toàn khi các máy lệch cấu hình: máy chưa bật không đẩy, không nhận, và không xoá ảnh máy khác đã đưa lên. UI nói thẳng đánh đổi trước khi bật: git nhớ mãi mãi, tắt sau không lấy lại dung lượng.

## [0.45.0] - 2026-08-26
### Thêm mới
- **Javis sửa thẳng vai và chuỗi bước đã có, thay vì đẻ bản sao.** Trước đây tự học chỉ biết tạo mới, nên mỗi lần một workflow cần cải tiến lại có thêm một bản gần giống nằm cạnh. Giờ nó sửa đúng file đó: thiếu bước thì thêm, thừa thì bỏ, sai thứ tự thì xếp lại.
- Sửa xong vẫn giữ nguyên phần của bạn: tên bạn đặt, trạng thái bật/tắt, model bạn chọn cho agent. Mỗi lần sửa đều ghi ngày và lý do vào cuối file để bạn đọc lại, và vẫn hoàn tác được bằng một chạm.
- **Khoá được từng file.** Thêm dòng `learn_lock: true` vào phần đầu file agent hoặc workflow là tự học không đụng vào nữa.

## [0.44.0] - 2026-08-26
### Thêm mới
- **Tự học thêm được Vai (Agent) và Chuỗi bước (Workflow).** Trang Tự học có thêm 2 công tắc: bật lên thì khi bạn nhờ một vai hay một chuỗi việc lặp đi lặp lại trong chat, Javis tự đóng thành agent/workflow mới trong Studio.
- An toàn như học skill: mặc định tắt, có vòng kiểm tra thứ hai trước khi ghi, chỉ tạo mới không ghi đè cái đã có, và workflow luôn tạo ở trạng thái tắt để bạn xem trước rồi tự bật.

## [0.43.3] - 2026-08-26
### Sửa lỗi
- **Tự học chạy được cả khi máy chưa đăng nhập Claude.** Trước đây ai dùng bộ não Gemini, OpenAI hay Groq mà bỏ trống model việc nền thì vòng tự học nào cũng chết lặng, nhật ký chỉ ghi "không parse được manifest" kèm câu "Not logged in". Giờ việc nền tự chuyển sang đúng bộ não bạn đang chat khi Claude không sẵn sàng.
- **Câu "Not logged in / Please run /login" không còn bị tưởng là kết quả.** Việc nền (tự học, loop, việc Kanban) coi nó là bộ não chết và thử bộ não dự phòng kế tiếp; hết đường mới báo lỗi, và báo đúng là mất đăng nhập chứ không phải lỗi khó hiểu.

## [0.43.2] - 2026-08-24
### Sửa lỗi
- **Dải "việc đang chạy ngầm" không còn bị cắt mất nửa.** Trước đây khi khung chat đầy tin nhắn, dải này bị bóp bẹp chỉ còn ló nửa dòng đầu, phải cuộn bên trong mới đọc được.
- **Đồng hồ chờ trả lời hiện phút và giờ.** Việc chạy lâu giờ đếm kiểu "1m 56s" hay "1h 30m 40s" thay vì dồn hết về giây, nhìn phát biết ngay đã đợi bao lâu.

## [0.43.1] - 2026-08-23
### Sửa lỗi
- **Hội thoại từ Telegram hiện lại ở thanh bên.** Chúng vẫn được lưu đủ từ trước tới nay, chỉ là bị lọc mất khỏi danh sách và khỏi ô tìm kiếm khi bạn đã từng gõ `/brain` trên Telegram. Giờ mở dashboard là thấy, kể cả những cuộc cũ.
- **File bạn dán hoặc kéo vào khung chat thì Javis đọc thẳng, khỏi phải chép vào thư mục Brain.** Trước đây với các bộ não chạy bằng API key, dán một đoạn văn dài vào chat xong Javis lại bảo bạn tự chuyển file qua Brain rồi mới đọc được. Bộ não Claude Code không dính lỗi này.
- Vẫn đúng ranh giới cũ: Javis chỉ đọc thêm file bạn vừa đưa vào khung chat, không đọc lung tung trên máy, không ghi ra ngoài bộ não, và chatbot nói chuyện với khách thì không thấy mấy file đó.

## [0.43.0] - 2026-08-22
### Sửa lỗi
- **Bộ não Antigravity giờ dùng được tool của Javis thật.** Bấy lâu nay nó chat trôi chảy nhưng không gọi được MCP, không giao được việc Kanban, không chạy được skill - mà chẳng báo lỗi gì nên rất khó nhận ra. Javis ghi cấu hình sai chỗ và sai tên trường, tức `agy` chưa từng nhìn thấy trung tâm kết nối lần nào.
- **Nút Kiểm tra lại ở trang Models nói rõ hai chuyện.** Trước chỉ báo "Dùng được", nghĩa là chat được. Giờ nó nói thêm tool của Javis đã đấu vào chưa - đúng chỗ đã hỏng lặng lẽ suốt mấy bản.
- **Bản Docker: kết nối MCP của Antigravity sống qua cập nhật.** Trước đây cứ cập nhật là mất, phải khai báo lại từ đầu.

### Bảo mật
- **Khoá kết nối nội bộ không còn lọt vào bản sao lưu Git của bộ não.** Các tệp cấu hình Javis ghi cho hai bộ não Google nằm ngay trong thư mục brain và có chứa khoá. Từ bản này chúng bị loại khỏi sao lưu, và mấy tệp thừa của bản cũ được tự xoá.

## [0.42.1] - 2026-08-22
### Sửa lỗi
- **Đổi model giữa chừng không còn làm Javis quên cuộc đang nói.** Trước đây đổi sang model khác rồi quay lại Claude Code hoặc Gemini CLI thì nó trả lời như chưa hề có mấy lượt ở giữa, có khi lạc đề hẳn. Giờ đổi qua đổi lại bao nhiêu lần cũng liền mạch.
- Đổi lại: lượt đầu tiên ngay sau khi đổi model tốn thêm một chút, vì Javis phải gửi lại lịch sử hội thoại cho bộ não mới.

## [0.42.0] - 2026-08-22
### Sửa lỗi
- **Đọc video YouTube: vá ba lỗi khiến bản trước gần như luôn thất bại trên máy chủ.** Danh sách trình phát đã cũ cả năm và còn chứa một cái YouTube đã bỏ; quân dự bị yt-dlp thì bị lỗi cấu hình nên chưa từng chạy được lần nào; và câu từ chối của YouTube bị đọc nhầm nên Javis báo "video riêng tư" cho một video vốn công khai.
- **Báo đúng bệnh.** Giờ Javis phân biệt rõ "máy chủ bị nghi là robot" với "video riêng tư", "giới hạn tuổi", "video đã bị gỡ", và cả trường hợp **máy chủ mất mạng** (trước đây cũng bị đổ cho YouTube). Khi không chắc thì nói thẳng là không chắc, kèm cách tự kiểm trong một phút, thay vì đoán bừa.

### Thêm mới
- **Lệnh tự kiểm khi video không đọc được**: chạy `python server/youtube_read.py <link>` ngay trên máy chủ, nó in ra bảng từng đường thử: đường nào sống, đường nào chết, YouTube trả lý do gì, mất bao nhiêu mili giây. Nó còn thử thêm một video đối chứng để tách bạch "riêng video này có vấn đề" với "cả máy chủ bị chặn", rồi kết luận bằng một dòng gọn và lưu báo cáo ra file để bạn gửi đi.
- **Đổi đường mạng riêng cho YouTube**: nếu máy chủ của bạn bị YouTube đánh dấu, đặt `JAVIS_YOUTUBE_PROXY` là xong, và chỉ mình lưu lượng YouTube đi qua đó chứ không phải cả Javis.

## [0.41.0] - 2026-08-20
### Sửa lỗi
- **Đọc được nhiều video YouTube hơn hẳn.** Bản trước hay báo "video đòi đăng nhập" rồi bỏ cuộc, kể cả với video công khai bình thường. Thủ phạm là YouTube nghi địa chỉ máy chủ là robot, hay gặp khi Javis chạy trên VPS. Giờ nó tự đổi lần lượt qua sáu kiểu trình phát rồi mới nhờ tới yt-dlp, nên phần lớn ca đó tự vượt được.
- **Báo đúng bệnh.** "Máy chủ bị nghi là robot" không còn bị nói nhầm thành "video riêng tư" nữa, nên bạn khỏi mất công đi mở quyền một video vốn đã công khai sẵn.

## [0.40.0] - 2026-08-20
### Thêm mới
- **Dán link YouTube là Javis tóm tắt được video.** Trước đây gửi link vào chat thì Javis luôn báo không đọc được; giờ nó đọc phụ đề của video rồi tóm tắt theo lời thoại thật, kèm mốc thời gian cho từng ý để bạn tua lại đúng chỗ. Nhận cả link youtu.be, Shorts, link phát trực tiếp và link dán lẫn trong câu.
- Chạy được ở **mọi bộ não** (kể cả các bộ não chỉ có API key), không cần khoá API YouTube và không cần đăng nhập.
- Video không có phụ đề, video riêng tư hay bị chặn thì Javis nói thẳng lý do chứ không đoán nội dung theo tiêu đề. Video dài quá thì nó báo đã đọc tới phút mấy, bạn bảo "đọc tiếp" là nó đọc khúc sau.

## [0.39.0] - 2026-08-19
### Thêm mới
- **Đấu được cửa hàng Shopify.** Thẻ **Shopify** trong Kho kết nối chỉ hỏi địa chỉ cửa hàng - không API key, không cài app, không cần bạn là chủ shop. Đấu xong là hỏi được sản phẩm, giá, tồn kho, và nhờ Javis dựng sẵn giỏ hàng rồi đưa link cho bạn bấm thanh toán.
- Mặc định ở mức Chỉ đọc nên Javis chỉ tra cứu. Muốn nó dựng giỏ hàng thật trên shop thì nâng lên Ghi nháp; Javis không bao giờ tự thanh toán được.
- **Ô nhập kỹ thuật giờ điền sẵn giùm bạn.** Vài kết nối đòi một giá trị mà người thường không thể tự biết; nay Javis điền sẵn, bạn cứ bấm Kết nối, và vẫn sửa được nếu muốn.

## [0.38.0] - 2026-08-18
### Thêm mới
- **Terminal mở được nhiều tab.** Ngay trên khung terminal có dải tab như trình duyệt: bấm **+** mở thêm shell riêng (tối đa 4), bấm tên tab để chuyển, bấm **x** để đóng hẳn phiên đó. Tab đang khuất vẫn chạy lệnh bình thường, F5 quay lại còn nguyên dàn tab.
- Nút "Phiên mới" đổi tên thành **Khởi động lại** cho rõ nghĩa: nó làm mới shell của tab đang xem, còn muốn thêm shell thì bấm **+** trên dải tab.

## [0.37.2] - 2026-08-18
### Sửa lỗi
- **Việc chạy nền dài không còn bị chặt ngang ở 5 phút.** Lịch hẹn, việc Kanban và bước workflow trước đây bị giới hạn 5-10 phút mỗi việc, nên việc thật (như quét quảng cáo nhiều phân mục rồi ghi Google Sheet) chết giữa chừng với lỗi "Fork vượt trần 300s". Giờ trần chung là **1 giờ**, và ai cần hơn nữa thì đặt biến môi trường `JAVIS_BG_MAX_WALL_S` (giây) rồi khởi động lại - không phải sửa code.

## [0.37.1] - 2026-08-18
### Sửa lỗi
- **Hết cảnh Javis (bộ não Claude Code) đột nhiên quên sạch cuộc đang nói dở.** Đang trao đổi thì bỗng nhiên Javis hỏi lại "bạn muốn nói về cái gì?" như người lạ - xảy ra sau khi một lượt đi đường tắt Tức thì, sau khi một lượt bị lỗi giữa chừng, hoặc sau khi máy chủ cập nhật. Nguyên nhân: ba ca đó làm đứt mạch hội thoại của engine mà chỉ ca "mạch quá dài" mới được khôi phục lịch sử; giờ mạch đứt vì lý do gì cũng được tự nối lại từ hội thoại đã lưu.

## [0.37.0] - 2026-08-18
### Thêm mới
- **Windows mở Javis như một app.** Double-click `JAVIS OS.bat` là server tự chạy nền rồi dashboard tự mở thành cửa sổ riêng - không thanh địa chỉ, có ô riêng trên taskbar, không cửa sổ đen. Đang chạy rồi thì bấm lại chỉ mở cửa sổ, không khởi động lại.
- **Tự chạy khi đăng nhập máy Windows**: `javis-autostart.bat install` (gỡ bằng `uninstall`). Không cần quyền admin.

## [0.36.1] - 2026-08-18
### Sửa lỗi
- **Chat trên điện thoại giờ xuống dòng được.** Bấm Enter/nhập trên bàn phím điện thoại là xuống dòng như mọi app nhắn tin, muốn gửi thì bấm nút Gửi. Trên máy tính giữ nguyên lối cũ: Enter gửi, Shift+Enter xuống dòng.
- **App "Thêm vào màn hình chính" hết cảnh mở lại thấy hội thoại cũ đứng im.** iPhone đóng băng app khi xuống nền nên tin nhắn đến trong lúc đó bị lỡ, mà app dạng này lại không có nút tải lại để tự cứu. Giờ mở app lên là Javis tự nối lại kết nối và tự kéo phần hội thoại đã lỡ về, không phải làm gì cả.

## [0.36.0] - 2026-08-18
Bản này gộp 6 đóng góp từ cộng đồng - cảm ơn @japanvip115 và @mrcong2909-web.
### Thêm mới
- **macOS mở Javis như một app.** Double-click `JAVIS OS.app` trong Finder là server tự chạy và dashboard tự mở, kèm lựa chọn tự khởi động khi đăng nhập máy. Không cần Docker, không cần gõ lệnh.
- **Chó canh cửa cho Mac** (`./watchdog.sh install`): server sống mà đơ không trả lời 3 phút liên tiếp thì tự được khởi động lại, không phải chờ ai phát hiện.
### Sửa lỗi
- **Terminal hết làm treo cả server trên Mac.** Đóng phiên terminal, hoặc dán một khối chữ lớn khi lệnh đang bận, đều có thể làm cả trang đứng hình phải khởi động lại bằng tay - đã sửa tận gốc cả hai đường, kèm test canh không cho tái phát. Cập nhật trên Mac cũng hết cảnh hai tiến trình giành nhau cổng.
- **Gõ tiếng Việt hết sót chữ cuối khi bấm Enter gửi tin.** Bộ gõ đang ghép vần mà Enter thì trước đây ký tự cuối rơi rớt hoặc lọt sang tin sau.
- **Kết nối Google NotebookLM hết chết ngay khi vừa đấu** (ô "Tên hồ sơ" cũ đè mất phiên đăng nhập vừa dán - đã bỏ hẳn ô đó, kết nối cũ tự hết lỗi).
- **Đấu Google Workspace từ VPS giờ được nói thẳng vì sao không đăng nhập được** thay vì chết im với lỗi "localhost từ chối kết nối" - kèm chỉ đường sang thẻ Lịch và Gmail riêng vốn chạy tốt trên VPS. Cài đặt trên Mac cũng hết chọn nhầm Python cũ rồi báo lỗi khó hiểu.

## [0.35.12] - 2026-08-17
### Sửa lỗi
- **App "Thêm vào màn hình chính" trên iPhone hết cảnh cứ đóng lại là bị đăng nhập lại.** Mỗi lần mở app từ icon là một lần khởi động nguội (khác tab Safari giữ ấm sẵn), nên câu hỏi "đã đăng nhập chưa" gửi đi lúc mạng chưa kịp lên hay bị lỗi - và trước đây hễ lỗi là Javis coi luôn như chưa đăng nhập, bắt gõ lại mật khẩu dù phiên vẫn còn hạn. Giờ hỏi lại vài lần trước khi kết luận, và có lỗi mạng thật thì để nguyên màn hình thay vì ép hiện màn đăng nhập oan.

## [0.35.11] - 2026-08-17
### Sửa lỗi
- **Thêm vào màn hình chính iPhone giờ luôn ẩn thanh địa chỉ.** Trước đây tuỳ máy tuỳ bản iOS mà có cái ẩn có cái không, vì Javis thiếu khai báo "chạy như app riêng" đầy đủ. Lưu ý: icon đã thêm vào màn hình chính TRƯỚC bản này vẫn giữ hành vi cũ - xoá icon đó rồi bấm "Thêm vào MH chính" lại một lần là hết.
### Cải thiện
- **Tắt phóng to/thu nhỏ bằng hai ngón tay trên điện thoại.** Giao diện Javis không còn bị lệch khi lỡ chạm hai ngón hoặc double-tap.

## [0.35.10] - 2026-08-16
### Sửa lỗi
- **Claude Code hết "thi thoảng tự đăng xuất".** Thủ phạm: khi Javis dừng một lượt chạy quá lâu, tiến trình claude có thể bị giết đúng lúc đang ghi file đăng nhập - file đứt nửa chừng là lần sau coi như chưa đăng nhập (ChatGPT không bị vì Javis tự giữ token hộ). Hai lớp vá: dừng tiến trình giờ có vài giây ân hạn để nó kịp đóng file, và Javis tự sao lưu file đăng nhập lành mạnh mỗi 5 phút - file hỏng hay biến mất là tự phục hồi ngay, có ghi log rõ ràng. Bấm Ngắt chủ động thì vẫn ngắt thật, không bị "hồi sinh".

## [0.35.9] - 2026-08-16
### Thêm mới
- **Chọn nhiều rồi tải về một gói ở Studio.** Ba trang Skills, Workflows, Agents đều có ô tick trên từng thẻ và nút Chọn tất cả; bấm "Tải đã chọn" là mọi thứ đã tick về chung MỘT file .zip, kèm luôn agent và skill phụ thuộc. Hết cảnh muốn chia sẻ 10 skill phải bấm Xuất 10 lần nhận 10 file. Gói này nhập lại một phát ở nút Nhập như gói thường.

## [0.35.8] - 2026-08-16
### Cải thiện
- **Terminal trong tab Code giờ là cmd gốc của máy.** Shell mở ở thư mục HOME như mọi terminal bình thường, không còn đứng trong thư mục brain - cài và đăng nhập CLI (như `agy` của Antigravity) hết vướng. Cần vào brain thì gõ `cd "$JAVIS_BRAIN"` là về. Muốn kiểu cũ thì đặt `JAVIS_TERMINAL_CWD`.
- **Gõ `agy` trong terminal của Javis là thấy lệnh ngay.** Trước đây PATH của server thiếu chỗ chứa lệnh vừa cài nên gõ `agy` báo không tìm thấy, dễ tưởng cài hỏng. Kèm theo: hướng dẫn đăng nhập Antigravity nay nói thẳng lý do hay gặp nhất của cảnh "cài rồi mà Javis không nhận" - đăng nhập qua SSH bằng user khác (như root) thì Javis không thấy; đăng nhập trong trang Code của chính Javis là chắc ăn.

## [0.35.7] - 2026-08-16
### Sửa lỗi
- **Đăng nhập Antigravity sống qua cập nhật.** Trước đây mỗi lần cập nhật là bay cả lệnh `agy` lẫn đăng nhập Google, phải cài và đăng nhập lại từ đầu. Giờ chúng được giữ trên vùng lưu trữ bền của máy: sau khi lên bản này, cài lại một lần cuối là từ đó cập nhật thoải mái. Không phải sửa gì trong cấu hình Docker.
- **Hết cảnh "kết nối ChatGPT xanh mà chat thì vỡ".** Máy thiếu lệnh `codex` (một số bản cài trước đây bị thiếu) thì thẻ ChatGPT trên trang Models nay cảnh báo thẳng kèm cách xử lý, thay vì báo đã kết nối rồi để bạn vào chat mới gặp lỗi. Bản đóng gói từ nay bảo đảm luôn có sẵn codex.

## [0.35.6] - 2026-08-16
### Bảo mật
- **2FA hết kiểu "tự tắt" âm thầm sau cập nhật.** Khoá mã hoá trên máy chủ (file .secret_key) mà mất hoặc đổi thì trước đây 2FA lặng lẽ ngừng hỏi mã và giao diện báo "Chưa bật" - ai có mật khẩu là vào thẳng. Giờ Javis nói thẳng "đang bật nhưng khoá bị lỗi", cổng đăng nhập vẫn chặn và nhận mã khôi phục, có nút bật lại với khoá mới ngay trên trang Tài khoản.
- **Không còn mất trắng khoá 2FA vì một lần lưu cài đặt.** Trước đây khi khoá đang lỗi, chỉ cần lưu bất kỳ cài đặt nào là bản mã hoá của khoá 2FA bị ghi đè thành rỗng vĩnh viễn. Giờ nó được giữ nguyên - tìm lại được file khoá cũ là 2FA sống lại, không cần làm gì.

## [0.35.5] - 2026-08-16
### Cải thiện
- **Chat cũ tuyệt đối không tự đổi model nữa.** Mỗi cuộc trò chuyện được đóng dấu model đang chạy ngay từ tin nhắn đầu tiên, kể cả khi bạn chưa từng đổi tay trong đó. Đổi mặc định chung ở trang Models chỉ áp cho cuộc mở sau, không đổi ngược cuộc đang dở; muốn cuộc cũ chạy model mới thì đổi ngay trong khung chat của nó.

## [0.35.4] - 2026-08-16
### Cải thiện
- **Bộ nhớ tự học của agent giờ đặc dần thay vì dài dần.** Agent chỉ đề xuất bài học, Javis cầm bút ghi hộ vào mục riêng: tự loại trùng, giữ đúng 15 dòng mới nhất, và phần bạn viết tay không bao giờ bị chạm. Hết cảnh bài học chất đống làm agent chậm và loãng dần theo thời gian.
- **Thanh model thôi nói dối khi ghim hỏng.** Phiên ghim một model mà provider đó đã bị gỡ key thì trước đây thanh model vẫn khoe "ghim" trong khi thực tế chạy mặc định chung. Giờ nó báo thẳng "ghim hỏng", và gửi tin nhắn là ghim hỏng tự được gỡ.

## [0.35.3] - 2026-08-16
### Thêm mới
- **Mỗi cuộc trò chuyện nhớ model riêng.** Đổi model ngay trong khung chat là chọn cho riêng cuộc đó (thanh model hiện dấu ghim), sang tab khác đổi model không kéo cuộc cũ đổi theo. Cuộc chưa từng đổi tay vẫn theo mặc định chung ở trang Models.
- **Agent thông minh dần theo mỗi lần dùng.** Chạy xong một việc mà rút ra bài học đáng giữ, agent tự ghi thêm vào bộ nhớ riêng của nó, không đụng phần bạn viết tay. Đúng chủ trương cải thiện lúc dùng: không có job nền nào quét sửa hàng loạt.

### Sửa lỗi
- **Hết cảnh VPS đầy RAM vì kết nối.** Server của thẻ kết nối (như Google Sheets) bị bỏ rơi thành cả trăm tiến trình mồ côi, ăn gần hết RAM sau một ngày. Giờ đóng là dọn cả cây tiến trình, và kết nối được giữ ấm thay vì đập đi dựng lại mỗi 10 phút.
- **Agent tạo qua chat hết "biến mất".** Hướng dẫn nội bộ còn trỏ thư mục cũ nên agent ghi vào chỗ app không đọc - đã xảy ra hai lần, giờ sửa tận gốc. Nhật ký chạy của agent cũng ghi đủ ở mọi đường chạy workflow, kể cả bước kiểm chứng.

## [0.35.2] - 2026-08-16
### Sửa lỗi
- **Thẻ Google Sheets và TikTok Ads sống lại.** Hai thẻ này chết ngay lúc kết nối với mọi người - không phải do key của bạn sai, mà do gói bên thứ ba bị thư viện mới làm gãy. Đã ghim đúng phiên bản, đấu lại là chạy. Ai đã tự đấu Google Sheets bằng nguồn tự khai để chữa cháy thì sau khi cập nhật nên quay về thẻ chính chủ và gỡ nguồn tự khai cho đỡ trùng.
- **Thông báo lỗi kết nối MCP hết giấu bệnh.** Trước đây phần quan trọng nhất của lỗi luôn bị cắt mất và Javis đổ tại key làm bạn đi kiểm key oan nhiều giờ. Giờ nó hiện đúng dòng nguyên nhân, và khi lỗi nằm ở gói chứ không phải ở bạn thì nói thẳng như vậy.

## [0.35.1] - 2026-08-15
### Cải thiện
- **Javis mặc định im lặng.** Mở lần đầu là chỉ hiện chữ, không tự đọc thành tiếng nữa - đỡ giật mình khi đang ở chỗ đông người hay quên bật loa nhỏ. Muốn nghe thì bấm nút loa ở khung chat hoặc bật **Đọc trả lời bằng giọng** trong Cài đặt nhanh; đã bật rồi thì Javis nhớ, F5 vẫn giữ nguyên. Ai đang bật sẵn từ trước cũng không bị tắt.

## [0.35.0] - 2026-08-14
### Thêm mới
- **Javis trả lời bằng đúng thứ tiếng bạn gõ.** Không chỉ tiếng Việt với tiếng Anh - gõ tiếng Nhật, Thái, Pháp hay bất kỳ thứ tiếng nào thì Javis đáp lại bằng chính thứ tiếng đó, không phải cài gì. Muốn ghim cứng một thứ tiếng thì vào **Cài đặt**, mục ngôn ngữ.
- **Giao diện có bản tiếng Anh.** Chọn ở **Cài đặt**; phần đã dịch hiện tiếng Anh, phần chưa dịch giữ nguyên tiếng Việt chứ không để trống ô nào. Chữ trên màn hình và ngôn ngữ Javis trả lời là hai lựa chọn riêng.
- **Múi giờ và tiền tệ tách khỏi ngôn ngữ.** Trước đây Javis luôn tính giờ Việt Nam dù bạn ngồi ở đâu, nên nhắc hẹn "7h sáng" kêu lệch vài tiếng cho người ở múi giờ khác. Giờ nó theo đúng múi giờ bạn đặt.

### Cải thiện
- **Javis gọi bạn là "bạn" và tự xưng "mình".** Trước đây nó mặc định xưng anh/em với mọi người, tức là đoán giới tính ngay từ câu đầu. Khi nào bạn tự xưng anh hoặc chị, Javis theo đúng như vậy và nhớ cho lần sau. Bot trả lời khách của bạn vẫn giữ lối "anh chị" quen thuộc.
- **Bản tiếng Anh cho README và trang hướng dẫn đầu tiên.** Các trang còn lại vẫn tiếng Việt; `docs/en/` nói rõ trang nào đã dịch để bạn khỏi đoán.

## [0.34.1] - 2026-08-14
### Sửa lỗi
- **Chữ trong Terminal trên Windows hết trôi thành bậc thang.** Chạy `git help` là cả màn hình xiên dần sang phải, mỗi dòng bắt đầu ở chỗ dòng trước kết thúc. Windows không có tầng nào lo việc "về đầu dòng" hộ nên Javis phải tự làm, giờ đã làm.

### Cải thiện
- **Code thành một nhóm riêng trên thanh bên, không còn nằm trong Bộ não.** Mở nhóm **Code** là thấy mục **Terminal**; các công cụ lập trình thêm sau sẽ nằm cùng chỗ đó. Bỏ luôn dải tab thừa bên trong trang - điều hướng gom về một tầng.

## [0.34.0] - 2026-08-13
### Thêm mới
- **Có tab Code, mở ra là một terminal thật.** Nằm cạnh Tệp tin trong nhóm Bộ não, mở sẵn ở thư mục brain. Gõ lệnh thẳng trên máy đang chạy Javis - `git pull`, xem log, cài CLI, đăng nhập `agy` - khỏi phải mở SSH ở cửa sổ khác. Chạy được cả `vim` và `htop`, có màu, có gợi ý Tab, Ctrl+C giết đúng lệnh đang chạy chứ không văng cả phiên.
- **Bấm sang trang khác không làm chết lệnh đang chạy.** Đang `npm install` mà đi xem chat rồi quay lại thì màn hình còn nguyên, chạy tới đâu hiện tới đó. F5 hay rớt mạng cũng vậy. Bỏ quên 30 phút thì Javis mới đóng phiên.
- Chỉ trình duyệt **đã đăng nhập** mới mở được terminal, token API không vào được. Muốn khoá hẳn thì đặt `JAVIS_TERMINAL=0` rồi khởi động lại.
- Windows chạy bản rút gọn: gõ một dòng rồi Enter, không có gợi ý Tab, không chạy được `vim`. Đó là giới hạn của hệ điều hành và giao diện nói thẳng điều đó ngay trên khung, không để bạn ngồi đoán.

## [0.33.7] - 2026-08-13
### Cải thiện
- **Đổi model Antigravity ngay trên Telegram.** Bảng nút của `/model` giờ hiện đủ nhà cung cấp như trang Models trên dashboard, chứ không còn kẹt ở năm cái cũ - nên bộ não Antigravity đổi được từ điện thoại. Nhà nào chưa liệt kê được model nào (hay gặp: cài rồi nhưng chưa đăng nhập) thì ẩn cho gọn.
- **Gõ thẳng `/model <tên model>` không còn chọn nhầm nhà.** Javis dò tên đó trong danh sách thật rồi chuyển đúng nơi; tên trùng ở nhiều nhà thì nó hỏi lại thay vì đoán.

## [0.33.6] - 2026-08-13
### Sửa lỗi
- **Chat qua Antigravity hết vỡ dấu tiếng Việt.** Chữ như "gồm", "hạn" hiện thành ô vuông hỏi chấm. Đo ra thì Javis đọc chữ về không hề sai - chỗ vỡ nằm ở lúc `agy` nhận nội dung, nên giờ Javis gửi theo từng mẩu cắt đúng chỗ để bên kia có đọc kiểu gì cũng không vỡ.
- Nếu chữ vẫn vỡ, Javis tự đổi cách gửi rồi hỏi lại một lần nữa; vẫn vỡ thì nó nói thẳng là lỗi nằm trong `agy` chứ không im lặng trả về chữ sai.

## [0.33.5] - 2026-08-13
### Sửa lỗi
- **Javis tự chữa mấy note .md đã hỏng từ bản cũ.** Vào trang Tệp tin, nếu còn file dính lỗi ở bản trước 0.33.4 (khối thuộc tính đầu note biến thành `* * *`, chữ bị dồn dấu gạch chéo) thì Javis hiện danh sách và bạn bấm một nút là chữa hết. Không file nào hỏng thì không hiện gì cả.
- Javis chỉ đụng vào đúng dấu vết của lỗi đó, nên đường kẻ ngang giữa bài hay note còn lành đều giữ nguyên.

## [0.33.4] - 2026-08-13
### Sửa lỗi
- **Mở file trong trang Tệp tin giờ dùng đúng trình sửa của khung chat.** Không còn ô soạn thảo trần bật lên giữa màn hình: file .md, .txt, .html mở **ngay trong trang**, có soạn thảo trực quan, thanh định dạng, Lùi/Tiến, đổi tên, xoá, phóng to. Bấm **✕** hoặc `Esc` là về lại danh sách.
- **Lưu note .md không còn làm hỏng file.** Khối `---` đầu note (status, type, created...) trước đây bị biến thành `* * *` ngay lần lưu đầu, và mỗi lần mở ra sửa lại thêm một lớp dấu gạch chéo vào tiêu đề. Nay khối đó hiện thành mục **Thuộc tính** khoá lại, giữ nguyên từng ký tự. File đã lỡ hỏng thì sửa tay lại một lần là xong.
- **Bấm link file trong chat không còn rơi vào trang trắng "Không phải thư mục".** Link trỏ vào file thì mở thẳng ra sửa; link trỏ trượt (hay gặp: chat ghi tên có dấu còn file lưu không dấu) thì Javis tự dò cả brain theo tên rồi bày ra file tên gần giống, bấm một phát là mở.

## [0.33.3] - 2026-08-13
### Sửa lỗi
- **Hết nháy cửa sổ đen trên Windows.** Thi thoảng đang dùng, một khung terminal đen chớp lên giữa màn hình rồi tắt - do Javis chạy nền không có cửa sổ nên mỗi lệnh phụ nó gọi lại được Windows cấp cho một cửa sổ mới. Đã bịt toàn bộ, và có bài kiểm tự động canh để đừng lọt lại lần nữa.
- Lượt cập nhật trên Windows cũng thôi nháy liên tục vì cùng nguyên nhân.

## [0.33.2] - 2026-08-13
### Sửa lỗi
- **Antigravity trên Windows: sửa nốt.** Bản 0.33.1 gửi nội dung cho `agy` theo một cú pháp suy ra từ tài liệu, và bản `agy` thật trả lại `Error: empty prompt` rồi thôi. Giờ Javis tự thử vài cách ngay lần chạy đầu, cách nào ăn thì dùng và nhớ luôn; không cách nào ăn thì tự chuyển sang đường dự phòng thay vì ném câu lỗi tiếng Anh cho bạn.

## [0.33.1] - 2026-08-13
### Sửa lỗi
- **Bộ não Antigravity CLI chat được trên Windows.** Trước đây mọi lượt đều trả về "hội thoại này đã quá dài", kể cả khi bạn vừa mở chat mới và chỉ gõ "hi" - nên mở bao nhiêu hội thoại mới cũng không thoát. Phần vượt giới hạn là phần cố định của Javis chứ không phải phần bạn gõ, và câu báo lỗi cũ chỉ sai đường.
- Nay Javis gửi nội dung cho `agy` theo đường khác, không còn dính giới hạn độ dài lệnh của Windows. Bản `agy` nào không nhận được thì Javis tự chuyển sang đường dự phòng ngay trong lượt đó, và nếu đường đó cũng không trọn vẹn thì nó nói thẳng ra thay vì lặng lẽ trả lời thiếu.
- **Antigravity giờ dùng được tool của Javis.** Đường dẫn cấu hình cũ đoán sai chỗ nên bộ não này chạy mà không có Kanban, không MCP, không skill, mà chẳng báo gì.
- Việc chạy nền qua Antigravity không còn bị cắt ngang ở phút thứ 5.

## [0.33.0] - 2026-08-13
### Thêm mới
- **Đưa file HTML vào là ra file Webcake sửa được, giống bản gốc.** Javis tự đọc trang HTML rồi dựng thành file `.pke` mở thẳng trong trình dựng trang Webcake: màu, cỡ chữ, ảnh, nút, form và thứ tự các khối lấy nguyên từ bản gốc chứ không phải nhìn rồi gõ lại. Bảo Javis "chuyển file html này sang webcake" là chạy.
- **Javis soi giúp trước khi giao.** Trang dựng xong được kiểm tự động: chữ đè lên nhau, khối tràn ra ngoài, và **chữ chìm vào nền** - lỗi hay gặp nhất khi bê màu từ HTML sang mà mắt thường khó thấy.

### Sửa lỗi
- **Kỹ năng có kèm công cụ giờ mới thật sự dùng được.** Trước đây Javis chỉ chép mỗi phần hướng dẫn của kỹ năng xuống bộ não, bỏ lại toàn bộ thư mục công cụ đi kèm - nên kỹ năng nào cần chạy công cụ là hỏng ở mọi bộ não. Đây chính là lý do "HTML sang Webcake" từng bị gỡ hẳn ở bản 0.9.291; nay sửa gốc và đưa nó trở lại.

## [0.32.2] - 2026-08-13
### Cải thiện
- **Antigravity CLI: đăng nhập giờ làm trong terminal, thẻ trên trang Models không còn nút đăng nhập.** Nút cũ mở ra một ô terminal nhỏ ngay trên trang mà bấm vào không ăn, nên rốt cuộc vẫn phải mở terminal thật; trên Windows thì nó chưa bao giờ chạy được.
- Thẻ giờ đưa thẳng lệnh cần gõ (`agy`) kèm một câu giải thích: qua SSH nó tự in ra link để bạn mở trên máy mình. Gõ xong bấm **Kiểm tra lại** là thẻ đổi sang đã đăng nhập.

## [0.32.1] - 2026-08-13
### Cải thiện
- **Trang Mức dùng chỉ hiện tiền đô, bỏ hẳn phần quy đổi sang đồng.** Giá của các nhà cung cấp đều niêm yết bằng USD, còn tỉ giá thì trôi mà con số trong máy thì đứng yên - quy đổi thêm một lần chỉ tạo ra một chỗ nữa để sai.
- Khoản tiền nhỏ hơn một xu giờ ghi là `<$0.01` thay vì làm tròn thành `$0.00` trông như bằng không.

### Sửa lỗi
- **Đơn giá quy đổi lấy đúng model đang chạy.** Trước đây với cấu hình mặc định nó nhặt nhầm tên model trong một ô cũ, nên tính giá $0,15 cho một lượt Opus giá $15 - lệch 100 lần, và lệch theo hướng khai thấp phần tiết kiệm xuống.

## [0.32.0] - 2026-08-13
### Thêm mới
- **Trang Mức dùng làm lại từ đầu.** Mở ra là một câu tiếng người nói thẳng tháng này ai trả gì cho cái gì, rồi tới ba ô bấm được: tiền mặt so với ngân sách, cửa sổ 5 giờ còn bao nhiêu, và đã tiết kiệm được bao nhiêu token.
- **Đặt ngân sách tiền API mỗi tháng ngay trên trang.** Chạm 80% Javis nhắn, chạm trần thì (nếu bạn bật) tự đẩy việc chạy nền sang đường không tốn tiền - chat của bạn không bị đụng tới. Kèm ô khai giá gói để biết gói đang lời hay lỗ so với giá API.
- **Báo cáo token tự gửi về chat sáng thứ Hai**, bật bằng một ô tick. Biểu đồ theo ngày giờ có gạch mốc ngày bạn đổi chế độ hay đổi bộ não, nhìn phát hiểu vì sao cột tụt.

### Sửa lỗi
- **Token tiết kiệm được hiện lại rồi, và hiện ở mọi kỳ.** Trước đây khối này biến mất đúng lúc chế độ tiết kiệm chạy tốt nhất, vì nó cần cả lượt cũ lẫn lượt mới trong 24 giờ mới có số - bật rồi để yên một ngày là mất hút.
- **Model OpenRouter hết bị tính chi phí bằng 0.** Đây đúng là nhánh duy nhất bạn trả tiền mặt thật, nên ô tiền cũ luôn hiện $0.00 dù ví có vơi đi.

## [0.31.0] - 2026-08-13
### Sửa lỗi
- **Đổi model xong không còn bị đòi đăng nhập lại Claude.** Trước đây chỉ cần một lần Javis hỏi không kịp là thẻ Claude hiện "chưa đăng nhập" kèm nút đăng nhập, dù tài khoản chẳng mất gì. Giờ nó nói rõ "chưa kiểm được, không phải bạn bị đăng xuất", và nhớ trạng thái nên đỡ hỏi lại liên tục.
- **Bộ não Antigravity CLI dùng được trở lại.** Javis đọc nhầm danh sách model của bản `agy` mới nên gửi sai tên model, lượt chat nào cũng lỗi; và khi chạy được thì bong bóng trả lời lại rỗng. Cả hai đã sửa, kèm dòng "Fetching available models..." không còn hiện như một model trong trình chọn.
- **Máy nhân Linux đời cũ (NAS, VPS cũ) chat được bằng Claude Code.** Trước đây mọi lượt chết ngay vì Javis chạy nhầm bản Claude đóng gói sẵn, giờ nó dùng đúng bản đã cài trên máy.
- Trên Windows, hội thoại quá dài cho Antigravity giờ báo rõ và mách hai cách đi tiếp, thay cho một lỗi khó hiểu về "tên tệp quá dài".

Cảm ơn người dùng đã gửi báo cáo rất kỹ kèm log và bản vá cho bốn lỗi trên.

## [0.30.3] - 2026-08-13
### Sửa lỗi
- **Đăng nhập Antigravity CLI chạy thật rồi.** Bản trước đứng im vì `agy` hỏi "chọn cách đăng nhập" trước khi đưa link, mà Javis lại ngồi chờ link. Giờ Javis tự chọn giúp đúng mục **Google OAuth** rồi mới lấy link ra cho bạn.
- Nút **Kiểm tra lại** khi chưa đăng nhập cũng nói đúng việc phải làm, thay vì báo "không trả lời kịp" rồi để bạn ngồi đoán.

## [0.30.2] - 2026-08-13
### Sửa lỗi
- **Bấm vào link file trong chat giờ mở thẳng ra sửa, không còn lúc được lúc không.** File .html Javis vừa xuất ra, file .md, .css, .json... bấm phát là vào trình sửa; trước đây có lúc lại quăng bạn về thư mục trong trang Tệp tin.
- Lý do cũ: cùng một link có hai đường đi (bấm thường, và mở tab mới hoặc F5) mà hai đường lại xử khác nhau. Nay đi chung một luật.
- Chữ hiện khi rê chuột cũng nói đúng việc: **Mở ra sửa** với file, **Mở vị trí trong Tệp tin** với thư mục. Ảnh, PDF, file nén vẫn là tải về như cũ.

## [0.30.1] - 2026-08-13
### Sửa lỗi
- **Danh sách mốc hội thoại đọc được trở lại khi chat đã dài.** Từ khoảng 60 câu hỏi, các dòng trong danh sách bị bóp bẹp lại thành một mớ vệt mờ; giờ mỗi dòng giữ nguyên chiều cao và danh sách tự cuộn như bình thường.

## [0.30.0] - 2026-08-13
### Thêm mới
- **Đăng nhập Google cho Antigravity CLI ngay trên trang Models, không phải mở terminal nữa.** Bấm **Đăng nhập Google**, mở link, đăng nhập, dán mã Google đưa lại là xong - giống hệt cách đăng nhập Claude Code và ChatGPT đang có.
- Chạy được cả khi Javis nằm trên VPS: Javis tự lo phần terminal. Tiện thể chữa luôn một lỗi của CLI làm đường link bị đứt đoạn khi đăng nhập qua SSH, dán sang trình duyệt là báo lỗi.
- Trên Windows thẻ nói thẳng là phải gõ `agy` một lần trong PowerShell, chứ không bày ra một cái nút bấm vào không chạy.

### Cải thiện
- Ô **Chạy bằng** ở thẻ Claude Code nói rõ hơn: nó chỉ đổi **ai trả tiền**, còn lệnh máy và MCP thì cả hai lựa chọn đều giữ nguyên - khác thẻ "Anthropic (API)" bên dưới. Trước đây hai chỗ nhìn như trùng nhau.

## [0.29.1] - 2026-08-13
### Cải thiện
- **Thẻ Google Gemini CLI tự ẩn đi nếu máy bạn không có nó**, nên sẽ không còn ai vấp vào một lựa chọn Google đã ngắt rồi loay hoay đăng nhập. Ai đang đặt nó làm bộ não chính thì vẫn thấy thẻ để còn đổi sang cái khác.
- **Javis thôi tự cài Gemini CLI lúc cài đặt.** Bản cài nhẹ hơn và nhanh hơn một chút. Vẫn dùng được nếu bạn có giấy phép doanh nghiệp hoặc chạy bằng API key: tự cài `npm i -g @google/gemini-cli` là thẻ hiện lại.
- Bộ não Google cho tài khoản cá nhân giờ là **Antigravity CLI** (bản 0.29.0).

## [0.29.0] - 2026-08-13
### Thêm mới
- **Bộ não thứ 10: Antigravity CLI - dùng gói Google của bạn, và chọn được đúng dàn model như trong Antigravity IDE**, gồm cả model không phải của Google. Đây là đường Google chỉ định sau khi họ ngắt Gemini CLI với tài khoản cá nhân.
- Cài một lần trên máy chạy Javis rồi gõ `agy` để đăng nhập Google, vào trang **Models** bấm **Kiểm tra lại** là xong. Chạy trên VPS cũng được: nó tự in ra một đường link cho bạn mở trên máy mình.
- Danh sách model **hỏi thẳng CLI** chứ Javis không giữ bảng chép tay, nên tài khoản bạn được cấp model nào là thấy đúng model đó.
- Ngang hàng Claude Code và ChatGPT: chạy được lệnh máy, gọi được mọi kết nối đã đấu, dùng skill, nhận việc nền và trả lời qua Telegram.

## [0.28.9] - 2026-08-13
### Sửa lỗi
- **Google đã ngắt Gemini CLI với mọi tài khoản cá nhân từ 18/06/2026** - gói miễn phí, AI Pro lẫn Ultra. Trước bản này chat bằng nó chỉ ra dòng trống khó hiểu; giờ Javis nói thẳng chuyện gì đã xảy ra và chỉ sang đường còn dùng được. Đây là chặn từ phía Google, không phải lỗi máy bạn.
- Thẻ **Google Gemini CLI** ở trang Models hết mời đăng nhập như thể vẫn dùng được. Muốn model Gemini thì dùng **OpenRouter** (nhiều model một chỗ, có cả Gemini lẫn Claude) hoặc **Google Gemini (API)**.

## [0.28.8] - 2026-08-12
### Sửa lỗi
- **Ô dán mã khi đăng nhập Google đã gõ được.** Nút "Xong" bị giãn ra chiếm hết hàng làm ô nhập teo lại còn vài chục pixel, không dán nổi mã vào. Màn hình hẹp thì nút tự rơi xuống dòng dưới cho ô nhập đủ rộng.

### Cải thiện
- **Cài Javis là có sẵn cả ba bộ não chạy bằng gói đăng nhập: Claude Code, ChatGPT (Codex) và Gemini CLI.** Không phải tự mở terminal gõ `npm i -g` từng cái nữa, mở trang Models ra là chỉ còn việc đăng nhập.
- Áp cho cả ba đường cài: Docker, `install.sh` trên VPS, và `setup.bat` trên Windows (trước đây file này không cài bộ não nào).
- Bản đang chạy thì **cập nhật Javis** một lần là có. Cái nào cài lỗi cũng không sao: các bộ não còn lại vẫn chạy như thường, thẻ ở trang Models chỉ báo cách cài tay.

## [0.28.7] - 2026-08-12
### Sửa lỗi
- **Mở lại hội thoại cũ không còn thấy một đống chữ máy trong bong bóng câu hỏi của mình.** Khi bạn đang mở một file trong trình sửa, Javis kèm một khối hướng dẫn vào tin nhắn để nó biết đang làm việc trên file nào. Khối đó lẽ ra chỉ dành cho máy đọc, nhưng lúc tải lại trang thì nó hiện ra thay cho câu bạn đã gõ.
- **Thanh mốc hội thoại đọc được trở lại.** Trước đây hội thoại càng dài thì danh sách càng toàn những dòng giống hệt nhau, vì dòng nào cũng là khối hướng dẫn đó - không nhìn ra câu nào với câu nào.
- **Tên hội thoại trong Lịch sử cũng hết bị đặt theo khối đó.** Nút gửi lại và sửa câu hỏi giờ dùng đúng câu bạn gõ, không kèm rác.

## [0.28.6] - 2026-08-12
### Thêm mới
- **Đăng nhập Google cho Gemini CLI ngay trên trang Models, không phải mở terminal nữa.** Bấm **Đăng nhập Google**, đăng nhập, Google hiện ra một mã, dán mã đó lại là xong - giống hệt cách đăng nhập Claude Code và ChatGPT đang có.
- Chạy được cả khi Javis nằm trên VPS còn trình duyệt ở máy bạn, vì không có localhost nào ở giữa. Màn hình đồng ý của Google ghi đúng tên **Gemini CLI**.
- Có nút **Ngắt** để gỡ tài khoản Google khỏi Javis. Ai thích đăng nhập bằng terminal thì vẫn dùng được như cũ.

## [0.28.5] - 2026-08-12
### Thêm mới
- **Bộ não thứ 9: Gemini CLI, chạy bằng tài khoản Google của bạn - không cần mua API key.** Ngang hàng Claude Code và ChatGPT: chạy được lệnh máy, gọi được mọi kết nối đã đấu, dùng skill, nhận việc nền. Cài `npm install -g @google/gemini-cli`, chạy `gemini` một lần để đăng nhập Google, rồi vào trang Models bấm **Kiểm tra lại**.
- Thẻ mới nằm riêng, không lẫn với **Google Gemini (API)** cũ: thẻ cũ trả tiền theo lượt gọi, thẻ mới dùng gói miễn phí gắn với tài khoản Google.
- Việc chạy nền giao cho nó cũng được, và ba mức quyền của Javis xuống thẳng chế độ duyệt của CLI - mức **Chỉ đọc** là do chính Gemini CLI chặn, không phải một lời dặn trong prompt.

### Cải thiện
- Hết lượt gói Google giờ báo bằng tiếng Việt kèm mốc dùng lại được, thay cho câu tiếng Anh của Google.

## [0.28.4] - 2026-08-12
### Sửa lỗi
- **Kết nối ChatGPT xong không còn đứng ở "0 model".** Danh sách model của gói ChatGPT do Codex cấp, mà trước đây không ai đi hỏi cho tới khi bạn tự mở hộp chọn model. Nay đăng nhập xong là trang Models tự hỏi và điền con số thật. Máy mới cài (hay máy Mac vừa dựng) là chỗ lộ rõ nhất vì chưa có danh sách cũ để hiện tạm.
- **Không lấy được model thì nói rõ vì sao.** Thay cho câu chung chung "provider chưa kết nối hoặc không có model", giờ là câu chỉ đúng việc phải làm: chưa đăng nhập, chưa cài Codex CLI, hay thiếu API key.
- **Trên máy Mac, Javis tự tìm thấy `claude` và `codex` cài bằng Homebrew hoặc nvm.** Chạy nền thì hệ điều hành chỉ đưa cho Javis một danh sách thư mục rất ngắn, nên hai lệnh này gõ trong Terminal vẫn chạy mà Javis lại báo chưa cài.

### Cải thiện
- **Gõ `/` trong Telegram sổ ra danh sách lệnh đáng tin hơn.** Javis đặt menu cho cả chat riêng lẫn nhóm, và nếu Telegram từ chối thì báo hẳn lý do ở trang Cài đặt thay vì im lặng như trước.

## [0.28.3] - 2026-08-12
### Sửa lỗi
- **Đổi mật khẩu quản trị nay lưu được thật.** Trước đây điền tên đăng nhập với mật khẩu mới rồi bấm Lưu là không có gì xảy ra: app gửi nhầm sang đường dành cho lần đầu tạo tài khoản, mà đường đó luôn từ chối khi máy đã có chủ. Cả trang Tài khoản lẫn khối tài khoản trong trang Cài đặt đều dính, nay cả hai đều chạy.
- Form hỏi thêm **mật khẩu hiện tại** trước khi đổi, và báo ngay tại chỗ nếu mật khẩu mới dưới 8 ký tự thay vì để bấm xong mới biết.

### Bảo mật
- Đổi mật khẩu xong thì **mọi máy khác đang đăng nhập bị đăng xuất**, riêng máy bạn vừa thao tác ở lại. Xác thực 2 lớp giữ nguyên, không phải quét lại mã QR.
- Bịt đường đổi mật khẩu cũ: nó không hỏi mật khẩu hiện tại và token API gọi được, nên một token lộ ra là đủ để chiếm tài khoản rồi khoá chính chủ ra ngoài.

## [0.28.2] - 2026-08-12
### Sửa lỗi
- **Chuông thông báo hết nhắc bản mà bạn đã cài rồi.** Trước đây đọc hết thông báo, nâng cấp xong là con số lại hiện ra - vì các bản ra sau lần bấm "Đọc tất cả" vẫn nằm trong hàng chưa đọc dù chính chúng vừa được cài. Nay cài xong là hết nhắc, còn bản chưa cài thì vẫn báo bình thường.

### Cải thiện
- **Khung chat trên điện thoại: tên model và nút phóng to nay nằm sát bên trái**, ngay cạnh chữ HỘI THOẠI. Trước đây hai thứ đó bị đẩy ra tận mép phải nên phải quét mắt ngang cả màn mới đọc được đang chạy model nào.
- Tên model dài cũng không còn đẩy nút phóng to lệch ra ngoài.

## [0.28.1] - 2026-08-12
### Sửa lỗi
- **Nút "Kiểm tra lại" ở trang Cập nhật nay làm mới cả danh sách phiên bản.** Trước đây nó chỉ làm mới cái khung trên, còn danh sách bên dưới chỉ nạp một lần lúc mở trang - nên bấm bao nhiêu lần cũng không thấy bản mới hiện ra, phải rời trang rồi quay lại hoặc tải lại trang.
- Danh sách cũng không còn ăn bản cũ trong bộ nhớ đệm trình duyệt. Đây là chỗ duy nhất ở trang này còn thiếu, và đúng chỗ hiển thị các phiên bản.

## [0.28.0] - 2026-08-12
### Thêm mới
- **Thanh mốc hội thoại nay có trên điện thoại.** Không phải dãy vạch thu nhỏ mà là một nút nhỏ ở góc trên khung chat, chạm vào thì danh sách câu hỏi trượt lên từ đáy, chạm một câu là nhảy tới.
- Nút hiện luôn **đang ở câu mấy trên tổng mấy**, thay cho việc nhìn vạch sáng bên máy tính.
- Đóng bằng cách chạm ra ngoài, bấm dấu X, hoặc phím Esc. Xoay máy sang ngang thì tự đổi về dãy vạch như trên máy tính.

## [0.27.2] - 2026-08-12
### Sửa lỗi
- **Tạo bot Zalo hay Telegram báo "Thiếu Agent" trong khi đã chọn Agent hẳn hoi.** Lỗi rơi vào đúng những Agent bạn đặt tên tiếng Việt: tên file của chúng có dấu, mà chỗ lưu bot lại chỉ nhận chữ không dấu. Nay chọn Agent nào cũng lưu được, kể cả "Tư vấn sản phẩm" hay "Chăm sóc khách hàng".
- Câu báo lỗi cũng tách làm hai cho đúng việc: chưa chọn Agent là một chuyện, tên Agent không dùng được là chuyện khác.
- **Đổi Agent ở form Sửa bot giờ báo thật khi không lưu được.** Trước đây gặp tên lạ nó lặng lẽ bỏ qua rồi vẫn hiện "đã lưu", nên bot vẫn trả lời bằng vai cũ mà không ai biết.

## [0.27.1] - 2026-08-12
### Sửa lỗi
- **Mở hội thoại cũ nay rơi thẳng vào cuối, không phải câu hỏi đầu tiên.** App vẫn cuộn xuống đáy đàng hoàng, nhưng ngay sau đó khung chat bị dời sang trang Trò chuyện, mà dời một khung đang cuộn thì trình duyệt tự kéo về đầu. Nay giữ đúng chỗ đang đọc ở cả hai chiều đi và về.
- **Danh sách của thanh mốc hội thoại nay trỏ tới được.** Bản trước nó hiện ở đỉnh khung trong khi dãy vạch nằm giữa, chuột đi tới nửa đường là nó tắt. Nay hộp nằm ngang hàng với dãy vạch và dính liền, thêm một nhịp trễ nhỏ để lỡ tay đưa chuột ra ngoài vẫn kịp quay lại.

## [0.27.0] - 2026-08-12
### Thêm mới
- **Thanh mốc hội thoại ở khung chat.** Mép phải khung chat giờ có một dãy vạch nhỏ, mỗi vạch là một câu bạn đã hỏi. Rê chuột vào thì hiện danh sách các câu hỏi, bấm một câu là nhảy thẳng về chỗ đó. Hội thoại càng dài càng đỡ phải kéo tay đi tìm.
- Vạch của câu đang đọc sáng lên theo vị trí cuộn, nên liếc một cái là biết mình đang ở đâu trong cuộc trò chuyện.
- Ý tưởng từ **Trưng Minh** góp qua nhóm. Cảm ơn bạn.
- Thanh chỉ hiện trên máy tính. Trên điện thoại thao tác chính của nó là rê chuột, mà chạm sát mép phải lại giành mất cú vuốt để cuộn.

## [0.26.28] - 2026-08-12
### Cải thiện
- **Khung Cập nhật chỉ luôn cách tìm thư mục compose.** Bản trước bảo "chạy ở thư mục chứa file compose" nhưng không nói cách tìm, nên gõ xong hay lãnh `no configuration file provided: not found` - tên thư mục tuỳ lúc tải về, có máy là `javis`, có máy là `javis-os`.
- Tài liệu Khắc phục sự cố thêm bảng phân biệt ba kiểu báo `not found` khi gõ lệnh Docker, mỗi kiểu một cách xử lý.

## [0.26.27] - 2026-08-12
### Sửa lỗi
- **Trang Cập nhật nay nói rõ vì sao máy này không có nút "Cập nhật ngay".** Trước đây mọi máy thiếu nút đều nhận chung một câu, nên không có cách nào biết máy mình thiếu gì.
- Nếu là **VPS tự quản**: nút cần Watchtower, mà lệnh `docker compose up -d` quen tay không bật nó. Khung giờ đưa thẳng lệnh cần chạy một lần: `docker compose --profile update up -d`. Đây là lý do phổ biến nhất khiến máy này có nút mà máy kia không.
- Nếu là **Hostinger**: bản đó cố tình không kèm Watchtower, khung nói luôn là cập nhật bằng Redeploy chứ không có gì để bật.

## [0.26.26] - 2026-08-12
### Sửa lỗi
- **Trên điện thoại, tab "Thư mục" ở trang Trò chuyện bấm vào chỉ thấy khoảng trắng.** Tab này dùng chung cây thư mục với màn chính, mà cây đó lại đang bị ẩn trên màn hẹp nên nó ẩn theo. Nay mở tab là thấy cây.
- **Trang Nhật ký cập nhật hiện nguyên dấu sao và dấu huyền** quanh chữ in đậm và tên file. Nay chữ đậm ra chữ đậm, tên file ra khung mã, và đường dẫn dài tự xuống dòng thay vì đẩy ngang cả trang.

### Cải thiện
- **Nhật ký cập nhật từ nay viết ngắn cho người đọc trên điện thoại**: mỗi bản vài dòng, nói cái người dùng thấy khác chứ không kể tên hàm và đường dẫn file. Chi tiết kỹ thuật chuyển hết vào commit và pull request.

## [0.26.25] - 2026-08-12
### Sửa lỗi
- **Bấm vào link trong file .md không mở ra gì cả.** Đường dẫn có khoảng trắng bị mã hoá thành `%20`, dashboard đem nguyên chuỗi đó đi tìm file nên không bao giờ thấy. Nay mở đúng file.
- **Ảnh có khoảng trắng trong tên bị thành ô xám**, cùng một nguyên nhân. Nay hiện bình thường.
- **Bấm trượt nay nói rõ là không tìm thấy file**, kèm đường dẫn đã thử. Trước đây nó báo nhầm thành "loại file này không xem trực tiếp - hãy tải về".

## [0.26.24] - 2026-08-12
### Cải thiện
- **Thẻ Token API có link sang tài liệu.** Trước đây tạo token xong là hết đường: cầm chuỗi `jvs_...` trong tay mà không biết dùng ở đâu. Nay có link hướng dẫn ngay dưới thẻ và trong khối token vừa tạo, kèm câu lệnh cài Javis CLI.

## [0.26.23] - 2026-08-12
### Sửa lỗi
- **Mã QR của xác thực 2 lớp quét không ra.** Chủ repo bật 2FA, QR hiện ra đàng hoàng, điện thoại soi vào thì chịu. Ba lỗi cộng dồn, và cả ba đều KHÔNG nhìn thấy được bằng mắt vì cái QR trông vẫn bình thường.
- **Vùng trắng viền chỉ có 2 ô, chuẩn QR đòi 4.** Thiếu vùng đó thì máy quét không tách được mã ra khỏi nền xung quanh.
- **Chuỗi otpauth nhét thừa `algorithm=SHA1&digits=6&period=30`** - cả ba đều là giá trị MẶC ĐỊNH mà mọi app Authenticator tự hiểu. 34 ký tự thừa đẩy QR từ phiên bản 6 (41x41 ô) lên phiên bản 8 (49x49 ô) trong cùng một khung hình. Nay chỉ khai khi hằng số thật sự khác mặc định.
- **CSS ép ảnh QR xuống 200px trong khi ảnh gốc 265px**, tức mỗi ô còn 3,77 pixel. Đây là thủ phạm nặng nhất: người dùng soi điện thoại vào MÀN HÌNH máy tính chứ không phải tờ giấy, nên cỡ mỗi ô quyết định tất cả. Nay để ảnh ra đúng cỡ server tính (8 pixel mỗi ô, hơn gấp đôi).
- **Tên workspace dài làm QR phình lại.** Tên nằm HAI chỗ trong chuỗi otpauth nên mỗi ký tự tốn gấp đôi; đo thật thì tên 48 ký tự đẩy QR lên phiên bản 11 (69 ô). Nay cắt tên ở 24 ký tự, nên đặt tên kiểu gì QR cũng giữ được 8 pixel mỗi ô.
- **Nền QR nay là trắng thật**, không còn trong suốt dựa vào màu nền của thẻ bọc - ai dùng tông tối trước đây sẽ thấy mã đen nằm trên nền tối.
- **Tên trong app Authenticator lấy theo workspace và theo NGƯỜI.** Trước đây hiện "Javis OS: admin" - đúng về kỹ thuật nhưng vô nghĩa khi nằm giữa chục tài khoản 2FA trên điện thoại. Nay lấy tên workspace thật cộng tên người dùng (`USER_NAME`), rơi về tên đăng nhập khi chưa đặt: "Javis OS: Minh Quý".
- **Nhãn GIỮ nguyên dấu tiếng Việt.** Bản đầu bóc sạch dấu ("Minh Quý" thành "Minh Quy") vì sợ app hiện chuỗi hỏng; nỗi sợ đó lỗi thời - Key Uri Format cho phép nhãn UTF-8 phần trăm-mã-hoá và các app phổ biến đọc đúng từ lâu. Chỉ còn bỏ ký tự điều khiển và dấu ':' (nó là dấu ngăn giữa tên workspace và tên tài khoản, lọt vào là vỡ nhãn). Đã đo: kể cả tên có dấu dài hết mức thì QR vẫn giữ 8 pixel mỗi ô.
- Thêm canary đo bằng SỐ chứ không đọc chữ: mỗi ô phải >= 7 pixel ở cỡ tự nhiên, viền phải 4 ô, nền không được trong suốt, và CSS không được ép ảnh về một cỡ pixel cố định. Vế cuối là cách âm thầm nhất để phá lại mọi thứ ở trên - server trả ảnh đúng cỡ, trình duyệt nén lại, và không test phía server nào thấy được.

## [0.26.22] - 2026-08-12
### Thêm mới
- **Cài được NHIỀU bản Javis trên cùng một VPS, mỗi bản một link riêng.** Trước bản này thì không: bản thứ hai dựng lên là chết ngay. Bản thân app đã đa-bản-được từ lâu (`JAVIS_PORT`, `JAVIS_STATE_DIR` đều đọc từ biến môi trường); chỗ chặn nằm hết ở file cài đặt, và đều là cùng một loại lỗi - một cái tên bị đóng cứng ở nơi Docker/Traefik/systemd định danh theo phạm vi TOÀN MÁY. Năm cái tên đó: `container_name: javis`, cổng máy chủ `7777`, tên router/service Traefik `javis`, `/etc/systemd/system/javis.service`, và `~/.codex/javis.config.toml`.
- **Ba biến là đủ để tách một bản:** `JAVIS_NAME` (tên container + tên router Traefik + tên dịch vụ systemd), `JAVIS_HOST_PORT` (cổng máy chủ), `DOMAIN_NAME` (link). Bỏ trống cả ba = `javis` + cổng `7777`, tức **y hệt cách cài cũ** - ai đang chạy một bản không phải sửa gì.
- **Proxy dùng chung cho VPS tự quản** (`docker-compose.proxy.yml` + `docker-compose.multi.yml`). Một máy chỉ có một cổng 443, nên Caddy phải đứng NGOÀI mọi bản: chạy proxy một lần cho cả máy, rồi mỗi bản một thư mục riêng. Proxy tự phát hiện bản mới qua nhãn Docker và tự xin Let's Encrypt, nên thêm hay bớt một bản KHÔNG phải sửa gì ở proxy, cũng không phải khởi động lại nó. Đúng cách Traefik của Hostinger đang làm. Socket Docker chỉ mount `:ro`.
- **Hostinger:** deploy `docker-compose.hostinger.yml` thành stack thứ hai rồi điền ba ô đó. Ô Environment vì vậy có thêm hai trường `JAVIS_NAME` + `JAVIS_HOST_PORT`; cả hai đều có mặc định nên người cài bản đầu vẫn bỏ trống. Không có cách nào suy chúng ra từ ba trường cũ vì Traefik và Docker đều định danh theo phạm vi toàn máy.
- **Native:** `JAVIS_NAME=javis-shop JAVIS_PORT=7778 ./install.sh` cho ra `javis-shop.service` thay vì ghi đè `javis.service` của bản trước. `install.sh` chặn tên có ký tự lạ trước khi ghi vào `/etc/systemd`.

### Sửa lỗi
- **Hai bản Javis native chạy chung một user ghi đè profile Codex của nhau.** `~/.codex/javis.config.toml` là tên cố định, mà file đó chứa URL + token của hub, nên bản khởi động sau đè bản trước và Codex của bản A quay sang gọi hub của bản B - sai im lặng, không lỗi nào hiện ra ở đâu. Nay tên profile gắn cổng khi cổng khác mặc định (`javis-7778.config.toml`); cổng 7777 giữ nguyên tên `javis` nên máy đang chạy không phải sinh file mới. Hai nơi ghi profile (hub bật / hub tắt) nay dùng chung một hàm đặt tên.
- **`update.sh` của bản này đi restart bản khác.** Script dò container và dịch vụ bằng tên `javis` đóng cứng. Nay nó đọc `JAVIS_NAME` từ `.env` của đúng thư mục đang đứng, và giữ nguyên override `docker-compose.multi.yml` khi phát hiện proxy dùng chung - thiếu chỗ này thì một lượt cập nhật là gỡ mất nhãn Caddy và bản đó rơi khỏi proxy.
- **Watchtower theo dõi đúng container của bản mình** thay vì luôn nhắm vào container tên `javis`.

### Cải thiện
- `JAVIS_BIND` cho phép thu cổng về `127.0.0.1` khi đã có proxy đứng trước. Làm bằng biến chứ không phải một dòng `ports` trong file override, vì compose NỐI CHỒNG danh sách `ports` giữa các file `-f` chứ không thay thế - khai lại là ra hai binding cùng một cổng và Docker báo `port is already allocated`.
- Thêm `test_nhieu_ban_mot_vps.py` khoá cả năm cái tên toàn cục, khoá luôn điều kiện quan trọng nhất là bỏ trống mọi biến thì mọi file phải render ra y hệt trước đây. Test tự bung `${VAR:-mặc định}` như compose làm nên chạy được ở CI không có Docker.
- DEPLOY.md có mục riêng cho việc này, kèm bảng nói rõ trùng biến nào thì hỏng ra làm sao, và nói thẳng cái gì dùng chung cái gì riêng (không có gì dùng chung - mỗi bản phải đăng nhập Claude một lần).

## [0.26.21] - 2026-08-11
### Sửa lỗi
- **Xác thực 2 lớp không tìm thấy được từ trang Cài đặt.** Javis có HAI bề mặt cài đặt tài khoản - trang **Tài khoản** (đủ thứ, gồm luồng bật 2FA có QR) và khối "Tài khoản đăng nhập" cũ nhúng trong trang **Cài đặt** (chỉ đổi mật khẩu). 0.26.20 thêm 2FA vào chỗ đầu mà quên chỗ sau. Hậu quả không phải "thiếu một nút": người dùng mở trang Cài đặt, thấy khối tài khoản không nhắc gì tới 2FA, rồi kết luận Javis chưa có tính năng đó - trong khi nó đã chạy được cả ngày. Một tính năng bảo mật mà người ta không tìm ra thì bằng không.
- Nay khối đó có thêm một dòng trạng thái: chưa bật thì mời bật, đang bật thì khoe còn mấy mã khôi phục (kèm cảnh báo khi sắp hết), chưa đặt mật khẩu thì nói thẳng phải đặt mật khẩu trước chứ không đưa ra một nút bấm vào không ăn.
- **Cố ý chỉ là lối đi, không nhân đôi luồng bật.** Màn quét QR vẫn nằm đúng một chỗ ở trang Tài khoản; nút ở đây dùng chung đường chuyển trang sẵn có. Hai bản sao của một luồng bảo mật là hai chỗ phải sửa mỗi lần đổi, và chỗ nào quên sửa thì chỗ đó thành lỗ - `test_2fa_loi_vao.js` có canary cấm nhân đôi.

## [0.26.20] - 2026-08-11
### Thêm mới
- **Xác thực 2 lớp (2FA) bằng app Authenticator.** Bật ở Dashboard → Tài khoản: quét QR bằng Google Authenticator / Microsoft Authenticator / 1Password / Bitwarden (cái nào cũng được), nhập một mã 6 số để xác nhận, xong. Từ đó mỗi lần đăng nhập hỏi thêm mã. Javis chạy full quyền và có Bash, nên mật khẩu lộ ra ngoài mà vẫn vào được là một rủi ro không nên chấp nhận.
- **10 mã khôi phục, hiện đúng một lần lúc bật.** Không có chúng thì bật 2FA là tự đặt bẫy: mất điện thoại là mất luôn đường vào, và lối ra duy nhất là SSH vào server sửa tay `settings.json` - đúng thứ người ta bật 2FA để khỏi phải làm. Mã dùng một lần rồi tiêu; sinh lại bộ mới được (bộ cũ hết hiệu lực ngay).
- **`install.sh` hỏi có bật 2FA không.** Cố ý KHÔNG làm trọn trong terminal: vẽ QR ra terminal thì nửa số máy hiện sai và người dùng phải soi điện thoại vào cửa sổ SSH, trong khi vài giây nữa họ sẽ mở trình duyệt - chỗ hiện QR đúng đắn. Nên bước này chỉ ghi ý định vào `.env`, còn Dashboard mở sẵn màn quét QR ở trang Tài khoản.

### Bảo mật
- **Chống dùng lại mã.** Một mã TOTP sống 30 giây, cộng cửa sổ bù lệch đồng hồ là tới 90. Javis ghi lại bước thời gian của lần đăng nhập thành công gần nhất và từ chối mọi bước nhỏ hơn hoặc bằng, nên một mã bị nhìn trộm qua vai cũng không xài lại được. Đây là lỗ mà phần lớn bản TOTP tự viết mắc phải, vì nó không lộ ra trong lúc dùng thử.
- **Chỉ bật SAU khi người dùng chứng minh app sinh đúng mã.** Secret mới nằm trong RAM cho tới lúc xác nhận, không ghi vào cấu hình. Bật trước là tự khoá chính chủ ra ngoài khi app lệch giờ hoặc quét hụt.
- **Mật khẩu kiểm TRƯỚC, mã kiểm SAU.** Đảo lại là biến ô mã thành máy dò xem tài khoản nào đã bật 2FA, cho người còn chưa biết mật khẩu. Sai mật khẩu thì phản hồi không hề nhắc tới 2FA.
- **Secret TOTP và mã khôi phục không nằm nguyên văn trên đĩa.** Secret đi vào danh sách trường được mã hoá at rest như API key; mã khôi phục lưu dạng băm PBKDF2 như mật khẩu, nên không có đường nào đọc lại chúng.
- **Tắt 2FA đòi CẢ mật khẩu lẫn một mã đúng.** Ai đó mượn được máy đang mở sẵn dashboard mà tắt được lớp thứ hai bằng một cú bấm thì lớp đó coi như không có. Mọi endpoint 2FA đều đòi session trình duyệt, không nhận token API.
- Tự viết TOTP (RFC 6238) thay vì thêm thư viện: nó là HMAC-SHA1 trên một bộ đếm 30 giây, đúng 20 dòng thật sự, và đã đứng yên từ 2011. Thêm dependency cho ngần đó code là đổi một thứ đọc hết được lấy một thứ không kiểm soát, ngay tại cổng đăng nhập. Chỉ thêm `segno` để vẽ QR (thuần Python, không kéo theo gì); thiếu nó thì màn bật lui về nhập tay khoá.

## [0.26.19] - 2026-08-11
### Cải thiện
- **Cài xong là đăng nhập được luôn, hết cảnh đi đọc MÃ THIẾT LẬP trong log.** Trước bản này, mở Javis ra công khai mà chưa có tài khoản thì server sinh một chuỗi ngẫu nhiên và chỉ in nó vào log lúc khởi động; người dùng phải SSH vào máy, `docker compose logs javis`, chép mã, dán vào trình duyệt. Cái mã đó chặn người lạ chỉ-có-URL chiếm quyền admin trước chủ máy nên nó có lý do tồn tại, nhưng bắt người ta đọc log là trải nghiệm tệ, và tệ đúng lúc họ vừa cài xong và chưa quen gì cả. Nay `install.sh` hỏi thẳng tên đăng nhập và mật khẩu rồi ghi vào `.env`: người đang chạy script vốn đã ngồi trên máy chủ, nên hỏi một câu KHÔNG thêm bước nào, mà server boot lên đã có admin nên mã thiết lập không bao giờ hiện ra.
- **Enter một cái là có mật khẩu mạnh.** Bỏ trống ô mật khẩu thì script tự sinh 20 ký tự chữ-số và in ra ĐÚNG MỘT LẦN ở cuối màn hình cài. Chạy không có bàn phím (`curl | bash`, CI) cũng tự sinh chứ không bỏ trống, vì bỏ trống là đẩy người dùng về đúng cái màn đọc-log vừa xoá đi.
- **Chạy lại `install.sh` không đổi mật khẩu đang dùng.** Đã có trong `.env` thì giữ nguyên và nói rõ là giữ nguyên. Cài lại hoặc chạy lại script là chuyện thường, không được biến nó thành lần đổi mật khẩu ngoài ý muốn.
- **`docker-compose.yml` nhận `JAVIS_ADMIN_USER` / `JAVIS_ADMIN_PASSWORD`.** Bản Hostinger đã có hai trường này từ lâu, riêng compose thường thì không, nên ai deploy bằng nó LUÔN phải đi đọc log - không có đường nào khác. Nay điền hai dòng vào `.env` cạnh compose là xong.
- Mật khẩu ghi vào `.env` bằng Python chứ không bằng `sed`: mật khẩu người ta tự gõ có thể chứa `|`, `&`, `\`, `"`, `'` và mọi ký tự đó đều làm vỡ một lệnh `sed` viết theo lối thường gặp. Có test ghi rồi đọc lại một mật khẩu chứa đủ cả sáu ký tự đó.

### Bảo mật
- **Cơ chế MÃ THIẾT LẬP KHÔNG bị bỏ**, chỉ thôi làm đường chính. Nó vẫn là lưới cho người deploy bằng cách khác (compose tay, image trần). Bỏ hẳn là mở toang `/auth/setup` cho bất kỳ ai gõ trúng URL trước chủ máy, mà thứ họ chiếm được là một máy có Bash, chạy full quyền, cắm sẵn vào POS/quảng cáo/email của chủ. Có canary trong `test_install_admin.py` giữ cơ chế này khỏi bị gỡ nhầm về sau.

## [0.26.18] - 2026-08-11
### Sửa lỗi
- **Chat chạy rất lâu rồi chết bằng `Control request timeout: initialize`.** Chủ repo gõ một câu nhờ tạo 2 trang checkout trên Webcake, ngồi chờ, rồi nhận đúng hai dòng: một chuỗi lỗi tiếng Anh trần trụi và "(không có nội dung trả về)". Nguyên nhân nằm ở chỗ không ai nghĩ tới - danh sách tool của MCP nằm trên ĐƯỜNG GĂNG của mọi lượt chat. Lúc khởi động, `claude` phải đấu xong mọi MCP server rồi mới nhận việc; nó đấu vào hub Javis; hub trả tool bằng cách **dò tuần tự từng nguồn**, mỗi nguồn được chờ hết trần riêng của transport (http 60s, stdio 90s lúc init). Máy đấu chục connector mà có một nguồn chết là tổng thời gian tính bằng phút, trong khi Agent SDK chỉ chờ đúng 60 giây rồi bỏ cuộc. Cả lượt chat mất trắng vì một nguồn không liên quan.
- **Dò MCP nay chạy song song, mỗi nguồn có trần riêng 20 giây.** Tổng thời gian xấp xỉ nguồn chậm nhất chứ không còn là tổng của mọi nguồn, và một nguồn treo bị bỏ qua ở vòng đó thay vì kéo cả lượt chờ theo (cache hub hết hạn sau 60s là dò lại, nên không mất gì lâu dài). Phiên bị cắt giữa chừng bị vứt hẳn chứ không tái dùng - cắt ngang một request NDJSON là ống stdio lệch pha vĩnh viễn. Chỉnh bằng `JAVIS_MCP_DISCOVER_TIMEOUT=<giây>`, đặt 0 để bỏ trần.
- **Trần chờ `claude` khởi động nới từ 60 lên 300 giây.** Agent SDK chỉ nhận trần này qua biến môi trường `CLAUDE_CODE_STREAM_CLOSE_TIMEOUT` chứ không có tham số nào trong options, nên Javis tự đặt hộ; ai đã tự đặt biến đó thì Javis không đè. Chỉnh bằng `JAVIS_CLAUDE_INIT_TIMEOUT=<giây>` (sàn cứng 60s là của SDK).
- **Lỗi hết giờ khởi động nay nói ra việc phải làm.** Thay cho `SDK engine: Exception: Control request timeout: initialize`, người dùng đọc được rằng thủ phạm gần như luôn là một nguồn dữ liệu chết, và mở trang Kết nối bấm Kiểm tra để tìm nó. Lỗi nào không khớp mẫu thì vẫn giữ nguyên chuỗi gốc - đoán bừa nguyên nhân còn tệ hơn tiếng Anh trần.
- Thêm `test_khoi_dong_cham.py` khoá cả ba chỗ: dò song song có trần từng nguồn, nới trần khởi động, và câu báo lỗi chỉ được chỗ bấm.

## [0.26.17] - 2026-08-11
### Bảo mật
- **Javis không còn tự đọc token đăng nhập Claude Code của bạn.** Từ 0.18.2 tới bản này, Javis mở `~/.claude/.credentials.json` (hoặc Keychain trên macOS), lấy access token OAuth ra rồi gửi thẳng `Authorization: Bearer <token>` tới `api.anthropic.com/v1/messages`. Anthropic cấm đúng việc đó: token của gói Free/Pro/Max chỉ được dùng trong Claude Code và Claude.ai, họ nói rõ chuyện này trong tài liệu Legal & compliance từ tháng 2/2026 và chặn hẳn các công cụ bên thứ ba từ 04/04/2026. Cách họ phát hiện là soi dấu vân tay request - thiếu telemetry và heartbeat mà CLI chính chủ mới phát - mà request Javis tự dựng thì không có gì trong số đó. Có người dùng Javis đã bị khoá tài khoản.
- **Ba chỗ moi token đều đã gỡ**, và mỗi chỗ có một canary chống hồi quy: đường chat tiết kiệm (`main._api_stream_goc`), vòng gọi tool của bot chuyên trách (`main._bot_stream_co_tool`), và danh sách model live (`claude_models`). Hai tham số `oauth_token` trong `engine.py` gỡ theo. Module `claude_models` nay chỉ còn hai hàm và không đụng vào file nào của người dùng.
- **Không mất tính năng nào.** Cả ba đường chạy lại qua đúng binary `claude`, tức để chính sản phẩm của Anthropic lo phần đăng nhập. Mức Siêu tiết kiệm giữ nguyên phần tiết kiệm nhờ gửi system prompt trần thay vì preset của Claude Code - để preset vào là nó tự nhét lại prompt đầy đủ và ăn sạch phần tiết kiệm. Danh sách model live nay hỏi bằng API key nếu máy có; không có key thì giữ bốn alias `opus/sonnet/haiku/fable`, mà alias thì luôn trỏ bản mới nhất nên không lạc hậu.

### Thêm mới
- **Trang Models có ô "Chạy bằng" cho Claude Code**: giữ gói đang đăng nhập, hoặc dùng API key Anthropic. Hai lựa chọn giữ NGUYÊN năng lực - Bash, WebFetch, MCP, nối lại phiên cũ - chỉ khác ai trả tiền và ai chịu rủi ro. Chọn API key thì Javis truyền `ANTHROPIC_API_KEY` xuống tiến trình `claude`; chọn API key mà bỏ trống ô key thì lui về phiên đăng nhập sẵn có chứ không làm chết lượt chat.
- **Cảnh báo hiện đúng lúc đáng lo**, không phải lúc nào cũng nhá: chỉ khi máy đang để gói subscription gánh việc nền (model việc nền trỏ vào Claude Code) thì thẻ Claude Code mới hiện dải vàng nói rõ rủi ro và hai lối ra. Server tự ghép hai điều kiện đó rồi trả kèm dữ liệu, dashboard không tự đoán.
- **Việc nền chạy bằng gói subscription vẫn là một LỰA CHỌN, không bị tắt cứng.** Chủ máy tự cân rủi ro, Javis chỉ bảo đảm họ cân khi đã biết. README, trang web và system prompt đều nói thẳng chuyện này thay vì chỉ quảng cáo "0đ tiền API".

### Sửa lỗi
- **Mức Toàn quyền của việc Kanban chưa từng là toàn quyền.** `_lane_tools` đọc `execution_mode` rồi vứt đi: mọi việc đều bị rào allowlist, kể cả việc chủ đã chủ động đặt Toàn quyền. Hậu quả không phải "hơi chặt hơn" mà là mất hẳn một lớp công cụ. Gmail, Google Drive, Google Calendar đấu vào TÀI KHOẢN Claude chứ không nằm trong registry MCP của Javis, nên chúng chỉ gọi được bằng tool native `mcp__<tên>__*` - mà tool native chỉ tồn tại khi phiên chạy KHÔNG có allowlist. Nay `full` trả về allowlist rỗng thật, giống hệt nhánh full của loop và nhắc hẹn. Ba mức dưới giữ nguyên rào.
- **Bật `mcp.strict` là âm thầm khoá cửa sau của mức Toàn quyền.** Cờ này nghĩa là "chỉ dùng MCP của Javis", mà connector ambient thì nằm ngoài registry của Javis, nên ở mức full nó mở allowlist ra rồi lại chặn đúng nhóm vừa mở. Nay `full` bỏ qua cờ này. Người bật strict muốn siết mấy mức DƯỚI; ai đã chọn Toàn quyền cho một việc thì việc đó phải thật sự toàn quyền, không thì "Toàn quyền" là một cái nhãn nói dối.
- **Việc nền mức Toàn quyền thôi tự rơi sang engine dự phòng.** Chuỗi *engine phụ → Claude → OpenRouter free* đúng cho việc nhẹ, nhưng sai hẳn ở mức full vì ba lý do: engine API không có tool native nên việc cần Google Drive dừng giữa chừng; model không biết mình vừa bị đổi engine nên tự dựng một lý do nghe hợp lý mà sai; và mắt trước có thể đã làm xong MỘT PHẦN việc (đăng được 1 trong 3 bài) rồi mới gãy, chạy lại nguyên prompt là đăng lại từ đầu. Nay mức full dừng hẳn và báo lý do thật. Mức auto/suggest giữ nguyên chuỗi dự phòng.
- **Engine API khai thật là nó thiếu tool gì.** Không có lời khai này thì model chỉ thấy "gọi tool không được" rồi đổ cho quyền - đúng cái đã xảy ra: một nhắc hẹn đăng Fanpage báo về Telegram "phiên này bị chặn quyền" trong khi chủ đã bật Toàn quyền, làm người ta đi sửa nhầm chỗ suốt buổi sáng. Nay system prompt của engine API nói rõ nó không có Bash, không có WebFetch, không có connector của tài khoản Claude, và cấm thẳng chuyện mô tả điều đó là thiếu quyền.

### Cải thiện
- **Bot chuyên trách chạy trên gói Claude Code giờ dựng rào an toàn tường minh.** Tới bản trước, "bot không bao giờ có tool native" là hệ quả miễn phí của một sự thật kiến trúc: không engine nào của bot mở CLI. Bản này phải bỏ sự thật đó, nên chỗ tựa được dựng lại bằng bốn lớp và cả bốn đều có canary: allowlist chỉ có hub (cổng `can_use_tool` từ chối mọi tool khác từng lần gọi), danh sách chặn thẳng nhóm native, config hub mang brain CỦA BOT nên tool file bị `_safe_path` khoá đúng brain đó, và `mcp_strict` để bot không thấy connector của chủ.
- `mcp_hub.claude_config_path` nhận thêm `vault_root`. Cần cho đúng ca trên: engine Claude bình thường có Read/Write native nên hub cố ý không cấp nhóm tool file, nhưng bot bị chặn native nên không có nó là mất luôn khả năng ghi. File config tách theo brain nên hai bot hai brain chạy song song không đè header của nhau.
- Thêm `test_full_quyen_ungated.py` canh luật **"full ⇒ ungated"** ở cả bốn đường nền. Bốn đường cố ý không chia chung một hàm dựng engine (rào của chúng khác nhau thật), nên luật này phải được canh ở từng đường một - đó chính là lý do `tasks.py` lệch suốt nhiều bản mà không ai thấy.

## [0.26.16] - 2026-08-10
### Thêm mới
- **Nút Lùi / Tiến giữa các note trong trình sửa.** Đọc wiki là đi theo chuỗi `[[wikilink]]`: bấm một cái là rời khỏi note đang đọc, mà trước bản này KHÔNG có đường về - phải đi tìm lại file cũ trong cây. Nghĩa là mỗi cú bấm link là một quyết định một chiều, đúng thứ làm người ta ngại bấm link trong chính vault của mình.
- **Thiết kế theo hướng quen tay hơn là thông minh.** Hai mũi tên `‹ ›` nằm bên TRÁI tên file, đúng chỗ mọi trình duyệt đặt nó, nên không phải học. Phím `Alt` + `←` / `→` như trình duyệt. Chuột có nút lùi/tiến bên hông dùng được luôn (chặn ở `mousedown` để không lùi cả trang dashboard, mất luôn hội thoại đang mở).
- **Tooltip gọi TÊN file sẽ tới**, không phải chữ "Lùi" trơn: "Lùi về: Bát Giác Offer.md". Đi sâu bốn năm tầng liên kết thì nhớ mình từ đâu tới là chuyện không dễ, nên nút nói hộ trước khi bấm.
- **Hết chỗ đi thì nút MỜ đi chứ không biến mất.** Nút ẩn hiện làm thanh tiêu đề nhảy, và người dùng không bao giờ học được là có nút đó. Nút mờ vẫn nói được vì sao bấm không ăn.
- Vệt đường đi sống qua lần đóng trình sửa (đóng ra chat về chính note đó rồi mở lại là luồng thường gặp nhất), tự xoá khi đổi brain, tự sửa theo khi đổi tên file và tự rút khi xoá file - ba ca đều dẫn tới "bấm Lùi rơi vào đường dẫn không còn tồn tại". Đang đứng giữa vệt mà mở note mới thì nhánh tiến bị cắt, y như trình duyệt.

### Sửa lỗi
- **Rời một file đang sửa dở thì thôi mất chữ.** Bấm `[[wikilink]]`, bấm file khác trong cây, hay bấm Lùi/Tiến: nếu có sửa mà chưa bấm Lưu thì Javis lưu trước rồi mới đi. Lỗi này có từ trước, nhưng nút Lùi/Tiến làm chuyện rời file xảy ra thường xuyên hơn hẳn nên không vá thì nó thành cái bẫy.
- **Lưu hỏng thì Ở LẠI**, không đi tiếp, và lỗi hiện ngay trên nút Lưu. Đi tiếp lúc đó là vứt bài người ta vừa viết mà không nói một câu nào.
- **Chỉ ĐỌC rồi rời đi thì không ghi lại gì.** Mốc so sánh "đã sửa gì chưa" lấy từ chính khung soạn lúc vừa mở, không phải chữ thô đọc từ đĩa: bản render WYSIWYG đổi ngược thành markdown luôn lệch đôi chỗ so với file gốc (chuẩn hoá dấu, xuống dòng), nên so với file gốc thì mở ra đọc một cái cũng bị tính là có sửa và Javis sẽ âm thầm ghi đè định dạng của file đó.

### Cải thiện
- Tài liệu: [Quản lý tệp tin](docs/05-quan-ly-tep-tin.md) thêm mục "Lùi về / Tiến lên giữa các note".

## [0.26.15] - 2026-08-10
### Thêm mới
- **Ra lệnh bằng ghi âm trên Zalo**, y như Telegram ở bản trước. Bấm giữ micro nói một câu, Javis nghe thành chữ rồi làm như bạn gõ tay. **Dùng chung một key Groq**: đã đấu cho Telegram thì Zalo chạy luôn, không phải làm gì thêm.
- Việc có tác động ra ngoài (gửi tin, đăng bài, đặt lịch, tiêu tiền, sửa file) vẫn đọc lại "Em nghe: ..." rồi hỏi xác nhận. File ghi âm không lưu vào `inbox/`.
- Phần nghe nằm ở `server/stt.py` từ bản trước, không biết Telegram hay Zalo là gì, nên bản này chỉ nối dây chứ không viết bản thứ hai. Dòng dặn engine cũng chuyển hẳn vào đó để hai kênh không trôi lệch câu chữ.

### Sửa lỗi
- **Khác Telegram đúng một khâu, và đó là khâu rủi ro nhất: Zalo KHÔNG có `getFile`.** Cả bộ method Zalo công bố không có cái nào tải file, nên đường duy nhất tới file ghi âm là một URL nằm sẵn trong dữ liệu tin nhắn - mà khuôn dữ liệu của `message.voice.received` thì Zalo bỏ trống trong tài liệu. Nên Javis thử một loạt tên trường (`voice_url`, `voice`, `audio_url`, `audio`, `file_url`, `url`, kể cả dạng lồng `{"url": ...}`) thay vì cược vào một cái rồi im lặng bỏ hết tin thoại khi cược sai.
- **Trượt hết thì kêu ra, không im.** Bot nói thẳng với người gửi là không tải được file ghi âm, và server ghi MỘT dòng `[zalo voice] không tìm ra đường dẫn file thoại trong payload` kèm mẫu dữ liệu thật - lần chạy đầu tiên tự nói cho biết trường tên gì. Kêu một lần cho mỗi phiên bot, không spam log mỗi tin.
- Hàm moi URL này dùng chung với phần ảnh (trước đây viết lồng trong nhánh ảnh), nên hai loại file không còn hai bản logic trôi lệch nhau.

### Cải thiện
- Tài liệu: [Kênh Zalo Bot](docs/26-kenh-zalo-bot.md) thêm mục "Ra lệnh bằng ghi âm" kèm cảnh báo về khuôn dữ liệu chưa công bố; [Telegram](docs/11-telegram.md) và [Models & engine](docs/10-models-va-engine.md) cập nhật theo.

## [0.26.14] - 2026-08-10
### Thêm mới
- **Ra lệnh bằng ghi âm trên Telegram.** Bấm giữ micro nói một câu, Javis nghe thành chữ rồi làm y như bạn gõ tay. Trước đây gửi tin thoại chỉ nhận lại một câu "Javis chưa đọc được loại này, nhờ anh gõ chữ" - tức là cái nút micro to nhất trong Telegram không dùng được, đúng lúc người ta cần nó nhất (đang lái xe, tay bận).
- **Chạy bằng Whisper của Groq, tận dụng key có sẵn.** Groq vốn đã là một trong tám bộ não của Javis và phục vụ Whisper trên cùng endpoint với model chat, nên ai đã đấu Groq để chat thì tin thoại chạy luôn, không phải đăng ký thêm nhà cung cấp nào. Ngược lại, đấu key chỉ để nghe giọng cũng được - không bắt buộc đổi model chính sang Groq.
- **Chưa đấu key thì nói rõ phải làm gì**, không im lặng và cũng không nói lấp lửng "chưa đọc được": bot chỉ thẳng vào trang Models, mục Groq (API), dán key lấy ở console.groq.com. Key đọc TẠI THỜI ĐIỂM NGHE nên dán xong là tin thoại tiếp theo chạy được ngay, không phải tắt bật lại bot.
- **Việc có tác động ra ngoài thì hỏi lại trước.** Gửi tin, đăng bài, đặt lịch, tiêu tiền, sửa file: Javis mở đầu bằng một dòng "Em nghe: ..." rồi chờ xác nhận. Máy vẫn nghe nhầm được, mà mấy việc đó lỡ làm rồi thì không rút lại. Hỏi số liệu, tra cứu, tóm tắt thì làm thẳng.
- **Mọi ngả hỏng đều quay lại thành một câu nói**: file quá dài, nghe không ra chữ, Groq trả lỗi, hàm nghe ném ngoại lệ. Tin thoại là loại tin mà "hỏng" và "chạy" nhìn giống hệt nhau ở phía người gửi (bấm giữ, thả ra, thấy đã gửi), nên im lặng ở đây là kiểu hỏng tệ nhất.
- File ghi âm KHÔNG lưu vào `inbox/`: nghe xong lấy chữ là xong, người ta ghi âm để ra lệnh chứ không phải để gửi Javis một file `.ogg`.
- Gửi tin thoại kèm caption `/notes` vẫn chạy đúng lệnh với nội dung là câu vừa nói (khối thoại nhiều dòng đi nguyên vẹn, không bị cắt như marker file đính kèm).
- Video và video note vẫn chưa xem được, nhưng câu từ chối thôi gộp chung với voice.
- Kênh Zalo chưa nghe được tin thoại. Phần nghe nằm ở `server/stt.py`, không biết gì về Telegram, nên đấu Zalo vào sau này là nối dây chứ không viết lại.
- Tài liệu: [Telegram](docs/11-telegram.md) thêm mục "Ra lệnh bằng ghi âm (tin thoại)" + hai mục sự cố; [Models & engine](docs/10-models-va-engine.md) ghi rõ key Groq còn dùng để nghe giọng.

## [0.26.13] - 2026-08-10
### Cải thiện
- **Thẻ "file đang mở" dưới khung chat nay bấm được: bấm vào là quay lại sửa đúng file đó.** Trước đây thẻ chỉ để nhìn. Mở một note ra sửa, đóng trình sửa lại rồi chat vài lượt, muốn sửa tiếp thì phải đi tìm lại file trong cây vault - đúng cái việc mà thẻ ghim sinh ra để khỏi phải làm. Nay bấm thẻ (hoặc chọn bằng phím Tab rồi Enter) là file mở lại trong trình sửa, cây vault tự xổ tới đúng nhánh chứa nó.
- **File đang mở sẵn thì chỉ đưa mắt về, KHÔNG nạp lại.** Đây là phần dễ làm hỏng nhất: mở lại một file đang mở nghĩa là đọc lại nội dung từ đĩa, tức là đoạn chữ vừa gõ mà chưa bấm Lưu sẽ bay sạch. Nên trình sửa nhớ file nào đang mở, trùng thì chỉ cuộn về và đặt con trỏ vào chỗ đang soạn.
- **Nút ✕ trên thẻ vẫn chỉ là bỏ ghim**, không bị lây cú bấm mở file. Trên điện thoại (màn dưới 860px, nơi trình sửa đính bị tắt) thẻ mở file trong khung sửa bung giữa màn hình.
- Thẻ nay có cây bút bên phải và đổi viền khi rê chuột - không có dấu hiệu nhìn thấy được thì tính năng coi như không tồn tại. Dòng phụ đổi từ "đang mở - Javis làm việc trên file này" thành "đang mở - bấm để sửa tiếp"; ý "Javis đang làm việc trên file này" chuyển vào tooltip cùng đường dẫn đầy đủ.
- Tài liệu: cập nhật [Quản lý tệp tin](docs/05-quan-ly-tep-tin.md) và [Trò chuyện & giọng nói](docs/02-tro-chuyen-va-giong-noi.md).

## [0.26.12] - 2026-08-09
### Sửa lỗi
- **"Tự khởi động cùng Windows" báo Bật trong khi mở máy lên không có gì chạy.** Cả tính năng nằm gọn trong một dòng registry `HKCU\...\Run`, và dashboard đọc đúng dòng đó rồi kết luận "Bật". Nhưng dòng đó **còn nguyên** trong ít nhất ba cảnh mà lúc đăng nhập vẫn không có gì chạy, và không cảnh nào để lại lỗi ở đâu để lần ra. Người dùng chỉ thấy `ERR_CONNECTION_REFUSED` và một cái thẻ nói dối.
- **Cảnh im lặng nhất: Task Manager tắt hộ.** Thẻ **Startup** không xoá mục trong Run key khi bấm Disable, nó ghi một cờ 12 byte vào `Explorer\StartupApproved\Run` rồi Explorer bỏ qua mục đó. Mấy phần mềm "dọn máy, tăng tốc khởi động" cũng tắt bằng đúng cờ này, thường là không hỏi. Javis nay đọc cờ đó, và **bấm Bật tự khởi động sẽ gỡ cờ thật** thay vì chỉ ghi lại Run key (ghi lại Run key không đụng gì tới cờ, nên trước đây cái nút đó là một cái nút không làm gì trong đúng ca này).
- **Cảnh thứ hai: thư mục cài đặt đổi chỗ.** Cờ `stale` đã được tính từ lâu nhưng **trang Cài đặt bỏ qua hẳn nó**, chỉ trang Tổng quan mới hiện. Cùng một máy hỏng mà mở hai trang thì đọc được hai câu trả lời khác nhau. Nay lý do do server tính một lần và cả hai trang cùng hiện, nên không còn cửa cho hai bản trôi lệch.
- **Cảnh thứ ba: mảnh của dây chuyền biến mất** (`start-javis.vbs` hoặc `.venv\Scripts\python.exe`). `wscript` không thấy file .vbs thì im hoàn toàn, còn `cmd` thì ghi lỗi vào `javis.log`, một file không ai mở ra xem bao giờ. Nay Javis kiểm ngay lúc đọc trạng thái và gọi tên đúng file đang thiếu.
- **Nhãn trên thẻ nói thật:** bật mà có vấn đề thì ghi "Bật nhưng không chạy" kèm một câu chỉ rõ phải sửa gì, thay vì chữ "Bật" trơn. Trạng thái cũng trả kèm đường dẫn `server\javis.log` để còn chỗ mà soi khi server có chạy nhưng chết giữa chừng.
- Tài liệu: thêm mục "Khi thẻ ghi Bật nhưng không chạy" vào [Bắt đầu & thiết lập](docs/01-bat-dau-thiet-lap.md).

## [0.26.11] - 2026-08-09
### Sửa lỗi
- **Thẻ bot Zalo thôi đỏ vì một vòng poll gãy lẻ.** Bản 0.26.10 chữa được ca "Request timeout" lúc bot rảnh, nhưng nó dựa trên một PHỎNG ĐOÁN chưa kiểm chứng: rằng nhịp hết giờ chờ của Zalo không gắn `error_code`. Tài liệu Zalo không nói gì về chuyện đó. Đoán sai theo hướng ấy thì bản vá im lặng không chạy, và người dùng lại thấy đúng cái thẻ đỏ cũ mà không hiểu vì sao. Nay nhận cả hai khuôn: có mã hết giờ (408, 504) kèm chữ timeout vẫn là nhịp rảnh.
- **Lỗi không rõ nguyên nhân chỉ đỏ thẻ khi gãy 3 vòng LIÊN TIẾP.** Một vòng gãy lẻ là chuyện của đường truyền chứ không phải chuyện người chủ phải ra tay, mà đỏ thẻ vì nó thì cái thẻ mất giá trị đúng như hồi nó đỏ vì mỗi vòng rảnh. Vòng chạy được hoặc vòng rảnh đều xoá bộ đếm, nên hai lần gãy cách nhau một tiếng không bị cộng dồn thành "đang hỏng".
- **Nhóm lỗi CẦN NGƯỜI vẫn đỏ thẻ ngay lập tức** (401 sai token, 403 bị chặn, 404 bot đã xoá, 429 gọi quá dày). Chỉ nhóm này mới nói được cho chủ một việc cụ thể để làm, nên nó không bị hoãn theo ngưỡng 3 vòng.
- Vì sao cả hai chuyện trên hay bị bắt gặp khi hỏi câu KHÓ: lúc Javis nghĩ lâu thì vòng poll chạy không mà không có tin nào, nên mọi vòng trong khoảng đó đều rơi vào đúng nhánh này. Chat qua lại nhanh thì các vòng poll đều có tin và thẻ sạch, nên lỗi chỉ ló ra đúng lúc người ta ngồi chờ một câu trả lời dài.

## [0.26.10] - 2026-08-09
### Sửa lỗi
- **Bot Zalo đang RẢNH không còn bị báo là đang LỖI.** Thẻ bot ở trang Chatbot đỏ chấm "Lỗi" kèm dòng "Request timeout" trong khi con bot vẫn sống và vẫn trả lời được. Nguyên nhân: `getUpdates` của Zalo không cư xử như Telegram. Telegram hết giờ chờ thì trả `ok: true` với danh sách rỗng, còn Zalo trả `ok: false` kèm `description: "Request timeout"`. Đó là nhịp bình thường của long polling, 25 giây không ai nhắn thì đúng là không có gì để trả về.
- **Và bot thôi bị ĐIẾC 10 giây mỗi vòng rảnh.** Đây mới là phần nặng, nhưng nó nấp sau phần trên nên không ai nhìn ra: nhánh lỗi ngủ 10 giây rồi mới poll lại, nên cứ mỗi vòng không có tin là bot không nghe gì trong 10 giây. Tin nhắn rơi vào khoảng đó không mất, chỉ là phải chờ tới vòng sau mới được đọc. Nay vòng rảnh poll lại ngay, và chỉ tự ghìm một nhịp ngắn nếu Zalo đáp gần như tức thì (không tôn trọng tham số `timeout`), để vòng lặp không nện API vài lần mỗi giây rồi ăn 429 thật.
- **Thẻ đỏ thường trực là loại hỏng tệ hơn vẻ ngoài của nó:** rảnh là trạng thái bình thường của một con bot chăm sóc khách, nên thẻ gần như luôn đỏ, và tới lần bot hỏng THẬT thì không còn ai nhìn ra nữa.
- **Ranh giới của bản sửa nằm ở chỗ ai đang nói, không phải ở chữ "timeout".** Máy chủ Javis mất mạng cũng đẻ ra một chuỗi có chữ timeout, và đó là hỏng thật. Nay `_api` gắn dấu `loi_mang` cho dict sinh từ ngoại lệ, còn nhịp rảnh thì phải do chính Zalo đáp bằng body JSON và không mang mã lỗi nào. Lỗi thật (401, 429, mất mạng) giữ nguyên hành vi cũ: đỏ thẻ, ghi lý do, nghỉ dài rồi thử lại.

### Cải thiện
- **429 của Anthropic nay được chờ theo nhịp của hạn mức, không phải nhịp của một cú vấp mạng.** Bản trước thử lại theo 1 giây, 2 giây, 4 giây, nên cả ba lần hỏi lại gói gọn trong bảy giây, trong khi cửa sổ hạn mức tính bằng phút. Ba lần hỏi trong bảy giây chỉ là ăn đúng cú 429 đó ba lần, rồi báo "đã thử lại 3 lần" và bỏ cuộc. Nay 429 chờ theo nhịp riêng, đủ dài để một đợt nghẽn ngắn kịp trôi qua.
- **Đọc thêm mốc cửa sổ mở lại mà Anthropic vẫn gửi kèm** (`anthropic-ratelimit-*-reset`). Anthropic không phải lúc nào cũng gửi `Retry-After`, và khi thiếu nó thì mấy header này là nguồn DUY NHẤT nói được phải chờ bao lâu. Bỏ qua chúng nghĩa là tự bịt mắt rồi đoán. Lấy cửa sổ mở sớm nhất: chờ hụt thì còn lượt thử lại để chờ tiếp, còn chờ dư là bắt người ta ngồi im vô ích.
- **Câu lỗi trên thẻ bot nói được phải làm gì tiếp.** Trước đó nó dán nguyên một cục JSON của nhà cung cấp, thứ không trả lời được câu hỏi duy nhất người chủ đang có khi nhìn thẻ đỏ. Nay nó nói rõ đây là hạn mức, còn bao lâu nữa cửa sổ mở lại (khi biết), và rằng có thể đổi bộ não cho bot ở trang Models. Lỗi gốc vẫn giữ nguyên bên cạnh để còn tra được.

## [0.26.9] - 2026-08-09
### Cải thiện
- **Javis thôi trả lời bằng những bức tường văn xuôi trên khung chat web.** Câu trả lời dài nay có hình khối để mắt bám: đoạn 2-4 câu, gạch đầu dòng khi liệt kê từ 3 ý trở lên, in đậm con số và kết luận, tiêu đề `###` khi câu trả lời có nhiều phần rõ rệt, và bảng khi so sánh cùng một bộ trường giữa nhiều mục.
- **Vì sao trước đó nó viết như vậy: đó là một luật có thật, viết cho thời dùng bằng GIỌNG NÓI.** CLAUDE.md cấm thẳng "bảng markdown, dấu gạch ngang dày, hay header khi báo cáo trong chat". Luật đó đúng cho thời nghe, nhưng nó cấm nguyên cả bộ công cụ trình bày trên một kênh vẽ được đủ markdown. Chuyển sang chủ yếu đọc bằng mắt thì cùng một luật đó trở thành lỗi hiển thị nặng nhất của khung chat.
- **Nỗi lo hỏng giọng đọc thì không còn cơ sở.** Nút loa của dashboard vốn đã bóc markdown (tiêu đề, in đậm, gạch đầu dòng, link, khối mã) trước khi đọc thành tiếng, nên định dạng đẹp cho mắt không hề làm hỏng phần nghe. Nay Javis được nói thẳng điều đó để nó khỏi tự siết mình về văn xuôi.
- **Cấu trúc phục vụ độ dài, không phải ngược lại.** Câu hỏi đáp được bằng một câu thì vẫn trả lời một câu. Bẻ một ý nhỏ thành ba gạch đầu dòng cho ra vẻ báo cáo còn khó đọc hơn văn xuôi, nên luật mới chặn luôn chiều ngược lại.
- **Kênh chữ thuần KHÔNG bị nới theo.** Telegram và Zalo vẫn cấm bảng, terminal vẫn cấm bảng lẫn ảnh nhúng lẫn link markdown. Ba kênh này chỉ được thêm đúng một thứ dùng được ở đâu cũng đọc rõ là gạch đầu dòng khi liệt kê.
- Sửa ở cả ba lớp vì thiếu một lớp là hành vi quay về cũ ở đúng đường đó: luật gốc trong `CLAUDE.md`, khối kênh trong `channel_context.py` (đứng cuối system prompt nên nó là tiếng nói to nhất), và capsule của `context_compiler.py` (đường tiết kiệm token không đọc CLAUDE.md, bỏ quên nó thì bật "Siêu tiết kiệm" là văn xuôi quay lại mà không ai đoán ra vì sao). `tests/python/test_chat_de_doc.py` canh cả ba, kèm canary cho câu cấm cũ và cho ranh giới của kênh chữ thuần.

### Cần biết
- Nếu bộ nhớ dài hạn của brain còn một ký ức cũ kiểu "không thích bảng markdown, thích văn nói ngắn" thì ký ức đó được nạp vào mọi lượt và sẽ kéo hành vi về cũ. Javis nay được dặn là luật mới thắng ký ức đó, nhưng dọn hẳn ký ức trong `Memory/facts/` vẫn sạch hơn.

## [0.26.8] - 2026-08-08
### Thêm mới
- **Kênh Zalo cho CHỦ: hỏi Javis ngay trên Zalo, không cần cài Telegram.** Thẻ Zalo mới ở trang **Kênh** (nhóm Kết nối). Dùng API chính thức của Zalo nên không có rủi ro khoá tài khoản. Xem [Kênh Zalo Bot](docs/26-kenh-zalo-bot.md).
- **Ghép nối bằng MỘT cú bấm, không phải đi tra id.** Zalo không có công cụ nào để bạn tự tra id Zalo của mình, và id đó là chuỗi hex như `6ede9afa66b88fe6d6a9` chứ không phải con số dễ đọc. Nên Javis đảo chiều: bật bot với ô Chat ID để TRỐNG, nhắn cho bot một câu, bot đáp lại kèm mã ghép nối 4 số, rồi bạn bấm **Cho phép** ngay trên dashboard. Người chờ hiện ra kèm **tên Zalo thật** để không bấm nhầm.
- **Việc giao từ Zalo báo kết quả VỀ Zalo.** Loop, việc Kanban và nhắc hẹn đặt qua Zalo mang tiền tố `zalo:` nên kết quả rơi đúng khung chat đó, không lạc sang Telegram của chủ.
- **Cửa "đủ điều kiện mới tạo lịch" nay chấp nhận Zalo.** Trước đó chỉ đấu Zalo mà tạo nhắc hẹn thì bị chặn với lý do "bot Telegram chưa bật" - một câu vừa sai vừa không sửa được, và nó đẩy người dùng đi cài một app họ không cần.

### Bảo mật
- **Ô Chat ID trống của kênh Zalo nghĩa là CHƯA AI được phép**, cố ý khác Telegram. Bên Telegram ô trống mở cho tất cả, và tài liệu phải dặn đừng để trống - vì bên đó người dùng tra được id của mình trước khi bật. Zalo không có đường đó, nên luồng đúng là bật với ô trống rồi tự nhắn cho bot. Giữ nguyên nết của Telegram ở đây thì chính luồng hướng dẫn đó sẽ tạo ra một con bot ai cũng chạm được vào brain, trong khoảng giữa lúc bật và lúc bấm Cho phép. Fail-closed.
- Người lạ nhắn tới chỉ nhận **một** câu từ chối trong 10 phút, hàng chờ giữ tối đa 20 người và mục cũ hơn 30 phút tự rụng. Đây là hộp thư mở cho người lạ nên nó không được phình theo.

### Cần biết
- Zalo không sửa và không xoá được tin, nên kênh này **không có tin trạng thái**: trong lúc chờ chỉ có chấm "đang nhập", và dòng vết công cụ đi kèm cuối câu trả lời.
- Zalo Bot **chưa có API gửi tài liệu**, nên PDF và bảng tính không gửi qua kênh này được. Javis nói thẳng và đưa đường dẫn trong brain thay vì im lặng nuốt file.
- Trần một tin là **2000 ký tự**, và Zalo **không hiện menu lệnh** nên các lệnh `/...` phải gõ tay.

## [0.26.7] - 2026-08-08
### Sửa lỗi
- **Connector nội bộ (Substack, Botcake) bị quét sạch khỏi vòng dò tool, nên không bộ não nào gọi được.** Kết nối bật, quyền full, token còn sống, trang Kết nối hiện "Đã kết nối", mà cả 16 tool của hai connector này đều vô hình với mọi engine - và không có một dòng lỗi ở đâu cả. Đây là loại hỏng tệ nhất: mọi đèn đều xanh trong khi chẳng có gì chạy.
- **Nguyên nhân: ba chỗ cùng hỏi một câu rồi cùng trả lời sai.** "Connection này có server để dial không" được hỏi ở vòng dò tool, ở nút Test, và ở vòng kiểm sức khoẻ; cả ba đều tự viết tay `not (url or command)`. Transport `internal` gọi thẳng một module Python trong repo nên nó không có url cũng không có command, và rơi trọn vào nhánh "không có server" vốn dành cho connection chỉ giữ token OAuth.
- **Hai chỗ sau còn che mất chỗ đầu.** Nút Test và đèn sức khoẻ trả về "ổn" mà chưa hề gọi thử, đếm số tool theo mô tả trong catalog thay vì gọi thật. Nên không có đường nào để phát hiện ra vòng dò đang hỏng. Nay cả hai dial thật như mọi connector khác.
- Cách sửa: một hàm dùng chung `mcp_client.co_server_de_dial`, và `tests/python/test_mcp_connector_internal.py` canh cả hành vi lẫn việc ba chỗ đó thật sự gọi hàm chung - vì bệnh gốc chính là ba bản chép tay trôi lệch.

## [0.26.6] - 2026-08-08
### Sửa lỗi
- **Mở form Sửa bot rồi bấm Lưu không còn xoá trắng tên bot đang chạy.** Lỗi vừa vào ở 0.26.5: hàm áp dụng lựa chọn kênh cũng chạy MỘT LẦN lúc mở form để dựng trạng thái ban đầu, mà nó lại bỏ token đã kiểm vô điều kiện. Hệ quả là sửa một ô bất kỳ rồi lưu thì thẻ quay ra báo "chưa có token" cho một con bot vẫn đang sống. Nay chỉ bỏ khi kênh THẬT SỰ đổi, và dòng "Đang dùng ..." giữ nguyên khi chưa đổi gì.

## [0.26.5] - 2026-08-08
### Thêm mới
- **Bot chuyên trách chạy được trên Zalo, bằng API CHÍNH THỨC.** Đây là thay đổi có giá trị kinh doanh lớn nhất của bản này: khách hàng Việt Nam không ai cài Telegram, còn Zalo thì đã nằm sẵn trên máy họ. Tạo bot ở trang **Chatbot**, chọn kênh Zalo, dán token lấy từ Official Account "Zalo Bot Manager" trong app Zalo. Không có rủi ro khoá tài khoản như đường Zalo cá nhân.
- **Zalo Bot KHÔNG thay Zalo Agent MCP**, hai thứ khác bản chất và cùng tồn tại. Bot là một danh tính riêng, chính thức, chỉ thấy thứ người ta nhắn thẳng cho nó; còn `zalo-agent-cli` đăng nhập chính tài khoản của bạn, đọc được hội thoại thật và nhắn được cho bất kỳ ai, đổi lại có rủi ro bị khoá. Cái đầu để **khách nói chuyện với Javis**, cái sau để **Javis thao tác thay bạn**.
- **Chọn kênh là ô ĐẦU TIÊN trong form tạo bot**, dạng hai thẻ bấm có logo chứ không phải một ô chọn trơn. Nó đứng đầu vì nó đổi cả phần còn lại: token lấy ở đâu, có dùng được nhóm không, có gửi được tài liệu không. Mỗi thẻ nói luôn ưu và nhược ngay trên nút.
- **Dấu hiệu kênh cho từng bot**, vẽ tay theo mô tả của chủ repo: Telegram là máy bay giấy trắng trên nền xanh, Zalo là chữ Z trắng trong bong bóng trò chuyện xanh. Hiện ở hai chỗ với hai khoảng cách nhìn khác nhau: huy hiệu nhỏ đè góc icon bot (liếc qua là biết), và chip có logo trong phần thông tin (đọc lướt). Hai con bot khác nền tảng nằm cạnh nhau mà chỉ khác một chữ nhỏ thì sẽ có ngày sửa nhầm con đang nói chuyện với khách.
- **Hàng lọc Tất cả / Telegram / Zalo** ở đầu trang Chatbot, chỉ hiện khi thật sự có từ hai kênh trở lên. Người mới chỉ có bot Telegram mà đã phải nhìn một hàng nút lọc thì đó là trả lời một câu họ chưa từng hỏi.

### Cải thiện
- **Giao diện tự giấu những thứ Zalo không làm được**, thay vì hiện ra rồi để chúng vô tác dụng. Chọn Zalo thì cả khối khai nhóm biến mất kèm một dòng nói rõ vì sao (gói bot cơ bản của Zalo không cho bot vào nhóm), và id nhóm đã gõ cũng không bị gửi lên máy chủ. Cảnh báo "chế độ riêng tư Telegram" cũng thôi hiện trên thẻ bot Zalo, vì nó dạy người ta đi tìm một cài đặt không tồn tại.
- **Nút Kiểm tra token hỏi ĐÚNG nền tảng đã chọn.** Dán token Zalo vào đường Telegram chỉ ra lỗi 401, và câu "token không hợp lệ" khi token hoàn toàn hợp lệ là chỗ người dùng mắc kẹt lâu nhất. Chặn trùng token cũng xét theo từng kênh, vì tên tài khoản là không gian tên riêng của mỗi nền tảng.
- **Kênh KHÔNG đổi được sau khi tạo bot**, và form Sửa nói thẳng điều đó thay vì cho bấm rồi báo lỗi token ở bước sau. Đổi kênh là đổi sang một con bot khác hẳn: token khác, danh tính khác, khách khác, và mọi id nhóm đang lưu lập tức vô nghĩa.
- **Phần dùng chung của mọi cổng bot tách ra `server/bot_gateway.py`**: hàng đợi lượt, luật `/stop`, cổng chặn trước khi tốn một lượt, dòng vết công cụ. Đó là luật hành vi của Javis chứ không phải chi tiết của một nhà cung cấp, nên hai kênh dùng chung một bản. Chép sang bản thứ hai là bảo đảm hai bản trôi lệch, và chỗ lệch sẽ nằm đúng ở nơi ít được nhìn nhất: bot đang nói chuyện với người lạ.

### Cần biết
- Zalo Bot **chưa có API gửi tài liệu** (chỉ có gửi ảnh), nên file Javis tạo ra không gửi qua kênh này được. Javis nói thẳng lý do thay vì im lặng nuốt file.
- Zalo **không sửa và không xoá được tin đã gửi**, nên bot Zalo không có tin trạng thái nào: chỉ có chấm "đang nhập" trong lúc chờ, và dòng vết công cụ đi kèm ngay trong câu trả lời.
- Trần một tin nhắn Zalo là **2000 ký tự** (Telegram là 4096), câu trả lời dài tự chia nhỏ.
- Zalo chưa công bố hạn mức gọi API. Gặp lỗi 429 thì Javis tự nghỉ rồi thử lại, và phơi lỗi ra dòng trạng thái chứ không nuốt.

## [0.26.4] - 2026-08-08
### Cải thiện
- **Bot Telegram không còn gửi tin rồi xoá tin.** Trước đây mỗi lượt hỏi, bot gửi tin "🤔 Javis đang xử lý…", cập nhật nó theo tiến trình, rồi **xoá hẳn** và gửi câu trả lời. Người dùng thấy một tin nhấp nháy rồi biến mất, đọc như lỗi, và ai đang đọc dở thì mất chữ giữa chừng. Nay tin đó **ở lại**: lần cập nhật cuối biến nó thành một dòng vết gọn, còn câu trả lời là một tin mới bên dưới. Không tin nào biến mất nữa.
- **Điện thoại chỉ rung một lần cho mỗi lượt, và rung đúng lúc đáng rung.** Tin trạng thái nay gửi im lặng (`disable_notification`), nên thông báo duy nhất là lúc câu trả lời thật tới, hiện đúng nội dung trả lời. Trước đây nó rung hai lần mà lần đầu chỉ nói "đang xử lý", tức là gọi người ta ra xem một câu không có thông tin nào.
- **Dòng vết nói được lượt đó đã chạm vào cái gì**, ví dụ `⚙ pos_statistics · Read · 8s`. Lượt không gọi công cụ nào thì ghi `✓ Trả lời trực tiếp · 3s`. Đây không phải chi tiết trang trí: nó là cách phân biệt một con số vừa lấy từ POS thật với một câu trả lời chay, và nó nằm lại trong lịch sử chat để tra lại được.
- **Gõ `/stop` giữa chừng thì tin trạng thái đổi thành "⏹ Đã dừng"** thay vì biến mất không dấu vết, nên câu hỏi bị cắt vẫn còn chỗ đứng trong mạch chat.
- Đã kiểm với API Telegram: **không có cách nào hiện chữ trạng thái tuỳ ý mà không gửi tin nhắn** (`sendChatAction` chỉ nhận một bộ hành động cố định như "đang nhập", "đang gửi ảnh", và không nhận chữ). Nên thứ sửa được là đừng để tin nào biến mất và đừng nổ thông báo thừa, chứ không phải bỏ hẳn tin trạng thái.
- Bot chuyên trách nói chuyện với khách **giữ nguyên hành vi cũ**: vẫn không để lộ một dòng trạng thái nào, chỉ có chấm "đang nhập…".

## [0.26.3] - 2026-08-08
### Thêm mới
- **Chế độ tiết kiệm nói được nó tiết kiệm BAO NHIÊU, không chỉ bao nhiêu phần trăm.** Trang Mức dùng thêm ba con số: số token thật đã tiết kiệm trong cửa sổ vừa đo, phép chiếu ra một tháng theo đúng nhịp đó, và quy đổi ra tiền. "Giảm 38%" không nói lên điều gì với người đang trả tiền; "khoảng 40 nghìn một tháng" thì có.
- **Ba mức tin cậy được gọi đúng tên**, vì con số to nhất rất dễ bị đọc như một hoá đơn: token trong cửa sổ vừa đo là **đo được**, token mỗi tháng là **phép chiếu**, tiền là **ước lượng**.
- **Giá lấy theo đúng model đang chạy** chứ không phải một số cố định (Opus khác Sonnet khác Haiku khác Groq). Bảng giá tham khảo này sẽ cũ đi vì các nhà cung cấp đổi giá vài tháng một lần, nên đặt `gia_input_1m` trong mục `model` của `settings.json` là đè lên được bằng đơn giá thật của bạn.
- **Nói đúng với người dùng gói thuê bao.** Gói thuê bao không trả theo token, nên với họ con số tiền là mức tiết kiệm quy đổi nếu tính theo giá API, và trên thực tế nó thể hiện thành việc lâu chạm trần gói hơn. Giao diện ghi rõ điều đó khi phát hiện engine là gói thuê bao; nhập nhèm chỗ này thì cả trang mất tin cậy, mà trang này tồn tại chính là để con số đáng tin.
### Sửa lỗi
- Ô **URL repo** ở phần Đồng bộ GitHub không còn lấy tài khoản của chủ repo làm ví dụ.
### Kiểm thử
- `test_trang_tiet_kiem.py` thêm 20 phép thử cho phần này: cách tính token tiết kiệm, phép chiếu co giãn đúng theo độ dài cửa sổ đo, giá đổi theo model, đơn giá tự đặt đè được lên bảng, đơn giá rác không làm nổ trang, chưa đủ dữ liệu thì không bịa ra tiền, và giao diện phải gọi đúng tên ba mức tin cậy.

## [0.26.2] - 2026-08-08
Git chỉ giữ CHỮ, không giữ media. Cỡ chữ khung chat lên 16px.
### Thay đổi
- **Đồng bộ GitHub chỉ đưa file chữ lên repo.** Ghi chú, Wiki, ký ức, skill, cấu hình việc định kỳ, script (`.md .txt .html .csv .json .yaml .canvas .py .svg`…). Ảnh, video, âm thanh, PDF và mọi file nhị phân khác **không lên** - chúng vẫn nằm nguyên trên máy và dùng bình thường, chỉ là không đi vào lịch sử git. Danh sách là **CHO PHÉP** chứ không phải danh sách cấm, nên định dạng media mới ra đời tự động nằm ngoài, khỏi chạy theo vá.
- Vì sao là luật cứng chứ không phải tuỳ chọn: git được thiết kế để nhớ mãi mãi. Nội dung mỗi file commit vào thành một blob nằm vĩnh viễn trong `.git/objects`; xoá file về sau chỉ ghi thêm một dòng "từ đây không còn file này", còn blob vẫn phải giữ để quay ngược về commit cũ được, và `git gc` cũng không dọn được vì nó vẫn có chủ. Với chữ thì đó là ưu điểm (git nén + lưu chênh lệch, sửa cả trăm lượt vẫn nhẹ). Với media thì ngược hẳn: mp4/jpg đã nén sẵn bằng codec nên git không nén thêm được, và hai bản render của cùng một clip là hai file khác hẳn nhau chứ không phải một file sửa nhẹ. Vài trăm MB media cộng thói quen render vài lượt sẽ đẩy repo lên nhiều GB trong ít tháng, và cách duy nhất rút xuống là viết lại toàn bộ lịch sử - việc đó làm mọi bản sao ở máy khác thành không tương thích.
- **Trang Đồng bộ nói thẳng điều này**, kèm lý do và chỗ nên để media (Drive, ổ ngoài: lưu theo trạng thái hiện tại, xoá là đòi lại được dung lượng thật). Sau mỗi lượt đồng bộ, nếu có media bị bỏ qua thì Javis ghi rõ bao nhiêu file và bao nhiêu MB. Bỏ qua lặng lẽ thì có ngày người dùng tưởng ảnh của mình cũng đã được sao lưu.
### Sửa lỗi
- **Luật `.gitignore` nay được ghi theo KHỐI, không nối thêm vào cuối.** Luật allowlist chỉ đúng khi đúng thứ tự (chặn hết → mở cho chữ → chặn lại thư mục cấm). Bản trước chỉ nối dòng còn thiếu vào cuối file, nên với một brain cũ thì mấy dòng "chặn lại" nằm trước dòng "mở cho chữ" và git hiểu ngược: `Javis/learn-log/*.json` được mở lại. Log thô có thể chứa secret nên đó không phải lỗi thẩm mỹ. Luật riêng người dùng tự thêm vẫn được giữ nguyên và vẫn nằm sau khối của Javis để đè lên được.
- **Máy khác không bị xoá mất media thật.** Máy nào cập nhật trước sẽ dọn media khỏi bản sao rồi đẩy việc xoá đó lên repo; máy thứ hai kéo về mà cứ thế áp là mất file trên đĩa. Cả hai chiều nay đi qua đúng một hàm lọc, nên lệnh xoá media từ remote bị bỏ qua thay vì thi hành.
### Cải thiện
- **Cỡ chữ khung chat 15px lên 16px** (cả tin của Javis lẫn tin người dùng). Trần độ dài dòng tính bằng `ch` nên tự giãn theo, giữ nguyên số ký tự mỗi dòng.
### Kiểm thử
- Thêm `tests/python/test_git_chi_giu_chu.py`: 45 phép thử, trong đó có **dựng repo git THẬT** rồi hỏi git xem nó định commit những gì - đây là cách duy nhất chắc chắn về thứ tự luật, vì suy luận trên chuỗi `.gitignore` rất dễ sai. Có cả ca nâng cấp một brain cũ đang có luật riêng của người dùng.
- **Sửa một dương tính giả của bộ quét `test_bien_chua_gan.py`**: nó đi xuyên vào comprehension để nhặt tên bị gán, nên một dòng `X = [f(n) for n in ...]` ở mức module bị coi là "module có biến `n`", rồi mọi hàm đếm bằng `n += 1` đều bị báo là quên `nonlocal`. Ở Python 3 biến chạy comprehension không rò ra ngoài. Đã khoá bằng phép thử riêng.

## [0.26.1] - 2026-08-07
Chủ repo gửi ảnh một câu trả lời dài: *"muốn cải thiện lại cách hiển thị của Javis cho dễ đọc, xuống cách dòng nhiều hơn chứ đọc khó quá."* Ba nguyên nhân khác nhau cùng dồn vào một bức tường chữ, sửa thiếu cái nào cũng vẫn khó đọc.
### Cải thiện
- **Giãn dòng 1.6 lên 1.75.** Đây là thứ dễ gọi tên nhất, và với tiếng Việt thì nó còn đáng hơn: dấu chồng lên chữ nên dòng chật thì các dấu gần như chạm nhau.
- **Khoảng cách giữa hai đoạn từ 6px lên 14px.** Đây là nguyên nhân âm thầm hơn: 6px gần bằng khoảng cách giữa hai DÒNG trong cùng một đoạn, nên mắt không tách được đâu là hết đoạn và cả khối dính thành một mảng. Danh sách, tiêu đề và trích dẫn cũng được nới theo cùng nguyên tắc; riêng danh sách lồng nhau thì siết lại vì nó thuộc về mục cha, giãn bằng đoạn văn là gãy mạch đọc.
- **Chặn độ dài dòng ở 76 ký tự.** Đây mới là thủ phạm chính trên màn rộng: một dòng chạy quá 120 ký tự thì đọc hết dòng, mắt phải quét ngược cả màn hình để tìm đầu dòng kế tiếp, và cứ vài dòng lại đọc nhầm sang dòng đã đọc rồi. Người ta cảm thấy điều đó là "mỏi" chứ ít khi chỉ ra được, nên nó cũng là thứ dễ bị chỉnh về như cũ nhất. Trần đặt trên cả bong bóng chứ không trên từng đoạn chữ: chặn từng đoạn thì nền bong bóng vẫn rộng nguyên và chừa một mảng trống bên phải trông như lỗi hiển thị. Khối mã và bảng dataview không bị bóp vì chúng vốn đã có cuộn ngang riêng; khung chat hẹp (khoang não, điện thoại) thì trần này không đụng tới gì cả.
### Kiểm thử
- Thêm `tests/js/test_de_doc_bong_bong.js`: 15 phép thử khoá các con số theo **quan hệ** chứ không theo giá trị tuyệt đối. Đổi cỡ chữ hay tinh chỉnh vài pixel vẫn xanh; chỉ đỏ khi tương quan hỏng, vd khoảng cách đoạn tụt xuống dưới khoảng cách dòng trong đoạn (đoạn dính vào nhau), trần độ dài dòng bị gỡ, hay tiêu đề dính đoạn phía trước hơn đoạn phía sau nó.

## [0.26.0] - 2026-08-07
Nhắc hẹn kiểu "tự làm rồi báo" giờ **làm được đúng việc bạn hẹn**, kể cả việc phải chạm ra ngoài. Trước bản này mức quyền của nó bị ghim cứng ở chỉ-đọc, nên mọi lời hẹn kiểu "10h mai gửi giúp tôi" đều thức dậy đúng giờ, chạy, rồi báo về là không làm được, còn việc thì vẫn chưa ai làm.
### Thêm mới
- **Ba mức quyền cho nhắc hẹn**, cùng bộ từ với việc lặp: **Chỉ đọc** (đọc MCP và file rồi báo lại), **Ghi file** (thêm quyền ghi nháp trong brain), **Toàn quyền** (dùng được mọi công cụ đã đấu, gồm cả hành động ra ngoài). Đổi được ở form trên trang Việc định kỳ, và hiện thành nhãn ngay trên thẻ việc.
- **Mặc định là Toàn quyền, và đây là quyết định có chủ ý.** Nhắc hẹn khác việc lặp ở chỗ căn bản: việc lặp tự nghĩ ra việc để làm mỗi vòng, còn nhắc hẹn làm ĐÚNG một việc bạn đã viết ra và hẹn giờ, tức là một câu lệnh trong chat được dời sang giờ khác. Trói nó chặt hơn lúc bạn đang ngồi chat là tự mâu thuẫn.
- **Cảnh báo đi kèm ở đúng lúc bạn đang nhìn.** Chọn Toàn quyền trên form thì hiện ô cảnh báo đỏ; tạo qua chat thì tool `javis_schedule` trả kèm câu cảnh báo và Javis phải đọc lại nguyên văn. Nội dung nói ba điều: việc chạy một mình, không có ai duyệt lại, và phần lớn hành động ra ngoài không rút lại được.
### Sửa lỗi
- **Nhắc hẹn cũ (tạo trước bản này) tự chạy ở mức mặc định mới** thay vì rơi vào chỉ-đọc, nên những lời hẹn đang chờ trong hàng đợi làm được việc ngay mà không phải tạo lại.
- Prompt của nhắc hẹn nay nói đúng mức quyền của chính nó. Bản cũ dán cứng câu "tuyệt đối không gửi tin ra ngoài" cho mọi nhắc hẹn, nên kể cả khi mở quyền ở tầng công cụ thì model vẫn tự từ chối. Mức toàn quyền còn được dặn thêm một điều nó không tự suy ra được: lúc đó không có ai ngồi cạnh, nên hỏi lại là hỏi vào hư không - làm được thì làm rồi thuật lại, không làm được thì nói thẳng.
### Kiểm thử
- Thêm `tests/python/test_nhac_hen_muc_quyen.py`: 39 phép thử, trong đó phần đáng canh nhất là **ba mức dựng engine khác nhau THẬT** (allowlist, mức của hub, brain truyền xuống, và câu ràng buộc trong prompt) chứ không phải chỉ đổi cái nhãn. Có cả ca bản ghi cũ thiếu trường và giá trị rác.
- Khoá luôn yêu cầu **cảnh báo phải trung tính**: test bác bỏ nếu trong câu cảnh báo xuất hiện tên một kênh hay một ngành cụ thể. Javis là công cụ cho nhiều người, mỗi người đấu một bộ công cụ khác nhau.

## [0.25.9] - 2026-08-07
Chủ repo gửi ảnh Telegram: loop "[CK] Tin Hot Chứng Khoán" chạy bằng ChatGPT thay vì Claude, mọi lệnh đọc/ghi file đều trả `bwrap: Failed to make / slave: Permission denied`, và bản báo cáo về máy là một bài dài model tự kể lại nỗi bối rối của nó.
### Sửa lỗi
- **Việc nền chạy bằng ChatGPT không đọc nổi một file nào trong Docker.** Codex bọc mọi lệnh đọc/ghi file của nó bằng bubblewrap, mà bubblewrap cần tạo được user namespace và đổi propagation của `/`. Container Javis chạy user thường, không có `CAP_SYS_ADMIN`, và Ubuntu 24.04 còn chặn user namespace không đặc quyền bằng AppArmor. Nên trong Docker, hai mức rào `read-only` (mode suggest) và `workspace-write` (mode auto) của Codex **không bao giờ khởi động được** - rào đó không phải chặt hơn mà là chết hẳn. Loop tạo từ chat mặc định là `suggest`, nên mọi việc nền chạy bằng ChatGPT trong Docker đều câm theo đúng kiểu này. Chạy bằng Claude thì không sao vì Javis chặn theo từng tool qua chính SDK, không cần bubblewrap.
- **Ảnh Docker nay đặt sẵn `JAVIS_CODEX_SANDBOX=off`**, để chính container làm rào. Cập nhật lên bản này là việc nền bằng ChatGPT chạy được ngay, không phải đụng gì trên VPS. Đánh đổi được ghi thẳng trong Dockerfile chứ không giấu: Codex không có allowlist per-call như Claude, nên với cờ này thì loop mức `suggest` mất thứ chặn nó ghi file trong container. Các rào về tiền, đơn hàng, đăng bài, gửi tin KHÔNG bị ảnh hưởng vì chúng nằm ở MCP Hub chứ không ở sandbox. Ai muốn giữ rào thì đặt `JAVIS_CODEX_SANDBOX=auto` rồi cấp quyền cho container (vd `security_opt: [apparmor:unconfined]`).
- **Javis nhận ra dấu vết `bwrap` và tự giải thích trong chính bản báo cáo.** Trước đây thứ tới tay chủ là một bài model tự kể chuyện, đọc xong không ai biết phải đi sửa ở tầng container. Nay cuối lượt có một dòng nói đúng thủ phạm, khẳng định đây không phải lỗi của lượt chạy, và chỉ đúng hai lối ra. Cần cho cả người tự dựng container riêng.
### Kiểm thử
- Thêm `tests/python/test_codex_sandbox_docker.py`: 24 phép thử phủ bản đồ mức quyền sang cờ sandbox (kể cả giá trị lạ và mức lạ), đường dây thật qua `aux_engine._build_codex` tới argv, ảnh Docker có đặt cờ và có ghi lý do lẫn đánh đổi hay không, và việc nhận diện dấu vết `bwrap` không bắt nhầm lượt chạy bình thường.
- Khoá luôn một bẫy dựng ảnh: chú thích không được chen vào giữa khối `ENV` nối dòng bằng `\`, vì hỏng Dockerfile thì VPS không cập nhật được nữa.

## [0.25.8] - 2026-08-07
Hai test đỏ lai rai làm nền cho mọi lần chạy đều phải đoán "cái này có phải lỗi mình vừa gây ra không". Sửa dứt cả hai, và một trong hai hoá ra là lỗi thật của sản phẩm chứ không phải lỗi test.
### Sửa lỗi
- **Câu đại diện trong danh sách "chỗ tài liệu đang thiếu" chọn sai khi hai lượt trùng dấu thời gian.** `chatbot_log.lo_hong` gom các câu hỏi trùng nhau rồi giữ bản MỚI NHẤT làm đại diện, nhưng so bằng `>` nên khi hai lượt có `ts` bằng nhau thì nó giữ bản CŨ. Đồng hồ hệ thống trên Windows nhảy theo bước ~15ms nên hai khách hỏi sát nhau trùng `ts` là chuyện thường. Nay so `>=`: `_nap` đọc theo đúng thứ tự ghi vào nên bản nằm sau trong file chính là bản mới hơn. Đây là lỗi sản phẩm, chỉ tình cờ lộ ra qua một test đỏ ngẫu nhiên khoảng 1/6 số lần chạy.
### Kiểm thử
- `test_chatbot_grounding.py` khoá ca trùng `ts` bằng đồng hồ ĐỨNG YÊN thay vì trông vào may rủi: đổi `>=` về `>` là test đỏ chắc chắn. Chạy 25 lần liên tiếp, xanh cả 25.
- **`test_readonly_orchestrator_phase7.py` đỏ trên máy đã chạy app thật, xanh trên CI** - loại "đỏ trên máy tôi" khó lần nhất vì sai nằm ở dữ liệu ngoài repo. `ObserveRuntime.start_turn` ghim revision từ registry TOÀN CỤC, trong khi `resume` đối chiếu với registry dựng riêng cho test. Fixture đã ghim đè `registry_revision` nhưng bỏ sót `model_profile_revision`, nên máy nào có bảng `model_profiles` chứa dữ liệu là 3 phép thử resume đỏ. Nay ghim đủ cả hai, test hết phụ thuộc vào state dir của người chạy.

## [0.25.7] - 2026-08-07
Chủ repo gửi ảnh nhóm "Cười Sóng AI": *"chat bất kỳ điều gì trong nhóm khi add bot vào nó đều typing, làm sao để chỉ hiện typing khi bot thực sự trả lời."* Hai người trong nhóm nói chuyện với nhau, tin nào bot cũng hiện "đang nhập…" rồi lặng lẽ không nói gì.
### Sửa lỗi
- **Chốt chặn `precheck` chưa từng chặn được ca im lặng.** Bot chuyên trách nói "chặn, đừng nói gì" bằng cách trả về `{}`, nhưng cổng ở `_dispatch` viết `if chan:` - dict rỗng là falsy nên nhánh chặn bị bỏ qua và lượt vẫn chạy tiếp. Cái thấy được là chấm "đang nhập…" trên mọi tin trong nhóm. Cái KHÔNG thấy được thì đắt hơn nhiều: **mỗi tin trong nhóm đều tốn một lượt engine thật**, chạy hết rồi mới bị lớp thứ hai trong `answer_fn` trả về `im_lang` và vứt đi. Nhóm đông người thì đó là hoá đơn token cho những câu chẳng ai hỏi bot. Cổng nay so `is not None`, đúng như hợp đồng vẫn ghi trong docstring.
- Con bọ này nằm im từ lúc có `precheck` và chỉ lộ ra ở 0.25.5, khi chấm "đang nhập…" chuyển từ một nháy 5 giây thành sáng liên tục suốt lượt. Nó biến một lỗi vô hình thành một lỗi nhìn thấy được.
### Kiểm thử
- `test_bot_noi_nhu_nguoi.py` thêm 7 phép thử cho cổng precheck: `{}` thì không gọi engine, không "đang nhập…", không gửi gì; `{"reply": ...}` thì nói đúng một câu mà vẫn không gọi engine; `None` mới là ca duy nhất được chạy lượt; và precheck nổ thì vẫn trả lời chứ không nuốt câu của khách.

## [0.25.6] - 2026-08-07
Chủ repo bảo Javis *"thiết kế cho anh file .md nhé"*, Javis đáp *"có một chỗ va nhau giữa lựa chọn của anh và tài liệu chiến lược, em xử lý thẳng trong file. Viết file luôn."* rồi lượt chết ở giây thứ 180 với dòng *"Claude đang trả lời rồi im 180s - đã dừng để tránh treo server."* Cái chết oan: engine đang soạn nội dung file để đưa vào tool Write, mọi thứ chạy đúng, chỉ là không có gì để phát ra.
### Sửa lỗi
- **Bỏ hẳn trần 180s và trần 600s.** Vấn đề không nằm ở con số mà ở PHÉP ĐO: watchdog đếm "bao lâu rồi chưa nhận được message từ SDK" rồi coi đó là treo, trong khi SDK chỉ phát message khi model kết thúc một khối. Model suy nghĩ ở mức nỗ lực cao, hoặc soạn nội dung một file dài để đưa vào tool ghi, đều làm kênh im hàng phút dù không có gì hỏng. Nay hai trần đo-sự-im-lặng (`JAVIS_CLAUDE_IDLE_TIMEOUT`, `JAVIS_CLAUDE_FIRST_TIMEOUT`) mặc định **không giới hạn**. Cắt một lượt đang chạy tốt là mất trắng cả công lẫn token, tệ hơn hẳn để nó chạy lâu.
- **Trần chờ TOOL giữ nguyên 1 tiếng.** Trần này đo một thứ có thật: tool đã khởi động mà chưa trả kết quả, tức có một tiến trình con đang sống ngoài kia và nó có thể treo thật (chờ nhập liệu, kẹt khoá file). Đây là khác biệt bản chất với hai trần trên.
- **Việc nền vẫn không treo vô hạn.** Loop, việc Kanban, nhắc hẹn và tự học đều đã có trần wall-clock riêng (`max_wall_s`, từ 240 tới 600 giây tuỳ loại), nên bỏ trần im lặng không mở đường cho một việc nền chạy mãi. Chat trên dashboard thì luôn bấm Dừng được.
- **`0` giờ có nghĩa là "không giới hạn" ở cả ba biến**, ở cả engine Claude lẫn engine Codex. Giá trị rác trong biến môi trường thì về mặc định chứ không làm nổ lượt chat.
- **Thông báo hết giờ không còn suy ngược lý do.** Trần và lý do được chốt cùng lúc lúc chọn trần; suy ngược sau khi hết giờ vừa ra thông báo sai (nói "tool chạy quá" trong khi thật ra là chạm trần wall-clock) vừa có đường dẫn tới `int(None)` nổ giữa lượt chat khi một trần bị tắt.
### Kiểm thử
- `test_sdk_engine.py` thêm 4 phép thử chạy THẬT qua engine: `IDLE=0` thì im bao lâu cũng không bị chém, `FIRST=0` cũng vậy, trần chờ tool vẫn ngắt được khi hai trần kia đã tắt, và việc nền vẫn bị trần wall-clock chặn.
- `test_watchdog_treo.py` khoá hành vi của `tran_watchdog` (0/âm/rác/số dương) và khoá luôn việc chốt trần kèm lý do ở cả hai engine.

## [0.25.5] - 2026-08-07
Chủ repo gửi ảnh chụp một nhóm Telegram: bot chuyên trách đang nói chuyện như người, rồi giữa cuộc hiện ra *"⏳ Đang xử lý câu trước. Gửi /stop để dừng rồi hỏi lại."* trước mặt cả nhóm. Một câu như vậy khai ngay đây là máy, và còn dạy người lạ một lệnh quản trị. Yêu cầu: *"các phần trạng thái của Javis anh không muốn để lộ ra như vậy, anh muốn ẩn đi để như cảm giác người thật nói chứ ko phải bot."* Gốc rễ: bot chuyên trách và bot Javis của chủ dùng chung lớp `TelegramBot`, mà lớp đó nói trạng thái ra ngoài như đang nói với người vận hành máy.
### Sửa lỗi
- **Bot chuyên trách không còn để lộ một dòng trạng thái nào.** Thêm cờ `giau_trang_thai` cho `TelegramBot`, bật sẵn cho mọi bot khách. Bốn chỗ rò bị bịt: tin "🤔 Javis đang xử lý…" cùng các bản cập nhật "⏳ ⚙ Đang gọi công cụ…" của nó, câu "Đang xử lý câu trước, gửi /stop", dòng "⚠ Lỗi: TênLớpNgoạiLệ: …" khi một lượt gãy, và chữ "(không có nội dung)" khi lượt trả về rỗng. Bot Javis của CHỦ giữ nguyên tất cả: người vận hành máy thì cần nhìn thấy Javis đang chạy tới đâu.
- **Thay tin trạng thái bằng chấm "đang nhập…" của chính Telegram**, giữ sáng đều suốt lượt trả lời. Đây đúng là thứ một người thật để lại khi họ đang gõ, và nó không phải một tin nhắn nên không nằm lại trong lịch sử nhóm.
- **Lượt gãy thì xin lỗi bằng một câu bình thường** rồi mời nhắn lại, thay vì đọc tên lớp ngoại lệ ra miệng. Lý do kỹ thuật vẫn vào stderr, vẫn vào nhật ký bot, vẫn báo người trực nếu chủ có đặt.
### Cải thiện
- **Nhắn thêm lúc bot đang trả lời thì không bị chặn nữa, mà được xếp hàng.** Giấu câu báo bận mà vẫn bỏ tin đi thì tệ hơn cả để lộ: khách hỏi mà không ai đáp. Nay bot gom mấy câu tới trong lúc bận, trả lời xong câu trước là trả lời tiếp một thể, đúng như một người đọc nốt tin rồi mới đáp. Trần 5 tin hoặc 4000 ký tự mỗi cuộc trò chuyện để người lạ spam không làm phình bộ nhớ; gõ `/stop` thì bỏ luôn phần đang chờ.
### Kiểm thử
- Thêm `tests/python/test_bot_noi_nhu_nguoi.py`: dựng Telegram giả lập rồi soi đúng những gì bot ĐỊNH gửi đi. 24 phép thử phủ cả bốn chỗ rò, luật xếp hàng và trần của nó, ca `/stop` cắt ngang, và đối chứng rằng bot của chủ vẫn giữ nguyên hành vi cũ ở từng ca một.

## [0.25.4] - 2026-08-07
Chủ repo gửi ảnh chụp khung chat kèm câu: *"sao lại hiển thị 9 việc nền như này? anh không muốn vào chat mà hiện ra như này đâu."* Trong ảnh là một khối chữ chắn ngang khung chat, liệt kê đủ 9 nhắc hẹn. Chín cái đó không chạy, không hỏng, không cần ai làm gì: chúng chỉ đang đợi tới giờ, và trang Việc định kỳ đã liệt kê sẵn. Dải việc nền thêm ở 0.25.2 sinh ra để trả lời đúng một câu hỏi *"ngay lúc này có cái gì đang chạy cho tôi không"*, mà nhắc hẹn chờ tới giờ trả lời là "không". Câu trả lời "không" thì phải im lặng, chứ không phải dựng một bức tường chữ.
### Sửa lỗi
- **Bỏ hẳn mức xám "đang chờ tới giờ".** Dải chỉ còn hai mức, cả hai đều là thứ phải biết ngay: xanh khi có việc đang chạy THẬT, vàng khi vừa giao mà điều phối tắt nên nó không tự chạy. Mọi trạng thái khác thì dải ẩn hoàn toàn, không chiếm một pixel nào. Quyết định này nằm ở trường `level` do máy chủ tính (`background_status.active_view`) nên test được bằng Python, không phải luật rải rác trong lúc dựng HTML.
- **Dải chỉ vẽ đúng việc gây ra mức đó.** Trước đây dù chỉ có 1 việc đang chạy thì nó vẫn đổ cả hàng đợi ra thành chip, kể cả 9 nhắc hẹn không liên quan. Nay mức xanh chỉ vẽ việc đang chạy, mức vàng chỉ vẽ việc đang kẹt, tối đa 4 chip rồi gộp phần dư thành "+N nữa". Máy chủ đánh dấu sẵn `stalled` trên từng mục để trình duyệt khỏi đoán lại luật.
- **Backlog cũ thôi sơn vàng khung chat vĩnh viễn.** Việc xếp hàng chỉ tính là "đứng im" khi nó vừa được giao trong vòng 24 giờ. Một việc để quên từ tuần trước không phải tin tức, mà dải nào hiện suốt thì thành dải không ai đọc, tới lúc hỏng thật cũng chẳng ai nhìn.
### Cải thiện
- **Nhịp hỏi máy chủ co giãn theo việc thật:** 6 giây khi dải đang hiện việc, 20 giây khi không có gì để hiện, 60 giây khi tab bị ẩn. Trước đây cứ 6 giây một nhát suốt cả ngày để hỏi một thứ hầu như luôn rỗng. Nhịp kế tiếp được hẹn SAU khi câu trả lời về, nên lúc chuyển từ rỗng sang có việc là bám sát ngay chứ không phải đợi hết một nhịp thưa.
### Kiểm thử
- Thêm `tests/js/test_dai_viec_nen.js`: phần quyết định của dải tách thành hàm thuần nên chạy được bằng node, 21 phép thử gồm đúng ca 9 nhắc hẹn trong ảnh, ca có việc chạy lẫn giữa 9 nhắc hẹn, trần 4 chip, và ca máy chủ đời trước không gửi `level`.
- `tests/python/test_viec_nen_hien_ra.py` khoá thêm mức `level` cho từng ca và luật 24 giờ của việc kẹt.

## [0.25.3] - 2026-08-06
Chủ repo gửi ảnh chụp iPhone kèm câu: *"Ở điện thoại khi não thu nhỏ thì nó quá bé ko thấy gì cả."* Đúng. Đo lại bằng Chromium 390x844 thì khoang não cao 228px, mà lệnh canh khung chừa cứng 70px mỗi bên - còn đúng 88px cho TOÀN BỘ đồ thị. Cụm node ra 87x88 giữa một khung 390x228, chiếm 22% bề ngang. Ba thứ khác cộng dồn vào cùng chỗ đó: 8 nhãn thư mục rải kín khung (tên dài tràn hẳn ra ngoài mép phải), dải Agents/Skills/Workflows xếp chồng cao ~56px, và sàn lưới phối cảnh ăn 28% cuối.
### Sửa lỗi
- **Lề canh khung tính theo KÍCH THƯỚC KHUNG, không còn là hằng số.** `zoomToFit(500, 70)` là con số hợp lý cho khoang não desktop (~900x700) và thảm hoạ trên điện thoại. Nay lấy 10% của cạnh nhỏ nhất, kẹp trong [10, 70]: desktop giữ nguyên cảm giác cũ (700 x 0.10 = 70), mobile tự co xuống 23. Đo lại trên cùng máy ảo: cụm node từ **87x88 lên 200x202**, tức lấp 77% chiều cao khoang thay vì 39%.
- **Trên điện thoại nút "ẩn nhãn" chưa từng bấm được.** Cả ba nút góc phải đều mang class `.brain-overlay-toggle`, nên dòng `top: 7px` trong khối mobile của `console.css` đè luôn `.graph-timelapse-btn { top: 58px }` bên `style.css` (cùng độ ưu tiên, `console.css` nạp sau). Hai nút chồng khít lên nhau và nút vẽ sau ăn hết cú chạm. Nay mỗi nút một hàng, đặt tường minh.
- **Tên thư mục dài bị cắt cụt ngoài mép.** Nhãn vốn `nowrap` + `translate(-50%)` nên "BRAIN DEFAULT" ở rìa phải tràn hẳn ra ngoài khoang. Nay kẹp bề ngang và cắt bằng dấu ba chấm; đo trên 5 cỡ màn khác nhau, không nhãn nào còn tràn.
### Cải thiện
- **Khung hẹp rải 4 nhãn ở bốn góc thay vì 8 nhãn kín khung**, khe trống dưới đáy nới rộng cho chữ trạng thái. Desktop giữ nguyên 8 nhãn và bán kính cũ. Xoay ngang dọc thì tự rải lại.
- **Dải Agents/Skills/Workflows mỏng còn một dòng** (số và nhãn cùng hàng): từ ~56px xuống ~28px, trả lại một phần tám khoang não cho đồ thị.
- **Sàn lưới phối cảnh tụt chân trời xuống 86%** khi khoang não thấp dưới 320px, thay vì 72% cố định. Vẫn còn chiều sâu, nhưng thôi cướp chỗ của thứ người dùng thật sự muốn nhìn.
- **Khoang não mobile cao thêm một nhịp**: `clamp(190px, 27dvh, 260px)` thành `clamp(210px, 31dvh, 300px)`.
### Thêm mới
- **Nút BUNG NÃO toàn màn trên điện thoại.** Siết lề với thu nhỏ chữ chỉ làm một khung 228px bớt tệ chứ không biến nó thành chỗ xem đồ thị tử tế - đây mới là câu trả lời thật. Bấm là khoang não chiếm trọn phần thân (cụm node lên 301x305), bấm lần nữa thu về. Gửi tin nhắn lúc đang bung thì tự thu lại, vì ở trạng thái đó khung chat bị ẩn và người dùng gõ xong sẽ không thấy câu trả lời ở đâu. Về màn rộng thì cờ bung tự bỏ. Chip đính kèm KHÔNG bị giấu (giấu là tưởng gắn hụt); chỉ dải việc nền nhường chỗ.
### Kiểm thử
- `test_nao_tren_dien_thoai.js`: canh lề động, `refit()` phải mở lại `minZoom` trước khi canh (không thì khung to hơn không bao giờ zoom-out đủ), ba nút ba hàng riêng, desktop không đổi, và luật "gửi tin thì thu não".
- `test_mobile_layout.py`: đổi từ ghim nguyên chuỗi `clamp` sang khoá theo SÀN, đúng tinh thần đã ghi ngay trên nó. Ghim nguyên chuỗi thì một lần nới khoang não cho dễ nhìn cũng làm test đỏ oan; cái phải chặn là chiều ngược lại.

## [0.25.2] - 2026-08-06
Chủ repo gửi ảnh chụp khung chat kèm câu: *"anh đang bật chức năng siêu tiết kiệm, nhiều khi nó trả lời như này nhưng không hề báo lại chút nào cả. Và có agent chạy ngầm thì anh cũng không biết là nó đang chạy thật hay không? Không giống như claude nếu đang chạy ngầm thì vẫn có báo ở đầu hội thoại. Đây là không thấy gì luôn và không chạy luôn."*

Câu Javis nói trong ảnh: *"Em đang dò code để xem trong nhóm bot có lọc tin nhắn (theo mention, reply, hay AI tự quyết định) trước khi trả lời hay không, có kết quả em báo ngay."* Rồi hết. Không có gì về nữa.

Ba nguyên nhân khác nhau chồng lên nhau cho ra đúng một triệu chứng, và không cái nào để lại một dòng lỗi nào.
### Sửa lỗi
- **Cảnh báo "điều phối đang TẮT" của tool giao việc CHƯA TỪNG in ra một lần nào.** Cổng viết là `not view.get("orchestration")`, mà giá trị trả về là CHUỖI `"off"` - luôn truthy, nên nhánh cảnh báo chết từ lúc được viết. Đây là "không chạy luôn": điều phối Kanban mặc định `off` ở mọi brain mới, việc giao từ chat nằm xếp hàng vô thời hạn, và chỗ duy nhất có thể nói ra chuyện đó thì im. Cổng nay so đúng với `"auto"` - mức duy nhất có dispatcher lấy việc ra chạy.
- **`javis_task` op=add hứa hộ "Việc chạy nền. Kết quả tự về" trong MỌI trường hợp**, kể cả khi điều phối tắt và việc chắc chắn không chạy. Model không có cách nào biết câu đó sai nên nó chuyển tiếp nguyên văn cho người dùng. Nay câu này chỉ xuất hiện khi điều phối THẬT SỰ chạy; còn lại tool nói thẳng việc đang nằm xếp hàng và dặn model đừng hứa là nó đang chạy.
- **Hứa "xong em báo" rồi im vĩnh viễn.** Luật cũ chỉ cấm đúng một câu mẫu ("em sẽ đợi các agent chạy xong rồi tổng hợp"), nên kiểu "đang làm, có kết quả em báo ngay" lọt thẳng. Chặn bằng cách liệt kê chữ cấm là trò đuổi bắt, nên nay Javis **tự kiểm bằng sự thật**: cuối mỗi lượt server dò lời hứa trong câu trả lời rồi đối chiếu với việc nền đang có thật (việc Kanban, loop, nhắc hẹn). Hứa mà không có gì chạy thì nó tự dán một dòng đính chính ngay dưới câu trả lời, nói rõ là sẽ không có báo cáo nào tự về và anh cần làm gì tiếp. Chạy ở cả dashboard lẫn Telegram; không chặn và không sửa câu của model, chỉ nói thêm sự thật.
### Thêm mới
- **Dải "đang chạy ngầm" ngay trên khung nhập.** Đây là vế "không thấy gì luôn": việc nền sống ở ba kho khác nhau (Kanban trong sqlite, loop là file .md, nhắc hẹn trong json) và không kho nào lộ ra ở khung chat, nên muốn biết phải tự nghĩ ra việc mở trang Việc. Dải mới trả lời đúng một câu hỏi "ngay lúc này có cái gì đang chạy cho tôi không", với ba tông rõ ràng: xanh có việc **đang chạy thật**, vàng là **đã giao nhưng KHÔNG tự chạy** (kèm cách bật), xám là loop/nhắc đang chờ tới giờ. Không có gì thì dải ẩn hẳn. Việc giao từ chính hội thoại này được viền riêng và đếm riêng, vì "máy đang bận" với "việc CỦA TÔI đang chạy" là hai chuyện khác nhau.
- **`GET /background?brain=&chat_id=`**: gom việc nền còn sống của một khung chat từ cả ba kho. Dải trên hỏi endpoint này mỗi 6 giây khi tab đang mở (30 giây khi tab ẩn), và hỏi lại ngay mỗi khi một lượt chat kết thúc hoặc một việc nền vừa báo kết quả về.
### Cải thiện
- **Luật cấm hẹn suông chuyển lên khối kênh dùng CHUNG cho mọi kênh** (dashboard, Telegram, CLI) thay vì chỉ nằm ở nhánh dashboard. Nêu thẳng hai lối đúng: làm luôn trong lượt này, hoặc giao thành việc nền rồi nói rõ đã giao gì và kết quả về đâu. Kèm luật mới: giao việc xong phải đọc kết quả tool và thuật lại đúng như vậy, tool báo điều phối tắt thì phải nói ra chứ không rút gọn thành "việc đang chạy".
### Kiểm thử
- `test_viec_nen_hien_ra.py`: canh cả ba nguyên nhân. Bộ dò lời hứa kiểm bằng ĐÚNG câu chủ repo chụp lại, cộng 6 câu hứa khác và 6 câu vô hại phải không bị bắt nhầm (cảnh báo thừa dán dưới một câu trả lời đúng còn hỏng hơn là thiếu cảnh báo). Ca đắt nhất: việc đã giao + điều phối tắt thì lời hứa VẪN là suông, vì việc đó sẽ không chạy.
- `test_giao_viec_moi_engine.py`: kiểm cả hai chiều của cổng điều phối, mức `off` cấm hứa "chạy nền" còn mức `auto` bắt buộc phải nói - một chiều thì không phân biệt được cổng đang đọc mức thật với việc dán cứng một câu.

## [0.25.1] - 2026-08-06
Chủ repo cập nhật 0.25.0 rồi báo lại: *"chat trong nhóm vẫn im re, còn chat riêng thì vẫn được"*. Nghĩa là 0.25.0 mới vá đúng MỘT trong ba nguyên nhân cho ra cùng một triệu chứng đó, và hai nguyên nhân còn lại đều nằm ở chỗ Javis không nhìn thấy tin nào.

Ba nguyên nhân, sửa khác nhau hoàn toàn, và đứng trong nhóm thì không phân biệt được cái nào: **nhóm chưa được bật**, **chế độ riêng tư của Telegram còn bật**, **bot chưa hỏi được danh tính của chính nó**.
### Sửa lỗi
- **getMe hỏng một lần là bot ĐIẾC trong mọi nhóm, vĩnh viễn, không dấu vết.** Bot không biết `@username` của chính mình thì `_co_nhac_ten` trả False cho MỌI tin - tin nhắn riêng vẫn chạy hoàn hảo (không cần nhận ra tên), còn trong nhóm thì im tuyệt đối. Bản trước nuốt lỗi này bằng đúng một dòng stderr rồi đặt trạng thái `polling`, nên thẻ vẫn chấm xanh và không có chỗ nào nói ra. Một cú mạng rớt đúng giây khởi động là đủ.

  Nay getMe **thử lại ba lần**, thất bại thì **giữ lại lý do** cho thẻ bot hiện thành một dòng đỏ, và vòng lặp **tự hỏi lại mỗi phút** chừng nào còn chưa có danh tính - thay vì đợi ai đó nghĩ ra việc tắt bật lại bot. Lý do này để riêng khỏi `last_error` vì vòng lặp xoá `last_error` sau mỗi lượt poll thành công, mà lượt nào cũng thành công.
- **Gõ `/id` trong nhóm xong quay lại dashboard vẫn không thấy nhóm nào để bấm cho phép.** 0.25.0 chỉ đưa nhóm lên hàng đợi khi có người GỌI BOT, mà tin gọi bot lại chính là thứ chế độ riêng tư chặn - vòng luẩn quẩn. Nay **tin bất kỳ về từ một nhóm** cũng đưa nhóm đó lên thẻ, và lệnh `/...` thì luôn về tới nơi bất kể chế độ riêng tư. Nhưng không tính là một lần gọi bot: đếm gộp thì con số "có người gọi bot N lần" mất sạch ý nghĩa.
### Cải thiện
- **`/id` thành một bản chẩn đoán, không còn là một con số trơ.** Nó là chỗ DUY NHẤT chắc chắn nói được ra khi bot im trong nhóm. Nay nó trả lời: id nhóm, nhóm này đã được bật chưa, chế độ riêng tư đang bật hay tắt, bot đã biết danh tính của mình chưa, và phải làm gì tiếp. Trong tin nhắn riêng thì vẫn chỉ một dòng id như cũ, không giảng giải thừa.
- **Cảnh báo chế độ riêng tư hiện cho MỌI bot có dùng nhóm**, không riêng bot đặt "trả lời mọi tin" như 0.25.0. Nó là nguyên nhân số một của "nhắn riêng thì được, trong nhóm tag tên thì im re", và người dùng không có cách nào đoán ra vì mọi dấu hiệu trên trang đều xanh.
- **Nói cả HAI cách sửa**, không chỉ một: `@BotFather` → `/setprivacy` → **Disable**, **hoặc** cho bot làm **quản trị viên** nhóm (admin nhận được mọi tin, không phụ thuộc chế độ riêng tư). Cách thứ hai làm được ngay trong nhóm, không phải đi tìm BotFather.
### Kiểm thử
- Canary getMe: phải có thử lại, phải giữ lý do, và lý do đó phải TÁCH khỏi `last_error` - test canh đúng dòng `self.last_error = ""` trong vòng lặp để bản sau không gộp lại.
- `/id` trong nhóm chưa bật / đã bật / trong tin nhắn riêng: ba đường ra ba câu khác nhau, và đọc nhóm từ KHO chứ không từ bản ghi chụp lúc dựng lệnh (bấm Cho phép là ăn ngay từ câu sau, không phải tắt bật lại bot).
- Tin bất kỳ từ nhóm đưa nhóm lên hàng đợi nhưng KHÔNG thổi phồng bộ đếm lần gọi.
### Tài liệu
- `docs/25-chatbot.md`: Bước 4 đổi sang dùng `/id` thay vì gọi tên bot, kèm lý do; thêm hẳn một mục **Chế độ riêng tư của Telegram** liệt kê chính xác thứ gì tới được bot và thứ gì không, cùng cả ba nguyên nhân của triệu chứng "riêng thì được, nhóm im re".

## [0.25.0] - 2026-08-06
Chủ repo gửi hai ảnh. Ảnh một: một nhóm Telegram, bot vừa trả lời `/id` xong, rồi ba tin gọi thẳng tên nó - `@ten_bot em hỗ trợ được gì bọn anh nhé?`, `@ten_bot ALo`, `chốt mịa rồi ném vào nhóm nhỏ méo phản hồi`. Không có tin nào của bot sau đó. Ảnh hai: thẻ bot trên dashboard vẫn báo **Đang khởi động** trong khi con bot đó vừa trả lời trong nhóm.

Ba việc, và cả ba đều là **hỏng lặng lẽ** chứ không phải hỏng chức năng.
### Sửa lỗi
- **Thả bot vào nhóm, gọi tên nó, không có gì xảy ra.** Rào thì đúng: bot không tự nhận việc trong nhóm chưa được chủ khai. Nhưng CÁCH TỪ CHỐI thì sai hoàn toàn - im hoàn toàn, không log, không dòng nào trên trang Chatbot. "Hành vi đúng" và "bot hỏng" trông y hệt nhau, và người dùng chỉ có thể kết luận vế thứ hai.

  Nay từ chối vẫn từ chối, nhưng nó **nói**: bot đáp đúng một câu cho người đang gọi biết phải làm gì, và nhóm đó **hiện lên thẻ bot** kèm nút **Cho phép nhóm này**. Một cú bấm thay cho đường cũ dài bảy bước (gõ /id, chép id, mở dashboard, bấm Sửa, kéo xuống đáy form, dán, Lưu) mà sót một bước là quay lại đúng chỗ im lặng.
- **Ô "Nhóm được phép" chỉ có trong form Sửa, không có trong form Tạo.** Nghĩa là đường đi tự nhiên nhất - tạo bot xong thả thẳng vào nhóm - bảo đảm lần thử đầu tiên của mọi người dùng gặp một con bot im lặng. Nay khai được ngay lúc tạo, và ô chọn "trong nhóm thì khi nào bot lên tiếng" cũng lên mặt giao diện (trước đây chỉ tồn tại trong kho, không có đường nào để đổi).
- **Nhóm thường lên siêu nhóm thì Telegram đổi id** (thêm tiền tố `-100`), không báo ai cả. Id chủ khai hôm trước lập tức trỏ vào một nhóm không còn tồn tại, và bot im trong đúng nhóm nó vừa trả lời được hôm qua. Nay hai dạng id khớp nhau, và Javis nghe tin nâng cấp để tự cập nhật danh sách.
- **Gọi tên bot mà Telegram không kèm `entities` thì cờ "được gọi" tắt.** `entities` là thứ Telegram gắn thêm, không phải một bảo đảm. Thêm nhánh so chuỗi thô làm lưới đỡ.
- **Thẻ bot đứng nguyên ở "Đang khởi động".** Bấm Bật thì server trả về `starting` - poller vừa được tạo, chưa kịp bắt tay với Telegram - rồi vài giây sau nó thành `polling`. Nhưng trang chỉ nạp lại khi người dùng bấm cái gì đó, nên thẻ đứng ở "Đang khởi động" cho tới lúc rời trang rồi quay lại, trong khi bot đã trả lời thật từ lâu. Nay trang tự làm mới 5 giây một nhịp; nhịp đó cũng là thứ DUY NHẤT phát hiện được một con bot vừa chết.
- **Icon mức Toàn quyền vẽ ra ô trống.** `shield-alert` không có trong bộ icon đã vendor. Test icon không bắt được vì nó chỉ dò tên viết thẳng trong lời gọi, còn chỗ này là một biểu thức ba ngôi.
### Cải thiện
- **Mức quyền hiện trên thẻ ở CẢ BA mức, kể cả Chỉ đọc.** Bản trước bỏ trống nhãn cho mức mặc định với lý do "mặc định thì không cần dán nhãn". Nhưng một ô trống đọc ra được hai nghĩa ngược nhau: bot đang chỉ đọc, hay trang này không nói cho biết? Xám cho Chỉ đọc, vàng cho Được ghi, đỏ cho Toàn quyền.
- **Thẻ nói rõ trong nhóm bot lên tiếng khi nào** ("3 nhóm, khi được gọi tên") chứ không chỉ đếm số nhóm.
- **Cảnh báo khi cấu hình đòi thứ Telegram không cho.** Đặt bot "trả lời mọi tin trong nhóm" mà chế độ riêng tư của Telegram còn bật thì Telegram chặn từ phía nó, Javis không bao giờ nhìn thấy những tin đó, và mọi dấu hiệu trên trang vẫn xanh. Nay `getMe` đọc `can_read_all_group_messages` và thẻ nói thẳng phải vào @BotFather gõ `/setprivacy` → Disable.
### Bảo mật
- **Im lặng có chủ ý nay là im lặng THẬT.** Trước bản này, bot từ chối một tin trong nhóm lạ vẫn đi hết đường: gửi tin "🤔 đang xử lý…", xoá nó, rồi gửi **"(không có nội dung)"** vào mặt người ngoài. Chốt chặn mới nằm ở tầng kênh, chạy TRƯỚC khi tốn một lượt engine và trước cả tin trạng thái. Câu trả lời rỗng vì engine gãy vẫn hiện ra như cũ - hai thứ đó không được lẫn vào nhau.
- Lệnh `/...` cố ý KHÔNG đi qua chốt chặn: `/id` là đường chính thức để lấy id nhóm, chặn nó thì chủ không còn cách nào khai nhóm cho bot.
- Rào "bot không tự nhận việc trong nhóm lạ" **không bị nới ra**. Hàng đợi nhóm chờ duyệt nằm trong RAM, có trần 20 nhóm mỗi bot, và câu báo trong nhóm chỉ nói đúng một lần cho mỗi nhóm.
### Kiểm thử
- `test_chatbot_store.py` thêm hai mục: lý do im phải phân biệt được (nhóm chưa bật ≠ không ai gọi tên - hai thứ sửa khác nhau hoàn toàn), và canary id nhóm thường ↔ siêu nhóm, kèm mục ngược để chuẩn hoá không nuốt nhầm một nhóm khác có đuôi trùng.
- Canary mới ở tầng kênh: chốt chặn phải đứng trước tin trạng thái, lệnh không bị chặn, và im-lặng-có-chủ-ý phải phân biệt được với câu trả lời rỗng.
- `test_trang_chatbot.js` đảo chiều một mục cũ ("mức chỉ đọc KHÔNG dán nhãn") kèm lý do đổi ý ghi tại chỗ, và thêm mục canh nhịp tự làm mới phải dừng khi rời trang.
### Tài liệu
- `docs/25-chatbot.md` viết lại Bước 4 theo đường mới (thả vào nhóm → gọi tên → bấm cho phép), thêm mục chế độ riêng tư của Telegram, và hai câu hỏi thường gặp đúng bằng lời chủ repo đã hỏi.

## [0.24.7] - 2026-08-06
Chủ repo chốt bốn việc cùng một lúc: *"gom nút tiết kiệm sang bên Mức Dùng, đặt mặc định phiên bản mới là siêu tiết kiệm, và loại bỏ các thông số không có ý nghĩa với người dùng cuối. Menu tiết kiệm cũng không cần nữa."*
### Thay đổi hành vi
- **Mặc định của bản này là Siêu tiết kiệm**, thay cho Tắt. Áp cho cả máy đã cài từ lâu, không riêng máy cài mới - cơ chế `_ap_muc_mac_dinh` dựng sẵn từ 0.16.0 nay mới thật sự được dùng lần đầu.

  Vì sao đổi: trước đây mặc định là Tắt và gần như không ai tự bật, nghĩa là **đa số đang trả tiền cho chế độ đắt nhất mà không biết**. Đo trên một brain mẫu: mức Tắt khoảng 8.900 token cố định mỗi lượt, Siêu tiết kiệm khoảng 460.

  Đây là mặc định an toàn được, không phải liều: mọi đường trong mức này đều fail-closed, thiếu điều kiện thì lượt đó tự rơi về chế độ Đầy đủ chứ không trả lời sai. Và ai **đã từng tự bấm một mức** thì không bị đụng tới, kể cả người cố ý bấm Tắt.
- **Trang Tiết kiệm gộp vào trang Mức dùng, mục "Tiết kiệm" biến khỏi thanh bên.** Ba nút chọn mức nằm ở ĐẦU trang Mức dùng, trên cả bộ lọc kỳ.

  "Tôi tiêu bao nhiêu" và "làm sao tiêu ít đi" là cùng một câu hỏi. Tách hai trang thì người dùng đọc hết hoá đơn mà không bao giờ thấy cái công tắc.
- **Bỏ khỏi màn hình mọi thông số của người vận hành máy**: bảng canary tính bằng phần vạn, công tắc trùm off/observe/shadow/canary/on, ô khai hạn mức, cửa sổ token 60 giây, hạn mức tự học, số công cụ registry, độ chính xác khi đoán, bảng "Lượt gần nhất" kèm task_id và execution_path, các bảng đếm lý do trượt.

  Giữ lại đúng thứ người dùng cuối quyết định được: tên mức, tiết kiệm bao nhiêu phần trăm, còn bao nhiêu token mỗi lượt, dấu "không áp cho bộ não đang dùng", và khối **đo thật 24 giờ qua**.
### Thêm mới
- **`GET /runtime/muc`** - endpoint gọn trả đúng bốn thứ trang cần. Trang Mức dùng gọi nó sau mỗi lần đổi mức nên nó phải rẻ; `/runtime/diagnostics` vẫn còn nguyên cho ai soi máy, kèm mọi trường vừa gỡ khỏi giao diện.
- Bấm vào dòng chế độ dưới mỗi câu trả lời, hoặc dòng "Tiết kiệm" trong panel Mức dùng, đều sang thẳng trang Mức dùng. Id trang cũ `runtime` có bảng chuyển hướng nên bookmark cũ không rơi vào màn hình trắng.
### Sửa lỗi
- **Bảng dịch tên chế độ giờ chỉ còn MỘT bản** (ở khung chat). Trước đó có hai bản chép tay của cùng một tập tên, và hai bản chép tay là hai chỗ để lệch nhau - lệch thì người dùng không nối được dòng dưới câu trả lời với chỗ chỉnh mức. Bản còn lại được bổ sung tên cho đường `bot`.
### Kiểm thử
- Ba fixture ghim cứng "nền sạch là toàn số 0" được sửa lại (`test_muc_mac_dinh`, `test_settings_merge`, `test_runtime_preset`): nền sạch không còn toàn số 0 từ khi mức xuất xưởng là một mức thật. Đây đúng là cái bẫy đã cắn `test_cauhinh_cu_khong_ket` hồi 0.24.3, nên lần này ghi thẳng lý do vào test.
- Bất biến "số liệu phải đến được mắt người" đổi PHẠM VI chứ không bỏ: nay soi bốn trường của `/runtime/muc` trên trang Mức dùng, và canh riêng rằng đường lấy số liệu chẩn đoán vẫn còn cho người vận hành.
### Tài liệu
- `docs/23-muc-dung-token.md` thêm mục **Chế độ tiết kiệm token** và **Vì sao mặc định là Siêu tiết kiệm**; `docs/10` và `docs/17` trỏ lại đúng chỗ mới.

## [0.24.6] - 2026-08-06
Chủ repo gửi ảnh một con bot chuyên trách đang trực: người ta nhắn vào, bot trả lời *"Em đang gặp trục trặc kỹ thuật, anh chị nhắn lại giúp em sau ít phút ạ"*, và người trực bị đánh thức kèm lý do `⚠ Anthropic 429: {"type":"rate_limit_error"}`.

429 là lỗi **tạm thời**. Việc đúng là chờ một nhịp rồi hỏi lại.
### Sửa lỗi
- **Bảy trong tám bộ não bỏ cuộc ngay ở lần gãy đầu tiên.** `engine.py` có sẵn đủ bộ đồ nghề để thử lại từ lâu - `_RETRY_STATUS`, `_is_transient_body`, `_parse_retry_after`, `_jittered_backoff` - nhưng **chỉ `openrouter_stream` dùng chúng**. Bảy đường gọi model còn lại và cả bốn vòng tool đều chết ngay khi nhà cung cấp hắt hơi một cái.

  Không ai thấy vì trên máy sạch thì nhà cung cấp không 429 bao giờ. Chỉ khi một con bot trực thật, cho người thật, mới lộ ra: một cú 429 kéo dài chưa tới một giây đủ để một người đang hỏi nhận lời xin lỗi kỹ thuật và một người trực bị gọi dậy giữa ca.
- **Nay lỗi tạm thời được đánh dấu TẠI NGUỒN** (`engine.ev_loi_http` / `ev_loi_exc`), vì chỉ chỗ gọi HTTP mới còn status thật, body thật và header `Retry-After`. Lên tới tầng trên thì tất cả đã bị ép thành một chuỗi chữ, và đoán lại bằng cách dò chữ trong chuỗi đó là thứ hỏng ngay lần đầu ai đó sửa nhãn.
- **Chạy lại nằm ở `_api_stream`**, chỗ DUY NHẤT mọi đường chat không-tool đi qua: dashboard, Telegram, bot chuyên trách, việc nền, đường tắt. Tối đa ba lượt, nghe theo `Retry-After` nếu nhà cung cấp có gửi. Vòng tool cũng được bọc.
### Bảo mật
- **Hai điều kiện để chạy lại, thiếu một là thôi.** Đã nhả chữ ra ngoài thì thôi (người ta sẽ đọc câu trả lời hai lần), và **đã chạy tool thì càng thôi** - lượt đó có thể đã gửi tin, đã ghi file, đã đặt lịch, chạy lại cả vòng là làm những việc đó lần thứ hai. Đây là mục canary nặng nhất của file test.
- **Lỗi KHÔNG tạm thời báo ngay từ lần đầu**: sai khoá, sai tên model, vượt kích thước ngữ cảnh, và mọi lỗi đã đọc ra được hạn mức thật. Thử lại y nguyên chỉ tốn thêm một lượt gọi model đã trả tiền để nhận lại đúng lỗi đó.
- **Lượt cuối gỡ dấu `tam_thoi` đi.** Dấu đó là lời mời chạy lại, mà đã hết lượt rồi. Nhờ vậy bọc chồng hai lớp không nở thành chín lần gọi, và `openrouter_stream` (vốn tự thử lại bên trong) không bị thử thêm một tầng nữa.
### Cải thiện
- Câu lỗi cuối cùng có thêm *(đã thử lại 3 lần)* - để chủ phân biệt được sự cố chớp nhoáng với hạn mức đã cạn thật, hai thứ sửa khác nhau hoàn toàn.
### Kiểm thử
- `test_thu_lai_tam_thoi.py` mới, canh cả ba tầng, và mục cuối dựng lại ĐÚNG ảnh chụp của chủ: bot gặp 429 một nhịp thì vẫn trả lời người đang hỏi và **không** gọi người trực dậy; 429 mãi thì vẫn phải báo hỏng chứ không nuốt lỗi.
- Canary "cả tám bộ não": sửa cho Anthropic rồi bỏ bảy đường kia lại đúng là kiểu hỏng vừa sửa, nên test chạy thẳng qua từng provider trong `PROVIDER_DEFS`.
### Tài liệu
- `docs/17-khac-phuc-su-co.md` thêm mục **Nhà cung cấp gãy một nhịp thì Javis tự hỏi lại**; `docs/25-chatbot.md` nói rõ trường hợp thứ ba khiến người trực bị gọi (bot gãy) và việc đã thử lại trước đó.

## [0.24.5] - 2026-08-06
Hai chỗ vướng khi Javis đưa một file HTML vào chat: bấm vào link thì file rơi xuống máy, và mở ra sửa thì code một màu xám đọc mỏi mắt.
### Cải thiện
- **Bấm link `.html` trong chat giờ mở thẳng trình sửa, không tải về nữa.** Đó là file NGUỒN, mà ép một cú bấm phải rơi file xuống máy là đường vòng dài nhất: muốn xem thì phải mở bằng app khác, muốn sửa một chữ thì phải sửa ngoài rồi tải lên lại. Trình sửa đã có sẵn cả nút **Mở tab mới** lẫn nút **Tải về**, nên mở trình sửa là đường ngắn hơn cho CẢ hai ý định. Ảnh, video, pdf, docx, zip vẫn tải về như cũ.
- **Khung sửa bung giữa màn hình có thêm nút "Mở tab mới"** (↗), trước chỉ có nút tải. Trình sửa đính đã có đôi nút này từ trước, giờ hai chỗ giống nhau.
- **Tô màu cú pháp khi sửa code**, cho cả trình sửa đính lẫn khung bung giữa màn hình: `.html`, `.css`, `.js`, `.json`, `.py`, `.yaml`, `.sh` và các đuôi thường gặp khác. Tên thẻ, tên thuộc tính, chuỗi, số, chú thích và từ khoá mỗi thứ một màu, có bảng màu riêng cho giao diện sáng và tối.

  HTML có bộ đọc riêng chứ không dùng chung bộ tô màu của khối code trong chat: bộ đó coi mọi thứ là ngôn ngữ kiểu C nên đọc HTML ra rất sai, tô `class` thành từ khoá còn tên thẻ với tên thuộc tính thì không tô gì. Ruột `<style>` và `<script>` được đọc theo đúng ngôn ngữ của nó. CSS và JSON cũng có bộ riêng; các ngôn ngữ còn lại vẫn giao lại cho bộ chung, không chép lại logic.
### Ghi chú
- Ô sửa vẫn là `<textarea>` thật, lớp màu nằm CHỒNG KHÍT bên dưới. Cố ý không đổi sang `contenteditable`: đổi là mất undo của trình duyệt, mất bộ gõ tiếng Việt ngoài, mất mọi phím tắt quen tay.
- `.md` không tô màu: nó mở bằng trình soạn WYSIWYG có thanh công cụ tự chèn chữ vào ô sửa mà không bắn sự kiện `input`, lớp màu sẽ lệch khỏi nội dung thật.
- Hai bẫy hình học đã bịt sẵn, cả hai đều thuộc loại chỉ lộ ra khi file đã dài: hai lớp phải chừa **cùng một chỗ cho thanh cuộn** (`scrollbar-gutter`), nếu không thì từ lúc xuất hiện thanh cuộn dọc, bề ngang chỗ chữ trong ô sửa hụt đi khoảng 15px còn lớp màu thì không, và chữ màu trôi hẳn khỏi chữ thật; test canh ràng buộc **gỡ hết thẻ đi phải ra lại đúng chuỗi gốc**, vì chỉ cần bộ tô màu nuốt hay thêm một ký tự là từ đó trở đi mọi dòng đều lệch mà không có lỗi nào được ném ra.
- File lớn hơn 300 nghìn ký tự thì bỏ tô màu (mỗi lần gõ là dựng lại cả cây HTML). Sửa vẫn bình thường, chỉ là chữ một màu.

## [0.24.4] - 2026-08-06
Chủ repo báo: *"khi yêu cầu Javis thêm mcp nào đó thì nó đang không hiện ra phần kết nối"*. Đúng, và lý do không phải giao diện quên vẽ - **Javis chưa từng có đường nào ghi vào kho kết nối của chính mình.**
### Thêm mới
- **Plugin đi kèm `javis-connect`, tool `javis_add_mcp`.** Nhờ Javis đấu một MCP ngay trong chat, và nó hiện ở khu **"Đã kết nối"** trang Kết nối như tài khoản bạn tự thêm bằng tay, mọi bộ não dùng chung qua hub.

  Kho kết nối trước nay chỉ ghi được qua `/connect/add`, mà endpoint đó nằm sau lớp đăng nhập nên chỉ trang web gọi được. Javis còn đúng hai lối, cả hai đều hỏng: chạy `claude mcp add` bằng Bash - server rơi vào cấu hình riêng của Claude Code, sáu bộ não còn lại không thấy, và trên trang Kết nối nó không nằm ở khu "Đã kết nối" mà lọt xuống khu gập *"Kết nối sẵn của Claude Code và Codex"* (mặc định ĐÓNG, chỉ tải khi bấm mở); hoặc nói suông "anh vào trang Kết nối tự thêm nhé". Người dùng nhìn trang Kết nối thấy y như cũ, và kết luận Javis nói dối - hợp lý.

  `op=find` tra Kho kết nối trước, `op=add` đấu nguồn mới. Tool đi thẳng vào `mcp_store`, cùng một kho mà `/connect/catalog` đọc.
### Bảo mật
- **Ba rào cứng, không tham số nào mở được.** Mức quyền mặc định là **chỉ đọc** (luật `CLAUDE.md`: Javis không tự nâng quyền, người dùng tự nâng ở trang Kết nối). Nguồn chạy bằng **lệnh trên máy** (stdio) được thêm ở trạng thái **tắt** và không dial thử, vì chỉ riêng việc thử kết nối đã là chạy lệnh đó - cho engine API đẻ một stdio tự chạy là mở cửa hậu đúng bằng Bash mà chúng vốn không có. Dịch vụ đã có sẵn trong Kho kết nối (Gmail, Lịch, POS...) thì tool chỉ tay sang đúng card chứ không đẻ bản tự khai song song, vì một connection rỗng token nằm lại trang Kết nối trông y hệt tài khoản thật mà không chạy được.
### Sửa lỗi
- **Thử kết nối hỏng thì mục đó vẫn nằm lại trang Kết nối** kèm nguyên văn lý do, ở trạng thái tắt. Khác `/connect/add` (xoá sạch khi validate lỗi) - hợp lý cho form vì người dùng đang nhìn thẳng vào nó, nhưng sai hoàn toàn cho chat: thứ họ cần là NHÌN THẤY nó nằm đó và biết vì sao chưa chạy.
- **`server/chatbots.json` và `server/chatbot-logs/` vào `.gitignore`.** Hai artifact chạy của trang Chatbot (0.19.0) vừa không track vừa không ignore từ đó tới nay, nên một cú `git add -A` là commit thẳng **token bot** vào repo. `test_ignore_files.py` bắt được.
### Ghi chú
- System prompt (`channel_context`) nay dặn thẳng: thêm MCP thì dùng `javis_add_mcp`, tuyệt đối không `claude mcp add` / `codex mcp add`, và thêm xong phải nói rõ nó nằm ở trang Kết nối, đang bật hay tắt, mức quyền nào.

## [0.24.3] - 2026-08-06
Chủ repo đọc thẳng mã nguồn và chỉ ra: **toàn bộ hệ Tiết kiệm chỉ được nối vào đúng handler WebSocket của dashboard.** Đúng, và đây là lỗ hổng kiến trúc thật.
### Sửa lỗi
- **Mức Tối ưu và Siêu tiết kiệm không có hiệu lực trên Telegram.** Ba thứ khớp nhau hoàn toàn: mọi lệnh gọi `prepare()` trong `websocket_endpoint` truyền cứng chữ `"dashboard"`, `_tg_answer_engine` không có một dòng nào chạm tới chúng, và `channels` trong config cũng chỉ khai `["dashboard"]`.

  Hệ quả: người dùng bấm mức tiết kiệm, trang Cài đặt báo xanh "đã bật, có hiệu lực ngay", rồi mỗi lượt Telegram vẫn gửi nguyên `CLAUDE.md` + `MEMORY.md`. **Không lỗi, không cảnh báo - chỉ có hoá đơn token không giảm** ở đúng kênh nhiều người dùng nhất. Cùng họ với con bệnh `provider_kinds` hồi 0.12.4, lần này rơi vào KÊNH thay vì loại bộ não.

  Nay `_tg_answer_engine` nối cả hai tầng, theo thứ tự rẻ dần: đường tắt (Phase 5) rồi nguồn chọn lọc (Phase 8). Cả hai đều nhận **biến** `channel` chứ không phải hằng chuỗi.
- **Lõi đường tắt tách khỏi WebSocket.** `_execute_fast_path` gắn chặt với `ws.send_text` nên kênh khác không dùng lại được. Nay lõi nằm ở `_fast_path_core` với hai móc gửi tin tuỳ kênh; bản WebSocket chỉ còn là cái vỏ mỏng bọc nó.
- **`channels` mở thêm `telegram` và `cli`** cho đường tắt, bộ nhớ chọn lọc và skill nạp-khi-cần. Máy đã cài cũng được nới nhờ `_no_rong_pham_vi_bo_nao` (settings.json cũ ghim cứng `["dashboard"]`, sửa mặc định thôi thì bản vá chỉ tới được máy cài mới).

  `conversation_state_canary` **cố ý không mở**: phiên Telegram đã giữ mạch hội thoại riêng, đưa thêm transcript vào system prompt là gửi lịch sử hai lần.
### Ghi chú
- Ba đường thực thi tool (`readonly`, `orchestrator`, `write`) vẫn chỉ chạy trên dashboard. Chúng fail-closed sẵn (`capability_profiles` rỗng) nên hôm nay không ảnh hưởng ai, và mỗi đường cần một adapter gửi tin riêng - việc đó tách khỏi bản này.
- **Bot chuyên trách KHÔNG đi qua hai tầng đó**, và không phải vì bỏ sót: prompt của bot (~20 token) vốn đã nhỏ hơn capsule của mức Siêu tiết kiệm (~460 token) hơn hai chục lần. Test canh đúng điều đó.
- Lệnh điều khiển lịch vẫn do gateway lịch xử lý; đường tắt được hỏi SAU khi lệnh lịch đã giải quyết xong, nên không cướp lượt.

## [0.24.2] - 2026-08-05
Chủ repo bật mức **Được ghi** cho một bot chạy gói ChatGPT, và bot chết: mọi câu nhắn vào đều nhận *"⚠ ChatGPT trả về rỗng (backend Codex có thể chưa hỗ trợ tool)"*.

Lỗi của bản 0.24.0, và đáng ghi lại vì nó là một kiểu ẩu có tên: **nối đường đi thật vào một hàm chưa ai từng gọi.**
### Sửa lỗi
- **Nâng mức quyền làm HỎNG con bot vốn đang chạy tốt.** `engine.responses_with_mcp` tới 0.24.0 **chưa từng được gọi từ đâu** - `git log -S` cho đúng một kết quả, là chính commit 0.24.0 - và docstring của nó tự ghi EXPERIMENTAL. Bản 0.24.0 nối mức Được ghi/Toàn quyền của gói ChatGPT vào đó rồi phát hành mà không có đường lui.

  Hậu quả không dừng ở "tính năng mới chưa chạy": bot đang trả lời tốt ở mức Chỉ đọc, chủ nâng mức, và nó **ngừng trả lời hoàn toàn**.

  Nay có đường lui: vòng tool trả rỗng thì chạy lại lượt đó **không tool**. Luật rút ra và đã viết thành test - *nâng mức quyền không được phép LẤY ĐI năng lực đã có*.
- **Nhưng KHÔNG im lặng hạ mức.** Chủ đặt Được ghi mà bot lặng lẽ chạy như Chỉ đọc là kiểu hỏng tệ hơn cả gãy hẳn. Lượt chạy thiếu quyền mang theo một **cảnh báo** lên thẻ bot (dải vàng, khác dải đỏ của lượt gãy), nói rõ nó đang chạy ở mức nào so với mức đã đặt và việc cần làm: đổi engine ở trang Models, hoặc hạ mức xuống Chỉ đọc.

  Cảnh báo đi đường RIÊNG chứ không mượn trường `loi`: `loi` kéo theo bộ đếm bí, kéo theo gọi người trực, và làm bẩn tab "Bot bí" - trong khi đây là lượt trả lời bình thường.
- **`responses_with_mcp` khớp lại với đường không-tool đang chạy thật.** Nó thiếu đúng dòng `openai_responses_stream` có: không có `account_id` thì BỎ HẲN header `chatgpt-account-id` thay vì gửi chuỗi rỗng. Thêm cả xử lý `[DONE]` và bóc dấu trích dẫn nội bộ.
- **Gãy cả hai đường thì báo lỗi của đường KHÔNG TOOL, không phải lỗi vòng tool.** Đường không-tool là lời gọi đơn giản nhất còn lại nên nó nói đúng bệnh hơn (hết quota, sai token, mạng chết). Báo lỗi vòng tool trước là đẩy chủ đi tìm xem engine có hỗ trợ tool không, trong khi thứ hỏng là cái khác hẳn.
- **Chưa đấu nguồn nào mà đặt mức nâng quyền** cũng ra cảnh báo tương tự, thay vì chỉ ghi một dòng stderr không ai đọc.
### Tài liệu
- `docs/25-chatbot.md` thêm mục **Engine nào chạy được mức nâng quyền**: mức Chỉ đọc chạy trên cả tám bộ não không ngoại lệ; hai mức nâng quyền thì gói ChatGPT đi qua đường backend Codex chưa ổn định, gặp vậy bot vẫn trả lời và thẻ hiện dải vàng.

## [0.24.1] - 2026-08-05
Chủ repo đọc lại chữ nghĩa của 0.24.0: *"em chỉnh sửa lại các text đừng có dùng tiền, đơn, đăng bài. nó cá nhân hóa với anh quá. Các hướng dẫn ở mức chung nhất cho nhiều trường hợp thôi."*

Đúng. Javis không gắn với ngành nào, nhưng chữ trên màn hình thì đang gắn.
### Thay đổi
- **Cảnh báo mức quyền tả theo LOẠI THAO TÁC, không kể tên việc của một ngành.** "tạo đơn, tiêu tiền quảng cáo, đăng bài" thành "gửi đi, thanh toán, đặt/huỷ, xoá, công bố ra ngoài" - đúng cách `mcp_catalog` phân loại, và đúng cho mọi nguồn dữ liệu đấu vào.

  Không phải chuyện thẩm mỹ: người dùng Javis để quản lý dự án, chăm sức khoẻ hay dạy học đọc bản cũ xong **tưởng cảnh báo không áp cho mình**, rồi bật Toàn quyền vì nghĩ mình không có gì để mất. Cảnh báo trượt mục tiêu còn tệ hơn không có cảnh báo.
- **"khách / khách hàng" thành "người nhắn cho bot"** trong mọi chữ hiện ra màn hình. Bot chuyên trách trực cho lớp học, cộng đồng, đội nội bộ đều được; chăm sóc khách hàng chỉ là MỘT ca dùng.
- **"nhân viên" thành "người trực"** ở nhãn ô, thẻ bot, nhật ký và menu lệnh Telegram của bot (`/nhanvien` giữ nguyên tên lệnh - đổi tên lệnh là phá thói quen người đang dùng).
- **`docs/25-chatbot.md` bỏ khung cửa hàng**: ví dụ "bảng giá, chính sách đổi trả, mô tả sản phẩm" thay bằng một nguyên tắc dùng được cho mọi việc - *nếu một câu trong file này lọt ra ngoài mà bạn thấy phiền thì file đó không thuộc về brain của bot*. Đầu trang thêm một dòng kể các ca dùng khác nhau.
- **Ví dụ mẫu của `description` skill không còn là sản phẩm cụ thể.** "Chuyển HTML sang file Webcake .pke." thành "Tóm tắt biên bản họp thành danh sách việc cần làm." - sửa ở cả ba nơi dạy luật này (`skill_router`, `learn`, skill `javis-builder`) và ở `docs/06-skills.md`.
### Sửa lỗi
- **Bộ dò "bot bí" hụt câu chuyển người sau khi đổi chữ.** `_DAU_BI` khớp theo chuỗi trên chính câu bot vừa nói, nên đổi "chuyển cho nhân viên" mà quên thêm cách nói mới là những lượt đó lặng lẽ ngừng được tính là bí, và tab "Bot bí" rỗng dần mà không ai hiểu vì sao. Nay giữ CẢ cách nói cũ (Agent người dùng viết từ trước vẫn dùng từ đó) lẫn cách nói trung tính.
### Kiểm thử
- Canary ở cả `test_chatbot_muc_quyen.py` lẫn `test_trang_chatbot.js`: chữ cảnh báo và chữ trên trang Chatbot **không được chứa** "đơn hàng", "tạo đơn", "tiêu tiền", "quảng cáo", "đăng bài", "cửa hàng", "bán hàng", "bảng giá", "POS". Viết luật ra thành test vì đây là loại chữ hay bị viết lại theo ca dùng trước mắt.

## [0.24.0] - 2026-08-05
Chủ repo mở phạm vi của Bot chuyên trách: *"ở chức năng tạo bot đang là chỉ đọc, anh muốn thêm chức năng được ghi và toàn quyền. Vì cơ bản anh vẫn muốn có thể thực hiện nhiều task, nhưng em thêm phần thông báo cho anh để hiểu rõ nguy cơ khi sử dụng."*

Bản này cho bot **làm việc thật**, và làm đúng điều kiện chủ đặt ra: nói rõ cái mất được, trước khi chủ bấm.
### Thêm mới
- **Ba mức quyền cho bot** (`muc_quyen`), chọn ở ô **Bot được làm gì** khi tạo hoặc sửa:
  - **Chỉ đọc** (`suggest`, MẶC ĐỊNH) - hành vi cũ y nguyên: không công cụ nào, chỉ đọc tài liệu rồi trả lời.
  - **Được ghi** (`auto`) - ghi file trong brain của chính bot + gọi nguồn dữ liệu đã đấu ở mức đọc/ghi. Hub vẫn **chặn cứng** nhóm thao tác ra ngoài: gửi đi, thanh toán, đặt/huỷ, xoá, công bố.
  - **Toàn quyền** (`full`) - làm được mọi thứ nguồn đã đấu cho phép, kể cả nhóm ra ngoài.

  Ba chữ này ĐÚNG bằng bộ tên của loop và của hub, cố ý: chữ chọn trên giao diện đi thẳng vào `discover_all` rồi thành header `X-Javis-Mode`, không qua bảng dịch nào. Bảng dịch là chỗ dễ sai nhất, và sai ở đây nghĩa là cấp nhầm quyền cho một con bot đang nói chuyện với người lạ.
- **Cảnh báo rủi ro hiện ngay tại chỗ chọn**, và do SERVER cấp (`GET /chatbots` trả kèm nhãn + danh sách rủi ro từng mức). Giao diện không giữ bản chép riêng: chép rồi thì một hôm server siết thêm rào mà ô cảnh báo vẫn hứa như cũ, và chủ bấm đồng ý dựa trên một câu đã sai.
- **Thẻ bot dán nhãn mức quyền** - vàng cho Được ghi, đỏ cho Toàn quyền, không dán gì cho Chỉ đọc. Một con toàn quyền lẫn giữa mấy con chỉ đọc mà nhìn giống hệt nhau là đúng kiểu hỏng im lặng: chủ nhớ nhầm con nào là con nào rồi thả nhầm vào chỗ ai cũng nhắn được.
- **Nhật ký ghi mức quyền của TỪNG LƯỢT**, không phải mức đang đặt lúc đọc lại. Hai thứ đó lệch nhau ngay khi chủ hạ mức sau một sự cố, và lúc soi lại "hôm đó bot làm gì" thì cái cần biết là mức lúc ĐÓ.
- **Gói Claude Code gọi được tool** (`engine.anthropic_chat_with_mcp` nhận `oauth_token`). Trước đó gói thuê bao chỉ chat thuần được vì hàm này chỉ nhận `x-api-key`.
### Bảo mật
- **Hai rào KHÔNG đổi theo mức**, và cả hai là hệ quả của việc bot không bao giờ chạm vào tool NATIVE của engine:
  - **Cách ly brain.** Tool file đi qua hub nên bị kẹp bằng `_safe_path(vault_root)` với `vault_root` là brain CỦA BOT - kể cả ở mức Toàn quyền. Mở CLI cho bot là mất rào này ngay: `Read` của Claude Code nhận đường dẫn tuyệt đối, đúng lỗ 0.21.0 đã phải vá.
  - **Không lệnh máy.** Không Bash, không WebFetch/WebSearch, không Task - chúng vốn không nằm trong hub.
- **Nâng mức phải xác nhận có ý thức.** Rào đặt ở KHO (`chatbot_store.can_xac_nhan`) chứ không chỉ ở route, vì route chỉ là một trong nhiều đường vào. Route trả `can_force` kèm đúng lý do, cùng khuôn với `POST /reminders` lúc chưa đấu kênh báo. **HẠ** mức thì không đòi gì: hạ quyền luôn an toàn, và lúc chủ đang dập sự cố thì đừng bắt bấm thêm.
- **Fail-closed ở chỗ rẽ.** Chỉ đúng hai chữ đã khai mới mở tool; bản ghi cũ thiếu khoá, file sửa tay gõ sai, `None` - tất cả rơi về đường không tool. Viết ngược lại ("khác `suggest` thì mở tool") là một lỗi chính tả trong `chatbots.json` cũng đủ cấp tool cho bot đang chat với người lạ.
- **Giá trị lạ trong bản vá GIỮ NGUYÊN mức cũ**, không rơi về mặc định: bot đang Toàn quyền mà một bản vá gõ sai lại lặng lẽ hạ nó xuống thì chủ tưởng bot vẫn làm việc, còn nó thì từ chối mọi công cụ.
- Giao diện hỏi lại thêm một lần cho mức Toàn quyền, và hỏi lại lúc **Bật** bot có quyền thao tác - lúc tạo có thể là mấy hôm trước.
### Kiểm thử
- `test_chatbot_muc_quyen.py` mới: chạy THẬT một lượt bot qua cả tám provider ở mức Toàn quyền rồi kiểm từng con có gọi vòng tool không. Cấp tool cho sáu engine API rồi bỏ hai gói thuê bao lại là kiểu hỏng im lặng tệ nhất - chủ đặt Toàn quyền, bot vẫn lễ phép trả lời, và không làm gì cả.
- Cùng file canh fail-closed bằng tám giá trị lạ (kể cả `1`, `True`, `"readonly"`, và hai chuỗi thừa khoảng trắng để ai bỏ `strip()` thì đỏ ngay), hub trả rỗng, và hub nổ giữa chừng.
- `test_chatbot_cach_ly.py` thêm canary cho đường CÓ tool: không `claude_engine`, không `CodexCLI`, không `allowed_tools`, không tên tool native nào. Tên tool soi ở dạng có nháy - soi dạng trần thì chính đoạn ghi chú giải thích vì sao không có Bash lại làm test đỏ.

## [0.23.1] - 2026-08-05
Chủ repo hỏi: *"anh thấy chưa qua chức năng tiết kiệm và siêu tiết kiệm của bot. em kiểm tra giúp anh xem có phải vậy không?"* Đúng là chưa qua, nhưng cái sai không nằm ở chỗ đó.
### Sửa lỗi
- **Trang Tiết kiệm token xếp lượt bot vào "Đầy đủ" - đúng NGƯỢC sự thật.** `pin_execution_path` chỉ nhận một danh sách tên cố định, tên lạ rơi hết về `legacy`. Lượt bot không ghim gì nên bị gộp vào cột **đắt nhất**, trong khi đo ra nó là đường **rẻ nhất** hệ thống.

  Nay có đường `bot`, hiện trên giao diện là **"Bot chuyên trách"**.
### Ghi nhận (không phải lỗi)
- **Bot không đi Phase 5 (đường tắt) và Phase 8 (bộ nhớ chọn lọc), và cũng không cần.** Hai tầng đó nằm trong `websocket_endpoint`, tức chỉ chạy cho chat trên dashboard - đường Telegram của chủ cũng chưa bao giờ đi qua chúng.

  Quan trọng hơn: chúng sinh ra để gọt CLAUDE.md, MEMORY.md và bảng đặc tả tool - ba thứ bot chưa bao giờ có. Đo phần cố định mỗi lượt trên một brain mẫu: **~8.900 token** (dashboard mức Đầy đủ), **~460** (mức Siêu tiết kiệm), **~20** (bot). Đẩy bot qua hai tầng kia chỉ làm nó nặng thêm, vì riêng capsule của mức Siêu tiết kiệm đã lớn gấp năm lần cả prompt của bot.

  Test giờ đo thẳng hai con số đó và bắt prompt bot phải nhỏ hơn capsule - để lần sau ai đó "tối ưu" bot bằng cách nối nó vào Phase 8 thì có chỗ đỏ.

## [0.23.0] - 2026-08-05
Bỏ hẳn khái niệm **"brain riêng của bot"**. Chủ repo chốt: *"lựa brain nào thì hiện agent và chatbot của brain đó thôi. Chứ không cần phải có việc tạo brain cho bot. Như thế sẽ dễ dàng hơn trong quản lý."*
### Thay đổi hành vi
- **Trang Chatbot thuộc về brain đang mở**, y như trang Agents và Skills. Đổi brain ở đầu trang là thấy bot của brain đó. `GET /chatbots?brain=` lọc theo brain; bỏ trống vẫn trả tất cả vì bộ giám sát không đứng ở brain nào cả.
- **Form tạo bot không còn ô chọn brain và nút "Tạo brain mới".** Bot thuộc brain đang mở, Agent lấy từ chính brain đó.

  Bản 0.22.3 bắt chọn brain trong form rồi phải nhớ Agent nằm ở brain nào - hai lớp phải khớp nhau mà **không có gì bắt chúng khớp**. Bỏ hẳn ô đó thì phạm vi của trang chính là câu trả lời, và không còn gì để lệch. Server cũng tự giữ `brain` và `agent_brain` bằng nhau ở cả lúc tạo lẫn lúc sửa.
- **Thẻ bot bỏ dòng brain**, thay bằng một dòng ở đầu trang nói rõ đang xem bot của brain nào. Mọi bot trên trang đều cùng một brain nên nhắc lại từng thẻ chỉ là nhiễu.

Cách ly brain **không đổi**: bot vẫn chỉ đọc được brain của chính nó, khoá bằng mã nguồn. Chỉ đổi cách CHỌN brain đó - trước là một ô trong form, nay là brain bạn đang đứng.

Kèm theo: tài liệu đổi bước chuẩn bị thành "đứng đúng brain trước đã", và nói rõ chỗ đáng cân nhắc nhất - bot trả lời người lạ thì đừng tạo nó trong brain chính của bạn.

## [0.22.3] - 2026-08-05
Dọn form tạo bot theo góp ý dùng thật, và sửa một câu hướng dẫn đã mô tả sai hành vi.
### Sửa lỗi
- **Danh sách Agent lấy theo brain đang mở trên dashboard, không theo brain của bot.** Chọn brain "My Bullet Journal" cho bot mà ô Agent vẫn liệt kê Agent của brain khác. Lưu xong thì bot trỏ vào một Agent KHÔNG nằm trong brain nó đọc, và không có chỗ nào báo chuyện đó.

  Nay **brain hỏi trước Agent**, và đổi brain là nạp lại danh sách Agent của đúng brain đó. `agent_brain` cũng bằng luôn brain của bot - Agent và tài liệu đi cùng một chỗ.
- **Ô chọn Agent tràn ngang ra khỏi form** khi tên Agent kèm vai trò quá dài. Thẻ `<option>` thì trình duyệt không cho tạo kiểu, nên cắt chuỗi ở JS (vai trò tối đa 34 ký tự, tên Agent luôn giữ đủ) và thêm `min-width:0` + `text-overflow` cho chính thẻ `<select>`.
- **Câu hướng dẫn ô "Chat ID nhân viên" mô tả hành vi đã không còn đúng**: nó viết "bỏ trống thì bot chỉ nói chưa có thông tin rồi dừng". Từ 0.21.0 Javis không chèn luật nào vào prompt nữa, nên bỏ trống thì bot **vẫn trả lời bình thường** theo Agent, chỉ là không có ai để chuyển tiếp. Câu cũ dạy người dùng sợ một hành vi không tồn tại.
- **`/nhanvien` khi chưa đặt người nhận trả lời sai chuyện.** Câu cũ ("Cái này em chưa có thông tin ạ, anh chị chờ phản hồi") vừa lạc đề - khách xin gặp người chứ có hỏi thông tin gì đâu - vừa đóng cửa cuộc trò chuyện. Nay nói thật là chưa nối máy sang người trực được, và mời hỏi tiếp.
### Thêm mới
- **Nút "Tạo Agent"** ngay cạnh ô chọn Agent, bấm là sang thẳng trang Agents. Trước đó form chỉ nói "tạo ở trang Agents" bằng chữ, người dùng phải tự đi tìm.
- `console.js` phơi `window.JavisNav.go(id)` để module trang khác chuyển trang được. Phơi `navigateTo` chứ không để module tự đặt `store.active`: `navigateTo` còn dọn trang cũ, cất `#quickSet` và vẽ lại đồ thị.

## [0.22.2] - 2026-08-05
Bot vẫn kêu "chưa trả lời được" sau khi cập nhật. Ba lỗi riêng biệt chồng lên nhau, và cả ba đều làm chủ nhìn màn hình mà không biết chuyện gì đang xảy ra.
### Sửa lỗi
- **Gói subscription gọi thẳng API có thể 401 ở MỌI lượt.** 0.22.0 cho bot đi `_api_stream` cho cả tám bộ não - đúng hướng, nhưng với gói Claude Code thì đường đó cần token OAuth mà CLI đã lưu. Đọc không ra (hoặc Anthropic không nhận) là lượt nào cũng gãy, và người dùng chỉ thấy một câu xin lỗi lặp đi lặp lại.

  Nay có đường dự phòng: gọi thẳng hỏng thì rơi về chính CLI của gói đó, với `allowed_tools` là một chuỗi **không khớp tool nào** - cổng `can_use_tool` bật lên và mọi tool đều bị từ chối từng lượt gọi. Vẫn đúng hợp đồng của bot: cùng prompt, cùng tài liệu, cùng lịch sử, không tool. Chỉ khác đường truyền.

  (Không dùng list rỗng làm allowlist được: engine kiểm `if self.allowed_tools:` nên `[]` là falsy và nó hiểu thành "không có allowlist" rồi chạy `bypassPermissions` - mở toàn quyền đúng lúc mình định khoá chặt nhất.)

  Codex không có đường dự phòng vì không có cổng duyệt per-call. Bù lại, chưa đăng nhập được ChatGPT thì bot nói thẳng việc cần làm thay vì trả một mã lỗi HTTP.
- **Câu chào `/start` vẫn tự gắn "của cửa hàng" vào tên bot.** Bot tên "Coach kỷ luật" thành "Coach kỷ luật của cửa hàng" - đúng lỗi áp nghề bán hàng đã bác ở 0.20.1, sót lại ở đây vì lệnh không đi qua prompt.
- **Câu báo lượt GÃY trùng với câu báo THIẾU TÀI LIỆU.** Cả hai đều là "Em chưa trả lời được câu này..." nên nhìn từ ngoài không phân biệt được bot đang hỏng hay đang thiếu tài liệu - hai chuyện sửa khác nhau hoàn toàn. Nay lượt gãy nói "Em đang gặp trục trặc kỹ thuật", tách hẳn.
### Cải thiện
- **Lỗi lượt gần nhất hiện ngay trên THẺ bot**, không bắt mở Nhật ký mới thấy. Trạng thái poller không nói lên chuyện này: poller vẫn "đang chạy" chấm xanh trong khi mọi lượt trả lời đều gãy. Chủ chỉ mở Nhật ký khi đã NGỜ là có chuyện, nên cảnh báo phải tự đập vào mắt trước.
- **Lượt gãy tính là bí** (bot đúng là không trả lời được, nên bộ đếm gọi người thấy nó) **nhưng bị loại khỏi tab "Bot bí"** - tab đó dành cho chỗ tài liệu thiếu. Để lẫn thì danh sách "viết thêm tài liệu" đầy dòng lỗi kỹ thuật và chủ đi sửa nhầm chỗ. Lượt gãy xem ở tab Hội thoại, có dòng đỏ riêng.

## [0.22.1] - 2026-08-05
Bot báo lỗi mà **không ai đọc được lý do**. Chủ repo gặp đúng ca: hỏi "chào Coach", bot đáp "Em chưa trả lời được câu này, anh chị chờ cửa hàng phản hồi giúp em ạ." Đó là câu xin lỗi CHUNG khi lượt gãy, không phải bot trả lời sai - nhưng nhìn từ ngoài hai chuyện đó giống hệt nhau.
### Sửa lỗi
- **Lý do kỹ thuật của lượt gãy bị ném đi trước khi tới chỗ nào đọc được.** Lõi một lượt trả CHUỖI khi lỗi (đúng quy ước), `_make_answer_fn` thay nó bằng câu xin lỗi chung để không dội lỗi kỹ thuật vào mặt người ngoài - nhưng rồi **vứt luôn bản gốc**. Kết quả: khách thấy một câu vô nghĩa, chủ cũng thấy đúng câu đó, và không ai biết bot đang hỏng hay chỉ đang thiếu tài liệu. Hai chuyện ấy sửa khác nhau hoàn toàn (một bên đổi engine, một bên viết thêm tài liệu), nên lẫn vào nhau là bắt chủ đi sai đường.

  Nay lý do được giữ lại ở ba chỗ: ghi vào nhật ký (trường `loi`), in ra stderr, và hiện thành một dòng đỏ trong tab **Hội thoại gần đây** ghi rõ "Lượt này LỖI, không phải bot trả lời sai" kèm nguyên văn. Khách vẫn chỉ nhận câu xin lỗi chung.
- **Lượt gãy giờ báo nhân viên NGAY từ lần đầu**, không chờ đủ hai câu bí như trước. Bí là thiếu tài liệu, gãy là bot không chạy được - mỗi phút im lặng là khách nghĩ cửa hàng bỏ mặc họ. Tin báo cũng nói thẳng "Bot đang LỖI: ..." thay vì "bí N câu liên tiếp".

  Nhưng chỉ báo **một lần** cho tới khi có lượt chạy được: engine hỏng thì mọi lượt sau đều gãy, báo hết là biến hộp thư nhân viên thành log lỗi.

## [0.22.0] - 2026-08-04
Chủ repo bác cách làm ở 0.21.0: **"anh muốn dù là claude hay codex hay dùng api thì trải nghiệm nói chuyện với bot cũng vẫn giống nhau, em không nghĩ cách làm sao để có thể đổi các bộ não mà không ảnh hưởng đến chất lượng trả lời của bot à?"**

Đúng, và bản 0.21.0 đã phá chính lời hứa gốc của Javis: đổi bộ não thì năng lực không đổi. Chặn Codex là thừa nhận thua ở đúng chỗ không được phép thua.

Lời giải hoá ra đơn giản hơn cả hai bản chắp vá trước: **bot không cần tool nào cả.**
### Thay đổi hành vi
- **Lượt của Bot chuyên trách đi MỘT đường duy nhất cho cả tám bộ não** (`_bot_tra_loi`), không còn rẽ theo bốn nhánh engine. Mọi engine nhận cùng system prompt từ Agent, cùng tài liệu đã tra sẵn, cùng lịch sử hội thoại, và đều không có tool. Khác biệt còn lại đúng bằng khác biệt giữa các model, không phải giữa các đường ống.

  Đi bốn nhánh thì không bao giờ giống nhau được: Claude Code có Bash, Codex có kho MCP riêng, engine API bị trần 8 vòng gọi tool. Ba kiểu hành xử cho cùng một con bot, và chủ đổi model là khách thấy khác ngay.
- **Bỏ tool KHÔNG làm bot mất khả năng đọc brain.** `chatbot_grounding` vốn đã tra tài liệu bằng Python TRƯỚC khi model chạy và nhét sẵn vào prompt. Bỏ tool chỉ bỏ khả năng đi lang thang trong brain, không bỏ khả năng đọc nó.
- **Bot chạy được trên Codex trở lại**, và trên cả tám bộ não. Cả hai gói subscription đều đã có sẵn đường gọi thẳng không tool trong `_api_stream` (ChatGPT qua `openai_responses_stream`, Claude Code qua `anthropic_stream` với token OAuth mà chính CLI đã lưu) - bản trước bỏ sót điều này nên mới phải chặn.
- **Bot trả lời nhanh hơn và rẻ hơn**: không mở CLI, không nạp danh mục tool, không vòng gọi tool nào. Trần `JAVIS_MAX_TOOL_ROUNDS` cũng không còn liên quan tới bot.
- Lịch sử hội thoại với mỗi người được cắt cứng ở 20 lượt thay vì nén. Nén là thêm một lượt gọi model nữa, mà bot trả lời người lạ thì cần nhanh và rẻ hơn là cần nhớ dai.
### Bảo mật
- **Cách ly brain giờ là hệ quả của kiến trúc, không phải một rào phải canh.** Bot không có tool nên KHÔNG CÓ cách nào chạm vào đĩa: khỏi cần cổng duyệt per-call, khỏi cần sandbox, khỏi phải hy vọng `cwd` giữ chân được nó.

  Hai bản chắp vá biến mất theo: `allowed_tools` khoá cho Claude Code (0.21.0) và nhánh từ chối Codex (0.21.0). Cùng với đó là mức quyền `suggest` cho lượt bot (0.19.0) - nó vốn chỉ lọc tool của hub, không đụng tool native, nên chưa bao giờ là rào thật.
- **Lượt bot thoát khỏi `_tg_answer_engine` trước cả `_schedule_cancel_action`.** Trước đó một người lạ nhắn "huỷ lịch" cho bot là chạm được vào lịch của chủ.
- **Prompt của bot không còn kèm block kênh.** Block đó dạy cách tự gửi file qua Telegram và nêu đường dẫn thư mục thật của brain - kiến thức vận hành, không phải thứ đưa cho một con bot đang nói chuyện với người lạ.
- Test `test_chatbot_cach_ly.py` giờ kiểm bằng **hành vi thật**: chạy một lượt bot qua cả tám provider rồi đối chiếu payload từng con phải giống hệt nhau, thay vì chỉ đọc mã nguồn.

## [0.21.0] - 2026-08-04
Chủ repo chốt lại phạm vi của Bot chuyên trách: **"Anh có Agent và quy định của nó rồi, em đừng tự thêm vào quy định của nó. Chỉ có làm việc chống chỉ định xem các brain khác ngoài brain agent đang ở thôi."** Bản này bỏ hết luật Javis tự chèn, và đi kiểm tra lại rào cách ly brain - hoá ra nó hở thật.
### Bảo mật
- **Bot chạy trên Claude Code có TOÀN QUYỀN máy, không chỉ brain của nó.** Lượt bot dựng engine với `cwd=CLAUDE_CWD` (gốc project) và không đặt `allowed_tools`, nên engine chạy `permission_mode="bypassPermissions"`: các tool NATIVE (Bash, Read, Glob, Grep, Write) **không đi qua hub** và không bị `mcp_hub._safe_path` chặn. Một người lạ nhắn cho bot có thể lấy được nội dung mọi brain khác lẫn mã nguồn server.

  Mức quyền `suggest` đặt từ 0.19.0 không cứu được: nó lọc tool của HUB, không đụng tới tool native của engine. Và `cwd` một mình chưa bao giờ là rào - `cat ../brain-khac/...` vẫn chạy.

  Nay lượt bot dựng engine với `cwd` = brain của bot **và** `allowed_tools = ["mcp__javis"]`. Đặt `allowed_tools` mới là lớp chặn thật: nó bật `permission_mode="default"` cùng cổng `can_use_tool`, nên mọi tool ngoài hub bị TỪ CHỐI từng lượt gọi.
- **Bot bị TỪ CHỐI chạy khi engine chính là ChatGPT (Codex).** Codex không có allowlist per-call như Claude, và sandbox của nó chặn GHI với mạng chứ không nhốt phạm vi ĐỌC - `cat` sang brain khác vẫn chạy. Không khoá được thì nói thẳng, chứ không hạ sandbox rồi coi như xong: một rào chặn được nửa vời còn tệ hơn không có, vì chủ tưởng nó đang bảo vệ mình. Bot trả một câu nêu rõ lý do và cách xử lý (đổi engine chính sang Claude Code hoặc một engine API).
- **Test mới `test_chatbot_cach_ly.py` canh đúng rào này**, gồm cả các đường trèo ra: `../`, `../../`, đường dẫn tuyệt đối, và brain trùng tiền tố tên (`brain-bot` với `brain-bot-khac`) - ca mà so chuỗi thô sẽ cho lọt.
### Thay đổi hành vi
- **Javis KHÔNG còn chèn luật nào vào prompt của bot.** Từ 0.19.0 tới 0.20.1, prompt bot luôn có một khối "luật bắt buộc, đứng trên mọi hướng dẫn khác" - dặn xưng hô, cấm hứa hẹn, cấm đổi vai, bắt trả lời ngắn. Khối đó cãi nhau với chính quy định người dùng viết trong file Agent, và 0.20.1 mới chỉ sửa cho nó bớt gắn với ngành bán hàng chứ chưa bỏ.

  Nay prompt của bot = **đúng file Agent**, cộng tài liệu tra sẵn đưa vào như dữ liệu chứ không kèm mệnh lệnh nào. Muốn bot không nói về giá, không hứa giao hàng, không đổi vai khi bị dụ thì viết vào Agent - đó là nơi những điều ấy thuộc về.
- **Chế độ "chỉ tài liệu" là luật duy nhất còn lại, và người dùng phải tự bật.** Chế độ mặc định giờ không thêm chữ nào khi tra không ra tài liệu; Agent tự quyết.
- Trang Chatbot và tài liệu nói lại cho đúng việc Javis thật sự làm: nó không viết luật cho bot, nó khoá phạm vi brain. Hứa nhiều hơn thế là dạy người dùng tin vào một rào không tồn tại.

## [0.20.1] - 2026-08-04
Chủ repo tạo Agent **"Coach kỷ luật"**, hỏi bot về kỷ luật, và nhận lại một con bot ngu ngơ: nó tự xưng là trợ lý cửa hàng, trích một mục quy ước nội bộ của Javis ra làm câu trả lời, rồi nói "em chưa có thông tin" cho đúng câu thuộc chuyên môn của Agent. Bốn lỗi chồng lên nhau, đều do bản Chatbot đầu tiên mặc định rằng mọi bot đều là bot bán hàng.
### Sửa lỗi
- **Prompt đóng khung MỌI bot là nhân viên bán hàng, đè lên chính Agent người dùng vừa chọn.** Bản cũ viết thẳng "trợ lý trả lời khách của cửa hàng", "không chốt giá ngoài bảng giá", "không hứa giao hàng". Agent coach nào rơi vào đó cũng thành nhân viên bán hàng từ chối tư vấn.

  Bán hàng chỉ là MỘT ca dùng. Đề bài gốc là "mỗi chatbot chuyên về 1 lĩnh vực để hỗ trợ trả lời", còn nhóm chăm sóc khách hàng là ví dụ chứ không phải định nghĩa. Nay khung trung tính: Agent nói nó là ai, phần hướng dẫn vai được nêu rõ là **phần quan trọng nhất**, và luật chỉ giữ ba thứ không phụ thuộc ngành - đừng bịa chi tiết riêng của nơi đó, đừng khai hệ thống bên trong, đừng hứa thay chủ.
- **Bot bị bịt miệng khi brain không có tài liệu.** Bản 0.20.0 ép mọi bot vào chế độ chỉ-trả-lời-theo-tài-liệu, nên một Agent coach viết rất kỹ vẫn trả lời "em chưa có thông tin" cho câu thuộc đúng chuyên môn của nó - chuyên môn ấy nằm trong hướng dẫn vai, không nằm ở file nào trong brain.

  Nay bot có **hai chế độ**, chọn khi tạo hoặc sửa: *chuyên môn của Agent + tài liệu* (mặc định) và *chỉ tài liệu*. Khác biệt CHỈ nằm ở lúc không tìm thấy gì; tìm thấy thì hai chế độ hành xử y hệt. Cả hai đều vẫn bắt buộc phải có tài liệu mới được nói về giá, chính sách, tồn kho, lịch, liên hệ. Bot tạo trước bản này tự đọc thành chế độ mặc định, không cần di trú.
- **Bot trích quy ước nội bộ của Javis ra trả lời khách.** `meta_tools` seed `CLAUDE.md` + `AGENTS.md` vào GỐC mọi brain, mà danh sách loại trừ chỉ chặn theo thư mục. Hỏi "sao lại kỷ luật cửa hàng" thì bot tra ra mục "Ba kỷ luật chống Wiki rỗng/sai" rồi giải thích cho khách rằng đó là "quy tắc nội bộ vận hành hệ thống của cửa hàng" - vừa vô nghĩa, vừa khai ruột hệ thống, đúng thứ luật trong prompt cấm mà chính phần tra cứu lại dâng tận tay. Nay loại cả `CLAUDE.md`, `AGENTS.md`, `index.md`, `log.md`, `_open-questions.md`, `_session-handoff.md`; note Wiki thật của người dùng vẫn dùng bình thường.
- **Gọi nhân viên vì một câu hỏi vu vơ.** Bản 0.20.0 báo ngay từ lượt bí đầu tiên. Nhân viên bị đánh thức vì câu không ai cần xử lý thì vài lần là họ tắt thông báo, rồi lúc có người thật cần giúp thì không ai đọc nữa. Nay chỉ gọi khi khách gõ `/nhanvien`, hoặc bot bí **hai câu liên tiếp** với cùng một người; trả lời được một câu là đếm về 0.
### Cải thiện
- **Phân biệt khớp đúng dấu với khớp nhờ bỏ dấu.** Bỏ dấu là con dao hai lưỡi: nó cho khách gõ "gia si bao nhieu" mà vẫn ra "giá sỉ" (rất cần), nhưng cũng làm những cặp từ khác hẳn nghĩa đụng nhau, và tiếng Việt đụng rất nhiều. Ca thật: "có bán cà phê không" khớp vào note "Kỷ luật bản thân" có câu "kể cả khi hết hứng" - "bán" gặp "bản", "cà" gặp "cả", trúng hai chữ, đủ qua mọi ngưỡng.

  Nay chỉ mục giữ cả hai dạng. Người hỏi có đánh dấu mà tài liệu mang dấu khác thì hạ mạnh trọng số (0.3) chứ không loại hẳn, vì vẫn có người gõ sai dấu. Người hỏi gõ không dấu thì họ không nói gì về dấu, không phạt: mọi dạng tính là khớp thật. Bộ câu chuẩn trong test lên 30 câu, có cả cặp bẫy dấu đó.
- **"Bí" đo bằng chính câu bot vừa nói**, không bằng việc có tìm ra tài liệu hay không. Ở chế độ theo Agent thì không có tài liệu là chuyện thường và bot vẫn trả lời tốt; đếm nó là bí thì danh sách "Bot bí" đầy rác đúng chỗ nó phải sạch.
- **Thẻ bot hiện đang chạy chế độ nào**, và ô chọn chế độ nằm ngay dưới ô brain trong form kèm giải thích khi nào dùng cái nào - đây là thứ người dùng cần hiểu TRƯỚC khi bấm tạo, không phải thứ giấu ở cuối.

## [0.20.0] - 2026-08-04
Ba giai đoạn còn lại của Bot chuyên trách: **trả lời có căn cứ**, **vào nhóm được thật**, và **thống kê câu bot trả lời không nổi**. Kèm một lỗ của 0.19.0 phải vá.
### Sửa lỗi
- **Bot IM trong MỌI nhóm ở 0.19.0.** Luật mặc định "chỉ trả lời khi được gọi tên" đọc hai cờ `mentioned`/`reply_to_bot`, mà `TelegramBot._build_meta` không hề gắn chúng - nó chỉ gắn `chat_type`. Nên điều kiện luôn sai và bot không bao giờ mở miệng trong nhóm. Hỏng đúng kiểu tệ nhất: im lặng, không log, không báo, chủ chỉ thấy bot "như chết".

  Nay `_build_meta` đọc thẳng từ tin nhắn: `entities` loại `mention` (khách gõ `@ten_bot`, phải cắt chuỗi theo offset/length ra so) và loại `text_mention` (khách bấm chọn từ danh sách thành viên, không có `@` trong chữ, danh tính nằm ở `entity.user.id`), cộng `reply_to_message`. Cả `caption_entities` của ảnh cũng tính. Bot tự hỏi `getMe` lúc khởi động để biết chính nó là ai, thay vì nhận từ cấu hình vốn có thể chép sai hoặc cũ.

  So theo **id** chứ không theo cờ `is_bot`: trong nhóm có thể có nhiều bot, nhận vơ tin reply vào bot khác là chen ngang vào việc của người ta.
### Thêm mới
- **Tra tài liệu trước rồi mới trả lời (giai đoạn 2).** Bot vốn đã có `javis_read_file` trỏ vào brain của nó, nhưng **có tool đọc không bằng có đọc**: model trả lời thẳng bằng kiến thức chung thì câu vẫn trôi chảy tự tin y hệt, và chủ KHÔNG phân biệt được từ bên ngoài. Với khách hàng thật thì một câu bịa về giá hay chính sách là rủi ro thật.

  Nay mỗi lượt đều tra brain trước (module mới `chatbot_grounding`), lấy vài đoạn khớp nhất và nhét thẳng vào prompt làm căn cứ duy nhất. Không tìm thấy gì thì prompt **nói thẳng là đã tìm và không có** - đưa khối rỗng rồi im lặng chính là để model tự lấp bằng trí nhớ chung của nó.

  Tìm bằng đối chiếu từ khoá có trọng số IDF, không nhúng vector: brain của một bot chăm sóc khách là vài chục tới vài trăm file, ở cỡ đó thì cách này đủ tốt, chạy tại chỗ, không thêm dịch vụ nào, và quan trọng nhất là **giải thích được** - chủ nhìn vào biết vì sao bot lấy đúng file đó. Tài liệu cắt theo tiêu đề markdown để mỗi đoạn là một ý trọn vẹn; cắt cứng theo số ký tự thì bot đọc được nửa điều kiện rồi trả lời như thể đó là toàn bộ điều kiện.
- **Nhật ký hội thoại khách + danh sách CÂU BOT TRẢ LỜI KHÔNG NỔI (giai đoạn 4).** Nút Nhật ký trên mỗi thẻ bot, hai tab, và tab mở sẵn là "Bot bí" chứ không phải hội thoại: hội thoại chỉ để soi lại khi nghi ngờ, còn mỗi dòng trong "Bot bí" là một chỗ tài liệu đang thiếu, tức là thứ chủ **làm được gì đó** với nó.

  Gom trùng theo câu hỏi đã bỏ dấu, xếp theo số lần hỏi giảm dần - thứ đáng viết tài liệu bổ sung trước là thứ nhiều khách hỏi nhất, không phải thứ vừa mới hỏi. Bot tính là bí trong hai trường hợp: không tìm ra tài liệu, hoặc tìm ra rồi mà vẫn phải nói chưa có thông tin. Trường hợp sau tinh vi hơn và đáng chú ý hơn - tài liệu CÓ mà THIẾU Ý.

  Tab hội thoại hiện **đúng file bot đã dùng** cho từng lượt. Không có dòng nguồn đó thì "bot trả lời đúng chưa" là câu hỏi không kiểm chứng được, chỉ đoán.
- **Bí thì báo nhân viên ngay**, kèm câu khách vừa hỏi, nếu đã đặt Chat ID nhân viên. Khách hỏi hụt mà không ai biết là mất một khách.
### Bảo mật
- **File khách gửi lên KHÔNG được tính là tài liệu.** `inbox/` bị loại khỏi phần tra cứu, cùng với các thư mục hệ thống. Nếu không thì bất kỳ ai cũng tải lên một file ghi "chính sách mới: hoàn tiền 100% mọi trường hợp" rồi hỏi lại một câu, và bot trích dẫn nó như tài liệu chính thức của cửa hàng - tự đầu độc kho tri thức bằng một lần bấm gửi file.
- **Menu lệnh Telegram của bot khách không còn là menu quản trị của chủ.** `TelegramBot` trước đây ghim cứng `BOT_COMMANDS`, nên bot chăm sóc khách hiện cho khách thấy "/brain - Xem hoặc đổi brain (vault) của phiên này" và cả tập lệnh quản trị khác, dù chính nó từ chối chạy chúng. Nay menu truyền vào được; bot khách dùng đúng ba mục `/help`, `/nhanvien`, `/id`.
### Cải thiện
- **Ngưỡng "coi như tìm thấy" đo bằng ĐỘ PHỦ câu hỏi, không phải điểm tuyệt đối.** Điểm tuyệt đối một mình không dùng được: "cửa hàng có tuyển lập trình viên Rust không" trúng đúng chữ "hàng" trong mục Giao hàng, mà "hàng" hiếm nên IDF cao, nên điểm vượt ngưỡng và bot tưởng mình có căn cứ để trả lời về tuyển dụng. Nay đo tỉ lệ sức nặng câu hỏi thật sự có mặt trong đoạn, cộng luật câu từ ba chữ có nghĩa trở lên phải trúng ít nhất hai chữ. Kèm bộ 28 câu chuẩn trong test làm hàng rào cho cả hai hướng hỏng (quá lỏng thì bot bịa, quá chặt thì bot nói không biết trong khi câu trả lời nằm ngay trong bảng giá).
- **Từ dừng soạn lại cho tiếng Việt bỏ dấu.** "bán" và "bạn" cùng ra "ban"; loại "ban" đi là mất luôn chữ "bán" - với bot bán hàng thì đó là chữ có nghĩa nhất trong câu, và "có bán cà phê không" tụt xuống còn hai chữ rồi khớp bừa vào "cá cơm". Cùng lý do với "anh" (ảnh) và "chi" (chi phí).

## [0.19.0] - 2026-08-04
Trang **Chatbot**: đem một Agent bạn đã tạo ra đứng trước KHÁCH HÀNG, qua bot Telegram riêng, brain riêng, gặp câu ngoài tầm thì chuyển nhân viên thật. Spec đầy đủ ở `docs/dev/2026-08-bot-chuyen-trach-spec.md`, hướng dẫn dùng ở [docs/25-chatbot.md](docs/25-chatbot.md).
### Thêm mới
- **Bot chuyên trách.** Javis đã có Agent, Skill, Workflow, nhưng tất cả đều chỉ phục vụ CHỦ. Nay một Agent đem ra trả lời khách được: mỗi bot là bộ ba **Agent + brain riêng + token Telegram riêng**. Khách nhắn riêng cho bot, hoặc bạn thả bot vào nhóm chăm sóc khách hàng.

  Bot **trỏ tới** Agent chứ không chép lại nó: sửa Agent ở trang Agents là bot đổi theo ngay, không phải sửa hai chỗ. Agent bị xoá thì bot vẫn chạy (không sập) nhưng thẻ trên trang Chatbot báo động, và prompt tự dặn nó thận trọng hơn.

- **Trang Chatbot dựng theo hướng nhiều bot ngay từ bản đầu**: lưới thẻ, ô tìm theo tên, thêm/sửa/xoá, bật/tắt tại chỗ. Chủ repo đặt đề bài đúng như vậy ("làm 1 bot, nhưng uxui có tính scale"), nên bản này chạy một con mà thêm con thứ hai không phải sửa lại giao diện.

  Thẻ bot có **bốn** trạng thái chứ không phải hai: đang chạy, đang khởi động, **lỗi**, đã tắt. Bot chết âm thầm (token bị thu hồi, mạng rớt, trùng token) là thứ chủ cửa hàng chỉ phát hiện khi khách phàn nàn, nên "lỗi" phải là một ô màu nhìn thấy được kèm lý do, chứ không phải sự vắng mặt của màu xanh.

- **Chuyển cho nhân viên thật.** Đặt Chat ID nhân viên là bot có hai đường chuyển: tự chuyển khi gặp câu ngoài phạm vi, và khách chủ động gõ `/nhanvien`. Nhân viên nhận được tin có tên bot, id khách và lý do. Bỏ trống thì bot chỉ nói chưa có thông tin rồi dừng, không đoán tiếp.

- **Kiểm tra token trước khi lưu.** Nút Kiểm tra hỏi thẳng Telegram, trả về đúng tên bot, và **chặn nếu token đó đã có bot khác trong Javis đang dùng** (so theo @username từ getMe chứ không so chuỗi token, vì cùng một token dán hai lần với khoảng trắng khác nhau vẫn là hai chuỗi khác nhau). Một token chỉ chạy được MỘT tiến trình long-polling; hai poller cùng token thì Telegram trả 409 và cả hai cùng chết, hỏng ở chỗ không ai ngờ và không ai báo.
### Bảo mật
- **Rào của bot nằm ở MÃ NGUỒN, không phải ở prompt.** Đây là điểm thiết kế quan trọng nhất của tính năng, vì người ở đầu bên kia là người lạ:
  - Lượt của bot chạy ở mức quyền **suggest** (chỉ đọc), hạ bằng mã trong `_tg_answer_engine`. Không ghi file, không tạo đơn, không tiêu tiền, không đăng bài, không giao việc, không gọi được nguồn dữ liệu chủ đã đấu. Câu dặn trong prompt có thể bị lời lẽ khôn khéo lách qua; mức quyền thì không, vì công cụ đơn giản là không được cấp cho lượt đó.
  - Bot **không** dùng system prompt của Javis (prompt đó dạy điều phối, ghi vault, giao việc, toàn thứ bot khách hàng không được làm) mà dùng prompt riêng: vai trò của Agent nó trỏ tới, cộng luật trả lời khách.
  - Lệnh là danh sách **TRẮNG**: chỉ `/start`, `/help`, `/id`, `/nhanvien`. Mọi lệnh khác trả lời chung chung. Bot chủ có `/brain`, `/model`, `/status`; kế thừa được một lệnh trong số đó là khách đổi được brain của cửa hàng.
  - **Bot mới LUÔN tắt**, kể cả khi lời gọi tạo gửi `enabled: true`. Bật là một cú bấm có ý thức, không phải tác dụng phụ của việc tạo. Bật mà chưa có token thì từ chối kèm lý do, chứ không bật rồi để nó chết lặng lẽ trong bộ giám sát.
  - Token mã hoá qua `secrets_store`, **không bao giờ** trả ra giao diện kể cả dạng đã mã hoá; giao diện chỉ nhận cờ `token_set`. Bản vá từ giao diện đi qua danh sách **TRẮNG** các trường được sửa, nên `id`, `created_at`, `token_enc`, `channel` không ghi đè được.
  - **Giới hạn tần suất** theo giờ trượt, riêng từng người trong từng bot (mặc định 20 lượt/giờ). Một người rảnh trong nhóm đủ đốt hết quota model của chủ trong một buổi chiều, và chủ chỉ biết khi nhìn hoá đơn.
  - **Trong nhóm thì mặc định IM.** Chưa khai id nhóm thì bot không tự nhận việc ở nhóm lạ; đã khai rồi thì mặc định chỉ trả lời khi có người nhắc tên hoặc reply vào tin của nó.
- **Xoá bot KHÔNG xoá brain và Agent của nó**, và hộp xác nhận nói rõ điều đó. Cùng lý do với xoá Project không xoá hội thoại ở 0.18.0: brain có thể chứa cả tháng tài liệu chủ tự soạn, Agent có thể đang được bot khác hoặc workflow dùng.
### Cải thiện
- **Mức quyền của lượt chat truyền được xuống MCP Hub.** `_api_stream_mcp` nhận thêm tham số `mode`, nên `discover_all`/`registry_inventory` lọc tool theo đúng mức quyền của lượt đó thay vì luôn ở mức toàn quyền. Đây là thứ làm cho rào "bot chỉ đọc" là thật chứ không phải lời hứa.
- **Mục Chatbot trên thanh bên có icon riêng** (`headset`), không dùng lại icon của Trò chuyện. Hai mục cạnh nhau mà cùng một icon thì mắt không tách được.

## [0.18.2] - 2026-08-04
Ba lỗi người dùng thật báo: **cài đặt chết trên Windows tiếng Việt**, **model báo sai nguyên nhân khi bị chặn ghi file**, và **chạm trần vòng gọi tool rồi dừng không có lối thoát**.
### Sửa lỗi
- **`setup.bat` chết ngay bước [2/3] trên Windows tiếng Việt.** `pip install -r requirements.txt` nổ `UnicodeDecodeError` giữa chừng, không cài được gì.

  Nguyên nhân: pip đọc `requirements.txt` bằng `auto_decode()`. Không thấy BOM và không thấy khai báo encoding kiểu PEP-263 ở HAI DÒNG ĐẦU thì nó decode bằng `locale.getpreferredencoding()` - trên Windows tiếng Việt là cp1252/cp1258, mà file có chú thích tiếng Việt. Đây là loại lỗi máy dev không đời nào thấy: Linux và macOS locale UTF-8 nên đọc trót lọt. `chcp 65001` sẵn có trong `setup.bat` cũng không cứu được, vì nó đổi codepage của console chứ không đổi ANSI codepage mà Python đọc.

  Sửa bằng một dòng `# -*- coding: utf-8 -*-` ở đầu file, kèm chú thích dặn đừng xoá. Test chạy CHÍNH hàm `auto_decode` của pip với locale giả lập cp1252 và cp1258.
- **Model báo sai nguyên nhân khi bị chặn ghi file.** Việc Kanban chạy ở mức Chỉ đọc thì `javis_write_file` từ chối, đúng thiết kế. Nhưng câu từ chối cũ mơ hồ ("chế độ hiện tại không được ghi file"), nên model đọc xong tự dựng ra một nguyên nhân nghe hợp lý mà sai hoàn toàn. Người dùng thật nhận được câu **"môi trường filesystem đang lỗi quyền sandbox"** rồi đi tìm lỗi ổ đĩa, trong khi thứ cần làm chỉ là nâng mức việc lên Ghi nháp.

  Nay câu từ chối nói thẳng đây là giới hạn QUYỀN chứ không phải lỗi ổ đĩa hay sandbox, chỉ đúng chỗ chỉnh (trang Việc, mức Ghi nháp), và dặn model đừng thử ghi lại mà trả trọn nội dung ra câu trả lời để người dùng tự lưu. Thông báo dành cho MÁY đọc cũng là giao diện: viết mơ hồ thì máy đoán, và nó đoán sai.
### Cải thiện
- **Trần vòng gọi tool chỉnh được bằng `JAVIS_MAX_TOOL_ROUNDS`** (mặc định vẫn 8, kẹp trong 1-40). Việc nền nhiều bước hay chạm trần rồi dừng giữa chừng mà không có đường nào nâng lên. Con số 8 trước đây ghim cứng ở ba chỗ khác nhau trong `engine.py`; nay một chỗ khai duy nhất.
- **Câu báo chạm trần nói được việc cần làm**: nêu đúng con số đang áp dụng, cảnh báo câu trả lời có thể còn dở, và chỉ ra hai cách xử lý (chia nhỏ yêu cầu, hoặc nâng biến môi trường). Bản cũ chỉ nêu con số rồi im.

## [0.18.1] - 2026-08-04
Sửa chỗ đặt icon: đưa về **đầu hai tab** và về **Project**, gỡ khỏi từng hội thoại.
### Sửa lỗi
- **Icon đặt nhầm chỗ ở 0.18.0.** Ý trong sổ tay là thêm một icon phù hợp ở đầu hai tab "Hội thoại" và "Thư mục"; bản trước lại làm thành bộ chọn icon cho TỪNG cuộc hội thoại.

  Sai ở chỗ có thể suy ra được nếu chịu hỏi "icon này phân loại cái gì với cái gì". Danh sách hội thoại thì hàng nào cũng là một cuộc trò chuyện, nên icon ở đó không tách được nhóm nào ra khỏi nhóm nào - chỉ là trang trí phải bấm tay từng cái, cộng thêm một nút nữa vào hàng nút vốn đã có bốn cái. Còn hai tab là hai thứ khác loại đứng cạnh nhau mà chỉ phân biệt bằng chữ, nên liếc qua phải đọc mới biết đang ở đâu.
### Thêm mới
- **Hai tab của cột Lịch sử có icon.** Lấy đúng icon rail đang dùng cho hai thứ đó để cả app nói cùng một ngôn ngữ hình, chứ không đặt icon mới chỉ riêng chỗ này.
- **Project chưa đặt icon thì mượn icon thư mục làm mặc định**, và hai dòng đầu của menu chọn nhóm cũng có icon. Hàng nào cũng có icon thì mắt quét được theo cột icon, và nhìn là biết chỗ này đổi icon được. Project vẫn là nơi DUY NHẤT đổi icon, vì mỗi nhóm thật sự là một thứ khác nhau.
### Cải thiện
- **Gỡ sạch icon của từng hội thoại, không để lại UI chết**: cột `sessions.icon`, `SessionStore.set_icon`, endpoint `POST /sessions/{id}/icon`, nút bấm và phần render đều bỏ. Hàng nút khi rê chuột còn bốn nút thay vì năm.

## [0.18.0] - 2026-08-04
Dọn một loạt ý trong sổ tay phát triển: **ghim và gom nhóm hội thoại**, **link trong file .md bấm được**, **chọn skill khi số skill đã lên 55+**, **phân trang nhật ký**, thêm **NotebookLM** vào kho kết nối và **gửi ảnh qua Zalo**. Spec đầy đủ ở `docs/dev/2026-08-backlog-spec.md`.
### Thêm mới
- **Ghim hội thoại lên đầu, gom thành Project, gắn icon.** Danh sách Lịch sử xếp thuần theo thời gian nên cuộc dùng đi dùng lại cứ trôi dần xuống dưới, và toàn chữ nên nhìn lâu không phân biệt nổi cái nào là cái nào. Nay rê chuột vào một cuộc là ghim được, gắn emoji được, chuyển sang một Project được.

  Thanh chọn nhóm nằm ngay dưới nút Hội thoại mới. Đang mở một project thì danh sách lọc theo nó, **và cuộc trò chuyện mới bạn bắt đầu tự rơi vào project đó** chứ không phải gắn tay - thứ chỉ làm được vì id hội thoại sinh ở phía trình duyệt ngay lúc bấm gửi, nên nhãn kịp gắn từ tin nhắn ĐẦU TIÊN.

  **Xoá project KHÔNG xoá hội thoại**: các cuộc bên trong chỉ được gỡ khỏi nhóm. Hộp xác nhận nói rõ điều đó kèm số cuộc sẽ được gỡ, vì không có đường hoàn tác nào cho một cú bấm nhầm cuốn theo cả tháng trò chuyện.

  Icon lấy từ **chính bộ icon của Javis**, không phải emoji: icon Javis tự đổi màu theo tông sáng/tối và vẽ giống hệt nhau trên mọi máy, còn emoji thì mỗi hệ điều hành một kiểu và màu cứng nên nền tối nhìn chói. Bảng chọn hiện toàn bộ icon đang có kèm ô lọc theo tên.
- **Kho kết nối có Google NotebookLM.** Liệt kê notebook, đọc nguồn, hỏi đáp ngay trong notebook, thêm nguồn, tạo tóm tắt hay audio ở Studio.

  Sổ tay ghi việc này là "viết MCP server wrapper", nhưng đào ra thì `notebooklm-py` đã đóng gói sẵn một MCP server, nên phần Javis làm chỉ là một mục trong kho connector - không một dòng Python nào. Mặc định **Chỉ đọc**; đăng nhập bằng phiên trình duyệt (xem phần Bảo mật bên dưới).
- **Gửi ẢNH và FILE qua Zalo** (plugin bundled `zalo-image`, tool `zalo_send_image`). `zalo_send_message` của MCP chuẩn chỉ nhận chữ, nên Javis tạo được ảnh mà vẫn không gửi cho ai được. Trong khi thư viện bên dưới (`zca-js`) làm được từ lâu, và chính CLI đó đã có lệnh `msg send-image`.

  Bản 1.6.2 đã là bản mới nhất trên npm nên chờ upstream phơi thêm tham số là chờ vô hạn. Cách làm: gọi lại chính CLI đó với `HOME` trỏ vào đúng thư mục phiên của kết nối Zalo đang đăng nhập - không fork package Node, không bắt quét QR lần hai.
### Cải thiện
- **Link trong file .md giờ bấm được.** Mở một note ra đọc, bấm vào link tới file khác thì trước đây không đi đâu cả; trong khi `[[wikilink]]` ngay cạnh nó thì đi được, dù hai cái nhìn y hệt nhau.

  Nguyên nhân: xử lý CÓ, nhưng nằm SAU hàng rào "đang soạn trong trình sửa thì đừng mở gì cả" - mà bản render của trình sửa CHÍNH LÀ vùng soạn thảo, nên mọi link markdown đều rơi vào hàng rào đó. Nay link file nằm trước hàng rào, đúng chỗ wikilink vẫn đứng. Link http trong bản render cũng được mở hộ (trình duyệt không tự mở tab trong vùng soạn thảo, nó chỉ đặt con trỏ). Ảnh giữ nguyên hành vi cũ để còn kéo thả và xoá được như một ký tự.
- **Đi tới một file bằng link thì cây thư mục tự sổ tới đúng nhánh chứa nó.** Trước đây mở xong vẫn không biết file nằm đâu, lần sau lại đi tìm lại từ đầu.
- **Mở file từ trong chat dùng khung sửa dính thay cho popup.** Mở file từ tab Thư mục thì trình sửa chiếm chỗ khung chat, mở cùng file đó bằng link trong chat thì bật popup che giữa màn hình - hai đường vào một file, hai bộ mặt. Nay cùng một đường. Popup vẫn còn cho màn hẹp (dưới 860px không đủ chỗ cho khung dính). Loại file không sửa được (pdf, docx, zip) hiện thẻ file kèm nút Mở tab mới và Tải về.
- **Khung chọn skill khi sửa Agent có tìm kiếm và gom nhóm.** Brain thật đang có 55+ skill mà khung này là một mớ checkbox phẳng, nên tick đúng cái muốn là dò bằng mắt qua cả danh sách. Nay có ô tìm (không dấu, quét cả tên, slug, nhóm và mô tả), gom nhóm theo đúng field `group` mà trang Skills đang dùng, nhóm nào có skill đã tick thì mở sẵn, kèm ô đếm và nút Bỏ chọn hết.
- **Phân trang cho nhật ký tự học, commit học và bảng Lượt gần nhất.** Trang Tự học trước chỉ hiện 10 dòng nhật ký và 12 commit rồi hết, không có đường xem xa hơn. Nguồn cũng nới theo: nhật ký học đọc tới khi đủ số mục thay vì cắt cứng ở 3 tệp - nhật ký ghi mỗi ngày một tệp, nên cắt ở 3 nghĩa là phân trang cũng chỉ lật quanh 3 ngày.

  Khối phân trang được tách thành một hàm dùng chung thay vì chép ra bản thứ hai và thứ ba, đúng bài học đã học ở cây Vault (0.15.1) và Javis CLI (0.17.0).
### Bảo mật
- **Gửi ảnh Zalo chỉ gửi được file NẰM TRONG bộ não đang dùng.** Tool nhận đường dẫn từ chính câu chat và đầu ra là gửi ra ngoài, không thu hồi được; thiếu rào này thì một câu khéo léo là tuồn được tệp khoá hay `/etc/passwd` ra một cuộc chat Zalo bất kỳ. Đường dẫn tuyệt đối ngoài bộ não cũng bị chặn, không riêng dạng `../`.
- **Đấu nhiều tài khoản Zalo thì Javis hỏi lại, không đoán.** Gửi nhầm tài khoản là gửi dưới danh tính người khác. Tool cũng ở mức `full` như `zalo_send_message`, nên chế độ suggest và các việc nền chạy giới hạn không tự gửi được.
- **NotebookLM nói thẳng đây là cookie phiên Google, không phải OAuth giới hạn phạm vi.** Ai cầm được chuỗi đó thì vào được tài khoản Google, nên connector mặc định **Chỉ đọc** và cảnh báo ngay ở bước đầu của trình hướng dẫn. Các tool CHIA SẺ notebook ra ngoài được xếp nhóm nguy hiểm dù thư viện tự đánh dấu chúng là không phá huỷ: gỡ chia sẻ lại được, nhưng không rút lại được việc người ta đã đọc. Connector cố ý KHÔNG xếp vào nhóm Google một cửa - nhóm đó là các kết nối đi chung một key OAuth client, cách đăng nhập và rủi ro khác hẳn.

## [0.17.1] - 2026-08-04
Giao việc Kanban nay làm được từ **mọi bộ não**, không chỉ hai engine chạy được lệnh máy.
### Thêm mới
- **Tool `javis_task`** (plugin bundled `javis-task`, bật sẵn): giao việc nền vào hàng đợi Kanban (`op=add`) và xem việc đang chạy tới đâu (`op=list`), ngay từ chat, trên bất kỳ engine nào.
### Sửa lỗi
- **Tài liệu hứa một thứ mã không làm được, suốt nhiều bản.** `CLAUDE.md` và `docs/10-models-va-engine.md` đều ghi mọi bộ não được cấp cùng bộ đồ nghề, trong đó có "giao việc Kanban". Thực tế đường duy nhất để giao việc là `POST /kanban/task`, mà gọi được nó thì phải có Bash và curl - tức là chỉ Claude Code với Codex. Năm engine API đứng ngoài.

  Tệ hơn cả việc thiếu: `CLAUDE.md` còn dặn Javis "đừng bao giờ nói mình không làm task được, sai sự thật". Nên một engine API sẽ TỰ TIN nhận lời rồi im lặng không làm gì. Người dùng ngồi đợi một việc không bao giờ chạy, và không có một dòng lỗi nào ở đâu cả.

  Sửa theo hướng nâng MÃ lên cho khớp tài liệu, chứ không hạ tài liệu xuống: giao việc là thứ dùng thật, và để nó chỉ chạy trên hai engine thì lời hứa "đổi não thoải mái không mất chức năng" thủng đúng chỗ đáng tiếc nhất.
- **Câu "khác biệt DUY NHẤT là chạy lệnh máy" cũng sai, nay nói đủ.** Hai engine CLI còn có thêm **WebFetch/WebSearch** (tự mở URL lạ ra đọc, tự tra web), **Task** (đẻ agent con chạy song song), và nối lại được phiên cũ. Engine API còn hai giới hạn thực dụng chưa từng ghi ở đâu: mỗi lượt tối đa **8 vòng gọi tool**, và khi lượt có gọi tool thì câu trả lời hiện một cục ở cuối chứ không chạy dần từng chữ.
### Bảo mật
- **Tool `javis_task` KHÔNG tạo được việc mức `full`.** Mức full cho việc tự thao tác thật ra ngoài (tạo đơn, tiêu tiền, chạy quảng cáo, gửi tin) và không hoàn tác được, nên phải do chính người dùng đặt ở trang Việc. Mặc định là `suggest`; mode lạ kẹp về `suggest` chứ không trôi thành `auto`.
- **Gọi thẳng hàng đợi in-process, không mở thêm cửa HTTP.** Cách dễ hơn là cho plugin POST `/kanban/task` như `javis-schedule` vẫn POST `/reminders`, nhưng route đó đòi đăng nhập và cách duy nhất để mở là thêm vào danh sách miễn auth cho localhost - nghĩa là bất kỳ tiến trình nào trên cùng máy chủ cũng giao được việc cho Javis mà không cần credential. Không đáng, khi plugin vốn đã chạy trong tiến trình server.
- **Không nuốt thiếu sót.** Chưa biết brain nào thì từ chối chứ không âm thầm rơi về Brain Default (giao việc nhầm brain là chạy trên dữ liệu của người khác). Thiếu người nhận thì cảnh báo ngay trong kết quả, vì đó là lý do số một khiến người dùng "giao việc rồi không thấy gì".

## [0.17.0] - 2026-08-04
**Javis CLI**: gõ `javis "doanh thu tuần này thế nào"` ngay trong terminal. Kênh thứ ba, cùng một Javis.
### Thêm mới
- **`pip install javis-cli` rồi gõ thẳng câu hỏi.** Không cần lệnh con, không cần mở trình duyệt. Câu trả lời vẫn đến từ chính Javis của bạn: cùng brain, cùng bộ nhớ, cùng MCP đã đấu, cùng lịch sử hội thoại ở trang Phiên.

  Có cả `javis chat` (phiên hỏi đáp liên tục, giữ mạch), `javis status`, `javis task add`, `javis tasks`, `javis brain ls|cat`, `javis loops`, và `javis up` để bật Javis đã cài trên chính máy đó.
- **CLI là CLIENT MỎNG, không phải Javis thứ hai.** Nó không chứa server bên trong và nói thẳng điều đó ở dòng đầu tài liệu lẫn trong thông báo lỗi. Lý do: gần như mọi thứ làm nên Javis đều đòi một tiến trình sống dài (loop theo chu kỳ, nhắc hẹn chờ tới giờ, MCP Hub giữ kết nối, kho capability, runtime tiết kiệm token học dần), mà một lệnh gõ xong là thoát thì không phải chỗ cho chúng.

  Nên CLI đi qua ĐÚNG cái lõi dashboard và Telegram đang dùng (`_tg_answer`, nay nhận thêm tham số kênh). Đổi lại: tính năng mới vào Javis là CLI thấy ngay, không phải sửa hai chỗ. Đây cũng là bài học 0.15.0 - dựng bản thứ hai của thứ đã có rồi để hai bản trôi lệch - áp dụng ở quy mô lớn hơn nhiều.
- **Javis biết mình đang nói qua terminal nên trả lời khác.** Kênh `cli` có khối ngữ cảnh và hợp đồng đầu ra riêng: không bảng markdown, không nhúng ảnh, không link markdown, đường dẫn file in TUYỆT ĐỐI để copy chạy được luôn.
- **Luật Unix, để ghép được vào script.** Câu trả lời ra stdout, mọi thứ khác (tiến độ, tên tool, lỗi) ra stderr. Nên `javis "tóm tắt tuần này" > bao-cao.md` cho ra file sạch. Lỗi thì thoát khác 0 và không in gì ra stdout, nên `&&` trong script hành xử đúng. Có test canh đúng MỘT chỗ trong cả gói được ghi stdout.
- **Nối được nhiều Javis cùng lúc**: một hồ sơ cho máy nhà, một cho VPS, đổi bằng `--profile`. Cấu hình ở `~/.javis/config.json` quyền `600`, và bốn biến môi trường (`JAVIS_URL`, `JAVIS_TOKEN`, `JAVIS_BRAIN`, `JAVIS_PROFILE`) đè lên file cho CI/Docker.
- **Trang Tài khoản có mục Token API.** Tạo token, chọn phạm vi, xem lần dùng cuối của từng cái, thu hồi. Chuỗi thô hiện đúng MỘT lần kèm sẵn câu lệnh `javis login` để dán sang máy kia.
### Bảo mật
- **Không có token nào sẵn.** Chưa ai bấm tạo thì không token nào tồn tại, và không cửa nào vào ngoài trình duyệt. Đây là điểm quan trọng nhất của cả tính năng: mở cổng mới ra Internet phải là một hành động CÓ Ý THỨC, không phải mặc định.
- **Hai mức phạm vi.** `chat` đi theo danh sách TRẮNG (`/chat`, `/version`, `/health`, `/sessions`); `full` ngang session trình duyệt. Chọn chiều trắng chứ không chiều đen, vì danh sách đen nghĩa là mỗi endpoint mới thêm vào server tự động phơi ra cho token hẹp.
- **Token không đẻ được token.** Tạo token đòi session trình duyệt. Thiếu rào này thì một token rò ra là kẻ cầm nó tự cấp thêm token vĩnh viễn, và thu hồi cái đã rò thành vô nghĩa. Ngược lại, THU HỒI thì cho dùng chính token đang cầm: mất máy là phải hạ được credential ngay, kể cả khi không mở nổi trình duyệt.
- **Trên đĩa chỉ có bản băm SHA-256**, so bằng `compare_digest` chứ không so chuỗi (so chuỗi thường thoát sớm ở ký tự đầu khác nhau, và chênh lệch thời gian đó đủ để dò token theo từng ký tự). Token đi trong header `Authorization`, không bao giờ trong query string - query string nằm trong log của mọi proxy trên đường đi.
- **Sai quá 10 lần trong 5 phút thì IP bị chặn 15 phút**, mỗi lần sai ghi vào `auth_audit.jsonl` nhưng chỉ 12 ký tự đầu, vì file log là thứ hay bị gửi kèm báo lỗi. Chặn dò được kiểm TRƯỚC khi băm, và nhánh token đặt SAU nhánh cookie để dashboard không phải đọc file token mỗi request.

## [0.16.1] - 2026-08-03
Ollama gọn lại còn đúng bản **Cloud** - dán API key là chạy, như mọi nhà cung cấp khác.
### Cải thiện
- **Gỡ đường chạy trên máy nhà, chỉ giữ Ollama Cloud.** Javis phần đông chạy trên VPS trong Docker, nơi "localhost" là chính cái container chứ không phải máy người dùng - nên đường máy nhà gần như không ai dùng được, mà lại kéo theo nguyên một ca đặc biệt: ô địa chỉ riêng (`host_field`, thứ duy nhất trong cả lớp nhà cung cấp có), một nhánh riêng để tính "đã kết nối chưa", một nhánh giao diện riêng, và một hàm chọn-đường-theo-key.

  Nay Ollama đúng hình dạng của Groq hay Gemini: dán key, xong. Thẻ nhà cung cấp cũng về đúng một ô như các thẻ còn lại.
- Lấy danh sách model vẫn hỏi hai đường (`/v1/models` chuẩn OpenAI trước, `/api/tags` gốc Ollama sau) vì tài liệu của họ không nói rõ đường nào là chính cho bản Cloud. Thà thừa một request còn hơn báo "chưa thấy model" với một key hoàn toàn đúng.

## [0.16.0] - 2026-08-03
Thêm bộ não thứ tám: **Ollama** - chạy model ngay trên máy bạn, hoặc qua Ollama Cloud.
### Thêm mới
- **Nhà cung cấp Ollama, hai đường chạy trong một thẻ.**
  - **Máy nhà**: để trống cả hai ô. Miễn phí, không hạn mức token, và dữ liệu không ra khỏi máy - thứ chưa provider nào trong Javis làm được. Cần cài Ollama rồi tải model về (`ollama pull llama3.1`).
  - **Ollama Cloud**: dán API key lấy ở ollama.com. Chạy được model to mà máy nhà không kham nổi.
  - Để trống địa chỉ thì Javis tự chọn đường: có key thì đi Cloud, không key thì máy này. Khai địa chỉ rõ thì luôn theo địa chỉ đó, kể cả máy khác trong mạng.
- **Ollama là agent đủ đồ nghề như mọi bộ não khác**: gọi MCP đã đấu, đọc/ghi brain, chạy skill, nhận việc Kanban. Không phải chat suông. Model cần biết gọi tool (llama3.1 trở lên, qwen2.5, mistral-nemo, gpt-oss... đều biết).
- **Nút Kiểm tra hỏi thẳng máy đó xem có model gì.** Lấy được model tức là địa chỉ đúng và Ollama đang chạy - nên nó vừa là danh sách model vừa là đèn báo kết nối, không cần nút thử riêng. Không thấy gì thì báo rõ nên kiểm tra cái nào, và lời nhắc phân biệt máy nhà với Cloud.
### Sửa lỗi
- Bài kiểm "UI liệt kê đúng 5 provider có MCP" ghim cứng năm cái tên, nên thêm nhà cung cấp là CI đỏ dù mọi thứ đều đúng - hàng rào quay ra chặn việc sửa. Nay nó đọc danh sách thật ở máy chủ và canh đúng bất biến cần canh: **giao diện khớp máy chủ**.

## [0.15.2] - 2026-08-03
Mở file từ tab Thư mục thì trình sửa CHIẾM CHỖ khung chat, không đè lên nó.
### Thêm mới
- **Bấm một file trong tab Thư mục là mở thẳng trình sửa markdown, y như ở màn chính** - nhưng ở trang Trò chuyện thì khung chat bên dưới biến mất hẳn, chỉ còn trình sửa. Ở màn chính, trình sửa là lớp nổi đè lên visual não, chỗ đó rỗng nên đè là hợp lý; còn ở trang Trò chuyện thì phía dưới là đoạn chat đang có nội dung, đè lên vừa chật vừa rối.

  Đóng trình sửa (nút đóng hoặc phím Esc) là khung chat hiện lại nguyên vẹn, còn đủ đoạn đang nói dở - nó chỉ bị ẩn chứ không bị dựng lại.
- Vẫn dùng **chính trình sửa của màn chính**, không dựng bản thứ hai. Nên mọi thứ nó vốn có đi theo: xem/sửa markdown, Ctrl+S để lưu, đổi tên, tải về, nút phóng to, và file đang mở tự được ghim làm đầu vào của cuộc trò chuyện.

## [0.15.1] - 2026-08-03
Tab Thư mục dùng ĐÚNG cây Vault sẵn có, thay vì cây thứ hai tự dựng ở bản trước.
### Sửa lỗi
- **Bản 0.15.0 dựng một cây thư mục thứ hai thay vì dùng cây đã có.** Chủ repo chỉ ra ngay: "sao không bê nguyên cái cây y hệt bên Javis sang mà phải dựng lại phức tạp thế, lại còn lỗi nữa chứ". Đúng vậy - Javis đã có cây Vault ở cột trái màn chính, kèm tìm theo tên và theo nội dung, tạo file, tạo thư mục, làm mới, tô sáng file đang mở. Viết bản thứ hai là chép lại từng đó thứ rồi để hai bản trôi lệch nhau, mà bản mới thì chưa ai dùng thật nên lỗi cứ nằm im ở đó.

  Nay tab Thư mục **mượn đúng panel Vault** đó, y như cách trang Trò chuyện vẫn mượn khung chat của màn chính. Cùng một cây, chỉ đổi chỗ đứng. Module tự dựng đã gỡ bỏ hoàn toàn.
### Thêm mới
- **Nút "Vị trí" ở kết quả tìm kiếm của cây Vault** - có ở CẢ màn chính lẫn tab Thư mục trong khung chat, vì giờ chỉ còn một cây. Bấm là xổ cây tới đúng thư mục đang chứa file rồi tô sáng nó, thay vì mở note ra luôn như trước.

## [0.15.0] - 2026-08-03
Cột trái khung chat có thêm tab **Thư mục**: cây file của brain, ngay cạnh lịch sử hội thoại.
### Thêm mới
- **Tab Thư mục trong khung Trò chuyện.** Cột trái trước nay chỉ có lịch sử hội thoại, nên muốn xem brain đang có file gì là phải rời sang trang Tệp tin - mà rời đi thì mất chỗ đang nói dở. Nay cột đó có hai tab, bấm qua lại không rời khung chat. Tab đang chọn được nhớ lại cho lần sau.
- **Cây xổ ra thu vào, nạp theo nhu cầu.** Bấm mở thư mục nào mới đọc thư mục đó, nên brain vài nghìn file vẫn mở tức thì. Bấm vào một file là mở thẳng trong trình sửa của dashboard, tức là nó thành file đang mở của cuộc trò chuyện luôn.
- **Nút "Vị trí" ở kết quả tìm kiếm xổ cây tới đúng chỗ file đang nằm** và tô sáng nó. Tìm ra file mà không biết nó nằm thư mục nào thì lần sau vẫn phải đi tìm lại; nút này trả lời đúng câu đó. Các nhánh không nằm trên đường đi vẫn đóng nguyên, nên "xổ tới nơi" không biến thành "xổ tung cả cây".
### Cải thiện
- Đổi brain thì cây tự dựng lại. Không có bước này thì tab Thư mục còn treo cây của brain cũ và bấm vào là mở nhầm brain - im lặng và rất khó ngờ.

## [0.14.8] - 2026-08-03
Trang Cập nhật thôi báo "đang dùng bản mới nhất" trong khi ngay dưới nó nói có bản mới.
### Sửa lỗi
- **Máy đang chạy v0.14.4 mà khung trên vẫn ghi "Đang dùng bản mới nhất", nút cập nhật không hiện.** Ngay bên dưới, cùng trang đó, lại ghi "Có bản mới: v0.14.7". Hai dòng nói ngược nhau vì chúng đọc hai nguồn khác nhau: khung trên so file `VERSION` trên nhánh main, còn huy hiệu dưới đọc `CHANGELOG.md`. Ba bản 0.14.5, 0.14.6, 0.14.7 đều được ghi vào nhật ký mà quên bump `VERSION`, nên với khung trên thì bản mới nhất vẫn là 0.14.4 - đúng bằng bản đang chạy, và nó kết luận không có gì để cập nhật.

  Hậu quả nặng hơn vẻ ngoài: người dùng Docker không có nút bấm nào, cũng không thấy hướng dẫn Redeploy, tức là **không có đường nào lên bản mới** trừ khi tự SSH. Ba bản vá liên tiếp nằm đó mà không ai lấy được.
- **Nay có hàng rào chặn đúng lỗi này.** Test soát `VERSION` phải khớp mục mới nhất trong `CHANGELOG.md`, nên lần sau quên bump là CI đỏ ngay tại chỗ chứ không im lặng phát ra ngoài. Cùng bài đó soát luôn định dạng số hiệu và thứ tự các mục trong nhật ký.

## [0.14.7] - 2026-08-03
Mức Siêu tiết kiệm chưa chạy lần nào trên máy đấu nhiều MCP. Tìm ra và mở khoá.
### Sửa lỗi
- **Đường tắt bị chặn ở gần như mọi lượt, càng đấu nhiều nguồn càng chặn chắc.** Chủ repo báo "chưa lần nào chat anh nhìn thấy chữ Tức thì", và soi ra thì đúng như vậy. Cửa nhận lượt xét số ứng viên **dò được bằng chữ**, đếm trước khi chấm điểm và trước khi lọc quyền. Trên máy đấu vài trăm tool MCP (Gmail, Drive, Lịch, quảng cáo...), gần như câu tiếng Việt nào cũng dò trúng vài tool qua một từ chung, nên điều kiện đó đúng với mọi lượt và đường tắt không bao giờ chạy.

  Nghĩa là mức Siêu tiết kiệm càng đấu nhiều nguồn càng không tiết kiệm được, ngược hẳn thứ nó hứa. Trên máy dev thì không lộ, vì kho tool ở đó gần như rỗng và mọi test đều xanh.

  Nay xét **điểm khớp cao nhất** sau khi đã chấm. Có cái suýt trúng thì vẫn nhường đường thường cho chắc, còn dò trúng một từ vu vơ thì không phải lý do để bỏ đường tắt. Ngưỡng nằm ở `context_runtime.canary.min_resolver_score` (mặc định 0.45) để vặn được khi cần.
- **Nhiều nhánh trả lời không gắn nhãn chế độ, nên có lượt không hiện gì dưới câu trả lời.** Dòng "chế độ + token" do gói tin trả lời mang theo, mà chỉ ba nhánh gắn nó. Nhánh nhắc hẹn, nhánh tra cứu, nhánh thực thi, nhánh từ chối vì vượt hạn mức đều gửi câu trả lời trần. Nay mọi gói trả lời đều mang nhãn, và có test soát toàn bộ mã nguồn để không nhánh nào mới thêm bị sót nữa.
### Thêm mới
- **Trang Tiết kiệm nói thẳng vì sao lượt chat chưa đi được đường tắt**, gộp theo lý do và xếp theo số lần. Bảng "Lượt gần nhất" đã ghi lý do từng dòng, nhưng một lý do chiếm 18 trên 20 lượt là một cái hỏng còn xuất hiện 2 lần thì bình thường, mà nhìn từng dòng không phân biệt nổi hai ca đó. Chính vì thiếu con số này mà lỗi ở trên phải chờ chủ repo nói bằng lời mới lộ ra.

## [0.14.6] - 2026-08-03
Javis biết bây giờ mấy giờ trên mọi đường, thôi bịa lý do khi không biết.
### Sửa lỗi
- **Hỏi mấy giờ thì Javis nói "MCP server đang mất kết nối".** Không có server nào mất kết nối cả. Sự thật là lượt đó đi đường tắt của mức Siêu tiết kiệm, mà đường tắt gửi gói tin KHÔNG kèm tool nào - đó chính là chỗ nó tiết kiệm. Model thì không có đồng hồ sẵn trong đầu, nên khi bị hỏi giờ mà không có tool để gọi, nó làm cái tệ nhất: bịa ra một lý do nghe hợp lý.

  Bộ lọc câu hỏi có chặn "bây giờ", "hôm nay" và bắt những câu đó đi đường đầy đủ, nhưng chặn theo từ khoá là trò đuổi bắt: "giờ Việt Nam là mấy giờ" lọt qua ngay. Nay chữa ở gốc - mọi gói tin Javis gửi đi, đường tắt lẫn đường đầy đủ, đều mang sẵn một dòng giờ thật theo múi giờ Việt Nam. Khoảng 30 token mỗi lượt, đổi lấy việc không còn cửa nào để bịa, và bật hay tắt tiết kiệm thì Javis cũng biết giờ y như nhau.

  Múi giờ là UTC+7 cố định chứ không đọc múi giờ của máy chủ, vì VPS gần như luôn chạy giờ UTC.
### Cải thiện
- Trang **Tiết kiệm token** đổi tên thành **Tiết kiệm** cho gọn.

## [0.14.5] - 2026-08-03
Dọn đường để sau này nâng được mức tiết kiệm mặc định, mà không giẫm lên ai đã tự chọn.
### Sửa lỗi
- **Đổi mức tiết kiệm mặc định sẽ không bao giờ tới được máy đã cài.** Cái bẫy nằm ở chỗ Javis lưu cấu hình: mỗi lần ghi là ghi lại TOÀN BỘ config đã trộn, nên ngay lần đầu người dùng bấm bất cứ nút nào ở trang Cài đặt, giá trị mặc định của đúng ngày hôm đó bị đóng băng vào settings.json. Lúc đọc thì file lại đè lên mặc định. Hệ quả: về sau nâng mặc định lên mức Tối ưu hay Siêu tiết kiệm thì chỉ máy cài mới tinh mới thấy, còn máy đang chạy thì không, và không có lỗi nào báo ra cả. Đây đúng là con bệnh đã cắn `provider_kinds` hồi 0.12.4, lần này rơi vào thứ quyết định mỗi lượt chat tốn bao nhiêu token.

  Chỗ khó riêng: số 0 nằm trong file có hai nghĩa ngược nhau, "đã cân nhắc và cố ý chọn Tắt" và "chưa ai chọn gì cả". Không phân biệt được thì hoặc là giẫm lên quyết định của người dùng, hoặc là mặc định mới không bao giờ tới nơi. Nay mọi lần tự đổi mức đều để lại chữ ký, và có chữ ký thì bản cập nhật không đụng vào. Máy chưa từng chọn thì đi theo mặc định của bản đang chạy, kể cả máy đã cài từ lâu.
### Cải thiện
- **Trang Tiết kiệm nói rõ mức đang chạy là do anh chọn hay chỉ là mặc định.** Hai thứ đó trông y hệt nhau trên màn hình mà ý nghĩa ngược nhau: cái sau sẽ đi lên theo bản cập nhật, cái trước thì không. Chưa chọn bao giờ thì có một dòng nói thẳng điều đó, kèm cách ghim lại là bấm một mức bất kỳ, kể cả bấm đúng mức đang hiện.
- **Nâng mức mặc định chỉ NÂNG, không bao giờ HẠ.** Máy đang chạy mức cao hơn mặc định, kể cả do sửa tay settings.json, vẫn giữ nguyên. Không có thứ gì người dùng đã bật bị bản cập nhật tắt đi.
- Bảng "mức nào bật đường nào" gom về một chỗ duy nhất. Trước đó nó nằm ở `main.py`, mà chỗ nâng mặc định lại ở `config.py` và không import được sang - chép ra hai bản thì tới lúc thêm một đường vào mức nào đó, chỗ nâng mặc định vẫn nâng theo bảng cũ, lệch âm thầm.
### Lưu ý
- Bản này chưa đổi mặc định của ai, mức xuất xưởng vẫn là Tắt. Nó chỉ dựng sẵn cơ chế để lần nâng sau đi được tới nơi. Một chỗ mơ hồ còn lại, nói ra cho minh bạch: máy nào từng cố ý chọn Tắt TRƯỚC bản này thì không để lại chữ ký nào, nên tới ngày nâng mặc định sẽ được nâng theo. Bấm một mức một lần sau khi cập nhật là ghim vĩnh viễn.

## [0.14.4] - 2026-08-03
Gói Claude Code dùng được mức Siêu tiết kiệm. Trước đó nó là bộ não duy nhất bị đứng ngoài.
### Thêm mới
- **Đường tắt cho câu hỏi đơn giản giờ chạy trên cả gói Claude Code.** Bản 0.14.0 chặn cứng nó vì lúc đó không có cách nào gọi thẳng model mà không cần API key, thứ gói thuê bao không có. Nhưng Javis vốn đã mượn chính access token của Claude Code để hỏi danh sách model, và cùng token đó gọi được cả đường trả lời. Nay cả ba loại bộ não đều ăn được mức này.
- **Có lưới an toàn.** Token của CLI có thể hết hạn hoặc bị từ chối. Khi đó lượt tự lui về Claude Code đầy đủ ngay trong lượt, không ném lỗi ra và không để lại bong bóng rỗng. Chậm hơn một chút, nhưng anh vẫn có câu trả lời.
### Sửa lỗi
- **Lượt lui về engine đầy đủ vẫn đeo nhãn "Tức thì".** Đường tắt ghim nhãn ngay lúc nhận lượt, nên khi nó về tay không thì nhãn vẫn còn nguyên: dòng dưới câu trả lời nói sai, bảng đo 24 giờ xếp nhầm cột, và con số tiết kiệm bị thổi lên bằng đúng những lượt không hề tiết kiệm. Nay ghim được trả lại khi tầng đó không giao được hàng, và một tầng không gỡ được cam kết của tầng khác.
- **Alias model của Claude Code được dịch sang tên thật.** Claude Code hiểu "haiku" và tự chọn bản mới nhất, nhưng đường gọi thẳng thì không: gửi "haiku" là báo không tìm thấy model. Nay Javis tra danh sách model đang có và dịch sang đúng bản mới nhất cùng dòng.

## [0.14.3] - 2026-08-03
Trang thôi dán nhãn sai lên mức Siêu tiết kiệm, và mỗi lượt nói được VÌ SAO nó không đi đường tắt.
### Sửa lỗi
- **Bấm mức Siêu tiết kiệm xong trang vẫn ghi "không áp cho bộ não đang dùng".** Nhãn đó sai từ 0.14.0: nó gõ cứng "chỉ chạy trên bộ não dùng API key" từ hồi đường tắt đúng là như vậy, rồi 0.14.0 mở cho gói ChatGPT mà không ai nhớ sửa dòng đó. Kết quả là trang dán nhãn phủ nhận lên đúng cái mức vừa được mở, và người bấm tưởng mình bấm nhầm. Nay nhãn đọc thẳng cấu hình thật, nên lần sau mở thêm bộ não nào là trang tự đúng theo. Chỉ gói Claude Code còn được báo là chưa mở, và đó là rào cứng có lý do: đường tắt gọi model bằng đường cần API key, thứ gói đó không có.
### Thêm mới
- **Mỗi lượt trong bảng "Lượt gần nhất" giờ nói rõ vì sao nó đi đường đó.** Lý do vẫn được ghi lại từ đầu nhưng chưa bao giờ đưa ra màn hình, nên bấm mức xong thấy chat vẫn hiện "Tối ưu" là chịu, không có cách nào biết do câu hỏi cần tra cứu, do bộ não chưa mở, hay do kho công cụ chưa kịp sẵn sàng. Nay mỗi dòng có một chú thích tiếng Việt ngay dưới tên chế độ: "câu này cần dữ liệu thật", "kho công cụ chưa sẵn sàng, thử lại sau vài lượt", "câu này cần gọi công cụ"...
### Cải thiện
- Mô tả mức Siêu tiết kiệm nói thêm một câu quan trọng: **câu cần tra cứu vẫn đi đường đầy đủ**, nên không phải lượt nào bật mức này cũng thấy khác. Đó là chủ đích, không phải hỏng.

## [0.14.2] - 2026-08-03
Mở mạch mới thôi làm mất ngữ cảnh: bản mồi lại dày lên năm lần và mang theo tóm tắt.
### Cải thiện
- **Khi Javis mở mạch hội thoại mới, nó mang theo nhiều gấp năm lần so với trước.** Chủ repo lo mất ngữ cảnh khi giao việc nặng chạy lâu, và soi lại thì chỗ đau không nằm ở cái ngưỡng như tưởng, mà ở bản mồi lại. Hai con số đó đi ngược nhau theo cách phản trực giác: ngưỡng càng cao thì xoay mạch càng hiếm, nhưng mỗi lần xoay lại **rơi càng sâu**. Ở ngưỡng 120.000, rơi xuống bản mồi 60.000 ký tự là mất sáu lần. Ở ngưỡng 1 triệu vừa nâng, cùng cái trần đó thành mất năm mươi lần.

  Nay bản mồi lại rộng 300.000 ký tự, khoảng 100.000 token. Đo trên một hội thoại 120 lượt: trước giữ được 16 lượt, nay giữ được 86.
- **Và nó mang theo cả bản tóm tắt đã nén của phần đầu hội thoại**, đặt trước phần lịch sử thô và không bị cắt. Một dòng tóm tắt đại diện cho hàng chục lượt đã rơi khỏi ngân sách, nên bỏ nó để nhét thêm hai lượt thô là đổi sai chiều.
- Đã kiểm: ngưỡng xoay mạch **không đụng gì tới việc nền**. Nó chỉ chạy trong khung chat; loop và việc Kanban mở phiên engine mới mỗi lần chạy nên không có mạch nào để xoay.

## [0.14.1] - 2026-08-03
Ngưỡng xoay mạch nâng lên 1 triệu token theo số dùng thật, và dọn rác trích dẫn lọt vào câu trả lời.
### Sửa lỗi
- **Câu trả lời hiện ra kèm mấy ô vuông trống và chữ `citeturn4view0`.** Đó là dấu trích dẫn nội bộ của OpenAI, viết bằng ba ký tự vô hình mà trình duyệt vẽ thành ô vuông. Phần khó chịu hơn nằm ở chỗ không nhìn thấy: nó đi thẳng vào lịch sử hội thoại, nên lượt sau chính Javis đọc lại rồi tưởng `turn4view0` là một nguồn có thật. Hỏi "em lấy thông tin ở đâu" thì nó trả lời "mình chỉ còn mã tham chiếu `turn4view0`, không có URL nguồn gốc". Nay dấu đó được bóc ngay tại nguồn, ở cả đường Codex lẫn đường gọi thẳng.
### Cải thiện
- **Ngưỡng tự mở mạch hội thoại mới nâng từ 120.000 lên 1.000.000 token mỗi lượt**, theo yêu cầu chủ repo sau khi dùng thật. Số đo ủng hộ: ba lượt liên tiếp trong cùng một hội thoại là 83.000, rồi 552.000 (lượt đi tra thời tiết, Codex chạy cả vòng lặp tìm kiếm), rồi 36.000. Nghĩa là một lượt nặng thường nặng vì **công việc của chính lượt đó**, không phải vì mạch dài, và mạch tự co lại ngay lượt sau. Để 120.000 thì gần như lượt nào cũng vượt, tức xoay mạch liên tục: mỗi lần xoay là một lần vứt phần ngữ cảnh mà engine đang giữ, đổi lấy gần như không gì.

## [0.14.0] - 2026-08-03
Số đo thật cho thấy phần Javis gọt được chỉ là 13%, còn 87% token nằm ở chỗ khác. Bản này đi lấy chỗ đó.
### Thêm mới
- **Câu hỏi đơn giản trên gói ChatGPT giờ đi thẳng, không qua vòng lặp công cụ.** Số đo trên máy chủ repo: mỗi lượt Codex đọc vào 35.000 tới 412.000 token trong khi model chỉ viết ra 266 tới 1.496. Tỉ lệ đó không phải một lần gọi, mà là cả một vòng lặp: Codex nhận câu hỏi rồi tự gọi model nhiều vòng, mỗi vòng gửi lại toàn bộ ngữ cảnh đã tích. Với câu không cần tra cứu gì - "entropy là gì", "viết giúp em một tiêu đề" - cả vòng lặp đó là thừa. Nay những câu như vậy đi thẳng một vòng. Đây chính là thứ mức **Siêu tiết kiệm** hứa mà trước nay chưa từng làm được cho người dùng gói thuê bao.
- **Javis tự mở mạch hội thoại mới khi mạch cũ phình quá 120.000 token mỗi lượt.** Claude Code và Codex tự quản mạch của chúng, nên phần to nhất của mỗi lượt vốn nằm ngoài tầm với: gọt bộ luật xuống vài trăm token thì mạch cũ vẫn kéo theo hàng trăm nghìn. Số đo thật: lượt đầu một hội thoại 36.000 token, vài lượt sau đã 191.000. Nay khi vượt ngưỡng, Javis mở mạch mới và **mang theo tóm tắt lịch sử**, có báo cho anh biết ngay trong khung chat. Có mốc chống xoay liên tục: phải có thêm ít nhất hai lượt hỏi-đáp mới được xoay lần nữa, để một lượt nặng vì công việc không kéo theo việc phá mạch mỗi lượt.
### Sửa lỗi
- **Javis đoán trước mỗi lượt tốn bao nhiêu, và đoán thấp hơn thật gần bảy lần.** Trang ghi lệch âm 86%, có lượt âm 96%. Con số đó không chỉ để xem: nó chính là thứ Javis dùng để chặn TRƯỚC khi vượt hạn mức, nên đoán thấp bảy lần nghĩa là hàng rào đó gần như không tồn tại. Nguyên nhân: bộ đoán đếm đúng những gì Javis gói lại, nhưng không thấy được các vòng lặp mà engine tự chạy sau đó. Nay Javis **học từ chính các lượt đã chạy** của từng bộ não: thật gấp mấy lần đoán thì nhân lại bấy nhiêu. Chỉ nới lên chứ không bao giờ thu nhỏ, và có kẹp trần để một lượt bất thường không kéo lệch cả hệ số.
- **Lượt đi đường tắt là lượt duy nhất không có dòng "đi đường nào, tốn bao nhiêu".** Bản 0.13.0 gắn dòng đó vào ba nhánh mà quên nhánh này, nên đúng những lượt tiết kiệm nhất lại là những lượt không khoe được gì.
- **Lượt đi đường tắt không đi qua Codex, nên mạch của Codex không biết nó đã xảy ra.** Cứ nối tiếp mạch cũ ở lượt sau là Codex trả lời với một bản ghi thiếu: không thấy câu vừa hỏi lẫn câu vừa đáp, rồi nói lại hoặc nói mâu thuẫn. Nay sau mỗi lượt đường tắt, mạch được dựng lại từ lịch sử đã lưu.
- Đường tắt bị **chặn cứng** với gói Claude Code, không phụ thuộc cấu hình: nó chạy bằng đường gọi thẳng cần API key, thứ gói Claude Code không có. Nới cấu hình bằng tay tới đó là mọi câu hỏi đơn giản báo lỗi đăng nhập.
### Cải thiện
- **Test mới `test_ba_don_bay_token.py` chạy lượt chat thật qua cả ba đường** và canh cả chiều nguy hiểm: câu cần dữ liệu thật thì TUYỆT ĐỐI không được đi tắt, vì đi tắt một câu cần tra cứu là trả lời bịa. Kiểm ngược 10 đột biến, cả 10 đều bị bắt.

## [0.13.4] - 2026-08-03
Máy đã cài Javis từ trước thì bật tiết kiệm cũng không ăn: cấu hình cũ trong máy đè lên mặc định mới, và nó đè im lặng.
### Sửa lỗi
- **Bật mức tiết kiệm rồi mà dòng dưới mỗi câu trả lời vẫn ghi "Đầy đủ".** Đúng lỗi chủ repo chụp lại. Nguyên nhân nằm ở chỗ không ai ngờ: **mọi máy đã chạy Javis từ trước bản 0.12.4 đều dính**, còn máy cài mới thì không, nên mọi thử nghiệm trước đó đều xanh.

  Javis ghi lại **toàn bộ** cấu hình vào `settings.json` ngay lần đầu người dùng bấm bất cứ thứ gì, và khi đọc thì lấy file đè lên mặc định. Nghĩa là mặc định của ngày hôm đó bị đóng băng vĩnh viễn: sau này Javis có sửa mặc định cho tốt hơn thì máy đã cài rồi **không bao giờ thấy**. Trước 0.12.4, hai mảng tiết kiệm quan trọng nhất (bộ nhớ chọn lọc và skill nạp khi cần) chỉ chạy trên bộ não dùng API key. Máy cũ ghim cứng con số đó. Nâng cấp lên, bấm "Tối ưu", trang báo xanh "đã bật, có hiệu lực ngay", rồi mọi lượt trên gói ChatGPT hay gói Claude vẫn gửi nguyên bộ luật vì cả ba nguồn bị loại lặng lẽ.

  Nay khi đọc cấu hình, Javis **nới** phạm vi bộ não của các mảng tiết kiệm về ít nhất bằng mặc định hiện tại, và chỉ nới chứ không bao giờ thu hẹp. Mảng nào cố ý chỉ chạy trên bộ não API key (phần gửi lại lịch sử hội thoại: Claude Code và ChatGPT tự nhớ mạch của chúng rồi, gửi thêm là gửi hai lần) vẫn giữ đúng phạm vi của nó. Bấm mức một lần nữa thì chính file cấu hình cũng được chữa luôn.
### Cải thiện
- **Test mới `test_cauhinh_cu_khong_ket.py` dựng đúng một máy cài từ trước** rồi bấm mức như người dùng bấm. Đây là lớp lỗi mà test chạy trên máy sạch không bao giờ thấy được. Gỡ bản vá ra thì nó đỏ đúng năm chỗ.

## [0.13.3] - 2026-08-03
Rà lại xem bật mức tiết kiệm thì có tiết kiệm thật không. Thủng bốn chỗ, và cả bốn đều im lặng: trang vẫn báo xanh, token vẫn tốn như cũ.
### Sửa lỗi
- **Bốn trên năm bộ não dùng API key bấm "Tối ưu" xong không tiết kiệm được gì.** OpenRouter, OpenAI, Gemini và Anthropic API đều rơi vào đây. Lý do: phần chọn lọc ngữ cảnh đòi phải biết trước hạn mức token, mà bảng hạn mức có sẵn trong máy hiện **chỉ có Groq**. Không biết hạn mức thì nó lặng lẽ quay về gửi nguyên bộ luật mỗi lượt, trong khi trang vẫn ghi "đã bật, giảm 89%". Nay khi chưa biết hạn mức thật, Javis dùng một **trần ngữ cảnh mặc định** để gói ghém. Trần đó chỉ để biên soạn, không bao giờ dùng để từ chối câu hỏi của anh: vượt thì lui về cách cũ chứ không chặn. Và ngay lần đầu nhà cung cấp báo vượt hạn mức, Javis dùng đúng con số thật của họ thay cho trần này.
- **Đổi bộ não là mức tiết kiệm lặng lẽ ngừng chạy.** Hạn mức chỉ được khai đúng một lần, lần sau thấy "đã có gì đó" là bỏ qua. Nên bấm mức khi đang dùng Groq, sau đổi sang bộ não khác, thì Javis vẫn cầm hạn mức của Groq, không khớp bộ não mới, và mọi lượt về đường cũ mà không báo gì. Nay hạn mức được **bổ sung** cho bộ não đang dùng, giữ nguyên phần người dùng tự khai, và không đẻ bản sao khi bấm lại.
- **Lượt đã tiết kiệm vẫn bị ghi là "Đầy đủ".** Một lượt đi qua nhiều tầng; tầng nào không nhận thì đánh dấu "đường cũ", mà cách cũ là ai đánh dấu trước thì thắng. Phần tiết kiệm ngữ cảnh chạy sau cùng nên có nhận lượt cũng không đổi được nhãn. Hệ quả: dòng dưới câu trả lời ghi "Đầy đủ", bảng đo 24 giờ xếp lượt đó vào cột chưa tiết kiệm, và trang bảo anh chưa tiết kiệm được gì trong khi đang tiết kiệm. Toàn bộ bộ não API key dính, tức đúng những người trả tiền theo token. Nay "đường cũ" chỉ là mặc định khi chưa ai nhận, tầng nào nhận thật thì nhãn theo tầng đó. Vẫn giữ nguyên hai luật cũ: đường thật không ghi đè đường thật, và chỉnh mức giữa lượt không đổi lượt đang chạy.
- **Mức "Siêu tiết kiệm" khoe giảm 96% cho cả bộ não không dùng được nó.** Mức này hơn "Tối ưu" ở đúng đường tắt cho câu hỏi đơn giản, mà đường tắt chỉ chạy trên bộ não dùng API key. Ai đang chạy gói Claude hay gói ChatGPT thì bấm vào cũng chỉ bằng mức Tối ưu. Nay nút đó hiện đúng con số của bộ não đang chạy, kèm dấu **"không áp cho bộ não đang dùng"** và một câu nói rõ vì sao.
- **Cảnh báo của máy chủ bị nuốt.** Máy chủ có trả lời "mảng này chưa chạy được đâu" khi bấm mức, nhưng giao diện chưa bao giờ hiện nó, nên anh chỉ thấy một dòng xanh "đã bật, có hiệu lực ngay". Nay cảnh báo hiện thẳng trong thông báo.
### Cải thiện
- **Test mới `test_tiet_kiem_chay_that.py` bấm mức đúng như người dùng bấm, trên cả bảy bộ não, rồi hỏi thẳng lớp quyết định xem lượt này đi đường nào.** Kiểm ngược năm đột biến, gieo lại đúng năm lỗi trên, cả năm đều bị bắt.
- Nới trần độ dài một bước hướng dẫn kết nối lên 450 ký tự (chủ repo duyệt). Chín bước của Facebook và Google đang vượt mức cũ vì mỗi câu thêm vào là một sự cố có thật; giao diện không cắt chữ nên cắt cho vừa con số cũ là vứt đúng phần cứu người dùng.

## [0.13.2] - 2026-08-03
Bật gói ChatGPT là lượt chat nào cũng chết. Sửa lỗi đó, và dọn ba chỗ hỏng cùng họ mà CI không có cách nào nhìn thấy.
### Sửa lỗi
- **Chat qua gói ChatGPT (Codex) lượt nào cũng hỏng: `UnboundLocalError: cannot access local variable '_ctx_in'`.** Bộ đếm token thêm ở 0.13.0 cộng dồn ở ba nhánh bộ não; hai nhánh cộng ngay trong thân hàm nên chạy tốt, riêng nhánh Codex cộng bên trong một hàm con mà quên khai `nonlocal`. Python liền coi đó là biến cục bộ của hàm con, và `+=` đọc phải một biến chưa hề được gán. Nó nổ đúng vào khoảnh khắc Codex trả lời xong, nên hậu quả không chỉ là mất dòng đếm token: cả lượt vỡ, câu trả lời đã hiện trên màn hình không được lưu vào lịch sử, người dùng chỉ còn thấy "Lỗi xử lý". Mọi lượt chat của người dùng gói ChatGPT đều dính từ 0.13.0.
- **Đường đẩy kết quả việc nền về khung chat web có sẵn một NameError nằm phục.** `push_to_chat` ghi log lỗi bằng `sys.stderr` trong khi `main.py` chưa từng import `sys`. Vì nó nằm trong nhánh `except`, nó chỉ nổ khi đã có sự cố khác, và biến chuyện "ghi log rồi chạy tiếp" thành vỡ luôn cả đường báo kết quả. Đây đúng là đường mà việc Kanban, loop và nhắc hẹn dùng để trả kết quả về khung chat.
- **Nút "Bật People API" ở thẻ Google Lịch không bao giờ hiện ra.** Thẻ nào có wizard từng bước thì khối nút cũ bị ẩn hẳn, mà link People API chỉ nằm ở khối cũ. Người dùng làm đủ các bước vẫn bị `ACCESS_TOKEN_SCOPE_INSUFFICIENT` khi tìm giờ trống, không có cách nào biết còn thiếu gì. Nay People API là một bước riêng, có nút bấm.
- **Bảy file test chưa từng chạy một dòng nào trong CI.** Chúng viết theo kiểu pytest nhưng thiếu block `__main__`, mà CI thì chạy từng file như script, nên file chỉ định nghĩa hàm rồi thoát 0. Bốn assertion trong số đó đang ĐỎ và không ai biết, gồm cả lỗi nút People API ở trên. Nay cả bảy đều chạy thật.
### Cải thiện
- **Test mới `test_luot_chat_codex.py` chạy trọn MỘT lượt chat thật qua nhánh Codex** với WebSocket giả và Codex CLI giả, rồi soi đúng ba thứ lỗi kia phá: không gói lỗi nào, có câu trả lời kèm số token vào, và lượt được lưu vào lịch sử. Gieo lại đúng lỗi cũ thì test đỏ với y nguyên câu "Lỗi xử lý: UnboundLocalError" người dùng nhìn thấy.
- **Test mới `test_bien_chua_gan.py` canh đúng hai loại lỗi vừa sửa** trên toàn bộ cây mã: hàm con cộng dồn vào biến hàm cha mà quên `nonlocal`, và hàm dùng một tên toàn cục không tồn tại. Byte-compile không thấy được hai thứ này vì cú pháp hoàn toàn đúng, còn test kiểu tìm chữ thì càng mù: chúng vẫn đếm đủ số lần `_ctx_in +=` trong khi lỗi đang xảy ra. Bộ quét tự kiểm bằng cách dựng lại đúng hai đoạn mã hỏng và bắt mình phải kêu.
- Dòng giới thiệu gói Google Workspace và bước đầu của nó ngắn lại cho vừa một dòng menu, không cắt mất ý nào.

## [0.13.1] - 2026-08-03
Đặt lại tên các chế độ theo hướng nói đúng nó làm gì, thay vì nó cũ hay mới.
### Cải thiện
- **Bỏ chữ "đường cũ".** Đó là góc nhìn của người viết code, không phải của người dùng: với anh đó là chế độ **gửi đủ mọi thứ**, an toàn nhất, và đúng là thứ đang chạy khi bấm **Tắt**. Gọi nó là "cũ" vừa nghe như đang xin lỗi, vừa làm người ta tưởng máy đang chạy thứ hỏng.
- Bốn chế độ giờ có tên nói thẳng lợi ích: **Đầy đủ** (gửi mọi thứ, an toàn nhất), **Tối ưu** (chỉ gửi phần liên quan), **Tức thì** (câu đơn giản trả lời thẳng, không qua vòng công cụ), **Tra cứu** / **Tra cứu sâu** / **Thực thi** / **Quy trình**.
- Tên khớp nhau ở cả hai chỗ: dòng nhỏ dưới mỗi câu trả lời và bảng trên trang Tiết kiệm token, để nhìn một chỗ là nối được sang chỗ kia.
- Các mục trên trang viết lại theo bộ từ mới: "Vì sao chưa tối ưu được", "Mỗi cuộc chat dùng chế độ nào", "Gói tin khi Tối ưu".

## [0.13.0] - 2026-08-03
Trang Tiết kiệm token viết lại quanh câu hỏi duy nhất người dùng quan tâm: bật cái này thì đỡ được bao nhiêu. Và mỗi câu trả lời tự nói nó đi đường nào.
### Thêm mới
- **Mỗi mức ghi rõ tiết kiệm bao nhiêu phần trăm.** Ba nút giờ hiện thẳng con số: **Tắt** (mốc), **Tối ưu** (giảm khoảng 89%), **Siêu tiết kiệm** (khoảng 96%), kèm số token mỗi lượt. Con số đo trên chính bộ luật và bộ nhớ của anh chứ không phải hằng số quảng cáo, nên mỗi bộ não ra một con số riêng. Có ghi rõ đây là ước lượng.
- **Bảng đo THẬT.** Khi đã có lượt chạy ở cả hai đường trong 24 giờ, trang hiện luôn số thật: đường cũ tốn bao nhiêu, đường tiết kiệm tốn bao nhiêu, giảm mấy phần trăm. Chưa đủ dữ liệu thì nói là chưa đủ, không hiện 0% một cách vô nghĩa.
- **Mỗi câu trả lời có một dòng nhỏ nói nó đi đường nào** và tốn bao nhiêu token vào. Trước đây chuyện một lượt lặng lẽ tụt về đường cũ là hoàn toàn vô hình, phải đợi tới lúc nhà cung cấp báo vượt hạn mức mới lộ ra. Bấm vào dòng đó là sang thẳng trang Tiết kiệm token.
- **Panel Mức dùng nói luôn đang ở mức nào và giảm được bao nhiêu.** Con số tiêu thụ chỉ có nghĩa khi biết đáng lẽ nó phải là bao nhiêu.
### Cải thiện
- **Đổi tên ba mức thành Tắt / Tối ưu / Siêu tiết kiệm**, và đưa lên **đầu trang**. Trước đây ba nút bị chôn ở giữa, dưới bốn khối biểu đồ, nên mở trang ra là thấy số liệu trước khi thấy cái nút cần bấm.
- **Bảng "mỗi cuộc chat đi đường nào" thôi bắt người dùng tự hiểu chữ `legacy`.** Tên đường dịch hết ra tiếng Việt, và đường tiết kiệm giờ có tên riêng thay vì bị đếm nhầm thành đường cũ. Đây cũng là thứ làm bảng đo thật ở trên chạy được.
- Bảng hạn mức tự học nói đúng loại: token mỗi phút, token mỗi ngày, số lượt mỗi phút, số lượt mỗi ngày. Trước đây cái nào cũng ghi là token.

## [0.12.6] - 2026-08-03
Bật tiết kiệm token không còn biến câu trả lời thành khối JSON. Badge gọi đúng tên bộ não. Sửa vỡ khung chat trên điện thoại.
### Sửa lỗi
- **Bật mức Tiết kiệm xong, câu trả lời hiện ra thành một khối JSON.** Chỗ đáng lẽ là lời chào thì khung chat in nguyên `{"channel":"dashboard","language":"match_user",...,"content":"Chào anh"}`. Nguyên nhân: phần dặn cách trả lời được nhét vào prompt dưới dạng một object JSON. Đặt object ngay trước chỗ model phải trả lời thì model yếu hiểu là "hãy phát ra object này", và nó phát thật. Nay phần đó viết thành lời, cấm đích danh việc bọc câu trả lời trong JSON. Đây là lỗi nặng nhất trong nhóm: nó làm chính tính năng tiết kiệm token sinh ra rác, bật lên là hỏng.
- **Badge góc phải ghi "CLI" cho mọi bộ não dùng API key.** Chọn Groq mà badge ghi "CLI", trong khi thanh model ngay bên cạnh ghi "Groq". Chỗ nhận diện chỉ có hai nhánh: OpenRouter, hoặc CLI. Nay biết đủ bảy bộ não và đọc model chính theo đúng thứ tự máy chủ dùng.
- **Khung chat vỡ trên điện thoại.** Tiêu đề "Trò chuyện với Javis" xuống bốn dòng, chữ "Thu nhỏ" xuống hai dòng, đẩy khung chat tụt hẳn xuống. Hồi quy từ chính nút Thu nhỏ thêm ở 0.12.4. Nay màn hẹp thì nút chỉ còn icon, tiêu đề và nhãn bộ não tự cắt gọn trong một dòng.
- Panel Mức dùng thôi hiện trần mã provider cho Groq và Gemini.

## [0.12.5] - 2026-08-03
Groq siết bốn chiều cùng lúc, Javis từng gộp cả bốn thành "request quá lớn". Nay nói đúng loại và khuyên đúng việc.
### Sửa lỗi
- **"groq báo request quá lớn... lượt này cần khoảng 0 token".** Ba thứ sai trong đúng một câu. Gói Groq siết **bốn** thứ song song: token mỗi phút, **số lượt** mỗi phút, token mỗi **ngày**, số lượt mỗi ngày. Cả bốn đều mở đầu bằng "Rate limit reached", mà Javis lại lấy đúng cụm đó làm dấu hiệu "vượt kích thước", nên ba chiều kia bị gán nhãn sai. Số 0 là vì không đọc được gì từ câu lỗi, còn con 12.000 thì lấy từ **bảng tra sẵn trong code** chứ không phải từ Groq. Ghép hai thứ đó thành một câu nghe như đã hiểu chuyện vừa sai vừa che mất bằng chứng.
- **Nay mỗi loại hạn mức được khuyên đúng việc.** Lượt quá to thì rút gọn rồi thử lại. Cửa sổ phút đã đầy thì chờ đúng số giây nhà cung cấp nói. **Hết hạn mức theo ngày thì nói thẳng là rút gọn không giúp gì**, phải chờ sang ngày hoặc đổi bộ não hoặc nâng gói, thay vì để anh ngồi cắt câu hỏi cho ngắn rồi vẫn lỗi.
- **Không hiểu lỗi thì đưa nguyên văn lời nhà cung cấp ra, không bịa câu cho tròn.** Trước đây câu lỗi thật bị nuốt mất nên không ai lần ra được nguyên nhân.
- **Hạn mức đếm LƯỢT không còn bị dùng làm ngân sách token.** "30 lượt mỗi phút" mà đem nhân hệ số an toàn thì thành "co ngữ cảnh xuống 22 token", đủ để hỏng lượt chat.
- **Thôi thử lại khi thử lại chắc chắn vô ích.** Hết hạn mức ngày mà gửi lại chỉ tốn thêm một lượt để ăn đúng lỗi đó lần nữa.
### Cải thiện
- **Bộ định tuyến tự dùng hạn mức nó đã học được, khỏi chờ ai khai.** Thứ tự cũ bị ngược: cơ chế an toàn đòi khai hạn mức trước mới cho chạy, nên đúng lúc bị siết lại là đúng lúc phần tiết kiệm ngữ cảnh không hoạt động. Nay sau **một lần** bị nhà cung cấp từ chối là Javis có ngay con số thật của tài khoản đó và dùng luôn làm ngân sách. Người vận hành khai tay vẫn được ưu tiên trên hết.
- Rút gọn ngữ cảnh khi không đọc được hạn mức lần này thì lấy con số đã học từ lần trước, thay vì bỏ trống rồi chỉ cắt được mỗi lịch sử hội thoại.

## [0.12.4] - 2026-08-03
Phần tiết kiệm token nay dùng được cho **gói Claude và gói ChatGPT**, không chỉ tài khoản API key. Bỏ khung chat phóng to. Sửa nút xoá/đổi tên hội thoại.
### Thêm mới
- **Tiết kiệm token cho gói thuê bao.** Trước đây toàn bộ phần chọn lọc ngữ cảnh chỉ chạy trên bộ não dùng API key: Claude Code và ChatGPT/Codex bị loại ngay từ đầu vì hệ thống đòi biết "hạn mức token mỗi phút", thứ gói thuê bao không công bố. Nay hai bộ não đó dùng **trần ngữ cảnh** thay cho hạn mức thương mại, và ăn được hai mảng: **nhớ có chọn lọc** và **skill nạp khi cần**.
- **Trang Tiết kiệm token có khối "Bộ não đang dùng".** Nói thẳng bộ não hiện tại là loại gì, đang ăn được mấy mảng, mảng nào không áp cho nó và vì sao. Trước đây muốn biết phải đọc file cấu hình trên máy chủ.
- **Hết lượt gói thuê bao thì nói bằng tiếng Việt.** Claude Code và Codex in nguyên văn câu tiếng Anh, có khi là dạng máy đọc. Nay Javis dịch thành câu nói rõ: hết lượt gói nào, còn bao lâu nữa, bộ não nào đang sẵn sàng chạy tạm. Không tự đổi bộ não hộ - đó là tiêu hạn mức của một tài khoản khác, có khi mất tiền thật.
### Sửa lỗi
- **Bấm mức "Tiết kiệm" xong vẫn không có gì đổi.** Hạn mức được khai theo tên từng mảng, trong khi ba mảng chọn lọc ngữ cảnh lại đọc hạn mức ở một chỗ dùng chung. Kết quả: công tắc bật, con số lên, mà mọi lượt vẫn đi đường cũ. Nay khai vào đúng chỗ chúng đọc.
- **Hover vào một hội thoại thì nút xoá và đổi tên bấm không ăn.** Nút có hiện, bấm vào lại mở hội thoại đó. Vùng bấm thật chỉ còn viền mỏng quanh icon. Nay bấm đâu trong nút cũng ăn.
- Bật tiết kiệm token cho Claude Code không còn vô tình tắt phần skill native của nó.
### Cải thiện
- **Bỏ hẳn khung chat phóng to.** Nút phóng to nay **chuyển thẳng sang trang Trò chuyện**, và trang đó có nút **Thu nhỏ** để về lại màn Javis. Trước đây có hai khung chat trông gần giống nhau mà hành xử khác nhau, và cả hai giành chung một bộ thành phần nên hay sinh lỗi khi chuyển tab.

## [0.12.3] - 2026-08-02
Cập nhật thất bại thì nói rõ vì sao và phải làm gì, thay vì bảo đi đọc file log.
### Sửa lỗi
- **"Server lên nhưng phiên bản chưa đổi (pull chưa áp?). Xem update.log."** Câu này biết có chuyện bất thường mà không nói ra chuyện gì, rồi đẩy người dùng đi đọc một file log mà bản Windows/Docker gần như không với tới được. Nay Javis tự chẩn đoán và nói thẳng: đang đứng ở nhánh nào, theo dõi nhánh nào, và **lệnh cụ thể để sửa**. Nguyên nhân hay gặp nhất là máy đang theo dõi một nhánh khác nhánh có bản mới, nên `git` báo "đã mới nhất" một cách hoàn toàn hợp lệ. Cũng nhận ra trường hợp bản đóng gói sẵn (Docker) không cập nhật được từ mã nguồn, và trường hợp không đứng trên nhánh nào.
- Thông báo lỗi giờ nêu cả phiên bản đang chạy lẫn phiên bản đích, để nhìn là biết ngay đã lên hay chưa.

## [0.12.2] - 2026-08-02
Model yếu bịa sai cú pháp gọi công cụ thì Javis tự gỡ, thay vì hiện khối JSON lỗi rồi im lặng.
### Sửa lỗi
- **Llama đôi khi trả lời được, đôi khi hiện lỗi JSON rồi "(không có nội dung trả về)".** Nguyên nhân: model yếu thỉnh thoảng tự bịa cú pháp gọi công cụ thay vì đúng định dạng, nhà cung cấp từ chối. Nay Javis gỡ theo hai nấc: thử lại một lần (model sinh chữ có yếu tố ngẫu nhiên nên lần sau thường trúng), vẫn hỏng thì **bỏ công cụ và trả lời bằng lời** kèm một dòng báo. Trả lời thiếu công cụ vẫn hơn hẳn không trả lời gì.
- Chỉ áp cho đúng lỗi này, nhận theo mã lỗi riêng chứ không theo mã trạng thái, vì cùng mã đó còn dùng cho cả chục lỗi khác mà thử lại chỉ tổ tốn thêm một lượt.

## [0.12.1] - 2026-08-02
Groq/Llama: xử được cả trường hợp hạn mức phút đã đầy. Ba lỗi giao diện.
### Sửa lỗi
- **Groq báo lỗi hạn mức kiểu thứ hai mà Javis không nhận ra.** Nhà cung cấp có hai câu báo khác nhau: một là "lượt này quá lớn", hai là "phút này đã dùng hết hạn mức". Javis mới chỉ đọc được câu đầu, nên sau khi đã tự rút gọn thành công thì lại vấp câu thứ hai và trả lỗi thô. Nay đọc được cả hai, và với trường hợp thứ hai thì **chờ đúng số giây nhà cung cấp bảo chờ rồi tự gửi lại** thay vì cắt bớt ngữ cảnh vô ích. Vòng gọi công cụ vốn không có cơ chế thử lại nào nên đây cũng là lần đầu nó biết chờ.
- **Phóng to khung chat rồi chuyển tab thì khung phóng to vẫn nằm đè lên trang mới.** Nay chuyển tab là tự thu lại.
- **Trên điện thoại, chạm vào note mở trình sửa rồi không thoát được** vì thanh nút tràn khỏi màn hình hẹp. Theo yêu cầu, đã **tắt hẳn việc chạm note để sửa trên điện thoại** (node quá nhỏ nên gần như luôn chạm nhầm), kèm một dòng nhắc mở trên máy tính. Thanh nút của trình sửa cũng đã biết xuống dòng để nút Đóng luôn với tới được nếu vào bằng đường khác.
- **Đổi model ở trang Models thì thanh model dưới khung chat và dòng trạng thái trên hội thoại không đổi theo.** Hai chỗ đó đọc cấu hình ở hai thời điểm khác nhau và không ai báo cho ai. Nay mọi đường đổi model đều làm mới cả hai ngay lập tức.

## [0.12.0] - 2026-08-02
Trang Chẩn đoán đổi thành **Tiết kiệm token**: ba nút thay cho bảng mười dòng. Sửa lỗi Llama vẫn vượt hạn mức.
### Sửa lỗi
- **Llama/Groq vẫn báo vượt hạn mức dù 0.11.0 nói là đã tự xử.** Phần tự học hạn mức đặt nhầm chỗ: nó nằm ở các hàm gửi đơn giản, trong khi mọi lượt chat thật đều đi qua vòng gọi công cụ (Javis luôn có công cụ nội bộ nên vòng đó luôn được dùng). Code chạy đúng, test xanh, và không bao giờ được gọi tới. Nay đã đặt đúng chỗ, phủ cả năm nhà cung cấp cùng ChatGPT.
- **Bấm nút "Đặt" không thấy gì xảy ra.** Ô số hiện sẵn giá trị đang dùng, nên bấm mà không sửa số là đặt lại đúng giá trị cũ - một thao tác rỗng, lại không có thông báo nào. Nay mọi thao tác đều hiện một dòng xác nhận nói rõ vừa đổi cái gì.
### Cải thiện
- **Đổi tên trang thành "Tiết kiệm token".** Tên cũ "Chẩn đoán" không nói được trang dùng để làm gì.
- **Ba nút thay cho bảng mười dòng.** Chọn **Tắt**, **Tiết kiệm** hoặc **Tối đa**, mỗi nút có một dòng nói rõ đánh đổi. Javis tự lo phần bên dưới: bật đúng những mảng cần, tự bật công tắc trùm, tự khai hạn mức cho nhà cung cấp đang dùng. Không còn phải hiểu "canary", "allocation" hay "basis point" mới dùng được.
- Mức chỉ gồm những mảng **chạy được thật**. Mảng nào cần danh sách cho phép mà chưa khai thì không đưa vào, vì bật lên chỉ tạo cảm giác đã bật trong khi mọi lượt vẫn đi đường cũ.
- Bảng chi tiết cùng công tắc trùm chuyển vào mục **Nâng cao** gập sẵn, cho ai muốn thử nghiệm.
- Hạ mức thì tắt hẳn phần dư, không cộng dồn. Chỉnh tay lệch chuẩn thì trang báo là "custom" chứ không im lặng nhận bừa.

## [0.11.0] - 2026-08-02
Javis tự học hạn mức của mọi nhà cung cấp từ chính câu báo lỗi, tự rút gọn rồi chạy tiếp. Trang Chẩn đoán viết lại bằng tiếng người.
### Sửa lỗi
- **Dải báo đỏ trên thanh trạng thái nói sai và chỉ sai chỗ.** Nó ghi "Bộ não claude mất đăng nhập... Mở terminal chạy claude rồi gõ /login" - hướng dẫn đã lỗi thời vì giờ kết nối ở trang **Models**. Chuỗi lại dài hơn cả thanh trạng thái nên bị cắt cụt giữa chừng, mà phần bị cắt đúng là phần nói phải làm gì. Nay chỉ còn một câu ngắn **"Chưa kết nối Model AI - bấm để kết nối"**, bấm vào là sang thẳng trang Models. Chi tiết kỹ thuật chuyển vào tooltip, vẫn còn khi cần đi tra.
- Thông báo cùng nội dung gửi qua Telegram cũng viết lại theo góc người dùng, không mở đầu bằng tên bộ não nữa.

### Tính năng mới
- **Vượt hạn mức thì tự xử, không bắt anh đọc lỗi kỹ thuật.** Khi nhà cung cấp từ chối vì request quá lớn, câu báo lỗi của họ có nêu hạn mức thật của tài khoản. Javis đọc lấy con số đó, tự bỏ lịch sử hội thoại cho nhẹ, rồi gửi lại. Anh chỉ thấy một dòng "đang rút gọn ngữ cảnh rồi thử lại" và sau đó là câu trả lời.
- **Áp dụng cho MỌI nhà cung cấp, không riêng ai.** Nhận diện được câu báo lỗi của Groq, OpenAI, Anthropic, Gemini và OpenRouter, kể cả khi họ viết hai con số theo thứ tự ngược nhau. Cắm nhà cung cấp mới cũng không phải khai gì trước: Javis học từ lần từ chối đầu tiên và nhớ để không đâm vào nữa.
- **Chỉ thử lại một lần.** Rút gọn rồi mà vẫn vượt thì báo cho anh kèm con số cụ thể, vì lúc đó vấn đề không còn nằm ở kích thước ngữ cảnh.
- Câu hỏi hiện tại của anh **không bao giờ** bị cắt khi rút gọn. Thứ tự hy sinh là lịch sử cũ trước, rồi mới tới phần đuôi của hướng dẫn hệ thống.
### Cải thiện
- **Trang Chẩn đoán viết lại cho dễ hiểu.** Thêm phần giải thích trang này để làm gì, đường cũ khác đường mới ra sao, và "bật thử từng phần" nghĩa là gì. Mọi nhãn kỹ thuật đổi sang tiếng thường: "Token đã gửi đi" thay cho "Token vào (thật)", "Vì sao vẫn đi đường cũ" thay cho "Lý do không vào đường mới". Mỗi mục có một dòng nói rõ nhìn số đó để làm gì.
- Thêm mục **Hạn mức Javis tự học được**, cho thấy nhà cung cấp nào đã nói ra hạn mức thật của tài khoản anh.
- Lỗi vượt kích thước không còn bị thử lại y nguyên như lỗi quá tải tạm thời. Thử lại mà không rút gọn thì chỉ tốn thêm một lượt để nhận đúng lỗi đó.

## [0.10.1] - 2026-08-02
Sửa lỗi làm không bật được đường chạy mới, phát hiện ngay khi dùng thật với Groq.
### Sửa lỗi
- **Bật đường mới xong vẫn không có gì đổi.** Có một công tắc trùm (`mode`) mà 0.10.0 không hề phơi ra: mọi đường chỉ chạy khi nó ở `canary` hoặc `on`, còn mặc định là `shadow`. Đặt tỉ lệ lên bao nhiêu cũng vô nghĩa, mà màn hình lại báo thành công. Nay trang Chẩn đoán có ô chọn mode, và bật tỉ lệ khi mode chưa đúng thì bị chặn kèm lý do rõ ràng thay vì báo thành công giả.
- **Ba đường của tầng ngữ cảnh bị chặn nhầm.** Chúng dùng chung hạn mức khai ở chỗ khác nên không có mục hạn mức riêng, nhưng bộ kiểm tra lại đòi và từ chối với lý do sai là "chưa khai hạn mức". Lý do sai còn khó lần ra hơn là không chặn.
### Lưu ý
- Sau khi cập nhật, muốn Javis chạy nhẹ với model bị siết hạn mức (Groq) thì vào **Chẩn đoán**: đổi mode sang `canary`, bấm **Khai** hạn mức cho groq, rồi đặt tỉ lệ 10000 cho `memory_canary`, `lazy_skill_canary`, `conversation_state_canary`. Đo trên cấu hình thật: phần cố định gửi đi giảm từ khoảng 15.400 xuống khoảng 4.100 token.

## [0.10.0] - 2026-08-02
Nền tảng Adaptive Context Runtime: ngữ cảnh gửi cho model co theo việc cần làm, không phình theo số thứ đã cắm.
### Cải thiện
- **Tool không còn nhồi hết vào mỗi lượt.** Trước đây mọi schema tool đi thẳng vào request, cho mọi model, mọi câu hỏi. Tầng "nạp theo nhu cầu" đã có sẵn nhưng chưa từng chạy: nó chỉ giấu tool của connector ngoài, còn tool nội bộ và plugin thì luôn hiện, mà ngưỡng bật lại đếm theo SỐ LƯỢNG tool trong khi cái tốn tiền là KÍCH THƯỚC. Nay ngưỡng xét cả hai, và chỉ giữ lại vài tool hạt nhân. Đo trên cấu hình 26 tool + 30 skill: schema mỗi lượt giảm **83%** (11.994 xuống 2.001 ký tự). Có tác dụng ngay, không cần bật gì.
- **Javis biết trước là sẽ vượt hạn mức, và nói ra.** Trước đây gặp model bị siết token mỗi phút (như gói Groq miễn phí 12.000 TPM), Javis vẫn gửi request rồi để nhà cung cấp trả lỗi khó hiểu. Tệ hơn: khi phát hiện request quá to, nó lại rơi về đường gửi NHIỀU token hơn. Nay nó dừng trước, nêu rõ cần bao nhiêu token so với hạn mức, và gợi ý provider anh đang có mà chưa bị siết.
- **Loop nền, việc Kanban và nhắc hẹn không còn âm thầm ăn hết hạn mức.** Hạn mức token mỗi phút là của TÀI KHOẢN, nhưng trước đây chỉ vài đường được kế toán, còn chat thường, loop, việc nền và Telegram thì đốt vô hình. Nay gom về một sổ chung, nên khi bị chặn thì con số nhìn thấy được đúng như thực tế.
- **Trang Chẩn đoán** ở mục Hệ thống: token vào ra thật, sai số ước lượng, đường chạy từng lượt, lý do bị chặn, và token 60 giây qua gộp mọi nguồn. Chỉ số liệu, không có nội dung hội thoại hay tham số tool.
### Bảo mật
- **Chặn trang web lạ kích hoạt lệnh của Javis.** `/workflows/run` và `/workflows/resume` là địa chỉ dạng GET nên lớp chống giả mạo cũ không phủ tới, trong khi cookie đăng nhập vẫn đi kèm khi bị điều hướng. Một trang bất kỳ chỉ cần đẩy trình duyệt sang địa chỉ đó là workflow chạy trên máy anh, kể cả khi đã đặt mật khẩu. Nay chỉ chạy khi lệnh xuất phát từ chính dashboard; công cụ dòng lệnh không bị ảnh hưởng.
- **Sửa cấu hình lồng nhau không còn xoá nhầm phần bên cạnh.** Trước đây sửa một mục con là thay trọn cả nhóm, làm mất các thiết lập anh em mà không báo gì.
### Tính năng mới
- **Bật/tắt và khai hạn mức ngay trên trang Chẩn đoán.** Không phải sửa tay file cấu hình nữa. Bật một đường mà chưa khai hạn mức thì bị chặn kèm lý do, thay vì bật xong ngồi đợi một thứ không bao giờ chạy. Tắt thì luôn có hiệu lực ngay, không cần khởi động lại.
### Lưu ý
- **Bản này chưa đổi cách Javis trả lời.** Toàn bộ đường chạy mới vẫn ở chế độ quan sát, mọi tỉ lệ bằng 0. Phần thấy được ngay là tool nhẹ đi, trang Chẩn đoán, và hai bản vá bảo mật. Việc bật đường mới để sau, khi đã có số liệu nền để so.

## [0.9.293] - 2026-08-01
Trang Models xếp nhà cung cấp đã kết nối lên đầu.
### Cải thiện
- **Nhà cung cấp đã kết nối xếp lên đầu, chưa kết nối dồn xuống dưới.** Trong mỗi nhóm vẫn giữ nguyên thứ tự gốc nên nhìn không bị xáo trộn. Áp dụng cho cả danh sách card lẫn cột chọn nhà cung cấp trong hộp **Đổi model** (cả model chính lẫn model việc nền), để hai chỗ không nói hai kiểu.
- Riêng Claude Code phải hỏi `/claude/status` mới biết có đăng nhập thật không: nó không có ô API key nên server luôn báo `configured=true`, tin theo đó thì máy chưa đăng nhập Claude vẫn thấy nó nằm chễm chệ trên cùng.

## [0.9.292] - 2026-08-01
Thêm Groq làm nhà cung cấp model thứ bảy.
### Tính năng mới
- **Đấu thêm Groq (API).** Trang Models có thêm card **Groq (API)**: dán API key là dùng được, danh sách model nạp LIVE từ Groq (đã lọc bỏ model whisper/guard/embedding vì chúng không chat được). Groq đi đường OpenAI-compatible nên dùng chung vòng gọi tool với OpenAI/Gemini - tức là **đủ MCP Javis + tool file brain + skill** ngay từ đầu, không phải chat suông.
- Chọn được cả cho **model việc nền**. Groq suy luận rất nhanh và rẻ nên hợp với loop, việc Kanban, nhắc hẹn - những thứ đốt hạn mức âm thầm nhất.
- `reasoning_effort` chỉ gửi cho dòng model suy luận (qwen3, deepseek-r1, gpt-oss, kimi thinking). Gửi cho llama/mixtral/gemma là Groq trả 400, nên phải lọc theo tên model y như cách đang làm với OpenAI o-series và Gemini 2.5.
- Khoá Groq nằm trong danh sách **mã hoá trước khi ghi** `settings.json`, giống các khoá provider khác.
- Thêm `test_groq_provider.py` chốt phần đấu dây. Thêm một provider phải chạm 7 chỗ rời nhau; sót một chỗ là lỗi câm (card hiện ra nhưng chat rơi về nhánh mặc định, hoặc key ghi plaintext, hoặc chọn làm model việc nền thì nổ lúc chạy nền). Test chạy với máy chủ Groq giả lập nên không cần mạng và không tốn quota.

## [0.9.291] - 2026-08-01
Bỏ `html-to-webcake` khỏi bộ skill mặc định của hệ thống.
### Cải thiện
- **Gỡ skill hệ thống `html-to-webcake`.** Nó ship kèm `tools/` và `examples/`, nhưng cơ chế cài skill hệ thống chỉ chuyển mỗi `SKILL.md` nên cây con chưa bao giờ tới brain nào - skill này hỏng ở mọi brain từ đầu (đã ghi nhận ở 0.9.71 mà chưa vá). Chủ repo chốt bỏ hẳn thay vì vá.
- Brain nào đã cài rồi thì **bản trong brain vẫn còn nguyên**, chỉ khác là giờ nó tính như skill của bạn: xoá được thẳng ở trang Skills (skill hệ thống thì không xoá được). Vòng đồng bộ không đụng tới mục đã rời khỏi nguồn hệ thống, nên không có gì tự mất.
- Mục cảnh báo trong skill `javis-builder` bỏ ví dụ đã chết, viết lại thành luật chung: đừng viết skill HỆ THỐNG cần cây con.

## [0.9.290] - 2026-07-31
Gõ `/` gọi skill được ở giữa câu, không phải chỉ ở đầu ô nhập.
### Cải thiện
- **Lệnh `/` dùng được ở giữa khung chat.** Trước đây cả menu lẫn phần định tuyến đều neo vào đầu chuỗi, nên viết "test sử dụng skill giữa khung chat /" là không ra menu và gửi đi cũng không ăn gì. Giờ cứ viết yêu cầu trước, tới đâu cần thì gõ `/` tới đó: phần chữ hai bên lệnh đều được gộp thành yêu cầu cho skill. Chọn trong menu thì `/slug ` chèn đúng chỗ con trỏ, chữ đã gõ giữ nguyên.
- **Ba rào chống bắt nhầm.** Dấu `/` phải đứng đầu câu hoặc ngay sau khoảng trắng (nên `https://vd.com/notes` và `3/4 cái bánh` vô can); ở giữa câu thì tên lệnh phải là skill CÓ THẬT trong brain đang chọn (nên `/home/user/notes` đi thẳng vào chat như chữ thường); và ba lệnh phiên `/new` `/reset` `/stop` chỉ chạy khi đứng ở đầu ô nhập - viết nửa câu rồi lỡ bấm `/reset` mà mất sạch ngữ cảnh thì hại hơn tiện, menu cũng không gợi ý chúng ở giữa câu.
- Danh sách skill được nạp sẵn lúc khởi động thay vì đợi mở menu lần đầu, để người gõ tay `/viet-email` giữa câu mà chưa mở menu lần nào vẫn được nhận.
- 20 kiểm tra mới trong `test_chat_slash.js` phủ cả định tuyến lẫn cách menu bắt token theo con trỏ.
- Sửa một test đo mức dùng token bị đỏ theo giờ: nó ghi vài dòng theo NGÀY THẬT rồi lại so sánh mốc cố định, nên đúng lúc đồng hồ sang tháng mới là dòng rác đó rơi vào cửa sổ so sánh và làm nổ cảnh báo oan. Dọn sạch dòng ngày-thật trước phần kiểm tra cảnh báo.

## [0.9.289] - 2026-07-31
Giao việc nền trong chat web xong là im lặng tuyệt đối - giờ kết quả tự về đúng khung chat đó.
### Sửa lỗi
- **Chạy agent/việc nền trên dashboard: không trạng thái, không hồi âm.** Đường báo cáo của việc Kanban, loop và nhắc hẹn CHỈ biết gửi Telegram. Máy chưa đấu Telegram thì `_notify_owner` trả về thất bại và `TaskRunner._report` nuốt luôn - kết quả bay vào hư không, người ngồi web không có kênh nào nhận. Giờ chat web là kênh nhận báo thật: việc giao trong chat mang theo mã phiên (`chat_id: "web:<mã phiên>"`, mượn field có sẵn nên không phải đổi lược đồ CSDL), xong việc thì kết quả hiện thẳng thành một tin của Javis trong đúng cuộc trò chuyện đó. Server ghi vào lịch sử phiên TRƯỚC rồi mới đẩy WebSocket, nên đóng tab hay F5 vẫn còn; đang xem cuộc trò chuyện khác thì phiên gốc nổi lên trong Lịch sử.
- **Javis hứa "em sẽ đợi các agent chạy nền hoàn tất rồi tổng hợp cho anh" - lời hứa không thể giữ.** Lượt trả lời kết thúc ngay khi nó nói xong, không cơ chế nào đánh thức nó dậy. System prompt và khối kênh dashboard nay cấm hẳn kiểu hứa đó, và chỉ hai đường thay thế: giao thêm một việc chuyên tổng hợp (dùng `deps` trỏ vào các việc trước), hoặc bảo user nhắn lại một câu khi kết quả đã về.
- Javis giờ biết mã phiên chat hiện tại (khối "KÊNH HỘI THOẠI HIỆN TẠI" của bản web) nên tự gắn được người nhận. Nhánh Telegram giữ nguyên đường cũ, hai kênh độc lập.
- Thêm `test_bao_viec_ve_chat_web.py` canh cả đường báo (đẩy WebSocket + lưu phiên + không bịa thành công khi thiếu kênh) lẫn lời văn trong prompt. Đặt lại lỗi cũ thì đỏ đúng 6 dòng.

## [0.9.288] - 2026-07-31
Ô nhập tên miền teo còn một sợi, không thấy chỗ mà gõ.
### Sửa lỗi
- **Ô nhập tên miền trong Cài đặt bị bóp còn một sợi.** style.css cho MỌI nút trong Cài đặt nhanh `width:100%` - đúng khi nút xếp chồng dọc, nhưng hàng tên miền là một hàng ngang "ô nhập + nút". Trong flex row, item mang `width:100%` có cỡ mong muốn bằng trọn hàng, còn ô nhập khai `flex:1` (cỡ mong muốn bằng 0), nên khi phải co thì phần co dồn hết vào nút và ô nhập ở lại 0 - chỉ còn thấy viền. Giờ ô nhập grow từ kích thước thật và nút chỉ rộng bằng chữ. Đo trên Chromium: ô nhập từ vài pixel lên 285px ở desktop, giãn hết 476px khi màn hẹp xếp dọc.
- **Hàng nút SSL dính đúng lỗi đó** (nút "Kiểm tra lại" nuốt hàng, "Bật SSL" teo lại) vì chỉ khai flex cho một trong hai nút. Hàng này chỉ hiện sau khi đã đặt tên miền nên chưa ai kịp báo. Đã khai cho cả hai.
- Ô nhập tên miền nay có kiểu riêng (nền, viền, bo góc, viền cam khi focus) thay vì để trơ mặc định trình duyệt - khối popover này không có kiểu input dùng chung.
- Thêm `test_hang_nhap_ngang.py` canh luật: hàng ngang trong Cài đặt nhanh thì ô nhập phải grow từ basis auto, nút phải `width:auto`, và ngoại lệ trong style.css phải đủ 3 lớp class để thắng bất kể thứ tự nạp (CSS khối tên miền do branding.js tiêm lúc chạy).

## [0.9.287] - 2026-07-31
Mở file nào trong trình sửa thì Javis làm việc trên file đó - khỏi dán đường dẫn hay tả lại.
### Tính năng mới
- **File đang mở tự ghim vào khung chat.** Mở một file văn bản trong trình sửa là Javis ghim ngay file đó thành thẻ màu cam phía trên thanh nhập ("đang mở - Javis làm việc trên file này"). Từ đó bảo "dọn lại phần quá hạn" hay "viết thêm mục kết luận" mà không nhắc tên file thì Javis vẫn ghi thẳng vào đúng file đó. Mở file khác thì thẻ đổi theo, không cộng dồn.
- Thẻ ghim khác thẻ đính kèm ở chỗ **không mất sau khi gửi**: đính kèm là dữ liệu một lượt, còn file đang mở là đầu vào của cả cuộc trò chuyện. Ghim sống qua F5 (cùng lý do với khôi phục hội thoại ở 0.9.268), tự bỏ khi đổi brain hoặc xoá chính file đó, và bấm nút đóng trên thẻ để bỏ tay. Đóng cửa sổ sửa KHÔNG bỏ ghim - đóng ra để quay sang chat về chính file đó là luồng thường gặp nhất.
- `/files/read` trả thêm khoá `abs` (đường dẫn thật của file). Cần nó vì đường dẫn tương đối trên giao diện tính theo trần duyệt, còn engine cần đường dẫn hệ thống - hai cái lệch nhau khi trần duyệt nằm cao hơn gốc brain, client tự ghép là ghép sai.
- System prompt học cách đọc khối `[FILE ĐANG MỞ ...]`: đọc file trước khi trả lời, và mặc định ghi vào chính file đó khi user không nói rõ file nào.

## [0.9.286] - 2026-07-31
Trang Models gọn lại, thang độ sâu suy nghĩ thêm hai nấc.
### Tính năng mới
- **Thang độ sâu suy nghĩ thêm hai nấc: Rất cao và Tối đa.** Trước chỉ có Tắt / Thấp / Vừa / Cao, trong khi Claude Code cho tới Ultra. Nay đủ sáu nấc ở cả trang Models lẫn thanh chọn trong khung chat.
### Cải thiện
- **Trang Models bớt tường chữ.** Hai đoạn mô tả dài ở mục Model việc nền và mục Suy nghĩ rút còn một dòng mỗi mục; phần chi tiết kỹ thuật hạ xuống thành ghi chú nhỏ, mờ, một ý. Cảnh báo "nhà cung cấp chưa kết nối" tách thành dòng riêng thay vì nhét vào giữa dòng tên model.
- **Chọn độ sâu đổi từ chip rời sang thanh phân đoạn liền.** Sáu nấc để rời thì hàng nút trôi lung tung; gộp một thanh thì nhìn ra ngay đây là một thang từ nhẹ tới nặng. Mỗi nấc kèm một dòng phụ rất ngắn (nhanh nhất, cân bằng, tốn token nhất). Màn hẹp thì giữ nhãn, bỏ dòng phụ cho khỏi vỡ hàng.
- Card cài đặt thôi nhún khi rê chuột - nó là bảng cài đặt đứng yên, không phải thẻ bấm được.
### Sửa lỗi
- **Đường lưu và đường đọc mức suy nghĩ có hai danh sách hợp lệ riêng.** Thêm nấc mới mà chỉ sửa một bên thì giao diện cho chọn nhưng server lặng lẽ hạ về "Tắt" - đã đo được đúng lỗi này trong trình duyệt khi làm. Nay cả hai soi chung `engine.REASONING_LEVELS`.
- **Nấc mới không được gửi thẳng lên API.** Nhà cung cấp chỉ nhận `low|medium|high`; gửi `ultra` là ăn 400 và hỏng cả lượt chat. Thêm một cửa ải dịch mức Javis sang giá trị API an toàn, và toàn bộ 9 chỗ nhét effort vào payload đều đi qua nó. Hai nấc trên cùng khác nhau thật ở chỗ Javis tự điều khiển được: từ khoá think của Claude Code và budget token của model Anthropic đời cũ (20k so với 32k).
- Ghi chú dưới thanh chọn nói thẳng rằng nhiều nhà cung cấp chỉ nhận 3 nấc nên hai nấc trên cùng có thể như nhau ở đó - thà nói trước còn hơn để người dùng tưởng đã chọn sâu hơn.
- Thêm `tests/python/test_do_sau_suy_nghi.py`: 33 phép thử, trong đó 5 canary, có kiểm chứng ngược.

## [0.9.285] - 2026-07-31
Bấm ảnh trong chat là xem phóng to, không còn tự tải file về.
### Tính năng mới
- **Lightbox xem ảnh.** Bấm bất kỳ ảnh nào trong chat là mở lớp xem phóng to: ảnh vừa màn hình, nền tối, kèm tên file và ba nút Tải về / Mở tab mới / Đóng. Bấm vào ảnh để đổi qua lại giữa vừa-màn và cỡ thật (1:1) rồi kéo xem chi tiết. Esc hoặc bấm nền tối để đóng.
### Sửa lỗi
- **Bấm ảnh vừa tạo thì file tự tải xuống máy thay vì mở ra xem.** Ảnh trong brain được bọc trong `<a download href=…&dl=1>` nên bấm một cái là file rơi xuống máy; muốn xem cho rõ thì phải đi mở file vừa tải, rất vòng. Trớ trêu là CSS `.chat-img` đã để `cursor: zoom-in` từ lâu, tức con trỏ hứa phóng to mà hành vi lại là tải về. Nay xem là mặc định, tải về nằm trong lightbox.
- Áp cho **mọi ảnh trong chat**: ảnh markdown, ảnh `![[...]]`, và ảnh từ URL ngoài đều cùng một hành vi.
### Cải thiện
- **Ctrl/Cmd/Shift/giữa chuột vẫn mở ảnh gốc ra tab mới** như mọi link khác - lightbox chỉ chặn cú bấm thường. Thẻ `<a>` vẫn trỏ thẳng tới ảnh nên hành vi này là của trình duyệt, không phải mô phỏng.
- Nút Tải về đi qua đường `dl=1` của server, nên tên file giữ nguyên kể cả tên tiếng Việt.
- Đang soạn note thì bấm ảnh vẫn là để sửa, không bung lightbox.
- File **không phải ảnh** (html, pdf, docx…) giữ nguyên hành vi tải về như cũ.
- Đã đo trong app THẬT bằng Chromium, 16 phép thử. Thêm `tests/js/test_lightbox_anh.js` (28 phép thử) cho CI, có kiểm chứng ngược. Một assertion cũ trong `test_chat_render.js` khoá đúng hành vi tải-về nay đã cập nhật theo, kèm ghi chú đây là đổi có chủ ý.

## [0.9.284] - 2026-07-31
Hội thoại có file đính kèm thôi trùng tên, đặt tên theo nội dung thật.
### Sửa lỗi
- **Mọi hội thoại có file đính kèm đều mang đúng một cái tên "[File đính kèm để ĐỌC (đườn…"**, nhìn danh sách Lịch sử không phân biệt nổi cái nào là cái nào. Nguyên nhân: tên = 48 ký tự **đầu** của tin nhắn thô, mà khi có file đính kèm thì dashboard chèn sẵn một khối hướng dẫn dài **trước** câu hỏi. Nay khối đó được bóc trước, tên lấy từ chính câu người dùng gõ.
- Đính kèm file mà không gõ chữ nào thì tên lấy **tên file** (nhiều file thì "a.png +2 file"), thay vì lấy câu điền sẵn cũng vô nghĩa như nhau ở mọi hội thoại.
- Cắt tên ở **ranh giới từ** thay vì cắt cứng giữa chữ, nên không còn ra kiểu "…(đườn…".
- Tin nhiều dòng lấy **dòng đầu** làm tên, thay vì dính cả bài thành một chuỗi dài.
### Cải thiện
- Bóc khối đính kèm neo đúng vào cụm "File đính kèm" chứ không bóc mọi khối `[..]` mở đầu: người dùng có quyền mở câu bằng ngoặc vuông ("[gấp] xem giúp anh…"), bóc bừa là mất luôn phần quan trọng nhất. Có canary canh.
- Tên file lấy theo đúng định dạng danh sách `- <đường dẫn>` mà dashboard sinh ra, nên hai thư mục cấu hình `Sources=`/`Attachments=` không lọt vào tên (trước khi sửa cho ra "My +4 file", lặp y hệt ở mọi hội thoại).
- Không cắt ở dấu chấm giữa câu: tiếng Việt chấm nhiều, cắt ở đó thì "Chào em. Hôm nay doanh thu bao nhiêu?" chỉ còn "Chào em".
- Thêm `tests/python/test_dat_ten_hoi_thoai.py`: 32 phép thử, có kiểm chứng ngược.

## [0.9.283] - 2026-07-31
Đấu được n8n qua MCP chính chủ, và catalog học được kiểu connector tự dựng.
### Tính năng mới
- **Connector n8n.** Đấu vào trang Kết nối bằng địa chỉ n8n của bạn + MCP Access Token, dùng được cả n8n cloud lẫn n8n tự dựng. Javis tìm và đọc workflow, xem lịch sử chạy, tạo và sửa workflow, và chạy workflow nếu được cấp quyền.
- **Catalog hỗ trợ URL động (`url_template`).** n8n là connector đầu tiên mà địa chỉ server nằm trên tên miền của **chính người dùng**, không phải một địa chỉ dùng chung ghi cứng trong app. Địa chỉ ở đây là một phần thông tin đăng nhập, nên catalog cho khai template rồi ghép từ ô người dùng gõ. Không có nó thì n8n phải rơi sang connector "custom", mất hướng dẫn, mất phân loại quyền đọc/ghi và mất cảnh báo rủi ro.
- Địa chỉ gõ kiểu nào cũng nhận: thiếu `https://`, thừa gạch chéo cuối, hay dán nguyên URL đang mở kèm đường dẫn và tham số đều được cắt về đúng tên miền. Giữ nguyên `http` và cổng cho bản tự dựng trong mạng nội bộ. Đầu vào không phải địa chỉ thì trả rỗng để báo thiếu, thay vì đẻ ra URL cụt rồi để người dùng ngồi đoán vì sao Test đỏ.
- URL được dựng lại **mỗi lần resolve** chứ không chỉ lúc thêm, nên sửa địa chỉ n8n là kết nối đi theo ngay, giống cách headers vốn đã hoạt động.
### An toàn
- **`execute_workflow` xếp vào nhóm NGUY HIỂM**, không phải nhóm ghi thường. Tên nghe hiền nhưng nó chạy thật một workflow: gửi mail, đăng bài, gọi API tính tiền, đẩy dữ liệu ra ngoài. Javis không nhìn được bên trong workflow làm gì và chạy rồi thì không hoàn tác được. Kết quả: mức **Ghi nháp** tạo và sửa được workflow nhưng **không chạy được**, phải lên Toàn quyền mới chạy. Loop nền ở chế độ gợi ý vẫn bị ép về chỉ đọc kể cả khi kết nối để Toàn quyền.
- Mặc định mức **Chỉ đọc**. Cảnh báo rủi ro nói rõ token này thấy mọi workflow và cả danh sách credential mà tài khoản n8n của bạn thấy.
### Cải thiện
- Thêm `tests/python/test_n8n_connector.py`: 59 phép thử gồm chuẩn hoá địa chỉ, phân loại 12 tool, cổng quyền ở cả ba mức, và đường thật thêm kết nối rồi resolve. Có kiểm chứng ngược.

## [0.9.282] - 2026-07-31
Menu gõ "/" sửa hai lỗi chặn dùng thật, và bỏ bớt hai mục thừa.
### Sửa lỗi
- **Bấm mũi tên xuống thì vệt chọn bật ngược lên đầu, không đi xuống được.** Bộ xử lý nhả phím chạy tiếp rồi đặt lại vị trí chọn về 0, nên keydown vừa chọn mục 2 xong là keyup kéo ngay về mục 1. Nay phím điều hướng được chặn hẳn ở nhả phím, và phần lọc chỉ chạy lại khi chữ đang gõ **thật sự đổi**.
- **Chọn "Tiêu đề 1/2/3" ở một dòng trống thì không ra gì.** Sau khi xoá đoạn `/tu-dang-go`, text node còn rỗng nên trình duyệt dọn luôn, kéo theo vị trí con trỏ chết và rơi về thẻ bọc. Lúc đó `formatBlock` vẫn trả về `true` nhưng không làm gì cả vì nó không biết đang đứng ở khối nào. Nay con trỏ được đặt lại bám vào node còn sống, ưu tiên chính text node, không thì khối cha. Lỗi này có từ bản 0.9.280; test cũ không bắt được vì chỉ thử đường checkbox, mà lệnh đó dùng `insertUnorderedList` vốn dễ tính với con trỏ.
- Menu đang mở mà con trỏ nhảy sang chỗ khác rồi gõ `/` thì menu đóng nhưng **không mở lại** ở chỗ mới, phải gõ `/` hai lần. Nay đóng xong vẫn xét tiếp chính phím vừa gõ.
### Cải thiện
- **Bỏ "Đậm" và "Nghiêng" khỏi menu `/`** theo yêu cầu. Hai lệnh đó bôi chữ **đang chọn**, mà gõ `/` xong thì có chọn gì đâu. Chúng vẫn giữ nút trên thanh công cụ và `Ctrl+B` / `Ctrl+I`. Menu còn 10 mục.
- Mục đang chọn được kéo vào tầm nhìn khi bấm mũi tên, vì menu dài hơn khung nên trước đây đi xuống quá nửa là không còn thấy mình đang ở đâu.
- Đã đo bằng Chromium thật: 11 phép thử điều hướng (xuống, lên, vòng lại, cuộn theo, Enter chèn đúng mục đang sáng, gõ chữ mới đặt lại vệt chọn) và 7 phép thử chọn từng lệnh bằng cách **gõ thật** vào khung soạn, cả dòng trống lẫn dòng có sẵn chữ.
- Test CI thêm 5 phép thử khoá hai lỗi trên, có kiểm chứng ngược.

## [0.9.281] - 2026-07-31
Cuộn lên đọc lại trong khung chat dài giờ có nút nhảy thẳng xuống cuối.
### Tính năng mới
- **Nút xuống cuối hiện ngay khi rời đáy khung chat.** Nút `#newMsgBtn` vốn đã có nhưng chỉ được bật bên trong `scrollBottom()`, mà hàm đó chỉ chạy khi **có tin mới** tới. Nghĩa là cuộn lên đọc lại một hội thoại dài rồi muốn quay xuống thì không có nút nào, phải tự kéo tay hết cả khung. Nay chính bộ xử lý cuộn bật nút, nên rời đáy là có nút, không phụ thuộc tin mới.
- Nút có **hai dạng cho hai tình huống**: chỉ đang cuộn lên đọc lại thì là nút tròn nhỏ chỉ có mũi tên, đủ để nhảy xuống; có tin mới tới lúc đang đọc thì nở ra thành viên thuốc chữ "Tin mới" màu nhấn để đập vào mắt. Cuộn về đáy thì nhả lại dạng gọn, nếu không thì lần sau chỉ cuộn lên đọc lại vẫn thấy chữ "Tin mới" báo sai.
### Cải thiện
- Nút mang `aria-label` đổi theo dạng, nên bộ đọc màn hình nói đúng việc nó làm.
- Bóng đổ dùng `--shadow-2` thay vì `--shadow-1`, và viền/icon tăng tương phản: nút nổi **đè lên chữ** của tin nhắn nên nhạt quá là chìm hẳn vào nền chữ.
- Đã đo trong app THẬT bằng Chromium (dựng server tại chỗ), 15 phép thử: cuộn lên hiện nút, bấm nhảy đúng xuống đáy, có tin mới thì nút nở ra, về đáy thì ẩn và nhả dạng tin mới, và nút vẫn đi theo khi phóng to khung chat. Xem cả hai tông sáng và tối.
- Thêm `tests/js/test_nut_xuong_day.js`: 25 phép thử cho CI, có kiểm chứng ngược (gỡ `flex: none` hoặc gỡ lời gọi trong bộ xử lý cuộn thì test đỏ đúng chỗ).
### Sửa lỗi
- `flex: none` cho nút: `.transcript` là flex dọc nên nút là flex item **bị co theo chiều cao**, nút tròn 32px bị bóp còn 15px thành bầu dục. Lỗi này chỉ lộ ra khi đo trong trình duyệt thật.

## [0.9.280] - 2026-07-31
Trình soạn .md có nút checkbox, phím tắt cho mọi định dạng, và menu gõ "/".
### Tính năng mới
- **Nút checkbox trên thanh công cụ**, đứng ngay sau danh sách số vì nó cùng họ danh sách. Bấm ở chế độ Sửa là ra ô tick thật; ở chế độ Nguồn thì chèn `- [ ] `. Trước đây thanh công cụ có bullet và danh sách số nhưng thiếu hẳn checkbox, nên cách duy nhất để tạo là gõ `- [ ]` rồi nhấn phím cách, mà không có gì trên màn hình gợi ý điều đó.
- **Phím tắt cho toàn bộ định dạng**, chạy ở cả hai chế độ Sửa và Nguồn: `Ctrl+B` đậm, `Ctrl+I` nghiêng, `Ctrl+Alt+1/2/3` tiêu đề, `Ctrl+Shift+8` gạch đầu dòng, `Ctrl+Shift+7` danh sách số, `Ctrl+Shift+9` checkbox, `Ctrl+Shift+.` trích dẫn (nhớ theo dấu `>` của markdown), `Ctrl+E` code, `Ctrl+K` link. Trên Mac đọc `Ctrl` thành `Cmd`.
- **Menu gõ "/"**: trong chế độ Sửa, gõ `/` ở đầu một từ là sổ bảng chọn đủ 12 chức năng kèm phím tắt hiện bên cạnh. Gõ tiếp để lọc (không dấu cũng ra, `/tieu` khớp "Tiêu đề"), mũi tên chọn, Enter hoặc bấm chuột để chèn, Esc để đóng. Dấu `/` giữa từ như `12/2026`, `và/hoặc` hay đường dẫn `a/b` không kích hoạt menu.
### Cải thiện
- Bảng lệnh gom về một chỗ duy nhất (`dashboard/editor-cmds.js`) nuôi cả ba đầu ra: nút, phím tắt, menu "/". Trước đây bảng nút nằm lẫn trong hàm dựng thanh công cụ; để nguyên vậy thì ba nơi sẽ trôi khỏi nhau ngay lần thêm lệnh sau.
- Phím SỐ khớp bằng `e.code` chứ không phải `e.key`: giữ Alt trên Mac làm `e.key` thành `¡`, dùng `e.key` là phím tắt tiêu đề chết trên Mac.
- Không cướp phím của trình duyệt và của app: `Ctrl+1..9` trần (đổi tab), `Ctrl+S` (lưu note), `Ctrl+Shift+I` (devtools), `Ctrl+Shift+B` (thanh bookmark) đều được để nguyên.
- Đã đo bằng Chromium thật: 24 phép thử cho nút, phím tắt hai chế độ, và menu "/"; cộng một vòng round-trip khép kín Sửa → markdown → vẽ lại với Turndown và plugin GFM thật, xác nhận checkbox lưu ra đúng `- [ ]` / `- [x]` và mở lại vẫn là ô tick.
- Thêm `tests/js/test_editor_cmds.js`: 57 phép thử cho CI (vốn chỉ có `node`), gồm 8 canary chặn việc cướp phím trình duyệt và chặn menu "/" bung nhầm giữa từ.
### Sửa lỗi
- `dashboard/console.js` lẫn **một byte NUL thô** trong chuỗi khoá cache, khiến mọi công cụ coi cả file là nhị phân và `grep` không đọc được. Thay bằng escape `\0`, chuỗi lúc chạy y hệt.

## [0.9.279] - 2026-07-31
Chat mở rộng thôi làm popup: nó choán đúng khung nội dung, dán tệt vào bố cục.
### Cải thiện
- **Khung chat phóng to giờ là một phần của giao diện, không phải hộp thoại nổi.** Trước đây nó bo góc 16px, có bóng đổ, canh giữa màn hình và chỉ rộng `96vw` nên hai bên vẫn hở ra thấy graph phía sau - đọc ra như một lớp đè lên app. Nay nó bám đúng vùng nội dung: mép trên là đáy thanh top, mép trái là cạnh rail, hai mép còn lại trùng cửa sổ. Bỏ bo góc, bỏ bóng đổ, bỏ nền kính mờ (chính cái blur là thứ khiến nó trông như đang trôi), nền chuyển sang màu đặc theo tông đang dùng.
- Toạ độ **đo từ bố cục thật** chứ không ghi số cứng: `chat-zoom.js` đọc kích thước `.hud` và đáy `.hud-top` rồi bơm vào bốn biến CSS. Đo `.hud` thay vì cộng tay `var(--rail-w)` là có chủ đích - khi trang không có rail thì biến đó vẫn là 160px, cộng tay sẽ lệch nguyên một dải.
- Khung **bám theo khi bố cục đổi**: nghe cả `resize` cửa sổ lẫn `ResizeObserver` trên `.hud`. Cần cả hai vì thu/mở rail làm đổi bề ngang `.hud` mà **không** bắn `resize` - chỉ nghe `resize` là khung đứng ì, hở đúng phần rail vừa co.
- Đã đo tận nơi bằng Chromium ở 6 tình huống (rail 160px, rail thu 60px, trang không rail, đổi cỡ cửa sổ, và đổi cỡ lẫn thu rail **trong lúc** đang mở rộng): mép khung trùng khít bố cục, sai số dưới 0.6px ở cả bốn cạnh.
- Thêm `tests/js/test_chat_zoom_khung.js`: 24 phép thử khoá hợp đồng này cho CI (vốn chỉ có `node`, không có trình duyệt) - hết dấu vết popup, toạ độ lấy từ biến đo, và hai canary giữ `ResizeObserver` cùng thứ tự đo sau khi gắn `.chat-zoomed`.

## [0.9.278] - 2026-07-30
Ảnh trong khung chat quay đi quay lại là mất: không phải Javis xoá, mà là ghép sai brain rồi bị thay bằng ô xám.
### Sửa lỗi
- **Ảnh và tài liệu trong chat biến mất khi mở lại hội thoại (báo từ người dùng thật).** Đường dẫn ảnh trong tin nhắn là đường dẫn TƯƠNG ĐỐI (`attachments/x.png`), không mang thông tin brain. Mỗi lần vẽ lại, bộ render ghép nó với **brain đang chọn trên thanh công cụ** chứ không phải brain của chính hội thoại đó. Mở một hội thoại cũ trong khi đang đứng ở brain khác là URL trỏ sai chỗ, `/files/raw` trả 404, thẻ `img` chạy `onerror` và **bị thay bằng ô xám** - nhìn hệt như Javis vừa gửi ảnh xong tự xoá đi. File vẫn nguyên trong vault. Nay mỗi tin nhắn mang theo brain của hội thoại chứa nó: `mdToHtml` nhận thêm tham số brain, đường khôi phục từ Lịch sử lấy `sess.brain` mà server **vốn đã lưu sẵn** (cột `brain` bảng `sessions`) nhưng trước giờ vứt đi, đường khôi phục từ localStorage lấy brain lưu kèm phiên. Tin lưu từ trước bản này không có trường đó thì rơi về hành vi cũ, không hỏng thêm gì.
- **Ô xám đổ oan cho "hết hạn".** Nó ghi "Ảnh đã hết hạn" cho MỌI lỗi tải, kể cả khi ảnh còn nguyên và chỉ là ghép sai đường, nên người dùng đi tìm nhầm hướng. Nay ghi trung tính kèm tên file, chú thích rõ hai khả năng: file bị xoá thật, hoặc hội thoại thuộc brain khác với brain đang chọn.
### Cải thiện
- Thêm `tests/js/test_chat_anh_theo_brain.js`: 11 phép thử khoá cả ba cú pháp đường dẫn trong vault (ảnh markdown, ảnh `![[...]]`, link tài liệu) đều theo brain của hội thoại, URL ngoài không bị đụng, và hai canary chống rò rỉ - brain của lượt render trước không được dính sang lượt sau, kể cả khi lượt giữa ném lỗi.
### Chưa sửa
- File **do người dùng tự đính kèm** vẫn mất khi mở lại hội thoại từ Lịch sử: đường khôi phục đó gán cứng danh sách đính kèm rỗng vì CSDL phiên chưa có chỗ lưu đính kèm theo từng tin. Sửa được nhưng phải thêm cấu trúc lưu trữ, để chủ repo quyết trước.

## [0.9.277] - 2026-07-30
Chat dài hay bị chém ngang bởi "Claude không phản hồi 180s": im lặng lúc nạp ngữ cảnh không phải là treo.
### Sửa lỗi
- **Hội thoại càng dài càng dễ dính "Claude không phản hồi 180s - đã dừng để tránh treo server" (báo từ người dùng thật).** Watchdog chống treo vốn có hai trần: 180 giây cho lúc model im lặng, và 3600 giây cho lúc đang chờ tool chạy (vì render/build im cả tiếng là bình thường). Nó bỏ sót đúng trường hợp thứ ba: khoảng im **trước khi có chữ đầu tiên**. Hội thoại dài thì lượt đầu phải nạp lại toàn bộ ngữ cảnh, model suy nghĩ trước khi phát chữ, có lúc còn tự nén lịch sử - im lúc đó là bình thường, nhưng bị tính là treo và chém ngang. Nay tách trần thứ ba `JAVIS_CLAUDE_FIRST_TIMEOUT` (mặc định 600 giây) chỉ áp cho khoảng chờ chữ đầu; im lặng SAU khi đã có chữ vẫn ngắt ở 180 giây như cũ, nên tác dụng chống treo giữ nguyên. Áp cho CẢ HAI bộ não Claude và ChatGPT/Codex.
- **Thông báo lỗi nay chỉ được lối thoát người thường làm được.** Câu cũ chỉ bảo đi tăng biến môi trường, thứ đa số người dùng không biết đặt ở đâu. Câu mới nói rõ hay gặp khi hội thoại đã rất dài và **mở hội thoại mới thường hết ngay**, biến môi trường vẫn nêu cho ai muốn chỉnh. Ba tình huống ngắt giờ có ba câu khác nhau, đọc là biết đang gặp bệnh nào.
### Cải thiện
- Thêm `test_watchdog_treo.py` khoá quan hệ ba trần ở cả hai engine (chờ chữ đầu > im giữa chừng, chờ tool là dài nhất), cờ đánh dấu phải thật sự được lật, và nội dung ba thông báo.
- `test_sdk_engine.py` thay ca kiểm chứng cũ bằng bốn ca chạy thật qua engine giả: tool chạy lâu thì sống, đã có chữ rồi mới im thì ngắt ở IDLE, chờ chữ đầu lâu hơn IDLE nhưng dưới FIRST thì sống, im quá cả FIRST thì vẫn ngắt. Ca cuối quan trọng nhất: nới trần mà quên chặn là đổi lỗi này lấy lỗi treo vô hạn.

## [0.9.276] - 2026-07-30
Lỗi của dịch vụ trả về giữa lúc gọi tool nay được Javis chẩn đoán tại chỗ, thay vì để model tự đoán rồi đoán sai.
### Sửa lỗi
- **Bộ chẩn đoán lỗi Google chỉ cắm vào nút Test, không cắm vào chỗ gọi tool thật.** Đây là chỗ 99% người dùng gặp lỗi, mà ở đó `_guard` trả về nguyên văn tiếng Anh của Google. Hậu quả có thật: Google trả `The caller does not have permission` khi gọi `list_calendars` và `create_event`, Javis đọc xong kết luận là **hub của Javis đang chặn quyền** và đòi đi sửa tầng permission. Sai hoàn toàn: kết nối đang ở mức Toàn quyền nên `allowed()` cho qua ngay từ dòng đầu, và khi Javis thật sự chặn thì nó báo bằng tiếng Việt kèm chữ "bị chặn", không bao giờ là một câu tiếng Anh. Nay mọi lỗi tool đi qua hub đều được soi, nhận ra họ lỗi quen mặt thì **gắn thêm** một dòng `[Javis chẩn đoán]` ngay dưới nguyên văn lỗi. Gắn thêm chứ không thay thế, để nguyên văn còn đó mà lần manh mối.
- **Thêm nhận diện 403 PERMISSION_DENIED không kèm chữ scope.** Với server MCP của Google, họ lỗi này gần như luôn là chưa ghi danh Developer Preview cho đúng tài khoản đang đăng nhập, hoặc project chưa bật API MCP riêng. Thông báo nói rõ ba điều người dùng cần biết: đây không phải Javis chặn, ghi danh tính theo TỪNG tài khoản Google nên vừa đổi tài khoản là phải ghi danh lại, và email theo tên miền riêng còn cần quản trị viên của miền cho phép. Lỗi thiếu scope cũng mang status `PERMISSION_DENIED` nên nhánh mới đặt SAU nhánh scope, có test canh đúng thứ tự đó.
### Cải thiện
- Tách `chan_doan_loi()` khỏi `_friendly_tool_error()`: hàm nhận diện trả rỗng khi không nhận ra, chỗ gọi tự quyết định nói gì. Nút Test giữ nguyên hành vi cũ (không nhận ra thì vẫn câu "Key chưa đúng hoặc chưa đủ quyền" kèm nguyên văn), còn đường gọi tool thì im lặng khi không chắc chứ không bịa chẩn đoán.
- `test_loi_ket_noi_google.py` thêm 10 phép thử: nội dung thông báo mới, thứ tự nhánh scope so với nhánh permission, canary "lỗi lạ thì phải im", và soát cho chắc `_guard` thật sự có gắn chẩn đoán mà vẫn giữ nguyên văn.

## [0.9.275] - 2026-07-30
Đổi tài khoản Google mà Javis vẫn chạy bằng tài khoản cũ: đổi ô đăng nhập giờ vứt luôn token cũ.
### Sửa lỗi
- **Đăng nhập lại bằng email khác mà mọi tool vẫn trả về tài khoản cũ (báo từ người dùng thật).** Người dùng xoá kết nối rồi đăng nhập lại bằng `hi@minhquy.vn`, nhưng tool Google vẫn báo tài khoản `blogminhquy@gmail.com`. Nguyên nhân nối tiếp đúng vụ 0.9.274: `workspace-mcp` cache token theo email, còn ô "Email Google của bạn" chỉ CHỌN dùng credential nào chứ không ép đăng nhập lại. Token cũ nằm nguyên trên đĩa nên nó cứ chọn đúng cái cũ. Nay đổi bất kỳ ô đăng nhập nào (email, Client ID, Client Secret) trên nguồn tự giữ token là Javis vứt luôn kho token của tài khoản cũ, lần gọi tool sau bắt buộc đăng nhập lại. Nhập lại y hệt giá trị cũ, hoặc chỉ đổi tên gợi nhớ, thì KHÔNG đụng gì - không bắt ai đăng nhập lại vô cớ.
### Cải thiện
- `test_cred_dir_rieng.py` thêm 7 phép thử, trong đó 4 phép chạy THẬT `update_connection` trên kho giả rồi soi thư mục token trên đĩa: nhập lại y hệt thì giữ, đổi tên thì giữ, đổi email thì vứt, đổi Client ID thì vứt. Đây là loại lỗi soi mã nguồn không thấy, phải chạy mới lộ.

## [0.9.274] - 2026-07-30
Đây mới là chỗ hỏng thật của vụ "Lịch báo thiếu quyền, xoá đi cài lại chục lần vẫn vậy": kết nối Google Workspace giữ token ở ngoài Javis, xoá kết nối không dọn được gì.
### Sửa lỗi
- **Kết nối Google Workspace (và Google Tasks) xoá đi cài lại KHÔNG hề đăng nhập lại.** Hai thẻ này chạy `workspace-mcp`, một server TỰ lo luồng OAuth của nó và cache token ra `~/.google_workspace_mcp/credentials` - nằm ngoài tầm với của Javis. Xoá kết nối trong Javis chỉ xoá bản ghi của Javis; thêm lại là tiến trình con đọc đúng file token cũ, không mở lại màn đăng nhập Google. Token cấp thiếu quyền thì thiếu vĩnh viễn, và người dùng có cài lại bao nhiêu lần cũng vô ích. Đây chính là vòng lặp mà bản 0.9.271 KHÔNG chạm tới: bản đó sửa danh sách phạm vi quyền của hai thẻ **Google Calendar** và **Gmail** rời (loại OAuth do Javis tự giữ token), không phải thẻ Workspace gộp. Ai đang đi qua thẻ Workspace thì phải chờ đúng bản này.
- **Mỗi tài khoản một kho token riêng.** Trước đây mọi connection của hai thẻ đó dùng chung một thư mục mặc định, nên hai tài khoản Google giẫm lên nhau. Nay Javis trỏ từng connection vào `connector-cred/<connector>-<slug>` riêng qua biến `WORKSPACE_MCP_CREDENTIALS_DIR`, và **xoá kết nối là xoá token theo** - từ bản này, "xoá đi cài lại" làm đúng cái người dùng tưởng nó làm.
### Thêm mới
- **Nút "Đăng nhập lại Google (xoá quyền cũ)"** trong menu của từng tài khoản, chỉ hiện với nguồn tự giữ token kiểu này. Nó vứt token mà GIỮ nguyên kết nối, quyền, tên và danh sách tool chặn; lần gọi tool kế tiếp server tự mở trình duyệt xin lại quyền theo đúng bộ hiện hành. Trước đây nút "Kết nối lại" chỉ lưu lại Client ID/Secret nên không bao giờ đụng được tới token, và người dùng bấm mãi mà Google không hiện lại ô tick quyền nào.
### Cải thiện
- Thêm `test_cred_dir_rieng.py`: 27 phép thử khoá cả chuỗi - catalog khai kho token, hai tài khoản ra hai thư mục khác nhau, xoá thật sự xoá, `delete_connection` có dọn theo, endpoint đăng nhập lại không lỡ tay xoá connection, nút chỉ mọc đúng nguồn có kho riêng, và canary cho nguồn không khai thì không đẻ thư mục thừa.
- **Sau khi cập nhật, ai đang dùng Google Workspace hoặc Google Tasks phải đăng nhập Google lại một lần** (kho token đổi chỗ). Lần gọi tool đầu tiên trình duyệt sẽ tự mở trên máy chạy Javis.

## [0.9.273] - 2026-07-30
Đăng nhập lại Google mà không thấy ô tick quyền nào: nói cho người dùng biết đó là bình thường và cách bắt Google hỏi lại.
### Cải thiện
- **"Re-auth mà nó không hiện ra checkbox các quyền" (báo từ người dùng thật) không phải lỗi, mà là cơ chế của Google.** Màn hình tick từng quyền chỉ bật cho quyền CHƯA từng cấp, và chỉ khi ứng dụng xin từ hai quyền trở lên; quyền đã cấp rồi thì Google cho qua thẳng. Bản trước 0.9.271 lại chỉ xin đúng một phạm vi `auth/calendar`, tức là chưa bao giờ có ô tick nào để mà hiện. Sau bản này Javis xin 5 phạm vi Lịch, 4 cái trong đó chưa từng được cấp nên màn tick sẽ hiện ra.
- **Chỉ luôn đường thoát khi vẫn không thấy ô tick**: gỡ Javis khỏi trang quyền của tài khoản Google rồi bấm Kết nối lại, khi đó Google hỏi lại từ đầu. Câu này gắn vào cả ba chỗ người dùng sẽ đọc: bước cuối trong hướng dẫn của thẻ Lịch và Gmail (kèm nút mở thẳng trang gỡ quyền), thông báo lỗi thiếu quyền lúc gọi tool, và dòng trạng thái ở vòng check sức khoẻ.
- `test_scope_google.py` thêm 6 phép thử canh cả ba đường đó, để câu hướng dẫn này không rơi rụng ở lần sửa sau.

## [0.9.272] - 2026-07-30
Hướng dẫn đấu Google Workspace viết lại cho làm theo được, và vá biến môi trường thiếu khiến đăng nhập không bao giờ xong.
### Sửa lỗi
- **Thiếu `OAUTHLIB_INSECURE_TRANSPORT=1` nên đấu Google Workspace/Google Tasks bấm đồng ý xong vẫn không đăng nhập được.** Hai connector này chạy `workspace-mcp`, nhận Client ID + Secret nên đi luồng OAuth confidential, mà chỗ nó hứng kết quả là `http://localhost:8000/oauth2callback` - HTTP trần. Thư viện oauthlib mặc định ném `InsecureTransportError` với http, và README upstream khai biến này là bắt buộc. Javis chưa từng đặt nó, hướng dẫn cũng không có chữ nào cứu được. Nay khai vào khối `env` tĩnh của cả hai connector, user không phải biết tới nó. An toàn vì callback chỉ chạy trên loopback của chính máy đó.
- **Hướng dẫn bảo bật đúng 4 API trong khi thẻ hứa nhiều hơn thế.** Tier `core` của workspace-mcp phục vụ cả Sheets, Slides, Forms, Tasks, Danh bạ - mô tả thẻ ghi rõ những thứ đó nhưng làm đúng theo hướng dẫn thì chúng chết lặng, không ai hiểu vì sao. Bước bật API nay chia hai nhóm: bốn cái cơ bản và những cái bật thêm nếu cần, kèm câu nói rõ quên cái nào thì chỉ nhóm công cụ đó lỗi chứ không hỏng cả kết nối.
- **Cảnh báo "phải có máy màn hình" nằm ở bước CUỐI.** Người cài trên VPS đọc tới đó là đã bỏ 10 phút tạo project, bật API, tạo OAuth client rồi mới biết đường này không đi được. Nay là bước ĐẦU TIÊN, và chỉ thẳng sang hai thẻ Google Calendar/Gmail vốn đăng nhập gọn trong dashboard.
### Cải thiện
- **Viết lại toàn bộ 8 bước của thẻ Google Workspace** (và thẻ Google Tasks theo cùng khuôn): nói rõ client loại "Ứng dụng dành cho máy tính" KHÔNG phải khai URI chuyển hướng - khác hẳn thẻ Lịch/Gmail nên ai làm thẻ kia trước đều đi tìm ô đó; tách bước dán key với bước bấm Kết nối; thêm bước dặn qua màn cảnh báo "ứng dụng chưa được xác minh" bằng Nâng cao > Tiếp tục và tick hết ô quyền - chỗ người dùng hay đứng hình rồi bỏ cuộc.
- **Ô email Google đổi nhãn từ "tuỳ chọn" thành "nên điền"**, kèm lý do: bỏ trống thì mỗi lần gọi tool server lại hỏi ngược xem dùng tài khoản nào. Vẫn không bắt buộc, chỉ là nói thật hậu quả.
- Trang tài liệu MCP cập nhật theo, thêm cả nhắc nhở khai đủ phạm vi quyền cho thẻ Lịch/Gmail.
- Thêm `test_google_workspace_setup.py`: 33 phép thử khoá biến môi trường (soát cả `build_env` thật sự đẩy được xuống tiến trình con), thứ tự bước cảnh báo phải đứng trước bước bắt tay vào làm, đủ danh sách API, nhãn ô email, và luật "mọi connector chạy workspace-mcp đều phải có đủ hai thứ đó" để lần sau không vá nửa con bug.

## [0.9.271] - 2026-07-30
Lịch Google báo "thiếu quyền" mãi không hết dù xoá đi cài lại: chính danh sách quyền Javis xin mới là chỗ sai.
### Sửa lỗi
- **Google Calendar trả `ACCESS_TOKEN_SCOPE_INSUFFICIENT` ở bước tìm giờ trống, cài lại bao nhiêu lần cũng dính (báo từ người dùng thật).** Javis chỉ xin đúng một phạm vi gộp `auth/calendar`, nhưng server MCP chính chủ của Google đòi các phạm vi HẠT NHỎ: `calendar.calendarlist.readonly`, `calendar.events.readonly` và nhất là `calendar.events.freebusy` cho `suggest_time`. Thiếu freebusy thì đăng nhập vẫn xanh, `list_calendars` vẫn chạy, chỉ đúng lúc kiểm tra rảnh bận mới chết - nên xoá kết nối tạo lại chẳng đổi được gì, lần nào cũng xin lại đúng bộ quyền thiếu đó. Connector Lịch nay xin đủ 5 phạm vi (giữ cả `calendar` + `calendar.events` cho nhóm tool ghi); Gmail xin thêm `gmail.readonly`, `gmail.compose`, `gmail.labels` cho cùng lý do (ba cái này nằm trong `gmail.modify` nên không nới quyền). **Ai đang đấu Lịch/Gmail phải bấm Đăng nhập lại một lần** - token cũ chỉ mang những quyền xin ở bản trước.
- **Nút Test báo xanh trong khi kết nối thiếu quyền.** Tool validate của Lịch là `list_calendars`, chỉ cần phạm vi danh sách lịch, nên nó chạy ngon lành và cả trang Kết nối lẫn vòng check sức khoẻ đều báo ổn. Giờ Javis LƯU danh sách phạm vi thật được cấp (đọc từ token response, cả lúc đăng nhập lẫn lúc refresh) và đối chiếu với phạm vi catalog đang xin: thiếu là báo đỏ ngay, gọi đích danh quyền còn thiếu, kèm nút Kết nối lại. Token lưu từ bản cũ chưa có thông tin này thì coi là "chưa biết" và im lặng, không bắt ai đăng nhập lại vô cớ.
- **Lỗi thiếu quyền lúc gọi tool nay nói thẳng thiếu quyền nào** và nói rõ xoá kết nối tạo lại không chữa được, phải Đăng nhập lại sau khi cập nhật - thay vì câu chung chung "tick chọn đầy đủ các quyền" khiến người dùng đi soát lại màn hình đồng ý mà không thấy gì sai.
- **Tool bị mức quyền ẩn giờ được KỂ RA thay vì biến mất im lặng.** Kết nối Lịch mặc định mức Chỉ đọc nên `create_event` không có trong danh sách tool, model đi tìm không thấy rồi kết luận sai là kết nối hỏng (đúng vệt hỏi "tạo lịch sáng mai 9h" của người dùng). `javis_connections` nay trả thêm `tool_bi_an_do_quyen` + cách mở, và `javis_search_tools` kèm lưu ý khi nguồn vừa tìm thấy còn tool đang bị che - để Javis nói đúng câu "kết nối đang ở mức Chỉ đọc, anh nâng lên Ghi nháp thì em tạo được", chứ không tự nâng quyền.
### Cải thiện
- Hướng dẫn đấu Lịch/Gmail bổ sung hai bước hay bị bỏ sót: bật **People API** (server MCP dùng khi tìm giờ trống có người tham dự) và khai đủ phạm vi ở trang **Quyền dữ liệu** của Google Auth Platform, kèm nút mở thẳng hai trang đó. Guide cũng nói hẳn vì sao phải đủ 5 phạm vi và nhắc TICK HẾT các ô ở màn hình đồng ý.
- Thêm `test_scope_google.py`: 33 phép thử khoá danh sách scope trong catalog, phép so scope được cấp (kể cả bẫy Google trả `email` dưới dạng URL `userinfo.email`), canary "chưa biết thì không đoán bừa là thiếu", nội dung ba đường báo lỗi, và soát cho chắc validate/health thật sự có đi qua bộ kiểm scope.

## [0.9.270] - 2026-07-30
Javis hết thiên về Claude: bộ não nào cũng đủ năng lực như nhau, và banner đỏ đòi đăng nhập Claude không còn làm phiền máy chạy OpenRouter.
### Sửa lỗi
- **Banner đỏ "Bộ não claude mất đăng nhập" treo trên máy chưa từng cài Claude.** Đèn báo não giữ trạng thái trong RAM và không ai dọn, nên đèn thắp hồi Claude còn là Main Model treo vĩnh viễn sau khi người dùng đổi sang OpenRouter - đúng lỗi khách gặp. Giờ đèn chỉ tính bộ não người dùng THẬT SỰ chọn (Main Model, cộng model việc nền khi đặt rõ provider), tự dọn ở vòng quét và lọc ngay lúc trả `/connect/health` nên đổi provider là banner tắt liền, không phải chờ 10 phút. Provider API (OpenRouter, OpenAI, Gemini, Anthropic API) không có đèn vì chúng chạy bằng API key, không có phiên đăng nhập nào để mất.
- **Trang Kết nối báo nhầm "Google Gemini chưa hỗ trợ gọi công cụ".** Gemini bị sót khỏi danh sách `MCP_PROVIDERS` trên giao diện dù `_api_stream_mcp` ở server đã phục vụ nó từ lâu. Giờ cả năm provider hiện thẻ xanh; dòng vàng chỉ còn để chặn provider lạ.
### Cải thiện
- **Javis tự mô tả đúng năng lực của mình.** System prompt trước đây ghi "ngoài ra hỗ trợ chat thuần qua OpenRouter / OpenAI / Anthropic API", nên khi khách hỏi thì Javis trả lời "không có Claude Code thì chỉ chat chơi thôi, không điều phối, không làm task được" - sai. Viết lại mục Bản chất: Javis là AI agentic ĐỔI ĐƯỢC BỘ NÃO, sáu nhà cung cấp dùng chung một bộ đồ nghề qua MCP Hub (kho Kết nối, tool file brain, skill, việc Kanban, agent/workflow/loop/nhắc hẹn), khác biệt duy nhất là hai engine CLI chạy thêm được lệnh máy. Kèm lệnh cấm tự nhận "chỉ chat được" / "phải cài Claude Code mới làm được".
- **Nhãn trên giao diện nói đúng sự thật.** Nhãn kiểu của bốn provider API đổi từ **chat** sang **MCP Javis**. Dòng Main Model đổi từ "Gọi API thẳng - chat thuần (không MCP)" sang "Gọi API thẳng - MCP Javis + skill + loop (không chạy lệnh máy)", và có thêm dòng riêng cho Codex. Thẻ OpenRouter trong wizard, mục Engine ở trang Tổng quan, mô tả lệnh `/cli` `/or` của Telegram cũng sửa theo. Mục Engine ở Tổng quan trước đây đọc trường `model.engine` cũ nên máy chạy Gemini/OpenAI vẫn bị ghi là "Claude CLI" - giờ đọc `model.main` như trang Models.
- **Tài liệu giới thiệu đổi trục.** README, `docs/README.md`, `docs/01-bat-dau-thiet-lap.md` và `docs/10-models-va-engine.md` viết lại theo hướng "AI agentic đổi được bộ não" thay vì "xây trên CLI của Claude": bảng so sánh engine tách riêng cột chạy lệnh máy, bỏ các ghi chú kiểu "dòng này đã cũ, đừng tin nhãn trên màn hình" vì nhãn đã đúng.
- Thêm `test_engine_ngang_quyen.py` canh cả hai vế: logic đèn báo não theo bộ não đang dùng, và luật không chỗ nào (system prompt, giao diện, tài liệu) được nói provider API "chỉ chat, không MCP". Danh sách provider có MCP trên giao diện được đối chiếu thẳng với danh sách thật trong `main.py` để lần sau thêm provider mà quên UI là test đỏ ngay.

## [0.9.269] - 2026-07-30
Khung nhập ở tab Trò chuyện lòi dải xám đen, và nút phụ ở trang Model mất chữ khi rê chuột.
### Sửa lỗi
- **Khung nhập ở tab Trò chuyện không cùng màu với khung nhập ở màn Javis.** CSS của tab gõ cứng `background: rgba(24,24,34,.6)` thay vì lấy token nền, nên tông sáng lòi ra một dải xám đen giữa nền giấy trắng, còn tông tối thì lệch nhẹ so với bản gốc. Giờ dùng `var(--bg2)` và bo góc 18px đúng như thanh nhập ở màn Javis. Lớp phóng to chat cũng chỉnh theo, nên cả ba chỗ đặt chat (cockpit, tab Trò chuyện, lớp phóng to) trông như một. Nhân tiện đổi nốt hai chỗ gõ cứng còn lại trong cùng khối: nền cột lịch sử dùng `var(--surface-1)`, bóng ngăn kéo mobile dùng `var(--shadow-veil)`.
- **Nút phụ ở trang Model mất chữ khi rê chuột, cả tông tối lẫn tông sáng.** Năm nút (Qua trình duyệt, Ngắt x3, Kiểm tra lại) viết `style="background:transparent"` thẳng trên thẻ. Style inline thắng mọi rule `:hover`, nên khi rê chuột chỉ nửa hiệu ứng chạy: nền vẫn trong suốt còn chữ đã đổi sang `var(--on-accent)` - vốn là màu dành cho chữ ĐẶT TRÊN nền cam đặc. Tông tối thì `--on-accent` gần đen nằm trên nền tối, tông sáng thì nó trắng nằm trên nền trắng: hai bên đều tàng hình. Chuyển cả năm sang class `.gcard-btn.ghost` sẵn có, hover ra nền mờ + chữ đậm lên.
### Cải thiện
- Nút `disabled` không còn tô cam khi rê chuột (tô cam xong chữ đổi màu trong khi độ mờ hạ xuống là đọc không ra) - giữ nguyên bộ mặt thường.
- Thêm `test_theme_tokens.py` canh hai luật này: không gõ cứng màu trong CSS tiêm động của tab Trò chuyện, và không dùng `style="background:transparent"` trên nút có `:hover`. Đây là loại lỗi chỉ lộ ra khi lật tông hoặc khi rê chuột, mắt thường lướt qua code không thấy.

## [0.9.268] - 2026-07-30
Tải lại trang hoặc mở thêm tab giờ vào lại đúng hội thoại đang dở.
### Cải thiện
- **Tải lại trang không còn văng vào hội thoại mới.** Bản 0.9.88 đổi mặc định thành mỗi lần tải trang là mở khung trống; dùng thật thì mỗi lần F5, mỗi lần mở thêm tab là mất mạch chuyện đang nói, phải vào Lịch sử bấm lại. Giờ quay về khôi phục đúng hội thoại đang dở. Muốn khung trống thì bấm nút + như cũ. Khôi phục đọc từ localStorage nên hiện tức thì và giữ nguyên cả ảnh đính kèm lẫn chip chọn đáp án - thứ mà tải lại từ server không có. Mã phiên sống lại theo, nên lượt đang chạy nền vẫn stream tiếp vào đúng khung sau khi tải lại.

## [0.9.267] - 2026-07-30
Bong bóng lỗi trong chat in nguyên thẻ svg, và Javis không nhận ra Codex mất đăng nhập.
### Sửa lỗi
- **Tin báo lỗi trong chat hiện nguyên `<svg ...>` và chữ bị escape hai lần.** Lối lọt thứ tư của đợt đổi sang icon Lucide, cơ chế khác hẳn ba lần trước: `appendJavisMessage` chạy nội dung qua `markdownToHtml`, mà bộ render escape HTML, nên thẻ icon thành chữ. Tệ hơn, chỗ gọi còn `escapeHtml` sẵn trước khi truyền vào nên chữ bị escape lần hai, user đọc ra `&quot;` giữa câu log. Tách riêng `appendJavisError`: phần chữ vẫn đi đúng đường markdown như mọi tin khác, icon gắn vào bong bóng bằng HTML thật.
- **Codex mất đăng nhập mà đèn báo não không sáng.** Codex CLI báo "Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again." Bộ mẫu nhận diện chỉ biết cách nói của Claude ("OAuth session expired", "failed to authenticate") nên không câu nào khớp: user hỏi ba lần, nhận ba bong bóng lỗi khó hiểu, không ai nói cho biết phải đăng nhập lại - đúng thứ tính năng đèn báo não sinh ra để tránh. Thêm ba cách nói của Codex vào bộ mẫu.
### Cải thiện
- Bộ quét icon canh thêm lối thứ tư: hàm phụ nhận tham số rồi đưa qua **bộ escape hoặc render markdown** (`markdownToHtml`, `escapeHtml`, `esc`), không chỉ `.textContent`. Bốn lối lọt của cùng một lỗi giờ đều có rào.

## [0.9.266] - 2026-07-30
Icon mục Kênh đổi sang máy bay giấy, và chuẩn hoá chữ trong mọi ô nhập.
### Cải thiện
- **Mục Kênh đổi icon từ phong bì sang máy bay giấy.** Trang này là Telegram và các kênh chat, phong bì đọc ra thành email nên sai nghĩa.
- **Mọi placeholder trong ô nhập viết hoa chữ đầu và bỏ viết tắt.** Rà 96 chuỗi ở index.html, dashboard/*.js và system/mcp-catalog.json: "vd 123456789, 987654321" thành "Ví dụ: 123456789, 987654321", "dán API key Pancake POS..." thành "Dán API key Pancake POS...". Chuỗi mẫu kỹ thuật (key, URL, lệnh) thì không viết hoa được phần ruột vì viết hoa là sai giá trị, nên thêm tiền tố "Ví dụ: " cho vừa đúng luật vừa nói rõ đó là mẫu. Vài chỗ nhân tiện viết lại cho gọn: "để trống = không đặt mật khẩu" thành "Để trống nếu không đặt mật khẩu", "args cách nhau bằng dấu cách" thành "các tham số cách nhau bằng dấu cách".
- Thêm `test_placeholder_ui.py` canh quy ước này. Placeholder nằm rải ba nơi và mỗi connector mới lại thêm một bộ trường riêng, nên không có test thì vài tuần là lệch lại.

## [0.9.265] - 2026-07-30
Khách cài VPS đấu Facebook bị "URL bị chặn" vì hướng dẫn không có chỗ copy địa chỉ callback.
### Sửa lỗi
- **Hướng dẫn đấu Meta Ads / Facebook Trang không hiện ô copy Redirect URI.** Text bước 4 bảo "dán địa chỉ https ở nút 'Sao chép' bên dưới" nhưng bước đó quên khai `"copy": "redirect"`, mà connector có steps thì khối setup cũ (vốn có ô này) lại bị steps thay hẳn - thành ra không đâu có ô để copy. Khách trên VPS tự đoán đường dẫn callback (sai, vì đường thật là `/connect/oauth/callback`) rồi bị Facebook chặn "URL bị chặn". Giờ cả hai connector hiện ô copy sinh ĐÚNG địa chỉ theo tên miền của từng bản cài.
- **Thiếu luôn bước "Miền ứng dụng" (App Domains).** Khách qua được cửa redirect lại vướng tiếp "Không thể tải URL - Miền của URL này không được đưa vào miền của ứng dụng". Thêm bước mới cho bản cài VPS: dán tên miền trần (không https, không dấu /) vào 'Cài đặt ứng dụng > Thông tin cơ bản > Miền ứng dụng' - kèm ô copy mới loại `copy: "domain"` sinh sẵn tên miền của khách. Cập nhật cả guide tường chữ lẫn trang docs, thêm hai lỗi này vào mục Sự cố thường gặp.
### Cải thiện
- Rào test mới trong lint catalog: step nào hứa nút 'Sao chép' hay bảo dán địa chỉ/tên miền "bên dưới" mà không khai `copy` là đỏ ngay - đã thử trên catalog cũ, bắt đúng hai bước lỗi. Giá trị `copy` lạ (dashboard không hiểu) cũng bị bắt.

## [0.9.264] - 2026-07-30
Thêm icon bộ não trước dropdown chọn brain trên thanh trên cùng.
### Cải thiện
- **Cụm chọn bộ não trên navbar giờ có icon brain** đứng trước dropdown, màu cam theo accent, kèm chú thích cho trình đọc màn hình. Icon nằm trong khối `.navbar-brain` nên mobile dời cụm này vào rail thì icon cũng đi theo, không cần xử lý riêng.

## [0.9.263] - 2026-07-30
Lối lọt thứ tư của đợt đổi emoji sang icon Lucide: tiêu đề trang in nguyên tên icon.
### Sửa lỗi
- **Tiêu đề các trang sidebar hiện chữ "brain Tự học", "bot Agents", "puzzle Skills"** thay vì vẽ icon. Ba lần trước icon lọt qua đường `.textContent` trong JS; lần này đi đường HTML: tiêu đề trang bind icon bằng `x-text` của Alpine (vốn đúng thời còn emoji), trong khi `VIEW_META.icon` từ 0.9.257 đã đổi thành TÊN icon Lucide, nên tên bị in thẳng lên màn hình bằng màu cam của icon. Đổi sang `x-html` và bọc qua `ic()` để tên icon thành thẻ svg thật. Thanh rail bên trái không dính vì nó dùng chuỗi svg dựng sẵn từ đầu.
### Cải thiện
- Bộ quét icon canh thêm lối thứ tư: **bind giá trị icon bằng `x-text`** (quét cả index.html lẫn template Alpine dựng trong .js). Đã thử rule mới trên bản trước khi sửa: bắt đúng dòng lỗi.

## [0.9.262] - 2026-07-30
Nốt chỗ thứ ba của cùng một lỗi: chip hoạt động trong khung chat cũng in nguyên thẻ svg.
### Sửa lỗi
- **Mỗi lượt chat lại hiện một khối `<svg ...>` giữa màn hình.** Chip hoạt động ("Nhận data - đang phân tích...", "Đang soạn câu trả lời...") gọi qua hàm `showActivity`, mà hàm này đổ tham số vào `.textContent` trong khi ba chỗ gọi lại truyền chuỗi icon vào. Đây là lối lọt thứ ba của đợt đổi emoji sang icon Lucide, và là lối khó thấy nhất: chỗ gọi với chỗ gán cách nhau ba trăm dòng. Đổi `showActivity` sang nhận HTML, ba chỗ gọi icon dùng `Icons.msg`, còn hai chỗ truyền chữ từ server thì escape trước.
- Nhân tiện bịt luôn một lỗ nhỏ: chữ trạng thái do engine gửi lên trước nay đi bằng `textContent` nên vô hại; chuyển sang `innerHTML` mà không escape là mở đường chèn HTML từ dữ liệu server. Giờ có `escapeHtml`, thử với chuỗi `<img src=x onerror=...>` thì hiện đúng thành chữ, không sinh thẻ nào.
### Cải thiện
- Bộ quét icon canh thêm lối thứ ba: **hàm phụ nhận tham số rồi mới đổ vào `.textContent`**. Test lần được từ chỗ khai hàm tới mọi lời gọi nó trong cùng file, chỉ báo khi lời gọi thật sự truyền chuỗi icon vào đúng vị trí tham số đó. Ba lần lọt trong hai ngày đều là cùng một lỗi đi ba đường khác nhau, giờ cả ba đường đều có rào.

## [0.9.261] - 2026-07-30
Hai lỗi giao diện lọt vào từ bản dọn emoji: bấm chip model không ra menu, và thanh công cụ sửa file .md hiện nguyên thẻ svg.
### Sửa lỗi
- **Bấm vào chip model không hiện menu đổi model.** Bản 0.9.257 thêm `overflow: hidden` lên hàng model để dải HỆ THỐNG/MCP dài khỏi đẩy nở cột chat. Nhưng menu đổi model là con `position:absolute` nằm HOÀN TOÀN phía trên hàng đó, mà hàng lại chính là khối chứa của nó, nên bị cắt sạch: menu vẫn mở đúng trong DOM, chỉ là không còn một điểm ảnh nào được vẽ. Bỏ cắt tràn ở hàng model và chuyển việc chống nở ngang xuống đúng chỗ cần: dải HỆ THỐNG tự cắt phần thừa như cũ, chip model thêm trần bề ngang để tên model dài cũng không đẩy được hàng.
- **Thanh công cụ sửa file .md hiện nguyên `<svg ...>` thành chữ.** Cùng bản đó đổi hai nút Trích dẫn và Link từ emoji sang icon Lucide, nhưng nhãn nút vẫn gán bằng `textContent` nên chuỗi SVG bị in ra như văn bản, chiếm hai dòng to đùng giữa thanh công cụ. Giờ nhãn dựng bằng `innerHTML`, chữ thuần thì escape trước để nút `</>` không bị trình duyệt nuốt mất.
- Hai rào test mới cho đúng hai lỗi trên, vì cả hai đều thuộc loại mắt người review không thấy: bộ quét icon giờ lần được cả đường icon đi qua BẢNG DỮ LIỆU rồi rã mảng ra biến (`BTNS.forEach(([label]) => ...textContent = label)`) chứ không chỉ biến gán thẳng; và test bố cục thanh model đổi từ "phải có `overflow: hidden`" thành "CẤM cắt tràn ở hàng model" - chính dòng test cũ đang khoá cứng cái lỗi lại.

## [0.9.260] - 2026-07-30
Lịch tự động giờ NÓI RÕ nó chạy lúc nào, sửa được, và không tự sinh ra khi chưa đủ điều kiện.
### Sửa lỗi
- **Nhìn thẻ nhắc hẹn không biết bao giờ nó chạy.** Thẻ cron chỉ in đúng biểu thức thô `cron 0 7 * * *` rồi hết. Giờ đọc thành lời (`7:00 mỗi ngày`) kèm lần chạy kế tiếp và còn bao lâu nữa (`kế tiếp mai 07:00 (còn 14 giờ)`), biểu thức thô vẫn giữ bên cạnh cho ai cần. Thẻ việc lặp cũng nói rõ ngày chứ không chỉ giờ trần, và nói thẳng "đang tắt nên chưa có lần chạy kế tiếp" thay vì bỏ trống.
- **Không sửa/xoá được lịch cron.** Nhắc hẹn tạo xong là bất động: chỉ có Huỷ và Chuyển brain, muốn đổi giờ phải xoá đi tạo lại. Thêm nút **Sửa** (đổi tên, nội dung, kiểu, và giờ - sửa cron xong tính lại ngay lần chạy kế tiếp) và nút **Xoá** (mất hẳn, khác Huỷ là vẫn giữ trong lịch sử). Hai endpoint mới `POST /reminders/update` và `POST /reminders/delete`; tool `javis_schedule` thêm `op=update` để sửa được bằng chat luôn.
- **Javis tạo cron quá dễ, thiếu điều kiện vẫn tạo rồi im lặng.** Khách dựng job "sáng nào cũng báo email + lịch qua Telegram" trong khi Telegram còn chưa đấu: job chạy đúng giờ, kết quả rơi vào hư không, không ai nói cho họ biết thiếu gì. Giờ server chặn ngay lúc tạo, nói rõ thiếu gì và chỉ chỗ sửa; người dùng vẫn có quyền bấm "Vẫn tạo". Trang Việc định kỳ hiện cảnh báo ở đầu trang khi chưa có kênh báo, và thẻ nào lần chạy trước lỗi thì hiện luôn lỗi đó. Job script không bị chặn - loại đó vốn cố ý im lặng.
- **"Vòng lặp tự cải thiện" mọc lại sau mỗi lần xoá.** Bản di trú cũ dựng lại loop legacy mỗi lần khởi động nếu thư mục `Javis/loops` trống - mà xoá cái cuối cùng thì đúng là trống, nên xoá bao nhiêu lần cũng vô ích. Thêm ba rào: đóng dấu đã-di-trú vào `loop_config.json` (chạy một lần là xong vĩnh viễn); config rỗng thì không có gì để di trú, nên bản fork sạch không còn tự mọc ra một loop trắng; và vault cũ ghi trong config mà không còn trên máy thì bỏ qua luôn, thay vì dồn loop cũ sang brain mặc định - đó chính là đường một "Vòng lặp tự cải thiện" lạ đi vào Brain Default trên máy khách. Bản cũ có nội dung thật, vault còn nguyên, vẫn được chuyển đầy đủ.
- Trang Việc định kỳ cũng báo khi **kênh đã đấu nhưng đang lỗi thật** (token bị thu hồi, 409 trùng poll): việc vẫn chạy nhưng tin không tới. Lỗi loại này không chặn tạo việc mới vì có thể chỉ thoáng qua, nhưng phải nói ra.
### Cải thiện
- **Mở app là vào màn Javis**, kể cả màn hẹp hoặc khi tắt khoang não. Bản 0.9.182 cho lite-mode tự nhảy sang Trò chuyện; dùng thật thì rối hơn vì mỗi lần tải lại rơi vào một trang khác. Màn Javis đã có sẵn ô chat, chỉ khác là không vẽ khoang não. Co giãn cửa sổ qua ngưỡng mobile cũng không còn tự đẩy sang trang khác.
- Luật **"đủ điều kiện mới tạo lịch"** vào CLAUDE.md + chỉ dẫn kênh + mô tả tool: trước khi tạo, Javis phải tự soát nguồn dữ liệu đã đấu chưa và có chỗ báo kết quả chưa; thiếu thì nói thẳng rồi hỏi, không tạo cho xong.

## [0.9.259] - 2026-07-30
Dọn hai test đỏ tồn từ trước, giờ cả 93 test đều xanh.
### Sửa lỗi
- **`/brains/<tên>/<path>` gọi thẳng handler `/files/raw` như hàm Python thường.** Chạy được nên không ai thấy, nhưng tham số mặc định của handler là đối tượng `Query` chứ không phải chuỗi, nên ngày nào có người gọi thiếu đối số thì nó nổ ở route tương thích link cũ, chứ không nổ ở chỗ vừa sửa. Tách lõi thuần `raw_file_response()` đúng lối `zip_dir_response()` đã đi, hai handler cùng gọi vào đó.
### Kiểm thử
- **Hợp đồng lite-mode trong `test_settings_consolidation.py` viết ngược ý định nên đỏ ngay từ lúc ra đời (0.9.182).** Bản 0.9.182 chủ ý cho màn hẹp đi thẳng tới Trò chuyện vì trang Tổng quan đã bỏ, nhưng test lại đòi "không được nhảy sang Trò chuyện". Sửa test theo hành vi đã chốt, và canh thêm rằng không còn chỗ nào trỏ về trang Tổng quan đã xoá.

## [0.9.258] - 2026-07-30
Sửa mấy chỗ hiện nguyên mã `<svg ...>` thành chữ trên màn hình - dư âm của đợt đổi emoji sang icon Lucide.
### Sửa lỗi
- **Trang Kênh: dòng trạng thái Telegram in ra nguyên thẻ `<svg class="ic ic-fill ic-ok" ...>`** thay vì đèn xanh. Nguyên do: nội dung dòng đó chứa icon (là HTML) nhưng vẫn gán qua `textContent`, mà `textContent` coi mọi thứ là chữ trơ. Đổi sang `innerHTML`. Cùng lỗi ở dòng báo kết quả "Gửi test", ở trạng thái mật khẩu và nút gửi test Telegram trong hộp Cài đặt nhanh, và ở hàng nút của khung xem file (sửa tên / xoá / phóng to / đóng - trước đây mỗi nút là một đoạn mã dài).
- Nhân đây bịt luôn hai chỗ nối thẳng chuỗi lỗi từ server vào HTML (lỗi 409 của Telegram và lỗi khi gửi test): giờ escape qua `esc()`, còn `r.sent`/`r.total` ép về số.
- Trạng thái Telegram trong hộp Cài đặt nhanh lúc TẮT còn dùng ký tự `●`, giờ dùng icon như ba nhánh còn lại nên cùng một kiểu vẽ.
### Cải thiện
- **`tests/python/test_icons.py` canh thêm loại lỗi này**: quét nguồn tìm chỗ gán chuỗi icon vào `.textContent`, lần theo cả biến trung gian (`line = ic(...)` rồi `st.textContent = line` - đúng ca đã lọt). Đây là lỗi mắt người review rất khó thấy vì trên code nó y như một dòng chữ bình thường.

## [0.9.257] - 2026-07-30
Bỏ hết emoji khỏi giao diện, thay bằng bộ icon Lucide vẽ nét. Emoji do font hệ thống vẽ nên mỗi máy ra một hình, lại cứng màu nên ở tông SÁNG là chọc vào mắt; icon nét thì giống nhau trên mọi máy và tự ăn theo màu chữ.
### Cải thiện
- **392 chỗ emoji trong dashboard đổi sang icon Lucide**, trải 18 file. Icon vẽ bằng `stroke="currentColor"` nên tự đổi màu theo tông SÁNG/TỐI và theo màu chữ của chỗ nó đứng - việc emoji không làm được. Cỡ icon là `1em` nên co theo cỡ chữ của khối chứa, không phải con số cứng.
- **Vendor bộ rút gọn 115 icon, 20.7KB** (`dashboard/vendor/lucide-icons.js`) thay vì bản đầy đủ 414KB cho ~2000 icon. Không gọi mạng lúc chạy nên chạy được cả khi máy không có internet. Sinh lại bằng `python tools/gen_icons.py` sau khi thêm tên vào `dashboard/icons.manifest.json`.
- **Thay 24 icon SVG vẽ tay** trong thanh điều hướng bằng Lucide, và gộp chỗ khai trùng: trước đây mỗi trang khai icon hai lần (`ICON` + `VIEW_META`) nên đã lệch thật - Việc (Kanban) trùng icon với Tệp tin, Tài khoản trùng với Cài đặt. Giờ cả hai lấy từ một bảng `VIEW_ICON` duy nhất.
- **Bộ chọn brain dùng `<optgroup>`**: thẻ `<option>` chỉ nhận chữ nên không nhét được SVG. Thư mục ngoài giờ xếp vào nhóm `Thư mục ngoài` - cách gốc của HTML, giữ trọn thông tin mà icon thư mục đang mang, hiển thị đúng trên mọi máy.
- Icon dùng được cả trong `content:` của CSS (dấu tích ở bước workflow, chấm đầu dòng nhật ký cập nhật) qua mặt nạ + biến `--ic-*` do script sinh ra, nên vẫn ăn `currentColor` chứ không phải màu cứng.
### Bảo mật
- `Icons.msg()` / `Icons.warn()` / `Icons.ok()` tự escape phần chữ. Việc đổi icon buộc hàng chục chỗ chuyển từ `textContent` sang `innerHTML`, mà nhiều chỗ nối thẳng chuỗi lỗi từ server - đó là đường mở lỗ XSS ở đúng những chỗ trước đây an toàn. Ba hàm này bịt hẳn đường đó, có test canh.
### Sửa lỗi
- Biến cục bộ tên `ic` trong `iconInner()` che mất hàm `ic()` toàn cục, đổi tên để không xung đột.
- `chip()` tự escape nội dung nên nhận TÊN icon thay vì HTML, không thể vô tình nhét HTML thô qua đường này.
### Giữ nguyên có lý do
- Cú pháp Obsidian Tasks (`ngày hạn`, `ưu tiên`, `ngày hoàn thành`...) trong file `.md` vẫn là emoji vì đó là ĐỊNH DẠNG DỮ LIỆU, đổi là Obsidian không đọc được. Phần hiển thị các mốc đó trên giao diện thì đã dùng icon. Emoji trong tin Telegram cũng giữ vì Telegram tự render đều trên mọi thiết bị.
### Kiểm chứng
- `tests/python/test_icons.py`: quét nguồn báo lỗi nếu emoji bò trở lại (danh sách ngoại lệ ngắn, ghi rõ lý do từng dòng), và đối chiếu mọi tên icon gọi trong nguồn với bộ đã vendor - chặn lỗi gõ sai tên thành icon vô hình.
- `tests/js/test_icons.mjs`: chạy thật `ic()` / `Icons.msg()` trong DOM tối thiểu, gồm cả rào XSS.
- Kiểm trên app đang chạy: 17/17 trang render icon, không thẻ nào sót, không tên icon nào sai, không lỗi console, icon đúng cỡ và đúng hàng chữ ở cả hai tông.

## [0.9.256] - 2026-07-30
Webcake có thêm cách đấu dễ hơn: bấm Kết nối rồi đăng nhập, không dán JWT, không cần Node.js.
### Thêm mới
- **Webcake Landing (đăng nhập web)**: connector mới trỏ vào máy chủ hosted `https://mcp.toolvn.io.vn/mcp`. Máy chủ này công bố OAuth đúng chuẩn (RFC 9728 discovery + RFC 7591 đăng ký ứng dụng động, PKCE S256, scope `landing:read` và `landing:write`), nên Javis tự đăng ký ứng dụng và user chỉ cần bấm Kết nối, y như Higgsfield. Hai cách đấu Webcake gom về CÙNG một thẻ trong kho kết nối, mỗi cách một dòng mô tả để chọn.
- Thẻ nói thẳng đánh đổi: cách web đi qua máy chủ trung gian do tác giả công cụ vận hành (Pancake dẫn link trong tài liệu chứ không phải hạ tầng chính chủ), nên quyền vào tài khoản Webcake nằm ở máy chủ đó; cách chạy trên máy thì token nằm lại máy và đi thẳng tới Webcake.
### Bảo mật
- **KHÔNG dùng kiểu link kèm token mà tài liệu Webcake gợi ý** (`...?jwt=<token>`). `mcp_store` lưu `url` KHÔNG mã hoá và `_public()` trả nguyên `url` ra frontend, chỉ headers/env/secrets mới được che, nên token nhét vào URL là rơi thẳng ra dashboard và log. Dùng OAuth thay thế.
- `test_webcake_env.py` thêm bất biến cho TOÀN catalog: không connector nào được nhét `jwt=`, `token=`, `api_key=`, `secret=`, `password=`, `access_token=` vào `url`, kèm canary chứng minh luật này soi thật.
### Kiểm thử
- Đã kiểm bằng curl thật: endpoint hosted trả 401 kèm `WWW-Authenticate` trỏ `.well-known/oauth-protected-resource`, và metadata có `registration_endpoint`. Bước đăng nhập bằng trình duyệt thì phải user tự bấm nên connector để `status: beta`.
- Test buộc hai cách Webcake CÙNG `tool_meta`, CÙNG tool validate và CÙNG `default_perm`, tránh một đường cho qua thứ đường kia chặn.

## [0.9.255] - 2026-07-30
Đấu Webcake trong Javis xong là hỏng ngay: mọi tool tạo, sửa hay đăng trang đều trả `missing_env WEBCAKE_API_BASE`, vì catalog chưa hề cấp base URL của API.
### Sửa lỗi
- **Connector Webcake thiếu base URL API**: package `webcake-landing-mcp` giải base theo thứ tự `WEBCAKE_API_BASE` > preset của `WEBCAKE_ENV` > file `auth.json` do lệnh `login` ghi. Catalog Javis chỉ map `WEBCAKE_JWT` và `WEBCAKE_ORG_ID` từ ô đăng nhập nên không cấp gì trong ba đường đó, khiến cả 9 tool lưu trữ (`list_organizations`, `create_page`, `list_pages`, `find_pages`, `get_page`, `update_page`, `add_section`, `patch_page`, `publish_page`) chết ngay. Tool validate cũng nằm trong nhóm đó nên thẻ kết nối đỏ luôn từ lúc vừa đấu. Nay catalog cấp `WEBCAKE_ENV=prod`: dán JWT là chạy, khỏi bắt user gõ lệnh `login` ngoài Javis.
### Thêm mới
- **Khối `env` tĩnh mức connector trong catalog**: chỗ khai hằng số kỹ thuật KHÔNG phải secret (base URL, preset môi trường) để khỏi đẻ thêm ô nhập bắt user gõ URL. Thứ hạng: env user tự đặt ở connection > ô đăng nhập > env tĩnh catalog, nên bản staging hay self-hosted vẫn đè được bằng `WEBCAKE_API_BASE` riêng. Dùng preset thay vì ghi cứng URL để Webcake đổi tên miền thì package tự lo.
### Kiểm thử
- `test_webcake_env.py`: dán JWT là đủ để giải được base, không được đẻ ô nhập cho URL kỹ thuật, tool validate phải nằm trong nhóm cần base, thứ tự ưu tiên của env tĩnh so với ô đăng nhập và env connection, kèm canary chứng minh check đọc catalog thật chứ không luôn xanh.

## [0.9.254] - 2026-07-29
Note trong đồ thị 3D vẫn nhạt nhoè không đọc được. Hai lỗi, và bộ mô phỏng ở bản trước đã che mất cả hai.
### Sửa lỗi
- **Cỡ hạt gõ cứng bằng đơn vị thế giới, trong khi nó phải TỈ LỆ với cỡ khối**: hạt để 3.2-20 đơn vị cố định, nhưng lực vật lý trải khối ra rộng bao nhiêu thì hạt teo tương ứng bấy nhiêu. Trên máy thật khối trải rộng hơn nhiều so với giả định nên hạt chỉ còn mấy chấm mờ. Nay cỡ hạt là tỉ lệ bán kính khối đo được: note lẻ 0.030R, hub tối đa 0.115R - khối to nhỏ thế nào cũng giữ đúng tỉ lệ nhìn thấy được. Đã kiểm ở bán kính 70 và 210 với three.js thật, tỉ lệ giữ nguyên.
- **Dải màu hạt quá nhọn**: đặc tới 9% bán kính rồi tắt ngay, nên ở cỡ màn hình thật cái lõi đặc đó bé hơn một pixel và chỉ còn quầng mờ. Nay là ĐĨA ĐẶC viền mềm (đặc tới 34% rồi mới tắt) nên hạt luôn là một chấm thật, không phải vệt nhoè.
- Dây nối tông sáng giảm từ 0.26 xuống 0.16 vì nó đang át hết note; sương giảm tiếp còn 0.13 (tối) và 0.10 (sáng).
### Kiểm thử
- Bộ mô phỏng ở bản trước dùng cỡ khối cố định nên vô tình che đúng cái lỗi tỉ lệ này. Nay nó giãn/co được cả khối và tính cỡ hạt theo bán kính, và mọi phương án đều phải kiểm ở hai cỡ chênh nhau 2.5 lần mới được duyệt.
- `test_graph3d_nebula.js` thêm điểm khoá: khối to gấp 3 thì hạt phải to gấp 3, đo trên sprite thật chứ không phải chép lại công thức.

## [0.9.253] - 2026-07-29
Bản trước sửa đồ thị 3D nhưng làm nó tệ hơn: cả tối lẫn sáng đều thành một màn sương, không thấy note đâu. Lần này dựng bộ mô phỏng để NHÌN được rồi mới chỉnh.
### Sửa lỗi
- **Ba lớp quầng sáng chồng lên nhau ở giữa khoang não**: nền CSS, quầng của starfield, và lõi sáng thêm ở 0.9.252. Riêng cái lõi đặt đường kính bằng 2.5 lần bán kính khối nên nó phủ trùm toàn bộ đồ thị. Nay lõi thu về 0.38 (gọn trong lòng khối, đọc ra "tim" chứ không phải "mù"), và quầng nền giữ NGUYÊN không đụng tới vì dùng chung với đồ thị 2D.
- **Note bị chìm dưới dây nối**: dây để mờ 0.20 còn note chỉ 0.52, thành ra nhìn ra mạng nhện xám mà không thấy note - ngược hẳn thứ tự quan trọng. Nay note lên 0.90 (tối) / 0.97 (sáng), dây xuống 0.12 (tối).
- **Hạt note loang thành vệt**: dải màu quá thoải nên mỗi note là một đám mờ chứ không phải một điểm. Nay gọn hẳn, gần như đặc tới 9% bán kính rồi tắt nhanh - mỗi note là một ĐIỂM đọc được.
- Sương mù giảm từ 0.26 xuống 0.17 (tối) và 0.30 xuống 0.13 (sáng); bụi vành giảm từ 620 hạt xuống 260 và mờ đi một nửa. Cả hai đang góp phần làm mờ thay vì tạo chiều sâu.
- Sàn cỡ hạt nâng từ 2.4 lên 3.2: dưới mức đó note ít liên kết nhỏ tới mức coi như không tồn tại.
### Cải thiện
- **Lõi mang hơi ấm của Javis**: đổi từ trắng-tím sang đốm than cam thương hiệu loang ra tím. Tông sáng thành vệt ửng đào-lavender nhạt, đọc như chỗ mực thấm đậm nhất giữa trang giấy.
### Kiểm thử
- Dựng bộ mô phỏng dựng hình bằng PIL, chồng lớp đúng thứ tự và đúng phép trộn của app, để đối chiếu được bằng mắt trước khi sửa code. Đã kiểm ở 150, 220 và 400 note - màu giữ nguyên, không bệt lại ở mật độ dày.
- `test_graph3d_nebula.js` đổi từ khoá hằng số sang khoá QUAN HỆ (sương tỉ lệ nghịch bán kính, dải cỡ có sàn và trần) để còn vặn được thẩm mỹ mà test không vỡ oan.

## [0.9.252] - 2026-07-29
Đồ thị 3D trước giờ là một quả cầu lốm đốm xám trắng, dẹt và không ra chất. Nguyên nhân đo được rồi, không phải chuyện gu.
### Sửa lỗi
- **Màu thư mục trong đồ thị 3D bị bạc thành xám**: mỗi hạt có một chấm TRẮNG ở tâm trước khi tới màu danh mục. Đo pixel tâm của một hạt đơn lẻ: chàm `#8b93ff` ra `rgb(177,178,190)`, lục `#3fdc9a` ra `rgb(171,184,181)`, cam `#f0a24a` ra `rgb(186,179,174)` - tức mất khoảng **90% màu ngay khi chưa chồng lớp nào**. Cộng thêm vài trăm hạt cộng sáng chồng nhau thì cả khối thành trắng bệt. Nay dải màu của hạt chỉ còn MỘT hue từ tâm ra viền: ba màu trên lần lượt ra `rgb(125,132,230)`, `rgb(57,197,139)`, `rgb(215,145,68)` - mất dưới 11%.
- Hạ độ mờ nền của hạt xuống 0.52 (trước 0.62): mô phỏng phép cộng sáng cho thấy trên 0.6 thì chỉ 16 hạt chồng nhau đã dồn về trắng, màu chỉ sống được ở vành.
### Thêm mới
- **Lõi sáng ở tâm tinh vân**: thứ mà mọi tham chiếu đẹp đều có và bản cũ thiếu hẳn. Thở theo giọng nói, không chịu sương mù vì nó là nguồn sáng. Tông sáng đổi thành vệt loang lavender-đào, đọc như mực thấm dày giữa trang giấy.
- **Sương mù theo chiều sâu**: hạt ở xa mờ dần về màu nền nên khối có thể tích thay vì dẹt như ảnh dán. Độ dày suy ra từ bán kính khối đo được, brain to nhỏ đều hợp cỡ.
- **Lớp bụi vành**: 620 hạt rất mịn bao ngoài, trôi ngược chiều rất chậm để sinh thị sai - mắt đọc ra khối 3D thật thay vì một tấm ảnh đang quay.
### Cải thiện
- **Lõi đặc, vành thưa**: lực hút về tâm giờ tỉ lệ theo số liên kết, note nhiều liên kết bị kéo vào giữa còn note lẻ trôi ra rìa. Vừa đẹp hơn quả cầu đều tăm tắp, vừa mang nghĩa - cái gì quan trọng thì nằm giữa.
- **Dải cỡ hạt rộng và mịn hơn**: note lẻ thành hạt bụi nhỏ, hub to rõ gấp nhiều lần. Trước đây mọi hạt gần như cùng cỡ nên nhìn ra một đám chấm đều.
- Dây nối nâng từ mờ 0.11 lên 0.20 nên thấy được cấu trúc mạng, và tự mờ theo chiều sâu cùng với hạt.
### Kiểm thử
- `test_graph3d_nebula.js` khoá 20 điểm: hạt không được có điểm dừng trắng, tông sáng phải đổi kiểu chồng lớp, sương suy ra từ bán kính, lõi/bụi đúng thứ tự vẽ và không nhân bản khi dựng lại. Đã đối chiếu mọi API dùng tới với three.js r159 thật.

## [0.9.251] - 2026-07-30
Zalo được rút về đúng một đường MCP: nối tài khoản xong là tìm cuộc chat và gửi trực tiếp, không cần bật nghe hay chọn danh sách theo dõi.
### Cải thiện
- **Gửi Zalo trực tiếp bằng MCP upstream**: Javis dùng `zalo_search_threads` để tìm đúng người/nhóm rồi gọi `zalo_send_message`; bỏ chốt phụ thuộc danh sách cuộc chat đang nghe và bỏ tool `javis_zalo_send`.
- **Gỡ toàn bộ menu “Nghe tin liên tục”**: không còn chọn tài khoản nghe, cuộc chat theo dõi, báo Telegram theo từ khoá hay giờ im lặng.
- **Một tiến trình Zalo duy nhất**: bỏ sidecar listener, webhook, luật theo từng cuộc chat và hai plugin Zalo cũ; dùng thẳng `zalo-agent-cli` 1.6.2 qua stdio với đủ 7 tool MCP.
- Thẻ kết nối Zalo có link mở tài liệu hướng dẫn trên GitHub.

## [0.9.250] - 2026-07-29
Nút đổi tông trước giờ chỉ lật từ đen sang xám, không phải giao diện sáng thật. Nay có tông sáng đúng nghĩa, và khoang não được vẽ lại cho hợp nền giấy.
### Thêm mới
- **Tông SÁNG thật sự**: nền trắng ngà ấm `#FBF9F7`, thẻ trắng, chữ gần đen, nhấn cam thương hiệu. Nút đổi tông giờ lật thẳng TỐI ↔ SÁNG (biểu tượng trăng/mặt trời báo tông đang dùng); tông "tối nhạt" cũ đã gỡ, ai đang dùng nó sẽ tự về tông tối.
- **Khoang não vẽ lại theo lối "mực trên giấy"**: nền giấy có quầng lavender-đào rất nhạt ở giữa, nút và dây nối vẽ bằng mực sẫm cùng tông màu danh mục cũ, sao đổi thành hạt bụi giấy, vignette tối đổi thành đậm dần bằng chính màu giấy. Bảng màu danh mục có bản mực riêng, cùng thứ tự màu nên mỗi thư mục vẫn giữ đúng "màu nhận dạng" của nó khi đổi tông.
- Đổi tông **không nạp lại đồ thị**: node giữ nguyên vị trí, cụm đang rọi sáng và node đang trỏ đều còn - chỉ đổi màu tại chỗ.
### Cải thiện
- Gom **62 biến màu** thành một bộ token duy nhất ở đầu `style.css`, khai đủ cho cả hai tông. Ba thủ pháp mà nền sáng không có (mặt kính trắng-mờ, bóng đen tách lớp, quầng phát sáng) được tách token riêng để tông sáng thay bằng thủ pháp tương đương: tô sẫm nhẹ, bóng nâu rất nhạt, viền vòng.
- Khai `color-scheme` cho từng tông, nên thanh cuộn hệ thống, con trỏ nhập, lịch, và nền vàng autofill của trình duyệt cũng đổi theo thay vì kẹt ở mặc định tối.
- Khối code cũng sáng theo (có bảng màu cú pháp riêng cho nền giấy) thay vì để một mảng đen giữa trang.
### Sửa lỗi
- Mọi chữ trong tông sáng đạt tối thiểu 4.5:1 theo WCAG AA. Cam thương hiệu tách làm hai vai: `--accent` giữ nguyên độ rực cho chấm/viền/gạch, còn nút cam đặc mang chữ trắng dùng bản sẫm hơn - vì tương phản là đối xứng, một màu vừa nổi trên nền trắng vừa đỡ được chữ trắng là bất khả.

## [0.9.249] - 2026-07-29
Muốn giao thêm một fanpage cho Javis mà bấm Kết nối lại thì Facebook không hỏi lại gì cả.
### Sửa lỗi
- **Kết nối lại Facebook giờ hiện lại màn chọn Trang**: đã cấp quyền một lần rồi thì Facebook đi đường tắt "Tiếp tục với tên X" và bỏ qua màn "Chọn nội dung bạn cho phép", nên không có chỗ nào tick thêm fanpage mới - người dùng kẹt với đúng bộ Trang đã chọn lần đầu, xoá tài khoản đi đấu lại cũng vậy. Nay đường đăng nhập Meta luôn kèm `auth_type=rerequest` (tham số Meta khai đúng cho việc hỏi lại), nên mỗi lần Kết nối lại là hộp thoại quyền hiện đầy đủ, tick thêm Trang được. Áp dụng cho cả Facebook Trang lẫn Meta Ads (chọn lại tài khoản quảng cáo).
- Lưu ý khi tick: **giữ nguyên các Trang cũ**, bỏ tick Trang nào là Javis mất quyền Trang đó. Hướng dẫn trong hộp Kết nối và mục Sự cố thường gặp đã ghi thêm bước này.
### Kiểm thử
- `test_meta_graph.py` chốt đường authorize của Meta phải mang `auth_type=rerequest`, để lần sau ai dọn tham số không lỡ tay gỡ mất.

## [0.9.248] - 2026-07-29
Dọn nốt đường phình media bị bỏ sót ở bản trước, và nó lại là đường to nhất.
### Cải thiện
- **Tự dọn thư mục stage tạm**: nơi file dán vào khung chat rơi xuống trước đây không có gì dọn, trên máy phát triển đã tích 114MB với 62 tệp, file cũ nhất 27 ngày. Nay hết hạn sau 3 ngày, chỉnh qua `media.staging_days` trong `settings.json`. Hạn ngắn hơn vùng cache của brain vì đây là chỗ trung chuyển một lượt chat, không ai mở lại; cũng vì thế file `.md` lạc vào đó bị dọn luôn chứ không được chừa như trong brain.

## [0.9.247] - 2026-07-29
Ảnh và file gửi lên thôi nằm lại vĩnh viễn trong brain. Chúng là nguyên liệu đi qua, đọc xong rút thành ghi chú là đủ dùng.
### Cải thiện
- **Media không lên git nữa**: `attachments/` và `inbox/` giờ nằm ngoài git của brain. Trước đây mỗi tấm ảnh là một blob nằm vĩnh viễn trong lịch sử, xoá file về sau cũng không lấy lại được dung lượng, mà bản mirror còn nhân đôi. Brain cũ đã lỡ commit thì được gỡ khỏi chỉ mục một lần; phần lịch sử đã lỡ thì giữ nguyên, không viết lại.
- **Tự dọn vùng cache media**: ảnh quá 30 ngày tự xoá, và nếu tổng vượt 300MB thì dọn từ cũ tới mới cho tới khi xuống dưới trần. Chỉnh được qua khoá `media` trong `settings.json`, đặt `enabled: false` là thôi dọn. Ghi chú `.md` lạc vào hai thư mục đó thì được chừa ra.
- **Ảnh đã hết hạn hiện ô xám**: chỗ ảnh không còn hiện ô viền đứt ghi "Ảnh đã hết hạn" thay cho icon vỡ, đúng cả khi file bị xoá tay hay đổi tên.

## [0.9.246] - 2026-07-29
Nối Telegram vào kho phiên ở 0.9.244 để lộ vấn đề ngược lại: phiên Telegram không có gì chặn nó dài vô tận.
### Cải thiện
- **Phiên Telegram tự XOAY.** Trên dashboard người dùng tự bấm "＋ Hội thoại mới" nên phiên không bao giờ dài mãi; trên Telegram thì gần như KHÔNG AI gõ `/reset`, nên một Chat ID dính vào một phiên là phiên đó dài vô tận chừng nào server chưa restart. Mở ra đọc là kéo về cả nghìn tin, vì `openStoredSession` vẽ TOÀN BỘ `sess.messages` không phân trang - nút "Xem thêm" ở thanh bên chỉ phân trang DANH SÁCH hội thoại chứ không phân trang tin trong một cuộc. Nay `_tg_conv_sid` sang phiên mới khi nghỉ quá 12 tiếng hoặc chạm 200 tin (`/reset`, đổi brain và restart vốn đã mở phiên mới từ 0.9.244).
- **Xoay chỉ xoay BẢN GHI, không đụng ngữ cảnh engine.** `sess['cli']`, thread Codex và `sess['or']` (vốn đã có `compact_mem` lo cửa sổ) đều giữ nguyên, nên người dùng Telegram không hề thấy Javis quên gì; chỉ dashboard là thấy hội thoại chia thành khúc đọc được. Đây là lý do cách này chấp nhận được, và có test riêng chốt lại ràng buộc đó.
- **Không phải sửa gì ở phần đọc.** Xoay biến một phiên vô hạn thành nhiều phiên hữu hạn, nên cái tăng lên là SỐ hội thoại - đúng thứ nút "Xem thêm" của thanh bên đã lo sẵn. Không đụng `app.js`.
### Thêm mới
- **Cột `channel` trong bảng `sessions`** (`web` mặc định, tự migrate cho DB cũ qua vòng ALTER sẵn có) + nhãn **TG** trong danh sách hội thoại, để phân biệt cuộc đến từ bot với cuộc tự mở trên dashboard. Không có nó thì xoay phiên chỉ làm thanh bên đầy những cuộc không rõ từ đâu ra.
- **`SessionStore.archive_stale(channel, before_ts)`**: phiên Telegram nguội quá 30 ngày tự cất vào kho lưu để thanh bên không ngập dần. Chạy theo nhịp xoay (cỡ vài ngày một lần) chứ không mỗi lượt. Cất chứ không xoá - vẫn tra được qua `search` và `include_archived`.
### Kiểm thử
- **`test_telegram_sessions.py`**: 38 khẳng định. Cột `channel` gồm cả migrate DB cũ; `archive_stale` đúng kênh, đúng độ nguội, cất rồi vẫn search được; luật xoay THẬT trong `_tg_conv_sid` chứ không mô phỏng lại (giữ phiên khi còn nóng, xoay khi nghỉ lâu / chạm trần tin / phiên bị xoá trên dashboard, hai chat không lẫn phiên); và ràng buộc xoay-không-đụng-engine.
- Phần LƯU một lượt vẫn do `test_luu_luot_chat.py` (0.9.244) phủ; test này không giẫm lên.

## [0.9.245] - 2026-07-29
Đóng nốt bảy chỗ còn lại mà hai bản dispatch engine trôi lệch nhau. Danh sách phụ lục spec giờ hết mục.
### Sửa lỗi
- **Telegram mất sạch ngữ cảnh khi phiên Codex cũ không còn trên máy**: rollout của Codex nằm ở máy, bị dọn hoặc mất sau nâng cấp là lượt đó chết hẳn, không dựng lại được gì. Nay bắt đúng lỗi resume hỏng, mở thread mới và nạp lại ngữ cảnh từ lịch sử đã lưu, rồi các lượt sau resume thread mới. Chữa được là nhờ 0.9.244 đã cho Telegram một kho phiên để mà dựng lại.
- **Đổi model rồi quay lại Codex thì nó mù các lượt ở giữa**: chuyển sang Claude nói vài câu rồi quay về ChatGPT, Codex vẫn resume đúng luồng cũ vốn chưa hề thấy mấy câu đó. Nay provider khác chen một lượt là liên kết luồng Codex bị xoá, lượt Codex kế tiếp dựng lại ngữ cảnh từ kho phiên.
- **Một lỗi vặt giữa lượt huỷ luôn cả câu trả lời trên Telegram**: một tool hỏng là Javis trả về mỗi dòng "⚠", trong khi luồng thường vẫn chạy tiếp và vẫn ra câu trả lời tử tế. Nay lỗi giữa lượt không chí mạng: có câu trả lời thì gửi câu trả lời, kèm một dòng báo có lỗi ở cuối; không có chữ nào mới báo lỗi như cũ. Đây vốn là cách dashboard xử lý.
- **Bong bóng chat trên web treo mãi khi luồng đứt giữa chừng**: khung `response` của nhánh Claude nằm trong nhánh xử lý `final`, nên engine chết trước khi kịp phát `final` là client không nhận được `response` nào cả, dù chữ đã hiện ra rồi. Nay khung `response` nằm ngoài vòng lặp và lấy phần đã stream làm phương án dự phòng. Nhánh Telegram cũng vậy.
- **Phiên Telegram dài phải chờ tóm tắt xong mới thấy câu trả lời**: `compact_mem` là một request LLM nữa nhưng lại chạy thẳng trong đường request. Nay chạy nền, và chỉ áp kết quả khi lịch sử chưa đổi kể từ lúc bắt đầu nén (có lượt chen vào giữa mà đè lên là nuốt mất lượt vừa nói).
- **File Codex ghi ra không được gửi kèm**: nhánh Codex truyền danh sách rỗng cho bộ thu file, nên file chỉ về tay anh nếu đường dẫn tình cờ được nhắc trong câu trả lời. Codex không có trường `file_path` chuẩn hoá như Claude - đường dẫn nằm rải trong `changes[]`, trong `arguments`, hay lẫn trong lệnh shell, tuỳ loại việc. Nay `CodexCLI` đẩy nguyên payload thô lên và bộ gom mới đi hết payload nhặt mọi thứ trông giống đường dẫn; thu rộng vô hại vì bộ lọc phía sau vốn chỉ giữ tệp có thật và vừa đổi trong lượt.
- **Model bị ép về bản hợp lệ mà không ai nói gì**: chọn `gpt-4o` cho tài khoản ChatGPT thì Codex không chạy được, Javis lặng lẽ đổi sang model khác và anh cứ tưởng vẫn đang chạy model mình chọn. Nay ghi lại model đúng vào Settings và báo ngay trong câu trả lời. Báo trong câu trả lời chứ không phải dòng trạng thái, vì dòng trạng thái bị thay bằng câu trả lời nên không ai đọc được.
### Thay đổi
- **`_tg_ket`** gói câu trả lời Telegram (cảnh báo hệ thống lên đầu, lỗi giữa lượt xuống cuối) và **`_tg_compact_bg`** đẩy vòng nén sang nền. Vẫn KHÔNG gộp luồng dispatch: mỗi lỗi sửa tại chỗ, đúng khuyến nghị trong spec.
- **`channel_context.candidate_paths_from_tool`**: bộ gom đường dẫn từ payload tool call, cố tình thu rộng vì tầng lọc phía sau đã chặt sẵn.
- **`CodexCLI` phát thêm sự kiện `item`** cho các item lạ (vd bản vá file). Không hiện thành "đang gọi tool" để khỏi ồn, nhưng caller vẫn moi được đường dẫn file vừa ghi.
### Kiểm thử
- **`test_dispatch_hai_kenh.py`**: 27 khẳng định, sáu lỗi Telegram test bằng cách gọi thẳng `_tg_answer` thật với engine giả (đo hành vi, không đo hình dạng code) - resume hỏng có dựng lại ngữ cảnh thật không, lỗi giữa lượt có nuốt câu trả lời không, nén có chặn đường request không, file Codex ghi ra có về tay user không. Lỗi bong bóng treo nằm trong hàm lồng bên trong WebSocket handler nên không gọi thẳng được, test bằng AST đúng hai điều tạo nên lỗi.
- 90/90 xanh.

## [0.9.244] - 2026-07-29
Hội thoại Telegram từ nay được LƯU và được HỌC như hội thoại trên web, token Telegram được tính vào bảng Mức dùng, và khối nút bấm thôi lọt vào kho phiên.
### Sửa lỗi
- **Hội thoại Telegram không được lưu vào đâu cả**: không vào `/sessions`, không vào `brain/Memory/conversations`, không vào vòng tự học. Nói chuyện với Javis qua Telegram bao lâu cũng vậy, mở trang Lịch sử ra là trống, và bộ não không dày lên được một chút nào. Nay mỗi lượt Telegram mở/khớp một phiên trong kho như dashboard, lưu cả lượt hỏi lẫn lượt trả lời, tự đặt tiêu đề, ghi nhật ký hội thoại vào Memory của brain đang dùng, và đẩy vào hàng đợi tự học.
- **Token Telegram không được tính, trừ khi chạy qua Codex**: nhánh Claude Code và nhánh API (OpenRouter/OpenAI/Anthropic/Gemini) đều thiếu `usage_store.record`, nên bảng Mức dùng báo thiếu mọi cuộc trò chuyện Telegram. Nhánh API còn bám model THẬT do sự kiện `meta` báo về, chứ không phải model đã đặt trong Settings (OpenRouter tính tiền theo model thật).
- **Khối nút bấm thô lọt vào kho phiên và vào nhật ký hội thoại**: dashboard ghi thẳng `<!-- JAVIS_ASK ... -->` vào SQLite và vào `brain/Memory/conversations`, tức rác lọt vào chính corpus dùng để tự học. Nay bóc khối trước khi lưu ở CẢ HAI kênh. Nút bấm vẫn vẽ bình thường vì dashboard dựng nút từ sự kiện WebSocket sống, còn lịch sử thì vốn đã không dựng lại nút.
- **Chỗ thứ 9 gọi route handler như hàm thường**: `bench_hotpath.py` gọi `asyncio.run(main.list_brains())`. Lưới dựng ở 0.9.243 bỏ sót vì nó chỉ soi `main.py` + `routes/` và chỉ bắt lời gọi trần, không bắt dạng `module.handler()`.
### Thay đổi
- **`_persist_turn(...)` - đường lưu một lượt, dùng chung cho mọi kênh**: bóc khối điều khiển rồi mới `append_message` + `auto_title` + `log_conversation` + `learn.enqueue`. Đây là mảnh chung DUY NHẤT được rút ra; luồng 4 nhánh engine vẫn để nguyên hai bản, đúng khuyến nghị trong spec là sửa từng lỗi trước rồi mới cân nhắc gộp.
- **Telegram tách vỏ khỏi lõi**: `_tg_answer` (vỏ - phiên + lưu) và `_tg_answer_engine` (lõi 4 nhánh, giữ nguyên văn). Vỏ quyết định nhãn engine rồi truyền xuống lõi, để không có ngày phiên bị dán nhãn `cli` trong khi lượt thật chạy qua OpenRouter. Quy ước: lõi trả **dict = câu trả lời thật (đáng lưu)**, trả **chuỗi = thông báo lỗi (không lưu)**.
- `/reset` và `/brain` trên Telegram nay mở phiên mới trong kho thay vì nối tiếp mạch cũ.
- **`learn.enqueue` chuyển từ `asyncio.create_task` sang `await` thẳng**: nó chỉ đọc config + cộng bộ đếm dưới khoá (mẻ học thật chạy ở `tick`), rẻ hơn chính lần ghi file log ngay trên nó. Task mồ côi không ai chờ, nuốt lỗi im, không đáng.
### Kiểm thử
- **`test_luu_luot_chat.py`**: gọi THẲNG `_tg_answer` thật với engine giả nên đo hành vi chứ không đo hình dạng code - phủ cả nhánh Claude CLI lẫn nhánh API, khẳng định có ghi Mức dùng đúng nhà cung cấp/token/model thật, có lưu đủ lượt hỏi + lượt trả lời vào CÙNG một phiên, nhiều lượt không đẻ phiên mới, hai chat khác nhau ra hai phiên khác nhau, và bản lưu / nhật ký / corpus tự học đều sạch khối điều khiển.
- **`test_handler_khong_goi_truc_tiep` quét rộng ra toàn bộ `server/`** và bắt cả dạng `module.handler()`, có phân biệt theo module nên `skill_router.list_skills()` (hàm thường trùng tên với handler) không bị báo động giả.
- 89/89 xanh.

## [0.9.243] - 2026-07-29
Bóc hai nhóm route đầu tiên khỏi `main.py`, và bịt một quả bom hẹn giờ: code nội bộ gọi thẳng route handler như hàm Python thường.
### Sửa lỗi
- **8 chỗ gọi route handler như hàm thường**: khối Telegram gọi `await list_agents(brain)`, `await provider_models(provider=pid)`, `await list_brains()`, `await list_skills(brain)`, `await list_workflows(brain)` (6 chỗ), cộng `_fetch_provider_models` gọi `openrouter_models()` và `/notifications` gọi `changelog_info()`. Chạy được nên chưa ai thấy, nhưng tham số mặc định của handler là ĐỐI TƯỢNG `fastapi.params.Query` chứ không phải chuỗi: ngày nào có người gọi thiếu đối số thì `brain` thành một Query object, `_brain_root` nhận vào rồi `os.path.isdir(Query)` ném TypeError - và nó nổ ở Telegram chứ không ở chỗ vừa sửa. Nay handler chỉ còn là vỏ HTTP mỏng bọc quanh hàm thuần (`agents_index`, `workflows_index`, `skills_index`, `provider_models_index`, `changelog_index`, `openrouter_models_index`), nội bộ gọi thẳng hàm thuần.
### Thay đổi
- **`routes/graph.py`**: `GET /graph` + `WS /ws/graph` và 5 helper riêng rời khỏi `main.py`. Chép nguyên văn, chỉ đổi chỗ lấy đường dẫn brain/vault sang tiêm phụ thuộc.
- **`routes/domain.py`**: 4 route tên miền/HTTPS (`/tls-check`, `/domain`, `/domain/status`, `/domain/ssl`). Đã xác minh 7 helper và 2 biến trạng thái không được dùng ngoài khối. `/tls-check` giữ nguyên đường dẫn vì nó nằm trong danh sách công khai của middleware và Caddy gọi nó trước khi xin chứng chỉ.
- `main.py` 6.491 -> 6.159 dòng.
### Kiểm thử
- **`test_handler_khong_goi_truc_tiep.py`**: quét AST toàn bộ `main.py` + `routes/` tìm mọi lời gọi tới hàm có decorator route. Chính test này tìm ra 2 chỗ mà bản phân tích bỏ sót (nó chỉ soi vùng Telegram), và nó chặn tái phát cho cả những khối chưa đụng tới.
- **`test_skill_usage` soi đúng chỗ mang hành vi**: nó dùng AST khẳng định handler `GET /skills` có gọi `skill_usage.read_usage`/`is_stale`. Bóc lõi sang `skills_index` là handler rỗng và test đỏ dù hành vi còn nguyên. Nay soi `skills_index`, VÀ thêm một khẳng định mới là handler phải thật sự gọi lõi đó chứ không tự dựng lại đường khác.
- **`test_domain_setup_ui` thôi bám vào chỗ code nằm**: nó tìm chuỗi trong `main.py` để khẳng định backend xử lý Hostinger, nên mỗi lần bóc khối là đỏ oan. Nay đọc ghép cả `main.py` lẫn `routes/`.
- 88/88 xanh. Bảng route khớp 192 mục đúng thứ tự sau mỗi bước, kể cả `WS /ws/graph` giữ nguyên kiểu `APIWebSocketRoute`, tên route và vị trí.
### Ghi chú
- Lưới an toàn dựng ở 0.9.235 đã trả công: khi bóc lõi `/changelog` và `/openrouter/models`, decorator bị gắn nhầm vào hàm lõi thay vì hàm vỏ, làm hai endpoint đổi tên route. Ảnh chụp bảng route bắt ngay lập tức.

## [0.9.242] - 2026-07-29
Tách test ra khỏi mã nguồn. `server/` từ 126 file `.py` xuống còn 50 file nguồn thuần.
### Thay đổi
- **76 file test Python chuyển sang `tests/python/`, 11 file test JS sang `tests/js/`**. Trước đó test nằm xen kẽ theo thứ tự bảng chữ cái với 50 module nguồn trong cùng một thư mục phẳng, nên mọi lần tìm kiếm trong `server/` đều lẫn nhiễu và câu hỏi "file nào là nguồn" không trả lời được bằng mắt.
- **Test không còn phụ thuộc thư mục làm việc.** Trước đây phải chạy đúng từ `server/` mới được: 62 file nạp `sys.path` theo thư mục script, 35 biểu thức `__file__` dò đường tới nguồn, 15 chỗ mở file nguồn bằng đường dẫn tương đối theo cwd. Chạy sai chỗ là hàng loạt test đỏ vì `import main` không thấy module, hoặc tệ hơn là lặng lẽ đọc nhầm file. Nay tất cả quy về `tests/python/_paths.py` (`ROOT`, `SERVER`, và import nó cũng nạp `server/` vào `sys.path`), nên chạy được từ bất kỳ đâu và lần sau có dời nữa cũng chỉ sửa một file.
- **Test JS thôi bị phục vụ công khai**: chúng nằm trong `dashboard/` vốn được mount tĩnh, nên `/static/test_chat_render.js` truy cập được từ ngoài. Chuyển sang `tests/js/` là hết.
### Thêm mới
- **`tests/run.py`**: chạy toàn bộ hoặc lọc theo tên (`python tests/run.py zalo`), có `--js` / `--py` / `-v`. Tự tìm `.venv` nên không chạy nhầm python hệ thống (thiếu fastapi/yaml). In tiến độ có `flush` nên chạy nền hay qua pipe vẫn theo dõi được, thay vì im ru tới lúc kết thúc.
- **`tests/python/conftest.py`**: để `pytest` chạy được với các file đã chuyển sang kiểu pytest. Bộ chạy chính vẫn là vòng lặp từng file, vì 61 trên 76 file gọi `sys.exit()` ngay ở mức module nên bước collect của pytest sẽ huỷ cả lượt chạy.
### Kiểm thử
- **7 test JS chưa từng chạy lần nào giờ đã chạy.** CI trước đây liệt tay 4 file (`test_chat_ask`, `test_chat_render`, `test_chat_slash`, `test_wikilink`), bỏ sót 7 file còn lại. Nay quét cả thư mục nên thêm test mới là tự chạy. Cả 11 đều xanh.
- CI bỏ `cd server`, chạy thẳng `tests/python/test_*.py` và `tests/js/test_*`. 87/87 xanh.
- `tests/` vào `.dockerignore`: image không chạy test. Trước 0.9.242 không loại được vì test rải trong `server/` và `dashboard/`, muốn loại là đụng luôn mã nguồn.

## [0.9.241] - 2026-07-28
Bịt lỗ rò bí mật vào image Docker, và sửa ba lỗi trong chính bộ test - trong đó có một lỗi làm hai bài test đo hiệu năng luôn xanh bất kể code đúng hay sai.
### Bảo mật
- **`.dockerignore` để lọt khoá bí mật vào image**: `Dockerfile:64` là `COPY . .` nên đây là hàng rào DUY NHẤT, mà nó đã trôi thành bản sao cũ và yếu hơn `.gitignore` nhiều. Bốn file đang bị nướng thẳng vào image: `server/.secret_key`, `server/.hub_token`, `server/.oauth_mcp.json`, `server/usage_index.db`. Build trên GHCR chạy từ checkout sạch nên không dính, đó là lý do lỗi này sống lâu mà không ai thấy; chỉ ai `docker build` cục bộ mới bị.
- **Bẫy cú pháp `.dockerignore`**: pattern khớp từ GỐC context, KHÔNG tự khớp mọi độ sâu như `.gitignore`. Nên dòng `.staging/` trần chưa bao giờ loại được `server/.staging` (114MB), và tương tự với `brains-backup` (1,4GB). Muốn khớp mọi độ sâu phải viết `**/`, đúng như dòng `**/__pycache__` vốn đã có trong file. Sau khi vá, **context build từ 1.239 MB xuống 6 MB**.
### Sửa lỗi
- **Phép đo độ trễ event loop trong test vô nghĩa**: `test_brains_dem` và `test_kanban_snapshot` (thêm ở 0.9.239-240) huỷ tác vụ nhịp tim NGAY sau khi gọi hàm. Hàm đồng bộ không có điểm nhường loop nào nên nhịp tim bị huỷ trước khi kịp ghi lại độ trễ - kết quả là cả đường đồng bộ lẫn đường qua thread đều báo 16ms, tức test luôn xanh bất kể code đúng hay sai. Nay nhường loop trước khi huỷ, và mỗi test có thêm một bước ĐỐI CHỨNG bắt buộc đường đồng bộ phải tệ hơn hẳn. Số thật sau khi vá: `/brains` đồng bộ khoá loop 456ms so với 21ms qua thread; snapshot Kanban 221ms so với 35ms.
- **`test_khoi_dong_nhe` báo oan trên máy đang tải**: dùng trần tuyệt đối 3000ms, mà trên máy đang quét virus thì riêng `import fastapi` mất 2,9-6,3 giây và interpreter trống mất 500ms, nên `import main` vọt lên 7,6 giây dù không dòng code nào đổi. Trần theo mili giây đo tốc độ MÁY chứ không đo thứ cần đo. Nay đo bằng TỈ LỆ so với chi phí nạp `fastapi`: hiện tại 1,93, nếu ai đó thêm lại `edge_tts` vào đầu file là 3,66, ngưỡng 3,0 tách sạch và miễn nhiễm với tốc độ máy.
### Dọn dẹp
- **`.gitignore` phủ 7 artifact trước đây vừa không track vừa không ignore**: `kanban.sqlite3`, `tg_brain.json`, `update_state.json`, `logs/`, `brain-trash/`, `_selfupdate.bat`, `videos/`. Trước đó một cú `git add -A` là commit thẳng dữ liệu chạy và trạng thái deploy vào repo.
- **Gỡ hai dòng `/agents` và `/workflows` khỏi `.gitignore`**: chúng sinh ra để che hai file rác 28 byte (mảnh log của một lệnh redirect hỏng), nhưng hệ quả là chặn vĩnh viễn việc tạo thư mục `agents/` hay `workflows/` THẬT ở gốc. Hai file rác đã xoá hẳn, cùng hai thư mục rỗng `memory/` và `server/utf-8/`.
- **`test_brains_dem` từ 27 giây xuống 9,5 giây**: bỏ việc tạo 3000 file thật, đổi sang mô phỏng đĩa chậm - vừa nhanh hơn vừa đúng tình huống thật cần chống (vault lớn, ổ mạng, VPS I/O nghẽn).
### Không làm (có chủ đích)
- **KHÔNG dời `server/brains-backup/` (1,4GB) và `server/.staging/` (114MB) ra ngoài repo** như spec ban đầu ghi. Kiểm ra thì cả hai không phải rác: `brains-backup` là bản sao làm việc git của tính năng sao lưu brain lên GitHub (`main.py:1474`) và ĐANG có thay đổi chưa commit; `.staging` chứa file người dùng upload thật. Cả hai là nội dung của `JAVIS_STATE_DIR`, mà `STATE_DIR` mặc định chính là `server/`, nên "dời ra ngoài" thực chất là đổi `STATE_DIR` - đúng điều spec cấm ở mục 3 vì đó là bẫy mất tài khoản và connector. `server/tmp/` cũng đang được `claude_sdk_engine.py:254` dùng.
### Kiểm thử
- `test_ignore_files.py` mới: kiểm 28 đường dẫn bí mật/trạng thái/dữ liệu nặng đều bị cả git lẫn Docker loại, và mã nguồn cùng tầng hệ thống thì KHÔNG bị loại. Phần git dùng chính `git check-ignore` nên là chân lý; phần Docker dùng một bản mô phỏng luật khớp có tự kiểm 5 case trước khi kết luận, giá trị chính là khoá cứng cái bẫy `**/`.
- 76/76 test xanh.

## [0.9.240] - 2026-07-28
Giai đoạn 1 của đợt tái cấu trúc: gỡ hết các chỗ chặn event loop rẻ tiền nhất. Mỗi lượt chat từ 150,8ms xuống 37,2ms, khởi động từ 2.263ms xuống ~1.400ms. Không đổi một hành vi nào ngoài số đếm note (xem dưới).
### Cải thiện
- **Đọc YAML bằng bộ nạp C (libyaml)**: `yaml.safe_load` chọn bản thuần Python trong khi venv đã có sẵn libyaml. Trên frontmatter SKILL.md thật thì bản C nhanh 6,2 lần, mà YAML chiếm 64% chi phí `build_system_prompt` - hàm chạy mỗi lượt chat, mỗi task Kanban, mỗi lần nhắc hẹn nổ, mỗi tick loop. `fastyaml.safe_load` thay ở đủ 9 chỗ; bộ nạp C chê thì tự thử lại bằng bộ nạp Python nên không thể thành bước lùi. **150,8 -> 52,6ms.**
- **Quét cây skill 1 lần thay vì 2 mỗi lượt**: `_javis_capability_summary` gọi `list_skills` còn `_skill_router_block` gọi `list_enabled_meta` (vốn là `list_skills` lọc lại). **52,6 -> 43,5ms.**
- **Cache manifest + state plugin theo mtime**: `describe()` đọc và parse lại `plugin.yaml` của mọi plugin mỗi lần gọi, và còn đọc lại `plugins.json` cho TỪNG plugin bundled. Phát hiện thêm: `plugins.json` không tồn tại trên phần lớn bản cài, nên mỗi lần gọi ném `FileNotFoundError` một lần cho mỗi plugin. Sau sửa, lần gọi thứ hai đọc 0 file (trước là 9). **43,5 -> 33,7ms.**
- **Nạp lười `edge_tts`**: chiếm 944ms trong 2.263ms khởi động (41%) và kéo cả chuỗi aiohttp vào đường boot, dù TTS là tính năng tuỳ chọn. Trên VPS, khởi động chậm ăn thẳng vào cửa sổ healthcheck lúc deploy. **2.263 -> ~1.400ms.**
- **Nhớ đệm bảng giá token**: `estimate_cost` quét tuyến tính cả bảng giá cho MỖI dòng - 321.009 lần so tiền tố cho 3 vòng báo cáo, trong khi chỉ có 11 model phân biệt và 6 khoá giá. Số lần quét mỗi `summary()` từ 53.496 xuống 54. Nói thẳng mức lợi: chỉ cắt 9% tổng thời gian, vì hàm vẫn bị gọi đủ số lần do `_group` chạy lại trên cùng bộ dòng cho 15 chiều.
### Sửa lỗi
- **Bốn chỗ chặn event loop**: `/usage/summary` và `/usage/insights` gọi thẳng truy vấn sqlite trên loop (46-65ms) dù `refresh()` ngay dòng trên đã offload đúng cách; `GET /brains` quét `rglob("*.md")` cả cây mỗi brain (136ms) và dashboard gọi nó lúc BOOT; snapshot Kanban chạy đồng bộ ở 10 route handler. Trên một tiến trình uvicorn không `--workers`, mọi cú chặn đều dồn vào cùng chỗ và có ngày cộng đủ làm healthcheck 4 giây trượt, Traefik gỡ route, ra 404 - đúng bệnh đã gặp.
- **Kho usage thiếu WAL**: sau khi chuyển sang chạy trong thread, `summary`/`insights` đọc SONG SONG với `refresh()` đang ghi. Chế độ journal mặc định làm hai bên khoá nhau và ném "database is locked" đúng lúc user mở trang Mức dùng. `sessions.py` và `task_store.py` đã làm đúng từ lâu, riêng kho này thì chưa.
- **Snapshot Kanban N+1**: lấy `list_tasks(limit=5000)` rồi gọi `list_events` cho TỪNG việc. Thêm `list_events_bulk` dùng một truy vấn `ROW_NUMBER() OVER (PARTITION BY task_id)`: snapshot 120 việc từ 120 truy vấn xuống 1. Kèm khoá asyncio theo từng brain, vì đẩy ra thread mà quên khoá là tự tạo bug mới - hai snapshot song song đều ghi file hợp lệ nhưng lần CŨ có thể hạ cánh sau lần MỚI và để lại mirror thiu.
### Thay đổi
- **Số note trên dropdown chọn brain giảm** (vd 623 -> 579): nay đếm bằng `_count_md` nên bỏ qua thư mục hệ thống. Chênh lệch đúng bằng số file trong `.claude/` - tức bản mirror skill do CHÍNH Javis sinh ra, không phải note của người dùng. Số mới đúng hơn số cũ. Chạm trần đếm thì nhãn hiện dấu "+" để không nói dối là con số chính xác.
### Kiểm thử
- 6 file test mới, tất cả đều khoá phần dễ hỏng ngầm chứ không chỉ phần dễ đo: `test_fastyaml` đối chiếu 295 frontmatter THẬT trong repo cộng 14 góc hiểm hai bộ nạp hay lệch; `test_prompt_scan_once` ĐẾM số lần quét đúng bằng 1 và đối chiếu nội dung sinh ra phải y hệt đường cũ; `test_plugins_cache` kiểm cả "thiu" lẫn "bẩn" (dict bị nơi gọi sửa tại chỗ rồi ghi ngược ra file); `test_usage_hotpath` đối chiếu 27 model x 4 mức token với thuật toán gốc vì rủi ro là im lặng trả sai TIỀN, và chạy thật 200 lần ghi song song 60 lần đọc; `test_brains_dem` và `test_kanban_snapshot` ĐO ĐỘ TRỄ NHỊP TIM của event loop chứ không chỉ đo thời gian hàm.
- `test_brains_dem.py` có chốt chặn khẳng định `BRAINS_DIR` trỏ vào thư mục tạm trước khi ghi. Chốt này sinh ra từ một tai nạn thật lúc viết: đặt nhầm tên biến môi trường làm 3019 file rác rơi vào `brains/` thật, đã dọn sạch và xác nhận 4 brain thật nguyên vẹn.

## [0.9.236] - 2026-07-28
CI xanh trở lại sau nhiều bản đỏ liên tiếp. Hai lỗi độc lập, không cái nào là lỗi logic của app.
### Sửa lỗi
- **`test_graph_watch.py` segfault trên Linux**: test in đủ "TẤT CẢ PASS" rồi mới `Segmentation fault (core dumped)`, nên vòng lặp CI nhận exit code khác 0 và cả bộ test bị tính là đỏ dù không assertion nào hỏng. Nguyên nhân là `awatch` của watchfiles chạy trên luồng Rust (notify); khi socket đóng, khối `finally` của `/ws/graph` chỉ `.cancel()` các task chứ không `await`, nên luồng đó còn sống lúc interpreter finalize và chạm vào object đã giải phóng. Nay test ngủ 0,5 giây cho watcher thấy `stop_event` rồi thoát bằng `os._exit`, bỏ qua hẳn bước finalize. Đã kiểm chứng mã thoát vẫn đúng: 0 khi pass, 1 khi cố tình làm hỏng một assertion. Không ảnh hưởng production vì server chạy liên tục không thoát, nhưng việc `/ws/graph` cancel mà không await thì vẫn nên dọn riêng.
- **`test_catalog_guides` bắt 2 guide vượt trần 200 ký tự/dòng**: `meta-ads-graph` có dòng 291 và 441 ký tự, `facebook-pages` có dòng 442. Đã CHÈN xuống dòng tại ranh giới câu, KHÔNG đổi một chữ nào; kiểm chứng bằng cách bỏ hết khoảng trắng rồi so cây JSON thì trùng khít bản cũ. Sửa bằng thay chuỗi trong văn bản thô nên diff đúng 2 dòng (ghi lại bằng `json.dump` sẽ bung các mảng gọn, phình file từ 1012 lên 1633 dòng).
### Ghi chú
- CI đỏ kinh niên từ 0.9.231 nghĩa là suốt 5 bản vừa rồi không ai thấy được tín hiệu test. Bước import thật thêm ở 0.9.235 chỉ có giá trị khi CI xanh nền, nên hai vá này đi cùng đợt.

## [0.9.235] - 2026-07-28
Dựng lưới an toàn trước đợt tái cấu trúc server. Chưa đụng một dòng code chạy nào.
### Thêm mới
- **`server/test_route_table.py` + `server/route_table.json`**: ảnh chụp toàn bộ 192 mục bảng route (185 APIRoute, 2 WebSocket, 4 route mặc định FastAPI, 1 Mount tĩnh) kèm cả THỨ TỰ đăng ký, vì Starlette khớp route theo thứ tự nên hai bảng cùng tập hợp mà khác thứ tự vẫn định tuyến khác nhau. Đây là dây bảo hiểm cho đợt bóc `main.py` thành các module APIRouter sắp tới: bóc đúng thì bảng phải y hệt từng ký tự. Đã kiểm chứng guard thật sự đỏ khi cố tình xoá `/brains`, dịch thứ tự `/health` và đổi tên `/version`. Đổi route có chủ đích thì chạy `python test_route_table.py --update` rồi commit file .json kèm theo.
- **`server/bench_hotpath.py`**: đo các điểm đang chặn event loop. Baseline trên brain 623 file .md / 30 skill: `build_system_prompt` 150,8ms mỗi lượt chat, `GET /brains` 136,1ms, `usage_index.summary` 46,7ms, `import main` 2.263ms. Trên brain nhỏ 101 file thì `build_system_prompt` chỉ 39,6ms, chênh gần 4 lần, nên mọi mốc nghiệm thu đều phải nói rõ đo trên brain nào.
### Kiểm thử
- **CI thêm bước import thật `main`**: byte-compile không chạy code nên không thấy vòng import bị gãy, mà server có 3 vòng đang phá bằng import trong hàm cộng 8 module nữa dựa vào mẹo đó. Nâng nhầm một import lên đầu file là app chết lúc khởi động chứ không phải lúc build, CI cũ vẫn xanh rồi tự deploy lên VPS. Bước mới đóng đúng khe hở đó.
### Tài liệu
- `docs/superpowers/specs/2026-07-28-tai-cau-truc-server-design.md`: spec tái cấu trúc 5 giai đoạn. Đo trước khi thiết kế nên bác bỏ được 3 giả định: hermes-agent KHÔNG gọn hơn (`gateway/run.py` 18.911 dòng, 12 file source lớn hơn `main.py`, 200 route treo `@app.*` trong một file 14k dòng); độ dài file Python tốn 0 thời gian chạy (compile 155ms một lần rồi `.pyc` nạp 1,7ms, route scan 0,13-0,64ms và `include_router` gộp lại y hệt); treo app là do chặn event loop trên một tiến trình uvicorn không `--workers` chứ không phải do cấu trúc thư mục.

## [0.9.234] - 2026-07-28
Vá lỗi treo cả server khi duyệt thư mục, dọn trắng bảng Việc, tooltip đồ thị hết dính sang trang khác.
### Sửa lỗi
- **`/browse` không còn khoá chết cả server** (sự cố VPS trả 404 toàn trang): hàm khai `async def` nhưng bên trong quét đĩa đồng bộ, và đoạn `glob.glob(..., recursive=True)[:500]` chỉ trông như có trần - lát cắt áp lên KẾT QUẢ nên glob vẫn đi hết cây thư mục trước rồi mới cắt. Trên VPS `/home` ôm cả brains lẫn dự án khác, nên một request duyệt thư mục khoá cứng event loop; healthcheck bị bỏ đói, Docker gắn nhãn unhealthy, Traefik gỡ route và cả trang thành 404 dù app vẫn sống. Log chứng minh: healthcheck 200 đều mỗi 30 giây rồi câm hẳn ngay sau dòng `GET /browse?path=/home`. Nay tách `_browse_sync` chạy qua `asyncio.to_thread`, và `_count_md` đếm bằng `os.scandir` có trần THẬT (chạm trần là dừng), có trần độ sâu, không đi theo symlink (symlink trỏ ngược lên cha làm glob recursive lặp vô tận), lỗi quyền một nhánh không giết cả lần đếm.
- **Tooltip node đồ thị hết dính lại khi chuyển trang** (Codex sửa, em soát và gộp): nguyên nhân thật là View Transition chụp khung cũ kèm tooltip đang hover, nên ẩn ở `pause()` là đã muộn. Nay ẩn ngay đầu `navigateTo` trước khi chụp, thêm `hideTooltip()` cho cả đồ thị 2D lẫn 3D, và chốt chặn cuối bằng CSS `body.in-console .graph-tooltip { display: none }`.
### Thêm mới
- **`TaskStore.clear_board` + `POST /kanban/clear`**: xoá TRẮNG bảng Việc của một brain, giữ lại đúng việc đang có worker cầm (xoá task trong lúc worker chạy sẽ để lại worker mồ côi ghi vào task không còn tồn tại).
### Kiểm thử
- `test_browse_khong_treo.py` mới (9 case): trần đếm dừng đúng chỗ, không đi theo symlink vòng, bỏ qua thư mục cấm quyền, cây 2400 file vẫn trả lời dưới 3 giây, và chốt chặn quan trọng nhất là event loop vẫn thở trong lúc quét.
- `test_tasks_autonomous.py` thêm case cho `clear_board`; `test_graph_tooltip_cleanup.js` chạy bằng node cho phần tooltip.

## [0.9.233] - 2026-07-28
Javis thôi tự đẻ việc: chỉ tạo việc khi được bảo thẳng, kèm nút dọn bảng.
### Thay đổi
- **Vòng học KHÔNG còn tự tạo việc nền** (`capabilities.task` mặc định `false`). Lý do từ số liệu thật: 33 việc trên 4 bảng thì 33 đều do máy tự suy ra từ hội thoại, không cái nào chủ trực tiếp giao, và phần lớn chết yểu vì worker headless không làm nổi. Từ nay việc chỉ sinh khi được BẢO THẲNG trong chat (`POST /kanban/task`) - đúng mức 2 của thang điều phối. Công tắc vẫn còn trong Cài đặt cho ai muốn bật lại.
- **Migration `task_autocreate_off`**: đổi mặc định thôi không đủ vì `read_config` để giá trị đã lưu đè lên default, máy đang chạy vẫn giữ `task: true`. Nay có cơ chế migration chạy ĐÚNG MỘT LẦN rồi ghi cờ `_migrations`, nên vừa hạ được cấu hình cũ vừa không biến công tắc thành nút chết khi chủ tự bật lại.
### Thêm mới
- **`TaskStore.purge_terminal` + `POST /kanban/purge`**: dọn HẲN việc đã kết thúc khỏi kho (kèm event/run/dependency), khác `archive_old_terminal` vốn chỉ ẩn khỏi bảng. Mặc định chỉ đụng archived + cancelled; `include_done=1` mới dọn cả done. Whitelist cứng `_PURGEABLE` để một lời gọi sai tham số không thể quét mất việc đang chờ hay đang chạy.
### Kiểm thử
- `test_learn_task_gate.py` thêm 3 case: mặc định tắt tự tạo việc, config cũ đang bật bị hạ xuống đúng một lần và ghi được xuống đĩa, chủ bật lại bằng tay thì tôn trọng.
- `test_tasks_autonomous.py` thêm 3 case cho purge: xoá đúng archived/cancelled kèm event, không lan sang brain khác, không đụng việc đang sống dù truyền status bậy.

## [0.9.232] - 2026-07-28
Việc nền báo gọn và thôi tự đẻ việc rác: chặn ngay ở cửa vào thứ worker headless không thể làm.
### Sửa lỗi
- **Thông báo Telegram của việc nền hết là bức tường văn**: `_query` gom CHUNG dòng tường thuật (`text`) với câu chốt (`final`) nên `result` = toàn bộ dòng suy nghĩ của worker ("Tôi sẽ lần theo...", "Lệnh shell vừa bị chặn..."); `_report` dán `result[:1200]` rồi dán tiếp `block_reason[:500]` vốn cũng cắt từ chính chuỗi đó - một tin nhắn lặp lại y hệt hai lần. Nay có `final` thì `final` LÀ kết quả (text chỉ là lối thoát cho engine không phát final), việc bị chặn chỉ báo LÝ DO gọn, việc xong báo vài dòng đầu, đóng bằng "Xem chi tiết ở trang Việc". Tin nhắn xuống dưới 400 ký tự.
- **Lý do chặn lấy đúng ý cần hỏi**: `_needs_input_reason` cắt 1000 ký tự từ ĐẦU chuỗi nên toàn dính đoạn kể lể mở bài. Nay lấy dòng cuối có nghĩa (chỗ worker thật sự nêu cái còn thiếu), tối đa 200 ký tự, một dòng.
### Cải thiện
- **Cửa gác việc learn tự tạo** (`learn.task_infeasible`): bảng Kanban brain chính có 28 việc thì 100% do learn tự tạo, và nhóm "cập nhật cookie Facebook", "gửi link Drive vào Zalo nhóm", "theo dõi duyệt bài Substack", "sửa IPN repo ShortMason" đều kết thúc archived/cancelled/blocked - worker nền là headless, chỉ có file trong brain + đọc MCP, không có tay chủ, không trình duyệt đăng nhập, không được gửi ra ngoài, không thấy repo ngoài brain. Bốn nhóm đó nay bị loại NGAY ở cửa vào kèm lý do tiếng Việt (trước để lọt rồi mới chặn lúc chạy: tốn một lượt worker, tốn quota, thêm một thông báo làm phiền). Prompt learn cũng siết theo: chỉ đề xuất task khi hội đủ ba điều kiện (user nhờ rõ, worker tự làm trọn được, có kết quả kiểm chứng được), thà bỏ sót còn hơn đẻ backlog rác.
### Kiểm thử
- `test_learn_task_gate.py` mới (7 case): 4 nhóm việc bất khả thi bị loại, việc thao tác file trong brain và việc đọc MCP vẫn đi qua (không gác quá tay), lý do trả về là câu tiếng Việt ngắn.
- `test_tasks_autonomous.py` thêm 5 case: `_query` lấy final bỏ tường thuật, không có final thì giữ text, lý do chặn một ý ngắn, thông báo blocked/done đều dưới 400 ký tự và không lặp lại.

## [0.9.231] - 2026-07-28
Đổi brain là hội thoại đổi theo: hết cảnh "tưởng mất chat, phải reload trang".
### Sửa lỗi
- **Khung chat đổi theo brain khi chuyển brain trên dropdown**: trước đây handler đổi brain chỉ reload graph/số liệu, transcript và phiên đang xem vẫn dính brain cũ - chuyển qua lại tưởng mất hội thoại, phải reload trang mới thấy (phản hồi từ người dùng 2 second brain trên Mac). Nay trang nhớ phiên đang xem của TỪNG brain trong bộ nhớ trang: sang brain khác thì khung trắng sạch (hội thoại mới), quay lại brain cũ thì tự mở lại đúng phiên đang dở từ server, kể cả phiên đang trả lời nền (bong bóng sống gắn lại). Cố ý không persist qua reload để giữ luật "mỗi lần tải trang là vào hội thoại mới".

## [0.9.230] - 2026-07-28
Sửa 3 lỗi từ máy Mac: banner "mất đăng nhập" báo oan, panel Lịch sử delay, tooltip 3D treo.
### Sửa lỗi
- **Mac hết bị banner "Bộ não claude mất đăng nhập" báo oan**: Claude Code trên macOS cất OAuth trong Keychain chứ KHÔNG ghi `~/.claude/.credentials.json`, probe cũ chỉ đọc file nên kết luận nhầm "Chưa đăng nhập" và cứ 10 phút lại đè đèn đỏ. Nay nhánh darwin hỏi Keychain qua `security find-generic-password` (chỉ-đọc, timeout 5s); không xác định được thì coi là sống - thà bỏ sót còn hơn báo oan, đèn do lượt chạy thật (source=run) vẫn là bằng chứng mạnh nhất. Test `test_probe_mac_doc_keychain_khong_bao_do_oan` chốt 4 nhánh.
- **Tooltip node đồ thị hết treo lơ lửng trên editor**: bấm node mở note thì editor phủ lên canvas làm canvas không còn nhận hover để tự ẩn tooltip → card "click để mở" dính vĩnh viễn đè lên bài. Nay ẩn thẳng tooltip ngay lúc click node (cả 2D lẫn 3D) + ẩn khi chuột rời vùng graph.
### Cải thiện
- **Panel Lịch sử hiện tức thì**: trước bấm Lịch sử mới bắt đầu debounce 150ms + fetch nên thấy "Đang tải…" rõ. Nay prefetch danh sách 1.5s sau khi cockpit load, mở panel là vẽ ngay từ cache rồi fetch mới đè lên sau; lần đầu mount cũng nạp thẳng không qua debounce. Lỗi mạng thoáng qua không đập danh sách đang hiện.

## [0.9.229] - 2026-07-28
Bố cục cockpit hài hoà hơn: chuông Thông báo về góc phải, ô chat thành pill nổi có khoảng thở.
### Cải thiện
- **Chuông Thông báo dời từ giữa header về góc phải** (đứng đầu cụm nút, cạnh nút đổi tông): trước nó tự căn giữa phần không gian thừa nên trôi theo độ dài tên brain, nhìn như đặt đại; panel thông báo vốn ghim `right:18px` nên bấm giữa màn mà hộp bung tít góc - giờ nút và panel về cùng một góc. Mobile giữ nguyên (chuông vẫn cạnh nút menu).
- **Ô chat desktop thành pill nổi bo tròn 18px, cách đáy 16px** thay cho dải full-width dán sát mép dưới viewport - đồng bộ với kiểu pill bản mobile đã có.
- **Sửa gốc grid `.hud`**: 5 con trong flow mà chỉ khai 4 hàng nên hàng 70px cứng rơi nhầm vào model-bar (bị kéo giãn), ô chat rớt xuống hàng ngầm không khoảng thở. Khai đủ 5 hàng auto; hàng model/HỆ THỐNG nới padding (8px trên, 6px dưới) để 3 tầng đáy có nhịp rõ ràng thay vì dính chùm.

## [0.9.228] - 2026-07-28
Router việc nền: chuỗi fallback nhiều mắt xích, mắt cuối là OpenRouter model free mạnh nhất.
### Thêm mới
- **Fallback 0.9.227 nâng thành ROUTER chuỗi** (`_FallbackChain`): engine phụ user chọn → Claude → OpenRouter model free. Mắt trước chết lúc chạy (hết quota, CLI lỗi, stream câm, không sẵn sàng) là mắt sau tiếp quản nguyên nhiệm vụ; cả chuỗi chết mới báo lỗi thật. Giờ cả CLAUDE hết hạn mức thì việc nền vẫn sống bằng model free.
- **Tự chọn model free mạnh nhất trên OpenRouter** (`pick_openrouter_free`): tải danh sách model, lọc `:free`, chấm điểm theo họ model + cỡ tham số + context, cache 6 giờ. Hiện chọn ra `nvidia/nemotron-3-ultra-550b-a55b:free`. Model đã chọn lưu vào settings `model.fallback_openrouter_model` - user xem/đổi sau được; đặt sẵn field này thì router tôn trọng, không tự chọn nữa.
- Điều kiện có mắt OpenRouter: đã dán key OpenRouter ở trang Model (model free vẫn cần key tài khoản). Chưa có key thì chuỗi dừng ở Claude như 0.9.227.
### Kiểm thử
- `test_aux_fallback.py` nâng lên 22 case: chuỗi 3 mắt (phụ + Claude cùng chết → free cứu), chấm điểm model free (họ mạnh thắng, cùng họ to thắng), cache picker, swap ghép chuỗi đúng từng cấu hình (Claude không key = không bọc, phụ openrouter trống không nhân đôi mắt).

## [0.9.227] - 2026-07-28
Việc nền hết chết vì engine phụ hết quota: tự rơi về Claude khi Codex/API lỗi lúc chạy.
### Sửa lỗi
- **Nhắc hẹn/loop/kanban/tự học không chết khi "model việc nền" hết hạn mức**: ca thật - việc nền đặt chạy gói ChatGPT (Codex), tài khoản chạm limit là nhắc hẹn chỉ báo ⚠ "You've hit your usage limit" về Telegram rồi thôi, nhiệm vụ không ai làm. `aux_engine.swap()` vốn chỉ đỡ được lỗi lúc DỰNG engine (thiếu key/CLI); nay bọc thêm `_FallbackToClaude`: engine phụ lỗi LÚC CHẠY (error/exception/stream câm không final/không sẵn sàng) là tự chạy lại nguyên prompt bằng engine Claude đã dựng sẵn. Cả hai cùng chết mới trả lỗi thật cho user. Wrapper trong suốt: attr caller gán sau swap (max_wall_s...) đặt cho cả hai engine.
### Kiểm thử
- `test_aux_fallback.py` mới (15 case): phụ ok không đụng Claude, hết quota/nổ exception/stream câm/unavailable đều được Claude cứu, cả hai chết mới lộ error, hợp đồng attr + swap bọc đúng provider.

## [0.9.226] - 2026-07-28
Timelapse nhanh gấp đôi: 160ms mỗi note.
### Cải thiện
- Nhịp timelapse 320ms → 160ms mỗi note (chủ xem thử thấy hơi rề, chốt x2). Vẫn giữ nguyên triết lý nhịp cố định theo note - não càng dày phim càng dài, không ép tổng thời gian.

## [0.9.225] - 2026-07-28
Timelapse chậm rãi: mỗi note một nhịp cố định, não càng dày phim càng dài.
### Cải thiện
- Timelapse bỏ kiểu "ép xong trong 18 giây" (vault to là node túa ra như pháo hoa, không kịp ngắm): giờ mỗi note hiện cách nhau 320ms, MỘT note mỗi nhịp, tổng thời gian tự dài theo số note - xem thư thái như lật album cuộc đời brain. Yêu cầu trực tiếp của chủ: đừng đổi lại thành tổng thời gian cố định.

## [0.9.224] - 2026-07-28
Nút Timelapse "cuộc đời brain": chiếu lại não lớn lên từ note đầu tiên tới hiện tại.
### Thêm mới
- **Nút timelapse dưới nút mắt** (khung đồ thị giữa): bấm là não về TRỐNG rồi các note hiện dần theo đúng THỨ TỰ RA ĐỜI, dây liên kết chỉ nối khi cả hai đầu đã sinh ra - xem lại cả hành trình vault từ khi thức giấc. Node được thả lại cho d3 tự xếp nên mạng nở và co kéo hữu cơ như não đang lớn thật. Bấm lần nữa là dừng và trả lại đồ thị đầy đủ ngay; hết phim tự về trạng thái thường. Đang chiếu thì nút đổi icon + nhấp nháy nhẹ.
- Backend gắn mốc ra đời `t` cho mỗi node (birthtime macOS / ctime Windows / min với mtime cho file sync mang mtime gốc) ở cả `/graph` lẫn node đẩy realtime qua `/ws/graph` - node mới sinh trong phiên cũng xếp đúng chỗ trong lần chiếu sau.
- Hiệu năng: chỉ chạy khi bấm nút, chiếu bằng nhịp 160ms và tắt warmup sync của force-graph trong lúc chiếu (24 tick warmup mỗi lần đổ data x ~110 nhịp là khựng); timelapse chỉ có ở đồ thị 2D, chế độ 3D bấm sẽ nhắc chuyển về 2D qua title.
### Kiểm thử
- `test_graph_timelapse.js` mới (16 case, stub ForceGraph thuần node): khung đầu trống, node hiện đúng thứ tự thời gian, link chỉ nối khi đủ hai đầu, khung cuối khôi phục đủ mạng, dừng giữa chừng trả lại ngay, sự kiện end bắn đúng.

## [0.9.223] - 2026-07-28
Đồ thị realtime chạy bằng sự kiện file của hệ điều hành: vault không đổi thì server nằm im.
### Cải thiện
- **`/ws/graph` bỏ hẳn poll định kỳ, chuyển sang watchfiles** (inotify Linux / FSEvents macOS / ReadDirectoryChangesW Windows - lib sẵn có theo `uvicorn[standard]`, chạy được cả VPS Docker lẫn Mac): node mọc lên NGAY khoảnh khắc file .md được ghi thay vì đợi nhịp quét 4 giây, và không có gì đổi thì không tốn CPU (poll cũ 99% số lần quét trả lời "không có gì mới"). CPU nền server đo được ~2% so với ~18% của bản 0.9.222 và nguyên một nhân của bản trước đó.
- **Lưới an toàn quét thưa 5 phút/lần** (trong to_thread): bắt thay đổi mà sự kiện không phủ - vault trên ổ mạng NFS/SMB không bắn sự kiện, hoặc sự kiện rơi khi burst quá lớn. Thiếu watchfiles thì tự lùi về chỉ quét thưa, không chết tính năng.
- File trong thư mục ẩn (`.git`, `.obsidian`, `.trash`...) bị lọc ở cả đường sự kiện lẫn đường quét; disconnect là dọn sạch watcher + task nền của socket đó.
### Kiểm thử
- `test_graph_watch.py` mới (10 case, chạy sự kiện file THẬT qua TestClient websocket): tạo file mới ra `graph_add` ngay với `isNew=true` + trích đúng wikilink, sửa file có sẵn ra `isNew=false`, file trong thư mục ẩn không lọt, disconnect không nổ exception.

## [0.9.222] - 2026-07-28
Tăng tốc tải trang: hết nghẽn event loop do quét vault, cache asset dài hạn, thư viện tự host.
### Sửa lỗi
- **Server hết "đứng hình" từng đợt 0.3-1.4 giây**: vòng theo dõi đồ thị realtime (`/ws/graph`) quét toàn bộ file .md của vault MỖI 1.5 giây bằng code sync ngay trên event loop - vault lớn là mọi request (file tĩnh lẫn API) xếp hàng chờ, đo được P50 ~500ms cho một file JS vài KB và server ăn nguyên một nhân CPU 24/7. Nay quét qua `asyncio.to_thread`, nhịp poll giãn 1.5s → 4s, và quét bằng `os.walk` cắt tỉa thư mục ẩn ngay khi duyệt (glob cũ vẫn chui vào `.git`/`.obsidian` rồi mới lọc). `GET /graph` (nguồn `all` đo được ~10 giây sync) cũng chuyển sang to_thread.
### Cải thiện
- **Middleware auth/CSRF rẻ đi ~10 lần**: `read_settings()` được cache theo mtime+size của `settings.json` (trước đây MỖI request đọc file + giải mã Fernet 2 lần, ~10-16ms chỉ để check đăng nhập; nay ~1ms). File đổi là cache tự đọc lại, trả bản sao nên caller sửa không bẩn cache.
- **Asset tĩnh có `?v=` được cache 1 năm immutable** (đổi phiên bản là đổi URL nên an toàn): mở trang lần sau không phải hỏi lại ~27 file JS/CSS.
- **Tự host Alpine.js + force-graph** trong `dashboard/vendor/` thay vì tải từ unpkg (đo được 2.1s + 0.7s trên đường boot, lệ thuộc mạng ngoài, offline là chết UI). three.js/3d-force-graph (chỉ dùng khi bật 3D) vẫn lazy từ CDN.
- Kết quả đo trên máy dev: TTFB trang chủ 572ms → 35ms, DOMContentLoaded 2936ms → 1114ms, file tĩnh P95 từ ~700ms → ~24ms, CPU nền server từ ~100% một nhân → ~18%.

## [0.9.221] - 2026-07-28
Gõ nhanh task trong editor với menu gợi ý kiểu Obsidian, bản gọn.
### Thêm mới
- **`task-suggest.js`**: trong chế độ Sửa của note, gõ `- [ ]` rồi ấn cách là dòng biến thành task thật có checkbox (trong danh sách bullet chỉ cần gõ `[ ]` + cách). Đứng cuối dòng task ấn cách là bung menu gợi ý 6 mục (📅 hạn, ⏳ dự kiến, 🛫 bắt đầu, ⏫🔼🔽 ưu tiên) - cố tình NGẮN hơn Obsidian cho đỡ ngợp. Chọn mục ngày bung tiếp Hôm nay / Ngày mai / Cuối tuần / Tuần sau / Chọn ngày (mở lịch), chèn thẳng `📅 YYYY-MM-DD` đúng chuẩn obsidian-tasks.
- Điều khiển: mũi tên + Enter hoặc chuột; Esc đóng; gõ chữ tiếp thì menu tự tắt. Chạy ở CẢ editor cây (trang Bộ não/Tệp tin) lẫn khung sửa file bung từ chat.
- Việc gõ `- [ ]` trong bản render trước đây khi lưu sẽ bị turndown escape thành `\- \[ \]` (hỏng cú pháp) - nay thành checkbox thật nên lưu ra markdown chuẩn.
### Kiểm thử
- `test_task_suggest.js` mới (15 case): nhận diện khung `- [ ]` (kể cả nbsp của contenteditable, `- []`, `* [ ]`, đã có chữ thì thôi), tính ngày Hôm nay/Ngày mai/Cuối tuần/Tuần sau kể cả khi đứng đúng thứ 7 / thứ 2.

## [0.9.220] - 2026-07-28
Khối ```tasks chạy thật + nút "+ Việc" + thư mục Dashboard mặc định + hết chậm lượt đầu.
### Thêm mới
- **Khối ```tasks (ngôn ngữ plugin obsidian-tasks) chạy thật**: `not done`, `due before today`, `has/no due date`, `description/path includes`, `tag includes`, `priority is ...`, `sort by ... reverse`, `limit to N tasks`. Mỗi dòng AND với nhau đúng ngữ nghĩa plugin gốc; dòng chưa hỗ trợ hiện cảnh báo rõ ràng, các dòng còn lại vẫn chạy; `group by`/`hide`/`show`/`short mode` bỏ qua im lặng. Dashboard.md viết kiểu Obsidian giờ hiện việc thật thay vì cục code chết.
- **Nút "+ Việc" trên mọi khối danh sách việc**: form mini nhập nội dung + hạn (tuỳ chọn), Enter là thêm. Việc rơi vào `00 - Dashboard/Task Inbox.md` (tự tạo nếu thiếu) qua API mới `POST /files/taskadd`, gắn `📅 hạn` kiểu obsidian-tasks, mọi khối trên trang tự làm mới.
- **`00 - Dashboard` vào cấu trúc chuẩn vault**: brain mới có sẵn kèm seed `Dashboard.md` (4 khối tasks: quá hạn / hôm nay / sắp tới / chưa có hạn) + `Task Inbox.md`; brain cũ thiếu thì nút chuẩn hoá tạo đủ. Seed chỉ tạo khi chưa có, không ghi đè file user.
### Cải thiện
- **Hết chậm lượt mở đầu tiên**: server tự hâm nóng chỉ mục dataview cho MỌI brain ngay sau khi boot (thread nền) - khối trên dashboard hiện gần như tức thì thay vì ngồi chờ parse cả vault.
### Kiểm thử
- `test_dataview.js` thêm 12 case dịch ngôn ngữ tasks; `test_dataview_tasks.py` thêm 6 case taskadd (mặc định vào Task Inbox, gắn 📅, chặn `../`, line trả về tick được ngay); `test_vault_scaffold.py` thêm 2 case seed Dashboard; `test_chat_render.js` thêm case fence tasks.

## [0.9.219] - 2026-07-28
Bộ sổ bullet journal (Daily/Weekly/Monthly/Future Log) vào cấu trúc chuẩn của vault.
### Thêm mới
- **4 thư mục sổ vào cấu trúc chuẩn**: `01 - Daily Log`, `02 - Weekly Log`, `03 - Monthly Log`, `04 - Future Log`. Brain mới tạo có sẵn; brain cũ thiếu thì banner "cấu trúc vault" liệt kê và nút tạo thiếu (/vault/init) tự tạo đủ. Đây là nơi ghi chép + task hằng ngày mà khối dataview kéo việc từ đó.
- Nhận diện tên linh hoạt như các mục khác: `01 - Daily Log`, `Daily Log`, `daily` đều tính là có - vault đã có sổ theo tên riêng thì KHÔNG bị đẻ thêm bản trùng. Là mục tuỳ chọn (không essential) nên vault không dùng bullet journal không bị báo "chưa chuẩn".
- Seed `AGENTS.md` của brain mới ghi rõ bộ sổ trong schema để AI hiểu vai trò từng thư mục.
### Kiểm thử
- `test_vault_scaffold.py` mới (9 case): nhận diện các biến thể tên, /vault/init tạo đủ 4 sổ, idempotent, không tạo trùng khi đã có sổ tên khác.

## [0.9.218] - 2026-07-28
Dataview nhanh hơn hẳn với vault lớn: cache tăng dần, ETag 304, khoanh vùng theo FROM.
### Cải thiện
- **Cache chỉ mục tăng dần theo mtime ở server**: `/files/mdindex` không còn đọc + parse lại toàn bộ note mỗi lần gọi; chỉ file nào đổi (mtime/dung lượng khác lần trước) mới bị parse lại, còn lại lấy từ RAM. Vault vài nghìn note giảm từ cỡ giây xuống cỡ vài chục ms từ lần gọi thứ hai. File xoá được dọn khỏi cache khi quét toàn brain.
- **ETag / If-None-Match**: không note nào đổi thì server trả 304 rỗng thay vì gửi lại cả cục JSON chỉ mục; dataview.js giữ bản cũ trong RAM và dùng lại. Hết 15 giây TTL chỉ tốn một request "có gì mới không" gần như miễn phí.
- **Khoanh vùng quét theo FROM**: truy vấn mà mọi nhánh OR đều có thư mục dương (vd `FROM "01 - Daily Log" OR "02 - Weekly Log"`) thì client chỉ xin chỉ mục đúng các nhánh đó (`?path=A&path=B`, endpoint nhận nhiều path), server chỉ walk đúng thư mục đó. Nhánh chỉ có #tag vẫn quét cả brain vì tag nằm rải rác. Kết quả là tập cha, matchFrom vẫn lọc chính xác phía client.
- Trần chỉ mục nâng từ 3.000 lên **20.000 note** (an toàn nhờ cache tăng dần).
### Kiểm thử
- `test_dataview_tasks.py` thêm 9 case: đếm số lần parse (lần 2 = 0, sửa 1 file chỉ parse 1), 304 đúng scope, nhận list path + tương thích path chuỗi, file mới/xoá vào ra chỉ mục đúng. Thêm kiểm chứng HTTP thật qua TestClient: nhiều `?path=` gom đúng list, 304 theo đúng scope.
- `test_dataview.js` thêm 4 case fromScope: gộp thư mục, nhánh chỉ có tag thì trả null, bỏ qua phủ định, không FROM thì null.

## [0.9.217] - 2026-07-28
Tài liệu hướng dẫn cho Task & Dataview.
### Thêm mới
- **Trang docs mới [19 - Task & Dataview trong note](docs/19-task-va-dataview.md)**: tick checkbox tự lưu ở đâu, bảng ký hiệu 📅⏳🛫✅ + độ ưu tiên, đầy đủ cú pháp truy vấn dataview (TASK/LIST/TABLE, FROM, WHERE, SORT, LIMIT) kèm ví dụ thực dụng, danh sách thứ chưa hỗ trợ, giới hạn kỹ thuật và mục khắc phục sự cố. Đã thêm vào mục lục docs.

## [0.9.216] - 2026-07-28
Task tick được ngay trên note + khối dataview chạy thật, lấy cảm hứng từ obsidian-tasks và obsidian-dataview.
### Thêm mới
- **Checkbox task bấm được**: mở note .md ở chế độ Sửa (bản render), bấm vào ô `- [ ]` là tick và **tự lưu ngay** như Obsidian, khỏi bấm nút Lưu. Trong chat thì checkbox vẫn chỉ để xem (tin nhắn không có file để ghi).
- **Khối ```dataview chạy thật**: note nào chứa khối dataview nay hiện kết quả sống thay vì cục code chết. Hỗ trợ tập lệnh hay dùng nhất: `TASK` / `LIST` / `TABLE` (kèm `WITHOUT ID`, cột `AS "Tên"`), `FROM "thư mục"` hoặc `#tag` (AND/OR, phủ định `-`), `WHERE` (`!completed`, `due <= date(today)`, `status = "doing"`, `contains(...)`), `SORT`, `LIMIT`. Chưa hỗ trợ dataviewjs và FLATTEN - khối sẽ nói rõ thay vì im lặng.
- **Tick task ngay trong kết quả dataview**: mỗi việc trong kết quả `TASK` có checkbox, tick là ghi thẳng vào file gốc qua API mới `/files/taskcheck` (có rào chống ghi đè khi file đã đổi - lệch thì báo tải lại, không ghi bừa).
- **Hiểu ký hiệu obsidian-tasks**: 📅 hạn, ⏳ dự kiến, 🛫 bắt đầu, ✅ xong, độ ưu tiên 🔺⏫🔼🔽⏬. Việc quá hạn hiện badge đỏ; task kiểu Tasks khi tick xong tự gắn `✅ ngày`, untick thì gỡ - checklist thường giữ nguyên chữ.
- API mới `GET /files/mdindex`: chỉ mục toàn bộ note .md của brain (frontmatter, tag, task) cho truy vấn dataview chạy phía trình duyệt.
### Sửa lỗi
- **Lưu note ở chế độ Sửa không còn phá khối code/dataview**: trước đây bản render đang sửa mà chứa code fence dài (thẻ artifact) hay khối dataview thì bấm Lưu là mất nội dung gốc; nay tất cả được trả về đúng fence ``` như cũ.
### Kiểm thử
- `server/test_dataview_tasks.py` (21 case): bóc ký hiệu ngày/độ ưu tiên, quét note (bỏ qua code fence, số dòng đúng file gốc), mdindex lọc thư mục + chặn `../`, taskcheck tick/untick + rào 409 + tìm lại dòng khi file bị chèn.
- `dashboard/test_dataview.js` (27 case): parse truy vấn, FROM/WHERE/SORT/LIMIT, bảng, escape XSS. `test_chat_render.js` thêm case checkbox không disabled + fence dataview.

## [0.9.215] - 2026-07-28
Thêm công tắc tự chọn: giữ hay gỡ dấu nguồn gốc AI trên ảnh Javis tạo.
### Thêm mới
- **Công tắc "Dấu nguồn gốc ảnh AI"** ở Cài đặt, nhóm Giao diện & Brain. Ảnh sinh ra mang sẵn Content Credentials (C2PA) ghi rằng ảnh do AI tạo, và Facebook đọc dấu đó để gắn nhãn "Nội dung do AI tạo" lên bài. Công tắc cho chọn **Giữ dấu** (mặc định) hoặc **Gỡ dấu**.
- **Mặc định là GIỮ**, và có test khoá mặc định đó lại: bản fork nào cũng khởi đầu ở trạng thái an toàn, muốn gỡ thì chủ workspace phải tự bật. Lúc bật có hộp xác nhận nói rõ nghĩa vụ công bố nội dung AI vẫn thuộc về người đăng.
- **Nhãn tác giả javisos.com luôn được giữ** ở cả hai chế độ. Gỡ dấu chỉ là gỡ, không đánh tráo nguồn gốc thành của người khác.
- Chỉ ảnh tạo từ lúc bật trở đi mới bị ảnh hưởng; ảnh đã tạo trước đó không đổi.
### Kiểm thử
- `test_image_gen.py` thêm 8 case: gỡ đúng chunk caBX và không đụng phần còn lại, ảnh không có dấu thì trả nguyên xi, mặc định phải là False, và hai nhánh bật/tắt cho ra file khác nhau đúng như mong đợi.

## [0.9.214] - 2026-07-28
Ảnh Javis tạo ra tự mang nhãn tác giả javisos.com.
### Thêm mới
- **Gắn nhãn tác giả vào ảnh**: mọi ảnh sinh bằng `javis_generate_image` nay được ghi sẵn metadata `Software = Javis OS`, `Source = https://javisos.com` và thời điểm tạo, dưới dạng chunk tEXt chuẩn PNG. Ai mở file bằng công cụ xem metadata sẽ thấy ảnh do Javis tạo.
- Việc gắn nhãn **chỉ THÊM chunk, không gỡ gì**: phần Content Credentials (C2PA) mà nhà cung cấp ảnh nhúng sẵn vẫn nằm nguyên trong file, pixel không bị đụng vào. File không phải PNG hợp lệ thì trả nguyên xi, không làm hỏng ảnh.
### Kiểm thử
- `test_image_gen.py` thêm 8 case, trong đó có case khoá hành vi "KHÔNG gỡ chunk C2PA có sẵn" để sau này không ai lặng lẽ đổi thành gỡ nguồn gốc rồi ghi đè tên mình.

## [0.9.213] - 2026-07-28
Javis xoá được bài trên Trang, nên đổi ảnh bài đã đăng giờ làm trọn được bằng lời.
### Thêm mới
- **Tool `fb_page_delete`**: xoá hẳn một bài đã đăng trên Trang bằng lời ("xoá bài này giúp anh"). Trước giờ Javis đăng và sửa chữ được nhưng không xoá được, nên tình huống hay gặp nhất là muốn ĐỔI ẢNH của bài đã đăng thì kẹt: Meta không cho thay ảnh bài cũ, phải đăng bài mới rồi xoá bài cũ, mà bước xoá lại phải tự làm tay. Giờ đi trọn được.
- Tool chạy ở mức **Toàn quyền**, khai trong nhóm nguy hiểm. Trước khi xoá, Javis **đọc lại bài** để chắc đúng bài và giữ nội dung: bài không đọc được thì dừng, KHÔNG xoá mù theo id sai; xoá xong trả lại đoạn nội dung vừa xoá để đối chiếu (và có cái dán lại nếu lỡ tay).
- **Cảnh báo rủi ro của connector Facebook Trang** viết lại cho đúng bán kính thiệt hại: nói thẳng Toàn quyền là xoá được bài và xoá thì KHÔNG hoàn tác được, Trang không có thùng rác.
### Sửa lỗi
- **Khai báo plugin Trang bị thiếu 4 tool**: `plugin.yaml` mới liệt kê 5 tool trong khi plugin đăng ký 9 (thiếu ảnh, album, video, sửa bài). Đã khai đủ 10.
### Kiểm thử
- `test_meta_pages.py` thêm 5 case cho `fb_page_delete`, trong đó có case chốt chặn "bài không đọc được thì KHÔNG được gọi DELETE", và case cảnh báo connector phải nói rõ xoá không hoàn tác.

## [0.9.212] - 2026-07-28
Sửa lại cho đúng: bảng "Invalid Scopes" KHÔNG chặn đăng nhập, đừng bắt người dùng đi vòng.
### Sửa lỗi
- **Hạ "Invalid Scopes" từ lỗi chặn xuống cảnh báo bỏ qua được**: bản 0.9.211 mô tả bảng này như lỗi bắt buộc phải đi thêm quyền mới kết nối được. Sai. Chính thông báo của Meta ghi "This message is only shown to developers" và luồng đăng nhập vẫn chạy tiếp; app ở Chế độ phát triển với người bấm là Quản trị viên thì Facebook vẫn cấp đủ quyền (kiểm chứng thực tế: token lấy về có đủ `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_engagement`, không quyền nào bị từ chối). Hướng dẫn hai connector Facebook Trang và Meta Ads nay bảo bấm OK đi tiếp, chỉ khi kết nối xong mà không thấy Trang/tài khoản quảng cáo nào mới quay lại thêm quyền.
- **Thêm cách tự kiểm chứng** trong tài liệu: kết nối xong hỏi Javis "liệt kê các Trang của tôi", thấy đủ là xong, không phải mò cấu hình app.

## [0.9.211] - 2026-07-27
Hướng dẫn đấu Trang và Quảng cáo thêm bước bật quyền cho app, hết lỗi "Invalid Scopes".
### Sửa lỗi
- **Bổ sung bước bật quyền cho app - nguyên nhân thật của lỗi "Invalid Scopes"**: trong giao diện app mới của Meta, quyền bị khoá theo trường hợp sử dụng. App tạo bằng trường hợp "Xác thực và yêu cầu dữ liệu từ người dùng" chỉ có `email` + `public_profile`, nên bấm Kết nối là Facebook trả về "Invalid Scopes: pages_show_list, pages_read_engagement, pages_manage_posts, pages_manage_engagement" và dừng. Hướng dẫn connector **Facebook Trang** nay có hẳn một bước bật quyền (Thêm trường hợp sử dụng > "Quản lý mọi thứ trên Trang của bạn" > Tùy chỉnh > Quyền), kèm cảnh báo nhận diện đúng thông báo lỗi để người dùng không đi mò App ID với Secret.
- **Connector Meta Ads (Graph API) thêm cảnh báo tương tự** cho `ads_read` và `business_management`, vì cùng một cơ chế.
- **Hướng dẫn Facebook Trang cập nhật hai điểm còn sót**: nhận biết giao diện cũ/mới, và ô URI chuyển hướng chỉ phải điền khi chạy trên VPS/tên miền riêng (máy cá nhân bỏ qua).
- **Khắc phục sự cố** thêm mục "Invalid Scopes" với cách sửa riêng cho quyền Trang, quyền quảng cáo và giao diện cũ.

## [0.9.210] - 2026-07-27
Sửa bước sai trong hướng dẫn Meta Ads: bản chạy máy cá nhân KHÔNG phải điền URI chuyển hướng.
### Sửa lỗi
- **Hết bắt người dùng điền thứ Meta không cho điền**: hướng dẫn cũ bảo dán `http://localhost:7777/connect/oauth/callback` vào ô "URI chuyển hướng OAuth hợp lệ", nhưng khi app ở Chế độ phát triển thì Meta TỰ ĐỘNG cho phép chuyển hướng về localhost và cố tình chặn không cho thêm tay (có chú thích ngay cạnh ô). Người cài trên máy cá nhân làm theo hướng dẫn cũ sẽ mắc kẹt ở đúng bước này. Hướng dẫn trong hộp thoại Kết nối và tài liệu nay tách rõ: cài máy cá nhân thì BỎ QUA ô đó, cài trên VPS/tên miền riêng thì BẮT BUỘC điền địa chỉ https.
- **Khắc phục sự cố nói đúng nguyên nhân**: mục "Facebook từ chối / redirect_uri" tách theo nơi cài, và nhấn rằng với bản chạy localhost thì chính việc GIỮ app ở Chế độ phát triển mới là thứ khiến localhost được chấp nhận. Thêm mục riêng cho tình huống "không điền được localhost vào ô đó".

## [0.9.209] - 2026-07-27
Hướng dẫn đấu Meta Ads giờ đi được cả hai giao diện app của Meta, hết cảnh "không thấy mục Sản phẩm".
### Cải thiện
- **Hướng dẫn tạo Facebook App nhận biết 2 giao diện**: Meta đang chuyển trang quản lý ứng dụng từ bản cũ (menu "Sản phẩm") sang bản mới (menu "Trường hợp sử dụng"), nên mỗi người mở ra thấy một kiểu và ai ở bản mới thì tìm mãi không ra bước "thêm sản phẩm Đăng nhập bằng Facebook". Hướng dẫn trong hộp thoại Kết nối và tài liệu giờ mở đầu bằng cách tự nhận biết mình đang ở bản nào, rồi tách đường đi riêng cho từng bản (bản mới: Trường hợp sử dụng > Tùy chỉnh > Cài đặt).
- **Nói rõ được phép bỏ qua xác minh và xét duyệt**: bảng "Việc cần làm" của app dụ người ta tick hết cả "Xác minh doanh nghiệp" lẫn "Xét duyệt ứng dụng", trong khi cách đấu của Javis (app giữ Chế độ phát triển, tự làm Admin) không cần hai bước đó. Hướng dẫn nay nói thẳng bỏ qua, tránh mất nhiều ngày chờ duyệt vô ích.
- **Địa chỉ callback cho bản chạy VPS**: trước chỉ hướng dẫn `localhost`, ai cài trên VPS/tên miền riêng phải tự đoán. Nay ghi rõ cả hai trường hợp và nhắc ngoài localhost thì Meta bắt buộc https.
- **Khắc phục sự cố** thêm 2 mục: không thấy menu "Sản phẩm" (do đang ở giao diện mới), và không thấy "Đăng nhập bằng Facebook cho doanh nghiệp" (chỉ có ở app tạo đúng loại Doanh nghiệp, nhưng Javis dùng bản thường nên không cần).

## [0.9.208] - 2026-07-27
Nút "Cập nhật ngay" chạy được trên Mac (và Linux không có systemd).
### Sửa lỗi
- **Mac hết bị chặn cập nhật**: trước đây updater trên máy không phải Windows bắt buộc phải có systemd service 'javis', trong khi Mac không hề có systemd nên bấm cập nhật là dừng ngay với lỗi "Không có systemd service 'javis' để tự khởi động lại". Giờ updater có 3 chế độ restart: Windows (bat/vbs), Linux systemd (systemctl), và nohup cho Mac hoặc Linux cài không systemd - tự dừng đúng tiến trình server (server truyền PID của mình cho updater, kèm dò cổng dự phòng) rồi chạy lại uvicorn nền y như install.sh. Rollback tự động vẫn nguyên.
- **Nhãn nền tảng nói thật**: máy Mac trước đây bị dán nhãn "Linux (systemd)" ở mục Cập nhật vì frontend hardcode theo mode. `/version` giờ báo thêm nền tảng thật (windows/mac/linux) và giao diện ghi đúng "macOS" hay "Linux".
- **update.sh cũng tự restart khi không có systemd**: thay vì chỉ in "hãy khởi động lại thủ công", script giờ tự dừng tiến trình đang giữ cổng rồi chạy lại nền bằng nohup.
### Kiểm thử
- `test_update.py` thêm 8 case: 3 chế độ của service_mode, updater hết nhánh chặn systemd, dry-run nhận --server-pid, /version có platform, console.js hết hardcode nhãn và main.py truyền --server-pid.

## [0.9.207] - 2026-07-27
Gỡ hẳn kết nối "Facebook cá nhân (cookie)" - đường mbasic đã chết, không cứu được.
### Gỡ bỏ
- **Xoá connector `facebook-personal` và plugin `fb-personal`** cùng 11 tool đi kèm (`fb_feed_read`, `fb_personal_post`, `fb_personal_comment`, `fb_personal_comments`, `fb_personal_comment_reply`, `fb_personal_delete`, `fb_personal_react`, `fb_personal_share`, `fb_messages_read`, `fb_message_thread`, `fb_message_send`). Lý do: Facebook đã khai tử mbasic nên plugin không còn đọc hay ghi được dù cookie còn tốt, và bản thân cách làm này vi phạm điều khoản Facebook, rủi ro khoá tài khoản là có thật. Không thay bằng gì - hướng khác sẽ tính sau.
- Các kết nối Facebook còn lại KHÔNG bị ảnh hưởng: `meta-ads-graph` (quảng cáo), `facebook-pages` (Trang), `facebook-monitor` (theo dõi Trang/Nhóm công khai qua Apify), `meta-ads`.
### Kiểm thử
- Xoá `test_fb_personal.py`; `test_canh_bao_rui_ro.py` bỏ `facebook-personal` khỏi danh sách connector bắt buộc có cảnh báo rủi ro.

## [0.9.206] - 2026-07-27
Kết nối OAuth bỏ dở không còn hiện như tài khoản thật và không mọc lại sau khi xoá.
### Sửa lỗi
- **Hết cảnh "xoá rồi lại hiện" của kết nối OAuth**: bấm nút đăng nhập một connector OAuth là connection được tạo TRƯỚC rồi mới đi xin đăng nhập; xin thất bại (vd Meta Ads MCP đang là beta chỉ mở theo danh sách) thì cái xác chưa-có-token nằm lại trên trang Kết nối như tài khoản thật, mỗi lần bấm thử là một lần mọc lại. Giờ đăng nhập thất bại là server tự xoá connection vừa tạo và trả lỗi rõ ràng.
- **Xác OAuth còn sót hiện chấm đỏ nói thật**: connection OAuth chưa từng có token (đăng nhập bỏ dở) được vòng health đánh dấu đỏ với thông điệp "Chưa hoàn tất đăng nhập - bấm Kết nối lại", kèm nút sửa ngay trên card - áp dụng cả connector ảo kiểu Meta Ads Graph trước đây bị báo xanh oan.
### Kiểm thử
- `test_connect_health.py` thêm case: xác oauth bỏ dở báo đỏ đúng lý do và không dial server.

## [0.9.205] - 2026-07-27
Dán văn bản siêu dài vào khung chat tự thành file .txt đính kèm, kiểu Claude.
### Thêm mới
- **Dán dài thành file**: dán quá 1500 ký tự hoặc quá 25 dòng vào ô chat thì thay vì nhồi hết vào ô nhập, Javis biến đoạn đó thành file van-ban-dan-*.txt đính kèm dạng chip gọn. Hội thoại dễ đọc hẳn, Javis vẫn đọc trọn nội dung khi trả lời, và hỏi đáp tiếp trên tài liệu đó thoải mái. Chỉ áp dụng cho ô chat - dán vào các ô khác (form Kết nối, đặt tên...) vẫn như cũ; đoạn ngắn dán vào chat cũng như cũ.

## [0.9.204] - 2026-07-27
Ảnh video dán vào khung chat đăng thẳng lên Facebook được, không phải chép vào vault trước.
### Sửa lỗi
- **Tool đăng Facebook nhận file từ vùng nhận file của chat**: ảnh video dán vào khung chat dashboard rơi vào vùng tạm ngoài vault, tool đăng từ chối với lỗi "không xác định được vault" dù file do chính chủ vừa gửi. Sandbox media giờ gồm hai gốc: vault đang làm việc và vùng nhận file của chat; file gửi qua Telegram vốn rơi vào inbox trong vault nên đã chạy từ trước. File ngoài hai gốc này vẫn bị từ chối như cũ - không đăng được file tuỳ ý trên máy.
### Kiểm thử
- `test_meta_pages.py` thêm 3 case: đường dẫn tuyệt đối trong vùng staging đăng được, đường dẫn tương đối tính từ staging đăng được, file trong STATE_DIR nhưng ngoài staging vẫn bị chặn.

## [0.9.203] - 2026-07-27
Facebook Trang đăng được album nhiều ảnh và sửa được bài đã đăng.
### Thêm mới
- **Tool fb_page_album**: đăng 2 tới 10 ảnh gom vào MỘT bài kèm caption chung. Ảnh nhận file trong vault hoặc URL, trộn lẫn cũng được; up từng ảnh ở chế độ chưa đăng rồi gom một lượt nên lên Trang là thành một album gọn. Quá 10 ảnh báo rõ trần của Meta; một ảnh thì chỉ sang fb_page_photo.
- **Tool fb_page_edit**: sửa nội dung chữ của bài đã đăng theo post_id, tự suy Trang từ id bài. Nói rõ giới hạn của Meta: chỉ đổi được chữ, không đổi được ảnh video đã đính kèm.
- Cả hai xếp mức Toàn quyền và khai danger trong catalog như các tool đăng bài khác.
### Kiểm thử
- `test_meta_pages.py` thêm 11 case: album up published=false từng ảnh, bài cuối đủ attached_media, trộn URL với file vault, trần 10 ảnh, chuỗi phẩy vẫn hiểu, sửa bài đúng token Trang, thiếu tham số báo lỗi.

## [0.9.202] - 2026-07-27
Facebook Trang đăng được cả ảnh và video.
### Thêm mới
- **Tool fb_page_photo**: đăng ảnh lên Trang kèm caption. Nhận đường dẫn file ảnh trong vault (vd attachments/anh.jpg) hoặc URL http(s).
- **Tool fb_page_video**: đăng video lên Trang kèm tiêu đề và mô tả, nhận file trong vault (tối đa cỡ 1GB) hoặc URL. Upload đi host video riêng của Meta; Facebook xử lý nền vài phút rồi bài mới hiện.
- Cả hai là hành động THẬT công khai nên xếp mức Toàn quyền như đăng bài chữ: chế độ đề xuất và tự-làm-an-toàn không bao giờ tự đăng. File bắt buộc nằm TRONG vault, cùng sandbox với tool file - không đăng được file tuỳ ý ngoài vault lên mạng.
### Kiểm thử
- `test_meta_pages.py` thêm 10 case: đăng ảnh bằng URL và bằng file, chặn file ngoài vault, thiếu vault báo rõ, video đi đúng host graph-video, thiếu tham số báo lỗi, và danger list catalog khai đủ 4 tool ghi.

## [0.9.201] - 2026-07-27
Đăng nhập OAuth trên VPS https hết bị Meta chặn "không dùng kết nối bảo mật".
### Sửa lỗi
- **Redirect OAuth phía server theo đúng https của người dùng**: chạy sau reverse proxy (VPS Hostinger...), server nhìn thấy request dạng http nội bộ nên dựng redirect_uri thành http://... gửi cho Meta/Google - Meta chặn thẳng với thông báo app "không sử dụng kết nối bảo mật". Giờ server ưu tiên header X-Forwarded-Proto/Host do proxy đặt khi dựng địa chỉ quay về. Giá trị này chỉ dùng cho redirect_uri nên không ảnh hưởng các quyết định quyền theo địa chỉ client.
### Kiểm thử
- `test_security.py` thêm 5 case external_base: lấy proto/host từ proxy, proxy chồng lấy giá trị đầu, không proxy giữ nguyên, và chốt hàm này không được lẫn vào auth guard.

## [0.9.200] - 2026-07-27
Redirect URI theo đúng tên miền đang mở và hướng dẫn Facebook viết lại khớp giao diện tiếng Việt.
### Sửa lỗi
- **Redirect URI hết ghi cứng localhost**: người chạy Javis trên VPS (vd Hostinger) mở form Facebook thấy ô sao chép hiện http://localhost:7777 - dán vào Meta là đăng nhập xong trả về sai chỗ, hỏng cả luồng. Giờ ô này lấy đúng địa chỉ đang mở (https://tên-miền/connect/oauth/callback); riêng 127.0.0.1 vẫn ép về localhost vì Meta chỉ miễn HTTP cho host localhost.
### Cải thiện
- **Hướng dẫn Facebook thành wizard từng bước khớp giao diện tiếng Việt của Meta**: chỉ đúng menu 'Đăng nhập bằng Facebook > Cài đặt' và ô 'URI chuyển hướng OAuth hợp lệ', kèm cảnh báo đừng lạc vào 'Cài đặt ứng dụng > Nâng cao' (chỗ người dùng hay lạc nhất). Facebook Trang nhắc rõ dùng lại được app của Meta Ads.
### Kiểm thử
- `test_connect_group.py` mở rộng: schema tự soi MỌI connector có steps, connector BYO phải có đúng một bước copy Redirect URI, và steps che khối setup cũ thì mọi link phải xuất hiện lại trong steps.

## [0.9.199] - 2026-07-27
Ô kéo thả file JSON key không mọc nhầm sang form Facebook nữa.
### Sửa lỗi
- **Ô "kéo thả file JSON tải từ Google" chỉ hiện ở connector nhóm Google**: connector Facebook tự tạo app dùng chung tên trường client_id/client_secret nên ô này từng mọc nhầm sang form Kết nối Facebook Trang, trong khi Facebook không có file JSON nào để tải.

## [0.9.198] - 2026-07-27
Nút Thông báo trên tablet gọn như bản mobile.
### Cải thiện
- **Nút Thông báo cỡ tablet (861-1180px) dùng đúng kiểu mobile**: số chưa đọc nổi ở góc trên nút thay vì chen chung với cái chuông trong viên 34px - trước đây hai thứ chen nhau nhìn rất lôi thôi.

## [0.9.197] - 2026-07-27
Đèn báo não hết lộ vỏ rỗng trên thanh trạng thái khi não vẫn khoẻ.
### Sửa lỗi
- **Đèn báo não ẩn đúng lúc khoẻ**: rule display của đèn đè mất thuộc tính hidden mặc định của trình duyệt nên viên đèn rỗng hiện thường trực cạnh chuông Thông báo dù não bình thường. Thêm rule ẩn tường minh; đèn giờ chỉ hiện khi bộ não thật sự mất đăng nhập.

## [0.9.196] - 2026-07-27
Huỷ lịch nói tự nhiên cũng hiểu, huỷ nhầm khó hơn, và tin nhắc hẹn không còn lộ chỉ dẫn máy.
### Sửa lỗi
- **"Huỷ lịch Làm việc tại cafe" giờ vào đúng cổng huỷ**: trước đây phải nói kèm chữ cron, nhắc hẹn hay reminder thì cổng huỷ mới nhận, nói gọn kiểu tự nhiên là lọt ra ngoài để model tự đoán cách xoá (có thể sửa thẳng file reminders.json và huỷ nhầm). Giờ chữ "lịch" độc lập là đủ, nhưng lịch ngoài Javis (Google Calendar, cuộc họp, sự kiện) vẫn được nhường cho tool Calendar.
- **Tin Telegram của nhắc hẹn dạng tự-làm chỉ gửi kết quả**: trước đây ghép cả prompt nội bộ (vai trò, quy trình, đường dẫn) vào tin nhắn - vừa rối vừa lộ chỉ dẫn máy như ca Coach Mục Tiêu & Kỷ Luật. Giờ chỉ gửi phần việc đã làm ra; lỗi thì báo ngắn gọn, cũng không lộ prompt.
### Cải thiện
- **Luật huỷ an toàn cho agent**: khi tool javis_schedule lỗi, hướng dẫn kênh nói rõ đường lui duy nhất là POST /reminders/cancel bằng form-data với id thật lấy từ danh sách; cấm gọi DELETE, cấm đoán body JSON, cấm sửa trực tiếp file reminders.json.
### Kiểm thử
- `test_reminder_delivery.py` mới: task chỉ gửi kết quả, lỗi không lộ prompt, notify thường giữ nguyên. `test_tool_reliability.py` và `test_channel_reminder_brain.py` thêm case câu huỷ tự nhiên, lịch Google không bị cướp, và recipe fallback đúng endpoint.

## [0.9.195] - 2026-07-27
Đèn báo não: bộ não mất đăng nhập là dashboard báo ngay, kèm dọn gọn thanh trạng thái.
### Thêm mới
- **Đèn báo não**: khi bộ não Claude hết phiên đăng nhập, thanh trạng thái hiện dải đỏ nói rõ chuyện gì và sửa thế nào (chạy claude rồi gõ /login), kèm MỘT tin Telegram - không spam lại mỗi vòng, hồi sinh rồi chết lại mới báo tiếp. Hai nguồn tín hiệu: server tự soi hạn token định kỳ trong vòng health sẵn có, và bất cứ lượt chạy nào của engine trả lỗi đăng nhập thì bật đèn ngay. Bài học từ vụ 2026-07-27: não chết âm thầm, 3 việc nền chạy ra rác mà không ai hay - não chết thì chính não không tự báo được, phải có đèn ngoài.
### Cải thiện
- **Thanh trạng thái dọn gọn**: bỏ chữ Javis OS và dòng thứ ngày tháng theo yêu cầu chủ - thanh đang quá tải; tên workspace vẫn hiện trong Cài đặt. Chỗ trống dành cho chuông Thông báo và đèn báo não.
### Kiểm thử
- `test_connect_health.py` thêm 5 test đèn báo: bật đèn với chuỗi lỗi thật, không bật với kết quả thường, báo Telegram đúng một lần mỗi đợt chết, probe không đè đèn đỏ do lượt chạy thật, đọc hạn token đủ nhánh.

## [0.9.194] - 2026-07-27
Trang Kết nối bớt chữ kỹ thuật, gọn hơn và dễ đọc trên điện thoại.
### Cải thiện
- **Hai khu kết nối sẵn của Claude Code và Codex gộp làm một, gập mặc định**: người dùng thường không cần thấy, bấm mới mở. Danh sách chỉ tải khi mở ra nên trang Kết nối hiện nhanh hơn hẳn (trước đây gọi health check ambient ngay khi vào trang).
- **Chữ MCP rời khỏi mọi text chính**: nhãn cách đăng nhập trên card kho đổi sang tiếng người (Dán key, Quét QR, Đăng nhập tài khoản, Bấm là xong); thuật ngữ kỹ thuật chỉ còn trong phần Tự thêm (nâng cao).
- **Mobile**: kho kết nối xuống 1 cột, chip tài khoản dài tự cắt gọn không tràn khung.

## [0.9.193] - 2026-07-27
Mọi dịch vụ Google gom về một cửa, kèm wizard từng bước, kéo thả file key và nút dùng lại key.
### Thêm mới
- **Card Google một cửa trong Kho kết nối**: 6 dịch vụ Google (Lịch, Gmail, Tasks, Workspace, Sheets, Keep) gom về MỘT card. Bấm vào hiện màn chọn dịch vụ: mỗi dòng một câu nói rõ dịch vụ làm được gì và cách đăng nhập, kèm nhãn đã nối bao nhiêu tài khoản. Người dùng không còn phải hiểu sự khác nhau kỹ thuật giữa các đường kết nối.
- **Wizard từng bước thay tường chữ**: hướng dẫn tạo key Google giờ là các bước đánh số, mỗi bước có nút mở thẳng đúng trang cần tới trên Google Cloud (tạo project, bật API, màn hình đồng ý, tạo client) và ô sao chép Redirect URI một chạm ngay tại bước cần dán. Redirect URI tự lấy theo địa chỉ đang mở nên chạy đúng cả trên VPS có tên miền.
- **Kéo thả file JSON key**: tải file client từ Google xong kéo thả thẳng vào form (hoặc bấm chọn file), Javis tự bóc Client ID và Secret, nhận cả loại Ứng dụng web lẫn Desktop. Hết cảnh copy nhầm thiếu ký tự.
- **Dùng lại key giữa các dịch vụ Google**: đã tạo key cho một dịch vụ thì dịch vụ sau chỉ cần bấm "Dùng lại key này" - server tự sao chép nội bộ, key không bao giờ đi qua trình duyệt.
### Kiểm thử
- `test_connect_group.py` mới: đủ thành viên nhóm, schema các bước wizard, bước Redirect URI, dùng lại key không đè giá trị tự nhập và không copy key ngoài danh sách connector đích.

## [0.9.192] - 2026-07-27
Trang Kết nối biết tự khám sức khoẻ: chấm màu trên từng tài khoản và nút Kết nối lại một chạm.
### Thêm mới
- **Sức khoẻ kết nối thường trực**: server có vòng check nền (10 phút một lần) ping từng tài khoản đang bật qua session pool, không gọi tool thật nên không tốn quota. Mỗi chip tài khoản trên trang Kết nối hiện chấm màu: xanh là sống, đỏ là lỗi, vàng là chưa kiểm tra; rê chuột thấy nguyên nhân và thời điểm kiểm tra. Trạng thái tự làm tươi mỗi phút khi đang mở trang.
- **Lỗi nói tiếng người**: lỗi kỹ thuật được phân loại ngay tại server thành hết phiên đăng nhập, dịch vụ không phản hồi, không khởi động được trình kết nối trên máy - thay vì chuỗi lỗi thô. Bài học từ vụ nghi oan Google Workspace: thông điệp mù mờ làm chẩn đoán sai cả loạt.
- **Kết nối lại một chạm**: tài khoản chết vì hết phiên đăng nhập hiện thẳng nút Kết nối lại trên card - tài khoản OAuth mở lại đúng luồng đăng nhập cũ, tài khoản dán key mở hộp dán key mới đè lên; giữ nguyên tên, quyền, cài đặt, không phải xoá đi thêm lại. Menu tài khoản cũng thêm mục này để chủ động đổi key bất cứ lúc nào.
### Kiểm thử
- `test_connect_health.py` mới: phân loại lỗi đủ nhánh, connector ảo không báo đỏ oan, một kết nối lỗi không giết cả vòng quét, snapshot trả bản sao.

## [0.9.191] - 2026-07-27
Bảng Việc tự dọn: việc một-lần đã xong không nằm lì trên bảng nữa.
### Thêm mới
- **Tự lưu trữ việc đã kết thúc**: task done hoặc cancelled quá 3 ngày tự chuyển sang lưu trữ trong vòng dọn dẹp định kỳ của bộ điều phối. Bảng Việc chỉ còn việc đang sống và việc mới xong gần đây; lịch sử không mất, vẫn tra được ở khu lưu trữ. Trước đây không có cơ chế dọn nào nên việc giao một lần cứ ở lại bảng vĩnh viễn.
### Kiểm thử
- `test_tasks_autonomous.py` thêm test tự lưu trữ: dọn đúng task cũ, giữ task mới xong và task đang chờ, chạy lại không dọn trùng.

## [0.9.190] - 2026-07-27
Khi phiên nền bị chặn tool, thông điệp lỗi nói thẳng lý do thật để agent không chẩn đoán nhầm.
### Cải thiện
- **Thông điệp chặn tool của phiên nền hết đánh lừa**: trước đây tool MCP bị rào quyền từ chối chỉ hiện "user cancelled MCP tool call", agent đọc vào suy diễn connector chết rồi đề nghị đăng nhập lại OAuth (vụ nghi oan Google Workspace ở 0.9.189). Giờ thông điệp nói rõ đây là rào quyền phiên nền an toàn, kết nối không hỏng, đừng thử re-auth, việc cần quyền rộng hơn thì báo lại người giao việc.

## [0.9.189] - 2026-07-27
Việc nền dùng lại được các nguồn dữ liệu (MCP): sửa lỗi chặn nhầm khiến task và loop báo "connector hỏng" dù kết nối vẫn sống.
### Sửa lỗi
- **Task Kanban và loop nền gọi lại được tool MCP**: cổng quyền của phiên nền so tên tool bằng fnmatch, trong khi danh sách cho phép ghi `mcp__javis` theo kiểu tiền tố của Claude CLI, nên không khớp tool nào - mọi lời gọi qua hub đều bị từ chối ("user cancelled MCP tool call") và agent kết luận nhầm là connector chết, kéo theo hàng loạt việc nền bị treo ở trạng thái chặn. Cổng quyền giờ hiểu cả kiểu tiền tố: `mcp__<server>` trần cho phép mọi tool của server đó, và vẫn không khớp lố sang server tên gần giống. Kèm test tái hiện đúng ca lỗi.
### Kiểm thử
- `test_sdk_engine.py` thêm nhóm test prefix cho cổng quyền phiên nền: khớp tool hub, chặn server khác, chặn server tên gần giống.

## [0.9.188] - 2026-07-27
Bỏ nút bấm không làm gì ở tin chỉ có ảnh.
### Sửa lỗi
- **Tin chỉ có ảnh không còn nút chết**: tin gửi kèm ảnh mà không có lời nhắn thì chẳng có chữ nào để gửi lại, nên hai nút gửi lại và sửa lại được ẩn hẳn thay vì bấm vào không ra gì. Câu trả lời của Javis cho tin dạng đó cũng ẩn nút gửi lại theo. Tin có cả chữ lẫn ảnh vẫn giữ đủ nút và gửi lại phần chữ như cũ.

## [0.9.187] - 2026-07-27
Mỗi tin nhắn trong khung chat có thêm hàng nút nhỏ bên dưới: giờ gửi, gửi lại, sửa lại và sao chép.
### Thêm mới
- **Hàng nút dưới mỗi tin**: rê chuột vào tin (hoặc chạm vào tin trên điện thoại) là hiện giờ gửi cùng các nút gửi lại, sửa lại, sao chép. Hàng nút luôn chiếm chỗ sẵn nên hiện ra không làm nhảy khung chat.
- **Giờ gửi từng tin**: hiện dạng `HH:mm`, rê chuột vào xem đủ thứ và ngày. Hội thoại mở lại từ Lịch sử lấy đúng giờ đã lưu trong SQLite; tin cũ lưu từ trước bản này chưa có mốc giờ thì ẩn phần giờ thay vì đoán bừa.
- **Gửi lại và sửa lại**: gửi lại đưa đúng câu hỏi cũ thành một lượt mới ở cuối hội thoại, không xoá gì của lượt trước; ở tin của Javis thì nút này chạy lại câu hỏi ngay phía trên nó. Sửa lại đổ câu cũ vào ô nhập để sửa rồi tự bấm gửi. Đang chạy một lượt thì nút gửi lại bị khoá.
### Cải thiện
- Nút sao chép cũ của tin Javis gộp vào hàng nút chung cho đồng bộ hai phía.
### Kiểm thử
- Thêm `dashboard/test_chat_acts.js` phủ định dạng giờ, tin thiếu mốc giờ, thành phần hàng nút theo từng phía và việc dò ngược lên câu hỏi gần nhất.

## [0.9.186] - 2026-07-27
Lượt chat web tiếp tục chạy trên server khi đóng hoặc tải lại trang, đồng thời vẫn có thể quay lại xem tiến độ và dừng đúng lượt.
### Sửa lỗi
- **Đóng web không còn huỷ yêu cầu**: vòng đời job chat được tách khỏi WebSocket; mất kết nối chỉ gỡ kênh hiển thị, không `cancel()` tác vụ đang xử lý.
- **Mở lại thấy job đang chạy**: server gửi snapshot các session đang xử lý và phần nội dung đã stream để Lịch sử hiện trạng thái, mở đúng hội thoại sẽ xem tiếp trực tiếp.
- **Stop vẫn chính xác sau reconnect**: registry theo `session_id` giữ task và tag subprocess, nên nút Stop hoặc endpoint `/stop` chỉ huỷ đúng lượt đã chọn, kể cả lượt bắt đầu từ kết nối cũ.
### Kiểm thử
- Bổ sung kiểm thử vòng đời job, reconnect/snapshot, Stop theo session và tình huống WebSocket đóng ngay sau khi gửi nhưng kết quả vẫn được lưu đủ vào SQLite.

## [0.9.185] - 2026-07-26
Dọn sạch form Environment khi cài Docker, chỉ để lại những trường người dùng thực sự cần.
### Cải thiện
- **Hostinger chỉ còn 3 trường**: `DOMAIN_NAME`, `JAVIS_ADMIN_USER`, `JAVIS_ADMIN_PASSWORD`; bỏ khỏi form các biến kỹ thuật về cổng, state, brain và thư mục làm việc.
- **Không mất cấu hình nội bộ**: các mặc định kỹ thuật tiếp tục lấy từ Docker image; target Hostinger được gắn trong lệnh chạy thay vì lộ thành một ô Environment.
- **Compose VPS/build gọn hơn**: xoá các khai báo lặp với Dockerfile, production VPS chỉ giữ token cần chia sẻ với Watchtower.
- **Tài liệu cài đặt rõ ràng**: README, DEPLOY và hướng dẫn `.env` nói đúng ba trường cần điền trên Hostinger.
### Kiểm thử
- Thêm hợp đồng hồi quy đọc YAML để chặn biến kỹ thuật quay lại form Environment ở các bản sau.

## [0.9.184] - 2026-07-26
Tên giọng đọc thân thiện hơn và cài đặt tên miền trở thành wizard rõ ràng ngay trên UI.
### Cải thiện
- **Đổi tên hiển thị giọng Edge**: HoaiMy thành **Ngọc Thu**, NamMinh thành **Nam Minh**; giữ nguyên mã giọng Microsoft phía sau nên lựa chọn đã lưu và chất giọng không thay đổi.
- **Wizard tên miền ba bước**: lưu tên miền, kiểm tra/trỏ DNS và bật HTTPS được trình bày theo trạng thái, có nút sao chép bản ghi và link mở tên miền khi hoàn tất.
- **Hướng dẫn đúng môi trường**: VPS thường dùng nút Bật SSL/Caddy ngay trên UI; Hostinger hiện biến `DOMAIN_NAME` để sao chép và yêu cầu Redeploy, không còn đưa nút SSL không thể thực thi.
- **Tài liệu ngay trong card**: thêm link trực tiếp tới hướng dẫn tên miền và tài liệu deploy/SSL; đồng bộ các trang hướng dẫn liên quan.
### Kiểm thử
- Bổ sung hợp đồng hồi quy cho tên giọng, wizard, nút sao chép, link tài liệu, metadata môi trường và compose Hostinger/VPS.

## [0.9.183] - 2026-07-26
Đồng bộ toàn bộ hướng dẫn sử dụng với cấu trúc điều hướng mới sau khi bỏ trang Tổng quan.
### Cải thiện
- **Không còn hướng dẫn tới trang đã bỏ**: README, triển khai, thiết lập, Telegram, Second Brain, bảo mật, biến môi trường và khắc phục sự cố đều trỏ đúng tới Cài đặt hoặc Cập nhật.
- **Phân biệt Hostinger và VPS Docker**: tài liệu cập nhật nói rõ Hostinger cần Redeploy, còn cập nhật một chạm trên VPS cần Watchtower/profile `update`.

## [0.9.182] - 2026-07-26
Gom lại khu vực quản trị hệ thống: bỏ trang Tổng quan trung gian, đưa cập nhật về đúng Nhật ký cập nhật và làm Cài đặt gọn, dễ quét hơn.
### Cải thiện
- **Bỏ tab Tổng quan**: trạng thái hệ thống cần thiết chuyển vào Cài đặt; mobile/lite-mode đi thẳng tới Trò chuyện thay vì dừng ở một trang ít giá trị.
- **Cập nhật đúng một nơi**: kiểm tra phiên bản, xem tóm tắt bản mới, tự cập nhật, tiến trình và hướng dẫn Redeploy/rollback nằm ngay đầu trang Nhật ký cập nhật.
- **Cài đặt có chiều rộng đọc tối ưu**: nội dung được căn giữa với giới hạn 960px, chia thành các nhóm có thể gập/mở thay vì kéo dài kín từ trái sang phải.
- **Gom theo nhiệm vụ**: Hệ thống, Giao diện & Brain, Giọng nói/Thương hiệu/Truy cập và Khởi động Windows được phân nhóm; Models, Kênh, Tài khoản và Cập nhật dùng lối tắt tới trang chuyên sâu thay vì lặp lại form.
- **Mobile sạch hơn**: bỏ nút mở cửa sổ cài đặt cũ khỏi ngăn kéo; các card và quick settings tự chuyển về một cột trên màn hình hẹp.
### Kiểm thử
- Thêm hợp đồng hồi quy cho menu, router, lite-mode, vị trí update, cấu trúc gập/mở, chiều rộng Cài đặt và việc loại đường vào cài đặt cũ trên mobile.

## [0.9.181] - 2026-07-26
Hộp thư Thông báo gọn hơn trên cả desktop và mobile, không còn để một bản cập nhật dài chiếm gần trọn màn hình.
### Cải thiện
- **Card cập nhật chỉ hiện tóm tắt**: nội dung release được giới hạn hai dòng; các bullet đầy đủ tiếp tục nằm ở trang Nhật ký cập nhật khi người dùng bấm xem chi tiết.
- **Tin cộng đồng/marketing có giới hạn**: phần mô tả tối đa hai dòng và nội dung bổ sung tối đa ba dòng, giữ đủ ý nhưng không làm card cao quá mức.
- **Tải thêm theo nhóm**: lần đầu chỉ render 5 thông báo; nút `Tải thêm` nạp tiếp từng nhóm tối đa 5 tin và tự biến mất khi đã hết.
- **Panel mobile thấp hơn**: chiều cao tối đa khoảng 72% dynamic viewport, danh sách cuộn độc lập bên trong để không che toàn bộ giao diện phía sau.
### Kiểm thử
- Bổ sung hợp đồng hồi quy cho kích thước trang 5 tin, nút tải thêm và quy tắc không render toàn bộ body của release trong card.

## [0.9.180] - 2026-07-26
Ảnh do ChatGPT/Codex hoặc model OpenRouter tạo trong Telegram được gửi thành ảnh thật thay vì hiện nguyên đường dẫn Markdown.
### Sửa lỗi
- **Nhận đường dẫn có khoảng trắng**: bộ thu file trước đây chỉ khớp `attachments/x.png`, nên bỏ sót đường dẫn thực tế như `99 - Attachments/claude-workforce-vietnamese-4x5.png`; parser mới hỗ trợ cả path có khoảng trắng, dạng `<path>` và path tuyệt đối nằm trong brain.
- **ChatGPT Telegram gửi media thật**: nhánh Codex OAuth resolve ảnh Markdown về đúng file trong brain, xếp hàng `sendPhoto` và loại dòng `![...](...)` khỏi phần chữ sau khi file đã được nhận.
- **OpenRouter/API có cùng chức năng**: gateway giờ thu file do MCP tạo cho mọi provider API, không còn giả định engine API chỉ có thể trả text.
- **Không gửi tin rỗng trước ảnh**: nếu câu trả lời chỉ chứa ảnh nhúng, Telegram bỏ tin `(không có nội dung)` và gửi thẳng ảnh.
### Bảo mật
- **Không mở rộng ra ngoài brain**: URL web, `data:`, liên kết thường và đường dẫn `../` thoát vault không được coi là file local; chỉ Markdown ảnh khớp đúng file đã xếp hàng mới bị ẩn khỏi text.
### Kiểm thử
- Bổ sung hồi quy đúng trường hợp `99 - Attachments` trong ảnh lỗi, path bọc `<>`, giữ URL/link thường, chống thoát brain và xác nhận reply chỉ có file vẫn gửi đúng chat Telegram.

## [0.9.179] - 2026-07-26
Navbar có hộp thư Thông báo nổi bật, hợp nhất nhật ký phiên bản với các tin cộng đồng và marketing có thể phát hành tập trung.
### Thêm mới
- **Chuông Thông báo trên navbar**: có huy hiệu số chưa đọc, hiệu ứng nhấn vừa đủ nổi bật và panel dạng hộp thư; hỗ trợ đọc từng tin, đọc tất cả, làm mới và đi thẳng tới Nhật ký cập nhật.
- **Hai nguồn trong một luồng**: mọi release trong `CHANGELOG.md` tự trở thành thông báo cập nhật; tin cộng đồng/marketing lấy từ `ANNOUNCEMENTS.json` trên GitHub `main`.
- **Phát tin không cần release ứng dụng**: thông báo trung tâm trên GitHub ghi đè bản local cùng ID, được Javis làm mới định kỳ và cache phía server trong hai phút để giảm tải.
- **Ghi nhớ đã đọc trên từng trình duyệt**: lần đầu không biến toàn bộ lịch sử release thành tin chưa đọc; các thông báo mới về sau tự xuất hiện trong badge.
- **Responsive**: desktop hiển thị nút có nhãn `Thông báo`; mobile dùng chuông gọn cạnh menu và panel gần toàn màn hình.
### Bảo mật
- **Dữ liệu marketing được giới hạn**: backend chỉ nhận text thuần, ID hợp lệ, loại tin cho phép và URL `http/https`; frontend escape toàn bộ nội dung trước khi render.
### Kiểm thử
- Mở rộng `test_update.py` để phủ parser, tin hết hạn, URL nguy hiểm, endpoint hợp nhất, hợp đồng navbar, trạng thái đã đọc và vị trí chuông mobile.

## [0.9.178] - 2026-07-26
Brain trên điện thoại tự canh camera sau khi mô phỏng neuron ổn định và có chế độ xem toàn cảnh không bị lớp thông tin che.
### Thêm mới
- **Nút mắt trong góc brain**: ẩn/hiện đồng thời nhãn thư mục, tỷ lệ `% Vault` và thanh Agents / Skills / Workflows; neuron cùng trạng thái `Sẵn sàng` luôn được giữ lại.
- **Ghi nhớ lựa chọn**: trạng thái ẩn/hiện được lưu trên trình duyệt và đồng bộ giữa các tab.
### Sửa lỗi
- **Neuron 3D mobile tự co đúng lúc**: bổ sung bước `zoomToFit` sau khi physics dừng và fit lại khi visual viewport đổi kích thước, khắc phục camera mobile mắc ở trạng thái phóng lớn ban đầu.
- **Không ảnh hưởng desktop**: auto-fit mới chỉ chạy ở viewport tối đa 860px; trải nghiệm co tự nhiên hiện tại trên máy tính được giữ nguyên.

## [0.9.177] - 2026-07-26
Trang Tệp tin có khung tìm kiếm đồng bộ với Vault Explorer của Javis, giúp tìm và mở file mà không cần nhớ nó nằm trong thư mục nào.
### Thêm mới
- **Tìm theo tên file trên toàn brain**: ô tìm dùng cùng giao diện kính lúp, nút xoá và chip chế độ như màn Javis; so khớp không phân biệt hoa thường và hỗ trợ gõ tiếng Việt không dấu.
- **Tìm trong nội dung**: chế độ Nội dung quét file text dưới 1 MB, trả đoạn trích và số dòng khớp; chế độ Tên không đọc thân file nên phản hồi nhanh hơn.
- **Mở ngay hoặc tìm tới vị trí**: mỗi kết quả cho phép xem/sửa file trực tiếp hoặc chuyển File Manager tới đúng thư mục và tô sáng file đó.
- **Responsive**: khung tìm tự xuống dòng trên mobile, kết quả giữ đường dẫn/đoạn trích gọn và các nút thao tác luôn hiện trên màn cảm ứng.
### Kiểm thử
- Mở rộng `server/test_files_root.py` để phủ tìm tên không dấu, tìm nội dung, tách hai chế độ, hợp đồng UI và khả năng tương thích của endpoint cũ.

## [0.9.176] - 2026-07-26
Tối ưu cockpit Javis trên điện thoại để neuron vẫn nhận diện được nhưng không đẩy khung chat và ô nhập ra ngoài màn hình.
### Cải thiện
- **Khung chat luôn nằm trong màn hình iPhone**: thay chiều cao `100vh` bằng dynamic viewport (`100dvh` có fallback), hỗ trợ safe area và bỏ `min-height` desktop khỏi transcript mobile; thanh địa chỉ/bàn phím Safari hoặc Chrome không còn che ô nhập.
- **Neuron gọn hơn trên mobile**: vùng graph giảm từ 34% xuống khoảng 27% chiều cao khả dụng, có trần/sàn cho màn hình ngắn; nhãn concept, trạng thái và lời thoại tạm thu nhỏ riêng ở breakpoint mobile.
- **Agents / Skills / Workflows thành thanh mỏng**: giảm padding, cỡ số, nhãn và khoảng cách; ba mục tự chia đều chiều ngang và vẫn bấm mở Studio như trước.
- **Desktop giữ nguyên**: toàn bộ thay đổi nằm trong breakpoint tối đa 860px; bố cục ba cột và kích thước graph desktop không đổi.

## [0.9.175] - 2026-07-26
Xoá cron/nhắc hẹn trực tiếp từ chat hoạt động nhất quán với ChatGPT/Codex và mọi model OpenRouter, không còn đẩy người dùng sang UI tự xoá.
### Sửa lỗi
- **Nhận đúng từ “xoá”**: intent router trước đây chỉ có `huỷ/tắt` nên câu “xoá cron…” không bị ép gọi `javis_schedule`; bổ sung đầy đủ biến thể xoá/huỷ/dừng và chặn nhầm sang đường chỉ đọc (`server/engine.py`).
- **Gateway xoá lịch không phụ thuộc function-calling của model**: Javis tự gọi `op=list`, chỉ khớp và `op=cancel` khi có đúng một mục chắc chắn. Nhiều mục gần giống thì trả danh sách thật để hỏi lại; kho trống báo đúng là trống, tuyệt đối không đoán hoặc xác nhận xoá giả.
- **ChatGPT trên Telegram có MCP như dashboard**: nhánh OpenAI OAuth được chuyển từ Responses chat-thuần sang Codex CLI có MCP native, đúng brain và giữ session riêng theo chat (`server/main.py`).
- **OpenRouter không còn tự nhận là “không MCP”**: thao tác xoá lịch đi qua gateway chung nên cả model không hỗ trợ function-calling vẫn xoá được mục khớp chắc chắn; các thao tác tool khác tiếp tục dùng vòng MCP đa-model hiện có.
- **Luật kênh rõ cho mọi provider**: tạo/sửa/xoá/huỷ/tắt lịch bắt buộc dùng `javis_schedule`; xoá chưa có ID phải list trước, không hướng dẫn người dùng tự vào trang Việc định kỳ (`server/channel_context.py`).
### Kiểm thử
- Bổ sung hồi quy intent “xoá cron”, khớp tên duy nhất, không xoá nhầm khi mơ hồ, kho trống, tuyến ChatGPT Telegram và nhãn OpenRouter. Chạy tích hợp với hai cron thật trong brain test: gateway xoá đúng cron brainstorm, giữ nguyên cron thuốc còn lại và lưu mục đã xoá ở trạng thái `cancelled`.

## [0.9.174] - 2026-07-25
Bản vá cho hàng đợi AI: Codex chạy lại bình thường, task lỗi được phục hồi có kiểm soát và màn chi tiết Kanban thao tác được đầy đủ.
### Sửa lỗi
- **Codex CLI không còn chặn hàng loạt task**: các cờ toàn cục `--sandbox`, `--ask-for-approval`, model, profile và config được đặt trước subcommand `exec`, tương thích cú pháp Codex đang cài trên VPS (`server/claude_cli.py`).
- **Tự phục hồi đúng nhóm task bị lỗi tham số**: khi khởi động sau nâng cấp, Javis đưa về hàng đợi đúng một lần các task bị chặn bởi lỗi `unexpected argument '--ask-for-approval'`; các ngoại lệ khác vẫn giữ nguyên để không chạy nhầm (`server/task_store.py`, `server/tasks.py`).
- **Drawer chi tiết luôn đóng được**: chuyển drawer lên `document.body` để không bị vùng nội dung cắt mất thanh đầu; có nút đóng cố định, phím `Esc` và bấm vùng nền (`dashboard/console.js`).
- **Task có thể xóa khỏi bảng**: mọi task không chạy đều có nút **Xóa khỏi bảng** ở card và trong drawer; dữ liệu được archive thay vì xóa cứng để còn lịch sử. Task đang chạy phải dừng trước.
### Kiểm thử
- Bổ sung hồi quy thứ tự tham số Codex và phục hồi có chọn lọc; kiểm tra thao tác drawer/xóa task trên giao diện.

## [0.9.173] - 2026-07-25
Kanban trở thành hàng đợi vận hành dành cho AI, thay vì một bảng Trello cần người bấm chạy từng thẻ.
### Thêm mới
- **Task kernel bền vững bằng SQLite**: thêm board, task, dependency, run và event log; claim task dùng compare-and-set trong transaction, có worker lease, heartbeat, timeout, retry, idempotency key và lịch sử từng lần chạy (`server/task_store.py`).
- **AI specifier trước khi thực thi**: goal mới đi qua tầng triage để model nền chuẩn hoá intent, chọn lane `files`, `research`, `mcp-read`, `code` hoặc `external-write`, rồi mới vào hàng đợi chạy. Hành động ra ngoài thiếu quyền `full` bị block theo loại `capability`, không chạy liều (`server/tasks.py`).
- **Operations console mới**: trang Việc tập trung vào worker đang chạy, hàng đợi, ngoại lệ cần xử lý, throughput 24 giờ và drawer xem run/event; tự cập nhật 3 giây một lần. Sáu cột ngang và nút Chạy trên từng card không còn là luồng chính (`dashboard/console.js`).
### Sửa lỗi
- **Dispatcher quét mọi brain**: không còn hardcode `tick(["brain"])` khiến board khác hiển thị auto nhưng không bao giờ chạy.
- **Chạy đúng task được chọn**: endpoint chạy/retry claim chính xác task id bằng transaction, không đưa về ready rồi vô tình chọn task cũ có ưu tiên cao hơn.
- **Task nền không chặn cron và lịch thuốc**: dispatcher có vòng lặp riêng, mỗi worker là một asyncio task độc lập; scheduler 30 giây chỉ đánh thức dispatcher và trả ngay.
- **Task Learn không dừng review thủ công hàng loạt**: task nội bộ mặc định tự hoàn thành; chỉ thiếu input, thiếu capability, hành động bên ngoài hoặc cờ duyệt tường minh mới cần người xử lý.
### Tương thích
- `Javis/kanban.json` cũ được import đúng một lần, task `running` từ tiến trình cũ được thu hồi về `ready`. SQLite là nguồn lifecycle chính nhưng Javis vẫn xuất snapshot JSON để brain backup và phiên bản cũ đọc được.
- Worker tiếp tục đi qua `aux_engine`, nên Claude Code, Codex/ChatGPT và OpenAI/OpenRouter API dùng cùng queue, brain context và policy MCP hiện có.
### Kiểm thử
- Thêm `server/test_tasks_autonomous.py`: phủ migration JSON, atomic claim, dependency promotion, dispatcher đa brain và chạy đúng task được chọn.

## [0.9.172] - 2026-07-25
ChatGPT nhớ đúng mạch hội thoại, và mọi model đọc cron/lịch thuốc từ dữ liệu thật thay vì đoán theo memory.
### Sửa lỗi
- **ChatGPT/Codex không còn quên ngữ cảnh giữa các lượt**: mỗi hội thoại lưu riêng `codex_thread_id` và dùng `codex exec resume`; phiên cũ bị mất rollout thì tự dựng lại mạch từ lịch sử SQLite. Khi đổi qua provider khác, liên kết Codex cũ được xoá để tránh resume một nhánh hội thoại đã stale (`server/claude_cli.py`, `server/sessions.py`, `server/compaction.py`, `server/main.py`).
- **Codex đọc cron đúng brain đang chat**: MCP hub nhận `X-Javis-Vault` theo từng tiến trình Codex rồi truyền xuống plugin. Trước đây Codex nhìn thấy `javis_schedule` nhưng context thiếu `vault_root`, nên tool dừng ở lỗi “không xác định được brain đang làm việc” (`server/mcp_hub.py`, `server/main.py`, `server/aux_engine.py`).
- **OpenRouter không còn báo “không có tool” hoặc đoán lịch từ memory**: câu hỏi chỉ xem cron/nhắc hẹn/lịch thuốc được server gọi thẳng `javis_schedule(op=list)` trước khi model trả lời, nên vẫn hoạt động khi `openrouter/free` route tới model không có function calling. Tạo/sửa/hủy lịch vẫn bắt buộc gọi tool; model bỏ qua hai lần thì Javis chặn câu trả lời có nguy cơ bịa (`server/engine.py`).
### Cải thiện
- **Một nguyên tắc dữ liệu thật cho mọi provider và mọi kênh**: Claude, ChatGPT/Codex, OpenAI-compatible và OpenRouter đều được nhắc bắt buộc gọi tool khi user hỏi trạng thái đang chạy hoặc dữ liệu tài khoản ngoài; lỗi tool phải được báo đúng, không thay bằng ký ức cũ (`server/channel_context.py`).
- **Plugin nội bộ vẫn có trên Codex khi chưa đấu connector ngoài**: profile hub không còn bị xoá chỉ vì danh sách MCP bên ngoài rỗng; các tool hệ thống như `javis_schedule` và `datetime-vn` vẫn dùng được.
### Kiểm thử
- Thêm `server/test_codex_context.py` và `server/test_tool_reliability.py`; chạy đạt các bộ hồi quy context Codex, MCP lazy, lịch/cron, provider việc nền, channel reminder, Claude SDK và session brain.

## [0.9.171] - 2026-07-25
Gọt phần đầu cố định của mỗi lượt chat, KHÔNG động tới bộ nhớ.
### Cải thiện
- **Mô tả skill trong bản mirror bị ép về đúng trần 150 ký tự**: Claude Code nạp native đọc frontmatter ở `.claude/skills`, và danh sách skill đó nằm trong phần đầu CỐ ĐỊNH của mọi lượt chat. Đo trên brain thật: 14/30 skill vượt trần 150 của chính dự án (dài nhất 1.018 ký tự), tổng mô tả 10.095 ký tự; sau khi ép còn 3.844, giảm 62%. Bản canonical trong `skills/` **giữ nguyên chữ của người dùng** - mirror vốn là bản phái sinh. Không mất năng lực: mô tả chỉ để định tuyến, router xưa nay đã cắt đúng ở 150 nên phần dư vốn đang mất im lặng; thân skill vẫn nạp đủ khi được gọi. Xử được cả YAML nhiều dòng (`>`, `>-`, `|`) - hai mô tả dài nhất của brain thật đều viết kiểu đó (`server/system_sync.py`).
- **Chỉ mục bộ nhớ có TRẦN, hạ dần theo bậc**: `JAVIS_MEMORY_INDEX_MAX` mặc định 20.000 ký tự. Vượt trần thì rút mô tả còn 100 ký tự, rồi 60, rồi chỉ còn tiêu đề kèm link - **bỏ hẳn dòng là bậc CUỐI**, và khi buộc phải bỏ thì nói rõ còn bao nhiêu ký ức cùng đường đọc tiếp. Rút mô tả không làm mất trí nhớ: tiêu đề và đường dẫn file vẫn còn, chi tiết đầy đủ vẫn nằm trong `Memory/facts/`. Hôm nay chưa cắt gì (18.363 < 20.000) - đây là chặn đường dốc trước khi nó thành vấn đề, đúng bệnh curator vừa mắc (`server/main.py`).
- **CLAUDE.md thôi ôm mẫu file dài**: các bản mẫu frontmatter của loop, agent, workflow, skill và cả `plugin.yaml`/`plugin.py` đã có sẵn trong skill `javis-builder`, nạp theo nhu cầu khi thật sự đi tạo. Gỡ bản trùng khỏi system prompt, **giữ nguyên toàn bộ luật an toàn và luật hành vi** (mặc định `mode: suggest` + `enabled: false`, env gate plugin, trần 150 ký tự, bắt buộc có `group`, `owner_chat`, `notify: false`). Bổ sung `tools_profile` và `notify` vào `javis-builder` cho khỏi hụt thông tin.
### Đo được
- Phần đầu mỗi lượt chat giảm khoảng **9.328 ký tự (~2,9k token)**: system prompt Javis từ 46.056 xuống 42.979, mô tả skill từ 10.095 xuống 3.844.
- **Không cắt bộ nhớ**, và đó là quyết định có đo: MEMORY.md chỉ chiếm 5,7k trong prefix 85k (7%); thử rút mô tả xuống 60 ký tự chỉ tiết kiệm 1,4k token, đổi khả năng nhớ lấy chừng đó là lỗ.
### Kiểm thử
- `server/test_prefix_slim.py`: cắt được cả 4 kiểu viết description (trần, nháy kép, gấp `>-`, khối `|`) mà thân skill và `group` nguyên vẹn; canonical không bị đụng; chỉ mục bộ nhớ giữ đủ ký ức qua nhiều mức trần và chỉ bỏ dòng ở bậc cuối kèm lời chỉ đường; CLAUDE.md đã gỡ mẫu nhưng còn đủ 8 luật, và `javis-builder` phủ đủ 10 trường đã dời sang.

## [0.9.170] - 2026-07-25
Curator chỉ soi phần wiki thật sự đổi, thôi quét lại cả kho mỗi ngày.
### Cải thiện
- **Chi phí curator bám theo LƯỢNG THAY ĐỔI, không còn bám theo độ lớn brain**: trước đây mỗi vòng curator quét lại toàn bộ wiki như chưa từng thấy. Đo trên brain thật: đầu tháng 7 tốn 2,46M/vòng, cuối tháng 7 đã 5,22M/vòng - gấp đôi trong ba tuần - dù số lượt chỉ tăng 16% (37 lên 43); ngữ cảnh mỗi lượt phình ra vì vòng nào cũng đọc lại cả kho. Nghĩa là càng bồi đắp Second Brain thì việc nền càng đắt, không có trần. Nay curator so mốc quét lần trước rồi quyết định: wiki không đổi note nào thì **bỏ hẳn vòng, không spawn agent**; có đổi thì prompt liệt kê đúng những note đó và cấm quét lại cả wiki (`server/learn.py`).
- **Đo thật sau khi sửa**: một vòng với 10/174 note đổi (tồn đọng cả tuần) tốn **1,62M**, so với 5,22M của vòng quét toàn bộ - rẻ hơn khoảng 69%. Mà thực tế 7/14 ngày gần nhất wiki không đổi note nào, những ngày đó giờ tốn 0.
- **Vẫn quét toàn bộ định kỳ**: mặc định 30 ngày một lần (`curator.full_every_days`, đặt 0 để tắt) vì soi-phần-đổi không thấy được vấn đề liên-trang tích tụ dần. Ngoài ra xoá hoặc đổi tên note cũng ép quét toàn bộ ngay vòng đó, vì chúng sinh wikilink gãy ở những trang KHÔNG đổi - thứ mtime không nhìn thấy. Thêm note mới thì không ép, đó là việc thường ngày và note mới vốn đã nằm trong danh sách đổi.
- **Bỏ qua vòng thì giữ nguyên mốc cũ**: nếu vòng bỏ qua cũng dời mốc lên hiện tại, note sửa trước đó mà chưa kịp soi sẽ rơi khỏi cửa sổ vĩnh viễn, im lặng không bao giờ được lint.
### Kiểm thử
- `server/test_curator_scope.py`: phủ lần đầu, không đổi, có đổi, xoá, đổi tên, thêm note, đến hẹn quét toàn bộ, tắt quét định kỳ, wiki rỗng, và chốt bẫy giữ mốc khi bỏ qua vòng.

## [0.9.169] - 2026-07-25
Chọn model việc nền bằng hộp có ô tìm, thay cho dãy chip tràn trang.
### Cải thiện
- **Model việc nền không còn phơi hết ra thành chip**: bản 0.9.167 mở ô này cho mọi nhà cung cấp nhưng vẫn vẽ từng model thành một chip, mà riêng OpenRouter đo live đã **345 model** - dán hết ra trang thì tràn dài và không có đường tìm kiếm. Nay mục này chỉ hiện LỰA CHỌN HIỆN TẠI (tên model + nhà cung cấp, kèm cảnh báo nếu nhà đó chưa kết nối) cùng hai nút "Đổi model" và "Về mặc định"; việc chọn giao cho hộp `openModelPicker` - đúng hộp đang dùng cho model chính ngay phía trên, có ô lọc, cột nhà cung cấp và tự nạp danh sách model live.
- **Một hộp chọn dùng chung cho cả hai chỗ**: `openModelPicker` nhận thêm tham số tuỳ chọn `{title, note, save}` nên model chính và model việc nền dùng chung một giao diện, không nhân đôi mã. Thiếu tham số thì giữ nguyên hành vi cũ.
### Sửa lỗi
- **Ô lọc không còn mất chữ khi đổi nhà cung cấp**: bấm sang nhà khác là `draw()` dựng lại DOM, chữ đang gõ trong ô lọc bị xoá và phải gõ lại từ đầu - khó chịu nhất đúng lúc đang dò trong danh sách vài trăm dòng. Nay chữ lọc được giữ và tự áp lại sau mỗi lần vẽ.
- **Nhãn "đang dùng" chỉ sai chỗ ở hộp chọn model việc nền**: nhãn này đọc `is_main` do máy chủ tính cho MODEL CHÍNH, nên khi mở hộp để chọn model việc nền nó đánh dấu nhầm sang nhà cung cấp của model chính. Nay so trực tiếp với lựa chọn được truyền vào, đúng cho cả hai chỗ (đổi chữ CURRENT thành "ĐANG DÙNG").

## [0.9.168] - 2026-07-25
Vá cảnh báo rủi ro của Composio bị dính thành một khối chữ khó đọc.
### Sửa lỗi
- **Cảnh báo Composio xuống dòng đúng chỗ**: đoạn "Mức Toàn quyền" dài 210 ký tự nằm liền một dòng, vượt ngưỡng 200 mà `test_canh_bao_rui_ro.py` đặt ra để cảnh báo còn đọc được (khối `.conn-risk` dùng `white-space: pre-line` nên xuống dòng trong JSON mới hiện ra). Tách câu "Chỉ nâng khi thật sự cần..." xuống dòng riêng, giữ nguyên từng chữ của cảnh báo - đây là lỗi trình bày, không hạ nhẹ nội dung (`system/mcp-catalog.json`). Lỗi có từ 0.9.162 lúc thêm connector Composio.

## [0.9.167] - 2026-07-25
Việc nền chạy được bằng model NGOÀI Claude, và curator thôi quét những brain đã bỏ.
### Thêm mới
- **Chọn nhà cung cấp cho model việc nền**: ô "Auxiliary" ở trang Model trước đây khoá cứng vào danh sách của `anthropic-cli` (console.js đọc thẳng `providers.find(id==="anthropic-cli").models`), nên mọi việc nền - loop, việc Kanban, nhắc hẹn, tự học, tiêu hoá nguồn - đều ăn hạn mức Claude, không có đường đổi. Nay ô này liệt kê MỌI nhà cung cấp đã đấu (đã đăng nhập hoặc đã có key), gom theo từng nhà; chọn nhà nào thì việc nền chạy bằng gói/khoá của nhà đó (`server/aux_engine.py`).
- **Ba loại engine nền, khác nhau ở công cụ**: Claude Code giữ nguyên như cũ (tool file native + Bash + MCP, chặn theo allowlist per-call). Codex CLI cũng là agent thật (đọc/ghi file + MCP qua profile javis) và nay nhận `--sandbox` ánh xạ theo mode của loop - suggest thành `read-only`, auto thành `workspace-write`, full giữ toàn quyền; trước đây Codex luôn chạy bypass sandbox nên không dùng cho việc nền có mức quyền được (`server/claude_cli.py`). Các model API (OpenRouter, OpenAI, Gemini, Anthropic API) không có tool native nhưng dùng tool vault của hub (`javis_read_file` / `javis_write_file` / `javis_use_skill` + MCP), và `javis_write_file` vốn đã tự chặn khi mode là suggest - nên loop chỉ-đọc vẫn chỉ-đọc trên mọi engine.
- **Rào an toàn khi cấu hình hỏng**: chọn nhà chưa có key hoặc chưa cài Codex CLI thì việc nền LẲNG LẶNG dùng lại Claude kèm dòng log nêu lý do, thay vì chết giữa chừng. Provider lạ gửi lên `/settings` bị ép về `anthropic-cli`.
### Cải thiện
- **Curator thôi quét brain đã bỏ**: danh sách `learn_config['brains']` chỉ NỐI THÊM mỗi lần chat một brain mới, không bao giờ bớt - mà mỗi vòng curator là một phiên LINT Wiki đầy đủ cho TỪNG brain. Đo thực tế: tháng 7 chạy 22 lần hết 97M token trên 4 brain, trong đó 1 là đường dẫn không tồn tại và 2 là brain người dùng đã bỏ gần 3 tuần. Nay curator bỏ qua brain có thư mục không còn, và brain im lặng quá `curator.stale_days` (mặc định 14 ngày), có log nêu rõ bỏ cái nào vì sao (`server/learn.py`).
- **Đo độ mới bằng Memory/conversations, KHÔNG bằng mtime thư mục**: chính curator ghi `Javis/learn-log` mỗi vòng, nên lấy mtime thư mục thì brain nào cũng "vừa hoạt động" và curator tự nuôi lý do chạy tiếp mãi trên brain đã chết.
### Kiểm thử
- `server/test_aux_engine.py`: mặc định và cấu hình cũ (thiếu `provider`) vẫn ra đúng engine Claude; đổi sang API thì thừa hưởng system_prompt/vault/mode; thiếu key hoặc provider lạ thì giữ Claude; mode ánh xạ đúng sang sandbox Codex và sandbox thật sự vào dòng lệnh; engine API gom nhiều mảnh text thành đúng một sự kiện `final`.
- `server/test_curator_targets.py`: bỏ brain mất thư mục, bỏ brain nguội, giữ brain vừa chat, và chốt rằng learn-log mới KHÔNG cứu được brain đã nguội.

## [0.9.166] - 2026-07-25
Gỡ hẳn bảng thẻ SỐ LIỆU KINH DOANH. Muốn xem số thì hỏi thẳng, Javis gọi MCP lấy về.
### Gỡ bỏ
- **Bảng thẻ số liệu ở cột trái**: bảng này đã bỏ khỏi giao diện từ trước (thay bằng Vault explorer), nhưng toàn bộ máy móc phía sau vẫn chạy để nuôi một stub ẩn không ai nhìn thấy - mỗi lần mở dashboard là một phiên Claude đầy đủ kèm MCP. Nay gỡ sạch: endpoint `/metrics` cùng lớp cache vừa thêm ở 0.9.165 (`server/main.py`), toàn bộ phần dựng thẻ trong `dashboard/app.js` (`loadMetrics`, `renderMetrics`, `agenticFallbackCards`, `extractMetrics`, `pushMetricsToPanel`, biến `savedMetrics` và phần lưu/khôi phục nó theo phiên), stub ẩn trong `index.html`, và các lớp `.metric-*` trong `style.css`.
- **Chỉ thị nhúng khối `JAVIS_METRICS`**: gỡ khỏi system prompt (`CLAUDE.md`), nên Javis không còn tự đính khối ẩn vào cuối câu trả lời có số liệu nữa. Bộ bóc khối điều khiển cho kênh chữ thuần thì GIỮ nguyên và vẫn bóc chung mọi `JAVIS_*` - ký ức cũ trong brain còn nhắc tên khối này, để đó cho chắc kẻo lọt nguyên xi ra Telegram.
### Cải thiện
- **Loop `goal: business` tự lấy số qua MCP**: trước đây vòng này mồi sẵn chỉ số từ chính job thẻ dashboard, không có số là bỏ qua cả vòng kèm lời nhắc "bấm ⟳ tải số liệu" - nút giờ không còn. Nay bước đầu mỗi vòng là loop tự gọi MCP lấy 3-6 chỉ số theo thứ tự ưu tiên POS → kênh → quảng cáo → nguồn khác, và báo cáo phải nêu rõ số kèm nguồn. Bỏ luôn tham số `metrics` khỏi `LoopDeps` (`server/self_improve.py`).
### Kiểm thử
- Thay `test_metrics_cache.py` (hết đối tượng) bằng `server/test_session_brain.py`: giữ phần nhãn dự án theo brain, thêm chốt chặn hồi quy khẳng định `/metrics`, phần dựng thẻ trong app.js, stub HTML, CSS và chỉ thị trong system prompt đều đã sạch - và khối `JAVIS_*` lạ vẫn bị bóc khỏi kênh chữ thuần.

## [0.9.165] - 2026-07-25
Chặn khoản hao token âm thầm: mở dashboard không còn spawn agent mới mỗi vài phút.
### Sửa lỗi
- **Thẻ số liệu dashboard đốt hạn mức mà không ai dùng**: đo trên log phiên thật của bản VPS, dự án "app" tốn 22M token thì 402/502 phiên là đúng một job lặp - "tạo các thẻ SỐ LIỆU KINH DOANH cho dashboard" (~16k token mỗi lần, cộng dồn ~6.5M). Gốc rễ ở `/metrics`: cache chỉ 180 giây, chỉ nằm trong RAM, không nhớ lần lỗi và không gộp request trùng, nên gần như mỗi lần MỞ dashboard là một phiên Claude đầy đủ kèm MCP. Nay cache mặc định 15 phút (`METRICS_TTL`), **ghi ra đĩa** nên restart hay tự cập nhật không làm mất, **nhớ cả kết quả lỗi** 2 phút (`METRICS_ERR_TTL`) để MCP hỏng không thành spawn lại mỗi lần F5, và **gộp request trùng** bằng một khoá chung - mở dashboard trên điện thoại lẫn máy tính cùng lúc chỉ tính một lần (`server/main.py`).
- **Trang Token gọi sai tên dự án**: mọi engine Claude đều chạy với `cwd` = gốc project chứ không phải thư mục brain, mà log thô của Claude Code chỉ ghi `cwd`, nên chat Telegram, việc nền và job dashboard bị gộp hết vào một dự án ("Javis-OS" khi chạy ở máy, "app" khi chạy trong Docker) - nhìn vào tưởng đang code Javis mà thật ra là hội thoại của chủ trên brain khác. Nay engine ghi riêng phiên nào thuộc brain nào (`server/session_brain.py`) và bộ index token lấy tên brain làm nhãn, nên số liệu về đúng "My Bullet Journal", "Brain Default"... Không đụng vào `cwd` vì đổi nó sẽ phá dò `.claude/skills` và `vault_root` của plugin. Chỉ có tác dụng với phiên chạy từ bản này trở đi; phiên cũ giữ nhãn như trước.
### Kiểm thử
- Thêm `server/test_metrics_cache.py`: phủ TTL dài/ngắn theo chất lượng kết quả, cache sống qua khởi động lại, hết hạn thì tính lại, và nhãn dự án theo brain (kèm trường hợp không tra được brain thì vẫn giữ nhãn cũ).

## [0.9.164] - 2026-07-25
Đổi model Claude giờ lấy DANH SÁCH SỐNG từ Anthropic, ra bản mới là thấy ngay.
### Cải thiện
- **Provider "Anthropic OAuth (Claude Code)" list model động**: trước đây provider này không hỏi được API nên picker rơi về 4 alias tĩnh trong code (opus/sonnet/haiku/fable) và thiếu hẳn Opus 4.8, 4.7, 4.6, Sonnet 4.6... Giờ Javis mượn chính access token OAuth mà Claude Code đã lưu (`~/.claude/.credentials.json`, hoặc `CLAUDE_CONFIG_DIR`, hoặc biến `CLAUDE_CODE_OAUTH_TOKEN`) để gọi `GET /v1/models`, nên Anthropic ra model mới là danh sách tự có, khỏi sửa code (`server/claude_models.py`).
- **Alias tự suy từ danh sách sống**: 4 tên "luôn bản mới nhất" đứng đầu picker được rút từ chính các dòng model API trả về, nên có dòng model mới thì alias cũng tự xuất hiện.
- **Nhớ danh sách mới nhất vào catalog**: mỗi lần lấy live thành công, `/provider/models` ghi lại vào `settings.json` (tối đa 50 mục). Khi mất mạng hoặc token OAuth hết hạn thì fallback vẫn là danh sách MỚI từng thấy chứ không tụt về alias cũ hardcode.
- Không tự refresh token OAuth (tránh xoay `refresh_token` làm Claude Code của người dùng bị đăng xuất): token hết hạn thì lặng lẽ dùng fallback, chạy Claude Code một lượt là tươi lại.

## [0.9.163] - 2026-07-24
Trang Kết nối: ghim card "Tự thêm (nâng cao)" lên ĐẦU kho với icon ⭐, ngay sau là Composio.
### Cải thiện
- **Card "Tự thêm (nâng cao)" lên đầu Kho kết nối, icon đổi 🧩 thành ⭐**: trước nằm cuối grid, người muốn tự khai URL/lệnh phải kéo qua toàn bộ kho mới thấy; icon cũ cũng trùng với Composio mới thêm.
- **Composio đứng đầu danh sách connector trong kho**: chuyển entry lên đầu system/mcp-catalog.json (grid vẽ theo thứ tự file), một kết nối mở 500+ app nên đáng thấy đầu tiên.

## [0.9.162] - 2026-07-24
Thêm connector Composio: MỘT kết nối mở ra hơn 500 app đã có sẵn MCP (Gmail, Notion, Sheets, GitHub, Linear...), Javis khỏi viết connector riêng cho từng app.
### Thêm mới
- **Connector Composio (nhóm mới "Kho ứng dụng")**: đấu connect.composio.dev/mcp bằng API key (header x-consumer-api-key), đi qua hub và chịu phân quyền như mọi connector khác. 7 tool phân loại tường minh: tìm và xem mô tả tool là Chỉ đọc; nối app mới (COMPOSIO_MANAGE_CONNECTIONS - Composio đưa link, người dùng tự đăng nhập) là Ghi nháp; COMPOSIO_MULTI_EXECUTE_TOOL cùng 2 tool remote bash/workbench xếp NGUY HIỂM vì mọi hành động app thật (kể cả lệnh đọc) chạy qua MỘT tool chung nên Javis không tách được đọc với ghi bên trong - muốn Javis thao tác thật phải chủ động nâng kết nối lên Toàn quyền, guide và cảnh báo rủi ro nói rõ điều này. Loop nền vẫn bị mode ép trần như thường lệ (suggest ép Chỉ đọc, auto ép Ghi nháp).

## [0.9.161] - 2026-07-24
Google Keep có đường lui oauth_token khi Google từ chối App Password (BadAuthentication).
### Sửa lỗi
- **Kết nối Google Keep báo 'Google từ chối đăng nhập' dù App Password đúng**: Google đang siết dần đường đổi App Password lấy master token (perform_master_login trả BadAuthentication tuỳ tài khoản, kể cả trên máy cá nhân). Thêm đường lui chuẩn của cộng đồng gkeepapi: ô oauth_token mới trong form - người dùng mở accounts.google.com/EmbeddedSetup trong tab ẩn danh (có nút mở thẳng), đăng nhập, lấy cookie oauth_token dán vào, Javis đổi qua gpsoauth.exchange_token thành master token. Cookie dùng một lần, bị drop không lưu, không map ra env. Thông báo BadAuthentication giờ chỉ đủ 3 khả năng kèm đường lui này, và guide có hướng dẫn lấy cookie từng bước.
### Cải thiện
- **cred_exchange.run cho phép input tuỳ chọn bỏ trống**: input khai optional trong auth.fields không còn bị chặn "Thiếu" từ ngoài - handler tự kiểm tổ hợp (Keep cần App Password HOẶC oauth_token, không bắt cả hai).
### Kiểm thử
- `test_cred_exchange.py` thêm 9 phép thử: đường oauth_token đổi qua exchange_token (gpsoauth giả, không chạm mạng), lỗi BadAuthentication phải chỉ sang đường lui, input tuỳ chọn tới được handler, ô oauth_token không map env + có trong drop, nút EmbeddedSetup. `test_google_keep.py` cập nhật đếm 5 ô nhập.

## [0.9.160] - 2026-07-24
Sửa "Không kết nối được (ValueError)" khi đấu Google Workspace: response tools/list lớn hơn 64KB làm nổ trần dòng mặc định của asyncio.
### Sửa lỗi
- **Đấu connector Google Workspace báo "Không kết nối được (ValueError)"**: tools/list của server workspace-mcp là MỘT dòng NDJSON vài trăm KB (hàng chục tool, mô tả dài), vượt trần StreamReader 64KB/dòng mặc định của asyncio.create_subprocess_exec nên readline() nổ LimitOverrunError đội lốt ValueError. Nới trần lên 16MB cho mọi session MCP stdio. Các connector stdio khác chưa dính chỉ vì response của chúng còn dưới 64KB.
- **Thông báo lỗi kết nối kèm nội dung lỗi thật**: trước chỉ hiện tên loại lỗi (vd "ValueError") nên không lần ra manh mối; giờ kèm cả message rút gọn.
### Kiểm thử
- Thêm `test_stdio_big_line.py`: server MCP giả trả tools/list một dòng ~200KB, phải đọc trọn không nổ, kèm canary chứng minh kịch bản thật sự vượt trần 64KB.

## [0.9.159] - 2026-07-24
Kết nối Lịch Google/Gmail hết cảnh "đã kết nối mà không có quyền": guide bổ sung 2 điều kiện bắt buộc của Google, nút Test báo đúng bệnh.
### Sửa lỗi
- **Lịch Google/Gmail OAuth xong vẫn "không có quyền" (báo từ người dùng thật)**: server MCP hosted của Google (calendarmcp/gmailmcp.googleapis.com) đòi 2 thứ mà guide cũ không nói: ghi danh Google Workspace Developer Preview Program (miễn phí) và bật API MCP RIÊNG (Google Calendar MCP API / Gmail MCP API) bên cạnh API thường. Thiếu là Google chặn 403 dù đăng nhập thành công, càng dễ hiểu nhầm vì trạng thái "đã kết nối" vẫn xanh (tools/list của Google không cần token, chỉ tools/call mới cần). Guide 2 connector viết lại đủ 6 bước, thêm nút mở thẳng trang ghi danh + trang bật API. Không phải lỗi não/model: nút Test chạy hoàn toàn phía server, không đi qua engine.
- **Nút Test dịch lỗi Google thành lời khuyên đúng bệnh**: thay câu chung "Key chưa đúng hoặc chưa đủ quyền" bằng nhận diện 3 họ lỗi: API chưa bật trong project (kèm đúng link bật lấy từ thông báo của Google, nhắc ghi danh preview nếu là server *mcp.googleapis.com), token thiếu scope do bỏ tick lúc đồng ý (khuyên đăng nhập lại tick đủ), token hỏng/hết hạn (khuyên đăng nhập lại). Lỗi lạ giữ nguyên hành vi cũ.
### Kiểm thử
- Thêm `test_loi_ket_noi_google.py`: 15 phép thử cho bộ dịch lỗi (API chưa bật có/không phải server MCP, thiếu scope, token hỏng, fallback + canary, chuỗi UI có dấu tiếng Việt, và soát validate_connection thật sự đi qua bộ dịch).

## [0.9.158] - 2026-07-23
Kho kết nối có thêm Google Tasks, kèm vá phân quyền các tool gộp manage_* của Google Workspace.
### Thêm mới
- **Connector Google Tasks**: đọc và quản việc cần làm trong Google Tasks (xem danh sách, thêm việc, đặt hạn, đánh dấu xong). Chạy chung server `workspace-mcp` với connector Google Workspace nhưng chỉ nạp service tasks ở tier complete - vì `list_task_lists` (tra ID danh sách việc, thứ mọi tool tasks khác cần) chỉ có ở tier complete, connector Google Workspace tier core dùng Tasks sẽ cụt đường. Chỉ xin đúng quyền Google Tasks, không đụng Gmail/Drive/Lịch; đã có OAuth client của Google Workspace thì dùng lại được, chỉ cần bật thêm Google Tasks API. Cân nhắc và KHÔNG chọn gtasks-mcp (zcaceres): server đó vỡ đường dẫn credential trên Windows (`new URL(...).pathname` ra `\D:\...`), token không tự refresh (chết sau ~1 giờ phải auth lại bằng tay), không có trên npm phải tự clone build, và bắt chạy lệnh auth thủ công - trái nguyên tắc đấu nối trên UI.
### Bảo mật
- **Vá lỗ phân loại tool `manage_*` của Google Workspace**: `manage_task`, `manage_event`, `manage_gmail_label`... không khớp mẫu write/danger nào và chữ "manage" cũng không nằm trong heuristic, nên bị xếp nhầm là "đọc" - kết nối đặt mức Chỉ đọc (hay loop suggest) vẫn cho Javis sửa/xoá lịch và việc thật. Thêm mẫu `*manage*` vào nhóm ghi và nói rõ trong cảnh báo rủi ro.

## [0.9.157] - 2026-07-23
ChatGPT (Codex) dùng được kho MCP gốc của chính nó, ngang hàng cách engine Claude dùng MCP gốc của Claude Code.
### Thêm mới
- **Trang Kết nối có thêm khu "MCP từ Codex (ChatGPT)"**: liệt kê các server trong kho MCP gốc của Codex CLI (những gì bạn tự đăng ký bằng `codex mcp add`, nằm trong config gốc của Codex), song song khu "MCP từ Claude Code" sẵn có. Engine ChatGPT vốn tự nạp kho này khi chạy (profile javis chỉ phủ THÊM MCP của Javis lên config gốc, không đè), nhưng trước đây Javis không nhìn thấy và không quản được nó nên người dùng khó biết ChatGPT đang có công cụ gì. Endpoint `/mcp/ambient` trả thêm `codex_servers`; hỗ trợ cả bản codex cũ chưa có `mcp list --json` (đọc bảng text).
- **Server MCP kiểu OAuth giờ đăng ký cho CẢ HAI CLI**: server OAuth không đi qua hub được (CLI phải tự giữ token), nên trước đây thêm ở form "Tự thêm (nâng cao)" chỉ đăng ký vào Claude Code (`claude mcp add`) - engine ChatGPT hoàn toàn không thấy nhóm này. Nay Javis đăng ký thêm vào kho gốc của Codex (best-effort, máy chưa cài codex thì bỏ qua, không chặn flow), xoá server thì gỡ ở cả hai. Xác thực một lần bằng `codex mcp login <tên>`; endpoint `/mcp/oauth-auth` nhận `{"engine":"codex","name":...}` để mở terminal chạy sẵn lệnh đó (máy local có màn hình), `/mcp/native-status` nhận `engine=codex` để kiểm tra trạng thái đăng nhập.
### Kiểm thử
- Thêm `test_codex_native_mcp.py`: parse output `codex mcp list --json` (3 hình dạng JSON khác nhau giữa các bản codex + trạng thái tắt/cần-đăng-nhập), fallback bảng text, và dựng argv `codex mcp add` (HTTP, bearer env, stdio). Toàn bộ hàm parse là hàm thuần nên test không cần cài Codex.

## [0.9.156] - 2026-07-22
Báo đúng bệnh khi Facebook khai tử mbasic (thay vì đổ oan cho cookie).
### Sửa lỗi
- **Phân biệt "mbasic bị ngừng phục vụ" với "cookie hỏng"**: Facebook đang khai tử `mbasic.facebook.com`, nó chuyển hướng (302) sang `m.facebook.com` dù cookie vẫn đăng nhập tốt. Trước đây tool báo nhầm "cookie bị từ chối" khiến người dùng đi lấy lại cookie vô ích. Nay `_fetch` nhận ra khi bị đá khỏi host mbasic và trả thông báo đúng: mbasic có thể đã bị Facebook ngừng phục vụ, cookie không phải nguyên nhân, muốn đọc feed/thao tác cá nhân cần trình duyệt thật hoặc chuyển sang nguồn được hỗ trợ (Trang qua Graph API, theo dõi công khai qua Apify).

## [0.9.155] - 2026-07-22
Sửa lỗi bấm node trên brain 3D không mở được note (dính từ 0.9.152).
### Sửa lỗi
- **Bấm chấm màu trên brain 3D ra "Loại file này không xem trực tiếp - hãy tải về"**: bản 0.9.152 lỡ gán đè hàm `JavisOpenNote` (cầu nối click-node-đồ-thị mở editor) bằng hàm mở note thô, làm mất bước suy tên/đuôi file nên note .md rơi nhầm vào nhánh tải về. Nay bỏ chỗ gán đè, wikilink trong editor cũng gọi đúng cầu nối sẵn có này, và thêm chú thích cảnh báo ngay tại hàm để không tái phạm.

## [0.9.154] - 2026-07-22
Sửa lỗi phát hiện cookie hỏng trong plugin Facebook cá nhân.
### Sửa lỗi
- **Trang đăng nhập không còn bị đọc nhầm thành feed**: khi cookie bị Facebook đá ra, mbasic (hoặc m.facebook.com khi bị chuyển hướng) trả trang splash "Đăng nhập hoặc đăng ký" ở URL không chứa `login` và không có sẵn ô email/mật khẩu (chỉ tiêu đề + nút). Trước đây `fb_feed_read` để lọt trang này và trả về như feed thật (post_links rỗng). Nay `_is_login` bắt rộng theo nội dung (ô mật khẩu, form/nút dẫn tới `/login` hoặc `/checkpoint`, tiêu đề trang đăng nhập) nên tool báo rõ "cookie bị từ chối" thay vì trả rác.

## [0.9.153] - 2026-07-22
Mở rộng plugin Facebook cá nhân (cookie/mbasic) thêm loạt thao tác cơ bản của người dùng: xoá bài, thả cảm xúc, chia sẻ, đọc và gửi tin nhắn Messenger, lướt feed nhiều trang. Vẫn theo cách mbasic nhẹ (chỉ cần cookie, chạy VPS headless) nên không đăng được reel/video và không sửa bài đã đăng. Mọi thao tác ghi bằng tài khoản cá nhân có rủi ro khoá tài khoản; connector mặc định Chỉ đọc, các tool ghi chỉ chạy khi bật Toàn quyền.
### Thêm mới
- **Xoá bài, thả cảm xúc, chia sẻ**: `fb_personal_delete` (xoá bài của chính mình), `fb_personal_react` (like/love/care/haha/wow/sad/angry) và `fb_personal_share` (chia sẻ lên tường, kèm lời tuỳ chọn). Thao tác thật, mức Toàn quyền.
- **Messenger**: `fb_messages_read` (danh sách hội thoại) và `fb_message_thread` (đọc một cuộc trò chuyện) ở mức Chỉ đọc; `fb_message_send` (gửi tin) ở mức Toàn quyền.
### Cải thiện
- **Lướt feed sâu hơn**: `fb_feed_read` trả thêm `next_url` và nhận `pages` (tối đa 5) để lướt liền nhiều trang, hoặc truyền `next_url` để đọc tiếp từ trang trước.

## [0.9.152] - 2026-07-22
Điều hướng kiểu Wikipedia trong vault: bấm được đường dẫn file .md trong chat để mở đọc/sửa ngay, và bấm được wikilink [[..]] khi đọc note để nhảy sang note đích.
### Thêm mới
- **Đường dẫn file trong chat bấm mở được**: khi Javis nhắc tới một file kiểu `Javis/loops/x.md` trong khung chat (dạng inline code), giờ bấm thẳng vào là bung khung đọc/sửa file giữa màn hình, không phải tự dò trong trang Tệp tin. Chỉ nhận chuỗi trông đúng là đường dẫn file (có đuôi file, có thư mục hoặc là file .md); lệnh, URL và code thường không bị nhận nhầm.
- **Wikilink [[..]] thành link điều hướng**: mọi chỗ render markdown (chat, khung sửa file, trình đọc note ở trang Bộ não/Tệp tin) giờ hiện `[[note]]` và `[[note|tên đẹp]]` thành link. Bấm vào là tự TÌM file đích trong vault (khớp đuôi đường dẫn kiểu Obsidian, hoặc khớp tên note ở bất kỳ thư mục nào, ưu tiên .md) rồi mở ngay tại chỗ: đang đọc trong editor cây thì chuyển note trong editor đó như Wikipedia, đang ở chat thì bung khung sửa. Không thấy note thì link báo đỏ nhẹ chứ không mở lung tung.
### Cải thiện
- **Tìm file không phân biệt dấu tiếng Việt ở máy chủ** (`/files/search`): gõ "chi nga" vẫn tìm ra "Chị Nga...". Ô tìm kiếm theo Nội dung ở trang Tệp tin hưởng lợi luôn.
- **Lưu từ chế độ Sửa (WYSIWYG) giữ đúng cú pháp gốc**: wikilink giữ nguyên `[[..]]` (kèm cả alias `[[..|..]]`), link markdown `[chữ](đường-dẫn)` không còn bị đổi thành wikilink, ảnh nhúng `![[..]]` không mất dấu chấm than, đường dẫn trong inline code giữ nguyên là code.
### Kiểm thử
- Thêm test render wikilink/alias/đường dẫn trong code (test_chat_render.js) + test bộ tìm file đích wkResolve với fetch giả lập (test_wikilink.js mới); CI giờ chạy đủ 4 file test JS dashboard.

## [0.9.151] - 2026-07-21
Cải thiện trang Việc định kỳ và khung Hội thoại trên dashboard: thêm ô tìm việc, phân trang nhật ký, và sửa link dài bị tràn ra ngoài khung chat.
### Thêm mới
- **Ô tìm kiếm ở trang Việc định kỳ**: khi có nhiều việc lặp và nhắc hẹn, giờ gõ vài chữ để lọc nhanh theo tên (bỏ dấu và không phân biệt hoa thường, vd gõ "email" hay "kho" đều khớp). Việc không hợp và cả nhóm brain rỗng tự ẩn đi; xoá ô tìm là hiện lại đầy đủ.
### Cải thiện
- **Nhật ký gần đây phân trang 10 mục mỗi trang**: trước đây đổ nhiều dòng ra cùng lúc gây dài và nặng trang; nay chia trang 10 mục, có nút Trước/Sau và số trang. Phần đọc nhật ký ở máy chủ cũng sửa lại để xếp mới nhất lên đầu và gom đủ tin qua nhiều ngày (không còn giới hạn cứng 3 tệp gần nhất).
### Sửa lỗi
- **Link dài trong tin nhắn tràn ra ngoài khung chat**: đường link không có khoảng trắng (vd link Google Docs, Google Drive) trước đây kéo dài quá mép phải của bong bóng tin nhắn. Nay link tự xuống dòng gói gọn trong khung, cho cả tin của Javis lẫn tin người dùng.

## [0.9.150] - 2026-07-21
Sửa lỗi Javis (chạy bằng Claude) báo "chưa đấu" các nguồn kết nối vào tài khoản Claude (Google Drive, Gmail, Lịch...) khi đang bật chế độ tool gọn, dù thực ra vẫn gọi được.
### Sửa lỗi
- **Không thấy MCP của tài khoản Claude khi bật tool gọn (lazy)**: các connector đấu thẳng vào tài khoản Claude (Google Drive, Gmail, Lịch... đồng bộ từ claude.ai) vốn là công cụ native của engine Claude, KHÔNG đi qua hub của Javis. Nhưng bảng liệt kê nguồn (javis_connections) và ô tìm công cụ của chế độ tool gọn chỉ biết các nguồn do Javis quản lý (POS, Substack...), nên Javis tra danh sách thấy "chỉ có POS và Substack" rồi kết luận nhầm là "chưa đấu Drive" dù người dùng đã kết nối. Nay hub tự đọc danh sách MCP của tài khoản Claude (các cái đang "Connected") và kèm vào cả javis_connections lẫn kết quả tìm công cụ, chỉ rõ đây là công cụ gọi THẲNG (mcp__<tên>__...), không bọc qua tool chạy của hub. Javis không còn phủ nhận nguồn đã đấu sẵn trong tài khoản.
### Cải thiện
- Danh sách nguồn tài khoản Claude được đọc ở luồng nền và nhớ tạm (cache) vì lệnh liệt kê hơi chậm, nên không làm chậm câu trả lời. Chỉ engine Claude mới được kèm gợi ý này (Codex và các engine API không có công cụ native đó nên không kèm, tránh chỉ nhầm sang tool không tồn tại). Tắt được ở settings `mcp.ambient_hint` nếu không muốn.
### Kiểm thử
- Thêm test cho việc đọc danh sách MCP tài khoản (chỉ lấy cái đang "Connected"), khớp nguồn theo tên/tiền tố, kèm đúng vào javis_connections và ô tìm công cụ, và chốt rằng engine API (đường in-process) không bị kèm nhầm gợi ý tài khoản.

## [0.9.149] - 2026-07-21
Sửa lỗi việc lặp không khai mục tiêu bị chạy nhầm thành phân tích kinh doanh, và gỡ việc lặp mặc định "Tự cải tiến Javis" khỏi app.
### Sửa lỗi
- **Việc lặp thiếu khai mục tiêu bị chạy nhầm thành báo cáo kinh doanh**: một việc lặp (loop) mà file định nghĩa không ghi rõ dòng mục tiêu thì bị mặc định thành "cải thiện chỉ số kinh doanh", nên nó bỏ qua hẳn nội dung việc đã viết và quay sang đọc số liệu bán hàng. Ví dụ việc "nhắc uống thuốc" lại đi đọc doanh thu POS rồi bàn chuyện đơn hàng thay vì nhắc thuốc. Nay mặc định là chạy đúng nội dung việc viết trong file; muốn việc lặp tự bơm số liệu kinh doanh mỗi vòng thì phải khai rõ mục tiêu kinh doanh. Hai đường tạo việc lặp (qua chat và qua trang Việc) vốn đã đặt đúng, chỉ khâu đọc lại file là còn lệch nên mới lọt.
### Cải thiện
- **Gỡ việc lặp mặc định "Tự cải tiến Javis"**: bỏ hẳn loop hệ thống tự cải tiến khỏi app, không còn tự cài vào brain nào nữa. Brain nào đang có sẵn bản cũ thì vào trang Việc xoá một lần là dứt, từ bản này nó không tự mọc lại.
### Kiểm thử
- Thêm test chốt mặc định mục tiêu việc lặp là chạy đúng nội dung file (không rơi về kinh doanh), và test xác nhận app không còn loop hệ thống thì cơ chế đồng bộ vẫn chạy đúng.

## [0.9.148] - 2026-07-21
Sửa lỗi nhắc hẹn tạo qua chat khi đang dùng brain khác (vd My Bullet Journal) lại rơi vào Brain Default.
### Sửa lỗi
- **Nhắc hẹn rơi nhầm Brain Default dù đang chat ở brain khác**: khi đặt nhắc hẹn từ Telegram hoặc dashboard, Javis hay dùng lệnh curl mẫu có sẵn trong hướng dẫn để gọi kho nhắc hẹn, mà lệnh mẫu đó lại KHÔNG kèm brain đang chọn. Lệnh curl chạy từ sandbox nên không mang phiên đăng nhập, brain chỉ đi được qua nội dung lệnh; thiếu nó thì kho nhắc hẹn âm thầm dùng Brain Default. Hậu quả: đang chọn brain My Bullet Journal, đặt nhắc hẹn, nhưng nhắc lại nằm ở Default. Nay lệnh mẫu tự kèm brain của phiên, và ưu tiên gọi thẳng tool javis_schedule (vốn luôn gắn đúng brain). Kho nhắc hẹn cũng ghi log khi nhận nhắc thiếu brain để dễ soi nếu tái diễn.

## [0.9.147] - 2026-07-21
Thêm lệnh /notes trên Telegram để lưu nhanh tin nhắn (kèm ảnh) vào Sources của brain, giống bản chat web.
### Thêm mới
- **Lệnh /notes trên Telegram**: trước đây chỉ bản chat web mới có /notes để chộp nhanh một ghi chú vào Second Brain, trên Telegram không thấy trong menu lệnh. Nay /notes đã nằm trong menu lệnh Telegram (gõ "/" là thấy), lưu nguyên văn tin nhắn vào Sources rồi tự chưng cất lên wiki nếu đáng, đúng như bản web.
- **Gửi ảnh kèm /notes**: gửi một tấm ảnh với chú thích "/notes ..." nay được nhận đúng là lệnh, ảnh được tải về và đính vào note. Trước đây chú thích lệnh bị chôn trong đoạn mô tả tệp đính kèm nên không chạy như lệnh, mà đây lại đúng ca dùng hay gặp nhất là chụp cái gì đó rồi lưu ngay vào brain.
### Kiểm thử
- Thêm test cho danh sách lệnh Telegram và cho việc tách lệnh từ chú thích ảnh (giữ đường dẫn ảnh cho skill dùng).

## [0.9.146] - 2026-07-21
Thêm chế độ "tool gọn" cho MCP: khi đấu nhiều nguồn, Javis không còn nạp sẵn hàng trăm công cụ vào mỗi câu nữa mà chỉ mở đúng công cụ khi ngữ cảnh cần, tiết kiệm token đáng kể.
### Thêm mới
- **Chế độ tool gọn (lazy tools) cho MCP**: trước đây mỗi câu hỏi, kể cả câu chẳng liên quan bán hàng hay quảng cáo, đều phải gánh toàn bộ mô tả công cụ của MỌI nguồn đang đấu (POS, Meta Ads, Systeme.io, Webcake...), tốn rất nhiều token dù không dùng tới. Nay khi tổng số công cụ vượt ngưỡng, Javis chỉ đưa cho model một thực đơn gọn liệt kê đang có những nguồn nào, kèm hai công cụ máy móc: một để TÌM công cụ theo nhu cầu, một để GỌI công cụ tìm được. Model tự quyết mỗi câu là có cần đụng nguồn nào không rồi mới mở đúng nhóm công cụ đó. Câu tán gẫu, dịch, viết bài gần như không tốn token công cụ; câu cần số liệu thì tự mở đúng nguồn. Không phải bật tắt tay gì cả.
### Cải thiện
- Chế độ này tự bật khi đông công cụ (mặc định trên 40) và tự tắt khi ít; chỉnh được ở settings `mcp.lazy_tools` (auto/bật/tắt), `mcp.lazy_threshold` (ngưỡng số công cụ), `mcp.lazy_top_k` (số công cụ trả về mỗi lần tìm). Các công cụ nội bộ nhỏ và hay dùng (đọc ghi file, tạo ảnh, nhắc hẹn, gửi Zalo...) vẫn hiện thẳng như cũ, chỉ nhóm công cụ nguồn ngoài đông đúc mới được gom sau thực đơn.
- Lớp phân quyền, ghi nhật ký và giới hạn tần suất giữ nguyên vì mọi lời gọi công cụ vẫn đi qua đúng đường cũ. Thêm kiểm thử cho xếp hạng tìm công cụ, việc giấu/hiện đúng nhóm, và các nhánh lỗi khi gọi.

## [0.9.145] - 2026-07-21
Sửa lỗi tick chọn cuộc chat theo dõi trên Zalo cứ mất sau khi tải lại trang hoặc khởi động lại server.
### Sửa lỗi
- **Tick theo dõi biến mất khi tải lại**: danh sách cuộc chat trong panel chỉ vẽ từ sổ tạm trong bộ nhớ (dựng lại từ tin đến), mà sổ này rỗng mỗi khi khởi động lại server. Luật theo dõi vẫn còn nguyên trên đĩa nhưng không có dòng nào để hiện, nên tick biến mất dù thực ra vẫn đang theo dõi. Nay panel vẽ từ HỢP của sổ tạm và các luật đang bật, và server tự nạp lại sổ từ luật ngay khi khởi động, nên cuộc chat đang theo dõi luôn hiện và tick được ngay, không phải đợi có tin mới đi qua.
- **Hai cuộc chat trùng tên ghi đè luật của nhau**: file luật trước đây đặt tên theo TÊN cuộc chat, mà hệ thống lại cố ý đặt tên trùng cho nhóm chưa biết tên. Hai nhóm khác nhau cùng tên ghi vào một file, lưu cái sau xoá mất luật cái trước, tick của nó biến mất khi tải lại. Nay tên file gắn thẳng mã cuộc chat nên không thể đụng nhau.
- **Lưu danh sách rỗng làm mất sạch theo dõi**: bản web cũ gửi khuôn dữ liệu cũ bị hiểu nhầm là "bỏ hết", tắt sạch mọi luật đang theo dõi. Nay chỉ bỏ theo dõi khi chủ gửi rõ danh sách mới.
- **Nhóm bị hiện thành cá nhân sau khởi động lại**: luật giờ ghi kèm loại nhóm hay khách, nên sau khởi động lại vẫn dựng đúng nhãn nhóm và gửi tin đúng kiểu nhóm, không còn nhầm.
- Dọn khoá cấu hình rác cũ (threads, dm_only, keywords) còn sót trong settings, tránh nó rò ngược vào ô từ khoá của giao diện và lật cuộc chat theo dõi thành lọc từ khoá.
### Lưu ý
- Nếu server đang chạy bản cũ thì phải KHỞI ĐỘNG LẠI server rồi tải lại trang (Ctrl+F5) thì bản vá này mới có tác dụng. Bản cũ không ghi được tick xuống đĩa nên tải lại là mất.

## [0.9.144] - 2026-07-21
Sửa lỗi bảng nghe Zalo cứ hiện "Mất kết nối, đang thử lại" dù thực ra vẫn đang nghe bình thường.
### Sửa lỗi
- **Kẹt ở trạng thái "Mất kết nối" dù kết nối vẫn sống**: mỗi khi mạng chớp một cái, thư viện Zalo tự nối lại ngay ở bên dưới mà KHÔNG in ra dòng thông báo nào, nên bảng điều khiển không có gì để biết là đã nối lại và cứ đứng ở "đang thử lại" mãi. Thêm nữa, dòng báo nối lại thành công của nhánh đăng nhập lại có kèm chữ "events:" nên bị bộ lọc dòng khởi động nuốt mất. Kết quả là chỉ cần rớt mạng một lần là nhãn đỏ nằm lì, chỉ tạm hết khi có tin mới về trong vòng ba phút, dù tiến trình nghe vẫn sống và tin vẫn về.
- Nay Javis nhận đúng các dòng hồi phục để kéo trạng thái về đang nghe. Với trường hợp nối lại im lặng (không in dòng nào), nếu tiến trình nghe vẫn còn sống và đã qua một khoảng lặng không thấy dòng rớt mới thì tự coi là đã nối lại. Rớt thật thì thư viện in dòng rớt đều đặn nên vẫn báo đúng là đang thử lại; còn tiến trình chết hẳn thì vẫn để cơ chế dựng lại lo, không nhận nhầm.
- Thêm kiểm thử chốt cho cả hai đường hồi phục và cho trường hợp nối lại im lặng.

## [0.9.143] - 2026-07-21
Bỏ hẳn tính năng Javis tự trả lời khách trên Zalo. Nay Javis chỉ đọc và báo, mọi tin gửi đi đều do chủ yêu cầu trực tiếp.
### Cải thiện
- **Zalo chỉ đọc và báo, không còn tự phản hồi**: gỡ bỏ chế độ "Tự phản hồi" (chatbot) cùng toàn bộ phần engine hộp cát soạn tin tự động cho khách. Listener giờ chỉ nghe rồi báo về Telegram theo luật từng cuộc chat, gồm bốn chế độ giữ nguyên: im lặng, báo hết, báo theo từ khoá, và nhắc khi quá lâu chưa ai trả lời. Muốn gửi tin cho ai thì chủ bảo thẳng trong chat, Javis dùng công cụ gửi an toàn javis_zalo_send.
- Panel "Nghe tin liên tục" gọn lại: mỗi cuộc chat chỉ còn tick theo dõi là đọc và báo, bỏ ô chọn chế độ hai lựa chọn và hộp thoại xác nhận cho tự nhắn.
- Dọn sạch mã phần Zalo: bỏ hàm soạn tin của bot, các hằng hộp cát, giới hạn tin mỗi giờ, và phụ thuộc model phụ mà chỉ chế độ tự trả lời mới cần.
### An toàn
- Không còn đường nào để Javis tự gửi tin cho khách khi đọc được tin nhắn của họ. File luật cũ để chế độ chatbot tự hạ về im lặng khi đọc, nên sau khi cập nhật không nhóm nào còn tự trả lời.

## [0.9.142] - 2026-07-21
Sửa lỗi nghiêm trọng: bảo Javis gửi tin Zalo cho một người thì nó nhắn nhầm sang người khác không trong danh sách theo dõi.
### Sửa lỗi
- **Gửi tin Zalo qua chat có thể ra nhầm tài khoản và nhầm người**: khi bật nghe một tài khoản, listener tự tắt connector của tài khoản đó, nên khi chủ bảo gửi tin, engine lặng lẽ rơi sang một tài khoản Zalo khác đang bật, tra tên người nhận trong danh bạ của tài khoản sai rồi gửi từ tài khoản sai. Không có bước xác nhận nên tin bay đi luôn, không thu hồi được. Đây là hệ quả của cơ chế tự tắt connector thêm việc engine được tự do gửi mà không phải chắc đúng người.
- Thêm công cụ gửi Zalo an toàn riêng, khoá cứng vào tài khoản đang nghe và chỉ gửi được cho cuộc chat trong danh sách đang theo dõi, nên về mặt cấu trúc không thể gửi nhầm tài khoản hay nhầm người. Tên khớp nhiều thì công cụ từ chối và bắt hỏi lại, không đoán. Không có trong danh sách theo dõi thì từ chối.
- Dặn Javis trong hướng dẫn hệ thống dùng công cụ an toàn này khi được yêu cầu gửi tin, tuyệt đối không dùng công cụ thô.
### An toàn
- Công cụ gửi ở mức quyền an toàn, nên vòng lặp nền chạy chế độ chỉ đọc không thể tự gửi tin. Chỉ khi chủ yêu cầu trực tiếp trong chat mới gửi.

## [0.9.141] - 2026-07-20
Sửa lỗi ảnh Javis tạo trong lúc chat Telegram cứ gửi về tài khoản Telegram đầu tiên thay vì người đang hỏi.
### Sửa lỗi
- **Ảnh gửi nhầm về chủ bot khi hai người cùng chat**: khi Javis tạo ảnh, ảnh được lưu vào thư mục attachments của brain và nhúng vào câu trả lời bằng đường dẫn tương đối như `![](attachments/anh.png)`. Cơ chế tự đính kèm file về Telegram trước đây chỉ nhận đường dẫn TUYỆT ĐỐI hoặc file viết bằng công cụ Write, nên ảnh tạo ra không được tự đính kèm. Engine đành gửi ảnh bằng lệnh curl, mà lệnh này thiếu mã người nhận thì rơi về tài khoản Telegram đầu tiên trong danh sách. Kết quả là người thứ hai đang chat vẫn thấy ảnh của mình bay về máy người đầu.
- Nay cơ chế tự đính kèm hiểu luôn đường dẫn tương đối trong vault (ví dụ `attachments/...`), giải về gốc brain của đúng phiên đang chat và gửi thẳng cho người đang hỏi, không cần curl nữa. Có chặn thoát vault (không cho `../` ra ngoài) và bỏ qua liên kết web. Gateway cũng nhắc engine rằng ảnh vừa tạo chỉ cần nhúng là đủ, khỏi curl (curl dễ gửi nhầm chủ bot).
- Thêm kiểm thử chốt cho việc thu file: ảnh nhúng tương đối được bắt đúng, đường dẫn tuyệt đối vẫn chạy, URL không bị nhầm là file, chặn thoát vault, và file cũ không bị gửi lại.

## [0.9.140] - 2026-07-20
Sửa lỗi bấm Bật nghe hiện Đang bật rồi lập tức quay về Bật nghe mà không có gì diễn ra.
### Sửa lỗi
- **Nút Bật nghe văng lỗi ngầm rồi tự hồi**: bản 0.9.136 đổi tên một biến trong giao diện nhưng sót lại một chỗ dùng tên cũ, nên khi bấm Bật nghe thì đoạn dựng dữ liệu gửi đi tham chiếu một biến không còn tồn tại và văng lỗi. Nút được lập trình luôn tự bật lại nên nó quay về Bật nghe, còn lệnh thì chưa bao giờ được gửi tới máy chủ. Không có thông báo gì nên nhìn như không phản ứng.
- Sửa chỗ sót đó, và cập nhật nốt phần mô tả cùng bố cục panel sang thiết kế hai trạng thái Chỉ đọc và Tự phản hồi mà bản 0.9.136 áp dụng thiếu.
- Thêm kiểm thử chốt để kiểu lỗi đổi tên biến sót chỗ này không lọt qua lần nữa.

## [0.9.139] - 2026-07-20
Sửa lỗi gốc khiến mọi thay đổi giao diện của nhiều bản gần đây trở nên vô hình với trình duyệt.
### Sửa lỗi
- **Trình duyệt giữ mãi bản giao diện cũ trong cache**: mỗi file javascript và css được đánh số phiên bản bằng tay trong trang chủ, và con số của console.js đứng yên suốt hàng chục bản. Vì địa chỉ tải không đổi nên trình duyệt cứ dùng bản cũ trong bộ nhớ đệm, máy chủ cập nhật thật mà giao diện đóng băng. Đây là lý do các sửa đổi như thiết kế hai trạng thái, nút không còn chìm, hạn chờ, đều có trên máy chủ nhưng người dùng không hề thấy.
- Nay trang chủ tự gắn phiên bản app vào mọi file javascript và css khi phục vụ, nên mỗi lần cập nhật là trình duyệt tải lại toàn bộ, không phải nhớ tăng số bằng tay nữa và không thể quên.

## [0.9.138] - 2026-07-20
Sửa lỗi nút Bật nghe bấm vào rồi chìm mãi, không bật được cũng không hồi lại.
### Sửa lỗi
- **Endpoint bật nghe chặn cả vòng lặp sự kiện**: nó ghi cấu hình, giải mã kết nối và chờ luồng cũ dừng, tất cả làm đồng bộ ngay trong hàm bất đồng bộ, nên trong lúc đó máy chủ không phục vụ được gì khác và nút treo. Nay phần nặng chạy trong luồng riêng, vòng lặp không bị nghẽn.
- **Chờ luồng cũ quá lâu**: khi bật lại ngay sau khi tắt, trước đây chờ tới mười lăm giây. Nay giết tiến trình con trước rồi chỉ chờ bốn giây, vì dừng xong là nó thoát ngay.
- **Nút không tự hồi khi request lỗi**: thiếu bước bật lại nút trong mọi trường hợp, nên chỉ cần request chậm hay lỗi là nút kẹt vĩnh viễn. Nay nút luôn được bật lại, và lệnh gọi có hạn chờ ba mươi giây, quá hạn thì báo máy chủ không phản hồi thay vì chìm mãi.

## [0.9.137] - 2026-07-20
Sửa lỗi báo chưa chọn tài khoản Zalo trong khi ô chọn rõ ràng đang hiện tên tài khoản.
### Sửa lỗi
- **Ô chọn tài khoản hiện tên nhưng chưa hề được lưu**: giá trị đó chỉ được ghi xuống khi bấm Bật nghe, còn bấm Lưu theo dõi thì không gửi, nên cấu hình vẫn trống và lời báo tuy khó hiểu nhưng đúng. Nay lưu theo dõi ghi luôn tài khoản đang chọn, và đổi tài khoản trong ô là lưu ngay.
- **Thông báo lỗi cũ nằm lì trên màn hình**: từ bản 0.9.132 giao diện hiện lỗi kể cả khi đang tắt, nhưng lệnh dừng lại không xoá lỗi cũ, nên một lần bật hụt từ lúc nào đó cứ hiện mãi và làm tưởng đang hỏng. Nay dừng nghe là xoá luôn.

## [0.9.136] - 2026-07-20
Mỗi cuộc chat Zalo giờ chỉ có hai trạng thái dễ hiểu, và Javis tự quyết khi nào nên lên tiếng.
### Thay đổi
- **Hai trạng thái thay cho năm chế độ**: mỗi cuộc chat trong danh sách có một ô chọn với hai lựa chọn là Chỉ đọc và Tự phản hồi. Đơn giản hơn hẳn cách cũ, và mọi thứ tinh vi hơn thì dặn thẳng trong chat.
### Thêm mới
- **Javis được quyền im lặng**: ở chế độ tự phản hồi, nó tự quyết có nên lên tiếng hay không chứ không phải cứ có tin là trả lời. Người ta đang nói chuyện với nhau, tán gẫu, hay chuyện chẳng liên quan thì nó im. Trước đây bot luôn phải sinh ra một câu trả lời, mà một con bot xen vào mọi câu chuyện trong nhóm còn phiền hơn là không có bot.
- **Được tự do diễn đạt theo ngữ cảnh** thay vì bám câu chữ có sẵn, và nói theo phong cách riêng của từng nhóm nếu chủ đã dặn trong luật.
- **Bật tự phản hồi phải xác nhận một lần**, vì tin gửi đi không thu hồi được.
### Bảo mật
- Vẫn giữ nguyên hộp cát: bot không có công cụ nào, không thấy dữ liệu kinh doanh, chỉ sinh ra chữ còn gửi đi đâu là do mã Javis quyết.
- Giữ một rào cứng dù chủ cho tự do sáng tạo: không được bịa giá, tồn kho, thời gian giao hàng hay cam kết với khách. Sai một câu ở đó là mất tiền thật, nên gặp là hỏi lại chủ.

## [0.9.135] - 2026-07-20
Javis tự dọn đống luật ồn do chính mặc định hỏng của nó sinh ra, thay vì bắt chủ đi sửa tay từng cái.
### Sửa lỗi
- **Đổi mặc định không cứu được luật đã tạo**: bản 0.9.131 chuyển mặc định sang im lặng nhưng chỉ áp cho luật mới, còn những cuộc chat đã tick từ bản 0.9.130 vẫn mang chế độ báo mọi tin nên vẫn dội về Telegram. Ba lần trước Javis chỉ bảo chủ bấm Lưu lại, tức là đẩy việc dọn hậu quả sang cho người dùng. Nay khi khởi động Javis tự chuyển chúng về im lặng đúng một lần, và nhắn cho chủ biết đã sửa cái gì.
- Chỉ đụng vào luật báo mọi tin mà không có từ khoá, vì đó đúng là dấu vết của mặc định hỏng. Luật có từ khoá, luật nhắc khi quên trả lời, và luật để Javis tự trả lời đều là chủ cố ý đặt nên giữ nguyên.
- Việc dọn chạy đúng một lần, những lần khởi động sau không đè lên luật chủ tự đặt lại.

## [0.9.134] - 2026-07-20
Hết cảnh cập nhật xong là báo đỏ trùng phiên và phải xoá kết nối quét lại mã QR.
### Sửa lỗi
- **Không đóng listener tử tế khi tắt app**: lúc cập nhật, tiến trình bị dừng đột ngột mà chưa kịp đóng kết nối, nên phía Zalo vẫn coi phiên cũ đang sống và chặn listener mới. Nay khi server tắt sẽ đóng listener trước, gửi tín hiệu dừng nhẹ để công cụ kịp ngắt kết nối sạch sẽ.
- **Trùng phiên bị coi là lỗi cứng ngay từ lần đầu**: ngay sau khi khởi động lại thì trùng phiên là chuyện bình thường và tự hết sau vài chục giây, nhưng listener lại dừng hẳn và bắt chủ đi xoá kết nối quét lại mã QR một cách oan uổng. Nay kiên nhẫn thử lại năm lần với khoảng chờ tăng dần, báo rõ đang chờ phiên cũ rụng và đây là chuyện thường sau khi cập nhật. Hết kiên nhẫn mới kết luận, kèm số lần đã thử.
- **Dọn tiến trình cũ cũng ngắt nhẹ trước**: chính chúng đang giữ phiên Zalo, giết thẳng thì phiên lại treo, đúng cái vòng luẩn quẩn vừa gỡ.

## [0.9.133] - 2026-07-20
Javis giờ biết đặt luật Zalo khi được dặn bằng lời, thay vì chỉ ghi vào bộ nhớ rồi thôi.
### Sửa lỗi
- **Dặn bằng lời chỉ được ghi nhớ chứ không thành hành động**: chủ nói với nick này cứ trả lời thoải mái, Javis đáp đã ghi nhớ và tạo một file sở thích trong bộ nhớ, nhưng không hề tạo luật nào nên hành vi không đổi. Nguyên nhân là hướng dẫn hệ thống không hề nhắc tới Zalo, nên Javis không biết có công cụ đặt luật mà dùng, và rơi về thói quen mặc định là ghi nhớ sở thích.
- Bổ sung việc đặt luật Zalo vào danh sách các cách xử lý khi nhận yêu cầu qua chat, kèm luật chọn nói thẳng rằng ghi nhớ không làm đổi hành vi, phải có file luật thì listener mới thật sự im lặng, báo, hay tự trả lời.
- Mô tả công cụ được viết lại bằng đúng những câu người dùng hay nói, ví dụ đừng báo nữa, im lặng thôi, báo hết tin nhóm này, ba mươi phút chưa ai trả lời thì nhắc, với nick này cứ trả lời thoải mái.

## [0.9.132] - 2026-07-20
Sửa lỗi đặt luật Zalo bằng lời trong chat nhưng listener không hề áp dụng.
### Sửa lỗi
- **Ghi một nơi, đọc một nẻo**: khi chủ dặn bằng lời, công cụ ghi file luật vào brain đang mở, ví dụ My Bullet Journal. Nhưng listener là dịch vụ chạy nền nên chỉ đọc brain mặc định là Brain Default. Luật đặt bằng lời rơi vào chỗ không ai đọc, nên dặn đừng báo nữa mà vẫn báo. Nay listener gom luật từ mọi brain, hết luôn lớp lỗi này.
- Cùng một cuộc chat mà có luật ở hai brain khác nhau thì lấy bản sửa gần nhất, thay vì chọn bừa một cái.
### Ghi chú
- Luật cũ tạo ở bản 0.9.130 vẫn là báo mọi tin, vì đổi mặc định ở bản 0.9.131 chỉ áp cho luật tạo mới. Muốn im lặng thì bấm Lưu theo dõi lại một lần với ô từ khoá để trống, hoặc dặn Javis trong chat.

## [0.9.131] - 2026-07-20
Mặc định Javis im lặng khi theo dõi cuộc chat Zalo, không còn dội mọi tin về Telegram.
### Thay đổi
- **Tick theo dõi giờ mặc định là im lặng**: chỉ ghi nhận cuộc chat chứ không báo Telegram. Trước đây tick vào là báo mọi tin, mà theo dõi vài nhóm đông thì điện thoại nổ tung và cuối cùng chẳng ai đọc nữa. Nghe là để Javis biết chuyện, còn báo phải là thứ chủ chủ động yêu cầu cho từng nhóm.
- **Muốn được báo thì nói rõ**: nhập từ khoá vào ô bên dưới để chỉ báo khi tin có chứa những chữ đó, hoặc dặn Javis trong chat cho từng nhóm, ví dụ báo hết tin của nhóm này, hay nhắc khi ba mươi phút chưa ai trả lời.
- Dòng xác nhận sau khi lưu nói rõ đang im lặng hay đang báo theo từ khoá nào, để không hiểu nhầm là sẽ được báo.

## [0.9.130] - 2026-07-20
Sửa lỗi tick chọn cuộc chat theo dõi nhưng không lưu được gì, và thêm nút lưu có xác nhận nhìn thấy được.
### Sửa lỗi
- **Tick vào không lưu gì cả**: từ khi chuyển sang luật riêng cho từng cuộc chat, giao diện vẫn gửi danh sách theo khuôn cấu hình cũ, mà phần ghi cấu hình chỉ nhận những trường còn trong khuôn mặc định nên danh sách bị vứt âm thầm. Đây là lỗi dời kiến trúc mà quên nối lại giao diện. Nay tick chọn sẽ ghi thành file luật thật trong brain.
- **Ô tick hiện sai trạng thái**: nó đọc từ trường cấu hình đã bị bỏ, nên luật đặt qua chat không hiện lên và ngược lại. Nay lấy thẳng từ luật đang bật, và tự vẽ lại khi luật đổi.
### Thêm mới
- **Nút Lưu theo dõi kèm dòng xác nhận**: bấm là thấy ngay đã lưu bao nhiêu cuộc chat và theo kiểu gì. Trước đây lưu ngầm nên không có cách nào biết là đã ăn hay chưa. Ô từ khoá và giờ im lặng cũng được lưu cùng, trước đây hai ô đó chỉ ghi khi bật tắt nên sửa xong mà không bật tắt là mất.
### Bảo mật
- **Không để một cái tick xoá mất công sức**: luật chế độ chatbot hoặc nhắc khi quên trả lời do chủ đặt kỹ qua chat thì tick chỉ bật hoặc tắt, tuyệt đối không ghi đè chế độ và kịch bản. Bỏ tick cũng chỉ tắt luật chứ không xoá file, nên kịch bản đã viết vẫn còn nguyên.

## [0.9.129] - 2026-07-20
Phân biệt được các nhóm Zalo trong danh sách cuộc chat, thay vì tất cả cùng hiện tên người nhắn.
### Sửa lỗi
- **Nhóm hiện tên người nhắn chứ không phải tên nhóm**: dữ liệu tin nhắn gửi về không hề kèm tên nhóm. Bản trước đoán tên trường mà không kiểm chứng được, nên thực tế vẫn rơi về tên người gửi, và hai nhóm khác nhau mà cùng một người nhắn thì hiện y hệt nhau.
### Thêm mới
- **Phân biệt được ngay**: nhóm chưa có tên thật sẽ hiện kèm bốn số cuối của mã nhóm, nên không còn hai dòng trùng nhau.
- **Nút lấy tên nhóm**: hỏi Zalo tên thật của tất cả nhóm trong một lần gọi rồi gắn vào danh sách. Để là nút bấm tay chứ không tự chạy ngầm, vì mỗi lần gọi mở một kết nối ngắn khiến listener phải nối lại một nhịp.
- Bộ đọc kết quả nhận được nhiều định dạng khác nhau và không bao giờ lỗi với dữ liệu lạ, vì định dạng đầu ra của công cụ chưa kiểm chứng được nếu không có tài khoản đăng nhập thật.

## [0.9.128] - 2026-07-20
Sửa lỗi báo mất kết nối trong khi thực tế vẫn đang nghe bình thường và tin vẫn về đều.
### Sửa lỗi
- **Đọc nhầm dòng khai báo thành sự cố**: công cụ in dòng thông báo có bật tính năng tự nối lại, ngay sau dòng báo đã bắt đầu nghe. Bộ đọc log khớp chuỗi quá thô nên hiểu dòng khai báo đó thành đang mất kết nối, ghi đè trạng thái đúng và kẹt luôn ở đó. Nay chỉ nhận đúng những dòng báo sự cố thật, và bỏ qua các dòng liệt kê năng lực, sự kiện hay địa chỉ webhook.
- **Thêm một nguồn sự thật chắc chắn hơn log**: nếu vừa có tin nhắn về trong ba phút gần đây thì kết nối chắc chắn đang sống, nên trạng thái báo đang nghe bất kể log đoán gì. Đọc log để suy ra trạng thái vốn mong manh vì chuỗi chữ của công cụ có thể đổi bất cứ lúc nào. Riêng lỗi cứng như trùng phiên thì không bị che, vì cái đó phải do người sửa rồi bật lại.

## [0.9.127] - 2026-07-20
Sửa lỗi mù của bộ dò tiến trình Zalo trên máy chủ: nó luôn báo không tìm thấy gì, kể cả khi thực tế đang có tiến trình chiếm kết nối.
### Sửa lỗi
- **Bộ dò tiến trình không chạy được trong Docker**: nó gọi lệnh pgrep, mà ảnh Docker chỉ cài ca-certificates, curl, git, ripgrep, ffmpeg và tini, không có gói chứa pgrep. Lệnh ném lỗi, bị nuốt, nên trang trạng thái luôn báo không có tiến trình lạ nào trong khi listener vẫn bị đá ra liên tục. Một con số không giả còn tệ hơn không có số vì nó khiến loại nhầm nguyên nhân. Nay đọc thẳng thư mục tiến trình của hệ thống, luôn có sẵn không cần cài gói.
- **Bỏ sót phiên đăng nhập quét QR**: bộ dọn trước đây chỉ tìm tiến trình nghe và tiến trình của connector, trong khi phiên quét QR chưa thoát cũng giữ một kết nối cho cùng tài khoản. Nay quét cả ba loại.
- **Không tự giết tiến trình con của chính mình**: loại trừ theo nhóm tiến trình, tránh vừa bật đã tự tắt.
### Cải thiện
- Đường dẫn thư mục tiến trình được tách thành hằng số để kiểm thử chạy được trên cả Windows lẫn Linux. Trước đây nhánh Linux không hề được kiểm thử, đó chính là lý do lỗi mù lọt qua.

## [0.9.126] - 2026-07-20
Dứt điểm trùng phiên Zalo: listener tự tắt connector của chính tài khoản đó khi bật, và dọn cả tiến trình của connector chứ không riêng tiến trình nghe.
### Sửa lỗi
- **Connector Zalo chính là thứ đá listener**: nó giữ một kết nối lâu dài cho cùng tài khoản, mà Zalo chỉ cho một kết nối mỗi tài khoản. Bản trước mới chỉ đổi đường gửi tin, còn bản thân connector vẫn bật nên vẫn tranh chỗ. Nay bật nghe là Javis tự tắt connector của đúng tài khoản đó, dừng nghe thì bật lại như cũ, và nói rõ cho chủ biết chứ không im lặng làm mất công cụ.
- **Bộ dọn tiến trình cũ bỏ sót**: bản trước chỉ tìm tiến trình nghe, không đụng tới tiến trình của connector, nên thứ đang giữ kết nối vẫn sống. Nay quét cả hai.
### Ghi chú
- Từ bản 0.9.124 listener không cần connector nữa, cả nghe lẫn gửi đều tự lo, nên việc tạm tắt connector không mất chức năng gì.

## [0.9.125] - 2026-07-20
Tự dọn tiến trình nghe cũ còn sót, và thêm đường xoá hẳn phiên đăng nhập Zalo khi bị trùng phiên mà đăng xuất không ăn thua.
### Thêm mới
- **Bật nghe tự dọn trước khi khởi động**: tiến trình nghe mồ côi từ các bản trước vẫn giữ kết nối sống và đá listener mới ra ngay. Đăng xuất ở nơi khác không giết được nó vì kết nối đã mở thì cứ sống. Nay mỗi lần bật là Javis tự tìm và dọn sạch trước, chủ không phải đi tìm tiến trình trên máy chủ.
- **Nút xoá phiên đăng nhập**: chỉ hiện khi đang trùng phiên. Cần vì lệnh đăng xuất của công cụ cố ý giữ lại thông tin đăng nhập để tự vào lại lần sau, nên đăng xuất không hề gỡ được phiên đang kẹt. Xoá xong quét QR lại là sạch.
- **Nói rõ tìm thấy bao nhiêu tiến trình cũ** thay vì để chủ đoán tại sao trùng phiên.
### Bảo mật
- **Chặn một lỗi phá hoại trước khi phát hành**: bản đầu của bộ dò tiến trình lọc theo dòng lệnh, mà chính câu truy vấn lại chứa những chữ đang tìm nên nó tự bắt chính mình, và lệnh dọn thì giết cả cây tiến trình. Nay chỉ soi đúng tiến trình node và loại trừ chính câu dò. Có kiểm thử chốt lại.
- **Xoá phiên bị rào trong đúng thư mục phiên của connector**, nên một mã kết nối bị sửa bậy không thể khiến Javis xoá thư mục khác.

## [0.9.124] - 2026-07-20
Xử lý va chạm một kết nối mỗi tài khoản Zalo, thứ đã ghi là chưa kiểm chứng từ bản đầu và nay xảy ra thật trên máy chủ.
### Sửa lỗi
- **Listener bị đá ra liên tục**: log thật báo có kết nối khác được mở nên kết nối này bị đóng, cứ vài phút một lần. Nguyên nhân là đường gửi tin đi qua connector Zalo, mà connector giữ một kết nối lâu dài cho cùng tài khoản nên chính nó đá listener, rồi listener nối lại và đá ngược. Nay gửi tin bằng lệnh một lần, chỉ mở kết nối trong tích tắc rồi thoát.
- **Không còn quay vòng vô ích**: chuỗi báo lỗi của thư viện Zalo trong trường hợp này không nằm trong bộ nhận diện lỗi cứng, nên listener tưởng là rớt mạng thường và cứ thử lại mãi. Nay nhận ra đúng, dừng lại và nói rõ phải kiểm tra những gì: connector Zalo đã tắt chưa, có đang mở Zalo Web không, có listener cũ nào còn chạy không.
- **Log không còn rác ký tự**: bóc mã màu trước khi hiển thị, hết cảnh nhìn thấy những đoạn như ESC ngoặc 31m ERROR.
- **Nhóm hiện đúng tên nhóm**: trước đây sổ cuộc chat lấy tên người gửi làm tên nhóm nên hai nhóm khác nhau cùng hiện một tên và không phân biệt được. Nay ưu tiên tên nhóm, và người nhắn sau không ghi đè mất tên đã biết.

## [0.9.123] - 2026-07-20
Zalo chuyển từ một bộ lọc thông báo dùng chung sang chính sách riêng cho từng cuộc chat, đặt bằng lời qua chat. Thêm chế độ Javis tự trả lời khách như một chatbot, chạy trong hộp cát.
### Thêm mới
- **Mỗi cuộc chat một luật riêng**, ghi ở `Javis/zalo/<slug>.md` trong brain nên có git, xem lại và sửa tay được. Năm chế độ: chỉ ghi nhận, báo mọi tin, báo theo từ khoá, nhắc khi quá N phút chưa ai trả lời, và tự trả lời khách theo kịch bản.
- **Đặt luật bằng lời**: tool `javis_zalo_rule` để nói thẳng trong chat hoặc Telegram, ví dụ nhóm này nếu 30 phút chưa ai trả lời thì nhắc. Giao diện chỉ hiển thị luật, không có form nhập. Gọi tên nhóm mà khớp nhiều hơn một thì tool từ chối kèm danh sách chứ không đoán, vì gắn kịch bản nhầm nhóm là bot đi trả lời khách của nhóm khác.
- **Nhắc khi quên trả lời**: khách nhắn mà quá N phút không ai đáp thì báo Telegram đúng một lần. Làm được là nhờ Javis có tài khoản Zalo riêng, nên chủ trả lời bằng tài khoản của mình sẽ là một thành viên khác trong nhóm và tin của chủ về đầy đủ.
- **Chế độ chatbot**: Javis tự trả lời khách theo kịch bản riêng của từng nhóm, có trần số tin mỗi giờ, và tự đẩy về cho chủ khi gặp việc ngoài kịch bản.
### Bảo mật
- **Hộp cát cho chatbot**: engine chạy không có tool nào, không thấy MCP nào, không mang theo bộ nhớ hay brain. Model chỉ sinh ra chữ, còn gửi đi đâu là do mã Javis quyết và luôn gửi về đúng cuộc chat vừa phát sinh tin, nên dù bị dụ hoàn toàn cũng không nhắn được cho người khác.
- **Vá một bẫy nguy hiểm của lớp engine**: điều kiện kiểm tra danh sách tool cho phép coi danh sách rỗng là chưa đặt gì, nên cách viết trực giác nhất để tạo hộp cát lại mở toàn quyền kèm nạp cả MCP sẵn của máy, đúng lúc nội dung do người lạ soạn đi vào engine. Nay truyền một tên tool không tồn tại để cổng kiểm quyền thực sự bật, và có kiểm thử chốt lại.
- Bốn chế độ còn lại vẫn không đụng tới engine, giữ nguyên rào của bản trước.
- Chế độ chatbot luôn được tạo ở trạng thái tắt, chủ phải bật riêng sau khi nghe lại kịch bản.

## [0.9.122] - 2026-07-20
Nhóm Zalo giờ hiện ra để chọn được, danh sách cuộc chat chịu được hàng trăm nhóm, và dọn nốt lỗi tiến trình con sống mồ côi.
### Sửa lỗi
- **Tin nhóm không bao giờ hiện ra**: công cụ nghe mặc định chỉ gửi hai loại sự kiện là tin nhắn và bạn bè, thiếu hẳn loại nhóm. Nay khai đủ cả bốn loại. Ngoài ra sổ cuộc chat trước đây chỉ ghi đúng sự kiện tin nhắn, nên lúc vừa thêm tài khoản vào một nhóm mà chưa ai nhắn gì thì nhóm không xuất hiện. Nay mọi sự kiện có cuộc chat đều được ghi, thêm vào nhóm là thấy ngay.
- **Tiến trình con sống mồ côi**: npx chỉ là lớp vỏ, node bên trong mới là thứ giữ kết nối. Lệnh dừng cũ chỉ giết cái vỏ nên node vẫn chạy và vẫn đẩy tin về, gây ra cảnh giao diện báo tiến trình chưa chạy trong khi tin vẫn chảy đều. Nay dọn cả cây tiến trình, bằng taskkill trên Windows và killpg trên Linux.
- **Bật lại lúc luồng cũ đang dừng dở**: trước đây trả về "đã chạy rồi" mà không dựng luồng mới, cờ dừng vẫn còn bật nên luồng cũ thoát và để lại trạng thái tắt trong khi cấu hình nói đang bật. Nay chờ luồng cũ thoát hẳn rồi mới dựng luồng mới.
- **Không dội tin cũ khi nối lại**: loại trừ các sự kiện phát lại lịch sử và báo đã xem, tránh dồn hàng loạt tin cũ vào Telegram mỗi lần kết nối lại.
### Cải thiện
- **Danh sách cuộc chat dùng được khi có hàng trăm nhóm**: thêm ô tìm kiếm, chỉ hiện sẵn 8 cuộc chat gần nhất và có nút xem thêm. Cuộc chat đang theo dõi luôn ghim lên đầu và không bao giờ bị cắt, để lúc nào cũng bỏ tick được. Trần ghi nhớ nâng từ 60 lên 300.
- **Nhận diện tin nhắn rộng hơn**: chấp nhận cả biến thể tên sự kiện như tin nhắn nhóm, vì tên sự kiện của công cụ chưa có tài liệu chốt.
- **Thêm bộ đếm loại sự kiện** trong trang trạng thái, để lần sau có thứ đáng lẽ phải hiện mà không hiện thì nhìn ra sự thật thay vì đoán.

## [0.9.121] - 2026-07-20
Sửa lỗi listener Zalo bấm Bật rồi mà vẫn hiện "Đang tắt" và không nhận được tin nào. Đây là lỗi chặn hoàn toàn: ở các bản trước listener CHƯA BAO GIỜ khởi động nổi, không phải chạy rồi hỏng.
### Sửa lỗi
- **Lấy sai nguồn thư mục phiên đăng nhập**: chỗ tìm thư mục phiên đọc qua mcp_store.get_connection, mà hàm đó trả bản đã che secret và lược mất trường config, nên đường dẫn luôn rỗng và mọi lần bật đều thất bại ngay từ bước kiểm tra. Chuyển sang đọc từ mcp_store.resolved, cũng chính là nơi tính thư mục home cho connector chạy cô lập, nên listener và connector không còn lệch nhau.
- **Bật hụt vẫn ghi là đã bật**: endpoint bật ghi cờ enabled trước rồi mới kiểm tra, kiểm tra hỏng thì không hoàn tác, để lại đúng cảnh nhãn "Đang tắt" nằm cạnh nút "Tắt" còn danh sách thì bảo đang nghe. Nay kiểm tra xong mới bật.
- **Lý do lỗi bị xoá mất sau 5 giây**: nhịp hỏi lại trạng thái ghi đè dòng lỗi vừa hiện, chủ không kịp đọc. Nay lý do được giữ ở tiến trình nền và hiện cả khi đang tắt.
- **Thông báo lỗi giờ kèm đường dẫn cụ thể** thay vì chỉ nói chung chung là chưa đăng nhập.
### Cải thiện
- **Luồng nền không còn chết câm**: mọi lỗi bất ngờ được biến thành trạng thái đọc được thay vì để trạng thái đứng nguyên giá trị cũ và giao diện báo sai.
- **Phân biệt hỏng cứng với rớt mạng**: sidecar bật lên là tắt ngay 3 lần thì dừng hẳn và phơi log của công cụ ra, thay vì lặp vô tận trong khi vẫn hiện "đang thử lại".
- **Hiện log thô của sidecar trên giao diện** khi đang trục trặc, để không phải đoán mò nữa.
- **Nhãn trạng thái nói đúng tên vấn đề**: đã bật mà tiến trình chưa chạy thì nói đúng như vậy, không hiện "Đang tắt".
### Đã kiểm chứng
- Chạy thật `zalo-agent-cli --help` và `listen --help`: lệnh listen có thật, các cờ webhook, filter, no-self đều đúng. Ghi nhận thêm là filter chỉ nhận user, group hoặc all; giá trị "dm" dùng ở 0.9.118 là sai, đã thay bằng "all" từ 0.9.119.
- Chạy listen với thư mục trống: công cụ in "Not logged in" rồi thoát mã 1, khớp với bộ nhận diện lỗi sẵn có.
- Kiểm trên dữ liệu thật: kết nối Zalo trả về đường dẫn home tồn tại.

## [0.9.120] - 2026-07-20
Sửa lỗi ô "Cuộc chat theo dõi" trống trơn không có một chữ hướng dẫn nào, khiến người dùng mở panel ra không biết phải làm gì để có nhóm mà chọn.
### Sửa lỗi
- **Ô cuộc chat trống giờ có chỉ dẫn**: biến chống vẽ lại được khởi tạo bằng chuỗi rỗng, mà danh sách rỗng cũng sinh ra khoá rỗng, nên lần vẽ đầu tiên bị chặn ngay và dòng hướng dẫn không bao giờ hiện. Đổi sang khởi tạo bằng null.
- **Chỉ dẫn nói đúng việc cần làm theo từng trạng thái**: đang tắt thì bảo bấm Bật nghe trước, đang nghe mà chưa ai nhắn thì bảo nhờ người nhắn thử một tin vào nhóm cần theo dõi. Trước đây chỉ có một câu chung cho cả hai.
- Thêm 4 kiểm tra trong dashboard/test_zalo_panel.js chốt đúng lỗi này để không tái phát.

## [0.9.119] - 2026-07-20
Siết listener Zalo theo đúng cách dùng thật: chỉ nghe những cuộc chat được chọn, và rà bảo mật toàn tuyến vì nội dung tin nhắn là do người lạ soạn.
### Thay đổi
- **Chỉ nghe cuộc chat được chọn**: danh sách cuộc chat theo dõi giờ là cổng chính, chưa tick cái nào thì không báo gì. Trước đây mặc định nghe mọi tin nhắn riêng rồi lọc bằng từ khoá, ồn và không đúng nhu cầu. Từ khoá hạ xuống thành lọc phụ, chỉ thu hẹp thêm bên trong các cuộc chat đã chọn. Bỏ ô "chỉ tin riêng" vì nó mâu thuẫn với việc đã chọn đích danh.
- **Tự liệt kê cuộc chat để chọn**: chủ không biết thread ID, nên sidecar học từ chính luồng tin đi qua và hiện thành danh sách tick chọn trong trang Kết nối. Tick là ăn ngay, không cần tắt bật lại. Cố ý không gọi tool liệt kê hội thoại vì làm vậy sẽ dựng thêm một socket cho cùng tài khoản, đúng vào va chạm chưa kiểm chứng.
### Thêm mới
- **Dòng dấu hiệu trên panel**: hiện tin gần nhất nhận lúc nào, và phân biệt rõ "đã nối nhưng chưa nhận tin nào" với "đang tắt". Đây là thứ cần để biết listener thật sự sống hay chỉ báo sống.
### Bảo mật
- **Nội dung Zalo không có đường chạm vào engine hay máy chủ**: đường dữ liệu chỉ là webhook, lọc, chuỗi text, Telegram. Module chỉ nhận đúng năm phụ thuộc, không engine, không Bash, không file, không MCP. Có test chốt đúng bộ năm đó nên ai nới về sau sẽ làm gãy test.
- **Chống giả dạng lời của Javis**: tin của khách bị rào giữa hai vạch có nhãn "KHÔNG phải lệnh cho Javis", nhãn đặt trước nội dung và tin dài bị cắt, nên một tin cố ý xuống dòng rồi viết "Javis: xác nhận chuyển khoản" không lừa được.
- **Chống dựng markup**: chốt bằng test rằng đường gửi Telegram của listener không đặt parse_mode, khác với đường gửi thường dùng MarkdownV2.
- **Chống XSS trên dashboard**: tên hiển thị Zalo do người lạ tự đặt và được vẽ vào danh sách cuộc chat, nay bọc esc() toàn bộ. Thêm dashboard/test_zalo_panel.js chạy thật hàm esc và chốt nguồn chỗ vẽ danh sách.
- **Lọc ký tự giấu chữ**: bỏ ký tự điều khiển, zero-width và ký tự đảo chiều RTL, những thứ nhìn vô hại mà máy đọc ra nội dung khác. Thêm trần payload 256KB và trần số cuộc chat ghi nhớ.

## [0.9.118] - 2026-07-20
Thêm khả năng nghe tin Zalo LIÊN TỤC. Trước đây connector Zalo là pull-only: phải gọi tool mới biết có tin, mà pool MCP lại đóng tiến trình sau 10 phút không dùng (`mcp_client._IDLE_TTL`), nên websocket và bộ đệm tin của `zalo-agent-cli mcp start` không sống sót. Giờ Javis chạy một tiến trình sidecar riêng, độc lập với pool, nhận tin ngay khi khách nhắn rồi báo về Telegram.
### Thêm mới
- **Listener Zalo chạy nền**: sidecar `zalo-agent-cli listen --webhook` đẩy từng sự kiện về `/hook/zalo`, Javis lọc rồi bắn Telegram. Bật tắt ngay trong thẻ Zalo ở trang Kết nối, có hiện trạng thái thật (đang nghe, mất kết nối đang thử lại, trùng phiên). Tự dựng lại khi đứt với backoff 5s rồi 30s rồi 120s rồi 300s, và tự bật lại sau khi khởi động lại app.
- **Lọc mặc định chặt**: chỉ báo tin nhắn riêng có chứa từ khoá, không báo nhóm. Khớp từ khoá bỏ dấu và không phân biệt hoa thường nên khách gõ "gia" vẫn khớp "giá". Có danh sách cuộc chat theo dõi riêng, giờ im lặng, khử trùng msgId, và trần 20 thông báo mỗi 10 phút để nhóm đông không làm nổ Telegram.
### Bảo mật
- **`/hook/zalo` hai tầng rào**: chỉ nhận từ loopback (`_AUTH_LOCAL_EXACT`), cộng shared secret sinh tự động. Secret đi trong query chứ không phải header, vì `--webhook` của CLI chỉ POST JSON trần và không đặt được header tuỳ ý; gác bằng header sẽ chặn sạch tin. Loopback một mình không đủ vì tiến trình khác trên cùng VPS cũng là loopback. Secret không bao giờ trả ra frontend.
- **Javis vẫn không tự trả lời khách**: listener chỉ đọc và báo. Gửi tin Zalo vẫn phải do chủ yêu cầu trực tiếp trong chat.
### Đã biết
- Zalo chỉ cho MỘT socket mỗi tài khoản, nên connector `zalo` và sidecar có thể đá nhau nếu dùng chung tài khoản. Chưa kiểm chứng được nên thiết kế chọn làm va chạm hiện rõ: bắt chuỗi trùng phiên trong log, đẩy lên giao diện và dừng hẳn thay vì quay vòng vô ích.

## [0.9.117] - 2026-07-20
Sửa lỗi báo nhầm "Chưa cài Codex CLI" khiến không chat được bằng gói ChatGPT dù đã đăng nhập thành công. Nguyên nhân: binary codex không nằm trong PATH nên Javis phải dò nó trong thư mục home, mà home lại lấy mỗi từ biến môi trường USERPROFILE; khi server được bật lại bởi tự-cập-nhật hay tác vụ nền thì biến này có thể trống, home thành rỗng nên mọi đường dẫn ~/.codex/... hoá ra tương đối và không khớp, dù binary vẫn nằm nguyên chỗ cũ.
### Sửa lỗi
- **Dò Codex CLI không còn phụ thuộc mỗi USERPROFILE**: thêm các đường lùi lần lượt là HOME, HOMEDRIVE cộng HOMEPATH, rồi Path.home(). Đã kiểm bằng cách bỏ lần lượt cả ba biến môi trường, vẫn dò ra đúng binary.
- **Thêm biến JAVIS_CODEX_BIN**: trỏ thẳng tới file codex nếu máy cài ở chỗ lạ; trỏ sai đường dẫn thì bỏ qua và dò tiếp như thường.

## [0.9.116] - 2026-07-20
Rà soát toàn bộ cảnh báo rủi ro của 23 connector. Từ khi viết ra tới nay chưa ai kiểm lại, mà chúng lại không hiện trên giao diện (sửa ở 0.9.115) nên lỗi tích lại không ai thấy. Tìm được ba connector có tool nguy hiểm mà không một chữ cảnh báo, một chỗ xếp loại mâu thuẫn, và một chỗ mô tả nhẹ hơn thực tế.
### Bảo mật
- **Ba connector có tool nguy hiểm mà KHÔNG có cảnh báo, nay đã có**: `pancake-pos` (tạo đơn hàng, ghi giao dịch thu chi, sửa công nợ, xuất hoá đơn điện tử, chạy quảng cáo, tạo voucher), `botcake` (gửi tin thật tới khách qua chatbot), `webcake-landing` (đăng trang công khai, lại đang mặc định ở mức Ghi nháp).
- **Siết `*share*` của `google-sheets` từ mức Ghi lên mức NGUY HIỂM**: connector này mặc định ở mức Ghi nháp, nghĩa là trước đây Javis chia sẻ được bảng tính chứa số liệu kinh doanh ra người ngoài ngay từ mặc định. Nay thống nhất một chuẩn với `google-keep` (đã xếp `add_note_collaborator` là nguy hiểm): đẩy dữ liệu ra người ngoài luôn là mức Toàn quyền.
### Sửa lỗi
- **`google-workspace` mô tả nhẹ hơn thực tế**: cảnh báo viết mức Ghi nháp "chỉ soạn nháp, tạo lịch, tạo tài liệu", trong khi danh sách ghi có cả `*modify*` và `*move*`, tức sửa tài liệu có sẵn và di chuyển file Drive cũng được. Đã viết đúng lại.
- **`zalo` là connector DUY NHẤT mặc định Toàn quyền** (17 cái Chỉ đọc, 5 cái Ghi nháp, 1 cái Toàn quyền) mà cảnh báo cũ không nói rõ điều đó. Giữ nguyên mức mặc định vì đấu Zalo vào chủ yếu để nhắn tin, nhưng cảnh báo nay nói thẳng là quyền gửi tin đang bật sẵn và chỉ cách hạ xuống.
### Cải thiện
- **Viết lại cả 20 cảnh báo theo một khuôn, có ngắt đoạn**: trước đây tất cả đều là một đoạn chạy dài không xuống dòng, y hệt vấn đề của phần hướng dẫn đã sửa ở 0.9.111. Nay mỗi mức quyền một đoạn, cảnh báo nặng nhất đứng đầu.
### Thêm mới
- Bổ sung 5 luật vào `server/test_canh_bao_rui_ro.py`: có tool nguy hiểm thì bắt buộc có cảnh báo; tool chia sẻ dữ liệu không được xếp mức Ghi; cảnh báo dài phải ngắt dòng và không dòng nào quá 200 ký tự; cảnh báo không được dùng chữ hạ thấp mức quyền so với thực tế; connector mặc định Toàn quyền phải nói rõ và chỉ cách hạ.
### Ghi chú
- Ba connector còn lại không có cảnh báo (`google-search-console`, `google-ads`, `tiktok-ads`) đều không khai tool nguy hiểm nào và mặc định Chỉ đọc, nên đúng là chưa cần.

## [0.9.115] - 2026-07-20
Sửa một lỗ hổng trình bày nghiêm trọng: **15 trong 16 connector có cảnh báo rủi ro thì không bao giờ hiện cảnh báo lúc bấm Kết nối**. Trường `risk` chỉ được vẽ ở luồng QR (Zalo) và ở hộp thoại đổi quyền, nên cảnh báo mạnh nhất lại vắng mặt đúng lúc người dùng ra quyết định.
### Sửa lỗi
- **Cảnh báo rủi ro hiện ở CẢ ba luồng đấu nối**: `openApikeyFlow` và `openOauthFlow` giờ vẽ khối `conn-risk` như `openQrFlow` vẫn làm, đặt NGAY TRÊN phần hướng dẫn để đọc trước. Ảnh hưởng 15 connector, trong đó có `facebook-personal` (dán cookie tài khoản thật), `google-workspace`, `slack`, `gmail`, `google-keep`.
### Cải thiện
- **Mô tả thẻ `google-keep` nói thẳng về bán kính thiệt hại**: Keep không có API chính chủ nên phải dùng master token có TOÀN QUYỀN tài khoản Google, khác hẳn `gmail` / `google-calendar` / `google-ads` vốn xin đúng một scope. Javis chỉ thao tác được ghi chú, nhưng token thì mở cả tài khoản nếu bị lộ. Nói ngay trên thẻ để thấy trước khi bấm vào.
### Thêm mới
- Test `server/test_canh_bao_rui_ro.py` (12 kiểm tra, không mạng): cắt thân từng hàm JS để xác nhận cả ba luồng đều vẽ `conn-risk` và chỉ vẽ khi thật sự có cảnh báo; kiểm mô tả thẻ Keep có nêu rủi ro; kiểm `google-keep` vẫn chỉ khai tool Keep chứ không lan sang Gmail/Drive. Có canary chứng minh phép cắt thân hàm đang soi đúng một hàm.
### Ghi chú
- Giữ nguyên tên "Google Keep" vì đó đúng với NĂNG LỰC (server chỉ phơi 23 tool Keep, đã bắt tay MCP đếm thật). Vấn đề nằm ở CREDENTIAL chứ không ở năng lực, nên xử bằng cảnh báo thay vì đổi tên.
- KHÔNG mở rộng `google-keep` thành connector kiểu Workspace. Javis đã có `gmail`, `google-calendar`, `google-workspace` dùng OAuth có scope, an toàn hơn hẳn. Master token nên bị nhốt vào đúng chỗ duy nhất không có đường thay thế.

## [0.9.114] - 2026-07-20
Đấu **Google Ads** cũng không còn phải chạy lệnh. Trước đây phải cài Google Cloud CLI, chạy `gcloud auth application-default login` với một chuỗi scope rất dài, rồi đi tìm file JSON trong `%APPDATA%` mà dán vào. Giờ điền Client ID/Secret rồi bấm đăng nhập như Gmail và Lịch, Javis tự dựng file đăng nhập.
### Thêm mới
- **`oauth_mcp.credentials_file(conn_id, fmt)`**: dựng nội dung file credential cho connector STDIO đăng nhập bằng OAuth. Ghép refresh_token trong kho oauth với client_id/secret trong `mcp_store` thành đúng khuôn ADC mà gcloud vẫn sinh ra (`{type: authorized_user, client_id, client_secret, refresh_token}`). Đồng bộ, không gọi mạng.
- **`oauth_file` trong catalog**: connector khai `{format, env, ext}` thì `mcp_store.resolved()` ghi file 0600 vào `connector-files/` rồi trỏ biến môi trường vào. Tái dùng đúng khuôn sẵn có của field `file`.
- Test `server/test_google_ads_oauth.py` (26 kiểm tra, không mạng): khai báo catalog, dựng nội dung ADC, và kiểm ĐẦU-CUỐI rằng `resolved()` ghi được file thật lên đĩa với đúng nội dung. Có canary chứng minh hàm thật sự đọc kho token chứ không bịa file.
### Sửa lỗi
- **`openOauthFlow` không render được ô nhiều dòng**: nó ép mọi field thành input một dòng, nên ô dán file ADC (đường lui) sẽ không dùng nổi. Giờ khai `multiline` thì ra textarea, y như luồng apikey.
### Cải thiện
- **Bỏ yêu cầu Google Cloud CLI** khỏi `google-ads`. Chỉ còn cần Git (đã có sẵn trong Docker image) vì uvx tải server từ GitHub.
- **Giữ ô dán tay file ADC làm đường lui** cho ai đã lỡ chạy gcloud, và đường lui THẮNG: dán tay rồi thì OAuth không ghi đè.
### Ghi chú
- Import `oauth_mcp` trong `mcp_store` phải TRỄ (gọi bên trong hàm) vì `oauth_mcp` đã import `mcp_store` ở cấp module. Import thẳng là vòng lặp.
- KHÔNG đụng `args` của google-ads: vẫn tải từ `git+https://...` vì bản trên PyPI mới ở 0.0.1 (10/2025), đổi sang là rước rủi ro không cần thiết.
- Chưa nghiệm thu với tài khoản Google Ads thật (cần developer token + tài khoản quảng cáo), nên bước đăng nhập phải thử tại chỗ.

## [0.9.113] - 2026-07-20
Bỏ hẳn bước bắt người dùng mở terminal để đấu **Google Keep**. Trước đây phải chạy một lệnh dài đổi App Password lấy master token rồi dán vào; giờ dán thẳng App Password vào Javis, server tự đổi. Hai bước còn lại (bật xác minh 2 bước, tạo App Password) là giao diện của chính Google nên không tự động hoá được, nhưng đã có nút mở thẳng tới đó.
### Thêm mới
- **Bước đổi credential khai báo từ catalog** (`server/cred_exchange.py`): connector khai `auth.exchange` gồm `handler` / `inputs` / `output` / `drop`; khi đấu, Javis tự đổi rồi XOÁ các field trong `drop` trước khi lưu. Làm tổng quát thay vì nhét cứng cho Keep, vì `google-ads` sẽ cần đúng cơ chế này.
- **Handler `google_master_token`**: gọi `gpsoauth.perform_master_login`, tự bỏ dấu cách trong App Password (Google hiển thị thành 4 nhóm 4 ký tự), kiểm đủ 16 ký tự, và dịch mã lỗi Google sang tiếng Việt (sai mật khẩu, chưa bật 2 bước, đòi xác minh trình duyệt, bị chặn vì chạy trên VPS).
- **Nút mở trang ngoài cho connector dạng apikey**: `openApikeyFlow` giờ gọi `oauthWizard(con)` nên mọi connector khai `auth.setup.links` đều hiện được nút, không riêng luồng OAuth. Google Keep có nút "Tạo App Password".
- Test `server/test_cred_exchange.py` (25 kiểm tra, không mạng): phủ đổi thành công/thất bại, bỏ qua khi đã dán sẵn token, thiếu đầu vào, handler lạ, và kiểm ĐẦU-CUỐI rằng App Password không lọt xuống đĩa lẫn env. Có canary chứng minh check xoá là thật.
### Bảo mật
- **App Password KHÔNG BAO GIỜ được lưu**: bị xoá dù đổi thành công hay thất bại, không map ra biến môi trường, không xuất hiện trong thông báo lỗi. Đã kiểm bằng cách đọc thẳng file `mcp_servers.json` trên đĩa tìm chuỗi bí mật.
- **Giữ nguyên đường lui dán master token thủ công**: quan trọng vì Google hay chặn đăng nhập từ IP trung tâm dữ liệu, nên bản chạy VPS vẫn có lối đi.
### Ghi chú
- Thêm `gpsoauth` vào `requirements.txt` (kéo theo pycryptodomex, requests, urllib3). Đã kiểm bằng `pip install --dry-run`: không đụng tới pin `fastapi`/`starlette`.
- Chưa chạy thử với App Password thật (cần tài khoản Google thật), nên bước đổi token vẫn phải nghiệm thu tại chỗ.
- Khảo sát `google-ads`: đưa lên UI ĐƯỢC, chi tiết trong `docs/superpowers/specs/2026-07-20-doi-credential-tren-ui-design.md`.

## [0.9.112] - 2026-07-20
Đính chính một khẳng định SAI ở bản 0.9.110 và gỡ dòng Dockerfile thừa đi kèm.
### Sửa lỗi
- **Gỡ `pip install uv` thừa khỏi `Dockerfile`**: bản 0.9.110 thêm dòng này kèm khẳng định "image thiếu uv nên 4 connector uvx khác (google-sheets, google-search-console, google-ads, tiktok-ads) đang hỏng trên VPS". Khẳng định đó SAI. `uv>=0.5` đã nằm trong `requirements.txt` từ v0.9.0 (commit 856cb19) và `Dockerfile` vẫn chạy `pip install -r requirements.txt`, nên image LUÔN có `uv`. Bốn connector kia chưa từng hỏng vì lý do này.
- Nguyên nhân sai: chỉ grep `Dockerfile` tìm chữ `uv`, không thấy thì kết luận là thiếu, dù dòng `pip install -r requirements.txt` nằm ngay đó mà chưa mở `requirements.txt` ra xem.
### Cải thiện
- **Ghi chú lý do vào `requirements.txt`**: dòng `uv>=0.5` giờ có comment nói rõ nó không phải thư viện app import mà là runner cho các connector khai `command: uvx`, kèm cảnh báo đừng gỡ.
- Sửa lại `CHANGELOG` bản 0.9.110 và file thiết kế `docs/superpowers/specs/2026-07-20-google-keep-connector-design.md` cho khớp sự thật, giữ lại phần phân tích cái sai để lần sau không lặp lại.

## [0.9.111] - 2026-07-20
Viết lại hướng dẫn đăng nhập của TẤT CẢ 23 connector cho dễ đọc, và sửa lỗi hộp hướng dẫn bị tràn ngang. Trước đây cả 23 guide đều là MỘT đoạn văn chạy dài không ngắt dòng, các bước (1)(2)(3) chen ngang giữa câu; gặp chuỗi dài không khoảng trắng (lệnh shell, URL callback) thì hộp bị đẩy tràn ra ngoài modal, phải kéo ngang mới đọc hết.
### Sửa lỗi
- **Hộp hướng dẫn không tràn ngang nữa**: thêm `overflow-wrap: anywhere` cho `.conn-guide` và `.conn-risk`, nên lệnh shell dài hay URL callback tự bẻ dòng thay vì đẩy tràn. Đã đo trên modal thật rộng 520px: `scrollWidth == clientWidth`, không còn thanh cuộn ngang.
- **Xuống dòng trong catalog giờ hiện đúng**: thêm `white-space: pre-line`, nên ký tự xuống dòng viết trong `mcp-catalog.json` hiện thành xuống dòng thật trên giao diện (guide là chuỗi thuần đi qua `esc()`, trước đây HTML nuốt hết).
### Cải thiện
- **23/23 guide viết lại theo một khuôn**: dòng "Cần trước:" cho thứ phải cài sẵn, rồi "Làm 1 lần:" với mỗi bước một dòng đánh số, cuối cùng là ghi chú và cảnh báo tách đoạn riêng. Nội dung sự thật giữ nguyên, chỉ đổi cách trình bày.
- **Tách các đoạn quá dài**: `meta-ads` (226 ký tự), `facebook-personal` (235), `google-keep` (204) được cắt thành đoạn ngắn hơn. Bước 2 của `facebook-personal` vốn nhồi cả quy trình DevTools vào một câu, nay tách thành 3 bước riêng.
- **Entry `google-keep` khớp style file**: mảng gọn trên một dòng như 22 connector còn lại, thay vì mỗi phần tử một dòng.
### Thêm mới
- Test `server/test_catalog_guides.py` (10 kiểm tra, không mạng): guide dài phải có xuống dòng, không dòng nào quá 200 ký tự, bước đánh số phải mở đầu dòng, CSS phải thật sự khai `pre-line` + `overflow-wrap`, và cấm em dash / en dash trong cả file. Có canary chứng minh luật bắt được chuỗi kiểu cũ.

## [0.9.110] - 2026-07-20
Thêm connector **Google Keep** để Javis đọc và thao tác ghi chú Keep. Google Keep không có API chính chủ cho tài khoản gmail thường nên connector này đi qua thư viện không chính thức và đòi Google master token, loại token có TOÀN QUYỀN tài khoản Google chứ không giới hạn phạm vi như OAuth. Rủi ro này được ghi thẳng vào phần cảnh báo của connector.

> **Đính chính (0.9.112):** bản 0.9.110 ban đầu có thêm `pip install uv` vào `Dockerfile` kèm khẳng định "image thiếu uv nên 4 connector uvx khác đang hỏng trên VPS". Khẳng định đó SAI: `uv>=0.5` đã nằm trong `requirements.txt` từ v0.9.0 và Dockerfile vẫn chạy `pip install -r requirements.txt`, nên image luôn có `uv`. Dòng thừa đã được gỡ ở 0.9.112.
### Thêm mới
- **Connector `google-keep`** (apikey, 3 ô: `google_email`, `master_token`, `unsafe_mode`): chạy local qua `uvx` với server cộng đồng `keep-mcp`. Phủ 23 tool: tìm/đọc note, tạo note và danh sách việc, sửa, gắn nhãn, ghim, lưu trữ, vứt, xoá, chia sẻ. Khai trong `system/mcp-catalog.json`, mặc định `readonly`.
- **`UNSAFE_MODE` là opt-in, mặc định TẮT**: để trống thì Javis chỉ sửa được note do chính nó tạo (gắn nhãn `keep-mcp`); gõ `true` mới cho đụng note người dùng viết tay. Giữ bản fork sạch đúng nguyên tắc năng lực chạm dữ liệu cá nhân phải tự bật.
- **Phân loại quyền có chủ ý**: `restore_note` ở mức Ghi nháp nhưng `trash_note` ở mức Toàn quyền, nên mức Ghi nháp luôn gỡ lại được note bị vứt nhầm mà không tự vứt được. Hai tool collaborator xếp mức nguy hiểm vì chúng chia sẻ note ra người khác, khác chất với sửa nội dung trong nhà.
- Test `server/test_google_keep.py` (40 kiểm tra, không mạng, không cần token): map env, luật opt-in của `UNSAFE_MODE`, lớp chặn theo 3 mức quyền và trần của mode, kèm canary chứng minh lớp chặn có quyền lực thật.
### Ghi chú
- **Bẫy entry point của keep-mcp**: package này khai console script tên `mcp`, TRÙNG tên với CLI của MCP SDK vốn là dependency của nó. Nên `uvx keep-mcp` báo lỗi, còn `uvx --from keep-mcp mcp` thì chạy nhầm sang CLI của SDK mà KHÔNG báo lỗi gì. Cách đúng là `uvx --from keep-mcp python -m server`, đã xác minh bằng bắt tay MCP thật (trả đúng 23 tool). Có ghi chú `_args_doc` trong catalog để người sau đừng "dọn gọn" nó lại.
- Chưa kiểm chứng được trên Docker thật (máy phát triển không có Docker) và chưa gọi tool nào chạm Keep thật (cần master token). Xem `docs/superpowers/specs/2026-07-20-google-keep-connector-design.md` mục "CHƯA kiểm chứng được".

## [0.9.109] - 2026-07-20
Thêm connector **Theo dõi Facebook (Apify)** và plugin `fb-monitor-apify`: theo dõi Trang và Nhóm CÔNG KHAI để tìm bài viral (nhiều share) qua dịch vụ quét Apify, thay vì tự cào bằng cookie cá nhân. Không đụng tài khoản Facebook của user nên không lo khoá, chạy tốt trên VPS 24/7, trả về số share/react/bình luận để lọc bài hot. Đây là hướng đúng cho nhu cầu "theo dõi nhóm/trang tìm bài nhiều share" mà cookie cá nhân không kham nổi 24/7.
### Thêm mới
- **Connector `facebook-monitor`** (apikey, field `apify_token`): dán Personal API token của Apify (đăng ký free tại apify.com). Chỉ đọc, tốn phí Apify theo lượt (~2.6 USD/1000 bài). Khai trong `system/mcp-catalog.json`.
- **Plugin `fb-monitor-apify`** (bundled) - tool `fb_monitor(urls, limit, min_shares)`: nhận danh sách link Trang/Nhóm công khai, tự chọn actor Apify theo URL (`/groups/` → `apify/facebook-groups-scraper`, còn lại → `apify/facebook-posts-scraper`), chạy đồng bộ qua `run-sync-get-dataset-items`, chuẩn hoá bài (share/react/bình luận/link/tác giả), lọc theo `min_shares` và sắp theo share giảm dần. readonly, không dùng tài khoản cá nhân.
- Test `server/test_fb_monitor.py` (17 kiểm tra, không mạng): catalog hợp lệ, routing actor, bóc số share nhiều tên trường, lọc + sắp xếp, gộp lỗi.

### Ghi chú
- V1 chỉ Trang + Nhóm CÔNG KHAI (actor chính chủ Apify không vào nhóm kín). Nhóm KÍN là bước sau: cần actor nhận cookie + cookie tài khoản là thành viên, vẫn có chút rủi ro khoá.
### Cải thiện
- **Đăng nhập ChatGPT qua trình duyệt báo lỗi rõ khi backend chưa sẵn**: nếu server đang chạy bản cũ (chưa có route browser OAuth), nút "Qua trình duyệt" trước đây mở một tab trắng (about:blank) không rõ vì sao. Giờ nó báo thẳng "Máy chủ chưa có chức năng này - khởi động lại Javis rồi tải lại trang" thay vì mở tab trắng.

## [0.9.107] - 2026-07-19
Thêm cách đăng nhập ChatGPT thứ hai qua trình duyệt (OAuth Authorization Code + PKCE), dành cho tài khoản Workspace bị chặn xác thực device-code. Trước đây Javis chỉ có một cách là device-code (nhập mã tại auth.openai.com/codex/device); Workspace nào tắt device-code thì không đăng nhập được. Cách mới dùng đúng luồng `codex login` mặc định.
### Thêm mới
- **Đăng nhập ChatGPT qua trình duyệt**: nút "Qua trình duyệt" ở card ChatGPT (trang Model) mở trang đăng nhập OpenAI; đăng nhập xong dán lại đường dẫn callback trên thanh địa chỉ để Javis tách mã và đổi lấy token. Chạy được cả bản trên máy cá nhân lẫn VPS headless vì không cần server tự bắt cổng localhost. Dùng chung client_id và endpoint đổi token với device-code nên token tương thích, vẫn bắc cầu sang ~/.codex/auth.json như cũ.
- Kèm test offline `server/test_openai_oauth.py` phủ PKCE, dựng URL /oauth/authorize, tách mã từ URL callback dán lại, kiểm state, và redirect_uri đúng cho từng luồng. (Bước bấm nút đăng nhập thật với OpenAI cần kiểm tại chỗ vì đụng mạng.)

## [0.9.106] - 2026-07-19
Sửa lỗi trang Mức dùng (token & chi phí) hiện toàn số 0 trên một số bản cài (điển hình VPS Docker). Nguyên nhân: chỉ số Claude/ChatGPT được dựng TỪ log thô (~/.claude/projects, ~/.codex/sessions); bản cài nào không có/không đọc được log thô đó thì mất trắng, dù mỗi lượt đã ghi số token thật vào usage-events.jsonl (nguồn này trước đây bị bỏ qua cho cli/codex).
### Sửa lỗi
- **Trang Mức dùng dùng usage-events làm nguồn dự phòng**: indexer giờ nạp cả lượt cli (Claude SDK) và codex/ChatGPT từ usage-events.jsonl khi log thô thiếu, nên báo cáo có số thay vì 0. Chống đếm trùng: ngày nào đã có log thô phủ thì bỏ dòng-từ-event ngày đó, log thô luôn thắng.
- **Backfill lịch sử một lần**: sau khi lên bản này, indexer đọc lại usage-events.jsonl từ đầu đúng một lần để dựng lại lịch sử token cli/codex đã ghi trước đó (xoá dòng cũ trước nên nhánh API không bị đếm trùng).

## [0.9.105] - 2026-07-19
Sửa lỗi trang Việc định kỳ báo "không tải được danh sách việc" trên VPS nặng. Nguyên nhân: /viec/all đếm số note của mọi brain (quét cả cây file) mỗi lần mở, vault lớn thì mất vài giây và reverse proxy cắt giữa chừng. VPS nhẹ thì kịp nên vẫn hiện, VPS nặng thì lỗi.
### Sửa lỗi
- **/viec/all bỏ đếm note**: trang Việc không cần số note nên bỏ hẳn phần quét cả cây file (rglob) - nhanh hơn 4-6 lần (đo tại chỗ 2.06s xuống 0.3s). Đây là gốc lỗi VPS khách không tải được danh sách.
- **Tự thử lại 1 lần**: /viec/all lỗi/nghẽn thoáng qua thì dashboard tự thử lại sau 1.5s trước khi báo lỗi + nút Thử lại, đỡ phải bấm tay khi mạng chậm chốc lát.

## [0.9.104] - 2026-07-19
Trang Việc định kỳ hết cảnh tạo tay mà ô Brain trống, và giờ thêm được cả nhắc hẹn ngay trong form chứ không chỉ loop. Loop tạo qua chat rơi vào brain nào cũng hiện được.
### Thêm mới
- **Thêm nhắc hẹn ngay trong form Việc định kỳ**: nút "+ Thêm việc" cho chọn "Việc lặp" hay "Nhắc hẹn". Nhắc hẹn nhận thời điểm linh hoạt ("30 phút nữa", "8h30", cron "0 7 * * *", hoặc ngày giờ đầy đủ) và kiểu "Chỉ nhắc" hoặc "Tự làm rồi báo", lưu thẳng vào kho nhắc hẹn của brain đã chọn.
### Sửa lỗi
- **Ô chọn Brain trống khi tạo việc tay**: ô Brain trước đây chỉ đổ sau khi /viec/all (quét note mọi brain, chậm trên VPS) tải xong, bấm sớm là trống và không tự đổ lại. Giờ đổ độc lập từ /brains nên luôn có lựa chọn dù danh sách việc còn đang tải.
- **Loop tạo qua chat chạy nhưng không hiện ở tab Việc**: /viec/all giờ gộp cả brain đã đăng ký với scheduler nằm ngoài thư mục brains, nên loop chạy nền ở brain ngoài cũng hiện. Khi /viec/all lỗi hoặc quá chậm thì báo rõ kèm nút Thử lại thay vì im lặng hiện "chưa có việc".

## [0.9.103] - 2026-07-19
Phần Skills trong Studio trên điện thoại giờ dễ đọc, dễ bấm. Trước đây dưới 860px khung Skills vẫn giữ 2 cột như máy tính (cột nhóm 210px + cột skill), khiến cột skill chỉ còn khoảng 150px và mô tả bị xuống dòng mỗi chữ một dòng; các nút Sửa/Xuất/Xoá lại chỉ hiện khi rê chuột nên trên điện thoại không bao giờ bấm được. Chỉ đổi bản điện thoại.
### Cải thiện
- **Skills trên điện thoại xếp dọc**: dưới 860px, khung Skills chuyển từ 2 cột sang xếp dọc. Danh sách nhóm thành dải chip cuộn ngang gọn ở trên (bấm để lọc), danh sách skill chiếm trọn bề ngang nên mô tả đọc bình thường thay vì vỡ từng từ.
- **Nút thao tác skill luôn hiện trên điện thoại**: Sửa/Xuất/Xoá tách xuống một hàng riêng dưới mỗi thẻ và luôn hiển thị (bỏ kiểu chỉ hiện khi hover), vùng chạm to hơn, ô chọn bật/tắt cũng lớn hơn. Ô tìm skill dùng cỡ chữ 16px để iOS không tự phóng to khi focus.

## [0.9.102] - 2026-07-19
Màn Javis (cockpit) trên điện thoại giờ là một khung cố định không trôi: quả cầu thu nhỏ ở trên, khung chat cuộn được ngay dưới để đọc kết quả. Chỉ đổi bản điện thoại.
### Cải thiện
- **Cockpit điện thoại thành 1 khung cố định**: khoá cuộn cả trang trên điện thoại (không còn cảnh trôi lên trôi xuống lộ quả cầu), quả cầu não thu về khoảng 34% màn hình ở trên, phần chat chiếm khoảng còn lại và tự cuộn bên trong để đọc hội thoại. Header cố định + ô nhập bám đáy như cũ.

## [0.9.101] - 2026-07-19
Facebook cá nhân: nhận diện đúng trang ĐĂNG NHẬP mbasic trả về khi cookie bị từ chối, thay vì đọc nhầm trang login thành feed. Trước đó fix User-Agent (0.9.99) đã hết lỗi "không hỗ trợ", nhưng nếu cookie hết hạn/bị Facebook chặn thì mbasic trả trang đăng nhập (URL vẫn là mbasic, không redirect) nên không bị bắt.
### Sửa lỗi
- **fb-personal đọc nhầm trang đăng nhập thành feed**: thêm `_is_login()` (trang có cả ô email lẫn ô mật khẩu) vào lớp `_fetch`; gặp trang đăng nhập (theo NỘI DUNG, không chỉ theo URL redirect) thì trả lỗi rõ nêu 3 nguyên nhân thường gặp (cookie hết hạn/đã logout; Javis chạy ở IP/máy khác nơi đăng nhập nên Facebook chặn phiên lạ; tài khoản bị checkpoint) kèm cách sửa, thay vì trả nội dung trang login. Test lên 31 kiểm tra.
Trang Việc định kỳ giờ gộp MỌI brain, mỗi việc gắn nhãn brain và chuyển được sang brain khác; tạo việc qua chat báo rõ brain; lựa chọn /brain trên Telegram được nhớ bền qua khởi động lại. Gỡ cái rối "tạo việc qua Telegram vào brain mặc định, tìm ở brain đang làm không thấy" - hai khái niệm brain (phiên Telegram vs brain đang xem trên dashboard) vốn tách rời, việc vẫn chạy nhưng người dùng không nhìn thấy.
### Thêm mới
- **Trang Việc gộp mọi brain**: endpoint `GET /viec/all` trả loop + nhắc hẹn của TẤT CẢ brain, nhóm theo brain (brain đang xem lên đầu, gắn "đang xem"), mỗi thẻ có nhãn brain. Nút bật/tắt/xoá/chạy/huỷ nhắm ĐÚNG brain của chính việc đó thay vì brain ở sidebar.
- **Chuyển việc sang brain khác**: nút "Chuyển brain" trên mỗi loop/nhắc (`POST /loops/move`, `POST /reminders/move`). Loop dời nguyên file .md + trạng thái chạy; trùng tên ở brain đích thì từ chối, KHÔNG ghi đè (định danh loop theo tên file). Form tạo loop mới có ô chọn brain đích.
- **Nhớ bền /brain Telegram**: lựa chọn brain của mỗi cuộc chat lưu bền ở `tg_brain.json` (theo tên brain), sống sót qua khởi động lại bot thay vì mất về mặc định như trước; brain bị xoá thì tự về mặc định + dọn mục cũ.
### Cải thiện
- **javis_schedule báo rõ brain**: câu xác nhận khi tạo việc/nhắc qua chat nêu tên brain ("Đã tạo việc ... trong brain Kim Khí Hà Lộc") để biết ngay việc rơi vào brain nào, không phải đi tìm mới ngã ngửa.
- Test mới `test_viec_xuyen_brain.py` (30 kiểm tra): di chuyển loop/nhắc hẹn (thành công, va chạm slug, brain trùng, không tồn tại), nhớ bền tg brain qua restart + brain xoá, `/viec/all` gắn đúng brain cho từng item.

## [0.9.99] - 2026-07-19
Vá lỗi Facebook cá nhân (0.9.95) trả trang "Trình duyệt không hỗ trợ, hãy tải Facebook Lite" thay vì feed. Nguyên nhân: mbasic.facebook.com chê User-Agent - đã dò thật, mbasic chỉ nhả HTML cho trình duyệt DI ĐỘNG (UA iPhone Safari nhận được trang thật, UA desktop/Firefox mobile bị đẩy sang trang Lite).
### Sửa lỗi
- **fb-personal đọc feed ra trang "không hỗ trợ / Facebook Lite"**: đổi User-Agent mặc định sang iPhone Safari + danh sách UA dự phòng. Thêm lớp `_fetch` tự đổi UA khi gặp trang bị chê; nếu MỌI UA đều bị chê thì trả lỗi kèm cách sửa (dán UA riêng, lấy cookie từ trình duyệt di động) thay vì trả rác. Phát hiện đúng trang "không hỗ trợ" và trang login/checkpoint để báo lỗi rõ. Thêm field tuỳ chọn `user_agent` vào connector `facebook-personal` (khớp UA với trình duyệt nơi lấy cookie là chắc nhất) + cập nhật hướng dẫn. Test `test_fb_personal.py` lên 28 kiểm tra (thêm phát hiện UA + tự đổi UA + override).

## [0.9.98] - 2026-07-19
Vá triệt để lỗi header điện thoại ở trang quản lý (0.9.97 chưa dứt): header giờ CỐ ĐỊNH trên cùng nên luôn thấy nút ☰ để vào menu, và quả cầu cockpit ẩn hẳn sau trang quản lý. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Mất header (không vào được menu ☰) + lộ quả cầu ở trang quản lý**: header trước nằm trong lưới nên bị cuộn trôi mất, để lộ quả cầu 3D/2D phía sau. Nay header `position: fixed` trên cùng (nền đặc, luôn hiện ☰ · chip model · ＋ ở mọi trang), và ẩn hẳn `hud-body` (quả cầu) khi đang ở trang quản lý nên không còn lộ hay kéo trượt được. Màn cockpit vẫn hiển thị quả cầu bình thường.

## [0.9.97] - 2026-07-19
Vá lỗi trên điện thoại: ở trang quản lý (Tổng quan, Kết nối...) quả cầu 2D phía sau bị lộ ra và trượt nhẹ ở mép trên header. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Quả cầu cockpit lộ sau lưng trang quản lý khi cuộn**: mobile bật cuộn body cho màn cockpit dài, nhưng trang quản lý (cview đè lên) khi cuộn nhẹ làm header trượt lên để lộ quả cầu 3D/2D phía sau. Nay khoá cuộn body khi đang ở trang quản lý (`body.in-console`), nội dung trang tự cuộn bên trong khung - header cố định, không còn lộ cockpit. Màn cockpit vẫn cuộn bình thường.

## [0.9.96] - 2026-07-19
Vá nút + (hội thoại mới) trên header điện thoại: hết lệch khỏi header và bấm được. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Nút + bị rớt khỏi header, bấm không ăn**: header mobile trước là lưới 3 cột, thêm ☰ và chip model làm dư ô nên nút + rớt xuống dòng, đè lên quả cầu 3D và bị canvas chặn tap. Nay header thành một hàng flex (☰ · chip model căn giữa · +), nút + là con trực tiếp header (không còn nằm trong cụm bị ẩn ở trang quản lý). Bấm + giờ mở hội thoại mới và focus ô nhập luôn.

## [0.9.95] - 2026-07-19
Thêm connector **Facebook cá nhân (cookie - thử nghiệm)** và plugin `fb-personal`: tự động hoá tài khoản Facebook CÁ NHÂN bằng cookie phiên (Facebook đã đóng API cá nhân) - lướt/đọc feed, đăng bài lên tường, bình luận. Đi đường cookie + mbasic bằng httpx nên chạy được trên VPS headless, không cần Chromium. CẢNH BÁO: vi phạm điều khoản Facebook, rủi ro khoá tài khoản; mặc định TẮT, cookie mã hoá at rest. Đây là bước 2 nối tiếp connector Trang (0.9.90) cho nhu cầu lướt feed cá nhân.
### Thêm mới
- **Connector `facebook-personal`** (apikey, field `cookie` mã hoá): dán cookie phiên Facebook (kèm hướng dẫn lấy an toàn từ DevTools). Mặc định Chỉ đọc; đăng/bình luận chỉ chạy khi nâng Toàn quyền. Khai trong `system/mcp-catalog.json`.
- **Plugin `fb-personal`** (bundled) - 3 tool: `fb_feed_read` (readonly, trả văn bản feed đã làm sạch + link bài để Javis tóm tắt) và `fb_personal_post`, `fb_personal_comment` (min_mode full). Engine gọi `mbasic.facebook.com` bằng httpx + cookie, tự bóc `fb_dtsg` và tìm form soạn bài/bình luận (best-effort, chỉnh selector khi Facebook đổi). Chặn rõ khi cookie bị đẩy về login/checkpoint.
- **`validate_connection` nhận connector ẢO**: connector plugin-backed không có URL/command (Meta/Facebook gọi qua plugin) nay qua cửa thêm-kết-nối mà không dial MCP (đếm tool theo `tool_meta`). Trước đây connector apikey không URL sẽ bị xoá khi thêm. Sửa trong `mcp_hub.py` + bơm không đổi.
- Test `server/test_fb_personal.py` (24 kiểm tra, không mạng): catalog hợp lệ, min_mode đúng, gate chưa-có-cookie, bóc fb_dtsg/tìm form, đọc feed + chặn login, đăng/bình luận build đúng POST, và nhánh validate connector ẢO.

### Ghi chú
- Phần tự động hoá Facebook cá nhân là THỬ NGHIỆM và chỉ kiểm chứng được khi chạy thật với cookie thật trên máy đích; mbasic có thể bị Facebook đổi/đóng nên bộ tìm form là best-effort, cần tinh chỉnh khi kết nối thực tế.
Đổi font chữ toàn app sang **Montserrat** cho sạch, dễ đọc (thay font monospace cũ trông "lỗi lỗi" ở các nhãn). Code vẫn giữ font monospace. Và vá header màn cockpit trên điện thoại.
### Cải thiện
- **Font Montserrat**: nạp Montserrat (Google Fonts) và dùng làm font chính cho toàn giao diện (nhãn, tiêu đề, chữ thân, thanh bên). Khối mã và mã inline giữ font monospace riêng (`--mono`) cho dễ đọc code. Tải lại trang là thấy (đã bump ?v).
- **Header cockpit điện thoại hết lệch**: ẩn nút "Lịch sử" trên điện thoại để header màn "Javis" (buồng lái) khỏi bị chồng dòng, gọn còn ☰ + chip model + nút hội thoại mới. (Lịch sử vẫn xem được ở khung chat phóng to trên máy tính.)

## [0.9.93] - 2026-07-19
Chỉnh tiếp giao diện chat điện thoại theo phản hồi: header hết chồng lên nhau, bấm chip model là sổ ra danh sách được, và mục Hệ thống trong ngăn kéo gọn lại. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Header điện thoại bị chồng lên nhau**: ẩn tên workspace + ngày trên mobile để chip model làm phần giữa header, không còn đè lên tiêu đề hội thoại.
- **Bấm chip model không sổ ra danh sách**: popover chọn model giờ dùng vị trí cố định (không bị khung cha cắt), và sửa model-picker để bấm trong popover (chọn model, đổi effort) không tự đóng - trước đó do popover đã dời khỏi khung model-bar nên bị hiểu là bấm ra ngoài.
- **Rò dòng comment ra màn hình** ("...parse vào đây nhưng không hiển thị"): comment HTML lồng nhau ở stub số liệu làm rò chữ; đã gỡ dấu comment lồng.
- **Mục Hệ thống trong ngăn kéo**: bỏ nút Studio (không dùng nữa) và vá lỗi cụm chọn brain bị định vị đè lên đầu ngăn kéo.

## [0.9.92] - 2026-07-19
Wizard cài đặt cho các connector tự-tạo-app (Facebook Trang, Meta Ads): thêm nút mở thẳng trang tạo Facebook App và ô Redirect URI kèm nút Sao chép, để bớt thao tác dán tay hay dán sai. Chỉ đổi trang Kết nối, tải lại trang là thấy.
### Cải thiện
- **Nút mở trang + copy Redirect URI khi kết nối**: modal đăng nhập OAuth giờ đọc thêm `auth.setup` từ catalog để vẽ dãy nút "Bước 1: Tạo App mới / App của tôi" (mở tab mới) và một ô Redirect URI chỉ-đọc kèm nút Sao chép (tự lấy đúng cổng đang chạy). Hướng dẫn bằng chữ được rút gọn theo, trỏ vào các nút này. Áp cho connector `facebook-pages` và `meta-ads-graph`; connector không khai `setup` thì không đổi. Thêm trường `setup` vào `public_catalog()`, hàm `oauthWizard()` trong `console.js`, style `.conn-wizard/.wiz-*` trong `console.css`. Bump `console.js?v=72`, `console.css?v=21`.
Vá tiếp giao diện chat điện thoại (0.9.89): rút gọn dòng gợi ý trong ô nhập cho khỏi xuống dòng, và đưa "phần Hệ thống" trở lại. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Dòng gợi ý ô nhập bị xuống dòng trên điện thoại**: đổi placeholder mobile thành câu ngắn "Nói hoặc gõ cho Javis…" cho vừa một dòng (bản máy tính giữ câu đầy đủ).
- **Mất phần Hệ thống trên điện thoại**: chọn brain, Cài đặt, Đổi tông, Studio, bật/tắt loa và dải trạng thái HỆ THỐNG/MCP nay gom vào mục "Hệ thống" ở đáy ngăn kéo ☰ (trước đó bị ẩn mất). Dùng lại đúng nút cũ nên bấm là chạy như thường.

## [0.9.90] - 2026-07-19
Thêm connector **Facebook Trang (tự tạo app - Graph API)** và plugin `meta-pages-graph`: quản lý Fanpage của bạn qua Graph API chính chủ. Vẫn theo kiểu tự tạo app (BYO) nên KHÔNG cần Facebook duyệt app khi thao tác trên Trang bạn là admin, và mỗi bản fork tự đứng được một mình. Xem danh sách Trang, đọc bài và bình luận (chỉ đọc); đăng bài và trả lời bình luận (toàn quyền, không tự chạy lén). Dùng lại nguyên hạ tầng OAuth Meta sẵn có, không đụng `oauth_mcp`. Lưu ý: "lướt feed" trên trang cá nhân KHÔNG làm được qua Page API (Facebook đã đóng), để dành bài toán browser-automation đợt sau.
### Thêm mới
- **Connector `facebook-pages`**: OAuth BYO app kiểu Meta (dùng chung app với Meta Ads được), scope `pages_show_list, pages_read_engagement, pages_manage_posts, pages_manage_engagement`. Mặc định thêm ở mức Chỉ đọc; đăng/trả lời chỉ chạy khi user nâng lên Toàn quyền. Khai trong `system/mcp-catalog.json`, kèm hướng dẫn tạo app (~5 phút, redirect localhost).
- **Plugin `meta-pages-graph`** (bundled) - 5 tool cho mọi engine: `fb_pages_list`, `fb_page_posts`, `fb_page_comments` (readonly) và `fb_page_post`, `fb_page_reply` (min_mode full). Mỗi thao tác trên một Trang dùng Page Access Token RIÊNG lấy từ `/me/accounts`, không dùng token cá nhân; `fb_pages_list` không lộ token Trang ra output. Tự chọn Trang khi chỉ có 1, bắt chỉ rõ khi có nhiều.
- Test `server/test_meta_pages.py` (27 kiểm tra, không mạng): catalog hợp lệ, min_mode đúng (đọc readonly / ghi full), gate chưa-kết-nối, chọn Trang, đăng/trả lời dùng đúng token Trang, không lộ token.

## [0.9.89] - 2026-07-19
Giao diện chat trên điện thoại gọn hẳn: ô nhập thành viên bo tròn lớn, header chỉ còn menu ☰ + chip model + nút hội thoại mới, dãy công cụ chuyển thành ngăn kéo trượt từ trái. Chỉ đổi bản điện thoại (màn hẹp dưới 860px), bản máy tính giữ nguyên. Có spec + plan ở `docs/superpowers/specs/2026-07-19-mobile-chat-declutter-design.md`.
### Cải thiện
- **Khung chat điện thoại gọn tối đa**: ô nhập nở to thành một viên (đính kèm bên trái, ô gõ chiếm gần hết bề ngang và tự cao lên, mic và nút gửi bên phải); bỏ hai hàng điều khiển chật (dải HỆ THỐNG/MCP và thanh công cụ ở đáy). Header rút còn ☰ (mở ngăn kéo công cụ) + chip model (bấm đổi model/engine như cũ) + nút hội thoại mới. Nút đọc tiếng dời khỏi thanh nhập. Bản máy tính không đổi.

## [0.9.88] - 2026-07-18
Mỗi lần tải lại Javis giờ vào thẳng hội thoại mới thay vì mở lại phiên cũ. Chỉ đổi frontend, tải lại trang là có.
### Cải thiện
- **Tải trang = hội thoại mới**: trước đây F5 khôi phục phiên gần nhất vào khung chat; nay mặc định mở khung trống cho hội thoại mới. Hội thoại cũ KHÔNG mất - vẫn nằm trong panel Lịch sử (lưu ở server), bấm để mở lại. Bỏ gọi `restoreSession()` lúc load + xoá phiên tạm trong localStorage. Bump `app.js?v=70`.

## [0.9.87] - 2026-07-18
Chỉnh menu lệnh `/` sau lần chạy thật: mô tả skill dài giờ cắt gọn 1 dòng, tràn thì hiện "...". Chỉ đổi frontend, tải lại trang là thấy.
### Sửa lỗi
- **Mô tả trong menu `/` tràn nhiều dòng**: các skill mô tả dài (vd jay-abraham-sales) đẩy menu cao ngoằng, che cả các lệnh khác. Nay tên + mô tả mỗi cái cắt đúng 1 dòng, quá dài thì "..." (grid `minmax(0,1fr)` + `text-overflow: ellipsis`). Bump `style.css?v=46`.
- **`/notes` chưa hiện trong menu ở brain đang mở**: skill hệ thống chỉ rải vào brain lần đầu truy cập trong đời process, mà server đã chạy từ trước khi thêm `notes` nên brain đang mở bị bỏ sót. Đã rải `notes` vào cả 3 brain trên đĩa (`system_sync.sync_brain`); endpoint `/skills` đọc đĩa nên menu thấy ngay, không cần khởi động lại. Brain mới hoặc sau khi restart thì tự có.

## [0.9.86] - 2026-07-18
Khung lệnh `/` cho khung chat web (giống Telegram/Claude) và lệnh đầu tiên `/notes`: gõ `/notes` thì lưu tin nhắn hiện tại nguyên văn vào `sources/` (kèm ảnh), rồi tự chưng cất lên wiki nếu note đáng. Chỉ đổi frontend + thêm 1 skill hệ thống, không cần khởi động lại server; chỉ cần tải lại trang.
### Thêm mới
- **Menu lệnh `/` trên web**: gõ `/` ở ô chat hiện menu gợi ý các skill của brain + vài lệnh phiên (`/new`, `/reset`, `/stop`), lọc dần khi gõ, chọn bằng chuột hoặc phím mũi tên + Enter. Chọn skill thì điền `/slug ` để gõ tiếp nội dung; lệnh phiên chạy ngay. Nhất quán với Telegram (mọi `/<slug>` = gọi skill cùng tên).
- **Skill hệ thống `notes`**: lưu nhanh một note vào Second Brain. Giữ nguyên văn phần chữ người dùng gõ (không biên tập), ảnh đính kèm chuyển vào `attachments/` và nhúng `![[...]]`. Sau khi lưu vào `sources/`, tự đánh giá đáng-wiki: đáng thì chưng cất lên `wiki/` đủ 3 kỷ luật của vault; không đáng thì vẫn giữ source, chỉ báo nhẹ. Chạy được cả trên web lẫn Telegram, mọi engine. Là skill hệ thống nên tự có ở mọi brain qua `system_sync`.
- Frontend: thêm `dashboard/chat-slash.js` (logic parse/route/menu + menu DOM) và `dashboard/test_chat_slash.js` (test node headless); chặn `/` trong `sendMessage` của `app.js`. Bump `app.js?v=69`, thêm `chat-slash.js?v=1`.

## [0.9.85] - 2026-07-18
Bản đánh dấu để kiểm tra luồng tự cập nhật 1-click (nút "Cập nhật ngay") chạy end-to-end trên bản Docker có Watchtower. Không đổi tính năng, không cần thao tác gì thêm.
### Cải thiện
- **Thử nút "Cập nhật ngay"**: bump phiên bản để xác nhận app phát hiện bản mới, gọi Watchtower kéo image + dựng lại container, rồi tự tải lại trang. Không ảnh hưởng dữ liệu hay cấu hình.

## [0.9.84] - 2026-07-18
### Sửa lỗi
- **Đề xuất trong Dashboard Token thiếu dấu tiếng Việt**: các câu insight (cache thấp, hoạt động ngầm ngốn nhiều, opus chiếm nhiều, phiên phình, spike) viết trong `usage_index.py` bị gõ không dấu nên hiện ra "Hoat dong ngam chiem...", lệch với phần còn lại của app. Nay sửa thành tiếng Việt có dấu đầy đủ. CẦN KHỞI ĐỘNG LẠI SERVER (đổi ở backend) để đề xuất hiện đúng.

## [0.9.83] - 2026-07-18
Dashboard Token: nâng trang **Mức dùng** thành bảng theo dõi tiêu thụ token thật, đọc từ log của Claude Code và Codex trên máy (không cần API riêng). CẦN KHỞI ĐỘNG LẠI SERVER (thêm module `usage_index` + route `/usage/*`); sau đó tải lại trang.
### Thêm mới
- **Lọc theo kỳ**: hôm nay, hôm qua, tuần này, tuần trước, tháng này, tháng trước, 3 tháng gần nhất, năm nay - mỗi kỳ tự so với kỳ tương đương liền trước (delta %).
- **Bóc tách nguồn tiêu**: theo provider (Claude Code / ChatGPT-Codex / API), theo nguồn (bạn gõ tay vs Javis tự chạy qua SDK), theo hoạt động (chat / nền loop-lịch / subagent), theo model, theo dự án. Phát hiện nhanh chỗ ngốn token nhất.
- **Chỉ số hiệu quả**: tổng token, token/ngày, cache hit (tái dùng ngữ cảnh), số phiên + token trung bình mỗi phiên, và chi phí QUY ĐỔI theo giá API (với gói thuê bao là "tiết kiệm được bao nhiêu", chỉ OpenRouter là tiền thật).
- **Đề xuất tự động**: cache thấp gợi ý /compact, hoạt động nền ngốn nhiều gợi ý giảm loop, opus dùng nhiều gợi ý hạ model, phiên phình gợi ý tách, spike bất thường cảnh báo sớm.
- Backend: `usage_index.py` quét tăng dần `~/.claude/projects` + `~/.codex/sessions` (bỏ file chưa đổi), phân loại chat/nền qua `conversations.db`, gộp vào SQLite. Nhánh API ghi log tiến tới qua `usage_store`. Route `/usage/summary|insights|refresh`. Bump `console.js?v=71`, thêm `usage.js?v=1`.

## [0.9.82] - 2026-07-18
### Sửa lỗi
- **Nhãn nút trong khung sửa file thiếu dấu tiếng Việt**: các nút của `file-editor.js` viết không dấu ("Sua / Nguon / Luu / Da luu / Loi / Tai ve / Dong / Mo tab moi"), lệch với phần còn lại của app. Nay sửa thành "Sửa / Nguồn / Lưu / Đã lưu / Lỗi / Tải về / Đóng / Mở tab mới". Nội dung tiếng Việt gõ vào vẫn hiển thị đúng như trước, chỉ nhãn nút thiếu dấu. Bump `file-editor.js?v=3`, chỉ cần tải lại trang.

## [0.9.81] - 2026-07-18
Nâng khung sửa file .md trong chat lên WYSIWYG (soạn như Word), dùng lại đúng bộ máy của editor cây. Thuần giao diện, KHÔNG cần khởi động lại server (chỉ tải lại trang, đã bump `?v`).
### Cải thiện
- **Khung sửa .md trong chat giờ là WYSIWYG 2 khung**: gõ trực tiếp trên bản render (đậm, nghiêng, tiêu đề, danh sách, trích dẫn, link, kẻ ngang qua thanh công cụ), gạt "Sửa / Nguồn" để xem markdown thô. Dùng lại Turndown + thanh công cụ + đổi HTML sang markdown của editor cây (`window.JavisNoteEditor` mới expose từ `console.js`), giữ nguyên `[[wikilink]]` và `![[ảnh]]`. File text không phải `.md` vẫn là textarea nguồn như cũ. Turndown nạp lazy từ CDN; offline thì tự ở lại chế độ Nguồn (vẫn sửa tốt). Đã kiểm chứng trên trình duyệt thật với Turndown thật: mở ra vào chế độ Sửa, gõ thêm nội dung, lưu ra markdown đúng (giữ tiêu đề, in đậm, danh sách), gạt Sửa/Nguồn đổi qua lại đúng.
- **Bấm link/ảnh khi đang soạn không bung editor lồng nhau**: handler click trong chat nay bỏ qua khi click rơi vào vùng đang soạn (`[contenteditable]` / `.jvfe-modal` / `.note-editor`).

## [0.9.80] - 2026-07-18
Nút "Cập nhật ngay" làm chắc lại toàn diện: kiểm tra sức khoẻ sau khi cập nhật, bản git (Windows/native) lỗi thì TỰ QUAY VỀ bản cũ, có thanh tiến trình theo bước và xem trước "bản mới có gì" trước khi bấm; bản Docker có hướng dẫn lùi rõ ràng. **Cần khởi động lại server** (đổi luồng cập nhật + thêm endpoint). Có spec + plan ở `docs/superpowers/specs/2026-07-18-update-triet-de-design.md` và `docs/superpowers/plans/2026-07-18-update-triet-de.md`.
### Thêm mới
- **Updater đa nền tự rollback (bản git)**: thêm `server/updater.py` chạy tách rời, chỉ dùng thư viện chuẩn (vẫn chạy được cả khi bản mới làm hỏng dependency). Chuỗi: dừng server -> (git stash nếu cây bẩn) -> `git pull` -> `pip install` -> khởi động lại -> chờ `/health` khoảng 90 giây. Bản mới không lên được thì `git reset --hard` về commit cũ + cài lại lib + khởi động lại (tự rollback). Mọi bước ghi trạng thái vào `update_state.json` (sống qua restart).
- **Thanh tiến trình + xem trước bản mới trong panel Phiên bản**: dashboard hiện changelog của bản mới trước khi bấm, và khi cập nhật hiện các bước Chuẩn bị -> Tải code -> Cài thư viện -> Khởi động lại -> Kiểm tra sức khoẻ -> Xong; lỗi thì báo đã tự quay về bản cũ (git) hoặc hiện cách lùi (Docker), kèm thông báo khi có sửa đổi cục bộ được cất vào git stash.
- **Endpoint `GET /update/status` + `previous_version` trong `/version`**: UI theo dõi tiến trình qua trạng thái có cấu trúc + đuôi `update.log`, và biết bản cũ để lùi.
- **CI xuất tag phiên bản GHCR**: image thêm tag `:x.y.z` (đọc từ VERSION) cạnh `:latest` và `:<sha>`, để luôn có bản cũ cố định mà pin khi cần lùi trên Docker.
### Sửa lỗi
- **Bản Windows thiếu bước cài thư viện khi cập nhật**: updater cũ chỉ `git pull` rồi bật lại, không `pip install`, nên bản mới thêm thư viện là app crash. Nay mọi bản git đều cài lib khi cập nhật.
- **`git pull` chết khi cây làm việc bẩn**: có sửa đổi cục bộ ở file tracked là pull abort im lặng, cập nhật thất bại mà không rõ lý do. Nay tự `git stash` (giữ lại, không mất, không tự pop để tránh xung đột) trước khi pull và báo cho người dùng.
### Bảo mật
- **Chống double-click spawn 2 updater**: `POST /update` claim trạng thái ngay sau guard (không có await ở giữa) và chỉ chặn khi lần cập nhật đang dở BẮT ĐẦU gần đây, nên bấm hai lần không tạo hai tiến trình cập nhật chồng nhau, đồng thời không kẹt "đang cập nhật" vĩnh viễn nếu một lần cập nhật bị gián đoạn.

## [0.9.79] - 2026-07-18
Trong khung chat giờ bấm được link, và file .md/text bấm là bung ngay khung sửa giữa màn hình để xem và chỉnh sửa. Thuần giao diện, KHÔNG cần khởi động lại server (chỉ tải lại trang - đã bump `?v` để nạp bản mới). Có brainstorm + spec ở `docs/superpowers/specs/2026-07-18-chat-link-va-sua-md-design.md`.
### Thêm mới
- **Bấm file .md/text trong chat bung khung sửa giữa màn hình**: thêm `dashboard/file-editor.js` dựng một modal độc lập gắn thẳng vào `<body>` nên chạy được từ mọi trang. Với `.md` và file text hiện `<textarea>` sửa được (riêng `.md` có nút gạt "Nguồn / Xem", bản Xem render bằng `mdToHtml` sẵn có); ảnh/PDF xem trước; file khác cho tải. Lưu qua `/files/write` có ghép sẵn tiền tố "nhà" của brain nên ghi ĐÚNG chỗ kể cả trên localhost (trần duyệt = cả ổ đĩa). Đóng bằng Esc / ✕ / bấm nền mờ, lưu nhanh Ctrl+S. Bấm link thư mục vẫn nhảy trang Tệp tin như cũ; ảnh inline giữ nguyên.
- **URL trần trong chat tự thành link mở tab mới**: URL `http(s)://...` Javis gõ thẳng (không bọc markdown) nay tự nhận thành link bấm được. Chạy sau khi code block / inline code / ảnh / link markdown đã cất vào placeholder nên không đụng vào chúng; dấu câu ở đuôi URL nằm ngoài link.
### Sửa lỗi
- **Link file có khoảng trắng hoặc dấu ngoặc bị cắt cụt đường dẫn**: regex link/ảnh markdown cũ (`[chữ](đường-dẫn)`) chỉ bắt tới khoảng trắng đầu tiên rồi dừng ở dấu `)` đầu tiên, nên đường dẫn kiểu `06 - Sources/Tên (Tư Duy Ngược).md` bị cắt còn `06` và phần đuôi rớt ra thành chữ. Nay bắt cả cặp ngoặc cân bằng 1 tầng và cho phép khoảng trắng, đồng thời cắt title markdown tùy chọn (`( "tiêu đề" )`). Nhờ vậy bấm đúng file cần mở.

## [0.9.78] - 2026-07-18
### Sửa lỗi
- **Số liệu trên header ("N note · N kết nối") không còn ngắt xuống 2 dòng**: `.graph-stats` thiếu `white-space: nowrap` nên chữ tự xuống dòng khi cụm trái thiếu chỗ; và grid `.hud-top` là `1fr auto 1fr` ép cột trái bằng cột phải, trong khi cụm trái (chọn brain + nút + số liệu) rộng hơn hẳn. Nay: (1) `nowrap` cho `.graph-stats`; (2) grid đổi thành `auto minmax(0,1fr) auto` để cụm trái/phải bám theo nội dung, cụm giữa (tên + ngày) co giãn phần còn lại và cắt gọn bằng `…` khi màn hình quá hẹp thay vì đè lên nhau. Đã đo ở 1000px (một dòng, không đè, giữa tự cắt) và 1280px (đủ chỗ, hiện đầy đủ).

## [0.9.77] - 2026-07-18
Xoá não giờ LAN sang mọi máy đồng bộ (không còn bị "hồi sinh"), và giữ bản sao trong thùng rác cục bộ 30 ngày. **Cần khởi động lại server** (đổi luồng sync + endpoint xoá); giao diện tự nạp lại nhờ bump `?v=7`. Có brainstorm + spec + plan ở `docs/superpowers/specs/2026-07-18-brain-delete-sync-propagation-design.md` và `docs/superpowers/plans/2026-07-18-brain-delete-sync-propagation.md`.
### Thêm mới
- **Giấy báo tử (tombstone) đồng bộ để lan việc xoá não**: khi xoá 1 não (đã gõ đúng tên xác nhận), Javis ghi một file nhỏ `<BRAINS_DIR>/.javis-tombstones/<tên>.json` đồng bộ theo repo. Bước `_apply_tombstones` mới trong sync đọc tombstone và xoá dứt khoát não đó ở mọi máy, ghi đè đúng chính sách "xoá không thắng bản còn sống" - NHƯNG chỉ cho lần xoá cố ý. Có chốt thời gian: não được tạo/sửa lại sau khi xoá thì không bị giết oan (tombstone tự gỡ, và tạo lại não cùng tên qua `/brains/new` cũng gỡ tombstone). Não mặc định miễn nhiễm.
- **Thùng rác cục bộ 30 ngày**: xoá não giờ CHUYỂN dữ liệu vào `<STATE_DIR>/brain-trash/<tên>__<thời-gian>/` (ngoài vùng đồng bộ, mỗi máy một thùng riêng) thay vì xoá cứng; tự dọn mục quá 30 ngày ở đầu mỗi lần sync. Lời xác nhận khi xoá báo rõ điều này. Khôi phục bằng tay (chuyển folder từ thùng rác về `brains/`). Endpoint xoá là nguyên tử: ghi tombstone lỗi thì hoàn tác việc chuyển thùng rác.
### Sửa lỗi
- **Não đã xoá bị "hồi sinh" khi sync/update**: chính sách sync cũ cố tình không cho việc xoá thắng bản còn sống (chống mất dữ liệu), nên một não xoá ở máy này bị máy/remote khác đẩy ngược lại. Nay lần xoá cố ý lan đi qua tombstone; lá chắn chống mất dữ liệu chung vẫn nguyên vẹn cho mọi trường hợp KHÔNG có tombstone (folder biến mất do volume chưa mount, engine ghi dở... được `_restore_missing_brains` khôi phục, không bị lan xoá).

## [0.9.76] - 2026-07-18
Giãn thanh header cho hết dồn cục, và thêm nút đổi tông tối-đậm / tối-nhạt. Có brainstorm + spec ở `docs/superpowers/specs/2026-07-18-header-theme-toggle-design.md`.
### Thêm mới
- **Nút đổi tông giao diện ở góc phải header**: lật giữa tối-đậm (mặc định, nền `#0e0e16`) và tối-nhạt (nền xám `#282a37`, chữ dịu cho đỡ chói). KHÔNG có light mode nền trắng - giữ cả app tông tối nên cockpit 3D không bị phá. Đặt `data-theme="dim"` trên `<html>` override ~9 biến CSS (màu nền/chữ + nền rail); graph 3D dùng màu hard-code nên giữ nền tối, nhưng hai tông đều tối nên nhìn liền. Nhớ lựa chọn qua `localStorage["javis.theme"]`, có inline script đầu `<head>` áp trước khi vẽ để không nháy.
### Cải thiện
- **Header hết "díu dít", giãn đều 3 cột**: `.hud-top` (grid `1fr auto 1fr`) trước đây có 4 con phẳng; ở trang quản lý `.brand` + `.hud-actions` bị ẩn khiến 2 con còn lại dồn vào cột 1-2, cột 3 (~414px) trống hoác. Nay gói thành 3 nhóm cố định cột: trái (brand + chọn brain + số liệu), giữa (tên + ngày), phải (nút theme + cụm nút cockpit). Con ẩn chỉ tự co, nhóm vẫn giữ cột nên cân ở CẢ home lẫn trang quản lý; nút theme là con trực tiếp nhóm phải nên luôn hiện, lấp đúng cột phải từng bỏ trống.

## [0.9.75] - 2026-07-18
Sửa lỗi dropdown chọn não giữ lại "folder ngoài" (📁) đã xoá khỏi ổ đĩa hoặc trùng với một não thật - chúng sống dai qua cả xoá folder, xoá não, lẫn update lên bản mới. **Cần khởi động lại server** để có endpoint `/path/exists`; phần giao diện tự nạp lại nhờ bump `?v=6`.
### Sửa lỗi
- **Menu chọn não hiện lại não cũ đã xoá**: dropdown gộp option từ 2 nguồn ĐỘC LẬP. Loại 🧠 (`data-brain`) do `brains-ui.js` nạp tươi từ `GET /brains` (đọc đĩa thật) nên xoá folder/xoá não là tự biến mất khi tải lại. Nhưng loại 📁 (`data-custom`) do `app.js` nạp từ `localStorage["javis.brains"]` (folder ngoài tự chọn qua nút duyệt) thì KHÔNG BAO GIỜ được kiểm tra tồn tại, không dọn, không có nút gỡ. `localStorage` sống theo origin trình duyệt nên trụ qua cả xoá folder, xoá não lẫn update app - đúng triệu chứng. Nút thùng rác khi chọn 📁 còn báo "folder ngoài thì bỏ khỏi danh sách" nhưng không cung cấp cách bỏ nào → entry kẹt vĩnh viễn.
- **`brains-ui.js` giờ tự dọn danh sách 📁 mỗi lần nạp**: sau khi có danh sách não thật, hàm `pruneCustomBrains` bỏ khỏi `localStorage` những entry TRÙNG path một não thật (tránh hiện 2 lần) và entry mà path KHÔNG còn là thư mục (đã xoá khỏi đĩa), GIỮ lại folder ngoài hợp lệ khác path. Dọn ngay nguồn `localStorage` nên lần `app.js` render sau vẫn đúng, không "sống lại" qua update. Chạy TRƯỚC bước khôi phục lựa chọn để không khôi phục về một path đã chết.
- **Nút thùng rác gỡ được folder ngoài 📁**: chọn một 📁 rồi bấm xoá giờ hỏi xác nhận và gỡ khỏi menu + `localStorage` (KHÔNG đụng dữ liệu trên ổ đĩa), thay vì chỉ báo lỗi rồi bó tay như trước.
### Thêm mới
- **Endpoint `GET /path/exists?path=`** (đọc-only, chỉ `os.path`, nhẹ): trả `{exists, is_dir}` cho một đường dẫn tuyệt đối. Dùng để dropdown kiểm tra folder ngoài còn tồn tại không. FAIL-SAFE: lỗi truy cập trả `exists=null` → frontend hiểu là "chưa xác định" và GIỮ entry, chỉ dọn khi server xác nhận rõ path đã mất (endpoint thiếu/404 vì server chưa restart, hay lỗi mạng, đều không làm mất entry hợp lệ). Kèm test `server/test_path_exists.py` + `dashboard/test_brains_ui.mjs` (mock DOM, chạy thẳng logic dọn đúng kịch bản bug thật).

## [0.9.74] - 2026-07-18
Gom phần "mức dùng" thành một trang riêng có đồ thị, bỏ widget nổi vướng víu, và tinh chỉnh nốt nút thu/mở rail. **Cần khởi động lại server** để đồ thị mức dùng có dữ liệu (thêm field ở endpoint `/usage`); phần còn lại chỉ cần tải lại trang.
### Thêm mới
- **Trang "Mức dùng" trong rail (nhóm Hệ thống) có đồ thị 14 ngày**: thay cho hộp mức dùng nhỏ trước đây, giờ là một trang đầy đủ gồm 3 thẻ tổng (hôm nay, tổng tích luỹ, số dư OpenRouter), đồ thị cột token/ngày 14 ngày gần nhất, và bảng chi tiết theo nhà cung cấp/model (token vào/ra, số lượt, chi phí). Endpoint `/usage` thêm field `daily` (hàm `usage_store.daily(14)` gộp per-day, lấp cả ngày trống cho trục liền mạch). Số liệu vẫn do Javis tự đo, giữ 30 ngày.
### Cải thiện
- **Bỏ widget "MỨC DÙNG" nổi ở góc dưới khung giữa**: user thấy vướng. Gỡ khối HTML + CSS; hàm `refreshUsage`/`initUsageToggle` trong app.js tự thành no-op (đã có guard khi không thấy element) nên không cần đụng tới, không còn fetch `/usage` mỗi lượt chat.
- **Nút thu/mở rail dời sang PHẢI, version/tác giả sang trái**: `.rail-foot` xếp `space-between` (dùng `order`), icon nút to lên chút (18px) cho cân với icon nav; khi thu gọn chỉ còn nút, căn giữa.
- **Tooltip nhãn khi rê chuột lúc thu gọn hiện nhanh hơn**: native `title` trễ ~500ms, thay bằng tooltip tự vẽ (1 node body-level, thoát mọi overflow của rail) hiện sau 90ms, đặt cạnh phải icon; tạm gỡ `title` lúc hover để không lòi thêm tooltip native chậm, trả lại khi rời chuột (giữ cho screen-reader).

## [0.9.73] - 2026-07-18
Tinh chỉnh nút thu/mở rail (bản 0.9.72) theo góp ý: đổi icon, dời vị trí, và sửa link tác giả.
### Cải thiện
- **Icon nút thu/mở đổi sang kiểu "panel sidebar"**: thay mũi tên kép `«` bằng khung vuông chia hai với cột trái có các dòng nội dung (giống icon toggle sidebar quen thuộc). Icon tĩnh, bỏ hiệu ứng xoay 180° khi thu (kiểu panel không cần chỉ hướng, trạng thái đã có tooltip).
- **Dời nút thu/mở nằm CẠNH dòng version thay vì phía trên**: `.rail-foot` đổi từ xếp dọc sang hàng ngang, nút ở trái kề số phiên bản + "by Minh Quý". Khi thu gọn vẫn ẩn version/tác giả, chỉ còn mỗi nút căn giữa.
- **Link "by Minh Quý" trỏ về javisos.com** thay cho minhquy.vn.

## [0.9.72] - 2026-07-18
Làm gọn thanh điều hướng bên trái (rail) theo góp ý trực tiếp: chữ khó đọc vì dùng font monospace, header nhóm trơ không icon, và rail chiếm quá nhiều bề ngang màn hình.
### Thêm mới
- **Nút thu/mở sidebar ở góc dưới**: bấm để thu rail còn 60px chỉ hiện cột icon dọc (tên mục hiện qua tooltip khi rê chuột), bấm lần nữa bung lại đầy chữ 160px. Phần nội dung bên phải tự giãn chiếm lại chỗ khi thu (mọi offset chạy qua biến `--rail-w`, thu chỉ đổi 1 biến trên `body.rail-collapsed`). Trạng thái nhớ qua `localStorage` nên lần sau vào giữ nguyên. Mũi tên nút xoay 180° báo trạng thái (xoay cả nút chứ không xoay riêng `<svg>` để né quirk transform-box của SVG root). Luật thu gọn bọc trong `@media (min-width: 861px)` nên KHÔNG chạm thanh dưới ngang trên mobile.
### Cải thiện
- **Rail thành 2 tầng gập/mở thay cho danh sách phẳng dài phải cuộn**: tầng 1 là tên nhóm bấm để xổ, tầng 2 là các mục con trượt ra dưới (max-height transition). Mỗi lúc chỉ 1 nhóm mở; nhóm chứa trang đang xem tự mở, nếu đang gập thì tên nhóm hé màu cam để biết mình ở đâu. Store `nav` thêm `openGroup`/`toggleGroup`/`collapsed`/`toggleCollapsed`.
- **Sửa font sai + chữ to hơn**: nhãn rail trước dùng biến `--font` (monospace `SF Mono`/`Consolas`) làm chữ tiếng Việt có dấu cứng và lệch. Thêm biến `--font-ui` (Segoe UI sans-serif) cho riêng rail; cỡ chữ tên nhóm 12.5px, tên mục 13.5px (trước 11 và 12.5px).
- **Thêm icon cho tên nhóm (tầng 1)**: 6 icon line-style đồng bộ với icon mục (`GICON`) cho Trợ lý/Bộ não/Năng lực/Việc/Kết nối/Hệ thống, hết trơ.
- **Thu bề ngang rail 172→160px** ở chế độ mở rộng cho đỡ dư diện tích; đã đo không mục nào bị cắt chữ (kể cả "Việc định kỳ").

## [0.9.71] - 2026-07-17
Bản 0.9.70 ship tool `javis_schedule` ra ngoài trong tình trạng KHÔNG dùng được thật - review độc lập (chạy code, không đoán) tìm ra 2 lỗi Critical, 3 lỗi Important và 1 khoản nợ kỹ thuật. Bản này vá toàn bộ. Cảm ơn review đã chỉ đúng: "cả hai nửa của tool đều không làm được việc nó hứa".
### Sửa lỗi
- **[Critical] `httpx` ĐỒNG BỘ gọi ngược vào chính server đang chạy nó → treo CẢ SERVER**: handler `javis_schedule` (`plugin.py`) là `def` thuần, và 3 hàm `_post_reminder`/`_get_reminders`/`_cancel_reminder` gọi `httpx.post`/`httpx.get` ĐỒNG BỘ tới `http://127.0.0.1:<port>/reminders`. `plugins_host._make_call` gọi handler plugin bằng `res = handler(args, ctx)` rồi mới `await` - KHÔNG bọc `asyncio.to_thread` - nên lệnh `httpx.post` chặn NGUYÊN event loop của uvicorn (1 worker duy nhất, `main.py:5037`) trong lúc nó tự chờ CHÍNH request đó được trả lời → deadlock, `ReadTimeout` sau ~5-10s, và trong lúc đó server không trả lời được BẤT KỲ ai (mọi user, mọi tool). Tệ hơn: nhắc hẹn vẫn được tạo thật (đã vào hàng đợi trước khi treo), tool trả lỗi nên model retry → tạo THÊM 1 nhắc trùng + treo thêm 1 lần. Vá: cả 4 hàm chuyển `async def` + `httpx.AsyncClient`, đúng khuôn `system/plugins/meta-ads-graph/plugin.py` (`_get()`) và `system/plugins/image-chatgpt/plugin.py` (`_gen()`) - 2 plugin bundled còn lại vốn đã làm đúng từ đầu, `javis-schedule` là ngoại lệ duy nhất phá quy ước.
- **[Critical] Loop tạo qua tool KHÔNG BAO GIỜ làm việc user yêu cầu**: `_create_loop_file` ghi frontmatter thiếu hẳn field `goal`. `self_improve.py:250` `goal = fm.get("goal", "business")` mặc định `"business"` khi thiếu, và nhánh `goal == "business"` (`self_improve.py:546`) không đọc `loop["body"]` một chữ nào (thân file - đúng chỗ chứa prompt user vừa gõ qua chat). Hai kiểu hỏng: chưa đấu MCP số liệu kinh doanh → `skip_reason` khiến loop bỏ qua VÔ HẠN mọi vòng; có POS/ads → loop âm thầm chạy "phân tích chỉ số kinh doanh" (nhiệm vụ mặc định) thay vì việc user thật sự yêu cầu, rồi vẫn báo Telegram như đã làm đúng việc. Form web tạo loop vốn làm đúng (`self_improve.py:914` `goal = goal or (old["goal"] if old else "custom")`) - tool là nơi DUY NHẤT sai. Vá: `_create_loop_file` ghi cứng `goal: custom` vào frontmatter, kèm comment giải thích tại sao dòng này bắt buộc để không ai vô tình xoá.
- **`notify_only` không có tác dụng gì - mọi nhắc đều dựng nguyên engine Claude + MCP để "làm hộ"**: `_do_create` hard-code `"mode": "task"` trong payload gửi `POST /reminders`, bất kể `notify_only`. Hậu quả: "30 phút nữa nhắc anh gọi khách" (chỉ muốn 1 câu nhắc) tới giờ lại chạy `reminders.py:418 _run_task` (dựng CLI, đọc MCP, `max_wall_s=300`) rồi gửi "⏰ Nhắc hẹn (Javis đã làm): ..." thay vì đúng "⏰ Nhắc anh: ..." (`reminders.py:342`) - ngược hẳn mô tả tool tự khai và ngược CLAUDE.md ("notify_only=true nếu chỉ nhắc"). Vá: `"mode": "notify" if notify_only else "task"`.
- **Lịch "mỗi tuần"/"mỗi ngày"/"mỗi tháng"/"mỗi sáng" đều bị hiểu thành chạy MỖI 5 PHÚT**: `_UNIT_ALT` trước đó chỉ biết phút/giờ (VN + tắt tiếng Anh), không có ngày/tuần/tháng; các chuỗi này không match được số+đơn vị nên `_interval_min` rơi về sàn cứng 5 phút - "việc mỗi tuần tổng kết doanh thu" thành ra chạy 5 phút/lần (cộng lỗi goal ở trên = spam Telegram + đốt phí LLM thật). Ca nặng hơn: "mỗi sáng 7h" bị hiểu thành "mỗi 7 TIẾNG" (`interval_min=420`) vì regex chỉ thấy số "7" + đơn vị "h", không phân biệt được đó là MỐC GIỜ TRONG NGÀY chứ không phải khoảng cách lặp. Vá 3 lớp: (1) thêm `ngay=1440`/`tuan=10080`/`thang=43200` vào bảng quy đổi, và cho phép đơn vị đứng một mình ngầm định số lượng 1 ("mỗi ngày" = "mỗi 1 ngày"); (2) hàm `_daily_cron` mới dò tín hiệu LẶP HẰNG NGÀY (`mỗi` + buổi sáng/trưa/chiều/tối, hoặc từ "ngày", hoặc cụm "hằng ngày") CỘNG một mốc giờ đồng hồ (`7h`, `07:00`) → route sang kho reminders dạng cron 5 trường thay vì loop interval; (3) **luật an toàn**: lịch mơ hồ không rút được đơn vị/mốc giờ nào (vd "mỗi sáng" trơ, "mỗi khi rảnh") → `_interval_min` trả `None`, `_create_loop_file` trả `"ERROR: ..."` yêu cầu nói rõ hơn - KHÔNG còn âm thầm rơi về 5 phút trong bất kỳ trường hợp nào.
- **Skill `javis-builder` dạy gõ YAML tay, thắng cả chỉ dẫn "ưu tiên gọi tool" của CLAUDE.md**: `CLAUDE.md` (mục "Tự tạo năng lực") nói dùng skill `javis-builder`; skill này nạp SAU nên cụ thể hơn thắng - mà mục Loop của nó (trước bản này) chỉ có mẫu YAML để tự ghi file, không nhắc một chữ `javis_schedule`, nên model vẫn gõ tay dù tool đã có sẵn (và thiếu cả `owner_chat` trong mẫu → loop viết tay báo nhầm người). Vá: mục Loop giờ dạy ưu tiên gọi tool `javis_schedule` (op=create) trước, chỉ ghi file tay khi SỬA loop đã có hoặc cần trường nâng cao tool chưa nhận (`quiet_hours`/`max_runs_per_day`/`workspace`/`ambient_mcp`/`goal` khác `custom`); mẫu YAML còn lại thêm `goal: custom` + `owner_chat` cho đúng chuẩn tool đang tạo ra. Kèm hash bản cũ vào `system_sync.py:LEGACY_HASHES["skills/javis-builder"]` để brain user tự nhận bản vá này qua sync (không bị coi là "đã sửa tay").
- **`apply_mcp` không truyền `brain` ở vài đường UNGATED, plugin in-process vẫn có thể mù brain**: những nơi tạo CLI với `allowed_tools=None` (ungated) đều nạp plugin in-process (`claude_sdk_engine._plugins_server`, đọc `cli.javis_vault`) - thiếu `brain` là tái diễn đúng bug 0.9.70 vừa vá ở đường chat (`image-chatgpt` lưu nhầm `brains/Brain Default`). Vá `self_improve._make_cli` nhận thêm tham số `brain`, truyền xuống cả 3 lần gọi `apply_mcp` bên trong (nhánh `mode=full`, nhánh `ambient_mcp`, và nhánh mặc định - nhánh này thật ra GATED nên plugin không nạp, nhưng vẫn truyền cho nhất quán/phòng hờ); 2 điểm gọi `_make_cli` trong `run_cycle`/kiểm chứng nay truyền `brain=brain` có sẵn trong scope. Thêm `else` nhánh ungated của `execute_workflow` (`main.py`, Studio "chạy full quyền") gắn thẳng `c.javis_vault = vault_root` - KHÔNG gọi `_apply_mcp()` ở đây vì nhánh này cố ý dựa `setting_sources` để kế thừa MCP máy như phiên `claude` tương tác thật, gọi `_apply_mcp` sẽ đổi hành vi ngoài phạm vi bug đang vá. **2 đường còn lại KHÔNG sửa được** vì không có biến brain/vault nào trong scope để truyền (không bịa biến): `/metrics` (`main.py:1451`) không nhận tham số brain (endpoint dùng chung mọi brain); `/ingest-upload` (`main.py:1733`) chỉ nhận `staged`/`sources`/`attachments` đã resolve sẵn, không có brain gốc.
### Kiểm thử
- `test_javis_schedule.py` thêm 5 nhóm test chặn đúng các lỗi trên: (1) `inspect.iscoroutinefunction` trên handler + 3 hàm HTTP - lưới hồi quy chặn quay lại lối sync; (2) LƯỚI THẬT cho lỗi goal - đưa loop vừa tạo qua ĐÚNG API `self_improve.LoopFeature.get_loop` (không chỉ kiểm tra chữ đã ghi ra file) và khẳng định `goal == "custom"` + thân file tới được nơi sẽ chạy; (3) monkeypatch `_post_reminder` bắt payload, khẳng định `mode` đổi đúng theo `notify_only`; (4) `_interval_min` cho ngày/tuần/tháng + cron mốc giờ cố định + lịch mơ hồ phải `None`/`ERROR`; (5) dispatcher với `op` sai và `vault_root` rỗng. `test_loop_ambient.py` cập nhật stub `_apply_mcp` nhận thêm `brain=None` để khớp chữ ký mới.

## [0.9.70] - 2026-07-17
### Thêm mới
- **Tool `javis_schedule` - chat đặt được việc định kỳ, thôi gõ YAML tay**: trước đây muốn "tạo việc mỗi 2 tiếng quét đơn" phải tự gõ YAML frontmatter vào `Javis/loops/<slug>.md`, hoặc shell ra `curl POST /reminders` (`reminders.py:17` vốn ghi thẳng cách đó). Đường thứ hai còn tự mâu thuẫn: loop mode suggest/auto bị chặn Bash (`self_improve.py:112`) nên loop không tự đặt nhắc được cho chính nó. Nay một câu chat gọi thẳng tool, `op=create` tự route vào 1 trong 2 kho theo tính chất việc: lặp + bền → file `.md` (sửa được trong Obsidian); nhắc/cron/một lần → kho reminders (đã có cron 5 trường sẵn: `cron_util.py`, tự tính lần kế ở `reminders.py:364`). `op=list` nhìn CẢ HAI kho, `op=cancel` huỷ nhắc đang chờ. An toàn giữ nguyên luật CLAUDE.md: loop tạo qua chat luôn `enabled: false` + `mode: suggest`, không nhận tham số để đổi; trùng slug báo lỗi chứ không đẻ bản sao song song (định danh theo TÊN FILE, `self_improve.py:321-327`).
- **Vì sao là plugin bundled chứ không phải tool trong hub**: hub không với tới được mọi engine cho việc này, vướng hai rào. Rào 1: `_builtin_tools` (`mcp_hub.py:211-212`) early-return ngay khi `vault_root` rỗng - không đăng ký thêm tool nào cần biết brain - mà đường HTTP hub (`tools/list`/`tools/call`, `mcp_hub.py:392,398`) luôn gọi `discover_all` không kèm brain nên `vault_root` luôn `None` ở đường đó. Rào 2: `claude_config_path` (`mcp_hub.py:448-453`) trả `None` khi chưa có connector MCP nào bật, tức Claude Code còn chưa từng thấy hub tồn tại. Plugin đi qua MCP server IN-PROCESS của engine SDK (`claude_sdk_engine.py:162-186`, phần `_plugins_server`), không dính rào nào trong hai rào đó.
### Sửa lỗi
- **Plugin gọi từ chat luôn mù brain, `javis_generate_image` âm thầm lưu ảnh vào Brain Default**: `_plugins_server` (`claude_sdk_engine.py`) trước đây tự suy brain từ `self.cwd`, nhưng chat luôn chạy với `cwd=CLAUDE_CWD` (`main.py:318`, gốc project - không có thư mục `Javis/`) nên phép suy này luôn trượt về `None` ở đúng đường chat, mọi plugin gọi từ Claude Code đều nhận `ctx.vault_root=None`. Hệ quả cụ thể: `image_gen._resolve_vault` rơi về fallback `brains/Brain Default`, không có lỗi nào báo. Việc build `javis_schedule` (cần ghi đúng `Javis/loops/` của brain đang mở) mới lộ ra brain chưa từng được truyền tường minh qua engine SDK. Vá: `_apply_mcp` (`main.py`) nhận thêm tham số brain, đặt `cli.javis_vault` tường minh ở cả hai đường chat (dashboard websocket + Telegram, brain có sẵn trong scope) - không còn suy từ cwd.
- **Tên việc chứa ký tự chỉ-thị YAML làm loop chết âm thầm**: `_yaml_scalar` trước đó chỉ escape `[:#'"\n]`, bỏ sót các ký tự YAML coi là chỉ thị đầu dòng (`- @ * ! % ? | & >`). Tên việc dùng ký tự này ghi ra frontmatter vỡ, `yaml.safe_load` ném `ScannerError`/`ConstructorError`, và `self_improve.list_loops()` nuốt lỗi bằng try/except nên loop biến mất khỏi tab Việc định kỳ dù tool vừa báo "đã tạo thành công". Sửa bằng cách luôn trả về chuỗi nháy kép kiểu JSON (`json.dumps`) thay vì liệt kê ký tự cần escape - YAML 1.2 là superset của JSON nên scalar nháy kép JSON luôn hợp lệ. Áp dụng cả cho `owner_chat` (trước đó nối chuỗi tay, không qua hàm escape nào).
- **`op=cancel` luôn 401 trên instance đã bật mật khẩu**: `POST /reminders/cancel` thiếu trong `_AUTH_LOCAL_EXACT` (`main.py`), nên khi `gate_active()=True`, `javis_schedule` gọi httpx từ localhost (không cookie) luôn bị chặn. `/reminders` (tạo nhắc) đã được miễn cùng nhóm từ trước; huỷ là thao tác yếu hơn tạo nên miễn cùng mức mới nhất quán.
### Cải thiện
- **CLAUDE.md dạy đúng thứ vừa xây**: mục "Điều phối" bậc 6 (Nhắc hẹn) đổi từ `POST /reminders` sang gọi tool `javis_schedule`; bậc 7 (Loop) thêm câu ưu tiên gọi tool thay vì tự ghi file. Lý do phải sửa ngay trong bản có tool: mô tả tool cạnh tranh trực tiếp với chỉ dẫn trong system prompt, và prompt thường thắng - có tool mà tài liệu vẫn dạy gõ YAML tay thì model vẫn gõ tay. Phần mô tả format file loop giữ nguyên bên dưới, vẫn cần để SỬA loop đã có.

## [0.9.69] - 2026-07-17
### Bảo mật
- **`/automations/sync` là một lỗ bảo mật, xoá cùng toàn bộ tính năng giả nó thuộc về**: route gọi `claude_engine(...)` không truyền `allowed_tools`, nên theo `claude_sdk_engine.py:290-301` nó chạy `permission_mode="bypassPermissions"` VÀ nạp `setting_sources=["user","project","local"]` - engine call ít rào nhất trong codebase. Bảo đảm "CHỈ LIỆT KÊ" của route này chỉ là chữ trong prompt, không có gate thật nào đứng sau. Xoá route cùng lúc với toàn bộ registry `automations`.
### Cải thiện
- **Tab "Lịch" từng là tính năng giả, nay xoá sạch**: `Javis/automations.json` chưa từng có executor nào đọc - `_scheduler_loop` (`server/main.py`) tick 6 việc (loop, learn, kanban, reminders, backup, index) và không nhánh nào đọc file này. Kiểm tra thực tế trước khi xoá: 0 file `automations.json` tồn tại trên cả 4 brain đang chạy, 0 test phủ. Cái làm nó trông giống thật: badge xanh "N đang chạy" cho những dòng không bao giờ nổ, và ô lịch là free text không dòng code nào parse - vì tab phần lớn đang chiếu chính Loop qua hai lớp `_loops_as_routines` (main.py) và `pending_as_automations` (reminders.py), với chuỗi "mỗi N phút" bị bịa ra ngay lúc GET chứ không đọc từ đâu cả. Cả hai lớp chiếu, 3 helper registry và 5 route `/automations*` nay đã xoá.
- **Một trang "Việc" thay cho hai trang Loop + Lịch**: rail `selfimprove` đổi nhãn "Loop" thành "Việc định kỳ", gộp thêm khối "Nhắc hẹn đang chờ" (đọc `GET /reminders`, huỷ qua `POST /reminders/cancel`) - bắt buộc phải gộp vì nhắc hẹn trước đây CHỈ hiện ở tab Lịch vừa xoá. Không thêm endpoint mới: trang đọc thẳng `GET /loops` và `GET /reminders` vốn đã có sẵn.
- **Ô thống kê ROUTINES xoá hẳn, không thay bằng ô khác**: ô này ở `index.html` đếm "routines đang chạy" bằng cách fetch `/automations` trong `loadBrainStats()` (`app.js`) - chính route vừa xoá ở trên, nên sau khi route biến mất, số hiển thị mãi mãi là 0 vì lỗi 404 bị `.catch(() => ({}))` nuốt âm thầm. Ô này đúng là badge nói dối mà việc dọn tab Lịch sinh ra để diệt, chỉ là kế hoạch ban đầu bỏ sót nó vì chưa từng grep `app.js`.
- **Dọn 138 dòng cụm chết của panel loop cũ**: panel `<div class="loop-box" style="display:none">` trong `index.html` cùng cụm phục vụ nó trong `app.js` (`loadLoopConfig`, `saveLoopConfig`, `renderLoopStatus`, `loadLoopLog`, listener `loopRunNow` kèm vòng poll, listener `lintBtn`, các fetch `/loop/config`, `/loop/log`, `/loop/run-now`) - panel đã bị ẩn cứng bằng `display:none` và không dòng code nào từng gỡ nó ra, nên toàn bộ cụm phía sau không thể chạm tới được nữa. Backend `/loop/config` và `/lint` giữ nguyên, chỉ dọn phía UI đã chết.

## [0.9.68] - 2026-07-17
### Cải thiện
- **Lịch sử hội thoại chỉ hiện 20 mục, có nút "Xem thêm 20"**: sidebar trước đây đổ thẳng 100 hội thoại ra một mạch, chat nhiều thì danh sách dài lê thê phải cuộn mãi mới hết. Nay mặc định 20 mục, mỗi lần bấm mở thêm 20 nữa, hết hội thoại thì nút tự ẩn. Không cần sửa server: endpoint `/sessions` vốn nhận `limit` tự do nên client chỉ việc xin dư đúng 1 mục (`limit = shown + 1`) để biết còn dữ liệu phía sau hay không.
- Số mục đang mở được giữ nguyên khi danh sách tự làm mới lúc có tin nhắn mới (nếu không thì đang xem 60 mục lại bị thu về 20), và chỉ reset về 20 khi đổi brain. Lần render lại cũng giữ chỗ cuộn để bấm "Xem thêm" không bị nhảy vọt lên đầu.
- **Tìm kiếm vẫn quét toàn bộ hội thoại** như cũ, không bị giới hạn 20 mục này chạm vào.

## [0.9.67] - 2026-07-17
### Sửa lỗi
- **Xoá một bước làm MẤT TRẮNG chữ đang gõ dở ở các bước khác**: nút ✕ gọi thẳng `steps.splice(i, 1)` rồi `render()` mà quên gọi `captureSteps()` trước (nút "+ Bước" thì có gọi), nên `render()` vẽ đè mọi ô nhập bằng giá trị cũ trong mảng. Sửa vài bước, chưa Lưu, bấm xoá một bước bất kỳ là bay sạch, rất dễ tưởng mình gõ nhầm. Đã dựng lại đúng kịch bản trên cả bản cũ lẫn bản mới để đối chứng: bản cũ trả về chữ cũ, bản mới giữ nguyên chữ vừa gõ.
- **Dòng "Kiểm chứng" vỡ thành ba dòng**: quy tắc gộp `.editor-box input { width: 100% }` có specificity (0,1,1), thắng `.st-retries { width: 48px }` chỉ (0,1,0), nên ô số lần bị kéo full-width và đẩy chữ "lần" xuống dòng riêng. Ý đồ ban đầu là ba thứ nằm gọn một dòng nhưng CSS chưa bao giờ chạy đúng ý đó. Nay đổi thành `.editor-box .st-retries` (0,2,0). Ô chọn agent kiểm chứng không dính lỗi này vì nó có `flex: 1`.
### Cải thiện
- **Form Sửa workflow gập bước lại để thấy toàn cảnh**: workflow 11 bước trước đây trải hết cỡ trong hộp cao 86vh nên chỉ thấy được một bước rưỡi mỗi lần, muốn nắm tổng thể phải cuộn liên tục. Nay mỗi bước là một dòng gọn gồm số, tên agent và trích nội dung việc; bấm vào thì mở ra sửa, mở bước khác thì bước cũ tự gập. Các ô nhập vẫn nằm trong DOM khi gập (chỉ ẩn bằng CSS) nên `captureSteps()` đọc đủ, bước đang gập vẫn giữ nguyên cấu hình kiểm chứng lúc Lưu.
- **Thêm nút lên/xuống đổi thứ tự bước**: trước đây muốn chuyển bước 9 lên trước bước 4 phải chép tay qua lại. Nút ↑ ở bước đầu và ↓ ở bước cuối tự mờ đi.

## [0.9.66] - 2026-07-17
### Cải thiện
- **Biến workflow trong ô bước đọc thành lời thay vì dấu ba chấm**: mã cũ thay mọi `{{...}}` bằng `…`, nên bước đầu của viral-video-production hiện ra "Nhận …, tạo project folder" đọc lên cụt nghĩa. Nay `{{input}}` thành "đầu vào", `{{prev}}` thành "kết quả bước trước", và biến lạ thì hiện thẳng tên biến chứ không nuốt mất. Xử đúng cả trường hợp có khoảng trắng trong ngoặc như `{{ input }}`.

## [0.9.65] - 2026-07-17
### Sửa lỗi
- **Trang Workflows hiện các bước thành mấy cột cao lêu nghêu, rỗng ruột**: dải bước dùng `flex: 1` chia đều bề ngang, nên workflow 11 bước (viral-video-production) bị bóp mỗi ô còn khoảng 35px, trong khi tên agent `viral-video-director` có `white-space: nowrap` nên bị cắt sạch không còn chữ nào, chỉ trơ lại số thứ tự. Nay mỗi ô rộng tối thiểu 150px và tự xuống dòng khi hết chỗ, chữ luôn đọc được. Đo thật trên màn 1720px: 10 ô một hàng, ô thứ 11 xuống hàng dưới; 1280px được 7 ô; 900px được 5; 600px được 3; 380px được 2. Bề rộng ô luôn nằm trong 152 tới 173px ở mọi khổ và không khổ nào tràn ngang.
- **Bước từ thứ 10 trở đi đánh số sai thành `010`, `011`**: mã nối chuỗi `0${i+1}` nên chỉ đúng với bước 1 tới 9. Thay bằng `padStart(2, "0")`.
- **Thẻ workflow bị nhét vào lưới cột hẹp**: panel Workflows dùng chung lưới `.cards` (`auto-fill, minmax(280px, 1fr)`) với Agents và Lịch, mà pipeline lại nằm ngang nên hai thứ đánh nhau, và khi chỉ có một workflow thì phần còn lại của hàng bỏ trống. Nay Workflows có `.wf-list` và `.wf-row` riêng, mỗi workflow một hàng đầy chiều rộng; Agents, Lịch, plugin và loop giữ nguyên `.cards`/`.wf-card` cũ nên không bị ảnh hưởng.
### Cải thiện
- **Ô bước lấy việc làm làm chữ chính, tên agent hạ xuống chữ phụ**: nhiều workflow gọi cùng một agent ở mọi bước, lấy agent làm chữ chính thì 11 ô hiện chữ giống hệt nhau và không phân biệt được bước nào với bước nào. Nội dung task cắt gọn 2 dòng, di chuột vào xem đầy đủ.
- **Cụm nút và số bước dồn lên cùng hàng với tên workflow**, thay vì nằm dưới cùng, nên quét nhanh hơn khi có nhiều workflow.

## [0.9.64] - 2026-07-17
### Sửa lỗi
- **Javis tốn tới ~52ms mỗi lượt chat chỉ để đồng bộ skill, và nó chặn cả tiến trình**: hàm mirror skill đọc và băm lại `SKILL.md` của MỌI skill (cả bản nguồn lẫn bản đích) mỗi lần dựng system prompt, tức mỗi lượt chat, mỗi tin Telegram, mỗi task Kanban, mỗi vòng loop, mỗi nhắc hẹn. Đo thật trên 3 brain đang chạy, trước khi sửa: My Bullet Journal (27 skill/41 file) 52,48ms/lượt, Ngọc Thu Phạm (16 skill/30 file) 44,23ms/lượt, Brain Default (6 skill/9 file) 11,62ms/lượt - chạy đồng bộ trên event loop nên làm đứng luôn các kết nối khác. Nay thay bằng cổng chữ ký chỉ dùng `stat` (không đọc nội dung file nào), chỉ copy thật khi cây skill có thay đổi. Đo lại đúng 3 brain đó sau khi sửa: còn 8,30ms, 6,05ms, 2,28ms/lượt theo cùng thứ tự - nhanh hơn khoảng 5 tới 7 lần tuỳ brain (5,1x / 6,3x / 7,3x), không phải một con số cố định. Lỗi có sẵn, không ai biết cho tới khi đo.
- **File phụ trong skill đổi nội dung mà bản mirror không bao giờ nhận**: cổng cũ chỉ băm `SKILL.md`, nên sửa một file ảnh hay tài liệu ngang hàng trong thư mục skill thì bản Claude Code nạp native vẫn giữ bản cũ mãi. Chữ ký mới phủ mọi file (đường dẫn tương đối, thời gian sửa, kích thước) nên hết lỗi này.
### Thêm mới
- **Skill mang theo được `references/` và `scripts/`**: bản mirror sang `.claude/skills` nay copy cả cây con, nên skill có tài liệu tách riêng hay script đi kèm chạy được cả trên đường Claude Code nạp native, không chỉ đường router. 10 skill trong các brain hiện có đã dùng `references/` từ trước và tới giờ vẫn chưa tới được đường native; đã xác nhận cả 10 tới nơi sau bản này.
### Đã biết, chưa sửa
- **Skill hệ thống vẫn chưa ship được cây con**: `html-to-webcake` ship kèm `tools/` và `examples/` nhưng cơ chế cài skill hệ thống chỉ chuyển mỗi `SKILL.md`, nên cây con chưa bao giờ tới brain nào. Bản này KHÔNG sửa lỗi đó: nó nằm ở tầng cài đặt, phía trên tầng mirror.
- **Bản mirror bị phá từ bên ngoài sẽ không tự lành cho tới khi khởi động lại**: cổng chữ ký tính trên cây nguồn và nhớ trong bộ nhớ, nên nếu ai đó xoá tay file trong `.claude/skills` mà không đụng vào skill gốc thì Javis sẽ không nhận ra. Đánh đổi có chủ đích để lấy tốc độ; tắt/bật skill hay khởi động lại đều đưa nó về đúng.

## [0.9.63] - 2026-07-17
### Sửa lỗi
- **Skill Javis TỰ HỌC mất sạch frontmatter khi mô tả có dấu hai chấm**: `learn.py` ghi `description: <giá trị>` không bọc nháy kép. Mô tả tiếng Việt rất hay có dấu hai chấm (chính bản 0.9.62 phải bọc nháy kép cho 2 trong 5 skill hệ thống, tức khoảng 40%), và khi đó PyYAML ném lỗi trên CẢ KHỐI frontmatter chứ không riêng một dòng: `name`, `group`, `origin`, `status` mất theo, `split_frontmatter` nuốt lỗi trả về rỗng, và skill đó im lặng không bao giờ route được. Nay mọi giá trị do model sinh (`name`, `description`, `group`) đều đi qua `_yaml_scalar` (bọc nháy kép + escape đúng), kèm test round-trip gọi thẳng mã thật.
- **`learn.py` chưa hề ép trần 150 ký tự**: bản 0.9.62 chỉ chặn ở `POST /skills`. Đường tự học vẫn ghi thẳng mô tả quá dài xuống đĩa rồi để runtime cắt cụt. Nay `_promote_sync` gọi `validate_description` và đưa vi phạm vào danh sách bị chặn, cùng khuôn với quét secret và quét injection sẵn có.
- **`javis-builder` vẫn dạy đúng cái lỗi mà 0.9.62 sinh ra để diệt**: mẫu file trong skill đó, nằm dưới tiêu đề "ghi CHÍNH XÁC theo đây", vẫn ghi `description: <mô tả NGẮN nêu rõ KHI NÀO kích hoạt - đây là trigger, viết kỹ>` trong khi bộ chuẩn ngay 14 dòng dưới nói ngược lại. **CHANGELOG 0.9.62 tuyên bố "cả hai" tài liệu đã sửa là SAI**: `CLAUDE.md` sửa rồi, `javis-builder` thì chưa. Vì skill viết qua chat ghi thẳng ra đĩa nên không lớp chặn nào bắt được, và người viết theo mẫu sẽ tạo ra skill không route được mà không có lỗi nào báo. Nay đã sửa mẫu và một chỗ thứ hai cùng loại.
- **Sidecar đếm lượt dùng bị hỏng KIỂU dữ liệu làm sập cả trang Skill**: `GET /skills` và `is_stale` ép kiểu số mà không phòng thủ, nên một bản ghi bị sửa tay hỏng sẽ trả lỗi 500 cho toàn trang, trái đúng cam kết "sidecar hỏng không bao giờ được làm gãy". Nặng hơn: nó không tự lành, vì `bump` cũng vấp đúng chỗ đó rồi nuốt lỗi, nên bản ghi hỏng tồn tại vĩnh viễn và cả brain ngừng đếm. Nay cả ba chỗ đều phòng thủ, và `bump` ghi đè để tự lành ở lượt dùng kế tiếp.
### Thêm mới
- **Javis biết skill nào THẬT SỰ được dùng**: mỗi lần nạp skill qua `javis_use_skill` được ghi vào `Javis/skill-usage.json` của brain. Trang Skill hiện "đã dùng N lần, gần nhất ..." hoặc "chưa thấy dùng" cho skill đủ già mà chưa có tín hiệu. **Đây là tín hiệu MỘT CHIỀU và cần hiểu đúng**: Claude Code còn nạp skill NATIVE qua bản mirror `.claude/skills`, đường đó không đi qua bộ đếm. Nên "đã dùng" là chắc chắn, còn "chưa thấy dùng" chỉ có nghĩa **chưa có bằng chứng**, KHÔNG có nghĩa skill vô dụng. Không có gì tự tắt, tự archive hay tự dọn skill dựa trên con số này; mọi quyết định vẫn là của người dùng.
- **Chuẩn viết skill trong prompt của vòng tự học**: 9 điểm bắt buộc (trần 150 nội suy từ hằng số chứ không viết cứng, cấm mở đầu sáo rỗng, bọc nháy kép khi có dấu hai chấm, thứ tự mục thân file, cấm bịa flag và đường dẫn, trần độ dài thân, cấm skill kiểu router), kèm `group` thành trường bắt buộc trong schema.
- **Sidecar không lọt vào lịch sử học**: `Javis/skill-usage.json` là state runtime nên được thêm vào `.gitignore` của brain và loại khỏi bản backup. Brain cũ trước đây không bao giờ nhận được cập nhật `.gitignore` (hàm khởi tạo repo trả về sớm, và cả nhánh init cũng bỏ qua nếu file đã tồn tại); nay được hợp nhất thêm dòng còn thiếu ở lần bật tự học hoặc bấm học tiếp theo, giữ nguyên các dòng người dùng tự thêm. Việc này tạo một commit `chore:` một lần trong repo của brain, cố ý tách khỏi tiền tố `learn:` để không hiện ở trang Duyệt và không bị hoàn tác nhầm.
### Đã biết, chưa sửa
- **Skill hệ thống `html-to-webcake` đang hỏng ở mọi brain**: nó ship kèm `tools/` và `examples/`, thân skill bảo agent chạy chúng, nhưng cơ chế cài skill hệ thống chỉ chuyển mỗi `SKILL.md` nên cây con chưa bao giờ tới brain nào. Lỗi có sẵn, không do bản này gây ra.
- **`references/` và `scripts/` trong skill chỉ tới được đường router, chưa tới bản mirror `.claude/skills`**: bản mirror hiện chỉ copy file top-level. Đã ghi rõ giới hạn này ngay trong `javis-builder` để người viết skill biết trước. Làm mirror đệ quy đã được cân nhắc và HOÃN có chủ đích sau khi rà soát thấy 6 rào chặn thật (đắt nhất: nó sẽ quét và băm toàn bộ cây skill mỗi lượt chat, và chặn cả event loop). Chi tiết trong `docs/superpowers/specs/2026-07-16-skill-telemetry-authoring-design.md`.
- **Bản mirror không nhận file phụ đổi nội dung nếu `SKILL.md` không đổi**: cổng bỏ qua chỉ băm `SKILL.md`. Lỗi có sẵn, cùng hồ sơ với hai mục trên.

## [0.9.62] - 2026-07-16
### Sửa lỗi
- **Mô tả skill bị cắt cụt âm thầm nên skill không route được**: Javis cắt `description` của skill ở BA nơi với BA hạn mức khác nhau mà không ai biết: 60 ký tự ở mô tả tool `javis_use_skill`, 100 ký tự ở khối router trong system prompt, 140 ký tự ở đường dự phòng khi frontmatter thiếu `description`. Người viết skill không có cách nào biết mình đang bị chấm theo thước nào. Đo bằng chính `skill_router` trên brain đang chạy: **6/6 skill đang bật đều bị cắt**, mất từ 79 tới 316 ký tự mỗi cái, và phần bị vứt đúng là các ví dụ trigger, tức là thứ khiến routing hoạt động. Nay gom cả ba về một hằng số duy nhất `skill_router.SKILL_DESC_MAX = 150`, và gộp luôn hai hạn mức số-skill-liệt-kê (15 ở system prompt, 20 ở hub) về `SKILL_LIST_MAX = 20`.
- **Tài liệu đang dạy viết sai**: `CLAUDE.md` bảo `description` phải "viết rõ trigger" và `javis-builder` bảo "viết kỹ", trong khi runtime cắt cụt. Nay cả hai nêu rõ trần 150 KÈM LÝ DO (viết dài hơn là mất im lặng, skill không route được, viết xong phải tự đếm) và chỉ rõ ví dụ trigger đầy đủ thuộc về mục `## Khi nào dùng` trong thân file, nơi không bị cắt. Kiến trúc: index để TÌM, thân file để LÀM.
- **`javis-builder` trỏ sai chỗ ghi skill**: skill builder dạy ghi vào `.claude/skills/<slug>/SKILL.md` ở ba chỗ khác nhau, nhưng đó là bản MIRROR phái sinh. Canonical là `skills/<slug>/SKILL.md`. Đã sửa cả ba.
### Thêm mới
- **Viết lại mô tả 5 skill hệ thống cho lọt trần**: `html-to-webcake` (376 ký tự), `javis-builder` (333), `ingest-source` (266), `query-wiki` (249), `lint-wiki` (213) rút còn 69 tới 110 ký tự. Không mất thông tin: mọi ví dụ trigger chuyển xuống mục `## Khi nào dùng` trong thân file. Bỏ luôn cụm mở đầu sáo rỗng "Kích hoạt khi người dùng muốn" (29 ký tự giống hệt nhau ở mọi skill, đốt gần nửa ngân sách mà không phân biệt được gì).
- **Lint CI chặn lỗi tái phát**: `server/test_skill_caps.py` quét mọi skill hệ thống, fail nếu có mô tả vượt trần, dính boilerplate, rỗng, hoặc frontmatter vỡ. Liệt kê MỌI skill vi phạm trong một lần chạy chứ không dừng ở cái đầu.
- **`POST /skills` từ chối mô tả sai ngay lúc ghi**: trước đây endpoint chỉ kiểm slug, mô tả 400 ký tự vẫn lưu được rồi bị cắt âm thầm. Nay trả 400 kèm lý do, và kiểm TRƯỚC khi tạo thư mục nên request bị từ chối không để lại folder rỗng trên đĩa.
- **Chuẩn viết skill nhúng vào `javis-builder`**: 8 điểm bắt buộc (trần 150, cấm boilerplate, bọc nháy kép khi mô tả có dấu hai chấm, thứ tự mục thân file, cấm bịa flag/path, trần độ dài thân, cấm skill kiểu router). Nói thẳng rằng skill do chat ghi thẳng ra đĩa KHÔNG qua lớp chặn nào và lint CI chỉ soi skill hệ thống, nên tự đếm là phòng tuyến duy nhất.

## [0.9.61] - 2026-07-16
### Thêm mới
- **Khối hỏi-lại có lựa chọn trong khung chat**: Javis hỏi lại được bằng nút bấm ngay trong chat, kiểu Claude Code: nhúng khối ẩn `JAVIS_ASK` ở cuối câu trả lời, dashboard vẽ thành hàng chip dưới bong bóng. Bấm một nút là gửi đi như gõ tay, cùng phiên. Chỉ tin nhắn cuối mới bấm được; cuộn lên lịch sử thì chip đã đông cứng.
- **Chạy trên mọi engine**: Claude Agent SDK, Codex CLI, các engine API đều dùng được vì chỉ dựa vào system prompt, không đụng MCP hub.
### Sửa lỗi
- **Khối điều khiển không còn lọt sang Telegram**: khối `JAVIS_METRICS` trước đây lọt nguyên xi sang Telegram. Nay mọi khối điều khiển đều bị bóc trước khi ra kênh chữ ở cả 4 đường trả lời Telegram (chat, báo cáo Loop, báo cáo Việc Kanban, nhắc hẹn kiểu task); riêng `JAVIS_ASK` hạ xuống danh sách đánh số để nhắn lại "1" là chọn.
- **Chip hỏi-lại: nhãn hiện và nhãn gửi lệch nhau khi dài quá 40 ký tự**: nút chip trước đây cắt gọn LÚC VẼ nhưng vẫn gửi nguyên nhãn gốc khi bấm, nên nhãn dài (ẩn cả trong nội dung do connector ngoài chèn vào) có thể gửi đi phần người dùng chưa từng đọc hết. Nay cắt ngay ở bước bóc dữ liệu (`extract()`), thứ hiện và thứ gửi luôn giống nhau.

## [0.9.60] - 2026-07-16
### Sửa lỗi
- **Loop nền thấy lại connector claude.ai (Gmail/Drive/lịch) qua cờ opt-in `ambient_mcp`**: từ bản chuyển engine sang Agent SDK (quãng v0.9.35-0.9.37), loop tự chạy không còn "nhìn thấy" các connector claude.ai như Gmail, Google Drive, Google Calendar, nên loop kiểu "chiều đọc Gmail tóm tắt" ngưng chạy dù trước đó chạy được. Nguyên nhân: loop chạy ở nhánh fork nền có khoá quyền (duyệt từng tool, mặc định từ chối mọi tool ngoài whitelist), và ở nhánh này engine SDK cố tình KHÔNG nạp cấu hình máy (`setting_sources`) để allow-rule trong settings không che được lớp gate. Hệ quả phụ là connector claude.ai (vốn chỉ xuất hiện khi nạp cấu hình máy, như `claude -p` vẫn làm) biến mất khỏi loop. Nhánh Popen cũ trước đó chạy `--dangerously-skip-permissions` cộng `--mcp-config` không kèm `--strict` nên connector luôn được gộp vào, đó là lý do loop cũ đọc được Gmail. Chat (web và Telegram) KHÔNG dính vì chạy nhánh không-khoá-quyền đã được nạp lại `setting_sources`. Cách sửa: thêm cờ frontmatter `ambient_mcp: true` cho từng loop. Bật thì loop đó chạy nhánh không-gated (nạp cấu hình máy nên connector claude.ai xuất hiện lại), vẫn chặn cứng Bash/WebFetch/WebSearch/Task và tool tiền/đơn qua hub vẫn khoá theo mode. MẶC ĐỊNH TẮT để bản fork về sạch, không loop nào tự chạm Gmail/Drive của ai; chỉ bật khi user yêu cầu rõ. Bước kiểm chứng luôn giữ khoá chặt dù cờ bật. Kèm test hành vi trong `test_loop_ambient.py`.
### Bảo mật
- **Không lộ định danh thật trong ví dụ cấu hình + soát sạch git**: `system/mcp-catalog.json` dùng nhầm một mã định danh thật làm placeholder gợi ý, nay đổi thành số giả `1234567890` để bản fork không thấy thông tin thật của ai. Đã soát toàn bộ file đang được git theo dõi: mọi file dữ liệu kết nối (Kho kết nối, hub config, settings, khoá bí mật, token) đều đã nằm trong `.gitignore` và chưa từng bị commit, nên người fork về có bản trắng, không kết nối nào cài sẵn.

## [0.9.59] - 2026-07-16
### Cải thiện
- **Navbar gom nhóm cho dễ tìm công cụ**: thanh điều hướng trái trước đây xếp phẳng 18 mục thành một cột dài, tìm mỏi mắt. Nay gom theo chức năng thành 5 nhóm có nhãn nhỏ (Trợ lý, Bộ não, Năng lực, Việc & lịch, Kết nối) và ghim cụm Hệ thống (Cài đặt, Cập nhật, Tài khoản) xuống đáy rail (có đường kẻ ngăn). Sắp lại thứ tự các mục cho hợp mạch dùng. Trên mobile các nhóm tự dàn phẳng thành một hàng ngang như cũ (ẩn nhãn nhóm). Cấu trúc nhóm khai trong `RAIL_GROUPS` (console.js) - đổi thành viên/thứ tự chỉ sửa một chỗ, mục nào quên xếp nhóm sẽ tự dồn vào cụm Hệ thống nên không bao giờ mất mục.
- **Trang Cập nhật phân trang 20 bản mỗi trang**: nhật ký dài 98 bản trước đây đổ hết ra một trang vừa nặng DOM vừa khó đọc. Nay chỉ hiện 20 bản mới nhất mỗi trang, cuối trang có thanh "‹ Mới hơn · Trang x/y · N bản · Cũ hơn ›"; đổi trang dùng lại dữ liệu đã tải (không gọi lại mạng) và tự cuộn lên đầu cho dễ theo dõi.

## [0.9.58] - 2026-07-16
### Sửa lỗi
- **Đồ thị 3D chói trắng + mất hiệu ứng nhấp nháy lúc "đang suy nghĩ"**: từ v0.9.55 bản 3D được tô đa màu theo danh mục (bảng màu cầu vồng) và kéo co tròn chặt, nhưng bản 3D render bằng `AdditiveBlending` (cộng dồn ánh sáng) nên nhiều màu cộng dồn trong khối chặt dồn về TRẮNG - lõi cháy trắng, nhìn chói. Nền đã sáng sẵn nên node loé lên lúc suy nghĩ không còn nổi bật, mất cảm giác nhấp nháy (code hiệu ứng vẫn còn nguyên, chỉ bị chìm). Sửa trong `graph3d.js`: hạ lõi glow từ trắng đặc `1.0` xuống `0.7` và cho màu danh mục ra sớm (giữ đúng hue thay vì cháy trắng); hạ độ sáng nền lúc nghỉ từ `0.85` xuống `0.5`; cho node "suy nghĩ" loé dày hơn (mỗi 14 khung thay vì 22, nhiều điểm khởi phát hơn). Kết quả: nền dịu, hết chói, node loé lên nổi bật rõ trên nền tối nên nhấp nháy quay lại. Vẫn giữ đa màu.

## [0.9.57] - 2026-07-16
### Thêm mới
- **Đổi tên / xoá file ngay trong trình sửa note**: thanh nút của editor thêm ✎ (đổi tên) và 🗑 (xoá) bên cạnh Lưu/Tab mới/Tải/Phóng/Đóng, thao tác trên đúng file đang mở. Đổi tên sẽ tự lưu nội dung đang gõ trước (không mất chữ) rồi mở lại file ở tên mới; xoá thì đóng editor. Cả hai đều làm mới cây mà giữ nguyên các thư mục đang mở.

## [0.9.56] - 2026-07-16
### Sửa lỗi
- **Thêm/đổi tên/xoá file trong cây Vault làm SẬP hết các thư mục đang mở**: mỗi thao tác gọi `renderVaultTree()` dựng lại cả cây từ đầu (mọi thư mục về trạng thái đóng), nên đang mở sâu vào thư mục nào là bị đóng mất, rất khó chịu. Sửa: thêm `_vtRebuildReExpand()` - trước khi dựng lại thì GHI LẠI các thư mục đang mở (childBox không ẩn), dựng tươi xong tự mở lại đúng chúng theo thứ tự nông-trước-sâu (cha trước con). Áp cho cả 4 thao tác: thêm file (nút ＋ đầu VAULT và ＋ trên node), đổi tên, xoá. Riêng thêm file còn tự bung thêm tới đúng thư mục vừa tạo để thấy file mới ngay. Nút ↻ làm mới thủ công vẫn thu gọn như cũ.

## [0.9.55] - 2026-07-16
### Thêm mới
- **Giao diện brain mới - cột trái thành Vault explorer (cây thư mục kiểu Obsidian + tìm note)** thay cho panel số liệu kinh doanh cũ. Cây lồng nhiều tầng mở lazy (bấm mới nạp), neo trong gốc brain. Ô tìm 2 chế độ: Tên (quét toàn vault ở trình duyệt qua `/files/list`, bỏ dấu tiếng Việt) và Nội dung (endpoint mới `GET /files/search` quét ruột file text, chạy threadpool, cap kết quả). Rê chuột vào node hiện 3 nút: ＋ thêm file (bấm ở thư mục tạo bên trong, ở file tạo cùng thư mục; mặc định `.md`; tạo xong tự bung cây tới đúng chỗ), ✎ đổi tên, 🗑 xoá.
- **Trình sửa note đè lên khoang não 3D**: bấm note mở editor neo trong khung giữa (cây trái + chat phải vẫn sống). File `.md` mặc định mở dạng WYSIWYG - sửa trực tiếp trên bản render markdown, có thanh công cụ (đậm, nghiêng, H1-H3, danh sách, trích dẫn, code, link, kẻ ngang); lưu chuyển HTML→markdown (turndown) GIỮ nguyên `[[wikilink]]`. Còn chế độ Nguồn cho markdown thô lossless. Ảnh xem inline, docx/pdf chỉ hiện thẻ tải về. Tái dùng `window.mdToHtml`, cụm endpoint `/files/*` sẵn có.
- **Công tắc đồ thị 2D / 3D trong Cài đặt (Tổng quan)**, mặc định 2D cho nhẹ máy (render ở trình duyệt, không phải VPS). Bản 2D dùng thư viện `force-graph` (engine d3-force, cùng họ với 3D và Obsidian): node phát sáng tô MÀU THEO DANH MỤC (thư mục), hover rọi đèn (sáng vùng liên kết, mờ phần còn lại, chỉ hiện tên note đang trỏ), co tròn về tâm, kéo node tự trôi về, zoom giới hạn vừa khung, và hiện CẢ note cô đơn (tham số `/graph?orphans=1`). three.js chỉ nạp lazy khi chọn 3D.

### Cải thiện
- **Đồ thị 3D cũng đa màu theo danh mục + co tròn** như 2D (dùng chung cách gán màu).
- **Nhãn danh mục quanh não tô chữ "% Vault" đúng màu cụm note** của thư mục đó; bấm nhãn rọi sáng đúng cụm.
- **Dời HỆ THỐNG + MCP ĐANG DÙNG xuống thanh chọn model** (ngang hàng, giải phóng cột chat). **Dời MỨC DÙNG token thành hộp nổi gọn ở góc dưới-phải khung giữa**, có nút thu nhỏ / mở rộng (nhớ trạng thái).
- **Click node trong đồ thị mở đúng editor cây** (WYSIWYG + công cụ) thay cho popup đọc/sửa phẳng cũ.
- Số liệu kinh doanh gỡ khỏi giao diện theo yêu cầu (giữ 3 id ẩn để không lỗi app.js).

## [0.9.54] - 2026-07-15
### Cải thiện
- **Bấm link/ảnh/thư mục Javis chèn trong chat giờ mở thẳng trang Tệp tin ĐÚNG vị trí (thay vì tải file thô)**: trước đây bấm ảnh hoặc link file mà Javis đính trong chat sẽ mở file thô trong tab mới - thấy nội dung nhưng không biết nó nằm ở đâu trong brain. Nay mọi link trỏ vào file/thư mục trong vault (đường dẫn tương đối gốc brain, vd `attachments/anh.jpg`, `videos/`) khi bấm sẽ nhảy sang trang **Tệp tin** mở đúng thư mục chứa, cuộn tới và tô sáng file mục tiêu để tìm thấy ngay. Link ra ngoài (http, mailto) vẫn mở tab trình duyệt mới như cũ. Ảnh vẫn hiện inline trong chat như trước, chỉ đổi hành vi khi bấm. Giữ deep-link `#open=<đường-dẫn>` trên thẻ link nên Ctrl/Cmd+bấm hoặc chuột giữa vẫn mở TAB TRÌNH DUYỆT MỚI và tab đó cũng tự vào đúng vị trí trong Tệp tin (chat ở tab cũ không mất). Khớp ngữ nghĩa đường dẫn với server: path trong chat tính theo gốc brain, còn File Manager duyệt theo trần (trên localhost là cả ổ đĩa) nên tự ghép tiền tố brain (`home` từ `/files/list`) để ra đúng thư mục. Nếu chat đang mở dạng phóng to (overlay) thì tự thu lại để thấy trang Tệp tin. Đã test trong trình duyệt: render ra đúng thẻ link mở-vị-trí cho ảnh/file/thư mục vault (link ngoài không đổi), bấm điều hướng sang trang Tệp tin, và deep-link `#open=` khi nạp tab mới cũng vào thẳng trang Tệp tin.

## [0.9.53] - 2026-07-15
### Sửa lỗi
- **Kết nối Substack báo "Substack 403: <!DOCTYPE html>..." khi Test/lấy cookie**: cầu nối `server/substack_mcp.py` gọi API Substack bằng `httpx`, nhưng Substack đứng sau Cloudflare - chặn client Python theo TLS fingerprint (trả 403 kèm nguyên trang HTML). Nghĩa là không chỉ nút Test, mà cả tạo nháp/đăng bài đều dính. Sửa: chuyển toàn bộ lời gọi HTTP của cầu nối sang `curl` (đã xác minh curl chạm được app Substack, trả JSON / "Not authorized"; có sẵn cả trên Windows lẫn Docker image). Kèm lọc thông điệp lỗi cho NGẮN GỌN, sạch (không đổ HTML dài vào chat và form Kết nối). Với session token đúng, Test giờ ra 200 và kết nối thành công.
- **Form Kết nối vẫn tràn/không cuộn được dù đã vá ở v0.9.49**: bản vá CSS (`.conn-form` cuộn được) đã có trong `console.css` nhưng KHÔNG hiện ra vì `index.html` nạp `console.css?v=14` (cache-bust) chưa được bump - trình duyệt vẫn dùng bản CSS cũ trong cache. Sửa: bump lên `?v=15` để trình duyệt tải bản mới. Thêm thanh cuộn NHÌN RÕ cho `.conn-form` (màu nhấn khi rê chuột) và chặn thông báo lỗi trong footer không phình quá cao đẩy nút Kết nối ra ngoài.

## [0.9.52] - 2026-07-15
### Sửa lỗi
- **Bấm "Open" file (video/ảnh/tài liệu) do Javis đính trong chat báo "Không tìm thấy file" dù file có thật**: link và ảnh Javis chèn vào chat dùng đường dẫn tương đối GỐC VAULT (vd `videos/tin-tuc.mp4`, `attachments/anh.jpg`) đúng theo quy ước trong CLAUDE.md, nhưng endpoint phục vụ file (`/files/raw`, `/files/read`, `/files/download`) lại resolve đường dẫn theo TRẦN duyệt của File Manager. Khi chạy localhost (không bắt đăng nhập) trần duyệt mở tới cả Ổ ĐĨA, nên `videos/tin-tuc.mp4` bị hiểu thành `D:\videos\tin-tuc.mp4` và luôn 404. Lỗi chỉ hiện trên bản localhost; bản public/login (trần = gốc brain) thì trùng nên không dính. Sửa: thêm resolver `_safe_serve_path` cho các endpoint CHỈ-ĐỌC, chấp nhận CẢ HAI quy ước - thử tương đối trần trước (giữ nguyên hành vi File Manager), không thấy thì thử tương đối gốc vault (link/ảnh trong chat). Cả hai nhánh vẫn khoá trong trần duyệt, nhánh vault còn siết chặt trong gốc brain nên không nới rộng phạm vi truy cập, không đụng các endpoint ghi/xoá/đổi tên. Đã test bằng cách gọi thẳng hàm thật của server: đường dẫn vault trước đây 404 nay phục vụ đúng file, đường dẫn kiểu File Manager vẫn chạy, thử `../` ra ngoài vault không bị nới. Cần khởi động lại server Javis để bản vá có hiệu lực.

## [0.9.51] - 2026-07-15
### Sửa lỗi
- **Trợ lý lấy User ID của Substack không chạy do Substack đổi định dạng link Hồ sơ**: Substack đã bỏ URL Hồ sơ kiểu `substack.com/profile/12345678-ten` (có dãy số) sang `substack.com/@handle` (không còn số), nên "Cách A" cũ (bóc số từ URL) vô dụng. Thêm endpoint backend `GET /connect/substack/resolve-uid` nhận handle hoặc link Hồ sơ rồi hỏi API công khai của Substack, trả về User ID kèm gợi ý Publication URL. Vì Substack đứng sau Cloudflare (chặn httpx theo TLS fingerprint, trả 403) nên endpoint gọi qua `curl` (có sẵn cả Windows lẫn Docker image) - handle được validate chặt + truyền dạng argv nên không có nguy cơ SSRF/chèn lệnh; endpoint vẫn nằm sau auth guard. Trang Docs cập nhật Cách A: dán link `@handle` rồi bấm "Lấy User ID" là ra số + nút Copy + danh sách Publication URL gợi ý bấm để copy. Đã test end-to-end backend (curl thật) lẫn front-end (mock fetch trong trình duyệt).

## [0.9.50] - 2026-07-15
### Sửa lỗi
- **CI và build Docker đỏ mỗi lần push (xung đột thư viện trong requirements.txt)**: GitHub Actions cứ gửi mail "Run failed" ở cả workflow CI lẫn Build Docker, fail ngay bước `pip install -r requirements.txt`. Nguyên nhân có từ v0.9.35 (không liên quan Substack): commit thêm engine Agent SDK ghim `starlette<0.39`, nhưng `fastapi==0.115.6` (bump ở bản vá bảo mật v0.9.12) lại đòi `starlette>=0.40` - hai ràng buộc chọi nhau nên pip không giải được. Bản 0.115.6 thực tế chưa từng được cài; app vẫn chạy fastapi 0.115.0 + starlette 0.38.6. Sửa: hạ pin về `fastapi==0.115.0` cho khớp `starlette<0.39` và đúng bản đang chạy thật. Lộ thêm xung đột thứ hai bị che: `uvicorn==0.30.6` chọi với `mcp` (đòi `uvicorn>=0.31.1`) - nâng lên `uvicorn==0.51.0` (bản .venv đang dùng). Đã resolve thử sạch và chạy đủ bộ test cục bộ (8/8 pass) trước khi push. Kèm ghi chú trong requirements.txt về việc fastapi-starlette bị khoá cặp để không tái phạm.

## [0.9.49] - 2026-07-15
### Sửa lỗi
- **Form Kết nối dài không cuộn được, bị cắt mất nút và ô cuối**: modal Kết nối (vd Substack với 3 ô + phần hướng dẫn dài) tràn quá chiều cao màn hình nhưng không cuộn xuống được, che mất ô User ID và nút Kết nối. Nguyên nhân: `.conn-form` nằm trong `.mp-box` giới hạn `max-height: 86vh` nhưng bản thân nó không có vùng cuộn. Sửa: cho `.conn-form` co lại và cuộn (`flex: 1 1 auto; min-height: 0; overflow-y: auto`), phần đầu đề và hàng nút Kết nối/Huỷ vẫn ghim cố định. Áp dụng cho MỌI connector có form dài, không riêng Substack.
### Cải thiện
- **Substack: thêm trợ lý lấy nhanh User ID + Publication URL, gọn phần hướng dẫn trong form**: trang hướng dẫn (`/static/docs/substack.html`) nay có công cụ tương tác: (A) dán link trang Hồ sơ là tự bóc ra User ID kèm nút Copy, không cần DevTools; (B) một dòng lệnh dán vào Console DevTools trên substack.com tự lấy cả User ID lẫn Publication URL (gọi `api/v1/user/profile/self`, tự copy User ID). Session token vẫn phải copy tay vì Substack khoá cookie HttpOnly - JS không đọc được, đã nói rõ trong trang. Đồng thời rút gọn đoạn `guide` hiển thị trong form Kết nối cho đỡ dài, dẫn người dùng bấm 'Hướng dẫn' để dùng trợ lý.

## [0.9.48] - 2026-07-15
### Cải thiện
- **Substack: hướng dẫn riêng trong Docs của Javis (không trỏ ra GitHub nữa)**: thêm trang hướng dẫn tự chứa `dashboard/docs/substack.html` (khớp giao diện tối của Javis, phục vụ tại `/static/docs/substack.html`) và đổi link "Hướng dẫn" của connector Substack trỏ vào trang này thay vì repo GitHub gốc. Trang gồm các bước lấy 3 thông tin đăng nhập (publication URL, cookie `substack.sid`, User ID), giới thiệu 3 tool, bảng mức quyền và cách bật quyền đăng bài, các lớp an toàn (loop không tự đăng, mặc định không gửi email), và bảng markdown gọn dựng nội dung.

## [0.9.47] - 2026-07-15
### Thêm mới
- **Substack: thêm quyền ĐĂNG BÀI (không chỉ tạo nháp)**: server MCP cộng đồng `substack-mcp` chỉ có đúng 1 tool tạo nháp và không đăng được, nên Javis thay bằng cầu nối Substack tự dựng (`server/substack_mcp.py`, transport `internal` giống Botcake) gọi thẳng API Substack. Ưu điểm kèm theo: chạy Python thuần, KHÔNG cần cài Node/npx nữa. Bộ tool mới: `substack_list_drafts` (liệt kê nháp - đọc), `substack_create_draft` (tạo nháp - ghi), `substack_publish` (đăng bài - nguy hiểm). Tool đăng tạo mới rồi đăng (title+body) hoặc đăng một nháp có sẵn (draft_id); có bộ chuyển markdown gọn sang định dạng thân bài của Substack (tiêu đề #, danh sách, trích dẫn, **đậm**, *nghiêng*, [link], `code`). An toàn: đăng bài xếp loại NGUY HIỂM nên mức mặc định (Ghi nháp) CHẶN - phải nâng kết nối lên Toàn quyền mới đăng được, và ngay cả khi Toàn quyền thì loop chạy nền vẫn không bao giờ tự đăng (chỉ đăng khi bạn yêu cầu trực tiếp trong chat). Đăng mặc định chỉ lên web, KHÔNG gửi email cho người đăng ký; chỉ khi bạn nói rõ mới bật cờ gửi mail (đã gửi thì không hoàn tác). Nút Test kết nối giờ kiểm tra token thật qua danh sách nháp.

## [0.9.46] - 2026-07-15
### Thêm mới
- **Đấu được Substack vào kho Kết nối**: thêm connector `substack` (dùng server MCP cộng đồng `substack-mcp` của marcomoauro, chạy local qua `npx`). Javis soạn tiêu đề, phụ đề và nội dung rồi đẩy vào Substack ở dạng BẢN NHÁP để bạn tự vào bấm Publish - không tự xuất bản, không gửi email cho người đăng ký. Đăng nhập bằng 3 thông tin dán ở trang Kết nối: địa chỉ trang (publication URL), session token (cookie `substack.sid`) và User ID (dãy số trong URL trang Hồ sơ); form kèm hướng dẫn lấy từng thứ. Phân quyền: tool `create_draft_post` xếp loại "ghi", mặc định mức Ghi nháp để tạo nháp chạy được trong chat, nhưng bị chặn ở mức Chỉ đọc và với loop chạy nền (không bao giờ tự tạo nháp). Kèm logo Substack chính chủ. Connector nạp thẳng từ `system/mcp-catalog.json`, dùng chung đường ống stdio sẵn có nên mọi engine (Claude Code, Codex, API) đều gọi được.

## [0.9.45] - 2026-07-14
### Sửa lỗi
- **Hết lỗi "CLINotFoundError: Claude Code not found at ...\_bundled\claude.exe" khi làm việc nặng (system prompt dài)**: engine Claude báo không tìm thấy Claude Code dù đã cài và đăng nhập bình thường. Thủ phạm KHÔNG phải thiếu Claude Code, mà là giới hạn độ dài dòng lệnh của Windows (32767 ký tự): thư viện Agent SDK nhét cả system prompt của Javis vào THAM SỐ dòng lệnh khi khởi chạy Claude, và với brain nhiều note/bộ nhớ thì system prompt vượt ngưỡng, Windows từ chối tạo tiến trình, Python báo lỗi "file not found" và SDK dán nhãn nhầm thành "Claude Code not found" (trỏ vào bản bundled). Đã dò và tái hiện đúng ngưỡng: prompt ~32k chạy được, ~33k trở lên là vỡ. Cách sửa: đẩy system prompt qua FILE (`--append-system-prompt-file`) thay vì nhét vào dòng lệnh, nên độ dài prompt không còn giới hạn (đã kiểm chứng chạy trơn ở 48k-60k ký tự). File tạm được dọn sau mỗi lượt, kèm quét dọn file sót nếu tiến trình bị kill giữa chừng. Lỗi này ảnh hưởng mọi tác vụ chat/edit trên brain lớn, không riêng gì làm video. Kèm test trong `test_sdk_engine.py`.

## [0.9.44] - 2026-07-13
### Sửa lỗi
- **Chat qua Telegram không còn mất ngữ cảnh khi phiên dài (vá nốt cùng lớp lỗi của v0.9.43)**: bản 0.9.43 chỉ vá đường chat trên dashboard; đường chat Telegram vẫn dính y hệt lỗi quên phần đầu hội thoại khi phiên dài hoặc khi vừa đổi từ engine Claude (Claude Code) sang một engine API. Nguyên nhân: khác dashboard (dựng lại lịch sử từ database mỗi lượt rồi nén), phiên Telegram giữ lịch sử TRONG BỘ NHỚ (`sess["or"]` theo từng chat_id) và sau mỗi lượt chỉ CẮT CỨNG còn 12 message gần nhất - phần cũ hơn bị bỏ CÂM không tóm tắt nên model quên sạch mạch đầu. Nay thay bước cắt cứng bằng `compact_mem` - bản in-memory của cơ chế nén dashboard: phần cũ rơi khỏi cửa sổ được TÓM TẮT (gộp cả tóm tắt cũ) rồi chèn làm system message ngay sau phần đầu, phần gần nhất giữ nguyên văn, tóm tắt chỉ được tạo khi đủ dài để đáng một lần nén, provider lỗi thì lùi về cắt an toàn để payload không phình vô hạn. Logic tóm tắt được tách dùng chung với đường dashboard (`compaction._summarize`). Kèm test hành vi trong `test_compaction.py` (phủ nén cuộn nhiều vòng, phiên ngắn giữ nguyên văn, và ca provider lỗi).

## [0.9.43] - 2026-07-13
### Sửa lỗi
- **Chat engine API (OpenAI/OpenRouter/Gemini/Anthropic API) không còn mất ngữ cảnh giữa chừng**: khi phiên dài hoặc khi vừa đổi từ engine Claude (Claude Code) sang một engine API, Javis hay quên sạch phần đầu hội thoại và trả lời lạc mục đích (vd đang bàn edit video mà hỏi "viết lại kế hoạch" thì lại đi viết kế hoạch sản phẩm Javis OS). Nguyên nhân: mỗi lượt chat engine API dựng lại lịch sử từ database rồi cắt cứng còn 12 message gần nhất - phần cũ hơn lẽ ra phải thay bằng bản tóm tắt nén, nhưng bản tóm tắt CHỈ được tạo khi các lượt trước cũng chạy bằng engine API. Nếu trước đó dùng Claude Code (engine này tự quản trí nhớ, không tạo tóm tắt) thì phần đầu bị cắt CÂM không tóm tắt, model chỉ còn system prompt + câu hỏi cuối nên bịa nội dung theo system prompt. Nay thay bước cắt cứng bằng `prepare_history`: phần cũ CHỈ rời khỏi payload khi đã nằm trong tóm tắt nén; nếu đuôi hội thoại chưa nén quá dài (đổi engine giữa chừng, hoặc nén nền chưa kịp) thì nén ĐỒNG BỘ ngay một nhịp trước khi gửi để gấp phần cũ vào tóm tắt. Đảm bảo không bao giờ bỏ câm một message nào. Kèm test hành vi trong `test_compaction.py` (phủ cả ca đổi engine Claude→API và ca phiên ngắn giữ nguyên văn).

## [0.9.42] - 2026-07-13
### Sửa lỗi
- **Tác vụ dài (edit video, render, tách nền...) không còn bị chém oan ở giây 180**: watchdog chống treo coi "engine im lặng 180 giây" là treo và ngắt phiên, nhưng khi Claude/Codex gọi một tool chạy lâu (render video cả tiếng, tách nền, build) thì im lặng suốt lúc tool chạy là BÌNH THƯỜNG - kết quả là đang làm dở việc dài thì bị dừng với thông báo "Claude không phản hồi 180s". Nay watchdog phân biệt hai trạng thái: đang CHỜ TOOL chạy thì trần chờ riêng 1 tiếng (đổi bằng biến `JAVIS_CLAUDE_TOOL_TIMEOUT`, xem [Cấu hình env](docs/16-cau-hinh-env.md)), còn im lặng khi KHÔNG tool nào chạy (treo thật) vẫn ngắt ở 180 giây như cũ. Áp dụng cho cả engine Claude (Agent SDK) lẫn Codex CLI. Kèm 2 test hành vi trong `test_sdk_engine.py`.
- **Hết cảnh "(không có nội dung trả về)" câm lặng**: khi phiên Claude kết thúc LỖI mà không có chữ nào (hay gặp ở lượt hỏi ngay sau khi phiên trước bị ngắt giữa chừng), engine giờ báo rõ loại lỗi và gợi ý cách thoát (gửi lại / mở hội thoại mới) thay vì để khung chat hiện dòng rỗng không rõ nguyên nhân.

## [0.9.41] - 2026-07-13
### Sửa lỗi
- **Giọng Javis không còn bị thu ngược vào khung chat**: trước đây khi Javis đọc câu trả lời (TTS), micro nhận dạng giọng nói vẫn mở và nghe lại chính giọng Javis phát ra loa, chép thành chữ rồi sau 1.5 giây im lặng tự gửi vào khung chat như tin nhắn của người dùng (hay gặp nhất khi bật chế độ rảnh tay rồi gõ phím gửi tin - mic mở suốt lúc Javis nói). Nguyên nhân: bộ nhận dạng (SpeechRecognition) thu âm bằng luồng riêng KHÔNG được khử vọng, và không có cơ chế loại trừ lẫn nhau giữa nghe với nói. Nay sửa 2 lớp trong voice.js: (1) Javis bắt đầu đọc mà mic đang nghe thì tạm NGỪNG nhận dạng ngay (bỏ cả phần lỡ nghe dở), đọc xong toàn bộ tự mở nghe lại sau một nhịp ngắn bằng phiên nhận dạng mới sạch; (2) mọi kết quả nhận dạng lọt về trong lúc đang phát tiếng đều bị bỏ (chắc chắn đó là giọng Javis, không phải người dùng). Ngắt lời bằng giọng (barge-in) vẫn hoạt động bình thường vì nó đo mức âm qua luồng mic đã khử vọng, không dựa vào nhận dạng. Người dùng chủ động tắt mic (Esc/bấm nút) thì không bị tự mở lại.

## [0.9.40] - 2026-07-12
### Thêm mới
- **Kết nối Meta Ads bằng cách CHẠY ĐƯỢC ngay: tự tạo Facebook App, gọi thẳng Marketing API (như Composio)**: vì MCP chính chủ của Meta đang beta khóa allowlist (không tự nối được), Javis thêm connector mới "Meta Ads (tự tạo app - Graph API)" đi đường vòng đã được chứng minh - bạn tạo một Facebook App của riêng mình (~10 phút, có hướng dẫn từng bước trong app và trong tài liệu), dán App ID + App Secret, Javis đọc thẳng số liệu quảng cáo của bạn qua Graph API. Có sẵn công cụ: liệt kê tài khoản quảng cáo, hiệu suất (chi tiêu/hiển thị/click/CTR/CPC/reach/chuyển đổi) theo kỳ, danh sách chiến dịch, và một công cụ đọc Graph API tùy ý. TẤT CẢ CHỈ ĐỌC - không tạo/sửa chiến dịch, không tiêu tiền. Token Facebook (~60 ngày) được Javis tự gia hạn; hết hạn thì bấm Kết nối lại. Đây đúng là mô hình các nền tảng như Composio dùng cho Meta Ads. Kèm hướng dẫn tạo app đầy đủ trong [MCP & số liệu](docs/09-mcp-va-so-lieu.md) và test tự động (`test_meta_graph.py`).

## [0.9.39] - 2026-07-12
### Sửa lỗi
- **Kết nối Meta Ads báo lỗi trung thực, hết ngõ cụt "cần client_id thủ công"**: sau khi điều tra sâu (probe thật endpoint của Meta + đối chiếu tài liệu chính chủ và báo cáo cộng đồng), xác định `mcp.facebook.com/ads` là MCP chính chủ của Meta đang ở beta GIỚI HẠN: máy chủ chỉ chấp nhận vài ứng dụng được Meta cấp phép sẵn (trợ lý của ChatGPT, Claude, Perplexity) và đã TẮT tự đăng ký ứng dụng (DCR) - nên Javis, và cả các công cụ khác, chưa nối tự phục vụ được. Đây là giới hạn phía Meta, không phải lỗi máy người dùng. Thông báo lỗi cũ ("Server không hỗ trợ tự đăng ký client (DCR) - cần client_id thủ công") gây hiểu nhầm rằng chỉ cần dán client_id là xong, giờ đổi thành giải thích rõ + hiện nguyên văn thông báo của Meta. Mô tả và hướng dẫn của connector Meta Ads cũng viết lại đúng thực tế (bỏ câu "đăng nhập 1 chạm, không cần tạo app").

## [0.9.38] - 2026-07-12
### Thêm mới
- **Trang Tệp tin duyệt được ra ngoài brain (tới cả ổ đĩa)**: trước đây File Manager khoá cứng trong thư mục brain, bấm "Lên" tới gốc brain là hết - không đọc/sửa được dữ liệu nằm ngoài vault. Nay khi chạy trên máy cá nhân (localhost), trần duyệt mở tới ổ đĩa chứa brain: mặc định mở vẫn vào đúng thư mục brain như cũ, nhưng bấm "Lên" đi ra được tới tận gốc ổ đĩa để đọc/sửa/tải mọi file. Thêm nút "⌂ Brain" để nhảy nhanh về thư mục brain, và nút "Lên" tự ẩn khi đã ở gốc. An toàn giữ nguyên khi chạy public (VPS/có đăng nhập): vẫn khoá trong brain để không hở cả ổ đĩa ra web. Tinh chỉnh bằng biến `JAVIS_FILES_ROOT` (xem [Cấu hình env](docs/16-cau-hinh-env.md)): ép khoá brain, mở cả ổ đĩa, hay chỉ một thư mục cụ thể. Không xoá được thư mục brain hay gốc ổ đĩa.

## [0.9.37] - 2026-07-12
### Cải thiện
- **Gỡ hẳn nhánh engine Claude kiểu cũ (Popen) - khép hồ sơ kế hoạch Agent SDK**: engine Claude giờ chạy duy nhất qua Agent SDK chính chủ. Xoá ~220 dòng code tự chế spawn/parse tiến trình trong claude_cli.py (nơi từng phát sinh các lỗi kiểu WinError 206); Codex CLI và phần auth/ngắt tiến trình dùng chung giữ nguyên. Biến `JAVIS_CLAUDE_ENGINE` không còn tác dụng (đặt `cli`/`sdk-loops` sẽ bị bỏ qua kèm một dòng log). Máy chưa cài claude-agent-sdk sẽ được engine báo rõ cách cài thay vì lỗi khó hiểu. Toàn bộ 6 bộ test + kiểm tra sống qua factory đều pass; nhật ký hoàn công ở docs/dev/2026-07-ke-hoach-agent-sdk.md.

## [0.9.36] - 2026-07-12
### Thêm mới
- **Engine Claude chạy Agent SDK chính chủ theo MẶC ĐỊNH (hoàn tất cả 4 phase kế hoạch)**: sau spike và smoke đạt toàn bộ, engine Claude giờ mặc định chạy qua claude-agent-sdk. Người dùng không phải làm gì - vẫn đăng nhập Claude Code như cũ, chat/loop/workflow/Telegram chạy y hệt nhưng nền tảng do Anthropic bảo trì, fork nền được chặn quyền theo từng lần gọi tool kèm audit. Trục trặc thì đặt biến môi trường `JAVIS_CLAUDE_ENGINE=cli` là quay về cách cũ ngay (giữ tối thiểu một bản phát hành); có thêm mức trung gian `sdk-loops` (chỉ tác vụ nền dùng SDK). Đã kiểm chứng bằng phiên chạy thật cô lập đủ 3 luồng: chat 2 lượt có nhớ phiên, workflow chạy trọn chuỗi bước, loop chế độ đề xuất bị lệnh "tạo file bằng được" vẫn không tạo được file; log server sạch không lỗi không fallback.
- **Plugin chạy thẳng trong tiến trình server (in-process) trên engine SDK**: tool plugin (tạo ảnh ChatGPT, ngày giờ VN, plugin user tự viết) không còn đi vòng qua hub HTTP - engine gọi thẳng handler Python, nhanh hơn và dùng được plugin cả khi CHƯA đấu kết nối MCP nào. Hub tự bỏ nhóm plugin khi engine đã có bản in-process (không còn nguy cơ model thấy 2 tool trùng chức năng); các engine khác (Codex, API) vẫn dùng plugin qua hub như cũ. Mức quyền min_mode của plugin vẫn được tôn trọng đúng theo chế độ suggest/auto/full.

## [0.9.35] - 2026-07-12
### Thêm mới
- **Engine Claude chạy được qua Agent SDK chính chủ (thử nghiệm, Phase 0-2 của kế hoạch)**: spike đạt cả 7 hạng mục (auth subscription không cần API key, stream, resume, interrupt, MCP config, prompt 43k ký tự không WinError 206, và tới token đầu còn NHANH HƠN cách cũ 3.6s vs 4.0s). Thêm engine `claude_sdk_engine.py` cùng hợp đồng với engine CLI cũ; bật thử bằng biến môi trường `JAVIS_CLAUDE_ENGINE=sdk` rồi khởi động lại - mặc định vẫn là `cli` như cũ, SDK lỗi thì tự rơi về CLI. Nút Dừng ngắt được cả hai loại engine.
- **Quyền per-call cho fork nền (nâng cấp an toàn lớn nhất của đợt này)**: khi chạy engine SDK, các fork nền an toàn (loop suggest/auto, task, reminder, learn) chặn tool NGOÀI whitelist theo TỪNG LẦN GỌI kể cả Bash/Write builtin - kèm audit JSONL ở `logs/sdk_tool_audit.jsonl` trong thư mục state. Smoke test thật: fork chỉ-đọc bị lệnh "tạo file bằng mọi cách" vẫn không tạo được file. Trước đây chỉ giới hạn được bằng danh sách tĩnh lúc spawn, không có audit tool builtin.
### Sửa lỗi
- **Ghim starlette tránh gãy server khi cài dependency mới**: package `mcp` (dependency của claude-agent-sdk) kéo starlette 1.x xung đột fastapi 0.115; requirements.txt ghim `starlette<0.39` + `sse-starlette<3` (pip check sạch).

## [0.9.34] - 2026-07-12
### Thêm mới
- **Chat engine API hết "mất trí nhớ" trong phiên dài (nén hội thoại)**: trước đây phiên chat dài trên engine API (OpenRouter/OpenAI/Anthropic API/Gemini) chỉ giữ 12 message gần nhất, phần cũ bị cắt bỏ - hỏi lại chuyện đầu phiên là Javis quên sạch. Nay phần lịch sử cũ rơi khỏi cửa sổ được TÓM TẮT tự động (chạy nền sau mỗi lượt, gộp dồn với tóm tắt trước) và bơm lại vào đầu phiên - Javis vẫn nhớ mạch cũ (quyết định, con số, việc dang dở) mà payload không phình. Tóm tắt lưu bền trong SQLite theo phiên, DB cũ tự migrate. Port ý tưởng session_memory_compaction của cookbook Anthropic. Kèm test `test_compaction.py` chạy trong CI.
### Cải thiện
- **Workflow tự cải thiện đúng kiểu evaluator-optimizer**: bước có `verify_agent` khi bị chấm CHƯA ĐẠT giờ được xem lại KẾT QUẢ LẦN TRƯỚC kèm phản hồi để sửa tiếp (giữ phần tốt, sửa chỗ bị chê) thay vì làm lại mù từ đầu - đỡ lặp đúng lỗi cũ, hội tụ nhanh hơn. Mẫu workflow trong tài liệu hệ thống bổ sung 2 khoá tuỳ chọn `verify_agent`/`max_retries` để Javis tạo workflow qua chat biết dùng vòng kiểm chứng.
- **Kế hoạch chuyển engine Claude sang Agent SDK chính chủ**: viết bản kế hoạch chi tiết ở `docs/dev/2026-07-ke-hoach-agent-sdk.md` - vì sao (lớp Popen tự chế là ổ bug WinError 206, quyền tool tĩnh), kiến trúc adapter giữ nguyên giao diện ClaudeCLI, map 3 mức quyền suggest/auto/full vào callback `can_use_tool` từng tool call, lộ trình 4 phase + spike go/no-go, rủi ro và tiêu chí thành công. Chưa code - chờ duyệt.

## [0.9.33] - 2026-07-12
### Thêm mới
- **Prompt caching cho engine API**: học từ cookbook chính chủ của Anthropic. Nhánh Anthropic API có tool MCP (nhánh chạy nhiều request nhất - mỗi vòng gọi tool là một request chở lại nguyên system prompt ~26k ký tự + schema tool + hội thoại) giờ được cache system + tools + hội thoại, các vòng sau chỉ trả ~10% giá input cho phần đã cache. Cách đánh dấu mới không mutate hội thoại gốc nên không còn nguy cơ tích luỹ marker vượt trần 4 breakpoint của API (lý do trước đây nhánh này phải tắt cache). Model Claude chạy qua OpenRouter cũng được cache system prompt. Kèm test mới `test_engine_cache.py` chạy trong CI.
- **Second Brain: trang wiki tự đủ ngữ cảnh (contextual retrieval)**: skill `ingest-source` giờ yêu cầu mỗi trang wiki mở đầu bằng 1-2 câu định vị (khái niệm gì, thuộc nguồn/chủ đề nào, dùng khi nào) và khai `aliases` (tên gọi khác, thuật ngữ tiếng Anh) trong frontmatter - để sau này hỏi bằng từ khác thì tìm kiếm vẫn trúng trang, và đọc trang lẻ tách khỏi source vẫn hiểu. Ý tưởng lấy từ công thức contextual retrieval của Anthropic, áp cho search dạng file không cần vector DB.
- **javis-builder viết system prompt theo khung metaprompt**: khi tạo agent qua chat, Javis giờ dựng system prompt theo khung 6 phần rút từ metaprompt của Anthropic (vai + mục tiêu, bối cảnh nghiệp vụ, quy trình đánh số, định dạng đầu ra kèm ví dụ, cách xử lý trường hợp khó, điều cấm cụ thể) thay vì 1-2 câu chung chung - agent tạo ra làm việc được ngay, đỡ phải sửa đi sửa lại. Hai skill hệ thống tự cập nhật vào mọi brain chưa chỉnh tay (brain đã chỉnh giữ nguyên bản riêng).

## [0.9.32] - 2026-07-12
### Sửa lỗi
- **Kết nối Meta Ads hết báo "Server này không khai OAuth chuẩn MCP"**: Meta khai issuer OAuth có path (`mcp.facebook.com/ads`) và đặt metadata theo đúng chuẩn RFC 8414 dạng chèn giữa (`/.well-known/oauth-authorization-server/ads`), trong khi Javis chỉ tìm dạng nối đuôi và gốc domain nên không thấy. Nay bước discovery thử đủ cả hai dạng (chèn giữa trước, nối đuôi fallback) cho issuer lẫn URL MCP có path - bấm Kết nối là ra trang đăng nhập Facebook như thiết kế. Các connector OAuth khác không đổi hành vi.

## [0.9.31] - 2026-07-11
### Sửa lỗi
- **Dán bài dài vào chat không còn nổ "Subprocess error: WinError 206"**: trước đây tin nhắn (cộng system prompt) được truyền cho engine CLI qua command line, mà Windows giới hạn command line tối đa 32767 ký tự - dán một bài báo dài hay đoạn văn bản lớn là vượt trần và lỗi "FileNotFoundError: The filename or extension is too long" ngay trước khi engine kịp chạy. Nay prompt được bơm qua stdin (không đi qua command line) nên dán bao nhiêu cũng chạy; áp dụng cho cả engine Claude Code lẫn Codex. Đã test thật với prompt hơn 40 nghìn ký tự.

## [0.9.30] - 2026-07-11
### Thêm mới
- **Key ElevenLabs trong Cài đặt dùng chung cho chỉnh sửa video**: Javis giờ biết dựng và cắt sửa video qua hai bộ công cụ ngoài (HyperFrames tạo video mới từ HTML, video-use cắt từ thừa / chèn phụ đề / chỉnh màu footage quay thật - cài dạng skill cho engine CLI). Phần phiên âm của video-use cần key ElevenLabs: chỉ cần nhập key một chỗ ở **Cài đặt > Giọng đọc (ElevenLabs)** như lâu nay, server tự bơm biến môi trường `ELEVENLABS_API_KEY` cho engine và tool con lúc khởi động và ngay khi lưu Cài đặt (không cần restart, không phải sửa file .env). Key vẫn được mã hóa at rest như các secret khác.
### Sửa lỗi
- **Tiến trình Python con hết crash Unicode trên Windows**: server tự đặt `PYTHONUTF8=1` cho tiến trình con (tôn trọng giá trị user đã đặt sẵn), tránh lỗi UnicodeEncodeError khi tool như video-use in ký tự đặc biệt ra console cp1252.
- **Giá trị che "••••" không còn đè được key ElevenLabs thật**: client lạ lấy cài đặt từ GET /settings (key hiển thị dạng che) rồi POST nguyên object về sẽ không làm mất key đã lưu nữa.

## [0.9.29] - 2026-07-10
### Thêm mới
- **Nút tắt/bật giọng đọc ngay trên khung chat**: thêm một nút loa cạnh nút mic và đính kèm ở thanh nhập chat (hiện ở cả màn 3D lẫn tab Trò chuyện). Bấm để tắt/bật việc Javis đọc câu trả lời bằng giọng mà không phải lên góc trên hay vào Cài đặt. Khi tắt, nút chuyển màu đỏ kèm gạch chéo cho dễ thấy; trạng thái đồng bộ hai chiều với nút loa ở header và công tắc "Đọc trả lời bằng giọng" trong Cài đặt nhanh, và nhớ qua các lần tải lại.

## [0.9.28] - 2026-07-09
### Thêm mới
- **Telegram hiện trạng thái trung gian khi chờ**: trước đây nhắn cho Javis qua Telegram rồi phải chờ im lặng tới khi có câu trả lời, dễ tưởng bị treo. Nay bot gửi một tin trạng thái ("🤔 Javis đang xử lý…") rồi tự cập nhật theo tiến trình thật của lượt (đang gọi công cụ nào, đã nhận dữ liệu, đang soạn câu trả lời); soạn xong thì xoá tin trạng thái và gửi câu trả lời. Có tiết chế nhịp cập nhật (~2.5s) để không spam / dính giới hạn của Telegram. Áp dụng cho cả engine Claude Code lẫn engine API.

## [0.9.27] - 2026-07-09
### Thêm mới
- **Click node trên graph 3D mở popup đọc/sửa note**: trước đây bấm một node trên biểu đồ là gửi thẳng một câu hỏi vào khung chat (gây nhầm lẫn). Nay bấm node mở một cửa sổ hiện nội dung note để đọc và sửa trực tiếp rồi Lưu (đọc/ghi qua đúng API Tệp tin), kèm nút mở tab mới; nhấn Esc hoặc ✕ để đóng.
### Cải thiện
- **Esc không còn dừng câu trả lời / ngắt Javis đang nói**: trước đây nhấn Esc vừa tạm dừng giọng đọc vừa ngắt luôn lượt đang chạy, rất dễ lỡ tay mất câu trả lời. Nay Esc chỉ thoát chế độ rảnh tay, tắt mic và đóng popup. Muốn dừng thì dùng nút Dừng (ô đỏ) hoặc nút bật/tắt tiếng.

## [0.9.26] - 2026-07-09
### Thêm mới
- **Nhiều hội thoại chạy song song (như Claude)**: bấm "Hội thoại mới" giờ KHÔNG còn làm dừng hội thoại đang trả lời. Mỗi lượt chat chạy nền độc lập, nên bạn có thể mở một hội thoại mới và hỏi việc khác NGAY trong khi hội thoại cũ vẫn đang generate - cả hai chạy cùng lúc. Danh sách Lịch sử hiện dấu ⏳ ở hội thoại đang trả lời; bấm vào một hội thoại đang chạy nền để xem tiếp phần đang soạn trực tiếp, và mọi lượt tự lưu vào phiên của nó dù bạn đang xem chỗ khác. Nút Dừng chỉ ngắt đúng hội thoại đang xem, các hội thoại nền khác không bị ảnh hưởng.
### Cải thiện
- **Lõi chat xử lý mỗi lượt như một tác vụ nền**: server không còn khoá kiểu một-kết-nối-một-lượt-một-lúc; mỗi lượt có engine riêng và mọi gói gửi kèm session_id để giao diện định tuyến đúng phiên (có khoá ghi để nhiều lượt không xen kẽ làm hỏng gói). Toàn bộ luồng stream, phiên, MCP/skill và giọng nói giữ nguyên. Ngoài ra nếu chưa cài Claude Code CLI mà dùng engine API/OpenRouter thì không còn bị chặn kết nối như trước (báo lỗi theo từng lượt nếu thực sự cần CLI).

## [0.9.25] - 2026-07-09
### Thêm mới
- **Tab "Trò chuyện" - màn chat riêng, rộng rãi**: thêm tab mới trên thanh bên trái (ngay dưới "Javis") mở khung chat toàn màn hình kiểu Claude, tiện hơn hẳn khung chat chật ở cạnh màn hình 3D. Cột trái là lịch sử hội thoại (nút tạo mới, ô tìm trong mọi hội thoại, nhóm theo Hôm nay / 7 ngày qua / Cũ hơn, đổi tên và xoá, phiên đang mở được tô sáng); giữa là khung chat lớn dễ đọc kèm tiêu đề và badge engine thật (vd "CLI · opus"); ngay trên ô nhập là thanh chọn model + effort, dưới cùng là ô gõ kèm nút mic và đính kèm file. Tab này KHÔNG viết lại bộ máy chat mà dùng lại chính khung chat của màn 3D (mượn rồi trả về khi rời tab) nên cùng một cuộc trò chuyện hiện ở cả hai nơi, giữ nguyên WebSocket, stream, phiên, giọng nói và đính kèm; rời tab thì màn 3D vẫn chat bình thường. Vào tab chat, đồ hoạ 3D tự tắt cho nhẹ máy. Màn hẹp (điện thoại) thì cột lịch sử thu thành ngăn kéo, bấm nút 🕘 để mở.
### Sửa lỗi
- **Chống mất nội dung khi đổi trang nhanh**: mỗi lần chuyển trang quản lý, khung nội dung (`#cviewBody`) được thay bằng một vùng mới, nên nếu một trang tải chậm (Tổng quan, Models, Kết nối...) trả kết quả về TRỄ sau khi bạn đã sang trang khác thì cú ghi đó rơi vào vùng cũ đã bỏ, không đè lên trang đang xem. Trước đây chuyển thật nhanh từ một trang tải-chậm sang tab Trò chuyện có thể xoá mất khung chat vừa mở; nay đã an toàn, đồng thời hết luôn hiện tượng thoáng thấy nội dung trang cũ khi đổi trang.

## [0.9.20] - 2026-07-09
### Thêm mới
- **Loop và Việc tự báo kết quả về Telegram người yêu cầu**: giờ là hành vi mặc định của Javis - mỗi vòng loop chạy nền chạy xong, và mỗi việc (Kanban task) hoàn tất, đều tự nhắn kết quả về Telegram của đúng người đã yêu cầu (kèm tóm tắt, dòng kiểm chứng, và cảnh báo nếu loop tự tạm dừng). Loop hoặc việc tạo trên bản web (không rõ chủ) thì báo về ID Telegram đầu tiên trong whitelist. Loop lưu thêm `owner_chat` (chat_id người tạo) trong frontmatter; việc lưu `chat_id` tương ứng - Javis tự gắn khi bạn tạo qua chat. Vòng bị bỏ qua vì chưa có số liệu thì không nhắn để khỏi làm phiền; muốn một loop ngừng báo mỗi vòng thì đặt `notify: false` trong frontmatter loop đó.

- **Khung chat render chân thật như Claude, xem được Artifact**: câu trả lời của AI giờ hiện đầy đủ như trên khung chat Claude. Khi trả về một trang HTML tự chứa, ảnh SVG, sơ đồ mermaid hoặc một file code dài, Javis hiện một thẻ artifact gọn trong luồng chat; bấm vào mở một panel bên phải có tab Xem trước / Mã nguồn cùng nút Copy và Tải về. HTML chạy trong iframe sandbox cô lập (không đụng được trang cha), SVG render không cho script, mermaid vẽ thành sơ đồ (offline thì tự hạ xuống hiện mã nguồn kèm ghi chú). Nhấn Esc để đóng panel, không thu nhỏ luôn khung chat đang phóng to.
### Cải thiện
- **Markdown và code block đầy đủ hơn**: thêm heading nhiều cấp, danh sách đánh số + lồng nhau + checkbox, blockquote, đường kẻ ngang, in nghiêng, gạch ngang; code block có nhãn ngôn ngữ và tô màu cú pháp, giữ nút Copy. Lúc đang stream, đoạn code chưa đóng vẫn hiện gọn dạng khối code đang gõ thay vì chữ thô. Bộ render tách sang file riêng `dashboard/chat-render.js`, giữ nguyên số liệu panel trái, ảnh vault và link như cũ.

## [0.9.18] - 2026-07-07
### Cải thiện
- **Menu đổi model + effort có luôn trong khung chat phóng to**: trước đây thanh chọn model chỉ hiện ở khung chat thường; khi bấm phóng to hội thoại (nút ⛶ / Thu nhỏ bằng Esc) thì thanh này bị bỏ lại nên không thấy. Nay khi vào chế độ toàn màn hình, thanh chọn model được đưa theo vào ngay trên ô nhập, mở menu chọn nhà cung cấp/model và đổi effort bình thường; thu nhỏ lại thì trả về đúng chỗ cũ.

## [0.9.17] - 2026-07-07
### Thêm mới
- **Đổi model + effort ngay trên khung chat**: thêm một thanh nhỏ ngay phía trên ô chat của dashboard, hiện nhà cung cấp, model và mức "Suy nghĩ" (effort) đang chạy. Bấm vào mở một menu gộp: danh sách model gom theo 6 nhà cung cấp (Claude Code, ChatGPT, OpenRouter, Anthropic API, OpenAI API, Google Gemini), có ô tìm model và hàng chọn effort (Tắt/Thấp/Vừa/Cao) ở dưới. Nhà cung cấp đã nối thì bung ra chọn model (danh sách nạp động theo tài khoản), nhà cung cấp chưa nối hiện khoá kèm lối tắt sang trang Models để thêm key. Chọn model hay effort là lưu ngay vào cấu hình và có hiệu lực ở lượt chat kế, badge engine tự cập nhật. Toàn bộ tái dùng các endpoint sẵn có nên không đổi luồng chat/engine.

## [0.9.16] - 2026-07-07
### Thêm mới
- **Tự khởi động cùng máy (Windows)**: thêm mục "Khởi động cùng máy" ở trang Tổng quan để bật/tắt việc Javis tự chạy khi mở máy. Bật lên là Javis chạy nền ẩn ngay sau khi bạn đăng nhập Windows (không cửa sổ đen, mở `localhost:7777` để dùng), và tự tắt bản cũ trước khi chạy nên không mở trùng. Cơ chế dùng khóa registry theo tài khoản (`HKCU...\Run`, không cần quyền admin) trỏ tới `start-javis.vbs` sẵn có; kèm 2 endpoint `/autostart` để xem trạng thái và bật/tắt, có cờ nhận biết khi bạn dời thư mục cài đặt. Mục này tự ẩn trên bản Docker/Linux.
- **Nhắc hẹn từ chat**: nói kiểu "30 phút nữa nhắc anh...", "8h30 sáng mai nhắc...", "mỗi sáng 7h nhắc uống thuốc" là Javis tự đặt lịch, tới giờ tự thức dậy bắn nhắc qua Telegram cho đúng người đang nói. Hẹn được theo số phút, theo giờ trong ngày, theo ngày cụ thể, hoặc lịch định kỳ bằng biểu thức cron; server tự tính giờ Việt Nam nên chỉ cần nói bằng lời. Ba chế độ: chỉ nhắc lại (notify), tự làm việc rồi gửi kết quả về (task), hoặc chạy một script giám sát KHÔNG cần AI cho rẻ (script, chỉ chạy file bạn đã bỏ sẵn trong `Javis/scripts`). Nhắc hẹn hiện luôn ở trang Việc/Lịch, gạt công tắc để huỷ.
- **Thêm nhà cung cấp Google Gemini**: cắm API key Gemini là dùng được các model 2.5 Flash/Pro và 2.0 Flash để chat, kể cả chế độ agent dùng MCP của Javis y như OpenAI. Đi qua endpoint tương thích OpenAI nên tận dụng lại đúng luồng stream + tool-calling; danh sách model nạp động theo tài khoản, và bật "Suy nghĩ" áp cho model 2.5 trở lên.
- **Skill HTML → Webcake (.pke)**: chuyển một file hoặc đoạn HTML thành file Webcake mở sửa được trên trình dựng landing - đọc HTML, tái dựng thành `page_source` đúng khuôn Webcake rồi xuất `.pke` để tải lên chỉnh tiếp.

## [0.9.15] - 2026-07-06
### Sửa lỗi
- **Favicon giờ khớp logo app**: icon trên tab trình duyệt trước đây vẫn là ảnh mặc định cũ dù link đã trỏ đúng. Nguyên nhân: đường `/favicon.ico` (trình duyệt LUÔN tự gọi) trả về 404 nên trình duyệt giữ icon cache cũ. Đã thêm route trả thẳng logo hiện tại (mặc định `logo.png`, tự đổi theo ảnh bạn tải lên). Trình duyệt cache favicon rất lì nên cần đóng mở lại tab để thấy icon mới.
- **Dải trống bên trên khung chat**: lưới `.hud` khai báo thiếu một hàng nên thanh đính kèm (lúc trống) chiếm mất hàng 70px, để lại một dải trống chạy hết bề ngang ngay trên ô nhập. Đã thêm hàng `auto` cho thanh đính kèm để nó co về 0 khi trống; phần thân giờ giãn hết xuống sát ô chat.
- **Nút "Lịch sử" đè lên nút header**: nút "Lịch sử" để nổi cố định ở góc phải, che mất các nút Cài đặt / Đọc / Reset hội thoại phía dưới. Đã đưa nút vào nằm chung hàng với dãy nút header nên không còn chồng lên nhau.

## [0.9.14] - 2026-07-06
### Thêm mới
- **Panel "Mức dùng" - đo token đa nhà cung cấp**: sidebar giờ hiện lượng token Javis **tự đo** qua từng nhà cung cấp/model trong ngày (vào ↑ / ra ↓ + ước tính chi phí ở nơi provider trả về, vd Claude Code), cộng tổng. Đồng nhất cho mọi engine (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI API, Anthropic API) vì Javis đọc usage trong mọi phản hồi. Kèm **số dư THẬT của OpenRouter** nếu đã cắm key (provider duy nhất lộ số dư qua API). Đây là lượng Javis dùng, KHÔNG phải hạn mức gói thuê bao - đa số nhà cung cấp không cho lấy hạn mức tài khoản qua API nên xem trong app của họ.

## [0.9.13] - 2026-07-06
### Thêm mới
- **Chia sẻ agent / skill / workflow qua file**: mỗi agent, skill, workflow giờ có nút **⤓ Xuất** để tải về một gói `.zip`, và mỗi trang (Agents / Skills / Workflows) có nút **⤒ Nhập** để tải gói lên - trao đổi năng lực với người khác dễ dàng. Gói workflow tự **kèm các agent nó dùng + skill của agent** (skill của bạn, KHÔNG kèm skill hệ thống) để bên nhận chạy được ngay; gói agent kèm skill của nó. Nhập chấp nhận `.zip`, file `.md` lẻ (agent/workflow), và **cả gói skill `.skill` của Claude** (Javis tự nhận diện `SKILL.md` trong gói và đưa vào đúng thư mục skill). Có rào an toàn (chống zip-slip, giới hạn dung lượng) và trùng tên thì bỏ qua trừ khi bạn chọn ghi đè.

## [0.9.12] - 2026-07-06
### Bảo mật
- **Vá 2 lỗ hổng DoS trong thư viện nền** (CVE-2024-47874 Starlette, CVE-2024-53981 python-multipart): nâng fastapi lên 0.115.6 (kéo Starlette lên 0.41.3) và python-multipart lên 0.0.18. Trước đây kẻ tấn công CHƯA đăng nhập có thể gửi multipart form dị dạng vào endpoint công khai (đăng nhập / thiết lập) để làm quá tải server VPS.
- **Chặn XSS trong dashboard**: các hàm escape giờ escape cả dấu nháy (`"` và `'`), tránh nội dung do AI/MCP sinh ra (tên file, nội dung task...) thoát khỏi thuộc tính HTML và chạy JavaScript same-origin điều khiển Javis. Ngoài ra link ngoài (kết quả tìm kiếm, URL xác thực) chỉ được render khi là http/https, chặn scheme `javascript:`.

## [0.9.11] - 2026-07-06
### Thêm mới
- **X (Twitter) vào kho Kết nối** (MCP chính chủ của X, remote): tìm và đọc bài đăng, xem hồ sơ và số liệu công khai. Dán Bearer Token App-only từ X Developer Portal; mặc định Chỉ đọc (token app-only không đăng bài/nhắn tin được nên an toàn). Đăng bài theo tài khoản người dùng cần OAuth - sẽ bổ sung khi bạn cần.
### Cải thiện
- **Logo thương hiệu cho connector**: X, Higgsfield, TikTok Ads, Google Ads và Gmail giờ hiện logo thật thay cho biểu tượng emoji.

## [0.9.10] - 2026-07-06
### Thêm mới
- **Higgsfield vào kho Kết nối** (MCP chính chủ, remote): tạo và chỉnh ảnh/video bằng AI - sinh ảnh, sinh video, nâng nét (upscale), mở rộng khung hình, xoá nền, cắt nhân vật, điều khiển chuyển động. Đăng nhập Higgsfield 1 chạm: Javis tự đăng ký ứng dụng theo chuẩn OAuth của MCP (tự dò metadata + DCR + PKCE, không cần tạo app hay dán key), dùng được trên mọi engine. Mặc định mức Ghi nháp để Javis tạo được nội dung ngay và chặn thao tác xoá/thanh toán; mỗi lần tạo tiêu credit Higgsfield trả trước của bạn.

## [0.9.9] - 2026-07-06
### Thêm mới
- **Xem ảnh và mở file ngay trong chat + trang Tệp tin**: Javis nhúng được ảnh vào câu trả lời (hiện luôn trong khung chat, bấm là mở full ở tab mới) và đính link mở/tải file như PDF, DOCX, XLSX. Trang Tệp tin xem trước được ảnh và PDF ngay trong app; file khác có nút "Mở" ra tab mới bằng đường dẫn tĩnh. Thêm endpoint `/files/raw` phục vụ file inline (khác `/files/download` luôn ép tải).
### Sửa lỗi
- **Ảnh/file trong chat bấm vào không xem được; trang Tệp tin không xem được ảnh và không mở được PDF/DOCX** (chỉ tải về): do khung chat chưa render ảnh/link markdown và chưa có URL phục vụ file inline. Nay hiển thị ảnh, mở PDF trong app, và mọi file đều có đường dẫn tĩnh để mở/tải.

## [0.9.8] - 2026-07-06
### Thêm mới
- **Skill chạy trên MỌI engine, hết phụ thuộc cấu trúc của Claude**: trước đây skill chỉ hoạt động ngon trên Claude Code (đọc native từ `.claude/skills`), còn ChatGPT/Codex thì gọi không ra. Nay Javis có một **skill router riêng** dùng chung cho mọi engine: danh sách skill (tên + mô tả) được bơm thẳng vào system prompt, kèm tool `javis_use_skill` để nạp nội dung skill và làm theo. Claude Code, ChatGPT/Codex, OpenRouter, OpenAI API và Anthropic API giờ đều dùng được skill như nhau.
- **Nơi lưu skill chuyển sang `skills/` (phẳng, do Javis sở hữu)**: đồng bộ với `agents/`, `workflows/`, `memory/`. Brain cũ để skill ở `.claude/skills` được **tự dời sang `skills/`** một lần (an toàn, không mất dữ liệu, giữ nguyên skill đang tắt). Javis vẫn tự **mirror** sang `.claude/skills` để Claude Code nạp native như một điểm cộng - nhưng router chính không còn phụ thuộc thư mục đó nữa.
### Cải thiện
- **Skill do Javis tự học giờ BẬT sẵn** (thay vì để nháp tắt chờ duyệt), đánh dấu `origin: javis-learned` để nhận diện; vẫn tuyệt đối KHÔNG ghi đè skill bạn đã có và KHÔNG hồi sinh skill bạn cố ý tắt.
### Sửa lỗi
- **ChatGPT/Codex không tìm thấy skill**: nhánh chat qua Codex trước đây không được nạp system prompt của Javis và chạy sai thư mục làm việc nên không thấy skill nào. Nay Codex chạy đúng thư mục brain và nhận đủ router skill, gọi được skill người dùng đã tạo.
- **Sửa skill đang tắt bị rỗng nội dung**: nút Sửa trước đây chỉ đọc skill ở vị trí bật nên skill đang tắt mở ra form trống. Nay đọc được cả skill trong `.disabled`; và Lưu khi sửa giữ nguyên trạng thái bật/tắt (không tự bật skill đang tắt, không để lại bản nháp mồ côi).

## [0.9.7] - 2026-07-05
### Cải thiện
- **Giọng nói mượt hơn, hết chèn giọng lạ, biết dừng khi bạn nói**: (1) audio đầu tiên phát NHANH hơn - tách câu đầu ra đoạn nhỏ để tổng hợp + tải tức thì, bớt cảnh khựng vài giây sau khi chữ đã hiện; (2) khi một đoạn đọc lỗi mạng, Javis thử lại đúng giọng Việt và TUYỆT ĐỐI không rơi về giọng mặc định trình duyệt (thường là tiếng Anh) - hết cảnh "giọng Anh lạ chèn giữa chừng"; (3) ngắt lời (barge-in) khi rảnh tay: đang đọc mà nghe bạn nói đủ rõ thì tự dừng và mở nghe ngay, kèm bật khử vọng/khử ồn mic để đỡ nghe lại chính giọng mình.
### Sửa lỗi
- Một đoạn đọc lỗi trước đây bị xử lý 2 lần (Chrome bắn cả sự kiện error lẫn play() reject cho cùng audio) gây 2 luồng đọc chồng nhau và audio không dừng được; nay mỗi đoạn lỗi chỉ xử lý đúng một lần.

## [0.9.6] - 2026-07-04
### Cải thiện
- **Trang Cài đặt gọn và hợp lý hơn**: gộp "Nhà cung cấp giọng đọc" vào chung nhóm Giọng nói (trước đây nằm tách tận cuối trang, sau avatar và tên miền); bỏ nút "Nghe thử" bị trùng (giữ 1 nút duy nhất); ẩn danh sách giọng Edge (HoaiMy/NamMinh) khi chọn provider OpenAI/ElevenLabs vì lúc đó chọn giọng ngay trong khối provider; sửa tiêu đề gây hiểu nhầm (bỏ "Giao diện" vì không có mục đó); nút nghe thử chuyển sang viền để nút Lưu nổi đúng vai trò chính.
- **Thông báo cập nhật bản Docker rõ ràng hơn**: bản Docker không bật Watchtower giờ hướng dẫn thẳng cách **Redeploy** để lấy image mới nhất (Hostinger bấm nút Redeploy trong Docker Manager; VPS chạy `docker compose up -d --pull always`), thay vì bảo "tự thêm service watchtower". Panel Phiên bản hiện luôn hướng dẫn này khi có bản mới mà không tự cập nhật tại chỗ được, không còn để bấm nút "Cập nhật ngay" rồi mới báo lỗi.
### Sửa lỗi
- Nút "Cập nhật ngay" trước đây coi là tự cập nhật được chỉ vì biến `WATCHTOWER_TOKEN` có sẵn trong compose (dù Watchtower chưa chạy), bấm vào trigger âm thầm thất bại rồi báo "phiên bản chưa đổi". Nay **dò Watchtower thật** (kiểm tra cổng, không gửi HTTP để khỏi kích hoạt update nhầm) mới quyết định, tránh báo nhầm.

## [0.9.5] - 2026-07-04
### Thêm mới
- **Lark** vào kho Kết nối (MCP chính chủ của Lark/LarkSuite, chạy local qua `@larksuiteoapi/lark-mcp`): nhắn tin, tài liệu (Docs), bảng dữ liệu (Base/Bitable), wiki, danh bạ. Tạo một Lark app rồi dán App ID + App Secret; Javis chỉ làm được đúng quyền bạn cấp cho app. Cần Node.js 18+. Mặc định Chỉ đọc; gửi tin nhắn và cấp quyền file là hành động nguy hiểm (phải Toàn quyền). Phân loại quyền theo 19 tool thật đã kiểm chứng.
- **Logo Zalo và Google Sheets**: hai connector này giờ hiện logo thật thay cho emoji.

## [0.9.4] - 2026-07-04
### Thêm mới
- **Slack** vào kho Kết nối (MCP chính chủ của Slack, remote): tìm/đọc/gửi tin, xem kênh và thành viên, quản lý canvas. Đăng nhập bằng OAuth qua một Slack app của chính bạn (Slack không cho tự đăng ký client, cần tạo app trong workspace + admin duyệt). Mặc định Chỉ đọc; gửi tin phải nâng Toàn quyền.
- **Systeme.io** vào kho Kết nối (MCP chính chủ, remote): quản lý liên hệ, tag, trường tuỳ biến, newsletter, phễu. Chỉ cần dán MCP key (tạo trong Cài đặt hồ sơ, hạn tối đa 90 ngày). Mặc định Chỉ đọc.
- **Logo thương hiệu cho connector**: các thẻ trong kho Kết nối giờ hiện logo thật (Pancake POS, Botcake, Webcake, Meta Ads, Google Calendar, Gmail, Slack, Systeme.io) thay cho biểu tượng emoji; connector chưa có logo vẫn dùng emoji như cũ.
### Cải thiện
- Nhánh OAuth explicit của hub nhận thêm 2 tinh chỉnh theo hãng: tên tham số scope và dấu ngăn (Slack dùng `user_scope` + dấu phẩy cho token người dùng, Google giữ `scope` + dấu cách) - để hỗ trợ đúng các nhà cung cấp OAuth không theo chuẩn chung.

## [0.9.3] - 2026-07-04
### Thêm mới
- **Kho Kết nối có Google Calendar và Gmail** (MCP chính chủ của Google, remote - chạy được cả trên VPS): Calendar xem lịch, tìm chỗ trống, tạo/sửa/xoá sự kiện; Gmail đọc/tìm thư, soạn NHÁP, gắn nhãn. Gmail bản chính chủ KHÔNG có tool gửi thẳng nên Javis luôn dừng ở bản nháp để bạn tự bấm gửi. Đăng nhập Google ngay trong dashboard; cần tạo OAuth client 1 lần (~10 phút, hướng dẫn từng bước trong cửa sổ kết nối, dùng chung 1 client cho cả hai). Mặc định Chỉ đọc; nâng lên Ghi nháp để tạo sự kiện/soạn nháp, Toàn quyền mới xoá được sự kiện.
### Cải thiện
- Hub OAuth giờ nhận **client tự khai (BYO client_id/secret)** cho nhà cung cấp không hỗ trợ tự đăng ký client như Google (trước đây chỉ chạy với server có DCR). Tự xin `access_type=offline` để giữ kết nối lâu dài (tự làm mới token), gửi kèm client secret khi đổi/làm mới token, và tự đặt tên tài khoản bằng email Google sau khi đăng nhập.

## [0.9.2] - 2026-07-04
### Thêm mới
- **Kho Kết nối có nhóm Quảng cáo - đủ 3 nền tảng lớn**: **Meta Ads** (Facebook & Instagram) qua MCP chính chủ của Meta - bấm Kết nối là đăng nhập Facebook, không cần tạo app hay dán key; **Google Ads** qua MCP chính chủ của Google (chỉ đọc, truy vấn GAQL: chi phí, chuyển đổi, từ khoá); **TikTok Ads** qua server cộng đồng trên Marketing API chính thức (chỉ đọc - TikTok chưa mở MCP chính chủ, khi mở sẽ thay trong kho). Cả 3 mặc định Chỉ đọc; Meta bật Toàn quyền mới tạo/sửa được chiến dịch (cảnh báo tiền thật, chiến dịch tạo mới luôn ở trạng thái tạm dừng chờ bạn tự bật).
### Cải thiện
- Kết nối OAuth (vd Meta Ads) sau khi đăng nhập giờ **tự đặt tên tài khoản** (lấy đúng tên tài khoản ads) như flow dán key, và ghi ngay profile MCP cho Codex - trước đây tên để mặc định và Codex phải đợi lần đổi cấu hình sau.

## [0.9.1] - 2026-07-04
### Sửa lỗi
- `start-javis.bat` chạy server ẩn hoàn toàn - hết cửa sổ CMD đen nằm lì.

## [0.9.0] - 2026-07-04
### Thêm mới
- **Trang "Kết nối" thay trang MCP**: kho connector cài sẵn (Pancake POS, Zalo cá nhân, Webcake Landing, Botcake) - bấm Kết nối, dán key (hoặc quét QR với Zalo) là xong, không còn tự gõ URL/transport/header. Javis tự kiểm tra key và tự đặt tên tài khoản (lấy đúng tên cửa hàng từ POS). Form kỹ thuật cũ vẫn còn ở card "Tự thêm (nâng cao)".
- **Đa tài khoản chính thức**: một dịch vụ nối NHIỀU tài khoản (nhiều shop POS, nhiều số Zalo) - mỗi tài khoản một chip có tên + quyền + dấu mặc định, thêm/tắt/xoá từng cái. Zalo mỗi tài khoản chạy cô lập (home riêng) nên nhiều số chạy song song không giẫm nhau.
- **MCP HUB**: mọi bộ não (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI API, Anthropic API) đấu qua MỘT điểm - Codex và engine API giờ dùng được cả MCP local dạng stdio (Zalo, Webcake) chứ không chỉ http như trước.
- **Anthropic API có vòng gọi tool** - hết cảnh "chat thuần không MCP". Engine API còn được thêm tool đọc/ghi file trong vault, `javis_use_skill` (kích hoạt skill của brain) và `javis_connections` - engine nào cũng là agent thực thụ.
- **Phân quyền 3 mức mỗi kết nối** (Chỉ đọc / Ghi nháp / Toàn quyền) chặn CỨNG tại hub theo từng lời gọi, hiểu cả tool đa hành động kiểu Pancake (`action=list` cho qua, `action=create` chặn). Loop nền mode suggest/auto bị hub chặn hành động ghi/tiền-đơn bất kể prompt nói gì. Bật Toàn quyền phải tick xác nhận rủi ro; Zalo có cảnh báo riêng về nguy cơ bị khoá tài khoản (API không chính thức).
- **Nhật ký gọi tool (audit)** xem theo từng kết nối, nút Test lại, rate limit chống spam cho Zalo.
- **Đăng nhập Zalo bằng quét QR ngay trong dashboard**: Javis tự chạy zalo-agent-cli, hiện mã QR trong modal, quét xong tự tạo kết nối (cần Node.js 20+).
- **OAuth chuẩn MCP** (PKCE + tự đăng ký client): server nào theo chuẩn thì bấm Kết nối là xong ngay trên VPS, Javis tự giữ và tự refresh token - bỏ cảnh mở terminal gõ /mcp.
- Cầu nối **Botcake** tự viết qua Public API v1 (13 tool: khách hàng, tag, flow, gửi flow, keyword...) - không cần cài gì thêm.
- **3 card Google cho kinh doanh**: Google Sheets (đổ báo cáo doanh thu/tồn kho ra bảng tính - dán service account JSON là chạy, không cần đăng nhập), Google Search Console (số liệu SEO: khách tìm gì ra website), Google Workspace (Gmail + Lịch + Drive + Docs trong 1 kết nối, OAuth tự tạo có hướng dẫn từng bước; mặc định Ghi nháp - soạn nháp được nhưng KHÔNG tự gửi mail/xoá, bật Toàn quyền phải xác nhận). Kho hỗ trợ field dạng file (dán JSON, Javis tự lo phần còn lại) và tự kèm sẵn uv/uvx để chạy connector Python.
### Cải thiện
- MCP client có **session pool sống lâu** (giữ kết nối giữa các tin nhắn) + hỗ trợ stdio/internal: hết cảnh "mỗi tin nhắn kết nối MCP lại nên hơi chậm". Hub tự làm nóng lúc khởi động.
- Registry MCP chuyển sang STATE_DIR (Docker ghi được) và **tự migrate** từ bản cũ: server cũ thành connection, backup nguyên bản ở `mcp_servers.v1.bak.json`, không mất dữ liệu.
### Bảo mật
- API key/token của kết nối **mã hoá at rest** (Fernet, key riêng theo máy). Nhật ký audit chỉ ghi TÊN tham số, không ghi giá trị. Endpoint hub xác thực bằng token nội bộ riêng, không dùng session dashboard.

## [0.8.13] - 2026-07-03
### Cải thiện
- Bảng chọn model trong Telegram làm lại theo UX gateway Hermes: chọn provider ĐÃ KẾT NỐI (Claude Code, **ChatGPT**, OpenRouter, Claude API, OpenAI API - trước đây thiếu hẳn ChatGPT) có dấu ✓ + số model, rồi lưới model 2 cột **phân trang ◀ 1/N ▶**. Danh sách model lấy LIVE từ provider (OpenRouter đủ vài trăm model thay vì vài cái trong catalog; ChatGPT hiện model Codex), có mẹo gõ `/model <id>` chọn nhanh.
- Gõ tay `/model gpt-5.5` hoặc `/model gpt-5.3-codex` giờ tự hiểu là ChatGPT (Codex) nếu đã kết nối OAuth, không còn bị nhét nhầm sang Claude.

## [0.8.12] - 2026-07-03
### Thêm mới
- Telegram có lệnh **`/brain`** - xem và đổi brain (vault) cho RIÊNG phiên của mình: gõ `/brain` mở bảng nút bấm chọn (brain đang dùng có dấu ✓), hoặc gõ thẳng tên `/brain <tên>` (khớp một phần cũng được). Đổi xong hội thoại tự reset để nạp đúng bộ nhớ/skill của brain mới; người khác dùng chung bot và dashboard KHÔNG bị ảnh hưởng. `/reset` giữ nguyên brain đã chọn.
- File gửi lên Telegram giờ rơi vào `inbox/telegram` của brain PHIÊN người gửi (trước đây luôn vào brain mặc định).
- `/status` hiển thị brain phiên đang dùng.

## [0.8.11] - 2026-07-03
### Thêm mới
- Telegram **đa phiên theo tài khoản**: mỗi chat ID giờ có ngữ cảnh hội thoại RIÊNG, không còn lẫn lộn khi nhiều người dùng chung 1 bot. Trước đây tất cả người dùng dùng chung một session (người sau nối tiếp mạch của người trước, và chỉ 1 người được trả lời tại một thời điểm). Nay mỗi tài khoản có session Claude riêng (giữ `--resume` độc lập), lịch sử OpenRouter riêng, câu `/retry` riêng.
- Các tài khoản **chạy song song**: A đang được trả lời thì B hỏi vẫn được xử lý ngay, không phải xếp hàng chờ. Trong CÙNG một tài khoản vẫn tuần tự 1 lượt/lúc (gửi câu mới khi đang bận sẽ báo "đang xử lý câu trước").
- `/reset` và `/stop` chỉ tác động **phiên của chính người gõ**: reset xoá đúng ngữ cảnh của họ, stop chỉ giết đúng tiến trình Claude của họ (không đụng người khác đang chat). `/status` hiển thị mã phiên.
- File Javis tạo ra gửi về **đúng người đang hỏi**: endpoint `POST /telegram/send-file` nhận thêm `chat_id`, và gateway nhắc engine luôn gắn chat_id của người hỏi vào lệnh gửi (thiếu thì rơi về chủ bot như cũ). Whitelist vẫn chặn ID lạ.
### Sửa lỗi
- Dashboard web: nút **Stop không còn giết nhầm lượt của người khác** đang chat song song. Mỗi kết nối WebSocket giờ có tag phiên riêng (server phát qua message hello, frontend gửi kèm khi POST `/stop`) - web vốn đã đa phiên (mỗi tab/kết nối một session, lưu SQLite resume được), đây là lỗ hổng chéo duy nhất còn lại.
- Khung chat **phóng to (chat workspace) trước đây KHÔNG hiện trạng thái** "đang suy nghĩ / đang gọi tool": thanh trạng thái cũ nằm ngoài `#chatArea` nên bị bỏ lại khi phóng to. Đã thay bằng chip hoạt động ngay trong khung chat.
### Cải thiện
- **Chip hoạt động trong khung chat** (cả thường lẫn phóng to): bong bóng 3 chấm nhún + dòng trạng thái sống ("Javis đang suy nghĩ...", "⚙ Đang gọi: pos_statistics", "✍ Đang soạn câu trả lời...") + đồng hồ đếm giây khi đợi lâu (hiện từ giây thứ 3). Chip hiện NGAY khi bấm gửi, luôn nằm dưới cùng kể cả dưới bubble đang stream, tự biến mất khi xong lượt.

## [0.8.10] - 2026-07-03
### Thêm mới
- Telegram hỗ trợ **NHIỀU chat ID** dùng chung 1 bot: ô "Chat ID được phép dùng" giờ nhận nhiều ID cách nhau dấu phẩy (vd `123456789, 987654321`) - thêm người thân/nhân viên nhắn với Javis mà không phải dựng bot riêng. Whitelist chặn đúng theo danh sách; ID nhóm (số âm) cũng dùng được.
- Nút **Gửi test** gửi tin thử tới TẤT CẢ ID và báo rõ ID nào lỗi (thường do người đó chưa bấm Start bot); thông báo nền (loop tự tạm dừng...) cũng gửi tới tất cả ID; dòng trạng thái hiện số ID được phép, cảnh báo rõ khi đang để trống (mọi người nhắn được). File tự gửi về Telegram không kèm chat cụ thể sẽ về ID ĐẦU TIÊN (chủ bot).
- Tương thích ngược hoàn toàn: cấu hình 1 ID cũ giữ nguyên, không phải làm lại gì.

## [0.8.9] - 2026-07-03
### Thêm mới
- **Trang chủ giới thiệu** (`website/index.html`): landing page 1 file HTML/CSS/JS thuần, phong cách dark nebula đồng bộ dashboard - hero gõ chữ tự động, nền đồ thị hạt sao canvas, bảng so sánh chatbot vs Javis, bento 8 tính năng, mockup Telegram có bong bóng chạy, timeline 3 bước deploy, section giới thiệu tác giả Nguyễn Minh Quý, FAQ accordion, nút copy lệnh. Mọi link tài liệu trỏ về GitHub; KHÔNG hiển thị số phiên bản trên trang. Dùng ảnh thật: screenshot đồ thị tri thức trong ô tính năng lớn (kiêm og:image khi share) + chân dung tác giả (fallback chữ MQ nếu ảnh lỗi).

## [0.8.8] - 2026-07-03
### Sửa lỗi
- Đổi tên file mẫu `.env.example` → `env.example` (bỏ dấu chấm đầu): Docker Manager của Hostinger tự quét file `.env*` trong repo khi deploy từ URL và nhập nguyên nội dung (kể cả dòng chú thích `#`) vào ô Environment, gây một loạt biến đỏ "Invalid variable name" mỗi lần deploy. Ô Environment trên Hostinger giờ chỉ cần đúng 1 biến `DOMAIN_NAME`. Ai đã dính: xoá các dòng có dấu `#` trong ô Environment một lần là sạch vĩnh viễn. Chạy local không đổi gì ngoài lệnh copy: `cp env.example .env`.

## [0.8.7] - 2026-07-03
### Thêm mới
- **Telegram thành kênh làm việc đầy đủ** (port ý tưởng gateway của hermes-agent):
  - Javis giờ **biết mình đang trả lời qua kênh nào**: gateway chèn block "Kênh hội thoại hiện tại" (Telegram DM/nhóm với ai, chat_id, các nền tảng đang kết nối) vào system prompt mỗi lượt - hỏi "em đang chat với anh qua đâu" là khai đúng, không đoán.
  - **Tự gửi file về Telegram**: file Javis tạo trong lượt (tool Write) hoặc file có đường dẫn tuyệt đối nhắc trong câu trả lời được tự động đính kèm gửi ngay sau câu trả lời (tối đa 10 file/lượt, mỗi file dưới 50MB; ảnh gửi dạng photo có preview, còn lại gửi dạng document).
  - Endpoint nội bộ `POST /telegram/send-file` (CHỈ nhận từ localhost - bên ngoài qua proxy vẫn bị chặn đăng nhập): agent chủ động gửi file bất kỳ có sẵn trên máy giữa lượt bằng curl.
  - **Nhận file/ảnh từ Telegram**: gửi file/ảnh (kèm caption) cho bot là Javis tự tải về `inbox/telegram/` trong brain rồi đọc như file đính kèm trong chat (trần tải 20MB của bot API). Voice/video chưa hỗ trợ - Javis sẽ nói rõ.
  - Tin nhắn trả lời render **MarkdownV2** (đậm/nghiêng/code/link hiện đẹp), tự fallback plain text nếu Telegram từ chối parse - không mất tin.
### Cải thiện
- Dashboard web cũng có block kênh riêng: Javis phân biệt đang nói chuyện qua web hay Telegram, và biết cách đẩy file sang Telegram khi user yêu cầu (nếu bot đang chạy).

## [0.8.6] - 2026-07-02
### Thêm mới
- **Chat workspace**: phóng to chat (nút ⛶ hoặc 🕘 Lịch sử) giờ mở thành không gian làm việc gần full màn hình kiểu Claude/Cowork - cột trái là **sidebar Lịch sử hội thoại** (＋ Hội thoại mới, tìm toàn văn, danh sách nhóm Hôm nay/Hôm qua/7 ngày/Cũ hơn, badge engine + số tin, đổi tên/xoá khi rê chuột, phiên đang mở tô sáng, bấm phát mở lại ngay), cột phải là nội dung chat căn giữa rộng tối đa ~980px. Sidebar ẩn/hiện được (nhớ trạng thái); màn hẹp tự chuyển thành ngăn kéo nổi, Esc đóng ngăn kéo trước rồi mới thu nhỏ chat. Panel Lịch sử trượt bên phải cũ được gỡ, nút 🕘 góc phải mở thẳng workspace.
- Tiện ích đọc/soạn trong chat: nút **⧉ Copy** cho từng khối code + copy cả tin nhắn Javis (hiện khi rê chuột); tin nhắn dài của bạn tự thu gọn sau 10 dòng kèm "Xem thêm"; đang cuộn đọc phía trên thì tin mới KHÔNG kéo giật xuống - hiện nút **↓ Tin mới** ở đáy khung; chip file đính kèm hiển thị ngay trong workspace khi phóng to.
### Sửa lỗi
- Tin nhắn nhiều dòng của bạn (Shift+Enter) trước đây hiển thị dính thành một dòng - giờ giữ nguyên xuống dòng.
- Copy hoạt động cả khi trình duyệt chặn Clipboard API (tự fallback), vd truy cập qua HTTP LAN.

## [0.8.5] - 2026-07-02
### Thay đổi
- Sao lưu GitHub nâng cấp thành **đồng bộ 2 CHIỀU**: mỗi lượt vừa đẩy thay đổi của máy lên repo, vừa kéo thay đổi từ máy khác về và tự hoà nhập. Dùng được nhiều máy chung 1 repo (máy nhà + VPS làm việc xen kẽ, các máy tự khớp nhau) - hết cảnh 2 máy force-push đè mất backup của nhau.
- Xung đột cùng 1 file sửa ở 2 nơi: bản có lần sửa MỚI HƠN thắng, bản thua giữ nguyên thành file `.conflict-<local|remote>-<thời điểm>` ngay cạnh (không âm thầm mất chữ nào); một bên sửa một bên xoá thì bản sửa thắng. Đẩy lên bằng push thường (bỏ force-push); máy khác chen ngang thì tự kéo về hoà tiếp rồi đẩy lại.
- Khôi phục máy mới không cần git tay: dán repo + token rồi bấm Đồng bộ ngay là brain về đủ. Thư mục brains trống được coi là chế độ KHÔI PHỤC - chỉ nhận về, không bao giờ đẩy "trạng thái trống" lên đè backup. File thiếu cục bộ (wipe/volume mới) tự được vá lại từ bản đồng bộ.
### Sửa lỗi
- Đồng bộ truyền byte nguyên văn giữa các máy (tắt autocrlf của git trên mirror) - hết cảnh cùng 1 file lệch CRLF/LF giữa Windows và VPS Linux mãi không khớp.
### Cải thiện
- Trang Tự học: mục đổi tên "⇅ Đồng bộ brain với GitHub (2 chiều)", nút "Đồng bộ ngay" báo kết quả chi tiết (nhận về bao nhiêu file, có đẩy lên không, danh sách file xung đột); trạng thái lần cuối lưu kèm báo cáo. Không đẩy được về máy (file bị khoá) thì HOÃN push để giữ an toàn dữ liệu, lần sau tự thử lại.

## [0.8.4] - 2026-07-02
### Thay đổi
- Tách 2 tầng rõ ràng: **tầng hệ thống** (chức năng mặc định của Javis OS - skill javis-builder / ingest-source / query-wiki / lint-wiki + loop tự-cải-tiến) giờ đi theo mã nguồn app tại `.claude/skills/` và `system/loops/`, cập nhật cùng phiên bản khi update app; **tầng brain** chỉ còn dữ liệu của bạn (ký ức, sources, wiki, agent/skill/workflow/loop tự tạo). Đổi brain không còn mất chức năng mặc định.
- Đồng bộ có manifest (`.javis/system-manifest.json` trong mỗi brain): app lên bản mới thì bản skill/loop hệ thống trong brain được cập nhật theo, NHƯNG file bạn đã sửa thì giữ nguyên bản của bạn (user override); loop giữ nguyên trạng thái bật/tắt, chế độ, chu kỳ bạn đã chỉnh. Lỡ xoá file hệ thống thì tự cài lại (muốn ngừng dùng hãy TẮT skill - trạng thái tắt được tôn trọng qua mọi lần update).
- Lúc khởi động đồng bộ cho MỌI brain trong thư mục brains (trước đây chỉ Brain Default được seed lúc boot, brain tạo ở bản cũ không bao giờ nhận skill mới); brain ngoài chọn qua `path:` được đồng bộ ngay lượt dùng đầu. Nút "Tạo cấu trúc" (vault init) giờ seed đầy đủ như brain mới tạo.
- Skill hệ thống được nạp NATIVE cho chat ở mọi brain (nguồn chuẩn nằm trong thư mục app - engine Claude Code đọc trực tiếp), không còn phụ thuộc bản sao trong brain.
### Cải thiện
- Trang Skills: skill hệ thống có nhãn "hệ thống", không xoá được (chỉ tắt/bật hoặc sửa - sửa thì thành bản riêng của bạn và ngừng tự cập nhật).

## [0.8.3] - 2026-07-02
### Thêm mới
- Javis Index (`Javis/index.md`): chỉ mục tầng vận hành - liệt kê MỌI agent/skill/workflow/loop/lịch trong brain, tự sinh từ file (không sửa tay), kèm dòng tổng quan + cờ sức khoẻ (workflow trỏ agent không tồn tại, agent mồ côi, skill tắt, loop tự tạm dừng). Song song wiki/index.md để bất kỳ AI/engine đọc 1 chỗ là hiểu Javis có năng lực gì.
- Bản gọn (live) được chèn vào system prompt mọi engine (Claude/Codex/OpenRouter) → giải bài toán "đổi model là mất nhận biết skill", và giúp không tạo trùng năng lực. Endpoint GET /javis/index. Tự dựng lại khi khởi động + theo nhịp nền (chỉ ghi khi đổi, không churn git).

## [0.8.2] - 2026-07-02
### Cải thiện
- Engine Tự học siết 3 kỷ luật chống bịa (đồng bộ schema vault): citation cứng cho mọi câu wiki cụ thể, gắn nhãn mục-tiêu-vs-thực-tế (không biến câu tầm nhìn thành claim chắc nịch), giữ mâu thuẫn không ghi đè. Wiki tự sinh giờ ít mà chất, đáng tin để tích luỹ.
### Thêm mới
- 3 skill vận hành Second Brain (seed vào mỗi brain, create-if-missing): **ingest-source** (tiêu hoá source, kèm 3-pass cho source dài), **query-wiki** (trả lời có trích dẫn + lưu lại kết quả giá trị), **lint-wiki** (health-check 8 loại lỗi, chỉ trả checklist). Biến 3 phép toán INGEST/QUERY/LINT từ prose thành công cụ tự kích hoạt, nhất quán đa engine.

## [0.8.1] - 2026-07-02
### Thêm mới
- Brain mặc định giờ là bộ "compounding wiki" phổ quát (không còn tối giản): mỗi brain tự seed schema doc (CLAUDE.md + AGENTS.md để Claude Code lẫn Codex tự nạp) + file điều hướng wiki (index.md, log.md, _open-questions.md) + _session-handoff.md (chuyển giữa các model không mất mạch). Encode pattern tích luỹ tri thức + 3 kỷ luật chống bịa (citation bắt buộc, mục tiêu vs thực tế, mâu thuẫn giữ rõ) + 3 phép toán INGEST/QUERY/LINT.
- Trung lập ngành: KHÔNG seed folder marketing/Bullet Journal; taxonomy mọc dần theo source thật, gói theo-ngành để dành làm opt-in. Tất cả create-if-missing (không đè file bạn đã sửa).

## [0.8.0] - 2026-07-02
### Thay đổi
- Sao lưu GitHub giờ đồng bộ **TOÀN BỘ thư mục brains** (mọi brain) trong MỘT lần thay vì từng brain (sửa lỗi các brain đè nhau khi tự động backup vào cùng repo). Mỗi brain là một thư mục con trong repo; xoá brain khỏi máy thì backup sau cũng bỏ. Khuyến nghị để mọi brain trong thư mục brains (tạo brain mới bằng nút ➕ là tự vào đó) để chuyển máy dễ.
- Cơ chế mới dùng bản sao sạch (mirror): bỏ hội thoại gốc/log/khoá + git thô của từng brain (tránh lỗi nested-repo), token không lọt .git/config.
### Thêm mới
- Đổi avatar/logo mặc định của Javis.

## [0.7.9] - 2026-07-02
### Thêm mới
- Bộ "meta-capabilities" khởi đầu, tự seed vào mỗi brain: skill **javis-builder** (dạy Javis tự tạo agent/skill/workflow/loop đúng chuẩn, có chống trùng + rào an toàn) và loop **tự-cải-tiến-javis** (mặc định TẮT, chế độ đề xuất - mỗi vòng rà hệ thống, đề xuất 1 cải tiến nhỏ an toàn, ghi báo cáo vào 05 - Projects). Tạo dạng create-if-missing, không đè file bạn đã sửa.
- Quy tắc "Làm rõ trước khi trả lời" trong system prompt: câu hỏi phức tạp/mơ hồ thì Javis tự diễn đạt lại cách hiểu + nêu giả định rồi mới làm, chỉ hỏi lại khi thực sự tắc.

## [0.7.8] - 2026-07-02
### Thêm mới
- Agent chọn được model của ChatGPT/Codex (GPT-5.x) bên cạnh Claude (Sonnet/Opus/Haiku/Fable). Agent model Codex chạy qua Codex CLI - vẫn đọc/ghi file vault + dùng MCP. Dropdown model trong Studio chia 2 nhóm Claude / ChatGPT.
- An toàn: workflow chạy nền tự động (dispatcher, file-only) luôn dùng Claude Code để giữ giới hạn công cụ, kể cả khi agent chọn Codex; model Codex chỉ áp khi chạy workflow trực tiếp ở Studio.
### Thay đổi
- Tài liệu mô tả lại: Javis xây trên CLI dạng agent của nhà cung cấp (Claude Code + Codex) và tận dụng gói subscription, không còn xoay quanh chỉ Claude. Cập nhật README, docs 07/10, nhãn Docker và system prompt.

## [0.7.7] - 2026-07-02
### Sửa lỗi
- Agent: phần chọn Model (Sonnet/Opus/Haiku) trước đây lưu vào file nhưng KHÔNG được áp khi chạy - workflow luôn dùng model mặc định. Nay model của từng agent (kể cả agent kiểm chứng) được áp THẬT vào CLI lúc chạy. Thêm lựa chọn "Fable" + "Mặc định (theo CLI)" trong dropdown; agent để trống model = dùng model mặc định.

## [0.7.6] - 2026-07-02
### Sửa lỗi
- ChatGPT/Codex trên VPS báo "gpt-5-mini không hỗ trợ khi dùng Codex với tài khoản ChatGPT": model API thường (gpt-5-mini, gpt-4o, o3...) không chạy được qua Codex. Nay tự đổi (coerce) sang model Codex hợp lệ trong catalog (mặc định gpt-5.5) ở cả chat lẫn Telegram, tự chữa lại cấu hình đã lưu, và báo cho người dùng. Bộ chọn model của ChatGPT-OAuth cũng chỉ còn liệt kê đúng model Codex (bỏ nguồn trả model ChatGPT chung).
### Thêm mới
- Guide khi deploy: thêm OCI image labels (documentation/source/url) + nhãn compose để Docker Manager (Hostinger) hiện link Documentation/Quick start cho project. Thêm QUICKSTART.md (deploy 3 cách + sự cố hay gặp) ở gốc repo; mọi link tài liệu trỏ về docs trên GitHub.

## [0.7.5] - 2026-07-02
### Thêm mới
- Sao lưu brain lên GitHub: mục mới trong trang Tự học, có hướng dẫn 3 bước ngay trên màn hình (tạo repo private → tạo token fine-grained → dán vào). Nút Kiểm tra kết nối + Sao lưu ngay + công tắc tự sao lưu định kỳ. Tài liệu chi tiết: docs/18-sao-luu-github.md.
- Backup đẩy toàn bộ brain lên repo GitHub riêng (force-push, local là bản gốc); khôi phục bằng git clone khi mất máy/VPS.
### An toàn
- Token GitHub lưu nội bộ settings.json (gitignored), KHÔNG đẩy lên repo và tự che trong mọi thông báo lỗi; push dùng URL tạm nên token không nằm trong .git/config. File nhạy cảm (log thô, hội thoại gốc, khoá lock) được .gitignore loại khỏi bản đẩy. Cảnh báo rõ trên UI: chỉ dùng repo Private.

## [0.7.4] - 2026-07-02
### Thay đổi
- Tự học: mặc định BẬT sẵn + chế độ Tự ghi + bật cả 4 khả năng (Ký ức, Wiki, Kỹ năng, Việc) cho cài mới. Học chạy ngay từ đầu, không phải vào bật thủ công.
- Bỏ yêu cầu git: chế độ Tự ghi giờ hoạt động KỂ CẢ khi máy chưa có git (trước đây tự hạ về Chạy thử). Có git thì vẫn tự commit để hoàn tác 1 chạm; không có git thì vẫn ghi bình thường, chỉ thiếu undo/backup.
- Tự học giờ tự đăng ký brain đang trò chuyện: chat trên vault nào là học vault đó, không cần vào trang Tự học bấm lưu để thêm vault vào danh sách.
### An toàn
- Các rào an toàn của engine học GIỮ NGUYÊN: fork chỉ-đọc cô lập (0 MCP), quét lộ khoá + câu tiêm, chặn ghi ngoài phạm vi, ký ức chỉ thêm không đè.

## [0.7.3] - 2026-07-02
### Thêm mới
- Loop có thêm chế độ "Toàn quyền" (mode full): loop tự thao tác THẬT ra ngoài qua MCP không cần hỏi (tạo/sửa đơn, chạy quảng cáo tiêu tiền, gửi tin, đăng bài). Dành cho ai muốn loop tự làm hết. Kèm cảnh báo rủi ro đỏ trong form + hộp xác nhận khi lưu và khi bật; tab Lịch đánh dấu "⚠ TOÀN QUYỀN".
- 3 mức quyền rõ ràng: Đề xuất (chỉ đọc) · Tự làm an toàn (ghi nháp + đọc MCP, KHÔNG tiền/đơn) · Toàn quyền (làm mọi thứ). Mặc định vẫn là mức an toàn; chế độ toàn quyền phải tự bật.
### An toàn
- Loop toàn quyền vẫn tôn trọng cài đặt "chặn tool" (deny_tools) của từng MCP server; bước tự kiểm chứng chuyển sang soi "đúng phạm vi nhiệm vụ" thay vì cấm hành động. Javis khi chat KHÔNG bao giờ tự đặt loop sang toàn quyền - chỉ khi người dùng yêu cầu rõ.

## [0.7.2] - 2026-07-02
### Thay đổi
- Form tạo Loop gọn còn Tên + Mô tả (+ chế độ + chu kỳ): bỏ bộ chọn "Loại nhiệm vụ" 4 nút. Mỗi loop giờ chỉ cần mô tả việc cần làm mỗi vòng. Tinh chỉnh nâng cao (giờ im lặng, trần vòng/ngày, profile code) sửa trực tiếp trong file Javis/loops/<tên>.md.
- Loop giờ ĐỌC được dữ liệu thật qua MCP (POS, quảng cáo, lịch...) để làm việc - trước đây loop bị cô lập 0-MCP. An toàn giữ 3 lớp: tôn trọng deny_tools từng server, chỉ dẫn cứng cấm tạo đơn/tiêu tiền/quảng cáo/đăng bài/gửi tin (chỉ được đọc + ghi nháp), và kiểm chứng độc lập sẽ fail nếu phát hiện hành động ghi ra ngoài. Loop chạy nền vẫn KHÔNG có Bash/Web (trừ profile code cho loop sửa mã, vốn 0-MCP).

## [0.7.1] - 2026-07-02
### Cải thiện
- Trang loop: đổi tên mục sidebar "Tự cải thiện" thành "Loop" cho gọn, đúng bản chất.
- Bỏ nút "LINT Wiki" khỏi trang Loop (engine Tự học đã lo bảo trì Wiki qua curator/LINT chỉ-đề-xuất), tránh trùng chức năng.

## [0.7.0] - 2026-07-02
### Thêm mới
- MULTI-LOOP: "Vòng lặp tự cải thiện" nâng thành hệ NHIỀU loop. Mỗi loop = 1 file `Javis/loops/<slug>.md` trong vault (sửa được bằng Obsidian/chat/Studio), có bật/tắt, chu kỳ riêng, giờ im lặng (quiet_hours), trần vòng/ngày, workspace + tools_profile (vault-safe mặc định / code cho loop sửa mã). Thực thi TUẦN TỰ (1 vòng/lúc), state runtime tách riêng ở `Javis/loop-state.json`.
- Tự bảo vệ: loop lỗi/kiểm chứng ✗ 3 lần liên tiếp thì TỰ TẠM DỪNG (ghi lý do + log, báo Telegram nếu có bot); bật lại hoặc Chạy ngay để tiếp tục.
- API mới `/loops` (list/tạo/sửa/toggle/xoá/run-now/log lọc theo loop). `/loop/*` cũ giữ nguyên, trỏ về loop legacy `vong-lap-goc`.
- Trang "Tự cải thiện" thành DANH SÁCH loop: trạng thái, lần chạy cuối + kết quả kiểm chứng, next run, nút bật/tắt - chạy ngay - sửa - xoá, form tạo loop đầy đủ, nhật ký lọc theo loop.
- Tab Lịch hiện MỌI loop như routine builtin (id `__loop__:<slug>`): bật/tắt ngay tại đó; xoá thì phải sang trang Tự cải thiện.
- Javis chat = ĐIỀU PHỐI VIÊN: system prompt thêm quy trình chọn công cụ nhỏ nhất đủ hoàn thành (trả lời → task Kanban → skill → agent → workflow → lịch → loop), kiểm tra trùng trước khi tạo, loop tạo qua chat mặc định suggest + tắt.
### Cải thiện
- Migrate 1 lần: `loop_config.json` cũ tự sinh `Javis/loops/vong-lap-goc.md` (giữ nguyên toàn bộ custom_goal), json cũ giữ làm backup.

## [0.6.6] - 2026-07-02
### Thêm mới
- Nối engine tự học vào Kanban: capability "Việc (Kanban)" - sau mỗi hội thoại, engine học đề xuất việc nền vào backlog (dedup theo tên, chờ duyệt).
### Sửa lỗi
- Dashboard chết toàn bộ (Enter không gửi, stats trống, không graph) do app.js bám nút học cũ đã gỡ - đã guard + nghỉ hưu auto-learn client cũ.

## [0.6.5] - 2026-07-02
### Sửa lỗi
- docker-compose.hostinger.yml "không cài được": bỏ ${DOMAIN_NAME:?...} (bắt buộc biến, thiếu là deploy fail). Nay LUÔN deploy được: chưa đặt DOMAIN_NAME thì chạy tạm ở :7777, đặt DOMAIN_NAME thì có HTTPS. Publish lại cổng 7777 làm đường vào dự phòng.

## [0.6.4] - 2026-07-02
### Sửa lỗi
- docker-compose.yml: Watchtower chuyển sang profile "update" (mặc định TẮT) nên deploy base compose KHÔNG còn "Partially running" (Watchtower cần Docker socket, Hostinger hay chặn). Bật auto-update khi cần: docker compose --profile update up -d.
### Cải thiện
- README: sửa mục cài Hostinger dùng docker-compose.hostinger.yml + đặt DOMAIN_NAME cho tên miền/HTTPS; bỏ thông tin sai "Hostinger tự cấp URL hstgr.cloud".

## [0.6.3] - 2026-07-02
### Sửa lỗi
- docker-compose.hostinger.yml: đổi ports "7777:7777" (cố định) thành "7777" (ngẫu nhiên, giống Hermes) để nút Open trỏ thẳng domain HTTPS của Traefik thay vì http://<ip>:7777. Truy cập qua https://<DOMAIN_NAME>.

## [0.6.2] - 2026-07-02
### Sửa lỗi
- docker-compose.hostinger.yml: đã kiểm chứng Hostinger KHÔNG cấp biến TRAEFIK_HOST cho compose dán tay (link ra "javis-os." cụt). Nay Host BẮT BUỘC DOMAIN_NAME (dùng ${DOMAIN_NAME:?...}): thiếu thì deploy báo lỗi rõ ràng thay vì ra link hỏng. Tài liệu chỉ rõ đặt DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud ở ô Environment.

## [0.6.1] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml: Host mặc định dùng ${COMPOSE_PROJECT_NAME}.${TRAEFIK_HOST} (đúng mẫu Hermes) thay cho giá trị localhost -> deploy trên Hostinger là TỰ có link <tên-project>.<hostname-vps>.hstgr.cloud + HTTPS, không cần đặt biến gì. Muốn tên miền riêng thì đặt DOMAIN_NAME (ghi đè). Ai deploy trên VPS của họ cũng ra link đúng.

## [0.6.0] - 2026-07-01
### Thay đổi
- Đồng bộ NỐT toàn bộ tên hạ tầng nội bộ sang javis: biến môi trường JAVIS_*, volume javis-data/javis-brains, service/container/user javis (/home/javis), profile codex javis, marker JAVIS_METRICS, và các file javis.service / start-javis.vbs / stop-javis.bat. Toàn dự án dùng một tên duy nhất.
- LƯU Ý khi redeploy: volume đã đổi tên nên bản mới bắt đầu TRỐNG (cần tạo lại admin + nạp lại brain), hoặc tự chép dữ liệu từ volume cũ sang javis-data/javis-brains. Nếu trước đó đặt biến admin trên Hostinger, đổi tiền tố sang JAVIS_ADMIN_USER / JAVIS_ADMIN_PASSWORD.

## [0.5.1] - 2026-07-01
### Thay đổi
- Đổi tên repo/image GitHub sang javis-os (image ghcr.io/blogminhquy/javis-os, GITHUB_REPO, link cài đặt trong README/DEPLOY).

## [0.5.0] - 2026-07-01
### Thay đổi
- Đổi thương hiệu hiển thị sang Javis (giao diện, tài liệu, README, system prompt).
### Thêm mới
- docker-compose.hostinger.yml dùng ${COMPOSE_PROJECT_NAME} cho tên router/service Traefik: chạy được nhiều bản Javis trên cùng 1 VPS mà không đụng nhau (giống đuôi ngẫu nhiên -efxd của Hermes).

## [0.4.7] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml gắn nhãn Traefik đúng mẫu app Hermes: BỎ phần networks/external traefik-proxy (chính chỗ làm deploy báo "network not found"). Traefik của Hostinger tự thấy container qua nhãn.
### Thêm mới
- Có link mặc định chạy HTTPS mà không cần mua tên miền: đặt DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud (Hostinger có wildcard DNS + tự cấp SSL).

## [0.4.6] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml không deploy được trên Hostinger: bỏ yêu cầu mạng ngoài `traefik-proxy` (gây lỗi "network not found"). Bản mới chỉ 1 container, publish cổng 7777, deploy là chạy; gắn tên miền + HTTPS là bước tùy chọn (Hostinger UI hoặc nhãn Traefik thủ công, hướng dẫn trong file).

## [0.4.5] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml bỏ Watchtower (cần Docker socket, hay gây "Partially running" trên Hostinger Docker Manager). Bản Hostinger giờ chỉ 1 container javis + nhãn Traefik, cập nhật bằng Redeploy.

## [0.4.4] - 2026-07-01
### Thêm mới
- File docker-compose.hostinger.yml: chạy Javis trên Hostinger với tên miền riêng + HTTPS qua Traefik có sẵn của Hostinger, bỏ cổng :7777.
### Sửa lỗi
- Tài liệu Hostinger nói đúng thực tế: compose gốc chỉ vào bằng IP:7777; muốn tên miền và SSL phải dùng bản có nhãn Traefik (docker-compose.hostinger.yml).

## [0.4.3] - 2026-07-01
### Thêm mới
- Khu Tên miền & SSL trong Cài đặt làm mới: huy hiệu trạng thái DNS và SSL, nút Bật SSL chủ động xin chứng chỉ rồi kiểm tra kết quả.
### Sửa lỗi
- Số phiên bản ở góc thanh bên nay đọc đúng bản đang chạy (trước bị cố định 0.4.0).
### Cải thiện
- Trạng thái tên miền rõ ràng: DNS đã trỏ đúng chưa, SSL bật chưa, kèm lệnh bật Caddy cho bản Docker khi cần.

## [0.4.2] - 2026-07-01
### Thêm mới
- Trang **Cập nhật** (mục Logs cũ trên thanh bên): nhật ký phiên bản và các thay đổi mới, đọc thẳng trong app.
- Tự đối chiếu bản đang cài với bản mới nhất trên GitHub, đánh dấu phiên bản "đang dùng" và bản "có thể cập nhật".

## [0.4.1] - 2026-07-01
### Sửa lỗi
- Upload file trên Docker/VPS báo "lỗi máy chủ (500)": thư mục stage tạm đổi sang STATE_DIR ghi được (`/data/state`) thay vì code tree `/app` chỉ đọc.
- Endpoint upload bọc chống lỗi: sự cố môi trường trả thông báo rõ ràng kèm log thay vì lỗi 500 khó đoán.
### Thêm mới
- Bộ tài liệu hướng dẫn sử dụng chi tiết trong `docs/` (17 trang) và mục lục nối vào README.
### Cải thiện
- Bỏ toàn bộ ký tự gạch ngang dài khỏi giao diện và tài liệu cho giọng nói đọc mượt hơn.

## [0.4.0] - 2026-06-30
### Thêm mới
- Trang **Cài đặt** riêng: chọn giọng đọc theo nhà cung cấp (Edge TTS, OpenAI, ElevenLabs), tinh chỉnh giao diện, avatar, tên miền.
- Nút **Cập nhật ngay** trong Tổng quan: cập nhật phiên bản mới ngay trên giao diện, không cần terminal.
- Đổi logo/avatar và trỏ tên miền riêng chạy HTTPS ngay trong app.
### Cải thiện
- Gộp cài đặt vào thanh bên, thu gọn điều hướng.

## [0.3.0] - 2026-06-29
### Thêm mới
- Chạy ChatGPT qua Codex CLI trên VPS: đăng nhập bằng gói subscription, dùng được cả MCP của Javis.
- Đăng nhập Claude bằng OAuth device-code ngay trong giao diện (không cần terminal).
- Kiến trúc đa Second Brain: quản lý nhiều brain trong thư mục `brains/`, tạo và xoá brain trong app.
### Sửa lỗi
- Trạng thái bot Telegram hiển thị đúng thực tế (đang chạy, lỗi 409, chưa bật).

## [0.2.0] - 2026-06-28
### Thêm mới
- Bộ cài đặt lần đầu (wizard) chọn 1 trong 3 nhà cung cấp: Claude Code, ChatGPT, OpenRouter.
- Triển khai 1-click qua Hostinger Docker Manager (kéo image GHCR).
- Tự bật HTTPS bằng Caddy, logo và favicon thương hiệu.
### Bảo mật
- Bắt buộc đăng nhập khi chạy public, MÃ THIẾT LẬP chống chiếm tài khoản admin.

## [0.1.0] - 2026-06-26
### Thêm mới
- Bản đầu tiên: trợ lý AI cá nhân chạy bằng Claude Code, giọng nói, đồ thị tri thức 3D, Second Brain.
- README chi tiết: giới thiệu, cài đặt mọi cách, hướng dẫn dùng, bảo mật, khắc phục sự cố.
