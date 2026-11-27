---
bump: minor
title: Javis finds skills by their whole description, every skill named, nothing cut
---
## vi
### Cải thiện
- **Javis thấy đủ mọi skill.** Trước đây danh sách skill trong prompt chỉ chứa khoảng 20 skill (brain 44 skill thì 23 skill bị ẩn). Giờ prompt nêu tên mọi skill, gọn và cố định nên không làm mất cache.
- **Chọn skill theo trọn mô tả, không còn cắt 150 ký tự.** Mỗi lượt Javis chấm mọi skill theo câu bạn vừa gõ, rồi đưa vài skill khớp nhất kèm mô tả đầy đủ cho model. Đo trên hai bộ thử: chọn đúng 95-96%, cách cũ 23-64%.
- **Mô tả skill được dài tới 1.024 ký tự** (chuẩn Agent Skills), nên skill nhập từ Anthropic hay kho khác dùng nguyên văn. Cảnh báo "Mô tả dài quá" trên trang Kỹ năng chỉ còn hiện khi quá 1.024.
- **Javis tự học cách bạn gọi skill.** Câu nào gợi ý bỏ sót mà sau đó skill vẫn được dùng thì lần sau nói tương tự là tìm ra ngay. Model cũng tìm được skill theo việc cần làm qua `javis_use_skill(find=...)`, tìm tool và `javis_code`. Phần thử mô tả skill (Duyệt đề xuất cải tiến skill) cũng chấm theo cách chọn mới.

## en
### Improved
- **Javis sees every skill.** The skill list in the prompt used to hold about 20 skills (a 44-skill brain hid 23). The prompt now names every skill, short and fixed, so the prompt cache keeps holding.
- **Skills are picked by their whole description, no longer cut at 150 characters.** Each turn Javis ranks every skill against what you typed and gives the model the few that fit, with their whole description. Measured on two test sets: the right skill 95-96% of the time, against 23-64% before.
- **A skill description can be up to 1,024 characters** (the Agent Skills standard), so skills from Anthropic or other stores work as written. The "Description too long" warning on the Skills page only shows past 1,024.
- **Javis learns how you ask for a skill.** A request the suggestions missed, followed by that skill being used, finds it next time. The model can also search skills by the job through `javis_use_skill(find=...)`, the tool search and `javis_code`. Skill description trials (review of skill improvement proposals) now score with the new routing too.
