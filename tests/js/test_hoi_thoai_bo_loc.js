/* Bộ lọc dropdown của Hộp thư hội thoại (0.65.3): phần thuần chạy thật dưới node, phần vẽ canh bằng cấu trúc mã.

       node tests/js/test_hoi_thoai_bo_loc.js

   Chủ dự án (2026-09-30): lọc bằng hàng nút bấm tốn diện tích, muốn dropdown. Ba thứ được canh:
     1. `conversations-filters.js` chạy thật: giá trị lạ về "không lọc", lưu trình duyệt hỏng vẫn chạy, query ghép đúng,
        <option> có số đếm và chọn sẵn đúng giá trị, giá trị người dùng/bot KHÔNG chèn được HTML.
     2. `conversations.js`: một hàng dropdown chung với ô tìm, không còn hàng chip kênh và ô chọn bot ẩn-khi-dưới-2-bot,
        dropdown đang mở không bị dựng lại giữa nhịp làm mới, thẻ tên bot chỉ khi có từ 2 bot, gửi đúng tham số.
     3. Từ điển: mọi khoá `ht.f_*` có ở cả vi và en, khoá của chip cũ không còn.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const MOD = src("dashboard/conversations-filters.js");
const CV = src("dashboard/conversations.js");
const HTML = src("dashboard/index.html");
const CSS = src("dashboard/console.css");
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
check("module phơi ra đủ hàm", F && ["emptyState", "sanitize", "load", "save", "activeCount", "query", "botColor",
  "botOptions", "statusOptions", "typeOptions", "channelOptions"].every((k) => typeof F[k] === "function"));

// ---- 1. hàm thuần ----
check("trạng thái rỗng", JSON.stringify(F.emptyState()) === '{"bot":"","status":"","type":"","channel":""}');
check("giá trị lạ về không lọc (tình trạng và loại không nằm trong bảng)",
  F.sanitize({ bot: "b1", status: "hack", type: "??", channel: "zalo" }).status === "" &&
  F.sanitize({ status: "hack", type: "??" }).type === "" && F.sanitize({ bot: "b1" }).bot === "b1");
check("kiểu sai không làm sập", F.sanitize(null).bot === "" && F.sanitize("x").status === "" && F.sanitize({ bot: 5 }).bot === "");
check("giữ giá trị hợp lệ", JSON.stringify(F.sanitize({ bot: "-", status: "need_reply", type: "group", channel: "telegram" }))
  === '{"bot":"-","status":"need_reply","type":"group","channel":"telegram"}');
F.save({ bot: "b1", status: "unread", type: "private", channel: "" });
check("lưu rồi đọc lại đúng", JSON.stringify(F.load()) === '{"bot":"b1","status":"unread","type":"private","channel":""}');
store["javis.inbox.filters"] = "không phải json";
check("dữ liệu lưu hỏng thì về không lọc, không sập", JSON.stringify(F.load()) === JSON.stringify(F.emptyState()));
store["javis.inbox.filters"] = JSON.stringify({ status: "hack" });
check("dữ liệu lưu có giá trị lạ thì bỏ giá trị đó", F.load().status === "");
const oldLs = win.localStorage;
win.localStorage = { getItem() { throw new Error("chặn"); }, setItem() { throw new Error("chặn"); } };
check("bộ nhớ trình duyệt bị chặn: đọc và ghi không ném lỗi", (function () {
  try { F.save({ bot: "x" }); return JSON.stringify(F.load()) === JSON.stringify(F.emptyState()); } catch (e) { return false; }
})());
win.localStorage = oldLs;

check("đếm bộ lọc đang bật", F.activeCount({}) === 0 && F.activeCount({ bot: "b", status: "unread" }) === 2 &&
  F.activeCount({ bot: "b", status: "unread", type: "group", channel: "x" }) === 4 && F.activeCount({ status: "hack" }) === 0);
check("query chỉ gồm khoá đang lọc", F.query({}) === "" && F.query({ status: "need_reply" }) === "&status=need_reply" &&
  F.query({ bot: "b1", type: "group" }) === "&bot_id=b1&chat_type=group");
check("query thoát ký tự lạ trong id bot", F.query({ bot: "a&b=c d" }) === "&bot_id=a%26b%3Dc%20d");
check("query bỏ giá trị lạ của tình trạng (không gửi lên server)", F.query({ status: "hack" }) === "");
check("màu thẻ bot: ổn định theo id và nằm trong 4 màu", F.botColor("bot_a") === F.botColor("bot_a") &&
  ["bot_a", "bot_b", "bot_c", "bot_d", "", null].every((id) => F.botColor(id) >= 0 && F.botColor(id) < 4));

const facets = { tong: 9, bots: { b1: { tong: 5 }, b2: { tong: 3 }, "": { tong: 1 } },
                 status: { unread: 4, need_reply: 2, human: 1 }, type: { group: 6, private: 3 } };
const bots = [{ id: "b2", name: "Nhi Mai", tong: 3 }, { id: "b1", name: "Javis Vũ", tong: 5 }];
const bo = F.botOptions(bots, facets, "");
check("dropdown bot: có Tất cả kèm tổng, từng bot kèm số, và 'chưa có bot trực'",
  bo.indexOf('ht.f_bot_all#9') > 0 && bo.indexOf("Javis Vũ (5)") > 0 && bo.indexOf("Nhi Mai (3)") > 0 &&
  bo.indexOf('value="-"') > 0 && bo.indexOf('ht.f_bot_none#1') > 0, bo);
check("dropdown bot sắp theo tên (Javis trước Nhi), không theo số đếm", bo.indexOf("Javis Vũ") < bo.indexOf("Nhi Mai"));
check("dropdown bot chọn sẵn đúng giá trị", /value="b2" selected/.test(F.botOptions(bots, facets, "b2")) &&
  !/value="b1" selected/.test(F.botOptions(bots, facets, "b2")) && /<option value="" selected>/.test(bo));
check("bot đang lọc mà chưa có hội thoại vẫn có lựa chọn (mở từ thẻ bot)",
  /value="b9" selected>ht\.f_bot_picked/.test(F.botOptions(bots, facets, "b9")));
check("không có cuộc chat không-bot thì không có lựa chọn '-'", F.botOptions(bots, { tong: 8, bots: { b1: { tong: 8 } } }, "").indexOf('value="-"') < 0);
check("tên bot do người dùng đặt KHÔNG chèn được HTML",
  F.botOptions([{ id: "b1", name: '<img src=x onerror=alert(1)>', tong: 1 }], facets, "").indexOf("<img") < 0 &&
  F.botOptions([{ id: 'b"1', name: "a", tong: 1 }], facets, "").indexOf('value="b"1"') < 0);

const so = F.statusOptions(facets, "need_reply");
check("dropdown tình trạng: Mọi tình trạng + ba lựa chọn kèm số, chọn sẵn đúng",
  so.indexOf("ht.f_st_all") > 0 && so.indexOf('ht.f_st_unread#4') > 0 && so.indexOf('ht.f_st_need#2') > 0 &&
  so.indexOf('ht.f_st_human#1') > 0 && /value="need_reply" selected/.test(so), so);
const to = F.typeOptions(facets, "group");
check("dropdown loại: nhóm và riêng kèm số", to.indexOf('ht.f_type_group#6') > 0 && to.indexOf('ht.f_type_private#3') > 0 &&
  /value="group" selected/.test(to));
check("thiếu facets (server cũ) thì không sập, số là 0", F.statusOptions(null, "").indexOf('#0') > 0 &&
  F.typeOptions(undefined, "").indexOf('#0') > 0 && F.botOptions([], null, "").indexOf("ht.f_bot_all") > 0);
const co = F.channelOptions({ telegram: 4, zalo_personal: 5 }, "", (id) => "Nhãn " + id);
check("dropdown kênh: nhãn do server cấp kèm số", co.indexOf("Nhãn telegram (4)") > 0 && co.indexOf("Nhãn zalo_personal (5)") > 0);
check("kênh đang lọc mà không còn hội thoại vẫn có lựa chọn", /value="zalo" selected/.test(F.channelOptions({ telegram: 1 }, "zalo")));

// ---- 2. hợp đồng với conversations.js ----
check("hòm thư có MỘT hàng dropdown chung với ô tìm (bot, tình trạng, loại, kênh)",
  /class="ht-search"/.test(CV) && ["ht-f-bot", "ht-f-status", "ht-f-type", "ht-f-channel"].every((c) => CV.indexOf('class="ht-f ' + c + '"') > 0));
check("KHÔNG còn hàng chip kênh và ô chọn bot cũ", !/ht-loc-chip\[data-k\]/.test(CV) && !/function veChonBot/.test(CV) &&
  !/class="ht-bot"/.test(CV) && !/ht\.moi_bot/.test(CV) && !/ht\.tat_ca/.test(CV));
check("dropdown kênh ẩn khi hòm thư dưới 2 kênh", /ch\.hidden = Object\.keys\(_stats\.theo_kenh \|\| \{\}\)\.length < 2 && !st\.channel/.test(CV));
check("gửi tham số lọc lên server qua JavisConvFilters.query", /JavisConvFilters\.query\(filterState\(\)\)/.test(CV) &&
  !/"&bot_id=" \+ encodeURIComponent\(_botLoc\)/.test(CV));
check("đọc facets và danh sách bot từ server, dùng cho cả nhịp làm mới", /_facets = d\.facets \|\| null/.test(CV) &&
  /_botList = d\.bots \|\| \[\]/.test(CV) && /JSON\.stringify\(\[_items, _stats, _facets, _botList\]\)/.test(CV));
check("dropdown ĐANG MỞ không bị dựng lại giữa nhịp tự làm mới", /document\.activeElement !== sel && sel\.dataset\.sig !== html\[k\]/.test(CV));
check("chọn dropdown thì lưu bộ lọc ở trình duyệt rồi tải lại", /function onFilterChange\(\) \{ saveFilters\(\); tai\(\); \}/.test(CV) &&
  ["_botLoc", "_statusLoc", "_typeLoc", "_kenhLoc"].every((v) => new RegExp(v + " = e\\.target\\.value; onFilterChange\\(\\)").test(CV)));
check("khôi phục bộ lọc đã lưu khi mở hòm thư; mở từ nơi khác thì bỏ tình trạng và loại đã lưu",
  /JavisConvFilters\.load\(\)/.test(CV) && /_statusLoc = ""; _typeLoc = "";/.test(CV));
check("nút Xoá lọc reset cả bốn dropdown lẫn chip tài khoản", /_botLoc = _statusLoc = _typeLoc = _kenhLoc = _tkLoc = ""/.test(CV) &&
  /class="ht-fclear" hidden/.test(CV));
check("dòng tóm tắt nói số hội thoại và số bộ lọc", /ht\.f_count_f/.test(CV) && /ht\.f_count"/.test(CV));
check("thẻ tên bot trên hàng chỉ khi có từ 2 bot; tình trạng 'Cần trả lời' và 'Tôi lo' cùng một dòng thẻ",
  /_botList\.length >= 2 && c\.bot_name/.test(CV) && /class="ht-bot-tag c'/.test(CV) && /c\.need_reply/.test(CV) &&
  /ht-item-tags/.test(CV));
check("tên bot do server trả được thoát HTML trước khi vẽ", /esc\(c\.bot_name\)/.test(CV));
check("trạng thái rỗng tính cả bộ lọc mới", /_q \|\| _kenhLoc \|\| _botLoc \|\| _tkLoc \|\| _statusLoc \|\| _typeLoc/.test(CV));
check("index.html nạp module lọc TRƯỚC conversations.js", HTML.indexOf("conversations-filters.js") > 0 &&
  HTML.indexOf("conversations-filters.js") < HTML.indexOf("/static/conversations.js"));
check("CSS: dropdown bị ẩn thật khi có thuộc tính hidden, và có bố cục điện thoại",
  /\.ht-f\[hidden\], \.ht-fclear\[hidden\] \{ display: none; \}/.test(CSS) && /\.ht-f \{ flex: 1 1 42%; font-size: 16px; \}/.test(CSS) && /\.ht-search, \.ht-f-bot, \.ht-f-channel \{ flex-basis: 100%; \}/.test(CSS));
check("CSS: hàng của bot/ô tìm/kênh đặt SAU quy tắc .ht-f (thứ tự quyết định độ rộng trên điện thoại)",
  CSS.indexOf(".ht-f { flex: 1 1 42%") > 0 && CSS.indexOf(".ht-f { flex: 1 1 42%") < CSS.indexOf(".ht-search, .ht-f-bot, .ht-f-channel"));
check("CSS: bốn màu thẻ bot và thẻ cần trả lời", [0, 1, 2, 3].every((i) => CSS.indexOf(".ht-bot-tag.c" + i) > 0) && /\.ht-need \{/.test(CSS));

// ---- 3. từ điển ----
const dung = new Set([...MOD.matchAll(/"(ht\.f_[a-z_]+)"/g)].map((m) => m[1]));
[...CV.matchAll(/"(ht\.(?:f_[a-z_]+|tag_need))"/g)].forEach((m) => dung.add(m[1]));
const thieu = [...dung].filter((k) => !VI[k] || !EN[k]);
check(`mọi khoá ht.f_* và ht.tag_need đang dùng (${dung.size}) có ở cả vi và en`, dung.size >= 18 && !thieu.length, thieu.join(","));
check("khoá của chip cũ đã bỏ khỏi từ điển", !("ht.moi_bot" in VI) && !("ht.tat_ca" in VI) && !("ht.moi_bot" in EN) && !("ht.tat_ca" in EN));
check("không khoá ht.f_* nào mồ côi", Object.keys(VI).filter((k) => k.startsWith("ht.f_") && !dung.has(k)).length === 0,
  Object.keys(VI).filter((k) => k.startsWith("ht.f_") && !dung.has(k)).join(","));
check("mọi dropdown có nhãn cho trình đọc màn hình", ["ht.f_aria_bot", "ht.f_aria_status", "ht.f_aria_type", "ht.f_aria_kenh"]
  .every((k) => CV.indexOf('"' + k + '"') > 0 && VI[k] && EN[k]));
check("không dùng em dash trong module, test và phần mới", ![MOD, fs.readFileSync(__filename, "utf8")].some((t) => t.indexOf(String.fromCharCode(0x2014)) >= 0));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_hoi_thoai_bo_loc: tất cả pass");
