/* Insert images into a note - two things the main spec (test_note_images.js) does not guard:

       node tests/js/test_note_image_heic_rotation.js

     1. iPhone HEIC photos. Chrome/Edge on Windows cannot decode them. The old path "cannot decode,
        just send the original" would store a .heic file the note shows as a grey box in every
        browser except Safari. It must be refused with a clear message, not stored silently.
     2. Upright photos lying on their side. A phone stores the pixels landscape plus an EXIF
        rotation tag; the canvas drops EXIF, so the image must be rotated by the tag BEFORE drawing
        (imageOrientation "from-image"). */
const fs = require("fs");
const path = require("path");
const NI = require("../../dashboard/note-images.js");

const ROOT = path.join(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "dashboard", "note-images.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// 1. HEIC
check("detects HEIC by MIME", NI.isHeic("image/heic", "") === true && NI.isHeic("image/heif", "") === true);
check("detects HEIC by name when MIME is empty", NI.isHeic("", "IMG_0001.HEIC") === true);
check("JPG is not HEIC", NI.isHeic("image/jpeg", "a.jpg") === false);
check("HEIC still counts as an image (Safari decodes it, then it compresses as usual)", NI.isImage("", "a.heic") === true);
check("HEIC extension is kept", NI.extForType("image/heic", "") === ".heic");
check("CANARY: HEIC that cannot be decoded is REFUSED, the original is not sent",
      /if \(isHeic\(file\.type, file\.name\)\) return \{ heic: true \}/.test(SRC) &&
      /if \(res\.heic\) \{ showStatus\(tw\("nimg\.heic"\), "err"\); return false; \}/.test(SRC));
check("i18n key nimg.heic exists in both vi and en", !!VI["nimg.heic"] && !!EN["nimg.heic"] && VI["nimg.heic"] !== EN["nimg.heic"]);

// 2. EXIF rotation
check("CANARY: decoding rotates by EXIF", /imageOrientation: "from-image"/.test(SRC));
check("a browser that rejects that option still decodes", /\.catch\(function \(\) \{ return open\(\); \}\)/.test(SRC));
check("a broken createImageBitmap falls back to an <img> tag", /return decodeWithTag\(file\);/.test(SRC));

check("does NOT use the em dash character", !SRC.includes("\u2014"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nAll green");
process.exit(fails.length ? 1 : 0);
