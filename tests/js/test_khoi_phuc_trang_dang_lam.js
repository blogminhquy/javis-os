/* Khoi phuc trang va phien cong su sau khi trinh duyet dung lai tab. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..", "..");
const consoleJs = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
const workspaceJs = fs.readFileSync(path.join(root, "dashboard", "workspace.js"), "utf8");
const appJs = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
function fn(src, name, indent = "  ") {
  const start = src.indexOf(indent + "function " + name + "(");
  assert.ok(start >= 0, "missing " + name);
  const end = src.indexOf("\n" + indent + "}", start);
  assert.ok(end > start, "unterminated " + name);
  return src.slice(start, end + indent.length + 2);
}
function storage(seed = {}) {
  const data = { ...seed };
  return {
    getItem: k => Object.hasOwn(data, k) ? data[k] : null,
    setItem: (k, v) => { data[k] = String(v); },
    data,
  };
}

// These cases fail if startup goes to home, if navigation is not saved, or if stale ids
// are trusted. Run the actual routing functions with only DOM and network edges stubbed.
function navCase(seed, expected) {
  const localStorage = storage(seed);
  const route = { active: "home", openGroup: "" };
  const rendered = [];
  const classes = new Set();
  const ctx = {
    localStorage,
    Alpine: { store: () => route },
    RAIL_BY_ID: { home: {}, chat: {}, workspace: {}, settings: {} },
    TRANG_GOP: { agents: "workspace" },
    TRANG_CUOI_KEY: "javis_last_page",
    groupLabelOf: id => "group:" + id,
    document: { body: { classList: {
      toggle: (c, on) => on ? classes.add(c) : classes.delete(c),
    } } },
    window: {},
    renderPage: id => rendered.push(id),
    refreshModelUi() {}, parkQuickSet() {}, recomputeGraph() {},
    _pageLeave: null,
  };
  vm.createContext(ctx);
  vm.runInContext(fn(consoleJs, "navigateTo") + "\n" + fn(consoleJs, "khoiPhucTrang"), ctx);
  ctx.khoiPhucTrang();
  assert.equal(route.active, expected);
  assert.equal(rendered.at(-1), expected);
  assert.equal(route.openGroup, "group:" + expected);
  assert.ok(classes.has("in-console"));
  ctx.navigateTo("settings");
  assert.equal(localStorage.data.javis_last_page, "settings");
}
navCase({}, "chat");
navCase({ javis_last_page: "workspace" }, "workspace");
navCase({ javis_last_page: "not-a-page" }, "chat");

// An assistant's selected conversation can be older than the latest one. Reopening the
// workspace must use its exact id, while keeping the main chat id for the return path.
{
  const localStorage = storage({ javis_workspace_view: JSON.stringify({
    brain: "brain-a", kind: "agent", slug: "writer", sessionId: "older-chat", mainSessionId: "main-chat",
  }) });
  let opened = null;
  const ctx = {
    localStorage,
    brain: () => "brain-a",
    VI_TRI_KEY: "javis_workspace_view",
    S: { loai: "agent", chon: { agent: "writer", workflow: "review" }, sessionCuaPhien: {} },
    _phienTruoc: null,
    danhSach: () => [{ slug: "writer" }],
    dangChon: () => ctx.danhSach().find(x => x.slug === ctx.S.chon[ctx.S.loai]),
    veDanhSach() {},
    moPhien: (...args) => { opened = args; },
    window: { JavisSessions: { current: () => "older-chat" } },
  };
  vm.createContext(ctx);
  vm.runInContext(fn(workspaceJs, "docViTri") + "\n" + fn(workspaceJs, "luuViTri") + "\n" + fn(workspaceJs, "nhoPhienTruoc") + "\n" + fn(workspaceJs, "chonMacDinh"), ctx);
  ctx.nhoPhienTruoc();
  ctx.chonMacDinh();
  assert.equal(ctx._phienTruoc, "main-chat");
  assert.equal(opened[2], "older-chat");
  ctx.luuViTri("selected-older");
  assert.deepEqual(JSON.parse(localStorage.data.javis_workspace_view), {
    brain: "brain-a", kind: "agent", slug: "writer", sessionId: "selected-older", mainSessionId: "main-chat",
  });
  ctx.S.loai = "workflow";
  ctx.danhSach = () => [{ slug: "review" }];
  ctx.chonMacDinh();
  assert.equal(opened[2], null, "another coworker must not open the assistant's conversation");
}

// A live socket has already delivered chat events while the page is in memory. Returning
// from another app must leave the existing transcript DOM intact.
{
  let reloads = 0;
  const ctx = {
    _hiddenAt: Date.now() - 30000,
    ws: { readyState: 1 },
    WebSocket: { OPEN: 1 },
    savedSessionId: "main-chat",
    connect() {},
    openStoredSession() { reloads++; },
  };
  vm.createContext(ctx);
  vm.runInContext(fn(appJs, "_resumeSauNgu", ""), ctx);
  ctx._resumeSauNgu(false);
  assert.equal(reloads, 0, "live transcript was rebuilt on return");
  ctx.ws.readyState = 3;
  ctx._hiddenAt = Date.now() - 30000;
  ctx._resumeSauNgu(false);
  assert.equal(reloads, 1, "missed events must still be recovered after disconnect");
}

console.log("OK - khoi phuc trang dang lam va phien tro ly");
