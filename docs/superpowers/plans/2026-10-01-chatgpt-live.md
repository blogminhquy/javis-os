# ChatGPT Live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bấm mic là gọi Javis qua ChatGPT Live (Codex realtime trên gói ChatGPT), có thanh gọi, đường dự phòng Cơ bản cho mọi máy, và trang cài đặt giọng nói còn 3 ô.

**Architecture:** Một `codex app-server` sống lâu cho cả máy chủ (`server/codex_realtime.py`) chuyển gói bắt tay WebRTC; âm thanh đi thẳng trình duyệt tới OpenAI. Nhà cung cấp mới `chatgpt` trong `server/voice_live.py` nói cùng khuôn sự kiện `LiveProvider`, nên route `/ws/voice-live` và `dashboard/voice-live.js` chỉ thêm nhánh WebRTC. Handoff của model thành `tool_call ask_javis` như các Live khác, kết quả về bằng `appendSpeech`.

**Tech Stack:** Python 3.12 FastAPI, JSON-RPC qua stdio tới Codex CLI ≥ 0.153, WebRTC trên trình duyệt, vanilla JS, test bằng `python tests/run.py` (script Python + node).

**Spec:** `docs/dev/2026-10-voice-call-spec.md`

## Global Constraints

- Tên hiện ra cho người dùng: chỉ **ChatGPT Live**. Không dùng chữ "song công" ở nhãn, thông báo, CHANGELOG.
- Không dùng ký tự em dash (U+2014) ở bất cứ đâu.
- Chuỗi giao diện: tiếng Việt có dấu trong `dashboard/i18n/vi.json` và bản dịch trong `en.json`; không hard-code "anh/em" (`test_xung_ho.py`).
- Tên module/hàm/khoá/route MỚI bằng tiếng Anh; chú thích và tài liệu tiếng Việt.
- Codex app-server luôn chạy `[cli, "-c", "features.realtime_conversation=true", "app-server"]`; `includeStartupContext: false`; mỗi phiên realtime một thread mới.
- Giọng v3 hợp lệ: juniper, maple, spruce, ember, vale, breeze, arbor, sol, cove. Mặc định `juniper`.
- Thêm route thì `python tests/python/test_route_table.py --update` trong cùng commit. Thêm khoá cài đặt thì nối nhánh `voice` của `POST /settings` (allowlist).
- Mỗi PR: đặt số phiên bản trước (`docs/quy-uoc-dev.md`), CHANGELOG viết cho người đọc trên điện thoại, CI xanh rồi merge, xác nhận bản phát hành.

---

## PR 1 (0.65.17): ChatGPT Live

### Task 1: `server/codex_realtime.py` - quản lý Codex app-server

**Files:** Create `server/codex_realtime.py`; Test `tests/python/test_codex_realtime.py`.

**Interfaces (Produces):**
- `class AppServer(cli: str, popen_factory=subprocess.Popen)`: `start()` (spawn + `initialize` experimentalApi + `initialized`), `async request(method, params, timeout=30) -> dict` (trả `result`, ném `AppServerError(message)` khi có `error`), `subscribe(thread_id) -> asyncio.Queue` (thông báo có `params.threadId` khớp), `unsubscribe(thread_id)`, `alive -> bool`, `close()`.
- Tự từ chối mọi yêu cầu server gửi về (có `id` và `method`).
- `def get_app_server() -> AppServer` (singleton, dựng lại khi tiến trình chết; dùng `claude_cli.find_codex_cli()`), `def realtime_available() -> (bool, reason)` (có binary và có đăng nhập ChatGPT).
- Luồng đọc stdout là thread daemon; chuyển sang asyncio bằng `loop.call_soon_threadsafe`.

- [ ] Viết test với tiến trình giả (đối tượng có `stdin.write/flush`, `stdout.readline` từ hàng đợi): khởi động gửi đúng `initialize` có `capabilities.experimentalApi`, gọi `initialized`; `request` khớp `id`; lỗi thành `AppServerError`; yêu cầu duyệt quyền bị từ chối; thông báo đi đúng hàng đợi theo `threadId`; tiến trình chết thì `alive` false và `get_app_server` dựng lại.
- [ ] Chạy test, thấy đỏ. Viết code. Chạy `python tests/run.py codex_realtime`, xanh.

### Task 2: Nhà cung cấp `chatgpt` trong `server/voice_live.py`

**Files:** Modify `server/voice_live.py`; Test `tests/python/test_voice_live_chatgpt.py`.

**Interfaces:**
- Consumes: `codex_realtime.get_app_server()`, `AppServer.request/subscribe/unsubscribe`.
- Produces: `PROVIDERS["chatgpt"] = {"label": "ChatGPT Live (gói ChatGPT)", "key_field": None, "default_model": "", "default_voice": "juniper", "voices": CHATGPT_VOICES, "transport": "webrtc"}`; `class ChatGPTLive(LiveProvider)` với `transport = "webrtc"`, `async start_webrtc(sdp) -> str` (answer), `speakable(text, limit=600) -> str`; `make_provider` nhận nhánh không key; `catalog()` mang `transport` và `key_field` có thể None.
- `connect()`: app-server + `thread/start {ephemeral, cwd: thư mục tạm rỗng, sandbox: "read-only", approvalPolicy: "never", developerInstructions: "Reply only: [FINAL]"}`, `subscribe(thread)`.
- `restore_history()`: giữ lại thành `initialItems` (`[{role, text}]`, tối đa 12 tin / 8.000 ký tự) cộng mục lục bộ nhớ (truyền qua `memory_index`).
- `start_webrtc()`: `thread/realtime/start {threadId, version: "v3", outputModality: "audio", transport: {type: "webrtc", sdp}, prompt, voice, includeStartupContext: false, clientManagedHandoffs: true, delegationAckFiller: true, flushTranscriptTailOnSessionEnd: false, realtimeStartInstructions: "Do no work. Reply only: [FINAL]", initialItems}` rồi chờ `thread/realtime/sdp` (25 s) hoặc `thread/realtime/error`.
- `translate(notif)`: `transcript/delta` user thành transcript không final (gom bộ đệm), assistant delta thành transcript assistant (đóng bộ đệm user thành final trước); `transcript/done` user thành final, assistant done thành `turn_done`; `itemAdded` `handoff_request` thành `tool_call ask_javis` (yêu cầu dưới 3 tiếng thì ghép câu user gần nhất trong 10 giây); `turn/started` thì gọi `turn/interrupt` (không phát sự kiện); `realtime/error` thành `error`; `realtime/closed` thành `error` nếu không phải do Javis đóng.
- `send_text` = `thread/realtime/appendText`; `send_tool_result` = `thread/realtime/appendSpeech` với `speakable(result)`; `send_audio`, `truncate_played`, `interrupt` không làm gì; `close()` = `thread/realtime/stop` + `unsubscribe`.
- Prompt nhân cách theo mục 3.3 của spec.

- [ ] Viết test với `AppServer` giả (ghi lại request, đẩy thông báo vào hàng đợi): khuôn `thread/start` và `realtime/start` (có `includeStartupContext: False`, voice mặc định juniper, initialItems từ lịch sử); dịch từng loại thông báo; handoff ngắn được ghép; `turn/started` sinh `turn/interrupt`; kết quả đi `appendSpeech` đã lột markdown và ≤ 600 ký tự; `make_provider` chọn `chatgpt` không cần key nhưng báo lỗi dễ hiểu khi chưa nối ChatGPT.
- [ ] Đỏ, viết code, xanh: `python tests/run.py voice_live`.

### Task 3: Route `/ws/voice-live` và cài đặt

**Files:** Modify `server/main.py` (route `/ws/voice-live`, `/voice/options`, nhánh `voice` của `POST /settings`); Test thêm vào `tests/python/test_voice_live_chatgpt.py` (route qua `TestClient.websocket_connect` với provider giả).

- `ready` mang `transport` (`"webrtc"` với chatgpt). Khung mới từ trình duyệt `{"type":"webrtc_offer","sdp"}` gọi `prov.start_webrtc` rồi trả `{"type":"webrtc_answer","sdp"}` (lỗi thì `error`).
- Trước `connect` với chatgpt: `openai_oauth.write_codex_auth()` trong thread.
- Mục lục bộ nhớ: đọc `memory/MEMORY.md` của brain (cắt 4.000 ký tự) truyền vào provider.
- `_run_tool`: sau khi có kết quả, gửi `{"type":"tool_result","name","text"}` về trình duyệt và lưu vào phiên như tin assistant.
- Khoá mới `voice.chatgpt_voice` (chỉ nhận giá trị trong `CHATGPT_VOICES`).
- `/voice/options`: `live_providers` có `chatgpt` với `available` theo `codex_realtime.realtime_available()` và `hint` khi chưa sẵn.

### Task 4: `dashboard/voice-live.js` nhánh WebRTC

**Files:** Modify `dashboard/voice-live.js`; Test `tests/js/test_voice_live_webrtc.js`.

- Sau khi WS mở, CHỜ `ready` (tối đa 20 s) rồi mới chọn đường: `transport === "webrtc"` thì dựng `RTCPeerConnection`, `addTransceiver("audio", {direction:"sendrecv"})`, `replaceTrack` bằng track mic, kênh dữ liệu `oai-events`, chờ ICE (3 s), gửi `webrtc_offer`, đặt answer; còn lại giữ đường PCM cũ.
- Tiếng Javis: track remote vào một `<audio autoplay>`; analyser trên track remote cho `isSpeaking()` và `onSpeakStart/End`.
- `progress()` ở WebRTC trả `{played: 1, total: 1}` (chữ về gần như cùng lúc với tiếng).
- Thêm `setMuted(bool)` (tắt track mic, dùng chung cho cả hai đường) và `onToolResult(name, text)`.
- `stop()` đóng peer connection.

### Task 5: `dashboard/app.js`, mẫu giọng, cài đặt ChatGPT Live

**Files:** Modify `dashboard/app.js` (`batLive`: `onToolResult` vẽ bong bóng Javis đầy đủ và `recordTurn`), `dashboard/console.js` (ô nhà cung cấp Live hiện "ChatGPT Live", ô giọng 9 giọng + nút nghe thử mẫu), Create `dashboard/voices/<giọng>.mp3` (9 file, mono 24 kbps), i18n vi/en; Test cập nhật `tests/js/test_voice_v2_day_noi.js`.

### Task 6: Tài liệu, CHANGELOG, phát hành 0.65.17

- `docs/02-tro-chuyen-va-giong-noi.md` và `docs/en/02-chat-and-voice.md`: mục ChatGPT Live (bấm mic, cần nối ChatGPT ở trang Models, giọng, hạn mức).
- Chạy `python tests/run.py voice live stt route_table i18n`, rồi toàn bộ `--js`. Thử thật một cuộc gọi trên máy.

## PR 2 (0.65.18): Trải nghiệm gọi điện

### Task 7: Chọn đường gọi

**Files:** Create `server/voice_call.py`; Modify `server/main.py` (`GET /voice/call`, allowlist `call_engine`, `make_provider` theo đường), `dashboard/app.js` (`napCaiDatGiong` đọc `/voice/call`); Test `tests/python/test_voice_call_select.py`.

- `select_call_engine(cfg) -> {"engine": "chatgpt"|"api"|"basic", "live_provider": str, "reason": str, "setting": str}`; khoá `voice.call_engine` = auto | chatgpt | api | basic, thiếu là auto. Auto: chatgpt nếu `realtime_available()`; api nếu `voice.live_provider` có key; còn lại basic. Chọn tay mà không chạy được thì rơi xuống và ghi lý do.
- Client: engine chatgpt/api đặt `voiceMode = "live"`; basic dùng `fast` khi có bộ não giọng, không thì `standard`.

### Task 8: Thanh gọi

**Files:** Create `dashboard/call-bar.js`; Modify `dashboard/index.html`, `dashboard/style.css`, `dashboard/app.js` (nút mic, Esc, bỏ Space), i18n; Test `tests/js/test_call_bar.js`, sửa các test đang ghim phím Space.

- `JavisCallBar.show({onMute, onHangup})`, `.setState(state, detail)`, `.hide()`, đồng hồ cuộc gọi. Trạng thái: listening, speaking, working, waiting_wake, reconnecting.
- Nút mic đổi nhãn và `aria-label` thành "Cúp máy" khi đang gọi. Esc cúp. Space không còn làm gì.
- Nằm ngay trên khung chat, cả trang Trò chuyện; một cột trên điện thoại.

### Task 9: Đường Cơ bản dùng vỏ gọi, tự rơi xuống khi lỗi

- Đường basic chính là rảnh tay hiện nay, chỉ đổi sang thanh gọi. Live mở không được trước `ready` thì báo một dòng và mở cuộc gọi bằng đường kế tiếp.
- Phát hành 0.65.18.

## PR 3 (0.65.19): Trang cài đặt gọn

### Task 10: Thẻ Giọng nói mới

**Files:** Modify `dashboard/console.js` (thẻ giọng nói), `dashboard/index.html` (bỏ `#qsTts`, các ô mic), `dashboard/quick-settings.js`, `server/main.py` (allowlist), `server/voice_brain.py` (tự chọn bộ não giọng khi trống), i18n; Test `tests/js/test_voice_settings_simple.js`, sửa các test ghim ô cũ (`test_micro_gop_vao_che_do.js`, `test_voice_v2_day_noi.js`, `test_luu_cai_dat_giong.py`, `test_voice_tap_am.py`, `test_bo_nut_loa_header.js`, `test_giong_edge_da_ngon_ngu.py`).

- Trang chính: dòng "Đang dùng", ô Giọng Javis đổi theo đường gọi + Nghe thử, công tắc Tập trung. Nâng cao: Đường gọi, Tốc độ đọc, ElevenLabs. Mọi ô tự lưu.
- Bỏ: đọc trả lời bằng giọng, nhịp hội thoại (gỡ wiring `voice-adaptive*.js` khỏi trang), từ hay nghe nhầm, key OpenAI, ngôn ngữ nghe (theo ngôn ngữ giao diện), im lặng rồi gửi, ngắt lời bằng giọng, tai nghe lại, bộ não giọng. Giá trị đã lưu vẫn dùng tiếp.

### Task 11: Tài liệu, CHANGELOG, phát hành 0.65.19, xoá file kế hoạch này

- Cập nhật tài liệu người dùng, ghi trạng thái "đã làm xong" vào spec, xoá `docs/superpowers/plans/2026-10-01-chatgpt-live.md`.
