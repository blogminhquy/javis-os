# Pilot đầu-cuối Resonance MVP qua đường chat thật: kịch bản và hạn mức đề xuất

**Trạng thái: CHỜ DUYỆT. Chưa gọi model nào cho pilot này.** Bộ chạy đã có và đã chạy ở chế độ `dry` (không gọi model) để kiểm hạ tầng; chế độ `real` chỉ chạy khi người dùng duyệt hạn mức dưới đây.

## Mục đích

Nghiệm thu điều kiện MVP còn thiếu (plan 00-mvp, "Điều kiện hoàn thành MVP", mục 1): một yêu cầu cần theo đuổi đi hết vòng trên host thật, gồm **tự hình thành mục tiêu** từ một tin chat thật, hành động có receipt, kiểm chứng, tiếp tục sau gián đoạn và trả kết quả đúng phiên. Các pilot M3 và M5 đều dựng mục tiêu bằng đề xuất soạn sẵn; pilot này để chính bộ não quyết định có gọi `javis_goal` hay không.

## Bộ chạy

`tests/python/test_resonance_mvp_e2e_pilot.py`, opt-in bằng `JAVIS_RESONANCE_E2E`:

- **Server thật** của checkout đang review, tiến trình riêng, cổng 7791; `JAVIS_STATE_DIR` và `BRAINS_DIR` tạm ở đường dẫn ngắn; brain mặc định (`Brain Default`, dashboard gọi tắt là `"brain"`) bật Resonance.
- **Chỉ chép các ô chọn engine** từ settings.json thật (`auxiliary`, `main`, `engine`, `claude_model`). Không chép khoá, kênh hay tài khoản nào: không Telegram, không Zalo, nên không gửi gì ra ngoài.
- **Đường thật:** tin gửi qua WebSocket `/ws` đúng khuôn của dashboard; thẻ và phản hồi đi qua HTTP thật (kiểm Origin); việc nền chạy qua nhịp lập lịch thật của server (30 giây một nhịp).
- **Gián đoạn thật:** giết CẢ CÂY tiến trình server (trên Windows, `python.exe` của `.venv` là launcher có tiến trình con), không tắt êm.
- Báo cáo JSON thoát ký tự, không có đường dẫn cá nhân; thư mục tạm bị xoá sau khi chạy.

## Kịch bản (chế độ `real`)

Lời người dùng (dữ liệu mô phỏng, lĩnh vực trung lập):

> (Dữ liệu mô phỏng để thử nghiệm.) Từ biên bản họp dưới đây, lo giúp mình một ghi chú Inbox/viec-tu-bien-ban.md liệt kê từng việc kèm người phụ trách và hạn chót. Không cần làm ngay trong lượt này, cứ làm ở nền, xong thì báo để mình xem lại rồi xác nhận. Đừng đụng tới Notes/ghi-chu-cu.md.
> Biên bản họp nhóm nội dung ngày 03/10: Lan soạn kế hoạch bài viết tháng 11, hạn thứ Sáu. Minh kiểm lại lịch đăng, hạn 10/10. Hà gửi bảng số liệu cho cả nhóm trước thứ Hai.

| Bước | Việc | Kiểm |
|---|---|---|
| 1 | Server A lên; gửi tin qua `/ws`; chờ `turn_done` | Lượt kết thúc có `session_id`; bộ não lập ĐÚNG MỘT mục tiêu qua `javis_goal`, gắn đúng phiên; ý định gốc là nguyên lời người dùng; thẻ mục tiêu được đặt vào đúng phiên, có biên nhận |
| 2 | GIẾT server A ngay sau lượt (trước nhịp lập lịch đầu), dựng server B | Nhịp lập lịch tự nhận lịch và làm lượt việc nền; receipt succeeded, đúng provider đã chọn, 0 lần gọi công cụ; sản phẩm đăng đúng chỗ; tin báo (chờ duyệt) về đúng phiên, có biên nhận |
| 3 | GIẾT server B, dựng server C, chờ hơn hai nhịp | Không báo lặp, không gọi thêm model |
| 4 | Bấm "Đạt yêu cầu" qua `POST /goals/{id}/feedback` như nút trên thẻ (đúng revision, đúng `artifact_ref` lấy từ `GET /goals/{id}`) | Host đánh giá lại, mục tiêu thành công, không gọi model thêm; tin báo thành công về đúng phiên, có biên nhận |
| Cuối | | Ghi chú cũ còn nguyên (hash); tổng lượt gọi model trong trần |

**Điều kiện dừng:** bộ não không lập mục tiêu thì dừng và ghi đó là kết quả pilot, KHÔNG thử lại, không sửa lời cho tới khi người dùng quyết. Lượt gọi model vượt trần thì giết server ngay và ghi FAIL. Lỗi bộ chạy thì dừng.

Nếu bộ não tự làm luôn trong lượt (tự ghi file bằng công cụ của nó) thay vì lập mục tiêu, đó cũng là một kết quả cần ghi: tool `javis_goal` mô tả rõ không gọi cho "việc làm xong ngay trong lượt", và lời người dùng ở trên nói rõ là làm ở nền.

## Hạn mức đề xuất

| Mục | Đề xuất |
|---|---|
| Lượt bộ não chính | **1** (engine chính đang chọn: `anthropic-cli` / `claude-opus-5-5`, gói thuê bao) |
| Lượt việc nền | **1 dự kiến, tối đa 2** (engine việc nền: `anthropic-cli` / `sonnet`). Trong cửa sổ pilot không có lượt thứ hai: thử lại khi chưa đạt cách 15 phút |
| Trần cứng của bộ chạy | **3 lượt gọi** (`JAVIS_RESONANCE_E2E_MAX_CALLS=3`); vượt là giết server |
| Token ước tính | Lượt bộ não: vài chục nghìn token vào (prompt hệ thống của Javis và công cụ); lượt việc nền: khoảng 18 nghìn vào, dưới 1 nghìn ra (đo ở pilot M3, M5) |
| Thời gian | Khoảng 8 đến 15 phút (ba lần dựng server, một lượt chat, hơn hai nhịp chờ) |
| Số lần chạy | **Một lần.** Không chạy lại nếu kết quả không như ý; báo cáo nguyên trạng |

**Tuỳ chọn mở rộng (chưa đề xuất chạy ngay):** thêm tin bổ sung thứ hai ("Thêm việc: ...") để đo bộ não gọi `javis_goal op=update`, cộng 1 lượt bộ não và 1 lượt việc nền, trần 5.

Gói thuê bao: một lần chạy cục bộ trên máy người dùng, không chạy nền 24/7, không VPS, không dùng chung tài khoản.

## Đã kiểm ở chế độ `dry` (không gọi model)

`JAVIS_RESONANCE_E2E=dry`: không gửi tin chat, engine việc nền đặt là một provider bộ chọn chỉ chữ chặn sẵn, mục tiêu được lập bằng đúng hàm tool `javis_goal` dùng (`form_goal`) vào kho của server thật. Kết quả 13/13 kiểm xanh, **0 lượt gọi model**, khoảng 2 phút:

- server thật lên, `/ws` nhận kết nối qua kiểm Origin;
- giết server rồi dựng lại: nhịp lập lịch tự nhận lịch và chạy lượt việc nền (bị chặn trước khi gọi model, như dự định);
- tin báo về đúng phiên, có biên nhận của host; dựng lại lần nữa không báo lặp, không gọi thêm;
- API thẻ `GET /goals/{id}` và `POST /goals/{id}/feedback` qua kiểm Origin của server thật;
- ghi chú cũ còn nguyên.

Lần chạy `dry` đầu làm lộ một điều của chính bộ chạy: tham số brain `"pilot"` không được ánh xạ thành thư mục brain (dashboard gửi `"brain"` cho brain mặc định, kênh khác gửi đường dẫn tuyệt đối). Đã đổi bộ chạy sang brain mặc định và `"brain"`, đúng như dashboard.

## Pilot này KHÔNG chứng minh

- Kênh khác ngoài chat web (Telegram, Zalo, giọng nói).
- Dữ liệu thật hay mục tiêu dài ngày; guard nhảy trên dữ liệu thật.
- Ca ứng viên tụt hạng trên model thật (M5; không đổi `no_improvement` thành `regression`).
- Độ ổn định của quyết định lập mục tiêu: một lần chạy chỉ là một mẫu.

## Lệnh chạy khi được duyệt

```bash
JAVIS_RESONANCE_E2E=real JAVIS_RESONANCE_PILOT_SETTINGS=D:/Project/Javis-OS/server/settings.json JAVIS_RESONANCE_E2E_MAX_CALLS=3 JAVIS_RESONANCE_E2E_OUT=docs/dev/resonance-mvp-e2e-pilot.json D:/Project/Javis-OS/.venv/Scripts/python.exe tests/python/test_resonance_mvp_e2e_pilot.py
```
