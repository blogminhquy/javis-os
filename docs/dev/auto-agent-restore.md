# Auto: trợ lý có file trở lại, khi nào hỏi và khi nào không (2026-11-11)

Bổ sung cho hợp đồng A1 (`missing` cần chủ dự án xác nhận). Mã: `server/agent_presence.py`,
`GoalStore.agent_restore` / `agent_set_origin` / `agent_origins` trong `server/resonance_store.py`,
`pack_vault.agent_packs`. Test: `tests/python/test_pack_reinstall_auto.py`, `tests/js/test_pack_confirm_ui.js`.

## Báo lỗi

Brain PSC Advisor, gói "ECC: Đội lập trình" (17 trợ lý). Gỡ gói rồi cài lại từ Store: cả 17 thẻ báo
"Auto: Cần xác nhận", phải mở từng thẻ bấm "Đúng trợ lý cũ". Lần cài lại sau lại y như vậy.

Nguyên nhân: gỡ gói xoá file trợ lý thẳng trên đĩa, sổ Auto thấy file mất thì chuyển mã sang `missing`. File
có lại cùng tên không tự mở, vì theo A1 một file khác đội tên cũ không được thừa hưởng Auto đang chạy. Luật đó
đúng, nhưng không phân biệt được "gói đặt lại đúng trợ lý của nó" với "một file lạ trùng tên".

## Luật mới

Host tự đưa mã `missing` về `active`, GIỮ NGUYÊN mã (như chủ bấm "Đúng trợ lý cũ"), trong đúng hai trường hợp
không có gì để quyết:

1. **Cùng nguồn gốc.** Lúc mã còn `active`, host ghi nguồn gốc file của nó: `pack:<mã gói>` khi file do gói đặt
   vào và chưa ai sửa, rỗng khi là file của người dùng. Mã `missing` có file trở lại, file đó là file nguyên bản
   của ĐÚNG gói đã ghi, thì nhận lại. Công tắc, mục tiêu, cuộc trò chuyện đi tiếp; mục tiêu được hẹn thức như
   sau khi chủ xác nhận.
2. **Không có gì đang mở.** Auto của mã đang tắt và mã không có mục tiêu nào đang mở: xác nhận kiểu nào cũng
   không có gì tự chạy, và bật Auto sau đó là quyết định của chính chủ về file đang có.

Vẫn hỏi như cũ: Auto đang bật hoặc còn mục tiêu mở, mà file trở lại KHÔNG phải file nguyên bản của gói đã ghi
(file người dùng tự viết, file gói đã bị sửa, file của một gói khác, hay gói đặt file lên tên của một trợ lý
vốn là của người dùng).

Mỗi lần nhận lại ghi một sự kiện `restored` (lý do `same_origin` hay `nothing_open`) và tăng `config_version`,
nên mọi cổng đang giữ version cũ vẫn thấy thay đổi. Nguồn gốc là sự kiện `origin`, không đổi version.

## Chạy ở đâu

`agent_presence.sync(store, root, slugs)` là chỗ DUY NHẤT làm ba việc: chốt `missing`, ghi nguồn gốc, nhận lại.

- `GET /resonance/agents` (trang Cộng sự, trang Cài đặt): như trước đã chốt `missing` ở đây.
- `POST /packs/install`: ngay sau khi gói đặt file, để nhóm và mục tiêu dùng lại được trợ lý mà không cần ai
  mở trang Cộng sự.
- `POST /packs/uninstall`: một lần TRƯỚC khi xoá file (ghi nguồn gốc cho mã chưa kịp ghi), một lần sau.

Hai route gói báo các tab đang mở bằng gói WS `resonance_agents` khi có trạng thái đổi.

## Nút xác nhận cả gói

Máy nâng cấp từ bản cũ có thể đang giữ các mã `missing` chưa từng được ghi nguồn gốc. Mã nào Auto tắt và không
có mục tiêu mở thì tự về theo luật 2. Mã còn lại vẫn phải hỏi, nhưng hỏi một lần cho cả gói:

- `GET /resonance/agents` trả thêm `pack` và `pack_name` cho trợ lý có file nguyên bản của một gói.
- Trang Cộng sự: gói có từ hai trợ lý đang chờ thì dưới thanh lọc hiện một dòng "N trợ lý của gói X cần xác nhận
  Auto" kèm nút "Đúng trợ lý cũ, xác nhận tất cả". Một trợ lý lẻ thì trả lời trên thẻ của nó như cũ.
- Nút gửi `POST /resonance/agents/confirm` với `{pack, same: true}`. Server tự tính tập mã (đang `missing`, file
  có lại, là file nguyên bản của gói đó), không nhận danh sách từ trình duyệt. Chỉ có "đúng trợ lý cũ"; coi là
  trợ lý mới vẫn là quyết định từng trợ lý, trên bảng của trợ lý đó.

Sau lần xác nhận này nguồn gốc được ghi, nên các lần cài lại sau không hỏi nữa.

## Giới hạn

- Gói đổi mã (`replaces`): gỡ gói mã cũ rồi cài thẳng gói mã mới thì nguồn gốc không khớp, vẫn hỏi (một lần, có
  nút cả gói). Cập nhật tại chỗ qua `replaces` thì file không hề mất nên không có gì để hỏi.
- File gói mà người dùng đã sửa không được tính là "của gói": gỡ gói giữ lại file đó (mã vẫn `active`), và nếu
  nó mất rồi có lại thì hỏi như file của người dùng.
