/* voice-lang.js - "Auto by language" Edge voice for the basic call path (0.220.0). Pure module.

   The voice follows the language of the TEXT being read, detected from its script: Vietnamese
   diacritics, kana, Han, Hangul, Thai, Cyrillic, else Latin. Why not Whisper's language: the
   recognition language is pinned to the UI language (vi-VN or en-US) so Whisper never mistranslates
   a short Vietnamese sentence, which means Whisper's "language" field always echoes the hint. And
   it is the reply text, not the question, that the speaker has to pronounce.

   Anti-flap: a chunk under 3 words never switches the voice ("OK.", "Dạ."), and a new language
   must hold for 2 chunks in a row unless the chunk is long (6 words or more). */
(function () {
  "use strict";

  // Language -> Edge voice. Latin text that is not Vietnamese goes to Emma, which is multilingual
  // and reads French, Spanish or German correctly too.
  var VOICES = {
    vi: "vi-VN-HoaiMyNeural",
    en: "en-US-EmmaMultilingualNeural",
    ja: "ja-JP-NanamiNeural",
    zh: "zh-CN-XiaoxiaoNeural",
    ko: "ko-KR-SunHiNeural",
    th: "th-TH-PremwadeeNeural",
    ru: "ru-RU-SvetlanaNeural",
  };
  var MIN_WORDS = 3, STRONG_WORDS = 6;

  // Letters that only Vietnamese uses among Latin scripts (đ, ư, ơ and the stacked tone marks).
  var VI_ONLY = /[đĐưƯơƠăĂ]|[ạảấầẩẫậắằẳẵặẹẻẽếềểễệỉĩịọỏốồổỗộớờởỡợụủũứừửữựỳỵỷỹ]/i;
  // Marks Vietnamese shares with French or Spanish ("Chào anh, em là Javis." has only à). Dense
  // enough, and with no letter those languages have and Vietnamese lacks, they still mean Vietnamese.
  var VI_SHARED = /[àáâãèéêìíòóôõùúý]/gi;
  var NOT_VI = /[çœëïÿñßüöä¿¡]/i;

  function count(re, text) { var m = text.match(re); return m ? m.length : 0; }

  // Spoken-word estimate: Latin words plus CJK/Thai characters at two per word.
  function words(text) {
    text = String(text || "");
    var dense = count(/[぀-ヿ㐀-鿿가-힯฀-๿]/g, text);
    var latin = count(/[A-Za-zÀ-ɏḀ-ỿЀ-ӿ]+/g, text);
    return latin + Math.ceil(dense / 2);
  }

  function detect(text) {
    text = String(text || "");
    if (count(/[぀-ヿ]/g, text)) return "ja";            // kana only exists in Japanese
    if (count(/[가-힯]/g, text)) return "ko";
    if (count(/[฀-๿]/g, text)) return "th";
    if (count(/[㐀-鿿]/g, text)) return "zh";
    if (count(/[Ѐ-ӿ]/g, text) > count(/[A-Za-z]/g, text)) return "ru";
    if (VI_ONLY.test(text)) return "vi";
    var letters = count(/[A-Za-z\u00c0-\u024f\u1e00-\u1eff]/g, text);
    if (letters && !NOT_VI.test(text) && count(VI_SHARED, text) / letters >= 0.06) return "vi";
    if (letters) return "en";
    return "";
  }

  // Language of a WHOLE message, for read aloud (2026-11-08, owner): an answer written in English
  // is read in English, one written in Vietnamese keeps the Vietnamese way of saying English words.
  // Same rule as phien_am.is_english_text on the server. Words left out of the list stand alone in
  // Vietnamese too: "to", "in", "do", "so", "no", "an", "a", "me", "he".
  var ENGLISH_MARKERS = {};
  ("the is are was were been will would can could should does did have has had not " +
   "of for with from and but if than then that this these those there here " +
   "you your yours we our they their them it's its i'm i've i'll don't doesn't can't " +
   "what when where why how who which please just also very about into over")
    .split(" ").forEach(function (w) { ENGLISH_MARKERS[w] = 1; });

  function messageLang(text) {
    text = String(text || "");
    var tokens = text.match(/[A-Za-z\u00c0-\u024f\u1e00-\u1eff]+(?:['\u2019][A-Za-z]+)*/g) || [];
    var vietnamese = 0, markers = 0;
    tokens.forEach(function (w) {
      if (/[^\x00-\x7f]/.test(w)) vietnamese++;
      if (ENGLISH_MARKERS[w.toLowerCase().replace("\u2019", "'")]) markers++;
    });
    if (markers >= 2 && markers >= vietnamese) return "en";
    if (vietnamese && detect(text) === "vi") return "vi";
    return "";
  }

  // What read aloud sends to /tts as `en`: "1" English message, "0" Vietnamese, "" can't tell.
  function englishFlag(text) {
    var l = messageLang(text);
    return l === "en" ? "1" : l === "vi" ? "0" : "";
  }

  function voiceFor(lang, fallback) { return VOICES[lang] || fallback || VOICES.en; }

  // One tracker per JavisVoice. `start` is the language to read in before anything is detected.
  function Tracker(start) {
    this.lang = VOICES[start] ? start : "vi";
    this.candidate = "";
    // The same chunk is asked twice in a row (preload, then play): answer it once, not twice.
    this._lastKey = null;
    this._lastVoice = "";
  }

  Tracker.prototype.reset = function (start) {
    this.lang = VOICES[start] ? start : this.lang;
    this.candidate = "";
    this._lastKey = null;
  };

  Tracker.prototype.pick = function (text) {
    var key = String(text || "");
    if (key === this._lastKey) return this._lastVoice;
    var lang = detect(key), n = words(key);
    if (!lang || lang === this.lang || n < MIN_WORDS) {
      if (lang === this.lang) this.candidate = "";
    } else if (n >= STRONG_WORDS || this.candidate === lang) {
      this.lang = lang;
      this.candidate = "";
    } else {
      this.candidate = lang;
    }
    this._lastKey = key;
    this._lastVoice = voiceFor(this.lang);
    return this._lastVoice;
  };

  var api = { VOICES: VOICES, detect: detect, messageLang: messageLang, englishFlag: englishFlag, words: words, voiceFor: voiceFor, Tracker: Tracker };
  if (typeof window !== "undefined") window.JavisVoiceLang = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
