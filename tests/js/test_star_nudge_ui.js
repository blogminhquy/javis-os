/* Thẻ mời tặng sao GitHub (0.324.0): được gọi ở đúng khoảnh khắc, vẽ đúng thứ người dùng cần.

       node tests/js/test_star_nudge_ui.js

   Chủ repo 25/10/2026: mời ở khoảnh khắc vui (lần đầu thả tim là dễ nhất), viết cho người không
   biết GitHub, hình minh hoạ trực quan, linh vật là ngôi sao của logo Javis, số sao không viết
   cứng. Test này canh các dây nối dễ đứt im lặng: sửa chat-reactions.js hay app.js mà quên sự
   kiện thì thẻ không bao giờ hiện, và không ai thấy lỗi. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const rd = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const SN = rd("dashboard/star-nudge.js");
const CSS = rd("dashboard/star-nudge.css");
const CR = rd("dashboard/chat-reactions.js");
const APP = fs.readFileSync(path.join(ROOT, "dashboard/app.js")).toString("utf8");
const CON = rd("dashboard/console.js");
const IDX = rd("dashboard/index.html");
const LOGO = rd("dashboard/logo.svg");
const VI = JSON.parse(rd("dashboard/i18n/vi.json"));
const EN = JSON.parse(rd("dashboard/i18n/en.json"));

const fails = [];
const check = (ten, ok, them) => {
  console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + them + "]"));
  if (!ok) fails.push(ten);
};

// 1. Dây nối các khoảnh khắc vui
check("thả tim/like thành công phát javis:react-positive",
  /rv === "love" \|\| rv === "like"[\s\S]{0,160}javis:react-positive/.test(CR));
check("star-nudge nghe sự kiện thả tim", /addEventListener\("javis:react-positive", function \(\) \{ moment\("heart"\); \}\)/.test(SN));
check("app.js: việc nền trả kết quả là một khoảnh khắc", /data\.type === "inbox"[\s\S]{0,600}JavisStar\.moment\("work"\)/.test(APP));
check("app.js: lượt làm từ 3 bước trở lên là một khoảnh khắc", /t\.buoc\.so\) \|\| 0\) >= 3[\s\S]{0,40}JavisStar\.moment\("work"\)/.test(APP));
check("mở app thì hỏi server có cột mốc / bản mới không", /moment\("load"\)/.test(SN));
check("trang Cập nhật có thẻ Ủng hộ Javis", /JavisStar\.theUngHo\(\)/.test(CON) && /\.sn-ho \.sn-go/.test(CON));
check("nút Tặng sao ở góc trái", /querySelector\("\.rail-foot"\)/.test(SN) && /rf-star/.test(CSS));
// Chủ repo 25/10: nhét nút vào cột phiên bản thì "Give a star" gãy làm hai dòng. Nút là hàng riêng,
// trải hết bề ngang, chữ một dòng; thanh thu gọn chỉ còn ngôi sao.
check("nút Tặng sao là hàng riêng, không nằm trong cột phiên bản",
  !/rf-meta[\s\S]{0,80}appendChild\(b\)/.test(SN) && /\.rail-foot \{ flex-wrap: wrap; \}/.test(CSS) &&
  /\.rail-foot \.rf-star \{[^}]*flex: 1 0 100%/.test(CSS));
check("chữ nút một dòng", /\.rail-foot \.rf-star \{[^}]*white-space: nowrap/.test(CSS));
check("thanh thu gọn: chỉ còn ngôi sao", /\.rail\.collapsed \.rail-foot \.rf-star-chu \{ display: none; \}/.test(CSS));
check("index nạp css và js", /\/static\/star-nudge\.css\?v=\d+/.test(IDX) && /\/static\/star-nudge\.js\?v=\d+/.test(IDX));

// 2. Không làm phiền
check("không bung khi đang gõ dở hay tab đang ẩn", /function dangBan\(\)/.test(SN) && /document\.hidden/.test(SN));
check("server bảo chưa thì nghỉ hỏi một lúc", /NGHI_HOI = 30 \* 60 \* 1000/.test(SN));
check("bốn lựa chọn đều ghi về server", ["later", "never", "done", "dismiss"].every((a) => SN.includes('"' + a + '"')));

// 3. Viết cho người không biết GitHub
check("có hình minh hoạ nút Star, bản máy tính và bản điện thoại", /function minhHoa\(/.test(SN) && /sn-gh-dt/.test(SN));
check("bước đăng nhập nhắc Continue with Google", /Continue with Google/.test(VI["star.step3"]) && /Continue with Google/.test(EN["star.step3"]));
check("bước 2 nói đúng vị trí theo thiết bị", /dt \? "star\.step2_dt" : "star\.step2"/.test(SN));
check("số sao đọc từ server, không viết cứng", /phanSo\(d\.count\)/.test(SN) && !/\b286\b/.test(SN));

// 4. Linh vật là ngôi sao của logo Javis
const saoLogo = (LOGO.match(/<path d="(M145 81[^"]+)"/) || [])[1];
const saoThe = (SN.match(/var SAO_JAVIS = ([\s\S]*?);\n/) || [])[1];
const noiChuoi = saoThe ? saoThe.replace(/"\s*\+\s*"/g, "").replace(/^"|"$/g, "").trim() : "";
check("đường hình sao trùng logo.svg", !!saoLogo && noiChuoi === saoLogo, noiChuoi.slice(0, 40));
check("màu thân và viền của logo", /fill: #FD6100/.test(CSS) && /stroke: #FBBA9C/.test(CSS));

// 5. Chữ đủ to cho điện thoại, có chừa cho người tắt chuyển động
const nho = [...CSS.matchAll(/\.sn-[a-z-]+[^{]*\{[^}]*font(?:-size)?:[^;}]*?(\d+(?:\.\d+)?)px/g)]
  .filter((m) => !/sn-gh/.test(m[0]) && Number(m[1]) < 16).map((m) => m[0].split("{")[0].trim());
check("chữ trong thẻ từ 16px (trừ hình minh hoạ GitHub)", nho.length === 0, nho.join(", "));
check("tôn trọng prefers-reduced-motion", /prefers-reduced-motion: reduce/.test(CSS));

// 6. Từ điển
const ks = Object.keys(VI).filter((k) => k.startsWith("star."));
check("vi và en cùng bộ khoá star.*", ks.length > 20 && ks.every((k) => k in EN) &&
  Object.keys(EN).filter((k) => k.startsWith("star.")).every((k) => k in VI));
const dung = [...SN.matchAll(/t\("(star\.[a-z0-9_]+)"/g)].map((m) => m[1]);
const thieu = dung.filter((k) => !(k in VI));
check("mọi khoá dùng trong JS đều có trong từ điển", thieu.length === 0, thieu.join(", "));
["d30", "d100", "d365", "d730", "d1095"].forEach((k) => check("có nhãn kỷ niệm star." + k, ("star." + k) in VI));
["heart", "work", "update", "manual"].forEach((k) => check("có lời chào star.hi_" + k, ("star.hi_" + k) in VI));

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nOK");
