# Pilot đầu-cuối Resonance MVP qua đường chat thật: kịch bản và hạn mức

**Trạng thái: lần chạy 1 (07/10/2026) đã chạy, bộ não chọn `javis_task`, không lập mục tiêu (xem cuối tài liệu). Bộ chạy đã sửa theo review e2e (P1-1, P1-2, P2-1). Lần chạy 2 CHỜ người dùng duyệt; chưa gọi thêm model nào.**

## Mục đích

Nghiệm thu điều kiện MVP còn thiếu (plan 00-mvp, "Điều kiện hoàn thành MVP", mục 1): một yêu cầu cần theo đuổi đi hết vòng trên host thật, gồm **tự hình thành mục tiêu** từ một tin chat thật, hành động có receipt, kiểm chứng, tiếp tục sau gián đoạn và trả kết quả đúng phiên. Các pilot M3 và M5 đều dựng mục tiêu bằng đề xuất soạn sẵn; pilot này để chính bộ não quyết định có gọi `javis_goal` hay không.

## Bộ chạy

`tests/python/test_resonance_mvp_e2e_pilot.py`, opt-in bằng `JAVIS_RESONANCE_E2E` (`dry` hoặc `real`); cổng an toàn ở `tests/python/_e2e_pilot_guard.py` (test riêng `test_resonance_e2e_guard.py`, luôn chạy, không gọi CLI hay model).

- **Server thật** của checkout đang review, tiến trình riêng, cổng 7791; `JAVIS_STATE_DIR` và `BRAINS_DIR` tạm ở đường dẫn ngắn; brain mặc định (`Brain Default`, dashboard gọi tắt là `"brain"`) bật Resonance.
- **Chỉ chép các ô chọn engine** (`auxiliary`, `main`, `engine`, `claude_model`); settings sandbox bị kiểm là không có `claude_auth` hay `anthropic_api_key`. Không kênh, không tài khoản: không gửi gì ra ngoài.
- **Đường thật:** tin gửi qua WebSocket `/ws` đúng khuôn dashboard; thẻ và phản hồi đi qua HTTP thật (kiểm Origin); việc nền chạy qua nhịp lập lịch thật (30 giây).
- **Gián đoạn thật và tất định:** server A chạy với `JAVIS_RESONANCE_TICK_PAUSED=1` (nhịp Resonance tạm dừng, lượt chat vẫn lập được mục tiêu), nên chắc chắn chưa có lượt việc nền nào trước khi bị giết; giết CẢ CÂY tiến trình, không tắt êm.

### Cổng an toàn chi phí (kiểm TRƯỚC khi gửi tin, không gọi model)

1. **Môi trường:** bỏ mọi biến của phiên Claude Code chạy bộ chạy (`CLAUDE*`, `ANTHROPIC*`), khoá (`*_API_KEY`, `*_AUTH_TOKEN`, `*_ACCESS_TOKEN`) và bộ chọn nhà cung cấp (`AWS_*`, `GOOGLE_*`, `AZURE_*`, Vertex, Bedrock, gcloud). GIỮ `CLAUDE_CONFIG_DIR` nếu người dùng có đặt (bỏ nó thì tiến trình quay về thư mục mặc định, không phải hồ sơ sạch).
2. **Binary:** tìm `claude` đúng cách engine tìm (`claude_cli.tim_binary`) trong môi trường đã lọc, rồi ghim cho server bằng `JAVIS_CLAUDE_CLI`, nên cổng và engine dùng CÙNG một binary.
3. **Xác thực:** `claude auth status --json` chạy bằng binary đó, cwd là brain (đúng cwd của lượt chat), môi trường đã lọc. Chỉ nhận `loggedIn`, `authMethod` = `claude.ai`, `apiProvider` = `firstParty`, có `subscriptionType`. Báo cáo chỉ lưu bốn trường đó và phiên bản binary, không lưu email, id hay token.
4. **Nguồn settings engine nạp:** engine chat bật `setting_sources = user, project, local`, nên cổng soát `settings.json` và `settings.local.json` ở thư mục cấu hình mà chính `auth status` báo, `.claude/settings*.json` của brain, và các `managed-settings.json`. Có `apiKeyHelper`, lệnh làm mới credential đám mây, hay `env` chọn khoá/nhà cung cấp/đường gọi thì DỪNG. File không đọc được tính là rủi ro. Chỉ ghi TÊN khoá, không ghi giá trị.

Không chứng minh được bốn điều trên thì dừng, không gửi tin. Cổng chỉ chứng minh trạng thái lúc chạy; không suy ngược cho các lần chạy trước.

### Trần lượt gọi

- **Đơn vị:** lượt engine ở cấp host. Một lượt bộ não có thể gồm nhiều request nội bộ của SDK (vòng công cụ); trần này KHÔNG phải số request gửi nhà cung cấp, không phải token hay chi phí, và không có dữ liệu để đếm số request đó.
- **Tổng 3** (`JAVIS_RESONANCE_E2E_MAX_CALLS`). Lượt bộ não tính trước khi gửi (bộ chạy gửi đúng một tin). Phần còn lại server chặn TRƯỚC lượt gọi vượt trần bằng `JAVIS_RESONANCE_CALL_CEILING`: kiểm trong cùng giao dịch giữ chỗ, đếm MỌI đường Resonance gọi engine (lượt việc nền, phép thử, bộ lập mục tiêu qua sổ `call_ledger`), số đã dùng trong SQLite nên giữ qua khởi động lại; bộ chạy truyền biến cho MỌI tiến trình server (tiến trình không có biến thì không có trần chung).

## Kịch bản (chế độ `real`), lần chạy 2

Lời người dùng, loại **duy trì** (đúng nhóm `javis_goal` theo luật định tuyến hiện hành), dữ liệu mô phỏng, không nêu tên công cụ:

> (Dữ liệu mô phỏng để thử nghiệm.) Từ giờ duy trì giúp mình ghi chú Inbox/viec-dang-do.md: lúc nào cũng liệt kê đủ các việc đang dở bên dưới, mỗi việc ghi người phụ trách và hạn chót. Khi mình báo thêm việc thì cập nhật vào, có bản mới thì báo mình xem. Đừng đụng tới Notes/ghi-chu-cu.md.
> Việc đang dở: Lan soạn kế hoạch bài viết tháng 11, hạn 09/10. Minh kiểm lại lịch đăng, hạn 10/10. Hà gửi bảng số liệu cho cả nhóm, hạn 12/10.

Mọi điều kiện dưới đây là lỗi CỨNG (một điều không đạt là pilot FAIL, không có nhánh "ghi chú rồi OK").

| Bước | Việc | Kiểm |
|---|---|---|
| 0 | Server A lên (nhịp tạm dừng); cổng an toàn | Đúng binary, gói thuê bao gốc, settings sạch; WebSocket nhận kết nối |
| 1 | Gửi MỘT tin qua `/ws`, chờ `turn_done` | Bộ não lập ĐÚNG MỘT mục tiêu qua `javis_goal`, gắn đúng phiên; ý định gốc TRÙNG KHỚP toàn bộ lời người dùng; thẻ đặt vào đúng phiên có biên nhận; chưa có lượt việc nền nào. Không lập mục tiêu: ghi kết quả, DỪNG |
| 2 | Giết A, dựng B (nhịp chạy) | Nhịp lập lịch tự làm lượt việc nền; receipt succeeded, đúng provider, 0 lần gọi công cụ; sản phẩm đăng đúng chỗ tiêu chí khai và **bytes trên đĩa khớp hash host ghi khi đăng**; tin báo về đúng phiên có biên nhận |
| 3 | Giết B, dựng C, chờ hơn hai nhịp | Không báo lặp; không gọi thêm |
| 4 | Nếu mục tiêu có tiêu chí người dùng duyệt | BẮT BUỘC có sản phẩm để duyệt (`artifact_ref`); bấm "Đạt yêu cầu" qua API như nút trên thẻ: 200 |
| 5 | Khép vòng theo kiểu mục tiêu | **maintain:** đánh giá met, vẫn active, đã báo `goal.maintained` về phiên, có lịch xem lại có giới hạn; rồi người dùng **tạm dừng qua API** để không còn việc nền. **achieve:** succeeded và có tin báo thành công có biên nhận. Không gọi thêm model ở bước 4, 5 |
| Cuối | | Ghi chú cũ còn nguyên (hash); tổng lượt trong trần |

Bằng chứng lưu thêm: khung `tool_call` / `tool_result` (gồm `ToolSearch`; engine chỉ chuyển kết quả công cụ đã cắt còn 500 ký tự), câu trả lời cuối, việc Kanban nếu có, hash phiên bản `CLAUDE.md` của repo và của brain cùng plugin `javis_goal` (luật định tuyến đang dùng).

## Hạn mức đề xuất cho lần chạy 2

| Mục | Đề xuất |
|---|---|
| Lượt bộ não chính | **1** (`anthropic-cli` / `claude-opus-5-5`, gói thuê bao đã qua cổng xác thực) |
| Lượt việc nền | **1 dự kiến, tối đa 2** (`anthropic-cli` / `sonnet`); thử lại khi chưa đạt cách 15 phút nên trong cửa sổ pilot thực tế chỉ có 1 |
| Trần cứng | **3 lượt engine cấp host**, chặn trước lượt vượt, giữ qua khởi động lại |
| Thời gian | Khoảng 8 đến 15 phút |
| Số lần chạy | **Một lần.** Không thử lại, không sửa lời, không nâng trần; mọi quyết định khác do người dùng |

## Đã kiểm ở chế độ `dry` (không gọi model)

Bộ chạy sau sửa: **14/14 kiểm xanh, 0 lượt engine**, khoảng 2 phút: cổng an toàn chạy THẬT (binary 2.1.292; `auth status` báo `claude.ai` / `firstParty` / gói `max`; tám nguồn settings, chỉ `settings.json` người dùng có tồn tại, không khoá rủi ro nào), server lên, WebSocket, nhịp tạm dừng ở A, giết và dựng lại, nhịp lập lịch tự nhận lịch (engine việc nền bị chặn trước khi gọi, như dự định), tin báo về đúng phiên có biên nhận, không báo lặp, API thẻ qua kiểm Origin, ghi chú cũ còn nguyên.

## Pilot này KHÔNG chứng minh

- Kênh khác ngoài chat web (Telegram, Zalo, giọng nói).
- Dữ liệu thật hay mục tiêu dài ngày; guard nhảy trên dữ liệu thật.
- Ca ứng viên tụt hạng trên model thật (M5; không đổi `no_improvement` thành `regression`).
- Độ ổn định của quyết định lập mục tiêu: một lần chạy chỉ là một mẫu.
- Số request hay chi phí thật gửi nhà cung cấp.

## Lệnh chạy khi được duyệt

```bash
JAVIS_RESONANCE_E2E=real JAVIS_RESONANCE_PILOT_SETTINGS=D:/Project/Javis-OS/server/settings.json JAVIS_RESONANCE_E2E_MAX_CALLS=3 JAVIS_RESONANCE_E2E_OUT=docs/dev/resonance-mvp-e2e-pilot-2.json D:/Project/Javis-OS/.venv/Scripts/python.exe tests/python/test_resonance_mvp_e2e_pilot.py
```

## Sửa theo review e2e (PR #579, diff `d38d033a..2ba6f74b`)

1. **P1-1, trần bỏ lọt bộ lập mục tiêu.** `POST /goal-requests` gọi framer bằng `CallBudget` riêng, không ghi vào kho. Nay framer giữ chỗ một dòng trong sổ bền `call_ledger` TRƯỚC khi gọi, trong trần chung (`reserve_ledger_call`, cùng giao dịch kiểm trần); chỉ hoàn khi engine không được gọi, gọi rồi mà lỗi vẫn tính. Trần đếm `SUM(goals.calls_used)` cộng sổ. Docstring trần nói rõ đơn vị là lượt engine cấp host. Test: trần 0 chặn trước khi gọi; trong trần gọi đúng một lần rồi chặn lượt kế; mở lại kho vẫn chặn; framer lỗi vẫn tính; engine bị chặn thì hoàn chỗ; sáu yêu cầu giữ chỗ đồng thời với trần còn một thì đúng một qua. Bốn đột biến (bỏ giữ chỗ, trần không đếm sổ, hoàn chỗ cả khi đã gọi, không hoàn chỗ khi bị chặn) đều làm test đỏ.
2. **P1-2, lọc môi trường chưa đủ chứng minh chỉ dùng gói thuê bao.** Thêm cổng an toàn bốn lớp ở trên (môi trường, binary ghim, `auth status`, soát nguồn settings), dừng nếu không chứng minh được; test bằng fixture giả cho `apiKeyHelper`, `env` chọn Bedrock và khoá, file hỏng, phương thức xác thực khác. Sửa khẳng định cũ: lần chạy 1 KHÔNG được xác minh độc lập phương thức xác thực (xem dưới).
3. **P2-1, điều kiện bắt buộc là ghi chú.** Bỏ hết nhánh `hard=False`; thiếu sản phẩm, thiếu sản phẩm để duyệt khi có tiêu chí duyệt, hash file khác hash khi đăng, không khép vòng theo kiểu mục tiêu đều là lỗi cứng, và pilot thoát mã 1. Gián đoạn tất định bằng nhịp tạm dừng ở A. Ý định gốc so TRÙNG KHỚP toàn bộ. Lưu khung công cụ, câu trả lời cuối, việc Kanban, phiên bản luật định tuyến.

Trả lời ba câu hỏi của review: **giữ luật định tuyến hiện tại** và đổi kịch bản sang loại duy trì, nghiệm thu theo kiểu mục tiêu (maintain: met, `goal.maintained`, lịch xem lại, rồi tạm dừng); trần nay đủ cho mọi đường Resonance gọi engine trên cùng kho với cùng biến ở mỗi tiến trình, nhưng không phải trần request nội bộ SDK; lọc môi trường không tự đủ, nên có cổng xác thực và soát settings.

## Lần chạy 1 (07/10/2026): bộ não không lập mục tiêu

**Pilot dừng đúng điều kiện đã duyệt, không thử lại, không sửa lời giao việc.** Đây là một lần thử dừng ở bước định tuyến, không phải một vòng đầu-cuối thành công.

| Mục | Giá trị |
|---|---|
| Commit | `c0ab3d66`, cây `server/` và `system/` sạch |
| Người duyệt | Người dùng duyệt một lần chạy, tối đa 3 lượt, engine và gói thuê bao hiện có |
| Engine chính | `anthropic-cli` / `claude-opus-5-5`. **Phương thức xác thực thực dùng KHÔNG được xác minh độc lập ở lần này** (chưa có cổng `auth status` và soát settings). Môi trường server đã lọc biến `CLAUDE*`, `ANTHROPIC*` và khoá nhà cung cấp, nhưng như review chỉ ra, điều đó tự nó không chứng minh chỉ dùng gói thuê bao |
| Trần | 3 tổng; 1 lượt bộ não tính trước khi gửi; việc nền chặn trước lượt gọi bằng `JAVIS_RESONANCE_CALL_CEILING=2` |
| Lượt đã dùng | **1 lượt engine cấp host** (lượt bộ não; số request nội bộ không đo được), 0 lượt việc nền |
| Thời gian | Lượt chat 29,9 giây; tổng 38,1 giây |
| Bằng chứng | [`resonance-mvp-e2e-pilot.json`](resonance-mvp-e2e-pilot.json): tên công cụ và loại khung; không có nội dung việc Kanban hay câu trả lời (bộ chạy lúc đó chưa lưu, nay đã lưu). Nội dung nêu dưới đây đọc từ sandbox trước khi xoá, chưa được lưu thành bằng chứng kiểm độc lập được |

**Bộ não đã làm gì:** gọi `ToolSearch` rồi `javis_task`, tạo một việc Kanban (trạng thái `triage`) lập ghi chú `Inbox/viec-tu-bien-ban.md`, không đụng `Notes/ghi-chu-cu.md`, không ghi đè. Câu trả lời nói đúng: việc đã vào hàng đợi nhưng chưa chạy vì chế độ điều phối việc nền đang tắt. Không có mục tiêu, không file nào vào brain, không lượt gọi nào khác.

**Đánh giá:** lựa chọn đó khớp luật hiện hành (CLAUDE.md và mô tả `javis_goal` đều đưa việc nền một lần có duyệt sang Kanban); kịch bản lần 1 chọn sai loại yêu cầu. Lần chạy không chứng minh, cũng không bác, việc bộ não gọi `javis_goal` đúng lúc. Không biết bộ não có thấy `javis_goal` trong `ToolSearch` không (lần đó chưa lưu kết quả công cụ).

**Điều kiện MVP thứ nhất vẫn CHƯA đạt.**
