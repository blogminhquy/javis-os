#!/usr/bin/env node
/*
 * webcake-lint.js - kiem tra layout cua page_source Webcake (chong node, tran section, khoang chet).
 *
 *   node webcake-lint.js input(.pke|.json)
 *
 * Exit code 1 neu co ERROR (chong / tran). Warn khong lam fail.
 * Cung duoc require boi webcake-build.js (--check) va dung doc lap.
 */
'use strict';
const fs = require('fs');
const { decodeMsgpack } = require('./webcake-pke.js');

const W = { desktop: 960, mobile: 420 };
const CONTAINERS = new Set(['rectangle', 'image-block', 'form']);

function loadSource(p){
  const raw = fs.readFileSync(p, 'utf8').trim();
  let obj;
  if (/\.pke$/i.test(p) || /^[A-Za-z0-9+/=\r\n]+$/.test(raw.slice(0, 200)) && !raw.startsWith('{')) obj = decodeMsgpack(Buffer.from(raw, 'base64'));
  else obj = JSON.parse(raw);
  if (obj.source) return obj.source;
  if (obj.page) return obj;
  throw new Error('Khong tim thay page_source trong ' + p);
}

function boxOf(node, bp){
  const st = node.responsive[bp].styles;
  let h = st.height;
  if (node.type === 'text-block') h = node.responsive[bp].config.virtualHeight || 0;
  return { x: +st.left || 0, y: +st.top || 0, w: +st.width || 0, h: +h || 0,
    name: node.properties && node.properties.name || node.type, type: node.type, id: node.id };
}
const right = b => b.x + b.w, bottom = b => b.y + b.h;
function contains(a, b, tol){ // a chua b
  return b.x >= a.x - tol && b.y >= a.y - tol && right(b) <= right(a) + tol && bottom(b) <= bottom(a) + tol;
}
function overlap(a, b){
  const ix = Math.min(right(a), right(b)) - Math.max(a.x, b.x);
  const iy = Math.min(bottom(a), bottom(b)) - Math.max(a.y, b.y);
  return (ix > 4 && iy > 4) ? { ix, iy } : null;
}

/** Do sang cam nhan cua mot chuoi mau/gradient CSS. null = khong doan duoc (vd chi co url(...)). */
function lumOf(bg){
  const m = /(rgba?\(\s*\d+[^)]*\)|#[0-9a-fA-F]{3,8})/.exec(String(bg || ''));
  if (!m) return null;
  let r, g, b;
  if (m[1][0] === '#'){
    let h = m[1].slice(1);
    if (h.length === 3 || h.length === 4) h = h.split('').map(c => c + c).join('');
    r = parseInt(h.slice(0, 2), 16); g = parseInt(h.slice(2, 4), 16); b = parseInt(h.slice(4, 6), 16);
  } else {
    const p = m[1].replace(/rgba?\(|\)/g, '').split(/[\s,/]+/).filter(Boolean).map(parseFloat);
    [r, g, b] = p;
    if (p[3] != null && p[3] < 0.25) return null;   // gan nhu trong suot -> khong phai lop nen that
  }
  if (![r, g, b].every(Number.isFinite)) return null;
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
const ratioOf = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

function lintSource(source){
  const errors = [], warns = [];
  (source.page || []).forEach((sec, si) => {
    const secName = (sec.properties && sec.properties.name) || ('section#' + si);
    for (const bp of ['desktop', 'mobile']){
      const secH = +sec.responsive[bp].styles.height || 0;
      const boxes = (sec.children || []).map(n => boxOf(n, bp));
      const label = `[${bp}] ${secName}`;
      // 1. bien section
      boxes.forEach(b => {
        if (b.y < -3) errors.push(`${label}: "${b.name}" top am (${Math.round(b.y)})`);
        if (bottom(b) > secH + 3) errors.push(`${label}: "${b.name}" vuot day section (${Math.round(bottom(b))} > ${secH})`);
        if (b.x < -3) errors.push(`${label}: "${b.name}" trai am (${Math.round(b.x)})`);
        if (right(b) > W[bp] + 3) errors.push(`${label}: "${b.name}" vuot mep phai (${Math.round(right(b))} > ${W[bp]})`);
        if (b.type === 'text-block' && b.w < 50 && b.name !== 'badge') warns.push(`${label}: "${b.name}" khung chu qua hep (${Math.round(b.w)}px)`);
      });
      // 2. chong nhau (bo qua quan he chua-trong voi container)
      for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++){
        const a = boxes[i], b = boxes[j];
        const ov = overlap(a, b);
        if (!ov) continue;
        if (CONTAINERS.has(a.type) && contains(a, b, 3)) continue;
        if (CONTAINERS.has(b.type) && contains(b, a, 3)) continue;
        errors.push(`${label}: "${a.name}" chong "${b.name}" (${Math.round(ov.ix)}x${Math.round(ov.iy)}px)`);
      }
      // 3. khoang chet giua cac khoi top-level (khong nam trong container nao)
      const containers = boxes.filter(b => CONTAINERS.has(b.type));
      const flow = boxes.filter(b => !containers.some(c => c !== b && contains(c, b, 3)));
      flow.sort((a, b) => a.y - b.y);
      for (let i = 1; i < flow.length; i++){
        const gap = flow[i].y - Math.max(...flow.slice(0, i).map(bottom));
        if (gap > 140) warns.push(`${label}: khoang trong ${Math.round(gap)}px truoc "${flow[i].name}"`);
      }
      if (flow.length){
        const tail = secH - Math.max(...flow.map(bottom));
        if (tail > 170) warns.push(`${label}: thua ${Math.round(tail)}px o day section`);
      }
      // 4. TUONG PHAN: chu chim vao nen la loi hay gap nhat khi bung mau tu HTML sang, va no
      //    khong hien ra o buoc build - trang chi "trong nhu thieu chu" luc mo ra xem.
      const secBg = sec.responsive[bp].styles.background;
      const rects = (sec.children || []).filter(n => n.type === 'rectangle');
      for (const n of (sec.children || [])){
        if (n.type !== 'text-block' && n.type !== 'button') continue;
        const box = boxOf(n, bp);
        let bg = n.type === 'button' ? n.responsive[bp].styles.background : null;
        if (!bg){
          let best = null;
          for (const r of rects){
            const rb = boxOf(r, bp);
            if (!contains(rb, box, 3)) continue;
            if (!best || rb.w * rb.h < best.area){ best = { area: rb.w * rb.h, bg: r.responsive[bp].styles.background }; }
          }
          bg = best ? best.bg : secBg;
        }
        const lb = lumOf(bg), lt = lumOf(n.responsive[bp].styles.color);
        if (lb == null || lt == null) continue;
        const cr = ratioOf(lb, lt);
        const what = `"${box.name}" (chu ${n.responsive[bp].styles.color} tren nen ${String(bg).slice(0, 42)})`;
        if (cr < 1.6) errors.push(`${label}: ${what} gan nhu KHONG DOC DUOC, do tuong phan ${cr.toFixed(2)}:1`);
        else if (cr < 2.8) warns.push(`${label}: ${what} tuong phan thap ${cr.toFixed(2)}:1`);
      }
      // 5. Section khong khai nen: Webcake ve trong suot, ca dai trang tro
      if (bp === 'desktop' && !secBg) warns.push(`${label}: section khong co nen (Webcake se ve trong suot)`);
      // 6. Anh khong dung URL cong khai thi ban chay that se trong
      for (const n of (sec.children || [])){
        if (n.type !== 'image-block') continue;
        const src = (n.specials && n.specials.src) || '';
        if (bp === 'desktop' && !/^https?:\/\//i.test(src))
          warns.push(`${label}: anh "${String(src).slice(0, 50)}" khong phai URL cong khai - upload roi thay src`);
      }
    }
  });
  return { errors, warns };
}

function formatReport(rep){
  const lines = [];
  lines.push(`LINT: ${rep.errors.length} loi, ${rep.warns.length} canh bao`);
  rep.errors.forEach(e => lines.push('  ERROR ' + e));
  rep.warns.forEach(w => lines.push('  warn  ' + w));
  return lines.join('\n');
}

module.exports = { lintSource, formatReport, loadSource, lumOf, ratioOf };

if (require.main === module){
  const p = process.argv[2];
  if (!p){ console.log('Cach dung: node webcake-lint.js input(.pke|.json)'); process.exit(1); }
  const rep = lintSource(loadSource(p));
  console.log(formatReport(rep));
  process.exit(rep.errors.length ? 1 : 0);
}
