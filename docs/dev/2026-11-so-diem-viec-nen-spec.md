# Sổ điểm việc nền: mỗi việc tự tìm model vừa đủ cho nó

Spec viết ngày 10/11/2026, đi tiếp sau `2026-11-javis-nhe-token-spec.md`. Chủ repo chốt hướng bằng ba câu:

- "Javis là hệ thống tự học, tự cải tiến cả cách nó tự học nữa."
- "Nó phải tự điều chỉnh các model nền cho được việc hoặc tiết kiệm token theo ý định của người dùng, chứ không thể
  cố định theo khung anh nghĩ được."
- "Nhớ tối ưu performance, và tối giản nhất cho người dùng, không cần phải cài đặt nhiều."

Vì vậy không ai gán model cho việc nền nữa, kể cả mã. Mã chỉ đưa cho Javis ba thứ: ý định của chủ, một cái thang, và
một cuốn sổ điểm.

Mục 1 đến 6 là phần ĐÃ LÀM trong cùng PR. Mục 7 là phần chưa làm, xếp theo thứ tự đáng làm.

## 1. Ba thành phần

| Thành phần | Là gì | Nằm ở đâu |
|---|---|---|
| **Ý định** | Điều chủ muốn, nói trong chat: `save` (tiết kiệm), `balanced` (để Javis tự cân, mặc định), `sure` (chắc ăn). Áp cho mọi việc nền hoặc riêng một việc | `job_scorecard.intent`, `set_intent`; tool `javis_tune` |
| **Thang** | Các model chat của nhà cung cấp, xếp từ nhẹ tới model của MAIN. Model chính đọc danh sách của chính nhà đó rồi xếp một lần; chỉ xếp lại khi danh sách đổi. Không có bảng tên model trong mã | `auto_background.build_prompt`, `parse` (khoá `ladder`) |
| **Sổ điểm** | Mỗi lần chạy của một việc để lại một dòng: model nào, được việc không, tốn bao nhiêu. Từ đó việc tự leo hay tự hạ bậc | `server/job_scorecard.py`, `STATE_DIR/scorecard.sqlite3` |

Mỗi nhắc hẹn, mỗi loop, mỗi loại việc Kanban (theo `route`) và tự học có **bậc riêng**. Bậc của việc này không kéo
theo việc khác.

## 2. Luật đổi bậc (`job_scorecard.step`, mã thuần, không gọi model)

| Chuyện xảy ra | Kết quả |
|---|---|
| Hỏng **do model** (trả rỗng, sai khuôn, không qua bước tự kiểm, nhà cung cấp từ chối chính model đó) | Lần chạy KẾ leo một bậc. Trần là model của MAIN |
| Hỏng **không do model** (hết hạn mức, mất đăng nhập, đứt kết nối, cần chủ trả lời) | Bậc giữ nguyên |
| Chạy tốt đủ số lần liền nhau (`balanced` 6, `save` 3, `sure` không bao giờ) | Lần kế thử xuống một bậc |
| Lần thử xuống chạy tốt | Ở lại bậc thấp |
| Lần thử xuống hỏng do model | Quay lên, và bậc đó thành "sàn" trong 30 ngày để không thử lại ngay |
| Không có kết luận (chủ bấm dừng, việc chưa kịp chạy) | Không ghi gì |

Hai luật chắn:

- Việc mà tín hiệu duy nhất là "không lỗi" (nhắc hẹn, bước workflow, việc phụ) **không tự hạ bậc**, trừ khi chủ đã
  nói `save`. Hạ bậc dựa trên một tín hiệu yếu là hạ chất lượng mà không ai thấy.
- Sổ điểm **không bao giờ chạy lại** một việc. Việc đã gửi tin hay tạo đơn thì không gửi lần hai; bậc chỉ đổi cho
  lần chạy kế tiếp.

Bậc khởi đầu của một việc chưa có lịch sử: việc Javis tự làm bắt đầu ở đáy thang, việc chủ giao bắt đầu ở bậc model
chính đã chỉ làm "điểm giữa" khi xếp thang. `save` kéo việc chủ giao xuống một bậc, `sure` đẩy mọi việc lên một bậc.

## 3. Tín hiệu "được việc" của từng loại việc

| Việc | Khoá trong sổ | Được việc khi | Hỏng do model khi | Độ tin |
|---|---|---|---|---|
| Tự học | `learn` | mẻ học trả đúng khuôn JSON | trả lời không đọc được thành JSON | mạnh |
| Loop | `loop:<slug>@<brain>` | bước tự kiểm của loop báo đạt | bước tự kiểm báo chưa đạt | mạnh |
| Kanban | `kanban:<route>` | bước nghiệm thu (`ai` hoặc `heuristic`) báo đạt | nghiệm thu báo chưa đạt | mạnh |
| Nhắc hẹn làm việc | `reminder:<id>` | có nội dung trả về | chạy xong mà không trả gì | yếu |
| Mọi việc | (việc đó) | chủ khen qua `javis_tune op=feedback` | chủ chê qua `javis_tune op=feedback` | theo lời chủ |

Chỗ ghi: `learn.LearnFeature.run_once`, `self_improve` (quanh `_run_cycle_inner`), `tasks._run_worker`,
`reminders._fire`. Bước nghiệm thu Kanban là một engine riêng và chạy NGOÀI khối của việc, để nó không bị chấm bằng
chính model yếu vừa làm việc đó.

**Model nào thật sự trả lời.** Việc nền chạy qua một chuỗi dự phòng (`aux_engine._FallbackChain`). Chuỗi giờ báo cho
sổ điểm mắt nào đã trả lời và mắt nào hỏng vì sao. Nếu model Javis chọn bị nhà cung cấp từ chối và model của MAIN
làm thay, việc vẫn xong nhưng bậc đó bị tính một lần hỏng; nếu nó chỉ hết hạn mức thì không tính.

## 4. Người dùng thấy gì

Không có màn hình và không có ô cài đặt nào mới.

- **Nói với Javis.** "Tiết kiệm token giúp anh", "việc gửi báo cáo phải thật chắc", "báo cáo sáng nay sai rồi", "việc
  nền đang chạy model gì". Model chat gọi tool `javis_tune` (plugin hệ thống `javis-tune`, chỉ phiên của chủ thấy):
  `status`, `intent {level, job?}`, `feedback {job, good}`, `undo {id}`. Tên việc lấy theo lời chủ; nhiều việc khớp
  thì Javis hỏi lại.
- **Chuông.** Mỗi lần một việc đổi model có một thông báo mức thấp: việc nào, từ model nào sang model nào, vì sao,
  và câu để hoàn lại.
- **Trang Models.** Vẫn một khối "Model việc nền", ghi "Tự động". Chọn tay một model ở đó thì toàn bộ cơ chế này
  tắt và việc nền chạy đúng model đã chọn.

## 5. Hiệu năng

- Không có lượt gọi model nào được thêm vào trước, trong hay sau một việc. Luật đổi bậc là mã thuần.
- Lượt chat không đi qua sổ điểm.
- Đọc bậc của một việc là tra một dict trong bộ nhớ. SQLite chỉ được mở một lần, lười.
- Mỗi lần chạy xong ghi đúng một lần vào SQLite (WAL), đẩy ra luồng phụ khi đang ở event loop.
- Mỗi việc giữ tối đa 200 dòng lịch sử.
- Thang chỉ được xếp lại khi danh sách model của nhà cung cấp đổi (so chữ ký mỗi ngày, không tốn token).

## 6. Dùng lại gì của hệ thống sẵn có

- **Chuỗi dự phòng việc nền** (`aux_engine._FallbackChain`): nơi duy nhất biết mắt nào trả lời, nên móc ở đó.
- **Phân loại lỗi của chuỗi** (`aux_engine.cooldown_for`): tách "hết hạn mức, mất quyền, sập" khỏi lỗi về chính model.
- **Bước tự kiểm của loop và bước nghiệm thu của Kanban**: đã có, giờ thành tín hiệu cho sổ điểm.
- **Khuôn plugin hệ thống chỉ-của-chủ** (`javis-memory`, `OWNER_ONLY_TOOLS`): cho `javis_tune`.
- **Kênh thông báo của Javis Core** (`_notify_owner`, nhóm `cost`, mức `info`).

## 7. Chưa làm, theo thứ tự đáng làm

Cập nhật: mục 2 dưới đây và phần luật bằng mã của mục 1 đã làm ở bước kế, xem
`2026-11-vong-cai-tien-javis-core-spec.md`. Phần Javis Core suy xét bằng model mạnh vẫn chưa làm.

1. **Vòng tự soát bằng model mạnh cho CÁCH HỌC**, theo đúng khuôn `chatbot_reply_policy_review.py`: gom báo cáo từ sổ
   điểm và nhật ký học, hỏi model chính, nhận tối đa vài thay đổi từ một danh sách núm đóng (thời gian chờ yên, học
   loại gì, ngưỡng thử hạ bậc), mỗi thay đổi dẫn bằng chứng, tự hoàn tác nếu số đo tệ đi. Đây là phần "tự cải tiến
   cả cách tự học" theo nghĩa đầy đủ; phần đã làm mới điều chỉnh MODEL, chưa điều chỉnh nhịp và nội dung học.
2. **Bài học về cách học**: cho mẻ học đọc và ghi thêm vào kho bài học có phạm vi (`agent_lessons.py`), ví dụ khi chủ
   xoá một ghi nhớ sai (`javis_memory op=forget`) thì thành một bài học và một lần "hỏng do model" của việc `learn`.
3. **Thêm tín hiệu**: cảm xúc chủ thả vào kết quả việc nền (`feedback_projector.py`), tin nhắn kế tiếp của chủ sau
   một kết quả (cách `auto_learning.py` đang làm), gợi ý câu tiếp theo có được dùng hay không.
4. **Chi phí đầy đủ**: token hiện chỉ được cộng khi việc chạy qua chuỗi dự phòng hoặc là mẻ học. Engine đơn (không
   chuỗi) của Grok và Antigravity không báo token.
5. **Hiển thị bậc trên từng thẻ việc** ở trang Nhiệm vụ (hiện xem qua chat).
6. **Việc phụ chỉ cần chữ** (gợi ý câu tiếp, phân loại sự cố) chưa có kết luận được việc hay không, nên chúng đứng
   yên ở bậc khởi đầu của mình.

## 8. Chưa kiểm trên máy thật

Môi trường viết mã không có `claude` hay `codex` đăng nhập. Cần nhìn trên một máy đang chạy:

- Model chính có xếp được thang hợp lý từ danh sách model thật của từng gói không (xem `javis_tune op=status`).
- Câu lỗi thật của nhà cung cấp khi từ chối một model có rơi đúng vào nhóm "do model" không
  (`aux_engine._score_link`).
- Model chat có tìm ra `javis_tune` khi chủ nói "tiết kiệm token" không (tool nằm sau `javis_search_tools`).

Mọi đường lui đều giữ hành vi cũ: không có thang, không chọn được, hay sổ điểm lỗi thì việc nền chạy model khởi đầu
của bậc nó, và nếu model đó bị từ chối thì chạy model của MAIN.
