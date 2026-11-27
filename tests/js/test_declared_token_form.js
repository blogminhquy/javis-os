/* Declared account form (`TOKEN_FORM` -> `k.token_form`) drawn by `drawTokenForm` in conversations.js.

       node tests/js/test_declared_token_form.js

   Runs the real function on a tiny fake DOM (no browser). Guarded here:
   1. A select without dependencies loads its list on open (GET); `auto_single` picks the only item on an Add form.
   2. A field hidden by `hidden_when` is emptied and not required while hidden.
   3. A dependent list POSTs its fields as a form body (a typed key never in a URL) and `fill` copies the item.
   4. The token is ONE JSON object of the sent fields; `send: false` fields stay out; a missing field throws.
   5. Edit form: fields (the workspace select too) start from the saved account; untouched = "" (no change),
      touched = a full token, so changing only the secret keeps the workspace.
   6. `generate`: Generate fills a random 64-hex-char secret, shows it and marks the form changed.
   7. Duplicate warning: an option on a network a core channel answers is never picked by itself, is marked in the list,
      and picking it shows a warning whose box must be ticked before a token is given; the saved pick of an edit is
      not asked again.
*/
const fs = require("fs");
const path = require("path");
const CV = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "conversations.js"), "utf8");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

const a = CV.indexOf("  function drawTokenForm(");
const b = CV.indexOf("  // {network: label of the core channel");
check("drawTokenForm found", a > 0 && b > a);
const SRC = CV.slice(a, b);

// ---- fake DOM: enough for the markup drawTokenForm writes ----
function attrs(s) { const o = {}; s.replace(/([a-z-]+)="([^"]*)"/g, (_, k, v) => { o[k] = v.replace(/&quot;/g, '"').replace(/&amp;/g, "&"); }); return o; }
function node(tag, at, parent) {
  const n = { tag, id: at.id || "", cls: at.class || "", dataset: {}, hidden: false, disabled: false, parent,
              value: at.value || "", type: at.type || "", options: [], selectedIndex: 0 };
  Object.keys(at).forEach((k) => { if (k.startsWith("data-")) n.dataset[k.slice(5)] = at[k]; });
  if (tag === "select") {
    Object.defineProperty(n, "innerHTML", {
      set(h) {
        n.options = [];
        h.replace(/<option([^>]*)>([^<]*)<\/option>/g, (_, at2, txt) => {
          const x = attrs(at2); n.options.push({ value: x.value || "", text: txt, dataset: x["data-i"] != null ? { i: x["data-i"] } : {} });
        });
        n.selectedIndex = 0; n.value = n.options.length ? n.options[0].value : "";
      }, get() { return ""; } });
    Object.defineProperty(n, "_v", { value: null, writable: true });
  }
  if (tag === "div" && n.dataset.dup != null) {
    // The duplicate warning box: its markup is written later, and holds the confirm checkbox.
    n.kids = [];
    Object.defineProperty(n, "innerHTML", {
      set(h) {
        n.kids = []; n.html = h;
        h.replace(/<input([^>]*)>/g, (_, at2) => { const x = attrs(at2); n.kids.push({ dataset: { ack: x["data-ack"] }, checked: false }); });
      }, get() { return n.html || ""; } });
    n.querySelector = (q) => { const m = /^\[data-ack="(.+)"\]$/.exec(q); return m ? n.kids.find((k) => k.dataset.ack === m[1]) || null : null; };
  }
  return n;
}
function makeHost() {
  const host = { nodes: [] };
  Object.defineProperty(host, "innerHTML", {
    set(h) {
      host.nodes = [];
      let cur = null;
      h.replace(/<(div|select|input|button)([^>]*)>/g, (_, tag, at) => {
        const x = attrs(at);
        const n = node(tag, x, cur);
        if (tag === "div" && (x.class || "") === "ht-ftk") cur = n;
        host.nodes.push(n);
      });
    }, get() { return ""; } });
  host.querySelector = function (q) {
    let m;
    if ((m = /^#(.+)$/.exec(q))) return host.nodes.find((n) => n.id === m[1]) || null;
    if ((m = /^\.ht-ftk\[data-k="(.+)"\]$/.exec(q))) return host.nodes.find((n) => n.cls === "ht-ftk" && n.dataset.k === m[1]) || null;
    if ((m = /^\[data-(st|load|gen|copy|dup)="(.+)"\]$/.exec(q))) return host.nodes.find((n) => n.dataset[m[1]] === m[2]) || null;
    return null;
  };
  return host;
}
// A select's value must follow selectedIndex the way a browser does.
function pick(sel, value) { sel.value = value; sel.selectedIndex = sel.options.findIndex((o) => o.value === value); }

const calls = [];
const replies = {
  "/ext/p/connections": { connections: [{ id: "ws1", label: "Shop" }] },
  "/ext/p/accounts": { accounts: [{ id: "acc9", username: "shop", platform: "tiktok" }] },
  "/ext/p/mixed": { accounts: [{ id: "ig1", username: "shop.ig", platform: "instagram" }] },
};
const api = async (url, opts) => { calls.push({ url, opts }); return replies[url]; };
const window = { t: (k, v) => k + (v ? ":" + JSON.stringify(v) : ""), crypto: require("crypto").webcrypto };
const esc = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
const fd = (o) => ({ form: o });
const drawTokenForm = new Function("api", "fd", "esc", "window", "infoBtn", "infoBody",
  SRC + "\nreturn drawTokenForm;")(api, fd, esc, window, () => "", (h) => "<div>" + h + "</div>");

const FORM = { fields: [
  { key: "connection_id", type: "select", label: "WS", send: true, required: false, initial: "meta.connection_id",
    options: { url: "/ext/p/connections", list: "connections", value: "id", label: "{label}", from: [], fill: {}, auto_single: true } },
  { key: "api_key", type: "password", label: "API key", send: true, required: false, required_unless: "connection_id", hidden_when: "connection_id" },
  { key: "account", type: "select", label: "Acc", send: false, required: false,
    options: { url: "/ext/p/accounts", list: "accounts", value: "id", label: "@{username} ({platform})",
               from: ["connection_id", "api_key"], fill: { account_id: "id", username: "username" }, auto_single: false } },
  { key: "account_id", type: "text", label: "Account ID", send: true, required: true, initial: "meta.account_id" },
  { key: "username", type: "text", label: "Username", send: true, required: true, initial: "external_id" },
  { key: "secret", type: "password", label: "Secret", send: true, required: false, generate: true },
] };
// One workspace whose only account is Instagram, which Messenger (a core channel) already answers.
const DUP_FORM = { fields: [
  { key: "connection_id", type: "select", label: "WS", send: true, required: true, initial: "meta.connection_id",
    options: { url: "/ext/p/connections", list: "connections", value: "id", label: "{label}", from: [], fill: {}, auto_single: true } },
  { key: "account_id", type: "select", label: "Acc", send: true, required: true, initial: "meta.account_id",
    options: { url: "/ext/p/mixed", list: "accounts", value: "id", label: "@{username}", from: ["connection_id"],
               fill: {}, auto_single: true, network: "platform" } },
] };
const COVERED = { instagram: "Messenger", facebook: "Messenger" };
const tick = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  // ---- Add form ----
  const h = makeHost();
  const f = drawTokenForm(h, FORM, null);
  await tick(); await tick(); await tick();
  const q = (k) => h.querySelector("#htF_" + k);
  check("1. connection list loaded by GET", calls[0] && calls[0].url === "/ext/p/connections" && !calls[0].opts);
  check("1. auto_single picked the only workspace", q("connection_id").value === "ws1", q("connection_id").value);
  check("2. API key hidden while a workspace is chosen", h.querySelector('.ht-ftk[data-k="api_key"]').hidden === true);
  const post = calls.find((c) => c.url === "/ext/p/accounts");
  check("3. dependent list POSTed with the workspace", post && post.opts.method === "POST" && post.opts.body.form.connection_id === "ws1",
        JSON.stringify(post));
  check("3. key never in the URL", calls.every((c) => !/api_key|ws1/.test(c.url)));
  let threw = "";
  try { f.token(); } catch (e) { threw = e.message; }
  check("4. missing required fields throw", /Account ID/.test(threw) && /Username/.test(threw) && !/API key/.test(threw), threw);
  pick(q("account"), "acc9"); q("account").onchange();
  check("3. fill copied account id and username", q("account_id").value === "acc9" && q("username").value === "shop");
  q("secret").value = "s3cret"; q("secret").oninput();
  const tok = JSON.parse(f.token());
  check("4. one JSON token, send:false left out", JSON.stringify(tok) === JSON.stringify(
    { connection_id: "ws1", account_id: "acc9", username: "shop", secret: "s3cret" }), JSON.stringify(tok));

  // No workspace: the API key shows again and becomes required.
  pick(q("connection_id"), ""); q("connection_id").onchange();
  check("2. API key shown without a workspace", h.querySelector('.ht-ftk[data-k="api_key"]').hidden === false);
  threw = ""; try { f.token(); } catch (e) { threw = e.message; }
  check("2. API key required without a workspace", /API key/.test(threw), threw);

  // ---- Edit form ----
  calls.length = 0;
  const h2 = makeHost();
  const acc = { external_id: "shop", meta: { account_id: "acc9", connection_id: "ws1" } };
  const g = drawTokenForm(h2, FORM, acc);
  await tick(); await tick();
  const q2 = (k) => h2.querySelector("#htF_" + k);
  check("5. edit starts from the saved account", q2("account_id").value === "acc9" && q2("username").value === "shop");
  check("5. edit selects the saved workspace", q2("connection_id").value === "ws1", q2("connection_id").value);
  check("5. saved workspace hides the API key", h2.querySelector('.ht-ftk[data-k="api_key"]').hidden === true);
  check("5. untouched edit sends no token", g.token() === "");
  q2("secret").value = "new"; q2("secret").oninput();
  const t2 = JSON.parse(g.token());
  check("5. changing only the secret keeps the workspace", t2.connection_id === "ws1" && t2.secret === "new" && t2.account_id === "acc9",
        JSON.stringify(t2));

  // ---- Generated secret ----
  const h3 = makeHost();
  const k3 = drawTokenForm(h3, FORM, null);
  await tick(); await tick();
  const s3 = h3.querySelector("#htF_secret");
  check("6. generate button drawn", !!h3.querySelector('[data-gen="secret"]') && !!h3.querySelector('[data-copy="secret"]'));
  check("6. no generate button on plain fields", !h3.querySelector('[data-gen="account_id"]'));
  h3.querySelector('[data-gen="secret"]').onclick();
  const v1 = s3.value;
  check("6. 64 hex chars", /^[0-9a-f]{64}$/.test(v1), v1);
  check("6. shown after generating", s3.type === "text");
  h3.querySelector('[data-gen="secret"]').onclick();
  check("6. a new value each press", s3.value !== v1 && /^[0-9a-f]{64}$/.test(s3.value));
  h3.querySelector("#htF_account_id").value = "a"; h3.querySelector("#htF_username").value = "u";
  check("6. generated secret is sent", JSON.parse(k3.token()).secret === s3.value);
  const h4 = makeHost();
  const k4 = drawTokenForm(h4, FORM, { external_id: "shop", meta: { account_id: "acc9", connection_id: "ws1" } });
  await tick(); await tick();
  h4.querySelector('[data-gen="secret"]').onclick();
  check("6. edit + generate posts the new secret", JSON.parse(k4.token()).secret === h4.querySelector("#htF_secret").value);

  // ---- Duplicate warning ----
  const h5 = makeHost();
  const k5 = drawTokenForm(h5, DUP_FORM, null, null, COVERED);
  await tick(); await tick(); await tick();
  const acc5 = h5.querySelector("#htF_account_id"), dup5 = h5.querySelector('[data-dup="account_id"]');
  check("7. a covered account is not picked by itself, even when it is the only one", acc5.value === "", acc5.value);
  check("7. the covered option is marked in the list", /ht\.dup_option/.test(acc5.options[1] && acc5.options[1].text),
        acc5.options[1] && acc5.options[1].text);
  check("7. no warning before a pick", dup5.hidden === true);
  pick(acc5, "ig1"); acc5.onchange();
  check("7. picking it shows the warning", dup5.hidden === false && /ht\.dup_title/.test(dup5.innerHTML) && /Messenger/.test(dup5.innerHTML));
  threw = ""; try { k5.token(); } catch (e) { threw = e.message; }
  check("7. no token while the box is unticked", /ht\.dup_need_ack/.test(threw), threw);
  dup5.querySelector('[data-ack="account_id"]').checked = true;
  check("7. ticked: token given and the network acknowledged", JSON.parse(k5.token()).account_id === "ig1" && k5.ackedNetwork() === "instagram");
  pick(acc5, ""); acc5.onchange();
  check("7. unpicking hides the warning", dup5.hidden === true && k5.ackedNetwork() === "");
  // Without covered networks (no core channel answers Instagram), nothing changes: the only account is picked.
  const h6 = makeHost();
  drawTokenForm(h6, DUP_FORM, null, null, {});
  await tick(); await tick(); await tick();
  check("7. uncovered network keeps auto_single", h6.querySelector("#htF_account_id").value === "ig1");
  // Edit of an account already saved on Instagram: the saved pick is not asked again.
  const h7 = makeHost();
  const k7 = drawTokenForm(h7, DUP_FORM, { external_id: "shop.ig", meta: { account_id: "ig1", connection_id: "ws1" } }, null, COVERED);
  await tick(); await tick(); await tick(); await tick();
  check("7. edit restores the saved covered account", h7.querySelector("#htF_account_id").value === "ig1");
  check("7. edit of the saved pick shows no warning", h7.querySelector('[data-dup="account_id"]').hidden === true && k7.ackedNetwork() === "");

  console.log("\n" + (fails.length ? fails.length + " FAIL" : "ALL OK"));
  process.exit(fails.length ? 1 : 0);
})();
