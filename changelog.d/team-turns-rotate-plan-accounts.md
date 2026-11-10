---
bump: patch
title: Teams and workflows move to the plan account that still has quota
---
## vi
### Sửa lỗi
- **Nhóm (Team) không còn kẹt ở tài khoản đã hết lượt.** Thẻ Claude Code, ChatGPT hay Grok Build có nhiều tài khoản thì lượt của cộng sự trong nhóm giờ chạy trên tài khoản còn hạn mức, giống chat và việc nền. Trước đây nhóm luôn chạy tài khoản 1, nên tài khoản 1 hết lượt tuần là cả nhóm báo "You've hit your weekly limit" dù tài khoản kia vẫn còn.
- **Hết lượt giữa lượt nhóm thì tự chạy lại bằng tài khoản kế.** Tài khoản báo hết lượt trước khi gọi công cụ nào: Javis cho nó nghỉ và chạy lại ngay, tin trả lời ghi rõ đang dùng tài khoản nào. Bước đã gọi công cụ thì không chạy lại, để không gửi hay đăng hai lần.
- **Câu báo hết lượt không còn bị đăng thành câu trả lời của cộng sự.** Claude Code đôi khi in câu đó như một câu trả lời thường, nhóm giờ nhận ra và xử lý như lỗi hết lượt.
- **Workflow cũng xoay tài khoản.** Bước workflow chạy bằng Claude Code hay ChatGPT bắt đầu trên tài khoản còn lượt; tài khoản hết lượt khi bước chưa làm gì thì bước đó tự chạy lại bằng tài khoản kế và lần chạy đi tiếp. Trước đây cả lần chạy dừng với câu "gói hết lượt" dù tài khoản kia vẫn còn.
- **Thẻ ở trang Models ghi đúng tài khoản đang dùng.** Dòng đầu thẻ hiện tên, email và gói của tài khoản đang chạy. Trước đây nó luôn ghi tài khoản 1, nên thẻ đang chạy tài khoản Max vẫn đề "Pro".

## en
### Fixed
- **Teams no longer stay stuck on an account that ran out.** With several accounts on a Claude Code, ChatGPT or Grok Build card, a team member's turn now runs on the account that still has quota, like chat and background work. Before, teams always ran on account 1, so once it hit its weekly limit the whole team answered "You've hit your weekly limit" while the other account still had quota.
- **A team turn that runs out of quota runs again on the next account.** When the account refuses before any tool call, Javis rests it and runs the turn again at once, and the reply says which account answered. A step that already called a tool is not run again, so nothing is sent or posted twice.
- **The out-of-quota sentence is no longer posted as a member's reply.** Claude Code sometimes prints it as a normal answer; teams now recognise it and treat it as an out-of-quota error.
- **Workflows rotate accounts too.** A workflow step on Claude Code or ChatGPT starts on the account that still has quota; when the account runs out before the step did anything, the step runs again on the next account and the run carries on. Before, the whole run stopped with "the plan is out of quota" while the other account still had quota.
- **The card on the Models page names the account in use.** Its first line shows the name, e-mail and plan of the account that is running. Before, it always showed account 1, so a card running on a Max account still read "Pro".
