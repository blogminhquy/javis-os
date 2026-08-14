#!/usr/bin/env node
/*
 * webcake-pke.js - Bộ giải mã / mã hóa file .pke của Webcake (KHÔNG cần cài gói ngoài).
 *
 * .pke = base64( MessagePack( { source, name, engine, owner_id, email, data_set_id } ) )
 *   source = { settings, popup, page, options, cartConfigs }  ← chính là "page_source" của editor Webcake
 *
 * Dùng:
 *   node webcake-pke.js decode  input.pke  [output.json]   # PKE  -> JSON (đọc/sửa được)
 *   node webcake-pke.js encode  input.json [output.pke]    # JSON -> PKE  (upload lại Webcake)
 *
 * File JSON cho lệnh encode có thể là:
 *   (a) nguyên envelope {source,name,engine,...}  — giữ nguyên mọi meta, HOẶC
 *   (b) chỉ mình "source" {settings,page,...}      — sẽ tự bọc envelope (cần --name / --owner nếu muốn).
 */
'use strict';
const fs = require('fs');

/* ---------- MessagePack decode ---------- */
function decodeMsgpack(buf){
  let p=0;
  const rd=n=>{const s=buf.toString('utf8',p,p+n);p+=n;return s;};
  const arr=n=>{const a=[];for(let i=0;i<n;i++)a.push(dec());return a;};
  const map=n=>{const o={};for(let i=0;i<n;i++){const k=dec();o[k]=dec();}return o;};
  function dec(){
    const c=buf[p++];
    if(c<0x80)return c; if(c>=0xe0)return c-0x100;
    if(c<=0x8f)return map(c-0x80); if(c<=0x9f)return arr(c-0x90); if(c<=0xbf)return rd(c-0xa0);
    switch(c){
      case 0xc0:return null; case 0xc2:return false; case 0xc3:return true;
      case 0xcc:{const v=buf.readUInt8(p);p+=1;return v;}
      case 0xcd:{const v=buf.readUInt16BE(p);p+=2;return v;}
      case 0xce:{const v=buf.readUInt32BE(p);p+=4;return v;}
      case 0xcf:{const v=Number(buf.readBigUInt64BE(p));p+=8;return v;}
      case 0xd0:{const v=buf.readInt8(p);p+=1;return v;}
      case 0xd1:{const v=buf.readInt16BE(p);p+=2;return v;}
      case 0xd2:{const v=buf.readInt32BE(p);p+=4;return v;}
      case 0xd3:{const v=Number(buf.readBigInt64BE(p));p+=8;return v;}
      case 0xca:{const v=buf.readFloatBE(p);p+=4;return v;}
      case 0xcb:{const v=buf.readDoubleBE(p);p+=8;return v;}
      case 0xd9:{const n=buf.readUInt8(p);p+=1;return rd(n);}
      case 0xda:{const n=buf.readUInt16BE(p);p+=2;return rd(n);}
      case 0xdb:{const n=buf.readUInt32BE(p);p+=4;return rd(n);}
      case 0xc4:{const n=buf.readUInt8(p);p+=1;const b=buf.slice(p,p+n);p+=n;return b;}
      case 0xc5:{const n=buf.readUInt16BE(p);p+=2;const b=buf.slice(p,p+n);p+=n;return b;}
      case 0xc6:{const n=buf.readUInt32BE(p);p+=4;const b=buf.slice(p,p+n);p+=n;return b;}
      case 0xdc:{const n=buf.readUInt16BE(p);p+=2;return arr(n);}
      case 0xdd:{const n=buf.readUInt32BE(p);p+=4;return arr(n);}
      case 0xde:{const n=buf.readUInt16BE(p);p+=2;return map(n);}
      case 0xdf:{const n=buf.readUInt32BE(p);p+=4;return map(n);}
      default: throw new Error('msgpack: byte lạ 0x'+c.toString(16)+' @'+(p-1));
    }
  }
  return dec();
}

/* ---------- MessagePack encode (khớp byte với Webcake) ---------- */
function encodeMsgpack(v){
  const out=[];
  (function enc(v){
    if(v===null||v===undefined){out.push(Buffer.from([0xc0]));return;}
    if(typeof v==='boolean'){out.push(Buffer.from([v?0xc3:0xc2]));return;}
    if(typeof v==='number'){
      if(Number.isInteger(v)){
        if(v>=0){
          if(v<0x80)out.push(Buffer.from([v]));
          else if(v<0x100)out.push(Buffer.from([0xcc,v]));
          else if(v<0x10000){const b=Buffer.alloc(3);b[0]=0xcd;b.writeUInt16BE(v,1);out.push(b);}
          else if(v<0x100000000){const b=Buffer.alloc(5);b[0]=0xce;b.writeUInt32BE(v,1);out.push(b);}
          else {const b=Buffer.alloc(9);b[0]=0xcf;b.writeBigUInt64BE(BigInt(v),1);out.push(b);}
        }else{
          if(v>=-32)out.push(Buffer.from([v&0xff]));
          else if(v>=-128)out.push(Buffer.from([0xd0,v&0xff]));
          else if(v>=-32768){const b=Buffer.alloc(3);b[0]=0xd1;b.writeInt16BE(v,1);out.push(b);}
          else if(v>=-2147483648){const b=Buffer.alloc(5);b[0]=0xd2;b.writeInt32BE(v,1);out.push(b);}
          else {const b=Buffer.alloc(9);b[0]=0xd3;b.writeBigInt64BE(BigInt(v),1);out.push(b);}
        }
      }else{const b=Buffer.alloc(9);b[0]=0xcb;b.writeDoubleBE(v,1);out.push(b);}
      return;
    }
    if(typeof v==='string'){
      const s=Buffer.from(v,'utf8'),n=s.length;
      if(n<32)out.push(Buffer.from([0xa0|n]));
      else if(n<256)out.push(Buffer.from([0xd9,n]));
      else if(n<65536){const b=Buffer.alloc(3);b[0]=0xda;b.writeUInt16BE(n,1);out.push(b);}
      else {const b=Buffer.alloc(5);b[0]=0xdb;b.writeUInt32BE(n,1);out.push(b);}
      out.push(s);return;
    }
    if(Buffer.isBuffer(v)){
      const n=v.length;
      if(n<256)out.push(Buffer.from([0xc4,n]));
      else if(n<65536){const b=Buffer.alloc(3);b[0]=0xc5;b.writeUInt16BE(n,1);out.push(b);}
      else {const b=Buffer.alloc(5);b[0]=0xc6;b.writeUInt32BE(n,1);out.push(b);}
      out.push(v);return;
    }
    if(Array.isArray(v)){
      const n=v.length;
      if(n<16)out.push(Buffer.from([0x90|n]));
      else if(n<65536){const b=Buffer.alloc(3);b[0]=0xdc;b.writeUInt16BE(n,1);out.push(b);}
      else {const b=Buffer.alloc(5);b[0]=0xdd;b.writeUInt32BE(n,1);out.push(b);}
      for(const x of v)enc(x);return;
    }
    if(typeof v==='object'){
      const keys=Object.keys(v),n=keys.length;
      if(n<16)out.push(Buffer.from([0x80|n]));
      else if(n<65536){const b=Buffer.alloc(3);b[0]=0xde;b.writeUInt16BE(n,1);out.push(b);}
      else {const b=Buffer.alloc(5);b[0]=0xdf;b.writeUInt32BE(n,1);out.push(b);}
      for(const k of keys){enc(k);enc(v[k]);}return;
    }
    throw new Error('msgpack: không mã hóa được '+typeof v);
  })(v);
  return Buffer.concat(out);
}

/* ---------- CLI ---------- */
module.exports={decodeMsgpack,encodeMsgpack};
function arg(flag){const i=process.argv.indexOf(flag);return i>0?process.argv[i+1]:undefined;}
const [,,cmd,inp,outp]=process.argv;

if(require.main===module){
if(cmd==='decode'){
  const raw=fs.readFileSync(inp,'utf8').trim();
  const obj=decodeMsgpack(Buffer.from(raw,'base64'));
  const out=outp||inp.replace(/\.pke$/i,'')+'.json';
  fs.writeFileSync(out, JSON.stringify(obj,null,2));
  console.log('OK decode ->',out,'| name:',obj.name,'| engine:',obj.engine);
}else if(cmd==='encode'){
  let obj=JSON.parse(fs.readFileSync(inp,'utf8'));
  // Nếu người dùng đưa vào chỉ mình "source" -> tự bọc envelope
  if(obj.source===undefined && obj.page!==undefined){
    obj={ source:obj, owner_id:arg('--owner')||'', name:arg('--name')||'Untitled',
          engine:2, email:{}, data_set_id:[] };
  }
  const buf=encodeMsgpack(obj);
  const out=outp||inp.replace(/\.json$/i,'')+'.pke';
  fs.writeFileSync(out, buf.toString('base64'));
  console.log('OK encode ->',out,'| bytes:',buf.length);
}else{
  console.log('Cách dùng:\n  node webcake-pke.js decode input.pke  [output.json]\n  node webcake-pke.js encode input.json [output.pke]  [--name "Tên" --owner <uuid>]');
  process.exit(1);
}
}
