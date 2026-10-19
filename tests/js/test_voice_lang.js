/* "Auto by language" Edge voice (dashboard/voice-lang.js, 0.220.0) - pure, runs under node.

       node tests/js/test_voice_lang.js

   The voice follows the language of the text being read. Short chunks never switch it, and a new
   language has to hold for two chunks unless the chunk is long, so "OK." in the middle of a
   Vietnamese answer does not flip the speaker to English for one word. */
const L = require("../../dashboard/voice-lang.js");
const fs = require("fs");
const path = require("path");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

check("detect: Vietnamese diacritics", L.detect("Doanh thu hôm nay tăng mười phần trăm.") === "vi");
check("detect: plain English", L.detect("Revenue went up ten percent today.") === "en");
check("detect: Japanese (kana)", L.detect("今日は晴れです。") === "ja");
check("detect: Chinese (Han, no kana)", L.detect("今天天气很好。") === "zh");
check("detect: Korean", L.detect("안녕하세요") === "ko");
check("detect: digits only -> no language", L.detect("12.345") === "");
check("words: CJK counts two characters per word", L.words("今日は晴れです") === 4);

// The plan's sequence: vi, vi, "ok", a long English sentence.
const t = new L.Tracker("vi");
const vi = L.VOICES.vi, en = L.VOICES.en;
check("turn 1 Vietnamese -> Hoai My", t.pick("Dạ, để em xem doanh thu hôm nay.") === vi);
check("turn 2 Vietnamese -> Hoai My", t.pick("Hôm nay có mười hai đơn hàng mới.") === vi);
check("turn 3 'OK.' (under 3 words) keeps Hoai My", t.pick("OK.") === vi);
check("turn 4 long English sentence switches at once", t.pick("Sure, here is the summary of today's sales in English.") === en);
const t3 = new L.Tracker("vi");
t3.pick("Here is the news.");
check("asking the same chunk twice in a row (preload, play) counts once", t3.pick("Here is the news.") === vi);
check("detect: 'Chào anh, em là Javis.' is Vietnamese (shared marks only)", L.detect("Chào anh, em là Javis.") === "vi");
check("detect: French with ç is not Vietnamese", L.detect("Ça va très bien, merci.") === "en");

const t2 = new L.Tracker("vi");
t2.pick("Chào anh, em là Javis.");
check("a short English chunk (3-5 words) does not switch alone", t2.pick("Check the dashboard now.") === vi);
check("the second English chunk in a row switches", t2.pick("Then open the report.") === en);
check("Japanese long reply switches to a Japanese voice", new L.Tracker("vi").pick("今日の売上は十二万円でした。明日も頑張りましょう。") === L.VOICES.ja);
check("unknown start language falls back to Vietnamese", new L.Tracker("xx").lang === "vi");

// Wiring: the option exists, the module loads before voice.js, voice.js resolves "auto" per chunk.
const root = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(root, "dashboard/index.html"), "utf8");
const voiceJs = fs.readFileSync(path.join(root, "dashboard/voice.js"), "utf8");
check("index.html offers the auto voice", html.includes('<option value="auto" data-i18n="qs.voice_opt_auto">'));
check("voice-lang.js loads before voice.js", html.indexOf("/static/voice-lang.js") > 0 && html.indexOf("/static/voice-lang.js") < html.indexOf("/static/voice.js"));
check("voice.js resolves the voice per chunk", /voice=\$\{encodeURIComponent\(this\._voiceFor\(text\)\)\}/.test(voiceJs));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - voice-lang");
