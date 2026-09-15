/* Trang Cộng sự (dashboard/workspace.js): sắp xếp, chọn phiên, tiến độ quy trình.

       node tests/js/test_workspace.js

   Chạy dưới node với DOM giả tối thiểu: workspace.js phơi phần thuần qua window.JavisWorkspace. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");

global.window = { t: (k) => k, ic: () => "", addEventListener() {}, matchMedia: () => ({ matches: false }) };
global.document = { getElementById: () => null, createElement: () => ({ classList: { add() {}, remove() {} }, appendChild() {} }), body: { classList: { add() {}, remove() {} } } };
global.localStorage = { getItem: () => null, setItem() {} };
require(path.join(root, "dashboard", "workspace.js"));
const W = window.JavisWorkspace;

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// Sắp xếp: mốc gần nhất lên đầu, chưa có mốc xếp sau theo tên
const wfs = [{ slug: "a", name: "Bản tin", last_run_at: 0 }, { slug: "b", name: "Viết bài", last_run_at: 50 }, { slug: "c", name: "Ads", last_run_at: 99 }, { slug: "d", name: "Zalo", last_run_at: 0 }];
check("xep quy trinh theo lan chay gan nhat", W.sapXep(wfs, "last_run_at").map(x => x.slug).join(",") === "c,b,a,d");
const ags = [{ slug: "x", name: "Người viết", last_chat_at: 0 }, { slug: "y", name: "Javis", last_chat_at: 3 }];
check("xep tro ly theo lan chat gan nhat", W.sapXep(ags, "last_chat_at").map(x => x.slug).join(",") === "y,x");

// Lọc: tìm không dấu + nhóm
const ds = [{ slug: "a", name: "Người viết", role: "viết", group: "Marketing" }, { slug: "b", name: "Kế toán", role: "sổ sách", group: "Finance" }];
check("loc theo chu khong dau", W.loc(ds, "nguoi viet", "").map(x => x.slug).join() === "a");
check("loc theo nhom", W.loc(ds, "", "Finance").map(x => x.slug).join() === "b");

// Tiến độ quy trình từ wf_event
const st = W.tienDoMoi(3);
W.apDung(st, { type: "step_start", i: 0, agent: "A" });
check("step_start -> buoc 0 dang lam", st.buoc[0].trang_thai === "dang" && st.hien_tai === 0);
W.apDung(st, { type: "step_done", i: 0 });
W.apDung(st, { type: "step_start", i: 1, agent: "B" });
check("step_done -> xong, sang buoc 1", st.buoc[0].trang_thai === "xong" && st.buoc[1].trang_thai === "dang");
W.apDung(st, { type: "wait_user", node: "dang", task_id: "tk", code: "AB" });
check("wait_user -> cho duyet + giu code", st.cho_duyet && st.cho_duyet.code === "AB" && st.trang_thai === "cho");
W.apDung(st, { type: "done" });
check("done -> xong het", st.trang_thai === "xong" && st.buoc.every(b => b.trang_thai === "xong"));
const st2 = W.tienDoMoi(2);
W.apDung(st2, { type: "step_start", i: 0, agent: "A" });
W.apDung(st2, { type: "error", content: "chết" });
check("error -> buoc dang lam thanh loi", st2.trang_thai === "loi" && st2.buoc[0].trang_thai === "loi");
check("phan tram", W.phanTram(W.tienDoMoi(4)) === 0 && W.phanTram(st) === 100);

// Dây nối
const app = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
check("app.js chuyen wf_event sang JavisWorkspace", /data\.type === "wf_event"/.test(app) && /JavisWorkspace\.onWfEvent\(/.test(app));
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");
// Dò theo ĐƯỜNG DẪN "/static/<ten>.js" chứ không theo tên trần: tên trần còn nằm trong hàng
// chục dòng chú thích ở nửa trên file, nên so vị trí kiểu đó là so nhầm với một chú thích.
const viTri = (ten) => html.indexOf('/static/' + ten + '.js');
check("index.html nap workspace.js sau studio.js, truoc console.js",
  viTri("studio") > 0 && viTri("studio") < viTri("workspace") && viTri("workspace") < viTri("console"));
const con = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
check("console.js co renderWorkspace muon khung chat", /function renderWorkspace\(el\)/.test(con) && /JavisWorkspace\.render\(el, \{ borrow: _borrowChatNodes \}\)/.test(con));
const studio = fs.readFileSync(path.join(root, "dashboard", "studio.js"), "utf8");
check("studio.js editAgent nhan host + onSaved", /function editAgent\(a, opts\)/.test(studio) && /opts\.host/.test(studio) && /opts\.onSaved/.test(studio));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - workspace");
