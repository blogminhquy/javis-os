// T0 nhóm chat team (spec 2026-10-13-team-chat-design mục 10): công tắc Cộng hưởng trên từng dòng trợ lý.
//
//     python tests/run.py --js team_t0_toggle -v
//
// Hàm thuần của resonance-agent.js chạy dưới node: trạng thái bằng chữ, công tắc trên dòng, câu hỏi lại khi tắt.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const RA = require(path.join(ROOT, "dashboard", "resonance-agent.js"));
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

const on = { slug: "viet-bai", name: "Viết <b>bài</b>", agent_key: "ag_1", enabled: true, status: "active", goals_open: 2 };
const off = Object.assign({}, on, { enabled: false, goals_open: 0 });

let h = RA.rowToggleHtml(on, {});
// 0.142.0: nhãn hiện "Auto" + công tắc nhỏ trong thẻ; trạng thái bằng chữ nằm trong aria-label và tooltip.
check("bật: trạng thái Bật bằng chữ (aria, tooltip), ô đã chọn, màu cam", h.includes(vi["resonance.t0_state_on"])
      && /ws-rs-toggle"[^>]* checked/.test(h) && /aria-checked="true"/.test(h) && h.includes("ws-auto is-on")
      && h.includes(">" + vi["resonance.auto_label"] + "<"), h);
h = RA.rowToggleHtml(off, {});
check("tắt: trạng thái Tắt bằng chữ, ô chưa chọn, không màu cam", h.includes(vi["resonance.t0_state_off"])
      && !/ws-rs-toggle"[^>]* checked/.test(h) && /aria-checked="false"/.test(h) && !h.includes("is-on"), h);
h = RA.rowToggleHtml({ slug: "moi", status: "unregistered", enabled: false }, {});
check("chưa đăng ký coi như Tắt", h.includes(vi["resonance.t0_state_off"]), h);
h = RA.rowToggleHtml(Object.assign({}, on, { status: "missing" }), {});
check("missing: chữ Cần xác nhận, không có ô bật, có nút mở bảng", h.includes(vi["resonance.t0_state_missing"])
      && !h.includes("ws-rs-toggle") && h.includes("ws-rs-confirm"), h);
h = RA.rowToggleHtml(Object.assign({}, on, { status: "retired" }), {});
check("retired: chữ Đã nghỉ, không có ô bật", h.includes(vi["resonance.t0_state_retired"]) && !h.includes("ws-rs-toggle"), h);
h = RA.rowToggleHtml(on, { saving: true });
check("đang lưu: ô bị khoá, chữ Đang lưu", /ws-rs-toggle"[^>]*disabled/.test(h) && h.includes(vi["resonance.t0_saving"]), h);
check("không có dữ liệu: không vẽ công tắc", RA.rowToggleHtml(undefined, {}) === "");
check("nhãn aria và title không chèn HTML", !RA.rowToggleHtml(on, {}).includes("<b>"));
check("trạng thái bằng chữ, không chỉ màu", RA.stateKey(on) === "resonance.t0_state_on"
      && RA.stateKey(off) === "resonance.t0_state_off" && RA.stateKey({ status: "missing" }) === "resonance.t0_state_missing");
check("tắt khi có mục tiêu mở: hỏi kèm số mục tiêu", RA.offConfirmText(on).includes("2"), RA.offConfirmText(on));
check("tắt khi không có mục tiêu: không hỏi", RA.offConfirmText(off) === "");
check("bảng bên phải không còn công tắc riêng", !RA.panelHtml(on, "ready", []).includes("rsa-toggle")
      && RA.panelHtml(on, "ready", []).includes(vi["resonance.t0_state_on"])
      && RA.panelHtml(on, "ready", []).includes(vi["resonance.t0_where"]));
const st = RA.settingsHtml({ agents: [on, off, Object.assign({}, on, { slug: "mat", status: "missing" })] }, []);
check("trang Cài đặt: chỉ tóm tắt và nút sang trang Cộng sự, không còn công tắc", !st.includes("rsa-set-toggle")
      && st.includes("rsa-goto-ws") && st.includes(vi["resonance.t0_settings_manage"])
      && st.includes(vi["resonance.t0_settings_summary"].replace("{n}", "1")), st);

const keys = Object.keys(vi).filter(function (k) { return k.indexOf("resonance.t0_") === 0; });
check("đủ khoá tiếng Anh", keys.length >= 11 && keys.every(function (k) { return typeof en[k] === "string" && en[k]; }),
      keys.filter(function (k) { return !en[k]; }).join(","));
check("không em dash trong chuỗi mới", keys.every(function (k) { return (vi[k] + en[k]).indexOf(String.fromCharCode(0x2014)) < 0; }));

// ───────────── toggleAgent: chỉ báo thành công khi server xác nhận; luôn phát sự kiện để tải trạng thái thật ─────────────
const events = [];
global.window = { dispatchEvent: function (e) { events.push(e.type); },
  JavisSessions: { brain: function () { return "brain"; } } };
global.CustomEvent = function (type) { this.type = type; };
let reply = { status: 200, body: { ok: true, agent: { slug: "viet-bai", enabled: true, status: "active" } } };
const sent = [];
global.fetch = function (url, init) {
  sent.push([url, JSON.parse(init.body)]);
  return Promise.resolve({ status: reply.status, json: function () { return Promise.resolve(reply.body); } });
};
(async function () {
  let r = await RA.toggleAgent("viet-bai", true);
  check("200: ok, gửi đúng route và thân, không kèm session_id", r.ok
        && sent[0][0].indexOf("/resonance/agents/toggle?brain=brain") === 0 && sent[0][1].slug === "viet-bai"
        && sent[0][1].enabled === true && !("session_id" in sent[0][1]), JSON.stringify(sent));
  check("200: phát sự kiện tải lại", events.indexOf("javis:resonance-agents-changed") >= 0);
  events.length = 0;
  reply = { status: 409, body: { ok: false, error: "cần xác nhận" } };
  r = await RA.toggleAgent("viet-bai", true);
  check("409: không ok, mang lỗi của server, VẪN phát sự kiện để tải trạng thái thật", !r.ok
        && r.error === "cần xác nhận" && events.indexOf("javis:resonance-agents-changed") >= 0);
  events.length = 0;
  global.fetch = function () { return Promise.reject(new Error("mạng")); };
  r = await RA.toggleAgent("viet-bai", false);
  check("rớt mạng: không ok, không ném lỗi, vẫn phát sự kiện", !r.ok && typeof r.error === "string" && r.error
        && events.indexOf("javis:resonance-agents-changed") >= 0);

  const WS = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8").replace(/\s+/g, " ");
  check("trang Cộng sự đọc /resonance/agents bằng MỘT request riêng (không theo từng dòng); lỗi không làm hỏng danh sách",
        (WS.match(/\/resonance\/agents\?brain=/g) || []).length === 1
        && /api\("\/resonance\/agents\?brain=" \+ encodeURIComponent\(b0\)\)\.catch\(function \(\) \{ return null; \}\)/.test(WS));
  check("dòng trợ lý vẽ công tắc qua rowToggleHtml, nối dây ws-rs-toggle và ws-rs-confirm",
        WS.includes("rowToggleHtml(") && WS.includes(".ws-rs-toggle") && WS.includes(".ws-rs-confirm") && WS.includes("toggleAgent("));
  check("trang Cộng sự nghe sự kiện đồng bộ", WS.includes("javis:resonance-agents-changed"));
  const APP = fs.readFileSync(path.join(ROOT, "dashboard", "app.js"), "latin1");
  check("app.js đổi gói WS resonance_agents thành sự kiện", APP.includes('"resonance_agents"')
        && APP.includes("javis:resonance-agents-changed"));
  const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "resonance-agent.js"), "utf8");
  check("trang Cài đặt không còn trình nghe công tắc cũ, có nút sang trang Cộng sự",
        !SRC.includes("rsa-set-toggle") && SRC.includes('JavisNav.go("workspace")'));
  const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
  check("CSS có .ws-rs và luật [hidden] riêng", CSS.includes(".ws-rs{") && CSS.includes(".ws-rs[hidden]"));

  // ───────────── sửa sau review cuối T0 ─────────────
  const RAW = fs.readFileSync(path.join(ROOT, "dashboard", "workspace.js"), "utf8");
  check("Important 2: đọc Cộng hưởng KHÔNG nằm trong Promise.all của danh sách (chậm thì danh sách vẫn hiện)",
        !/Promise\.all\(\[[^\]]*\/resonance\/agents/.test(WS) && /loadResonance\(\)/.test(WS));
  check("định danh mới tiếng Anh (không còn banDoCongHuong, taiCongHuong)",
        !RAW.includes("banDoCongHuong") && !RAW.includes("taiCongHuong"));
  check("chỉ phần chữ và công tắc bấm được (không cả dải rộng)", /\.ws-rs\{display:inline-flex/.test(CSS));
  check("không có ký tự em dash nguyên văn trong file test này",
        !fs.readFileSync(__filename, "utf8").includes(String.fromCharCode(0x2014)));
  check("xác nhận ở bảng bên phải phát sự kiện trong tab", /agents\/confirm[\s\S]{0,400}javis:resonance-agents-changed/.test(SRC));
  check("nút Quản lý mở đúng tab Trợ lý", SRC.includes('JavisWorkspace.openTab("agent")'));

  // Hàm thuần của workspace.js chạy dưới node với DOM giả tối thiểu (như test_workspace.js).
  global.window = { t: function (k) { return k; }, ic: function () { return ""; }, addEventListener: function () {},
    removeEventListener: function () {}, matchMedia: function () { return { matches: false }; } };
  global.document = { getElementById: function () { return null; }, createElement: function () {
    return { classList: { add: function () {}, remove: function () {} }, appendChild: function () {} }; },
    body: { classList: { add: function () {}, remove: function () {} } } };
  global.localStorage = { getItem: function () { return null; }, setItem: function () {} };
  delete require.cache[require.resolve(path.join(ROOT, "dashboard", "workspace.js"))];
  require(path.join(ROOT, "dashboard", "workspace.js"));
  const W = window.JavisWorkspace;
  check("resonanceMap: dữ liệu tốt thì dựng bản đồ theo slug", W.resonanceMap &&
        W.resonanceMap({ agents: [{ slug: "a", enabled: true }] }, {}).a.enabled === true);
  check("Minor 2: đọc lại hỏng thì GIỮ bản đồ cũ, không xoá hết công tắc",
        W.resonanceMap && W.resonanceMap(null, { b: { slug: "b" } }).b.slug === "b");
  const st = W.state();
  st.rsSaving = { a: true, b: true }; st.tagNote = { loi: true, msg: "cũ" };
  W.afterToggle("a", { ok: true, error: "" });
  check("Important 1, Minor 1: xong lượt nào chỉ gỡ cờ đang lưu của đúng trợ lý đó", !st.rsSaving.a && st.rsSaving.b === true);
  check("Minor 3: thành công thì gỡ câu báo lỗi cũ", st.tagNote === null);
  W.afterToggle("b", { ok: false, error: "x" });
  check("lỗi: gỡ cờ đang lưu và hiện lý do", !st.rsSaving.b && st.tagNote && st.tagNote.loi === true);
  process.exit(fails ? 1 : 0);
})();
