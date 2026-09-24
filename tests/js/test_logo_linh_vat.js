/* Logo, favicon và linh vật mặc định là CÙNG MỘT nhân vật: ngôi sao màu cam (0.64.47).

       node tests/js/test_logo_linh_vat.js

   Chủ dự án chốt 24/09: linh vật chính thức của Javis là ngôi sao cam, mắt cười ^^; logo,
   favicon và linh vật mặc định đều phải là hình đó. Ba thứ này nằm ở ba chỗ khác nhau
   (dashboard/logo.svg + các PNG xuất từ nó, bảng SHAPES/PALETTES trong pet.js, MAC_DINH), nên
   rất dễ lệch nhau khi một chỗ được sửa mà chỗ kia quên. Test này khoá sự trùng khớp đó.

   KHÔNG dùng ký tự em dash. */
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

const pet = read("dashboard/pet.js");
const svg = read("dashboard/logo.svg");
const dSao = (/star:\s+\{ key: "pet\.shape\.star",\s+d: "([^"]+)"/.exec(pet) || [])[1] || "";
const cam = /cam:\s+\{ key: "pet\.color\.cam",\s+sun: \["(#\w{6})", "(#\w{6})"/.exec(pet) || [];

check("linh vật mặc định là NGÔI SAO", /var MAC_DINH = \{[^}]*shape: "star"/.test(pet));
check("linh vật mặc định màu CAM", /var MAC_DINH = \{[^}]*palette: "cam"/.test(pet));
check("nút Đặt lại trả về đúng ngôi sao cam",
  /P\.setCfg\(\{ shape: "star", palette: "cam",/.test(read("dashboard/console.js")));
check("logo.svg vẽ ĐÚNG đường ngôi sao của linh vật", dSao.length > 50 && svg.split(dSao).length - 1 === 2,
  "số lần xuất hiện: " + (svg.split(dSao).length - 1));
check("thân logo cùng màu thân bảng Cam", !!cam[1] && svg.includes('fill="' + cam[1] + '"'), cam[1]);
check("viền logo cùng màu vành bảng Cam", !!cam[2] && svg.includes('stroke="' + cam[2] + '"'), cam[2]);
const dMat = (/<path d="(M[^"]+)"\s+fill="none" stroke="#1F1F1F"/.exec(svg) || [])[1] || "";
check("logo có đôi mắt cười ^^ (đúng hai cung, đầu bo tròn)", (dMat.match(/Q/g) || []).length === 2 && /stroke-linecap="round"/.test(svg), dMat);
check("logo nền trong suốt (không có hình nền)", !/<rect/.test(svg));

// Các PNG phải là ảnh vuông đúng cỡ (đọc thẳng header PNG, khỏi cần thư viện ảnh).
for (const [ten, px] of [["logo.png", 512], ["icon-512.png", 512], ["icon-192.png", 192], ["favicon.png", 64]]) {
  const b = fs.readFileSync(path.join(ROOT, "dashboard", ten));
  const w = b.readUInt32BE(16), h = b.readUInt32BE(20), kieuMau = b[25];
  check(ten + " là PNG " + px + "x" + px + " có kênh trong suốt", b.toString("latin1", 1, 4) === "PNG" && w === px && h === px && kieuMau === 6,
    w + "x" + h + " kieu " + kieuMau);
}

console.log(fails.length ? "\nFAIL: " + fails.join(", ") : "\nTat ca OK");
process.exit(fails.length ? 1 : 0);
