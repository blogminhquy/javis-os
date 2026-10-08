# Resonance A1: cách dùng, nâng cấp, quay về và khôi phục

Áp dụng cho bản 0.87.0 trở đi (Cộng hưởng theo từng trợ lý). Thiết kế đầy đủ: `docs/superpowers/specs/2026-10-08-resonance-a1-agent-scope-design.md`.

## Cách dùng

1. Vào trang **Cộng sự**, chọn một trợ lý, mở tab **Cài đặt** ở cột phải. Khối **Cộng hưởng** nằm trên cùng.
2. Bật công tắc. Lần bật đầu, Javis cấp cho trợ lý một mã riêng (không ghi vào file trợ lý).
3. Trò chuyện với trợ lý đó. Khi giao việc cần theo đuổi tới khi đạt, trợ lý lập mục tiêu. Khung **Mục tiêu của trợ lý** ở cùng chỗ hiện cách hiểu, tiêu chí, sản phẩm, điều đang chờ, lần làm tiếp, số lượt đã dùng, cùng các nút Tạm dừng và Huỷ.
4. Trang **Cài đặt** có danh sách mọi trợ lý kèm công tắc, và mục **Chờ gán**.

Những điều cần biết:
- Chat thường (trang Trò chuyện) không lập mục tiêu, kể cả khi model cố gọi tool.
- Tắt công tắc thì trợ lý vẫn trò chuyện và làm việc một lần như thường. Mục tiêu đang mở đứng yên; xem, tạm dừng, huỷ vẫn được.
- Bật lại không mở lại mục tiêu đang tạm dừng, đã huỷ hay đã kết thúc. Đầu ra hợp lệ làm xong trước lúc tắt được đăng mà không gọi model lại.
- Báo **"cuộc trò chuyện này mở trước khi trợ lý được cấp mã"**: bấm **Mở cuộc trò chuyện mới**. Ca hay gặp là trợ lý vừa xoá rồi tạo lại cùng tên.
- Engine của trợ lý:
  - Claude Code: lập mục tiêu và nhận bản viết ngay trong cuộc trò chuyện.
  - Codex và các engine API: lập được mục tiêu; bản viết trong cuộc trò chuyện chưa được nhận làm sản phẩm (để A4), việc nền tự làm bản đạt.
  - Grok và Antigravity: chưa lập được mục tiêu, giao diện có cảnh báo.
- Trợ lý mất file hay đổi tên tay: Cộng hưởng của nó bị chặn. File có lại thì chọn **Đúng trợ lý cũ** (giữ mã và mục tiêu) hay **Đây là trợ lý mới** (mã mới, phải bật lại).

## Nâng cấp từ 0.86.x

- Không phải làm gì tay. Lần đầu mở kho, Javis chép `resonance.sqlite3` thành `resonance.sqlite3.pre-a1.bak` cạnh file gốc (thư mục `JAVIS_STATE_DIR`), chỉ một lần.
- Kho chỉ có thêm bảng mới (`resonance_agents`, `resonance_agent_events`, `session_agents`, `goal_agents`, `handoff_agents`). Không bảng cũ nào đổi cột.
- Công tắc theo brain cũ (`<brain>/Javis/resonance.json`) không còn cấp quyền gì. File không bị xoá.
- Mục tiêu có từ trước (chưa thuộc trợ lý nào) chuyển sang trạng thái chờ gán:
  - không tự chạy, không tự gán theo tên;
  - vào **Cài đặt → Chờ gán**, chọn trợ lý, bấm **Gán**;
  - gán một lần, không chuyển sang trợ lý khác được trong A1;
  - đầu ra làm trước lúc gán không được đăng; trợ lý làm lại theo quyền của nó.

## Quay về 0.86.x (giữ kho đã nâng)

Bản 0.86.1 chạy được trên kho đã nâng: nó bỏ qua các bảng mới. Đã kiểm bằng mã 0.86.1 thật trong `tests/python/test_resonance_a1_rollback.py`. Trước khi quay về:

1. **Tắt công tắc brain cũ** (`Javis/resonance.json` của mọi brain, hay để tắt). Bản 0.86.x không biết công tắc theo trợ lý và lại dùng công tắc brain; không tắt thì mục tiêu có thể tự chạy trong lúc chuyển.
2. Quay về image hay bản 0.86.x như thường.
3. Chỉ bật lại công tắc brain khi chủ dự án quyết định.

Nâng lại lên A1 sau đó:
- sổ trợ lý, liên kết cuộc trò chuyện và mục tiêu đã gán còn nguyên;
- mục tiêu tạo trong lúc chạy 0.86.x chưa thuộc trợ lý nào, nên nằm ở **Chờ gán**.

## Khôi phục bằng bản sao trước nâng cấp

`resonance.sqlite3.pre-a1.bak` chỉ có dữ liệu tới lúc nâng cấp. Mục tiêu, sự kiện, bằng chứng, sổ trợ lý phát sinh sau đó **không có** trong bản sao.

1. Dừng server.
2. Chép riêng kho hiện tại (`resonance.sqlite3`, cùng `-wal`, `-shm` nếu có) ra chỗ khác để giữ trạng thái mới.
3. Chép `resonance.sqlite3.pre-a1.bak` đè thành `resonance.sqlite3`, xoá `-wal` và `-shm` cũ.
4. Chạy bản 0.86.x (theo mục trên, tắt công tắc brain trước).

Không chạy thao tác khôi phục trên kho thật khi chưa có bản chép ở bước 2.
