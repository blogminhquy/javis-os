// Trang Hoi thoai (hop thu khach, Chatbot V2): canary cau truc cua dashboard/conversations.js.
//
//     node tests/js/test_hoi_thoai_khach.js
//
// Vi sao co file nay
// ------------------
// Trang nay la mot module uy quyen giong chatbots.js: console.js chi goi
// window.JavisConversations.render(el). Mat ten global, hoac quen dung nhip tu lam moi khi
// roi trang, thi trang trang trong hoac de lai mot vong goi mang chay mai - hai loi im lang,
// khong test nao khac thay. Chua co DOM gia cho ca trang, nen test nay soi ma nguon.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "conversations.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const SCSS = fs.readFileSync(path.join(ROOT, "dashboard", "style.css"), "utf8");
const CB = fs.readFileSync(path.join(ROOT, "dashboard", "chatbots.js"), "utf8");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Kiem Y NGHIA (co du cua cho module ngoai goi), khong khoa cung hinh dang object: moi lan
// them mot cua la test do oan.
check("xuat global JavisConversations voi render, mo, chonTab va themTaiKhoan",
      /window\.JavisConversations\s*=\s*\{/.test(SRC) &&
      /\brender:\s*render\b/.test(SRC) && /\bmo:\s*moTu\b/.test(SRC) &&
      /\bchonTab:\s*chonTab\b/.test(SRC) && /\bthemTaiKhoan:\s*moThemTK\b/.test(SRC));

// ------------------------------------------------------------------ MOT form dan token duy nhat
// 0.61.1: form tao bot khong con form dan token rieng. Truoc do hai form song song lam cach
// lay token cua tung kenh bi nhan doi, va them mot kenh moi la phai sua ca hai noi - dung loai
// loi hong lang le ma sinh ra sau ba thang moi thay.
check("chi conversations.js biet cach dan token, chatbots.js khong con form token",
      SRC.includes('id="htToken"') && !CB.includes('id="cbToken"') &&
      !CB.includes("/chatbots/verify-token"));
check("o token la type=password va KHONG do token cu vao lai",
      /id="htToken" type="password"/.test(SRC) && !/id="htToken"[^>]*value="/.test(SRC));
check("co nut kiem token truoc khi luu, hoi dung nen tang theo kenh dang chon",
      SRC.includes("/channels/verify-token") && /body: fd\(\{ channel: chon, token: t \}\)/.test(SRC));
check("doi kenh thi BO token da kiem (no la danh tinh o nen tang KIA)",
      /function apKenh\(id\) \{\s*\n\s*chon = id; uname = ""; meta = \{\};/.test(SRC));
check("doi kenh la doi theo ca form (nhan token, cho lay token)",
      SRC.includes("htTokenLabel") && SRC.includes("htTokenNote") && SRC.includes("k.lay_token"));
check("moi kenh noi ro uu va nhuoc ngay tren nut, cau chu lay tu server",
      /esc\(k\.tom_tat \|\| ""\)/.test(SRC) && !/KENH_TOM\s*=/.test(SRC));
check("chon kenh bang the bam co logo, khong phai <select> tron",
      /class="cb-kenh"/.test(SRC) && /class="cb-kenh-o/.test(SRC) && SRC.includes("cb-kenh-logo"));
// Luoi hai cot bop cau tom tat cua moi kenh thanh nam sau dong chu hep tren dien thoai, va no
// khong mo rong duoc: kenh thu tu, thu nam la man hinh dai them chung ay lan.
check("danh sach kenh xep DOC mot hang mot kenh, khong phai luoi hai cot",
      /\.cb-kenh \{[^}]*flex-direction: column/.test(SCSS) &&
      !/\.cb-kenh \{[^}]*grid-template-columns: 1fr 1fr/.test(SCSS));
check("form tao bot mo duoc dung form nay, va nhan lai tai khoan vua noi",
      CB.includes("JavisConversations.themTaiKhoan") && CB.includes("onXong") &&
      /opts\.onXong\(moi\)/.test(SRC));
check("nhip tu lam moi tu dung khi node roi khoi DOM",
      SRC.includes("document.body.contains(_host)") && SRC.includes("clearInterval(_timer)"));
check("nhip im khi tab an hoac dang mo hop thoai Kenh",
      SRC.includes("document.hidden") && SRC.includes('querySelector(".ht-modal")'));
check("lan nap ngam KHONG xoa danh sach dang hien (giu man hinh cu khi mang hong mot nhip)",
      /if \(!im\) box\.innerHTML/.test(SRC) && SRC.includes("vet === _dauVet"));
check("doc mot hoi thoai thi danh dau da doc",
      SRC.includes('"/read", { method: "POST" }'));
check("tiep quan / tra lai AI goi dung duong mode",
      SRC.includes('"/mode", { method: "POST", body: fd({ mode: mode })'));
// 0.61.0: cong tac ghi di qua API tai khoan kenh CHUNG (khong con duong rieng cho Zalo).
check("bat/tat ghi theo tung tai khoan kenh qua API chung /channels/accounts",
      SRC.includes("/channels/accounts/") && SRC.includes('"/watch"') && !SRC.includes("/conversations/zalo/"));
check("khong doan gi theo id kenh: logo va nhan lay tu danh sach server (khong con nhanh zalo_personal)",
      !SRC.includes('"zalo_personal"') && SRC.includes("k.logo"));
check("tra loi khach tu Hop thu qua /reply, chi khi kenh co nang luc",
      SRC.includes('"/reply", { method: "POST", body: fd({ text: txt })') &&
      SRC.includes('nangLuc(c.channel, "tra_loi_tu_javis")'));
check("ba tab Hop thu | Kenh | Chatbot, tab Chatbot uy quyen cho chatbots.js",
      /TABS = \["inbox", "kenh", "chatbot"\]/.test(SRC) && SRC.includes("window.JavisChatbots.render"));
check("dien thoai: mo hoi thoai la them lop thread-on, co nut quay lai",
      SRC.includes('classList.add("thread-on")') && SRC.includes(".ht-back") &&
      /\.ht-wrap\.thread-on \.ht-list \{ display: none; \}/.test(CSS) &&
      /\.ht-back \{ display: inline-flex; \}/.test(CSS));
check("chu chinh len 16px tren man nhỏ (chuan doc cua chu repo)",
      /@media \(max-width: 900px\) \{[\s\S]*\.ht-bubble[^}]*font-size: 16px/.test(CSS));
check("cau bot ve qua mdToHtml (co loc), tin khach chi escape",
      SRC.includes("window.mdToHtml(t.text") && SRC.includes("than = esc(t.text"));
check("the bot o trang Chatbot co nut mo hop thu loc theo bot",
      CB.includes("JavisConversations.mo({ bot_id: b.id })"));
check("khong dung ky tu em dash", !SRC.includes("\u2014") && !CB.includes("\u2014"));

if (fails.length) {
  console.log("\nDO " + fails.length + " muc: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_hoi_thoai_khach: tat ca pass");
