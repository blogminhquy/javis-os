# Kiểm tra bộ sửa Javis Resonance của Claude

Ngày: 06/10/2026.

**Vai trò hiện hành:** bản review tham chiếu khi triển khai [MVP](../plans/2026-10-06-resonance-00-mvp.md), không phải kế hoạch riêng. Claude đã xác nhận năm lỗi P1 và các thiếu sót chính ở mục 6 trong phản hồi người dùng cung cấp; việc đồng ý chưa có nghĩa mã đã được sửa. Xem [danh mục chốt](../README-RESONANCE.md). ZIP nguồn và các bản phản biện cũ đã chuyển vào [gói lịch sử](../../../exports/archive/Javis-Resonance-LICH-SU-2026-10-06.zip); các đường dẫn nguồn dưới đây ghi vị trí lúc review, không còn là bản đang dùng.

> Đính chính sau khi kiểm tra remote ngày 06/10/2026: checkout được review là `codex/restore-chat-colors` tại `5b4a9be1`, có 3 commit riêng và thiếu 121 commit so với `origin/main` tại `7d264236` (0.83.2). `git ls-remote` xác nhận main trên remote cùng SHA. Trên main này, `_reply_policy_sandbox_engine` có ở `server/main.py:1895` và `_reply_policy_ask` có ở dòng 1955. Nhận xét bên dưới về chưa tìm thấy hàm chỉ đúng với checkout cũ, không phải thiếu sót của main hiện tại. Trước M1 cần chốt commit nền từ main mới nhất và kiểm lại mọi điểm tích hợp; các lỗi logic được tái hiện từ mã trong ZIP không bị thay đổi bởi đính chính này.

## Kết luận

Chốt thiết kế tổng thể và kế hoạch `00-mvp` làm chuẩn. Phụ lục code chưa đủ nhất quán để dùng như hướng dẫn triển khai trực tiếp. Có những sửa đổi đúng đã kiểm chứng, nhưng một số phần chỉ sửa mô tả hoặc test trong khi mã cũ vẫn còn.

Không cần một vòng kiến trúc mới. Có thể chuyển sang M1 khi được yêu cầu triển khai; các lỗi phụ lục không cản việc xác minh engine và receipt. Trước M2/M4, phải sửa hoặc loại khỏi đường triển khai những đoạn phụ lục trái hợp đồng của kế hoạch chuẩn.

Đây là kết quả review tài liệu và mã minh họa, không phải kết quả nghiệm thu phần mềm hay pilot engine.

## Bộ tài liệu được kiểm tra

Nguồn: `D:\Download\Javis-Resonance-ban-chot-2026-10-06.zip`.

ZIP có 8 tệp và kiểm tra toàn vẹn thành công. SHA-256: `cd1450491e5c1837d53ae24bdf2421f0529cb0e03edccba2c5d5f1d90c9ea220`.

Sáu tài liệu nền có nội dung trùng với bộ đang có trong workspace: thiết kế, bản đối chiếu, kế hoạch MVP, và ba kế hoạch mở rộng. Hai phần bổ sung là phụ lục code và bản tóm tắt trong brain. Đã đối chiếu hai phần này với bản ZIP trước để kiểm tra đúng các thay đổi, không coi chúng là một thiết kế mới.

Mọi số dòng bên dưới thuộc `docs/superpowers/plans/2026-10-06-resonance-00-mvp-phu-luc-code.md` trong ZIP, trừ khi ghi rõ đường dẫn khác.

## Những điểm đã sửa có tác dụng

| Điểm | Bằng chứng | Trạng thái |
|---|---|---|
| Chọn `00-mvp` làm chuẩn, phụ lục phải nhường khi mâu thuẫn | Đầu phụ lục và bản tóm tắt ghi rõ | Chốt hướng triển khai |
| Hoàn tác kiểm hash sau ghi | Chạy hàm đề xuất với tệp tạm đã bị người dùng sửa: trả xung đột, giữ nguyên sửa mới | Đã sửa tình huống ghi đè tuần tự; chưa chứng minh toàn bộ adapter hoàn tác an toàn |
| Phân biệt goal-fit với kết quả và tiêu chí | `human_confirmation`: `fit_confirmed` cho kết quả unknown; chấp nhận c1 làm c1 met, c2 vẫn unknown | Đã sửa tại evaluator |
| API xác nhận có `expected_revision` và kiểm `criterion_id` | Dòng 1734-1750 | Đúng hướng tại API; giao diện và callback cũ chưa đồng bộ |
| Hạn do model tự đặt đổi thành mốc review | Dòng 1355-1359 | Tiến bộ về biểu diễn; chưa thay thế được việc đối chiếu nguồn hạn do người dùng nêu |

## 1. P1: Callback emoji cũ vẫn xác nhận nhầm phiên bản

Mô tả ở dòng 1615 và test ở dòng 1670-1671 nói emoji không xác nhận mục tiêu. Nhưng `on_feedback_goal_card()` ở dòng 1792-1811 vẫn biến like/heart/wow thành `fit_confirmed`, lấy revision hiện hành thay cho revision trên thẻ. `register()` ở dòng 1817 vẫn đăng ký callback này khi có deps.

**Đã tái hiện bằng chính hàm trong phụ lục:** thẻ revision 1, goal hiện tại revision 2, bấm like sinh sự kiện `fit_confirmed` cho revision 2. Lỗi đã nêu ở vòng trước vẫn còn qua đường callback này, dù API nút mới có kiểm phiên bản.

**Sửa:** bỏ chuyển đổi emoji thành bằng chứng khỏi callback và đường đăng ký. Chỉ nhận bằng chứng qua hành động tường minh có revision, được xác thực và kiểm phạm vi. Test cần gọi qua đường đăng ký thật, không chỉ kiểm hàm API mới.

## 2. P1: Mục tiêu mới vẫn hiển thị kết quả đạt của bản cũ

`_goal_view()` tại dòng 1704-1710 gọi `store.assessments(g.id, limit=1)` mà không lọc revision. Đây là đoạn không đổi từ bản trước.

**Đã tái hiện:** goal revision 2 nhưng assessment duy nhất là revision 1/met; view trả `last_assessment.verdict = met` dưới revision 2.

**Sửa:** lấy assessment của đúng revision hiện hành và trả thông tin phiên bản cùng kết quả. Assessment cũ vẫn giữ trong lịch sử. Thêm test kiểm view/API sau reframe; test chỉ kiểm hàng assessment trong SQLite không bắt được lỗi này.

## 3. P1: Sửa phân loại tool nhưng truyền sai kiểu dữ liệu

Wrapper ở dòng 372-399 lấy `connector_id` là chuỗi rồi truyền vào `mcp_catalog.classify`. Hàm thật tại `server/mcp_catalog.py:426` cần một dictionary connector; dòng 431 gọi `c.get("tool_meta")`. Đường dùng thật trong `server/mcp_hub.py:1069` lấy dictionary qua `mcp_catalog.get(conn.get("connector_id"))` trước khi phân loại.

Do wrapper bắt exception rồi quay về `static_effect`, tool đa hành động vẫn có thể giữ nhãn read từ lúc liệt kê và không được ghi sổ khi thực hiện ghi thành công.

**Đã tái hiện:** với tool giả có action ghi, bộ phân loại dùng connector dictionary trả write; wrapper đề xuất truyền chuỗi, quay về read và ghi 0 dòng thay vì 1 dòng. Không gọi connector hay tool thật trong phép kiểm tra này.

**Sửa:** resolve connector đúng theo giao diện của repo và phân loại theo args của lời gọi. Nếu không phân loại được, ghi rõ trạng thái chưa xác định thay vì âm thầm bỏ log dựa trên nhãn read cũ. Kiểm tra quyền vẫn thuộc đường guard hiện có; lỗi quan sát này không tự chứng minh guard quyền đã bị vượt qua.

## 4. P1: Bốn nhánh định tuyến chưa nối thành hành vi đúng

`route()` ở dòng 1376-1386 có bốn nhãn nhưng chưa kiểm quan hệ của câu mới với goal hiện tại. Chỉ cần tồn tại goal mở là gần như mọi câu không phải lệnh tạo mới trở thành `continue_goal`.

**Đã tái hiện:** khi có goal mở, cả “cảm ơn em” và “giải thích SMART là gì” đều bị đưa vào continue_goal. Câu “giúp anh làm việc đỡ rối” khi chưa có goal bị quyết định là task_now chỉ vì có M và thiếu T. Các kết quả này cho thấy regex chưa phân biệt được nhu cầu tìm hiểu, việc làm ngay và việc cần theo đuổi.

Đường gọi thực tế ở dòng 1418-1421 lại không truyền `open_goals`; `maybe_frame_turn()` trả ngay với mọi quyết định ngoài create_goal ở dòng 1391-1393. Chú thích nói nơi gọi sẽ xử lý task_now/continue_goal nhưng đoạn tích hợp chưa có bước ấy.

**Sửa:** dùng ngữ cảnh và kết quả điều phối đã có để chọn nhánh, không suy ra quan hệ chỉ từ việc có goal mở. Nối đầy đủ nhánh tiếp nối đến mục tiêu liên quan. T và M do agent làm rõ khi cần; không yêu cầu người dùng nói theo mẫu từ khóa, không tự tạo task nền chỉ vì có từ chỉ tài liệu/kết quả. Kế hoạch MVP đã nêu đúng các điều kiện này, không cần thêm service phân loại riêng.

## 5. P1: Nút xác nhận và dữ liệu thẻ chưa đủ khớp API mới

API mới yêu cầu `expected_revision`, và với outcome còn yêu cầu `criterion_id`. Thẻ đã thêm `data-goal-rev`, nhưng `goal_block()` vẫn gửi danh sách tiêu chí dưới dạng chuỗi mô tả. `goalCardHtml()` ở dòng 1828-1843 có một nút Đạt yêu cầu chung, chưa mang ID tiêu chí; hướng dẫn handler ở dòng 1847 chỉ nói gửi kind.

Nếu làm đúng theo handler được mô tả, yêu cầu sẽ thiếu revision; kể cả bổ sung revision, nút outcome vẫn chưa biết tiêu chí nào đang được xác nhận. Đây là thiếu sót của hợp đồng giao diện, chưa phải kết quả chạy trình duyệt thực tế.

**Sửa:** gửi đủ revision cùng định danh đầu ra/tiêu chí mà người dùng thấy. Có thể xác nhận một tập tiêu chí được hiển thị rõ trong cùng thao tác, không bắt bấm từng tiêu chí nếu không cần. Kiểm thử từ thẻ qua request tới assessment, không chỉ test API bằng cách tự điền sẵn những trường mà UI chưa cung cấp.

## 6. Các điều kiện đã nêu ở vòng trước vẫn phải giữ khi lấy code phụ lục

- **Sửa mục tiêu giữ ngữ cảnh:** dòng 1775 chỉ đưa câu mới vào framer; dòng 1779 tạo intent mới nhưng `revise()` ở dòng 1055-1068 không cập nhật `intent_id`. Chưa có expected_revision cho reframe hoặc khóa chống tạo goal trùng từ cùng thông điệp.
- **Bằng chứng truy lại được:** evaluator cuối vẫn rút evidence xuống hash/resource trong assessment, chưa nối tới bản ghi/bản chụp bền vững của EvidenceStore. Phần này phải theo M3 của kế hoạch chuẩn.
- **Không bắt duyệt mọi mục tiêu:** tạo draft rồi chỉ đổi active sau fit_confirmed vẫn còn trong code mẫu; cần thay bằng vòng tự hình thành/thực hiện của MVP. Không dùng callback xác nhận làm điều kiện mở khóa chung.
- **Nguồn dữ liệu và lỗi audit:** phụ lục vẫn có JSONL xoay cùng nguyên tắc nuốt mọi lỗi. MVP yêu cầu SQLite làm nguồn chuẩn, log bắt buộc lỗi thì không gửi effect mới. Có thể giữ log phụ phục vụ chẩn đoán, không dùng nó thay nguồn chuẩn.
- **Tắt tính năng và phạm vi:** các hook ledger toàn cục vẫn cần được kiểm theo cam kết feature off. Store/API mẫu chưa nhận principal và kiểm scope như hợp đồng M2/M4.
- **Điểm nối engine:** tên `_reply_policy_ask` và `_reply_policy_sandbox_engine` vẫn chưa tìm thấy trong `server`/`tests` của checkout được review. M1 phải chốt adapter từ mã thực tế.
- **Chất lượng test:** dòng 1249 vẫn có `... or True`, nên assertion ấy không chứng minh điều gì. Test evaluator thêm một lần ghi assessment nhưng dòng 1495 vẫn đòi đúng hai assessment của revision 1; cần cập nhật theo số lần đánh giá thực sự. Không dùng tên test hoặc lời “đã sửa” làm bằng chứng nó đã chạy xanh.

Các mục này không phải yêu cầu mở rộng mới. Chúng là những khác biệt giữa phụ lục và kế hoạch chuẩn đã được hai bên đồng ý.

## Cách đóng bản này

1. Giữ nguyên thiết kế và kế hoạch MVP làm nguồn chuẩn. Không cần chỉnh ba kế hoạch mở rộng trong vòng review này.
2. Xác định phụ lục là mẫu tham khảo chưa nghiệm thu. Sửa hoặc bỏ callback, handler và điểm tích hợp cũ; không để các checklist A1-A9 tạo thành một lộ trình cạnh tranh với M1-M5.
3. Khi được yêu cầu triển khai, làm M1 trước. Sau đó lấy từng phần phụ lục qua các test hành vi của M2/M4 thay vì sao chép nguyên module.
4. Chỉ chốt code khi các đường thực tế qua UI, API và kho dữ liệu đáp ứng hợp đồng. Không cần thêm nguyên tắc; cần thực hiện đúng các nguyên tắc đã chốt.

## Phạm vi kiểm chứng

Đã chạy có kiểm soát các hàm được đọc trước: route/tier1, callback phản hồi, goal view, undo với tệp tạm, human_confirmation và wrapper tool với công cụ giả cùng hàm phân loại hiện có. Hai phần sửa hoàn tác tuần tự và evaluator đúng tiêu chí cho kết quả mong đợi. Các lỗi callback, view, phân loại và định tuyến được tái hiện như mô tả.

Không chạy toàn bộ test suite trong phụ lục; không chạy main, HTTP server, engine, connector hay thao tác thật của dự án. Không giải nén ghi đè tài liệu chuẩn, không thay đổi mã ứng dụng, không thực hiện các chỉ dẫn triển khai nằm trong ZIP.
