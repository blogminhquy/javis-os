// ============================================
// JAVIS OS - Console layer (sidebar + router)
// Bọc ngoài cockpit: rail điều hướng + trang quản lý. KHÔNG sửa app.js.
// Đồ thị tự pause khi rời cockpit (qua window.__javisGraph). Alpine cho UI.
// Thêm trang mới = thêm 1 mục vào RAIL_ITEMS + 1 case trong renderPage().
// ============================================
(function () {
  "use strict";

  // Locale để định dạng số/ngày. Lấy từ i18n chứ KHÔNG khoá "vi-VN": người dùng đổi
  // ngôn ngữ giao diện thì ngày giờ phải đổi theo, nếu không thì nửa màn hình tiếng Anh
  // mà ngày vẫn dd/mm/yyyy kiểu Việt.
  const LOC = () => (window.JavisI18n && JavisI18n.locale()) || "vi-VN";
  // ---- Khai báo các mục trên rail (mở rộng = thêm dòng ở đây) ----
  // type 'view' = render trong cview ; có launch() = nút mở overlay/modal sẵn có.
  const APP_VERSION = "0.4.3";   // fallback hiển thị tức thời; nguồn thật là /version (file VERSION)

  // Icon của TỪNG TRANG, khai MỘT LẦN ở đây. Cả thanh rail (ICON) lẫn tiêu đề
  // trang (VIEW_META) đều lấy từ bảng này, nên hai chỗ không bao giờ lệch nhau -
  // trước đây mỗi trang khai icon hai lần và đã lệch thật (Kanban trùng icon
  // với Tệp tin, Tài khoản trùng với Cài đặt).
  //
  // Giá trị là TÊN icon Lucide. Tra tên tại https://lucide.dev/icons/, thêm vào
  // dashboard/icons.manifest.json rồi chạy python tools/gen_icons.py.
  const VIEW_ICON = {
    home: "hexagon",
    chat: "message-circle",
    settings: "settings",
    workflows: "workflow",
    agents: "bot",
    chatbots: "headset",
    skills: "puzzle",
    files: "folder-tree",
    selfimprove: "repeat",
    learn: "brain",
    kanban: "square-kanban",
    terminal: "terminal",
    models: "cpu",
    channels: "send",
    mcp: "plug",
    plugins: "toolbox",
    logs: "scroll-text",
    account: "circle-user",
    usage: "chart-column",
  };
  // Cỡ icon rail do CSS lo (.rail-ico svg { width: 19px }), độ ưu tiên chọn tử
  // cao hơn .ic nên không cần truyền cỡ ở đây.
  const ICON = Object.fromEntries(
    Object.entries(VIEW_ICON).map(([id, name]) => [id, ic(name)])
  );

  // Icon cho TẦNG 1 (nhãn nhóm) - chỉ dùng ở header nhóm rail.
  const GICON = {
    "Trợ lý": ic("sparkles"),
    "Bộ não": ic("brain"),
    "Code": ic("file-code"),
    "Năng lực": ic("lightbulb"),
    "Việc": ic("clipboard-check"),
    "Kết nối": ic("link"),
    "Hệ thống": ic("sliders-horizontal"),
  };
  // Icon nút thu/mở sidebar: kiểu "panel sidebar". Tĩnh, không xoay.
  const COLLAPSE_ICON = ic("panel-left");

  // Ba icon trạng thái dùng dày đặc trong file này (~80 chỗ). Khai sẵn thành
  // hằng cho câu ngắn và khỏi lặp lời gọi dài. ic() trả về chuỗi nên đây chỉ là
  // chuỗi hằng, ghép thoải mái.
  //
  // Khi chữ đi kèm là chuỗi TỪ SERVER thì đừng ghép tay: dùng Icons.warn(text)
  // hoặc Icons.ok(text) để chữ được escape. Ghép tay chỉ dành cho chữ tĩnh
  // hoặc chữ đã qua esc() rồi.
  const WARN_ICON = ic("triangle-alert", { cls: "ic-warn" });
  const OK_ICON = ic("circle-check", { cls: "ic-ok" });
  const CHECK_ICON = ic("check", { cls: "ic-ok" });
  const SAVE_ICON = ic("save");
  const X_ICON = ic("x");

  // Nhãn rail lấy từ TỪ ĐIỂN (thư mục dashboard/i18n) chứ không viết cứng. `t()` suy biến về
  // tiếng Việt khi thiếu key, nên một bản dịch làm dở không bao giờ để lại key trần trên rail.
  const RAIL_ITEMS = [
    "home", "chat", "settings", "workflows", "agents", "skills", "chatbots", "files",
    "terminal", "selfimprove", "learn", "kanban", "models", "channels", "mcp", "plugins",
    "logs", "account", "usage",
  ].map(id => ({ id, icon: ICON[id], get label() { return t(`page.${id}.label`); } }));

  // ---- Gom rail thành nhóm theo chức năng (dễ tìm hơn danh sách phẳng 18 mục) ----
  // Nhóm cuối (foot:true) được ghim xuống ĐÁY rail; các nhóm còn lại cuộn ở giữa.
  // Thứ tự & thành viên đổi ở đây; RAIL_ITEMS vẫn là nguồn icon/label + tra cứu cho go().
  const RAIL_GROUPS = [
    { get label() { return t("nav.group.tro_ly"); },      icon: GICON["Trợ lý"],   ids: ["home", "chat"] },
    { get label() { return t("nav.group.bo_nao"); },      icon: GICON["Bộ não"],   ids: ["files", "learn"] },
    // "Code" là NHÓM riêng, không phải một mục nhét vào "Bộ não". Đây là một KHU VỰC làm việc
    // sẽ dày lên (Terminal hôm nay, các công cụ lập trình khác sau này), chứ không phải một
    // chức năng của Second Brain - chủ repo nói rõ điều đó khi thấy bản đầu xếp nhầm.
    // Thêm chức năng Code mới = thêm 1 mục vào RAIL_ITEMS + 1 id vào đây + 1 dòng trong
    // CHUC_NANG của dashboard/code-term.js.
    { get label() { return t("nav.group.code"); },        icon: GICON["Code"],     ids: ["terminal"] },
    { get label() { return t("nav.group.nang_luc"); },    icon: GICON["Năng lực"], ids: ["agents", "chatbots", "skills", "workflows", "plugins"] },
    { get label() { return t("nav.group.viec"); },        icon: GICON["Việc"],     ids: ["kanban", "selfimprove"] },
    { get label() { return t("nav.group.ket_noi"); },     icon: GICON["Kết nối"],  ids: ["mcp", "channels", "models"] },
    { get label() { return t("nav.group.he_thong"); },    icon: GICON["Hệ thống"], ids: ["usage", "settings", "logs", "account"], foot: true },
  ];
  const RAIL_BY_ID = Object.fromEntries(RAIL_ITEMS.map(i => [i.id, i]));
  // Trả về [{label, foot, items:[...]}], bỏ id không tồn tại. Mục nào chưa xếp nhóm → dồn vào "Khác".
  function railGroups() {
    const seen = new Set();
    const groups = RAIL_GROUPS.map(g => {
      const items = (g.ids || []).map(id => { seen.add(id); return RAIL_BY_ID[id]; }).filter(Boolean);
      return { label: g.label, icon: g.icon || "", foot: !!g.foot, items };
    }).filter(g => g.items.length);
    const rest = RAIL_ITEMS.filter(i => !seen.has(i.id));
    if (rest.length) {
      const foot = groups.find(g => g.foot);
      if (foot) foot.items.push(...rest); else groups.push({ label: "Khác", foot: false, items: rest });
    }
    return groups;
  }
  // Nhãn nhóm chứa một mục id (cho accordion: mở đúng nhóm của trang đang xem).
  function groupLabelOf(id) {
    const g = RAIL_GROUPS.find(gr => (gr.ids || []).includes(id));
    return g ? g.label : (RAIL_GROUPS[0] && RAIL_GROUPS[0].label) || "";
  }

  // icon lấy từ VIEW_ICON ở đầu file - đừng khai icon riêng ở đây, hai bảng
  // lệch nhau là lỗi đã xảy ra một lần rồi.
  // Tiêu đề + phụ đề của mỗi trang, lấy từ TỪ ĐIỂN. Dùng getter chứ không đọc `t()` một lần
  // lúc nạp: từ điển về bất đồng bộ, và đọc sớm thì mọi nhãn đóng băng ở giá trị lúc chưa có.
  //
  // `page.<id>.title` cho phép tiêu đề trang KHÁC nhãn trên rail khi cần (rail chật nên
  // "Việc", trang rộng nên "Việc (Kanban)"); thiếu key đó thì tự rơi về `page.<id>.label`.
  const VIEW_META = Object.fromEntries(["home", "chat", "settings", "workflows", "agents", "skills", "files", "terminal", "selfimprove", "chatbots", "learn", "kanban", "models", "channels", "mcp", "plugins", "logs", "account", "usage"].map(id => [id, {
    icon: VIEW_ICON[id],
    get label() {
      const rieng = t(`page.${id}.title`);
      return rieng === `page.${id}.title` ? t(`page.${id}.label`) : rieng;
    },
    get sub() {
      const v = t(`page.${id}.sub`);
      return v === `page.${id}.sub` ? "" : v;
    },
  }]));

  // 4 trang tách từ Studio cũ - render container rồi gọi loader trong studio.js (window.JavisStudio).
  const STUDIO_PAGES = ["workflows", "agents", "skills"];

  let _settings = null;
  let _renderGen = 0;         // token chống race: mỗi lần đổi trang tăng 1; render async cũ tự bỏ
  let _fmPending = null;       // { dir, file } - vị trí mở sẵn cho trang Tệp tin (khi bấm link file/thư mục trong chat)
  let _fmSauKhiDong = null;    // việc trang Tệp tin cần làm khi đóng trình sửa (nạp lại danh sách)
  let graphEnabled = true;
  const isNarrow = () => window.matchMedia("(max-width: 860px)").matches;
  const liteMode = () => !graphEnabled || isNarrow();

  const esc = (s) => (s || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  // Chỉ cho link http(s) (chặn javascript:/data: XSS); dùng kèm esc() khi nhúng vào href.
  const safeHref = (u) => /^https?:\/\//i.test((u || "").toString().trim()) ? u : "#";
  const _shield = (on) => on
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V5l8-3z"/><path d="M9 12l2 2 4-4"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V5l8-3z"/></svg>';
  const body = () => document.getElementById("cviewBody");

  /** Phân trang phía client cho các khung nhật ký: tải một lần rồi lật trang tại chỗ.
   *
   * Dùng chung cho nhật ký loop (trang Việc định kỳ), nhật ký học + commit học (trang Tự học)
   * và bảng "Lượt gần nhất" (trang Tiết kiệm). Trước đây chỉ trang Việc định kỳ có, viết
   * thẳng trong hàm render của nó; hai trang kia thì cắt cứng ở 10 và 12 mục. Chép khối đó
   * ra thành bản thứ hai và thứ ba là ba bản trôi lệch nhau ngay lần sửa đầu tiên.
   *
   * KHÔNG dùng cuộn vô hạn: mấy khung này nằm GIỮA trang còn nội dung phía dưới, cuộn vô hạn
   * sẽ nuốt luôn đường xuống phần đó.
   *
   * @param box       node chứa (bị ghi đè innerHTML)
   * @param items     mảng đã sắp sẵn, mới nhất trước
   * @param perPage   số mục mỗi trang
   * @param renderPage  (mảng con) -> chuỗi HTML
   * @param emptyHtml HTML hiện khi không có mục nào
   */
  function pager(box, items, perPage, renderPage, emptyHtml) {
    if (!box) return;
    const all = items || [];
    if (!all.length) { box.innerHTML = emptyHtml || `<div class="dim" style="color:var(--text3)">Chưa có gì.</div>`; return; }
    const pages = Math.max(1, Math.ceil(all.length / perPage));
    let page = 0;
    const draw = () => {
      page = Math.min(Math.max(0, page), pages - 1);
      const nav = pages > 1 ? `<div class="jv-pager">
          <button class="s-btn-ghost" data-pg="prev"${page === 0 ? " disabled" : ""}>← Trước</button>
          <span class="jv-pager-n">Trang ${page + 1}/${pages} · ${all.length} mục</span>
          <button class="s-btn-ghost" data-pg="next"${page >= pages - 1 ? " disabled" : ""}>Sau →</button>
        </div>` : "";
      box.innerHTML = renderPage(all.slice(page * perPage, page * perPage + perPage)) + nav;
      const p = box.querySelector('[data-pg="prev"]'), n = box.querySelector('[data-pg="next"]');
      if (p) p.onclick = () => { page--; draw(); };
      if (n) n.onclick = () => { page++; draw(); };
    };
    draw();
  }

  // Pause SỚM (chạy ngay khi parse, không chờ Alpine tải): màn hẹp → graph app.js vừa dựng
  // dừng luôn, khỏi ngốn pin/GPU trong lúc Alpine đang tải. _animate có guard _paused nên
  // dù load() chạy xong gọi lại cũng không bật lại.
  if (isNarrow() && window.__javisGraph) { try { window.__javisGraph.pause(); } catch (e) {} }

  // ---- Điều khiển graph: chỉ chạy khi đang ở cockpit + không lite + không mở Studio ----
  function recomputeGraph() {
    const g = window.__javisGraph;
    if (!g) return;
    const studioOpen = !!document.getElementById("studio")?.classList.contains("open");
    const active = window.Alpine ? Alpine.store("nav").active : "home";
    const shouldRun = !liteMode() && active === "home" && !studioOpen;
    if (shouldRun) g.wake(); else g.pause();
  }

  // ---- Chuyển trang (có View Transition cho mượt) ----
  // Hook "rời trang": trang nào mượn DOM dùng chung (vd tab Trò chuyện mượn khung chat của
  // cockpit) đặt _pageLeave để TRẢ node về chỗ cũ TRƯỚC khi cviewBody bị ghi đè / cview bị ẩn.
  let _pageLeave = null;
  // Trang cũ đã gộp đi đâu. Giữ bảng này thay vì xoá trắng: người dùng có bookmark, có nút
  // trong chat, và có thói quen. Bấm vào một id đã biến mất mà không có chỗ đáp là màn hình
  // trắng không giải thích gì.
  const TRANG_GOP = { runtime: "usage" };
  function navigateTo(id) {
    id = TRANG_GOP[id] || id;
    const store = Alpine.store("nav");
    if (store.active === id) return;   // đang ở trang này → khỏi đổi (tránh nháy + mượn/trả node thừa)
    const swap = () => {
      const leave = _pageLeave; _pageLeave = null;
      if (leave) { try { leave(); } catch (e) {} }   // dọn trang cũ trước khi thay nội dung
      // (Trước 0.12.4 ở đây còn một nhát thu lớp chat phóng to. Lớp nổi đó đã bỏ - phóng to
      // giờ là chuyển hẳn sang trang Trò chuyện, và _pageLeave ở trên đã trả node về HUD.)
      store.active = id;
      // Về nơi có hiển thị model thì làm mới, phòng khi model bị đổi bằng đường khác
      // (trang Models, Cài đặt nhanh, hoặc chỉnh tay settings).
      if (id === "home" || id === "chat") refreshModelUi();
      // Nút điều khiển cockpit (cài đặt, giọng nói, làm mới) chỉ hiện ở trang Javis, không hiện navbar trang quản lý
      document.body.classList.toggle("in-console", id !== "home");
      // Rời trang Cài đặt → cất #quickSet về holder TRƯỚC khi cviewBody bị ghi đè (giữ node + handler).
      if (id !== "settings") parkQuickSet();
      if (id !== "home") renderPage(id);
      recomputeGraph();
    };
    // Dính tab Trò chuyện thì bỏ View Transition: nó chụp snapshot đồ thị của home rồi
    // cross-fade → loé orb ~1s (bitmap chụp trước cả khi ẩn graph). Swap thẳng cho sạch, tức thì.
    const skipVT = (id === "chat" || store.active === "chat");
    if (document.startViewTransition && !skipVT) document.startViewTransition(swap);
    else swap();
  }

  // Mở trang Tệp tin ĐÚNG vị trí một file/thư mục (gọi từ link trong chat qua window.JavisOpenFiles,
  // hoặc từ deep-link #open=<đường-dẫn> khi mở ở tab trình duyệt mới). fullPath tương đối GỐC BRAIN
  // (đúng quy ước AI ghi trong chat); trang Tệp tin sẽ tự ghép tiền tố brain để ra path tương đối trần.
  function openFilesAt(fullPath) {
    const raw = String(fullPath == null ? "" : fullPath);
    const clean = raw.replace(/^\.?\//, "").replace(/\/+$/, "");
    const i = clean.lastIndexOf("/");
    const base = i >= 0 ? clean.slice(i + 1) : clean;
    const parent = i >= 0 ? clean.slice(0, i) : "";
    const isDir = /\/$/.test(raw) || (base !== "" && base.indexOf(".") < 0);   // gạch chéo cuối hoặc không có đuôi → thư mục
    _fmPending = isDir ? { dir: clean, file: "" } : { dir: parent, file: base };
    const active = window.Alpine ? Alpine.store("nav").active : "";
    if (active === "files") renderPage("files");   // đã ở trang Tệp tin → nạp lại để nhảy tới vị trí mới
    else navigateTo("files");
  }
  if (typeof window !== "undefined") window.JavisOpenFiles = openFilesAt;
  // Bấm một đường dẫn vault: file SỬA ĐƯỢC thì mở thẳng TRÌNH SỬA, còn lại mới về trang Tệp tin.
  //
  // Vì sao gom vào một hàm: cùng một link trong chat có HAI đường đi tới đây - cú bấm thường
  // (chat-render.js bắt được, gọi moFileVault) và deep-link `#open=` (Ctrl/chuột giữa mở tab
  // mới, hoặc tải lại trang khi hash còn đó). Trước bản này đường thứ hai đổ thẳng vào
  // openFilesAt, nên cùng một file .html lúc thì mở ra sửa được lúc thì quăng người dùng về
  // thư mục - đúng cái "thi thoảng nó vẫn bị gửi về folder" chủ repo báo (2026-08-13). Một
  // quyết định, mọi người gọi chung.
  function openVaultPath(fullPath) {
    const raw = String(fullPath == null ? "" : fullPath);
    const clean = raw.replace(/^\.?\//, "").replace(/\/+$/, "");
    const base = clean.split("/").pop();
    // Không có dấu chấm trong tên = thư mục, cùng luật với openFilesAt và chat-render.js.
    const laThuMuc = /\/$/.test(raw) || !base || base.indexOf(".") < 0;
    const duoi = base.indexOf(".") >= 0 ? "." + base.split(".").pop().toLowerCase() : "";
    if (!laThuMuc && VT_TEXT_EXTS.includes(duoi)) {
      // Màn rộng: trình sửa đính bên cây. Màn hẹp: modal của file-editor.js - ở đây người dùng
      // bấm ĐÚNG một file nên đừng chặn như nhánh node đồ thị.
      if (!isNarrow() && typeof window.JavisOpenNote === "function") {
        window.JavisOpenNote(clean); return;
      }
      if (typeof window.JavisEditFile === "function") { window.JavisEditFile(clean); return; }
    }
    openFilesAt(fullPath);
  }
  if (typeof window !== "undefined") window.JavisOpenVaultPath = openVaultPath;
  // Mở note trong editor cây từ đường dẫn TƯƠNG ĐỐI GỐC BRAIN (như openNodePopup). Người gọi: click node
  // đồ thị (app.js onGraphNodeClick) VÀ wikilink [[..]] trong chat-render.js - đều truyền MỘT chuỗi path.
  // ĐỪNG gán đè hàm này bằng openNote thô: mất bước suy tên/đuôi file → note .md rơi nhánh "hãy tải về"
  // (đã dính ở 0.9.152).
  if (typeof window !== "undefined") window.JavisOpenNote = function (brainRel) {
    if (!brainRel) return;
    // Trên điện thoại KHÔNG mở trình sửa: node trên đồ thị quá nhỏ nên chạm gần như luôn
    // trúng nhầm note, và trình sửa mở ra rồi thì thanh nút tràn khỏi màn hẹp nên khó thoát.
    // Mở nhầm một note rồi mắc kẹt trong đó tệ hơn hẳn là không mở.
    if (isNarrow()) {
      if (window.JavisToast) window.JavisToast("Sửa note trên điện thoại đã tắt - mở trên máy tính để chỉnh sửa.");
      else alert("Sửa note trên điện thoại đã tắt. Mở trên máy tính để chỉnh sửa.");
      return;
    }
    const ceilingRel = _vtHome ? _vtHome + "/" + brainRel : brainRel;   // ghép tiền tố trần như cây
    const name = brainRel.split("/").pop();
    const ext = name.includes(".") ? "." + name.split(".").pop().toLowerCase() : ".md";
    openNote(ceilingRel, { name: name, ext: ext, type: "file" });
    // Đi tới một file bằng LINK thì cây bên cạnh phải sổ tới đúng nhánh chứa nó. Không có
    // nhát này thì mở xong vẫn không biết file nằm đâu, lần sau lại phải đi tìm lại từ đầu.
    // Đặt ở wrapper chứ không trong openNote: openNote còn được chính cây gọi khi bấm node,
    // ở đó cây đã đúng chỗ rồi, dựng lại là thừa.
    try { _vtRevealInTree(ceilingRel); } catch (e) {}
  };
  // Mở lại một file bằng đường dẫn THEO TRẦN DUYỆT (đã có sẵn tiền tố nhà brain). Người gọi:
  // chip "file đang mở" dưới khung chat (app.js) - ghim giữ đúng dạng path mà openNote nhận,
  // nên gọi thẳng vào đây; đi vòng qua JavisOpenNote sẽ ghép tiền tố trần LẦN HAI và mở hụt.
  // Trả về true nếu đã mở được; false = người gọi tự lo đường lui (khung sửa bung giữa màn).
  if (typeof window !== "undefined") window.JavisOpenNoteAt = function (ceilRel, name) {
    if (!ceilRel) return false;
    // Màn hẹp không có chỗ cho trình sửa đính, nhưng ở đây người dùng bấm ĐÚNG một file đã biết
    // (khác click nhầm node đồ thị) nên đừng chặn - trả false để app.js rơi về JavisEditFile.
    if (isNarrow()) return false;
    const ed = document.getElementById("noteEditor");
    if (!ed) return false;
    // Đúng file này đang mở sẵn: chỉ đưa mắt về, TUYỆT ĐỐI không openNote lại - openNote đọc lại
    // file từ đĩa nên chữ đang gõ dở mà chưa lưu sẽ bay sạch.
    if (!ed.hidden && _neOpenRel && _neOpenRel === ceilRel) {
      if (document.body.classList.contains("on-chat")) _borrowNoteEditor();
      try { ed.scrollIntoView({ block: "nearest" }); } catch (e) {}
      try { (document.getElementById("neWys") || document.getElementById("neText")).focus(); } catch (e) {}
      return true;
    }
    // Đuôi file suy từ ĐƯỜNG DẪN chứ không từ `name`: tên hiển thị của ghim có lúc là cả
    // đường dẫn (lúc server không trả tên), mà thư mục cũng có thể chứa dấu chấm.
    const fileName = String(ceilRel).split("/").pop();
    const ext = fileName.includes(".") ? "." + fileName.split(".").pop().toLowerCase() : ".md";
    openNote(ceilRel, { name: name || fileName, ext: ext, type: "file" });
    try { _vtRevealInTree(ceilRel); } catch (e) {}
    return true;
  };
  // Xổ cây tới đúng nhánh chứa `path` (đường dẫn theo TRẦN DUYỆT). Phơi ra cho chỗ khác gọi
  // mà không phải chép lại cơ chế xổ cây thứ hai.
  if (typeof window !== "undefined") window.JavisRevealInTree = (path) => _vtRevealInTree(path);

  // ============================================
  // Render từng trang vào #cviewBody
  // ============================================
  async function renderPage(id) {
    let el = body();
    if (!el) return;
    // Thay #cviewBody bằng node MỚI mỗi lần đổi trang: renderer async của trang CŨ (đang await
    // fetch) nếu ghi trễ (el.innerHTML=...) sẽ ghi vào node cũ ĐÃ THÁO RỜI → vô hại, không phá
    // nội dung/nút của trang mới. Đặc biệt bảo vệ các node chat mà tab Trò chuyện mượn vào
    // cviewBody (trước đây bị 1 render async trễ xoá mất → chat vỡ). Cũng hết nháy nội dung cũ.
    const fresh = el.cloneNode(false); el.parentNode.replaceChild(fresh, el); el = fresh;
    _renderGen++;   // đổi trang → vô hiệu mọi render async đang dở (guard bổ sung cho renderer đã có)
    if (id === "chat")     return renderChat(el);
    if (STUDIO_PAGES.includes(id)) return renderStudioPage(el, id);
    if (id === "settings") return renderSettings(el);
    if (id === "models")   return renderModels(el);
    if (id === "mcp")      return renderConnect(el);
    if (id === "plugins")  return renderPlugins(el);
    if (id === "channels") return renderChannels(el);
    if (id === "account")  return renderAccount(el);
    if (id === "files")    return renderFiles(el);
    if (CODE_PAGES.includes(id)) return renderCode(el, id);
    if (id === "selfimprove") return renderSelfImprove(el);
    if (id === "chatbots") return renderChatbots(el);
    if (id === "learn")    return renderLearn(el);
    if (id === "kanban")   return renderKanban(el);
    if (id === "logs")     return renderLogs(el);
    if (id === "usage")    return renderUsage(el);
    el.innerHTML = placeholder(id);
  }

  // Trang Studio: tạo panel-<id> trong cview rồi gọi loader cũ (studio.js fill vào đó).
  function renderStudioPage(el, id) {
    el.innerHTML = `<div class="stab-panel" id="panel-${id}"></div>`;
    const fn = window.JavisStudio && window.JavisStudio[id];
    if (fn) { try { fn(); } catch (e) { el.innerHTML = placeholder(id, "Lỗi nạp: " + e.message); } }
    else el.innerHTML = placeholder(id, "studio.js chưa sẵn sàng.");
  }

  // Các trang thuộc nhóm Code, đều do code-term.js dựng. Thêm chức năng Code mới thì thêm id
  // vào đây (và vào RAIL_ITEMS + RAIL_GROUPS + VIEW_META + CHUC_NANG bên code-term.js).
  const CODE_PAGES = ["terminal"];

  // Trang Code do code-term.js dựng (uỷ quyền như trang Chatbot). Trang này KHÁC mọi trang
  // khác ở hai chỗ, nên có thêm mấy dòng dưới đây:
  //   - nó chiếm trọn khung và tự cuộn bên trong (terminal cần chiều cao thật để tính số
  //     dòng), nên cviewBody phải bỏ padding + bỏ cuộn: lớp .cview-flush;
  //   - nó giữ một WebSocket + một ResizeObserver, phải dọn TRƯỚC khi cviewBody bị ghi đè,
  //     nếu không thì mỗi lần ghé qua lại bỏ lại một socket sống.
  // _pageLeave lo cả hai. (Lớp .cview-flush phải gỡ bằng tay: renderPage clone lại cviewBody
  // bằng cloneNode(false), mà clone đó GIỮ NGUYÊN class - để lại thì trang sau mất padding.)
  function renderCode(el, id) {
    const fn = window.JavisCode && window.JavisCode.render;
    if (!fn) { el.innerHTML = placeholder(id, "code-term.js chưa sẵn sàng."); return; }
    _pageLeave = () => {
      el.classList.remove("cview-flush");
      try { window.JavisCode.roi(); } catch (e) {}
    };
    try { fn(el, id); } catch (e) { el.innerHTML = placeholder(id, "Lỗi nạp: " + e.message); }
  }

  // Trang Chatbot do chatbots.js dựng - uỷ quyền y như renderStudioPage uỷ cho studio.js,
  // để console.js không phình thêm một màn hình nữa.
  function renderChatbots(el) {
    const fn = window.JavisChatbots && window.JavisChatbots.render;
    if (fn) { try { fn(el); } catch (e) { el.innerHTML = placeholder("chatbots", "Lỗi nạp: " + e.message); } }
    else el.innerHTML = placeholder("chatbots", "chatbots.js chưa sẵn sàng.");
  }

  function placeholder(id, note) {
    const m = VIEW_META[id] || {};
    return `<div class="cview-placeholder">
      <div class="ph-ico">${ic(m.icon || "sparkles", { cls: "ic-xl" })}</div>
      <div><b>${esc(m.label || id)}</b> - đang phát triển</div>
      <div style="max-width:380px;font-size:14px;opacity:.7">${esc(note || "Trang này là chỗ cắm chức năng mở rộng sau. Khung điều hướng đã sẵn sàng.")}</div>
    </div>`;
  }

  // ============================================
  // Trang Mức dùng (token & chi phí Javis tự đo, có đồ thị 14 ngày)
  // ============================================
  let _uzCss = false;
  function _injectUsageCss() {
    if (_uzCss) return; _uzCss = true;
    const css = `
    .uz-wrap{max-width:840px}
    .uz-cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:24px}
    .uz-card{flex:1 1 150px;background:var(--glass);border:1px solid var(--glass-brd);border-radius:12px;padding:14px 16px}
    .uz-card .uz-k{font-size:12px;color:var(--text3);letter-spacing:.3px}
    .uz-card .uz-v{font-size:23px;font-weight:700;color:var(--text);margin-top:4px;font-variant-numeric:tabular-nums}
    .uz-card .uz-sub{font-size:12px;color:var(--text2);margin-top:4px}
    .uz-card.accent .uz-v{color:var(--accent)}
    .uz-sec-h{font-size:12px;color:var(--text3);text-transform:uppercase;letter-spacing:1px;margin:0 0 12px;font-weight:600}
    .uz-chart{display:flex;align-items:flex-end;gap:5px;height:150px;padding:6px 2px 0}
    .uz-bar-col{flex:1 1 0;display:flex;align-items:flex-end;justify-content:center;height:100%;min-width:0;cursor:default}
    .uz-bar{width:64%;max-width:24px;background:linear-gradient(180deg,var(--accent),var(--accent-ink));border-radius:4px 4px 0 0;transition:opacity .15s;min-height:3px}
    .uz-bar.empty{background:rgba(255,255,255,.07)}
    .uz-bar-col:hover .uz-bar{opacity:.75}
    .uz-xlabels{display:flex;gap:5px;border-top:1px solid var(--glass-brd);padding-top:5px;margin-bottom:26px}
    .uz-xl{flex:1 1 0;text-align:center;font-size:9.5px;color:var(--text3);white-space:nowrap;overflow:hidden}
    .uz-tbl{width:100%;border-collapse:collapse;font-size:13.5px}
    .uz-tbl th{text-align:left;color:var(--text3);font-weight:600;font-size:12px;padding:6px 10px;border-bottom:1px solid var(--glass-brd)}
    .uz-tbl td{padding:8px 10px;border-bottom:1px solid var(--surface-2);font-variant-numeric:tabular-nums}
    .uz-tbl td.num{text-align:right;color:var(--link-ink)}
    .uz-tbl .uz-prov{color:var(--text)}
    .uz-tbl .uz-mdl{color:var(--text3);font-size:12px}
    .uz-note{margin-top:20px;font-size:12px;color:var(--text3);line-height:1.55;max-width:640px}`;
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
  }
  const _uzTok = (n) => { n = +n || 0; if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M"; if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k"; return "" + n; };
  const _uzCost = (c) => (+c > 0 ? "$" + (+c).toFixed(+c < 0.01 ? 4 : 2) : "-");
  const _UZ_PROV = { cli: "Claude Code", codex: "ChatGPT", openrouter: "OpenRouter", openai: "OpenAI", "anthropic-api": "Anthropic" };
  const _uzModel = (m) => (m || "").split("/").pop().replace(/^(claude-|gpt-)/, "").slice(0, 26);

  async function renderUsage(el) {
    // Trang Token nâng cấp (usage.js): index log thô Claude+Codex + lọc kỳ/provider + insight.
    // Ủy quyền sang module mới nếu đã nạp; nếu chưa thì rơi về bảng cũ (usage_store 30 ngày).
    if (window.JavisUsage && window.JavisUsage.render) { try { return window.JavisUsage.render(el); } catch (e) {} }
    _injectUsageCss();
    el.innerHTML = `<div class="uz-wrap"><div class="cview-placeholder" style="min-height:200px"><div class="ph-ico">${ic("loader", { cls: "ic-xl ic-spin" })}</div><div class="dim">Đang tải mức dùng...</div></div></div>`;
    let d;
    try { d = await (await fetch("/usage")).json(); }
    catch (e) { el.innerHTML = `<div class="uz-wrap"><div class="cview-placeholder"><div class="ph-ico">${ic("chart-column", { cls: "ic-xl ic-dim" })}</div><div>Không tải được dữ liệu mức dùng.</div></div></div>`; return; }
    const daily = d.daily || [];
    const today = d.today || { items: [], total: { in: 0, out: 0, cost: 0, turns: 0 } };
    const all = d.all_time || { items: [], total: { in: 0, out: 0, cost: 0, turns: 0 } };
    const tt = today.total, at = all.total;

    const orCard = (d.openrouter && d.openrouter.remaining != null)
      ? `<div class="uz-card"><div class="uz-k">OpenRouter còn</div><div class="uz-v" style="color:var(--green)">$${(+d.openrouter.remaining).toFixed(2)}</div><div class="uz-sub">đã dùng $${(+(d.openrouter.used || 0)).toFixed(2)}</div></div>` : "";
    const cards = `<div class="uz-cards">
      <div class="uz-card accent"><div class="uz-k">Hôm nay</div><div class="uz-v">${_uzTok(tt.in + tt.out)}</div><div class="uz-sub">${_uzTok(tt.in)}↑ ${_uzTok(tt.out)}↓ · ${tt.turns || 0} lượt${tt.cost > 0 ? " · $" + tt.cost.toFixed(2) : ""}</div></div>
      <div class="uz-card"><div class="uz-k">Tổng tích luỹ</div><div class="uz-v">${_uzTok(at.in + at.out)}</div><div class="uz-sub">${_uzTok(at.in)}↑ ${_uzTok(at.out)}↓${at.cost > 0 ? " · $" + at.cost.toFixed(2) : ""}</div></div>
      ${orCard}
    </div>`;

    const maxv = Math.max(1, ...daily.map(x => x.in + x.out));
    const bars = daily.map(x => {
      const v = x.in + x.out, h = v > 0 ? Math.max(3, Math.round(v / maxv * 100)) : 0;
      const tip = `${x.day}: ${_uzTok(v)} token${x.cost > 0 ? " · $" + x.cost.toFixed(2) : ""} · ${x.turns || 0} lượt`;
      return `<div class="uz-bar-col" title="${esc(tip)}"><div class="uz-bar ${v > 0 ? "" : "empty"}" style="height:${h}%"></div></div>`;
    }).join("");
    const xlabels = daily.map(x => `<div class="uz-xl">${esc(x.day.slice(8))}</div>`).join("");
    const chart = daily.length ? `<div class="uz-sec-h">${daily.length} ngày gần nhất · token/ngày</div>
      <div class="uz-chart">${bars}</div><div class="uz-xlabels">${xlabels}</div>` : "";

    const scope = today.items.length ? "hôm nay" : "tổng tích luỹ";
    const items = today.items.length ? today.items : all.items;
    const rows = items.length ? items.map(i => `<tr>
        <td><span class="uz-prov">${esc(_UZ_PROV[i.provider] || i.provider)}</span> <span class="uz-mdl">${esc(_uzModel(i.model))}</span></td>
        <td class="num">${_uzTok(i.in)}</td><td class="num">${_uzTok(i.out)}</td>
        <td class="num">${i.turns || 0}</td><td class="num">${_uzCost(i.cost)}</td></tr>`).join("")
      : `<tr><td colspan="5" style="padding:16px;color:var(--text3)">Chưa có lượt nào.</td></tr>`;
    const table = `<div class="uz-sec-h">Theo nhà cung cấp · ${scope}</div>
      <table class="uz-tbl"><thead><tr><th>Nhà cung cấp / model</th><th style="text-align:right">Token vào</th><th style="text-align:right">Token ra</th><th style="text-align:right">Lượt</th><th style="text-align:right">Chi phí</th></tr></thead><tbody>${rows}</tbody></table>`;

    el.innerHTML = `<div class="uz-wrap">${cards}${chart}${table}
      <div class="uz-note">Số liệu do Javis tự đo từ token vào/ra của mọi engine (Claude Code, ChatGPT/Codex, OpenRouter...), không phụ thuộc nhà cung cấp có lộ hạn mức hay không. Chi phí chỉ hiện khi nhà cung cấp trả về giá thật (vd Claude Code CLI); còn lại chỉ đếm token. Lưu 30 ngày gần nhất.</div>
    </div>`;
  }

  // ============================================
  // Trang Cập nhật (Nhật ký phiên bản / changelog)
  // ============================================
  let _clCss = false;
  function _injectChangelogCss() {
    if (_clCss) return; _clCss = true;
    const css = `
    .cl-wrap{max-width:820px;margin:0 auto}
    .upd-card{margin-bottom:24px;padding:18px;border:1px solid rgba(255,107,43,.28);border-radius:16px;background:linear-gradient(135deg,rgba(255,107,43,.08),rgba(124,58,237,.05))}
    .upd-card .gcard-btn{width:auto}
    .upd-title{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .upd-name{font-family:var(--font);font-size:17px;font-weight:700;color:var(--text)}
    .upd-changes{display:none;margin:10px 0;padding:10px 12px;border-left:3px solid var(--accent);background:rgba(120,140,160,.08);border-radius:7px;font-size:13px;line-height:1.55}
    /* Lý do máy này không có nút cập nhật. Có lệnh để copy nên phải cho ngắt dòng và cho bôi
       đen cả cụm - dòng lệnh mà đứt mất một chữ là chạy ra lỗi khó hiểu hơn cả lúc chưa có. */
    .upd-why{margin-top:8px;line-height:1.6;font-size:13.5px}
    /* Cách gỡ khi lệnh trên báo lỗi: cần có mặt, nhưng phải nhạt hơn lệnh chính để mắt đi đúng
       thứ tự - làm trước, chỉ đọc phần này khi vấp. */
    .upd-why-sub{margin-top:8px;padding-top:8px;border-top:1px solid var(--surface-3);
      font-size:12.5px;color:var(--text2)}
    .upd-why code{display:inline-block;margin:3px 0;padding:2px 7px;border-radius:6px;
      background:var(--surface-2);border:1px solid var(--glass-brd);user-select:all;
      overflow-wrap:anywhere;word-break:break-word}
    .upd-progress{display:none;margin-top:10px}
    .upd-rollback{display:none;margin-top:10px;padding:10px;border:1px solid var(--red);border-radius:8px;background:rgba(200,80,80,.08);font-size:13px;line-height:1.6}
    .cl-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px}
    .cl-cur{font-size:15px;color:var(--text)}
    .cl-badge{padding:3px 11px;border-radius:20px;font-size:13px;font-weight:600;border:1px solid rgba(255,255,255,.14)}
    .cl-badge.up{background:rgba(120,180,255,.14);border-color:rgba(120,180,255,.5);color:var(--link-ink)}
    .cl-badge.ok{background:rgba(44,122,75,.15);border-color:var(--green);color:var(--green)}
    .cl-note{font-size:14px;color:var(--text3);margin:2px 0 18px}
    .cl-note code{background:var(--surface-2);padding:1px 6px;border-radius:5px}
    .cl-rel{position:relative;padding:0 0 6px 22px;border-left:2px solid rgba(120,180,255,.22);margin-left:6px}
    .cl-rel:last-child{border-left-color:transparent}
    .cl-rel:before{content:"";position:absolute;left:-8px;top:5px;width:12px;height:12px;border-radius:50%;background:var(--panel-solid);border:2px solid rgba(120,180,255,.5)}
    .cl-rel.cur:before{background:var(--green);border-color:var(--green);box-shadow:0 0 0 4px rgba(63,220,134,.14)}
    .cl-rel.new:before{background:var(--link-ink);border-color:var(--link-ink)}
    .cl-rtop{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
    .cl-ver{font-size:18px;font-weight:700;color:var(--text)}
    .cl-date{font-size:13px;color:var(--text3)}
    .cl-tag{font-size:12px;padding:2px 9px;border-radius:12px;font-weight:600}
    .cl-tag.cur{background:rgba(63,220,134,.16);color:var(--green)}
    .cl-tag.new{background:rgba(120,180,255,.16);color:var(--link-ink)}
    .cl-sec{margin:0 0 12px}
    .cl-sec h4{margin:8px 0 5px;font-size:14px;color:var(--text3);font-weight:600}
    .cl-sec ul{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:5px}
    .cl-sec li{font-size:14.5px;color:var(--text);line-height:1.5;padding-left:24px;position:relative}
    /* Đoạn mã trong dòng nhật ký thường là đường dẫn dài (07%20-%20Wiki/...). Không cho ngắt
       thì trên điện thoại nó đẩy ngang cả trang, mà trang đọc chữ thì tuyệt đối không được
       cuộn ngang. */
    .cl-sec li code,.upd-changes code{background:var(--surface-2);padding:1px 5px;border-radius:5px;
      font-size:.9em;overflow-wrap:anywhere;word-break:break-word}
    .cl-sec li strong{font-weight:650}
    .cl-sec li:before{position:absolute;left:0;top:0}
    .cl-sec li:before{content:"";display:inline-block;width:1em;height:1em;vertical-align:-.14em;background-color:currentColor;mask-position:center;mask-size:contain;mask-repeat:no-repeat;-webkit-mask-position:center;-webkit-mask-size:contain;-webkit-mask-repeat:no-repeat}
    .cl-sec.feat li:before{mask-image:var(--ic-sparkles);-webkit-mask-image:var(--ic-sparkles)}
    .cl-sec.fix li:before{mask-image:var(--ic-wrench);-webkit-mask-image:var(--ic-wrench)}
    .cl-sec.imp li:before{mask-image:var(--ic-zap);-webkit-mask-image:var(--ic-zap)}
    .cl-sec.sec li:before{mask-image:var(--ic-lock);-webkit-mask-image:var(--ic-lock)}
    .cl-sec.doc li:before{mask-image:var(--ic-book-open);-webkit-mask-image:var(--ic-book-open)}
    .cl-sec.other li:before{mask-image:none;content:"•";width:auto;height:auto;background:none}
    .cl-empty{color:var(--text3);font-size:15px}
    .cl-pager{display:flex;align-items:center;justify-content:center;gap:14px;margin:24px 0 6px;padding-top:16px;border-top:1px solid rgba(255,255,255,.07)}
    .cl-pg{background:var(--surface-2);border:1px solid var(--hairline);color:var(--text);font-size:13.5px;font-weight:600;padding:7px 15px;border-radius:9px;cursor:pointer;transition:background .15s,border-color .15s,color .15s}
    .cl-pg:hover:not(:disabled){background:rgba(120,180,255,.14);border-color:rgba(120,180,255,.45);color:var(--text)}
    .cl-pg:disabled{opacity:.32;cursor:default}
    .cl-pg-info{font-size:13px;color:var(--text3);min-width:130px;text-align:center}`;
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
  }
  function _clSecClass(title) {
    const t = (title || "").toLowerCase();
    if (t.includes("thêm") || t.includes("mới")) return "feat";
    if (t.includes("sửa") || t.includes("lỗi") || t.includes("fix")) return "fix";
    if (t.includes("cải thiện") || t.includes("improve")) return "imp";
    if (t.includes("bảo mật") || t.includes("security")) return "sec";
    if (t.includes("tài liệu") || t.includes("doc")) return "doc";
    return "other";
  }
  // Phân trang nhật ký: giữ dữ liệu đã fetch, render 20 bản/trang - đỡ dài, đỡ nặng DOM.
  let _clData = null;              // cache /changelog để đổi trang không phải gọi lại mạng
  const CL_PAGE_SIZE = 20;         // số phiên bản hiển thị mỗi trang

  // CHANGELOG.md là markdown, nhưng trang này in bằng esc() nên người dùng đọc thấy nguyên
  // `**Bấm vào link...**` kèm dấu sao và dấu huyền quanh mỗi tên file. Trên điện thoại thì
  // nặng hẳn: dòng ngắn, dấu nhiều, mắt phải tự lọc (chủ repo báo 2026-08-12).
  //
  // KHÔNG dùng mdToHtml: hàm đó là bộ dựng khối, nó bọc <p>, và tệ hơn là biến mọi đường dẫn
  // trông giống file trong vault thành link bấm mở - ở đây `dashboard/console.js` chỉ là tên
  // file được nhắc tới, bấm vào chỉ tổ 404.
  //
  // esc() chạy TRƯỚC rồi mới dựng thẻ, nên dù CHANGELOG.md có chứa HTML cũng không có đường
  // nào chèn vào trang. Một lượt quét với hai luật thay vì hai lượt: dấu sao nằm TRONG một
  // đoạn mã bị nhánh code nuốt trước nên còn nguyên là dấu sao, khỏi cần chỗ giữ tạm.
  function _clInline(s) {
    return esc(String(s == null ? "" : s)).replace(
      /`([^`]+)`|\*\*([^*]+)\*\*/g,
      (_m, ma, dam) => ma != null ? "<code>" + ma + "</code>" : "<strong>" + dam + "</strong>");
  }
  function _clRelHtml(rel) {
    const cls = rel.is_current ? "cur" : (rel.installed ? "" : "new");
    const tag = rel.is_current ? `<span class="cl-tag cur">đang dùng</span>`
      : (!rel.installed ? `<span class="cl-tag new">bản mới</span>` : "");
    const secs = (rel.sections || []).map(s => {
      const items = (s.items || []).map(it => `<li>${_clInline(it)}</li>`).join("");
      return `<div class="cl-sec ${_clSecClass(s.title)}"><h4>${esc(s.title)}</h4><ul>${items}</ul></div>`;
    }).join("");
    return `<div class="cl-rel ${cls}">
      <div class="cl-rtop"><span class="cl-ver">v${esc(rel.version)}</span>${rel.date ? `<span class="cl-date">${esc(rel.date)}</span>` : ""}${tag}</div>
      ${secs || '<div class="cl-empty">(không có chi tiết)</div>'}
    </div>`;
  }

  function _clRenderPage(el, page) {
    const d = _clData; if (!d) return;
    const cur = d.current || "?";
    const upBadge = d.update_available
      ? `<span class="cl-badge up">Có bản mới: v${esc(d.latest)}</span>`
      : `<span class="cl-badge ok">Đang ở bản mới nhất</span>`;
    const upNote = d.update_available
      ? `<div class="cl-note">Có thể cập nhật ngay ở khung phía trên; nếu bản Docker không hỗ trợ tự cập nhật, hãy <b>Redeploy</b> trên Hostinger hoặc chạy <code>docker compose up -d --pull always</code>.</div>`
      : "";
    const rels = d.releases || [];
    const total = rels.length;
    const pages = Math.max(1, Math.ceil(total / CL_PAGE_SIZE));
    page = Math.min(Math.max(0, page | 0), pages - 1);
    const start = page * CL_PAGE_SIZE;
    const slice = rels.slice(start, start + CL_PAGE_SIZE);
    const timeline = slice.length
      ? slice.map(_clRelHtml).join("")
      : `<div class="cl-empty">Chưa có nhật ký. Thêm file <code>CHANGELOG.md</code> ở gốc dự án.</div>`;
    const pager = pages > 1 ? `<div class="cl-pager">
      <button class="cl-pg" data-clpage="${page - 1}"${page === 0 ? " disabled" : ""}>‹ Mới hơn</button>
      <span class="cl-pg-info">Trang ${page + 1}/${pages} · ${total} bản</span>
      <button class="cl-pg" data-clpage="${page + 1}"${page >= pages - 1 ? " disabled" : ""}>Cũ hơn ›</button>
    </div>` : "";
    el.innerHTML = `<div class="cl-wrap">
      <div class="cl-head"><span class="cl-cur">Đang cài: <b>v${esc(cur)}</b></span>${upBadge}</div>
      ${upNote}
      ${timeline}
      ${pager}
    </div>`;
    el.querySelectorAll(".cl-pg[data-clpage]").forEach(b => {
      if (b.disabled) return;
      b.onclick = () => {
        _clRenderPage(el, parseInt(b.dataset.clpage, 10) || 0);
        let n = el; while (n && n.scrollHeight <= n.clientHeight + 1) n = n.parentElement;
        if (n) n.scrollTop = 0;   // đổi trang → cuộn lên đầu cho dễ đọc
      };
    });
  }

  async function renderLogs(el) {
    _injectChangelogCss();
    const myGen = _renderGen;
    el.innerHTML = `<div class="cl-wrap">
      <section class="upd-card" aria-label="Cập nhật Javis OS">
        <div class="upd-title"><span class="upd-name">Javis OS</span><span class="gcard-tag" id="updVerTag">…</span></div>
        <div class="gcard-meta" id="updVerMeta">Đang kiểm tra bản mới…</div>
        <div class="upd-changes" id="updVerChangelog"></div>
        <div class="js-actions">
          <button class="gcard-btn ghost" id="updVerCheck">Kiểm tra lại</button>
          <button class="gcard-btn" id="updVerUpdate" style="display:none">${ic("upload-cloud")} Cập nhật ngay</button>
        </div>
        <div class="upd-progress" id="updVerProgress"></div>
        <div class="gcard-meta" id="updVerStatus"></div>
        <div class="upd-rollback" id="updVerRollback"></div>
      </section>
      <div id="clTimeline"><div class="cl-note">Đang tải nhật ký cập nhật...</div></div>
    </div>`;
    // Nút "Kiểm tra lại" PHẢI làm mới cả danh sách bên dưới, không chỉ khung trên.
    wireUpdateManager(el, napTimeline);
    await napTimeline();

    async function napTimeline() {
    let d;
    try {
      // cache: "no-store" - KHÔNG phải đề phòng suông. Mọi lời gọi khác ở trang này đều đã
      // no-store; riêng dòng nạp danh sách phiên bản thì quên, nên nó là chỗ duy nhất có thể
      // ăn bản cũ trong bộ nhớ đệm trình duyệt. Triệu chứng đúng như chủ repo báo (2026-08-12):
      // khung trên báo có bản mới, mà danh sách bên dưới không thấy bản đó đâu.
      const r = await fetch("/changelog", { cache: "no-store" });
      d = await r.json();
    } catch (e) {
      if (myGen !== _renderGen) return;
      const timeline = el.querySelector("#clTimeline");
      if (timeline) timeline.innerHTML = `<div class="cl-empty">Không tải được nhật ký cập nhật. Hãy tải lại trang.</div>`;
      return;
    }
    if (myGen !== _renderGen) return;   // đã đổi trang trong lúc chờ
    _clData = d;
    const timeline = el.querySelector("#clTimeline");
    if (timeline) _clRenderPage(timeline, 0);
    }
  }

  const UPDATE_STEPS = [
    ["preparing", "Chuẩn bị"], ["pulling", "Tải code"], ["installing", "Cài thư viện"],
    ["restarting", "Khởi động lại"], ["health_check", "Kiểm tra sức khoẻ"], ["done", "Xong"],
  ];
  // mode "native" chạy trên cả Linux lẫn Mac - nhãn lấy theo platform server báo về
  const updateModeLabel = (j) => j.mode === "docker" ? "Docker / VPS"
    : j.mode === "windows" ? "Windows"
    : (j.platform === "mac" ? "macOS" : "Linux");

  // Vì sao máy này không có nút "Cập nhật ngay". Chủ repo báo (2026-08-12): "một số máy VPS
  // không có nút update, anh không hiểu vì sao". Cả hai lý do đều ĐÚNG THIẾT KẾ, nhưng app gộp
  // chúng vào một câu chung chung nên nhìn hệt như máy hỏng.
  //
  // Khác nhau ở chỗ QUAN TRỌNG NHẤT: một cái bật được bằng đúng một lệnh, một cái thì không.
  // Gộp lại là cướp mất của người dùng thông tin duy nhất họ cần.
  function _updVimSaoKhongCoNut(maLyDo) {
    if (maLyDo === "watchtower_off") {
      return "Máy này <b>chưa bật Watchtower</b> - đó là thứ nhận lệnh cập nhật từ nút bấm, và nó "
        + "nằm ngoài luồng <code>docker compose up -d</code> thường lệ. Bật một lần, ở thư mục chứa "
        + "file compose:<br><code>docker compose --profile update up -d</code><br>"
        + "Xong tải lại trang là nút hiện ra. Không muốn bật thì vẫn cập nhật tay được: "
        + "<code>docker compose up -d --pull always</code>."
        // Chủ repo gõ lệnh trên rồi lãnh "no configuration file provided: not found" - đứng sai
        // thư mục, vì tên thư mục tuỳ lúc clone (javis hay javis-os). Câu "ở thư mục chứa file
        // compose" đúng nhưng vô dụng khi người ta KHÔNG BIẾT nó nằm đâu. Docker biết, nên hỏi nó.
        + "<div class=\"upd-why-sub\">Báo <code>no configuration file provided: not found</code> "
        + "là đang đứng sai thư mục. Hỏi Docker xem nó nằm đâu:<br>"
        + "<code>docker ps --format '{{.Names}}\\t{{.Label \"com.docker.compose.project.working_dir\"}}'</code>"
        + "</div>";
    }
    if (maLyDo === "no_token") {
      return "Bản cài này <b>không kèm Watchtower</b> (stack Hostinger cố tình bỏ - trên đó nó không "
        + "đụng được Docker socket nên chạy là lỗi vòng lặp). Cập nhật bằng <b>Redeploy</b> trong "
        + "Hostinger Docker Manager.";
    }
    // Rơi vào đây là mode lạ hoặc server cũ chưa trả mã lý do - giữ nguyên câu cũ, đừng đoán bừa.
    return "↻ Cập nhật bằng <b>Redeploy</b>: Hostinger dùng Docker Manager; VPS chạy "
      + "<code>docker compose up -d --pull always</code>.";
  }

  function wireUpdateManager(root, napLai) {
    const q = (id) => root.querySelector("#" + id);
    const progress = (phase, extra) => {
      const box = q("updVerProgress"); if (!box) return;
      box.style.display = "";
      const normalized = phase === "rolling_back" ? "health_check" : phase;
      let at = UPDATE_STEPS.findIndex(x => x[0] === normalized); if (at < 0) at = 0;
      box.innerHTML = `<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px">${
        UPDATE_STEPS.map((s, i) => `<span style="${i === at ? "font-weight:600" : "opacity:.7"}">${i < at ? OK_ICON : (i === at ? ic("loader", { cls: "ic-spin" }) : ic("circle", { cls: "ic-dim" }))} ${esc(s[1])}</span>`).join('<span style="opacity:.4"> → </span>')
      }</div>${phase === "rolling_back" ? '<div style="margin-top:6px;color:var(--red)">↩ Bản mới lỗi, đang tự quay về bản cũ…</div>' : ""}${extra ? `<div style="margin-top:6px;opacity:.85">${esc(extra)}</div>` : ""}`;
    };
    const loadChanges = async () => {
      const box = q("updVerChangelog"); if (!box) return;
      let d = {}; try { d = await (await fetch("/changelog", { cache: "no-store" })).json(); } catch (e) { return; }
      const fresh = (d.releases || []).filter(r => !r.installed).slice(0, 2);
      if (!fresh.length) { box.style.display = "none"; return; }
      box.style.display = "";
      box.innerHTML = "<b>Bản mới có gì:</b>" + fresh.map(r => {
        const items = (r.sections || []).flatMap(s => s.items || []).slice(0, 3);
        return `<div style="margin-top:5px">v${esc(r.version)}${r.date ? " · " + esc(r.date) : ""}</div><ul style="margin:2px 0 0 16px;padding:0">${items.map(it => `<li>${_clInline(it)}</li>`).join("")}</ul>`;
      }).join("");
    };
    const loadVersion = async () => {
      const tag = q("updVerTag"), meta = q("updVerMeta"), update = q("updVerUpdate"), changes = q("updVerChangelog");
      if (!tag || !meta || !update) return;
      meta.textContent = "Đang kiểm tra bản mới…";
      let j = {}; try { j = await (await fetch("/version", { cache: "no-store" })).json(); }
      catch (e) { meta.innerHTML = WARN_ICON + " Không kiểm tra được phiên bản."; return; }
      tag.textContent = "v" + (j.current || "?");
      root.dataset.currentVersion = j.current || "";
      root.dataset.previousVersion = j.previous_version || "";
      root.dataset.updateMode = j.mode || "";
      if (changes) { changes.style.display = "none"; changes.innerHTML = ""; }
      const mode = updateModeLabel(j) || j.mode || "";
      if (j.update_available) {
        const base = `🆕 Có bản mới <b>v${esc(j.latest)}</b> (đang chạy v${esc(j.current)}) · ${esc(mode)}`;
        if (j.can_self_update) { meta.innerHTML = base; update.style.display = ""; }
        else {
          meta.innerHTML = base + '<div class="upd-why">' + _updVimSaoKhongCoNut(j.self_update_off) + "</div>";
          update.style.display = "none";
        }
        loadChanges();
      } else {
        meta.innerHTML = j.latest ? `${OK_ICON} Đang dùng bản mới nhất (v${esc(j.current)}) · ${esc(mode)}` : `v${esc(j.current)} · ${esc(mode)}${j.error ? " · chưa so được với GitHub" : ""}`;
        update.style.display = "none";
      }
    };
    // Trước bản này nút chỉ gọi loadVersion, tức chỉ vẽ lại KHUNG TRÊN. Danh sách phiên bản
    // bên dưới chỉ được nạp ĐÚNG MỘT LẦN lúc mở trang, nên bấm "Kiểm tra lại" bao nhiêu lần
    // cũng không thấy bản mới hiện ra - phải rời trang rồi quay lại, hoặc F5. Chủ repo báo
    // đúng triệu chứng đó (2026-08-12): "trên bản update anh chưa thấy bản 28".
    const check = q("updVerCheck");
    if (check) check.onclick = async () => {
      await loadVersion();
      if (typeof napLai === "function") await napLai();
    };
    const update = q("updVerUpdate");
    if (update) update.onclick = async () => {
      if (!confirm("Cập nhật Javis lên bản mới nhất?\nApp sẽ tự khởi động lại; nếu lỗi hệ thống sẽ thử quay về bản cũ.")) return;
      const status = q("updVerStatus"), rollback = q("updVerRollback");
      const oldCur = root.dataset.currentVersion || "";
      update.disabled = true; if (rollback) { rollback.style.display = "none"; rollback.innerHTML = ""; }
      progress("preparing", "Đang chuẩn bị cập nhật…"); status.textContent = "";
      let resp; try { resp = await (await fetch("/update", { method: "POST" })).json(); }
      catch (e) { resp = { ok: true }; }
      if (resp && resp.ok === false) {
        update.disabled = false; q("updVerProgress").style.display = "none";
        status.innerHTML = WARN_ICON + " " + esc(resp.error || "Không cập nhật được.") + (resp.manual ? " Chạy: <code>" + esc(resp.manual) + "</code>" : "");
        return;
      }
      status.innerHTML = ic("loader", { cls: "ic-spin" }) + " Đang cập nhật… đừng tắt trang.";
      let tries = 0;
      const poll = setInterval(async () => {
        tries++;
        let state = null; try { state = await (await fetch("/update/status", { cache: "no-store" })).json(); } catch (e) {}
        if (state && state.state && state.state.phase) {
          const phase = state.state.phase, result = state.state.result;
          const stash = state.state.stashed ? ic("package") + " Sửa đổi cục bộ đã được cất vào git stash." : "";
          progress(phase, stash);
          if (result === "success") { clearInterval(poll); status.innerHTML = OK_ICON + " Đã cập nhật xong. Đang tải lại trang…"; setTimeout(() => location.reload(), 1500); return; }
          if (result === "rolled_back") { clearInterval(poll); status.innerHTML = "↩ Bản mới lỗi, đã <b>tự quay về bản cũ</b>."; update.disabled = false; return; }
          if (["pull_failed", "rollback_failed", "error"].includes(result)) {
            clearInterval(poll); q("updVerProgress").style.display = "none";
            status.innerHTML = WARN_ICON + " " + esc(state.state.error || "Cập nhật lỗi.") + " Xem <code>update.log</code>."; update.disabled = false; return;
          }
        }
        try {
          const v = await (await fetch("/version", { cache: "no-store" })).json();
          const docker = root.dataset.updateMode === "docker";
          if ((docker || !(state && state.state && state.state.phase)) && v.update_available === false && v.current && v.current !== oldCur) {
            clearInterval(poll); status.innerHTML = OK_ICON + " Đã cập nhật xong. Đang tải lại trang…"; setTimeout(() => location.reload(), 1500); return;
          }
          if (docker && tries >= 12 && v.current === oldCur) {
            clearInterval(poll); status.innerHTML = WARN_ICON + " Bản mới chưa lên sau một lúc - có thể lỗi.";
            if (rollback) {
              const prev = root.dataset.previousVersion || v.previous_version || "";
              rollback.style.display = "";
              rollback.innerHTML = "<b>Cách lùi bản Docker:</b><br><code>docker compose pull && docker compose up -d</code>" + (prev ? `<br>Hoặc pin image <code>ghcr.io/blogminhquy/javis-os:${esc(prev)}</code> rồi Redeploy.` : "");
            }
            update.disabled = false; return;
          }
        } catch (e) {}
        if (tries > 60) { clearInterval(poll); status.textContent = "Server chưa lên lại sau khoảng 3 phút - thử tải lại trang."; update.disabled = false; }
      }, 3000);
    };
    loadVersion();
  }

  const fbrain = () => (window.currentBrainPath ? currentBrainPath() : "brain");

  // ============================================
  // Tải về (dùng chung cho trang Tệp tin + cây file)
  // ============================================
  // Bấm tải bằng thẻ <a download> ẩn thay vì window.open: không dính chặn popup, không mở
  // tab trắng rồi tự đóng (trên điện thoại tab trắng đó hay làm mất luôn file).
  function _dlGo(url) {
    const a = document.createElement("a");
    a.href = url; a.rel = "noopener"; a.style.display = "none";
    document.body.appendChild(a); a.click();
    setTimeout(() => a.remove(), 0);
  }
  const _dlFileUrl = (rel) => `/files/raw?brain=${encodeURIComponent(fbrain())}&path=${encodeURIComponent(rel)}&dl=1`;
  const _dlZipUrl = (rel) => `/files/zip?brain=${encodeURIComponent(fbrain())}&path=${encodeURIComponent(rel)}`;
  const _dlFile = (rel) => _dlGo(_dlFileUrl(rel));
  // Tải CẢ thư mục: hỏi /files/zip?probe=1 để ĐO trước (số file + dung lượng) rồi mới nén.
  // Nhờ vậy thư mục quá lớn báo được bằng lời, và thư mục nặng thì xin xác nhận trước khi chờ.
  async function _dlFolder(rel, name) {
    let d = {};
    try {
      const r = await fetch(_dlZipUrl(rel) + "&probe=1");
      d = await r.json().catch(() => ({}));
    } catch (e) { alert("Không đọc được thư mục: " + e.message); return; }
    if (d.error) { alert(d.error); return; }
    if (!d.files) { alert(`Thư mục "${name}" không có file nào để tải.`); return; }
    const mb = (d.bytes || 0) / 1048576;
    if (mb > 200 && !confirm(`"${name}" có ${d.files} file, khoảng ${mb.toFixed(0)} MB.\nNén thành .zip và tải về?`)) return;
    _dlGo(_dlZipUrl(rel));
  }

  // ============================================
  // Trang Tệp tin (File Manager)
  // ============================================
  function _humanSize(n) { if (n < 1024) return n + " B"; if (n < 1048576) return (n / 1024).toFixed(1) + " KB"; return (n / 1048576).toFixed(1) + " MB"; }
  function _fileIcon(ext) {
    return ic(_fileIconName(ext));
  }
  function _fileIconName(ext) {
    if ([".md", ".txt"].includes(ext)) return "file-text";
    if ([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"].includes(ext)) return "image";
    if ([".json", ".yaml", ".yml", ".toml", ".ini", ".env"].includes(ext)) return "settings";
    if ([".js", ".ts", ".py", ".sh", ".bat", ".css", ".html"].includes(ext)) return "file-code";
    if ([".mp3", ".wav", ".ogg"].includes(ext)) return "file-audio";
    if (ext === ".pdf") return "file-type";
    return "file";
  }
  let _fmCss = false;
  function _injectExtraCss() {
    if (_fmCss) return; _fmCss = true;
    const css = `
    .fm-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
    .fm-crumb{flex:1;min-width:160px;font-size:15px;color:var(--text3)}
    .fm-crumb a{color:var(--link-ink);cursor:pointer;text-decoration:none} .fm-crumb a:hover{text-decoration:underline}
    .fm-actions{display:flex;gap:6px;flex-wrap:wrap}
    .fm-search-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:14px}
    .fm-search{flex:1 1 360px;max-width:700px;margin:0;padding:8px 11px;border-radius:10px}
    .fm-search input{font-size:14px}
    .fm-search-modes{margin:0;flex:none}
    .fm-search-meta{min-width:130px;color:var(--text3);font-size:12px}
    .fm-search-row{cursor:pointer}
    .fm-search-main{flex:1;min-width:0}
    .fm-search-name{display:flex;align-items:center;gap:8px;color:var(--text);font-size:15px}
    .fm-search-path,.fm-search-snip{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .fm-search-path{margin-top:2px;color:var(--text3);font-size:12px}
    .fm-search-snip{margin-top:3px;color:var(--text3);font-size:12px}
    .fm-search-kind{flex:none;color:var(--text3);font-size:11px;border:1px solid var(--hairline);border-radius:99px;padding:2px 7px}
    .fm-search-row .fm-row-act{opacity:1}
    .fm-uplabel{cursor:pointer}
    .fm-list{display:flex;flex-direction:column;border:1px solid var(--hairline);border-radius:10px;overflow:hidden}
    .fm-row{display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--surface-2);cursor:default}
    .fm-row:last-child{border-bottom:none} .fm-row:hover{background:rgba(120,180,255,.06)}
    .fm-ico{flex:none} .fm-name{flex:1;color:var(--text);font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .fm-row.is-dir .fm-ico,.fm-row.is-dir .fm-name{cursor:pointer}
    .fm-row.fm-target{box-shadow:inset 3px 0 0 var(--link-ink);background:rgba(120,180,255,.10);animation:fmFlash 1.7s ease}
    @keyframes fmFlash{0%,45%{background:rgba(120,180,255,.42)}100%{background:rgba(120,180,255,.10)}}
    .fm-size{color:var(--text3);font-size:13px;min-width:60px;text-align:right}
    .fm-row-act{display:flex;gap:5px;opacity:.6;transition:.15s} .fm-row:hover .fm-row-act,.fm-row:focus-within .fm-row-act{opacity:1}
    @media(hover:none){.fm-row-act{opacity:1}}
    .fm-row-act button{background:var(--surface-2);border:1px solid var(--hairline);color:var(--text3);cursor:pointer;font-size:13px;padding:3px 9px;border-radius:6px;white-space:nowrap} .fm-row-act button:hover{color:var(--text-hi);border-color:rgba(120,180,255,.5)}
    .fm-row-act button.danger:hover{color:var(--red);border-color:rgba(255,120,120,.5)}
    /* Mở file trong trang Tệp tin: trình sửa DÍNH vào đúng khung của trang, không popup nữa.
       Cùng một node #noteEditor mà trang Trò chuyện vẫn mượn - một trình sửa, một trải nghiệm. */
    .fm-edit{display:none;position:relative;min-height:0}
    .fm-page.edit-on{display:flex;flex-direction:column;height:100%}
    .fm-page.edit-on>.fm-browse{display:none}
    .fm-page.edit-on>.fm-edit{display:flex;flex:1 1 auto}
    .fm-edit>.note-editor:not(.ne-full){position:static;inset:auto;z-index:auto;flex:1 1 auto;min-height:0;border:1px solid var(--hairline);border-radius:12px;overflow:hidden}
    .fm-miss{margin-bottom:12px;padding:11px 13px;border:1px solid rgba(224,160,74,.45);border-radius:10px;background:rgba(224,160,74,.08);color:var(--warn-ink);font-size:13px;line-height:1.55}
    .fm-miss b{color:var(--text)}
    .fm-miss-hits{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
    .fm-miss-hits button{background:var(--surface-2);border:1px solid var(--hairline);color:var(--text2);cursor:pointer;font-size:12.5px;padding:4px 9px;border-radius:6px}
    .fm-miss-hits button:hover{color:var(--text-hi);border-color:var(--link-ink)}
    .fm-fix{margin-bottom:12px;padding:12px 14px;border:1px solid rgba(224,160,74,.45);border-radius:10px;background:rgba(224,160,74,.08);color:var(--text2);font-size:13px;line-height:1.6}
    .fm-fix.xong{border-color:rgba(63,220,134,.45);background:rgba(63,220,134,.08)}
    .fm-fix b{color:var(--text)}
    .fm-fix code{background:var(--surface-2);border-radius:4px;padding:1px 5px;font-size:12px}
    .fm-fix-list{margin:9px 0 2px;max-height:190px;overflow:auto;border:1px solid var(--hairline);border-radius:8px}
    .fm-fix-row{display:flex;align-items:center;gap:8px;padding:5px 10px;border-bottom:1px solid var(--surface-2);font-size:12.5px;color:var(--text3)}
    .fm-fix-row:last-child{border-bottom:none}
    .fm-fix-row span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text2)}
    .fm-fix-row em{flex:none;font-style:normal;font-size:11.5px;opacity:.8}
    .fm-fix-act{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
    @media(max-width:700px){.fm-fix-row em{display:none}}
    .si-grid{display:flex;flex-direction:column;gap:14px;max-width:640px}
    .si-field label{display:block;font-size:14px;color:var(--text3);margin-bottom:5px}
    .si-field select,.si-field input,.si-field textarea{width:100%;padding:8px 10px;border-radius:8px;border:1px solid var(--hairline);background:var(--field-bg);color:var(--text);font-size:15px;outline:none}
    .si-field textarea{min-height:80px;resize:vertical;font-family:inherit}
    .si-row{display:flex;gap:10px;flex-wrap:wrap}
    .si-chip{padding:7px 14px;border-radius:20px;border:1px solid rgba(255,255,255,.14);background:rgba(15,22,40,.6);color:var(--text);cursor:pointer;font-size:14px}
    .si-chip.sel{border-color:var(--accent);background:rgba(255,138,60,.15);color:var(--accent-ink)}
    .si-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}
    .si-status{margin-top:16px;padding:12px 14px;border-radius:10px;background:var(--surface-1);border:1px solid rgba(255,255,255,.07);font-size:15px;color:var(--text)}
    .si-log{margin-top:16px} .si-log .le{padding:10px 12px;border-left:2px solid rgba(120,180,255,.4);background:rgba(255,255,255,.02);margin-bottom:8px;border-radius:0 8px 8px 0;font-size:14px;white-space:pre-wrap;color:var(--text2)}
    .kn-health{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:10px;margin:16px 0}
    .kn-kpi{padding:13px 14px;border:1px solid var(--hairline);border-radius:11px;background:var(--surface-1)}
    .kn-kpi b{display:block;font-size:22px;color:var(--text);margin-top:4px}.kn-kpi span{font-size:12px;color:var(--text3)}
    .kn-layout{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(280px,.75fr);gap:14px;align-items:start}
    .kn-panel{border:1px solid var(--hairline);border-radius:12px;background:rgba(255,255,255,.018);overflow:hidden}
    .kn-panel-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.07)}
    .kn-panel-head b{font-size:14px;color:var(--text)}.kn-panel-head span{font-size:12px;color:var(--text3)}
    .kn-list{max-height:440px;overflow:auto}.kn-empty{padding:22px;text-align:center;color:var(--text3);font-size:13px}
    .kn-task{padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.055);cursor:pointer;transition:.15s}
    .kn-task:last-child{border-bottom:none}.kn-task:hover{background:rgba(127,176,255,.055)}
    .kn-task-top{display:flex;gap:9px;align-items:flex-start}.kn-task-title{flex:1;color:var(--text);font-size:14px;font-weight:600;line-height:1.35}
    .kn-pill{flex:none;border-radius:99px;padding:2px 7px;font-size:10px;border:1px solid var(--hairline);color:var(--text3)}
    .kn-task-meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:5px;color:var(--text3);font-size:11px}
    .kn-task-result{margin-top:6px;color:var(--text3);font-size:12px;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
    .kn-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.kn-actions button{padding:3px 8px;border-radius:6px;border:1px solid var(--hairline);background:var(--surface-1);color:var(--text2);font-size:11px;cursor:pointer}.kn-actions button:hover{border-color:var(--link-ink);color:var(--text-hi)}.kn-actions button.danger{color:var(--red)}.kn-actions button.danger:hover{border-color:var(--red);color:var(--red)}
    .kn-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}.kn-dot.live{background:var(--green);box-shadow:0 0 0 4px rgba(63,220,134,.12)}.kn-dot.off{background:var(--text3)}
    .kn-drawer-backdrop{position:fixed;z-index:10000;inset:0;background:rgba(3,7,16,.58);backdrop-filter:blur(2px);opacity:0;pointer-events:none;transition:opacity .2s}.kn-drawer-backdrop.open{opacity:1;pointer-events:auto}
    .kn-drawer{position:fixed;z-index:10001;top:0;right:0;width:min(520px,94vw);height:100vh;height:100dvh;background:var(--bg2);border-left:1px solid rgba(127,176,255,.25);box-shadow:-20px 0 60px rgba(0,0,0,.45);transform:translateX(105%);transition:transform .2s;display:flex;flex-direction:column}
    .kn-drawer.open{transform:translateX(0)}.kn-drawer-head{position:sticky;top:0;z-index:2;padding:12px 12px 12px 17px;border-bottom:1px solid var(--hairline);background:var(--bg2);display:flex;align-items:center;gap:10px}.kn-drawer-head b{flex:1;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.kn-drawer-head button{width:36px;height:36px;display:grid;place-items:center;background:rgba(255,255,255,.035);border:1px solid var(--hairline);border-radius:8px;color:var(--text2);font-size:22px;line-height:1;cursor:pointer}.kn-drawer-head button:hover{border-color:var(--link-ink);color:var(--text-hi)}
    .kn-drawer-body{padding:16px 17px;overflow:auto;color:var(--text2);font-size:13px;line-height:1.5}.kn-detail-block{margin-top:16px}.kn-detail-block h4{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);margin:0 0 7px}.kn-event{padding:8px 0;border-bottom:1px solid var(--surface-2)}
    @media(max-width:850px){.fm-search-tools{align-items:stretch}.fm-search{flex-basis:100%;max-width:none}.fm-search-meta{width:100%;min-width:0}.fm-search-kind{display:none}.kn-health{grid-template-columns:repeat(2,1fr)}.kn-layout{grid-template-columns:1fr}.kn-list{max-height:none}}`;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  }

  // Rời trang Tệp tin: TRẢ trình sửa về khoang não trước khi #cviewBody bị ghi đè, y như trang
  // Trò chuyện vẫn làm. Không trả là mất luôn node #noteEditor, và lần sau mở file ra trắng trơn.
  function _fmRoiTrang() {
    document.body.classList.remove("on-files");
    _fmSauKhiDong = null;
    _returnNoteEditor();
  }

  async function renderFiles(el) {
    _injectExtraCss();
    let cur = "";
    // Vào LẠI trang này trong khi trình sửa đang mượn khung của bản render cũ (openFilesAt gọi
    // thẳng renderPage("files") nên _pageLeave không chạy) → trả node về trước, kẻo el.innerHTML
    // bên dưới xoá luôn cả trình sửa.
    if (document.getElementById("fmEdit")) _fmRoiTrang();
    document.body.classList.add("on-files");
    _pageLeave = _fmRoiTrang;
    el.innerHTML = `<div class="fm-page">
      <div class="cview-section fm-browse">
      <div class="fm-search-tools">
        <div class="vault-search fm-search">
          <span class="vs-ico">${ic("search")}</span>
          <input id="fmSearch" type="search" placeholder="Tìm file trong toàn brain..." spellcheck="false" autocomplete="off">
          <button class="vs-clear" id="fmSearchClear" title="Xoá tìm kiếm" hidden>${X_ICON}</button>
        </div>
        <div class="vault-modes fm-search-modes" aria-label="Phạm vi tìm kiếm">
          <button class="vs-chip active" id="fmSearchName" data-mode="name" title="Tìm theo tên file">Tên</button>
          <button class="vs-chip" id="fmSearchContent" data-mode="content" title="Tìm trong nội dung file text">Nội dung</button>
        </div>
        <div class="fm-search-meta" id="fmSearchMeta">Tìm trong toàn brain</div>
      </div>
      <div class="fm-bar">
        <div class="fm-crumb" id="fmCrumb"></div>
        <div class="fm-actions">
          <button class="s-btn-ghost" id="fmUp">↑ Lên</button>
          <button class="s-btn-ghost" id="fmHome" title="Về thư mục brain">${ic("house")} Brain</button>
          <button class="s-btn-ghost" id="fmNewDir">+ Thư mục</button>
          <button class="s-btn-ghost" id="fmNewFile">+ File</button>
          <label class="s-btn-ghost fm-uplabel">⤒ Tải lên<input type="file" id="fmUpload" hidden multiple></label>
          <button class="s-btn-ghost" id="fmZipCur" title="Nén cả thư mục đang mở thành .zip rồi tải về">⤓ Tải thư mục</button>
          <button class="s-btn-ghost" id="fmRefresh">↻</button>
        </div>
      </div>
      <div id="fmFix"></div>
      <div id="fmMiss"></div>
      <div id="fmList" class="fm-list">Đang tải...</div>
      </div>
      <div class="fm-edit" id="fmEdit"></div>
    </div>`;
    const listEl = el.querySelector("#fmList"), crumbEl = el.querySelector("#fmCrumb");
    const searchInput = el.querySelector("#fmSearch"), searchClear = el.querySelector("#fmSearchClear");
    const searchMeta = el.querySelector("#fmSearchMeta"), missEl = el.querySelector("#fmMiss");
    const fixEl = el.querySelector("#fmFix");
    const TEXT_EDIT_EXTS = VT_TEXT_EXTS;   // một danh sách duy nhất với trình sửa - hai bản sao là hai luật lệch nhau
    const IMG_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"];   // .svg = sửa text
    // URL tĩnh phục vụ file inline (ảnh hiện, pdf mở tab). dl=1 → ép tải về.
    const rawUrl = (rel, dl) => `/files/raw?brain=${encodeURIComponent(fbrain())}&path=${encodeURIComponent(rel)}${dl ? "&dl=1" : ""}`;
    let searchMode = "name", searchTimer = null, searchSeq = 0;
    let homeRel = "";   // tiền tố nhà brain (server trả trong /files/list) - để cắt cho gọn khi hiện đường dẫn

    function resetSearchUi() {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = null; searchSeq++;
      searchInput.value = "";
      searchClear.hidden = true;
      searchMeta.textContent = searchMode === "content" ? "Quét nội dung file text" : "Tìm trong toàn brain";
    }

    // upTarget: đường dẫn nút "Lên" sẽ tới (null = đã ở trần → ẩn nút). Do server tính (parent).
    let upTarget = null;
    async function load(path) {
      // path === undefined → điểm vào mặc định (brain); "" = trần (ổ đĩa); chuỗi = tương đối trần
      resetSearchUi();
      missEl.innerHTML = "";
      listEl.innerHTML = "Đang tải...";
      const qp = (path === undefined || path === null) ? "" : `&path=${encodeURIComponent(path)}`;
      let resp, d;
      try { resp = await fetch(`/files/list?brain=${encodeURIComponent(fbrain())}${qp}`); d = await resp.json().catch(() => ({})); }
      catch (e) { listEl.innerHTML = `<div class="empty" style="padding:20px;color:var(--red)">Lỗi kết nối: ${esc(e.message)}</div>`; return null; }
      if (!resp.ok || d.error) {
        const msg = d.error || (resp.status === 404
          ? "Máy chủ Javis chưa có chức năng Tệp tin - hãy KHỞI ĐỘNG LẠI server (stop-javis.bat → start-javis.vbs) rồi tải lại trang."
          : resp.status === 401 ? "Phiên đăng nhập hết hạn - tải lại trang & đăng nhập."
          : "Lỗi máy chủ (" + resp.status + ").");
        listEl.innerHTML = `<div class="empty" style="padding:20px;color:var(--red)">${WARN_ICON} ${esc(msg)}</div>`;
        // Server cũ trả 400 "Không phải thư mục" khi path trỏ vào FILE. Đừng để người dùng đứng
        // trước một trang trống: lùi về thư mục cha rồi soi sáng đúng file đó.
        const lui = String(path || "");
        if (resp.status === 400 && lui.includes("/")) {
          const ten = lui.split("/").pop();
          const d2 = await load(lui.slice(0, lui.lastIndexOf("/")));
          if (d2) revealFile(ten);
          return d2;
        }
        return null;
      }
      cur = d.path || ""; upTarget = d.parent; homeRel = d.home || homeRel;
      const upBtn = el.querySelector("#fmUp"); if (upBtn) upBtn.style.display = (upTarget === null || upTarget === undefined) ? "none" : "";
      crumb(d.root);
      const items = d.items || [];
      if (!items.length) listEl.innerHTML = `<div class="empty" style="padding:20px;text-align:center;color:var(--text3)">Thư mục trống.</div>`;
      else { listEl.innerHTML = ""; items.forEach(it => listEl.appendChild(row(it))); }
      // Link trỏ vào chỗ không có gì: nói rõ đã tìm cái gì, đang đứng ở đâu, rồi tự đi tìm theo
      // TÊN (server khớp cả khi lệch dấu tiếng Việt) - tên trong chat hay khác tên trên đĩa.
      if (d.missing) khongThayFile(d.missing, d.home);
      return d;
    }
    // Đi tìm file mà một đường dẫn hụt đang nhắm tới, rồi bày ra cho bấm một phát là mở.
    // Đường dẫn hiện cho người đọc luôn cắt tiền tố nhà brain: "06 - Sources/x.md" là thứ họ
    // thấy trong chat, còn "home/user/.../brains/Brain Default/06 - Sources/x.md" chỉ tổ rối mắt.
    const trongBrain = (p, home) => {
      const h = String(home || "").replace(/\/+$/, "");
      const s = String(p || "");
      return h && s.indexOf(h + "/") === 0 ? s.slice(h.length + 1) : s;
    };
    async function khongThayFile(missing, home) {
      const ten = String(missing).split("/").pop() || missing;
      missEl.innerHTML = `<div class="fm-miss">${WARN_ICON} Không có <b>${esc(trongBrain(missing, home))}</b> trong brain này.
        Đang mở thư mục gần nhất còn tồn tại. <span id="fmMissWait">Đang tìm file tên giống…</span>
        <div class="fm-miss-hits" id="fmMissHits"></div></div>`;
      let items = [];
      try {
        const r = await fetch(`/files/search?brain=${encodeURIComponent(fbrain())}&q=${encodeURIComponent(ten)}&mode=name&limit=8`);
        items = ((await r.json()) || {}).items || [];
      } catch (e) {}
      const wait = missEl.querySelector("#fmMissWait"), hits = missEl.querySelector("#fmMissHits");
      if (!wait || !hits) return;
      if (!items.length) { wait.textContent = "Không tìm thấy file nào tên gần giống."; return; }
      wait.textContent = items.length === 1 ? "Có lẽ là file này:" : "Có lẽ là một trong các file này:";
      items.forEach(it => {
        const b = document.createElement("button");
        b.innerHTML = `${_fileIcon(it.ext || "")} ${esc(trongBrain(it.path, home) || it.name)}`;
        b.onclick = () => moTrongTrang(it.path, { name: it.name, ext: it.ext || "", type: "file" });
        hits.appendChild(b);
      });
    }
    // ---- Chữa file .md bị bản cũ (<= 0.33.3) làm hỏng ----------------------------------
    // Lưu note qua trình sửa trực quan hồi đó phá khối `---` đầu note và dồn dấu gạch chéo.
    // Người dùng KHÔNG có cách nào tự biết là file mình hỏng, và cũng không có lý do gì phải
    // đi tìm một nút "sửa" mà họ không biết là tồn tại. Nên: tự soi một lần khi vào trang, im
    // lặng nếu mọi thứ lành, và chỉ lên tiếng khi có thứ thật sự cần chữa.
    async function soiMdHong() {
      let items = [];
      try {
        const r = await fetch(`/files/md-hong?brain=${encodeURIComponent(fbrain())}`);
        if (!r.ok) return;                                  // server cũ chưa có -> im lặng
        items = ((await r.json()) || {}).items || [];
      } catch (e) { return; }
      if (!items.length || !fixEl.isConnected) return;
      veBangSua(items);
    }
    function veBangSua(items) {
      const n = items.length;
      fixEl.innerHTML = `<div class="fm-fix">${WARN_ICON}
        <b>${n} file .md còn dấu vết hỏng từ bản cũ.</b>
        Bản Javis trước 0.33.4 lưu note qua trình sửa trực quan là làm hỏng khối thuộc tính
        (<code>---</code> đầu note thành <code>* * *</code>) và dồn dấu gạch chéo vào chữ.
        Bản này đã bịt đường đó; mấy file lỡ hỏng thì chữa lại một lần là xong.
        <div class="fm-fix-list" id="fmFixList"></div>
        <div class="fm-fix-act">
          <button class="s-btn" id="fmFixGo">Chữa hết ${n} file</button>
          <button class="s-btn-ghost" id="fmFixNo">Để sau</button>
        </div></div>`;
      const ds = fixEl.querySelector("#fmFixList");
      items.slice(0, 12).forEach(it => {
        const d = document.createElement("div");
        d.className = "fm-fix-row";
        d.innerHTML = `${_fileIcon(".md")} <span>${esc(trongBrain(it.path, homeRel))}</span><em>${esc(it.mo_ta || "")}</em>`;
        ds.appendChild(d);
      });
      if (n > 12) {
        const d = document.createElement("div");
        d.className = "fm-fix-row"; d.textContent = `… và ${n - 12} file nữa`;
        ds.appendChild(d);
      }
      fixEl.querySelector("#fmFixNo").onclick = () => { fixEl.innerHTML = ""; };
      fixEl.querySelector("#fmFixGo").onclick = async (ev) => {
        const b = ev.currentTarget; b.disabled = true; b.textContent = "Đang chữa…";
        let d = {};
        try {
          const fd = new FormData();
          fd.append("brain", fbrain());
          fd.append("paths", JSON.stringify(items.map(x => x.path)));
          d = await (await fetch("/files/md-hong/sua", { method: "POST", body: fd })).json();
        } catch (e) { d = { error: e.message }; }
        const xong = (d.da_sua || []).length, hong = (d.loi || []).length;
        // Nói đúng số thật, kể cả khi có file chữa không xong - im lặng nuốt phần hỏng là
        // để người dùng tưởng đã sạch trong khi chưa.
        fixEl.innerHTML = `<div class="fm-fix${hong || d.error ? "" : " xong"}">${hong || d.error ? WARN_ICON : CHECK_ICON}
          ${d.error ? `Không chữa được: ${esc(d.error)}`
            : `Đã chữa <b>${xong} file</b>.${hong ? ` Còn <b>${hong} file</b> không ghi được - xem quyền ghi của thư mục brain.` : " Mở lại note là thấy khối thuộc tính về đúng chỗ."}`}
        </div>`;
        if (xong) load(cur);
      };
    }
    function crumb(rootName) {
      const parts = cur ? cur.split("/") : []; let acc = "";
      let html = `<a data-p="">${ic("house")} ${esc(rootName || "brain")}</a>`;
      parts.forEach(p => { acc = acc ? acc + "/" + p : p; html += ` / <a data-p="${esc(acc)}">${esc(p)}</a>`; });
      crumbEl.innerHTML = html;
      crumbEl.querySelectorAll("a").forEach(a => a.onclick = () => load(a.dataset.p));
    }
    function setSearchMode(mode) {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = null;
      searchMode = mode === "content" ? "content" : "name";
      el.querySelector("#fmSearchName").classList.toggle("active", searchMode === "name");
      el.querySelector("#fmSearchContent").classList.toggle("active", searchMode === "content");
      searchInput.placeholder = searchMode === "content"
        ? "Tìm trong nội dung file text..."
        : "Tìm theo tên file trong toàn brain...";
      if (searchInput.value.trim()) runSearch();
      else searchMeta.textContent = searchMode === "content" ? "Quét nội dung file text" : "Tìm trong toàn brain";
      searchInput.focus();
    }
    async function runSearch() {
      searchTimer = null;
      const q = searchInput.value.trim();
      searchClear.hidden = !q;
      if (!q) { await load(cur); return; }
      if (searchMode === "content" && q.length < 2) {
        searchSeq++;
        listEl.innerHTML = `<div class="empty" style="padding:20px;text-align:center;color:var(--text3)">Nhập ít nhất 2 ký tự để tìm trong nội dung.</div>`;
        searchMeta.textContent = "Cần ít nhất 2 ký tự";
        return;
      }
      const seq = ++searchSeq;
      listEl.innerHTML = `<div class="empty" style="padding:20px;text-align:center;color:var(--text3)">Đang tìm trong toàn brain...</div>`;
      searchMeta.textContent = searchMode === "content" ? "Đang quét nội dung..." : "Đang tìm theo tên...";
      let resp, d;
      try {
        resp = await fetch(`/files/search?brain=${encodeURIComponent(fbrain())}&q=${encodeURIComponent(q)}&mode=${searchMode}&limit=100`);
        d = await resp.json().catch(() => ({}));
      } catch (e) {
        if (seq !== searchSeq) return;
        listEl.innerHTML = `<div class="empty" style="padding:20px;color:var(--red)">Lỗi tìm kiếm: ${esc(e.message)}</div>`;
        searchMeta.textContent = "Tìm kiếm thất bại";
        return;
      }
      if (seq !== searchSeq) return;
      if (!resp.ok || d.error) {
        listEl.innerHTML = `<div class="empty" style="padding:20px;color:var(--red)">${WARN_ICON} ${esc(d.error || "Không tìm kiếm được.")}</div>`;
        searchMeta.textContent = "Tìm kiếm thất bại";
        return;
      }
      const items = d.items || [];
      searchMeta.textContent = `${items.length} kết quả · ${searchMode === "content" ? "nội dung" : "tên file"}`;
      if (!items.length) {
        listEl.innerHTML = `<div class="empty" style="padding:24px;text-align:center;color:var(--text3)">Không tìm thấy file phù hợp với “${esc(q)}”.</div>`;
        return;
      }
      listEl.innerHTML = "";
      items.forEach(it => listEl.appendChild(searchRow(it)));
    }
    function searchRow(it) {
      const div = document.createElement("div"); div.className = "fm-row fm-search-row";
      const target = { name: it.name, ext: it.ext || "", type: "file", size: 0 };
      const editable = TEXT_EDIT_EXTS.includes(target.ext);
      const viewable = IMG_EXTS.includes(target.ext) || target.ext === ".pdf";
      const match = it.match === "content"
        ? `Trong nội dung${it.line ? " · dòng " + it.line : ""}`
        : "Tên file";
      div.innerHTML = `<span class="fm-ico">${_fileIcon(target.ext)}</span>
        <span class="fm-search-main">
          <span class="fm-search-name">${esc(it.name)}</span>
          <span class="fm-search-path">${esc(it.path || "")}</span>
          ${it.snippet ? `<span class="fm-search-snip">${esc(it.snippet)}</span>` : ""}
        </span>
        <span class="fm-search-kind">${esc(match)}</span>
        <span class="fm-row-act"><button data-act="open">Mở</button><button data-act="dl" title="Tải file về máy">⤓ Tải</button><button data-act="loc">Vị trí</button></span>`;
      const openHit = () => {
        if (editable || viewable) moTrongTrang(it.path, target);
        else window.open(rawUrl(it.path), "_blank");
      };
      div.querySelector(".fm-search-main").onclick = openHit;
      div.querySelector(".fm-ico").onclick = openHit;
      div.querySelector('[data-act="open"]').onclick = (e) => { e.stopPropagation(); openHit(); };
      div.querySelector('[data-act="dl"]').onclick = (e) => { e.stopPropagation(); _dlFile(it.path); };
      div.querySelector('[data-act="loc"]').onclick = async (e) => {
        e.stopPropagation();
        const parts = String(it.path || "").split("/");
        const name = parts.pop() || it.name;
        await load(parts.join("/"));
        revealFile(name);
      };
      return div;
    }
    function row(it) {
      const div = document.createElement("div"); div.className = "fm-row" + (it.type === "dir" ? " is-dir" : "");
      const rel = cur ? cur + "/" + it.name : it.name;
      const editable = it.type === "file" && TEXT_EDIT_EXTS.includes(it.ext);
      const viewable = it.type === "file" && (IMG_EXTS.includes(it.ext) || it.ext === ".pdf");
      let acts = "";
      if (editable) acts += '<button data-act="edit" title="Sửa nội dung">Sửa</button>';
      else if (viewable) acts += '<button data-act="view" title="Xem trước">Xem</button>';
      else if (it.type === "file") acts += '<button data-act="open" title="Mở trong tab mới">Mở</button>';
      acts += '<button data-act="ren" title="Đổi tên">Đổi tên</button>';
      // Tải: MỌI loại file (không riêng .md); thư mục thì nén .zip rồi mới tải.
      acts += it.type === "dir"
        ? '<button data-act="zip" title="Tải cả thư mục về máy (nén .zip)">⤓ Zip</button>'
        : '<button data-act="dl" title="Tải file về máy">⤓ Tải</button>';
      acts += '<button data-act="del" class="danger" title="Xoá">Xoá</button>';
      div.innerHTML = `<span class="fm-ico">${it.type === "dir" ? ic("folder") : _fileIcon(it.ext)}</span>
        <span class="fm-name">${esc(it.name)}</span>
        <span class="fm-size">${it.type === "dir" ? "" : _humanSize(it.size)}</span>
        <span class="fm-row-act">${acts}</span>`;
      // Click TÊN: thư mục → mở vào; ảnh/pdf/text → xem trước; file khác → mở tab mới.
      const nameGo = it.type === "dir" ? () => load(rel)
        : (editable || viewable) ? () => moTrongTrang(rel, it)
        : () => window.open(rawUrl(rel), "_blank");
      div.querySelector(".fm-name").onclick = nameGo; div.querySelector(".fm-ico").onclick = nameGo;
      div.querySelectorAll("[data-act]").forEach(b => b.onclick = (e) => {
        e.stopPropagation(); const a = b.dataset.act;
        if (a === "edit" || a === "view") moTrongTrang(rel, it);
        else if (a === "open") window.open(rawUrl(rel), "_blank");
        else if (a === "dl") _dlFile(rel);
        else if (a === "zip") _dlFolder(rel, it.name);
        else if (a === "ren") doRename(rel, it.name);
        else if (a === "del") doDelete(rel, it.name);
      });
      return div;
    }
    // Mở file NGAY TRONG TRANG, bằng ĐÚNG trình sửa của khung chat (#noteEditor) - không popup nữa.
    //
    // Popup cũ (.fm-modal) là một trình sửa thứ hai, nghèo hơn hẳn: một ô textarea trần, không
    // WYSIWYG, không thanh định dạng, không Lùi/Tiến, không đổi tên/xoá, không phóng to. Mở cùng
    // MỘT file .md từ chat và từ trang Tệp tin lại ra hai trải nghiệm khác hẳn nhau (chủ repo báo
    // 2026-08-13). Nay mượn chính node trình sửa kia, y như cách trang Trò chuyện vẫn mượn.
    function moTrongTrang(rel, it) {
      const slot = el.querySelector("#fmEdit");
      if (!slot) { window.open(rawUrl(rel), "_blank"); return; }
      const ten = (it && it.name) || String(rel).split("/").pop();
      // Đuôi file suy từ TÊN khi người gọi không đưa: openNote chọn nhánh (soạn thảo / xem ảnh /
      // tải về) theo đuôi, thiếu đuôi là file .md cũng rơi vào cửa "hãy tải về".
      const duoi = (it && it.ext) || (ten.includes(".") ? "." + ten.split(".").pop().toLowerCase() : "");
      _fmSauKhiDong = () => { load(cur); };   // đóng trình sửa → danh sách khớp lại (file có thể vừa đổi tên/xoá)
      _borrowNoteEditor(slot);
      openNote(rel, { name: ten, ext: duoi, type: "file" });
    }
    async function doRename(rel, oldname) {
      const nn = prompt("Tên mới:", oldname); if (!nn || nn === oldname) return;
      const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel); fd.append("newname", nn);
      await fetch("/files/rename", { method: "POST", body: fd }); load(cur);
    }
    async function doDelete(rel, name) {
      if (!confirm(`Xoá "${name}"? Không thể hoàn tác.`)) return;
      const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel);
      await fetch("/files/delete", { method: "POST", body: fd }); load(cur);
    }
    searchInput.oninput = () => {
      searchClear.hidden = !searchInput.value;
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(runSearch, 260);
    };
    searchInput.onkeydown = (e) => {
      if (e.key === "Enter") { e.preventDefault(); if (searchTimer) clearTimeout(searchTimer); runSearch(); }
      else if (e.key === "Escape" && searchInput.value) { e.stopPropagation(); load(cur); }
    };
    searchClear.onclick = () => load(cur);
    el.querySelector("#fmSearchName").onclick = () => setSearchMode("name");
    el.querySelector("#fmSearchContent").onclick = () => setSearchMode("content");
    el.querySelector("#fmUp").onclick = () => { if (upTarget !== null && upTarget !== undefined) load(upTarget); };
    el.querySelector("#fmHome").onclick = () => load(undefined);   // undefined = về brain (điểm vào mặc định)
    el.querySelector("#fmRefresh").onclick = () => load(cur);
    el.querySelector("#fmZipCur").onclick = async (e) => {
      const b = e.currentTarget, old = b.textContent;
      b.textContent = "Đang nén..."; b.disabled = true;
      try { await _dlFolder(cur, cur.split("/").pop() || "brain"); }
      finally { b.textContent = old; b.disabled = false; }
    };
    el.querySelector("#fmNewDir").onclick = async () => {
      const n = prompt("Tên thư mục mới:"); if (!n) return;
      const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", cur); fd.append("name", n);
      await fetch("/files/mkdir", { method: "POST", body: fd }); load(cur);
    };
    el.querySelector("#fmNewFile").onclick = async () => {
      const n = prompt("Tên file mới (vd ghi-chu.md):"); if (!n) return;
      const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", (cur ? cur + "/" : "") + n); fd.append("content", "");
      await fetch("/files/write", { method: "POST", body: fd }); load(cur);
    };
    el.querySelector("#fmUpload").onchange = async (e) => {
      for (const f of e.target.files) {
        const fd = new FormData(); fd.append("file", f); fd.append("brain", fbrain()); fd.append("path", cur);
        await fetch("/files/upload", { method: "POST", body: fd });
      }
      load(cur);
    };
    // Sau khi nạp thư mục: cuộn tới đúng file mục tiêu + tô sáng để "tìm thấy vị trí" ngay.
    function revealFile(name) {
      let hit = null;
      listEl.querySelectorAll(".fm-row").forEach(r => {
        r.classList.remove("fm-target");
        const nm = r.querySelector(".fm-name");
        if (nm && nm.textContent === name) hit = r;
      });
      if (!hit) return;
      hit.classList.add("fm-target");
      try { hit.scrollIntoView({ block: "center", behavior: "smooth" }); } catch (e) {}
    }
    // Mở đúng vị trí một mục tiêu từ chat: path trong chat tương đối GỐC BRAIN, còn load() tính theo
    // TRẦN duyệt → cần ghép tiền tố brain (home) mà /files/list trả về.
    async function openVaultTarget(brainRelDir, fileName) {
      let home = "";
      try { const d = await (await fetch(`/files/list?brain=${encodeURIComponent(fbrain())}`)).json(); home = d.home || ""; }
      catch (e) {}
      const full = brainRelDir ? (home ? home + "/" + brainRelDir : brainRelDir) : (home || undefined);
      const d = await load(full);
      // Đường dẫn hoá ra trỏ vào một FILE (server trả `focus` kèm thư mục cha): đó là thứ người
      // dùng nhắm tới, nên MỞ THẲNG ra sửa. Đây chính là cú bấm "tưởng là thư mục" - trước đây
      // nó rơi vào một trang trống ghi "Không phải thư mục".
      if (d && d.focus) { revealFile(d.focus); moTrongTrang(cur ? cur + "/" + d.focus : d.focus, { name: d.focus }); return; }
      if (!fileName) return;
      revealFile(fileName);
      // Có tên file mà thư mục này không chứa nó → cũng là một link trỏ hụt, đi tìm cho ra.
      if (!listEl.querySelector(".fm-row.fm-target")) khongThayFile(brainRelDir ? brainRelDir + "/" + fileName : fileName);
    }
    const pend = _fmPending; _fmPending = null;
    if (pend) openVaultTarget(pend.dir, pend.file);
    else load();   // undefined → điểm vào mặc định = brain (dù trần duyệt có thể là cả ổ đĩa)
    soiMdHong();   // chạy nền: im lặng nếu không có file nào hỏng
  }

  // ============================================
  // Trang Tự cải thiện (Nhiệm vụ tự động chạy nền)
  // ============================================
  // ============================================
  // Trang PLUGINS - tool/hook native cho mọi engine (bundled / toàn cục / brain)
  // ============================================
  async function renderPlugins(el) {
    _injectExtraCss();
    const myGen = _renderGen;   // chống race: đổi trang → load dở tự bỏ
    el.innerHTML = `<div class="cview-section"><div class="empty">Đang tải...</div></div>`;

    const SRC = { bundled: ["Có sẵn", "var(--green)"], user: ["Toàn cục", "var(--link-ink)"], vault: ["Brain này", "var(--warn-ink)"] };
    const srcBadge = (s) => {
      const [t, c] = SRC[s] || [s, "var(--text3)"];
      return `<span style="font-size:11px;padding:2px 7px;border-radius:99px;border:1px solid ${c}55;color:${c}">${esc(t)}</span>`;
    };
    // Tham số thứ hai là TÊN icon, không phải HTML: giữ esc() bắt buộc cho phần
    // chữ nên không thể vô tình nhét HTML thô vào qua đường này.
    const chip = (t, iconName) => `<span style="font-size:11px;padding:2px 7px;border-radius:6px;background:var(--surface-2);color:var(--text2);margin:0 4px 4px 0;display:inline-block">${iconName ? ic(iconName) + " " : ""}${esc(t)}</span>`;
    const MM = { readonly: "chỉ đọc", safe: "ghi (safe)", full: "toàn quyền" };

    function card(p) {
      const status = p.error ? `<span style="color:var(--red)">${WARN_ICON} lỗi</span>`
        : p.gated ? `<span style="color:var(--warn-ink)">${WARN_ICON} chờ bật env</span>`
        : p.loaded ? `<span style="color:var(--green)">● đang chạy</span>`
        : p.enabled ? `<span style="color:var(--warn-ink)">● bật (chưa nạp)</span>`
        : `<span style="color:var(--text3)">○ tắt</span>`;
      const meta = [MM[p.min_mode] ? `quyền tối thiểu: ${MM[p.min_mode]}` : "",
                    p.version ? `v${esc(p.version)}` : "", p.author ? esc(p.author) : ""].filter(Boolean).join(" · ");
      const chips = (p.tools || []).map(t => chip(t, "wrench")).join("") + (p.hooks || []).map(h => chip(h, "webhook")).join("");
      const div = document.createElement("div");
      div.className = "wf-card" + (p.loaded ? "" : " off");
      div.innerHTML = `
        <div class="wf-top">
          <div class="wf-name">${ic("puzzle")} ${esc(p.name)} <span class="dim" style="font-size:12px">${esc(p.slug)}</span> ${srcBadge(p.source)}</div>
          <div>${status}</div>
        </div>
        <div class="wf-desc">${esc(p.description || "")}</div>
        <div class="wf-steps">${meta}${chips ? `<div style="margin-top:8px">${chips}</div>` : ""}${p.error ? `<div style="margin-top:6px;color:var(--red)">${esc(p.error)}</div>` : ""}</div>
        <div class="wf-actions"><button class="s-btn-ghost tgl">${p.enabled ? "Tắt" : "Bật"}</button></div>`;
      div.querySelector(".tgl").onclick = async () => {
        const fd = new FormData();
        fd.append("slug", p.slug); fd.append("enabled", p.enabled ? "0" : "1"); fd.append("brain", fbrain());
        let r = {}; try { r = await (await fetch("/plugins/toggle", { method: "POST", body: fd })).json(); } catch (e) { r = { error: e.message }; }
        if (r && r.error) alert(r.error);
        else if (r && r.note) alert(r.note);
        load();
      };
      return div;
    }

    async function load() {
      if (myGen !== _renderGen) return;
      let d = { plugins: [] };
      try { d = await (await fetch(`/plugins?brain=${encodeURIComponent(fbrain())}`)).json(); } catch (e) {}
      if (myGen !== _renderGen) return;
      const intro = `<p style="color:var(--text3);font-size:15px;max-width:720px;margin:0 0 12px">Plugin thêm <b>tool</b> (công cụ engine gọi được) và <b>hook</b> native cho Javis mà không sửa lõi - dùng được ở MỌI engine (Claude Code, Codex, API) qua hub, tôn trọng 3 mức quyền như tool khác.</p>`;
      const gateBanner = (!d.user_gate) ? `<div style="margin-bottom:14px;padding:11px 13px;border:1px solid rgba(224,160,74,.5);border-radius:10px;background:rgba(224,160,74,.08);color:var(--warn-ink);font-size:13px;line-height:1.55"><b>${WARN_ICON} Plugin do bạn cài đang bị chặn.</b> Plugin toàn cục/brain chạy code Python thật trong server nên mặc định TẮT. Để bật: đặt biến môi trường <code>JAVIS_ENABLE_USER_PLUGINS=true</code> rồi khởi động lại Javis. Plugin có sẵn (bundled) vẫn chạy bình thường.</div>` : "";
      const dirHint = `<p style="color:var(--text3);font-size:12.5px;margin:0 0 14px">Thả plugin TOÀN CỤC (dùng cho MỌI brain) vào <code>${esc(d.global_dir || "")}</code> · mỗi plugin gồm <code>plugin.yaml</code> + <code>plugin.py</code>. Hoặc bảo Javis trong khung chat: "tạo plugin ...".</p>`;
      const plugins = (d.plugins || []).slice();
      const order = { bundled: 0, user: 1, vault: 2 };
      plugins.sort((a, b) => (order[a.source] ?? 9) - (order[b.source] ?? 9) || (a.name || "").localeCompare(b.name || ""));
      const wrap = document.createElement("div");
      wrap.className = "cview-section";
      wrap.innerHTML = intro + gateBanner + dirHint + `<div id="plCards"></div>`;
      const host = wrap.querySelector("#plCards");
      if (!plugins.length) host.innerHTML = `<div class="empty">Chưa có plugin nào. Thả một thư mục plugin vào ${esc(d.global_dir || "thư mục plugins toàn cục")} rồi tải lại.</div>`;
      else plugins.forEach(p => host.appendChild(card(p)));
      el.innerHTML = "";
      el.appendChild(wrap);
    }
    load();
  }

  async function renderSelfImprove(el) {
    _injectExtraCss();
    const myGen = _renderGen;   // chống race: đổi trang → mọi loadLoops/loadLog dở tự bỏ
    let pollTimer = null;       // 1 chuỗi poll duy nhất (clearTimeout trước khi đặt lại)
    el.innerHTML = `<div class="cview-section"><div class="empty">Đang tải...</div></div>`;
    const GNAME = { business: "Kinh doanh", brain: "Bộ não", product: "Cải thiện Javis", custom: "Tự định nghĩa" };
    const fmtT = ts => ts ? new Date(ts * 1000).toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" }) : "-";
    // Giờ TRẦN (chỉ "07:00") không cho biết là hôm nay, mai hay tuần sau - nhìn thẻ việc vẫn
    // không biết bao giờ nó chạy. fmtWhen luôn nói rõ NGÀY khi không phải hôm nay.
    function fmtWhen(ts) {
      if (!ts) return "-";
      const d = new Date(ts * 1000), now = new Date();
      const hm = d.toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" });
      const day = x => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`;
      const tomorrow = new Date(now.getTime() + 86400000);
      if (day(d) === day(now)) return `hôm nay ${hm}`;
      if (day(d) === day(tomorrow)) return `mai ${hm}`;
      return `${hm} ${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
    }
    // "còn 2 giờ 15 phút" - trả lời đúng câu người dùng hỏi trong đầu: bao lâu nữa thì nó chạy.
    function fmtLeft(ts) {
      if (!ts) return "";
      const s = Math.round(ts - Date.now() / 1000);
      if (s <= 0) return "đang tới hạn";
      if (s < 3600) return `còn ${Math.max(1, Math.round(s / 60))} phút`;
      if (s < 86400) {
        const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
        return `còn ${h} giờ${m ? " " + m + " phút" : ""}`;
      }
      return `còn ${Math.round(s / 86400)} ngày`;
    }

    el.innerHTML = `<div class="cview-section">
      <p style="color:var(--text3);font-size:15px;max-width:680px;margin:0 0 14px">Nhiều <b>loop</b> chạy ngầm: mỗi loop tự thức theo chu kỳ, làm <b>một việc</b> bạn mô tả, tự kiểm chứng rồi ghi log. Thực thi <b>tuần tự</b> (1 vòng/lúc). Loop <b>đọc được dữ liệu thật qua MCP</b> (POS, quảng cáo, lịch...) để làm việc, nhưng KHÔNG tự tạo đơn/tiêu tiền/đăng bài - chỉ ghi nháp để bạn duyệt.</p>
      <div class="si-actions" style="margin-bottom:14px">
        <button class="s-btn" id="lpNew">+ Thêm việc</button>
        <button class="s-btn-ghost" id="lpStop">■ Dừng vòng đang chạy</button>
      </div>
      <div id="lpNotifyWarn" style="display:none;margin-bottom:12px;padding:10px 12px;border:1px solid rgba(224,102,74,.5);border-radius:8px;background:rgba(224,102,74,.08);font-size:13px;line-height:1.5"></div>
      <div id="lpForm" style="display:none;margin-bottom:14px;padding:14px;border:1px solid var(--hairline);border-radius:10px;background:var(--surface-1)">
        <input type="hidden" id="lpSlug">
        <input type="hidden" id="lpRemId">
        <div class="si-grid">
          <div class="si-field"><label>Loại việc</label><div class="si-row" id="lpKind">
            <button class="si-chip sel" data-kind="loop">${ic("repeat")} Việc lặp</button>
            <button class="si-chip" data-kind="reminder">${ic("alarm-clock")} Nhắc hẹn</button></div></div>
          <div class="si-field"><label>Tên</label><input id="lpName" placeholder="Ví dụ: Đọc email mỗi 2 tiếng"></div>
          <div class="si-field"><label id="lpBodyLabel">Mô tả nhiệm vụ (mỗi vòng Javis làm đúng việc này)</label>
            <textarea id="lpBody" placeholder="Ví dụ: Mỗi vòng đọc 1 source chưa xử lý trong 06 - Sources rồi đề xuất Wiki page nên tạo. Hoặc: đọc số đơn hôm nay qua MCP POS, nếu thấp thì soạn nháp 1 caption đẩy hàng vào 05 - Projects."></textarea></div>
          <div id="lpLoopFields">
            <div class="si-row" style="gap:14px;flex-wrap:wrap">
              <div class="si-field"><label>Chế độ</label><div class="si-row" id="lpModes">
                <button class="si-chip" data-mode="suggest">Đề xuất (chỉ đọc)</button>
                <button class="si-chip" data-mode="auto">Tự làm (an toàn)</button>
                <button class="si-chip" data-mode="full" style="border-color:rgba(224,102,74,.5)">${WARN_ICON} Toàn quyền</button></div></div>
              <div class="si-field"><label>Chu kỳ (phút, tối thiểu 5)</label><input type="number" id="lpInterval" min="5" value="120" style="max-width:120px"></div>
            </div>
          </div>
          <div id="lpRemFields" style="display:none">
            <div class="si-row" style="gap:14px;flex-wrap:wrap">
              <div class="si-field"><label>Khi nào</label><input id="lpRemWhen" placeholder="Ví dụ: 30 phút nữa · 8h30 · 0 7 * * * · 2026-07-20 09:00" style="min-width:260px"></div>
              <div class="si-field"><label>Kiểu</label><div class="si-row" id="lpRemModes">
                <button class="si-chip sel" data-rmode="notify">${ic("alarm-clock")} Chỉ nhắc</button>
                <button class="si-chip" data-rmode="task">${ic("bot")} Tự làm rồi báo</button></div></div>
              <div class="si-field" id="lpRemMqWrap" style="display:none"><label>Được phép làm gì</label><div class="si-row" id="lpRemMq">
                <button class="si-chip" data-mq="suggest">Chỉ đọc</button>
                <button class="si-chip" data-mq="auto">Ghi file</button>
                <button class="si-chip sel" data-mq="full">Toàn quyền</button></div></div>
            </div>
            <div class="dim" style="font-size:12px;color:var(--text3);margin-top:4px">Nhắc một lần: "30 phút nữa", "8h30", "2026-07-20 09:00". Lặp theo giờ cố định: cron 5 trường (vd "0 7 * * *" = 7h sáng mỗi ngày). "Chỉ nhắc" = bắn tin nhắc bạn; "Tự làm rồi báo" = Javis chạy đúng việc này rồi báo kết quả.</div>
            <div id="lpRemMqWarn" style="display:none;margin-top:6px;padding:10px 12px;border:1px solid rgba(224,102,74,.5);border-radius:8px;background:rgba(224,102,74,.08);color:var(--red);font-size:13px;line-height:1.5">
              <b>${WARN_ICON} TOÀN QUYỀN.</b> Tới giờ việc này chạy <b>một mình</b>, với đầy đủ quyền như lúc bạn đang ngồi chat: nó dùng được mọi công cụ đã đấu, nên tuỳ việc bạn giao mà nó có thể <b>gửi tin, đăng bài, đặt lịch, tạo đơn hoặc tiêu tiền thật</b>. Ở bước đó không có ai duyệt lại, và phần lớn những việc đó <b>không rút lại được</b>. Chỉ giao thứ bạn sẵn sàng để nó tự làm; muốn nó chỉ đọc rồi báo lại thì chọn <b>Chỉ đọc</b>.
            </div>
          </div>
          <div class="si-field"><label>Brain (nơi lưu việc)</label><select id="lpBrain" class="loop-sel" style="min-width:180px"></select></div>
          <div id="lpFullWarn" style="display:none;margin-top:4px;padding:10px 12px;border:1px solid rgba(224,102,74,.5);border-radius:8px;background:rgba(224,102,74,.08);color:var(--red);font-size:13px;line-height:1.5">
            <b>${WARN_ICON} CHẾ ĐỘ TOÀN QUYỀN - rủi ro cao.</b> Loop sẽ tự thao tác THẬT qua MCP không cần hỏi: có thể <b>tạo/sửa đơn hàng, chạy quảng cáo (tiêu tiền thật), gửi tin nhắn/email, đăng bài</b>. Nó chạy nền theo lịch, KHÔNG có người duyệt từng bước, và <b>hành động thật không hoàn tác được</b>. Chỉ bật khi bạn đã tin tưởng loop này và mô tả nhiệm vụ thật rõ ràng, giới hạn phạm vi. Nên chạy thử ở "Đề xuất" hoặc "Tự làm (an toàn)" trước.
          </div>
          <div class="dim" id="lpLoopNote" style="font-size:12px;color:var(--text3);margin-top:2px">Đề xuất = chỉ đọc + gợi ý. Tự làm (an toàn) = ghi nháp file + đọc MCP, KHÔNG tiền/đơn/đăng bài. Toàn quyền = tự thao tác mọi thứ. · Tinh chỉnh nâng cao (giờ im lặng, trần vòng/ngày, thư mục code): sửa file <code>Javis/loops/&lt;tên&gt;.md</code>.</div>
          <div class="si-actions"><button class="s-btn" id="lpSave">${SAVE_ICON} Lưu</button><button class="s-btn-ghost" id="lpCancel">Huỷ</button><span class="dim" id="lpFormMsg" style="font-size:13px;color:var(--warn-ink)"></span></div>
        </div>
      </div>
      <div class="lp-search-row" style="margin:6px 0 10px">
        <input id="lpSearch" type="search" autocomplete="off" placeholder="Tìm việc theo tên..."
          style="width:100%;max-width:340px;padding:8px 12px;border-radius:8px;border:1px solid var(--hairline);background:var(--surface-2);color:var(--text);font-size:14px;outline:none">
        <span class="dim" id="lpSearchNote" style="display:none;font-size:12px;color:var(--text3);margin-left:8px"></span>
      </div>
      <div id="lpGroups">Đang tải...</div>
      <div class="si-log"><h3 style="font-size:15px;color:var(--text)">Nhật ký gần đây · <select id="lpLogFilter" class="loop-sel" style="font-size:13px"><option value="">Tất cả loop</option></select></h3><div id="lpLog">Đang tải...</div></div>
    </div>`;

    let fcur = { mode: "suggest" };
    let fkind = "loop";      // loại việc đang tạo: loop (việc lặp) | reminder (nhắc hẹn)
    let frmode = "notify";   // kiểu nhắc hẹn: notify (chỉ nhắc) | task (tự làm rồi báo)
    let frmq = "full";       // mức quyền của kiểu "task": suggest | auto | full
    function syncFormChips() {
      el.querySelectorAll("#lpModes .si-chip").forEach(x => x.classList.toggle("sel", x.dataset.mode === fcur.mode));
      const w = el.querySelector("#lpFullWarn"); if (w) w.style.display = (fcur.mode === "full" && fkind === "loop") ? "block" : "none";
    }
    el.querySelectorAll("#lpModes .si-chip").forEach(c => c.onclick = () => { fcur.mode = c.dataset.mode; syncFormChips(); });

    // Chuyển giao diện form theo loại việc: loop hiện chế độ + chu kỳ; nhắc hẹn hiện thời điểm + kiểu.
    function syncKindUI() {
      el.querySelectorAll("#lpKind .si-chip").forEach(x => x.classList.toggle("sel", x.dataset.kind === fkind));
      const isRem = fkind === "reminder";
      const q = id => el.querySelector(id);
      if (q("#lpLoopFields")) q("#lpLoopFields").style.display = isRem ? "none" : "";
      if (q("#lpRemFields")) q("#lpRemFields").style.display = isRem ? "" : "none";
      if (q("#lpLoopNote")) q("#lpLoopNote").style.display = isRem ? "none" : "";
      if (isRem && q("#lpFullWarn")) q("#lpFullWarn").style.display = "none";
      q("#lpBodyLabel").textContent = isRem
        ? "Nội dung nhắc (Javis sẽ nhắc hoặc làm đúng việc này)"
        : "Mô tả nhiệm vụ (mỗi vòng Javis làm đúng việc này)";
    }
    el.querySelectorAll("#lpKind .si-chip").forEach(c => c.onclick = () => {
      // Đang SỬA (loop hay nhắc hẹn) → khoá loại: đổi loại giữa đường là ghi sang kho khác,
      // để lại bản gốc ở kho cũ vẫn chạy.
      if (el.querySelector("#lpSlug").value || el.querySelector("#lpRemId").value) return;
      fkind = c.dataset.kind; syncKindUI();
    });
    // Mức quyền chỉ có nghĩa với kiểu "Tự làm rồi báo" - "Chỉ nhắc" không chạy engine nào cả,
    // nên phơi ô đó ra là bày thêm một lựa chọn không làm gì.
    function syncRemMq() {
      const wrap = el.querySelector("#lpRemMqWrap");
      const warn = el.querySelector("#lpRemMqWarn");
      if (wrap) wrap.style.display = frmode === "task" ? "" : "none";
      if (warn) warn.style.display = (frmode === "task" && frmq === "full") ? "block" : "none";
      el.querySelectorAll("#lpRemMq .si-chip").forEach(x => x.classList.toggle("sel", x.dataset.mq === frmq));
    }
    el.querySelectorAll("#lpRemModes .si-chip").forEach(c => c.onclick = () => {
      frmode = c.dataset.rmode;
      el.querySelectorAll("#lpRemModes .si-chip").forEach(x => x.classList.toggle("sel", x.dataset.rmode === frmode));
      syncRemMq();
    });
    el.querySelectorAll("#lpRemMq .si-chip").forEach(c => c.onclick = () => {
      frmq = c.dataset.mq; syncRemMq();
    });

    // "Khi nào" (nhắc hẹn) → payload cho POST /reminders. Cron 5 trường/@macro → {cron};
    // "N phút/tiếng/giờ/ngày [nữa]" → {delay_min}; còn lại (8h30, 07:00, ngày giờ) → {at} để
    // reminders.resolve_due tự hiểu. Chỉ nhận đơn-vị-chữ cho delay để "8h" vẫn là mốc giờ 8h.
    function parseReminderWhen(s) {
      s = (s || "").trim();
      if (!s) return null;
      if (s[0] === "@") return { cron: s };
      const toks = s.split(/\s+/);
      if (toks.length === 5 && toks.every(t => /^[\d*/,\-]+$/.test(t))) return { cron: s };
      // KHÔNG dùng \b sau đơn vị: \b của JS là ranh giới ASCII, mà "giờ" kết thúc bằng ký tự có
      // dấu ("ờ") nên "1.5 giờ" ở cuối chuỗi sẽ trượt. Alternation đã đủ đặc trưng để không khớp bừa.
      const m = s.toLowerCase().match(/^(\d+(?:[.,]\d+)?)\s*(phút|phut|tiếng|tieng|giờ|gio|ngày|ngay)/);
      if (m) {
        const num = parseFloat(m[1].replace(",", "."));
        const u = m[2];
        const mins = (u === "ngày" || u === "ngay") ? num * 1440
          : (u === "tiếng" || u === "tieng" || u === "giờ" || u === "gio") ? num * 60 : num;
        return { delay_min: Math.max(1, Math.round(mins)) };
      }
      return { at: s };
    }

    async function createReminder(payload) {
      try {
        return await (await fetch("/reminders", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        })).json();
      } catch (e) { return { ok: false, error: e.message }; }
    }

    let allLoops = [];    // phẳng mọi brain - cho bộ lọc nhật ký (log per brain+slug)
    let allBrains = [];   // [{name, path, is_default}] - cho ô chọn brain (tạo mới + chuyển)

    // Nạp danh sách brain cho ô chọn ĐỘC LẬP với /viec/all (vốn nặng: quét note mọi brain).
    // /brains là nguồn chuẩn của sidebar - nhanh + luôn sẵn, nên form không bao giờ trống ô brain
    // dù /viec/all còn đang tải hoặc lỗi. Đây là gốc bug "phần brain không thấy để chọn".
    async function ensureBrains() {
      if (allBrains.length) return;
      try {
        const d = await (await fetch("/brains")).json();
        allBrains = (d.brains || []).map(b => ({ name: b.name, path: b.path, is_default: b.is_default }));
      } catch (e) {}
    }

    function isCurrentBrain(b) {
      const cur = fbrain();   // path brain đang chọn ở sidebar, hoặc "brain" (mặc định)
      return cur === "brain" ? !!b.is_default : b.path === cur;
    }
    // Options brain cho nút "Chuyển sang..." - bỏ chính brain của item (không chuyển sang chỗ cũ).
    function moveOptions(exceptPath) {
      return allBrains.filter(b => b.path !== exceptPath)
        .map(b => `<option value="${esc(b.path)}">${esc(b.name)}</option>`).join("");
    }

    // openForm(loop) = tạo/sửa việc lặp · openForm(null, rem) = SỬA một nhắc hẹn/lịch cron.
    // Trước đây nhắc hẹn tạo xong là bất động (chỉ huỷ/chuyển brain) - muốn đổi giờ cron phải
    // xoá rồi tạo lại, đúng chỗ khách báo "không sửa được lịch cron".
    async function openForm(lp, rem) {
      await ensureBrains();   // đảm bảo ô brain luôn có lựa chọn dù /viec/all chưa tải xong
      fcur = { mode: lp ? lp.mode : "suggest" };
      fkind = rem ? "reminder" : "loop";
      frmode = rem && rem.mode === "task" ? "task" : "notify";
      // Mở form một nhắc hẹn cũ thì hiện ĐÚNG mức nó đang chạy (bản ghi cũ chưa có trường này
      // thì server đã quy về mặc định trong _view, nên chỗ này không phải đoán lại).
      frmq = (rem && rem.muc_quyen) || "full";
      const locked = !!(lp || rem);   // đang SỬA (loop hay nhắc) → khoá loại việc + brain
      el.querySelector("#lpSlug").value = lp ? lp.slug : "";
      el.querySelector("#lpRemId").value = rem ? rem.id : "";
      el.querySelector("#lpName").value = rem ? (rem.label || "") : (lp ? lp.name : "");
      el.querySelector("#lpBody").value = rem ? (rem.text || "") : (lp ? (lp.body || "") : "");
      el.querySelector("#lpInterval").value = lp ? lp.interval_min : 120;
      // Cron sửa được nguyên văn (không phụ thuộc múi giờ). Hẹn MỘT LẦN thì để trống + nói rõ
      // "trống = giữ nguyên", vì viết lại mốc giờ tuyệt đối dễ lệch múi giờ máy người dùng.
      const when = el.querySelector("#lpRemWhen");
      when.value = rem && rem.cron ? rem.cron : "";
      when.placeholder = (rem && !rem.cron)
        ? `Để trống nếu giữ nguyên (đang hẹn ${fmtWhen(rem.due_at)})`
        : "30 phút nữa · 8h30 · 0 7 * * * · 2026-07-20 09:00";
      // Job script giữ nguyên kiểu (đổi kiểu là mất tên file script) → khoá hai nút Kiểu cho khỏi
      // tưởng đang đổi được; server cũng bỏ qua trường mode với loại này.
      const isScript = !!(rem && rem.script);
      el.querySelectorAll("#lpRemModes .si-chip").forEach(x => {
        x.classList.toggle("sel", !isScript && x.dataset.rmode === frmode);
        x.disabled = isScript; x.style.opacity = isScript ? .45 : 1;
      });
      el.querySelector("#lpFormMsg").textContent = isScript
        ? `Job script "${rem.script}" - sửa được tên, nội dung và lịch; kiểu giữ nguyên.` : "";
      // Khoá bộ chọn loại khi SỬA (chỉ đổi được lúc tạo mới); mờ đi cho rõ.
      el.querySelectorAll("#lpKind .si-chip").forEach(x => { x.disabled = locked; x.style.opacity = locked ? .45 : 1; });
      // Ô chọn brain: TẠO MỚI cho chọn (mặc định brain đang xem); SỬA thì khoá về brain của việc
      // (đổi brain lúc sửa sẽ đẻ file mới ở brain khác mà bản gốc vẫn còn - muốn dời thì dùng nút
      // "Chuyển sang brain" trên thẻ, có kiểm tra trùng + dời state đàng hoàng).
      const bsel = el.querySelector("#lpBrain");
      const defPath = (lp || rem) ? ((lp || rem).brain_path || "")
        : ((allBrains.find(isCurrentBrain) || allBrains[0] || {}).path || "");
      bsel.innerHTML = allBrains.map(b =>
        `<option value="${esc(b.path)}" ${b.path === defPath ? "selected" : ""}>${esc(b.name)}</option>`).join("");
      bsel.disabled = locked;
      syncKindUI();
      syncFormChips();
      syncRemMq();
      el.querySelector("#lpForm").style.display = "block";
      el.querySelector("#lpName").focus();
    }
    el.querySelector("#lpNew").onclick = () => openForm(null);
    el.querySelector("#lpCancel").onclick = () => { el.querySelector("#lpForm").style.display = "none"; };

    el.querySelector("#lpSave").onclick = async () => {
      const name = el.querySelector("#lpName").value.trim();
      const body = el.querySelector("#lpBody").value.trim();
      const msg = el.querySelector("#lpFormMsg");
      const brainVal = el.querySelector("#lpBrain").value || fbrain();   // brain đích do user chọn
      const b = el.querySelector("#lpSave");
      if (!name) { msg.textContent = "Nhập tên"; return; }
      if (!body) { msg.textContent = fkind === "reminder" ? "Nhập nội dung nhắc" : "Nhập mô tả nhiệm vụ (Javis cần biết mỗi vòng làm gì)"; return; }

      // NHẮC HẸN → kho reminders. Tạo mới: POST /reminders. Đang sửa: POST /reminders/update.
      if (fkind === "reminder") {
        const remId = el.querySelector("#lpRemId").value;
        const whenRaw = el.querySelector("#lpRemWhen").value.trim();
        const timePayload = whenRaw ? parseReminderWhen(whenRaw) : null;
        if (!remId && !timePayload) { msg.textContent = 'Nhập thời điểm (vd "30 phút nữa", "8h30", "0 7 * * *")'; return; }
        b.textContent = "Đang lưu...";
        let r = {};
        if (remId) {
          const f = new FormData();
          f.append("id", remId); f.append("brain", brainVal);
          f.append("label", name); f.append("text", body); f.append("mode", frmode);
          f.append("muc_quyen", frmq);
          if (timePayload) Object.keys(timePayload).forEach(k => f.append(k, timePayload[k]));
          try { r = await (await fetch("/reminders/update", { method: "POST", body: f })).json(); }
          catch (e) { r = { error: e.message }; }
        } else {
          r = await createReminder(Object.assign(
            { text: body, label: name, mode: frmode, muc_quyen: frmq, brain: brainVal,
              created_by: "dashboard" }, timePayload));
        }
        b.innerHTML = SAVE_ICON + " Lưu";
        if (!r.ok) {
          // can_force = server chặn vì THIẾU ĐIỀU KIỆN (chưa đấu Telegram thì không báo được kết
          // quả cho ai). Nói rõ thiếu gì, và để người dùng tự quyết có tạo tiếp hay không.
          if (r.can_force) {
            msg.innerHTML = Icons.warn(r.error || "Chưa đủ điều kiện")
              + ` <button class="s-btn-ghost" id="lpForce" style="margin-left:6px">Vẫn tạo</button>`;
            const fb = el.querySelector("#lpForce");
            if (fb) fb.onclick = async () => {
              const r2 = await createReminder(Object.assign(
                { text: body, label: name, mode: frmode, muc_quyen: frmq, brain: brainVal,
                  created_by: "dashboard", allow_no_channel: true }, timePayload));
              if (!r2.ok) { msg.innerHTML = Icons.warn(r2.error || "Lưu lỗi"); return; }
              el.querySelector("#lpForm").style.display = "none";
              loadAll();
            };
          } else msg.innerHTML = Icons.warn(r.error || "Lưu lỗi");
          return;
        }
        el.querySelector("#lpForm").style.display = "none";
        loadAll();
        return;
      }

      // LOOP → POST /loops (file Javis/loops/<slug>.md).
      if (fcur.mode === "full" && !confirm(`Bật CHẾ ĐỘ TOÀN QUYỀN cho loop "${name}"?\n\nLoop sẽ tự thao tác THẬT qua MCP không cần hỏi: tạo/sửa đơn, chạy quảng cáo (tiêu tiền thật), gửi tin, đăng bài. Chạy nền theo lịch, KHÔNG duyệt từng bước, hành động KHÔNG hoàn tác được.\n\nAnh chắc chắn chứ?`)) return;
      const fd = new FormData();
      fd.append("slug", el.querySelector("#lpSlug").value);
      fd.append("name", name);
      fd.append("mode", fcur.mode);
      fd.append("interval_min", el.querySelector("#lpInterval").value || "120");
      fd.append("body", body);
      fd.append("brain", brainVal);
      // Không gửi goal/workspace/tools_profile/quiet/maxruns → server giữ giá trị cũ (khi sửa)
      // hoặc mặc định an toàn (tạo mới: goal=custom, vault + MCP đọc).
      b.textContent = "Đang lưu...";
      let r = {}; try { r = await (await fetch("/loops", { method: "POST", body: fd })).json(); } catch (e) { r = { error: e.message }; }
      b.innerHTML = SAVE_ICON + " Lưu";
      if (!r.ok) { msg.innerHTML = Icons.warn(r.error || "Lưu lỗi"); return; }
      el.querySelector("#lpForm").style.display = "none";
      loadAll(); loadLog();
    };

    el.querySelector("#lpStop").onclick = async () => { await fetch("/loops/stop", { method: "POST" }); loadAll(); };

    // Chuẩn hoá chuỗi để tìm kiếm: thường + bỏ dấu tiếng Việt (gõ "email" khớp "Email", "kho"
    // khớp "khô") + đ→d. Dùng cho cả gắn nhãn thẻ việc lẫn từ khoá người dùng gõ.
    function _lpNorm(s) {
      return String(s == null ? "" : s).toLowerCase()
        .normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d");
    }
    // Lọc các thẻ việc trong #lpGroups theo ô tìm kiếm. Ẩn thẻ không khớp; ẩn luôn tiêu đề brain /
    // "Nhắc hẹn đang chờ" khi cả nhóm/mục không còn thẻ nào hiện. Gọi lại sau mỗi lần render danh sách.
    function applyLpSearch() {
      const input = el.querySelector("#lpSearch");
      const note = el.querySelector("#lpSearchNote");
      const q = _lpNorm(input ? input.value.trim() : "");
      let shown = 0, totalCards = 0;
      el.querySelectorAll("#lpGroups .lp-group").forEach(group => {
        let groupShown = 0, remShown = 0;
        group.querySelectorAll(".wf-card").forEach(card => {
          totalCards++;
          const hit = !q || (card.dataset.search || "").indexOf(q) !== -1;
          card.style.display = hit ? "" : "none";
          if (hit) { groupShown++; shown++; if (card.dataset.kind === "rem") remShown++; }
        });
        const remHead = group.querySelector('[data-lp="remhead"]');
        if (remHead) remHead.style.display = (q && !remShown) ? "none" : "";
        const emptyRow = group.querySelector('[data-lp="empty"]');
        if (emptyRow) emptyRow.style.display = q ? "none" : "";
        group.style.display = (q && !groupShown) ? "none" : "";
      });
      if (note) {
        if (q && !shown && totalCards) { note.style.display = ""; note.textContent = "Không có việc nào khớp."; }
        else note.style.display = "none";
      }
    }

    function loopCard(lp) {
      const paused = !!lp.auto_paused_reason;
      const dot = lp.running ? `<span style="color:var(--green)">${ic("loader", { cls: "ic-spin" })} đang chạy</span>`
        : paused ? `<span style="color:var(--warn-ink)">${WARN_ICON} tự tạm dừng</span>`
        : lp.enabled ? `<span style="color:var(--green)">● bật</span>` : `<span style="color:var(--text3)">○ tắt</span>`;
      const verify = lp.last_status && lp.last_status !== "ok"
        ? ` · ${esc(lp.last_status.slice(0, 90))}` : (lp.last_status === "ok" ? " · ok" : "");
      const last = lp.last_run ? `lần cuối ${fmtWhen(lp.last_run)}` : "chưa chạy";
      const next = (lp.enabled && !paused && lp.next_run)
        ? ` · kế tiếp ~${fmtWhen(lp.next_run)} (${fmtLeft(lp.next_run)})`
        : (lp.enabled ? "" : " · đang tắt nên chưa có lần chạy kế tiếp");
      const modeLbl = lp.mode === "full" ? `<span style="color:var(--red);font-weight:600">${WARN_ICON} toàn quyền</span>`
        : lp.mode === "auto" ? "tự làm (an toàn)" : "đề xuất";
      const extra = [
        `${modeLbl} · mỗi ${lp.interval_min} phút`,
        (lp.goal && lp.goal !== "custom") ? (GNAME[lp.goal] || lp.goal) : "",
        lp.quiet_hours ? `im lặng ${lp.quiet_hours}` : "",
        lp.max_runs_per_day ? `tối đa ${lp.max_runs_per_day}/ngày (đã ${lp.runs_today})` : "",
        lp.tools_profile === "code" ? `${ic("settings")} code · ${esc(lp.workspace)}` : "",
      ].filter(Boolean).join(" · ");
      const div = document.createElement("div");
      div.className = "wf-card" + (lp.enabled ? "" : " off");
      div.dataset.kind = "loop";
      div.dataset.search = _lpNorm(`${lp.name} ${lp.slug} ${lp.goal || ""} ${GNAME[lp.goal] || ""}`);
      div.innerHTML = `
        <div class="wf-top"><div class="wf-name">${ic("repeat")} ${esc(lp.name)} <span class="dim" style="font-size:12px">${esc(lp.slug)}</span></div><div>${dot}</div></div>
        <div class="wf-desc">${extra}</div>
        <div class="wf-steps">${last}${verify}${next}${paused ? `<br>${WARN_ICON} ${esc(lp.auto_paused_reason)}` : ""}</div>
        <div class="wf-actions">
          <button class="s-btn-ghost tgl">${lp.enabled ? "Tắt" : "Bật"}</button>
          <button class="s-btn-ghost run">▶ Chạy ngay</button>
          <button class="s-btn-ghost edit">Sửa</button>
          <button class="s-btn-ghost del" style="color:var(--red)">Xoá</button>
          <select class="mv loop-sel" style="font-size:12px"><option value="">Chuyển brain…</option>${moveOptions(lp.brain_path)}</select>
        </div>`;
      // MỌI thao tác gửi brain của CHÍNH item (lp.brain_path), KHÔNG phải fbrain() - trang này gộp
      // nhiều brain nên bám sidebar sẽ nhắm nhầm brain.
      div.querySelector(".tgl").onclick = async () => {
        // Bật loop TOÀN QUYỀN = xác nhận rủi ro (tắt thì khỏi hỏi)
        if (!lp.enabled && lp.mode === "full" &&
            !confirm(`Bật loop TOÀN QUYỀN "${lp.name}"?\n\nNó sẽ tự thao tác THẬT qua MCP (tạo đơn, tiêu tiền quảng cáo, gửi tin, đăng bài) theo lịch, không duyệt từng bước. Chắc chứ?`)) return;
        await fetch("/loops/toggle", { method: "POST", body: (() => { const f = new FormData(); f.append("slug", lp.slug); f.append("brain", lp.brain_path); return f; })() });
        loadAll();
      };
      div.querySelector(".run").onclick = async (e) => {
        e.target.disabled = true; e.target.textContent = "Đang chạy...";
        await fetch("/loops/run-now", { method: "POST", body: (() => { const f = new FormData(); f.append("slug", lp.slug); f.append("brain", lp.brain_path); return f; })() });
        setTimeout(() => { loadAll(); loadLog(); }, 2500);
      };
      div.querySelector(".edit").onclick = () => openForm(lp);
      div.querySelector(".del").onclick = async () => {
        if (!confirm(`Xoá loop "${lp.name}"? File Javis/loops/${lp.slug}.md sẽ bị xoá.`)) return;
        await fetch("/loops/delete", { method: "POST", body: (() => { const f = new FormData(); f.append("slug", lp.slug); f.append("brain", lp.brain_path); return f; })() });
        loadAll(); loadLog();
      };
      div.querySelector(".mv").onchange = async (e) => {
        const to = e.target.value; if (!to) return;
        const toName = (allBrains.find(b => b.path === to) || {}).name || to;
        if (!confirm(`Chuyển việc "${lp.name}" sang brain ${toName}?`)) { e.target.value = ""; return; }
        const f = new FormData();
        f.append("slug", lp.slug); f.append("from_brain", lp.brain_path); f.append("to_brain", to);
        let r = {}; try { r = await (await fetch("/loops/move", { method: "POST", body: f })).json(); } catch (er) { r = { error: er.message }; }
        if (!r.ok) alert("Không chuyển được: " + (r.error || "lỗi"));
        loadAll(); loadLog();
      };
      return div;
    }

    // Nhắc hẹn đang chờ: gộp cùng loop trong mỗi nhóm brain. Loop = việc bền (.md, sửa trong
    // Obsidian); nhắc = việc phù du. Cả hai đều gắn brain_path để thao tác đúng brain.
    const MODE_LBL = { notify: "nhắc", task: "tự làm + báo", script: "script" };
    // Mức quyền của nhắc hẹn kiểu "tự làm": phải hiện trên thẻ. Việc này tới giờ chạy một mình,
    // nên "nó được phép làm tới đâu" là thứ người dùng cần liếc một cái là biết, không phải mở
    // form Sửa mới thấy.
    const MQ_LBL = { suggest: "chỉ đọc", auto: "được ghi file", full: "toàn quyền" };
    // Câu tả LỊCH của một nhắc hẹn. Trước đây thẻ cron chỉ in "cron 0 7 * * *" rồi hết - không
    // đọc được lịch, cũng không biết lần chạy kế tiếp là lúc nào (lỗi khách báo).
    function remWhen(r) {
      const next = r.due_at ? `kế tiếp ${fmtWhen(r.due_at)} (${fmtLeft(r.due_at)})` : "";
      if (r.cron) {
        const human = r.cron_human || r.cron;
        return `${human} · ${next}`.replace(/ · $/, "");
      }
      if (r.repeat_min) return `lặp mỗi ${r.repeat_min} phút · ${next}`.replace(/ · $/, "");
      return next ? `một lần, ${next}` : (r.due_human || "");
    }
    function reminderCard(r) {
      const title = r.label || r.text || "Nhắc hẹn";
      const when = remWhen(r);
      const kind = MODE_LBL[r.mode] || "nhắc";
      const mq = r.mode === "task" ? (MQ_LBL[r.muc_quyen] || "") : "";
      const div = document.createElement("div");
      div.className = "wf-card";
      div.dataset.kind = "rem";
      div.dataset.search = _lpNorm(`${title} ${when} ${r.cron || ""} ${kind} ${mq}`);
      div.innerHTML = `<b>${ic("alarm-clock")} ${esc(title)}</b>
        <div class="dim" style="font-size:12px;color:var(--text3)">${esc(when)} · ${esc(kind)}${mq ? ` · <span class="rm-mq${r.muc_quyen === "full" ? " on" : ""}">${esc(mq)}</span>` : ""}${r.cron ? ` · <code>${esc(r.cron)}</code>` : ""}</div>
        ${r.error ? `<div style="font-size:12px;color:var(--warn-ink);margin-top:4px">${WARN_ICON} lần chạy trước lỗi: ${esc(r.error.slice(0, 160))}</div>` : ""}
        <div class="wf-actions" style="margin-top:8px">
          <button class="s-btn-ghost rmEdit">Sửa</button>
          <button class="s-btn-ghost rmCancel">Huỷ</button>
          <button class="s-btn-ghost rmDel" style="color:var(--red)">Xoá</button>
          <select class="mv loop-sel" style="font-size:12px"><option value="">Chuyển brain…</option>${moveOptions(r.brain_path)}</select>
        </div>`;
      div.querySelector(".rmEdit").onclick = () => openForm(null, r);
      div.querySelector(".rmCancel").onclick = async () => {
        if (!confirm(`Huỷ "${title}"?\n\nMục này ngừng chạy nhưng vẫn còn trong lịch sử. Muốn mất hẳn thì bấm Xoá.`)) return;
        const f = new FormData();
        f.append("id", r.id);        // id THÔ, /reminders/cancel nhận đúng dạng này
        f.append("brain", r.brain_path);
        await fetch("/reminders/cancel", { method: "POST", body: f });
        loadAll();
      };
      div.querySelector(".rmDel").onclick = async () => {
        if (!confirm(`Xoá hẳn "${title}"? Không hoàn tác được.`)) return;
        const f = new FormData();
        f.append("id", r.id); f.append("brain", r.brain_path);
        let rr = {}; try { rr = await (await fetch("/reminders/delete", { method: "POST", body: f })).json(); } catch (er) { rr = { error: er.message }; }
        if (!rr.ok) alert("Không xoá được: " + (rr.error || "lỗi"));
        loadAll();
      };
      div.querySelector(".mv").onchange = async (e) => {
        const to = e.target.value; if (!to) return;
        const toName = (allBrains.find(b => b.path === to) || {}).name || to;
        if (!confirm(`Chuyển nhắc "${title}" sang brain ${toName}?`)) { e.target.value = ""; return; }
        const f = new FormData();
        f.append("id", r.id); f.append("from_brain", r.brain_path); f.append("to_brain", to);
        let rr = {}; try { rr = await (await fetch("/reminders/move", { method: "POST", body: f })).json(); } catch (er) { rr = { error: er.message }; }
        if (!rr.ok) alert("Không chuyển được: " + (rr.error || "lỗi"));
        loadAll();
      };
      return div;
    }

    // Gộp MỌI brain: /viec/all trả từng brain kèm loop + nhắc hẹn. Nhóm theo brain, brain đang
    // xem ở sidebar lên đầu; brain khác rỗng thì ẩn. Mỗi item mang brain_path riêng.
    async function loadAll(retried) {
      if (myGen !== _renderGen) return;
      let d = null, loadErr = false;
      try { d = await (await fetch("/viec/all")).json(); } catch (e) { loadErr = true; }
      if (myGen !== _renderGen) return;
      const box = el.querySelector("#lpGroups");
      if (!box) return;
      // /viec/all lỗi/hết-giờ (VPS chậm) → tự thử lại 1 lần sau 1.5s (vượt qua nhịp chậm/nghẽn
      // thoáng qua), rồi mới BÁO RÕ + cho bấm thử lại. KHÔNG im lặng hiện "chưa có việc" (dễ tưởng
      // việc biến mất). Giữ danh sách brain cũ + ensureBrains cho ô chọn của form.
      if (loadErr || !d || !d.brains) {
        ensureBrains();
        if (!retried) {
          box.innerHTML = `<div class="empty">Đang tải danh sách việc...</div>`;
          setTimeout(() => { if (myGen === _renderGen) loadAll(true); }, 1500);
          return;
        }
        box.innerHTML = `<div class="empty">Không tải được danh sách việc (mạng chậm hoặc hết giờ). <a href="#" id="lpRetry" style="color:var(--link-ink)">Thử lại</a></div>`;
        const rt = el.querySelector("#lpRetry");
        if (rt) rt.onclick = (ev) => { ev.preventDefault(); loadAll(); loadLog(); };
        return;
      }
      allBrains = (d.brains || []).map(b => ({ name: b.name, path: b.path, is_default: b.is_default }));
      // Chưa đấu Telegram = việc vẫn chạy đúng giờ nhưng kết quả không tới tay ai. Người dùng
      // không tự đoán ra điều đó, nên nói thẳng ở đầu trang kèm lối đi sang trang Kênh.
      const nw = el.querySelector("#lpNotifyWarn");
      if (nw) {
        const nt = d.notify || {};
        const bad = nt.ok === false;            // chưa đấu gì cả
        const warn = !bad && nt.warn;           // đấu rồi nhưng bot đang lỗi thật
        nw.style.display = (bad || warn) ? "block" : "none";
        if (bad || warn) {
          nw.innerHTML = bad
            ? `${WARN_ICON} <b>Chưa có kênh báo kết quả</b> - ${esc(nt.error || "bot Telegram chưa sẵn sàng")}.
               Việc vẫn chạy đúng giờ nhưng kết quả sẽ không gửi được cho ai.
               <a href="#" data-settings-go="channels" style="color:var(--link-ink)">Đấu Telegram ở trang Kênh</a>`
            : `${WARN_ICON} <b>Kênh báo đang lỗi</b> - ${esc(nt.warn)}.
               Việc vẫn chạy nhưng tin có thể không tới.
               <a href="#" data-settings-go="channels" style="color:var(--link-ink)">Xem trang Kênh</a>`;
          const go = nw.querySelector("[data-settings-go]");
          if (go) go.onclick = (ev) => { ev.preventDefault(); navigateTo("channels"); };
        }
      }
      allLoops = [];
      const groups = (d.brains || []).slice().sort((a, b) => {
        const ac = isCurrentBrain(a) ? 0 : 1, bc = isCurrentBrain(b) ? 0 : 1;
        return ac - bc || String(a.name).localeCompare(String(b.name));
      });
      box.innerHTML = "";
      let anyItem = false;
      groups.forEach(g => {
        const loops = g.loops || [], rems = g.reminders || [];
        const cur = isCurrentBrain(g);
        if (!loops.length && !rems.length && !cur) return;   // brain rỗng không phải brain đang xem → ẩn
        if (loops.length || rems.length) anyItem = true;
        // Mỗi brain gói vào 1 wrapper .lp-group để ô tìm kiếm ẩn/hiện cả nhóm gọn gàng.
        const group = document.createElement("div");
        group.className = "lp-group";
        const head = document.createElement("div");
        head.style.cssText = "display:flex;align-items:center;gap:8px;margin:18px 0 8px;font-size:15px;color:var(--text);font-weight:600;border-bottom:1px solid var(--hairline);padding-bottom:6px";
        head.innerHTML = `<span>${ic("brain")} ${esc(g.name)}</span>`
          + (cur ? `<span style="font-size:11px;color:var(--green);font-weight:500">đang xem</span>` : "")
          + (g.is_default ? `<span style="font-size:11px;color:var(--text3);font-weight:400">mặc định</span>` : "");
        group.appendChild(head);
        if (!loops.length && !rems.length) {
          const e2 = document.createElement("div");
          e2.className = "empty"; e2.style.margin = "0 0 10px";
          e2.dataset.lp = "empty";
          e2.innerHTML = `Chưa có việc nào ở brain này. Bấm <b>+ Thêm việc</b>, hoặc nói với Javis trong chat.`;
          group.appendChild(e2);
        }
        loops.forEach(lp => { allLoops.push(lp); group.appendChild(loopCard(lp)); });
        if (rems.length) {
          const rh = document.createElement("div");
          rh.style.cssText = "font-size:13px;color:var(--text3);margin:10px 0 6px";
          rh.dataset.lp = "remhead";
          rh.textContent = "Nhắc hẹn đang chờ";
          group.appendChild(rh);
          rems.forEach(r => group.appendChild(reminderCard(r)));
        }
        box.appendChild(group);
      });
      if (!anyItem) {
        box.innerHTML = `<div class="empty">Chưa có việc định kỳ hay nhắc hẹn nào. Bấm <b>+ Thêm việc</b>, hoặc nói với Javis trong chat (vd "tạo loop mỗi 2 tiếng đọc 1 source rồi đề xuất").</div>`;
      }
      applyLpSearch();   // giữ nguyên bộ lọc tìm kiếm sau mỗi lần render lại danh sách
      // Bộ lọc nhật ký: mọi loop mọi brain (value = index vào allLoops → biết cả brain lẫn slug).
      const sel = el.querySelector("#lpLogFilter");
      const cur = sel.value;
      sel.innerHTML = `<option value="">Nhật ký brain đang xem</option>` +
        allLoops.map((lp, i) => `<option value="${i}" ${String(i) === cur ? "selected" : ""}>${esc(lp.name)} · ${esc(lp.brain_name)}</option>`).join("");
      clearTimeout(pollTimer);
      if (d.running) pollTimer = setTimeout(loadAll, 5000);   // đang có vòng chạy → tự refresh
    }
    // Nhật ký gần đây: tải 1 lần (mới nhất trước), rồi phân trang phía client 10 mục/trang - đỡ
    // đổ cả trăm dòng DOM cùng lúc, có nút Trước/Sau để lật xem tin cũ hơn.
    let logEntries = [];
    const LOG_PER_PAGE = 10;
    async function loadLog() {
      if (myGen !== _renderGen) return;
      const v = el.querySelector("#lpLogFilter").value;
      let brainQ = fbrain(), slugQ = "";
      if (v !== "") { const lp = allLoops[+v]; if (lp) { brainQ = lp.brain_path; slugQ = lp.slug; } }
      let d = { entries: [] };
      try { d = await (await fetch(`/loops/log?brain=${encodeURIComponent(brainQ)}&slug=${encodeURIComponent(slugQ)}&limit=200`)).json(); } catch (e) { }
      if (myGen !== _renderGen) return;
      logEntries = d.entries || [];
      renderLog();
    }
    function renderLog() {
      pager(el.querySelector("#lpLog"), logEntries, LOG_PER_PAGE,
            (rows) => rows.map(e => `<div class="le">${esc(e)}</div>`).join(""),
            `<div class="dim" style="color:var(--text3)">Chưa có nhật ký.</div>`);
    }
    el.querySelector("#lpLogFilter").onchange = loadLog;
    { const s = el.querySelector("#lpSearch"); if (s) s.oninput = applyLpSearch; }
    ensureBrains();   // nạp sẵn danh sách brain cho ô chọn (không chờ /viec/all vốn nặng)
    loadAll(); loadLog();
  }

  // ============================================
  // Trang Tự học (rewire Memory/Wiki/Skill - an toàn, undo được)
  // ============================================
  async function renderLearn(el) {
    _injectExtraCss();
    el.innerHTML = `<div class="cview-section"><div class="empty">Đang tải...</div></div>`;
    let cfg = {};
    try { cfg = await (await fetch("/learn/config")).json(); } catch (e) {}
    const caps = cfg.capabilities || {};
    const MODES = [
      ["dry-run", "Chạy thử", "Chỉ ghi nhật ký 'sẽ học gì' - KHÔNG đụng file. An toàn nhất."],
      ["suggest", "Đề xuất", "Như chạy thử, để bạn xem trước khi cho ghi."],
      ["auto", "Tự ghi", "Ghi thẳng vào Memory/Wiki - git-commit + undo được."],
    ];
    const modeChips = MODES.map(([v, l]) => `<button class="si-chip ${cfg.mode === v ? "sel" : ""}" data-mode="${v}">${l}</button>`).join("");
    const modeDesc = (MODES.find(m => m[0] === cfg.mode) || MODES[0])[2];
    const capRow = [["memory", "Ký ức (Memory)"], ["wiki", "Tri thức (Wiki)"], ["skill", "Kỹ năng (Skill)"], ["task", "Việc (Kanban)"]]
      .map(([k, l]) => `<button class="si-chip ${caps[k] ? "sel" : ""}" data-cap="${k}">${caps[k] ? "● " : "○ "}${l}</button>`).join("");
    const gitWarn = cfg.git_available ? "" : `<div class="dim" style="color:var(--text3);font-size:13px;margin-top:6px">ℹ Máy chưa có <code>git</code>: Tự học VẪN chạy bình thường, chỉ là chưa có hoàn tác 1-chạm/backup lên GitHub. Cài git để bật undo + sao lưu brain.</div>`;

    el.innerHTML = `<div class="cview-section">
      <p style="color:var(--text3);font-size:15px;max-width:660px;margin:0 0 14px">Sau mỗi hội thoại, Javis tự rút <b>ký ức</b>, đúc <b>tri thức Wiki</b>, <b>kỹ năng</b> và <b>việc</b> - qua tiến trình học <b>chỉ-đọc, cô lập</b> (0 MCP, không xoá). Người ghi file là code tin cậy. Mặc định <b>bật sẵn + tự ghi</b>; nếu brain có git thì mỗi lần học còn được <b>git-commit để hoàn tác 1 chạm</b>.</p>
      <div class="si-grid">
        <div class="si-field"><label>Bật tự học</label>
          <button class="si-chip ${cfg.enabled ? "sel" : ""}" id="lnEnabled">${cfg.enabled ? "● Đang bật" : "○ Đang tắt"}</button>
          <div class="dim" id="lnEnableNote" style="font-size:13px;margin-top:6px;color:var(--text3)">Học chạy được ngay cả khi chưa có git. Có git thì thêm undo + sao lưu.</div></div>
        <div class="si-field"><label>Chế độ ghi</label><div class="si-row" id="lnModes">${modeChips}</div>
          <div class="dim" id="lnModeDesc" style="font-size:14px;margin-top:6px;color:var(--text3)">${esc(modeDesc)}</div>${gitWarn}</div>
        <div class="si-field"><label>Học cái gì</label><div class="si-row" id="lnCaps">${capRow}</div>
          <div class="dim" style="font-size:13px;margin-top:6px;color:var(--text3)">Wiki/Skill nên bật sau khi đã quen với Ký ức (lộ trình Phase 2/3). Việc = học xong đề xuất task nền vào bảng Việc (Kanban) - chỉ tạo thật ở chế độ Tự ghi, và task luôn chờ bạn duyệt.</div></div>
        <div class="si-field"><label>Curator (bảo trì định kỳ)</label>
          <button class="si-chip ${(cfg.curator||{}).enabled ? "sel" : ""}" id="lnCurator">${(cfg.curator||{}).enabled ? "● Bật" : "○ Tắt"}</button>
          <div class="dim" style="font-size:13px;margin-top:6px;color:var(--text3)">Dọn index, LINT Wiki (chỉ đề xuất), nén MEMORY.md. Không xoá.</div></div>
        <div class="si-actions">
          <button class="s-btn" id="lnSave">${SAVE_ICON} Lưu cấu hình</button>
          <button class="s-btn-ghost" id="lnRun">▶ Học ngay</button>
          <button class="s-btn-ghost" id="lnCuratorRun">${ic("brush-cleaning")} Curator ngay</button>
          <button class="s-btn-ghost" id="lnStop">■ Dừng</button>
          <button class="s-btn-ghost" id="lnUndo" style="color:var(--warn-ink)">↶ Hoàn tác lần học gần nhất</button>
        </div>
      </div>
      <div class="si-status" id="lnMetrics"></div>

      <div class="si-log" id="lnBackupBox">
        <h3 style="font-size:15px;color:var(--text)">⇅ Đồng bộ brain với GitHub (2 chiều)</h3>
        <p style="color:var(--text3);font-size:14px;max-width:680px;margin:2px 0 10px">Đồng bộ <b>TẤT CẢ brain trong thư mục brains</b> (mọi bộ não, ghi chú, Wiki, ký ức) với 1 repo GitHub <b>riêng tư</b>: vừa đẩy thay đổi của máy này lên, vừa kéo thay đổi từ máy khác về (dùng chung cho máy nhà + VPS, các máy tự khớp nhau). Sửa trùng 1 file ở 2 nơi thì bản mới hơn thắng, bản kia được giữ thành file <code>.conflict-*</code> ngay cạnh. Máy mới cấu hình repo rồi bấm đồng bộ là khôi phục được toàn bộ. Hướng dẫn: <a href="https://github.com/blogminhquy/javis-os/blob/main/docs/18-sao-luu-github.md" target="_blank" style="color:var(--link-ink)">docs/18-sao-luu-github.md</a>.</p>
        <ol style="color:var(--text3);font-size:13.5px;line-height:1.7;max-width:680px;margin:0 0 12px;padding-left:20px">
          <li>Tạo repo GitHub <b>Private</b> (trống, KHÔNG thêm README) - vd <code>javis-brain-backup</code>.</li>
          <li>Tạo token: GitHub → Settings → Developer settings → <b>Fine-grained tokens</b> → chọn đúng repo đó → quyền <b>Contents: Read and write</b> → tạo và copy token (dạng <code>github_pat_...</code>).</li>
          <li>Dán URL repo + token vào đây, bấm <b>Kiểm tra</b>, rồi <b>Đồng bộ ngay</b>. Bật tự động để định kỳ tự khớp giữa các máy.</li>
        </ol>
        <div style="max-width:680px;margin:0 0 12px;padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--surface-1);color:var(--text3);font-size:13.5px;line-height:1.7">
          <b style="color:var(--text)">Chỉ đồng bộ THÔNG TIN, không đồng bộ media.</b>
          Lên GitHub là ghi chú, Wiki, ký ức, skill, cấu hình việc định kỳ, script - tức là file chữ
          (<code>.md .txt .html .csv .json .canvas .py</code>…). <b>Ảnh, video, âm thanh, PDF và các file nhị phân khác KHÔNG lên</b>;
          chúng vẫn nằm nguyên trên máy này và dùng bình thường, chỉ là không đi vào lịch sử git.
          <div style="margin-top:6px">Vì sao: git được thiết kế để <b>nhớ mãi mãi</b>. Một file video đã commit là nằm đó vĩnh viễn,
          xoá về sau cũng không đòi lại được dung lượng, và mỗi lần xuất lại clip là thêm nguyên một bản mới.
          Vài trăm MB media cộng thói quen render vài lượt sẽ đẩy repo lên nhiều GB trong ít tháng, máy mới clone về phải tải cả những bản đã bỏ từ lâu.
          Với chữ thì ngược lại: git nén và chỉ lưu phần chênh lệch, nên cả trăm lượt sửa vẫn rất nhẹ.</div>
          <div style="margin-top:6px">Cần bản sao media thì dùng thứ lưu theo <b>trạng thái hiện tại</b> (Google Drive, ổ cứng ngoài, NAS): xoá là mất thật và đòi lại được dung lượng thật. Hai thứ chia việc cho nhau chứ không thay nhau.</div>
        </div>
        <div class="si-grid">
          <div class="si-field"><label>URL repo (https)</label><input id="bkRepo" placeholder="Ví dụ: https://github.com/tai-khoan-cua-ban/javis-brain-backup"></div>
          <div class="si-field"><label>GitHub token (fine-grained, quyền Contents)</label><input id="bkToken" type="password" placeholder="Ví dụ: github_pat_..."></div>
          <div class="si-row" style="gap:14px;flex-wrap:wrap">
            <div class="si-field"><label>Nhánh</label><input id="bkBranch" value="main" style="max-width:120px"></div>
            <div class="si-field"><label>Tự đồng bộ mỗi (giờ)</label><input type="number" id="bkInterval" min="1" value="6" style="max-width:120px"></div>
            <div class="si-field"><label>Tự động</label><button class="si-chip" id="bkAuto">○ Tắt</button></div>
          </div>
          <div class="si-actions">
            <button class="s-btn-ghost" id="bkTest">${ic("plug")} Kiểm tra kết nối</button>
            <button class="s-btn" id="bkNow">⇅ Đồng bộ ngay</button>
            <button class="s-btn-ghost" id="bkSave">${SAVE_ICON} Lưu cấu hình</button>
          </div>
          <div class="dim" id="bkStatus" style="font-size:13px;color:var(--text3)"></div>
          <div class="dim" id="bkWarn" style="font-size:12px;color:var(--warn-ink);margin-top:2px">${WARN_ICON} Brain có thể chứa số liệu/thông tin cá nhân - CHỈ dùng repo Private. Token lưu nội bộ (không đẩy lên repo).</div>
        </div>
      </div>

      <div class="si-log"><h3 style="font-size:15px;color:var(--text)">Javis đã tự học gì (commit gần nhất)</h3><div id="lnReview">Đang tải...</div></div>
      <div class="si-log"><h3 style="font-size:15px;color:var(--text)">Nhật ký học</h3><div id="lnLog">Đang tải...</div></div>
    </div>`;

    let cur = { enabled: !!cfg.enabled, mode: cfg.mode || "dry-run",
                caps: { memory: !!caps.memory, wiki: !!caps.wiki, skill: !!caps.skill, task: !!caps.task },
                curator: !!(cfg.curator || {}).enabled };
    const modeDescEl = el.querySelector("#lnModeDesc");
    el.querySelectorAll("#lnModes .si-chip").forEach(c => c.onclick = () => {
      cur.mode = c.dataset.mode;
      el.querySelectorAll("#lnModes .si-chip").forEach(x => x.classList.toggle("sel", x === c));
      modeDescEl.textContent = (MODES.find(m => m[0] === cur.mode) || MODES[0])[2];
    });
    el.querySelectorAll("#lnCaps .si-chip").forEach(c => c.onclick = () => {
      const k = c.dataset.cap; cur.caps[k] = !cur.caps[k];
      c.classList.toggle("sel", cur.caps[k]);
      c.textContent = (cur.caps[k] ? "● " : "○ ") + c.textContent.slice(2);
    });
    const curBtn = el.querySelector("#lnCurator");
    curBtn.onclick = () => { cur.curator = !cur.curator; curBtn.classList.toggle("sel", cur.curator); curBtn.textContent = cur.curator ? "● Bật" : "○ Tắt"; };
    const enBtn = el.querySelector("#lnEnabled");
    enBtn.onclick = async () => {
      if (!cur.enabled) {
        enBtn.textContent = "Đang git-init...";
        let r = {}; try { r = await (await fetch("/learn/enable", { method: "POST", body: (()=>{const f=new FormData();f.append("brain",fbrain());return f;})() })).json(); } catch (e) {}
        cur.enabled = true; el.querySelector("#lnEnableNote").textContent = r.note || "Đã bật.";
      } else {
        cur.enabled = false;
        const f = new FormData(); f.append("enabled", "0"); f.append("brain", fbrain());
        await fetch("/learn/config", { method: "POST", body: f });
      }
      enBtn.classList.toggle("sel", cur.enabled); enBtn.textContent = cur.enabled ? "● Đang bật" : "○ Đang tắt";
    };

    async function save() {
      const f = new FormData();
      f.append("enabled", cur.enabled ? "1" : "0"); f.append("mode", cur.mode);
      f.append("cap_memory", cur.caps.memory ? "1" : "0");
      f.append("cap_wiki", cur.caps.wiki ? "1" : "0");
      f.append("cap_skill", cur.caps.skill ? "1" : "0");
      f.append("cap_task", cur.caps.task ? "1" : "0");
      f.append("curator_enabled", cur.curator ? "1" : "0");
      f.append("brain", fbrain());
      return (await fetch("/learn/config", { method: "POST", body: f })).json();
    }
    el.querySelector("#lnSave").onclick = async () => { const b = el.querySelector("#lnSave"); b.textContent = "Đang lưu..."; await save(); b.innerHTML = CHECK_ICON + " Đã lưu"; setTimeout(() => b.innerHTML = SAVE_ICON + " Lưu cấu hình", 1500); };
    const brainForm = () => { const f = new FormData(); f.append("brain", fbrain()); return f; };
    el.querySelector("#lnRun").onclick = async () => {
      const b = el.querySelector("#lnRun"); b.disabled = true; b.textContent = "Đang học...";
      await save(); await fetch("/learn/run-now", { method: "POST", body: brainForm() });
      setTimeout(() => { b.disabled = false; b.textContent = "▶ Học ngay"; loadAll(); }, 2500);
    };
    el.querySelector("#lnCuratorRun").onclick = async () => {
      const b = el.querySelector("#lnCuratorRun"); b.disabled = true; b.textContent = "Đang dọn...";
      await fetch("/learn/curator-now", { method: "POST", body: brainForm() });
      setTimeout(() => { b.disabled = false; b.innerHTML = ic("brush-cleaning") + " Curator ngay"; loadAll(); }, 2500);
    };
    el.querySelector("#lnStop").onclick = async () => { await fetch("/learn/stop", { method: "POST" }); };
    el.querySelector("#lnUndo").onclick = async () => {
      if (!confirm("Hoàn tác (git revert) lần học gần nhất?")) return;
      const b = el.querySelector("#lnUndo"); b.disabled = true; b.textContent = "Đang hoàn tác...";
      let r = {}; try { r = await (await fetch("/learn/undo", { method: "POST", body: brainForm() })).json(); } catch (e) { r = { error: e.message }; }
      b.disabled = false; b.textContent = "↶ Hoàn tác lần học gần nhất";
      alert(r.ok ? ("Đã hoàn tác: " + (r.subject || r.reverted)) : ("Không hoàn tác được: " + (r.error || "?")));
      loadAll();
    };

    async function loadMetrics() {
      let m = {}; try { m = await (await fetch(`/learn/metrics?brain=${encodeURIComponent(fbrain())}`)).json(); } catch (e) { }
      el.querySelector("#lnMetrics").innerHTML =
        `<b>Chỉ số</b> · Ký ức: <b>${m.facts ?? "?"}</b> · Wiki: <b>${m.wiki ?? "?"}</b> · MEMORY.md: ${(m.memory_bytes||0)}B` +
        ` · Fork hôm nay: ${m.fork_today ?? 0} · Token ước tính: ${m.token_today ?? 0} · Commit học: ${m.learn_commits ?? 0}`;
    }
    // Hai khung dưới đây trước chỉ hiện 10 dòng nhật ký và 12 commit rồi hết - muốn xem xa hơn
    // là không có đường nào. Nay tải sâu hơn hẳn rồi lật trang tại chỗ bằng pager() dùng chung.
    async function loadReview() {
      let d = { commits: [] }; try { d = await (await fetch(`/learn/review?brain=${encodeURIComponent(fbrain())}&limit=60`)).json(); } catch (e) { }
      const box = el.querySelector("#lnReview");
      if (!d.git_repo) { box.innerHTML = `<div class="dim" style="color:var(--warn-ink)">Brain chưa phải git repo - bật Tự học để git-init (mới xem/undo được commit).</div>`; return; }
      pager(box, d.commits || [], 6, (rows) => rows.map(c => {
        const when = c.ts ? new Date(c.ts * 1000).toLocaleString() : "";
        const files = (c.files || []).slice(0, 6).map(f => `<code style="font-size:11px">${esc(f)}</code>`).join(" ");
        return `<div class="le"><b>${esc(c.subject)}</b> <span class="dim" style="color:var(--text3)">${esc(c.hash)} · ${esc(when)}</span><br>${files}</div>`;
      }).join(""), `<div class="dim" style="color:var(--text3)">Chưa có commit học nào.</div>`);
    }
    async function loadLog() {
      let d = { entries: [] }; try { d = await (await fetch(`/learn/log?brain=${encodeURIComponent(fbrain())}&limit=200`)).json(); } catch (e) { }
      pager(el.querySelector("#lnLog"), d.entries || [], 10,
            (rows) => rows.map(e => `<div class="le">${esc(e)}</div>`).join(""),
            `<div class="dim" style="color:var(--text3)">Chưa có nhật ký học.</div>`);
    }
    // ── Backup GitHub ──
    let bkAutoOn = false;
    const bkAutoBtn = el.querySelector("#bkAuto");
    bkAutoBtn.onclick = () => { bkAutoOn = !bkAutoOn; bkAutoBtn.classList.toggle("sel", bkAutoOn); bkAutoBtn.textContent = bkAutoOn ? "● Bật" : "○ Tắt"; };
    async function bkSaveCfg() {
      const f = new FormData();
      f.append("repo_url", el.querySelector("#bkRepo").value.trim());
      const tk = el.querySelector("#bkToken").value.trim();
      if (tk && !tk.startsWith("••••")) f.append("token", tk);   // chỉ gửi token mới, không gửi chuỗi che
      f.append("branch", el.querySelector("#bkBranch").value.trim() || "main");
      f.append("interval_hours", el.querySelector("#bkInterval").value || "6");
      f.append("enabled", bkAutoOn ? "1" : "0");
      return (await fetch("/backup/config", { method: "POST", body: f })).json();
    }
    el.querySelector("#bkSave").onclick = async () => { const b = el.querySelector("#bkSave"); b.textContent = "Đang lưu..."; await bkSaveCfg(); b.innerHTML = CHECK_ICON + " Đã lưu"; setTimeout(() => b.innerHTML = SAVE_ICON + " Lưu cấu hình", 1500); loadBackup(); };
    el.querySelector("#bkTest").onclick = async () => {
      const b = el.querySelector("#bkTest"); b.disabled = true; b.textContent = "Đang kiểm tra..."; await bkSaveCfg();
      let r = {}; try { r = await (await fetch("/backup/test", { method: "POST" })).json(); } catch (e) { r = { error: e.message }; }
      b.disabled = false; b.innerHTML = ic("plug") + " Kiểm tra kết nối";
      el.querySelector("#bkStatus").innerHTML = r.ok ? `<span style="color:var(--green)">${CHECK_ICON} Kết nối OK - token + repo hợp lệ.</span>` : `<span style="color:var(--red)">${ic("circle-x")} ${esc(r.error || "không kết nối được")}</span>`;
    };
    el.querySelector("#bkNow").onclick = async () => {
      const b = el.querySelector("#bkNow"); b.disabled = true; b.textContent = "Đang đồng bộ 2 chiều..."; await bkSaveCfg();
      let r = {}; try { r = await (await fetch("/backup/now", { method: "POST", body: brainForm() })).json(); } catch (e) { r = { error: e.message }; }
      b.disabled = false; b.textContent = "⇅ Đồng bộ ngay";
      if (r.ok) {
        const bits = [];
        if (r.applied) bits.push(`nhận về ${r.applied} file`);
        if (r.deleted) bits.push(`xoá ${r.deleted} file (máy khác đã xoá)`);
        if (r.pushed) bits.push("đã đẩy lên GitHub");
        if (r.restored) bits.push("khôi phục từ backup");
        const cf = (r.conflicts || []).length
          ? ` · <span style="color:var(--warn-ink)">${WARN_ICON} ${r.conflicts.length} file sửa trùng 2 nơi - bản mới hơn thắng, bản kia lưu thành .conflict-* (xem: ${esc(r.conflicts.slice(0, 3).map(c => c.path).join(", "))}${r.conflicts.length > 3 ? "..." : ""})</span>` : "";
        // Media bị bỏ qua phải NÓI RA. Im lặng thì có ngày người dùng tưởng ảnh của mình
        // cũng đã được sao lưu, tới lúc mất máy mới biết là không.
        const mq = r.media_bo_qua
          ? `<div style="color:var(--text3);font-size:12.5px;margin-top:3px">Bỏ qua ${r.media_bo_qua} file media${r.media_bytes ? " (" + _humanSize(r.media_bytes) + ")" : ""} - git chỉ giữ chữ. Chúng vẫn nằm nguyên trên máy này; muốn có bản sao thì dùng Drive hoặc ổ ngoài.</div>` : "";
        el.querySelector("#bkStatus").innerHTML = `<span style="color:var(--green)">${CHECK_ICON} Đồng bộ xong${bits.length ? " - " + bits.join(", ") : " - hai bên đã khớp nhau"}.</span>${cf}${mq}`;
      } else {
        el.querySelector("#bkStatus").innerHTML = `<span style="color:var(--red)">${ic("circle-x")} ${esc(r.error || "lỗi")}</span>`;
      }
    };
    async function loadBackup() {
      let s = {}; try { s = await (await fetch(`/backup/status?brain=${encodeURIComponent(fbrain())}`)).json(); } catch (e) { return; }
      el.querySelector("#bkRepo").value = s.repo_url || "";
      el.querySelector("#bkBranch").value = s.branch || "main";
      el.querySelector("#bkInterval").value = s.interval_hours || 6;
      if (s.token_set && !el.querySelector("#bkToken").value) el.querySelector("#bkToken").placeholder = "Đã lưu, để trống nếu giữ nguyên";
      bkAutoOn = !!s.enabled; bkAutoBtn.classList.toggle("sel", bkAutoOn); bkAutoBtn.textContent = bkAutoOn ? "● Bật" : "○ Tắt";
      const when = s.last_backup ? new Date(s.last_backup * 1000).toLocaleString() : "chưa đồng bộ";
      const gitNote = s.has_git ? "" : " · " + WARN_ICON + " máy chưa cài git (cần git để đồng bộ)";
      const brainsNote = s.brains_count != null ? ` · ${s.brains_count} brain trong thư mục brains` : "";
      el.querySelector("#bkStatus").innerHTML = `Lần cuối: ${esc(when)}${s.last_status ? " · " + esc(s.last_status) : ""}${brainsNote}${gitNote}`;
    }

    function loadAll() { loadMetrics(); loadReview(); loadLog(); loadBackup(); }
    loadAll();
  }

  // ============================================
  // Trang Việc - operations console cho hàng đợi AI tự vận hành
  // ============================================
  // Ưu tiên việc: tên icon + lớp màu. Cao thì mũi đôi màu đỏ để nhảy ra khỏi
  // danh sách, thấp thì mờ đi cho khỏi tranh chú ý.
  const _PRIO = { 1: ["chevrons-up", "ic-err"], 2: ["chevron-up", "ic-warn"], 3: ["chevron-down", "ic-dim"] };
  function _prioIcon(p) {
    const spec = _PRIO[p];
    return spec ? ic(spec[0], { cls: spec[1] }) : "";
  }
  const _KSTATUS = {
    triage: "AI đang đặc tả", todo: "Chờ phụ thuộc", ready: "Trong hàng đợi",
    running: "Đang chạy", review: "Cần duyệt ngoại lệ", blocked: "Cần xử lý",
    done: "Hoàn thành", cancelled: "Đã huỷ",
  };
  async function renderKanban(el) {
    _injectExtraCss();
    if (window._javisKanbanDrawerCleanup) window._javisKanbanDrawerCleanup();
    el.innerHTML = `<div class="cview-section"><div class="empty">Đang tải...</div></div>`;
    let wfs = [];
    try { wfs = (await (await fetch(`/workflows?brain=${encodeURIComponent(fbrain())}`)).json()).workflows || []; } catch (e) {}
    const routeOpts = `<option value="auto">AI tự chọn worker</option>` +
      wfs.map(w => `<option value="wf:${esc(w.slug)}">Workflow: ${esc(w.name || w.slug)}</option>`).join("");

    el.innerHTML = `<div class="cview-section">
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap">
        <div>
          <div style="font-size:16px;color:var(--text);font-weight:650"><span class="kn-dot off" id="knLiveDot"></span><span id="knLiveText">Dispatcher</span></div>
          <p style="color:var(--text3);font-size:13px;max-width:680px;margin:6px 0 0">AI tự đặc tả goal, chọn capability, claim task và chạy worker nền. Màn hình này dùng để quan sát và xử lý ngoại lệ.</p>
        </div>
        <div class="si-actions" style="margin:0">
          <button class="s-btn" id="knAdd">+ Giao goal</button>
          <button class="s-btn-ghost" id="knNudge">Chạy nhịp ngay</button>
          <button class="s-btn-ghost" id="knRefresh">↻</button>
          <button class="s-btn-ghost" id="knStop" style="color:var(--warn-ink)">Tạm dừng AI</button>
        </div>
      </div>
      <div class="kn-health">
        <div class="kn-kpi"><span>Worker đang chạy</span><b id="knKpiActive">0</b></div>
        <div class="kn-kpi"><span>Đang chờ</span><b id="knKpiQueue">0</b></div>
        <div class="kn-kpi"><span>Cần bạn xử lý</span><b id="knKpiAttention">0</b></div>
        <div class="kn-kpi"><span>Hoàn thành 24h</span><b id="knKpiDone">0</b></div>
      </div>
      <div class="si-field" style="margin-bottom:14px"><label>Chế độ dispatcher</label><div class="si-row" id="knOrch"></div></div>
      <div id="knForm" style="display:none;margin-bottom:14px;padding:14px;border:1px solid var(--hairline);border-radius:10px;background:var(--surface-1)">
        <div class="si-field"><label>Goal</label><input id="knTitle" placeholder="Ví dụ: Phân tích sản phẩm bán chạy tuần này và soạn 3 bài đăng"></div>
        <div class="si-field"><label>Ngữ cảnh và đầu ra mong muốn</label><textarea id="knIntent" placeholder="Có thể viết tự nhiên. AI specifier sẽ chuẩn hoá, chọn worker và điều kiện hoàn thành."></textarea></div>
        <div class="si-row" style="gap:14px;flex-wrap:wrap">
          <div class="si-field" style="flex:1;min-width:220px"><label>Route</label><select id="knRoute" class="loop-sel">${routeOpts}</select></div>
          <div class="si-field"><label>Ưu tiên</label><select id="knPrio" class="loop-sel"><option value="1">Cao</option><option value="2" selected>Vừa</option><option value="3">Thấp</option></select></div>
          <div class="si-field"><label>Ngoại lệ</label><label class="auto-learn" style="margin-top:8px"><input type="checkbox" id="knApprove"><span>Yêu cầu duyệt kết quả</span></label></div>
        </div>
        <div class="si-actions"><button class="s-btn" id="knSave">Giao cho AI</button><button class="s-btn-ghost" id="knCancel">Huỷ</button></div>
      </div>
      <div class="kn-layout" id="knOps">
        <div style="display:flex;flex-direction:column;gap:14px">
          <section class="kn-panel"><div class="kn-panel-head"><b>Đang hoạt động</b><span id="knActiveCount">0 worker</span></div><div class="kn-list" id="knActive"></div></section>
          <section class="kn-panel"><div class="kn-panel-head"><b>Hàng đợi AI</b><span id="knQueueCount">0 task</span></div><div class="kn-list" id="knQueue"></div></section>
        </div>
        <div style="display:flex;flex-direction:column;gap:14px">
          <section class="kn-panel"><div class="kn-panel-head"><b style="color:var(--accent-ink)">Cần bạn xử lý</b><span id="knAttentionCount">0 ngoại lệ</span></div><div class="kn-list" id="knAttention"></div></section>
          <section class="kn-panel"><div class="kn-panel-head"><b>Lịch sử gần đây</b><span>24 giờ và mới nhất</span></div><div class="kn-list" id="knHistory"></div></section>
        </div>
      </div>
    </div>`;

    // Portal lên document.body để drawer không bị cắt bởi vùng content có
    // transform/overflow. Đây cũng bảo đảm nút đóng luôn nằm trong viewport.
    const drawerPortal = document.createElement("div");
    drawerPortal.id = "knDrawerPortal";
    drawerPortal.innerHTML = `
      <div class="kn-drawer-backdrop" id="knDrawerBackdrop"></div>
      <aside class="kn-drawer" id="knDrawer" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="knDrawerTitle">
        <div class="kn-drawer-head">
          <b id="knDrawerTitle">Chi tiết task</b>
          <button id="knDrawerClose" type="button" aria-label="Đóng chi tiết" title="Đóng (Esc)">×</button>
        </div>
        <div class="kn-drawer-body" id="knDrawerBody">Đang tải...</div>
      </aside>`;
    document.body.appendChild(drawerPortal);
    const drawer = drawerPortal.querySelector("#knDrawer");
    const drawerBackdrop = drawerPortal.querySelector("#knDrawerBackdrop");
    const drawerBody = drawerPortal.querySelector("#knDrawerBody");
    const drawerTitle = drawerPortal.querySelector("#knDrawerTitle");
    const closeDrawer = () => {
      drawer.classList.remove("open");
      drawerBackdrop.classList.remove("open");
      drawer.setAttribute("aria-hidden", "true");
    };
    const openDrawer = () => {
      drawer.classList.add("open");
      drawerBackdrop.classList.add("open");
      drawer.setAttribute("aria-hidden", "false");
    };
    const onDrawerKeydown = (event) => {
      if (event.key === "Escape" && drawer.classList.contains("open")) closeDrawer();
    };
    document.addEventListener("keydown", onDrawerKeydown);
    drawerPortal.querySelector("#knDrawerClose").onclick = closeDrawer;
    drawerBackdrop.onclick = closeDrawer;
    const cleanupDrawer = () => {
      document.removeEventListener("keydown", onDrawerKeydown);
      drawerPortal.remove();
      if (window._javisKanbanDrawerCleanup === cleanupDrawer) {
        delete window._javisKanbanDrawerCleanup;
      }
    };
    window._javisKanbanDrawerCleanup = cleanupDrawer;

    const bf = () => { const f = new FormData(); f.append("brain", fbrain()); return f; };
    const post = async (url, extra) => { const f = bf(); for (const k in (extra || {})) f.append(k, extra[k]); return (await fetch(url, { method: "POST", body: f })).json(); };

    el.querySelector("#knAdd").onclick = () => { const b = el.querySelector("#knForm"); b.style.display = b.style.display === "none" ? "block" : "none"; };
    el.querySelector("#knCancel").onclick = () => { el.querySelector("#knForm").style.display = "none"; };
    el.querySelector("#knRefresh").onclick = () => load();
    el.querySelector("#knStop").onclick = async () => { await post("/kanban/stop"); load(); };
    el.querySelector("#knNudge").onclick = async () => { const b = el.querySelector("#knNudge"); b.disabled = true; await post("/kanban/nudge"); b.disabled = false; load(); };
    el.querySelector("#knSave").onclick = async () => {
      const title = el.querySelector("#knTitle").value.trim();
      if (!title) { alert("Nhập tiêu đề"); return; }
      await post("/kanban/task", {
        title, intent: el.querySelector("#knIntent").value.trim() || title,
        route: el.querySelector("#knRoute").value, priority: el.querySelector("#knPrio").value,
        needs_approval: el.querySelector("#knApprove").checked ? "1" : "0",
      });
      el.querySelector("#knTitle").value = ""; el.querySelector("#knIntent").value = "";
      el.querySelector("#knForm").style.display = "none"; load();
    };

    function ago(ts) {
      const sec = Math.max(0, Date.now() / 1000 - Number(ts || 0));
      if (sec < 60) return "vừa xong";
      if (sec < 3600) return `${Math.floor(sec / 60)} phút`;
      if (sec < 86400) return `${Math.floor(sec / 3600)} giờ`;
      return `${Math.floor(sec / 86400)} ngày`;
    }

    function taskActions(t) {
      const acts = [];
      if (t.status === "review") acts.push(`<button data-act="done" data-id="${esc(t.id)}">${CHECK_ICON} Duyệt ngoại lệ</button>`);
      if (t.status === "blocked" || t.status === "review") acts.push(`<button data-act="retry" data-id="${esc(t.id)}">↻ Thử lại</button>`);
      if (t.status === "running") acts.push(`<button data-act="cancel" data-id="${esc(t.id)}">Dừng task</button>`);
      if (t.status !== "running") acts.push(`<button class="danger" data-act="archive" data-id="${esc(t.id)}">Xóa khỏi bảng</button>`);
      return acts;
    }

    function taskHtml(t, area) {
      const acts = taskActions(t);
      const reason = t.block_reason ? `<div class="kn-task-result" style="color:var(--red)">${esc(t.block_reason)}</div>` : "";
      const result = !reason && t.result ? `<div class="kn-task-result">${esc(t.result.slice(0, 240))}</div>` : "";
      return `<div class="kn-task" data-task="${esc(t.id)}">
        <div class="kn-task-top"><div class="kn-task-title">${_prioIcon(t.priority)} ${esc(t.title)}</div><span class="kn-pill">${esc(_KSTATUS[t.status] || t.status)}</span></div>
        <div class="kn-task-meta"><span>${esc(t.capability || "auto")}</span><span>attempt ${Number(t.attempts || 0)}/${Number(t.max_attempts || 3)}</span><span>${ago(t.updated_at)}</span></div>
        ${reason}${result}
        ${acts.length ? `<div class="kn-actions">${acts.join("")}</div>` : ""}
      </div>`;
    }

    function fillList(node, items, area) {
      node.innerHTML = items.length ? items.map(t => taskHtml(t, area)).join("") : `<div class="kn-empty">${area === "attention" ? "Không có ngoại lệ. AI đang tự vận hành bình thường." : "Chưa có task."}</div>`;
    }

    async function doTaskAction(id, act) {
      if (act === "archive" && !confirm("Xóa task này khỏi bảng? Task sẽ được lưu trữ để không mất lịch sử.")) return false;
      let result;
      if (act === "retry") result = await post("/kanban/task/retry", { id });
      else if (act === "cancel") result = await post("/kanban/task/cancel", { id });
      else if (act === "archive") result = await post("/kanban/task/delete", { id });
      else result = await post("/kanban/task/move", { id, status: act });
      if (!result || !result.ok) {
        alert((result && result.error) || "Không thể cập nhật task");
        return false;
      }
      closeDrawer();
      await load();
      return true;
    }

    function bindActionButtons(scope) {
      scope.querySelectorAll(".kn-actions button[data-act]").forEach(b => b.onclick = async ev => {
        ev.stopPropagation();
        b.disabled = true;
        await doTaskAction(b.dataset.id, b.dataset.act);
        b.disabled = false;
      });
    }

    function bindActions() {
      el.querySelectorAll(".kn-task[data-task]").forEach(row => row.onclick = () => showTask(row.dataset.task));
      bindActionButtons(el);
    }

    async function showTask(id) {
      openDrawer();
      drawerBody.innerHTML = "Đang tải...";
      let d = {}; try { d = await (await fetch(`/kanban/task/show?brain=${encodeURIComponent(fbrain())}&id=${encodeURIComponent(id)}`)).json(); } catch (e) {}
      if (!d.ok) { drawerBody.innerHTML = `<span style="color:var(--red)">${esc(d.error || "Không tải được task")}</span>`; return; }
      const t = d.task || {}, events = d.events || [], runs = d.runs || [];
      const acts = taskActions(t);
      drawerTitle.textContent = t.title || "Chi tiết task";
      drawerBody.innerHTML = `
        <div style="color:var(--text);white-space:pre-wrap">${esc(t.intent || "")}</div>
        <div class="kn-task-meta" style="margin-top:10px"><span>${esc(_KSTATUS[t.status] || t.status)}</span><span>${esc(t.capability || "auto")}</span><span>mode ${esc(t.execution_mode || "auto")}</span><span>ưu tiên ${Number(t.priority || 2)}</span></div>
        ${acts.length ? `<div class="kn-actions" style="margin-top:14px">${acts.join("")}</div>` : ""}
        ${t.block_reason ? `<div class="kn-detail-block"><h4>Lý do bị chặn</h4><div style="color:var(--red)">${esc(t.block_reason)}</div></div>` : ""}
        ${t.result ? `<div class="kn-detail-block"><h4>Kết quả</h4><div style="white-space:pre-wrap">${esc(t.result)}</div></div>` : ""}
        <div class="kn-detail-block"><h4>Lần chạy (${runs.length})</h4>${runs.length ? runs.map(r => `<div class="kn-event"><b>${esc(r.status)}</b> · ${new Date(Number(r.started_at || 0) * 1000).toLocaleString()}${r.error ? `<div style="color:var(--red)">${esc(r.error)}</div>` : ""}</div>`).join("") : `<div class="dim">Chưa chạy</div>`}</div>
        <div class="kn-detail-block"><h4>Nhật ký lifecycle</h4>${events.length ? events.map(v => `<div class="kn-event"><b>${esc(v.event_type)}</b> · ${new Date(Number(v.created_at || 0) * 1000).toLocaleString()}<div>${esc(v.message || "")}</div></div>`).join("") : `<div class="dim">Chưa có sự kiện</div>`}</div>`;
      bindActionButtons(drawerBody);
    }

    async function load() {
      if (!el.isConnected || !el.querySelector("#knOps")) return;
      let d = { operations: {}, orchestration: "off", counts: {}, dispatcher: {} };
      try { d = await (await fetch(`/kanban?brain=${encodeURIComponent(fbrain())}`)).json(); } catch (e) {}
      const ops = d.operations || {}, active = ops.active || [], attention = ops.attention || [], queue = ops.queue || [], history = ops.history || [];
      const live = !!(d.dispatcher && d.dispatcher.running), dot = el.querySelector("#knLiveDot");
      dot.classList.toggle("live", live); dot.classList.toggle("off", !live);
      el.querySelector("#knLiveText").textContent = live ? `Dispatcher đang chạy · tối đa ${Number(d.dispatcher.max_workers || 0)} worker` : "Dispatcher chưa chạy";
      el.querySelector("#knKpiActive").textContent = Number(d.dispatcher.active_workers || active.length);
      el.querySelector("#knKpiQueue").textContent = queue.length;
      el.querySelector("#knKpiAttention").textContent = attention.length;
      el.querySelector("#knKpiDone").textContent = Number(d.completed_24h || 0);
      el.querySelector("#knActiveCount").textContent = `${active.length} worker`;
      el.querySelector("#knQueueCount").textContent = `${queue.length} task`;
      el.querySelector("#knAttentionCount").textContent = `${attention.length} ngoại lệ`;
      const orch = el.querySelector("#knOrch");
      orch.innerHTML = [["off", "Tắt"], ["manual", "Quan sát"], ["auto", "AI tự vận hành"]]
        .map(([v, l]) => `<button class="si-chip ${d.orchestration === v ? "sel" : ""}" data-orch="${v}">${l}</button>`).join("");
      orch.querySelectorAll(".si-chip").forEach(c => c.onclick = async () => { await post("/kanban/orchestration", { mode: c.dataset.orch }); load(); });
      fillList(el.querySelector("#knActive"), active, "active");
      fillList(el.querySelector("#knQueue"), queue, "queue");
      fillList(el.querySelector("#knAttention"), attention, "attention");
      fillList(el.querySelector("#knHistory"), history.slice(0, 20), "history");
      bindActions();
    }
    load();
    const poll = setInterval(() => {
      if (!el.isConnected || !el.querySelector("#knOps")) {
        clearInterval(poll);
        cleanupDrawer();
      }
      else load();
    }, 3000);
  }

  async function freshSettings() {
    // Timeout 6s: nếu /settings chậm/treo thì KHÔNG để panel kẹt "Đang tải..." mãi - dùng cache cũ
    // (hoặc {}) để vẫn hiện providers/cấu hình ngay, refresh lần sau.
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 6000);
      const r = await fetch("/settings", { signal: ctrl.signal });
      clearTimeout(t);
      _settings = await r.json();
    } catch (e) { /* giữ _settings cũ */ }
    return _settings || {};
  }

  // ---- Trang Tổng quan ----
  async function renderOverview(el) {
    el.innerHTML = `<div class="cview-placeholder"><div class="ph-ico">${ic("loader", { cls: "ic-xl ic-spin" })}</div><div>Đang tải...</div></div>`;
    const s = await freshSettings();
    const m = s.model || {};
    // Đọc từ model.main + model.providers (nguồn thật của trang Models), KHÔNG từ m.engine -
    // trường cũ đó chỉ biết "cli" với "openrouter" nên máy đang chạy Gemini/OpenAI vẫn bị
    // ghi là "Claude CLI". Mọi provider đều có MCP Javis, khác nhau ở chỗ chạy được lệnh máy.
    const _mainP = (m.providers || []).find(p => p.id === (m.main || {}).provider) || {};
    const eng = (_mainP.label || (m.main || {}).provider || "-")
      + (_mainP.kind === "api" ? " (MCP Javis)" : _mainP.kind ? " (MCP Javis + lệnh máy)" : "");
    const curModel = (m.main || {}).model || "mặc định";
    const tg = s.telegram || {};
    const dash = s.dashboard || {};
    const gOn = dash.graph_enabled !== false;
    el.innerHTML = `
      <div class="cview-section">
        <h3>Phiên bản</h3>
        <div class="gcard" style="max-width:640px">
          <div class="gcard-top"><span class="gcard-name">Javis OS</span><span class="gcard-tag" id="ovVerTag">…</span></div>
          <div class="gcard-meta" id="ovVerMeta">Đang kiểm tra bản mới…</div>
          <div id="ovVerChangelog" style="display:none;margin:8px 0;padding:8px 10px;border-left:3px solid var(--accent,var(--accent));background:rgba(120,140,160,.08);border-radius:6px;font-size:13px;line-height:1.6"></div>
          <div class="js-actions">
            <button class="gcard-btn ghost" id="ovVerCheck">Kiểm tra lại</button>
            <button class="gcard-btn" id="ovVerUpdate" style="display:none">${ic("upload-cloud")} Cập nhật ngay</button>
          </div>
          <div id="ovVerProgress" style="display:none;margin-top:10px"></div>
          <div class="gcard-meta" id="ovVerStatus"></div>
          <div id="ovVerRollback" style="display:none;margin-top:10px;padding:10px;border:1px solid var(--red);border-radius:8px;background:rgba(200,80,80,.08);font-size:13px;line-height:1.6"></div>
        </div>
      </div>
      <div class="cview-section">
        <h3>Hệ thống</h3>
        <div class="cgrid">
          <div class="gcard"><div class="gcard-top"><span class="gcard-name">Engine</span></div><div class="gcard-meta">${esc(eng)}</div></div>
          <div class="gcard"><div class="gcard-top"><span class="gcard-name">Model</span></div><div class="gcard-meta">${esc(curModel)}</div></div>
          <div class="gcard"><div class="gcard-top"><span class="gcard-name">Workspace</span></div><div class="gcard-meta">${esc(s.workspace_name || "Javis OS")}</div></div>
          <div class="gcard"><div class="gcard-top"><span class="gcard-name">Telegram</span></div><div class="gcard-meta">${tg.enabled ? "● Bật" : "○ Tắt"}${tg.chat_id ? " · " + esc(tg.chat_id) : ""}</div></div>
        </div>
      </div>
      <div class="cview-section">
        <h3>Hiệu năng</h3>
        <div class="cgrid">
          <div class="gcard">
            <div class="gcard-top"><span class="gcard-name">Đồ thị não</span><span class="gcard-tag">${gOn ? "bật" : "tắt"}</span></div>
            <div class="gcard-meta">Đồ thị canvas nhẹ, chạy ngay trên thiết bị. Có thể tắt hẳn để giảm tải thêm. ${isNarrow() ? "Màn hình hẹp đang tự ép lite-mode." : ""}</div>
            <div class="js-actions">
              <button class="gcard-btn ${gOn ? "ghost" : ""}" id="ovGraphToggle">${gOn ? "Tắt đồ thị" : "Bật đồ thị"}</button>
            </div>
          </div>
        </div>
      </div>
      <div class="cview-section" id="ovAutostartSec" style="display:none">
        <h3>Khởi động cùng máy</h3>
        <div class="cgrid">
          <div class="gcard">
            <div class="gcard-top"><span class="gcard-name">Tự bật Javis khi mở máy</span><span class="gcard-tag" id="ovAutoTag">…</span></div>
            <div class="gcard-meta" id="ovAutoMeta">Đang kiểm tra…</div>
            <button class="gcard-btn" id="ovAutoToggle" style="display:none"></button>
            <div class="gcard-meta" id="ovAutoStatus" style="margin-top:8px"></div>
          </div>
        </div>
      </div>
      <div class="cview-section">
        <h3>Cấu trúc brain</h3>
        <div class="cgrid">
          <div class="gcard">
            <div class="gcard-top"><span class="gcard-name">Chuẩn hóa thư mục</span></div>
            <div class="gcard-meta">Gom <code>agents/ workflows/ memory/ skills/</code> về dạng phẳng đồng nhất cho brain đang chọn. An toàn: chỉ di chuyển khi đích chưa có.</div>
            <button class="gcard-btn" id="ovMigrate">Chuẩn hóa brain đang chọn</button>
            <div class="gcard-meta" id="ovMigrateResult" style="margin-top:8px"></div>
          </div>
        </div>
      </div>`;
    // ---- Phiên bản + cập nhật trong UI ----
    const modeLbl = (j) => j.mode === "docker" ? "Docker / VPS"
      : j.mode === "windows" ? "Windows"
      : (j.platform === "mac" ? "macOS" : "Linux");
    const UPD_STEPS = [
      { key: "preparing", label: "Chuẩn bị" },
      { key: "pulling", label: "Tải code" },
      { key: "installing", label: "Cài thư viện" },
      { key: "restarting", label: "Khởi động lại" },
      { key: "health_check", label: "Kiểm tra sức khoẻ" },
      { key: "done", label: "Xong" },
    ];
    function updStepIndex(phase) {
      if (phase === "rolling_back") return 4;        // vẫn ở giai đoạn kiểm tra/khôi phục
      const i = UPD_STEPS.findIndex(s => s.key === phase);
      return i < 0 ? 0 : i;
    }
    function renderProgress(phase, extra) {
      const box = document.getElementById("ovVerProgress");
      if (!box) return;
      box.style.display = "";
      const at = updStepIndex(phase);
      const dots = UPD_STEPS.map((s, i) => {
        const mark = i < at ? OK_ICON : (i === at ? ic("loader", { cls: "ic-spin" }) : ic("circle", { cls: "ic-dim" }));
        const w = i === at ? "font-weight:600" : "opacity:.7";
        return `<span style="${w}">${mark} ${esc(s.label)}</span>`;
      }).join('<span style="opacity:.4"> → </span>');
      box.innerHTML = `<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px">${dots}</div>`
        + (phase === "rolling_back" ? `<div style="margin-top:6px;color:var(--red)">↩ Bản mới lỗi, đang tự quay về bản cũ…</div>` : "")
        + (extra ? `<div style="margin-top:6px;opacity:.85">${esc(extra)}</div>` : "");
    }
    async function ovLoadVersion() {
      const tag = document.getElementById("ovVerTag");
      const meta = document.getElementById("ovVerMeta");
      const upd = document.getElementById("ovVerUpdate");
      const cl = document.getElementById("ovVerChangelog");
      if (!tag) return;
      meta.textContent = "Đang kiểm tra bản mới…";
      let j = {};
      try { j = await (await fetch("/version", { cache: "no-store" })).json(); }
      catch (e) { meta.innerHTML = WARN_ICON + " Không kiểm tra được (mạng)."; return; }
      tag.textContent = "v" + (j.current || "?");
      window._ovVerCur = j.current || "";
      window._ovVerPrev = j.previous_version || "";
      window._ovVerMode = j.mode || "";
      const ml = modeLbl(j) || j.mode || "";
      if (cl) { cl.style.display = "none"; cl.innerHTML = ""; }
      if (j.update_available) {
        const base = "🆕 Có bản mới <b>v" + esc(j.latest) + "</b> (đang chạy v" + esc(j.current) + ") · " + esc(ml);
        if (j.can_self_update) {
          meta.innerHTML = base;
          upd.style.display = "";
          ovLoadChangelogSnippet(j.current);
        } else {
          meta.innerHTML = base + '<div style="margin-top:8px;line-height:1.55">↻ Cập nhật bằng cách <b>Redeploy</b>: trên Hostinger bấm nút <b>Redeploy</b> trong Docker Manager; trên VPS chạy <code>docker compose up -d --pull always</code>. Bản mới lỗi thì pin tag <code>:' + esc(j.previous_version || "bản-cũ") + '</code> rồi Redeploy để lùi.</div>';
          upd.style.display = "none";
          ovLoadChangelogSnippet(j.current);
        }
      } else if (j.latest) {
        meta.innerHTML = OK_ICON + " Đang dùng bản mới nhất (v" + esc(j.current) + ") · " + esc(ml);
        upd.style.display = "none";
      } else {
        meta.innerHTML = "v" + esc(j.current) + " · " + esc(ml) + (j.error ? " · chưa so được với GitHub" : "");
        upd.style.display = "none";
      }
    }
    async function ovLoadChangelogSnippet(current) {
      const cl = document.getElementById("ovVerChangelog");
      if (!cl) return;
      let d = {};
      try { d = await (await fetch("/changelog", { cache: "no-store" })).json(); }
      catch (e) { return; }
      const fresh = (d.releases || []).filter(r => !r.installed).slice(0, 3);
      if (!fresh.length) return;
      cl.style.display = "";
      cl.innerHTML = "<b>Bản mới có gì:</b><br>" + fresh.map(r => {
        const items = (r.sections || []).flatMap(s => s.items || []).slice(0, 4);
        return "<div style='margin-top:4px'>v" + esc(r.version) + (r.date ? " · " + esc(r.date) : "") + "</div>"
          + "<ul style='margin:2px 0 0 16px;padding:0'>" + items.map(it => "<li>" + esc(it) + "</li>").join("") + "</ul>";
      }).join("");
    }
    const verCheck = document.getElementById("ovVerCheck");
    if (verCheck) verCheck.onclick = ovLoadVersion;
    const verUpd = document.getElementById("ovVerUpdate");
    if (verUpd) verUpd.onclick = async () => {
      if (!confirm("Cập nhật Javis lên bản mới nhất?\nApp sẽ tự khởi động lại. Nếu bản mới lỗi, hệ thống sẽ tự quay về bản cũ (bản git) hoặc hiện cách lùi (Docker).")) return;
      const st = document.getElementById("ovVerStatus");
      const rb = document.getElementById("ovVerRollback");
      const oldCur = window._ovVerCur || "";
      verUpd.disabled = true;
      if (rb) { rb.style.display = "none"; rb.innerHTML = ""; }
      renderProgress("preparing", "Đang chuẩn bị cập nhật…");
      st.textContent = "";
      let resp;
      try { resp = await (await fetch("/update", { method: "POST" })).json(); }
      catch (e) { resp = { ok: true, _dropped: true }; }   // đứt kết nối = server đang restart
      if (resp && resp.ok === false) {
        verUpd.disabled = false;
        renderProgress("preparing", "");
        document.getElementById("ovVerProgress").style.display = "none";
        st.innerHTML = WARN_ICON + " " + esc(resp.error || "Không cập nhật được.") + (resp.manual ? " Chạy: <code>" + esc(resp.manual) + "</code>" : "");
        return;
      }
      st.innerHTML = ic("loader", { cls: "ic-spin" }) + " Đang cập nhật… đừng tắt trang.";
      let tries = 0;
      const poll = setInterval(async () => {
        tries++;
        // 1) ưu tiên trạng thái chi tiết từ updater (bản git)
        let s = null;
        try { s = await (await fetch("/update/status", { cache: "no-store" })).json(); } catch (e) { s = null; }
        if (s && s.state && s.state.phase) {
          const ph = s.state.phase, res = s.state.result;
          const stashNote = s.state.stashed ? ic("package") + " Sửa đổi cục bộ đã được cất vào git stash (dùng 'git stash list' để xem lại)." : "";
          renderProgress(ph, stashNote);
          if (res === "success") { clearInterval(poll); st.innerHTML = OK_ICON + " Đã cập nhật xong. Đang tải lại trang…"; setTimeout(() => location.reload(), 1500); return; }
          if (res === "rolled_back") { clearInterval(poll); renderProgress("done", stashNote); st.innerHTML = "↩ Bản mới lỗi, đã <b>tự quay về bản cũ</b>. Xem <code>update.log</code>."; verUpd.disabled = false; return; }
          if (res === "pull_failed" || res === "rollback_failed" || res === "error") {
            clearInterval(poll);
            const pb = document.getElementById("ovVerProgress"); if (pb) pb.style.display = "none";
            st.innerHTML = WARN_ICON + " " + esc(s.state.error || "Cập nhật lỗi.") + " Xem <code>update.log</code>.";
            verUpd.disabled = false; return;
          }
        }
        // 2) fallback: dò /version (docker qua Watchtower - updater.py không chạy)
        try {
          const v = await (await fetch("/version", { cache: "no-store" })).json();
          const flipOk = (window._ovVerMode === "docker") || !(s && s.state && s.state.phase);
          if (flipOk && v && v.update_available === false && v.current && v.current !== oldCur) {
            clearInterval(poll); st.innerHTML = OK_ICON + " Đã cập nhật xong. Đang tải lại trang…"; setTimeout(() => location.reload(), 1500); return;
          }
          // docker bản mới có thể lỗi: server vẫn còn bản cũ sau khá lâu → hiện cách lùi
          if ((window._ovVerMode === "docker") && tries >= 12 && v && v.current === oldCur) {
            clearInterval(poll);
            const prev = window._ovVerPrev || (v.previous_version || "");
            st.innerHTML = WARN_ICON + " Bản mới chưa lên sau một lúc - có thể lỗi.";
            if (rb) {
              rb.style.display = "";
              rb.innerHTML = "<b>Cách lùi về bản cũ (Docker):</b><br>Pin tag phiên bản cũ rồi kéo lại:"
                + "<br><code>docker compose pull && docker compose up -d</code>"
                + (prev ? "<br>Hoặc sửa image thành <code>ghcr.io/blogminhquy/javis-os:" + esc(prev) + "</code> rồi Redeploy." : "");
            }
            verUpd.disabled = false; return;
          }
        } catch (e) { /* server đang restart - chờ tiếp */ }
        if (tries > 60) { clearInterval(poll); st.innerHTML = "Server chưa lên lại sau ~3 phút - thử tải lại trang."; verUpd.disabled = false; }
      }, 3000);
    };
    ovLoadVersion();

    // ---- Tự khởi động cùng máy (chỉ Windows) ----
    async function ovLoadAutostart() {
      const sec = document.getElementById("ovAutostartSec");
      if (!sec) return;
      let j = {};
      try { j = await (await fetch("/autostart", { cache: "no-store" })).json(); }
      catch (e) { sec.style.display = "none"; return; }
      if (!j.supported) { sec.style.display = "none"; return; }   // Docker/Linux: ẩn hẳn
      sec.style.display = "";
      const on = !!j.enabled;
      // Nhãn phải nói THẬT. "Bật" mà lúc mở máy không có gì chạy là kiểu hỏng đã đưa người
      // dùng tới màn hình ERR_CONNECTION_REFUSED mà không biết bắt đầu tìm từ đâu.
      document.getElementById("ovAutoTag").textContent =
        on ? (j.ly_do ? "bật nhưng không chạy" : "bật") : "tắt";
      const meta = document.getElementById("ovAutoMeta");
      meta.innerHTML = on
        ? "Javis tự chạy nền mỗi khi bạn đăng nhập Windows - không cần bật tay. Chạy ẩn, mở <code>localhost:7777</code> để dùng."
        : "Bật để Javis tự khởi động mỗi khi mở máy. Chạy ẩn ở nền, không hiện cửa sổ.";
      if (j.ly_do) meta.innerHTML += '<br><span class="dim">' + WARN_ICON + " " + esc(j.ly_do) + "</span>";
      const btn = document.getElementById("ovAutoToggle");
      btn.style.display = "";
      btn.disabled = false;
      btn.textContent = on ? "Tắt tự khởi động" : "Bật tự khởi động";
      btn.onclick = async () => {
        btn.disabled = true;
        const st = document.getElementById("ovAutoStatus");
        st.textContent = "Đang lưu…";
        const fd = new FormData(); fd.append("enabled", on ? "0" : "1");
        let r = {};
        try { r = await (await fetch("/autostart", { method: "POST", body: fd })).json(); }
        catch (e) { r = { ok: false, error: e.message }; }
        if (r.ok) { st.textContent = ""; ovLoadAutostart(); }
        else { st.innerHTML = Icons.warn(r.error || "Lỗi"); btn.disabled = false; }
      };
    }
    ovLoadAutostart();

    const btn = document.getElementById("ovGraphToggle");
    if (btn) btn.onclick = async () => {
      btn.disabled = true;
      const next = !(s.dashboard && s.dashboard.graph_enabled !== false);
      await saveSetting("dashboard", { graph_enabled: next });
      graphEnabled = next;
      recomputeGraph();
      renderOverview(el);
    };
    const mig = document.getElementById("ovMigrate");
    if (mig) mig.onclick = async () => {
      const brain = (window.currentBrainPath ? currentBrainPath() : "brain");
      if (!confirm("Chuẩn hóa cấu trúc brain đang chọn?\n(Di chuyển Javis/agents→agents, Javis/workflows→workflows, Memory→memory. Có git backup.)")) return;
      mig.disabled = true; mig.textContent = "Đang chuẩn hóa...";
      const fd = new FormData(); fd.append("brain", brain);
      let r = {};
      try { r = await (await fetch("/brain/migrate", { method: "POST", body: fd })).json(); } catch (e) { r = { ok: false, error: e.message }; }
      const res = document.getElementById("ovMigrateResult");
      if (r.ok) res.innerHTML = `${OK_ICON} ${(r.moved || []).length ? "Đã di chuyển: " + r.moved.join(", ") : "Không có gì cần di chuyển (đã chuẩn)."}` + ((r.skipped || []).length ? `<br><span class="dim">Bỏ qua: ${r.skipped.join("; ")}</span>` : "");
      else res.innerHTML = WARN_ICON + " Lỗi: " + esc(r.error || "không rõ");
      mig.disabled = false; mig.textContent = "Chuẩn hóa brain đang chọn";
    };
  }

  // ---- Trang Models: (A) Main Model + (B) Providers ----
  async function renderModels(el) {
    el.innerHTML = `<div class="cview-placeholder"><div class="ph-ico">${ic("loader", { cls: "ic-xl ic-spin" })}</div><div>Đang tải...</div></div>`;
    const s = await freshSettings();
    const m = s.model || {};
    const providers = m.providers || [];
    const main = m.main || {};
    // Đã kết nối xếp LÊN ĐẦU, chưa kết nối dồn xuống dưới; trong mỗi nhóm giữ nguyên thứ tự
    // gốc của PROVIDER_DEFS (sort có tiebreak theo chỉ số nên ổn định, không phụ thuộc engine).
    // Phải hỏi /claude/status mới biết Claude Code có đăng nhập thật không: nó không có
    // key_field nên server luôn trả configured=true, tin theo đó là Claude chưa đăng nhập vẫn
    // nằm chễm chệ trên cùng. Một request cục bộ, rẻ.
    let claudeOn = false;
    try { claudeOn = !!(await (await fetch("/claude/status")).json()).connected; } catch (e) {}
    // kind "cli" nay có HAI bộ não (Claude Code, Gemini CLI). Chỉ Claude mới phải hỏi
    // /claude/status; Gemini CLI đã có `configured` thật từ server (đọc file đăng nhập).
    const provOn = (p) => (p.id === "anthropic-cli" ? claudeOn : !!p.configured);
    const provList = providers.map((p, i) => ({ p, i }))
      .sort((a, b) => (provOn(b.p) - provOn(a.p)) || (a.i - b.i))
      .map(x => x.p);
    const mainP = providers.find(p => p.id === main.provider) || {};
    const auxCfg = m.auxiliary || {};
    const aux = auxCfg.model || "";
    const auxProv = auxCfg.provider || "anthropic-cli";
    // Việc nền chạy được trên MỌI provider đã đấu, không riêng Claude. Nhưng OpenRouter một
    // mình đã vài trăm model, phơi hết ra thành chip thì tràn trang và không tìm nổi - nên ở
    // đây chỉ hiện LỰA CHỌN HIỆN TẠI, còn việc chọn giao cho openModelPicker (có ô lọc, có
    // cột provider, tự nạp model live) - đúng cái đang dùng cho model chính ngay phía trên.
    const auxProvDef = providers.find(p => p.id === auxProv) || {};
    const auxReady = auxProv === "anthropic-cli" || auxProvDef.configured;
    const reasoning = m.reasoning || "off";
    // Thang này phải KHỚP engine.REASONING_LEVELS bên server và EFFORT trong model-picker.js.
    // Mỗi nấc kèm một dòng RẤT ngắn nói nó đánh đổi gì - đủ để chọn, không phải đọc bài.
    const REASON = [["off", "Tắt", "nhanh nhất"], ["low", "Thấp", "nghĩ sơ"],
                    ["medium", "Vừa", "cân bằng"], ["high", "Cao", "kỹ hơn"],
                    ["xhigh", "Rất cao", "rất kỹ"], ["ultra", "Tối đa", "tốn token nhất"]];
    const reasonChips = REASON.map(([v, l, d]) =>
      `<button class="seg-btn ${reasoning === v ? "sel" : ""}" data-reason="${v}" title="${esc(d)}">` +
      `<span class="seg-lb">${l}</span><span class="seg-d">${esc(d)}</span></button>`).join("");

    const KEYFIELD = { "openrouter": "openrouter_key", "anthropic-api": "anthropic_api_key", "openai": "openai_api_key", "gemini": "gemini_api_key", "groq": "groq_api_key", "ollama": "ollama_key" };
    const provHead = (p, on, kindLabel, statusText) => `
        <div class="prov-head">
          <span class="prov-shield ${on ? "on" : ""}">${_shield(on)}</span>
          <div class="prov-info">
            <div class="prov-name">${esc(p.label)} <span class="prov-kind">${kindLabel}</span></div>
            <div class="prov-status ${on ? "on" : ""}">${statusText}</div>
          </div>
          ${p.is_main ? '<span class="prov-badge">MAIN</span>' : ""}
        </div>`;
    const provCard = (p) => {
      const on = p.configured;
      // Máy thiếu binary CLI thì nói TẠI ĐÂY, đừng để user đăng nhập xanh rồi vào chat mới
      // vỡ (báo cáo 16/08: người mới cài "kết nối được nhưng không sử dụng được").
      // cli_found === false mới cảnh báo - undefined nghĩa là thẻ không thuộc diện kiểm.
      const cliWarn = (ten) => p.cli_found === false
        ? `<div class="prov-note warn">${WARN_ICON} <b>Máy chạy Javis chưa có lệnh <code>${ten}</code></b>
             - ${on ? "đăng nhập đã xong nhưng" : ""} chat bằng thẻ này sẽ lỗi cho tới khi cài.
             Bản Docker: <b>cập nhật Javis lên bản mới nhất</b> là có sẵn. Bản cài tay: mở trang
             Code &gt; Terminal chạy <code>${esc(p.cai_lenh || "")}</code> rồi khởi động lại Javis.</div>`
        : "";
      if (p.kind === "oauth") {
        const st = on
          ? "● Đã kết nối" + (p.plan ? " · " + esc(p.plan) : "") + " · " + p.models.length + " model"
          : "○ Chưa kết nối · " + p.models.length + " model";
        return `<div class="prov-card ${p.is_main ? "main" : ""}">
          ${provHead(p, on, "Device code", st)}
          ${cliWarn("codex")}
          <div class="prov-action" style="flex-wrap:wrap">
            ${on
              ? `<button class="gcard-btn ghost" data-oauth-disc="1">Ngắt</button>`
              : `<button class="gcard-btn" data-oauth-login="1">Đăng nhập ChatGPT</button>
                 <button class="gcard-btn ghost" data-oauth-browser="1">Qua trình duyệt</button>`}
            <span id="oauthMsg" class="gcard-meta" style="margin-left:10px;flex:1;min-width:220px"></span>
          </div>
        </div>`;
      }
      if (p.id === "antigravity-cli") {
        // Bộ não thứ 10. Không có nút "Đăng nhập" ở đây và đó là quyết định có lý do: đăng nhập
        // của `agy` là một giao diện bàn phím trong terminal, token thì nằm trong keyring hệ
        // điều hành chứ không phải file. Bản 0.30-0.32.1 có thử lái luồng đó qua một terminal
        // giả - chạy được trên Linux nhưng trên trang hiện ra một ô terminal bấm không ăn, còn
        // Windows không có pseudo-terminal nên luôn tắc. Người dùng `agy` vốn là dân code, gõ
        // một lệnh nhanh hơn hẳn. Nên thẻ này chỉ đưa đúng lệnh cần gõ.
        const dn = p.dang_nhap || {};
        const st = on
          ? "● Đã đăng nhập" + (p.auth_method ? " · " + esc(p.auth_method) : "")
            + " · " + p.models.length + " model"
          : (p.cli_found ? "○ Đã cài CLI, chưa đăng nhập" : "○ Chưa cài Antigravity CLI");
        return `<div class="prov-card ${p.is_main ? "main" : ""}">
          ${provHead(p, on, "MCP/skill", st)}
          <div class="prov-note">Dùng <b>gói Google của bạn</b>, không cần mua API key. Đây là
            bản Google chỉ định thay cho Gemini CLI, và cho chọn <b>đúng dàn model của
            Antigravity IDE</b> - gồm cả model không phải của Google.</div>
          ${p.cli_found ? "" : `<div class="prov-steps">
            <div>Chưa thấy CLI trên máy. Cài một lần trên máy chạy Javis:<br><code>${esc(p.cai_lenh || "")}</code></div>
          </div>`}
          ${on ? "" : `<div class="prov-steps">
            <div><b>Đăng nhập trong terminal của máy chạy Javis:</b> <code>${esc(dn.dang_nhap || "agy")}</code></div>
            <div>${esc(dn.ghi_chu || "")}</div>
            <div>Xong rồi bấm <b>Kiểm tra lại</b> ở dưới.</div>
          </div>`}
          <div class="prov-action" style="flex-wrap:wrap">
            <button class="gcard-btn ghost" data-agycheck="1">Kiểm tra lại</button>
            <span id="agyMsg" class="gcard-meta" style="margin-left:10px;flex:1;min-width:200px">${on ? "" : esc(p.auth_error || "")}</span>
          </div>
        </div>`;
      }
      if (p.id === "gemini-cli") {
        // Gemini CLI: đăng nhập bằng tài khoản Google, KHÔNG cần mua API key. Không có nút
        // "Đăng nhập" ở đây là cố ý - luồng đăng nhập của nó là giao diện bàn phím trong
        // terminal rồi mở trình duyệt, không có cờ headless nào để bọc cho tử tế. Dựng một
        // cái nút chỉ chạy được trên máy có màn hình thì trên VPS nó là nút chết.
        const st = on
          ? "● Đã đăng nhập Google" + (p.account ? " · " + esc(p.account) : "")
            + (p.auth_method ? " · " + esc(p.auth_method) : "") + " · " + p.models.length + " model"
          : (p.cli_found ? "○ Đã cài CLI, chưa đăng nhập" : "○ Chưa cài Gemini CLI");
        return `<div class="prov-card ${p.is_main ? "main" : ""}">
          ${provHead(p, on, "MCP/skill", st)}
          <div class="prov-note warn"><b>Google đã ngắt đường này với tài khoản cá nhân từ 18/06/2026</b>
            - cả gói miễn phí, Google AI Pro lẫn Ultra. Đăng nhập vẫn xong nhưng lúc chat sẽ báo
            <code>IneligibleTierError</code>. Chặn từ phía Google, không sửa được bên Javis.
            Thẻ này giờ chỉ còn dùng được với <b>giấy phép Code Assist doanh nghiệp</b> hoặc khi
            chạy CLI bằng API key.</div>
          <div class="prov-steps">
            <div><b>Muốn dùng model Gemini thì đi đường khác:</b> thẻ <b>OpenRouter</b> (nhiều model
              một chỗ, có cả Gemini lẫn Claude - gần nhất với trình chọn model của Antigravity),
              hoặc thẻ <b>Google Gemini (API)</b> bên dưới.</div>
          </div>
          ${p.cli_found ? "" : `<div class="prov-steps">
            <div>Chưa thấy CLI trên máy. Cài tay: <code>npm install -g @google/gemini-cli</code></div>
          </div>`}
          <div class="prov-action" style="flex-wrap:wrap">
            ${on
              ? (p.auth_by_javis ? `<button class="gcard-btn ghost" data-glogout="1">Ngắt</button>` : "")
              : `<button class="gcard-btn" data-glogin="1">Đăng nhập Google</button>`}
            <button class="gcard-btn ghost" data-gcheck="1">Kiểm tra lại</button>
            <span id="gcliMsg" class="gcard-meta" style="margin-left:10px;flex:1;min-width:200px">${on ? "" : esc(p.auth_error || "")}</span>
          </div>
          <div id="gcliLogin"></div>
        </div>`;
      }
      if (p.kind === "cli") {   // Claude Code - trạng thái + login/logout nạp động qua /claude/status
        // Ô chọn nguồn xác thực. Cả hai lựa chọn giữ NGUYÊN năng lực (Bash, WebFetch, MCP, nối
        // phiên cũ); khác nhau ở chỗ ai trả tiền và ai chịu rủi ro. Javis cố ý không tắt cứng
        // đường subscription - chủ máy tự cân, nhưng phải cân khi đã BIẾT, nên có cảnh báo.
        const byKey = p.auth_mode === "api_key";
        return `<div class="prov-card ${p.is_main ? "main" : ""}">
          <div class="prov-head">
            <span class="prov-shield on">${_shield(true)}</span>
            <div class="prov-info">
              <div class="prov-name">${esc(p.label)} <span class="prov-kind">MCP/skill</span></div>
              <div class="prov-status" id="cliStatus">đang kiểm tra…</div>
            </div>
            ${p.is_main ? '<span class="prov-badge">MAIN</span>' : ""}
          </div>
          ${cliWarn("claude")}
          <div class="prov-action" id="cliAction"></div>
          <div class="prov-auth">
            <div class="prov-auth-title">Chạy bằng</div>
            <div class="prov-auth-note">Ô này chỉ đổi <b>ai trả tiền</b>. Cả hai đều chạy qua
              Claude Code nên <b>giữ nguyên lệnh máy, WebFetch, MCP native và nối phiên cũ</b> -
              khác hẳn thẻ "Anthropic (API)" bên dưới, thẻ đó gọi API thẳng nên không chạy được
              lệnh máy.</div>
            <label class="prov-auth-opt"><input type="radio" name="claudeAuth" value="subscription" ${byKey ? "" : "checked"}>
              <span><b>Gói đang đăng nhập</b> - không tốn thêm tiền. Hợp với một người dùng cá nhân ngồi gõ.</span></label>
            <label class="prov-auth-opt"><input type="radio" name="claudeAuth" value="api_key" ${byKey ? "checked" : ""}>
              <span><b>API key Anthropic</b> - trả theo lượt dùng. Đây là cách duy nhất để việc nền
              (loop, nhắc hẹn, Kanban) chạy <b>vừa hợp lệ vừa còn lệnh máy</b>.
              ${p.auth_api_key_set ? "" : ` <i>Chưa có key: dán ở thẻ "${esc("Anthropic (API)")}" bên dưới - dán xong quay lại đây chọn ô này.</i>`}</span></label>
            ${p.auth_warning ? `<div class="prov-auth-warn">${WARN_ICON} ${esc(p.auth_warning)}</div>` : ""}
          </div>
        </div>`;
      }
      const masked = (m[KEYFIELD[p.id]] || "").slice(-4);
      return `<div class="prov-card ${p.is_main ? "main" : ""}">
        ${provHead(p, on, p.kind === "cli" ? "MCP/skill" : "MCP Javis", (on ? "● Đã kết nối" : "○ Chưa kết nối") + " · " + p.models.length + " model")}
        ${p.needs_key
          ? `<div class="prov-action"><input class="js-input" id="pk-${p.id}" type="password" placeholder="${on ? "Đổi key (•••" + esc(masked) + ")" : "Dán API key để kết nối"}"><button class="gcard-btn" data-pk="${p.id}">${on ? "Đổi key" : "Kết nối"}</button>${on ? `<button class="gcard-btn ghost" data-disc="${p.id}">Ngắt</button>` : ""}</div>`
          : `<div class="prov-note">Dùng đăng nhập Claude Code - không cần key</div>`}
      </div>`;
    };

    el.innerHTML = `
      <div class="cview-section">
        <h3>◆ Main Model <span style="opacity:.5">model chính cho hội thoại</span></h3>
        <div class="gcard current" style="max-width:540px">
          <div class="gcard-top"><span class="gcard-name">${esc(main.model || "-")}</span><span class="gcard-tag">${esc(mainP.label || main.provider || "")}</span></div>
          <div class="gcard-meta">${mainP.id === "gemini-cli" ? "Qua Gemini CLI - MCP Javis + skill + loop + chạy lệnh máy (đăng nhập Google)"
            : mainP.kind === "cli" ? "Qua Claude Code - MCP Javis + skill + loop + chạy lệnh máy"
            : mainP.kind === "oauth" ? "Qua Codex - MCP Javis + skill + loop + chạy lệnh máy"
            : mainP.kind === "api" ? "Gọi API thẳng - MCP Javis + skill + loop (không chạy lệnh máy)" : ""}</div>
          <button class="gcard-btn" id="mdChange">Đổi model ▾</button>
        </div>
      </div>
      <div class="cview-section">
        <h3>◆ Providers <span style="opacity:.5">đăng nhập / kết nối nhà cung cấp model</span></h3>
        <div class="prov-list">${provList.map(provCard).join("")}</div>
      </div>
      <div class="cview-section">
        <h3>◆ Model việc nền <span style="opacity:.5">loop · việc Kanban · nhắc hẹn · tự học</span></h3>
        <div class="gcard aux-card">
          <div class="gcard-meta">Model chạy việc nền. Chọn model rẻ để đỡ hạn mức Claude.</div>
          <div class="aux-now">
            <div class="aux-now-txt">
              <div class="aux-now-model">${aux ? esc(aux) : "Mặc định của Claude Code"}</div>
              <div class="aux-now-prov">${aux ? esc(auxProvDef.label || auxProv) : "dùng model mặc định"}</div>
            </div>
            <div class="aux-now-act">
              ${aux ? '<button class="gcard-btn ghost" id="auxReset">Về mặc định</button>' : ""}
              <button class="gcard-btn" id="auxChange">Đổi model ▾</button>
            </div>
          </div>
          ${auxReady ? "" : `<div class="aux-note warn">${WARN_ICON} Nhà cung cấp này chưa kết nối - việc nền sẽ tự dùng lại Claude.</div>`}
          <div class="aux-note">Claude Code và Codex chạy được lệnh máy. Model API chỉ đọc/ghi qua vault - hợp việc đọc, tổng hợp, ghi chú.</div>
        </div>
      </div>
      <div class="cview-section">
        <h3>◆ Độ sâu suy nghĩ <span style="opacity:.5">nghĩ kỹ hơn trước khi trả lời</span></h3>
        <div class="gcard aux-card">
          <div class="gcard-meta">Nghĩ càng sâu càng chính xác, nhưng chậm và tốn token hơn.</div>
          <div class="seg">${reasonChips}</div>
          <div class="aux-note">Nhiều nhà cung cấp chỉ nhận 3 nấc, nên hai nấc trên cùng có thể như nhau ở đó. OpenAI cần model o-series, Gemini cần 2.5 trở lên.</div>
        </div>
      </div>`;

    const chg = document.getElementById("mdChange");
    if (chg) chg.onclick = () => openModelPicker(provList, main, () => renderModels(el));
    // Nguồn xác thực của gói Claude Code. Vẽ lại cả trang sau khi lưu vì cảnh báo phụ thuộc
    // cả lựa chọn này LẪN model việc nền - chỉ server mới ghép được hai thứ đó.
    el.querySelectorAll('input[name="claudeAuth"]').forEach((r) => {
      r.onchange = async () => {
        if (!r.checked) return;
        await saveSetting("model", { claude_auth: r.value });
        renderModels(el);
      };
    });
    const auxChg = document.getElementById("auxChange");
    if (auxChg) auxChg.onclick = () => openModelPicker(provList, { provider: auxProv, model: aux }, () => renderModels(el), {
      title: "MODEL VIỆC NỀN",
      note: "Việc nền: loop · việc Kanban · nhắc hẹn · tự học · tiêu hoá nguồn",
      save: (prov, mod) => saveSetting("model", { auxiliary: { provider: prov, model: mod } }),
    });
    const auxRst = document.getElementById("auxReset");
    if (auxRst) auxRst.onclick = async () => {
      await saveSetting("model", { auxiliary: { provider: "anthropic-cli", model: "" } });
      renderModels(el);
    };
    el.querySelectorAll("[data-reason]").forEach(b => b.onclick = async () => {
      await saveSetting("model", { reasoning: b.dataset.reason });
      renderModels(el);
    });
    el.querySelectorAll(".gcard-btn[data-pk]").forEach(b => {
      b.onclick = async () => {
        const pid = b.dataset.pk;
        const inp = document.getElementById("pk-" + pid);
        const val = (inp && inp.value || "").trim();
        if (!val) { if (inp) inp.focus(); return; }
        b.disabled = true; b.textContent = "Đang lưu...";
        await saveSetting("model", { [KEYFIELD[pid]]: val });
        renderModels(el);
      };
    });
    el.querySelectorAll(".gcard-btn[data-disc]").forEach(b => {
      b.onclick = async () => {
        b.disabled = true; b.textContent = "Đang ngắt...";
        await saveSetting("model", { clear_key: b.dataset.disc });
        renderModels(el);
      };
    });
    const ol = el.querySelector("[data-oauth-login]");
    if (ol) ol.onclick = () => startOauthLogin(el);
    const ob = el.querySelector("[data-oauth-browser]");
    if (ob) ob.onclick = () => startOauthBrowser(el);
    const gl = el.querySelector("[data-glogin]");
    if (gl) gl.onclick = () => startGeminiLogin(el);
    const glo = el.querySelector("[data-glogout]");
    if (glo) glo.onclick = async () => {
      if (!confirm("Ngắt tài khoản Google khỏi Javis?")) return;
      glo.disabled = true; glo.textContent = "Đang ngắt...";
      try { await fetch("/gemini-cli/logout", { method: "POST" }); } catch (e) {}
      _daHoiModel.delete("gemini-cli");
      renderModels(el);
    };
    const gk = el.querySelector("[data-gcheck]");
    if (gk) gk.onclick = async () => {
      const msg = el.querySelector("#gcliMsg");
      gk.disabled = true; const cu = gk.textContent; gk.textContent = "Đang thử…";
      if (msg) msg.textContent = "Đang chạy thử một lượt thật…";
      let r = null;
      try { r = await (await fetch("/gemini-cli/check", { method: "POST" })).json(); }
      catch (e) { r = { ok: false, error: "Lỗi mạng." }; }
      gk.disabled = false; gk.textContent = cu;
      if (r && r.ok) {
        if (msg) msg.innerHTML = OK_ICON + " Dùng được.";
        _daHoiModel.delete("gemini-cli");
        setTimeout(() => renderModels(el), 700);
      } else if (msg) msg.innerHTML = Icons.warn((r && r.error) || "Chưa dùng được.");
    };
    const agk = el.querySelector("[data-agycheck]");
    if (agk) agk.onclick = async () => {
      const msg = el.querySelector("#agyMsg");
      agk.disabled = true; const cu2 = agk.textContent; agk.textContent = "Đang thử…";
      if (msg) msg.textContent = "Đang chạy thử một lượt thật…";
      let r = null;
      // Gửi kèm brain đang mở: phần `mcp` của câu trả lời soi cấu hình theo ĐÚNG brain đó
      // (header X-Javis-Vault khoá tool file/lịch vào một brain), nên hỏi trống là soi nhầm.
      const _br = window.currentBrainPath ? currentBrainPath() : "brain";
      try { r = await (await fetch(`/antigravity/check?brain=${encodeURIComponent(_br)}`,
                                   { method: "POST" })).json(); }
      catch (e) { r = { ok: false, error: "Lỗi mạng." }; }
      agk.disabled = false; agk.textContent = cu2;
      // Nói RIÊNG chuyện tool của Javis. "Chat được" và "gọi được tool của Javis" là hai
      // chuyện khác nhau, và suốt các bản 0.30-0.42 cái thứ hai luôn hỏng trong khi cái thứ
      // nhất vẫn xanh - nên thẻ này chỉ báo "Dùng được" là báo thiếu đúng chỗ đau.
      const mcpTxt = (r && r.mcp)
        ? (r.mcp.ok ? " · tool của Javis đã đấu"
           : (r.mcp.hub_bat === false ? " · trung tâm kết nối đang tắt"
              : " · <b>chưa đấu được tool của Javis</b>"))
        : "";
      if (r && r.ok) {
        if (msg) msg.innerHTML = OK_ICON + " Dùng được." + mcpTxt;
        _daHoiModel.delete("antigravity-cli");
        setTimeout(() => renderModels(el), 700);
      } else if (msg) msg.innerHTML = Icons.warn((r && r.error) || "Chưa dùng được.") + mcpTxt;
    };
    const od = el.querySelector("[data-oauth-disc]");
    if (od) od.onclick = async () => {
      od.disabled = true; od.textContent = "Đang ngắt...";
      try { await fetch("/oauth/openai/disconnect", { method: "POST" }); } catch (e) {}
      _daHoiModel.delete("openai-oauth");
      renderModels(el);
    };
    refreshClaudeCard(el);   // nạp trạng thái đăng nhập Claude Code (bất đồng bộ)
    hoiModelConNo(el, provList);   // thẻ "0 model" của provider đã kết nối: hỏi danh sách thật
  }

  // Provider nào ĐÃ kết nối mà thẻ vẫn hiện "0 model" thì đi hỏi danh sách thật ngay tại đây.
  //
  // Vì sao cần: con số trên thẻ đọc từ `model.catalog` trong settings, mà catalog chỉ được ghi
  // SAU một lần lấy live thành công. ChatGPT không có catalog mặc định (danh sách model do
  // Codex quyết, Javis cố ý không ghim version), nên trên máy mới đăng nhập xong là thẻ hiện
  // "● Đã kết nối · 0 model" và nằm im như vậy cho tới khi ai đó mở hộp chọn model - trông y
  // hệt đăng nhập hỏng. Máy cũ không thấy lỗi này chỉ vì catalog đã có sẵn từ lần trước.
  const _daHoiModel = new Set();   // hỏi HỤT thì thôi, không quay vòng vô tận
  async function hoiModelConNo(el, provList) {
    const rong = (provList || []).filter(p => p.configured && !(p.models || []).length
                                              && !_daHoiModel.has(p.id));
    if (!rong.length) return;
    let coThem = false;
    for (const p of rong) {
      _daHoiModel.add(p.id);
      try {
        const r = await (await fetch("/provider/models?provider=" + encodeURIComponent(p.id) + "&refresh=1")).json();
        // `live` = vừa lấy được thật và server đã ghi vào catalog → vẽ lại là con số đúng.
        if (r && r.live && r.models && r.models.length) coThem = true;
        else if (r && r.error) {
          const box = el.querySelector("#oauthMsg");
          if (box && p.kind === "oauth" && !box.textContent.trim()) box.innerHTML = Icons.warn(r.error);
        }
      } catch (e) {}
    }
    if (coThem && el.isConnected) renderModels(el);
  }

  // ---- Card Claude Code: status + login/logout (giống OpenAI OAuth) ----
  async function refreshClaudeCard(el, ep) {
    const st = el.querySelector("#cliStatus"), act = el.querySelector("#cliAction");
    if (!st || !act) return;
    let d;
    try { d = await (await fetch("/claude/status" + (ep ? "?refresh=1" : ""))).json(); }
    catch (e) { st.textContent = "không kiểm tra được"; return; }
    // KHÔNG hỏi được KHÁC hẳn "chưa đăng nhập", và trước bản này hai thứ đó vẽ y như nhau: một
    // lần hết giờ (hay gặp lúc đổi Main Model, khi trang cùng lúc gọi mấy tiến trình con) là
    // thẻ bày ra nút Đăng nhập, người dùng tưởng mất tài khoản rồi đi nối lại - trong khi
    // chẳng có gì mất cả (chủ repo báo 2026-08-13). Chưa biết thì nói là chưa biết.
    if (!d.connected && d.unknown) {
      st.className = "prov-status";
      st.textContent = "◐ Chưa kiểm được trạng thái" + (d.error ? " · " + d.error : "");
      act.innerHTML = `
        <button class="gcard-btn ghost" id="cliRecheck">↻ Kiểm tra lại</button>
        <button class="gcard-btn ghost" id="cliLogin">Đăng nhập Claude</button>
        <span id="cliMsg" class="gcard-meta" style="margin-left:10px;flex:1"></span>
        <div class="prov-note" style="margin-top:8px;line-height:1.6">
          Chưa hỏi được Claude Code lần này (thường là máy đang bận). <b>Không có nghĩa là bạn bị
          đăng xuất</b> - bấm Kiểm tra lại trước khi nghĩ tới chuyện đăng nhập lại.
        </div>`;
      el.querySelector("#cliRecheck").onclick = () => refreshClaudeCard(el, true);
      el.querySelector("#cliLogin").onclick = () => startClaudeLogin(el);
      return;
    }
    if (d.connected) {
      st.className = "prov-status on";
      st.textContent = "● Đã kết nối" + (d.email ? " · " + d.email : "") + (d.plan ? " · " + d.plan : "")
        + (d.stale ? " · (chưa hỏi lại được, đang hiện trạng thái lần trước)" : "");
      act.innerHTML = `<button class="gcard-btn ghost" id="cliLogout">Ngắt</button>`;
      el.querySelector("#cliLogout").onclick = async () => {
        const b = el.querySelector("#cliLogout"); b.disabled = true; b.textContent = "Đang ngắt…";
        try { await fetch("/claude/logout", { method: "POST" }); } catch (e) {}
        refreshClaudeCard(el);
      };
    } else {
      st.className = "prov-status";
      st.textContent = d.error ? "○ " + esc(d.error) : "○ Chưa đăng nhập";
      act.innerHTML = `
        <button class="gcard-btn" id="cliLogin">Đăng nhập Claude</button>
        <button class="gcard-btn ghost" id="cliRecheck">↻ Kiểm tra lại</button>
        <span id="cliMsg" class="gcard-meta" style="margin-left:10px;flex:1"></span>
        <div class="prov-note" style="margin-top:8px;line-height:1.6">
          Bấm <b>Đăng nhập Claude</b> → hiện link → mở link đăng nhập claude.ai → dán code (nếu trang yêu cầu) vào ô.
          Chạy được cả trên VPS. (Hoặc terminal: <code>claude auth login --claudeai</code>.)
        </div>`;
      el.querySelector("#cliLogin").onclick = () => startClaudeLogin(el);
      el.querySelector("#cliRecheck").onclick = () => refreshClaudeCard(el, true);
    }
  }

  async function startClaudeLogin(el) {
    const act = el.querySelector("#cliAction");
    const msg = el.querySelector("#cliMsg");
    if (msg) msg.textContent = "Đang lấy link đăng nhập…";
    let r;
    try { r = await (await fetch("/claude/login-start", { method: "POST" })).json(); }
    catch (e) { if (msg) msg.textContent = "Lỗi mạng."; return; }
    if (!r.ok) { if (msg) msg.innerHTML = Icons.warn(r.error || "Không bắt đầu được đăng nhập."); return; }
    if (act) act.innerHTML = `
      <div class="prov-note" style="line-height:1.7">
        <b>1)</b> Mở link này để đăng nhập claude.ai:<br>
        <a href="${esc(safeHref(r.url))}" target="_blank" rel="noopener" style="color:var(--link-ink);word-break:break-all">${esc(r.url || "(không có link)")}</a><br>
        <b>2)</b> Đăng nhập xong, nếu trang hiện <b>một mã code</b> thì dán vào đây:
        <div style="margin-top:6px;display:flex;gap:8px;max-width:520px">
          <input class="js-input" id="cliCode" placeholder="Dán code (nếu có)" style="flex:1">
          <button class="gcard-btn" id="cliCodeBtn">Gửi code</button>
        </div>
        <span id="cliMsg2" class="gcard-meta"></span>
      </div>`;
    const m2 = el.querySelector("#cliMsg2");
    let stopped = false;
    const t0 = Date.now();
    const poll = async () => {   // tự hoàn tất (một số luồng không cần dán code)
      if (stopped) return;
      if (Date.now() - t0 > 5 * 60 * 1000) { if (m2) m2.textContent = "Hết thời gian, thử lại."; return; }
      let d; try { d = await (await fetch("/claude/status")).json(); } catch (e) { setTimeout(poll, 3000); return; }
      if (d.connected) { stopped = true; refreshClaudeCard(el); return; }
      setTimeout(poll, 3000);
    };
    setTimeout(poll, 3000);
    const cb = el.querySelector("#cliCodeBtn");
    if (cb) cb.onclick = async () => {
      const code = (el.querySelector("#cliCode").value || "").trim();
      if (m2) m2.textContent = "Đang xác nhận…";
      const fd = new FormData(); fd.append("code", code);
      let rr;
      try { rr = await (await fetch("/claude/login-code", { method: "POST", body: fd })).json(); }
      catch (e) { if (m2) m2.textContent = "Lỗi mạng."; return; }
      if (rr.ok) { stopped = true; refreshClaudeCard(el); }
      else if (m2) m2.innerHTML = Icons.warn(rr.error || "Code sai, thử lại.");
    };
  }

  // ---- Gemini CLI: đăng nhập Google ngay trên trang, không phải mở terminal ----
  // Dùng đúng đường "mã dán" của chính Gemini CLI: Google redirect về trang codeassist của họ,
  // trang đó HIỆN RA một mã cho người dùng chép. Không có localhost nào ở giữa nên chạy được
  // cả khi Javis nằm trên VPS còn trình duyệt ở máy người dùng - y như đăng nhập Claude Code.
  async function startGeminiLogin(el) {
    const hop = el.querySelector("#gcliLogin");
    const msg = el.querySelector("#gcliMsg");
    if (msg) msg.textContent = "Đang lấy link đăng nhập…";
    let r;
    try { r = await (await fetch("/gemini-cli/login-start", { method: "POST" })).json(); }
    catch (e) { if (msg) msg.textContent = "Lỗi mạng."; return; }
    if (!r.ok || !r.authorize_url) {
      if (msg) msg.innerHTML = Icons.warn(r.error || "Không bắt đầu được đăng nhập.");
      return;
    }
    if (msg) msg.textContent = "";
    try { window.open(r.authorize_url, "_blank"); } catch (e) {}
    if (hop) hop.innerHTML = `
      <div class="prov-steps">
        <div><b>1)</b> Mở link này rồi đăng nhập bằng tài khoản Google của bạn:<br>
          <a href="${esc(safeHref(r.authorize_url))}" target="_blank" rel="noopener"
             style="color:var(--link-ink);word-break:break-all">${esc(r.authorize_url.slice(0, 90))}…</a></div>
        <div><b>2)</b> Đồng ý xong, Google hiện ra <b>một mã</b>. Chép mã đó dán vào đây:</div>
        <div class="gcli-code-row">
          <input class="js-input" id="gcliCode" placeholder="Dán mã Google vừa hiện" autocomplete="off"
                 spellcheck="false">
          <button class="gcard-btn" id="gcliCodeBtn">Xong</button>
        </div>
        <div id="gcliCodeMsg" class="gcard-meta" style="margin-top:4px"></div>
      </div>`;
    const btn = el.querySelector("#gcliCodeBtn");
    if (btn) btn.onclick = async () => {
      const m2 = el.querySelector("#gcliCodeMsg");
      const code = (el.querySelector("#gcliCode").value || "").trim();
      if (!code) { if (m2) m2.textContent = "Dán mã vào đã."; return; }
      btn.disabled = true; if (m2) m2.textContent = "Đang xác nhận…";
      let d;
      try {
        const fd = new FormData(); fd.append("code", code);
        d = await (await fetch("/gemini-cli/login-code", { method: "POST", body: fd })).json();
      } catch (e) { d = { ok: false, error: "Lỗi mạng." }; }
      btn.disabled = false;
      if (!d.ok) { if (m2) m2.innerHTML = Icons.warn(d.error || "Chưa được, thử lại."); return; }
      if (m2) m2.innerHTML = OK_ICON + " Đã kết nối" + (d.email ? " · " + esc(d.email) : "") + ".";
      _daHoiModel.delete("gemini-cli");
      setTimeout(() => renderModels(el), 900);
    };
  }

  // ---- ChatGPT OAuth device-code: lấy mã → mở link → poll tới khi kết nối ----
  async function startOauthLogin(el) {
    const msg = el.querySelector("#oauthMsg");
    if (msg) msg.textContent = "Đang khởi tạo…";
    let d;
    try { d = await (await fetch("/oauth/openai/start", { method: "POST" })).json(); }
    catch (e) { if (msg) msg.textContent = "Lỗi kết nối server."; return; }
    if (d.error) { if (msg) msg.textContent = "Lỗi: " + d.error; return; }
    try { window.open(d.verification_uri, "_blank"); } catch (e) {}
    if (msg) msg.innerHTML = `Mở <a href="${esc(safeHref(d.verification_uri))}" target="_blank">${esc(d.verification_uri)}</a> · nhập mã <b style="font-size:1.15em;letter-spacing:1px">${esc(d.user_code)}</b> <span style="opacity:.6">- đang chờ…</span>`;
    const iv = Math.max(2, (d.interval || 5)) * 1000;
    const t0 = Date.now();
    const poll = async () => {
      if (Date.now() - t0 > 16 * 60 * 1000) { if (msg) msg.textContent = "Hết hạn, thử lại."; return; }
      let p;
      try { p = await (await fetch("/oauth/openai/poll", { method: "POST" })).json(); }
      catch (e) { setTimeout(poll, iv); return; }
      if (p.status === "connected") {
        if (msg) msg.innerHTML = CHECK_ICON + " Đã kết nối! Đang hỏi Codex xem gói này có model nào…";
        _daHoiModel.delete("openai-oauth");   // vừa đăng nhập xong: cho phép hỏi lại danh sách
        renderModels(el); return;
      }
      if (p.status === "error") { if (msg) msg.textContent = "Lỗi: " + (p.error || ""); return; }
      setTimeout(poll, iv);
    };
    setTimeout(poll, iv);
  }

  // ---- ChatGPT OAuth qua trình duyệt: mở link → user dán lại URL callback → đổi token ----
  async function startOauthBrowser(el) {
    const msg = el.querySelector("#oauthMsg");
    if (msg) msg.textContent = "Đang khởi tạo…";
    let d;
    try { d = await (await fetch("/oauth/openai/browser/start", { method: "POST" })).json(); }
    catch (e) { if (msg) msg.textContent = "Lỗi kết nối server."; return; }
    if (d.error) { if (msg) msg.textContent = "Lỗi: " + d.error; return; }
    if (!d.authorize_url) { if (msg) msg.textContent = "Máy chủ chưa có chức năng này - khởi động lại Javis rồi tải lại trang (Ctrl+Shift+R)."; return; }
    try { window.open(d.authorize_url, "_blank"); } catch (e) {}
    if (msg) msg.innerHTML =
      `Đã mở trang <a href="${esc(safeHref(d.authorize_url))}" target="_blank">đăng nhập ChatGPT</a>. `
      + `Đăng nhập xong, trình duyệt sẽ nhảy sang <b>localhost</b> (có thể báo không tải được trang - không sao). `
      + `Copy toàn bộ đường dẫn trên thanh địa chỉ rồi dán vào đây:`
      + `<div style="display:flex;gap:6px;margin-top:6px">`
      + `<input id="oauthCb" class="js-input" placeholder="Ví dụ: http://localhost:1455/auth/callback?code=…" style="flex:1;min-width:180px">`
      + `<button class="gcard-btn" id="oauthCbBtn">Xác nhận</button></div>`
      + `<div id="oauthCbMsg" class="gcard-meta" style="margin-top:4px;opacity:.75"></div>`;
    const btn = el.querySelector("#oauthCbBtn");
    if (btn) btn.onclick = async () => {
      const cb = (el.querySelector("#oauthCb").value || "").trim();
      const m2 = el.querySelector("#oauthCbMsg");
      if (!cb) { if (m2) m2.textContent = "Dán đường dẫn callback vào đã."; return; }
      btn.disabled = true; if (m2) m2.textContent = "Đang xác nhận…";
      let p;
      try {
        p = await (await fetch("/oauth/openai/browser/finish", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ callback: cb }),
        })).json();
      } catch (e) { if (m2) m2.textContent = "Lỗi mạng."; btn.disabled = false; return; }
      if (p.status === "connected") {
        if (msg) msg.innerHTML = CHECK_ICON + " Đã kết nối! Đang hỏi Codex xem gói này có model nào…";
        _daHoiModel.delete("openai-oauth");
        renderModels(el); return;
      }
      if (m2) m2.innerHTML = Icons.warn(p.error || "Chưa được, thử lại.");
      btn.disabled = false;
    };
  }

  // ---- Picker model (kiểu Hermes SET MAIN MODEL) ----
  function openModelPicker(providers, main, onDone, opts) {
    // opts (tuỳ chọn) để dùng lại hộp này cho MODEL VIỆC NỀN, không chỉ model chính:
    //   {title, note, save(provider, model)}. Thiếu opts = hành vi cũ (đổi model chính).
    opts = opts || {};
    const SAVE = opts.save || ((prov, mod) => saveSetting("model", { main: { provider: prov, model: mod } }));
    let filterQ = "";   // giữ chữ đang lọc qua mỗi lần vẽ lại (bấm provider là draw() dựng lại DOM)
    let modal = document.getElementById("modelPicker");
    if (!modal) { modal = document.createElement("div"); modal.id = "modelPicker"; modal.className = "mp-overlay"; document.body.appendChild(modal); }
    let selProv = main.provider || (providers[0] && providers[0].id);
    // "đang chọn" phải so với main truyền vào, KHÔNG dùng p.is_main: is_main do server tính cho
    // MODEL CHÍNH, nên ở chế độ model việc nền nó sẽ đánh dấu nhầm nhà cung cấp của model chính.
    let selModel = (selProv === main.provider) ? (main.model || null) : null;
    const liveCache = {};      // pid -> {models:[], live:bool} - model load động từ API provider
    let loadingProv = null;

    const modelsFor = (pid) => (liveCache[pid] && liveCache[pid].models) || (providers.find(x => x.id === pid) || {}).models || [];
    const tagFor = (pid) => {
      if (loadingProv === pid && !liveCache[pid]) return " · đang tải…";
      if (!liveCache[pid]) return "";
      return liveCache[pid].live ? " · live" : " · catalog";
    };

    async function ensureModels(pid) {
      if (liveCache[pid]) { draw(); return; }
      loadingProv = pid; draw();
      let res = null;
      try {
        const force = pid === "openai-oauth" ? "&refresh=1" : "";
        res = await (await fetch("/provider/models?provider=" + encodeURIComponent(pid) + force)).json();
      } catch (e) {}
      const stat = (providers.find(x => x.id === pid) || {}).models || [];
      liveCache[pid] = (res && res.models && res.models.length)
        ? { models: res.models, live: !!res.live }
        // Rỗng thì GIỮ LẠI lý do server nói. Trước đây nuốt mất nên hộp chọn chỉ còn một câu
        // chung chung "chưa kết nối hoặc không có model", đọc xong vẫn không biết phải làm gì.
        : { models: stat, live: false, error: (res && res.error) || "" };
      if (loadingProv === pid) loadingProv = null;
      if (pid === selProv) {   // model đang chọn không còn trong list mới → reset
        const ms = liveCache[pid].models;
        if (!selModel || ms.indexOf(selModel) < 0)
          selModel = (pid === main.provider && ms.indexOf(main.model) >= 0) ? main.model : (ms[0] || null);
      }
      draw();
    }

    const draw = () => {
      const models = modelsFor(selProv);
      modal.innerHTML = `
        <div class="mp-box">
          <div class="mp-head">
            <div><div class="mp-title">${esc(opts.title || "SET MAIN MODEL")}</div><div class="mp-sub">hiện tại: ${esc(main.model || "mặc định")} · ${esc(main.provider || "")}</div></div>
            <button class="mp-x" data-act="close">${X_ICON}</button>
          </div>
          <input class="mp-filter" placeholder="Lọc provider / model…" value="${esc(filterQ)}">
          <div class="mp-body">
            <div class="mp-provs">${providers.map(p => `
              <button class="mp-prov ${p.id === selProv ? "active" : ""}" data-prov="${p.id}">
                <div class="mp-prov-l">${esc(p.label)}</div>
                <div class="mp-prov-c">${esc(p.id)}${p.id === main.provider ? " · ĐANG DÙNG" : ""}${esc(tagFor(p.id))}${p.configured ? "" : " · " + WARN_ICON + " cần kết nối"}</div>
              </button>`).join("")}</div>
            <div class="mp-models">${models.length ? models.map(mod => `
              <button class="mp-model ${mod === selModel ? "sel" : ""}" data-mod="${esc(mod)}">${esc(mod)}${(selProv === main.provider && mod === main.model) ? ' <span class="mp-cur">ĐANG DÙNG</span>' : ""}</button>`).join("")
                : (loadingProv === selProv ? '<div class="mp-empty">Đang tải model…</div>'
                    : '<div class="mp-empty">' + esc((liveCache[selProv] && liveCache[selProv].error)
                        || "Provider chưa kết nối hoặc không có model. Kết nối ở Providers (hoặc thêm vào settings.json → model.catalog).") + '</div>')}</div>
          </div>
          <div class="mp-foot">
            <span class="mp-note">${esc(opts.note || "Model load động theo provider · lưu cho phiên mới")}</span>
            <div><button class="mp-btn" data-act="close">Huỷ</button><button class="mp-btn primary" data-act="switch" ${selModel ? "" : "disabled"}>${esc(opts.title ? "Chọn" : "Switch")}</button></div>
          </div>
        </div>`;
      modal.querySelectorAll(".mp-prov").forEach(b => b.onclick = () => {
        selProv = b.dataset.prov;
        const ms = modelsFor(selProv);
        selModel = (selProv === main.provider && ms.indexOf(main.model) >= 0) ? main.model : (liveCache[selProv] ? (ms[0] || null) : null);
        ensureModels(selProv);
      });
      modal.querySelectorAll(".mp-model").forEach(b => b.onclick = () => { selModel = b.dataset.mod; draw(); });
      modal.querySelectorAll('[data-act="close"]').forEach(b => b.onclick = () => modal.classList.remove("open"));
      const applyFilter = () => {
        const q = filterQ.toLowerCase();
        modal.querySelectorAll(".mp-prov,.mp-model").forEach(x => { x.style.display = (!q || x.textContent.toLowerCase().includes(q)) ? "" : "none"; });
      };
      modal.querySelector(".mp-filter").oninput = (e) => { filterQ = e.target.value || ""; applyFilter(); };
      applyFilter();   // đổi provider xong vẫn giữ nguyên chữ đang lọc, khỏi gõ lại
      const sw = modal.querySelector('[data-act="switch"]');
      if (sw) sw.onclick = async () => {
        if (!selModel) return;
        sw.disabled = true; sw.textContent = "Đang lưu...";
        await SAVE(selProv, selModel);
        modal.classList.remove("open");
        if (onDone) onDone();
      };
    };
    ensureModels(selProv);
    modal.classList.add("open");
  }

  // ---- Trang MCP - quản lý server công cụ ngoài cho engine Claude Code ----
  async function postJson(url, obj, timeoutMs) {
    // Hạn chờ: request treo (vd server bận vòng lặp sự kiện) phải nổi lên thành lỗi đọc
    // được, chứ không để nút bấm chìm mãi. 0 = không giới hạn (giữ hành vi cũ cho chỗ khác).
    const ctl = timeoutMs ? new AbortController() : null;
    const timer = ctl ? setTimeout(() => ctl.abort(), timeoutMs) : null;
    try {
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                   body: JSON.stringify(obj || {}), signal: ctl ? ctl.signal : undefined });
      return await r.json();
    } catch (e) {
      return { ok: false, error: (ctl && e && e.name === "AbortError")
        ? "Máy chủ không phản hồi sau " + Math.round(timeoutMs / 1000) + "s. Thử lại giúp em."
        : String(e) };
    } finally { if (timer) clearTimeout(timer); }
  }
  function parseKV(text, sep) {
    const o = {};
    (text || "").split("\n").forEach(line => {
      line = line.trim(); if (!line) return;
      let i = line.indexOf(sep); if (i < 0 && sep === ":") i = line.indexOf("=");
      if (i < 0) return;
      const k = line.slice(0, i).trim(), v = line.slice(i + 1).trim();
      if (k) o[k] = v;
    });
    return o;
  }
  // ==== Trang Kết nối: kho connector + đa tài khoản (qua MCP hub) ====
  const PERM_META = {
    readonly: { label: "Chỉ đọc", color: "var(--link-ink)" },
    safe: { label: "Ghi nháp", color: "var(--warn-ink)" },
    full: { label: "Toàn quyền", color: "var(--red)" },
  };
  // Nhãn cách đăng nhập bằng tiếng người - dân thường không cần biết OAuth là gì
  // "none" = connector KHÔNG cần thông tin đăng nhập nào (vd Shopify: endpoint công khai,
  // chỉ cần biết địa chỉ cửa hàng). Nhãn phải nói đúng chuyện đó, đừng để user đi tìm key.
  const AUTH_BADGE = { apikey: "Dán key", qr: "Quét QR", oauth: "Đăng nhập tài khoản", none: "Không cần key" };
  let _connPoll = null;

  function closeConnModal() {
    const m = document.getElementById("connectModal");
    if (m) m.classList.remove("open");
    if (_connPoll) { clearInterval(_connPoll); _connPoll = null; }
  }
  function connModal(html, maxw) {
    let m = document.getElementById("connectModal");
    if (!m) { m = document.createElement("div"); m.id = "connectModal"; m.className = "mp-overlay"; document.body.appendChild(m); }
    m.innerHTML = '<div class="mp-box" style="max-width:' + (maxw || 520) + 'px">' + html + '</div>';
    m.classList.add("open");
    m.querySelectorAll('[data-act="close"]').forEach(b => b.onclick = closeConnModal);
    return m;
  }
  function mHead(title) {
    return '<div class="mp-head"><div class="mp-title">' + title + '</div><button class="mp-x" data-act="close">' + X_ICON + '</button></div>';
  }
  function permChip(p) {
    const m = PERM_META[p] || PERM_META.full;
    return '<span class="perm-chip" style="color:' + m.color + ';border-color:' + m.color + '55">' + m.label + '</span>';
  }
  function iconInner(con) {
    // Trường icon của connector có 3 dạng, xử lý theo thứ tự:
    //   URL/đường dẫn ảnh (logo hãng) → <img>
    //   tên icon Lucide               → dựng SVG
    //   thứ khác                      → in thẳng
    // Nhánh cuối để giữ catalog TỰ THÊM của người dùng vẫn hiện được: nếu họ
    // để emoji thì cứ hiện emoji, đừng biến thành dấu hỏi.
    const src = (con && con.icon) || "plug";
    if (/^(https?:|\/)/.test(src)) {
      return '<img class="ico-img" src="' + esc(src) + '" alt="" loading="lazy">';
    }
    return Icons.has(src) ? ic(src) : esc(src);
  }
  function connChip(c) {
    return '<button class="conn-chip' + (c.enabled ? "" : " off") + '" data-conn="' + c.id + '">'
      + '<span class="cdot' + (c.enabled ? " on" : "") + '">●</span> ' + esc(c.label || c.name || "?")
      + (c.is_default ? ' <span class="cstar">' + ic("star", { cls: "ic-fill" }) + '</span>' : "") + " " + permChip(c.perm) + '</button>';
  }

  // ── Sức khoẻ kết nối (khối A): tô chấm màu chip theo /connect/health + nút Kết nối lại ──
  let _healthTimer = null;
  async function refreshConnHealth(el, conns, byId) {
    if (!document.body.contains(el)) { clearInterval(_healthTimer); _healthTimer = null; return; }
    let h = {};
    try { h = (await (await fetch("/connect/health")).json()).health || {}; } catch (e) { return; }
    el.querySelectorAll(".conn-chip[data-conn]").forEach(chip => {
      const dot = chip.querySelector(".cdot");
      if (!dot) return;
      if (chip.classList.contains("off")) { chip.title = "Đang tắt tạm"; return; }
      const rec = h[chip.dataset.conn];
      dot.classList.remove("hok", "herr", "hunk");
      if (!rec) { dot.classList.add("hunk"); chip.title = "Chưa kiểm tra - vòng check nền sẽ tự chạy"; return; }
      const when = rec.checked_at ? " · kiểm tra " + zlAgo(rec.checked_at) : "";
      if (rec.ok) {
        dot.classList.add("hok");
        chip.title = "Hoạt động bình thường (" + (rec.tools || 0) + " công cụ)" + when;
      } else {
        dot.classList.add("herr");
        chip.title = (rec.message || "Lỗi") + when;
      }
    });
    // Connection chết vì HẾT PHIÊN ĐĂNG NHẬP → nút sửa ngay trên card, khỏi mò vào menu
    el.querySelectorAll(".conn-fix").forEach(b => b.remove());
    (conns || []).forEach(c => {
      const rec = h[c.id];
      if (!rec || rec.ok || rec.kind !== "auth" || !c.enabled) return;
      const chip = el.querySelector('.conn-chip[data-conn="' + c.id + '"]');
      if (!chip) return;
      const fix = document.createElement("button");
      fix.className = "conn-chip conn-fix";
      fix.innerHTML = ic("repeat") + " Kết nối lại " + esc(c.label || "");
      fix.onclick = () => reconnectAccount(el, c, byId[c.connector_id]);
      chip.after(fix);
    });
  }

  // Kết nối lại GIỮ NGUYÊN connection (id, label, quyền, deny) - không xoá tạo lại.
  function reconnectAccount(el, c, con) {
    if ((c.auth || "") === "oauth" || (con && con.auth_type === "oauth")) {
      postJson("/connect/oauth/start", { id: c.id }).then(r => {
        if (!r || r.ok === false) { alert("Không mở được đăng nhập: " + ((r && r.error) || "lỗi")); return; }
        window.open(r.url, "_blank");
      });
      return;
    }
    openReKey(el, c, con);
  }
  function openReKey(el, c, con) {
    const flds = (con && con.fields) || [];
    const rows = flds.map(f =>
      '<label class="mcp-lb">' + esc(f.label || f.key)
      + '<input class="js-input" data-rk="' + esc(f.key) + '" placeholder="Để trống = giữ giá trị cũ"'
      + ((/secret|password|token|key/i.test(f.key)) ? ' type="password"' : "") + '></label>').join("");
    const m = connModal(mHead("KẾT NỐI LẠI: " + esc(c.label || ""))
      + '<div class="conn-form"><div class="mp-note">Dán key/thông tin MỚI cho tài khoản này. Ô để trống sẽ giữ nguyên giá trị cũ.</div>'
      + (rows || '<div class="mp-note">Kết nối này không có trường key để thay - dùng menu Test để kiểm tra.</div>')
      + '<div class="mp-note" id="rkErr" style="color:var(--red)"></div></div>'
      + '<div class="mp-foot"><button class="mp-btn" data-act="close">Huỷ</button>'
      + (rows ? '<button class="mp-btn primary" id="rkGo">Lưu và kiểm tra</button>' : "") + '</div>');
    const go = m.querySelector("#rkGo");
    if (go) go.onclick = async () => {
      const fields = {};
      m.querySelectorAll("[data-rk]").forEach(i => { if (i.value.trim()) fields[i.dataset.rk] = i.value.trim(); });
      if (!Object.keys(fields).length) { m.querySelector("#rkErr").textContent = "Chưa nhập giá trị mới nào."; return; }
      go.disabled = true; go.textContent = "Đang kiểm tra…";
      await postJson("/connect/update", { id: c.id, fields: fields });
      const r = await postJson("/connect/health/check", { id: c.id });
      if (r && r.ok) { closeConnModal(); renderConnect(el); return; }
      go.disabled = false; go.textContent = "Lưu và kiểm tra";
      m.querySelector("#rkErr").innerHTML = Icons.warn((r && r.message) || "Vẫn chưa kết nối được.");
    };
  }
  function connectorCard(con, conns) {
    const chips = conns.map(connChip).join("")
      + '<button class="conn-chip add" data-addacc="' + esc(con.id) + '">＋ Thêm tài khoản</button>';
    return '<div class="prov-card conn-card">'
      + '<div class="prov-head"><span class="conn-ico">' + iconInner(con) + '</span>'
      + '<div class="prov-info"><div class="prov-name">' + esc(con.name || con.id) + '</div>'
      + '<div class="prov-status">' + esc(con.description || "") + '</div>'
      + (con.guide_url ? '<a class="cat-doc" href="' + esc(safeHref(con.guide_url))
          + '" target="_blank" rel="noopener">Hướng dẫn trên GitHub ↗</a>' : "")
      + '</div></div>'
      + '<div class="conn-accounts">' + chips + '</div>'
      + '</div>';
  }

  // ── Nhóm connector (khối B): mọi dịch vụ Google gom về MỘT card, bấm vào chọn dịch vụ ──
  const GROUP_META = {
    google: { name: "Google", icon: '<span class="gico">G</span>', category: "Văn phòng",
              desc: "Lịch, Gmail, Tasks, Drive/Docs, Sheets, Keep - chọn dịch vụ cần đấu, các dịch vụ dùng chung được một key đăng nhập." },
  };
  function catSolo(cat) { return cat.filter(c => !c.group); }
  function groupCards(cat, conns) {
    const byGroup = {};
    cat.forEach(c => { if (c.group) (byGroup[c.group] = byGroup[c.group] || []).push(c); });
    return Object.keys(byGroup).map(g => {
      const meta = GROUP_META[g] || { name: g, icon: ic("plug"), category: "Khác", desc: "" };
      const ids = byGroup[g].map(c => c.id);
      const nConn = (conns || []).filter(x => ids.includes(x.connector_id)).length;
      return '<div class="cat-card" data-cat="' + esc(meta.category) + '">'
        + '<div class="cat-ico">' + meta.icon + '</div>'
        + '<div class="cat-name">' + esc(meta.name) + ' <span class="prov-kind">' + byGroup[g].length + ' dịch vụ</span>'
        + (nConn ? ' <span class="prov-kind" style="color:var(--green)">đã nối ' + nConn + '</span>' : "") + '</div>'
        + '<div class="cat-desc">' + esc(meta.desc) + '</div>'
        + '<button class="gcard-btn" data-groupopen="' + esc(g) + '">Chọn dịch vụ</button>'
        + '</div>';
    }).join("");
  }
  function openGroupPicker(el, g, items, ctx, isFirst) {
    const meta = GROUP_META[g] || { name: g };
    const rows = items.map(c => {
      const acc = (ctx.conns || []).filter(x => x.connector_id === c.id);
      const badge = c.auth_type === "oauth" ? "Đăng nhập " + esc(meta.name)
        : (c.auth_type === "qr" ? "Quét QR" : "Dán key");
      const short = (c.name || c.id).replace(/^Google\s+/, "");
      return '<button class="conn-menu-btn gp-row" data-gp="' + esc(c.id) + '">'
        + '<span class="gp-ico">' + iconInner(c) + '</span>'
        + '<span class="gp-main"><span class="gp-name">' + esc(short)
        + (c.status === "beta" ? ' <span class="prov-kind" style="color:var(--warn-ink)">beta</span>' : "")
        + (acc.length ? ' <span class="prov-kind" style="color:var(--green)">đã nối ' + acc.length + '</span>' : "")
        + '</span><span class="mp-note">' + esc(c.group_line || c.description || "") + '</span></span>'
        + '<span class="prov-kind">' + badge + '</span></button>';
    }).join("");
    const m = connModal(mHead(esc(meta.name.toUpperCase()) + " - CHỌN DỊCH VỤ")
      + '<div class="conn-menu">' + rows + '</div>'
      + '<div class="mp-foot"><span class="mp-note">Tạo key một lần, các dịch vụ sau bấm "Dùng lại key" là xong.</span>'
      + '<button class="mp-btn" data-act="close">Đóng</button></div>', 560);
    m.querySelectorAll("[data-gp]").forEach(b => b.onclick = () => {
      const con = items.find(x => x.id === b.dataset.gp);
      closeConnModal();
      openAddFlow(el, con, isFirst, ctx);
    });
  }

  function catalogCard(con) {
    const soon = con.status === "soon";
    const badge = '<span class="prov-kind">' + (AUTH_BADGE[con.auth_type] || con.auth_type || "") + '</span>'
      + (con.status === "beta" ? ' <span class="prov-kind" style="color:var(--warn-ink)">beta</span>' : "")
      + (soon ? ' <span class="prov-kind">sắp có</span>' : "");
    return '<div class="cat-card' + (soon ? " soon" : "") + '" data-cat="' + esc(con.category || "Khác") + '">'
      + '<div class="cat-ico">' + iconInner(con) + '</div>'
      + '<div class="cat-name">' + esc(con.name) + ' ' + badge + '</div>'
      + '<div class="cat-desc">' + esc(con.description || "") + '</div>'
      + (soon
        ? '<button class="gcard-btn" disabled style="opacity:.5">Sắp có</button>'
          + (con.guide_url ? ' <a class="cat-doc" href="' + esc(con.guide_url) + '" target="_blank">docs ↗</a>' : "")
        : '<button class="gcard-btn" data-connect="' + esc(con.id) + '">Kết nối</button>'
          + (con.guide_url ? ' <a class="cat-doc" href="' + esc(safeHref(con.guide_url))
              + '" target="_blank" rel="noopener">Hướng dẫn ↗</a>' : ""))
      + '</div>';
  }

  function openAddFlow(el, con, isFirst, ctx) {
    if (!con) return;
    if (con.id === "custom") return openMcpForm(el);
    if (con.auth_type === "qr") return openQrFlow(el, con, isFirst);
    if (con.auth_type === "oauth") return openOauthFlow(el, con, ctx);
    openApikeyFlow(el, con, isFirst, ctx);
  }

  // Ô đăng nhập của connector. `default` điền SẴN vào ô: có connector đòi một giá trị kỹ
  // thuật mà người thường không thể tự biết (vd URL hồ sơ agent UCP của Shopify) - để trống
  // thì họ đứng hình, mà ghi cứng trong code thì hết đổi được. Điền sẵn + cho sửa là vừa.
  function fieldsHtml(con, rows) {
    return (con.fields || []).map(f =>
      '<label class="mcp-lb">' + esc(f.label || f.key)
      + (f.multiline
        ? '<textarea class="js-input" data-f="' + esc(f.key) + '" rows="' + rows + '" placeholder="' + esc(f.placeholder || "") + '">' + esc(f.default || "") + '</textarea>'
        : '<input class="js-input" data-f="' + esc(f.key) + '" placeholder="' + esc(f.placeholder || "") + '" value="' + esc(f.default || "") + '">')
      + '</label>').join("");
  }

  function openApikeyFlow(el, con, isFirst, ctx) {
    const hasSteps = con.steps && con.steps.length;
    const fields = fieldsHtml(con, 5);
    const m = connModal(mHead("KẾT NỐI " + esc((con.name || "").toUpperCase()))
      + '<div class="conn-form">'
      // Cảnh báo rủi ro phải hiện NGAY LÚC QUYẾT ĐỊNH, không đợi tới hộp thoại đổi quyền.
      + (con.risk ? '<div class="conn-risk">' + WARN_ICON + ' ' + esc(con.risk) + '</div>' : "")
      // Có steps thì wizard từng bước THAY guide tường chữ (guide giữ làm fallback catalog cũ)
      + (hasSteps ? stepsHtml(con)
        : (con.guide ? '<div class="conn-guide">' + esc(con.guide) + (con.guide_url ? ' <a href="' + esc(con.guide_url) + '" target="_blank">Hướng dẫn ↗</a>' : "") + '</div>' : ""))
      + oauthWizard(con)   // nút mở trang ngoài (vd "Tạo App Password") khi catalog khai auth.setup.links
      + reuseHtml(reuseDonors(con, ctx))
      + jsonDropHtml(con)
      + fields
      + '<label class="mcp-lb">Tên gợi nhớ (tuỳ chọn - bỏ trống sẽ tự lấy tên tài khoản/shop)<input class="js-input" id="cLabel"></label>'
      + '</div>'
      + '<div class="mp-foot"><span class="mp-note" id="cErr"></span><div><button class="mp-btn" data-act="close">Huỷ</button><button class="mp-btn primary" id="cGo">Kết nối</button></div></div>');
    wireWizCommon(m); wireJsonDrop(m); wireReuse(m);
    m.querySelector("#cGo").onclick = async () => {
      const fieldsVal = {};
      m.querySelectorAll("[data-f]").forEach(inp => { fieldsVal[inp.dataset.f] = inp.value.trim(); });
      const missing = missingField(m, con);
      const err = m.querySelector("#cErr"), go = m.querySelector("#cGo");
      if (missing) { err.textContent = "Thiếu: " + missing; return; }
      go.disabled = true; go.textContent = "Đang kiểm tra key…"; err.textContent = "";
      const r = await postJson("/connect/add", { connector_id: con.id, fields: fieldsVal,
        label: m.querySelector("#cLabel").value.trim(), reuse_from: m._reuseFrom || "",
        force: !!m._forceAdd });
      if (!r.ok) {
        err.textContent = r.error || "Lỗi";
        // can_force = server chặn có lý do (vd connector cần trình duyệt trên máy chạy Javis
        // mà đang mở qua domain public - issue #112). Bấm lần nữa là xác nhận vẫn muốn đấu.
        if (r.can_force) { m._forceAdd = true; go.textContent = "Tôi hiểu, vẫn kết nối"; }
        else { go.textContent = "Kết nối"; }
        go.disabled = false; return;
      }
      m.querySelector(".conn-form").innerHTML = '<div class="conn-ok">' + CHECK_ICON + ' Đã kết nối: <b>' + esc(r.label || con.name) + '</b> (' + (r.tools || 0) + ' công cụ)'
        + (isFirst ? '<div class="conn-hint">Sang trang Javis hỏi thử: "Hôm nay bán được bao nhiêu?"</div>' : "") + '</div>';
      go.style.display = "none";
      setTimeout(() => { closeConnModal(); renderConnect(el); }, 1600);
    };
  }

  function openQrFlow(el, con, isFirst) {
    const risk = con.risk ? '<div class="conn-risk">' + WARN_ICON + ' ' + esc(con.risk) + '</div>' : "";
    const guide = con.guide
      ? '<div class="conn-guide">' + esc(con.guide)
        + (con.guide_url ? ' <a href="' + esc(safeHref(con.guide_url))
          + '" target="_blank" rel="noopener">Xem hướng dẫn đầy đủ trên GitHub ↗</a>' : "")
        + '</div>'
      : "";
    const m = connModal(mHead("KẾT NỐI " + esc((con.name || "").toUpperCase()))
      + '<div class="conn-form">' + risk + guide
      + '<label class="mcp-lb">Tên gợi nhớ (tuỳ chọn)<input class="js-input" id="qLabel"></label>'
      + '<button class="mp-btn primary" id="qGo">' + (con.risk ? "Tôi hiểu rủi ro, hiện mã QR" : "Hiện mã QR") + '</button>'
      + '<div id="qrZone"></div></div>'
      + '<div class="mp-foot"><span class="mp-note" id="qErr"></span><button class="mp-btn" data-act="close">Đóng</button></div>');
    m.querySelector("#qGo").onclick = async () => {
      const err = m.querySelector("#qErr");
      err.textContent = "";
      const r = await postJson("/connect/zalo/start", { label: m.querySelector("#qLabel").value.trim() });
      if (!r.ok) { err.textContent = r.error || "Lỗi"; return; }
      m.querySelector("#qGo").style.display = "none";
      const zone = m.querySelector("#qrZone");
      zone.innerHTML = '<div class="mp-note" style="margin-top:8px">Đang khởi động… (lần đầu hơi lâu do phải tải công cụ)</div>';
      _connPoll = setInterval(async () => {
        let st;
        try { st = await (await fetch("/connect/zalo/status?sid=" + encodeURIComponent(r.sid))).json(); } catch (e) { return; }
        if (st.state === "qr" && st.qr) {
          zone.innerHTML = '<img class="qr-img" src="' + st.qr + '"><div class="mp-note">Mở Zalo trên điện thoại > biểu tượng QR góc trên > quét mã này</div>';
        } else if (st.state === "done") {
          clearInterval(_connPoll); _connPoll = null;
          zone.innerHTML = '<div class="conn-ok">' + CHECK_ICON + ' Đã đăng nhập: <b>' + esc(st.label || "Zalo") + '</b>'
            + (isFirst ? '<div class="conn-hint">Sang trang Javis nhắn thử: "Đọc tin nhắn Zalo mới nhất"</div>' : "") + '</div>';
          setTimeout(() => { closeConnModal(); renderConnect(el); }, 1800);
        } else if (st.state === "error") {
          clearInterval(_connPoll); _connPoll = null;
          zone.innerHTML = "";
          err.textContent = st.error || "Lỗi đăng nhập";
          m.querySelector("#qGo").style.display = "";
        }
      }, 1500);
    };
  }

  // Wizard cài đặt cho connector tự-tạo-app (Facebook/Meta): nút mở thẳng trang Developer
  // + ô Redirect URI kèm nút sao chép. Chỉ hiện khi connector khai auth.setup trong catalog.
  function oauthWizard(con) {
    // Có steps (wizard từng bước) thì steps thay hẳn khối setup links cũ
    if (con.steps && con.steps.length) return "";
    const s = con.setup || {};
    const hasLinks = Array.isArray(s.links) && s.links.length;
    if (!hasLinks && !s.redirect) return "";
    let h = '<div class="conn-wizard">';
    if (hasLinks) {
      h += '<div class="wiz-links">' + s.links.map(l =>
        '<button type="button" class="mp-btn wiz-open" data-url="' + esc(l.url) + '">' + esc(l.label) + ' ↗</button>'
      ).join("") + '</div>';
    }
    if (s.redirect) {
      h += '<label class="mcp-lb">Redirect URI - dán vào ô "URI chuyển hướng OAuth hợp lệ" (menu trái: Đăng nhập bằng Facebook &gt; Cài đặt)'
        + '<div class="wiz-copy"><input class="js-input" id="wizRedirect" readonly value="' + esc(_redirectUri()) + '">'
        + '<button type="button" class="mp-btn wiz-copy-btn" id="wizCopy">Sao chép</button></div></label>';
    }
    return h + '</div>';
  }

  // ── Khối B: wizard từng bước + kéo thả JSON + dùng lại key (nhóm Google) ──
  function _redirectUri() {
    // Theo ĐÚNG địa chỉ đang mở: VPS có tên miền thì ra https://<tên-miền>/... (trước đây
    // ghi cứng localhost nên người chạy Hostinger dán vào là hỏng). Riêng 127.0.0.1 ép về
    // localhost vì Meta chỉ miễn HTTP cho host 'localhost'.
    return location.origin.replace("://127.0.0.1", "://localhost") + "/connect/oauth/callback";
  }
  function redirectCopyBox() {
    const uri = _redirectUri();
    return '<div class="wiz-copy"><input class="js-input" readonly value="' + esc(uri) + '">'
      + '<button type="button" class="mp-btn wiz-copy-btn">Sao chép</button></div>';
  }
  // Ô sao chép TÊN MIỀN trần (không https, không /) - cho ô "Miền ứng dụng"
  // (App Domains) của Facebook. Cũng động theo địa chỉ đang mở như redirect.
  function domainCopyBox() {
    const host = location.hostname === "127.0.0.1" ? "localhost" : location.hostname;
    return '<div class="wiz-copy"><input class="js-input" readonly value="' + esc(host) + '">'
      + '<button type="button" class="mp-btn wiz-copy-btn">Sao chép</button></div>';
  }
  function stepsHtml(con) {
    const st = con.steps || [];
    if (!st.length) return "";
    return '<ol class="conn-steps">' + st.map(s =>
      '<li>' + esc(s.text)
      + (s.link ? ' <button type="button" class="mp-btn wiz-open step-link" data-url="' + esc(s.link) + '">' + esc(s.link_label || "Mở trang") + ' ↗</button>' : "")
      + (s.copy === "redirect" ? redirectCopyBox() : s.copy === "domain" ? domainCopyBox() : "")
      + '</li>').join("") + '</ol>';
  }
  function wireWizCommon(m) {
    m.querySelectorAll(".wiz-open").forEach(b => { b.onclick = () => window.open(b.dataset.url, "_blank", "noopener"); });
    m.querySelectorAll(".wiz-copy-btn").forEach(btn => btn.onclick = async () => {
      const inp = btn.parentElement.querySelector("input");
      if (!inp) return;
      try { await navigator.clipboard.writeText(inp.value); }
      catch (e) { inp.select(); try { document.execCommand("copy"); } catch (_) {} }
      btn.innerHTML = "Đã chép " + CHECK_ICON;
      setTimeout(() => { btn.textContent = "Sao chép"; }, 1400);
    });
  }
  function hasClientFields(con) {
    const ks = (con.fields || []).map(f => f.key);
    return ks.includes("client_id") && ks.includes("client_secret");
  }
  function jsonDropHtml(con) {
    // CHỈ nhóm Google: Facebook/Meta cũng đặt tên field client_id/client_secret (nhãn App ID)
    // nhưng không hề có file JSON để tải - từng mọc nhầm ô "tải từ Google" sang form Facebook.
    if (!hasClientFields(con) || con.group !== "google") return "";
    return '<div class="json-drop" id="jsonDrop"><span id="jdMsg">' + ic("file-code") + ' Kéo thả file JSON client tải từ Google vào đây (hoặc bấm chọn file) - tự điền Client ID + Secret</span>'
      + '<input type="file" accept=".json,application/json" style="display:none"></div>';
  }
  function wireJsonDrop(m) {
    const z = m.querySelector("#jsonDrop");
    if (!z) return;
    const file = z.querySelector('input[type="file"]');
    const msg = z.querySelector("#jdMsg");
    const fill = (txt) => {
      let c = null;
      try { const d = JSON.parse(txt); c = d.web || d.installed || d; } catch (e) {}
      if (!c || !c.client_id) {
        z.classList.remove("ok"); z.classList.add("bad");
        msg.innerHTML = WARN_ICON + " File này không phải JSON client của Google - tải đúng file từ trang Credentials.";
        return;
      }
      const idI = m.querySelector('[data-f="client_id"]'), scI = m.querySelector('[data-f="client_secret"]');
      if (idI) idI.value = c.client_id || "";
      if (scI) scI.value = c.client_secret || "";
      z.classList.remove("bad"); z.classList.add("ok");
      msg.innerHTML = CHECK_ICON + " Đã điền key từ file (" + (c.client_id || "").slice(0, 28) + "…)"
        + (c.client_secret ? "" : " - file thiếu client_secret, dán tay ô Secret");
    };
    z.onclick = () => file.click();
    file.onchange = () => { if (file.files[0]) file.files[0].text().then(fill); };
    z.ondragover = (e) => { e.preventDefault(); z.classList.add("over"); };
    z.ondragleave = () => z.classList.remove("over");
    z.ondrop = (e) => {
      e.preventDefault(); z.classList.remove("over");
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) f.text().then(fill);
    };
  }
  function reuseDonors(con, ctx) {
    if (!ctx || !con.group || !hasClientFields(con)) return [];
    return (ctx.conns || []).filter(x => {
      const cc = (ctx.byId || {})[x.connector_id] || {};
      return cc.group === con.group && hasClientFields(cc);
    });
  }
  function reuseHtml(donors) {
    if (!donors.length) return "";
    return '<div class="reuse-row"><span class="mp-note">Đã có key Google ở tài khoản khác - dùng lại, khỏi tạo mới:</span>'
      + '<select class="js-input" id="reuseSel">' + donors.map(d =>
        '<option value="' + esc(d.id) + '">' + esc(d.label || d.id) + '</option>').join("") + '</select>'
      + '<button type="button" class="mp-btn" id="reuseBtn">Dùng lại key này</button></div>';
  }
  function wireReuse(m) {
    const btn = m.querySelector("#reuseBtn");
    if (!btn) return;
    btn.onclick = () => {
      m._reuseFrom = m.querySelector("#reuseSel").value;
      ["client_id", "client_secret"].forEach(k => {
        const i = m.querySelector('[data-f="' + k + '"]');
        if (i) { i.value = ""; i.placeholder = "Dùng lại key của tài khoản đã chọn"; i.disabled = true; }
      });
      btn.innerHTML = CHECK_ICON + " Sẽ dùng lại key"; btn.disabled = true;
    };
  }
  // Field client_id/secret coi như ĐÃ CÓ khi user chọn dùng lại key
  function missingField(m, con) {
    let missing = "";
    m.querySelectorAll("[data-f]").forEach(inp => {
      const k = inp.dataset.f, v = inp.value.trim();
      const fd = (con.fields || []).find(x => x.key === k) || {};
      const reused = m._reuseFrom && (k === "client_id" || k === "client_secret");
      if (!v && !fd.optional && !reused) missing = fd.label || k;
    });
    return missing;
  }

  function openOauthFlow(el, con, ctx) {
    // Provider không tự đăng ký client (vd Google) khai sẵn fields client_id/secret user tự tạo.
    // Có ô multiline (vd google-ads cho dán sẵn file ADC làm đường lui) nên render y như luồng
    // apikey, đừng ép hết thành input 1 dòng.
    const hasSteps = con.steps && con.steps.length;
    const fields = fieldsHtml(con, 4);
    const m = connModal(mHead("KẾT NỐI " + esc((con.name || "").toUpperCase()))
      + '<div class="conn-form">'
      // Cảnh báo rủi ro phải hiện NGAY LÚC QUYẾT ĐỊNH, không đợi tới hộp thoại đổi quyền.
      + (con.risk ? '<div class="conn-risk">' + WARN_ICON + ' ' + esc(con.risk) + '</div>' : "")
      + (hasSteps ? stepsHtml(con)
        : '<div class="conn-guide">' + esc(con.guide || "Đăng nhập bằng tài khoản của nhà cung cấp.")
          + (con.guide_url ? ' <a href="' + esc(con.guide_url) + '" target="_blank">Hướng dẫn ↗</a>' : "") + '</div>')
      + oauthWizard(con)
      + reuseHtml(reuseDonors(con, ctx))
      + jsonDropHtml(con)
      + fields
      + '<button class="mp-btn primary" id="oGo">' + (fields ? "Lưu & mở trang đăng nhập" : "Mở trang đăng nhập") + '</button></div>'
      + '<div class="mp-foot"><span class="mp-note" id="oErr"></span><button class="mp-btn" data-act="close">Đóng</button></div>');
    wireWizCommon(m); wireJsonDrop(m); wireReuse(m);
    m.querySelector("#oGo").onclick = async () => {
      const err = m.querySelector("#oErr"), go = m.querySelector("#oGo");
      const fieldsVal = {};
      m.querySelectorAll("[data-f]").forEach(inp => { fieldsVal[inp.dataset.f] = inp.value.trim(); });
      const missing = missingField(m, con);
      if (missing) { err.textContent = "Thiếu: " + missing; return; }
      go.disabled = true; err.textContent = "";
      const r = await postJson("/connect/oauth/start", { connector_id: con.id, fields: fieldsVal,
        reuse_from: m._reuseFrom || "" });
      go.disabled = false;
      if (!r.ok) { err.textContent = r.error || "Lỗi"; return; }
      window.open(r.url, "_blank");
      err.textContent = "Hoàn tất đăng nhập ở tab mới, xong quay lại bấm Làm mới trang này.";
    };
  }

  function openPermPicker(el, c, con) {
    const DESC = { readonly: "chỉ xem số liệu, không đụng dữ liệu thật", safe: "được ghi nháp, CHẶN hành động tiền/đơn/gửi tin", full: "thao tác THẬT: tạo đơn, gửi tin, publish…" };
    const opts = ["readonly", "safe", "full"].map(p =>
      '<button class="conn-menu-btn" data-p="' + p + '">' + permChip(p) + ' <span class="mp-note">' + DESC[p] + '</span></button>').join("");
    const m = connModal(mHead("QUYỀN: " + esc(c.label || "")) + '<div class="conn-menu">' + opts + '</div>'
      + '<div class="mp-foot"><button class="mp-btn" data-act="close">Huỷ</button></div>');
    m.querySelectorAll("[data-p]").forEach(b => b.onclick = async () => {
      const p = b.dataset.p;
      if (p === "full") return openFullAck(el, c, con);
      await postJson("/connect/update", { id: c.id, perm: p });
      closeConnModal(); renderConnect(el);
    });
  }
  function openFullAck(el, c, con) {
    const text = (con && con.risk) ? con.risk
      : "Mức này cho phép Javis thao tác THẬT ra ngoài qua kết nối này: tạo đơn, gửi tin, chạy quảng cáo, publish… Hành động có thể KHÔNG hoàn tác được.";
    const m = connModal(mHead(WARN_ICON + " BẬT TOÀN QUYỀN")
      + '<div class="conn-form"><div class="conn-risk">' + esc(text) + '</div>'
      + '<label style="display:flex;gap:8px;align-items:center;cursor:pointer;font-size:14px"><input type="checkbox" id="ackChk"> Tôi hiểu rủi ro và tự chịu trách nhiệm</label></div>'
      + '<div class="mp-foot"><button class="mp-btn" data-act="close">Huỷ</button><button class="mp-btn primary" id="ackGo" disabled>Bật Toàn quyền</button></div>');
    m.querySelector("#ackChk").onchange = (e) => { m.querySelector("#ackGo").disabled = !e.target.checked; };
    m.querySelector("#ackGo").onclick = async () => {
      await postJson("/connect/update", { id: c.id, perm: "full" });
      closeConnModal(); renderConnect(el);
    };
  }

  function openAccountMenu(el, c, con) {
    const m = connModal(mHead(esc(c.label || "Tài khoản"))
      + '<div class="conn-menu">'
      + '<button class="conn-menu-btn" data-m="test">' + ic("rotate-cw") + ' Test kết nối</button>'
      + '<button class="conn-menu-btn" data-m="rekey">' + ic("repeat") + ' Kết nối lại (đăng nhập / đổi key)</button>'
      + '<button class="conn-menu-btn" data-m="default"' + (c.is_default ? " disabled" : "") + '>' + ic("star") + ' Đặt làm mặc định</button>'
      + '<button class="conn-menu-btn" data-m="rename">' + ic("pencil") + ' Đổi tên</button>'
      + '<button class="conn-menu-btn" data-m="perm">' + ic("shield") + ' Đổi quyền (' + ((PERM_META[c.perm] || {}).label || c.perm) + ')</button>'
      + '<button class="conn-menu-btn" data-m="deny">' + ic("ban") + ' Chặn tool cụ thể' + ((c.deny_tools || []).length ? " (" + c.deny_tools.length + ")" : "") + '</button>'
      + (con && con.cred_dir ? '<button class="conn-menu-btn" data-m="relogin">' + ic("key")
          + ' Đăng nhập lại Google (xoá quyền cũ)</button>' : "")
      + '<button class="conn-menu-btn" data-m="audit">' + ic("scroll") + ' Nhật ký gọi tool</button>'
      + '<button class="conn-menu-btn" data-m="toggle">' + (c.enabled ? "○ Tắt tạm" : "● Bật lại") + '</button>'
      + '<button class="conn-menu-btn danger" data-m="del">' + ic("trash-2") + ' Xoá kết nối</button>'
      + '</div><div class="mp-foot"><span class="mp-note" id="cmNote"></span><button class="mp-btn" data-act="close">Đóng</button></div>');
    const note = m.querySelector("#cmNote");
    m.querySelectorAll("[data-m]").forEach(b => b.onclick = async () => {
      const act = b.dataset.m;
      if (act === "test") {
        note.textContent = "Đang test…";
        const r = await postJson("/connect/test", { id: c.id });
        note.innerHTML = r.ok ? CHECK_ICON + " OK - " + (r.tools || 0) + " công cụ" + (r.label ? " (" + r.label + ")" : "") : WARN_ICON + " " + esc(r.error || "lỗi");
      } else if (act === "rekey") {
        closeConnModal(); reconnectAccount(el, c, con);
      } else if (act === "default") {
        await postJson("/connect/default", { id: c.id }); closeConnModal(); renderConnect(el);
      } else if (act === "rename") {
        const v = prompt("Tên mới:", c.label || ""); if (v === null) return;
        await postJson("/connect/update", { id: c.id, label: v.trim() }); closeConnModal(); renderConnect(el);
      } else if (act === "perm") {
        openPermPicker(el, c, con);
      } else if (act === "deny") {
        const v = prompt("Tên tool cần CHẶN riêng cho kết nối này, cách nhau dấu phẩy.\nVD: pos_order, pos_transaction\n(Để trống = bỏ chặn)", (c.deny_tools || []).join(", "));
        if (v === null) return;
        await postJson("/connect/update", { id: c.id, deny_tools: v.split(",").map(x => x.trim()).filter(Boolean) });
        closeConnModal(); renderConnect(el);
      } else if (act === "relogin") {
        // Nguồn tự giữ token ngoài Javis (workspace-mcp): nút Kết nối lại chỉ lưu key chứ không
        // đụng được token, nên token cấp thiếu quyền là thiếu mãi. Đây là đường duy nhất bắt nó
        // hỏi lại quyền.
        if (!confirm('Xoá đăng nhập Google của "' + (c.label || "") + '"?\n\n'
          + 'Kết nối giữ nguyên. Lần sau nhờ Javis làm việc với nguồn này, trình duyệt trên MÁY '
          + 'CHẠY JAVIS sẽ mở để bạn cấp lại quyền - nhớ tick hết các ô.')) return;
        note.textContent = "Đang xoá…";
        const r = await postJson("/connect/relogin", { id: c.id });
        note.innerHTML = (r && r.ok ? CHECK_ICON : WARN_ICON) + " " + esc((r && (r.message || r.error)) || "Lỗi");
      } else if (act === "audit") {
        openAuditModal(c);
      } else if (act === "toggle") {
        await postJson("/connect/toggle", { id: c.id }); closeConnModal(); renderConnect(el);
      } else if (act === "del") {
        if (!confirm('Xoá kết nối "' + (c.label || "") + '"?')) return;
        await postJson("/connect/delete", { id: c.id }); closeConnModal(); renderConnect(el);
      }
    });
  }

  async function openAuditModal(c) {
    const m = connModal(mHead("NHẬT KÝ: " + esc(c.label || "")) + '<div class="conn-audit" id="audBody">Đang tải…</div>'
      + '<div class="mp-foot"><button class="mp-btn" data-act="close">Đóng</button></div>', 640);
    let d;
    try { d = await (await fetch("/connect/audit?limit=80&id=" + encodeURIComponent(c.id))).json(); } catch (e) { d = { entries: [] }; }
    const rows = (d.entries || []).map(e =>
      '<div class="aud-row' + (e.ok ? "" : " bad") + '"><span class="aud-ts">' + esc((e.ts || "").replace("T", " ")) + '</span> '
      + esc(e.tool || "") + ' <span class="mp-note">' + esc(e.mode || "") + "/" + esc(e.cls || "") + " · " + (e.ms || 0) + "ms</span>"
      + (e.ok ? "" : '<div class="aud-err">' + esc(e.err || "") + '</div>') + '</div>').join("");
    m.querySelector("#audBody").innerHTML = rows || '<div class="mp-note">Chưa có lượt gọi nào.</div>';
  }
  function ambientCard(s, kind) {   // MCP sẵn trong CLI (Claude Code / Codex) - chỉ hiển thị
    const ok = s.connected;
    const detail = s.url || s.command || "";
    return `<div class="prov-card" style="opacity:.92">
      <div class="prov-head">
        <span class="prov-shield ${ok ? "on" : ""}">${_shield(ok)}</span>
        <div class="prov-info">
          <div class="prov-name">${esc(s.name)} <span class="prov-kind">${esc(kind || "claude code")}</span></div>
          <div class="prov-status ${ok ? "on" : ""}">${ok ? ic("circle", { cls: "ic-fill ic-ok" }) + " " : WARN_ICON + " "}${esc(s.status)}${detail ? " · " + esc(detail) : ""}</div>
        </div>
      </div>
    </div>`;
  }
  async function renderConnect(el) {
    el.innerHTML = `<div class="cview-placeholder"><div class="ph-ico">${ic("loader", { cls: "ic-xl ic-spin" })}</div><div>Đang tải...</div></div>`;
    let d;
    try { d = await (await fetch("/connect/catalog")).json(); } catch (e) { el.innerHTML = placeholder("mcp", "Không tải được."); return; }
    const cat = d.catalog || [];
    const conns = d.connections || [];
    const byId = {};
    cat.forEach(c => byId[c.id] = c);
    byId.custom = { id: "custom", name: "Tự thêm (nâng cao)", icon: "star", category: "Khác",
                    description: "Server MCP tự khai URL/lệnh/header - dành cho người rành kỹ thuật.", auth_type: "apikey" };
    const st = await freshSettings();
    const main = (st.model && st.model.main) || {};
    const provs = (st.model && st.model.providers) || [];
    // MỌI provider Javis hỗ trợ đều gọi được kho Kết nối: hai CLI (Claude Code, Codex) đi
    // native, bốn provider API đi qua vòng gọi tool + hub trong _api_stream_mcp. Gemini từng
    // thiếu trong danh sách này nên khách chạy Gemini bị banner vàng "chưa hỗ trợ gọi công cụ"
    // dù bên dưới đã chạy MCP ngon - nhánh vàng giờ chỉ còn để chặn provider lạ.
    const MCP_PROVIDERS = ["anthropic-cli", "openrouter", "openai", "anthropic-api", "gemini", "groq", "ollama"];
    const mainLabel = (provs.find(p => p.id === main.provider) || {}).label || main.provider || "-";
    let warn = "";
    if (main.provider === "openai-oauth") {
      warn = `<div class="gcard" style="border:1px solid var(--green);background:rgba(44,122,75,.10);max-width:740px;margin-bottom:14px"><div class="gcard-meta" style="opacity:1">${CHECK_ICON} <b>ChatGPT (gói subscription)</b> chạy qua <b>Codex CLI</b> - Javis tự đẩy kho Kết nối sang Codex qua hub, nên vẫn dùng được đầy đủ.</div></div>`;
    } else if (!MCP_PROVIDERS.includes(main.provider)) {
      warn = `<div class="gcard" style="border:1px solid var(--warn-ink);background:rgba(185,130,31,.10);max-width:740px;margin-bottom:14px"><div class="gcard-meta" style="opacity:1">${WARN_ICON} Main Model đang là <b>${esc(mainLabel)}</b> - chưa hỗ trợ gọi công cụ. Đổi ở trang <b>Models</b>.</div></div>`;
    } else if (main.provider !== "anthropic-cli") {
      warn = `<div class="gcard" style="border:1px solid var(--green);background:rgba(44,122,75,.10);max-width:740px;margin-bottom:14px"><div class="gcard-meta" style="opacity:1">${CHECK_ICON} <b>${esc(mainLabel)}</b> dùng được kho Kết nối qua <b>MCP Javis</b> (vòng gọi tool + hub), kèm tool file trong brain và skill - không phải chat suông.</div></div>`;
    }
    const groups = {};
    conns.forEach(c => { const k = c.connector_id || "custom"; (groups[k] = groups[k] || []).push(c); });
    const connectedHtml = Object.keys(groups).map(cid =>
      connectorCard(byId[cid] || { id: cid, name: cid, icon: "plug" }, groups[cid])).join("");
    const cats = Array.from(new Set(cat.map(c => c.category || "Khác")));
    el.innerHTML = warn
      + '<div class="cview-section"><h3>◆ Đã kết nối <span style="opacity:.5">' + conns.length + ' tài khoản</span></h3>'
      + '<div class="gcard-meta" style="max-width:740px">Một dịch vụ nối được NHIỀU tài khoản (nhiều shop, nhiều số Zalo…). Mọi bộ não - Claude Code, ChatGPT/Codex, OpenRouter, API - dùng chung kho này qua trung tâm kết nối của Javis, kèm phân quyền và nhật ký.'
      + '<label style="margin-left:8px;cursor:pointer"><input type="checkbox" id="mcpStrict" ' + (d.strict ? "checked" : "") + '> Chỉ dùng kết nối của Javis (bỏ kết nối sẵn của máy)</label></div>'
      + '<div class="prov-list" style="margin-top:12px">' + (connectedHtml || '<div class="mp-empty">Chưa đấu nguồn nào - chọn một dịch vụ trong Kho bên dưới để bắt đầu.</div>') + '</div></div>'
      + '<div class="cview-section"><h3>◆ Kho kết nối</h3>'
      + '<div class="cat-tools"><input class="js-input" id="catQ" placeholder="Tìm dịch vụ…" style="max-width:220px">'
      + '<span class="cat-filter"><button class="cat-chip on" data-catf="">Tất cả</button>' + cats.map(x => '<button class="cat-chip" data-catf="' + esc(x) + '">' + esc(x) + '</button>').join("") + '</span></div>'
      + '<div class="cat-grid" id="catGrid">' + catalogCard(byId.custom) + groupCards(cat, conns) + catSolo(cat).map(catalogCard).join("") + '</div></div>'
      // Hai khu kết nối sẵn của CLI: GẬP mặc định (dân thường không cần thấy) + LAZY:
      // chỉ gọi /mcp/ambient (chậm - phải health check) khi người dùng thật sự mở ra.
      + '<details class="cview-section amb-details" id="ambWrap"><summary><h3 style="display:inline">◆ Kết nối sẵn của Claude Code và Codex <span style="opacity:.5">chỉ hiển thị - bấm để xem</span></h3></summary>'
      + '<div class="gcard-meta" style="max-width:740px;margin-top:10px">Những nguồn đã đăng nhập sẵn trong tài khoản Claude (đồng bộ từ claude.ai) và trong Codex CLI. Bộ não tương ứng tự dùng được các nguồn "Connected". Đăng nhập và quản lý trong app Claude hoặc bằng lệnh <code>codex mcp</code>, không sửa ở đây.</div>'
      + '<div class="prov-list" id="mcpAmbient" style="margin-top:12px"><div class="mp-empty">Bấm để tải…</div></div>'
      + '<div class="prov-list" id="mcpAmbientCodex" style="margin-top:12px"></div></details>';
    document.getElementById("mcpStrict").onchange = (e) => postJson("/mcp/strict", { strict: e.target.checked });
    // Sức khoẻ kết nối: tô ngay khi mở trang + làm tươi mỗi 60s (tự dừng khi rời trang)
    clearInterval(_healthTimer);
    refreshConnHealth(el, conns, byId);
    _healthTimer = setInterval(() => refreshConnHealth(el, conns, byId), 60000);
    const isFirst = conns.length === 0;
    const ctx = { conns: conns, byId: byId };   // cho flow biết tài khoản sẵn có (dùng lại key, đếm đã nối)
    el.querySelectorAll("[data-connect]").forEach(b => b.onclick = () => openAddFlow(el, byId[b.dataset.connect], isFirst, ctx));
    el.querySelectorAll("[data-addacc]").forEach(b => b.onclick = () => openAddFlow(el, byId[b.dataset.addacc], false, ctx));
    el.querySelectorAll("[data-groupopen]").forEach(b => b.onclick = () =>
      openGroupPicker(el, b.dataset.groupopen, cat.filter(c => c.group === b.dataset.groupopen), ctx, isFirst));
    el.querySelectorAll("[data-conn]").forEach(b => b.onclick = () => {
      const c = conns.find(x => x.id === b.dataset.conn);
      if (c) openAccountMenu(el, c, byId[c.connector_id]);
    });
    const applyFilter = () => {
      const q = (document.getElementById("catQ").value || "").toLowerCase();
      const onChip = el.querySelector(".cat-chip.on");
      const cf = onChip ? (onChip.dataset.catf || "") : "";
      el.querySelectorAll("#catGrid .cat-card").forEach(card => {
        const okQ = !q || card.textContent.toLowerCase().includes(q);
        const okC = !cf || card.dataset.cat === cf;
        card.style.display = (okQ && okC) ? "" : "none";
      });
    };
    document.getElementById("catQ").oninput = applyFilter;
    el.querySelectorAll(".cat-chip").forEach(ch => ch.onclick = () => {
      el.querySelectorAll(".cat-chip").forEach(x => x.classList.remove("on"));
      ch.classList.add("on");
      applyFilter();
    });
    // Lazy: chỉ tải danh sách ambient khi người dùng mở khu gập (lần đầu)
    const ambWrap = document.getElementById("ambWrap");
    if (ambWrap) ambWrap.addEventListener("toggle", () => {
      if (!ambWrap.open || ambWrap._loaded) return;
      ambWrap._loaded = true;
      const box = document.getElementById("mcpAmbient");
      if (box) box.innerHTML = '<div class="mp-empty">Đang tải… (kiểm tra tình trạng từng nguồn, hơi lâu)</div>';
      fetch("/mcp/ambient").then(r => r.json()).then(a => {
        if (box) {
          const list = a.servers || [];
          box.innerHTML = list.length ? list.map(s => ambientCard(s, "claude code")).join("") : '<div class="mp-empty">Không có (hoặc Claude CLI chưa cài).</div>';
        }
        const cbox = document.getElementById("mcpAmbientCodex");
        if (cbox) {
          const clist = a.codex_servers || [];
          cbox.innerHTML = clist.length ? clist.map(s => ambientCard(s, "codex")).join("") : '<div class="mp-empty">Không có (hoặc Codex CLI chưa cài).</div>';
        }
      }).catch(() => {
        ambWrap._loaded = false;   // mở lại sẽ thử tải lại
        ["mcpAmbient", "mcpAmbientCodex"].forEach(id => { const b = document.getElementById(id); if (b) b.innerHTML = '<div class="mp-empty">Không tải được.</div>'; });
      });
    });
  }
  function openMcpForm(el, server) {
    const edit = !!server;
    let modal = document.getElementById("mcpAddModal");
    if (!modal) { modal = document.createElement("div"); modal.id = "mcpAddModal"; modal.className = "mp-overlay"; document.body.appendChild(modal); }
    const keys = edit ? (server.header_keys || []).concat(server.env_keys || []) : [];
    const credPh = edit && keys.length ? "Để trống nếu giữ key cũ (" + esc(keys.join(", ")) + ")" : "Ví dụ: Authorization: Bearer xxxxx";
    modal.innerHTML = `
      <style>#mcpAddModal .mcp-lb{display:flex;flex-direction:column;gap:4px;font-size:14px;opacity:.85}#mcpAddModal .mcp-lb input,#mcpAddModal .mcp-lb select,#mcpAddModal .mcp-lb textarea{width:100%}</style>
      <div class="mp-box" style="max-width:560px">
        <div class="mp-head"><div class="mp-title">${edit ? "SỬA MCP SERVER" : "THÊM MCP SERVER"}</div><button class="mp-x" data-act="close">${X_ICON}</button></div>
        <div style="padding:14px 18px;display:flex;flex-direction:column;gap:10px">
          <label class="mcp-lb">Tên<input class="js-input" id="mName" placeholder="Ví dụ: pancake-pos-shop-2" value="${edit ? esc(server.name) : ""}"></label>
          <label class="mcp-lb">Transport<select class="js-input" id="mTransport"><option value="http">HTTP</option><option value="sse">SSE</option><option value="stdio">stdio</option></select></label>
          <label class="mcp-lb" id="mUrlWrap">URL<input class="js-input" id="mUrl" placeholder="Ví dụ: https://mcp-pos.pancake.biz/mcp" value="${edit ? esc(server.url || "") : ""}"></label>
          <label class="mcp-lb" id="mCmdWrap" style="display:none">Lệnh (stdio)<input class="js-input" id="mCmd" placeholder="Ví dụ: npx my-mcp-server (các tham số cách nhau bằng dấu cách)" value="${edit ? esc(((server.command || "") + " " + (server.args || []).join(" ")).trim()) : ""}"></label>
          <label class="mcp-lb" id="mCredWrap">Header (mỗi dòng, ví dụ Authorization: Bearer xxx)<textarea class="js-input" id="mCred" rows="3" placeholder="${credPh}"></textarea></label>
        </div>
        <div class="mp-foot"><span class="mp-note" id="mErr"></span><div><button class="mp-btn" data-act="close">Huỷ</button><button class="mp-btn primary" id="mSave">${edit ? "Lưu" : "Thêm"}</button></div></div>
      </div>`;
    const $ = (id) => modal.querySelector(id);
    if (edit) $("#mTransport").value = server.transport || "http";
    const sync = () => {
      const t = $("#mTransport").value;
      $("#mUrlWrap").style.display = (t === "stdio") ? "none" : "";
      $("#mCmdWrap").style.display = (t === "stdio") ? "" : "none";
      $("#mCredWrap").childNodes[0].nodeValue = (t === "stdio") ? "Env KEY=VALUE (mỗi dòng)" : "Header (mỗi dòng, vd Authorization: Bearer xxx)";
    };
    $("#mTransport").onchange = sync; sync();
    modal.querySelectorAll('[data-act="close"]').forEach(b => b.onclick = () => modal.classList.remove("open"));
    $("#mSave").onclick = async () => {
      const t = $("#mTransport").value;
      const body = { name: $("#mName").value.trim(), transport: t, url: $("#mUrl").value.trim() };
      if (!body.name) { $("#mErr").textContent = "Thiếu tên"; return; }
      const cred = $("#mCred").value.trim();
      if (t === "stdio") {
        const parts = $("#mCmd").value.trim().split(/\s+/).filter(Boolean);
        body.command = parts[0] || ""; body.args = parts.slice(1); body.auth = "env";
        if (cred || !edit) body.env = parseKV(cred, "=");
      } else {
        body.auth = "header";
        if (cred || !edit) body.headers = parseKV(cred, ":");   // edit + để trống = giữ key cũ
      }
      $("#mSave").disabled = true; $("#mSave").textContent = "Đang lưu…";
      let r;
      if (edit) { body.id = server.id; r = await postJson("/mcp/update", body); }
      else r = await postJson("/mcp/add", body);
      if (!r.ok) { $("#mErr").textContent = r.error || "Lỗi"; $("#mSave").disabled = false; $("#mSave").textContent = edit ? "Lưu" : "Thêm"; return; }
      modal.classList.remove("open");
      renderConnect(el);
    };
    modal.classList.add("open");
  }

  // ---- Trang Kênh (Telegram) - form đầy đủ ----
  async function renderChannels(el) {
    el.innerHTML = `<div class="cview-placeholder"><div class="ph-ico">${ic("loader", { cls: "ic-xl ic-spin" })}</div><div>Đang tải...</div></div>`;
    const s = await freshSettings();
    const tg = s.telegram || {};
    const zl = s.zalo_bot || {};
    el.innerHTML = `
      <div class="cview-section">
        <h3>Telegram</h3>
        <div class="gcard" style="max-width:560px">
          <label class="js-row"><span>Bật bot Telegram</span><input type="checkbox" id="tgEnabled" ${tg.enabled ? "checked" : ""}></label>
          <label class="js-lbl">Bot token ${tg.token_set ? '<span class="dim">(đã đặt)</span>' : ""}</label>
          <input class="js-input" id="tgToken" type="password" placeholder="${tg.token_set ? "Để trống nếu không đổi" : "Ví dụ: 123456:ABC..."}">
          <label class="js-lbl">Chat ID được phép dùng <span class="dim">(nhiều ID cách nhau dấu phẩy - mỗi người /start bot rồi thêm ID vào đây)</span></label>
          <input class="js-input" id="tgChat" value="${esc(tg.chat_id || "")}" placeholder="Ví dụ: 123456789, 987654321">
          <div class="js-actions"><button class="gcard-btn" id="tgSave">Lưu & bật</button><button class="gcard-btn ghost" id="tgTest">Gửi test</button></div>
          <div class="gcard-meta" id="tgStatus"></div>
        </div>
      </div>
      <div class="cview-section">
        <h3>${Icons.kenh("zalo", { size: "18px" })} Zalo</h3>
        <div class="gcard" style="max-width:560px">
          <div class="gcard-meta" style="margin-bottom:8px">Bot Zalo <b>chính thức</b> để hỏi Javis
            từ điện thoại. Khác <b>Zalo Agent MCP</b> ở trang Kết nối: cái kia đăng nhập chính tài
            khoản của bạn để Javis thao tác thay bạn, cái này là một danh tính riêng, an toàn, để
            bạn nhắn cho Javis.</div>
          <label class="js-row"><span>Bật bot Zalo</span><input type="checkbox" id="zlEnabled" ${zl.enabled ? "checked" : ""}></label>
          <label class="js-lbl">Bot token ${zl.token_set ? '<span class="dim">(đã đặt)</span>' : ""}</label>
          <input class="js-input" id="zlToken" type="password" placeholder="${zl.token_set ? "Để trống nếu không đổi" : "Ví dụ: 123456789:abc-xyz"}">
          <div class="gcard-meta">Lấy token: mở app Zalo, tìm Official Account <b>Zalo Bot Manager</b>,
            chọn <b>Tạo bot</b>. Tên bot bắt buộc mở đầu bằng chữ "Bot". Token gửi về bằng tin nhắn Zalo.</div>
          <label class="js-lbl">Chat ID được phép dùng <span class="dim">(không cần gõ tay - xem bên dưới)</span></label>
          <input class="js-input" id="zlChat" value="${esc(zl.chat_id || "")}" placeholder="Để trống rồi nhắn cho bot một câu">
          <div class="js-actions"><button class="gcard-btn" id="zlSave">Lưu & bật</button><button class="gcard-btn ghost" id="zlTest">Gửi test</button></div>
          <div class="gcard-meta" id="zlStatus"></div>
          <div id="zlCho"></div>
        </div>
      </div>
      ${placeholder("channels", "Sắp tới: web widget… mỗi kênh là 1 card ở đây.")}`;
    const st = document.getElementById("tgStatus");
    async function refreshTgStatus() {
      let d; try { d = await (await fetch("/telegram/status")).json(); } catch (e) { return; }
      let line;
      if (!d.enabled) line = ic("circle", { cls: "ic-dim" }) + " Bot CHƯA bật - tích 'Bật bot Telegram' rồi Lưu (test gửi được KHÔNG có nghĩa bot đang nhận tin).";
      else if (!d.token_set) line = ic("circle", { cls: "ic-dim" }) + " Chưa có bot token.";
      else if (d.status === "polling") {
        const n = (d.chat_ids || []).length;
        line = `${ic("circle", { cls: "ic-fill ic-ok" })} Bot đang nhận tin - ${n ? n + " chat ID được phép" : "MỌI NGƯỜI nhắn được (chưa giới hạn ID)"} - nhắn cho bot là Javis trả lời.`;
      }
      else if (d.status === "conflict") line = ic("circle", { cls: "ic-fill ic-err" }) + " 409: " + esc(d.last_error || "token bị poll nơi khác hoặc còn webhook") + " - bot tự xoá webhook khi khởi động; nếu vẫn lỗi thì có nơi khác đang poll cùng token.";
      else if (d.status === "error") line = WARN_ICON + " Lỗi bot: " + esc(d.last_error || "");
      else if (d.status === "starting") line = ic("loader", { cls: "ic-spin" }) + " Đang khởi động bot…";
      else line = ic("circle", { cls: "ic-dim" }) + " Bot đã tắt.";
      st.innerHTML = line;  // line chứa thẻ <svg> của icon - textContent sẽ in nguyên mã ra chữ
    }
    refreshTgStatus();
    document.getElementById("tgSave").onclick = async () => {
      const data = { enabled: document.getElementById("tgEnabled").checked, chat_id: document.getElementById("tgChat").value.trim() };
      const tok = document.getElementById("tgToken").value.trim();
      if (tok) data.token = tok;
      st.textContent = "Đang lưu...";
      const r = await saveSetting("telegram", data);
      st.innerHTML = r.ok ? OK_ICON + " Đã lưu, đang khởi động bot…" : WARN_ICON + " Lỗi lưu.";
      if (r.ok) setTimeout(refreshTgStatus, 1800);
    };
    document.getElementById("tgTest").onclick = async () => {
      st.textContent = "Đang gửi test...";
      try {
        const r = await (await fetch("/telegram/test", { method: "POST" })).json();
        st.innerHTML = r.ok
          ? (r.total > 1 ? `${OK_ICON} Đã gửi tin test tới ${Number(r.sent) || 0}/${Number(r.total) || 0} ID.` + (r.error ? " Lỗi: " + esc(r.error) : "") : OK_ICON + " Đã gửi tin test.")
          : Icons.warn(r.error || "Chưa cấu hình bot.");
      }
      catch (e) { st.innerHTML = WARN_ICON + " Lỗi mạng."; }
    };

    // ---- Thẻ Zalo ----
    const zst = document.getElementById("zlStatus");
    const zcho = document.getElementById("zlCho");
    async function refreshZalo() {
      let d; try { d = await (await fetch("/zalo-bot/status")).json(); } catch (e) { return; }
      let line;
      if (!d.enabled) line = ic("circle", { cls: "ic-dim" }) + " Bot CHƯA bật - tích 'Bật bot Zalo' rồi Lưu.";
      else if (!d.token_set) line = ic("circle", { cls: "ic-dim" }) + " Chưa có bot token.";
      else if (d.status === "polling") {
        const n = (d.chat_ids || []).length;
        line = `${ic("circle", { cls: "ic-fill ic-ok" })} Bot đang nhận tin${d.bot_name ? " (" + esc(d.bot_name) + ")" : ""} - ${n ? n + " chat ID được phép" : "chưa cho phép ai - nhắn cho bot một câu rồi bấm Cho phép bên dưới"}.`;
      }
      else if (d.status === "error") line = WARN_ICON + " Lỗi bot: " + esc(d.last_error || "");
      else if (d.status === "starting") line = ic("loader", { cls: "ic-spin" }) + " Đang khởi động bot…";
      else line = ic("circle", { cls: "ic-dim" }) + " Bot đã tắt.";
      if (d.loi_danh_tinh) line += "<br>" + WARN_ICON + " " + esc(d.loi_danh_tinh);
      zst.innerHTML = line;
      // Hàng chờ ghép nối: thay cho việc bắt user đi tra một chuỗi hex không ai đọc nổi.
      // Zalo không có công cụ kiểu @userinfobot của Telegram, nên phải đảo chiều - người lạ
      // nhắn cho bot thì họ hiện ra ở đây kèm TÊN THẬT và một mã để chủ đối chiếu đúng người.
      const cho = d.cho || [];
      zcho.innerHTML = cho.length
        ? '<div class="gcard-meta" style="margin-top:10px"><b>Đang chờ bạn cho phép</b></div>' +
          cho.map(g => `<div class="zl-cho" data-cid="${esc(g.chat_id)}">
              <div><b>${esc(g.ten || "Người dùng Zalo")}</b> <span class="dim">mã ${esc(g.ma)}</span></div>
              <div class="dim">Đã nhắn ${Number(g.lan) || 1} lần. Hỏi họ đọc mã trong tin bot trả lời để chắc đúng người.</div>
              <div class="js-actions"><button class="gcard-btn zl-ok">Cho phép</button><button class="gcard-btn ghost zl-bo">Bỏ qua</button></div>
            </div>`).join("")
        : "";
      zcho.querySelectorAll(".zl-cho").forEach(n => {
        const cid = n.dataset.cid;
        const gui = async (on) => {
          const f = new FormData(); f.append("chat_id", cid); f.append("on", on ? "1" : "0");
          try { await fetch("/zalo-bot/allow", { method: "POST", body: f }); } catch (e) {}
          const inp = document.getElementById("zlChat");
          if (on && inp) inp.value = inp.value ? inp.value + ", " + cid : cid;
          refreshZalo();
        };
        n.querySelector(".zl-ok").onclick = () => gui(true);
        n.querySelector(".zl-bo").onclick = () => gui(false);
      });
    }
    refreshZalo();
    document.getElementById("zlSave").onclick = async () => {
      const data = { enabled: document.getElementById("zlEnabled").checked, chat_id: document.getElementById("zlChat").value.trim() };
      const tok = document.getElementById("zlToken").value.trim();
      if (tok) data.token = tok;
      zst.textContent = "Đang lưu...";
      const r = await saveSetting("zalo_bot", data);
      zst.innerHTML = r.ok ? OK_ICON + " Đã lưu, đang khởi động bot…" : WARN_ICON + " Lỗi lưu.";
      if (r.ok) setTimeout(refreshZalo, 1800);
    };
    document.getElementById("zlTest").onclick = async () => {
      zst.textContent = "Đang gửi test...";
      try {
        const r = await (await fetch("/zalo-bot/test", { method: "POST" })).json();
        zst.innerHTML = r.ok
          ? (r.total > 1 ? `${OK_ICON} Đã gửi tin test tới ${Number(r.sent) || 0}/${Number(r.total) || 0} ID.` + (r.error ? " Lỗi: " + esc(r.error) : "") : OK_ICON + " Đã gửi tin test.")
          : Icons.warn(r.error || "Chưa cấu hình bot.");
      }
      catch (e) { zst.innerHTML = WARN_ICON + " Lỗi mạng."; }
    };
  }

  // ---- Trang Tài khoản: workspace + đăng nhập ----
  async function renderAccount(el) {
    el.innerHTML = `<div class="cview-placeholder"><div class="ph-ico">${ic("loader", { cls: "ic-xl ic-spin" })}</div><div>Đang tải...</div></div>`;
    const s = await freshSettings();
    const auth = s.auth || {};
    el.innerHTML = `
      <div class="cview-section">
        <h3>Workspace</h3>
        <div class="gcard" style="max-width:560px">
          <label class="js-lbl">Tên workspace</label>
          <input class="js-input" id="acWs" value="${esc(s.workspace_name || "Javis OS")}">
          <button class="gcard-btn" id="acWsSave">Lưu</button>
          <div class="gcard-meta" id="acWsStatus"></div>
        </div>
      </div>
      <div class="cview-section">
        <h3>Tài khoản đăng nhập</h3>
        <div class="gcard" style="max-width:560px">
          <div class="gcard-meta" id="acAuthMeta">${auth.has_password ? ic("lock") + " Đã đặt mật khẩu · tài khoản: <b>" + esc(auth.username || "admin") + "</b>" : "Chưa đặt mật khẩu - ai mở dashboard cũng dùng được. Đặt mật khẩu nếu đưa lên VPS."}</div>
          <label class="js-lbl">Tài khoản</label><input class="js-input" id="acUser" value="${esc(auth.username || "")}" placeholder="Ví dụ: admin">
          ${auth.has_password ? '<label class="js-lbl">Mật khẩu hiện tại</label><input class="js-input" id="acCur" type="password" placeholder="Mật khẩu đang dùng" autocomplete="current-password">' : ""}
          <label class="js-lbl">${auth.has_password ? "Mật khẩu mới" : "Mật khẩu"}</label><input class="js-input" id="acPass" type="password" autocomplete="new-password" placeholder="${auth.has_password ? "Tối thiểu 8 ký tự - để trống nếu chỉ đổi tên đăng nhập" : "Đặt mật khẩu (tối thiểu 8 ký tự)"}">
          <div class="js-actions">
            <button class="gcard-btn" id="acSave">${auth.has_password ? "Đổi mật khẩu" : "Đặt mật khẩu"}</button>
            ${auth.has_password ? '<button class="gcard-btn ghost" id="acLogout">Đăng xuất</button><button class="gcard-btn ghost" id="acDisable">Tắt đăng nhập</button>' : ""}
          </div>
          <div class="gcard-meta" id="acStatus"></div>
        </div>
      </div>
      ${auth.has_password ? `
      <div class="cview-section">
        <h3>Xác thực 2 lớp <span style="opacity:.5">mã 6 số từ app Authenticator</span></h3>
        <div class="gcard tfa-card" style="max-width:560px" id="tfaCard">
          <div class="gcard-meta" id="tfaHead">Đang kiểm tra...</div>
          <div id="tfaBody"></div>
          <div class="gcard-meta" id="tfaStatus"></div>
        </div>
      </div>` : ""}
      <div class="cview-section">
        <h3>Token API (cho CLI)</h3>
        <div class="gcard" style="max-width:560px">
          <div class="gcard-meta">Token để <b>Javis CLI</b> (hoặc script) gọi được Javis từ máy khác. Không có token nào sẵn - chưa tạo thì không đường nào vào ngoài trình duyệt.</div>
          <label class="js-lbl">Tên token</label>
          <input class="js-input" id="tkName" placeholder="Ví dụ: laptop của bạn">
          <label class="js-lbl">Phạm vi</label>
          <select class="js-input" id="tkScope">
            <option value="chat">Chỉ chat - vào được /chat, /version, /health, /sessions</option>
            <option value="full">Toàn quyền - như đang đăng nhập</option>
          </select>
          <div class="js-actions"><button class="gcard-btn" id="tkCreate">Tạo token</button></div>
          <div class="gcard-meta" id="tkStatus"></div>
          <div id="tkNew"></div>
          <div id="tkList" class="tk-list"></div>
          <div class="tk-docs">
            <a href="https://github.com/blogminhquy/javis-os/blob/main/docs/24-cli-terminal.md" target="_blank" rel="noopener">Hướng dẫn Javis CLI ↗</a>
            <a href="https://github.com/blogminhquy/javis-os/blob/main/docs/14-bao-mat-tai-khoan.md" target="_blank" rel="noopener">Bảo mật &amp; tài khoản ↗</a>
          </div>
        </div>
      </div>`;
    renderTokens();
    document.getElementById("tkCreate").onclick = async () => {
      const st = document.getElementById("tkStatus");
      st.textContent = "Đang tạo...";
      const fd = new FormData();
      fd.append("name", document.getElementById("tkName").value.trim());
      fd.append("scope", document.getElementById("tkScope").value);
      let r;
      try { r = await (await fetch("/auth/tokens", { method: "POST", body: fd })).json(); }
      catch (e) { st.innerHTML = WARN_ICON + " Lỗi mạng."; return; }
      if (!r.ok) { st.innerHTML = Icons.warn(r.error || "Không tạo được token."); return; }
      st.textContent = "";
      document.getElementById("tkName").value = "";
      // Bản thô hiện ĐÚNG một lần. Trên đĩa chỉ còn bản băm nên không có đường nào xem lại,
      // và nói thẳng điều đó ra ngay tại đây thay vì để người dùng phát hiện lúc F5.
      document.getElementById("tkNew").innerHTML = `
        <div class="tk-new">
          <div class="tk-new-hd">${OK_ICON} Token mới - copy ngay, đóng trang là không xem lại được.</div>
          <code class="tk-code" id="tkRaw">${esc(r.token || "")}</code>
          <div class="js-actions">
            <button class="gcard-btn" id="tkCopy">Copy</button>
            <button class="gcard-btn ghost" id="tkHide">Ẩn đi</button>
          </div>
          <div class="gcard-meta">Dán vào máy kia: <code>javis login ${esc(location.origin)} --token &lt;token&gt;</code></div>
          <div class="gcard-meta">Chưa cài CLI? <code>pip install javis-cli</code> · <a class="tk-doclink" href="https://github.com/blogminhquy/javis-os/blob/main/docs/24-cli-terminal.md" target="_blank" rel="noopener">xem hướng dẫn ↗</a></div>
        </div>`;
      document.getElementById("tkCopy").onclick = () => {
        const c = document.getElementById("tkCopy");
        try { navigator.clipboard.writeText(r.token || ""); c.textContent = "Đã copy"; }
        catch (e) { c.textContent = "Copy tay giúp em"; }
      };
      document.getElementById("tkHide").onclick = () => { document.getElementById("tkNew").innerHTML = ""; };
      renderTokens();
    };
    const wsStatus = document.getElementById("acWsStatus");
    document.getElementById("acWsSave").onclick = async () => {
      wsStatus.textContent = "Đang lưu...";
      const r = await saveSetting("general", { workspace_name: document.getElementById("acWs").value.trim() });
      wsStatus.innerHTML = r.ok ? OK_ICON + " Đã lưu." : WARN_ICON + " Lỗi.";
      const wn = document.getElementById("workspaceName"); if (wn) wn.textContent = document.getElementById("acWs").value.trim() || "Javis OS";
    };
    const acStatus = document.getElementById("acStatus");
    // HAI đường, đừng gộp: /auth/setup là đường CÔNG KHAI cho lần đầu tạo admin và nó TỪ CHỐI
    // khi đã có tài khoản, nên gọi nó để đổi mật khẩu là bấm Lưu mà không có gì xảy ra (lỗi
    // 0.28.2 trở về trước). Đã có tài khoản thì đi /auth/password, kèm mật khẩu hiện tại.
    document.getElementById("acSave").onclick = async () => {
      const user = document.getElementById("acUser").value.trim() || "admin";
      const pass = document.getElementById("acPass").value;
      const curEl = document.getElementById("acCur");
      if (auth.has_password) {
        const cur = curEl ? curEl.value : "";
        if (!cur) { acStatus.innerHTML = WARN_ICON + " Nhập mật khẩu hiện tại để xác nhận."; return; }
        if (pass && pass.length < 8) { acStatus.innerHTML = WARN_ICON + " Mật khẩu mới tối thiểu 8 ký tự."; return; }
        if (!pass && user === (auth.username || "")) { acStatus.innerHTML = WARN_ICON + " Chưa đổi gì cả - nhập mật khẩu mới hoặc tên đăng nhập mới."; return; }
        acStatus.textContent = "Đang lưu...";
        const fd = new FormData();
        fd.append("current_password", cur); fd.append("username", user);
        if (pass) fd.append("password", pass);
        try {
          const r = await (await fetch("/auth/password", { method: "POST", body: fd })).json();
          if (!r.ok) { acStatus.innerHTML = Icons.warn(r.error || "Lỗi."); return; }
          // KHÔNG vẽ lại cả trang: vẽ lại là xoá mất câu báo vừa hiện, mà đây đúng là lúc người
          // ta cần đọc nó (các máy khác vừa bị đăng xuất).
          auth.username = r.username || user;
          if (curEl) curEl.value = "";
          document.getElementById("acPass").value = "";
          document.getElementById("acUser").value = auth.username;
          const meta = document.getElementById("acAuthMeta");
          if (meta) meta.innerHTML = ic("lock") + " Đã đặt mật khẩu · tài khoản: <b>" + esc(auth.username) + "</b>";
          acStatus.innerHTML = OK_ICON + (pass
            ? " Đã đổi mật khẩu. Máy khác đang đăng nhập sẽ phải đăng nhập lại."
            : " Đã đổi tên đăng nhập.");
        } catch (e) { acStatus.innerHTML = WARN_ICON + " Lỗi mạng."; }
        return;
      }
      if (!pass || pass.length < 8) { acStatus.innerHTML = WARN_ICON + " Mật khẩu tối thiểu 8 ký tự."; return; }
      acStatus.textContent = "Đang lưu...";
      // /auth/setup cấp cookie ngay → tránh tự khoá khi bật auth lần đầu
      const fd = new FormData(); fd.append("username", user); fd.append("password", pass);
      try { const r = await (await fetch("/auth/setup", { method: "POST", body: fd })).json(); acStatus.innerHTML = r.ok ? OK_ICON + " Đã lưu tài khoản." : Icons.warn(r.error || "Lỗi."); if (r.ok) renderAccount(el); }
      catch (e) { acStatus.innerHTML = WARN_ICON + " Lỗi mạng."; }
    };
    const lo = document.getElementById("acLogout");
    if (lo) lo.onclick = async () => { await fetch("/auth/logout", { method: "POST" }); location.reload(); };
    const dis = document.getElementById("acDisable");
    if (dis) dis.onclick = async () => { if (confirm("Tắt đăng nhập? Ai mở dashboard cũng dùng được.")) { await fetch("/auth/disable", { method: "POST" }); renderAccount(el); } };
    renderTfa(el);
  }

  // ---- Xác thực 2 lớp (TOTP) ----
  // Ba trạng thái: TẮT (mời bật), ĐANG BẬT (quét QR + nhập mã xác nhận), ĐÃ BẬT (quản lý).
  // Vẽ lại cả thẻ theo trạng thái thay vì ẩn/hiện từng mảnh: luồng này người ta đi đúng một
  // lần rồi thôi, nên rõ ràng quan trọng hơn mượt.
  async function renderTfa(rootEl) {
    const head = document.getElementById("tfaHead");
    const body = document.getElementById("tfaBody");
    const st = document.getElementById("tfaStatus");
    if (!head || !body) return;
    let a = {};
    try { a = await (await fetch("/auth/status")).json(); } catch (e) {
      head.innerHTML = WARN_ICON + " Không đọc được trạng thái."; return;
    }
    const bao = (m, loi) => { if (st) st.innerHTML = (loi ? WARN_ICON : OK_ICON) + " " + esc(m); };

    // 2FA bật trong cấu hình nhưng máy chủ KHÔNG giải mã được khoá (mất/đổi file
    // .secret_key trong thư mục state - hay gặp khi đổi volume/chép state thiếu file ẩn).
    // Nói thẳng thay vì hiện "Chưa bật" như trước: chủ bật 2FA mà thấy "Chưa bật" là
    // tưởng cập nhật đè mất, còn thực tế cổng đăng nhập đang đòi mã khôi phục.
    if (a.totp_broken) {
      head.innerHTML = WARN_ICON + " <b>Đang bật nhưng khoá bị lỗi.</b> Máy chủ không giải mã được "
        + "khoá 2FA (file <code>.secret_key</code> trong thư mục state bị mất hoặc đổi). "
        + "Mã 6 số từ app KHÔNG dùng được nữa - đăng nhập tạm bằng <b>mã khôi phục</b>. "
        + "Bấm nút dưới để bật lại với khoá mới (mục cũ trong app Authenticator sẽ hết hiệu lực).";
      body.innerHTML = `<div class="js-actions"><button class="gcard-btn" id="tfaOn">Bật lại xác thực 2 lớp</button></div>`;
      const nutBatLai = document.getElementById("tfaOn");
      if (nutBatLai) nutBatLai.onclick = async () => {
        const r = await (await fetch("/auth/2fa/start", { method: "POST" })).json();
        if (!r.ok) { bao(r.error || "Không bắt đầu được.", true); return; }
        batLuong2Fa(body, r, bao, rootEl);
      };
      return;
    }

    if (a.totp_enabled) {
      const con = Number(a.totp_recovery_left || 0);
      head.innerHTML = ic("shield") + " <b>Đang bật.</b> Mỗi lần đăng nhập sẽ hỏi thêm mã 6 số."
        + ` Còn <b>${con}</b> mã khôi phục.`
        + (con <= 2 ? ' <span class="tfa-warn">Sắp hết - nên tạo bộ mới.</span>' : "");
      body.innerHTML = `
        <label class="js-lbl">Mật khẩu (xác nhận là chính bạn)</label>
        <input class="js-input" id="tfaPw" type="password" placeholder="Mật khẩu đang dùng">
        <label class="js-lbl">Mã 6 số (chỉ cần khi TẮT)</label>
        <input class="js-input" id="tfaCode" inputmode="numeric" placeholder="Mã đang hiện, hoặc mã khôi phục">
        <div class="js-actions">
          <button class="gcard-btn" id="tfaRegen">Tạo bộ mã khôi phục mới</button>
          <button class="gcard-btn ghost" id="tfaOff">Tắt 2 lớp</button>
        </div>`;
      document.getElementById("tfaRegen").onclick = async () => {
        const pw = document.getElementById("tfaPw").value;
        if (!pw) { bao("Nhập mật khẩu trước.", true); return; }
        const fd = new FormData(); fd.append("password", pw);
        const r = await (await fetch("/auth/2fa/recovery", { method: "POST", body: fd })).json();
        if (!r.ok) { bao(r.error || "Lỗi.", true); return; }
        hienMaKhoiPhuc(body, r.recovery, "Bộ mã CŨ vừa hết hiệu lực. Đây là bộ mới:");
        bao("Đã tạo bộ mã khôi phục mới.");
      };
      document.getElementById("tfaOff").onclick = async () => {
        if (!confirm("Tắt xác thực 2 lớp? Từ đó chỉ còn mật khẩu bảo vệ Javis.")) return;
        const fd = new FormData();
        fd.append("password", document.getElementById("tfaPw").value);
        fd.append("code", document.getElementById("tfaCode").value.trim());
        const r = await (await fetch("/auth/2fa/disable", { method: "POST", body: fd })).json();
        if (!r.ok) { bao(r.error || "Lỗi.", true); return; }
        renderTfa(rootEl);
      };
      return;
    }

    // Chưa bật. `totp_suggested` = lúc cài người dùng đã CHỌN bật 2FA (install.sh ghi cờ vào
    // .env), nên nói rõ ra thay vì để họ tự nhớ mình đã chọn gì mấy phút trước.
    head.innerHTML = a.totp_suggested
      ? ic("shield") + " <b>Bạn đã chọn bật 2 lớp lúc cài.</b> Bấm Bật để quét QR và hoàn tất."
      : ic("shield") + " Chưa bật. Bật thì mật khẩu lộ ra ngoài cũng chưa đủ để vào được Javis.";
    body.innerHTML = `<div class="js-actions"><button class="gcard-btn" id="tfaOn">Bật xác thực 2 lớp</button></div>`;
    document.getElementById("tfaOn").onclick = async () => {
      const r = await (await fetch("/auth/2fa/start", { method: "POST" })).json();
      if (!r.ok) { bao(r.error || "Không bắt đầu được.", true); return; }
      batLuong2Fa(body, r, bao, rootEl);
    };
  }

  // Luồng quét QR + xác nhận mã. Tách hàm vì có HAI cửa vào: bật lần đầu, và bật LẠI khi
  // khoá cũ hỏng (mất .secret_key) - hai cửa phải ra cùng một luồng, không chép đôi.
  function batLuong2Fa(body, r, bao, rootEl) {
    body.innerHTML = `
      <div class="tfa-steps">
        <div class="tfa-step"><b>1.</b> Mở app Authenticator (Google Authenticator, Microsoft
          Authenticator, 1Password, Bitwarden... cái nào cũng được) rồi quét mã dưới đây.</div>
        <div class="tfa-qr">${r.qr_svg || '<div class="gcard-meta">Máy chủ chưa cài segno nên không vẽ được QR - nhập tay khoá bên dưới.</div>'}</div>
        <div class="tfa-step"><b>2.</b> Quét không được thì nhập tay khoá này:
          <code class="tfa-secret">${esc(r.secret)}</code></div>
        <div class="tfa-step"><b>3.</b> Nhập mã 6 số đang hiện trong app để xác nhận:</div>
        <input class="js-input" id="tfaVerify" inputmode="numeric" placeholder="Mã 6 số">
        <div class="js-actions">
          <button class="gcard-btn" id="tfaConfirm">Xác nhận và bật</button>
          <button class="gcard-btn ghost" id="tfaCancel">Huỷ</button>
        </div>
      </div>`;
    const inp = document.getElementById("tfaVerify");
    inp.focus();
    const xacNhan = async () => {
      const fd = new FormData(); fd.append("code", inp.value.trim());
      const d = await (await fetch("/auth/2fa/enable", { method: "POST", body: fd })).json();
      if (!d.ok) { bao(d.error || "Mã không đúng.", true); inp.select(); return; }
      // Mã khôi phục chỉ hiện ĐÚNG LÚC NÀY. Server giữ bản băm nên không có đường nào xem lại.
      hienMaKhoiPhuc(body, d.recovery,
        "Đã bật. Chép 10 mã khôi phục dưới đây ra chỗ an toàn NGAY - chúng chỉ hiện một lần, "
        + "và là đường vào duy nhất nếu bạn mất điện thoại:");
      bao("Đã bật xác thực 2 lớp.");
    };
    document.getElementById("tfaConfirm").onclick = xacNhan;
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") xacNhan(); });
    document.getElementById("tfaCancel").onclick = () => renderTfa(rootEl);
  }

  function hienMaKhoiPhuc(body, ds, loiNhan) {
    body.innerHTML = `
      <div class="tfa-rec">
        <div class="tfa-rec-note">${esc(loiNhan)}</div>
        <div class="tfa-rec-grid">${(ds || []).map(m => `<code>${esc(m)}</code>`).join("")}</div>
        <div class="js-actions">
          <button class="gcard-btn" id="tfaCopy">Chép tất cả</button>
          <button class="gcard-btn ghost" id="tfaDone">Tôi đã lưu xong</button>
        </div>
      </div>`;
    document.getElementById("tfaCopy").onclick = async () => {
      try { await navigator.clipboard.writeText((ds || []).join("\n")); } catch (e) {}
      document.getElementById("tfaCopy").textContent = "Đã chép";
    };
    document.getElementById("tfaDone").onclick = () => location.reload();
  }

  // Danh sách token. Chỉ có tiền tố + tên: máy chủ không giữ bản thô nên UI cũng không có gì
  // để hiện lại, và đó là điểm mạnh chứ không phải thiếu sót.
  async function renderTokens() {
    const box = document.getElementById("tkList");
    if (!box) return;
    let d;
    try { d = await (await fetch("/auth/tokens")).json(); }
    catch (e) { box.innerHTML = `<div class="gcard-meta">${WARN_ICON} Không đọc được danh sách token.</div>`; return; }
    const ds = d.tokens || [];
    if (!ds.length) { box.innerHTML = '<div class="gcard-meta">Chưa có token nào.</div>'; return; }
    box.innerHTML = ds.map(t => {
      const dung = Number(t.last_used_at) > 0
        ? "dùng lần cuối " + new Date(Number(t.last_used_at) * 1000).toLocaleString(LOC())
        : "chưa dùng lần nào";
      const pv = t.scope === "chat" ? "chỉ chat" : "toàn quyền";
      return `<div class="tk-row">
        <div class="tk-info">
          <b>${esc(t.name || "không tên")}</b>
          <span class="tk-meta"><code>${esc(t.prefix || "")}…</code> · ${pv} · ${esc(dung)}</span>
        </div>
        <button class="gcard-btn ghost tk-del" data-id="${esc(t.id || "")}">Thu hồi</button>
      </div>`;
    }).join("");
    box.querySelectorAll(".tk-del").forEach(b => {
      b.onclick = async () => {
        if (!confirm("Thu hồi token này? Máy nào đang dùng nó sẽ mất kết nối ngay.")) return;
        const fd = new FormData(); fd.append("id", b.dataset.id || "");
        try { await fetch("/auth/tokens/revoke", { method: "POST", body: fd }); } catch (e) {}
        renderTokens();
      };
    });
  }

  // ---- Lưu 1 section settings ----
  async function saveSetting(section, dataObj) {
    const fd = new FormData();
    fd.append("section", section);
    fd.append("data", JSON.stringify(dataObj));
    let res;
    try { res = await (await fetch("/settings", { method: "POST", body: fd })).json(); }
    catch (e) { res = { ok: false }; }
    // Đổi model ở trang Models mà thanh model trong chat không đổi theo: hai chỗ đó đọc
    // /settings ở hai thời điểm khác nhau và không ai báo cho ai. Làm mới ngay tại đây để
    // mọi đường đổi model đều đồng bộ, thay vì nhớ gọi ở từng nút.
    if (section === "model") refreshModelUi();
    return res;
  }

  // Đồng bộ mọi chỗ hiển thị model: thanh chọn model dưới khung chat và badge engine trên
  // đầu hội thoại (badge trong trang chat soi gương từ badge HUD nên chỉ cần làm mới HUD).
  function refreshModelUi() {
    try { if (window.initModelBar) window.initModelBar(); } catch (e) {}
    try { if (window.refreshEngineBadge) window.refreshEngineBadge(); } catch (e) {}
  }
  if (typeof window !== "undefined") window.JavisRefreshModelUi = refreshModelUi;

  // ---- Cất #quickSet (avatar/tên miền/giọng nói) về holder ẩn khi rời trang Cài đặt ----
  // Node giữ nguyên → mọi handler đã gắn ở app.js/branding.js/quick-settings.js vẫn sống.
  function parkQuickSet() {
    const qs = document.getElementById("quickSet");
    const holder = document.getElementById("quickSetHolder");
    if (qs && holder && qs.parentNode !== holder) holder.appendChild(qs);
  }

  // ---- Trang Cài đặt: nhúng #quickSet + bộ chọn nhà cung cấp giọng đọc ----
  // Dòng trạng thái 2FA trong khối "Tài khoản đăng nhập" cũ (#quickSet, index.html).
  //
  // Vì sao cần: Javis có HAI bề mặt cài đặt tài khoản - trang Tài khoản (đủ thứ, gồm cả 2FA)
  // và khối cũ này nhúng trong trang Cài đặt (chỉ đổi mật khẩu). Ai mở Cài đặt trước sẽ thấy
  // một khối tài khoản không nhắc gì tới 2FA và kết luận Javis không có, rồi thôi.
  //
  // Đây CHỈ là trạng thái + lối đi. Nút bấm mang data-settings-go="account" nên nó dùng chung
  // đúng đường chuyển trang với mấy nút còn lại, không tự gọi navigateTo.
  async function renderTfaRow() {
    const row = document.getElementById("setTfaRow");
    if (!row) return;                     // index.html bản cũ (cache) → bỏ qua, không làm sập trang
    let a = {};
    try { a = await (await fetch("/auth/status")).json(); } catch (e) { row.hidden = true; return; }
    // Chưa đặt mật khẩu thì chưa có gì để chồng lớp thứ hai lên. Nói thẳng thứ tự phải làm,
    // thay vì hiện một nút bấm vào rồi mới biết là chưa tới lượt.
    if (a.needs_setup) {
      row.hidden = false;
      row.innerHTML = `${ic("shield")} Xác thực 2 lớp: <b>đặt mật khẩu trước đã</b> - xong mới bật được.`;
      return;
    }
    const con = Number(a.totp_recovery_left || 0);
    row.hidden = false;
    // totp_broken đứng TRƯỚC: khoá hỏng mà hiện "chưa bật" là chủ tưởng cập nhật đè mất
    // 2FA, trong khi thật ra cổng đang đòi mã khôi phục (vụ 16/08).
    row.innerHTML = a.totp_broken
      ? `${ic("shield")} Xác thực 2 lớp: <b class="tfa-low">đang bật nhưng khoá bị lỗi</b>`
        + ` - đăng nhập bằng mã khôi phục, rồi bật lại với khoá mới.`
        + ` <button class="s-btn" data-settings-go="account">Sửa ngay</button>`
      : a.totp_enabled
      ? `${ic("shield")} Xác thực 2 lớp: <b class="tfa-on">đang bật</b>`
        + ` · còn ${con} mã khôi phục`
        + (con <= 2 ? ` <b class="tfa-low">(sắp hết)</b>` : "")
        + ` <button class="s-btn-ghost" data-settings-go="account">Quản lý</button>`
      : `${ic("shield")} Xác thực 2 lớp: <b class="tfa-off">chưa bật</b>`
        + ` - bật thì mật khẩu lộ ra ngoài cũng chưa đủ để vào được Javis.`
        + ` <button class="s-btn" data-settings-go="account">Bật ngay</button>`;
  }

  async function renderSettings(el) {
    const gen = _renderGen;               // chốt token: nếu user đổi trang trong lúc await → bỏ render này
    parkQuickSet();                       // giữ #quickSet an toàn TRƯỚC khi ghi đè cviewBody
    el.innerHTML = `<div class="cview-placeholder"><div class="ph-ico">${ic("loader", { cls: "ic-xl ic-spin" })}</div><div>Đang tải...</div></div>`;
    const s = await freshSettings();
    if (gen !== _renderGen) return;       // đã sang trang khác → KHÔNG ghi đè trang mới bằng nội dung cũ
    const v = s.voice || {};
    const prov = v.tts_provider || "edge";
    const oaSet = !!(s.model && s.model.openai_api_key_set);
    const elSet = !!v.elevenlabs_key_set;
    const model = s.model || {};
    const telegram = s.telegram || {};
    const dashboard = s.dashboard || {};
    const graphOn = dashboard.graph_enabled !== false;
    const stripC2pa = !!((s.image || {}).strip_c2pa);
    const mainProviderId = model.main?.provider || (model.engine === "openrouter" ? "openrouter" : "anthropic-cli");
    const mainProvider = (model.providers || []).find(p => p.id === mainProviderId);
    const engine = mainProvider?.label || ({ "openrouter": "OpenRouter", "openai": "OpenAI API", "openai-oauth": "ChatGPT OAuth", "anthropic-cli": "Claude CLI" }[mainProviderId] || mainProviderId);
    const currentModel = model.main?.model || (mainProviderId === "openrouter" ? model.openrouter_model : model.claude_model) || "Mặc định";
    const opt = (val, label, cur) => `<option value="${esc(val)}"${val === cur ? " selected" : ""}>${esc(label)}</option>`;
    const oaVoices = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"];
    // NGÔN NGỮ TRẢ LỜI. Danh sách lấy từ /lang/list (sổ đăng ký phía server) chứ KHÔNG khai
    // lại ở đây: khai hai nơi thì thêm ngôn ngữ mới lại phải nhớ sửa cả hai, và chỗ bị quên
    // là chỗ hỏng trong im lặng.
    const lc = s.locale || {};
    const langs = (s.lang_list || []);
    const replyLang = lc.reply_lang || "auto";
    const uiLang = (window.JavisI18n && JavisI18n.lang()) || "vi";
    const langHtml = `
      <div class="qs-block">
        <div class="popover-label">${esc(t("settings.ui_lang.title"))}</div>
        <select class="js-input" id="vpUiLang">
          ${langs.map(l => opt(l.ma, l.ten, uiLang)).join("")}
        </select>
        <div class="qs-hint">${esc(t("settings.ui_lang.hint"))}
          <b>${esc(t("settings.ui_lang.beta"))}</b></div>
      </div>
      <div class="qs-block">
        <div class="popover-label">${esc(t("settings.lang.title"))}</div>
        <select class="js-input" id="vpReplyLang">
          ${opt("auto", t("settings.lang.auto"), replyLang)}
          ${langs.map(l => opt(l.ma, l.ten, replyLang)).join("")}
        </select>
        <div class="qs-hint">${esc(t("settings.lang.hint"))}</div>
      </div>`;

    // Nhà cung cấp giọng đọc - gộp NGAY trong nhóm giọng nói (render vào #ttsProviderHost), không tách section riêng.
    const provHtml = `
      <div class="qs-block">
        <div class="popover-label">NHÀ CUNG CẤP GIỌNG ĐỌC</div>
        <select class="js-input" id="vpProvider">
          ${opt("edge", "Edge TTS - miễn phí (mặc định)", prov)}
          ${opt("openai", "OpenAI - mượt, đa ngôn ngữ", prov)}
          ${opt("elevenlabs", "ElevenLabs - tự nhiên nhất", prov)}
        </select>
        <div id="vpOpenai" style="display:none">
          <label class="js-lbl">OpenAI API key ${oaSet ? '<span class="dim">(đã có - để trống nếu không đổi)</span>' : ""}</label>
          <input class="js-input" id="vpOaKey" type="password" placeholder="Ví dụ: sk-...">
          <label class="js-lbl">Giọng OpenAI</label>
          <select class="js-input" id="vpOaVoice">${oaVoices.map(x => opt(x, x, v.openai_tts_voice || "alloy")).join("")}</select>
        </div>
        <div id="vpEleven" style="display:none">
          <label class="js-lbl">ElevenLabs API key ${elSet ? '<span class="dim">(đã có - để trống nếu không đổi)</span>' : ""}</label>
          <input class="js-input" id="vpElKey" type="password" placeholder="Dán API key ElevenLabs">
          <label class="js-lbl">Voice ID <span class="dim">(lấy ở ElevenLabs → Voices)</span></label>
          <input class="js-input" id="vpElVoice" value="${esc(v.elevenlabs_voice || "")}" placeholder="Ví dụ: 21m00Tcm4TlvDq8ikWAM (Rachel)">
        </div>
        <div class="js-actions"><button class="gcard-btn" id="vpSave">Lưu nhà cung cấp</button></div>
        <div class="gcard-meta" id="vpStatus">Đang dùng: <b>${esc(prov)}</b>. Provider trả phí lỗi sẽ tự về Edge. Bấm ▶ Nghe thử ở dưới để nghe.</div>
      </div>`;
    el.innerHTML = `<div class="settings-page">
      <details class="settings-group" open>
        <summary><span><b>Hệ thống</b><small>Trạng thái hiện tại và lối tắt tới các nhóm chuyên sâu</small></span><span class="settings-caret">${ic("chevron-down")}</span></summary>
        <div class="settings-group-body">
          <div class="settings-status-grid">
            <div><span>Engine</span><b>${esc(engine)}</b></div>
            <div><span>Model</span><b>${esc(currentModel)}</b></div>
            <div><span>Workspace</span><b>${esc(s.workspace_name || "Javis OS")}</b></div>
            <div><span>Telegram</span><b>${telegram.enabled ? "Đang bật" : "Đang tắt"}</b></div>
          </div>
          <div class="settings-links">
            <button data-settings-go="models"><span>◈</span><b>Models</b><small>Model và nhà cung cấp</small></button>
            <button data-settings-go="channels"><span>${ic("send")}</span><b>Kênh</b><small>Telegram và kết nối chat</small></button>
            <button data-settings-go="account"><span>${ic("circle-user")}</span><b>Tài khoản</b><small>Đăng nhập, workspace, token API cho CLI</small></button>
            <button data-settings-go="logs"><span>${ic("scroll-text")}</span><b>Cập nhật</b><small>Phiên bản và nhật ký mới</small></button>
          </div>
        </div>
      </details>

      <details class="settings-group" open>
        <summary><span><b>Giao diện &amp; Brain</b><small>Hiệu năng đồ thị và cấu trúc dữ liệu</small></span><span class="settings-caret">${ic("chevron-down")}</span></summary>
        <div class="settings-group-body settings-two-col">
          <div class="settings-card">
            <div class="settings-card-head"><b>Đồ thị não</b><span class="gcard-tag">${graphOn ? "Bật" : "Tắt"}</span></div>
            <p>Đồ thị canvas nhẹ, không dùng WebGL. Mobile luôn ưu tiên chế độ nhẹ.</p>
            <div class="js-actions">
              <button class="gcard-btn ${graphOn ? "ghost" : ""}" id="setGraphToggle">${graphOn ? "Tắt đồ thị" : "Bật đồ thị"}</button>
            </div>
          </div>
          <div class="settings-card">
            <div class="settings-card-head"><b>Chuẩn hóa brain</b></div>
            <p>Gom agents, workflows, memory và skills về cấu trúc phẳng đồng nhất. Chỉ di chuyển khi đích chưa tồn tại.</p>
            <button class="gcard-btn ghost" id="setBrainMigrate">Chuẩn hóa brain đang chọn</button>
            <div class="gcard-meta" id="setBrainMigrateResult"></div>
          </div>
          <div class="settings-card">
            <div class="settings-card-head"><b>Dấu nguồn gốc ảnh AI</b><span class="gcard-tag">${stripC2pa ? "Đang gỡ" : "Đang giữ"}</span></div>
            <p>Ảnh Javis tạo ra mang sẵn dấu nguồn gốc (Content Credentials) ghi rằng ảnh do AI sinh ra. Facebook đọc dấu này để gắn nhãn "Nội dung do AI tạo" lên bài. Gỡ dấu đi thì nhãn thường không hiện nữa, nhưng bạn vẫn phải tự chịu trách nhiệm công bố nội dung AI theo luật và điều khoản của nền tảng nơi bạn đăng. Nhãn tác giả javisos.com luôn được giữ dù bật hay tắt.</p>
            <div class="js-actions">
              <button class="gcard-btn ${stripC2pa ? "ghost" : ""}" id="setC2paKeep">Giữ dấu</button>
              <button class="gcard-btn ${stripC2pa ? "" : "ghost"}" id="setC2paStrip">Gỡ dấu</button>
            </div>
            <div class="gcard-meta" id="setC2paMeta">${stripC2pa
              ? "Đang GỠ dấu nguồn gốc khỏi ảnh mới tạo. Ảnh đã tạo trước đó không đổi."
              : "Mặc định: giữ nguyên dấu nguồn gốc."}</div>
          </div>
        </div>
      </details>

      <details class="settings-group" open>
        <summary><span><b>Giọng nói, thương hiệu &amp; truy cập</b><small>TTS, avatar và tên miền riêng</small></span><span class="settings-caret">${ic("chevron-down")}</span></summary>
        <div class="settings-group-body cs-host"></div>
      </details>

      <details class="settings-group" id="setAutostartSec" style="display:none">
        <summary><span><b>Khởi động cùng Windows</b><small>Tự chạy Javis ở nền khi đăng nhập</small></span><span class="settings-caret">${ic("chevron-down")}</span></summary>
        <div class="settings-group-body">
          <div class="settings-card compact">
            <div class="settings-card-head"><b>Tự bật Javis</b><span class="gcard-tag" id="setAutoTag">…</span></div>
            <p id="setAutoMeta">Đang kiểm tra…</p>
            <button class="gcard-btn ghost" id="setAutoToggle" style="display:none"></button>
            <div class="gcard-meta" id="setAutoStatus"></div>
          </div>
        </div>
      </details>
    </div>`;
    const host = el.querySelector(".cs-host");
    const qs = document.getElementById("quickSet");
    if (qs && host) host.appendChild(qs);         // nhúng bộ điều khiển cũ vào trang (giữ handler)
    // Phải chạy TRƯỚC vòng nối [data-settings-go] bên dưới: nút "Bật ngay" nằm trong khối vừa
    // nhúng, và nó dựa vào chính vòng đó để nối hành động chuyển trang.
    await renderTfaRow();
    // Khối tài khoản vừa nhúng do app.js nuôi, và đường vào trang này KHÔNG đi qua
    // openSettings() - không gọi cái này thì ô "Tài khoản" trống trơn, ô mật khẩu hiện tại
    // không hiện ra, và nút Lưu tưởng là chưa có tài khoản nên bấm không ăn.
    if (window.__javisRefreshAuthRow) { try { await window.__javisRefreshAuthRow(); } catch (e) {} }
    if (window.__javisRefreshExtras) { try { window.__javisRefreshExtras(); } catch (e) {} }  // nạp lại avatar/tên miền
    const langHost = document.getElementById("replyLangHost");
    if (langHost) {
      langHost.innerHTML = langHtml;
      const sel = document.getElementById("vpReplyLang");
      if (sel) sel.onchange = async () => {
        const r = await saveSetting("locale", { reply_lang: sel.value });
        toast(r && r.ok ? t("settings.lang.saved") : t("settings.save_failed"), !(r && r.ok));
      };
      const selUi = document.getElementById("vpUiLang");
      if (selUi) selUi.onchange = async () => {
        // Đổi NGAY trên máy này trước, rồi mới lưu lên server. Ngôn ngữ giao diện là lựa chọn
        // THEO THIẾT BỊ (người dùng mở Javis từ nhiều máy), nên trải nghiệm phải tức thì và
        // không được phụ thuộc vào việc gọi mạng có thành công hay không.
        try { await JavisI18n.setLang(selUi.value); } catch (e) { /* noop */ }
        await saveSetting("locale", { ui_lang: selUi.value });
      };
    }
    const provHost = document.getElementById("ttsProviderHost");   // điểm neo trong nhóm giọng nói (index.html)
    if (provHost) provHost.innerHTML = provHtml;

    const provSel = document.getElementById("vpProvider");
    if (provSel) {   // guard: thiếu điểm neo (vd cache index.html cũ) thì avatar/tên miền vẫn chạy, không sập trang
      const showFields = () => {
        const p = provSel.value;
        document.getElementById("vpOpenai").style.display = p === "openai" ? "block" : "none";
        document.getElementById("vpEleven").style.display = p === "elevenlabs" ? "block" : "none";
        // Giọng Ngọc Thu/Nam Minh chỉ áp dụng cho Edge. Provider khác chọn giọng ngay trong khối trên
        // (vpOaVoice / vpElVoice) nên ẩn khối này cho gọn. Radio vẫn nằm trong DOM + giữ 'checked'
        // để app.js đọc input[name=voice] không lỗi; server dùng provider đã lưu nên giá trị này vô hại.
        const edgeVoice = document.getElementById("edgeVoiceSection");
        if (edgeVoice) edgeVoice.style.display = p === "edge" ? "" : "none";
      };
      provSel.onchange = showFields; showFields();

      const st = document.getElementById("vpStatus");
      document.getElementById("vpSave").onclick = async () => {
        st.textContent = "Đang lưu...";
        const data = {
          tts_provider: provSel.value,
          openai_tts_voice: document.getElementById("vpOaVoice").value,
          elevenlabs_voice: document.getElementById("vpElVoice").value.trim(),
        };
        const elKey = document.getElementById("vpElKey").value.trim();
        if (elKey) data.elevenlabs_key = elKey;
        const r = await saveSetting("voice", data);
        const oaKey = document.getElementById("vpOaKey").value.trim();
        if (oaKey) await saveSetting("model", { openai_api_key: oaKey });   // key OpenAI dùng chung với chat
        _settings = null;
        st.innerHTML = r.ok
          ? OK_ICON + " Đã lưu. Đang dùng: <b>" + esc(provSel.value) + "</b>. Bấm ▶ Nghe thử."
          : WARN_ICON + " Lỗi lưu.";
      };
    }

    el.querySelectorAll("[data-settings-go]").forEach(btn => {
      btn.onclick = () => navigateTo(btn.dataset.settingsGo);
    });
    const refreshSettings = () => { _settings = null; renderSettings(el); };
    const graphToggle = document.getElementById("setGraphToggle");
    if (graphToggle) graphToggle.onclick = async () => {
      graphToggle.disabled = true;
      const next = !graphOn;
      await saveSetting("dashboard", { graph_enabled: next });
      graphEnabled = next; recomputeGraph(); refreshSettings();
    };
    // Gỡ dấu nguồn gốc AI: hỏi lại một lần khi BẬT (tắt thì cho về thẳng, vì về mặc định
    // an toàn thì không cần cản). Chỉ đổi ảnh tạo MỚI, ảnh cũ giữ nguyên.
    const setC2pa = async (strip) => {
      if (strip && !confirm("Gỡ dấu nguồn gốc AI khỏi ảnh Javis tạo?\n\n"
          + "Dấu này cho người xem biết ảnh do AI sinh ra. Gỡ đi thì Facebook thường "
          + "không gắn nhãn nữa, nhưng nghĩa vụ công bố nội dung AI vẫn thuộc về bạn "
          + "với tư cách người đăng.\n\nChỉ áp dụng cho ảnh tạo từ giờ trở đi.")) return;
      await saveSetting("image", { strip_c2pa: !!strip });
      refreshSettings();
    };
    const c2paKeep = document.getElementById("setC2paKeep");
    const c2paStrip = document.getElementById("setC2paStrip");
    if (c2paKeep) c2paKeep.onclick = () => setC2pa(false);
    if (c2paStrip) c2paStrip.onclick = () => setC2pa(true);

    const migrate = document.getElementById("setBrainMigrate");
    if (migrate) migrate.onclick = async () => {
      if (!confirm("Chuẩn hóa cấu trúc brain đang chọn?\n(Có git backup và không ghi đè thư mục đích đã tồn tại.)")) return;
      migrate.disabled = true; migrate.textContent = "Đang chuẩn hóa…";
      const fd = new FormData(); fd.append("brain", fbrain());
      let r = {}; try { r = await (await fetch("/brain/migrate", { method: "POST", body: fd })).json(); }
      catch (e) { r = { ok: false, error: e.message }; }
      const result = document.getElementById("setBrainMigrateResult");
      if (result) result.innerHTML = r.ok
        ? `${OK_ICON} ${(r.moved || []).length ? "Đã di chuyển: " + (r.moved || []).map(esc).join(", ") : "Brain đã đúng cấu trúc."}${(r.skipped || []).length ? `<br><span class="dim">Bỏ qua: ${(r.skipped || []).map(esc).join("; ")}</span>` : ""}`
        : WARN_ICON + " " + esc(r.error || "Không chuẩn hóa được.");
      migrate.disabled = false; migrate.textContent = "Chuẩn hóa brain đang chọn";
    };

    const loadAutostart = async () => {
      const section = document.getElementById("setAutostartSec"); if (!section) return;
      let j = {}; try { j = await (await fetch("/autostart", { cache: "no-store" })).json(); } catch (e) { return; }
      if (!j.supported) return;
      section.style.display = ""; section.open = true;
      const on = !!j.enabled;
      document.getElementById("setAutoTag").textContent =
        on ? (j.ly_do ? "Bật nhưng không chạy" : "Bật") : "Tắt";
      // Lý do do SERVER tính (`ly_do`), không dựng lại ở đây: cùng trạng thái này hiện ở cả
      // trang Tổng quan lẫn trang Cài đặt, viết hai bản thì sớm muộn hai bản nói khác nhau.
      // Bản trước trang này bỏ qua hẳn cờ `stale`, nên cùng một máy hỏng mà hai trang nói khác nhau.
      document.getElementById("setAutoMeta").innerHTML = (on
        ? "Javis tự chạy nền khi bạn đăng nhập Windows; mở <code>localhost:7777</code> để dùng."
        : "Bật để Javis tự khởi động ở nền mỗi khi mở máy.")
        + (j.ly_do ? '<br><span class="dim">' + WARN_ICON + " " + esc(j.ly_do) + "</span>" : "");
      const button = document.getElementById("setAutoToggle");
      button.style.display = ""; button.disabled = false; button.textContent = on ? "Tắt tự khởi động" : "Bật tự khởi động";
      button.onclick = async () => {
        button.disabled = true; document.getElementById("setAutoStatus").textContent = "Đang lưu…";
        const fd = new FormData(); fd.append("enabled", on ? "0" : "1");
        let r = {}; try { r = await (await fetch("/autostart", { method: "POST", body: fd })).json(); } catch (e) { r = { ok: false, error: e.message }; }
        if (r.ok) { document.getElementById("setAutoStatus").textContent = ""; loadAutostart(); }
        else { document.getElementById("setAutoStatus").innerHTML = WARN_ICON + " " + esc(r.error || "Lỗi"); button.disabled = false; }
      };
    };
    loadAutostart();
  }

  // ============================================
  // Trang TRÒ CHUYỆN - khung chat toàn khung (mượn node chat của cockpit + sidebar lịch sử)
  // Không nhân đôi bộ máy chat: relocate chính #chatArea/#attachBar/#modelBar/#hudVoice
  // (giữ nguyên mọi handler + WebSocket + streaming đã gắn trong app.js) rồi TRẢ về HUD khi
  // rời trang. Cùng một cuộc trò chuyện hiển thị ở cả màn Javis lẫn tab này.
  // ============================================
  const CHAT_NODE_IDS = ["chatArea", "bgStrip", "attachBar", "modelBar", "hudVoice"];
  let _chatSlots = [];        // vị trí gốc từng node để trả về đúng chỗ trong HUD
  let _chatEngObs = null;     // theo dõi engineBadge gốc để phản chiếu badge trong tab

  function _injectChatCss() {
    if (document.getElementById("cp-css")) return;
    const css = `
    body.on-chat .cview-head{ display:none; }
    body.on-chat .cview-body{ padding:0; overflow:hidden; }
    /* Ẩn hẳn THÂN HUD (metrics/graph/panels) khi ở tab chat. cview fade-in 200ms của Alpine
       + canvas WebGL bị đẩy lớp compositing có thể để lộ HUD phía sau (loé orb) lúc mở tab. Giữ
       .hud-top (thanh trên toàn cục) hiển thị. Rời tab (bỏ .on-chat) HUD tự hiện lại + graph thức. */
    body.on-chat .hud-body{ visibility:hidden; }
    .chatpage{ display:flex; height:100%; min-height:0; position:relative; }
    .chatpage-side{ width:280px; flex:none; display:flex; flex-direction:column; gap:10px;
      min-height:0; padding:14px 12px; border-right:1px solid var(--glass-brd); background:var(--surface-1); }
    .chatpage-main{ flex:1 1 auto; min-width:0; display:flex; flex-direction:column; min-height:0; padding:14px 20px 16px; }
    .chatpage-bar{ display:flex; align-items:center; gap:10px; padding:0 4px 10px; flex:none; }
    .cp-title{ font-family:var(--font); font-weight:700; letter-spacing:.5px; color:var(--text); }
    .cp-engine{ margin-left:auto; font-size:12px; color:var(--text2); font-family:var(--font); white-space:nowrap; }
    .cp-ico-btn{ background:none; border:1px solid var(--border); color:var(--text2); border-radius:8px;
      padding:4px 10px; cursor:pointer; font-size:14px; line-height:1; }
    .cp-ico-btn:hover{ color:var(--accent); border-color:var(--accent); }
    .cp-ico-btn .ic{ vertical-align:-2px; }
    .cp-side-toggle{ display:none; }
    .cp-min{ display:inline-flex; align-items:center; gap:5px; font-family:var(--font); }
    .chatpage-slot{ flex:1 1 auto; min-height:0; display:flex; flex-direction:column; gap:10px; }
    /* Mở file từ tab Thư mục: trình sửa CHIẾM CHỖ khung chat, không đè lên nó. Khung chat chỉ
       bị display:none - node vẫn nguyên nên đóng trình sửa ra là còn đủ đoạn chat đang dở. */
    .chatpage-edit{ display:none; position:relative; flex:1 1 auto; min-height:0; }
    .chatpage-main.edit-on > .chatpage-slot{ display:none; }
    .chatpage-main.edit-on > .chatpage-edit{ display:flex; }
    /* Trình sửa vốn là lớp nổi neo trong .hud-center; ở đây nó là một khối bình thường của
       cột chat, nên gỡ inset/z-index đi kẻo nó bung ra ngoài khung. TRỪ khi đang phóng to
       (.ne-full) - lúc đó nó cố ý phủ kín màn hình, và :not() giữ cho khối CSS này không
       vô hiệu hoá nút phóng to (hai selector cùng độ ưu tiên, khối này nạp sau nên thắng). */
    .chatpage-edit > .note-editor:not(.ne-full){ position:static; inset:auto; z-index:auto;
      flex:1 1 auto; min-height:0; border-radius:12px; }
    .chatpage-slot > *{ width:100%; max-width:900px; margin-left:auto; margin-right:auto; }
    .chatpage-slot .transcript{ flex:1 1 auto; min-height:0; max-height:none; background:transparent; }
    /* Khung nhập giữ NGUYÊN bộ mặt của thanh nhập ở màn Javis (--bg2 + bo 18px). Trước đây
       gõ cứng rgba(24,24,34,.6) nên tông sáng lòi ra một dải xám đen giữa nền giấy. */
    .chatpage-slot .hud-voice{ background:var(--bg2); border:1px solid var(--border); border-radius:18px; }
    .chatpage-slot .attach-bar{ flex:none; }
    /* Màn hẹp: cả hàng tiêu đề phải nằm gọn MỘT dòng. Trước đây tiêu đề "Trò chuyện với Javis"
       xuống bốn dòng và chữ "Thu nhỏ" xuống hai dòng, đẩy khung chat tụt hẳn xuống - chủ repo
       chụp lại đúng cảnh đó. Ba việc: nút chỉ còn icon, tiêu đề cấm xuống dòng và tự cắt,
       nhãn engine nhường chỗ trước vì nó là thứ ít cần nhất trong ba. */
    @media (max-width:860px){
      .chatpage-bar{ gap:6px; min-width:0; }
      .cp-min span{ display:none; }
      .cp-min{ padding:4px 8px; }
      .cp-title{ font-size:14px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        min-width:0; flex:0 1 auto; }
      .cp-engine{ flex:0 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; font-size:11px; }
      .cp-side-toggle{ display:inline-block; }
      .chatpage-side{ position:absolute; left:0; top:0; bottom:0; z-index:6; width:min(84vw,300px);
        transform:translateX(-105%); transition:transform .2s ease; box-shadow:10px 0 40px var(--shadow-veil); background:var(--bg); }
      .chatpage.side-open .chatpage-side{ transform:none; }
      .chatpage-main{ padding:10px 12px 12px; }
    }`;
    const st = document.createElement("style"); st.id = "cp-css"; st.textContent = css; document.head.appendChild(st);
  }

  // DỜI một node đang cuộn thì trình duyệt ĐẶT LẠI scrollTop về 0. Đây là lý do chủ repo báo
  // (2026-08-12) "mở hội thoại cũ thì luôn bắt đầu từ câu hỏi đầu tiên": bấm một phiên ở cột
  // Lịch sử → app.js nạp tin rồi cuộn xuống đáy → NGAY SAU ĐÓ trang Trò chuyện mượn #chatArea,
  // và cú dời node xoá sạch vị trí vừa đặt. Không lỗi nào hiện ra, chỉ là mỗi lần mở đều rơi
  // về đầu một hội thoại có khi dài hàng trăm tin.
  //
  // Nhớ theo PIXEL là sai: cột chat ở màn chính hẹp hơn khung ở trang Trò chuyện, nên cùng nội
  // dung mà xuống dòng khác đi và scrollHeight đổi hẳn. Phải neo vào MỘT TIN NHẮN cụ thể rồi
  // đặt lại đúng tin đó về đúng chỗ cũ trên màn hình.
  function _neoCuon() {
    const ca = document.getElementById("chatArea");
    if (!ca) return null;
    // Đang ở đáy thì neo là "đáy" chứ không phải một tin cụ thể: có tin mới tới trong lúc
    // chuyển trang thì vẫn phải nằm ở đáy, đó mới là chỗ người dùng muốn về.
    if (ca.scrollHeight - ca.scrollTop - ca.clientHeight < 90) return { day: true };
    const tren = ca.getBoundingClientRect().top;
    for (let i = 0; i < ca.children.length; i++) {
      const n = ca.children[i], r = n.getBoundingClientRect();
      if (r.bottom > tren) return { day: false, node: n, lech: r.top - tren };
    }
    return { day: true };
  }
  function _thaCuon(neo) {
    if (!neo) return;
    const dat = () => {
      const ca = document.getElementById("chatArea");
      if (!ca) return;
      if (neo.day || !neo.node || !neo.node.isConnected) { ca.scrollTop = ca.scrollHeight; return; }
      ca.scrollTop += neo.node.getBoundingClientRect().top - ca.getBoundingClientRect().top - neo.lech;
    };
    dat();
    // Lần hai ở khung hình sau: lúc gọi dat() lần đầu, trang mới vừa dựng xong DOM nhưng bề
    // rộng cuối cùng chưa chốt, nên đo được một con số rồi nó lệch đi ngay sau đó.
    try { requestAnimationFrame(dat); } catch (e) {}
  }

  function _borrowChatNodes(into) {
    const neo = _neoCuon();
    _chatSlots = [];
    CHAT_NODE_IDS.forEach(id => {
      const n = document.getElementById(id);
      if (!n) return;
      _chatSlots.push({ node: n, parent: n.parentNode, next: n.nextSibling });
      into.appendChild(n);
    });
    _thaCuon(neo);
  }
  // ===== Cho tab "Thư mục" của khung chat MƯỢN chính panel Vault =====
  // Không dựng lại cây thứ hai. Bản đầu của tính năng này viết hẳn một module cây riêng, và
  // chủ repo chỉ ra ngay: "sao không bê nguyên cái cây y hệt bên Javis sang mà phải dựng lại".
  // Đúng - cây Vault đã có sẵn tìm theo tên/nội dung, tạo file, tạo thư mục, làm mới, tô sáng
  // file đang mở. Dựng bản thứ hai là chép lại từng đó thứ rồi để hai bản trôi lệch nhau.
  // Mượn node y như cách trang này vẫn mượn #chatArea: cùng một cây, chỉ đổi chỗ đứng.
  // ===== Trình sửa file CHIẾM CHỖ khung chat khi mở file từ tab Thư mục =====
  // Ở màn chính, trình sửa là lớp nổi đè lên visual não - chỗ đó rỗng nên đè là hợp lý. Ở
  // trang Trò chuyện thì phía dưới là khung chat đang có nội dung; đè lên nó vừa chật vừa
  // rối. Yêu cầu của chủ repo: mở file thì khung chat biến mất hẳn, chỉ còn trình sửa.
  // Vẫn MƯỢN chính #noteEditor chứ không dựng trình sửa thứ hai - cùng lý do với cây Vault.
  // `into` = khung sẽ mượn trình sửa. Bỏ trống = khung của trang Trò chuyện (#chatPageEdit).
  // Từ 0.33.4 trang Tệp tin cũng mượn chính node này (#fmEdit) thay vì bật popup riêng - một
  // trình sửa duy nhất cho cả app, không có bản nghèo hơn ở góc nào nữa.
  let _neSlot = null;
  function _borrowNoteEditor(into) {
    const ed = document.getElementById("noteEditor");
    into = into || document.getElementById("chatPageEdit");
    if (!ed || !into) return false;
    if (!_neSlot) _neSlot = { node: ed, parent: ed.parentNode, next: ed.nextSibling };
    into.appendChild(ed);
    const main = into.parentNode;
    if (main && main.classList) main.classList.add("edit-on");
    return true;
  }
  function _returnNoteEditor() {
    const s = _neSlot; if (!s || !s.parent) return;
    // Khung đang mượn = CHA hiện tại của node, không tra cứng #chatPageEdit: giờ có hai trang
    // cùng mượn được, tra cứng một cái là trang kia không bao giờ bỏ được lớp .edit-on.
    const into = s.node.parentNode;
    const main = into && into.parentNode;
    if (main && main.classList) main.classList.remove("edit-on");
    if (s.next && s.next.parentNode === s.parent) s.parent.insertBefore(s.node, s.next);
    else s.parent.appendChild(s.node);
    _neSlot = null;
  }

  let _vaultSlot = null;
  function _borrowVaultPanel(into) {
    const n = document.querySelector(".hud-left");
    if (!n || !into) return false;
    if (_vaultSlot && _vaultSlot.node === n) { into.appendChild(n); return true; }
    _vaultSlot = { node: n, parent: n.parentNode, next: n.nextSibling };
    into.appendChild(n);
    try { renderVaultTree(); } catch (e) {}
    return true;
  }
  function _returnVaultPanel() {
    const s = _vaultSlot; if (!s || !s.parent) return;
    if (s.next && s.next.parentNode === s.parent) s.parent.insertBefore(s.node, s.next);
    else s.parent.appendChild(s.node);
    _vaultSlot = null;
  }
  if (typeof window !== "undefined") {
    window.JavisVaultPanel = { borrow: _borrowVaultPanel, giveBack: _returnVaultPanel };
    // Cửa chuyển trang cho module ngoài (vd nút "Tạo Agent" ở trang Chatbot). Phơi navigateTo
    // chứ không để module tự đặt store.active: navigateTo còn dọn trang cũ, cất #quickSet và
    // vẽ lại đồ thị - bỏ qua mấy bước đó là để lại rác của trang trước trên trang sau.
    window.JavisNav = { go: navigateTo };
  }

  function _returnChatNodes() {
    if (_chatEngObs) { try { _chatEngObs.disconnect(); } catch (e) {} _chatEngObs = null; }
    // Rời trang Trò chuyện thì trả cây Vault về cột trái màn chính, nếu không màn chính mất
    // hẳn panel Vault và người dùng tưởng app hỏng. Trình sửa cũng vậy - nó đang nằm trong
    // khung sắp bị xoá, không trả về là mất luôn node và mở file ở màn chính sẽ trắng trơn.
    _returnNoteEditor();
    _returnVaultPanel();
    const neo = _neoCuon();   // đường VỀ cũng dời node, cũng mất chỗ đọc - xem _neoCuon
    for (let i = _chatSlots.length - 1; i >= 0; i--) {
      const s = _chatSlots[i];
      if (!s.parent) continue;
      if (s.next && s.next.parentNode === s.parent) s.parent.insertBefore(s.node, s.next);
      else s.parent.appendChild(s.node);
    }
    _chatSlots = [];
    document.body.classList.remove("on-chat");
    _thaCuon(neo);
  }

  function renderChat(el) {
    _injectChatCss();
    // Vào lại trang này (vd đổi brain gọi thẳng renderPage) trong khi node đang mượn ở cviewBody
    // cũ → TRẢ về HUD trước, nếu không el.innerHTML bên dưới sẽ xoá luôn #chatArea đang nằm trong đó.
    if (_chatSlots.length) _returnChatNodes();
    document.body.classList.add("on-chat");
    el.innerHTML =
      '<div class="chatpage" id="chatPage">' +
        '<aside class="chatpage-side" id="chatPageSide"></aside>' +
        '<div class="chatpage-main">' +
          '<div class="chatpage-bar">' +
            '<button class="cp-ico-btn cp-side-toggle" type="button" title="Ẩn/hiện lịch sử">' + ic("history") + '</button>' +
            // Chữ nằm trong <span> để màn hẹp ẩn được, giữ lại icon. Để chữ trần thì không
            // có cách nào ẩn mà không mất luôn cả nút.
            '<button class="cp-ico-btn cp-min" type="button" id="cpMinBtn" ' +
              'title="Thu nhỏ về màn Javis" aria-label="Thu nhỏ về màn Javis">' +
              ic("chevron-left") + '<span>Thu nhỏ</span></button>' +
            '<span class="cp-title">Trò chuyện với Javis</span>' +
            '<span class="cp-engine" id="cpEngine"></span>' +
          '</div>' +
          '<div class="chatpage-slot" id="chatPageSlot"></div>' +
          // Chỗ đứng cho TRÌNH SỬA khi mở file từ tab Thư mục. Rỗng và ẩn cho tới lúc đó.
          '<div class="chatpage-edit" id="chatPageEdit"></div>' +
        '</div>' +
      '</div>';
    const page = el.querySelector("#chatPage");
    const slot = el.querySelector("#chatPageSlot");
    _borrowChatNodes(slot);

    // Sidebar lịch sử hội thoại (dùng lại module chung của chat workspace)
    try { if (window.JavisChatSide) window.JavisChatSide.mount(el.querySelector("#chatPageSide")); } catch (e) {}

    // Badge engine: phản chiếu từ badge gốc trong HUD (không mượn node để khỏi phá HUD)
    const eb = document.getElementById("engineBadge"), cpe = el.querySelector("#cpEngine");
    if (eb && cpe) {
      const sync = () => { cpe.textContent = (eb.textContent || "").trim(); };
      sync();
      try { _chatEngObs = new MutationObserver(sync); _chatEngObs.observe(eb, { childList: true, characterData: true, subtree: true }); } catch (e) {}
    }

    // Mobile: nút lịch sử mở/đóng drawer lịch sử; bấm vào vùng chat thì đóng drawer
    const isNar = () => window.matchMedia("(max-width: 860px)").matches;
    el.querySelector(".cp-side-toggle").onclick = () => page.classList.toggle("side-open");
    // Đường VỀ. Nút phóng to ở màn Javis nay dẫn thẳng sang trang này (lớp nổi .chat-stage đã
    // bỏ), nên trang này phải có nút thu nhỏ, nếu không người dùng chỉ còn cách bấm rail.
    el.querySelector("#cpMinBtn").onclick = () => navigateTo("home");
    slot.addEventListener("click", () => { if (isNar() && page.classList.contains("side-open")) page.classList.remove("side-open"); });
    el.querySelector("#chatPageSide").addEventListener("click", (e) => {
      if (isNar() && e.target.closest(".cside-item")) page.classList.remove("side-open");
    });

    // Cuộn xuống đáy + focus ô nhập cho tiện gõ ngay
    const ca = document.getElementById("chatArea"); if (ca) ca.scrollTop = ca.scrollHeight;
    const ci = document.getElementById("chatInput"); if (ci) { try { ci.focus(); } catch (e) {} }

    _pageLeave = _returnChatNodes;   // rời tab → trả node về HUD trước khi cviewBody bị ghi đè
  }

  // ============================================
  // Alpine store + boot
  // ============================================
  document.addEventListener("alpine:init", () => {
    Alpine.store("nav", {
      active: "home",
      items: RAIL_ITEMS,
      openGroup: groupLabelOf("home"),   // accordion 2 tầng: nhóm đang mở (mặc định nhóm chứa trang đầu)
      collapsed: (() => { try { return localStorage.getItem("javis_rail_collapsed") === "1"; } catch (e) { return false; } })(),
      collapseIcon: COLLAPSE_ICON,
      // Alpine không biết từ điển i18n đổi (nó là object thuần), nên phải có một biến
      // ĐẾM phản ứng để đá vào getter. Thiếu nó thì đổi ngôn ngữ xong rail vẫn chữ cũ
      // cho tới khi F5 - một kiểu hỏng nhìn như "lưu không ăn".
      i18nTick: 0,
      get groups() { void this.i18nTick; return railGroups(); },
      get meta() { void this.i18nTick; return VIEW_META[this.active] || VIEW_META.home; },
      isOpen(label) { return this.openGroup === label; },
      toggleGroup(label) { this.openGroup = (this.openGroup === label) ? null : label; },   // 1 nhóm mở 1 lúc; bấm lại để đóng
      toggleCollapsed() {   // thu/mở sidebar: thu → chỉ còn icon; mở → đầy chữ. Nhớ lựa chọn qua localStorage.
        this.collapsed = !this.collapsed;
        try { localStorage.setItem("javis_rail_collapsed", this.collapsed ? "1" : "0"); } catch (e) {}
      },
      go(id) {
        const item = RAIL_ITEMS.find(i => i.id === id);
        if (item && item.launch) { item.launch(); recomputeGraph(); return; }  // launcher: không đổi view
        const gl = groupLabelOf(id); if (gl) this.openGroup = gl;   // giữ nhóm chứa mục vừa mở luôn bung ra
        navigateTo(id);
      },
    });
  });

  // ============================================================
  // VAULT EXPLORER (cột trái) - cây lazy + tìm note + editor overlay đè lên não
  // Tái dùng thẳng esc / _fileIcon / fbrain / recomputeGraph (đều trong IIFE này).
  // KHÔNG đụng renderFiles/openVaultTarget (deep-link chat) - openNote là luồng riêng, additive.
  // ============================================================
  const VT_IMG_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"];
  const VT_FRAME_EXTS = [".pdf"];   // trình duyệt tự hiện được -> xem tại chỗ, không mời tải về
  const VT_TEXT_EXTS = [".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".js", ".ts", ".py",
    ".html", ".css", ".toml", ".ini", ".log", ".sh", ".bat", ".xml", ".svg", ".env"];
  let _vtHome = "";            // đường dẫn (theo trần duyệt) của gốc brain
  let _vtCache = new Map();    // key -> items[] (cache con thư mục đã nạp)
  let _vtActivePath = null;    // file .md đang mở (để tô sáng trong cây)
  let _vtWired = false;        // đã gắn handler search/toolbar chưa
  let _vtIndex = null;         // chỉ mục file toàn vault (crawl client) - cho tìm theo Tên không cần server restart
  let _neSaveFn = null;        // hàm lưu của editor đang mở (cho Ctrl+S), trả true nếu lưu được
  let _neOpenRel = "";         // file đang mở trong trình sửa (đường dẫn theo TRẦN DUYỆT)
  let _neLayNoiDung = null;    // () -> nội dung ĐANG soạn (markdown nếu là .md ở chế độ Sửa)
  let _neGocText = null;       // nội dung lúc VỪA MỞ, để biết có sửa gì chưa (xem _neCoSuaChua)
  // Vệt đường đi giữa các note, y hệt lịch sử trình duyệt: bấm [[wikilink]] là đi tới, Lùi là
  // quay lại chỗ vừa đọc. Một mảng + một con trỏ, không phải hai ngăn xếp - dễ đọc hơn và
  // đúng ngữ nghĩa "đi tới giữa chừng thì cắt nhánh tiến".
  let _neLichSu = [];          // [{rel, name, ext}] theo thứ tự đi
  let _neViTri = -1;           // vị trí đang đứng trong _neLichSu
  let _neDangDiLichSu = false; // cờ: lần openNote này là do bấm Lùi/Tiến, đừng ghi thêm vệt
  const NE_LICH_SU_MAX = 50;   // vệt là để quay lại chỗ vừa đọc, không phải nhật ký cả phiên
  const _vtRaw = (rel, dl) => `/files/raw?brain=${encodeURIComponent(fbrain())}&path=${encodeURIComponent(rel)}${dl ? "&dl=1" : ""}`;
  const _vtNoAccent = (s) => (s || "").toString().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[đĐ]/g, "d").toLowerCase();

  async function _vtList(path) {
    const key = (path == null) ? "\0home" : path;
    if (_vtCache.has(key)) return _vtCache.get(key);
    const qp = (path == null) ? "" : `&path=${encodeURIComponent(path)}`;
    let items = [];
    try {
      const d = await (await fetch(`/files/list?brain=${encodeURIComponent(fbrain())}${qp}`)).json();
      if (d && !d.error) { items = d.items || []; if (path == null && d.home != null) _vtHome = d.home; }
    } catch (e) {}
    _vtCache.set(key, items);
    return items;
  }

  // Dựng lại cây nhưng GIỮ NGUYÊN các thư mục đang mở (thêm/sửa/xoá không làm sập cây).
  // revealDir (tuỳ chọn) = thư mục cần mở thêm để thấy file vừa tạo.
  async function _vtRebuildReExpand(revealDir) {
    const tree = document.getElementById("vaultTree"); if (!tree) return;
    const escSel = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/"/g, '\\"');
    // 1. Ghi lại các thư mục đang mở (childBox không ẩn).
    const wanted = new Set();
    tree.querySelectorAll(".vt-branch > .vt-children:not(.vt-hidden)").forEach(box => {
      const node = box.previousElementSibling;
      if (node && node.dataset && node.dataset.rel) wanted.add(node.dataset.rel);
    });
    // 2. Thêm chuỗi thư mục cha của revealDir (để thấy file mới dù thư mục đó đang đóng).
    if (revealDir != null && revealDir !== "") {
      let inner;
      if (_vtHome && revealDir.indexOf(_vtHome + "/") === 0) inner = revealDir.slice(_vtHome.length + 1);
      else if (!_vtHome) inner = revealDir;
      else inner = (revealDir === _vtHome ? "" : revealDir);
      const segs = inner ? inner.split("/") : [];
      let acc = _vtHome || "";
      for (const seg of segs) { acc = acc ? acc + "/" + seg : seg; wanted.add(acc); }
    }
    // 3. Dựng lại (tươi) rồi mở lại từ NÔNG tới SÂU (cha trước con).
    _vtCache.clear(); _vtIndex = null;
    await renderVaultTree();
    const list = [...wanted].sort((a, b) => a.split("/").length - b.split("/").length);
    for (const rel of list) {
      const node = tree.querySelector(`.vt-node[data-rel="${escSel(rel)}"]`);
      if (!node) continue;
      const box = node.parentElement && node.parentElement.querySelector(":scope > .vt-children");
      if (box && box.classList.contains("vt-hidden")) {
        node.click();
        for (let i = 0; i < 25 && (box.classList.contains("vt-hidden") || !box.children.length); i++) await new Promise(r => setTimeout(r, 30));
      }
    }
  }

  async function _vtAddFile(rel, isDir) {
    // Bấm ở thư mục → tạo file BÊN TRONG; bấm ở file → tạo CÙNG thư mục (thư mục cha của file).
    const dir = isDir ? rel : (rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "");
    let n = prompt("Tên file mới (vd ghi-chu):");
    if (!n) return;
    if (!/\.[a-z0-9]+$/i.test(n)) n += ".md";   // mặc định file markdown
    const path = dir ? dir + "/" + n : n;
    const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", path); fd.append("content", "");
    try { await fetch("/files/write", { method: "POST", body: fd }); } catch (e) {}
    await _vtRebuildReExpand(dir);               // giữ thư mục đang mở + bung tới thư mục vừa tạo
    const ext = "." + n.split(".").pop().toLowerCase();
    openNote(path, { name: n, ext: ext, type: "file" });
  }

  async function _vtRename(rel, oldname) {
    const nn = prompt("Tên mới:", oldname);
    if (!nn || nn === oldname) return;
    const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel); fd.append("newname", nn);
    try { await fetch("/files/rename", { method: "POST", body: fd }); } catch (e) {}
    await _vtRebuildReExpand(null);   // giữ nguyên các thư mục đang mở
  }
  async function _vtDelete(rel, name, isDir) {
    if (!confirm(`Xoá "${name}"${isDir ? " và toàn bộ bên trong" : ""}? Không hoàn tác được.`)) return;
    const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel);
    try { await fetch("/files/delete", { method: "POST", body: fd }); } catch (e) {}
    if (_vtActivePath === rel) closeNote();
    await _vtRebuildReExpand(null);   // giữ nguyên các thư mục đang mở
  }

  function _vtRowEl(it, parentPath, depth) {
    const rel = parentPath ? parentPath + "/" + it.name : it.name;
    const isDir = it.type === "dir";
    const wrap = document.createElement("div"); wrap.className = "vt-branch";
    const node = document.createElement("div");
    node.className = "vt-node"; node.dataset.rel = rel; node.dataset.name = it.name;
    node.style.paddingLeft = (6 + depth * 13) + "px";
    node.innerHTML = `<span class="vt-chev ${isDir ? "" : "leaf"}">▸</span>`
      + `<span class="vt-ico">${isDir ? ic("folder") : _fileIcon(it.ext)}</span>`
      + `<span class="vt-name">${esc(it.name)}</span>`
      + `<span class="vt-act"><button data-a="add" title="Thêm file ${isDir ? "trong thư mục này" : "cùng thư mục"}">＋</button>`
      + `<button data-a="dl" title="${isDir ? "Tải cả thư mục về máy (nén .zip)" : "Tải file về máy"}">⤓</button>`
      + `<button data-a="ren" title="Đổi tên">${ic("pencil")}</button><button data-a="del" title="Xoá">${ic("trash-2")}</button></span>`;
    if (!isDir && rel === _vtActivePath) node.classList.add("active");
    node.querySelectorAll(".vt-act button").forEach(b => b.onclick = (e) => {
      e.stopPropagation();
      const a = b.dataset.a;
      if (a === "add") _vtAddFile(rel, isDir);
      else if (a === "dl") { if (isDir) _dlFolder(rel, it.name); else _dlFile(rel); }
      else if (a === "ren") _vtRename(rel, it.name);
      else _vtDelete(rel, it.name, isDir);
    });
    wrap.appendChild(node);
    if (isDir) {
      const childBox = document.createElement("div"); childBox.className = "vt-children vt-hidden";
      wrap.appendChild(childBox);
      let loaded = false;
      node.onclick = async () => {
        const chev = node.querySelector(".vt-chev");
        const willOpen = childBox.classList.contains("vt-hidden");
        childBox.classList.toggle("vt-hidden", !willOpen);
        chev.classList.toggle("open", willOpen);
        if (willOpen && !loaded) {
          loaded = true;
          const kids = await _vtList(rel);
          if (!kids.length) childBox.innerHTML = `<div class="vt-info" style="padding-left:${18 + depth * 13}px">trống</div>`;
          else kids.forEach(k => childBox.appendChild(_vtRowEl(k, rel, depth + 1)));
        }
      };
    } else {
      node.onclick = () => openNote(rel, it);
    }
    return wrap;
  }

  // Crawl toàn vault qua /files/list (đã sống) → chỉ mục file để tìm theo TÊN không cần server restart.
  // Bám trong gốc brain (bắt đầu từ home), có trần chống treo trên vault lớn. Cache lại sau lần đầu.
  async function _vtBuildIndex() {
    if (_vtIndex) return _vtIndex;
    const SKIP = new Set([".git", "node_modules", "__pycache__", ".obsidian", ".trash", ".venv"]);
    if (!_vtHome && !_vtCache.has(" home")) await _vtList(null);
    const out = []; const queue = [_vtHome || ""]; let guard = 0;
    while (queue.length && out.length < 3000 && guard < 600) {
      guard++;
      const dir = queue.shift();
      const items = await _vtList(dir);
      for (const it of items) {
        const rel = dir ? dir + "/" + it.name : it.name;
        if (it.type === "dir") { if (!it.name.startsWith(".") && !SKIP.has(it.name)) queue.push(rel); }
        else out.push({ name: it.name, ext: it.ext, path: rel, dir: dir });
      }
    }
    _vtIndex = out;
    return out;
  }

  function _vtRelHome(dir) {
    if (!dir) return "";
    if (_vtHome && dir === _vtHome) return "";
    if (_vtHome && dir.indexOf(_vtHome + "/") === 0) return dir.slice(_vtHome.length + 1);
    return dir;
  }

  /** Xổ cây tới đúng chỗ `path` đang nằm rồi tô sáng nó, và tắt khung kết quả tìm kiếm.
   *
   * Tìm ra file mà không biết nó nằm thư mục nào thì lần sau vẫn phải đi tìm lại - đó là chỗ
   * hụt của khung tìm kiếm cũ: bấm kết quả là mở note luôn, cây phía sau không hề nhúc nhích.
   * Dùng lại `_vtRebuildReExpand` (vốn viết cho việc tạo file mới) nên không đẻ thêm cơ chế
   * xổ cây thứ hai.
   */
  async function _vtRevealInTree(path) {
    const p = String(path || "");
    const dir = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : (_vtHome || "");
    const input = document.getElementById("vaultSearch");
    if (input) input.value = "";
    const results = document.getElementById("vaultResults"); if (results) results.hidden = true;
    const clearBtn = document.getElementById("vaultSearchClear"); if (clearBtn) clearBtn.hidden = true;
    const tree = document.getElementById("vaultTree"); if (tree) tree.hidden = false;
    await _vtRebuildReExpand(dir);
    _vtMarkActive(p);
    const sel = (window.CSS && CSS.escape) ? CSS.escape(p) : p.replace(/"/g, '\\"');
    const node = tree && tree.querySelector(`.vt-node[data-rel="${sel}"]`);
    if (node && node.scrollIntoView) node.scrollIntoView({ block: "center" });
  }

  function _vtRenderResults(box, list, withSnippet) {
    box.innerHTML = "";
    list.forEach(it => {
      const el = document.createElement("div"); el.className = "vr-item";
      const sub = withSnippet ? (it.snippet || "") : _vtRelHome(it.dir);
      el.innerHTML = `<div class="vr-name"><span class="vt-ico">${_fileIcon(it.ext)}</span>${esc(it.name)}`
        + `<button class="vr-loc" type="button" title="Xổ cây tới thư mục đang chứa file này">Vị trí</button></div>`
        + (sub ? `<div class="vr-snip">${esc(sub)}</div>` : "");
      el.onclick = () => openNote(it.path, { name: it.name, ext: it.ext, type: "file" });
      el.querySelector(".vr-loc").onclick = (e) => { e.stopPropagation(); _vtRevealInTree(it.path); };
      box.appendChild(el);
    });
  }

  async function _vtNameSearch(q) {
    const box = document.getElementById("vaultResults"); if (!box) return;
    box.innerHTML = `<div class="vr-empty">Đang tìm…</div>`;
    const idx = await _vtBuildIndex();
    const nq = _vtNoAccent(q);
    const hits = idx.filter(f => _vtNoAccent(f.name).includes(nq)).slice(0, 120);
    if (!hits.length) { box.innerHTML = `<div class="vr-empty">Không thấy note nào tên khớp "${esc(q)}".</div>`; return; }
    _vtRenderResults(box, hits, false);
  }

  async function _vtSearchContent(q) {
    const box = document.getElementById("vaultResults"); if (!box) return;
    box.innerHTML = `<div class="vr-empty">Đang tìm…</div>`;
    let resp, d = {};
    try { resp = await fetch(`/files/search?brain=${encodeURIComponent(fbrain())}&q=${encodeURIComponent(q)}&limit=60`); d = await resp.json().catch(() => ({})); }
    catch (e) { resp = null; }
    if (!resp || resp.status === 404) {
      box.innerHTML = `<div class="vr-empty">Tìm theo <b>nội dung</b> cần khởi động lại Javis một lần (chạy start-javis.bat) để bật. Tạm thời hãy tìm theo <b>Tên</b>.</div>`;
      return;
    }
    if (!resp.ok) { box.innerHTML = `<div class="vr-empty">Lỗi tìm kiếm (${resp.status}).</div>`; return; }
    const items = (d && d.items) || [];
    if (!items.length) { box.innerHTML = `<div class="vr-empty">Không thấy note nào chứa "${esc(q)}".</div>`; return; }
    _vtRenderResults(box, items, true);
  }

  function _vtWire() {
    if (_vtWired) return; _vtWired = true;
    const input = document.getElementById("vaultSearch");
    const clearBtn = document.getElementById("vaultSearchClear");
    const chipName = document.getElementById("vsModeName");
    const chipContent = document.getElementById("vsModeContent");
    const tree = document.getElementById("vaultTree");
    const results = document.getElementById("vaultResults");
    if (!input || !tree) return;
    let mode = "name", t = null;
    const apply = () => {
      const q = input.value.trim();
      if (clearBtn) clearBtn.hidden = !q;
      if (!q) { results.hidden = true; tree.hidden = false; return; }   // rỗng → về cây
      tree.hidden = true; results.hidden = false;
      if (mode === "name") _vtNameSearch(q); else _vtSearchContent(q);
    };
    const deb = () => { clearTimeout(t); t = setTimeout(apply, mode === "name" ? 150 : 280); };
    input.addEventListener("input", deb);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { clearTimeout(t); apply(); }
      else if (e.key === "Escape") { input.value = ""; apply(); }
    });
    if (clearBtn) clearBtn.onclick = () => { input.value = ""; apply(); input.focus(); };
    const setMode = (m) => { mode = m; chipName.classList.toggle("active", m === "name"); chipContent.classList.toggle("active", m === "content"); apply(); };
    chipName.onclick = () => setMode("name");
    chipContent.onclick = () => setMode("content");
    const nf = document.getElementById("vtNewFile"), nd = document.getElementById("vtNewDir"), rf = document.getElementById("vtRefresh");
    if (rf) rf.onclick = () => { _vtCache.clear(); _vtIndex = null; renderVaultTree(); };
    if (nf) nf.onclick = async () => {
      let n = prompt("Tên file mới (vd ghi-chu):"); if (!n) return;
      if (!/\.[a-z0-9]+$/i.test(n)) n += ".md";   // mặc định file markdown
      const rel = _vtHome ? _vtHome + "/" + n : n;
      const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel); fd.append("content", "");
      await fetch("/files/write", { method: "POST", body: fd });
      await _vtRebuildReExpand(_vtHome || "");   // giữ thư mục đang mở
      const ext = "." + n.split(".").pop().toLowerCase();
      openNote(rel, { name: n, ext: ext, type: "file" });
    };
    if (nd) nd.onclick = async () => {
      const n = prompt("Tên thư mục mới:"); if (!n) return;
      const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", _vtHome || ""); fd.append("name", n);
      await fetch("/files/mkdir", { method: "POST", body: fd }); _vtCache.clear(); renderVaultTree();
    };
  }

  async function renderVaultTree() {
    const tree = document.getElementById("vaultTree"); if (!tree) return;
    _vtWire();
    tree.hidden = false;
    const results = document.getElementById("vaultResults"); if (results) results.hidden = true;
    tree.innerHTML = `<div class="vt-info">Đang tải…</div>`;
    const items = await _vtList(null);
    tree.innerHTML = "";
    if (!items.length) { tree.innerHTML = `<div class="vt-info">Vault trống.</div>`; return; }
    items.forEach(it => tree.appendChild(_vtRowEl(it, _vtHome || "", 0)));
  }

  function _vtMarkActive(rel) {
    _vtActivePath = rel;
    const tree = document.getElementById("vaultTree"); if (!tree) return;
    tree.querySelectorAll(".vt-node.active").forEach(n => n.classList.remove("active"));
    if (rel) {
      const sel = (window.CSS && CSS.escape) ? CSS.escape(rel) : rel.replace(/"/g, '\\"');
      const n = tree.querySelector(`.vt-node[data-rel="${sel}"]`); if (n) n.classList.add("active");
    }
  }

  function _neKeyHandler(e) {
    const ed = document.getElementById("noteEditor"); if (!ed || ed.hidden) return;
    if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) { e.preventDefault(); if (_neSaveFn) _neSaveFn(); }
    // Alt+mũi tên: đúng phím trình duyệt nào cũng dùng cho Lùi/Tiến. Chiếm phím này lúc trình
    // sửa đang mở là đúng - lùi trong note mới là thứ người ta đang nghĩ tới, không phải lùi
    // cả trang dashboard (mà lùi cả trang thì mất luôn hội thoại đang mở).
    else if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); _neDiLichSu(-1); }
    else if (e.altKey && e.key === "ArrowRight") { e.preventDefault(); _neDiLichSu(1); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeNote(); }
  }
  // Chuột có nút lùi/tiến bên hông (button 3/4): dùng được luôn, không phải học gì thêm.
  // Chặn ở `mousedown` mới cắt được hành vi lùi TRANG của trình duyệt (chặn ở mouseup là
  // muộn, trang đã đi rồi - mà lùi cả trang dashboard thì mất luôn hội thoại đang mở).
  function _neTrongEditor(target) {
    const ed = document.getElementById("noteEditor");
    return !!(ed && !ed.hidden && ed.contains(target));
  }
  document.addEventListener("mousedown", (e) => {
    if ((e.button === 3 || e.button === 4) && _neTrongEditor(e.target)) e.preventDefault();
  });
  document.addEventListener("auxclick", (e) => {
    if (!_neTrongEditor(e.target)) return;
    if (e.button === 3) { e.preventDefault(); _neDiLichSu(-1); }
    else if (e.button === 4) { e.preventDefault(); _neDiLichSu(1); }
  });
  function closeNote() {
    const ed = document.getElementById("noteEditor"); if (!ed) return;
    ed.hidden = true; ed.classList.remove("ne-full");
    // Đóng trình sửa ở trang Trò chuyện = trả chỗ lại cho khung chat. Không trả thì khung chat
    // vẫn bị ẩn và người dùng nhìn vào một trang trống, tưởng chat hỏng.
    _returnNoteEditor();
    document.getElementById("neBody").innerHTML = ""; document.getElementById("neActions").innerHTML = "";
    _neSaveFn = null;
    _neOpenRel = "";
    _neLayNoiDung = null; _neGocText = null;
    // Vệt đường đi SỐNG QUA lần đóng: đóng trình sửa để quay sang chat về chính note đó rồi mở
    // lại là luồng thường gặp nhất, xoá vệt ở đây là bắt người ta đi lại từ đầu.
    document.removeEventListener("keydown", _neKeyHandler, true);
    _vtMarkActive(null);
    // Trang Tệp tin vừa mượn trình sửa: đóng ra thì danh sách file phải khớp lại - ngay trong
    // trình sửa có nút đổi tên và xoá, quay về mà vẫn thấy tên cũ là nhìn vào một danh sách sai.
    if (typeof _fmSauKhiDong === "function") { const f = _fmSauKhiDong; _fmSauKhiDong = null; try { f(); } catch (e) {} }
    try { recomputeGraph(); } catch (e) {}   // chạy lại não (đã gate active===home + không lite + studio đóng)
  }
  // Đổi tên file đang mở: lưu nội dung hiện tại trước (giữ chữ đã gõ), đổi tên, rồi mở lại ở tên mới.
  async function _neRenameCur(rel, it) {
    const oldname = (it && it.name) || rel.split("/").pop();
    const nn = prompt("Tên mới:", oldname);
    if (!nn || nn === oldname) return;
    if (_neSaveFn) { try { await _neSaveFn(); } catch (e) {} }
    const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel); fd.append("newname", nn);
    try { await fetch("/files/rename", { method: "POST", body: fd }); } catch (e) {}
    await _vtRebuildReExpand(null);
    const dir = rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "";
    const newRel = dir ? dir + "/" + nn : nn;
    const ext = nn.includes(".") ? "." + nn.split(".").pop().toLowerCase() : ".md";
    // Vệt đường đi đang trỏ vào TÊN CŨ ở mọi bước từng ghé file này. Không sửa lại thì bấm Lùi
    // sẽ đi mở một đường dẫn không còn tồn tại.
    _neLichSu.forEach(n => { if (n.rel === rel) { n.rel = newRel; n.name = nn; n.ext = ext; } });
    openNote(newRel, { name: nn, ext: ext, type: "file" });
  }
  async function _neDeleteCur(rel, it) {
    const name = (it && it.name) || rel.split("/").pop();
    if (!confirm(`Xoá "${name}"? Không hoàn tác được.`)) return;
    const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel);
    try { await fetch("/files/delete", { method: "POST", body: fd }); } catch (e) {}
    // Ghim trỏ tới file vừa xoá thì bỏ, đừng để Javis đi mở một đường dẫn không còn tồn tại.
    try {
      const p = window.JavisPin && window.JavisPin.get();
      if (p && p.rel === rel) window.JavisPin.clear();
    } catch (e) {}
    // Cùng lý do: rút file đã xoá khỏi vệt đường đi, kẻo bấm Lùi lại rơi vào nó.
    const truoc = _neLichSu.slice(0, _neViTri + 1).filter(n => n.rel !== rel).length;
    _neLichSu = _neLichSu.filter(n => n.rel !== rel);
    _neViTri = Math.min(truoc - 1, _neLichSu.length - 1);
    closeNote();
    await _vtRebuildReExpand(null);
  }
  function _neCommonBtns(actions, rel, it) {
    // label là HTML (icon SVG), không phải chữ trơ - dùng innerHTML kẻo in ra mã.
    const mk = (label, title, fn) => { const b = document.createElement("button"); b.innerHTML = label; if (title) b.title = title; b.onclick = fn; return b; };
    const ed = document.getElementById("noteEditor");
    actions.appendChild(mk(ic("pencil"), "Đổi tên file", () => _neRenameCur(rel, it)));
    actions.appendChild(mk(ic("trash-2"), "Xoá file", () => _neDeleteCur(rel, it)));
    actions.appendChild(mk("↗", "Mở tab mới", () => window.open(_vtRaw(rel), "_blank")));
    actions.appendChild(mk("⤓ Tải", "Tải file về máy", () => _dlFile(rel)));
    actions.appendChild(mk(ic("maximize"), "Phóng to / thu nhỏ", () => ed.classList.toggle("ne-full")));
    actions.appendChild(mk(X_ICON, "Đóng (Esc)", closeNote));
  }
  function _neRenderDownload(body, actions, rel, it) {
    body.className = "ne-body";
    body.innerHTML = `<div class="ne-dl"><div class="ne-dl-ico">${_fileIcon(it.ext)}</div>`
      + `<div>Loại file này không xem trực tiếp - hãy tải về.<br><b>${esc(it.name)}</b></div>`
      + `<div><a href="${_vtRaw(rel, 1)}">⤓ Tải về</a> &nbsp;·&nbsp; <a href="${_vtRaw(rel)}" target="_blank">↗ Mở tab mới</a></div></div>`;
    _neCommonBtns(actions, rel, it);
  }
  // File KHÔNG TỒN TẠI là chuyện khác hẳn file không xem trực tiếp được, nhưng trước bản này cả
  // hai rơi chung một cửa và người dùng nhận đúng một câu: "loại file này không xem trực tiếp -
  // hãy tải về". Câu đó sai sự thật khi link trỏ trượt, lại còn mời tải một thứ không có, nên
  // người dùng đi nghi ngờ loại file thay vì nghi ngờ cái link. Nói thẳng đường dẫn đã thử là
  // biến một cú bấm chết thành một báo lỗi sửa được.
  function _neRenderMissing(body, actions, rel, it, loi) {
    body.className = "ne-body";
    body.innerHTML = `<div class="ne-dl"><div class="ne-dl-ico">${_fileIcon(it.ext)}</div>`
      + `<div><b>${esc(loi || "Không tìm thấy file")}</b><br>`
      + `Link trỏ tới <code>${esc(rel)}</code> nhưng chỗ đó không có gì.<br>`
      + `File có thể đã đổi tên, bị xoá, hoặc link ghi sai đường dẫn.</div>`
      + `<div class="ne-hits" id="neMissHits"><span class="dim">Đang tìm file tên gần giống…</span></div></div>`;
    const ed = document.getElementById("noteEditor");
    actions.innerHTML = "";
    const b = document.createElement("button");
    b.innerHTML = X_ICON; b.title = "Đóng (Esc)"; b.onclick = closeNote;
    actions.appendChild(b);
    if (ed) ed.classList.remove("ne-full");
    _neTimFileGan(String(rel).split("/").pop(), body.querySelector("#neMissHits"));
  }
  // Link hụt thường KHÔNG phải file đã mất - chỉ là tên trong chat lệch tên trên đĩa (hay gặp
  // nhất: chat ghi có dấu tiếng Việt còn file lưu không dấu). /files/search?mode=name khớp cả hai
  // chiều dấu, nên đi tìm hộ rồi bày ra cho bấm một phát là mở, thay vì bỏ người dùng ở ngõ cụt.
  async function _neTimFileGan(ten, host) {
    if (!host || !ten) return;
    let items = [];
    try {
      const r = await fetch(`/files/search?brain=${encodeURIComponent(fbrain())}&q=${encodeURIComponent(ten)}&mode=name&limit=8`);
      items = ((await r.json()) || {}).items || [];
    } catch (e) {}
    if (!host.isConnected) return;
    if (!items.length) { host.innerHTML = `<span class="dim">Tìm cả brain cũng không có file nào tên gần giống.</span>`; return; }
    host.innerHTML = `<span class="dim">${items.length === 1 ? "Có lẽ là file này:" : "Có lẽ là một trong các file này:"}</span>`;
    items.forEach(hit => {
      const b = document.createElement("button");
      b.type = "button";
      // Cắt tiền tố nhà brain cho dễ đọc: người dùng nghĩ theo "06 - Sources/x.md", không phải
      // theo đường dẫn đầy đủ trên đĩa.
      const nhan = (_vtHome && String(hit.path || "").indexOf(_vtHome + "/") === 0)
        ? hit.path.slice(_vtHome.length + 1) : (hit.path || hit.name);
      b.innerHTML = `${_fileIcon(hit.ext || "")} ${esc(nhan)}`;
      b.onclick = () => {
        openNote(hit.path, { name: hit.name, ext: hit.ext || "", type: "file" });
        try { _vtRevealInTree(hit.path); } catch (e) {}
      };
      host.appendChild(b);
    });
  }

  // Nạp turndown (HTML→markdown) LAZY, chỉ khi cần lưu bản WYSIWYG. + plugin GFM (bảng).
  let _tdPromise = null, _td = null;
  function _ensureTurndown() {
    if (window.TurndownService) return Promise.resolve();
    if (_tdPromise) return _tdPromise;
    const load = (src) => new Promise((res) => { const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = res; document.head.appendChild(s); });
    _tdPromise = load("https://unpkg.com/turndown@7.2.0/dist/turndown.js")
      .then(() => load("https://unpkg.com/turndown-plugin-gfm@1.0.2/dist/turndown-plugin-gfm.js"));
    return _tdPromise;
  }
  // HTML (bản render đang sửa) → markdown. GIỮ [[wikilink]] và ![[ảnh]] qua luật riêng theo data-vault-path.
  function _mdFromHtml(html) {
    if (!window.TurndownService) return null;
    if (!_td) {
      _td = new window.TurndownService({ headingStyle: "atx", bulletListMarker: "-", codeBlockStyle: "fenced", emDelimiter: "*" });
      try { if (window.turndownPluginGfm) _td.use(window.turndownPluginGfm.gfm); } catch (e) {}
      _td.addRule("wikilink", { filter: (n) => n.nodeName === "A" && n.getAttribute("data-vault-path") != null,
        replacement: (c, n) => {
          const p = n.getAttribute("data-vault-path");
          const cls = n.getAttribute("class") || "";
          if (n.querySelector && n.querySelector("img")) return c;   // ảnh vault bọc link: giữ ![[..]] từ luật ảnh
          if (cls.indexOf("jv-fcode") >= 0) return c;                // đường dẫn trong inline code: giữ nguyên `..`
          if (cls.indexOf("jv-wikilink") >= 0) {                     // wikilink thật: giữ [[path]] / [[path|alias]]
            const alias = n.getAttribute("data-wiki-alias");
            return "[[" + p + (alias ? "|" + alias : "") + "]]";
          }
          return "[" + (c || p) + "](" + p + ")";                    // link markdown vault: giữ dạng [chữ](đường-dẫn)
        } });
      _td.addRule("wikiimg", { filter: (n) => n.nodeName === "IMG" && n.getAttribute("data-vault-path") != null,
        replacement: (c, n) => "![[" + n.getAttribute("data-vault-path") + "]]" });
      // Các khối render đặc biệt của mdToHtml phải TRẢ VỀ đúng fence gốc khi lưu bản WYSIWYG,
      // nếu không nội dung note bị phá (mất truy vấn dataview, mất code). Round-trip:
      // Frontmatter: trả lại NGUYÊN VĂN khối `---...---`. Thiếu luật này thì mỗi lần lưu một
      // note có frontmatter là hỏng metadata (`---` thành `* * *`) - lỗi mất dữ liệu thật.
      _td.addRule("jvfrontmatter", { filter: (n) => n.nodeName === "DIV" && n.classList.contains("jv-fm"),
        replacement: (c, n) => {
          let t = n.getAttribute("data-fm") || "";
          try { t = decodeURIComponent(t); } catch (e) {}
          return t.replace(/\s+$/, "");   // turndown tự chèn dòng trống ngăn cách khối
        } });
      _td.addRule("jvdataview", { filter: (n) => n.nodeName === "DIV" && n.classList.contains("jv-dataview"),
        replacement: (c, n) => {
          let q = n.getAttribute("data-dv-q") || "";
          try { q = decodeURIComponent(q); } catch (e) {}
          return "\n\n```" + (n.getAttribute("data-dv-lang") || "dataview") + "\n" + q + "\n```\n\n";
        } });
      _td.addRule("jvcodewrap", { filter: (n) => n.nodeName === "DIV" && n.classList.contains("code-wrap"),
        replacement: (c, n) => {
          const pre = n.querySelector("pre.code-block");
          let lang = (n.querySelector(".code-lang") || { textContent: "" }).textContent.trim();
          if (lang === "text") lang = "";
          return "\n\n```" + lang + "\n" + (pre ? pre.textContent : "") + "\n```\n\n";
        } });
      _td.addRule("jvartifact", { filter: (n) => n.nodeName === "DIV" && n.classList.contains("jv-art"),
        replacement: (c, n) => {
          const art = window.JavisArtifacts && window.JavisArtifacts.get && window.JavisArtifacts.get(n.getAttribute("data-art"));
          if (!art) return c;   // registry mất (hiếm): giữ chữ, còn hơn mất trắng
          return "\n\n```" + (art.lang || (art.type === "code" ? "" : art.type)) + "\n" + art.code + "\n```\n\n";
        } });
    }
    try { return _td.turndown(html); } catch (e) { return null; }
  }

  // Thanh công cụ markdown - hoạt động CẢ trên bản render (WYSIWYG, execCommand) LẪN nguồn thô (chèn cú pháp).
  // Bảng lệnh nay ở editor-cmds.js (window.JavisEditorCmds), KHÔNG còn nằm trong hàm này:
  // cùng một bảng đó nuôi luôn phím tắt và menu gõ "/". Để mỗi nơi giữ bảng riêng là ba chỗ
  // trôi khỏi nhau ngay lần thêm lệnh đầu tiên. Hàm này giờ chỉ còn việc vẽ nút.
  function _neBuildToolbar(host, ctx) {
    if (!host) return;
    const EC = window.JavisEditorCmds;
    if (!EC) { host.innerHTML = ""; return; }   // index.html nạp editor-cmds.js TRƯỚC console.js
    host.innerHTML = "";
    EC.CMDS.forEach((c) => {
      const b = document.createElement("button"); b.type = "button";
      b.title = EC.btnTitle(c);                  // nhãn kèm phím tắt, vd "Checkbox (Ctrl+Shift+9)"
      // Nhãn nút có hai loại: chuỗi SVG do ic() sinh ra, và chữ thuần ("B", "</>", "―").
      // Cả hai đều đi bằng innerHTML - textContent sẽ in nguyên thẻ <svg ...> ra màn hình.
      // Chữ thuần bắt buộc escape, nếu không nút "</>" bị trình duyệt nuốt mất.
      b.innerHTML = EC.btnHtml(c);
      if (c.btn.style) b.style.cssText += c.btn.style;
      b.onmousedown = (e) => e.preventDefault();
      b.onclick = () => EC.run(c.id, ctx);
      host.appendChild(b);
    });
  }

  // Cho khung sua file trong chat (file-editor.js) dung LAI dung bo may WYSIWYG cua editor cay:
  // nap Turndown, doi HTML<->markdown (giu [[wikilink]]/![[anh]]), va thanh cong cu markdown.
  if (typeof window !== "undefined") {
    window.JavisNoteEditor = {
      ensureTurndown: _ensureTurndown,
      mdFromHtml: _mdFromHtml,
      buildToolbar: _neBuildToolbar,
    };
  }

  // ============================================================
  // LÙI / TIẾN giữa các note - vệt đường đi kiểu trình duyệt
  //
  // Vì sao cần: bấm một [[wikilink]] là rời khỏi note đang đọc, và trước bản này KHÔNG có
  // đường về - phải đi tìm lại file cũ trong cây. Đọc wiki là đi theo chuỗi liên kết, nên
  // thiếu nút Lùi thì mỗi cú bấm link là một quyết định một chiều.
  //
  // Ba lựa chọn thiết kế, cả ba đều theo hướng "quen tay hơn là thông minh":
  //   1. Nút nằm BÊN TRÁI tên file, hình mũi tên ‹ › - đúng chỗ mọi trình duyệt đặt nó.
  //   2. Hết chỗ để đi thì nút MỜ ĐI chứ không biến mất. Nút ẩn hiện làm thanh tiêu đề nhảy
  //      và người dùng không bao giờ học được là có nút đó.
  //   3. Tooltip GỌI TÊN file sẽ tới ("Lùi về: Bát Giác Offer.md"), không phải chữ "Lùi" trơn.
  //      Đi sâu bốn năm tầng link thì nhớ được mình từ đâu tới là chuyện không dễ.
  // ============================================================
  // Luật đi vệt, tách riêng và THUẦN (không đụng DOM, không đụng biến ngoài) để test chạy
  // được thẳng vào nó. Ba luật, và luật thứ hai là thứ dễ bị sửa hỏng nhất về sau.
  function _neVetMoi(lichSu, viTri, nut, max) {
    if (!nut || !nut.rel) return { lichSu, viTri };
    // 1. Mở lại đúng file đang đứng (bấm lại chính nó trong cây) thì không đẻ thêm một bước.
    if (viTri >= 0 && lichSu[viTri] && lichSu[viTri].rel === nut.rel) {
      const ra = lichSu.slice(); ra[viTri] = nut;
      return { lichSu: ra, viTri };
    }
    // 2. Đang đứng GIỮA vệt mà đi chỗ mới thì nhánh TIẾN bị cắt - y như trình duyệt. Không cắt
    //    thì bấm Tiến sẽ nhảy sang một nhánh người ta đã bỏ, và không cách nào đoán ra vì sao.
    const ra = lichSu.slice(0, viTri + 1);
    ra.push(nut);
    // 3. Vệt là để quay lại chỗ vừa đọc, không phải nhật ký cả phiên: quá trần thì rụng đầu.
    while (ra.length > max) ra.shift();
    return { lichSu: ra, viTri: ra.length - 1 };
  }

  function _neDayLichSu(rel, it) {
    const nut = { rel: rel || "", name: (it && it.name) || String(rel || "").split("/").pop(),
                  ext: (it && it.ext) || "" };
    const kq = _neVetMoi(_neLichSu, _neViTri, nut, NE_LICH_SU_MAX);
    _neLichSu = kq.lichSu; _neViTri = kq.viTri;
  }

  // Nội dung có khác lúc vừa mở không. So với BẢN ĐÃ VÒNG QUA markdown lúc mở, không phải
  // chữ thô đọc từ đĩa: bản render WYSIWYG đổi lại thành markdown luôn lệch đôi chỗ so với
  // file gốc (turndown chuẩn hoá dấu, xuống dòng). So với file gốc thì mỗi lần chỉ ĐỌC rồi
  // rời đi cũng bị tính là có sửa, và Javis sẽ âm thầm ghi đè định dạng của file đó.
  function _neCoSuaChua() {
    if (!_neSaveFn || !_neLayNoiDung || _neGocText == null) return false;
    try { return _neLayNoiDung() !== _neGocText; } catch (e) { return false; }
  }

  function _neVeNutLui() {
    const host = document.getElementById("neNav");
    if (!host) return;
    const truoc = _neViTri > 0 ? _neLichSu[_neViTri - 1] : null;
    const sau = _neViTri >= 0 && _neViTri < _neLichSu.length - 1 ? _neLichSu[_neViTri + 1] : null;
    host.innerHTML = "";
    [[truoc, -1, "chevron-left", "Lùi về", "Chưa đi đâu để lùi về", "Alt+←"],
     [sau, 1, "chevron-right", "Tiến tới", "Chưa có note nào ở phía trước", "Alt+→"]]
      .forEach(([dich, buoc, icon, nhan, khiTrong, phim]) => {
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = ic(icon);
        b.disabled = !dich;
        b.title = dich ? `${nhan}: ${dich.name} (${phim})` : `${khiTrong} (${phim})`;
        b.setAttribute("aria-label", b.title);
        b.onclick = () => _neDiLichSu(buoc);
        host.appendChild(b);
      });
  }

  async function _neDiLichSu(buoc) {
    const dich = _neLichSu[_neViTri + buoc];
    if (!dich) return;
    // Giữ chữ đang gõ dở: lưu TRƯỚC khi rời đi, và lưu hỏng thì KHÔNG đi. Đi tiếp lúc đó là
    // vứt bài người ta vừa viết mà không nói một câu nào.
    if (_neCoSuaChua() && (await _neSaveFn()) === false) return;
    _neViTri += buoc;
    _neDangDiLichSu = true;
    openNote(dich.rel, { name: dich.name, ext: dich.ext, type: "file" });
    try { _vtRevealInTree(dich.rel); } catch (e) {}
  }

  async function openNote(rel, it) {
    const ed = document.getElementById("noteEditor"); if (!ed) return;
    it = it || {}; const ext = (it.ext || "").toLowerCase();
    // Rời một file đang sửa dở (bấm [[wikilink]], bấm file khác trong cây) thì lưu lại trước.
    // Trước bản này chữ vừa gõ bay sạch, im lặng - và nút Lùi/Tiến làm chuyện rời file xảy ra
    // thường xuyên hơn hẳn nên không vá thì đây thành cái bẫy.
    if (_neOpenRel && _neOpenRel !== (rel || "") && _neCoSuaChua()) {
      if ((await _neSaveFn()) === false) return;   // lưu hỏng thì ở lại, lỗi hiện trên nút Lưu
    }
    const laLichSu = _neDangDiLichSu;
    _neDangDiLichSu = false;
    if (!laLichSu) _neDayLichSu(rel, it);
    _neVeNutLui();
    ed.hidden = false; ed.classList.remove("ne-full");
    _neOpenRel = rel || "";     // để chip "file đang mở" biết có cần nạp lại hay chỉ cần đưa mắt về
    _neLayNoiDung = null; _neGocText = null;   // file mới: mốc so sánh dựng lại ở dưới
    // Đang ở trang Trò chuyện thì trình sửa chiếm chỗ khung chat thay vì đè lên visual não
    // (thứ không hề hiện ở trang này). Trang Tệp tin cũng vậy: chiếm chỗ danh sách file.
    if (document.body.classList.contains("on-chat")) _borrowNoteEditor();
    else if (document.body.classList.contains("on-files")) _borrowNoteEditor(document.getElementById("fmEdit"));
    document.removeEventListener("keydown", _neKeyHandler, true);
    document.addEventListener("keydown", _neKeyHandler, true);
    try { if (window.__javisGraph && window.__javisGraph.pause) window.__javisGraph.pause(); } catch (e) {}
    document.getElementById("neTitle").innerHTML = `<span class="vt-ico">${_fileIcon(ext)}</span>${esc(it.name || rel)}`;
    const actions = document.getElementById("neActions"); const body = document.getElementById("neBody");
    actions.innerHTML = ""; body.innerHTML = ""; body.className = "ne-body"; _neSaveFn = null;

    if (VT_IMG_EXTS.includes(ext)) {
      body.innerHTML = `<div class="ne-img"><img src="${_vtRaw(rel)}" alt="${esc(it.name || "")}"></div>`;
      _neCommonBtns(actions, rel, it); _vtMarkActive(null); return;
    }
    // .pdf: trình duyệt tự đọc được, nên xem NGAY tại chỗ thay vì mời tải về. Popup cũ của trang
    // Tệp tin có sẵn khung xem này; bỏ popup mà không mang theo là mất một thứ đang chạy tốt.
    if (VT_FRAME_EXTS.includes(ext)) {
      body.innerHTML = `<iframe class="ne-frame" src="${_vtRaw(rel)}"></iframe>`;
      _neCommonBtns(actions, rel, it); _vtMarkActive(null); return;
    }
    if (VT_TEXT_EXTS.includes(ext)) {
      body.innerHTML = `<div class="vt-info" style="padding:16px">Đang mở…</div>`;
      let resp, d = {};
      try { resp = await fetch(`/files/read?brain=${encodeURIComponent(fbrain())}&path=${encodeURIComponent(rel)}`); d = await resp.json().catch(() => ({})); }
      catch (e) { _neRenderDownload(body, actions, rel, it); return; }
      // 404 = không có file ở đường dẫn đó (server trả rõ như vậy). Mọi lỗi còn lại - nhị phân,
      // quá to - vẫn là file CÓ THẬT nên đường tải về mới có nghĩa.
      if (resp.status === 404) { _neRenderMissing(body, actions, rel, it, d.error); return; }
      if (!resp.ok || d.error || d.content == null) { _neRenderDownload(body, actions, rel, it); return; }
      // Mở file để sửa = GHIM nó vào khung chat làm file đầu vào. Mở file khác thì thay chỗ,
      // nên chỉ cần gọi set() ở đây, không phải dọn ghim cũ. Đóng trình sửa KHÔNG bỏ ghim:
      // đóng ra để quay sang chat về chính file đó là luồng thường gặp nhất.
      try { if (window.JavisPin && d.abs) window.JavisPin.set({ name: d.name || it.name || rel, rel, abs: d.abs }); } catch (e) {}
      const isMd = ext === ".md";
      if (isMd) { try { await _ensureTurndown(); } catch (e) {} }   // để lưu bản render (WYSIWYG) → markdown
      const wysOk = isMd && !!window.TurndownService;
      body.className = "ne-body" + (isMd ? (wysOk ? " ne-md mode-wys" : " ne-md mode-source") : " mode-source");
      body.innerHTML = isMd
        ? `<div class="ne-fmt"></div><div class="ne-panes"><div class="ne-prev ne-wys" id="neWys" contenteditable="true" spellcheck="false"></div><div class="ne-src"><textarea id="neText" spellcheck="false"></textarea></div></div>`
        : `<div class="ne-src"><textarea id="neText" spellcheck="false"></textarea></div>`;
      const ta = document.getElementById("neText"); ta.value = d.content || "";
      let mdGetter = null;
      if (isMd) {
        const wys = document.getElementById("neWys");
        wys.innerHTML = window.mdToHtml ? window.mdToHtml(ta.value) : esc(ta.value);
        let curMode = wysOk ? "wys" : "source";
        // Tick checkbox task trong bản render -> tự lưu ngay (như Obsidian), khỏi bấm nút Lưu
        wys.addEventListener("jv-task-toggle", () => { if (_neSaveFn) _neSaveFn(); });
        const wysToSrc = () => { const md = _mdFromHtml(wys.innerHTML); if (md != null) ta.value = md; };
        const srcToWys = () => { wys.innerHTML = window.mdToHtml ? window.mdToHtml(ta.value) : esc(ta.value); };
        _neBuildToolbar(body.querySelector(".ne-fmt"), { mode: () => curMode, ta, wys });   // thanh công cụ chạy cả 2 chế độ
        mdGetter = () => (curMode === "wys" ? (_mdFromHtml(wys.innerHTML) != null ? _mdFromHtml(wys.innerHTML) : ta.value) : ta.value);
        const seg = document.createElement("span"); seg.className = "ne-seg";
        [["Sửa", "mode-wys"], ["Nguồn", "mode-source"]].forEach(([lbl, cls]) => {
          const b = document.createElement("button"); b.textContent = lbl; b.classList.toggle("active", cls === (curMode === "wys" ? "mode-wys" : "mode-source"));
          b.onclick = () => {
            const toSrc = cls === "mode-source";
            if (toSrc && curMode === "wys") wysToSrc();
            else if (!toSrc && curMode === "source") srcToWys();
            curMode = toSrc ? "source" : "wys";
            body.className = "ne-body ne-md " + cls;
            seg.querySelectorAll("button").forEach(x => x.classList.remove("active")); b.classList.add("active");
          };
          seg.appendChild(b);
        });
        actions.appendChild(seg);
      } else {
        // File nguồn (.html, .css, .js, .json, .py...): tô màu cú pháp cho dễ đọc. .md không
        // đi nhánh này vì thanh công cụ soạn thảo tự chèn chữ vào textarea mà không bắn sự
        // kiện input, lớp màu sẽ lệch khỏi nội dung thật.
        try {
          const hlLang = window.JavisCodeHL ? window.JavisCodeHL.langFromPath(rel) : "";
          if (hlLang) window.JavisCodeHL.attach(ta, hlLang);
        } catch (e) {}
      }
      const saveBtn = document.createElement("button"); saveBtn.innerHTML = SAVE_ICON + " Lưu"; saveBtn.title = "Lưu (Ctrl+S)";
      // Mốc so sánh "đã sửa gì chưa": lấy SAU khi dựng xong khung soạn, tức là bản đã vòng
      // qua markdown một lượt - xem chú thích ở `_neCoSuaChua`.
      _neLayNoiDung = () => (mdGetter ? mdGetter() : ta.value);
      try { _neGocText = _neLayNoiDung(); } catch (e) { _neGocText = null; }
      // Trả true/false chứ không nuốt kết quả: chỗ gọi tự động (rời file, bấm Lùi) phải biết
      // lưu có ăn không để quyết định có đi tiếp hay ở lại.
      _neSaveFn = async () => {
        const content = _neLayNoiDung();
        const fd = new FormData(); fd.append("brain", fbrain()); fd.append("path", rel); fd.append("content", content);
        try {
          const r = await (await fetch("/files/write", { method: "POST", body: fd })).json();
          if (r.ok) {
            saveBtn.innerHTML = CHECK_ICON + " Đã lưu"; saveBtn.classList.add("ne-saved");
            setTimeout(() => { saveBtn.innerHTML = SAVE_ICON + " Lưu"; saveBtn.classList.remove("ne-saved"); }, 1400);
            _neGocText = content;   // vừa lưu = mốc mới, không thì rời file lại lưu lần nữa
            return true;
          }
          saveBtn.innerHTML = WARN_ICON + " Lỗi";
        } catch (e) { saveBtn.innerHTML = WARN_ICON + " Lỗi"; }
        return false;
      };
      saveBtn.onclick = _neSaveFn;
      actions.appendChild(saveBtn);
      _neCommonBtns(actions, rel, it);
      _vtMarkActive(isMd ? rel : null);
      ta.focus();
      return;
    }
    _neRenderDownload(body, actions, rel, it); _vtMarkActive(null);
  }

  // Tooltip NHANH cho rail khi thu gọn (native title trễ ~500ms). 1 node body-level, thoát mọi overflow clip.
  // Từ điển i18n về (hoặc user đổi ngôn ngữ giao diện): đá biến đếm cho Alpine vẽ lại rail
  // và tiêu đề trang, rồi quét lại các nhãn tĩnh trong index.html.
  window.addEventListener("javis:i18n", () => {
    try {
      const st = window.Alpine && Alpine.store("nav");
      if (st) st.i18nTick++;
    } catch (e) { /* Alpine chưa dựng xong - lát nữa nó đọc từ điển đã đầy rồi */ }
    try { window.JavisI18n && JavisI18n.applyDom(); } catch (e) { /* noop */ }
  });

  function initRailTooltip() {
    const nav = document.querySelector(".rail-nav"); if (!nav) return;
    let tip = document.getElementById("railTip");
    if (!tip) { tip = document.createElement("div"); tip.id = "railTip"; tip.className = "rail-tip"; document.body.appendChild(tip); }
    let timer = null, cur = null;
    const collapsed = () => document.body.classList.contains("rail-collapsed");
    nav.addEventListener("mouseover", (e) => {
      const btn = e.target.closest(".rail-item"); if (!btn || !collapsed() || btn === cur) return;
      cur = btn;
      if (btn.hasAttribute("title")) { btn.dataset.tip = btn.getAttribute("title"); btn.removeAttribute("title"); }  // chặn tooltip native chậm
      clearTimeout(timer);
      timer = setTimeout(() => {
        const label = btn.dataset.tip || ""; if (!label) return;
        const r = btn.getBoundingClientRect();
        tip.textContent = label;
        tip.style.top = (r.top + r.height / 2) + "px";
        tip.style.left = (r.right + 8) + "px";
        tip.classList.add("show");
      }, 90);
    });
    nav.addEventListener("mouseout", (e) => {
      const btn = e.target.closest(".rail-item"); if (!btn) return;
      if (e.relatedTarget && btn.contains(e.relatedTarget)) return;
      clearTimeout(timer); tip.classList.remove("show");
      if (btn.dataset.tip && !btn.hasAttribute("title")) btn.setAttribute("title", btn.dataset.tip);   // trả title cho accessibility
      if (btn === cur) cur = null;
    });
  }

  // ── Đèn báo não: bộ não (Claude/Codex) mất đăng nhập thì thắp dải đỏ trên thanh trạng thái.
  // Não chết thì chính não không tự báo được, nên server probe + cắm cờ, UI chỉ việc hỏi.
  // Thông báo phải NGẮN và nói được VIỆC CẦN LÀM. Bản cũ ghép tên engine với câu báo lỗi
  // của server rồi nối thêm hướng dẫn, ra một chuỗi dài hơn cả thanh trạng thái nên bị cắt
  // cụt, và nó còn chỉ sai chỗ ("mở terminal gõ /login") vì giờ kết nối ở trang Models.
  // Người dùng cũng không cần biết "bộ não claude" là gì: với họ chỉ có một sự thật là chưa
  // dùng được Javis, và một việc phải làm là vào Models.
  async function refreshEngineBanner() {
    const b = document.getElementById("engineBanner");
    if (!b) return;
    let d;
    try {
      const r = await fetch("/connect/health", { cache: "no-store" });
      if (!r.ok) return;   // chưa đăng nhập dashboard thì thôi, đừng nháy lỗi
      d = await r.json();
    } catch (e) { return; }
    const dead = Object.entries(d.engines || {}).filter(([, rec]) => rec && rec.ok === false);
    if (!dead.length) { b.hidden = true; return; }
    b.innerHTML = WARN_ICON + " Chưa kết nối Model AI - bấm để kết nối";
    // Chi tiết kỹ thuật (engine nào, lỗi gì) chuyển vào tooltip: cần khi đi hỏi, nhưng
    // không đáng chiếm chỗ trên thanh trạng thái.
    const [name, rec] = dead[0];
    b.title = `Chưa dùng được: ${name} - ${rec.message || "không phản hồi"}. `
      + "Vào trang Models để kết nối và sử dụng Javis.";
    b.hidden = false;
  }

  function boot() {
    document.body.classList.add("has-rail");
    refreshEngineBanner();
    setInterval(refreshEngineBanner, 90000);
    // Báo "chưa kết nối" mà không đưa được người ta tới chỗ kết nối thì chỉ là than phiền.
    const _eb = document.getElementById("engineBanner");
    if (_eb) _eb.addEventListener("click", () => navigateTo("models"));
    const ver = document.getElementById("railVersion");
    if (ver) {
      ver.textContent = "v" + APP_VERSION;   // hiện tạm, thay ngay bằng phiên bản thật từ server
      fetch("/version").then(r => r.json()).then(d => { if (d && d.current) ver.textContent = "v" + d.current; }).catch(() => {});
    }
    // Theo dõi Studio mở/đóng → bật/tắt graph theo
    const st = document.getElementById("studio");
    if (st) new MutationObserver(recomputeGraph).observe(st, { attributes: true, attributeFilter: ["class"] });
    // Màn hình co/giãn qua ngưỡng mobile → tính lại (chỉ tắt/bật graph, KHÔNG tự nhảy trang:
    // đang đứng ở màn Javis mà tự bị đẩy sang Trò chuyện là mất chỗ đang xem)
    window.matchMedia("(max-width: 860px)").addEventListener("change", recomputeGraph);
    // Đổi brain (Select Brain) → nạp lại trang quản lý đang xem theo brain mới (không cần F5)
    const gs = document.getElementById("graphSource");
    if (gs) gs.addEventListener("change", () => {
      const active = Alpine.store("nav").active;
      if (active !== "home") renderPage(active);
      // Cây vault ở cột trái sống ngoài hệ cview → tự làm mới theo brain mới
      _vtCache.clear(); _vtIndex = null; _vtActivePath = null; renderVaultTree();
      // Ghim của brain cũ trỏ ra ngoài brain mới → bỏ, kẻo Javis sửa nhầm file brain khác.
      try { if (window.JavisPin) window.JavisPin.clear(); } catch (e) {}
      // Vệt đường đi cũng thuộc brain cũ: mọi bước trong đó trỏ vào file của brain kia.
      _neLichSu = []; _neViTri = -1; _neVeNutLui();
    });

    // Cột trái = Vault explorer (luôn có trong DOM ở màn home) → nạp cây ngay khi khởi động
    renderVaultTree();
    initRailTooltip();   // tooltip nhanh cho rail thu gọn

    freshSettings().then(s => {
      graphEnabled = !(s.dashboard && s.dashboard.graph_enabled === false);
      // MỞ APP LÀ VÀO MÀN JAVIS, kể cả lite-mode (cờ graph tắt hoặc màn hẹp): màn Javis đã có
      // sẵn ô chat, chỉ khác là không vẽ khoang não. Bản trước tự đẩy sang trang Trò chuyện,
      // hoá ra rối hơn - mỗi lần tải lại là mỗi lần rơi vào một trang khác.
      recomputeGraph();
      // Deep-link mở tab mới từ link file trong chat: #open=<đường-dẫn-vault>.
      // Đi qua openVaultPath chứ KHÔNG phải openFilesAt: file sửa được thì mở thẳng trình sửa,
      // đúng như cú bấm thường. Trước bản này hai đường cho ra hai kết quả khác nhau.
      try {
        const m = /^#open=(.+)$/.exec(location.hash || "");
        if (m) openVaultPath(decodeURIComponent(m[1]));
      } catch (e) {}
    });
  }

  if (window.Alpine && Alpine.version) boot();           // Alpine đã sẵn (hiếm)
  else document.addEventListener("alpine:initialized", boot);
})();
