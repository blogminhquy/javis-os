# Pilot đầu-cuối Resonance MVP qua đường chat thật: kịch bản và hạn mức

**Trạng thái: đã chạy HAI lần theo hạn mức người dùng duyệt (07/10/2026). Cả hai lần bộ não KHÔNG lập mục tiêu (lần 1 chọn `javis_task`, lần 2 tự làm luôn trong lượt). Điều kiện MVP thứ nhất CHƯA đạt. Không chạy thêm khi người dùng chưa quyết hướng tiếp theo.**

## Mục đích

Nghiệm thu điều kiện MVP còn thiếu (plan 00-mvp, "Điều kiện hoàn thành MVP", mục 1): một yêu cầu cần theo đuổi đi hết vòng trên host thật, gồm **tự hình thành mục tiêu** từ một tin chat thật, hành động có receipt, kiểm chứng, tiếp tục sau gián đoạn và trả kết quả đúng phiên. Các pilot M3 và M5 đều dựng mục tiêu bằng đề xuất soạn sẵn; pilot này để chính bộ não quyết định có gọi `javis_goal` hay không.

## Bộ chạy

`tests/python/test_resonance_mvp_e2e_pilot.py`, opt-in bằng `JAVIS_RESONANCE_E2E` (`dry` hoặc `real`); cổng an toàn ở `tests/python/_e2e_pilot_guard.py` (test riêng `test_resonance_e2e_guard.py`, luôn chạy, không gọi CLI hay model).

- **Server thật** của checkout đang review, tiến trình riêng, cổng 7791; `JAVIS_STATE_DIR` và `BRAINS_DIR` tạm ở đường dẫn ngắn; brain mặc định (`Brain Default`, dashboard gọi tắt là `"brain"`) bật Resonance.
- **Chỉ chép các ô chọn engine** (`auxiliary`, `main`, `engine`, `claude_model`); settings sandbox bị kiểm là không có `claude_auth` hay `anthropic_api_key`. Không kênh, không tài khoản: không gửi gì ra ngoài.
- **Đường thật:** tin gửi qua WebSocket `/ws` đúng khuôn dashboard; thẻ và phản hồi đi qua HTTP thật (kiểm Origin); việc nền chạy qua nhịp lập lịch thật (30 giây).
- **Gián đoạn thật và tất định:** server A chạy với `JAVIS_RESONANCE_TICK_PAUSED=1` (nhịp Resonance tạm dừng, lượt chat vẫn lập được mục tiêu), nên chắc chắn chưa có lượt việc nền nào trước khi bị giết; giết CẢ CÂY tiến trình, không tắt êm. Mọi biến của pilot thừa kế từ shell cha (nhịp tạm dừng, trần, binary, thư mục) bị XOÁ trước khi dựng mỗi server rồi đặt lại đúng giá trị; báo cáo ghi trạng thái hiệu lực của từng server (`servers`).

### Cổng an toàn chi phí (kiểm TRƯỚC khi gửi tin, không gọi model)

0. **Engine sẽ chạy đúng cấu hình đã duyệt** (review e2e vòng 2): resolve bộ não chính và việc nền bằng chính luật runtime (`aux_engine.main_spec`, `read_spec`, kèm `claude_model`) trên settings sandbox, so với cấu hình người dùng duyệt (lần 2: `anthropic-cli` / `claude-opus-5-5` cho bộ não, `anthropic-cli` / `sonnet` cho việc nền). Khác hoặc không resolve được thì dừng, không tự đổi model. Báo cáo ghi lựa chọn đã resolve. Chế độ `dry` kỳ vọng riêng: việc nền là provider bị chặn.
1. **Môi trường:** bỏ mọi biến của phiên Claude Code chạy bộ chạy (`CLAUDE*`, `ANTHROPIC*`), khoá (`*_API_KEY`, `*_AUTH_TOKEN`, `*_ACCESS_TOKEN`) và bộ chọn nhà cung cấp (`AWS_*`, `GOOGLE_*`, `AZURE_*`, Vertex, Bedrock, gcloud). GIỮ `CLAUDE_CONFIG_DIR` nếu người dùng có đặt (bỏ nó thì tiến trình quay về thư mục mặc định, không phải hồ sơ sạch).
2. **Binary:** tìm `claude` đúng cách engine tìm (`claude_cli.tim_binary`) trong môi trường đã lọc, rồi ghim cho server bằng `JAVIS_CLAUDE_CLI`, nên cổng và engine dùng CÙNG một binary.
3. **Xác thực:** `claude auth status --json` chạy bằng binary đó, môi trường đã lọc, ở CẢ HAI cwd: brain (lượt chat) và `STATE/resonance_cwd` (lượt việc nền, cấu hình công cụ khác lượt chat). Chỉ nhận `loggedIn`, `authMethod` = `claude.ai`, `apiProvider` = `firstParty`, có `subscriptionType`. Báo cáo chỉ lưu bốn trường đó và phiên bản binary, không lưu email, id hay token.
4. **Nguồn settings người dùng và dự án:** engine chat bật `setting_sources = user, project, local`, nên cổng soát `settings.json` và `settings.local.json` ở thư mục cấu hình mà chính `auth status` báo, cùng `.claude/settings*.json` của CẢ HAI cwd. Có `apiKeyHelper`, lệnh làm mới credential đám mây, hay `env` chọn khoá/nhà cung cấp/đường gọi thì DỪNG. File không đọc được tính là rủi ro. Chỉ ghi TÊN khoá, không ghi giá trị.
5. **Nguồn do quản trị đặt** (review e2e vòng 2): `managed-settings.json`, thư mục `managed-settings.d/*.json` ở các vị trí hệ thống, khoá registry `SOFTWARE\Policies\ClaudeCode` (HKLM, HKCU), và file cache kiểu managed/remote trong thư mục cấu hình. Cổng KHÔNG đánh giá nội dung các nguồn này: có bất kỳ nguồn nào thì môi trường **chưa hỗ trợ**, DỪNG. Máy hiện tại không có nguồn nào.

**Phạm vi bảo đảm:** cổng chứng minh danh tính xác thực của Claude (gói thuê bao, nhà cung cấp gốc) cho đúng engine sẽ chạy. Cổng KHÔNG chứng minh mọi tiến trình con không tiêu tiền: hook, plugin, MCP có thể chạy tiến trình hay dịch vụ riêng. Các khoá đó trong settings được ghi TÊN vào báo cáo (`not_assessed`; máy hiện tại: `enabledPlugins` ở settings người dùng). Không gắn nhãn "đã soát mọi nguồn".

Không chứng minh được các điều trên thì dừng, không gửi tin. Cổng chỉ chứng minh trạng thái lúc chạy; không suy ngược cho các lần chạy trước.

### Trần lượt gọi

- **Đơn vị:** lượt engine ở cấp host. Một lượt bộ não có thể gồm nhiều request nội bộ của SDK (vòng công cụ); trần này KHÔNG phải số request gửi nhà cung cấp, không phải token hay chi phí, và không có dữ liệu để đếm số request đó.
- **Tổng 3** (`JAVIS_RESONANCE_E2E_MAX_CALLS`). Lượt bộ não tính trước khi gửi (bộ chạy gửi đúng một tin). Phần còn lại server chặn TRƯỚC lượt gọi vượt trần bằng `JAVIS_RESONANCE_CALL_CEILING`: kiểm trong cùng giao dịch giữ chỗ, đếm MỌI đường Resonance gọi engine (lượt việc nền, phép thử, bộ lập mục tiêu qua sổ `call_ledger`), số đã dùng trong SQLite nên giữ qua khởi động lại; bộ chạy truyền biến cho MỌI tiến trình server (tiến trình không có biến thì không có trần chung).

## Kịch bản (chế độ `real`), lần chạy 2

Lời người dùng, loại **duy trì** (đúng nhóm `javis_goal` theo luật định tuyến hiện hành), dữ liệu mô phỏng, không nêu tên công cụ:

> (Dữ liệu mô phỏng để thử nghiệm.) Từ giờ duy trì giúp mình ghi chú Inbox/viec-dang-do.md: lúc nào cũng liệt kê đủ các việc đang dở bên dưới, mỗi việc ghi người phụ trách và hạn chót. Khi mình báo thêm việc thì cập nhật vào, có bản mới thì báo mình xem. Đừng đụng tới Notes/ghi-chu-cu.md.
> Việc đang dở: Lan soạn kế hoạch bài viết tháng 11, hạn 09/10. Minh kiểm lại lịch đăng, hạn 10/10. Hà gửi bảng số liệu cho cả nhóm, hạn 12/10.

**Hợp đồng kỳ vọng độc lập** (review e2e vòng 2 và 3), lấy từ lời người dùng, không từ đề xuất của bộ não và không đưa thêm vào prompt: kiểu `maintain`; file `Inbox/viec-dang-do.md`; ghi chú cũ nguyên vẹn; và đủ ba bộ:

| Việc | Người | Hạn | Cụm đặc trưng chấp nhận (mọi cụm trong một phương án phải có) |
|---|---|---|---|
| Soạn kế hoạch bài viết tháng 11 | Lan | 09/10 | "kế hoạch" + "bài viết"; "kế hoạch" + "tháng 11"; "kế hoạch nội dung" |
| Kiểm lại lịch đăng | Minh | 10/10 | "lịch đăng"; "lịch" + "đăng bài" |
| Gửi bảng số liệu cho cả nhóm | Hà | 12/10 | "số liệu" |

**Nghiệm thu nội dung do NGƯỜI REVIEW chốt** (điều chỉnh quy trình nghiệm thu theo review e2e vòng 4, phương án 1; không đổi luật đánh giá của Resonance trong sản phẩm). Khớp cụm từ không hiểu được phủ định ("không gửi"), hành động trái nghĩa ("hủy lịch đăng"), sai tháng hay chỉ đúng chủ đề ("kiểm tra số liệu"), nên không dùng làm căn cứ nghiệm thu:

- Bộ chạy tính **chỉ báo hỗ trợ** `content_candidate` (`_e2e_pilot_guard.content_contract`) theo đơn vị trình bày (hàng bảng, mục danh sách cùng dòng tiếp nối, đoạn văn, từng dòng; KHÔNG gộp mục dưới tiêu đề), chỉ đơn vị nói về đúng một người. Kết quả: `met` (các cụm, người, hạn cùng một đơn vị), `not_met` (có bằng chứng sai rõ: không thấy tên, việc của người khác, đúng việc mà khác hạn, có người và hạn mà không có việc), `unverified` (không trích được quan hệ: câu nhắc nhiều người, tiêu đề, việc không kèm ngày, cách nói chưa hỗ trợ). Chỉ báo được ghi vào báo cáo để người review tham khảo.
- Bộ chạy **lưu NGUYÊN VẸN** file sản phẩm ra ngoài thư mục tạm (cạnh báo cáo, `<tên báo cáo>-deliverable.md`) trước khi dọn, kiểm hash bản chép bằng hash nguồn; báo cáo trỏ đúng tên file và hash. Chế độ real bắt buộc có `JAVIS_RESONANCE_E2E_OUT`.
- Mọi kiểm kỹ thuật đạt thì kết luận của lần chạy là `acceptance: pending_content_review` và `content_review: pending`: **chưa nghiệm thu pilot**. Người review đối chiếu ba bộ việc, người, hạn trên đúng file và hash đó rồi mới chốt; không bao giờ tự suy ra từ chỉ báo. Kỹ thuật không đạt thì `technical_failed`; dừng giữa chừng thì `stopped`.

Mục tiêu hiểu sai về kiểu hay file vẫn là lỗi kỹ thuật cứng (pilot FAIL); sai về nội dung do người review bắt.

Mọi điều kiện dưới đây là lỗi CỨNG (một điều không đạt là pilot FAIL, không có nhánh "ghi chú rồi OK").

| Bước | Việc | Kiểm |
|---|---|---|
| 0 | Server A lên (nhịp tạm dừng); cổng an toàn | Đúng binary, gói thuê bao gốc, settings sạch; WebSocket nhận kết nối |
| 1 | Gửi MỘT tin qua `/ws`, chờ `turn_done` | Bộ não lập ĐÚNG MỘT mục tiêu qua `javis_goal`, gắn đúng phiên; **kiểu là `maintain`**; **file sản phẩm của mục tiêu đúng file người dùng nêu**; ý định gốc TRÙNG KHỚP toàn bộ lời người dùng; thẻ đặt vào đúng phiên có biên nhận; chưa có lượt việc nền nào. Không lập mục tiêu: ghi kết quả, DỪNG |
| 2 | Giết A, dựng B (nhịp chạy) | Nhịp lập lịch tự làm lượt việc nền; receipt succeeded, đúng provider, 0 lần gọi công cụ; **file người dùng nêu** tồn tại và bytes khớp hash host ghi khi đăng; sản phẩm được **lưu nguyên vẹn** ra ngoài thư mục tạm, hash khớp; chỉ báo nội dung được ghi (không quyết định); tin báo về đúng phiên có biên nhận |
| 3 | Giết B, dựng C, chờ hơn hai nhịp | Không báo lặp; không gọi thêm |
| 4 | Nếu mục tiêu có tiêu chí người dùng duyệt | BẮT BUỘC có sản phẩm để duyệt (`artifact_ref`); bấm "Đạt yêu cầu" qua API như nút trên thẻ: 200 |
| 5 | Khép vòng theo KIỂU KỊCH BẢN (không theo kiểu bộ não chọn) | Đánh giá met, vẫn active, đã báo `goal.maintained` về phiên có biên nhận, lịch xem lại nằm trong **[6 giờ, 24 giờ] sau mốc đánh giá (cả hai đầu)**; rồi người dùng **tạm dừng qua API** để không còn việc nền. Không gọi thêm model ở bước 4, 5 |
| Cuối | | Ghi chú cũ còn nguyên (hash); tổng lượt trong trần; kết luận `pending_content_review` nếu mọi kiểm kỹ thuật đạt. **Người review chốt nội dung** trên file đã lưu |

Bằng chứng lưu thêm: khung `tool_call` / `tool_result` (gồm `ToolSearch`; engine chỉ chuyển kết quả công cụ đã cắt còn 500 ký tự), câu trả lời cuối, việc Kanban nếu có, hash phiên bản `CLAUDE.md` của repo và của brain cùng plugin `javis_goal` (luật định tuyến đang dùng).

## Hạn mức đề xuất cho lần chạy 2

| Mục | Đề xuất |
|---|---|
| Lượt bộ não chính | **1** (`anthropic-cli` / `claude-opus-5-5`, gói thuê bao đã qua cổng xác thực) |
| Lượt việc nền | **1 dự kiến, tối đa 2** (`anthropic-cli` / `sonnet`); thử lại khi chưa đạt cách 15 phút nên trong cửa sổ pilot thực tế chỉ có 1 |
| Trần cứng | **3 lượt engine cấp host** (1 lượt Opus, tối đa 2 lượt Sonnet), chặn trước lượt vượt, giữ qua khởi động lại. Không phải 3 request nội bộ của SDK. Hook, plugin, MCP trong settings người dùng (máy hiện tại: `enabledPlugins`) nằm ngoài trần này và ngoài phạm vi cổng; muốn cam kết rộng hơn thì phải cô lập chúng trong sandbox |
| Đề xuất duyệt ghi rõ | Commit của bộ chạy, lời giao nguyên văn, hợp đồng chấm ở trên, cấu hình engine cụ thể. Cổng engine và xác thực vẫn chạy ngay trước khi gửi tin |
| Thời gian | Khoảng 8 đến 15 phút |
| Số lần chạy | **Một lần.** Không thử lại, không sửa lời, không nâng trần; mọi quyết định khác do người dùng |

## Đã kiểm ở chế độ `dry` (không gọi model)

Bộ chạy sau sửa vòng 2: **14/14 kiểm xanh, 0 lượt engine**, khoảng 2 phút: cổng an toàn chạy THẬT (engine resolve đúng kỳ vọng của dry; binary 2.1.292; `auth status` ở cả hai cwd báo `claude.ai` / `firstParty` / gói `max`; không khoá rủi ro, không nguồn managed; `enabledPlugins` ở settings người dùng ghi là ngoài phạm vi), server lên, WebSocket, nhịp tạm dừng ở A (báo cáo ghi A tạm dừng, B và C chạy, trần và binary ghim ở cả ba), giết và dựng lại, nhịp lập lịch tự nhận lịch (engine việc nền bị chặn trước khi gọi, như dự định), tin báo về đúng phiên có biên nhận, không báo lặp, API thẻ qua kiểm Origin, ghi chú cũ còn nguyên. Riêng cấu hình THẬT (chép các ô chọn engine): resolve ra `anthropic-cli` / `claude-opus-5-5` và `anthropic-cli` / `sonnet`, khớp cấu hình duyệt.

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

### Vòng 2 (diff `2ba6f74b..2a8db1aa` được review)

1. **P2-1, cổng không kiểm engine sắp chạy.** Thêm bước 0 của cổng (resolve bằng luật runtime, so cấu hình duyệt, dừng nếu khác); `auth status` và soát settings chạy ở cả cwd lượt chat lẫn cwd lượt việc nền. Test fixture: bộ não chọn Codex, việc nền chọn OpenRouter, model khác, `claude_model` khác, không resolve được: đều dừng; dry kỳ vọng riêng.
2. **P2-2, kịch bản duy trì chấm đạt dù hiểu sai.** Hợp đồng kỳ vọng độc lập (kiểu, file, ba bộ người và hạn), chấm trên file thật; nhánh khép vòng theo kiểu kịch bản, không còn nhánh `achieve`; lịch xem lại kiểm cả hai đầu. Test fixture: nội dung thiếu người hay ngày, người và ngày khác dòng, 19/10 không bị nhận là 9/10, lịch một năm hay một giờ: đều không đạt.
3. **Nguồn cấu hình chưa soát.** Thêm nguồn managed (managed-settings.d, registry, cache): có thì dừng như môi trường chưa hỗ trợ. Hook, plugin, MCP ghi là ngoài phạm vi bảo đảm.
4. **Biến pilot thừa kế** bị xoá trước khi dựng mỗi server; trạng thái hiệu lực ghi vào báo cáo.

Script kỳ vọng `PR-579-e2e-round3-expected-checks.py` (dựng từ script vòng 2 của người review: cùng mục tiêu hiểu sai bằng `form_goal` + `advance` thật, chạy chính các biểu thức kiểm của bộ chạy): 17 PASS, exit 0. Trên `2a8db1aa` script dừng ngay vì bộ chạy cũ không có hợp đồng kỳ vọng.

### Vòng 3 (diff `2a8db1aa..d5cff3d2` được review)

**P2, đủ tên và ngày vẫn chấm đạt dù thiếu hay gán sai việc.** Hợp đồng nay lưu ba bộ VIỆC, NGƯỜI, HẠN; chấm theo đơn vị trình bày, chỉ đơn vị nói về đúng một người, với ba kết quả `met`, `not_met`, `unverified` như mô tả ở trên. Câu hỏi "cùng dòng có quá chặt" được trả lời bằng việc đọc thêm mục danh sách nhiều dòng, đoạn văn và mục dưới tiêu đề; bố cục ngoài khả năng đọc thì `unverified`, không phải `not_met`.

Test fixture (`test_resonance_e2e_guard.py`, tổng 49 kiểm): bảng đúng, danh sách một dòng, danh sách nhiều dòng (ca của reviewer), gom theo người dưới tiêu đề, văn xuôi hai dòng, bảng kèm dòng tóm tắt nhắc cả ba người: `met`. Chỉ người và hạn (ca của reviewer), bảng chỉ cột người và hạn, thiếu một việc, gán nhầm người (ca của reviewer), sai hạn, hạn của người khác, sản phẩm rỗng: `not_met`. Cách nói chưa hỗ trợ: `unverified`.

Script kỳ vọng `PR-579-e2e-round4-expected-checks.py` (dựng từ script vòng 3 của reviewer: mục tiêu duy trì thật đạt theo tiêu chí host, đúng file, hash, lịch; chạy chính biểu thức kiểm nội dung của bộ chạy): thiếu việc và gán nhầm FAIL, đúng và nhiều dòng qua; exit 0. Trên `d5cff3d2` script dừng ở kiểm đầu vì hợp đồng cũ không có việc.

### Vòng 4 (diff `d5cff3d2..5c414d6f` được review)

**P2, chấm từ khoá vẫn báo đạt cho nội dung sai.** Theo khuyến nghị của review, chọn **phương án 1**: bỏ phép chấm nội dung khỏi các kiểm nghiệm thu; giữ nó làm chỉ báo hỗ trợ; kỹ thuật đạt thì `pending_content_review`; lưu nguyên vẹn sản phẩm với hash để người review chốt. Không mở rộng thêm từ khoá. Chỉ báo được chỉnh cho thận trọng hơn: không gộp mục dưới tiêu đề (ca mượn hạn của việc khác không còn `met`); tên chỉ nằm trong đơn vị nhắc nhiều người thì `unverified`, không phải "không thấy người"; có đúng việc mà ngày không phải hạn của ai thì `not_met`.

Test (`test_resonance_e2e_guard.py`, 56 kiểm): thêm ca mượn hạn trong mục tiêu đề, câu nhiều người, không thấy tên, ngày lạ, chỉ báo tự nói là chỉ báo, lưu nguyên vẹn (hash khớp) và không có file. Script kỳ vọng `PR-579-e2e-round5-expected-checks.py`: bộ chạy không còn kiểm nội dung để nghiệm thu, đòi lưu nguyên vẹn; `acceptance` chỉ phụ thuộc kỹ thuật (`rep`, `_fails`, `MODE`); bốn ca sai nghĩa của reviewer chỉ báo vẫn nói `met` nhưng kết luận là chờ người review; mượn hạn và câu nhiều người không còn `met`; sản phẩm hơn 4.000 ký tự được lưu đủ. Exit 0; trên `5c414d6f` thì đỏ.

Trả lời ba câu hỏi của review vòng 1: **giữ luật định tuyến hiện tại** và đổi kịch bản sang loại duy trì, nghiệm thu theo kiểu mục tiêu (maintain: met, `goal.maintained`, lịch xem lại, rồi tạm dừng); trần nay đủ cho mọi đường Resonance gọi engine trên cùng kho với cùng biến ở mỗi tiến trình, nhưng không phải trần request nội bộ SDK; lọc môi trường không tự đủ, nên có cổng xác thực và soát settings.

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

## Lần chạy 2 (07/10/2026): bộ não tự làm luôn trong lượt, không lập mục tiêu

**Pilot dừng đúng điều kiện đã duyệt, không thử lại, không sửa lời giao.** Kết luận của lần chạy: `acceptance: stopped`.

| Mục | Giá trị |
|---|---|
| Commit | `9e4f842a` (đã qua review e2e vòng 5), cây `server/` và `system/` sạch |
| Người duyệt | Người dùng duyệt một lần chạy theo đề xuất: 1 lượt Opus + tối đa 2 lượt Sonnet, lời giao, hợp đồng và cấu hình engine như trên |
| Cổng an toàn | Đạt: engine resolve `anthropic-cli` / `claude-opus-5-5` và `anthropic-cli` / `sonnet` đúng cấu hình duyệt; `auth status` ở cả hai cwd là `claude.ai` / `firstParty` / `max`; không nguồn managed; `enabledPlugins` ghi là ngoài phạm vi |
| Server | Một server (A, nhịp tạm dừng, trần việc nền 2, binary ghim); dừng trước khi tới bước giết và dựng lại |
| Lượt đã dùng | **1 lượt engine cấp host** (lượt bộ não), 0 lượt việc nền |
| Thời gian | Tổng 41,1 giây |
| Bằng chứng | [`resonance-mvp-e2e-pilot-2.json`](resonance-mvp-e2e-pilot-2.json): cổng, khung công cụ, câu trả lời cuối, việc Kanban (không có), trạng thái server |

**Bộ não đã làm gì** (khung công cụ trong báo cáo): `Bash` xem thư mục `Inbox` và `Notes`; `Write` tạo `Inbox/viec-dang-do.md`; `Bash` đọc chỉ mục bộ nhớ; `Write` một ký ức `memory/facts/duy-tri-viec-dang-do.md`; `Edit` `memory/MEMORY.md`. **Không gọi `ToolSearch` hay `javis_search_tools`**, nên không lúc nào thấy `javis_goal`. Câu trả lời cuối có bảng đủ ba việc, người, hạn (Lan 09/10, Minh 10/10, Hà 12/10, kèm năm 2026), nói không đụng `Notes/ghi-chu-cu.md`, và nói rõ: file chỉ được cập nhật khi người dùng nhắn, "không tự theo dõi ở nền".

**Đánh giá:**
1. Prompt của brain đã bật Resonance CÓ dòng định tuyến (main.py: "duy trì, theo dõi, chờ sự kiện, làm tới khi đạt thì gọi tool javis_goal op=create ... Chưa thấy tool thì tìm bằng javis_search_tools"). Bộ não không làm theo dòng đó; `javis_goal` là tool phải tìm mới thấy, và bộ não không tìm.
2. Nhưng đọc kỹ, lời giao lần 2 cũng KHÔNG thật sự cần làm gì sau lượt: "khi mình báo thêm việc thì cập nhật vào" là phản ứng theo tin nhắn mới, không có trạng thái nào đổi ở nền giữa hai tin. Bộ não làm xong ngay trong lượt và nói đúng giới hạn của mình. Như lần 1, lần chạy này không chứng minh, cũng không bác, việc bộ não dùng `javis_goal` khi một việc THẬT SỰ cần theo đuổi sau lượt.
3. Hai lần cho thấy một khó khăn thiết kế, không chỉ của kịch bản: với bộ thực thi việc nền chỉ chữ, không đọc được dữ liệu, rất khó dựng một yêu cầu tự nhiên vừa cần làm sau lượt, vừa làm được bằng Resonance MVP, mà lại không thuộc Kanban (việc nền một lần) hay `javis_schedule` (giờ cố định).

**Điều kiện MVP thứ nhất vẫn CHƯA đạt. Không chạy thêm.** Hướng tiếp theo cần người dùng quyết (xem báo cáo gửi người dùng).

## Sau lần chạy 2: chốt ranh giới và kiểm đường công cụ (không gọi model)

Làm theo đánh giá `PR-579-pilot-2-assessment.md`: chưa chạy thêm, chưa đổi lời giao để ép bộ não lập mục tiêu. Mọi kiểm ở phần này chạy bằng mã và brain giả.

### Ranh giới định tuyến (review đồng ý về nguyên tắc)

| Loại | Khi nào | Đường | Ví dụ |
|---|---|---|---|
| Làm ngay | Làm xong và trả kết quả trong lượt | Trả lời, có thể ghi file | "Tóm tắt ghi chú này thành ba ý"; "Lập bảng việc từ tin dưới, lưu vào Inbox" |
| Việc nền một lần | Chạy một lần ở nền, xong là hết trách nhiệm | `javis_task` (Kanban) | "Dịch hết 40 file trong thư mục này, xong báo anh" |
| Theo đuổi kết quả | Giữ trách nhiệm qua nhiều vòng làm, tự kiểm, sửa theo phản hồi; giữ việc mở tới khi đạt. Lúc chờ phản hồi không gọi model | `javis_goal` (Resonance) | "Lo giúp anh bản hướng dẫn này tới khi anh thấy dùng được, anh góp ý dần" |
| Nhắc giờ cố định | Một thông báo nhắc đơn thuần vào một thời điểm (không phải mọi việc có hạn chót) | `javis_schedule` | "8 giờ sáng mai nhắc anh gọi nhà cung cấp" |

Thêm hai ca không lập gì mới: **nối mục tiêu đang mở** (chỉ góp ý làm thay đổi mục tiêu đang mở mới nối vào nó bằng `javis_goal op=update`; "cảm ơn" hay câu hỏi bên lề thì không) và **chat thường** (câu hỏi, tư vấn, lập kế hoạch: chỉ trả lời).

Điểm phân biệt là trách nhiệm tiếp tục theo đuổi kết quả, không phải số lần gọi model hay chữ "duy trì". Lời giao lần 2 ("khi mình báo thêm việc thì cập nhật vào") nằm ở vùng giao: mỗi lần cập nhật là phản ứng với một tin mới, làm ngay trong lượt đó vẫn hợp lý. Ngược lại, viết bản đầu ngay trong lượt KHÔNG phủ định Resonance: bộ não có thể làm phần hữu ích ngay và vẫn lưu trách nhiệm vào mục tiêu.

### Kết quả kiểm đường công cụ trên engine Claude Code

Script `exports/reviews/PR-579-tool-path-probe.py` (ngoài repo), sau đó thành test `tests/python/test_resonance_tool_path.py`:

1. **Đăng ký đúng brain: đạt.** `javis_goal` chỉ có trong `plugins_host.plugin_tools` khi brain bật Resonance; brain tắt hoặc không rõ brain thì không có. `javis_task` luôn có.
2. **Danh sách tới engine: đạt.** Engine Claude nhận plugin qua MCP in-process `javis-plugins` (32 tool, có `javis_goal`). Đường chat đặt `javis_vault` trong `main._apply_mcp`; thiếu nó thì `javis_goal` không có mặt.
3. **Đường tìm: sai trên Claude Code.** Khi engine Claude dựng được server plugin in-process, nó báo hub bỏ nhóm plugin (`X-Javis-No-Plugins: 1`) để khỏi trùng tool, nên `javis_search_tools` của hub không trả về `javis_goal`. Kết luận chỉ áp cho đường đó; nhánh lùi khi server in-process lỗi (hub giữ nhóm plugin) không được kiểm ở đây. Với engine API hay Codex, hub có nhóm plugin nên `javis_search_tools` tìm ra. Dòng gợi ý cũ chỉ nêu `javis_search_tools`.
4. **Nguồn tin người dùng: đạt.** `luot_dang_chay` trả đúng phiên, id tin và lời người dùng của lượt đang chạy; hết lượt thì không còn.

**Chưa kiểm được khi không gọi model:** ToolSearch của SDK có luôn sẵn không, và Claude Code có hoãn nạp tool `mcp__javis-plugins__*` không. Bằng chứng gián tiếp duy nhất là lần chạy 1 (bộ não tìm thấy `mcp__javis-plugins__javis_task` qua ToolSearch). Chỗ sai ở mục 3 có thật, nhưng **chưa chứng minh nó là nguyên nhân** của lần chạy 2.

### Sửa tối thiểu

- `server/main.py` (dòng gợi ý, chỉ khi brain bật Resonance): nêu đủ bốn loại theo bảng trên và chỉ đường tìm cho từng engine: Claude Code dùng ToolSearch (`mcp__javis-plugins__javis_goal`), engine khác dùng `javis_search_tools`. Comment ghi đúng mức bằng chứng (việc hoãn nạp chưa xác minh). Trần độ dài dòng gợi ý trong test nâng từ 450 lên 650 ký tự.
- `system/plugins/javis-goal/plugin.py`: thêm "tự kiểm, sửa theo phản hồi, giữ việc mở tới khi đạt" vào điều kiện lập mục tiêu; ghi rõ "việc nền một lần, xong là hết trách nhiệm: javis_task". Mô tả này chỉ tới engine khi brain bật.
- **Mô tả `javis_task` giữ nguyên** (review đường công cụ, P2). Bản `9c62b9a0` từng thêm câu ranh giới vào đó, và câu này tới cả brain chưa bật Resonance; đã gỡ. Ranh giới nay chỉ nằm ở hai chỗ chỉ có khi bật.

`test_resonance_tool_path.py` (20 kiểm) đọc mô tả tool **thật sự tới engine Claude** (metadata của server in-process) ở brain bật và tắt. Mô tả `javis_task` phải giống hệt nhau và không nhắc `javis_goal`; đặt lại câu cũ thì đỏ. Không thêm từ khoá nào nhắm vào lời giao của pilot. Không có bằng chứng sửa này đủ để bộ não lập mục tiêu.

**Hai điều kiện thật của `op=update`** (tìm ra khi viết test engine giả): đề xuất phải có `relevant_quote` trích nguyên văn lời GÓP Ý, và phải đổi ít nhất một trường (ràng buộc, tiêu chí, cách hiểu). Thiếu trích dẫn thì host từ chối; không đổi gì thì host trả "không có thay đổi nào được áp dụng", không ghi ý định mới, việc nền không chạy lại.

### Lần chạy 3 (CHƯA chạy, chờ review bộ chạy rồi chờ người dùng duyệt)

**Kịch bản: hoàn thiện một bản hướng dẫn qua phản hồi** (mục tiêu `achieve`, sản phẩm chữ). Bộ chạy riêng: `tests/python/test_resonance_mvp_e2e_achieve.py` (biến `JAVIS_RESONANCE_E2E_ACHIEVE=dry|real`, cổng 7792). Bộ chạy maintain cũ giữ nguyên làm hồ sơ lần 1 và lần 2.

**Đầu vào đóng băng** (nguyên văn trong bộ chạy, báo cáo ghi kèm sha256): lời giao gồm yêu cầu, đường dẫn `Docs/huong-dan-nhan-hang.md`, ba điều dặn (cho người chưa làm, bước đánh số, mục "Lỗi hay gặp") và sáu dòng ghi chú (đếm kiện trước khi cho tài xế đi; đối chiếu từng dòng phiếu giao về mã hàng và số lượng; thùng móp, ướt, rách để riêng và ghi hàng hỏng; chỉ ký sau khi đếm và đối chiếu, thiếu hay hỏng ghi cạnh chữ ký; nhập sổ kho trong ngày; không chắc thì gọi anh Tùng). Tin góp ý: "Anh xem bản đầu rồi. Bước đối chiếu phiếu giao khó hiểu quá, em thêm một ví dụ cụ thể, và thêm bước chụp ảnh hàng hỏng trước khi ký." Không có tên tool, API hay schema trong lời người dùng.

**Các bước và hạn mức chia theo giai đoạn** (tối đa 4 lượt engine cấp host):

| Bước | Server | Lượt | Đạt khi | Dừng khi |
|---|---|---|---|---|
| S0 | A: giai đoạn 1, nhịp dừng | 0 | Cổng xác thực đạt | Cổng không đạt |
| S1 lượt chat 1 | A | chat 1/2 | Đúng một mục tiêu `achieve`, file `Docs/huong-dan-nhan-hang.md`, có tiêu chí người dùng xác nhận; ý định gốc trùng lời giao | Không lập hay lập hai mục tiêu, giao Kanban: `stopped`. Lệch kiểu, file hay tiêu chí: `contract_failed` |
| S2 bản đầu | B: giai đoạn 1, nhịp chạy | nền 1/1 | Receipt đúng provider; file khớp hash bản đăng; lưu nguyên vẹn; chờ người dùng; báo về phiên có biên nhận | Lỗi kỹ thuật |
| S3 dựng lại | C: giai đoạn 1, nhịp chạy, rồi D: nhịp dừng | 0 | Mục tiêu và revision giữ nguyên; không báo lặp; 75 giây không gọi thêm | Mất trạng thái |
| S4 lượt chat 2 | D | chat 2/2 | Cùng phiên; cùng mục tiêu, revision +1; ý định mới đúng lời góp ý, nối về ý định trước; giữ ràng buộc cũ, file, tiêu chí xác nhận; lịch làm lại chưa ai nhận | Mục tiêu mới, Kanban, hay revision không đổi: `stopped` |
| S5 bản sửa | E: giai đoạn 2, nhịp chạy | nền 2/2 | Đúng một lượt cho revision mới; hash khác bản đầu, khớp bản đăng; lưu nguyên vẹn; chờ người dùng; 75 giây không gọi thêm | Lỗi kỹ thuật |
| S6 xác nhận | E | 0 | Bấm "Đạt yêu cầu" cho **từng** tiêu chí người dùng của revision hiện hành, trên đúng `artifact_ref`; mục tiêu `succeeded` và đã báo | |

- **Lượt chat:** sổ `TurnLedger` giữ chỗ TRƯỚC mỗi lần gửi và ghi xuống đĩa ngay. Lượt hết giờ hay lỗi vẫn được tính, không có đường thử lại, tối đa 2.
- **Việc nền:** trần TÍCH LUỸ 1 cho mọi server tới hết S4, 2 cho server E. Sổ trong SQLite không bao giờ đặt lại. Lượt chat góp ý chạy trên server nhịp dừng, nên lịch làm lại chỉ được nhận khi E lên. Nếu nhịp chạy với trần 1 sau góp ý, lịch đó bị chặn vì hạn mức và bộ chạy không được sửa kho để gỡ.
- Không thử lại, không nâng trần, không chuyển API trả phí. Tool javis_goal lập mục tiêu không gọi model (framer `CallBudget(0)`); bộ thử cách làm M5 không có đường gọi trong sản phẩm.

**Kết luận của lần chạy** tách bốn loại: `technical_failed` (host hay bộ chạy), `contract_failed` (đã đi đường mục tiêu nhưng lệch kịch bản), `stopped` (bộ não không đi đường mục tiêu ở S1 hay S4), `pending_content_review` (kỹ thuật đạt).

**Nghiệm thu nội dung vẫn do người review** (giữ quy trình vòng 5). Hash khác chỉ chứng minh bytes khác. Bộ chạy lưu nguyên vẹn bản đầu và bản sửa cùng hash, revision, sha của lời góp ý, kèm danh sách điều cần kiểm:
- **bản đầu:** viết cho người chưa làm bao giờ, các bước đánh số, có mục "Lỗi hay gặp", đủ sáu ý của ghi chú;
- **bản sửa:** bước đối chiếu có ví dụ cụ thể, có bước chụp ảnh hàng hỏng đặt trước bước ký, và vẫn giữ mọi yêu cầu của bản đầu.

Nút "Đạt yêu cầu" ở S6 là thao tác **mô phỏng** (`simulated_acceptance: true`), chỉ kiểm đường API, không phải con người đã duyệt.

**Bằng chứng ghi thêm:**
- mọi khung công cụ, riêng các khung dính ToolSearch hay `javis_search_tools` (`search_calls`) và các khung dính `javis_goal` hay `javis_task`;
- file bộ não ghi trong từng lượt chat (ảnh chụp trước và sau);
- file sản phẩm lưu sau S1 và S4, kể cả khi dừng sớm.

Danh sách tool trong tin `init` của Claude Code không đọc được từ ngoài nếu không đổi mã sản phẩm; báo cáo ghi `not_observable`.

**Đã kiểm không gọi model:**
- `dry` của bộ chạy: 24/24 kiểm, `dry_ok`.
  - Lập mục tiêu bằng đúng hàm của tool.
  - Năm server: bốn server trần 1, server cuối trần 2.
  - Góp ý nối bằng `revise_goal` như `op=update`, revision 1 lên 2, ý định nối chuỗi.
  - Bản sửa của revision 2 bị chặn trước lượt gọi model (provider chỉ chữ không chạy được).
  - Lệnh tạm dừng qua API vẫn có hiệu lực. 0 lượt engine.
- `test_resonance_achieve_stages.py` (20 kiểm, engine giả):
  - Trần 1: bản đầu chưa đạt thì lần làm lại bị chặn trước lượt gọi, kể cả sau khi dựng lại kho.
  - Đang chờ người dùng thì đánh thức lại không gọi model.
  - Góp ý hợp lệ rồi trần 2: đúng thêm một lượt, prompt có lời góp ý và bản trước; lượt thứ ba không giữ được chỗ.
  - Sổ lượt chat tính cả lượt hết giờ, không giữ lại cùng lượt, đọc lại được sau khi dựng lại.
- `test_resonance_e2e_guard.py`: thêm ảnh chụp brain và lọc khung tìm tool.

**Rủi ro biết trước:**
- Bộ não có thể làm bản đầu ngay trong lượt mà không lập mục tiêu: `stopped`, không mặc định là lỗi.
- `op=update` thiếu trích dẫn hay không đổi trường nào: S4 dừng và ghi rõ; bộ chạy không tự thêm trường để giả sửa.
- Dòng gợi ý định nghĩa loại 3 khá gần lời giao, nên một lần đạt chỉ chứng minh đường này đi được khi ranh giới nêu rõ, chưa chứng minh định tuyến ổn định.

**Sửa theo review bộ chạy achieve (diff `9c62b9a0..ff9f97bf`):**
- **P2-1, kiểm hỏng vẫn cấp lượt tiếp:** cổng chi phí nay nằm TRONG ba thao tác có thể dẫn tới lượt gọi model: dựng server, gửi tin chat, bấm xác nhận (`tests/python/_e2e_achieve_harness.py`). Có bất kỳ kiểm nào hỏng, kỹ thuật hay hợp đồng, thì cả ba từ chối. Script bộ chạy đi qua harness cho cả ba.
- **P2-2, tin báo cũ được tính cho bản sửa:** tin của S2, S5, S6 phải khớp một dòng outbox đúng mục tiêu, đúng loại (`goal.waiting_human`, `goal.succeeded`) và đúng revision. Tin `outbox:<id>` kèm biên nhận của host phải nằm trong phiên người giao việc. Cờ `delivered` không còn đủ.
- **Ca âm** (`test_resonance_e2e_achieve_harness.py`, 31 kiểm):
  - S4 sai nguồn góp ý, mất ràng buộc, thiếu lịch: không dựng giai đoạn 2.
  - Kiểm hỏng trước S4: không gửi tin, không giữ chỗ.
  - Lượt chat lỗi: tính vào sổ, không thử lại.
  - S5 hỏng: không bấm xác nhận.
  - Tin báo: chỉ có tin cũ, chỉ có thẻ reframe, phiên rỗng, không gửi, nhầm phiên, thiếu biên nhận, khác mục tiêu, chưa giao, S6 chỉ có cờ delivered.
  - Soát nguồn: script không còn đường dựng server, gửi chat hay bấm xác nhận vòng qua cổng.
- **`dry` trên commit sạch `64ad9eba`:** 23/23 kiểm, `dry_ok`, 0 lượt engine.

## Lần chạy 3 (07/10/2026): bộ não tự lập mục tiêu, dừng ở S2 vì xung đột đăng file

**Kết luận: `technical_failed` ở S2. Không thử lại, không chạy tiếp.** Người dùng duyệt đúng một lần chạy trên `1c76ce6f` (cây sạch), tối đa 2 Opus và 2 Sonnet.

| Mục | Giá trị |
|---|---|
| Cổng | Đạt: engine `anthropic-cli` / `claude-opus-5-5` (chat) và `sonnet` (việc nền), gói Max ở cả hai cwd |
| Lượt đã dùng | 2 trên 4: một lượt chat Opus (S1), một lượt việc nền Sonnet (S2). Server 2 dừng thì cổng chi phí chặn server thứ ba |
| Thời gian | 122,6 giây |
| Bằng chứng | [`resonance-mvp-e2e-pilot-3.json`](resonance-mvp-e2e-pilot-3.json), bản bộ não viết [`resonance-mvp-e2e-pilot-3-s1-chat.md`](resonance-mvp-e2e-pilot-3-s1-chat.md) (`draft1` và `final` là cùng file đó, cùng hash `c30c9443...`) |

**S1 đạt: lần đầu bộ não tự định tuyến sang mục tiêu.**
- Thứ tự công cụ: `Write` (viết luôn bản đầu vào `Docs/huong-dan-nhan-hang.md`), `ToolSearch` với `select:mcp__javis-plugins__javis_goal`, rồi hai lần gọi `javis_goal`. Trace chỉ ghi khung gọi, không ghi kết quả, nên không biết lần đầu bị từ chối hay không.
- Mục tiêu khớp hợp đồng:
  - `achieve`, đúng file;
  - tiêu chí `c1` tự kiểm (có "Lỗi hay gặp", "1.", "anh Tùng", tối thiểu 800 ký tự), tiêu chí `c2` người dùng xác nhận;
  - bốn ràng buộc đúng lời dặn; hạn xem lại nội bộ một tuần, ghi rõ người dùng không nêu hạn.
- Thẻ mục tiêu về đúng phiên có biên nhận. Không giao Kanban.
- Câu trả lời nói rõ đã ghi việc để theo tới khi anh xác nhận.

**S2 hỏng: bộ não đã viết bản đầu, host không có đường nhận bản đó.**
- Việc nền vẫn chạy một lượt Sonnet: receipt succeeded, đầu ra hash `bebd0547...`.
- Khi đăng, host thấy file đã có mà không phải do mục tiêu ghi, nên không ghi đè. Host ghi `goal.publish_conflict` và giữ bản Sonnet trong vùng làm việc (vùng này mất khi dọn sandbox).
- Đánh giá sau đó chấm `c1` trên file của bộ não (đạt), rồi chờ người dùng xác nhận. Thẻ hỏi xác nhận vì thế trỏ vào bản bộ não viết, không phải bản host vừa làm.
- Tin `goal.waiting_human` về đúng phiên có biên nhận. Không có bản đăng nào, nên kiểm "bytes khớp hash host đã ghi khi đăng" hỏng đúng. Cổng chi phí chặn mọi bước sau.

**Đánh giá (chờ review):**
1. **Định tuyến đi được trên engine Claude Code** sau khi dòng gợi ý chỉ đúng ToolSearch: bộ não gọi đúng `select:mcp__javis-plugins__javis_goal`. Một mẫu, chưa chứng minh ổn định.
2. **Lộ một chỗ hở thật của sản phẩm**, đúng ca review đã lường ("làm phần hữu ích ngay và vẫn lưu trách nhiệm vào mục tiêu"). Khi bộ não viết bản đầu trong lượt rồi lập mục tiêu:
   - host vẫn tiêu một lượt việc nền làm lại bản đầu;
   - bản đó không đăng được vì xung đột;
   - tin báo nói sai nguồn gốc ("file đã được sửa sau lần Javis ghi trước", trong khi Javis chưa từng ghi).
   Hướng sửa cần review trước khi làm, ví dụ: lúc lập mục tiêu, host nhận file bộ não vừa ghi trong chính lượt đó làm bản đầu (có hash, đúng phiên, đúng file của tiêu chí) và không xếp lượt việc nền cho tới khi có góp ý.
3. **Bản Sonnet bị mất** vì vùng làm việc nằm trong sandbox. Bộ chạy nên lưu cả đầu ra việc nền khi không đăng được.
4. **Trace thiếu kết quả của khung công cụ** (chỉ có khung gọi), nên không biết vì sao `javis_goal` được gọi hai lần.

Điều kiện MVP thứ nhất (tự định tuyến từ chat, đi hết vòng) vẫn **chưa đạt**: mới qua bước lập mục tiêu, chưa qua vòng bản đầu, góp ý, bản sửa.
