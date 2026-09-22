# Coding Workspace (dự kiến 0.63.0)

**Phiên bản:** v0.3. Thay cho v0.2 (chia bốn giai đoạn) và v0.1 (viết ngoài repo 2026-09-21).
**Trạng thái:** **đã làm** ở 0.63.0, sửa theo phản hồi dùng thử ở 0.63.1, 0.63.2 và 0.63.4 (xem mục 13).
**Phạm vi:** làm gọn trong MỘT phiên sửa. Chủ dự án chốt 2026-09-22.
Tài liệu cho người sửa lõi.

## Ba quyết định chi phối tài liệu này

1. **Một phiên sửa, không chia giai đoạn.** v0.2 chia bốn giai đoạn; thực tế bốn giai đoạn
   nằm rải nhiều tuần thì giai đoạn 1 ra đời thiếu an toàn và không ai quay lại làm nốt. Bản
   này cắt xuống còn thứ nhỏ nhất mà **tự nó đã dùng được và đã an toàn**, mọi thứ khác đẩy
   xuống mục "Để lần sau".
2. **Không có auto switch model.** Đổi engine giữa chừng một tác vụ coding làm hỏng mạch code.
   Chỉ đổi bằng tay. Bỏ hẳn quota router, bảng quota phần trăm, failover tự động.
3. **Mượn màn, không dựng lại.** Mọi thành phần giao diện là node mượn của trang khác.

---

## 1. Vì sao

Javis đã chạy được Claude Code, Codex, Grok Build, Antigravity qua CLI thật, cộng sáu engine
API qua `server/engine.py`. Cái thiếu không phải năng lực coding mà là **một chỗ để làm việc
coding**: hôm nay muốn sai Javis sửa một repo thì phải nói trong khung chat chung, không chỗ
nào ghi đang làm ở repo nào nhánh nào quyền tới đâu, và mở hai việc song song trên cùng repo
là giẫm chân nhau.

Nhóm Code trên rail hiện chỉ có Terminal. `dashboard/code-term.js` đã viết sẵn cho việc này:

> "Code" là một KHU VỰC trên rail chứ không phải một trang: mỗi chức năng là MỘT MỤC trong
> nhóm đó. Hôm nay có Terminal; thêm chức năng sau = thêm một dòng vào CHUC_NANG.

Đây là mục thứ hai của khu vực đó.

## 2. Vì sao vừa MỘT phiên sửa

Vì phần lớn công việc đã có người làm rồi. Ba chỗ then chốt đều đã sẵn:

- **`cwd` đã là tham số của engine.** `claude_engine(..., cwd=...)` (`claude_cli.py:988`),
  `CodexCLI(cwd=...)`. Đường chat đang gọi với `cwd=_brain_root(brain)` tại `main.py:2021`.
  Cho một phiên coding chạy trong repo = truyền cwd khác. Không phải viết runtime mới.
- **Kho phiên đã có cột `channel`.** `sessions.py:73`, cộng `moc_cap_nhat_theo_kenh(brain,
  tien_to)` để lọc theo tiền tố. Trang Cộng sự đã dùng `agent:<slug>` và `workflow:<slug>`.
  Phiên coding chỉ là kênh `coding:<repo-id>`.
- **Khung chat đã cho mượn.** `_borrowChatNodes` (`console.js:6925`) di dời nguyên
  `#chatArea #bgStrip #attachBar #modelBar #hudVoice` kèm mọi handler, WebSocket và streaming
  đã gắn.

Nên bề mặt mã THẬT SỰ mới chỉ còn ba thứ: **sổ repo**, **hàng chip ngữ cảnh**, **worktree kèm
điểm hồi**.

## 3. Luật mượn

Luật này không mới, nó đã nằm trong `console.js` từ lần làm tab Thư mục:

> Không dựng lại cây thứ hai. Bản đầu của tính năng này viết hẳn một module cây riêng, và chủ
> repo chỉ ra ngay: "sao không bê nguyên cái cây y hệt bên Javis sang mà phải dựng lại". Đúng
> [...] Dựng bản thứ hai là chép lại từng đó thứ rồi để hai bản trôi lệch nhau.

Bảng dưới là **khế ước**. Không viết bản thứ hai của bất kỳ dòng nào bên phải.

| Trang Coding cần | Dùng lại |
|---|---|
| Khung chat (stream, tool call, đính kèm, giọng nói) | `_borrowChatNodes` (`console.js`) |
| Danh sách phiên, ghim, đổi tên, tìm | `sessions-ui.js`, lọc theo kênh `coding:` |
| Cây thư mục repo | `JavisVaultPanel.borrow(host)` (`console.js:7005`) |
| Xem sửa file, tô màu cú pháp | `file-editor.js` + `code-hl.js` |
| Terminal trong phiên | `code-term.js` |
| Chọn engine và model | `model-picker.js` + `model-list.js` |
| Chạy nền khi đóng tab, thông báo lượt xong | `chat_runtime.py` + `background_status.py` + `push.js` |
| Hết lượt gói thuê bao | `limit_resume.py` + `limit-resume.js` |
| Nhật ký | kho log đang có |
| Thêm mục vào nhóm Code | `RAIL_ITEMS` + `RAIL_GROUPS` id `code` + `CODE_PAGES` (`console.js`) + `CHUC_NANG` (`code-term.js`) |

---

## 4. Phạm vi một phiên sửa

Năm việc. Hết năm việc này là dùng được thật, không phải bản nháp chờ giai đoạn sau.

### 4.1 Mục Coding trong nhóm Code

Bốn chỗ khai báo, mỗi chỗ một dòng, đúng như comment trong `code-term.js` đã dặn:
`RAIL_ITEMS`, `RAIL_GROUPS` id `code`, `CODE_PAGES`, `CHUC_NANG`. Nhãn lấy từ từ điển
`dashboard/i18n/`, không viết cứng.

### 4.2 Sổ repo

`server/coding_store.py`, một file JSON trong `JAVIS_STATE_DIR`, khoá theo brain:

```json
{
  "repos": [
    {"id": "javis-os", "ten": "javis-os", "duong_dan": "/home/user/javis-os", "nhanh_goc": "main"}
  ],
  "phien": {
    "<session id>": {"repo": "javis-os", "nhanh": "main", "worktree": "/var/javis/wt/ab12",
                     "muc_quyen": "full", "diem_hoi": "javis/ab12/3"}
  }
}
```

Thêm repo = nhập đường dẫn tuyệt đối. Kiểm `.git` tồn tại; không phải repo git thì từ chối kèm
lý do, không im lặng nhận.

### 4.3 Hàng chip ngữ cảnh

Nằm ngay TRÊN ô nhập, không phải ở header. Đây là chỗ điều khiển chứ không phải chỗ hiển thị:

```text
[ javis-os ▾ ]  [ main ▾ ]  [ ☑ worktree ]  [ Bypass ▾ ]  [ Claude Code · Opus ▾ ]
```

Chip Engine mở thẳng `model-picker.js` đang có. Chip Mức quyền dùng lại ba mức của Javis
(`suggest` / `auto` / `full`), không đặt tên mới. Đổi giữa chừng được, áp dụng từ lượt sau.

### 4.4 Chạy engine trong repo

Ở `main.py:2021` và chỗ tương ứng của Codex, khi phiên có kênh `coding:` thì `cwd` lấy từ sổ
repo (worktree nếu có, không thì đường dẫn repo) thay vì `_brain_root(brain)`. Mức quyền
truyền y như đường chat đang truyền.

Một luật phải giữ: phiên coding **vẫn dùng MCP Hub và skill như mọi phiên khác**. Không dựng
một đường engine riêng cho coding, vì đó là cách hai đường trôi lệch nhau.

### 4.5 Worktree và điểm hồi

Đây là phần khiến mode Bypass dùng được mà không phải cầu may, nên nó nằm trong phạm vi chứ
không đẩy xuống sau.

- **Worktree**: mode `full` thì mặc định bật, hai mức kia mặc định tắt. `git worktree add` đặt
  ngoài cây repo chính, tên theo phiên. Đóng phiên mà worktree sạch thì dọn; còn sửa dở thì
  giữ và nói trong chat là giữ ở đâu.
- **Điểm hồi**: trước mỗi lượt ở mode `full`, tạo một tag `javis/<phiên>/<n>` trên HEAD hiện
  tại. Rollback là `git reset --hard <tag>`, hiện thành một nút trong lượt đó.
- **Không bao giờ** force push, và không bao giờ đụng nhánh không thuộc phiên.

---

## 5. Đổi engine: chỉ bằng tay

### 5.1 Vì sao bỏ auto switch

Đổi engine giữa chừng nghĩa là Claude đang sửa dở ba file theo một hướng, Codex vào tiếp với
phong cách khác, có thể đạp lại chính sửa đổi trước. Nửa vời hai phong cách thường tệ hơn một
phong cách xoàng. Tiện lợi đổi lại chỉ là tiết kiệm một cú bấm, không đáng.

Nên **không có** router tự chọn engine, **không có** failover khi provider lỗi, **không có**
ngưỡng quota kích hoạt chuyển engine, **không có** bảng quota phần trăm.

### 5.2 Còn lại

Bấm chip Engine, chọn, xong. Tấm xác nhận nói ba điều: engine cũ, engine mới, trạng thái
working tree. Cây bẩn thì đề nghị tạo điểm hồi trước; từ chối cũng đổi được, nhưng tấm xác
nhận nói rõ engine mới sẽ thấy một đống sửa dở không có mô tả.

Trong một phiên sửa này, engine mới **tự đọc lại repo** để hiểu trạng thái, đúng theo mục 6.
Không có bản bàn giao sinh bằng model. Xem "Để lần sau".

### 5.3 Hết lượt gói thuê bao

Giữ nguyên `limit_resume.py`, không đụng: nó chạy lại đúng lượt đó bằng **đúng engine cũ** khi
hạn mức mở. Đó là chạy lại, không phải đổi model, nên không vi phạm quyết định trên.

Thêm đúng một nút vào thẻ hết lượt của `limit-resume.js`: "Đổi engine và chạy tiếp", đi qua
đúng cửa xác nhận 5.2. Người quyết định vẫn là người dùng.

---

## 6. Repo là nguồn sự thật

Trạng thái thật nằm ở `git status`, `git diff`, kết quả test. Engine mới vào phiên luôn phải
tự đọc lại; khi ngữ cảnh trong chat nói khác repo thì tin repo.

Đây cũng là lý do bản bàn giao sinh bằng model chưa cần ở bản đầu: repo cộng diff cộng kết quả
test đã là phần lớn ngữ cảnh, phần thiếu chỉ là **ý định đang dở**, mà ý định đó vẫn nằm
nguyên trong lịch sử chat của chính phiên.

---

## 7. Giao diện

Hai vùng, không phải ba:

```text
┌──────────────┬────────────────────────────────────────────┐
│ PHIÊN CODING │                   CHAT                     │
│ trạng thái   │                                            │
│ repo/nhánh   │  ── hàng chip ngữ cảnh ──                  │
│              │  ── ô nhập ──                              │
└──────────────┴────────────────────────────────────────────┘
```

Không có cột Work Tree cố định. Cây thư mục, trình sửa file và terminal là **tab bật khi cần**
ở vùng phải của khung chat, dùng đúng cơ chế tab Thư mục của trang Trò chuyện. Claude Code
trên web, công cụ coding thuần tuý, cũng không có cột file tree; giữ một cột luôn hiện là mang
tư duy IDE vào một sản phẩm tự nhận là chat-first.

**Điện thoại:** một cột chat, chip xuống một hàng cuộn ngang, danh sách phiên là tấm kéo lên.
Bố cục hai vùng chỉ áp dụng từ bề rộng desktop.

**Trạng thái phiên:** bốn mức `đang chạy`, `xong`, `lỗi`, `hết lượt`, suy từ
`background_status.py` và `limit_resume.py` đang có. Lượt xong khi tab đóng thì thông báo đi
theo đúng đường nền hiện tại, không viết đường thông báo mới.

Mức thứ năm `cần trả lời` (agent dừng lại hỏi) là thứ đáng giá nhất khi chạy nhiều phiên, vì
agent chạy nền rồi dừng lại hỏi mà không ai biết là cách công việc chết âm thầm. Nhưng nhận ra
nó cần đoán ý cuối lượt, mà đoán sai thì báo động giả hoặc bỏ sót. Để lần sau, làm cho đúng.

---

## 8. Dữ liệu và API

Chốt sẵn để lúc làm không phải quyết định lại giữa chừng:

- `GET /coding/repos` - danh sách repo của brain.
- `POST /coding/repos` - thêm, body `duong_dan`. Kiểm `.git`.
- `POST /coding/repos/{id}/delete` - chỉ xoá khỏi sổ, KHÔNG đụng đĩa.
- `GET /coding/session/{sid}` - ràng buộc hiện tại của phiên.
- `POST /coding/session/{sid}` - đặt repo, nhánh, worktree, mức quyền.
- `POST /coding/session/{sid}/checkpoint` - tạo điểm hồi, trả tên tag.
- `POST /coding/session/{sid}/rollback` - body `tag`.

Route mới đặt trong `server/routes/` theo đúng lối `channels.py` và `conversations.py`, không
nhét thêm vào `main.py`.

## 9. Test

Theo quy ước repo, CI chạy `python tests/run.py`:

- `tests/python/test_coding_store.py` - thêm repo không phải git thì từ chối; xoá repo không
  đụng đĩa; sổ di trú được khi thiếu trường.
- `tests/js/test_trang_coding.js` - hàng chip vẽ đúng ràng buộc; đổi mức quyền không mất phiên.

Thêm một canary cho luật mượn: trang Coding không được tự dựng khung chat hay cây thư mục thứ
hai.

---

## 10. Để lần sau

Cắt khỏi bản đầu, có chủ ý, kèm lý do:

- **Bản bàn giao khi đổi engine.** `conversation_state.py` đã có `StructuredState` (goals,
  decisions, open_questions, constraints, artifacts, last_completed_step), việc cần làm chỉ là
  thêm một khối coding (repo, nhánh, điểm hồi, files_changed, test_status). Nhưng theo mục 6,
  engine mới đọc repo là đủ cho bản đầu. Nói cho đúng một con số của v0.1: working state không
  phải "≈ 0 token"; ghi thì 0 vì code ghi, nhưng đọc thì phải nằm trong prompt MỖI lượt.
- **Trạng thái `cần trả lời`** và đẩy nó ra inbox cộng Telegram. Xem mục 7.
- **Preflight trước deploy** (test pass và build pass và có điểm hồi và nhánh được phép), cộng
  **quét secret trước khi commit**. Chưa cần vì bản đầu chưa đấu deploy; đến lúc đấu thì hai
  thứ này vào cùng, không để sau.
- **Git và PR trong giao diện**, adapter deploy Cloudflare / Supabase / VPS, rollback
  deployment.
- **Model chỉ có API chạy trong phiên coding.** Đường đã có (`engine.py`, vòng tool qua MCP Hub,
  tối đa 30 round) nên đây là mở rộng chứ không phải xây mới, chỉ là chưa cần ở bản đầu.

## 11. Quyết định KHÔNG làm

Giữ lại vì lý do từ chối bền hơn thứ bị từ chối:

- **Auto switch model.** Xem 5.1. Chốt 2026-09-22.
- **Bảng quota phần trăm.** Các CLI thuê bao không phơi ra con số đáng tin để đọc trước, chỉ
  biết khi đã vấp. Vẽ bảng đó là hứa một thứ hạ tầng không cấp.
- **Cột Work Tree cố định.** Xem mục 7.
- **Một tầng Handoff Layer riêng.** `conversation_state.py` đã là Working State. Chữ "handoff"
  cũng giữ nghĩa cũ (bot bàn giao cho người, `chatbot_store` / `chatbot_runtime`); việc đổi
  engine gọi là bàn giao phiên.
- **Ép model chỉ có API qua Codex CLI.** v0.1 xếp đây là đường ưu tiên và runtime Javis là
  fallback. Đảo lại: runtime Javis đang chạy thật, Codex-as-harness là giả định chưa kiểm
  chứng, hạ xuống một thử nghiệm một ngày.
- **IDE, editor phức tạp, terminal UI nặng.** Đã có `file-editor.js` và Terminal.
- **Sao chép toàn bộ transcript làm bản bàn giao.**
- **Self-improve / ASA trong tài liệu này.** Javis đã có trang `selfimprove` riêng. Nếu làm,
  ràng buộc cứng: chỉ chạy trong worktree riêng, chỉ mở PR, không tự merge, không tự deploy
  `javis-os`.

---

## 12. North Star

> Một Javis. Nhiều engine. Người dùng chọn engine, Javis lo phần còn lại.

---

## 13. Ba lượt sửa sau khi dùng thử

Bản 0.63.0 đúng tài liệu này nhưng sai trải nghiệm ở mấy chỗ chỉ lộ ra khi có người dùng thật.
Ghi lại vì cả ba lượt đều là CÙNG một loại sai, và loại đó dễ lặp:

- **0.63.1** bỏ màn chặn "Chưa có repo nào" (một bước cài đặt dựng chắn trước một trang CHAT),
  và đổi REPO thành THƯ MỤC (git là thứ đọc ra, không phải điều kiện vào cửa).
- **0.63.2** thay danh sách phiên tự vẽ bằng chính cột hội thoại của trang Trò chuyện
  (`JavisChatSide.mount`), và thêm chế độ Plan.
- **0.63.4** thay ô gõ đường dẫn bằng hộp duyệt thư mục `JavisFolderPicker`, mặc lại bộ lớp
  `.folder-modal/.fm-*` và endpoint `GET /browse` đã có; `/browse` thêm `md=0` (bỏ đếm .md) và
  cờ `git` cho từng thư mục con. Icon mục đổi sang `code-xml`.

Loại sai chung: **dựng bản thứ hai của một thứ app đã có** (danh sách hội thoại, hộp chọn thư
mục), hoặc **bắt người dùng khai dữ liệu cho vừa mô hình bên trong** (phải có `.git`, phải gõ
đường dẫn tuyệt đối). Quyết định 3 ở đầu tài liệu đã nói "mượn màn, không dựng lại"; ba lượt
sửa này là giá của việc chỉ áp nó cho khung chat mà quên mọi thứ nhỏ hơn.
