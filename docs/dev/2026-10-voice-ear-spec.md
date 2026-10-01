# Tai nghe lại: model đa ngôn ngữ nghe âm thanh rồi mới chốt bong bóng (0.65.15)

Ngày 01/10/2026. Hồ sơ cho PR A (tai dạng tải lên, Groq chạy đủ mọi lượt, bộ đo) và ghi lại kết
quả thử nhanh tai ChatGPT realtime, làm nền cho bước kế tiếp "Live qua gói ChatGPT".

## 1. Vấn đề và số đo

Chrome Web Speech chỉ nghe một ngôn ngữ (vi-VN), nên câu Việt pha tiếng Anh hỏng nặng: "Mở
dashboard Facebook ads" thành "Mở double Facebook add". Bộ đo `tools/stt_bench` (26 clip Edge
TTS, 20 câu pha) chấm ba số: tỉ lệ từ sai (WER), số thuật ngữ đúng, số câu lệnh đúng trọn.

| Cách nghe (20 câu pha) | Từ sai | Thuật ngữ | Lệnh đúng trọn | Thời gian |
|---|---|---|---|---|
| Chrome thô | 41% | 11/42 | 4/20 | tức thì |
| Chrome rồi model mạnh sửa chữ theo từ điển | 23% | 28/42 | 11/20 | 1 lượt model |
| **Groq Whisper qua đường /stt của Javis** | **14%** | **33/42** | **13/20** | 0,9 giây |
| ChatGPT realtime (gói, WebRTC) | 13% | 33/42 | 12/20 | 0,5 giây sau khi nói xong |
| Gemini nghe file qua Antigravity CLI | 5% | 39/42 | 17/20 | 7 đến 17 giây |

Đo thêm cùng ngày:
- Rào sửa chữ hiện có (`voice_brain.safe_transcript_rewrite`) chặn 9 trên 13 câu sửa đúng; có câu
  Chrome làm mất hẳn thông tin ("John Smith về deadline" thành "Dung biết về nick liên quân").
  Sửa chữ sau khi nghe không cứu được tận gốc.
- Rào đối chiếu nháp (`stt.khop_ban_nhap`) cho qua 12 trên 13 câu chữ đúng của tai. Nó là rào
  chống bịa dùng chung cho mọi tai (Gemini từng trả nguyên một câu không liên quan ở clip v1a).

## 2. Đường đã loại

- **Tai Claude.** Model Claude không nhận âm thanh (Messages API không có khối audio). Giọng nói
  của Claude Code là dịch vụ riêng (`/api/ws/speech_to_text/voice_stream`), chỉ thu mic của máy
  chạy terminal và cần token đăng nhập claude.ai mà Javis cố ý không đọc. Bộ não Claude dùng tai
  tốt nhất đang có.
- **`chatgpt.com/backend-api/transcribe`**: Cloudflare chặn (403 challenge). Không lách.
- **Gemini qua agy**: chính xác nhất nhưng 7 đến 17 giây mỗi câu, không hợp trò chuyện.
- **`SpeechRecognition.phrases` của Chrome**: bản ổn định báo `phrases-not-supported`.

## 3. PR A (0.65.15): tai dạng tải lên

- `server/voice_ear.py`: `select_ear(cfg, brain_provider)` chọn tai từ khoá `voice.ear` =
  auto | groq | off. Auto: tai cùng hãng với bộ não chính, rồi tai xếp hạng cao nhất đang dùng
  được (`RANKING`), không có thì rỗng (chữ trình duyệt như trước). Khoá cũ `stt_provider`:
  "groq" vẫn là đã chọn tay, "browser" bị bỏ qua vì nút Lưu luôn gửi kèm nó. CỐ Ý không đặt
  mặc định cho `ear` trong config.py, để còn phân biệt được hai trường hợp đó.
- `transcribe_upload`: thân cũ của `/stt` (Groq, lọc câu bịa, sửa tên trợ lý, đối chiếu nháp),
  thêm từ mồi gồm tên các kết nối MCP. Tên MCP chỉ đi vào prompt Whisper, KHÔNG vào lớp sửa mờ
  `nghe_sua.sua`.
- `GET /voice/ear` (nhẹ, không hỏi mạng) cho dashboard; `/voice/options` trả thêm `ear` và
  `ear_choices` cho trang Cài đặt.
- `voice.js`, ba chỗ khiến câu không tới tai:
  - lượt ĐẦU sau khi tải trang: chờ luồng mic rồi mới mở nhận dạng, không thì bộ ghi bắt đầu sau
    Web Speech và câu bị coi là thiếu tiếng; nợ dừng `_stopPending` hạ ở `startListening` chứ
    không ở `_moNhanDang`, để lệnh dừng trong lúc chờ vẫn có hiệu lực;
  - rào chú ý: câu bị chặn mà mở đầu GẦN GIỐNG tên gọi ("David ơi", `voice-attention.js`
    `wakeCandidate`) được đưa cho tai nghe lại rồi xét lại trên chữ tai; tiếng ồn thường vẫn bị
    chặn trước khi tải lên;
  - chế độ tự nhiên: `commitWithEar` tách bản ghi ra TRƯỚC khi huỷ phiên nhận dạng.
- Điện thoại vẫn chưa có tai (máy chỉ cho một đường thu mic): để cho bước Live / song công.

## 4. Thử nhanh tai ChatGPT realtime (code bỏ đi, 01/10)

Đường: trình duyệt dựng `RTCPeerConnection` (transceiver audio sendrecv + kênh `oai-events`),
gửi SDP offer cho server; server gọi `codex app-server` (JSON-RPC qua stdio, `initialize` với
`capabilities.experimentalApi = true`) `thread/start` (ephemeral, cwd thư mục tạm rỗng, sandbox
read-only, approvalPolicy never) rồi `thread/realtime/start` (`version: "v3"`, `outputModality:
"audio"`, `transport: {type: "webrtc", sdp}`), nhận answer qua thông báo `thread/realtime/sdp`.
Âm thanh đi THẲNG trình duyệt tới OpenAI. Javis không đọc token: app-server tự lo đăng nhập.

Kết quả (Codex 0.153.4 và 0.159.3, gói ChatGPT, máy Windows):
- Một cuộc gọi nghe liền 9 câu trong 78 giây. Chữ cuối của mỗi câu về **0,46 giây** (trung vị,
  chậm nhất 0,66 giây) sau khi nói xong; chữ đầu khoảng 1,6 giây sau khi bắt đầu nói.
- Offer tới answer 1,2 đến 2,2 giây; phiên thứ hai trên cùng tiến trình mở thread mới trong 0,1 giây.
- Với `clientManagedHandoffs: true`, `includeStartupContext: false`, `delegationAckFiller: false`
  và prompt "chỉ chép lời": không sinh `turn/started`, không có chữ role assistant.
- Kênh dữ liệu `oai-events` phía trình duyệt TỰ nhận `input_transcript.added` (từng mẩu chữ),
  không cần server chuyển. Phiên v3 là một dòng liền, không chia câu: Javis tự chia theo thời gian.
- `transcript/done` cho role user thường không tới: lấy chữ từ các delta.
- **Codex trước 0.159 phải bật cờ**: `realtime_conversation` là "under development", mặc định tắt
  (0.147 và 0.153 báo "thread does not support realtime conversation"). Chạy app-server với
  `-c features.realtime_conversation=true` thì 0.153.4 (bản Docker đang ghim) chạy được. Từ 0.159
  cờ này đã "stable" và bật sẵn.
- `transport: websocket` cần API key; `outputModality: "text"` cần realtime v2, mà gói ChatGPT
  chỉ cho v1 hoặc v3. Dùng lại một thread cho nhiều `realtime/start` thì ICE hỏng: mỗi phiên mic
  một thread mới.

Bẫy khi dựng lại bộ thử: Chrome headless hỏng vì đường dẫn hồ sơ quá dài (MAX_PATH), nên để hồ sơ
và file âm thanh giả ở thư mục tạm ngắn; trên Windows `allow_reuse_address` cho nhiều tiến trình
cùng nghe một cổng, và một tiến trình lạ đã nuốt yêu cầu của Chrome, nên tắt nó đi.

## 5. Hướng tiếp theo (chủ dự án chốt 01/10)

Thay vì bịt miệng model realtime làm tai, cho nó NÓI: thành "Live qua gói ChatGPT" đứng cạnh Live
qua API key, handoff chuyển cho bộ não Javis (khuôn ủy nhiệm đã có trong `GPTLive` ở
`voice_live.py`). Tai dạng tải lên của PR A thành phương án dự phòng và là phần nhận dạng phía
server cho bước song công. Giá phải trả: giọng và tính cách lớp ngoài là của OpenAI, API thử
nghiệm, ăn hạn mức Codex nhiều hơn.

Việc kế: thử nhanh mở rộng, kiểm thêm tiếng Việt khi model nói, thời gian tới tiếng đầu, ngắt
lời, handoff do client quản lý có chuyển được sang bộ não Javis không (sự kiện nào báo, trả kết
quả bằng `appendText` hay `appendSpeech`), và phiên 15 phút. Gác lại phần tối ưu chỉ phục vụ kiểu
nói rồi chờ (rào chờ chữ lắng 1,5 giây của kế hoạch tai cũ).
