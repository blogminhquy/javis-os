/* Quả cầu não phải ĐÓNG BĂNG khi không có gì động, và sống lại NGAY khi có.
 *
 *     node tests/js/test_qua_cau_nghi_khi_ranh.js
 *
 * Vì sao có file này. Chủ dự án báo 2026-09-22: vợ anh dùng bản mới trên máy yếu và kêu
 * "siêu đơ". Đo trên bộ não 844 note (Chromium, CDP Performance.TaskDuration): màn chính ăn
 * 34% một nhân CPU trong lúc KHÔNG AI ĐỤNG VÀO GÌ. Hồ sơ CPU cho thấy thủ phạm không phải
 * JavaScript (chỉ ~5%) mà là phần TÔ ĐIỂM ẢNH của trình duyệt: đồ thị được đặt
 * `autoPauseRedraw(false)`, tức là vẽ lại mọi khung hình mãi mãi, kể cả khi vật lý đã nguội
 * và bức vẽ ra giống hệt bức trước. Tắt phần vẽ thừa đó: 34% xuống 19%.
 *
 * Nhưng nhẹ mà hỏng thì vô nghĩa, nên file này canh CẢ HAI chiều:
 *   - rảnh thì phải đóng băng (nếu không, lỗi hiệu năng quay lại trong im lặng);
 *   - có giọng nói, có nhịp NGHĨ, hoặc con trỏ chạm vào vùng đồ thị thì phải vẽ lại NGAY.
 *
 * Chiều thứ hai quan trọng hơn người ta tưởng: thư viện đồ thị dò con trỏ đang ở trên chấm
 * nào NGAY TRONG vòng vẽ của nó. Dừng vẽ thì nó thôi dò, nên nếu chỉ dựa vào onNodeHover để
 * bật lại thì thành con gà quả trứng và hiệu ứng rọi sáng chết hẳn. Vì thế phải nghe chuột
 * ngay trên khung chứa. Đã kiểm trên Chromium thật: đứng yên 0 lần vẽ/giây, đưa chuột vào
 * vùng đồ thị lên 44 lần/giây, rời ra thì về 0. */
global.window = global;
global.document = { createElement: () => ({ getContext: () => null }) };
global.window.dispatchEvent = () => {};
// Đồng hồ giả chạy MỘT CHIỀU cho cả file. Bản đầu của test này vặn đồng hồ tiến rồi trả về
// thật, khiến thời gian ĐI LÙI - chuyện performance.now() không bao giờ làm - và test tự đỏ
// vì một tình huống không có ngoài đời.
let _gio = 1e6;
global.performance = { now: () => _gio };
const troi = (ms) => { _gio += ms; };

require("../../dashboard/graph.js");
const JavisGraph = window.JavisGraph;

let fails = 0;
const check = (ten, ok) => { console.log((ok ? "ok   " : "FAIL ") + ten); if (!ok) fails++; };

// Khung chứa giả: chỉ cần ghi lại các bộ nghe chuột đã đăng ký.
function khungGia() {
  const nghe = {};
  return {
    nghe,
    addEventListener(loai, fn) { (nghe[loai] = nghe[loai] || []).push(fn); },
    ban(loai) { (nghe[loai] || []).forEach((fn) => fn({})); },
    contains: () => true,
  };
}
// Đồ thị giả: nhớ MỌI lần bị gọi autoPauseRedraw.
function doThiGia(log) {
  return { autoPauseRedraw(v) { log.push(v); return this; } };
}

const log = [];
const cont = khungGia();
const g = new JavisGraph(cont, {});
g.graph = doThiGia(log);
g.container = cont;
g._ngheChuot();

// ---- 1. Mặc định là NGHỈ ----
check("mới dựng thì chưa vẽ liên tục", g._veLienTuc === false);
check("nguồn đã khai autoPauseRedraw(true), không còn (false)", (() => {
  const src = require("fs").readFileSync(require("path").join(__dirname, "..", "..", "dashboard", "graph.js"), "utf8");
  return /\.autoPauseRedraw\(true\)/.test(src) && !/\.autoPauseRedraw\(false\)/.test(src);
})());

// ---- 2. Im lặng thì KHÔNG bật vẽ ----
for (let i = 0; i < 5; i++) g.setLevel(0);
check("im lặng: vẫn đóng băng", g._veLienTuc === false);
check("và không hề gọi thư viện lần nào", log.length === 0);

// ---- 3. Có tiếng nói thì bật NGAY ----
g.setLevel(0.9);
check("có giọng nói: vẽ liên tục ngay", g._veLienTuc === true);
check("đã bảo thư viện thôi bỏ khung", log[log.length - 1] === false);

// ---- 4. Dứt tiếng: còn ân hạn thì CHƯA đóng băng ----
// Mức âm xuống CHẬM có chủ đích (6% mỗi nhịp, xem setLevel), nên phải hạ hẳn xuống dưới
// ngưỡng rồi mới đo được quãng ân hạn - đây chính là chỗ bản đầu của test này đoán sai.
for (let i = 0; i < 5; i++) g.setLevel(0);
check("vừa dứt tiếng: mức âm còn cao nên vẫn vẽ", g._veLienTuc === true);
for (let i = 0; i < 200; i++) g.setLevel(0);
check("mức âm đã về 0 nhưng còn ân hạn: vẫn vẽ", g._veLienTuc === true);

// ---- 5. Hết ân hạn thì đóng băng ----
troi(JavisGraph.AN_HAN_MS + 50);
g.setLevel(0);
check("hết ân hạn: đóng băng lại", g._veLienTuc === false);
check("và đã bảo thư viện tự bỏ khung", log[log.length - 1] === true);

// ---- 6. Nhịp NGHĨ cũng đánh thức ----
g.setThinking(true);
check("đang nghĩ: vẽ liên tục", g._veLienTuc === true);
g.setThinking(false);
for (let i = 0; i < 200; i++) g.setLevel(0);
troi(JavisGraph.AN_HAN_MS + 50);
g.setLevel(0);
check("nghĩ xong, hết ân hạn: đóng băng", g._veLienTuc === false);

// ---- 7. CHỐT QUAN TRỌNG NHẤT: chuột chạm vào là sống lại ----
// Thiếu vế này thì hover chết mà test vẫn xanh - đúng kiểu "nhẹ đi bằng cách bỏ tính năng".
check("có nghe chuột trên khung chứa đồ thị",
  !!cont.nghe.pointerenter && !!cont.nghe.pointermove && !!cont.nghe.pointerleave);
cont.ban("pointerenter");
check("chuột chạm vào vùng đồ thị: vẽ lại NGAY", g._veLienTuc === true);
cont.ban("pointermove");
check("rê tiếp vẫn giữ vẽ", g._veLienTuc === true);
cont.ban("pointerleave");
for (let i = 0; i < 200; i++) g.setLevel(0);
troi(JavisGraph.AN_HAN_MS + 50);
g.setLevel(0);
check("chuột rời ra, hết ân hạn: đóng băng lại", g._veLienTuc === false);

// ---- 8. Không gọi thư viện thừa ----
const truoc = log.length;
for (let i = 0; i < 50; i++) g.setLevel(0);
check("đang đóng băng mà bị gọi 50 lần: không đổi trạng thái thì không gọi lại thư viện",
  log.length === truoc);

console.log("");
if (fails) { console.log("FAIL " + fails + " mục"); process.exit(1); }
console.log("TẤT CẢ PASS");
