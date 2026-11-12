// 2026-11-12: documents in the create-team box, and brain files in a team's Info tab (dashboard/team-picker.js, teams.js).
//
//     node tests/js/test_team_create_docs_ui.js
//
// Owner: "làm phần này khi tạo team luôn, thêm file và thêm link tài liệu". A customer had to upload the same files
// again for every new team although they were already in the brain.
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");
const vi = JSON.parse(read("i18n/vi.json"));
const en = JSON.parse(read("i18n/en.json"));
const P = require(path.join(root, "dashboard", "team-picker.js"));
P.setStrings(vi);

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + String(extra).slice(0, 500)));
  if (!cond) fails++;
}

const roster = [{ slug: "lan", name: "Lan" }];
const base = { mode: "create", selected: ["lan"], leader: "lan", docs: [], links: [] };

// ---- the block is in the create box only ----
check("the create box has the documents block, under the name", (() => {
  const h = P.html(base, roster);
  return h.includes('class="tmp-docs-box"') && h.indexOf("tmp-name-input") < h.indexOf("tmp-docs-box")
    && h.indexOf("tmp-docs-box") < h.indexOf("tmp-search-input");
})());
check("the add-members box has none", !P.html({ mode: "add", selected: [], exclude: [] }, roster).includes("tmp-docs"));
check("it starts closed and opens once something is picked or typed", !/<details class="tmp-desc tmp-docs" open/.test(P.docsHtml(base))
  && /<details class="tmp-desc tmp-docs" open/.test(P.docsHtml(Object.assign({}, base, { links: ["https://a.vn"] })))
  && /<details class="tmp-desc tmp-docs" open/.test(P.docsHtml(Object.assign({}, base, { docQuery: "bang" }))));
check("three ways in: search the brain, upload from the device, paste a link", (() => {
  const h = P.docsHtml(base);
  return h.includes("tmp-doc-search") && h.includes("tmp-doc-upload") && h.includes("tmp-link-input") && h.includes("tmp-link-add");
})());

// ---- picking files ----
let st = P.addDoc(base, { name: "bang-gia.md", brain_path: "docs/bang-gia.md" });
check("a brain file is added once", P.addDoc(st, { name: "bang-gia.md", brain_path: "docs/bang-gia.md" }).docs.length === 1);
check("the old state is not changed", base.docs.length === 0 && st.docs.length === 1);
let full = base;
for (let i = 0; i < P.DOCS_MAX + 3; i++) full = P.addDoc(full, { name: "f" + i, brain_path: "docs/f" + i });
check("at most DOCS_MAX files", full.docs.length === P.DOCS_MAX && P.DOCS_MAX === 10);
st = Object.assign({}, st, { docQuery: "bang", docState: "done", docResults: [{ path: "docs/bang-gia.md", name: "bang-gia.md" },
  { path: "docs/bang-gia-2.md", name: "bang-gia-2.md" }] });
const res = P.docResultsHtml(st);
check("a result already picked says so and cannot be added again", /data-doc-add="0" disabled>Đã thêm</.test(res)
  && /data-doc-add="1">Thêm</.test(res), res);
check("searching and no match have their own line", P.docResultsHtml(Object.assign({}, st, { docState: "searching" })).includes(vi["teams.pick.doc_searching"])
  && P.docResultsHtml(Object.assign({}, st, { docResults: [] })).includes(vi["teams.pick.doc_none"])
  && P.docResultsHtml(Object.assign({}, st, { docQuery: "  " })) === "");
check("a file name with markup is shown as text", !P.docResultsHtml(Object.assign({}, st, { docResults: [{ path: "a/<b>.md", name: "<img src=x>" }] })).includes("<img"));

// ---- uploads ----
const busy = P.addDoc(base, { name: "hop-dong.pdf", path: "", uid: "u1", busy: true, err: "" });
check("Create waits while a file uploads", P.canSubmit(base) === true && P.canSubmit(busy) === false);
check("the chip says it is uploading", P.docChipsHtml(busy).includes(vi["teams.pick.doc_uploading"]));
const failed = P.addDoc(base, { name: "hop-dong.pdf", path: "", uid: "u1", busy: false, err: "1" });
check("a failed upload is marked and is not sent", P.docChipsHtml(failed).includes("is-err") && P.docPayload(failed).attachments.length === 0);

// ---- links ----
check("a bare address gets https://", P.cleanLink("docs.google.com/document/d/1") === "https://docs.google.com/document/d/1"
  && P.cleanLink(" https://a.vn/x ") === "https://a.vn/x" && P.cleanLink("localhost:7777/x") === "https://localhost:7777/x");
check("what is not a web link is refused", ["javascript:alert(1)", "mailto:a@b.vn", "ftp://a.b", "hai chu", "abc", ""].every((u) => P.cleanLink(u) === ""));
let L = P.addLink(base, "example.com/a");
check("a link is added and the box is emptied", L.ok && L.st.links[0] === "https://example.com/a" && L.st.linkDraft === "" && !L.st.linkBad);
check("the same link twice stays one", P.addLink(L.st, "https://example.com/a").st.links.length === 1);
const bad = P.addLink(base, "khong phai link");
check("a bad link says so and adds nothing", !bad.ok && bad.st.linkBad && bad.st.links.length === 0
  && P.docsHtml(bad.st).includes(vi["teams.pick.link_bad"]));
check("an empty box is not an error", !P.addLink(base, "  ").st.linkBad);
check("removing by position", P.removeLink(L.st, 0).links.length === 0 && P.removeDoc(st, 0).docs.length === 0);

// ---- what goes to the server ----
const mix = P.addLink(P.addDoc(P.addDoc(base, { name: "a.md", brain_path: "docs/a.md" }), { name: "b.pdf", path: "/staging/b.pdf", uid: "u2" }), "a.vn").st;
check("the request carries brain files by brain_path, uploads by path, and the links",
  JSON.stringify(P.docPayload(mix)) === JSON.stringify({ attachments: [{ brain_path: "docs/a.md", name: "a.md" },
    { path: "/staging/b.pdf", name: "b.pdf" }], links: ["https://a.vn"] }), JSON.stringify(P.docPayload(mix)));
check("the summary counts files and links together", P.docsCount(mix) === 3 && P.docsSummaryHtml(mix).includes(">3<"));

// ---- teams.js wiring ----
const tm = read("teams.js");
check("Create sends the picked documents with the team", /client_req_id: st\.reqId, attachments: docs\.attachments, links: docs\.links \}/.test(tm));
check("a failed upload stops Create with a clear line", tm.includes('return pickFail(tw("teams.pick.doc_fix"))'));
check("the server's count of documents left out is told once, after the team opens", tm.includes('setNote(tw("teams.pick.docs_partial", { n: missed }))'));
check("the brain search asks /files/search by name, with a pause while typing",
  tm.split('"/files/search?mode=name&limit=20&q="').length === 3 && /\}, 280\);/.test(tm));
check("Enter in the link box adds the link and never presses Create",
  /contains\("tmp-link-input"\) && e\.key === "Enter"\) \{ e\.preventDefault\(\); pickAddLink\(\); return; \}/.test(tm)
  && /contains\("tmp-doc-search"\) && e\.key === "Enter"\) \{ e\.preventDefault\(\); return; \}/.test(tm));
check("Info tab: a search box for brain files, added through the team's own route", tm.includes('class="tm-info-fsearch"')
  && tm.includes('call("POST", teamUrl("/files"), { attachments: [{ brain_path: it.path, name: it.name }] })'));
check("what was typed for one team is not shown in another", tm.includes("S.info = null; S.infoFind = null;"));

// ---- words ----
const keys = ["docs_add", "docs_help", "doc_search_ph", "doc_upload", "doc_add", "doc_added", "doc_searching", "doc_none", "doc_uploading",
  "doc_failed", "doc_remove", "doc_fix", "link_ph", "link_add", "link_bad", "docs_partial"].map((k) => "teams.pick." + k);
check("every new line exists in Vietnamese and English", keys.every((k) => vi[k] && en[k]), keys.filter((k) => !vi[k] || !en[k]));
const LONG_DASH = new RegExp("[" + String.fromCharCode(0x2013, 0x2014) + "]");
check("no long dash in the new lines", keys.every((k) => !LONG_DASH.test(vi[k] + en[k])));
const css = read("console.css");
check("styles for the block, readable on a phone (16px text, 44px buttons)", css.includes(".tmp-docs-row .ws-btn { min-height: 44px;")
  && css.includes(".tmp-doc-res-text b { font-weight: 600; font-size: 16px;") && css.includes("@media (max-width: 640px) { .tmp-docs-row { flex-wrap: wrap; }"));

process.exit(fails ? 1 : 0);
