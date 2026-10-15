/* Composer "+" menu (0.153.0): registry, keyboard, brain files. The folder item moved to
   composer-folder.js in 0.158.0 (pin a working folder), see test_pinned_folder.js.

       node tests/js/test_menu_cong.js
*/
const fs = require("fs");
const path = require("path");
const P = require("../../dashboard/composer-plus.js");
const ROOT = path.join(__dirname, "../..");
const src = fs.readFileSync(path.join(ROOT, "dashboard/composer-plus.js"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "dashboard/app.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const reg = P.createRegistry();
reg.register({ id: "b", order: 20, label: "x.b" });
reg.register({ id: "a", order: 10, label: "x.a" });
reg.register({ id: "b", order: 5, label: "x.b2" });
check("the registry sorts by order and re-registering an id replaces it", reg.list().map(i => i.id + ":" + i.label).join(",") === "b:x.b2,a:x.a");

check("left arrow inside the search box does not leave it", P.shouldGoBack({ key: "ArrowLeft", target: { tagName: "INPUT" } }, true) === false);
check("left arrow on a submenu row goes back", P.shouldGoBack({ key: "ArrowLeft", target: { tagName: "BUTTON" } }, true) === true);
check("the top menu has no back row, so nothing happens", P.shouldGoBack({ key: "ArrowLeft", target: { tagName: "BUTTON" } }, false) === false);

const img = P.brainAttachment({ ok: true, path: "D:/b/attachments/x.jpg", name: "x.jpg", size: 9, kind: "image" }, "attachments/x.jpg", "D:/b");
check("an image picked from the brain has a viewable url (not 'expired')",
  img.url === "/files/raw?brain=" + encodeURIComponent("D:/b") + "&path=" + encodeURIComponent("attachments/x.jpg"));
check("a plain file picked from the brain needs no url", !P.brainAttachment({ ok: true, path: "D:/b/a.md", name: "a.md", kind: "file" }, "a.md", "D:/b").url);
check("app.js keeps the url of a brain file", /addBrainFile[\s\S]{0,400}url: it\.url/.test(app));
check("a failed brain file lookup says so instead of closing silently", src.indexOf('tw("cp.brain_failed")') !== -1);

["attach", "brain_file", "commands", "connections", "partners"].forEach(id =>
  check("default item with id " + id, src.indexOf('id: "' + id + '"') !== -1));
check("Ctrl+U blocks the browser default (source check)", /key === "u"[\s\S]{0,800}preventDefault/.test(src));
check("the commands item opens the / menu through an input event", src.indexOf('new Event("input"') !== -1);
check("calling an assistant inserts the same token as the / menu", src.indexOf('"/agent-" + ') !== -1 && src.indexOf('"/workflow-" + ') !== -1);
check("app.js exposes JavisAttach (pick, upload, addBrainFile, note)", /window\.JavisAttach = \{[\s\S]*pick[\s\S]*upload[\s\S]*addBrainFile[\s\S]*note/.test(app));
check("composer-plus.js loads after model-picker.js", html.indexOf("model-picker.js") < html.indexOf("composer-plus.js"));
check("no Vietnamese in composer-plus.js run code",
  !/[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]/i.test(src.replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "")));

// 0.160.0 follow-ups.
check("Ctrl+U does nothing when the composer is hidden or its + button is disabled",
  /key === "u"[\s\S]{0,600}plusBtn[\s\S]{0,120}disabled[\s\S]{0,200}offsetParent/.test(src));
check("the connections-to-fix count is refreshed each time the menu opens", /function open\(\) \{[\s\S]{0,300}refreshConnHealth\(\)/.test(src));
if (fails.length) { console.log("\nFAIL - test_menu_cong: " + fails.length); process.exit(1); }
console.log("\nOK - test_menu_cong: all pass");
