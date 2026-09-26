/* Khởi động với brain tải muộn và từ điển tải muộn vẫn giữ đúng khung chat. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..", "..");
const app = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
const side = fs.readFileSync(path.join(root, "dashboard", "sessions-ui.js"), "utf8");
const ui = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");

function functionSource(src, name) {
  const start = src.indexOf("function " + name + "(");
  assert.ok(start >= 0, "missing " + name);
  const end = src.indexOf("\n}", start);
  assert.ok(end > start, "unterminated " + name);
  return src.slice(start, end + 2);
}

// app.js khôi phục cuộc của brain phụ trước; brains-ui.js chỉ tải được danh sách
// brain sau đó và phát change. Sự kiện này không được xoá cuộc vừa khôi phục.
{
  const saved = JSON.stringify({ brain: "vault/other", sessionId: "last-viewed", convo: [] });
  let selected = "brain", onChange, resets = 0, opened = 0;
  const ctx = {
    localStorage: { getItem: k => k === "javis.session.v1" ? saved : null, setItem() {} },
    SESSION_KEY: "javis.session.v1", convo: [], savedSessionId: null, _tinCu: null,
    graphSource: { value: "brain", addEventListener: (name, fn) => { if (name === "change") onChange = fn; } },
    currentBrainPath: () => selected,
    window: { JavisResume: null },
    datMoiTinCu() {}, notifySessions() {}, syncActiveUI() {},
    resetChatView() { resets++; }, openStoredSession() { opened++; }, capNhatManChinh() {},
    _trangGiuKhungChat: () => false,
  };
  vm.createContext(ctx);
  const brainBlock = app.slice(app.indexOf("let _lastBrain = currentBrainPath();"),
    app.indexOf("\n// ============================================\n// Realtime graph watch", app.indexOf("let _lastBrain = currentBrainPath();")));
  vm.runInContext(brainBlock + "\n" + functionSource(app, "restoreSession"), ctx);
  ctx.restoreSession();
  assert.equal(ctx.savedSessionId, "last-viewed");
  selected = "vault/other";
  ctx.graphSource.value = "path:vault/other";
  onChange();
  assert.equal(resets, 0, "late brain restoration erased the last viewed chat");
  assert.equal(opened, 0, "last viewed chat was already restored locally");
  assert.equal(ctx.savedSessionId, "last-viewed");
  selected = "brain";
  ctx.graphSource.value = "brain";
  onChange();
  assert.equal(resets, 1, "a real brain switch must still clear the old brain's chat");
}

// Các nhãn dựng động trước khi vi.json về phải có hook để applyDom() dịch sau.
for (const [src, marker, key] of [
  [side, 'class="cside-tab" data-tab="chat"', "sess.tab_chat"],
  [side, 'class="cside-tab" data-tab="files"', "sess.tab_files"],
  [side, 'class="cside-new"', "sess.new_chat"],
  [side, 'class="cside-search"', "sess.search_ph"],
  [ui, 'class="cp-ico-btn cp-min"', "cs.cp_min"],
]) {
  const start = src.indexOf(marker);
  assert.ok(start >= 0, "missing dynamic control " + marker);
  const region = src.slice(start, start + 350);
  assert.ok(region.includes('data-i18n') && region.includes(key), key + " cannot be translated after load");
}

console.log("OK - restore last chat and translate late labels");
