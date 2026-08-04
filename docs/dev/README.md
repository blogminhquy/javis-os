# Wiki kỹ thuật Javis OS

Tài liệu dành cho **người sửa code Javis** (không phải người dùng cuối). Người dùng cuối đọc `docs/01..18-*.md`.

Mục tiêu: một người mới clone repo về có thể hiểu **cái gì nằm ở đâu, vì sao lại thế, sửa thì sửa chỗ nào** mà không phải đọc hết 18k dòng Python.

## Đọc theo thứ tự này

| # | Trang | Trả lời câu hỏi |
|---|-------|-----------------|
| 1 | [Kiến trúc tổng quan](01-kien-truc.md) | Javis gồm những lớp nào, một lượt chat chạy qua đâu |
| 2 | [Backend - server/](02-backend.md) | 5000 dòng `main.py` chia thế nào, API nào có sẵn, thêm endpoint ra sao |
| 3 | [Frontend - dashboard/](03-frontend.md) | Rail + router trang, thêm một trang mới, các thủ thuật DOM cần biết |
| 4 | [Bộ não, MCP Hub, Plugin, Skill](04-engine-hub-plugin-skill.md) | Engine chọn provider kiểu gì, tool đi qua đâu, 3 mức quyền enforce ở đâu |
| 5 | [Brain (vault) và quy ước file](05-brain-vault.md) | Cấu trúc vault, agent/skill/workflow/loop/memory/wiki ghi ở đâu |
| 6 | [Bẫy, quy ước, quy trình phát hành](06-bay-quy-uoc-release.md) | Những chỗ đã cắn người trước, và cách ra một phiên bản |

## Hồ sơ kế hoạch (lịch sử quyết định)

Hai tài liệu này ghi **vì sao** kiến trúc thành ra như hiện tại. Đọc khi cần hiểu bối cảnh một quyết định cũ:

- [Kế hoạch Agent SDK](2026-07-ke-hoach-agent-sdk.md) - bỏ nhánh spawn Claude CLI bằng Popen, chuyển hẳn sang `claude-agent-sdk`. Đã khép ở v0.9.37.
- [Kế hoạch Kết nối Hub](2026-07-ke-hoach-ket-noi-hub.md) - vì sao có `mcp_hub.py` và kho connector đa tài khoản.

## Đề xuất đang mở

- [Gộp menu cài đặt](2026-07-gop-menu-cai-dat.md) - rail hiện có 18 mục, 7 trong đó là cài đặt. Kèm một khối UI chết cần xoá.
- [Adaptive Context Runtime](2026-08-adaptive-context-runtime-spec.md) - Phase 0-4 đang chạy shadow: trace, Registry, Resolver và Context Compiler thích ứng để capability tăng mà prompt ban đầu không tăng tuyến tính.
- [Javis CLI](2026-08-cli-spec.md) - đưa Javis ra terminal như một KÊNH thứ ba (sau dashboard và Telegram), bằng client mỏng chứ không nhân bản runtime. Kèm bốn chỗ đang thiếu và kế hoạch bốn giai đoạn.

## Quy ước của chính tài liệu này

- Tiếng Việt, văn nói, không dùng ký tự em dash (làm giọng đọc TTS bị khựng - đây là luật toàn dự án, xem `CLAUDE.md`).
- Trỏ tới code bằng `đường/dẫn.py:dòng` để bấm được trong editor.
- Nói **vì sao** trước, **cái gì** sau. Cái gì thì đọc code là ra, vì sao thì không.
