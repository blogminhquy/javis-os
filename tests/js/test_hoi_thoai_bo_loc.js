/* Bộ lọc của Hộp thư hội thoại: phần thuần chạy thật dưới node, phần vẽ canh bằng cấu trúc mã.

       node tests/js/test_hoi_thoai_bo_loc.js

   0.65.3 (chủ dự án 2026-09-30): nhiều bot thì hộp thư lẫn vào nhau, cần lọc mà không tốn diện tích. Since Chatbot v5
   (2026-10-28, docs/dev/2026-10-chatbot-v5-spec.md section 6) the controls are the channel picker (tick several nicks
   and Pages), the quick "who is handling it" filters and the two-level Filter menu. Three things are guarded:
     1. `conversations-filters.js` runs for real: odd values become "no filter", a broken or blocked browser store still
        works, an old saved status moves to the matching quick filter, the query is built right and escaped.
     2. `conversations.js`: the list head (picker, search + Filter, quick filters, chips), popovers that the 5-second
        refresh never redraws, filters saved then reloaded, "opened from elsewhere" clears what could hide the chat.
     3. Dictionary: every `ib.*` key used by the inbox has vi and en; no orphan `ht.f_*` key.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const MOD = src("dashboard/conversations-filters.js");
const V5 = src("dashboard/inbox-v5.js");
const CV = src("dashboard/conversations.js");
const HTML = src("dashboard/index.html");
const CSS = src("dashboard/inbox-v5.css");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

// ---- nạp module với window giả ----
const store = {};
const win = {
  t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : ""),
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
};
const ctx = { window: win, console, encodeURIComponent, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(MOD, ctx);
const F = win.JavisConvFilters;
check("module phơi ra đủ hàm", F && ["emptyState", "sanitize", "load", "save", "activeCount", "query", "tagChips", "tagChip",
  "rowMenuItems", "rowMenuHtml", "tagMenuHtml"].every((k) => typeof F[k] === "function"));
check("dropdown builders of the pre-v5 filter row are gone", ["botOptions", "statusOptions", "typeOptions", "channelOptions",
  "tagOptions", "contactLabel", "botColor"].every((k) => !(k in F)));

// ---- 1. hàm thuần ----
const EMPTY = '{"bot":"","status":"","type":"","channel":"","contact":"","who":"","accs":[],"tagsAny":[],"tagsNone":[],"when":null,"lastBy":"","pinned":""}';
check("trạng thái rỗng", JSON.stringify(F.emptyState()) === EMPTY, JSON.stringify(F.emptyState()));
check("giá trị lạ về không lọc (tình trạng, loại, who không nằm trong bảng)",
  F.sanitize({ bot: "b1", status: "hack", type: "??", channel: "zalo", who: "boss" }).status === "" &&
  F.sanitize({ status: "hack", type: "??" }).type === "" && F.sanitize({ who: "boss" }).who === "" && F.sanitize({ bot: "b1" }).bot === "b1");
check("kiểu sai không làm sập", F.sanitize(null).bot === "" && F.sanitize("x").status === "" && F.sanitize({ bot: 5 }).bot === "" &&
  F.sanitize({ accs: "a" }).accs.length === 0 && F.sanitize({ tagsAny: [{}] }).tagsAny.length === 0);
check("giữ giá trị hợp lệ", JSON.stringify(F.sanitize({ bot: "-", status: "unread", type: "group", channel: "telegram", who: "ai",
  accs: ["zalo:1", "zalo:1", "telegram:acc_9"], tagsAny: ["7"], tagsNone: ["8", "x"] }))
  === '{"bot":"-","status":"unread","type":"group","channel":"telegram","contact":"","who":"ai","accs":["zalo:1","telegram:acc_9"],"tagsAny":["7"],"tagsNone":["8"],"when":null,"lastBy":"","pinned":""}');
check("an old saved status moves to the matching quick filter (need_reply = Needs you, human = You are handling)",
  F.sanitize({ status: "need_reply" }).who === "you" && F.sanitize({ status: "need_reply" }).status === "" &&
  F.sanitize({ status: "human" }).who === "owner" && F.sanitize({ status: "human" }).status === "");
check("an old saved single tag becomes a 'has tag' filter", JSON.stringify(F.sanitize({ tag: "7" }).tagsAny) === '["7"]' &&
  !("tag" in F.sanitize({ tag: "7" })));
check("an account key with odd characters is dropped", F.sanitize({ accs: ["zalo:1", "a b", "<x>"] }).accs.join() === "zalo:1");
// Owner, 2026-10-28 ("lọc như kia hơi ít"): when the last message came, who wrote it, pinned only.
check("a time filter keeps a known quick range or two real dates (swapped when backwards), drops the rest",
  JSON.stringify(F.sanitize({ when: { preset: "d30" } }).when) === '{"preset":"d30"}' && F.sanitize({ when: { preset: "d999" } }).when === null &&
  JSON.stringify(F.sanitize({ when: { from: "2026-10-09", to: "2026-10-01" } }).when) === '{"from":"2026-10-01","to":"2026-10-09"}' &&
  F.sanitize({ when: { from: "x", to: "2026-10-01" } }).when === null && F.sanitize({ when: "d7" }).when === null);
check("'last message by' takes customer, A.I. or you; pinned is on or off", F.sanitize({ lastBy: "ai" }).lastBy === "ai" &&
  F.sanitize({ lastBy: "boss" }).lastBy === "" && F.sanitize({ pinned: "1" }).pinned === "1" && F.sanitize({ pinned: "yes" }).pinned === "");
check("the new filters count in the Filter button", F.activeCount({ when: { preset: "d7" }, lastBy: "customer", pinned: "1" }) === 3);
const q2 = F.query({ when: { from: "2026-10-01", to: "2026-10-09" }, lastBy: "customer", pinned: "1" });
check("query: from/to as days, last_by, pinned=1", /&from=2026-10-01&to=2026-10-09/.test(q2) && /&last_by=customer/.test(q2) && /&pinned=1/.test(q2));
F.save({ bot: "b1", status: "unread", type: "private", channel: "", who: "" });
check("lưu rồi đọc lại đúng (chosen 'All' stays All)", JSON.stringify(F.load()) ===
  '{"bot":"b1","status":"unread","type":"private","channel":"","contact":"","who":"","accs":[],"tagsAny":[],"tagsNone":[],"when":null,"lastBy":"","pinned":""}');
store["javis.inbox.filters"] = JSON.stringify({ bot: "b1" });
check("nothing saved about who yet (first visit, pre-v5 browser): opens on Needs you", F.load().who === "you" && F.load().bot === "b1");
store["javis.inbox.filters"] = "không phải json";
check("dữ liệu lưu hỏng thì về không lọc (mở ở Cần bạn), không sập", JSON.stringify(F.load()) === EMPTY.replace('"who":""', '"who":"you"'));
store["javis.inbox.filters"] = JSON.stringify({ status: "hack" });
check("dữ liệu lưu có giá trị lạ thì bỏ giá trị đó", F.load().status === "");
const oldLs = win.localStorage;
win.localStorage = { getItem() { throw new Error("chặn"); }, setItem() { throw new Error("chặn"); } };
check("bộ nhớ trình duyệt bị chặn: đọc và ghi không ném lỗi", (function () {
  try { F.save({ bot: "x" }); return F.load().who === "you" && F.load().bot === ""; } catch (e) { return false; }
})());
win.localStorage = oldLs;

check("Filter count: what the Filter menu holds (who and the picker have their own controls)", F.activeCount({}) === 0 &&
  F.activeCount({ bot: "b", status: "unread" }) === 2 && F.activeCount({ bot: "b", status: "unread", type: "group", channel: "x" }) === 4 &&
  F.activeCount({ status: "hack" }) === 0 && F.activeCount({ who: "you", accs: ["zalo:1"] }) === 0 &&
  F.activeCount({ tagsAny: ["1", "2"], tagsNone: ["3"], contact: "1" }) === 4);
check("query chỉ gồm khoá đang lọc", F.query({}) === "" && F.query({ status: "unread" }) === "&status=unread" &&
  F.query({ bot: "b1", type: "group" }) === "&bot_id=b1&chat_type=group" && F.query({ who: "you" }) === "&who=you");
check("query: waiting longest = need reply sorted waiting-first; phone/email is its own flag",
  F.query({ status: "waiting" }) === "&status=need_reply&sort=waiting" && F.query({ contact: "1" }) === "&has_contact=1");
check("query: picked accounts and tags go as comma lists", F.query({ accs: ["zalo:1", "telegram:acc_9"], tagsAny: ["1", "2"], tagsNone: ["3"] }) ===
  "&account_ids=zalo%3A1%2Ctelegram%3Aacc_9&tags_any=1,2&tags_none=3");
check("query thoát ký tự lạ trong id bot", F.query({ bot: "a&b=c d" }) === "&bot_id=a%26b%3Dc%20d");
check("query bỏ giá trị lạ của tình trạng (không gửi lên server)", F.query({ status: "hack", who: "x" }) === "");

// ---- 2. hợp đồng với conversations.js ----
check("list head: search with the Filter button, the who dropdown and the channel picker, active chips, three popovers",
  ["ht-search", "ib-fbtn", "ib-whobtn", "ib-picker", "ib-activef", "ib-pop ib-wm", "ib-pop ib-pk", "ib-pop ib-fm"].every((c) => CV.indexOf('class="' + c) > 0));
check("KHÔNG còn hàng dropdown cũ (bot, tình trạng, loại, kênh, thẻ) và chip tài khoản",
  !/ht-f-bot|ht-f-status|ht-f-type|ht-f-channel|ht-f-tag|ht-f-contact|ht-fclear|ht-loc-tk|_tkLoc|_tagLoc/.test(CV) && !/function paintFilters/.test(CV));
check("gửi tham số lọc lên server qua JavisConvFilters.query", /JavisConvFilters\.query\(filterState\(\)\)/.test(CV) &&
  !/"&bot_id=" \+ encodeURIComponent\(_botLoc\)/.test(CV) && !/&account_id=/.test(CV));
check("đọc facets, bot, who_counts từ server, dùng cho cả nhịp làm mới", /_facets = d\.facets \|\| null/.test(CV) &&
  /_botList = d\.bots \|\| \[\]/.test(CV) && /if \(d\.who_counts\) _whoCounts = d\.who_counts/.test(CV) &&
  /JSON\.stringify\(\[_items, _stats, _facets, _botList, _conDS, _tags, _whoCounts\]\)/.test(CV));
check("the popovers redraw only on the owner's own actions, never on the 5-second refresh",
  /function paintPops\(\)/.test(CV) && !/function tai\(im\)[\s\S]*?paintPops\(\)[\s\S]*?\n  }\n/.test(CV.slice(CV.indexOf("async function tai(im)"), CV.indexOf("async function taiThem"))));
check("a who choice, a picker tick, a menu choice or a chip x saves the filters and reloads",
  /function onFilterChange\(\) \{ saveFilters\(\); paintHead\(\); tai\(\); \}/.test(CV) &&
  /_who = b\.dataset\.who \|\| "";\s*setPop\(""\);\s*onFilterChange\(\)/.test(CV) && /dropFilter\(b\.dataset\.k, b\.dataset\.v\);\s*onFilterChange\(\)/.test(CV) &&
  (CV.match(/onFilterChange\(\);\n\s*paintPops\(\);/g) || []).length >= 1 && /clearMenuFilters\(\);\n\s*paintPops\(\);/.test(CV));
check("ticking a channel ticks every nick or Page of it, not only the ones the search shows",
  /accList\(\)\.filter\(function \(a\) \{ return a\.channel === t\.dataset\.ch; \}\)/.test(CV));
check("khôi phục bộ lọc đã lưu khi mở hòm thư; mở từ nơi khác thì bỏ mọi bộ lọc có thể giấu cuộc chat",
  /JavisConvFilters\.load\(\)|F\.load\(\)/.test(CV) &&
  /_who = ""; _statusLoc = ""; _typeLoc = ""; _tagsAny = \[\]; _tagsNone = \[\]; _contactLoc = ""; _q = "";/.test(CV) &&
  /_accs = _cho\.account_key \? \[_cho\.account_key\] : \[\]/.test(CV));
check("Filter menu 'Clear' resets every filter of the menu", /_tagsAny = \[\]; _tagsNone = \[\]; _typeLoc = _botLoc = _statusLoc = _contactLoc = _lastBy = _pinned = ""; _when = null;/.test(CV));
check("Escape or a click outside closes a popover and gives focus back to its button", /function watchPopOutside\(\)/.test(CV) &&
  /ev\.key !== "Escape"/.test(CV) && /focusOpener\(from\)/.test(CV));
check("trạng thái rỗng tính cả bộ lọc mới, and only the quick filter hiding everything offers 'Show all'",
  /var loc = !!\(_q \|\| _kenhLoc \|\| _botLoc \|\| _accs\.length \|\| _statusLoc \|\| _typeLoc \|\| _tagsAny\.length \|\| _tagsNone\.length \|\| _contactLoc \|\|\s+_when \|\| _lastBy \|\| _pinned\)/.test(CV) &&
  /EMPTY_WHO\[_who\]/.test(CV) && /ib-see-all/.test(CV));
check("index.html nạp module lọc và inbox-v5 TRƯỚC conversations.js, kèm CSS", HTML.indexOf("conversations-filters.js") > 0 &&
  HTML.indexOf("conversations-filters.js") < HTML.indexOf("/static/conversations.js") &&
  HTML.indexOf("/static/inbox-v5.js") > 0 && HTML.indexOf("/static/inbox-v5.js") < HTML.indexOf("/static/conversations.js") &&
  HTML.indexOf("/static/inbox-v5.css") > 0);
check("CSS: popovers hide for real with [hidden]; the old chip row is gone", /\.ib-pop\[hidden\] \{ display: none; \}/.test(CSS) &&
  !/\.ib-quick|\.ib-q\b/.test(CSS) && !/ib-quick|quickHtml/.test(CV));

// ---- 3. từ điển ----
const used = new Set();
[MOD, V5, CV].forEach((t) => [...t.matchAll(/"((?:ib|ht\.f)[._][a-z_]+)"/g)].forEach((m) => used.add(m[1].replace(/^ht_/, "ht."))));
[...V5.matchAll(/"(ht\.f_[a-z_]+)"/g)].forEach((m) => used.add(m[1]));
const keys = [...used].filter((k) => !k.endsWith("_"));
const thieu = keys.filter((k) => !VI[k] || !EN[k]);
check(`mọi khoá ib.* và ht.f_* đang dùng (${keys.length}) có ở cả vi và en`, keys.length >= 100 && !thieu.length, thieu.join(","));
const htf = new Set([...V5.matchAll(/"(ht\.f_[a-z_]+)"/g), ...CV.matchAll(/"(ht\.f_[a-z_]+)"/g)].map((m) => m[1]));
check("không khoá ht.f_* nào mồ côi", Object.keys(VI).filter((k) => k.startsWith("ht.f_") && !htf.has(k)).length === 0,
  Object.keys(VI).filter((k) => k.startsWith("ht.f_") && !htf.has(k)).join(","));
check("Vietnamese inbox text writes A.I. with dots, never a bare 'AI'", Object.keys(VI).filter((k) => k.startsWith("ib.") &&
  /(^|[^.A-Za-z])AI([^.A-Za-z]|$)/.test(VI[k])).length === 0);
check("không dùng em dash trong module, test và phần mới", ![MOD, V5, fs.readFileSync(__filename, "utf8")].some((t) => t.indexOf(String.fromCharCode(0x2014)) >= 0));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_hoi_thoai_bo_loc: tất cả pass");
