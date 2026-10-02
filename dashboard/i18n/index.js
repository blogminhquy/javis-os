/* i18n cho dashboard - KHÔNG có bước build, KHÔNG có thư viện ngoài.
 *
 * Dashboard của Javis là JS thuần phục vụ qua StaticFiles: không webpack, không vite, không
 * bundler. Nên mọi giải pháp i18n "chuẩn công nghiệp" đều không lắp vào được, và đó là chuyện
 * tốt: cái vừa vặn ở đây nhỏ hơn nhiều so với một khung nặng.
 *
 * BA LUẬT, và mỗi luật đều để tránh một tai nạn cụ thể:
 *
 * 1. KEY LÀ ASCII CÓ PHÂN CẤP, không phải chính chuỗi tiếng Việt.
 *    Lấy chuỗi làm key thì sửa một lỗi chính tả trong bản tiếng Việt là hỏng luôn bản dịch
 *    của mọi ngôn ngữ khác - một kiểu hỏng không đáng có và rất khó truy.
 *
 * 2. SUY BIẾN <ngôn ngữ đã chọn> -> en -> vi -> chính key.
 *    `vi.json` đủ 100% key theo định nghĩa vì nó được rút ra từ mã đang chạy. Nhờ vậy một
 *    bản dịch làm dở KHÔNG bao giờ để lại ô chữ trống hay một key trần trên màn hình.
 *    Từ 0.66.0 tiếng Anh đứng TRƯỚC tiếng Việt trong chuỗi này: người đọc tiếng Nhật gặp một
 *    chỗ chưa dịch thì tiếng Anh đọc được, còn tiếng Việt thì không.
 *
 * Chưa ai chọn ngôn ngữ trên máy này thì theo NGÔN NGỮ TRÌNH DUYỆT (thứ tự navigator.languages,
 * lấy cái đầu tiên có từ điển), không khớp cái nào thì tiếng Anh. Máy đã chọn rồi (localStorage)
 * thì giữ nguyên. Người dùng cũ mà trình duyệt để tiếng Anh vẫn không bị đổi ngôn ngữ trong im
 * lặng: console.js đọc `ui_lang` đã lưu trên server và áp lại (xem `daChon()`).
 *
 * 3. TỪ ĐIỂN LÀ DỮ LIỆU, KHÔNG PHẢI HTML.
 *    Không nhận thẻ trong giá trị. Cần in đậm một phần thì tách chuỗi ra. Cho HTML vào từ
 *    điển là mở một cửa XSS mà vài tháng sau không ai còn nhớ để đóng.
 */
(function () {
  "use strict";

  // GOC là từ điển ĐỦ key (rút từ mã), DU_PHONG là ngôn ngữ cho người chưa chọn gì và trình
  // duyệt cũng không khớp từ điển nào. Hai vai khác nhau nên hai hằng, đừng gộp.
  var GOC = "vi";
  var DU_PHONG = "en";
  var KHOA_LUU = "javis.ui_lang";
  var _lang = DU_PHONG;
  var _tu = {};        // ngôn ngữ đang chọn
  var _en = {};        // tiếng Anh, nấc suy biến đầu (rỗng khi đang chọn vi: không cần)
  var _goc = {};       // vi, luôn nạp, nấc suy biến cuối
  var _san_sang = false;
  var _da_chon = false;   // true = ngôn ngữ do người dùng chọn, không phải đoán từ trình duyệt
  var _luot = 0;          // init() gọi chồng nhau thì chỉ lượt MỚI NHẤT được ghi kết quả
  var _cache = {};        // mã -> Promise<từ điển | null>, để dò trình duyệt không tải hai lần

  function _doc_luu() {
    try { return localStorage.getItem(KHOA_LUU) || ""; } catch (e) { return ""; }
  }
  function _ghi_luu(ma) {
    try { localStorage.setItem(KHOA_LUU, ma); } catch (e) { /* chế độ riêng tư */ }
  }

  /* Tra một key. `bien` là object thay chỗ {ten}.
   *
   * `count` được đối xử riêng: ngôn ngữ có chia số nhiều (tiếng Anh) khai `key.one` và
   * `key.other`, ngôn ngữ không chia (tiếng Việt) chỉ khai `key.other`. Cố ý KHÔNG kéo cả
   * ICU MessageFormat vào cho đúng một việc này. */
  function t(key, bien) {
    var k = String(key || "");
    var val = null;
    if (bien && typeof bien.count === "number") {
      var hau = bien.count === 1 ? ".one" : ".other";
      val = _tu[k + hau];
      if (val == null) val = _en[k + hau];
      if (val == null) val = _goc[k + hau];
      if (val == null) val = _tu[k + ".other"];
      if (val == null) val = _en[k + ".other"];
      if (val == null) val = _goc[k + ".other"];
    }
    if (val == null) val = _tu[k];
    if (val == null) val = _en[k];
    if (val == null) val = _goc[k];
    if (val == null) return k;   // chỉ tới đây khi CẢ vi.json cũng thiếu key - đó là lỗi thật
    return String(val).replace(/\{(\w+)\}/g, function (m, ten) {
      return (bien && bien[ten] != null) ? String(bien[ten]) : m;
    });
  }

  /* Quét DOM tĩnh trong index.html. Các thuộc tính, đủ cho mọi chỗ chữ hiện ra:
   *   data-i18n        -> nội dung chữ
   *   data-i18n-title  -> tooltip
   *   data-i18n-aria   -> nhãn cho trình đọc màn hình
   *   data-i18n-ph     -> placeholder của ô nhập
 *   data-i18n-empty  -> data-empty-hint, câu CSS vẽ khi khung còn trống
   * Cố ý dùng textContent chứ không innerHTML: xem luật 3 ở đầu file. */
  function applyDom(goc) {
    var root = goc || document;
    // t() trả về CHÍNH cái khoá khi cả từ điển gốc cũng thiếu nó. Lúc đó ĐỪNG ghi đè: chữ
    // tiếng Việt có sẵn trong HTML còn đọc được, còn ghi đè là màn hình đầy `bar.input_ph`.
    // Ca này có thật chứ không phải phòng hờ: từ điển cũ bị cache qua bản cập nhật (0.52.1).
    var tra = function (el, attr) {
      var v = t(el.getAttribute(attr));
      return v === el.getAttribute(attr) ? null : v;
    };
    root.querySelectorAll("[data-i18n]").forEach(function (el) {
      var v = tra(el, "data-i18n");
      if (v !== null) el.textContent = v;
    });
    root.querySelectorAll("[data-i18n-title]").forEach(function (el) {
      var v = tra(el, "data-i18n-title");
      if (v !== null) el.setAttribute("title", v);
    });
    root.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      var v = tra(el, "data-i18n-aria");
      if (v !== null) el.setAttribute("aria-label", v);
    });
    root.querySelectorAll("[data-i18n-ph]").forEach(function (el) {
      var v = tra(el, "data-i18n-ph");
      if (v !== null) el.setAttribute("placeholder", v);
    });
    // Câu hiện khi khung còn TRỐNG, do CSS vẽ bằng `content: attr(data-empty-hint)`.
    root.querySelectorAll("[data-i18n-empty]").forEach(function (el) {
      var v = tra(el, "data-i18n-empty");
      if (v !== null) el.setAttribute("data-empty-hint", v);
    });
  }

  /* Tải một từ điển. Trả `null` khi KHÔNG có file (404, mất mạng), để phần dò trình duyệt
   * phân biệt được "ngôn ngữ này chưa có bản dịch" với "từ điển rỗng". */
  function _thu(ma) {
    if (!/^[a-z]{2,3}$/.test(String(ma || ""))) return Promise.resolve(null);
    if (_cache[ma]) return _cache[ma];
    // cache: "no-cache" = LUÔN hỏi lại server (304 nếu chưa đổi, rẻ). URL này không có `?v=`
    // nên thiếu nó là trình duyệt cache theo heuristic và giữ từ điển CŨ qua cả bản cập nhật -
    // code mới gọi khoá mới, từ điển cũ không có, cả trang in nguyên mã khoá kiểu
    // `models.st_connected` (khách báo 2026-08-30, bản 0.52.1).
    var p = fetch("/static/i18n/" + ma + ".json", { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
    // Hỏng thì bỏ khỏi cache: lần sau (mạng đã về) còn được thử lại.
    _cache[ma] = p.then(function (d) { if (!d) delete _cache[ma]; return d; });
    return _cache[ma];
  }
  function _tai(ma) {
    return _thu(ma).then(function (d) { return d || {}; });
  }

  /* Mã ngôn ngữ trình duyệt, đã rút về mã gọn ("en-US" -> "en"), giữ thứ tự ưu tiên. */
  function _ngon_ngu_trinh_duyet() {
    var ds = [];
    try {
      var nav = (typeof navigator !== "undefined") ? navigator : null;
      var goc = (nav && (nav.languages && nav.languages.length ? nav.languages : [nav.language])) || [];
      for (var i = 0; i < goc.length; i++) {
        var ma = String(goc[i] || "").toLowerCase().split(/[-_]/)[0];
        if (ma && ds.indexOf(ma) < 0) ds.push(ma);
      }
    } catch (e) { /* trình duyệt lạ: coi như không biết */ }
    return ds;
  }

  /* Ngôn ngữ đầu tiên trong danh sách trình duyệt CÓ từ điển. Không cái nào có thì DU_PHONG.
   * Không khai danh sách ngôn ngữ ở client: hỏi thẳng file, thêm `xx.json` là tự được nhận. */
  function _doan_tu_trinh_duyet() {
    var ds = _ngon_ngu_trinh_duyet();
    function thu(i) {
      if (i >= ds.length) return Promise.resolve(DU_PHONG);
      if (ds[i] === GOC || ds[i] === DU_PHONG) return Promise.resolve(ds[i]);
      return _thu(ds[i]).then(function (d) { return d ? ds[i] : thu(i + 1); });
    }
    return thu(0);
  }

  /* Nạp từ điển. Gọi MỘT lần lúc khởi động, TRƯỚC khi vẽ.
   *
   * Luôn nạp `vi` kể cả khi đang chọn ngôn ngữ khác: nó là lưới an toàn của luật suy biến, và
   * không có nó thì một key thiếu sẽ hiện ra màn hình dưới dạng chuỗi kỹ thuật. Nạp thêm `en`
   * khi đang chọn một thứ tiếng thứ ba (nấc suy biến giữa). */
  function init(ma) {
    var luot = ++_luot;
    var luu = ma || _doc_luu();
    _da_chon = !!luu;
    var chon = luu ? Promise.resolve(luu) : _doan_tu_trinh_duyet();
    return chon.then(function (lang) {
      var cho = [_tai(GOC), lang !== GOC ? _tai(DU_PHONG) : Promise.resolve({})];
      if (lang !== GOC && lang !== DU_PHONG) cho.push(_tai(lang));
      return Promise.all(cho).then(function (kq) { return [lang, kq]; });
    }).then(function (x) {
      if (luot !== _luot) return _lang;   // đã có lượt init mới hơn, đừng ghi đè nó
      var lang = x[0], kq = x[1];
      _lang = lang;
      _goc = kq[0] || {};
      _en = kq[1] || {};
      _tu = (lang === GOC) ? _goc : (lang === DU_PHONG ? _en : (kq[2] || {}));
      _san_sang = true;
      try { document.documentElement.setAttribute("lang", _lang); } catch (e) { /* noop */ }
      applyDom();
      // Báo cho phần còn lại của dashboard biết từ điển đã về. Alpine không theo dõi được
      // một object thuần, nên nơi nào vẽ nhãn từ `t()` phải nghe sự kiện này rồi vẽ lại.
      try {
        window.dispatchEvent(new CustomEvent("javis:i18n", { detail: { lang: _lang } }));
      } catch (e) { /* trình duyệt quá cũ - giao diện vẫn dùng được, chỉ là không tự vẽ lại */ }
      return _lang;
    });
  }

  function setLang(ma) {
    if (!ma) return Promise.resolve(_lang);
    _ghi_luu(ma);
    // Chọn ĐÚNG ngôn ngữ đang đoán theo trình duyệt vẫn là một lựa chọn: ghi lại để lần sau
    // không đoán nữa, nhưng khỏi tải lại từ điển.
    if (ma === _lang && _san_sang) { _da_chon = true; return Promise.resolve(_lang); }
    return init(ma);
  }

  // Nhãn hiển thị cho tên NHÓM / DANH MỤC do DỮ LIỆU mang tới (kho Kết nối, Javis Store).
  // Giá trị gốc là tiếng Việt và đang làm KHOÁ lọc (`data-cat`, `data-kho-nhom`), nên không
  // đổi ở nguồn - chỉ đổi lúc VẼ. Cách tra: tìm khoá `cat.*` nào có bản tiếng Việt đúng bằng
  // tên gốc rồi lấy bản dịch của khoá đó, nên mã này không phải viết chuỗi Việt nào. Tên lạ
  // (gói cộng đồng tự đặt) thì giữ nguyên. Mã máy `ban-hang` của kho là ngoại lệ ASCII.
  var NHOM_MA_MAY = { "ban-hang": "cat.ban_hang" };
  function catLabel(raw) {
    var goc = String(raw == null ? "" : raw).trim();
    if (!goc) return "";
    var khoa = NHOM_MA_MAY[goc] || "";
    if (!khoa) {
      for (var k in _goc) {
        if (k.indexOf("cat.") === 0 && _goc[k] === goc) { khoa = k; break; }
      }
    }
    if (!khoa) return goc;
    var v = t(khoa);
    return v === khoa ? goc : v;
  }

  window.JavisI18n = {
    t: t,
    catLabel: catLabel,
    init: init,
    setLang: setLang,
    applyDom: applyDom,
    lang: function () { return _lang; },
    ready: function () { return _san_sang; },
    /* true = máy này đã CHỌN ngôn ngữ (lưu trong localStorage), false = đang đoán theo trình
     * duyệt. console.js dựa vào đây để quyết định có áp `ui_lang` của server hay không. */
    daChon: function () { return _da_chon; },
    /* Locale cho toLocaleString/toLocaleDateString. Dashboard KHÔNG được viết cứng "vi-VN"
     * nữa - đó đúng là kiểu rải rác đã làm việc thêm ngôn ngữ trở nên đắt. */
    locale: function () { return t("_meta.number_locale") || "vi-VN"; },
  };
  // Bí danh ngắn: `t("nav.viec")` đọc dễ hơn `JavisI18n.t("nav.viec")` ở chỗ dựng HTML.
  window.t = t;

  // Nạp NGAY, không chờ ai gọi. Script này đứng đầu danh sách trong index.html nên nó khởi
  // động sớm nhất có thể; các script sau vẫn chạy ngay (fetch là bất đồng bộ) và tự vẽ lại
  // khi nghe "javis:i18n".
  init();
})();
