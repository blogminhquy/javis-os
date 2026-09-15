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
    const seed = Array.from((agent && agent.slug) || "").reduce((n, c) => n + c.codePointAt(0), 0);
    return {shape: co(shapes, a.shape) ? a.shape : Object.keys(shapes)[seed % Object.keys(shapes).length],
      palette: co(palettes, a.palette) ? a.palette : Object.keys(palettes)[seed % Object.keys(palettes).length]};
  }
  function random() {
    const {shapes, palettes} = catalog();
    const pick = o => Object.keys(o)[Math.floor(Math.random() * Object.keys(o).length)];
    return {shape: pick(shapes), palette: pick(palettes)};
  }
  function html(agent, size = 40, state = "idle") {
    const a = of(agent);
    const svg = svgOf(a);
    // esc() cả shape/palette: of() đã lọc về thư viện, nhưng html() là hàm CÔNG KHAI của
    // window.JavisAvatar nên chỗ gọi khác có thể ném thẳng chuỗi lạ vào.
    return '<span class="agent-avatar" data-shape="' + esc(a.shape) + '" data-palette="' + esc(a.palette) + '" data-state="' + esc(state) + '" style="--avatar-size:' + Number(size) + 'px">' + svg + '</span>';
  }
  function svgOf(a) {
    return window.JavisPet.previewSvg(a.shape, a.palette)
      .replace('<ellipse', '<g class="aa-gaze"><g class="aa-eyes"><ellipse')
      .replace('</svg>', '</g></g></svg>');
  }
  function picker(host, initial, onChange) {
    let value = initial || random();
    const {shapes, palettes} = catalog();
    function draw() {
      host.innerHTML = '<div class="aa-preview">' + html({avatar:value}, 100) + '</div>' +
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
    document.querySelectorAll('.agent-avatar').forEach(el => { el.innerHTML = svgOf({shape:el.dataset.shape,palette:el.dataset.palette}); });
    document.querySelectorAll('.aa-colors [data-palette]').forEach(el => { el.style.setProperty('--swatch', tone(el.dataset.palette)); });
  });
  window.JavisAvatar = {of, random, html, picker};
})();
