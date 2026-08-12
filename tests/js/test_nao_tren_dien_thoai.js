/* Khoang nao tren DIEN THOAI: do thi phai du to de nhin, va ba nut goc phai phai bam duoc.

       node tests/js/test_nao_tren_dien_thoai.js

   Loi that chu repo bao (2026-08-06, kem anh chup iPhone): "O dien thoai khi nao thu nho thi
   no qua be ko thay gi ca."

   Do lai bang trinh duyet that (Chromium 390x844, dpr 3) truoc khi sua: khoang nao cao 228px,
   ma `zoomToFit(500, 70)` chua 70px moi ben -> con dung 88px cho TOAN BO do thi. Cum node ra
   87x88 giua mot khung 390x228, tuc chiem 22% be ngang. Do la "cuc nho xiu" trong anh.

   Ba thu khac cong don vao cung mot cho:
     - 8 nhan thu muc rai kin khung, ten dai ("BRAIN DEFAULT") tran han ra ngoai mep phai.
     - Dai Agents/Skills/Workflows xep chong (so tren, nhan duoi) cao ~56px = mot phan tu khung.
     - San luoi phoi canh bat dau tu 72% chieu cao, an them 28% cuoi.

   Va mot loi CO SAN chua ai thay: ca ba nut goc phai deu mang class .brain-overlay-toggle, nen
   dong `top: 7px` trong khoi mobile cua console.css de luon `.graph-timelapse-btn { top: 58px }`
   ben style.css (cung do uu tien, console.css nap sau). Hai nut chong khit len nhau, nut ve sau
   an het cu cham -> tren dien thoai KHONG BAM DUOC nut an nhan.

   Kiem tren SOURCE that, khong doc thuoc long. */
const fs = require("fs");
const path = require("path");

const D = (f) => fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", f), "utf8");
const GRAPH = D("graph.js");
const APP = D("app.js");
const CONSOLE_CSS = D("console.css");
const STYLE = D("style.css");
const HTML = D("index.html");
const MOBILE = D("mobile-chat.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- 1. Le canh khung phai theo KICH THUOC KHUNG, khong phai hang so ----
// Boc chu thich truoc khi soi: chu thich trong graph.js CO QUYEN nhac lai `zoomToFit(500, 70)`
// de giai thich vi sao bo no, va bat nham chinh dong giai thich do la mot test vo dung.
const GRAPH_CODE = GRAPH.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
check("CANARY: khong con zoomToFit voi le cung 70",
  GRAPH_CODE.indexOf("zoomToFit(500, 70)") === -1);
check("co ham tinh le theo khung", /_fitPad\s*\(\)\s*\{/.test(GRAPH));
check("le tinh tu ben NHO nhat cua khung", /Math\.min\(w \|\| 800, h \|\| 600\)/.test(GRAPH));
check("le co tran duoi/tren (khong bao gio 0, khong vuot 70)",
  /Math\.max\(10, Math\.min\(70, Math\.round\(nho \* 0\.10\)\)\)/.test(GRAPH));
check("zoomToFit dung le da tinh", /zoomToFit\(ms, this\._fitPad\(\)\)/.test(GRAPH));

// Bung/thu khoang nao doi kich thuoc canvas -> phai canh lai, va phai MO minZoom truoc.
// Thieu buoc mo: lan fit truoc da kep minZoom o muc cua khung CU, khung to hon khong bao gio
// zoom-out du de thay het do thi.
check("co refit() de canh lai khi khung doi co", /refit\s*\(ms\s*=\s*400\)\s*\{/.test(GRAPH));
const REFIT = GRAPH.slice(GRAPH.indexOf("refit(ms = 400)"), GRAPH.indexOf("resize() {", GRAPH.indexOf("refit(ms = 400)")));
check("CANARY: refit mo lai minZoom TRUOC khi fit",
  REFIT.indexOf("minZoom(0.05)") !== -1 && REFIT.indexOf("minZoom(0.05)") < REFIT.indexOf("_fit("));
check("refit do lai kich thuoc canvas truoc", REFIT.indexOf("this.resize()") < REFIT.indexOf("_fit("));

// ---- 2. Nhan thu muc: khung hep thi it nhan hon va khong tran mep ----
check("so nhan + ban kinh tinh theo be ngang khoang nao",
  /const hep = pw < 620 \|\| ph < 320;/.test(APP) && /hep \? 4 : 8/.test(APP));
check("khung hep chua khe day rong hon cho chu trang thai", /hep \? 104 : 76/.test(APP));
check("ban kinh ngang keo vao trong khi hep", /const rx = hep \? 33 : 40;/.test(APP));
check("CANARY: desktop giu nguyen 8 nhan va ban kinh cu",
  /hep \? 4 : 8/.test(APP) && /hep \? 33 : 40/.test(APP) && /hep \? 34 : 32/.test(APP));
check("ten dai bi kep + cat bang ba cham, khong tran ra ngoai khoang",
  /\.concept-label \{ max-width: 32vw; \}/.test(CONSOLE_CSS) &&
  /\.concept-label \.cl-name, \.concept-label \.cl-meta \{[\s\S]{0,120}text-overflow: ellipsis/.test(CONSOLE_CSS));
check("xoay may thi rai lai nhan (co cache + debounce)",
  /_catsCache/.test(APP) && /addEventListener\("resize"/.test(APP) && /_catsT/.test(APP));

// ---- 3. San luoi khong an cho cua do thi tren khung thap ----
check("chan troi tut xuong khi khoang nao thap",
  /cssH \* \(cssH < 320 \? 0\.86 : 0\.72\)/.test(APP));

// ---- 4. Dai so lieu mong lai: so va nhan cung mot dong ----
const MOB = CONSOLE_CSS.slice(CONSOLE_CSS.indexOf("@media (max-width: 860px)"));
check("bstat xep NGANG tren mobile (khong chong doc nhu desktop)",
  /\.bstat \{ flex: 1 1 0; flex-direction: row;/.test(MOB));
check("nhan bstat khong con day xuong dong duoi", /\.bstat-lbl \{ margin-top: 0;/.test(MOB));

// ---- 5. Ba nut goc phai KHONG duoc chong len nhau ----
// Day la loi co san: chung deu la .brain-overlay-toggle nen `top: 7px` cua khoi mobile de
// luon top: 58px cua .graph-timelapse-btn. Khoa lai bang cach doi console.css phai tu dat
// top tuong minh cho ca hai nut con lai.
const tlTop = /\.graph-timelapse-btn \{ top: 46px; \}/.test(MOB);
const mxTop = /\.brain-max-btn \{ top: 85px; \}/.test(MOB);
check("CANARY: mobile dat top tuong minh cho nut timelapse", tlTop);
check("CANARY: mobile dat top tuong minh cho nut bung nao", mxTop);
check("ba nut ba hang khac nhau, khong trung toa do",
  /\.brain-overlay-toggle \{\s*top: 7px;/.test(MOB) && tlTop && mxTop);
// Man thap cung phai xep dung, chi khac khoang cach.
const THAP = CONSOLE_CSS.slice(CONSOLE_CSS.indexOf("@media (max-width: 860px) and (max-height: 620px)"));
check("man thap van xep ba hang", /\.graph-timelapse-btn \{ top: 42px; \}/.test(THAP) &&
  /\.brain-max-btn \{ top: 77px; \}/.test(THAP));

// ---- 6. Bung nao toan man (mobile-only) ----
check("co nut bung nao trong HTML", HTML.indexOf('id="brainMaxBtn"') !== -1);
check("CANARY: desktop KHONG hien nut bung (khoang nao von la ca cot giua)",
  /\.brain-max-btn \{ display: none; \}/.test(STYLE));
check("mobile moi bat nut len", /\.brain-max-btn \{ display: grid; \}/.test(MOB));
check("bung nao thi khoang nao chiem het than, chat nhuong cho",
  /body\.brain-max \.hud-center \{ flex: 1 1 auto; height: auto;/.test(MOB) &&
  /body\.brain-max \.hud-right \{ display: none; \}/.test(MOB));
check("CANARY: chip dinh kem KHONG bi giau khi bung (giau la tuong gan hut)",
  MOB.indexOf("body.brain-max .attach-bar") === -1);
check("bung/thu xong phai canh lai do thi", /refitGraph\(340\)/.test(MOBILE) &&
  /typeof g\.refit === "function"/.test(MOBILE));
check("ve man rong thi bo co bung (khong thi khung chat bien mat tren desktop)",
  /function syncBrainMax\(\)/.test(MOBILE) && /if \(!mq\.matches && document\.body\.classList\.contains\("brain-max"\)\) setBrainMax\(false\)/.test(MOBILE));
check("CANARY: gui tin khi dang bung thi tu thu lai (khong thu = go xong khong thay tra loi)",
  /document\.body\.classList\.contains\("brain-max"\)[\s\S]{0,260}getElementById\("brainMaxBtn"\)\.click\(\)/.test(APP));

// ---- 7. Cache asset phai bump, khong thi may dang mo van chay ban cu ----
["style.css", "console.css", "app.js", "graph.js", "mobile-chat.js"].forEach(f => {
  const rx = new RegExp(f.replace(".", "\\.") + "\\?v=(\\d+)");
  const m = HTML.match(rx);
  check("index.html co danh so phien ban cho " + f, !!m && Number(m[1]) > 0);
});

// ============================================================
// Thanh nhan khung chat tren dien thoai
// ============================================================
// Chu repo bao (2026-08-12, kem anh chup): "o khung chat dien thoai thi anh muon dua nut zoom
// va ten model gan sat ben trai hon".
//
// Mac dinh .panel-label la space-between: tren man rong thi dep, nhung tren dien thoai no nem
// ten model + nut phong to ra tan mep phai, cach chu HOI THOAI mot khoang trong to - mat phai
// quet ngang ca man moi doc duoc dang chay model nao.
//
// Do that trong Chromium 390px: truoc khi sua ten model bat dau o 115px, sau khi sua con 70px,
// tuc ngay canh chu HOI THOAI (ket thuc o 62px). Nut phong to van nam gon trong hang ke ca khi
// ten model dai ("Claude Code - claude-sonnet-5-20260101").
check("khung chat dien thoai: don ten model + nut phong to ve sat trai",
  /\.hud-right \.panel-label \{[^}]*justify-content: flex-start/.test(CONSOLE_CSS));
check("co khoang cach giua chu HOI THOAI va ten model",
  /\.hud-right \.panel-label \{[^}]*gap: 8px/.test(CONSOLE_CSS));
// max-width:60% mac dinh tinh theo khoi boc, ma khoi do co theo noi dung nen ten model dai la
// no day nut phong to di. Tren man hep phai neo theo BE NGANG MAN HINH.
check("CANARY: ten model dai khong day nut phong to ra ngoai",
  /\.hud-right \.panel-label \.engine-badge \{ max-width: 58vw; \}/.test(CONSOLE_CSS));

if (fails.length) {
  console.error("\nFAIL - test_nao_tren_dien_thoai: " + fails.length + " loi");
  process.exit(1);
}
console.log("\nOK - test_nao_tren_dien_thoai: tat ca pass");
