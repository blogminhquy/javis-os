/* task-suggest.js - goi y task kieu plugin obsidian-tasks, BAN GON cho editor Javis.
   Hoat dong trong ban render dang sua (.ne-wys, ca editor cay lan khung sua tu chat):

   1) Go "- [ ]" roi AN CACH o dau mot dong thuong -> tu bien thanh task that (checkbox).
   2) Dung CUOI mot dong task, AN CACH -> bung menu goi y NGAN (6 muc, khong ngop nhu
      Obsidian): 📅 han chot, ⏳ du kien, 🛫 bat dau, ⏫🔼🔽 uu tien.
   3) Chon muc ngay -> bung tiep: Hom nay / Ngay mai / Cuoi tuan / Tuan sau / Chon ngay...
      -> chen "📅 2026-07-28 " ngay tai cho. Esc dong menu, go tiep thi menu tu tat.

   Ky hieu chen ra dung chuan obsidian-tasks nen dataview/tasks block va server deu hieu.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  // File nay chay hai che do: trong trinh duyet va duoi node (test require no).
  // Duoi node khong co window nen khong co ic() - tra ve chuoi rong de phan logic
  // van test duoc ma khong phai keo ca tang icon vao.
  var ic = (typeof window !== "undefined" && window.ic) ? window.ic : function () { return ""; };

  // Chu hien ra lay tu tu dien. Trong trinh duyet la window.t (i18n/index.js nap dau tien);
  // duoi node khong co window nen doc thang vi.json, nho vay ban node van ra chu that chu
  // khong phai ma khoa tran. Cung mot ly do voi ic() o tren.
  function tw(khoa) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa);
    try { return require("./i18n/vi.json")[khoa] || khoa; } catch (e) { return khoa; }
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function addDays(d, n) { var x = new Date(d.getTime()); x.setDate(x.getDate() + n); return x; }

  // Cac lua chon ngay (thuan, test duoc): thu 7 / thu 2 GAN NHAT phia truoc mat
  function tsDateOptions(now) {
    now = now || new Date();
    var dow = now.getDay();                       // 0 CN .. 6 T7
    var toSat = (6 - dow + 7) % 7 || 7;
    var toMon = (1 - dow + 7) % 7 || 7;
    return [
      { label: tw("cs.uz_today"), date: iso(now) },
      { label: tw("tsug.ngay_mai"), date: iso(addDays(now, 1)) },
      { label: tw("tsug.cuoi_tuan"), date: iso(addDays(now, toSat)) },
      { label: tw("tsug.tuan_sau"), date: iso(addDays(now, toMon)) },
      { label: tw("tsug.chon_ngay"), pick: true },
    ];
  }
  // Dong vua go xong co phai khung task "- [ ]" / "- [x]" tron? (nbsp cua contenteditable -> space)
  function tsTaskStart(text) {
    return /^\s*[-*+]\s+\[(?: |x|X)?\]\s*$/.test(String(text == null ? "" : text).replace(/ /g, " "));
  }

  // Hai thu KHAC NHAU trong bang nay, dung lan la sai:
  //   menuIcon = ten icon Lucide, chi de HIEN trong menu goi y.
  //   token / text = ky tu THAT duoc chen vao file .md. Day la cu phap cua
  //     Obsidian Tasks nen BUOC phai giu nguyen emoji - doi la Obsidian khong
  //     doc duoc nua va test_dataview_tasks.py se do.
  // Ham chu khong phai hang: nhan phai lay tu dien lai moi lan mo menu, vi nguoi dung
  // co the doi ngon ngu giua chung ma khong tai lai trang.
  function mainItems() {
    return [
      { menuIcon: "calendar", label: tw("tsug.han_chot"), kind: "date", token: "📅" },
      { menuIcon: "hourglass", label: tw("tsug.ngay_du_kien"), kind: "date", token: "⏳" },
      { menuIcon: "plane-takeoff", label: tw("tsug.ngay_bat_dau"), kind: "date", token: "🛫" },
      { menuIcon: "chevrons-up", label: tw("tsug.uu_tien_cao"), kind: "insert", text: "⏫ " },
      { menuIcon: "chevron-up", label: tw("tsug.uu_tien_vua"), kind: "insert", text: "🔼 " },
      { menuIcon: "chevron-down", label: tw("tsug.uu_tien_thap"), kind: "insert", text: "🔽 " },
    ];
  }

  // ---------------------------------------------------------------- popup (chi khi co DOM)
  if (typeof document !== "undefined") {
    var pop = null, items = [], sel = 0, mode = "main", token = "", savedRange = null;

    function closePop() {
      if (pop) { pop.remove(); pop = null; }
      mode = "main"; token = ""; savedRange = null;
    }
    function renderPop() {
      pop.innerHTML = items.map(function (it, i) {
        return '<div class="ts-item' + (i === sel ? " sel" : "") + '" data-i="' + i + '">' +
          (it.menuIcon ? '<span class="ts-ic">' + ic(it.menuIcon) + "</span>" : "") + esc(it.label) +
          (it.date ? ' <span class="ts-date">' + esc(it.date) + "</span>" : "") + "</div>";
      }).join("");
    }
    function openPop(list) {
      items = list; sel = 0;
      if (!pop) {
        pop = document.createElement("div");
        pop.className = "ts-pop";
        document.body.appendChild(pop);
        pop.addEventListener("mousedown", function (e) {
          if (!e.target.closest(".ts-datein")) e.preventDefault();   // giu caret trong editor
        });
        pop.addEventListener("click", function (e) {
          var it = e.target.closest(".ts-item");
          if (it) choose(+it.dataset.i);
        });
      }
      renderPop();
      var s = window.getSelection();
      if (s && s.rangeCount) {
        var r = s.getRangeAt(0).getBoundingClientRect();
        var left = r.left || 0, top = r.bottom || 0;
        if (!left && !top && s.anchorNode) {   // caret o node rong: lay theo block
          var elx = s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement;
          if (elx && elx.getBoundingClientRect) { var b = elx.getBoundingClientRect(); left = b.left; top = b.bottom; }
        }
        pop.style.left = Math.max(8, Math.min(left, window.innerWidth - 270)) + "px";
        pop.style.top = Math.min(top + 4, window.innerHeight - 250) + "px";
      }
    }
    function insertText(t) {
      try { document.execCommand("insertText", false, t); } catch (e) {}
    }
    function restoreCaret() {
      if (!savedRange) return;
      try {
        var s = window.getSelection();
        s.removeAllRanges(); s.addRange(savedRange);
      } catch (e) {}
    }
    function choose(i) {
      var it = items[i];
      if (!it) return;
      if (mode === "main") {
        if (it.kind === "insert") { insertText(it.text); closePop(); return; }
        token = it.token; mode = "date";
        openPop(tsDateOptions());
        return;
      }
      if (it.pick) { showDatePicker(); return; }
      insertText(token + " " + it.date + " ");
      closePop();
    }
    function showDatePicker() {
      try { savedRange = window.getSelection().getRangeAt(0).cloneRange(); } catch (e) { savedRange = null; }
      pop.innerHTML = '<input type="date" class="ts-datein">';
      var inp = pop.querySelector("input");
      inp.addEventListener("change", function () {
        var v = inp.value;
        restoreCaret();
        if (v) insertText(token + " " + v + " ");
        closePop();
      });
      inp.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { e.stopPropagation(); restoreCaret(); closePop(); }
      });
      setTimeout(function () {
        try { inp.focus(); if (inp.showPicker) inp.showPicker(); } catch (e) {}
      }, 0);
    }
    function placeCaretEnd(el) {
      var r = document.createRange();
      r.selectNodeContents(el); r.collapse(false);
      var s = window.getSelection();
      s.removeAllRanges(); s.addRange(r);
    }
    function caretAtEnd(li, s) {
      try {
        var r2 = document.createRange();
        r2.selectNodeContents(li);
        r2.setStart(s.anchorNode, s.anchorOffset);
        return r2.toString().replace(/ /g, " ").trim() === "";
      } catch (e) { return false; }
    }
    var CB_HTML = '<input type="checkbox" class="md-cb" contenteditable="false"> ';
    function convertToTask(block, checked) {
      var ul = document.createElement("ul");
      var li = document.createElement("li");
      li.className = "task-item" + (checked ? " task-done" : "");
      li.innerHTML = checked ? CB_HTML.replace("> ", " checked> ") : CB_HTML;
      ul.appendChild(li);
      block.replaceWith(ul);
      placeCaretEnd(li);
    }
    function convertLiToTask(li, checked) {
      li.classList.add("task-item");
      li.innerHTML = checked ? CB_HTML.replace("> ", " checked> ") : CB_HTML;
      placeCaretEnd(li);
    }

    // AN CACH trong editor: (a) "- [ ]" tron -> task that; (b) cuoi dong task -> menu goi y
    document.addEventListener("keyup", function (e) {
      if (e.key !== " ") return;
      var wys = e.target && e.target.closest ? e.target.closest(".ne-wys") : null;
      if (!wys) return;
      var s = window.getSelection();
      if (!s || !s.rangeCount || !s.isCollapsed) return;
      var node = s.anchorNode;
      var elx = node && (node.nodeType === 1 ? node : node.parentElement);
      if (!elx || !wys.contains(elx)) return;
      var li = elx.closest ? elx.closest("li") : null;
      if (li && li.classList.contains("task-item")) {
        if (caretAtEnd(li, s)) { mode = "main"; openPop(mainItems()); }
        return;
      }
      var block = li || (elx.closest ? elx.closest("p,div,h1,h2,h3,h4,h5,h6") : null);
      if (!block || block === wys || block.classList.contains("ne-wys")) return;
      var txt = (block.textContent || "").replace(/ /g, " ");
      if (li) {
        // trong li thuong (danh sach bullet): go "[ ]" + cach -> chuyen li thanh task
        if (/^\s*\[(?: |x|X)?\]\s*$/.test(txt)) convertLiToTask(li, /[xX]/.test(txt));
        return;
      }
      if (tsTaskStart(txt)) convertToTask(block, /\[[xX]\]/.test(txt));
    });

    // Dieu huong menu bang phim (capture + stopImmediate de khong dung Esc/Enter cua editor)
    document.addEventListener("keydown", function (e) {
      if (!pop) return;
      if (pop.querySelector(".ts-datein")) return;   // dang o o chon ngay: input tu xu ly
      if (e.key === "ArrowDown") { sel = (sel + 1) % items.length; renderPop(); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.key === "ArrowUp") { sel = (sel - 1 + items.length) % items.length; renderPop(); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.key === "Enter") { e.preventDefault(); e.stopImmediatePropagation(); choose(sel); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); closePop(); }
      else if (e.key.length === 1) closePop();       // go tiep (ke ca cach) -> menu tu tat
    }, true);
    document.addEventListener("mousedown", function (e) {
      if (pop && !pop.contains(e.target)) closePop();
    });
    window.addEventListener("scroll", function () { closePop(); }, true);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { tsDateOptions: tsDateOptions, tsTaskStart: tsTaskStart };
  }
})();
