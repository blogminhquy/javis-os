# Chatbot (hòm thư bot, tài khoản bot, tạo chatbot)

***Tiếng Việt** · [English](en/28-customer-conversations.md)*

Mọi tin khách nhắn cho **bot chuyên trách** (Telegram hoặc Zalo Bot) và cho **tài khoản Zalo cá nhân** đã nối đều được gom về một hộp thư trong Javis. Bạn đọc lại cuộc trò chuyện giữa khách và bot, thấy cuộc nào bot đang bí, và **tiếp quản** một cuộc chat khi cần người thật.

Từ bản 0.61.0 trang này gộp luôn phần Chatbot: **một mục trên thanh bên, bốn tab** (Hội thoại, Bot, Kênh, Thống kê; tab Hội thoại tên cũ là Hòm thư bot, đổi tên và làm lại giao diện ở 0.372.0), và bạn **trả lời khách ngay trong tab Hội thoại**.

## Mở ở đâu trong Javis

Thanh điều hướng bên trái, nhóm **Năng lực**, mục **Chatbot**. Trong trang có bốn tab:

- **Hội thoại**: mọi tin khách, ai đang lo cuộc chat nào, trả lời, nhờ A.I. soạn.
- **Bot**: nhân viên A.I. đứng trực các kênh. Kênh đã có bot hiện thành chip trên thẻ bot; bấm chip để sửa hoặc xoá kênh đó. Xem [Chatbot](25-chatbot.md).
- **Kênh**: mọi nick và Page, bot nào trực, bật tắt A.I. từng nhóm hay người.
- **Thống kê**: A.I. và bạn đã trả lời bao nhiêu, khách chờ bao lâu.

Nói bằng lời cũng được: "mở hộp thư khách", "hòm thư bot", "tài khoản bot", và "mở chatbot" vẫn tới đúng tab Bot. Nói "hội thoại" trần vẫn ra trang Trò chuyện như trước.

## Mô hình

Bốn khái niệm, đọc một lần rồi khỏi đoán:

| | Là gì |
|---|---|
| **Chatbot** | Một nhân viên AI: Agent, brain riêng, mức quyền, và những tài khoản kênh nó đứng trực (một bot trực được nhiều tài khoản). |
| **Kênh** | Nơi khách nhắn tới. Mỗi kênh có nhiều **tài khoản**: một token bot Telegram, một token Zalo Bot, một tài khoản Zalo cá nhân đã quét QR. Sau này thêm Zalo OA, Facebook, Web Chat. |
| **Hội thoại** | Một phiên trao đổi với một khách (hoặc một nhóm) trên một kênh. |
| **Hòm thư bot** | Nơi AI và người thật cùng vận hành hội thoại: đọc, tiếp quản, trả lại AI. |

Bên dưới, mọi kênh đều đưa tin về **một khuôn chung** rồi vào cùng một kho: tài khoản kênh, khách, hội thoại, tin. Hòm thư bot không cần biết tin đến từ Telegram hay Zalo.

## Tab Hội thoại

Từ 0.372.0 (Chatbot v5) máy tính chia **ba cột**: danh sách khách bên trái, khung chat ở giữa, bảng **Thông tin** bên phải. Từ 0.397.0 bảng Thông tin **đóng sẵn** để khung chat rộng, bấm nút ⓘ ở góc phải đầu cuộc chat mới mở (Javis nhớ lựa chọn của bạn trên trình duyệt đó); màn hẹp hơn 1200px thì bảng trượt đè lên khung chat. Chữ trên máy tính cũng gọn lại: danh sách 14px, tin nhắn 15px, và tin nằm trong một cột giữa vừa tầm mắt.

**Trên điện thoại** (từ 0.397.0): không còn chữ "Chatbot" ở đầu trang, bốn tab chỉ còn icon (giữ ngón tay hay đọc màn hình vẫn nghe tên tab). Mở một cuộc chat là nó **chiếm cả màn hình**: một hàng đầu gồm nút quay lại, tên khách, kênh, và một **nút chế độ** màu tím (ví dụ "A.I. trả lời ▾"). Bấm nút đó là một bảng trượt từ dưới lên với ba chế độ, mỗi cái một dòng giải thích, cùng **Thông tin khách và cài đặt A.I.** Ô nhập một hàng, hai nút tròn: ✨ để A.I. soạn hộ, mũi tên để gửi.

**Ai đang lo cuộc chat này.** Server tính cho mỗi cuộc chat một trạng thái, mọi chỗ trên trang đọc đúng nó:

| Màu | Tên | Khi nào |
|---|---|---|
| vàng | **Cần bạn** | khách chờ mà không ai lo, có người gọi A.I. ở nhóm chưa cho phép, A.I. soạn xong chờ bạn duyệt |
| tím | **A.I. đang xử lý** | A.I. được phép trả lời ở đây và bot đang chạy |
| xanh | **Bạn đang xử lý** | bạn chọn Tôi trả lời và khách không chờ |
| xám | **Chỉ ghi lại** | A.I. không trả lời ở đây (chưa cho phép, kênh chưa có bot, bot tắt) và không ai chờ |

Mỗi dòng khách có **viền trái** theo màu đó, ảnh đại diện có **logo kênh** ở góc, tên, giờ, tin cuối (có "A.I.:" hay "Bạn:" phía trước), **số tin của cả cuộc chat** (ô xám, ví dụ "11 tin") rồi số chưa đọc (ô đỏ), và dòng thứ ba chỉ khi có thẻ: tối đa hai thẻ cộng "+n". Rê chuột lên dòng là đọc tên nick hay Page (khi đang xem nhiều nơi) và một câu nói chuyện gì đang xảy ra.

Đầu cột trái, từ trên xuống:

- **Ô tìm** (tên, số điện thoại, nội dung), nút **Lọc** là icon nằm ngay trong ô: menu hai tầng gồm Thời gian (tin cuối trong khoảng nào: hôm nay, 7, 30, 90 ngày, tháng trước, đầu tuần, đầu tháng, hoặc chọn ngày trên lịch), Có chứa thẻ, Loại trừ thẻ, Loại cuộc chat, Bot trả lời, Tình trạng (chưa đọc, chờ lâu nhất, đã ẩn), Tin cuối của ai (khách, A.I., bạn), Thông tin khách (có SĐT hay email, chỉ chat đã ghim). Bộ lọc đang bật hiện thành chip có dấu x ngay dưới.
- Hàng dưới có **hai nút thả xuống** (từ 0.397.0, thay cho bốn nút lọc nhanh trước đây hay bị gãy chữ):
  - Bên trái, **ai đang lo**: nút luôn hiện chế độ đang xem kèm số, ví dụ "Cần bạn 4". Bấm ra bốn lựa chọn, mỗi cái một dòng giải thích: **Cần bạn** (khách đang chờ bạn trả lời hoặc duyệt), **A.I. lo** (A.I. đang tự trả lời khách), **Bạn lo** (bạn đã nhận tự trả lời, A.I. im), **Tất cả** (mọi cuộc chat, kể cả chỉ ghi lại). Mở trang lần đầu là ở **Cần bạn**; không còn chat nào cần bạn thì trang nói vậy, kèm nút **Xem tất cả**.
  - Bên phải, **hộp chọn kênh**: bấm để mở danh sách nick và Page có ô tick, xếp theo kênh với logo thật. Tick tên kênh là chọn cả kênh; mỗi nơi có số chat **Cần bạn**. Không tick gì là xem tất cả. Có ô tìm, **Bỏ chọn**, **Xong** và **Quản lý kênh**. Rê chuột lên nút là đọc tên các nơi đang chọn.

Mọi lựa chọn được nhớ ở trình duyệt. Số trên tab **Hội thoại** là số chat **Cần bạn**.

**"Khách đang chờ" nghĩa là gì** (một trong các lý do của Cần bạn). Khách nhắn cuối, chưa ai đáp, **bạn chưa mở đọc** (mở chat là ra khỏi Cần bạn cho tới khi khách nhắn tiếp), tin đó không chỉ là báo kết bạn ("đã đồng ý kết bạn"), và: là chat riêng, hoặc là nhóm mà bot vừa **cân nhắc nói rồi im** (chưa chắc, hết hạn mức tự nói, hay bộ phán xử lỗi, trong 24 giờ qua và bạn chưa bấm Đúng/Sai). Nhóm thì phải có điều kiện thứ hai, vì bot chỉ nói khi được gọi thì khách nhắn cuối trong nhóm là chuyện bình thường; đếm hết vào thì bộ lọc đầy rác. Cần bật Tự đánh giá thì mới có dấu "bot cân nhắc" này (xem [Bộ phán xử](25-chatbot.md#bộ-phán-xử-bot-tự-quyết-nói-hay-im-và-học-từ-nhóm)).

**Nhóm chỉ giữ 1.000 tin gần nhất** (từ 0.396.0; từ 0.65.12 tới trước đó là 100). Hòm thư lưu hết tin của chat riêng với khách, nhưng mỗi **nhóm** chỉ giữ 1.000 tin mới nhất; tin cũ hơn tự xoá khi có tin mới về. Lý do: kho không phình mãi, và Javis không giữ lời của người lạ trong nhóm lâu hơn cần thiết (nick Zalo cá nhân ở nhiều nhóm thì Hòm thư ghi cả nhóm bot chưa được phép trả lời). Lần đầu cập nhật lên 0.65.12, các nhóm cũ đang có hơn 100 tin đã được cắt xuống 100 (tin đó không tự quay lại khi nâng lên 1.000); Javis **sao lưu nguyên file kho một lần** trước khi cắt (file `customer_conversations.sqlite3.bak-truoc-cat-nhom-...` cạnh file kho) và **tự xoá bản sao lưu sau 14 ngày**. Muốn lấy lại tin đã cắt thì chép bản sao lưu đè lên file kho trong vòng 14 ngày đó. Số "tin từng nhận" của hội thoại không giảm theo.

**Tải dần, không đơ máy** (từ 0.65.11). Danh sách chỉ tải 40 dòng đầu; cuộn gần tới cuối thì tự tải 40 dòng nữa (hoặc bấm **Xem thêm**). Khung tin cũng vậy: mở một hội thoại chỉ tải 40 tin **mới nhất**, kéo lên gần đầu (hoặc bấm **Xem tin cũ hơn**) thì tải thêm 40 tin cũ hơn và giữ nguyên chỗ bạn đang đọc. Cứ 5 giây Javis chỉ hỏi các tin **mới hơn tin cuối** rồi chèn vào cuối khung; đang đọc tin cũ mà có tin mới về thì khung đứng yên, không kéo bạn về đầu như trước.

Bấm một hội thoại là lịch sử tin hiện ở giữa: tin khách bên trái (nền trắng), câu A.I. (nền tím nhạt) và câu bạn (nền xanh) bên phải; tên người gửi và giờ nằm ngay dưới mỗi bong bóng, tên khách chỉ hiện trong nhóm. Đầu cuộc chat có tên khách kèm thẻ của cuộc chat và nút **+ Tag** (mở bảng Thông tin với bộ chọn thẻ), dòng dưới là kênh, nick và **số tin**. Lượt bot bị gãy cũng nằm đó kèm lý do kỹ thuật, để bạn phân biệt "bot trả lời sai" với "bot đang hỏng". Trang tự làm mới mỗi vài giây, không cần tải lại.

## Ai trả lời: đầu cuộc chat và thanh màu

**A.I. được phép trả lời ở đây**: ba chế độ **A.I. trả lời**, **A.I. soạn**, **Tôi trả lời** nằm ngay trên đầu cuộc chat, bên phải tên khách (trên điện thoại là nút chế độ mở bảng chọn). Rê chuột lên đó là đọc một câu nói chuyện gì đang xảy ra.

Ngay dưới tên khách là một **thanh mảnh** cùng màu với trạng thái, kèm **một câu** (ví dụ "A.I. đã soạn xong câu trả lời, chờ bạn duyệt"). Từ 0.397.0 thanh này **chỉ hiện khi cần bạn** hoặc khi có việc để bật, còn lúc A.I. đang lo yên ổn thì ẩn đi cho khung chat rộng. Nút đi kèm hợp với lúc đó:

- Đang ở Tôi trả lời mà khách chờ: **Trả lại cho A.I.**
- **Chưa cho phép**: nút **Cho A.I. trả lời ở đây**. Bot vẫn giữ nguyên ai được trả lời ở các cuộc khác.
- **Có người gọi A.I. ở một nhóm chưa cho phép**: **Cho phép** hoặc **Bỏ qua**.
- **Kênh chưa có bot**: **Tạo A.I. cho kênh này** mở form tạo bot với kênh đó tích sẵn.

Mọi thay đổi hiện một dòng báo ở đáy màn hình kèm **Hoàn tác**.

**A.I. soạn, tôi duyệt** (mới ở 0.371.0): lượt bot chạy như thường nhưng câu trả lời **không gửi**. Nó nằm ngay **trong khung ô nhập**, phía trên chỗ gõ, nền tím nhạt, cuộc chat chuyển sang Cần bạn. Bạn sửa chữ nếu cần rồi bấm **Gửi** (ghi vào hộp thư là lời A.I.), **Viết lại** (nhờ soạn lần nữa) hoặc **Bỏ**. Tin khách mới tới khi bản cũ chưa duyệt thì bản mới thay bản cũ. Đổi chế độ không xoá bản đang chờ; bạn tự gửi tay thì bản đó bỏ đi.

**Tắt A.I. ở riêng một cuộc chat**: chọn "Không cho A.I. trả lời ở đây" trong bảng Thông tin. Chỉ cuộc chat đó im; khách khác và nhóm khác vẫn như cũ.

## Trả lời khách và nút "A.I. soạn"

Ô nhập có hai nút:

- **Gửi**: gửi nguyên văn cho khách. Trên máy tính **Enter** để gửi, Shift+Enter xuống dòng. Trên điện thoại (từ 0.398.0) **Enter là xuống dòng** như khung chat chính, muốn gửi thì bấm nút gửi.
- **A.I. soạn** (trước 0.397.0 tên là "A.I. trả lời"): chữ trong ô là **lệnh cho A.I.**, ví dụ "báo giá sỉ 20 thùng, hẹn giao thứ 5". A.I. viết thành câu trả lời lịch sự ngay trong khung ô nhập, ghi rõ lệnh của bạn, kèm Bỏ / Viết lại / Gửi. Ô trống thì A.I. tự đọc cuộc chat mà soạn. **Không bao giờ tự gửi.** Lệnh chỉ A.I. đọc, không vào hộp thư.

Dưới tin khách cuối có dòng **"Bot im: lý do"** khi bộ phán xử đã ghi lý do (ví dụ "Điểm thấp hơn ngưỡng (0.52 / 0.60)"), kèm nút **Vì sao** mở thẳng bảng Bộ phán xử của bot đó, và nút **Nhờ A.I. trả lời tin này**: A.I. trả lời ngay tin đó và gửi luôn, cuộc chat vẫn ở A.I. tự trả lời. Nếu đó đúng là tin bộ phán xử đã im, bot còn **học thêm một ca**: lần sau gặp tin giống vậy bot sẽ nói. Gửi hỏng mà A.I. đã soạn xong thì câu đó nằm trong ô nhập để bạn gửi tay.

Tin đi qua đúng kênh của cuộc chat: bot Telegram hay Zalo Bot gửi bằng token của tài khoản đó, Zalo cá nhân gửi qua chính tài khoản bạn đã quét QR, **dưới tên bạn** (chữ mờ trong ô nhập nói rõ, ví dụ "Gửi dưới tên Javis Vũ..."). Kênh nào chưa gửi được từ Javis thì ô nhập thay bằng một dòng nói vậy.

Gửi tay ở một cuộc chat đang **A.I. tự trả lời** là bạn **tiếp quản** cuộc đó: A.I. im với khách này cho tới khi bạn chọn lại A.I. tự trả lời. Không thì khách đọc hai giọng một lúc. Chọn **Tôi trả lời** làm y như vậy mà không cần gửi gì; chọn xong bạn trả lời trong app của kênh cũng được.

## Bảng Thông tin

- **Khách**: tên, nick hay Page, số điện thoại hoặc email khách để lại, **thẻ** (thêm, bớt, tạo thẻ mới ngay tại chỗ) và **ghi chú** chỉ bạn thấy (lưu khi bạn bấm ra ngoài ô; ghi chú theo khách, sang cuộc chat khác của cùng khách vẫn thấy).
- **A.I. ở cuộc chat này**: Ai trả lời (tắt ở đây, hoặc một trong ba chế độ); với nhóm thì **A.I. lên tiếng khi** (được gọi tên, khi thấy cần, mọi tin); **Bạn nhắn tay thì A.I. nhường** bao lâu. Hai ô sau là cài đặt chung của cả bot, bảng nói rõ điều này. Có lối **Mở cài đặt bot**.
- **Kênh**: logo, tên kênh và nick hay Page.

Hai điều nên biết:

- Lượt bot đang soạn dở đúng lúc bạn tiếp quản vẫn gửi nốt câu đó. Cắt ngang một câu đang gửi còn khó hiểu hơn với khách.
- Tiếp quản là theo **từng cuộc chat**, không tắt bot. Các khách khác vẫn được bot trả lời.

## Tab Kênh

Từ 0.377.0 mọi nick và Page nằm ở tab **Kênh** (trước đó là mục "Kênh chưa có bot" dưới tab Bot). Bên trái: nút **Kết nối kênh mới**, công tắc **Xem mọi brain**, rồi từng kênh với logo thật và các nick hay Page của nó; mỗi dòng nói A.I. nào đang trực (hoặc "Chưa có A.I.", "Không cần A.I.") và số chat Cần bạn. Kênh có từ hai nơi thì có **Gắn A.I. cho nhiều Page**: tick các nơi, chọn bot, bấm Lưu.

Bấm một nick hay Page, bên phải hiện:

- **A.I. trực Page này**: một hộp chọn bot. Đổi xong mới hiện **Huỷ** và **Lưu**; chưa bấm Lưu thì chưa có gì thay đổi. Chọn **Không cần A.I.** là nơi đó chỉ ghi lại tin và không bị đếm vào số việc trên tab. Đổi bot thì các cuộc chat cũ của nơi đó cũng theo bot mới. Bot cũ hết nơi để trực thì tự tắt, và Javis nói ra.
- **Thông tin**: nút cạnh hộp chọn bot. Bấm vào là thẻ tài khoản hiện lên dạng popup: trạng thái, ghi hội thoại, nhập tin cũ, sửa, xoá (như mô tả bên dưới), và **Cài đặt bot** khi đã có bot trực. Tài khoản đang lỗi thì nút có chấm đỏ. Từ 0.404.0 thẻ không còn nằm trên đầu danh sách chat.
- **Nhóm và người**: mỗi cuộc chat một công tắc **A.I. ở đây**, câu nói ai đang lo, nút **Cho phép** khi có người gọi A.I. ở nhóm chưa cho phép, và **Mở chat**. Mọi thay đổi có Hoàn tác. Chưa chọn A.I. trực thì công tắc mờ đi, bấm vào sẽ nhắc chọn ở ô phía trên.

Số trên tab Kênh là số nơi cần bạn xử lý: tài khoản lỗi, hoặc chưa có bot mà bạn chưa chọn "Không cần A.I.".

## Tab Thống kê

Bấm nút kỳ để mở bộ chọn ngày: chọn nhanh (hôm nay, hôm qua, 7, 30, 90 ngày qua, tháng trước, đầu tuần, đầu tháng đến nay) hoặc bấm ngày bắt đầu và ngày kết thúc trên lịch rồi **Áp dụng**. Javis nhớ kỳ bạn xem lần cuối. Từ 0.399.0 trang mở đầu bằng **khối lợi ích**: A.I. đã trả lời thay bạn bao nhiêu tin (so với kỳ trước), A.I. lo bao nhiêu phần trăm câu trả lời, **bạn được rảnh bao lâu** (ước 1 phút cho mỗi câu A.I. trả lời thay) và **bao nhiêu tin A.I. trả lời lúc bạn nghỉ** (21h đến 7h, theo múi giờ của brain). Bốn ô: Khách được phục vụ (kèm số khách mới, tức cuộc chat riêng có tin đầu tiên trong kỳ), Trả lời đầu tiên sau (A.I. so với trả lời tay, lấy mức điển hình), Trả lời tay, Đang chờ bạn (bấm vào là mở danh sách Cần bạn). Biểu đồ **Giờ khách nhắn nhiều nhất** có 24 cột, cột giờ bạn nghỉ tô đậm, ghi rõ giờ đông nhất. Dưới cùng là **A.I. và trả lời tay theo tài khoản** (mỗi nick một thanh hai màu kèm phần trăm A.I. lo của riêng nick đó) và A.I. trả lời theo bot. Từ 0.401.0 có ô **chọn tài khoản** cạnh nút kỳ: chọn một nick thì cả trang chỉ tính nick đó, nên nick có người gõ tay không kéo phần trăm của nick chỉ có A.I. trả lời. "Trả lời tay" là tin một người thật gõ, trong Javis hoặc trên điện thoại của chính nick đó. Số liệu tính từ hộp thư của Javis.

## Thẻ tài khoản kênh

Mọi tài khoản khách nhắn tới hiện thành **cùng một kiểu thẻ**, bất kể kênh: logo và tên kênh, tên tài khoản, trạng thái (đang chạy, đang tắt, lỗi kèm lý do), bot đang trực, số hội thoại và số chưa đọc, và các năng lực của kênh đó (vào nhóm, gửi file, trả lời từ Javis). Không kênh nào có mục riêng, kể cả Zalo. Kênh thêm về sau chỉ việc xuất hiện thêm một thẻ.

Có hai loại tài khoản, khác nhau ở cách có nó chứ không ở cách hiện ra:

**Tài khoản bot** (Telegram, Zalo Bot) là một token. Bấm **Thêm kênh**, chọn loại kênh, dán token, bấm **Kiểm tra** để Javis hỏi đúng nền tảng token đó là bot nào, đặt tên gợi nhớ rồi Lưu. Tài khoản bot ghi vào hộp thư khi bot trực nó đang bật; chưa có bot trực thì thẻ nói thẳng và có nút **Tạo bot cho kênh này** mở sẵn form Bot mới với kênh đó được tick.

### Tài khoản bot thuộc về một brain (0.62.4)

Trước 0.62.4 mục này hiện tài khoản của **mọi** brain, vì một token Telegram là tài khoản có thật ngoài đời nên nó không thuộc brain nào cả. Đúng về kỹ thuật nhưng khó dùng: đứng ở brain của mình mà nhìn một danh sách trộn lẫn thì không biết cái nào là của mình.

Từ 0.62.4 mỗi tài khoản có một **brain chủ**:

- **Thêm ở brain nào thì thuộc brain đó.** Mục chỉ hiện tài khoản của brain đang mở.
- **Form tạo bot cũng chỉ cho chọn tài khoản trong brain đó**, nên không còn tạo ra liên kết chéo brain.
- **Công tắc "Xem mọi brain"** ở đầu mục để tìm lại một tài khoản lỡ thêm nhầm chỗ. Khi đó mỗi thẻ tự ghi brain của nó, và mục liệt kê cả kênh đang do bot của brain khác trực (bot đó không hiện ở trang này, nên đây là chỗ duy nhất để sửa hoặc xoá kênh ấy). Zalo cá nhân là kết nối ở trang Kết nối nên không thuộc brain nào và brain nào cũng thấy.
- **Đổi chủ:** bấm **Sửa**, chọn lại ở mục **Brain của tài khoản**. Lịch sử hội thoại giữ nguyên, vì nó khoá theo id tài khoản chứ không theo brain.
- **Tài khoản cũ không đoán ra được chủ** (lúc nâng cấp không có bot nào trực nó) thì để **chưa gán** và hiện ở **mọi** brain kèm ghi chú. Chủ ý: thà thấy thừa một thẻ còn hơn có một token tồn tại mà không màn hình nào hiện ra, không ai xoá hay gắn lại được. Gắn nó vào một bot là nó nhận brain của bot đó.

Zalo cá nhân (`kind: account`) không bị lọc: nó là một kết nối ở trang **Kết nối**, không thuộc brain nào, nên luôn hiện.

Đây là bước đầu của hướng dài hơn: chia quyền quản lý tài khoản cho brain, rồi tới agent, skill, workflow và chatbot, để sau này lên được bản nhiều người dùng.

**Xoá một tài khoản:** bấm **Xoá**. Nếu đang có bot trực nó, Javis nói rõ bot nào, ở brain nào, rồi hỏi một câu duy nhất: gỡ khỏi bot đó rồi xoá luôn? Đồng ý là xong trong một lần, không phải đổi brain rồi đi tìm bot để tự gỡ. Bot vẫn còn và vẫn trực các tài khoản khác của nó. Nếu đó là tài khoản **duy nhất** của bot thì Javis nói trước, và sau khi xoá sẽ tắt bot đó đi (bản ghi bot vẫn còn, gắn tài khoản khác vào là bật lại được). Hội thoại đã ghi vẫn nằm nguyên trong hộp thư.

**Tài khoản của chính bạn** (Zalo cá nhân) đến từ trang **Kết nối** (quét QR ở Zalo Agent MCP) và hiện ở đây với công tắc **Ghi hội thoại**. Bật lên là Javis đọc tin mới mỗi 20 giây qua MCP và đổ vào hộp thư. Ba điều về kênh này, nói thẳng:

- **Mặc định tắt.** Bật là giữ phiên Zalo của bạn sống liên tục qua API không chính thức, tức tài khoản đăng nhập 24/7 trên máy chạy Javis. Đó là lựa chọn của bạn, không phải của Javis. Nên dùng tài khoản phụ.
- **Chỉ lưu từ lúc bật.** Không kéo lịch sử cũ. Tin do chính bạn (hay nhân viên dùng chung nick) gửi từ điện thoại hiện là tin "Bạn". Với Zalo cá nhân điều này cần Javis 0.108.0 trở lên: các bản trước dùng javis-zalo 1.2.0, bản đó bỏ mọi tin của chính tài khoản khỏi luồng tin mới nên tin bạn nhắn tay không bao giờ vào Hộp thư.
- **Không có bot trực.** Trả lời từ Hòm thư bot là gửi dưới tên bạn. Muốn nick này tự trả lời khách thì tạo một Bot chuyên trách và chọn kênh Zalo cá nhân (chat riêng từ 0.64.80, nhóm và chế độ Tự đánh giá từ 0.64.82), xem [Chatbot](25-chatbot.md).

## Dữ liệu lưu ở đâu, giữ gì

Kho nằm trong thư mục trạng thái của Javis (`customer_conversations.sqlite3`), tách khỏi kho phiên chat. Giữ **chữ** lâu dài; ảnh, file, tin thoại chỉ giữ loại tin và mô tả, file gốc theo hạn dọn của Javis. Tin trùng (đọc lại cùng một tin sau khi khởi động lại) không sinh dòng thứ hai.

Xoá một bot **không** xoá hội thoại của nó, và cũng không xoá tài khoản kênh nó trực: lịch sử khách là tài sản của bạn, token là thứ dùng lại được. Bot tạo trước 0.61.0 (token nằm trong bot) tự chuyển sang mô hình tài khoản khi bạn cập nhật; token, hội thoại, nhóm cho phép đều giữ nguyên.

## Cho ai muốn nối thêm kênh

Từ 0.61.0 mọi thứ lõi biết về một kênh nằm trong **sổ đăng ký kênh** (`server/channels/`, mỗi kênh một file). Một file kênh khai: id, tên, khoá logo, loại (`bot` dùng token, `account` dùng phiên đăng nhập sẵn có, `webhook` cho nền tảng gọi ngược), năng lực (nhóm, gửi chữ, gửi file), cách lấy token; và một bộ hàm: kiểm token và lớp long-poll (loại bot), liệt kê tài khoản và bật ghi (loại account), `gui` để trả lời từ Javis. Tin nhận về thì đưa về khuôn chung (`channel`, `account_id`, `external_chat_id`, `sender_type`, `text`, `external_message_id`, `created_at`) rồi gọi kho.

Thêm một kênh = thêm một file ở sổ, một dòng đăng ký, một logo trong `icons.js`. Kho bot, bộ giám sát, API và cả hai tab tự nhận, không sửa gì khác. Chi tiết ở `docs/dev/2026-09-kenh-hoi-thoai-spec.md`. Đường API:

- `GET /channels` các loại kênh và năng lực; `GET /channels/accounts` mọi tài khoản, một khuôn.
- `POST /channels/verify-token`, `POST /channels/accounts`, `POST /channels/accounts/{id}/update`, `.../watch` (loại account), `.../delete`.
- `POST /conversations/{id}/ai-reply` (từ 0.65.5): `mode=send` hoặc `draft`; lỗi trả `code` (`human`, `bot_off`, `no_bot`, `already_answered`, `busy`, `no_message`, `send_failed`, `engine`).
- `GET /conversations` danh sách kèm số liệu, lọc theo `channel`, `bot_id` (`-` = cuộc chat không có bot), `account_id`, `q`, và từ 0.65.3 `status` (`unread`, `need_reply`, `human`) và `chat_type` (`group`, `private`; giá trị lạ thì bỏ qua bộ lọc đó). Trả thêm `bot_name` và `need_reply` cho từng dòng, `facets` (số đếm cho dropdown, toàn hòm thư) và `bots` (bot có hội thoại, kèm tên).
- `GET /conversations/{id}/messages` lịch sử tin; `POST /conversations/{id}/reply` trả lời qua kênh.
- `POST /conversations/{id}/read`, `POST /conversations/{id}/mode` (`ai` hoặc `human`).
- `GET /conversations/channels` và `POST /conversations/zalo/{conn_id}/watch` là bí danh cũ, còn giữ.

## Xử lý lỗi

- **Bot đang bật mà không thấy hội thoại nào**: kho chỉ ghi từ lúc kênh được nối; nhắn thử cho bot một câu. Nếu vẫn trống, bấm Nhật ký trên thẻ bot ở tab Bot.
- **Thẻ bot báo "chưa có tài khoản kênh nào"**: bot chưa trực token nào. Bấm Sửa, tích một tài khoản có sẵn hoặc dán token mới.
- **Gửi từ Hòm thư bot báo lỗi**: câu lỗi là của chính nền tảng (token bị thu hồi, khách đã chặn bot, phiên Zalo hết hạn). Tin không đi thì không được ghi vào kho.
- **Zalo cá nhân báo lỗi đỏ ở tab Kênh**: thường là phiên QR hết hạn hoặc máy thiếu Node.js 20. Vào trang Kết nối kiểm tra kết nối Zalo, quét QR lại nếu cần. Vòng đọc tự thử lại sau 90 giây.
- **Gạt sang Tôi trả lời mà bot vẫn trả lời một câu**: đó là lượt đã chạy dở từ trước khi bấm. Từ tin sau bot im.

## Muốn hơn thế: gói Quản lý khách hàng (CRM)

Kho cài đặt có gói **Quản lý khách hàng (CRM)** (`javis.khach-hang-crm`, cần bản 0.60.1 trở lên) đặt lên chính hộp thư này. Cài xong hỏi Javis bằng lời: "khách nào chờ hơn 2 tiếng chưa được trả lời", "chị Lan đã hỏi gì", "gắn tag VIP cho chị Lan", "tuần này bao nhiêu khách mới", "xuất danh sách khách đã hỏi giá ra Excel". Kèm một trợ lý chăm sóc khách và một quy trình rà soát mỗi ngày. Gói chỉ đọc hộp thư và ghi tag, ghi chú lên khách; không gửi tin cho ai.

## Tham khảo

- [Chatbot (Bot chuyên trách)](25-chatbot.md)
- [Kênh Zalo Bot](26-kenh-zalo-bot.md)
- [Zalo Agent MCP](12-zalo.md)
