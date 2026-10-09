/* Trang Cộng sự không còn "thi thoảng không thấy gì" vì một lượt tải danh sách CŨ về muộn (0.88.4).

       node tests/js/test_cong_su_danh_sach_cu.js

   Chủ repo báo 09/10/2026 kèm ảnh: brain "My Bullet Journal" có trợ lý mà trang Cộng sự hiện "Chưa có cộng sự
   nào". Mở app thẳng vào trang này: danh sách brain từ server chưa về nên ô chọn brain tạm là brain mặc định,
   trang tải danh sách của brain đó (rỗng); brain thật về thì trang dựng lại và tải đúng. Lượt tải cũ vẫn đang
   bay, và nếu nó về SAU thì nó đè danh sách đúng bằng danh sách rỗng. Ngoài ra server trả {"error"} cũng bị
   coi là "không có ai", thay vì báo lỗi kèm nút Thử lại.

   Chạy THẬT hàm taiDanhSach (cắt từ workspace.js) với mạng giả điều khiển được thứ tự trả về. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const WS = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "workspace.js"), "utf8");
const fails = [];
const check = (name, cond, detail) => { console.log((cond ? "ok   " : "FAIL ") + name + (cond ? "" : "  [" + detail + "]")); if (!cond) fails.push(name); };

const i = WS.indexOf("  async function taiDanhSach() {");
const fn = WS.slice(i, WS.indexOf("\n  }\n", i) + 4);
check("tìm thấy taiDanhSach", i !== -1 && fn.length > 100, fn.slice(0, 80));

function dung() {
  const cho = [];   // các lời gọi mạng đang chờ: {url, resolve}
  const ctx = {
    S: { agents: [], workflows: [] }, daTai: false, lanDung: 1, _brain: "brain",
    brain() { return ctx._brain; },
    sapXep: (ds) => ds,
    api: (url) => new Promise((res) => cho.push({ url, res })),
    cho,
  };
  vm.createContext(ctx);
  vm.runInContext(fn + "\nglobalThis.taiDanhSach = taiDanhSach;", ctx);
  return ctx;
}
const traLoi = (ctx, brainPart, agents) => ctx.cho.filter((c) => c.url.indexOf(brainPart) !== -1 && !c.xong).forEach((c) => {
  c.xong = true;
  c.res(c.url.indexOf("/agents") === 0 ? { agents } : { workflows: [] });
});

(async () => {
  // ---- 1. Lượt cũ (brain mặc định) về SAU lượt mới (brain thật) ----
  const c = dung();
  const cu = c.taiDanhSach();                 // lần dựng 1, brain mặc định
  c.lanDung = 2; c._brain = "path:D:/brains/My Bullet Journal";
  const moi = c.taiDanhSach();                // lần dựng 2, brain thật
  traLoi(c, "Bullet", [{ slug: "thu-ky", name: "Thư ký" }]);
  const kqMoi = await moi;
  traLoi(c, "brain=brain", []);               // lượt cũ về muộn, danh sách rỗng
  const kqCu = await cu;
  check("lượt mới ghi danh sách thật", kqMoi === true, kqMoi);
  check("lượt cũ về muộn bị bỏ, không đè thành rỗng", kqCu === false && c.S.agents.length === 1, JSON.stringify(c.S.agents));

  // ---- 2. Đổi brain mà không dựng lại (vẫn phải bỏ kết quả của brain cũ) ----
  const c2 = dung();
  const p = c2.taiDanhSach();
  c2._brain = "path:D:/brains/Khac";
  traLoi(c2, "brain=brain", []);
  check("kết quả của brain cũ bị bỏ khi brain đã đổi", (await p) === false && c2.daTai === false);

  // ---- 3. Server trả lỗi: báo lỗi, không giả làm danh sách rỗng ----
  const c3 = dung();
  const p3 = c3.taiDanhSach();
  c3.cho.forEach((x) => { x.res(x.url.indexOf("/agents") === 0 ? { error: "Không đọc được thư mục" } : { workflows: [] }); });
  let nem = null;
  try { await p3; } catch (e) { nem = e; }
  check("server trả {error}: ném lỗi để trang hiện Thử lại", !!nem && /Không đọc được/.test(String(nem.message)), String(nem));
  check("server trả lỗi: không đánh dấu đã tải", c3.daTai === false);

  // ---- 4. Hợp đồng với nơi gọi ----
  check("render tăng lanDung mỗi lần dựng", /opening\+\+; lanDung\+\+;/.test(WS));
  check("nơi gọi lúc dựng trang bỏ qua kết quả cũ",
    /taiDanhSach\(\)\.then\(function \(moi\) \{ if \(moi === false \|\| lanNay !== lanDung\) return;/.test(WS));
  check("lỗi của lượt cũ không vẽ đè lên trang mới", /\.catch\(function \(\) \{ if \(lanNay !== lanDung\) return;/.test(WS));

  if (fails.length) { console.log("\nĐỎ " + fails.length + " mục: " + fails.join(", ")); process.exit(1); }
  console.log("\nTất cả xanh.");
})();
