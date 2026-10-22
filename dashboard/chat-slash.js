// Khung lenh / cho khung chat web. Phan LOGIC thuan (parse/route/menu) test duoc headless;
// phan menu DOM o cuoi file chi chay trong trinh duyet. Pattern giong chat-ask.js.
(function () {
  var SESSION_COMMANDS = ["new", "reset", "stop"];
  // Lệnh HỆ THỐNG: chạy tại chỗ trong khung chat, do chat-lenh.js xử lý. `needArg` = cần kèm nội
  // dung (/plan, /goal): chọn từ menu thì chỉ điền "/plan " để người dùng gõ tiếp, không chạy ngay.
  // Cũng như lệnh phiên, chỉ chạy khi đứng ĐẦU tin: "hãy /compact lại" giữa câu là một câu nói.
  var SYSTEM_COMMANDS = [
    { cmd: "help", nhan: "lenh.help_name", mota: "lenh.help_desc" },
    { cmd: "status", nhan: "lenh.status_name", mota: "lenh.status_desc" },
    { cmd: "model", nhan: "lenh.model_name", mota: "lenh.model_desc" },
    { cmd: "brain", nhan: "lenh.brain_name", mota: "lenh.brain_desc" },
    { cmd: "retry", nhan: "lenh.retry_name", mota: "lenh.retry_desc" },
    { cmd: "usage", nhan: "lenh.usage_name", mota: "lenh.usage_desc" },
    { cmd: "tasks", nhan: "lenh.tasks_name", mota: "lenh.tasks_desc" },
    { cmd: "compact", nhan: "lenh.compact_name", mota: "lenh.compact_desc" },
    { cmd: "plan", nhan: "lenh.plan_name", mota: "lenh.plan_desc", needArg: true },
    { cmd: "memory", nhan: "lenh.memory_name", mota: "lenh.memory_desc" },
    { cmd: "export", nhan: "lenh.export_name", mota: "lenh.export_desc" },
    { cmd: "goal", nhan: "lenh.goal_name", mota: "lenh.goal_desc", needArg: true },
  ];
  var SYSTEM_NAMES = SYSTEM_COMMANDS.map(function (x) { return x.cmd; });

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
    var sau = start + 1 + hit[2].length;
    var don = function (x) { return x.trim().replace(/\s{2,}/g, " "); };
    // HAI bản của phần chữ còn lại, vì hai đường dùng nó khác nhau:
    //   arg       - BỎ HẲN token (đường cộng sự: "/agent-viet" là một ĐỊA CHỈ, gửi kèm tên
    //               agent vào tin nhắn cho chính agent đó là chữ thừa);
    //   argGiuTen - giữ tên, chỉ bỏ dấu "/" (đường SKILL).
    // Vì sao đường skill phải giữ: tên skill hay là một THÀNH PHẦN của câu ("Skill
    // /viet-bai-x sẽ là skill chính"). Xoá hẳn token rồi nối hai đầu lại thì câu thành "Skill
    // sẽ là skill chính" - mất một từ, đọc ra vô nghĩa. Khách báo đúng chuyện này 16/09:
    // "chữ nó bị dịch chạy đi linh tinh".
    return { cmd: hit[2].toLowerCase(),
             arg: don(text.slice(0, start) + " " + text.slice(sau)),
             argGiuTen: don(text.slice(0, start) + hit[2] + text.slice(sau)),
             giuaCau: true };
  }

  // Vùng lệnh để TÔ MÀU trong ô nhập (0.290.0): {start, end} của đúng token mà route() sẽ dùng, hoặc null.
  // Ở đầu tin chỉ tô lệnh có thật (lệnh phiên, lệnh hệ thống, skill, cộng sự): đang gõ dở "/go" thì chưa
  // phải lệnh nào, tô lên là nói dối. Giữa câu thì như parseSlashAnywhere: skill hay cộng sự có thật, lần
  // xuất hiện cuối.
  function laCongSu(cmd) { return knownPartners.some(function (x) { return x.cmd === String(cmd || "").toLowerCase(); }); }
  function vungLenh(text) {
    if (typeof text !== "string" || text.indexOf("/") === -1) return null;
    var dau = text.match(/^\/([a-zA-Z0-9_-]+)(?=\s|$)/);
    if (dau) {
      var c = dau[1].toLowerCase();
      if (classify(c) !== "skill" || isKnownSkill(c) || laCongSu(c)) return { start: 0, end: 1 + dau[1].length };
    }
    var hit = null, m;
    MID_RE.lastIndex = 0;
    while ((m = MID_RE.exec(text)) !== null) {
      if (m.index === 0 && !m[1] && dau) continue;   // token đầu tin đã xét ở trên
      if (isKnownSkill(m[2]) || laCongSu(m[2])) hit = m;
    }
    if (!hit) return null;
    var st = hit.index + hit[1].length;
    return { start: st, end: st + 1 + hit[2].length };
  }

  // Bề rộng cột lệnh của menu, theo ký tự (font đơn cách): lệnh dài nhất trong danh sách đang hiện, có
  // sàn và trần. Mọi dòng dùng chung một bề rộng nên chữ mô tả bắt đầu thẳng một cột. Trước 0.290.0 mỗi dòng
  // tự co theo lệnh của nó, nên mô tả dòng /new và dòng /status lệch nhau (ảnh chủ repo 22/10).
  function cotLenh(items) {
    var dai = 0;
    (items || []).forEach(function (it) { dai = Math.max(dai, String(it && it.cmd || "").length + 1); });
    return Math.max(7, Math.min(dai, 18));
  }

  // Nhóm của một dòng menu: lệnh (phiên + hệ thống), cộng sự, quy trình, skill.
  function nhomCua(it) { return (it.kind === "session" || it.kind === "system") ? "cmd" : it.kind; }

  function classify(cmd) {
    if (SESSION_COMMANDS.indexOf(cmd) !== -1) return "session";
    return SYSTEM_NAMES.indexOf(cmd) !== -1 ? "system" : "skill";
  }

  // Lệnh skill đi thành một KHỐI NGỮ CẢNH đặt TRƯỚC câu người dùng, không viết lại câu đó.
  //
  // Vì sao đổi (khách báo 16/09): mẫu cũ nhồi câu của người dùng vào giữa một câu của máy -
  // "Hãy dùng skill `X` với yêu cầu: <câu của họ>. Nếu không có skill tên này thì cứ xử lý
  // yêu cầu của tôi bình thường." Server LƯU nguyên chuỗi đó làm tin của NGƯỜI DÙNG, nên mở
  // lại hội thoại là họ đọc được một câu mình chưa từng gõ, kèm một câu cuối tự xuất hiện.
  // Khách nói đúng: "nó tự sửa câu lệnh của em, tự thêm câu cuối này".
  //
  // Khối trong ngoặc vuông kết thúc bằng "]\n\n" là ĐÚNG hình dạng mà app.js (chuNguoiGo)
  // đã biết gỡ ra trước khi vẽ bong bóng - cùng đường với khối FILE ĐANG MỞ và khối đính kèm.
  // Nhờ vậy bong bóng, thanh mốc hội thoại, nút Gửi lại và nút Sửa câu hỏi đều thấy ĐÚNG câu
  // người dùng gõ, không phải câu máy dựng.
  //
  // `giuaCau`: người dùng nhắc tên skill Ở GIỮA một câu (vd "Skill viet-bai-x sẽ là skill
  // chính") thì đó là họ ĐANG NÓI VỀ skill, không hẳn là ra lệnh chạy nó - nên lời dặn nhẹ
  // hơn và nhấn "làm đúng yêu cầu bên dưới". Gõ ở ĐẦU tin mới là ra lệnh rõ ràng.
  function buildSkillInvocation(cmd, arg, giuaCau) {
    var than = String(arg || "").trim() || "/" + cmd;
    var dan = giuaCau
      ? "Người dùng có nhắc tên skill này trong câu. Dùng nó nếu phù hợp, còn lại cứ làm đúng "
        + "yêu cầu bên dưới."
      : "Hãy dùng skill này để làm việc dưới đây.";
    if (!isKnownSkill(cmd)) {
      dan += " Brain không có skill tên này thì cứ xử lý yêu cầu bên dưới như bình thường.";
    }
    return "[SKILL: " + cmd + "\n" + dan + "]\n\n" + than;
  }

  function route(text) {
    var p = parseSlashAnywhere(text);
    if (!p) return { type: "passthrough" };
    if (classify(p.cmd) === "session") return { type: "session", cmd: p.cmd };
    // Lệnh hệ thống chỉ ở ĐẦU tin. Giữa câu thì rơi xuống nhánh skill/cộng sự bên dưới (một skill
    // tình cờ trùng tên vẫn gọi được ở giữa câu như cũ).
    if (classify(p.cmd) === "system" && !p.giuaCau) return { type: "system", cmd: p.cmd, arg: p.arg };
    var partner = knownPartners.find(function (x) { return x.cmd === p.cmd; });
    if (partner) return { type: partner.kind, slug: partner.slug, message: p.arg };
    return { type: "skill", cmd: p.cmd,
             message: buildSkillInvocation(p.cmd, p.argGiuTen || p.arg, !!p.giuaCau) };
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

  function systemItems() {
    return SYSTEM_COMMANDS.map(function (x) {
      // Khoá i18n là DỮ LIỆU ở bảng trên chứ không ghép chuỗi ở đây: test_i18n quét các lời gọi tw
      // theo mặt chữ, ghép khoá lúc chạy thì nó không kiểm được khoá có tồn tại không.
      return { kind: "system", cmd: x.cmd, needArg: !!x.needArg, name: tw(x.nhan), desc: tw(x.mota) };
    });
  }

  function buildMenu(skills, agents, workflows) {
    var out = sessionItems().concat(systemItems());
    [["agent", agents], ["workflow", workflows]].forEach(function (group) {
      (group[1] || []).forEach(function (x) {
        if (!x.slug || (group[0] === "workflow" && x.status !== "active")) return;
        out.push({kind: group[0], slug: x.slug, cmd: group[0] + "-" + x.slug, name: x.name || x.slug, group: x.group || "", desc: x.role || x.description || ""});
      });
    });
    (skills || []).forEach(function (s) {
      if (!s || !s.slug) return;
      // Skill trùng tên lệnh phiên/hệ thống sẽ không bao giờ chạy được ở đầu tin (lệnh thắng),
      // nên đừng bày ra một dòng bấm vào mà không ra skill.
      if (classify(String(s.slug).toLowerCase()) !== "skill") return;
      out.push({ kind: "skill", cmd: s.slug, name: s.name || s.slug, group: s.group || "", desc: s.description || "" });
    });
    return out;
  }

  function normalizeSearch(value) {
    return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[đĐ]/g, "d").toLowerCase().replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  }
  function filterItems(items, query) {
    var q = normalizeSearch(query), words = q.split(" ").filter(Boolean);
    if (!q) return (items || []).slice();
    return (items || []).map(function (it, index) {
      var name = normalizeSearch(it.name), cmd = normalizeSearch(it.cmd);
      var extra = normalizeSearch([it.desc, it.group, it.kind].join(" "));
      var all = name + " " + cmd + " " + extra;
      if (!words.every(function (word) { return all.indexOf(word) !== -1; })) return null;
      var score = name === q || cmd === q ? 0 : name.indexOf(q) === 0 || cmd.indexOf(q) === 0 ? 1 : name.indexOf(q) >= 0 || cmd.indexOf(q) >= 0 ? 2 : 3;
      return {item: it, score: score, index: index};
    }).filter(Boolean).sort(function (a, b) { return a.score - b.score || a.index - b.index; })
      .map(function (x) { return x.item; });
  }

  // Token lenh dang go NGAY TRUOC con tro. Tra {start, query, atHead} hoac null.
  // atHead=true nghia la token bat dau tu vi tri 0 -> moi duoc hien them lenh phien.
  function tokenAtCaret(text, caret) {
    if (typeof text !== "string") return null;
    var pos = (typeof caret === "number") ? caret : text.length;
    var m = text.slice(0, pos).match(/(^|\s)\/([\p{L}\p{M}0-9_-]*)$/u);
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
    SYSTEM_COMMANDS: SYSTEM_NAMES,
    classify: classify,
    buildSkillInvocation: buildSkillInvocation,
    route: route,
    vungLenh: vungLenh,
    cotLenh: cotLenh,
    nhomCua: nhomCua,
    buildMenu: buildMenu,
    filterItems: filterItems,
    normalizeSearch: normalizeSearch,
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
      try { if (api.syncHighlight) api.syncHighlight(); } catch (e) {}   // skill vừa biết thì tô được
      return skillsCache;
    }

    function hide() { inputSeq++; if (box) box.style.display = "none"; items = []; active = 0; }

    function positionBox(input) {
      // Tu 0.153.0 o go nam trong mot khung co anh dinh kem phia tren; neo vao khung de khong che anh.
      var anchor = input.closest(".hud-voice") || input;
      var rect = anchor.getBoundingClientRect();
      box.style.left = rect.left + "px";
      box.style.width = rect.width + "px";
      box.style.bottom = (window.innerHeight - rect.top + 6) + "px";
    }

    function esc(s) {
      return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }

    // 0.290.0: một dòng mỗi lệnh. Cột lệnh chung một bề rộng (cotLenh) nên mô tả thẳng hàng; tên rồi mô tả
    // mờ nối tiếp trên cùng dòng, tràn thì "...". Chưa gõ chữ lọc thì chia nhóm có tiêu đề nhỏ; đang lọc thì
    // kết quả xếp theo độ khớp nên bỏ tiêu đề, nhãn nhóm nằm cuối dòng.
    function tenNhom(g) {
      if (g === "agent") return tw("ws.tab_agent");
      if (g === "workflow") return tw("ws.tab_workflow");
      if (g === "skill") return tw("slash.grp_skill");
      return tw("slash.grp_cmd");
    }
    function rows() { return box.querySelectorAll(".slash-item"); }
    function renderList() {
      box.innerHTML = "";
      box.style.setProperty("--slash-cmdw", api.cotLenh(items) + "ch");
      var coTieuDe = !(tok && tok.query), nhomTruoc = null;
      items.forEach(function (it, i) {
        var g = api.nhomCua(it);
        if (coTieuDe && g !== nhomTruoc) {
          var h = document.createElement("div");
          h.className = "slash-head";
          h.textContent = tenNhom(g);
          box.appendChild(h);
        }
        nhomTruoc = g;
        var row = document.createElement("div");
        row.className = "slash-item" + (i === active ? " active" : "");
        row.setAttribute("role", "option");
        row.innerHTML = '<span class="slash-cmd">/' + esc(it.cmd) + '</span>' +
          '<span class="slash-text"><span class="slash-name">' + esc(it.name) + '</span>' +
          (it.desc ? '<span class="slash-desc">' + esc(it.desc) + '</span>' : '') + '</span>' +
          (!coTieuDe && g !== "cmd" ? '<span class="slash-kind">' + esc(tenNhom(g)) + '</span>' : '');
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
      if (it.kind !== "session" && !(it.kind === "system" && !it.needArg)) {
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
        // Lenh phien va lenh he thong khong can noi dung kem: chay ngay.
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
      // Lenh phien (/new /reset /stop) va lenh he thong chi hien khi token o DAU o nhap: giua cau ma bam
      // /reset thi mat sach ngu canh dang viet do, khong ai muon vay.
      var all = tok.atHead ? buildMenu(skills, agentsCache, workflowsCache) : buildMenu(skills, agentsCache, workflowsCache).filter(function (x) { return x.kind !== "session" && x.kind !== "system"; });
      items = filterItems(all, tok.query);
      active = 0;
      if (!items.length) { hide(); return; }
      positionBox(input);
      renderList();
      box.style.display = "block";
    }

    function onKeydown(e) {
      if (!box || box.style.display === "none") return;
      if (e.key === "ArrowDown") { e.preventDefault(); active = (active + 1) % items.length; renderList(); rows()[active].scrollIntoView({block: "nearest"}); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = (active - 1 + items.length) % items.length; renderList(); rows()[active].scrollIntoView({block: "nearest"}); }
      else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); e.stopImmediatePropagation(); choose(active); }
      else if (e.key === "Escape") { e.preventDefault(); hide(); }
    }

    // ===== Tô màu lệnh đã gõ trong ô nhập (0.290.0) =====
    // Ô <textarea> không tô màu được từng chữ, nên đặt một lớp GƯƠNG ngay dưới nó: cùng font, cùng lề,
    // cùng bề rộng, chữ y hệt, riêng token lệnh bọc trong <mark>. Khi có lệnh, chữ của ô nhập trong suốt
    // (con trỏ vẫn hiện) và người dùng nhìn thấy chữ của gương. Không có lệnh thì gương ẩn, ô nhập như cũ.
    // Giá trị ô nhập hay bị app.js gán thẳng (gửi xong thì xoá) mà không bắn sự kiện input, nên trong lúc
    // đang tô, mỗi khung hình soi lại giá trị: lệch là vẽ lại ngay, không để gương hiện chữ cũ.
    var hl = null, hlKey = "", hlLoop = 0;
    var CHEP = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "wordSpacing",
      "textIndent", "textTransform", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "tabSize"];
    function syncHl() {
      var input = document.getElementById("chatInput");
      if (!input) return;
      var v = input.value, r = api.vungLenh(v);
      if (!r) {
        input.classList.remove("has-cmd");
        if (hl) hl.hidden = true;
        hlKey = "";
        if (hlLoop) { cancelAnimationFrame(hlLoop); hlLoop = 0; }
        return;
      }
      if (!hl) {
        hl = document.createElement("div");
        hl.className = "ci-hl";
        hl.setAttribute("aria-hidden", "true");
        input.parentNode.insertBefore(hl, input);
      } else if (hl.nextSibling !== input) {
        input.parentNode.insertBefore(hl, input);
      }
      var key = v + "|" + input.scrollTop + "|" + input.clientWidth + "|" + input.clientHeight + "|" + input.offsetTop;
      if (key !== hlKey || hl.hidden) {
        hlKey = key;
        var cs = getComputedStyle(input);
        CHEP.forEach(function (p) { hl.style[p] = cs[p]; });
        hl.style.top = input.offsetTop + "px";
        hl.style.left = input.offsetLeft + "px";
        hl.style.width = input.clientWidth + "px";
        hl.style.height = input.clientHeight + "px";
        hl.innerHTML = esc(v.slice(0, r.start)) + '<mark class="ci-cmd">' + esc(v.slice(r.start, r.end)) + "</mark>" +
          esc(v.slice(r.end)) + "\n";
        hl.hidden = false;
        hl.scrollTop = input.scrollTop;
        input.classList.add("has-cmd");
      }
      if (hlLoop) cancelAnimationFrame(hlLoop);
      hlLoop = requestAnimationFrame(function () { hlLoop = 0; syncHl(); });
    }
    api.syncHighlight = syncHl;

    api._initMenu = function () {
      var input = document.getElementById("chatInput");
      if (!input) return;
      input.addEventListener("input", onInput);
      input.addEventListener("input", syncHl);
      input.addEventListener("scroll", syncHl);
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
