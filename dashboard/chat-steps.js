/* chat-steps.js - khoi "tien trinh tung buoc" trong khung chat Javis.

   Van de: server DA ban ra su kien tool_call cho moi engine (main.py), nhung dashboard chi co
   MOT dong trang thai (showActivity): buoc moi ghi de buoc cu, het luot thi xoa sach. Luot
   chay lau thi nguoi dung ngoi nhin mot dong nhay loan, khong biet da lam nhung gi.

   File nay gom cac buoc do lai thanh mot khoi nam ngay tren bong bong tra loi:
     - MAC DINH GAP ca luc dang chay lan luc xong (chu repo yeu cau 2026-09-24: hai chuc dong
       "Dang goi: Bash" bung san day kin khung chat). Dong tom tat van noi dang chay, bao nhieu
       buoc va buoc moi nhat; bam vao moi bung ra. Nguoi dung da bam bung thi giu bung.
     - moi buoc ghi RO viec: "Chay lenh: git status", "Doc file: wiki/a.md" (server gui kem
       truong `detail` rut tu tham so lenh goi, xem server/tool_label.py)

   Chia lam hai tang de test duoc bang node: `nhan`/`tomTat` la ham THUAN (khong dung DOM),
   con `taoKhoi`/`ve` chi ve. Khong goi MCP, khong phu thuoc engine.

   An toan: nhan buoc la chu do SERVER gui xuong (ten cong cu, nhan do model dat) nen phai
   escape het truoc khi nhet vao innerHTML.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  // Tran so buoc GIU LAI de ve. Mot loop goi hang tram cong cu thi ve het la dung khung chat
  // lam bai log. Tong so buoc van dem du (truong `so`) nen dong tom tat khong noi doi.
  var TRAN = 50;

  // Chu hien ra lay tu tu dien. Trong trinh duyet la window.t; duoi node - noi test require()
  // thang file nay - `window` CHUA KHAI BAO nen phai hoi bang typeof, roi doc thang vi.json.
  // Cung khuon voi chat-ask.js.
  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  function esc(t) {
    return String(t == null ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Loai cong cu -> KHOA i18n cua dong tu nguoi doc duoc (viet du khoa de test_i18n soi duoc).
  // Ten lay theo cac engine that (Claude Code, Codex,
  // Grok, Antigravity, API); ten la thi giu nguyen ten cong cu, khong doan.
  var LOAI = [
    [/^(bash|shell|run_shell_command|command_execution|local_shell_call|run_terminal_command|run_command|exec)$/, "app.step_v_run"],
    [/^(read|read_file|view|view_file|notebookread|read_many_files|cat)$/, "app.step_v_read"],
    [/^(write|write_file|create_file|write_to_file)$/, "app.step_v_write"],
    [/^(edit|multiedit|notebookedit|str_replace|str_replace_editor|apply_patch|edit_file|replace|patch)$/, "app.step_v_edit"],
    [/^(grep|search_file_content|grep_search|codebase_search)$/, "app.step_v_grep"],
    [/^(glob|ls|list_directory|list_dir|find|find_by_name)$/, "app.step_v_find"],
    [/^(webfetch|web_fetch|fetch|read_url_content|fetch_url)$/, "app.step_v_web"],
    [/^(websearch|web_search|web_search_call|google_search|search_web)$/, "app.step_v_search"],
    [/^(task|agent)$/, "app.step_v_agent"],
    [/^(todowrite|todo_write|update_plan|todo_list|javis_plan|taskcreate|taskupdate)$/, "app.step_v_todo"],
    [/^(skill|javis_use_skill)$/, "app.step_v_skill"]
  ];
  function loaiCongCu(ten) {
    var t = String(ten || "").toLowerCase().trim();
    for (var i = 0; i < LOAI.length; i++) if (LOAI[i][0].test(t)) return LOAI[i][1];
    return "";
  }
  // "mcp__zalo__zalo_send_message" -> "zalo_send_message": phan dau chi la ten may chu.
  function tenGon(ten) {
    var t = String(ten || "").trim();
    var m = t.match(/^mcp__[^_]+(?:_[^_]+)*?__(.+)$/);
    return m ? m[1] : t;
  }

  // Nhan mot dong buoc. Co `detail` (server rut tu tham so lenh goi) thi ghi ro viec:
  // "Chay lenh: git status". Khong co thi giu cau server dat san ("Dang goi: pos_order"),
  // bo ky tu banh rang U+2699 dan dau vi khoi nay tu ve icon rieng.
  // Cat bang lop "moi ky tu dau khong phai chu/so" chu KHONG viet thang ky tu banh rang vao
  // day: test_icons.py cam emoji trong file dashboard. Luat rong nay cung ben hon khi server
  // doi sang dau khac.
  function nhanBuoc(ev) {
    var ten = String((ev && ev.tool) || "").trim();
    var ct = String((ev && ev.detail) || "").replace(/\s+/g, " ").trim();
    var loai = loaiCongCu(tenGon(ten));
    if (ct) return (loai ? tw(loai) : tenGon(ten) || tw("app.step_unknown")) + ": " + ct;
    if (loai) return tw(loai);
    var noi = String((ev && ev.content) || "").replace(/^[^\p{L}\p{N}]+/u, "").trim();
    if (noi) return noi;
    return ten || tw("app.step_unknown");
  }

  function chuanHoa(st) {
    var ds = (st && Array.isArray(st.ds)) ? st.ds : [];
    var so = (st && typeof st.so === "number" && isFinite(st.so)) ? st.so : ds.length;
    var out = { ds: ds, so: so };
    if (st && Array.isArray(st.plan) && st.plan.length) out.plan = st.plan;
    return out;
  }

  /* ---------- The turn's plan (owner, 08/11/2026) ----------
     The engine's own checklist for a long task: Claude Code TodoWrite / TaskCreate / TaskUpdate, Codex update_plan,
     Grok todo_write. The server reads it from the tool call (server/turn_plan.py) and sends one op per frame under
     `plan`: "set" (the whole list), "add" (one item, its id comes in the tool result), "update" (one item by id).
     Item: { id, text, st } with st "pending" | "active" | "done". Pure, tested under node. */
  var PLAN_MAX = 30;
  var PLAN_ST = { pending: "pending", active: "active", done: "done",
                  in_progress: "active", inprogress: "active", completed: "done", complete: "done" };
  function planSt(v, dflt) {
    return PLAN_ST[String(v || "").toLowerCase()] || dflt;
  }

  function applyPlan(plan, op) {
    var cur = Array.isArray(plan) ? plan : [];
    if (!op || typeof op !== "object") return cur;
    if (op.op === "set" && Array.isArray(op.items)) {
      return op.items.slice(0, PLAN_MAX).map(function (x, i) {
        return { id: String(i + 1), text: String((x && x.text) || ""), st: planSt(x && x.status, "pending") };
      }).filter(function (x) { return x.text; });
    }
    if (op.op === "add" && op.text) {
      if (cur.length >= PLAN_MAX) return cur;
      // No id yet: Claude Code names it in the tool result ("Task #3 created"), see planResult.
      return cur.concat([{ id: "", text: String(op.text), st: "pending", waiting: true }]);
    }
    if (op.op === "update" && op.id != null) {
      var id = String(op.id), hit = false;
      var next = [];
      cur.forEach(function (x) {
        if (x.id !== id) { next.push(x); return; }
        hit = true;
        if (op.status === "deleted") return;
        next.push({ id: x.id, text: op.text ? String(op.text) : x.text,
                    st: planSt(op.status, x.st) });
      });
      // An id this turn never saw (made in an earlier turn) is left alone: there is no text to show for it.
      return hit ? next : cur;
    }
    return cur;
  }

  // A tool result naming the id of a task created this turn ("Task #3 created successfully: ...").
  function planResult(plan, content) {
    var cur = Array.isArray(plan) ? plan : [];
    var m = String(content || "").match(/task\s*#\s*(\w+)/i);
    if (!m) return cur;
    for (var i = 0; i < cur.length; i++) {
      if (cur[i].waiting) {
        var next = cur.slice();
        next[i] = { id: m[1], text: cur[i].text, st: cur[i].st };
        return next;
      }
    }
    return cur;
  }

  // { n, done, now }: how many items, how many done, the text of the one running (else the first not done).
  function planSummary(plan) {
    var ds = Array.isArray(plan) ? plan : [];
    var done = 0, now = "", next = "";
    ds.forEach(function (x) {
      if (x.st === "done") done++;
      else if (x.st === "active" && !now) now = x.text;
      else if (!next) next = x.text;
    });
    return { n: ds.length, done: done, now: now || next };
  }

  // One line for the activity chip under the chat: "Plan 2/5: Write the tests". "" without a plan.
  function planLine(st) {
    var p = chuanHoa(st).plan;
    if (!p) return "";
    var s = planSummary(p);
    var head = tw("app.plan_progress", { done: s.done, n: s.n });
    return s.now && s.done < s.n ? head + ": " + s.now : head;
  }

  /* Gop mot su kien WS vao mach buoc. Ham THUAN: tra ve state MOI, khong sua state cu.
     Chi tool_call moi sinh buoc - `status` ("dang suy nghi") va `stream` la trang thai cua ca
     luot, khong phai viec da lam. */
  function nhan(st, ev) {
    var cu = chuanHoa(st);
    var loai = ev && ev.type;
    var plan = cu.plan;
    if (loai === "tool_call") {
      var ds = cu.ds.concat([{ tool: String((ev && ev.tool) || ""), label: nhanBuoc(ev), xong: false }]);
      if (ds.length > TRAN) ds = ds.slice(ds.length - TRAN);   // giu cac buoc MOI NHAT
      if (ev && ev.plan) plan = applyPlan(plan, ev.plan);
      return withPlan({ ds: ds, so: cu.so + 1 }, plan);
    }
    if (loai === "tool_result") {
      if (plan) plan = planResult(plan, ev && ev.content);
      // Danh dau buoc dang chay la xong. Khung tool_result lac long (chua co buoc nao) thi bo
      // qua - khong phai loi, chi la engine ban ket qua cua thu khong di qua day.
      for (var i = cu.ds.length - 1; i >= 0; i--) {
        if (!cu.ds[i].xong) {
          var ds2 = cu.ds.slice();
          ds2[i] = { tool: cu.ds[i].tool, label: cu.ds[i].label, xong: true };
          return withPlan({ ds: ds2, so: cu.so }, plan);
        }
      }
      return withPlan({ ds: cu.ds, so: cu.so }, plan);
    }
    return cu;
  }

  function withPlan(st, plan) {
    if (Array.isArray(plan) && plan.length) st.plan = plan;
    return st;
  }

  /* Luot KHONG goi cong cu nao thi `hien` = false: app.js khong dung khoi nao ca. Mot dong
     xam "Da chay 0 buoc" duoi moi cau chao hoi la rac. */
  function tomTat(st) {
    var cu = chuanHoa(st);
    return { hien: cu.ds.length > 0, so: cu.so, nhan: tw("app.steps_done", { n: cu.so }) };
  }

  function icon(name) {
    return (typeof ic === "function") ? ic(name) : "";
  }

  // The plan card: always open, even while the step list is folded, because it is the part worth reading.
  function planHtml(plan, running) {
    var s = planSummary(plan);
    var rows = plan.map(function (x) {
      var cls = "plan-item plan-" + x.st + (running && x.st === "active" ? " plan-live" : "");
      var ico = x.st === "done" ? "circle-check" : x.st === "active" ? "circle-dot" : "circle";
      return '<li class="' + cls + '">' + icon(ico) + '<span class="plan-text">' + esc(x.text) + "</span></li>";
    }).join("");
    return '<div class="plan-head">' + icon("list-checks") + "<span>" +
           esc(tw("app.plan_progress", { done: s.done, n: s.n })) + "</span></div>" +
           '<ul class="plan-list">' + rows + "</ul>";
  }

  function chevron() {
    return (typeof ic === "function") ? ic("chevron-down") : "›";
  }

  function taoKhoi() {
    var el = document.createElement("div");
    el.className = "msg msg-steps steps-fold";
    el.innerHTML =
      '<button class="steps-sum" type="button">' + chevron() +
      '<span class="steps-sum-text"></span><span class="steps-sum-now"></span></button>' +
      '<div class="steps-plan" hidden></div>' +
      '<div class="steps-list"></div>';
    var nut = el.querySelector(".steps-sum");
    if (nut) {
      nut.setAttribute("aria-label", tw("app.steps_toggle"));
      nut.addEventListener("click", function () {
        el.classList.toggle("steps-fold");
        // Nho lua chon cua nguoi dung: lan ve lai sau (moi buoc moi) khong duoc gap nguoc.
        el._moTay = !el.classList.contains("steps-fold");
        if (nut.setAttribute) nut.setAttribute("aria-expanded", el._moTay ? "true" : "false");
      });
      nut.setAttribute("aria-expanded", "false");
    }
    return el;
  }

  /* Ve lai khoi theo mach buoc. MAC DINH GAP, ca luc dang chay: dong tom tat da noi dang
     chay, bao nhieu buoc, buoc moi nhat la gi. Chi bung khi nguoi dung bam (`_moTay`). */
  function ve(el, st, dangChay) {
    if (!el) el = taoKhoi();
    // Nhớ mạch để vẽ lại khi từ điển về (xem bộ nghe "javis:i18n" cuối file).
    el._st = st; el._dangChay = !!dangChay;
    var cu = chuanHoa(st);
    var txt = el.querySelector(".steps-sum-text");
    if (txt) txt.textContent = dangChay ? tw("app.steps_running_n", { n: cu.so }) : tomTat(cu).nhan;
    var now = el.querySelector(".steps-sum-now");
    if (now) {
      var cuoi = cu.ds.length ? cu.ds[cu.ds.length - 1] : null;
      now.textContent = (dangChay && cuoi) ? cuoi.label : "";
    }
    var pl = el.querySelector(".steps-plan");
    if (pl) {
      if (cu.plan) { pl.innerHTML = planHtml(cu.plan, !!dangChay); pl.hidden = false; }
      else { pl.innerHTML = ""; pl.hidden = true; }
    }
    var ds = el.querySelector(".steps-list");
    if (ds) {
      ds.innerHTML = cu.ds.map(function (b, i) {
        var song = dangChay && i === cu.ds.length - 1 && !b.xong;
        return '<div class="step' + (song ? " step-live" : "") + (b.xong ? " step-done" : "") +
               '" title="' + esc(b.label) + '">' + esc(b.label) + "</div>";
      }).join("");
    }
    el.classList.toggle("steps-fold", el._moTay !== true);
    return el;
  }

  var API = { nhan: nhan, tomTat: tomTat, taoKhoi: taoKhoi, ve: ve, nhanDong: nhanBuoc, TRAN: TRAN,
              applyPlan: applyPlan, planResult: planResult, planSummary: planSummary, planLine: planLine,
              planHtml: planHtml };
  if (typeof window !== "undefined") window.JavisSteps = API;
  // Mở lại hội thoại (restoreSession) vẽ khối bước TRƯỚC khi từ điển tải xong, lúc đó t() trả
  // về chính cái khoá, nên người dùng thấy chữ thô "app.steps_done" (chủ repo báo 27/09). Từ
  // điển về thì vẽ lại mọi khối đang có.
  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("javis:i18n", function () {
      var ds = document.querySelectorAll(".msg-steps");
      for (var i = 0; i < ds.length; i++) {
        if (ds[i]._st) { try { ve(ds[i], ds[i]._st, ds[i]._dangChay); } catch (e) {} }
      }
    });
  }
  if (typeof module !== "undefined" && module.exports) module.exports = API;

  /* The switch for javis_plan, the plan tool of the API brains (server/plan_tool.py), in the composer "+" menu.
     Claude Code, Codex and Grok plan with their own tools and are not affected. Stored on the server
     (settings.chat.plan_tool), read once. */
  if (typeof document === "undefined" || typeof window === "undefined" || typeof fetch !== "function" ||
      typeof document.addEventListener !== "function") return;
  var planTool = { enabled: true, loaded: false };
  function loadPlanTool() {
    if (planTool.loaded) return;
    planTool.loaded = true;
    fetch("/chat/plan", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.enabled === false) planTool.enabled = false; }).catch(function () {});
  }
  function setPlanTool(on) {
    var fd = new FormData();
    fd.append("section", "chat");
    fd.append("data", JSON.stringify({ plan_tool: !!on }));
    return fetch("/settings", { method: "POST", body: fd, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d && d.ok !== false) planTool.enabled = !!on; })
      .catch(function () {});
  }
  function registerPlanMenu() {
    if (!window.JavisComposerMenu || !window.JavisComposerMenu.register) return false;
    loadPlanTool();
    window.JavisComposerMenu.register({
      id: "plan-tool", order: 91, label: "app.plan_menu",
      icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 5h8M13 12h8M13 19h8M3 17l2 2 4-4M3 7l2 2 4-4"/></svg>',
      hint: function () { return tw(planTool.enabled ? "app.plan_menu_on" : "app.plan_menu_off"); },
      run: function () { setPlanTool(!planTool.enabled); },
    });
    return true;
  }
  if (!registerPlanMenu()) document.addEventListener("DOMContentLoaded", registerPlanMenu);
})();
