---
bump: patch
title: Slash commands work in the middle or at the end of a message
---
## vi
### Sửa lỗi
- **/goal và /plan gõ ở cuối hay giữa câu giờ chạy được.** Trước đây chỉ ăn khi đứng đầu tin, gõ "...làm luôn giúp anh /goal" thì Javis chỉ chat thường. Phần chữ còn lại thành nội dung của mục tiêu.
- **Skill, agent, workflow vừa cài giữa cuộc trò chuyện gọi được ngay bằng "/" ở giữa câu.** Trang nạp lại danh sách trước khi gửi nếu gặp tên lạ, không còn coi là chữ thường.
- **Gõ tên agent hay workflow không cần tiền tố.** "/seo-pro" mở thẳng agent seo-pro, như "/agent-seo-pro".
- **Dấu câu ngay sau lệnh không làm hụt lệnh.** "/viet-email," hay "/goal." vẫn được nhận.

## en
### Fixed
- **/goal and /plan work at the end or in the middle of a message.** They used to work only at the start, so "...do it for me /goal" went out as a plain chat. The rest of the text becomes the goal.
- **Skills, agents and workflows installed mid-conversation can be called with "/" mid-sentence right away.** The page reloads its list before sending when it meets an unknown name, instead of treating it as plain text.
- **Agent and workflow names work without the prefix.** "/seo-pro" opens the seo-pro agent, same as "/agent-seo-pro".
- **Punctuation right after a command no longer hides it.** "/viet-email," and "/goal." are still recognized.
