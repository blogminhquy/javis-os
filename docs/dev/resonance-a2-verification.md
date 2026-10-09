# Resonance A2: biên bản nghiệm thu (09/10/2026)

Mốc A2 của lộ trình [agent scope](../superpowers/specs/2026-10-08-resonance-agent-scope-roadmap.md): trợ lý thức vì lý do cụ thể, ngủ khi chờ, không gọi model vô ích.

**Trạng thái: thiết kế và mã đạt review; kiểm tích hợp đạt. Chưa merge, chưa phát hành, chưa đo VPS.** A2 chỉ tính là mốc hoàn tất khi A1 và A2 được merge, và bản 0.88.0 được phát hành.

## Mã và commit

- **PR:** #593, nhánh `claude/resonance-a2-heartbeat`, VERSION 0.88.0, chồng lên A1 (#590, `077bcf73`). `main` (`71f9c5b9`, 0.86.2) nằm trong lịch sử nhánh.
- **Thiết kế:** đạt review ở vòng 4, `cb11fc23`.
- **Mã:**
  - `c2b0874f` mã A2, `50c355f1` bản vá nhãn i18n.
  - Ba vòng sửa theo review mã: `d1f64b46`, `f7cbab4c`, `b5975b7e`.
  - **Review mã đạt ở `b5975b7e`.**
- **Sau review (kiểm tích hợp):** một sửa nhỏ và hai mục không chặn của review, ghi ở mục "Sau review mã" bên dưới.

## Bảng nghiệm thu (thiết kế mục 13)

| Điều kiện | Kết quả | Bằng chứng |
|---|---|---|
| Chỉ lý do mở được lượt model (bước đầu, tin mới, thử lại trong trần); xem lại, hạn chót, mã lạ không gọi model | Đạt | `test_resonance_a2_heartbeat.py`, chính sách và ca chỉ-kiểm |
| Đạt và chờ người dùng 30 ngày: 0 lượt thêm | Đạt | cùng file |
| Duy trì đạt 30 ngày: xem lại giãn 6, 12, 24, 48, 96, 168 giờ; 0 lượt thêm | Đạt | cùng file |
| Bế tắc 2 lượt thì chờ, không thất bại; góp ý mở lại; còn một lượt thì thử lại tự động không dùng | Đạt | cùng file |
| Lỗi: tối đa 3 lượt tổng cộng; lỗi cố định không thử lại; chết giữa lượt tính một lượt lỗi | Đạt | cùng file |
| Chuỗi lỗi và tiến bộ bền, không phụ thuộc sổ thức (ghi lỗi, bị cắt, chết giữa receipt và kết sổ, mở lại kho, bật lại trợ lý) | Đạt | mục "Review mã vòng 1" |
| Hạn chót gần, qua hạn báo một lần; hai nghĩa vụ thử lại và kiểm không thay nhau; cùng thời điểm | Đạt | cùng file |
| Lịch người dùng hẹn chỉ xét từ giờ hẹn, giữ giờ qua khởi động lại, không nhân đôi | Đạt | cùng file |
| Lý do không mất khi bị chặn (tạm dừng, tắt trợ lý, guard chưa đọc được); sự kiện giữa lượt còn chờ; giao lại không xử lý hai lần | Đạt | cùng file |
| Bị gác chỉ hẹn kiểm gỡ gác; không thức mỗi 30 giây; không chiếm suất mục tiêu khác; khởi động lại không thức dày | Đạt | cùng file, gồm mở lại kho thật |
| Sửa ngoài luồng: 0 lượt model, báo một lần mỗi hash, không đổi mốc thay file; tự kiểm lại 1 giờ tới 24 giờ; metadata trùng mà bytes khác vẫn nhận ra | Đạt | cùng file |
| Guard: tạm dừng vẫn theo dõi; tắt trợ lý báo mất theo dõi; bật lại dựng lại kể cả khi tạm dừng; chốt guard không tự mở | Đạt | cùng file |
| Lỗi của revision cũ không gác hay xoá lịch của revision mới | Đạt | mục "Review mã vòng 1" |
| I/O trước và sau lời gọi engine không chạy trên event loop; huỷ ở mọi pha không nhả khoá sớm, không mất lượt, không hoàn lượt đã chạy; lỗi của pha không che lời huỷ | Đạt | mục "Review mã vòng 2" và "vòng 3" |
| Hiệu năng trong môi trường test: không đọc file mục tiêu chưa tới hạn, 3 lịch mỗi nhịp theo `due_at`, trễ loop dưới 50 ms, số câu SQLite không tăng theo số mục tiêu | Đạt | mục "Hiệu năng" |
| Quay về 0.87.0 bằng mã thật trên kho đã nâng; nâng lại không gọi thừa | Đạt | `test_resonance_a2_rollback.py`, chạy cả trên CI |
| Thẻ mục tiêu: nhãn lý do thức hai thứ tiếng, sổ thức gần đây, trạng thái theo dõi, sửa ngoài luồng | Đạt | `tests/js/test_resonance_a2_ui.js`; soi trên dashboard sandbox (dưới) |
| Hiệu năng trên VPS | **Chưa kiểm** | Phải đo riêng khi triển khai |

## Kiểm tích hợp (09/10/2026)

- **Nền:** A1 (#590) chưa merge, `main` vẫn `71f9c5b9`. SHA ghim của test quay về (`077bcf73`) và bước fetch trên CI vẫn đúng, không phải đổi.
- **Smoke dry trên bản tích hợp:**
  - chạy `JAVIS_RESONANCE_E2E_ACHIEVE=dry tests/python/test_resonance_mvp_e2e_achieve.py`;
  - dựng server thật, đi đủ S0 tới S6 trong phiên trợ lý;
  - kết quả `dry_ok`, **0 lượt engine cấp host**, 255 giây.
- **Soi giao diện** trên server sandbox (cổng 7788, state và brain tạm, engine giả, nhịp tạm dừng):
  - ba mục tiêu: chưa đạt chờ thử lại, duy trì đạt có guard, file bị sửa tay;
  - trang Cộng sự, tab Cài đặt của trợ lý, hiện đúng các mục trong bảng dưới;
  - không cuộn ngang. Sandbox đã dừng và xoá.

| Mục tiêu | Thẻ hiện |
|---|---|
| Chưa đạt, chờ thử lại | "Lần làm tiếp: ... (làm lại phần chưa đạt)", 15 phút sau lượt đầu |
| Duy trì đạt, có guard | "(xem lại định kỳ)" và "Theo dõi điều kiện bảo vệ, lần kiểm tới: ..." |
| File bị sửa tay | trạng thái "File bị sửa ngoài Javis, đang chờ", dòng cảnh báo kèm giờ tự kiểm lại |
| Cả ba | Mục "Các lần thức gần đây" ghi lý do và "làm một lượt" hay "không gọi model" |

## Sau review mã (trong đợt kiểm tích hợp)

1. **Sửa nhỏ, cần reviewer xem lại diff:** hành động ĐĂNG sản phẩm tạo hẹn phục hồi mã `recovery`, cùng nghĩa vụ với thử lại tự động.
   - Lỗi này lộ ra khi soi dữ liệu thẻ của sandbox.
   - Khi không có hẹn thử lại nào thay nó, sau khoảng 2 phút nó được xét như một lần thử lại tự động. Với mục tiêu đã đạt thì vô hại; ở nhánh có bản không đăng được thì có thể mở lượt sớm hơn mốc.
   - Nay hành động không phải lượt việc dùng mã `action_recovery` (chỉ kiểm, không bao giờ mở lượt model).
   - Dòng sổ của lượt việc ghi thêm dấu vết đánh giá theo hash của bản vừa đăng, nên lần xem lại đầu sau lượt việc giãn nhịp đúng 6 rồi 12 giờ.
   - Test mới: sau khi đăng không còn lý do thử lại tự động nào chờ. Ca này hỏng trên mã `b5975b7e`.
2. **Lưu ý không chặn 1:** hướng dẫn liệt kê đủ bốn bảng mới, gồm `heartbeat_state`.
3. **Lưu ý không chặn 2:** `_cleanup` và bước nhả khoá cuối của `advance` ghi log lỗi mà lời huỷ mang theo (`_CancelledWith.error`). Lời huỷ vẫn đi tiếp như trước.

## Test đã chạy

- `test_resonance_a2_heartbeat.py`: **148 kiểm đạt**.
- `test_resonance_a2_rollback.py`: 11 kiểm đạt. `test_resonance_a2_ui.js`: 10 kiểm đạt.
- Nhóm hồi quy `tests/run.py resonance turn_ route_table plugin hub chat_disconnect workflow agent settings i18n`: **70/70 xanh** trên mã tích hợp; toàn bộ test JS xanh.
- Toàn bộ 621 file đã chạy một lần ở `c2b0874f`: 605/621. 16 file đỏ đều do môi trường máy, không file nào thuộc Resonance. Chưa chạy lại toàn bộ sau các vòng sửa.
- CI: xem PR cho head cuối.

## Giới hạn còn lại

- **Hiệu năng VPS chưa đo.** Số đo event loop là môi trường test cục bộ, không suy ra tab trên VPS đã hết chậm. Đo tốc độ tab trên VPS là bằng chứng triển khai riêng (cùng việc Cloudflare và PR #592).
- **Không có pilot model thật cho A2.** Thiết kế mục 12 và 13 nghiệm thu bằng đồng hồ giả. Nếu cần pilot thật thì trình kịch bản và hạn mức riêng.
- **Bản chat chưa đạt** được việc nền sửa sau 15 phút (chính sách đã chốt); thẻ hiện giờ làm tiếp.
- **`user_schedule`** có trong lõi nhưng chưa có nút hay tool để người dùng hẹn.
- **Liên kết `javis_schedule` với mục tiêu** để sau (thiết kế mục 9).
- **Khi A1 merge bằng squash:** đổi `OLD_SHA` trong `test_resonance_a2_rollback.py` và SHA trong `.github/workflows/ci.yml` sang commit 0.87.0 trên `main`, rồi rebase A2 lên `main`.

## Tài liệu cho người dùng

- [Cách dùng, nâng cấp, quay về, khôi phục](resonance-a2-heartbeat.md).
- [Thiết kế A2](../superpowers/specs/2026-10-08-resonance-a2-heartbeat-design.md).
