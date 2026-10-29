# Ý tưởng: chấm sao, đếm lượt cài và lọc trong Javis Store

Trạng thái: **tạm gác** (chủ dự án, 2026-10-29). Làm khi có bản doanh nghiệp, lúc đó Javis có máy chủ
trung tâm để quản lý key, và phần này dùng chung máy chủ đó.

## Chủ dự án muốn gì

- Người dùng **vote sao** cho từng gói trong Store, kiểu nút Star của GitHub.
- Store **thống kê được lượt cài** của từng gói.
- Store có **bộ lọc, sắp xếp**: theo lượt cài, theo sao, theo đề xuất, theo mới tải lên.

## Đã làm (0.407.0)

Phần không cần máy chủ đã có trong Store:

- Ô **Sắp xếp** cạnh ô tìm: Đề xuất (mặc định, gói Khuyên dùng theo repo gốc lên đầu), Mới cập nhật,
  Tên A-Z. Javis nhớ lựa chọn trên từng máy.
- Mô tả trên thẻ dừng ở 3 dòng, kết thúc bằng dấu "…".

Khi có máy chủ, ô Sắp xếp chỉ cần thêm hai lựa chọn: **Nhiều lượt cài** và **Nhiều sao**.

## Vì sao phải có máy chủ

Store hiện chỉ là tệp tĩnh `index.json` trên GitHub (repo `javis-store`). Mỗi máy Javis tự tải về,
không có chỗ nào ghi lại ai đã cài gói gì hay ai đã vote. Muốn đếm thì mỗi máy Javis phải báo về
**một nơi chung**.

## Thiết kế đề xuất

### Định danh máy, không định danh người

- Mỗi máy Javis tự tạo một **mã ẩn danh ngẫu nhiên** lúc cài, lưu trong thư mục state.
- Javis chỉ gửi: mã ẩn danh, id gói, phiên bản gói, loại sự kiện (cài, gỡ, sao, bỏ sao).
  Không gửi tên, email, nội dung brain hay địa chỉ máy.
- Bản doanh nghiệp có key: lúc đó có thể gắn sao với tài khoản để chống vote ảo tốt hơn.

### Dữ liệu trên máy chủ

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `luot_cai` | ma_may, id_goi, phien_ban, luc | Một dòng cho mỗi cặp (máy, gói). Cài lại không đếm thêm. |
| `sao` | ma_may, id_goi, luc | Một máy chỉ một sao mỗi gói. Bỏ sao là xoá dòng. |
| `thong_ke` | id_goi, so_cai, so_sao, cap_nhat | Bảng gộp, tính lại theo lịch (vd 15 phút một lần). |

### API

- `POST /su-kien`: Javis báo cài, gỡ, sao, bỏ sao.
- `GET /thong-ke.json`: toàn bộ số đếm của mọi gói trong một tệp, có cache ở CDN.
  Javis tải tệp này cùng lúc với `index.json` rồi ghép theo id gói.

Lý do tách tệp thống kê khỏi `index.json`: danh mục vẫn là tệp tĩnh trên GitHub như bây giờ, máy chủ
có sập thì Store vẫn chạy, chỉ thiếu con số.

### Chống gian lận

- Một máy một sao, một lượt cài mỗi gói (khoá chính là cặp mã máy và id gói).
- Giới hạn số sự kiện mỗi phút theo mã máy và theo IP.
- Bản doanh nghiệp: sao gắn với key tài khoản, đáng tin hơn mã máy.

### Quyền riêng tư

- Đếm lượt cài **mặc định bật**, có công tắc tắt trong Cài đặt.
- Ở Store có nút (i) nói rõ Javis gửi những gì.
- Sao là thao tác người dùng tự bấm, nên không cần hỏi thêm.

### Giao diện

- Thẻ gói hiện số sao và lượt cài trên dòng thông tin, ví dụ "★ 128 · 2,3k lượt cài".
- Nút ☆ trên thẻ: bấm để vote, bấm lại để bỏ. Trạng thái đã vote lưu trên máy.
- Ô Sắp xếp thêm: **Nhiều lượt cài**, **Nhiều sao**.
- Có thể thêm **Mới thêm vào kho** nếu danh mục có trường ngày thêm (hiện chỉ có ngày cập nhật
  `updated`).

## Các nơi đặt máy chủ đã cân nhắc

| Lựa chọn | Ưu | Nhược |
|---|---|---|
| Máy chủ trung tâm của bản doanh nghiệp | Dùng chung với quản lý key, gắn được sao với tài khoản | Chưa có, làm cùng bản doanh nghiệp |
| Cloudflare Worker + D1 | Bền, không tạm ngủ, gói miễn phí đủ dùng | Cần API token để triển khai |
| Supabase (bảng + hàm) | Dựng nhanh qua kết nối Supabase có sẵn | Gói miễn phí có thể tạm ngủ khi ít dùng |
| GitHub Releases | Không cần máy chủ, GitHub tự đếm lượt tải | Chỉ có lượt tải, không có sao |

Chủ dự án chọn: **đợi máy chủ trung tâm của bản doanh nghiệp**.

## Việc cần làm khi bắt đầu

1. Máy chủ: bảng `luot_cai`, `sao`, `thong_ke`, hai API ở trên, giới hạn tần suất.
2. Javis (`server/packs_store.py`): tạo mã ẩn danh, gửi sự kiện khi cài, gỡ, sao; tải `thong-ke.json`
   cùng danh mục, có cache như danh mục.
3. Store (`dashboard/packs.js`): hiện số trên thẻ, nút sao, thêm hai lựa chọn vào `SAP`.
4. Cài đặt: công tắc tắt đếm lượt cài, kèm (i) giải thích.
5. Test: không có máy chủ thì Store vẫn chạy đủ; một máy không vote được hai lần.
