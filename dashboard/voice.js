// ============================================
// JAVIS OS - Voice Layer (Web Speech API)
// ============================================

class JavisVoice {
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
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;

    this.accumulatedTranscript = "";
    this.userStopped = false;                 // user chủ động dừng?
    this.silenceMs = 1500;                    // im lặng bao lâu thì tự gửi
    this._silenceTimer = null;
    this._starting = false;                   // đã gọi start() nhưng onstart chưa chạy
    this._stopPending = false;                // có lệnh dừng tới trong lúc đang mở phiên

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
      let interim = "", final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) final += transcript;
        else interim += transcript;
      }
      if (final) this.accumulatedTranscript += final + " ";
      // Show user toàn bộ tích lũy + đoạn đang nghe
      const display = (this.accumulatedTranscript + interim).trim();
      if (display) {
        this.onInterim(display);
        // Reset đồng hồ im lặng - nói tiếp thì hoãn, im đủ lâu thì tự gửi
        clearTimeout(this._silenceTimer);
        this._silenceTimer = setTimeout(() => this.stopListening(), this.silenceMs);
      }
    };

    this.recognition.onerror = (event) => {
      this._starting = false;
      // 'no-speech' không phải lỗi thật - auto-restart
      if (event.error === "no-speech" || event.error === "aborted") {
        return;
      }
      this.isListening = false;
      this.onError(event.error);
    };

    this.recognition.onend = () => {
      this._starting = false;
      // Nếu user chưa chủ động dừng → tự restart (giữ session sống khi user dừng nghĩ)
      if (!this.userStopped) {
        try {
          this.recognition.start();
          return;
        } catch (e) {
          // start fail (đã đang chạy) - ignore
        }
      }
      this.isListening = false;
      // Gửi toàn bộ text đã tích luỹ khi user dừng
      const finalText = this.accumulatedTranscript.trim();
      if (finalText) this.onTranscript(finalText);
      this.onEnd();
    };
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

  startListening() {
    if (!this.recognition) {
      this.onError("not-supported");
      return;
    }
    if (this.isListening) return;
    // Mở nghe chủ động → huỷ mọi lịch tự-mở-lại còn treo
    this._resumeAfterTTS = false;
    clearTimeout(this._resumeTimer);
    // Stop TTS đang đọc nếu user bấm nói
    this.synth.cancel();
    this.stopSpeaking();
    this._startMicMeter();  // bật đo âm mic cho hiệu ứng phát sáng
    try {
      this._stopPending = false;
      this._starting = true;
      this.recognition.start();
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
    this.speechQueue.push(clean);
    if (!this.isPlaying) this._pumpQueue();
  }

  // Lấy đoạn kế trong hàng đợi để đọc; hết hàng đợi thì dừng.
  _pumpQueue() {
    if (!this.speechQueue || this.speechQueue.length === 0) {
      this.isPlaying = false;
      this._stopBargeMonitor();
      this._resumeRecognitionIfNeeded();             // đọc xong hết → mở nghe lại nếu trước đó mic đang mở
      return;
    }
    this.isPlaying = true;
    this._muteRecognition();                         // mic đang mở → tạm ngừng NHẬN DẠNG, khỏi thu giọng TTS vào chat
    this._startBargeMonitor();                       // cho phép ngắt lời bằng giọng khi đang đọc
    const text = this.speechQueue.shift();
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
    try { this.recognition.abort(); } catch (e) {}
  }

  // Đọc xong (hoặc bị dừng) → mở nghe lại nếu mic từng bị tạm ngừng vì TTS.
  // Chờ một nhịp cho đuôi âm tắt hẳn; phiên nhận dạng MỚI nên không dính giọng TTS cũ.
  _resumeRecognitionIfNeeded() {
    if (!this._resumeAfterTTS) return;
    this._resumeAfterTTS = false;
    clearTimeout(this._resumeTimer);
    this._resumeTimer = setTimeout(() => {
      if (!this.isPlaying && !this.isListening) this.startListening();
    }, 400);
  }

  // ---- Ngắt lời (barge-in): đang đọc mà nghe user nói đủ to/đủ lâu → dừng đọc + mở nghe ngay ----
  _startBargeMonitor() {
    // Ngắt lời chỉ khi user THỰC SỰ dùng giọng (đã cấp mic). Đo BIÊN ĐỘ SÓNG (time-domain RMS) từ
    // luồng mic ĐÃ khử vọng - đúng độ TO thật, đáng tin hơn trung bình phổ (bị pha loãng bởi dải tần
    // cao im lặng nên giọng nói không bao giờ chạm ngưỡng). Tự HIỆU CHỈNH theo nền (echo + ồn) đo
    // trong ~600ms đầu để hợp mọi máy/môi trường, hạn chế tự-ngắt do nghe lại chính giọng TTS.
    // CHỈ rình khi mic ĐANG mở và vừa bị tạm ngừng vì TTS (_resumeAfterTTS). Không có chốt này
    // thì luồng mic mở từ lần nói trước còn sống suốt đời trang, nên MỌI lần Javis đọc đều rình:
    // một tiếng động đủ to trong phòng (nhạc, TV, người khác nói) là mic tự mở, chép lại rồi tự
    // gửi thành tin nhắn của người dùng. Mic đang tắt thì Javis không được phép tự nghe lại.
    if (!this._resumeAfterTTS) return;
    if (this._bargeTimer || !this.micStream || !this.inAnalyser) return;
    const N = this.inAnalyser.fftSize || 128;
    if (!this._timeData || this._timeData.length !== N) this._timeData = new Uint8Array(N);
    let hits = 0, ticks = 0, baseline = 0;
    this._bargeTimer = setInterval(() => {
      if (!this.isPlaying) { this._stopBargeMonitor(); return; }
      this.inAnalyser.getByteTimeDomainData(this._timeData);
      let s = 0;
      for (let k = 0; k < N; k++) { const dv = this._timeData[k] - 128; s += dv * dv; }
      const rms = Math.sqrt(s / N) / 128;   // 0..1 (im lặng ~0.005, nói thường ~0.05-0.2)
      ticks++;
      if (ticks <= 6) { baseline = Math.max(baseline, rms); return; }   // ~600ms đầu: đo nền/echo
      const thresh = Math.max(0.045, baseline * 2 + 0.02);             // vượt HẲN nền mới coi là user nói
      if (rms > thresh) { if (++hits >= 3) { this._stopBargeMonitor(); this._bargeIn(); } }   // ~300ms liên tục
      else hits = 0;
    }, 100);
  }

  _stopBargeMonitor() {
    if (this._bargeTimer) { clearInterval(this._bargeTimer); this._bargeTimer = null; }
  }

  _bargeIn() {
    this.stopSpeaking();       // dừng đọc ngay (không để chồng tiếng)
    this.startListening();     // user muốn nói → mở nghe luôn, bắt trọn câu
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
    // Dùng audio đã preload nếu trùng index, không thì tạo mới (retry = tạo mới, tránh cache lỗi).
    let audio = (!retry && this._preloaded && this._preloaded.i === i) ? this._preloaded.audio
              : new Audio(this._chunkUrl(this.ttsChunks[i]) + (retry ? "&retry=1" : ""));
    this._preloaded = null;
    this.currentAudio = audio;

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

    // PRELOAD đoạn kế tiếp ngay khi đoạn này bắt đầu → khi hết là phát liền, không trống
    if (i + 1 < this.ttsChunks.length) {
      const na = new Audio(this._chunkUrl(this.ttsChunks[i + 1]));
      na.preload = "auto";
      try { na.load(); } catch (e) {}
      this._preloaded = { i: i + 1, audio: na };
    }

    // Một audio lỗi thì Chrome bắn CẢ sự kiện 'error' LẪN play() reject → phải chống xử lý 2 lần
    // (nếu không: 2 retry chồng nhau + audio mồ côi stopSpeaking không dừng được). Cờ handled = xử lý đúng 1 lần.
    let handled = false;
    const onFail = () => {
      if (handled) return;
      handled = true;
      audio.onerror = null;
      this._chunkFailed(i, retry);   // thử lại backend, vẫn hỏng mới cân nhắc trình duyệt (không rơi tiếng Anh)
    };
    audio.onended = () => { if (!handled) this._playChunk(i + 1); };
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
    else this._playChunk(i + 1);
  }

  // onDone: gọi khi đọc xong đoạn (mặc định: lấy đoạn kế trong hàng đợi).
  _speakBrowser(text, onDone) {
    const done = onDone || (() => this._pumpQueue());
    const chunks = this._splitIntoChunks(text, 200);
    let idx = 0;
    const playNext = () => {
      if (idx >= chunks.length) { done(); return; }
      const utter = new SpeechSynthesisUtterance(chunks[idx++]);
      utter.lang = this.lang;
      if (this.vietnameseVoice) utter.voice = this.vietnameseVoice;
      utter.rate = 1.05;
      utter.onend = playNext;
      utter.onerror = playNext;
      this.synth.speak(utter);
    };
    playNext();
  }

  stopSpeaking() {
    this._stopBargeMonitor();
    this.synth.cancel();
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio = null;
    }
    if (this._preloaded && this._preloaded.audio) {
      try { this._preloaded.audio.pause(); } catch (e) {}
    }
    this._preloaded = null;
    this.ttsChunks = null;
    this.ttsQueue = [];
    this.speechQueue = [];
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

  isSpeaking() {
    return this.isPlaying || (this.synth && this.synth.speaking);
  }

  isSupported() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }
}

window.JavisVoice = JavisVoice;
