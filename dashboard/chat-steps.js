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
    [/^(todowrite|todo_write|update_plan)$/, "app.step_v_todo"],
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
    return { ds: ds, so: so };
  }

  /* Gop mot su kien WS vao mach buoc. Ham THUAN: tra ve state MOI, khong sua state cu.
     Chi tool_call moi sinh buoc - `status` ("dang suy nghi") va `stream` la trang thai cua ca
     luot, khong phai viec da lam. */
  function nhan(st, ev) {
    var cu = chuanHoa(st);
    var loai = ev && ev.type;
    if (loai === "tool_call") {
      var ds = cu.ds.concat([{ tool: String((ev && ev.tool) || ""), label: nhanBuoc(ev), xong: false }]);
      if (ds.length > TRAN) ds = ds.slice(ds.length - TRAN);   // giu cac buoc MOI NHAT
      return { ds: ds, so: cu.so + 1 };
    }
    if (loai === "tool_result") {
      // Danh dau buoc dang chay la xong. Khung tool_result lac long (chua co buoc nao) thi bo
      // qua - khong phai loi, chi la engine ban ket qua cua thu khong di qua day.
      for (var i = cu.ds.length - 1; i >= 0; i--) {
        if (!cu.ds[i].xong) {
          var ds2 = cu.ds.slice();
          ds2[i] = { tool: cu.ds[i].tool, label: cu.ds[i].label, xong: true };
          return { ds: ds2, so: cu.so };
        }
      }
    }
    return cu;
  }

  /* Luot KHONG goi cong cu nao thi `hien` = false: app.js khong dung khoi nao ca. Mot dong
     xam "Da chay 0 buoc" duoi moi cau chao hoi la rac. */
  function tomTat(st) {
    var cu = chuanHoa(st);
    return { hien: cu.ds.length > 0, so: cu.so, nhan: tw("app.steps_done", { n: cu.so }) };
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
    var cu = chuanHoa(st);
    var txt = el.querySelector(".steps-sum-text");
    if (txt) txt.textContent = dangChay ? tw("app.steps_running_n", { n: cu.so }) : tomTat(cu).nhan;
    var now = el.querySelector(".steps-sum-now");
    if (now) {
      var cuoi = cu.ds.length ? cu.ds[cu.ds.length - 1] : null;
      now.textContent = (dangChay && cuoi) ? cuoi.label : "";
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

  var API = { nhan: nhan, tomTat: tomTat, taoKhoi: taoKhoi, ve: ve, nhanDong: nhanBuoc, TRAN: TRAN };
  if (typeof window !== "undefined") window.JavisSteps = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
