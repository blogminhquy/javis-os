// Resonance: thẻ mục tiêu không bão request, không vẽ lại bậc hai (audit tốc độ 08/10/2026).
//
//     python tests/run.py --js resonance_perf_ui -v
//
// Chạy NGUYÊN module dashboard/chat-resonance.js trong vm với DOM và fetch giả có bộ đếm (không đo thời gian trình
// duyệt). Trước bản sửa: 50 thẻ cùng một mục tiêu phát 50 GET và 2.500 lần gán innerHTML khi vẽ.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "chat-resonance.js"), "utf8");

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + JSON.stringify(extra)));
  if (!cond) fails++;
}

function world(goals) {
  const st = { requests: [], writes: 0, els: [], brain: "/brain-a", resolvers: [] };
  function mkEl() {
    return { attrs: {}, classList: { toggle() {} }, setAttribute(k, v) { this.attrs[k] = v; },
      getAttribute(k) { return this.attrs[k]; }, set innerHTML(v) { st.writes++; this._html = v; },
      get innerHTML() { return this._html || ""; } };
  }
  const document = { readyState: "loading", addEventListener() {},
    querySelectorAll(sel) { const m = /data-goal="([^"]+)"/.exec(sel); return st.els.filter((e) => !m || e.attrs["data-goal"] === m[1]); },
    createElement: mkEl };
  const ctx = { document, window: { t: (k) => k, currentBrainPath: () => st.brain },
    fetch(url) {
      st.requests.push(url);
      const id = decodeURIComponent(/\/goals\/([^?]+)/.exec(url)[1]);
      return new Promise((res) => st.resolvers.push(() => res({ status: 200, json: () => Promise.resolve({ goal: goals[id] }) })));
    } };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  st.api = ctx.window.JavisResonance;
  st.add = (gid) => st.api.ve({ querySelector: () => null, appendChild: (e) => st.els.push(e) }, { goal_id: gid });
  st.flush = async () => { const rs = st.resolvers.splice(0); rs.forEach((f) => f()); for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); };
  return st;
}

const G = (id, rev) => ({ goal_id: id, status: "active", revision: rev || 1, criteria: [], understanding: "Mục tiêu " + id });

(async function () {
  // 50 thẻ cùng một mục tiêu nạp đồng thời (mở lại hội thoại có nhiều tin báo).
  const w = world({ g1: G("g1") });
  for (let i = 0; i < 50; i++) w.add("g1");
  const loading = w.writes;
  await w.flush();
  check("50 thẻ cùng mục tiêu: đúng MỘT GET", w.requests.length === 1, w.requests.length);
  check("50 thẻ: số lần vẽ tuyến tính (50 lần khi có kết quả, không phải 2.500)", w.writes - loading === 50, w.writes - loading);
  const full = w.els.filter((e) => !/see_latest/.test(e.innerHTML));
  check("chỉ thẻ CUỐI vẽ đầy đủ, các thẻ trước gọn", full.length === 1 && full[0] === w.els[49]);

  // Hai mục tiêu khác nhau: mỗi mục tiêu một GET, không lẫn.
  const w2 = world({ a: G("a"), b: G("b") });
  for (let i = 0; i < 10; i++) { w2.add("a"); w2.add("b"); }
  await w2.flush();
  check("hai mục tiêu: hai GET, mỗi thẻ mang đúng mục tiêu của nó",
        w2.requests.length === 2 && w2.els.every((e) => e._goal && e._goal.goal_id === e.attrs["data-goal"]));

  // Đổi brain khi request còn chạy: kết quả thuộc brain cũ bị bỏ, không vẽ.
  const w3 = world({ g1: G("g1") });
  w3.add("g1");
  const before = w3.writes;
  w3.brain = "/brain-b";
  await w3.flush();
  check("đổi brain giữa chừng: kết quả brain cũ không được vẽ", w3.writes === before && !w3.els[0]._goal);
  check("request mang đúng brain lúc phát", w3.requests[0].indexOf(encodeURIComponent("/brain-a")) > 0);
  w3.add("g1");
  check("sau khi đổi brain: thẻ mới phát request MỚI theo brain mới, không ghép vào request cũ",
        w3.requests.length === 2 && w3.requests[1].indexOf(encodeURIComponent("/brain-b")) > 0);

  // Sau một request đã xong, thẻ mới (tin báo mới tới) phát request mới: đọc trạng thái mới, không dùng bộ nhớ đệm.
  const w4 = world({ g1: G("g1", 1) });
  w4.add("g1");
  await w4.flush();
  w4.add("g1");
  check("request đã xong không bị dùng lại: thẻ mới đọc trạng thái mới", w4.requests.length === 2);

  check("sau thao tác (bấm nút) luôn đọc lại trạng thái MỚI, không ghép vào request đang chạy",
        /load\(el, true\)/.test(SRC) && /if \(cur && !fresh\)/.test(SRC));

  if (fails) { console.log("\n" + fails + " FAIL"); process.exit(1); }
  console.log("\nOK");
})();
