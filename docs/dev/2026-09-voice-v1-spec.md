# Voice V1 - spec triển khai (VOICE_V1_IMPLEMENTATION_SPEC)

> Viết 2026-09-14 trên nền v0.55.66, sau khi có bản đồ hiện trạng
> `2026-09-voice-v1-ban-do-hien-trang.md`. Ba tài liệu gốc của chủ dự án
> (`01_JAVIS_OS_VISION.md`, `02_JAVIS_OS_ARCHITECTURE.md`, `03_JAVIS_OS_ROADMAP.md`) là đầu bài.
> Chủ dự án chốt 2026-09-14: KHÔNG phụ thuộc OpenAI Realtime, làm pipeline riêng của Javis dù
> chưa mượt bằng; đóng và mở app làm ngay không hỏi lại; làm luôn cả điều khiển UI; giữ Web
> Speech làm tai; triển khai từ đầu đến cuối trong một đợt.

## 1. Quyết định cốt lõi

**Không kéo LiveKit vào làm dependency, chỉ mượn thiết kế.** `livekit/livekit` là SFU WebRTC
cho nhiều người; một người nói với một server thì WebSocket và HTTP hiện có là đủ. Cái đáng
mượn nằm ở `livekit/agents`: state machine hội thoại, endpointing hai ngưỡng, chen ngang có
tạm dừng và hoàn nguyên, chỉ lưu phần đã nghe thấy, tool chạy lâu thả model nói tiếp. Toàn bộ
mục 9 của bản đồ hiện trạng là danh sách mượn, kèm số dòng nguồn.

**"Realtime của Javis" = tai Web Speech + não là engine đang chọn + miệng là TTS stream.**
Không có mô hình nói thẳng. Độ trễ được bù bằng bốn thứ rẻ: TTS trả byte ngay khi Edge sinh
ra (streaming HTTP thay vì gom cả câu), câu đầu tách riêng (đã có), chen ngang tạm dừng thay vì
giết, và orb báo đúng trạng thái để người dùng không tưởng máy treo.

**Voice là interface, không sở hữu vòng đời việc.** Voice gửi tin vào đúng khung chat đang
mở; việc nền vẫn qua `javis_task` và báo về bằng frame `push` như hôm nay. Đợt này chỉ thêm
một luật: tin nền chỉ được ĐỌC khi người dùng không đang nói.

**Điều khiển UI và app đi bằng TOOL, không bằng khối bình luận trong câu trả lời.** Lý do:
tool có kết quả trả về ngay trong lượt (dashboard xác nhận đã mở hay báo lỗi), đi qua hub nên
mọi bộ não gọi được như nhau, và tôn trọng ba mức quyền bằng code. Khối `JAVIS_UI` trong câu
trả lời đã cân nhắc và bỏ: server đang lột mọi khối `JAVIS_*` trước khi lưu, không có đường
báo kết quả về, và Telegram sẽ nhìn thấy rác.

**Điều khiển app máy tính là plugin bundled, không phải Desktop Agent riêng.** Roadmap xếp
Desktop Agent ở Phase 5 dưới dạng dịch vụ cục bộ tách rời. Trên máy chủ dự án, Javis ĐANG
chạy ngay trên máy Windows của họ (deploy_mode `windows`), nên một plugin Python 2 file làm
được 80% giá trị với 5% chi phí. Khi Javis chạy trong Docker trên VPS, plugin tự chặn và nói
rõ lý do; Desktop Agent thật để sau, khi cần điều khiển máy KHÁC máy chạy Javis.

## 2. Kiến trúc đợt này

```text
Trình duyệt                                   Server FastAPI
--------------------------------------------  ------------------------------------------
voice.js        tai (Web Speech) + miệng      GET /tts            stream byte Edge ngay
                (hàng đợi audio)              WS /ws              thêm khung ui_action ->
voice-turn.js   ĐẠO DIỄN: state machine,                          <- ui_result
                endpointing, cụm từ, chen ngang
ui-context.js   khối [NGỮ CẢNH GIAO DIỆN]     channel_context.py  dặn model có javis_ui,
                (trang, đoạn chọn, ngắt lời)                      javis_app_*, hiểu khối ngữ cảnh
ui-actions.js   nhận ui_action, kiểm, chạy,   ui_bridge.py        cầu tool -> dashboard, chờ ack
                trả ui_result                 plugins/javis-ui    tool javis_ui
app.js          nối orb, WS, gửi tin          plugins/desktop-apps tool javis_app_list/open/close
```

Mọi thứ mới đứng SAU ranh giới có sẵn: `/ws` chỉ thêm loại frame, hub chỉ thêm plugin, prompt
chỉ thêm vài dòng ở khối kênh web.

## 3. Đạo diễn hội thoại: `dashboard/voice-turn.js`

Module thuần, không đụng DOM, `require()` được dưới node để test. Xuất `window.JavisVoiceTurn`.

### 3.1 Trạng thái

`idle | listening | user_speaking | waiting_for_user | processing | speaking | interrupted |
reconnecting | error`. Cờ phụ, không phải trạng thái: `background` (số việc nền đang chạy),
`slow` (mạng chậm, đo từ thời gian tải khúc TTS).

### 3.2 Đầu vào và hành động

Mỗi hàm đầu vào trả về một MẢNG hành động để lớp I/O thực hiện; đạo diễn không gọi thẳng
recognition hay audio.

| Đầu vào | Từ đâu | Hành động có thể trả |
|---|---|---|
| `micOn()` / `micOff()` | app.js | `state` |
| `interim(text)` | voice.js onresult | `arm_endpoint {ms}`, `state` |
| `endpoint(text)` | đồng hồ im lặng nổ | `commit {text}`, `hold`, `stop_tts`, `stop_turn`, `state` |
| `turnStart()` / `turnDone()` | app.js sendMessage / frame turn_done | `state`, `flush_deferred` |
| `ttsStart()` / `ttsEnd()` | voice.js | `state` |
| `bargeStart()` | bộ rình RMS | `pause_tts`, `listen`, `state` |
| `bargeText(text)` | interim đầu tiên sau bargeStart | `stop_tts`, `state` |
| `bargeTimeout()` | 2000 ms không có chữ | `resume_tts`, `abort_listen`, `state` |
| `toolCall(name)` | frame tool_call | `state {tool}` |
| `wsDown()` / `wsUp()` | app.js connect | `state` |
| `waitTimeout()` | 90 s trong waiting_for_user | `state` |

### 3.3 Endpointing hai ngưỡng (mượn `voice/turn.py`)

- `minDelay` 800 ms (Web Speech giao chữ chậm hơn VAD nên nới từ 500 của LiveKit), `maxDelay`
  2200 ms. Người dùng chỉnh `minDelay` ở Cài đặt nhanh: Nhanh 500 / Vừa 800 / Chậm 1200.
- Mỗi `interim` tính lại: `looksUnfinished(text) ? maxDelay : minDelay`. Câu "chưa xong" =
  kết thúc bằng liên từ hoặc giới từ (vi: và, nhưng, thì, là, với, rồi, để, mà, hoặc, hay,
  nếu, vì, còn, cho, của, về, như, khi, nên, từ, đến, tới; en: and, but, then, so, with, to,
  the, a, of, or, if, because, that, when, for) hoặc bằng dấu phẩy. Không có mô hình EOT vì
  LiveKit cũng không có tiếng Việt trong bảng ngưỡng.
- Một đồng hồ duy nhất, interim mới thì huỷ và đặt lại ("bounce"). Không bao giờ commit chuỗi
  rỗng.

### 3.4 Luật cụm từ (chạy cục bộ, không gọi AI)

Chuẩn hoá: thường hoá, bỏ dấu câu, bỏ "javis"/"javis ơi" ở đầu, bỏ tiểu từ đuôi (nhé, nha,
đã, đi, chút, xíu, tí, nào, ạ, với, please). Chuỗi còn lại phải KHỚP ĐÚNG một cụm; câu dài hơn
("khoan, mở Chrome") là tin bình thường.

- CHỜ: khoan, khoan đã, đợi, đợi chút, đợi đã, đợi mình, đợi anh, đợi em, từ từ, chờ chút,
  chờ tí, chờ xíu, để mình nghĩ, để anh nghĩ, để em nghĩ, để tôi nghĩ, chưa xong; wait, hold on,
  hang on, one sec, one second, give me a second, let me think, just a moment.
  Hiệu ứng: KHÔNG gửi, sang `waiting_for_user`, orb "ĐANG CHỜ BẠN", mic vẫn mở, hết 90 giây thì
  về `listening`. Nếu Javis đang đọc thì dừng đọc luôn.
- DỪNG: thôi, dừng, dừng lại, im, im đi, đủ rồi, ngừng, thôi đủ rồi; stop, enough, never mind,
  cancel. Hiệu ứng: đang đọc thì dừng đọc; đang xử lý thì bấm hộ nút Dừng lượt; không gửi.

### 3.5 Chen ngang có tạm dừng (mượn `InterruptionOptions`)

- Bộ rình RMS giữ nguyên cách đo, nhưng cần 5 nhịp 100 ms liên tiếp (500 ms, bằng
  `min_duration` của LiveKit) thay vì 3.
- Đủ 500 ms: TẠM DỪNG audio (`audio.pause()`, giữ nguyên vị trí), mở recognition, orb "TẠM
  DỪNG, ĐANG NGHE BẠN".
- Trong 2000 ms có interim có chữ: dừng thật, sang `user_speaking`, ghi nhớ PHẦN ĐÃ ĐỌC (các
  khúc đã phát xong cộng phần khúc dở theo tỉ lệ `currentTime / duration`, cắt ở ranh giới
  từ). Không có chữ: phát tiếp từ chỗ dừng, đóng recognition, quay về `speaking` (chen ngang
  giả: tiếng ho, tiếng ngoài).
- Phần đã đọc đi vào khối `[NGỮ CẢNH GIAO DIỆN ...]` của tin kế tiếp (mục 5) để model không
  đọc lại từ đầu.

### 3.6 Tin nền và giọng

Frame `push` (việc nền xong) chỉ được đọc khi trạng thái là `idle` hoặc `listening`. Đang
`user_speaking`, `waiting_for_user`, `speaking`, `processing` thì xếp vào hàng chờ và đọc ở
`turnDone` hoặc `ttsEnd` kế tiếp. Chữ vẫn hiện ngay trong khung chat như cũ.

## 4. Trạng thái thật trên orb

| Trạng thái | Nhãn (vi) | Nguồn sự kiện thật |
|---|---|---|
| listening | ĐANG NGHE / ĐANG NGHE • LUÔN | recognition onstart |
| user_speaking | (giữ ĐANG NGHE, chữ tạm hiện dưới) | interim |
| waiting_for_user | ĐANG CHỜ BẠN | luật cụm từ CHỜ |
| processing | ĐANG SUY NGHĨ | sendMessage / frame status |
| processing + tool | ĐANG GỌI <tên tool> | frame tool_call |
| speaking | ĐANG NÓI | audio bắt đầu phát |
| interrupted | TẠM DỪNG, ĐANG NGHE BẠN | bargeStart |
| reconnecting | ĐANG KẾT NỐI LẠI | ws.onclose cho tới hello |
| cờ slow | hậu tố "· MẠNG CHẬM" | khúc TTS mất hơn 2500 ms mới phát |
| cờ background | hậu tố "· N VIỆC NỀN" | `GET /background` running_count qua background-strip |
| error | LỖI MIC | onError với lỗi chết |

Không có trạng thái giả. "Mạng yếu" chỉ hiện khi đo được, không suy đoán.

## 5. Ngữ cảnh giao diện gửi kèm mỗi lượt: `dashboard/ui-context.js`

Hàm thuần `build({page, selection, interruptedAt})` trả chuỗi rỗng khi không có gì đáng nói,
ngược lại trả một khối một dòng đứng SAU khối FILE ĐANG MỞ và TRƯỚC câu của người dùng:

```
[NGỮ CẢNH GIAO DIỆN: trang=kanban; chọn="đoạn người dùng đang bôi đen, tối đa 600 ký tự";
 ngắt_lời="Javis vừa bị ngắt khi đọc tới: ..."]
```

- `page` bỏ qua khi là `chat` hoặc `home` (mặc định, không mang thông tin).
- `selection` lấy từ vùng chọn trong trình sửa ghi chú hoặc trên trang; cắt 600 ký tự.
- Dashboard lột khối này khỏi bong bóng hiển thị (`_KHOI_NGU_CANH` trong app.js) và
  `sessions.py` lột khỏi tiêu đề hội thoại (`_KHOI_NGU_CANH_UI`), cùng cách với FILE ĐANG MỞ.
- Khối kênh web trong `channel_context.py` dặn model: "cái này / đoạn này / file này" trỏ vào
  khối đó, không hỏi lại.

## 6. Tool điều khiển dashboard: plugin `javis-ui` + `server/ui_bridge.py`

Tool `javis_ui(action, target, session_id?)`, `min_mode: safe`:

| action | target | Dashboard làm gì |
|---|---|---|
| `open_page` | một trong `home chat settings workflows agents skills chatbots files terminal selfimprove learn kanban models channels mcp plugins packs logs account usage` (nhận cả bí danh tiếng Việt: việc, tệp, cài đặt, mô hình, kết nối...) | `JavisNav.go(id)` |
| `open_file` | đường dẫn tương đối trong brain (không `..`, không tuyệt đối, không scheme) | `JavisOpenVaultPath(rel)` (cùng luật với link trong chat) |
| `open_task` | mã việc Kanban | sang trang Việc rồi mở ngăn kéo việc đó |
| `scroll` | `top` hoặc `bottom` | cuộn khung chat |

Luồng: handler tool gọi `ui_bridge.request(...)` → publish frame
`{"type":"ui_action","id","action","target","session_id"}` lên `_CHAT_RUNTIME` → mọi tab đang
mở nhận; tab thực hiện khi `session_id` rỗng hoặc trùng phiên đang xem → gửi lại
`{"action":"ui_result","id","ok","detail"}` qua `/ws` → vòng nhận của WS gọi
`ui_bridge.resolve()` → tool trả `"Đã mở trang Việc"` hoặc lỗi. Không có tab nào: trả ngay
"không có dashboard nào đang mở" (dùng khi gọi từ Telegram). Quá 4 giây không ai đáp: trả lỗi
hết giờ. Dashboard KIỂM lại target một lần nữa trước khi chạy (không tin server tuyệt đối).

`ui_bridge.py` giữ tham chiếu runtime (main gắn lúc khởi động) và bảng future chờ ack. Nó
không import main; plugin import nó, giống cách `javis-task` import `tasks`.

## 7. Tool điều khiển app máy tính: plugin `desktop-apps`

Ba tool, cùng `check_fn` chặn khi `deploy_mode() == "docker"` hoặc Linux không có
`DISPLAY`/`WAYLAND_DISPLAY`, với câu lý do nói rõ Javis đang chạy ở máy chủ chứ không phải máy
người dùng.

- `javis_app_list(filter?)` readonly: app cài (Windows: quét `.lnk` ở hai thư mục Start Menu;
  mac: `/Applications`; Linux: `.desktop` trong `/usr/share/applications` và `~/.local/share`)
  và app đang chạy (Windows `tasklist /V /FO CSV`, còn lại `ps`). Kết quả cắt 60 dòng.
- `javis_app_open(name)` safe: `name` là tên app (khớp mờ: chuẩn hoá bỏ dấu, exact →
  startswith → contains → difflib ≥ 0.75, có bảng bí danh chrome/edge/word/excel/máy tính/
  trình duyệt...), hoặc URL http(s), hoặc đường dẫn tuyệt đối tồn tại nằm trong thư mục người
  dùng hay trong brain. Windows dùng `os.startfile`, mac `open`, Linux `xdg-open`/`gtk-launch`.
- `javis_app_close(name, force=false)` full: khớp `name` với ảnh tiến trình và tiêu đề cửa sổ
  đang chạy. Windows: `taskkill /IM <exe>` (đóng lịch sự, app đang có tài liệu chưa lưu sẽ hiện
  hộp thoại hỏi), chờ 1,5 giây, còn sống thì báo và gợi ý `force=true` (`/F`). mac:
  `osascript quit`, force `pkill`. Linux: `pkill`.

Chủ dự án chọn "mở và đóng đều làm ngay": tool KHÔNG hỏi lại, nhưng đóng mặc định là đóng lịch
sự để chính app hỏi lưu, và `force` là tham số model chỉ truyền khi người dùng nói "ép tắt".
Manifest `enabled: true` vì trên máy chủ Docker plugin tự chặn; phiên bản fork trên VPS Linux
không có màn hình cũng tự chặn.

## 8. TTS streaming: `GET /tts`

Nhánh Edge đổi từ gom `bytes` sang `StreamingResponse`: lấy khúc audio ĐẦU TIÊN trước khi trả
response (để lỗi Edge vẫn thành 502 thay vì một stream rỗng), rồi phát tiếp các khúc còn lại
khi chúng về. Header `Cache-Control: no-cache`, `Accept-Ranges: none`. Hai provider trả phí giữ
nguyên (API của họ trả nguyên file). Client không đổi: thẻ `<audio>` của Chrome phát dần mp3
chunked. Đo được ở voice.js: thời gian từ `play()` đến sự kiện `playing`; quá 2500 ms thì bật
cờ `slow`.

## 9. Prompt

Chỉ thêm vào khối kênh WEB (`channel_context.build_channel_block`, nhánh dashboard), sáu dòng:
có `javis_ui` để mở trang/file/việc khi người dùng yêu cầu bằng lời; có `javis_app_open` /
`javis_app_close` / `javis_app_list` khi họ muốn mở hay tắt app trên máy; đọc kết quả tool rồi
nói đúng như vậy; khối `[NGỮ CẢNH GIAO DIỆN ...]` là thứ người dùng đang nhìn và "cái này"
trỏ vào đó; nhắc lại rằng ngắt_lời nghĩa là không đọc lại phần đã nói. Telegram không nhận
mấy dòng này, nhưng ba tool app vẫn gọi được từ Telegram (mở Chrome trên máy nhà khi đang ở
ngoài đường là ca dùng thật).

## 10. Cài đặt

Cài đặt nhanh (popover giọng) thêm hai hàng, lưu localStorage: `javis.endpoint` (500/800/1200)
và `javis.bargeIn` (mặc định bật). Không thêm khoá vào `settings.json`.

## 11. Kiểm thử

JS (node thuần, `tests/js/`): `test_voice_turn.js` (state machine, endpointing hai ngưỡng,
luật CHỜ/DỪNG, chen ngang giả và thật, hoãn tin nền), `test_ui_actions.js` (kiểm target: trang
lạ, `..`, đường tuyệt đối, bí danh), `test_ui_context.js` (khối rỗng khi không có gì, cắt 600
ký tự, lột khỏi hiển thị), `test_orb_trang_thai_that.js` (app.js nối reconnecting/tool_call,
voice.js dùng 5 nhịp và pause thay vì giết). Bốn test mic cũ phải còn xanh.

Python (`tests/python/`): `test_ui_bridge.py` (không client → lỗi rõ; có client → frame đúng
khuôn, ack giải future, hết giờ), `test_desktop_apps_plugin.py` (khớp mờ, bí danh, chặn Docker,
chặn đường dẫn ngoài home/brain, mở/đóng đi qua hàm tiêm được, không mở gì thật),
`test_tts_stream.py` (Edge giả trả nhiều khúc → response streaming, Edge lỗi ngay → 502),
`test_channel_ui_prompt.py` (khối web có javis_ui, khối Telegram không), tiêu đề hội thoại
lột khối ngữ cảnh giao diện.

## 12. Ngoài phạm vi (ghi để không lạc)

Wake word "Javis ơi" khi mic tắt; mô hình dò hết lượt; STT server cho dashboard; Browser
Extension; Desktop Agent điều khiển máy KHÁC máy chạy Javis; camera và sensor; huỷ việc
Kanban bằng giọng (tool `javis_task` chưa có op cancel).
