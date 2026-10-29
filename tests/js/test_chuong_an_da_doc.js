/* Chuông thông báo: đọc rồi thì ẩn, Đọc tất cả là trống, mỗi thẻ có nút X (0.408.0).

       node tests/js/test_chuong_an_da_doc.js

   Chủ repo (2026-10-29): "khi anh đã đọc rồi nó phải ẩn các thông báo đi, ấn đọc tất cả phải xoá
   hết các thông báo đi và có nút x để xoá thông báo đó khỏi hàng đợi", và "anh đã ấn Không cần
   báo rồi nhưng nó vẫn hiện ra".

   Chạy THẬT notifications.js trên một trang giả tối thiểu (không jsdom): server giả trả hòm thư và
   tin tức, rồi soi HTML danh sách mà file vẽ ra. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "notifications.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
};

// ---- fake page ----
const els = {};
function el(id) {
  if (!els[id]) {
    els[id] = {
      id, hidden: id === "notificationPanel", innerHTML: "", textContent: "", disabled: false, dataset: {},
      _h: {}, classList: { toggle() {}, add() {}, remove() {} },
      addEventListener(ev, fn) { (this._h[ev] = this._h[ev] || []).push(fn); },
      setAttribute() {}, querySelector: () => null, querySelectorAll: () => [],
    };
  }
  return els[id];
}
const store = {};
global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
global.document = { readyState: "complete", hidden: false, getElementById: el, addEventListener() {} };
global.location = { search: "", pathname: "/", origin: "http://x" };
global.history = { replaceState() {} };
global.window = global;
window.t = (k, p) => {
  let s = VI[k] || k;
  if (p) Object.keys(p).forEach((n) => { s = s.replace("{" + n + "}", p[n]); });
  return s;
};
window.addEventListener = () => {};
window.ic = (n) => '<svg data-ic="' + n + '"></svg>';

let thu = [
  { id: "a1", kind: "report", title: "Chưa đọc 1", body: "x", ts: 1, read: false },
  { id: "a2", kind: "report", title: "Đã đọc 1", body: "x", ts: 1, read: true },
  { id: "a3", kind: "report", title: "Đã đọc 2", body: "x", ts: 1, read: true },
];
const goi = [];
global.fetch = (url, opt) => {
  goi.push([url, opt && opt.body]);
  let d = {};
  if (url.startsWith("/inbox?")) d = { items: thu, unread: thu.filter((x) => !x.read).length };
  else if (url === "/notifications") d = { items: [{ id: "n1", kind: "community", title: "Tin 1" }, { id: "n2", kind: "community", title: "Tin 2" }] };
  else if (url === "/notifications/read") d = { read: [] };
  else if (url === "/inbox/read") { thu.forEach((x) => { x.read = true; }); d = { ok: true, unread: 0 }; }
  return Promise.resolve({ ok: true, json: () => Promise.resolve(d) });
};
const cho = () => new Promise((r) => setTimeout(r, 20));

new Function(JS)();
const list = el("notificationList");

(async () => {
  await cho();
  let h = list.innerHTML;
  check("tab Của tôi chỉ hiện thông báo chưa đọc", h.includes("Chưa đọc 1") && !h.includes("Đã đọc 1"), h.slice(0, 200));
  check("cuối danh sách có dòng xem lại thông báo đã đọc (đếm đúng 2)",
    h.includes("data-noti-xemdadoc") && h.includes(VI["noti.show_read"].replace("{count}", "2")));
  check("mỗi thẻ có nút X", (h.match(/data-noti-x(?!emdadoc)/g) || []).length === 1);
  check("nút X có nhãn đọc được", h.includes('aria-label="' + VI["noti.dismiss"] + '"'));

  // "Đọc tất cả" (the real button handler)
  el("notificationReadAll")._h.click.forEach((f) => f());
  await cho();
  h = list.innerHTML;
  check("bấm Đọc tất cả: danh sách trống, nói rõ không còn thông báo chưa đọc",
    !h.includes("Chưa đọc 1") && h.includes(VI["noti.all_clear"]), h.slice(0, 200));
  check("Đọc tất cả đi qua server", goi.some(([u, b]) => u === "/inbox/read" && String(b).includes('"all":true')));
  check("vẫn còn đường xem lại cả 3 thông báo đã đọc", h.includes(VI["noti.show_read"].replace("{count}", "3")));

  // News tab: same rule
  el("notiTabNews")._h.click.forEach((f) => f());
  await cho();
  h = list.innerHTML;
  check("tab Tin tức: đã Đọc tất cả thì không còn tin nào hiện", !h.includes("Tin 1") && h.includes(VI["noti.all_clear"]), h.slice(0, 200));

  // ---- source contract for the click paths a fake page cannot click ----
  check("X trên thư riêng gọi /inbox/delete", /fetch\("\/inbox\/delete"/.test(JS) && /if \(t\.closest\("\[data-noti-x\]"\)\)/.test(JS));
  check("X trên tin tức ẩn hẳn tin đó trên máy này", /function anTin\(id\)/.test(JS) && /state\.an\.has\(String\(item\.id\)\)/.test(JS));
  check("Enter trên nút X không mở thẻ tin tức", /if \(event\.target !== card\) return;/.test(JS));
  check("Không cần báo cũng đánh dấu đã đọc, nên thẻ rời danh sách",
    /if \(body\.axis === "not_needed"\) \{[\s\S]{0,200}item\.read = true;/.test(JS));

  for (const k of ["noti.dismiss", "noti.show_read", "noti.hide_read", "noti.all_clear"]) {
    check("có chữ " + k + " cả tiếng Việt lẫn tiếng Anh", !!VI[k] && !!EN[k]);
  }

  console.log("");
  if (fails.length) { console.log("FAIL - test_chuong_an_da_doc: " + fails.length); process.exit(1); }
  console.log("OK - test_chuong_an_da_doc: all pass");
})();
