// ============================================================
// Javis - CÂY THƯ MỤC dùng lại được (file-tree.js)
//
// Trang Tệp tin duyệt theo kiểu "một thư mục một màn": vào thư mục con là mất dấu chỗ vừa
// đứng, muốn quay ra phải bấm Lên. Nó hợp cho việc quản lý, nhưng lúc đang chat thì thứ cần
// là NHÌN THẤY brain đang có gì và file nằm ở đâu, mà không rời khung chat.
//
// Module này dựng cây xổ ra thu vào, nạp con theo nhu cầu (bấm mở thư mục nào mới gọi
// /files/list thư mục đó), nên brain vài nghìn file vẫn mở tức thì.
//
// Hai đường vào chính:
//   mount(container, opts) -> ctl   dựng cây trong một khung bất kỳ
//   ctl.reveal(rootRel)             xổ cây tới đúng file đó rồi tô sáng nó
//
// `reveal` là lý do module này tồn tại: tìm ra file rồi mà không biết nó nằm thư mục nào thì
// lần sau vẫn phải đi tìm lại. Bấm "Vị trí" ở kết quả tìm kiếm là cây tự mở hết các nhánh cha
// và cuộn tới nơi.
//
// ĐƯỜNG DẪN CÓ HAI HỆ, đừng lẫn:
//   rootRel  - tương đối TRẦN duyệt (thứ /files/list và /files/search nói)
//   brainRel - tương đối GỐC BRAIN (thứ JavisEditFile/JavisOpenFiles nhận)
// `home` (từ /files/list) là tiền tố nối hai hệ đó. Lẫn hai hệ là mở nhầm file hoặc mở hụt.
// ============================================================
(function () {
  "use strict";

  // ---- Phần THUẦN: không đụng DOM, không đụng mạng. Tách ra để test gọi thẳng. ----

  function chuanHoa(p) {
    return String(p == null ? "" : p).replace(/\\/g, "/").replace(/^\.?\/+/, "").replace(/\/+$/, "");
  }

  /** rootRel -> brainRel. Ngoài brain (lên trần) thì trả "" vì trình sửa không mở được. */
  function toBrainRel(rootRel, home) {
    var r = chuanHoa(rootRel), h = chuanHoa(home);
    if (!h) return r;
    if (r === h) return "";
    return r.indexOf(h + "/") === 0 ? r.slice(h.length + 1) : "";
  }

  /**
   * Các thư mục CHA cần xổ để thấy `rootRel`, từ gốc cây đi xuống.
   * Trả cả chính `home` vì cây luôn bắt đầu từ đó.
   * File ngoài brain -> mảng rỗng: cây này chỉ nhận trong brain.
   */
  function ancestorsOf(rootRel, home) {
    var h = chuanHoa(home), rel = toBrainRel(rootRel, home);
    if (!rel) return chuanHoa(rootRel) === h ? [h] : [];
    var phan = rel.split("/");
    phan.pop();                       // bỏ chính nó, chỉ giữ các cha
    var ra = [h], acc = h;
    phan.forEach(function (x) { acc = acc + "/" + x; ra.push(acc); });
    return ra;
  }

  var API = { toBrainRel: toBrainRel, ancestorsOf: ancestorsOf, chuanHoa: chuanHoa };

  // Chạy trong Node (test) thì dừng ở đây: không có document để dựng gì cả.
  if (typeof window === "undefined" || typeof document === "undefined") {
    if (typeof module !== "undefined" && module.exports) module.exports = API;
    return;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function ic(name) {
    try { return window.ic ? window.ic(name) : ""; } catch (e) { return ""; }
  }
  function brainHienTai() {
    try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; }
    catch (e) { return "brain"; }
  }

  var THU_MUC_AN = /^(\.|__pycache__$|node_modules$)/;

  function mount(container, opts) {
    if (!container) return null;
    opts = opts || {};
    var layBrain = opts.brain || brainHienTai;

    container.innerHTML =
      '<input class="ftree-search" type="search" spellcheck="false" ' +
      'placeholder="Tìm file trong brain…">' +
      '<div class="ftree-body"><div class="ftree-empty">Đang tải…</div></div>';
    var oSearch = container.querySelector(".ftree-search");
    var oBody = container.querySelector(".ftree-body");

    var home = "";                 // thư mục gốc brain, theo hệ rootRel
    var con = {};                  // rootRel -> [item] đã nạp
    var moRa = {};                 // rootRel -> đang xổ
    var dangSang = "";             // rootRel của node vừa reveal, để tô sáng
    var brainCu = null, timer = null, lanTim = 0;

    function url(path) {
      var u = "/files/list?brain=" + encodeURIComponent(layBrain());
      return path == null ? u : u + "&path=" + encodeURIComponent(path);
    }

    async function napCon(path) {
      if (con[path]) return con[path];
      var d = await (await fetch(url(path))).json();
      if (d && d.error) throw new Error(d.error);
      if (!home && d && typeof d.path === "string") home = chuanHoa(d.home || d.path);
      con[path] = (d.items || []).filter(function (it) {
        return !(it.type === "dir" && THU_MUC_AN.test(it.name));
      });
      return con[path];
    }

    /** Nạp gốc: gọi KHÔNG kèm path để server tự trả đúng thư mục brain + tiền tố home. */
    async function napGoc() {
      var d = await (await fetch(url(null))).json();
      if (d && d.error) throw new Error(d.error);
      home = chuanHoa(d.home || d.path || "");
      con[home] = (d.items || []).filter(function (it) {
        return !(it.type === "dir" && THU_MUC_AN.test(it.name));
      });
      moRa[home] = true;
      return con[home];
    }

    function moFile(rootRel) {
      var rel = toBrainRel(rootRel, home);
      if (!rel) return;
      if (typeof opts.onOpen === "function") { opts.onOpen(rel, rootRel); return; }
      if (typeof window.JavisEditFile === "function") window.JavisEditFile(rel);
      else if (typeof window.JavisOpenFiles === "function") window.JavisOpenFiles(rel);
    }

    function veHang(it, cha, sau) {
      var rootRel = cha ? cha + "/" + it.name : it.name;
      var laThuMuc = it.type === "dir";
      var mo = !!moRa[rootRel];
      var row = document.createElement("div");
      row.className = "ftree-row" + (laThuMuc ? " is-dir" : "")
        + (rootRel === dangSang ? " hit" : "");
      row.style.paddingLeft = (6 + sau * 13) + "px";
      row.dataset.path = rootRel;
      row.innerHTML =
        '<span class="ftree-caret">' + (laThuMuc ? (mo ? "▾" : "▸") : "") + "</span>" +
        '<span class="ftree-ico">' + ic(laThuMuc ? (mo ? "folder-open" : "folder") : "file-text") + "</span>" +
        '<span class="ftree-name">' + esc(it.name) + "</span>";
      row.onclick = function () { laThuMuc ? doiTrangThai(rootRel) : moFile(rootRel); };
      return row;
    }

    function veNhanh(path, sau, ra) {
      (con[path] || []).forEach(function (it) {
        ra.appendChild(veHang(it, path, sau));
        var rootRel = path + "/" + it.name;
        if (it.type === "dir" && moRa[rootRel]) veNhanh(rootRel, sau + 1, ra);
      });
    }

    function ve() {
      var giuCuon = oBody.scrollTop;
      oBody.innerHTML = "";
      if (!(con[home] || []).length) {
        oBody.innerHTML = '<div class="ftree-empty">Thư mục trống.</div>';
        return;
      }
      var box = document.createElement("div");
      veNhanh(home, 0, box);
      oBody.appendChild(box);
      oBody.scrollTop = giuCuon;
      var hit = oBody.querySelector(".ftree-row.hit");
      if (hit && hit.scrollIntoView) hit.scrollIntoView({ block: "center" });
    }

    async function doiTrangThai(path) {
      if (moRa[path]) { delete moRa[path]; ve(); return; }
      moRa[path] = true;
      try { await napCon(path); } catch (e) { delete moRa[path]; }
      ve();
    }

    /** Xổ cây tới đúng `rootRel` rồi tô sáng. Đây là thứ biến "tìm thấy" thành "biết nó ở đâu". */
    async function reveal(rootRel) {
      var p = chuanHoa(rootRel);
      if (!home) { try { await napGoc(); } catch (e) { return; } }
      var cha = ancestorsOf(p, home);
      if (!cha.length) return;
      for (var i = 0; i < cha.length; i++) {
        moRa[cha[i]] = true;
        try { await napCon(cha[i]); } catch (e) { /* thư mục hỏng thì dừng ở nhánh đã mở được */ }
      }
      dangSang = p;
      ve();
    }

    async function timKiem(q) {
      var seq = ++lanTim;
      oBody.innerHTML = '<div class="ftree-empty">Đang tìm…</div>';
      var d;
      try {
        d = await (await fetch("/files/search?brain=" + encodeURIComponent(layBrain())
          + "&q=" + encodeURIComponent(q) + "&mode=name&limit=60")).json();
      } catch (e) {
        if (seq === lanTim) oBody.innerHTML = '<div class="ftree-empty">Lỗi tìm kiếm.</div>';
        return;
      }
      if (seq !== lanTim) return;
      var items = (d && d.items) || [];
      if (!items.length) {
        oBody.innerHTML = '<div class="ftree-empty">Không tìm thấy file nào.</div>';
        return;
      }
      oBody.innerHTML = "";
      items.forEach(function (it) {
        var thuMuc = chuanHoa(it.path).split("/").slice(0, -1).join("/");
        var row = document.createElement("div");
        row.className = "ftree-hit";
        row.innerHTML =
          '<span class="ftree-ico">' + ic("file-text") + "</span>" +
          '<span class="ftree-hit-main"><span class="ftree-hit-name">' + esc(it.name) + "</span>" +
          '<span class="ftree-hit-path">' + esc(toBrainRel(thuMuc, home) || "gốc brain") + "</span></span>" +
          '<button class="ftree-loc" type="button" title="Xổ cây tới chỗ file này đang nằm">Vị trí</button>';
        row.querySelector(".ftree-hit-main").onclick = function () { moFile(it.path); };
        row.querySelector(".ftree-ico").onclick = function () { moFile(it.path); };
        // Không xoá ô tìm kiếm: người dùng hay muốn xem vị trí vài kết quả liên tiếp, xoá đi
        // là mỗi lần lại phải gõ lại.
        row.querySelector(".ftree-loc").onclick = async function (e) {
          e.stopPropagation();
          oSearch.value = "";
          await reveal(it.path);
        };
        oBody.appendChild(row);
      });
    }

    oSearch.oninput = function () {
      clearTimeout(timer);
      var q = oSearch.value.trim();
      timer = setTimeout(function () {
        if (q) timKiem(q);
        else { lanTim++; ve(); }
      }, 280);
    };

    async function napLai(ep) {
      var b = layBrain();
      if (ep || b !== brainCu) {
        brainCu = b; home = ""; con = {}; moRa = {}; dangSang = "";
        oBody.innerHTML = '<div class="ftree-empty">Đang tải…</div>';
      }
      if (home && !ep) return;
      try { await napGoc(); ve(); }
      catch (e) { oBody.innerHTML = '<div class="ftree-empty">Không đọc được thư mục brain.</div>'; }
    }

    napLai(true);
    return { reveal: reveal, refresh: function () { napLai(false); }, reload: function () { napLai(true); } };
  }

  API.mount = mount;
  window.JavisFileTree = API;
})();
