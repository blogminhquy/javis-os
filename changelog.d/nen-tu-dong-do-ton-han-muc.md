---
bump: minor
title: Background work spends far less of the plan allowance
---
## vi
### Thêm mới
- **Model việc nền có chế độ Tự động, và là mặc định.** Trước đây việc nền chạy bằng model mặc định của nhà cung cấp, trên gói thuê bao thường là model mạnh và tốn nhất. Giờ Javis dùng nhà cung cấp của MAIN và chọn sẵn hai model từ danh sách của chính nhà đó: model nhẹ cho việc Javis tự làm (tự học, gợi ý câu tiếp theo, chấm điểm), model bậc giữa cho việc bạn giao chạy nền (nhắc hẹn, loop, Kanban). Trang Models ghi rõ hai model đang dùng. Javis chỉ chọn lại khi danh sách model của nhà đó thay đổi, và báo ở chuông mỗi lần chọn.
- **Model bạn tự chọn thì Javis không bao giờ đổi.** Bấm Đổi model ở khối Model việc nền và chọn một model: nó giữ nguyên. Muốn về Tự động thì chọn dòng "Tự động (khuyên dùng)" ở đầu danh sách. Máy đã cài: model nền còn nguyên cấu hình mặc định thì chuyển sang Tự động, bạn từng chọn model khác thì giữ nguyên.
- **Việc Javis tự làm tự nghỉ khi gói sắp hết hạn mức.** Cửa sổ 5 giờ của gói đã dùng từ 80% thì tự học và gợi ý câu tiếp theo chờ tới lúc hạn mức mở lại, phần còn lại để dành cho chat của bạn.

### Cải thiện
- **Tự học mặc định chỉ học ký ức và wiki.** Học skill mở thêm một lượt phản biện mỗi mẻ và kéo theo cả phần chấm điểm skill chạy ngầm, là chỗ tốn hạn mức nhất khi bạn không gõ gì. Máy đã cài cũng được tắt một lần; cần thì bật lại công tắc Kỹ năng ở trang Tự học.
- **Tự học chạy 15 phút sau sự kiện cuối cùng, một lần cho cả cuộc trò chuyện.** Trước đây cứ 3 lượt chat là một mẻ học, nên một cuộc 12 lượt mở 4 mẻ đọc lại gần như cùng một đoạn. Giờ Javis chờ brain yên 15 phút (bạn hỏi thêm, việc nền chạy xong hay khách đang nhắn với chatbot đều tính lại từ đầu) rồi học một mẻ, mỗi tin nhắn chỉ đọc một lần. Cả ngày không có sự kiện nào thì không học và không tốn gì. Câu "ghi nhớ giúp" vẫn được học sau 30 giây.
- **Bỏ trần ngày của tự học.** Trần 40 mẻ và 15 triệu token mỗi ngày không hợp cho cả người dùng nhiều lẫn người dùng ít, và chạm trần thì Javis vẫn chạy mẻ học rồi chỉ không ghi file. Nhịp mới đã giữ số mẻ theo đúng số cuộc trò chuyện.
- **Gợi ý câu tiếp theo và các lượt chỉ cần chữ nhẹ đi nhiều.** Những lượt này (gợi ý câu tiếp theo sau mỗi lượt chat, bộ phán xử, phân loại sự cố, câu nhắc thói quen) không dùng công cụ nào nhưng vẫn gửi kèm cả bộ luật và mô tả công cụ của Claude Code. Phép đo sẵn có trong mã cho cùng một câu: 27.665 token khi gửi kèm, 183 token khi không. Giờ chúng không gửi kèm nữa.

## en
### Added
- **The background model has an Automatic mode, and it is the default.** Background work used to run on the provider's default model, which on a plan is usually the strongest and costliest. Javis now uses MAIN's provider and picks two models from that provider's own list: a light one for the work Javis starts itself (self-learning, next-message suggestions, judging), a middle one for the jobs you hand over (reminders, loops, Kanban). The Models page names both. Javis picks again only when that provider's model list changes, and leaves a notice in the bell each time.
- **A model you choose yourself is never changed.** Press Change model in the Background model block and choose one: it stays. To go back, choose "Automatic (recommended)" at the top of the list. On existing installs, a background model still on its starting setup moves to Automatic; one you had changed stays as it is.
- **Javis's own work waits when the plan is nearly used up.** Once the plan's 5-hour window is 80% used, self-learning and next-message suggestions wait for the reset, and what is left is kept for your chat.

### Improved
- **Self-learning learns memories and wiki notes only by default.** Skill learning adds a second verify pass to every batch and switches on the background skill judging, the costliest part while you are not typing. Existing installs were switched off once too; turn the Skill switch on the Self-learning page back on if you need it.
- **Self-learning runs 15 minutes after the last event, once per conversation.** A batch used to fire every 3 chat turns, so a 12-turn chat opened four batches that each re-read much the same messages. Javis now waits until the brain has been quiet for 15 minutes (you asking again, a background job finishing or a customer talking to a chatbot all start the wait over) and learns in one batch, reading each message once. A day with no event learns nothing and costs nothing. "Remember this" is still learned after 30 seconds.
- **The daily ceilings of self-learning are gone.** 40 batches and 15 million tokens a day fit neither a heavy user nor a light one, and at the ceiling Javis still ran the batch and only kept its result from being written. The new rhythm already ties the number of batches to the number of conversations.
- **Next-message suggestions and other text-only turns are much lighter.** These turns (the suggestion after every chat turn, the reply judges, incident triage, habit lines) use no tool, yet still sent Claude Code's own rules and every tool description. The measurement already in the code for the same question: 27,665 tokens with them, 183 without. They are no longer sent.
