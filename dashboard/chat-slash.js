// Khung lenh / cho khung chat web. Phan LOGIC thuan (parse/route/menu) test duoc headless;
// phan menu DOM o cuoi file chi chay trong trinh duyet. Pattern giong chat-ask.js.
(function () {
  var SESSION_COMMANDS = ["new", "reset", "stop"];

  // Chu hien ra lay tu tu dien. Trong trinh duyet la window.t (i18n/index.js nap dau tien);
  // duoi node (test require file nay) khong co window nen doc thang vi.json. Chu tw chu
  // khong phai t: ham choose() ben duoi da co bien cuc bo ten t, viet t( la goi nham no.
  function tw(khoa) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa);
    try { return require("./i18n/vi.json")[khoa] || khoa; } catch (e) { return khoa; }
  }

  // Danh sach slug skill dang co (menu nap tu /skills rot vao). Chi dung cho lenh GIUA cau:
  // o giua cau ma bat bua theo hinh dang thi '/home/user/x' hay '3/4 cai' cung thanh lenh.
  var knownSkills = [];
  var knownPartners = [];
  function setKnownPartners(agents, workflows) { knownPartners = buildMenu([], agents, workflows).filter(function (x) { return x.kind === "agent" || x.kind === "workflow"; }); }
  function setKnownSkills(list) {
    knownSkills = [];
    (list || []).forEach(function (s) {
      var slug = (typeof s === "string") ? s : (s && s.slug);
      if (slug) knownSkills.push(String(slug).toLowerCase());
    });
  }
  function isKnownSkill(cmd) { return knownSkills.indexOf(String(cmd || "").toLowerCase()) !== -1; }

  // Nhan dien lenh: bat dau bang / + token [a-z0-9_-], phan sau la arg.
  function parseSlash(text) {
    if (typeof text !== "string") return null;
    var m = text.match(/^\/([a-zA-Z0-9_-]+)(?:\s+([\s\S]*))?$/);
    if (!m) return null;
    return { cmd: m[1].toLowerCase(), arg: (m[2] || "").trim() };
  }

  // Lenh nam GIUA cau: "test sual skill giua khung chat /viet-email" -> skill viet-email,
  // arg la phan chu con lai. Rang buoc de khoi bat nham:
  //   - dau '/' phai dung dau chuoi hoac ngay sau khoang trang (giet 'https://', '3/4');
  //   - token phai la skill CO THAT (giet '/home/user/x');
  //   - lenh phien (/new /reset /stop) KHONG tinh o giua cau - "hay /reset lai" ma reset
  //     that thi mat sach ngu canh, do la pha hoai chu khong phai tien.
  // Lay lan xuat hien CUOI cung: nguoi dung vua go xong o cuoi cau la y dinh moi nhat.
  var MID_RE = /(^|\s)\/([a-zA-Z0-9_-]+)(?=\s|$)/g;
  function parseSlashAnywhere(text) {
    if (typeof text !== "string") return null;
    var head = parseSlash(text);
    if (head) return head;                       // dau chuoi: giu nguyen hanh vi cu
    var hit = null, m;
    MID_RE.lastIndex = 0;
    while ((m = MID_RE.exec(text)) !== null) {
      if (isKnownSkill(m[2]) || knownPartners.some(function (x) { return x.cmd === m[2].toLowerCase(); })) hit = m;
    }
    if (!hit) return null;
    var start = hit.index + hit[1].length;
    var rest = (text.slice(0, start) + " " + text.slice(start + 1 + hit[2].length)).trim();
    return { cmd: hit[2].toLowerCase(), arg: rest.replace(/\s{2,}/g, " ") };
  }

  function classify(cmd) {
    return SESSION_COMMANDS.indexOf(cmd) !== -1 ? "session" : "skill";
  }

  // Khop DUNG mau fallback cua Telegram (server/main.py) de 2 kenh nhat quan.
  function buildSkillInvocation(cmd, arg) {
    return "Hãy dùng skill `" + cmd + "`" +
      (arg ? " với yêu cầu: " + arg : "") +
      ". Nếu không có skill tên này thì cứ xử lý yêu cầu của tôi bình thường.";
  }

  function route(text) {
    var p = parseSlashAnywhere(text);
    if (!p) return { type: "passthrough" };
    if (classify(p.cmd) === "session") return { type: "session", cmd: p.cmd };
    var partner = knownPartners.find(function (x) { return x.cmd === p.cmd; });
    if (partner) return { type: partner.kind, slug: partner.slug, message: p.arg };
    return { type: "skill", cmd: p.cmd, message: buildSkillInvocation(p.cmd, p.arg) };
  }

  // Ham chu khong phai hang: nhan phai lay tu dien lai moi lan dung menu, vi nguoi dung
  // co the doi ngon ngu giua chung ma khong tai lai trang.
  function sessionItems() {
    return [
      { kind: "session", cmd: "new", name: tw("top.new_chat"), desc: tw("slash.new_desc") },
      { kind: "session", cmd: "reset", name: tw("slash.reset_name"), desc: tw("slash.reset_desc") },
      { kind: "session", cmd: "stop", name: tw("slash.stop_name"), desc: tw("slash.stop_desc") },
    ];
  }

  function buildMenu(skills, agents, workflows) {
    var out = sessionItems();
    [["agent", agents], ["workflow", workflows]].forEach(function (group) {
      (group[1] || []).forEach(function (x) {
        if (!x.slug || (group[0] === "workflow" && x.status !== "active")) return;
        out.push({kind: group[0], slug: x.slug, cmd: group[0] + "-" + x.slug, name: x.name || x.slug, desc: x.role || x.description || ""});
      });
    });
    (skills || []).forEach(function (s) {
      if (!s || !s.slug) return;
      out.push({ kind: "skill", cmd: s.slug, name: s.name || s.slug, desc: s.description || "" });
    });
    return out;
  }

  function filterItems(items, query) {
    var q = (query || "").toLowerCase();
    if (!q) return (items || []).slice();
    var scored = [];
    (items || []).forEach(function (it) {
      var cmd = (it.cmd || "").toLowerCase();
      var name = (it.name || "").toLowerCase();
      var score = -1;
      if (cmd.indexOf(q) === 0) score = 0;            // cmd khop tien to - uu tien nhat
      else if (cmd.indexOf(q) !== -1) score = 1;      // cmd chua query
      else if (name.indexOf(q) !== -1) score = 2;     // ten chua query
      if (score >= 0) scored.push({ it: it, score: score });
    });
    scored.sort(function (a, b) { return a.score - b.score; });
    return scored.map(function (x) { return x.it; });
  }

  // Token lenh dang go NGAY TRUOC con tro. Tra {start, query, atHead} hoac null.
  // atHead=true nghia la token bat dau tu vi tri 0 -> moi duoc hien them lenh phien.
  function tokenAtCaret(text, caret) {
    if (typeof text !== "string") return null;
    var pos = (typeof caret === "number") ? caret : text.length;
    var m = text.slice(0, pos).match(/(^|\s)\/([a-zA-Z0-9_-]*)$/);
    if (!m) return null;
    var start = m.index + m[1].length;
    return { start: start, query: m[2], atHead: start === 0 };
  }

  var api = {
    parseSlash: parseSlash,
    parseSlashAnywhere: parseSlashAnywhere,
    tokenAtCaret: tokenAtCaret,
    setKnownSkills: setKnownSkills,
    setKnownPartners: setKnownPartners,
    SESSION_COMMANDS: SESSION_COMMANDS,
    classify: classify,
    buildSkillInvocation: buildSkillInvocation,
    route: route,
    buildMenu: buildMenu,
    filterItems: filterItems,
  };

  if (typeof window !== "undefined") window.JavisSlash = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;

  // ===== Phan MENU DOM (chi trinh duyet) =====
  if (typeof window !== "undefined" && typeof document !== "undefined") {
    var box = null, items = [], active = 0, skillsCache = null, cacheBrain = null, agentsCache = [], workflowsCache = [], loadedAt = 0, inputSeq = 0;

    function ensureBox() {
      if (box) return box;
      box = document.createElement("div");
      box.id = "slashMenu";
      box.className = "slash-menu";
      box.style.display = "none";
      document.body.appendChild(box);
      return box;
    }

    async function loadSkills() {
      var brain = (typeof window.currentBrainPath === "function") ? window.currentBrainPath() : "brain";
      if (skillsCache && cacheBrain === brain && Date.now() - loadedAt < 5000) return skillsCache;
      try {
        var results = await Promise.all(["skills", "agents", "workflows"].map(async function (kind) {
          try { var r = await fetch("/" + kind + "?brain=" + encodeURIComponent(brain)); if (!r.ok) return {}; return await r.json(); } catch (e) { return {}; }
        }));
        var d = results[0]; agentsCache = results[1].agents || []; workflowsCache = results[2].workflows || [];
        api.setKnownPartners(agentsCache, workflowsCache); loadedAt = Date.now();
        skillsCache = (d && d.skills) || [];
      } catch (e) { skillsCache = []; }
      cacheBrain = brain;
      // route() can biet slug CO THAT de dam nhan duoc lenh giua cau (xem parseSlashAnywhere).
      api.setKnownSkills(skillsCache);
      return skillsCache;
    }

    function hide() { inputSeq++; if (box) box.style.display = "none"; items = []; active = 0; }

    function positionBox(input) {
      var rect = input.getBoundingClientRect();
      box.style.left = rect.left + "px";
      box.style.width = rect.width + "px";
      box.style.bottom = (window.innerHeight - rect.top + 6) + "px";
    }

    function esc(s) {
      return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    function renderList() {
      box.innerHTML = "";
      items.forEach(function (it, i) {
        var row = document.createElement("div");
        row.className = "slash-item" + (i === active ? " active" : "");
        row.innerHTML = '<span class="slash-cmd">/' + esc(it.cmd) + '</span>' +
          '<span class="slash-name">' + esc(it.kind === 'agent' ? tw('ws.tab_agent') + ' · ' : it.kind === 'workflow' ? tw('ws.tab_workflow') + ' · ' : '') + esc(it.name) + '</span>' +
          '<span class="slash-desc">' + esc(it.desc) + '</span>';
        row.addEventListener("mousedown", function (e) { e.preventDefault(); choose(i); });
        box.appendChild(row);
      });
    }

    var tok = null;   // token dang go tai con tro (tokenAtCaret cua lan onInput gan nhat)

    function choose(i) {
      var it = items[i];
      if (!it) return;
      var input = document.getElementById("chatInput");
      var t = tok;
      hide();
      if (it.kind !== "session") {
        // Thay DUNG token dang go, giu nguyen chu hai ben - go lenh giua cau khong duoc
        // xoa cau dang viet. Khong ro token thi rot ve hanh vi cu (thay ca o).
        var val = input.value;
        var end = t ? t.start + 1 + t.query.length : val.length;
        var ins = "/" + it.cmd + " ";
        input.value = t ? (val.slice(0, t.start) + ins + val.slice(end)) : ins;
        var caret = (t ? t.start : 0) + ins.length;
        input.focus();
        try { input.setSelectionRange(caret, caret); } catch (e) {}
        input.dispatchEvent(new Event("input"));
      } else {
        // Lenh phien: chay ngay.
        input.value = "";
        if (typeof window.JavisSend === "function") window.JavisSend("/" + it.cmd);
      }
    }

    async function onInput() {
      var input = document.getElementById("chatInput");
      // Mo menu khi dang go token lenh NGAY TRUOC con tro - dau o hay giua cau deu duoc.
      tok = api.tokenAtCaret(input.value, input.selectionStart);
      if (!tok) { hide(); return; }
      ensureBox();
      var seq = ++inputSeq;
      var skills = await loadSkills();
      if (seq !== inputSeq || !api.tokenAtCaret(input.value, input.selectionStart)) return;
      // Lenh phien (/new /reset /stop) chi hien khi token o DAU o nhap: giua cau ma bam
      // /reset thi mat sach ngu canh dang viet do, khong ai muon vay.
      var all = tok.atHead ? buildMenu(skills, agentsCache, workflowsCache) : buildMenu(skills, agentsCache, workflowsCache).filter(function (x) { return x.kind !== "session"; });
      items = filterItems(all, tok.query);
      active = 0;
      if (!items.length) { hide(); return; }
      positionBox(input);
      renderList();
      box.style.display = "block";
    }

    function onKeydown(e) {
      if (!box || box.style.display === "none") return;
      if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % items.length; renderList(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + items.length) % items.length; renderList(); }
      else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); e.stopImmediatePropagation(); choose(active); }
      else if (e.key === "Escape") { e.preventDefault(); hide(); }
    }

    api._initMenu = function () {
      var input = document.getElementById("chatInput");
      if (!input) return;
      input.addEventListener("input", onInput);
      // Keydown PHAI dang ky TRUOC app.js (cung element -> chay theo thu tu dang ky). Script
      // nay nap truoc app.js va #chatInput da ton tai, nen init DONG BO ngay o duoi. Khi menu
      // mo, onKeydown goi stopImmediatePropagation chan handler Enter cua app.js.
      input.addEventListener("keydown", onKeydown);
      input.addEventListener("blur", function () { setTimeout(hide, 120); });
      // Nap truoc danh sach skill: lenh GIUA cau chi duoc nhan khi slug co that, ma nguoi
      // dung hoan toan co the go tay '/viet-email' ma khong mo menu lan nao. Khong nap
      // truoc thi lan go tay dau tien roi thang xuong chat thuong.
      loadSkills().catch(function () {});
    };
    // #chatInput co san luc script chay -> init ngay de dang ky truoc app.js. Phong ho: neu
    // chua co (load-order doi ve sau), doi DOMContentLoaded.
    if (document.getElementById("chatInput")) {
      api._initMenu();
    } else {
      document.addEventListener("DOMContentLoaded", api._initMenu);
    }
  }
})();
