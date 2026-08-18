# Nhóm Code: Terminal ngay trong dashboard

**Code** là một nhóm riêng trên thanh điều hướng - khu vực làm việc kiểu lập trình viên của Javis. Mục đầu tiên trong nhóm là **Terminal**: một dòng lệnh thật, chạy trên đúng máy đang chạy Javis, mở ngay trong trình duyệt. Không cần mở SSH ở cửa sổ khác nữa.

## Tính năng này là gì

Terminal ở đây là **pseudo-terminal thật của hệ điều hành**, không phải ô chữ giả lập. Nghĩa là:

- Chạy được mọi lệnh bạn vẫn gõ qua SSH: `git pull`, `ls`, `tail -f`, `pip install`, `agy`, `claude auth login`...
- Chạy được cả chương trình toàn màn hình: `htop`, `vim`, `nano`, `less`.
- Có màu, có gợi ý Tab, có lịch sử lệnh (mũi tên lên/xuống), có `Ctrl+C` giết đúng lệnh đang chạy chứ không giết cả phiên.
- Đổi cỡ cửa sổ thì shell biết ngay, nên chữ không bị gãy dòng lung tung.

Nhóm Code dựng sẵn theo hướng còn mở rộng: hôm nay trong nhóm mới có đúng mục **Terminal**, các công cụ lập trình khác sẽ thành các mục kế tiếp trong cùng nhóm đó.

## Mở ở đâu trong Javis

1. Mở dashboard Javis (mặc định cổng 7777).
2. Rail điều hướng bên trái, mở nhóm **Code**, bấm mục **Terminal**.
3. Terminal tự mở và tự nối. Bấm vào khung đen rồi gõ như terminal bình thường.

Shell mở sẵn ở **thư mục HOME của user đang chạy Javis** - đúng như một terminal bình thường của máy, hợp nhất cho việc chính của tab này: cài và đăng nhập CLI (`agy`, `codex login`...). Cần vào brain thì gõ `cd "$JAVIS_BRAIN"` - biến này luôn trỏ về gốc brain đang chọn.

## Nhiều tab, mỗi tab một shell riêng

Ngay trên khung terminal có một dải tab, giống tab của trình duyệt:

- Bấm nút **+** để mở thêm tab - mỗi tab là một shell hoàn toàn riêng, việc tab này không đụng tab kia. Tiện khi vừa `tail -f` log ở một tab, vừa gõ lệnh ở tab khác.
- Bấm vào tên tab để chuyển qua lại. Tab đang khuất vẫn chạy bình thường: lệnh không dừng, output không mất.
- Bấm dấu **x** trên tab là đóng hẳn phiên đó (giết shell). Đóng tab cuối cùng thì Javis tự mở một tab sạch thay vào.
- Tối đa **4 tab** (đúng trần số phiên của server, tính chung mọi cửa sổ trình duyệt). Chạm trần thì nút **+** tự khoá.
- F5 hay đổi trang rồi quay lại: nguyên dàn tab được mở lại, tab nào đang xem vẫn đang xem.

## Thanh trên cùng

| Thứ | Ý nghĩa |
|---|---|
| Chấm tròn + chữ trạng thái | Của tab đang xem. Xanh = đang chạy. Đỏ = mất kết nối (Javis tự nối lại). Xám = shell đã thoát. |
| Đường dẫn | Thư mục shell đang đứng lúc mở. Màn hình hẹp thì ẩn đi để nhường chỗ cho nút. |
| **Xoá** | Xoá màn hình của tab đang xem, giống lệnh `clear`. |
| **Khởi động lại** | Đóng hẳn phiên của tab đang xem (giết shell) rồi mở một phiên sạch trong cùng tab. Dùng khi shell treo hoặc muốn bắt đầu lại. |

## Phiên chạy tiếp khi bạn rời tab

Đây là điểm quan trọng nhất khi dùng hằng ngày: **đổi trang hay tải lại trang KHÔNG giết shell.**

- Đang `npm install` mà bấm sang trang Trò chuyện: lệnh vẫn chạy - ở MỌI tab, không riêng tab đang xem. Quay lại tab Code là thấy nguyên dàn tab cũ, chạy tới đâu hiện tới đó.
- Mất mạng, đóng máy, F5: Javis tự nối lại vào đúng các phiên đó.
- Không ai quay lại trong **30 phút** thì Javis mới đóng phiên để khỏi bỏ quên tiến trình chạy hoài.
- Muốn đóng ngay thì bấm dấu **x** trên tab, bấm **Khởi động lại**, hoặc gõ `exit`.

Mở tối đa **4 phiên** cùng lúc (tính chung mọi cửa sổ trình duyệt). Chạm trần thì Javis báo rõ thay vì im lặng mở thêm.

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
| `JAVIS_TERMINAL_CWD` | Thư mục shell mở ra | HOME của user chạy Javis |

Chi tiết cách đặt biến xem [Cấu hình .env](16-cau-hinh-env.md).

## Sự cố thường gặp

**Vào mục Terminal thấy "Terminal đang tắt trên máy này".** Máy chủ có `JAVIS_TERMINAL=0`. Bỏ biến đó trong `.env` rồi khởi động lại Javis.

**Báo "Đang mở 4 phiên terminal rồi".** Trần 4 phiên tính chung mọi cửa sổ trình duyệt. Đóng bớt một tab (dấu **x**) ở cửa sổ đang mở nó, hoặc chờ 30 phút để Javis tự dọn phiên không ai xem.

**Chữ gãy dòng, viền bảng lệch.** Bấm vào khung terminal rồi đổi cỡ cửa sổ trình duyệt một nhát để nó đo lại. Nếu vẫn lệch, gõ `clear`.

**Gõ Tab mà không có gợi ý.** Bạn đang ở chế độ đơn giản (Windows). Đó là giới hạn của hệ điều hành, không phải lỗi cấu hình.

**Shell thoát ngay khi vừa mở.** Xem `JAVIS_TERMINAL_SHELL` có trỏ đúng file thực thi không, và thư mục ở `JAVIS_TERMINAL_CWD` có tồn tại không.

## Liên quan

- [05 - Quản lý tệp tin](05-quan-ly-tep-tin.md) - duyệt và sửa cùng thư mục đó bằng giao diện.
- [24 - Javis CLI (terminal)](24-cli-terminal.md) - chiều ngược lại: gõ `javis "..."` từ terminal của máy bạn.
- [14 - Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - hàng rào đăng nhập che nhóm Code.
- [16 - Cấu hình .env](16-cau-hinh-env.md) - mọi biến môi trường.
