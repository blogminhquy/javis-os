/* Tap a quote to scroll back to the words it quotes (quote-jump.js). Run by hand or in CI:
       node tests/js/test_quote_jump.js
   Owner, 2026-11-14: in a long answer there are a few spots to ask more about; quote them, and a tap on that quote should
   scroll back to the exact sentence quoted. The search runs over the messages above, nearest first, folds away spaces,
   punctuation, markdown marks, case and accents, and loads older pages when the source is not on screen.
   Note: never use the em dash character anywhere. */
const fs = require("fs");
const path = require("path");
const J = require("../../dashboard/quote-jump.js");
const Q = require("../../dashboard/chat-quote.js");
const order = require("./_thu_tu_nap.js");

const ROOT = path.join(__dirname, "../..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");

const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- 1. Folding: only letters and digits, lower case, no accents ----
check("fold drops spaces, punctuation and markdown marks", J.fold("**Giá sỉ:** 45k, (một chai)!") === "giasi45kmotchai", J.fold("**Giá sỉ:** 45k, (một chai)!"));
check("fold keeps đ as a letter", J.fold("Đường đi") === "đuongđi", J.fold("Đường đi"));
check("fold reads composed and decomposed accents the same", J.fold("Tiếng Việt") === J.fold("Tiếng Việt".normalize("NFD")));
check("fold of nothing is empty", J.fold("") === "" && J.fold(null) === "" && J.fold("\u2014 \u2026 !!") === "");

// ---- 2. The words a markdown quote shows on screen ----
const md = "## Kết luận\n\n1. Giá **sỉ** là 45k\n- [x] Xem [bảng giá](https://x.vn/gia) ngay\n> trích\n" +
  "![ảnh](a.png) ![[b.png]] [[Ghi chú|ghi chú hay]]\n```js\nlet a = 1;\n```\n<!-- JAVIS_CARD: {\"x\":1} -->";
const v = J.fold(J.visible(md));
check("visible drops heading, list number, bullet, checkbox and quote marks", v.indexOf("ketluangiasila45kxembanggia") === 0, v);
check("visible keeps a link's label and drops its target", v.includes("banggia") && !v.includes("https") && !v.includes("xvn"), v);
check("visible drops pictures and keeps a wikilink's label", !v.includes("png") && v.includes("ghichuhay") && !v.includes("ghichughi"), v);
check("visible drops code fence markers (the language label) but keeps the code", v.includes("leta1") && !v.includes("jsleta"), v);
check("visible drops hidden blocks", !v.includes("javis") && !v.includes("card"), v);

// ---- 3. Where the quote sits ----
const hay = J.fold("Mở đầu. Giá sỉ là 45k một chai, lấy từ 100 chai giảm thêm 5%. Phí ship tính riêng theo tỉnh.");
const exact = J.findSpan(hay, J.fold("lấy từ 100 chai giảm thêm 5%"), false);
check("exact match: start and end of the quoted words", exact && exact.exact && hay.slice(exact.start, exact.end) === J.fold("lấy từ 100 chai giảm thêm 5%"), JSON.stringify(exact));
check("no match: null", J.findSpan(hay, J.fold("không có câu này"), true) === null);
check("empty quote or message: null", J.findSpan("", "a", true) === null && J.findSpan("abc", "", true) === null);
const longText = "Câu đầu tiên của đoạn trích dài, nói về giá sỉ và chính sách chiết khấu cho đại lý cấp một. " +
  "Câu thứ hai nói về thời gian giao hàng và phí vận chuyển theo từng vùng miền trong cả nước.";
const pageText = J.fold(longText.replace("cấp một.", "cấp một. [Bảng 1]"));   // the page shows a word the quote does not
const loose = J.findSpan(pageText, J.fold(longText), true);
check("loose match: first and last words found, the span covers the whole quote", loose && !loose.exact
  && loose.start === 0 && loose.end === pageText.length, JSON.stringify(loose));
check("loose match is only tried when asked", J.findSpan(pageText, J.fold(longText), false) === null);
const cut = J.fold(Q.dinhDang(longText + " " + "thêm chữ ".repeat(300)).replace(/^> /gm, ""));
const pageLong = J.fold(longText + " " + "thêm chữ ".repeat(300));
const cs = J.findSpan(pageLong, cut, true);
check("a quote cut with … (chat-quote.js) is still found from its start", cs && cs.start === 0, JSON.stringify(cs));
check("a short quote never matches loosely", J.findSpan(J.fold("abc def"), J.fold("abc xyz"), true) === null);

// ---- 4. The DOM: folded text of a message and a range on the exact words ----
let docRanges = [];
const fakeDoc = {
  createRange() {
    const r = { setStart(n, o) { r.sn = n; r.so = o; }, setEnd(n, o) { r.en = n; r.eo = o; } };
    docRanges.push(r);
    return r;
  }
};
function txt(s) { return { nodeType: 3, data: s, ownerDocument: fakeDoc }; }
function el(tag, cls, kids) {
  const e = { nodeType: 1, tagName: tag.toUpperCase(), cls: (cls || "").split(" ").filter(Boolean), ownerDocument: fakeDoc };
  e.matches = (sel) => sel.split(",").map(x => x.trim()).some(x => x === tag || (x[0] === "." && e.cls.includes(x.slice(1)))
    || (x.startsWith("[aria-hidden") && false));
  (kids || []).forEach((k, i, a) => { k.parentNode = e; k.nextSibling = a[i + 1] || null; });
  e.firstChild = (kids || [])[0] || null;
  e.querySelector = (sel) => sel === ".bubble" ? (kids || []).find(k => k.cls && k.cls.includes("bubble")) || null : null;
  return e;
}
const strong = txt("45k");
const tail = txt(" một chai, lấy 100 chai giảm 5%.");
const answer = el("div", "msg msg-javis", [el("div", "bubble", [
  el("p", "", [txt("Giá sỉ là "), el("strong", "", [strong]), tail]),
  el("div", "code-head", [txt("python")]),
  el("button", "code-copy", [txt("Copy")])
])]);
const map = J.textMap([answer.querySelector(".bubble")], "button, .code-head");
check("textMap folds the words across tags and leaves buttons and code labels out", map.text === J.fold("Giá sỉ là 45k một chai, lấy 100 chai giảm 5%."), map.text);
check("textMap keeps one source position per folded character", map.nodes.length === map.text.length && map.offs.length === map.text.length);
docRanges = [];
const hit = J.locate([answer], J.fold(J.visible("Giá sỉ là **45k** một chai")), (e) => [e.querySelector(".bubble")], "button");
const r = docRanges[0];
check("locate finds the message and the exact words, across the bold", hit && hit.el === answer && hit.exact
  && r.so === 0 && r.en === tail && r.eo === " một chai".length, JSON.stringify({ so: r && r.so, eo: r && r.eo, same: r && r.en === tail }));
const user = el("div", "msg msg-user", [el("div", "bubble", [el("div", "utext", [el("span", "uquote", [txt("lấy 100 chai giảm 5%")]), txt("Còn 200 chai?")])])]);
const near = J.locate([user, answer], J.fold("lấy 100 chai giảm 5%"), (e) => [e.querySelector(".bubble")], "button, .uquote");
check("an earlier message's own quote block is not the source; the answer is", near && near.el === answer);
const twoMsgs = J.locate([el("div", "msg", [el("div", "bubble", [txt("Giá sỉ là 45k một chai ở kho Hà Nội, nhưng còn thêm phí")])]), answer],
  J.fold("Giá sỉ là 45k một chai, lấy 100 chai giảm 5%"), (e) => [e.querySelector(".bubble")], "button");
check("an exact match further up wins over a loose one nearer", twoMsgs && twoMsgs.el === answer && twoMsgs.exact);

// ---- 5. Messages above the tapped one, nearest first ----
function posEl(i) { return { i, compareDocumentPosition(o) { return o.i < this.i ? 2 : 4; } }; }
const list = [posEl(0), posEl(1), posEl(2), posEl(3)];
check("before: only the messages above, nearest first", J.before(list, list[2]).map(x => x.i).join() === "1,0");
check("before: a message not in the list (a pending one) searches everything above it",
  J.before(list.slice(0, 3), posEl(9)).map(x => x.i).join() === "2,1,0");

// ---- 6. go(): load older pages when needed, give up with a note ----
global.document = { body: { appendChild() {} }, createElement() { return { setAttribute() {}, remove() {} }; } };
global.window = undefined;
(async () => {
  let loads = 0;
  const notFound = await J.go({ quote: "câu không có", candidates: () => [answer], roots: (e) => [e.querySelector(".bubble")],
    loadOlder: () => { loads++; return Promise.resolve(true); } });
  check("not found: older pages are loaded at most MAX_LOADS times, then it gives up", notFound === false && loads === J.MAX_LOADS, loads);
  loads = 0;
  const stopAt = await J.go({ quote: "câu không có", candidates: () => [answer], roots: (e) => [e.querySelector(".bubble")],
    loadOlder: () => { loads++; return false; } });
  check("not found: stops as soon as there is nothing older", stopAt === false && loads === 1, loads);

  // Found after one older page: the list grows, the words are scrolled into the middle of the list and marked.
  const older = el("div", "msg msg-javis", [el("div", "bubble", [txt("Ở trang cũ: chính sách đổi trả trong 7 ngày.")])]);
  older.querySelector = (sel) => sel === ".bubble" ? older.firstChild : null;
  older.classList = { set: new Set(), add(c) { this.set.add(c); }, remove(c) { this.set.delete(c); } };
  Object.defineProperty(older, "offsetWidth", { get() { return 1; } });
  const shown = [answer];
  let scrolled = null, stuckOff = false;
  const scroller = { scrollTop: 500, clientHeight: 400, getBoundingClientRect: () => ({ top: 100 }),
    scrollTo(o) { scrolled = o; } };
  const realCreate = fakeDoc.createRange;
  fakeDoc.createRange = function () {
    const rr = realCreate();
    rr.getBoundingClientRect = () => ({ top: 900, height: 20, width: 200 });
    rr.startContainer = older.firstChild.firstChild;
    return rr;
  };
  older.firstChild.firstChild.parentElement = older.firstChild;
  older.firstChild.closest = () => null;
  loads = 0;
  const found = await J.go({ quote: "đổi trả trong 7 ngày", candidates: () => shown.slice().reverse(),
    roots: (e) => [e.querySelector(".bubble")], scroller, beforeScroll: () => { stuckOff = true; },
    loadOlder: () => { loads++; shown.unshift(older); return true; }, flashClass: "quote-flash" });
  check("found after loading one older page", found === true && loads === 1, loads);
  check("the list stops following the end before it scrolls", stuckOff);
  check("the quoted words land in the middle of the list (no Highlight API here: the message flashes)",
    scrolled && scrolled.top === 500 + (900 - 100) - (400 - 20) / 2 && older.classList.set.has("quote-flash"), JSON.stringify(scrolled));
  J.clear();
  check("clear() removes the mark", !older.classList.set.has("quote-flash"));

  // ---- 7. Wiring in both chats (owner rule 2026-11-05: a chat change goes to every chat screen) ----
  const app = read("dashboard/app.js");
  check("main chat: a tap on the quote of a sent message jumps to its source",
    /const quoted = t\.closest && t\.closest\("\.msg-user \.uquote"\);\s*if \(quoted\) \{ jumpToQuoted\(quoted\); return; \}/.test(app));
  check("main chat: Enter and Space on the quote jump too", /e\.key !== "Enter" && e\.key !== " "[\s\S]{0,200}jumpToQuoted\(quoted\)/.test(app));
  check("main chat: on a phone the tap on the quote does not toggle the action row",
    app.includes('if (e.target.closest(".uquote")) return;'));
  check("main chat: searches messages above, skips quote blocks, loads older pages, stops following the end",
    /J\.before\(chatArea\.querySelectorAll\("\.msg"\), msgEl\)/.test(app) && app.includes('skip: ".uquote"')
    && app.includes("await taiTinCu();") && app.includes("beforeScroll: () => chatScroll.setStuck(false)"));
  const teams = read("dashboard/teams.js");
  check("Team chat: the owner's quote is a button that jumps to its source",
    teams.includes('class="tm-quote tm-quote-src" data-quote-src="1"') && teams.includes("if (d.quoteSrc) return jumpToQuoted(t);"));
  check("Team chat: looks for the words after \"Name: \", in the messages above, and loads older pages",
    teams.includes("quote: quoteParts(quote).words") && /J\.before\(box\.querySelectorAll\("\.tm-msg\[data-mid\]"\), self\(\)\)/.test(teams)
    && teams.includes("return loadMsgs(true).then("));
  check("quote-jump.js loads before app.js and teams.js", order.napTruoc("quote-jump.js", ["app.js", "teams.js"]));
  const style = read("dashboard/style.css"), cons = read("dashboard/console.css");
  check("CSS: the marked words, the flash fallback and the clickable quotes",
    style.includes("::highlight(jv-quote-hit)") && style.includes(".msg.quote-flash .bubble") && style.includes(".uquote { cursor: pointer;")
    && cons.includes("button.tm-quote-src {"));
  const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
  check("i18n: tooltip and not-found note in vi and en", ["cact.quote_jump", "cact.quote_missing"].every(k => vi[k] && en[k]));
  check("no em dash in the new file", !read("dashboard/quote-jump.js").includes("\u2014"));

  console.log();
  if (fails.length) {
    console.log("RED " + fails.length + ": " + fails.join(", "));
    process.exit(1);
  }
  console.log("All green.");
})();
