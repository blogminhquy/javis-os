// Cuon phai trung KHUNG NGUOI DUNG DANG XEM (BUG-001).
//
//     node tests/js/test_cuon_dung_khung.js
//
// Truoc 0.58.5 lenh `scroll` luon nham #chatArea, nen dung o trang Tu hoc hay Viec dinh ky ma
// bao "cuon xuong duoi" thi danh sach dung im con khung chat ben canh nhay. Test nay NAP that
// ui-actions.js voi mot DOM gia roi GOI handle(), de biet no cuon dung node nao - canary quet
// chuoi khong bat duoc loai loi nay.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// ---- DOM gia toi thieu ----
let MAP = {};          // id -> phan tu
let GUI = [];          // cac frame ui_result da gui ve server

function nut(o) {
  o = o || {};
  const n = {
    scrollHeight: o.sh || 0,
    clientHeight: o.ch || 0,
    scrollTop: 0,
    daCuonToi: null,
    _oy: o.oy || "auto",
    _con: o.con || [],
    _hien: o.hien !== false,
    getClientRects() { return n._hien ? [{}] : []; },
    querySelectorAll() { return n._con; },
    scrollTo(x) { n.daCuonToi = x.top; },
  };
  return n;
}

global.document = {
  getElementById: (id) => MAP[id] || null,
  body: { scrollHeight: 5000 },
};
global.window = {
  t: (k) => k,
  getComputedStyle: (e) => ({ overflowY: e._oy || "auto" }),
  scrollTo: (x) => { global.window.daCuonTaiLieu = x.top; },
  JavisWsSend: (o) => GUI.push(o),
  JavisSessions: { current: () => "" },
};

const A = require(path.join(ROOT, "dashboard", "ui-actions.js"));
const UI = global.window.JavisUiActions;

async function cuon(target) {
  GUI = [];
  global.window.daCuonTaiLieu = null;
  await UI.handle({ id: "x", action: "scroll", target: target });
  return GUI[0] || {};
}

(async function () {
  // 1) Dang mo mot trang noi dung cuon duoc: cuon TRANG, khong dung toi chat
  let chat = nut({ sh: 3000, ch: 500 });
  let than = nut({ sh: 4000, ch: 600 });
  MAP = { cview: nut({ con: [than] }), cviewBody: than, chatArea: chat };
  let r = await cuon("bottom");
  check("trang noi dung dang mo: cuon than trang", than.daCuonToi === 4000);
  check("trang noi dung dang mo: KHONG cuon khung chat", chat.daCuonToi === null);
  check("bao ve dung thu vua cuon", r.ok === true && r.detail === "ui.scroll_page");

  // 2) Cockpit (cview an): quay ve khung chat
  chat = nut({ sh: 3000, ch: 500 });
  MAP = { cview: nut({ hien: false }), cviewBody: nut({ sh: 4000, ch: 600 }), chatArea: chat };
  r = await cuon("bottom");
  check("cockpit: cuon khung chat", chat.daCuonToi === 3000 && r.detail === "ui.scroll_chat");

  // 3) Noi ro "khung chat" thi cuon chat du dang mo trang
  chat = nut({ sh: 3000, ch: 500 });
  than = nut({ sh: 4000, ch: 600 });
  MAP = { cview: nut({ con: [than] }), cviewBody: than, chatArea: chat };
  r = await cuon("chat_top");
  check("chat_top: cuon khung chat len dau", chat.daCuonToi === 0 && than.daCuonToi === null);

  // 4) Trang dan sat mep (.cview-flush): than tat cuon, con ben trong moi cuon
  const trong = nut({ sh: 9000, ch: 700 });
  const nho = nut({ sh: 300, ch: 100 });
  than = nut({ sh: 600, ch: 600, oy: "hidden", con: [nho, trong] });
  MAP = { cview: nut({ con: [than] }), cviewBody: than, chatArea: nut({ sh: 3000, ch: 500 }) };
  r = await cuon("page_bottom");
  check("trang flush: cuon khung con CAO NHAT", trong.daCuonToi === 9000 && nho.daCuonToi === null);

  // 5) Ep cuon trang ma khong co trang nao: noi that, khong lang le cuon chat
  MAP = { cview: nut({ hien: false }), cviewBody: nut(), chatArea: nut({ sh: 3000, ch: 500 }) };
  r = await cuon("page_bottom");
  check("page_bottom khi khong co trang: bao khong lam duoc",
        r.ok === false && r.detail === "ui.scroll_no_page");

  // 6) Khong khung nao cuon duoc: cuon chinh tai lieu
  MAP = { cview: nut({ hien: false }), cviewBody: nut(), chatArea: nut({ sh: 100, ch: 500 }) };
  r = await cuon("bottom");
  check("khong khung nao cuon duoc: cuon ca tai lieu",
        r.ok === true && r.detail === "ui.scroll_window" && global.window.daCuonTaiLieu === 5000);

  // 6b) Trang "Tro chuyen" be thang #chatArea vao khung noi dung: van cuon dung, va goi
  // dung ten (khung chat) chu khong bao la "noi dung trang".
  chat = nut({ sh: 3000, ch: 500 });
  MAP = { cview: nut({ con: [chat] }), cviewBody: nut({ oy: "hidden", con: [chat] }), chatArea: chat };
  r = await cuon("bottom");
  check("trang Tro chuyen: cuon khung chat va goi dung ten",
        chat.daCuonToi === 3000 && r.detail === "ui.scroll_chat");

  // 7) Ba noi phai cung danh sach pham vi cuon
  const py = fs.readFileSync(path.join(ROOT, "server", "ui_targets.py"), "utf8");
  const m = py.match(/SCROLL_TARGETS = \(([\s\S]*?)\)/);
  const pyList = m ? m[1].split(",").map((x) => x.trim().replace(/^"|"$/g, "")).filter(Boolean) : [];
  check("SCROLLS cua ui-actions == SCROLL_TARGETS cua ui_targets.py",
        JSON.stringify(pyList) === JSON.stringify(A.SCROLLS));

  if (fails.length) {
    console.log("\nFAIL: " + fails.length + " " + JSON.stringify(fails));
    process.exit(1);
  }
  console.log("\nOK - cuon dung khung");
})();
