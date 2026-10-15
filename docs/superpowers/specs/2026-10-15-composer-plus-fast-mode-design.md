# Khung gõ mới: nút "+", chip mức suy nghĩ có thanh trượt, tia sét Fast mode

Ngày 15/10/2026. Yêu cầu của chủ repo, kèm ảnh khung gõ của Claude và ChatGPT. Bản đồ code và nghiên cứu
Fast mode do 9 agent đọc song song (workflow `composer-map-fastmode`), các ràng buộc dưới đây lấy từ đó.

## Mục tiêu

- Khung gõ gọn như Claude: **một khung bo tròn**, nút **"+"** gom mọi thứ "thêm vào tin nhắn", và menu đó
  mở rộng được về sau mà không phải sửa khung gõ.
- **Mức suy nghĩ tách khỏi chọn model**: đổi mức là việc làm thường xuyên, không được bắt mở danh sách model
  rồi cuộn xuống đáy.
- **Fast mode** bật bằng một nút tia sét, giống ChatGPT: bật thì cam và sóng sánh chạy, tắt thì đứng yên.
- Hiệu ứng dùng màu cam của Javis (`--accent`, #ff7a3c), chạy đúng ở giao diện sáng và tối.

Thành công khi: mọi thao tác cũ vẫn chạy (gõ, Enter gửi, dán và kéo thả file, giọng nói, chọn model, ghim
model theo phiên, trang Chat/Coding/Workspace mượn khung gõ, điện thoại), và hàng điều khiển chỉ còn một.

## Chia làm hai PR

1. **PR 1, giao diện**: khung, menu "+", chip mức suy nghĩ và thanh trượt, nút tia sét lưu được trạng thái.
2. **PR 2, nối Fast mode vào từng bộ não** và đọc lại trạng thái thật bộ não báo về.

PR 2 merge ngay sau PR 1. Giữa hai bản, nút tia sét lưu được nhưng chưa đổi tốc độ, tooltip nói rõ điều đó.

## PR 1: bố cục

```
#bgStrip (viên việc chạy ngầm, giữ nguyên, nằm ngoài khung)
#modelBar (rỗng trên trang chủ; trang Coding vẫn chèn hàng chip ngữ cảnh vào đây)
┌ #hudVoice.hud-voice ─────────────────────────────────────────────┐
│ #voiceFocusResume (giữ, nổi phía trên khung)                      │
│ #attachBar (ảnh, file đính kèm: dời VÀO khung)                    │
│ <textarea id="chatInput" ... rows="1">                            │
│ .cp-row: [+] [#cpChips: chip model | chip mức | tia sét] ··· [mic] [dừng/gửi] │
│ #mbPop  #effPop  #plusMenu (popover, mở lên trên, trong khung)    │
└───────────────────────────────────────────────────────────────────┘
```

- Gốc khung vẫn là `#hudVoice.hud-voice`. Khối `.hud-voice {` trong style.css giữ `align-items: flex-end` và
  `border-radius` đứng trước `background: var(--bg2)` (test ghim thứ tự), thêm `flex-direction: column` và cho con
  `align-self: stretch`. Bo góc tăng từ 18px lên **24px** theo ý chủ repo (duyệt phác thảo 15/10): sửa có chủ ý hai
  test đang ghim 18px (test_theme_tokens, test_o_chat_no_theo_chu) và cp-css `.chatpage-slot .hud-voice` cho đồng bộ. Khung `position: relative`, không `overflow: hidden` (popover và #voiceFocusResume nổi ra ngoài).
- `#attachBar` dời vào khung. Bỏ `"attachBar"` khỏi `CHAT_NODE_IDS` (console.js), không thì trang Chat, Coding,
  Workspace kéo nó ra khỏi khung. `CHAT_NODE_IDS` giữ thứ tự `callBar, chatArea, bgStrip, ...`, giữ `modelBar`.
- `#modelBar` ở lại làm anh em của khung (test ghim id và chỗ trong `CHAT_NODE_IDS`, coding.js chèn chip vào đó).
  Viết liền `<div class="model-bar" id="modelBar"></div>` không khoảng trắng, thêm `.model-bar:empty { display: none; }`.
  Khối `.model-bar {` giữ nguyên chữ (test ghim).
- Textarea `#chatInput` giữ nguyên thuộc tính (`id` đứng đầu, `rows="1"`), giữ mã tự giãn, IME, Enter gửi.
- `#attachBtn` bỏ. app.js dòng gắn `getElementById("attachBtn")` phải có kiểm null, việc mở chọn file chuyển sang
  mục menu "+". Giữ `#fileInput` trong khung.
- `#voiceBtn` dời sang phải, thành nút tròn nhỏ 34px; giữ id, 4 lớp trạng thái `recording`, `handsfree`,
  `in-call`, `focus-waiting`, và listener `click` đồng bộ (mở khoá âm thanh iOS, khoá màn hình). Thu nhỏ vòng
  sáng nhấp nháy cho hợp cỡ mới; `.mic-big.in-call` giữ màu đỏ.
- `#stopBtn`/`#sendBtn` giữ cách bật tắt bằng `style.display` của `updateStopBtn()`.
- Viền mỏng của khung đổi màu cam nhạt khi ô gõ được focus (thay viền của riêng textarea).

### Điện thoại (<= 860px)

- `#mbOpen`/`#mbPop` vẫn lên đầu trang như hiện tại (mobile-chat.js). Nhánh trả về desktop của `placeHeader`
  đổi chỗ trả: chèn lại vào đầu `#cpChips` (neo trước `#effBtn`), không còn `modelBar.firstChild`.
- Chip mức suy nghĩ và tia sét ở lại trong khung (đầu trang không đủ chỗ ~375px).
- Bỏ các luật `order` cũ của `.hud-voice` trên điện thoại, viết lại cho bố cục ô gõ trên, hàng nút dưới.
- Giữ `.cview .hud-voice { margin-bottom: 0; }` và `body.kb-open .hud-voice { margin-bottom: 6px; }` (test ghim).

### Trang mượn khung (Chat, Coding, Workspace)

- cp-css `.chatpage-slot .hud-voice{ background:var(--bg2); ... border-radius:18px; }` giữ nguyên chữ, chỉnh cho
  khớp khung mới; không dùng màu cứng (test_theme_tokens).
- Các luật lưới `edit-on` cho `.attach-bar`, `.model-bar` giữ nguyên chữ (test ghim), hàng trống thì tự xẹp.
- workspace.js đang chỉ khoá `#chatInput` khi phiên chưa sẵn: khoá thêm "+", mic, gửi.

## PR 1: menu "+"

File mới `dashboard/composer-plus.js` (không chữ Việt trong mã chạy; chữ qua i18n). Một danh sách đăng ký:

```js
window.JavisComposerMenu.register({ id, order, icon, label: "i18n.key", hint, run(ctx) | submenu(ctx) })
```

Thêm tính năng sau này chỉ cần gọi `register`. Mục mặc định:

1. **Đính kèm file hoặc ảnh** (Ctrl+U): `fileInput.click()`. Phím tắt Ctrl+U (Cmd+U trên Mac) gắn ở document,
   `preventDefault` vì trình duyệt dùng nó để xem mã nguồn; không chạy khi đang ở ô nhập khác ngoài `#chatInput`
   hoặc trình sửa note.
2. **Đính kèm thư mục**: `<input type="file" webkitdirectory>` ẩn. Bỏ `.git`, `node_modules`, file ẩn; trần
   **50 file**, quá thì báo. Gửi qua đường tải lên sẵn có, tối đa 4 file cùng lúc. Cấu trúc thư mục không giữ
   (đường `/upload` lưu phẳng), câu báo nói rõ.
3. **Chọn file trong brain**: popover tìm theo tên (GET `/files/search?mode=name`), chọn là gắn vào tin như một file
   đính kèm nhưng không tải lên lại. Cần endpoint nhỏ `GET /files/resolve?path=` trả đường dẫn tuyệt đối đã kiểm
   nằm trong gốc brain (chặn `..`, symlink ra ngoài). app.js lộ `window.JavisAttach = { upload, addBrainFile }`,
   `addBrainFile` đẩy vào `pendingAttachments` với khối `[File đính kèm ...]` sẵn có.
4. **Lệnh và kỹ năng** (/): focus ô gõ, chèn "/" ở con trỏ, phát sự kiện `input` để chat-slash.js mở menu.
5. **Kết nối ›**: menu con từ GET `/connect/health` (+ tên từ catalog), mỗi kết nối một chấm trạng thái; dòng mục cha
   ghi "N cần kết nối lại" khi có. Bấm một kết nối hoặc "Mở trang Kết nối" thì sang trang Kết nối.
6. **Gọi trợ lý hoặc quy trình ›**: menu con lấy agent và workflow (GET `/agents`, `/workflows`), chọn là chèn
   token giống hệt menu "/" đang chèn cho loại agent/workflow.

Menu mở lên trên nút "+", điều hướng bằng phím mũi tên, Enter, Esc; bấm ra ngoài là đóng. Menu "/" của
chat-slash.js neo vào khung thay vì textarea để không che ảnh đính kèm.

## PR 1: chip mức suy nghĩ và thanh trượt

- Chip `#effBtn` cạnh chip model, chữ là nhãn tiếng Anh: **Off · Light · Medium · High · Extra · Ultra**
  (giá trị lưu vẫn `off/low/medium/high/xhigh/ultra`, test ghim các chữ này trong model-picker.js). Nhãn đặt
  trong i18n (`eff.*`), cùng chữ tiếng Anh ở vi và en theo ý chủ repo. Tooltip của Ultra ghi thêm "max effort".
- Popover `#effPop`: dòng "Effort <nhãn>", hai đầu "Faster" và "Smarter", thanh 6 nấc, dòng "Recommended" dưới
  nấc Medium. `role="slider"` với `aria-valuemin/max/now/text`, phím mũi tên, Home, End; kéo và bấm đều được.
- Hiệu ứng (file mới `dashboard/effort-slider.js`, canvas): vệt cam phủ tới nấc đang chọn, hạt sáng lấp lánh trôi
  trong vệt, càng về phía Smarter hạt càng dày và to. Chỉ vẽ khi popover mở; `prefers-reduced-motion` thì vẽ tĩnh.
- Lưu bằng `saveModel({reasoning})` như cũ (mức suy nghĩ là thiết lập chung, không theo phiên).
- Khung chọn model bỏ hàng mức suy nghĩ ở đáy; chip model bỏ chữ "Effort: ...".
- Model đã gắn sẵn mức suy nghĩ (Antigravity, tên đuôi `-low/-medium/-high/-xhigh/-max`): popover hiện câu giải
  thích thay cho thanh trượt.
- Bấm ra ngoài hoặc Esc đóng popover; mở popover này thì đóng popover kia.

## PR 1: tia sét Fast mode

- Nút tròn `#fastBtn` cạnh chip mức suy nghĩ, `aria-pressed`. **Không có chữ bật/tắt bên cạnh**; rê chuột hoặc
  focus thì tooltip "Fast mode" kèm một dòng lưu ý tuỳ bộ não:
  - Claude Code: "Tính vào usage credits, giá gấp đôi, không trừ hạn mức gói."
  - ChatGPT/Codex: "Tiêu hạn mức gói nhanh gấp 2,5 lần."
  - API (Claude API, OpenAI, OpenRouter, Gemini): "Giá token cao hơn (khoảng gấp đôi)."
  - Bộ não không có Fast mode (Grok, Antigravity, Groq, DeepSeek, Ollama): nút mờ (`aria-disabled`, không
    `disabled`) và tooltip "Bộ não này không có Fast mode".
- Bật: nền cam với dải sáng chạy ngang liên tục và tia sét đập nhẹ. Tắt: viền xám, đứng yên. Giảm chuyển động thì
  bật chỉ còn nền cam tĩnh.
- Lưu: `saveModel({fast: true|false})` vào `settings.model.fast` (mặc định `false`). Server cần nhánh riêng trong
  POST /settings vì đường đó nuốt khoá lạ (main.py, cạnh nhánh `reasoning`).

## PR 2: nối Fast mode vào bộ não

Mỗi chỗ đặt cạnh chỗ đang truyền mức suy nghĩ. Không bao giờ gửi tham số model không khai là nhận.

| Bộ não | Cách bật | Ghi chú |
|---|---|---|
| Claude Code (SDK) | `ClaudeAgentOptions(settings='{"fastMode": true}')`, gộp với settings đang truyền | chỉ Opus 5.5, Opus 5, Opus 4.8; tắt thì không truyền |
| Claude API | header `anthropic-beta: fast-mode-2026-02-01` + body `"speed": "fast"` | 429/529 hay 400 "does not support the `speed` parameter" thì gửi lại không có `speed` |
| ChatGPT/Codex | `-c service_tier="fast"` trong `_codex_do_sau` khi model khai tier `priority` | tắt thì ép tốc độ thường (máy chủ có `service_tier = "priority"` sẵn trong `~/.codex/config.toml`); kiểm bằng một lượt thật xem giá trị `"default"` có được nhận |
| ChatGPT OAuth gọi thẳng (engine.py) | `payload["service_tier"] = "priority"` | |
| OpenAI API | `service_tier: "fast"` | lỗi 400 nhắc `service_tier` thì gửi lại không có |
| OpenRouter | `service_tier: "priority"` | |
| Gemini | `service_tier: "priority"` | chỉ tài khoản Tier 2/3; lỗi thì gửi lại không có |
| Grok, Antigravity, Groq, DeepSeek, Ollama | không có | nút mờ |

- `codex_models._chuan_hoa` giữ trường `serviceTiers` để biết model nào nhận Fast mode.
- Đọc lại trạng thái thật: Claude Code báo `fast_mode_state` (`off|cooldown|on`) và `fast_mode_disabled_reason`;
  API báo `usage.speed` hoặc `service_tier` trong phản hồi. Javis nhớ trạng thái cuối theo bộ não, tooltip của tia
  sét đọc nó: "đang tạm chạy thường vì vượt giới hạn tốc độ", "cần bật usage credits"...

## Kiểm thử

- Giữ xanh các test đang ghim khung gõ (danh sách trong bản đồ: test_bo_badge_engine, test_call_bar,
  test_viec_nen_hien_ra, test_o_chat_no_theo_chu, test_lui_tien_note, test_theme_tokens, test_sua_md_giu_khung_chat,
  test_trinh_sua_de_len_cot_hoi_thoai, test_mobile_layout, test_do_sau_suy_nghi, test_model_theo_phien,
  test_linh_vat, test_voice_*, test_i18n...). Đổi test chỉ khi chữ bị ghim đổi có chủ ý, kèm lý do.
- Test mới: đăng ký menu "+" (thứ tự, chạy, menu con), lọc thư mục (bỏ `.git`, trần 50), `/files/resolve` chặn
  vượt gốc, thanh trượt (giá trị, phím, nấc khoá), tia sét (lưu, tooltip theo bộ não, nút mờ), POST /settings giữ
  `fast`, PR 2: từng bộ não thêm đúng tham số khi bật và không thêm khi tắt, đường gửi lại khi bị từ chối.
- Xem bằng mắt trong trình duyệt: máy tính sáng và tối, điện thoại 375px, trang Chat, Coding, Workspace.
- Trước khi đẩy: chạy cả bộ test JS và các file Python soi chuỗi của những file đã sửa (bài học #648, #655).

## Ngoài phạm vi

- Esc để dừng câu trả lời (nút dừng ghi "(Esc)" nhưng hiện chưa có), sẽ làm riêng.
- Giữ cấu trúc thư mục khi đính kèm thư mục (cần sửa đường `/upload`).
- Fast mode theo từng phiên (mức suy nghĩ hiện cũng là thiết lập chung).
