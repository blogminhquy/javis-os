/* chat-ask.js - khoi hoi-lai co lua chon cho khung chat Javis.

   Javis ket thuc cau tra loi bang mot khoi an:
     <!-- JAVIS_ASK: {"question":"...","header":"...","options":[{"label":"..","desc":".."}]} -->
   File nay boc khoi do ra, ve thanh hang chip duoi bong bong tra loi, va bat su kien bam.
   Bam mot chip = gui dung nhan do di nhu mot tin nhan nguoi dung binh thuong.

   Di theo dung vet khoi JAVIS_METRICS da chay san (app.js). KHONG dung MCP hub, khong
   dung engine -> chay tren moi bo nao chi nho system prompt.

   An toan: moi text trong khoi la do model sinh ra -> escape het truoc khi nhet vao HTML.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  // Chữ hiện ra lấy từ từ điển. Trong trình duyệt là window.t (i18n/index.js nạp trước mọi
  // module này); dưới node - nơi test require() thẳng file này - `window` CHƯA KHAI BÁO nên
  // đọc window.t là ReferenceError chứ không phải undefined, phải hỏi bằng typeof. Ở đó đọc
  // thẳng vi.json để hàm vẫn trả về chữ thật, không phải mã khoá trần.
  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return tw(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  var ASK_RE = /<!--\s*JAVIS_ASK:\s*([\s\S]*?)\s*-->/;
  var MAX_OPTS = 4;
  var MAX_LABEL = 40;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Cat nhan con MAX_LABEL ky tu. Chi them "…" khi THUC SU cat bot noi dung
  // (nhan dai dung bang tran thi giu nguyen, khong them dau thua).
  function cut(s) {
    s = String(s || "");
    return s.length > MAX_LABEL ? s.slice(0, MAX_LABEL - 1) + "…" : s;
  }

  // Boc khoi JAVIS_ASK khoi text. LUON tra clean da bo khoi (ke ca khi JSON hong) -
  // mot khoi sai cu phap KHONG duoc phep nuot mat cau tra loi cua Javis.
  //
  // Cat nhan (cut) NGAY O DAY - tang du lieu - chu khong cat luc ve (render). Ly do:
  // nut ve ra thu nguoi dung DOC roi moi bam, dung la lop xac nhan cuoi truoc khi noi
  // dung duoc gui di nhu tin nhan cua ho. Neu ve thi cat con click lai gui ban goc chua
  // cat, nhan dai qua tran se hien mot dang nhung gui di mot dang khac - noi dung an
  // (vd do source bi chen lenh sinh ra) co the lot qua duoi danh nghia nguoi dung ma ho
  // chua bao gio thay het. Cat o day dam bao thu hien va thu gui LUON BANG NHAU.
  function extract(text) {
    if (typeof text !== "string") return { clean: "", ask: null };
    var m = text.match(ASK_RE);
    if (!m) return { clean: text, ask: null };
    var clean = text.replace(ASK_RE, "").replace(/\n{3,}/g, "\n\n").trim();
    var ask = null;
    try {
      var o = JSON.parse(m[1]);
      var opts = (o && Array.isArray(o.options) ? o.options : [])
        .filter(function (x) { return x && typeof x.label === "string" && x.label.trim(); })
        .slice(0, MAX_OPTS)
        .map(function (x) {
          return { label: cut(String(x.label).trim()), desc: String(x.desc == null ? "" : x.desc).trim() };
        });
      var q = (o && typeof o.question === "string") ? o.question.trim() : "";
      if (q && opts.length) {
        ask = { question: q, header: String((o && o.header) == null ? "" : o.header).trim(), options: opts };
      }
    } catch (e) {}
    return { clean: clean, ask: ask };
  }

  // Ve hang chip vao cuoi .bubble cua thu tin nhan Javis.
  // live=false -> ve san o trang thai dong cung (dung khi khoi phuc lich su).
  function render(msgEl, ask, live) {
    if (!msgEl || !ask || !ask.options || !ask.options.length) return null;
    var host = msgEl.querySelector(".bubble") || msgEl;
    var old = host.querySelector(".jv-ask");
    if (old) old.parentNode.removeChild(old);   // re-render thi thay, khong chong len nhau
    var box = document.createElement("div");
    box.className = "jv-ask" + (live ? "" : " jv-ask-done");
    var tag = ask.header ? '<span class="jv-ask-tag">' + esc(ask.header) + "</span>" : "";
    var chips = ask.options.map(function (o, i) {
      // label da duoc cut() trong extract() - thu ve va thu gui LUON la cung mot chuoi,
      // khong cat lai o day nua.
      return '<button class="jv-ask-chip" type="button" data-i="' + i + '" title="' +
        esc(o.desc || o.label) + '">' + esc(o.label) + "</button>";
    }).join("");
    box.innerHTML =
      '<div class="jv-ask-q">' + tag + esc(ask.question) + "</div>" +
      '<div class="jv-ask-row">' + chips +
        '<button class="jv-ask-chip jv-ask-other" type="button" data-other="1">' + esc(tw("cask.other")) + "</button>" +
      "</div>";
    box._ask = ask;              // giu lai de doc nhan luc bam chip (nhan trong day da bi cut())
    host.appendChild(box);
    return box;
  }

  // Dong cung moi hang chip dang song. Goi khi co tin nhan moi (bam chip hoac go tay):
  // cuon nguoc len lich su ma bam duoc cau hoi cu se lam roi mach hoi thoai.
  function freezeAll() {
    if (typeof document === "undefined") return;
    var boxes = document.querySelectorAll(".jv-ask:not(.jv-ask-done)");
    Array.prototype.forEach.call(boxes, function (b) { b.classList.add("jv-ask-done"); });
  }

  if (typeof document !== "undefined") {
    document.addEventListener("click", function (e) {
      var chip = e.target.closest ? e.target.closest(".jv-ask-chip") : null;
      if (!chip) return;
      var box = chip.closest(".jv-ask");
      if (!box || box.classList.contains("jv-ask-done")) return;   // lich su: bam khong an gi
      e.preventDefault();
      if (chip.dataset.other) {                                     // "Y khac" = tu go, khong gui gi
        var inp = document.getElementById("chatInput");
        if (inp) inp.focus();
        return;
      }
      var ask = box._ask;
      var opt = ask && ask.options[+chip.dataset.i];
      if (!opt) return;
      chip.classList.add("jv-ask-picked");   // danh dau TRUOC khi gui: JavisSend se freeze ca hang
      if (typeof window.JavisSend === "function") window.JavisSend(opt.label);
    });
  }

  if (typeof window !== "undefined") {
    window.JavisAsk = { extract: extract, render: render, freezeAll: freezeAll };
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { extract: extract };
  }
})();
