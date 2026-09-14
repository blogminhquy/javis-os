/* Dashboard kiểm lại lệnh ui_action trước khi chạy (dashboard/ui-actions.js).

       node tests/js/test_ui_actions.js

   Voice V1 spec mục 6. Bên thực hiện KHÔNG tin server tuyệt đối: trang lạ, đường dẫn tuyệt
   đối, `..`, scheme, mã việc lạ đều bị chặn ở đây dù plugin đã kiểm một lần. Danh sách trang
   phải khớp RAIL_ITEMS của console.js và PAGES của plugin javis-ui, không thì "mở trang X" ở
   một đầu nhận mà đầu kia từ chối. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const A = require(path.join(root, "dashboard", "ui-actions.js"));
const consoleJs = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
const plugin = fs.readFileSync(path.join(root, "system", "plugins", "javis-ui", "plugin.py"), "utf8");
const app = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
const main = fs.readFileSync(path.join(root, "server", "main.py"), "utf8");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}

check("open_page kanban: ok", A.validate({ action: "open_page", target: "kanban" }).ok);
check("open_page trang lạ: chặn", !A.validate({ action: "open_page", target: "admin" }).ok);
check("open_file tương đối: ok, chuẩn hoá \\ thành /", A.validate({ action: "open_file", target: "Wiki\\a.md" }).target === "Wiki/a.md");
check("open_file ..: chặn", !A.validate({ action: "open_file", target: "../x.md" }).ok);
check("open_file tuyệt đối Windows: chặn", !A.validate({ action: "open_file", target: "C:/x.md" }).ok);
check("open_file tuyệt đối POSIX: chặn", !A.validate({ action: "open_file", target: "/etc/passwd" }).ok);
check("open_file scheme: chặn", !A.validate({ action: "open_file", target: "file:///x" }).ok);
check("open_file rỗng: chặn", !A.validate({ action: "open_file", target: "" }).ok);
check("open_task mã hợp lệ: ok", A.validate({ action: "open_task", target: "t_2026-09-14_ab12" }).ok);
check("open_task mã có khoảng trắng: chặn", !A.validate({ action: "open_task", target: "a b" }).ok);
check("scroll top: ok", A.validate({ action: "scroll", target: "top" }).ok);
check("scroll left: chặn", !A.validate({ action: "scroll", target: "left" }).ok);
check("action lạ: chặn", !A.validate({ action: "eval", target: "x" }).ok);
check("frame null: chặn không nổ", !A.validate(null).ok);

// Danh sách trang khớp ba nơi
const railM = consoleJs.match(/const RAIL_ITEMS = \[\s*([\s\S]*?)\]\.map/);
const rail = railM ? railM[1].match(/"([a-z]+)"/g).map(x => x.replace(/"/g, "")) : [];
check("PAGES của ui-actions == RAIL_ITEMS của console.js", JSON.stringify(rail) === JSON.stringify(A.PAGES));
const pm = plugin.match(/PAGES = \(([\s\S]*?)\)/);
const ppages = pm ? pm[1].match(/"([a-z]+)"/g).map(x => x.replace(/"/g, "")) : [];
check("PAGES của plugin javis-ui == RAIL_ITEMS", JSON.stringify(rail) === JSON.stringify(ppages));

// Dây nối: app.js chuyển frame ui_action sang JavisUiActions, console.js xuất JavisKanbanShow,
// server có nhánh ui_result.
check("app.js xử lý frame ui_action", /data\.type === "ui_action"/.test(app) && /JavisUiActions\.handle\(/.test(app));
check("console.js xuất window.JavisKanbanShow", /window\.JavisKanbanShow = showTask/.test(consoleJs));
check("main.py có nhánh ui_result", /action == "ui_result"/.test(main));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - ui-actions");
