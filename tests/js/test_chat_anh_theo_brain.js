/* Anh trong tin nhan phai phan giai theo brain CUA HOI THOAI, khong phai brain dang chon.

       node tests/js/test_chat_anh_theo_brain.js

   Boi canh (bao tu nguoi dung that, 2026-07-30): "anh hoac tai lieu trong khung chat quay di
   quay lai la no mat khong hien thi nhu cu nua, no con gap tinh trang la no da gui anh va tai
   lieu roi xong no xoa tren chat di".

   Javis khong xoa anh. Duong dan anh trong tin nhan la TUONG DOI ("attachments/x.png"), khong
   mang brain. Moi lan ve lai, bo render ghep no voi brain DANG CHON tren thanh cong cu. Mo lai
   mot hoi thoai cu trong khi dang o brain khac -> URL tro sai cho -> 404 -> the <img> chay
   onerror va bi THAY bang o xam, nen nhin nhu anh bi xoa.

   Test nay khoa: co truyen brain thi phai dung brain do, khong truyen thi giu hanh vi cu, va
   brain cua luot render truoc KHONG duoc ro ri sang luot sau. */
const { mdToHtml } = require("../../dashboard/chat-render.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
function has(h, s) { return h.indexOf(s) !== -1; }
function brainCua(html) {
  const m = html.match(/brain=([^&"]*)/);
  return m ? decodeURIComponent(m[1]) : null;
}

global.currentBrainPath = () => "brains/Brain Default";

const ANH_MD = "![so do](attachments/javis-img-20260730-195818-65ea9f.png)";
const ANH_WIKI = "![[attachments/javis-img-20260730-195818-65ea9f.png]]";

// ---- 1. Khong truyen brain: giu nguyen hanh vi cu (tin moi trong brain dang chon) ----
let h = mdToHtml(ANH_MD);
check("khong truyen brain -> dung brain dang chon", brainCua(h) === "brains/Brain Default");
check("van ra the img nhu cu", has(h, "<img") && has(h, "/files/raw?"));

// ---- 2. Truyen brain cua hoi thoai: phai dung brain DO ----
h = mdToHtml(ANH_MD, "brains/My Bullet Journal");
check("truyen brain -> anh tro dung brain cua hoi thoai",
      brainCua(h) === "brains/My Bullet Journal");
check("duong dan tuong doi giu nguyen", has(h, "javis-img-20260730-195818-65ea9f.png"));

// Anh kieu wikilink ![[...]] cung phai theo brain do, khong chi rieng cu phap markdown.
h = mdToHtml(ANH_WIKI, "brains/My Bullet Journal");
check("anh wikilink cung theo brain cua hoi thoai",
      brainCua(h) === "brains/My Bullet Journal");

// Link tai lieu (khong phai anh) cung la duong dan tuong doi -> cung phai theo brain do.
h = mdToHtml("[Bao cao.pdf](exports/bao-cao.pdf)", "brains/My Bullet Journal");
check("link tai lieu cung theo brain cua hoi thoai",
      brainCua(h) === "brains/My Bullet Journal");

// ---- 3. KHONG duoc ro ri sang luot render sau (bien module phai duoc tra lai) ----
mdToHtml(ANH_MD, "brains/My Bullet Journal");
h = mdToHtml(ANH_MD);
check("CANARY: luot sau khong dinh brain cua luot truoc",
      brainCua(h) === "brains/Brain Default");

// Ro ri con nguy hiem hon khi luot giua bi nem loi -> van phai tra lai bien.
try { mdToHtml(null, "brains/My Bullet Journal"); } catch (e) { /* ke */ }
h = mdToHtml(ANH_MD);
check("CANARY: luot loi giua chung cung khong lam ket brain",
      brainCua(h) === "brains/Brain Default");

// ---- 4. Brain rong / null = coi nhu khong truyen, khong duoc ghep "brain=" rong ----
h = mdToHtml(ANH_MD, "");
check("brain rong -> roi ve brain dang chon", brainCua(h) === "brains/Brain Default");
h = mdToHtml(ANH_MD, null);
check("brain null -> roi ve brain dang chon", brainCua(h) === "brains/Brain Default");

// ---- 5. URL ngoai KHONG bi dinh brain (chi duong dan trong vault moi can) ----
h = mdToHtml("![ngoai](https://example.com/a.png)", "brains/My Bullet Journal");
check("anh URL ngoai giu nguyen, khong nhet /files/raw",
      has(h, 'src="https://example.com/a.png"') && !has(h, "files/raw"));

if (fails.length) {
  console.log("\nFAIL - test_chat_anh_theo_brain: " + fails.length + " loi: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_anh_theo_brain: tat ca pass");
