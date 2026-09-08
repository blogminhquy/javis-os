# Việc định kỳ & Nhắc hẹn

***Tiếng Việt** · [English](en/08-recurring-jobs.md)*

Trang **Việc định kỳ** là nơi bạn giao cho Javis những việc tự chạy khi bạn không ngồi trước máy: việc lặp theo chu kỳ (gọi là **loop**) và nhắc hẹn theo mốc giờ. Mỗi việc lặp tự thức dậy đúng chu kỳ, làm đúng một nhiệm vụ bạn mô tả, tự kiểm chứng rồi ghi nhật ký và nhắn kết quả về Telegram cho bạn.

Trang này gộp việc của **mọi brain**, không chỉ brain đang chọn ở thanh bên.

## Tính năng này là gì

Hai loại việc sống chung một trang:

| Loại | Bản chất | Lưu ở đâu |
|---|---|---|
| 🔁 **Việc lặp** (loop) | Cứ mỗi N phút lại tự thức dậy làm đúng một việc rồi dừng. Chạy vô hạn cho tới khi bạn tắt. | Một file `.md` trong `Javis/loops/` của brain |
| ⏰ **Nhắc hẹn** | Một mốc giờ cụ thể ("30 phút nữa", "8h30"), hoặc lịch cron lặp theo giờ cố định ("7h sáng mỗi ngày"). | `Javis/reminders.json` của brain |

Điểm khác nhau quan trọng: việc lặp tính theo **khoảng cách** giữa hai lần chạy, nhắc hẹn tính theo **mốc giờ**. "Mỗi 2 tiếng quét đơn" là việc lặp; "7h sáng nào cũng báo doanh thu" là nhắc hẹn dùng cron.

Bạn tạo được **nhiều việc lặp song song**, mỗi việc một file riêng. Nhưng chúng chạy **tuần tự**: tại một thời điểm toàn hệ thống chỉ có đúng một vòng đang chạy. Bộ đếm lịch của Javis kiểm tra mỗi 30 giây, mỗi lần kiểm chỉ chọn **một** việc lặp quá hạn lâu nhất để chạy. Vì vậy thời điểm chạy thật có thể lệch vài chục giây so với chu kỳ bạn đặt, và nếu đặt nhiều việc cùng lúc thì chúng xếp hàng chứ không chạy chồng nhau.

Loop **đọc được dữ liệu thật qua MCP** (POS, quảng cáo, lịch, analytics...) để làm việc. Nó có ghi được file hay có thao tác thật ra ngoài hay không thì tuỳ **mức quyền** bạn chọn, xem mục "Ba mức quyền" bên dưới.

Việc lặp được sửa trực tiếp bằng cách mở file `.md` trong Obsidian hoặc trang [Quản lý tệp tin](05-quan-ly-tep-tin.md). Trạng thái chạy (lần cuối, số vòng hôm nay, chuỗi lỗi) nằm tách ở `Javis/loop-state.json`, do server sở hữu, nên bạn sửa file định nghĩa mà không sợ giẫm chân.

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định `http://localhost:7777`).
2. Nhìn thanh điều hướng bên trái, bấm nhóm **Việc** để mở ra.
3. Bấm mục **Việc định kỳ**.

Trang mở ra với phụ đề "Việc định kỳ + nhắc hẹn đang chờ". Từ trên xuống dưới bạn thấy: một đoạn giới thiệu ngắn, hàng nút **+ Thêm việc** và **■ Dừng vòng đang chạy**, ô tìm kiếm, danh sách thẻ việc gom theo brain, cuối cùng là khối **Nhật ký gần đây**.

Biểu mẫu tạo/sửa việc bị ẩn cho tới khi bạn bấm **+ Thêm việc** hoặc **Sửa** trên một thẻ.

## Cách dùng (từng bước)

### Bước 1: Bấm "+ Thêm việc"

Biểu mẫu hiện ra ngay dưới hàng nút.

### Bước 2: Chọn loại việc

Ở mục **Loại việc** có hai nút: **🔁 Việc lặp** (chọn sẵn) và **⏰ Nhắc hẹn**. Bấm để đổi. Chọn loại nào thì biểu mẫu đổi các ô bên dưới theo loại đó.

Lưu ý: khi bạn bấm **Sửa** trên một thẻ có sẵn, hai nút này bị khoá và mờ đi. Biểu mẫu chỉ sửa được việc lặp; nhắc hẹn thì chỉ huỷ hoặc chuyển brain ngay trên thẻ.

### Bước 3: Đặt tên và mô tả

- **Tên**: tên ngắn hiện trên thẻ, ví dụ "Đọc email mỗi 2 tiếng". Bỏ trống thì báo "Nhập tên".
- **Mô tả nhiệm vụ (mỗi vòng Javis làm đúng việc này)**: đây là ô **bắt buộc** và là thứ quan trọng nhất. Javis không tự nghĩ ra việc; mỗi vòng nó làm đúng cái bạn viết trong ô này rồi dừng. Bỏ trống thì báo "Nhập mô tả nhiệm vụ (Javis cần biết mỗi vòng làm gì)".

Khi bạn chọn **⏰ Nhắc hẹn**, nhãn ô mô tả đổi thành "Nội dung nhắc (Javis sẽ nhắc hoặc làm đúng việc này)", và báo lỗi khi để trống là "Nhập nội dung nhắc".

Viết mô tả càng cụ thể càng tốt: nói rõ đọc gì, làm gì, lưu vào đâu. Viết tự đủ, đừng phụ thuộc ngữ cảnh cuộc chat hiện tại, vì việc sẽ chạy lúc không ai ngồi đó. Ví dụ:

> Mỗi vòng đọc 1 source chưa xử lý trong 06 - Sources rồi đề xuất Wiki page nên tạo.

> Đọc số đơn hôm nay qua MCP POS, nếu thấp thì soạn nháp 1 caption đẩy hàng vào 05 - Projects.

### Bước 4a (việc lặp): Chọn chế độ và chu kỳ

- **Chế độ**: ba nút **Đề xuất (chỉ đọc)**, **Tự làm (an toàn)**, **⚠ Toàn quyền**. Mặc định của việc mới là **Đề xuất (chỉ đọc)**. Xem mục "Ba mức quyền" bên dưới trước khi đổi.
- **Chu kỳ (phút, tối thiểu 5)**: số phút giữa hai lần chạy. Ô điền sẵn **120**. Nhập nhỏ hơn 5 thì server tự nâng lên 5.

Dưới biểu mẫu có dòng nhắc: "Đề xuất = chỉ đọc + gợi ý. Tự làm (an toàn) = ghi nháp file + đọc MCP, KHÔNG tiền/đơn/đăng bài. Toàn quyền = tự thao tác mọi thứ."

### Bước 4b (nhắc hẹn): Đặt "Khi nào" và "Kiểu"

- **Khi nào**: ô nhập thời điểm. Xem đầy đủ các dạng nó hiểu ở mục Ô "Khi nào" hiểu những gì bên dưới. Bỏ trống thì báo lỗi `Nhập thời điểm (vd "30 phút nữa", "8h30", "0 7 * * *")`.
- **Kiểu**: hai nút **⏰ Chỉ nhắc** (chọn sẵn) và **🤖 Tự làm rồi báo**.
  - **⏰ Chỉ nhắc**: tới giờ Javis bắn thẳng một tin Telegram, mở đầu bằng "⏰ Nhắc anh: " rồi tới nội dung bạn viết. Không gọi model, không tốn token.
  - **🤖 Tự làm rồi báo**: tới giờ Javis chạy engine để **làm** việc đó rồi gửi kết quả về Telegram.
- **Được phép làm gì** (chỉ hiện khi chọn 🤖 Tự làm rồi báo): ba mức, mặc định **Toàn quyền**.
  - **Chỉ đọc**: đọc dữ liệu thật qua MCP và đọc file, rồi báo lại. Không ghi gì, không làm gì ra ngoài.
  - **Ghi file**: thêm quyền ghi file nháp trong brain. Vẫn không tạo đơn, tiêu tiền, đăng bài hay gửi tin.
  - **Toàn quyền** (mặc định): dùng được mọi công cụ bạn đã đấu, gồm cả hành động ra ngoài. Đây là mức duy nhất làm được những việc kiểu "tới giờ thì gửi tin", "tới giờ thì đăng bài", "tới giờ thì đặt lịch".

  Vì sao mặc định là Toàn quyền: nhắc hẹn làm **đúng một việc bạn đã viết ra và hẹn giờ**, tức là một câu lệnh trong chat được dời sang giờ khác. Trói nó chặt hơn lúc bạn đang ngồi chat thì thành ra bạn dặn "10h mai gửi giúp tôi" mà tới 10h nó báo về là không được phép gửi. Đổi lại, khi chọn mức này form hiện một ô cảnh báo đỏ, và thẻ việc gắn nhãn **toàn quyền** để bạn liếc một cái là biết. Cần nhớ: **việc chạy khi không có ai ngồi cạnh**, không có bước duyệt nào, và gửi tin hay đăng bài thì không rút lại được. Chỉ giao thứ bạn sẵn sàng để nó tự làm.

### Bước 5: Chọn brain

Ô **Brain (nơi lưu việc)** cho chọn brain sẽ chứa việc này, mặc định là brain bạn đang xem ở thanh bên. Khi **Sửa** một việc lặp có sẵn, ô này bị khoá về đúng brain của nó. Muốn dời việc sang brain khác thì dùng ô **Chuyển brain…** trên thẻ, chứ đừng đổi lúc sửa.

### Bước 6: Lưu

Bấm **💾 Lưu**. Nút đổi thành "Đang lưu..." rồi trở lại. Lưu xong biểu mẫu tự đóng và danh sách tải lại. Lỗi thì hiện ngay cạnh nút, dạng "⚠ ..." màu vàng cam.

Nếu bạn chọn chế độ **⚠ Toàn quyền**, trước khi lưu sẽ có một hộp thoại xác nhận nhắc lại rủi ro. Bấm huỷ ở đó là không lưu gì cả.

### Bước 7: Bật việc lên

**Việc lặp mới tạo từ dashboard luôn ở trạng thái TẮT.** Đây là chủ ý an toàn: bạn xem lại mô tả, xong mới bấm **Bật** trên thẻ của nó. Chưa bấm Bật thì nó không bao giờ tự chạy.

Nhắc hẹn thì khác: tạo xong là đã ở hàng chờ, không cần bật.

## Ba mức quyền (chế độ của việc lặp)

| Nút trên biểu mẫu | Nhãn trên thẻ | Javis được làm gì |
|---|---|---|
| **Đề xuất (chỉ đọc)** | đề xuất | Chỉ dùng công cụ đọc, kể cả đọc dữ liệu thật qua MCP. **Không ghi file**. Mỗi vòng nêu 2-3 đề xuất hành động cụ thể. An toàn nhất, mặc định. |
| **Tự làm (an toàn)** | tự làm (an toàn) | Đọc MCP + **ghi được file** trong brain (tạo/sửa note nháp). Vẫn bị chặn cứng mọi hành động tiền, đơn hàng, quảng cáo, đăng bài, gửi tin. Có thêm bước tự kiểm chứng sau mỗi vòng. |
| **⚠ Toàn quyền** | ⚠ toàn quyền | Mở hết: mọi công cụ và mọi MCP, **thao tác thật ra bên ngoài** không cần hỏi. |

Chọn **⚠ Toàn quyền** thì một khối cảnh báo đỏ hiện ngay trong biểu mẫu, nguyên văn mở đầu: "**⚠ CHẾ ĐỘ TOÀN QUYỀN - rủi ro cao.** Loop sẽ tự thao tác THẬT qua MCP không cần hỏi: có thể **tạo/sửa đơn hàng, chạy quảng cáo (tiêu tiền thật), gửi tin nhắn/email, đăng bài**."

Hãy đọc kỹ chỗ này: loop toàn quyền chạy nền theo lịch, **không có người duyệt từng bước**, và **hành động thật thì không hoàn tác được**. Javis hỏi xác nhận hai lần (một lần khi lưu, một lần nữa khi bạn bấm **Bật**) chính vì lý do đó. Nếu cần chế độ này, hãy chạy thử ở **Đề xuất (chỉ đọc)** vài vòng trước, đọc nhật ký xem nó định làm gì, và viết mô tả nhiệm vụ thật hẹp về phạm vi.

## Ô "Khi nào" hiểu những gì

Ô này nhận bốn dạng, gợi ý sẵn trong ô là `30 phút nữa · 8h30 · 0 7 * * * · 2026-07-20 09:00`:

| Bạn gõ | Javis hiểu |
|---|---|
| `30 phút nữa`, `2 tiếng nữa`, `1.5 giờ`, `3 ngày` | Đếm ngược kể từ bây giờ. Đơn vị nhận: phút, tiếng, giờ, ngày (có dấu hoặc không dấu đều được). |
| `8h30`, `8:30`, `8h` | Mốc giờ trong ngày. Nếu giờ đó đã qua rồi thì tự dời sang **ngày mai**. |
| `2026-07-20 09:00` | Ngày giờ cụ thể. |
| `0 7 * * *` | Biểu thức cron 5 trường (phút, giờ, ngày, tháng, thứ). Đây là **lịch lặp**: cứ tới giờ đó là chạy, chạy xong tự tính lần kế tiếp. `0 7 * * *` = 7h sáng mỗi ngày. Macro `@daily`, `@hourly`, `@weekly`, `@monthly` cũng nhận. |

Mọi giờ tính theo giờ Việt Nam (UTC+7). Ba dạng đầu là hẹn **một lần** (chạy xong thì biến khỏi danh sách chờ); cron thì lặp mãi tới khi bạn huỷ. Hẹn một lần không được xa quá khoảng một năm.

## Danh sách việc

### Gom theo brain

Mỗi brain một khối, tiêu đề `🧠 <tên brain>`, kèm nhãn nhỏ **đang xem** cho brain bạn đang chọn ở thanh bên và **mặc định** cho brain mặc định. Brain đang xem được đẩy lên đầu. Brain không có việc nào và cũng không phải brain đang xem thì bị ẩn đi cho gọn.

Trong mỗi khối, việc lặp liệt kê trước, rồi tới mục **Nhắc hẹn đang chờ**.

Brain đang xem mà chưa có việc thì hiện dòng "Chưa có việc nào ở brain này. Bấm **+ Thêm việc**, hoặc nói với Javis trong chat." Cả hệ thống chưa có việc nào thì hiện "Chưa có việc định kỳ hay nhắc hẹn nào."

### Ô tìm kiếm

Ô **🔍 Tìm việc theo tên...** ở trên danh sách lọc thẻ ngay khi bạn gõ, **bỏ dấu tiếng Việt** nên gõ "kho" vẫn khớp "khô", gõ "email" vẫn khớp "Email". Nhóm brain nào không còn thẻ nào khớp thì tự ẩn. Không khớp gì cả thì hiện "Không có việc nào khớp."

### Đọc một thẻ việc lặp

Thẻ bắt đầu bằng `🔁 <tên việc>` kèm slug (tên file) mờ ở bên cạnh, và một trạng thái ở góc phải:

| Trạng thái | Nghĩa |
|---|---|
| ⏳ đang chạy | Vòng của chính việc này đang chạy ngay lúc đó |
| ⚠ tự tạm dừng | Đã hỏng 3 lần liên tiếp nên Javis tự khoá lại, xem mục "Tự tạm dừng" |
| ● bật | Đang bật, sẽ tự chạy theo chu kỳ |
| ○ tắt | Đang tắt, không tự chạy (thẻ hiển thị mờ) |

Dòng thứ hai ghi chế độ và chu kỳ, ví dụ `tự làm (an toàn) · mỗi 120 phút`, kèm các thông tin nâng cao nếu có: tên loại nhiệm vụ cũ (khi khác "Tự định nghĩa"), `im lặng 23-07`, `tối đa 3/ngày (đã 1)`, `⚙ code · <thư mục>`.

Dòng thứ ba là lịch sử ngắn: `lần cuối HH:MM` (hoặc `chưa chạy`), kết quả kiểm chứng gần nhất (` · ok` nếu sạch, hoặc `· ✓ Đạt: ...` / `· ✗ Chưa đạt: ...`), và `· kế tiếp ~HH:MM` nếu đang bật. Việc đang tự tạm dừng thì có thêm một dòng `⚠` ghi rõ lý do và thời điểm.

### Đọc một thẻ nhắc hẹn

Thẻ nhắc hẹn gọn hơn: tên (hoặc nội dung nếu không đặt tên), rồi một dòng phụ ghi thời điểm và kiểu. Kiểu là `nhắc` (chỉ nhắc), `tự làm + báo`, hoặc `script`. Riêng `tự làm + báo` có thêm nhãn mức quyền (`chỉ đọc`, `được ghi file`, hoặc `toàn quyền` in đỏ).

Thời điểm luôn nói rõ **bao giờ chạy**, không bắt bạn tự đọc cron:

- Hẹn một lần: `một lần, kế tiếp mai 08:30 (còn 14 giờ)`.
- Lịch lặp cron: lịch dịch thành lời rồi mới tới lần chạy kế tiếp, ví dụ `7:00 mỗi ngày · kế tiếp mai 07:00 (còn 14 giờ)`. Biểu thức thô vẫn in bên cạnh dạng `0 7 * * *` cho ai muốn kiểm.
- Lặp theo khoảng cách: `lặp mỗi 60 phút · kế tiếp hôm nay 15:20 (còn 12 phút)`.

Giờ trong ngày hôm nay ghi `hôm nay HH:MM`, ngày mai ghi `mai HH:MM`, xa hơn ghi `HH:MM DD/MM`.

Nếu lần chạy trước bị lỗi (ví dụ không gửi được tin), thẻ có thêm một dòng `⚠ lần chạy trước lỗi: ...` để bạn biết mà xử lý, thay vì im lặng chạy sai mãi.

### Các nút trên thẻ

Mọi nút đều nhắm đúng brain của chính thẻ đó, không phải brain đang chọn ở thanh bên.

Trên thẻ việc lặp:

- **Bật** / **Tắt**: gạt trạng thái. Bật một việc **⚠ Toàn quyền** sẽ hỏi xác nhận. Bật cũng xoá luôn trạng thái tự tạm dừng.
- **▶ Chạy ngay**: chạy một vòng ngay lập tức, không chờ tới chu kỳ. Nút đổi thành "Đang chạy..." và danh sách tự tải lại sau khoảng 2,5 giây. Lưu ý: nút này **không** lưu biểu mẫu đang mở, nó chạy đúng nội dung đã lưu trong file. Bấm Chạy ngay cũng xoá trạng thái tự tạm dừng vì đây là hành động chủ động của bạn.
- **Sửa**: mở lại biểu mẫu với nội dung của việc này.
- **Xoá**: hỏi xác nhận rồi xoá hẳn file `Javis/loops/<slug>.md`.
- **Chuyển brain…**: ô chọn để dời việc sang brain khác, giữ nguyên file và trạng thái chạy. Brain đích đã có việc trùng tên thì Javis từ chối và báo lỗi, không ghi đè. Việc đang chạy cũng không dời được, hãy thử lại sau.

Trên thẻ nhắc hẹn:

- **Sửa**: mở lại biểu mẫu với nội dung của nhắc hẹn này. Đổi được tên, nội dung, kiểu và giờ. Nếu là lịch cron thì ô "Khi nào" điền sẵn biểu thức cũ, sửa xong Javis tính lại lần chạy kế tiếp ngay. Nếu là hẹn một lần thì ô đó để trống và ghi giờ đang hẹn trong phần gợi ý: **để trống nghĩa là giữ nguyên giờ cũ**, chỉ gõ khi muốn đổi.
- **Huỷ**: ngừng chạy nhưng bản ghi vẫn nằm trong lịch sử để tra lại.
- **Xoá**: mất hẳn, không hoàn tác được.
- **Chuyển brain…**: dời sang brain khác, giữ nguyên id và mọi thiết lập.

## Chưa đấu Telegram thì Javis không tạo lịch

Nhắc hẹn và việc "tự làm rồi báo" chỉ có giá trị khi tới giờ nó **nói được với ai đó**, mà kênh báo duy nhất hiện nay là Telegram. Nếu bot Telegram chưa bật, chưa có token, hoặc chưa có Chat ID nào được phép, Javis **từ chối tạo** và nói rõ thiếu gì kèm lối sang trang [Kênh](11-telegram.md) để đấu.

Đây là chỗ trước đây gây hiểu lầm nhiều nhất: Javis dựng job "sáng nào cũng báo email và lịch", job chạy đúng giờ thật, nhưng kết quả không gửi được cho ai và cũng không ai nói cho bạn biết là thiếu Telegram.

Nếu bạn vẫn muốn tạo (ví dụ định đấu Telegram sau), bấm **Vẫn tạo** ngay cạnh lời cảnh báo. Việc sẽ chạy đúng giờ, kết quả lưu trong Javis, chỉ là chưa gửi đi đâu.

Khi trang Việc định kỳ phát hiện chưa có kênh báo, nó hiện một dải cảnh báo ở đầu trang, vì các việc đã tạo từ trước vẫn đang chạy mà không tới tay bạn.

Đặt lịch bằng lời qua chat cũng theo luật này: Javis phải soát trước xem nguồn dữ liệu đã đấu chưa và có chỗ báo kết quả chưa, thiếu thì nói thẳng rồi hỏi bạn, không tạo cho xong.

## Chạy ngay và dừng vòng đang chạy

Nút **■ Dừng vòng đang chạy** ở đầu trang huỷ vòng **đang chạy trên toàn hệ thống**, bất kể vòng đó thuộc việc nào. Vì mỗi lúc chỉ có một vòng chạy nên nút này không cần chọn việc. Nó chỉ cắt tiến trình đang chạy, **không tắt việc**: tới chu kỳ sau nó lại chạy tiếp. Muốn ngừng hẳn thì bấm **Tắt** trên thẻ.

Nút này không đụng tới nhắc hẹn kiểu "🤖 Tự làm rồi báo" đang chạy.

Trong lúc có một vòng chạy, trang tự làm mới danh sách mỗi 5 giây để bạn thấy trạng thái đổi.

## Bước tự kiểm chứng

Với chế độ **Tự làm (an toàn)** và **⚠ Toàn quyền**, sau khi làm xong việc, Javis chạy thêm một lượt kiểm tra độc lập: một "người soi" giả định kết quả vừa rồi là SAI, rồi đọc lại file liên quan để đối chiếu. Lượt kiểm chứng này **luôn chỉ được đọc**, kể cả với việc toàn quyền.

Bước này bị bỏ qua nếu vòng vừa rồi lỗi, hoặc kết quả nói "không có việc mới".

Tiêu chí soi thay đổi theo loại việc:

- Việc thường: kết quả có đúng mục tiêu không, có hợp lý và khả thi không, có bịa hay làm hỏng file nào không.
- Việc chạm số liệu kinh doanh: đề xuất có bám số thật không, có khả thi và đủ cụ thể không, có bịa số không.
- Việc làm dày Wiki: có đúng quy ước Wiki không, có bịa hay thiếu trích dẫn không, có làm hỏng link không.
- Việc dùng hồ sơ công cụ `code` (chỉ đặt được trong file `.md`): bắt buộc chạy `python -m py_compile` hoặc `node --check` cho từng file đã sửa và tất cả phải sạch, đồng thời diff phải nhỏ (dưới khoảng 80 dòng).

Với chế độ **Đề xuất** và **Tự làm (an toàn)** còn một tiêu chí cứng nữa: phát hiện bất kỳ hành động tiền, đơn hàng, quảng cáo, đăng bài hay gửi tin qua MCP là **trượt ngay**. Riêng chế độ **⚠ Toàn quyền** thì hành động thật là được phép, nên tiêu chí đổi thành: chỉ trượt nếu làm sai hoặc quá phạm vi nhiệm vụ, gây hại rõ ràng, hoặc đụng thứ ngoài ý bạn.

Kết quả hiện dạng **✓ Đạt** hoặc **✗ Chưa đạt** kèm lý do ngắn, cả trên thẻ lẫn trong nhật ký.

## Tự tạm dừng khi hỏng 3 lần

Nếu một việc lặp hỏng **3 lần liên tiếp** (engine lỗi, hoặc kiểm chứng ✗ Chưa đạt), Javis tự khoá nó lại và ghi lý do dạng "Tự tạm dừng 20/07 14:35: 3 lần lỗi/kiểm chứng không đạt liên tiếp". Thẻ chuyển sang **⚠ tự tạm dừng** và không tự chạy nữa cho tới khi bạn can thiệp.

Lý do này ghi vào trạng thái runtime, **không** sửa file `.md` của bạn. Muốn chạy lại, bấm **Bật** hoặc **▶ Chạy ngay** trên thẻ, cả hai đều xoá khoá và reset chuỗi lỗi. Trước khi bật lại, hãy đọc nhật ký xem nó hỏng vì cái gì.

## Báo cáo về Telegram

Đây là hành vi mặc định của Javis: **mỗi vòng chạy xong đều tự gửi kết quả về Telegram** cho người yêu cầu việc đó. Tin nhắn mở đầu bằng `✅ Loop '<tên việc>' vừa chạy...` (hoặc `⚠` nếu hỏng), rồi tới phần tóm tắt và dòng kiểm chứng.

Gửi cho ai:

- Việc tạo qua chat có gắn sẵn chat_id của người nói, nên báo về đúng người đó.
- Việc tạo trên dashboard không biết bạn là ai, nên báo về **ID Telegram đầu tiên** trong danh sách cho phép.

Muốn một việc ngừng báo mỗi vòng vì quá ồn, mở file `Javis/loops/<slug>.md` và đặt `notify: false` trong phần frontmatter.

Nhắc hẹn cũng bắn qua Telegram. Nhắc hẹn tạo trên dashboard không gắn người nhận nên gửi cho **mọi ID** trong danh sách cho phép; nhắc hẹn đặt bằng lời qua chat thì gửi đúng người đã đặt.

Cả hai đều cần bot đã bật, xem [Kênh Telegram](11-telegram.md). Chưa bật bot thì việc vẫn chạy và vẫn ghi nhật ký, chỉ là không có tin báo.

## Nhật ký gần đây

Khối cuối trang. Cạnh tiêu đề có một ô chọn để lọc:

- **Nhật ký brain đang xem**: gộp mọi việc lặp của brain đang chọn ở thanh bên.
- Hoặc chọn đúng một việc, hiển thị dạng `<tên việc> · <tên brain>`.

Javis tải 200 mục gần nhất rồi chia trang **10 mục** một trang, có nút **← Trước** và **Sau →**, kèm dòng đếm "Trang 1/5 · 47 mục". Chưa có gì thì hiện "Chưa có nhật ký."

Mỗi mục bắt đầu bằng dòng tiêu đề dạng `## [2026-07-20 14:35] doc-source · loop (custom/auto) - scheduled`, trong đó `scheduled` nghĩa là chạy theo lịch, `manual` nghĩa là bạn bấm **▶ Chạy ngay**. Bên dưới là tóm tắt việc đã làm, dòng **Kiểm chứng** nếu có, và dòng cảnh báo nếu chính vòng đó khiến việc bị tự tạm dừng.

Nhật ký cũng nằm trong brain dưới dạng file thật: `Javis/loop-log/YYYY-MM-DD.md`, mỗi ngày một file. Mở qua [Quản lý tệp tin](05-quan-ly-tep-tin.md) nếu muốn xem xa hơn 200 mục.

## Đặt lịch bằng lời trong chat

Bạn không bắt buộc phải vào trang này. Nói thẳng với Javis trong [Trò chuyện](02-tro-chuyen-va-giong-noi.md) hoặc qua Telegram cũng được, ví dụ:

- "Tạo cho anh việc mỗi 2 tiếng quét đơn mới rồi tổng hợp."
- "7h sáng nào cũng nhắc anh xem doanh thu hôm qua."
- "30 phút nữa nhắc anh gọi khách."
- "Còn việc gì đang chạy không?"
- "Huỷ việc quét đơn đi."

Javis dùng công cụ `javis_schedule` (một plugin đi kèm app) để tự chọn đúng kho: lịch lặp theo khoảng cách thì ghi file vào `Javis/loops/`; mốc giờ cố định lặp lại hoặc hẹn một lần thì vào kho nhắc hẹn. Công cụ này tự đặt slug đúng chuẩn và **chặn trùng tên**: đã có việc cùng tên thì nó báo lỗi và bảo bạn sửa cái cũ, chứ không đẻ bản sao.

Hai rào an toàn cứng của đường này, không tham số nào đổi được:

- Việc lặp tạo qua chat **luôn** ở `enabled: false` và `mode: suggest`. Bạn phải vào trang Việc định kỳ bấm **Bật** thì nó mới chạy thật.
- Không rõ chu kỳ (ví dụ bạn chỉ nói "mỗi sáng" mà không kèm giờ) thì công cụ báo lỗi và hỏi lại, tuyệt đối không tự đoán.

## Trường nâng cao (chỉ sửa được trong file .md)

Biểu mẫu trên dashboard cố ý giữ gọn. Những thứ dưới đây phải mở `Javis/loops/<slug>.md` và sửa phần frontmatter (qua [Quản lý tệp tin](05-quan-ly-tep-tin.md) hoặc Obsidian). Sửa xong, dashboard đọc lại ngay, không cần khởi động lại gì.

| Trường | Ý nghĩa |
|---|---|
| `quiet_hours` | Giờ im lặng, dạng `23-07` (không chạy từ 23h tới 7h, giờ Việt Nam). Chỉ nhận số giờ tròn. |
| `max_runs_per_day` | Trần số vòng mỗi ngày. `0` = không giới hạn. Thẻ hiện `tối đa N/ngày (đã M)`. |
| `workspace` | `vault` (mặc định, chạy trong brain) hoặc một đường dẫn thư mục tuyệt đối. Thư mục không tồn tại thì vòng chạy sẽ báo lỗi ngay. |
| `tools_profile` | `vault-safe` (mặc định) hoặc `code`. Hồ sơ `code` mở Bash, WebFetch, WebSearch và làm việc trong `workspace`, nhưng **tắt hết MCP**. Đây là hồ sơ để loop sửa mã nguồn trong một thư mục bạn giao, và nó thật sự sửa được file trong đó, hãy cân nhắc kỹ. |
| `ambient_mcp` | Mặc định tắt. Đặt `true` để việc lặp thấy lại các connector cài trên máy (Gmail, Drive, lịch qua claude.ai). Bật thì vẫn chặn cứng Bash, WebFetch, WebSearch. |
| `owner_chat` | chat_id Telegram nhận báo cáo. Để trống thì báo về ID đầu tiên trong danh sách cho phép. |
| `notify` | `false` để tắt báo cáo mỗi vòng của riêng việc này. |
| `goal` | Loại nhiệm vụ. Mặc định và cũng là thứ dashboard luôn tạo ra là `custom`, nghĩa là mỗi vòng làm đúng phần thân file. Các giá trị cũ `business`, `brain`, `product` vẫn chạy được cho file viết tay, và khi khác `custom` thì thẻ hiện thêm nhãn phụ. |

Phần **thân file** (bên dưới dấu `---` thứ hai) chính là ô "Mô tả nhiệm vụ" bạn gõ trên biểu mẫu.

## Bảng tra nhanh nút và trạng thái

| Bạn thấy | Ý nghĩa / thao tác |
|---|---|
| **+ Thêm việc** | Mở biểu mẫu tạo việc mới |
| **■ Dừng vòng đang chạy** | Huỷ vòng đang chạy trên toàn hệ, không tắt việc |
| **🔁 Việc lặp** / **⏰ Nhắc hẹn** | Chọn loại việc (khoá khi đang sửa) |
| **Đề xuất (chỉ đọc)** | Chỉ đọc, không ghi file. Mặc định |
| **Tự làm (an toàn)** | Ghi file nháp trong brain, cấm tiền/đơn/đăng bài |
| **⚠ Toàn quyền** | Thao tác thật ra ngoài. Hỏi xác nhận 2 lần |
| **⏰ Chỉ nhắc** | Tới giờ bắn tin "⏰ Nhắc anh: ..." |
| **🤖 Tự làm rồi báo** | Tới giờ chạy engine làm việc rồi báo kết quả |
| **Được phép làm gì** | Mức quyền của kiểu Tự làm: Chỉ đọc / Ghi file / Toàn quyền (mặc định) |
| **💾 Lưu** / **Huỷ** | Lưu hoặc đóng biểu mẫu |
| Ô **🔍 Tìm việc theo tên...** | Lọc thẻ theo tên, bỏ dấu tiếng Việt |
| **Bật** / **Tắt** | Gạt trạng thái chạy nền của một việc lặp |
| **▶ Chạy ngay** | Chạy một vòng ngay, xoá trạng thái tự tạm dừng |
| **Sửa** / **Xoá** | Sửa hoặc xoá hẳn file việc lặp |
| **Chuyển brain…** | Dời việc sang brain khác |
| **Sửa** (trên thẻ nhắc hẹn) | Đổi tên, nội dung, kiểu, giờ hoặc biểu thức cron |
| **Huỷ** (trên thẻ nhắc hẹn) | Ngừng chạy, vẫn giữ trong lịch sử |
| **Xoá** (trên thẻ nhắc hẹn) | Xoá hẳn bản ghi, không hoàn tác |
| **Vẫn tạo** | Tạo lịch dù chưa đấu kênh báo kết quả |
| ⏳ đang chạy | Vòng của việc này đang chạy |
| ⚠ tự tạm dừng | Hỏng 3 lần liên tiếp, đã tự khoá |
| ● bật / ○ tắt | Có tự chạy theo chu kỳ hay không |
| ✓ Đạt / ✗ Chưa đạt | Kết quả bước tự kiểm chứng |
| **← Trước** / **Sau →** | Lật trang nhật ký, 10 mục mỗi trang |

## Mẹo

- **Bắt đầu bằng Đề xuất (chỉ đọc).** Cho chạy vài vòng, đọc nhật ký xem chất lượng đề xuất thế nào, rồi mới nâng lên **Tự làm (an toàn)**.
- **Đừng đặt chu kỳ quá dày.** 5-10 phút một vòng tốn token và tài nguyên máy thật. Đa số nhu cầu chỉ cần vài giờ một lần. Theo dõi mức tiêu ở [Mức dùng: token & chi phí](23-muc-dung-token.md).
- **Dùng model rẻ cho việc nền.** Trang [Models & engine](10-models-va-engine.md) có khối "Model việc nền" áp cho cả loop, việc Kanban, nhắc hẹn và tự học. Chọn một model rẻ ở đó là tiết kiệm được nhiều.
- **Đặt `quiet_hours` cho việc chạy ban đêm.** Nếu bạn để báo cáo Telegram bật, việc chạy lúc 3h sáng sẽ đánh thức bạn. Thêm `quiet_hours: 23-07` vào file, hoặc đặt `notify: false`.
- **Một việc = một nhiệm vụ.** Mô tả ôm đồm nhiều việc thì mỗi vòng nó làm dở dang một mẩu. Tách thành nhiều việc lặp riêng, mỗi cái một chu kỳ, dễ đọc nhật ký hơn nhiều.
- **Việc nào không cần suy nghĩ thì đừng gọi model.** Nhắc kiểu "⏰ Chỉ nhắc" không tốn token nào cả.

## Sự cố thường gặp

**Đã tạo việc nhưng nó không bao giờ chạy.** Việc lặp tạo từ dashboard (và từ chat) mặc định **tắt**. Xem thẻ có đang ở **● bật** không; nếu là **○ tắt** thì bấm **Bật**.

**Bấm ▶ Chạy ngay mà không thấy gì.** Ba khả năng. Một là đang có vòng khác chạy ở đâu đó (toàn hệ chỉ một vòng cùng lúc) nên yêu cầu bị bỏ qua im lặng; đợi một chút rồi bấm lại. Hai là vòng cần thời gian, hãy đợi rồi tải lại trang và xem **Nhật ký gần đây**. Ba là engine chưa sẵn sàng, xem mục dưới.

**Thẻ hiện ⚠ tự tạm dừng.** Việc này đã hỏng 3 lần liên tiếp. Mở nhật ký, lọc đúng việc đó, đọc lý do. Sửa mô tả nhiệm vụ cho rõ hơn rồi bấm **Bật** hoặc **▶ Chạy ngay** để mở khoá.

**Kiểm chứng liên tục báo ✗ Chưa đạt.** Bước tự soi thấy kết quả chưa ổn (bịa số, sai quy ước Wiki, làm quá phạm vi). Đọc lý do trong nhật ký, mở file liên quan qua [Quản lý tệp tin](05-quan-ly-tep-tin.md) để kiểm tra. Thường là do mô tả nhiệm vụ quá mơ hồ nên mỗi vòng nó hiểu một kiểu.

**Kết quả báo "Claude CLI chưa cài".** Bộ não chưa sẵn sàng trên máy. Xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) và [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

**Chạy bằng ChatGPT thì báo `bwrap: Failed to make / slave: Permission denied`.** Codex (ChatGPT) bọc mọi lệnh đọc/ghi file của nó bằng bubblewrap, mà bubblewrap không khởi động nổi trong container Docker, nên việc nền không đọc được một file nào. Ảnh Docker từ bản 0.25.9 đã tắt sẵn rào riêng đó (`JAVIS_CODEX_SANDBOX=off`) nên chỉ cần **cập nhật lên bản mới** là hết. Nếu bạn tự dựng container riêng thì đặt biến môi trường đó, hoặc chuyển việc nền sang bộ não Claude. Chi tiết ở [Biến môi trường](16-cau-hinh-env.md).

**Việc lặp than không có số liệu kinh doanh.** Nó chỉ đọc được số thật khi bạn đã đấu nguồn. Vào [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) để nối POS, quảng cáo hoặc kênh bán. Không có nguồn nào thì vòng đó dừng và báo lại một câu.

**Không tải được danh sách việc.** Trang hiện "Không tải được danh sách việc (mạng chậm hoặc hết giờ)" kèm liên kết **Thử lại**. Trên VPS yếu hoặc brain rất lớn, lần tải đầu có thể quá lâu; Javis đã tự thử lại một lần trước khi báo. Bấm **Thử lại**.

**Tạo việc qua Telegram xong lên dashboard không thấy.** Việc rơi vào brain khác. Trang này gộp mọi brain nên hãy cuộn xem các khối `🧠` khác, hoặc gõ tên việc vào ô tìm kiếm. Muốn dời về đúng chỗ thì dùng **Chuyển brain…** trên thẻ.

**Không nhận được tin báo về Telegram.** Kiểm tra bot đã bật và Chat ID đã nằm trong danh sách cho phép chưa, xem [Kênh Telegram](11-telegram.md). Cũng kiểm tra file việc có bị đặt `notify: false` không.

**Sửa file .md xong loop biến mất khỏi danh sách.** File hỏng frontmatter (thiếu cặp `---`, hoặc YAML sai) thì Javis bỏ qua file đó. Mở lại file, đối chiếu với một file loop khác còn chạy tốt, sửa cho đúng khuôn.

## Liên quan

- [Việc / Kanban](21-viec-kanban.md) - hàng đợi việc chạy một lần do AI điều phối, khác với việc lặp ở trang này.
- [Tự học](22-tu-hoc.md) - việc nền riêng cho bộ nhớ và Wiki, có Curator và LINT Wiki.
- [Kênh Telegram](11-telegram.md) - bật bot để nhận báo cáo mỗi vòng và nhắc hẹn.
- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - đấu nguồn để việc nền đọc được số thật.
- [Models & engine](10-models-va-engine.md) - chọn model rẻ cho việc nền.
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - mở file định nghĩa việc và file nhật ký.
- [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) - đặt việc và nhắc hẹn bằng lời.
- [Plugins](20-plugins.md) - hiểu về `javis_schedule` và các công cụ đi kèm app.
