#!/usr/bin/env node
/*
 * webcake-html.js - doc HTML that (khong phu thuoc goi ngoai): tokenizer + cascade CSS + style tinh toan.
 *
 * Chi lam MOT viec: bien chuoi HTML thanh cay node co `css` (desktop) va `cssM` (ghi de trong
 * @media max-width mobile) da resolve day du - ke ca thua ke (color/font-size/font-family/
 * text-align/font-weight/line-height/font-style). webcake-from-html.js dung cay nay de dung spec.
 *
 * Vi sao viet tay chu khong dung jsdom/cheerio: skill duoc ship vao brain cua nguoi dung va chay
 * bang `node tools/...` tran, khong co buoc `npm install` nao. Mot phu thuoc ngoai = skill chet
 * o may khong co mang.
 */
'use strict';

const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
  'param', 'source', 'track', 'wbr']);
const RAW = new Set(['script', 'style', 'textarea', 'title']);
// The tu dong dong khi gap the anh em cung loai (hoac the ket thuc cua cha)
const AUTO_CLOSE = {
  p: new Set(['p', 'div', 'section', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'form', 'blockquote', 'pre', 'hr']),
  li: new Set(['li']), dt: new Set(['dt', 'dd']), dd: new Set(['dt', 'dd']),
  td: new Set(['td', 'th', 'tr']), th: new Set(['td', 'th', 'tr']), tr: new Set(['tr']),
  option: new Set(['option']), thead: new Set(['tbody', 'tfoot']), tbody: new Set(['tbody', 'tfoot'])
};

/* ───────────────────────── 1. TOKENIZER → CAY ───────────────────────── */

function parseAttrs(s){
  const attrs = {};
  const re = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>`]+)))?/g;
  let m;
  while ((m = re.exec(s)) !== null){
    const k = m[1].toLowerCase();
    if (k === '/') continue;
    attrs[k] = m[2] != null ? m[2] : m[3] != null ? m[3] : m[4] != null ? m[4] : '';
  }
  return attrs;
}

function parseHTML(src){
  const root = { tag: '#root', attrs: {}, children: [], parent: null };
  let cur = root, i = 0;
  const push = (n) => { n.parent = cur; cur.children.push(n); return n; };
  while (i < src.length){
    const lt = src.indexOf('<', i);
    if (lt < 0){ addText(src.slice(i)); break; }
    if (lt > i) addText(src.slice(i, lt));
    if (src.startsWith('<!--', lt)){
      const e = src.indexOf('-->', lt); i = e < 0 ? src.length : e + 3; continue;
    }
    if (src.startsWith('<!', lt)){                       // doctype / CDATA
      const e = src.indexOf('>', lt); i = e < 0 ? src.length : e + 1; continue;
    }
    const gt = findTagEnd(src, lt);
    if (gt < 0){ addText(src.slice(lt)); break; }
    const raw = src.slice(lt + 1, gt);
    if (raw[0] === '/'){                                  // the dong
      const name = raw.slice(1).trim().toLowerCase();
      let p = cur;
      while (p && p !== root && p.tag !== name) p = p.parent;
      if (p && p !== root) cur = p.parent;
      i = gt + 1; continue;
    }
    const sp = raw.search(/[\s/>]/);
    const name = (sp < 0 ? raw : raw.slice(0, sp)).toLowerCase();
    const attrs = parseAttrs(sp < 0 ? '' : raw.slice(sp));
    // tu dong dong the con dang mo (vd <p>a<p>b)
    while (AUTO_CLOSE[cur.tag] && AUTO_CLOSE[cur.tag].has(name)) cur = cur.parent;
    const node = push({ tag: name, attrs, children: [] });
    i = gt + 1;
    if (VOID.has(name) || /\/\s*$/.test(raw)) continue;
    if (RAW.has(name)){
      const close = new RegExp('</\\s*' + name + '\\s*>', 'i');
      const rest = src.slice(i); const m = close.exec(rest);
      const body = m ? rest.slice(0, m.index) : rest;
      node.children.push({ tag: '#text', text: body, parent: node, raw: true });
      i += m ? m.index + m[0].length : rest.length;
      continue;
    }
    cur = node;
  }
  function addText(t){
    if (!t) return;
    push({ tag: '#text', text: t, children: [] });
  }
  return root;
}

// Tim '>' ket thuc the, bo qua '>' nam trong gia tri thuoc tinh co nhay
function findTagEnd(src, from){
  let q = null;
  for (let i = from + 1; i < src.length; i++){
    const c = src[i];
    if (q){ if (c === q) q = null; continue; }
    if (c === '"' || c === "'") { q = c; continue; }
    if (c === '>') return i;
  }
  return -1;
}

/* ───────────────────────── 2. CSS ───────────────────────── */

function splitTop(s, sep){
  const out = []; let d = 0, q = null, cur = '';
  for (const c of s){
    if (q){ cur += c; if (c === q) q = null; continue; }
    if (c === '"' || c === "'"){ q = c; cur += c; continue; }
    if (c === '(' || c === '[') d++;
    if (c === ')' || c === ']') d--;
    if (c === sep && d === 0){ out.push(cur); cur = ''; continue; }
    cur += c;
  }
  out.push(cur);
  return out.map(x => x.trim()).filter(Boolean);
}

function parseDecls(body){
  const o = {};
  for (const part of splitTop(body, ';')){
    const c = part.indexOf(':');
    if (c < 0) continue;
    const k = part.slice(0, c).trim().toLowerCase();
    let v = part.slice(c + 1).trim();
    if (/!important$/i.test(v)) v = v.replace(/\s*!important$/i, '').trim();
    if (k) o[k] = v;
  }
  return o;
}

function specificity(sel){
  let a = 0, b = 0, c = 0;
  const s = sel.replace(/\[[^\]]*\]/g, m => { b++; return ' '; })
               .replace(/::[\w-]+/g, () => { c++; return ' '; })
               .replace(/:[\w-]+(\([^)]*\))?/g, () => { b++; return ' '; });
  for (const m of s.match(/#[\w-]+/g) || []) a++;
  for (const m of s.match(/\.[\w-]+/g) || []) b++;
  for (const m of s.replace(/[#.][\w-]+/g, ' ').match(/\b[a-zA-Z][\w-]*\b/g) || []) c++;
  return a * 10000 + b * 100 + c;
}

const REF_W = { desktop: 1280, mobile: 420 };   // be ngang tham chieu de danh gia @media

/**
 * Dieu kien @media co dung o be ngang `width` khong.
 * Vi sao phai lam that: trang that hay dung @media(max-width:980px). Ban truoc chi so voi mot
 * nguong cung 820 nen khoi do bi xep nham vao DESKTOP - the la `.grid3{grid-template-columns:1fr}`
 * va `.links{display:none}` cua ban MOBILE de len ban desktop: luoi 3 cot thanh 1 cot, thanh
 * dieu huong bien mat. Do la loi lam ban dung ra lech nhieu nhat.
 */
function mediaMatch(cond, width){
  const q = String(cond || '').replace(/^@media\s*/i, '');
  return splitTop(q, ',').some(one => {
    if (/\bprint\b/i.test(one)) return false;
    let ok = true;
    const re = /\(\s*(min|max)-width\s*:\s*([\d.]+)(px|r?em)?\s*\)/gi;
    let m;
    while ((m = re.exec(one)) !== null){
      let v = parseFloat(m[2]);
      if (m[3] && /em$/i.test(m[3])) v *= 16;
      if (m[1].toLowerCase() === 'min' ? !(width >= v) : !(width <= v)) ok = false;
    }
    return ok;
  }) || !splitTop(q, ',').length;
}

/** Tra { rules:[{sel,decls,spec,order,bps}], atRules:string[] } */
function parseCSS(text, bpDefault){
  const rules = [], atRules = [];
  let order = 0;
  const src = String(text || '').replace(/\/\*[\s\S]*?\*\//g, '');
  let i = 0;
  function block(from){                    // tra vi tri sau '}' cua khoi bat dau tai '{' o `from`
    let d = 0;
    for (let j = from; j < src.length; j++){
      if (src[j] === '{') d++;
      else if (src[j] === '}'){ d--; if (!d) return j; }
    }
    return src.length - 1;
  }
  function walk(chunk, bps){
    let k = 0;
    while (k < chunk.length){
      const br = chunk.indexOf('{', k);
      if (br < 0) break;
      const head = chunk.slice(k, br).trim();
      let d = 0, end = chunk.length - 1;
      for (let j = br; j < chunk.length; j++){
        if (chunk[j] === '{') d++;
        else if (chunk[j] === '}'){ d--; if (!d){ end = j; break; } }
      }
      const body = chunk.slice(br + 1, end);
      if (head.startsWith('@')){
        const at = head.slice(1).split(/[\s(]/)[0].toLowerCase();
        if (at === 'media'){
          const next = bps.filter(b => mediaMatch(head, REF_W[b]));
          if (next.length) walk(body, next);
        } else if (at === 'supports'){
          walk(body, bps);
        } else {
          atRules.push(head + '{' + body + '}');   // @keyframes / @font-face → giu nguyen cho extraCss
        }
      } else {
        const decls = parseDecls(body);
        for (const sel of splitTop(head, ',')){
          rules.push({ sel, decls, spec: specificity(sel), order: order++, bps: bps.slice() });
        }
      }
      k = end + 1;
    }
  }
  walk(src, bpDefault || ['desktop']);
  return { rules, atRules };
}

/* ───────────────────────── 3. KHOP SELECTOR ───────────────────────── */

const PSEUDO_STATE = /:(hover|focus|active|visited|focus-within|focus-visible|target|checked|disabled)\b/i;

function classesOf(node){
  return String((node.attrs && node.attrs.class) || '').split(/\s+/).filter(Boolean);
}

function matchCompound(node, comp){
  if (!node || node.tag === '#text' || node.tag === '#root') return false;
  // :root la noi bang mau (--bien CSS) hay nam nhat trong trang that - bo qua no la mat sach palette
  if (/:root\b/.test(comp) && node.tag !== 'html') return false;
  let s = comp.replace(/::?[\w-]+(\([^)]*\))?/g, '');       // bo pseudo (da loc state o tren)
  const parts = s.match(/([#.]?[\w-]+|\[[^\]]*\])/g) || [];
  // ':root' bi buoc pseudo o tren cat het chu -> phai tra ve dung o day, khong thi bang mau bien
  // CSS (thu hay nam trong :root) khong bao gio duoc doc.
  if (!parts.length) return /:root\b/.test(comp) ? true : (s === '*' || comp === '*');
  for (const p of parts){
    if (p[0] === '#'){ if ((node.attrs.id || '') !== p.slice(1)) return false; }
    else if (p[0] === '.'){ if (!classesOf(node).includes(p.slice(1))) return false; }
    else if (p[0] === '['){
      const m = /\[([\w-]+)(?:([~^$*|]?=)\s*"?([^"\]]*)"?)?\]/.exec(p);
      if (!m) return false;
      const v = node.attrs[m[1].toLowerCase()];
      if (v === undefined) return false;
      if (m[2] === '=' && v !== m[3]) return false;
      if (m[2] === '*=' && !String(v).includes(m[3])) return false;
      if (m[2] === '^=' && !String(v).startsWith(m[3])) return false;
    }
    else if (p !== '*' && node.tag !== p.toLowerCase()) return false;
  }
  return true;
}

function matchSelector(node, sel){
  if (PSEUDO_STATE.test(sel)) return false;                 // :hover... khong thuoc trang thai tinh
  const toks = sel.trim().split(/\s*(>|\+|~)\s*|\s+/).filter(Boolean);
  let idx = toks.length - 1;
  if (!matchCompound(node, toks[idx])) return false;
  let cur = node;
  idx--;
  while (idx >= 0){
    const comb = ['>', '+', '~'].includes(toks[idx]) ? toks[idx--] : ' ';
    const want = toks[idx--];
    if (want === undefined) return false;
    if (comb === '>'){
      cur = cur.parent;
      if (!matchCompound(cur, want)) return false;
    } else if (comb === '+' || comb === '~'){
      const sibs = (cur.parent && cur.parent.children || []).filter(c => c.tag !== '#text');
      const at = sibs.indexOf(cur);
      let ok = false;
      for (let j = at - 1; j >= 0; j--){
        if (matchCompound(sibs[j], want)){ ok = true; cur = sibs[j]; break; }
        if (comb === '+') break;
      }
      if (!ok) return false;
    } else {
      let p = cur.parent, ok = false;
      while (p){ if (matchCompound(p, want)){ ok = true; cur = p; break; } p = p.parent; }
      if (!ok) return false;
    }
  }
  return true;
}

/* ───────────────────────── 4. STYLE TINH TOAN ───────────────────────── */

const INHERITED = ['color', 'font-family', 'font-size', 'font-weight', 'font-style', 'text-align',
  'line-height', 'letter-spacing', 'text-transform', 'font-variant', 'list-style-type'];

/** Thay var(--ten, du-phong) bang gia tri that. Bien CSS thua ke nen map duoc gom doc theo cay. */
function resolveVars(v, vars, depth){
  if (typeof v !== 'string' || v.indexOf('var(') < 0) return v;
  if ((depth || 0) > 8) return v;
  return v.replace(/var\(\s*(--[\w-]+)\s*(?:,\s*([^]*?))?\)/g, (m, name, fb) => {
    if (vars[name] != null) return resolveVars(vars[name], vars, (depth || 0) + 1);
    return fb != null ? resolveVars(fb.trim(), vars, (depth || 0) + 1) : m;
  });
}

const NAMED = { black: '0,0,0', white: '255,255,255', red: '255,0,0', green: '0,128,0', blue: '0,0,255',
  gray: '128,128,128', grey: '128,128,128', silver: '192,192,192', yellow: '255,255,0', orange: '255,165,0',
  purple: '128,0,128', pink: '255,192,203', brown: '165,42,42', navy: '0,0,128', teal: '0,128,128',
  lime: '0,255,0', cyan: '0,255,255', aqua: '0,255,255', maroon: '128,0,0', olive: '128,128,0',
  gold: '255,215,0', crimson: '220,20,60', indigo: '75,0,130', violet: '238,130,238',
  transparent: '0,0,0,0', whitesmoke: '245,245,245', ghostwhite: '248,248,255', darkslategray: '47,79,79',
  dimgray: '105,105,105', lightgray: '211,211,211', lightgrey: '211,211,211', beige: '245,245,220',
  ivory: '255,255,240', khaki: '240,230,140', salmon: '250,128,114', tomato: '255,99,71',
  coral: '255,127,80', turquoise: '64,224,208', skyblue: '135,206,235', steelblue: '70,130,180',
  midnightblue: '25,25,112', seagreen: '46,139,87', forestgreen: '34,139,34', darkgreen: '0,100,0' };

/** Chuan hoa moi dang mau CSS ve rgba(r,g,b,a). Khong nhan ra -> tra null. */
function toRgba(v){
  if (!v) return null;
  const s = String(v).trim().toLowerCase();
  if (s === 'inherit' || s === 'currentcolor' || s === 'initial' || s === 'unset') return null;
  if (NAMED[s]){ const p = NAMED[s].split(','); return `rgba(${p[0]},${p[1]},${p[2]},${p[3] != null ? p[3] : 1})`; }
  let m = /^#([0-9a-f]{3,8})$/i.exec(s);
  if (m){
    let h = m[1];
    if (h.length === 3 || h.length === 4) h = h.split('').map(c => c + c).join('');
    if (h.length !== 6 && h.length !== 8) return null;
    const a = h.length === 8 ? +(parseInt(h.slice(6, 8), 16) / 255).toFixed(3) : 1;
    return `rgba(${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)},${a})`;
  }
  m = /^rgba?\(([^)]+)\)$/.exec(s);
  if (m){
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(x => x.trim());
    if (p.length < 3) return null;
    const n = (x) => x.endsWith('%') ? Math.round(parseFloat(x) * 2.55) : Math.round(parseFloat(x));
    const a = p[3] == null ? 1 : (p[3].endsWith('%') ? parseFloat(p[3]) / 100 : parseFloat(p[3]));
    return `rgba(${n(p[0])},${n(p[1])},${n(p[2])},${isNaN(a) ? 1 : a})`;
  }
  m = /^hsla?\(([^)]+)\)$/.exec(s);
  if (m){
    const p = m[1].split(/[\s,/]+/).filter(Boolean);
    const h = parseFloat(p[0]) / 360, sa = parseFloat(p[1]) / 100, l = parseFloat(p[2]) / 100;
    const a = p[3] == null ? 1 : (p[3].endsWith('%') ? parseFloat(p[3]) / 100 : parseFloat(p[3]));
    const q = l < 0.5 ? l * (1 + sa) : l + sa - l * sa, pp = 2 * l - q;
    const hue = (t) => { if (t < 0) t += 1; if (t > 1) t -= 1;
      if (t < 1 / 6) return pp + (q - pp) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return pp + (q - pp) * (2 / 3 - t) * 6;
      return pp; };
    const r = Math.round(hue(h + 1 / 3) * 255), g = Math.round(hue(h) * 255), b = Math.round(hue(h - 1 / 3) * 255);
    return `rgba(${r},${g},${b},${isNaN(a) ? 1 : a})`;
  }
  return null;
}

/** Do sang cam nhan (0..1) - dung de chon chu sang hay chu toi tren mot dai mau. */
function luminance(rgba){
  const m = /rgba?\(([^)]+)\)/.exec(String(rgba || ''));
  if (!m) return null;
  const [r, g, b] = m[1].split(',').map(x => parseFloat(x) / 255);
  const f = (c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

const ABS_FS = { 'xx-small': 9, 'x-small': 10, small: 13, medium: 16, large: 18,
  'x-large': 24, 'xx-large': 32, smaller: 13, larger: 19 };

/** Tinh gia tri so cua mot bieu thuc calc() don gian (+ - * / va ngoac). null neu chiu. */
function evalCalc(expr, parentFs, pct100){
  const toks = String(expr).match(/(\d*\.?\d+(?:px|pt|rem|em|%|vw|vh)?|[()+\-*/])/g);
  if (!toks) return null;
  let i = 0;
  const peek = () => toks[i];
  function prim(){
    if (peek() === '('){ i++; const v = sum(); if (peek() === ')') i++; return v; }
    if (peek() === '-'){ i++; const v = prim(); return v == null ? null : -v; }
    const t = toks[i++];
    return toPx(t, parentFs, pct100);
  }
  function mul(){
    let a = prim();
    while (peek() === '*' || peek() === '/'){
      const op = toks[i++], b = prim();
      if (a == null || b == null) return null;
      a = op === '*' ? a * b : (b ? a / b : null);
    }
    return a;
  }
  function sum(){
    let a = mul();
    while (peek() === '+' || peek() === '-'){
      const op = toks[i++], b = mul();
      if (a == null || b == null) return null;
      a = op === '+' ? a + b : a - b;
    }
    return a;
  }
  const r = sum();
  return Number.isFinite(r) ? r : null;
}

/** Doi mot do dai CSS sang px. base = font-size cua chinh element (cho em), rem = 16. */
function toPx(v, parentFs, pct100){
  if (v == null) return null;
  const s = String(v).trim().toLowerCase();
  if (ABS_FS[s] != null) return ABS_FS[s];
  // clamp/min/max/calc: trang that dung day (vd font-size:clamp(28px,4vw,42px)). Khong tinh duoc
  // la mat luon co chu -> roi ve co mac dinh, chu to nho lung tung so voi ban goc.
  let fn = /^(clamp|min|max|calc)\((.*)\)$/is.exec(s);
  if (fn){
    const name = fn[1];
    if (name === 'calc') return evalCalc(fn[2], parentFs, pct100);
    const args = splitTop(fn[2], ',').map(a => /^calc\(/i.test(a) ? evalCalc(a.replace(/^calc\(|\)$/gi, ''), parentFs, pct100) : toPx(a, parentFs, pct100));
    if (args.some(a => a == null)) return null;
    if (name === 'min') return Math.min(...args);
    if (name === 'max') return Math.max(...args);
    return Math.min(Math.max(args[1], args[0]), args[2]);      // clamp(min, val, max)
  }
  let m = /^(-?[\d.]+)(px|pt|rem|em|%|vw|vh)?$/.exec(s);
  if (!m) return null;
  const n = parseFloat(m[1]);
  switch (m[2]){
    case undefined: case '': case 'px': return n;
    case 'pt': return n * 4 / 3;
    case 'rem': return n * 16;
    case 'em': return n * (parentFs || 16);
    case '%': return pct100 != null ? n * pct100 / 100 : (parentFs != null ? n * parentFs / 100 : null);
    case 'vw': return n * 9.6;      // canvas desktop 960
    case 'vh': return n * 8;        // uoc luong khung 800
    default: return null;
  }
}

/**
 * Gan `css` (desktop) + `cssM` (chi cac khai bao bi @media mobile ghi de) cho moi element.
 * Thu tu cascade: rule khop (theo specificity roi thu tu xuat hien) → thuoc tinh style= → thua ke.
 */
function computeStyles(root, rules){
  const desk = rules.filter(r => r.bps.includes('desktop'));
  const mob = rules.filter(r => r.bps.includes('mobile') && !r.bps.includes('desktop'));
  (function walk(node, parentCss){
    if (node.tag === '#text' || node.tag === '#root'){
      const kids = node.children || [];
      for (const c of kids) walk(c, parentCss);
      if (node.tag !== '#root') return;
      return;
    }
    const own = {};
    const hits = desk.filter(r => matchSelector(node, r.sel))
      .sort((a, b) => a.spec - b.spec || a.order - b.order);
    for (const r of hits) Object.assign(own, r.decls);
    if (node.attrs.style) Object.assign(own, parseDecls(node.attrs.style));
    // thuoc tinh trinh bay co (width/height/align/bgcolor) van gap trong HTML that
    if (node.attrs.width && !own.width) own.width = /^\d+$/.test(node.attrs.width) ? node.attrs.width + 'px' : node.attrs.width;
    if (node.attrs.height && !own.height) own.height = /^\d+$/.test(node.attrs.height) ? node.attrs.height + 'px' : node.attrs.height;
    if (node.attrs.align && !own['text-align']) own['text-align'] = node.attrs.align;
    if (node.attrs.bgcolor && !own['background-color']) own['background-color'] = node.attrs.bgcolor;

    const css = {};
    for (const k of INHERITED) if (parentCss[k] != null) css[k] = parentCss[k];
    const vars = Object.assign({}, parentCss.__vars);
    for (const k of Object.keys(own)) if (k.startsWith('--')) vars[k] = own[k];
    if (/^(h1|h2|h3|h4|h5|h6|b|strong|th)$/.test(node.tag) && own['font-weight'] == null) css['font-weight'] = '700';
    if (/^(i|em|blockquote)$/.test(node.tag) && own['font-style'] == null) css['font-style'] = 'italic';
    Object.assign(css, own);

    for (const k of Object.keys(css)) if (!k.startsWith('--')) css[k] = resolveVars(css[k], vars, 0);
    css.__vars = vars;

    const pfs = parentCss.__fs || 16;
    css.__fs = toPx(css['font-size'], pfs, pfs);
    if (css.__fs == null){
      const DEF = { h1: 32, h2: 24, h3: 18.72, h4: 16, h5: 13.28, h6: 10.72, small: pfs * 0.8 };
      css.__fs = DEF[node.tag] != null && own['font-size'] == null && parentCss['font-size'] == null
        ? DEF[node.tag] : pfs;
    }
    node.css = css;

    const mhits = mob.filter(r => matchSelector(node, r.sel))
      .sort((a, b) => a.spec - b.spec || a.order - b.order);
    if (mhits.length){
      const mo = {};
      for (const r of mhits) Object.assign(mo, r.decls);
      node.cssM = mo;
    }
    for (const c of node.children || []) walk(c, css);
  })(root, { __fs: 16, color: 'rgb(0,0,0)', 'text-align': 'left' });   // mac dinh cua trinh duyet
  return root;
}

/* ───────────────────────── 5. TIEN ICH CAY ───────────────────────── */

const els = (n) => (n.children || []).filter(c => c.tag !== '#text');
function textOf(node){
  if (node.tag === '#text') return decodeEntities(node.text);
  if (node.tag === 'br') return '\n';
  if (node.tag === 'script' || node.tag === 'style' || node.tag === 'noscript') return '';
  return (node.children || []).map(textOf).join('');
}
const trimText = (n) => textOf(n).replace(/\s+/g, ' ').trim();

const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', mdash: '-', ndash: '-',
  hellip: '…', rsquo: '’', lsquo: '‘', rdquo: '”', ldquo: '“', times: '×', check: '✓', bull: '•',
  middot: '·', copy: '©', reg: '®', trade: '™', deg: '°', laquo: '«', raquo: '»' };
function decodeEntities(s){
  return String(s == null ? '' : s).replace(/&(#x?[0-9a-f]+|[a-z]+);/gi, (m, c) => {
    if (c[0] === '#'){
      const n = c[1] === 'x' || c[1] === 'X' ? parseInt(c.slice(2), 16) : parseInt(c.slice(1), 10);
      return Number.isFinite(n) ? String.fromCodePoint(n) : m;
    }
    const k = c.toLowerCase();
    return ENT[k] != null ? ENT[k] : m;
  });
}

module.exports = { parseHTML, parseCSS, computeStyles, matchSelector, matchCompound, specificity,
  toRgba, toPx, evalCalc, resolveVars, mediaMatch, luminance, textOf, trimText, els, decodeEntities,
  parseDecls, classesOf, splitTop, REF_W, VOID, RAW };
