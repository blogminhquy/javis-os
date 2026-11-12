# Vòng cải tiến của Javis Core: một vòng, nhiều núm

Spec viết ngày 10/11/2026, đi tiếp sau `2026-11-so-diem-viec-nen-spec.md`. Chủ repo yêu cầu: "đề xuất cải tiến cùng
Javis Core để có khả năng tự động scale và không ảnh hưởng đến performance, trở thành cả một hệ thống tự cải tiến theo
thời gian và cách dùng của người sử dụng".

Nguyên tắc: không phần nào của Javis tự mang theo bộ máy tự điều chỉnh riêng. Phần nào muốn tự cải tiến thì **đăng ký
một núm chỉnh** với Javis Core, và Javis Core chạy cùng một vòng cho mọi núm.

Mục 1 đến 5 là phần ĐÃ LÀM. Mục 6 là phần chưa làm.

## 1. Núm chỉnh và vòng chạy (`server/core_loop.py`)

Một núm khai: mã, tên, khoảng giá trị, mặc định, cách đọc, cách ghi, và tuỳ chọn một **luật** (mã thuần, nhìn các
con số phần đó vốn đã ghi, trả về giá trị đề nghị kèm lý do).

Vòng làm phần còn lại, giống nhau cho mọi núm:

| Luật của vòng | Vì sao |
|---|---|
| Luật chỉ dời núm MỘT bước mỗi lần, không bao giờ ra ngoài khoảng | Không có cú nhảy lớn dựa trên vài con số |
| Mỗi núm bị luật dời nhiều nhất một lần mỗi ngày | Hai lần dời không đuổi nhau |
| Núm chủ đang tự giữ (`frozen`) thì luật không đụng | Lựa chọn tay luôn thắng |
| Mỗi lần dời ghi lại ai dời, vì sao, từ đâu sang đâu, và báo một lần | Giải thích được |
| Hoàn lại bằng mã số; sau khi hoàn lại, luật để yên núm đó 14 ngày | Không làm lại ngay điều chủ vừa bỏ |
| Giá trị chủ đặt bằng lời (`javis_tune op=set`) thì luật để yên núm đó 30 ngày, qua cả lần khởi động lại | Điều chủ nói phải đứng vững |
| Một luật lỗi không làm dừng luật khác | Vòng không chết vì một phần |

Ba loại tác nhân, theo chi phí tăng dần:

- `rule`: mã nhìn các bộ đếm (`core_loop.tick`, 10 phút một lần, ở luồng phụ). Không gọi model.
- `core`: Javis Core đề nghị sau khi suy xét, trong hạn mức ngày của chính nó. **Chưa làm** (mục 6).
- `owner`: lời chủ nói trong chat (`javis_tune op=set`). Luôn thắng, được nhảy nhiều bước.

Sổ điểm việc nền là họ núm đầu tiên (mỗi việc một núm, luật riêng là `job_scorecard.step`). Nó giữ bảng riêng vì dời
sau từng lần chạy; `status` và `undo` của vòng hiển thị và hoàn lại cả hai, nên chủ thấy một danh sách duy nhất. Mã thay
đổi dạng số là của sổ điểm, dạng `k12` là của núm.

## 2. Núm đầu tiên không phải model: `learn.min_turns`

Số lượt đáng học phải có trong hàng chờ trước khi một mẻ tự học tự động được mở. Khoảng 1 đến 4, mặc định 1.

- Bằng chứng: mỗi mẻ tự động ghi 1 (học ra được ít nhất một thứ) hoặc 0 (không ra gì) vào một danh sách 12 mẻ gần
  nhất (`learn_config.json`, `_state.yield`). Mẻ chủ bấm tay không tính.
- Luật (`learn.LearnFeature.min_turns_rule`): cần ít nhất 6 mẻ. Từ ba phần tư trở lên là mẻ rỗng thì tăng một; từ ba
  phần tư trở lên là mẻ có ích và núm đang cao hơn mặc định thì giảm một. Sau mỗi lần dời, bằng chứng tính lại từ đầu.
- Không mất gì: lượt chưa đủ ngưỡng vẫn nằm trong hàng chờ và được học cùng các lượt sau. Câu "ghi nhớ giúp" và mốc
  chờ tối đa 2 giờ bỏ qua núm này.

Ý nghĩa: người hay hỏi nhanh một hai câu số liệu thì mẻ học thường rỗng, Javis tự thôi mở mẻ cho những cuộc như vậy.
Người hay bàn chuyện dài thì núm ở yên mức 1.

## 3. Tín hiệu mới: ghi nhớ bị chủ xoá

`memory_control.forget_memory` báo cho người nghe (`on_forget`) kèm cờ `learned`: ghi nhớ đó do vòng tự học viết
(`origin: javis-learned`) hay do chủ hoặc một lượt chat viết. Ghi nhớ Javis tự học mà chủ xoá thì tính một lần "hỏng do
model" cho việc `learn` trong sổ điểm, nên mẻ học kế tiếp chạy model cao hơn một bậc. Ghi nhớ chủ tự viết bị xoá thì
không nói gì về người học.

## 4. Bài học về cách học do Javis Core giữ

- Lưu trong kho bài học có phạm vi sẵn có (`agent_lessons`), là bài học của Javis Core ở brain đó, phạm vi `*`, gắn
  nhãn `learning` để phân biệt với bài học về cách nói chuyện.
- Chủ dặn bằng lời: `javis_tune op=teach {text}` ("đừng ghi doanh thu từng ngày thành ghi nhớ").
- Mỗi mẻ tự học đọc các bài học này ĐẦU TIÊN, trước hướng dẫn có sẵn (`LearnDeps.learning_lessons`).
- Xem và thu hồi như bài học của mọi trợ lý: `javis_memory op=lessons|lesson_revoke agent=javis-core`. Javis Core
  được thêm vào danh sách trợ lý của tool đó.
- Khối vai trò của Javis Core (`system/agents/javis-core.md`) thêm một dòng: việc nền và tự học đi qua `javis_tune`.
  Dòng này chỉ có trong lượt chat với Javis Core, không vào prompt của lượt chat thường.

## 5. Hiệu năng

- Không lượt gọi model nào được thêm. Vòng chỉ có mã.
- `tick` chạy 10 phút một lần ở luồng phụ; luật chỉ đọc bộ đếm có sẵn, không quét lịch sử.
- Một lần dời ghi một dòng SQLite (cùng tệp với sổ điểm).
- Bài học về cách học được đọc một lần mỗi mẻ học, ở luồng phụ.
- Lượt chat không đi qua vòng này.

## 6. Chưa làm

1. **Tác nhân `core`: Javis Core suy xét bằng model mạnh.** Cắm vào nhịp sẵn có của Javis Core như một loại lý do mới
   (`agent_pulse_host.register_reason_handler`), dùng chung hạn mức 6 lượt mỗi ngày với ưu tiên thấp nhất. Đọc báo cáo
   gọn từ sổ điểm, các núm và nhật ký học; được đề nghị vài thay đổi trong danh sách núm đã đăng ký và viết bài học về
   cách học bằng lời; mỗi đề nghị dẫn bằng chứng. Cần vài ngày dữ liệu thật từ mục 1 đến 4 mới đáng một lượt gọi model.
2. **Tự hoàn tác theo số đo.** Vòng tự soát của chatbot hoàn tác cả lần soát khi tỉ lệ sai tệ đi. Núm ở đây chưa có số
   đo chung kiểu đó; hiện dựa vào bước nhỏ, nhịp một ngày và việc chủ hoàn lại.
3. **Thêm núm:** mức suy nghĩ của từng việc nền, ghi nhớ nào luôn nạp, bật lại học skill khi thấy quy trình lặp lại.
   Núm "công cụ ghim sẵn theo brain" ĐÃ LÀM ở bước kế, xem `2026-11-ghim-cong-cu-theo-brain-spec.md`.
4. **Thêm tín hiệu:** cảm xúc chủ thả vào kết quả việc nền, tin nhắn kế tiếp của chủ sau một kết quả, gợi ý câu tiếp
   theo có được dùng không.
5. **Chuyển hai vòng sẵn có về chung vòng này:** mức thông báo (`notify_policy`) và ngưỡng lên tiếng của chatbot
   (`chatbot_reply_policy_review`).

## 7. Chưa kiểm trên máy thật

- Model chat có gọi `javis_tune op=teach` khi chủ dặn một điều về cách học không.
- Tỉ lệ mẻ học rỗng thực tế là bao nhiêu, tức núm `learn.min_turns` có dời hay không.
