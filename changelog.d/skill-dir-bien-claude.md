---
bump: patch
title: Skills that use ${CLAUDE_SKILL_DIR} now run on every engine
---
## vi
### Sửa lỗi
- **Skill viết lệnh bằng `${CLAUDE_SKILL_DIR}` giờ chạy được trên mọi engine, không riêng Claude Code.** Javis thay biến này bằng đúng thư mục của skill, như Claude Code vẫn làm, ở cả ba đường: tool `javis_use_skill`, lệnh `/skill` trong Team và skill Javis tự chọn cho câu hỏi. Trước đây engine nhận nguyên chữ `${CLAUDE_SKILL_DIR}`, shell biến nó thành rỗng và lệnh chết, ví dụ mọi lệnh `claude-seo` trong gói Claude SEO của Kho.

## en
### Fixed
- **Skills whose commands use `${CLAUDE_SKILL_DIR}` now run on every engine, not only Claude Code.** Javis replaces it with the skill's own folder, as Claude Code does, on all three paths: the `javis_use_skill` tool, `/skill` in a Team, and the skill Javis picks for a question. Engines used to get the literal token, their shell expanded it to nothing and the command failed, for example every `claude-seo` command in the Store's Claude SEO pack.
