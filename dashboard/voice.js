// ============================================
// JAVIS OS - Voice Layer (Web Speech API)
// ============================================

class JavisVoice {
  // Lỗi mic KHÔNG bao giờ tự khỏi khi thử lại. Thử lại chỉ đẻ ra đúng lỗi đó, và nếu nơi gọi
  // báo bằng alert thì thành vòng lặp chặn cứng cả trang.
  //   not-allowed         người dùng từ chối quyền, hoặc trang không chạy ở ngữ cảnh bảo mật
  //   service-not-allowed trình duyệt chặn dịch vụ nhận giọng
  //   audio-capture       máy không có mic (hay gặp trên phiên điều khiển từ xa)
  static LOI_CHET = ["not-allowed", "service-not-allowed", "audio-capture"];

  // ---- Ngắt lời bằng giọng: mẹo NHÁ TIẾNG (0.57.14) ----
  // Đo mức âm mic KHÔNG phân biệt nổi giọng người với tiếng LOA NGOÀI vọng lại, nên bản cũ
  // kẹt giữa hai cái sai: ngưỡng thấp thì Javis nghe chính mình rồi tự câm, ngưỡng cao thì
  // nói kiểu gì nó cũng đọc tiếp. Cách thoát: đừng đoán, hãy THỬ. Nghi có người nói thì hạ
  // âm lượng loa xuống một nhá rồi đo lại. Tiếng vọng đi theo âm lượng nên tụt cả chục lần;
  // giọng người thì không tụt. So mức sau khi nhá với mức trước khi nhá là biết ngay, không
  // cần hiệu chỉnh tay, không cần chờ nhận dạng trả chữ (Web Speech mất 0,5 đến 1,5 giây mới
  // có chữ đầu, lâu hơn cả một tiếng "thôi" - đó là lý do bản cũ không sao ngắt được).
  static BARGE_SAN = 0.045;     // sàn tuyệt đối của ngưỡng nghi ngờ (0..1)
  static NHA_GAIN = 0.12;       // nhá: còn 12% âm lượng
  static NHA_TICKS = 4;         // thăm dò 4 nhịp 100 ms
  static NHA_MIN_HIT = 2;       // 2 nhịp còn tiếng khi đã nhá = người thật
  static NHA_TI_LE = 0.45;      // còn trên 45% mức trước khi nhá thì không phải vọng
  static NHA_SAN = 0.02;        // dưới mức này coi như phòng im, đừng bắt

  // Mẫu đo trong lúc nhá tiếng có phải giọng NGƯỜI không. Thuần, không đụng DOM, để test
  // được bằng node: vọng của loa tụt theo âm lượng, giọng người giữ nguyên mức.
  static laNguoiThat(preLevel, samples) {
    const nguong = Math.max((preLevel || 0) * JavisVoice.NHA_TI_LE, JavisVoice.NHA_SAN);
    let hit = 0;
    for (let i = 0; i < (samples || []).length; i++) if (samples[i] > nguong) hit++;
    return hit >= JavisVoice.NHA_MIN_HIT;
  }

  constructor(opts = {}) {
    this.lang = opts.lang || "vi-VN";
    this.onTranscript = opts.onTranscript || (() => {});
    this.onInterim = opts.onInterim || (() => {});
    this.onStart = opts.onStart || (() => {});
    this.onEnd = opts.onEnd || (() => {});
    this.onError = opts.onError || (() => {});

    this.recognition = null;
    this.synth = window.speechSynthesis;
    this.isListening = false;
    // Nhớ lựa chọn bật/tắt đọc qua reload. MẶC ĐỊNH TẮT: người dùng mới vào phải im lặng,
    // chỉ đọc thành tiếng khi họ tự bật công tắc (lưu "1" vào localStorage).
    this.ttsEnabled = (localStorage.getItem("javis.ttsEnabled") === "1");
    this.vietnameseVoice = null;

    // Edge TTS backend (server)
    this.ttsBackend = opts.ttsBackend || "/tts"; // "/tts" hoặc null để dùng browser
    this.ttsVoice = opts.ttsVoice || "vi-VN-HoaiMyNeural"; // nhãn UI: Ngọc Thu (nữ) | Nam Minh (nam)
    this.ttsRate = opts.ttsRate || "+5%";
    this.currentAudio = null;
    this.ttsQueue = [];
    this.speechQueue = [];   // hàng đợi đọc nối tiếp (các bước trung gian + kết quả)
    this.isPlaying = false;
    this._resumeAfterTTS = false;  // mic đang mở khi TTS bắt đầu → đọc xong tự mở nghe lại
    this._resumeTimer = null;

    // ---- Voice V1 (docs/dev/2026-09-voice-v1-spec.md): móc nối với đạo diễn voice-turn.js ----
    // voice.js chỉ lo TAI và MIỆNG; luật "chờ bao lâu rồi gửi, có được ngắt không" nằm ở đạo
    // diễn, app.js gắn các móc này. Không gắn thì hành vi cũ giữ nguyên (silenceMs cố định,
    // chen ngang giết ngay).
    this.endpointDelay = opts.endpointDelay || null;   // (text) -> ms im lặng trước khi gửi
    this.onBargeStart = opts.onBargeStart || null;     // NGHI có người chen ngang (đường cũ: tạm dừng chờ chữ)
    this.onBargeConfirm = opts.onBargeConfirm || null; // ĐÃ CHẮC là người thật (nhá tiếng xong): dừng hẳn
    this.onSpeakStart = opts.onSpeakStart || null;     // bắt đầu phát tiếng
    this.onSpeakEnd = opts.onSpeakEnd || null;         // hết hàng đợi hoặc bị dừng
    this.onSlow = opts.onSlow || null;                 // (bool) khúc TTS tải quá chậm
    this.bargeEnabled = true;                          // công tắc "ngắt lời bằng giọng"
    this.handsFree = false;                            // app.js bật khi đang nói chuyện bằng giọng
    // 2 nhịp 100 ms là đủ để NGHI NGỜ, vì nghi ngờ chỉ dẫn tới một cú nhá tiếng 400 ms chứ
    // không còn dừng hẳn. Tiếng ho hay tiếng đặt cốc chết ngay trong lúc nhá nên không cắt
    // được câu nữa; đổi lại một tiếng "thôi" ngắn cũng kịp lọt vào cửa sổ thăm dò. Bản cũ
    // phải để 5 nhịp vì lúc ấy chạm ngưỡng là câm luôn.
    this.bargeMinTicks = 2;
    // Mức vọng của phòng, TỰ HỌC theo từng câu và nhớ qua các lần mở trang. Chặn trên 0.3 để
    // một giá trị rác trong localStorage không làm ngắt lời chết hẳn.
    this._echoFloor = Math.min(0.3, parseFloat(localStorage.getItem("javis.nenVong")) || 0);
    this._dangNha = false;                             // đang nhá tiếng để thăm dò
    this._nhaTimer = null;
    this._paused = false;                              // đang TẠM DỪNG vì nghi chen ngang
    this._spokenChunks = [];                           // khúc đã phát xong trong lượt đọc này
    // ---- Voice V3: đếm số TỪ đã ra tiếng, để bong bóng hiện chữ THEO LỜI ĐỌC (karaoke) ----
    // Khác _spokenChunks (reset mỗi lượt đọc), số này chỉ reset khi app.js mở lượt chat mới, nên
    // model chậm hơn loa (hàng đợi cạn rồi đầy lại) vẫn đếm liền. Câu tiến độ và tin nền đọc
    // với opts.uncounted thì không tính, vì chúng không nằm trong câu trả lời.
    this._wordsDone = 0;
    this._countThis = true;
    this._uncounted = [];

    // ---- Voice V2: nghe bằng Groq Whisper (docs/dev/2026-09-voice-v2-spec.md mục 3) ----
    // Web Speech vẫn cho chữ tạm và điểm dừng câu; song song đó MediaRecorder ghi âm, hết câu
    // thì gửi file lên /stt và chữ Groq THAY chữ Chrome. Groq lỗi thì giữ chữ Chrome. Bọc
    // onTranscript ở đây để onend của recognition không phải biết gì về chuyện này.
    this.sttUpload = false;                            // app.js bật khi cài đặt stt_provider = groq
    this.sttUrl = "/stt";
    this._rec = null;
    this._recChunks = [];
    const _userTranscript = this.onTranscript;
    this.onTranscript = (text) => { this._quaStt(text, _userTranscript); };

    // Audio analysis - cho hiệu ứng phát sáng theo âm thanh
    this.audioCtx = null;
    this.outAnalyser = null;   // âm Javis đọc (TTS)
    this.inAnalyser = null;    // âm mic (khi nghe)
    this.micStream = null;
    this._freqData = new Uint8Array(64);

    this._initRecognition();
    this._loadVoices();
  }

  _ensureCtx() {
    if (!this.audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.audioCtx = new AC();
    }
    if (this.audioCtx.state === "suspended") this.audioCtx.resume();
    return this.audioCtx;
  }

  async _startMicMeter() {
    try {
      const ctx = this._ensureCtx();
      if (!this.micStream) {
        // Bật khử vọng/khử ồn: giảm việc mic nghe lại chính giọng TTS (chống tự-kích-hoạt + lồng tiếng).
        this.micStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        });
      }
      const src = ctx.createMediaStreamSource(this.micStream);
      const an = ctx.createAnalyser();
      an.fftSize = 128;
      src.connect(an);
      this.inAnalyser = an;
    } catch (e) { /* mic meter optional */ }
    this._startRecorder();   // Voice V2: có luồng mic rồi thì ghi âm cho Groq (nếu bật)
  }

  // ---- Voice V2: ghi âm song song với Web Speech, gửi Groq khi hết câu ----
  _startRecorder() {
    if (!this.sttUpload || !this.micStream || !this.isListening && !this._starting) return;
    if (this._rec && this._rec.state === "recording") return;
    if (typeof MediaRecorder === "undefined") return;
    try {
      let opts = {};
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) opts = { mimeType: "audio/webm;codecs=opus" };
      const rec = new MediaRecorder(this.micStream, opts);
      this._recChunks = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size) this._recChunks.push(e.data); };
      rec.start(250);
      this._rec = rec;
    } catch (e) { this._rec = null; }
  }

  // Dừng ghi và trả Blob (null nếu không ghi gì). Gọi với giu=false để bỏ luôn (mic tắt vì TTS).
  _stopRecorder() {
    const rec = this._rec;
    this._rec = null;
    if (!rec || rec.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      const chunks = this._recChunks; this._recChunks = [];
      rec.onstop = () => resolve(chunks.length ? new Blob(chunks, { type: rec.mimeType || "audio/webm" }) : null);
      try { rec.stop(); } catch (e) { resolve(null); }
    });
  }

  async _quaStt(text, cb) {
    const blob = await this._stopRecorder();
    if (!this.sttUpload || !blob || blob.size < 2000) { cb(text); return; }
    let better = "";
    try {
      const fd = new FormData();
      fd.append("file", blob, "voice.webm");
      fd.append("lang", this.lang || "");
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), 8000);
      const r = await fetch(this.sttUrl, { method: "POST", body: fd, signal: ctl.signal });
      clearTimeout(timer);
      const d = await r.json();
      if (d && d.ok && d.text) better = String(d.text).trim();
    } catch (e) { better = ""; }
    cb(better || text);
  }

  getInputLevel() {
    if (!this.inAnalyser || !this.isListening) return 0;
    this.inAnalyser.getByteFrequencyData(this._freqData);
    let s = 0;
    for (let i = 0; i < this._freqData.length; i++) s += this._freqData[i];
    return Math.min(1, (s / this._freqData.length) / 200);
  }

  getOutputLevel() {
    if (!this.outAnalyser) return 0;
    this.outAnalyser.getByteFrequencyData(this._freqData);
    let s = 0;
    for (let i = 0; i < this._freqData.length; i++) s += this._freqData[i];
    return Math.min(1, (s / this._freqData.length) / 180);
  }

  getLevel() {
    return Math.max(this.getInputLevel(), this.getOutputLevel());
  }

  _initRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      console.warn("Trình duyệt không hỗ trợ SpeechRecognition. Dùng Chrome hoặc Edge.");
      return;
    }

    this.recognition = new SR();
    this.recognition.lang = this.lang;
    this.recognition.continuous = true;       // nghe liên tục, không dừng giữa câu
    // iPhone/iPad: WebKit KHÔNG nghe liên tục được. Đặt continuous=true thì nó vào một phiên
    // "ghi âm" không bao giờ tự kết thúc câu, và onend tự mở lại càng làm nó kéo dài - đúng
    // cảnh chủ repo tả 02/09 "bật mic nó thành chế độ ghi âm". Trên iOS mỗi lượt nói là một
    // phiên: nói xong -> gửi -> vòng rảnh tay bên app.js mở lại khi Javis đọc xong.
    if (this._laIOS()) this.recognition.continuous = false;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;

    this.accumulatedTranscript = "";
    this._committed = "";                     // chữ đã nghe ở các phiên trước trong CÙNG một lượt nói
    this.userStopped = false;                 // user chủ động dừng?
    this.silenceMs = 1500;                    // im lặng bao lâu thì tự gửi
    this._silenceTimer = null;
    this._starting = false;                   // đã gọi start() nhưng onstart chưa chạy
    this._stopPending = false;                // có lệnh dừng tới trong lúc đang mở phiên
    this._micHong = "";                       // lỗi mic KHÔNG thể tự thử lại (xem LOI_CHET)

    this.recognition.onstart = () => {
      this._starting = false;
      this.isListening = true;
      this.userStopped = false;
      this.accumulatedTranscript = "";
      // Lệnh dừng tới TRƯỚC khi phiên kịp mở (bấm rồi thả Space thật nhanh, bấm nút mic hai
      // lần liền): lúc đó isListening còn false nên stopListening() không dừng được gì, mic ở
      // lại MỞ vĩnh viễn và onend còn tự khởi động lại. Người dùng tưởng đã tắt, thực ra Javis
      // vẫn nghe: tiếng nhạc hay TV trong phòng được chép thành chữ rồi TỰ GỬI như tin của họ.
      // Nợ đó trả ở đây - đóng phiên ngay khi nó vừa mở, không nhận chữ, không gửi gì.
      if (this._stopPending) {
        this._stopPending = false;
        this.userStopped = true;             // chặn auto-restart trong onend
        try { this.recognition.abort(); } catch (e) {}
        return;
      }
      this.onStart();
    };

    this.recognition.onresult = (event) => {
      // Đang phát TTS thì BỎ mọi kết quả nhận dạng: đó là mic nghe lại chính giọng Javis
      // (SpeechRecognition thu riêng, KHÔNG được khử vọng như luồng đo mức âm), không phải
      // user nói. Không chặn thì giọng Javis bị chép vào khung chat rồi tự gửi đi.
      if (this.isSpeaking()) return;
      // DỰNG LẠI từ TOÀN BỘ event.results mỗi lần, KHÔNG cộng dồn qua từng sự kiện.
      // Bản cũ làm `accumulated += final` từ resultIndex trở đi. Chrome máy tính giao đúng
      // từng mảnh một nên không sao; Chrome Android thì resultIndex thường đứng ở 0 và mỗi
      // "final" lại chứa CẢ câu tới lúc đó, nên cộng dồn là chép câu ấy thêm một lần ở mỗi
      // sự kiện: "Ok" + "Ok có" + "Ok có vẻ" + ... - đúng cái tin dài cả trang chủ repo gửi
      // ảnh ngày 02/09. results là bức ảnh đầy đủ của phiên nên đọc lại từ 0 luôn đúng, và
      // phần đã nghe ở phiên trước (Chrome tự đóng rồi ta mở lại) giữ ở _committed.
      let interim = "", final = "";
      for (let i = 0; i < event.results.length; i++) {
        const transcript = (event.results[i][0] || {}).transcript || "";
        if (event.results[i].isFinal) final += transcript + " ";
        else interim += transcript;
      }
      this.accumulatedTranscript = this._ghepChuyenBien(final.trim());
      // Show user toàn bộ tích lũy + đoạn đang nghe
      const display = (this.accumulatedTranscript + " " + interim).trim();
      if (display) {
        this.onInterim(display);
        // Reset đồng hồ im lặng - nói tiếp thì hoãn, im đủ lâu thì tự gửi. Có đạo diễn thì
        // độ trễ tính theo câu (kết bằng liên từ thì chờ lâu hơn), không thì số cố định.
        clearTimeout(this._silenceTimer);
        let ms = this.silenceMs;
        try { if (this.endpointDelay) ms = this.endpointDelay(display) || ms; } catch (e) {}
        this._silenceTimer = setTimeout(() => this.stopListening(), ms);
      }
    };

    this.recognition.onerror = (event) => {
      this._starting = false;
      // 'no-speech' không phải lỗi thật - auto-restart
      if (event.error === "no-speech" || event.error === "aborted") {
        return;
      }
      this.isListening = false;
      // Ba lỗi này KHÔNG bao giờ tự khỏi khi thử lại: người dùng đã từ chối quyền, trình duyệt
      // chặn dịch vụ nhận giọng, hoặc máy không có mic. Thử lại chỉ đẻ ra đúng lỗi đó.
      //
      // Không chốt ở đây thì thành VÒNG LẶP KHÔNG THOÁT ĐƯỢC, và đã xảy ra thật (người dùng
      // báo 04/09 kèm ảnh): onend thấy `userStopped` còn false nên mở lại phiên; phiên mới lại
      // 'not-allowed'; app.js lại alert. Alert là hộp CHẶN, nên bấm OK xong là vòng kế tiếp
      // nổ ngay - không còn đường nào bấm vào trang nữa. Đánh dấu `userStopped` để chặn luôn
      // nhánh mở lại trong onend, chứ không chỉ ghi nhớ suông.
      if (JavisVoice.LOI_CHET.includes(event.error)) {
        this._micHong = event.error;
        this.userStopped = true;
      }
      this.onError(event.error);
    };

    this.recognition.onend = () => {
      this._starting = false;
      // Nếu user chưa chủ động dừng → tự restart (giữ session sống khi user dừng nghĩ).
      // iOS không: phiên kết thúc là hết một câu, gửi luôn (xem chú thích ở continuous).
      if (!this.userStopped && !this._micHong && !this._laIOS()) {
        try {
          // Phiên mới thì event.results bắt đầu lại từ trống. Gói phần đã nghe vào
          // _committed trước, không thì onstart xoá trắng và nửa câu đầu biến mất.
          this._committed = this._ghepChuyenBien("");
          this.recognition.start();
          return;
        } catch (e) {
          // start fail (đã đang chạy) - ignore
        }
      }
      this.isListening = false;
      // Gửi toàn bộ text đã tích luỹ khi user dừng
      const finalText = this.accumulatedTranscript.trim();
      this._committed = "";
      if (finalText) this.onTranscript(finalText);
      this.onEnd();
    };
  }

  // Ghép phần đã chốt ở phiên trước với phần final của phiên này. Android đôi khi giao một
  // final là BẢN DÀI HƠN của final trước (cùng câu, thêm chữ), nên câu mới mà mở đầu bằng câu
  // cũ thì lấy câu mới thay vì nối - đó chính là cách "Ok có vẻ" không thành "Ok Ok có vẻ".
  _ghepChuyenBien(finalNay) {
    const cu = (this._committed || "").trim();
    const moi = (finalNay || "").trim();
    if (!moi) return cu;
    if (!cu) return moi;
    if (moi.startsWith(cu)) return moi;
    if (cu.endsWith(moi)) return cu;
    return (cu + " " + moi).trim();
  }

  // Mic đang hỏng hẳn không? Nơi gọi dùng nó để TẮT chế độ rảnh tay thay vì cứ thử mãi.
  micHong() { return this._micHong; }

  _laIOS() {
    if (this._iosCache === undefined) {
      const ua = navigator.userAgent || "";
      this._iosCache = /iP(hone|ad|od)/.test(ua)
        || (navigator.platform === "MacIntel" && (navigator.maxTouchPoints || 0) > 1);
    }
    return this._iosCache;
  }

  // iOS chỉ cho phát âm thanh do CỬ CHỈ người dùng khởi động, và mỗi `new Audio()` là một
  // phần tử mới chưa được "mở khoá". Bản cũ tạo Audio mới cho từng đoạn + một Audio preload,
  // nên trên iPhone đoạn đầu phát được còn các đoạn sau bị chặn hoặc trễ - "đọc ngập ngừng,
  // ngắt giữa chừng". Chữa: MỘT phần tử Audio dùng lại, mở khoá ngay trong cử chỉ bấm mic
  // bằng một file WAV im lặng, sau đó chỉ đổi src.
  _moKhoaAudioIOS() {
    if (!this._laIOS() || this._iosAudio) return;
    const a = new Audio();
    a.setAttribute("playsinline", "");
    a.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
    a.play().catch(() => {});
    this._iosAudio = a;
  }

  _loadVoices() {
    const load = () => {
      const voices = this.synth.getVoices();
      // Tìm giọng Vietnamese tốt nhất theo thứ tự ưu tiên
      this.vietnameseVoice =
        voices.find(v => v.lang === "vi-VN" && v.name.includes("Google")) ||
        voices.find(v => v.lang === "vi-VN") ||
        voices.find(v => v.lang.startsWith("vi")) ||
        null;
    };
    load();
    if (this.synth.onvoiceschanged !== undefined) {
      this.synth.onvoiceschanged = load;
    }
  }

  // `tuDong` = true nghĩa là máy tự gọi (vòng giữ mic của chế độ rảnh tay, mở lại sau TTS).
  // Đường tự động KHÔNG được thử lại khi mic đã hỏng hẳn - đó chính là chỗ sinh vòng lặp.
  // Còn người dùng bấm nút mic thì LUÔN được thử lại: họ có thể vừa mới cấp quyền trong cài
  // đặt trình duyệt, và một cái nút bấm không lên là thứ không ai chẩn đoán nổi.
  // `giuTieng` = true: mở nghe trong lúc audio đang TẠM DỪNG vì nghi chen ngang (Voice V1).
  // Không được giết tiếng đang đọc ở đây, vì nếu hoá ra là chen ngang giả thì phải phát tiếp.
  startListening(tuDong, giuTieng) {
    if (!this.recognition) {
      this.onError("not-supported");
      return;
    }
    if (this.isListening) return;
    if (this._micHong) {
      if (tuDong) return;
      this._micHong = "";
    }
    // Mở nghe chủ động → huỷ mọi lịch tự-mở-lại còn treo
    if (!giuTieng) this._resumeAfterTTS = false;
    clearTimeout(this._resumeTimer);
    this._committed = "";                     // lượt nói MỚI, không kéo chữ của lượt trước sang
    // Stop TTS đang đọc nếu user bấm nói
    if (!giuTieng) { this.synth.cancel(); this.stopSpeaking(); }
    this._moKhoaAudioIOS(); // iOS: mở khoá phần tử phát tiếng NGAY trong cử chỉ bấm mic
    this._startMicMeter();  // bật đo âm mic cho hiệu ứng phát sáng (kèm ghi âm Groq nếu bật)
    try {
      this._stopPending = false;
      this._starting = true;
      this.recognition.start();
      this._startRecorder();  // luồng mic đã có từ lần trước thì ghi ngay, khỏi đợi _startMicMeter
    } catch (e) {
      // "InvalidStateError" = phiên trước đã/đang mở (vòng lặp giữ mic của chế độ rảnh tay gọi
      // lại trong lúc phiên đầu chưa kịp onstart). Phiên đó vẫn sắp mở, nên KHÔNG được hạ cờ
      // _starting: hạ là lệnh dừng tới sau không có chỗ ghi nợ, và mic kẹt mở lần nữa.
      if (!e || e.name !== "InvalidStateError") this._starting = false;
      this.onError("start-failed: " + e.message);
    }
  }

  stopListening() {
    clearTimeout(this._silenceTimer);
    // User chủ động tắt nghe → không tự mở lại sau khi TTS đọc xong
    this._resumeAfterTTS = false;
    clearTimeout(this._resumeTimer);
    if (this.recognition && this.isListening) {
      this.userStopped = true;     // đánh dấu user chủ động dừng → không auto-restart
      this.recognition.stop();
    } else if (this._starting) {
      // Phiên đang mở dở (start() đã gọi, onstart chưa chạy) nên chưa có gì để dừng. Ghi nợ
      // lại, onstart sẽ đóng ngay. Bỏ nhánh này là mic kẹt mở - xem chú thích ở onstart.
      this._stopPending = true;
    }
  }

  toggleListening() {
    if (this.isListening) this.stopListening();
    else this.startListening();
  }

  // Đọc NGAY: ngắt phần đang đọc + xoá hàng đợi, rồi đọc đoạn này.
  // opts.force = đọc kể cả khi đang tắt tiếng (dùng cho nút "nghe thử giọng").
  speak(text, opts = {}) {
    this.stopSpeaking();
    this.enqueueSpeak(text, opts);
  }

  // Đọc NỐI TIẾP: thêm vào cuối hàng đợi, KHÔNG cắt ngang đoạn đang đọc.
  // Dùng cho các cập nhật ở bước trung gian (stream).
  enqueueSpeak(text, opts = {}) {
    if (!this.ttsEnabled && !opts.force) return;
    const clean = this._cleanForTTS(text);
    if (!clean) return;
    // Cùng một đoạn tới hai lần liền (socket nối lại giao trùng sự kiện, hay lượt cuối lặp
    // lại đúng đoạn vừa stream) thì đọc một lần là đủ.
    if (clean === this._lastQueued && !opts.force) return;
    this._lastQueued = clean;
    this.speechQueue.push(clean);
    if (opts.uncounted) this._uncounted.push(clean);   // V3: không tính vào số từ đã đọc
    if (!this.isPlaying) this._pumpQueue();
    else this._preloadNextQueued();   // đang đọc khúc cuối của đoạn trước thì tải ngay đoạn này
  }

  // Tải trước audio của đoạn KẾ trong hàng đợi khi đoạn hiện tại đang ở khúc cuối, để hết
  // khúc là phát liền. Trước đây chỉ tải trước trong CÙNG một đoạn, còn giữa hai đoạn (hai câu
  // stream về liên tiếp) là một lượt chờ Edge TTS trọn vẹn: nghe như cắt từng câu.
  _preloadNextQueued() {
    if (this._laIOS() || this._preloaded || !this.ttsBackend) return;
    if (!this.ttsChunks || this._chunkIndex !== this.ttsChunks.length - 1) return;
    const next = this.speechQueue && this.speechQueue[0];
    if (!next) return;
    const first = this._splitForLatency(next)[0];
    if (first) this._preloadUrl(this._chunkUrl(first));
  }

  _preloadUrl(url) {
    const na = new Audio(url);
    na.preload = "auto";
    try { na.load(); } catch (e) {}
    this._preloaded = { url: url, audio: na };
  }

  // Lấy đoạn kế trong hàng đợi để đọc; hết hàng đợi thì dừng.
  _pumpQueue() {
    if (!this.speechQueue || this.speechQueue.length === 0) {
      const dangDoc = this.isPlaying;
      this.isPlaying = false;
      this._paused = false;
      this._stopBargeMonitor();
      this._resumeRecognitionIfNeeded();             // đọc xong hết → mở nghe lại nếu trước đó mic đang mở
      if (dangDoc && this.onSpeakEnd) { try { this.onSpeakEnd(); } catch (e) {} }
      return;
    }
    if (!this.isPlaying) {
      this._spokenChunks = [];                       // lượt đọc mới: phần "đã đọc" tính lại từ đầu
      // Nền vọng học được ở lượt trước giữ lại nhưng HẠ dần: cắm tai nghe hay vặn nhỏ loa
      // xong mà nền còn treo ở mức cũ thì ngắt lời lại hoá điếc. Hạ 30% mỗi lượt, vài câu là
      // về đúng môi trường mới, mà vẫn không phải học lại từ số không mỗi lần.
      this._echoFloor = this._echoFloor * 0.7;
      if (this.onSpeakStart) { try { this.onSpeakStart(); } catch (e) {} }
    }
    this.isPlaying = true;
    this._muteRecognition();                         // mic đang mở → tạm ngừng NHẬN DẠNG, khỏi thu giọng TTS vào chat
    this._giuTaiKhiDoc();                            // rảnh tay: giữ luồng mic sống để CÒN CÁI MÀ ĐO
    this._startBargeMonitor();                       // cho phép ngắt lời bằng giọng khi đang đọc
    const text = this.speechQueue.shift();
    const ui = this._uncounted.indexOf(text);        // V3: đoạn này có tính vào số từ đã đọc không
    this._countThis = ui < 0;
    if (ui >= 0) this._uncounted.splice(ui, 1);
    if (this.ttsBackend) this._speakBackend(text);   // Edge TTS (giọng Việt chuẩn)
    else this._speakBrowser(text);                   // fallback Web Speech
  }

  // Javis bắt đầu đọc mà mic đang nghe → tạm NGỪNG nhận dạng (abort, bỏ kết quả dở),
  // vì SpeechRecognition sẽ chép chính giọng TTS thành tin nhắn của user. Ngắt lời bằng
  // giọng vẫn hoạt động - barge-in đo mức âm qua luồng mic đã khử vọng, không cần nhận dạng.
  _muteRecognition() {
    if (!this.recognition || !this.isListening) return;
    this._resumeAfterTTS = true;
    this.userStopped = true;             // chặn auto-restart trong onend
    clearTimeout(this._silenceTimer);
    this.accumulatedTranscript = "";     // bỏ những gì lỡ nghe - không gửi
    this.onInterim("");                  // xoá chữ đang hiện dở trên màn hình
    this._stopRecorder().catch(() => {}); // Voice V2: bỏ đoạn ghi âm dở, không gửi Groq
    try { this.recognition.abort(); } catch (e) {}
  }

  // Đọc xong (hoặc bị dừng) → mở nghe lại nếu mic từng bị tạm ngừng vì TTS.
  // Chờ một nhịp cho đuôi âm tắt hẳn; phiên nhận dạng MỚI nên không dính giọng TTS cũ.
  _resumeRecognitionIfNeeded() {
    if (!this._resumeAfterTTS) return;
    this._resumeAfterTTS = false;
    clearTimeout(this._resumeTimer);
    this._resumeTimer = setTimeout(() => {
      if (!this.isPlaying && !this.isListening) this.startListening(true);
    }, 400);
  }

  // Đang nói chuyện bằng giọng thì phải GIỮ luồng mic sống trong lúc Javis đọc, kể cả khi
  // nhận dạng đã đóng. Ngắt lời đo mức âm chứ không đọc chữ, nên không có luồng mic là không
  // có gì để đo và ngắt lời chết câm. Luồng mic vốn không bao giờ bị tắt tracks, nên thường
  // chỉ cần nối lại bộ đo; lần đầu thì mở (quyền đã cấp từ lúc bật rảnh tay, không hỏi lại).
  _giuTaiKhiDoc() {
    if (!this.handsFree || !this.bargeEnabled) return;
    // AudioContext bị treo (tab ẩn lâu, máy ngủ dậy) thì analyser trả toàn số im lặng và ngắt
    // lời điếc mà không có lỗi nào báo. Đánh thức trước khi đo.
    try { this._ensureCtx(); } catch (e) {}
    if (this.micStream && this.inAnalyser) return;
    // _startMicMeter là async: nối xong mới mở được bộ rình, nên phải mở lại ở đây chứ không
    // dựa vào lời gọi đồng bộ ngay sau (lúc ấy inAnalyser còn chưa có, bộ rình thoát ngay).
    try { this._startMicMeter().then(() => this._startBargeMonitor()).catch(() => {}); } catch (e) {}
  }

  // ---- Ngắt lời (barge-in): đang đọc mà nghe user nói đủ to/đủ lâu → dừng đọc + mở nghe ngay ----
  _startBargeMonitor() {
    // Ngắt lời chỉ khi user THỰC SỰ dùng giọng (đã cấp mic). Đo BIÊN ĐỘ SÓNG (time-domain RMS) từ
    // luồng mic ĐÃ khử vọng - đúng độ TO thật, đáng tin hơn trung bình phổ (bị pha loãng bởi dải tần
    // cao im lặng nên giọng nói không bao giờ chạm ngưỡng). Tự HIỆU CHỈNH theo nền (echo + ồn) đo
    // trong ~600ms đầu để hợp mọi máy/môi trường, hạn chế tự-ngắt do nghe lại chính giọng TTS.
    // ĐIỀU KIỆN RÌNH: đang trong một cuộc nói chuyện bằng giọng (rảnh tay), hoặc mic vừa bị
    // tạm ngừng vì TTS.
    //
    // Bản cũ chỉ nhận `_resumeAfterTTS`, và đó là lý do ngắt lời CHƯA TỪNG chạy một lần nào
    // trong hội thoại rảnh tay: nói xong thì đồng hồ im lặng gọi stopListening() nên mic ĐÓNG
    // hẳn trước khi câu trả lời kịp đọc; tới lượt đọc, _muteRecognition() thấy isListening đã
    // false nên thoát ngay và không đặt cờ ấy; vòng giữ mic trong app.js thì bỏ qua vì đang
    // đọc. Cả ba chốt cùng đúng riêng lẻ mà ghép lại thành điếc hoàn toàn (chủ dự án thử thật
    // 15/09: nói chen vào, Javis đọc tiếp như không nghe thấy gì).
    //
    // Nỗi lo cũ vẫn được giữ nguyên, chỉ đổi chốt cho đúng chỗ: không được để luồng mic sống
    // suốt đời trang rồi lần nào Javis đọc cũng rình, vì một tiếng động to trong phòng (nhạc,
    // TV, người khác nói) sẽ tự mở mic rồi chép thành tin nhắn. Chốt đúng là "người dùng CÓ
    // đang nói chuyện bằng giọng không" (handsFree), chứ không phải "mic có tình cờ còn mở
    // không". Rảnh tay tắt thì Javis đọc trong im lặng, không nghe gì hết.
    if (!this._resumeAfterTTS && !this.handsFree) return;
    if (!this.bargeEnabled) return;                  // người dùng tắt "ngắt lời bằng giọng" trong Cài đặt nhanh
    if (this._dangNha) return;                       // đang nhá tiếng thăm dò, đừng mở bộ rình thứ hai
    if (this._bargeTimer || !this.micStream || !this.inAnalyser) return;
    let hits = 0, gan = [];
    // NGƯỠNG TỰ HỌC, không còn đo một lần rồi thôi. Bản cũ lấy nền trong 600 ms ĐẦU, mà bộ
    // rình khởi động TRƯỚC lúc tiếng thật sự ra loa (còn đang tải file TTS), nên nền đo được
    // là phòng im và ngưỡng rơi về sàn 0.045: loa ngoài mở to là vượt ngay, Javis tự ngắt
    // lời mình. Nay nền là trung bình trượt của chính những nhịp KHÔNG nghi ngờ, nên nó dâng
    // dần tới đúng mức vọng của phòng; thêm nữa mỗi lần nhá tiếng kết luận "là vọng" thì nền
    // được nâng thẳng lên trên mức vừa đo (xem _ketThucNha), nên chỉ sau một hai lần là hết
    // nghi oan.
    this._bargeTimer = setInterval(() => {
      if (!this.isPlaying || this._paused) { this._stopBargeMonitor(); return; }
      const rms = this._micRms();
      if (rms == null) return;
      // KHÔNG gieo nền bằng mẫu đầu tiên. Gieo là ngưỡng lập tức thành 1,8 lần mức đang đo,
      // nên chính mức ấy không bao giờ vượt nổi ngưỡng của nó: bộ rình tê liệt, không nhá
      // tiếng lần nào, ngắt lời chết câm. Đã đo thấy trên trang thật 15/09. Nền chỉ được đi
      // lên từ trung bình trượt và từ các lần nhá tiếng kết luận "là vọng".
      const thresh = Math.max(JavisVoice.BARGE_SAN, this._echoFloor * 1.8 + 0.01);
      if (rms > thresh) {
        gan.push(rms);
        if (gan.length > 3) gan.shift();
        if (++hits >= this.bargeMinTicks) {
          this._stopBargeMonitor();
          const pre = gan.reduce((a, b) => a + b, 0) / gan.length;
          this._nhaTiengThuXem(pre);
        }
      } else {
        hits = 0; gan = [];
        this._echoFloor = this._echoFloor * 0.9 + rms * 0.1;   // chỉ học lúc không nghi ngờ
      }
    }, 100);
  }

  // Biên độ sóng (time-domain RMS) của luồng mic ĐÃ khử vọng. Đúng độ TO thật, đáng tin hơn
  // trung bình phổ (bị pha loãng bởi dải tần cao im lặng nên giọng nói không bao giờ chạm
  // ngưỡng). Trả null khi chưa có luồng mic.
  _micRms() {
    if (!this.inAnalyser) return null;
    const N = this.inAnalyser.fftSize || 128;
    if (!this._timeData || this._timeData.length !== N) this._timeData = new Uint8Array(N);
    this.inAnalyser.getByteTimeDomainData(this._timeData);
    let s = 0;
    for (let k = 0; k < N; k++) { const dv = this._timeData[k] - 128; s += dv * dv; }
    return Math.sqrt(s / N) / 128;   // 0..1 (im lặng ~0.005, nói thường ~0.05-0.2)
  }

  // Âm lượng loa theo trạng thái: đang nhá thì nhỏ, không thì đầy. Gọi ở MỌI chỗ gắn audio
  // mới, vì mỗi khúc TTS là một phần tử Audio khác: quên một chỗ là khúc kế tiếp bật lại âm
  // lượng đầy ngay giữa lúc đang thăm dò, hỏng hết phép so.
  _apAmLuong(audio) {
    try { if (audio) audio.volume = this._dangNha ? JavisVoice.NHA_GAIN : 1; } catch (e) {}
  }

  // ---- Nhá tiếng để thăm dò: hạ âm lượng một nhá rồi đo lại ----
  // Vọng của loa tụt theo âm lượng, giọng người thì không. So mức sau khi nhá với mức trước
  // khi nhá là phân biệt được, không cần chờ nhận dạng trả chữ.
  _nhaTiengThuXem(preLevel) {
    if (this._dangNha) return;
    this._dangNha = true;
    this._apAmLuong(this.currentAudio);
    // Web Speech không hạ được âm lượng giữa câu đang đọc, nên đường đó tạm dừng hẳn trong
    // lúc thăm dò (vẫn đúng phép so: vọng biến mất, giọng người thì còn).
    const dungSynth = !this.currentAudio && this.synth && this.synth.speaking;
    if (dungSynth) { try { this.synth.pause(); } catch (e) {} }
    const mau = [];
    this._nhaTimer = setInterval(() => {
      if (!this.isPlaying) { this._ketThucNha(false, preLevel, dungSynth); return; }
      const rms = this._micRms();
      if (rms != null) mau.push(rms);
      if (mau.length >= JavisVoice.NHA_TICKS) {
        this._ketThucNha(JavisVoice.laNguoiThat(preLevel, mau), preLevel, dungSynth);
      }
    }, 100);
  }

  _ketThucNha(laNguoi, preLevel, dungSynth) {
    if (this._nhaTimer) { clearInterval(this._nhaTimer); this._nhaTimer = null; }
    if (!this._dangNha) return;
    this._dangNha = false;
    this._apAmLuong(this.currentAudio);
    if (dungSynth) { try { this.synth.resume(); } catch (e) {} }
    if (laNguoi) {
      this._bargeIn();
      // Lưới an toàn: nơi nhận (đạo diễn) có thể nuốt cú ngắt vì trạng thái lệch. Còn đang
      // đọc sau một nhịp nghĩa là không ai dừng gì cả, phải mở lại bộ rình chứ không thì
      // ngắt lời chết câm tới hết câu trả lời và người dùng không hiểu vì sao.
      setTimeout(() => { if (this.isPlaying && !this._paused) this._startBargeMonitor(); }, 300);
      return;
    }
    // Là vọng của chính mình: nâng nền cho đúng mức ấy thôi nghi ngờ lần nữa, rồi đọc tiếp.
    // Người nghe chỉ thấy tiếng nhỏ đi một nhá, không giật, không câm.
    //
    // Nền leo TỪNG BẬC chứ không nhảy thẳng tới mức vừa đo: một tiếng ho to (0.2) mà nhảy
    // thẳng là nền treo ở đó, ngưỡng vọt lên gần 0.4 và mấy lượt sau nói gì Javis cũng không
    // nghe. Leo bậc thì vọng thật (lặp lại liên tục) vẫn tới nơi sau một hai nhá, còn tiếng
    // ho một lần chỉ đẩy được một bậc nhỏ.
    const tran = (preLevel || 0) * 1.05;
    this._echoFloor = Math.max(this._echoFloor, Math.min(tran, this._echoFloor * 1.6 + 0.02));
    this._nhoNenVong();
    this._startBargeMonitor();
  }

  _stopBargeMonitor() {
    if (this._bargeTimer) { clearInterval(this._bargeTimer); this._bargeTimer = null; }
  }

  // Nhớ nền vọng qua các lần mở trang: phòng của một người thì gần như không đổi, nhớ được
  // thì câu trả lời ĐẦU TIÊN sau khi tải trang đã có ngưỡng đúng, khỏi phải nhá tiếng vài lần
  // để học lại từ số không. Hỏng localStorage (chế độ riêng tư) thì thôi, học lại cũng được.
  _nhoNenVong() {
    try { localStorage.setItem("javis.nenVong", String(this._echoFloor.toFixed(4))); } catch (e) {}
  }

  // Huỷ cuộc thăm dò đang dở (dừng đọc, đổi lượt): trả âm lượng về đầy, không để phần tử
  // Audio kế tiếp thừa hưởng mức nhá.
  _huyNha() {
    if (this._nhaTimer) { clearInterval(this._nhaTimer); this._nhaTimer = null; }
    if (!this._dangNha) return;
    this._dangNha = false;
    this._apAmLuong(this.currentAudio);
    try { if (this.synth && this.synth.paused) this.synth.resume(); } catch (e) {}
  }

  // Đã nhá tiếng và chắc là người thật: DỪNG HẲN, không chờ nhận dạng xác nhận nữa.
  // Đường cũ (onBargeStart) tạm dừng rồi đòi có chữ trong 2 giây mới coi là ngắt thật. Nghe
  // thì chặt chẽ, dùng thì hỏng: nhận dạng chỉ được mở SAU khi tạm dừng, mà Chrome mất 0,5
  // đến 1,5 giây mới trả chữ đầu tiên, nên một tiếng "thôi" hay "dừng lại" đã nói xong trước
  // khi tai kịp mở. Không có chữ nào tới, đạo diễn kết luận chen ngang giả rồi đọc tiếp:
  // đúng cảnh chủ dự án tả 15/09 "nói kiểu gì cũng không dừng được". Nay bằng chứng là phép
  // nhá tiếng, chắc hơn chữ và có trong 400 ms, nên không cần cửa sổ chờ ấy nữa.
  _bargeIn() {
    if (this.onBargeConfirm) {
      try { this.onBargeConfirm(); return; } catch (e) {}
    }
    if (this.onBargeStart) { try { this.onBargeStart(); return; } catch (e) {} }
    this.stopSpeaking();       // dừng đọc ngay (không để chồng tiếng)
    this.startListening(true); // máy tự mở lại (do đo được mức âm), không phải cú bấm
  }

  // ---- Voice V1: tạm dừng / phát tiếp / phần đã đọc ----
  // Tạm dừng audio tại chỗ (không xoá hàng đợi). Recognition được mở bởi app.js ngay sau đó
  // (startListening(true, true)) để xem người dùng có thật sự nói không.
  pauseSpeaking() {
    if (!this.isPlaying || this._paused) return false;
    this._paused = true;
    this._stopBargeMonitor();
    this._huyNha();
    try { if (this.currentAudio) this.currentAudio.pause(); } catch (e) {}
    try { if (this.synth && this.synth.speaking) this.synth.pause(); } catch (e) {}
    return true;
  }

  // Chen ngang giả (2 giây không có chữ): phát tiếp từ chỗ dừng.
  resumeSpeaking() {
    if (!this._paused) return false;
    this._paused = false;
    try { if (this.currentAudio) this.currentAudio.play().catch(() => {}); } catch (e) {}
    try { if (this.synth && this.synth.paused) this.synth.resume(); } catch (e) {}
    this._startBargeMonitor();
    return true;
  }

  // Phần Javis ĐÃ ĐỌC RA TIẾNG trong lượt này: các khúc đã phát xong cộng phần khúc dở theo
  // tỉ lệ thời gian, cắt ở ranh giới từ. Dùng khi bị ngắt lời thật, để tin kế tiếp mang
  // "ngắt_lời=" và model không đọc lại từ đầu (mượn synchronized_transcript của LiveKit).
  static demTu(s) { const m = String(s || "").trim().match(/\S+/g); return m ? m.length : 0; }

  // V3: số từ đã THẬT SỰ ra loa kể từ lần reset (app.js reset khi mở lượt chat mới): khúc đã
  // phát xong cộng phần khúc dở theo tỉ lệ thời gian. Bong bóng chat hiện đúng chừng ấy từ.
  resetSpokenWords() { this._wordsDone = 0; }
  spokenWords() {
    let n = this._wordsDone;
    try {
      const a = this.currentAudio, i = this._chunkIndex;
      if (this._countThis && this.isPlaying && a && this.ttsChunks && i != null && i < this.ttsChunks.length && a.duration > 0) {
        const ratio = Math.max(0, Math.min(1, a.currentTime / a.duration));
        n += Math.floor(JavisVoice.demTu(this.ttsChunks[i]) * ratio);
      }
    } catch (e) {}
    return n;
  }

  lastSpokenPrefix() {
    const parts = (this._spokenChunks || []).slice();
    try {
      const a = this.currentAudio;
      const i = this._chunkIndex;
      if (a && this.ttsChunks && i != null && i < this.ttsChunks.length && a.duration > 0) {
        const text = this.ttsChunks[i];
        const ratio = Math.max(0, Math.min(1, a.currentTime / a.duration));
        let cut = Math.floor(text.length * ratio);
        const sp = text.lastIndexOf(" ", cut);
        if (sp > 0) cut = sp;
        if (cut > 0) parts.push(text.slice(0, cut));
      }
    } catch (e) {}
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }

  _cleanForTTS(text) {
    return text
      .replace(/```[\s\S]*?```/g, " ")        // bỏ code block
      .replace(/\*\*(.+?)\*\*/g, "$1")
      .replace(/\*(.+?)\*/g, "$1")
      .replace(/`(.+?)`/g, "$1")
      .replace(/!\[.*?\]\(.*?\)/g, "")          // ảnh
      .replace(/\[(.+?)\]\(.+?\)/g, "$1")       // link → giữ chữ
      .replace(/^#{1,6}\s+/gm, "")              // heading
      .replace(/^\s*\d+[.)]\s+/gm, "")          // list số
      .replace(/^\s*[-*•]\s+/gm, "")            // list dấu đầu dòng
      .replace(/\s*[\u2014\u2013]\s*/g, ", ")   // gạch ngang em/en (U+2014/2013) -> phẩy (hết khựng khi đọc)
      .replace(/\s*\|\s*/g, ", ")               // ô bảng markdown
      .replace(/\n{2,}/g, ". ")                 // đoạn mới → chấm
      .replace(/\n/g, ", ")                     // xuống dòng → phẩy (liền mạch, vẫn có nhịp thở)
      .replace(/\s*([,.])\s*([,.])/g, "$1")     // dồn dấu trùng (.,  ,. → .)
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  _chunkUrl(text) {
    return `${this.ttsBackend}?text=${encodeURIComponent(text)}&voice=${encodeURIComponent(this.ttsVoice)}&rate=${encodeURIComponent(this.ttsRate)}`;
  }

  async _speakBackend(text) {
    // KHÔNG stopSpeaking ở đây - hàng đợi (_pumpQueue) điều phối thứ tự đọc.
    // Chunk ĐẦU nhỏ (1 câu) để audio đầu tiên tổng hợp + tải NHANH → bớt khựng; các chunk sau to (liền mạch).
    this.ttsChunks = this._splitForLatency(text);
    this._preloaded = null;
    this.isPlaying = true;
    this._playChunk(0);
  }

  // Cắt câu ĐẦU ra riêng cho ngắn (phát nhanh), phần còn lại gộp chunk lớn cho liền mạch.
  _splitForLatency(text) {
    const sentences = text.match(/[^.!?]+[.!?]+|\s*[^.!?]+$/g) || [text];
    let first = (sentences.shift() || "").trim();
    // Câu đầu vẫn dài → cắt tại dấu phẩy đầu tiên cho audio đầu ra thật nhanh.
    if (first.length > 160) {
      const c = first.indexOf(",");
      if (c > 20 && c < 160) { sentences.unshift(first.slice(c + 1)); first = first.slice(0, c + 1).trim(); }
    }
    const chunks = [];
    if (first) chunks.push(first);
    const rest = sentences.join("").trim();
    if (rest) chunks.push(...this._splitIntoChunks(rest, 600));
    return chunks.filter(c => c.length > 0);
  }

  _playChunk(i, retry) {
    // Hết chunk của đoạn này → chuyển sang đoạn kế trong hàng đợi (không tự dừng).
    if (!this.ttsChunks || i >= this.ttsChunks.length) { this._pumpQueue(); return; }
    if (this._laIOS()) {
      // Đường iOS: một phần tử Audio dùng lại, KHÔNG preload, KHÔNG nối qua AudioContext
      // (createMediaElementSource trên WebKit hay làm câm tiếng khi context chưa chạy).
      this._moKhoaAudioIOS();
      const a = this._iosAudio || (this._iosAudio = new Audio());
      a.onended = null; a.onerror = null;
      a.src = this._chunkUrl(this.ttsChunks[i]) + (retry ? "&retry=1" : "");
      this.currentAudio = a;
      this._apAmLuong(a);      // đang nhá tiếng thăm dò thì khúc mới cũng phải nhỏ theo
      this._chunkIndex = i;
      let done = false;
      const onFail = () => { if (done) return; done = true; a.onerror = null; this._chunkFailed(i, retry); };
      a.onended = () => {
        if (done) return;
        if (this._countThis) this._wordsDone += JavisVoice.demTu(this.ttsChunks[i]);
        this._playChunk(i + 1);
      };
      a.onerror = onFail;
      a.play().catch(onFail);
      return;
    }
    // Dùng audio đã preload nếu trùng URL (cùng đoạn hay đoạn kế trong hàng đợi), không thì
    // tạo mới (retry = tạo mới, tránh cache lỗi).
    const url = this._chunkUrl(this.ttsChunks[i]);
    let audio = (!retry && this._preloaded && this._preloaded.url === url) ? this._preloaded.audio
              : new Audio(url + (retry ? "&retry=1" : ""));
    this._preloaded = null;
    this.currentAudio = audio;
    this._apAmLuong(audio);    // đang nhá tiếng thăm dò thì khúc mới cũng phải nhỏ theo
    this._chunkIndex = i;
    // Đo mạng: từ lúc gọi play() tới lúc thật sự phát. Quá slowMs thì báo "mạng chậm" - đây là
    // số đo thật, không phải trạng thái vẽ cho có (spec Voice V1 mục 4).
    const _t0 = Date.now();
    audio.onplaying = () => {
      const cham = (Date.now() - _t0) > 2500;
      if (this.onSlow && cham !== !!this._slowFlag) { this._slowFlag = cham; try { this.onSlow(cham); } catch (e) {} }
    };

    // Route analyser (cho hiệu ứng glow) chỉ khi context chạy + chưa route
    try {
      const ctx = this._ensureCtx();
      if (ctx && ctx.state === "running" && !audio.__routed) {
        audio.crossOrigin = "anonymous";
        const src = ctx.createMediaElementSource(audio);
        const an = ctx.createAnalyser();
        an.fftSize = 128;
        src.connect(an);
        an.connect(ctx.destination);
        this.outAnalyser = an;
        audio.__routed = true;
      }
    } catch (e) { /* phát thẳng vẫn ổn */ }

    // PRELOAD khúc kế tiếp ngay khi khúc này bắt đầu → khi hết là phát liền, không trống;
    // khúc cuối thì tải trước đoạn KẾ trong hàng đợi.
    if (i + 1 < this.ttsChunks.length) this._preloadUrl(this._chunkUrl(this.ttsChunks[i + 1]));
    else this._preloadNextQueued();

    // Một audio lỗi thì Chrome bắn CẢ sự kiện 'error' LẪN play() reject → phải chống xử lý 2 lần
    // (nếu không: 2 retry chồng nhau + audio mồ côi stopSpeaking không dừng được). Cờ handled = xử lý đúng 1 lần.
    let handled = false;
    const onFail = () => {
      if (handled) return;
      handled = true;
      audio.onerror = null;
      this._chunkFailed(i, retry);   // thử lại backend, vẫn hỏng mới cân nhắc trình duyệt (không rơi tiếng Anh)
    };
    audio.onended = () => {
      if (handled) return;
      this._spokenChunks.push(this.ttsChunks[i]);   // khúc này đã ra tiếng trọn vẹn
      if (this._countThis) this._wordsDone += JavisVoice.demTu(this.ttsChunks[i]);
      this._playChunk(i + 1);
    };
    audio.onerror = onFail;
    audio.play().catch(onFail);
  }

  // Đoạn TTS backend lỗi: thử LẠI backend 1 lần (lỗi mạng chốc lát) để GIỮ giọng Việt;
  // vẫn hỏng thì TUYỆT ĐỐI không rơi về giọng mặc định (thường là tiếng Anh) khi đang đọc tiếng Việt -
  // đó chính là "giọng Anh lạ chèn giữa chừng". Có giọng đúng ngôn ngữ trong máy thì đọc, không thì BỎ đoạn.
  _chunkFailed(i, retry) {
    if (!this.ttsChunks || i >= this.ttsChunks.length) { this._pumpQueue(); return; }
    if (!retry) { this._playChunk(i, true); return; }
    const okBrowserVoice = this.lang.startsWith("vi") ? !!this.vietnameseVoice : true;
    if (okBrowserVoice) this._speakBrowser(this.ttsChunks[i], () => this._playChunk(i + 1));
    else {
      // Khúc bị BỎ vẫn tính là đã qua, kẻo bong bóng hiện chữ theo lời kẹt lại ở khúc đó.
      if (this._countThis) this._wordsDone += JavisVoice.demTu(this.ttsChunks[i]);
      this._playChunk(i + 1);
    }
  }

  // onDone: gọi khi đọc xong đoạn (mặc định: lấy đoạn kế trong hàng đợi).
  _speakBrowser(text, onDone) {
    const done = onDone || (() => this._pumpQueue());
    const chunks = this._splitIntoChunks(text, 200);
    let idx = 0;
    const playNext = () => {
      if (idx >= chunks.length) { done(); return; }
      const piece = chunks[idx++];
      const utter = new SpeechSynthesisUtterance(piece);
      utter.lang = this.lang;
      if (this.vietnameseVoice) utter.voice = this.vietnameseVoice;
      utter.rate = 1.05;
      utter.onend = () => { if (this._countThis) this._wordsDone += JavisVoice.demTu(piece); playNext(); };
      utter.onerror = playNext;
      this.synth.speak(utter);
    };
    playNext();
  }

  stopSpeaking() {
    const dangDoc = this.isPlaying;
    this._stopBargeMonitor();
    this._huyNha();            // đang thăm dò dở thì bỏ, và trả âm lượng về đầy
    this._paused = false;
    this.synth.cancel();
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio = null;
    }
    if (dangDoc && this.onSpeakEnd) { try { this.onSpeakEnd(); } catch (e) {} }
    if (this._preloaded && this._preloaded.audio) {
      try { this._preloaded.audio.pause(); } catch (e) {}
    }
    this._preloaded = null;
    this.ttsChunks = null;
    this.ttsQueue = [];
    this.speechQueue = [];
    this._lastQueued = "";
    this.isPlaying = false;
    this._resumeRecognitionIfNeeded();   // mic từng bị tạm ngừng vì TTS → mở nghe lại
  }

  setVoice(voiceName) {
    this.ttsVoice = voiceName;
  }

  setRate(rate) {
    this.ttsRate = rate;
  }

  setRecognitionLang(lang) {
    this.lang = lang;
    if (this.recognition) this.recognition.lang = lang;
  }

  toggleTTS() {
    this.ttsEnabled = !this.ttsEnabled;
    try { localStorage.setItem("javis.ttsEnabled", this.ttsEnabled ? "1" : "0"); } catch (e) {}
    if (!this.ttsEnabled) this.stopSpeaking();
    return this.ttsEnabled;
  }

  _splitIntoChunks(text, maxLen) {
    const sentences = text.match(/[^.!?]+[.!?]+|\s*[^.!?]+$/g) || [text];
    const chunks = [];
    let current = "";
    for (const s of sentences) {
      if ((current + s).length > maxLen && current) {
        chunks.push(current.trim());
        current = s;
      } else {
        current += s;
      }
    }
    if (current.trim()) chunks.push(current.trim());
    return chunks.filter(c => c.length > 0);
  }

  // Đang TẠM DỪNG (nghi chen ngang) thì KHÔNG tính là đang nói: onresult phải nhận chữ lúc
  // này, vì đó chính là bằng chứng phân biệt chen ngang thật với tiếng ho.
  isSpeaking() {
    if (this._paused) return false;
    return this.isPlaying || (this.synth && this.synth.speaking);
  }

  isPaused() { return !!this._paused; }

  isSupported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }
}

window.JavisVoice = JavisVoice;
