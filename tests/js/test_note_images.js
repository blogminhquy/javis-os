/* Insert images into a note: paste/drop/pick a file -> compress -> save into images/ -> embed
   ![[..]], plus the drag grip that resizes an image.

       node tests/js/test_note_images.js

   Requested by the owner (2026-09-11). Five places break SILENTLY, so they are guarded:

     1. Folder. Note images must NOT land in attachments/: media_gc treats that folder as a cache
        and by default deletes everything older than 30 days, so a month later the note shows a
        grey "image is gone" box. Note images live in images/, out of the sweeper's reach. (On the
        server side tests/python/test_note_images.py guards the same thing.)
     2. File name from LOCAL time, not UTC. With UTC, evening in Vietnam names the image after the
        previous day.
     3. Backwards compression. A small, already optimized PNG comes out HEAVIER when "compressed";
        then the original must be kept, or the space-saving feature bloats the file.
     4. The save round trip. The <img> tag must carry data-vault-path, otherwise the turndown rule
        "wikiimg" never runs and every save of a note with an image turns ![[a.png]] into
        ![a.png](/files/raw?brain=...) - with the brain name baked into the note.
     5. Keep the original syntax: ![](..) must not turn into ![[..]] on save. */
const fs = require("fs");
const path = require("path");
const vm = require("node:vm");
const NI = require("../../dashboard/note-images.js");
const R = require("../../dashboard/chat-render.js");
const EC = require("../../dashboard/editor-cmds.js");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const SRC = D("note-images.js");
const CON = D("console.js");
const HTML = D("index.html");
const CSS = D("style.css");
const VI = JSON.parse(D("i18n/vi.json"));
const EN = JSON.parse(D("i18n/en.json"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// ============================================================
// 1. Image name from the time
// ============================================================
const d = new Date(2026, 8, 11, 15, 4, 22);        // 2026-09-11 15:04:22 LOCAL time
check("image name follows yyyy-mm-dd-hh-mm-ss", NI.timestampName(d, ".webp") === "2026-09-11-15-04-22.webp");
check("single digits are zero-padded", NI.timestampName(new Date(2026, 0, 2, 3, 4, 5), ".png") === "2026-01-02-03-04-05.png");
// UTC time would make an evening image in Vietnam (UTC+7) jump to the next day.
check("CANARY: uses LOCAL time, not UTC", !/toISOString|getUTC/.test(SRC));
check("image name has no odd characters", /^[\d-]+\.webp$/.test(NI.timestampName(d, ".webp")));

// ============================================================
// 2. File extension and image detection
// ============================================================
check("extension from MIME", NI.extForType("image/webp") === ".webp" && NI.extForType("image/jpeg") === ".jpg");
check("MIME with a charset still reads", NI.extForType("image/png; charset=binary") === ".png");
// Some browsers' clipboard returns an empty type: infer from the file name, or a pasted .jpg is
// named .png.
check("empty MIME infers from the file name", NI.extForType("", "screenshot.JPG") === ".jpg");
check("nothing known defaults to .png", NI.extForType("", "") === ".png");
// Unknown MIME: the original name's extension is used only when it is a storable one.
check("CANARY: unknown MIME does not take an unchecked extension from the name",
      NI.extForType("", "a.html") === ".png" && NI.extForType("application/octet-stream", "x.exe") === ".png");
check("unknown MIME with a storable name extension keeps it", NI.extForType("", "a.avif") === ".avif");
check("original stored as-is only with a storable extension",
      NI.storableExt("", "a.JPG") === ".jpg" && NI.storableExt("image/png", "") === ".png");
check("CANARY: HEIC, TIFF and unknown types are never uploaded as-is",
      NI.storableExt("image/heic", "a.heic") === null && NI.storableExt("image/tiff", "a.tiff") === null &&
      NI.storableExt("", "blob") === null);
check("decode failure uploads the original only when storable, else reports unsupported",
      /if \(!origExt\) return \{ unsupported: true \};/.test(SRC) &&
      /if \(res\.unsupported\) \{ showStatus\(tw\("nimg\.unsupported"\), "err"\); return false; \}/.test(SRC));
check("a non-storable original always goes up re-encoded",
      /if \(origExt && pickSmaller\(/.test(SRC));
check("detects an image by MIME", NI.isImage("image/png", "") === true);
check("detects an image by name when MIME is empty", NI.isImage("", "x.webp") === true);
check("a .pdf file is not an image", NI.isImage("application/pdf", "a.pdf") === false);

// ============================================================
// 3. Compression: the new box, and when to keep the original
// ============================================================
check("a large image shrinks to a 1920 edge", JSON.stringify(NI.fitBox(4000, 3000, 1920)) === JSON.stringify({ w: 1920, h: 1440, resized: true }));
check("a portrait image follows the LONG edge too", JSON.stringify(NI.fitBox(1000, 4000, 1920)) === JSON.stringify({ w: 480, h: 1920, resized: true }));
check("CANARY: a small image is NOT upscaled", JSON.stringify(NI.fitBox(300, 200, 1920)) === JSON.stringify({ w: 300, h: 200, resized: false }));
check("exactly at the cap stays unchanged", NI.fitBox(1920, 100, 1920).resized === false);
check("zero dimensions do not break", NI.fitBox(0, 0, 1920).w === 1);

check("lighter when compressed: take the compressed one", NI.pickSmaller(900000, 200000, false) === "compressed");
check("CANARY: HEAVIER when compressed: keep the original", NI.pickSmaller(3000, 5200, false) === "original");
// Once the pixel count went down, keep the compressed one even if the bytes crept up: keeping a
// 4000px original keeps a resolution nobody needs in a note.
check("shrunk box still takes the compressed one", NI.pickSmaller(3000, 5200, true) === "compressed");
check("compression failed (no blob): keep the original", NI.pickSmaller(3000, 0, true) === "original");
check("gif kept as-is, not through the canvas (would lose animation)", NI.skipCompress("image/gif", "a.gif") === true);
// SVG can carry script and the note renders images inline, so it must never be stored.
check("SVG is not treated as an image (by MIME)", NI.isImage("image/svg+xml", "a.svg") === false);
check("SVG is not treated as an image (by name, empty MIME)", NI.isImage("", "a.svg") === false);
check("SVG has no stored extension", NI.extForType("image/svg+xml", "") !== ".svg");
check("png gets compressed", NI.skipCompress("image/png", "a.png") === false);

// ============================================================
// 4. Resize grip
// ============================================================
check("dragging right widens", NI.dragWidth(300, 120, 900) === 420);
check("dragging left narrows", NI.dragWidth(300, -100, 900) === 200);
check("CANARY: never narrower than 40px (a speck nobody can grab again)", NI.dragWidth(300, -9999, 900) === 40);
check("never wider than the editor", NI.dragWidth(300, 9999, 900) === 900);
check("an abnormally narrow editor still leaves a usable cap", NI.dragWidth(300, 9999, 10) === 80);

// ============================================================
// 5. Obsidian-style image size ![[a.png|300]]
// ============================================================
check("|300 is a size", JSON.stringify(R.imageSize("300")) === JSON.stringify({ w: 300, h: 0 }));
check("|300x200 is a two-dimension size", JSON.stringify(R.imageSize("300x200")) === JSON.stringify({ w: 300, h: 200 }));
check("text is alt text, not a size", JSON.stringify(R.imageSize("ảnh bìa")) === JSON.stringify({ alias: "ảnh bìa" }));
check("empty means nothing", R.imageSize("") === null && R.imageSize(null) === null);

const img = (md) => (R.mdToHtml(md).match(/<img[^>]*>/) || [""])[0];
check("![[a|320]] renders a 320-wide image", /style="width:320px"/.test(img("![[images/a.webp|320]]")));
check("the size is kept in data-img-size for saving back", /data-img-size="320"/.test(img("![[images/a.webp|320]]")));
check("no size means no style", !/style=/.test(img("![[images/a.webp]]")));
check("CANARY: the img tag carries data-vault-path (without it the save round trip breaks)",
      /data-vault-path="images\/a\.webp"/.test(img("![[images/a.webp]]")));
check("an image written as ![[..]] is marked data-img-wiki", /data-img-wiki="1"/.test(img("![[images/a.webp]]")));
check("CANARY: an image written as ![](..) is NOT marked wiki", !/data-img-wiki/.test(img("![anh](images/a.webp)")));
check("an external URL image gets no data-vault-path", !/data-vault-path/.test(img("![x](https://e.com/a.png)")));

// ============================================================
// 6. The SAVE round trip: run the real replacement of the turndown rule "wikiimg"
// ============================================================
// Extract the function from console.js and run it, not just match its text: this decides what
// the note on disk looks like, and a text match cannot prove it produces the right characters.
function extractReplacement(ruleName) {
  const i = CON.indexOf('_td.addRule("' + ruleName + '"');
  if (i < 0) return null;
  const j = CON.indexOf("replacement:", i);
  const k = CON.indexOf("{", CON.indexOf("=>", j));
  let depth = 0, e = k;
  for (; e < CON.length; e++) {
    if (CON[e] === "{") depth++;
    else if (CON[e] === "}") { depth--; if (!depth) break; }
  }
  return eval("(function (c, n) " + CON.slice(k, e + 1) + ")");
}
const saveImage = extractReplacement("wikiimg");
check("extracted the image save function", typeof saveImage === "function");
const node = (o) => ({ getAttribute: (k) => (Object.prototype.hasOwnProperty.call(o, k) ? o[k] : null) });

check("![[a]] saves back as ![[a]]",
      saveImage("", node({ "data-vault-path": "images/a.webp", "data-img-wiki": "1" })) === "![[images/a.webp]]");
check("a resized image saves as ![[a|320]]",
      saveImage("", node({ "data-vault-path": "images/a.webp", "data-img-wiki": "1", "data-img-size": "320" })) === "![[images/a.webp|320]]");
check("alt text survives after |",
      saveImage("", node({ "data-vault-path": "images/a.webp", "data-img-wiki": "1", "data-img-alias": "ảnh bìa" })) === "![[images/a.webp|ảnh bìa]]");
check("CANARY: ![](..) saves back STILL as ![](..), the syntax does not change on its own",
      saveImage("", node({ "data-vault-path": "images/a.webp", alt: "anh" })) === "![anh](images/a.webp)");
// A space ends the link target in markdown, so ![](..) saves spaces as %20 (the renderer
// decodes them back, see the round trip below). ![[..]] keeps them as typed.
check("CANARY: ![](..) with a space in the path saves it as %20",
      saveImage("", node({ "data-vault-path": "images/my pic.webp", alt: "a" })) === "![a](images/my%20pic.webp)");
check("![[..]] keeps the space as typed",
      saveImage("", node({ "data-vault-path": "images/my pic.webp", "data-img-wiki": "1" })) === "![[images/my pic.webp]]");
check("the %20 path renders back to the same vault path",
      /data-vault-path="images\/my pic\.webp"/.test(img("![a](images/my%20pic.webp)")));
// ![](..) has nowhere to store a size, so resizing such an image must switch it to ![[..|size]];
// keeping it would silently drop what the user just did.
check("a resized ![](..) switches to ![[..|size]] to keep the size",
      saveImage("", node({ "data-vault-path": "images/a.webp", alt: "anh", "data-img-size": "500" })) === "![[images/a.webp|500]]");

// ============================================================
// 7. Wired into the app
// ============================================================
check("images are saved into the images folder (NOT attachments)",
      /fd\.append\("folder", "images"\)/.test(SRC) && !/"folder", "attachments"/.test(SRC));
check("explains why attachments is not used", /media_gc/.test(SRC));
check("paste (Ctrl+V) is handled", /addEventListener\("paste"/.test(SRC));
check("dropping files is handled", /addEventListener\("drop"/.test(SRC) && /addEventListener\("dragover"/.test(SRC));
check("pasting TEXT is not hijacked (only blocked when there is an image)",
      /if \(!images\.length\) return;[\s\S]{0,40}e\.preventDefault\(\)/.test(SRC));
check("reads clipboardData.items too (Firefox returns empty files)", /dt\.items/.test(SRC));
check("several images at once run IN SEQUENCE", /reduce\(/.test(SRC));
check("an oversized image is refused before compressing", /MAX_MB \* 1024 \* 1024/.test(SRC));
check("after inserting, an input event fires so autosave runs", /dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\)/.test(SRC));
check("SHARES the editor lookup of editor-cmds, no second copy",
      /EC\.contextFor/.test(SRC) && typeof EC.contextFor === "undefined");   // contextFor exists only in the browser
check("the grip follows page scrolling", /addEventListener\("scroll"/.test(SRC));
check("double-clicking the grip restores the original size", /dblclick/.test(SRC) && /removeAttribute\("data-img-size"\)/.test(SRC));
check("does NOT use the em dash character", !SRC.includes("\u2014"));

// The grip and the status toast are appended to <body>: they must sit above the full-screen
// editor (.ne-full) and the file-editor modal (.jvfe-modal), or they are hidden under them.
const zOf = (re, src) => { const m = re.exec(src); return m ? +m[1] : -1; };
const zModal = zOf(/\.jvfe-modal\{[^}]*z-index:(\d+)/, D("file-editor.js"));
const zFull = zOf(/\.note-editor\.ne-full \{[^}]*z-index: (\d+)/, CSS);
const zGrip = zOf(/\.ni-grip \{[^}]*z-index: (\d+)/, CSS);
const zStatus = zOf(/\.ni-status \{[^}]*z-index: (\d+)/, CSS);
check("found the z-index of the full-screen editor and the file-editor modal", zModal > 0 && zFull > 0);
check("CANARY: resize grip sits above the full-screen editor and the file-editor modal",
      zGrip > zModal && zGrip > zFull);
check("CANARY: status toast sits above the full-screen editor and the file-editor modal",
      zStatus > zModal && zStatus > zFull);
check("status toast text is 16px", /\.ni-status \{[^}]*font-size: 16px/.test(CSS));

// insertLink() runs after the upload finishes. If the note was closed or another one opened in
// the meantime, its editor host is detached: the link must not land anywhere. Run the real function.
function extractFn(src, head) {
  const i = src.indexOf(head);
  if (i < 0) return null;
  let depth = 0, e = src.indexOf("{", i);
  for (; e < src.length; e++) {
    if (src[e] === "{") depth++;
    else if (src[e] === "}") { depth--; if (!depth) break; }
  }
  return src.slice(i, e + 1);
}
const insertSrc = extractFn(SRC, "function insertLink(ctx, path)");
check("found the insert function", !!insertSrc);
const insert = vm.runInNewContext("(" + insertSrc + ")", {
  document: { execCommand: () => false }, Event: function () {}, window: { getSelection: () => null },
  imageHtml: () => '<img src="x">',
});
const fakeTa = (connected) => ({
  isConnected: connected, value: "abc", selectionStart: 3, selectionEnd: 3,
  focus() {}, setSelectionRange() {}, dispatchEvent() {},
});
const gone = fakeTa(false);
check("CANARY: detached editor (note closed during upload) gets nothing and reports failure",
      insert({ mode: () => "source", ta: gone, wys: null }, "images/a.webp") === false && gone.value === "abc");
check("CANARY: detached render pane gets nothing either",
      insert({ mode: () => "wys", ta: null, wys: { isConnected: false, focus() {}, contains: () => false, dispatchEvent() {} } },
             "images/a.webp") === false);
const live = fakeTa(true);
check("a live source editor still gets the link",
      insert({ mode: () => "source", ta: live, wys: null }, "images/a.webp") === true &&
      live.value === "abc![[images/a.webp]]");

check("index.html loads note-images.js", /note-images\.js/.test(HTML));
check("loaded AFTER editor-cmds.js", HTML.indexOf("note-images.js") > HTML.indexOf("editor-cmds.js"));

const imageCmd = EC.CMDS.find((c) => c.id === "image");
check("the toolbar has an insert-image button", !!imageCmd && imageCmd.btn.icon === "image");
check("the image button works in BOTH modes (uses run, not separate wys/src)", !!(imageCmd && imageCmd.run));
check("the image button is in the '/' menu", EC.menuCmds().some((c) => c.id === "image"));
check("filtering the '/' menu by 'chen anh' finds the image button", EC.filterCmds("chen anh").map((c) => c.id).join() === "image");
// Cmd+Option+I opens devtools on macOS and Ctrl+Shift+I everywhere: the image command has no
// shortcut at all (toolbar button, "/image" and paste cover it).
check("CANARY: the image command has no keyboard shortcut", !!imageCmd && !imageCmd.key && EC.keyLabel(imageCmd) === "");
check("Ctrl/Cmd+Alt+I and Ctrl+Shift+I trigger no editor command",
      EC.matchCmd({ ctrlKey: true, altKey: true, code: "KeyI", key: "i" }) === null &&
      EC.matchCmd({ metaKey: true, altKey: true, code: "KeyI", key: "\u02c6" }) === null &&
      EC.matchCmd({ ctrlKey: true, shiftKey: true, code: "KeyI", key: "I" }) === null);

["ecmd.image", "nimg.working", "nimg.done", "nimg.too_large", "nimg.failed", "nimg.upload_failed",
 "nimg.no_place", "nimg.resize_grip", "nimg.heic", "nimg.unsupported"].forEach((k) => {
  check("i18n key " + k + " exists in both vi and en", !!VI[k] && !!EN[k] && VI[k] !== EN[k]);
});
check("the failure message takes the {error} parameter",
      VI["nimg.failed"].includes("{error}") && EN["nimg.failed"].includes("{error}"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nAll green");
process.exit(fails.length ? 1 : 0);
