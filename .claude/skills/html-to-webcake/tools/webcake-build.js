#!/usr/bin/env node
/*
 * webcake-build.js  (v3 - layout engine + theme tokens + do text theo bang do rong ky tu)
 * Sinh page_source Webcake tu "spec" roi xuat .pke. Webcake = canvas TUYET DOI (mobile 420 / desktop 960).
 *
 *   node webcake-build.js spec.json out.pke [--check]
 *
 * Bo cuc: moi phan tu duoc dat tuyet doi trong section (flat children). "Nhieu cot" = dat left khac nhau
 * cung top (desktop), con mobile thi xep doc. Card/badge/window dung <rectangle> lam nen + text de len.
 *
 * KIND ho tro:
 *   heading | text | image | button | form | spacer
 *   badge          -> vien thuoc (tu co chu / tu wrap khi text dai)
 *   card           -> hop nen bo goc + (icon) + tieu de + mo ta; ho tro iconTop, accent (soc mau canh trai)
 *   window         -> khung cua so chat
 *   divider        -> duong ke ngang mong
 *   progress       -> thanh tien trinh (track + fill theo value 0..1 + label)
 *   priceTable     -> bang gia: label trai / gia phai, hang total, dong gach gia + gia hom nay
 *   testimonial    -> the danh gia (sao + quote + tac gia); testimonialRow xep ngang
 *   guarantee      -> khoi cam ket (icon lon trai + tieu de + than)
 *   ctaBlock       -> (mui ten) + nut + dong phu, thanh 1 khoi
 *   iconRow        -> hang icon + chu ngan
 *   hero           -> 2 cot desktop (chu 1 ben, media 1 ben, can giua doc), mobile xep doc
 *   row {gap,valign,cols:[{w,items}]}    -> hang nhieu cot tong quat
 *   cardsRow {gap,cards:[...]}           -> duong tat: 1 hang cac card deu nhau
 *
 * THEME TOKENS: spec.theme = { colors:{ten:"rgba(...)"} , text/heading/badge/card/button/... defaults,
 *   textMaxWidth, headingMaxWidth, cardMaxWidth }. Trong moi truong string: "$ten" (nguyen chuoi) hoac
 *   "${ten}" (nhung trong chuoi dai/html) se duoc thay bang theme.colors.ten. Khong co ten do -> giu nguyen.
 */
'use strict';
const fs = require('fs');
const { encodeMsgpack } = require('./webcake-pke.js');

const DESK_W = 960, MOB_W = 420;
const PADX_D = 40, PADX_M = 16;
const LH = 1.5; // line-height mac dinh cua text-block Webcake

const ID = 'abcdefghijklmnopqrstuvwxyz0123456789';
function id(){ let s=''; for(let i=0;i<8;i++) s+=ID[Math.floor(Math.random()*ID.length)]; return s; }

/* ================= THEME ================= */
let THEME = null;
const THEME_BASE = {
  colors: {},
  textMaxWidth: 700,      // kho chu toi da cua text thuong (desktop) - chong dong qua dai kho doc
  headingMaxWidth: 800,
  cardMaxWidth: 800,      // card/priceTable/guarantee full-width se bo ve be rong nay va can giua
  text: {}, heading: {}, badge: {}, card: {}, button: {}, image: {}, window: {},
  testimonial: {}, priceTable: {}, guarantee: {}, progress: {}, divider: {}, ctaBlock: {}, iconRow: {}, hero: {}
};
function setTheme(t){
  THEME = JSON.parse(JSON.stringify(THEME_BASE));
  if (t) for (const k of Object.keys(t)){
    if (k === 'colors') Object.assign(THEME.colors, t.colors);
    else if (typeof t[k] === 'object' && THEME[k] && typeof THEME[k] === 'object') Object.assign(THEME[k], t[k]);
    else THEME[k] = t[k];
  }
  // resolve token ngay trong theme (vd card.bg = "$cardBg") - colors phai la literal
  for (const k of Object.keys(THEME)) if (k !== 'colors') THEME[k] = deepTok(THEME[k]);
}
function tok(s){
  if (typeof s !== 'string') return s;
  if (s[0] === '$' && s[1] !== '{'){
    const key = s.slice(1);
    if (THEME.colors[key] != null) return THEME.colors[key];
    return s; // khong phai token (vd "$50") -> giu nguyen
  }
  return s.replace(/\$\{([\w-]+)\}/g, (m, k) => THEME.colors[k] != null ? THEME.colors[k] : m);
}
function deepTok(v){
  if (typeof v === 'string') return tok(v);
  if (Array.isArray(v)) return v.map(deepTok);
  if (v && typeof v === 'object'){ const o = {}; for (const k of Object.keys(v)) o[k] = deepTok(v[k]); return o; }
  return v;
}
const KIND2THEME = { heading:'heading', text:'text', badge:'badge', card:'card', button:'button', image:'image',
  window:'window', testimonial:'testimonial', pricetable:'priceTable', guarantee:'guarantee', progress:'progress',
  divider:'divider', ctablock:'ctaBlock', iconrow:'iconRow', hero:'hero' };
function withDefaults(it){
  const key = KIND2THEME[(it.kind || '').toLowerCase()];
  if (!key || !THEME[key]) return it;
  const merged = Object.assign({}, THEME[key]);
  for (const k of Object.keys(it)) if (it[k] !== undefined) merged[k] = it[k]; // undefined khong duoc de mat default
  return merged;
}

/* ================= DO TEXT =================
 * Bang do rong TUNG KY TU cua Montserrat 400 (don vi em), DO THAT bang Chromium + font Montserrat
 * that (khong phai font du phong): getBoundingClientRect cua mot <span> chua dung 1 ky tu o 100px.
 * Hieu chuan lai 2026-08-13 tren 175 ky tu - ban truoc do lech toi 0.11em o mot so ky tu (% / ? ★ C X Y ư
 * va cap nhay), lam text tinh du/thieu ca mot dong. Emoji do duoc 1.248em (Noto Color Emoji) chu khong
 * phai 1.5 nhu ban cu uoc luong - do la nguon goc cua nhung khoi text bi cap thua ca dong tren mobile.
 */
const CHAR_W = {
  a:0.59,b:0.678,c:0.563,d:0.678,e:0.604,f:0.339,g:0.685,h:0.676,i:0.269,j:0.274,k:0.598,l:0.269,m:1.061,
  n:0.676,o:0.627,p:0.678,q:0.678,r:0.401,s:0.488,t:0.406,u:0.672,v:0.542,w:0.879,x:0.534,y:0.542,z:0.511,
  A:0.717,B:0.754,C:0.709,D:0.826,E:0.669,F:0.633,G:0.773,H:0.813,I:0.302,J:0.501,K:0.711,L:0.589,M:0.955,
  N:0.813,O:0.839,P:0.718,Q:0.839,R:0.723,S:0.615,T:0.574,U:0.792,V:0.698,W:1.111,X:0.656,Y:0.635,Z:0.651,
  '0':0.662,'1':0.361,'2':0.568,'3':0.564,'4':0.661,'5':0.566,'6':0.609,'7':0.589,'8':0.638,'9':0.609,
  'đ':0.678,'Đ':0.831,'ư':0.678,'Ư':0.797,'ơ':0.627,'Ơ':0.839,
  ' ':0.262,'.':0.212,',':0.212,';':0.212,':':0.212,'!':0.26,'?':0.567,'(':0.329,')':0.329,'%':0.829,
  '@':1.033,'#':0.696,'&':0.669,'*':0.386,'+':0.575,'-':0.382,'=':0.575,'/':0.335,'|':0.294,'<':0.575,
  '>':0.575,'_':0.5,'~':0.575,'^':0.576,'•':0.295,'★':0.897,'☆':0.897,'→':1,'←':1,'▼':0.99,'▲':0.99,
  '…':0.647,'°':0.419,"'":0.202,'"':0.373,'\\':0.273,'[':0.318,']':0.318,'{':0.334,'}':0.334,
  '“':0.382,'”':0.382,'‘':0.212,'’':0.212,'✕':0.838,'✓':0.838,'✔':0.838,'✗':0.838
};
const EMOJI_W = 1.25;   // do that: 1.248em (Noto Color Emoji), moi emoji mot o vuong nhu nhau
function chW(ch){
  const cp = ch.codePointAt(0);
  if (cp === 0x200D || cp === 0xFE0F || cp === 0xFE0E || cp === 0x20E3) return 0; // ZWJ / variation selector
  if (CHAR_W[ch] != null) return CHAR_W[ch];
  const base = ch.normalize('NFD')[0];                  // ky tu tieng Viet co dau -> chu goc cung width
  if (CHAR_W[base] != null) return CHAR_W[base];
  if (cp >= 0x1F000 || (cp >= 0x2600 && cp <= 0x27BF)) return EMOJI_W;  // emoji: ⚠ ✅ 🛡 📘
  if (cp >= 0x2190 && cp <= 0x25FF) return 1.0;         // mui ten / hinh hoc khac
  const lo = ch.toLowerCase();
  if (lo !== ch) return 0.75;
  return 0.62;
}
function stripHtml(html){
  return String(html == null ? '' : html).replace(/<br\s*\/?>/gi, '\n').replace(/<[^>]+>/g, '').replace(/&nbsp;/gi, ' ');
}
const BOLD_RATIO = 1.047;   // do that tren 52 chu cai: Montserrat 700 rong hon 400 trung binh 4,7%
function lineW(s, size, bold, ls){
  let w = 0, n = 0;
  for (const ch of String(s)){ w += chW(ch); n++; }
  return w * size * (bold ? BOLD_RATIO : 1) + (ls ? ls * n : 0);
}
/**
 * Chieu cao that cua mot khoi chu. `o` = { lh, ls }:
 *   lh - line-height (mac dinh 1.5 nhu text-block Webcake). Tieu de cua trang that hay dung ~1.1;
 *        khong theo thi tieu de bi doãng ra, nhin khac han ban goc.
 *   ls - letter-spacing tinh bang px (kicker viet hoa hay co .18em).
 * Hai gia tri nay duoc gui sang Webcake qua specials.custom_css, nen chieu cao PHAI tinh theo
 * chung, khong thi virtualHeight lech va chu bi cat o ban chay that.
 */
/**
 * Bo mot chuoi HTML inline thanh cac DOAN cung co chu / cung do dam.
 * Vi sao can: mot khoi chu that hay tron nhieu co ("1" to, chu thuong nho). Ban truoc do CA KHOI
 * theo co chu goc roi chi nhac chieu cao dong cuoi len - dem thieu so dong cua doan chu TO, nen
 * virtualHeight ngan hon thuc te va Webcake CAT mat may dong cuoi.
 */
function runsOf(html, baseSize, baseBold){
  const out = [];
  const stack = [{ size: baseSize, bold: baseBold }];
  const re = /<[^>]*>|[^<]+/g;
  let m;
  while ((m = re.exec(String(html == null ? '' : html))) !== null){
    const t = m[0];
    if (t[0] !== '<'){
      const top = stack[stack.length - 1];
      out.push({ text: t.replace(/&nbsp;/gi, ' '), size: top.size, bold: top.bold });
      continue;
    }
    if (/^<br/i.test(t)){ out.push({ br: true }); continue; }
    if (t[1] === '/'){ if (stack.length > 1) stack.pop(); continue; }
    if (/\/>\s*$/.test(t) || /^<(img|input|hr|meta|link)\b/i.test(t)) continue;
    const top = stack[stack.length - 1];
    let size = top.size, bold = top.bold;
    if (/^<(b|strong)\b/i.test(t)) bold = true;
    const st = /style\s*=\s*(['"])([\s\S]*?)\1/i.exec(t);
    if (st){
      const fs = /font-size:\s*([\d.]+)px/i.exec(st[2]);
      if (fs) size = parseFloat(fs[1]);
      const fw = /font-weight:\s*(bold|bolder|[1-9]00)/i.exec(st[2]);
      if (fw) bold = /bold|bolder|[6-9]00/i.test(fw[1]);
    }
    stack.push({ size, bold });
  }
  return out;
}

function textH(html, size, boxW0, bold, o){
  const lh = (o && o.lh) || LH, ls = (o && o.ls) || 0;
  const boxW = boxW0 * 0.985;   // bien an toan 1.5%: sat nut thi tinh du 1 dong (huong an toan)
  const runs = runsOf(html, size, !!bold);
  let total = 0, cur = 0, lineMax = 0;
  // Chieu cao mot dong = co chu LON NHAT tren dong do, nhung KHONG BAO GIO thap hon co chu goc
  // cua khoi: trinh duyet luon dat mot "strut" theo font-size cua chinh khoi tren moi dong. Bo
  // strut di thi mot dong chi co span 11px se bi tinh 11px trong khi that ra no cao 16px.
  const endLine = () => { total += Math.max(lineMax, size) * lh; cur = 0; lineMax = 0; };
  for (const r of runs){
    if (r.br){ endLine(); continue; }
    for (const p of String(r.text).split(/(\s+)/)){
      if (!p) continue;
      if (/^\s+$/.test(p)){ if (cur > 0) cur += lineW(' ', r.size, r.bold, ls); continue; }
      const ww = lineW(p, r.size, r.bold, ls);
      if (ww > boxW){                                   // tu don dai hon khung -> be tu
        if (cur > 0) endLine();
        const full = Math.ceil(ww / boxW) - 1;
        for (let i = 0; i < full; i++){ lineMax = Math.max(lineMax, r.size); endLine(); }
        cur = ww % boxW || boxW; lineMax = Math.max(lineMax, r.size); continue;
      }
      if (cur > 0 && cur + ww > boxW) endLine();
      cur += ww; lineMax = Math.max(lineMax, r.size);
    }
  }
  if (cur > 0 || lineMax) endLine();
  // Khoi tron nhieu co chu: moi dong bi lam tron nua-khoang-dan mot chut, cong don lai co the lech
  // 1-2px. Them dem 2px cho huong AN TOAN - virtualHeight thieu la Webcake CAT chu o ban chay that,
  // con thua vai pixel thi khong ai thay.
  const mixed = /font-size:/i.test(String(html == null ? '' : html));
  return Math.ceil(total || size * lh) + (mixed ? 2 : 0);
}
// giu ten cu de tuong thich (window va code ngoai neu co)
function measureText(html, fontSize, boxW){ return textH(html, fontSize, boxW, false); }
/** Gop line-height / letter-spacing (neu khac mac dinh) vao customCss cua mot khoi chu. */
function typoCss(o){
  const bits = [];
  if (o.lh && Math.abs(o.lh - LH) > 0.01) bits.push('line-height:' + o.lh);
  if (o.ls) bits.push('letter-spacing:' + (Math.round(o.ls * 100) / 100) + 'px');
  if (o.customCss) bits.push(String(o.customCss).replace(/;\s*$/, ''));
  return bits.join(';') || undefined;
}

const anim = (name) => ({ repeat: null, name: name || 'fadeInUp', duration: 1, delay: 0 });

/* Cua thoat hiem CHINH CHU cua Webcake cho thu ma element khong bieu dien duoc (gradient chu,
 * box-shadow la, backdrop-filter, transition...). Renderer CHI doc custom_css khi customAdvance
 * = true, va chi nhan KHAI BAO (khong selector, khong :hover, khong @keyframes - nhung thu do
 * thuoc settings.extra_css). Tuyet doi khong nhet position/top/left/width/height vao day: chung
 * de len hop tuyet doi cua canvas va lam vo bo cuc. */
const CUSTOM_CSS_BANNED = /(^|;)\s*(position|top|left|right|bottom|inset|width|height|display|float|flex|grid)\s*:/i;
function applyCustom(node, css, cls){
  if (css){
    const clean = String(css).replace(/[{}]/g, ' ').trim().replace(/;\s*$/, '');
    if (clean){
      if (CUSTOM_CSS_BANNED.test(';' + clean))
        throw new Error('customCss chua thuoc tinh hinh hoc (position/top/left/width/height/display/flex/grid) - dat qua styles, khong qua customCss: ' + clean);
      node.specials.custom_css = clean + ';';
      node.specials.customAdvance = true;
    }
  }
  if (cls){ node.specials.custom_class = String(cls); node.specials.customAdvance = true; }
  return node;
}
function firstColor(bg){
  const m = String(bg || '').match(/rgba?\([^)]*\)/);
  return m ? m[0] : 'rgba(120,120,140,1)';
}
function glowFrom(bg){
  const m = firstColor(bg).match(/rgba?\(([^)]*)\)/);
  const p = m[1].split(',').map(s => s.trim());
  return `0px 8px 26px rgba(${p[0]}, ${p[1]}, ${p[2]}, 0.35)`;
}

/* ================= NODE FACTORIES ================= */
function textNode(html, o, xD, yD, wD, xM, yM, wM){
  const sizeD = o.sizeD, sizeM = o.sizeM;
  const st = (x, y, w, size) => ({
    width: w, top: Math.round(y), textAlign: o.align || 'center', left: Math.round(x), height: 0,
    fontWeight: o.bold ? 'bold' : 'normal', fontSize: String(size), color: o.color || 'rgba(232,234,246,1)',
    borderWidth: 0, borderStyle: 'solid', borderColor: 'rgba(229, 231, 235, 1)'
  });
  const mD = { lh: o.lh, ls: o.ls, customCss: o.customCss };
  const mM = { lh: o.lh, ls: o.ls ? o.ls * (sizeM / (sizeD || sizeM || 1)) : 0, customCss: o.customCss };
  const hD = o.hD != null ? o.hD : textH(html, sizeD, wD, o.bold, mD);
  const hM = o.hM != null ? o.hM : textH(html, sizeM, wM, o.bold, mM);
  const r = { node: {
    type: 'text-block', specials: { text: String(html == null ? '' : html), tag: o.tag || 'p' }, runtime: {},
    responsive: {
      mobile:  { styles: st(xM, yM, wM, sizeM), config: { virtualHeight: hM, notloaded: false, animation: anim(o.anim) } },
      desktop: { styles: st(xD, yD, wD, sizeD), config: { virtualHeight: hD, notloaded: false, animation: anim(o.anim) } }
    },
    properties: { sync: true, name: o.name || 'text', movable: true }, id: id(), events: []
  }, hD, hM };
  applyCustom(r.node, typoCss(mD), o.customClass);
  return r;
}
function rectNode(bg, o, xD, yD, wD, hD, xM, yM, wM, hM){
  const bw = o.borderWidth != null ? o.borderWidth : (o.borderColor ? 1 : 0);
  const st = (x, y, w, h) => ({
    width: Math.round(w), top: Math.round(y), textShadow: '', left: Math.round(x), height: Math.round(h), fontSize: '16',
    filter: o.filter || '', boxShadow: o.boxShadow || '', borderWidth: bw,
    borderStyle: 'solid', borderRadius: (o.radius != null ? o.radius : 16) + 'px',
    borderColor: o.borderColor || 'rgba(255,255,255,0.08)', background: bg
  });
  return applyCustom({
    type: 'rectangle', specials: {}, runtime: {},
    responsive: {
      mobile:  { styles: st(xM, yM, wM, hM), config: { notloaded: false, hiddenEffect: {}, bgHidden: {}, animation: anim('none') } },
      desktop: { styles: st(xD, yD, wD, hD), config: { notloaded: false, hiddenEffect: {}, bgHidden: {}, animation: anim('none') } }
    },
    properties: { sync: true, name: o.name || 'rectangle', movable: true }, id: id(), events: []
  }, o.customCss, o.customClass);
}
function imageNode(src, o, xD, yD, wD, hD, xM, yM, wM, hM){
  // Khuon CHINH XAC cua editor Webcake. Thieu 'scroll' (ban cu) thi lan dau upload van hien,
  // nhung vua mo trong editor Webcake la chuoi bi bien thanh 'undefined/ undefined/ ...' va anh MAT.
  const bg = `center center/ cover no-repeat scroll content-box url(${src}) border-box`;
  const st = (x, y, w, h) => ({ zIndex: null, width: Math.round(w), top: Math.round(y), textShadow: '', position: 'absolute',
    left: Math.round(x), height: Math.round(h), filter: '', boxShadow: o.boxShadow || '', borderWidth: 0, borderStyle: 'solid',
    borderRadius: (o.radius != null ? o.radius : 0) + 'px',
    borderColor: 'rgba(255, 255, 255, 1)', background: bg });
  const cfg = (w, h) => ({ widthBgImage: Math.round(w), topBgImage: 0, notloaded: false, leftBgImage: 0, hiddenEffect: {},
    heightBgImage: Math.round(h), borderColorHidden: {}, bgHidden: {}, animation: anim() });
  return applyCustom({ type: 'image-block', specials: { src, imageCompression: true, compressible: true }, runtime: { checkedBlurImage: false },
    responsive: { mobile: { styles: st(xM, yM, wM, hM), config: cfg(wM, hM) }, desktop: { styles: st(xD, yD, wD, hD), config: cfg(wD, hD) } },
    properties: { sync: true, name: 'image-block', movable: true }, id: id(), events: [] }, o.customCss, o.customClass);
}
function buttonNode(el, xD, yD, wD, hD, xM, yM, wM, hM){
  const bg = el.bg || 'linear-gradient(135deg, rgba(90,96,132,1) 0%, rgba(58,62,88,1) 100%)';
  const events = el.href ? [{ type: 'click', target: el.href, id: id(), hoverColor: '', appTarget: '', action: 'link' }]
              : (el.scrollTo ? [{ type: 'click', target: el.scrollTo, id: id(), hoverColor: '', appTarget: '', action: 'scroll_to' }] : []);
  const shadow = el.boxShadow != null ? el.boxShadow : glowFrom(bg);
  const st = (x, y, w, h, size) => ({ width: Math.round(w), top: Math.round(y), left: Math.round(x), height: Math.round(h),
    fontWeight: 'bold', fontSize: String(size), color: el.color || 'rgba(255,255,255,1)',
    boxShadow: shadow, borderWidth: el.borderWidth != null ? el.borderWidth : 0,
    borderStyle: 'solid', borderRadius: (el.radius != null ? el.radius : 12) + 'px',
    borderColor: el.borderColor || firstColor(bg), background: bg });
  return applyCustom({ type: 'button', specials: { text: String(el.text || 'BUTTON') }, runtime: {},
    responsive: { mobile:  { styles: st(xM, yM, wM, hM, el.sizeMobile || 15), config: { notloaded: false, bgHidden: {}, animation: anim(el.animation || 'flipInX') } },
                  desktop: { styles: st(xD, yD, wD, hD, el.size || 16), config: { notloaded: false, bgHidden: {}, animation: anim(el.animation || 'flipInX') } } },
    properties: { sync: true, name: 'button', movable: true }, id: id(), events }, el.customCss, el.customClass);
}

/* ================= EMIT: dat 1 item, tra {hD,hM}, day node vao out ================= */
function emit(rawIt, xD, yD, wD, xM, yM, wM, out){
  const it = withDefaults(rawIt);
  const k = (it.kind || '').toLowerCase();

  /* ---- hang nhieu cot ---- */
  if (k === 'row' || k === 'cardsrow' || k === 'testimonialrow'){
    let cols;
    if (k === 'cardsrow') cols = (it.cards || []).map(c => ({ items: [{ ...c, kind: 'card' }] }));
    else if (k === 'testimonialrow') cols = (it.items || []).map(c => ({ items: [{ ...c, kind: 'testimonial' }] }));
    else cols = it.cols || [];
    const n = cols.length || 1;
    const gapD = it.gap != null ? it.gap : 22, gapM = Math.round((it.gap != null ? it.gap : 22) * 0.7);
    const availD = wD - gapD * (n - 1);
    let cxD = xD, curYM = yM, maxHD = 0;
    const colMeta = [];
    for (let i = 0; i < n; i++){
      const col = cols[i];
      const cwD = Math.round(availD * (col.w || 1 / n));
      const start = out.length;
      const r = stack(col.items || [], col.gap != null ? col.gap : 12, cxD, yD, cwD, xM, curYM, wM, out);
      colMeta.push({ start, end: out.length, hD: r.hD });
      maxHD = Math.max(maxHD, r.hD);
      cxD += cwD + gapD;
      curYM += r.hM + gapM;
    }
    if (it.valign === 'center' || it.valign === 'middle'){        // can giua doc tren desktop
      for (const cm of colMeta){
        const dy = Math.round((maxHD - cm.hD) / 2);
        if (dy > 0) for (let i = cm.start; i < cm.end; i++) out[i].responsive.desktop.styles.top += dy;
      }
    }
    return { hD: maxHD, hM: curYM - yM - gapM };
  }

  /* ---- hero: 2 cot chu + media, can giua doc ---- */
  if (k === 'hero'){
    const mediaW = it.mediaW || 0.42;
    const contentCol = { w: 1 - mediaW, gap: it.itemGap != null ? it.itemGap : 14, items: it.items || [] };
    const mediaCol = { w: mediaW, items: it.media ? [it.media] : [] };
    const cols = (it.side === 'left') ? [mediaCol, contentCol] : [contentCol, mediaCol];
    return emit({ kind: 'row', gap: it.gap != null ? it.gap : 40, valign: it.valign || 'center', cols }, xD, yD, wD, xM, yM, wM, out);
  }

  /* ---- heading / text (ho tro kicker + maxWidth) ---- */
  if (k === 'heading' || k === 'text'){
    const isH = k === 'heading';
    let usedD = 0, usedM = 0, curYD = yD, curYM = yM;
    if (it.kicker){
      const r = emit({ kind: 'badge', text: it.kicker, align: it.align === 'left' ? 'left' : 'center' }, xD, curYD, wD, xM, curYM, wM, out);
      curYD += r.hD + 14; curYM += r.hM + 10;
      usedD = r.hD + 14; usedM = r.hM + 10;
    }
    const sizeD = it.size || (isH ? 28 : 16);
    const sizeM = it.sizeMobile || Math.max(13, Math.round(sizeD * 0.84));
    const capRaw = it.maxWidth != null ? it.maxWidth : (isH ? THEME.headingMaxWidth : THEME.textMaxWidth);
    const twD = Math.min(wD, capRaw || 1e9);
    const txD = xD + Math.round((wD - twD) / 2);
    const r = textNode(it.text != null ? it.text : it.html, {
      sizeD, sizeM, align: it.align || 'center', bold: it.bold != null ? it.bold : isH,
      color: it.color || (isH ? 'rgba(232,234,246,1)' : 'rgba(154,160,181,1)'), tag: it.tag || (isH ? 'h2' : 'p'),
      name: isH ? 'heading' : 'text', anim: it.animation, customCss: it.customCss, customClass: it.customClass,
      lh: it.lineHeight, ls: it.letterSpacing,
      hD: it.height != null ? it.height : undefined, hM: it.heightMobile != null ? it.heightMobile : undefined
    }, txD, curYD, twD, xM, curYM, wM);
    out.push(r.node);
    return { hD: usedD + r.hD, hM: usedM + r.hM };
  }

  /* ---- image ---- */
  if (k === 'image'){
    const ratio = it.ratio || 1.4;
    const fracD = it.width || 1, fracM = it.widthMobile != null ? it.widthMobile : fracD;
    const iwD = Math.round(wD * fracD), iwM = Math.round(wM * fracM);
    const ihD = Math.round(iwD / ratio), ihM = Math.round(iwM / ratio);
    out.push(imageNode(it.src, { radius: it.radius, boxShadow: it.boxShadow, customCss: it.customCss, customClass: it.customClass },
      xD + (wD - iwD) / 2, yD, iwD, ihD, xM + (wM - iwM) / 2, yM, iwM, ihM));
    return { hD: ihD, hM: ihM };
  }

  /* ---- button (height tu tinh theo do dai chu) ---- */
  if (k === 'button'){
    const bwD = it.width ? Math.round(wD * it.width) : wD;
    const bwM = it.widthMobile ? Math.round(wM * it.widthMobile) : wM;
    const plain = stripHtml(it.text);
    const linesD = Math.max(1, Math.ceil(lineW(plain, it.size || 16, true) / Math.max(60, bwD - 40)));
    const linesM = Math.max(1, Math.ceil(lineW(plain, it.sizeMobile || 15, true) / Math.max(60, bwM - 32)));
    const hD = it.height || (linesD > 1 ? 30 + Math.round(linesD * (it.size || 16) * 1.4) : 56);
    const hM = it.heightMobile || (linesM > 1 ? 28 + Math.round(linesM * (it.sizeMobile || 15) * 1.4) : 52);
    out.push(buttonNode(it, xD + (wD - bwD) / 2, yD, bwD, hD, xM + (wM - bwM) / 2, yM, bwM, hM));
    return { hD, hM };
  }

  /* ---- badge: tu co chu / tu wrap khi dai ---- */
  if (k === 'badge'){
    const padx = it.padX != null ? it.padX : 20, ph = it.padY != null ? it.padY : 10;
    const plain = stripHtml(it.text || '');
    function fit(avail, size0){
      let size = size0;
      const oneW = (s) => lineW(plain, s, true) + padx * 2;
      while (oneW(size) > avail && size > 10.5) size -= 0.5;
      if (oneW(size) <= avail) return { size, bw: Math.max(44, Math.round(oneW(size))), lines: 1 };
      const inner = avail - padx * 2;
      const th = textH(plain, size, inner, true);
      const lines = Math.max(2, Math.round(th / (size * LH)));
      return { size, bw: avail, lines };
    }
    const fD = fit(wD, it.size || 13);
    const fM = fit(wM, Math.max(11, Math.round((it.size || 13) * 0.9)));
    const contentH = (f) => Math.ceil(f.lines * f.size * LH);
    const hOf = (f) => contentH(f) + ph * 2;
    const hD = hOf(fD), hM = hOf(fM);
    const align = it.align || 'center';
    const bxD = align === 'left' ? xD : xD + (wD - fD.bw) / 2;
    const bxM = align === 'left' ? xM : xM + (wM - fM.bw) / 2;
    out.push(rectNode(it.bg || 'rgba(20,22,34,0.7)', { radius: 99, borderWidth: it.borderWidth != null ? it.borderWidth : 1,
      borderColor: it.borderColor || 'rgba(255,255,255,0.18)', name: 'badge-bg' }, bxD, yD, fD.bw, hD, bxM, yM, fM.bw, hM));
    // text chiem nguyen be rong pill + chieu cao da biet -> khong bao gio wrap lech so voi pill
    const t = textNode(it.text, { sizeD: fD.size, sizeM: fM.size, align: 'center', bold: true,
      color: it.color || 'rgba(200,205,225,1)', name: 'badge', hD: contentH(fD), hM: contentH(fM) },
      bxD, yD + ph - 1, fD.bw, bxM, yM + ph - 1, fM.bw);
    out.push(t.node);
    return { hD, hM };
  }

  /* ---- card: nen + (icon) + title + text; iconTop, accent trai, maxWidth ---- */
  if (k === 'card'){
    const pad = it.pad != null ? it.pad : 24, gap = it.gapInner != null ? it.gapInner : 8;
    const bg = it.bg || 'rgba(20,22,34,1)';
    const capW = Math.min(wD, it.maxWidth != null ? it.maxWidth : (THEME.cardMaxWidth || 1e9));
    const cxD = xD + Math.round((wD - capW) / 2);
    const innerD = capW - pad * 2, innerM = wM - pad * 2;
    const iconTop = !!it.iconTop && !!it.icon;
    const title = (!iconTop && it.icon) ? (it.icon + '  ' + (it.title || '')) : (it.title || '');
    const tSizeD = it.titleSize || 19, tSizeM = Math.max(15, Math.round(tSizeD * 0.9));
    const bSizeD = it.textSize || 14.5, bSizeM = Math.max(13, Math.round(bSizeD * 0.92));
    const icSize = it.iconSize || 30;
    const icHD = iconTop ? Math.round(icSize * LH) : 0, icHM = icHD;
    const thD = title ? textH(title, tSizeD, innerD, true) : 0, thM = title ? textH(title, tSizeM, innerM, true) : 0;
    const bhD = it.text ? textH(it.text, bSizeD, innerD, false) : 0, bhM = it.text ? textH(it.text, bSizeM, innerM, false) : 0;
    const parts = (a, b, c) => a + (a && (b || c) ? gap : 0) + b + (b && c ? gap : 0) + c;
    const cHD = pad + parts(icHD, thD, bhD) + pad;
    const cHM = pad + parts(icHM, thM, bhM) + pad;
    out.push(rectNode(bg, { radius: it.radius != null ? it.radius : 16, name: 'card-bg', boxShadow: it.boxShadow || '',
      borderColor: it.borderColor, borderWidth: it.borderWidth, customCss: it.customCss, customClass: it.customClass },
      cxD, yD, capW, cHD, xM, yM, wM, cHM));
    if (it.accent) out.push(rectNode(it.accent, { radius: 2, name: 'card-accent', borderWidth: 0 },
      cxD, yD + 6, 3, cHD - 12, xM, yM + 6, 3, cHM - 12));
    let yTD = yD + pad, yTM = yM + pad;
    if (iconTop){
      const ic = textNode(it.icon, { sizeD: icSize, sizeM: icSize, align: it.align || 'left', bold: false,
        color: it.titleColor || 'rgba(232,234,246,1)', name: 'card-icon', hD: icHD, hM: icHM },
        cxD + pad, yTD, innerD, xM + pad, yTM, innerM);
      out.push(ic.node); yTD += icHD + gap; yTM += icHM + gap;
    }
    if (title){
      const t = textNode(title, { sizeD: tSizeD, sizeM: tSizeM, align: it.align || 'left', bold: true,
        color: it.titleColor || 'rgba(232,234,246,1)', name: 'card-title' }, cxD + pad, yTD, innerD, xM + pad, yTM, innerM);
      out.push(t.node); yTD += thD + gap; yTM += thM + gap;
    }
    if (it.text){
      const t = textNode(it.text, { sizeD: bSizeD, sizeM: bSizeM, align: it.align || 'left', bold: false,
        color: it.textColor || 'rgba(154,160,181,1)', name: 'card-text' }, cxD + pad, yTD, innerD, xM + pad, yTM, innerM);
      out.push(t.node);
    }
    return { hD: cHD, hM: cHM };
  }

  /* ---- testimonial: sao + quote + tac gia (dung khuon card) ---- */
  if (k === 'testimonial'){
    const stars = '★'.repeat(Math.max(1, Math.min(5, it.stars || 5)));
    let q = String(it.quote || '').trim();
    if (q && !/^["“]/.test(q)) q = '“' + q + '”';
    const author = it.author ? `<br><br><span style='font-weight:700;color:${it.authorColor || 'rgba(230,190,120,1)'};'>${it.author}</span>` : '';
    return emit({
      kind: 'card', bg: it.bg, borderColor: it.borderColor, radius: it.radius, maxWidth: it.maxWidth,
      pad: it.pad, align: it.align || 'left', accent: it.accent,
      title: stars, titleColor: it.starColor || 'rgba(230,190,120,1)', titleSize: it.starSize || 14,
      text: `<i>${q}</i>${author}`, textColor: it.textColor, textSize: it.textSize || 14.5
    }, xD, yD, wD, xM, yM, wM, out);
  }

  /* ---- guarantee: icon lon trai + noi dung phai ---- */
  if (k === 'guarantee'){
    const pad = it.pad != null ? it.pad : 26, gap = 8;
    const capW = Math.min(wD, it.maxWidth != null ? it.maxWidth : (THEME.cardMaxWidth || 1e9));
    const cxD = xD + Math.round((wD - capW) / 2);
    const icW = it.iconSize != null ? Math.round(it.iconSize * 1.4) : 62, icSize = it.iconSize || 44;
    const innerD = capW - pad * 2 - icW - 18, innerM = wM - pad * 2 - Math.round(icW * 0.8) - 12;
    const tSizeD = it.titleSize || 16, tSizeM = Math.max(14, Math.round(tSizeD * 0.92));
    const bSizeD = it.textSize || 14.5, bSizeM = Math.max(13, Math.round(bSizeD * 0.92));
    const thD = it.title ? textH(it.title, tSizeD, innerD, true) : 0, thM = it.title ? textH(it.title, tSizeM, innerM, true) : 0;
    const bhD = it.text ? textH(it.text, bSizeD, innerD, false) : 0, bhM = it.text ? textH(it.text, bSizeM, innerM, false) : 0;
    const contD = thD + (thD && bhD ? gap : 0) + bhD, contM = thM + (thM && bhM ? gap : 0) + bhM;
    const icHD = Math.round(icSize * LH), icHM = Math.round(icSize * 0.85 * LH);
    const cHD = pad * 2 + Math.max(contD, icHD), cHM = pad * 2 + Math.max(contM, icHM);
    out.push(rectNode(it.bg || 'rgba(20,26,22,1)', { radius: it.radius != null ? it.radius : 16, name: 'guarantee-bg',
      borderColor: it.borderColor || 'rgba(111,186,111,0.35)', borderWidth: it.borderWidth }, cxD, yD, capW, cHD, xM, yM, wM, cHM));
    const icYD = yD + Math.round((cHD - icHD) / 2), icYM = yM + Math.round((cHM - icHM) / 2);
    const ic = textNode(it.icon || '🛡️', { sizeD: icSize, sizeM: Math.round(icSize * 0.85), align: 'center', bold: false,
      color: 'rgba(255,255,255,1)', name: 'guarantee-icon', hD: icHD, hM: icHM },
      cxD + pad, icYD, icW, xM + pad, icYM, Math.round(icW * 0.8));
    out.push(ic.node);
    const txD0 = cxD + pad + icW + 18, txM0 = xM + pad + Math.round(icW * 0.8) + 12;
    let yTD = yD + Math.round((cHD - contD) / 2), yTM = yM + Math.round((cHM - contM) / 2);
    if (it.title){
      const t = textNode(it.title, { sizeD: tSizeD, sizeM: tSizeM, align: 'left', bold: true,
        color: it.titleColor || 'rgba(111,186,111,1)', name: 'guarantee-title' }, txD0, yTD, innerD, txM0, yTM, innerM);
      out.push(t.node); yTD += thD + gap; yTM += thM + gap;
    }
    if (it.text){
      const t = textNode(it.text, { sizeD: bSizeD, sizeM: bSizeM, align: 'left', bold: false,
        color: it.textColor || 'rgba(180,196,182,1)', name: 'guarantee-text' }, txD0, yTD, innerD, txM0, yTM, innerM);
      out.push(t.node);
    }
    return { hD: cHD, hM: cHM };
  }

  /* ---- priceTable: bang gia tri ---- */
  if (k === 'pricetable'){
    const pad = it.pad != null ? it.pad : 26, rowGap = it.rowGap != null ? it.rowGap : 13;
    const capW = Math.min(wD, it.maxWidth != null ? it.maxWidth : (THEME.cardMaxWidth || 1e9));
    const cxD = xD + Math.round((wD - capW) / 2);
    const innerD = capW - pad * 2, innerM = wM - pad * 2;
    const labelW = 0.66, priceW = 0.30;
    const rows = it.rows || [];
    const rSizeD = it.rowSize || 15, rSizeM = Math.max(13, Math.round(rSizeD * 0.9));
    const labelColor = it.labelColor || 'rgba(154,160,181,1)', priceColor = it.priceColor || 'rgba(232,234,246,1)';
    // do truoc toan bo chieu cao
    const measures = rows.map(r => ({
      hD: Math.max(textH(r.label, rSizeD, innerD * labelW, false), textH(r.price, rSizeD, innerD * priceW, true)),
      hM: Math.max(textH(r.label, rSizeM, innerM * labelW, false), textH(r.price, rSizeM, innerM * priceW, true))
    }));
    const tSizeD = it.titleSize || 13;
    const titleHD = it.title ? textH(it.title, tSizeD, innerD, true) + 14 : 0;
    const titleHM = it.title ? textH(it.title, Math.max(12, tSizeD - 1), innerM, true) + 12 : 0;
    const totSize = it.totalSize || 19;
    const totHD = it.total ? Math.max(textH(it.total.label, totSize, innerD * labelW, true), textH(it.total.price, totSize, innerD * priceW, true)) + 10 : 0;
    const totHM = it.total ? Math.max(textH(it.total.label, Math.round(totSize * 0.9), innerM * labelW, true), textH(it.total.price, Math.round(totSize * 0.9), innerM * priceW, true)) + 8 : 0;
    const strikeHD = it.strike ? textH(it.strike, 15, innerD, false) + 8 : 0;
    const strikeHM = it.strike ? textH(it.strike, 14, innerM, false) + 6 : 0;
    const todayHD = it.today ? textH(it.today, 16, innerD, false) : 0;
    const todayHM = it.today ? textH(it.today, 15, innerM, false) : 0;
    let bodyD = 0, bodyM = 0;
    measures.forEach(m => { bodyD += m.hD + rowGap; bodyM += m.hM + rowGap; });
    const cHD = pad + titleHD + bodyD + totHD + strikeHD + todayHD + pad;
    const cHM = pad + titleHM + bodyM + totHM + strikeHM + todayHM + pad;
    out.push(rectNode(it.bg || 'rgba(20,22,34,1)', { radius: it.radius != null ? it.radius : 18, name: 'price-bg',
      borderColor: it.borderColor, borderWidth: it.borderWidth }, cxD, yD, capW, cHD, xM, yM, wM, cHM));
    let yTD = yD + pad, yTM = yM + pad;
    if (it.title){
      const t = textNode(it.title, { sizeD: tSizeD, sizeM: Math.max(12, tSizeD - 1), align: 'center', bold: true,
        color: it.titleColor || 'rgba(230,190,120,1)', name: 'price-title' }, cxD + pad, yTD, innerD, xM + pad, yTM, innerM);
      out.push(t.node);
      out.push(rectNode(it.lineColor || 'rgba(255,255,255,0.10)', { radius: 1, name: 'price-line', borderWidth: 0 },
        cxD + pad, yTD + titleHD - 7, innerD, 1, xM + pad, yTM + titleHM - 6, innerM, 1));
      yTD += titleHD; yTM += titleHM;
    }
    rows.forEach((r, i) => {
      const m = measures[i];
      const l = textNode(r.label, { sizeD: rSizeD, sizeM: rSizeM, align: 'left', bold: false, color: labelColor, name: 'price-label' },
        cxD + pad, yTD, Math.round(innerD * labelW), xM + pad, yTM, Math.round(innerM * labelW));
      out.push(l.node);
      const p = textNode(r.price, { sizeD: rSizeD, sizeM: rSizeM, align: 'right', bold: true, color: priceColor, name: 'price-value' },
        cxD + pad + Math.round(innerD * (1 - priceW)), yTD, Math.round(innerD * priceW),
        xM + pad + Math.round(innerM * (1 - priceW)), yTM, Math.round(innerM * priceW));
      out.push(p.node);
      if (i < rows.length - 1) out.push(rectNode(it.lineColor || 'rgba(255,255,255,0.06)', { radius: 1, name: 'price-line', borderWidth: 0 },
        cxD + pad, yTD + m.hD + Math.round(rowGap / 2) - 1, innerD, 1, xM + pad, yTM + m.hM + Math.round(rowGap / 2) - 1, innerM, 1));
      yTD += m.hD + rowGap; yTM += m.hM + rowGap;
    });
    if (it.total){
      const tc = it.totalColor || 'rgba(230,190,120,1)';
      out.push(rectNode(it.lineColor || 'rgba(255,255,255,0.14)', { radius: 1, name: 'price-line', borderWidth: 0 },
        cxD + pad, yTD - Math.round(rowGap / 2), innerD, 1, xM + pad, yTM - Math.round(rowGap / 2), innerM, 1));
      const l = textNode(it.total.label, { sizeD: totSize, sizeM: Math.round(totSize * 0.9), align: 'left', bold: true, color: tc, name: 'price-total' },
        cxD + pad, yTD + 6, Math.round(innerD * labelW), xM + pad, yTM + 5, Math.round(innerM * labelW));
      out.push(l.node);
      const p = textNode(it.total.price, { sizeD: totSize, sizeM: Math.round(totSize * 0.9), align: 'right', bold: true, color: tc, name: 'price-total-value' },
        cxD + pad + Math.round(innerD * (1 - priceW)), yTD + 6, Math.round(innerD * priceW),
        xM + pad + Math.round(innerM * (1 - priceW)), yTM + 5, Math.round(innerM * priceW));
      out.push(p.node);
      yTD += totHD; yTM += totHM;
    }
    if (it.strike){
      const t = textNode(`<span style='text-decoration:line-through;'>${it.strike}</span>`, { sizeD: 15, sizeM: 14, align: 'center', bold: false,
        color: it.strikeColor || 'rgba(140,140,150,1)', name: 'price-strike' }, cxD + pad, yTD + 4, innerD, xM + pad, yTM + 3, innerM);
      out.push(t.node); yTD += strikeHD; yTM += strikeHM;
    }
    if (it.today){
      const t = textNode(it.today, { sizeD: 16, sizeM: 15, align: 'center', bold: false,
        color: it.todayColor || 'rgba(232,234,246,1)', name: 'price-today' }, cxD + pad, yTD, innerD, xM + pad, yTM, innerM);
      out.push(t.node);
    }
    return { hD: cHD, hM: cHM };
  }

  /* ---- divider ---- */
  if (k === 'divider'){
    const frac = it.width || 0.36, h = it.thickness || 1;
    const dwD = Math.round(wD * frac), dwM = Math.round(wM * frac);
    out.push(rectNode(it.color || 'rgba(255,255,255,0.12)', { radius: 1, name: 'divider', borderWidth: 0 },
      xD + (wD - dwD) / 2, yD, dwD, h, xM + (wM - dwM) / 2, yM, dwM, h));
    return { hD: h, hM: h };
  }

  /* ---- progress: track + fill + label ---- */
  if (k === 'progress'){
    const frac = it.width || 0.7, h = it.thickness || 8;
    const val = Math.max(0, Math.min(1, it.value != null ? it.value : 0.5));
    const twD = Math.round(wD * frac), twM = Math.round(wM * Math.min(1, frac + 0.15));
    const txD = xD + (wD - twD) / 2, txM = xM + (wM - twM) / 2;
    out.push(rectNode(it.trackColor || 'rgba(0,0,0,0.45)', { radius: 99, name: 'progress-track',
      borderColor: it.borderColor || 'rgba(255,255,255,0.12)', borderWidth: 1 }, txD, yD, twD, h, txM, yM, twM, h));
    out.push(rectNode(it.fillColor || (THEME.button.bg ? THEME.button.bg : 'rgba(120,190,120,1)'), { radius: 99, name: 'progress-fill',
      borderWidth: 0, boxShadow: it.glow ? glowFrom(it.fillColor || THEME.button.bg || '') : '' },
      txD, yD, Math.max(h, Math.round(twD * val)), h, txM, yM, Math.max(h, Math.round(twM * val)), h));
    let hD = h, hM = h;
    if (it.label){
      const lh = textNode(it.label, { sizeD: it.labelSize || 12, sizeM: Math.max(11, (it.labelSize || 12) - 1), align: 'center', bold: false,
        color: it.labelColor || 'rgba(150,152,166,1)', name: 'progress-label' }, xD, yD + h + 10, wD, xM, yM + h + 8, wM);
      out.push(lh.node);
      hD += 10 + lh.hD; hM += 8 + lh.hM;
    }
    return { hD, hM };
  }

  /* ---- ctaBlock: (mui ten) + nut + dong phu ---- */
  if (k === 'ctablock'){
    const items = [];
    if (it.arrow !== false) items.push({ kind: 'text', html: it.arrowText || '▼ ▼ ▼', size: 15,
      color: it.arrowColor || firstColor(it.bg || THEME.button.bg || ''), align: 'center', maxWidth: 9999 });
    items.push({ kind: 'button', text: it.text, href: it.href, scrollTo: it.scrollTo, width: it.width || 0.62,
      widthMobile: it.widthMobile, height: it.height, size: it.size, sizeMobile: it.sizeMobile,
      bg: it.bg, color: it.color, radius: it.radius, boxShadow: it.boxShadow, animation: it.animation });
    if (it.sub) items.push({ kind: 'text', html: it.sub, size: it.subSize || 12,
      color: it.subColor || 'rgba(150,152,166,1)', align: 'center' });
    return stack(items, it.gap != null ? it.gap : 14, xD, yD, wD, xM, yM, wM, out);
  }

  /* ---- iconRow: hang icon + chu ngan ---- */
  if (k === 'iconrow'){
    const items = it.items || [];
    const cols = items.map(x => ({ items: [
      { kind: 'text', html: x.icon || '•', size: it.iconSize || 26, align: 'center', color: x.iconColor || it.iconColor || 'rgba(232,234,246,1)', maxWidth: 9999 },
      { kind: 'text', html: x.text || '', size: it.textSize || 13, align: 'center', color: x.color || it.color || 'rgba(154,160,181,1)', maxWidth: 9999 }
    ], gap: 6 }));
    return emit({ kind: 'row', gap: it.gap != null ? it.gap : 18, cols }, xD, yD, wD, xM, yM, wM, out);
  }

  if (k === 'window'){
    const pad = 18, barH = 40, lineGap = 10;
    const bg = it.bg || 'rgba(20,22,34,1)';
    const innerD = wD - pad * 2, innerM = wM - pad * 2;
    const lines = it.lines || [];
    const lSizeD = 14, lSizeM = 13;
    let bodyD = 0, bodyM = 0;
    const lh = lines.map(L => {
      const hD = textH(L.text, lSizeD, innerD * 0.9, false), hM = textH(L.text, lSizeM, innerM * 0.9, false);
      bodyD += hD + lineGap; bodyM += hM + lineGap; return { hD, hM };
    });
    const cHD = barH + pad + bodyD + pad, cHM = barH + pad + bodyM + pad;
    out.push(rectNode(bg, { radius: 16, borderColor: it.borderColor || 'rgba(255,255,255,0.14)', borderWidth: 1, name: 'window-bg',
      boxShadow: '0px 30px 80px rgba(0,0,0,0.5)' }, xD, yD, wD, cHD, xM, yM, wM, cHM));
    const bar = textNode(it.title || 'Window', { sizeD: 12.5, sizeM: 12, align: 'left', bold: false,
      color: 'rgba(154,160,181,1)', name: 'window-bar' }, xD + pad + 30, yD + 12, innerD - 30, xM + pad + 30, yM + 12, innerM - 30);
    out.push(bar.node);
    let yLD = yD + barH + pad, yLM = yM + barH + pad;
    lines.forEach((L, i) => {
      const you = L.who === 'you';
      const t = textNode(L.text, { sizeD: lSizeD, sizeM: lSizeM, align: you ? 'right' : 'left', bold: false,
        color: you ? 'rgba(255,255,255,1)' : 'rgba(200,205,225,1)', name: 'window-line' },
        xD + pad, yLD, innerD, xM + pad, yLM, innerM);
      out.push(t.node); yLD += lh[i].hD + lineGap; yLM += lh[i].hM + lineGap;
    });
    return { hD: cHD, hM: cHM };
  }

  if (k === 'spacer') return { hD: it.height || 40, hM: it.heightMobile || it.height || 40 };

  if (k === 'form') return emitForm(it, xD, yD, wD, xM, yM, wM, out);

  throw new Error('kind la: ' + it.kind);
}

function emitForm(el, xD, yD, wD, xM, yM, wM, out){
  const fields = el.fields || [
    { name: 'full_name', placeholder: 'Họ và tên', type: 'text', required: true },
    { name: 'phone_number', placeholder: 'Số điện thoại', type: 'phone', required: true }
  ];
  const fieldH = 50, fieldGap = 14, pad = 16, btnH = 60;
  const formId = id(); const children = []; let y = pad;
  const innerWD = wD - 1, innerWM = wM - 1;
  for (const f of fields){
    const sp = { required: f.required !== false, parentCarousel: formId, field_placeholder: f.placeholder || f.name, field_name: f.name };
    if ((f.type || '').toLowerCase() === 'email'){ sp.useInputPattern = true; sp.inputPattern = '[^@\\s]+@[^@\\s]+\\.[^@\\s]+'; }
    if ((f.type || '').toLowerCase() === 'phone'){ sp.validate = true; sp.phone_validator = '^(\\+84|84|0)(3|5|7|8|9)([0-9]{8})$'; }
    const st = (w) => ({ width: w, top: y, left: 0, height: fieldH, borderWidth: '1px', borderStyle: 'solid',
      borderRadius: '6px', borderColor: 'rgba(147, 147, 147, 1)', background: '#fff' });
    children.push({ type: 'input', specials: sp, runtime: {},
      responsive: { mobile: { styles: st(innerWM), config: { notloaded: false } }, desktop: { styles: st(innerWD), config: { notloaded: false } } },
      properties: { sync: true, name: 'Input', movable: true, field_default: true }, id: id() });
    y += fieldH + fieldGap;
  }
  const btnTop = y + 6;
  const submitBg = el.submitBg || (THEME.button && THEME.button.bg) || 'linear-gradient(135deg, rgba(90,96,132,1) 0%, rgba(58,62,88,1) 100%)';
  const bst = (w) => ({ width: w, top: btnTop, left: 0, height: btnH, fontWeight: 'bold', fontSize: '18',
    color: el.submitColor || 'rgba(255,255,255,1)', boxShadow: glowFrom(submitBg), borderWidth: 0, borderStyle: 'solid',
    borderRadius: '12px', borderColor: 'rgba(229,231,235,1)', background: submitBg });
  children.push({ type: 'button', specials: { text: String(el.submitText || 'GỬI NGAY'), parentCarousel: formId, submit: true }, runtime: {},
    responsive: { mobile: { styles: bst(innerWM), config: { notloaded: false, bgHidden: {} } }, desktop: { styles: bst(innerWD), config: { notloaded: false, bgHidden: {} } } },
    properties: { sync: true, name: 'button', movable: true }, id: id() });
  const formH = btnTop + btnH + pad;
  const fst = (w, x, yy) => ({ width: w, top: Math.round(yy), left: Math.round(x), height: formH, fontSize: '18', borderWidth: '1px',
    borderStyle: 'solid', borderRadius: '8px', borderColor: 'rgba(147, 147, 147, 1)' });
  out.push({ type: 'form',
    specials: { submit_success: el.submit || 2, redirect_url: el.redirect || '', multiFormParent: '', fb_event_type: 'Lead', event_name_custom: 'generate_lead' },
    runtime: {},
    responsive: { mobile: { styles: fst(wM, xM, yM), config: { notloaded: false, borderColorHidden: {} } },
                  desktop: { styles: fst(wD, xD, yD), config: { notloaded: false, borderColorHidden: {} } } },
    properties: { sync: true, name: 'form', movable: true }, id: formId, children });
  return { hD: formH, hM: formH };
}

/* xep doc 1 danh sach item, tra {hD,hM} */
function stack(items, gap, xD, yD, wD, xM, yM, wM, out){
  const gapD = gap, gapM = Math.round(gap * 0.7);
  let cyD = yD, cyM = yM, first = true;
  for (const it of items){
    if (!first){ cyD += gapD; cyM += gapM; } first = false;
    const r = emit(it, xD, cyD, wD, xM, cyM, wM, out);
    cyD += r.hD; cyM += r.hM;
  }
  return { hD: cyD - yD, hM: cyM - yM };
}

function buildSection(sec){
  const out = [];
  const padTopD = sec.padTop != null ? sec.padTop : 56, padTopM = sec.padTopMobile != null ? sec.padTopMobile : Math.round(padTopD * 0.72);
  const padBot = sec.padBottom != null ? sec.padBottom : padTopD;
  const padBotM = sec.padBottomMobile != null ? sec.padBottomMobile : Math.round(padBot * 0.8);
  const gap = sec.gap != null ? sec.gap : 18;
  const cwD = DESK_W - PADX_D * 2, cwM = MOB_W - PADX_M * 2;
  const r = stack(sec.elements || [], gap, PADX_D, padTopD, cwD, PADX_M, padTopM, cwM, out);
  const heightD = Math.max(sec.minHeight || 0, Math.round(padTopD + r.hD + padBot));
  const heightM = Math.max(sec.minHeightMobile || 0, Math.round(padTopM + r.hM + padBotM));
  const secStyle = (h) => { const s = { position: 'relative', height: h }; if (sec.background) s.background = sec.background; if (sec.fontSize) s.fontSize = String(sec.fontSize); return s; };
  return { type: 'section', specials: { imageCompression: true }, runtime: {},
    responsive: { mobile: { styles: secStyle(heightM), config: { notloaded: false, bgHidden: {} } },
                  desktop: { styles: secStyle(heightD), config: { notloaded: false, bgHidden: {} } } },
    properties: { sync: true, name: sec.name || 'section', movable: false }, id: id(), events: [], children: out };
}

function buildPageSource(spec){
  setTheme(spec.theme);
  spec = deepTok(spec);
  const settings = {
    width_section: { mobile: MOB_W, desktop: DESK_W }, title: spec.title || spec.name || 'Landing Page',
    tiktok_script: '', thumbnail: spec.thumbnail || '', send_info_to_thank_page: true, keywords: spec.keywords || '',
    global_track_ids: [], fontGeneral: spec.font || 'Montserrat', fb_tracking_code: '',
    favicon: spec.favicon || '', extra_script: spec.extraScript || '', extra_css: spec.extraCss || '', description: spec.description || '',
    country: '84', bhet: spec.beforeHead || '', bbet: spec.beforeBody || '', auto_save_info_user: true, auto_save_draft: true, auto_complete_form_in_popup: true, analytic_heatmap: true
  };
  return { settings, popup: [], page: (spec.sections || []).map(buildSection), options: { versionID: '', mobileOnly: !!spec.mobileOnly }, cartConfigs: {} };
}
function buildEnvelope(spec){ return { source: buildPageSource(spec), owner_id: spec.owner_id || '', name: spec.name || 'Landing Page', engine: 2, email: {}, data_set_id: [] }; }

module.exports = { buildPageSource, buildEnvelope, textH, lineW, runsOf, stripHtml, measureText, LH, CHAR_W };

if (require.main === module){
  const args = process.argv.slice(2).filter(a => a !== '--check');
  const doCheck = process.argv.includes('--check');
  const [specPath, outPath] = args;
  if (!specPath){ console.log('Cach dung: node webcake-build.js spec.json out.pke [--check]'); process.exit(1); }
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  const env = buildEnvelope(spec);
  const out = outPath || specPath.replace(/\.json$/i, '') + '.pke';
  fs.writeFileSync(out, encodeMsgpack(env).toString('base64'));
  const nEl = env.source.page.reduce((a, s) => a + s.children.length, 0);
  console.log('OK build ->', out, '| sections:', env.source.page.length, '| nodes:', nEl);
  // luon chay lint sau khi build de canh bao som
  try {
    const { lintSource, formatReport } = require('./webcake-lint.js');
    const rep = lintSource(env.source);
    console.log(formatReport(rep));
    if (doCheck && rep.errors.length) process.exit(1);
  } catch (e) {
    if (e.code !== 'MODULE_NOT_FOUND') throw e;
  }
}
