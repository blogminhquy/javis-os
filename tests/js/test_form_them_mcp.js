/* Form "Tự thêm MCP" trên trang Kết nối: dán cấu hình là tự điền, key nhập theo dòng, và SỬA
 * lại được sau khi thêm.
 *
 *       node tests/js/test_form_them_mcp.js
 *
 * Chủ repo báo 24/09: "thêm MCP hơi khó, ví dụ Composio thì thêm API key như nào, và thêm xong
 * không có chỗ sửa lại các thông số". Composio đưa một link kèm tên header `x-consumer-api-key`;
 * form cũ bắt gõ tay "Tên: giá trị" vào ô văn bản, còn chế độ Sửa có trong code mà không nút nào
 * gọi tới. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const P = require(path.join(ROOT, "dashboard", "mcp-form-parse.js"));
const JS = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "dashboard", "index.html"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

const fails = [];
const check = (ten, ok, them) => {
  console.log((ok ? "ok   " : "FAIL ") + ten + (ok || them === undefined ? "" : "  [" + JSON.stringify(them) + "]"));
  if (!ok) fails.push(ten);
};
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ============================================================
// 1. Đọc cấu hình dán vào
// ============================================================
let d = P.docCauHinh("https://connect.composio.dev/mcp");
check("link trần → kiểu HTTP", d && d.transport === "http" && d.url === "https://connect.composio.dev/mcp", d);
check("tên tự đặt từ tên miền", d && d.name === "composio", d && d.name);
check("Composio: có sẵn dòng x-consumer-api-key để dán key", d && eq(d.headers, { "x-consumer-api-key": "" }), d && d.headers);

d = P.docCauHinh("https://example.com/v1/sse");
check("link đuôi /sse → SSE", d && d.transport === "sse", d);

d = P.docCauHinh(JSON.stringify({ mcpServers: { composio: { url: "https://connect.composio.dev/mcp",
  headers: { "x-consumer-api-key": "ck_abc" } } } }));
check("JSON mcpServers dạng URL: giữ tên, URL và header kèm giá trị",
  d && d.name === "composio" && d.transport === "http" && d.headers["x-consumer-api-key"] === "ck_abc", d);

d = P.docCauHinh('{"mcpServers":{"github":{"command":"npx","args":["-y","@modelcontextprotocol/server-github"],"env":{"GITHUB_TOKEN":"ghp_x"}}}}');
check("JSON mcpServers dạng lệnh → stdio + env",
  d && d.transport === "stdio" && d.command === "npx" && eq(d.args, ["-y", "@modelcontextprotocol/server-github"])
  && d.env.GITHUB_TOKEN === "ghp_x" && d.name === "github", d);

d = P.docCauHinh('"notion": { "type": "http", "url": "https://mcp.notion.com/mcp" }');
check("copy thiếu ngoặc ngoài vẫn đọc được", d && d.name === "notion" && d.url === "https://mcp.notion.com/mcp", d);

d = P.docCauHinh('{"url":"https://a.example/mcp","headers":{"Authorization":"Bearer t"}}');
check("JSON một server không bọc tên", d && d.url === "https://a.example/mcp" && d.headers.Authorization === "Bearer t", d);

d = P.docCauHinh('claude mcp add --transport http composio https://connect.composio.dev/mcp --header "x-consumer-api-key: ck_1"');
check("lệnh claude mcp add có header", d && d.name === "composio" && d.transport === "http"
  && d.headers["x-consumer-api-key"] === "ck_1", d);

d = P.docCauHinh("claude mcp add gh -e GITHUB_TOKEN=abc -- npx -y @modelcontextprotocol/server-github");
check("lệnh claude mcp add dạng stdio", d && d.transport === "stdio" && d.name === "gh" && d.command === "npx"
  && d.env.GITHUB_TOKEN === "abc", d);

d = P.docCauHinh('npx -y mcp-remote https://mcp.example.com/sse --header "Authorization: Bearer k"');
check("npx mcp-remote được đổi về kết nối link trực tiếp", d && d.transport === "sse"
  && d.url === "https://mcp.example.com/sse" && d.headers.Authorization === "Bearer k", d);

d = P.docCauHinh("uvx mcp-server-fetch");
check("lệnh chạy thường → stdio, tên gọn", d && d.transport === "stdio" && d.command === "uvx" && d.name === "fetch", d);

check("chữ vô nghĩa → null (form báo chưa nhận ra)", P.docCauHinh("{ không phải json") === null);
check("rỗng → null", P.docCauHinh("   ") === null);

// ============================================================
// 2. Tách/ghép lệnh giữ được tham số có dấu cách
// ============================================================
check("tách lệnh tôn trọng nháy", eq(P.tachLenh('npx a "b c" \'d e\''), ["npx", "a", "b c", "d e"]));
const args = ["-y", "pkg", "--name", "hai tu", ""];
check("ghép rồi tách lại ra đúng như cũ (Sửa → Lưu không làm vỡ tham số)",
  eq(P.tachLenh(P.ghepLenh("npx", args)), ["npx"].concat(args)), P.ghepLenh("npx", args));

check("nhắc thiếu Bearer khi Authorization chỉ có key trần", P.thieuBearer("Authorization", "sk_abc") === true);
check("không nhắc khi đã có Bearer", P.thieuBearer("authorization", "Bearer sk") === false);
check("không nhắc với header khác", P.thieuBearer("x-api-key", "sk") === false);

// ============================================================
// 3. Form trong console.js
// ============================================================
const HAM = (JS.match(/function openMcpForm\(el, server\) \{[\s\S]*?\n  \}\n/) || [""])[0];
check("bóc được hàm openMcpForm", HAM.length > 2000, HAM.length);
check("mượn vỏ hộp .pkm một cột", /\}, 0, true\)/.test(HAM) || /, 0, true\);/.test(HAM));
check("bấm ra ngoài KHÔNG đóng form đang gõ key", /m\.onclick = null/.test(HAM));
check("key nhập theo dòng tên + giá trị, ẩn như mật khẩu", /mcpf-k/.test(HAM) && /type="password"/.test(HAM));
check("CANARY: không quay lại ô header văn bản thô", !/Authorization: Bearer xxx/.test(HAM) && !/parseKV/.test(JS));
check("lưu xong tự kiểm tra kết nối", /\/connect\/test/.test(HAM));
check("lưu lần hai sau khi thêm là SỬA, không đẻ bản trùng", /editId = r\.id/.test(HAM) && /\/mcp\/update/.test(HAM));
check("sửa gửi prune để xoá được header đã bỏ", /body\.prune = true/.test(HAM));
check("menu kết nối tự thêm có mục Sửa cấu hình", /data-m="edit"/.test(JS) && /act === "edit"[\s\S]{0,80}openMcpForm\(el, c\)/.test(JS));
check("Kết nối lại trên kết nối tự thêm mở form Sửa",
  /function reconnectAccount[\s\S]{0,400}=== "custom"[\s\S]{0,120}openMcpForm\(el, c\)/.test(JS));
check("mcp-form-parse.js nạp TRƯỚC console.js",
  HTML.indexOf("mcp-form-parse.js") > 0 && HTML.indexOf("mcp-form-parse.js") < HTML.indexOf("/static/console.js"));

check("khung dòng ẩn thật sự ẩn (display:flex không đè hidden)", /\.mcpf-ds\[hidden\] \{ display: none; \}/.test(CSS));

// Mọi khoá cs.mf_* mà form gọi phải có trong cả hai bản dịch.
const dung = Array.from(new Set((JS.match(/"cs\.mf_[a-z_]*[a-z]"/g) || []).map(x => x.slice(1, -1))));
dung.push("cs.mf_hint_composio");
const thieu = dung.filter(k => !VI[k] || !EN[k]);
check("đủ bản dịch vi + en cho form", dung.length > 20 && thieu.length === 0, thieu);
const gach = Object.keys(VI).filter(k => k.startsWith("cs.mf_") && /[–—]/.test(VI[k] + (EN[k] || "")));
check("không có gạch ngang dài trong chữ của form", gach.length === 0, gach);

if (fails.length) { console.log("\n" + fails.length + " FAIL"); process.exit(1); }
console.log("\nTất cả xanh");
