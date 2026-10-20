/* note-images.js - chen anh vao note .md: DAN (Ctrl+V) / THA / bam nut chon tep -> nen lai ->
   luu vao `images/` -> nhung `![[images/2026-09-11-15-04-22.webp]]` vao dung cho caret. Kem
   tay keo doi co anh ngay trong ban render, luu thanh "|300" kieu Obsidian.

   Chay o CA HAI trinh sua .md - editor cay o trang Tep tin (console.js) va khung sua tu chat
   (file-editor.js) - vi ca hai dung cung lop .ne-wys / .ne-src, nen mot bo nghe o tang
   document la phu het, khong phai goi lap dat o tung noi mo editor.

   VI SAO ANH KHONG VAO `attachments/`: media_gc.media_dirs() coi `attachments/` + `inbox/` la
   VUNG CACHE, mac dinh xoa moi file qua 30 ngay hoac khi vung do vuot 300MB. Anh cua mot note
   thi CO NGUOI TRO VAO - don nó đi la mo note ra thay o xam "anh khong con", mat du lieu am
   tham khong mot dong bao. `images/` nam ngoai tam may don nen anh o lai vinh vien.

   Nen anh lam o TRINH DUYET bang canvas, khong phai o server: repo co y KHONG phu thuoc Pillow
   (xem chu thich trong requirements.txt), va nen truoc khi gui thi tiet kiem luon duong truyen.

   File chay duoc CA duoi node (test require) lan trong trinh duyet: phan DOM boc trong
   `if (typeof document !== "undefined")`, phan logic thuan de tran de test.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  // ---------------------------------------------------------------- so do
  var CANH_TOI_DA = 1920;        // canh dai nhat sau khi nen (du net cho man hinh 2K)
  var CHAT_LUONG = 0.82;         // chat luong webp/jpeg: mat mat khong thay bang mat
  var TRAN_MB = 25;              // to hon nua thi chan tu dau, khong nen noi trong tab

  function tw(khoa, tham) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, tham);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      if (tham) for (var k in tham) s = s.split("{" + k + "}").join(tham[k]);
      return s;
    } catch (e) { return khoa; }
  }

  // ---------------------------------------------------------------- ham thuan (test duoc)
  function hai(n) { return (n < 10 ? "0" : "") + n; }

  // Ten anh theo THOI GIAN MAY (khong phai UTC): buoi toi o Viet Nam ma lay gio UTC thi ten
  // anh lui ve hom truoc, xep thu muc theo ten la lech ngay. Chu repo chot dinh dang
  // yyyy-mm-dd-hh-mm-ss.
  function tenAnhTheoGio(d, duoi) {
    d = d || new Date();
    return d.getFullYear() + "-" + hai(d.getMonth() + 1) + "-" + hai(d.getDate()) + "-" +
      hai(d.getHours()) + "-" + hai(d.getMinutes()) + "-" + hai(d.getSeconds()) +
      (duoi || ".png");
  }

  var DUOI_THEO_LOAI = {
    "image/webp": ".webp", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/gif": ".gif", "image/svg+xml": ".svg", "image/bmp": ".bmp", "image/avif": ".avif",
    "image/heic": ".heic", "image/heif": ".heif",
  };
  function duoiTheoLoai(mime, tenGoc) {
    var m = String(mime == null ? "" : mime).toLowerCase().split(";")[0].trim();
    if (DUOI_THEO_LOAI[m]) return DUOI_THEO_LOAI[m];
    // Khong doan duoc tu MIME (clipboard co luc tra rong) thi lay duoi cua ten goc.
    var t = /(\.[a-z0-9]{2,5})$/i.exec(String(tenGoc == null ? "" : tenGoc));
    return t ? t[1].toLowerCase() : ".png";
  }
  function laAnh(mime, tenGoc) {
    if (/^image\//i.test(String(mime || ""))) return true;
    return /\.(png|jpe?g|gif|webp|bmp|svg|avif|heic|heif)$/i.test(String(tenGoc || ""));
  }
  // Anh HEIC/HEIF cua iPhone: Safari doc duoc (nen ra webp binh thuong), con Chrome/Edge tren
  // Windows thi KHONG. Gui nguyen file .heic len la note hien o xam o moi trinh duyet khong phai
  // Safari, nen doc khong duoc thi phai chan va noi ro, khong am tham luu mot file khong xem duoc.
  function laHeic(mime, tenGoc) {
    if (/^image\/hei[cf]/i.test(String(mime || ""))) return true;
    return /\.hei[cf]$/i.test(String(tenGoc || ""));
  }
  // Dinh dang KHONG duoc dua qua canvas: gif mat anh dong, svg la vector (ve ra canvas la
  // bien thanh anh diem, vua mo vua to hon ban goc).
  function khongNen(mime, tenGoc) {
    var m = String(mime || "").toLowerCase();
    if (m === "image/gif" || m === "image/svg+xml") return true;
    return /\.(gif|svg)$/i.test(String(tenGoc || ""));
  }
  // Khung moi sau khi thu nho theo canh dai nhat. KHONG bao gio phong to anh nho len.
  function khungMoi(w, h, max) {
    w = Math.max(1, Math.round(w || 0)); h = Math.max(1, Math.round(h || 0));
    max = max || CANH_TOI_DA;
    var canh = Math.max(w, h);
    if (canh <= max) return { w: w, h: h, doi: false };
    var k = max / canh;
    return { w: Math.max(1, Math.round(w * k)), h: Math.max(1, Math.round(h * k)), doi: true };
  }
  // Nen xong roi moi biet co an khong: anh PNG nho da toi uu san thi ban "nen" con NANG HON.
  // Luc do giu ban GOC - nen de tiet kiem dung luong, nen ra to hon la phan tac dung.
  function chonBanNhe(cyGoc, cyNen, daThuNho) {
    if (!cyNen) return "goc";
    if (daThuNho) return "nen";                 // da giam so diem anh: van lay ban nen
    return cyNen < cyGoc ? "nen" : "goc";
  }
  // Co moi khi keo tay: giu trong khoang doc duoc, lam tron ve so nguyen px.
  function coKhiKeo(coDau, dx, rongKhung) {
    var w = Math.round((coDau || 0) + (dx || 0));
    var tran = Math.max(80, Math.round(rongKhung || 0) || 2000);
    return Math.max(40, Math.min(w, tran));
  }

  var api = {
    tenAnhTheoGio: tenAnhTheoGio, duoiTheoLoai: duoiTheoLoai, laAnh: laAnh,
    khongNen: khongNen, laHeic: laHeic, khungMoi: khungMoi, chonBanNhe: chonBanNhe, coKhiKeo: coKhiKeo,
    CANH_TOI_DA: CANH_TOI_DA, TRAN_MB: TRAN_MB,
  };

  // ---------------------------------------------------------------- phan DOM
  if (typeof document !== "undefined") {
    function brainHienTai() {
      try { return (window.currentBrainPath && window.currentBrainPath()) || "brain"; }
      catch (e) { return "brain"; }
    }
    function ctxTu(target) {
      var EC = window.JavisEditorCmds;
      return (EC && EC.ctxTu) ? EC.ctxTu(target) : null;
    }

    // ----- bang trang thai nho o goc man hinh -----
    var bang = null, bangHen = null;
    function noi(chu, loai) {
      if (!bang) {
        bang = document.createElement("div");
        bang.className = "ni-status";
        document.body.appendChild(bang);
      }
      bang.textContent = chu;
      bang.className = "ni-status show" + (loai ? " ni-" + loai : "");
      clearTimeout(bangHen);
      // Loi thi de lau hon: nguoi dung can doc kip xem vi sao anh khong vao.
      bangHen = setTimeout(function () { if (bang) bang.className = "ni-status"; },
                           loai === "err" ? 5000 : 1800);
    }

    // ----- nen anh bang canvas -----
    function doAnh(file) {
      if (window.createImageBitmap) {
        // imageOrientation "from-image": xoay theo the EXIF. Anh dien thoai chup doc luu diem
        // anh nam ngang kem the xoay; ve thang ra canvas ma bo qua the do la anh nam nghieng,
        // va canvas bo luon EXIF nen ve sau khong con gi de xoay lai. (Ve qua canvas cung bo
        // luon toa do GPS trong anh, co loi khi chia se note.)
        var mo = function (tuyChon) {
          return window.createImageBitmap(file, tuyChon).then(function (bm) {
            return { nguon: bm, w: bm.width, h: bm.height, dong: function () { try { bm.close(); } catch (e) {} } };
          });
        };
        return mo({ imageOrientation: "from-image" }).catch(function () { return mo(); })
          .catch(function () { return doBangThe(file); });
      }
      return doBangThe(file);
    }
    // Duong du phong: the <img> (CSS image-orientation mac dinh from-image nen cung xoay dung).
    function doBangThe(file) {
      return new Promise(function (res, rej) {
        var url = URL.createObjectURL(file);
        var im = new Image();
        im.onload = function () {
          res({ nguon: im, w: im.naturalWidth, h: im.naturalHeight,
                dong: function () { URL.revokeObjectURL(url); } });
        };
        im.onerror = function () { URL.revokeObjectURL(url); rej(new Error("decode")); };
        im.src = url;
      });
    }
    function veRaBlob(canvas, loai, chatLuong) {
      return new Promise(function (res) {
        if (canvas.toBlob) canvas.toBlob(function (b) { res(b); }, loai, chatLuong);
        else res(null);
      });
    }
    // Tra { blob, duoi, goc } - goc=true nghia la giu nguyen ban goc, khong nen.
    function nenAnh(file) {
      var duoiGoc = duoiTheoLoai(file.type, file.name);
      if (khongNen(file.type, file.name)) {
        return Promise.resolve({ blob: file, duoi: duoiGoc, goc: true });
      }
      return doAnh(file).then(function (a) {
        var k = khungMoi(a.w, a.h, CANH_TOI_DA);
        var cv = document.createElement("canvas");
        cv.width = k.w; cv.height = k.h;
        var ct = cv.getContext("2d");
        ct.drawImage(a.nguon, 0, 0, k.w, k.h);
        a.dong();
        return veRaBlob(cv, "image/webp", CHAT_LUONG).then(function (b) {
          if (!b) return { blob: file, duoi: duoiGoc, goc: true };
          // Trinh duyet khong biet webp thi no tra ve png ma KHONG bao loi - phai lay duoi
          // theo loai blob THAT, khong thi file .webp ben trong lai la png.
          var duoi = duoiTheoLoai(b.type, "") || ".webp";
          if (chonBanNhe(file.size, b.size, k.doi) === "goc") {
            return { blob: file, duoi: duoiGoc, goc: true };
          }
          return { blob: b, duoi: duoi, goc: false };
        });
      }).catch(function () {
        // Khong doc duoc: HEIC thi chan (xem laHeic), dinh dang khac cu gui ban goc.
        if (laHeic(file.type, file.name)) return { heic: true };
        return { blob: file, duoi: duoiGoc, goc: true };
      });
    }

    // ----- tai len -----
    function taiLen(blob, ten) {
      var fd = new FormData();
      fd.append("file", blob, ten);
      fd.append("brain", brainHienTai());
      fd.append("folder", "images");          // server tu tim/tao dung thu muc that
      return fetch("/files/upload", { method: "POST", body: fd })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (d) {
          if (!d || !d.ok || !d.path) throw new Error((d && d.error) || tw("nimg.loi_tai"));
          return d.path;
        });
    }

    // ----- chen vao editor -----
    // Ban render: dung DUNG markup ma mdToHtml sinh ra cho ![[..]], nho vay luat turndown
    // "wikiimg" nhan lai duoc va luu nguoc ra ![[..]] y nguyen.
    function htmlAnh(path) {
      var md = "![[" + path + "]]";
      var h = window.mdToHtml ? window.mdToHtml(md) : "";
      var hop = document.createElement("div");
      hop.innerHTML = h;
      // mdToHtml boc trong <p>; chen ca the <p> vao giua mot doan dang go la bi xe doan.
      var con = (hop.children.length === 1 && hop.firstElementChild.tagName === "P")
        ? hop.firstElementChild.innerHTML : hop.innerHTML;
      return con || null;
    }
    function chen(ctx, path) {
      if (!ctx) return false;
      if (ctx.mode() === "source") {
        var ta = ctx.ta;
        if (!ta) return false;
        var t = "![[" + path + "]]";
        try { ta.focus(); } catch (e) {}
        var ok = false;
        try { ok = document.execCommand("insertText", false, t); } catch (e) {}
        if (!ok) {
          var s = ta.selectionStart, e2 = ta.selectionEnd;
          ta.value = ta.value.slice(0, s) + t + ta.value.slice(e2);
          var p = s + t.length;
          try { ta.setSelectionRange(p, p); } catch (e) {}
          try { ta.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
        }
        return true;
      }
      var wys = ctx.wys;
      if (!wys) return false;
      var html = htmlAnh(path);
      if (!html) return false;
      try { wys.focus(); } catch (e) {}
      // Caret co the dang o ngoai (vua bam nut tren thanh cong cu): dat ve cuoi bai cho khoi
      // chen anh vao hu khong.
      try {
        var sel = window.getSelection();
        var trong = !sel || !sel.rangeCount ||
          !(sel.anchorNode && (sel.anchorNode === wys || wys.contains(sel.anchorNode)));
        if (trong) {
          var r = document.createRange(); r.selectNodeContents(wys); r.collapse(false);
          sel.removeAllRanges(); sel.addRange(r);
        }
      } catch (e) {}
      try { document.execCommand("insertHTML", false, html + "&nbsp;"); } catch (e) { return false; }
      // Tu luu: chen anh xong ma chua luu, dong khung la link anh bay mat con file anh nam lai
      // trong images/ khong ai tro toi.
      try { wys.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
      return true;
    }

    // ----- duong di chinh: tep -> nen -> tai len -> chen -----
    function xuLyMotTep(ctx, file) {
      if (!laAnh(file.type, file.name)) return Promise.resolve(false);
      if (file.size > TRAN_MB * 1024 * 1024) {
        noi(tw("nimg.qua_lon", { mb: TRAN_MB }), "err");
        return Promise.resolve(false);
      }
      noi(tw("nimg.dang_xu_ly"));
      return nenAnh(file).then(function (kq) {
        if (kq.heic) { noi(tw("nimg.heic"), "err"); return false; }
        return taiLen(kq.blob, tenAnhTheoGio(new Date(), kq.duoi)).then(function (path) {
          if (!chen(ctx, path)) throw new Error(tw("nimg.loi_chen"));
          noi(tw("nimg.xong", { kb: Math.max(1, Math.round(kq.blob.size / 1024)) }), "ok");
          return true;
        });
      }).catch(function (err) {
        noi(tw("nimg.loi", { loi: (err && err.message) || "?" }), "err");
        return false;
      });
    }
    // Nhieu anh mot luot: lam TUAN TU de thu tu chen dung nhu thu tu nguoi dung chon, va de
    // ten theo giay khong doi dau nhau trong cung mot lan.
    function xuLyNhieuTep(ctx, files) {
      var ds = [];
      for (var i = 0; i < files.length; i++) if (laAnh(files[i].type, files[i].name)) ds.push(files[i]);
      if (!ds.length) return Promise.resolve(0);
      var n = 0;
      return ds.reduce(function (chuoi, f) {
        return chuoi.then(function () {
          return xuLyMotTep(ctx, f).then(function (ok) { if (ok) n++; });
        });
      }, Promise.resolve()).then(function () { return n; });
    }

    // ----- DAN (Ctrl+V) -----
    document.addEventListener("paste", function (e) {
      var ctx = ctxTu(e.target);
      if (!ctx) return;
      var dt = e.clipboardData;
      if (!dt) return;
      var files = [];
      // dt.files rong tren mot so ban Firefox khi dan anh chup man hinh -> phai doc ca items.
      if (dt.files && dt.files.length) {
        for (var i = 0; i < dt.files.length; i++) files.push(dt.files[i]);
      } else if (dt.items) {
        for (var j = 0; j < dt.items.length; j++) {
          if (dt.items[j].kind === "file") {
            var f = dt.items[j].getAsFile();
            if (f) files.push(f);
          }
        }
      }
      var anh = files.filter(function (f) { return laAnh(f.type, f.name); });
      if (!anh.length) return;             // dan CHU thi de editor lo binh thuong
      e.preventDefault();
      xuLyNhieuTep(ctx, anh);
    }, true);

    // ----- THA tep vao khung soan -----
    document.addEventListener("dragover", function (e) {
      var ctx = ctxTu(e.target);
      if (!ctx) return;
      var dt = e.dataTransfer;
      if (!dt || !dt.types || Array.prototype.indexOf.call(dt.types, "Files") < 0) return;
      e.preventDefault();
      try { dt.dropEffect = "copy"; } catch (err) {}
    });
    document.addEventListener("drop", function (e) {
      var ctx = ctxTu(e.target);
      if (!ctx) return;
      var dt = e.dataTransfer;
      if (!dt || !dt.files || !dt.files.length) return;
      var anh = [];
      for (var i = 0; i < dt.files.length; i++) {
        if (laAnh(dt.files[i].type, dt.files[i].name)) anh.push(dt.files[i]);
      }
      if (!anh.length) return;
      e.preventDefault();
      // Tha KHONG dat duoc caret theo diem tha trong moi trinh duyet, nen chen tai caret dang
      // co. Bam mot cai vao cho muon chen roi tha la dung y.
      xuLyNhieuTep(ctx, anh);
    }, true);

    // ----- nut tren thanh cong cu: chon tep -----
    function chonTep(ctx) {
      var inp = document.createElement("input");
      inp.type = "file"; inp.accept = "image/*"; inp.multiple = true;
      inp.style.display = "none";
      document.body.appendChild(inp);
      inp.addEventListener("change", function () {
        var fs = inp.files;
        inp.remove();
        if (fs && fs.length) xuLyNhieuTep(ctx, fs);
      });
      inp.click();
    }

    // ================================================================ TAY KEO DOI CO ANH
    // Chromium KHONG con tay keo anh san trong contenteditable (Firefox co, qua
    // enableObjectResizing) nen phai tu ve mot tay keo noi tuyen tren anh.
    var tay = null, anhDangTro = null, keo = null;

    function anhTrongEditor(el) {
      if (!el || el.tagName !== "IMG") return null;
      var wys = el.closest ? el.closest(".ne-wys") : null;
      return wys ? el : null;
    }
    function veTay() {
      if (!anhDangTro || !anhDangTro.isConnected) return anTay();
      var r = anhDangTro.getBoundingClientRect();
      if (!r.width && !r.height) return anTay();
      tay.style.left = (r.right - 7) + "px";
      tay.style.top = (r.bottom - 7) + "px";
      tay.classList.add("show");
    }
    function anTay() {
      anhDangTro = null;
      if (tay) tay.classList.remove("show");
    }
    function hienTay(img) {
      if (!tay) {
        tay = document.createElement("div");
        tay.className = "ni-grip";
        tay.title = tw("nimg.tay_keo");
        document.body.appendChild(tay);
        tay.addEventListener("mousedown", batDauKeo);
        // Bam dup vao tay keo = ve co GOC (bo "|300"), khong phai doan mo lai note de sua tay.
        tay.addEventListener("dblclick", function (e) {
          e.preventDefault();
          if (!anhDangTro) return;
          anhDangTro.style.width = ""; anhDangTro.style.height = "";
          anhDangTro.removeAttribute("data-img-size");
          banInput(anhDangTro);
          veTay();
        });
      }
      anhDangTro = img;
      veTay();
    }
    function banInput(img) {
      try {
        var wys = img.closest(".ne-wys");
        if (wys) wys.dispatchEvent(new Event("input", { bubbles: true }));
      } catch (e) {}
    }
    function batDauKeo(e) {
      if (!anhDangTro) return;
      e.preventDefault(); e.stopPropagation();
      var wys = anhDangTro.closest(".ne-wys");
      keo = {
        img: anhDangTro, x: e.clientX,
        w: anhDangTro.getBoundingClientRect().width,
        tran: wys ? wys.clientWidth - 28 : 0,
      };
      document.body.classList.add("ni-keo");
      document.addEventListener("mousemove", dangKeo, true);
      document.addEventListener("mouseup", xongKeo, true);
    }
    function dangKeo(e) {
      if (!keo) return;
      e.preventDefault();
      var w = coKhiKeo(keo.w, e.clientX - keo.x, keo.tran);
      keo.img.style.width = w + "px";
      keo.img.style.height = "";            // giu ti le: chi dat mot chieu
      keo.img.setAttribute("data-img-size", String(w));
      veTay();
    }
    function xongKeo() {
      document.removeEventListener("mousemove", dangKeo, true);
      document.removeEventListener("mouseup", xongKeo, true);
      document.body.classList.remove("ni-keo");
      if (keo) banInput(keo.img);           // co moi -> tu luu
      keo = null;
      veTay();
    }

    document.addEventListener("mouseover", function (e) {
      if (keo) return;
      if (tay && (e.target === tay || (tay.contains && tay.contains(e.target)))) return;
      var img = anhTrongEditor(e.target);
      if (img) hienTay(img);
      else if (anhDangTro) anTay();
    });
    // Cuon hoac doi co cua so: toa do tay keo (position:fixed) lech ngay -> ve lai.
    window.addEventListener("scroll", function () { if (anhDangTro && !keo) veTay(); }, true);
    window.addEventListener("resize", function () { if (anhDangTro) anTay(); });

    api.chonTep = chonTep;
    api.xuLyNhieuTep = xuLyNhieuTep;
    window.JavisNoteImages = api;
  }

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
