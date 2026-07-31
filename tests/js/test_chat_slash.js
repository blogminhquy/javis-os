/* Test logic thuan cua khung lenh /. Chay: node dashboard/test_chat_slash.js
   KHONG can trinh duyet. */
const S = require("../../dashboard/chat-slash.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- parseSlash ----
check("parse: /notes hello", (() => { const r = S.parseSlash("/notes hello"); return r && r.cmd === "notes" && r.arg === "hello"; })());
check("parse: /notes tron -> arg rong", (() => { const r = S.parseSlash("/notes"); return r && r.cmd === "notes" && r.arg === ""; })());
check("parse: chu HOA -> thuong", (() => { const r = S.parseSlash("/Notes X"); return r && r.cmd === "notes" && r.arg === "X"; })());
check("parse: dau / tron -> null", S.parseSlash("/") === null);
check("parse: khong phai lenh -> null", S.parseSlash("chao Javis") === null);
check("parse: khoang trang dau -> null", S.parseSlash("  /notes") === null);
check("parse: arg nhieu dong giu nguyen", (() => { const r = S.parseSlash("/notes dong1\ndong2"); return r && r.arg === "dong1\ndong2"; })());

// ---- classify ----
check("classify: new = session", S.classify("new") === "session");
check("classify: stop = session", S.classify("stop") === "session");
check("classify: notes = skill", S.classify("notes") === "skill");

// ---- buildSkillInvocation (khop mau Telegram) ----
check("invoke: co arg", S.buildSkillInvocation("notes", "mua sua") ===
  "Hãy dùng skill `notes` với yêu cầu: mua sua. Nếu không có skill tên này thì cứ xử lý yêu cầu của tôi bình thường.");
check("invoke: khong arg", S.buildSkillInvocation("notes", "") ===
  "Hãy dùng skill `notes`. Nếu không có skill tên này thì cứ xử lý yêu cầu của tôi bình thường.");

// ---- route ----
check("route: passthrough", S.route("chao").type === "passthrough");
check("route: session new", (() => { const r = S.route("/new"); return r.type === "session" && r.cmd === "new"; })());
check("route: skill notes co message", (() => { const r = S.route("/notes x"); return r.type === "skill" && r.cmd === "notes" && r.message.indexOf("skill `notes`") !== -1 && r.message.indexOf("x") !== -1; })());

// ---- buildMenu + filterItems ----
const menu = S.buildMenu([
  { slug: "notes", name: "Notes", description: "Luu note" },
  { slug: "ingest-source", name: "Ingest Source", description: "Tieu hoa source" },
]);
check("menu: co lenh phien new", menu.some(i => i.kind === "session" && i.cmd === "new"));
check("menu: co skill notes", menu.some(i => i.kind === "skill" && i.cmd === "notes"));
check("filter: 'no' ra notes", (() => { const r = S.filterItems(menu, "no"); return r.length >= 1 && r[0].cmd === "notes"; })());
check("filter: 'ingest' ra ingest-source", (() => { const r = S.filterItems(menu, "ingest"); return r.some(i => i.cmd === "ingest-source"); })());
check("filter: rong tra ve tat ca", S.filterItems(menu, "").length === menu.length);


// ---- Lenh GIUA cau (0.9.290) ----
// Truoc day route() va menu deu neo vao dau chuoi, nen go "... /viet-email" o cuoi cau la
// khong an gi ca - dung loi chu repo bao. Gio nhan duoc, nhung CHI khi slug co that.
S.setKnownSkills([{ slug: "notes" }, { slug: "viet-email" }]);

check("giua cau: nhan skill co that", (() => {
  const r = S.route("test su dung skill giua khung chat /viet-email");
  return r.type === "skill" && r.cmd === "viet-email";
})());
check("giua cau: phan chu con lai thanh arg", (() => {
  const r = S.route("test su dung skill giua khung chat /viet-email");
  return r.message.indexOf("test su dung skill giua khung chat") !== -1;
})());
check("giua cau: chu hai ben deu vao arg", (() => {
  const r = S.route("viet cho anh /notes ve cuoc hop");
  return r.type === "skill" && r.cmd === "notes"
    && r.message.indexOf("viet cho anh ve cuoc hop") !== -1;
})());
check("giua cau: slug KHONG co that -> chat thuong", S.route("mo giup /khong-co-that di").type === "passthrough");
check("giua cau: URL khong bi bat nham", S.route("xem https://vd.com/notes nhe").type === "passthrough");
check("giua cau: duong dan tuyet doi khong bi bat nham", S.route("mo /home/user/notes ho anh").type === "passthrough");
check("giua cau: phan so khong bi bat nham", S.route("con 3/4 cai banh").type === "passthrough");
check("giua cau: lenh phien KHONG chay (hay /reset lai)", S.route("hay /reset lai giup anh").type === "passthrough");
check("dau o: lenh phien van chay nhu cu", S.route("/reset").type === "session");
check("giua cau: nhieu lenh -> lay cai CUOI (y dinh moi nhat)", (() => {
  const r = S.route("/notes roi /viet-email");
  return r.type === "skill" && r.cmd === "notes";   // dau chuoi van uu tien tuyet doi
})());
check("giua cau: lay lan xuat hien cuoi khi khong o dau chuoi", (() => {
  const r = S.route("lam on /notes roi /viet-email");
  return r.type === "skill" && r.cmd === "viet-email";
})());

// ---- tokenAtCaret: menu bat len o dau con tro ----
check("token: dau o nhap", (() => { const t = S.tokenAtCaret("/no", 3); return t && t.query === "no" && t.atHead === true; })());
check("token: giua cau sau khoang trang", (() => { const t = S.tokenAtCaret("chao anh /no", 12); return t && t.query === "no" && t.atHead === false; })());
check("token: vua go moi dau '/' o giua cau", (() => { const t = S.tokenAtCaret("chao anh /", 10); return t && t.query === "" && t.atHead === false; })());
check("token: dinh lien chu thi KHONG mo menu", S.tokenAtCaret("abc/no", 6) === null);
check("token: con tro dung truoc token thi khong tinh", S.tokenAtCaret("chao /notes", 5) === null);
check("token: chi tinh phan TRUOC con tro", (() => { const t = S.tokenAtCaret("/notes them chu", 3); return t && t.query === "no"; })());

if (fails.length) { console.log("\nFAIL - test_chat_slash: " + fails.length + " loi"); process.exit(1); }
console.log("\nOK - test_chat_slash: tat ca pass");
