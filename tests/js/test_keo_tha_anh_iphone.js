/* Kéo ảnh vừa chụp vào ô chat trên iPhone: ảnh hiện mà gửi thì hỏng (0.65.30).

   Chủ dự án báo: kéo ảnh chụp màn hình (thumbnail ở góc) vào ô chat, chip hiện ảnh, bấm gửi thì
   hỏng. iPhone chỉ cho ĐỌC file kéo thả trong lúc sự kiện thả đang chạy; Javis trước đây chỉ giữ
   tham chiếu File rồi đọc khi tải lên (sau đó), lúc quyền đã hết. Nay chupFile() bắt đầu đọc
   NGAY trong sự kiện và gói bản sao thành File mới; file 0 byte báo ngay trên chip.

   Chạy: node tests/js/test_keo_tha_anh_iphone.js
   Ghi chú: KHÔNG dùng ký tự em dash. */
"use strict";
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const app = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(root, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ---- 1. Dây nối ----
check("thả file: chụp bản sao NGAY rồi mới tải lên",
  /\[\.\.\.e\.dataTransfer\.files\]\.map\(chupFile\)\.forEach\(p => p\.then\(f => uploadFile\(f\)\)\);/.test(app));
check("dán ảnh cũng chép ngay", /if \(f\) \{ chupFile\(f\)\.then\(uploadFile\); e\.preventDefault\(\); \}/.test(app));
check("file 0 byte báo lỗi ngay trên chip, không gửi lên máy chủ",
  /if \(!file\.size\) \{[\s\S]{0,120}att\.loi = true; att\.statusText = window\.t\("app\.att_empty"\);/.test(app));
check("có chữ báo file rỗng (vi/en), không em dash",
  typeof vi["app.att_empty"] === "string" && typeof en["app.att_empty"] === "string"
  && !/—/.test(vi["app.att_empty"] + en["app.att_empty"]));

// ---- 2. Chạy thật chupFile lấy từ nguồn ----
const src = (app.match(/function chupFile\(f\) \{[\s\S]*?\n\}/) || [""])[0];
check("nhấc được hàm chupFile", src.length > 0);
const chupFile = new Function("File", "Promise", "Date", src + "\nreturn chupFile;")(
  class { constructor(parts, name, opts) { this.parts = parts; this.name = name; this.type = opts.type; this.lastModified = opts.lastModified; this.size = parts[0].byteLength; } },
  Promise, Date);

(async () => {
  // Giả lập file kéo thả của iPhone: chỉ đọc được khi gọi arrayBuffer() trước lúc sự kiện kết thúc.
  let trongSuKien = true, goiLuc = null;
  const buf = new Uint8Array([137, 80, 78, 71]).buffer;
  const fileThat = { name: "IMG_0001.PNG", type: "image/png", lastModified: 5, size: 4,
    arrayBuffer() { goiLuc = trongSuKien; return trongSuKien ? Promise.resolve(buf) : Promise.reject(new Error("NotReadableError")); } };
  const p = chupFile(fileThat);
  trongSuKien = false;   // sự kiện thả kết thúc ngay sau lời gọi đồng bộ
  const ban = await p;
  check("đọc được bắt đầu ĐỒNG BỘ trong sự kiện thả", goiLuc === true);
  check("trả File mới mang bản sao, giữ tên, kiểu, mốc giờ",
    ban !== fileThat && ban.parts[0] === buf && ban.name === "IMG_0001.PNG" && ban.type === "image/png" && ban.lastModified === 5);

  const hong = { name: "x.png", type: "image/png", size: 4, arrayBuffer() { return Promise.reject(new Error("NotReadableError")); } };
  check("đọc hỏng thì trả lại file gốc (hành vi cũ), không ném lỗi", (await chupFile(hong)) === hong);
  const rong = { name: "x.png", type: "image/png", size: 0, arrayBuffer() { return Promise.resolve(new ArrayBuffer(0)); } };
  check("đọc ra 0 byte thì trả file gốc để chip báo file rỗng", (await chupFile(rong)) === rong);
  const cu = { name: "x.png", type: "image/png", size: 4, arrayBuffer: undefined };
  check("trình duyệt cũ không có arrayBuffer() thì vẫn trả file gốc", (await chupFile(cu)) === cu);
  const khongTen = { name: "", type: "", size: 4, arrayBuffer() { return Promise.resolve(buf); } };
  const k = await chupFile(khongTen);
  check("file không tên, không kiểu vẫn có tên và kiểu dùng được", k.name === "anh-keo-tha.png" && k.type === "application/octet-stream");

  if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
  console.log("\nOK - kéo thả ảnh trên iPhone");
})().catch(e => { console.error(e); process.exit(1); });
