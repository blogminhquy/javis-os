// webhook_ui_narrow_check.mjs - the webhook page at phone width (390 px), in a real browser (0.274.0, spec §12/§15 UI).
//
//   node tools/webhook_ui_narrow_check.mjs http://127.0.0.1:7791 /tmp/shots
//
// Start a LOCAL Javis first with a temporary state folder and outgoing calls refused, then create one hook and send it a
// few events (docs/webhook-platform/staging-pilot-pack.md, "UI check"). The script opens the Webhooks page, takes the
// four parts (Configuration, Events with one event opened, Health, the test-send preview) as PNG files, and fails when
// the page scrolls sideways or throws. It never presses Send, Stop receiving, Delete or View raw.
import { createRequire } from "module";
const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); } catch (e) { pw = require("/opt/node-tools/node_modules/playwright"); }

const base = process.argv[2] || "http://127.0.0.1:7791";
const out = process.argv[3] || ".";
const exe = process.env.CHROMIUM_PATH || undefined;
const b = await pw.chromium.launch(exe ? { executablePath: exe } : {});
const p = await b.newPage({ viewport: { width: 390, height: 900 } });
const errs = [];
p.on("pageerror", (e) => errs.push(e.message));
await p.goto(base + "/", { waitUntil: "networkidle" });
await p.waitForFunction(() => window.JavisNav && window.JavisNav.go, null, { timeout: 20000 });
await p.evaluate(() => { const w = document.getElementById("setupWizard"); if (w) w.remove(); window.JavisNav.go("webhooks"); });
await p.waitForSelector(".wf-card", { timeout: 15000 });
const card = p.locator(".wf-card").first();
await card.screenshot({ path: out + "/1-config.png" });
await card.locator('.whTab[data-tab="ev"]').click();
await card.locator(".whLog summary").click();
if (await card.locator(".whEvInfo").count()) { await card.locator(".whEvInfo").first().click(); await p.waitForTimeout(800); }
await card.screenshot({ path: out + "/2-events.png" });
await card.locator('.whTab[data-tab="health"]').click();
await p.waitForTimeout(800);
await card.screenshot({ path: out + "/3-health.png" });
await card.locator('.whTab[data-tab="cfg"]').click();
await card.locator(".whTest").click();
await card.locator(".whTestPreview").click();
await p.waitForTimeout(800);
await card.screenshot({ path: out + "/4-test-preview.png" });
const wide = await p.evaluate(() => document.documentElement.scrollWidth);
const small = await p.evaluate(() => [...document.querySelectorAll("#whSection *")].filter((el) => el.offsetParent
  && el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
  && parseFloat(getComputedStyle(el).fontSize) < 16).map((el) => el.className || el.tagName).slice(0, 5));
await b.close();
console.log(`scrollWidth ${wide} (viewport 390), page errors ${errs.length}, text under 16px ${small.length}`);
if (errs.length) console.log("errors:", errs.join(" | "));
if (small.length) console.log("under 16px:", small.join(", "));
process.exit(wide > 390 || errs.length || small.length ? 1 : 0);
