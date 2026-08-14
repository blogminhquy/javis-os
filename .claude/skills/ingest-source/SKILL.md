---
name: Ingest Source
description: Tiêu hoá một source thô vào Second Brain, chưng cất thành tri thức wiki tích luỹ.
description_en: "Digest one raw source into the Second Brain and distil it into wiki knowledge that compounds."
group: AI
---

# INGEST - tiêu hoá 1 source thành wiki (compounding)

## Khi nào dùng

Kích hoạt khi người dùng nói những câu như: "tiêu hoá source này", "xử lý bài này vào
wiki", "đọc file này rồi ghi lại kiến thức", hoặc khi có file mới thả vào `sources/`.

Skill làm theo đúng 3 kỷ luật của vault.

Đọc schema vault (`CLAUDE.md`/`AGENTS.md` ở gốc brain) trước; đây là bản thao tác của phép INGEST.

## Trước khi làm
- Kiểm frontmatter source: `status: processed` -> DỪNG, báo đã xử lý, hỏi có re-ingest không. `unprocessed`/chưa có -> làm.
- Phân loại độ dài. Source dài (>= ~10.000 dòng / sách / transcript) -> BẮT BUỘC 3-pass:
  1. Đọc lướt, lập mục lục theo số dòng (vd "1-1300: giới thiệu"). Báo người dùng xác nhận trọng tâm.
  2. Đọc sâu từng đoạn ~1.000-1.500 dòng, viết wiki NGAY từng đoạn (đừng nén cả file 1 lần - mất 25-40% chi tiết).
  3. Tự hỏi 5 câu về các vùng khác nhau; wiki không trả lời được câu nào -> quét bổ sung vùng đó.

## Các bước
1. Đọc source (kèm ảnh nếu có).
2. Tóm tắt 3-5 ý chính; rút insight/framework; liên hệ khái niệm đã có.
3. Xác định trang wiki: mới cần tạo / cần cập nhật / cần merge (đọc `wiki/index.md` để dedup).
4. Viết/cập nhật wiki (1 trang = 1 ý, có `[[...]]` ngược lại trang liên quan) - TUÂN THỦ 3 KỶ LUẬT:
   - Citation cứng: mỗi câu cụ thể kết bằng `[[Nguồn]]`.
   - Mục tiêu vs thực tế: gắn nhãn "(mục tiêu)" / "(thực tế tính đến ...)" / "(cần xác minh)".
   - Mâu thuẫn với trang cũ: thêm `## Mâu thuẫn` (giữ cả 2 quan điểm + nguồn) + append `wiki/_open-questions.md`, KHÔNG ghi đè.
   Ngoài 3 kỷ luật, mỗi trang phải TỰ ĐỦ NGỮ CẢNH (contextual retrieval - trang tách khỏi source vẫn hiểu và tìm thấy được):
   - Mở đầu trang bằng 1-2 câu định vị: khái niệm này là gì, thuộc chủ đề/nguồn nào, dùng khi nào. Nhất là khi ingest source dài theo từng đoạn - đoạn giữa sách mà thiếu câu định vị là sau này đọc lẻ không hiểu.
   - Frontmatter thêm `aliases: [tên gọi khác, viết tắt, thuật ngữ tiếng Anh]` - để sau này hỏi bằng từ khác thì grep/search vẫn bắt trúng trang.
5. Cập nhật `wiki/index.md` (thêm dòng link + mô tả 1 dòng).
6. Set source `status: processed`, `processed_at`, `wiki_links: [...]`. Không đáng vào wiki -> `status: skipped` + `note`.
7. Append `wiki/log.md`: `## [YYYY-MM-DD] ingest | <tên source>` + nguồn/đã tạo/đã cập nhật/insight.
8. Đề xuất task nếu source mở ra hành động (chỉ đề xuất). Báo cáo ngắn: tóm tắt + trang đã chạm + insight + task.
