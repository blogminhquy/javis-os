/* chat-steps.js - khoi "tien trinh tung buoc" trong khung chat Javis.

   Van de: server DA ban ra su kien tool_call cho moi engine (main.py), nhung dashboard chi co
   MOT dong trang thai (showActivity): buoc moi ghi de buoc cu, het luot thi xoa sach. Luot
   chay lau thi nguoi dung ngoi nhin mot dong nhay loan, khong biet da lam nhung gi.

   File nay gom cac buoc do lai thanh mot khoi nam ngay tren bong bong tra loi:
     - dang chay: bung san, buoc cuoi dang chay duoc danh dau
     - xong luot: tu gap thanh mot dong "Da chay N buoc", bam vao bung ra xem lai

   Chia lam hai tang de test duoc bang node: `nhan`/`tomTat` la ham THUAN (khong dung DOM),
   con `taoKhoi`/`ve` chi ve. Khong goi MCP, khong phu thuoc engine.

   An toan: nhan buoc la chu do SERVER gui xuong (ten cong cu, nhan do model dat) nen phai
   escape het truoc khi nhet vao innerHTML.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  // Tran so buoc GIU LAI de ve. Mot loop goi hang tram cong cu thi ve het la dung khung chat
  // lam bai log. Tong so buoc van dem du (truong `so`) nen dong tom tat khong noi doi.
  var TRAN = 50;

  // Chu hien ra lay tu tu dien. Trong trinh duyet la window.t; duoi node - noi test require()
  // thang file nay - `window` CHUA KHAI BAO nen phai hoi bang typeof, roi doc thang vi.json.
  // Cung khuon voi chat-ask.js.
  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  function esc(t) {
    return String(t == null ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Nhan mot dong buoc. Server da dat san cau nguoi doc duoc ("Dang goi: pos_order"), kem mot
  // ky tu banh rang U+2699 dan dau - bo no di vi khoi nay tu ve icon rieng.
  // Cat bang lop "moi ky tu dau khong phai chu/so" chu KHONG viet thang ky tu banh rang vao
  // day: test_icons.py cam emoji trong file dashboard. Luat rong nay cung ben hon khi server
  // doi sang dau khac.
  function nhanBuoc(ev) {
    var noi = String((ev && ev.content) || "").replace(/^[^\p{L}\p{N}]+/u, "").trim();
    if (noi) return noi;
    var ten = String((ev && ev.tool) || "").trim();
    return ten || tw("app.step_unknown");
  }

  function chuanHoa(st) {
    var ds = (st && Array.isArray(st.ds)) ? st.ds : [];
    var so = (st && typeof st.so === "number" && isFinite(st.so)) ? st.so : ds.length;
    return { ds: ds, so: so };
  }

  /* Gop mot su kien WS vao mach buoc. Ham THUAN: tra ve state MOI, khong sua state cu.
     Chi tool_call moi sinh buoc - `status` ("dang suy nghi") va `stream` la trang thai cua ca
     luot, khong phai viec da lam. */
  function nhan(st, ev) {
    var cu = chuanHoa(st);
    var loai = ev && ev.type;
    if (loai === "tool_call") {
      var ds = cu.ds.concat([{ tool: String((ev && ev.tool) || ""), label: nhanBuoc(ev), xong: false }]);
      if (ds.length > TRAN) ds = ds.slice(ds.length - TRAN);   // giu cac buoc MOI NHAT
      return { ds: ds, so: cu.so + 1 };
    }
    if (loai === "tool_result") {
      // Danh dau buoc dang chay la xong. Khung tool_result lac long (chua co buoc nao) thi bo
      // qua - khong phai loi, chi la engine ban ket qua cua thu khong di qua day.
      for (var i = cu.ds.length - 1; i >= 0; i--) {
        if (!cu.ds[i].xong) {
          var ds2 = cu.ds.slice();
          ds2[i] = { tool: cu.ds[i].tool, label: cu.ds[i].label, xong: true };
          return { ds: ds2, so: cu.so };
        }
      }
    }
    return cu;
  }

  /* Luot KHONG goi cong cu nao thi `hien` = false: app.js khong dung khoi nao ca. Mot dong
     xam "Da chay 0 buoc" duoi moi cau chao hoi la rac. */
  function tomTat(st) {
    var cu = chuanHoa(st);
    return { hien: cu.ds.length > 0, so: cu.so, nhan: tw("app.steps_done", { n: cu.so }) };
  }

  function chevron() {
    return (typeof ic === "function") ? ic("chevron-down") : "›";
  }

  function taoKhoi() {
    var el = document.createElement("div");
    el.className = "msg msg-steps steps-fold";
    el.innerHTML =
      '<button class="steps-sum" type="button">' + chevron() +
      '<span class="steps-sum-text"></span></button>' +
      '<div class="steps-list"></div>';
    var nut = el.querySelector(".steps-sum");
    if (nut) {
      nut.setAttribute("aria-label", tw("app.steps_toggle"));
      nut.addEventListener("click", function () { el.classList.toggle("steps-fold"); });
    }
    return el;
  }

  /* Ve lai khoi theo mach buoc. `dangChay` quyet dinh bung hay gap: dang chay thi bung de
     nguoi dung nhin thay viec dang lam, xong luot thi gap lai nhuong cho cau tra loi. */
  function ve(el, st, dangChay) {
    if (!el) el = taoKhoi();
    var cu = chuanHoa(st);
    var txt = el.querySelector(".steps-sum-text");
    if (txt) txt.textContent = dangChay ? tw("app.steps_running") : tomTat(cu).nhan;
    var ds = el.querySelector(".steps-list");
    if (ds) {
      ds.innerHTML = cu.ds.map(function (b, i) {
        var song = dangChay && i === cu.ds.length - 1 && !b.xong;
        return '<div class="step' + (song ? " step-live" : "") + (b.xong ? " step-done" : "") +
               '">' + esc(b.label) + "</div>";
      }).join("");
    }
    el.classList.toggle("steps-fold", !dangChay);
    return el;
  }

  var API = { nhan: nhan, tomTat: tomTat, taoKhoi: taoKhoi, ve: ve, TRAN: TRAN };
  if (typeof window !== "undefined") window.JavisSteps = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
