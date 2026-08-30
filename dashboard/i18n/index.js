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
 * 2. SUY BIẾN <ngôn ngữ đã chọn> -> vi -> chính key.
 *    `vi.json` đủ 100% key theo định nghĩa vì nó được rút ra từ mã đang chạy. Nhờ vậy một
 *    bản dịch làm dở KHÔNG bao giờ để lại ô chữ trống hay một key trần trên màn hình; chỗ
 *    chưa dịch chỉ đơn giản là còn tiếng Việt.
 *
 * 3. TỪ ĐIỂN LÀ DỮ LIỆU, KHÔNG PHẢI HTML.
 *    Không nhận thẻ trong giá trị. Cần in đậm một phần thì tách chuỗi ra. Cho HTML vào từ
 *    điển là mở một cửa XSS mà vài tháng sau không ai còn nhớ để đóng.
 */
(function () {
  "use strict";

  var MAC_DINH = "vi";
  var KHOA_LUU = "javis.ui_lang";
  var _lang = MAC_DINH;
  var _tu = {};        // ngôn ngữ đang chọn
  var _goc = {};       // vi, luôn nạp, dùng để suy biến
  var _san_sang = false;

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
      if (val == null) val = _goc[k + hau];
      if (val == null) val = _tu[k + ".other"];
      if (val == null) val = _goc[k + ".other"];
    }
    if (val == null) val = _tu[k];
    if (val == null) val = _goc[k];
    if (val == null) return k;   // chỉ tới đây khi CẢ vi.json cũng thiếu key - đó là lỗi thật
    return String(val).replace(/\{(\w+)\}/g, function (m, ten) {
      return (bien && bien[ten] != null) ? String(bien[ten]) : m;
    });
  }

  /* Quét DOM tĩnh trong index.html. Ba thuộc tính, đủ cho mọi chỗ chữ hiện ra:
   *   data-i18n        -> nội dung chữ
   *   data-i18n-title  -> tooltip
   *   data-i18n-aria   -> nhãn cho trình đọc màn hình
   *   data-i18n-ph     -> placeholder của ô nhập
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
  }

  function _tai(ma) {
    // cache: "no-cache" = LUÔN hỏi lại server (304 nếu chưa đổi, rẻ). URL này không có `?v=`
    // nên thiếu nó là trình duyệt cache theo heuristic và giữ từ điển CŨ qua cả bản cập nhật -
    // code mới gọi khoá mới, từ điển cũ không có, cả trang in nguyên mã khoá kiểu
    // `models.st_connected` (khách báo 2026-08-30, bản 0.52.1).
    return fetch("/static/i18n/" + ma + ".json", { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .catch(function () { return {}; });
  }

  /* Nạp từ điển. Gọi MỘT lần lúc khởi động, TRƯỚC khi vẽ.
   *
   * Luôn nạp `vi` kể cả khi đang chọn ngôn ngữ khác: nó là lưới an toàn của luật suy biến, và
   * không có nó thì một key thiếu sẽ hiện ra màn hình dưới dạng chuỗi kỹ thuật. */
  function init(ma) {
    _lang = ma || _doc_luu() || MAC_DINH;
    var cho = [_tai(MAC_DINH)];
    if (_lang !== MAC_DINH) cho.push(_tai(_lang));
    return Promise.all(cho).then(function (kq) {
      _goc = kq[0] || {};
      _tu = (_lang === MAC_DINH) ? _goc : (kq[1] || {});
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
    if (!ma || ma === _lang) return Promise.resolve(_lang);
    _ghi_luu(ma);
    return init(ma);
  }

  window.JavisI18n = {
    t: t,
    init: init,
    setLang: setLang,
    applyDom: applyDom,
    lang: function () { return _lang; },
    ready: function () { return _san_sang; },
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
