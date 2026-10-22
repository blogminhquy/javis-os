/* Thanh mục tiêu và vòng đời của /goal (0.290.0): dashboard/chat-goal.js + phần /goal của chat-lenh.js. Chạy:
 *
 *     node tests/js/test_chat_goal.js
 *
 * Chủ repo 22/10/2026: một mục tiêu thì hiện thanh để bám theo, dừng hay xoá một chạm; nhiều mục tiêu thì có số
 * ở đầu, bấm xổ danh sách. Kiểm:
 *   1. hàm thuần: đồng hồ (tạm dừng thì đứng), định dạng giờ, chọn mục tiêu đứng trên thanh, kho localStorage;
 *   2. HTML của thanh: một mục tiêu không có ô số, hai mục tiêu có, nút đúng trạng thái, escape chữ của người dùng;
 *   3. vòng đời với khung chat giả: đặt mục tiêu ở chat mới, vòng tiếp, rời chat thì CHỜ (không tắt), quay lại thì
 *      chạy tiếp, bấm Dừng thì tạm dừng, chạy tiếp, gõ chen ngang, xoá, đạt mục tiêu, trần vòng sau tải lại trang.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "../..");
let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

const G = require("../../dashboard/chat-goal.js");

// ---- 1. hàm thuần ----
check("giờ: 3h 39m 9s như thanh của Codex", G.dinhDangThoiGian((3 * 3600 + 39 * 60 + 9) * 1000) === "3h 39m 9s");
check("giờ: phút và giây", G.dinhDangThoiGian(12 * 60000 + 3000) === "12m 3s" && G.dinhDangThoiGian(45000) === "45s" && G.dinhDangThoiGian(-5) === "0s");
const g0 = G.taoMucTieu({ sid: "s1", dk: "Đối soát đơn", toiDa: 5 }, 1000);
check("mới tạo: đang chạy, vòng 1", g0.state === "running" && g0.vong === 1 && g0.sid === "s1");
check("đồng hồ chạy", G.thoiGian(g0, 61000) === 60000);
G.tamDung(g0, 61000);
check("tạm dừng thì đồng hồ đứng", g0.state === "paused" && G.thoiGian(g0, 999999) === 60000);
G.chayLai(g0, 100000);
check("chạy lại thì đồng hồ đi tiếp từ chỗ dừng", g0.state === "running" && G.thoiGian(g0, 110000) === 70000);
check("tạm dừng hai lần không cộng dồn", G.tamDung(g0, 120000) === true && G.tamDung(g0, 130000) === false && G.thoiGian(g0, 140000) === 80000);
const ga = G.taoMucTieu({ sid: "a", dk: "A" }, 10), gb = G.taoMucTieu({ sid: "b", dk: "B" }, 20);
check("thanh: mục tiêu của chat đang mở đứng trước", G.chonChinh([ga, gb], "a") === ga);
check("thanh: chat đang mở không có mục tiêu thì lấy cái mới nhất", G.chonChinh([ga, gb], "zz") === gb && G.chonChinh([], "a") === null);
check("trạng thái hiện: chạy ở chat khác là đang chờ", G.trangThaiHien(ga, "b") === "waiting" && G.trangThaiHien(ga, "a") === "running");
const raw = G.veKho([g0, ga, G.taoMucTieu({ sid: null, dk: "chưa có id" })], 140000);
const doc = G.tuKho(raw);
check("kho: mục tiêu chưa có id phiên không lưu", doc.length === 2);
check("kho: tải lại trang thì mục tiêu đang chạy thành tạm dừng, vòng sau đi luôn khi chạy tiếp",
  doc.every((x) => x.state === "paused" && x.tiepNgay === true));
check("kho: giữ vòng, phần còn thiếu, giờ đã chạy", doc[0].id === g0.id && doc[0].daChay === 80000);
check("kho: hỏng thì rỗng", G.tuKho("{x") .length === 0 && G.tuKho('{"a":1}').length === 0 && G.tuKho(null).length === 0);

// ---- 2. HTML ----
const one = G.barHtml([ga], "a", 100, {});
check("một mục tiêu: không có ô số", !one.includes("gb-count") && one.includes("gb-txt") && one.includes('data-act="del"') && one.includes('data-act="pause"'));
check("một mục tiêu: nhãn đang theo đuổi + đồng hồ", one.includes("Đang theo đuổi mục tiêu") && one.includes('data-gt="' + ga.id + '"'));
const two = G.barHtml([ga, gb], "a", 100, { xo: true });
check("hai mục tiêu: ô số 2 ở đầu, danh sách xổ đủ hai dòng", two.includes('class="gb-count"') && />2<\/button>/.test(two) && (two.match(/class="gb-item /g) || []).length === 2);
check("danh sách không xổ thì không có khung", !G.barHtml([ga, gb], "a", 100, {}).includes("gb-pop"));
G.tamDung(gb, 100);
check("tạm dừng: nút chạy tiếp thay nút tạm dừng", G.barHtml([gb], "b", 100, {}).includes('data-act="resume"'));
check("chat khác: bấm vào mục tiêu là mở chat của nó", G.barHtml([ga], "zz", 100, {}).includes('class="gb-main" data-act="open"'));
check("chi tiết: chữ đầy đủ, vòng, gợi ý mở chat khi đang chờ", (() => {
  const h = G.barHtml([ga], "zz", 100, { mo: true }); return h.includes("gb-detail") && h.includes("Vòng 1/5") && h.includes("gb-open");
})());
check("escape chữ mục tiêu", (() => { const x = G.taoMucTieu({ sid: "x", dk: "<img src=x onerror=1>" }); return !G.barHtml([x], "x", 1, { mo: true }).includes("<img"); })());
check("không có mục tiêu: rỗng", G.barHtml([], "a", 1, {}) === "");

// ---- 3. vòng đời với khung chat giả ----
const handlers = {};
global.window = { addEventListener: (ev, f) => { (handlers[ev] = handlers[ev] || []).push(f); } };
G._datLai();
window.JavisGoals = G;
let SID = null, RUNNING = {}, SENT = [], NOTES = [];
window.JavisChatApi = {
  note: (md) => NOTES.push(md),
  sid: () => SID,
  brain: () => "brain",
  dangChay: (sid) => !!RUNNING[sid],
  send: (msg, opts) => {
    if (!SID) SID = "s1";            // app.js mint id cho chat mới
    SENT.push({ sid: SID, msg, opts });
    L.daGui(SID, opts);
  },
};
window.JavisSessions = { open: (sid) => { SID = sid; fire("javis:sessions-changed"); } };
global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ block: "[MỤC TIÊU: x]\n\n" }) });
function fire(ev) { (handlers[ev] || []).forEach((f) => f()); }
const L = require("../../dashboard/chat-lenh.js");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lastNote = () => NOTES[NOTES.length - 1] || "";
// Một vòng của mục tiêu trả về: marker rồi turn_done (đúng thứ tự app.js gọi).
function xongVong(sid, marker) { L.ghiNhan(sid, marker, false); L.hetLuot(sid); }

(async () => {
  await L.chay("goal", "mọi đơn hôm nay đã đối soát");
  const g = G.theoSid("s1");
  check("đặt mục tiêu ở chat mới: tin đầu gửi kèm khối, mục tiêu nhận id của phiên", SENT.length === 1 && SENT[0].opts.goal && g && g.state === "running");
  check("đang chạy: dangCoMucTieu() của chat đang mở", L.dangCoMucTieu() === true && L.dangCoMucTieu("khac") === false);

  xongVong("s1", { done: false, left: "còn 8 đơn" });
  await sleep(350);
  check("chưa đạt: vòng 2 tự gửi", SENT.length === 2 && g.vong === 2 && g.left === "còn 8 đơn");

  // Rời sang chat khác trong lúc vòng 2 đang chạy, vòng 2 xong ở nền.
  SID = "s2"; fire("javis:sessions-changed");
  check("rời chat: mục tiêu KHÔNG tắt", G.theoSid("s1") === g);
  xongVong("s1", { done: false, left: "còn 3 đơn" });
  await sleep(350);
  check("vòng xong lúc chat đang ở nền: chưa gửi gì, mục tiêu chờ", SENT.length === 2 && g.xongLuot === true);
  check("thanh: mục tiêu ở chat khác hiện là đang chờ", G.trangThaiHien(g, SID) === "waiting");

  SID = "s1"; fire("javis:sessions-changed");
  await sleep(350);
  check("mở lại chat: chạy tiếp vòng 3, gửi vào đúng chat", SENT.length === 3 && SENT[2].sid === "s1" && g.vong === 3);

  // Bấm Dừng của khung chat giữa vòng 3.
  RUNNING.s1 = true;
  L.tamDungVi("s1");
  check("bấm Dừng: mục tiêu tạm dừng, không mất", g.state === "paused" && G.theoSid("s1") === g && /tạm dừng/i.test(lastNote()));
  check("tạm dừng: không còn tính là đang chạy (gõ chữ không phải chen ngang)", L.dangCoMucTieu() === false);
  RUNNING.s1 = false;
  xongVong("s1", { done: true });
  await sleep(350);
  check("lượt bị cắt: kết quả dở dang không dùng, mục tiêu vẫn còn", G.theoSid("s1") === g && g.tiepNgay === true && SENT.length === 3);

  L.goalAct("resume", g.id);
  await sleep(350);
  check("chạy tiếp từ thanh: vòng 4 đi luôn", g.state === "running" && SENT.length === 4 && g.vong === 4);

  // Gõ chen ngang một tin thường.
  L.chenNgang("s1");
  check("gõ chen ngang: tạm dừng kèm câu báo", g.state === "paused" && /vừa nhắn/.test(lastNote()));
  xongVong("s1", null);   // lượt trả lời tin của người dùng
  await sleep(350);
  check("lượt của tin người dùng không làm mục tiêu chết", G.theoSid("s1") === g && SENT.length === 4);

  // Tạm dừng từ thanh khi không có lượt nào chạy, rồi chạy tiếp: vòng 5 (vòng cuối).
  L.goalAct("resume", g.id);
  await sleep(350);
  check("chạy tiếp: vòng 5", SENT.length === 5 && g.vong === 5);
  L.goalAct("pause", g.id);
  xongVong("s1", { done: true });
  check("đang tạm dừng mà vòng báo đạt: báo ngay và gỡ mục tiêu", G.theoSid("s1") === null && /Đã đạt mục tiêu sau 5 vòng/.test(lastNote()));

  // Tạm dừng giữa vòng (không cắt) và vòng báo chưa đạt: giữ, chạy tiếp mới đi.
  await L.chay("goal", "gửi báo cáo tuần");
  const h = G.theoSid("s1");
  check("mục tiêu mới trong chat cũ: vào kho ngay", !!h && h.vong === 1);
  RUNNING.s1 = true;
  L.goalAct("pause", h.id);
  RUNNING.s1 = false;
  xongVong("s1", { done: false, left: "chưa gửi" });
  await sleep(350);
  const truoc = SENT.length;
  check("tạm dừng từ thanh, vòng báo chưa đạt: không tự gửi", h.tiepNgay === true && SENT.length === truoc);

  // Mục tiêu thứ hai ở chat khác: thanh có ô số.
  SID = "s9"; fire("javis:sessions-changed");
  await L.chay("goal", "dọn kho ảnh");
  check("hai chat hai mục tiêu", G.ds().length === 2 && G.barHtml(G.ds(), SID, Date.now(), {}).includes("gb-count"));
  L.goalAct("del", G.theoSid("s9").id);
  check("xoá từ thanh: còn một, có câu báo ở chat đang mở", G.ds().length === 1 && /Đã xoá mục tiêu/.test(lastNote()));

  // Chạy tiếp một mục tiêu của chat khác: mở đúng chat đó rồi đi tiếp.
  L.goalAct("resume", h.id);
  await sleep(350);
  check("chạy tiếp mục tiêu ở chat khác: mở chat của nó và gửi vòng sau vào đó", SID === "s1" && SENT[SENT.length - 1].sid === "s1" && h.vong === 2);

  // Trần vòng giữ cả khi vòng sau đi thẳng (sau tải lại trang).
  h.vong = h.toiDa; G.tamDung(h); h.tiepNgay = true;
  const n0 = SENT.length;
  L.goalAct("resume", h.id);
  await sleep(350);
  check("hết vòng sau tải lại trang: dừng và báo, không gửi vòng thứ 6", SENT.length === n0 && G.theoSid("s1") === null && /Dừng sau 5 vòng/.test(lastNote()));

  check("/goal clear khi không có mục tiêu", (await L.chay("goal", "clear"), /Hiện không có mục tiêu/.test(lastNote())));

  // ---- 4. chỗ nối trong app.js, index.html, console.js ----
  const app = fs.readFileSync(path.join(ROOT, "dashboard/app.js"), "utf8");
  const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
  const con = fs.readFileSync(path.join(ROOT, "dashboard/console.js"), "utf8");
  check("app.js: nút Dừng tạm dừng mục tiêu chứ không xoá", app.includes("window.JavisLenh.tamDungVi(sid)") && !app.includes("window.JavisLenh.dungMucTieu(); } catch (e) {}   // Dừng"));
  check("app.js: turn_done của chat nền cũng báo cho /goal", app.includes("if (window.JavisLenh) window.JavisLenh.hetLuot(sid);") && !app.includes("isActive && window.JavisLenh) window.JavisLenh.hetLuot"));
  check("index.html: thanh mục tiêu ẩn sẵn, nạp chat-goal.js trước chat-lenh.js",
    /id="goalBar"[^>]*hidden/.test(html) && html.indexOf("chat-goal.js") > 0 && html.indexOf("chat-goal.js") < html.indexOf("chat-lenh.js"));
  check("console.js: thanh đi theo khung chat sang trang Trò chuyện", /CHAT_NODE_IDS = \[[^\]]*"goalBar"/.test(con));
  for (const f of ["dashboard/chat-goal.js", "tests/js/test_chat_goal.js"]) {
    const src = fs.readFileSync(path.join(ROOT, f), "utf8");
    check("không có gạch dài trong " + f, !src.includes(String.fromCharCode(0x2014)) && !src.includes(String.fromCharCode(0x2013)));
  }

  if (fails.length) { console.log("\nFAIL - test_chat_goal: " + fails.length + " loi"); process.exit(1); }
  console.log("\nOK - test_chat_goal: tat ca pass");
})().catch((e) => { console.log("FAIL exception " + (e && e.stack)); process.exit(1); });
