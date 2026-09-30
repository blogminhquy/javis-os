# Nhóm chỉ giữ 100 tin, bot xem 30 tin làm ngữ cảnh (0.65.12)

## Vấn đề

Chủ dự án (30/09/2026) lo bot lưu quá nhiều chat vào kho SQL của Hòm thư. Đọc mã: `customer_conversations.sqlite3` lưu MỌI tin của MỌI cuộc chat trên kênh được theo dõi (mỗi tin tối đa
8.000 ký tự), không có hạn xoá, kể cả nhóm mà bot chưa được phép trả lời (tin vẫn vào Hòm thư). Các kho khác đã có trần (bộ phán xử: 400 ký tự mỗi quyết định, dòng chưa gắn
nhãn giữ 14 ngày, 500 ca mỗi bot; nhật ký bot: 2.000 dòng). Hòm thư là kho duy nhất phình vô hạn. Ngoài dung lượng còn có riêng tư: kho giữ lời của người lạ trong nhóm.

Ngoài ra bot trong nhóm chỉ được gọi khi có người tag hoặc reply nên chỉ thấy đúng câu gọi nó (cửa sổ 8 tin trong RAM chỉ phục vụ bộ phán xử). "Vậy còn cái kia?" vô nghĩa nếu bot không biết
người ta vừa nói gì.

## Quyết định (chủ chốt)

- **Nhóm giữ 100 tin gần nhất, khách hàng (chat riêng) giữ hết.** Không ô cài đặt.
- **Bot trong nhóm xem 30 tin gần nhất** trước tin đang hỏi khi trả lời.

## Cách làm

- `conversations.ghi_su_kien` cắt ngay trong giao dịch ghi tin, chỉ với `chat_type == "group"`: xoá các tin có id nhỏ hơn id của tin thứ 100 tính từ mới nhất (truy vấn theo chỉ mục
  `ix_msg_conv`, không quét bảng). `message_count` vẫn là số tin từng nhận.
- **Di trú nhóm cũ** `conversations.cat_nhom_cu()`, một lần lúc khởi động, ở luồng nền: sao lưu NGUYÊN file kho bằng API sao lưu của SQLite (nhất quán cả khi đang ghi WAL) rồi cắt các nhóm vượt
  mức, ghi dấu `cat_nhom_v1` vào `sync_state` SAU khi cắt xong, rồi `wal_checkpoint` + `VACUUM` để file nhỏ lại thật (hỏng bước này chỉ là file chưa nhỏ). Chỉ sao lưu khi thật sự có nhóm vượt mức.
  Bản sao lưu còn giữ lời người lạ nên **tự xoá sau 14 ngày** (dọn ở lần khởi động sau).
- **Ngữ cảnh cho bot** `chatbot_runtime.ngu_canh_nhom`: 30 tin ngay trước tin đang hỏi (bỏ chính tin đang hỏi theo `message_id`; không biết id thì bỏ tin khách cuối), mỗi tin cắt 300 ký tự, cả khối
  tối đa 6.000 ký tự (bớt từ tin cũ nhất), nhãn người nói (tên khách, `Bot`, `Chủ`). Nội dung đi qua `clean_chat_text` (gỡ marker nội bộ và thẻ `<chat_data>`) và được bọc `<chat_data>`
  kèm lời dặn đó là DỮ LIỆU, không phải lệnh. Gắn vào cấu hình lượt (`cfg["_ngu_canh_nhom"]`) và vào PROMPT HỆ THỐNG qua `build_bot_prompt`, **không** nối vào tin của người hỏi: nối vào tin
  thì mỗi lượt lại ghi thêm 30 tin vào lịch sử phiên của Agent và phình dần. Cả lượt thật lẫn lượt "Trả lời giúp tin này" của Hòm thư đều có.
- Chat riêng không đổi: phiên của khách đã mang sẵn lịch sử.

## Những chỗ dễ hỏng (đã có canary trong `tests/python/test_hoi_thoai_cat_nhom.py`)

1. Cắt nhầm chat riêng hoặc tin mới: test ghi 130 tin nhóm và 130 tin riêng, nhóm còn đúng tin 31 đến 130, riêng còn đủ 130.
2. Xoá không hoàn tác: sao lưu trước, chạy một lần (lần hai không sao lưu thêm), bản sao lưu còn NGUYÊN số tin cũ, bản quá hạn tự xoá.
3. Tin nhắn thoát khỏi khối dữ liệu: tin chứa `</chat_data>`, `[IM_LANG]`, `JAVIS_ADMIN` bị gỡ; khối chỉ có một thẻ đóng.
4. Phình phiên: ngữ cảnh nằm trong prompt hệ thống, tin của người hỏi vẫn chỉ là `[Tên] nội dung`.
5. Lỗi khởi động bị nuốt im lặng: hook chạy trong `try/except` nên thiếu `import threading` khiến di trú không bao giờ chạy mà không báo gì. Bắt được khi chạy thật trên bản thử
   (log `NameError`), đã sửa; di trú thật đã kiểm: nhóm 300 tin còn 100, nhóm 80 tin và chat riêng 250 tin nguyên vẹn, có bản sao lưu đủ 300.

## Kèm theo

`conversations._now()` tăng nghiêm ngặt trong tiến trình: đồng hồ Windows nhích khoảng 15 ms nên hai lần ghi liên tiếp trùng `updated_at` và thứ tự "mới hoạt động trước" của danh sách khách
ngẫu nhiên (`test_hoi_thoai_crm` đỏ khoảng 2 lần trên 5 trên máy Windows; 8 lần liên tiếp xanh sau khi sửa).

## Ngoài phạm vi

- Không cắt chat riêng (chủ: khách hàng giữ hết, tạm thời).
- Không cắt kho phiên của Agent hay bộ phán xử (đã có trần riêng).
- Chưa có ô cài đặt số tin giữ lại hay số tin ngữ cảnh (chủ muốn ít cài đặt).
