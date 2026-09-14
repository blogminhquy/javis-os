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
