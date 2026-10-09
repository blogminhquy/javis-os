# Resonance A3: học từ phản hồi, cách dùng, nâng cấp, quay về

Thiết kế: [2026-10-09-resonance-a3-feedback-learning-design.md](../superpowers/specs/2026-10-09-resonance-a3-feedback-learning-design.md). Biên bản kiểm: [resonance-a3-verification.md](resonance-a3-verification.md).

## Hai làn học

**Làn trình bày (P):**
- Dưới mỗi tin báo của trợ lý (tin do Javis gửi về khung chat, có thẻ mục tiêu) có hàng **Tin này thế nào?** gồm hai nút 👍 Hữu ích và 👎 Chưa ổn.
- Bấm 👎 thì hiện ba lý do: Dài quá, Báo nhiều quá, Khó hiểu. Bấm lại đúng nút đang sáng là rút phản hồi.
- Đủ hai tin khác nhau cùng lý do thì Javis **đề xuất**: báo gọn tin "đã đạt" và tin cập nhật định kỳ, hoặc không rung chuông cho tin cập nhật định kỳ.
- Đề xuất nằm ở mục **Bài học** trên trang trợ lý (trang Cộng sự, cột phải), kèm câu cũ và câu mới của cùng một tin. Bạn bấm Áp dụng hay Bỏ qua. Không ai quyết thì đề xuất hết hạn sau 14 ngày và giữ cách cũ.
- Làn này không bao giờ gọi model.

**Làn cách làm (M):**
- Khi hai lượt liên tiếp không tiến thêm theo tiêu chí Javis tự chấm được (bế tắc của A2), Javis có thể thử cách làm "Rà đủ ý trước khi trả" so với cách cũ, trên hai tình huống, bằng đúng phép thử M5.
- Chỉ thử khi đủ cả hai điều kiện:
  - **ngân sách trọn vòng**: phép thử 4 lượt, cộng một lượt làm lại sản phẩm được giữ sẵn, cộng lượt dự phòng;
  - **có tình huống đối chứng hợp lệ**: một cách hiểu trước của cùng mục tiêu, cùng bộ tiêu chí, lời người dùng khác thật.
- **Mục tiêu mặc định 6 lượt không bao giờ thử**: bế tắc sau 3 lượt thì cần hạn mức ít nhất 9.
- Cách mới thắng thì áp dụng cho đúng cách hiểu hiện tại, rồi làm lại sản phẩm một lần bằng lượt đã giữ, và báo kết quả. Thua hay chưa rõ thì giữ cách cũ.

## Những điều không bao giờ xảy ra

- Phản hồi không làm mục tiêu đạt, không đổi tiêu chí, không mở lượt model, không đổi lịch thức.
- Phản hồi không ghi vào file trợ lý, công tắc, version hay hạn mức.
- Tin bắt buộc luôn đầy đủ và luôn rung chuông, gồm:
  - cảnh báo: guard, mất giám sát, qua hạn chót, xung đột ghi file, lỗi, bị chặn;
  - tin cần bạn làm gì: chờ xác nhận, bế tắc, khám phá xong;
  - tin đổi cách làm.
- Lời chat thường không nhận phản hồi; chỉ tin báo có biên nhận của Javis mới nhận.

## Thu hồi

- **Bài học trình bày:** bấm Thu hồi ở mục Bài học, tin kế tiếp quay về cách mặc định.
- **Cách làm đã học:** bấm Quay lại cách cũ trên thẻ mục tiêu, hoặc Thu hồi ở mục Bài học. Lượt làm sản phẩm còn giữ sẵn được trả lại cùng lúc.
- Sửa cách hiểu (revision mới) thì cách làm vừa học tự hết hiệu lực, vì nó chỉ được kiểm cho cách hiểu cũ.

## Nâng cấp từ 0.88.x

- Lần đầu 0.89 mở kho `resonance.sqlite3` có từ trước: chép bản sao `resonance.sqlite3.pre-a3.bak`, rồi thêm năm bảng `reactions`, `reaction_log`, `lessons`, `lesson_events`, `call_holds`. Bảng cũ không đổi cột.
- Mỗi lần mở kho, Javis đối soát lượt giữ: dựng lại lý do làm sản phẩm nếu bị mất, trả lượt không còn hợp lệ, đúng một lần.

## Quay về 0.88.x

- Bản cũ bỏ qua các bảng A3. Tin báo trở lại đầy đủ và rung chuông.
- Cách làm đã áp dụng vẫn nằm ở cột M5 mà 0.88 hiểu, vẫn chỉ cho đúng cách hiểu đó.
- Lượt giữ còn `held` vẫn tính trong `calls_used` (dư một lượt, phía an toàn). Bản cũ coi lý do làm sản phẩm là lý do chỉ kiểm: chốt nó, không gọi model.
- Nâng lại 0.89: đối soát khi mở kho dựng lại lý do (hay trả lượt nếu trong lúc đó bản cũ đã huỷ, sửa cách hiểu hoặc quay lại cách cũ). Chu trình này có test chạy mã 0.88.1 thật (`tests/python/test_resonance_a3_rollback.py`).

## Khôi phục bằng bản sao trước nâng cấp

Dừng Javis, đổi tên `resonance.sqlite3` hiện tại, chép `resonance.sqlite3.pre-a3.bak` thành `resonance.sqlite3`, rồi chạy bản 0.88.x. Mọi phản hồi và bài học sau lúc nâng cấp sẽ mất; mục tiêu và lịch A2 giữ như lúc chép.
