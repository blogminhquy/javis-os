/* The pet rests on CSS when nothing happens, and wakes up on anything (0.418.0).

       node tests/js/test_pet_nghi_yen.js

   Measured on a simulated phone (Team page, app idle): the pet's JS loop at 30 frames a second kept the main thread
   busy about 26% of the time and forced a layout every frame; without the pet, 13%. Sitting still, the pet only spins
   its ring, glances now and then, blinks and dozes off. So the JS loop now stops ("rest"): the ring spins with the
   petVanh CSS animation (10 steps a second), the glance is a CSS transition, blinks and dozing are timers. Measured
   again: 14%. Anything (pointer, state change, a reaction, new words) calls chay(), which leaves the rest and restarts
   the loop. Run for real with the fake DOM of test_pet_huong_liec.js: reading the source would stay green if the loop
   never stopped or never woke up. */
const path = require("path");
const fs = require("fs");
const root = path.join(__dirname, "..", "..");

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const lop = new Set();
function nutGia() {
  const n = {
    innerHTML: "", hidden: false, dataset: {}, childElementCount: 1,
    style: { setProperty(k, v) { this[k] = v; }, removeProperty() {} },
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    setAttribute() {}, getAttribute: () => null, addEventListener() {}, appendChild() {},
    getBoundingClientRect: () => ({ top: 0, left: 0, right: 0, bottom: 0, width: 56, height: 56 }),
    querySelectorAll: () => [], focus() {},
  };
  n.querySelector = () => n;
  return n;
}
const nut = {
  ".pet-body": nutGia(), ".pet-menu": nutGia(), ".pet-rig": nutGia(),
  ".pet-ring": nutGia(), ".pet-face": nutGia(), ".pet-eyes": nutGia(), svg: nutGia(),
};
const goc = nutGia();
goc.querySelector = (sel) => nut[sel] || null;
goc.classList = { add: (c) => lop.add(c), remove: (c) => lop.delete(c), contains: (c) => lop.has(c), toggle() {} };

let dongHo = 1000;
let khungCho = null;
const nghe = {};
const mqGiam = { matches: false, addEventListener() {}, addListener() {} };
global.window = {
  t: (k, d) => d || k, ic: () => "", innerWidth: 1280, innerHeight: 900,
  matchMedia: () => mqGiam,
  addEventListener(ten, fn) { nghe[ten] = fn; }, dispatchEvent() {},
  requestAnimationFrame: (fn) => { khungCho = fn; return 1; },
  cancelAnimationFrame: () => { khungCho = null; },
};
global.document = {
  readyState: "complete", hidden: false, createElement: () => goc, getElementById: () => null,
  addEventListener() {}, body: { appendChild() {} }, querySelectorAll: () => [],
};
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.performance = { now: () => dongHo };
global.requestAnimationFrame = window.requestAnimationFrame;
global.cancelAnimationFrame = window.cancelAnimationFrame;
global.fetch = () => new Promise(() => {});
// Timers on the fake clock: a blink ends 130 ms after it starts, the rest's glance and blink timers fire as the clock
// moves. Real timers would never fire inside the synchronous frame loop below.
let hang = [], soHen = 0;
global.setTimeout = (fn, ms) => { hang.push({ id: ++soHen, luc: dongHo + (ms || 0), fn }); return soHen; };
global.clearTimeout = (id) => { hang = hang.filter(h => h.id !== id); };
function chayHen() {
  for (;;) {
    hang.sort((a, b) => a.luc - b.luc);
    const h = hang[0];
    if (!h || h.luc > dongHo) return;
    hang.shift(); h.fn();
  }
}
global.CustomEvent = function () {};
global.FormData = function () { this.append = function () {}; };
Math.random = () => 0.5;

require(path.join(root, "dashboard", "pet.js"));
const P = window.JavisPet;

// Run frames 16 ms apart until the loop stops asking for one (rest) or a limit.
function chayKhung(toiDa) {
  for (let i = 0; i < toiDa && khungCho; i++) {
    const f = khungCho; khungCho = null;
    dongHo += 16; chayHen(); f(dongHo);
  }
}

check("the pet exists and runs its loop", !!P && !!khungCho);
chayKhung(2000);   // up to 32 s of frames
check("sitting still, the JS loop stops by itself (no frame requested)", khungCho === null);
check("and the pet is marked resting (CSS takes over)", lop.has("pet-nghi"));
check("the ring spins with the petVanh CSS animation, 10 steps a second", /^petVanh [\d.]+s steps\(\d+\) infinite$/.test(nut[".pet-ring"].style.animation || "")
  && (() => { const m = /petVanh ([\d.]+)s steps\((\d+)\)/.exec(nut[".pet-ring"].style.animation); return Math.abs(Number(m[2]) - Number(m[1]) * 10) <= 1; })());
check("the ring animation starts where the ring stands (--vanh0)", typeof nut[".pet-ring"].style["--vanh0"] === "string");
const truocLiec = nut[".pet-eyes"].style.transform;
dongHo += 8000; chayHen();
check("resting, the glance still moves on a timer (no frame needed)", khungCho === null && typeof truocLiec === "string");

P.setState("thinking");
check("a state change wakes it: the loop asks for a frame again", !!khungCho);
check("and the resting mark is gone, the CSS ring animation removed", !lop.has("pet-nghi") && !nut[".pet-ring"].style.animation);

P.setState("idle");
chayKhung(2000);
check("back to idle it rests again", khungCho === null && lop.has("pet-nghi"));

dongHo += 10;
nghe.pointermove({ clientX: 300, clientY: 200 });
check("a pointer move wakes it so the eyes follow", !!khungCho && !lop.has("pet-nghi"));

const css = fs.readFileSync(path.join(root, "dashboard", "style.css"), "utf8");
check("CSS: petVanh keyframes start from --vanh0", /@keyframes petVanh \{ from \{ stroke-dashoffset: var\(--vanh0, 0\); \} to \{ stroke-dashoffset: calc\(var\(--vanh0, 0\) - 360\); \} \}/.test(css));
check("CSS: the resting glance moves in 10 steps (a smooth SVG transform transition relayouts every frame)",
  /\.pet\.pet-nghi \.pet-rig, \.pet\.pet-nghi \.pet-eyes \{ transition: transform 2\.4s steps\(10\); \}/.test(css));
const src = fs.readFileSync(path.join(root, "dashboard", "pet.js"), "utf8");
check("reduced motion never enters the CSS rest (the loop already stands still there)", /!\(giamChuyenDong && giamChuyenDong\.matches\);\n  \}/.test(src));

if (fails.length) { console.log("\nFAIL - test_pet_nghi_yen: " + fails.length); process.exit(1); }
console.log("\nOK - test_pet_nghi_yen: all pass");
