# Resonance: tiếp nhận bản bộ não viết trong lượt chat

Trạng thái: **đã làm theo thiết kế này, chờ review mã.** Chưa chạy model. Nguồn: pilot lần 3 (`docs/dev/resonance-mvp-e2e-pilot-plan.md`, mục "Lần chạy 3") và review `PR-579-pilot3-review.md`.

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

## Đã làm (chờ review mã)

Chốt hai câu hỏi trên theo đề xuất, review có thể đổi:
- so khớp sau khi đổi CRLF thành LF;
- `HANDOFF_HOLD_S` = 900 giây.

**Mã:**
- `resonance.py`:
  - `note_turn_write`, `drop_turn_writes`, `handoff_after_turn`;
  - `_output_refs`: `advance` tính cả `chat_output`;
  - `_effective_text`: bản trước của `_work_step` là bản đang có hiệu lực;
  - `_artifact_file` nhận bản tiếp nhận;
  - `form_goal` và `revise_goal` nhận `hold_until`.
- `resonance_store.py`: `adopt_artifact` (một giao dịch); `create` và `revise` nhận `work_due_at`.
- `javis-goal/plugin.py`: lập và cập nhật trong lượt chat thì giữ lịch.
- `main.py`:
  - `_resonance_note_write` ở nhánh engine Claude (`_consume_claude`) và nhánh engine API;
  - `_resonance_after_turn` gọi bàn giao và ghi vết `resonance.handoff`.
- Bộ chạy pilot achieve:
  - S2 và S5 nhận "tiếp nhận hoặc đăng";
  - điều kiện chờ gắn với tin báo của đúng revision, không đọc `run_state` của revision trước.

**Test:**
- `test_resonance_inline_handoff.py` (40 kiểm, engine giả, kho thật), theo tám ca review:
  - Write rồi lập, lập rồi Write;
  - file có sẵn, biên nhận của lượt khác, Edit sau Write, ngoài brain, công cụ không có toàn văn;
  - lỗi bằng chứng;
  - bản chat chưa đạt thì việc nền sửa từ bản đó;
  - tạm dừng, tắt tính năng;
  - góp ý cả hai đường;
  - revision đổi giữa chừng, restart, xác nhận cũ.
- `test_resonance_mvp_main.py`: đường nối thật trong main.
  - Bàn giao nhả lịch.
  - Write trong lượt qua đúng helper các nhánh engine gọi thì được tiếp nhận.
  - Mục tiêu đạt mà không có lượt việc nền.

**Giới hạn còn lại:**
- `dry` của bộ chạy lập mục tiêu bằng `form_goal` trực tiếp, nên không đi qua bàn giao. Bàn giao chỉ được kiểm ở hai test trên.
- Engine Grok, Antigravity và Codex chưa ghi biên nhận (không có toàn văn ở sự kiện), nên vẫn chạy như cũ.


## Sửa theo review mã bàn giao (`67007b7d`, 2 P1, 2 P2)

Review trả lời ba câu hỏi:
- **CRLF/LF:** chấp nhận cho việc SO nội dung một Write đã thành công. Hash bằng chứng, mốc thay file và `artifact_ref` vẫn là hash bytes thật.
- **900 giây:** chỉ là mốc đối soát, cần trạng thái bàn giao. Đã làm, xem P1-2.
- **Trước pilot 4:** sửa bốn điểm dưới, chưa tiêu thêm lượt model.

**P1-1, Write thất bại vẫn được tiếp nhận.** Mapper SDK (`claude_sdk_engine.map_message`) giờ giữ `id` của lời gọi, `tool_use_id` và `is_error` của kết quả. `note_turn_event` coi lời gọi `Write` chỉ là **ứng viên**. Chỉ kết quả thành công gắn đúng id mới xác nhận.
- Kết quả lỗi, thiếu kết quả, hay kết quả của lời gọi khác: không có biên nhận.
- Mọi công cụ không nằm trong danh sách chắc chắn chỉ đọc (Edit, Bash, MCP lạ...), nếu gọi SAU một Write, đều làm Write đó mất hiệu lực, kể cả khi nội dung cuối trùng lại.
- Shell hay Task chạy nền làm cả lượt mất hiệu lực.
- Bash gọi TRƯỚC Write (vd `ls`) không ảnh hưởng.
- `javis_write_file` của engine API chưa có kết quả ghi do host xác nhận gắn đúng lời gọi, nên đã bỏ khỏi danh sách lập biên nhận. Engine API chạy như cũ.

**P1-2, việc nền chạy trước bàn giao, đầu ra cũ đè bản tiếp nhận.** Bàn giao giờ là **trạng thái trong kho** (bảng `handoffs`), không phải giờ hẹn.
- Một dòng cho mỗi revision lập hay sửa trong lượt chat, ghi tin nhắn và tiến trình sở hữu (`BOOT_ID`). Dòng được mở trong cùng giao dịch với `create` / `revise`.
- `advance` gọi `handoff_gate` trước khi đăng hay làm:
  - lượt chat của chính tiến trình này còn chạy (`luot_dang_chay.dang_chay`): chờ, đánh thức lại sau `HANDOFF_POLL_S` = 30 giây;
  - lượt không còn chạy, hoặc `BOOT_ID` khác (server đã khởi động lại): chuyển quyền cho việc nền (`expired`) ngay trong giao dịch.
- `finish_handoff` chỉ tiếp nhận khi dòng còn `pending`. Bàn giao đến muộn sau khi việc nền đã nhận quyền trả `handoff_expired`, không tiếp nhận, không đặt mốc.
- Phòng thủ thêm: `_publish_latest` không đăng một đầu ra việc nền CŨ hơn bản tiếp nhận của cùng revision (`superseded`).
- `HANDOFF_HOLD_S` chỉ còn là giờ của lịch đầu tiên.

**P2-1, bỏ sót đầu ra chưa có receipt.** `_e2e_achieve_harness.preserve_work_outputs` tìm theo cả receipt lẫn đường dẫn host quy định (`output_root/<action id>.md`, đúng chỗ `_reconcile` đối soát), và mọi file .md lạc trong vùng làm việc.
- Bản không có receipt thành công được lưu với nhãn `unverified`, không nâng thành succeeded.
- Lưu lỗi, thiếu nơi lưu, hay action succeeded mà không thấy file: không dọn sandbox.

**P2-2, bộ chạy bác nhầm đường sửa hợp lệ.** `adoption_contract` đọc lý do của **từng** lượt việc nền (`intent.last_verdict`, host ghi trước khi gọi model).
- 0 lượt: đạt.
- Có lượt: mọi lượt phải vì `not_met`, có receipt succeeded, và không vượt phần trần còn lại.
- Lượt chạy khi bản đã đạt là làm lại vô ích: bác.
- Không dùng đánh giá đầu tiên, vì đánh giá chưa đạt ngay trước lượt làm không được lưu thành dòng riêng.

**Test:**
- `test_resonance_inline_handoff.py` viết lại theo mapper SDK thật, có các ca review tái hiện:
  - Write lỗi, thiếu kết quả, kết quả của lời gọi khác;
  - Bash sau Write, Edit rồi hoàn lại, shell chạy nền;
  - Bash trước Write, Write rồi ToolSearch và javis_goal (đường pilot lần 3);
  - quá 900 giây mà chat còn chạy;
  - lượt kết thúc không bàn giao, bàn giao muộn, khởi động lại;
  - đầu ra cũ không đè.
- Đột biến kiểm lại:
  - coi lời gọi là đã xác nhận: đỏ 2 kiểm;
  - bỏ cổng bàn giao: đỏ 5 kiểm.
- `test_resonance_e2e_achieve_harness.py` thêm ca P2-1, P2-2, và đúng đường sản phẩm: bản chat BAD được tiếp nhận, việc nền sửa một lượt, hợp đồng chấp nhận.
- `test_sdk_engine.py` và `test_resonance_mvp_main.py` cập nhật theo dạng sự kiện mới.

## Sửa theo review mã bàn giao vòng 2 (`15cbf200`, 1 P1, 2 P2)

**P1-1, công cụ MCP mang đuôi `Write` được coi là Write gốc.** Danh tính công cụ giờ là TÊN ĐẦY ĐỦ, không cắt đuôi.
- Chỉ đúng `Write` của Claude Code mới tạo ứng viên. `mcp__remote__Write` là một MCP báo thành công, không phải lần ghi local.
- Danh sách chỉ đọc gồm công cụ gốc của Claude Code và đúng các tool Javis qua hai server Javis biết rõ (`mcp__javis__...`, `mcp__javis-plugins__...`).
- MCP khác, kể cả `mcp__untrusted__Read`, đi nhánh bảo thủ: làm mất hiệu lực các Write trước nó.

**P2-1, lượt còn sống mất quyền sau ba giờ.** `luot_dang_chay` có thêm sổ SỐNG `_SONG`.
- Chỉ `ket_thuc` (gọi trong `finally` của lượt) mới gỡ, không dọn theo tuổi.
- `dang_chay` chỉ đọc sổ này.
- `_DANG` vẫn dọn theo tuổi, vì nó chỉ dùng để đoán người giao việc.
- Lượt kết thúc thật hay server khởi động lại vẫn nhả quyền.
- Giả định: một tiến trình server sở hữu kho.

**P2-2, nhánh tiếp nhận rồi sửa bỏ mất kiểm receipt.** `_e2e_achieve_harness.work_receipt_ok` là hợp đồng receipt chung cho mọi lượt việc nền, ở cả hai nhánh S2 và S5:
- status succeeded;
- provider thật = provider yêu cầu = provider đã duyệt;
- model thật = model yêu cầu = model đã duyệt;
- `tool_calls_observed` là số 0;
- thiếu trường thì không đạt.

`adoption_contract` thêm điều kiện riêng của đường tiếp nhận (lý do `not_met`, trong trần) trên nền hợp đồng chung.

**Test:**
- `test_resonance_inline_handoff.py`: thêm MCP mang đuôi Write, MCP lạ mang đuôi Read, đối chứng tool Javis đã biết, lượt sống quá ba giờ, và lượt kết thúc thật thì gỡ khỏi sổ.
- `test_resonance_e2e_achieve_harness.py`: thêm ca sai provider, provider khớp nhau nhưng khác bản duyệt, sai model, có công cụ, thiếu trường; đường sản phẩm với receipt bị sửa sai thì bị bác; soát nguồn bộ chạy.
- Đột biến kiểm lại:
  - cắt đuôi tên lại: đỏ 4 kiểm;
  - `dang_chay` đọc sổ dọn theo tuổi: đỏ 2 kiểm.
- Script `PR-579-handoff-round2-checks.py --expect-fixed` dừng ở dòng 101, vì `adoption_contract` nay cần tham số engine đã duyệt (thay đổi chủ ý của P2-2). Cần cập nhật lời gọi trong script.
