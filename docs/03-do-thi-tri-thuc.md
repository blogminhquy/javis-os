# Đồ thị tri thức

***Tiếng Việt** · [English](en/03-knowledge-graph.md)*

Đồ thị tri thức biến các ghi chú trong brain thành một mạng lưới trực quan. Mỗi đốm sáng là một file Markdown; mỗi sợi nối là một wikilink `[[...]]` giữa hai ghi chú.

Đồ thị dùng canvas 2D, không dùng WebGL và không cần tải thư viện từ Internet. Nó hiện cả các ghi chú chưa có liên kết, hỗ trợ timelapse và có thể tắt hoàn toàn trong Cài đặt.

Xem thêm nơi dữ liệu này được tạo ra: [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md).

## Đồ thị thể hiện gì

- **Mỗi node = một ghi chú** trong brain đang chọn. Node có nhiều kết nối sẽ lớn hơn.
- **Mỗi sợi nối = một wikilink `[[...]]`** giữa hai ghi chú.
- **Màu node = thư mục cha trực tiếp** của file.
- **Nhãn danh mục** quanh đồ thị cho biết các thư mục lớn nhất, số note và tỷ lệ của chúng trong vault.
- **Dải AGENTS · SKILLS · WORKFLOWS** ở đáy cho biết số năng lực đang có. Bấm một mục để mở đúng trang quản lý.

## Mở đồ thị

1. Mở dashboard, mặc định tại `http://<địa-chỉ-máy>:7777`.
2. Trên thanh điều hướng bên trái, mở nhóm **Trợ lý** rồi chọn **Javis**.
3. Đồ thị nằm ở vùng giữa màn hình.

Khi bạn chuyển sang trang khác hoặc mở trình soạn ghi chú, đồ thị tự tạm dừng. Quay lại trang **Javis** hoặc đóng trình soạn thì nó chạy tiếp.

Trên màn hình hẹp dưới 860px, Javis ưu tiên giao diện nhẹ và mở thẳng trang **Trò chuyện**.

## Bật hoặc tắt đồ thị

1. Mở **Hệ thống → Cài đặt**.
2. Mở nhóm **Giao diện & Brain**.
3. Tìm thẻ **Đồ thị não**.
4. Bấm **Tắt đồ thị** hoặc **Bật đồ thị**.

Khi tắt, Javis không dựng đồ thị và mở thẳng trang **Trò chuyện**. Lựa chọn được lưu trong cài đặt server.

## Chọn brain

Ô chọn brain nằm trên thanh trên cùng, cạnh chữ JAVIS OS. Khi đổi brain, Javis đồng thời cập nhật đồ thị, bộ nhớ, số agent/skill/workflow, cây tệp tin và khung hội thoại.

Ba nút nhỏ cạnh ô chọn:

| Nút | Chức năng |
|---|---|
| ➕ | Tạo brain mới trong thư mục `brains`. |
| 🗑 | Xoá brain đang chọn sau khi xác nhận đúng tên. Không xoá được **Brain Default**. |
| 📁 | Chọn một thư mục ghi chú bất kỳ trên máy làm nguồn. |

Thư mục ngoài được lưu vào danh sách để chọn lại. Khi bấm 🗑 với một nguồn ngoài, Javis chỉ gỡ nó khỏi menu chứ không xoá dữ liệu trên ổ đĩa.

## Di chuyển và đọc đồ thị

- **Kéo nền** để dời mạng lưới.
- **Lăn con lăn** để phóng to hoặc thu nhỏ.
- **Kéo một node** để đổi vị trí tạm thời; khi thả, node trở lại trạng thái cân bằng.
- **Rê chuột lên node** để hiện tên ghi chú, làm sáng node đó cùng các hàng xóm và làm mờ phần còn lại.
- **Bấm node** để mở ghi chú trong trình soạn.
- **Bấm nhãn danh mục** để rọi sáng riêng cụm của thư mục đó. Bấm lại nhãn hoặc bấm nền để bỏ lọc.

Sau khi các lực vật lý ổn định, Javis tự canh cho toàn bộ mạng vừa khung.

## Mở và sửa ghi chú từ node

1. Bấm một node.
2. Trình soạn ghi chú mở ngay trên vùng đồ thị.
3. Đọc, sửa hoặc tải file như bình thường.
4. Bấm ✕ hoặc nhấn Esc để đóng và chạy lại đồ thị.

Với file `.md`, trình soạn có hai chế độ **Sửa** và **Nguồn**. Thanh công cụ gồm:

| Nút | Việc nó làm |
|---|---|
| 💾 Lưu | Ghi nội dung xuống file; hỗ trợ `Ctrl+S`. |
| ✎ | Đổi tên file. |
| 🗑 | Xoá ghi chú sau khi xác nhận. |
| ↗ | Mở file thô ở tab mới. |
| ⤓ Tải | Tải file về máy. |
| ⛶ | Phóng to hoặc thu nhỏ trình soạn. |
| ✕ | Đóng trình soạn. |

Bấm node chỉ mở file, không tự gửi câu hỏi vào chat. Muốn Javis tóm tắt hay phân tích, hãy yêu cầu trong khung hội thoại.

## Ẩn lớp thông tin phủ

Nút hình con mắt ở góc trên bên phải vùng đồ thị dùng để ẩn hoặc hiện:

- nhãn danh mục;
- dải AGENTS · SKILLS · WORKFLOWS.

Trạng thái được nhớ trong trình duyệt và đồng bộ giữa các tab.

## Timelapse “cuộc đời brain”

Nút hình đồng hồ dưới nút con mắt chiếu lại quá trình brain lớn lên:

1. Đồ thị bắt đầu từ trống.
2. Các note xuất hiện theo thứ tự ngày tạo file, cách nhau khoảng 0,16 giây.
3. Một sợi nối chỉ xuất hiện khi cả hai đầu đã có mặt.
4. Bấm nút lần nữa để dừng; đồ thị đầy đủ sẽ được khôi phục.

## Màu node theo thư mục

Javis dùng bảng màu tương phản và gán lần lượt cho từng thư mục cha trực tiếp. Tiền tố số như `07 - ` được bỏ qua khi so tên, nên `07 - Wiki` và `Wiki` được xem là cùng một danh mục.

Màu trên node cũng được dùng cho phần “% Vault” của nhãn danh mục. Khi đổi tông sáng/tối, đồ thị đổi sang bảng màu phù hợp nhưng giữ nguyên nhóm màu của từng thư mục.

## Dòng thống kê

Trên thanh trên cùng có dòng dạng:

```text
42 note · 87 kết nối
```

- **note**: số ghi chú đang hiển thị, gồm cả note chưa có wikilink.
- **kết nối**: tổng số wikilink hợp lệ giữa các ghi chú.

Các trạng thái khác là **Đang tải...**, **Lỗi: ...** hoặc cảnh báo không nạp được thư viện đồ thị.

## Cập nhật theo thời gian thực

Đồ thị theo dõi brain và tự cập nhật khi có ghi chú mới hoặc liên kết mới:

1. Node mới nảy lên rồi co về kích thước bình thường.
2. Dòng thống kê cập nhật và nháy nhẹ.

Nếu kết nối theo dõi bị ngắt, Javis tự nối lại. Một lần quét định kỳ cũng giúp bắt các thay đổi bị bỏ lỡ.

## Phản ứng theo giọng nói và trạng thái

- Khi bạn nói hoặc Javis đọc câu trả lời, các node phồng nhẹ theo mức âm lượng.
- Khi Javis chuyển sang **ĐANG SUY NGHĨ**, mạng đổi nhịp.
- Khi nghỉ, các node thở nhẹ với pha lệch nhau.

## Đồ thị được dựng ra sao

1. Javis quét tối đa 2.000 file `.md` trong nguồn đang chọn.
2. Mỗi file trở thành một node; tên node là tên file bỏ đuôi.
3. Javis tìm wikilink `[[...]]`; mỗi liên kết tới một file khác trở thành một cạnh.
4. Dạng `[[thư-mục/Tên|bí danh]]` được hỗ trợ; Javis lấy phần tên file để nối.
5. Javis đếm note theo thư mục cha và chọn tối đa 8 thư mục lớn nhất làm nhãn.

## Sự cố thường gặp

- **Đồ thị trống hoặc ít node**: kiểm tra brain đang chọn và xem nguồn có file `.md` hay không.
- **Không nạp được thư viện đồ thị**: tải lại trang. Thư viện nằm trên chính máy chủ Javis, nên lỗi thường do trang tải dở hoặc static file không được phục vụ.
- **Dòng thống kê báo “Lỗi”**: nguồn ngoài có thể đã đổi đường dẫn hoặc không còn quyền đọc.
- **Đồ thị đứng im**: kiểm tra xem bạn có đang ở trang khác, mở trình soạn, dùng màn hình hẹp hoặc đã tắt đồ thị trong Cài đặt không.
- **Vào Javis nhưng chuyển thẳng sang Trò chuyện**: màn hình đang hẹp hoặc đồ thị đã bị tắt.
- **Node mới chưa xuất hiện**: chờ kết nối theo dõi tự nối lại, hoặc đổi brain rồi chọn lại để tải mới.

## Liên quan

- [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md)
- [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md)
- [Quản lý tệp tin](05-quan-ly-tep-tin.md)
- [Agents & Workflows](07-agents-va-workflows.md)
- [Skills](06-skills.md)
- [Sao lưu brain lên GitHub](18-sao-luu-github.md)
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md)
