# Gọi điện với Javis: ChatGPT Live

Ngày 01/10/2026. Chủ dự án đã duyệt thiết kế trong phiên cùng ngày. Đây là tài liệu thiết kế
DUY NHẤT cho giọng nói: các spec giọng nói cũ (Voice V1, V2, tai nghe lại, nhịp thích nghi, tập
trung, kiểm toán 24/09) đã gộp phần còn đúng vào Phụ lục A rồi xoá. Code trỏ về tài liệu này.

**Trạng thái: đã làm xong** cả ba bước của mục 6: ChatGPT Live ở 0.65.17, trải nghiệm gọi điện ở
0.65.18, trang cài đặt gọn ở 0.65.19. Còn treo một việc dọn dẹp: gỡ hẳn code nhịp thích nghi đã
tắt (Phụ lục A8).

## 1. Mục tiêu và các quyết định đã chốt

Người dùng muốn nói chuyện với Javis như gọi điện: nghe và nói cùng lúc, chen ngang lúc nào
cũng được, đáp gần như ngay, và phải cài đặt ít nhất có thể.

| Quyết định | Chốt |
|---|---|
| Bấm nút mic | **Gọi điện**: bấm một lần mở cuộc gọi, bấm lần nữa (hoặc Esc) là cúp |
| Màn hình lúc gọi | **Thanh gọi mỏng trên khung chat**, lời hai bên thành bong bóng chat thường |
| Ai trả lời | **Chia việc**: chuyện trò thì model nói chuyện đáp ngay; cần dữ liệu, MCP, file, ghi nhớ, mở trang thì giao bộ não Javis người dùng đã chọn |
| Đường chính | **ChatGPT Live** (Codex realtime, không cần API key) |
| Im lặng lâu | Im 20 giây thì **ngắt kết nối nghe**, gọi "Javis" là nối lại; thanh gọi vẫn giữ |
| Phím Space | **Bỏ** phím tắt nói. Chỉ còn nút mic, Esc để cúp |
| Giọng mặc định | **juniper** |
| Tên hiện ra | Chỉ ghi **ChatGPT Live** (nhãn, thông báo, CHANGELOG). Không dùng chữ "song công" ở chỗ người dùng đọc |
| Cài đặt | Trang chính còn 3 thứ; máy tự suy ra mọi thứ còn lại (mục 5) |
| Tai Claude | Không làm: model Claude không nhận âm thanh, giọng nói của Claude Code cần token claude.ai mà Javis không đọc |

## 2. Số đo làm căn cứ

**Nghe câu Việt pha tiếng Anh** (`tools/stt_bench`, 20 câu lệnh, giọng tổng hợp Edge TTS):

| Cách nghe | Từ sai | Thuật ngữ đúng | Lệnh đúng trọn | Thời gian |
|---|---|---|---|---|
| Chrome Web Speech thô | 41% | 11/42 | 4/20 | tức thì |
| Chrome rồi model sửa chữ | 23% | 28/42 | 11/20 | thêm 1 lượt model |
| Groq Whisper qua /stt (0.65.15) | 14% | 33/42 | 13/20 | 0,9 giây |
| ChatGPT realtime | 13% | 33/42 | 12/20 | chữ về 0,46 giây sau khi nói xong |
| Gemini nghe file qua agy | 5% | 39/42 | 17/20 | 7 đến 17 giây, loại |

Rào sửa chữ `safe_transcript_rewrite` chặn 9 trên 13 câu sửa đúng, và có câu Chrome làm mất hẳn
thông tin, nên sửa chữ sau khi nghe không phải đường chính.

**Thử ChatGPT Live** (Codex 0.153.4 và 0.159.3, 01/10, kịch bản giọng tổng hợp):
- Tiếng Việt tự nhiên, xưng hô đúng ("Dạ, em vẫn ổn anh ơi, cảm ơn anh").
- Tiếng đầu tiên của Javis ra **0,44 đến 0,85 giây** sau khi người dùng nói xong (lượt đầu ~2 giây).
- Handoff tới **0,5 giây** sau câu hỏi; trả kết quả bằng `appendSpeech`, model đọc gần nguyên văn.
- Chen ngang khi Javis đang kể chuyện: Javis dừng, đáp "Dạ vâng, em dừng đây ạ".
- Phiên 15 phút không rớt. Lỗi lẻ: câu đầu sau 3 phút im bị tách đôi ("Doanh" / "là bao nhiêu
  em") và chữ về trễ ~29 giây. Ngắt khi im 20 giây và ghép yêu cầu ngắn (mục 3.2) xử lý chuyện này.

## 3. Kiến trúc

### 3.1 Chọn đường gọi

Khoá `voice.call_engine` = `auto` (mặc định) | `chatgpt` | `api` | `basic`. `auto` chọn theo thứ tự:

1. **chatgpt**: đã nối ChatGPT (trang Models) và Codex chạy được realtime (dò một lần rồi nhớ).
2. **api**: Live qua API key hiện có (`voice.live_provider` gemini | openai | gpt-live), khi có key.
3. **basic**: đường dự phòng Cơ bản cho mọi máy, mọi bộ não (mục 3.6).

Chọn tay mà đường đó không chạy được thì rơi xuống đường kế tiếp và dòng "Đang dùng" nói rõ lý do,
giống `voice_ear.select_ear`.

### 3.2 Nhà cung cấp `codex-plan` (server)

Một lớp mới trong `server/voice_live.py`, cùng giao diện `LiveProvider`, KHÔNG cần key
(`make_provider` thêm nhánh không key).

**Tiến trình.** Một `codex -c features.realtime_conversation=true app-server` sống lâu cho cả máy
chủ (cờ bắt buộc với Codex trước 0.159, vô hại từ 0.159; Docker đang ghim 0.153.4). Tìm binary bằng
`claude_cli.find_codex_cli()`. Khuôn JSON-RPC theo `codex_models.list_models` (`initialize` với
`capabilities.experimentalApi = true`, từ chối mọi yêu cầu duyệt quyền server gửi về). Mỗi cuộc
gọi, và mỗi lần nối lại sau khi ngắt vì im lặng, mở một thread MỚI: dùng lại thread cho lần
`realtime/start` thứ hai thì ICE hỏng.

**Thread.** `thread/start {ephemeral: true, cwd: <thư mục tạm rỗng>, sandbox: "read-only",
approvalPolicy: "never", developerInstructions: "Reply only: [FINAL]"}`.

**Phiên realtime.** `thread/realtime/start`:
- `version: "v3"`, `outputModality: "audio"`, `transport: {type: "webrtc", sdp: <offer của trình duyệt>}`.
- `voice`: `voice.chatgpt_voice`, mặc định `juniper`. Danh sách hợp lệ của v3: juniper, maple,
  spruce, ember, vale, breeze, arbor, sol, cove (marin, alloy... bị từ chối).
- `prompt`: nhân cách Javis cho giọng nói (mục 3.3).
- `includeStartupContext: false`. BẮT BUỘC: mặc định Codex nhét ~5.300 token quét máy và thư mục
  làm việc vào prompt.
- `clientManagedHandoffs: true`, `delegationAckFiller: true`, `flushTranscriptTailOnSessionEnd: false`.
- `realtimeStartInstructions: "Do no work. Reply only: [FINAL]"`.
- `initialItems`: mục lục bộ nhớ (`memory/MEMORY.md`) và ~12 lượt chat gần nhất của phiên, trong
  trần 128 mục và 8.192 token.

Âm thanh đi THẲNG trình duyệt tới OpenAI. Máy chủ Javis chỉ chuyển gói bắt tay SDP, nên chạy được
cả khi Javis nằm trên VPS. Javis không bao giờ đọc token: app-server tự lo đăng nhập.

**Handoff về bộ não Javis.**
1. Sự kiện tới là `thread/realtime/itemAdded` với `item.type == "handoff_request"`, kèm
   `input_transcript`. Không có method riêng (khung `GPTLive` cũ đoán sai tên).
2. Yêu cầu quá ngắn (dưới 3 tiếng) thì ghép với lời người dùng vừa nói trong ~10 giây trước.
3. Phát `tool_call ask_javis` như các Live khác: `_voice_ask_javis` chạy nền, kèm khối ngữ cảnh
   giao diện, bằng bộ não chính người dùng đã chọn.
4. Codex luôn TỰ mở một lượt agent cho mỗi handoff (`turn/started`): gọi `turn/interrupt` ngay.
   `developerInstructions` ở trên là lưới đỡ khi interrupt thua cuộc đua.
5. Có kết quả: bản ĐẦY ĐỦ hiện thành bong bóng chat (bảng, link, file). Bản NÓI được rút từ đó
   (lột markdown, giữ số liệu, trần ~600 ký tự) rồi gửi `thread/realtime/appendSpeech`.

**Sự kiện dịch sang khung Live chung.** `sdp` thành `webrtc_answer`; `started` thành `ready`;
`transcript/delta|done` thành `transcript` (lời người dùng `done` là `final`); assistant `done`
thành `turn_done`; `error`/`closed` thành `error` (nối lại một lần rồi mới báo người dùng). Chen
ngang do chính model xử lý (VAD phía server): `interrupt` và `truncate_played` không làm gì.

### 3.3 Nhân cách giọng nói

Prompt riêng cho model nói chuyện, tiếng Việt, ngắn: nói như người qua điện thoại, 1 đến 2 câu;
XƯNG HÔ theo cách người dùng đang xưng (bộ nhớ trong `initialItems` cho biết), không ép cố định;
chuyện trò, giải thích kiến thức chung thì trả lời thẳng; MỌI câu cần dữ liệu thật hay hành động
(số liệu, đơn, lịch, email, file, mở trang, gửi tin, ghi nhớ) thì nói một câu đệm rồi giao việc,
không đoán; có kết quả thì đọc lại, không thêm số; bị chen ngang thì dừng và nghe.

### 3.4 Khung `/ws/voice-live` và trình duyệt

`/ws/voice-live` giữ vai kênh điều khiển, thêm chế độ WebRTC:
- `ready` mang `transport: "webrtc"` khi nhà cung cấp là `codex-plan`.
- Trình duyệt gửi `{type: "webrtc_offer", sdp}`, nhận `{type: "webrtc_answer", sdp}`.
- `transcript`, `tool`, `turn_done`, `error` giữ nguyên khuôn; thêm khung `handoff_result`
  (bản đầy đủ) để vẽ bong bóng kết quả.

`dashboard/voice-live.js` thêm nhánh WebRTC: `RTCPeerConnection` với transceiver audio
`sendrecv` lấy track mic (`echoCancellation`, `noiseSuppression`), kênh dữ liệu `oai-events`
(bắt buộc phải có trong offer), tiếng Javis phát qua một phần tử `<audio>`; mức âm hai phía cho
orb lấy từ analyser (track remote phải gắn vào một phần tử media thì mới chảy vào WebAudio). Bỏ
qua đường PCM của các Live khác. Điện thoại chạy được vì WebRTC chỉ dùng MỘT đường mic.

### 3.5 Tập trung khi im lặng

Im 20 giây (đếm từ lúc cả hai bên cùng im) thì `thread/realtime/stop`, đóng WebRTC, thanh gọi
chuyển sang "Đang chờ, gọi Javis để nói tiếp". Bộ nghe miễn phí của trình duyệt (`liveWake`, đã
có) chờ tên gọi; nghe thấy thì mở thread mới (~2 đến 3 giây) và gửi câu vừa nói làm lời đầu
(`appendText`). Lợi ích: tiếng TV không bị gửi đi, đỡ hạn mức, và tránh lỗi phiên ngồi im lâu.
Tắt "Tập trung" thì giữ kết nối suốt cuộc gọi.

### 3.6 Đường dự phòng `basic`

Cùng trải nghiệm gọi điện nhưng mỗi lúc chỉ một bên nói, cho máy không có Live: Web Speech làm nháp và điểm
dừng câu, tai nghe lại (Groq) chốt chữ, Làn nhanh nếu có bộ não giọng (không thì bộ não chính),
giọng Edge. Mic tự mở lại sau mỗi câu, ngắt lời bằng mẹo nhá tiếng (Phụ lục A2). Đây chính là
chế độ rảnh tay hiện nay, chỉ đổi vỏ.

## 4. Trải nghiệm gọi điện

- **Nút mic** đổi thành **Cúp máy** khi đang gọi. Esc cũng cúp. Phím Space không còn làm gì.
- **Thanh gọi** nằm ngay trên khung chat, ở mọi trang có khung chat (cả trang Trò chuyện):
  chấm trạng thái + chữ ("Đang nghe", "Javis đang nói", "Đang làm: <tên việc>", "Đang chờ, gọi
  Javis để nói tiếp", "Đang nối lại"), đồng hồ cuộc gọi, nút **Tắt mic** (`track.enabled =
  false`, Javis vẫn nói được) và nút **Cúp máy**.
- **Bong bóng**: lời người dùng hiện dạng nháp trong lúc nói rồi chốt; lời Javis chạy theo tiếng
  đọc; kết quả handoff là một bong bóng đầy đủ. Tất cả vào lịch sử phiên như tin thường.
- **Orb** (trang chủ) và linh vật vẫn theo trạng thái thật, vẽ qua `capNhatOrb()`.
- **Lỗi**: không nối được đường đang dùng thì báo một dòng và tự chuyển xuống đường kế tiếp trong
  mục 3.1, không bắt người dùng vào cài đặt.
- Gõ chữ trong lúc gọi vẫn được: chữ gửi vào cuộc gọi (`appendText`).

## 5. Trang cài đặt Giọng nói

```
GIỌNG NÓI
  Đang dùng: ChatGPT Live                            <- kèm lý do khi đang ở đường dự phòng
  Giọng Javis   [ juniper                 v ] [▶]    <- danh sách đổi theo đường gọi
  Tập trung khi đàm thoại                    [on]
    Im 20 giây thì phải gọi "Javis" mới nghe tiếp
  > Nâng cao
      Đường gọi      [ Tự động v ]  (Tự động / ChatGPT Live / Live API key / Cơ bản)
      Tốc độ đọc     [ 1,10x  v ]   (chỉ đường Cơ bản)
      ElevenLabs     key + Voice ID (chỉ khi chọn giọng ElevenLabs)
```

- **Mọi ô tự lưu khi đổi**, không còn nút Lưu. Xếp một cột.
- **Giọng Javis**: đường chatgpt hiện 9 giọng v3, "Nghe thử" phát mẫu thu sẵn
  (`dashboard/voices/<giọng>.mp3`, vài chục KB mỗi giọng); đường api hiện giọng của nhà cung
  cấp đó; đường basic hiện giọng Edge, giọng OpenAI khi đã có key ở trang Models, và giọng
  ElevenLabs riêng (key và Voice ID ở Nâng cao). Ở đường basic, chọn giọng là chọn luôn nhà
  cung cấp giọng đọc.
- **Bỏ khỏi giao diện, máy tự lo**: đọc trả lời bằng giọng (trùng nút mic), nhịp hội thoại thử
  nghiệm (gỡ hẳn ô nhập; code điều khiển ép tắt, chờ PR dọn riêng), từ hay nghe nhầm (tự lấy tên trợ lý và tên kết nối MCP), ô
  API key OpenAI (ở trang Models), ngôn ngữ nghe (theo ngôn ngữ giao diện), im lặng rồi gửi (mặc
  định 1,2 giây), ngắt lời bằng giọng (luôn bật), tai nghe lại (luôn tự chọn), bộ não giọng (bộ não
  đầu tiên sẵn trên gói), khoá chết `loc_tap_am`, khoá cũ `stt_provider`.
- **Giữ dữ liệu cũ**: giá trị người dùng đã lưu ở các ô bị bỏ vẫn được đọc và dùng tiếp (ví dụ từ
  đã khai ở hotwords vẫn vào từ mồi); chỉ ô nhập biến mất. Khoá mới không đè khoá cũ.
- Cập nhật allowlist `POST /settings` (nhánh `voice`) và `test_luu_cai_dat_giong.py` cùng lúc.
- **Bộ não giọng tự chọn** (`voice_brain.auto_brain`): Làn nhanh mà khoá `brain_provider` rỗng thì
  dùng bộ não đầu tiên sẵn trên gói theo thứ tự antigravity, codex, claude, grok (dò binary và
  token đã lưu, không hỏi mạng, nhớ 60 giây). Không có cái nào thì tin từ mic đi bộ não chính.
  Khoá cũ `mode = live` tính như Làn nhanh vì Live nay là đường gọi riêng.
- Thẻ đọc `GET /voice/options?brains=0`: bỏ danh sách bộ não nên không chạy `agy models` (có khi
  tới 30 giây); trả thêm `call` (đường gọi), `tts` (giọng đọc đường basic) và `voice_brain`.

## 6. Thứ tự làm (mỗi bước một PR, đặt số phiên bản trước theo `docs/quy-uoc-dev.md`)

1. **ChatGPT Live**: nhà cung cấp `codex-plan`, khung WebRTC trên `/ws/voice-live`, nhánh
   WebRTC trong `voice-live.js`, handoff về bộ não Javis + bong bóng kết quả, ngắt khi im 20 giây,
   giọng juniper, mẫu thu sẵn 9 giọng. Chọn được trong ô nhà cung cấp Live hiện có.
2. **Trải nghiệm gọi điện cho mọi đường**: thanh gọi, nút Cúp máy, Tắt mic, bỏ Space, chọn đường
   gọi tự động (mục 3.1), đường basic dùng vỏ mới.
3. **Gọn trang cài đặt** như mục 5, gỡ nhịp thích nghi khỏi giao diện.

## 7. Kiểm thử

- **Python** (app-server giả qua `popen_factory`): khuôn `thread/start` và `realtime/start` (có
  `includeStartupContext: false`, cờ feature, giọng mặc định juniper); handoff thành `tool_call`
  với yêu cầu ghép khi quá ngắn; `turn/started` bị interrupt; kết quả đi `appendSpeech` đã rút gọn
  và bong bóng đầy đủ; từ chối yêu cầu duyệt quyền; nối lại một lần khi `closed`; chọn đường gọi.
- **JS** (node): nhánh WebRTC tạo offer có `oai-events`, đặt answer, không phát PCM; thanh gọi
  theo trạng thái; Esc cúp, Space không làm gì; im 20 giây thì ngắt và `liveWake` nối lại; trang
  cài đặt tự lưu và không còn các ô đã bỏ.
- **Thử thật**: máy tính và điện thoại (Android Chrome, iPhone Safari): chuyện trò, hỏi số liệu
  (handoff), mở trang, chen ngang, im quá 20 giây rồi gọi lại, cuộc gọi 15 phút.
- **Bộ đo**: `tools/stt_bench` cho phần nghe; bộ thử trong scratchpad của phiên 01/10
  (`spike_live.py`) là mẫu cho một runner Live sau này.

## 8. Rủi ro

- **API realtime của Codex là bản thử nghiệm**: dò khả năng khi mở cuộc gọi, hỏng thì tự xuống
  đường kế tiếp và báo lý do. Bám bản Codex mới (0.159 đã ổn định cờ realtime).
- **Hạn mức gói ChatGPT**: cả cuộc gọi lẫn mỗi lượt Codex bị interrupt đều tính vào hạn mức. Chủ
  dự án chấp nhận. Ngắt khi im 20 giây giảm đáng kể.
- **Điều khoản dùng gói**: OpenAI chưa nói rõ giới hạn cho cách dùng này. Một người ngồi gọi thì
  gần với dùng cá nhân thường; nhiều người dùng chung một gói qua cùng một Javis thì nằm ngoài
  cách dùng cá nhân, giống lưu ý trong CLAUDE.md về gói Claude và gói xAI. Đừng hứa suông.
- **Giọng và tính cách lớp ngoài là của OpenAI**: bộ não người dùng chọn chỉ làm phần việc phía
  sau. Ai muốn giọng khác thì ép đường gọi sang Cơ bản.
- **Riêng tư**: âm thanh đi tới OpenAI suốt lúc nghe. Ngắt khi im lặng và tắt mic giới hạn
  phần này; `includeStartupContext` luôn tắt để không lộ thông tin máy.

## Phụ lục A. Các lớp giọng nói đang chạy

Rút từ các spec cũ (Voice V1, V2, tai nghe lại, nhịp thích nghi, tập trung, kiểm toán 24/09), chỉ
giữ phần đã đối chiếu đúng với code ngày 01/10/2026. Code trỏ về các mục dưới đây.

### A1. Đạo diễn lượt nói (voice-turn.js) và trạng thái orb
- Module thuần, không đụng DOM hay audio. voice.js và app.js gửi sự kiện vào, nhận về một MẢNG hành động (`commit`, `hold`, `stop_tts`, `stop_turn`, `pause_tts`, `resume_tts`, `listen`, `speak_filler`, `flush_deferred`) rồi tự thực hiện.
- Trạng thái suy ra từ cờ theo một danh sách ưu tiên (`_recompute`): reconnecting, error, interrupted, user_speaking, waiting_for_user, speaking, processing, listening, idle. Thêm trạng thái thì thêm vào danh sách này, không viết tay từng cặp chuyển.
- Chờ hết lượt theo hai ngưỡng, một đồng hồ duy nhất, có lời mới thì đặt lại. Câu kết bằng liên từ, giới từ, dấu phẩy, tiếng ậm ừ ("ừm", "ờ", "kiểu") hoặc chỉ gọi "Javis" thì chờ `maxDelay` 2200 ms; còn lại chờ `minDelay` 1200 ms (`javis.endpoint`). Không bao giờ chốt lượt rỗng. Không có "à" trong danh sách vì "vậy à" là câu đã xong. Không dùng mô hình dò hết lượt vì LiveKit không hỗ trợ tiếng Việt.
- Cụm CHỜ/DỪNG phải khớp trọn câu sau khi bỏ "Javis ơi" và tiểu từ đuôi; bản nói lắp vẫn nhận nếu mọi từ thuộc bộ từ vựng; câu có từ lạ ("khoan, mở Chrome") là tin thường. CHỜ thì không gửi và giữ tối đa 90 giây. DỪNG thì dừng đọc và dừng lượt đang chạy.
- Câu tiến độ: đang xử lý quá 2,5 giây (đang gọi tool thì 1,2 giây) mà chưa có chữ thật nào ra loa thì nói đúng một lần mỗi lượt.
- Tin nền (frame `push`) chỉ đọc khi ở `idle`/`listening`, trạng thái khác thì hoãn; chữ vẫn hiện ngay.
- Orb chỉ hiện trạng thái thật lấy từ đạo diễn (`ORB_LABEL` trong app.js), chỉ vẽ qua `capNhatOrb()`. Hậu tố MẠNG CHẬM chỉ hiện khi khúc TTS mất hơn 2500 ms mới phát.

### A2. Tai và miệng ở trình duyệt (voice.js, voice-chunker.js)
- Web Speech thu mic bằng luồng riêng, không được khử vọng, nên phải ngừng nhận dạng khi TTS phát, không thì nó chép giọng Javis thành lời người dùng. Cũng vì thế cố ý không làm tiếng đệm "ừ, à".
- Ngắt lời bằng NHÁ TIẾNG: 2 nhịp 100 ms vượt ngưỡng chỉ là nghi ngờ; hạ loa còn 12% trong 4 nhịp rồi đo lại, tiếng vọng tụt theo âm lượng còn giọng người thì không (còn trên 45%). Là người thì `bargeConfirmed` dừng hẳn lời đọc lẫn lượt đang chạy, không chờ chữ. Mức vọng của phòng tự học, lưu `javis.nenVong`, chặn trên 0.3.
- Điện thoại chỉ cho MỘT đường thu mic: mobile không ghi âm song song và không có tai nghe lại ở đường Web Speech. WebRTC (mục 3.4) dùng đúng một đường nên chạy được.
- Chrome Android giao final là cả câu và còn sửa câu giữa các mảnh: ghép bằng `ghepManh`, không `+=`. iOS ép `continuous=false` và hay không chốt final (ghép `_duoiTam`). Mỗi lượt tối đa 30 giây.
- Chữ đã hiện lúc chốt là bất biến: final đến muộn, STT phụ hay AI đều không được sửa âm thầm. Stop trước khi có kết quả nào thì nhận final đầu tiên.
- TTS Edge stream byte ngay; khúc đầu lấy trước khi trả response để lỗi thành 502 thật. Khúc lỗi thì thử lại cùng giọng một lần rồi báo, không đổi nhà cung cấp, không chuyển sang giọng của thiết bị. Epoch chặn callback audio cũ. Emma Multilingual là giọng Edge mặc định.
- voice-chunker.js cho mọi làn: cụm đầu cắt sớm (6 từ có phẩy hoặc liên từ, hoặc đủ 12 từ), cụm sau cắt ở hết câu hoặc quá 220 ký tự; im 400 ms thì chỉ đẩy cụm khi loa đang im. Không đọc từng mẩu stream vì mỗi cụm là một yêu cầu TTS. Bỏ khối mã, dừng ở `<!--`. Không có "so"/"or" trong danh sách liên từ.

### A3. Làn nhanh: bộ não giọng (voice_brain.py)
- Tin mang `voice: true` (kể cả chữ gõ lúc rảnh tay) đi bộ não giọng. Mọi bộ não chỉ cần hợp đồng `stream(text, history)`, tự đóng sau 5 phút không nói.
- Bốn marker không bao giờ ra loa: `JAVIS_NGHE`, `JAVIS_ASK_MAIN`, `JAVIS_UI`, `JAVIS_BO_QUA` (cái cuối chỉ còn là di sản: prompt cấm dùng, không còn xoá lời).
- Thiếu `JAVIS_NGHE`, hoặc câu diễn giải bị `safe_transcript_rewrite` từ chối (ngưỡng âm 0,6, tối đa 4 tiếng một cụm, không đụng số, phủ định hay lệnh), thì bộ não chính nhận nguyên văn kèm `GHI_CHU_CAU_NGHE`.
- `JAVIS_ASK_MAIN`: lượt giọng kết thúc ngay, việc chạy nền dưới khoá `voice:<sid>:<id>`. Task phải được giữ tham chiếu (`_nho_viec_nen_giong`) kẻo bộ gom rác nuốt. Chặn việc trùng (độ giống từ 0,8), tối đa 3 việc song song. "Dừng việc nền" là luật cứng trong code, không thành việc mới.
- `JAVIS_UI` không đánh thức bộ não chính (lượt đó có lúc mang hơn 200 nghìn token ngữ cảnh).
- `MODES`, `BRAIN_PROVIDERS`, `STT_PROVIDERS` là nguồn duy nhất cho cả trang Cài đặt lẫn nhánh lưu `POST /settings`.
- Lớp sửa tên tất định `nghe_sua.sua` ("David" thành "Javis") chạy trước khi lưu; gỡ nó thì Javis đáp "anh nói là David".

### A4. Tai nghe lại (voice_ear.py, stt.py, nghe_sua.py)
- `voice.ear` = auto | groq | off, CỐ Ý không có mặc định trong config.py; khoá cũ `stt_provider: "groq"` vẫn tính là chọn tay.
- `transcribe_upload`: Groq Whisper, `loc_ao_giac`, `nghe_sua.sua`, rồi `khop_ban_nhap` (chống bịa: lệch bản nháp thì giữ bản nháp). Tên kết nối MCP chỉ làm mồi cho Whisper, không vào lớp sửa mờ.
- Chỉ tải lên khi bản ghi phủ hết cả lượt; không lấy độ dài làm bằng chứng bản nào đúng. Lượt đầu sau khi tải trang chờ luồng mic rồi mới mở nhận dạng.
- `loc_ao_giac` cắt câu outro YouTube do Whisper bịa, xét theo từng câu; thà sót một câu bịa còn hơn nuốt lời thật. Gặp mẫu bịa mới thì thêm mẫu VÀ thêm một câu thật gần giống vào test.
- Số đo và các đường đã loại: mục 1 và mục 2. Codex realtime: mục 3.2.

### A5. Live qua API key (voice_live.py, voice-live.js)
- Trình duyệt gửi PCM16 16 kHz, nhận 24 kHz. Nhà cung cấp mới chỉ cần một lớp con `LiveProvider`.
- `ask_javis` chạy nền. Gemini 3.1 Flash Live (mặc định) chưa có tool bất đồng bộ nên model im chờ; OpenAI Realtime phải xếp `response.create` chờ tới `response.done`.
- Ngắt lời: trình duyệt gửi `played` (số ms thực đã phát) để server cắt ngữ cảnh đúng chỗ đã nghe. Gemini phải chờ `setupComplete` trước khi gửi PCM; transcript người dùng tách khỏi `turnComplete` của model.
- `generation` sở hữu socket và callback của từng phiên. GPT-Live chưa chạy thật lần nào, và đoán sai tên khung delegation (mục 3.2).

### A6. Điều khiển giao diện bằng giọng (ui_bridge.py, plugin javis-ui, desktop-apps)
- Điều khiển đi bằng TOOL, không bằng khối chữ trong câu trả lời: server lột mọi `JAVIS_*`, không có đường báo kết quả về, và Telegram sẽ thấy rác.
- `ui_bridge.request` gửi `ui_action` tới các tab và chờ `ui_result`; không có tab thì báo lỗi ngay, quá 4 giây thì hết giờ. Dashboard kiểm lại target trước khi chạy.
- Trang mới phải thêm ở BA nơi: `RAIL_ITEMS` (console.js), `PAGES` (ui-actions.js), `PAGES` cùng bí danh không dấu trong `server/ui_targets.py`. Nhóm thanh bên dùng khoá `id` vì nhãn đổi theo ngôn ngữ.
- desktop-apps: mở và đóng làm ngay không hỏi lại (chủ dự án chọn). Đóng mặc định là đóng lịch sự để app tự hỏi lưu; `force` chỉ khi người dùng nói ép tắt. Tự chặn khi chạy trong Docker hay Linux không màn hình.
- Khối `[NGỮ CẢNH GIAO DIỆN: ...]` bị lột khỏi bong bóng và tiêu đề; `kênh=giọng` yêu cầu trả lời 2 đến 4 câu. Đường tắt `JAVIS_UI` chỉ có `open_page`, `open_group`, `sidebar`, `scroll`; `open_file` và `open_task` chỉ có ở tool `javis_ui`.

### A7. Chế độ tập trung (voice-attention.js, focus_mode)
- Đây là cửa chú ý, KHÔNG phải nhận diện người nói. Bấm mic là mở hội thoại; sau 20 giây không có lượt nào được nhận thì phải gọi "Javis", và tên gọi phải có trong bản final.
- `focus_mode` mặc định bật. Không xoá lời đã nhận dựa trên việc đoán tạp âm từ chữ.
- Câu mở đầu gần giống tên gọi ("David ơi") không mở cửa, chỉ được đưa cho tai nghe lại.
- Live khi đang chờ: đóng kết nối, gửi câu gọi đúng một lần sau `ready`, nạp lại tối đa 12 tin hoặc 8.000 ký tự.
- Giới hạn đã biết: TV nói "Javis" vẫn đánh thức được.

### A8. Nhịp hội thoại thích nghi (đã gỡ khỏi giao diện ở 0.65.19, code còn chờ dọn)
- Từng bật qua `javis.adaptive` (off | observe | natural). Từ 0.65.19 `voice-adaptive-ui.js` ép `off`, bỏ qua giá trị đã lưu, và không còn ô nào trên trang; code điều khiển (`voice-adaptive.js`, nhánh `adaptive` trong `app.js`) chờ một PR gỡ hẳn.
- Biên nhận SQLite (`voice_turn_protocol.py`) bảo đảm gửi lại không làm chạy lại hành động. `ack_only` (ghi nhận mà không trả lời) rất hẹp: chưa chắc thì trả lời bình thường.
- Khi gỡ giao diện phải giữ hai bảo đảm: chữ đã chốt là bất biến, và epoch chặn callback cũ.

## Phụ lục B. Luật đang có test canh

- `test_voice_turn.js`: máy trạng thái, chờ hai ngưỡng, CHỜ/DỪNG, chen ngang, hoãn tin nền.
- `test_orb_trang_thai_that.js`, `test_ngat_loi_nha_tieng.js`: orb chỉ đi qua đạo diễn; hằng số nhá tiếng, `bargeMinTicks = 2`.
- `test_mic_dien_thoai_mot_duong_thu.js`: một đường thu mic trên điện thoại. `test_mic_doc_chong_va_loa_theo_mic.js`: không cộng dồn mảnh trên Android. `test_mic_khong_tu_gui.js`: mic không tự gửi tiếng động.
- `test_voice_capture_lifecycle.js`, `test_voice_app_session.js`: bản ghi phủ hết lượt, thứ tự STT, final muộn, đổi chat.
- `test_voice_chunker.js`, `test_voice_v3_mot_luong.js`, `test_voice_v2_day_noi.js`: cắt cụm và dây nối.
- `test_ui_actions.js`: ba danh sách trang và hai danh sách nhóm phải khớp. `test_ui_bridge.py`, `test_desktop_apps_plugin.py`, `test_channel_ui_prompt.py`, `test_ui_context.js`: điều khiển giao diện và khối ngữ cảnh.
- `test_tts_stream.py`: Edge stream, lỗi ngay thành 502. `test_voice_privacy.py`: query `/tts` không vào log.
- `test_luu_cai_dat_giong.py`: lưu rồi đọc lại cài đặt giọng (bẫy: phải dùng `base_url=http://127.0.0.1:7777`, không thì 403).
- `test_stt_ao_giac.py`, `test_stt_route.py`, `test_voice_ear_select.py`, `test_voice_ear_upload.js`: tai nghe lại.
- `test_voice_brain.py`, `test_voice_transcript_integrity.py`, `test_voice_turn_integrity.py`, `test_voice_ten_javis.py`, `test_nghe_sua.py`, `test_voice_tap_am.py`: marker, rào `JAVIS_NGHE`, sửa tên Javis.
- `test_viec_nen_giong_khong_chet_lang.py`, `test_viec_nen_giong_dung_khung_chat.py`: việc nền giữ tham chiếu, báo về đúng khung chat.
- `test_voice_attention.js`, `test_voice_focus_app.js`, `test_voice_live_focus.py`: tập trung.
- `test_voice_live.py`, `test_voice_live_transcription.py`, `test_voice_live_language.py`, `test_voice_live_lifecycle.js`: Live.
- `test_voice_adaptive*.js`, `test_voice_turn_protocol.py`, `test_voice_protocol_ws.py`: nhịp thích nghi và biên nhận.
- `test_route_table.py`: thêm hay đổi route thì chụp lại bảng (`--update`) trong cùng commit.
