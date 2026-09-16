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
// KHACH BAO 16/09: mau cu nhoi cau cua nguoi dung vao GIUA mot cau cua may ("Hay dung skill
// `X` voi yeu cau: <cau cua ho>. Neu khong co skill ten nay thi..."), va server LUU nguyen
// chuoi do lam tin cua NGUOI DUNG - mo lai hoi thoai la doc duoc mot cau minh chua tung go,
// kem mot cau cuoi tu xuat hien. Nay loi dan la mot KHOI NGU CANH dat TRUOC cau do, dung hinh
// dang ma app.js (chuNguoiGo) biet go ra truoc khi ve bong bong.
check("invoke: cau nguoi dung GIU NGUYEN, khong bi nhoi vao giua cau may",
  S.buildSkillInvocation("notes", "mua sua").endsWith("]\n\nmua sua"));
check("invoke: mo bang khoi [SKILL: <ten>",
  S.buildSkillInvocation("notes", "mua sua").startsWith("[SKILL: notes\n"));
// Khoi phai ket thuc bang "]\n\n" moi dung cua ma chuNguoiGo nhan ra.
check("invoke: dung hinh dang khoi ngu canh (ket bang ]\\n\\n)",
  S.buildSkillInvocation("notes", "mua sua").indexOf("]\n\n") > 0);
check("invoke: khong arg -> than la chinh lenh da go (bong bong khong rong)",
  S.buildSkillInvocation("notes", "").endsWith("]\n\n/notes"));
// Cau "neu khong co skill ten nay..." CHI xuat hien khi ten skill KHONG co that. Skill co
// that ma van them cau do la tu them chu vao tin cua nguoi dung khong vi ly do gi.
S.setKnownSkills([{ slug: "notes" }]);
check("invoke: skill CO THAT -> KHONG them cau du phong",
  S.buildSkillInvocation("notes", "mua sua").indexOf("Brain không có skill") === -1);
check("invoke: skill LA -> co cau du phong",
  S.buildSkillInvocation("khong-co-that", "x").indexOf("Brain không có skill") !== -1);
check("invoke: giua cau -> loi dan nhac LAM DUNG YEU CAU BEN DUOI",
  S.buildSkillInvocation("notes", "x", true).indexOf("làm đúng yêu cầu bên dưới") !== -1);
S.setKnownSkills([]);

// ---- route ----
check("route: passthrough", S.route("chao").type === "passthrough");
check("route: session new", (() => { const r = S.route("/new"); return r.type === "session" && r.cmd === "new"; })());
check("route: skill notes co message", (() => { const r = S.route("/notes x"); return r.type === "skill" && r.cmd === "notes" && r.message.indexOf("[SKILL: notes") !== -1 && r.message.endsWith("\n\nx"); })());

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
// Truoc 0.59.15 token bi XOA hẳn khoi cau roi noi hai dau lai, nen "Skill /viet-bai-x se la
// skill chinh" thanh "Skill se la skill chinh" - mat mot tu, cau doc thanh vo nghia. Khach goi
// dung ten: "chu no bi dich chay di linh tinh". Nay chi bo dau "/", GIU ten lai.
check("giua cau: chu hai ben deu vao arg, GIU nguyen ten skill", (() => {
  const r = S.route("viet cho anh /notes ve cuoc hop");
  return r.type === "skill" && r.cmd === "notes"
    && r.message.indexOf("viet cho anh notes ve cuoc hop") !== -1;
})());
check("giua cau: cau cua nguoi dung khong bi cat mat tu nao", (() => {
  S.setKnownSkills([{ slug: "viet-bai-trang-chu-igaming" }]);
  const cau = "vay hay tao cho toi 1 workflow rieng. Skill /viet-bai-trang-chu-igaming se la skill chinh.";
  const r = S.route(cau);
  S.setKnownSkills([{ slug: "notes" }, { slug: "viet-email" }]);
  return r.type === "skill"
    && r.message.indexOf("Skill viet-bai-trang-chu-igaming se la skill chinh.") !== -1;
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


const agents = [{slug: "writer", name: "Writer"}];
const workflows = [{slug: "writer", name: "Workflow", status: "active"}, {slug: "draft", status: "draft"}];
S.setKnownPartners(agents, workflows);
check("agent command routes to agent", S.route("/agent-writer hello").type === "agent" && S.route("/agent-writer hello").message === "hello");
check("workflow collision is distinct", S.route("/workflow-writer hello").type === "workflow");
// Duong CONG SU van BO HAN token: "/agent-writer" la mot dia chi, gui kem ten agent vao tin
// nhan cho chinh agent do la chu thua. Chi duong SKILL moi giu ten lai (xem khoi giua cau).
check("partner in middle preserves request", S.route("hello /agent-writer").message === "hello");
check("draft workflows hidden", !S.buildMenu([], agents, workflows).some(x => x.cmd === "workflow-draft"));
check("skill remains a skill", S.route("/writer hello").type === "skill");

const searchable = [{cmd: "agent-viet", name: "Người viết", desc: "Nội dung bán hàng", group: "Marketing"}, {cmd: "workflow-ban", name: "Bán hàng", desc: ""}];
check("Vietnamese without accents", S.filterItems(searchable, "nguoi viet")[0] === searchable[0]);
check("multiple words across fields", S.filterItems(searchable, "marketing noi dung")[0] === searchable[0]);
check("exact name outranks description", S.filterItems(searchable, "ban hang")[0] === searchable[1]);
check("all words required", S.filterItems(searchable, "marketing unknown").length === 0);
check("Vietnamese slash query opens menu", S.tokenAtCaret("/viết", 5).query === "viết");
if (fails.length) { console.log("\nFAIL - test_chat_slash: " + fails.length + " loi"); process.exit(1); }
console.log("\nOK - test_chat_slash: tat ca pass");
