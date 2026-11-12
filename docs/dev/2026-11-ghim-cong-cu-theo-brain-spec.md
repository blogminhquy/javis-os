# Ghim sẵn công cụ hay dùng theo từng brain

Spec viết ngày 10/11/2026, đi tiếp sau `2026-11-vong-cai-tien-javis-core-spec.md` (mục 6.3). Chủ repo chốt: "Nên làm
ngay: ghim sẵn công cụ hay dùng theo từng brain".

## 1. Vấn đề

Khi một brain đấu nhiều nguồn, hub giấu các công cụ sau hai công cụ `javis_search_tools` và `javis_run_tool` để mỗi
request nhẹ đi. Cái giá: công cụ nào dùng hằng ngày cũng tốn thêm MỘT VÒNG gọi model mỗi lần (tìm trước, rồi mới gọi).
Một vòng là đọc lại toàn bộ ngữ cảnh, nên đây là phần đắt, nhất là với loop: mỗi vòng lặp là một phiên mới, lần nào
cũng phải tìm lại.

Số đo trên máy của chủ repo (brain Minh Quý): 1.065 lượt gọi trên 49 công cụ, 6 công cụ đầu chiếm 64%, 10 công cụ đầu
chiếm 79%. Tức là ghim vài công cụ là bớt được phần lớn số vòng tìm.

## 2. Cách làm

| Thành phần | Là gì | Nằm ở đâu |
|---|---|---|
| **Bộ đếm** | Mỗi brain đếm công cụ nào (trong nhóm bị giấu) được gọi, và bao nhiêu lần phải tìm trước | `tool_pins.note_run`, `note_search`; móc trong `mcp_hub._lazy_tools_and_route` |
| **Danh sách ghim** | Vài công cụ brain đó gọi nhiều nhất, được hiện thẳng cạnh nhóm công cụ lõi | `tool_pins.pick`, `tick`; `mcp_hub._apply_lazy` |
| **Núm** | Mỗi brain được ghim tối đa mấy công cụ: `tools.pin_limit`, 0 đến 8, mặc định 4, 0 là tắt | `core_loop` (đăng ký ở `main.py`) |

Luật chọn danh sách (mã thuần, `tool_pins.pick`):

- Một công cụ được ghim khi có đủ lượt gọi gần đây (từ 5, tính theo trọng số) VÀ chiếm từ 3% số lượt gọi của brain.
- Mỗi ngày không được gọi, lượt gọi cũ nhẹ đi 10% (sau khoảng một tuần còn một nửa). Thói quen cũ tự phai.
- Công cụ đã ghim giữ chỗ cho tới khi tụt dưới NỬA ngưỡng trên, để danh sách không chập chờn.
- Hết chỗ: công cụ được gọi gấp đôi công cụ ghim yếu nhất thì thế chỗ; chưa tới mức đó thì "chờ chỗ".
- Danh sách của một brain đổi nhiều nhất một lần mỗi ngày, giữ nguyên thứ tự cũ, cái mới xếp cuối. Lý do: danh sách
  công cụ nằm ở đầu prompt, mỗi lần đổi là một lần nhà cung cấp phải đọc lại phần đã lưu đệm.

Luật của núm (`tool_pins.limit_rule`, chạy trong vòng của Javis Core, mỗi ngày nhiều nhất một bước):

- Có brain đang có công cụ "chờ chỗ" thì thêm một chỗ (tối đa 8).
- Núm đang trên mặc định mà không brain nào dùng hết chỗ thì bớt một chỗ.
- Núm bằng 0 nghĩa là chủ đã tắt: luật không tự bật lại.

Hai giới hạn không luật nào dời, kiểm ở MỌI request chứ không chỉ lúc chọn: một công cụ không quá 2.000 ký tự (tên, mô
tả, schema), tổng các công cụ ghim của một brain không quá 5.000 ký tự (khoảng 1.400 token). Nhờ vậy model bị siết hạn
mức nhất vẫn vừa.

## 3. An toàn

- Công cụ ghim vẫn đi qua đúng lớp quyền, audit và hook như cũ: route của nó chỉ được bọc thêm một bộ đếm.
- Mức quyền hiện tại không có công cụ đó (ví dụ loop ở mức chỉ đọc, công cụ ghi) thì công cụ ghim không hiện.
- Công cụ ghim vẫn nằm trong nhóm tìm được, nên tìm rồi gọi kiểu cũ vẫn chạy.
- Chat của chủ và việc nền của một brain dùng chung một danh sách. Chatbot trả lời khách của brain đó có danh sách
  riêng, để việc khách hay hỏi không chiếm chỗ ghim của chủ.
- Khi nhóm công cụ không bị giấu (brain ít công cụ) thì không có gì thay đổi: mọi công cụ vốn đã hiện thẳng.

## 4. Người dùng thấy gì

Không có màn hình hay ô cài đặt mới.

- **Chuông.** Khi một brain có công cụ mới được ghim: một thông báo mức thấp nêu brain, tên công cụ và câu để tắt.
- **Nói với Javis.** "Đang ghim công cụ nào" (`javis_tune op=status`, mục `pinned_tools`: danh sách ghim, số lượt gọi
  thẳng, số lượt còn phải tìm trước). "Đừng ghim công cụ nữa" (`javis_tune op=set knob=tools.pin_limit value=0`).
- Giá trị chủ đặt thì luật để yên 30 ngày (luật mới của vòng, áp cho mọi núm).

## 5. Hiệu năng

- Một lượt gọi công cụ thêm một phép cộng trong bộ nhớ. Không ghi đĩa trong lượt gọi.
- `tool_pins.tick` chạy 10 phút một lần ở luồng phụ, cùng nhịp với vòng của Javis Core; chỉ ghi một tệp JSON nhỏ
  (`STATE_DIR/tool-pins.json`) khi có gì đổi. Mỗi brain theo dõi tối đa 120 công cụ.
- Đọc danh sách ghim ở lượt chat là tra một dict trong bộ nhớ. Danh sách ghim nằm trong khoá cache của hub, nên đổi
  ghim không phải xoá cache hay đóng kết nối MCP.
- Không gọi model ở bất kỳ đâu.

## 6. Chưa làm, chưa kiểm

- Số "vòng tìm đã bớt" là suy ra từ số lượt gọi thẳng: một lần tìm có thể phục vụ nhiều lượt gọi trong cùng một lượt
  chat, nên con số thật thấp hơn hoặc bằng số lượt gọi thẳng. Chưa có số đo token trước và sau trên máy thật.
- Chưa tự hoàn tác theo số đo (mục 6.2 của spec vòng cải tiến).
- Hub không biết engine nào đang hỏi, nên giới hạn ký tự là một mức chung cho mọi engine.
- Bộ đếm của plugin `tool-audit` (tắt mặc định, không tách theo brain) không được dùng làm dữ liệu khởi đầu; bộ đếm
  mới bắt đầu từ 0 sau khi cập nhật, công cụ dùng thường xuyên được ghim sau vài lượt gọi.
