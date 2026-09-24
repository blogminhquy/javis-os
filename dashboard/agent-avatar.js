/* Avatar trợ lý dùng cùng thư viện hình/màu VÀ cùng bộ chỉnh với linh vật (0.64.39), không đổi cấu hình pet. */
(function () {
  "use strict";
  const t = (k) => window.t ? window.t(k) : k;
  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const catalog = () => ({ shapes: window.JavisPet.shapes(), palettes: window.JavisPet.palettes() });
  // Dạng cổ điển của phép "có thuộc tính riêng": bản rút gọn trên Object cần Safari 15.4+, mà
  // iPhone cũ vẫn vào dashboard (xem các chốt WebKit khác trong repo). Vẫn chặn "__proto__".
  const co = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  // toneOf trả null khi tên bảng màu lạ (dashboard/pet.js), nên mọi chỗ đọc [0] phải chốt:
  // một `data-palette` lạc sẽ ném ngay giữa vòng vẽ lại theo chủ đề và giết nốt phần còn lại.
  const tone = (p) => (window.JavisPet.toneOf(p) || ["transparent"])[0];
  // Mã màu "#rrggbb" chữ thường, sai thì "". Tự khai ở đây chứ không mượn JavisPet.hex: file
  // này còn được nạp với một JavisPet giả trong test và ở trang cũ chưa có hàm đó.
  const hex = (v) => /^#[0-9a-f]{6}$/i.test(String(v || "")) ? String(v).toLowerCase() : "";
  const MAT = ["den", "trang"];
  // Nhân dạng đã lọc về thư viện. Khoá mới của 0.64.39 (mã màu tự chọn, màu mắt, cỡ mắt) chỉ
  // có mặt khi đã được chọn: trợ lý cũ vẫn đúng dạng {shape, palette} và mắt suy tự động.
  function of(agent) {
    const {shapes, palettes} = catalog(), a = (agent && agent.avatar) || {};
    const seed = hat(agent);
    const tuChon = a.palette === "custom" && hex(a.color);
    const out = {shape: co(shapes, a.shape) ? a.shape : Object.keys(shapes)[seed % Object.keys(shapes).length],
      palette: co(palettes, a.palette) || tuChon ? a.palette : Object.keys(palettes)[seed % Object.keys(palettes).length]};
    if (tuChon) out.color = hex(a.color);
    if (MAT.includes(a.eye)) out.eye = a.eye;
    else if (a.eye === "custom" && hex(a.eyeColor)) { out.eye = "custom"; out.eyeColor = hex(a.eyeColor); }
    const k = Number(a.eyeSize);
    if (isFinite(k) && k >= 0.8 && k <= 1.5 && k !== 1) out.eyeSize = Math.round(k * 100) / 100;
    return out;
  }
  // Hạt giống theo SLUG: cùng một trợ lý thì mọi chỗ vẽ nó ra cùng một con số, và con số đó
  // sống qua mỗi lần vẽ lại. Dùng cho cả hình/màu mặc định lẫn nhịp chớp mắt.
  function hat(agent) {
    return Array.from((agent && agent.slug) || "").reduce((n, c) => n + c.codePointAt(0), 0);
  }
  // NHỊP CHỚP MẮT riêng cho từng trợ lý. Trước đây mọi avatar dùng chung `animation: aa-blink
  // 6s` nên cả danh sách chớp mắt ĐỒNG LOẠT, nhìn ra ngay là mấy bản sao của một cái máy chứ
  // không phải mấy nhân vật khác nhau. Lệch pha bằng hạt giống theo slug chứ không bằng
  // Math.random(): ngẫu nhiên thật thì mỗi lần vẽ lại danh sách là mỗi con đổi nhịp, và hai
  // chỗ cùng vẽ một trợ lý (hàng danh sách + đầu khung chat) lại chớp lệch nhau.
  function nhip(agent) {
    const h = hat(agent);
    return { tre: -((h * 7) % 61) / 10, lau: 5 + ((h * 13) % 34) / 10 };   // trễ 0-6s, chu kỳ 5-8,4s
  }
  // Độ chói tương đối (WCAG) của một mã màu, để chọn mắt đọc ra được trên thân.
  function doChoi(h6) {
    if (!hex(h6)) return 0.5;
    return h6.slice(1).match(/../g).map(x => {
      const v = parseInt(x, 16) / 255;
      return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }).reduce((n, v, i) => n + v * [0.2126, 0.7152, 0.0722][i], 0);
  }
  // Mắt trắng hay đen: chủ dự án muốn NGẪU NHIÊN giữa hai màu này (0.64.39). Chỉ chặn đúng
  // hai trường hợp mất mặt: mắt trắng trên thân rất sáng (ngọc trai, nắng) và mắt đen trên
  // thân rất tối, vì ở đó con mắt biến mất và avatar thành một cục màu trống trơn.
  function matNgauNhien(palette, color) {
    const l = doChoi((window.JavisPet.toneOf(palette, color) || ["#888888"])[0]);
    const m = MAT[Math.floor(Math.random() * MAT.length)];
    if (m === "trang" && l > 0.55) return "den";
    if (m === "den" && l < 0.06) return "trang";
    return m;
  }
  // Mắt SUY TỰ ĐỘNG (trợ lý cũ chưa chọn): đúng luật của chân dung linh vật, để ô chọn đánh
  // dấu đúng màu đang hiện chứ không để trống.
  const matTuDong = (a) => doChoi((window.JavisPet.toneOf(a.palette, a.color) || ["#888888"])[0]) > 0.179 ? "den" : "trang";
  // Ngẫu nhiên: hình, một trong các bảng màu CÓ SẴN (không bốc màu tự chọn), mắt trắng/đen.
  function random() {
    const {shapes, palettes} = catalog();
    const pick = o => Object.keys(o)[Math.floor(Math.random() * Object.keys(o).length)];
    const palette = pick(palettes);
    return {shape: pick(shapes), palette, eye: matNgauNhien(palette)};
  }
  // Tuỳ chọn chân dung từ nhân dạng: chỉ đưa khoá ĐÃ CÓ, trợ lý cũ gọi previewSvg y như trước.
  function anh(a) {
    const o = {};
    if (a.color) o.mau = a.color;
    if (a.eye) o.mat = a.eye;
    if (a.eyeColor) o.mauMat = a.eyeColor;
    if (a.eyeSize) o.coMat = a.eyeSize;
    return o;
  }
  // Rút gọn bản đầy đủ của bộ chỉnh (luôn mang đủ color/eyeColor/eyeSize) về đúng thứ cần lưu.
  function gon(v) {
    const out = {shape: v.shape, palette: v.palette, eye: v.eye};
    if (v.palette === "custom") out.color = v.color;
    if (v.eye === "custom") out.eyeColor = v.eyeColor;
    if (v.eyeSize && Number(v.eyeSize) !== 1) out.eyeSize = Number(v.eyeSize);
    return out;
  }
  // Các trường form cho POST /agents (server/agent_avatar.py đọc lại đúng các tên này).
  function formFields(v) {
    const f = {avatar_shape: v.shape, avatar_palette: v.palette, avatar_eye_size: String(v.eyeSize || 1)};
    if (v.palette === "custom") f.avatar_color = v.color;
    if (v.eye) f.avatar_eye = v.eye;
    if (v.eye === "custom") f.avatar_eye_color = v.eyeColor;
    return f;
  }
  // `opts.liec`: đổi hướng liếc. "trai_duoi" = sang trái và hơi xuống, dùng cho ô xem thử lớn
  // trong cài đặt trợ lý (chủ dự án chốt 15/09); bỏ trống = chéo lên phải như con pet.
  const LIEC = { trai_duoi: { liecX: -16, liecY: 9 } };
  function html(agent, size = 40, state = "idle", opts) {
    const a = of(agent);
    const o = opts || {};
    const svg = svgOf(a, o);
    const n = nhip(agent);
    // Tâm CHỚP MẮT phải đi theo mắt: co theo trục dọc quanh một điểm nằm lệch chỗ thì con mắt
    // vừa nhắm vừa trượt đi. Toạ độ tính trong hệ viewBox của chân dung (tâm 160/160).
    const l = LIEC[o.liec] || { liecX: 16, liecY: -12 };
    // esc() cả shape/palette: of() đã lọc về thư viện, nhưng html() là hàm CÔNG KHAI của
    // window.JavisAvatar nên chỗ gọi khác có thể ném thẳng chuỗi lạ vào.
    const them = (k, v) => v ? ' data-' + k + '="' + esc(v) + '"' : "";
    return '<span class="agent-avatar" data-shape="' + esc(a.shape) + '" data-palette="' + esc(a.palette) + '"' +
      them("color", a.color) + them("eye", a.eye) + them("eye-color", a.eyeColor) + them("eye-size", a.eyeSize) +
      ' data-state="' + esc(state) + '" style="--avatar-size:' + Number(size) + 'px' +
      ';--aa-blink-delay:' + n.tre + 's;--aa-blink-dur:' + n.lau + 's' +
      ';--aa-eye-x:' + (160 + l.liecX) + 'px;--aa-eye-y:' + (160 + l.liecY) + 'px">' + svg + '</span>';
  }
  function svgOf(a, opts) {
    const o = opts || {};
    return window.JavisPet.previewSvg(a.shape, a.palette, Object.assign({}, LIEC[o.liec] || {}, anh(a)))
      .replace('<ellipse', '<g class="aa-gaze"><g class="aa-eyes"><ellipse')
      .replace('</svg>', '</g></g></svg>');
  }
  // Bộ chọn avatar trong cài đặt trợ lý. Từ 0.64.39 nó là ĐÚNG bộ chỉnh của trang Linh vật
  // (JavisPet.editorHtml/editorBind): hình dáng, bảng màu + màu tự chọn, màu mắt trắng/đen/tự
  // chọn, thanh trượt cỡ mắt. Chỉ bỏ thanh trượt cỡ thân, vì cỡ avatar do chỗ vẽ quyết.
  function picker(host, initial, onChange) {
    let value = initial || random();
    // Trợ lý cũ chưa chọn màu mắt thì đang hiện mắt suy tự động: đánh dấu đúng màu đó.
    if (!value.eye) value = {...value, eye: matTuDong(value)};
    const P = window.JavisPet;
    const veXemThu = () => {
      const o = host.querySelector('.aa-preview');
      if (o) o.innerHTML = html({avatar:value}, 100, "idle", {liec:"trai_duoi"});
    };
    function draw(moSan) {
      host.innerHTML = '<div class="aa-preview">' + html({avatar:value}, 100, "idle", {liec:"trai_duoi"}) + '</div>' +
        '<details class="aa-options"' + (moSan ? ' open' : '') + '><summary>' + esc(t("ws.avatar_change")) + '</summary>' +
        '<div class="aa-editor pet-editor">' + (P.editorHtml ? P.editorHtml(value, {}) : '') + '</div>' +
        '<button type="button" class="ws-btn" data-random>' + esc(t("ws.avatar_random")) + '</button></details>';
      if (P.editorBind) P.editorBind(host.querySelector('.aa-editor'), value, (patch, tam, look) => {
        value = gon(look || {...value, ...patch});
        veXemThu(); onChange({...value});
      }, {});
      host.querySelector('[data-random]').onclick = () => {
        value = random();
        draw(true); host.querySelector('[data-random]').focus(); onChange({...value});
      };
    }
    draw(false); onChange({...value});
  }
  document.addEventListener('pointermove', e => {
    const preview = e.target.closest && e.target.closest('.aa-preview');
    if (!preview || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const r = preview.getBoundingClientRect(), gaze = preview.querySelector('.aa-gaze');
    if (gaze) gaze.style.transform = 'translate('+((e.clientX-r.left)/r.width*16-8)+'px,'+((e.clientY-r.top)/r.height*12-6)+'px)';
  });
  window.addEventListener('javis-theme-change', () => {
    // Vẽ lại theo tông mới nhưng GIỮ hướng liếc của từng ô: ô xem thử lớn (.aa-preview) liếc
    // trái-xuống, các avatar còn lại liếc chéo lên phải. Nhận ra bằng chính chỗ nó đang đứng,
    // khỏi phải nuôi thêm một thuộc tính chỉ để nhớ điều đó.
    document.querySelectorAll('.agent-avatar').forEach(el => {
      const trai = el.closest && el.closest('.aa-preview');
      const d = el.dataset;
      const a = {shape:d.shape, palette:d.palette};
      if (d.color) a.color = d.color;
      if (d.eye) a.eye = d.eye;
      if (d.eyeColor) a.eyeColor = d.eyeColor;
      if (d.eyeSize) a.eyeSize = Number(d.eyeSize);
      el.innerHTML = svgOf(a, trai ? {liec:'trai_duoi'} : {});
    });
    document.querySelectorAll('.aa-colors [data-palette]').forEach(el => { el.style.setProperty('--swatch', tone(el.dataset.palette)); });
  });
  window.JavisAvatar = {of, random, html, picker, formFields};
})();
