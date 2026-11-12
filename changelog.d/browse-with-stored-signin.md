---
bump: minor
title: Agents can operate pages behind a stored sign-in, with owner approval for important actions
---
## vi
### Thêm mới
- **Agent thao tác được trang cần đăng nhập, không chỉ đọc.** Tool mới `javis_browse` mở trang bằng cookie đã cất ở trang Cookies rồi bấm, gõ, nhấn phím, chụp màn hình. Cookie không bao giờ trả cho model, và trang chỉ đi trong tên miền của đăng nhập đó. `javis_login` vẫn chỉ đọc.
- **Thao tác quan trọng trên sàn và trang quảng cáo chờ bạn duyệt.** Mỗi thẻ ở trang Cookies có công tắc "Cho agent thao tác" và lựa chọn "Hỏi tôi / Tự động" (Shopee, TikTok, Lazada, Facebook Ads, Google Ads, Sapo, MoMo... mặc định là Hỏi tôi). Agent bấm hoặc gõ thì thao tác nằm chờ trong khung "Chờ bạn duyệt" với ba nút: Duyệt lần này, Duyệt toàn quyền, Từ chối, và chuông báo có việc cần duyệt. Chỉ bạn duyệt được, agent không tự duyệt.

## en
### Added
- **Agents can operate pages behind a sign-in, not just read them.** The new `javis_browse` tool opens a page with the cookies stored on the Cookies page, then clicks, types, presses keys and takes screenshots. Cookies never reach the model, and the page can only navigate within the login's own domains. `javis_login` stays read-only.
- **Important actions on marketplace and ads sites wait for your approval.** Each card on the Cookies page has a "Let agents operate" switch and an "Ask me / Automatic" choice (Shopee, TikTok, Lazada, Facebook Ads, Google Ads, Sapo, MoMo... default to Ask me). When an agent clicks or types, the action waits in a "Waiting for your approval" panel with three buttons: Approve this once, Always approve, Deny, and the bell tells you something needs approval. Only you can approve; an agent cannot approve itself.
