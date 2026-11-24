# Rà soát tốc độ Javis OS (23/11/2026)

Bản 0.631.0, đo trên máy đang chạy thật (Docker, 2 vCPU, 8 GB RAM, không swap), dữ liệu thật: brain mặc định
5.420 file .md, 142 skill, 2.877 cuộc chat, 45.863 tin nhắn. Lượt này chỉ đo và báo cáo, không sửa mã sản phẩm.
Ba việc ở mục 6 đã làm ở lượt sau, số đo trước và sau nằm ở mục 11.

Mọi con số dưới đây là số vừa đo trong ngày 23/11/2026, lệnh ở mục 9. Chỗ nào ghi "dự kiến" là phép tính từ số
đã đo, phải đo lại sau khi sửa. Chỗ không đo được ghi rõ ở mục 8.

## 1. Kết luận ngắn

1. **Chỗ chờ lâu nhất là chữ đầu tiên của lượt chat.** Claude Code: trung vị 12,2 giây khi tiến trình nguội,
   5,6 giây khi ấm. Chỉ 32% lượt chạm tiến trình ấm. 53% lượt chờ hơn 10 giây mới thấy chữ đầu.
2. **Mở dashboard trên điện thoại mạng chậm: 12,2 giây lần đầu, 7,9 giây lần sau.** Lần sau chỉ tải 45 KB mà
   vẫn 7,9 giây, tức là thời gian nằm ở việc chạy 2,1 MB JavaScript khởi động, không nằm ở mạng.
3. **Máy chủ khởi động mất 20 giây vì image Docker không có bytecode biên dịch sẵn.** Có bytecode thì còn
   7,2 giây (đo 5 lần mỗi kiểu, cùng lúc, cùng tải).
4. **Năm API đọc chậm vì quét lại đĩa ở mỗi lần gọi:** `/graph` 896 ms, `/conversations` 416 ms, `/brains` 302 ms,
   `/reminders` 200 ms, `/skills` 176 ms. Phần còn lại đều dưới 100 ms.
5. **Máy đang bão hoà CPU lúc đo** (tải 4 đến 8 trên 2 nhân) do một việc xử lý ảnh chạy nền từ một phiên chat
   khác. Trong lúc đó `/health` có p95 197 ms và lần chậm nhất 1,9 giây. Việc nền nặng làm chậm cả dashboard.

Tiền đề "index.html nạp khoảng 125 thẻ script" đúng với file nguồn nhưng không đúng với trang thật: máy chủ đã
gộp khoảng 120 file thành một gói, trang phục vụ chỉ còn 4 thẻ script có `src`. Vấn đề còn lại là gói đó nặng
(584 KB sau nén, 2.122 KB mã phải chạy).

## 2. Bối cảnh đo và giới hạn

- **Máy:** 2 vCPU, RAM 8.126 MB, không swap. RAM còn dùng được 1.874 đến 3.033 MB trong lúc đo.
- **Tải lúc đo:** loadavg 4,1 đến 8,5. Mẫu 20 giây: tổng 197% của một nhân. Hai tiến trình xử lý ảnh (nâng nét
  ảnh bằng mô hình chạy trên CPU, do một phiên chat ở brain khác khởi chạy bằng `nohup`) chiếm 90,8% và 72,8%,
  RAM 910 MB và 1.378 MB. uvicorn 22,3%, RAM 559 MB. Tổng 49 tiến trình, 5.743 MB.
- **Hệ quả:** số đo thời gian phía máy chủ ở đây cao hơn lúc máy rảnh. So sánh trước và sau trong cùng điều kiện
  thì vẫn đúng.
- **Không đăng nhập vào bản đang chạy.** Trong môi trường có sẵn tài khoản quản trị, nhưng nó không được giao cho
  việc này, và đăng nhập sẽ ghi một phiên cùng một dòng nhật ký bảo mật lên hệ thống thật, trái yêu cầu chỉ đọc.
  Vì vậy:
  - Dashboard đo tới lúc **ô đăng nhập gõ được**, không phải ô chat. Mã và CSS tải y hệt nhau ở hai trường hợp,
    chỉ thiếu các lần đọc dữ liệu sau đăng nhập.
  - API đo **trong một tiến trình riêng**: nạp đúng `main.app` thật, tắt cổng đăng nhập cho riêng tiến trình đó,
    không mở cổng mạng, không chạy tác vụ khởi động, chỉ gọi các lần đọc không có tác dụng phụ.
  - Muốn đo tới ô chat: chạy lại bench trình duyệt với `JAVIS_BENCH_COOKIE=<giá trị cookie javis_session>`.
- **Một tác dụng phụ đã xảy ra, nói rõ:** lần gọi `/usage/summary` kích hoạt `usage_index.refresh` (quét lại file
  phiên của Codex và cập nhật chỉ mục usage, đúng việc trang Usage vẫn làm khi mở). Nó chạy hơn 45 giây, bị dừng,
  và hai API usage đã bị gỡ khỏi script đo.

## 3. Đang chậm ở đâu

### 3.1 Lượt chat (867 lượt thật trên dashboard, 09/11 đến 23/11/2026)

Nguồn: sự kiện `engine.first_output` trong `runtime.db`, đo từ đầu `_do_turn` (`server/main.py:21271`) tới sự
kiện đầu tiên engine trả về.

| Engine | n | p50 | p75 | p95 |
|---|---|---|---|---|
| Claude Code, nguội | 470 | 12,2 s | 18,8 s | 44,6 s |
| Claude Code, ấm | 252 | 5,6 s | 8,9 s | 23,3 s |
| Codex, nguội | 118 | 8,3 s | 16,5 s | 31,2 s |
| Codex, ấm | 27 | 6,1 s | 12,0 s | 23,7 s |

- Phân bố cả 867 lượt: dưới 3 giây 6,3%; 3 đến 6 giây 17,5%; 6 đến 10 giây 23,2%; 10 đến 20 giây 35,9%;
  trên 20 giây 17,1%.
- Tỉ lệ ấm: 279 trên 867 lượt (32%). Bảy ngày gần nhất: 33%.
- Phần Javis tự làm trước `_do_turn` (từ `task.started`): p50 132 ms, p75 410 ms, p95 2.695 ms, lớn nhất 13,8 giây.
- `build_system_prompt()` trên brain thật: 288 ms (đích của chính `bench_hotpath.py` là dưới 40 đến 60 ms).
- Chạy cùng lúc 4 lượt trở lên: Claude nguội p50 15,5 giây và p95 65,3 giây, so với 12,3 và 32,4 giây khi chạy
  một mình.
- Cả lượt (tới `task.finished`): Claude nguội p50 161 giây, ấm 65 giây; Codex nguội 104 giây, ấm 35 giây.
- Riêng lệnh `claude --version` chỉ mất 83 ms, nên bản thân việc mở file chạy không phải là chi phí nguội.

**Nguyên nhân gốc:** chênh lệch nguội trừ ấm khoảng 6,6 giây là mở tiến trình, resume phiên và nối MCP
(`server/warm_pool.py`). Hồ giữ ấm lấy một phần tư RAM trống, mỗi tiến trình Claude tính 300 MB
(`warm_pool.py:30`, hàm `budget_mb`). Với 1.874 đến 3.033 MB trống, phép tính đó cho 468 đến 758 MB, tức 1 đến 2
cuộc chat được giữ ấm. Đây là suy ra từ mã và số RAM đo được; sự kiện hiện không ghi **lý do nguội** nên chưa có
số trực tiếp cho từng lý do (chat mới, nghỉ quá 300 giây, đổi cấu hình, hết ngân sách RAM, vừa khởi động lại).

### 3.2 Mở dashboard (trình duyệt thật, 5 lần mỗi trường hợp, trung vị và p95)

| Trường hợp | Gõ được sau | Tải qua mạng | JS chạy |
|---|---|---|---|
| Máy tính, mạng nhanh, lần đầu | 1.917 ms (1.999) | 1.469 KB, 88 yêu cầu | 587 ms |
| Máy tính, mạng nhanh, lần sau | 1.610 ms (2.221) | 44 KB, 43 yêu cầu | 491 ms |
| Máy tính, 4G chậm, lần đầu | 7.568 ms (7.696) | 1.309 KB, 93 yêu cầu | 706 ms |
| Máy tính, 4G chậm, lần sau | 2.000 ms (2.241) | 43 KB, 45 yêu cầu | chưa ghi lại |
| Điện thoại 390px, 4G chậm, CPU chậm 4 lần, lần đầu | 12.198 ms (13.329) | 1.300 KB, 91 yêu cầu | 4.328 ms |
| Điện thoại 390px, 4G chậm, CPU chậm 4 lần, lần sau | 7.869 ms (10.034) | 45 KB, 47 yêu cầu | 3.780 ms |

- Chữ đầu tiên hiện (FCP) vẫn nhanh: 512 đến 1.680 ms. Cái chậm là từ lúc thấy trang tới lúc gõ được.
- Điện thoại, lần đầu: 21 tác vụ dài, tổng 5.084 ms phần vượt 50 ms. Lần sau: 17 tác vụ dài, 4.244 ms.
- Lần đầu tải gì (máy tính, 4G chậm): script 741 KB, các lần fetch 377 KB, CSS 98 KB, font 79 KB, ảnh 33 KB,
  trang 31 KB.
- Nặng nhất: gói khởi động 584 KB; `i18n/vi.json` 143 KB; `i18n/en.json` 138 KB (chỉ tải khi ngôn ngữ không phải
  tiếng Việt); `teams.js` 71 KB; force-graph 57 KB; `style.css` 46 KB; `console.css` 46 KB; `/brand-logo` 33 KB
  (bị gọi hai lần).

**Nguyên nhân gốc:**

- File nguồn có 123 thẻ script có `src`, tổng 3.571 KB; gói sau khi rút gọn là 2.122 KB. Lớn nhất (nén từng file):
  `console.js` 210 KB, `app.js` 113 KB, `sessions-ui.js` 51 KB, `workspace.js` 50 KB, `chat-render.js` 39 KB,
  `studio.js` 33 KB, `pet.js` 33 KB, `voice.js` 26 KB, `github-connect.js` 21 KB, `graph.js` 17 KB. Nhiều file
  trong đó chỉ phục vụ một trang (Studio, Workspace, GitHub, đồ thị, trình sửa file) nhưng mọi lần mở đều phải
  chạy. Khối nạp chậm ở `dashboard/index.html:1051` mới có 7 nhóm, 27 file.
- Khoảng 40 lần đọc API bắn ra ngay khi mở, kể cả khi chưa đăng nhập (tất cả trả 401), có trùng: `/settings` 3 lần,
  `/agents`, `/brains`, `/connect/health`, `/plan-limits` mỗi thứ 2 lần.
- `loadBrainStats` (`dashboard/app.js:4449`) tải trọn `/agents` (239 KB thô, 75 KB sau nén, kèm toàn bộ prompt),
  `/skills` (69 KB thô) và `/workflows` chỉ để hiện **ba con số đếm**.
- Lần mở đầu, các file của nhóm nạp chậm (`teams.js`, `conversations.js`, `chatbots.js`...) được tải ngay cùng
  lúc với gói chính, tranh đường truyền 1,6 Mbps.
- Từ điển giao diện dùng `cache: "no-cache"` (`dashboard/i18n/index.js:129`) nên lần mở nào cũng hỏi lại máy chủ.

### 3.3 Chuyển trang và dữ liệu (7 lần mỗi API, đo trong máy chủ)

Chỉ liệt kê những API trên 90 ms hoặc trả về nặng. Số sau là p95.

| API | Trung vị (p95) | Cỡ thô, sau nén | Nguyên nhân gốc |
|---|---|---|---|
| `/graph?orphans=1` | 896 ms (1.135) | 644 KB, 79 KB | `graph_builder._scan_root` (`graph_builder.py:118`) đi hết vault ở mỗi lần gọi; `graph_with_etag` (`:187`) quét xong mới tính ETag nên trúng cache vẫn tốn |
| `/conversations?limit=30` | 416 ms (793) | 42 KB, 10 KB | `conversations.danh_sach` (`conversations.py:914`), phần phụ của trang đầu và `hesitant_chats` (`chatbot_reply_policy_store.py:216`), đọc bot cho từng dòng |
| `/brains` | 302 ms (519) | 0,3 KB | `_list_brains_sync` (`main.py:9738`) đếm lại file .md của mọi brain bằng `_count_md` (`main.py:18004`) ở mỗi lần gọi. Đã có trần số file và đã chạy ngoài vòng lặp sự kiện (`tests/python/test_brains_dem.py`), chỉ thiếu việc nhớ kết quả |
| `/reminders` | 200 ms (242) | 99 KB, 16 KB | mỗi nhắc hẹn tra múi giờ một lần, mỗi lần stat `settings.json` (`reminders.py:589` `_view` tới `config.py:603`) |
| `/skills` | 176 ms (265) | 69 KB, 16 KB | `skill_router.list_skills` (`skill_router.py:338`) đọc lại 142 thư mục skill mỗi lần |
| `/channels/accounts` | 124 ms (153) | 16 KB, 4 KB | giải mã khoá và dò kết nối Zalo cho từng tài khoản |
| `/viec/all` | 95 ms (116) | 81 KB, 20 KB | cùng lỗi múi giờ như `/reminders` |
| `/teams` | 91 ms (125) | 8 KB, 3 KB | |
| `/agents?brain=` | 71 ms (223) | 239 KB, 75 KB | trả cả prompt; bản `prompt=0` là 26 ms và 17 KB thô |
| `/settings` | 62 ms (101) | 18 KB, 5 KB | hỏi danh sách model của Antigravity (`antigravity_cli.py:112`) |

Số ở bảng đo lúc tải 4 đến 6. Chạy lại cùng lệnh lúc tải 8,8 đến 9,5 thì mọi thứ chậm gấp 2 đến 3 lần nhưng thứ
tự không đổi: `/graph` 1.710 ms, `/brains` 839 ms, `/reminders` 595 ms, `/conversations` 477 ms, `/skills` 353 ms,
`/viec/all` 247 ms; mở cuộc chat dài nhất 70 ms. Tức là các API này ăn CPU thật, không phải chờ đĩa.

Những thứ đã nhanh, đo để xác nhận:

- Mở cuộc chat dài nhất (2.227 tin), lấy 30 tin cuối: 13 ms (29), 43 KB thô, 10 KB sau nén.
- Mở cuộc chat thường (6 tin): 11 ms. Danh sách chat `/sessions?limit=21`: 15 ms (30).
- Trang Nhiệm vụ: `/kanban` 22 ms, `/watch` 8 ms, `/incidents` 10 ms, `/my-tasks` 8 ms, `/loops/log` 7 ms. Mười lần
  đọc của trang đi cùng một đợt (`dashboard/tasks.js:557`), nên trang chờ bằng lần chậm nhất là `/reminders` 200 ms.
- Trang Tệp `/files/list`: 12 ms (17). `/inbox?limit=40`: 25 ms. `/notifications`: 16 ms. `/config`: 5 ms.
- Đồ thị chỉ tải khi màn chính lần đầu hiện ra (đã làm ngày 12/11/2026, `dashboard/app.js:3719`). Người mở
  thẳng vào Chat không trả 896 ms này.

### 3.4 Máy chủ

| Điểm đo | Số đo | Nguyên nhân gốc |
|---|---|---|
| `import main`, chạy từ mã nguồn | 20.352 ms (lớn nhất 24.501) | `Dockerfile:32` đặt `PYTHONDONTWRITEBYTECODE=1`, image không có file `.pyc` cho `server/` (534 module), `/app` chỉ đọc nên không bao giờ ghi được |
| `import main`, có bytecode | 7.247 ms (lớn nhất 11.543) | phần còn lại là chạy thân module |
| Biên dịch riêng `main.py` | 2.510 ms | file 35.931 dòng, 437 route |
| Module nặng nhất khi import | `main` 5.632 ms tự thân; `team_api` 1.739 ms; `fastapi` 1.618 ms; `claude_cli` 855 ms; `brain_seed_i18n` 826 ms; `improvement_trial_api` 611 ms; `chatbot_runtime` 595 ms | đều nạp ngay lúc khởi động dù có trang cả ngày không ai mở |
| `GET /health` trên bản đang chạy | n=120, trung vị 20 ms, p95 197 ms, lớn nhất 1.921 ms | máy bão hoà CPU; vòng lặp sự kiện bị chen |
| `GET /` trên bản đang chạy | n=30, trung vị 88 ms, p95 662 ms, lớn nhất 2.689 ms | như trên |
| RAM uvicorn | 559 đến 793 MB, 51 luồng | |
| Tiến trình con | mỗi `claude` 223 đến 258 MB (4 đến 5 cái); 3 đến 4 `google-ads-mcp` khoảng 156 MB mỗi cái; các MCP khác khoảng 100 MB mỗi cái | mỗi lượt chạy song song mở bộ MCP riêng |

Cỡ các kho SQLite: `conversations.db` 53,5 MB; `customer_conversations.sqlite3` 37,9 MB; `memory_index.db`
37,7 MB; `runtime.db` 36,1 MB; `usage_index.db` 34,9 MB. Các truy vấn chat đo được đều dưới 30 ms.

## 4. Đã có, không đề xuất lại

- Gộp script khởi động thành một gói (`server/static_bundle.py`), rút gọn lúc phục vụ (`server/tinh_gon.py`).
- Nén gzip cho file tĩnh và cho câu trả lời API, phần nặng nén ngoài vòng lặp sự kiện (`server/nen_phan_hoi.py`).
- Cache một năm theo dấu vân tay từng file, ETag và 304, đầu `Server-Timing`.
- Nạp chậm theo nhóm trang (`nap-cham.js`), màn chờ (`boot-splash.js`); xterm (`code-term.js:100`) và force-graph
  (`app.js:3693`) chỉ tải khi cần.
- Cache cuộc chat trong IndexedDB (`chat-cache.js`), mở chat chỉ lấy 30 tin cuối không kèm tool.
- `fetch-gop.js`: gộp lần đọc trùng đang bay, bản sao dùng tạm 10 phút, gộp nhiều lần đọc qua `POST /batch`.
- Trang Nhiệm vụ đọc song song một đợt; `/kanban` chạy ở luồng riêng.
- Hồ tiến trình ấm cho lượt chat của chủ, có trần RAM, hâm trước khi đang gõ (`server/warm_pool.py`).
- Danh sách tool của hub dùng bản cũ trong lúc làm mới.
- Ngân sách lời gọi chặn vòng lặp sự kiện (`tests/python/test_loop_blocking_budget.py`), ngân sách prompt
  (`tests/python/test_prompt_budget.py`).
- Chủ repo đã chốt **không cắt chữ trong prompt của lượt chat** (`2026-11-javis-nhe-token-spec.md` mục 0). Prompt
  hệ thống trung vị 57.698 ký tự được ghi nhận ở đây như số đo, không phải đề xuất cắt.

## 5. Hướng cải thiện, xếp theo lợi trên công

Công: S dưới nửa ngày, M một đến ba ngày, L hơn một tuần.

### Nhóm A. Sửa nhanh, gom trong một PR

**A1. Biên dịch sẵn bytecode trong image.**
- Lợi: `import main` từ 20.352 ms còn 7.247 ms, đã đo. Mỗi lần khởi động lại hay cập nhật bớt khoảng 13 giây
  dashboard không vào được. Image nặng thêm 30 MB.
- Công: S. Rủi ro: thấp.
- File: `Dockerfile` (thêm `python -m compileall -q server` sau bước chép mã).
- Đo lại: lệnh so sánh import ở mục 9.

**A2. `/brains` nhớ số đếm file .md.**
- Lợi: tối đa 302 ms mỗi lần gọi (p95 519 ms), API này bị gọi 2 lần lúc mở. Dự kiến còn dưới 20 ms.
- Công: S. Rủi ro: thấp, số đếm trễ tối đa một phút. Bộ nhớ: một con số cho mỗi brain.
- File: `server/main.py` (`_list_brains_sync`, `_count_md`), `tests/python/test_brains_dem.py`.
- Đo lại: `api_read_bench.py`, dòng `/brains`; `server/bench_hotpath.py` (đích sẵn có dưới 10 ms).

**A3. Tra múi giờ một lần cho cả yêu cầu, không phải cho từng nhắc hẹn.**
- Lợi: tối đa 200 ms ở `/reminders` và 95 ms ở `/viec/all`. Trang Nhiệm vụ chờ đúng bằng lần chậm nhất này.
- Công: S. Rủi ro: thấp.
- File: `server/reminders.py` (`_view`, `live_views`), `server/localefmt.py`.
- Đo lại: `api_read_bench.py`, nhóm "tasks page".

**A4. Ba con số đếm ở màn chính không tải trọn danh sách.**
- Lợi: bớt 70 KB sau nén và 46 ms cho `/agents` (đo: bản đầy đủ 75 KB sau nén, 71 ms; bản `prompt=0` 4 KB sau
  nén, 26 ms). Trên 4G chậm 1,6 Mbps, 70 KB bằng khoảng 0,35 giây đường truyền.
- Công: S. Rủi ro: thấp, vì hàm này chỉ dùng độ dài mảng.
- File: `dashboard/app.js` (`loadBrainStats`, dòng 4449).
- Đo lại: bench trình duyệt, cột "tải qua mạng".

**A5. Từ điển giao diện có khoá phiên bản như mọi file tĩnh khác.**
- Lợi: lần mở sau bớt 1 đến 2 lượt hỏi lại máy chủ (mỗi lượt một vòng 150 ms trên 4G chậm).
- Công: S. Rủi ro: thấp, cần giữ đường cập nhật chữ khi lên bản mới.
- File: `dashboard/i18n/index.js`, `server/main.py` (`_stamp_asset_keys`).
- Đo lại: bench trình duyệt, số yêu cầu lần mở sau.

**A6. `/brand-logo` chỉ tải một lần.**
- Lợi: 33 KB ở lần mở đầu. Công: S. Rủi ro: thấp.
- File: `dashboard/branding.js`, `dashboard/pet.js`.

**A7. Ghi lý do nguội vào sự kiện `engine.first_output`.**
- Lợi: không bớt mili giây nào ngay, nhưng là điều kiện để làm B1 đúng chỗ. Hiện 68% lượt nguội mà không biết
  vì sao.
- Công: S. Rủi ro: thấp. Không đụng `server/claude_sdk_engine.py`.
- File: `server/warm_pool.py`, `server/main.py` (chỗ ghi sự kiện, quanh dòng 21285).
- Đo lại: `chat_turn_wait.py` thêm bảng theo lý do.

### Nhóm B. Vừa

**B1. Nâng tỉ lệ lượt ấm.**
- Lợi: mỗi lượt chuyển từ nguội sang ấm bớt 6,6 giây ở trung vị (12,2 xuống 5,6). Hiện 470 trên 722 lượt Claude
  là nguội.
- Hướng: sau khi A7 cho biết lý do, chọn trong các cách không làm RAM tăng theo số hội thoại: một chỗ ấm dự phòng
  cho "cuộc chat mới kế tiếp" của brain đang mở, hâm lại chỗ đó ngay sau khi máy chủ khởi động xong, và nới thời
  gian nghỉ nếu lý do chính là quá 300 giây. Tất cả nằm trong trần RAM sẵn có của hồ.
- Công: M. Rủi ro: vừa, vì mỗi chỗ ấm giữ 300 MB trên máy 8 GB.
- File: `server/warm_pool.py`, `server/claude_warm.py`. Không sửa `server/claude_sdk_engine.py`.
- Đo lại: `chat_turn_wait.py`, tỉ lệ ấm và p50 nguội.

**B2. Đưa các module chỉ phục vụ một trang ra khỏi gói khởi động.**
- Lợi: các ứng viên `workspace.js`, `studio.js`, `voice.js`, `github-connect.js`, `graph.js`, `file-editor.js`,
  `dictate.js`, `editor-cmds.js`, `improvement-candidates.js`, `coding.js`, `dataview.js` cộng lại 693 KB
  mã nguồn trong 3.571 KB của gói, khoảng 19% (216 KB nếu nén từng file). Số mili giây bớt được trên điện thoại chưa đo được (cần sửa mới đo), trần
  là 3.780 ms thời gian chạy script của lần mở sau.
- Cách làm: dùng đúng cơ chế nhóm nạp chậm đang có ở `index.html:1051`, không cần bundler hay framework mới.
- Công: M. Rủi ro: vừa, vì file trong gói gọi hàm của nhau lúc khởi động; mỗi lần chuyển một nhóm, có test.
- File: `dashboard/index.html`, `dashboard/nap-cham.js`, `tests/python/test_static_bundle.py`.
- Đo lại: bench trình duyệt, trường hợp điện thoại, cột "gõ được sau" và "JS chạy".

**B3. `/graph` nhớ kết quả quét, làm mới theo tín hiệu của bộ theo dõi file sẵn có.**
- Lợi: tối đa 896 ms mỗi lần mở màn chính và mỗi lần đổi brain.
- Công: M. Rủi ro: vừa (đồ thị cũ nếu bỏ sót một thay đổi). Bộ nhớ tăng theo số brain đang mở, không theo số
  hội thoại.
- File: `server/graph_builder.py`, bộ theo dõi đồ thị trong `server/main.py`.
- Đo lại: `api_read_bench.py`, dòng `/graph`.

**B4. Danh sách skill nhớ theo dấu thời gian thư mục.**
- Lợi: tối đa 176 ms ở `/skills`, và `list_skills` chiếm 84 ms trong 288 ms của `build_system_prompt` ở mỗi lượt
  chat.
- Công: M. Rủi ro: vừa, skill vừa tạo từ chat phải hiện ngay. Bộ nhớ: một danh sách cho mỗi brain.
- File: `server/skill_router.py`.
- Đo lại: `server/bench_hotpath.py` (đích sẵn có dưới 60 ms).

**B5. `/conversations` trang đầu.**
- Lợi: tối đa 416 ms (p95 793 ms) mỗi lần vào trang Hội thoại.
- Công: M. Rủi ro: vừa.
- File: `server/conversations.py`, `server/chatbot_reply_policy_store.py`.
- Đo lại: `api_read_bench.py`, nhóm "customer chats and chatbot"; `tests/python/test_inbox_speed.py`.

**B6. Lần mở đầu không tải nhóm nạp chậm cùng lúc với gói chính, và không đọc dữ liệu khi chưa đăng nhập.**
- Lợi: 377 KB fetch trong 1.309 KB của lần mở đầu trên 4G chậm đang tranh đường truyền với gói chính. Số mili
  giây chưa tách được.
- Công: M. Rủi ro: thấp.
- File: `dashboard/freshness.js`, `dashboard/nap-cham.js`, `dashboard/app.js`.

### Nhóm C. Đổi kiến trúc

**C1. Tách việc nền nặng khỏi CPU của dashboard.**
- Bằng chứng: lúc hai việc xử lý ảnh chiếm 164% CPU, `/health` p95 197 ms, lớn nhất 1.921 ms; 4 lượt chạy cùng
  lúc đẩy p95 chữ đầu từ 32,4 lên 65,3 giây.
- Hướng: chạy tiến trình con của việc nền và lệnh shell dài ở mức ưu tiên thấp hơn máy chủ, hoặc giới hạn số việc
  nặng chạy cùng lúc theo số nhân.
- Công: L. Rủi ro: vừa, việc nền chậm đi khi máy bận.

**C2. Nạp trễ các phân hệ ít dùng lúc khởi động.**
- Bằng chứng: `team_api` 1.739 ms, `brain_seed_i18n` 826 ms, `improvement_trial_api` 611 ms, `chatbot_runtime`
  595 ms (đo khi chạy từ mã nguồn, sẽ nhỏ hơn sau A1).
- Công: L. Rủi ro: cao, `main.py` 35.931 dòng đăng ký 437 route ở mức module. Chỉ nên làm sau A1 và đo lại.

**C3. Chia nhỏ `console.js` (210 KB sau nén, lớn nhất gói).**
- Công: L. Rủi ro: cao. Chỉ làm nếu sau B2 điện thoại vẫn trên ngưỡng ở mục 7.

## 6. Ba việc nên làm đầu tiên

1. **Một PR sửa nhanh gồm A1, A2, A3, A4.** Rủi ro thấp, lợi đã đo hoặc có trần rõ: bớt 13 giây mỗi lần khởi
   động, tối đa 302 ms và 200 ms ở hai API chậm nhất của màn mở và trang Nhiệm vụ, bớt 70 KB mỗi lần mở.
2. **A7 rồi B1: ghi lý do nguội, sau đó nâng tỉ lệ ấm.** Đây là chỗ chờ lớn nhất tính bằng giây (12,2 so với
   5,6 giây) và xảy ra ở 68% lượt. Làm B1 mà chưa có A7 là đoán.
3. **B2: rút gói khởi động.** Là thứ duy nhất chạm được vào 7,9 giây của lần mở sau trên điện thoại, vì lúc đó
   mạng chỉ còn 45 KB.

Ngoài mã: việc xử lý ảnh chạy nền lúc đo đang chiếm gần trọn 2 nhân và 2,3 GB RAM. Khi nó xong, nên đo lại mục
3.4 để có số "máy rảnh".

## 7. Ngưỡng nên giữ lâu dài và test canh

Ngưỡng là đích đề xuất, đặt sát số đo hiện tại hoặc số dự kiến sau khi sửa.

| Thứ cần giữ | Ngưỡng | Canh bằng |
|---|---|---|
| Gói khởi động sau nén | không lớn hơn 584 KB hôm nay, hạ dần sau B2 | thêm trần vào `tests/python/test_static_bundle.py`, kiểu chỉ được giảm như `loop_blocking_budget.json` |
| Image có bytecode cho `server/` | có | test mới đọc `Dockerfile`, đỏ nếu thiếu bước `compileall` |
| `import main` có bytecode | dưới 8 giây trên máy 2 nhân đang tải | `server/bench_hotpath.py` (đích 1.400 ms hiện có không đạt được trên máy này, nên sửa đích theo số đo) |
| `/brains`, `/reminders`, `/skills` gọi lần hai | không quét lại đĩa | test mới đếm số lần gọi `os.scandir` hoặc `stat`, không đo bằng đồng hồ để CI không chập chờn |
| Lời gọi chặn vòng lặp sự kiện | không tăng (`main.py` đang là 100) | `tests/python/test_loop_blocking_budget.py`, đã có |
| Prompt cố định mỗi lượt | theo trần đang có | `tests/python/test_prompt_budget.py`, đã có |
| Mở chat lấy 30 tin, không kèm tool | giữ nguyên | test mới cho `_urlPhien` (`dashboard/app.js:2612`) |
| Trang Hội thoại | chỉ mục và đọc song song | `tests/python/test_inbox_speed.py`, đã có |
| Chữ đầu của lượt chat | tỉ lệ ấm trên 50%, p50 ấm dưới 5 giây, p50 nguội dưới 10 giây | không canh được trong CI; chạy `chat_turn_wait.py --days 7` trước mỗi đợt tối ưu |
| Mở lại trên điện thoại 4G chậm | dưới 4 giây tới lúc gõ được | `dashboard_load_bench.mjs`, chạy tay trước khi phát hành thay đổi lớn ở dashboard |

## 8. Chưa đo được

- **Thời gian tới lúc ô chat gõ được, và số lần gọi trùng sau khi đăng nhập:** chưa đo được, vì không dùng phiên
  đăng nhập nào trên bản thật. Chạy lại với `JAVIS_BENCH_COOKIE`.
- **Thời gian API qua mạng trên bản đang chạy:** chưa đo được, cùng lý do. Số ở mục 3.3 là thời gian trong máy chủ.
- **Dòng `[turn timing]`:** chưa đo được, vì nó ghi ra stderr của container, không đọc được từ bên trong.
- **Tách phần recall, ghi SQLite, nối hub MCP bên trong một lượt:** chưa đo được, vì sự kiện chỉ ghi một mốc
  `engine.first_output`. Có được là mốc trước `_do_turn` (p50 132 ms) và `build_system_prompt` (288 ms).
- **Lý do từng lượt nguội:** chưa đo được, sự kiện không ghi (xem A7).
- **`/usage/summary` và `/usage/insights`:** chưa đo được, lần quét lại chạy hơn 45 giây và bị dừng.
- **Nhật ký truy vấn SQLite chậm:** chưa đo được, máy chủ không ghi thời gian từng truy vấn.
- **RAM và CPU lúc máy rảnh thật sự:** chưa đo được, suốt buổi đo máy luôn có việc nền chạy.
- **Trang Chatbot, Đồ thị, Tệp trong trình duyệt:** chưa đo được ở trình duyệt (cần đăng nhập); đã đo API phía sau.
- **`tools/team_perf_bench.py`:** không dùng, vì nó chạy trên dữ liệu giả trong thư mục tạm, không phải dữ liệu
  thật. **`tools/token_bench.py`:** không chạy lại; số prompt lấy từ sự kiện `payload.observed`.
- **`tests/test_timings.json`:** là tốc độ của bộ test (946 file, 4.453 giây), không phải chỗ người dùng chờ.

## 9. Lệnh đã chạy

Tất cả chạy từ gốc repo, chỉ đọc.

```
# Mở dashboard, trình duyệt thật, 5 lần mỗi trường hợp
PLAYWRIGHT_CORE=<thư mục playwright-core> CHROME_PATH=<đường dẫn chrome> RUNS=5 \
  node docs/dev/2026-11-ra-soat-toc-do/dashboard_load_bench.mjs

# API đọc, 7 lần mỗi API, trong một tiến trình riêng
python docs/dev/2026-11-ra-soat-toc-do/api_read_bench.py

# Lượt chat, từ lịch sử chạy thật
python docs/dev/2026-11-ra-soat-toc-do/chat_turn_wait.py
python docs/dev/2026-11-ra-soat-toc-do/chat_turn_wait.py --days 7

# Đường nóng phía máy chủ
cd server && python bench_hotpath.py

# Khởi động: module nào nặng
cd server && python -X importtime -c "import main" 2> importtime.txt

# Khởi động: từ mã nguồn so với có bytecode (bytecode để ở thư mục tạm)
cd server && PYTHONPYCACHEPREFIX=/tmp/pyc PYTHONDONTWRITEBYTECODE= python -m compileall -q .
cd server && PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/nonexistent python -c "import time;t=time.perf_counter();import main;print(round((time.perf_counter()-t)*1000))"
cd server && env -u PYTHONDONTWRITEBYTECODE PYTHONPYCACHEPREFIX=/tmp/pyc python -c "import time;t=time.perf_counter();import main;print(round((time.perf_counter()-t)*1000))"

# Bản đang chạy có đáp nhanh không (không cần đăng nhập)
for i in $(seq 120); do curl -s -o /dev/null -w "%{time_total}\n" http://127.0.0.1:7777/health; sleep 0.3; done

# Trang thật phục vụ mấy thẻ script, gói nặng bao nhiêu
curl -s --compressed http://127.0.0.1:7777/ | grep -o '<script[^>]*src="[^"]*"'
```

CPU và RAM theo tiến trình đọc từ `/proc/<pid>/stat` và `/proc/<pid>/status` hai lần cách nhau 20 giây (máy
không có `ps`, `top`).

## 10. Chỗ để script đo

Ba script nằm ở `docs/dev/2026-11-ra-soat-toc-do/` chứ không ở `tools/`. Lý do: theo `docs/quy-uoc-dev.md`, file
trong `tools/` tính là mã, PR phải kèm một mảnh `changelog.d/` và sẽ ra một bản phát hành mới, trái với yêu cầu
"không đổi VERSION hay CHANGELOG" của lượt này. PR sửa lỗi đầu tiên (vốn đã có mảnh changelog) có thể chuyển
chúng sang `tools/`.

- `dashboard_load_bench.mjs`: mở dashboard bằng Playwright, máy tính và điện thoại 390px, có giả lập 4G chậm.
- `api_read_bench.py`: đo các lần đọc API trên dữ liệu thật, không mở cổng, không đăng nhập.
- `chat_turn_wait.py`: thời gian chờ chữ đầu của lượt chat từ `runtime.db`, mở ở chế độ chỉ đọc.

## 11. Đã làm ba việc ở mục 6 và số đo sau khi sửa (23/11/2026)

Mã ở cùng PR với mục này. Số "trước" và "sau" dưới đây đo cùng lúc, cùng máy, cùng lệnh, để không lẫn với tải
máy (tải lúc đo lại thấp hơn lúc rà soát, nên số "trước" ở đây cũng thấp hơn số ở mục 3).

### 11.1 Việc 1: A1 đến A4

| Chỗ sửa | Trước | Sau | Cách đo |
|---|---|---|---|
| `/brains` | 253 ms (496) | 5,5 ms (6,6) | `api_read_bench.py`, 7 lần, tải 2,5 đến 3 |
| `/reminders` | 120 ms (128) | 25 ms (29) | như trên |
| `/viec/all` | 54 ms (67) | 34 ms (38) | như trên |
| Ba con số đếm ở màn chính | 239 KB thô, 75 KB sau nén | 17 KB thô, 4,4 KB sau nén | cỡ trả về của `/agents` |
| Khởi động máy chủ | 20,4 giây | 7,2 giây | số của mục 3.4, CHƯA đo lại |

Đối chứng không sửa trong cùng hai lần chạy: `/skills` 66 và 68 ms, `/teams` 39 và 43 ms. Tức là chênh lệch ở
bảng là do mã, không do tải.

- **A1.** `Dockerfile` chạy `python -m compileall -q server` lúc dựng image. Không dựng được image trong máy này,
  nên con số 13 giây vẫn là số của mục 3.4 (đo bằng cách bật tắt bytecode trên cùng mã). Phải xem lại ở lần
  khởi động đầu sau khi cập nhật: dòng `import main` trong log.
- **A2.** `/brains` nhớ số đếm ghi chú của mỗi brain 60 giây (`_brain_note_count` trong `server/main.py`). Bộ nhớ
  có một mục cho mỗi brain và bỏ mục của brain đã xoá, không lớn theo số hội thoại. Số đếm có thể trễ tối đa
  60 giây sau khi thêm hay xoá ghi chú.
- **A3.** `/reminders` và `/viec/all` tra múi giờ một lần cho cả danh sách (`server/reminders.py`).
- **A4.** `loadBrainStats` gọi `/agents?prompt=0` (`dashboard/app.js`).

### 11.2 Việc 2: A7 rồi B1

**A7, đã ghi lý do.** Sự kiện `engine.first_output` có thêm ba trường: `cold` (lý do nguội), `cold_parts` (phần
cấu hình nào đổi, khi lý do là `config_changed`) và `opened_ahead` (lượt này dùng tiến trình mở sẵn cho luồng
mới). Các giá trị hay gặp của `cold`: `new_chat`, `thread_rotated`, `thread_lost`, `idle_expired`,
`config_changed`, `evicted`, `process_died`, `busy`, `warm_start_failed`, và nhóm không bao giờ dùng tiến trình ấm
(`not_owner_chat`, `gated_engine`, `trial_profile`, `engine_not_sdk`, `pool_off`). Danh sách đủ nằm ở
`warm_pool.take`, `claude_warm.ineligible_reason` và `main._cold_reason`. `chat_turn_wait.py` in thêm bảng theo lý
do. Sự kiện cũ không có trường này, nên bảng chỉ đầy dần từ sau khi cập nhật.

Vì sự kiện cũ không ghi lý do, lý do của 14 ngày qua được dựng lại từ dữ liệu sẵn có (thứ tự lượt trong từng
cuộc, khoảng cách giữa hai lượt, lượt nào bị xoay luồng) để B1 không phải đoán. Trên 724 lượt Claude:

| Lý do | Tỉ lệ |
|---|---|
| Vừa xoay luồng ở chính lượt này | 38,3% |
| Ấm | 34,9% |
| Để yên quá 300 giây | 12,6% |
| Lượt đầu của cuộc | 9,4% |
| Còn lại | 4,8% |

**B1, đã sửa nguồn lớn nhất.** Lượt bị xoay luồng trước đây không bao giờ tìm trong kho tiến trình ấm vì nó không
có phiên để nối. Bây giờ ngay sau khi lưu một lượt, nếu `compaction.next_turn_rotates` thấy lượt kế sẽ xoay,
Javis đóng tiến trình cũ và mở sẵn một tiến trình trên luồng mới (`claude_warm.prepare_new_thread`,
`warm_pool.swap_recipe`). Đóng trước rồi mới mở, nên vẫn là một tiến trình cho mỗi cuộc, RAM không tăng.

Giới hạn, nói thẳng:

- Mới kiểm bằng tiến trình `claude` giả trong test (`tests/python/test_warm_new_thread_turn.py`), không mở phiên
  thật vì sẽ tiêu gói của chủ máy. Hiệu quả thật phải đọc từ `engine.first_output` sau khi cập nhật: lượt có
  `opened_ahead` phải gần 5,6 giây chứ không phải 12,2 giây.
- Trên dữ liệu cũ, 194 trong 276 lượt xoay luồng (70%) có system prompt khác lượt trước. Tiến trình mở sẵn vẫn
  phục vụ các lượt này, đúng luật của mọi lượt ấm (ngữ cảnh của lượt đi trong tin nhắn đầu, #1329). Riêng lượt
  có tin nhắn không phải văn bản thuần (kèm ảnh) thì ngữ cảnh nằm trong system prompt, nên lượt đó vẫn chạy
  nguội và ghi `cold_parts: ["new_thread_prompt"]`.
- Đoán sai (lượt kế hoá ra vẫn nối luồng cũ) tốn đúng một lần khởi động nguội, và sự kiện ghi `resume` trong
  `cold_parts`.
- Tắt bằng `JAVIS_WARM_NEW_THREAD=0`.

**Việc cần chủ máy quyết, chưa đổi.** Javis xoay luồng Claude theo tổng token của cả lượt. Số đo thật: cỡ
luồng thật (đầu vào của lần gọi cuối) có trung vị 159.889 token, lớn nhất 175.388, trong khi 24% lượt có tổng
cả lượt trên 1 triệu token vì một lượt gọi model nhiều lần. Đổi Claude sang cách đo theo lần gọi cuối như Codex
đã làm (#999) sẽ bớt hẳn số lần xoay, tức bớt chính nguồn 38% ở trên, nhưng nó đổi lúc gom gọn hội thoại và chi
phí token, nên không gộp vào PR sửa tốc độ.

Hai nguồn nguội còn lại chưa đụng: để yên quá 300 giây (12,6%; kéo dài thời gian giữ thì tốn RAM theo số cuộc
đang mở, trái ràng buộc của lượt rà soát) và lượt đầu của cuộc (9,4%; hướng "một chỗ ấm dự phòng cho cuộc chat
mới kế tiếp" ở B1 của mục 5 vẫn còn nguyên, chưa làm).

### 11.3 Việc 3: B2

Chuyển sang nhóm nạp chậm sẵn có (`<script id="javis-lazy">` trong `dashboard/index.html`), không thêm bundler:

- Nhóm `congviec`: `studio.js`, `workspace.js`, `improvement-candidates.js`, `improvement-experiments.js`,
  `improvement-candidates.css`.
- Nhóm `packs`: `messenger-connect.js`.

Hai thứ `studio.js` gắn lúc mở app (nút Studio và `window.openStudio`) chuyển sang `app.js`. Mọi chỗ ở trang khác
gọi vào các file này (lệnh `/agent` trong chat chính, link cộng sự, thông báo, menu linh vật, link cài đặt
Resonance, gợi ý Messenger ở trang Hội thoại) đều nạp nhóm trước rồi mới gọi.

| Gói khởi động | Trước | Sau | Bớt |
|---|---|---|---|
| File nguồn nạp lúc mở | 3.572 KB, 123 file | 3.208 KB, 118 file | 364 KB |
| Gói máy chủ phục vụ, mã phải chạy | 2.122 KB | 1.885 KB | 237 KB (11,2%) |
| Gói máy chủ phục vụ, sau nén | 584 KB | 522 KB | 62,5 KB (10,7%) |

**Mili giây trên điện thoại: chưa thấy lợi vượt khỏi nhiễu.** Đo bằng `dashboard_load_bench.mjs` trên hai máy chủ
thử (mã trước và mã sau, dữ liệu tạm, dừng ở màn đăng nhập), ba vòng xen kẽ, mỗi vòng 3 lần, điện thoại 390px,
4G chậm, CPU chậm 4 lần. Trung vị từng vòng:

| Vòng (tải máy) | Lần đầu, trước | Lần đầu, sau | Lần sau, trước | Lần sau, sau |
|---|---|---|---|---|
| 1 (4,7) | 7.956 ms | 9.566 ms | 3.426 ms | 3.533 ms |
| 2 (4,6 và 4,9) | 8.389 ms | 7.493 ms | 3.749 ms | 2.995 ms |
| 3 (3,3 và 2,8) | 8.008 ms | 8.045 ms | 2.661 ms | 3.191 ms |
| Trung vị ba vòng | 8.008 ms | 8.045 ms | 3.426 ms | 3.191 ms |

Thời gian chạy script của lần đầu: trước 1.530, 2.034, 1.362 ms; sau 2.663, 1.272, 1.935 ms. Dữ liệu tải qua
mạng ở lần đầu: trước trung bình 1.325 KB, sau 1.262 KB (bớt 63 KB, khớp với gói sau nén).

Đọc bảng này cho đúng:

- Chênh lệch giữa các vòng của cùng một bản (1.600 đến 2.000 ms) lớn hơn nhiều so với lợi mong đợi từ việc bớt
  11% mã. Máy 2 nhân đang chạy việc khác, nên phép đo này không tách nổi vài trăm mili giây.
- Thứ chắc chắn đo được là số byte: 237 KB mã không còn phải phân tích và chạy lúc mở, 62,5 KB không còn phải
  tải trước màn đầu.
- Số ở đây thấp hơn mục 3.2 (12,2 và 7,9 giây) vì máy chủ thử gần như trống và dừng ở màn đăng nhập. Chỉ so
  trước với sau trong cùng bảng, không so với mục 3.2.
- Muốn có số mili giây tin được: đo lại trên bản thật lúc máy rảnh, hoặc trên điện thoại thật.

Để lại trong gói khởi động có chủ ý, vì màn chat dùng ngay lúc mở: `github-connect.js`, `file-editor.js`,
`graph.js`, `coding.js`, `voice.js`, `dictate.js`, `dataview.js`, `editor-cmds.js`, `pet.js`. Muốn rút tiếp các
file này phải tách phần màn chat dùng ra khỏi phần chỉ một trang dùng, là việc lớn hơn một lần chuyển nhóm.

Đã kiểm trong trình duyệt thật trên máy chủ thử: lúc trang sẵn sàng, `JavisWorkspace`, `JavisStudio` và
`JavisMessenger` chưa nạp, `window.openStudio` vẫn gọi được; mở trang Cộng sự, trang Skills và thẻ Messenger ở
trang Kết nối đều vẽ đúng, không lỗi trang; gõ lệnh `/agent` hai lần trong lúc mã còn đang tải thì chỉ mở cộng
sự đúng một lần.

### 11.4 Test canh

- `tests/python/test_image_bytecode.py`: Dockerfile còn biên dịch sẵn `server`.
- `tests/python/test_brains_dem.py` (mục 6): `/brains` không đếm lại trong 60 giây, và bỏ mục của brain đã xoá.
- `tests/python/test_reminders_list_timezone_once.py`: một lần tra múi giờ cho cả danh sách.
- `tests/js/test_brain_stats_light_list.js`: ba con số đếm dùng `prompt=0`.
- `tests/python/test_warm_cold_reason.py`, `tests/python/test_warm_new_thread_turn.py`: lý do nguội và tiến trình
  mở sẵn cho luồng mới.
- `tests/js/test_startup_bundle_single_page.js`: các file đã chuyển không quay lại gói khởi động, mọi chỗ gọi
  đều nạp nhóm trước, và trần 3.260 KB cho mã nguồn nạp lúc mở (chỉ được giảm).

Hai test có sẵn phải đổi cho khớp vị trí mới của mã, không nới: `tests/js/test_hieu_nang_gd2.js` (trước canh
`studio.js` nạp lúc mở để giữ nút Studio; nay canh `app.js` nạp lúc mở, giữ `window.openStudio` và nút đó) và
`tests/js/test_studio_chon_model_agent.js` (thứ tự nạp đọc từ nhóm nạp chậm thay vì từ thẻ script).
