/* editor-cmds.js - BANG LENH DUNG CHUNG cua trinh soan .md (editor cay + khung sua tu chat).

   Mot bang CMDS duy nhat nuoi ca ba dau ra, nen them mot lenh la ca ba cho co ngay:
     1) Nut tren thanh cong cu  (console.js _neBuildToolbar doc bang nay)
     2) Phim tat               (nghe o tang document, chay ca 2 che do Sua/Nguon)
     3) Menu go dau "/"        (chi trong ban render dang sua .ne-wys)

   Truoc day bang nut nam CUNG trong _neBuildToolbar, tach ra day de menu "/" va phim tat
   khong phai chep lai lan hai roi troi nhau.

   Moi lenh co hai nhanh chay vi editor co hai che do khac han:
     wys  -> ban render contenteditable, dung document.execCommand
     src  -> textarea markdown tho, chen ky tu that
   Nhanh nao chay do ctx.mode() quyet dinh.

   File chay duoc CA duoi node (test require) lan trong trinh duyet: phan DOM boc trong
   `if (typeof document !== "undefined")`, phan logic thuan de tran de test.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  var ic = (typeof window !== "undefined" && window.ic) ? window.ic : function () { return ""; };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Mac hien "Cmd", con lai hien "Ctrl". CO Y dung CHU chu khong dung ky hieu Apple: repo cam
  // ky tu hinh trong giao dien (test_icons.py gac), va chu thi bo doc man hinh doc ra tu te.
  // Duoi node khong co navigator -> coi nhu khong phai Mac, nho vay nhan phim tat trong test la
  // chuoi co dinh, khong doi theo may chay test.
  var MAC = (typeof navigator !== "undefined") &&
    /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

  // ---------------------------------------------------------------- thao tac tren 2 che do
  function exec(ctx, cmd, val) {
    try { ctx.wys.focus(); document.execCommand(cmd, false, val == null ? null : val); } catch (e) {}
  }
  // Boc doan dang chon: **dam**, `code`...
  function wrapTa(ctx, b, a, ph) {
    var ta = ctx.ta, s = ta.selectionStart, e = ta.selectionEnd;
    var sel = ta.value.slice(s, e) || ph || "";
    ta.value = ta.value.slice(0, s) + b + sel + a + ta.value.slice(e);
    ta.selectionStart = s + b.length; ta.selectionEnd = s + b.length + sel.length; ta.focus();
  }
  // Them tien to vao DAU moi dong dang chon: "# ", "- ", "- [ ] "... ({n} = so thu tu)
  function lineTa(ctx, prefix) {
    var ta = ctx.ta, s = ta.selectionStart, e = ta.selectionEnd, v = ta.value;
    var ls = v.lastIndexOf("\n", s - 1) + 1;
    var block = v.slice(ls, e).split("\n").map(function (ln, i) {
      return prefix.replace("{n}", i + 1) + ln;
    }).join("\n");
    ta.value = v.slice(0, ls) + block + v.slice(e); ta.focus();
  }
  function insTa(ctx, t) {
    var ta = ctx.ta, s = ta.selectionStart;
    ta.value = ta.value.slice(0, s) + t + ta.value.slice(s);
    ta.selectionStart = ta.selectionEnd = s + t.length; ta.focus();
  }

  // Checkbox trong ban render. Dung DUNG khuon ma task-suggest.js sinh ra ("- [ ]" + phim cach)
  // de hai loi vao ra cung mot thu, luc luu nguoc ve markdown moi khop.
  var CB_HTML = '<input type="checkbox" class="md-cb" contenteditable="false"> ';
  function caretEnd(el) {
    try {
      var r = document.createRange(); r.selectNodeContents(el); r.collapse(false);
      var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    } catch (e) {}
  }
  function wysTask(ctx) {
    var wys = ctx.wys;
    try { wys.focus(); } catch (e) {}
    function liHienTai() {
      var s = window.getSelection();
      var n = s && s.anchorNode;
      var el = n && (n.nodeType === 1 ? n : n.parentElement);
      return (el && el.closest && wys.contains(el)) ? el.closest("li") : null;
    }
    var li = liHienTai();
    // Chua o trong danh sach thi tao danh sach truoc roi moi gan checkbox - lam nguoc lai
    // thi execCommand nuot mat cai checkbox vua chen.
    if (!li) {
      try { document.execCommand("insertUnorderedList"); } catch (e) {}
      li = liHienTai();
    }
    if (!li) { try { document.execCommand("insertHTML", false, CB_HTML); } catch (e) {} return; }
    if (li.classList.contains("task-item")) return;      // da la task roi, bam nua khong nhan doi
    li.classList.add("task-item");
    li.insertAdjacentHTML("afterbegin", CB_HTML);
    caretEnd(li);
  }

  // ---------------------------------------------------------------- BANG LENH
  // key: mo ta to hop phim. Phim mod (Ctrl, hoac Cmd tren Mac) luon bat buoc nen khong ghi lai.
  //   code   - dung e.code cho phim SO/DAU: giu Alt hoac doi bo go la e.key doi (Mac: Alt+1
  //            ra "¡"), con e.code van la "Digit1".
  //   letter - dung e.key cho phim CHU vi nguoi dung nho mat chu, khong nho vi tri.
  //   show   - chu hien trong nhan phim tat.
  var CMDS = [
    { id: "bold", label: "Đậm", btn: { text: "B", style: "font-weight:700" },
      key: { letter: "b", show: "B" },
      wys: function (c) { exec(c, "bold"); },
      src: function (c) { wrapTa(c, "**", "**", "chữ đậm"); } },

    { id: "italic", label: "Nghiêng", btn: { text: "I", style: "font-style:italic" },
      key: { letter: "i", show: "I" },
      wys: function (c) { exec(c, "italic"); },
      src: function (c) { wrapTa(c, "*", "*", "chữ nghiêng"); } },

    { id: "h1", label: "Tiêu đề 1", kw: "heading tieu de lon", btn: { text: "H1" },
      key: { alt: true, code: "Digit1", show: "1" },
      wys: function (c) { exec(c, "formatBlock", "H1"); },
      src: function (c) { lineTa(c, "# "); } },

    { id: "h2", label: "Tiêu đề 2", kw: "heading tieu de", btn: { text: "H2" },
      key: { alt: true, code: "Digit2", show: "2" },
      wys: function (c) { exec(c, "formatBlock", "H2"); },
      src: function (c) { lineTa(c, "## "); } },

    { id: "h3", label: "Tiêu đề 3", kw: "heading tieu de nho", btn: { text: "H3" },
      key: { alt: true, code: "Digit3", show: "3" },
      wys: function (c) { exec(c, "formatBlock", "H3"); },
      src: function (c) { lineTa(c, "### "); } },

    { id: "ul", label: "Gạch đầu dòng", kw: "bullet danh sach list", btn: { text: "•" },
      key: { shift: true, code: "Digit8", show: "8" },
      wys: function (c) { exec(c, "insertUnorderedList"); },
      src: function (c) { lineTa(c, "- "); } },

    { id: "ol", label: "Danh sách số", kw: "so thu tu numbered list", btn: { text: "1." },
      key: { shift: true, code: "Digit7", show: "7" },
      wys: function (c) { exec(c, "insertOrderedList"); },
      src: function (c) { lineTa(c, "{n}. "); } },

    // Nut MOI (yeu cau 2026-07-31): dung ngay sau hai kieu danh sach vi no cung ho danh sach.
    { id: "task", label: "Checkbox", kw: "task viec can lam todo o vuong tick",
      btn: { icon: "list-todo" },
      key: { shift: true, code: "Digit9", show: "9" },
      wys: wysTask,
      src: function (c) { lineTa(c, "- [ ] "); } },

    { id: "quote", label: "Trích dẫn", kw: "blockquote trich", btn: { icon: "quote" },
      // Ctrl+Shift+. de nho: Shift+. chinh la ky tu ">" cua markdown trich dan.
      key: { shift: true, code: "Period", show: "." },
      wys: function (c) { exec(c, "formatBlock", "BLOCKQUOTE"); },
      src: function (c) { lineTa(c, "> "); } },

    { id: "code", label: "Code", kw: "ma nguon inline", btn: { text: "</>" },
      key: { letter: "e", show: "E" },
      wys: function (c) { exec(c, "insertHTML", "<code>code</code>"); },
      src: function (c) { wrapTa(c, "`", "`", "code"); } },

    { id: "link", label: "Link", kw: "lien ket url", btn: { icon: "link" },
      key: { letter: "k", show: "K" },
      run: function (c) {
        var u = prompt("URL:", "https://");
        if (!u) return;
        if (c.mode() === "wys") exec(c, "createLink", u); else wrapTa(c, "[", "](" + u + ")", "chữ");
      } },

    { id: "hr", label: "Kẻ ngang", kw: "duong ke ngan cach", btn: { text: "―" },
      wys: function (c) { exec(c, "insertHorizontalRule"); },
      src: function (c) { insTa(c, "\n---\n"); } },
  ];

  // ---------------------------------------------------------------- ham thuan (test duoc)
  function keyLabel(c) {
    if (!c || !c.key) return "";
    var p = [MAC ? "Cmd" : "Ctrl"];
    if (c.key.shift) p.push("Shift");
    if (c.key.alt) p.push(MAC ? "Opt" : "Alt");
    p.push(c.key.show);
    return p.join("+");
  }

  // Doi phim vua bam -> lenh. Tra null neu khong khop lenh nao.
  function matchCmd(e) {
    if (!e || !(e.ctrlKey || e.metaKey)) return null;
    for (var i = 0; i < CMDS.length; i++) {
      var c = CMDS[i];
      if (!c.key) continue;
      if (!!c.key.shift !== !!e.shiftKey) continue;
      if (!!c.key.alt !== !!e.altKey) continue;
      if (c.key.code) { if (e.code !== c.key.code) continue; }
      else if (c.key.letter) { if (String(e.key || "").toLowerCase() !== c.key.letter) continue; }
      else continue;
      return c;
    }
    return null;
  }

  function bo_dau(s) {
    return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
  }
  // Loc menu "/" theo chu vua go. Go khong dau van ra ("tieu de" khop "Tiêu đề 1").
  function filterCmds(q) {
    var t = bo_dau(q).trim();
    if (!t) return CMDS.slice();
    return CMDS.filter(function (c) {
      return (bo_dau(c.label) + " " + c.id + " " + (c.kw || "")).indexOf(t) !== -1;
    });
  }
  // Dau "/" chi mo menu khi no MO DAU mot tu (dau dong hoac sau khoang trang). Nho vay
  // "12/2026", "và/hoặc", duong dan "a/b" go binh thuong khong bung menu.
  function slashTrigger(truoc) {
    return /(^|\s)$/.test(String(truoc == null ? "" : truoc).replace(/ /g, " "));
  }

  function run(id, ctx) {
    var c = null;
    for (var i = 0; i < CMDS.length; i++) if (CMDS[i].id === id) { c = CMDS[i]; break; }
    if (!c || !ctx) return false;
    if (c.run) { c.run(ctx); return true; }
    if (ctx.mode() === "wys") { if (c.wys) c.wys(ctx); }
    else if (c.src) c.src(ctx);
    return true;
  }

  var api = {
    CMDS: CMDS, run: run, keyLabel: keyLabel, matchCmd: matchCmd,
    filterCmds: filterCmds, slashTrigger: slashTrigger, esc: esc,
    // Nhan nut cho thanh cong cu: SVG neu co icon, chu da escape neu la chu thuan.
    btnHtml: function (c) { return c.btn.icon ? ic(c.btn.icon) : esc(c.btn.text); },
    btnTitle: function (c) { var k = keyLabel(c); return c.label + (k ? " (" + k + ")" : ""); },
  };

  // ---------------------------------------------------------------- phan DOM
  if (typeof document !== "undefined") {
    // Tim khung soan tu event. Lam o tang document nhu task-suggest.js: khong phai goi lap
    // dat o tung noi mo editor, editor moi nao dung dung lop .ne-wys / .ne-src la co ngay.
    function ctxTu(target) {
      if (!target || !target.closest) return null;
      var wys = target.closest(".ne-wys");
      if (wys) {
        var src = wys.parentElement ? wys.parentElement.querySelector(".ne-src textarea") : null;
        return { mode: function () { return "wys"; }, wys: wys, ta: src };
      }
      var ta = target.closest(".ne-src") ? target : null;
      if (ta && ta.tagName === "TEXTAREA") {
        var pane = ta.closest(".ne-panes");
        return { mode: function () { return "source"; }, ta: ta,
                 wys: pane ? pane.querySelector(".ne-wys") : null };
      }
      return null;
    }

    // ----- phim tat -----
    document.addEventListener("keydown", function (e) {
      var c = matchCmd(e);
      if (!c) return;
      var ctx = ctxTu(e.target);
      if (!ctx) return;
      e.preventDefault();
      e.stopPropagation();
      run(c.id, ctx);
    }, true);

    // ----- menu go "/" (chi trong ban render dang sua) -----
    var pop = null, mItems = [], mSel = 0, mNode = null, mOff = -1, mCtx = null;

    function dongMenu() {
      if (pop) { pop.remove(); pop = null; }
      mItems = []; mSel = 0; mNode = null; mOff = -1; mCtx = null;
    }
    function veMenu() {
      pop.innerHTML = mItems.map(function (c, i) {
        return '<div class="ec-item' + (i === mSel ? " sel" : "") + '" data-i="' + i + '">' +
          '<span class="ec-ic">' + api.btnHtml(c) + "</span>" +
          '<span class="ec-lb">' + esc(c.label) + "</span>" +
          '<span class="ec-key">' + esc(keyLabel(c)) + "</span></div>";
      }).join("");
    }
    function moMenu() {
      if (!pop) {
        pop = document.createElement("div");
        pop.className = "ec-pop";
        document.body.appendChild(pop);
        pop.addEventListener("mousedown", function (e) { e.preventDefault(); });  // giu caret
        pop.addEventListener("click", function (e) {
          var it = e.target.closest(".ec-item");
          if (it) chon(+it.dataset.i);
        });
      }
      veMenu();
      try {
        var s = window.getSelection();
        var r = s.getRangeAt(0).getBoundingClientRect();
        var left = r.left || 0, top = r.bottom || 0;
        if (!left && !top && s.anchorNode) {
          var el = s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement;
          if (el && el.getBoundingClientRect) { var b = el.getBoundingClientRect(); left = b.left; top = b.bottom; }
        }
        pop.style.left = Math.max(8, Math.min(left, window.innerWidth - 280)) + "px";
        pop.style.top = Math.min(top + 4, window.innerHeight - 300) + "px";
      } catch (e) {}
    }
    // Xoa doan "/tu-dang-go" roi moi chay lenh, khong thi chu "/" con nam lai trong note.
    function xoaChuSlash() {
      try {
        var s = window.getSelection();
        var het = (s && s.rangeCount && s.anchorNode === mNode) ? s.anchorOffset : mNode.length;
        var r = document.createRange();
        r.setStart(mNode, mOff); r.setEnd(mNode, Math.max(mOff, het));
        r.deleteContents();
        var c = document.createRange(); c.setStart(mNode, mOff); c.collapse(true);
        s.removeAllRanges(); s.addRange(c);
      } catch (e) {}
    }
    function chon(i) {
      var c = mItems[i], ctx = mCtx;
      if (!c || !ctx) { dongMenu(); return; }
      xoaChuSlash();
      dongMenu();
      run(c.id, ctx);
    }

    document.addEventListener("keyup", function (e) {
      var ctx = ctxTu(e.target);
      if (!ctx || ctx.mode() !== "wys") { if (pop) dongMenu(); return; }
      var s = window.getSelection();
      if (!s || !s.rangeCount || !s.isCollapsed) { if (pop) dongMenu(); return; }
      var node = s.anchorNode;

      if (!pop) {
        if (e.key !== "/") return;
        if (!node || node.nodeType !== 3) return;                 // "/" phai nam trong text node
        var off = s.anchorOffset - 1;
        if (off < 0 || node.textContent.charAt(off) !== "/") return;
        if (!slashTrigger(node.textContent.slice(0, off))) return;
        mNode = node; mOff = off; mCtx = ctx; mItems = CMDS.slice(); mSel = 0;
        moMenu();
        return;
      }
      // Menu dang mo: go tiep thi loc dan. Roi khoi text node cu / xoa mat dau "/" -> dong.
      if (node !== mNode || mNode.textContent.charAt(mOff) !== "/" || s.anchorOffset <= mOff) {
        dongMenu(); return;
      }
      var q = mNode.textContent.slice(mOff + 1, s.anchorOffset);
      if (/\s/.test(q)) { dongMenu(); return; }                   // go khoang trang -> thoi tim
      mItems = filterCmds(q); mSel = 0;
      if (!mItems.length) { dongMenu(); return; }
      veMenu();
    });

    // Dieu huong menu. Capture + stopImmediate de Enter/Esc khong roi xuong editor.
    document.addEventListener("keydown", function (e) {
      if (!pop) return;
      if (e.key === "ArrowDown") { mSel = (mSel + 1) % mItems.length; veMenu(); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.key === "ArrowUp") { mSel = (mSel - 1 + mItems.length) % mItems.length; veMenu(); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); e.stopImmediatePropagation(); chon(mSel); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); dongMenu(); }
    }, true);

    document.addEventListener("mousedown", function (e) {
      if (pop && !e.target.closest(".ec-pop")) dongMenu();
    });

    window.JavisEditorCmds = api;
  }

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
