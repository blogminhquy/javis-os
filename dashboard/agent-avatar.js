/* Avatar trợ lý dùng cùng thư viện hình/màu với linh vật, không đổi cấu hình pet. */
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
  function of(agent) {
    const {shapes, palettes} = catalog(), a = (agent && agent.avatar) || {};
    const seed = hat(agent);
    return {shape: co(shapes, a.shape) ? a.shape : Object.keys(shapes)[seed % Object.keys(shapes).length],
      palette: co(palettes, a.palette) ? a.palette : Object.keys(palettes)[seed % Object.keys(palettes).length]};
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
  function random() {
    const {shapes, palettes} = catalog();
    const pick = o => Object.keys(o)[Math.floor(Math.random() * Object.keys(o).length)];
    return {shape: pick(shapes), palette: pick(palettes)};
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
    return '<span class="agent-avatar" data-shape="' + esc(a.shape) + '" data-palette="' + esc(a.palette) +
      '" data-state="' + esc(state) + '" style="--avatar-size:' + Number(size) + 'px' +
      ';--aa-blink-delay:' + n.tre + 's;--aa-blink-dur:' + n.lau + 's' +
      ';--aa-eye-x:' + (160 + l.liecX) + 'px;--aa-eye-y:' + (160 + l.liecY) + 'px">' + svg + '</span>';
  }
  function svgOf(a, opts) {
    const o = opts || {};
    return window.JavisPet.previewSvg(a.shape, a.palette, LIEC[o.liec] || {})
      .replace('<ellipse', '<g class="aa-gaze"><g class="aa-eyes"><ellipse')
      .replace('</svg>', '</g></g></svg>');
  }
  function picker(host, initial, onChange) {
    let value = initial || random();
    const {shapes, palettes} = catalog();
    function draw() {
      host.innerHTML = '<div class="aa-preview">' + html({avatar:value}, 100, "idle", {liec:"trai_duoi"}) + '</div>' +
        '<details class="aa-options"><summary>' + esc(t("ws.avatar_change")) + '</summary>' +
        '<div class="aa-shapes" role="group" aria-label="' + esc(t("ws.avatar_shape")) + '">' +
        Object.keys(shapes).map(s => '<button type="button" data-shape="'+s+'" aria-label="'+esc(t(shapes[s].key))+'" aria-pressed="'+(s===value.shape)+'">'+html({avatar:{shape:s,palette:value.palette}},36)+'</button>').join('') + '</div>' +
        '<div class="aa-colors" role="group" aria-label="'+esc(t("ws.avatar_color"))+'">'+Object.keys(palettes).map(p =>
          '<button type="button" data-palette="'+p+'" aria-label="'+esc(t(palettes[p].key))+'" aria-pressed="'+(p===value.palette)+'" style="--swatch:'+tone(p)+'"></button>').join('')+'</div>' +
        '<button type="button" class="ws-btn" data-random>'+esc(t("ws.avatar_random"))+'</button></details>';
      host.querySelectorAll('[data-shape], [data-palette], [data-random]').forEach(b => b.onclick = () => {
        value = b.hasAttribute('data-random') ? random() : {...value, ...(b.dataset.shape ? {shape:b.dataset.shape} : {palette:b.dataset.palette})};
        const focus = b.hasAttribute('data-random') ? '[data-random]' : b.dataset.shape ? '[data-shape="'+b.dataset.shape+'"]' : '[data-palette="'+b.dataset.palette+'"]';
        draw(); host.querySelector('details').open = true; host.querySelector(focus).focus(); onChange({...value});
      });
    }
    draw(); onChange({...value});
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
      el.innerHTML = svgOf({shape:el.dataset.shape,palette:el.dataset.palette}, trai ? {liec:'trai_duoi'} : {});
    });
    document.querySelectorAll('.aa-colors [data-palette]').forEach(el => { el.style.setProperty('--swatch', tone(el.dataset.palette)); });
  });
  window.JavisAvatar = {of, random, html, picker};
})();
