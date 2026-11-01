// Desktop Chat page: wide Markdown tables use the available pane without widening
// mobile chats or the separate HUD / Workspace / Coding layouts.
// Run: node tests/js/test_chat_desktop_width.js
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "../..");
const css = fs.readFileSync(path.join(root, "dashboard/style.css"), "utf8");
const consoleJs = fs.readFileSync(path.join(root, "dashboard/console.js"), "utf8");

// This page ID is created only by the normal Chat page; Coding has #cdPage
// and HUD / Workspace use separate containers.
assert.match(consoleJs, /'<div class="chatpage" id="chatPage">'/);
assert.match(consoleJs, /'<div class="chatpage" id="cdPage">'|function renderCoding/);

// Keep the old readable measure as the fallback and for every other page.
assert.match(css, /\.msg-javis \.bubble \{ max-width: min\(72ch, 100%\); \}/);
assert.match(css, /\.msg-javis > \.jr-chat \{[^\n]*max-width: min\(72ch, 100%\)/);

// One desktop-only rule must widen BOTH the assistant bubble and the reaction
// anchor together. A 100% ceiling means editor/narrow panes never overflow.
assert.match(css, /@media \(min-width: 861px\) \{\s*#chatPage \.msg-javis > \.jr-chat,\s*#chatPage \.msg-javis \.bubble \{\s*max-width: min\(1200px, 100%\);\s*\}\s*\}/);

// Wide tables retain their own horizontal scrolling when columns do not fit.
assert.match(css, /\.md-tablewrap, \.jv-dataview \.dv-tablewrap \{\s*overflow-x: auto;/);
assert.match(css, /\.md-tablewrap > \.md-table, \.jv-dataview \.dv-tablewrap > \.md-table \{/);

console.log("PASS desktop Chat answer/table width; mobile and other views remain scoped");
