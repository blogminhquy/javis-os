#!/usr/bin/env node
/*
 * webcake-preview.js - render page_source Webcake thanh HTML tinh de soi bang mat TRUOC khi upload.
 *
 *   node webcake-preview.js input(.pke|.json) [outBase] [--debug]
 *
 * Xuat 2 file: <outBase>.desktop.html (960) va <outBase>.mobile.html (420), mo phong dung canvas
 * tuyet doi cua Webcake (font Montserrat, line-height 1.5, extra_css/extra_script nhu khi publish).
 * --debug: ve khung dut net quanh text-block + hop virtualHeight de doi chieu chieu cao du tinh.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { decodeMsgpack } = require('./webcake-pke.js');

const W = { desktop: 960, mobile: 420 };

function loadSource(p){
  const raw = fs.readFileSync(p, 'utf8').trim();
  let obj;
  if (raw.startsWith('{')) obj = JSON.parse(raw);
  else obj = decodeMsgpack(Buffer.from(raw, 'base64'));
  if (obj.source) return obj.source;
  if (obj.page) return obj;
  throw new Error('Khong tim thay page_source trong ' + p);
}

const px = v => (v == null ? '0' : String(v).match(/[a-z%]/i) ? String(v) : v + 'px');
function esc(s){ return String(s == null ? '' : s).replace(/&(?![a-z#0-9]+;)/gi, '&amp;'); }

function styleCommon(st){
  let s = `position:absolute;left:${px(st.left)};top:${px(st.top)};width:${px(st.width)};`;
  if (st.zIndex != null && st.zIndex !== '') s += `z-index:${st.zIndex};`;
  return s;
}
function borderCss(st){
  const bw = parseFloat(st.borderWidth) || 0;
  let s = '';
  if (bw) s += `border:${bw}px ${st.borderStyle || 'solid'} ${st.borderColor || 'transparent'};`;
  if (st.borderRadius) s += `border-radius:${px(st.borderRadius)};`;
  if (st.boxShadow) s += `box-shadow:${st.boxShadow};`;
  if (st.filter) s += `filter:${st.filter};`;
  return s;
}

function renderNode(node, bp, debug, relTo){
  const st = node.responsive[bp].styles;
  const cfg = node.responsive[bp].config || {};
  const out = [];
  const base = styleCommon(st);
  const meta = `data-type="${node.type}" data-name="${node.properties?.name || ''}"`;
  // custom_css cua Webcake (line-height, letter-spacing, gradient, shadow...) phai duoc ve o day,
  // khong thi preview noi doi: nhin thi dep ma len that lai khac.
  const custom = (node.specials && node.specials.customAdvance && node.specials.custom_css) || '';
  if (node.type === 'text-block'){
    const dbg = debug ? 'outline:1px dashed rgba(255,90,90,0.5);' : '';
    out.push(`<div class="tb" ${meta} data-vh="${cfg.virtualHeight || 0}" style="${base}font-size:${px(st.fontSize)};color:${st.color};font-weight:${st.fontWeight || 'normal'};text-align:${st.textAlign || 'left'};line-height:1.5;${dbg}${custom}">${node.specials.text}</div>`);
    if (debug && cfg.virtualHeight) out.push(`<div style="${base}height:${cfg.virtualHeight}px;outline:1px dashed rgba(80,200,255,0.45);pointer-events:none;"></div>`);
  } else if (node.type === 'rectangle'){
    out.push(`<div ${meta} style="${base}height:${px(st.height)};background:${st.background || 'transparent'};${borderCss(st)}${custom}"></div>`);
  } else if (node.type === 'image-block'){
    out.push(`<div ${meta} style="${base}height:${px(st.height)};background:${st.background};${borderCss(st)}${custom}"></div>`);
  } else if (node.type === 'button'){
    out.push(`<div ${meta} style="${base}height:${px(st.height)};background:${st.background};color:${st.color};font-size:${px(st.fontSize)};font-weight:bold;${borderCss(st)}display:flex;align-items:center;justify-content:center;text-align:center;padding:0 14px;box-sizing:border-box;cursor:pointer;${custom}">${node.specials.text}</div>`);
  } else if (node.type === 'form'){
    out.push(`<div ${meta} style="${base}height:${px(st.height)};${borderCss(st)}">`);
    (node.children || []).forEach(ch => out.push(renderNode(ch, bp, debug, true)));
    out.push('</div>');
  } else if (node.type === 'input'){
    out.push(`<div ${meta} style="${base}height:${px(st.height)};background:${st.background || '#fff'};${borderCss(st)}display:flex;align-items:center;padding:0 12px;box-sizing:border-box;color:#9a9a9a;font-size:14px;">${node.specials?.field_placeholder || ''}</div>`);
  } else {
    out.push(`<div ${meta} style="${base}height:${px(st.height)};outline:1px dotted orange;font-size:10px;color:orange;">${node.type}</div>`);
  }
  return out.join('\n');
}

function render(source, bp, debug){
  const width = (source.settings.width_section && source.settings.width_section[bp]) || W[bp];
  const secs = (source.page || []).map((sec, i) => {
    const st = sec.responsive[bp].styles;
    const dbg = debug ? 'outline:1px dashed rgba(120,120,120,0.35);' : '';
    const kids = (sec.children || []).map(n => renderNode(n, bp, debug)).join('\n');
    return `<div class="sec" data-idx="${i}" data-name="${sec.properties?.name || ''}" style="position:relative;width:${width}px;height:${st.height}px;background:${st.background || 'transparent'};${dbg}">\n${kids}\n</div>`;
  }).join('\n');
  const font = source.settings.fontGeneral || 'Montserrat';
  return `<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>preview ${bp} - ${esc(source.settings.title || '')}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=${encodeURIComponent(font)}:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;0,900;1,400;1,600&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;padding:0;background:#161616;}
  .canvas{width:${width}px;margin:18px auto;box-shadow:0 0 0 1px #2c2c2c, 0 20px 60px rgba(0,0,0,0.5);}
  .canvas, .canvas *{font-family:'${font}', sans-serif;}
  .tb{word-wrap:break-word;}
  .bar{font:12px monospace;color:#888;text-align:center;padding:10px;}
${source.settings.extra_css || ''}
</style></head>
<body>
<div class="bar">${bp} ${width}px - ${esc(source.settings.title || '')}</div>
<div class="canvas">
${secs}
</div>
<script>${source.settings.extra_script || ''}<\/script>
</body></html>`;
}

module.exports = { render, loadSource };

if (require.main === module){
  const args = process.argv.slice(2).filter(a => a !== '--debug');
  const debug = process.argv.includes('--debug');
  const inp = args[0];
  if (!inp){ console.log('Cach dung: node webcake-preview.js input(.pke|.json) [outBase] [--debug]'); process.exit(1); }
  const base = args[1] || inp.replace(/\.(pke|json)$/i, '') + '-preview';
  const source = loadSource(inp);
  for (const bp of ['desktop', 'mobile']){
    const out = `${base}.${bp}.html`;
    fs.writeFileSync(out, render(source, bp, debug));
    console.log('OK preview ->', out);
  }
}
