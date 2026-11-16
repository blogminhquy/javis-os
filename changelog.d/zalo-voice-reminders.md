---
bump: minor
title: Zalo reminders that tag you, ring and speak the note
---
## vi
### Thêm mới
- **Nhắc hẹn qua Zalo có tag tên, gọi ảo và tin thoại.** Anh ra lệnh trên Zalo, tới giờ Javis tag tên anh, gửi dòng "Javis đang gọi", một tin thoại đọc nội dung cần nhớ, tin chữ, và một lịch nhắc hiện ngay trong khung chat Zalo. Lặp theo mức nhẹ, vừa hoặc gắt, hay đúng số lần anh muốn.
- **Javis học cách anh viết tiếng Việt.** "ko", "dc", "7h", "a Thế" được hiểu và đọc đúng là "không", "được", "7 giờ", "anh Thế". Anh sửa một từ Javis hiểu sai thì Javis nhớ luôn cho các lần sau.
- **Tên chính thức là tên người đó tự đặt cho mình trên Zalo**, không phải biệt danh anh lưu trong danh bạ.
- Zalo chưa có API gọi thoại thật, nên cuộc gọi là gọi ảo: dòng gọi có tag cùng tin thoại.
- **Tin thoại phát ngay trong khung chat Zalo**, không còn là thẻ file mp3. Javis tự gắn lại công cụ gửi thoại sau mỗi lần cập nhật.

- **Giọng đọc offline cho lời nhắc Zalo** (Piper, tiếng Việt, Anh, Trung): file giọng nằm trong thư mục state nên không mất khi cập nhật, đọc được cả khi không có mạng. Thiếu file giọng thì dùng giọng trực tuyến như cũ.

- Giọng offline đọc chậm hơn 20% và đều âm lượng giữa các ngôn ngữ; đổi mức chậm bằng biến `JAVIS_VOICE_SPEED`.

### Sửa lỗi
- Lời nhắc có đọc to không còn mất giọng khi dịch vụ giọng đọc của Microsoft từ chối máy chủ: Javis thử lại bằng tiến trình mới, rồi bằng giọng Google.

## en
### Added
- **Zalo reminders that tag you, ring and speak.** Book something by Zalo and, at the time, Javis tags your name, sends a "Javis is calling" line, a voice message of what to remember, the written note, and a reminder entry inside the Zalo chat. Repeats at a light, medium or urgent level, or an exact number of times.
- **Javis learns how you write Vietnamese.** Chat shorthand such as "ko", "dc", "7h" or a one-letter "a" before a name is read and spoken in full. Correct a word Javis misread and it remembers for next time.
- **The official name is the one a person set for themselves on Zalo**, not the nickname you saved for them.
- Zalo has no real voice-call API, so the call is a virtual one: a tagged call line plus the voice message.
- **The voice message plays inside the Zalo chat** instead of arriving as an mp3 file card. Javis re-adds the voice tool after every update.

- **Offline voices for Zalo reminders** (Piper, Vietnamese, English, Chinese): the voice files live in the state folder so an update keeps them, and they speak with no internet. Without the files the online voice is used as before.

- Offline voices speak 20% slower with the same loudness across languages; the pace is set with `JAVIS_VOICE_SPEED`.

### Fixed
- Spoken reminders no longer lose their voice when the Microsoft speech service refuses the server: Javis retries from a fresh process, then with Google's voice.
