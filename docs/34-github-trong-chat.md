# GitHub ngay trong khung chat

***Tiếng Việt** · [English](en/34-github-in-chat.md)*

Gắn repo GitHub vào một cuộc trò chuyện, giao việc bằng lời, rồi để Javis tự lo phần còn lại: sửa code trên nhánh riêng, tự kiểm tra, đẩy lên, mở PR, theo dõi CI, tự sửa khi CI đỏ và merge khi xanh. Bạn nhìn tiến độ bằng một biểu tượng nhỏ cạnh cuộc trò chuyện.

Thiết kế đầy đủ: [docs/dev/2026-10-github-trong-chat-spec.md](dev/2026-10-github-trong-chat-spec.md).

## 1. Kết nối GitHub (một lần)

Mở **Kết nối**. Thẻ **GitHub** luôn nằm đầu danh sách, có sẵn trong Javis, không phải cài gói nào.

1. Trên github.com: **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Chọn các repo cho Javis làm việc. Bật quyền: **Contents**, **Pull requests**, **Workflows** (Read and write); **Checks**, **Actions**, **Commit statuses**, **Metadata** (Read).
3. Dán token vào thẻ GitHub, bấm **Kết nối**.

Đã bật [sao lưu brain lên GitHub](18-sao-luu-github.md)? Bấm **Dùng token sao lưu brain** để dùng chung, Javis kiểm quyền trước. Token cũ dạng `ghp_...` cần quyền `repo` và `workflow`.

Token được mã hoá khi lưu và không bao giờ gửi về trình duyệt. Javis đưa token vào git qua biến môi trường của riêng lệnh đó, nên model chạy lệnh trong thư mục repo không có cách nào tự đẩy code.

## 2. Gắn repo vào cuộc trò chuyện

Trong khung chat bấm **dấu cộng → Repo GitHub**, tích một hay nhiều repo, bấm **Gắn**. Chip tên repo hiện cạnh ô nhập.

- Javis tải repo về máy, **ngoài** thư mục brain (`<thư mục trạng thái>/repos/<brain>/<owner>/<repo>`), nên code không lẫn vào bản sao lưu brain hay ô tìm kiếm.
- Mỗi cuộc trò chuyện làm trên **một nhánh và một thư mục riêng** (`javis/...`). Hai cuộc cùng sửa một repo không bao giờ đè việc của nhau.
- Gắn repo không chạy script, không cài gì cho tới khi bước kiểm tra cần.

## 3. Sau mỗi lượt có sửa code

Javis tự làm, không cần bạn nhắc:

1. **Kiểm tra ở máy**: chạy đúng bộ lệnh CI của repo (đọc từ `.github/workflows`, bỏ bước cài vào máy, cần secret hay deploy), quét thông tin bí mật trong diff, dò các kiểu "ăn gian cho CI xanh" (bỏ qua test, xoá test, sửa workflow, nới coverage). Lệnh đỏ thì **không đẩy**, Javis mở một lượt sửa kèm lỗi.
2. **Commit, đẩy lên, mở PR** (dạng nháp) dưới tên tài khoản GitHub của bạn.
3. **Theo dõi CI** theo đúng commit vừa đẩy. Commit mới không bao giờ thừa hưởng kết quả xanh của commit cũ.
4. **CI đỏ**: Javis mở lượt sửa ngay trong cuộc trò chuyện đó, kèm log. Tối đa **3 vòng**, quá thì báo kẹt kèm lý do. Đỏ cả trên nhánh chính thì báo không phải lỗi của việc này, không sửa lan.
5. **Review chéo**: CI xanh rồi, một engine **khác hãng** với engine đã viết đọc diff và chỉ nêu lỗi có đường gây hỏng cụ thể. Tác giả kiểm chứng: đúng thì sửa, sai thì bác bỏ kèm lý do.
6. **Merge**: CI xanh thì Javis **tự merge** theo kiểu merge repo cho phép. Không tự merge khi: tắt công tắc của repo, có thay đổi "ăn gian" cần người xem, repo không có CI, hay repo còn đòi người duyệt.

Lệnh kiểm tra của từng repo sửa được ở thẻ GitHub trên trang Kết nối, nút **Lệnh kiểm tra**. Công tắc **Tự merge khi CI xanh** cũng ở đó, mặc định bật.

## 4. Bốn biểu tượng cạnh cuộc trò chuyện

| Biểu tượng | Nghĩa |
|---|---|
| Nhánh nhấp nháy (kèm số) | Đang làm, hoặc đang chờ CI; số là số việc chạy song song |
| Nhánh có dấu tích, màu xanh | Sẵn sàng merge |
| Biểu tượng hợp nhất, màu tím | Đã merge (có dấu cảnh báo nếu kiểm tra sau merge đỏ) |
| Tam giác cảnh báo | Cần xử lý lại: xung đột, merge hỏng, hay bị kẹt |

Bấm vào biểu tượng để mở bảng chi tiết: nhánh, link PR, từng kiểm tra CI, lý do kẹt, thay đổi cần người xem, việc kế tiếp đang chờ, và nút **Merge** khi PR sẵn sàng.

## 5. Việc kế tiếp

Giao nhiều việc một lúc ("xong cái này thì làm cái kia")? Javis xếp việc kế tiếp và **chỉ bắt đầu khi PR hiện tại đã merge và kiểm tra trên nhánh chính sau merge đã qua**. CI xanh không bao giờ tự sinh việc mới ngoài những gì bạn đã giao.

## 6. Bài học và số đo

- Mỗi lần CI hay kiểm tra ở máy đỏ rồi được sửa, Javis ghi một dòng bài học cho repo đó vào `Javis/learned/repos/` trong brain, và nạp lại ở lượt sau.
- Nút **Số đo** trên thẻ GitHub cho biết, theo từng engine và model: tỉ lệ xanh ngay lần đẩy đầu, số vòng sửa trung bình, số lỗi review chéo bắt được. Chọn model bằng số thật.

## 7. Gỡ repo

- **Bỏ khỏi cuộc trò chuyện** (bỏ tích trong dấu cộng → Repo GitHub): bản tải về vẫn giữ.
- **Gỡ khỏi brain** (thẻ GitHub trên trang Kết nối): xoá bản trên máy, repo trên GitHub giữ nguyên. Javis từ chối khi còn sửa đổi chưa lưu, commit chưa đẩy, hay việc đang chạy.
- Xoá một cuộc trò chuyện: thư mục làm việc sạch của nó bị dọn, thư mục còn việc dở được giữ lại.
