# 📚 Tài liệu Javis OS

***Tiếng Việt** · [English](en/README.md)*

Hướng dẫn sử dụng chi tiết từng chức năng của Javis OS. Mỗi trang là một how-to độc lập: mở ở đâu, bấm gì, dùng thế nào.

> Mới bắt đầu? Đọc [Cài đặt trong README](../README.md#-cài-đặt) trước, rồi qua [01 - Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md).

Thanh điều hướng của dashboard gom **19 trang** thành **7 nhóm**: Trợ lý · Bộ não · Code · Năng lực · Việc · Kết nối · Hệ thống. Mục lục dưới đây xếp theo cùng logic đó.

## Mục lục

### Bắt đầu
- [01 - Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) - tạo admin, đăng nhập bộ não, chọn engine/model, trang Cài đặt.

### Dùng hằng ngày (nhóm Trợ lý & Bộ não)
- [02 - Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) - chat, nói rảnh tay, lệnh gạch chéo, nút trả lời nhanh, gửi file, tạo ảnh.
- [03 - Đồ thị tri thức](03-do-thi-tri-thuc.md) - wikilink, màu danh mục, timelapse và công tắc đồ thị.
- [04 - Phiên hội thoại](04-phien-hoi-thoai.md) - lưu, mở lại, đổi tên, xoá, tìm kiếm toàn văn, nén phiên dài.
- [05 - Quản lý tệp tin](05-quan-ly-tep-tin.md) - duyệt brain, tìm file theo tên/nội dung, sửa .md/.txt trực tiếp, tải lên/về.

### Code (nhóm Code)
- [27 - Nhóm Code: Terminal](27-tab-code-terminal.md) - dòng lệnh thật của máy chạy Javis, mở ngay trong dashboard, không cần SSH.

### Mở rộng năng lực (nhóm Năng lực)
- [06 - Skills](06-skills.md) - gom nhóm, tìm kiếm, bật/tắt, thêm/sửa/xoá, nhập/xuất skill.
- [07 - Agents & Workflows](07-agents-va-workflows.md) - tạo trợ lý chuyên biệt + chuỗi tự động nhiều bước.
- [20 - Plugins](20-plugins.md) - thêm tool/hook native cho mọi engine bằng một thư mục Python.
- [25 - Chatbot (Bot chuyên trách)](25-chatbot.md) - đem Agent ra trả lời khách qua bot Telegram hoặc Zalo riêng, brain riêng, chuyển nhân viên khi bí.

### Việc chạy nền (nhóm Việc & Bộ não)
- [08 - Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) - nhiều vòng lặp chạy nền + nhắc hẹn theo giờ hoặc cron.
- [21 - Việc (Kanban)](21-viec-kanban.md) - giao goal bằng lời, AI tự đặc tả và chạy task nền.
- [22 - Tự học](22-tu-hoc.md) - Javis tự rút ký ức, đúc Wiki và kỹ năng sau mỗi hội thoại, hoàn tác được.

### Kết nối & kênh (nhóm Kết nối)
- [09 - Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - kho dịch vụ ngoài đa tài khoản, phân quyền, báo cáo số thật.
- [10 - Models & engine](10-models-va-engine.md) - đổi bộ não giữa Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Gemini, Anthropic, Groq, Ollama mà không mất chức năng; mức suy nghĩ, model việc nền.
- [11 - Kênh Telegram](11-telegram.md) - hỏi Javis qua điện thoại, gửi và nhận file.
- [26 - Kênh Zalo Bot](26-kenh-zalo-bot.md) - hỏi Javis trên Zalo bằng API chính thức, ghép nối bằng một cú bấm.
- [12 - Zalo Agent MCP](12-zalo.md) - đăng nhập QR, đọc/tìm lịch sử và gửi tin qua MCP chuẩn.
- [24 - Javis CLI (terminal)](24-cli-terminal.md) - gõ `javis "..."` từ terminal, token API, ghép vào script.

### Bộ não & dữ liệu
- [13 - Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) - đa brain, bộ nhớ sống, tiêu hoá tri thức.
- [18 - Sao lưu brain lên GitHub](18-sao-luu-github.md) - đồng bộ 2 chiều lên repo riêng, khôi phục khi mất máy/VPS.
- [19 - Task & Dataview trong note](19-task-va-dataview.md) - tick checkbox tự lưu kiểu Obsidian, khối ```dataview chạy thật.

### Tài khoản, thương hiệu, cấu hình (nhóm Hệ thống)
- [14 - Bảo mật & tài khoản](14-bao-mat-tai-khoan.md) - đăng nhập bắt buộc, mật khẩu, rate-limit, mã hoá khoá bí mật.
- [15 - Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md) - đổi logo/avatar, trỏ tên miền và bật HTTPS.
- [16 - Cấu hình .env](16-cau-hinh-env.md) - tham chiếu mọi biến môi trường.
- [23 - Mức dùng: token & chi phí](23-muc-dung-token.md) - Javis tự đo token vào/ra theo ngày, theo nhà cung cấp, theo nguồn.

### Khi có sự cố
- [17 - Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md) - lỗi thường gặp và cách xử lý.

---

## Bản tiếng Anh

Tài liệu đang dịch dần từng trang, không dịch một lượt. [docs/en/](en/README.md) nói rõ trang
nào đã có tiếng Anh và trang nào còn nguyên tiếng Việt - xem ở đó thay vì đoán. Thêm một ngôn
ngữ vào chính Javis (không phải tài liệu) thì theo [sổ tay thêm ngôn ngữ](dev/them-mot-ngon-ngu.md).

---

> Quy ước viết tài liệu: tiếng Việt, thực tế, ngắn gọn. Không dùng ký tự em dash (U+2014), luôn thay bằng dấu gạch nối "-". Xem thêm [CLAUDE.md](../CLAUDE.md) cho quy ước hệ thống dành cho AI agent.
