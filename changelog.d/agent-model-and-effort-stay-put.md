---
bump: patch
title: Assistants and chat windows keep their own model and effort, and a limited card hands over by priority
---
## vi
### Sửa lỗi
- **Trợ lý và bot chạy tự động đúng cài đặt của mình.** Việc Kanban, nhắc hẹn, việc lặp, quy trình, lượt nhóm và bot chuyên trách dùng đúng model và mức suy nghĩ đặt ở trợ lý. Trước đây Kanban, nhắc hẹn và việc lặp chạy bằng model việc nền, nhóm và quy trình có thể đổi mức hoặc đổi kênh.
- **Mỗi cửa sổ chat giữ model và mức suy nghĩ riêng.** Chọn ở thanh model chỉ áp cho cửa sổ đó, kể cả chat riêng với trợ lý và Javis Core. Nó không đổi model chính, không đổi file trợ lý và không lan sang cửa sổ khác.
- **Kênh hết lượt thì chuyển sang kênh ưu tiên cao nhất còn lượt.** Javis dùng model và mức suy nghĩ đặt ở kênh thay thế, và không tự đảo thứ tự ưu tiên. Kênh của trợ lý hoặc cửa sổ chat hồi lại thì dùng lại đúng cài đặt cũ.

## en
### Fixed
- **Automatic work runs on the assistant's own settings.** Kanban jobs, reminders, loops, workflows, team turns and dedicated bots use the model and effort set on the assistant. Before, Kanban jobs, reminders and loops ran on the background model, and teams and workflows could change the effort or the card.
- **Every chat window keeps its own model and effort.** A pick in the model bar applies to that window only, private assistant chats and Javis Core included. It no longer changes the main model, the assistant file or other windows.
- **A card that is out of quota hands over by priority.** The work moves to the highest card in the priority list that still has quota, on the model and effort set on that card, and the list is never reordered. Once the assistant's or chat window's own card is back, its original settings apply again.
