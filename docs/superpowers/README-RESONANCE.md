# Javis Resonance: bộ tài liệu chốt để triển khai MVP

Cập nhật ngày 06/10/2026 sau các vòng đối chiếu giữa Claude và Codex. Đây là điểm bắt đầu duy nhất để chọn tài liệu. Bộ này chốt thiết kế và kế hoạch, chưa xác nhận phần mềm đã được triển khai hay nghiệm thu.

## Ba tài liệu đang dùng

| Thứ tự | Tài liệu | Vai trò |
|---|---|---|
| 1 | [Thiết kế tổng thể](specs/2026-10-06-javis-resonance-design.md) | Mục tiêu sản phẩm, ba bất biến, cách agent tự hình thành mục tiêu và kiến trúc đích |
| 2 | [Kế hoạch MVP M1-M5](plans/2026-10-06-resonance-00-mvp.md) | Kế hoạch triển khai hiện hành; bắt đầu bằng M1 |
| 3 | [Bản review mới nhất và đính chính nền mã](specs/2026-10-06-resonance-revised-package-review.md) | Các lỗi của mã mẫu cần tránh, bằng chứng đã kiểm và các điều kiện phải kiểm thử |

Trong phạm vi MVP, kế hoạch `00-mvp` quyết định phần phải làm và thứ tự. Thiết kế tổng thể quyết định các bất biến và hành vi sản phẩm. Bản review cung cấp bằng chứng và điều kiện kiểm tra, không tạo một lộ trình triển khai khác.

## Những điểm đã chốt

- Người dùng nêu nhu cầu; agent tự hình thành mục tiêu, làm rõ khi cần và có thể khám phá hữu hạn khi người dùng chưa rõ. Không bắt người dùng điền SMART hoặc duyệt mọi mục tiêu.
- Bốn nhánh answer_now/task_now/continue_goal/create_goal dựa vào ngữ cảnh. Từ khóa không đủ để quyết định tạo công việc nền hoặc gắn mọi tin mới vào goal đang mở.
- Một agent, một goal mỗi lần chạy; hai evaluator đầu là artifact contract và human confirmation. Goal-fit tách khỏi kết quả, bằng chứng và phản hồi gắn đúng phiên bản.
- Thực hiện trong quyền và hạn mức đã có. Không tự đổi sang provider trả phí. Thành công cần bằng chứng, không suy từ task done hoặc emoji.
- SQLite là nguồn dữ liệu chuẩn; EvidenceStore giữ bằng chứng truy lại được. Phụ lục JSONL không thay thế hợp đồng này.
- Có thể chụp trạng thái trước/sau những thao tác ghi mà host kiểm soát được để giữ bằng chứng. Undo tổng quát và thanh emoji không nằm trên đường bắt buộc của MVP; không quảng bá khả năng hoàn tác chưa được kiểm chứng.
- Mục tiêu triển khai hiện tại chỉ là M1-M5. Review sau M1, review các PR trong M2-M4, và nghiệm thu trọn vòng sau M5. Người triển khai tự kiểm thử trước khi giao review độc lập.

## Nền mã phải kiểm trước M1

Các khảo sát ban đầu dùng checkout `codex/restore-chat-colors` tại `5b4a9be1`. Khi kiểm remote ngày 06/10/2026, `origin/main` là `7d264236b61e10077dc7833c1b063076023ea7bb` (0.83.2), có 121 commit mà checkout cũ chưa có; checkout cũ có 3 commit riêng.

Trên main được kiểm, `_reply_policy_sandbox_engine` và `_reply_policy_ask` đều tồn tại. Không dùng nhận xét thiếu hàm trên checkout cũ để kết luận thiếu trên main.

Trước khi code: cập nhật thông tin main từ remote, ghi commit nền, tạo nhánh làm việc riêng từ main đã kiểm và dò lại mọi điểm tích hợp. Số dòng cũ chỉ phục vụ lịch sử. Người viết và người review phải dùng cùng commit/PR. Việc chuẩn hóa bộ tài liệu này không chuyển nhánh và không khởi chạy M1.

## Ba kế hoạch giữ cho giai đoạn sau

- [01 Foundation](plans/2026-10-06-resonance-01-foundation.md).
- [02 Runtime](plans/2026-10-06-resonance-02-runtime.md).
- [03 Evolution](plans/2026-10-06-resonance-03-evolution.md).

Đây là tài liệu tham khảo kiến trúc mở rộng, không phải các bước phải hoàn thành trước MVP và không phải ba luồng triển khai đồng thời. Khi dùng sau này phải đối chiếu lại mã thật và nhu cầu lúc đó.

## Lịch sử và phụ lục chưa nghiệm thu

[Gói lịch sử](../../exports/archive/Javis-Resonance-LICH-SU-2026-10-06.zip) giữ các bản ZIP nguồn và ảnh chụp tài liệu trước khi dọn, kèm manifest SHA-256. Các bản cũ đã được bỏ khỏi danh sách làm việc để tránh chọn nhầm.

Phụ lục code của Claude được giữ nguyên trong `source-packages/Javis-Resonance-ban-chot-2026-10-06.zip` bên trong gói lịch sử. Trạng thái: **mẫu tham khảo, chưa nghiệm thu**. Không sao chép nguyên các module hoặc chạy checklist A1-A9; chỉ lấy từng phần sau khi đáp ứng test hành vi của M2/M4 và hợp đồng dữ liệu của M3. Các lỗi còn mở được liệt kê trong bản review mới nhất.

Bản tóm tắt trong brain ở ZIP nguồn cũng chỉ giữ để đối chiếu. Dùng trang này làm danh mục hiện hành, không dùng bản tóm tắt cũ làm một đặc tả thứ hai.
