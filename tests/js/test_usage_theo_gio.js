/* Trang Mức dùng, phần "24 giờ qua" (0.329.0): nối dây đúng và chữ đủ cả hai thứ tiếng.

       node tests/js/test_usage_theo_gio.js

   Số đúng hay sai do tests/python/test_muc_dung_theo_gio.py canh. Ở đây canh mấy chỗ dễ đứt
   im lặng: quên gọi /usage/theo-gio thì cả phần không hiện mà không báo lỗi gì; thiếu khoá từ
   điển thì màn hình in nguyên mã khoá. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const U = fs.readFileSync(path.join(ROOT, "dashboard", "usage.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));
const fails = [];
const check = (ten, ok, them) => { console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + them + "]")); if (!ok) fails.push(ten); };

check("nạp /usage/theo-gio cùng lúc với các nguồn khác", /fetch\("\/usage\/theo-gio"\)/.test(U) && /state\.gio = res\[6\]/.test(U));
check("phần 24 giờ đứng ngay sau ba ô hành động", /heroHtml\(\) \+ act \+ gioHtml\(\) \+ cards/.test(U));
check("không có dữ liệu thì không vẽ khung rỗng", /if \(!g \|\| !g\.gio_24 \|\| !g\.gio_24\.length\) return "";/.test(U));
check("ba khối: cửa sổ 5 giờ, token từng giờ, giờ cao điểm", /cuaSoHtml\(g\)/.test(U) && /gio24Html\(g, tong24\)/.test(U) && /nhietHtml\(g\.nhiet_7/.test(U));
check("vạch mốc nói rõ là trần tự khai hay mức cao nhất", /usage\.gio\.moc_tran/.test(U) && /usage\.gio\.moc_dinh/.test(U));
check("đường đổi màu theo độ gần trần", /tl >= 0\.9 \? "bad" : tl >= 0\.7 \? "warn" : "ok"/.test(U));
check("biểu đồ ngày giãn hết bề ngang, nhãn đọc được", /\.tk-col\{flex:1 1 0/.test(U) && /\.tk-x\{flex:1 1 0[^}]*font-size:11px/.test(U));

const dung = [...U.matchAll(/t\("(usage\.gio\.[a-z0-9_]+)"/g)].map((m) => m[1]);
const thieu = [...new Set(dung)].filter((k) => !(k in VI) || !(k in EN));
check("mọi khoá usage.gio.* có ở vi và en", dung.length > 10 && thieu.length === 0, thieu.join(", "));
const keysVi = Object.keys(VI).filter((k) => k.startsWith("usage.gio."));
check("vi và en cùng bộ khoá usage.gio.*", keysVi.every((k) => k in EN) && Object.keys(EN).filter((k) => k.startsWith("usage.gio.")).every((k) => k in VI));
check("không gạch ngang dài trong chữ mới", keysVi.every((k) => !/[–—]/.test(VI[k] + EN[k])));

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nOK");
