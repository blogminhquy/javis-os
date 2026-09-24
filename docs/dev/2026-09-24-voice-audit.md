# Audit giọng nói Javis OS, 24/09/2026

## Phạm vi và mức độ xác nhận

Audit mã nguồn, chạy callback thật trong VM trình duyệt giả lập, kiểm tra provider bằng khung giao thức giả lập và chạy handler làn nhanh thật với SQLite tạm. Không thu mic của chủ dự án, không gọi API giọng nói trả phí, không lấy hội thoại cá nhân làm dữ liệu thử.

Các lỗi bên dưới đã có tình huống tái hiện xác định. Đây là các đường gây mất/sửa lời có thật trong mã; chưa có audio và trace của cuộc gọi được báo để kết luận đường nào đã xảy ra trong chính cuộc gọi đó.

## Bản đồ luồng

| Chế độ | Thu và nhận dạng | Ai chốt lượt | Ngôn ngữ | Hậu xử lý và lưu |
|---|---|---|---|---|
| Standard | Web Speech; máy tính có thể ghi MediaRecorder song song để gửi `/stt` Groq | `voice.js` gom interim/final và phiên tự mở lại; `VoiceTurn.delayFor` quyết định khoảng im lặng, trần 30 giây; iOS dùng điểm kết thúc của WebKit | `javis.recLang` mặc định `vi-VN`; Web Speech cần một locale cụ thể. Groq nhận ISO từ route `/stt`; lựa chọn `auto` bỏ language hint | `nghe_sua.sua` sửa có giới hạn; `sendMessage` gửi cùng nội dung hiển thị; SessionStore lưu user trước `run_turn`; phản hồi đi chunker → TTS → lịch sử |
| Fast | Cùng đường thu/STT như Standard | Cùng bộ chốt trình duyệt | Cùng cấu hình nhận dạng; prompt làn nhanh ưu tiên Việt khi âm thanh mơ hồ và cho đổi ngôn ngữ khi có chủ ý | Local correction → lưu user → `run_voice_turn` → kiểm tra `JAVIS_NGHE` → phản hồi/UI/việc nền. Bản sửa mất nghĩa bị từ chối và dùng câu gốc qua bộ não chính. `JAVIS_BO_QUA` là quyết định bỏ cả lượt, có kiểm tra nội dung tin trước khi xóa |
| Live Gemini/OpenAI Realtime/OpenAI GPT-Live | getUserMedia → Web Audio PCM16 16 kHz → `/ws/voice-live` → provider; phát PCM16 24 kHz | VAD/điểm kết thúc của provider; không dùng timer Web Speech | Dashboard gửi `lang`; mặc định `vi-VN`, auto là chủ động. OpenAI dùng language ISO cho input transcription; cả ba nhận chỉ dẫn ngôn ngữ trong system prompt | Adapter chuyển transcript provider → event; server lưu user transcript final, dashboard lưu bản tương ứng. Gemini input transcription được giữ theo từng segment độc lập với lượt model |

Các file điều phối: `dashboard/voice.js`, `voice-turn.js`, `voice-chunker.js`, `voice-live.js`, `app.js`; `server/stt.py`, `nghe_sua.py`, `voice_brain.py`, `voice_live.py`, `sessions.py`, các route trong `main.py`.

### Thu/phát và ngắt lời

- Standard/Fast: trước khi TTS phát, abort nhận dạng; Web Speech tự thu bằng stream riêng nên echo cancellation của getUserMedia không bảo vệ được đường đó. Bộ đo mức âm thử hạ tiếng loa để phân biệt vọng và tiếng người, rồi mới mở lại nhận dạng. Các ngưỡng âm học hiện có chưa được hiệu chỉnh bằng audio thật trong đợt này.
- Mobile Standard/Fast giữ một đường thu khi đang nghe, tránh tranh mic giữa Web Speech và getUserMedia. Vì vậy Groq song song không được hứa là sẽ chạy trên mọi lượt điện thoại; khi không có bản thu đầy đủ thì dùng Web Speech.
- Server TTS: Edge streaming, OpenAI/ElevenLabs có fallback Edge; browser speechSynthesis là đường dự phòng. Chunker gom câu để tránh đọc từng vài chữ. Live có hàng đợi audio riêng và xử lý interruption từ provider.
- AudioContext thường của `JavisVoice` được dùng lại trong đời trang để phục vụ output/unlock; hủy nghe nhả input source/track/recorder/timer. Live đóng AudioContext và socket khi dừng. Không coi AudioContext dùng lại là một stream mic còn mở.

## Phát hiện và bản sửa

Tham chiếu dòng theo bản sửa này; tên hàm là mốc ổn định khi file thay đổi.

| Mức | Vị trí | Kích hoạt và bằng chứng | Sửa |
|---|---|---|---|
| P1 | `dashboard/voice.js`, `_startRecorder`/`_stopRecorder` khoảng dòng 177 | `stop()` giao `dataavailable` cuối sau khi mảng chung bị đổi: `head + tail` chỉ còn `head`; chunk cuối recorder A còn có thể lọt vào B | Mỗi recorder giữ mảng chunk riêng đến `onstop`; test head/tail và hai recorder chồng thời gian |
| P1 | `dashboard/voice.js`, `_quaStt` khoảng dòng 207 | Recorder có stream sau lúc SpeechRecognition đã bắt đầu, nên Groq chỉ có đuôi câu. Quy tắc bản dài hơn không chứng minh đúng/sai | Ghi nhận thời điểm bắt đầu thu; chỉ upload khi bản thu bao phủ lượt. Groq được phép sửa thành câu ngắn nếu audio đầy đủ; lỗi/timeout dùng bản trình duyệt |
| P1 | `dashboard/voice.js`, `_quaStt`/`cancelListening` | Lượt B xong STT trước A; hoặc A trả về sau khi đã đổi chat | Xếp thứ tự giao kết quả, AbortController và epoch vô hiệu hóa kết quả cũ; snapshot language trước await |
| P1 | `dashboard/voice.js`, `_muteRecognition`/`onend` | Chữ `_committed` cũ còn sau abort để phát TTS; result trễ sống sót khi loa đã dừng | Xóa mọi phần câu khi hủy, bỏ result đã bị hủy, trả nợ abort lúc recognition đang mở; chặn start trùng và dọn timer cuối lượt |
| P1 | `dashboard/app.js`, `tatRanhTay`, `guiTinDutMang`, `sendMessage` | Câu chen ngang ở chat A nằm trong timer 5 giây rồi gửi vào chat B; tương tự callback chờ reconnect/upload | Hủy hàng đợi và tăng epoch khi rời/tắt phiên; callback đã hẹn kiểm tra epoch trước khi gửi |
| P1 | `server/main.py`, `run_voice_turn` khoảng dòng 13508; `voice_brain.py:160` | Model trả `JAVIS_NGHE: Javis` cho câu đầy đủ, đổi phủ định/số hoặc marker đến muộn. Trước đây thay DB rồi có thể thực hiện UI theo câu hỏng | Chỉ nhận sửa chính tả có căn cứ; giữ câu gốc/context, chặn hành động và fallback khi sửa phá nghĩa hoặc thiếu marker. Thiếu marker đầu thì giữ lời đáp đến khi kiểm tra xong |
| P1 | `server/sessions.py:556`; `main.py`, cửa tạp âm | Sửa/xóa tin cuối mà không kiểm tra nó còn là tin của lượt đang xử lý | Replace/pop so khớp nội dung kỳ vọng trong giao dịch. Khung `user_text` có ID lượt; UI kiểm tra ID và raw, không chọn nhầm bong bóng nháp |
| P2 | `server/nghe_sua.py`, `sua` khoảng dòng 211 | Tên gần âm đổi nhầm “gia vị”, email, đường dẫn hoặc ngữ cảnh giao diện thành tên riêng | Bảo vệ từ lệnh/phủ định và literal; tên gần âm cần dấu hiệu gọi tên; không sửa khối context |
| P1 | `dashboard/voice-live.js`, `start` khoảng dòng 112 | Tắt lúc chờ quyền mic/kết nối, mở lại rồi close/error của socket cũ tác động phiên mới; timeout cũ vẫn báo start thành công | Generation sở hữu callback/stream/socket, timeout là thất bại có cleanup; Live không phụ thuộc SpeechRecognition có sẵn |
| P1 | `server/voice_live.py`, `GeminiLive` khoảng dòng 264 | Gửi PCM trước `setupComplete`; inputTranscription có thể đến sau model turnComplete, không có trường `finished` được tài liệu hóa | Đợi setup ack có timeout, giữ event đầu; lưu segment input độc lập với model turn, provisional preview không lưu. Không suy diễn ranh giới câu từ turnComplete của model |
| P2 | `dashboard/voice-live.js`, `playedMs` khoảng dòng 81 | Tính cả khoảng im/buffering vào số ms đã phát, hoặc reset trước khi nhận interruption muộn | Đếm thời gian của audio đã lên lịch thực sự; giữ mốc đến lượt audio mới |
| P2 | `server/voice_live.py:95`, `/ws/voice-live` | Chọn ngôn ngữ ở dashboard chưa đi đến Live; OpenAI transcription thiếu language hint | Truyền locale, chuẩn hóa ISO khi provider yêu cầu; system language policy cho Gemini/GPT-Live/Realtime; vẫn hỗ trợ auto và đổi ngôn ngữ chủ động |
| P2 | `server/main.py`, `server/voice_privacy.py` | stderr in bản chép và lý do model; Uvicorn access log mặc định có `/tts?text=...` | Bỏ log bản chép/lý do tự do ở cửa sửa và tạp âm; lọc query TTS khỏi access log của app |

## Kiểm chứng các sửa cũ và tác dụng phụ

- Giữ `_committed` qua phiên tự mở lại vẫn cần thiết và được giữ. Test mô phỏng Android cumulative final, final đổi hoa/dấu câu, iOS interim-only, và restart chưa có result đều còn chạy.
- Bỏ `chonBanNghe` dựa vào độ dài. Test audio đầy đủ cho phép Groq trả “Không.” thay bản trình duyệt lặp dài; audio bắt đầu muộn không được thay câu đầy đủ bằng “Javis”. Đây là kiểm tra độ đầy đủ của nguồn thu, không xác nhận chất lượng STT.
- Thời gian đợi riêng tiếng gọi “Javis” và lời chưa xong vẫn dùng VoiceTurn. `khoan`, `đợi chút`, `thôi`, `dừng lại` dùng bài kiểm tra đạo diễn sẵn có. Không tăng đồng loạt độ trễ mọi câu.
- Thêm trạng thái “đang nhận dạng” trong khi đợi STT; giữ chữ nháp đến lúc giao kết quả. Vòng tự mở mic không bắt đầu lượt mới trong khi còn đang nhận dạng.
- Bảo vệ JAVIS_NGHE cố ý chặt: một bản sửa hợp lý nhưng thay nhiều từ có thể bị từ chối; khi đó câu gốc đi bộ não chính, có thể chậm hơn. Nó không chứng minh bản gốc đúng âm thanh.
- Gemini schema không bảo đảm ranh giới phát ngôn cho các model cũ: nếu provider phát từng mẩu ngắn, UI có thể có nhiều bong bóng ngắn. Bản sửa ưu tiên không mất segment; chưa tuyên bố gom đúng một bong bóng cho mọi câu/model.
- Lọc outro trong `stt.loc_ao_giac` và quyết định bỏ tạp âm của model vẫn có nguy cơ loại nhầm lời trích dẫn/tiếng thật. Bộ test có ca marketing, URL và ngữ cảnh nhưng không thay thế dữ liệu audio. Không mở rộng thêm blacklist trong đợt này.

## Bằng chứng kiểm thử

Các bài mới chạy logic thật với sự kiện/network giả lập:

- `test_voice_capture_lifecycle.js`: chunk cuối, recorder xen nhau, coverage, STT sai thứ tự, language snapshot, timeout/offline, abort/TTS, start lặp, quyền mic đến muộn, timer.
- `test_voice_app_session.js`: đổi chat, bản sửa cũ, hàng đợi chen ngang/reconnect, xóa tạp âm đúng bong bóng.
- `test_voice_live_lifecycle.js`: mic/socket trễ, stop/start, timeout, audio scheduling/interruption.
- `test_voice_transcript_integrity.py`: sửa tên đúng/nguy hiểm, câu lệnh/phủ định/số/identifier, context.
- `test_voice_turn_integrity.py`: chạy handler production được trích bằng AST + SQLite; bản sửa phá nghĩa trước/sau lời đáp, thiếu marker, xóa/sửa nhầm tin mới, context trong DB khác phần speech hiển thị.
- `test_voice_live_transcription.py`: 10 ca giao thức bao gồm transcript sau turnComplete, preview riêng, setup ack/timeout/rejection, không mất event đầu.
- `test_voice_live_language.py`: payload language và prompt thực tế, locale/auto/đầu vào không hợp lệ.
- `test_voice_privacy.py`: log TTS bỏ query, giữ method/status, không thay log route khác.

Các ca lỗi recorder, thứ tự STT, hủy phiên, sửa phá nghĩa, xóa nhầm tin, gửi hàng đợi sang chat khác, Gemini và local correction đã quan sát đỏ trước sửa rồi xanh sau sửa. Các source assertions cũ phụ thuộc cách viết đã được chuyển sang kiểm tra hành vi khi phù hợp.

Lệnh xác minh từ checkout phát hành:

```text
python tests/run.py voice micro nghe_sua stt tts -v
python tests/run.py --js -v
python -m compileall -q server system/plugins
cd server
python -c "import main; print(len(main.app.routes))"
```

23/23 nhóm voice/STT/TTS đạt ở vòng tích hợp đầu; compile và import main đạt. Toàn bộ 134/134 file kiểm tra JS đạt sau sửa assertions/epoch. Python toàn repo ở checkout làm việc Windows có lỗi không thuộc giọng nói (fake executable Unix/đường macOS, và bộ quét đi vào thư mục state/brain cá nhân); lượt đó được dừng để chuyển sang checkout sạch. Không báo toàn bộ Python local đạt. CI Linux và GHCR của chính commit phát hành được kiểm tra riêng sau push; liên kết và kết luận được gửi trong báo cáo hoàn tất.

Không có số WER, độ trễ mic thật hoặc tỷ lệ ngắt sai để báo cáo trong đợt này. Thời gian unit test không phải độ trễ đàm thoại.

## Ma trận thử mic thật còn lại

Thử Standard, Fast và Live đã cấu hình key, trên Chrome/Edge desktop, Android Chrome và iPhone Safari; ghi phiên bản trình duyệt/model và dùng cùng bộ câu. Mỗi ca lặp 10 lần, đo theo thiết bị/chế độ riêng, không gộp thành số trung bình thiếu ngữ cảnh.

1. “Javis, đưa anh về màn hình trò chuyện nhé.” So chữ tạm, bong bóng chốt và lịch sử sau tải lại; không được chỉ còn “Javis”.
2. Gọi “Javis”, ngừng 1 giây rồi nói tiếp; thêm ca ngừng dài hơn ngưỡng chờ để phân biệt hết lượt đúng và chốt sớm.
3. “Mở OpenRouter rồi kiểm tra API của Gemini.” Thêm tên file/email và “đừng mở”, con số, phần trăm để bắt sửa sai nghĩa.
4. Câu ngắn/dài, nhỏ tiếng, ngập ngừng, kết bằng dấu phẩy; “khoan”, “đợi chút”, “thôi”, “dừng lại”.
5. Tai nghe và loa ngoài ở các mức âm lượng; im lặng, ho, TV, hai người nói; ngắt Javis lúc đang đọc.
6. Bật/tắt mic nhanh, đổi chat/chế độ/ngôn ngữ, mất mạng lúc gửi/STT/Live, từ chối rồi cấp lại quyền, đổi thiết bị âm thanh, đưa tab nền rồi quay lại.

Đo `t_nói_xong → t_transcript_chốt → t_âm_đầu`, số từ thiếu/lặp so câu chuẩn, số lượt chốt sớm, sai ngôn ngữ, ngắt nhầm và mic không nhả. Chỉ lưu thống kê/ID ca tổng hợp theo mặc định. Audio hoặc transcript thử nghiệm chỉ thu khi người thử chủ động cho phép; không đưa hội thoại cá nhân vào log.

## Giới hạn vận hành

- `auto` có thể vẫn đoán sai trên tiếng ngắn/nhiễu; ưu tiên chọn Tiếng Việt khi chủ yếu nói tiếng Việt. Prompt ngôn ngữ không phải language lock tuyệt đối của model.
- Chưa kiểm chứng tự phục hồi khi rút mic, quyền hệ điều hành thay đổi hoặc tab bị hệ điều hành đóng băng; có đường lỗi/tắt/mở lại nhưng phải thử thiết bị thật.
- Filter log áp dụng cho Uvicorn của app. Reverse proxy do người dùng cấu hình vẫn có thể ghi query `/tts`; cấu hình proxy cần bỏ query tại route này. Không có bản ghi audio mới được thêm vào log.
- Phát hành GitHub/GHCR không có nghĩa máy đang chạy của người dùng đã kéo image mới.

## Tài liệu giao thức đã đối chiếu

- [Gemini Live WebSocket API](https://ai.google.dev/api/live?hl=en): setupComplete; inputTranscription độc lập thứ tự với model; schema text/languageCode.
- [Gemini Live language guidance](https://ai.google.dev/gemini-api/docs/live-api/best-practices#specify-language): chỉ dẫn ngôn ngữ cho native audio.
- [OpenAI Realtime client events](https://developers.openai.com/api/reference/resources/realtime/client-events): language của audio input transcription.
