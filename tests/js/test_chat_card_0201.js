// 0.201.0: interactive cards in a Javis answer. Model output is escaped, capped and secret-masked; a broken block
// disappears instead of eating the answer; buttons only carry a reply text.
const path = require("path");
const C = require(path.join(__dirname, "../../dashboard/chat-card.js"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const chart = C.parse(JSON.stringify({ type: "chart", title: "Doanh thu", kind: "bar", labels: ["T2", "T3", "<b>T4</b>"],
  series: [{ name: "Tuần này", data: [10, "12tr", -3] }, { name: "Tuần trước", data: [8, 9, 4] }] }));
check("chart parsed", chart && chart.type === "chart" && chart.series.length === 2);
check("numbers coerced", chart.series[0].data[1] === 12);
const ch = C.html(chart);
check("chart drawn as svg", ch.includes("<svg") && ch.includes("<rect"));
check("labels escaped", ch.includes("&lt;b&gt;T4") && !ch.includes("<b>T4"));
check("legend for two series", ch.includes("Tuần trước"));
check("line chart uses polyline", C.html(C.parse(JSON.stringify({ type: "chart", kind: "line", labels: ["a", "b"],
  series: [{ name: "x", data: [1, 2] }] }))).includes("<polyline"));
const many = C.parse(JSON.stringify({ type: "chart", labels: Array.from({ length: 50 }, (_, i) => "d" + i),
  series: [1, 2, 3, 4, 5].map(n => ({ name: "s" + n, data: Array(50).fill(n) })) }));
check("points and series capped", many.labels.length === 24 && many.series.length === 3);

const stats = C.parse(JSON.stringify({ type: "stats", items: [{ label: "Đơn", value: "128", delta: "+12%" },
  { label: "Chi phí", value: "4,2tr", delta: "-5%" }, { label: "Key", value: "sk-ant-api03-ABCDEFGHIJKL" }] }));
const sh = C.html(stats);
check("stats tiles drawn", stats.items.length === 3 && sh.includes("128") && sh.includes("+12%"));
check("secret masked", !sh.includes("sk-ant-api03") && sh.includes("••••"));

const btns = C.parse(JSON.stringify({ type: "buttons", title: "Duyệt?", buttons: [{ label: "Duyệt", reply: "Duyệt bản A" },
  { label: "Sửa" }, { label: "" }, { label: "4" }, { label: "5" }, { label: "6" }] }));
const bh = C.html(btns);
check("buttons capped and empty dropped", btns.buttons.length === 4);
check("button carries its reply", bh.includes('data-reply="Duyệt bản A"'));
check("button without reply sends its label", bh.includes('data-reply="Sửa"'));

check("broken JSON is no card", C.parse("{oops") === null);
check("unknown type is no card", C.parse(JSON.stringify({ type: "script", src: "x" })) === null);
const ph = [];
const out = C.replaceIn('Trước <!-- JAVIS_CARD: {"type":"stats","items":[{"label":"A","value":"1"}]} --> sau'
  + ' <!-- JAVIS_CARD: {broken} --> hết', h => { ph.push(h); return "@@" + (ph.length - 1) + "@@"; });
check("good block replaced by a placeholder", out.includes("@@0@@") && ph.length === 1);
check("broken block removed, text kept", !out.includes("JAVIS_CARD") && out.includes("Trước") && out.includes("hết"));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
