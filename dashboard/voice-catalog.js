// voice-catalog.js - nam hay nữ của từng giọng Javis có thể nói (0.298.0).
//
// Chủ repo báo 23/10/2026: "cài đặt là nữ nhưng khi nói là giọng nói nam, lưu thế nào cũng không cài được".
// Hai nguyên nhân, cả hai đều ở cách thẻ Giọng nói trình bày:
//   1. Gọi qua ChatGPT Live hay Live qua API thì cuộc gọi nói bằng giọng RIÊNG của nhà cung cấp (juniper,
//      spruce, Puck, cedar...). Danh sách đó hiện tên trần, không ai biết giọng nào nam giọng nào nữ, còn
//      dòng có chữ "Nữ" (Hoài My, Emma) lại là giọng ĐỌC câu trả lời, nằm ở ô khác. Chọn Hoài My xong gọi
//      vẫn nghe giọng nam của cuộc gọi.
//   2. Giọng Edge chỉ lưu trong trình duyệt đang mở; máy khác (điện thoại) vẫn giữ giọng cũ.
// File này lo phần 1: mỗi giọng một nhãn nam/nữ để danh sách tự nói, và hàm so hai ô để thẻ cảnh báo khi
// giọng gọi và giọng đọc khác giới. Thuần, chạy được dưới node (tests/js/test_voice_catalog.js).
//
// Nam/nữ theo mô tả công khai của nhà cung cấp. Giọng không rõ (ElevenLabs, giọng tự nhân bản) là "n":
// không gắn nhãn, không cảnh báo.
(function () {
  "use strict";

  var GIOI = {
    // ChatGPT Live (realtime v3 trên gói ChatGPT)
    juniper: "f", maple: "f", sol: "f", vale: "f",
    arbor: "m", breeze: "m", cove: "m", ember: "m", spruce: "m",
    // Gemini Live
    aoede: "f", kore: "f", leda: "f", zephyr: "f",
    puck: "m", charon: "m", fenrir: "m", orus: "m",
    // OpenAI (Realtime và đọc chữ)
    marin: "f", coral: "f", sage: "f", shimmer: "f", nova: "f",
    cedar: "m", ash: "m", ballad: "m", echo: "m", verse: "m", fable: "m", onyx: "m",
    alloy: "n",
    // Edge (giọng đọc mặc định, miễn phí)
    "en-us-emmamultilingualneural": "f", "vi-vn-hoaimyneural": "f", "en-us-avamultilingualneural": "f",
    "vi-vn-namminhneural": "m", "en-us-andrewmultilingualneural": "m", "en-us-brianmultilingualneural": "m",
    "en-au-williammultilingualneural": "m",
    // "Tự động theo thứ tiếng" chọn Hoài My, Emma hoặc giọng bản xứ, và mọi giọng bản xứ trong voice-lang.js là nữ.
    auto: "f",
  };

  // Giá trị trong ô chọn mang tiền tố nhà cung cấp ("edge:...", "openai:..."); bỏ đi để tra.
  function khoa(giong) {
    var s = String(giong == null ? "" : giong).trim().toLowerCase();
    var i = s.indexOf(":");
    return i >= 0 ? s.slice(i + 1) : s;
  }

  // "f" | "m" | "n"
  function gioiCua(giong) { return GIOI[khoa(giong)] || "n"; }

  // Tên để hiện: "juniper" -> "Juniper". Giọng Edge đã có nhãn riêng trong từ điển nên không qua đây.
  function tenDep(giong) {
    var s = String(giong == null ? "" : giong);
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  }

  // Xếp danh sách giọng thành nhóm nữ, nam, còn lại; giữ thứ tự gốc trong mỗi nhóm.
  function nhomTheoGioi(ds) {
    var out = { f: [], m: [], n: [] };
    (ds || []).forEach(function (g) { out[gioiCua(g)].push(g); });
    return out;
  }

  // Giọng gọi và giọng đọc khác giới (cả hai đều biết rõ nam/nữ): {goi, doc} hoặc null.
  function lechGioi(giongGoi, giongDoc) {
    var a = gioiCua(giongGoi), b = gioiCua(giongDoc);
    if (a === "n" || b === "n" || a === b) return null;
    return { goi: a, doc: b };
  }

  // Giọng đầu tiên trong danh sách có đúng giới `gioi`, hoặc "" khi không có.
  function giongCungGioi(ds, gioi) {
    var hit = (ds || []).filter(function (g) { return gioiCua(g) === gioi; })[0];
    return hit || "";
  }

  var api = { gioiCua: gioiCua, tenDep: tenDep, nhomTheoGioi: nhomTheoGioi, lechGioi: lechGioi,
              giongCungGioi: giongCungGioi };
  if (typeof window !== "undefined") window.JavisVoiceCatalog = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
