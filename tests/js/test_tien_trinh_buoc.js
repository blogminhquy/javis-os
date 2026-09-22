/* Khối tiến trình từng bước trong khung chat (JavisSteps).
 *
 *     node tests/js/test_tien_trinh_buoc.js
 *
 * Vì sao có file này: chủ dự án báo (2026-09-22, kèm ảnh chụp Claude Code) rằng lượt chat lâu
 * thì không biết Javis đang làm gì. Dashboard vốn CÓ nhận sự kiện tool_call, nhưng
 * showActivity() chỉ có một dòng duy nhất: bước mới ghi đè bước cũ, hết lượt thì xoá sạch.
 *
 * Hai thứ đáng khoá bằng test, vì đó đúng là hai chỗ đã hỏng:
 *   1. ĐẾM và GIỮ đủ bước (kể cả khi lượt gọi hàng chục công cụ) chứ không phải chỉ bước cuối.
 *   2. Lượt không gọi công cụ nào thì KHÔNG mọc khối rỗng "Đã chạy 0 bước" giữa khung chat.
 *
 * Không có jsdom trong repo nên DOM giả dưới đây chỉ ghi nhớ chuỗi gán vào innerHTML và trả
 * thẻ stub cho mỗi bộ chọn - đủ để kiểm phần đáng kiểm: vẽ ra bao nhiêu dòng, có escape
 * không, lúc nào thì gấp lại. Cùng kiểu với test_hop_chon_thu_muc.js. */

// ---- DOM giả ----------------------------------------------------------------------------
function theMoi(ten) {
  const el = {
    tagName: ten, className: "", textContent: "", _html: "", _sel: {}, con: [],
    parentNode: null,
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); },
    appendChild(c) { this.con.push(c); c.parentNode = this; return c; },
    querySelector(sel) { return (this._sel[sel] = this._sel[sel] || theMoi("div")); },
    addEventListener(loai, fn) { this["on" + loai] = fn; },
    setAttribute(k, v) { this["attr_" + k] = v; },
    classList: {
      _t: new Set(),
      add(c) { this._t.add(c); }, remove(c) { this._t.delete(c); },
      toggle(c, tren) { if (tren === undefined) { if (this._t.has(c)) this._t.delete(c); else this._t.add(c); } else if (tren) this._t.add(c); else this._t.delete(c); },
      contains(c) { return this._t.has(c); },
    },
  };
  return el;
}
global.document = { createElement: (t) => theMoi(t) };

const S = require("../../dashboard/chat-steps.js");

let fails = [];
function check(name, cond, them) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them ? "  [" + them + "]" : ""));
  if (!cond) fails.push(name);
}

const goi = (ten, noiDung) => ({ type: "tool_call", tool: ten, content: noiDung });

// ---- 1. Một sự kiện tool_call thành một bước --------------------------------------------
let st = S.nhan(null, goi("pos_order", "⚙ Đang gọi: pos_order"));
check("một tool_call: sinh đúng 1 bước", st.ds.length === 1);
check("một tool_call: giữ tên công cụ", st.ds[0].tool === "pos_order");
check("một tool_call: đếm tổng = 1", st.so === 1);
check("nhãn: bỏ ký tự ⚙ dẫn đầu", st.ds[0].label === "Đang gọi: pos_order",
  JSON.stringify(st.ds[0].label));

// ---- 2. Nhiều bước: giữ đủ và ĐÚNG THỨ TỰ (lỗi gốc: chỉ còn bước cuối) -------------------
st = S.nhan(st, goi("zalo_send_message", "⚙ Đang gọi: zalo_send_message"));
st = S.nhan(st, goi("javis_task", "⚙ Đang gọi: javis_task"));
check("ba bước: giữ đủ cả ba", st.ds.length === 3);
check("ba bước: thứ tự trước sau đúng",
  st.ds[0].tool === "pos_order" && st.ds[2].tool === "javis_task");
check("gọi lại cùng một công cụ vẫn là bước riêng",
  S.nhan(S.nhan(null, goi("a")), goi("a")).ds.length === 2);

// ---- 3. Nhãn thiếu / hỏng: không được lòi "undefined" ra màn hình ------------------------
check("thiếu content: nhãn rơi về tên công cụ",
  S.nhan(null, goi("pos_shop")).ds[0].label.indexOf("pos_shop") !== -1);
const trong = S.nhan(null, { type: "tool_call" }).ds[0].label;
check("thiếu cả tên lẫn content: nhãn vẫn có chữ", !!trong.trim());
check("thiếu cả tên lẫn content: không lòi undefined", trong.indexOf("undefined") === -1, trong);

// ---- 4. Sự kiện KHÔNG phải tool_call thì không sinh bước ---------------------------------
check("status không sinh bước",
  S.nhan(null, { type: "status", content: "Javis đang suy nghĩ..." }).ds.length === 0);
check("stream không sinh bước",
  S.nhan(null, { type: "stream", content: "Doanh thu" }).ds.length === 0);

// ---- 5. tool_result đánh dấu bước cuối đã xong -------------------------------------------
let xong = S.nhan(S.nhan(null, goi("pos_order")), { type: "tool_result", content: "ok" });
check("tool_result: đánh dấu bước cuối xong", xong.ds[0].xong === true);
check("tool_result: không sinh thêm bước", xong.ds.length === 1);
check("tool_result lạc lõng (chưa có bước nào): không nổ",
  S.nhan(null, { type: "tool_result" }).ds.length === 0);

// ---- 6. Đầu vào rác: không nổ ------------------------------------------------------------
check("state null + sự kiện null: không nổ", S.nhan(null, null).ds.length === 0);
check("state hỏng: dựng lại được", S.nhan({ ds: "hỏng", so: "x" }, goi("a")).ds.length === 1);

// ---- 7. tomTat: lượt KHÔNG gọi công cụ nào thì ẩn hẳn ------------------------------------
check("chưa có bước nào: khối ẩn", S.tomTat(S.nhan(null, null)).hien === false);
check("state null: khối ẩn", S.tomTat(null).hien === false);
let sau = S.tomTat(st);
check("có 3 bước: khối hiện", sau.hien === true);
check("nhãn tóm tắt có số bước", sau.nhan.indexOf("3") !== -1, sau.nhan);

// ---- 8. Trần: lượt gọi 60 công cụ thì vẫn đếm đủ 60, chỉ CẮT phần hiện -------------------
let dai = null;
for (let i = 1; i <= 60; i++) dai = S.nhan(dai, goi("cong_cu_" + i));
check("60 bước: danh sách hiện bị cắt theo trần", dai.ds.length <= S.TRAN, "" + dai.ds.length);
check("60 bước: tổng vẫn đếm đủ 60", dai.so === 60, "" + dai.so);
check("60 bước: giữ các bước MỚI NHẤT", dai.ds[dai.ds.length - 1].tool === "cong_cu_60");
check("60 bước: nhãn tóm tắt nói 60 chứ không nói 50",
  S.tomTat(dai).nhan.indexOf("60") !== -1, S.tomTat(dai).nhan);

// ---- 9. Vẽ: đang chạy thì bung, xong thì gấp ---------------------------------------------
let el = S.ve(null, st, true);
check("đang chạy: khối bung ra (không có lớp gấp)", el.classList.contains("steps-fold") === false);
S.ve(el, st, false);
check("xong lượt: khối tự gấp lại", el.classList.contains("steps-fold") === true);
check("xong lượt: dòng tóm tắt hiện số bước",
  String(el.querySelector(".steps-sum-text").textContent).indexOf("3") !== -1);

// ---- 10. Vẽ: đủ số dòng, đúng nội dung ---------------------------------------------------
const danhSach = el.querySelector(".steps-list").innerHTML;
check("vẽ đủ 3 dòng bước", (danhSach.match(/class="step[ "]/g) || []).length === 3,
  danhSach.slice(0, 200));
check("vẽ đúng nhãn bước đầu", danhSach.indexOf("pos_order") !== -1);

// ---- 11. Escape: tên công cụ do server gửi, không được chèn thẳng vào HTML ---------------
const doc = S.ve(null, S.nhan(null, goi("<script>alert(1)</script>")), false);
const rac = doc.querySelector(".steps-list").innerHTML;
check("escape: không lọt thẻ <script> nguyên vẹn", rac.indexOf("<script>") === -1, rac.slice(0, 160));
check("escape: vẫn hiện chữ đã escape", rac.indexOf("&lt;script&gt;") !== -1);

// ---- 12. Bấm dòng tóm tắt thì lật gấp / bung ---------------------------------------------
let el2 = S.ve(null, st, false);
check("trước khi bấm: đang gấp", el2.classList.contains("steps-fold") === true);
const nut = el2.querySelector(".steps-sum");
check("dòng tóm tắt có bắt sự kiện bấm", typeof nut.onclick === "function");
if (typeof nut.onclick === "function") {
  nut.onclick();
  check("bấm lần 1: bung ra", el2.classList.contains("steps-fold") === false);
  nut.onclick();
  check("bấm lần 2: gấp lại", el2.classList.contains("steps-fold") === true);
}

console.log(fails.length ? "\n" + fails.length + " FAIL" : "\nTất cả xanh");
process.exit(fails.length ? 1 : 0);
