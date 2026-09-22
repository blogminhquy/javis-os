# Coding Workspace và Bàn giao phiên (dự kiến 0.63.x)

**Phiên bản:** v0.2 (thay cho v0.1 ngày 2026-09-21)
**Trạng thái:** kiến trúc đang chốt, **chưa viết mã**.
**Tài liệu kỹ thuật cho người sửa lõi.** Người dùng cuối sẽ đọc `docs/29-coding.md` khi có.

## Đổi gì so với v0.1

Bản v0.1 vẽ ra một sản phẩm mới đứng cạnh Javis. Bản này vẽ **một mục trong nhóm Code** dựng
gần như hoàn toàn từ những thứ Javis đã có. Bốn quyết định đổi hướng:

1. **Bỏ hẳn auto switch model.** Chủ dự án chốt 2026-09-22: để router tự đổi engine giữa
   chừng một tác vụ coding là làm hỏng code. Chỉ còn **đổi bằng tay**, và chỉ ở ranh giới an
   toàn. Xoá luôn "Phase 3 Quota Router", bảng quota phần trăm và mọi nhánh failover tự động.
2. **Mượn màn, không dựng lại.** Mọi thành phần giao diện của trang Coding đều là node mượn
   từ trang khác. Không có khung chat thứ hai, không có cây thư mục thứ hai, không có trình
   sửa file thứ hai.
3. **Bỏ cột Work Tree cố định.** Chat chiếm toàn bộ phần giữa; cây thư mục là một tab bật khi
   cần, mượn nguyên panel Vault.
4. **Bỏ "Handoff Layer" như một tầng mới.** Javis đã có `server/conversation_state.py`. Việc
   cần làm là mở rộng nó thêm vài trường coding, không phải xây tầng mới. Chữ "handoff" cũng
   trả lại nghĩa cũ (bot bàn giao cho người ở trang Hội thoại); việc đổi engine gọi là
   **bàn giao phiên**.

---

## 1. Vì sao

Javis đã chạy được Claude Code, Codex, Grok Build và Antigravity qua CLI thật, cộng sáu engine
API qua `server/engine.py`. Cái thiếu không phải năng lực coding, mà là **một chỗ để làm việc
coding**: hôm nay muốn sai Javis sửa một repo thì phải nói trong khung chat chung, không có
chỗ nào ghi "đang làm ở repo nào, nhánh nào, quyền tới đâu", và mở hai việc song song trên
cùng repo là giẫm chân nhau.

Nhóm Code trên rail hiện chỉ có Terminal. `dashboard/code-term.js` đã viết sẵn cho việc này:

> "Code" là một KHU VỰC trên rail chứ không phải một trang: mỗi chức năng là MỘT MỤC trong
> nhóm đó. Hôm nay có Terminal; thêm chức năng sau = thêm một dòng vào CHUC_NANG.

Tài liệu này mô tả mục thứ hai của khu vực đó: **Coding**.

## 2. Nguyên tắc

### 2.1 Mượn chứ không dựng lại

Luật này không mới, nó đã nằm trong `dashboard/console.js` từ lần làm tab Thư mục:

> Không dựng lại cây thứ hai. Bản đầu của tính năng này viết hẳn một module cây riêng, và chủ
> repo chỉ ra ngay: "sao không bê nguyên cái cây y hệt bên Javis sang mà phải dựng lại". Đúng
> [...] Dựng bản thứ hai là chép lại từng đó thứ rồi để hai bản trôi lệch nhau.

Trang Coding tuân thủ nguyên tắc đó triệt để. Bảng dưới là **khế ước**: cột phải là thứ đã
tồn tại, không được viết bản thứ hai của bất kỳ dòng nào.

| Trang Coding cần | Dùng lại cái gì đã có |
|---|---|
| Khung chat (stream, tool call, đính kèm, giọng nói) | mượn node `#chatArea #bgStrip #attachBar #modelBar #hudVoice` qua `_borrowChatNodes` (`console.js`), đúng cách trang Trò chuyện và trang Cộng sự đang làm |
| Danh sách phiên, ghim, đổi tên, tìm kiếm | `dashboard/sessions-ui.js` (sidebar lịch sử của trang Trò chuyện) |
| Cây thư mục của repo | `window.JavisVaultPanel.borrow(host)` (`console.js:7005`), đã có tìm theo tên/nội dung, tạo file, tô sáng file đang mở |
| Xem và sửa file, tô màu cú pháp | `dashboard/file-editor.js` + `dashboard/code-hl.js` (lớp nổi trên desktop, xếp chồng trên trang chat) |
| Terminal trong phiên | `dashboard/code-term.js` (tab, xterm nạp lười) |
| Chọn engine và model | `dashboard/model-picker.js` + `model-list.js` + trang Bộ não |
| Việc chạy nền, hàng đợi, phụ thuộc | Kanban: `server/tasks.py`, `task_store.py`, `POST /kanban/task`, trang Việc |
| Báo "phiên đang chờ anh trả lời" | `server/inbox.py` + `dashboard/notifications.js` + `push.js` + kênh Telegram |
| Hết lượt gói thuê bao | `server/limit_resume.py` + `dashboard/limit-resume.js` (thẻ trong khung chat) |
| Học hạn mức từ lỗi provider | `server/limit_learner.py` |
| Chạy tiếp khi đóng tab | `server/chat_runtime.py` + `background_status.py` |
| Trạng thái có cấu trúc của phiên | `server/conversation_state.py` (`StructuredState`) |
| Thêm mục vào nhóm Code | `RAIL_ITEMS` + `RAIL_GROUPS` id `code` + `CODE_PAGES` (`console.js`) + `CHUC_NANG` (`code-term.js`) |

Phần **thật sự mới** chỉ còn ba thứ: sổ repo, hàng chip ngữ cảnh, và điểm hồi (checkpoint).
Đó là toàn bộ bề mặt mã mới của Giai đoạn 1.

### 2.2 Native first

Claude, Codex, Grok, Antigravity chạy bằng CLI thật của nhà cung cấp. Javis không viết lại
agent loop. Javis giữ: repo, nhánh, quyền, điểm hồi, log, thông báo, giao diện.

### 2.3 Model API dùng runtime Javis, không ép qua Codex

v0.1 xếp "chạy DeepSeek/Kimi qua Codex CLI" là đường ưu tiên và runtime Javis là fallback.
Đảo lại: `server/engine.py` đã có vòng gọi tool đầy đủ qua MCP Hub (tối đa 30 round) và đang
chạy thật. Đó là **đường chính** cho model chỉ có API. Codex-as-harness hạ xuống một thử
nghiệm một ngày, không phải một giai đoạn trong lộ trình.

### 2.4 Repo là nguồn sự thật

Bàn giao phiên chỉ giúp engine mới hiểu **ý định**. Trạng thái thật nằm ở `git status`,
`git diff`, kết quả test. Engine mới luôn phải tự đọc lại; khi bản bàn giao nói khác repo thì
tin repo.

---

## 3. Đổi engine: chỉ bằng tay

Đây là thay đổi lớn nhất so với v0.1.

### 3.1 Vì sao bỏ auto switch

Đổi engine giữa chừng nghĩa là Claude đang sửa dở ba file theo một hướng, Codex vào tiếp với
phong cách khác, có thể đạp lại chính sửa đổi trước. Nửa vời hai phong cách thường tệ hơn một
phong cách xoàng. Chủ dự án chốt: rủi ro đó lớn hơn tiện lợi, và tiện lợi kia chỉ tiết kiệm
được một cú bấm.

Vậy nên **không có** router tự chọn engine, **không có** failover tự động khi provider lỗi,
**không có** ngưỡng quota kích hoạt chuyển engine, **không có** bảng quota phần trăm. Bỏ hẳn
mục 17, 22, 23 và Phase 3 của v0.1.

### 3.2 Còn lại gì

- **Chip Engine** trên hàng ngữ cảnh. Bấm vào là `model-picker.js` đang có, không viết mới.
- Đổi engine mở một tấm xác nhận nói đúng ba điều: engine cũ, engine mới, và trạng thái
  working tree.
- **Điều kiện ranh giới an toàn:** chỉ bàn giao khi working tree sạch, hoặc Javis tạo một
  commit WIP trước. Không sạch và anh từ chối commit thì vẫn đổi được, nhưng tấm xác nhận nói
  rõ là engine mới sẽ thấy một đống sửa dở không có mô tả.
- Sau khi đổi, Javis tự chèn bản bàn giao gọn (mục 6) vào lượt đầu của engine mới, và nói một
  câu trong chat: đang ở việc gì, vừa đổi từ đâu sang đâu.

### 3.3 Hết lượt gói thuê bao thì sao

Giữ nguyên cơ chế đang chạy, không đụng vào: `limit_resume.py` ghi mục chờ và **tự chạy lại
đúng lượt đó bằng đúng engine cũ** khi hạn mức mở. Đó là chạy lại, không phải đổi model, nên
không vi phạm quyết định trên.

Thêm đúng **một nút** vào thẻ hết lượt của `dashboard/limit-resume.js`: "Đổi engine và chạy
tiếp". Bấm là mở đúng cái picker ở 3.2, đi qua đúng cửa xác nhận đó. Người quyết định vẫn là
anh.

---

## 4. Giao diện

### 4.1 Bố cục

Hai vùng, không phải ba:

```text
┌──────────────┬────────────────────────────────────────────┐
│ PHIÊN CODING │                                            │
│              │                   CHAT                     │
│ trạng thái   │                                            │
│ repo/nhánh   │  ── hàng chip ngữ cảnh ──                  │
│              │  ── ô nhập ──                              │
└──────────────┴────────────────────────────────────────────┘
```

Cột phải của v0.1 bị bỏ. Cây thư mục, trình sửa file và terminal là **tab bật khi cần** trong
cùng vùng phải của khung chat, dùng đúng cơ chế tab Thư mục đang có ở trang Trò chuyện.

Lý do: Claude Code trên web, công cụ coding thuần tuý, cũng không có cột file tree. Giữ một
cột luôn hiện là mang tư duy IDE vào một sản phẩm tự nhận là chat-first.

### 4.2 Hàng chip ngữ cảnh

Nằm ngay trên ô nhập, không phải ở header. Đây là chỗ **điều khiển**, không phải chỗ hiển thị:

```text
[ Local ▾ ]  [ javis-os ▾ ]  [ main ▾ ]  [ ☑ worktree ]  [ Bypass ▾ ]  [ Claude Code · Opus ▾ ]
```

- **Nơi chạy**: máy này hoặc VPS. Suy từ cấu hình sẵn có, chưa cần thêm gì ở Giai đoạn 1.
- **Repo**: thay cho khái niệm "Project" của v0.1. Một phiên gắn một repo, agent luôn biết
  thư mục làm việc, anh không phải nhắc lại repo trong mỗi câu.
- **Nhánh**: đọc từ git, đổi được.
- **Worktree**: xem mục 5.
- **Mức quyền**: Plan / Auto / Bypass (mục 7).
- **Engine và model**: mượn `model-picker.js`.

### 4.3 Trạng thái phiên là cột sống, không phải trang trí

v0.1 viết "hiển thị trạng thái đang chạy/dừng/lỗi **nếu cần**". Sai. Chạy full-auto nhiều
phiên thì câu hỏi duy nhất anh cần trả lời khi mở app là: **phiên nào đang chờ tôi**.

Năm trạng thái: `đang chạy`, `cần trả lời`, `xong`, `lỗi`, `hết lượt`.

Và điều quan trọng hơn cái badge: phiên chuyển sang `cần trả lời` thì **đẩy ra ngoài** qua
`inbox.py` và kênh Telegram đang có. Agent chạy nền rồi dừng lại hỏi mà không ai biết là cách
công việc chết âm thầm. Javis có kênh, các công cụ coding khác không có; đây là chỗ Javis hơn
chúng nó, và nó gần như miễn phí vì hạ tầng thông báo đã dựng xong.

### 4.4 Điện thoại

Một cột chat. Chip xuống một hàng cuộn ngang. Danh sách phiên là một tấm kéo lên. Không có
cột nào. Bố cục hai cột ở 4.1 chỉ áp dụng từ bề rộng desktop.

---

## 5. Worktree

v0.1 không nhắc worktree lần nào. Đây là thứ giải quyết vấn đề thực tế nhất của mô hình nhiều
phiên chạy song song: mỗi phiên một `git worktree`, không phiên nào thấy sửa đổi dở của phiên
khác.

**Luật:**

- Mode Bypass thì worktree **mặc định bật**.
- Mode Plan và Auto thì mặc định tắt, bật được.
- Worktree đặt ngoài cây repo chính, đặt tên theo phiên.
- Phiên đóng mà worktree sạch thì dọn; còn sửa đổi thì giữ lại và nói trong chat là giữ ở đâu.

Với tham vọng Javis tự sửa chính Javis, đây là điều kiện bắt buộc chứ không phải tuỳ chọn:
sửa thẳng trên thư mục đang chạy là tự khoá mình ra ngoài.

---

## 6. Trạng thái phiên và bản bàn giao

### 6.1 Thứ đã có

`server/conversation_state.py` đang duy trì `StructuredState` gồm `goals`, `decisions`,
`open_questions`, `constraints`, `artifacts`, `entities`, `last_completed_step`, mỗi mục có
`source_ref` trỏ về transcript, dựng lại được từ SQLite. So với sơ đồ "Working State" của v0.1
thì trùng gần hết.

### 6.2 Thứ cần thêm

Một khối phụ cho phiên coding, ghi bằng sự kiện hệ thống chứ không gọi model:

```json
{
  "repo": "javis-os",
  "worktree": "/var/javis/wt/coding-7f3a",
  "branch": "feature/coding-workspace",
  "checkpoint": "javis/coding-7f3a/3",
  "files_changed": ["dashboard/coding.js"],
  "commands_run": ["npm test"],
  "test_status": "128 passed, 1 failed"
}
```

### 6.3 Nói cho đúng về token

v0.1 ghi working state "≈ 0 token". Không đúng, và sai kiểu dễ dẫn tới tối ưu nhầm chỗ.
**Ghi** thì đúng là 0 token vì là code ghi. **Đọc** thì không: khối trạng thái phải nằm trong
prompt của mỗi lượt, đúng như `context_compiler` đang tính hôm nay. Chi phí thật nhỏ nhưng
khác không, và nó tỉ lệ với số lượt chứ không phải số lần bàn giao.

### 6.4 Bản bàn giao giữ ngắn

Với coding, repo cộng `git diff` cộng kết quả test đã là phần lớn ngữ cảnh, và engine mới phải
tự đọc chúng. Thứ duy nhất thật sự mất khi đổi engine là **ý định đang dở**. Nên bản bàn giao
chỉ ba phần:

- Đang làm gì và vì sao.
- Đã thử gì, hỏng ra sao.
- Bước tiếp theo.

Viết dài hơn là tự tạo một bản mô tả có thể mâu thuẫn với repo, mà theo mục 2.4 thì lúc mâu
thuẫn nó bị bỏ đi. Dài thêm là tốn token để làm tăng xác suất sai.

---

## 7. Ba mức quyền

Giữ nguyên khung ba mức của Javis, không đặt tên mới:

- **Plan**: đọc code, lập kế hoạch, chỉ ra file cần sửa. Không sửa.
- **Auto**: sửa file, chạy test, build. Không đẩy ra ngoài (không push, không deploy).
- **Bypass**: làm hết, gồm commit, push, deploy.

Đổi mức bằng chip, giữa chừng cũng được, áp dụng từ lượt sau.

---

## 8. Điểm hồi và rollback

v0.1 chỉ nói rollback deployment. Nhưng ở mode Bypass, thiệt hại lớn hơn nằm ở **file và git**:
xoá nhầm file chưa commit, sửa thẳng lên `main`, force push đè việc người khác.

**Luật, làm được bằng git thuần, không cần hạ tầng snapshot:**

- Trước mỗi lượt Bypass, Javis tạo một điểm hồi: commit WIP hoặc tag `javis/<phiên>/<n>`.
- Phiên chạy trong worktree riêng.
- Rollback = `git reset --hard <điểm hồi>`. Hiện thành một nút trong log của lượt đó.
- Không bao giờ force push lên nhánh không phải của phiên.

Rollback deployment (Cloudflare, Supabase) để Giai đoạn 4, khi đã đấu deploy.

---

## 9. Preflight thay cho hỏi xin phép

Bypass nghĩa là không hỏi, không có nghĩa là không kiểm. Preflight là điều kiện **máy tự
kiểm**, không làm phiền người:

> test pass **và** build pass **và** có điểm hồi **và** nhánh nằm trong danh sách được deploy.

Thiếu điều kiện nào thì vẫn chạy (anh đã bật Bypass), nhưng Javis **nói rõ đã bỏ qua cái gì**
trước khi đi tiếp. Giữ được tinh thần một lệnh chạy tới cùng mà không mù.

Thêm một bước v0.1 quên: **quét secret trước khi commit**. Agent chạy Bypass đọc `.env` rồi
commit nhầm khoá là tai nạn kinh điển, và nó không hồi được bằng `git reset` vì khoá đã lên
remote.

---

## 10. Nhật ký

Giao diện gọn nhưng log phải đủ. Mỗi phiên có một dòng thời gian: lệnh đã chạy, file đã sửa,
test, commit, deploy, kết quả kiểm tra. Mở khi cần audit, không hiện mặc định.

Dùng lại kho log đang có, không viết kho thứ hai.

---

## 11. Giai đoạn

### Giai đoạn 1: đứng được

- Thêm mục `coding` vào `RAIL_ITEMS`, vào `RAIL_GROUPS` id `code`, vào `CODE_PAGES`
  (`console.js`) và `CHUC_NANG` (`code-term.js`).
- Sổ repo: thêm, chọn, nhớ repo của từng phiên.
- Hàng chip ngữ cảnh, dùng lại `model-picker.js` cho chip Engine.
- Worktree, mặc định bật ở Bypass.
- Chạy Claude Code và Codex trên repo đã chọn.
- Trạng thái phiên năm mức, đẩy `cần trả lời` ra inbox và Telegram.

**Không có trong Giai đoạn 1:** bàn giao phiên, cột file, quota, git nâng cao, deploy.

### Giai đoạn 2: an toàn khi bật Bypass

- Điểm hồi trước mỗi lượt, nút rollback.
- Preflight và quét secret.
- Nhật ký phiên.

### Giai đoạn 3: bàn giao phiên bằng tay

- Mở rộng `conversation_state.py` thêm khối coding (6.2).
- Tấm xác nhận đổi engine, điều kiện ranh giới an toàn.
- Nút "Đổi engine và chạy tiếp" trên thẻ hết lượt.

### Giai đoạn 4: git và deploy

- Commit, push, mở PR từ trong phiên.
- Adapter deploy: Cloudflare trước, rồi Supabase và VPS.
- Rollback deployment.

**Không có Giai đoạn 5 và 6 của v0.1.** Quota Router bỏ hẳn theo mục 3. Self-improve / ASA
tách khỏi tài liệu này: Javis đã có trang `selfimprove` riêng, và trộn vào đây làm phình phạm
vi. Nếu làm, ràng buộc cứng là chỉ chạy trong worktree riêng, chỉ mở PR, không tự merge,
không tự deploy `javis-os`.

---

## 12. Những thứ quyết định KHÔNG làm

Giữ lại vì lý do từ chối bền hơn thứ bị từ chối:

- **Auto switch model.** Đổi engine giữa chừng làm hỏng mạch code. Chốt 2026-09-22.
- **Bảng quota phần trăm.** Các CLI thuê bao không phơi ra con số đáng tin để đọc trước; chỉ
  biết khi đã vấp. Vẽ một bảng như vậy là hứa một thứ hạ tầng không cấp.
- **Cột Work Tree cố định.** Xem 4.1.
- **Một tầng Handoff Layer riêng.** Xem 6.1: đã có `conversation_state.py`.
- **Ép model API qua Codex CLI.** Xem 2.3.
- **IDE, editor phức tạp, terminal UI nặng.** Javis có `file-editor.js` và Terminal rồi.
- **Sao chép toàn bộ transcript làm bản bàn giao.** Xem 6.4.

---

## 13. North Star

> Một Javis. Nhiều engine. Ngữ cảnh liền mạch. Anh chọn engine, Javis làm phần còn lại.
