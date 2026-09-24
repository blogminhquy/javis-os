# Chữ đã chốt và giọng mặc định (0.64.32)

## Yêu cầu
- Câu đã hiện lúc người dùng kết thúc lượt không bị final đến muộn, STT phụ hoặc AI sửa âm thầm khi vào chat/lịch sử.
- Giữ đường nghe miễn phí và chế độ tập trung đã phát hành ở 0.64.28.
- Chủ dự án xác nhận giọng nữ yêu thích là Emma trong cài đặt. Đặt Emma Multilingual làm mặc định cho bản cài mới/trình duyệt chưa lưu giọng, giữ lựa chọn đã lưu.
- Không đổi nhà cung cấp hoặc chuyển sang giọng thiết bị khi TTS lỗi.

## Thay đổi
- Chốt bản hiển thị tại stop; nếu chưa có kết quả nào, vẫn nhận final đầu tiên. Khi đang nói, kết quả tạm vẫn cập nhật bình thường.
- Dashboard khóa transcript qua STT phụ; Groq chỉ đối chiếu và báo khi khác. Cài đặt giải thích rõ hành vi này. Không tự gửi lại bằng câu gợi ý.
- Bỏ sửa hotword trước khi lưu WebSocket chat. Làn nhanh chỉ chấp nhận marker nguyên văn; marker sửa câu thì chuyển bộ não chính với nguyên bản, trước khi đọc/hành động.
- Nhà cung cấp TTS lỗi trả 502; client thử lại cùng giọng một lần rồi báo lỗi. Epoch ngăn callback âm thanh cũ chạm lượt mới.
- Emma mặc định tại voice.js, app.js, /tts, /config, env.example và thứ tự ô chọn. Live realtime vẫn dùng giọng riêng của nhà cung cấp.

## Kiểm chứng và giới hạn
- Mô phỏng Android: draft “Em phải trả lời vâng”, stop, late final “Em phải trở thành Vân”: bản cũ sai, bản mới giữ draft.
- Thêm ca stop trước kết quả đầu, AI sửa tên, STT phụ đổi câu, TTS fallback, callback audio cũ.
- Kiểm thử tự động không đo độ chính xác nghe trong phòng thật hay chất giọng trên tablet. Bản nhận dạng ban đầu vẫn có thể sai; không có bản ghi âm để khôi phục chính xác các câu lịch sử.
- Không thay toàn bộ nhận dạng trình duyệt bằng API trả phí; không hứa phân biệt người nói với TV bằng chữ.

## Hồi phục 0.64.38
- Gỡ lớp sửa hotword ở cửa WebSocket là quá tay: nó là so khớp âm tất định (`nghe_sua.sua`), không phải AI hay STT phụ, và đã có rào cho số, phủ định, lệnh, người thứ ba. Gỡ đi thì "Javis" nghe thành "David" đi thẳng vào bộ não, cộng với lời dặn "không tự đoán tên người", Javis trả lời "anh nói là David".
- 0.64.38 bật lại lớp đó cho tin từ mic, chạy TRƯỚC khi lưu (không đổi lịch sử sau khi chốt), báo `user_text` kèm chữ thô nên không âm thầm. AI vẫn không được viết lại câu: dòng JAVIS_NGHE vẫn phải khớp nguyên văn câu đã lưu.
- Bộ não giọng được dặn lại: 'David', 'Jarvis', 'Gia vít' khi gọi mình là Javis.
- Mở rộng theo yêu cầu chủ dự án (24/09: "không chỉ David, mà nhận diện đúng ngữ cảnh"): bộ não giọng lại diễn giải cả câu ở dòng JAVIS_NGHE. Câu diễn giải chỉ được nhận khi qua `voice_brain.safe_transcript_rewrite` (ngưỡng âm 0,6, tối đa 4 tiếng một cụm, không đụng từ bảo vệ/số, từ ngắn phải khớp dài); được nhận thì thay tin lưu và bong bóng kèm chữ thô, lượt có biên nhận utterance thì giữ bản lưu. Không qua rào thì bộ não chính nhận nguyên văn; khối KÊNH HỘI THOẠI dặn nó hiểu theo ngữ cảnh.
