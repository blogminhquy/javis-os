# Voice V2 - bộ não giọng nói riêng, nghe bằng Groq, nghe nói thẳng (Live)

> Viết 2026-09-14 trên nền v0.56.0 (Voice V1). Chủ dự án chốt: làm cả hai bậc; ưu tiên gói
> subscription (Antigravity) cho bộ não giọng; gom Groq đã có cho phần nghe; nhà cung cấp
> nghe nói thẳng phải đổi được như đổi model.

## 1. Số đo làm nền cho thiết kế

Đo trên máy chủ dự án 2026-09-14 với `agy` 1.2.2, model `gemini-3.8-flash-low`:

- mỗi tiến trình mới: chữ đầu về sau 4,2 s (2,6 s là khởi động tiến trình), model mặc định 8-9 s;
- MỘT tiến trình sống lâu (`--input-format stream-json`, mỗi lượt một dòng
  `{"event":"user","message":{"role":"user","content":"..."}}`): lượt 2 trở đi chữ đầu 1,3-2,0 s,
  giữ ngữ cảnh, và stream từng mảnh (`step_update.text_delta`).

Kết luận: bộ não giọng trên gói Antigravity khả thi ở mức tiếng đầu ~2 s nếu giữ tiến trình
sống suốt phiên nói. API Groq/Gemini còn nhanh hơn (0,5-0,8 s) cho ai có key.

## 2. Ba chế độ, một trang cài đặt

`settings.voice` thêm: `mode` (standard | fast | live), `brain_provider` ("" = bộ não chính |
antigravity | groq | gemini | openai | openrouter), `brain_model`, `stt_provider` (browser |
groq), `stt_model`, `live_provider` (gemini | openai), `live_model`, `live_voice`. Trang Cài đặt
→ nhóm Giọng nói thêm thẻ "Chế độ và bộ não giọng nói". Key dùng lại của trang Models.

- **Chuẩn**: đúng Voice V1.
- **Làn nhanh (fast)**: tin đến từ mic (`voice: true` trong khung WS) đi qua `voice_brain.py`
  thay vì bộ não chính. Bộ não giọng trả lời ngắn; câu nào cần dữ liệu, tool, file, ký ức hay
  hành động thì nó trả đúng một dòng `JAVIS_ASK_MAIN: <yêu cầu>` (được phép có một câu chờ
  trước đó). Server đọc dòng đó, đọc câu chờ ra loa, rồi chạy lượt bộ não chính như thường
  trong CÙNG phiên. Mọi thứ đều ghi vào kho phiên, gõ chữ hay nói đều một mạch.
- **Live**: trình duyệt mở `/ws/voice-live`, đẩy PCM16 16 kHz; server nối tới nhà cung cấp
  (`voice_live.py`: Gemini Live hoặc OpenAI Realtime) và trả PCM16 24 kHz về. Ngắt lời do nhà
  cung cấp dò; server báo `interrupted` để trình duyệt xả hàng đợi phát. Model có tool
  `ask_javis` gọi bộ não chính. Bản ghi chữ hai chiều hiện trong khung chat và lưu vào phiên.

## 3. Nghe bằng Groq

`stt_provider: groq`: voice.js ghi MediaRecorder (webm/opus) song song với Web Speech; Web
Speech vẫn cho chữ tạm và điểm dừng câu; hết câu thì gửi file lên `POST /stt` (Groq Whisper
qua `stt.groq_nghe`, key `model.groq_api_key`), chữ Groq thay chữ Chrome; Groq lỗi thì dùng chữ
Chrome. Không thêm độ trễ đáng kể vì ghi âm chạy song song và file chỉ vài trăm KB.

## 4. Giao diện nhà cung cấp Live

`LiveProvider`: `connect()`, `send_audio(pcm16_16k)`, `send_text()`, `send_tool_result()`,
`interrupt()`, `close()`, `events()` trả sự kiện chuẩn hoá: `audio` (bytes 24 kHz), `interrupted`,
`transcript` (role, text, final), `tool_call` (id, name, args), `turn_done`, `error`. Thêm nhà
cung cấp = thêm một lớp, không đụng route hay trình duyệt. Tên model mặc định để trong cài đặt vì
Google và OpenAI đổi tên liên tục.

## 5. An toàn và giới hạn

- Tiến trình `agy` sống lâu đóng sau 5 phút không nói; chết thì mở lại và mồi lại 10 lượt gần
  nhất từ kho phiên. Chỉ mở khi có người đang nói, không phải chạy nền 24/7.
- Bộ não giọng không có tool ngoài `JAVIS_ASK_MAIN`; hành động ra ngoài vẫn qua bộ não chính.
- Live chỉ bật được khi có key của nhà cung cấp; thiếu thì trang cài đặt nói rõ.
- Ngoài phạm vi: wake word khi mic tắt, STT streaming server, TTS có cảm xúc ngoài các provider
  đã có.

## 6. Sau khi so với GPT-Live (0.57.1, cùng ngày)

Đọc bài giới thiệu GPT-Live (OpenAI, 07/2026) và tài liệu API (09/2026): hai ý lớn là song công
toàn phần (model tự quyết nghe/nói/ngắt) và ủy nhiệm việc nặng cho model nền TRONG LÚC vẫn trò
chuyện. Javis đã có ý thứ hai (`ask_javis`, `JAVIS_ASK_MAIN`) nhưng route Live `await` tool ngay
trong vòng đọc sự kiện nên cuộc nói chuyện đứng im 5 đến 30 giây. Sửa:

- `ask_javis` chạy thành task nền (`_run_tool` trong route), vòng đọc sự kiện không dừng. Gemini
  2.5 Flash Live khai báo tool `behavior: NON_BLOCKING`, kết quả `scheduling: WHEN_IDLE`; Gemini
  3.1 Flash Live CHƯA hỗ trợ tool bất đồng bộ (tài liệu Google) nên model im chờ, nhưng audio vẫn
  chảy. OpenAI Realtime: kết quả tool về khi model đang nói thì `response.create` xếp hàng tới
  `response.done`.
- Ngữ cảnh giao diện: trình duyệt gửi khung `context` (cùng khối `[NGỮ CẢNH GIAO DIỆN: ...]` của
  V1, chỉ khi đổi, dò 1,5 s một lần); server kèm vào yêu cầu gửi bộ não chính và đẩy vào kênh
  im lặng của hãng nếu có (GPT-Live `session.thinking.append`).
- Ngắt lời: trình duyệt đo số ms đã phát của câu đang nói, gửi khung `played`; OpenAI Realtime
  nhận `conversation.item.truncate` để ngữ cảnh chỉ giữ phần đã nghe (nguyên tắc V1).
- Gemini: `sessionResumption` + `contextWindowCompression` trong setup; nhận `goAway` thì route nối
  lại ngay bằng handle cũ, trình duyệt chỉ thấy khung `reconnected`.
- Nhà cung cấp thứ ba `gpt-live` (`wss://api.openai.com/v1/live/sessions`, `session.start`, ủy nhiệm
  `client`): `session.delegation.created` -> chạy bộ não chính với câu người dùng vừa nói ->
  `session.commentary.append`. Không có sự kiện interrupted/turn_done, suy ra từ transcript. Khuôn
  sự kiện lấy từ SDK openai 3.13. CHƯA chạy thật (máy dev không có key).

## 7. Làn nhanh nghe giật (0.57.2)

Triệu chứng: nói chuyện ở làn nhanh (Antigravity) nghe giật, cắt từng mẩu, orb hay báo MẠNG CHẬM.
Nguyên nhân gốc: `_flush` trong `run_voice_turn` đẩy MỖI delta stream (vài từ) thành một khung
`stream`, và `app.js` gọi `voice.enqueueSpeak` cho mỗi khung, mỗi khung là một yêu cầu Edge TTS
riêng (0,5 đến 2 giây chờ mỗi cái); giữa hai khung không tải trước gì. Sửa hai tầng:
- server: `voice_brain.split_speakable(text, start, final)` (hàm thuần, có test) chỉ trả phần ĐỌC
  ĐƯỢC: câu đã khép, dòng đã khép, hoặc đoạn dở dài quá `SPEAK_MAX` cắt ở dấu phẩy; marker vẫn
  không ra loa.
- trình duyệt: `voice.js` tải trước câu KẾ trong hàng đợi khi đang ở khúc cuối câu hiện tại
  (`_preloadNextQueued`), preload khớp theo URL thay vì index.

## 8. Bấm Lưu báo xong mà F5 là mất (0.57.3)

Triệu chứng: trang Cài đặt chọn Làn nhanh + bộ não giọng, bấm Lưu, nút hiện "Đã lưu", tải lại
trang thì về giá trị cũ.

Nguyên nhân gốc: nhánh `voice` của `POST /settings` dùng ALLOWLIST TỪNG KEY và chỉ liệt kê các ô
TTS cũ. Bảy ô Voice V2 (`mode`, `brain_provider`, `brain_model`, `stt_provider`, `live_provider`,
`live_model`, `live_voice`) không có tên trong đó nên bị bỏ im lặng, endpoint vẫn trả
`{"ok": true}`. Giá trị đang có trong `settings.json` của máy dev là do viết tay lúc phát triển,
nên đường lưu chưa từng chạy đúng lần nào. Chính comment ở nhánh `locale` đã cảnh báo đúng bẫy này.

Sửa:
- `voice_brain.MODES / BRAIN_PROVIDERS / STT_PROVIDERS` là NGUỒN DUY NHẤT cho các ô chọn;
  `GET /voice/options` vẽ từ đó và nhánh lưu cũng nhận đúng từ đó, không còn hai danh sách song
  song. `_make` và `config_from_settings` cũng lấy `key_field` và `default_model` từ đây.
- `tests/python/test_luu_cai_dat_giong.py`: vòng tròn lưu rồi đọc lại qua TestClient, cộng một
  chốt chặn đọc khối `data` của nút Lưu trong `console.js` và bắt lỗi nếu có key nào nhánh voice
  của `main.py` chưa xử lý. Thêm ô mới mà quên server là test đỏ ngay.
- BẪY khi viết test: rào chống DNS-rebinding trả 403 cho host `testserver` mặc định của
  TestClient, phải đặt `base_url="http://127.0.0.1:7777"`, không thì 403 che mất lỗi thật.

## 9. Whisper bịa câu đăng ký kênh YouTube (0.57.4)

Triệu chứng: đang nói chuyện bằng giọng thì trong khung chat hiện một tin của NGƯỜI DÙNG với nội
dung "Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn ...", và Javis trả
lời câu đó một cách nghiêm túc.

Nguyên nhân gốc: không phải lỗi Javis, mà là ảo giác kinh điển của Whisper. Whisper học chủ yếu
từ phụ đề YouTube nên khi audio là im lặng, tiếng ồn nền hay một đoạn ngắn không rõ, nó sinh ra
câu outro dày đặc nhất trong dữ liệu học. Đường đi: `voice.js` ghi song song với Web Speech, hết
câu thì đẩy file lên `POST /stt`, và chữ Whisper THAY chữ Chrome (`cb(better || text)`), nên câu
bịa ghi đè lên câu nghe đúng. Không có tầng nào lọc, và vì không phải lỗi mạng nên không có gì
báo.

Sửa: `stt.loc_ao_giac(text)` trong `server/stt.py`, gọi ngay trong `groq_nghe` nên mọi kênh
(dashboard, Telegram, Zalo) dùng chung. Cắt THEO TỪNG CÂU vì Whisper hay dán câu bịa vào trước
lời thật; lọc xong rỗng thì trả `khong_nghe_ro` để `voice.js` giữ chữ Web Speech.

Ranh giới cố ý: mẫu chỉ bắt dấu hiệu riêng của câu outro (tên kênh, "subscribe cho kênh", "không
bỏ lỡ ... video"). Người dùng bàn chuyện marketing hằng ngày, nên thà sót một câu bịa còn hơn
nuốt một câu nói thật. `tests/python/test_stt_ao_giac.py` canh cả hai phía: cắt đúng câu bịa VÀ
giữ nguyên bảy câu nói thật dễ bị bắt nhầm.
