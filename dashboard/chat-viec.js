/* chat-viec.js - the viec nen (viec ngam) trong khung chat Javis (0.64.48).

   Van de (chu repo bao 2026-09-24: "man hinh hien thi cua tao viec ngam trong luc chat trong
   rat chan va tho ket"): ket qua viec nen quay ve khung chat chi la mot bong bong chu tron,
   dau dong la emoji server dan cung, cuoi dong la cau "Xem chi tiet o trang Viec." khong bam
   duoc. Luc giao viec bang giong thi chi co mot dong chu nghieng mo, F5 la mat.

   Server nay gan kem mot khoi an o dau noi dung:
       <!-- JAVIS_VIEC: {"kind":"task","status":"done","title":"...","id":"..."} -->
   (cung khuon voi JAVIS_ASK). File nay boc khoi do ra va ve:
     - the KET QUA: dong dau co icon trang thai, nhan ("Viec nen xong", "bi chan"...), ten viec
       va nut mo trang Viec; than la markdown nhu moi cau tra loi.
     - dong DA GIAO (status "giao"): mot dong gon duoi cau xac nhan cua giong noi.
   Khoi nam ngay trong noi dung da luu nen F5, mo lai hoi thoai, localStorage deu ve lai dung.

   Ham `tach` THUAN de test bang node. Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  var RE = /<!--\s*JAVIS_VIEC:\s*([\s\S]*?)\s*-->\s*/;

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

  var TRANG_THAI = {
    done: { ic: "circle-check", nhan: "viec.st_done" },
    review: { ic: "clipboard-check", nhan: "viec.st_review" },
    blocked: { ic: "triangle-alert", nhan: "viec.st_blocked" },
    failed: { ic: "circle-x", nhan: "viec.st_failed" },
    timeout: { ic: "hourglass", nhan: "viec.st_timeout" },
    cancelled: { ic: "circle-stop", nhan: "viec.st_cancelled" },
    giao: { ic: "loader", nhan: "viec.st_giao" }
  };

  /* Boc khoi JAVIS_VIEC. LUON tra `clean` da bo khoi, ke ca khi JSON hong: mot khoi hong
     khong duoc phep lot ra man hinh hay bi doc thanh tieng. */
  function tach(text) {
    var s = String(text == null ? "" : text);
    var m = s.match(RE);
    if (!m) return { clean: s, viec: null };
    var clean = (s.slice(0, m.index) + s.slice(m.index + m[0].length)).replace(/^\s+|\s+$/g, "");
    var v = null;
    try { v = JSON.parse(m[1]); } catch (e) { v = null; }
    if (!v || typeof v !== "object") return { clean: clean, viec: null };
    var st = String(v.status || "done");
    return {
      clean: clean,
      viec: {
        kind: String(v.kind || "task"),
        status: TRANG_THAI[st] ? st : "done",
        title: String(v.title || "").slice(0, 200),
        id: String(v.id || "")
      }
    };
  }

  function icon(ten, cls) {
    return (typeof ic === "function") ? ic(ten, cls ? { cls: cls } : undefined) : "";
  }

  // Loop va nhac hen song o trang Viec dinh ky, khong phai bang Kanban (0.64.49).
  function trangCua(kind) {
    return (kind === "loop" || kind === "reminder") ? "selfimprove" : "kanban";
  }

  function moTrang(trang) {
    try { window.Alpine.store("nav").go(trang); } catch (err) { location.hash = "#" + trang; }
  }

  // Nhan theo LOAI truoc ("viec.loop_done": "Vong lap vua chay"), khong co thi nhan chung.
  function nhanCua(viec) {
    var rieng = "viec." + viec.kind + "_" + viec.status;
    var chu = tw(rieng);
    if (chu && chu !== rieng) return chu;
    return tw((TRANG_THAI[viec.status] || TRANG_THAI.done).nhan);
  }

  function iconCua(viec) {
    if (viec.kind === "reminder" && viec.status === "done") return "alarm-clock";
    return (TRANG_THAI[viec.status] || TRANG_THAI.done).ic;
  }

  /* Dong dau cua the ket qua. Tra chuoi HTML (da escape). */
  function dauThe(viec) {
    var trang = trangCua(viec.kind);
    return '<div class="viec-head">' +
      '<span class="viec-ico">' + icon(iconCua(viec)) + "</span>" +
      '<span class="viec-nhan">' + esc(nhanCua(viec)) + "</span>" +
      (viec.title ? '<span class="viec-ten" title="' + esc(viec.title) + '">' + esc(viec.title) + "</span>" : "") +
      '<button type="button" class="viec-mo" data-trang="' + trang + '">' + icon("square-kanban") +
      "<span>" + esc(tw(trang === "kanban" ? "viec.mo_trang" : "viec.mo_dinh_ky")) + "</span></button>" +
      "</div>";
  }

  /* Dong "da giao lam nen" gon, nam duoi cau xac nhan cua giong noi. */
  function dongGiao(viec) {
    return '<div class="viec-giao">' + icon("list-todo") +
      "<span>" + esc(tw("viec.da_giao")) + "</span>" +
      (viec.title ? '<span class="viec-ten">' + esc(viec.title) + "</span>" : "") + "</div>";
  }

  /* Trang tri mot bong bong .msg-javis da ve xong theo khoi viec. */
  function ve(msgEl, viec) {
    if (!msgEl || !viec) return msgEl;
    if (viec.status === "giao") {
      var cu = msgEl.querySelector && msgEl.querySelector(".viec-giao");
      if (cu && cu.parentNode) cu.parentNode.removeChild(cu);
      var bubble0 = msgEl.querySelector(".bubble");
      if (bubble0 && bubble0.insertAdjacentHTML) bubble0.insertAdjacentHTML("afterend", dongGiao(viec));
      return msgEl;
    }
    msgEl.classList.add("msg-viec");
    msgEl.classList.add("viec-" + viec.status);
    var bubble = msgEl.querySelector(".bubble");
    if (bubble && bubble.insertAdjacentHTML) bubble.insertAdjacentHTML("afterbegin", dauThe(viec));
    var nut = msgEl.querySelector(".viec-mo");
    if (nut && nut.addEventListener) {
      var trang = trangCua(viec.kind);
      nut.addEventListener("click", function () { moTrang(trang); });
    }
    return msgEl;
  }

  var API = { tach: tach, ve: ve, dauThe: dauThe, dongGiao: dongGiao, TRANG_THAI: TRANG_THAI };
  if (typeof window !== "undefined") window.JavisViec = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
