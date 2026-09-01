/* Panel VAULT tìm theo TÊN phải hỏi server một phát, không bò cả vault từ trình duyệt.

       node tests/js/test_vault_tim_ten_qua_server.js

   Chủ repo báo 01/09/2026, sau khi đã cập nhật bản vá vòng soi md: *"tìm kiếm ở phần này
   vẫn rất chậm trong khi anh tìm trong tệp tin thì các file load ra cực kỳ nhanh"*.

   Hai ô tìm kiếm, hai đường hoàn toàn khác nhau:
     - Trang Tệp tin: gọi `/files/search` MỘT phát, server đi cây một lượt. Nhanh.
     - Panel VAULT (cột trái): gọi `_vtBuildIndex`, tức BÒ CẢ VAULT TỪ TRÌNH DUYỆT - mỗi thư
       mục một request `/files/list`, đi TUẦN TỰ trong vòng while. Trên máy dev round-trip
       gần bằng 0 nên không ai thấy; trên VPS mỗi request cả trăm mili giây, vault trăm thư
       mục là hàng chục giây trắng màn hình.

   Test này KHÔNG soi chữ trong mã (bản đầu làm vậy và nó xanh cả khi nhánh fetch bị vô hiệu
   hoá - vô dụng). Nó BÓC nguyên văn hàm `_vtNameSearch` ra khỏi console.js rồi CHẠY THẬT với
   fetch giả, đếm xem đường nào được gọi. Hai ca:
     1. Server trả lời được  -> đúng MỘT request /files/search, TUYỆT ĐỐI không bò.
     2. Server cũ chưa có endpoint (404) -> phải rơi về đường bò, không được chết câm. */
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const con = read("dashboard/console.js");
const html = read("dashboard/index.html");

let fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  [" + extra + "]"));
  if (!cond) fails.push(name);
}

// ---- Bóc nguyên văn hàm ra khỏi file nguồn ----
const src = (con.match(/\n  async function _vtNameSearch\(q\)[\s\S]*?\n  \}\n/) || [""])[0];
check("bóc được hàm _vtNameSearch từ console.js", src.length > 0);

// Bệ đỡ tối thiểu: chỉ những thứ hàm thật sự chạm tới.
const STUB = `
  const box = { innerHTML: "" };
  const document = { getElementById: () => box };
  const fbrain = () => "Brain Default";
  const esc = (s) => String(s == null ? "" : s);
  let _render = null;
  const _vtRenderResults = (b, list) => { _render = list; };
  const _vtNoAccent = (s) => String(s || "").toLowerCase();
  const _vtBuildIndex = async () => {
    calls.push("CRAWL");
    return [{ name: "KPI Funnel.md", ext: ".md", path: "00 - Dashboard/KPI Funnel.md", dir: "00 - Dashboard" }];
  };
`;

function chay(fetchGia) {
  const calls = [];
  // Ghi lại URL ngay ở đây: `calls` là thứ duy nhất test soi được, và nó phải đếm cả request
  // lẫn lượt bò để so hai đường với nhau.
  const fetchDem = async (u, ...r) => { calls.push(String(u)); return fetchGia(u, ...r); };
  const factory = new Function("calls", "fetch", STUB + src
    + "\n return { fn: _vtNameSearch, ket: () => _render, hop: () => box };");
  const o = factory(calls, fetchDem);
  return { calls, ...o };
}

// ---- Ca 1: server trả lời được ----
const dapAn = {
  items: [{ name: "KPI Funnel Webinar.md", ext: ".md",
            path: "00 - Dashboard/KPI Funnel Webinar.md", snippet: "", line: 0, match: "name" }],
};
const okFetch = async () => ({ ok: true, status: 200, json: async () => dapAn });

(async () => {
  const a = chay(okFetch);
  await a.fn("KPI Funnel Webinar Tripwir");
  const urls = a.calls.filter(c => c !== "CRAWL");
  check("server trả lời được: KHÔNG bò vault (đây là cả cái bug)", !a.calls.includes("CRAWL"), a.calls);
  check("và chỉ gửi ĐÚNG 1 request", urls.length === 1, urls.length);
  check("request đó là /files/search", urls[0] && urls[0].indexOf("/files/search?") === 0, urls[0]);
  check("hỏi đúng mode=name", /mode=name/.test(urls[0] || ""));
  check("có kèm brain và limit", /brain=Brain%20Default/.test(urls[0] || "") && /limit=\d+/.test(urls[0] || ""),
        urls[0]);
  const ket = a.ket() || [];
  check("vẽ ra đúng kết quả server trả về", ket.length === 1 && ket[0].name === "KPI Funnel Webinar.md", ket);
  check("giữ nguyên path của server (đúng quy ước openNote đang dùng)",
        ket[0] && ket[0].path === "00 - Dashboard/KPI Funnel Webinar.md", ket[0] && ket[0].path);
  check("tự suy ra thư mục chứa file để hiện dưới tên",
        ket[0] && ket[0].dir === "00 - Dashboard", ket[0] && ket[0].dir);

  // ---- Ca 2: server CŨ chưa có endpoint -> phải rơi về đường bò ----
  const b = chay(async () => ({ ok: false, status: 404, json: async () => ({}) }));
  await b.fn("KPI");
  check("server 404: rơi về đường bò cũ, không chết câm", b.calls.includes("CRAWL"), b.calls);
  check("và vẫn ra kết quả", (b.ket() || []).length === 1, b.ket());

  // ---- Ca 3: mất mạng giữa chừng cũng phải có đường lui ----
  const c = chay(async () => { throw new Error("network down"); });
  await c.fn("KPI");
  check("fetch ném lỗi: vẫn rơi về đường bò", c.calls.includes("CRAWL"), c.calls);

  // ---- Ca 4: không có kết quả thì báo rõ, không vẽ danh sách rỗng ----
  const d = chay(async () => ({ ok: true, status: 200, json: async () => ({ items: [] }) }));
  await d.fn("khongcogi");
  check("không thấy gì: KHÔNG bò thêm lần nữa", !d.calls.includes("CRAWL"), d.calls);
  check("và nói rõ là không thấy", /Không thấy note nào/.test(d.hop().innerHTML), d.hop().innerHTML);

  // ---- Ô "Nội dung" không bị đụng tới ----
  check("tìm theo NỘI DUNG vẫn gọi /files/search như cũ",
    /async function _vtSearchContent[\s\S]{0,600}\/files\/search\?brain=/.test(con));
  check("_vtBuildIndex vẫn còn trong file (server cũ 404 thì cần tới)",
    /async function _vtBuildIndex\(\)/.test(con));

  // ---- cache-bust ----
  const v = (f) => Number((html.match(new RegExp(f.replace(/\./g, "\\.") + "\\?v=(\\d+)")) || [])[1] || 0);
  check("console.js đã bump ?v= (>= 121)", v("console.js") >= 121, v("console.js"));

  console.log();
  if (fails.length) {
    console.log("THAT BAI " + fails.length + ": " + fails.join(", "));
    process.exit(1);
  }
  console.log("OK - test_vault_tim_ten_qua_server: tat ca pass");
})();
