/* Chèn ảnh vào note - hai chỗ đặc tả gốc (test_anh_trong_note.js) chưa canh:

       node tests/js/test_anh_heic_xoay.js

     1. Ảnh HEIC của iPhone. Chrome/Edge trên Windows không giải mã được. Đường cũ "đọc không
        được thì cứ gửi bản gốc" sẽ lưu một file .heic mà note chỉ hiện ô xám ở mọi trình duyệt
        trừ Safari. Phải chặn và nói rõ, không âm thầm lưu.
     2. Ảnh chụp dọc bị nằm nghiêng. Ảnh điện thoại lưu điểm ảnh nằm ngang kèm thẻ EXIF xoay;
        canvas bỏ EXIF, nên phải xoay theo thẻ TRƯỚC khi vẽ (imageOrientation "from-image"). */
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
check("nhận ra HEIC theo MIME", NI.laHeic("image/heic", "") === true && NI.laHeic("image/heif", "") === true);
check("nhận ra HEIC theo tên khi MIME rỗng", NI.laHeic("", "IMG_0001.HEIC") === true);
check("JPG không phải HEIC", NI.laHeic("image/jpeg", "a.jpg") === false);
check("HEIC vẫn được coi là ảnh (Safari giải mã được thì nén bình thường)", NI.laAnh("", "a.heic") === true);
check("đuôi HEIC giữ đúng", NI.duoiTheoLoai("image/heic", "") === ".heic");
check("CANARY: HEIC không giải mã được thì CHẶN, không gửi bản gốc",
      /if \(laHeic\(file\.type, file\.name\)\) return \{ heic: true \}/.test(SRC) &&
      /if \(kq\.heic\) \{ noi\(tw\("nimg\.heic"\), "err"\); return false; \}/.test(SRC));
check("có khoá dịch nimg.heic ở cả vi và en", !!VI["nimg.heic"] && !!EN["nimg.heic"] && VI["nimg.heic"] !== EN["nimg.heic"]);

// 2. Xoay theo EXIF
check("CANARY: giải mã ảnh có xoay theo EXIF", /imageOrientation: "from-image"/.test(SRC));
check("trình duyệt không nhận tuỳ chọn đó thì vẫn giải mã được", /\.catch\(function \(\) \{ return mo\(\); \}\)/.test(SRC));
check("createImageBitmap hỏng hẳn thì lùi về thẻ <img>", /return doBangThe\(file\);/.test(SRC));

check("KHÔNG dùng ký tự em dash", !SRC.includes("\u2014"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nTất cả đều xanh");
process.exit(fails.length ? 1 : 0);
