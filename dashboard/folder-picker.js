/* folder-picker.js - hộp CHỌN thư mục dùng chung cho cả dashboard.

   Vì sao có file này: app.js đã có một hộp chọn thư mục (#folderModal) nhưng nó GẮN CHẶT vào
   một việc duy nhất - chọn brain: nút "Dùng folder này" của nó gọi thẳng addCustomBrain rồi
   nạp lại graph. Mượn lại đúng cái hộp đó cho trang Coding thì mỗi lần bấm chọn thư mục code,
   brain của người dùng cũng bị đổi theo. Nên phần TÁI DÙNG ĐƯỢC ở đây là bộ lớp CSS
   (.folder-modal, .fm-*) và endpoint GET /browse: file này chỉ thêm đúng phần khung nối và
   một hàm callback, không chép lại kiểu dáng nào.

   Cách dùng:

     JavisFolderPicker.open({
       tieuDe: "Thêm thư mục",       // chữ ở đầu hộp
       ghiChu: "...",                 // dòng gợi ý ở chân hộp khi chưa có gì để nói
       nhanDung: "Dùng thư mục này",  // chữ trên nút xác nhận
       batDau: "/home/me/code",       // thư mục mở sẵn (rỗng = màn ĐIỂM XUẤT PHÁT)
       brain: "brain",                // brain đang mở, để lấy đúng điểm xuất phát
       demMd: false,                  // true mới hiện số file .md (chỉ hợp khi chọn brain)
       chon: async function (path) { ... return "câu lỗi" hoặc để trống là đóng hộp; },
     });

   KHÔNG dùng ký tự em dash. Chữ hiện ra lấy từ từ điển window.t. */
(function () {
  "use strict";

  var W = (typeof window !== "undefined") ? window : {};
  var t = function (k, v) { return (W.t ? W.t(k, v) : k); };
  var ic = function (n) { return (W.ic ? W.ic(n) : ""); };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  /** Nhãn phụ của một điểm xuất phát.
   *
   *  Viết ĐỦ CHỮ từng khoá thay vì ghép `"fp.start_" + x.ghi_chu`: ghép chuỗi thì bộ quét i18n
   *  không thấy khoá nào, nên xoá nhầm một dòng trong vi.json vẫn xanh và người dùng là người
   *  đầu tiên thấy mã khoá hiện trên màn hình. */
  function nhanDiem(ghiChu) {
    if (ghiChu === "brain") return t("fp.start_brain");
    if (ghiChu === "brains") return t("fp.start_brains");
    if (ghiChu === "home") return t("fp.start_home");
    if (ghiChu === "drive") return t("fp.start_drive");
    return "";
  }

  function open(o) {
    o = o || {};
    dong();
    var hienTai = "", dangTai = false, diemDs = null;

    var lop = document.createElement("div");
    lop.className = "modal-overlay open";
    lop.id = "fpModal";
    lop.innerHTML = '' +
      '<div class="folder-modal" role="dialog" aria-modal="true">' +
        '<div class="fm-head">' +
          "<span>" + ic("folder-open") + " " + esc(o.tieuDe || t("fp.title")) + "</span>" +
          '<span class="fp-nut">' +
            // Đường VỀ màn điểm xuất phát. Duyệt sâu vài tầng rồi muốn nhảy sang một nhánh
            // khác hẳn thì không có nút này là phải bấm "lên trên" chục lần hoặc đóng hộp đi
            // mở lại.
            '<button type="button" class="fm-close" data-nha title="' + esc(t("fp.starts")) +
              '">' + ic("house") + "</button>" +
            '<button type="button" class="fm-close" data-dong>' + ic("x") + "</button>" +
          "</span>" +
        "</div>" +
        // Ô đường dẫn vừa là chỗ BÁO đang đứng ở đâu, vừa là chỗ DÁN một đường dẫn dài rồi
        // Enter để nhảy thẳng tới. Người đã có sẵn đường dẫn trong tay không phải bấm lần
        // lượt qua mười tầng thư mục mới tới nơi.
        '<div class="fm-path">' +
          '<input type="text" class="fp-go" spellcheck="false" autocomplete="off"' +
                ' aria-label="' + esc(t("fp.path_label")) + '" placeholder="' + esc(t("fp.path_ph")) + '">' +
        "</div>" +
        '<div class="fm-list"></div>' +
        '<div class="fm-foot">' +
          '<span class="fm-hint"></span>' +
          '<button type="button" class="fm-use" data-dung>' +
            esc(o.nhanDung || t("fp.use")) + "</button>" +
        "</div>" +
      "</div>";
    document.body.appendChild(lop);

    var ds = lop.querySelector(".fm-list");
    var oGo = lop.querySelector(".fp-go");
    var goi = lop.querySelector(".fm-hint");
    var nutDung = lop.querySelector("[data-dung]");

    function mach(cau, loi) {
      goi.textContent = cau || "";
      goi.classList.toggle("fm-hint-loi", !!loi);
    }

    /** Danh sách điểm xuất phát, hỏi server MỘT lần rồi giữ lại. Hỏng thì coi như không có,
     *  và mọi đường gọi lui về hành vi cũ (duyệt thẳng thư mục nhà). */
    async function taiDiem() {
      if (diemDs) return diemDs;
      try {
        var r = await fetch("/browse/starts?brain=" + encodeURIComponent(o.brain || ""));
        var d = await r.json();
        diemDs = (d && d.diem) || [];
      } catch (e) { diemDs = []; }
      return diemDs;
    }

    /** Màn ĐIỂM XUẤT PHÁT, thay cho việc mở thẳng ở thư mục nhà.
     *
     *  Trên VPS thư mục nhà thường chỉ có file ẩn, mà /browse lọc hết file ẩn, nên hộp mở ra
     *  trống trơn và người dùng phải quay về gõ tay đường dẫn - đúng thứ hộp duyệt sinh ra để
     *  tránh. Không lấy được điểm nào thì vẫn duyệt thư mục nhà như trước, chứ không bày một
     *  màn rỗng thứ hai. */
    async function veDiem() {
      var ds2 = await taiDiem();
      if (!lop.parentNode) return;
      // Không có điểm nào (server cũ, hoặc mọi chỗ đều không tồn tại) thì duyệt thẳng thư
      // mục nhà như bản trước. Gọi taiThuMuc chứ KHÔNG gọi duyet(""): duyet("") quay ngược
      // về chính hàm này và thành vòng lặp không lối ra.
      if (!ds2.length) return taiThuMuc("");
      hienTai = "";
      if (document.activeElement !== oGo) oGo.value = "";
      ds.innerHTML = "";
      ds2.forEach(function (x) {
        hang("", x.ten, function () { duyet(x.duong_dan); },
             nhanDiem(x.ghi_chu), x.git, x.duong_dan);
      });
      nutDung.disabled = true;      // chưa đứng ở thư mục nào thì chưa chọn được gì
      mach(t("fp.starts_note"));
    }

    /** Đường vào chung: rỗng = màn điểm xuất phát, có đường dẫn = duyệt thư mục đó. */
    function duyet(p) {
      return p ? taiThuMuc(p) : veDiem();
    }

    async function taiThuMuc(p) {
      dangTai = true;
      mach(t("common.loading"));
      try {
        var r = await fetch("/browse?md=" + (o.demMd ? "1" : "0") + "&path=" + encodeURIComponent(p || ""));
        var d = await r.json();
        if (!lop.parentNode) return;             // người dùng đã đóng hộp trong lúc chờ
        hienTai = d.path || "";
        // Không đụng ô khi người dùng đang gõ dở trong đó: ghi đè giữa chừng là cướp phím.
        if (document.activeElement !== oGo) oGo.value = hienTai;
        ds.innerHTML = "";
        if (d.parent !== null && d.parent !== undefined) {
          hang("up", t("fp.up"), function () { duyet(d.parent); }, "");
        }
        (d.dirs || []).forEach(function (x) {
          var nhan = x.git ? t("fp.git") : (x.md ? x.md + " .md" : "");
          hang("", x.name, function () { duyet(x.path); }, nhan, x.git, x.path);
        });
        nutDung.disabled = !hienTai;
        if (d.error) mach(d.error, true);
        else if (!(d.dirs || []).length) mach(t("fp.empty"));
        else mach(o.ghiChu || t("fp.pick"));
      } catch (e) {
        if (lop.parentNode) mach(t("app.err_net"), true);
      }
      dangTai = false;
    }

    function hang(lopThem, ten, bam, nhan, laGit, duongDan) {
      var row = document.createElement("div");
      row.className = "fm-row" + (lopThem ? " " + lopThem : "");
      if (duongDan) row.title = duongDan;
      row.innerHTML = '<span class="fm-name">' + ic(lopThem === "up" ? "arrow-up" : (laGit ? "folder-git" : "folder")) +
        " " + esc(ten) + "</span>" +
        (nhan ? '<span class="fm-md">' + esc(nhan) + "</span>" : "");
      row.onclick = bam;
      ds.appendChild(row);
    }

    function dongHop() { if (lop.parentNode) lop.parentNode.removeChild(lop); }

    lop.onclick = function (e) { if (e.target === lop) dongHop(); };
    lop.querySelector("[data-dong]").onclick = dongHop;
    lop.querySelector("[data-nha]").onclick = function () { if (!dangTai) veDiem(); };
    lop.addEventListener("keydown", function (e) { if (e.key === "Escape") dongHop(); });
    oGo.onkeydown = function (e) {
      if (e.key !== "Enter" || dangTai) return;
      e.preventDefault();
      duyet((oGo.value || "").trim());
    };
    nutDung.onclick = async function () {
      // Lấy chữ TRONG ô chứ không lấy biến: người dùng có thể vừa dán một đường dẫn rồi bấm
      // thẳng nút này mà chưa Enter, và bỏ qua cái họ vừa gõ là lặng lẽ làm sai ý.
      var p = (oGo.value || "").trim() || hienTai;
      if (!p) return;
      nutDung.disabled = true;
      mach(t("common.loading"));
      var loi = "";
      try { loi = (o.chon ? await o.chon(p) : "") || ""; }
      catch (e) { loi = t("app.err_net"); }
      nutDung.disabled = false;
      if (loi) { mach(loi, true); return; }
      dongHop();
    };

    duyet(o.batDau || "");     // rỗng = màn điểm xuất phát (xem veDiem)
    setTimeout(function () { try { nutDung.focus(); } catch (e) {} }, 0);
  }

  function dong() {
    var cu = document.getElementById("fpModal");
    if (cu && cu.parentNode) cu.parentNode.removeChild(cu);
  }

  W.JavisFolderPicker = { open: open, dong: dong };
  // Phơi cho test node: tests/js/test_hop_chon_thu_muc.js dựng một DOM giả rồi GỌI THẬT hàm
  // open(), thay vì quét chuỗi trên mã nguồn.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { open: open, dong: dong };
  }
})();
