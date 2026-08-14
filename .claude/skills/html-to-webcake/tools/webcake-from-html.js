#!/usr/bin/env node
/*
 * webcake-from-html.js - HTML  ->  spec.json (dau vao cua webcake-build.js).
 *
 *   node webcake-from-html.js trang.html spec.json [--name "Ten trang"] [--quiet]
 *
 * Vi sao co file nay: truoc day skill bao agent TU DOC HTML roi TU GO spec bang tay. Do la
 * cach chac chan lech - mau, co chu, thu tu khoi deu di qua tri nho cua model. Tai lieu cua
 * chinh Webcake noi thang: "eyeballing a reference and rebuilding once typically lands ~60%
 * similar". File nay doc CASCADE CSS THAT (webcake-html.js) roi lay dung mau, dung co chu,
 * dung canh le, dung anh, dung thu tu - nen ban dung ra bam sat trang goc.
 *
 * Ranh gioi ro rang: KHONG phai anh chup pixel. Webcake la canvas tuyet doi xep doc, nen
 * bo cuc duoc TAI DUNG thanh cac section xep doc + hang nhieu cot. Nhung MAU, CHU, ANH,
 * NOI DUNG, THU TU thi lay nguyen.
 */
'use strict';
const fs = require('fs');
const H = require('./webcake-html.js');
const { lineW } = require('./webcake-build.js');   // dung CHUNG bang do rong ky tu voi engine dung trang
const { parseHTML, parseCSS, computeStyles, toRgba, toPx, luminance, trimText, els, decodeEntities } = H;

const DESK_CONTENT = 880;         // 960 - 2*40 padding cua engine
const BLOCK = new Set(['address', 'article', 'aside', 'blockquote', 'div', 'dl', 'fieldset', 'figcaption',
  'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr', 'li', 'main', 'nav',
  'ol', 'p', 'pre', 'section', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul', 'dt', 'dd']);
const SKIP = new Set(['script', 'style', 'noscript', 'head', 'link', 'meta', 'title', 'template', 'base']);

const warns = [];
const warn = (m) => { if (!warns.includes(m)) warns.push(m); };

/* ───────────────────── tien ich style ───────────────────── */

const px = (v, css, pct) => toPx(v, css && css.__fs, pct);
function num(v){ const n = parseFloat(v); return Number.isFinite(n) ? n : null; }

/** Nen cua mot element duoi dang chuoi CSS Webcake hieu, hoac null neu trong suot. */
function bgOf(css){
  if (!css) return null;
  const img = css['background-image'], sh = css.background, col = css['background-color'];
  const pick = (v) => v && !/^(none|transparent|initial|inherit|unset)$/i.test(String(v).trim()) ? String(v).trim() : null;
  const gi = pick(img);
  if (gi && /gradient|url\(/i.test(gi)){
    const c = toRgba(col);
    return c && !/,0\)$/.test(c) ? `${gi}, ${c}` : gi;
  }
  const gs = pick(sh);
  if (gs && /gradient|url\(/i.test(gs)) return gs;
  const c = toRgba(col) || (gs ? toRgba(gs.split(/\s+/)[0]) : null);
  if (c && !/,\s*0\)$/.test(c)) return c;
  return null;
}

function alignOf(css){
  const a = String((css && css['text-align']) || '').toLowerCase();
  return a === 'center' || a === 'right' || a === 'left' ? a : (a === 'start' ? 'left' : a === 'end' ? 'right' : null);
}
function boldOf(css){
  const w = String((css && css['font-weight']) || '').toLowerCase();
  if (w === 'bold' || w === 'bolder') return true;
  const n = parseInt(w, 10);
  return Number.isFinite(n) ? n >= 600 : false;
}
const hidden = (css) => !!css && (/^none$/i.test(css.display || '') || /^hidden$/i.test(css.visibility || '')
  || (css.opacity != null && parseFloat(css.opacity) === 0));

function padOf(css, side){
  if (!css) return null;
  const direct = css['padding-' + side];
  if (direct != null) return px(direct, css);
  const p = css.padding;
  if (!p) return null;
  const parts = String(p).trim().split(/\s+/);
  const idx = { top: 0, right: 1, bottom: 2, left: 3 };
  const pick = parts.length === 1 ? parts[0] : parts.length === 2 ? (side === 'top' || side === 'bottom' ? parts[0] : parts[1])
    : parts.length === 3 ? (side === 'top' ? parts[0] : side === 'bottom' ? parts[2] : parts[1])
    : parts[idx[side]];
  return px(pick, css);
}

/* ───────────────────── nhan dang loai khoi ───────────────────── */

function hasBlockDescendant(node){
  for (const c of els(node)){
    if (BLOCK.has(c.tag) || c.tag === 'img' || c.tag === 'form' || c.tag === 'table') return true;
    if (hasBlockDescendant(c)) return true;
  }
  return false;
}

function isButtonish(node){
  if (node.tag === 'button') return true;
  if (node.tag === 'input' && /^(submit|button)$/i.test(node.attrs.type || '')) return true;
  if (node.tag !== 'a' && node.tag !== 'div' && node.tag !== 'span') return false;
  const cls = H.classesOf(node).join(' ').toLowerCase() + ' ' + String(node.attrs.role || '');
  const looks = /\b(btn|button|cta|dang-ky|order|buy|mua)\b/.test(cls);
  const css = node.css || {};
  const hasBg = !!bgOf(css);
  const hasPad = (padOf(css, 'top') || 0) >= 6 || (padOf(css, 'left') || 0) >= 12;
  const round = css['border-radius'] != null;
  const short = trimText(node).length <= 90;
  if (!short || hasBlockDescendant(node)) return false;
  // Hang chua nut (vd <div class="cta-row"> co 2 the <a class="btn">) KHONG duoc coi la mot nut:
  // truoc day "cta-row" khop \bcta\b nen hai nut bi gop thanh mot cai duy nhat.
  if (node.tag !== 'button' && els(node).some(c => c.tag === 'a' || c.tag === 'button')) return false;
  return looks || (hasBg && (hasPad || round));
}

function isCardish(node){
  if (!BLOCK.has(node.tag) && node.tag !== 'li') return false;
  const css = node.css || {};
  const own = bgOf(css);
  const bordered = css.border != null || css['border-width'] != null || css['border-left'] != null
    || css['box-shadow'] != null;
  const round = px(css['border-radius'], css) || 0;
  const pad = Math.max(padOf(css, 'top') || 0, padOf(css, 'left') || 0);
  if (!(own || bordered)) return false;
  if (!(round >= 4 || pad >= 10)) return false;
  return trimText(node).length > 0;
}

function isRowish(node){
  const css = node.css || {};
  const disp = String(css.display || '').toLowerCase();
  const kids = els(node).filter(c => !SKIP.has(c.tag) && !hidden(c.css) && (trimText(c) || hasImage(c)));
  if (kids.length < 2) return false;
  if (/flex|grid|inline-flex/.test(disp)) return !/column/.test(String(css['flex-direction'] || ''));
  const cls = H.classesOf(node).join(' ').toLowerCase();
  if (/\b(row|cols?|columns|grid|flex)\b/.test(cls) && kids.length <= 4) return true;
  // con deu nhau + moi con co width % kha nhau
  const ws = kids.map(k => String((k.css || {}).width || '')).filter(w => /%$/.test(w));
  return ws.length === kids.length && kids.length <= 4;
}

/**
 * Doc `grid-template-columns` thanh mang TRONG SO tung cot (tong = 1 khi day du).
 * Day la thu quyet dinh "1 hang co may cot" o trang that: repeat(4,1fr), "300px 1fr", auto-fit...
 * Khong doc no thi 8 the trong mot luoi 4 cot se bi nhet het vao MOT hang 8 cot, moi cot con 30px.
 */
function gridCols(css, availW, gap){
  let g = css && css['grid-template-columns'];
  if (!g) return null;
  g = String(g).replace(/repeat\(\s*(\d+)\s*,\s*([^()]*(?:\([^()]*\)[^()]*)*)\)/gi,
    (m, n, x) => new Array(Math.min(12, +n)).fill(x.trim()).join(' '));
  if (/auto-fit|auto-fill/i.test(g)){
    const mm = /minmax\(\s*([\d.]+)px/i.exec(g);
    const min = mm ? parseFloat(mm[1]) : 260;
    const n = Math.max(1, Math.floor((availW + gap) / (min + gap)));
    return new Array(n).fill(1 / n);
  }
  const toks = H.splitTop(g, ' ').filter(t => t && t !== 'none');
  if (!toks.length || toks.length > 12) return null;
  const raw = toks.map(t => {
    if (/fr$/i.test(t)) return { fr: parseFloat(t) || 1 };
    const v = toPx(t, css.__fs, availW);
    return v != null ? { px: v } : { fr: 1 };
  });
  const fixed = raw.reduce((a, x) => a + (x.px || 0), 0);
  const frs = raw.reduce((a, x) => a + (x.fr || 0), 0);
  const free = Math.max(0, availW - fixed - gap * (raw.length - 1));
  const total = availW - gap * (raw.length - 1) || 1;
  return raw.map(x => (x.px != null ? x.px : (frs ? free * x.fr / frs : 0)) / total);
}

function hasImage(node){
  if (node.tag === 'img') return true;
  return els(node).some(hasImage);
}

/* ───────────────────── HTML inline giu dinh dang ───────────────────── */

const escText = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** Bien noi dung inline cua mot node thanh HTML Webcake nhan (span/b/i/u/a/br). */
function inlineHtml(node, baseCss){
  const out = [];
  for (const c of node.children || []){
    if (c.tag === '#text'){ out.push(escText(decodeEntities(c.text).replace(/\s+/g, ' '))); continue; }
    if (SKIP.has(c.tag)) continue;
    if (hidden(c.css)) continue;
    if (c.tag === 'br'){ out.push('<br>'); continue; }
    const inner = inlineHtml(c, baseCss);
    if (!inner.trim() && c.tag !== 'img') continue;
    const css = c.css || {};
    const sty = [];
    const col = toRgba(css.color);
    // mau trong suot ma khong co gradient de to = chu tang hinh -> giu mau cua khoi cha
    if (col && col !== toRgba(baseCss.color) && !/,\s*0\)$/.test(col)) sty.push('color:' + col);
    if (boldOf(css) && !boldOf(baseCss)) sty.push('font-weight:700');
    if (/italic/i.test(css['font-style'] || '') && !/italic/i.test(baseCss['font-style'] || '')) sty.push('font-style:italic');
    if (/line-through/i.test(css['text-decoration'] || '') || c.tag === 's' || c.tag === 'del' || c.tag === 'strike')
      sty.push('text-decoration:line-through');
    if (/underline/i.test(css['text-decoration'] || '') || c.tag === 'u') sty.push('text-decoration:underline');
    const bg = bgOf(css);
    const clipText = /text/i.test(String(css['background-clip'] || css['-webkit-background-clip'] || ''));
    const fillNone = /transparent|rgba\(0,\s*0,\s*0,\s*0\)/i.test(String(css['-webkit-text-fill-color'] || css.color || ''));
    if (bg && clipText && fillNone){
      // Chu to mau bang gradient. Day la HTML NAM TRONG specials.text nen -webkit-background-clip
      // chay binh thuong (khac han styles.background cua ca text-block). Bo qua cho nay la nua
      // tieu de bien mat vi color:transparent ma khong con gradient de to.
      sty.length = 0;
      sty.push('background:' + bg, '-webkit-background-clip:text', 'background-clip:text',
        '-webkit-text-fill-color:transparent');
    } else if (bg && !/gradient|url\(/i.test(bg)){
      sty.push('background:' + bg);                                        // chu highlight (nen vang...)
    }
    const fs = css.__fs, bfs = baseCss.__fs;
    if (fs && bfs && Math.abs(fs - bfs) > 0.6) sty.push('font-size:' + Math.round(fs) + 'px');
    if (/uppercase|lowercase|capitalize/i.test(css['text-transform'] || '')) sty.push('text-transform:' + css['text-transform']);
    if (c.tag === 'a' && c.attrs.href){
      out.push(`<a href='${String(c.attrs.href).replace(/'/g, '%27')}' style='${sty.join(';')}'>${inner}</a>`);
    } else if (sty.length){
      out.push(`<span style='${sty.join(';')};'>${inner}</span>`);
    } else {
      out.push(inner);
    }
  }
  return out.join('').replace(/\s{2,}/g, ' ');
}

/* ───────────────────── chuyen doi tung khoi ───────────────────── */

/** line-height + letter-spacing + VIET HOA cua nguon - ba thu quyet dinh "nhin giong" nhat. */
function typoOf(it, css){
  const fs = css.__fs || 16;
  const lhRaw = css['line-height'];
  if (lhRaw != null && !/^normal$/i.test(lhRaw)){
    const n = parseFloat(lhRaw);
    let lh = null;
    if (/^[\d.]+$/.test(String(lhRaw).trim())) lh = n;                 // so tran = boi cua co chu
    else { const v = toPx(lhRaw, fs, fs); if (v) lh = v / fs; }
    if (lh && lh > 0.6 && lh < 3 && Math.abs(lh - 1.5) > 0.02) it.lineHeight = Math.round(lh * 100) / 100;
  }
  const ls = css['letter-spacing'];
  if (ls != null && !/^normal$/i.test(ls)){
    const v = toPx(ls, fs, fs);
    if (v && Math.abs(v) >= 0.2) it.letterSpacing = Math.round(v * 100) / 100;
  }
  return it;
}
/** Ap text-transform NGAY VAO CHU: engine do chieu cao tren chuoi that nen phai doi truoc khi do. */
function applyTransform(html, css){
  const t = String((css && css['text-transform']) || '').toLowerCase();
  if (t !== 'uppercase' && t !== 'lowercase') return html;
  return html.replace(/>([^<]+)</g, (m, txt) => '>' + (t === 'uppercase' ? txt.toUpperCase() : txt.toLowerCase()) + '<')
    .replace(/^([^<]+)/, (m) => t === 'uppercase' ? m.toUpperCase() : m.toLowerCase())
    .replace(/([^>]+)$/, (m) => t === 'uppercase' ? m.toUpperCase() : m.toLowerCase());
}

function textItem(node, kind){
  const css = node.css || {};
  let html = inlineHtml(node, css).trim();
  if (!html) return null;
  html = applyTransform(html, css);
  const it = { kind };
  if (kind === 'heading'){
    it.text = html;
    it.tag = /^h[1-6]$/.test(node.tag) ? (node.tag === 'h1' ? 'h1' : node.tag === 'h2' ? 'h2' : 'h3') : 'h2';
  } else {
    it.html = html;
  }
  it.size = Math.round((css.__fs || 16) * 10) / 10;
  const col = toRgba(css.color); if (col) it.color = col;
  const al = alignOf(css); if (al) it.align = al;
  if (kind === 'text' && boldOf(css)) it.bold = true;
  const mw = px(css['max-width'], css);
  if (mw) it.maxWidth = Math.min(Math.round(mw), DESK_CONTENT);
  const mfs = node.cssM && node.cssM['font-size'] ? toPx(node.cssM['font-size'], css.__fs, css.__fs) : null;
  if (mfs) it.sizeMobile = Math.round(mfs * 10) / 10;
  return typoOf(it, css);
}

function imageItem(node, availW){
  const src = node.attrs.src || node.attrs['data-src'] || '';
  if (!src){ warn('Mot the <img> khong co src - da bo qua.'); return null; }
  if (/^data:/i.test(src)) warn('Co anh nhung dang data: URI - Webcake can URL cong khai, hay upload anh roi thay src.');
  else if (!/^https?:\/\//i.test(src)) warn(`Anh duong dan cuc bo "${src.slice(0, 60)}" - upload len host roi thay src, khong thi anh se trong.`);
  const css = node.css || {};
  const w = num(node.attrs.width) || px(css.width, css, availW);
  const h = num(node.attrs.height) || px(css.height, css, null);
  let ratio = null;
  if (w && h) ratio = w / h;
  else if (css['aspect-ratio']){
    const m = /([\d.]+)\s*\/\s*([\d.]+)/.exec(css['aspect-ratio']);
    if (m) ratio = parseFloat(m[1]) / parseFloat(m[2]);
  }
  if (!ratio){ ratio = 1.6; warn('Mot vai anh khong khai kich thuoc - dang tam ty le 1.6, xem preview roi chinh "ratio" trong spec.'); }
  const it = { kind: 'image', src, ratio: Math.round(ratio * 1000) / 1000 };
  const wpct = /%$/.test(String(css.width || '')) ? parseFloat(css.width) / 100 : null;
  const frac = wpct != null ? wpct : (w ? Math.min(1, w / availW) : 1);
  if (frac < 0.995) it.width = Math.round(frac * 1000) / 1000;
  const r = px(css['border-radius'], css); if (r) it.radius = Math.round(r);
  if (css['box-shadow']) it.boxShadow = css['box-shadow'];
  return it;
}

function buttonItem(node, availW){
  const css = node.css || {};
  const label = applyTransform(node.tag === 'input' ? (node.attrs.value || 'GỬI') : trimText(node), css);
  const it = { kind: 'button', text: label || 'BẤM VÀO ĐÂY' };
  const href = node.attrs.href;
  if (href && /^#/.test(href)) it.scrollTo = href.slice(1);
  else if (href && href !== '#') it.href = href;
  const bg = bgOf(css); if (bg) it.bg = bg;
  const col = toRgba(css.color); if (col) it.color = col;
  const r = px(css['border-radius'], css);
  if (r != null) it.radius = /%$/.test(String(css['border-radius'])) ? 99 : Math.round(r);
  if (css.__fs) it.size = Math.round(css.__fs);
  if (css['box-shadow']) it.boxShadow = css['box-shadow'];
  const w = px(css.width, css, availW);
  if (w && w < availW * 0.98){
    it.width = Math.round((w / availW) * 100) / 100;
  } else if (!/block|flex|grid/i.test(css.display || '')){
    // Nut inline trong HTML om sat chu. Do chu bang chinh bang do rong cua engine roi cong padding
    // ngang cua nguon -> nut ra dung co, thay vi mot con so 62% ang chung.
    const padx = (padOf(css, 'left') || 0) + (padOf(css, 'right') || 0) || 64;
    const tw = lineW(String(label || ''), it.size || 16, true) + padx;
    it.width = Math.max(0.22, Math.min(1, Math.round((tw / availW) * 100) / 100));
  }
  const bw = px(css['border-width'], css) || (css.border ? num(css.border) : null);
  if (bw){ it.borderWidth = Math.round(bw); const bc = toRgba((css['border-color'] || String(css.border || '').split(/\s+/).pop())); if (bc) it.borderColor = bc; }
  return it;
}

/** Vien thuoc / nhan nho: co nen + bo goc nhung khong bam duoc. */
function badgeItem(node){
  const css = node.css || {};
  const it = { kind: 'badge', text: applyTransform(inlineHtml(node, css).trim() || trimText(node), css) };
  const bg = bgOf(css); if (bg) it.bg = bg;
  const col = toRgba(css.color); if (col) it.color = col;
  const bc = toRgba(css['border-color'] || (css.border ? String(css.border).split(/\s+/).pop() : null));
  if (bc) it.borderColor = bc; else it.borderWidth = 0;
  if (css.__fs) it.size = Math.round(css.__fs * 10) / 10;
  const al = alignOf(css); if (al) it.align = al;
  const pl = padOf(css, 'left'); if (pl != null) it.padX = Math.round(pl);
  const pt = padOf(css, 'top'); if (pt != null) it.padY = Math.round(pt);
  return it;
}

const FIELD_MAP = [
  [/(full[_-]?name|ho[_-]?ten|hoten|^name$|your[_-]?name|fullname)/i, 'full_name', 'text'],
  [/(phone|tel|sdt|so[_-]?dien[_-]?thoai|mobile)/i, 'phone_number', 'phone'],
  [/(e?[_-]?mail)/i, 'email', 'email'],
  [/(address|dia[_-]?chi)/i, 'address', 'text'],
  [/(quantity|so[_-]?luong|qty)/i, 'quantity', 'number'],
];
function formItem(node){
  const fields = [];
  let submitText = null, submitBg = null, submitColor = null, redirect = node.attrs.action || '';
  (function walk(n){
    for (const c of els(n)){
      if (SKIP.has(c.tag)) continue;
      if (c.tag === 'input' || c.tag === 'textarea' || c.tag === 'select'){
        const t = String(c.attrs.type || 'text').toLowerCase();
        if (t === 'hidden') continue;
        if (t === 'submit' || t === 'button'){ submitText = c.attrs.value || submitText; submitBg = bgOf(c.css) || submitBg; submitColor = toRgba((c.css || {}).color) || submitColor; continue; }
        const key = [c.attrs.name, c.attrs.id, c.attrs.placeholder].filter(Boolean).join(' ');
        let name = null, type = t === 'tel' ? 'phone' : t;
        for (const [re, nm, ty] of FIELD_MAP) if (re.test(key)){ name = nm; type = t === 'text' ? ty : type; break; }
        if (!name) name = String(c.attrs.name || c.attrs.id || 'field_' + (fields.length + 1)).replace(/[^\w]/g, '_');
        fields.push({ name, placeholder: c.attrs.placeholder || c.attrs['aria-label'] || name, type,
          required: c.attrs.required !== undefined });
        continue;
      }
      if (c.tag === 'button'){ submitText = trimText(c) || submitText; submitBg = bgOf(c.css) || submitBg; submitColor = toRgba((c.css || {}).color) || submitColor; continue; }
      walk(c);
    }
  })(node);
  if (!fields.length) return null;
  const it = { kind: 'form', fields, submitText: submitText || 'GỬI NGAY' };
  if (submitBg) it.submitBg = submitBg;
  if (submitColor) it.submitColor = submitColor;
  if (redirect && /^https?:/i.test(redirect)) it.redirect = redirect;
  return it;
}

function listItem(node){
  const css = node.css || {};
  const ordered = node.tag === 'ol';
  const lines = [];
  let n = 0;
  for (const li of els(node)){
    if (li.tag !== 'li') continue;
    const inner = inlineHtml(li, css).trim();
    if (!inner) continue;
    n++;
    lines.push((ordered ? n + '. ' : '• ') + inner);
  }
  if (!lines.length) return null;
  const it = { kind: 'text', html: lines.join('<br>'), size: Math.round((css.__fs || 16) * 10) / 10, align: 'left' };
  const col = toRgba(css.color); if (col) it.color = col;
  return it;
}

function tableItem(node){
  const rows = [];
  let total = null;
  const trs = [];
  (function collect(n){ for (const c of els(n)){ if (c.tag === 'tr') trs.push(c); else collect(c); } })(node);
  for (const tr of trs){
    const cells = els(tr).filter(c => c.tag === 'td' || c.tag === 'th');
    if (cells.length !== 2) return null;                     // khong phai bang 2 cot -> de noi khac lo
    const label = inlineHtml(cells[0], cells[0].css || {}).trim();
    const price = inlineHtml(cells[1], cells[1].css || {}).trim();
    if (!label && !price) continue;
    const isTotal = tr.parent && tr.parent.tag === 'tfoot'
      || /\b(total|tong|thanh[- ]?tien)\b/i.test(H.classesOf(tr).join(' ') + ' ' + label);
    if (isTotal && !total) total = { label, price };
    else rows.push({ label, price });
  }
  if (!rows.length) return null;
  const it = { kind: 'priceTable', rows };
  if (total) it.total = total;
  const cap = els(node).find(c => c.tag === 'caption');
  if (cap) it.title = trimText(cap);
  const bg = bgOf(node.css); if (bg) it.bg = bg;
  return it;
}

function quoteItem(node){
  const css = node.css || {};
  let author = null;
  const cite = (function find(n){
    for (const c of els(n)){ if (c.tag === 'cite' || c.tag === 'footer') return c; const r = find(c); if (r) return r; }
    return null;
  })(node);
  if (cite){ author = trimText(cite); cite.__skip = true; }
  const quote = inlineHtml(node, css).replace(/\s+/g, ' ').trim();
  if (!quote) return null;
  const it = { kind: 'testimonial', quote: author ? quote.replace(new RegExp(escText(author).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'), '').trim() : quote };
  if (author) it.author = author;
  const bg = bgOf(css); if (bg) it.bg = bg;
  const col = toRgba(css.color); if (col) it.textColor = col;
  return it;
}

const EMOJI_HEAD = /^((?:\p{Extended_Pictographic}(?:\uFE0F|\uFE0E|\u200D\p{Extended_Pictographic}|[\u{1F3FB}-\u{1F3FF}])*\s*)+)/u;
const EMOJI_ONLY = /^(?:\p{Extended_Pictographic}|\uFE0F|\uFE0E|\u200D|[\u{1F3FB}-\u{1F3FF}]|\s)+$/u;

function cardItem(node, availW){
  const css = node.css || {};
  const parts = [];
  let title = null, icon = null;
  for (const c of els(node)){
    if (SKIP.has(c.tag) || hidden(c.css)) continue;
    // <span class="ico">🧠</span> dung truoc tieu de la khuon icon pho bien nhat cua the
    if (!icon && !title){
      const t = trimText(c);
      if (t && EMOJI_ONLY.test(t)){ icon = t; continue; }
    }
    if (/^h[1-6]$/.test(c.tag) && !title){ title = inlineHtml(c, c.css || {}).trim(); continue; }
    if (c.tag === 'ul' || c.tag === 'ol'){ const li = listItem(c); if (li) parts.push(li.html); continue; }
    const t = inlineHtml(c, c.css || {}).trim();
    if (t) parts.push(t);
  }
  if (!title && !parts.length){
    const t = inlineHtml(node, css).trim();
    if (!t) return null;
    parts.push(t);
  }
  const it = { kind: 'card' };
  if (icon){ it.icon = icon; it.iconTop = true; }
  if (title){
    // icon = emoji dan dau tieu de. PHAI dung \p{Extended_Pictographic}: ban truoc go tay mot day
    // range va lo tao ra range "0-ᾯ" om tron ca chu Latin lan tieng Viet, nen tieu de "Hoi xong la
    // quen" bi cat thanh icon "Hoi" + tieu de "xong la quen".
    const m = icon ? null : EMOJI_HEAD.exec(title.replace(/<[^>]+>/g, ''));
    if (m && m[1].trim()){ it.icon = m[1].trim(); it.iconTop = true; title = title.replace(m[1], '').trim(); }
    it.title = title;
  }
  if (parts.length) it.text = parts.join('<br><br>');
  const bg = bgOf(css); if (bg) it.bg = bg;
  const r = px(css['border-radius'], css); if (r != null) it.radius = Math.round(r);
  const pad = padOf(css, 'top'); if (pad != null) it.pad = Math.round(pad);
  const bc = toRgba(css['border-color'] || (css.border ? String(css.border).split(/\s+/).pop() : null));
  if (bc) it.borderColor = bc;
  if (css['box-shadow']) it.boxShadow = css['box-shadow'];
  const al = alignOf(css); if (al) it.align = al;
  const hcol = title ? toRgba(((els(node).find(c => /^h[1-6]$/.test(c.tag)) || {}).css || {}).color) : null;
  if (hcol) it.titleColor = hcol;
  const bcol = toRgba(css.color); if (bcol) it.textColor = bcol;
  if (availW && availW < DESK_CONTENT) it.maxWidth = 9999;   // trong 1 cot thi khong bo hep them
  return it;
}

/* ───────────────────── di cay trong 1 section ───────────────────── */

function walkBlock(node, availW, out){
  if (!node || node.__skip) return;
  if (node.tag === '#text'){
    const t = decodeEntities(node.text).replace(/\s+/g, ' ').trim();
    if (t) out.push({ kind: 'text', html: escText(t), size: Math.round(((node.parent && node.parent.css || {}).__fs) || 16) });
    return;
  }
  if (SKIP.has(node.tag) || hidden(node.css)) return;
  const css = node.css || {};

  if (node.tag === 'img'){ const it = imageItem(node, availW); if (it) out.push(it); return; }
  if (node.tag === 'hr'){ out.push({ kind: 'divider', color: toRgba(css['border-color'] || css['background-color']) || undefined }); return; }
  if (node.tag === 'form'){ const it = formItem(node); if (it) out.push(it); else warn('Mot <form> khong co o nhap nao - da bo qua.'); return; }
  if (node.tag === 'table'){ const it = tableItem(node); if (it){ out.push(it); return; } warn('Mot <table> khong phai bang 2 cot - da doi thanh chu thuong.'); }
  if (node.tag === 'blockquote'){ const it = quoteItem(node); if (it) out.push(it); return; }
  if (node.tag === 'ul' || node.tag === 'ol'){
    const rich = els(node).filter(li => li.tag === 'li' && (isCardish(li) || hasImage(li)));
    if (rich.length && rich.length === els(node).filter(l => l.tag === 'li').length && rich.length <= 4){
      out.push({ kind: 'row', gap: 18, cols: rich.map(li => ({ items: sub(li, Math.round(availW / rich.length)) })) });
      return;
    }
    const it = listItem(node); if (it) out.push(it); return;
  }
  if (node.tag === 'svg' || node.tag === 'canvas'){ warn('Trang co <svg>/<canvas> - Webcake khong nhan truc tiep, hay thay bang anh hoac icon.'); return; }
  if (node.tag === 'iframe' || node.tag === 'video'){ warn('Trang co video nhung - them lai bang element video cua Webcake sau khi upload.'); return; }
  if (isButtonish(node)){
    const clickable = node.tag === 'button' || node.tag === 'input'
      || (node.attrs.href && node.attrs.href !== '#') || node.attrs.onclick;
    out.push(clickable ? buttonItem(node, availW) : badgeItem(node));
    return;
  }
  if (/^h[1-6]$/.test(node.tag)){ const it = textItem(node, 'heading'); if (it) out.push(it); return; }

  const kidsEl = els(node).filter(c => !SKIP.has(c.tag) && !hidden(c.css));
  const rowish = isRowish(node);
  // Mot khoi chi chua the inline VAN co the la mot hang nut (<div class="cta-row"> voi 2 the <a>).
  // Ban truoc kiem "chi co chu" TRUOC nen hai nut do bi go phang thanh mot doan chu co link.
  const inlineOnly = !hasBlockDescendant(node) && !rowish && !kidsEl.some(isButtonish);
  if (inlineOnly){
    if (!trimText(node)) return;
    const it = textItem(node, 'text'); if (it) out.push(it); return;
  }
  if (rowish){
    const kids = els(node).filter(c => !SKIP.has(c.tag) && !hidden(c.css) && (trimText(c) || hasImage(c)));
    const gap = px(css.gap || css['column-gap'], css) || 22;
    let weights = gridCols(css, availW, gap);
    if (!weights){
      const pct = kids.map(k => { const w = String((k.css || {}).width || (k.css || {})['flex-basis'] || '');
        return /%$/.test(w) ? parseFloat(w) / 100 : null; });
      if (pct.every(x => x != null && x > 0)) weights = pct;
    }
    let ncol = weights ? weights.length : kids.length;
    // Cot khong duoc teo duoi 150px - het cho thi bot cot va cho hang sau xuong duoi, dung nhu
    // luoi CSS tu xuong dong.
    // Hang toan link/chu ngan (thanh dieu huong) duoc phep hep hon nhieu so voi hang the.
    const textOnly = kids.every(k => !hasImage(k) && !isCardish(k) && trimText(k).length <= 24);
    const minCol = textOnly ? 70 : 150;
    while (ncol > 1 && (availW - gap * (ncol - 1)) / ncol < minCol) ncol--;
    if (!weights || weights.length !== ncol) weights = new Array(ncol).fill(1 / ncol);
    const valign = /center/i.test(String(css['align-items'] || ''));
    let pushed = 0;
    for (let i = 0; i < kids.length; i += ncol){
      const chunk = kids.slice(i, i + ncol);
      const ws = weights.slice(0, chunk.length);
      const each = chunk.map((k, j) => Math.max(120, Math.round(availW * ws[j])));
      const cards = chunk.map((k, j) => isCardish(k) ? cardItem(k, each[j]) : null);
      const even = ws.every(w => Math.abs(w - ws[0]) < 0.02);
      if (chunk.length >= 2 && even && cards.every(Boolean)){
        out.push({ kind: 'cardsRow', gap: Math.round(gap),
          cards: cards.map(c => { const { kind, ...rest } = c; return rest; }) });
        pushed++; continue;
      }
      const cols = chunk.map((k, j) => ({ w: Math.round(ws[j] * 1000) / 1000, items: sub(k, each[j]) }))
        .filter(c => c.items.length);
      // Hang cuoi con dung MOT muc van phai giu be rong cua cot (1/3 luoi 3 cot) va nam ben trai,
      // giong het cach luoi CSS xuong dong - khong duoc phinh ra full chieu ngang.
      if (cols.length >= 2 || (cols.length === 1 && ncol > 1)){
        const item = { kind: 'row', gap: Math.round(gap), cols };
        if (valign) item.valign = 'center';
        out.push(item); pushed++; continue;
      }
      for (const c of cols) for (const it of c.items){ out.push(it); pushed++; }
    }
    if (pushed) return;
  }
  if (isCardish(node) && !hasImage(node) && !els(node).some(isButtonish) && !els(node).some(c => c.tag === 'form')){
    const it = cardItem(node, availW); if (it){ out.push(it); return; }
  }
  if (isCardish(node)) warn(`Khoi co nen/vien nhung ben trong co anh hoac nut nen khong goi duoc thanh 1 the - nen cua khoi do bi bo. Them lai bang cach tay neu can.`);
  for (const c of node.children || []) walkBlock(c, availW, out);
}

function sub(node, availW){
  const out = [];
  walkBlock(node, availW, out);
  return out;
}

/* ───────────────────── chia section ───────────────────── */

function pickSections(root){
  let host = root;
  for (let depth = 0; depth < 6; depth++){
    const kids = els(host).filter(c => !SKIP.has(c.tag) && !hidden(c.css));
    const real = kids.filter(c => trimText(c) || hasImage(c));
    if (real.length >= 2) return real;
    if (real.length === 1 && BLOCK.has(real[0].tag)){ host = real[0]; continue; }
    return real;
  }
  return els(host);
}

function sectionSpec(node, idx){
  const css = node.css || {};
  const elements = [];
  // Mot "section" co the CHINH NO la noi dung: doan HTML roi (kieu snippet sales page) khong co
  // the <section> nao, moi con truc tiep cua khoi bao thanh mot dai - trong do co ca <a class=cta>
  // va cac hop the. Nhung cai do phai di qua walkBlock cua CHINH NO, khong thi nut CTA bi go phang
  // thanh mot doan chu va ca dai bien thanh mot mang mau cam.
  // Phan biet DAI (band) voi THE (card): ca hai deu la div co nen + padding. Cai lam nen mot cai
  // the la BO GOC / vien / do bong; mot dai chay het chieu ngang thi khong bo goc. Thieu vach nay
  // thi <section style="background:#111;padding:60px"> cua trang that bi doc thanh mot cai the va
  // MAT nen cua ca dai - chu trang nam tren nen trang.
  const cardLike = (px(css['border-radius'], css) || 0) >= 4 || css.border != null || css['box-shadow'] != null;
  const selfContent = /^(h[1-6]|p|a|button|img|ul|ol|table|form|blockquote|hr)$/.test(node.tag)
    || isButtonish(node) || (isCardish(node) && cardLike && node.tag !== 'section');
  if (selfContent) walkBlock(node, DESK_CONTENT, elements);
  else for (const c of node.children || []) walkBlock(c, DESK_CONTENT, elements);
  if (!elements.length) return null;
  const sec = { name: sectionName(node, idx) };
  // Nen cua khoi da thanh nen cua chinh element (the/nut) roi thi khong nhan doi len ca dai nua.
  const bg = selfContent ? null : bgOf(css);
  if (bg) sec.background = bg;
  const pt = padOf(css, 'top'), pb = padOf(css, 'bottom');
  if (pt != null) sec.padTop = clampPad(pt);
  if (pb != null) sec.padBottom = clampPad(pb);
  sec.elements = elements;
  return sec;
}
const clampPad = (v) => Math.max(0, Math.min(160, Math.round(v / 4) * 4));

function sectionName(node, idx){
  const id = node.attrs.id || H.classesOf(node)[0];
  if (id) return String(id).toLowerCase().replace(/[^a-z0-9-]+/g, '-').slice(0, 28) || 'section-' + (idx + 1);
  if (node.tag === 'header') return 'header';
  if (node.tag === 'footer') return 'footer';
  return idx === 0 ? 'hero' : 'section-' + (idx + 1);
}

/* ───────────────────── theme suy ra tu trang ───────────────────── */

function inferTheme(spec, pageBg){
  const count = (arr) => { const m = new Map(); for (const v of arr) if (v) m.set(v, (m.get(v) || 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(x => x[0]); };
  const textColors = [], headColors = [], btnBgs = [], cardBgs = [];
  (function scan(items){
    for (const it of items || []){
      if (!it || typeof it !== 'object') continue;
      if (it.kind === 'text') textColors.push(it.color);
      if (it.kind === 'heading') headColors.push(it.color);
      if (it.kind === 'button' || it.kind === 'ctaBlock') btnBgs.push(it.bg);
      if (it.kind === 'card' || it.kind === 'cardsRow') cardBgs.push(it.bg);
      for (const k of ['items', 'cards', 'cols', 'rows']) if (Array.isArray(it[k])) scan(it[k]);
      if (Array.isArray(it.items)) scan(it.items);
    }
  })(spec.sections.flatMap(s => s.elements));
  const colors = {};
  const ink = count(headColors)[0], soft = count(textColors)[0], cta = count(btnBgs)[0], cardBg = count(cardBgs)[0];
  if (pageBg) colors.bg0 = pageBg;
  if (ink) colors.ink = ink;
  if (soft) colors.soft = soft;
  if (cta) colors.cta = cta;
  if (cardBg) colors.cardBg = cardBg;
  const theme = { colors };
  if (ink) theme.heading = { color: '$ink' };
  if (soft) theme.text = { color: '$soft' };
  if (cta) theme.button = { bg: '$cta' };
  if (cardBg) theme.card = { bg: '$cardBg' };
  // Engine dung TONG TOI lam mac dinh (the nen den, tieu de vang, chu xam sang). Trang nguon
  // nen SANG ma khong khai mau cho bang gia / danh gia / cam ket thi nhung khoi do se dinh nguyen
  // bo mac dinh toi kia va chim tit tren nen sang. Doi ca bo default sang tong sang mot the.
  const lp = luminance(pageBg || '');
  if (lp != null && lp > 0.5){
    const surface = cardBg || 'rgba(248,249,251,1)';
    const dark = ink || 'rgba(17,17,17,1)';
    const mid = soft || 'rgba(72,78,92,1)';
    const line = 'rgba(0,0,0,0.10)';
    const accent = cta && !/gradient/i.test(cta) ? cta : dark;
    theme.card = Object.assign({ bg: surface, titleColor: dark, textColor: mid, borderColor: line }, theme.card);
    theme.priceTable = { bg: surface, borderColor: line, lineColor: line, labelColor: mid,
      priceColor: dark, titleColor: accent, totalColor: accent, strikeColor: mid, todayColor: dark };
    theme.testimonial = { bg: surface, borderColor: line, textColor: dark, starColor: accent, authorColor: accent };
    theme.guarantee = { bg: surface, borderColor: line, titleColor: dark, textColor: mid };
    theme.badge = { bg: 'rgba(0,0,0,0.05)', color: dark, borderColor: line };
    theme.divider = { color: line };
    theme.progress = { trackColor: 'rgba(0,0,0,0.08)', labelColor: mid };
    theme.window = { bg: surface, borderColor: line };
  }
  // thay mau lap lai bang token cho spec de doc va de doi tong sau nay
  // Mot mau chi duoc MOT ten. Truoc day ink va soft cung la trang thi map bi de len nhau, nen
  // "$ink" cua tieu de bi thay bang "$soft" - doi tong sau nay la sai ca hai cho.
  const inv = new Map();
  for (const [k, v] of Object.entries(colors)) if (!inv.has(v)) inv.set(v, '$' + k);
  for (const key of Object.keys(colors)) if (inv.get(colors[key]) !== '$' + key) delete colors[key];
  for (const g of ['heading', 'text', 'button', 'card']){
    if (!theme[g]) continue;
    for (const f of Object.keys(theme[g])){
      const tokName = theme[g][f];                       // dang '$ink'...
      if (typeof tokName === 'string' && tokName[0] === '$' && colors[tokName.slice(1)] == null){
        const literal = { heading: ink, text: soft, button: cta, card: cardBg }[g];
        if (literal && inv.has(literal)) theme[g][f] = inv.get(literal); else delete theme[g][f];
      }
    }
    if (!Object.keys(theme[g]).length) delete theme[g];
  }
  // CHI token hoa ben trong element. Nen cua section giu mau THAT: no la mot quyet dinh rieng cua
  // tung dai, khong duoc dinh vao token mau chu (doi mau chu se doi luon nen ca trang).
  (function repl(o){
    if (!o || typeof o !== 'object') return;
    for (const k of Object.keys(o)){
      if (k === 'background') continue;
      const v = o[k];
      if (typeof v === 'string' && inv.has(v) && !['text', 'html', 'quote', 'title', 'label', 'price'].includes(k)) o[k] = inv.get(v);
      else if (v && typeof v === 'object') repl(v);
    }
  })(spec.sections);
  // element trung y het default cua theme -> bo bot cho spec gon
  const defOf = { heading: ['color'], text: ['color'], button: ['bg'], card: ['bg'], cardsRow: [] };
  (function prune(items){
    for (const it of items || []){
      if (!it || typeof it !== 'object') continue;
      const d = defOf[it.kind];
      if (d) for (const f of d) if (theme[it.kind] && it[f] === theme[it.kind][f]) delete it[f];
      for (const k of ['items', 'cards', 'cols']) if (Array.isArray(it[k])) prune(it[k]);
    }
  })(spec.sections.flatMap(s => s.elements));
  return theme;
}

/* ───────────────────── chay ───────────────────── */

function convert(html, opts){
  opts = opts || {};
  warns.length = 0;
  const root = parseHTML(html);
  // gom CSS: <style> trong trang + canh bao neu co stylesheet ngoai
  let cssText = '', atRules = [], scripts = [];
  (function collect(n){
    for (const c of n.children || []){
      if (c.tag === 'style') cssText += (c.children[0] && c.children[0].text) || '';
      else if (c.tag === 'link' && /stylesheet/i.test(c.attrs.rel || '') && !/fonts\.googleapis/.test(c.attrs.href || ''))
        warn(`Trang nap CSS ngoai (${String(c.attrs.href).slice(0, 60)}) - khong doc duoc, mau/co chu tu file do se khong sang.`);
      else if (c.tag === 'script' && !c.attrs.src){
        const t = (c.children[0] && c.children[0].text) || '';
        if (t.trim() && !/application\/(ld\+json|json)/i.test(c.attrs.type || '')) scripts.push(t.trim());
      }
      collect(c);
    }
  })(root);
  const { rules, atRules: at } = parseCSS(cssText);
  atRules = at;
  computeStyles(root, rules);

  const body = (function find(n){
    if (n.tag === 'body') return n;
    for (const c of n.children || []){ const r = find(c); if (r) return r; }
    return null;
  })(root) || root;

  const sections = [];
  pickSections(body).forEach((n, i) => { const s = sectionSpec(n, i); if (s) sections.push(s); });
  if (!sections.length) throw new Error('Khong boc duoc noi dung nao tu HTML nay.');

  const titleNode = (function find(n){
    if (n.tag === 'title') return n;
    for (const c of n.children || []){ const r = find(c); if (r) return r; }
    return null;
  })(root);
  const h1 = (function find(n){
    if (/^h1$/.test(n.tag)) return n;
    for (const c of n.children || []){ const r = find(c); if (r) return r; }
    return null;
  })(body);
  const metaDesc = (function find(n){
    if (n.tag === 'meta' && /^description$/i.test(n.attrs.name || '')) return n.attrs.content;
    for (const c of n.children || []){ const r = find(c); if (r) return r; }
    return null;
  })(root);

  const bodyCss = (body.css || {});
  // Doan HTML roi khong co <body>, font khai o khoi bao ben trong - lay theo font cua khoi noi dung
  // dau tien, khong thi luon bao "Montserrat" roi nguoi dung tuong da dung font goc.
  const firstFont = (function dig(n, d){
    if (d > 6 || !n) return null;
    const f = n.css && n.css['font-family'];
    if (f) return f;
    for (const c of els(n)){ const r = dig(c, d + 1); if (r) return r; }
    return null;
  })(body, 0);
  const fontFam = String(bodyCss['font-family'] || firstFont || '').split(',')[0].replace(/['"]/g, '').trim();
  const spec = {
    name: opts.name || (titleNode && trimText(titleNode)) || (h1 && trimText(h1)) || 'Trang tu HTML',
    title: (titleNode && trimText(titleNode)) || (h1 && trimText(h1)) || undefined,
    description: metaDesc || undefined,
    font: fontFam || 'Montserrat',
    sections
  };
  // Trang khong khai nen thi trinh duyet ve TRANG. Webcake thi ve TRONG SUOT - de trong la ca
  // trang tro, nen phai ghi mau trang ra cho ro.
  const pageBg = bgOf(bodyCss) || bgOf((body.parent && body.parent.css) || null) || 'rgba(255,255,255,1)';
  spec.theme = inferTheme(spec, pageBg);
  if (pageBg) for (const s of spec.sections) if (!s.background) s.background = pageBg;
  if (atRules.length){
    spec.extraCss = atRules.join('\n');
    warn('Da chuyen @keyframes/@font-face sang extraCss. Hieu ung :hover cua trang goc KHONG mang sang duoc tu dong - them lai trong Cai dat > CSS neu can.');
  }
  if (scripts.length){
    spec.extraScript = scripts.join('\n;\n');
    warn('Da chuyen <script> sang extraScript - no CHI chay khi Xem truoc / Xuat ban, khong chay trong trinh sua.');
  }
  if (!/montserrat/i.test(spec.font)) warn(`Font trang goc la "${spec.font}" - bang do chu cua engine hieu chuan cho Montserrat, hay chay preview de soi lai chieu cao.`);
  for (const k of Object.keys(spec)) if (spec[k] === undefined) delete spec[k];
  return { spec, warns: warns.slice() };
}

module.exports = { convert };

if (require.main === module){
  const argv = process.argv.slice(2);
  const flag = (n) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : undefined; };
  const args = argv.filter((a, i) => !a.startsWith('--') && argv[i - 1] !== '--name');
  const [inp, outp] = args;
  if (!inp){
    console.log('Cach dung: node webcake-from-html.js trang.html spec.json [--name "Ten trang"] [--quiet]');
    process.exit(1);
  }
  const html = fs.readFileSync(inp, 'utf8');
  const { spec, warns: w } = convert(html, { name: flag('--name') });
  const out = outp || inp.replace(/\.html?$/i, '') + '-spec.json';
  fs.writeFileSync(out, JSON.stringify(spec, null, 2));
  const nEl = spec.sections.reduce((a, s) => a + s.elements.length, 0);
  console.log(`OK spec -> ${out} | sections: ${spec.sections.length} | khoi cap 1: ${nEl}`);
  if (!argv.includes('--quiet') && w.length){
    console.log('CAN LUU Y:');
    for (const x of w) console.log('  - ' + x);
  }
}
