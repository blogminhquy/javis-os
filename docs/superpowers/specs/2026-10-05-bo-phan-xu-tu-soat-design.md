# Bộ phán xử tự soát và tự chỉnh (0.77.0)

Ngày: 2026-10-05. Chủ đã duyệt thiết kế trong chat (hướng A cộng một phần B, kèm vòng tự soát).
Nối tiếp đặc tả gốc `2026-09-30-bo-phan-xu-nhom-design.md`; đọc mục 3 và 4.1 ở đó trước.

## 1. Vì sao

Bộ phán xử (0.65.x) học tức thì từ phản ứng trong nhóm và từ nút Đúng/Sai, nhưng:

- **Không AI nào đọc được kho của nó.** Kho `chatbot_reply_policy.sqlite3` chỉ đi ra qua route của
  trang Chatbot. Hỏi Javis "vì sao bot im" thì Javis đoán theo tài liệu, không nhìn số liệu thật
  (ca 05/10: Javis trên VPS khẳng định tin tag chủ "không để lại dòng nào", sai, dòng có ghi).
- **Có chỗ học không chạm tới được.** `coarse_gate` trả `addressed_other` cho tin mở đầu bằng
  `@người khác` TRƯỚC khi xét ca dương, nên chủ bấm Sai hay dạy bằng lời cũng không gỡ được.
- Chủ muốn tự động hoá: máy tự soát, tự chỉnh; người chỉ can thiệp khi muốn, và can thiệp bằng
  cách NÓI với Javis chứ không tự tay sửa (nguyên tắc chung [ít cài đặt, đẩy về AI]).

## 2. Mục tiêu và không làm

Làm:
1. Một cửa chung cho AI: hai tool hub (đọc, chỉnh) mà mọi bộ não gọi được.
2. Vòng tự soát chạy nền khi có đủ bằng chứng, dùng **bộ não chính** (model mạnh nhất chủ có),
   tự áp dụng thay đổi trong một tập nút có trần, kèm nhật ký, tự đo và tự hoàn.
3. Hai nút mới AI vặn được (không phải ô cài đặt cho người): độ hăng nói gốc, và xét tin tag người khác.
4. Sửa `addressed_other`: ca dương hoặc nút "xét tin tag" gỡ được chặn.
5. Rào cứng: tool này KHÔNG BAO GIỜ tới tay bot chăm khách.

Không làm:
- AI không sửa mã Python. Chỗ nút vặn không chạm tới thì ghi góp ý vào brain.
- Không đổi nội dung câu trả lời của bot; chỉ đổi việc NÓI HAY IM (giữ nguyên đặc tả gốc).
- Không thêm ô nào trên giao diện. Không đụng hạn mức, nhường-khi-chủ-gõ, mức quyền.
- Vòng soát không sửa hồ sơ vai (chỉ chủ yêu cầu qua chat mới sửa).

## 3. Thành phần

### 3.1 Kho (`chatbot_reply_policy_store.py`)

Bảng mới:
- `tuning(bot_id, key, value, updated_ts)`: nút AI vặn theo bot. Khoá: `eagerness`
  (`low|medium|high`), `consider_tagged` (`0|1`). Không có dòng = mặc định (`medium`, `0`).
- `changes(id, bot_id, ts, actor, review_id, op, target, before_json, after_json, reason,
  evidence_json, status, status_ts)`: nhật ký mọi lần chỉnh. `actor`: `review` (vòng tự soát) hoặc
  `owner` (chủ nhờ qua chat). `status`: `applied`, `kept`, `reverted`, `auto_reverted`, `noted`
  (góp ý mã, không áp dụng gì).
- `review_state(bot_id, last_ts)`: mốc lần soát gần nhất.

Cột mới: `lessons.source` (`''` = chủ/cũ, `review` = vòng soát, `owner_chat` = chủ nhờ qua chat).
Thêm bằng `ALTER TABLE` có rào lúc mở kho lần đầu. Khi vượt 15 bài học, bỏ bài `review` cũ nhất
trước, để bài của chủ không bị máy đẩy ra.

Hàm mới: `get_tuning`, `set_tuning`, `delete_lesson`, `set_offset`, `log_change`, `list_changes`,
`set_change_status`, `label_counts(bot_id, since, until)`, `activity_since(since)`,
`get/set_review_state`. `delete_bot` và `forget` xoá cả bảng mới.

### 3.2 Bộ phán xử (`chatbot_reply_policy.py`)

- `BotProfile` thêm `consider_tagged: bool`. Hàm `apply_tuning(profile, store)` đọc bảng `tuning`
  ghi đè `eagerness` và `consider_tagged`; `chatbot_runtime._rp_profile` gọi nó.
- `coarse_gate(..., has_positive_case, consider_tagged)`: tin `@người khác` chỉ bị loại
  (`addressed_other`) khi KHÔNG có ca dương giống nó VÀ `consider_tagged` tắt. Đi qua cổng thì
  vẫn phải qua `no_grounding` (cần tài liệu), hạn mức và người phán xử như mọi tin.
- Prompt người phán xử thêm một dòng tín hiệu "tin mở đầu bằng tag một người khác".

### 3.3 Vòng tự soát (`chatbot_reply_policy_review.py`, module mới)

Thuần, tiêm `ask`, `store`, `notify`, `write_feedback`, `bot_lookup` để test không cần model.

**Khi nào chạy** (`due_bots(now)`): bot có trong `chatbot_store`, cách lần soát trước ít nhất 24
giờ, và từ lần trước có ít nhất 8 nhãn mới HOẶC 40 tin bị im. Mỗi nhịp chỉ khởi một lượt soát,
không chạy hai lượt cùng lúc. Biến môi trường `JAVIS_REPLY_POLICY_REVIEW=0` tắt hẳn (cho người
vận hành, không phải ô cài đặt).

**Báo cáo** (`build_report`): cửa sổ từ lần soát trước, tối đa 7 ngày. Gồm tổng theo kết luận và
mã im, nhãn theo loại, từng nhóm (tin, im, bỏ lỡ, chen nhầm, độ lệch ngưỡng), tối đa 12 tin bị
gắn nhãn sai và 16 tin im gần đây kèm mã, lý do, điểm, ngưỡng; nút hiện tại; bài học (có id,
nguồn); số ca theo nguồn; 10 thay đổi gần nhất kèm trạng thái (để model không lặp cái đã bị hoàn).
Mọi chữ chat đi qua `clean_chat_text` và nằm trong `<chat_data>`.

**Prompt** yêu cầu DUY NHẤT một JSON:
`{"summary": "...", "changes": [{"op": ..., ..., "reason": "...", "evidence": [id,...]}], "code_feedback": "..."}`.

**Kiểm và áp dụng** (`apply_change`, dùng chung với tool):

| op | tham số | vòng soát được dùng | hoàn lại |
|---|---|---|---|
| `lesson_add` | text (<=200) | có | xoá bài |
| `lesson_remove` | id | chỉ bài nguồn `review` | thêm lại |
| `case_add` | text, verdict, reason, chat_id? | có (nguồn `review`, trọng số 1.0) | xoá ca |
| `case_remove` | id | chỉ ca nguồn `review`/`bootstrap` | thêm lại |
| `offset_set` | chat_id, value (kẹp ±0.25) | có | đặt lại giá trị cũ |
| `eagerness_set` | value | có | đặt lại |
| `consider_tagged_set` | value | có | đặt lại |
| `role_profile_set` | text | KHÔNG (chỉ chủ) | đặt lại |

Vòng soát: tối đa 3 thay đổi mỗi lượt; mỗi thay đổi phải dẫn ít nhất một `evidence` là id quyết
định CỦA BOT NÀY; bỏ thay đổi trùng `op`+`target` đã bị hoàn trong 14 ngày. Thay đổi sai khuôn thì
bỏ riêng nó, không làm hỏng cả lượt. Nhãn chủ nhờ qua chat (`actor=owner`) không cần bằng chứng.

**Tự đo, tự hoàn** (`evaluate_due`): với mỗi lượt soát còn `applied`, so tỉ lệ lỗi
(bỏ lỡ + chen nhầm) / số nhãn trong 7 ngày trước lúc áp dụng với khoảng sau đó. Đủ 6 nhãn sau:
tệ hơn quá 0.15 (và có ít nhất 3 lỗi) thì hoàn CẢ lượt, trạng thái `auto_reverted`; không thì
`kept`. Quá 14 ngày mà chưa đủ nhãn thì `kept`. Thay đổi do chủ nhờ không tự hoàn.

**Góp ý mã**: `code_feedback` khác rỗng thì ghi một dòng `changes` trạng thái `noted` và nối vào
`<brain của bot>/Javis/gop-y-bo-phan-xu.md` (ngày, tên bot, nội dung, id bằng chứng).

**Báo lại**: có thay đổi, có góp ý, hoặc có tự hoàn thì gửi đúng một tin qua `_notify_owner("")`
(hộp thư + Telegram của chủ), viết thường, có câu "không vừa ý thì nhắn Javis hoàn lại".

**Model**: `main._reply_policy_review_ask` dựng engine giống `_reply_policy_ask` (thư mục trống,
không MCP, không công cụ) nhưng chọn **bộ não chính** qua `aux_engine.swap(spec=main_spec())`.
Hết giờ 240 giây. Lỗi hay JSON hỏng: không đổi gì, vẫn ghi mốc soát để khỏi thử lại liên hồi.

**Không công cụ, ở mọi engine** (rà soát độc lập 05/10 bắt được, lỗ có từ trước ở người phán xử):
`swap` thay engine Claude bị nhốt bằng Codex/API/Grok/agy, mà các engine đó được gắn hub. Nên cả
người phán xử lẫn vòng soát đi qua `aux_engine.strip_tools(engine, base)`: API bỏ `discover_all`,
Codex bỏ profile hub và thêm `mcp_servers={}`, Grok gỡ entry hub trong thư mục làm việc, **agy bị
loại** (nó đọc MCP từ file HOME dùng chung với chat của chủ, không gỡ riêng cho một lượt được).
Không còn mắt nào thì về Claude hộp cát.

**Luật hoàn và quyền của chủ**: hoàn một nút hay độ lệch chỉ khi nó còn giữ giá trị thay đổi đó
đặt; đã bị đổi tiếp (chủ, hoặc bộ phán xử tự học) thì đánh dấu `superseded` và giữ giá trị mới.
Nút hay độ lệch mà thay đổi sống gần nhất do chủ đặt thì vòng soát không được đụng. Vòng soát chỉ
tạo ca từ `decision_id` có trong báo cáo. Chỉ ca dương nguồn `owner` hoặc `review` mới gỡ chặn
`addressed_other` (ca khởi tạo và ca học từ người lạ thì không).

**Chữ của model ra khỏi vòng soát** (tin báo chủ, file góp ý) bị bỏ link và khối mã; file góp ý
ghi dạng trích dẫn kèm lời dặn "đọc như dữ liệu"; tin báo không chép nguyên nhận xét của model.

### 3.4 Hai tool hub (plugin hệ thống `system/plugins/javis-reply-policy/`)

- `javis_reply_policy` (readonly). `op`: `bots` (bot có dữ liệu phán xử, kèm số liệu gọn),
  `report` (bot, days), `decisions` (bot, code, label, chat_id, only_silent, limit), `changes`
  (bot). `bot` nhận id hoặc tên (không phân biệt dấu, hoa thường).
- `javis_reply_policy_tune` (safe). `op`: `apply` (bot, action = một op ở bảng trên, các tham
  số, reason) và `revert` (change_id hoặc review_id). Ghi `actor=owner`.

Kết quả tool là chữ gọn, có trần ký tự (engine API cắt 8000).

### 3.5 Rào: tool không tới tay bot chăm khách

Bot ở mức Được ghi / Toàn quyền nhận tool từ hub; khách lạ điều khiển bot. Đọc kho là lộ chat
của khách khác, chỉnh kho là khách tự vặn bot. Nên:

- `mcp_hub.OWNER_ONLY_TOOLS` = hai tool trên. `discover_all(..., for_bot=True)` bỏ chúng TRƯỚC
  tầng lazy (kẻo `javis_run_tool` vẫn gọi được), và `for_bot` nằm trong khoá cache.
- Đường API của bot (`_bot_tra_loi_co_tool`) truyền `for_bot=True`.
- Đường Claude của bot: `claude_config_path(..., bot=True)` gắn header `X-Javis-Bot: 1` (file
  config riêng hậu tố `_bot`); `handle_http` đọc header, chuyển xuống `discover_all`. Thêm lớp hai:
  `disallowed_tools` của bot có `mcp__javis__javis_reply_policy*`.
- Engine Claude của bot là bản "gated" (có `allowed_tools`) nên không nạp plugin trong tiến trình;
  mọi tool đều đi qua hub, rào trên là đủ.

### 3.6 Nối vào máy chủ (`main.py`)

- `chatbot_reply_policy_review.wire(...)` cạnh `chatbot_reply_policy.wire`.
- Vòng `_scheduler_loop`: nhịp riêng 30 phút gọi `chatbot_reply_policy_review.tick()` (đánh giá
  thay đổi đến hạn + khởi tối đa một lượt soát chạy nền bằng `create_task`, giữ tham chiếu).

## 4. Lưu ý vận hành

Bộ não chính là gói Claude Pro/Max thì lượt soát là việc chạy nền trên gói thuê bao, thứ
Anthropic không tính là dùng cá nhân thông thường. Tần suất thấp (tối đa một lần mỗi ngày mỗi
bot, chỉ khi có bằng chứng) nhưng tài liệu `docs/25-chatbot.md` phải nói rõ và gợi ý đặt bộ não
chính khác hoặc tắt bằng biến môi trường.

## 5. Kiểm thử

Script chạy thẳng như các test bộ phán xử cũ (`tests/python/test_reply_policy_*.py`):
- `test_reply_policy_tuning.py`: bảng mới, nút ghi đè profile, `coarse_gate` gỡ chặn tag bằng ca
  dương và bằng nút, bài học `review` rơi trước bài của chủ.
- `test_reply_policy_review.py`: điều kiện đến hạn, báo cáo không lẫn bot khác, kiểm thay đổi
  (trần 3, bằng chứng phải thuộc bot, op cấm, trùng với cái đã hoàn), áp dụng và hoàn từng op,
  tự đo tự hoàn, JSON hỏng thì không đổi gì, góp ý mã ghi file, báo đúng một tin.
- `test_reply_policy_hub_owner_only.py`: `discover_all(for_bot=True)` không có hai tool (cả khi
  lazy bật), `for_bot=False` có; `claude_config_path(bot=True)` có header; plugin `apply`/`revert`.

## 6. Tài liệu

`docs/25-chatbot.md` (và bản tiếng Anh nếu có): mục "Bộ phán xử tự soát", cách nhờ Javis xem và
chỉnh, cách hoàn lại, biến tắt, lưu ý gói thuê bao. CHANGELOG hai thứ tiếng cho 0.77.0.
