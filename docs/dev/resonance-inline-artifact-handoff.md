# Resonance: tiếp nhận bản bộ não viết trong lượt chat (thiết kế, chờ review)

Trạng thái: **thiết kế, CHƯA code phần lõi.** Nguồn: pilot lần 3 (`docs/dev/resonance-mvp-e2e-pilot-plan.md`, mục "Lần chạy 3") và review `PR-579-pilot3-review.md`.

## Vấn đề

Bộ não viết bản đầu trong lượt chat (`Write`), rồi lập mục tiêu. Host không có đường nhận bản đó, nên:
1. Việc nền vẫn tiêu một lượt model để viết lại bản đầu.
2. Bản việc nền không đăng được: file đã có, mục tiêu chưa từng ghi, nên chốt chống ghi đè giữ nguyên file. Chốt này đúng và không được bỏ.
3. Thẻ hỏi xác nhận trỏ vào bản A của chat, nhưng receipt mô tả bản B của việc nền, và không có bản đăng nào. Lần sửa sau sẽ lấy bản B chưa đăng làm "bản trước" (`_work_step` đọc receipt), chứ không lấy bản A người dùng đã đọc.

## Nguyên tắc (theo review)

- Mục tiêu dùng lại bản đã làm được. Nguồn có thể là chat hoặc việc nền. Nguồn chat không được giả thành một lượt việc nền và không tính lượt model.
- Tách hai quyền: **đọc file để đánh giá**, và **được thay file ở lần sửa sau**. Quyền thứ hai chỉ cấp khi host có biên nhận ghi tự kiểm chứng được. Lời model nói "em vừa ghi", hay chỉ có đường dẫn hoặc mtime, đều không đủ.
- Không bỏ chốt chống ghi đè, không âm thầm đánh dấu đã đăng.

## 1. Biên nhận ghi trong lượt (host tự lập)

**Nguồn duy nhất là sự kiện công cụ host đã thấy trong lượt, có TOÀN VĂN nội dung:**
- engine Claude Code: sự kiện `tool_call` tên `Write`, `input` có `file_path` và `content` (`claude_sdk_engine.map_message` đã đưa `input` ra);
- engine API và hub: `javis_write_file`, nơi host tự ghi file nên biết chính xác bytes.

**Không lập biên nhận** cho `Edit`, `MultiEdit`, lệnh shell, hay ghi của Codex qua shell: host không có toàn văn. Phần mở rộng ở mục 6.

**Ghi vào sổ lượt** (`luot_dang_chay`, theo khoá lượt đang chạy):
- dạng `{rel, sha256_lf, seq}`;
- `rel` là đường dẫn trong brain, đi qua cùng bộ lọc với lúc đăng: `_brain_file`, đường cấm, loại file, trần dung lượng;
- `sha256_lf` là hash của nội dung sau khi đổi CRLF thành LF (xem rủi ro 1);
- lần ghi sau cho cùng `rel` thay lần trước.

**Chưa là bằng chứng cho tới khi đối chiếu lúc bàn giao.** Lúc bàn giao host đọc file. Hash (sau chuẩn hoá xuống dòng) phải bằng hash của lần `Write` CUỐI cùng cho đường dẫn đó, và sau lần `Write` đó không có `Edit`, `MultiEdit` hay shell nào nhắm đường dẫn ấy. Khác đi thì biên nhận vô hiệu.

## 2. Bàn giao cuối lượt (chống tranh việc với scheduler)

**Khi `javis_goal` create hay update chạy trong một lượt chat web:**
- lịch work đặt ở `now + HANDOFF_HOLD_S` (đề xuất 900 giây) thay vì `now`, với lý do "chờ bàn giao lượt chat";
- vì vậy scheduler không chạy việc nền chen vào giữa lượt, dù bộ não viết trước rồi lập mục tiêu hay lập trước rồi mới viết.

**Cuối lượt**, ở `_resonance_after_turn`, cùng chỗ đẩy thẻ, với mục tiêu create hay continue của đúng tin này:

1. Kiểm trạng thái: tính năng còn bật, không pause hay cancel, revision chưa đổi so với revision lượt này tạo ra, không có latch guard.
2. Tìm biên nhận hợp lệ cho đúng file sản phẩm `_deliverable_rel(goal)`. Không có file khai báo thì không tiếp nhận.
3. **Có biên nhận:** `store.adopt_artifact(...)` chạy trong MỘT giao dịch, khoá chống lặp `adopt:{goal}:{rev}:{sha}`:
   - kiểm lại revision và hash file hiện tại;
   - lưu bản chụp vào kho bằng chứng (kind `chat_output`, gắn revision);
   - ghi `published(rel, sha, source="chat:<message_ref>")` làm mốc. Mốc này cấp quyền thay file ở lần sửa sau, vì bytes đúng là bytes lượt đó ghi, đã được host kiểm;
   - ghi sự kiện `artifact_adopted` (đường dẫn, sha, message_ref, phiên);
   - ghi bằng chứng lỗi thì KHÔNG công bố đã tiếp nhận, rơi về nhánh không có biên nhận.
   Sau đó đặt lịch work `now` để `advance` đánh giá ngay.
4. **Không có biên nhận:** đặt lịch work `now`, giữ nguyên hành vi hiện tại. Nếu file có sẵn, câu báo xung đột nói đúng nguyên nhân (đã sửa ở bản này).

**Lượt lỗi, restart, hay `after_turn` không chạy:** không có bàn giao, lịch vẫn tới hạn sau `HANDOFF_HOLD_S` và chạy như hiện tại. An toàn, chỉ chậm hơn. Bàn giao chạy lại thì khoá chống lặp giữ cho không nhân đôi bằng chứng.

## 3. Đánh giá rồi mới chọn bước tiếp theo (sửa ở các điểm đọc)

- `advance` và `_human_only`: `refs` gồm cả `action_output` lẫn `chat_output` của revision hiện tại.
  - Chỉ còn chờ người dùng xác nhận: chờ, **không** gọi việc nền.
  - Tiêu chí khách quan chưa đạt: việc nền sửa từ đúng bản đã nhận, trong hạn mức.
  - "Có bản đầu" không mặc định là "đủ để chờ duyệt".
- `_artifact_file`: một lần tiếp nhận của revision hiện tại được tính như một lượt làm thành công khi chọn file cho thẻ.
- `_work_step`, bản trước: lấy **bản đang có hiệu lực**, tức file đích khi hash của nó bằng mốc `published` (từ việc nền hay từ chat). Không có mốc thì lấy receipt việc nền như cũ. Nhờ vậy lần sửa dựa trên bản người dùng đã đọc.
- Xác nhận cũ không áp cho hash hay revision mới. Điều này đã có (`artifact_ref` theo từng lần bấm, `guard_seq`); phần test ở mục 5 sẽ kiểm lại.
- Góp ý tạo revision mới: bản cũ chỉ là đầu vào để sửa, không tự thành sản phẩm đạt của revision mới. Nếu lượt góp ý có biên nhận hợp lệ (bộ não tự sửa bằng `Write`), bản đó được tiếp nhận cho revision mới rồi đánh giá lại.

## 4. Hai sửa nhỏ (ĐÃ làm ở commit này)

1. **Câu báo xung đột nói đúng nguyên nhân.** Payload có `had_baseline`. Chưa từng có mốc: "File ... đã có sẵn và chưa được mục tiêu này tiếp nhận, nên Javis giữ nguyên file đó. Bản Javis vừa làm chưa được đăng...". Câu "đã được sửa sau lần Javis ghi trước" chỉ dùng khi có mốc thật. Test ở `test_resonance_mvp_run.py`.
2. **Bộ chạy giữ mọi đầu ra việc nền**, kể cả bản không đăng được, cạnh báo cáo, kèm receipt, hash, trạng thái đăng và sự kiện đăng. Lưu thất bại thì không dọn sandbox và báo rõ.

## 5. Test bằng engine giả (viết cùng phần lõi)

Theo tám ca review nêu:
1. Chat `Write` bản hợp lệ rồi lập mục tiêu: tiếp nhận đúng bản, 0 lượt việc nền, chờ đúng tiêu chí người dùng.
2. Lập mục tiêu rồi mới `Write`: scheduler không chạy trước bàn giao; tiếp nhận đúng.
3. Không tự cấp quyền thay file khi:
   - file có sẵn từ trước;
   - file do lượt hay phiên khác ghi;
   - file bị `Edit` sau `Write`;
   - file bị sửa sau lúc chụp.
4. Bản chat chưa đạt tiêu chí, hay guard không clear: không báo xong. Việc nền sửa từ bản A, giữ luật guard, chi phí và quyền.
5. Góp ý rồi việc nền sửa: prompt có bản A. Góp ý mà chat tự `Write` bản sửa: tiếp nhận cho revision mới, 0 lượt việc nền.
6. Không nhân đôi bằng chứng hay lượt gọi, không tác động trái trạng thái khi:
   - restart, bàn giao lặp;
   - revision đổi giữa chừng;
   - pause, cancel, tắt tính năng.
7. Hash hay revision đổi sau xác nhận: xác nhận cũ không làm bản mới đạt. Tiếp nhận không tạo receipt việc nền giả.
8. Xung đột đăng báo đúng nguyên nhân (đã có).

**Hợp đồng pilot cũng đổi theo:** S2 và S5 nhận "tiếp nhận hoặc đăng", không đòi đúng một lượt việc nền. Trần 2 Opus và tối đa 2 Sonnet vẫn là trần, không phải chỉ tiêu phải tiêu đủ. Nghiệm thu kiểm biên nhận tiếp nhận hoặc đăng, hash, revision, bằng chứng và tin báo; không nới tiêu chí chất lượng.

## 6. Ngoài phạm vi bản này (đề xuất để sau)

- **Biên nhận cho `Edit` và `MultiEdit`:** host có `old_string` và `new_string`, nên dựng lại được nội dung nếu có bản chụp đầu lượt. Nhưng sự kiện `tool_call` tới host gần như cùng lúc CLI thực thi công cụ, nên chụp "trước khi sửa" có thể trượt. Cần thiết kế riêng.
- **Engine không có toàn văn** (Codex ghi bằng shell): không tiếp nhận tự động. Đường đúng là để người dùng cho phép, ví dụ một nút "Dùng bản này" trên thẻ, đây là việc giao diện.
- **Nhắc trong kết quả của `javis_goal`:** "đã lập mục tiêu; sửa file sản phẩm thì viết trọn file bằng Write hoặc để việc nền làm". Chỉ giảm tần suất, không thay đường bàn giao. Có thể thêm sau nếu review muốn.

## Rủi ro và câu hỏi cho review

1. **Xuống dòng.** Claude Code trên Windows có thể ghi `content` với CRLF. So hash sau khi đổi CRLF thành LF giữ được "đúng nội dung lượt đó viết" mà không vỡ vì xuống dòng. Evidence vẫn lưu bytes thật và hash bytes thật. Review có chấp nhận chuẩn hoá này không?
2. **`HANDOFF_HOLD_S` = 900 giây.** Lượt chat bị cắt thì việc nền chậm tối đa 15 phút. Ngắn hơn thì có nguy cơ chen vào một lượt chat dài.
3. **Phạm vi sửa** nằm trong:
   - `luot_dang_chay`: sổ biên nhận;
   - năm nhánh engine trong `main.py`: gọi một helper ghi biên nhận;
   - `resonance_store`: `adopt_artifact`, mốc có `source`;
   - `resonance`: `advance`, `_human_only`, `_artifact_file`, nguồn bản trước;
   - `javis-goal`: đặt lịch giữ chỗ;
   - bộ chạy pilot: hợp đồng S2 và S5.
   Tính năng vẫn tắt mặc định. Brain chưa bật Resonance không đi qua đường nào ở trên.
