/* Light/dark theme by hand or by the clock (0.74.0).

       node tests/js/test_theme_schedule.js

   The owner asked for three choices in Settings: always dark, always light, or Auto, where the
   page turns light at the morning hour and dark at the evening hour by itself.

   What this pins, by RUNNING the real code rather than grepping it:
   - theme.js with a fake clock: the right tone at each hour, overnight windows, equal times,
     a bad stored schedule, the 30-second tick crossing the boundary, and the top-bar button
     dropping back to a manual choice.
   - The tiny pre-paint script at the top of index.html computes the SAME answer as
     theme.js for every minute of the day. If they drift, Auto users see the page flash
     the wrong tone on every load, and nothing else would catch it.
   - renderThemeBox in console.js draws the three choices and the two time fields, with every
     label present in both dictionaries. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- Minimal browser for theme.js ----
function boot(store, clock) {
  const attrs = {};
  const listeners = {};
  const docListeners = {};
  const timers = [];
  const events = [];
  const meta = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
  const btn = {
    attrs: {}, title: "", setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(ev, fn) { this.click = fn; },
  };
  const root = {
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
    setAttribute: (k, v) => { attrs[k] = String(v); },
    removeAttribute: (k) => { delete attrs[k]; },
  };
  const doc = {
    documentElement: root, readyState: "complete", hidden: false,
    head: { appendChild() {} },
    querySelector: (s) => (s.includes("theme-color") ? meta : null),
    getElementById: (id) => (id === "themeToggle" ? btn : null),
    createElement: () => meta,
    addEventListener: (ev, fn) => { (docListeners[ev] = docListeners[ev] || []).push(fn); },
  };
  const win = {
    addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
    dispatchEvent: (e) => { events.push(e); (listeners[e.type] || []).forEach(f => f(e)); },
  };
  class CustomEvent { constructor(type, o) { this.type = type; this.detail = o && o.detail; } }
  const ls = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
  };
  class FakeDate extends Date {
    constructor(...a) { if (a.length) super(...a); else super(clock.now); }
  }
  new Function("window", "document", "localStorage", "CustomEvent", "Date", "setInterval",
    fs.readFileSync(path.join(ROOT, "dashboard", "theme.js"), "utf8"))(
    win, doc, ls, CustomEvent, FakeDate, (fn, ms) => { timers.push({ fn, ms }); return timers.length; });
  return {
    T: win.javisTheme, root, btn, meta, store, events, timers,
    light: () => root.getAttribute("data-theme") === "light",
    fire: (ev, e) => (listeners[ev] || []).forEach(f => f(e || {})),
    fireDoc: (ev) => (docListeners[ev] || []).forEach(f => f({})),
  };
}
const at = (h, m) => new Date(2026, 9, 4, h, m || 0).getTime();

// ---- Defaults and manual modes ----
// Since 0.75.1 a device that never picked a theme runs on Auto (owner, 2026-10-05).
{
  const b = boot({}, { now: at(12) });
  check("no saved choice means Auto", b.T.mode() === "auto");
  check("so a fresh device is light at noon", b.light());
  check("and nothing is written until the user picks", !("javis.theme" in b.store));
  check("a fresh device is dark at night", !boot({}, { now: at(22) }).light());
  check("an explicit dark choice is kept", !boot({ "javis.theme": "dark" }, { now: at(12) }).light());
  check("default schedule is 06:00 to 18:00", JSON.stringify(b.T.schedule()) === '{"light":"06:00","dark":"18:00"}');
  b.T.setMode("light");
  check("manual light turns light", b.light() && b.store["javis.theme"] === "light");
  check("browser bar colour follows the tone", b.meta.attrs.content === "#ffffff");
  b.T.setMode("bogus");
  check("unknown mode falls back to Auto", b.store["javis.theme"] === "auto" && b.light());
}
{
  const b = boot({ "javis.theme": "dim" }, { now: at(12) });
  check("old 'dim' value is migrated to dark", b.store["javis.theme"] === "dark" && !b.light());
}

// ---- Auto: the clock decides ----
{
  const clock = { now: at(12) };
  const b = boot({ "javis.theme": "auto" }, clock);
  check("auto at noon is light", b.light());
  check("next change is the evening time", b.T.nextChange() === "18:00");
  check("button tooltip says Auto", /Auto by time, light now/.test(b.btn.title), b.btn.title);
  check("the clock is polled every 30 seconds", b.timers.length === 1 && b.timers[0].ms === 30000);

  const before = b.events.length;
  b.timers[0].fn();
  check("a tick with no change does not repaint canvases", b.events.length === before);

  clock.now = at(18, 0);
  b.timers[0].fn();
  check("tick at 18:00 turns dark", !b.light());
  check("and tells canvases once", b.events.length === before + 1);
  check("next change is now the morning time", b.T.nextChange() === "06:00");

  clock.now = at(6, 0);
  b.fireDoc("visibilitychange");
  check("coming back to the tab at 06:00 turns light at once", b.light());

  clock.now = at(5, 59);
  b.fire("focus");
  check("05:59 is still night", !b.light());

  // Top-bar button: a manual pick of the other tone, leaving Auto.
  clock.now = at(12);
  b.fire("focus");
  b.btn.click();
  check("button in Auto picks the other tone by hand", !b.light() && b.T.mode() === "dark");
  clock.now = at(13);
  b.timers[0].fn();
  check("and the clock no longer overrides it", !b.light());
}

// ---- Schedules: custom, overnight, equal, broken ----
{
  const clock = { now: at(21) };
  const b = boot({ "javis.theme": "auto" }, clock);
  check("setSchedule rejects garbage", b.T.setSchedule("25:00", "18:00") === false
    && b.T.setSchedule("abc", "18:00") === false);
  check("setSchedule accepts and normalises", b.T.setSchedule("7:05", "22:30") === true
    && b.store["javis.theme.schedule"] === "07:05-22:30");
  check("21:00 inside 07:05-22:30 is light right away", b.light());

  b.T.setSchedule("20:00", "04:00");      // night-shift worker: light overnight
  check("overnight window: 21:00 is light", b.light());
  check("overnight window: 03:59 is light", b.T.lightAt(new Date(at(3, 59)), b.T.schedule()));
  check("overnight window: 04:00 is dark", !b.T.lightAt(new Date(at(4, 0)), b.T.schedule()));
  check("overnight window: noon is dark", !b.T.lightAt(new Date(at(12)), b.T.schedule()));

  b.T.setSchedule("08:00", "08:00");
  check("equal times mean dark all day", !b.light() && b.T.nextChange() === "");

  const bad = boot({ "javis.theme": "auto", "javis.theme.schedule": "nonsense" }, { now: at(12) });
  check("a broken stored schedule falls back to the default", bad.light()
    && bad.T.schedule().light === "06:00");
}

// ---- Another tab changes the setting ----
{
  const store = { "javis.theme": "dark" };
  const clock = { now: at(12) };
  const b = boot(store, clock);
  store["javis.theme"] = "auto";
  b.fire("storage", { key: "javis.theme" });
  check("a change in another tab applies here", b.light());
  store["javis.theme.schedule"] = "13:00-14:00";
  b.fire("storage", { key: "javis.theme.schedule" });
  check("a schedule change in another tab applies here", !b.light());
}

// ---- The pre-paint script in index.html must agree with theme.js ----
const html = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
const pre = (html.match(/<script>(\(function\(\)\{try\{var m=localStorage\.getItem\('javis\.theme'\)[\s\S]*?)<\/script>/) || [])[1];
check("found the pre-paint script", !!pre);
check("theme.js is cache-busted past the old version", /\/static\/theme\.js\?v=([3-9]|\d\d)/.test(html));
if (pre) {
  const runPre = (store, now) => {
    const attrs = {};
    class FakeDate extends Date { constructor(...a) { if (a.length) super(...a); else super(now); } }
    new Function("localStorage", "document", "Date", pre)(
      { getItem: (k) => (k in store ? store[k] : null) },
      { documentElement: { setAttribute: (k, v) => { attrs[k] = v; } } }, FakeDate);
    return attrs["data-theme"] === "light";
  };
  const cases = ["unset", undefined, "06:00-18:00", "07:05-22:30", "20:00-04:00", "08:00-08:00", "nonsense"];
  let mismatch = "";
  for (const sch of cases) {
    const store = sch === "unset" ? {} : { "javis.theme": "auto" };
    if (sch && sch !== "unset") store["javis.theme.schedule"] = sch;
    for (let m = 0; m < 1440 && !mismatch; m += 1) {
      const now = at(0, m);
      const b = boot(Object.assign({}, store), { now });
      if (b.light() !== runPre(store, now)) mismatch = (sch || "default") + " @ " + m + " min";
    }
  }
  check("pre-paint and theme.js agree for every minute of the day", !mismatch, mismatch);
  check("pre-paint keeps manual light", runPre({ "javis.theme": "light" }, at(23)));
  check("pre-paint keeps manual dark", !runPre({ "javis.theme": "dark" }, at(12)));
  check("pre-paint: no saved choice is Auto (light at noon)", runPre({}, at(12)));
  check("pre-paint: no saved choice is Auto (dark at night)", !runPre({}, at(22)));
  check("pre-paint: old 'dim' stays dark, no flash before the migration",
    !runPre({ "javis.theme": "dim" }, at(12)) && !boot({ "javis.theme": "dim" }, { now: at(12) }).light());
}

// ---- Settings card in console.js ----
function bodyOf(src, decl) {
  const i = src.indexOf(decl);
  if (i < 0) return null;
  let d = 0, j = src.indexOf("{", i);
  const start = j;
  for (; j < src.length; j++) {
    if (src[j] === "{") d++;
    else if (src[j] === "}" && !--d) break;
  }
  return src.slice(start + 1, j);
}
const consoleSrc = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const renderBody = bodyOf(consoleSrc, "function renderThemeBox(box) {");
const nowBody = bodyOf(consoleSrc, "function themeNowText(T) {");
check("found renderThemeBox and themeNowText in console.js", !!renderBody && !!nowBody);
check("settings page mounts the theme card", /id="vpThemeBox"/.test(consoleSrc)
  && /renderThemeBox\(document\.getElementById\("vpThemeBox"\)\)/.test(consoleSrc));

for (const lang of ["vi", "en"]) {
  const dict = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", lang + ".json"), "utf8"));
  const t = (k, v) => (typeof dict[k] === "string"
    ? dict[k].replace(/\{(\w+)\}/g, (m, n) => (v && v[n] != null ? v[n] : m)) : "!!MISSING:" + k + "!!");
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const draw = (b) => {
    const box = { innerHTML: "", querySelectorAll: () => [], querySelector: () => null };
    const themeNowText = new Function("t", "T", nowBody).bind(null, t);
    new Function("box", "window", "t", "esc", "toast", "themeNowText", renderBody)(
      box, { javisTheme: b.T }, t, esc, () => {}, themeNowText);
    return box.innerHTML;
  };
  const manual = draw(boot({ "javis.theme": "light" }, { now: at(12) }));
  check(`[${lang}] three choices drawn`, ["dark", "light", "auto"].every(v => manual.includes(`data-theme-mode="${v}"`)));
  check(`[${lang}] the current choice is selected`, /seg-btn sel" data-theme-mode="light"/.test(manual));
  check(`[${lang}] no time fields in manual mode`, !manual.includes('type="time"'));
  const auto = draw(boot({ "javis.theme": "auto" }, { now: at(20) }));
  check(`[${lang}] Auto shows both time fields`, auto.includes('id="vpThemeLight" value="06:00"')
    && auto.includes('id="vpThemeDark" value="18:00"'));
  check(`[${lang}] Auto says when it switches next`, auto.includes("06:00"));
  const flat = draw(boot({ "javis.theme": "auto", "javis.theme.schedule": "08:00-08:00" }, { now: at(20) }));
  check(`[${lang}] equal times explain the all-dark result`, flat.includes(esc(dict["settings.theme.now_flat"])));
  const all = manual + auto + flat;
  check(`[${lang}] every label has a translation`, !all.includes("!!MISSING:"),
    (all.match(/!!MISSING:[^!]+!!/g) || []).join(", "));
  check(`[${lang}] tooltip keys for Auto exist`, !!dict["top.theme_auto_light"] && !!dict["top.theme_auto_dark"]);
}

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nAll OK");
process.exit(fails.length ? 1 : 0);
