// Giao diện của việc chạy nền và đồng bộ khung chat (0.64.66).
// Chạy: node tests/js/test_viec_chay_nen_ui.js
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const V = require(path.join(D, "chat-viec.js"));

let hong = 0;
function check(ten, dk) { console.log((dk ? "PASS " : "FAIL ") + ten); if (!dk) hong++; }

const the = V.dauThe({ kind: "job", status: "done", title: "ffmpeg -i a.mp4 b.mp4", id: "j1" });
check("thẻ việc chạy nền có nhãn riêng", the.includes("Việc chạy nền đã xong"));
check("thẻ việc chạy nền không có nút mở trang (không trang nào liệt kê nó)", !the.includes("viec-mo"));
const theTask = V.dauThe({ kind: "task", status: "done", title: "x", id: "t1" });
check("thẻ việc Kanban vẫn có nút mở trang Việc", theTask.includes("viec-mo"));
check("khối JAVIS_VIEC kind job bóc ra đúng",
  V.tach('<!-- JAVIS_VIEC: {"kind":"job","status":"cancelled","title":"t","id":"j"} -->\nx').viec.kind === "job");

const STEPS = fs.readFileSync(path.join(D, "chat-steps.js"), "utf8");
check("khối bước vẽ lại khi từ điển về (hết chữ thô app.steps_done)",
  STEPS.includes('addEventListener("javis:i18n"') && STEPS.includes("el._st = st"));

const APP = fs.readFileSync(path.join(D, "app.js"), "utf8");
check("quay lại app mà socket còn 'sống' vẫn đồng bộ nhẹ với server", /else if \(savedSessionId\) \{[\s\S]{0,600}_dongBoNeuLech\(\)/.test(APP));
// 17/11/2026: the FIRST hello checks too (a home-screen app iOS closed starts from its own copy of the chat).
check("mọi lời chào hello (cả lần đầu) đều đồng bộ nhẹ", /data\.type === "hello"\) \{[\s\S]{0,900}\n    setTimeout\(_dongBoNeuLech, 300\);/.test(APP));
check("đồng bộ nhẹ hỏi lại một lần khi mạng chưa kịp dậy", /if \(!isRetry\) setTimeout\(\(\) => _dongBoNeuLech\(true\), 2000\)/.test(APP));
check("đồng bộ nhẹ nhường cho hội thoại đang được mở", /seq !== sessionOpenSeq/.test(APP));
check("đồng bộ nhẹ không tải lại khi lượt đang chạy", APP.includes("if (!sid || (turns[sid] && turns[sid].running)) return;"));

const BGS = fs.readFileSync(path.join(D, "background-strip.js"), "utf8");
check("dải trạng thái có nhãn cho việc chạy nền", BGS.includes('job: "bgs.kind.job"'));
for (const l of ["vi", "en"]) {
  const j = JSON.parse(fs.readFileSync(path.join(D, "i18n", l + ".json"), "utf8"));
  check(`từ điển ${l} đủ khoá việc chạy nền`,
    ["bgs.kind.job", "viec.job_done", "viec.job_cancelled", "viec.job_timeout"].every(k => j[k]));
}

if (hong) { console.log("\nTHAT BAI " + hong); process.exit(1); }
console.log("\nOK - test_viec_chay_nen_ui: tat ca pass");
