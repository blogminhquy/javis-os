/* Test bo cong cu skill html-to-webcake. Chay tay / CI:
       node tests/js/test_html_to_webcake.js
   Khong can trinh duyet, khong cham mang, khong can npm install.

   VI SAO CO FILE NAY: skill nay tung bi go khoi Javis vi hong (cay con khong bao gio toi brain),
   va phan "doc HTML" truoc day KHONG CO - agent phai tu nhin roi go spec bang tay, nen ban dung
   ra lech mau/co chu/thu tu so voi trang goc. Bo test nay khoa lai dung nhung cho tung sai that:

     A. Cascade CSS: bien var(--x), clamp(), :root, @media danh gia theo be ngang tham chieu.
        (Loi that: @media(max-width:980px) bi xep nham vao desktop -> luoi 3 cot thanh 1 cot,
         thanh dieu huong bien mat.)
     B. Doc HTML -> spec: mau/co chu/canh le/anh/form/nut/the lay dung tu nguon.
        (Loi that: hang <div class="cta-row"> chua 2 the <a class="btn"> bi gop thanh MOT nut;
         tieu de "Hoi xong la quen" bi cat thanh icon "Hoi" + tieu de "xong la quen".)
     C. Engine dung trang: do chieu cao theo TUNG doan co chu khac nhau, chuoi nen anh dung khuon
        editor Webcake, chan customCss dat thuoc tinh hinh hoc.
     D. Codec .pke di duoc ca hai chieu.
*/
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");

const T = path.join(__dirname, "..", "..", ".claude", "skills", "html-to-webcake", "tools");
const H = require(path.join(T, "webcake-html.js"));
const B = require(path.join(T, "webcake-build.js"));
const L = require(path.join(T, "webcake-lint.js"));
const P = require(path.join(T, "webcake-pke.js"));
const F = require(path.join(T, "webcake-from-html.js"));

const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
const find = (n, tag) => {
  if (n.tag === tag) return n;
  for (const c of n.children || []) { const r = find(c, tag); if (r) return r; }
  return null;
};
function styled(html) {
  const root = H.parseHTML(html);
  const st = find(root, "style");
  const { rules } = H.parseCSS((st && st.children[0] && st.children[0].text) || "");
  H.computeStyles(root, rules);
  return root;
}
// gom moi item cua spec (ke ca item nam trong row/cardsRow) thanh mot mang phang
function flat(spec) {
  const out = [];
  (function walk(items) {
    for (const it of items || []) {
      if (!it || typeof it !== "object") continue;
      out.push(it);
      for (const k of ["items", "cards", "cols"]) if (Array.isArray(it[k])) walk(it[k]);
    }
  })(spec.sections.flatMap((s) => s.elements));
  return out;
}

/* ══════════ A. Cascade CSS ══════════ */

let root = styled(`<html><head><style>
  :root{--brand:#8b5cf6;--main:var(--brand)}
  h1{color:var(--main);font-size:clamp(20px,5vw,60px)}
  p{color:var(--khong-co,#123456);width:calc(100% - 48px)}
</style></head><body><h1>a</h1><p>b</p></body></html>`);
check("A1. bien CSS trong :root duoc doc va giai de quy",
  H.toRgba(find(root, "h1").css.color) === "rgba(139,92,246,1)");
check("A2. var() co gia tri du phong", H.toRgba(find(root, "p").css.color) === "rgba(18,52,86,1)");
check("A3. clamp() tinh ra so px", find(root, "h1").css.__fs === 48);
check("A4. calc() tinh duoc", H.toPx(find(root, "p").css.width, 16, 880) === 832);

check("A5. @media(max-width:980px) KHONG ap cho desktop", H.mediaMatch("(max-width:980px)", 1280) === false);
check("A6. @media(max-width:980px) ap cho mobile", H.mediaMatch("(max-width:980px)", 420) === true);
check("A7. @media(min-width:768px) ap cho desktop", H.mediaMatch("(min-width:768px)", 1280) === true);

root = styled(`<html><head><style>
  .g{display:grid;grid-template-columns:repeat(3,1fr)}
  @media(max-width:980px){ .g{grid-template-columns:1fr} .nav{display:none} }
</style></head><body><div class="g">x</div><div class="nav">y</div></body></html>`);
const g = find(root, "div");
check("A8. luoi 3 cot cua desktop KHONG bi ban mobile de len",
  g.css["grid-template-columns"] === "repeat(3,1fr)");
check("A9. khoi an tren mobile van hien o desktop",
  (root.children[0].children[1].children[1].css.display || "") !== "none");

check("A10. mau hex 3 ky tu", H.toRgba("#f00") === "rgba(255,0,0,1)");
check("A11. mau hsl", H.toRgba("hsl(0,100%,50%)") === "rgba(255,0,0,1)");
check("A12. ten mau", H.toRgba("white") === "rgba(255,255,255,1)");
check("A13. the <title> doc duoc chu (khong bi coi la the raw rong)",
  H.trimText(find(H.parseHTML("<html><head><title>Xin chao</title></head><body></body></html>"), "title")) === "Xin chao");

/* ══════════ B. Doc HTML -> spec ══════════ */

const SAMPLE = path.join(T, "..", "examples", "sample.html");
let out = F.convert(fs.readFileSync(SAMPLE, "utf8"), {});
let spec = out.spec;
check("B1. boc dung 3 section tu sample.html", spec.sections.length === 3);
check("B2. lay ten trang tu the <title>", spec.name === "Ebook Miễn Phí");
check("B3. nen section lay dung mau nguon", spec.sections[0].background === "rgba(17,17,17,1)");
check("B4. padding cua section thanh padTop/padBottom",
  spec.sections[0].padTop === 60 && spec.sections[0].padBottom === 60);
let items = flat(spec);
check("B5. co heading h1", items.some((i) => i.kind === "heading" && i.tag === "h1"));
check("B6. giu <b> thanh span dam", items.some((i) => i.kind === "text" && /font-weight:700/.test(i.html || "")));
check("B7. nut neo #dangky thanh scrollTo", items.some((i) => i.kind === "button" && i.scrollTo === "dangky"));
check("B8. anh giu nguyen URL",
  items.some((i) => i.kind === "image" && i.src === "https://statics.pancake.vn/web-media/demo-ebook.png"));
const form = items.find((i) => i.kind === "form");
check("B9. form doi ten truong ve chuan Webcake",
  !!form && form.fields.map((f) => f.name).join(",") === "full_name,email");
check("B10. nhan nut gui lay tu nguon", !!form && form.submitText === "GỬI EBOOK CHO TÔI");
check("B11. mau chu mac dinh la DEN (khong de engine roi ve mau sang tren nen trang)",
  spec.theme.colors.ink === "rgba(0,0,0,1)");

// hang nut + the + luoi
out = F.convert(`<html><head><style>
  body{background:#fff;color:#333}
  .cta-row{display:flex;gap:14px}
  .btn{background:#ff5500;color:#fff;padding:14px 28px;border-radius:8px}
  .g3{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
  .card{background:#f7f7f7;border-radius:12px;padding:20px}
  .kick{text-transform:uppercase;letter-spacing:.18em;font-size:13px}
  h2{line-height:1.1}
</style></head><body>
  <section>
    <p class="kick">van de</p>
    <h2>Tieu de</h2>
    <div class="cta-row"><a class="btn" href="https://a.vn">Mua ngay</a><a class="btn" href="https://b.vn">Xem them</a></div>
  </section>
  <section>
    <div class="g3">
      <div class="card"><span class="ico">🧠</span><h3>Hoi xong la quen</h3><p>Mo ta mot</p></div>
      <div class="card"><span class="ico">📊</span><h3>Khong biet so</h3><p>Mo ta hai</p></div>
      <div class="card"><span class="ico">💸</span><h3>Ton them tien</h3><p>Mo ta ba</p></div>
      <div class="card"><span class="ico">🔑</span><h3>The thu tu</h3><p>Mo ta bon</p></div>
    </div>
  </section>
</body></html>`, {});
spec = out.spec;
items = flat(spec);
const btns = items.filter((i) => i.kind === "button");
check("B12. hang chua 2 nut KHONG bi gop thanh mot nut", btns.length === 2);
check("B13. hai nut nam trong mot hang", items.some((i) => i.kind === "row" && i.cols.length === 2));
check("B14. nut giu href that", btns[0].href === "https://a.vn");
const rows = items.filter((i) => i.kind === "cardsRow");
const tail = items.find((i) => i.kind === "row" && i.cols.length === 1);
check("B15. luoi 3 cot: 3 the mot hang, the thu 4 xuong hang moi (khong nhet ca 4 vao mot hang)",
  rows.length === 1 && rows[0].cards.length === 3 && !!tail);
check("B15b. the le o hang cuoi giu be rong 1/3, khong phinh full chieu ngang",
  !!tail && Math.abs(tail.cols[0].w - 1 / 3) < 0.02);
const card0 = rows[0].cards[0];
check("B16. tieu de the KHONG bi cat nham thanh icon", card0.title === "Hoi xong la quen");
check("B17. emoji dung truoc tieu de thanh icon cua the", card0.icon === "🧠");
const kick = items.find((i) => /VAN DE/.test(String(i.html || "")));
check("B18. text-transform:uppercase duoc ap thang vao chu", !!kick);
check("B19. letter-spacing mang sang spec", !!kick && kick.letterSpacing > 2);
const h2 = items.find((i) => i.kind === "heading" && /Tieu de/.test(i.text || ""));
check("B20. line-height cua tieu de mang sang spec", !!h2 && h2.lineHeight === 1.1);

// chu to bang gradient
out = F.convert(`<html><head><style>
  em{background:linear-gradient(90deg,#8b5cf6,#22d3ee);-webkit-background-clip:text;color:transparent}
</style></head><body><section><h1>Xin <em>chao ban</em></h1><p>x</p></section><section><p>y</p></section></body></html>`, {});
const h1 = flat(out.spec).find((i) => i.kind === "heading");
check("B21. chu to gradient duoc giu (khong bien mat vi color:transparent)",
  /background-clip:text/.test(h1.text) && /chao ban/.test(h1.text));
check("B22. khong con color:transparent lam chu tang hinh", !/color:rgba\(0,0,0,0\)/.test(h1.text));

/* ══════════ C. Engine dung trang ══════════ */

check("C1. do chu theo TUNG doan: span 30px lam khoi cao hon han khi cung xuong dong",
  B.textH("<span style='font-size:30px;'>mot hai ba bon nam sau bay tam</span>", 12, 120) >
  B.textH("mot hai ba bon nam sau bay tam", 12, 120));
check("C2. mot dong chi co span nho van cao bang co chu goc (strut cua trinh duyet)",
  B.textH("<span style='font-size:8px;'>a</span>", 20, 400) >= Math.ceil(20 * 1.5));
check("C3. line-height rieng doi chieu cao", B.textH("a", 20, 400, false, { lh: 1.1 }) < B.textH("a", 20, 400));
check("C4. letter-spacing lam chu rong hon", B.lineW("abcdef", 16, false, 2) > B.lineW("abcdef", 16, false, 0));
check("C5. emoji rong 1.25em chu khong phai 1.5em",
  Math.abs(B.lineW("🧠", 100, false, 0) - 125) < 1);
check("C6. runsOf tach dung doan dam/co chu",
  B.runsOf("a<b>b</b><span style='font-size:22px'>c</span>", 14, false)
    .filter((r) => !r.br).map((r) => `${r.size}${r.bold ? "B" : ""}`).join(",") === "14,14B,22");

const built = B.buildPageSource({
  name: "t", theme: { colors: { bg: "rgba(10,10,10,1)" } },
  sections: [{
    name: "s", background: "$bg", elements: [
      { kind: "heading", text: "Xin chao", color: "rgba(255,255,255,1)" },
      { kind: "image", src: "https://x.vn/a.png", ratio: 1.5 },
      { kind: "button", text: "Mua", href: "https://x.vn", customCss: "box-shadow:0 2px 8px #000" }
    ]
  }]
});
const nodes = built.page[0].children;
const img = nodes.find((n) => n.type === "image-block");
check("C7. chuoi nen anh dung KHUON editor Webcake (co 'scroll')",
  img.responsive.desktop.styles.background ===
  "center center/ cover no-repeat scroll content-box url(https://x.vn/a.png) border-box");
const btn = nodes.find((n) => n.type === "button");
check("C8. customCss di qua specials.custom_css + customAdvance",
  btn.specials.customAdvance === true && /box-shadow/.test(btn.specials.custom_css));
let threw = false;
try {
  B.buildPageSource({ name: "t", sections: [{ name: "s", elements: [{ kind: "text", html: "a", customCss: "position:fixed" }] }] });
} catch (e) { threw = /hinh hoc/.test(e.message); }
check("C9. customCss dat thuoc tinh hinh hoc thi BI CHAN (khong lang le pha bo cuc)", threw);

// lint: tuong phan
const bad = B.buildPageSource({
  name: "t", sections: [{
    name: "s", background: "rgba(255,255,255,1)",
    elements: [{ kind: "text", html: "chim vao nen", color: "rgba(250,250,250,1)" }]
  }]
});
let rep = L.lintSource(bad);
check("C10. lint bat chu chim vao nen", rep.errors.some((e) => /KHONG DOC DUOC/.test(e)));
rep = L.lintSource(B.buildPageSource({
  name: "t", sections: [{ name: "s", elements: [{ kind: "text", html: "a", color: "rgba(0,0,0,1)" }] }]
}));
check("C11. lint canh bao section khong khai nen", rep.warns.some((w) => /khong co nen/.test(w)));

/* ══════════ D. HTML -> .pke chay het duong ══════════ */

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "wc-test-"));
const spec2 = F.convert(fs.readFileSync(SAMPLE, "utf8"), {}).spec;
const env = B.buildEnvelope(spec2);
const pke = P.encodeMsgpack(env).toString("base64");
fs.writeFileSync(path.join(tmp, "o.pke"), pke);
const back = P.decodeMsgpack(Buffer.from(pke, "base64"));
check("D1. .pke ma hoa roi giai lai khong mat gi",
  back.source.page.length === env.source.page.length &&
  back.source.settings.title === env.source.settings.title);
check("D2. envelope dung khuon Webcake (engine 2 + du 5 khoa source)",
  back.engine === 2 && ["settings", "popup", "page", "options", "cartConfigs"]
    .every((k) => k in back.source));
const finalRep = L.lintSource(env.source);
check("D3. ban dung tu sample.html khong con loi layout", finalRep.errors.length === 0);
fs.rmSync(tmp, { recursive: true, force: true });

console.log();
if (fails.length) {
  console.log(`${fails.length} test FAIL: ` + fails.join(", "));
  process.exit(1);
}
console.log("Tat ca test PASS");
