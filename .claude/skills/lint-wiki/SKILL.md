---
name: Lint Wiki
description: Rà soát sức khoẻ wiki của Second Brain, trả về danh sách vấn đề. Không tự sửa hàng loạt.
description_en: "Audit the health of the Second Brain wiki and hand back a list of problems. Never mass-edits on its own."
group: AI
---

# LINT - health-check wiki (chỉ CHECKLIST)

## Khi nào dùng

Kích hoạt khi người dùng nói những câu như: "health check wiki", "lint wiki", "wiki có
lỗi gì không", "rà soát bộ não".

Quét `wiki/` phát hiện 8 loại vấn đề:
1. Mâu thuẫn giữa các trang (gồm section `## Mâu thuẫn` ghi nhận trước mà chưa giải).
2. Stale claim (trang cũ chưa cập nhật theo source mới).
3. Orphan (không có inbound `[[link]]`).
4. Missing (khái niệm nhắc nhiều nơi nhưng chưa có trang riêng).
5. Broken `[[wikilink]]` (trỏ file không tồn tại).
6. Trùng lặp (2 trang gần giống -> đề xuất merge).
7. Gap (vùng kiến thức mỏng, cần thêm source / web search).
8. Open-question tồn lâu trong `wiki/_open-questions.md`.

NGUYÊN TẮC VÀNG: chỉ TRẢ VỀ DANH SÁCH có đánh số. TUYỆT ĐỐI KHÔNG tự sửa 50 chỗ một lúc. Người dùng ưu tiên rồi ra lệnh sửa từng cái (tránh mất kiểm soát audit).
