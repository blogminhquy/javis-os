# Cải tiến Hộp thư bot: lọc theo bot, trả lời ngay trong hòm thư (thiết kế)

Ngày 30/09/2026. Người yêu cầu: chủ dự án ("đề xuất cải tiến hòm thư, cần lọc hội thoại của nhiều bot, thêm nút trả lời
ngay trong chatbot để nhanh chóng chọn tự động trả lời nếu đang đúng chế độ; muốn dropdown chứ không phải hàng nút bấm").
Giao làm ba lát, mỗi lát một PR nhỏ. Lát 1 đã giao ở 0.65.3.

## 1. Vấn đề

- Chạy ba bot khác lĩnh vực (Javis Vũ, Nhi Mai, Ngọc Thu) thì hòm thư lẫn vào nhau: mỗi dòng chỉ có logo kênh, không có tên bot.
- Bộ lọc cũ chỉ có chip kênh (chỉ hiện khi có từ hai kênh) và một ô chọn bot bị ẩn khi có dưới hai bot có tài khoản.
  Không lọc được theo chưa đọc, cần trả lời, đang tiếp quản, nhóm hay chat riêng. Hàng chip lại tốn diện tích.
- Trả lời: gửi tay là tiếp quản ngầm (bot im), nút Tiếp quản nhỏ ở góc. Chưa có cách nhờ bot trả lời một tin nó đã im, chưa có
  cách nhờ bot soạn nháp cho chủ duyệt.

## 2. Quyết định (chủ chốt trong buổi thiết kế)

- **Dropdown, không phải chip.** Một hàng chung với ô tìm: Bot, Tình trạng, Loại; Kênh chỉ khi có từ hai kênh. Dùng ô chọn gốc của
  trình duyệt (trên điện thoại mở bộ chọn của máy). Số đếm nằm trong lựa chọn, tính trên TOÀN hòm thư nên không nhảy khi lọc.
  Chọn một giá trị mỗi ô. Đánh đổi đã nhận: không có chấm màu trong dropdown (mỗi dòng danh sách vẫn có thẻ tên bot cùng màu).
- **"Cần trả lời" phải có nghĩa thật.** Khách nhắn cuối, chưa ai đáp, chưa có người tiếp quản, VÀ (chat riêng, hoặc nhóm mà bot vừa
  cân nhắc nói rồi im). Đếm mọi nhóm có khách nhắn cuối thì bộ lọc đầy rác, vì bot chỉ nói khi được gọi là chuyện bình thường.
  "Bot cân nhắc rồi im" lấy từ kho bộ phán xử: quyết định `silent`, là ứng viên, mã `judge_silent` / `below_threshold` /
  `rate_limited` / `rate_limited_user` / `policy_error`, chưa có nhãn, trong 24 giờ. `agent_silent` (Agent chọn im có chủ ý) không tính.
- Mặc định của phần còn lại (chưa hỏi lại chủ, làm theo khuyến nghị): có cả hai "Trả lời giúp tin này" và công tắc tự động cho
  từng cuộc chat; có "Gợi ý câu trả lời".

## 3. Lát 1 (0.65.3, đã giao): bộ lọc và thẻ tên bot

- `conversations.danh_sach(status, chat_type, hesitant)`, `dem_bo_loc(hesitant)`; `bot_id="-"` = cuộc chat không có bot.
  Giá trị lạ của `status` / `chat_type` thì BỎ QUA bộ lọc đó (giá trị cũ còn lưu ở trình duyệt không được làm hòm thư trống).
- `GET /conversations` trả thêm `bot_name` và `need_reply` từng dòng, `facets`, và `bots` (bot có hội thoại, kèm tên; bot đã xoá
  hiện "Bot đã xoá", không lòi id thô). Kho bộ phán xử chưa có thì phần nhóm rỗng, không tạo file.
- Giao diện: `conversations-filters.js` (phần thuần: trạng thái, lưu trình duyệt, dựng `<option>`, màu bot) và vẽ ở `conversations.js`.
  Dropdown đang mở thì không dựng lại giữa nhịp tự làm mới 5 giây (đóng nó giữa chừng). Điện thoại: ô tìm và Bot mỗi cái một hàng,
  Tình trạng và Loại chia đôi một hàng. Thẻ tên bot chỉ khi có từ hai bot.

## 4. Lát 2 (0.65.4, đã giao): công tắc Tự động / Tôi trả lời và thanh trạng thái

- Đầu khung hội thoại: công tắc hai nấc **Tự động | Tôi trả lời** thay nút Tiếp quản nhỏ (gọi `POST /conversations/{id}/mode`, không API mới).
- Đáy khung: MỘT dòng trạng thái ("Nhi Mai đang trực cuộc này" / "Bạn đang tiếp quản, bot im") rồi hàng hai nút cùng cao, chia đôi bề ngang,
  không bao giờ rớt dòng (bản mẫu đầu bị lệch vì thẻ trạng thái nhỏ hơn nút và nút thứ hai rớt xuống); ô nhập và nút gửi cùng một hàng.
- Dòng "Bot im: <lý do>" ngay trong khung tin, lấy từ nhật ký bộ phán xử, khỏi mở menu. `GET /conversations/{id}/messages` trả thêm
  `bot_silence` (mã, điểm, ngưỡng) và `bot_name`. Điều kiện hiện, cố ý chặt vì hiện sai còn tệ hơn không hiện: cuộc chat ở chế độ AI, tin cuối là của
  khách, quyết định gần nhất là `silent` và lệch giờ với tin cuối không quá 60 giây. Người thật đang tiếp quản, bot đã đáp, quyết định là `reply`,
  hay kho bộ phán xử chưa có (không tạo file) thì không hiện. Nút "Vì sao" mở bảng Bộ phán xử của bot.
- Điện thoại: công tắc xuống hàng riêng rộng hết chiều ngang, hai nấc chia đôi, thay vì chèn tiêu đề còn vài chục điểm ảnh.

## 5. Lát 3 (0.65.5, đã giao): Trả lời giúp tin này và Gợi ý câu trả lời

- `POST /conversations/{id}/ai-reply` với `mode=send|draft`. Dùng đường trả lời sẵn có của CHÍNH bot đó (Agent của nó), bỏ qua cổng
  "có nên nói" nhưng giữ rào quyền và hạn mức an toàn. `send`: gửi qua kênh dưới danh nghĩa bot, cuộc chat vẫn ở Tự động, ghi Hộp thư là tin bot,
  và nếu tin đó từng bị bộ phán xử chọn im thì tính là nhãn "im nhầm" nặng nhất để bot học. `draft`: chỉ trả chữ để đổ vào ô nhập, KHÔNG ghi vào
  phiên Agent (dùng `phien_kho` / `ghi_kho=False` của `_tg_answer`) và không ghi Hộp thư.
- Chỉ bật khi đúng chế độ: bot đang chạy, cuộc chat đang ở Tự động, kênh gửi được. Không thì nút vẫn hiện, chạm vào nói lý do (không ẩn, không xám câm).
- Rủi ro đã canh (đều có test): không ghi trùng tin khách vào Hộp thư; không cho hai lượt chạy chồng trên một cuộc chat (`busy`); tin nhóm Zalo gửi đúng kiểu nhóm;
  bản nháp luôn dọn dấu vết kể cả khi engine ném lỗi; gửi hỏng thì trả chữ đã soạn; kênh của lượt lấy từ CHÍNH hội thoại (`meta._kenh`) để câu bot
  ghi ngược vào đúng hội thoại (test đầu tiên bắt được lỗi nó rơi sang kênh mặc định).
- **Tiếng vọng trên Zalo cá nhân**: đường gửi của kênh không nhớ câu vừa gửi (chỉ `Transport._gui` làm việc đó), nên câu bot gửi từ Hộp thư phải gọi
  `ghi_da_gui` trước khi gửi, không thì vòng đọc thấy nó quay về như tin của chính chủ (bot tưởng chủ nhắn tay nên im cả quãng) hoặc như tin khách
  (bot tự đáp chính mình). Đường gửi tay của chủ giữ nguyên hành vi cũ.
- Dòng trạng thái nói thật khi bot đang tắt ("đang tắt nên không tự trả lời"), không ghi "đang trực".

## 6. Không làm (cố ý)

- Không lọc nhiều bot cùng lúc, không nhóm theo bot, không dropdown tự vẽ (chưa cần).
- Không gộp Hòm thư với trang Trò chuyện.
