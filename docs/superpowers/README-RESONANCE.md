# Javis Resonance: tiến độ và hướng triển khai hiện hành

Cập nhật 08/10/2026. MVP M1–M5 đã phát hành trong 0.86.0 qua PR #587; main khi rà là 0.86.1 (`09f254d0`). Hướng tiếp theo theo yêu cầu chủ dự án: Cộng hưởng dành cho từng agent, có công tắc riêng, heartbeat thích nghi và học từ phản hồi.

## Đọc ba tài liệu này trước

| Tài liệu | Vai trò |
|---|---|
| [Phạm vi agent và lộ trình mới](specs/2026-10-08-resonance-agent-scope-roadmap.md) | Hướng sau MVP, bốn bất biến, A1–A5 và điều kiện nghiệm thu |
| [Báo cáo rà tiến độ](../dev/resonance-progress-audit-2026-10-08.md) | Phần đã có trong mã, nền có thể tái dùng và khoảng trống bằng chứng |
| Trang HTML theo dõi (`exports/javis-resonance-tien-do.html`, ngoài git, chỉ có trên máy chủ dự án) | Bản dễ đọc cho chủ dự án, tách phần đã phát hành và phần chưa làm |

## Lộ trình hiện hành

A1: phạm vi agent + công tắc + tiến độ tối thiểu. A2: heartbeat thích nghi. A3: vòng học từ phản hồi. A4: bàn giao sản phẩm đa engine. A5: đội một agent làm, một agent review. Kiểm một VPS đại diện (D0) có thể làm song song thiết kế A1.

Tiến độ 12/10/2026: A1 đã phát hành 0.87.0 (`fdfec7c5`, [biên bản](../dev/resonance-a1-verification.md)); A2 đã phát hành 0.88.0 (`c101d108`, [biên bản](../dev/resonance-a2-verification.md)), hiệu năng VPS chưa đo; A3 đã phát hành 0.89.0 (`33a3c1aa`, PR #598, [thiết kế A3](specs/2026-10-09-resonance-a3-feedback-learning-design.md), [hướng dẫn](../dev/resonance-a3-learning.md), [biên bản](../dev/resonance-a3-verification.md)); A4 thiết kế chốt (D1: không cấp quyền ghi từ lời chat), mã đạt review vòng 5 (`5b5e3ef0`); smoke giao diện bằng engine giả xong, sửa một lỗi thẻ (`f6aeb6d1`); bộ chạy pilot đạt review cổng (`5305687a`, dry 13/13); **pilot thật đã chạy một lần** tại `5305687a` (2 lượt Claude Code Opus qua gói thuê bao, 0 việc nền; kết quả gốc `technical_failed` do bộ chạy loại nhầm thẻ turn của host, đã sửa bộ chạy và khép bằng hậu kiểm offline; bản cuối đạt nội dung, bản đầu tự thêm ngày); **đã phát hành 0.96.0** (`d36ebb3e`, PR #604, 11/10/2026; CI `main` run 38146898745 và build image run 38146898746 thành công; image `ghcr.io/blogminhquy/javis-os:0.96.0`, digest `sha256:8f1751d2…`; VPS chưa kéo) ([thiết kế A4](specs/2026-10-10-resonance-a4-handoff-grants-design.md), [hướng dẫn](../dev/resonance-a4-grants.md), [biên bản](../dev/resonance-a4-verification.md)); A5 thiết kế chốt (vòng 3, `56f7ab50`; phương án A cho file sửa tay), **mã đạt review vòng 2 tại `05e9b065`; pilot thật real-2 tại `33cec518` được reviewer chấp nhận trong phạm vi một mẫu `pass_first` (1 lượt làm, 1 lượt review, 0 chat; chưa chứng minh vòng sửa bằng model thật); chưa phát hành** (PR nháp #616, số 0.109.0, đã tích hợp `main` 0.108.0, chờ review tích hợp, [thiết kế A5](specs/2026-10-11-resonance-a5-maker-reviewer-design.md), [hướng dẫn](../dev/resonance-a5-team.md), [biên bản](../dev/resonance-a5-verification.md); chưa phát hành). Không tự bật tính năng hoặc dùng lại hạn mức của các pilot cũ. Trước khi code, viết thiết kế và kế hoạch PR theo main mới nhất; người dùng không phải điền hoặc chọn mục tiêu nghiệp vụ.

## MVP đã hoàn thành, giữ làm lịch sử

- [Thiết kế 06/10](specs/2026-10-06-javis-resonance-design.md).
- [Kế hoạch M1–M5](plans/2026-10-06-resonance-00-mvp.md).
- [Đối chiếu các bản cũ](specs/2026-10-06-resonance-revised-package-review.md).
- Review nội dung pilot 5 (`exports/reviews/PR-579-pilot5-content-review.md`, ngoài git, chỉ có trên máy chủ dự án).
- [PR phát hành #587](https://github.com/blogminhquy/javis-os/pull/587).

Không chạy lại M1 chỉ vì checklist lịch sử chưa đánh dấu. Một mẫu pilot đã đạt không chứng minh mọi engine/kênh đều hỗ trợ; xác nhận cuối mô phỏng và phạm vi đó được giữ nguyên trong hồ sơ.

## Các kế hoạch mở rộng cũ

[01 Foundation](plans/2026-10-06-resonance-01-foundation.md), [02 Runtime](plans/2026-10-06-resonance-02-runtime.md), [03 Evolution](plans/2026-10-06-resonance-03-evolution.md) là nguồn tham khảo. Không thực hiện nguyên tuần tự. Bảng ánh xạ sang A1–A5 nằm trong tài liệu 08/10; phạm vi mới và thứ tự trong tài liệu đó được ưu tiên.

## Nền làm việc và bảo toàn lịch sử

Checkout chính có thể vẫn ở nhánh cũ `codex/restore-chat-colors`. Bản rà đọc mã ở checkout riêng tại `09f254d0`; trước khi triển khai phải fetch và chốt main mới, không dựa vào số dòng/commit nền 06/10. Các thay đổi lần này là bản tài liệu cục bộ, chưa commit/push.

Bản sao trước lần chỉnh này: thư mục lưu lịch sử (`exports/archive/resonance-before-agent-scope-20261008-120051/manifest.json`, ngoài git, chỉ có trên máy chủ dự án), kèm SHA-256. Giữ các gói nguồn cũ để tra cứu; không dùng chúng làm lệnh triển khai hiện hành.
