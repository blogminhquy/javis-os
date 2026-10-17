// Narrow-screen, bilingual check of the Team cards added in 0.207.0 to 0.209.0 (approval, work mode, mandate,
// opportunity, acceptance). Renders the real teams.js output with the real style.css and console.css at 390 px wide,
// once in Vietnamese and once in English, and checks: no horizontal scroll, card text at least 16 px, every button
// inside the screen. Uses Playwright with the Chromium already on the machine; no server, no model.
//
//     node pilot/team-multiday/ui_narrow_check.mjs [screenshot-dir]
//
// Not part of CI (CI has no browser). Run it before the pilot and keep the screenshots with the report.
// The app font (Be Vietnam Pro, Google Fonts) is not loaded here, so widths are measured on the system fallback font;
// a final look on a real phone is still part of run_guide.txt.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");
const shots = process.argv[2] || "";
let pw;
for (const p of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
  try { pw = require(p); break; } catch (e) { /* next */ }
}
if (!pw) { console.log("FAIL playwright not found"); process.exit(1); }

const TM = require(path.join(ROOT, "dashboard", "teams.js"));
const dict = {
  vi: JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8")),
  en: JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8")),
};

function cardsHtml(lang) {
  globalThis.window = { t: (k, v) => String(dict[lang][k] || k).replace(/\{(\w+)\}/g, (m, n) => (v && v[n] != null ? v[n] : m)) };
  const ap = { approval_id: "ap_1", team_rev: 1, kind: "action", status: "pending",
    title: lang === "vi" ? "Gửi tin khuyến mãi cho nhóm khách hàng thân thiết tháng mười" : "Send the October offer to loyal customers",
    action: "zalo_send_message", scope: lang === "vi" ? "Nhóm khách cũ" : "Past customers", impact: "200",
    evidence: ["pilot/ban-hang/kich-ban/thang-10-rat-dai-ten-file-de-kiem-tra-xuong-dong.md"],
    actions: [{ label: "Zalo: send_message", call: 'zalo_send_message {"message":"Chào anh chị, shop có ưu đãi tháng mười cho khách thân thiết","threadId":"1234567890123456789"}', used: false }] };
  const m = { version: 2, status: "active", outcome: lang === "vi" ? "Mỗi yêu cầu nội dung có bài viết đạt chuẩn" : "Every request gets a passing article",
    metrics: ["≥ 600"], sources: ["folder:pilot/noi-dung/yeu-cau", "mcp:pos"], autonomy: { approve: ["file_changed"] }, budget: {}, stop: {},
    sources_state: [{ source: "folder:pilot/noi-dung/yeu-cau", state: "ok" }, { source: "mcp:pos", state: "missing", missing: "chưa có kết nối 'pos'" }] };
  const opp = { opp_id: "op_1", status: "proposed", reason: "tài liệu trong thư mục được giao thay đổi: 3 tệp", benefit: "kịp",
    evidence: ["pilot/noi-dung/yeu-cau/bai-ra-mat.md"], source: "folder", ref: "pilot/noi-dung/yeu-cau", version_key: "9f2c1a7b3e4d5f60" };
  const acc = { task_id: "t_1", status: "review", stale: [], criteria: [{ kind: "file_contains", path: "pilot/noi-dung/bai-viet/ra-mat.md" }],
    last: [{ idx: 0, kind: "file_contains", verdict: "fail", evidence: { path: "pilot/noi-dung/bai-viet/ra-mat.md", sha256: "abcdef0123456789", detail: "thiếu: giá" } }] };
  return [
    TM.approvalCardHtml({ id: 1, meta: { approval: ap } }),
    TM.workModeHtml({ work_mode: "gated" }),
    TM.mandateHtml({ mandate: m }),
    TM.opportunityCardHtml({ id: 2, meta: { opportunity: opp } }),
    TM.acceptanceCardHtml({ id: 3, meta: { acceptance: acc } }),
    // The two forms whose CSS changed (review 0.210.0): mandate editor and acceptance criteria editor.
    TM.mandateHtml({ mandate: m }, true),
    TM.queueHtml({ waiting: [{ id: "t_9", title: lang === "vi" ? "Viết bài ra mắt" : "Write the launch post" }] }, { accEdit: "t_9" }),
  ].join("");
}

const css = ["style.css", "console.css"].map((f) => "file://" + path.join(ROOT, "dashboard", f));
let fails = 0;
const browser = await pw.chromium.launch({ executablePath: fs.existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined });
for (const lang of ["vi", "en"]) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const html = `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">` +
    css.map((h) => `<link rel="stylesheet" href="${h}">`).join("") +
    // The real side panel lives inside the app grid; outside it, let the page grow so the screenshot shows every card.
    "<style>html,body{height:auto!important;overflow:visible!important}.tm-side{display:block;height:auto}</style>" +
    `</head><body><div class="tm-side" style="padding:0 16px;overflow:visible">${cardsHtml(lang)}</div></body></html>`;
  const file = path.join(fs.mkdtempSync(path.join(process.env.TMPDIR || "/tmp", "tm-ui-")), `cards-${lang}.html`);
  fs.writeFileSync(file, html);
  await page.goto("file://" + file);
  const r = await page.evaluate(() => {
    const doc = document.documentElement;
    const small = [...document.querySelectorAll(".tm-ap, .tm-md, .tm-wm .tm-radio, .tm-ap button, .tm-md button, .tm-md .tm-sub, .tm-ap .tm-sub, .tm-md li, .tm-ap li, .tm-ap code, .tm-md code, .tm-md-form textarea, .tm-md-form input, .tm-md-form select, .tm-acc-form textarea, .tm-acc-form input, .tm-acc-form button")]
      .map((e) => [e.className, parseFloat(getComputedStyle(e).fontSize)]).filter(([, fs]) => fs < 16);
    const out = [...document.querySelectorAll("button")].filter((b) => { const x = b.getBoundingClientRect(); return x.right > innerWidth + 0.5 || x.left < -0.5; })
      .map((b) => b.textContent);
    return { scroll: doc.scrollWidth, width: innerWidth, small, out, cards: document.querySelectorAll(".tm-ap, .tm-md, .tm-wm").length,
      forms: document.querySelectorAll(".tm-md-form, .tm-acc-form").length };
  });
  const ok = r.scroll <= r.width && r.small.length === 0 && r.out.length === 0 && r.cards >= 5 && r.forms === 2;
  console.log((ok ? "ok   " : "FAIL ") + `${lang} 390px: ${r.cards} cards, ${r.forms} forms, scrollWidth ${r.scroll}, small text ${JSON.stringify(r.small)}, buttons off screen ${JSON.stringify(r.out)}`);
  if (!ok) fails++;
  if (shots) {
    fs.mkdirSync(shots, { recursive: true });
    await page.screenshot({ path: path.join(shots, `team-cards-${lang}-390.png`), fullPage: true });
  }
  await page.close();
}
await browser.close();
console.log(fails ? `\nFAILED ${fails}` : "\nALL OK");
process.exit(fails ? 1 : 0);
