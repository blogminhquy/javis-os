# Resonance A2: nhịp tim thích nghi, cách dùng, nâng cấp, quay về

Áp dụng cho bản 0.88.0 trở đi. Thiết kế đầy đủ: `docs/superpowers/specs/2026-10-08-resonance-a2-heartbeat-design.md`. Phần A1 (công tắc theo trợ lý) vẫn theo `docs/dev/resonance-a1-migration.md`.

## Trợ lý thức khi nào

Trợ lý đã bật Cộng hưởng chỉ gọi model khi có một trong ba lý do:

- **Việc mới:** mục tiêu vừa lập, hay cách hiểu vừa đổi, mà chưa có bản nào.
- **Tin mới từ bạn:** góp ý trên thẻ, hay một lần xem lại bạn đã hẹn giờ.
- **Thử lại còn trong giới hạn:** sau một lượt chưa đạt, hay sau lỗi.

Mọi lần thức khác chỉ chạy code, không gọi model:
- xem lại định kỳ (6 giờ, rồi giãn dần tới 7 ngày nếu không có gì đổi);
- kiểm hạn chót;
- kiểm lại công tắc trợ lý hay điều kiện bảo vệ.

Bản chat trợ lý viết ngay trong cuộc trò chuyện được tính là lượt đầu. Chưa đạt thì việc nền sửa lại theo lịch thử lại (15 phút sau), không chạy ngay.

## Giới hạn thử lại

- **Bế tắc:** hai lượt liên tiếp không tiến thêm theo tiêu chí thì trợ lý dừng thử và chờ. Mục tiêu vẫn mở; góp ý hay nói rõ hơn là làm tiếp.
- **Lỗi:** tối đa 3 lượt lỗi, rồi dừng. Lỗi cố định (bộ não việc nền không chạy được) không thử lại.
- **Thử lại tự động chừa một lượt:** không dùng lượt cuối của hạn mức. Việc mới hay góp ý của bạn thì dùng được lượt đó.
- **Hạn chót:** gần hạn thì kiểm dày hơn. Qua hạn mà chưa đạt thì báo một lần; Javis không tự gia hạn hay tự kết luận.

## File bạn sửa tay

File sản phẩm bị sửa ngoài Javis sau lần Javis ghi:
- Javis không ghi đè, không gọi model làm lại, báo một lần mỗi phiên bản file;
- tự kiểm lại sau 1 giờ, giãn dần tới 24 giờ; góp ý thì kiểm ngay;
- đưa file về đúng bản Javis đã ghi thì Javis làm tiếp; bản bạn sửa vẫn đạt tiêu chí thì Javis ghi nhận và không làm gì thêm.

## Điều kiện bảo vệ (guard)

- **Tạm dừng mục tiêu:** vẫn theo dõi bằng code; guard chạm thì vẫn báo.
- **Tắt trợ lý:** ngừng theo dõi và báo một lần. Thẻ hiện "Không còn theo dõi điều kiện bảo vệ". Bật lại thì kiểm ngay trước mọi tác động.

## Thẻ mục tiêu

- "Lần làm tiếp" kèm lý do (ví dụ "xem lại định kỳ", "có góp ý mới").
- Mục "Chi tiết và lịch sử" có "Các lần thức gần đây": giờ, lý do, có gọi model hay không.

Không có ô cài đặt mới. Các khoảng thời gian là hằng có phiên bản (`heartbeat.v1`) trong `server/resonance_heartbeat.py`.

## Nâng cấp từ 0.87.x

- **Không phải làm gì tay.** Lần đầu mở kho, Javis chép `resonance.sqlite3` thành `resonance.sqlite3.pre-a2.bak` cạnh file gốc, chỉ một lần.
- **Kho chỉ có thêm bốn bảng mới:** `wake_reasons` (lý do thức), `wake_log` (sổ thức, chỉ để xem), `source_observations` (bản file bị sửa ngoài Javis), `heartbeat_state` (chuỗi lỗi và tiến bộ dùng để quyết định thử lại). Không bảng cũ nào đổi cột.
- **Mục tiêu đang mở được dựng lại lý do từ lịch sử sự kiện:**
  - chưa làm lượt nào thì có lý do "việc mới";
  - góp ý chưa xử lý thì vẫn được xử lý một lần.

## Quay về 0.87.x

- **Bản 0.87.0 chạy được trên kho đã nâng:** nó bỏ qua bốn bảng mới. Đã kiểm bằng mã 0.87.0 thật trong `tests/python/test_resonance_a2_rollback.py`.
- **Trong lúc chạy 0.87:** nhịp cũ của MVP hoạt động lại, nên lần xem lại có thể gọi model như trước A2.
- **Nâng lại lên A2:** góp ý hay việc mới mà bản 0.87 đã làm (lượt bắt đầu sau khi tin đó tới) được tính là đã xử lý, không gọi model lần nữa.

## Khôi phục bằng bản sao trước nâng cấp

`resonance.sqlite3.pre-a2.bak` chỉ có dữ liệu tới lúc nâng. Cách làm giống bản sao A1:

1. Dừng server.
2. Chép riêng kho hiện tại (`resonance.sqlite3`, cùng `-wal`, `-shm` nếu có).
3. Chép bản sao đè thành `resonance.sqlite3`, xoá `-wal` và `-shm` cũ.
4. Chạy bản 0.87.x.
