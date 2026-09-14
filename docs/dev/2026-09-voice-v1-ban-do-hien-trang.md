# Voice V1 - Phase 0: bản đồ hiện trạng (CURRENT_ARCHITECTURE_MAP)

> Viết 2026-09-14 trên nền code v0.55.66. Đây là deliverable số 1 trong `03_JAVIS_OS_ROADMAP.md`
> (Phase 0 - Audit). Chỉ ghi SỰ THẬT đọc từ code, kèm đường dẫn và số dòng, không đề xuất.
> Phần cuối là bài học rút từ mã nguồn LiveKit (livekit/agents và livekit/livekit) để Phase 1 dùng.

## 0. Kích thước và bố cục

- Backend: `server/main.py` 15.970 dòng, `app = FastAPI` ở `main.py:128`. Router con ở `server/routes/`
  (`domain.py`, `graph.py`, `packs.py`) và các module tự đăng ký `APIRouter` (`tasks.py`, `reminders.py`).
- Dashboard: một trang `dashboard/index.html` (nạp toàn bộ JS ở dòng 773-823). File liên quan voice:
  `voice.js` (30 KB, class `JavisVoice`), `app.js` (149 KB, chat + WS + hands-free), `quick-settings.js`
  (công tắc TTS), `voice-test.html` (harness thử độc lập).
- Test: `tests/run.py` (tự tìm `.venv`), `tests/python/` 261 file, `tests/js/` 79 file chạy bằng node thuần.
  Test voice hiện có: `tests/js/test_mic_doc_chong_va_loa_theo_mic.js`, `test_mic_khong_tu_gui.js`,
  `test_mic_loi_khong_lap.js`, `test_bo_nut_loa_header.js`; `tests/python/test_tin_thoai.py`.

## 1. Voice hôm nay

### 1.1 Nghe (STT) - Web Speech API trong trình duyệt, KHÔNG có STT server cho dashboard

- Toàn bộ ở `dashboard/voice.js`. `_initRecognition()` `voice.js:97` dùng
  `window.SpeechRecognition || webkitSpeechRecognition`, `continuous = true` (`:106`), trên iOS ép `false`
  (`:111`, `_laIOS()` `:234`), `interimResults = true`.
- KHÔNG có `MediaRecorder` ở bất kỳ đâu trong repo. Dashboard không bao giờ upload byte âm thanh lên server.
  `getUserMedia` chỉ dùng cho đồng hồ mức mic và dò chen ngang: `_startMicMeter()` `voice.js:60` với
  `{echoCancellation, noiseSuppression, autoGainControl}`.
- Ghép chữ: `onresult` `voice.js:143` dựng lại từ toàn bộ `event.results` mỗi nhịp; nối qua nhiều phiên bằng
  `_ghepChuyenBien()` `:221`.
- Lỗi chết mic: `JavisVoice.LOI_CHET = ["not-allowed","service-not-allowed","audio-capture"]` `:11`,
  `micHong()` `:232`. Điểm vào: `startListening(tuDong)` `:277`, `stopListening()` `:309`, `toggleListening()` `:324`.
- STT server CÓ nhưng chỉ Telegram và Zalo dùng: `server/stt.py` (Groq Whisper `whisper-large-v3-turbo`,
  `groq_nghe()` `stt.py:78`), closure `stt_fn` dựng ở `main.py:15199`, gọi từ `telegram_bot.py:579-596` và
  `zalo_bot.py:370-386`. KHÔNG có route `/stt` hay `/transcribe`.

### 1.2 Nói (TTS) - server proxy, cắt câu, gần như streaming

- Route duy nhất: `GET /tts` `main.py:10254` (tham số `text`, `voice` mặc định `vi-VN-HoaiMyNeural`, `rate`
  `+5%`) và `GET /tts/voices` `main.py:10288`. Chọn provider theo `settings.voice.tts_provider`; provider trả
  phí lỗi thì RƠI VỀ Edge (`main.py:10272-10277`).
- Provider: `_tts_edge()` `~main.py:10211` (gom cả stream `edge_tts` thành một `bytes` rồi mới trả),
  `_tts_openai()` `~:10220` (`gpt-4o-mini-tts`, mp3), `_tts_elevenlabs()` `~:10238` (`eleven_multilingual_v2`).
- Phát ở client: hàng đợi `speak()` `voice.js:331`, `enqueueSpeak()` `:338`, `_pumpQueue()` `:351`.
  `_speakBackend()` `:452` gọi `_splitForLatency()` `:462` (câu đầu tách riêng, cắt ở dấu phẩy nếu quá 160 ký tự,
  phần còn lại 600 ký tự một khúc), mỗi khúc là một `GET /tts` riêng, khúc i+1 tải trước khi khúc i bắt đầu
  (`:517-522`). iOS dùng một thẻ `<audio>` mở khoá sẵn (`_moKhoaAudioIOS()` `:248`).
- Bậc thang lỗi khúc: `_chunkFailed()` `:541` thử lại backend một lần, rồi `speechSynthesis` của trình duyệt CHỈ
  khi có giọng đúng ngôn ngữ, không thì bỏ khúc.
- Lột markdown chỉ ở client: `_cleanForTTS()` `voice.js:428-446`. Server không lột; `channel_context.py:261-263`
  dặn model đừng giảm định dạng vì dashboard tự lột.
- Text nào đi vào TTS: mỗi frame `stream` ở `app.js:242-246` (nếu `voice.ttsEnabled` và `data.tts !== false`),
  bỏ khối điều khiển dở dang; nếu lúc stream chưa đọc gì thì đọc cả câu trả lời cuối ở `app.js:269`; tin `push`
  nền cũng được đọc ở `app.js:201`.

### 1.3 VAD, im lặng, wake word, chen ngang

- Tự gửi khi im lặng: `silenceMs = 1500` `voice.js:118`, reset ở mỗi kết quả interim, hết giờ thì
  `stopListening()` → `onend` → `onTranscript` → `sendMessage` (`voice.js:166-169`, `:194-215`, `app.js:104-107`).
- VAD: KHÔNG có VAD gác đầu vào. Chỉ có dò năng lượng để chen ngang: `_startBargeMonitor()` `voice.js:391`,
  `setInterval` 100 ms, RMS trên luồng mic đã khử vọng, tự hiệu chuẩn nền ~600 ms đầu, ngưỡng
  `max(0.045, baseline*2 + 0.02)`, cần 3 nhịp liên tiếp (~300 ms). Chỉ chạy khi `_resumeAfterTTS` (mic đang mở
  trước khi TTS bắt đầu).
- Chen ngang: `_bargeIn()` `:423` = `stopSpeaking()` + `startListening(true)`. Không có khái niệm "tạm dừng rồi
  phát tiếp nếu là chen ngang giả".
- Chống vọng: `onresult` bỏ hết chữ khi `isSpeaking()` (`:147`); `_muteRecognition()` `:369` huỷ recognition khi
  TTS bắt đầu; `_resumeRecognitionIfNeeded()` `:381` mở lại sau 400 ms.
- Wake word: KHÔNG có. Không có "hey javis" ở đâu.
- Rảnh tay (gần nhất với luôn nghe): `let handsFree` `app.js:1976`, nút `#voiceBtn` `app.js:2014-2030`, vòng
  keep-alive 500 ms mở lại mic khi rảnh `app.js:2032-2040`, `tatRanhTay()` `:1979` tắt khi mic lỗi chết.
  Push-to-talk phím Space `app.js:2042-2051`, Escape thoát rảnh tay `:2052-2058`.
- Trạng thái orb: `#orbState` `index.html:220`, `setOrbState()` `app.js:85` với 4 giá trị
  listening / thinking / speaking / ready. Không có trạng thái "đang chờ bạn", "đang gọi tool", "mạng yếu".

### 1.4 Cài đặt

- `settings.json` mục `voice`: `tts_provider` (edge | openai | elevenlabs), `openai_tts_voice`,
  `openai_tts_model`, `elevenlabs_key`, `elevenlabs_voice`, `elevenlabs_model`. Đọc ở `main.py:10220-10252`,
  ghi bởi `console.js:5894-5910` qua `POST /settings` (`main.py:3970`).
- Khoá STT là `model.groq_api_key` (`main.py:15185`); OpenAI TTS dùng chung `model.openai_api_key`.
- Client (localStorage): `javis.ttsEnabled`, `javis.voice`, `javis.rate`, `javis.recLang` (`app.js:2078-2103`).
- UI: `#qsTts` `index.html:333`, `#voicePopover` `:346-380` (radio ngôn ngữ nghe vi-VN/en-US, radio giọng
  HoaiMy/NamMinh, `#rateSlider` 0.7-1.8, `#testVoiceBtn`), `#voiceBtn` `:460`, `#voiceInterim` `:221`.
- Ghi nhận thực tế: `settings.json` máy này để `tts_provider: "elevenlabs"` nhưng khoá `sk_...` nằm nhầm ô
  `elevenlabs_voice`, `elevenlabs_key` trống, nên ElevenLabs luôn lỗi và rơi về Edge (khớp ký ức
  `project_elevenlabs-plan-status`).

## 2. Kênh thời gian thực

### 2.1 WebSocket

| endpoint | server | client |
|---|---|---|
| `/ws` chat | `main.py:10361` `websocket_endpoint` | `app.js:133`, `connect()` `app.js:128` |
| `/ws/terminal` | `main.py:11606` | `code-term.js:241` |
| `/ws/graph` | `routes/graph.py:152` | `app.js:1166` |

`/ws` chỉ là NGƯỜI ĐĂNG KÝ: job chat sống trong `_CHAT_RUNTIME` (`server/chat_runtime.py`, class `ChatRuntime`:
`add_client / remove_client / register_job / get_job / finish_job / cancel_session / cancel_matching / snapshot /
publish`). Đóng tab không giết lượt đang chạy. Mọi frame ra đều mang `session_id` (`_SendProxy` `main.py:10398-10416`),
`send_lock` tuần tự hoá ghi (`:10387`).

Frame dashboard xử lý (`app.js` `handleMessage`): `hello` (:164), `push` (:193, kết quả nền, cũng được đọc
TTS), `inbox` (:213), `status` (:225), `tool_call` (:229, mang `tool`), `tool_result` (:232), `stream` (:234, cờ
`tts:false` tuỳ chọn), `response` (:249, mang khối JAVIS_ASK), `error` (:274), `resume` (:287), `system` (:290),
`turn_done` (:292).

### 2.2 SSE

`GET /workflows/resume` `main.py:7751`, `GET /workflows/run` `:7767`, `POST /ollama-local/pull` `:12413`,
`POST /chat/stream` `:15777` (cho CLI, cùng từ vựng `{"type":...}` với `/ws`, không per-token). Middleware gzip
tự viết ở `main.py:250-280` chỉ nén `/static/` để không đệm stream.

### 2.3 Huy hiệu trạng thái

1. `#engineBanner` `index.html:72`: engine chết. `refreshEngineBanner()` `console.js:7252` POLL
   `GET /connect/health` mỗi 90 giây (`console.js:7286-7287`). Không đẩy qua WS.
2. `#bgStrip` `index.html:433`: dải việc nền. `background-strip.js` poll `GET /background` (`main.py:8444`, view
   ở `background_status.py:170`), được kích ngay bởi frame `push` và `turn_done`.
3. `#orbState`: xem 1.3.

## 3. Việc nền (Kanban)

- `server/tasks.py` (class `TasksFeature` `:87`), lưu SQLite `server/task_store.py` → `server/kanban.sqlite3`.
  Đăng ký ở `main.py:8193`.
- Route chính: `POST /kanban/task` `tasks.py:1076` (form `title, intent, route, priority, deps, needs_approval,
  chat_id, brain, capability, execution_mode, idempotency_key`) → `enqueue()` `:191`; `POST /kanban/orchestration`
  `:1212` (`off | manual | auto`); `POST /kanban/task/cancel` `:1262`; `GET /kanban/task/show` `:1063`.
- Cờ tự vận hành theo từng board, MẶC ĐỊNH `off` (`main.py:8171`, `task_store.py:170-190`).
- Báo kết quả về đúng khung chat: hằng `WEB_CHAT_PREFIX = "web:"` `main.py:7911`; prompt dặn model gắn
  `chat_id: "web:<sid>"` ở `channel_context.py:267-285`; runner `_report()` `tasks.py:936` → `deps.report`
  = `_notify_owner()` `main.py:8000` → `_bo_vao_hom_thu()` `:7947` (luôn ghi hòm thư) + `_gui_qua_kenh()` `:8060`
  → `push_to_chat()` `:7887` publish frame `push`. `quiet=True` khi `done` (vào chat và hòm thư nhưng không chấm đỏ).
- Hòm thư: `server/inbox.py` → `STATE_DIR/inbox.json`; route `GET /inbox` `main.py:10020`, `POST /inbox/read`
  `:10026`; UI `dashboard/notifications.js`.
- UI Kanban: `renderKanban()` `console.js:2497`, `showTask(id)` `:2696-2702` mở drawer, poll 3 giây `:2748`.

## 4. Điều hướng và hành động có cấu trúc trên dashboard

- Router là Alpine store, không phải hash: `Alpine.store("nav")` `console.js:6365`, `go(id)` `:6382` →
  `navigateTo(id)` `:250` → `renderPage(id)` `:391` (renderChat / renderStudioPage / renderSettings / renderModels /
  renderConnect / renderPlugins / renderChannels / renderFiles / renderCode / renderKanban ...). Hash duy nhất là
  deep link `#open=<path>` (`console.js:7345-7352`).
- Mở file: `window.JavisOpenNoteAt(rel, name)` `console.js:361` (editor gắn vault, trả `false` màn hẹp),
  `window.JavisEditFile(rel)` `file-editor.js:376` (modal), `window.JavisOpenFiles(full)` `console.js:270-289`.
  Link trong chat: `chat-render.js:189-226` sinh `<a href="#open=...">`, click → `moFileVault(rel)`
  `chat-render.js:854` thử ba cửa trên theo thứ tự.
- Mở task: `showTask(id)` `console.js:2696`, không đổi route.
- Giao thức model → UI hiện có: khối bình luận HTML `<!-- JAVIS_XXX: ... -->`. Regex server `_CTRL_RE`
  `channel_context.py:551`; `strip_control_blocks()` `:578` giữ JAVIS_ASK (đổi thành danh sách số cho kênh chữ),
  MỌI khối JAVIS_* khác bị bỏ trước khi lưu (`main.py:10318`), trước Telegram, trước báo cáo task. Client chỉ
  parse `JAVIS_ASK` ở `chat-ask.js` (`ASK_RE` `:30`, `extract()` `:56`, tối đa 4 nút, nhãn 40 ký tự), dùng ở
  `app.js:250/261/367`. `JAVIS_LESSON:` là dòng thường (`main.py:5273`). Không có khối nào ra lệnh cho UI.
- Khối "FILE ĐANG MỞ" do FRONTEND dựng ở `app.js:393-399` mỗi lượt, từ `JavisPin` `app.js:1800`; server lột khỏi
  tiêu đề ở `sessions.py:206`. Đây là kênh "ngữ cảnh đang nhìn" duy nhất hôm nay, chỉ chở file ghim.

## 5. Plugin

- Host `server/plugins_host.py`. Ba nguồn (`:46-50`): bundled `system/plugins/<slug>/`, global
  `STATE_DIR/plugins/`, vault `<vault>/plugins/<slug>/` (cần `JAVIS_ENABLE_USER_PLUGINS=true`). Trạng thái
  bật/tắt bundled ghi đè ở `STATE_DIR/plugins.json`, không sửa yaml gốc. Dữ liệu riêng `STATE_DIR/plugin-data/<slug>/`.
- `PluginContext` `:313`: `register_tool(name, description, handler, schema, min_mode="readonly", check_fn,
  emoji)` `:337`, `VALID_MIN_MODE = ("readonly","safe","full")` `:52`, `register_hook(event, cb)` `:368`
  (`pre_tool_call`, `post_tool_call`), `on_unload(fn)` `:355`.
- Cưỡng chế quyền bằng code: `_min_mode_ok()` `:586`, bọc async `:599-609` trả chuỗi `ERROR: tool ... cần mức
  quyền cao hơn`. Ánh xạ catalog `:722-731` readonly → read, safe → write, full → danger.
- Ra engine qua hub: `mcp_hub.discover_all()` `mcp_hub.py:869`, gộp `plugins_host.plugin_tools()` ở `:938-947`
  (tool trùng tên tool lõi thì bị bỏ), bọc hook `:951-956`. Claude Agent SDK gắn plugin in-process và gửi header
  `x-javis-no-plugins: 1` (`:1054-1055`); Codex đi qua hub HTTP.
- Bundled hiện có: `datetime-vn, fb-monitor-apify, image-chatgpt, javis-connect, javis-schedule, javis-task,
  meta-ads-graph, meta-pages-graph, tool-audit, youtube-read, zalo-image`. Mẫu ngắn nhất để chép: `tool-audit`.

## 6. Điều khiển app máy tính: CHƯA CÓ GÌ

- Không có `os.startfile`, không `pyautogui / pywinauto / win32gui`, không khái niệm desktop agent.
- `subprocess.Popen` chỉ dùng cho engine CLI, mở terminal đăng nhập MCP (`claude_cli.py:789`), terminal xterm
  (`terminal.py:258/286`, WS `/ws/terminal`, cổng `JAVIS_TERMINAL=0`), updater, và restart tách tiến trình
  `main.py:9621-9623`. `server/winproc.py` chỉ lo ẩn cửa sổ console (canary `tests/python/test_windows_no_console.py`).
- `docs/dev/` không có kế hoạch voice hay realtime nào trước bản này; chỉ spec đa ngôn ngữ nhắc STT/TTS ở
  `2026-08-da-ngon-ngu-spec.md:183-189, 285-293, 440-446`.

## 7. Nhận biết máy chạy

`server/deploy_info.py`: `deploy_mode()` `:17` trả `docker` (có `/.dockerenv` hoặc `JAVIS_STATE_DIR` bắt đầu
`/data`) | `windows` (`os.name == "nt"`) | `native`; `host_platform()` `:56` trả windows | mac | linux.
`STATE_DIR` ở `config.py:15`. Không có biến `IN_DOCKER`.

## 8. Đối chiếu roadmap Phase 0

| Roadmap hỏi | Trả lời |
|---|---|
| Module voice | `voice.js` + hands-free trong `app.js` + `/tts` trong `main.py`. Tái dùng 100%: hàng đợi TTS, tách câu, bậc thang lỗi, iOS unlock, `_cleanForTTS`. |
| Task/Kanban/nền | `tasks.py` + `task_store.py`, đã có báo về đúng khung chat qua frame `push`. Tái dùng 100%. |
| Event/WS | `/ws` với `ChatRuntime.publish`. Tái dùng 100%; chỉ cần THÊM loại frame, không thêm socket. |
| Routing agent/model | Ngoài phạm vi voice; không đụng. |
| MCP/tool | `mcp_hub` + `plugins_host`. Tái dùng 100%; app control và UI control đều đi bằng plugin/tool. |
| Memory | Không đụng (roadmap: không rewrite). |
| Frontend nav/state | `Alpine.store("nav").go`, ba cửa mở file, `showTask`. Có sẵn hàm, THIẾU giao thức để model gọi. |
| Boundary cần thêm | (a) orchestrator hội thoại (state machine) ở client, (b) một khối điều khiển UI mà model phát ra và server KHÔNG lột, (c) plugin điều khiển app cục bộ, (d) giao diện provider voice cho chế độ realtime. |

## 9. Bài học từ mã nguồn LiveKit (đọc 2026-09-14)

Nguồn: `livekit/agents` (Python, thư mục `livekit-agents/livekit/agents/voice/`) và `livekit/livekit` (Go, SFU).

**Về livekit/livekit (Go):** đó là SFU WebRTC (chuyển tiếp media nhiều người, simulcast, ước lượng băng thông).
Một người dùng nói với một server Python KHÔNG cần SFU; WebSocket thường chở PCM/Opus hai chiều là đủ. Cái
mất so với WebRTC là jitter buffer và che mất gói, còn khử vọng / lọc ồn / AGC vẫn lấy được từ `getUserMedia`
của trình duyệt, độc lập với transport. Kết luận: KHÔNG kéo LiveKit vào làm dependency, chỉ mượn thiết kế.

**Trạng thái và sự kiện** (`voice/events.py:291-310`): `UserState = speaking | listening | away`,
`AgentState = initializing | idle | listening | thinking | speaking`. Sự kiện: `user_state_changed,
agent_state_changed, user_input_transcribed, user_transcription_timeout, agent_false_interruption,
overlapping_speech, function_tools_executed, speech_created, tool_execution_updated, error, close`.

**Endpointing hai ngưỡng** (`voice/turn.py:131-143`): `min_delay 0.5 s`, `max_delay 3.0 s`. Mô hình đoán
hết lượt KHÔNG quyết định, chỉ chọn chờ ngắn hay chờ dài (`audio_recognition.py:1602-1606`). Bộ dò hết lượt
của LiveKit KHÔNG có tiếng Việt trong bảng ngưỡng (`inference/eot/languages.py:12-27`); ngôn ngữ không hỗ trợ
thì tắt mô hình, dùng VAD + độ trễ cố định. Với Javis: đi VAD + hai ngưỡng + luật cụm từ, không mơ mô hình EOT.

**Mọi đồng hồ neo vào mốc lùi**: đầu/cuối tiếng nói tính `now - speech_duration - inference_duration`, giấc ngủ
cuối là `delay + (last_speaking_time - now)` để độ trễ xử lý được hấp thụ chứ không cộng thêm
(`audio_recognition.py:1383, 1442, 1716`).

**Một task "bounce" duy nhất sở hữu việc chốt lượt**: mỗi sự kiện VAD/STT mới huỷ và tạo lại
`_end_of_turn_task`; không bao giờ chốt lượt rỗng (`:1506-1508, 1704-1716`).

**Chen ngang** (`voice/turn.py:145-190`): gác bằng thời lượng `min_duration 0.5 s` (tuỳ chọn `min_words`),
không phải khung VAD đầu tiên. TẠM DỪNG trước rồi mới giết: nếu sau `false_interruption_timeout 2.0 s` không có
chữ nào chốt thì phát tiếp và bắn `agent_false_interruption(resumed=True)` (`agent_activity.py:4842-4870`).
Bỏ qua chen ngang trong `aec_warmup 3.0 s` đầu của lượt nói; ân hạn 0.25 s ở đầu TTS
(`agent_session.py:116`, `endpointing.py:8`).

**Chỉ lưu vào lịch sử phần ĐÃ NGHE THẤY**: sink âm thanh báo `(playback_position, interrupted,
synchronized_transcript)` theo từng đoạn (`voice/io.py:111-120`), lịch sử ghi đúng tiền tố đã phát với cờ
`interrupted=True`, không nghe gì thì không ghi (`generation.py:690-765`).

**Đồng bộ chữ với tiếng**: tốc độ khởi điểm 3.83 âm tiết/giây rồi ước lượng lại theo thời lượng audio thật
(`transcription/synchronizer.py:22, 299-321`).

**Cắt câu đưa vào TTS sớm**: `min_sentence_len 20`, `stream_context_len 10` (`tokenize/basic.py:29-47`);
Javis đã làm gần giống ở `_splitForLatency`.

**Tool chạy lâu mà vẫn nói tiếp** (`voice/tool_executor.py:44-68, 299-320`): tool gọi `ctx.update("đang tìm...")`
là LLM được thả ngay với một thông điệp tổng hợp; prompt cấm bịa và cấm lặp; cập nhật sau gộp thành trả lời
trì hoãn. Filler "để mình xem" chỉ bắn khi phiên rảnh LIÊN TỤC đủ lâu (`filler_scheduler.py`). Với Javis: đây
chính là cầu nối Voice ↔ Kanban của Phase 2 (task nền = tool không chặn, frame `push` = trả lời trì hoãn).

**Khi không được phép chen ngang**: nạp im lặng cho STT nhưng vẫn nạp audio thật cho VAD
(`agent_activity.py:1644-1670`).

**Người dùng đi vắng**: `user_away_timeout 15 s`, không đếm khi có tool đang chạy (`agent_session.py:2015-2035`).

**Realtime OpenAI** (`plugins/openai/realtime/realtime_model.py`): 24 kHz mono, đẩy khung 100 ms;
`server_vad` mặc định `threshold 0.5, prefix_padding_ms 300, silence_duration_ms 200`; ngắt bằng
`response.cancel` + `conversation.item.truncate(audio_end_ms)`; nếu chưa nghe gì thì `conversation.item.delete`.
Khi realtime giữ quyền dò lượt thì client KHÔNG tự chen ngang cục bộ.

**Transport sau hai lớp trừu tượng** (`voice/io.py`): `AudioInput` / `AudioOutput`, phiên không biết gì về
room. Mặc định 24 kHz mono, khung vào 50 ms, khung TTS ra 200 ms, đệm audio 3 s trước khi kết nối xong để
không mất chữ đầu (`room_io/_pre_connect_audio.py`).
