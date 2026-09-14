/* voice-turn.js - ĐẠO DIỄN hội thoại bằng giọng (Voice V1, docs/dev/2026-09-voice-v1-spec.md mục 3).

   Module THUẦN: không đụng DOM, không gọi recognition hay audio. voice.js và app.js bắn sự kiện
   vào đây, nhận về một MẢNG hành động rồi tự thực hiện. Nhờ vậy toàn bộ luật "ai đang nói, đã
   nói xong chưa, có được ngắt không, có nên gửi không" nằm gọn một chỗ và test được bằng node.

   Thiết kế mượn từ livekit/agents (voice/turn.py, voice/audio_recognition.py,
   voice/agent_activity.py), đọc 2026-09-14:
     - endpointing HAI ngưỡng: câu trông chưa xong thì chờ lâu (maxDelay), còn lại chờ ngắn;
     - chen ngang phải đủ 500 ms tiếng nói, TẠM DỪNG trước rồi mới huỷ; 2 giây không có chữ
       nào thì coi là chen ngang giả (ho, tiếng ngoài) và phát tiếp;
     - không bao giờ chốt một lượt rỗng;
     - tin nền chỉ được đọc khi người dùng không đang nói.
   LiveKit không có tiếng Việt trong bảng ngưỡng dò hết lượt, nên ở đây dùng luật cụm từ và
   liên từ, không có mô hình.

   Trạng thái được SUY từ cờ (mic, userSpeaking, waiting, processing, speaking, interrupted,
   ws, error) theo thứ tự ưu tiên trong _recompute(), thay vì viết tay từng cặp chuyển trạng
   thái: cách đó có 9x9 ô để quên, cách này chỉ có một danh sách ưu tiên.

   Ghi chú: KHÔNG dùng ký tự em dash ở bất kỳ đâu. */
(function () {
  "use strict";

  var DEFAULTS = {
    minDelay: 800,          // ms im lặng để gửi khi câu trông đã xong
    maxDelay: 2200,         // ms im lặng khi câu trông CHƯA xong (kết bằng liên từ, dấu phẩy)
    bargeMinTicks: 5,       // nhịp 100 ms tiếng nói liên tiếp mới coi là chen ngang (500 ms)
    falseInterruptMs: 2000, // sau khi tạm dừng, không có chữ trong chừng này thì phát tiếp
    waitTimeoutMs: 90000,   // "khoan" rồi im 90 giây thì thôi chờ
    slowMs: 2500,           // khúc TTS mất hơn chừng này mới phát = mạng chậm
    fillerMs: 2500,         // xử lý chừng này ms chưa có chữ nào ra loa thì nói câu tiến độ (V3)
    fillerToolMs: 1200      // đang gọi tool thì nói sớm hơn: chắc chắn còn lâu
  };

  // ---- Cụm từ (đã chuẩn hoá: thường, không dấu câu) ----
  var WAIT = [
    "khoan", "khoan da", "khoan đã", "đợi", "đợi chút", "đợi đã", "đợi mình", "đợi anh", "đợi em",
    "đợi tôi", "đợi tí", "đợi xíu", "từ từ", "chờ chút", "chờ tí", "chờ xíu", "chờ mình", "chờ anh",
    "chờ em", "để mình nghĩ", "để anh nghĩ", "để em nghĩ", "để tôi nghĩ", "chưa xong", "chưa nói xong",
    "wait", "hold on", "hang on", "one sec", "one second", "give me a second", "give me a sec",
    "let me think", "just a moment", "just a sec", "not yet"
  ];
  var STOP = [
    "thôi", "dừng", "dừng lại", "im", "im đi", "đủ rồi", "ngừng", "thôi đủ rồi", "thôi khỏi",
    "dừng đi", "stop", "enough", "never mind", "nevermind", "cancel", "shut up", "stop it"
  ];
  // Tiểu từ đuôi / xưng hô không mang nghĩa lệnh: "khoan đã nhé", "đợi chút nào".
  var PARTICLES = ["nhé", "nha", "nhá", "đã", "đi", "chút", "xíu", "tí", "nào", "ạ", "với", "please",
                   "javis", "ơi", "nghen", "nhen", "hen", "đây", "cái"];
  var LEAD = ["javis ơi", "ê javis", "này javis", "javis", "ơi", "ê", "này", "hey javis", "hey", "ok javis"];

  // Câu kết bằng một trong các từ này thì rất có thể người dùng còn nói tiếp. Nhóm cuối là
  // tiếng ậm ừ lúc đang NGHĨ ("ừm", "ờ", "kiểu", "cái"): dừng để nghĩ, không phải dừng hẳn (V3,
  // gợi ý endpointing thông minh). Không có "à" vì "vậy à" là câu hỏi đã xong.
  var UNFINISHED = [
    "và", "nhưng", "thì", "là", "với", "rồi", "để", "mà", "hoặc", "hay", "nếu", "vì", "còn", "cho",
    "của", "về", "như", "khi", "lúc", "nên", "bằng", "từ", "đến", "tới", "tại", "bởi", "trong",
    "ngoài", "trên", "dưới", "sau", "trước", "cùng", "hãy", "rằng", "là", "the", "and", "but",
    "then", "so", "with", "to", "a", "an", "of", "or", "if", "because", "that", "when", "for",
    "in", "on", "at", "is", "are", "was", "were", "which", "who", "how", "what", "where",
    "ừm", "ờ", "ơ", "kiểu", "cái", "um", "uh", "hmm", "like"
  ];

  // Từ vựng của các cụm CHỜ / DỪNG, để nhận cả bản nói lắp hay lặp ("từ từ đợi đợi đợi chút"):
  // mọi từ đều thuộc bộ này VÀ có ít nhất một cụm nguyên vẹn nằm trong câu thì vẫn là CHỜ.
  function vocabOf(phrases) {
    var set = {};
    for (var i = 0; i < phrases.length; i++) {
      var toks = phrases[i].split(" ");
      for (var k = 0; k < toks.length; k++) set[toks[k]] = true;
    }
    for (var p = 0; p < PARTICLES.length; p++) set[PARTICLES[p]] = true;
    return set;
  }
  var WAIT_VOCAB = vocabOf(WAIT), STOP_VOCAB = vocabOf(STOP);

  function loosePhrase(core, phrases, vocab) {
    if (!core) return false;
    var toks = core.split(" ");
    for (var i = 0; i < toks.length; i++) if (!vocab[toks[i]]) return false;
    var padded = " " + core + " ";
    for (var j = 0; j < phrases.length; j++) if (padded.indexOf(" " + phrases[j] + " ") >= 0) return true;
    return false;
  }

  function normalize(text) {
    var s = String(text == null ? "" : text).toLowerCase();
    // Bỏ dấu câu và ký tự lạ nhưng GIỮ chữ có dấu tiếng Việt.
    s = s.replace(/[.,!?;:"'()\[\]{}…\-]+/g, " ");
    return s.replace(/\s+/g, " ").trim();
  }

  function stripLead(s) {
    for (var k = 0; k < 3; k++) {
      var hit = false;
      for (var i = 0; i < LEAD.length; i++) {
        var l = LEAD[i];
        if (s === l) return "";
        if (s.indexOf(l + " ") === 0) { s = s.slice(l.length + 1); hit = true; break; }
      }
      if (!hit) break;
    }
    return s;
  }

  function stripParticles(s) {
    var toks = s.split(" ");
    while (toks.length > 1 && PARTICLES.indexOf(toks[toks.length - 1]) >= 0) toks.pop();
    return toks.join(" ");
  }

  function coreOf(text) {
    var s = stripLead(normalize(text));
    return stripParticles(s);
  }

  function isWaitPhrase(text) {
    var c = coreOf(text);
    return !!c && (WAIT.indexOf(c) >= 0 || loosePhrase(c, WAIT, WAIT_VOCAB));
  }

  function isStopPhrase(text) {
    var c = coreOf(text);
    return !!c && (STOP.indexOf(c) >= 0 || loosePhrase(c, STOP, STOP_VOCAB));
  }

  function looksUnfinished(text) {
    var raw = String(text == null ? "" : text).trim();
    if (!raw) return false;
    if (/[,;:]$/.test(raw)) return true;
    var toks = normalize(raw).split(" ");
    var last = toks[toks.length - 1];
    return !!last && UNFINISHED.indexOf(last) >= 0;
  }

  function hasWord(text) {
    return /[\p{L}\p{N}]/u.test(String(text == null ? "" : text));
  }

  // ---- Đạo diễn ----
  function VoiceTurn(opts) {
    this.opts = {};
    for (var k in DEFAULTS) this.opts[k] = DEFAULTS[k];
    for (var k2 in (opts || {})) if (opts[k2] != null) this.opts[k2] = opts[k2];
    this.state = "idle";
    this.ws = true;
    this.mic = false;
    this.userSpeaking = false;
    this.waiting = false;
    this.processing = false;
    this.speaking = false;
    this.interrupted = false;
    this.tool = "";
    this.error = "";
    this.background = 0;
    this.slow = false;
    this.deferred = [];
    this.interruptedAt = "";   // câu Javis đọc tới lúc bị ngắt, đi vào tin kế tiếp
    this.history = [];
    this.turnAt = 0;           // mốc ms lượt hiện tại bắt đầu xử lý (V3: câu tiến độ)
    this.spoke = false;        // lượt này đã có chữ THẬT ra loa chưa
    this.fillerDone = false;   // câu tiến độ chỉ nói MỘT lần mỗi lượt
  }

  VoiceTurn.prototype._recompute = function () {
    var s;
    if (!this.ws) s = "reconnecting";
    else if (this.error) s = "error";
    else if (this.interrupted) s = "interrupted";
    else if (this.userSpeaking) s = "user_speaking";
    else if (this.waiting) s = "waiting_for_user";
    else if (this.speaking) s = "speaking";
    else if (this.processing) s = "processing";
    else if (this.mic) s = "listening";
    else s = "idle";
    var prev = this.state;
    this.state = s;
    if (s !== prev) this.history.push(s);
    var acts = [{ type: "state", state: s, prev: prev, tool: this.tool }];
    if (this.deferred.length && this.canSpeakNow()) acts.push({ type: "flush_deferred", texts: this.takeDeferred() });
    return acts;
  };

  VoiceTurn.prototype.canSpeakNow = function () {
    return this.state === "idle" || this.state === "listening";
  };

  VoiceTurn.prototype.delayFor = function (text) {
    return looksUnfinished(text) ? this.opts.maxDelay : this.opts.minDelay;
  };

  VoiceTurn.prototype.micOn = function () {
    this.mic = true; this.error = "";
    return this._recompute();
  };

  VoiceTurn.prototype.micOff = function () {
    this.mic = false; this.userSpeaking = false; this.waiting = false; this.interrupted = false;
    return this._recompute();
  };

  // Chữ tạm từ recognition. Đang tạm dừng vì nghi chen ngang thì đây chính là bằng chứng.
  VoiceTurn.prototype.interim = function (text) {
    if (this.interrupted) return this.bargeText(text);
    if (!hasWord(text)) return [];
    this.userSpeaking = true;
    this.waiting = false;
    var acts = [{ type: "arm_endpoint", ms: this.delayFor(text) }];
    return acts.concat(this._recompute());
  };

  // Đồng hồ im lặng nổ (hoặc recognition kết thúc) với toàn bộ chữ đã nghe.
  VoiceTurn.prototype.endpoint = function (text) {
    this.userSpeaking = false;
    var t = String(text == null ? "" : text).trim();
    var acts = [];
    if (!hasWord(t)) return this._recompute();           // không bao giờ chốt lượt rỗng
    if (isWaitPhrase(t)) {
      this.waiting = true;
      acts.push({ type: "hold" });
      if (this.speaking) { this.speaking = false; acts.push({ type: "stop_tts" }); }
      return acts.concat(this._recompute());
    }
    if (isStopPhrase(t)) {
      if (this.speaking) { this.speaking = false; acts.push({ type: "stop_tts" }); }
      if (this.processing) { acts.push({ type: "stop_turn" }); }
      this.waiting = false;
      return acts.concat(this._recompute());
    }
    this.waiting = false;
    this.processing = true;
    this.tool = "";
    acts.push({ type: "commit", text: t, interruptedAt: this.interruptedAt });
    this.interruptedAt = "";
    return acts.concat(this._recompute());
  };

  VoiceTurn.prototype.turnStart = function (now) {
    this.processing = true; this.tool = "";
    this.turnAt = now || Date.now();
    this.spoke = false; this.fillerDone = false;
    return this._recompute();
  };

  VoiceTurn.prototype.turnDone = function () {
    this.processing = false; this.tool = "";
    this.turnAt = 0;
    return this._recompute();
  };

  // Chữ thật của câu trả lời vừa ra loa: từ giờ không cần câu tiến độ nữa.
  VoiceTurn.prototype.noteSpoke = function () { this.spoke = true; };

  // Câu TIẾN ĐỘ (V3, gợi ý "vừa nói tiến độ vừa trả dần kết quả"): xử lý đã lâu mà loa còn im
  // thì nói một câu ngắn kiểu "để mình xem nhé", đúng một lần mỗi lượt. Đang gọi tool thì nói
  // sớm hơn vì chắc chắn còn lâu. Hàm chỉ quyết ĐẾN LÚC chưa; nói câu gì là việc của app.js.
  VoiceTurn.prototype.fillerCheck = function (now) {
    if (!this.processing || this.spoke || this.fillerDone || !this.turnAt) return [];
    var wait = this.tool ? this.opts.fillerToolMs : this.opts.fillerMs;
    if ((now || Date.now()) - this.turnAt < wait) return [];
    this.fillerDone = true;
    return [{ type: "speak_filler" }];
  };

  VoiceTurn.prototype.toolCall = function (name) {
    this.processing = true;
    this.tool = String(name || "");
    return this._recompute();
  };

  VoiceTurn.prototype.ttsStart = function () {
    this.speaking = true; this.interrupted = false;
    return this._recompute();
  };

  VoiceTurn.prototype.ttsEnd = function () {
    this.speaking = false; this.interrupted = false;
    return this._recompute();
  };

  // Bộ rình RMS đủ 500 ms tiếng nói trong lúc Javis đang đọc.
  VoiceTurn.prototype.bargeStart = function () {
    if (!this.speaking || this.interrupted) return [];
    this.interrupted = true;
    return [{ type: "pause_tts" }, { type: "listen" }].concat(this._recompute());
  };

  // Có chữ thật trong lúc tạm dừng -> chen ngang THẬT: dừng hẳn, nhớ phần đã đọc.
  VoiceTurn.prototype.bargeText = function (text, spokenPrefix) {
    if (!this.interrupted) return [];
    if (!hasWord(text)) return [];
    this.interrupted = false;
    this.speaking = false;
    this.userSpeaking = true;
    if (spokenPrefix) this.interruptedAt = String(spokenPrefix);
    return [{ type: "stop_tts", interrupted: true }, { type: "arm_endpoint", ms: this.delayFor(text) }]
      .concat(this._recompute());
  };

  // voice.js đã NHÁ TIẾNG và chắc là người thật (vọng tụt theo âm lượng, giọng người thì
  // không): dừng hẳn và mở tai, KHÔNG qua cửa sổ chờ chữ 2 giây. Cửa sổ ấy vốn là cách duy
  // nhất để phân biệt chen ngang thật với tiếng vọng, nhưng nhận dạng chỉ mở SAU khi tạm
  // dừng nên một tiếng "thôi" ngắn không bao giờ kịp lọt vào, và câu trả lời cứ thế đọc tiếp.
  VoiceTurn.prototype.bargeConfirmed = function (spokenPrefix) {
    if (!this.speaking) return [];
    this.interrupted = false;
    this.speaking = false;
    this.userSpeaking = true;
    if (spokenPrefix) this.interruptedAt = String(spokenPrefix);
    var acts = [{ type: "stop_tts", interrupted: true }];
    // Cắt lời giữa chừng nghĩa là THÔI, không cần nốt câu trả lời ấy nữa: dừng luôn lượt đang
    // chạy, y như cụm "thôi / dừng lại" trong endpoint(). Để lượt chạy tiếp thì server vẫn đẻ
    // chữ cho một câu không ai nghe, và tệ hơn: phiên còn "đang trả lời" nên câu người dùng
    // vừa chen vào sẽ bị chặn không gửi được.
    if (this.processing) { this.processing = false; acts.push({ type: "stop_turn" }); }
    acts.push({ type: "listen" });
    return acts.concat(this._recompute());
  };

  // 2 giây không có chữ -> chen ngang GIẢ: phát tiếp, đóng recognition.
  VoiceTurn.prototype.bargeTimeout = function () {
    if (!this.interrupted) return [];
    this.interrupted = false;
    return [{ type: "resume_tts" }, { type: "abort_listen" }].concat(this._recompute());
  };

  VoiceTurn.prototype.setInterruptedAt = function (text) { this.interruptedAt = String(text || ""); };

  VoiceTurn.prototype.wsDown = function () { this.ws = false; return this._recompute(); };
  VoiceTurn.prototype.wsUp = function () { this.ws = true; return this._recompute(); };

  VoiceTurn.prototype.waitTimeout = function () {
    if (!this.waiting) return [];
    this.waiting = false;
    return this._recompute();
  };

  VoiceTurn.prototype.errorMic = function (code) {
    this.error = String(code || "error"); this.mic = false; this.userSpeaking = false;
    return this._recompute();
  };

  VoiceTurn.prototype.clearError = function () { this.error = ""; return this._recompute(); };

  VoiceTurn.prototype.setBackground = function (n) {
    this.background = Math.max(0, parseInt(n, 10) || 0);
    return this._recompute();
  };

  VoiceTurn.prototype.setSlow = function (v) {
    this.slow = !!v;
    return this._recompute();
  };

  // Tin nền (frame push) chỉ được đọc khi người dùng không đang nói.
  VoiceTurn.prototype.defer = function (text) {
    if (text) this.deferred.push(String(text));
  };
  VoiceTurn.prototype.takeDeferred = function () {
    var d = this.deferred; this.deferred = []; return d;
  };

  var api = {
    VoiceTurn: VoiceTurn, DEFAULTS: DEFAULTS,
    normalize: normalize, coreOf: coreOf,
    isWaitPhrase: isWaitPhrase, isStopPhrase: isStopPhrase, looksUnfinished: looksUnfinished
  };
  if (typeof window !== "undefined") window.JavisVoiceTurn = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
