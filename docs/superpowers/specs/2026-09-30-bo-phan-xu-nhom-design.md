# Bộ phán xử hội thoại nhóm (0.65.0)

Ngày 2026-09-30. Trạng thái: đặc tả để làm MỘT lần, một PR (#502), nhiều commit theo mốc.

## 1. Vấn đề

Bot chuyên trách đứng trong nhóm chat (Zalo cá nhân, Telegram) phải tự quyết ba việc: có ai đang
nói với mình không, có nên chen vào không, và nói thì nói gì. Bản 0.64.82 giải bằng một chuỗi luật
cứng viết riêng cho một trường hợp:

- `zalo_personal_channel.nhan_dien_goi` chỉ bắt "@tên". Gọi tên trơn ("javis vũ ơi") không được coi
  là gọi bot.
- `chatbot_tu_dong.nhin_nhu_cau_hoi` là cửa từ khoá (dấu hỏi, "sao", "giúp"...). Tin không khớp bị
  loại, và cố ý KHÔNG ghi nhật ký, nên lỗi không để lại dấu vết.
- Chỉ nhìn đúng MỘT tin. Người ta nhắn tiếp "vậy còn cái kia?" ngay sau khi bot trả lời thì bot coi
  là tin lạ.

Chủ dự án (2026-09-30): muốn một cơ chế theo ngữ cảnh, không bó vào một bot, để nhiều bot khác nhau
dần dần tự học cách trả lời trong nhóm; học TRỰC TIẾP chứ không theo tuần; bỏ bước duyệt vì bot dùng
nick riêng nên nói nhầm là rẻ.

Và điều quan trọng nhất, chủ nói rõ sau bản đặc tả đầu: chủ chạy NHIỀU bot với lĩnh vực và nhóm không
liên quan nhau (ví dụ Javis Vũ hỗ trợ về Javis, Nhi Mai và Ngọc Thu mỗi người một ngành khác). Cách
trả lời của mỗi bot phải đến từ Agent của chính nó. Bản thiết kế không được mượn giọng, ca hay ví dụ
của bot này cho bot kia, và không được thiên về trường hợp của Javis Vũ.

## 2. Mục tiêu và không mục tiêu

Mục tiêu:
1. Nhận ra bị gọi tên trơn, hiểu tin nối tiếp sau lượt bot vừa nói.
2. Mọi quyết định, kể cả im, đều có dấu vết đọc được.
3. Một bộ máy dùng chung cho mọi bot và mọi kênh; cái riêng của từng bot nằm trong dữ liệu
   (hồ sơ, thẻ luật, ca đã học), không nằm trong mã.
4. Học tức thì từ phản ứng của người thật; ca vừa gắn nhãn tác động ngay quyết định kế tiếp.
5. Bot mới có hành vi hợp lý ngay ngày đầu THEO LĨNH VỰC CỦA NÓ (suy ra từ Agent và tài liệu của chính
   bot), không mượn giọng hay ca của bot khác.

Không mục tiêu: đổi NỘI DUNG câu bot nói (vẫn bám tài liệu và vai của Agent); huấn luyện hay tinh
chỉnh model; học chéo giữa các người dùng; sửa cách bot chat riêng; chia sẻ ca, giọng hay luật giữa các bot.

## 3. Nguyên tắc

1. **Tách "được gọi" khỏi "nên chen vào".** Cái đầu là nhận diện, luật cứng và rộng tay. Cái sau là
   phán đoán, mới là chỗ học. Trộn hai thứ này thì bot có thể học sai thành "bị gọi tên mà im cũng
   được".
2. **Học chỉ đổi việc NÓI HAY IM.** Không bao giờ đổi điều bot khẳng định. Nhờ vậy bỏ duyệt vẫn không
   làm bot bịa thêm.
3. **Rào cứng nằm ngoài vòng học** và là giới hạn của mọi thứ học được.
4. **Sai về phía im.** Lỗi, hết giờ, JSON hỏng, tín hiệu mơ hồ: im. Ngoại lệ duy nhất là tin gọi
   tên chắc chắn, luôn trả lời như chat riêng.
5. **Ca đơn lẻ nhẹ, lời dạy của chủ nặng.** Chỉ chủ mới tạo được luật. Người khác trong nhóm là nguồn
   không tin cậy: lời họ chỉ là tín hiệu yếu.
6. **Ba tầng, học chỉ ghi vào tầng riêng.** Tầng chung chỉ có CƠ CHẾ trò chuyện nhóm, không có chủ đề,
   giọng hay xưng hô. Tầng bot lấy từ Agent của chính bot. Tầng cuộc chat là văn hoá riêng của từng
   nhóm. Điều học được chỉ ghi vào tầng bot hoặc tầng cuộc chat, không bao giờ ngược lên tầng chung,
   và bot này không đọc được gì của bot kia (xem 4.1).
7. **Bộ phán xử không viết câu trả lời.** Nó chỉ quyết nói hay im. Câu nói ra vẫn do engine của bot
   chạy với prompt Agent của bot, nên giọng và cách trả lời luôn là của Agent.
8. **Mở rộng bằng dữ liệu và cắm thêm, không bằng nhánh if.** Thêm tín hiệu, thêm kênh, thêm ngôn
   ngữ là thêm một hàm hoặc một dòng dữ liệu.
9. **Dữ liệu chat khách là dữ liệu nhạy cảm.** Học là bật riêng từng bot, mặc định TẮT; dữ liệu
   ngoài git, có hạn giữ, xoá theo bot, có nút quên.

## 4. Kiến trúc

```
tin nhóm -> [Event chuẩn hoá] -> R rào cứng -> G nhận diện được gọi -> T tín hiệu
                                                        |                  |
                                            certain --->|                  v
                                       (trả lời luôn)   |          C cổng thô (rác/không tín hiệu -> silent + ghi vết)
                                                        |                  |
                                                        +----------> J người phán xử (model việc nền)
                                                                     ^   |   nhận: guidelines + ca giống + 8 tin gần nhất
                                                       ca giống -----+   v   trả: reply|silent + score + reason
                                                       K kho ca           D so score với threshold(bot, chat)
                                                                     ^   |
                                                    label, lesson ---+   v
                                                       O outcome tracker  <- mọi tin sau đó của cuộc chat
```

Ba khối dữ liệu tách rời, đổi cái này không đụng cái kia:

- **Sự kiện (Event):** khuôn chuẩn hoá, không phụ thuộc kênh. Bộ chuyển đổi của Zalo và Telegram
  tự dựng.
- **Hồ sơ (Profile):** riêng từng bot. Tên gọi, thẻ luật, độ hăng hái, người được dạy bot.
- **Kho (Store):** ca đã học, nhật ký quyết định, ngưỡng theo cuộc chat.

### 4.1 Ba tầng: cái gì đến từ đâu

| Tầng | Chứa gì | Từ đâu | Ai đổi được |
|---|---|---|---|
| Chung | cơ chế: nhận diện gọi tên, tin nối tiếp, cách chấm điểm, ngưỡng gốc, từ khoá phản ứng, mẫu cơ chế | mã và dữ liệu trong repo, KHÔNG có chủ đề nào | chỉ bản cập nhật |
| Bot | phạm vi đảm nhiệm và không đảm nhiệm, giọng, xưng hô, ngôn ngữ, khi nào nên lên tiếng | biên dịch từ file Agent và mục lục tài liệu brain của CHÍNH bot (5.10) | chủ sửa tay; tự soạn lại khi Agent đổi |
| Cuộc chat | ngưỡng lệch, ca đã học, bài học | phản ứng trong chính nhóm đó | học tự động; chủ xoá được |

Ví dụ với ba bot: Javis Vũ nhận câu hỏi về Javis, Nhi Mai và Ngọc Thu mỗi người nhận đúng ngành của
mình. Cả ba dùng CÙNG một bộ máy, nhưng hồ sơ vai, ca khởi tạo, ca đã học, ngưỡng và bài học đều tách
riêng theo `bot_id` (và theo cuộc chat). Bộ phán xử của Nhi Mai không bao giờ đọc thấy ca, ví dụ hay
giọng của Javis Vũ. Ai học gì ở nhóm nào thì chỉ ở nhóm đó.

Mã mới nằm trong `server/chatbot_reply_policy.py` (bộ máy, thuần và test được) và
`server/chatbot_reply_policy_store.py` (SQLite). Không nhét vào `chatbot_runtime.py` thêm nữa.

### 4.2 Sự kiện chuẩn hoá

```
Event: channel, bot_id, chat_id, chat_type, msg_id, ts, text, sender_id, sender_name,
       sender_role ("owner" | "known" | "new"), mentioned (bool), reply_to_bot (bool),
       window (tối đa 8 tin gần nhất: ts, sender_id, name, is_bot, text),
       bot_last_spoke_ts (ts hoặc None), owner_typing (bool)
```

`window` lấy từ Hộp thư (`conversations.tin_nhan`) của đúng cuộc chat; chưa có thì rỗng, bộ máy
vẫn chạy. Nội dung mỗi tin cắt 400 ký tự, gỡ marker nội bộ (`[IM_LANG]`, `JAVIS_`).

### 4.3 Quy ước đặt tên

Định danh mới (tên module, hàm, biến, trường dữ liệu, cột SQL, đường API, giá trị liệt kê, tên file dữ
liệu) viết bằng TIẾNG ANH, theo yêu cầu của chủ 2026-09-30. Chuỗi hiển thị cho người dùng, chú thích và
tài liệu vẫn là tiếng Việt có dấu. Tên cũ mà PR này chỉ gọi tới (như `chatbot_tu_dong`, `_ly_do_im`,
`zalo_personal_channel.nhan_dien_goi`) giữ nguyên: đổi tên hàng loạt kéo theo dữ liệu đang lưu, đường
API mà giao diện đang gọi và hàng trăm test, nên là một PR riêng, không lẫn vào đây.

| Khái niệm | Định danh |
|---|---|
| người phán xử, hồ sơ vai, kho ca | `judge`, `role_profile`, `cases` |
| ngưỡng, độ lệch ngưỡng | `threshold`, `offset` |
| mức được gọi: chắc chắn, có thể, không | `certain`, `possible`, `none` |
| quyết định: nói, im | `reply`, `silent` |
| nhãn: đúng, im nhầm, chen nhầm, lời dạy | `correct`, `missed`, `intruded`, `taught` |
| chế độ: tắt, chạy thử, bật | `off`, `shadow`, `on` |
| độ hăng hái: ít, vừa, nhiều | `low`, `medium`, `high` |
| người nói: chủ, đã biết, mới | `owner`, `known`, `new` |
| nguồn ca: tự động, chủ, khởi tạo | `auto`, `owner`, `bootstrap` |
| người được dạy bot, tên gọi, bài học | `trainer_ids`, `aliases`, `lessons` |

## 5. Các tầng

### 5.1 R: rào cứng (giữ nguyên, không học được)

> Phát hiện khi làm: khoảng nghỉ 20 giây giữa hai lần bot tự nói chặn luôn tin NỐI TIẾP của người bot vừa trả lời,
> làm hỏng đúng tính năng "hiểu tin nối tiếp". Nên tin nối tiếp được nới khoảng nghỉ và trần theo người; trần theo
> nhóm mỗi giờ vẫn áp (`chatbot_tu_dong.duoc_tra_loi(..., follow_up=True)`).

Nhóm chưa được cho phép thì im (`_nhom_duoc_phep`); người chưa chọn thì im; cuộc chat đã Tiếp
quản; chủ vừa gõ tay (`chu_vua_nhan_tay`); tin cũ quá `TUOI_TOI_DA`; tin do chính nick gửi;
hạn mức số lần tự nói (`chatbot_tu_dong.duoc_tra_loi`); không làm hành động ra ngoài do bộ phán
xử. Rào chạy TRƯỚC mọi thứ tốn model và vẫn ở chỗ hiện tại trong `chatbot_runtime`.

### 5.2 G: nhận diện được gọi

Trả `address_level` ∈ `certain` | `possible` | `none` cùng bằng chứng. Chuẩn hoá: bỏ dấu, chữ thường, gộp khoảng
trắng (dùng `chatbot_grounding._bo_dau`), khớp theo ranh giới từ.

| Mức | Điều kiện |
|---|---|
| `certain` | `@tên`; `mentions` chứa id nick; reply vào tin của bot; tên gọi đứng ĐẦU câu (sau các chữ mở như "ê", "này", "alo", "hi", "chào"); tên gọi đi liền tiểu từ gọi ("ơi", "à", "ạ", "này", "nè", "nha", "ê") |
| `possible` | tên gọi nằm giữa hoặc cuối câu không kèm tiểu từ ("hỏi javis vũ xem"); tin nối tiếp (5.3) |
| `none` | còn lại |

Tên gọi (`aliases`) gồm: nhãn kết nối, tên hiển thị học được của nick, và danh sách tên do chủ tự
thêm. KHÔNG tự lấy tên Agent hay tên bot ("@Lan" trong nhóm thường là một thành viên tên Lan). Tên
tự suy phải dài từ 4 ký tự trở lên sau chuẩn hoá; tên do chủ thêm không bị luật này.

Ví dụ phải đúng (chạy cả bản không dấu): "javis vũ ơi" certain; "Javis Vũ giúp anh cái này" certain;
"alo javis vu" certain; "hỏi javis vũ xem" possible; "mai họp mấy giờ" none; "@Lan xem giúp" none.

`certain` thì trả lời luôn như chat riêng, KHÔNG qua người phán xử, KHÔNG cần tài liệu, không đếm
hạn mức tự nói.

Nhận diện gọi tên trơn là SỬA LỖI nên áp dụng cho MỌI bot, kể cả khi bộ phán xử `mode = off`, nhưng chỉ dùng tên
tự suy (nhãn kết nối, tên hiển thị của nick) và tên chủ khai. Cờ `mentioned` được đặt ở lớp vận chuyển (Zalo cá nhân)
và ở từng điểm dùng (chốt chặn, `_answer`), vì `_gan_tai_khoan` bọc `meta` thành bản sao riêng cho từng callback nên
đánh dấu ở một chỗ không truyền sang chỗ kia.

### 5.3 T: tín hiệu (sổ đăng ký, cắm thêm được)

Mỗi tín hiệu là một hàm thuần `(Event, BotProfile) -> {value, evidence}` đăng ký bằng decorator.
Thêm tín hiệu = thêm một hàm và một test; không đụng khung.

- `question_score`: điểm 0..1 từ dấu hỏi, từ khoá (bảng dữ liệu, thay `_HOI`), cấu trúc "có ... không".
  Từ nay là TÍN HIỆU, không còn là cổng chặn.
- `follow_up`: bot vừa nói trong nhóm ≤ 180 giây và tin này của đúng người bot vừa trả lời, hoặc
  reply vào chuỗi đó.
- `doc_match`: có phần tài liệu khớp (`chatbot_grounding.thu_thap`), kèm điểm. Chỉ tính cho
  ứng viên, không quét đĩa cho mọi tin.
- `sender_role`: chủ / đã biết (đã có hội thoại với bot) / mới.
- `chat_pace`: mật độ tin trong 2 phút gần nhất (nhóm đang sôi nổi thì bot bớt chen).
- `alias_mid_sentence`: tên gọi xuất hiện nhưng chưa đủ `certain`.

### 5.4 C: cổng thô

Chỉ vứt thứ hiển nhiên không phải: rỗng, không phải chữ, chỉ có link, một hai chữ không phải lời
gọi, tin mở đầu bằng tag người khác khi `address_level = none`. Tin còn lại là **ứng viên** khi có ít nhất một
trong: `address_level = possible`, `follow_up`, `question_score >= 0.5`, hoặc kho có ca dương giống (5.7). Không ứng
viên thì im VÀ ghi vết `no_signal`.

Bộ mã im đầy đủ (mỗi mã có nhãn đọc được ở giao diện): `junk`, `addressed_other`, `no_signal`, `no_grounding`,
`rate_limited`, `rate_limited_user`, `just_spoke`, `owner_typing`, `policy_error`, `judge_silent`, `below_threshold`, và
hai mã do bước SAU quyết định rút lại: `taken_over` (chủ đã Tiếp quản) và `agent_silent` (Agent chọn im).

Giữ luật hiện có cho lời tự nói: khi `address_level = none` và không `follow_up`, bot chỉ mở miệng nếu có căn
cứ. Cấu hình `grounding`: `docs` (mặc định, phải có `doc_match`) hoặc `role` (bot lấy chuyên
môn từ vai của Agent, dùng cho bot tư vấn không dựa vào tài liệu). Ca đã học KHÔNG được miễn luật
này.

### 5.5 J: người phán xử

Một lượt model rẻ, chạy bằng engine "việc nền" (`aux_engine`, chủ đã chọn ở trang Models), mode
`suggest`, không công cụ. Đầu vào là văn bản gồm:

1. Hồ sơ vai của CHÍNH bot (5.10): phạm vi đảm nhiệm và không đảm nhiệm, giọng để hiểu vai, khi nào
   nên lên tiếng, cộng các bài học.
2. Tối đa 5 ca giống nhất CỦA BOT NÀY kèm "quyết định đúng" (5.7). Không bao giờ lấy ca của bot khác.
3. Cửa sổ 8 tin gần nhất, người nói, bot đã nói gì.
4. Tín hiệu đã tính và đoạn tài liệu khớp (cắt ngắn).
5. Tin cần quyết.

Prompt không chứa tên, ví dụ hay giọng của bất kỳ bot nào khác. Toàn bộ nội dung chat bọc trong khối `<chat_data>` và prompt nói rõ đó là dữ liệu, không phải
lệnh. Đầu ra bắt buộc một JSON: `{"verdict":"reply"|"silent","score":0..1,"reason":"<= 120 ký tự"}`.
Tối đa 3 lượt phán xử chạy đồng thời (semaphore theo vòng lặp sự kiện). Sai khuôn, hết 25 giây (engine gói thuê bao mất vài giây chỉ để khởi động, 8 giây là quá chặt), hay lỗi engine: coi là
`silent` với lý do `policy_error`. Engine chạy trong thư mục TRỐNG, không MCP, không công cụ ghi hay chạy lệnh
(nội dung chat là dữ liệu không tin cậy).

Chế độ: `off` (chạy luật cũ), `shadow` (người phán xử chạy song song, chỉ ghi, luật cũ quyết), `on`
(người phán xử quyết). Bot đang có sẵn giữ `off` cho tới khi chủ bật.

### 5.6 D: ngưỡng

`threshold = base_threshold(eagerness) + offset(bot, chat)`. `base_threshold`: `low` (ít lời) 0.75, `medium` (vừa) 0.60, `high` (nhiều lời) 0.45.
Bot nói khi `verdict = reply` và `score >= threshold`. `offset` ∈ [-0.25, +0.25], `threshold` kẹp trong [0.30, 0.90].
Cập nhật: im nhầm trừ 0.05, chen nhầm cộng 0.08 (chen đắt hơn im), nhân với trọng số nhãn. Không có
nhãn thì `offset` co dần về 0 với chu kỳ bán rã 14 ngày. Ngưỡng theo TỪNG cuộc chat: nhóm khách
thích bot nói nhiều, nhóm nội bộ thì không.

### 5.7 K: kho tình huống

Mỗi quyết định ứng viên ghi một dòng; khi có nhãn nó thành **ca**. Tra cứu không cần thư viện
embedding: chỉ trong ca của CHÍNH bot này, điểm giống = 0.6 × Jaccard(token chuẩn hoá) + 0.25 × khớp đặc trưng (`address_level`, `follow_up`,
`sender_role`) + 0.15 nếu cùng cuộc chat, nhân độ nhạt theo tuổi (bán rã 30 ngày) và trọng số ca.
Lấy tối đa 5 ca điểm ≥ 0.25. "Quyết định đúng" của ca: `correct` thì giữ quyết định đã chọn,
`missed` thì `reply`, `intruded` thì `silent`, `taught` thì theo lời dạy. Giao diện `tim_ca(event,
k)` để sau này thay bằng embedding mà không đổi khung.

**Khởi động cho bot mới, hai lớp và không lớp nào mang chủ đề của bot khác:**

1. *Mẫu cơ chế* (chung): `system/reply_policy/mechanics_vi.json`, khoảng 20 ca TRỪU TƯỢNG chỉ mô tả cơ
   chế trò chuyện nhóm, viết bằng chỗ giữ `{bot_name}` và `{topic}` thay vì tên hay ngành cụ thể. Ví dụ:
   "{ten_bot} ơi" thì trả lời; hai người đang trao đổi với nhau thì im; tin có tag người khác thì im;
   "vậy còn cái kia?" ngay sau khi bot trả lời thì trả lời; một lời cảm ơn không nhắm vào bot thì im;
   câu hỏi ngoài {chu_de} thì im. Khi dùng, `{bot_name}` thay bằng tên gọi của chính bot và `{topic}`
   bằng phạm vi trong hồ sơ vai của bot. Test cấm tên ngành hay tên sản phẩm trong file này.
2. *Ca khởi tạo theo vai* (riêng từng bot): lúc bật lần đầu và mỗi khi hồ sơ vai đổi, một lượt model
   đọc Agent và mục lục tài liệu của chính bot rồi viết khoảng 12 tin mẫu ĐÚNG LĨNH VỰC ĐÓ: 5 tin nên
   nói, 5 tin nên im, 2 tin ranh giới, kèm lý do. Lưu là ca `source = bootstrap`, trọng số thấp. Chủ xem
   và xoá được. Mỗi ca thật cùng loại làm giảm trọng số ca khởi tạo giống nó, nên khi bot đã học đủ từ
   nhóm thật thì các ca giả nhạt đi và biến mất.

Nhờ vậy bot thứ hai, thứ ba khởi động khôn sẵn theo ngành CỦA NÓ mà không chép hành vi từ bot nào.

Trần: 500 ca mỗi bot, 200 mỗi cuộc chat; vượt thì bỏ ca có trọng số × độ mới thấp nhất, ca đã gộp
vào thẻ luật thì xoá khỏi kho.

### 5.8 O: theo dõi hậu quả và gắn nhãn

Mỗi quyết định ứng viên mở một cửa theo dõi 10 phút hoặc 8 tin, tuỳ cái nào tới trước. Mỗi tin
mới của cuộc chat chạy qua `assign_label(watch, new_message)`, hàm thuần. Chỉ tín hiệu MẠNH mới gắn nhãn;
**không phản ứng thì không nhãn** (bị phớt lờ là chuyện thường, và im thì vốn không có phản ứng để đo,
dùng nó làm nhãn sẽ dạy bot nói nhiều hơn).

| Quyết định | Tín hiệu | Nhãn | Trọng số |
|---|---|---|---|
| silent | cùng người hỏi lại ("sao không trả lời", "bot ơi", "ai biết không") hoặc gửi lại gần giống ≥ 0.6 | `missed` | 1.0 |
| silent | có người gọi tên chắc chắn ngay sau, cùng chủ đề | `missed` | 0.8 |
| silent | chủ tự trả lời thực chất cho đúng người hỏi | `missed` | 0.5 (chủ có thể chỉ tiện tay) |
| reply (không được gọi) | chủ nói "đừng chen vào", "ai hỏi bot", "im đi" | `intruded` | 1.0 |
| reply (không được gọi) | người khác nói câu tương tự | `intruded` | 0.5 |
| reply (không được gọi) | chủ bấm Tiếp quản cuộc chat trong 10 phút | `intruded` | 0.7 |
| reply | cảm ơn, "ok", "được rồi" | `correct` | 0.6 |
| reply | hỏi tiếp đúng mạch (`follow_up`, reply vào bot) | `correct` | 0.8 |
| bất kỳ | chủ bấm 👍 hoặc 👎 trong Nhật ký | theo nút | 1.5 |

Bảng từ khoá tín hiệu nằm ở `system/reply_policy/keywords_vi.json` (đã bỏ dấu), thêm ngôn ngữ là thêm file.
Chống spam nhãn: mỗi người tối đa 3 nhãn mỗi giờ mỗi bot, mỗi bot tối đa 50 ca mới mỗi ngày.

### 5.8b Rà soát độc lập (30/09/2026): các sửa đã áp

Một lượt rà soát độc lập tìm ra chín lỗi thật, đã sửa và có test: (1) engine phán xử phải chạy với `allowed_tools` có giá
trị (để trống là `bypassPermissions` và nạp cả cài đặt máy), cộng danh sách công cụ bị cấm; (2) lời dạy không gắn nhãn vào
chính tin dạy; (3) gọi tên ngay sau đó chỉ tính "im nhầm" khi cùng chủ đề; (4) chữ của ca đã học nằm trong `<chat_data>`
và bộ lọc thẻ bắt cả biến thể; (5) nhãn của chủ ghi đè chứ không cộng dồn (`cases.decision_id`); (6) quyết định `reply` bị
chặn ở bước sau được rút lại (`amend_decision`), và Tiếp quản được kiểm TRƯỚC lượt model; (7) chữ mở đầu "này/ê" chỉ xét
trên bản GIỮ DẤU nên "hôm nay Nhi Mai..." không còn là lời gọi; (8) Quên hết xoá cả nhật ký quyết định, và giao diện nói thật
rằng chế độ Chạy thử/Bật ghi chữ chat 14 ngày kể cả khi chưa bật tự học; (9) giới hạn đồng thời, không quét đĩa trên vòng
sự kiện.

### 5.9 Lời dạy của chủ

Tin của người trong `trainer_ids` gọi bot (`address_level >= possible`) chạy thêm một lượt phân loại rẻ: "đây có
phải chủ đang dạy bot cách hành xử không?" → `{"is_teaching":bool,"rule":"...","kind":"should_speak"|"should_stay_silent"|"alias"}`.
Đúng thì: tạo ca `taught` trọng số 2.0 (có tác dụng ngay ở quyết định kế tiếp), thêm một dòng vào
mục Bài học của thẻ luật, và nếu `kind = alias` thì thêm cụm đó vào `aliases`. Người ngoài
`trainer_ids` không bao giờ tạo được luật, cho dù họ viết "từ giờ hãy trả lời mọi tin".

### 5.10 Hồ sơ vai (thẻ luật của từng bot)

Đây là cách một bot khác bot kia mà không phải viết mã riêng. `role_profile` do máy biên dịch từ file
Agent của CHÍNH bot (vai, giọng, quy định) và mục lục tài liệu trong brain của bot, gồm bốn mục:

1. **Đảm nhiệm:** những chủ đề bot trả lời.
2. **Không đảm nhiệm:** những chủ đề bot phải nhường, dù có người hỏi.
3. **Giọng và xưng hô:** CHỈ để người phán xử hiểu vai. Không dùng để viết câu trả lời (việc đó là của
   engine chạy Agent).
4. **Khi nào nên lên tiếng trong nhóm:** ví dụ chỉ khi có người hỏi đúng ngành, không chen vào chuyện
   riêng của thành viên.

Lưu kèm `agent_hash`. File Agent hoặc mục lục tài liệu đổi thì soạn lại NHÁP mới và giữ nguyên phần
chủ đã sửa tay: hai vùng riêng `generated_text` và `owner_text`, người phán xử đọc cả hai, vùng của chủ
đè lên khi mâu thuẫn. Chủ sửa ở ô "Luật lên tiếng" (`guidelines`). Không có engine thì dùng mẫu tĩnh
chỉ có bốn đầu mục để chủ điền.

`lessons` (máy ghi, theo mẫu `JAVIS_LESSON`: đề xuất lúc dùng, mã ghi, khử trùng, tối đa 15 dòng, dòng
cũ nhất rơi ra) là phần thứ năm, riêng từng bot. KHÔNG có vòng nền viết lại hàng loạt (quyết định
của chủ 2026-08-16).

## 6. Dữ liệu

SQLite `chatbot_reply_policy.sqlite3` trong thư mục state, thêm vào `.gitignore`, WAL.

```
decisions(id, bot_id, chat_id, msg_id, ts, text, sender, sender_id, sender_role, address_level, signals_json,
          candidate, verdict, score, threshold, reason, mode, silence_code, label, label_weight, label_ts)
cases(id, bot_id, chat_id, ts, text, tokens, features_json, correct_verdict, reason,
      source, weight, origin_case_id)               -- source: auto|owner|bootstrap
watches(decision_id, expires_ts, messages_left)
role_profiles(bot_id, generated_text, agent_hash, updated_ts)
threshold_offsets(bot_id, chat_id, offset, updated_ts)
lessons(id, bot_id, text, ts)                      -- bài học, tối đa 15 dòng mỗi bot
```

Nút Quên hết xoá cả `decisions` (chữ chat của khách), không chỉ phần đã học. Giữ: dòng chưa gắn nhãn 14 ngày; ca đã gắn nhãn 180 ngày (có nhạt dần); nội dung cắt 400 ký tự.
Xoá bot thì xoá sạch dòng của bot. Vòng đệm im: mọi tin bị im đều là một dòng `decisions` với
`silence_code` (`no_signal`, `no_grounding`, `policy_error`, `rate_limited`, `just_spoke`...).

## 7. Cấu hình, API, giao diện

Trường mới trong bản ghi bot (đi qua `chatbot_store`, có lọc và giá trị mặc định fail-closed):

```
reply_policy: { aliases: [str], trainer_ids: [str], guidelines: str (di sản, xem 7.2) }
```

Chỉ có nghĩa khi `reply_when = auto`. Bản 0.65.0 còn `mode`, `eagerness`, `grounding`, `learning_enabled`; xem 7.2 vì sao
bản 0.65.1 bỏ chúng.

### 7.2 Tự vận hành, không ô cài đặt (0.65.1)

Chủ dự án nhận xét ngày 30/09/2026: cài đặt quá nhiều, muốn lược bớt và đẩy phần suy luận về AI để tự cải thiện. Nguyên tắc
áp cho mọi thứ sau này của bộ phán xử: **thứ gì máy suy ra được từ dữ liệu sẵn có thì không thành ô cài đặt**. Bảy ô của
0.65.0 được xử lý như sau:

| Ô cũ | Nay |
|---|---|
| Chế độ Tắt / Chạy thử / Bật | Bỏ. Chọn "Tự đánh giá" là bật; muốn tắt thì chọn cách lên tiếng khác. Chạy thử thành công tắc của người vận hành: biến môi trường `JAVIS_REPLY_POLICY_SHADOW=1`. |
| Độ hăng hái | Bỏ. Cố định mức vừa làm ngưỡng gốc; ngưỡng riêng từng nhóm tự nhích theo Đúng/Sai và phản ứng của nhóm (đã có từ 0.65.0), co dần về gốc theo chu kỳ 14 ngày. |
| Căn cứ (tài liệu / vai) | Bỏ. Tự chọn: brain của bot có mảnh tài liệu nào thì bắt buộc có tài liệu khớp mới được tự nói, không có thì dựa vào vai. Đo ở thread nền cùng lần soạn hồ sơ vai (`chatbot_grounding.chi_muc`); chưa đo thì giữ luật chặt (tài liệu). |
| Luật lên tiếng + nút Soạn từ vai trò | Bỏ. Hồ sơ vai vốn đã tự soạn và tự soạn lại khi Agent hay tài liệu đổi. Chữ chủ đã viết ở 0.65.0 được gộp MỘT LẦN vào bảng `lessons` (từng dòng) rồi xoá khỏi cấu hình; ghi hỏng thì giữ chữ cũ nên không mất luật nào. Route `draft-guidelines` bị gỡ. |
| Tên gọi thêm | Bỏ khỏi form. Vẫn lưu trong `aliases`; thêm bằng cách dạy trong nhóm ("gọi em là Thu nhé", kind `alias` của mục 5.9). |
| Bật tự học | Bỏ. Luôn bật khi ở chế độ Tự đánh giá. Đổi lại lời nói thật về dữ liệu ở dòng giải thích của form (400 ký tự, 14 ngày, ca 180 ngày) và nút Quên hết. |
| Người được dạy bot | Bỏ ô nhập ID. Còn nút **Là chủ** ngay ở tin của mình trong menu Bộ phán xử: chọn trên dữ liệu thật, không phải gõ ID Zalo. |

Hệ quả: `normalize_config` đọc `reply_policy` nhưng BỎ QUA các khoá đã nghỉ hưu, kẻo bot đã lưu form ở 0.65.0 (khi form
luôn ghi `mode: "off"`) kẹt ở trạng thái tắt mà không còn nút nào sửa. `merge_config` chỉ ghi ba khoá còn ý nghĩa và dọn
các khoá cũ khỏi bản ghi. Form bot không còn gửi `reply_policy`, nên lưu bot không thể ghi đè `aliases` hay `trainer_ids`.

Đánh đổi đã cân: mất chế độ Chạy thử ở giao diện. Bù lại mọi quyết định (kể cả im) đều hiện ở menu Bộ phán xử kèm Đúng/Sai,
bộ phán xử vẫn sai về phía im, và người vận hành còn công tắc môi trường. Nếu sau này thấy thiếu chế độ thử, thêm lại thành
một nút BẬT TẠM (tự tắt sau N ngày) chứ không thành cài đặt vĩnh viễn.

Đường mới, đặt SAU route cuối của `main.py` để `route_table.json` chỉ thêm dòng cuối:

- `GET /chatbots/{id}/reply-policy`: cấu hình, số ca, lệch ngưỡng từng cuộc chat, 100 quyết định gần nhất
  (kể cả im), danh sách ca và bài học.
- `POST /chatbots/{id}/reply-policy/label`: chủ gắn 👍/👎 cho một quyết định.
- `POST /chatbots/{id}/reply-policy/cases/{case_id}/delete`: xoá một ca.
- `POST /chatbots/{id}/reply-policy/forget`: quên hết, hoặc riêng một cuộc chat.
- (bản 0.65.0 có thêm `POST .../draft-guidelines` soạn nháp thẻ luật; gỡ ở 0.65.1, hồ sơ vai tự soạn ở nền.)

Giao diện (một cột, đúng phong cách form hiện tại, đủ vi và en):

- Trong phần "Bot trả lời ai", khi chọn "Tự đánh giá": chỉ một dòng giải thích (bot tự cân nhắc, tự học,
  và nói thật về chữ chat được lưu). Không ô nhập, không nút chọn (0.65.1; bản 0.65.0 có bảy ô, xem 7.2).
- Menu "..." của thẻ bot thêm **Bộ phán xử**: bảng quyết định gần đây có cả tin bị im, mỗi dòng có
  Đúng/Sai và nút Là chủ, danh sách bài học, hồ sơ vai, nút Quên hết.

### 7.1 Lịch sử hội thoại của bot (M9)

Chủ dự án (2026-09-30): "các đoạn hội thoại đang nằm ở Trò Chuyện, anh muốn chuyển thành các đoạn phản hồi lại nằm
trong lịch sử của agent được nối với chatbot". Phiên của bot mang kênh `bot:<tên>` (xem `_tg_answer`) nên trước bản này
lọt vào danh sách Trò chuyện, vì chỉ các kênh cộng sự (`agent:`, `workflow:`, `coding:`) bị loại ở đó.

- `sessions.KENH_BOT = ("bot:",)`: danh sách mặc định (Trò chuyện) loại thêm các kênh này. Vòng tự học (`channel="*"`)
  vẫn thấy mọi phiên.
- Lịch sử của một Agent (`channel="agent:<slug>"`) gộp thêm kênh `bot:` của MỌI bot dùng Agent đó (`also_channels`, do
  `main._kenh_bot_cua_agent` tính từ kho bot theo slug Agent và brain của bot). Ô tìm ở cột lịch sử cũng vậy.
- Giao diện: trong lịch sử Agent, phiên của bot mang nhãn **Bot** để phân biệt với cuộc chủ tự chat với Agent.
- Không đổi kênh của phiên hiện có, nên không cần di trú dữ liệu.

## 8. Chỗ gắn vào mã hiện có

- `zalo_personal_channel.nhan_dien_goi`: giữ nguyên chữ ký `(tag, rep)` cho chỗ gọi cũ, bên trong dùng
  `chatbot_reply_policy.detect_address`; thêm bản trả mức `address_level`.
- Lớp vận chuyển gọi `PolicyHooks.prepare/replied` (`chatbot_runtime.py`); Tiếp quản báo qua
  `conversations.dat_che_do` -> `note_takeover`.
- `channels/zalo_personal.py::xu_ly`: dựng Event, đưa MỌI tin nhóm (kể cả tin sẽ bị loại) qua
  `watches` để gắn nhãn cho quyết định trước; meta thêm `address_level`, `follow_up`.
- `chatbot_runtime._answer`: khối `auto` gọi `chatbot_reply_policy.decide(...)` khi `mode != off`;
  `shadow` chạy song song rồi bỏ kết quả. `_ly_do_im`, `_make_precheck_fn` không đổi.
- Telegram: `TelegramBot._build_meta` đã có `mentioned`, `reply_to_bot`; nhận diện tên gọi chạy trong chốt chặn và
  `_answer` (chỉ tên chủ khai). Chế độ Bật quyết định trong nhóm, nhưng Telegram không có cửa sổ tin nối tiếp và không
  có Chạy thử (cần lớp vận chuyển đọc được toàn bộ tin nhóm, hiện chỉ Zalo cá nhân có).
- `chatbot_store`: `_PATCHABLE`, `_public`, kiểm giá trị. `chatbot_log`: tin bị im KHÔNG vào JSONL
  của bot (tránh nhiễu), vào kho mới và hiện ở Nhật ký qua bộ lọc "Cả tin bot im".

## 9. Kiểm thử (mọi thứ phải tự động, không cần Zalo thật)

Người phán xử luôn thay được bằng bản giả (`ask` là tham số), nên toàn bộ chạy được dưới CI.

1. **Nhận diện được gọi:** bảng ít nhất 30 câu tiếng Việt, có dấu và không dấu, cả ca phải im ("@Lan").
2. **Tín hiệu:** từng hàm, gồm `follow_up` với đồng hồ giả.
3. **Gắn nhãn:** kịch bản có thứ tự tin, kiểm từng dòng bảng 5.8 và các ca KHÔNG nhãn (phớt lờ).
4. **Ngưỡng:** cập nhật, kẹp biên, nhạt dần theo thời gian giả, tách theo cuộc chat.
5. **Tra ca:** xếp hạng, ưu tiên cùng cuộc chat, nhạt theo tuổi, trần dung lượng, 1000 ca dưới 50 ms.
6. **An toàn:** người ngoài dạy luật không được; model trả rác, hết giờ, ném lỗi thì im (còn `certain`
   vẫn trả lời); chèn "[IM_LANG]" hay "JAVIS_" trong tin chat không đi vào prompt; giá trị cấu hình lạ
   rơi về hẹp nhất.
7. **Kịch bản học đầu cuối** (nhân bản Zalo giả như `test_bot_zalo_nhom.py`): "javis vũ ơi" được trả
   lời; tin phiếm im và có dòng vết; câu hỏi có căn cứ bị im vì điểm thấp, người hỏi hỏi lại nên gắn
   `missed` và hạ ngưỡng, câu giống lần sau được trả lời và prompt của người phán xử giả CÓ chứa ca đó;
   nhóm B không bị ảnh hưởng bởi nhóm A; lời dạy của chủ có tác dụng ở tin kế tiếp; nút Quên xoá sạch.
8. **Cách ly giữa bot:** dựng ba bot có ba Agent khác lĩnh vực (hỗ trợ phần mềm, mỹ phẩm, dạy tiếng
   Anh). Kiểm: prompt của người phán xử giả cho bot B chỉ chứa hồ sơ vai của B, không có chữ nào của
   Agent A hay C; ca học ở bot A không bao giờ được tra ra ở bot B kể cả khi tin y hệt; ca khởi tạo của mỗi
   bot được sinh từ đúng Agent của bot đó (bộ sinh giả nhận đúng văn bản Agent); file mẫu cơ chế chỉ có
   chỗ giữ, không có tên ngành; bộ phán xử không bao giờ chạm vào chữ của câu trả lời và engine trả lời
   luôn được gọi với bản ghi bot của chính nó; ngưỡng và bài học của nhóm này không đổi nhóm kia.
9. **Ràng buộc chung:** `route_table.json` chụp lại, i18n vi/en đủ khoá, canary JS cho trường mới, không
   em dash, chuỗi UI có dấu, `test_prompt_budget` không đổi (không đụng CLAUDE.md).

## 10. Giao một lần: mốc và tiêu chí xong

Một PR (#502), commit theo mốc, mỗi mốc test xanh mới sang mốc sau:

| Mốc | Nội dung |
|---|---|
| M1 | `chatbot_reply_policy.py`: Event, Profile, nhận diện được gọi, sổ tín hiệu, cổng thô + test |
| M2 | Kho SQLite, ghi mọi quyết định kể cả im, giữ hạn, xoá theo bot |
| M3 | Hồ sơ vai biên dịch từ Agent, người phán xử, ba chế độ tat/bong/chay, nối vào `_answer` và `xu_ly`, fail-closed |
| M4 | Kho tình huống, tra cứu chỉ trong bot, mẫu cơ chế, ca khởi tạo theo vai, ngưỡng theo cuộc chat |
| M5 | Theo dõi hậu quả, gắn nhãn, lời dạy của chủ, bài học |
| M6 | Trường cấu hình, năm đường API, form và menu bot, i18n vi/en |
| M7 | Tài liệu (`docs/25-chatbot.md`, `docs/12-zalo.md`), CHANGELOG cho điện thoại, `route_table.json`, ghi nhớ |
| M8 | Kiểm sandbox thật với Zalo giả, chạy toàn bộ test, CI xanh, merge, xác nhận luồng phát hành |
| M9 | Hội thoại của bot chuyên trách chuyển khỏi lịch sử Trò chuyện, vào lịch sử của Agent nối với chatbot (mục 7.1) |

Xong khi TẤT CẢ đúng:
1. Tám nhóm test đầu ở mục 9 có mặt và xanh; toàn bộ test JS xanh; test Python đỏ sẵn trên `main` sạch
   (phân định bằng worktree sạch của `origin/main`) không tính.
2. Kịch bản đầu cuối mục 9.7 chạy được, kèm ba bot khác lĩnh vực chạy cạnh nhau không lẫn nhau và đã xem trên sandbox: giao diện form và bảng quyết định
   hiển thị đúng ở 1000 px và 375 px.
3. Mặc định không đổi hành vi bot cũ (`mode = off`, `learning_enabled = false`): test hồi quy của
   `test_bot_zalo_nhom.py` và `test_bot_doi_tuong.py` vẫn xanh nguyên.
4. Mã mới dùng định danh tiếng Anh theo 4.3. Test quét tên và đổi tên hàng loạt mã cũ HOÃN theo chủ (2026-09-30:
   "phần tiếng Anh thì để sau"), làm cùng đợt đổi tên.
5. CI của PR xanh, đã squash-merge vào `main`, `VERSION` là 0.65.0 và lớn hơn bản trên `main` lúc merge,
   luồng build ảnh Docker của `main` thành công.

## 11. Rủi ro đã cân

- **Chi phí và độ trễ:** mỗi ứng viên tốn một lượt model rẻ (1 đến 2 giây). Cổng thô, tín hiệu và hạn
  mức chặn trước; gọi tên chắc chắn không qua người phán xử.
- **Nhãn nhiễu:** chỉ tín hiệu mạnh, trọng số nhỏ cho một ca, ca nhạt theo tuổi, ngưỡng bị kẹp biên,
  nút Quên. Không dùng "tỉ lệ sai 50 quyết định gần nhất" làm căn cứ tự quay lại vì nhóm nhỏ mất nhiều
  tuần mới đủ mẫu và nhãn lại nhiễu.
- **Tiêm lệnh:** chỉ `trainer_ids` tạo luật; nội dung chat bị bọc và gỡ marker; đầu ra được kiểm khuôn.
- **Riêng tư:** học là opt-in từng bot, dữ liệu ngoài git, có hạn giữ, xoá theo bot.
- **Trôi hành vi:** ngưỡng kẹp biên, thẻ luật có trần, mẫu cơ chế làm điểm neo, và luôn có `shadow` để
  so trước khi chuyển sang `on`.

## 12. Để ngỏ

Thay `find_cases` bằng embedding khi có hạ tầng; chia sẻ ca giữa các bot cùng lĩnh vực và cùng chủ, chỉ khi chủ bật rõ, không mặc định;
tín hiệu cảm xúc; gắn nhãn từ reaction của Zalo nếu MCP mở ra; trang tổng hợp nhiều bot.
