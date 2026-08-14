---
name: Notes
description: Lưu tin nhắn hiện tại nguyên văn vào sources/ (kèm ảnh), tự chưng cất lên wiki nếu note đáng.
description_en: "Save the current message verbatim into sources/ (images included), then distil it up to the wiki if it earns a place."
group: AI
---

# NOTES - lưu nhanh 1 note vào Second Brain (giữ nguyên văn), wiki nếu đáng

## Khi nào dùng

Kích hoạt khi người dùng gõ lệnh `/notes` (web hoặc Telegram), hoặc nói "lưu note này",
"ghi nhanh cái này vào brain". Đây là bản CHỘP NHANH: lưu nguyên văn trước, chưng cất sau
nếu đáng. Khác `ingest-source` (dành cho source đã nằm sẵn trong `sources/` và luôn distill).

Đọc schema vault (`CLAUDE.md`/`AGENTS.md` ở gốc brain) trước khi ghi.

## Nội dung note lấy từ đâu

- Phần "yêu cầu" người dùng gõ SAU `/notes` = thân note. Giữ ĐÚNG NGUYÊN VĂN, không sửa,
  không tóm tắt, không thêm bớt chữ nào.
- File/ảnh đính kèm trong CÙNG tin nhắn (đường dẫn được đưa kèm) = tài liệu của note.
- CHỈ tin nhắn hiện tại. Không kéo câu trả lời trước hay các lượt cũ vào.

## Các bước

1. Xác định thư mục brain hiện tại: `sources/`, `attachments/`, `wiki/`.
2. Đặt tên file: `sources/note-YYYY-MM-DD-HHmm-<vài-chữ-đầu-không-dấu>.md` (dùng ngày giờ thật,
   lấy qua tool datetime nếu có; slug từ ~4-6 chữ đầu của note, bỏ dấu, nối gạch ngang).
3. Ghi file source với frontmatter:
   - `type: source`
   - `source_kind: own-note`
   - `status: unprocessed`
   - `created: <YYYY-MM-DD HH:mm>`
   - `tags: [note]`
   Thân file = văn bản gốc NGUYÊN VĂN. Với ảnh đính kèm: chuyển/đảm bảo file nằm trong
   `attachments/`, nhúng `![[tên-ảnh]]` trong thân. Nếu file đã nằm sẵn trong `sources/`/
   `attachments/` do web upload thì dùng chính nó, KHÔNG nhân đôi.
4. Đánh giá đáng-wiki (cùng tiêu chí ingest-source): có khái niệm / framework / nguyên lý /
   quy trình / insight tái dùng được -> ĐÁNG. Tâm sự, việc vặt, nhắc nhất thời, danh sách mua
   đồ -> KHÔNG đáng.
5. Nếu ĐÁNG: áp phép INGEST - viết/cập nhật trang `wiki/` đủ 3 kỷ luật (mỗi claim cụ thể kèm
   `[[Nguồn]]`; phân biệt "(mục tiêu)"/"(thực tế tính đến ...)"; mâu thuẫn với trang cũ thì
   thêm `## Mâu thuẫn` + append `wiki/_open-questions.md`, KHÔNG ghi đè). Mỗi trang tự đủ ngữ
   cảnh (1-2 câu định vị đầu trang) + `aliases:` nếu có tên gọi khác. Cập nhật `wiki/index.md`
   (thêm dòng link + mô tả 1 dòng). Append `wiki/log.md`:
   `## [YYYY-MM-DD] notes | <tên note>` + nguồn/đã tạo/đã cập nhật/insight. Set source
   `status: processed`, `processed_at: <...>`, `wiki_links: [...]`.
6. Nếu KHÔNG đáng: giữ source (`status: unprocessed`), KHÔNG đụng wiki.
7. Báo NGẮN bằng văn nói (không bảng, không gạch ngang dài, không em dash): đã lưu note vào
   `[[tên-source]]`; có lên wiki không, nếu có thì trang nào. Có ảnh thì nhúng lại `![...](...)`
   cho người dùng xem.

## An toàn

Ghi `sources/` + `wiki/` là mức `safe`, chạy được vì người dùng chủ động gõ lệnh. KHÔNG tạo
đơn, KHÔNG tiêu tiền, KHÔNG đăng bài, KHÔNG gửi tin. Chỉ ghi file trong vault.
