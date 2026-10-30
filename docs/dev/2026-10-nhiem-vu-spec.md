# Trang Nhiệm vụ (spec, 2026-10-30)

Chủ repo duyệt bản HTML mẫu ngày 30/10/2026 (artifact "Nhiệm vụ", bản 41). Spec này chép lại
những gì bản mẫu đã chốt, thêm phần dữ liệu và máy chủ để code theo, và chia việc thành 4 phần.
Mỗi phần là một phiên bản riêng, CI xanh mới gộp.

## 1. Mục tiêu

- Gộp trang **Kanban** và trang **Việc định kỳ** thành MỘT trang **Nhiệm vụ**. Nhóm nav "Việc"
  còn hai mục: **Nhiệm vụ** và **Webhook**.
- Hai tab: **Của tôi** (việc người dùng tự làm) và **Javis làm** (việc Javis chạy: việc Kanban,
  lời nhắc, loop). Tab mặc định là Của tôi, nhớ tab và danh sách đã chọn.
- Bỏ nút **Bản tin buổi sáng** và mẫu bản tin có sẵn.
- Ngoài mặt chỉ để thứ cần nhìn và cần bấm. Không có dòng mô tả thừa (luật nút (i) ở
  `docs/quy-uoc-dev.md`).

## 2. Bố cục

### Máy tính
- Cột trái dính khi cuộn, tự cuộn khi dài, thanh cuộn ẩn tới khi rê chuột. Trên cùng là chữ
  "Nhiệm vụ", rồi các danh sách thông minh, rồi Dự án (tab Của tôi) hoặc Trợ lý (tab Javis làm).
- Cột phải: hàng tab Của tôi | Javis làm dính trên cùng, ô tìm, rồi nội dung danh sách.
- Bấm một việc mở khung chi tiết bên phải (drawer). Nút **+** tròn ở góc dưới phải.

### Điện thoại
- Không có chữ "Nhiệm vụ". Chỉ hàng tab dính trên cùng, phần còn lại cuộn như thường.
- Kiểu TickTick: màn hình chủ là danh sách các danh sách, bấm vào là màn hình danh sách, bấm một
  việc là màn hình chi tiết, có nút quay lại. Nút **+** góc dưới phải.

## 3. Danh sách thông minh

| Tab | Danh sách |
|---|---|
| Của tôi | Tất cả việc, Hôm nay, Sắp tới, Quá hạn, Chưa có lịch, Lặp lại, Thói quen, Đã xong |
| Javis làm | Tất cả việc, Hôm nay, Sắp tới, Quá hạn, Lặp lại, Chạy lỗi, Đã xong, Nhật ký |

- **Quá hạn** có nút "Dời tất cả sang hôm nay" (chỉ dời việc làm một lần). Khối quá hạn cũng hiện
  trên đầu Hôm nay và Tất cả việc.
- **Quá hạn** có cả **lần lặp gần nhất bị bỏ lỡ** của việc lặp và thói quen của tôi, tích được tại
  chỗ. Chỉ lần gần nhất. Lịch hẹn lặp thì không (hết giờ là tự thành "Đã diễn ra").
- **Chạy lỗi**: "Đang dừng hoặc sắp lỗi" nhóm theo ngày, và "Lịch sử lỗi 7 ngày".
- **Lặp lại** xếp theo lần tới gần nhất (ngày rồi giờ). **Thói quen** xếp theo giờ người dùng hay
  làm (Javis học được), có buổi hôm nay lên trước, hôm nay nghỉ xuống sau, đang tắt xuống cuối.
- **Dự án** (chỉ tab Của tôi): chấm tròn màu. Tạo, sửa tên và màu, xoá (có hoàn tác), ghim.
- **Trợ lý** (chỉ tab Javis làm): avatar nhỏ đứng yên của trợ lý. Chỉ ghim, không sửa xoá (đã có
  trang quản lý riêng).
- Phân trang: hiện 6 dự án hoặc trợ lý, rồi "Xem thêm N..." / "Thu gọn". Cái đã ghim luôn lên đầu.

## 4. Hàng việc và thao tác

- Hàng việc của tôi: ô tròn để tích. Tích xong có toast "Hoàn tác"; bấm dấu tích xanh là bỏ tích.
- Hàng lặp bên Của tôi: ô tròn "xong lần này". Bên Javis làm: nút ▶ **Chạy ngay** (mờ khi đang
  tắt hoặc thiếu kết nối). Đang chạy thì nút thành ■ **Dừng** có vòng xoay, bấm là ngắt ngay,
  lịch lặp giữ nguyên. Việc đang tự chạy theo lịch cũng có nút ■.
- Menu ⋯:
  - Việc của tôi: Sửa, Giao cho Javis.
  - Việc Javis: Bỏ qua lần tới, Tạm dừng, Huỷ việc, Chuyển cho tôi làm.
  - Cả hai: Chuyển hoặc Nhân bản sang brain khác (kiểm tra brain kia có đủ kết nối), Xoá (hoàn
    tác, không hỏi lại).
- Hoàn tác (toast): tích xong, xong lần này, chạy ngay, giao qua lại, dời quá hạn, xoá, xoá dự án.
- Hộp hỏi (việc Javis cần người dùng làm, ví dụ kết nối lại Pancake) gọn một dòng. Việc Javis tự
  xử lý được thì không báo.

## 5. Form thêm (nút +)

- Đầu form: **Việc | Lịch hẹn**.
- **Việc**: Việc gì, Ai làm (Tôi / Javis), Javis làm thế nào (Tự làm rồi báo / Chỉ nhắc), Ngày
  giờ, Lặp lại, **Kiểu lặp** (Lặp lại | Thói quen, chỉ việc của tôi có lặp), Dự án (chỉ của tôi).
  Bấm + trong mục Thói quen: đặt sẵn lặp mỗi ngày và chọn sẵn Thói quen.
- **Lịch hẹn**: Hẹn gì, Bắt đầu, Kéo dài (ô thả), Kết thúc lúc, Nhắc trước (ô thả), Lặp lại, Dự
  án, Địa điểm (gập), "Nhờ Javis chuẩn bị trước" (tạo một việc Javis chạy trước giờ hẹn 30 phút).
- Chọn ngày: nút chỉ icon (Khi rảnh, Hôm nay, Ngày mai, Thứ Hai tới), lịch tháng bắt đầu thứ Hai,
  ô giờ mỗi 30 phút cộng "giờ khác". Mặc định Khi rảnh và Không đặt giờ. Việc có ngày mà không giờ
  là việc "trong ngày".
- Chọn lặp: "Mỗi [n] [phút/giờ/ngày/tuần/tháng/năm]", vòng tròn thứ khi chọn tuần, Bỏ lặp / Xong.
- Nhiều lựa chọn dùng ô thả xuống; hai lựa chọn dùng nút bật.
- Chữ đang gõ không mất khi form vẽ lại.

## 6. Lịch hẹn

- Khối có thanh màu (màu dự án). Nhãn: Đang diễn ra, Trùng giờ, Đã diễn ra (tự chuyển khi qua giờ).
- Lịch Google Calendar (khi đã kết nối) chỉ đọc, sửa ở Google.

## 7. Thói quen

- Thói quen = việc lặp của tôi có bật giữ lửa. Chuyển qua lại bằng công tắc "Tính là thói quen";
  tắt rồi bật lại thì chuỗi cũ còn nguyên.
- **Chuỗi chỉ tính ngày có lịch.** Ngày không có lịch là ngày nghỉ: không đóng băng, không gãy,
  không cộng. Bỏ 1 buổi có lịch: đóng băng. Bỏ 2 buổi có lịch liền nhau: mất chuỗi. Hằng tuần
  một buổi tự thành đếm theo tuần, hằng tháng theo tháng.
- Sửa tay được hôm nay và buổi có lịch gần nhất. Ngày nghỉ không tích được.
- Ô tích: vòng tròn thường; đang đóng băng là hạt băng xanh; ngày nghỉ là vòng nét đứt; xong là
  ngọn lửa. Hiệu ứng tích phẳng 2D khoảng 0,3 giây: lửa bật lên kèm một vòng lan; hạt băng co lại
  biến mất rồi mới bật lửa. Điện thoại rung 1 nhịp ngắn. Tôn trọng giảm chuyển động.
- Chi tiết thói quen: số ngày giữ lửa to, 3 ô (Ngày xong, Đóng băng, Dài nhất), lịch tháng nối dải
  như Duolingo (ngày nghỉ nằm giữa chuỗi nối nhạt), chấm trắng cho ngày Javis tích theo lời báo.
  Nhắc nhở: Javis tự nhắc / Nhắc đúng giờ (ô giờ) / Không nhắc.
- Đầu mục Thói quen: 4 ô số (Hôm nay x/y, Đóng băng, Chuỗi dài nhất, Tuần này %). Chưa đạt thì
  xám; tuần này từ 80% xanh, 50-79% vàng, dưới 50% đỏ, 0 xám.
- Ngôi sao linh vật Javis (đúng hình và bộ mắt trong `dashboard/pet.js`) nói một lời nhắn trong
  bong bóng cao cố định, sao nằm giữa. Biểu cảm theo tình trạng: bỏ buổi = dỗi (suspicious), xong
  hết = love, xong một phần = excited, sắp chạm mốc = wink (còn 3 ngày trở xuống: gang), tuần từ
  80% = happy, ngày nghỉ = sleepy, còn lại = curious. Chấm chuyển lời nhắn, X ẩn tới hết ngày.
- **Lời nhắn do Javis Core viết.** Core chạy nền tự viết lời nhắn ngắn: động viên khi làm tốt,
  dỗi khi bỏ buổi, tìm mọi cách để người dùng làm xong (đổi giờ nhắc, đổi giọng, nhắc mốc chuỗi),
  và tự học kiểu lời nào làm người đó hoàn thành. Câu mẫu có sẵn là dự phòng khi Core chưa chạy.
  Viết mỗi ngày một lượt rồi dùng lại, không gọi model mỗi lần mở trang.
- **Javis tích theo lời báo.** Người dùng nói "đọc sách xong rồi" trong chat là Javis tích. Chỉ
  tích khi người dùng nói rõ là đã xong, luôn để lại dấu (chấm trắng) và hoàn tác được.

## 8. Dữ liệu và máy chủ

(Điền ở mục 10 sau khi đọc code hiện có.)

## 9. Chia phần

1. **Phần 1, 0.422.0:** trang Nhiệm vụ với tab **Javis làm** chạy trên dữ liệu đang có (việc
   Kanban, lời nhắc, loop): danh sách thông minh, trợ lý, chạy ngay và dừng, hoàn tác, Chạy lỗi,
   Nhật ký, menu ⋯, bật tắt "AI tự vận hành", form + cho việc Javis. Đổi nav, bỏ bản tin sáng.
   Tab Của tôi hiện trống với nút thêm, chưa lưu.
2. **Phần 2:** tab **Của tôi**: kho việc cá nhân theo brain, dự án, chọn ngày và lặp, quá hạn có
   lần lặp bị lỡ, giao qua lại giữa tôi và Javis, chuyển brain.
3. **Phần 3:** **Thói quen**: chuỗi theo ngày có lịch, lịch tháng, ô số, ngôi sao với câu mẫu,
   hiệu ứng tích, nhắc nhở.
4. **Phần 4:** **Lịch hẹn** (và đọc Google Calendar khi có MCP), tool cho Javis tích thói quen và
   thêm việc của tôi qua chat, Core viết lời nhắn nền và tự học.
