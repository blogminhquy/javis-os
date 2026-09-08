/* The "het luot goi thue bao, tu chay lai luc HH:MM" (limit-resume.js).
       node tests/js/test_limit_resume.js
   Chi test cac ham thuan (describe / fmtWhen / fmtLeft): chu tren the phai noi dung trang
   thai server gui xuong, va dong "con X phut" phai doc duoc. Khong can DOM. */
const R = require("../../dashboard/limit-resume.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

// Moc co dinh: 2026-09-05 10:00 gio may. Tinh epoch tu gio dia phuong de khong phu thuoc TZ.
const base = new Date(2026, 8, 5, 10, 0, 0).getTime() / 1000;

// ---- fmtLeft ----
check("fmtLeft: 0 -> rong", R.fmtLeft(0) === "");
check("fmtLeft: 30s -> duoi 1 phut", R.fmtLeft(30) === "còn dưới 1 phút");
check("fmtLeft: 42 phut", R.fmtLeft(42 * 60 + 5) === "còn 42 phút");
check("fmtLeft: 1 gio 5 phut", R.fmtLeft(3600 + 5 * 60) === "còn 1 giờ 5 phút");
check("fmtLeft: 2 gio chan khong thua ' 0 phut'", R.fmtLeft(7200) === "còn 2 giờ");

// ---- fmtWhen ----
check("fmtWhen: cung ngay chi gio:phut", R.fmtWhen(base + 3661, base) === "11:01");
check("fmtWhen: khac ngay kem ngay/thang", R.fmtWhen(base + 86400 * 2, base) === "10:00 ngày 07/09");
check("fmtWhen: 0 -> rong", R.fmtWhen(0, base) === "");

// ---- describe: hen tu chay ----
let d = R.describe({ state: "scheduled", auto: true, resume_at: base + 42 * 60 }, base);
check("scheduled: noi gio va con bao lau", d.text === "Tự chạy lại lúc 10:42" && d.left === "còn 42 phút");
check("scheduled: co o tick, co nut chay ngay, khong busy", d.showAuto && d.showNow && !d.busy && d.auto);
d = R.describe({ state: "scheduled", auto: true, resume_at: base - 5 }, base);
check("scheduled qua gio: dang cho may chu", /chờ máy chủ/.test(d.text) && d.left === "");

// ---- describe: tat ----
d = R.describe({ state: "off", auto: false, reason: "off", resume_at: base + 600 }, base);
check("off: noi moc mo lai va khong tu chay", d.text === "Hạn mức mở lại lúc 10:10. Không tự chạy lại." && d.showAuto && !d.auto);
d = R.describe({ state: "off", auto: false, reason: "no_reset" }, base);
check("no_reset: giai thich, KHONG co o tick (bat cung vo nghia)", /không nói lúc nào/.test(d.text) && !d.showAuto && d.showNow);
d = R.describe({ state: "off", auto: false, reason: "max_attempts", max_attempts: 3 }, base);
check("max_attempts: noi da thu 3 lan", /3 lần/.test(d.text) && !d.showAuto);
d = R.describe({ state: "off", auto: false, reason: "too_far", resume_at: base + 86400 * 3 }, base);
check("too_far: noi moc kem ngay", /08\/09/.test(d.text) && /quá xa/.test(d.text));

// ---- describe: cac trang thai khac ----
d = R.describe({ state: "running" }, base);
check("running: busy, khong nut", d.busy && !d.showNow && /Đang chạy lại/.test(d.text));
d = R.describe({ state: "done", done_at: base + 60 }, base);
check("done: noi da chay lai luc may gio", d.text === "Đã chạy lại lúc 10:01." && !d.showNow);
d = R.describe({ state: "cancelled" }, base);
check("cancelled: giai thich vi tin moi", /tin mới/.test(d.text) && !d.showNow);
d = R.describe({ state: "pending", resume_at: base + 600 }, base);
check("pending (chua co khung resume): chi nhac moc, chua co nut", d.text === "Hạn mức mở lại lúc 10:10." && !d.showNow && !d.showAuto);
d = R.describe(null, base);
check("dau vao null: khong no", typeof d.text === "string");

// Chu tren the khong duoc chua em dash.
const all = ["scheduled", "off", "running", "done", "cancelled", "gone", "pending"].map(st =>
  R.describe({ state: st, auto: st === "scheduled", reason: "off", resume_at: base + 100 }, base).text).join(" ");
check("khong co em dash", all.indexOf("\u2014") === -1 && all.indexOf("\u2013") === -1);

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nOK tat ca");
