# Quản lý tệp tin

Trang "Tệp tin" là trình quản lý tệp ngay trong dashboard Javis. Bạn tìm file, duyệt thư mục, mở và sửa file văn bản (.md, .txt...) trực tiếp trên trình duyệt rồi lưu, tải file lên, tải file về (mọi loại file), tải cả thư mục về dạng .zip, tạo thư mục, đổi tên và xoá. Điểm vào luôn là "brain" (bộ não) bạn đang chọn, không cần mở File Explorer hay dùng lệnh.

## Tính năng này là gì

Mỗi brain của Javis thực chất là một thư mục trên máy/VPS chứa toàn bộ tri thức: ghi chú nguồn, Wiki, bộ nhớ, agents, workflows... Trang "Tệp tin" cho bạn xem và chỉnh sửa các file đó một cách trực quan:

- Tìm file trong toàn brain theo **tên** hoặc theo **nội dung**.
- Duyệt cây thư mục (nhấp vào thư mục để đi sâu vào, có breadcrumb để quay lại).
- Mở file để đọc: file chữ hiện ô soạn thảo, ảnh và PDF hiện ngay trong cửa sổ xem trước.
- Sửa file dạng chữ (.md, .txt, .json...) rồi bấm lưu.
- Tải file từ máy bạn lên brain, hoặc tải file trong brain về máy (mọi loại file, không riêng .md).
- Tải cả một thư mục về máy: Javis nén thành .zip rồi mới gửi.
- Tạo thư mục mới, tạo file mới, đổi tên, xoá.

## Phạm vi duyệt: tới đâu là hết

Điểm vào mặc định luôn là thư mục gốc của brain đang chọn. Nhưng **trần duyệt** (chỗ nút "↑ Lên" không đi lên được nữa) thì tuỳ cách bạn chạy Javis:

| Cách chạy | Trần duyệt | Ý nghĩa |
|---|---|---|
| Chạy cục bộ, không bắt đăng nhập (localhost) | **Ổ đĩa chứa brain** | Bạn duyệt và sửa được cả file ngoài brain, vì máy là của chính bạn |
| Nghe public / bắt buộc đăng nhập (Docker, VPS) | Thư mục brain | Khoá cứng trong brain, không hở ổ đĩa ra web |
| Đặt `JAVIS_FILES_ROOT=brain` (hoặc `vault`) | Thư mục brain | Khoá trong brain kể cả khi chạy cục bộ |
| Đặt `JAVIS_FILES_ROOT=drive` (hoặc `root`) | Ổ đĩa chứa brain | Ép mở rộng tới ổ đĩa |
| Đặt `JAVIS_FILES_ROOT=<đường dẫn>` | Đúng thư mục đó | Trần tuỳ ý, phải là thư mục có chứa brain |

Vì thế trên máy cá nhân, bấm **↑ Lên** nhiều lần có thể đưa bạn ra ngoài brain tới tận gốc ổ đĩa. Nút **⌂ Brain** đưa bạn về nhà ngay lập tức. Khi đã đứng ở trần, nút **↑ Lên** tự ẩn đi. Javis luôn chặn các đường dẫn cố vượt quá trần (kiểu `../../`), và brain luôn nằm trong trần.

Cách chỉnh biến môi trường xem [Cấu hình .env](16-cau-hinh-env.md).

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định ở cổng 7777).
2. Trên rail điều hướng bên trái, mở nhóm **Bộ não** rồi bấm mục **Tệp tin**.
3. Trang hiện ô tìm kiếm ở trên cùng, dưới đó là thanh công cụ, dưới nữa là danh sách file/thư mục. Lần đầu vào, Javis hiển thị thư mục gốc của brain đang chọn.

Nếu danh sách báo lỗi kiểu "Máy chủ Javis chưa có chức năng Tệp tin", hãy khởi động lại server (chạy `stop-javis.bat` rồi `start-javis.vbs`) và tải lại trang. Xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

## Chọn brain đang làm việc

Trình quản lý tệp luôn thao tác trên brain đang được chọn. Bạn đổi brain bằng ô chọn ở góc trái thanh trên cùng của dashboard:

1. Tìm ô danh sách brain trên thanh trên cùng (mặc định là "Brain Default").
2. Bấm vào ô đó và chọn brain bạn muốn. Mỗi brain hiển thị dạng "🧠 tên brain" (kèm số note nếu có).
3. Trang Tệp tin **tự nạp lại** theo brain mới ngay khi bạn đổi, không cần bấm ↻ cũng không cần F5. Cây vault ở cột trái cũng làm mới theo.

Cạnh ô chọn brain còn có ba nút nhỏ:

| Nút | Ý nghĩa |
|---|---|
| ➕ | Tạo brain mới trong thư mục brains |
| 🗑 | Xoá brain đang chọn (phải gõ đúng tên để xác nhận) |
| 📁 | Chọn brain từ folder ngoài bất kỳ |

Về nút 🗑, có ba điều cần nhớ:

- Với brain thật (🧠): xoá **toàn bộ** brain, không phải xoá một file. Hộp xác nhận ghi rõ não này sẽ được chuyển vào **THÙNG RÁC (giữ 30 ngày rồi tự xoá hẳn)**, và việc xoá sẽ **ĐỒNG BỘ sang mọi máy khác**. Bạn phải gõ chính xác tên brain mới xoá được.
- Với mục folder ngoài (📁): nút này chỉ **gỡ khỏi danh sách chọn**, không đụng dữ liệu trên ổ đĩa. Hộp xác nhận nói rõ "Chỉ gỡ khỏi menu chọn não, KHÔNG xoá dữ liệu trên ổ đĩa."
- Brain mặc định không xoá được, Javis báo "Không thể xoá Brain mặc định (não khởi đầu)."

Đừng nhầm nút này với nút "Xoá" từng dòng file bên trong trang Tệp tin. Chi tiết về brain và bộ nhớ xem [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

## Giao diện trang Tệp tin

**Hàng trên cùng - tìm kiếm**, gồm:

- Ô tìm với biểu tượng 🔍, chữ mờ **Tìm file trong toàn brain...**. Có chữ rồi thì hiện nút **✕** (chú thích: "Xoá tìm kiếm").
- Hai chip chọn phạm vi: **Tên** (chú thích: "Tìm theo tên file") và **Nội dung** (chú thích: "Tìm trong nội dung file text"). Mặc định đang ở **Tên**.
- Dòng meta bên phải cho biết trạng thái: lúc rảnh là "Tìm trong toàn brain" (hoặc "Quét nội dung file text" nếu đang ở chip Nội dung), lúc có kết quả là "12 kết quả · tên file".

**Hàng thứ hai - thanh công cụ**, gồm:

- **Breadcrumb** bên trái: bắt đầu bằng "🏠 tên thư mục gốc", rồi lần lượt các thư mục con bạn đang đứng. Bấm vào bất kỳ mắt xích nào để nhảy thẳng về cấp đó.
- Nút **↑ Lên**: lùi lên thư mục cha một cấp. Tự ẩn khi bạn đã ở trần duyệt.
- Nút **⌂ Brain** (chú thích: "Về thư mục brain"): quay thẳng về gốc brain, dù bạn đang lạc ở đâu.
- Nút **+ Thư mục**: tạo thư mục mới.
- Nút **+ File**: tạo file mới (rỗng).
- Nút **⤒ Tải lên**: chọn file từ máy để tải lên (chọn được nhiều file cùng lúc).
- Nút **⤓ Tải thư mục**: nén cả thư mục đang mở thành .zip rồi tải về máy.
- Nút **↻**: tải lại danh sách hiện tại.

Bên dưới là danh sách. Mỗi dòng gồm biểu tượng loại file, tên, dung lượng (với file), và một nhóm nút thao tác. Nhóm nút này luôn hiện (hơi mờ) và rõ hẳn khi bạn rê chuột vào dòng; trên điện thoại và máy tính bảng nó hiện rõ sẵn vì màn hình cảm ứng không có thao tác rê chuột.

## Cách dùng (từng bước)

### Tìm file trong toàn brain

1. Bấm vào ô **Tìm file trong toàn brain...** ở trên cùng trang.
2. Chọn phạm vi: chip **Tên** để khớp tên file, chip **Nội dung** để quét chữ bên trong file.
3. Gõ từ khoá. Javis tự tìm sau khi bạn ngừng gõ một chút; muốn tìm ngay thì nhấn **Enter**.
4. Danh sách bên dưới đổi thành kết quả tìm kiếm. Mỗi dòng gồm: tên file, đường dẫn của nó, đoạn trích (nếu tìm theo nội dung), và nhãn loại khớp - **Tên file** hoặc **Trong nội dung · dòng 42**.
5. Bấm nút **Mở** (hoặc bấm thẳng vào tên file) để mở file đó ngay.
6. Bấm nút **⤓ Tải** để tải thẳng file đó về máy, khỏi cần đi vào thư mục chứa nó.
7. Bấm nút **Vị trí** để nhảy về thư mục chứa file, Javis cuộn tới đúng dòng và tô sáng nó.
8. Xoá hết chữ trong ô tìm (hoặc bấm **✕**, hoặc nhấn **Esc**) để quay lại danh sách thư mục.

Vài điều nên biết về tìm kiếm:

- Phạm vi quét luôn là **gốc brain**, kể cả khi trần duyệt của bạn đang mở tới cả ổ đĩa. Javis cố ý không quét cả ổ đĩa vì sẽ rất chậm.
- Tìm theo **tên** không phân biệt dấu tiếng Việt: gõ `bao cao` vẫn ra `báo-cáo.md`. Áp dụng cho mọi loại file.
- Tìm theo **nội dung** chỉ quét file dạng chữ (.md, .txt, .json, .yaml, .csv, .py, .js...), bỏ qua file nặng hơn 1MB, và bỏ qua các thư mục kỹ thuật `.git`, `node_modules`, `__pycache__`, `.obsidian`, `.trash`, `.venv` cùng mọi thư mục ẩn.
- Chế độ **Nội dung** cần ít nhất 2 ký tự. Gõ 1 ký tự thì Javis nhắc "Nhập ít nhất 2 ký tự để tìm trong nội dung."
- Không có kết quả thì hiện `Không tìm thấy file phù hợp với "<từ khoá>".`

### Duyệt thư mục

1. Bấm vào **tên thư mục** (dòng có biểu tượng 📁) để đi vào trong.
2. Dùng breadcrumb ở trên, nút **↑ Lên**, hoặc nút **⌂ Brain** để quay ra.
3. Bấm vào **tên file** (hoặc biểu tượng của nó) cũng mở file luôn: file chữ và ảnh/PDF mở cửa sổ xem trước ngay tại chỗ, các loại còn lại mở ở tab mới.
4. Thư mục trống thì danh sách hiện "Thư mục trống."

### Mở và sửa file văn bản

1. Rê chuột vào dòng file, bấm nút **Sửa**. (Hoặc bấm thẳng vào tên file.)
2. Một cửa sổ hiện lên. Với file dạng chữ (.md, .txt, .json, .yaml, .yml, .csv, .js, .ts, .py, .html, .css, .toml, .ini, .log, .sh, .bat, .xml, .svg, .env), Javis hiện ô soạn thảo để bạn chỉnh trực tiếp.
3. Sửa xong bấm **💾 Lưu**. Khi lưu thành công, nút đổi thành **✓ Đã lưu** rồi trở lại như cũ.
4. Bấm **✕** ở góc trên cửa sổ để đóng. Bạn cũng có thể bấm ra vùng tối bên ngoài cửa sổ để đóng.

### Lùi về / Tiến lên giữa các note

Đọc một note wiki là đi theo chuỗi liên kết: bấm một `[[wikilink]]` là sang note khác. Hai nút mũi tên **‹ ›** ở **góc trên bên trái**, ngay trước tên file, đưa bạn đi lại trên vệt đó - đúng như nút Lùi/Tiến của trình duyệt.

- **Bấm mũi tên trái** để quay lại note vừa đọc, **mũi tên phải** để tiến lên lại.
- **Rê chuột vào nút là biết sẽ tới đâu.** Tooltip gọi thẳng tên file, ví dụ "Lùi về: Bát Giác Offer.md". Đi sâu bốn năm tầng liên kết thì nhớ mình từ đâu tới là chuyện không dễ, nên nút nói hộ.
- **Hết chỗ để đi thì nút mờ đi chứ không biến mất.** Nút ẩn hiện làm thanh tiêu đề nhảy, và bạn sẽ không bao giờ biết là có nút đó.
- **Phím tắt: `Alt` + `←` và `Alt` + `→`.** Chuột có nút lùi/tiến bên hông cũng dùng được luôn.
- Vệt đường đi **giữ nguyên khi bạn đóng trình sửa** rồi mở lại (đóng ra để chat về chính note đó là chuyện thường), và **tự xoá khi bạn đổi sang brain khác** - vì mọi bước trong vệt đều thuộc brain cũ.
- Đang đứng giữa vệt mà mở một note mới thì phần phía trước bị cắt, y như trình duyệt.

**Rời một file đang sửa dở thì Javis tự lưu trước.** Bấm mũi tên, bấm một wikilink, hay bấm file khác trong cây - nếu bạn có sửa gì mà chưa bấm Lưu, Javis lưu lại rồi mới đi. Nếu lưu hỏng (mất mạng, file bị khoá) thì **Javis không đi đâu cả** và nút Lưu hiện lỗi, để bài bạn vừa viết không bị vứt đi âm thầm. File bạn chỉ mở ra đọc rồi rời đi thì không bị ghi lại gì cả.

**Mở file nào thì Javis làm việc trên file đó.** Ngay khi mở một file văn bản để sửa, Javis tự **ghim** file đó vào khung chat: một thẻ màu cam hiện phía trên thanh nhập, ghi tên file kèm dòng "đang mở - bấm để sửa tiếp". Từ lúc đó bạn hỏi gì thì Javis cũng đã có sẵn file đó làm đầu vào, khỏi phải dán đường dẫn hay mô tả lại. Bảo "dọn lại phần quá hạn giúp anh" hay "viết thêm mục kết luận" mà không nói file nào thì Javis ghi thẳng vào chính file đang mở.

Thẻ ghim khác thẻ file đính kèm ở ba chỗ:
- **Chỉ có một.** Mở file khác là thẻ đổi theo file mới, không cộng dồn.
- **Không mất sau khi gửi.** File đính kèm gửi xong là biến mất; thẻ ghim ở lại suốt cuộc trò chuyện vì nó là file bạn đang làm việc trên đó. Đóng cửa sổ sửa cũng không bỏ ghim - đóng ra để quay sang chat về chính file đó là chuyện thường.
- **Bấm vào thẻ là quay lại sửa file đó.** Đóng trình sửa rồi chat vài lượt, muốn sửa tiếp thì bấm thẳng vào thẻ (hoặc chọn thẻ bằng phím Tab rồi Enter) - file mở lại trong trình sửa, cây vault bên trái tự xổ tới đúng nhánh chứa nó, khỏi đi tìm lại từ đầu. Nếu file đang mở sẵn thì Javis chỉ đưa bạn về đó chứ không nạp lại, nên chữ đang gõ dở không mất. Trên điện thoại, thẻ mở file trong khung sửa bung giữa màn hình. Bấm dấu **✕** trên thẻ vẫn là bỏ ghim chứ không mở file.

Bỏ ghim bằng cách bấm **✕** trên thẻ. Ghim cũng tự bỏ khi bạn đổi sang brain khác hoặc xoá chính file đang ghim, và nó sống qua F5 nên tải lại trang không mất mạch làm việc.

Lưu ý:
- Nút **Sửa** chỉ xuất hiện với các loại file văn bản nêu trên.
- File lớn hơn 2MB sẽ không mở để xem trong trình duyệt. Javis báo bạn tải về thay vì mở.
- Nếu file là dạng nhị phân (không phải văn bản), cửa sổ sẽ đề nghị **⤓ Tải** về thay vì hiển thị ô soạn thảo.

### Xem ảnh và PDF ngay trong dashboard

1. Rê chuột vào dòng file ảnh (.png, .jpg, .jpeg, .gif, .webp, .bmp, .ico) hoặc .pdf, bấm nút **Xem** (chú thích: "Xem trước"). Bấm thẳng vào tên file cũng ra kết quả y hệt.
2. Ảnh hiện luôn trong cửa sổ; PDF nhúng vào khung đọc ngay tại chỗ.
3. Trên đầu cửa sổ có thêm hai nút: **↗ Tab mới** để mở file ở tab riêng, và **⤓ Tải** để tải về máy. Bấm **✕** để đóng.

Các loại file còn lại (video, file nén, file dữ liệu...) không có nút Sửa cũng không có nút Xem, mà có nút **Mở** (chú thích: "Mở trong tab mới"). Nói cách khác, mỗi dòng file luôn có đúng một nút xem/mở, chỉ khác tên tuỳ loại.

### Tạo file mới

1. Bấm **+ File** trên thanh công cụ.
2. Nhập tên file, nhớ kèm đuôi. Ví dụ: `ghi-chu.md`.
3. Javis tạo file rỗng ngay trong thư mục hiện tại. Bạn có thể bấm **Sửa** để nhập nội dung.

### Tạo thư mục mới

1. Bấm **+ Thư mục**.
2. Nhập tên thư mục.
3. Thư mục mới xuất hiện trong thư mục hiện tại.

### Tải file lên

1. Bấm **⤒ Tải lên**.
2. Chọn một hoặc nhiều file từ máy của bạn.
3. Javis tải lần lượt vào thư mục hiện tại rồi làm mới danh sách.

Nếu trong thư mục đã có file trùng tên, Javis tự thêm hậu tố số vào tên file mới (ví dụ `bao-cao_1.pdf`) để không ghi đè file cũ.

### Tải file về máy

1. Bấm nút **⤓ Tải** ở dòng file.
2. File về máy theo cơ chế tải xuống của trình duyệt, giữ nguyên tên gốc kể cả tên tiếng Việt có dấu.

Nút này có ở **mọi loại file**, không riêng .md: ảnh, PDF, video, file nén, bảng tính, file dữ liệu đều tải về được. Kết quả tìm kiếm cũng có nút **⤓ Tải** ngay cạnh nút Mở, nên tìm thấy là tải được luôn, không cần đi vào thư mục chứa nó.

Cửa sổ xem/sửa file cũng luôn có nút **⤓ Tải** trên đầu, kể cả khi file đang mở ở chế độ sửa (trước đây file sửa được chỉ có nút Lưu).

### Tải cả thư mục về máy (nén .zip)

Có hai đường, dùng đường nào cũng ra kết quả như nhau:

- Bấm **⤓ Zip** ở dòng thư mục trong danh sách.
- Đi vào thư mục đó rồi bấm **⤓ Tải thư mục** trên thanh công cụ.

Javis đo thư mục trước, rồi nén toàn bộ bên trong (giữ nguyên cây thư mục con) thành một file .zip đặt theo tên thư mục, ví dụ `attachments.zip`. Vài điều nên biết:

- Thư mục nặng hơn 200MB thì Javis hỏi lại trước khi nén, kèm số file và dung lượng ước tính, để bạn khỏi ngồi chờ oan.
- Trần an toàn là 20.000 file hoặc 2GB. Vượt trần Javis báo thẳng và đề nghị bạn tải từng thư mục con - rào này để một cú bấm nhầm ở thư mục gốc ổ đĩa không kéo cả ổ đĩa vào file nén.
- Thư mục rỗng thì Javis báo không có gì để tải thay vì đưa bạn một file .zip trống.
- Thư mục con rỗng vẫn được giữ trong file .zip.

Cây file bên trang ghi chú cũng có nút **⤓** y hệt: đứng ở file thì tải file, đứng ở thư mục thì tải cả thư mục dạng .zip.

### Đổi tên

1. Rê chuột vào dòng file hoặc thư mục, bấm **Đổi tên**.
2. Nhập tên mới rồi xác nhận. Bỏ trống hoặc giữ nguyên tên cũ thì không có gì thay đổi.

Ký tự lạ trong tên sẽ được Javis thay bằng dấu gạch dưới cho an toàn, nên tên thực tế có thể khác nhẹ so với tên bạn gõ. Chữ tiếng Việt có dấu, dấu chấm, gạch ngang, gạch dưới, khoảng trắng và ngoặc đơn thì được giữ nguyên.

### Xoá

1. Rê chuột vào dòng cần xoá, bấm **Xoá** (nút màu cảnh báo).
2. Javis hỏi xác nhận: `Xoá "<tên>"? Không thể hoàn tác.` Bấm đồng ý mới xoá.
3. Với thư mục, thao tác xoá sẽ xoá luôn toàn bộ file bên trong.

Cảnh báo: thao tác xoá không có thùng rác, không hoàn tác được. Hãy chắc chắn trước khi xác nhận. Javis không cho phép xoá thư mục gốc của brain cũng như thư mục trần duyệt, báo "Không thể xoá thư mục gốc / brain".

## Hai thư mục là vùng cache, đừng để dữ liệu quý ở đó

`attachments/` và `inbox/` của mỗi brain được Javis coi là **vùng cache**, không phải kho lưu trữ:

- File trong hai thư mục đó quá **30 ngày** sẽ tự bị dọn, và nếu tổng dung lượng vượt trần **300MB** thì Javis dọn từ cũ tới mới cho tới khi xuống dưới trần.
- Riêng ghi chú `.md` lỡ nằm trong hai thư mục đó thì được chừa ra, không bị dọn.
- Muốn tắt hẳn việc tự dọn, đặt `enabled: false` ở khoá `media` trong `settings.json`. Ngưỡng ngày và dung lượng cũng chỉnh ở đó.
- Ảnh cũ đã hết hạn khi hiện lại trong hội thoại sẽ thành một ô xám viền đứt ghi **"Ảnh đã hết hạn"** thay vì biểu tượng ảnh vỡ.

Kết luận thực dụng: tài liệu bạn muốn giữ lâu dài thì chuyển sang thư mục nguồn hoặc Wiki của brain, đừng để nằm trong `attachments/` hay `inbox/`.

## Bảng tra nhanh nút và trạng thái

| Bạn muốn | Bấm | Ghi chú |
|---|---|---|
| Tìm file theo tên | Ô tìm + chip `Tên` | Không phân biệt dấu tiếng Việt |
| Tìm chữ trong file | Ô tìm + chip `Nội dung` | Chỉ file text, bỏ file >1MB, cần ≥2 ký tự |
| Mở kết quả tìm | `Mở` | Hoặc bấm thẳng vào tên |
| Nhảy tới thư mục chứa file | `Vị trí` | Cuộn tới và tô sáng dòng đó |
| Thoát tìm kiếm | `✕` hoặc phím `Esc` | Về lại danh sách thư mục |
| Vào thư mục | Tên thư mục (📁) | Có breadcrumb để quay ra |
| Lùi một cấp | ↑ Lên | Tự ẩn khi đã ở trần duyệt |
| Về gốc brain | ⌂ Brain | Cần khi bạn duyệt lạc ra ngoài brain |
| Làm mới danh sách | ↻ | Đổi brain thì tự làm mới, không cần bấm |
| Đọc/sửa file chữ | Sửa → 💾 Lưu | Chỉ với file văn bản, dưới 2MB |
| Xem ảnh / PDF | Xem | Kèm nút ↗ Tab mới và ⤓ Tải |
| Mở file loại khác | Mở | Mở ở tab mới |
| Tạo file rỗng | + File | Nhớ gõ đuôi, vd `.md` |
| Tạo thư mục | + Thư mục | |
| Đưa file từ máy vào | ⤒ Tải lên | Chọn được nhiều file |
| Lấy file về máy | ⤓ Tải | Có ở MỌI loại file, cả trong kết quả tìm kiếm |
| Lấy cả thư mục về máy | ⤓ Zip (ở dòng thư mục) hoặc ⤓ Tải thư mục (thanh công cụ) | Nén .zip; trần 20.000 file / 2GB |
| Đổi tên | Đổi tên | Ký tự lạ bị thay bằng `_` |
| Xoá | Xoá | Có hỏi xác nhận, không hoàn tác |

## Mẹo

- Không nhớ file nằm ở đâu thì đừng duyệt tay: gõ vào ô tìm là nhanh nhất. Nhớ mang máng nội dung thì chuyển sang chip **Nội dung**, nó tìm cả trong thân file.
- File Wiki và ghi chú trong vault đều là .md, nên bạn có thể sửa nhanh ngay tại đây thay vì mở app khác. Nhưng nếu chỉ chỉnh nội dung tri thức, thường tiện hơn khi để Javis làm qua trò chuyện. Xem [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) và [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).
- Đặt tên file mô tả rõ ý chính, tránh tên chung chung. Điều này giúp bạn và Javis tìm lại dễ hơn.
- Muốn đưa một bài viết, ảnh chụp kiến thức hay tài liệu vào cho Javis tiêu hoá, hãy tải lên thư mục nguồn của brain rồi yêu cầu Javis xử lý trong khung trò chuyện.
- Trên máy cá nhân bạn duyệt được ra cả ổ đĩa, nên hãy nhìn breadcrumb trước khi xoá. Thấy "🏠" không phải tên brain của bạn là đang đứng ngoài brain.
- Trước khi thao tác hàng loạt, kiểm tra lại đang đứng đúng brain qua ô chọn brain trên thanh trên cùng. Sửa nhầm brain là lỗi hay gặp nhất.

## Sự cố thường gặp

**Danh sách báo "Máy chủ Javis chưa có chức năng Tệp tin".** Server đang chạy bản cũ chưa có tính năng này. Khởi động lại server (`stop-javis.bat` rồi `start-javis.vbs`) và tải lại trang.

**Báo "Phiên đăng nhập hết hạn" hoặc lỗi 401.** Tải lại trang và đăng nhập lại. Xem [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).

**Bấm ↑ Lên mà không thấy nút đâu.** Bạn đã ở trần duyệt rồi, nút tự ẩn. Bấm **⌂ Brain** để về gốc brain.

**Duyệt lạc ra ngoài brain, không biết đường về.** Bấm **⌂ Brain**. Đây đúng là hành vi thiết kế khi chạy cục bộ: trần duyệt là ổ đĩa chứ không phải thư mục brain. Muốn khoá cứng trong brain thì đặt `JAVIS_FILES_ROOT=brain` rồi khởi động lại server.

**Tìm kiếm không ra file mà bạn biết chắc là có.** Ba nguyên nhân hay gặp: file nằm ngoài gốc brain (tìm kiếm chỉ quét trong brain); file nằm trong thư mục bị bỏ qua như `.git`, `node_modules`, `.trash`; hoặc bạn đang ở chip **Nội dung** mà file đó không phải dạng chữ hay nặng hơn 1MB. Thử đổi sang chip **Tên**.

**Tìm kiếm báo "Cần ít nhất 2 ký tự".** Chế độ **Nội dung** cần từ khoá dài tối thiểu 2 ký tự. Gõ thêm một ký tự nữa, hoặc chuyển sang chip **Tên**.

**Mở file báo "File quá lớn để xem (>2MB) - hãy tải về".** File vượt giới hạn xem trực tiếp. Dùng nút **Tải** để tải về máy rồi mở bằng phần mềm phù hợp.

**Mở file báo "File nhị phân - không xem được dạng văn bản".** File không phải văn bản (ví dụ file nén, file dữ liệu). Không sửa được trong trình duyệt, chỉ tải về.

**Tải thư mục báo "Thư mục quá lớn để nén".** Thư mục vượt trần an toàn 20.000 file hoặc 2GB. Đi vào trong rồi tải từng thư mục con. Hay gặp nhất khi bạn đứng ở thư mục gốc ổ đĩa chứ không phải trong brain - nhìn breadcrumb để kiểm tra.

**Tải thư mục báo "không có file nào để tải".** Thư mục rỗng. Javis không tạo file .zip trống.

**Bấm Tải mà không thấy file về đâu.** Kiểm tra thư mục Downloads của trình duyệt, và xem trình duyệt có chặn tải xuống tự động không. Riêng thư mục lớn cần vài giây để nén trước khi trình duyệt bắt đầu nhận file.

**Sửa xong bấm Lưu nhưng nút hiện "⚠ Lỗi".** Lưu thất bại. Thử lại; nếu vẫn lỗi, kiểm tra quyền ghi của thư mục brain và tình trạng ổ đĩa, hoặc xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

**Không thấy file vừa tải lên hoặc vừa tạo.** Bấm **↻** để làm mới danh sách. Nếu vẫn không thấy, kiểm tra bạn có đang đứng đúng thư mục và đúng brain hay không.

**Ảnh trong attachments biến mất.** Rất có thể ảnh đã quá 30 ngày hoặc thư mục vượt trần 300MB nên bị dọn tự động. Xem mục "Hai thư mục là vùng cache" bên trên.

**Lỡ xoá nhầm file.** Không có thùng rác trong trình quản lý này, thao tác xoá không hoàn tác được. Nếu brain của bạn được đặt trong thư mục có sao lưu git, có thể khôi phục từ đó; ngoài ra thì file đã mất. Xem [Sao lưu brain lên GitHub](18-sao-luu-github.md).

**Lỡ xoá nhầm cả một brain.** Cái này thì cứu được: brain bị xoá vào thùng rác và giữ 30 ngày trước khi mất hẳn.

## Liên quan

- [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) - cấu trúc bên trong một brain.
- [Sao lưu brain lên GitHub](18-sao-luu-github.md) - giữ lịch sử thay đổi và cứu file lỡ xoá.
- [Task & Dataview trong note](19-task-va-dataview.md) - viết task và bảng truy vấn trong file .md.
- [Cấu hình .env](16-cau-hinh-env.md) - biến `JAVIS_FILES_ROOT` và các biến khác.
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md)
