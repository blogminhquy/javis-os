/* Nothing runs on every frame while the app sits still, and a page visit leaves nothing behind (2026-11-12).

       node tests/js/test_idle_and_page_leaks.js

   Owner: "rà soát toàn bộ tốc độ load các màn ... để không gặp tình trạng giựt lag đơ". Measured in a real browser on a
   brain of 2,600 notes, phone-speed CPU:
   - every visit to the Chat page leaked its whole DOM (1,461 nodes and 167 listeners after a forced garbage
     collection): the drawer helper added a listener on a MediaQueryList on each render, and the browser keeps such a
     list for as long as the document lives. After a hundred page changes about 200,000 dead nodes were still held;
   - two loops asked for a frame on every frame for good (the voice level pump and the starfield), only to return at
     once, and each of those frames made the browser tick every CSS animation on the page;
   - opening the app on Chat or Partners still downloaded the brain graph and ran its physics for a screen out of view.
   Reading the source is the right tool here: the three loops are closures inside app.js and console.js with no seam to
   run them alone; the real-browser numbers are in the pull request. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const con = D("console.js"), app = D("app.js"), studio = D("studio.js");

// ───────── the drawer helper no longer leaks the page ─────────
const neo = (con.match(/function _neoCotTrai\(page, sideEl, slot\)[\s\S]*?\n  \}/) || [""])[0];
check("found _neoCotTrai", neo.length > 200);
check("it adds no listener of its own on a MediaQueryList (the browser keeps those, and the page with them)",
  !/matchMedia\([^)]*\)\.addEventListener/.test(neo) && !/\.addListener\(/.test(neo));
check("it asks for the one shared listener instead", /_watchNarrowOnce\(\);/.test(neo));
const watch = (con.match(/function _watchNarrowOnce\(\)[\s\S]*?\n  \}/) || [""])[0];
check("the shared listener is added once", /if \(_narrowWatchOn\) return;\n\s*_narrowWatchOn = true;/.test(watch));
check("and it holds no page: it looks the open drawers up when the width changes",
  /document\.querySelectorAll\('\[data-cot-trai-da-neo="1"\]\.side-open'\)\.forEach\(\(p\) => p\.classList\.remove\("side-open"\)\)/.test(watch)
  && !/\bpage\b/.test(watch));
check("every page that uses the helper is marked for that lookup", /page\.dataset\.cotTraiDaNeo = "1";/.test(neo));
check("the wide-screen clean-up still happens only when the screen stops being narrow", /if \(e\.matches\) return;/.test(watch));

// The agent form's two document listeners leave together.
const drop = (studio.match(/function dropPopListeners\(\) \{[\s\S]*?\n    \}/) || [""])[0];
check("the agent form drops its click and keydown listeners together",
  /removeEventListener\("click", ngoaiKhung\)/.test(drop) && /removeEventListener\("keydown", escKhung\)/.test(drop)
  && (studio.match(/if \(!mPop \|\| !mPop\.isConnected\) \{ dropPopListeners\(\); return; \}/g) || []).length === 2);

// ───────── no frame is asked for while nothing moves ─────────
const pump = (app.match(/function pumpAudioLevel\(\) \{[\s\S]*?\n\}/) || [""])[0];
check("found pumpAudioLevel", pump.length > 200);
check("the voice pump asks for a frame only while a level or a caption is live, a timer otherwise",
  /if \(live\) requestAnimationFrame\(pumpAudioLevel\);\n\s*else setTimeout\(pumpAudioLevel, PUMP_IDLE_MS\);/.test(pump)
  && (pump.match(/requestAnimationFrame\(/g) || []).length === 1);
check("a voice level or a caption following a voice makes it live",
  /if \(_lvl > 0\) live = true;/.test(pump) && /if \(_theoLoi\) live = true;/.test(pump));
check("the stop button keeps its six updates a second in both rhythms",
  /const PUMP_IDLE_MS = 160;/.test(app) && /if \(!live \|\| \(_stopBtnTick % 10\) === 0\) \{\n\s*updateStopBtn\(\);/.test(pump));
const star = app.slice(app.indexOf("function initStarfield()"), app.indexOf("// Bộ nhớ dài hạn / Tự học"));
check("the starfield asks for a frame directly only with a voice or thinking",
  /if \(active\) requestAnimationFrame\(draw\);\n\s*else setTimeout\(wake, /.test(star)
  && (star.match(/requestAnimationFrame\(draw\)/g) || []).length === 2    // the direct one and the one inside wake()
  && /const wake = \(\) => \{ if \(isParked\(\)\) setTimeout\(wake, STAR_PARKED_MS\); else requestAnimationFrame\(draw\); \};/.test(star));

// ───────── the brain graph waits for the home screen ─────────
const boot = app.slice(app.lastIndexOf("// Boot\n"));
check("starting the app no longer builds the graph by itself", !/\binitGraph\(\)/.test(boot) && !/\bensureGraph\(\);/.test(boot));
check("the graph is built once, on demand",
  /function ensureGraph\(\) \{\n\s*if \(!_graphBuilding\) _graphBuilding = initGraph\(\)\.then\(connectGraphWatch\)\.catch\(connectGraphWatch\);/.test(app));
check("the home screen asks for it: on the first page and on every later visit",
  /veManChinh\(\) \{ ensureGraph\(\); if \(_cockpitCho\) capNhatManChinh\(\); \}/.test(app)
  && /firstPage\(id\) \{ if \(id === "home"\) ensureGraph\(\); \}/.test(app));
check("console.js reports the page the app opened on, right after choosing it",
  /khoiPhucTrang\(\);\n[\s\S]{0,900}window\.JavisCockpit\.firstPage\(Alpine\.store\("nav"\)\.active\)/.test(con));
check("a safety net builds it anyway when console.js never reported and the home screen is in view",
  /setTimeout\(ensureGraphIfHome, 4000\);/.test(boot)
  && /function ensureGraphIfHome\(\) \{ if \(!_graphBuilding && _oManChinh\(\)\) ensureGraph\(\); \}/.test(app));
check("console.js still calls veManChinh whenever the home screen comes into view",
  /if \(active === "home"\) \{ try \{ if \(window\.JavisCockpit\) window\.JavisCockpit\.veManChinh\(\); \} catch \(e\) \{\} \}/.test(con));

if (fails.length) { console.log("\nFAIL - test_idle_and_page_leaks: " + fails.length); process.exit(1); }
console.log("\nOK - test_idle_and_page_leaks: all pass");
