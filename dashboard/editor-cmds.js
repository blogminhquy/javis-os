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

  // Nhan lenh giu KHOA tu dien, dich luc VE chu khong luc dinh nghia bang: file nay nap
  // truoc khi tu dien ve xong, va con chay duoi node (test require) noi khong co window.
  function dich(k) {
    try {
      if (typeof window !== "undefined" && window.t) return window.t(k);
      return require("./i18n/vi.json")[k] || k;
    } catch (e) {}
    return k;
  }
  function nhan(c) { return dich(c && c.label); }

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
  // li dang chua caret trong ban render. DUNG CHUNG cho nut checkbox, Enter va Tab: chep moi
  // noi mot ban thi som muon cac ban troi khoi nhau.
  function liTuCaret(wys) {
    var s = window.getSelection();
    var n = s && s.anchorNode;
    var el = n && (n.nodeType === 1 ? n : n.parentElement);
    return (el && el.closest && wys && wys.contains(el)) ? el.closest("li") : null;
  }
  function wysTask(ctx) {
    var wys = ctx.wys;
    try { wys.focus(); } catch (e) {}
    var li = liTuCaret(wys);
    // Chua o trong danh sach thi tao danh sach truoc roi moi gan checkbox - lam nguoc lai
    // thi execCommand nuot mat cai checkbox vua chen.
    if (!li) {
      try { document.execCommand("insertUnorderedList"); } catch (e) {}
      li = liTuCaret(wys);
    }
    if (!li) { try { document.execCommand("insertHTML", false, CB_HTML); } catch (e) {} return; }
    if (li.classList.contains("task-item")) return;      // da la task roi, bam nua khong nhan doi
    li.classList.add("task-item");
    li.insertAdjacentHTML("afterbegin", CB_HTML);
    caretEnd(li);
  }

  // ---------------------------------------------------------------- danh sach: Enter va Tab
  // Ham thuan, chay duoc duoi node. Phan nghe phim nam o cuoi file, trong phan DOM.
  var THUT = "    ";   // 4 dau cach: dung khuon Turndown dung khi ghi muc con ra markdown

  // Doc dau muc cua MOT dong markdown. Tra null neu khong phai dong danh sach.
  //   loai  task | ul | ol
  //   dau   phan dau muc that cua dong (ke ca thut le); caret phai qua no moi tinh la noi dung
  //   tiep  dau muc cho dong ke tiep: task luon CHUA tick, so thi tang mot
  // Task phai xet TRUOC bullet: "- [ ] x" cung khop khuon "- x".
  function dongDanhSach(line) {
    var l = String(line == null ? "" : line).replace(/ /g, " ");
    var m = /^(\s*)([-*+]) \[([ xX])\](?: (.*))?$/.exec(l);
    if (m) {
      return { loai: "task", indent: m[1], noiDung: m[4] || "",
               dau: m[1] + m[2] + " [" + m[3] + "] ", tiep: m[1] + m[2] + " [ ] " };
    }
    // Bat buoc co dau cach sau dau muc: nho vay "---" (duong ke) va "-5" khong bi bat.
    m = /^(\s*)([-*+]) (.*)$/.exec(l);
    if (m) return { loai: "ul", indent: m[1], noiDung: m[3], dau: m[1] + m[2] + " ", tiep: m[1] + m[2] + " " };
    m = /^(\s*)(\d{1,9})([.)]) (.*)$/.exec(l);
    if (m) {
      return { loai: "ol", indent: m[1], noiDung: m[4], dau: m[1] + m[2] + m[3] + " ",
               tiep: m[1] + (parseInt(m[2], 10) + 1) + m[3] + " " };
    }
    return null;
  }

  // Enter trong o nguon tho. Tra mo ta thay doi {s, e, text}: thay doan [s, e) bang text, caret
  // dung sau text. Tra null = de trinh duyet xuong dong binh thuong.
  function enterDanhSach(value, pos) {
    var v = String(value == null ? "" : value);
    if (typeof pos !== "number" || pos !== Math.floor(pos) || pos < 0 || pos > v.length) return null;
    var ls = v.lastIndexOf("\n", pos - 1) + 1;
    var le = v.indexOf("\n", pos); if (le < 0) le = v.length;
    var d = dongDanhSach(v.slice(ls, le));
    if (!d) return null;
    if (pos - ls < d.dau.length) return null;        // caret con nam trong dau muc
    // Dong chi co dau muc: Enter GO dau muc, day la loi ra khoi danh sach.
    if (!d.noiDung.trim()) return { s: ls, e: le, text: "" };
    return { s: pos, e: pos, text: "\n" + d.tiep };
  }

  // Tab / Shift+Tab trong o nguon tho. Tra {s, e, text, selS, selE}: thay doan [s, e) bang text
  // roi chon lai [selS, selE). Tra null = khong co gi de lam.
  //   - Caret tren dong danh sach, hoac dang chon nhieu dong: thut CA DONG vao/ra 4 cach.
  //   - Caret tren dong chu thuong: chen 4 cach ngay tai caret, nhu moi trinh soan.
  function thutLe(value, s, e, lui) {
    var v = String(value == null ? "" : value);
    if (typeof s !== "number" || typeof e !== "number" || s < 0 || e > v.length || s > e) return null;
    var ls = v.lastIndexOf("\n", s - 1) + 1;
    var e2 = (e > s && v.charAt(e - 1) === "\n") ? e - 1 : e;   // chon toi dau dong sau thi bo dong do
    var le = v.indexOf("\n", e2); if (le < 0) le = v.length;
    var khoi = v.slice(ls, le);
    if (!lui && s === e && !dongDanhSach(khoi)) {
      return { s: s, e: s, text: THUT, selS: s + THUT.length, selE: s + THUT.length };
    }
    var dauDong = 0, tong = 0;
    var moi = khoi.split("\n").map(function (ln, i) {
      var d = THUT.length;
      if (!lui) ln = THUT + ln;
      else {
        var m = /^( {1,4}|\t)/.exec(ln);
        d = m ? -m[1].length : 0;
        if (m) ln = ln.slice(m[1].length);
      }
      if (i === 0) dauDong = d;
      tong += d;
      return ln;
    }).join("\n");
    if (!tong) return null;
    return { s: ls, e: le, text: moi,
             // Chon tu dau dong thi giu ca phan thut vua them trong vung chon.
             selS: (s === ls && s !== e) ? ls : Math.max(ls, s + dauDong), selE: Math.max(ls, e + tong) };
  }

  // Go dau muc o dau mot doan trong ban render -> doi doan do thanh danh sach.
  // "-", "*", "+" -> bullet; "1." / "3)" -> danh sach so bat dau tu so do. Null = khong phai.
  function dauMucGo(text) {
    var t = String(text == null ? "" : text).replace(/ /g, " ");
    if (/^[-*+] $/.test(t)) return { loai: "ul" };
    var m = /^(\d{1,9})[.)] $/.exec(t);
    if (m) return { loai: "ol", batDau: parseInt(m[1], 10) };
    return null;
  }

  // ---------------------------------------------------------------- BANG LENH
  // key: mo ta to hop phim. Phim mod (Ctrl, hoac Cmd tren Mac) luon bat buoc nen khong ghi lai.
  //   code   - dung e.code cho phim SO/DAU: giu Alt hoac doi bo go la e.key doi (Mac: Alt+1
  //            ra "¡"), con e.code van la "Digit1".
  //   letter - dung e.key cho phim CHU vi nguoi dung nho mat chu, khong nho vi tri.
  //   show   - chu hien trong nhan phim tat.
  var CMDS = [
    // slash:false = KHONG vao menu "/". Dam va nghieng boi chu DANG CHON, khong phai thu
    // "chen tai cho" nhu ca menu con lai; ma go "/" xong thi dau co gi dang chon. Chung van
    // giu nut tren thanh cong cu va Ctrl+B / Ctrl+I - hai phim ai cung thuoc san.
    { id: "bold", label: "ecmd.bold", slash: false, btn: { text: "B", style: "font-weight:700" },
      key: { letter: "b", show: "B" },
      wys: function (c) { exec(c, "bold"); },
      src: function (c) { wrapTa(c, "**", "**", dich("ecmd.ph_bold")); } },

    { id: "italic", label: "ecmd.italic", slash: false, btn: { text: "I", style: "font-style:italic" },
      key: { letter: "i", show: "I" },
      wys: function (c) { exec(c, "italic"); },
      src: function (c) { wrapTa(c, "*", "*", dich("ecmd.ph_italic")); } },

    { id: "h1", label: "ecmd.h1", kw: "heading tieu de lon", btn: { text: "H1" },
      key: { alt: true, code: "Digit1", show: "1" },
      wys: function (c) { exec(c, "formatBlock", "H1"); },
      src: function (c) { lineTa(c, "# "); } },

    { id: "h2", label: "ecmd.h2", kw: "heading tieu de", btn: { text: "H2" },
      key: { alt: true, code: "Digit2", show: "2" },
      wys: function (c) { exec(c, "formatBlock", "H2"); },
      src: function (c) { lineTa(c, "## "); } },

    { id: "h3", label: "ecmd.h3", kw: "heading tieu de nho", btn: { text: "H3" },
      key: { alt: true, code: "Digit3", show: "3" },
      wys: function (c) { exec(c, "formatBlock", "H3"); },
      src: function (c) { lineTa(c, "### "); } },

    { id: "ul", label: "ecmd.ul", kw: "bullet danh sach list", btn: { text: "•" },
      key: { shift: true, code: "Digit8", show: "8" },
      wys: function (c) { exec(c, "insertUnorderedList"); },
      src: function (c) { lineTa(c, "- "); } },

    { id: "ol", label: "ecmd.ol", kw: "so thu tu numbered list", btn: { text: "1." },
      key: { shift: true, code: "Digit7", show: "7" },
      wys: function (c) { exec(c, "insertOrderedList"); },
      src: function (c) { lineTa(c, "{n}. "); } },

    // Nut MOI (yeu cau 2026-07-31): dung ngay sau hai kieu danh sach vi no cung ho danh sach.
    { id: "task", label: "ecmd.task", kw: "task viec can lam todo o vuong tick",
      btn: { icon: "list-todo" },
      key: { shift: true, code: "Digit9", show: "9" },
      wys: wysTask,
      src: function (c) { lineTa(c, "- [ ] "); } },

    { id: "quote", label: "ecmd.quote", kw: "blockquote trich", btn: { icon: "quote" },
      // Ctrl+Shift+. de nho: Shift+. chinh la ky tu ">" cua markdown trich dan.
      key: { shift: true, code: "Period", show: "." },
      wys: function (c) { exec(c, "formatBlock", "BLOCKQUOTE"); },
      src: function (c) { lineTa(c, "> "); } },

    { id: "code", label: "ecmd.code", kw: "ma nguon inline", btn: { text: "</>" },
      key: { letter: "e", show: "E" },
      wys: function (c) { exec(c, "insertHTML", "<code>code</code>"); },
      src: function (c) { wrapTa(c, "`", "`", "code"); } },

    { id: "link", label: "ecmd.link", kw: "lien ket url", btn: { icon: "link" },
      key: { letter: "k", show: "K" },
      run: function (c) {
        var u = prompt("URL:", "https://");
        if (!u) return;
        if (c.mode() === "wys") exec(c, "createLink", u); else wrapTa(c, "[", "](" + u + ")", dich("ecmd.ph_text"));
      } },

    { id: "hr", label: "ecmd.hr", kw: "duong ke ngan cach", btn: { text: "―" },
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
      .replace(/\u0111/g, "d").replace(/\u0110/g, "D").toLowerCase();
  }
  // Cac lenh duoc bay trong menu "/". Loc san theo slash !== false, nen bo/them mot lenh khoi
  // menu chi la sua ĐUNG mot chO trong bang CMDS.
  function menuCmds() {
    return CMDS.filter(function (c) { return c.slash !== false; });
  }
  // Loc menu "/" theo chu vua go. Go khong dau van ra ("tieu de" khop "Tiêu đề 1").
  function filterCmds(q) {
    var ds = menuCmds();
    var t = bo_dau(q).trim();
    if (!t) return ds;
    return ds.filter(function (c) {
      // KHONG tim tren c.label nua: tu 0.55.14 truong do giu MA KHOA i18n ("ecmd.bold"), nen
      // moi lenh deu chua chuoi "ecmd." va go mot chu bat ky trong {e,c,m,d,.} la khop het,
      // tuc bo loc mat tac dung. nhan(c) moi la chu that da dich.
      return (bo_dau(nhan(c)) + " " + c.id + " " + (c.kw || "")).indexOf(t) !== -1;
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
    menuCmds: menuCmds, filterCmds: filterCmds, slashTrigger: slashTrigger, esc: esc,
    dongDanhSach: dongDanhSach, enterDanhSach: enterDanhSach, thutLe: thutLe, dauMucGo: dauMucGo,
    // Nhan nut cho thanh cong cu: SVG neu co icon, chu da escape neu la chu thuan.
    btnHtml: function (c) { return c.btn.icon ? ic(c.btn.icon) : esc(c.btn.text); },
    btnTitle: function (c) { var k = keyLabel(c); return nhan(c) + (k ? " (" + k + ")" : ""); },
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
    var pop = null, mItems = [], mSel = 0, mNode = null, mOff = -1, mCtx = null, mQuery = "";

    function dongMenu() {
      if (pop) { pop.remove(); pop = null; }
      mItems = []; mSel = 0; mNode = null; mOff = -1; mCtx = null; mQuery = "";
    }
    function veMenu() {
      pop.innerHTML = mItems.map(function (c, i) {
        return '<div class="ec-item' + (i === mSel ? " sel" : "") + '" data-i="' + i + '">' +
          '<span class="ec-ic">' + api.btnHtml(c) + "</span>" +
          '<span class="ec-lb">' + esc(nhan(c)) + "</span>" +
          '<span class="ec-key">' + esc(keyLabel(c)) + "</span></div>";
      }).join("");
      // Menu co the dai hon khung -> keo muc dang chon vao tam nhin, khong thi bam mui ten
      // xuong toi muc khuat la nguoi dung khong con thay minh dang o dau.
      try {
        var el = pop.querySelector(".ec-item.sel");
        if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
      } catch (e) {}
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
    //
    // Cho chet nguoi: go "/" o mot dong TRONG thi text node chi chua moi dau "/". Xoa xong no
    // RONG, va Chromium don luon node rong -> range vua dat vao no chet theo, caret roi ve the
    // boc (.ne-wys). Luc do execCommand("formatBlock") van tra ve true nhung KHONG lam gi ca,
    // vi no khong biet dang dung o khoi nao. Trieu chung: chon "Tiêu đề 3" xong khong ra gi.
    // Nen phai bam lai vao node CON SONG: uu tien chinh text node, khong thi khoi cha cua no.
    function xoaChuSlash() {
      try {
        var s = window.getSelection();
        var het = (s && s.rangeCount && s.anchorNode === mNode) ? s.anchorOffset : mNode.length;
        var khoi = mNode.parentNode;                 // nhớ khối cha TRƯỚC khi xoá
        var r = document.createRange();
        r.setStart(mNode, mOff); r.setEnd(mNode, Math.max(mOff, het));
        r.deleteContents();
        var c = document.createRange();
        if (mNode.isConnected && mNode.parentNode) c.setStart(mNode, Math.min(mOff, mNode.length));
        else if (khoi && khoi.isConnected) c.selectNodeContents(khoi);
        else return;
        c.collapse(true);
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

    // Phim DIEU HUONG da do keydown lo tron ven. Phai chan o day, khong thi moi lan bam mui
    // ten la keyup chay tiep xuong duoi roi dat lai mSel = 0 -> vet chon bat nguoc len dau,
    // khong di xuong duoc (dung loi chu repo bao 2026-07-31).
    var PHIM_DIEU_HUONG = { ArrowDown: 1, ArrowUp: 1, Enter: 1, Tab: 1, Escape: 1 };

    document.addEventListener("keyup", function (e) {
      if (pop && PHIM_DIEU_HUONG[e.key]) return;
      var ctx = ctxTu(e.target);
      if (!ctx || ctx.mode() !== "wys") { if (pop) dongMenu(); return; }
      var s = window.getSelection();
      if (!s || !s.rangeCount || !s.isCollapsed) { if (pop) dongMenu(); return; }
      var node = s.anchorNode;

      // Menu dang mo ma caret da roi khoi cho cu (nhay sang dong khac, xoa mat dau "/") thi
      // dong lai. Dong xong VAN xet tiep phim vua go, vi chinh no co the la dau "/" mo menu
      // MOI o cho moi - tra ve luon thi lan go do bi nuot, phai go "/" hai lan moi ra menu.
      if (pop && !(node === mNode && mNode.textContent.charAt(mOff) === "/" && s.anchorOffset > mOff)) {
        dongMenu();
      }
      if (!pop) {
        if (e.key !== "/") return;
        if (!node || node.nodeType !== 3) return;                 // "/" phai nam trong text node
        var off = s.anchorOffset - 1;
        if (off < 0 || node.textContent.charAt(off) !== "/") return;
        if (!slashTrigger(node.textContent.slice(0, off))) return;
        mNode = node; mOff = off; mCtx = ctx; mQuery = ""; mItems = filterCmds(""); mSel = 0;
        moMenu();
        return;
      }
      var q = mNode.textContent.slice(mOff + 1, s.anchorOffset);
      if (/\s/.test(q)) { dongMenu(); return; }                   // go khoang trang -> thoi tim
      // Chu go THAT SU doi moi loc lai va nhay ve muc dau. Phim nao khong doi chu (Shift,
      // Ctrl, mui ten trai/phai...) thi de nguyen vet chon nguoi dung dang nham.
      if (q === mQuery) return;
      mQuery = q;
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

    // ----- Enter noi dong danh sach / task, Tab thut le, go "- " ra danh sach -----
    // Ban render (.ne-wys): Chromium TU noi bullet va danh sach so khi Enter, nen chi phai lo
    // task (li moi khong co checkbox) va loi ra khoi task rong. O nguon tho thi tu lam het.

    // Sua textarea qua execCommand de Ctrl+Z hoan tac duoc; trinh duyet nao tu choi thi ghi
    // thang vao value roi tu bao "input" de co danh dau da sua va tu luu van biet.
    function suaTa(ta, ed) {
      try { ta.focus(); } catch (x) {}
      ta.selectionStart = ed.s; ta.selectionEnd = ed.e;
      var ok = false;
      try { ok = document.execCommand("insertText", false, ed.text); } catch (x) {}
      if (!ok) {
        ta.value = ta.value.slice(0, ed.s) + ed.text + ta.value.slice(ed.e);
        ta.dispatchEvent(new Event("input", { bubbles: true }));
      }
      var a = ed.selS != null ? ed.selS : ed.s + ed.text.length;
      var b = ed.selE != null ? ed.selE : a;
      ta.selectionStart = a; ta.selectionEnd = b;
    }
    function baoDaSua(wys) {
      try { wys.dispatchEvent(new Event("input", { bubbles: true })); } catch (x) {}
    }
    // Chuyen node trong DOM la range cua selection bi keo ve node cha. Nho vi tri caret theo
    // text node (node van song sau khi chuyen) roi dat lai.
    function nhoCaret() {
      var s = window.getSelection();
      return (s && s.rangeCount) ? { n: s.anchorNode, o: s.anchorOffset } : null;
    }
    function datCaret(c) {
      if (!c || !c.n || !c.n.isConnected) return;
      try {
        var r = document.createRange(); r.setStart(c.n, c.o); r.collapse(true);
        var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
      } catch (x) {}
    }
    function laList(el) { return !!el && (el.tagName === "UL" || el.tagName === "OL"); }
    function cbCua(li) {
      for (var c = li.firstElementChild; c; c = c.nextElementSibling) {
        if (c.tagName === "INPUT" && c.classList.contains("md-cb")) return c;
      }
      return null;
    }
    // li khong co chu nao cua chinh no (bo qua checkbox va danh sach con)
    function liTrong(li) {
      var t = "";
      for (var c = li.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) t += c.textContent;
        else if (c.nodeType === 1 && !laList(c) && c.tagName !== "INPUT" && c.tagName !== "BR") t += c.textContent;
      }
      return !t.replace(/[\s ​]/g, "");
    }
    function caretSauCb(li) {
      var cb = cbCua(li);
      var sau = cb && cb.nextSibling;
      try {
        var r = document.createRange();
        if (sau && sau.nodeType === 3) r.setStart(sau, Math.min(1, sau.length));
        else if (cb) r.setStartAfter(cb);
        else r.setStart(li, 0);
        r.collapse(true);
        var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
      } catch (x) {}
    }
    // Bien li thanh task chua tick. Da co checkbox thi de yen (goi lai bao nhieu lan cung duoc).
    function dapCheckbox(li) {
      if (!li || li.tagName !== "LI" || cbCua(li)) return false;
      li.classList.add("task-item");
      // Chromium chep ca class cua li cu sang li moi: noi tu viec da xong la viec moi
      // sinh ra da mang vet gach ngang cua viec hoan thanh.
      li.classList.remove("task-done");
      // Enter giua dong: phan chu chay xuong mang theo dau cach (Chromium doi thanh nbsp), khong
      // bo thi luu ra "- [ ]  chu" thua mot dau cach.
      var dau = li.firstChild;
      if (dau && dau.nodeType === 3) dau.textContent = dau.textContent.replace(/^[  ]+/, "");
      li.insertAdjacentHTML("afterbegin", CB_HTML);
      return true;
    }
    // Chay SAU khi Chromium da tach li. truoc = li dung ngay tren li cu luc bam phim.
    function napTask(wys, truoc) {
      var li = liTuCaret(wys);
      if (!li) return;
      if (dapCheckbox(li)) caretSauCb(li);
      // Enter o DAU dong: Chromium day dong moi len TREN, caret o lai dong cu. Dong moi do
      // nam giua "truoc" va li dang chua caret.
      var tren = li.previousElementSibling;
      if (tren && tren !== truoc && tren.tagName === "LI") dapCheckbox(tren);
      baoDaSua(wys);
    }
    // Task rong + Enter: go checkbox, roi muc con thi lui ra mot cap, muc cap ngoai cung thi
    // tro thanh doan van thuong. Tra true neu da xu ly (chan Enter cua trinh duyet).
    function thoatDanhSach(li) {
      var cb = cbCua(li);
      if (cb) { var sau = cb.nextSibling; cb.remove(); if (sau && sau.nodeType === 3 && /^[  ]$/.test(sau.textContent)) sau.remove(); }
      li.classList.remove("task-item", "task-done");
      if (!li.firstChild) li.appendChild(document.createElement("br"));
      try { var r = document.createRange(); r.setStart(li, 0); r.collapse(true); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); } catch (x) {}
      if (thutLiRa(li)) return true;
      var list = li.parentNode;
      try { document.execCommand(list && list.tagName === "OL" ? "insertOrderedList" : "insertUnorderedList"); } catch (x) {}
      return true;
    }
    // Tab trong li: dua li vao danh sach con cua li ngay tren. Lam tay chu khong dung
    // lenh indent cua execCommand vi Chromium dat <ul> con ngang hang <li> (khong nam TRONG li),
    // Turndown doc kieu do khong ra thut le va muc con rot ve cap ngoai khi luu.
    function thutLiVao(li) {
      var tren = li.previousElementSibling, list = li.parentNode;
      if (!tren || tren.tagName !== "LI" || !laList(list)) return false;
      var c = nhoCaret();
      var con = tren.lastElementChild;
      if (!laList(con) || con.tagName !== list.tagName) {
        con = document.createElement(list.tagName);
        tren.appendChild(con);
      }
      con.appendChild(li);
      datCaret(c);
      return true;
    }
    // Shift+Tab: dua li ra ngoai mot cap, ngay sau li cha. Cac li dung SAU no trong cung danh
    // sach con theo no xuong lam con cua no, nhu vay thu tu tren duoi khong doi.
    function thutLiRa(li) {
      var list = li.parentNode, cha = list && list.parentNode;
      if (!laList(list) || !cha || cha.tagName !== "LI") return false;
      var c = nhoCaret();
      if (li.nextElementSibling) {
        var con = li.lastElementChild;
        if (!laList(con) || con.tagName !== list.tagName) {
          con = document.createElement(list.tagName);
          li.appendChild(con);
        }
        while (li.nextSibling) con.appendChild(li.nextSibling);
      }
      cha.parentNode.insertBefore(li, cha.nextSibling);
      if (!list.firstElementChild) list.remove();
      datCaret(c);
      return true;
    }
    function nhuongPhim(e) {
      if (e.isComposing || e.keyCode === 229) return true;     // bo go tieng Viet dang chot chu
      if (pop || document.querySelector(".ts-pop")) return true; // menu "/" hoac menu goi y task
      return false;
    }

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || e.defaultPrevented) return;
      if (e.isComposing || e.keyCode === 229) return;
      if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
      if (pop || document.querySelector(".ts-pop")) return;
      var ctx = ctxTu(e.target);
      if (!ctx) return;
      if (ctx.mode() === "source") {
        var ta = ctx.ta;
        if (!ta || ta.selectionStart !== ta.selectionEnd) return;
        var ed = enterDanhSach(ta.value, ta.selectionStart);
        if (!ed) return;
        e.preventDefault();
        suaTa(ta, ed);
        return;
      }
      var s = window.getSelection();
      if (!s || !s.isCollapsed) return;
      var li = liTuCaret(ctx.wys);
      if (!li || !li.classList.contains("task-item")) return;  // bullet/so: Chromium tu noi
      if (liTrong(li)) { if (thoatDanhSach(li)) { e.preventDefault(); baoDaSua(ctx.wys); } return; }
      var truoc = li.previousElementSibling, wys = ctx.wys;
      setTimeout(function () { napTask(wys, truoc); }, 0);
    }, true);

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Tab" || e.defaultPrevented) return;
      if (e.ctrlKey || e.metaKey || e.altKey || nhuongPhim(e)) return;
      var ctx = ctxTu(e.target);
      if (!ctx) return;
      if (ctx.mode() === "source") {
        var ta = ctx.ta;
        if (!ta) return;
        // Chan Tab ca khi khong co gi de lui: de mac dinh thi focus nhay khoi o soan.
        e.preventDefault();
        var ed = thutLe(ta.value, ta.selectionStart, ta.selectionEnd, e.shiftKey);
        if (ed) suaTa(ta, ed);
        return;
      }
      var li = liTuCaret(ctx.wys);
      if (li) {
        e.preventDefault();
        if (e.shiftKey ? thutLiRa(li) : thutLiVao(li)) baoDaSua(ctx.wys);
        return;
      }
      if (e.shiftKey) return;
      // Ngoai danh sach: chen 4 dau cach cung (nbsp). Dau cach thuong o dau doan bi
      // markdown nuot mat khi luu.
      e.preventDefault();
      try { document.execCommand("insertText", false, "    "); } catch (x) {}
    }, true);

    // Go "- " / "* " / "1. " o dau mot doan trong ban render -> thanh danh sach that. Khong co
    // buoc nay thi doan van giu nguyen chu "- ", Turndown luu ra "\- " va Enter khong noi duoc.
    document.addEventListener("keyup", function (e) {
      if (e.key !== " " || e.isComposing) return;
      var ctx = ctxTu(e.target);
      if (!ctx || ctx.mode() !== "wys") return;
      var s = window.getSelection();
      if (!s || !s.rangeCount || !s.isCollapsed) return;
      var n = s.anchorNode, el = n && (n.nodeType === 1 ? n : n.parentElement);
      if (!el || !ctx.wys.contains(el) || el.closest("li,pre,code,blockquote")) return;
      var khoi = el.closest("p,div,h1,h2,h3,h4,h5,h6");
      if (!khoi || khoi === ctx.wys || !/^(P|DIV)$/.test(khoi.tagName)) return;
      if (khoi.tagName === "DIV" && khoi.className) return;   // khoi dac biet: frontmatter, code...
      var dm = dauMucGo(khoi.textContent);
      if (!dm) return;
      khoi.innerHTML = "<br>";
      try { var r = document.createRange(); r.setStart(khoi, 0); r.collapse(true); s.removeAllRanges(); s.addRange(r); } catch (x) {}
      try { document.execCommand(dm.loai === "ol" ? "insertOrderedList" : "insertUnorderedList"); } catch (x) {}
      if (dm.loai === "ol" && dm.batDau !== 1) {
        var li = liTuCaret(ctx.wys), ol = li && li.parentNode;
        if (ol && ol.tagName === "OL") ol.setAttribute("start", String(dm.batDau));
      }
      baoDaSua(ctx.wys);
    });

    window.JavisEditorCmds = api;
  }

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
