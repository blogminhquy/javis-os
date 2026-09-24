/* mcp-form-parse.js - phần THUẦN của form "Tự thêm MCP" trên trang Kết nối.

   Người dùng thường không tự nghĩ ra cấu hình MCP. Họ COPY từ trang của nhà cung cấp, và mỗi
   nhà đưa một kiểu: Composio đưa một URL kèm tên header, Cursor/Claude Desktop đưa khối JSON
   `mcpServers`, trang khác đưa sẵn lệnh `claude mcp add ...` hoặc `npx ...`. Form cũ bắt họ
   tự dịch những thứ đó sang ô "Header (mỗi dòng)", và chính bước dịch đó là chỗ họ kẹt.

   File này nhận một cục văn bản dán vào và trả về một bản nháp form:
     { name, transport: "http"|"sse"|"stdio", url, command, args[], headers{}, env{} }
   hoặc null nếu không nhận ra.

   Không đụng DOM, nên test bằng node được: node tests/js/test_form_them_mcp.js
   KHÔNG dùng ký tự em dash ở bất kỳ đâu. */
(function () {
  "use strict";

  // Header mà nhà cung cấp hay dùng để nhận API key. Form dùng làm gợi ý cho ô tên header.
  var HEADER_GOI_Y = ["Authorization", "x-api-key", "x-consumer-api-key", "api-key", "X-Auth-Token"];

  // Nhận ra nhà cung cấp theo tên miền để điền sẵn tên header đúng. Chỉ khai những nhà đã
  // biết chắc cách họ nhận key; nhà lạ thì để người dùng tự điền theo hướng dẫn của họ.
  var NHA_CUNG_CAP = [
    { host: /(^|\.)composio\.dev$/i, ten: "composio", header: "x-consumer-api-key" },
  ];

  // Tách một dòng lệnh thành từng tham số, tôn trọng nháy đơn/nháy kép. Split theo dấu cách
  // như bản cũ thì `--header "Authorization: Bearer x"` vỡ thành ba mảnh.
  function tachLenh(s) {
    var out = [], cur = "", q = null, co = false;
    s = String(s || "").replace(/\\\r?\n/g, " ");
    for (var i = 0; i < s.length; i++) {
      var ch = s[i];
      if (q) {
        if (ch === q) { q = null; }
        else if (ch === "\\" && q === '"' && i + 1 < s.length && /["\\$`]/.test(s[i + 1])) { cur += s[++i]; }
        else cur += ch;
      } else if (ch === '"' || ch === "'") { q = ch; co = true; }
      else if (/\s/.test(ch)) { if (cur || co) { out.push(cur); cur = ""; co = false; } }
      else if (ch === "\\" && i + 1 < s.length) { cur += s[++i]; }
      else cur += ch;
    }
    if (cur || co) out.push(cur);
    return out;
  }

  // Ngược lại của tachLenh: ghép lại thành một dòng hiển thị trong ô lệnh khi SỬA. Tham số có
  // dấu cách phải được bọc nháy, không thì lưu lại lần nữa là vỡ.
  function ghepLenh(command, args) {
    return [command || ""].concat(args || []).filter(function (x, i) { return i > 0 || x; })
      .map(function (a) {
        a = String(a);
        if (a === "") return '""';
        return /[\s"'\\]/.test(a) ? '"' + a.replace(/(["\\])/g, "\\$1") + '"' : a;
      }).join(" ");
  }

  function hostCua(url) {
    try { return new URL(url).hostname; } catch (e) { return ""; }
  }

  function laUrl(s) { return /^https?:\/\/\S+$/i.test(String(s || "").trim()); }

  // SSE hay HTTP: endpoint SSE gần như luôn kết thúc bằng /sse. Mọi thứ khác đi HTTP (chuẩn
  // Streamable HTTP hiện hành), vì đoán sai sang SSE thì kết nối treo không báo lỗi gì.
  function doanTransport(url) {
    try { return /\/sse\/?$/i.test(new URL(url).pathname) ? "sse" : "http"; }
    catch (e) { return "http"; }
  }

  // Tên gợi nhớ tự đặt từ URL khi người dùng chưa đặt: "mcp.composio.dev" → "composio".
  function tenTuUrl(url) {
    var h = hostCua(url).replace(/^(www|mcp|api|connect|backend)\./i, "");
    var p = h.split(".");
    return (p.length > 1 ? p[p.length - 2] : p[0]) || "";
  }

  function nhaCungCap(url) {
    var h = hostCua(url);
    for (var i = 0; i < NHA_CUNG_CAP.length; i++) if (NHA_CUNG_CAP[i].host.test(h)) return NHA_CUNG_CAP[i];
    return null;
  }

  function tachHeader(s) {
    var i = String(s).indexOf(":");
    if (i < 0) return null;
    var k = s.slice(0, i).trim(), v = s.slice(i + 1).trim();
    return k ? [k, v] : null;
  }

  function nhap() { return { name: "", transport: "http", url: "", command: "", args: [], headers: {}, env: {} }; }

  function tuUrl(url) {
    var d = nhap();
    d.url = url.trim();
    d.transport = doanTransport(d.url);
    d.name = tenTuUrl(d.url);
    return d;
  }

  // `npx mcp-remote <url> --header "K: V"` là cách cũ để nối server HTTP vào client chỉ biết
  // stdio. Javis nói HTTP trực tiếp được, nên đổi ngược về dạng URL: bớt một tiến trình node
  // và header nằm trong ô header, sửa được, thay vì chôn trong tham số lệnh.
  function tuMcpRemote(cmd, args) {
    var all = [cmd].concat(args || []);
    var idx = -1;
    for (var i = 0; i < all.length; i++) if (/^mcp-remote(@.*)?$/.test(all[i])) { idx = i; break; }
    if (idx < 0) return null;
    var d = nhap(), rest = all.slice(idx + 1);
    for (var j = 0; j < rest.length; j++) {
      var a = rest[j];
      if (a === "--header" && j + 1 < rest.length) {
        var h = tachHeader(rest[++j]);
        if (h) d.headers[h[0]] = h[1];
      } else if (!d.url && laUrl(a)) d.url = a;
    }
    if (!d.url) return null;
    d.transport = doanTransport(d.url);
    d.name = tenTuUrl(d.url);
    return d;
  }

  // Một mục server trong khối JSON: {url|serverUrl|httpUrl, type, headers} hoặc
  // {command, args, env}. Trả null nếu không có gì dùng được.
  function tuMucJson(ten, o) {
    if (!o || typeof o !== "object") return null;
    var url = o.url || o.serverUrl || o.httpUrl || "";
    var d;
    if (url) {
      d = nhap();
      d.url = String(url);
      var t = String(o.type || o.transport || "").toLowerCase();
      d.transport = t === "sse" ? "sse" : (t === "http" || t === "streamable-http" || t === "streamablehttp") ? "http" : doanTransport(d.url);
      Object.keys(o.headers || {}).forEach(function (k) { d.headers[k] = String(o.headers[k]); });
      d.name = ten || tenTuUrl(d.url);
      return d;
    }
    if (o.command) {
      var args = Array.isArray(o.args) ? o.args.map(String) : [];
      var cmd = String(o.command);
      // "command": "npx -y pkg" (dồn cả lệnh vào một chuỗi) cũng gặp nhiều ngoài đời.
      if (!args.length && /\s/.test(cmd)) { var p = tachLenh(cmd); cmd = p[0]; args = p.slice(1); }
      d = tuMcpRemote(cmd, args);
      if (d) { if (ten) d.name = ten; return d; }
      d = nhap();
      d.transport = "stdio";
      d.command = cmd;
      d.args = args;
      Object.keys(o.env || {}).forEach(function (k) { d.env[k] = String(o.env[k]); });
      d.name = ten || "";
      return d;
    }
    return null;
  }

  function tuJson(s) {
    var o;
    try { o = JSON.parse(s); } catch (e) {
      // Người ta hay copy thiếu ngoặc ngoài: `"composio": {...}`. Bọc thêm một lần rồi thử lại.
      try { o = JSON.parse("{" + s.replace(/,\s*$/, "") + "}"); } catch (e2) { return null; }
    }
    if (!o || typeof o !== "object") return null;
    var goc = o.mcpServers || o.servers || (o.mcp && o.mcp.servers) || o.context_servers || null;
    if (goc && typeof goc === "object") {
      var ten = Object.keys(goc)[0];
      return ten ? tuMucJson(ten, goc[ten]) : null;
    }
    var truc = tuMucJson("", o);
    if (truc) return truc;
    // Dạng { "ten": { url/command ... } } không có mcpServers bọc ngoài.
    var k = Object.keys(o);
    if (k.length === 1 && o[k[0]] && typeof o[k[0]] === "object") return tuMucJson(k[0], o[k[0]]);
    return null;
  }

  // `claude mcp add [--transport http] [-H "K: V"] [-e K=V] <tên> <url | -- lệnh ...>`
  // (và `codex mcp add <tên> -- lệnh`). Trang docs của nhiều nhà cung cấp in sẵn dòng này.
  function tuLenhMcpAdd(tok) {
    var i = tok.indexOf("add");
    if (i < 0) return null;
    var d = nhap(), rest = tok.slice(i + 1), vitri = [], t = "";
    for (var j = 0; j < rest.length; j++) {
      var a = rest[j];
      if (a === "--") { var sau = rest.slice(j + 1); d.command = sau[0] || ""; d.args = sau.slice(1); break; }
      if (a === "--transport" || a === "-t") { t = (rest[++j] || "").toLowerCase(); continue; }
      if (/^--transport=/.test(a)) { t = a.split("=")[1].toLowerCase(); continue; }
      if (a === "--header" || a === "-H") { var h = tachHeader(rest[++j] || ""); if (h) d.headers[h[0]] = h[1]; continue; }
      if (a === "--env" || a === "-e") {
        var kv = rest[++j] || "", e = kv.indexOf("=");
        if (e > 0) d.env[kv.slice(0, e)] = kv.slice(e + 1);
        continue;
      }
      if (a === "--scope" || a === "-s" || a === "--client-id" || a === "--callback-port") { j++; continue; }
      if (a.charAt(0) === "-") continue;
      vitri.push(a);
    }
    d.name = vitri[0] || "";
    if (d.command) {
      var r = tuMcpRemote(d.command, d.args);
      if (r) { r.name = d.name || r.name; Object.keys(d.headers).forEach(function (k) { r.headers[k] = d.headers[k]; }); return r; }
      d.transport = "stdio";
      return d;
    }
    if (vitri[1] && laUrl(vitri[1])) {
      d.url = vitri[1];
      d.transport = t === "sse" ? "sse" : t === "http" ? "http" : doanTransport(d.url);
      return d;
    }
    return null;
  }

  // Cửa vào duy nhất. Thứ tự thử: JSON → URL trần → lệnh `... mcp add` → lệnh chạy thường.
  function docCauHinh(text) {
    var s = String(text || "").trim();
    if (!s) return null;
    var d = null;
    if (s.charAt(0) === "{" || s.charAt(0) === '"') d = tuJson(s);
    else if (laUrl(s)) d = tuUrl(s);
    else {
      var tok = tachLenh(s);
      if (!tok.length) return null;
      if (tok.length > 2 && tok[1] === "mcp" && tok.indexOf("add") > 1) d = tuLenhMcpAdd(tok);
      else {
        d = tuMcpRemote(tok[0], tok.slice(1));
        if (!d) { d = nhap(); d.transport = "stdio"; d.command = tok[0]; d.args = tok.slice(1); d.name = tenTuLenh(tok); }
      }
    }
    if (!d) return null;
    // Nhà cung cấp đã biết mà khối dán vào chưa có header key: thêm sẵn một dòng trống đúng
    // tên, để người dùng chỉ còn việc dán key.
    if (d.transport !== "stdio" && d.url) {
      var ncc = nhaCungCap(d.url);
      if (ncc && !Object.keys(d.headers).length) d.headers[ncc.header] = "";
    }
    return d;
  }

  // "npx -y @modelcontextprotocol/server-github" → "server-github" → "github".
  function tenTuLenh(tok) {
    for (var i = tok.length - 1; i >= 0; i--) {
      var a = tok[i];
      if (!a || a.charAt(0) === "-" || /[=\/\\]$/.test(a)) continue;
      if (/^(npx|uvx|node|python3?|bunx|pnpm|dlx|docker|run)$/i.test(a)) continue;
      var t = a.replace(/@[^@\/]*$/, "").split("/").pop().replace(/^(mcp-server-|server-)/, "").replace(/-mcp(-server)?$/, "");
      if (t) return t;
    }
    return "";
  }

  // Header Authorization mà giá trị chỉ là một chuỗi key trần (không có "Bearer ", "Basic "...)
  // thì gần như chắc chắn người dùng quên tiền tố. Form dùng để nhắc, KHÔNG tự sửa.
  function thieuBearer(ten, giaTri) {
    return /^authorization$/i.test(String(ten || "").trim())
      && !!String(giaTri || "").trim() && !/\s/.test(String(giaTri).trim());
  }

  var api = {
    docCauHinh: docCauHinh, tachLenh: tachLenh, ghepLenh: ghepLenh, doanTransport: doanTransport,
    nhaCungCap: nhaCungCap, tenTuUrl: tenTuUrl, thieuBearer: thieuBearer, HEADER_GOI_Y: HEADER_GOI_Y,
  };
  if (typeof window !== "undefined") window.JavisMcpParse = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
