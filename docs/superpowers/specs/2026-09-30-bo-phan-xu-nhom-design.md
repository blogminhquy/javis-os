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

## 2. Mục tiêu và không mục tiêu

Mục tiêu:
1. Nhận ra bị gọi tên trơn, hiểu tin nối tiếp sau lượt bot vừa nói.
2. Mọi quyết định, kể cả im, đều có dấu vết đọc được.
3. Một bộ máy dùng chung cho mọi bot và mọi kênh; cái riêng của từng bot nằm trong dữ liệu
   (hồ sơ, thẻ luật, ca đã học), không nằm trong mã.
4. Học tức thì từ phản ứng của người thật; ca vừa gắn nhãn tác động ngay quyết định kế tiếp.
5. Bot mới có hành vi hợp lý ngay ngày đầu (hạt giống), không cần học từ số không.

Không mục tiêu: đổi NỘI DUNG câu bot nói (vẫn bám tài liệu và vai của Agent); huấn luyện hay tinh
chỉnh model; học chéo giữa các người dùng; sửa cách bot chat riêng.

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
6. **Mở rộng bằng dữ liệu và cắm thêm, không bằng nhánh if.** Thêm tín hiệu, thêm kênh, thêm ngôn
   ngữ là thêm một hàm hoặc một dòng dữ liệu.
7. **Dữ liệu chat khách là dữ liệu nhạy cảm.** Học là bật riêng từng bot, mặc định TẮT; dữ liệu
   ngoài git, có hạn giữ, xoá theo bot, có nút quên.

## 4. Kiến trúc

```
tin nhóm -> [Sự kiện chuẩn hoá] -> R rào cứng -> G nhận diện được gọi -> T tín hiệu
                                                        |                  |
                                            chắc chắn ->|                  v
                                       (trả lời luôn)   |          C cổng thô (rác/không tín hiệu -> im + ghi vết)
                                                        |                  |
                                                        +----------> J người phán xử (model việc nền)
                                                                     ^   |   nhận: thẻ luật + ca giống + 8 tin gần nhất
                                                       ca giống -----+   v   trả: tra_loi|im + điểm + lý do
                                                       K kho tình huống   D so điểm với ngưỡng tau(bot, cuộc chat)
                                                                     ^   |
                                                    nhãn, lời dạy ---+   v
                                                       O theo dõi hậu quả  <- mọi tin sau đó của cuộc chat
```

Ba khối dữ liệu tách rời, đổi cái này không đụng cái kia:

- **Sự kiện (Event):** khuôn chuẩn hoá, không phụ thuộc kênh. Bộ chuyển đổi của Zalo và Telegram
  tự dựng.
- **Hồ sơ (Profile):** riêng từng bot. Tên gọi, thẻ luật, độ hăng hái, người được dạy bot.
- **Kho (Store):** ca đã học, nhật ký quyết định, ngưỡng theo cuộc chat.

Mã mới nằm trong `server/chatbot_phan_xu.py` (bộ máy, thuần và test được) và
`server/chatbot_phan_xu_kho.py` (SQLite). Không nhét vào `chatbot_runtime.py` thêm nữa.

### 4.1 Sự kiện chuẩn hoá

```
Event: kenh, bot_id, chat_id, chat_type, msg_id, ts, text, sender_id, sender_name,
       vai_nguoi_noi ("chu" | "da_biet" | "moi"), tag (bool), reply_to_bot (bool),
       cua_so (tối đa 8 tin gần nhất: ts, sender_id, ten, la_bot, text),
       bot_noi_lan_cuoi (ts hoặc None), chu_vua_go_tay (bool)
```

`cua_so` lấy từ Hộp thư (`conversations.tin_nhan`) của đúng cuộc chat; chưa có thì rỗng, bộ máy
vẫn chạy. Nội dung mỗi tin cắt 400 ký tự, gỡ marker nội bộ (`[IM_LANG]`, `JAVIS_`).

## 5. Các tầng

### 5.1 R: rào cứng (giữ nguyên, không học được)

Nhóm chưa được cho phép thì im (`_nhom_duoc_phep`); người chưa chọn thì im; cuộc chat đã Tiếp
quản; chủ vừa gõ tay (`chu_vua_nhan_tay`); tin cũ quá `TUOI_TOI_DA`; tin do chính nick gửi;
hạn mức số lần tự nói (`chatbot_tu_dong.duoc_tra_loi`); không làm hành động ra ngoài do bộ phán
xử. Rào chạy TRƯỚC mọi thứ tốn model và vẫn ở chỗ hiện tại trong `chatbot_runtime`.

### 5.2 G: nhận diện được gọi

Trả `goi` ∈ `chac` | `co_the` | `khong` cùng bằng chứng. Chuẩn hoá: bỏ dấu, chữ thường, gộp khoảng
trắng (dùng `chatbot_grounding._bo_dau`), khớp theo ranh giới từ.

| Mức | Điều kiện |
|---|---|
| `chac` | `@tên`; `mentions` chứa id nick; reply vào tin của bot; tên gọi đứng ĐẦU câu (sau các chữ mở như "ê", "này", "alo", "hi", "chào"); tên gọi đi liền tiểu từ gọi ("ơi", "à", "ạ", "này", "nè", "nha", "ê") |
| `co_the` | tên gọi nằm giữa hoặc cuối câu không kèm tiểu từ ("hỏi javis vũ xem"); tin nối tiếp (5.3) |
| `khong` | còn lại |

Tên gọi (`bi_danh`) gồm: nhãn kết nối, tên hiển thị học được của nick, và danh sách tên do chủ tự
thêm. KHÔNG tự lấy tên Agent hay tên bot ("@Lan" trong nhóm thường là một thành viên tên Lan). Tên
tự suy phải dài từ 4 ký tự trở lên sau chuẩn hoá; tên do chủ thêm không bị luật này.

Ví dụ phải đúng (chạy cả bản không dấu): "javis vũ ơi" chac; "Javis Vũ giúp anh cái này" chac;
"alo javis vu" chac; "hỏi javis vũ xem" co_the; "mai họp mấy giờ" khong; "@Lan xem giúp" khong.

`chac` thì trả lời luôn như chat riêng, KHÔNG qua người phán xử, KHÔNG cần tài liệu, không đếm
hạn mức tự nói.

### 5.3 T: tín hiệu (sổ đăng ký, cắm thêm được)

Mỗi tín hiệu là một hàm thuần `(Event, Profile) -> {gia_tri, bang_chung}` đăng ký bằng decorator.
Thêm tín hiệu = thêm một hàm và một test; không đụng khung.

- `cau_hoi`: điểm 0..1 từ dấu hỏi, từ khoá (bảng dữ liệu, thay `_HOI`), cấu trúc "có ... không".
  Từ nay là TÍN HIỆU, không còn là cổng chặn.
- `tiep_noi`: bot vừa nói trong nhóm ≤ 180 giây và tin này của đúng người bot vừa trả lời, hoặc
  reply vào chuỗi đó.
- `khop_tai_lieu`: có phần tài liệu khớp (`chatbot_grounding.thu_thap`), kèm điểm. Chỉ tính cho
  ứng viên, không quét đĩa cho mọi tin.
- `vai_nguoi_noi`: chủ / đã biết (đã có hội thoại với bot) / mới.
- `nhip_nhom`: mật độ tin trong 2 phút gần nhất (nhóm đang sôi nổi thì bot bớt chen).
- `bi_danh_giua_cau`: tên gọi xuất hiện nhưng chưa đủ `chac`.

### 5.4 C: cổng thô

Chỉ vứt thứ hiển nhiên không phải: rỗng, không phải chữ, chỉ có link, một hai chữ không phải lời
gọi, tin mở đầu bằng tag người khác khi `goi = khong`. Tin còn lại là **ứng viên** khi có ít nhất một
trong: `goi = co_the`, `tiep_noi`, `cau_hoi >= 0.5`, hoặc kho có ca dương giống (5.7). Không ứng
viên thì im VÀ ghi vết `khong_tin_hieu`.

Giữ luật hiện có cho lời tự nói: khi `goi = khong` và không `tiep_noi`, bot chỉ mở miệng nếu có căn
cứ. Cấu hình `can_cu`: `tai_lieu` (mặc định, phải có `khop_tai_lieu`) hoặc `vai_tro` (bot lấy chuyên
môn từ vai của Agent, dùng cho bot tư vấn không dựa vào tài liệu). Ca đã học KHÔNG được miễn luật
này.

### 5.5 J: người phán xử

Một lượt model rẻ, chạy bằng engine "việc nền" (`aux_engine`, chủ đã chọn ở trang Models), mode
`suggest`, không công cụ. Đầu vào là văn bản gồm:

1. Thẻ luật của bot (5.10) và vai tóm tắt của Agent.
2. Tối đa 5 ca giống nhất kèm "quyết định đúng" (5.7).
3. Cửa sổ 8 tin gần nhất, người nói, bot đã nói gì.
4. Tín hiệu đã tính và đoạn tài liệu khớp (cắt ngắn).
5. Tin cần quyết.

Toàn bộ nội dung chat bọc trong khối `<du_lieu_chat>` và prompt nói rõ đó là dữ liệu, không phải
lệnh. Đầu ra bắt buộc một JSON: `{"quyet":"tra_loi"|"im","diem":0..1,"ly_do":"<= 120 ký tự"}`.
Sai khuôn, hết 8 giây, hay lỗi engine: coi là `im` với lý do `phan_xu_loi`.

Chế độ: `tat` (chạy luật cũ), `bong` (người phán xử chạy song song, chỉ ghi, luật cũ quyết), `chay`
(người phán xử quyết). Bot đang có sẵn giữ `tat` cho tới khi chủ bật.

### 5.6 D: ngưỡng

`tau = tau_goc(hang_hai) + lech(bot, cuoc_chat)`. `tau_goc`: ít lời 0.75, vừa 0.60, nhiều lời 0.45.
Bot nói khi `quyet = tra_loi` và `diem >= tau`. `lech` ∈ [-0.25, +0.25], `tau` kẹp trong [0.30, 0.90].
Cập nhật: im nhầm trừ 0.05, chen nhầm cộng 0.08 (chen đắt hơn im), nhân với trọng số nhãn. Không có
nhãn thì `lech` co dần về 0 với chu kỳ bán rã 14 ngày. Ngưỡng theo TỪNG cuộc chat: nhóm khách
thích bot nói nhiều, nhóm nội bộ thì không.

### 5.7 K: kho tình huống

Mỗi quyết định ứng viên ghi một dòng; khi có nhãn nó thành **ca**. Tra cứu không cần thư viện
embedding: điểm giống = 0.6 × Jaccard(token chuẩn hoá) + 0.25 × khớp đặc trưng (`goi`, `tiep_noi`,
`vai_nguoi_noi`) + 0.15 nếu cùng cuộc chat, nhân độ nhạt theo tuổi (bán rã 30 ngày) và trọng số ca.
Lấy tối đa 5 ca điểm ≥ 0.25. "Quyết định đúng" của ca: `dung` thì giữ quyết định đã chọn,
`im_nham` thì `tra_loi`, `chen_nham` thì `im`, `loi_day` thì theo lời dạy. Giao diện `tim_ca(event,
k)` để sau này thay bằng embedding mà không đổi khung.

**Hạt giống:** `system/phan_xu/hat_giong_vi.json`, khoảng 40 ca chung bằng tiếng Việt (gọi tên trơn,
chào hỏi, chuyện phiếm, hỏi sản phẩm, nhờ giúp giữa người với người, tag người khác, tin nối tiếp,
xin ý kiến nhóm). Nạp vào mọi bot mới như ca `nguon = hat_giong`, trọng số thấp; ca của bot và của
cuộc chat đè lên bằng độ giống và độ mới. Đây là cách bot thứ hai, thứ ba khởi động khôn sẵn mà
không chép hành vi từ bot khác.

Trần: 500 ca mỗi bot, 200 mỗi cuộc chat; vượt thì bỏ ca có trọng số × độ mới thấp nhất, ca đã gộp
vào thẻ luật thì xoá khỏi kho.

### 5.8 O: theo dõi hậu quả và gắn nhãn

Mỗi quyết định ứng viên mở một cửa theo dõi 10 phút hoặc 8 tin, tuỳ cái nào tới trước. Mỗi tin
mới của cuộc chat chạy qua `gan_nhan(theo_doi, tin_moi)`, hàm thuần. Chỉ tín hiệu MẠNH mới gắn nhãn;
**không phản ứng thì không nhãn** (bị phớt lờ là chuyện thường, và im thì vốn không có phản ứng để đo,
dùng nó làm nhãn sẽ dạy bot nói nhiều hơn).

| Quyết định | Tín hiệu | Nhãn | Trọng số |
|---|---|---|---|
| im | cùng người hỏi lại ("sao không trả lời", "bot ơi", "ai biết không") hoặc gửi lại gần giống ≥ 0.6 | `im_nham` | 1.0 |
| im | có người gọi tên chắc chắn ngay sau, cùng chủ đề | `im_nham` | 0.8 |
| im | chủ tự trả lời thực chất cho đúng người hỏi | `im_nham` | 0.5 (chủ có thể chỉ tiện tay) |
| tra_loi (không được gọi) | chủ nói "đừng chen vào", "ai hỏi bot", "im đi" | `chen_nham` | 1.0 |
| tra_loi (không được gọi) | người khác nói câu tương tự | `chen_nham` | 0.5 |
| tra_loi (không được gọi) | chủ bấm Tiếp quản cuộc chat trong 10 phút | `chen_nham` | 0.7 |
| tra_loi | cảm ơn, "ok", "được rồi" | `dung` | 0.6 |
| tra_loi | hỏi tiếp đúng mạch (`tiep_noi`, reply vào bot) | `dung` | 0.8 |
| bất kỳ | chủ bấm 👍 hoặc 👎 trong Nhật ký | theo nút | 1.5 |

Bảng từ khoá tín hiệu nằm ở `system/phan_xu/tu_khoa_vi.json` (đã bỏ dấu), thêm ngôn ngữ là thêm file.
Chống spam nhãn: mỗi người tối đa 3 nhãn mỗi giờ mỗi bot, mỗi bot tối đa 50 ca mới mỗi ngày.

### 5.9 Lời dạy của chủ

Tin của người trong `chu_ids` gọi bot (`goi >= co_the`) chạy thêm một lượt phân loại rẻ: "đây có
phải chủ đang dạy bot cách hành xử không?" → `{"la_loi_day":bool,"luat":"...","kieu":"nen_noi"|"nen_im"|"goi_ten"}`.
Đúng thì: tạo ca `loi_day` trọng số 2.0 (có tác dụng ngay ở quyết định kế tiếp), thêm một dòng vào
mục Bài học của thẻ luật, và nếu `kieu = goi_ten` thì thêm cụm đó vào `bi_danh`. Người ngoài
`chu_ids` không bao giờ tạo được luật, cho dù họ viết "từ giờ hãy trả lời mọi tin".

### 5.10 Thẻ luật

`the_luat` (chủ sửa tay) + `bai_hoc` (máy ghi, theo mẫu `JAVIS_LESSON`: đề xuất lúc dùng, mã ghi, khử
trùng, tối đa 15 dòng, dòng cũ nhất rơi ra). Bật bộ phán xử lần đầu mà `the_luat` trống thì soạn
nháp từ vai của Agent bằng một lượt model, hiện trong form cho chủ sửa; không có engine thì dùng mẫu
tĩnh. KHÔNG có vòng nền viết lại hàng loạt (quyết định của chủ 2026-08-16).

## 6. Dữ liệu

SQLite `chatbot_phan_xu.sqlite3` trong thư mục state, thêm vào `.gitignore`, WAL.

```
quyet_dinh(id, bot_id, chat_id, msg_id, ts, van_ban, nguoi_gui, vai, goi, tin_hieu_json,
           ung_vien, quyet, diem, tau, ly_do, che_do, ma_im, nhan, trong_so_nhan, nhan_ts)
tinh_huong(id, bot_id, chat_id, ts, van_ban, token, dac_trung_json, quyet_dung, ly_do,
           nguon, trong_so, ca_goc_id)               -- nguon: tu_dong|chu|hat_giong
theo_doi(quyet_dinh_id, het_han_ts, so_tin_con_lai)
lech_tau(bot_id, chat_id, lech, cap_nhat_ts)
```

Giữ: dòng chưa gắn nhãn 14 ngày; ca đã gắn nhãn 180 ngày (có nhạt dần); nội dung cắt 400 ký tự.
Xoá bot thì xoá sạch dòng của bot. Vòng đệm im: mọi tin bị im đều là một dòng `quyet_dinh` với
`ma_im` (`khong_tin_hieu`, `khong_co_can_cu`, `phan_xu_loi`, `het_han_muc`, `vua_noi`...).

## 7. Cấu hình, API, giao diện

Trường mới trong bản ghi bot (đi qua `chatbot_store`, có lọc và giá trị mặc định fail-closed):

```
phan_xu: { che_do: "tat"|"bong"|"chay" (mặc định tat), hang_hai: "it"|"vua"|"nhieu" (vua),
           the_luat: str, bi_danh: [str], chu_ids: [str], tu_hoc: bool (false),
           can_cu: "tai_lieu"|"vai_tro" (tai_lieu) }
```

Giá trị lạ rơi về phía hẹp nhất (`tat`, `it`, `tu_hoc = false`). Chỉ có nghĩa khi `reply_when = auto`.

Đường mới, đặt SAU route cuối của `main.py` để `route_table.json` chỉ thêm dòng cuối:

- `GET /chatbots/{id}/phan-xu`: cấu hình, số ca, lệch ngưỡng từng cuộc chat, 100 quyết định gần nhất
  (kể cả im), danh sách ca và bài học.
- `POST /chatbots/{id}/phan-xu/nhan`: chủ gắn 👍/👎 cho một quyết định.
- `POST /chatbots/{id}/phan-xu/tinh-huong/{ca}/xoa`: xoá một ca.
- `POST /chatbots/{id}/phan-xu/quen`: quên hết, hoặc riêng một cuộc chat.
- `POST /chatbots/{id}/phan-xu/soan-the-luat`: soạn nháp thẻ luật từ vai Agent.

Giao diện (một cột, đúng phong cách form hiện tại, đủ vi và en):

- Trong phần "Bot trả lời ai", khi chọn "Tự đánh giá": khối **Bộ phán xử** gồm nút chọn một Tắt /
  Chạy thử / Bật, nút chọn một Ít lời / Vừa / Nhiều lời, ô "Luật lên tiếng" kèm nút "Soạn từ vai
  trò", ô "Tên gọi thêm", chọn người dạy bot từ danh sách người, và ô tick "Cho bot tự học từ phản
  ứng trong nhóm" (tắt sẵn, một dòng nói rõ bot lưu nội dung chat nhóm để học).
- Menu "..." của thẻ bot thêm **Bộ phán xử**: bảng quyết định gần đây có cả tin bị im, mỗi dòng có
  👍 👎, danh sách bài học, nút Quên hết.

## 8. Chỗ gắn vào mã hiện có

- `zalo_personal_channel.nhan_dien_goi`: giữ nguyên chữ ký `(tag, rep)` cho chỗ gọi cũ, bên trong dùng
  `chatbot_phan_xu.nhan_dien_goi`; thêm bản trả mức `goi`.
- `channels/zalo_personal.py::xu_ly`: dựng Event, đưa MỌI tin nhóm (kể cả tin sẽ bị loại) qua
  `theo_doi` để gắn nhãn cho quyết định trước; meta thêm `goi`, `tiep_noi`.
- `chatbot_runtime._answer`: khối `tu_dong` gọi `chatbot_phan_xu.quyet_dinh(...)` khi `che_do != tat`;
  `bong` chạy song song rồi bỏ kết quả. `_ly_do_im`, `_make_precheck_fn` không đổi.
- Telegram: `TelegramBot._build_meta` đã có `mentioned`, `reply_to_bot`; thêm nhận diện tên gọi qua
  cùng module.
- `chatbot_store`: `_PATCHABLE`, `_public`, kiểm giá trị. `chatbot_log`: tin bị im KHÔNG vào JSONL
  của bot (tránh nhiễu), vào kho mới và hiện ở Nhật ký qua bộ lọc "Cả tin bot im".

## 9. Kiểm thử (mọi thứ phải tự động, không cần Zalo thật)

Người phán xử luôn thay được bằng bản giả (`ask` là tham số), nên toàn bộ chạy được dưới CI.

1. **Nhận diện được gọi:** bảng ít nhất 30 câu tiếng Việt, có dấu và không dấu, cả ca phải im ("@Lan").
2. **Tín hiệu:** từng hàm, gồm `tiep_noi` với đồng hồ giả.
3. **Gắn nhãn:** kịch bản có thứ tự tin, kiểm từng dòng bảng 5.8 và các ca KHÔNG nhãn (phớt lờ).
4. **Ngưỡng:** cập nhật, kẹp biên, nhạt dần theo thời gian giả, tách theo cuộc chat.
5. **Tra ca:** xếp hạng, ưu tiên cùng cuộc chat, nhạt theo tuổi, trần dung lượng, 1000 ca dưới 50 ms.
6. **An toàn:** người ngoài dạy luật không được; model trả rác, hết giờ, ném lỗi thì im (còn `chac`
   vẫn trả lời); chèn "[IM_LANG]" hay "JAVIS_" trong tin chat không đi vào prompt; giá trị cấu hình lạ
   rơi về hẹp nhất.
7. **Kịch bản học đầu cuối** (nhân bản Zalo giả như `test_bot_zalo_nhom.py`): "javis vũ ơi" được trả
   lời; tin phiếm im và có dòng vết; câu hỏi có căn cứ bị im vì điểm thấp, người hỏi hỏi lại nên gắn
   `im_nham` và hạ ngưỡng, câu giống lần sau được trả lời và prompt của người phán xử giả CÓ chứa ca đó;
   nhóm B không bị ảnh hưởng bởi nhóm A; lời dạy của chủ có tác dụng ở tin kế tiếp; nút Quên xoá sạch.
8. **Ràng buộc chung:** `route_table.json` chụp lại, i18n vi/en đủ khoá, canary JS cho trường mới, không
   em dash, chuỗi UI có dấu, `test_prompt_budget` không đổi (không đụng CLAUDE.md).

## 10. Giao một lần: mốc và tiêu chí xong

Một PR (#502), commit theo mốc, mỗi mốc test xanh mới sang mốc sau:

| Mốc | Nội dung |
|---|---|
| M1 | `chatbot_phan_xu.py`: Event, Profile, nhận diện được gọi, sổ tín hiệu, cổng thô + test |
| M2 | Kho SQLite, ghi mọi quyết định kể cả im, giữ hạn, xoá theo bot |
| M3 | Người phán xử, ba chế độ tat/bong/chay, nối vào `_answer` và `xu_ly`, fail-closed |
| M4 | Kho tình huống, tra cứu, hạt giống, ngưỡng theo cuộc chat |
| M5 | Theo dõi hậu quả, gắn nhãn, lời dạy của chủ, bài học |
| M6 | Trường cấu hình, năm đường API, form và menu bot, i18n vi/en |
| M7 | Tài liệu (`docs/25-chatbot.md`, `docs/12-zalo.md`), CHANGELOG cho điện thoại, `route_table.json`, ghi nhớ |
| M8 | Kiểm sandbox thật với Zalo giả, chạy toàn bộ test, CI xanh, merge, xác nhận luồng phát hành |

Xong khi TẤT CẢ đúng:
1. Bảy nhóm test ở mục 9 có mặt và xanh; toàn bộ test JS xanh; test Python đỏ sẵn trên `main` sạch
   (phân định bằng worktree sạch của `origin/main`) không tính.
2. Kịch bản đầu cuối mục 9.7 chạy được và đã xem trên sandbox: giao diện form và bảng quyết định
   hiển thị đúng ở 1000 px và 375 px.
3. Mặc định không đổi hành vi bot cũ (`che_do = tat`, `tu_hoc = false`): test hồi quy của
   `test_bot_zalo_nhom.py` và `test_bot_doi_tuong.py` vẫn xanh nguyên.
4. CI của PR xanh, đã squash-merge vào `main`, `VERSION` là 0.65.0 và lớn hơn bản trên `main` lúc merge,
   luồng build ảnh Docker của `main` thành công.

## 11. Rủi ro đã cân

- **Chi phí và độ trễ:** mỗi ứng viên tốn một lượt model rẻ (1 đến 2 giây). Cổng thô, tín hiệu và hạn
  mức chặn trước; gọi tên chắc chắn không qua người phán xử.
- **Nhãn nhiễu:** chỉ tín hiệu mạnh, trọng số nhỏ cho một ca, ca nhạt theo tuổi, ngưỡng bị kẹp biên,
  nút Quên. Không dùng "tỉ lệ sai 50 quyết định gần nhất" làm căn cứ tự quay lại vì nhóm nhỏ mất nhiều
  tuần mới đủ mẫu và nhãn lại nhiễu.
- **Tiêm lệnh:** chỉ `chu_ids` tạo luật; nội dung chat bị bọc và gỡ marker; đầu ra được kiểm khuôn.
- **Riêng tư:** học là opt-in từng bot, dữ liệu ngoài git, có hạn giữ, xoá theo bot.
- **Trôi hành vi:** ngưỡng kẹp biên, thẻ luật có trần, hạt giống làm điểm neo, và luôn có `bong` để
  so trước khi chuyển sang `chay`.

## 12. Để ngỏ

Thay `tim_ca` bằng embedding khi có hạ tầng; dùng chung ca giữa các bot cùng loại (qua chợ workflow);
tín hiệu cảm xúc; gắn nhãn từ reaction của Zalo nếu MCP mở ra; trang tổng hợp nhiều bot.
