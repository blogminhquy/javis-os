/* Mascot own picture (2026-11-07): the pet shows an uploaded picture cut to its shape, and the same picture can
   become the browser tab icon so several Javis open side by side tell apart.

       node tests/js/test_pet_own_picture.js

   Loads the real pet.js on a fake DOM and checks what it draws and what it asks for:
   - a still portrait with a picture uses <image> clipped to the shape and no drawn eyes; a bad name falls back;
   - the mascot editor (opts.image) has the upload button and, once a picture is set, the tab icon switch;
   - the partner avatar editor (no opts.image) stays exactly as before: no second upload row there;
   - faviconHref follows the picture and the switch; junk names never reach the config. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

function node() {
  const o = {
    _html: "", disabled: false, textContent: "", dataset: {}, attrs: {},
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    style: { setProperty() {} }, setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] || null; },
    addEventListener() {}, appendChild() {}, querySelector: () => node(), querySelectorAll: () => [],
    get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  };
  return o;
}

const win = {
  JavisPet: null, matchMedia: () => ({ matches: false, addEventListener() {} }),
  addEventListener() {}, dispatchEvent() {}, innerWidth: 1280, innerHeight: 800,
};
const iconLinks = [];
const head = {
  querySelector: (s) => (s.indexOf("icon") >= 0 ? iconLinks[0] || null : null),
  querySelectorAll: () => iconLinks.slice(),
  appendChild: (l) => { l.parentNode = { removeChild: (x) => iconLinks.splice(iconLinks.indexOf(x), 1) }; iconLinks.push(l); },
};
const doc = {
  documentElement: { dataset: { javisTheme: "dark" }, getAttribute: () => "dark", classList: { contains: () => false } },
  addEventListener() {}, querySelectorAll: () => [], querySelector: () => node(), head,
  getElementById: () => node(), createElement: () => node(), createElementNS: () => node(), body: node(),
};
global.CustomEvent = function () {};
new Function("window", "document", "localStorage", "navigator", "matchMedia",
  "requestAnimationFrame", "cancelAnimationFrame", "getComputedStyle", "fetch",
  fs.readFileSync(path.join(ROOT, "dashboard", "pet.js"), "utf8"))(
  win, doc, { getItem: () => null, setItem() {} }, { userAgent: "node" }, win.matchMedia,
  () => 0, () => {}, () => ({ getPropertyValue: () => "" }), () => new Promise(() => {}));
const P = win.JavisPet;
check("pet.js loads", !!P);

const NAME = "0123456789abcdef0123.webp";

// Still portrait.
const withPic = P.previewSvg("star", "cam", { anh: NAME });
check("portrait draws the picture", withPic.indexOf('<image href="/avatars/' + NAME + '"') >= 0, withPic.slice(0, 200));
check("picture is clipped to the shape", /clipPath id="(petClip\d+)"/.test(withPic) && withPic.indexOf("clip-path=\"url(#" + withPic.match(/clipPath id="(petClip\d+)"/)[1] + ")\"") >= 0);
check("no drawn eyes over the picture", withPic.indexOf("<ellipse") < 0);
const twice = P.previewSvg("circle", "cam", { anh: NAME });
check("each portrait gets its own clip id", withPic.match(/petClip\d+/)[0] !== twice.match(/petClip\d+/)[0]);
const bad = P.previewSvg("star", "cam", { anh: '../x"><script>' });
check("bad picture name falls back to the drawn face", bad.indexOf("<image") < 0 && bad.indexOf("<ellipse") >= 0);

// Mascot editor.
const ed0 = P.editorHtml(P.get(), { size: true, vanh: true, image: true });
check("mascot editor has the upload button", ed0.indexOf("data-pet-upload") >= 0 && ed0.indexOf("data-pet-file") >= 0);
check("no tab icon switch before a picture exists", ed0.indexOf("data-pet-favicon") < 0);
const ed1 = P.editorHtml(Object.assign(P.get(), { image: NAME }), { size: true, vanh: true, image: true });
check("tab icon switch shows with a picture, on by default", /data-pet-favicon checked/.test(ed1));
check("button back to the Javis face shows with a picture", ed1.indexOf("data-pet-unimg") >= 0);
check("shape picker previews the picture", (ed1.match(/<image href="\/avatars\//g) || []).length >= 6);
const edOff = P.editorHtml(Object.assign(P.get(), { image: NAME, favicon: false }), { image: true });
check("switch reflects favicon:false", edOff.indexOf("data-pet-favicon>") >= 0 && !/data-pet-favicon checked/.test(edOff));

// Partner avatar editor: unchanged.
const edAgent = P.editorHtml(Object.assign(P.get(), { image: NAME }), {});
check("partner editor has no mascot upload row", edAgent.indexOf("data-pet-upload") < 0 && edAgent.indexOf("data-pet-favicon") < 0);
check("partner editor shape picker keeps the drawn faces", edAgent.indexOf("<image") < 0);

// Config and tab icon.
check("no picture: no tab icon request", P.faviconHref() === "");
P.setCfg({ image: NAME });
check("picture kept in config", P.get().image === NAME && P.get().favicon === true);
check("tab icon follows the picture", P.faviconHref() === "/pet-icon?v=0123456789abcdef0123", P.faviconHref());
check("the page icon link was swapped", iconLinks.length === 2 && iconLinks[0].attrs.href === "/pet-icon?v=0123456789abcdef0123",
  JSON.stringify(iconLinks.map((l) => l.attrs)));
P.setCfg({ favicon: false });
check("switch off: no tab icon", P.faviconHref() === "");
check("switch off: the tab goes back to the logo", iconLinks.length === 2 && iconLinks[0].attrs.href.indexOf("/brand-logo") === 0,
  JSON.stringify(iconLinks.map((l) => l.attrs)));
P.setCfg({ image: "../../settings.json", favicon: true });
check("junk picture name never reaches the config", P.get().image === "", P.get().image);

if (fails.length) { console.log("\n" + fails.length + " FAILED"); process.exit(1); }
console.log("\nOK - mascot own picture");
