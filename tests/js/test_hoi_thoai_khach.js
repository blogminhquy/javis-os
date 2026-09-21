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
// Phia may chu: hai dau kia (ten brain cua bot, va viec go tai khoan khoi bot) phai co that o
// day chu khong chi la mot chuoi trong giao dien.
const SRV = fs.readFileSync(path.join(ROOT, "server", "routes", "channels.py"), "utf8");
const ACC = fs.readFileSync(path.join(ROOT, "server", "channel_accounts.py"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
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
// ------------------------------------------------------------------ the tai khoan kenh
// Chu repo bao (2026-09-21) khi nhin tab Kenh: "dang bi loi tran ky tu, va dang khong co phan
// xoa kenh nua". Ca hai deu la loi hong lang le.
//
// 1. Cau loi cua MCP la mot cuc JSON khong co lay mot dau cach. De lam text tran trong mot
//    flex container thi no thanh mot flex item VO DANH - CSS khong voi toi duoc de cho phep
//    ngat dong - nen chu tran ra de sang the ben canh.
check("cau loi duoc boc trong <span> chu khong de lam text tran",
      /class="ht-acc-loi" title="' \+ esc\(a\.loi\)/.test(SRC) &&
      /'<span>' \+ esc\(String\(a\.loi\)\.slice\(0, 200\)\) \+ '<\/span>/.test(SRC));
check("CSS cho phep ngat dong giua chu trong cau loi",
      /\.ht-acc-loi span \{[^}]*min-width: 0/.test(CSS) &&
      /\.ht-acc-loi span \{[^}]*overflow-wrap: anywhere/.test(CSS));
check("the tai khoan cung chan tran (ten bot hay id nen tang dai)",
      /\.ht-acc \{[^}]*overflow-wrap: anywhere/.test(CSS));

// 2. Server tu choi xoa tai khoan dang co bot truc; ban truoc dich cau tu choi do thanh "an
//    nut di", nen chu repo nhin the nao cung khong thay cho xoa va khong co gi noi vi sao.
check("CANARY: nut Xoa KHONG con bi an theo xoa_duoc",
      !/a\.xoa_duoc \? '<button[^']*ht-acc-xoa/.test(SRC) && SRC.includes("ht-acc-xoa"));
check("moi the kenh bot deu co nut Xoa",
      /a\.kind === "bot"\s*\n?\s*\? '<button type="button" class="s-btn-ghost ht-acc-xoa">/.test(SRC));
// 0.62.4: tai khoan bot THUOC MOT BRAIN (truong `brain` trong kho tai khoan), va tab nay loc
// theo brain dang mo. Truoc do tai khoan la toan cuc nen tab tron het moi brain, nhin khong
// biet cai nao cua minh (chu repo bao 21/09). Bon thu phai giu:
check("kho tai khoan co truong brain rieng, khong suy tu bot",
      SRV.includes('"brain": a.get("brain") or ""') &&
      ACC.includes('def list_accounts(channel: str = "", brain: str = "")'));
check("tai khoan CHUA gan brain hien o MOI brain (khong co token nao tang hinh)",
      /_clean_brain\(a\.get\("brain"\)\) not in \(""/.test(ACC));
check("tab goi API kem brain dang mo",
      /api\("\/channels\/accounts\?brain=" \+ encodeURIComponent\(brain\(\)\)/.test(SRC));
check("co cong tac xem MOI brain, de tim lai tai khoan gan nham cho",
      /_tkMoiBrain \? "&tat_ca=1" : ""/.test(SRC) &&
      SRC.includes('window.t("ht.tk_xem_moi_brain")') &&
      SRC.includes('window.t("ht.tk_chi_brain_nay")'));
check("hang loc noi ro dang xem brain nao (danh sach ngan di phai co ly do)",
      SRC.includes('window.t("ht.tk_loc_brain", { brain: tenBrain(brain()) })') &&
      VI["ht.tk_loc_brain"].includes("{brain}"));
// Khoa brain that la "brain" hoac mot duong dan tuyet doi. Dan nguyen no len giao dien thi ra
// "brain brain" hoac mot dong path dai ngoang - da thay tan mat luc chup man hinh 21/09.
check("nhan brain hien TEN doc duoc, khong phai khoa tho",
      /function tenBrain\(v\)/.test(SRC) &&
      /o\.dataset && o\.dataset\.brainName/.test(SRC) &&
      /replace\(\/\\s\*·\\s\*\\d\+\\\+\?\$\//.test(SRC));
// Nhan brain tren the chi hien khi CO CHUYEN de noi. Loc theo brain roi ma the nao cung dan
// ten brain dang mo thi chi la tieng on.
check("the noi brain khi: xem moi brain / chua gan chu / bot truc o brain khac",
      SRC.includes('window.t("ht.tk_chua_brain")') &&
      SRC.includes('window.t("ht.tk_bot_brain_khac", { brain: tenBrain(botBr) })') &&
      /_tkMoiBrain \|\| brTK !== brNay/.test(SRC) &&
      SRV.includes('"bot_brain": (b or {}).get("brain") or ""'));
check("CANARY: khong con dan brain vo dieu kien vao sau ten bot",
      !SRC.includes('window.t("ht.o_brain", { brain: a.bot_brain })'));
check("doi duoc brain cua tai khoan (loi thoat khi them nham cho)",
      SRC.includes('window.t("ht.lb_brain_tk")') && /than\.brain = oBr\.value/.test(SRC) &&
      ACC.includes('"brain"') && /"meta", "brain"\)/.test(ACC));
check("bam Xoa thi go khoi bot roi xoa NGAY, trong mot lan hoi",
      /window\.t\(a\.bot_mot_tk \? "ht\.xoa_go_bot_cuoi" : "ht\.xoa_go_bot"/.test(SRC) &&
      /go_khoi_bot: a\.bot_id \? "1" : ""/.test(SRC));
check("cau hoi noi du ten bot va brain cua no",
      ["ht.xoa_go_bot", "ht.xoa_go_bot_cuoi"].every((k) =>
        VI[k].includes("{bot}") && VI[k].includes("{brain}") && VI[k].includes("{ten}")));
// Go tai khoan CUOI CUNG la bot het token va khong bat len duoc nua. Phai hoi khac di, va
// phai noi ra khi server da tat con bot do.
check("tai khoan cuoi cung cua bot thi hoi bang mot cau RIENG",
      VI["ht.xoa_go_bot_cuoi"] !== VI["ht.xoa_go_bot"] &&
      /DUY NH[ẤA]T/.test(VI["ht.xoa_go_bot_cuoi"]));
check("server tat bot thi giao dien noi ra",
      /if \(r && r\.bot_tat\) alert\(window\.t\("ht\.da_tat_bot"/.test(SRC) &&
      SRV.includes('bot_tat = b.get("name") or ""'));
// CANARY: duong cut cu. Tab Chatbot chi nap bot cua brain dang mo, nen nhay sang do de sua
// mot con bot o brain khac luon ket thuc bang "doi brain roi thu lai" ma khong noi brain nao.
// Soi DAY DISPATCH va DAY NGHE chu khong soi ten su kien tran: chu thich giai thich vi sao
// bo duong nay co nhac lai chinh cai ten do, va soi ten tran thi canary do vi cau giai thich.
check("CANARY: khong con nhay sang tab Chatbot de go tai khoan",
      !/dispatchEvent\(new CustomEvent\("javis:chatbot-edit"/.test(SRC) &&
      !/addEventListener\("javis:chatbot-edit"/.test(CB));
check("CANARY: cau bao tac cua duong do cung duoc don khoi tu dien",
      !("cb.khong_thay_bot" in VI));
// Zalo ca nhan la mot KET NOI ben trang Ket noi, khong xoa o day duoc. The van phai chi duong
// chu khong duoc cam.
check("the kenh khong xoa duoc o day thi chi duong sang trang Ket noi",
      SRC.includes("ht-acc-ket-noi") && SRC.includes('window.t("ht.mo_ket_noi")') &&
      /kn\.onclick = function \(\) \{ try \{ window\.JavisNav\.go\("mcp"\)/.test(SRC));

// 3. Nut cuoi hang kenh bi bop lai cho vua cho con thua, chu gay lam hai dong ("Mo / Ket noi").
check("nut o hang kenh giu nguyen be ngang cua no",
      /\.ht-src > button \{[^}]*flex: none/.test(CSS) &&
      /\.ht-src > button \{[^}]*white-space: nowrap/.test(CSS));

check("khong dung ky tu em dash", !SRC.includes("\u2014") && !CB.includes("\u2014"));

if (fails.length) {
  console.log("\nDO " + fails.length + " muc: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_hoi_thoai_khach: tat ca pass");
