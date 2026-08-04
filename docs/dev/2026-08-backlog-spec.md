# Spec: 10 ý tưởng trong sổ tay phát triển (08/2026)

Chốt cách làm cho 10 ý ghi trong sổ "Ý tưởng phát triển Javis" ngày 2026-08-04, rồi làm luôn.
Tài liệu này là **hồ sơ quyết định**: đọc để biết vì sao mỗi ý được làm theo cách đang thấy
trong mã, và vì sao ba trong số đó hoá ra dễ hơn hẳn cái sổ tưởng.

Trạng thái ở cuối mỗi mục là trạng thái THẬT tại thời điểm ghi, không phải mong muốn.

## Trước khi đọc từng mục: ba phát hiện đổi cục diện

Sổ tay ghi ba ý kèm câu "chưa biết có làm được không". Đào thử thì cả ba đều đã có sẵn đường:

1. **NotebookLM không cần viết MCP server.** Sổ ghi "viết MCP server wrapper". Thực tế
   `notebooklm-py` 0.8.0 đã đóng gói sẵn một MCP server: khai `console_scripts` tên
   `notebooklm-mcp`, chạy transport stdio, có cả HTTP kèm bearer token. Việc còn lại chỉ là
   thêm **một mục vào kho connector** như 20 connector khác, không viết dòng Python nào.
2. **Zalo gửi ảnh: thư viện làm được, chỉ là MCP không phơi ra.** `zca-js` nhận
   `sendMessage({ msg, attachments: [đường-dẫn] }, threadId, type)`, và chính `zalo-agent-cli`
   dùng đúng dạng đó cho lệnh `msg send-image`. Nhưng `mcp-tools.js` chỉ khai `text` cho
   `zalo_send_message`. Bản 1.6.2 là bản mới nhất trên npm, nên **chờ upstream là chờ vô hạn**.
3. **Trình sửa dính vào khung chat đã tồn tại từ 0.15.2**, chỉ là link trong chat không dùng
   nó mà bật popup riêng. Ý số 8 do đó không phải viết layout mới, chỉ là đổi chỗ gọi.

## Quy tắc chung khi làm 10 ý này

- **Không dựng bản thứ hai của thứ đã có.** Đây là bài học 0.15.0 và 0.15.1 (cây Vault) và
  0.17.0 (Javis CLI). Ba ý trong đợt này bị nó chi phối trực tiếp: ý 7 và 8 mượn lại trình sửa
  và cây Vault sẵn có, ý 10 mượn lại đúng khối phân trang đã viết cho trang Việc định kỳ.
- **Cột mới trong SQLite phải có migration.** `CREATE TABLE IF NOT EXISTS` không thêm cột cho
  DB cũ. `sessions.py` đã có sẵn vòng `ALTER TABLE ... ADD COLUMN` cho việc này, cột mới đi
  qua đó (`server/sessions.py:203`).
- **Mọi thứ mới phải chạy được trên DB và vault đang có sẵn dữ liệu**, không đòi xoá làm lại.

---

## 1. Tích hợp MCP NotebookLM

**Vấn đề.** Muốn hỏi Javis về nội dung đang nằm trong NotebookLM (nguồn, ghi chú, chat của
notebook) mà không phải mở trình duyệt copy sang.

**Quyết định.** Thêm connector `notebooklm` vào `system/mcp-catalog.json`, chạy server MCP
sẵn có của `notebooklm-py` qua `uvx`. Không viết wrapper.

**Thiết kế.**

- `transport: stdio`, `command: uvx`, args `["--from", "notebooklm-py[mcp]", "notebooklm-mcp"]`.
  Dùng `--from` vì tên package (`notebooklm-py`) khác tên lệnh (`notebooklm-mcp`), và phải
  kèm extra `[mcp]` vì `fastmcp` nằm ngoài dependency lõi. Đây đúng bẫy đã ghi ở connector
  `google-keep` trong cùng kho.
- **Đăng nhập**: NotebookLM không có API chính thức, thư viện đọc cookie phiên Google. Đường
  ổn định nhất trên VPS là dán sẵn cookie đã lấy từ trình duyệt, nên connector nhận hai ô:
  `NOTEBOOKLM_COOKIES` (chuỗi cookie) và `NOTEBOOKLM_PROFILE` (tên hồ sơ để cache phiên).
  `isolate_home: true` giống connector Zalo, để mỗi kết nối một hồ sơ riêng và xoá kết nối là
  phiên đi theo.
- **Phân loại tool** theo `tool_meta`: đọc notebook/nguồn/ghi chú/chat là `read`; tạo và sửa
  notebook, thêm nguồn, ghi note là `write`; xoá notebook, xoá nguồn, chia sẻ ra ngoài là
  `danger`. `default_perm: readonly` - đây là kho tri thức cá nhân, mở quyền ghi phải là hành
  động có ý thức.
- **Ghi rõ rủi ro** trong field `risk`: cookie phiên Google không phải OAuth giới hạn phạm vi;
  thư viện là bản không chính thức nên Google đổi giao thức lúc nào cũng có thể gãy.

**Chỗ chạm.** `system/mcp-catalog.json` (thêm 1 connector), `docs/09-mcp-va-so-lieu.md`.

**Không làm.** Không tự cài `notebooklm-py` vào `requirements.txt` của Javis: nó chạy trong
tiến trình con do `uvx` dựng, kéo vào lõi là thêm `fastmcp` + `playwright` cho một thứ đa số
người dùng không đấu.

**Trạng thái.** Đã làm. Chưa test được đăng nhập thật vì máy dựng không có tài khoản Google,
đúng mức "beta" như 20 connector cùng loại trong kho.

---

## 2. Cho Agent gắn chatbot AI

**Trạng thái: CHƯA LÀM, chờ brainstorm.** Chủ repo chốt ngày 2026-08-04: để lại, bàn kỹ rồi
mới làm.

Ghi lại ba cách hiểu để lần bàn sau khỏi bắt đầu từ số không:

1. **Khung chat riêng cho từng Agent.** Bấm vào một agent trong Studio thì mở một hội thoại
   hỏi thẳng nó, agent chạy với vai trò + skill + model của chính nó. Dùng lại được gần như
   toàn bộ lõi chat: phiên lưu ở `sessions.py` (thêm cột `agent_slug`), engine đi qua đúng
   đường `_tg_answer` mà dashboard/Telegram/CLI đang dùng. Đây là hướng thêm giá trị rõ nhất.
2. **Agent chọn engine riêng.** Agent đã có field `model` (`server/main.py:3432`) nhưng chưa
   chọn được ENGINE. Thêm `engine` vào frontmatter là xong phần dữ liệu; phần khó là
   `workflow_runtime` phải định tuyến theo nó.
3. **Agent làm bot cho kênh ngoài** (Zalo OA, bot Telegram riêng, Messenger). Nặng nhất, và
   đụng thẳng vào rào an toàn "không tự gửi tin ra ngoài" nên phải thiết kế quyền trước.

Ba hướng không loại trừ nhau: 1 và 2 ghép được, 3 nên tách hẳn thành việc riêng.

---

## 3. Gửi tin nhắn Zalo kèm ảnh

**Vấn đề.** `zalo_send_message` của `zalo-agent-cli` chỉ nhận `text`. Muốn gửi ảnh (vd ảnh
Javis vừa tạo, ảnh báo cáo) thì phải tự tay mở Zalo.

**Quyết định.** Viết plugin bundled `zalo-image` phơi tool `zalo_send_image`, gọi CLI
`zalo-agent-cli msg send-image` bằng **đúng home cô lập của kết nối Zalo đang đăng nhập**.

**Vì sao đường này chứ không đường khác.**

- *Chờ upstream thêm tham số*: 1.6.2 đã là bản mới nhất, không có gì để chờ.
- *Fork zalo-agent-cli*: gánh cả một package Node chỉ để thêm một tham số, và mỗi bản mới lại
  phải merge tay.
- *Gọi thẳng zca-js từ Python*: không có, zca-js là thư viện Node.
- *Gọi CLI có sẵn*: chính `zalo-agent-cli` đã có lệnh `msg send-image <threadId> <paths...>`
  hoạt động đúng bằng cách Javis cần. Phiên đăng nhập nằm trong thư mục HOME
  (`STATE_DIR/connector-home/zalo-*`, xem `server/zalo_login.py:157`), và `mcp_store` đã đặt
  `HOME` theo `config.home_dir` khi chạy MCP (`server/mcp_store.py:424`). Nên chỉ cần đặt lại
  đúng biến đó cho tiến trình con là dùng chung phiên, không đăng nhập lại, không quét QR lại.

**Thiết kế.**

- Tool `zalo_send_image(thread_id, paths[], caption?, thread_type?, connection_id?)`.
- `paths` nhận đường dẫn **tương đối gốc vault** (đúng quy ước AI vẫn ghi trong chat, vd
  `attachments/anh.jpg`) hoặc tuyệt đối. Tương đối thì ghép `ctx.vault_root`. File không tồn
  tại thì báo lỗi NGAY, không đẩy sang CLI để nhận một câu lỗi Node khó hiểu.
- **Chặn thoát khỏi vault**: resolve xong phải nằm trong `vault_root`; đường dẫn tuyệt đối
  ngoài vault bị từ chối. Không có rào này thì một câu chat khéo là gửi được `/etc/passwd`
  ra ngoài qua Zalo.
- `min_mode: full`. Gửi tin ra ngoài là hành động thật, không hoàn tác được, đúng hạng với
  `zalo_send_message` đang là `danger` trong `tool_meta`.
- Nhiều kết nối Zalo thì `connection_id` chọn tài khoản; bỏ trống mà có đúng một kết nối thì
  dùng luôn, có nhiều thì **từ chối và liệt kê** chứ không đoán (gửi nhầm tài khoản là gửi
  nhầm danh tính).
- Giới hạn 10 file mỗi lần, timeout 120 giây.

**Chỗ chạm.** `system/plugins/zalo-image/{plugin.yaml,plugin.py}`, `docs/12-zalo.md`,
`CLAUDE.md` (mục Zalo).

**Trạng thái.** Đã làm. Test phủ phần dựng lệnh, phần chọn kết nối và rào đường dẫn; phần gửi
thật cần một tài khoản Zalo đã quét QR nên không chạy được trên CI.

---

## 4, 5, 6. Ghim hội thoại, gom thành Project, gắn icon

Ba ý này đi chung một chỗ dữ liệu nên làm chung một lượt. Tách ra làm ba lần là ba lần
migration cho cùng một bảng.

**Vấn đề.** Danh sách hội thoại xếp thuần theo thời gian: cuộc quan trọng dùng đi dùng lại bị
trôi xuống dưới, và toàn chữ nên nhìn lâu không phân biệt được cái nào là cái nào.

**Quyết định.**

- Ghim: cột `pinned` trên `sessions`, mục ghim gom thành nhóm **Đã ghim** trên đầu danh sách.
- Project: bảng `projects` mới + cột `project_id` trên `sessions`.
- Icon: cột `icon` trên `sessions` và trên `projects` (emoji, tối đa 8 ký tự).

**Thiết kế.**

*Kho (`server/sessions.py`).*

```
projects(id TEXT PK, name TEXT, icon TEXT, brain TEXT, created_at REAL, updated_at REAL)
sessions  + pinned INTEGER NOT NULL DEFAULT 0
          + icon TEXT
          + project_id TEXT            -- NULL = chưa xếp vào project nào
```

- `project_id` **không** khai `REFERENCES projects(id)`: cột thêm bằng `ALTER TABLE` thì
  SQLite không cho khai khoá ngoại, và dù có thì `PRAGMA foreign_keys=ON` sẽ chặn xoá project
  còn hội thoại. Thay vào đó xoá project là **gỡ nhãn** các hội thoại về `NULL` trong cùng một
  transaction. Xoá project KHÔNG bao giờ xoá hội thoại - đó là thứ người dùng sẽ không ngờ tới
  và không hoàn tác được.
- `list_sessions` sắp `pinned DESC, updated_at DESC` và nhận thêm `project`:
  bỏ trống là tất cả, `<id>` là đúng project đó, `none` là các cuộc chưa xếp.

*API (`server/main.py`).*

```
GET    /projects?brain=            -> [{id,name,icon,session_count}]
POST   /projects                   name, icon, brain            -> tạo
POST   /projects/{id}/update       name?, icon?                 -> đổi tên / đổi icon
POST   /projects/{id}/delete                                    -> xoá, hội thoại về NULL
POST   /sessions/{id}/pin          pinned=1|0
POST   /sessions/{id}/icon         icon=<emoji|rỗng>
POST   /sessions/{id}/project      project_id=<id|rỗng>, brain?
GET    /sessions?...&project=      lọc theo project
```

- `/sessions/{id}/project` **tạo hàng nếu chưa có** khi có `brain`. Lý do: dashboard tự sinh
  id hội thoại ở phía client ngay lúc bấm gửi (`dashboard/app.js:253`), còn hàng trong DB thì
  tới lượt server xử lý mới có. Muốn "đang mở project nào thì chat mới tự rơi vào project đó"
  thì phải gắn được nhãn ngay tại lúc bấm gửi. `create_session` đã dùng
  `ON CONFLICT DO NOTHING` nên hai đường tạo cùng lúc không giẫm nhau, và lượt chat sau đó chỉ
  cập nhật `engine`/`model` chứ không đụng `brain`.

*Giao diện (`dashboard/sessions-ui.js`).*

- Thanh Project trên đầu cột trái: nút chọn project đang mở, nút tạo project, đổi tên, đổi
  icon, xoá.
- Đang mở project thì danh sách lọc theo nó, và **chat mới tạo tự gắn project đó** qua
  `window.JavisProjects.claim(sid)` mà `app.js` gọi ngay sau khi mint id.
- Mỗi mục hội thoại: icon (nếu có) + tên; hover ra hàng nút ghim / icon / đổi tên / xoá.
- Bộ chọn icon là một popover ~40 emoji + ô gõ tay + nút Xoá icon. Không kéo thư viện emoji
  picker nào về: nặng hơn cả tính năng.
- **Trạng thái project đang mở lưu ở `localStorage`** theo brain, không lưu server. Nó là chỗ
  đứng của người dùng trên MỘT máy, không phải dữ liệu chung.

**Rủi ro đã tính.** Ghim rồi đổi brain: hội thoại ghim thuộc brain khác không hiện lộn sang, vì
`list_sessions` vẫn lọc brain trước. Project cũng gắn brain, nên đổi brain là danh sách project
đổi theo.

**Trạng thái.** Đã làm cả ba.

---

## 7. Link trong file .md phải bấm được và cây tự sổ tới nơi

**Vấn đề.** Mở một file .md ra đọc, trong đó có link tới file khác, bấm vào không đi đâu cả.
Wikilink `[[..]]` thì đi được, link markdown `[chữ](đường-dẫn)` thì không, mà nhìn hai cái
giống hệt nhau.

**Nguyên nhân thật.** `chat-render.js` xử lý click theo hai lớp: wikilink được xử lý TRƯỚC hàng
rào "đang soạn trong editor thì đừng mở gì cả", còn link file thường (`a.jv-floc`) nằm SAU hàng
rào đó (`dashboard/chat-render.js:818`). Mà bản render của trình sửa là `contenteditable`, nên
mọi link markdown trong file .md rơi đúng vào vùng bị hàng rào chặn. Link http cũng vậy: trong
`contenteditable` trình duyệt không tự mở tab, nó chỉ đặt con trỏ.

**Quyết định.** Trong bản render của trình sửa, link là để **đi**, không phải để sửa chữ - đúng
luật đã áp cho wikilink từ trước. Muốn sửa chữ của link thì bật chế độ Nguồn.

**Thiết kế.**

- Đưa nhánh `a.jv-floc` lên TRƯỚC hàng rào contenteditable, cùng chỗ với wikilink.
- Thêm nhánh cho link ngoài (`http/https/mailto`) trong bản render: mở tab mới.
- **Ảnh vẫn không đụng vào**: ảnh trong bản render phải kéo thả và xoá được như một ký tự, nên
  giữ nguyên đường cũ.
- CSS `cursor: pointer` cho link trong `.ne-wys` và `.jvfe-prev`, để hover là biết bấm được.
- **Cây tự sổ**: `_vtRevealInTree(path)` đã tồn tại từ 0.15.0 (nút "Vị trí" của khung tìm
  kiếm, `dashboard/console.js:5016`). Phơi nó ra thành `window.JavisRevealInTree` và gọi mỗi
  khi điều hướng tới một file bằng link. Không viết cơ chế sổ cây thứ hai.

**Trạng thái.** Đã làm.

---

## 8. Mở file trong chat: bỏ popup, dùng khung dính

**Vấn đề.** Bấm link file trong chat thì bật `.jvfe-modal` che giữa màn hình. Trong khi mở file
từ tab Thư mục ngay bên cạnh lại cho một trải nghiệm khác hẳn: trình sửa chiếm chỗ khung chat.
Hai đường vào cùng một file, hai bộ mặt.

**Quyết định.** Link file trong chat đi vào **đúng trình sửa dính** đã có từ 0.15.2.

**Thiết kế.**

- `chat-render.js` gọi `window.JavisOpenNote(rel)` thay cho `window.JavisEditFile(rel)`.
  `openNote` tự biết: đang ở trang Trò chuyện thì mượn `#chatPageEdit` (chiếm chỗ khung chat),
  ở màn chính thì nổi lên trên visual não - chỗ đó rỗng nên đè là hợp lý.
- **Fallback theo đúng thứ tự**: màn hẹp (dưới 860px) hoặc `JavisOpenNote` chưa nạp thì giữ
  popup cũ. Màn hẹp không đủ chỗ cho khung dính, và popup vốn đã có `@media` riêng cho nó.
- **Loại file không sửa được** (pdf, docx, zip...) thì `openNote` đã có sẵn nhánh
  `_neRenderDownload`: hiện thẻ file kèm nút Mở tab mới và Tải về. Đúng yêu cầu "fallback
  hiện trạng thái đang tải, hoặc cho xem như file bình thường trên trình duyệt", và không phải
  viết gì thêm.
- `JavisOpenNote` đang từ chối chạy trên màn hẹp kèm toast "sửa note trên điện thoại đã tắt".
  Lý do gốc là chạm nhầm node đồ thị, không áp cho việc bấm một link có chủ đích. Nhưng vì
  chat-render đã chặn màn hẹp từ trước khi gọi, không cần đụng vào luật đó.

**Trạng thái.** Đã làm.

---

## 9. Khung chọn skill trong màn sửa Agent

**Vấn đề.** Danh sách skill trong form sửa Agent là một mớ checkbox phẳng. Brain hiện có 55+
skill, nên tìm đúng cái muốn tick là dò bằng mắt qua cả danh sách.

**Quyết định.** Thêm ô tìm kiếm + gom nhóm theo field `group` sẵn có của skill, mỗi nhóm là
một khối sổ ra thu vào được.

**Thiết kế.**

- Nhóm lấy từ `group` trong frontmatter skill (`/skills` đã trả sẵn). Trống thì vào "Chung" -
  đúng quy ước đang dùng ở trang Skills (`dashboard/studio.js:541`).
- Ô tìm lọc theo **tên + slug + mô tả**, bỏ dấu tiếng Việt (gõ "viet email" ra được "Viết
  email"). Đang tìm thì mọi nhóm khớp tự sổ ra, hết tìm thì thu về.
- Nhóm nào có skill đã tick thì mở sẵn khi vào form - người sửa agent quan tâm cái đang bật
  trước tiên.
- Đầu khung có dòng đếm "đã chọn N/M" và nút **Bỏ chọn hết**.
- **Tick vẫn phải giữ khi lọc.** Đây là chỗ dễ hỏng nhất: vẽ lại danh sách theo bộ lọc mà đọc
  trạng thái từ DOM thì skill bị lọc ra khỏi màn hình sẽ mất tick lúc lưu. Nên trạng thái chọn
  giữ trong một `Set` trong bộ nhớ, DOM chỉ là hình chiếu, và lúc lưu đọc từ `Set`.

**Trạng thái.** Đã làm.

---

## 10. Phân trang cho nhật ký tự học và bảng log dưới trang Tiết kiệm

**Vấn đề.** Trang Tự học chỉ hiện 10 dòng nhật ký gần nhất và 12 commit, hết. Trang Tiết kiệm
đổ thẳng cả bảng "Lượt gần nhất" ra một lượt.

**Quyết định.** Dùng lại **đúng khối phân trang đã viết cho trang Việc định kỳ**
(`dashboard/console.js:2211`): tải một lần rồi lật trang phía client.

**Thiết kế.**

- Tách khối đó thành helper dùng chung `_pager(box, items, perPage, renderRow)` thay vì chép
  lần thứ ba. Chép lần thứ ba là bắt đầu ba bản trôi lệch.
- Trang Tự học: `/learn/log` nâng `limit` 10 lên 200, hiện 10 mỗi trang;
  `/learn/review` nâng 12 lên 60, hiện 6 mỗi trang.
- Trang Tiết kiệm: bảng "Lượt gần nhất" hiện 20 dòng mỗi trang.
- Không dùng cuộn vô hạn: các khung này nằm giữa trang có nội dung khác phía dưới, cuộn vô hạn
  sẽ nuốt luôn đường xuống phần đó.

**Trạng thái.** Đã làm.

---

## Những gì KHÔNG làm trong đợt này

- Ý số 2 (chatbot cho Agent) - chờ brainstorm, xem mục 2.
- Không đụng vào giao thức chat, engine, hay runtime tiết kiệm token. Cả 9 ý làm được đều nằm
  ở tầng kho dữ liệu hội thoại, giao diện dashboard, kho connector và plugin.
- Không đổi hành vi mặc định của thứ đang chạy: hội thoại cũ không có project, không ghim,
  không icon, và hiện đúng như trước.
