/* voice-chunker.js - CẮT CỤM tự nhiên cho loa (Voice V3, docs/dev/2026-09-voice-v2-spec.md mục 11).

   Module THUẦN: không đụng DOM, không gọi TTS. app.js đổ từng mẩu chữ stream vào đây và
   nhận về những cụm ĐỌC ĐƯỢC; mỗi cụm là một yêu cầu TTS. Trước đây mỗi khung stream của bộ
   não chính (vài từ) là một yêu cầu Edge TTS riêng, nên nghe giật, cà nhắc và hay báo MẠNG
   CHẬM (làn nhanh đã sửa ở 0.57.2 phía server, làn chính thì chưa). Nay MỌI làn đi qua đây.

   Luật cắt (theo thứ tự ưu tiên, mượn gợi ý của ChatGPT Voice 2026-09-14):
     1. Dấu kết câu (. ! ? …) hay xuống dòng: cắt tới dấu cuối cùng đang có (gộp mấy câu ngắn
        thành một cụm cho ít yêu cầu TTS).
     2. Cụm ĐẦU của lượt ngắn hơn để tiếng đầu ra nhanh: đủ `firstWords` từ mà có dấu phẩy hay
        liên từ chuyển ý thì cắt ở đó; đủ `firstMaxWords` mà không có điểm đẹp thì cắt ở khoảng
        trắng cuối.
     3. Cụm sau dài hơn cho mạch nói tự nhiên: chỉ cắt giữa câu khi đoạn dở quá `maxChars`.
     4. Quá `staleMs` không có chữ mới mà LOA ĐANG IM thì đẩy cụm hiện tại (từ `minStaleWords`
        từ trở lên) ở điểm đẹp gần nhất, để loa không im mãi khi model chậm. Loa đang bận thì
        không đẩy: chờ không mất gì cả, còn đẩy sớm là thêm một yêu cầu TTS vô ích.
   Khối mã ``` chưa khép thì giữ lại tới khi khép (đọc nửa khối mã là rác). Khối `<!-- ... -->`
   (JAVIS_ASK) luôn ở cuối câu trả lời: gặp `<!--` là bỏ từ đó về sau.

   Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  var DEFAULTS = {
    firstWords: 6,       // cụm đầu: đủ chừng này từ + có dấu phẩy/liên từ thì cắt
    firstMaxWords: 12,   // cụm đầu: đủ chừng này từ thì cắt ở khoảng trắng dù không có điểm đẹp
    maxChars: 220,       // cụm sau: đoạn dở dài quá thì cắt ở phẩy/khoảng trắng (SPEAK_MAX server)
    staleMs: 400,        // im chừng này ms không có chữ mới + loa im -> đẩy cụm hiện tại
    minStaleWords: 5     // đẩy vì im lâu chỉ khi đã có từng này từ
  };

  var SENT_END = /[.!?…]+["'”’)\]]*(?=\s|$)/g;
  // Liên từ chuyển ý: cắt TRƯỚC liên từ ("mình đã xem số liệu | và thấy rằng...").
  var CONJ = ["và", "nhưng", "rồi", "nên", "thì", "mà", "vì", "còn", "hoặc", "hay", "để", "tuy",
              "and", "but", "then", "because", "while", "although"];
  // KHÔNG có "so" hay "or" tiếng Anh: "so với", "hay" tiếng Việt đụng ngay.

  function countWords(s) {
    var m = String(s || "").trim().match(/\S+/g);
    return m ? m.length : 0;
  }

  function hasWord(s) { return /[\p{L}\p{N}]/u.test(String(s || "")); }

  // Vị trí cắt "đẹp" cuối cùng trong `s` trước `limit` ký tự: sau dấu phẩy/chấm phẩy/hai chấm,
  // hoặc trước một liên từ. Trả -1 nếu không có.
  function lastNiceCut(s, limit) {
    var seg = s.slice(0, limit);
    var best = -1;
    var m, re = /[,;:]\s/g;
    while ((m = re.exec(seg))) best = Math.max(best, m.index + 1);
    var wre = /\s(\S+)/g;
    while ((m = wre.exec(seg))) {
      var w = m[1].toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
      if (CONJ.indexOf(w) >= 0 && m.index > 0) best = Math.max(best, m.index);
    }
    return best;
  }

  function lastSpace(s, limit) {
    return s.lastIndexOf(" ", Math.min(limit, s.length) - 1);
  }

  function Chunker(opts) {
    this.opts = {};
    for (var k in DEFAULTS) this.opts[k] = DEFAULTS[k];
    for (var k2 in (opts || {})) if (opts[k2] != null) this.opts[k2] = opts[k2];
    this.reset();
  }

  Chunker.prototype.reset = function () {
    this.buf = "";
    this.first = true;        // chưa phát cụm nào trong lượt này
    this.lastAt = 0;          // mốc ms của mẩu chữ mới nhất
    this.dropRest = false;    // đã gặp <!-- : bỏ mọi thứ về sau
  };

  Chunker.prototype.pending = function () { return this.buf; };
  Chunker.prototype.hasPending = function () { return hasWord(this.buf); };

  // Mẩu chữ mới từ stream. Trả mảng cụm đọc được ngay (thường rỗng).
  Chunker.prototype.push = function (delta, now) {
    if (this.dropRest) return [];
    delta = String(delta == null ? "" : delta);
    if (!delta) return [];
    this.buf += delta;
    this.lastAt = now || Date.now();
    var i = this.buf.indexOf("<!--");
    if (i >= 0) { this.buf = this.buf.slice(0, i); this.dropRest = true; }
    return this._drain(false);
  };

  // Hết lượt: đẩy nốt phần đuôi (một cụm), rồi dọn để lượt sau tính lại "cụm đầu".
  Chunker.prototype.flush = function () {
    var out = this._drain(true);
    this.reset();
    return out;
  };

  // Đồng hồ: loa đang im mà chữ dở đã nằm im quá staleMs thì đẩy ở điểm đẹp gần nhất.
  Chunker.prototype.tick = function (now, speakerIdle) {
    if (!speakerIdle || !hasWord(this.buf)) return [];
    if ((now || Date.now()) - this.lastAt < this.opts.staleMs) return [];
    if (this._fenceOpen()) return [];
    if (countWords(this.buf) < this.opts.minStaleWords) return [];
    var cut = lastNiceCut(this.buf, this.buf.length);
    if (cut < 0) cut = lastSpace(this.buf, this.buf.length);
    if (cut <= 0) return [];
    var chunk = this.buf.slice(0, cut);
    this.buf = this.buf.slice(cut);
    this.lastAt = now || Date.now();
    if (!hasWord(chunk)) return [];
    this.first = false;
    return [chunk];
  };

  Chunker.prototype._fenceOpen = function () {
    var n = (this.buf.match(/```/g) || []).length;
    return n % 2 === 1;
  };

  Chunker.prototype._emit = function (out, n) {
    var chunk = this.buf.slice(0, n);
    this.buf = this.buf.slice(n);
    if (hasWord(chunk)) { out.push(chunk); this.first = false; }
  };

  Chunker.prototype._drain = function (final) {
    var out = [];
    for (var guard = 0; guard < 50; guard++) {
      if (!this.buf) break;
      // Khối mã ```: không bao giờ ra loa. Đứng đầu buffer thì đợi khép rồi BỎ cả khối; đứng
      // sau một đoạn chữ thì đoạn chữ đó phát trước (rào ``` là ranh giới cứng).
      var f = this.buf.indexOf("```");
      if (f >= 0 && !this.buf.slice(0, f).trim()) {
        var close = this.buf.indexOf("```", f + 3);
        if (close < 0) { if (final) this.buf = ""; break; }
        var end = close + 3;
        if (this.buf[end] === "\n") end++;
        this.buf = this.buf.slice(end);
        continue;
      }
      var limit = f >= 0 ? f : this.buf.length;
      // 1. Xuống dòng: cả dòng là một cụm.
      var nl = this.buf.indexOf("\n");
      if (nl >= 0 && nl < limit) { this._emit(out, nl + 1); continue; }
      // 1b. Dấu kết câu cuối cùng đang có.
      var lastEnd = -1, m;
      SENT_END.lastIndex = 0;
      while ((m = SENT_END.exec(this.buf)) && m.index < limit) lastEnd = m.index + m[0].length;
      if (lastEnd > 0) { this._emit(out, lastEnd); continue; }
      if (f >= 0) { this._emit(out, f); continue; }        // chữ đứng trước rào mã: phát hết
      if (final) { this._emit(out, this.buf.length); break; }
      var words = countWords(this.buf);
      // 2. Cụm đầu ngắn cho tiếng đầu ra nhanh.
      if (this.first) {
        if (words >= this.opts.firstWords) {
          var c = lastNiceCut(this.buf, this.buf.length);
          if (c > 0 && countWords(this.buf.slice(0, c)) >= 2) { this._emit(out, c); continue; }
        }
        if (words >= this.opts.firstMaxWords) {
          var sp = lastSpace(this.buf, this.buf.length);
          if (sp > 0) { this._emit(out, sp + 1); continue; }
        }
        break;
      }
      // 3. Cụm sau: chỉ cắt giữa câu khi quá dài.
      if (this.buf.length >= this.opts.maxChars) {
        var c2 = lastNiceCut(this.buf, this.opts.maxChars);
        if (c2 <= 20) c2 = lastSpace(this.buf, this.opts.maxChars) + 1;
        if (c2 > 20) { this._emit(out, c2); continue; }
      }
      break;
    }
    return out;
  };

  var api = { Chunker: Chunker, DEFAULTS: DEFAULTS, countWords: countWords, lastNiceCut: lastNiceCut };
  if (typeof window !== "undefined") window.JavisVoiceChunker = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
