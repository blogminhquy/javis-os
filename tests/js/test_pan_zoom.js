/* Zoom and pan for diagrams and pictures (0.405.0; owner 2026-10-29: "a wide diagram on the phone cannot be zoomed",
   desktop and phone alike).

       node tests/js/test_pan_zoom.js

   The math in dashboard/pan-zoom.js runs for real under node; the wiring into the artifact viewer (chat-render.js), the
   editor picture (console.js), the CSS and index.html are guarded by their structure.
*/
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const PZ = require(path.join(ROOT, "dashboard", "pan-zoom.js"));
const PZS = src("dashboard/pan-zoom.js");
const CR = src("dashboard/chat-render.js");
const CON = src("dashboard/console.js");
const CSS = src("dashboard/style.css");
const HTML = src("dashboard/index.html");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };
const near = (a, b) => Math.abs(a - b) < 1e-6;

// ---- 1. math ----
const wide = { w: 2000, h: 300, vw: 400, vh: 700 };   // the owner's case: a wide diagram on a phone
const f = PZ.fitState(wide);
check("fit: a wide diagram scales down to the box width and sits in the middle", near(f.scale, 0.2) && near(f.x, 0) && near(f.y, (700 - 60) / 2),
  JSON.stringify(f));
const small = PZ.fitState({ w: 100, h: 50, vw: 400, vh: 400 });
check("fit: a small picture is not blown up past its natural size, and is centred", small.scale === 1 && small.x === 150 && small.y === 175);
const z = PZ.zoomAt(f, 2, 200, 350, wide);
check("zoom keeps the point under the pointer still", near(z.scale, 0.4) && near((200 - z.x) / z.scale, (200 - f.x) / f.scale) &&
  near((350 - z.y) / z.scale, (350 - f.y) / f.scale), JSON.stringify(z));
check("zoom stops at 8x the natural size and at half of fit", near(PZ.zoomAt(f, 1000, 0, 0, wide).scale, 8) &&
  near(PZ.zoomAt(f, 0.001, 0, 0, wide).scale, 0.1));
const p = PZ.pinchStep(f, { x: 200, y: 350, distance: 100 }, { x: 220, y: 350, distance: 300 }, wide);
check("pinch: fingers three times apart zoom 3x and the picture follows their midpoint", near(p.scale, 0.6) &&
  near((220 - p.x) / p.scale, (200 - f.x) / f.scale), JSON.stringify(p));
check("pinch with no distance does nothing", PZ.pinchStep(f, { x: 0, y: 0, distance: 0 }, { x: 5, y: 5, distance: 10 }, wide) === f);
const away = PZ.clampState({ scale: 1, x: -5000, y: 9000 }, wide);
check("pan cannot drag the picture fully out of the box", away.x > -2000 && away.y < 700 && away.x === 100 - 2000 && away.y === 700 - 75,
  JSON.stringify(away));

// ---- 2. the component ----
check("mouse wheel zooms around the pointer, trackpad pinch (ctrl+wheel) too, page does not scroll",
  /addEventListener\("wheel", onWheel, \{ passive: false \}\)/.test(PZS) && /e\.preventDefault\(\)/.test(PZS) && /e\.ctrlKey \? 0\.01 : 0\.002/.test(PZS));
check("pointer events: one pointer pans, two pinch, touch-action none so the phone hands the gestures over",
  /pointerdown/.test(PZS) && /pinchStep\(state, lastPinch, now, size\(\)\)/.test(PZS) && /touch-action: none/.test(CSS));
check("double click and double tap zoom in 2x or back to fit", /addEventListener\("dblclick", onDbl\)/.test(PZS) && /t - lastTap < 320/.test(PZS) &&
  /zoomBy\(2, px, py\)/.test(PZS));
check("bar: zoom out, percent, zoom in, fit; labels in both languages", /data-pz="out"/.test(PZS) && /data-pz="in"/.test(PZS) && /data-pz="fit"/.test(PZS) &&
  ["pz.in", "pz.out", "pz.fit"].every((k) => VI[k] && EN[k]) && /\.jv-pz-bar button \{ width: 36px; height: 36px;/.test(CSS));
check("refits when the box changes size until the user zooms", /new ResizeObserver/.test(PZS) && /ro\.disconnect\(\)/.test(PZS));

// ---- 3. wiring ----
check("diagram viewer: a drawn mermaid diagram gets zoom and pan", /renderMermaid\(art\.code, elBody\.querySelector\("\.jv-ap-mermaid"\), function \(host\)/.test(CR) &&
  /zoomOn\(host, svg, window\.JavisPanZoom\.svgSize\(svg\)\)/.test(CR) && /if \(done\) done\(host\)/.test(CR));
check("SVG picture: an <img> (no scripts run), not an iframe, so it zooms", /new Blob\(\[art\.code\], \{ type: "image\/svg\+xml" \}\)/.test(CR) &&
  /zoomOn\(box, img, nat\)/.test(CR) && !/frame\("",/.test(CR));
check("one zoom at a time: switching tab or closing the viewer drops it", /function renderTab\(\) \{\s*var art = curArt; if \(!art \|\| !elBody\) return;\s*dropZoom\(\);/.test(CR) &&
  /function closePanel\(\) \{\s*if \(!panel\) return;[\s\S]{0,200}dropZoom\(\);/.test(CR));
check("a picture opened in the editor zooms too, dropped on the next open and on close",
  /_nePz = window\.JavisPanZoom\.attach\(pic\.parentNode, pic, \{ w: pic\.naturalWidth, h: pic\.naturalHeight \}\)/.test(CON) &&
  (CON.match(/_neDropPz\(\);/g) || []).length >= 2);
check("index.html loads pan-zoom.js before chat-render.js", HTML.indexOf("/static/pan-zoom.js") > 0 &&
  HTML.indexOf("/static/pan-zoom.js") < HTML.indexOf("/static/chat-render.js"));
check("no em or en dash in the new file", !/[–—]/.test(PZS));

if (fails.length) { console.log("\nFAIL " + fails.length + ": " + fails.join("; ")); process.exit(1); }
console.log("\nOK - test_pan_zoom: tất cả pass");
