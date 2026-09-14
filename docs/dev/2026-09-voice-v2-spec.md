# Voice V2 - bộ não giọng nói riêng, nghe bằng Groq, nghe nói thẳng (Live)

> Viết 2026-09-14 trên nền v0.56.0 (Voice V1). Chủ dự án chốt: làm cả hai bậc; ưu tiên gói
> subscription (Antigravity) cho bộ não giọng; gom Groq đã có cho phần nghe; nhà cung cấp
> nghe nói thẳng phải đổi được như đổi model.

## 1. Số đo làm nền cho thiết kế

Đo trên máy chủ dự án 2026-09-14 với `agy` 1.2.2, model `gemini-3.8-flash-low`:

- mỗi tiến trình mới: chữ đầu về sau 4,2 s (2,6 s là khởi động tiến trình), model mặc định 8-9 s;
- MỘT tiến trình sống lâu (`--input-format stream-json`, mỗi lượt một dòng
  `{"event":"user","message":{"role":"user","content":"..."}}`): lượt 2 trở đi chữ đầu 1,3-2,0 s,
  giữ ngữ cảnh, và stream từng mảnh (`step_update.text_delta`).

Kết luận: bộ não giọng trên gói Antigravity khả thi ở mức tiếng đầu ~2 s nếu giữ tiến trình
sống suốt phiên nói. API Groq/Gemini còn nhanh hơn (0,5-0,8 s) cho ai có key.

## 2. Ba chế độ, một trang cài đặt

`settings.voice` thêm: `mode` (standard | fast | live), `brain_provider` ("" = bộ não chính |
antigravity | groq | gemini | openai | openrouter), `brain_model`, `stt_provider` (browser |
groq), `stt_model`, `live_provider` (gemini | openai), `live_model`, `live_voice`. Trang Cài đặt
→ nhóm Giọng nói thêm thẻ "Chế độ và bộ não giọng nói". Key dùng lại của trang Models.

- **Chuẩn**: đúng Voice V1.
- **Làn nhanh (fast)**: tin đến từ mic (`voice: true` trong khung WS) đi qua `voice_brain.py`
  thay vì bộ não chính. Bộ não giọng trả lời ngắn; câu nào cần dữ liệu, tool, file, ký ức hay
  hành động thì nó trả đúng một dòng `JAVIS_ASK_MAIN: <yêu cầu>` (được phép có một câu chờ
  trước đó). Server đọc dòng đó, đọc câu chờ ra loa, rồi chạy lượt bộ não chính như thường
  trong CÙNG phiên. Mọi thứ đều ghi vào kho phiên, gõ chữ hay nói đều một mạch.
- **Live**: trình duyệt mở `/ws/voice-live`, đẩy PCM16 16 kHz; server nối tới nhà cung cấp
  (`voice_live.py`: Gemini Live hoặc OpenAI Realtime) và trả PCM16 24 kHz về. Ngắt lời do nhà
  cung cấp dò; server báo `interrupted` để trình duyệt xả hàng đợi phát. Model có tool
  `ask_javis` gọi bộ não chính. Bản ghi chữ hai chiều hiện trong khung chat và lưu vào phiên.

## 3. Nghe bằng Groq

`stt_provider: groq`: voice.js ghi MediaRecorder (webm/opus) song song với Web Speech; Web
Speech vẫn cho chữ tạm và điểm dừng câu; hết câu thì gửi file lên `POST /stt` (Groq Whisper
qua `stt.groq_nghe`, key `model.groq_api_key`), chữ Groq thay chữ Chrome; Groq lỗi thì dùng chữ
Chrome. Không thêm độ trễ đáng kể vì ghi âm chạy song song và file chỉ vài trăm KB.

## 4. Giao diện nhà cung cấp Live

`LiveProvider`: `connect()`, `send_audio(pcm16_16k)`, `send_text()`, `send_tool_result()`,
`interrupt()`, `close()`, `events()` trả sự kiện chuẩn hoá: `audio` (bytes 24 kHz), `interrupted`,
`transcript` (role, text, final), `tool_call` (id, name, args), `turn_done`, `error`. Thêm nhà
cung cấp = thêm một lớp, không đụng route hay trình duyệt. Tên model mặc định để trong cài đặt vì
Google và OpenAI đổi tên liên tục.

## 5. An toàn và giới hạn

- Tiến trình `agy` sống lâu đóng sau 5 phút không nói; chết thì mở lại và mồi lại 10 lượt gần
  nhất từ kho phiên. Chỉ mở khi có người đang nói, không phải chạy nền 24/7.
- Bộ não giọng không có tool ngoài `JAVIS_ASK_MAIN`; hành động ra ngoài vẫn qua bộ não chính.
- Live chỉ bật được khi có key của nhà cung cấp; thiếu thì trang cài đặt nói rõ.
- Ngoài phạm vi: wake word khi mic tắt, STT streaming server, TTS có cảm xúc ngoài các provider
  đã có.

## 6. Sau khi so với GPT-Live (0.57.1, cùng ngày)

Đọc bài giới thiệu GPT-Live (OpenAI, 07/2026) và tài liệu API (09/2026): hai ý lớn là song công
toàn phần (model tự quyết nghe/nói/ngắt) và ủy nhiệm việc nặng cho model nền TRONG LÚC vẫn trò
chuyện. Javis đã có ý thứ hai (`ask_javis`, `JAVIS_ASK_MAIN`) nhưng route Live `await` tool ngay
trong vòng đọc sự kiện nên cuộc nói chuyện đứng im 5 đến 30 giây. Sửa:

- `ask_javis` chạy thành task nền (`_run_tool` trong route), vòng đọc sự kiện không dừng. Gemini
  2.5 Flash Live khai báo tool `behavior: NON_BLOCKING`, kết quả `scheduling: WHEN_IDLE`; Gemini
  3.1 Flash Live CHƯA hỗ trợ tool bất đồng bộ (tài liệu Google) nên model im chờ, nhưng audio vẫn
  chảy. OpenAI Realtime: kết quả tool về khi model đang nói thì `response.create` xếp hàng tới
  `response.done`.
- Ngữ cảnh giao diện: trình duyệt gửi khung `context` (cùng khối `[NGỮ CẢNH GIAO DIỆN: ...]` của
  V1, chỉ khi đổi, dò 1,5 s một lần); server kèm vào yêu cầu gửi bộ não chính và đẩy vào kênh
  im lặng của hãng nếu có (GPT-Live `session.thinking.append`).
- Ngắt lời: trình duyệt đo số ms đã phát của câu đang nói, gửi khung `played`; OpenAI Realtime
  nhận `conversation.item.truncate` để ngữ cảnh chỉ giữ phần đã nghe (nguyên tắc V1).
- Gemini: `sessionResumption` + `contextWindowCompression` trong setup; nhận `goAway` thì route nối
  lại ngay bằng handle cũ, trình duyệt chỉ thấy khung `reconnected`.
- Nhà cung cấp thứ ba `gpt-live` (`wss://api.openai.com/v1/live/sessions`, `session.start`, ủy nhiệm
  `client`): `session.delegation.created` -> chạy bộ não chính với câu người dùng vừa nói ->
  `session.commentary.append`. Không có sự kiện interrupted/turn_done, suy ra từ transcript. Khuôn
  sự kiện lấy từ SDK openai 3.13. CHƯA chạy thật (máy dev không có key).

## 7. Làn nhanh nghe giật (0.57.2)

Triệu chứng: nói chuyện ở làn nhanh (Antigravity) nghe giật, cắt từng mẩu, orb hay báo MẠNG CHẬM.
Nguyên nhân gốc: `_flush` trong `run_voice_turn` đẩy MỖI delta stream (vài từ) thành một khung
`stream`, và `app.js` gọi `voice.enqueueSpeak` cho mỗi khung, mỗi khung là một yêu cầu Edge TTS
riêng (0,5 đến 2 giây chờ mỗi cái); giữa hai khung không tải trước gì. Sửa hai tầng:
- server: `voice_brain.split_speakable(text, start, final)` (hàm thuần, có test) chỉ trả phần ĐỌC
  ĐƯỢC: câu đã khép, dòng đã khép, hoặc đoạn dở dài quá `SPEAK_MAX` cắt ở dấu phẩy; marker vẫn
  không ra loa.
- trình duyệt: `voice.js` tải trước câu KẾ trong hàng đợi khi đang ở khúc cuối câu hiện tại
  (`_preloadNextQueued`), preload khớp theo URL thay vì index.

## 8. Bấm Lưu báo xong mà F5 là mất (0.57.3)

Triệu chứng: trang Cài đặt chọn Làn nhanh + bộ não giọng, bấm Lưu, nút hiện "Đã lưu", tải lại
trang thì về giá trị cũ.

Nguyên nhân gốc: nhánh `voice` của `POST /settings` dùng ALLOWLIST TỪNG KEY và chỉ liệt kê các ô
TTS cũ. Bảy ô Voice V2 (`mode`, `brain_provider`, `brain_model`, `stt_provider`, `live_provider`,
`live_model`, `live_voice`) không có tên trong đó nên bị bỏ im lặng, endpoint vẫn trả
`{"ok": true}`. Giá trị đang có trong `settings.json` của máy dev là do viết tay lúc phát triển,
nên đường lưu chưa từng chạy đúng lần nào. Chính comment ở nhánh `locale` đã cảnh báo đúng bẫy này.

Sửa:
- `voice_brain.MODES / BRAIN_PROVIDERS / STT_PROVIDERS` là NGUỒN DUY NHẤT cho các ô chọn;
  `GET /voice/options` vẽ từ đó và nhánh lưu cũng nhận đúng từ đó, không còn hai danh sách song
  song. `_make` và `config_from_settings` cũng lấy `key_field` và `default_model` từ đây.
- `tests/python/test_luu_cai_dat_giong.py`: vòng tròn lưu rồi đọc lại qua TestClient, cộng một
  chốt chặn đọc khối `data` của nút Lưu trong `console.js` và bắt lỗi nếu có key nào nhánh voice
  của `main.py` chưa xử lý. Thêm ô mới mà quên server là test đỏ ngay.
- BẪY khi viết test: rào chống DNS-rebinding trả 403 cho host `testserver` mặc định của
  TestClient, phải đặt `base_url="http://127.0.0.1:7777"`, không thì 403 che mất lỗi thật.

## 9. Whisper bịa câu đăng ký kênh YouTube (0.57.4)

Triệu chứng: đang nói chuyện bằng giọng thì trong khung chat hiện một tin của NGƯỜI DÙNG với nội
dung "Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn ...", và Javis trả
lời câu đó một cách nghiêm túc.

Nguyên nhân gốc: không phải lỗi Javis, mà là ảo giác kinh điển của Whisper. Whisper học chủ yếu
từ phụ đề YouTube nên khi audio là im lặng, tiếng ồn nền hay một đoạn ngắn không rõ, nó sinh ra
câu outro dày đặc nhất trong dữ liệu học. Đường đi: `voice.js` ghi song song với Web Speech, hết
câu thì đẩy file lên `POST /stt`, và chữ Whisper THAY chữ Chrome (`cb(better || text)`), nên câu
bịa ghi đè lên câu nghe đúng. Không có tầng nào lọc, và vì không phải lỗi mạng nên không có gì
báo.

Sửa: `stt.loc_ao_giac(text)` trong `server/stt.py`, gọi ngay trong `groq_nghe` nên mọi kênh
(dashboard, Telegram, Zalo) dùng chung. Cắt THEO TỪNG CÂU vì Whisper hay dán câu bịa vào trước
lời thật; lọc xong rỗng thì trả `khong_nghe_ro` để `voice.js` giữ chữ Web Speech.

Ranh giới cố ý: mẫu chỉ bắt dấu hiệu riêng của câu outro (tên kênh, "subscribe cho kênh", "không
bỏ lỡ ... video"). Người dùng bàn chuyện marketing hằng ngày, nên thà sót một câu bịa còn hơn
nuốt một câu nói thật. `tests/python/test_stt_ao_giac.py` canh cả hai phía: cắt đúng câu bịa VÀ
giữ nguyên bảy câu nói thật dễ bị bắt nhầm.

## 10. Dọn ảo giác cũ, mở nhóm thanh bên, bỏ bộ não chính khỏi lệnh giao diện (0.57.5)

Ba việc chủ dự án nêu cùng lúc.

**a. Ảo giác đã lỡ vào kho.** Bộ lọc 0.57.4 chỉ chặn từ lúc nghe trở đi. `tools/don_ao_giac_stt.py`
quét lại `messages` (chỉ `role='user'`) bằng ĐÚNG `stt.loc_ao_giac`: tin chỉ toàn câu bịa thì xoá,
tin lẫn lời thật thì cắt phần bịa. Mặc định chỉ XEM, có `--xoa` mới sửa và luôn sao lưu DB trước.
Chạy thật trên máy chủ dự án: xoá 4, cắt 12.

Chạy thử lần đầu lộ ra ba lỗi THẬT của bộ lọc, sửa hết trước khi ghi:
- Cắt câu rồi nối bằng khoảng trắng làm hỏng `README.md` thành `README. md` và mọi URL, dù không
  có câu bịa nào. Nay ghép lại nguyên văn từng đoạn giữ lại (104 tin suýt bị sửa oan).
- Câu bịa dính ĐUÔI lời thật mà không có dấu chấm ngăn thì vứt cả câu là mất luôn lời người ta
  nói. Nay giữ hai đầu nếu còn từ 4 chữ trở lên.
- Người dùng TRÍCH DẪN chính câu bịa ("anh thấy có cái câu là các bạn đã đăng ký kênh ủng hộ
  mình, anh không nói câu đấy") thì bị cắt nát. Nay câu bịa nằm giữa mà hai đầu đều ra hồn thì
  giữ nguyên cả câu.
Thêm: `finditer` thay `search` (Whisper lặp câu bịa vài lần trong một câu), xuống dòng cũng là
ranh giới câu (không thì khối `[NGỮ CẢNH GIAO DIỆN: ...]` bị kéo đi theo).

**b. Mở nhóm thanh bên.** Trước chỉ có `open_page`. Thêm `open_group` (bung một nhóm đang gập mà
KHÔNG đổi trang) và `sidebar open|close`, đi đủ ba nơi như `PAGES`: `RAIL_GROUPS` trong
console.js (thêm khoá `id` vì nhãn đổi theo ngôn ngữ nên không làm khoá tra cứu được),
`GROUPS` trong ui-actions.js, `GROUPS` trong plugin javis-ui. `test_ui_actions.js` canh ba danh
sách khớp nhau.

Sửa luôn một lỗi liên quan: `window.JavisNav.go` trỏ thẳng `navigateTo`, trong khi hàm `go` của
store Alpine mới là chỗ bung nhóm chứa trang. Nên mở trang bằng lời xong thanh bên vẫn gập,
người dùng tưởng Javis không hiểu "mở dropdown". Nay `JavisNav.go` đi qua store.

**c. Lệnh giao diện không đánh thức bộ não chính.** Đường cũ: bộ não giọng phát
`JAVIS_ASK_MAIN` -> `run_turn` với cả ngữ cảnh hội thoại (có lúc hơn 200 nghìn token) -> tool
`javis_ui` -> dashboard. Một câu "mở trang Models" mất hàng chục giây cho một việc không cần dữ
liệu gì. Nay bộ não giọng phát `JAVIS_UI: <action> <target>` (`voice_brain.UI_MARKER`,
`parse_ui`), `run_voice_turn` gọi thẳng `ui_bridge.request`. Action lạ do model bịa thì bỏ qua
chứ không chạy. Dòng marker không bao giờ ra loa, y như `JAVIS_ASK_MAIN`.

## 11. Nói chuyện mượt, chữ và giọng một luồng (0.57.6, Voice V3)

Đầu bài: chủ dự án dán một cuộc trò chuyện với ChatGPT Voice (2026-09-14) và bảo "triển khai để
nói chuyện mượt như này, theo gợi ý của ChatGPT". Các gợi ý trong đó: vừa gõ vừa nói trong cùng
một phiên; cắt cụm tự nhiên (dấu câu trước, rồi phẩy hay liên từ, cụm 5 đến 12 từ, quá 300 đến
500 ms không có điểm đẹp thì đẩy, cụm đầu ngắn hơn); endpointing phân biệt dừng để nghĩ với dừng
hẳn; backchannel; câu trả lời voice ngắn hơn chat; ngắt lời bất cứ lúc nào; máy trạng thái rõ;
nói tiến độ khi việc lâu; hai chế độ nhanh và sâu. Đối chiếu với V1 và V2 thì đã có: máy trạng
thái (voice-turn.js), endpointing hai ngưỡng, ngắt lời có tạm dừng, hai chế độ (làn nhanh +
JAVIS_ASK_MAIN, Live + ask_javis). Đợt này làm phần còn thiếu.

**a. Bộ não chính vẫn đọc từng mẩu.** 0.57.2 mới sửa phía server cho LÀN NHANH; làn chính
(Claude Code) vẫn bắn mỗi text delta thành một khung `stream`, và app.js đọc mỗi khung là một
yêu cầu TTS. Sửa ở TRÌNH DUYỆT để mọi làn hưởng chung: `dashboard/voice-chunker.js` (module
thuần, test bằng node) gom chữ stream và chỉ trả cụm đọc được theo đúng thứ tự ưu tiên ChatGPT
gợi ý. Cụm ĐẦU của lượt cắt sớm (đủ 6 từ mà có phẩy hay liên từ, hoặc 12 từ) để tiếng đầu ra
nhanh; cụm SAU chỉ cắt khi hết câu hoặc quá 220 ký tự. Đồng hồ 150 ms: chữ dở nằm im quá 400 ms
mà LOA ĐANG IM thì đẩy ở điểm đẹp gần nhất; loa đang bận thì không đẩy vì đợi không mất gì, còn
đẩy sớm là thêm một yêu cầu TTS vô ích (đúng cái bẫy 0.57.1). Khối mã ``` không bao giờ ra
loa; gặp `<!--` (JAVIS_ASK) là bỏ từ đó về sau. `split_speakable` phía server giữ nguyên: làn
nhanh gửi nguyên câu thì qua chunker vẫn phát ngay. Không có "so"/"or" tiếng Anh trong danh
sách liên từ vì "so với", "hay" tiếng Việt đụng ngay.

**b. Một luồng chữ và giọng.** Đang rảnh tay (mic bật) mà gõ chữ thì khung WS vẫn mang
`voice: true` nên đi làn nhanh như tin từ mic, và câu trả lời vẫn đọc ra loa (loa đã đi theo mic
từ 02/09). Ở chế độ Live thì chữ gõ đẩy thẳng vào phiên Live qua `sendText` (route đã nhận khung
`text` từ 0.57.0 mà chưa ai gọi), không mở lượt chat riêng; có file đính kèm thì đi đường thường.

**c. Trả lời ngắn khi đang nói.** Khối `[NGỮ CẢNH GIAO DIỆN ...]` thêm `kênh=giọng` khi tin từ
mic hoặc gõ lúc rảnh tay; `channel_context.py` dặn bộ não chính: khi ấy luật "trình bày cho mắt"
nhường chỗ cho luật nói, 2 đến 4 câu, câu đầu ngắn, không tiêu đề, bảng, gạch đầu dòng. Bộ não
giọng (làn nhanh) vốn đã có luật này trong SYSTEM_PROMPT.

**d. Câu tiến độ.** Đạo diễn thêm `turnStart(now)`, `noteSpoke()`, `fillerCheck(now)`: xử lý quá
2,5 giây (đang gọi tool thì 1,2 giây) mà chưa có chữ thật nào ra loa thì trả `speak_filler` đúng
một lần mỗi lượt; app.js đọc một câu ngẫu nhiên từ `app.voice_filler` (i18n, các câu cách nhau
bằng `|`), chỉ khi rảnh tay. Làn nhanh đã có câu chờ trước JAVIS_ASK_MAIN thì `spoke` bật và
không nói thêm.

**e. Endpointing.** Kết câu bằng ậm ừ lúc nghĩ ("ừm", "ờ", "kiểu", "cái", "um", "like") thì chờ
ngưỡng dài; không có "à" vì "vậy à" là câu hỏi đã xong. Cụm CHỜ / DỪNG nhận cả bản nói lắp hay
lặp ("từ từ đợi đợi đợi chút", "thôi thôi dừng lại"): mọi từ thuộc bộ từ vựng của các cụm VÀ có
một cụm nguyên vẹn trong câu; có từ lạ ("đợi mình xem lại số liệu") thì vẫn là tin thường.

**Cố ý KHÔNG làm:** backchannel "ừ, à" khi người dùng nói dài, vì loa mở là voice.js phải tắt
nhận dạng (Web Speech chép chính giọng TTS thành chữ người dùng), một tiếng "ừ" sẽ cắt mất câu
họ đang nói; làm được thì phải đổi sang STT server streaming, ngoài phạm vi. Cảm xúc giọng thì
Edge TTS không có; OpenAI/ElevenLabs/Live đã chọn được trong cài đặt. Realtime API thì chính là
chế độ Live đã có.

## 12. Chữ hiện theo lời đọc (0.57.8)

Chủ dự án gửi ảnh ChatGPT Voice: chữ trong khung chat hiện DẦN theo đúng chỗ giọng đang đọc (như
typing), và ngắt giữa chừng thì bong bóng dừng đúng chỗ đã nói. Javis lúc đó vẽ cả câu ngay khi
chữ về từ model (trước loa vài giây), nên nhìn thì chữ xong rồi mà loa mới bắt đầu.

Cách làm, tất cả ở trình duyệt, không đổi khung WS:
- `voice.js` đếm số TỪ đã ra tiếng (`spokenWords()`): khúc đã phát xong cộng phần khúc dở theo tỉ
  lệ `currentTime / duration`, cả ba đường (Audio máy tính, một phần tử Audio trên iOS, giọng
  trình duyệt). Chỉ reset khi app.js mở lượt chat mới (`resetSpokenWords`), nên model chậm hơn
  loa (hàng đợi cạn rồi đầy lại) vẫn đếm liền; `_spokenChunks` cũ reset mỗi lượt đọc nên không
  dùng được. Câu tiến độ và tin nền đọc với `enqueueSpeak(text, {uncounted: true})` thì không
  tính, vì chúng không thuộc câu trả lời. Khúc TTS lỗi bị bỏ vẫn cộng từ, kẻo chữ kẹt lại.
- `voice-live.js` không có văn bản đồng bộ với tiếng, nên đo tỉ lệ: `progress()` trả ms đã xếp
  lịch và ms đã phát kể từ `resetProgress()`; bong bóng hiện `tổng từ * played / total`.
- `app.js`: `batTheoLoi / veTheoLoi / ketThucTheoLoi / nhipTheoLoi`. Đang rảnh tay (mic bật, loa
  bật) thì khung `stream` và `response` không vẽ markdown mà vẽ N từ đầu của văn bản ĐÃ LỌC cho
  loa (`_cleanForTTS`, để số từ khớp với số từ đã đọc); vòng vẽ orb gọi `nhipTheoLoi` khoảng 20
  lần một giây. Lượt xong và loa im thì vẽ markdown đầy đủ kèm chip hỏi lại. Ngắt lời THẬT
  (`stop_tts` với `interrupted`, hay `interrupted` từ Live) thì đóng băng ở chỗ đã nói kèm "…".
- Kho phiên vẫn lưu ĐỦ câu trả lời (server lưu trước khi loa đọc), nên F5 thấy cả câu; khối
  `ngắt_lời=` ở tin kế tiếp vẫn cho model biết người dùng nghe tới đâu. Cố ý không cắt bản lưu:
  người dùng có thể muốn đọc phần Javis chưa kịp nói.
