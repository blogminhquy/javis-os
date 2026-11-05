---
bump: patch
title: Medium security fixes from the November 5 audit
---
## vi
### Bảo mật
- **Gói khai "thay thế" gói khác không còn tự bật.** Chỉ bản phát hành của kho chính thức mới giữ trạng thái bật của gói cũ. Màn hình cài ghi rõ gói nào sẽ bị gỡ và nhận dữ liệu plugin.
- **Trang chạy ở cổng localhost khác không gửi lệnh được vào Javis.** Dev server hay app khác trên cùng máy không còn mở được terminal hay gọi API. Cửa đọc API cho mọi cổng localhost chỉ mở khi đặt `JAVIS_DEV_CORS=1`.
- **Link chia sẻ một ghi chú không còn mở ảnh trong inbox/, memory/ hay thư mục ẩn của brain.**
- **Tool của kết nối MCP tự thêm có tên forward, share, trash, transfer... được tính là thao tác ghi**, nên không chạy ở mức Chỉ đọc.
- **Chạy tay workflow Docker chỉ xuất bản image từ nhánh main.**

## en
### Security
- **A pack that says it replaces another no longer switches itself on.** Only the official store's release keeps the old pack's on state. The install screen names the pack it removes and hands plugin data to.
- **A page on another localhost port can no longer send commands to Javis.** A dev server or another app on the same machine cannot open the terminal or call the API. The CORS opening for every localhost port now needs `JAVIS_DEV_CORS=1`.
- **A shared note's link no longer serves images from the brain's inbox/, memory/ or hidden folders.**
- **Custom MCP tools named forward, share, trash, transfer and the like count as writes**, so they do not run at Read only.
- **Running the Docker workflow by hand only publishes an image from main.**
