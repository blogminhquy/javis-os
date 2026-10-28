// Kho cai dat: icon tren the (0.376.0).
//
//     node tests/js/test_kho_icon.js
//
// Chu repo che o chu cai dam mau ("Su", "LP") la xau va khong noi len gi. Gio: logo that neu co,
// tro ly (agent) ve chan dung tro ly y nhu trang Cong su (JavisAvatar), con lai la icon cua LOAI
// (skill = manh ghep "puzzle", quy trinh = "workflow", cong cu = "toolbox") tren o mau nhat.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const doc = {
  getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
  createElement: () => ({ style: {}, classList: { add() {}, remove() {} }, querySelectorAll: () => [], appendChild() {} }),
  body: { appendChild() {} },
};
const avatarGoi = [];
const win = {
  ic: (t) => '<svg data-ic="' + t + '"></svg>',
  Icons: { has: (t) => t === "megaphone" },
  JavisPet: {},
  JavisAvatar: { html: (a, size) => { avatarGoi.push([a.slug, size]); return '<span class="agent-avatar" data-slug="' + a.slug + '"></span>'; } },
  Alpine: { store: () => ({ go() {} }) },
};
const _alpineCu = globalThis.Alpine;
globalThis.Alpine = win.Alpine;
new Function("window", "document", "fetch",
  fs.readFileSync(path.join(ROOT, "dashboard", "packs.js"), "utf8"))(win, doc, () => Promise.resolve({}));
const P = win.JavisPacks || {};

const goi = (o) => Object.assign({ id: "javis.x", kind: "skill", name: { vi: "Superpowers" }, description: { vi: "a" },
  tier: "data", verified: true, nguon: "kho", author: { name: "A" }, version: "1.0.0" }, o);
const dau = (html) => html.slice(html.indexOf('<div class="kho-dau">'), html.indexOf('<span class="kho-nhom">'));

const skill = dau(P.theKho(goi({})));
check("skill: icon manh ghep cua trang Ky nang", skill.includes('data-ic="puzzle"') && skill.includes("kho-ava-ic"));
check("skill: khong con o chu cai", !/>Su</.test(skill));
check("skill: o co mau rieng theo id", /--kho-mau:#[0-9a-f]{6}/.test(skill));
check("quy trinh: icon quy trinh", dau(P.theKho(goi({ kind: "workflow" }))).includes('data-ic="workflow"'));
check("cong cu: icon cong cu", dau(P.theKho(goi({ kind: "tool" }))).includes('data-ic="toolbox"'));
check("loai la: icon goi", dau(P.theKho(goi({ kind: "la-lam" }))).includes('data-ic="package"'));

const agent = dau(P.theKho(goi({ id: "javis.tro-ly", kind: "agent" })));
check("agent: chan dung tro ly nhu trang Cong su", agent.includes('class="agent-avatar"') && agent.includes("kho-ava-agent"));
check("agent: chan dung theo id goi, co 40px", avatarGoi.some(x => x[0] === "javis.tro-ly" && x[1] === 40));

check("logo that van la anh", dau(P.theKho(goi({ kind: "connector", icon: "https://kho/a.png" }))).includes('<img src="https://kho/a.png"'));
check("icon Lucide khai san duoc dung", dau(P.theKho(goi({ icon: "megaphone" }))).includes('data-ic="megaphone"'));
check("ten icon la khong dung, roi ve icon loai", dau(P.theKho(goi({ icon: "khong-co" }))).includes('data-ic="puzzle"'));

delete win.JavisAvatar;
check("agent khi chua nap thu vien chan dung: roi ve icon tro ly",
  dau(P.theKho(goi({ kind: "agent" }))).includes('data-ic="bot"'));

globalThis.Alpine = _alpineCu;
if (fails.length) {
  console.log(`FAIL - test_kho_icon: ${fails.length} loi: ${fails.join("; ")}`);
  process.exit(1);
}
console.log("OK - test_kho_icon: tat ca pass");
