# Tab Code: Terminal ngay trong dashboard

Tab **Code** là khu vực làm việc kiểu lập trình viên của Javis. Chức năng đầu tiên của nó là **Terminal**: một dòng lệnh thật, chạy trên đúng máy đang chạy Javis, mở ngay trong trình duyệt. Không cần mở SSH ở cửa sổ khác nữa.

## Tính năng này là gì

Terminal ở đây là **pseudo-terminal thật của hệ điều hành**, không phải ô chữ giả lập. Nghĩa là:

- Chạy được mọi lệnh bạn vẫn gõ qua SSH: `git pull`, `ls`, `tail -f`, `pip install`, `agy`, `claude auth login`...
- Chạy được cả chương trình toàn màn hình: `htop`, `vim`, `nano`, `less`.
- Có màu, có gợi ý Tab, có lịch sử lệnh (mũi tên lên/xuống), có `Ctrl+C` giết đúng lệnh đang chạy chứ không giết cả phiên.
- Đổi cỡ cửa sổ thì shell biết ngay, nên chữ không bị gãy dòng lung tung.

Tab Code dựng sẵn theo hướng còn mở rộng: hôm nay có một dải tab với đúng mục **Terminal**, các chức năng sau sẽ thêm vào chính dải đó.

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định cổng 7777).
2. Rail điều hướng bên trái, mở nhóm **Bộ não**, bấm mục **Code**.
3. Terminal tự mở và tự nối. Bấm vào khung đen rồi gõ như terminal bình thường.

Terminal nằm cạnh **Tệp tin** vì hai trang này làm việc trên cùng một thư mục: shell mở sẵn ở **gốc brain đang chọn**, đúng thư mục mà trang Tệp tin đang duyệt.

## Thanh trên cùng

| Thứ | Ý nghĩa |
|---|---|
| Chấm tròn + chữ trạng thái | Xanh = đang chạy. Đỏ = mất kết nối (Javis tự nối lại). Xám = shell đã thoát. |
| Đường dẫn | Thư mục shell đang đứng lúc mở. Màn hình hẹp thì ẩn đi để nhường chỗ cho nút. |
| **Xoá** | Xoá màn hình, giống lệnh `clear`. |
| **Phiên mới** | Đóng hẳn phiên hiện tại (giết shell) rồi mở một phiên sạch. Dùng khi shell treo hoặc muốn bắt đầu lại. |

## Phiên chạy tiếp khi bạn rời tab

Đây là điểm quan trọng nhất khi dùng hằng ngày: **đổi trang hay tải lại trang KHÔNG giết shell.**

- Đang `npm install` mà bấm sang trang Trò chuyện: lệnh vẫn chạy. Quay lại tab Code là thấy nguyên màn hình cũ, chạy tới đâu hiện tới đó.
- Mất mạng, đóng máy, F5: Javis tự nối lại vào đúng phiên đó.
- Không ai quay lại trong **30 phút** thì Javis mới đóng phiên để khỏi bỏ quên tiến trình chạy hoài.
- Muốn đóng ngay thì bấm **Phiên mới**, hoặc gõ `exit`.

Mở tối đa **4 phiên** cùng lúc. Chạm trần thì Javis báo rõ thay vì im lặng mở thêm.

## Chế độ đơn giản trên Windows

Python trên Windows không có pseudo-terminal, nên ở đó tab Code chạy **chế độ đơn giản** và tự hiện một dòng cảnh báo ngay trên khung:

- Gõ nguyên một dòng rồi Enter, lệnh chạy và kết quả chảy về. Backspace sửa được, `Ctrl+C` ngắt được lệnh đang chạy.
- **Không** có gợi ý Tab, **không** có lịch sử lệnh bằng mũi tên, **không** chạy được chương trình toàn màn hình (`vim`, `htop`).

Linux, macOS và mọi bản Docker đều chạy chế độ đầy đủ.

## Ai vào được

Terminal là chỗ chạy lệnh tuỳ ý trên máy chủ, tức là quyền cao nhất dashboard có thể cấp. Vì thế:

- Chỉ **trình duyệt đã đăng nhập** vào được. Token API (loại `jvs_...` dùng cho script và CLI) **không** mở được terminal, kể cả token quyền `full`.
- Khi Javis chạy public (VPS, Docker) thì bắt buộc đăng nhập, nên terminal cũng được che sau đúng hàng rào đó. Xem [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).
- Shell thừa kế biến môi trường của server, trong đó có các khoá trong `.env`. Đúng như terminal của chủ máy, nhưng nên biết là nó ở đó khi cho người khác mượn màn hình.
- Muốn tắt hẳn tính năng: đặt `JAVIS_TERMINAL=0` rồi khởi động lại Javis. Vào tab Code sẽ thấy thông báo đã tắt thay vì khung trống.

## Biến môi trường

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `JAVIS_TERMINAL` | `0`/`off`/`false`/`no` = tắt hẳn terminal | Bật |
| `JAVIS_TERMINAL_SHELL` | Đường dẫn shell muốn chạy | `$SHELL`, không có thì `bash`/`sh`. Windows: `powershell.exe` rồi `cmd.exe` |
| `JAVIS_TERMINAL_CWD` | Thư mục shell mở ra | Gốc brain đang chọn |

Chi tiết cách đặt biến xem [Cấu hình .env](16-cau-hinh-env.md).

## Sự cố thường gặp

**Vào tab Code thấy "Terminal đang tắt trên máy này".** Máy chủ có `JAVIS_TERMINAL=0`. Bỏ biến đó trong `.env` rồi khởi động lại Javis.

**Báo "Đang mở 4 phiên terminal rồi".** Có phiên cũ còn sống ở tab trình duyệt khác. Bấm **Phiên mới** ở tab đó, hoặc chờ 30 phút để Javis tự dọn.

**Chữ gãy dòng, viền bảng lệch.** Bấm vào khung terminal rồi đổi cỡ cửa sổ trình duyệt một nhát để nó đo lại. Nếu vẫn lệch, gõ `clear`.

**Gõ Tab mà không có gợi ý.** Bạn đang ở chế độ đơn giản (Windows). Đó là giới hạn của hệ điều hành, không phải lỗi cấu hình.

**Shell thoát ngay khi vừa mở.** Xem `JAVIS_TERMINAL_SHELL` có trỏ đúng file thực thi không, và thư mục ở `JAVIS_TERMINAL_CWD` có tồn tại không.

## Liên quan

- [05 - Quản lý tệp tin](05-quan-ly-tep-tin.md) - duyệt và sửa cùng thư mục đó bằng giao diện.
- [24 - Javis CLI (terminal)](24-cli-terminal.md) - chiều ngược lại: gõ `javis "..."` từ terminal của máy bạn.
- [14 - Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - hàng rào đăng nhập che tab Code.
- [16 - Cấu hình .env](16-cau-hinh-env.md) - mọi biến môi trường.
