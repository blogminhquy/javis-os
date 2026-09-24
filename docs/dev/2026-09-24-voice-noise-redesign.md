# Thiết kế lại xử lý tiếng nền khi đàm thoại

Ngày: 24/09/2026. Đây là kết quả điều tra và các phương án ban đầu.

## Phương án đã chốt cho 0.64.28

Chủ dự án chọn giữ đường nghe miễn phí và gọi “Javis” sau lúc chờ. Triển khai theo
`2026-09-24-voice-focus-plan.md`: cửa chú ý trước khi gửi/lưu, mặc định bật độc lập với bộ
lọc chữ cũ; 20 giây không trao đổi thì chờ gọi tên, bấm tiếp tục sẽ hủy bản chép nền đang dở.
Live đóng kết nối khi chờ, dùng Web Speech gọi lại, chờ nhả mic trước khi mở Live và gửi
câu gọi kèm yêu cầu đúng một lần sau ready. Nạp lại tối đa 12 tin/8.000 ký tự gần nhất.
Trình duyệt không hỗ trợ gọi tên có nút tiếp tục. Không thêm API trả phí hay mô hình VAD.

Bỏ quyền xóa lời đã nhận dựa trên suy đoán tạp âm từ chữ. Vẫn giữ các kiểm tra chống sửa
sai ý của 0.64.27. Các phương án audio/VAD dưới đây là hướng nghiên cứu, không phải tính
năng đã cài trong 0.64.28.

Kiểm chứng tự động dùng callback trình duyệt, thời gian giả, provider giả và SQLite thật;
không dùng mic hay gọi nhà cung cấp thật. Chưa có số liệu giảm tin giả/độ chính xác âm học.
TV gọi đúng tên Javis vẫn có thể đánh thức; tiếng người chen khi cửa hội thoại mở vẫn có
thể được nhận. Web Speech có thể dùng dịch vụ của trình duyệt, không đồng nghĩa xử lý offline.

## Mục tiêu của chủ dự án

Tiếng nền không tự biến thành hội thoại; bật lọc không làm sai lời; nói nhỏ, nói tiếp, ngắt lời vẫn tự nhiên. Áp dụng Standard, Fast và Live. Người dùng báo lỗi ở cả ba; chưa có audio để xác định mức đóng góp của tiếng vọng, tiếng ồn và giọng người ở xa.

## Bằng chứng từ 0.64.27

1. `voice_brain.SYSTEM_PROMPT` yêu cầu model đoán TV/người khác từ CHỮ. `loc_tap_am` chỉ điều khiển nhánh JAVIS_BO_QUA trong làn nhanh; không nối vào xử lý audio.
2. Thử tạo setup của Gemini, OpenAI Realtime và GPT-Live với cùng cấu hình, chỉ đổi loc_tap_am True/False: cả ba payload giống hệt nhau. Đây là phép thử trực tiếp không dùng key hoặc gọi provider.
3. `dashboard/voice.js` gọi SpeechRecognition.start() không truyền luồng đã xử lý. getUserMedia với echoCancellation/noiseSuppression là luồng khác. Không thể khẳng định bật khử ồn ở luồng đó đã khử ồn cho Web Speech.
4. Standard/Fast lưu user ở `main.py` trước khi chạy run_voice_turn. Live lưu khi adapter phát transcript final; dashboard cũng recordTurn ngay. Chữ STT đang được xem là lời người dùng đã chấp nhận quá sớm.
5. OpenAI Realtime hiện chưa cấu hình noise_reduction, turn detection là server_vad mặc định. Gemini chưa cấu hình VAD theo môi trường. Chọn Live hiện tại không tự đem lại cùng hành vi của sản phẩm ChatGPT.
6. Nhãn “Lọc tạp âm” vẫn hứa cắt phần không nói với Javis, trong khi 0.64.27 đã chủ động chặn cắt mất ý. Prompt còn nói “lọc” rồi yêu cầu giữ nguyên đầy đủ. Sự không nhất quán này cần được bỏ.

Không có bằng chứng rằng model nghe đúng âm thanh rồi bật bộ lọc vật lý làm méo âm: trong đường Fast hiện tại, công tắc đó tác động suy diễn từ chữ. Đây là cơ chế có thể khiến người dùng cảm thấy nghe sai hơn; chưa đo trên audio của ca báo lỗi.

## Phân biệt ba bài toán

| Nguồn nhiễu | Cơ chế phù hợp | Giới hạn |
|---|---|---|
| Quạt, điều hòa, xe, gõ bàn | Khử ồn và phát hiện tiếng nói từ audio | Ngưỡng quá cao có thể bỏ giọng nhỏ/câu ngắn |
| Loa Javis vọng vào mic | Khử vọng với đường phát làm tham chiếu; kiểm tra ngắt lời | So khớp chữ với câu TTS không đủ, vì người dùng có thể lặp lại thật |
| TV/người khác nói | Quyết định lời có hướng tới Javis, ngữ cảnh phiên; chế độ tập trung hoặc kích hoạt chủ động | VAD phát hiện cả tiếng người trên TV. Không thể gọi VAD là nhận diện chủ giọng |

## Ba hướng thực hiện

| Hướng | Lợi ích | Đánh đổi |
|---|---|---|
| Thu âm thống nhất + STT API, giữ bộ não hiện có | Kiểm soát audio thực sự ở cả desktop/mobile; vẫn dùng gói Antigravity/Codex cho suy nghĩ | Thêm chi phí nghe; mạng ảnh hưởng độ trễ |
| Live audio trực tiếp với thiết lập đúng từng provider | Giảm các bước chuyển chữ/đọc lại; provider quản lý hội thoại audio | API riêng; khả năng lọc/endpoint/turn acceptance khác nhau giữa model |
| Nhận dạng cục bộ | Audio có thể ở thiết bị, không phí theo phút | Tải model, RAM/CPU/pin; cần benchmark tiếng Việt và thiết bị yếu |

Khuyến nghị kỹ thuật: dùng lớp thu âm chung cho hai hướng đầu, giữ Web Speech làm lựa chọn tương thích có ghi rõ giới hạn. Chưa tự đổi nhà cung cấp, bật dịch vụ trả phí hoặc tải model nặng khi chưa biết ưu tiên của chủ dự án.

## Luồng đề xuất

```text
Một stream mic
  → khử vọng / khử ồn theo thiết bị
  → phát hiện tiếng nói bằng model âm thanh + giữ đoạn đầu trong buffer
  → ứng viên phát ngôn (ID, thời gian, nguồn, bằng chứng audio)
  → kiểm tra lượt và trạng thái chú ý của cuộc trò chuyện
  → accepted / rejected / uncertain
  → chỉ accepted mới ghi lịch sử và được thực hiện hành động
```

### 1. Một nguồn audio được kiểm soát

- getUserMedia một lần cho phiên, dùng cùng stream cho bộ đo, VAD và STT. Tránh hai đường giành mic trên điện thoại.
- Dùng AudioWorklet; buffer đầu/cuối để không cắt tiếng gọi hoặc âm tiết đầu. Hủy phiên phải xóa buffer và kết quả STT cũ.
- Dùng VAD có xác suất speech thay vì chỉ ngưỡng âm lượng. Silero/ONNX là ứng viên có thể chạy ở trình duyệt; pin version và phục vụ asset cùng app, kiểm tra chi phí CPU trước khi bật mặc định.
- Thử riêng noiseSuppression/autoGainControl theo thiết bị. Không bật thêm nhiều tầng khử ồn một cách mặc định rồi cho rằng càng nhiều càng tốt.
- Với Standard/Fast, đường được kiểm soát cần STT nhận audio của Javis. Web Speech miễn phí không được hứa cùng khả năng khi browser không nhận custom audio track.

### 2. Quản lý sự chú ý và lượt nói

- Người dùng bấm mic là hành động mở cuộc trò chuyện: câu đầu không bắt buộc gọi tên. Trong cuộc trò chuyện đang diễn ra, cho nói tiếp tự nhiên.
- Sau khoảng yên lặng dài, chế độ tập trung có thể yêu cầu gọi “Javis” hoặc bấm nói lại; hiển thị rõ trạng thái. Thời gian là tham số cần đo, không chọn cứng rồi coi đã đúng.
- Không bắt gọi tên ở mọi câu. Không loại câu “ừ”, “không”, “khoan” chỉ vì ngắn.
- Giọng người nền khi cửa trò chuyện đang mở vẫn là bài toán khó: dùng tín hiệu audio/provider và xác nhận ngắn cho yêu cầu mơ hồ, không bịa nội dung để lấp chỗ nghe sai.
- Nhận diện riêng giọng chủ chưa nằm trong mặc định: đó là tính năng khác, cần mẫu giọng được cho phép và đánh giá khi nhiều người nói.

### 3. Ứng viên không phải tin nhắn chính thức

- Frontend hiển thị chữ tạm, không persist vào lịch sử ngay.
- Backend giữ ứng viên ngắn hạn với utterance_id/session_id và trạng thái. Chỉ commit một lần khi accepted; rejected không tạo tin user, không chạy tool, không đi vào bộ nhớ hoặc học.
- Lời nói chưa rõ được xử lý riêng với tiếng nền chắc chắn. Không hỏi “anh nói lại” liên tục khi phòng chỉ có tiếng quạt.
- Bỏ quyền của bộ lọc tạp âm tự viết lại câu. Việc sửa chính tả được giới hạn và phải giữ bản gốc để đối chiếu.
- Text-only classifier chỉ là tín hiệu bổ sung, không được khẳng định ai đã nói hoặc âm thanh nào thực sự có mặt.

### 4. Adapter Live riêng theo khả năng

- OpenAI Realtime: dùng noise_reduction phù hợp mic gần/xa; thử semantic_vad để giảm chốt sớm. Semantic VAD quyết định hết ý, không xác nhận đúng người nói.
- Khi cần cổng chấp nhận chặt, tách transcript và tạo response bằng cơ chế provider hỗ trợ; chỉ chặn bong bóng sau khi model đã trả lời/chạy tool là quá muộn.
- Gemini: cấu hình activity detection và endpoint có giữ đầu câu; proactivity chỉ bật cho model công bố hỗ trợ. Tài liệu loại trừ Gemini 3.1 Flash Live nên không bật đại trà.
- GPT-Live: giữ giao thức song công riêng, chỉ dùng trường được tài liệu hóa; không chép payload Realtime sang nó.
- Nếu provider không hỗ trợ kiểm soát lượt trước hành động, UI phải báo giới hạn của chế độ tập trung; không hứa cùng mức chặn cho mọi adapter.

## Kế hoạch kiểm chứng trước bật mặc định

1. Tạo baseline 0.64.27 bằng audio thử được cho phép: nói gần, nhỏ, ngắt quãng, tên tiếng Anh, câu ngắn; tiếng quạt/xe/ho; TV; người khác; tiếng loa Javis.
2. Replay cùng audio, cùng mức âm lượng và cấu hình trước/sau; test callback bổ sung chỉ chứng minh vòng đời và đúng lượt, không chứng minh chất lượng tiếng nói.
3. Đo tin giả trên mỗi 10 phút chỉ có tiếng nền; tỷ lệ bỏ sót trên bộ câu người dùng; độ trễ p50/p95; chốt sớm; ngắt nhầm; thiếu/lặp từ. Báo số mẫu và chia theo loại nhiễu.
4. Với từng chế độ, thử Chrome/Edge desktop, Android Chrome, iPhone Safari; âm thanh thật từ loa và mic cần thử vì replay không tái tạo hết đường khử vọng.
5. Điều kiện phát hành: giảm rõ tin giả mà không tăng bỏ sót giọng nhỏ/câu ngắn trong bộ thử. Chốt mục tiêu số sau baseline; không tự tuyên bố giảm 90% hoặc ngang ChatGPT khi chưa đo.
6. Có công tắc quay lại đường cũ và số liệu không chứa audio/transcript cá nhân. Rollout theo từng đường đã qua kiểm chứng, không ép cả ba cùng lúc.

## Trình tự triển khai đề xuất

- Đợt 1: sửa đúng ý nghĩa công tắc, bỏ prompt lọc mâu thuẫn; bổ sung candidate/acceptance trước persistence và đo baseline.
- Đợt 2: nguồn audio thống nhất, VAD và STT kiểm soát được cho Standard/Fast; kiểm tra desktop/mobile.
- Đợt 3: nối lớp chung với Live theo khả năng từng provider; kiểm chứng ngắt lời và tiếng nền.

Mỗi đợt chỉ phát hành sau kiểm tra liên quan, tăng phiên bản, cập nhật changelog, lên GitHub/main và xác nhận CI/GHCR theo yêu cầu đã có.

## Nguồn kỹ thuật

- OpenAI noise reduction: https://platform.openai.com/docs/api-reference/realtime?lang=javascript
- OpenAI VAD: https://developers.openai.com/api/docs/guides/realtime-vad
- Gemini activity detection/proactivity: https://ai.google.dev/gemini-api/docs/live-api/capabilities
- Silero VAD: https://github.com/snakers4/silero-vad
- VAD browser stream/buffer API: https://docs.vad.ricky0123.com/user-guide/api/
- Web Speech audioTrack và giới hạn hỗ trợ: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/start
