# Đồ thị tri thức 3D

Đồ thị tri thức 3D là "trái tim hình ảnh" của màn hình Javis: một đám tinh vân (nebula) tím phát sáng, mỗi đốm sáng là một ghi chú trong bộ não của bạn, các đốm nối với nhau bằng những sợi sáng mờ. Nó vừa để nhìn cho đẹp, vừa để bạn thấy được kho tri thức của mình đang lớn dần và các ý tưởng đang nối với nhau ra sao. Trang này hướng dẫn từng thao tác cụ thể.

Xem thêm về nơi dữ liệu này đến từ đâu: [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

## Tính năng này là gì

Hình dung đơn giản: mỗi file ghi chú `.md` trong bộ não của bạn là một ngôi sao. Khi trong một ghi chú bạn nhắc tới một ghi chú khác bằng cú pháp `[[Tên ghi chú]]` (gọi là wikilink), Javis vẽ một sợi nối giữa hai ngôi sao đó. Càng nhiều ghi chú trỏ tới nhau, mạng lưới càng dày, và đám sao trông càng giống một tinh vân sống.

Những điều đồ thị thể hiện:

- **Mỗi node (đốm sáng) = một ghi chú** trong bộ não/vault đang chọn. Node càng nhiều kết nối thì đốm sáng càng to.
- **Mỗi sợi nối = một wikilink `[[...]]`** giữa hai ghi chú. Đây là cách Javis đọc quan hệ, chứ không phải bạn tự vẽ.
- **Màu sắc theo nhóm thư mục**: các ghi chú ở cùng một thư mục gốc (ví dụ nhóm Sources, nhóm Wiki, thư mục brain) có tông màu tím khác nhau, giúp phân vùng bằng mắt.
- **Node cô đơn bị ẩn**: ghi chú không có bất kỳ kết nối nào (không link tới ai, cũng không ai link tới) sẽ không hiện, để đồ thị gọn. Số ghi chú bị ẩn được đếm riêng (xem mục thống kê bên dưới).
- **Lớp agentic ở đáy**: ngay dưới đồ thị là dải chỉ số AGENTS · SKILLS · WORKFLOWS. Đây là "phần cứng" của bộ não (số agent, skill, workflow đang có), tách khỏi phần "tri thức" là các node phía trên. Bấm vào một chỉ số sẽ mở Studio đúng tab đó. Chi tiết ở [Agents & Workflows](07-agents-va-workflows.md), [Skills](06-skills.md).

### Đồ thị phản ứng theo giọng nói và theo suy nghĩ

Đồ thị không đứng yên. Nó phản ứng theo hai tín hiệu:

- **Khi bạn nói (hoặc khi Javis đọc trả lời)**: các đốm sáng phồng lên và sáng hơn theo nhịp âm lượng giọng nói. Nói to thì cả tinh vân "thở" mạnh hơn, xoay nhanh hơn một chút. Nói nhỏ hoặc im thì nó dịu lại.
- **Khi Javis đang suy nghĩ**: khi trạng thái chuyển sang "đang suy nghĩ", đồ thị bật hiệu ứng "nơron kích hoạt". Các đốm sáng lần lượt loé lên rồi lan sang các node hàng xóm theo sợi nối, kèm những hạt sáng cam trôi dọc theo dây, trông như tín hiệu chạy qua mạng thần kinh. Khi Javis trả lời xong, hiệu ứng này tắt.

Ngoài ra, đồ thị luôn tự xoay nhẹ liên tục để lúc nào cũng "sống", kể cả khi bạn không làm gì.

## Mở ở đâu trong Javis

Đồ thị 3D nằm ngay ở trang chính, không cần bấm gì để mở:

1. Mở dashboard (mặc định tại `http://<địa-chỉ-máy>:7777`). Nếu chưa cài, xem [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).
2. Ở thanh điều hướng bên trái, chọn mục **Javis (3D)**. Đây là trang trung tâm, và đồ thị chiếm cả vùng giữa màn hình.
3. Khi bạn chuyển sang các trang quản lý khác (Cài đặt, Workflows, Agents, Skills, ...), đồ thị **tự động tạm dừng** để tiết kiệm CPU/GPU. Quay lại trang **Javis (3D)** thì nó chạy lại ngay.

Lưu ý: trên màn hình hẹp (điện thoại), đồ thị cũng tự tạm dừng để đỡ tốn pin.

## Cách dùng (từng bước)

### Xoay, phóng to, di chuyển

Bạn tương tác với đồ thị bằng chuột (hoặc chạm), giống xoay một quả cầu:

1. **Xoay**: nhấn giữ chuột trái trên vùng trống rồi kéo. Cả tinh vân quay theo. Con trỏ có hình bàn tay nắm khi ở chế độ này.
2. **Phóng to / thu nhỏ**: lăn con lăn chuột (cuộn). Cuộn lên để lại gần, cuộn xuống để lùi ra xa.
3. **Đồ thị vẫn tự xoay nhẹ** khi bạn buông tay, nên nó không bao giờ đứng chết cứng.

### Xem một ghi chú là gì (hover)

1. Rê chuột lên một đốm sáng bất kỳ. Con trỏ đổi thành hình bàn tay chỉ.
2. Một bảng chú thích nhỏ hiện lên cạnh con trỏ, cho biết:
   - **Tên ghi chú** (in đậm).
   - **Đường dẫn** của file trong bộ não.
   - Số kết nối, ví dụ `5 kết nối · click để mở`.
3. Rê ra chỗ trống thì bảng chú thích biến mất.

### Bấm vào một node để Javis mở ghi chú đó

Đây là thao tác quan trọng nhất, biến đồ thị thành cách điều khiển bằng một cú click:

1. Bấm chuột trái vào một đốm sáng.
2. Camera bay tới, đưa node đó ra giữa màn hình (khoảng dưới một giây).
3. Cùng lúc, Javis nhận một câu lệnh tự động: đọc đúng ghi chú đó trong second brain, tóm tắt ngắn nội dung chính và đề xuất việc tiếp theo nếu có. Kết quả hiện ở khung hội thoại bên phải.

Nói cách khác: thấy một ý tưởng thú vị trong tinh vân, bấm vào là Javis mở và tóm tắt hộ bạn ngay. Về cách trò chuyện tiếp, xem [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md).

### Chọn nguồn dữ liệu để dựng đồ thị

Đồ thị luôn được dựng từ **bộ não (brain) đang chọn**. Bạn đổi nguồn ngay trên thanh điều hướng, ở ô chọn brain (mặc định hiển thị **Brain Default**):

1. Bấm vào ô chọn brain ở góc trái trên.
2. Chọn brain bạn muốn xem. Đồ thị sẽ tải lại và vẽ đúng mạng lưới của brain đó.
3. Đổi brain cũng đồng thời cập nhật bộ nhớ, số agent/skill/workflow và các số liệu khác theo brain mới.

Ba nút nhỏ cạnh ô chọn brain:

| Nút | Nhãn/biểu tượng | Chức năng |
|---|---|---|
| Tạo brain mới | ➕ | Tạo một brain mới trong thư mục `brains`. |
| Xoá brain | 🗑 | Xoá brain đang chọn (phải gõ đúng tên để xác nhận). |
| Chọn folder ngoài | 📁 | Trỏ tới một thư mục ghi chú bất kỳ trên máy để dựng đồ thị từ đó. |

Khi bấm 📁, một cửa sổ duyệt thư mục mở ra. Bạn đi tới thư mục chứa ghi chú (mỗi thư mục hiện kèm số file `.md` để bạn biết chỗ nào có dữ liệu), rồi bấm **Dùng folder này**. Thư mục đã chọn được lưu lại và hiện thành một mục trong danh sách brain để lần sau chọn nhanh.

Lựa chọn nguồn được ghi nhớ giữa các lần mở, nên lần sau vào bạn thấy đúng đồ thị đã xem gần nhất.

### Đọc dòng thống kê

Cạnh ô chọn brain có một dòng thống kê ngắn, ví dụ:

```
42 note · 87 kết nối · ẩn 15
```

Ý nghĩa:

- **note**: số ghi chú đang hiển thị (đã có ít nhất một kết nối).
- **kết nối**: tổng số sợi nối (wikilink) giữa các ghi chú.
- **ẩn**: số ghi chú bị giấu vì không có kết nối nào. Con số này gợi ý bạn còn nhiều ghi chú "mồ côi" chưa được link vào mạng lưới.

### Node tự mọc lên khi bộ não sinh ghi chú mới

Đồ thị theo dõi bộ não theo thời gian thực. Khi Javis (hoặc bạn) tạo một ghi chú `.md` mới, hoặc sửa một ghi chú làm phát sinh link mới:

1. Một node mới **nảy sinh ngay trên đồ thị**: nó loé sáng to rồi co lại về kích thước thật, trông như một ngôi sao vừa hình thành cạnh mạng lưới.
2. Dòng thống kê cập nhật số note/kết nối và nháy nhẹ để báo có thay đổi.

Bạn không cần bấm tải lại. Đây là cách nhìn thấy Second Brain của mình "dày lên" theo từng lần INGEST. Xem quy trình nạp kiến thức ở [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

## Công tắc bật/tắt và tạm dừng

Đồ thị không có nút bật/tắt cứng, nhưng nó tự quản lý để không ngốn máy:

- **Tự tạm dừng** khi bạn rời trang **Javis (3D)** sang trang quản lý khác, khi mở Studio, hoặc khi màn hình hẹp. Lúc tạm dừng, vòng vẽ, phần vật lý và cả việc tự xoay đều ngừng, đưa mức dùng CPU/GPU về gần 0.
- **Tự chạy lại** ngay khi bạn quay về trang **Javis (3D)** và không có Studio đang mở.
- **Không vẽ khi tab bị ẩn**: nếu bạn chuyển sang tab trình duyệt khác, đồ thị ngừng vẽ hoàn toàn cho tới khi bạn quay lại.

Nói ngắn gọn: bạn chỉ cần vào đúng trang **Javis (3D)** là đồ thị sống; ra khỏi đó là nó tự ngủ.

## Đồ thị được dựng ra sao (giải thích ngắn)

Để bạn tin vào những gì mình thấy, đây là cách Javis dựng đồ thị ở phía sau:

1. Javis quét toàn bộ file `.md` trong nguồn đang chọn (brain đang chọn, hoặc thư mục bạn trỏ tới bằng nút 📁).
2. Mỗi file thành một node. Tên node là tên file.
3. Javis đọc nội dung từng file, tìm các wikilink `[[...]]`. Mỗi wikilink trỏ tới một file khác trở thành một sợi nối.
4. Các node không có kết nối nào bị loại khỏi hình (nhưng vẫn được đếm vào mục "ẩn").
5. Kết quả được vẽ thành đám tinh vân 3D. Kích thước mỗi đốm sáng tỉ lệ với số kết nối của nó.

Vì đồ thị đọc trực tiếp từ file thật, nên nó luôn phản ánh đúng hiện trạng bộ não của bạn tại thời điểm tải.

## Mẹo

- **Muốn mạng lưới dày và đẹp hơn?** Hãy dùng cú pháp `[[Tên ghi chú]]` khi viết ghi chú để nối các ý với nhau. Càng nhiều wikilink, tinh vân càng liền mạch.
- **Thấy nhiều ghi chú bị "ẩn"?** Đó là các ghi chú mồ côi chưa link vào đâu. Mở chúng ra và thêm vài wikilink tới các khái niệm liên quan để kéo chúng vào mạng lưới.
- **Node to = ý tưởng trung tâm.** Đốm sáng lớn nhất thường là những ghi chú được nhắc tới nhiều nhất. Đó là các "trụ" tri thức đáng để bạn đầu tư làm sâu.
- **Dùng nút 📁 để xem nhanh một thư mục ghi chú bất kỳ** mà không cần biến nó thành brain chính thức.
- **Muốn thấy đồ thị "suy nghĩ"?** Ra một câu hỏi cho Javis rồi nhìn tinh vân trong lúc nó xử lý: các đốm sáng sẽ lan tín hiệu qua nhau.

## Sự cố thường gặp

- **Đồ thị trống hoặc chỉ hiện vài đốm rời rạc**: brain đang chọn còn ít ghi chú, hoặc các ghi chú chưa có wikilink `[[...]]` nào nên bị ẩn hết. Hãy thêm ghi chú và link chúng lại. Kiểm tra dòng thống kê: nếu "ẩn" cao mà "note" thấp thì đúng là do thiếu kết nối.
- **Báo "Thư viện 3D chưa tải (kiểm tra mạng)"**: trình duyệt chưa tải được thư viện đồ thị 3D. Kiểm tra kết nối mạng rồi tải lại trang. Nếu vẫn lỗi, xem [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
- **Dòng thống kê báo "Lỗi: ..."**: Javis không dựng được đồ thị từ nguồn đang chọn, thường do đường dẫn thư mục sai (khi dùng nút 📁). Chọn lại một thư mục có chứa file `.md`.
- **Đồ thị đứng im, không xoay**: có thể bạn đang ở trang khác, đang mở Studio, đang ở màn hình hẹp, hoặc tab bị ẩn. Quay lại đúng trang **Javis (3D)** ở tab đang mở là nó chạy lại.
- **Node mới không "mọc" khi vừa tạo ghi chú**: đồ thị theo dõi qua kết nối thời gian thực; nếu mất kết nối nó sẽ tự nối lại sau vài giây. Bạn cũng có thể đổi nguồn brain rồi chọn lại để buộc tải mới.
- **Bấm node nhưng Javis không trả lời**: node click sẽ gửi một câu hỏi vào khung hội thoại. Nếu không thấy phản hồi, kiểm tra kết nối tới máy chủ và engine đang dùng ở [Models & engine](10-models-va-engine.md).

## Liên quan

- [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) - điều khiển Javis bằng giọng, thứ làm tinh vân "thở".
- [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) - nơi các node được sinh ra.
- [Agents & Workflows](07-agents-va-workflows.md) và [Skills](06-skills.md) - lớp agentic ở đáy đồ thị.
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md) - khi có gì trục trặc.
