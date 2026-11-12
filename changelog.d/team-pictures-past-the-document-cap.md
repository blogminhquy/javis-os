---
bump: patch
title: A team keeps taking pictures after its document list is full
---
## vi
### Sửa lỗi
- **Team không còn chặn gửi ảnh sau một thời gian dùng.** Mỗi team giữ tối đa 50 tài liệu, và mỗi ảnh gửi vào team chiếm hai chỗ (ảnh và bản mô tả ảnh cho cộng sự đọc). Sau khoảng 25 lần gửi ảnh là đầy, và từ đó file gửi thêm bị bỏ đi mà không báo gì. Giờ khi đầy, ảnh cũ nhất và bản mô tả của nó rời danh sách tài liệu để nhường chỗ cho ảnh mới. File vẫn còn trên máy và tin nhắn vẫn còn trong chat.
- **Tài liệu bạn tự gắn không bao giờ tự rời danh sách.** Bảng giá, hợp đồng, file PDF và bản chữ của nó vẫn giữ nguyên.
- **File không vào được team thì có báo.** Khi danh sách đã đầy toàn tài liệu bạn tự gắn, Javis nói rõ lý do và chỉ chỗ gỡ bớt, thay vì im lặng bỏ file.
### Cải thiện
- **Lần mở đầu tiên của một team dài sau khi Javis khởi động lại không còn làm các thao tác khác chờ.** Trong lúc Javis đọc lại lịch sử để dựng mục Tài liệu, tải tin nhắn vẫn nhanh như thường.

## en
### Fixed
- **A team no longer stops taking pictures after a while.** A team holds at most 50 documents, and every picture sent in a team takes two places (the picture and the description written for the assistants). The list was full after about 25 picture messages, and from then on files were dropped without a word. Now, when the list is full, the oldest picture and its description leave the list to let the new one in. The file stays on disk and the message stays in the chat.
- **Documents you attached yourself never leave by themselves.** A price list, a contract, a PDF and its text copy stay.
- **A file that cannot get into the team is said.** When the list is full of documents you attached, Javis gives the reason and where to remove some, instead of dropping the file in silence.
### Improved
- **The first open of a long team after Javis restarts no longer makes everything else wait.** While Javis reads the history again to build the Documents list, loading messages stays as fast as usual.
