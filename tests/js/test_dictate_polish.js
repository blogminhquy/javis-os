/* Every dictation ends with a rewrite by the main brain, in context (2026-11-06).

       node tests/js/test_dictate_polish.js

   Owner, 2026-11-06: "nói xong ấn Enter hoặc ấn tắt thì nó tự dùng mô hình viết lại thành câu đúng ngữ cảnh, không
   phải câu nghe được", "đừng chỉ sửa vài từ, hãy sửa cả cấu trúc", "dùng ngay chính mô hình chính". Drives dictate.js
   create() with a fake recognizer, recorder and server. Pins: when the recording ends the words go to POST /stt/fix with
   `final` and the chat's recent messages; the run stays "transcribing" until the rewrite is back and onText gets the
   REWRITTEN sentence before idle; the ear's text (Groq/OpenAI) is what gets rewritten when there is one; a failing or
   slow server keeps the words as heard; X while rewriting drops everything; recentMessages reads the last messages. */
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 12; i++) await tick(); };

const PC = { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36" };

let runs = [], ear = "", calls = [], fixMode = "ok", sttText = "Javis OS đã nghe được rồi.";
class SR {
  constructor() { runs.push(this); }
  start() {}
  stop() { setTimeout(() => this.onend && this.onend(), 0); }
  abort() {}
  say(text) { this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: true })] }); }
}
class Rec {
  constructor() { this.state = "inactive"; this.mimeType = "audio/webm"; }
  start() { this.state = "recording"; this.ondataavailable({ data: new Blob([new Uint8Array(4000)]) }); }
  stop() { this.state = "inactive"; setTimeout(() => this.onstop && this.onstop(), 0); }
}
Object.defineProperty(globalThis, "navigator", {
  value: Object.assign({}, PC, { mediaDevices: { getUserMedia: () => Promise.resolve({ getTracks: () => [{ stop() {} }] }) } }),
  configurable: true, writable: true,
});
global.window = { SpeechRecognition: SR };
global.MediaRecorder = Rec;
const json = v => Promise.resolve({ json: () => Promise.resolve(v) });
global.fetch = (url, init) => {
  url = String(url);
  if (url.indexOf("/voice/ear") !== -1) return json({ kind: ear });
  if (url.indexOf("/stt/fix") !== -1) {
    const body = JSON.parse(init.body);
    calls.push(body);
    if (fixMode === "fail") return Promise.reject(new Error("down"));
    if (fixMode === "hang") return new Promise(() => {});
    return json({ ok: true, text: "Bạn kiểm tra giúp anh Javis OS đã nghe đúng chưa." });
  }
  if (url.indexOf("/stt") !== -1) { calls.push({ stt: true }); return json({ ok: true, text: sttText }); }
  return json({});
};
function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}
const ctx = () => ["Anh vừa thêm Groq", "Dạ, em đã thấy khoá Groq."];

(async () => {
  // 1. Browser words only (no ear): stop, the rewrite comes back, then idle.
  ear = ""; runs = []; calls = []; fixMode = "ok";
  let D = fresh(), states = [], texts = [];
  await D.warm();
  let d = D.create({ context: ctx, onText: (t, f) => texts.push([t, !!f]), onState: s => states.push(s) });
  d.start(); await settle();
  runs[0].say("bạn kiểm tra giúp anh travis os đã nghe đúng chưa");
  check("while speaking the words as heard reach onText (not final)",
    texts.length === 1 && texts[0][0] === "bạn kiểm tra giúp anh travis os đã nghe đúng chưa" && !texts[0][1]);
  d.stop(); await settle();
  check("/stt/fix is asked once, with final and the chat context",
    calls.length === 1 && calls[0].final === true && calls[0].text === "bạn kiểm tra giúp anh travis os đã nghe đúng chưa"
    && calls[0].context.length === 2 && calls[0].context[0] === "Anh vừa thêm Groq");
  check("the run waits in transcribing while the sentence is rewritten", states.indexOf("transcribing") !== -1);
  const last = texts[texts.length - 1];
  check("onText gets the rewritten sentence, marked final", last[0] === "Bạn kiểm tra giúp anh Javis OS đã nghe đúng chưa." && last[1]);
  check("then idle, after the rewrite", states[states.length - 1] === "idle"
    && states.lastIndexOf("transcribing") < states.lastIndexOf("idle"));

  // 2. With an ear: the ear's text is what gets rewritten.
  ear = "upload"; runs = []; calls = []; fixMode = "ok";
  D = fresh(); states = []; texts = [];
  await D.warm();
  d = D.create({ context: ctx, onText: (t, f) => texts.push([t, !!f]), onState: s => states.push(s) });
  d.start(); await settle();
  runs[0].say("tra vít ô ét");
  d.stop(); await settle();
  const fix = calls.filter(c => c.final);
  check("ear: /stt runs first, then the rewrite", calls[0] && calls[0].stt && fix.length === 1);
  check("ear: the rewrite gets the ear's text, not the browser draft", fix[0] && fix[0].text === sttText);
  check("ear: the rewritten sentence is the final text", texts[texts.length - 1][0] === "Bạn kiểm tra giúp anh Javis OS đã nghe đúng chưa.");

  // 3. Server down: the words as heard, never lost.
  ear = ""; runs = []; calls = []; fixMode = "fail";
  D = fresh(); states = []; texts = [];
  await D.warm();
  d = D.create({ onText: (t, f) => texts.push([t, !!f]), onState: s => states.push(s) });
  d.start(); await settle();
  runs[0].say("giữ nguyên câu này");
  d.stop(); await settle();
  check("rewrite fails: the words as heard land as final", texts[texts.length - 1][0] === "giữ nguyên câu này" && texts[texts.length - 1][1]);
  check("rewrite fails: still ends idle", states[states.length - 1] === "idle");

  // 4. X while the rewrite is out: nothing lands, one idle.
  ear = ""; runs = []; calls = []; fixMode = "hang";
  D = fresh(); states = []; texts = [];
  await D.warm();
  d = D.create({ onText: (t, f) => texts.push([t, !!f]), onState: s => states.push(s) });
  d.start(); await settle();
  runs[0].say("bỏ câu này đi");
  d.stop(); await settle();
  check("rewrite pending: busy", d.busy() && states[states.length - 1] === "transcribing");
  const before = texts.length;
  d.cancel(); await settle();
  check("X during the rewrite: idle at once, no final text", states[states.length - 1] === "idle" && texts.length === before);

  // 5. polish: false skips the server (kept for a caller that wants raw words).
  ear = ""; runs = []; calls = []; fixMode = "ok";
  D = fresh(); texts = [];
  await D.warm();
  d = D.create({ polish: false, onText: (t, f) => texts.push([t, !!f]), onState: () => {} });
  d.start(); await settle();
  runs[0].say("không cần viết lại");
  d.stop(); await settle();
  check("polish: false keeps the words and asks no rewrite", calls.length === 0 && texts[texts.length - 1][0] === "không cần viết lại");

  // 6. polishText gives up after its wait and keeps the words.
  fixMode = "hang";
  D = fresh();
  const t0 = Date.now();
  const out = await D.polishText("câu chậm", [], 60);
  check("polishText: a slow server keeps the words after the wait", out === "câu chậm" && Date.now() - t0 < 1000);

  // 7. recentMessages: the last n, trimmed, oldest first.
  const nodes = ["một", "  hai  ba ", "", "bốn", "x".repeat(400)].map(t => ({ textContent: t }));
  const got = D.recentMessages({ querySelectorAll: () => nodes }, ".m", 3);
  check("recentMessages: last 3 non-empty, spaces folded, long ones cut",
    got.length === 2 && got[0] === "bốn" && got[1].length === 303);
  check("recentMessages: no root gives []", D.recentMessages(null, ".m").length === 0);

  if (fails.length) { console.log("\nFAIL - test_dictate_polish: " + fails.length); process.exit(1); }
  console.log("\nOK - test_dictate_polish: all pass");
  process.exit(0);
})();
