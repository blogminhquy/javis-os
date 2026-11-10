---
bump: patch
title: Google Ads connects without a developer token, label tools no longer run at read-only
---
## vi
### Sửa lỗi
- **Kết nối Google Ads không còn đòi developer token.** Ô này giờ là tuỳ chọn và hướng dẫn đi theo đường Google Cloud: bật Google Ads API, bấm xin mức Explorer ngay trong project, rồi tạo OAuth client. Người mới không còn kẹt ở bước xin một token mà Google không còn yêu cầu.

### Bảo mật
- **Tool sửa nhãn của Google Ads không còn chạy được ở mức Chỉ đọc.** Bản MCP mới của Google có thêm tool tạo, sửa, xoá nhãn và tải video lên YouTube; hai tool nhãn từng bị xếp nhầm vào nhóm đọc. Giờ chúng chỉ chạy ở mức Toàn quyền, tạo asset ở mức Ghi nháp, và thẻ kết nối nói rõ mỗi mức sửa được gì.

## en
### Fixed
- **Connecting Google Ads no longer demands a developer token.** The box is optional now and the guide follows the Google Cloud path: enable the Google Ads API, apply for Explorer access inside the project, then create the OAuth client. New users are no longer stuck asking for a token Google no longer requires.

### Security
- **Google Ads label tools no longer run at Read only.** Google's newer MCP adds tools that create, edit and delete labels and upload a video to YouTube; the two label tools were wrongly classified as read. They now need Full access, creating assets needs Draft writes, and the connection card says what each level can change.
