---
bump: patch
title: Team turns move to the plan account that still has quota
---
## vi
### Sửa lỗi
- **Nhóm (Team) không còn kẹt ở tài khoản đã hết lượt.** Thẻ Claude Code, ChatGPT hay Grok Build có nhiều tài khoản thì lượt của cộng sự trong nhóm giờ chạy trên tài khoản còn hạn mức, giống chat và việc nền. Trước đây nhóm luôn chạy tài khoản 1, nên tài khoản 1 hết lượt tuần là cả nhóm báo "You've hit your weekly limit" dù tài khoản kia vẫn còn.
- **Hết lượt giữa lượt nhóm thì tự chạy lại bằng tài khoản kế.** Tài khoản báo hết lượt trước khi gọi công cụ nào: Javis cho nó nghỉ và chạy lại ngay, tin trả lời ghi rõ đang dùng tài khoản nào. Bước đã gọi công cụ thì không chạy lại, để không gửi hay đăng hai lần.
- **Câu báo hết lượt không còn bị đăng thành câu trả lời của cộng sự.** Claude Code đôi khi in câu đó như một câu trả lời thường, nhóm giờ nhận ra và xử lý như lỗi hết lượt.

## en
### Fixed
- **Teams no longer stay stuck on an account that ran out.** With several accounts on a Claude Code, ChatGPT or Grok Build card, a team member's turn now runs on the account that still has quota, like chat and background work. Before, teams always ran on account 1, so once it hit its weekly limit the whole team answered "You've hit your weekly limit" while the other account still had quota.
- **A team turn that runs out of quota runs again on the next account.** When the account refuses before any tool call, Javis rests it and runs the turn again at once, and the reply says which account answered. A step that already called a tool is not run again, so nothing is sent or posted twice.
- **The out-of-quota sentence is no longer posted as a member's reply.** Claude Code sometimes prints it as a normal answer; teams now recognise it and treat it as an out-of-quota error.
