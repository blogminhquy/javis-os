/* dataview.js - Dataview LITE cho Javis OS (cam hung obsidian-dataview + obsidian-tasks).
   Khoi ```dataview trong note/chat duoc chat-render.js do thanh <div class="jv-dataview"
   data-dv-q="...">; file nay tu phat hien (MutationObserver), tai chi muc note tu
   /files/mdindex roi CHAY TRUY VAN NGAY TREN TRINH DUYET va ve ket qua.

   Ho tro (tap con hay dung nhat cua ngon ngu dataview):
   - TASK | LIST | TABLE [WITHOUT ID] cot1, cot2 AS "Ten"
   - FROM "thu-muc" | #tag  (ket hop AND / OR, phu dinh - hoac !)
   - WHERE <bieu thuc>: !completed, due <= date(today), status = "doing",
     contains(text, "goi"), contains(tags, "#ban-hang"), ket hop AND/OR/(..)
   - SORT <truong> [ASC|DESC], LIMIT n. GROUP BY file.link (TASK von nhom theo file).
   Chua ho tro: dataviewjs, FLATTEN, dur(...), lien ket [[..]] trong FROM.

   Task trong ket qua TICK DUOC: goi POST /files/taskcheck ghi thang vao file goc
   (kem expect de chong ghi de khi file da doi). Cac dau Obsidian Tasks (ngay han,
   ngay du kien, ngay bat dau, ngay hoan thanh, do uu tien) da duoc server boc san
   trong chi muc, file nay chi HIEN THI - khong tu doc dau tu markdown tho.

   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  // Chữ hiện ra lấy từ từ điển. Trong trình duyệt là window.t (i18n/index.js nạp trước mọi
  // module này); dưới node - nơi test require() thẳng file này - `window` CHƯA KHAI BÁO nên
  // đọc window.t là ReferenceError chứ không phải undefined, phải hỏi bằng typeof. Ở đó đọc
  // thẳng vi.json để hàm vẫn trả về chữ thật, không phải mã khoá trần.
  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  // File này chạy hai chế độ: trong trình duyệt và dưới node (test require nó).
  // Dưới node không có window nên không có ic() - trả về chuỗi rỗng để phần logic
  // vẫn test được mà không phải kéo cả tầng icon vào. Trong trình duyệt thì
  // icons.js đã nạp trước (index.html bảo đảm thứ tự, có test canh) nên lấy
  // được hàm thật.
  var ic = (typeof window !== "undefined" && window.ic) ? window.ic : function () { return ""; };

  // Cùng lý do với ic(): dưới node không có window nên không có từ điển, lúc đó trả về chính
  // khoá. Tra lúc GỌI chứ không lúc nạp file, để không phụ thuộc thứ tự script trong HTML.
  function dt(k, bien) {
    return (typeof window !== "undefined" && window.t) ? tw(k, bien) : k;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function brainPath() {
    try { return (typeof window !== "undefined" && window.currentBrainPath) ? (window.currentBrainPath() || "brain") : "brain"; }
    catch (e) { return "brain"; }
  }
  function todayIso(shift) {
    var d = new Date();
    if (shift) d.setDate(d.getDate() + shift);
    var m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (day < 10 ? "0" : "") + day;
  }

  // ---------------------------------------------------------------- chi muc note
  // 2 tang tiet kiem: (1) trong IDX_TTL dung lai ket qua khong hoi server; (2) het TTL
  // van hoi nhung kem If-None-Match - khong note nao doi thi server tra 304 rong (khoi
  // gui lai ca cuc JSON), minh dung lai ban da giu. Cache tach theo brain + pham vi scope.
  var idxCache = {};   // key -> { t, p, etag, data }
  var IDX_TTL = 15000;
  function loadIndex(scope) {
    var b = brainPath(), now = Date.now();
    var key = b + "||" + (scope && scope.length ? scope.slice().sort().join("|") : "*");
    var c = idxCache[key];
    if (c && c.p && now - c.t < IDX_TTL) return c.p;
    var url = "/files/mdindex?brain=" + encodeURIComponent(b) +
      (scope || []).map(function (s) { return "&path=" + encodeURIComponent(s); }).join("");
    var headers = {};
    if (c && c.etag) headers["If-None-Match"] = c.etag;
    var entry = { t: now, p: null, etag: c && c.etag, data: c && c.data };
    entry.p = fetch(url, { headers: headers, cache: "no-store" })
      .then(function (r) {
        if (r.status === 304 && entry.data) return entry.data;   // khong doi: dung ban cu
        if (!r.ok) return entry.data || { files: [] };
        return r.json().then(function (d) {
          entry.etag = (d && d.etag) || r.headers.get("ETag") || "";
          entry.data = d;
          return d;
        });
      })
      .catch(function () { return entry.data || { files: [] }; });
    idxCache[key] = entry;
    return entry.p;
  }
  // Du lieu vua doi (vd tick task): giu etag/data nhung ep lan render sau HOI LAI server
  function dropCache() {
    for (var k in idxCache) if (idxCache[k]) idxCache[k].t = 0;
  }
  // Suy pham vi quet tu FROM: moi nhanh OR deu phai co it nhat 1 thu muc DUONG thi moi
  // khoanh vung duoc (nhanh chi co #tag phai quet ca brain). Ket qua la TAP CHA du dung:
  // matchFrom van loc chinh xac tren client sau do.
  function fromScope(from) {
    if (!from || !from.or) return null;
    var out = [], seenF = {};
    for (var g = 0; g < from.or.length; g++) {
      var pos = from.or[g].filter(function (a) { return a.kind === "folder" && !a.neg && a.v; });
      if (!pos.length) return null;
      pos.forEach(function (a) { if (!seenF[a.v]) { seenF[a.v] = 1; out.push(a.v); } });
    }
    return out.length ? out : null;
  }

  // ---------------------------------------------------------------- parse truy van
  function splitTop(s, sep) {
    // tach theo sep (1 ky tu) o TANG NGOAI CUNG (khong tach trong "..", '..', (..))
    var out = [], cur = "", depth = 0, quote = null;
    for (var i = 0; i < s.length; i++) {
      var ch = s[i];
      if (quote) { cur += ch; if (ch === quote && s[i - 1] !== "\\") quote = null; continue; }
      if (ch === '"' || ch === "'") { quote = ch; cur += ch; continue; }
      if (ch === "(") depth++;
      if (ch === ")") depth--;
      if (ch === sep && depth === 0) { out.push(cur); cur = ""; continue; }
      cur += ch;
    }
    if (cur.trim()) out.push(cur);
    return out.map(function (x) { return x.trim(); }).filter(Boolean);
  }
  function parseQuery(src) {
    var s = String(src == null ? "" : src).replace(/\r/g, "").trim();
    if (!s) return { error: dt("dview.err.empty_query") };
    var parts = s.split(/\b(FROM|WHERE|SORT|GROUP\s+BY|LIMIT|FLATTEN)\b/i);
    var head = parts[0].trim();
    var hm = /^(TASK|LIST|TABLE)\b([\s\S]*)$/i.exec(head);
    if (!hm) return { error: dt("dview.err.unsupported_query") };
    var q = { type: hm[1].toUpperCase(), columns: [], from: null, where: null,
              sort: null, limit: 0, withoutId: false, warn: [] };
    var rest = hm[2].replace(/\n/g, " ").trim();
    if (/^WITHOUT\s+ID\b/i.test(rest)) { q.withoutId = true; rest = rest.replace(/^WITHOUT\s+ID\b/i, "").trim(); }
    if (q.type === "TABLE" && rest) {
      q.columns = splitTop(rest, ",").map(function (c) {
        var am = /^([\s\S]+?)\s+AS\s+("(?:[^"]*)"|'(?:[^']*)'|\S+)\s*$/i.exec(c);
        if (am) return { expr: am[1].trim(), name: am[2].replace(/^["']|["']$/g, "") };
        return { expr: c.trim(), name: c.trim() };
      });
    }
    for (var i = 1; i < parts.length; i += 2) {
      var kw = parts[i].toUpperCase().replace(/\s+/g, " ");
      var val = (parts[i + 1] || "").replace(/\n/g, " ").trim();
      if (kw === "FROM") q.from = parseFrom(val);
      else if (kw === "WHERE") q.where = val;
      else if (kw === "SORT") q.sort = parseSort(val);
      else if (kw === "LIMIT") q.limit = parseInt(val, 10) || 0;
      else if (kw === "GROUP BY") q.group = val;          // TASK von da nhom theo file
      else if (kw === "FLATTEN") q.warn.push(dt("dview.warn.flatten"));
    }
    if (q.from && q.from.error) return { error: q.from.error };
    return q;
  }
  function parseFrom(val) {
    if (!val) return null;
    var orGroups = val.split(/\bOR\b/i).map(function (side) {
      return side.split(/\bAND\b/i).map(function (atom) {
        atom = atom.trim();
        var neg = false;
        while (atom[0] === "-" || atom[0] === "!") { neg = !neg; atom = atom.slice(1).trim(); }
        var m = /^"([^"]*)"$|^'([^']*)'$/.exec(atom);
        if (m) return { kind: "folder", v: (m[1] != null ? m[1] : m[2]).replace(/^\/+|\/+$/g, ""), neg: neg };
        if (atom[0] === "#") return { kind: "tag", v: atom, neg: neg };
        if (/^\[\[/.test(atom)) return { kind: "bad", v: atom };
        return { kind: "bad", v: atom };
      });
    });
    for (var g = 0; g < orGroups.length; g++)
      for (var a = 0; a < orGroups[g].length; a++)
        if (orGroups[g][a].kind === "bad")
          return { error: dt("dview.err.from", { v: orGroups[g][a].v }) };
    return { or: orGroups };
  }
  // ---------------------------------------------------------------- ngon ngu obsidian-tasks (khoi ```tasks)
  // Dich TUNG DONG filter cua plugin Tasks sang bieu thuc WHERE noi bo (cac dong AND voi nhau,
  // dung ngu nghia plugin goc) roi chay CHUNG engine voi dataview. Dong chua ho tro -> canh bao
  // ro rang, cac dong con lai van chay. "happens" duoc xap xi bang "due".
  var TASKS_PRIO = { highest: 0, high: 1, medium: 2, none: 3, low: 4, lowest: 5 };
  var TASKS_FIELD = { due: "due", scheduled: "scheduled", starts: "start", start: "start",
                      done: "done", created: "created", happens: "due" };
  function tasksDateExpr(field, rel, when) {
    var d = null;
    if (/^today$/i.test(when)) d = "date(today)";
    else if (/^tomorrow$/i.test(when)) d = "date(tomorrow)";
    else if (/^yesterday$/i.test(when)) d = "date(yesterday)";
    else if (/^\d{4}-\d{2}-\d{2}$/.test(when)) d = 'date("' + when + '")';
    if (!d) return null;
    if (rel === "before") return field + " < " + d;
    if (rel === "after") return field + " > " + d;
    return field + " = " + d;
  }
  function parseTasksQuery(src) {
    var q = { type: "TASK", columns: [], from: null, where: null, sort: null, limit: 0,
              withoutId: false, warn: [] };
    var conds = [];
    var IGNORE = /^(group by |hide |show |short mode$|full mode$|explain$|is recurring$|is not recurring$)/i;
    String(src == null ? "" : src).replace(/\r/g, "").split("\n").forEach(function (line) {
      line = line.trim();
      if (!line || line[0] === "#") return;
      var low = line.toLowerCase(), m;
      if (low === "done") { conds.push("completed"); return; }
      if (low === "not done") { conds.push("!completed"); return; }
      if ((m = /^(due|scheduled|starts|start|done|created|happens)\s+(before|after|on)?\s*(.+)$/i.exec(line))) {
        var e = tasksDateExpr(TASKS_FIELD[m[1].toLowerCase()], (m[2] || "on").toLowerCase(), m[3].trim());
        if (e) { conds.push(e); return; }
      }
      if ((m = /^has\s+(due|scheduled|start|done|created)\s+date$/.exec(low))) { conds.push(TASKS_FIELD[m[1]]); return; }
      if ((m = /^no\s+(due|scheduled|start|done|created)\s+date$/.exec(low))) { conds.push("!" + TASKS_FIELD[m[1]]); return; }
      if ((m = /^description\s+(does not include|includes?)\s+(.+)$/i.exec(line))) {
        var e2 = 'contains(text, "' + m[2].trim().replace(/"/g, "") + '")';
        conds.push(/not/i.test(m[1]) ? "!" + e2 : e2); return;
      }
      if ((m = /^path\s+(does not include|includes?)\s+(.+)$/i.exec(line))) {
        var e3 = 'contains(file.path, "' + m[2].trim().replace(/"/g, "") + '")';
        conds.push(/not/i.test(m[1]) ? "!" + e3 : e3); return;
      }
      if ((m = /^tags?\s+(do(?:es)? not include|includes?)\s+(.+)$/i.exec(line))) {
        var tg = m[2].trim().replace(/"/g, "");
        if (tg[0] !== "#") tg = "#" + tg;
        var e4 = 'contains(tags, "' + tg + '")';
        conds.push(/not/i.test(m[1]) ? "!" + e4 : e4); return;
      }
      if ((m = /^priority\s+is\s+(above|below)?\s*(highest|high|medium|none|low|lowest)$/.exec(low))) {
        var p = TASKS_PRIO[m[2]];
        conds.push(m[1] === "above" ? "priority < " + p : m[1] === "below" ? "priority > " + p : "priority = " + p);
        return;
      }
      if ((m = /^sort by\s+(\S+)(\s+reverse)?$/.exec(low))) {
        var f = { due: "due", priority: "priority", description: "text", path: "file.path",
                  scheduled: "scheduled", start: "start", done: "done", created: "created" }[m[1]];
        if (f) { q.sort = { expr: f, desc: !!m[2] }; return; }
      }
      if ((m = /^limit(?:\s+to)?\s+(\d+)(?:\s+tasks?)?$/.exec(low))) { q.limit = parseInt(m[1], 10) || 0; return; }
      if (IGNORE.test(low)) return;
      q.warn.push(dt("dview.warn.skip_line") + ' "' + line + '"');
    });
    if (conds.length) q.where = conds.map(function (c) { return "(" + c + ")"; }).join(" AND ");
    return q;
  }

  function parseSort(val) {
    var first = splitTop(val, ",")[0] || "";
    var m = /^([\s\S]+?)(?:\s+(ASC|DESC))?$/i.exec(first.trim());
    if (!m) return null;
    return { expr: m[1].trim(), desc: /desc/i.test(m[2] || "") };
  }
  function matchFrom(from, f) {
    if (!from) return true;
    return from.or.some(function (group) {
      return group.every(function (atom) {
        var hit;
        if (atom.kind === "folder") {
          var p = f.path.toLowerCase(), fol = atom.v.toLowerCase();
          hit = !fol || p === fol || p === fol + ".md" || p.indexOf(fol + "/") === 0;
        } else {
          var t = atom.v.toLowerCase();
          hit = (f.tags || []).some(function (x) { return String(x).toLowerCase() === t; });
        }
        return atom.neg ? !hit : hit;
      });
    });
  }

  // ---------------------------------------------------------------- bieu thuc WHERE / SORT / cot TABLE
  var TOK_RE = /"(?:\\.|[^"])*"|'(?:\\.|[^'])*'|!=|>=|<=|=>|[()!,=<>]|-?\d+(?:\.\d+)?|#[A-Za-z0-9_\-\/À-ỹ]+|[A-Za-z_À-ỹ][\w.\-À-ỹ]*/g;
  function tokenize(s) {
    var out = [], m;
    TOK_RE.lastIndex = 0;
    while ((m = TOK_RE.exec(s)) !== null) out.push(m[0]);
    return out;
  }
  // compile(exprText) -> ham (ctx) => gia tri. Nem Error khi cu phap sai.
  function compile(src) {
    var toks = tokenize(String(src || "")), pos = 0;
    function peek() { return toks[pos]; }
    function next() { return toks[pos++]; }
    function expect(t) { if (next() !== t) throw new Error(dt("dview.err.missing_token", { tok: t, src: src })); }
    function parseOr() {
      var l = parseAnd();
      while (peek() && /^(or)$/i.test(peek())) { next(); var r = parseAnd(); l = (function (a, b) { return function (c) { return truthy(a(c)) || truthy(b(c)); }; })(l, r); }
      return l;
    }
    function parseAnd() {
      var l = parseCmp();
      while (peek() && /^(and)$/i.test(peek())) { next(); var r = parseCmp(); l = (function (a, b) { return function (c) { return truthy(a(c)) && truthy(b(c)); }; })(l, r); }
      return l;
    }
    function parseCmp() {
      var l = parseUnary();
      var op = peek();
      if (op === "=" || op === "!=" || op === ">" || op === "<" || op === ">=" || op === "<=") {
        next();
        var r = parseUnary();
        return (function (a, b, o) {
          return function (c) {
            var x = a(c), y = b(c);
            if (x == null || y == null) return o === "!=" ? x !== y : false;
            if (typeof x === "number" || typeof y === "number") { x = Number(x); y = Number(y); }
            else { x = String(x); y = String(y); }
            if (o === "=") return x === y;
            if (o === "!=") return x !== y;
            if (o === ">") return x > y;
            if (o === "<") return x < y;
            if (o === ">=") return x >= y;
            return x <= y;
          };
        })(l, r, op);
      }
      return l;
    }
    function parseUnary() {
      if (peek() === "!") { next(); var v = parseUnary(); return function (c) { return !truthy(v(c)); }; }
      return parseVal();
    }
    function parseVal() {
      var t = next();
      if (t == null) throw new Error(dt("dview.err.incomplete_expr", { src: src }));
      if (t === "(") { var e = parseOr(); expect(")"); return e; }
      if (t[0] === '"' || t[0] === "'") { var s = t.slice(1, -1); return function () { return s; }; }
      if (/^-?\d/.test(t)) { var n = parseFloat(t); return function () { return n; }; }
      if (t[0] === "#") { var tag = t; return function () { return tag; }; }
      var low = t.toLowerCase();
      if (peek() === "(") {
        next();
        if (low === "date") {
          var arg = next();
          expect(")");
          if (/^["']/.test(arg)) { var dv = arg.slice(1, -1); return function () { return dv; }; }
          var al = String(arg || "").toLowerCase();
          return function () {
            if (al === "today" || al === "now") return todayIso(0);
            if (al === "tomorrow") return todayIso(1);
            if (al === "yesterday") return todayIso(-1);
            return al;
          };
        }
        if (low === "contains") {
          var a1 = parseOr(); expect(","); var a2 = parseOr(); expect(")");
          return function (c) {
            var hay = a1(c), needle = a2(c);
            if (hay == null || needle == null) return false;
            if (Array.isArray(hay)) return hay.some(function (x) { return String(x).toLowerCase() === String(needle).toLowerCase(); });
            return String(hay).toLowerCase().indexOf(String(needle).toLowerCase()) >= 0;
          };
        }
        if (low === "length") {
          var la = parseOr(); expect(")");
          return function (c) { var v2 = la(c); return v2 == null ? 0 : (Array.isArray(v2) ? v2.length : String(v2).length); };
        }
        throw new Error(dt("dview.err.unknown_func", { ten: t }));
      }
      // chuoi truong: a.b.c (this. tro ve chinh ctx)
      var chain = t.split(".").filter(function (x) { return x && x.toLowerCase() !== "this"; });
      return function (c) {
        var cur = c;
        for (var i = 0; i < chain.length; i++) {
          if (cur == null || typeof cur !== "object") return undefined;
          var k = chain[i];
          cur = (k in cur) ? cur[k] : cur[k.toLowerCase()];
        }
        return cur;
      };
    }
    var fn = parseOr();
    if (pos < toks.length) throw new Error(dt("dview.err.extra_token", { tok: toks[pos], src: src }));
    return fn;
  }
  function truthy(v) {
    if (v == null || v === false || v === "" || v === 0) return false;
    if (Array.isArray(v)) return v.length > 0;
    return true;
  }
  function cmpVals(a, b) {
    if (a == null && b == null) return 0;
    if (a == null) return -1;
    if (b == null) return 1;
    if (typeof a === "number" && typeof b === "number") return a - b;
    return String(a).localeCompare(String(b), "vi");
  }

  // ---------------------------------------------------------------- ngu canh danh gia
  function fileCtx(f) {
    return { name: f.name.replace(/\.md$/i, ""), path: f.path, folder: f.folder || "",
             link: f.path, mtime: f.mtime || 0 };
  }
  function pageCtx(f) {
    var ctx = {};
    var fm = f.fm || {};
    for (var k in fm) if (Object.prototype.hasOwnProperty.call(fm, k)) ctx[k] = fm[k];
    ctx.file = fileCtx(f);
    ctx.tags = f.tags || [];
    return ctx;
  }
  function taskCtx(t, f) {
    return { text: t.text, raw: t.raw, line: t.line, checked: !!t.checked,
             completed: !!t.checked, fullyCompleted: !!t.checked, status: t.checked ? "x" : " ",
             due: t.due || null, done: t.done || null, scheduled: t.scheduled || null,
             start: t.start || null, created: t.created || null,
             priority: (t.priority == null ? 3 : t.priority), tags: t.tags || [],
             file: fileCtx(f), page: f.fm || {} };
  }

  // ---------------------------------------------------------------- chay truy van -> HTML
  function fileLinkHtml(path, label) {
    var name = label || String(path).split("/").pop().replace(/\.md$/i, "");
    return '<a class="jv-floc dv-flink" href="#open=' + esc(encodeURIComponent(path)) +
      '" data-vault-path="' + esc(path) + '" title="' + esc(path) + '">' + esc(name) + "</a>";
  }
  // Do uu tien -> [ten icon, lop mau]. Cung thang mau voi trang Viec (Kanban):
  // cang gap cang do, cang thap cang mo di cho khoi tranh chu y.
  var PRIO_ICON = {
    0: ["chevrons-up", "ic-err"],
    1: ["chevron-up", "ic-err"],
    2: ["chevron-up", "ic-warn"],
    4: ["chevron-down", "ic-dim"],
    5: ["chevrons-down", "ic-dim"],
  };
  function taskItemHtml(t, f) {
    var badges = "";
    if (t.priority != null && t.priority !== 3 && PRIO_ICON[t.priority])
      badges += ' <span class="dv-badge dv-prio">' + ic(PRIO_ICON[t.priority][0], { cls: PRIO_ICON[t.priority][1] }) + "</span>";
    if (t.due) {
      var over = !t.checked && t.due < todayIso(0);
      badges += ' <span class="dv-badge dv-due' + (over ? " dv-over" : "") + '">' + ic("calendar") + " " + esc(t.due) + "</span>";
    }
    if (t.scheduled) badges += ' <span class="dv-badge">' + ic("hourglass") + " " + esc(t.scheduled) + "</span>";
    if (t.done) badges += ' <span class="dv-badge dv-donedate">' + ic("circle-check", { cls: "ic-ok" }) + " " + esc(t.done) + "</span>";
    return '<li class="dv-task' + (t.checked ? " task-done" : "") + '">' +
      '<input type="checkbox" class="md-cb dv-cb" data-dv-path="' + esc(f.path) +
      '" data-dv-line="' + (t.line || 0) + '" data-dv-raw="' + esc(encodeURIComponent(String(t.raw || "").trim())) + '"' +
      (t.checked ? " checked" : "") + '><span class="dv-ttext">' + esc(t.text || "") + badges + "</span></li>";
  }
  function emptyHtml() { return '<div class="dv-empty">' + esc(tw("dview.rong_khong_khop")) + "</div>"; }
  function execQuery(q, files) {
    var pages = files.filter(function (f) { return matchFrom(q.from, f); });
    var whereFn = q.where ? compile(q.where) : null;
    var sortFn = q.sort ? compile(q.sort.expr) : null;
    var html = "";
    if (q.type === "TASK") {
      var rows = [];
      pages.forEach(function (f) {
        (f.tasks || []).forEach(function (t) {
          var ctx = taskCtx(t, f);
          if (whereFn && !truthy(whereFn(ctx))) return;
          rows.push({ t: t, f: f, ctx: ctx });
        });
      });
      if (sortFn) rows.sort(function (a, b) { return (q.sort.desc ? -1 : 1) * cmpVals(sortFn(a.ctx), sortFn(b.ctx)); });
      if (q.limit > 0) rows = rows.slice(0, q.limit);
      if (!rows.length) return emptyHtml();
      var groups = [], byPath = {};
      rows.forEach(function (r) {
        var g = byPath[r.f.path];
        if (!g) { g = { f: r.f, rows: [] }; byPath[r.f.path] = g; groups.push(g); }
        g.rows.push(r);
      });
      var done = rows.filter(function (r) { return r.t.checked; }).length;
      html += '<div class="dv-count">' + dt("dview.count_tasks", { so: rows.length, xong: done }) + "</div>";
      groups.forEach(function (g) {
        html += '<div class="dv-group"><div class="dv-ghead">' + fileLinkHtml(g.f.path) + "</div><ul class=\"dv-tasks\">" +
          g.rows.map(function (r) { return taskItemHtml(r.t, r.f); }).join("") + "</ul></div>";
      });
      return html;
    }
    // LIST / TABLE: don vi = trang (note)
    var prows = pages.map(function (f) { return { f: f, ctx: pageCtx(f) }; });
    if (whereFn) prows = prows.filter(function (r) { return truthy(whereFn(r.ctx)); });
    if (sortFn) prows.sort(function (a, b) { return (q.sort.desc ? -1 : 1) * cmpVals(sortFn(a.ctx), sortFn(b.ctx)); });
    else prows.sort(function (a, b) { return cmpVals(a.ctx.file.name.toLowerCase(), b.ctx.file.name.toLowerCase()); });
    if (q.limit > 0) prows = prows.slice(0, q.limit);
    if (!prows.length) return emptyHtml();
    if (q.type === "LIST") {
      return '<div class="dv-count">' + prows.length + ' note</div><ul class="dv-list">' +
        prows.map(function (r) { return "<li>" + fileLinkHtml(r.f.path) + "</li>"; }).join("") + "</ul>";
    }
    // TABLE
    var cols = q.columns.map(function (c) { return { name: c.name, fn: compile(c.expr) }; });
    var th = (q.withoutId ? "" : "<th>File</th>") +
      cols.map(function (c) { return "<th>" + esc(c.name) + "</th>"; }).join("");
    var trs = prows.map(function (r) {
      var tds = (q.withoutId ? "" : "<td>" + fileLinkHtml(r.f.path) + "</td>") +
        cols.map(function (c) {
          var v = c.fn(r.ctx);
          if (v == null || v === "") return "<td>-</td>";
          if (Array.isArray(v)) v = v.join(", ");
          return "<td>" + esc(v) + "</td>";
        }).join("");
      return "<tr>" + tds + "</tr>";
    }).join("");
    return '<div class="dv-count">' + prows.length + ' note</div>' +
      '<div class="dv-tablewrap"><table class="md-table dv-table"><thead><tr>' + th + "</tr></thead><tbody>" + trs + "</tbody></table></div>";
  }

  // ---------------------------------------------------------------- ve khoi
  function errHtml(msg, q) {
    return '<div class="dv-err">' + ic("triangle-alert", { cls: "ic-warn" }) + " " + esc(msg) + '</div><pre class="dv-src">' + esc(q) + "</pre>";
  }
  function run(el) {
    el.setAttribute("data-dv-done", "1");
    var body = el.querySelector(".jv-dv-body") || el;
    var lang = (el.getAttribute("data-dv-lang") || "dataview").toLowerCase();
    var q = el.getAttribute("data-dv-q") || "";
    try { q = decodeURIComponent(q); } catch (e) {}
    if (lang === "dataviewjs") {
      body.innerHTML = errHtml(tw("dview.err.dataviewjs"), q);
      return;
    }
    var pq = lang === "tasks" ? parseTasksQuery(q) : parseQuery(q);
    if (pq.error) { body.innerHTML = errHtml(pq.error, q); return; }
    // Khoi ra danh sach viec -> gan nut "+ Việc" (them nhanh vao Task Inbox) len dau khoi
    if (pq.type === "TASK") {
      var head = el.querySelector(".jv-dv-head");
      if (head && !head.querySelector(".dv-add")) {
        var ab = document.createElement("button");
        ab.type = "button"; ab.className = "dv-add"; ab.textContent = tw("dview.add_task_btn");
        ab.title = tw("dview.add_task_title");
        head.appendChild(ab);
      }
    }
    loadIndex(fromScope(pq.from)).then(function (idx) {
      if (!el.isConnected) return;
      try {
        var html = execQuery(pq, (idx && idx.files) || []);
        if (pq.warn && pq.warn.length)
          html = '<div class="dv-warn">' + esc(pq.warn.join(" · ")) + "</div>" + html;
        body.innerHTML = html;
      } catch (err) {
        body.innerHTML = errHtml(tw("dview.err.run", { loi: (err && err.message || err) }), q);
      }
    });
  }
  // Nut "+ Việc": form mini (noi dung + han) ngay tren khoi, POST /files/taskadd ->
  // viec roi vao "<thu muc Dashboard>/Task Inbox.md", xong lam moi MOI khoi tren trang.
  function submitAdd(el) {
    if (!el) return;
    var form = el.querySelector(".dv-addform");
    if (!form) return;
    var ti = form.querySelector(".dv-add-text"), di = form.querySelector(".dv-add-date");
    var go = form.querySelector(".dv-add-go");
    var text = (ti.value || "").trim();
    if (!text) { ti.focus(); return; }
    var fd = new FormData();
    fd.append("brain", brainPath());
    fd.append("text", text);
    fd.append("due", di.value || "");
    go.disabled = true; go.textContent = "…";
    fetch("/files/taskadd", { method: "POST", body: fd })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (d) {
        go.disabled = false; go.textContent = tw("proj.add");
        if (d && d.ok) {
          ti.value = ""; di.value = "";
          form.classList.remove("open");
          dropCache();
          document.querySelectorAll(".jv-dataview[data-dv-done]").forEach(function (x) {
            x.removeAttribute("data-dv-done");   // viec moi co the khop query cua khoi khac
          });
          scheduleScan();
        } else {
          go.innerHTML = ic("triangle-alert", { cls: "ic-warn" }); go.title = (d && d.error) || tw("dview.add_failed");
          setTimeout(function () { go.textContent = tw("proj.add"); }, 1600);
        }
      })
      .catch(function () {
        go.disabled = false; go.innerHTML = ic("triangle-alert", { cls: "ic-warn" });
        setTimeout(function () { go.textContent = tw("proj.add"); }, 1600);
      });
  }

  var scanTimer = null;
  function scheduleScan() {
    if (scanTimer) return;
    scanTimer = setTimeout(function () {
      scanTimer = null;
      document.querySelectorAll(".jv-dataview:not([data-dv-done])").forEach(run);
    }, 60);
  }

  // ---------------------------------------------------------------- wiring (chi khi co DOM)
  if (typeof document !== "undefined") {
    var mo = new MutationObserver(scheduleScan);
    var boot = function () {
      mo.observe(document.body, { childList: true, subtree: true });
      scheduleScan();
    };
    if (document.body) boot(); else document.addEventListener("DOMContentLoaded", boot);

    // Tick task trong ket qua dataview: ghi thang vao FILE GOC qua /files/taskcheck.
    document.addEventListener("click", function (e) {
      var cb = e.target;
      if (!cb || cb.tagName !== "INPUT" || cb.type !== "checkbox" ||
          !(cb.classList && cb.classList.contains("dv-cb"))) return;
      var want = cb.checked ? 1 : 0;
      var raw = cb.getAttribute("data-dv-raw") || "";
      try { raw = decodeURIComponent(raw); } catch (err) {}
      var fd = new FormData();
      fd.append("brain", brainPath());
      fd.append("path", cb.getAttribute("data-dv-path") || "");
      fd.append("line", cb.getAttribute("data-dv-line") || "0");
      fd.append("checked", String(want));
      fd.append("expect", raw);
      cb.disabled = true;
      fetch("/files/taskcheck", { method: "POST", body: fd })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }).catch(function () { return { ok: false, d: {} }; }); })
        .then(function (res) {
          cb.disabled = false;
          var li = cb.closest("li");
          if (res.ok && res.d && res.d.ok) {
            cb.setAttribute("data-dv-raw", encodeURIComponent(String(res.d.raw || "").trim()));
            if (res.d.line) cb.setAttribute("data-dv-line", String(res.d.line));
            if (cb.checked) cb.setAttribute("checked", ""); else cb.removeAttribute("checked");
            if (li) li.classList.toggle("task-done", cb.checked);
            dropCache();   // so lieu da doi, lan render sau lay ban moi
          } else {
            cb.checked = !cb.checked;   // hoan tac
            if (li) { li.classList.add("dv-failed"); setTimeout(function () { li.classList.remove("dv-failed"); }, 1600); }
            cb.title = (res.d && res.d.error) || tw("dview.save_failed");
          }
        })
        .catch(function () {
          cb.disabled = false; cb.checked = !cb.checked;
          cb.title = tw("dview.offline");
        });
    });

    // Nut "+ Việc" tren dau khoi: bat/tat form mini roi gui
    document.addEventListener("click", function (e) {
      var add = e.target.closest ? e.target.closest(".jv-dataview .dv-add") : null;
      if (add) {
        var el = add.closest(".jv-dataview");
        var form = el.querySelector(".dv-addform");
        if (!form) {
          form = document.createElement("div");
          form.className = "dv-addform";
          form.setAttribute("contenteditable", "false");
          form.innerHTML = '<input type="text" class="dv-add-text" placeholder="' +
            esc(tw("dview.new_task_ph")) + '">' +
            '<input type="date" class="dv-add-date" title="' +
            esc(tw("dview.due_title")) + '">' +
            '<button type="button" class="dv-add-go">' + esc(tw("proj.add")) + '</button>';
          var head = el.querySelector(".jv-dv-head");
          head.parentNode.insertBefore(form, head.nextSibling);
        }
        form.classList.toggle("open");
        if (form.classList.contains("open")) { try { form.querySelector(".dv-add-text").focus(); } catch (err) {} }
        return;
      }
      var go = e.target.closest ? e.target.closest(".jv-dataview .dv-add-go") : null;
      if (go) { submitAdd(go.closest(".jv-dataview")); return; }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.target && e.target.classList &&
          e.target.classList.contains("dv-add-text")) {
        e.preventDefault(); e.stopPropagation();
        submitAdd(e.target.closest(".jv-dataview"));
      }
    }, true);

    // Link file trong ket qua dataview: dieu huong duoc CA khi nam trong editor dang sua
    // (chat-render bo qua click trong contenteditable). Capture de chay truoc handler chung.
    document.addEventListener("click", function (e) {
      var a = e.target.closest ? e.target.closest(".jv-dataview a.jv-floc") : null;
      if (!a) return;
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button > 0) return;
      e.preventDefault(); e.stopPropagation();
      var p = a.getAttribute("data-vault-path") || "";
      if (!p) return;
      if (a.closest("#noteEditor") && typeof window.JavisOpenNote === "function") window.JavisOpenNote(p);
      else if (typeof window.JavisEditFile === "function") window.JavisEditFile(p);
      else if (typeof window.JavisOpenFiles === "function") window.JavisOpenFiles(p);
    }, true);
  }

  if (typeof window !== "undefined") {
    window.JavisDataview = { run: run, parseQuery: parseQuery, execQuery: execQuery, dropCache: dropCache };
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { parseQuery: parseQuery, execQuery: execQuery, compile: compile,
                       matchFrom: matchFrom, tokenize: tokenize, fromScope: fromScope,
                       parseTasksQuery: parseTasksQuery };
  }
})();
