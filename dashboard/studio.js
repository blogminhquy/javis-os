// ============================================
// JAVIS OS - Studio: Agents / Skills / Workflows
// ============================================
(function () {
  // Locale để định dạng số/ngày. Lấy từ i18n chứ KHÔNG khoá "vi-VN": người dùng đổi
  // ngôn ngữ giao diện thì ngày giờ phải đổi theo, nếu không thì nửa màn hình tiếng Anh
  // mà ngày vẫn dd/mm/yyyy kiểu Việt.
  const LOC = () => (window.JavisI18n && JavisI18n.locale()) || "vi-VN";
  const studio = document.getElementById("studio");
  const editor = document.getElementById("studioEditor");
  const brain = () => (window.currentBrainPath ? currentBrainPath() : "brain");
  const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const api = async (p, o) => {
    // Timeout 12s → loader hiện trạng thái rỗng thay vì kẹt "Đang tải..." mãi nếu server chậm/treo.
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 12000);
    try { return await (await fetch(p, Object.assign({}, o, { signal: ctrl.signal }))).json(); }
    catch (e) { return {}; }
    finally { clearTimeout(t); }
  };
  const fd = (obj) => { const f = new FormData(); Object.entries(obj).forEach(([k, v]) => f.append(k, v)); return f; };

  // ===== Hai lượt mạng NỀN của trình sửa trợ lý: danh sách skill + /settings (dựng ô chọn model) =====
  // Ở trang Cộng sự, form này dựng lại MỖI LẦN bấm sang một trợ lý khác, nên cứ một cú bấm là
  // thêm hai lượt mạng chen vào cùng lúc với /sessions và /agents của chính trang đó - trình
  // duyệt chỉ mở 6 kết nối một lúc, và /settings thì còn đi dò từng binary CLI trên đĩa. Chủ
  // dự án 22/09: "load phần trợ lý và phần cài đặt rất chậm".
  // Trong vài giây giữa hai cú bấm, hai thứ này không đổi, nên giữ lại một lát. Khoá theo
  // BRAIN để đổi bộ não là hết hiệu lực ngay; đổi skill/model rồi thì gọi quenForm().
  const FORM_TTL = 20000;
  let _formCache = null;
  async function duLieuForm() {
    const b = brain();
    if (_formCache && _formCache.brain === b && Date.now() - _formCache.luc < FORM_TTL) return _formCache.ds;
    const ds = await Promise.all([
      api(`/skills?brain=${encodeURIComponent(b)}`),
      api("/settings"),
    ]);
    // Lượt hỏng (api() nuốt lỗi và trả {}) thì ĐỪNG nhớ: nhớ một câu trả lời rỗng 20 giây là
    // form mở lên không có skill nào, không có model nào, mà không gì nói vì sao.
    if ((ds[0] && ds[0].skills) || (ds[1] && ds[1].model)) _formCache = { brain: b, luc: Date.now(), ds: ds };
    return ds;
  }
  function quenForm() { _formCache = null; }

  // ===== Trợ lý ĐẦY ĐỦ (kèm system prompt) cho trình sửa =====
  // Các danh sách nay xin bản NHẸ (`/agents?prompt=0`): đo trên brain 14 trợ lý, kèm prompt
  // là 366 KB còn bỏ ra là 2.9 KB, mà cột trái chưa bao giờ hiện prompt. Đổi lại, mục truyền
  // vào trình sửa thiếu `prompt` nên phải đi lấy riêng đúng một trợ lý.
  //
  // Lấy HỎNG thì trả `false`, KHÔNG rơi về chuỗi rỗng: một ô sửa mở ra trống nhìn y hệt một
  // trợ lý chưa có prompt, bấm Lưu một cái là prompt thật bị ghi đè mất, lặng lẽ.
  async function layAgentDay(a) {
    if (!a || !a.slug) return null;                  // tạo mới: chưa có gì để lấy
    if (typeof a.prompt === "string") return a;      // người gọi đã cầm bản đầy đủ
    const url = `/agents/get?slug=${encodeURIComponent(a.slug)}&brain=${encodeURIComponent(brain())}`;
    let r = await api(url);
    // `{}` trơn = api() nuốt một lần hết giờ / rớt mạng, KHÁC với `{error}` (server nói không
    // có trợ lý này). Máy chủ bận một lượt chat là đủ để lần đầu trượt, nên thử lại đúng một
    // lần trước khi báo lỗi. Trước đây trượt một lần là hiện ngay "Không tải được trợ lý này"
    // dù trợ lý vẫn nằm nguyên đó (chủ repo gặp 23/09).
    if (r && !r.error && typeof r.prompt !== "string") r = await api(url);
    if (!r || typeof r.prompt !== "string") return false;
    return Object.assign({}, a, r);
  }
  // Đổi bộ não / lưu skill / cắm key model ở trang khác đều làm bộ nhớ tạm này sai.
  try {
    const _gs = document.getElementById("graphSource");
    if (_gs) _gs.addEventListener("change", quenForm);
  } catch (e) { /* không có ô chọn brain thì thôi */ }

  // ===== Xuất / Nhập năng lực (chia sẻ agent/skill/workflow qua file .zip) =====
  // slug nhận 1 chuỗi hoặc mảng (chọn nhiều) - server gói tất cả vào MỘT file .zip.
  const exportUrl = (kind, slug) => `/export?kind=${kind}&slug=${encodeURIComponent(Array.isArray(slug) ? slug.join(",") : slug)}&brain=${encodeURIComponent(brain())}&deps=1`;
  function exportItem(kind, slug) { window.open(exportUrl(kind, slug), "_blank"); }

  // ===== Chọn nhiều để tải về (16/08): tick từng thẻ hoặc Chọn tất cả, tải MỘT gói =====
  const _sel = { workflow: new Set(), agent: new Set(), skill: new Set() };
  function taiDaChon(kind) {
    const ds = [..._sel[kind]];
    if (ds.length) window.open(exportUrl(kind, ds), "_blank");
  }
  function capNhatNutTai(kind, btnId) {
    const b = document.getElementById(btnId);
    if (!b) return;
    const n = _sel[kind].size;
    b.disabled = !n;
    b.textContent = t("studio.dl_sel") + (n ? ` (${n})` : "");
  }
  // Tick một thẻ. `boxCls` là class của ô tick để Chọn tất cả gom được cả trang.
  function noiSel(kind, btnId, el, slug) {
    el.onchange = () => { el.checked ? _sel[kind].add(slug) : _sel[kind].delete(slug); capNhatNutTai(kind, btnId); };
    el.checked = _sel[kind].has(slug);
  }
  // Chọn tất cả <-> bỏ chọn: đã chọn đủ thì bấm lần nữa là bỏ hết.
  function chonTatCa(kind, btnId, boxCls, slugsHienCo) {
    const duTat = slugsHienCo.length && slugsHienCo.every(s => _sel[kind].has(s));
    _sel[kind] = new Set(duTat ? [] : slugsHienCo);
    document.querySelectorAll("." + boxCls).forEach(c => { c.checked = _sel[kind].has(c.dataset.slug); });
    capNhatNutTai(kind, btnId);
  }
  function importItems(reload) {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".zip,.md,.skill,application/zip";
    inp.onchange = async () => {
      if (!inp.files || !inp.files.length) return;
      const ow = confirm(t("studio.import_confirm"));
      const f = new FormData();
      f.append("file", inp.files[0]); f.append("brain", brain()); f.append("overwrite", ow ? "1" : "0");
      let r;
      try { r = await (await fetch("/import", { method: "POST", body: f })).json(); }
      catch (e) { alert(t("studio.upload_err") + " " + e.message); return; }
      if (r && r.error) { alert(t("studio.import_fail") + " " + r.error); return; }
      const show = (a) => (a && a.length) ? a.join(", ") : t("studio.none");
      alert(`${t("studio.import_done")}\n• ${t("studio.imported")} ${show(r.imported)}\n• ${t("studio.skipped")} ${show(r.skipped)}`
        + ((r.errors && r.errors.length) ? `\n• ${t("studio.errors")} ${r.errors.join("; ")}` : ""));
      if (reload) reload();
    };
    inp.click();
  }

  // Studio đã tách thành các trang sidebar riêng. openStudio = điều hướng rail (giữ tương thích
  // cho nút header & dải số liệu .bstat ở đáy graph). Console gọi loader qua window.JavisStudio.
  //
  // Hai trang "agents" và "workflows" ĐÃ BỎ, cả hai gộp vào trang Cộng sự (workspace). Nút cũ
  // vẫn truyền tên trang cũ (dải .bstat trong index.html, nút Studio trên thanh đầu), nên đổi
  // tên ở ĐÂY thay vì đi sửa từng nút: gọi go("agents") bây giờ là đi tới một trang không tồn
  // tại, rail không sáng mục nào và khung giữa trắng trơn.
  const TRANG_CU = { agents: "workspace", workflows: "workspace" };
  window.openStudio = (tab) => {
    const id = TRANG_CU[tab] || tab || "workspace";
    if (window.JavisNav && window.JavisNav.go) window.JavisNav.go(id);
    else if (window.Alpine) Alpine.store("nav").go(id);
  };
  window.JavisStudio = {
    workflows: loadWorkflows, agents: loadAgents, skills: loadSkills,
    // Trang Cộng sự mượn chính hai trình sửa này (xem editAgent/editWorkflow) + nút Xuất.
    editAgent: editAgent, editWorkflow: editWorkflow, exportItem: exportItem, importItems: importItems,
    // Trang Models gọi sau khi cắm/ngắt key: ô chọn model trong form trợ lý dựng từ /settings.
    quenForm: quenForm,
  };
  const _studioBtn = document.getElementById("studioOpenBtn");
  if (_studioBtn) _studioBtn.addEventListener("click", () => window.openStudio("workspace"));

  const refreshStats = () => { if (window.loadBrainStats) window.loadBrainStats(); };

  // ===== Khung NHÓM: cột nhóm bên trái + ô tìm - DÙNG CHUNG cho Workflows / Agents / Skills =====
  // Trang Skills có cột nhóm từ lâu, còn Agents và Workflows thì không: brain dùng vài tháng là
  // hai danh sách phẳng vài chục dòng, phải dò bằng mắt. Ở đây gom thành MỘT khung cho cả ba
  // trang - cùng field `group` trong frontmatter, cùng nhóm mặc định, cùng cách lọc, cùng cách
  // xếp trên điện thoại. Chép tay thành ba bản là ba bản trôi lệch nhau ngay lần sửa đầu tiên.
  const NHOM_MD = "Chung";                     // nhóm mặc định khi file chưa khai `group`
  const nhomCua = (x) => (x && String(x.group || "").trim()) || NHOM_MD;
  // Ô CHỌN NHÓM trong trình sửa trợ lý đã BỎ ở 0.62.0 (chủ repo 21/09: "xoá nhóm ở đây vì đã
  // có phần gom nhóm rồi"). Gom nhóm nay chỉ còn MỘT chỗ: thanh nhóm ở cột trái trang Cộng sự
  // và menu "Chuyển sang nhóm" của từng mục. Hai chỗ cùng đặt một field là chỗ nào cũng có thể
  // ghi đè chỗ kia - đúng lỗi phải vá bằng dongBoNhomForm() suốt từ 0.59.2. Server giữ nguyên
  // nhóm cũ khi form không gửi `group` (xem main.save_agent), nên bỏ ô đi là hết hẳn lớp lỗi ấy.

  // Server trả về MÃ MÁY chứ không phải câu cho người đọc (server/agent_avatar.py ném
  // ValueError("avatar_shape"), main.py chuyển thẳng thành {"error": "avatar_shape"}). Đổ thẳng
  // mã đó vào alert là người dùng đọc được đúng chữ "avatar_shape" - vô nghĩa và không dịch
  // được. Ở đây dịch mã đã biết, mã lạ rơi về câu chung. Bảng tra dựng KHÔNG có prototype:
  // `{}["__proto__"]` trả về Object.prototype chứ không phải undefined, nên một mã lạ đúng
  // tên đó sẽ lọt qua nhánh "|| ws.save_failed".
  const _MA_LOI_LUU = Object.assign(Object.create(null),
    { avatar_shape: "ws.err_avatar_shape", avatar_palette: "ws.err_avatar_palette",
      avatar_color: "ws.err_avatar_palette", avatar_eye: "ws.err_avatar_eye",
      avatar_eye_color: "ws.err_avatar_eye", avatar_eye_size: "ws.err_avatar_eye" });
  const loiLuu = (ma) => t(_MA_LOI_LUU[String(ma == null ? "" : ma)] || "ws.save_failed");

  // Bỏ dấu để gõ "viet email" vẫn ra "Viết email".
  function _spNoAccent(s) {
    s = String(s == null ? "" : s);
    try { s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, ""); } catch (e) {}
    return s.replace(/[\u0111\u0110]/g, "d").toLowerCase();
  }

  function demNhom(items) {
    const m = {};
    (items || []).forEach(x => { const g = nhomCua(x); m[g] = (m[g] || 0) + 1; });
    return m;
  }

  // HTML của khung: cột nhóm + ô tìm + một chỗ trống (id=bodyId) để mỗi trang tự vẽ danh sách
  // theo kiểu riêng của nó (thẻ agent, hàng workflow, thẻ skill).
  function khungNhomHtml(items, state, o) {
    const dem = demNhom(items);
    const cats = ["ALL"].concat(Object.keys(dem).sort((a, b) => a.localeCompare(b, LOC())));
    const catHtml = cats.map(c => `<div class="gr-cat ${state.cat === c ? "sel" : ""}" data-cat="${esc(c)}"><span>${c === "ALL" ? esc(t("studio.all")) : esc(c)}</span><span class="n">${c === "ALL" ? items.length : dem[c]}</span></div>`).join("");
    return `<div class="gr">
      <div class="gr-side"><div class="sec">${esc(t("studio.groups"))}</div>${catHtml}</div>
      <div class="gr-main">
        <div class="gr-bar"><h4>${state.cat === "ALL" ? esc(t("studio.all")) : esc(state.cat)}</h4><span class="cnt"></span>
          <input id="${o.searchId}" placeholder="${esc(o.searchPh)}" value="${esc(state.q)}"></div>
        <div class="${o.bodyCls || ""}" id="${o.bodyId}"></div>
      </div></div>`;
  }

  // Lọc theo nhóm đang chọn + ô tìm. `blob` trả chuỗi dùng để dò của một mục.
  function locTheoNhom(items, state, blob) {
    let list = items || [];
    if (state.cat !== "ALL") list = list.filter(x => nhomCua(x) === state.cat);
    const nq = _spNoAccent((state.q || "").trim());
    if (nq) list = list.filter(x => nq.split(/\s+/).every(word => _spNoAccent(blob(x)).includes(word)));
    return list;
  }

  // Bấm nhóm thì vẽ lại CẢ trang (cột nhóm và tiêu đề đổi theo); gõ tìm thì chỉ vẽ lại danh
  // sách, để con trỏ không bị nhảy ra khỏi ô tìm giữa lúc đang gõ.
  function ganKhungNhom(panel, state, o) {
    panel.querySelectorAll(".gr-side .gr-cat").forEach(c => {
      c.onclick = () => { state.cat = c.dataset.cat; o.veLai(); };
    });
    const s = panel.querySelector("#" + o.searchId);
    if (s) s.oninput = () => { state.q = s.value; o.veDanhSach(); };
  }

  function datSoLuong(panel, chu) {
    const el = panel.querySelector(".gr-bar .cnt");
    if (el) el.textContent = chu;
  }

  // Gợi ý nhóm ĐANG CÓ cho ô nhập trong form, để khỏi đẻ "Marketing" và "marketing" song song.
  function nhomDatalist(items, id) {
    const gs = [...new Set((items || []).map(nhomCua))].sort((a, b) => a.localeCompare(b, LOC()));
    return `<datalist id="${id}">${gs.map(g => `<option value="${esc(g)}">`).join("")}</datalist>`;
  }

  // (Hàm switchTab của Studio ba-tab cũ đã bỏ: Studio không còn là MỘT trang ba tab, mỗi phần
  // là một trang riêng của rail, nên nó chỉ còn là đoạn code chết trỏ vào ba panel không tồn
  // tại. Đổi trang bây giờ đi qua openStudio/JavisNav.)

  // ===== Workflows =====
  // Biến workflow đọc thành lời cho ô bước: thay "…" (cũ) vì "Nhận …, tạo project folder"
  // đọc lên cụt nghĩa. Biến lạ thì hiện thẳng tên biến, đừng nuốt thành dấu ba chấm.
  const WF_VARS = { input: "studio.var_input", prev: "studio.var_prev" };   // tên KHOÁ i18n, tra lúc vẽ
  function renderPipeline(steps) {
    return (steps || []).map((s, i) => {
      const task = (s.task || "").replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (m, v) => (WF_VARS[v] ? t(WF_VARS[v]) : v));
      return `<div class="wf-pstep" data-i="${i}">
          <div class="wps-num">${String(i + 1).padStart(2, "0")}</div>
          ${task ? `<div class="wps-task" title="${esc(task)}">${esc(task)}</div>` : ''}
          <div class="wps-name">${esc(s.agent)}</div>
        </div>`;
    }).join('');
  }

  const _wfState = { cat: "ALL", q: "", wfs: [] };

  async function loadWorkflows() {
    _injectStudioCss();
    const panel = document.getElementById("panel-workflows");
    // Trang "Quy trình" riêng đã gộp vào trang Cộng sự, nên panel này thường KHÔNG có trong
    // DOM. Không chặn ở đây thì mọi lời gọi còn sót (nút cũ, onSaved mặc định) ném TypeError
    // giữa chừng và nuốt luôn phần việc đứng sau nó.
    if (!panel) return;
    panel.innerHTML = `<div class="empty">${esc(t("common.loading"))}</div>`;
    const d = await api(`/workflows?brain=${encodeURIComponent(brain())}`);
    _wfState.wfs = d.workflows || [];
    _sel.workflow.clear();   // nạp lại trang là làm mới lựa chọn (danh sách có thể đã đổi)
    refreshStats();
    renderWorkflowUI();
  }

  const _wfFiltered = () => locTheoNhom(_wfState.wfs, _wfState,
    (w) => `${w.name} ${w.slug} ${w.description || ""}`);

  function renderWorkflowUI() {
    const panel = document.getElementById("panel-workflows");
    const all = _wfState.wfs;
    panel.innerHTML = `<div class="panel-bar"><h3>${esc(t("page.workspace.label"))}</h3><div class="pb-actions"><button class="s-btn-ghost" id="wfSelAll" title="${esc(t("studio.selall_title"))}">${esc(t("studio.selall"))}</button><button class="s-btn-ghost" id="wfDl" disabled title="${esc(t("studio.dl_title"))}">${esc(t("studio.dl_sel"))}</button><button class="s-btn-ghost" id="wfImport">${esc(t("studio.import"))}</button><button class="s-btn-ghost" id="seedBtn">${esc(t("studio.seed"))}</button><button class="s-btn" id="newWf">+ ${esc(t("page.workspace.label"))}</button></div></div>
      ${all.length ? khungNhomHtml(all, _wfState, { bodyId: "wfCards", bodyCls: "wf-list",
                                                    searchId: "wfSearch", searchPh: t("studio.wf_search_ph") })
      : `<div class="empty">${esc(t("studio.wf_empty"))}</div>`}`;
    document.getElementById("newWf").onclick = () => editWorkflow(null);
    document.getElementById("wfImport").onclick = () => importItems(loadWorkflows);
    document.getElementById("seedBtn").onclick = async () => { await api("/studio/seed", { method: "POST", body: fd({ brain: brain() }) }); loadWorkflows(); };
    document.getElementById("wfDl").onclick = () => taiDaChon("workflow");
    // Chọn tất cả = danh sách ĐANG HIỆN (đúng nhóm + đúng ô tìm), giống trang Skills.
    document.getElementById("wfSelAll").onclick = () =>
      chonTatCa("workflow", "wfDl", "wf-sel", _wfFiltered().map(w => w.slug));
    capNhatNutTai("workflow", "wfDl");
    if (!all.length) return;
    ganKhungNhom(panel, _wfState, { searchId: "wfSearch", veLai: renderWorkflowUI, veDanhSach: renderWorkflowList });
    renderWorkflowList();
  }

  function renderWorkflowList() {
    const cards = document.getElementById("wfCards"); if (!cards) return;
    const wfs = _wfFiltered();
    datSoLuong(document.getElementById("panel-workflows"), wfs.length + " workflow");
    if (!wfs.length) { cards.innerHTML = `<div class="empty">${esc(t("studio.wf_no_match"))}</div>`; return; }
    cards.innerHTML = "";
    wfs.forEach(w => {
      const active = w.status === "active";
      const div = document.createElement("div");
      div.className = "wf-row" + (active ? "" : " archived");
      div.dataset.slug = w.slug;
      div.innerHTML = `
        <div class="wf-header">
          <input type="checkbox" class="wf-sel" data-slug="${esc(w.slug)}" title="${esc(t("studio.sel_one"))}">
          <div class="wf-name">${esc(w.name)}</div>
          <span class="wf-badge ${active ? "ready" : "off"}">${esc(active ? t("studio.ready") : t("studio.archived"))}</span>
          <span class="wf-group">${ic("folder-open")} ${esc(nhomCua(w))}</span>
          <span class="wf-count">${(w.steps || []).length} ${esc(t("studio.steps"))}</span>
          <div class="wf-spacer"></div>
          <div class="wf-actions">
            <button class="s-btn run" ${active ? "" : "disabled"}>▶ ${esc(t("studio.run"))}</button>
            <button class="s-btn-ghost edit">${esc(t("common.edit"))}</button>
            <button class="s-btn-ghost archive">${esc(active ? t("studio.archived") : t("studio.activate"))}</button>
            <button class="s-btn-ghost exp" title="${esc(t("studio.export_title"))}">${esc(t("studio.export"))}</button>
            <button class="s-btn-ghost del">${esc(t("common.delete"))}</button>
          </div>
        </div>
        ${w.description ? `<div class="wf-desc">${esc(w.description)}</div>` : ''}
        <div class="wf-pipeline">${renderPipeline(w.steps)}</div>`;
      noiSel("workflow", "wfDl", div.querySelector(".wf-sel"), w.slug);
      div.querySelector(".exp").onclick = () => exportItem("workflow", w.slug);
      div.querySelector(".archive").onclick = async () => { await api("/workflows/toggle", { method: "POST", body: fd({ slug: w.slug, brain: brain() }) }); loadWorkflows(); };
      div.querySelector(".run").onclick = () => runWorkflow(w, div);
      div.querySelector(".edit").onclick = () => editWorkflow(w);
      div.querySelector(".del").onclick = async () => { if (confirm(t("studio.del_wf", { ten: w.name }))) { await api("/workflows/delete", { method: "POST", body: fd({ slug: w.slug, brain: brain() }) }); loadWorkflows(); } };
      cards.appendChild(div);
    });
  }

  // ===== Run workflow (SSE) =====
  function runWorkflow(w, card) {
    const input = prompt(t("studio.run_input", { ten: w.name }), "");
    if (input === null) return;

    // Card chuyển sang trạng thái running
    const badge = card && card.querySelector(".wf-badge");
    if (card) { card.classList.add("running"); }
    if (badge) { badge.className = "wf-badge running"; badge.innerHTML = ic("loader", { cls: "ic-spin" }) + " " + esc(t("studio.running")); }

    const endRun = () => {
      if (card) { card.classList.remove("running"); }
      if (badge) { badge.className = "wf-badge ready"; badge.textContent = t("studio.ready"); }
      card && card.querySelectorAll(".wf-pstep").forEach(el => el.classList.remove("active"));
    };

    const drawer = document.getElementById("runDrawer");
    const stepsEl = document.getElementById("runSteps");
    document.getElementById("runTitle").textContent = `▶ ${w.name}`;
    stepsEl.innerHTML = `<div class="run-info">${esc(t("studio.starting"))}</div>`;
    drawer.classList.add("open");
    const url = `/workflows/run?slug=${encodeURIComponent(w.slug)}&brain=${encodeURIComponent(brain())}&input=${encodeURIComponent(input)}`;
    const es = new EventSource(url);
    const stepDivs = {};
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d.type === "start") {
        stepsEl.innerHTML = `<div class="run-info">${d.steps} ${esc(t("studio.steps"))} · workflow ${esc(d.workflow)}</div>`;
      } else if (d.type === "step_start") {
        // Pipeline card: sáng bước đang chạy
        if (card) {
          card.querySelectorAll(".wf-pstep").forEach(el => el.classList.remove("active"));
          const ps = card.querySelector(`.wf-pstep[data-i="${d.i}"]`);
          if (ps) ps.classList.add("active");
          if (badge) badge.innerHTML = `${ic("loader", { cls: "ic-spin" })} ${esc(t("studio.step_n", { a: d.i + 1, b: w.steps.length }))}`;
        }
        const div = document.createElement("div");
        div.className = "run-step";
        div.innerHTML = `<div class="rs-head"><span class="rs-num">${d.i + 1}</span><span class="rs-agent">${esc(d.agent)}</span><span class="rs-spin"></span></div><div class="rs-task">${esc(d.task)}</div><div class="rs-out" id="rs-out-${d.i}"></div>`;
        stepsEl.appendChild(div); stepDivs[d.i] = div;
        stepsEl.scrollTop = stepsEl.scrollHeight;
      } else if (d.type === "step_text") {
        const out = document.getElementById(`rs-out-${d.i}`);
        if (out) { out.textContent += d.content; stepsEl.scrollTop = stepsEl.scrollHeight; }
      } else if (d.type === "step_tool") {
        const div = stepDivs[d.i];
        if (div) div.querySelector(".rs-head").insertAdjacentHTML("beforeend", `<span class="rs-tool">${ic("settings")} ${esc(d.tool)}</span>`);
      } else if (d.type === "step_verify") {
        const div = stepDivs[d.i];
        if (div) div.querySelector(".rs-head").insertAdjacentHTML("beforeend",
          `<span class="rs-verify" id="rs-vf-${d.i}">${ic("search")} ${esc(d.agent)} ${esc(t("studio.verifying"))}${d.attempt ? ` ${esc(t("studio.attempt_n", { n: d.attempt + 1 }))}` : ""}...</span>`);
      } else if (d.type === "step_verify_result") {
        const vf = document.getElementById(`rs-vf-${d.i}`);
        if (vf) { vf.className = "rs-verify " + (d.passed ? "ok" : "fail"); vf.innerHTML = (d.passed ? ic("check", { cls: "ic-ok" }) + " " + esc(t("studio.pass")) : ic("circle-x", { cls: "ic-err" }) + " " + esc(t("studio.fail"))) + (d.reason ? ": " + esc(d.reason) : ""); vf.removeAttribute("id"); }
      } else if (d.type === "step_retry") {
        const out = document.getElementById(`rs-out-${d.i}`);
        if (out) out.insertAdjacentHTML("beforebegin", `<div class="rs-retry">↻ ${esc(t("studio.retry_n", { n: d.attempt }))}...</div>`);
      } else if (d.type === "step_done") {
        // Pipeline card: bước xong → xanh
        if (card) {
          const ps = card.querySelector(`.wf-pstep[data-i="${d.i}"]`);
          if (ps) { ps.classList.remove("active"); ps.classList.add("done"); }
        }
        const div = stepDivs[d.i];
        if (div) {
          div.classList.add("done");
          const sp = div.querySelector(".rs-spin"); if (sp) sp.outerHTML = `<span class="rs-ok">${ic("check", { cls: "ic-ok" })}</span>`;
          if (d.verified === false) div.insertAdjacentHTML("beforeend", `<div class="rs-warn">${ic("triangle-alert", { cls: "ic-warn" })} ${esc(t("studio.verify_fail"))}</div>`);
          const out = document.getElementById(`rs-out-${d.i}`); if (out && !out.textContent.trim()) out.textContent = d.output;
        }
      } else if (d.type === "step_error") {
        const out = document.getElementById(`rs-out-${d.i}`); if (out) out.innerHTML += `<div class="rs-err">${ic("triangle-alert", { cls: "ic-warn" })} ${esc(d.content)}</div>`;
        // Bước đã báo lỗi thì TẮT vòng quay của chính nó. Trước đây chỉ `step_done` mới thay
        // được .rs-spin, mà bước hỏng thì không bao giờ có step_done nữa (server dừng ngay),
        // nên bước ấy quay mãi trong khi cả lần chạy đã kết thúc.
        const divE = stepDivs[d.i];
        if (divE) {
          const sp = divE.querySelector(".rs-spin");
          if (sp) sp.outerHTML = `<span class="rs-fail">${ic("circle-x", { cls: "ic-err" })}</span>`;
        }
      } else if (d.type === "step_model") {
        // Router chọn model khác model mặc định của agent - nói rõ để khỏi ngờ ngợ.
        const div = stepDivs[d.i];
        if (div) div.querySelector(".rs-head").insertAdjacentHTML("beforeend",
          `<span class="rs-tool">${ic("settings")} model: ${esc(d.model)}</span>`);
      } else if (d.type === "resume") {
        stepsEl.insertAdjacentHTML("beforeend", `<div class="run-info">${ic("loader")} ${esc(t("studio.resume", { n: d.reused }))}</div>`);
      } else if (d.type === "replan") {
        stepsEl.insertAdjacentHTML("beforeend", `<div class="run-info">${ic("search")} ${esc(t("studio.replan", { n: (d.added || []).length, r: d.round }))}</div>`);
      } else if (d.type === "wait_user") {
        // Dừng chờ duyệt KHÔNG được trông giống bị sập: phải nói rõ đang chờ gì,
        // và nếu duyệt được thì cho bấm ngay tại đây.
        es.close();
        endRun();
        const canApprove = d.code && d.task_id;
        stepsEl.insertAdjacentHTML("beforeend",
          `<div class="run-info wf-wait">${ic("triangle-alert", { cls: "ic-warn" })} ` +
          `${esc(t("studio.wait1"))} "${esc(d.node || "")}"${d.prompt ? ": " + esc(d.prompt) : ""}` +
          (canApprove
            ? `<div class="wf-wait-act"><button type="button" class="wf-approve" ` +
              `data-task="${esc(d.task_id)}" data-node="${esc(d.node || "")}" ` +
              `data-code="${esc(d.code)}">${esc(t("studio.approve"))} ${esc(d.code)}</button>` +
              `<span class="dim">${esc(t("studio.wait_warn"))}</span></div>`
            : "") +
          `</div>`);
        stepsEl.scrollTop = stepsEl.scrollHeight;
      } else if (d.type === "escalation") {
        stepsEl.insertAdjacentHTML("beforeend", `<div class="run-info">${ic("triangle-alert", { cls: "ic-warn" })} ${esc(t("studio.escalation"))} ${esc(d.reason || "")}</div>`);
      } else if (d.type === "error") {
        es.close();
        endRun();
        stepsEl.insertAdjacentHTML("beforeend", `<div class="run-info">${ic("circle-x", { cls: "ic-err" })} ${esc(d.content || t("studio.err_stop"))}</div>`);
        stepsEl.scrollTop = stepsEl.scrollHeight;
      } else if (d.type === "done") {
        es.close();
        endRun();
        stepsEl.insertAdjacentHTML("beforeend", `<div class="run-info done">${ic("check", { cls: "ic-ok" })} ${esc(t("studio.done"))}</div>`);
        stepsEl.scrollTop = stepsEl.scrollHeight;
      }
    };
    es.onerror = () => { es.close(); endRun(); };
    // Nút Duyệt: mã nằm trên chính nút, nên một cú bấm gắn với ĐÚNG node đang chờ.
    stepsEl.onclick = (ev) => {
      const btn = ev.target.closest ? ev.target.closest(".wf-approve") : null;
      if (!btn || btn.disabled) return;
      btn.disabled = true;
      btn.textContent = t("studio.running");
      const q = new URLSearchParams({
        task_id: btn.dataset.task, node: btn.dataset.node, code: btn.dataset.code,
        slug: w.slug, brain: brain(),
      });
      const es2 = new EventSource(`/workflows/resume?${q}`);
      es2.onmessage = es.onmessage;
      es2.onerror = () => { es2.close(); endRun(); };
    };
    document.getElementById("runClose").onclick = () => { es.close(); endRun(); drawer.classList.remove("open"); };
  }

  // ===== Workflow editor =====
  let agentsCache = [];
  // `tuyChon.onSaved` thay cho loadWorkflows(): trang Cộng sự gọi hàm này lúc panel Studio
  // không có trong DOM, gọi loadWorkflows() ở đó là ghi vào node không tồn tại. (Tên tham số
  // KHÔNG đặt là `opts` vì thân hàm đã có một `const opts` khác - danh sách <option> của ô
  // chọn agent.)
  async function editWorkflow(w, tuyChon) {
    tuyChon = tuyChon || {};
    // Bản NHẸ: ô chọn agent của từng bước chỉ cần slug + tên (xem layAgentDay).
    const ad = await api(`/agents?brain=${encodeURIComponent(brain())}&prompt=0`);
    agentsCache = ad.agents || [];
    if (!agentsCache.length) { alert(t("studio.no_agents")); return; }
    const box = document.getElementById("editorBox");
    box.classList.remove("agent-editor");
    const steps = w ? JSON.parse(JSON.stringify(w.steps || [])) : [{ agent: agentsCache[0].slug, task: "" }];
    const opts = (sel) => agentsCache.map(a => `<option value="${a.slug}" ${a.slug === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
    const optsV = (sel) => `<option value="">${esc(t("studio.no_verify"))}</option>` + agentsCache.map(a => `<option value="${a.slug}" ${a.slug === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
    const agentName = (slug) => { const a = agentsCache.find(x => x.slug === slug); return a ? a.name : (slug || "?"); };
    // Bước gập lại để thấy toàn cảnh; bấm vào bước nào thì mở bước đó ra sửa. Workflow mới
    // chỉ có 1 bước nên mở sẵn. Các ô input VẪN nằm trong DOM khi gập (chỉ ẩn bằng CSS) -
    // captureSteps() đọc value của chúng, render kiểu chỉ-vẽ-bước-đang-mở sẽ làm nó vỡ.
    let openIdx = w ? null : 0;
    // Tên/mô tả/nhóm giữ trong BIẾN, không đọc lại từ `w` mỗi lần vẽ: render() chạy lại mỗi
    // khi thêm/xoá/đảo bước, nên lấy giá trị từ `w` là chữ vừa gõ ở ba ô này bị vẽ đè về giá
    // trị cũ, im lặng - đúng cái bẫy mà captureSteps() đang giữ cho phần các bước.
    let ten = w ? (w.name || "") : "";
    let mota = w ? (w.description || "") : "";
    let nhom = w ? nhomCua(w) : NHOM_MD;
    function move(i, d) {
      const j = i + d;
      if (j < 0 || j >= steps.length) return;
      captureSteps();
      const t = steps[i]; steps[i] = steps[j]; steps[j] = t;
      if (openIdx === i) openIdx = j; else if (openIdx === j) openIdx = i;
      render();
    }
    function render() {
      box.innerHTML = `
        <h3>${esc(w ? t("studio.edit") : t("studio.create"))} Workflow</h3>
        <label>${esc(t("studio.name"))}</label><input id="wfName" value="${esc(ten)}">
        <label>${esc(t("studio.desc"))}</label><input id="wfDesc" value="${esc(mota)}">
        <label>${esc(t("studio.groups"))}</label>
        <input id="wfGroup" list="wfGroupList" value="${esc(nhom)}" placeholder="${esc(t("studio.group_ph"))}">
        ${nhomDatalist(_wfState.wfs, "wfGroupList")}
        <label>${esc(t("studio.steps_label"))}</label>
        <div id="stepList"></div>
        <button class="s-btn-ghost" id="addStep">${esc(t("studio.add_step"))}</button>
        <div class="editor-actions"><button class="s-btn-ghost" id="cancelEd">${esc(t("common.cancel"))}</button><button class="s-btn" id="saveWf">${esc(t("common.save"))}</button></div>`;
      const sl = box.querySelector("#stepList"); sl.innerHTML = "";
      steps.forEach((st, i) => {
        const open = i === openIdx;
        const row = document.createElement("div"); row.className = "step-row" + (open ? " open" : "");
        const sum = (st.task || "").replace(/\s+/g, " ").trim();
        row.innerHTML = `
          <div class="step-header">
            <span class="step-num">${i + 1}</span>
            <span class="step-sum">${esc(agentName(st.agent))}${sum ? ` · ${esc(sum)}` : ""}</span>
            <select class="st-agent">${opts(st.agent)}</select>
            <button class="st-move" data-d="-1" title="${esc(t("studio.up"))}" ${i === 0 ? "disabled" : ""}>↑</button>
            <button class="st-move" data-d="1" title="${esc(t("studio.down"))}" ${i === steps.length - 1 ? "disabled" : ""}>↓</button>
            <button class="st-del" title="${esc(t("studio.del_step"))}">${ic("x")}</button>
          </div>
          <div class="step-body">
            <textarea class="st-task" rows="3" placeholder="${esc(t("studio.task_ph"))}">${esc(st.task)}</textarea>
            <div class="st-verify">
              <span class="stv-lbl">${esc(t("studio.verify_lbl"))}</span>
              <select class="st-verify-agent">${optsV(st.verify_agent || "")}</select>
              <input class="st-retries" type="number" min="0" max="5" value="${st.max_retries != null ? st.max_retries : 1}">
              <span class="stv-lbl">${esc(t("studio.times"))}</span>
            </div>
          </div>`;
        row.querySelector(".step-header").onclick = (e) => {
          if (e.target.closest("button, select")) return;
          captureSteps(); openIdx = open ? null : i; render();
        };
        row.querySelectorAll(".st-move").forEach(b => { b.onclick = () => move(i, parseInt(b.dataset.d, 10)); });
        // captureSteps() TRƯỚC khi splice: thiếu nó thì chữ đang gõ dở ở các bước khác
        // bị render() vẽ đè lại bằng giá trị cũ trong mảng steps, tức mất trắng.
        row.querySelector(".st-del").onclick = () => {
          captureSteps();
          steps.splice(i, 1);
          if (!steps.length) steps.push({ agent: agentsCache[0].slug, task: "" });
          if (openIdx !== null) { if (openIdx === i) openIdx = null; else if (openIdx > i) openIdx--; }
          render();
        };
        sl.appendChild(row);
      });
      box.querySelector("#addStep").onclick = () => { captureSteps(); steps.push({ agent: agentsCache[0].slug, task: "" }); openIdx = steps.length - 1; render(); };
      box.querySelector("#cancelEd").onclick = () => editor.classList.remove("open");
      // Cùng luật với #saveAg: khoá nút trong lúc gửi, ĐỌC kết quả rồi mới đóng. Bản cũ đóng
      // khung và báo onSaved() vô điều kiện, nên lưu hỏng (server 400, mất mạng) trông y hệt
      // lưu xong - người dùng đóng tab rồi mới biết mất bài. Và onSaved phải nhận `saved`:
      // trang Cộng sự dựa vào `saved.slug` để chọn đúng quy trình vừa tạo.
      box.querySelector("#saveWf").onclick = async () => {
        captureSteps();
        if (!ten.trim()) return alert(t("studio.need_name"));
        const nutLuu = box.querySelector("#saveWf");
        nutLuu.disabled = true;
        try {
          const saved = await api("/workflows", { method: "POST", body: fd({ name: ten.trim(), description: mota,
            group: nhom.trim() || NHOM_MD, steps: JSON.stringify(steps),
            status: w ? w.status : "active", slug: w ? w.slug : "", brain: brain() }) });
          if (!saved.ok) { alert(loiLuu(saved.error)); return; }
          editor.classList.remove("open");
          if (tuyChon.onSaved) await tuyChon.onSaved(saved); else loadWorkflows();
        } catch (err) { alert(t("ws.save_failed")); }
        finally { nutLuu.disabled = false; }
      };
    }
    function captureSteps() {
      const oNe = box.querySelector("#wfName"), oMo = box.querySelector("#wfDesc"), oNh = box.querySelector("#wfGroup");
      if (oNe) ten = oNe.value;
      if (oMo) mota = oMo.value;
      if (oNh) nhom = oNh.value;
      box.querySelectorAll(".step-row").forEach((r, i) => {
        const va = r.querySelector(".st-verify-agent").value;
        steps[i] = { agent: r.querySelector(".st-agent").value, task: r.querySelector(".st-task").value };
        if (va) { steps[i].verify_agent = va; steps[i].max_retries = parseInt(r.querySelector(".st-retries").value, 10) || 0; }
      });
    }
    render(); editor.classList.add("open");
  }

  // ===== Agents =====
  const _agState = { cat: "ALL", q: "", agents: [] };

  async function loadAgents() {
    _injectStudioCss();
    const panel = document.getElementById("panel-agents");
    if (!panel) return;   // cùng lý do với loadWorkflows: trang Trợ lý riêng đã gộp vào Cộng sự
    panel.innerHTML = `<div class="empty">${esc(t("common.loading"))}</div>`;
    // Bản NHẸ: lưới thẻ chỉ hiện tên/vai/nhóm; bấm Sửa thì layAgentDay() lấy prompt.
    const d = await api(`/agents?brain=${encodeURIComponent(brain())}&prompt=0`);
    _agState.agents = d.agents || [];
    _sel.agent.clear();   // nạp lại trang là làm mới lựa chọn
    refreshStats();
    renderAgentUI();
  }

  const _agFiltered = () => locTheoNhom(_agState.agents, _agState,
    (a) => `${a.name} ${a.slug} ${a.role || ""}`);

  function renderAgentUI() {
    const panel = document.getElementById("panel-agents");
    const all = _agState.agents;
    panel.innerHTML = `<div class="panel-bar"><h3>${esc(t("page.workspace.label"))}</h3><div class="pb-actions"><button class="s-btn-ghost" id="agSelAll" title="${esc(t("studio.selall_title"))}">${esc(t("studio.selall"))}</button><button class="s-btn-ghost" id="agDl" disabled title="${esc(t("studio.dl_title"))}">${esc(t("studio.dl_sel"))}</button><button class="s-btn-ghost" id="agImport">${esc(t("studio.import"))}</button><button class="s-btn" id="newAgent">+ ${esc(t("page.workspace.label"))}</button></div></div>
      ${all.length ? khungNhomHtml(all, _agState, { bodyId: "agCards", bodyCls: "cards",
                                                    searchId: "agSearch", searchPh: t("studio.ag_search_ph") })
      : `<div class="empty">${esc(t("studio.ag_empty"))}</div>`}`;
    document.getElementById("newAgent").onclick = () => editAgent(null);
    document.getElementById("agImport").onclick = () => importItems(loadAgents);
    document.getElementById("agDl").onclick = () => taiDaChon("agent");
    document.getElementById("agSelAll").onclick = () =>
      chonTatCa("agent", "agDl", "ag-sel", _agFiltered().map(a => a.slug));
    capNhatNutTai("agent", "agDl");
    if (!all.length) return;
    ganKhungNhom(panel, _agState, { searchId: "agSearch", veLai: renderAgentUI, veDanhSach: renderAgentList });
    renderAgentList();
  }

  function renderAgentList() {
    const cards = document.getElementById("agCards"); if (!cards) return;
    const list = _agFiltered();
    datSoLuong(document.getElementById("panel-agents"), list.length + " agent");
    if (!list.length) { cards.innerHTML = `<div class="empty">${esc(t("studio.ag_no_match"))}</div>`; return; }
    cards.innerHTML = "";
    list.forEach(a => {
      const div = document.createElement("div"); div.className = "ag-card";
      div.innerHTML = `<div class="ag-name"><input type="checkbox" class="ag-sel" data-slug="${esc(a.slug)}" title="${esc(t("studio.sel_one"))}"> ${ic("bot")} ${esc(a.name)} <span class="ag-model">${esc(a.model || "")}</span></div><div class="ag-role">${esc(a.role)}</div><div class="ag-skills">${(a.skills || []).map(s => `<span class="chip-skill">${esc(s)}</span>`).join("") || `<span class="dim">${esc(t("studio.no_skills"))}</span>`}</div><div class="ag-group">${ic("folder-open")} ${esc(nhomCua(a))}</div><div class="wf-actions"><button class="s-btn-ghost edit">${esc(t("common.edit"))}</button><button class="s-btn-ghost exp" title="${esc(t("studio.export_title"))}">${esc(t("studio.export"))}</button><button class="s-btn-ghost del">${esc(t("common.delete"))}</button></div>`;
      noiSel("agent", "agDl", div.querySelector(".ag-sel"), a.slug);
      div.querySelector(".exp").onclick = () => exportItem("agent", a.slug);
      div.querySelector(".edit").onclick = () => editAgent(a);
      div.querySelector(".del").onclick = async () => { if (confirm(t("studio.del_ag", { ten: a.name }))) { await api("/agents/delete", { method: "POST", body: fd({ slug: a.slug, brain: brain() }) }); loadAgents(); } };
      cards.appendChild(div);
    });
  }

  // Giá trị một dòng trong ô chọn model của agent: "<provider>::<model>". Phải mang theo
  // NHÀ chứ không chỉ tên model, vì cùng một tên có ở hai nhà (gemini-2.5-pro: Gemini CLI
  // lẫn Gemini API; claude-*: Claude Code lẫn Anthropic API) - lưu mỗi tên là server phải
  // đoán, mà đoán sai thì chạy nhầm nhà và nhầm cả hoá đơn.
  const MODEL_SEP = "::";

  // `opts.host` = vẽ form thẳng vào một khung có sẵn (cột phải trang Cộng sự) thay vì bật
  // modal #studioEditor. Vì sao cần: trang Cộng sự muốn sửa trợ lý NGAY cạnh khung chat, mà
  // dựng bản form thứ hai ở đó là hai bản trôi lệch nhau ngay lần sửa đầu tiên (chọn model,
  // chọn skill, avatar... đều đã nằm ở đây). `opts.onSaved` thay cho loadAgents(): trang gọi
  // tự quyết vẽ lại cái gì, vì panel Studio có thể đang không tồn tại trong DOM.
  // (`opts.dsNhom` của bản cũ đã bỏ cùng ô chọn nhóm - xem khối NHÓM ở đầu file.)
  async function editAgent(a, opts) {
    opts = opts || {};
    // Có host thì KHÔNG đụng vào modal: mở/đóng nó sẽ che mất cả trang Cộng sự.
    const moDong = (mo) => { if (!opts.host) editor.classList.toggle("open", mo); };
    // Nói "đang tải" ngay: ở cột phải trang Cộng sự, khung này trống trơn suốt lúc chờ mạng
    // trông y như app bị treo.
    if (opts.host && opts.host.isConnected && !opts.host.childElementCount) {
      opts.host.innerHTML = `<div class="empty">${esc(t("common.loading"))}</div>`;
    }
    // Song song, không nối đuôi: hai lượt của form và một lượt lấy prompt cùng đi một nhịp.
    const [dsForm, day] = await Promise.all([duLieuForm(), layAgentDay(a)]);
    const [sd, st] = dsForm;
    if (day === false) {
      const hong = opts.host || document.getElementById("editorBox");
      if (hong && (!opts.host || hong.isConnected)) {
        hong.innerHTML = `<div class="empty">${esc(t("studio.ag_load_err"))}</div>` +
          `<div class="editor-actions"><button class="s-btn" id="agRetry">${esc(t("common.retry"))}</button></div>`;
        hong.querySelector("#agRetry").onclick = () => editAgent(a, opts);
        moDong(true);
      }
      return;
    }
    if (day) a = day;
    const skills = sd.skills || [];
    // CÙNG nguồn với trình chọn model chính (/settings → model.providers), nên thêm nhà mới
    // ở trang Models là ô này có ngay - và giờ là cùng cả THÂN BẢNG CHỌN (model-list.js).
    // Lấy MỌI nhà chạy được agent, KỂ CẢ nhà chưa cắm key: chúng hiện ra kèm ổ khoá và một dòng
    // chỉ chỗ mở khoá, đúng như bảng chọn model dưới khung chat. Bản cũ lọc thẳng `configured`
    // nên nhà chưa cắm key BIẾN MẤT, người dùng không biết là có nhà đó (chủ repo báo 21/09).
    // `agent_ok` thì vẫn lọc thật: server không dựng nổi engine agent cho nhà ngoài danh sách
    // (AGENT_PROVIDERS), bày ra là hứa suông - agent sẽ lặng lẽ chạy Claude.
    const provs = ((st.model || {}).providers || []).filter(p => p.agent_ok);
    const coKetNoi = provs.some(p => p.configured);
    const val = (pid, m) => pid + MODEL_SEP + m;
    const provCua = (id) => provs.find(p => p.id === id) || {};
    // Agent CŨ chỉ lưu tên model (chưa có trường `model_provider`): dò trong catalog tĩnh mà
    // /settings đã trả về để mở form lên vẫn hiện đúng nhà, thay vì bỏ trống rồi bấm Lưu là
    // server phải đi đoán. Không dò ra thì để rỗng - server có `_agent_model_provider` lo.
    const doanNha = (m) => (provs.find(p => (p.models || []).includes(m)) || {}).id || "";
    let mModel = (a && a.model) || "";
    let mProv = mModel ? ((a && a.model_provider) || doanNha(mModel)) : "";
    let mLoc = "", mMo = mProv || (provs.find(p => p.configured) || {}).id || "";
    // Nhãn trên nút. Model đang lưu mà nhà đã ngắt key thì nói thẳng "(đang lưu)" chứ KHÔNG
    // âm thầm tụt về Mặc định - đó là lựa chọn của người dùng, chỉ là tạm chưa chạy được.
    const nhanModel = () => !mModel
      ? t("studio.model_default")
      : (provCua(mProv).label ? provCua(mProv).label + " · " + mModel : mModel)
        + (mProv && !provCua(mProv).configured ? " " + t("studio.saved_suffix") : "");
    const box = opts.host || document.getElementById("editorBox");
    if (opts.host && !box.isConnected) return;
    let avatar = window.JavisAvatar ? (a ? window.JavisAvatar.of(a) : window.JavisAvatar.random()) : null;
    box.classList.add("agent-editor");
    box.innerHTML = `<h3>${esc(a ? t("studio.edit") : t("studio.create"))} Agent</h3>
      <div class="agent-avatar-picker" id="agAvatar"></div>
      <label>${esc(t("studio.name"))}</label><input id="agName" value="${esc(a ? a.name : "")}">
      <label>${esc(t("studio.role"))}</label><input id="agRole" value="${esc(a ? a.role : "")}">
      <label for="agAssets">${esc(t("studio.assets"))}</label>
      <div class="ag-assets">
        <button type="button" class="s-btn-ghost" id="agAssets"${a && a.slug ? "" : " disabled"}>${ic("paperclip")} ${esc(t("studio.assets_open"))}</button>
        <div class="dim ag-assets-hint">${esc(a && a.slug ? t("studio.assets_hint") : t("studio.assets_new"))}</div>
      </div>
      <label>${esc(t("studio.sys_prompt"))}</label><textarea id="agPrompt" rows="4">${esc(a ? (a.prompt || "") : "")}</textarea>
      <label>Skills</label>
      ${skills.length ? `<div class="sp-box">
        <div class="sp-bar"><input id="spSearch" placeholder="${esc(t("studio.sp_search_ph"))}">
          <span class="sp-count" id="spCount"></span>
          <button type="button" class="s-btn-ghost sp-clear" id="spClear">${esc(t("studio.sp_clear"))}</button></div>
        <div class="sp-groups" id="skillPick"></div>
      </div>` : `<div class="skill-pick"><span class="dim">${esc(t("studio.sp_none"))}</span></div>`}
      <label for="agModelBtn">Model</label>
      <div class="ag-model-pick" id="agModelPick">
        <button type="button" class="ag-model-btn" id="agModelBtn">
          <span id="agModelTxt">${esc(nhanModel())}</span>${ic("chevron-down")}
        </button>
        <input type="hidden" id="agModel" value="${esc(mModel ? val(mProv, mModel) : "")}">
        <div class="mb-pop ag-model-pop" id="agModelPop" hidden></div>
      </div>
      <div class="dim" style="font-size:12px;margin-top:4px">${esc(coKetNoi
        ? t("studio.model_hint")
        : t("studio.model_none"))}</div>
      <div class="editor-actions"><button class="s-btn-ghost" id="cancelEd"${opts.host ? ' style="display:none"' : ""}>${esc(t("common.cancel"))}</button><button class="s-btn" id="saveAg">${esc(t("common.save"))}</button></div>`;
    if (window.JavisAvatar) window.JavisAvatar.picker(box.querySelector("#agAvatar"), avatar, v => { avatar = v; });
    // TÀI LIỆU & LINK của trợ lý: mở ĐÚNG ngăn kéo mà project và cuộc trò chuyện đang dùng
    // (sessions-ui.js), không dựng bản thứ hai ở đây. Trợ lý chưa lưu thì chưa có slug để gắn
    // vào, nên nút đứng im kèm một câu nói vì sao - ẩn nút đi thì người dùng tưởng không có.
    const nutTaiLieu = box.querySelector("#agAssets");
    if (nutTaiLieu) nutTaiLieu.onclick = () => {
      if (!(a && a.slug)) return;
      // Ở trang Cộng sự (opts.host) thì mở ngăn có công tắc phạm vi, đứng sẵn ở "của trợ lý":
      // bấm từ Cài đặt trợ lý là ý muốn gắn cho trợ lý. Ở Studio thì cuộc đang mở không liên
      // quan gì tới trợ lý này, nên vẫn mở ngăn riêng của trợ lý như cũ.
      if (opts.host && window.JavisChatSide && window.JavisChatSide.moTaiLieu)
        window.JavisChatSide.moTaiLieu(a.slug, a.name || a.slug, "agent");
      else if (window.JavisChatSide && window.JavisChatSide.moKhungAgent)
        window.JavisChatSide.moKhungAgent(a.slug, a.name || a.slug);
    };
    box.querySelectorAll("label").forEach(label => { const input = label.nextElementSibling; if (input && /^(INPUT|SELECT|TEXTAREA)$/.test(input.tagName)) label.htmlFor = input.id; });
    // ----- Bảng chọn model: CÙNG thân với bảng dưới khung chat (model-list.js) -----
    // Danh sách model của một nhà chỉ nạp khi nhà đó được sổ ra, nên mở form sửa trợ lý không
    // còn gọi /provider/models cho mọi nhà một lượt như bản cũ.
    const mPop = box.querySelector("#agModelPop");
    const mBtn = box.querySelector("#agModelBtn");
    const dongPop = () => { if (mPop) mPop.hidden = true; };
    async function veModelPop() {
      if (!mPop) return;
      const hangMacDinh = `<div class="mb-item ${mModel ? "" : "cur"}" data-prov="" data-model="">`
        + `<span class="tick">${mModel ? "" : ic("check", { cls: "ic-ok" })}</span>`
        + `<span>${esc(t("studio.model_default"))}</span></div>`;
      const o = {
        providers: provs, expanded: mMo, filter: mLoc,
        selected: { provider: mProv, model: mModel },
        searchId: "agModelSearch", extraTop: hangMacDinh,
      };
      const loc = mLoc;
      mPop.innerHTML = await window.JavisModelList.render(o);
      // Tìm kiếm chạy trên MỌI nhà: nhà nào chưa tải thì model-list.js vẽ "đang tải" và trả
      // Promise trong o.cho; tải xong thì vẽ lại, nếu người dùng chưa gõ chữ khác.
      if (o.cho.length) Promise.all(o.cho).then(() => { if (!mPop.hidden && loc === mLoc) veModelPop(); });
      const se = box.querySelector("#agModelSearch");
      if (se) {
        se.oninput = () => { mLoc = se.value; veModelPop(); };
        se.focus(); se.selectionStart = se.selectionEnd = se.value.length;   // giữ con trỏ khi gõ
      }
    }
    if (mBtn) mBtn.onclick = async () => {
      if (!mPop.hidden) { dongPop(); return; }
      mPop.hidden = false;
      await veModelPop();
      // Ô Model nằm giữa một form dài: mở ra ở gần đáy khung là bảng chọn thò ra ngoài màn.
      // Kéo khung chứa lên vừa đủ để thấy hết bảng, không nhảy giật cả trang.
      try { mPop.scrollIntoView({ block: "nearest" }); } catch (e) {}
    };
    if (mPop) mPop.onclick = (e) => {
      const goto = e.target.closest("[data-goto]");
      if (goto) {
        dongPop();
        try { if (window.Alpine) Alpine.store("nav").go(goto.dataset.goto); } catch (er) {}
        return;
      }
      const it = e.target.closest(".mb-item");
      if (it) {
        mProv = it.dataset.prov || ""; mModel = it.dataset.model || "";
        box.querySelector("#agModel").value = mModel ? val(mProv, mModel) : "";
        box.querySelector("#agModelTxt").textContent = nhanModel();
        dongPop();
        return;
      }
      const pr = e.target.closest(".mb-prov");
      if (pr && pr.dataset.prov) { mMo = mMo === pr.dataset.prov ? "" : pr.dataset.prov; veModelPop(); }   // bấm lại là thu
    };
    // Bấm ra ngoài / Escape thì đóng. Listener TỰ GỠ khi form bị thay (mở sửa trợ lý nhiều
    // lần là dựng lại DOM), khỏi để lại một chồng closure chết bám vào document.
    const mPick = box.querySelector("#agModelPick");
    const ngoaiKhung = (e) => {
      if (!mPop || !mPop.isConnected) { document.removeEventListener("click", ngoaiKhung); return; }
      // So bằng CHÍNH phần tử, không phải closest("#agModelPick"): trang Cộng sự có thể đang
      // mở form trong cột phải trong khi Studio bật thêm form trong modal, tức hai khung cùng
      // id trên một trang - so theo id là bấm vào khung này lại không đóng khung kia.
      if (!mPop.hidden && !(mPick && mPick.contains(e.target))) dongPop();
    };
    const escKhung = (e) => {
      if (!mPop || !mPop.isConnected) { document.removeEventListener("keydown", escKhung); return; }
      if (e.key === "Escape" && !mPop.hidden) { dongPop(); e.stopPropagation(); }
    };
    document.addEventListener("click", ngoaiKhung);
    document.addEventListener("keydown", escKhung);
    // Trạng thái chọn giữ trong Set, DOM chỉ là HÌNH CHIẾU của nó. Đây là chỗ dễ hỏng nhất của
    // khung có bộ lọc: vẽ lại theo bộ lọc rồi lúc lưu mới đi đọc DOM thì mọi skill đang bị lọc
    // ra khỏi màn hình sẽ mất tick, im lặng, và người dùng chỉ phát hiện sau khi agent chạy sai.
    const chosen = new Set(a ? (a.skills || []) : []);
    renderSkillPick(box, skills, chosen);
    // Vẽ trong host thì nút Huỷ vô nghĩa (form nằm sẵn ở cột phải, không có gì để đóng) nên
    // nó đã bị ẩn ở trên; giữ handler để bấm nhầm bằng bàn phím cũng không đóng modal người
    // khác đang mở.
    box.querySelector("#cancelEd").onclick = () => { if (opts.host) return; moDong(false); };
    box.querySelector("#saveAg").onclick = async () => {
      const name = box.querySelector("#agName").value.trim(); if (!name) return alert(t("studio.need_name"));
      const sk = [...chosen].join(",");
      const raw = box.querySelector("#agModel").value;
      const cut = raw.indexOf(MODEL_SEP);
      const mProv = cut === -1 ? "" : raw.slice(0, cut);
      const mName = cut === -1 ? raw : raw.slice(cut + MODEL_SEP.length);
      const saveButton = box.querySelector("#saveAg");
      saveButton.disabled = true;
      try {
        // KHÔNG gửi `group`: form không còn ô nhóm, mà gửi một giá trị đoán ra là ghi đè nhóm
        // người dùng vừa đổi ở cột trái. Server thấy thiếu field là giữ nguyên nhóm đang có.
        const saved = await api("/agents", { method: "POST", body: fd({ name, role: box.querySelector("#agRole").value,
          prompt: box.querySelector("#agPrompt").value, skills: sk, model: mName, model_provider: mProv,
          slug: a ? a.slug : "", brain: brain(), ...(avatar ? window.JavisAvatar.formFields(avatar) : {}) }) });
        if (!saved.ok) { alert(loiLuu(saved.error)); return; }
        moDong(false);
        if (opts.onSaved) await opts.onSaved(saved); else loadAgents();
      } catch (err) { alert(t("ws.save_failed")); }
      finally { saveButton.disabled = false; }
    };
    moDong(true);
  }

  // ===== Khung chọn skill trong màn sửa Agent =====
  // Brain thật đang có 55+ skill, nên danh sách checkbox phẳng là dò bằng mắt qua cả trang.
  // Ở đây: ô tìm + gom nhóm theo field `group` sẵn có của skill (đúng nhóm mà trang Skills
  // dùng, không đẻ cách phân loại thứ hai), mỗi nhóm sổ ra thu vào được.
  function renderSkillPick(box, skills, chosen) {
    const host = box.querySelector("#skillPick");
    if (!host) return;
    const countEl = box.querySelector("#spCount");
    const searchEl = box.querySelector("#spSearch");
    // Nhóm nào đang có skill được tick thì mở sẵn: người sửa agent quan tâm cái đang bật trước.
    const openGroups = new Set(skills.filter(s => chosen.has(s.slug)).map(s => s.group || "Chung"));
    let q = "";

    const draw = () => {
      const nq = _spNoAccent(q.trim());
      const hop = (s) => !nq || nq.split(/\s+/).every(word => _spNoAccent(`${s.name} ${s.slug} ${s.group || ""} ${s.description || ""}`).includes(word));
      const groups = new Map();
      skills.forEach(s => {
        if (!hop(s)) return;
        const g = s.group || "Chung";
        if (!groups.has(g)) groups.set(g, []);
        groups.get(g).push(s);
      });
      if (countEl) countEl.textContent = t("studio.sp_count", { a: chosen.size, b: skills.length });
      if (!groups.size) { host.innerHTML = `<div class="dim sp-empty">${esc(t("studio.sp_empty", { q }))}</div>`; return; }
      host.innerHTML = "";
      [...groups.keys()].sort((x, y) => x.localeCompare(y, LOC())).forEach(g => {
        const list = groups.get(g);
        const nSel = list.filter(s => chosen.has(s.slug)).length;
        // Đang tìm thì mọi nhóm còn khớp đều sổ ra - lọc xong mà vẫn phải bấm mở từng nhóm
        // thì ô tìm chẳng đỡ được gì.
        const open = !!nq || openGroups.has(g);
        const wrap = document.createElement("div");
        wrap.className = "sp-g" + (open ? " open" : "");
        wrap.innerHTML = `<button type="button" class="sp-g-head">
            <span class="sp-g-caret">${ic("chevron-right")}</span>
            <span class="sp-g-name">${esc(g)}</span>
            <span class="sp-g-n">${nSel ? `${nSel}/${list.length}` : list.length}</span>
          </button><div class="sp-g-body"></div>`;
        const body = wrap.querySelector(".sp-g-body");
        list.forEach(s => {
          const lb = document.createElement("label");
          lb.className = "sp";
          lb.title = s.description || s.name;
          lb.innerHTML = `<input type="checkbox" value="${esc(s.slug)}"${chosen.has(s.slug) ? " checked" : ""}> <span>${esc(s.name)}</span>`;
          lb.querySelector("input").onchange = (e) => {
            if (e.target.checked) { chosen.add(s.slug); openGroups.add(g); } else chosen.delete(s.slug);
            // Vẽ lại để con số của nhóm và ô đếm khớp ngay; Set là nguồn sự thật nên an toàn.
            draw();
          };
          body.appendChild(lb);
        });
        wrap.querySelector(".sp-g-head").onclick = () => {
          if (openGroups.has(g)) openGroups.delete(g); else openGroups.add(g);
          wrap.classList.toggle("open");
        };
        host.appendChild(wrap);
      });
    };

    if (searchEl) searchEl.oninput = () => { q = searchEl.value; draw(); };
    const clearBtn = box.querySelector("#spClear");
    if (clearBtn) clearBtn.onclick = () => { chosen.clear(); draw(); };
    draw();
  }

  // ===== Skills (cột nhóm + tìm kiếm + bật/tắt) =====
  // 0.75.0 thiết kế lại theo bản mẫu chủ repo duyệt 05/10: mỗi thẻ có ô tick CHỌN ĐỂ XUẤT ở
  // đầu và công tắc bật/tắt ở cuối (trước đây hai ô tick cùng kiểu đứng hai đầu thẻ, ô cam bật/
  // tắt trông y như ô chọn nên bấm "chọn" là tắt luôn skill), bấm thân thẻ mở khung chi tiết,
  // tick từ một skill trở lên thì hiện thanh xuất. Lọc theo trạng thái + sắp xếp nằm cạnh ô tìm.
  const _skState = { cat: "ALL", q: "", skills: [], status: "all", sort: "used", page: 0,
                     open: "", merged: [], bodies: Object.create(null) };

  // Trần mô tả của bộ định tuyến skill: server/skill_router.SKILL_DESC_MAX. Vượt trần thì router
  // cắt im lặng phần đuôi và POST /skills từ chối lưu, nên form phải đếm trước cho người viết.
  // tests/python/test_trang_ky_nang.py ghim hai con số này bằng nhau.
  const SKILL_DESC_MAX = 150;
  const _doDai = (s) => [...String(s || "").trim()].length;   // đếm như len() của Python

  // CSS tiêm một lần cho CẢ BA trang Studio: phần `.gr*` là khung nhóm dùng chung (cột nhóm +
  // ô tìm), phần `.sk3*`/`.ag-group`/`.wf-group` là thẻ riêng của từng trang.
  function _injectStudioCss() {
    if (window._skCss) return; window._skCss = true;
    const css = `
    .gr{display:flex;gap:16px;align-items:flex-start}
    .gr-side{width:210px;flex:none;border:1px solid var(--hairline);border-radius:10px;padding:8px;max-height:72vh;overflow:auto}
    .gr-side .sec{font-size:12px;letter-spacing:.08em;color:var(--text3);padding:8px 10px 4px;text-transform:uppercase}
    .gr-cat{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 10px;border-radius:7px;cursor:pointer;font-size:15px;color:var(--text)}
    .gr-cat:hover{background:rgba(120,180,255,.08)} .gr-cat.sel{background:var(--info-wash);color:var(--info-ink)}
    .gr-cat .n{color:var(--text3);font-size:13px;flex:none}
    .gr-main{flex:1;min-width:0}
    .gr-bar{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
    .gr-bar h4{margin:0;font-size:17px;color:var(--text)} .gr-bar .cnt{color:var(--text3);font-size:14px}
    .gr-bar input{flex:1;min-width:160px;max-width:340px;padding:7px 11px;border-radius:8px;border:1px solid var(--hairline);background:var(--field-bg);color:var(--text);font-size:15px;outline:none}
    /* Nhãn nhóm trên thẻ agent và hàng workflow: nhìn thẻ là biết nó thuộc nhóm nào, khỏi phải
       mở form ra xem. Cùng biểu tượng thư mục với dòng nhóm ở thẻ skill. */
    .ag-group{color:var(--text3);font-size:13px;margin-top:7px;display:flex;align-items:center;gap:5px}
    .wf-group{color:var(--text3);font-size:13px;display:inline-flex;align-items:center;gap:4px;flex:none}
    .sk2-list{display:flex;flex-direction:column;gap:8px;flex:1;min-width:0}
    /* .sk2-list là flex cột, nên hàng phân trang phải tự căn giữa - để mặc định nó dính mép
       trái, nhìn như rơi rớt lại chứ không ra một hàng điều khiển. */
    .sk2-list .jv-pager{justify-content:center}

    /* ---- Trang Kỹ năng (0.75.0) ---- một màu nhấn: cam của app, không tím, không xanh */
    #panel-skills .gr-cat.sel{background:var(--accent-wash-2);color:var(--accent-ink);font-weight:600}
    #panel-skills .gr-cat.sel .n{color:var(--accent-ink)}
    #panel-skills .gr-cat:hover{background:var(--surface-2)}
    .sk3-top h3{font-weight:600}
    .sk3-top .pb-actions{flex-wrap:wrap}
    .sk3-top .pb-actions button{display:inline-flex;align-items:center;gap:6px}
    .sk3-new{background:var(--accent-solid)!important}
    .sk3-all{display:flex;align-items:center;justify-content:center;width:40px;height:40px;flex:none;cursor:pointer}
    .sk3-all input,.sk3-pick input{width:18px;height:18px;accent-color:var(--accent-solid);cursor:pointer;margin:0}
    .sk3-seg{display:flex;gap:3px;padding:3px;border-radius:10px;background:var(--surface-2)}
    .sk3-seg button{height:34px;padding:0 12px;border:0;border-radius:8px;background:transparent;color:var(--text2);font-size:13.5px;font-weight:500;cursor:pointer}
    .sk3-seg button.sel{background:var(--panel-solid);color:var(--text);box-shadow:var(--shadow-1)}
    .sk3-sort{display:flex;align-items:center;gap:6px;font-size:13.5px;color:var(--text2)}
    .sk3-sort select{height:36px;padding:0 8px;border-radius:8px;border:1px solid var(--hairline);background:var(--field-bg);color:var(--text);font-size:14px}
    .sk3-merged{margin:10px 6px 2px;padding-top:10px;border-top:1px solid var(--hairline);font-size:12.5px;line-height:1.5;color:var(--text3)}
    .sk3-cols{display:flex;gap:16px;align-items:flex-start}
    .sk3-card{display:flex;align-items:center;gap:6px;padding:2px 6px 2px 2px;border:1px solid var(--hairline);border-radius:12px;background:var(--panel-bg)}
    .sk3-card:hover{border-color:var(--accent-line)}
    .sk3-card.open{border-color:var(--accent-line);background:var(--accent-wash)}
    .sk3-pick{display:flex;align-items:center;justify-content:center;width:40px;height:44px;flex:none;cursor:pointer}
    .sk3-pick input:disabled{cursor:not-allowed;opacity:.45}
    .sk3-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px;padding:11px 8px;border:0;border-radius:10px;background:transparent;color:inherit;text-align:left;cursor:pointer;font:inherit}
    .sk3-card.off .sk3-main{opacity:.55}
    .sk3-main:focus-visible,.sk3-sw:focus-visible{outline:2px solid var(--accent-solid);outline-offset:2px}
    .sk3-nm{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:15px;font-weight:600;color:var(--text)}
    .sk3-main:hover .sk3-nm{color:var(--accent-ink)}
    .sk3-ds{font-size:14px;line-height:1.5;color:var(--text2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
    .sk3-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px;color:var(--text3)}
    .sk3-chip{padding:2px 9px;border-radius:999px;background:var(--surface-2);color:var(--text2);font-weight:500}
    .sk3-warn{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:999px;background:var(--warn-wash);color:var(--warn-ink);font-weight:500}
    .sysb{display:inline-flex;align-items:center;gap:4px;padding:1px 8px;border-radius:999px;border:1px solid var(--hairline);font-size:11.5px;font-weight:600;color:var(--text2)}
    .sk3-sw{flex:none;display:flex;align-items:center;justify-content:center;width:52px;height:44px;padding:0;border:0;background:transparent;cursor:pointer}
    .sk3-tr{position:relative;display:block;width:40px;height:22px;border-radius:999px;background:var(--surface-3);transition:background .15s}
    .sk3-kn{position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(28,26,36,.3);transition:left .15s}
    .sk3-sw[aria-checked="true"] .sk3-tr{background:var(--accent-solid)}
    .sk3-sw[aria-checked="true"] .sk3-kn{left:20px}
    .sk3-sw:disabled{opacity:.5;cursor:wait}
    /* Thanh xuất: nền đảo màu so với trang (chữ sáng trên nền tối ở tông sáng, ngược lại ở tông
       tối) để tách hẳn khỏi danh sách - nó là việc ĐANG làm dở, không phải một thẻ nữa. */
    .sk3-bulk{display:flex;flex-direction:column;gap:8px;padding:12px 14px;margin-bottom:10px;border-radius:12px;background:var(--text);color:var(--bg)}
    .sk3-bulk-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
    .sk3-bulk-row strong{font-size:14.5px;margin-right:auto}
    .sk3-bulk-row.sub{font-size:13px}
    .sk3-bulk-hint{margin-right:auto;opacity:.78;flex:1 1 260px;line-height:1.45}
    .sk3-bulk button{height:34px;padding:0 12px;border-radius:8px;border:1px solid color-mix(in srgb, var(--bg) 35%, transparent);background:transparent;color:var(--bg);font-size:13.5px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
    .sk3-bulk button.main{border:0;background:var(--accent-solid);color:var(--on-accent);font-weight:600;height:38px;padding:0 16px;font-size:14px}
    .sk3-bulk button.link{border:0;text-decoration:underline}
    .sk3-bulk button:disabled{opacity:.55;cursor:wait}
    .sk3-detail{flex:0 0 360px;max-width:400px;box-sizing:border-box;display:flex;flex-direction:column;gap:16px;padding:18px;border:1px solid var(--hairline);border-radius:14px;background:var(--panel-solid);box-shadow:var(--shadow-2)}
    .sk3-detail[hidden],.sk3-scrim[hidden],#skBulk[hidden],.sk3-d-sec[hidden]{display:none}   /* display:flex đè thuộc tính hidden */
    .sk3-d-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
    .sk3-d-head h4{margin:0;font-size:18px;line-height:1.3;color:var(--text);word-break:break-word}
    .sk3-d-sub{font-size:13px;color:var(--text3);margin-top:4px}
    .sk3-x{flex:none;width:36px;height:36px;border-radius:8px;border:0;background:var(--surface-2);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px}
    .sk3-d-state{display:flex;justify-content:space-between;align-items:center;padding:4px 4px 4px 12px;border-radius:10px;background:var(--surface-1);font-size:14px;font-weight:500;color:var(--text)}
    .sk3-d-sec{display:flex;flex-direction:column;gap:7px}
    .sk3-d-sec h5{margin:0;font-size:13px;font-weight:600;color:var(--text2);display:flex;justify-content:space-between;gap:8px}
    .sk3-d-sec p{margin:0;font-size:14px;line-height:1.55;color:var(--text)}
    .sk3-d-sec ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px;font-size:14px;line-height:1.5;color:var(--text)}
    .sk3-n{font-variant-numeric:tabular-nums;color:var(--green)} .sk3-n.over{color:var(--red)}
    .sk3-cut{background:var(--danger-wash);color:var(--red);text-decoration:line-through}
    .sk3-note{padding:8px 10px;border-radius:8px;background:var(--warn-wash);font-size:13px!important;line-height:1.5;color:var(--warn-ink)!important}
    .sk3-path{font-size:12.5px!important;color:var(--text3)!important}
    .sk3-path code{font-family:ui-monospace,Consolas,monospace;font-size:12px;padding:1px 5px;border-radius:4px;background:var(--code-bg);color:var(--code-ink);word-break:break-all}
    .sk3-full summary{cursor:pointer;font-size:13px;font-weight:600;color:var(--text2)}
    .sk3-full .sk3-md{margin-top:8px;max-height:320px;overflow:auto;font-size:13.5px;line-height:1.55;padding:10px 12px;border-radius:8px;background:var(--surface-1)}
    .sk3-d-act{display:flex;flex-wrap:wrap;gap:8px;padding-top:14px;border-top:1px solid var(--hairline)}
    .sk3-d-act button{height:40px;padding:0 14px;border-radius:9px;font-size:14px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;gap:6px;border:1px solid var(--hairline);background:var(--panel-solid);color:var(--text)}
    .sk3-d-act button.pri{border:0;background:var(--accent-solid);color:var(--on-accent);font-weight:600}
    .sk3-d-act button.del{margin-left:auto;border:0;background:transparent;color:var(--red)}
    .sk3-d-act .sk3-sysnote{flex-basis:100%;margin:0;font-size:12.5px;line-height:1.5;color:var(--text3)}
    .sk3-scrim{position:fixed;inset:0;background:var(--scrim);z-index:59;display:none}
    /* Form sửa: một cột, nút Lưu ở cuối (chủ repo: trang cài đặt xếp một cột). */
    .sk3-form{display:flex;flex-direction:column;gap:18px;max-width:720px}
    .sk3-form .fld{display:flex;flex-direction:column;gap:6px}
    .sk3-form .fld > label,.sk3-form .lbl{font-size:14px;font-weight:600;color:var(--text)}
    .sk3-form .row{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
    .sk3-form .hint{font-size:12.5px;line-height:1.5;color:var(--text3)}
    .sk3-form .hint.over{color:var(--red)}
    .sk3-form textarea.over{border-color:var(--red)!important}
    .sk3-form .tabs{display:flex;gap:3px;padding:3px;border-radius:9px;background:var(--surface-2)}
    .sk3-form .tabs button{height:30px;padding:0 12px;border:0;border-radius:7px;background:transparent;color:var(--text2);font-size:13px;cursor:pointer}
    .sk3-form .tabs button.sel{background:var(--panel-solid);color:var(--text);box-shadow:var(--shadow-1)}
    .sk3-form .prev{min-height:200px;padding:12px 14px;border:1px solid var(--hairline);border-radius:9px;background:var(--panel-solid);font-size:14px;line-height:1.55}
    .sk3-form .err{padding:9px 12px;border-radius:9px;background:var(--danger-wash);border:1px solid var(--danger-line);color:var(--red);font-size:13.5px}
    .sk3-form .acts{display:flex;gap:10px}
    .sk3-form .acts .s-btn{background:var(--accent-solid)}
    /* Màn vừa (laptop nhỏ, máy tính bảng): khung chi tiết thành ngăn kéo bên phải đè lên trang
       thay vì chen cột thứ ba bóp danh sách. */
    @media (max-width:1180px){
      .sk3-detail{position:fixed;top:0;right:0;bottom:0;z-index:60;width:min(420px,100vw);max-width:none;border-radius:0;overflow:auto}
      .sk3-scrim:not([hidden]){display:block}
    }
    /* ===== Mobile (<=860px) ===== xep DOC: nhom thanh dai chip cuon ngang o tren, danh sach
       full-width ben duoi (truoc day cot nhom 210px bop cot con lai con ~150px -> chu vo tung
       tu). */
    @media (max-width:860px){
      .gr{flex-direction:column;gap:12px}
      .gr-side{width:auto;max-height:none;display:flex;flex-direction:row;gap:6px;padding:6px;
        overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch}
      .gr-side::-webkit-scrollbar{height:0}
      .gr-side .sec{display:none}
      .gr-cat{flex:none;padding:8px 13px;border:1px solid var(--hairline);
        border-radius:999px;white-space:nowrap}
      .gr-cat .n{padding:1px 6px;border-radius:9px;background:var(--surface-3)}
      .gr-cat.sel{border-color:var(--info-line)}
      #panel-skills .gr-cat.sel{border-color:var(--accent-line)}
      .gr-bar input{max-width:none;font-size:16px}   /* 16px: chan iOS tu zoom khi focus */
      .sk3-merged{display:none}
      .sk3-top{flex-wrap:wrap;gap:10px}
      .sk3-top h3{flex:1 1 100%}
      .sk3-bulk-hint{flex-basis:100%;font-size:12.5px}
      .sk3-pick{width:44px}
      .sk3-pick input,.sk3-all input{width:20px;height:20px}
      .sk3-nm{font-size:16px}
      .sk3-detail{top:auto;left:0;width:100%;max-height:86vh;border-radius:16px 16px 0 0}
    }`;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  }

  // ---- Gộp nhóm trùng tên ----
  // Ô Nhóm cũ là ô gõ tự do nên một brain dùng lâu có "ai" cạnh "AI", "vận-hành" cạnh "Vận hành"
  // (ảnh chủ repo 05/10). Gộp theo khoá bỏ dấu + chữ thường + gạch nối thành dấu cách, lấy tên
  // của BẢN ĐÔNG NHẤT làm tên hiển thị (hoà thì ưu tiên tên có dấu, viết hoa, không gạch nối).
  // Chỉ gộp KHI HIỂN THỊ; lưu skill qua form là file được sửa về tên chuẩn.
  const _khoaNhom = (g) => _spNoAccent(g).replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  const _diemTen = (g) => (/[^\x00-\x7f]/.test(g) ? 2 : 0)
    + (g && g[0] !== g[0].toLowerCase() ? 1 : 0) + (/[-_]/.test(g) ? 0 : 1);
  function gopNhomSkill(skills) {
    const theoKhoa = new Map();
    skills.forEach(s => {
      const g = nhomCua(s), k = _khoaNhom(g);
      if (!theoKhoa.has(k)) theoKhoa.set(k, new Map());
      const m = theoKhoa.get(k); m.set(g, (m.get(g) || 0) + 1);
    });
    const chuan = new Map(), daGop = [];
    theoKhoa.forEach((m, k) => {
      const ds = [...m.entries()].sort((a, b) => b[1] - a[1] || _diemTen(b[0]) - _diemTen(a[0]));
      chuan.set(k, ds[0][0]);
      ds.slice(1).forEach(([ten]) => daGop.push(ten + " → " + ds[0][0]));
    });
    skills.forEach(s => { s.groupRaw = nhomCua(s); s.group = chuan.get(_khoaNhom(s.groupRaw)); });
    return daGop;
  }
  const _nhomDangCo = () => [...new Set(_skState.skills.map(nhomCua))].sort((a, b) => a.localeCompare(b, LOC()));

  async function loadSkills() {
    _injectStudioCss();
    const panel = document.getElementById("panel-skills");
    panel.innerHTML = `<div class="empty">${esc(t("common.loading"))}</div>`;
    let d; try { d = await api(`/skills?brain=${encodeURIComponent(brain())}`); } catch (e) { panel.innerHTML = `<div class="empty">${esc(t("studio.sk_load_err"))}</div>`; return; }
    refreshStats();
    _sel.skill.clear();   // nạp lại là làm mới lựa chọn (danh sách có thể đã đổi)
    _skState.bodies = Object.create(null);
    napDanhSach(d);
    renderSkillUI();
  }

  function napDanhSach(d) {
    _skState.skills = (d && d.skills) || [];
    _skState.merged = gopNhomSkill(_skState.skills);
    if (_skState.open && !_skState.skills.some(s => s.slug === _skState.open)) _skState.open = "";
  }

  // Tải lại mà GIỮ trang đang xem và các ô đã tick (sau khi bật/tắt cả loạt).
  async function taiLaiGiuViTri() {
    const d = await api(`/skills?brain=${encodeURIComponent(brain())}`);
    if (!d || !Array.isArray(d.skills)) return;
    napDanhSach(d);
    const con = new Set(_skState.skills.map(s => s.slug));
    [..._sel.skill].forEach(sl => { if (!con.has(sl)) _sel.skill.delete(sl); });
    renderSkillUI(); refreshStats();
  }

  const _skFiltered = () => {
    let list = locTheoNhom(_skState.skills, _skState,
      (s) => `${s.name} ${s.slug} ${s.description || ""} ${s.group || ""}`);
    if (_skState.status === "on") list = list.filter(s => s.enabled !== false);
    else if (_skState.status === "off") list = list.filter(s => s.enabled === false);
    else if (_skState.status === "system") list = list.filter(s => s.system);
    list = list.slice();
    if (_skState.sort === "name") list.sort((a, b) => String(a.name).localeCompare(String(b.name), LOC()));
    else if (_skState.sort === "off") list.sort((a, b) => (a.enabled === false ? 0 : 1) - (b.enabled === false ? 0 : 1));
    else list.sort((a, b) => (b.use_count || 0) - (a.use_count || 0));   // sort ổn định: hoà giữ thứ tự server
    return list;
  };

  const SK_TRANG_THAI = [["all", "studio.sk_st_all"], ["on", "studio.sk_st_on"],
                         ["off", "studio.sk_st_off"], ["system", "studio.sk_st_sys"]];
  const SK_SAP_XEP = [["used", "studio.sk_sort_used"], ["name", "studio.sk_sort_name"], ["off", "studio.sk_sort_off"]];

  function renderSkillUI() {
    const panel = document.getElementById("panel-skills");
    const all = _skState.skills;
    const enabledN = all.filter(s => s.enabled !== false).length;
    panel.innerHTML = `
      <div class="panel-bar sk3-top"><h3 id="skHead">${esc(t("studio.sk_count", { n: all.length, on: enabledN }))}</h3>
        <div class="pb-actions"><button class="s-btn-ghost" id="skImport">${ic("package")} ${esc(t("studio.sk_import"))}</button><button class="s-btn sk3-new" id="skNew">${ic("plus")} ${esc(t("studio.sk_new_btn"))}</button></div></div>
      ${all.length ? khungNhomHtml(all, _skState, { bodyId: "skBody", bodyCls: "sk3-body",
                                                    searchId: "skSearch", searchPh: t("studio.sk_search_ph2") })
      : `<div class="empty">${esc(t("studio.sk_empty"))}</div>`}`;
    document.getElementById("skNew").onclick = () => openSkillForm(null);
    document.getElementById("skImport").onclick = () => importItems(loadSkills);
    if (!all.length) return;

    const bar = panel.querySelector(".gr-bar");
    bar.insertAdjacentHTML("afterbegin", `<label class="sk3-all" title="${esc(t("studio.sk_selall_aria"))}"><input type="checkbox" id="skAll" aria-label="${esc(t("studio.sk_selall_aria"))}"></label>`);
    bar.insertAdjacentHTML("beforeend", `<div class="sk3-seg" role="group" aria-label="${esc(t("studio.sk_status_aria"))}">${
      SK_TRANG_THAI.map(([k, nhan]) => `<button type="button" data-st="${k}" class="${_skState.status === k ? "sel" : ""}" aria-pressed="${_skState.status === k}">${esc(t(nhan))}</button>`).join("")
    }</div><label class="sk3-sort">${esc(t("studio.sk_sort"))} <select id="skSort">${
      SK_SAP_XEP.map(([k, nhan]) => `<option value="${k}"${_skState.sort === k ? " selected" : ""}>${esc(t(nhan))}</option>`).join("")
    }</select></label>`);
    if (_skState.merged.length) {
      panel.querySelector(".gr-side").insertAdjacentHTML("beforeend",
        `<div class="sk3-merged">${esc(t("studio.sk_merged", { ds: _skState.merged.join(", ") }))}</div>`);
    }
    document.getElementById("skBody").innerHTML = `<div id="skBulk" hidden></div>
      <div class="sk3-cols"><div class="sk2-list" id="skList"></div><aside class="sk3-detail" id="skDetail" aria-label="${esc(t("studio.sk_detail_aria"))}" hidden></aside></div>
      <div class="sk3-scrim" id="skScrim" hidden></div>`;

    // Chọn tất cả = toàn bộ danh sách ĐANG HIỆN (đúng nhóm + bộ lọc + ô tìm), trừ skill hệ
    // thống - chúng không xuất được (server bỏ qua) vì brain nào cũng có sẵn theo app.
    // Khác chonTatCa() của Agents/Workflows: chỉ THÊM/BỚT phần đang hiện, không thay cả tập, vì
    // thanh xuất giữ lựa chọn xuyên nhóm (tick ở Bán hàng rồi sang Marketing chọn tất cả thì
    // mấy skill Bán hàng vẫn còn trong gói).
    document.getElementById("skAll").onchange = () => {
      const ds = _skFiltered().filter(s => !s.system).map(s => s.slug);
      const du = ds.length > 0 && ds.every(sl => _sel.skill.has(sl));
      ds.forEach(sl => { if (du) _sel.skill.delete(sl); else _sel.skill.add(sl); });
      document.querySelectorAll(".sk2-sel").forEach(c => { c.checked = _sel.skill.has(c.dataset.slug); });
      veThanhChon();
    };
    panel.querySelectorAll(".sk3-seg [data-st]").forEach(b => {
      b.onclick = () => { _skState.status = b.dataset.st; _skState.page = 0; renderSkillUI(); };
    });
    document.getElementById("skSort").onchange = (e) => { _skState.sort = e.target.value; _skState.page = 0; renderSkillList(); };
    document.getElementById("skScrim").onclick = dongChiTiet;
    ganKhungNhom(panel, _skState, { searchId: "skSearch",
      veLai: () => { _skState.page = 0; renderSkillUI(); },
      veDanhSach: () => { _skState.page = 0; renderSkillList(); } });
    renderSkillList();
    veThanhChon();
    veChiTiet();
  }

  const SK_MOI_TRANG = 20;   // brain dùng lâu có cả trăm skill: đổ hết ra là cuộn mãi không hết

  function renderSkillList() {
    const box = document.getElementById("skList"); if (!box) return;
    const list = _skFiltered();
    datSoLuong(document.getElementById("panel-skills"), t("studio.sk_n", { n: list.length }));
    capNhatChonTatCa(list);
    if (!list.length) { box.innerHTML = `<div class="empty">${esc(t("studio.sk_no_match"))}</div>`; return; }
    const veTrang = (phan) => {
      const fr = document.createDocumentFragment();
      phan.forEach(s => fr.appendChild(theSkill(s)));
      return fr;
    };
    // Phân trang bằng pager() dùng chung của console.js. Đổi nhóm, bộ lọc hay ô tìm thì nơi gọi
    // đặt page về 0; bật/tắt một skill thì KHÔNG, nên người đang ở trang 3 vẫn ở trang 3.
    if (typeof window.JavisPager === "function") {
      window.JavisPager(box, list, SK_MOI_TRANG, veTrang, "",
                        { page: _skState.page, onPage: (p) => { _skState.page = p; } });
    } else {
      box.innerHTML = ""; box.appendChild(veTrang(list));
    }
  }

  // Một thẻ skill. Tách khỏi renderSkillList để phân trang gọi lại được từng trang một, và để
  // bật/tắt chỉ thay đúng một thẻ thay vì vẽ lại cả trang.
  function theSkill(s) {
    const on = s.enabled !== false;
    const div = document.createElement("div");
    div.className = "sk3-card" + (on ? "" : " off") + (_skState.open === s.slug ? " open" : "");
    div.dataset.slug = s.slug;
    const sysBadge = s.system ? ` <span class="sysb" title="${esc(t("studio.sys_title"))}">${ic("lock")} ${esc(t("studio.sk_sys_badge"))}</span>` : "";
    // Telemetry: use_count là tín hiệu DƯƠNG một chiều. Skill nạp native qua .claude/skills
    // không đi qua bộ đếm, nên chưa có số thì im, không in "chưa thấy dùng" lên gần hết các thẻ.
    let usageHtml = "";
    if (s.use_count > 0) {
      const when = s.last_used_at ? new Date(s.last_used_at * 1000).toLocaleDateString(LOC()) : "";
      usageHtml = `<span>${esc(t("studio.used", { n: s.use_count }))}${when ? ", " + esc(t("studio.last_used")) + " " + when : ""}</span>`;
    }
    const quaDai = _doDai(s.description) > SKILL_DESC_MAX
      ? `<span class="sk3-warn">${ic("triangle-alert")} ${esc(t("studio.sk_too_long"))}</span>` : "";
    div.innerHTML = `<label class="sk3-pick" title="${esc(s.system ? t("studio.sk_pick_sys") : t("studio.sel_one"))}"><input type="checkbox" class="sk2-sel" data-slug="${esc(s.slug)}"${s.system ? " disabled" : ""} aria-label="${esc(t("studio.sk_pick_aria", { ten: s.name }))}"></label>
      <button type="button" class="sk3-main"><span class="sk3-nm">${esc(s.name)}${sysBadge}</span><span class="sk3-ds">${esc(s.description || "")}</span><span class="sk3-meta"><span class="sk3-chip">${esc(nhomCua(s))}</span>${usageHtml}${quaDai}</span></button>
      <button type="button" class="sk3-sw" role="switch" aria-checked="${on}" title="${esc(on ? t("studio.tog_on") : t("studio.tog_off"))}" aria-label="${esc(t("studio.sk_sw_aria", { ten: s.name }))}"><span class="sk3-tr"><span class="sk3-kn"></span></span></button>`;
    const selBox = div.querySelector(".sk2-sel");
    if (!s.system) {
      noiSel("skill", "skDl", selBox, s.slug);
      selBox.addEventListener("change", veThanhChon);
    }
    div.querySelector(".sk3-main").onclick = () => moChiTiet(s.slug);
    const sw = div.querySelector(".sk3-sw");
    sw.onclick = () => { sw.disabled = true; toggleSkill(s, !on); };
    return div;
  }

  // Ô "Chọn tất cả": tick khi mọi skill xuất được đang hiện đều đã chọn, gạch ngang khi chọn một phần.
  function capNhatChonTatCa(list) {
    const el = document.getElementById("skAll"); if (!el) return;
    const ds = (list || _skFiltered()).filter(s => !s.system);
    const n = ds.filter(s => _sel.skill.has(s.slug)).length;
    el.checked = ds.length > 0 && n === ds.length;
    el.indeterminate = n > 0 && n < ds.length;
    el.disabled = !ds.length;
  }

  // Thanh xuất: hiện khi đã tick ít nhất một skill. Gói .zip đã sẵn cấu trúc chuẩn
  // skills/<slug>/SKILL.md nên KHÔNG có ô chọn định dạng: cùng một gói nhập lại được vào Javis
  // và giải nén vào .claude là Claude Code dùng ngay.
  function veThanhChon() {
    const bar = document.getElementById("skBulk"); if (!bar) return;
    capNhatChonTatCa();
    const n = _sel.skill.size;
    if (!n) { bar.hidden = true; bar.innerHTML = ""; return; }
    bar.hidden = false;
    bar.innerHTML = `<div class="sk3-bulk" role="region" aria-label="${esc(t("studio.sk_picked", { n }))}">
      <div class="sk3-bulk-row"><strong>${esc(t("studio.sk_picked", { n }))}</strong><button type="button" class="main" id="skBulkExport">${ic("download")} ${esc(t("studio.sk_export_n", { n }))}</button></div>
      <div class="sk3-bulk-row sub"><span class="sk3-bulk-hint">${esc(t("studio.sk_export_hint"))}</span><button type="button" id="skBulkOn">${esc(t("studio.sk_bulk_on"))}</button><button type="button" id="skBulkOff">${esc(t("studio.sk_bulk_off"))}</button><button type="button" class="link" id="skBulkClear">${esc(t("studio.sk_bulk_clear"))}</button></div></div>`;
    document.getElementById("skBulkExport").onclick = () => taiDaChon("skill");
    document.getElementById("skBulkOn").onclick = () => batTatLoat(true);
    document.getElementById("skBulkOff").onclick = () => batTatLoat(false);
    document.getElementById("skBulkClear").onclick = () => {
      _sel.skill.clear();
      document.querySelectorAll(".sk2-sel").forEach(c => { c.checked = false; });
      veThanhChon();
    };
  }

  async function batTatLoat(enabled) {
    const ds = _skState.skills.filter(s => _sel.skill.has(s.slug) && (s.enabled !== false) !== enabled);
    document.querySelectorAll("#skBulk button").forEach(b => { b.disabled = true; });
    const loi = [];
    for (const s of ds) {   // tuần tự: mỗi lần là đổi tên thư mục + đồng bộ mirror trên đĩa
      const r = await api("/skills/toggle", { method: "POST", body: fd({ slug: s.slug, enabled: enabled ? "1" : "0", brain: brain() }) });
      if (!r || !r.ok) loi.push(s.name + ((r && r.error) ? ": " + r.error : ""));
    }
    quenForm();
    if (loi.length) alert(t("studio.toggle_err") + "\n" + loi.join("\n"));
    await taiLaiGiuViTri();
  }

  async function toggleSkill(s, enabled) {
    const r = await api("/skills/toggle", { method: "POST", body: fd({ slug: s.slug, enabled: enabled ? "1" : "0", brain: brain() }) });
    quenForm();   // danh sách skill của form trợ lý vừa đổi
    if (!r || !r.ok) {
      alert(t("studio.toggle_err") + " " + ((r && r.error) || t("studio.sk_net_err")));
    } else {
      s.enabled = enabled;
      refreshStats();
    }
    capNhatMotThe(s);
  }

  // Thay đúng thẻ của một skill + số đếm đầu trang + khung chi tiết, không vẽ lại cả trang.
  function capNhatMotThe(s) {
    const box = document.getElementById("skList");
    const cu = box && [...box.querySelectorAll(".sk3-card")].find(el => el.dataset.slug === s.slug);
    if (cu) cu.replaceWith(theSkill(s));
    const head = document.getElementById("skHead");
    if (head) head.textContent = t("studio.sk_count", { n: _skState.skills.length,
      on: _skState.skills.filter(x => x.enabled !== false).length });
    if (_skState.open === s.slug) veChiTiet();
  }

  // ---- Khung chi tiết ----
  function moChiTiet(slug) {
    _skState.open = slug;
    document.querySelectorAll("#skList .sk3-card").forEach(el => el.classList.toggle("open", el.dataset.slug === slug));
    veChiTiet();
    const x = document.querySelector("#skDetail .sk3-x"); if (x) x.focus({ preventScroll: true });
  }

  function dongChiTiet() {
    _skState.open = "";
    document.querySelectorAll("#skList .sk3-card.open").forEach(el => el.classList.remove("open"));
    veChiTiet();
  }

  // Lấy các gạch đầu dòng của mục "When to use" / "Dùng khi nào" trong SKILL.md (quy ước của
  // javis-builder: ví dụ kích hoạt nằm trong thân, mô tả chỉ 150 ký tự).
  function phanDungKhiNao(body) {
    const dong = String(body || "").split(/\r?\n/);
    const i = dong.findIndex(l => /^#{1,4}\s*(when to use|dùng khi nào|khi nào dùng|khi nào nên dùng)\b/i.test(l.trim()));
    if (i < 0) return [];
    const out = [];
    for (let j = i + 1; j < dong.length && out.length < 8; j++) {
      const l = dong[j].trim();
      if (/^#{1,4}\s/.test(l)) break;
      const m = l.match(/^(?:[-*+]|\d+[.)])\s+(.*)$/);
      if (m) out.push(m[1].replace(/\*\*|__|`/g, ""));
    }
    return out;
  }

  function veChiTiet() {
    const box = document.getElementById("skDetail"), scrim = document.getElementById("skScrim");
    if (!box) return;
    const s = _skState.skills.find(x => x.slug === _skState.open);
    if (!s) { box.hidden = true; box.innerHTML = ""; if (scrim) scrim.hidden = true; return; }
    box.hidden = false; if (scrim) scrim.hidden = false;
    const on = s.enabled !== false;
    const desc = String(s.description || "").trim();
    const len = _doDai(desc), chu = [...desc];
    const giu = chu.slice(0, SKILL_DESC_MAX).join(""), cat = chu.slice(SKILL_DESC_MAX).join("");
    const used = s.use_count > 0
      ? t("studio.used", { n: s.use_count }) + (s.last_used_at ? ", " + t("studio.last_used") + " " + new Date(s.last_used_at * 1000).toLocaleDateString(LOC()) : "")
      : t("studio.sk_no_usage");
    const duongDan = (s.source === ".agents" ? ".agents/skills/" : "skills/") + s.slug + "/SKILL.md";
    box.innerHTML = `
      <div class="sk3-d-head"><div><h4>${esc(s.name)}</h4><div class="sk3-d-sub">${esc(nhomCua(s))} · ${esc(s.system ? t("studio.sk_system_lbl") : t("studio.sk_by_you"))}</div></div>
        <button type="button" class="sk3-x" aria-label="${esc(t("studio.sk_close"))}">${ic("x")}</button></div>
      <div class="sk3-d-state"><span>${esc(on ? t("studio.sk_state_on") : t("studio.sk_state_off"))}</span>
        <button type="button" class="sk3-sw" role="switch" aria-checked="${on}" aria-label="${esc(t("studio.sk_sw_aria", { ten: s.name }))}"><span class="sk3-tr"><span class="sk3-kn"></span></span></button></div>
      <section class="sk3-d-sec"><h5><span>${esc(t("studio.sk_desc_h"))}</span><span class="sk3-n${len > SKILL_DESC_MAX ? " over" : ""}">${esc(t("studio.sk_chars", { n: len, max: SKILL_DESC_MAX }))}</span></h5>
        <p>${esc(giu)}${cat ? `<span class="sk3-cut">${esc(cat)}</span>` : ""}</p>
        ${cat ? `<p class="sk3-note">${esc(t("studio.sk_cut_note", { max: SKILL_DESC_MAX }))}</p>` : ""}</section>
      <section class="sk3-d-sec" id="skWhen" hidden><h5>${esc(t("studio.sk_when_h"))}</h5><ul></ul></section>
      <section class="sk3-d-sec"><h5>${esc(t("studio.sk_activity_h"))}</h5><p>${esc(used)}</p>
        <p class="sk3-path">${esc(t("studio.sk_file"))}: <code>${esc(duongDan)}</code></p></section>
      <details class="sk3-full"><summary>${esc(t("studio.sk_full"))}</summary><div class="sk3-md" id="skMd">${esc(t("common.loading"))}</div></details>
      <div class="sk3-d-act"><button type="button" class="pri" id="skDEdit">${ic("pencil")} ${esc(t("common.edit"))}</button>${s.system
        ? `<p class="sk3-sysnote">${esc(t("studio.sk_sys_note"))}</p>`
        : `<button type="button" id="skDExp" title="${esc(t("studio.export_title"))}">${ic("download")} ${esc(t("studio.sk_export_one"))}</button><button type="button" class="del" id="skDDel">${ic("trash-2")} ${esc(t("common.delete"))}</button>`}</div>`;
    box.querySelector(".sk3-x").onclick = dongChiTiet;
    const sw = box.querySelector(".sk3-sw");
    sw.onclick = () => { sw.disabled = true; toggleSkill(s, !on); };
    box.querySelector("#skDEdit").onclick = () => openSkillForm(s.slug);
    const exp = box.querySelector("#skDExp"); if (exp) exp.onclick = () => exportItem("skill", s.slug);
    const del = box.querySelector("#skDDel"); if (del) del.onclick = () => deleteSkill(s.slug, s.name);
    napThanSkill(s.slug);
  }

  // Thân SKILL.md cho mục "Dùng khi nào" + "Xem toàn bộ": tải một lần mỗi skill rồi nhớ lại.
  async function napThanSkill(slug) {
    let body = _skState.bodies[slug];
    if (body == null) {
      const r = await api(`/skills/get?slug=${encodeURIComponent(slug)}&brain=${encodeURIComponent(brain())}`);
      body = (r && typeof r.body === "string") ? r.body : "";
      _skState.bodies[slug] = body;
    }
    if (_skState.open !== slug) return;   // người dùng đã bấm sang skill khác trong lúc chờ
    const when = phanDungKhiNao(body), sec = document.getElementById("skWhen");
    if (sec && when.length) {
      sec.querySelector("ul").innerHTML = when.map(w => `<li>${esc(w)}</li>`).join("");
      sec.hidden = false;
    }
    const md = document.getElementById("skMd");
    if (md) md.innerHTML = body.trim()
      ? (window.mdToHtml ? window.mdToHtml(body, null) : `<pre>${esc(body)}</pre>`)
      : esc(t("studio.sk_empty_body"));
  }

  if (!window._skEscGan) {
    window._skEscGan = true;
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && _skState.open && document.getElementById("skDetail")) dongChiTiet();
    });
  }

  // ---- Form tạo / sửa ----
  async function openSkillForm(slug) {
    const panel = document.getElementById("panel-skills");
    let sk = { slug: "", name: "", group: "Chung", description: "", body: "" };
    if (slug) { try { sk = await api(`/skills/get?slug=${encodeURIComponent(slug)}&brain=${encodeURIComponent(brain())}`); } catch (e) {} }
    // Nhóm trong file có thể là bản "trùng tên" (vd "ai"): chọn sẵn tên chuẩn đang hiện ở cột
    // nhóm, lưu lại là file được sửa luôn.
    const nhoms = _nhomDangCo();
    const khoa = _khoaNhom(sk.group || NHOM_MD);
    const nhomChon = nhoms.find(g => _khoaNhom(g) === khoa) || "";
    const opts = nhoms.map(g => `<option value="${esc(g)}"${g === nhomChon ? " selected" : ""}>${esc(g)}</option>`).join("")
      + `<option value="__new__"${nhomChon ? "" : " selected"}>${esc(t("studio.group_new"))}</option>`;
    panel.innerHTML = `<div class="panel-bar"><h3>${esc(slug ? t("studio.sk_edit") : t("studio.sk_new"))}</h3></div>
      <div class="sk3-form">
        <div class="fld"><label for="skName">${esc(t("studio.sk_name"))}</label><input id="skName" class="js-input" value="${esc(sk.name)}" placeholder="${esc(t("studio.sk_name_ph"))}"></div>
        <div class="fld"><label for="skGroupSel">${esc(t("studio.groups"))}</label>
          <select id="skGroupSel" class="js-input">${opts}</select>
          <input id="skGroupNew" class="js-input" placeholder="${esc(t("studio.sk_group_ph"))}" value="${esc(nhomChon ? "" : (sk.group || ""))}"${nhomChon ? " hidden" : ""}>
          <span class="hint">${esc(t("studio.sk_group_hint"))}</span></div>
        <div class="fld"><div class="row"><label for="skDesc">${esc(t("studio.sk_desc_lbl"))}</label><span class="hint" id="skDescN"></span></div>
          <textarea id="skDesc" class="js-input" style="min-height:76px">${esc(sk.description || "")}</textarea>
          <span class="hint" id="skDescHint">${esc(t("studio.sk_desc_hint", { max: SKILL_DESC_MAX }))}</span></div>
        <div class="fld"><div class="row"><span class="lbl">${esc(t("studio.sk_body_lbl"))}</span>
            <div class="tabs" role="tablist"><button type="button" role="tab" class="sel" aria-selected="true" data-tab="edit">${esc(t("studio.sk_tab_edit"))}</button><button type="button" role="tab" aria-selected="false" data-tab="preview">${esc(t("studio.sk_tab_preview"))}</button></div></div>
          <textarea id="skBody" class="js-input" aria-label="${esc(t("studio.sk_body_lbl"))}" style="min-height:260px;font-family:ui-monospace,monospace">${esc(sk.body || "")}</textarea>
          <div class="prev" id="skPrev" hidden></div></div>
        <div class="err" id="skErr" role="alert" hidden></div>
        <div class="acts"><button class="s-btn" id="skSave">${ic("save")} ${esc(t("common.save"))}</button><button class="s-btn-ghost" id="skCancel">${esc(t("common.cancel"))}</button></div>
      </div>`;
    const $ = (sel) => panel.querySelector(sel);
    const gSel = $("#skGroupSel"), gNew = $("#skGroupNew"), desc = $("#skDesc"), err = $("#skErr");
    gSel.onchange = () => { gNew.hidden = gSel.value !== "__new__"; if (!gNew.hidden) gNew.focus(); };
    const demMoTa = () => {
      const n = _doDai(desc.value), over = n > SKILL_DESC_MAX;
      $("#skDescN").textContent = t("studio.sk_chars", { n, max: SKILL_DESC_MAX });
      $("#skDescN").classList.toggle("over", over);
      desc.classList.toggle("over", over);
      const h = $("#skDescHint");
      h.textContent = over ? t("studio.sk_desc_over", { n, max: SKILL_DESC_MAX }) : t("studio.sk_desc_hint", { max: SKILL_DESC_MAX });
      h.classList.toggle("over", over);
      return over;
    };
    desc.oninput = demMoTa; demMoTa();
    panel.querySelectorAll(".tabs [data-tab]").forEach(b => {
      b.onclick = () => {
        const xem = b.dataset.tab === "preview";
        panel.querySelectorAll(".tabs [data-tab]").forEach(x => { x.classList.toggle("sel", x === b); x.setAttribute("aria-selected", String(x === b)); });
        const body = $("#skBody").value;
        $("#skPrev").innerHTML = xem ? (window.mdToHtml ? window.mdToHtml(body, null) : `<pre>${esc(body)}</pre>`) : "";
        $("#skPrev").hidden = !xem; $("#skBody").hidden = xem;
      };
    });
    $("#skCancel").onclick = () => loadSkills();
    $("#skSave").onclick = async () => {
      const name = $("#skName").value.trim();
      const baoLoi = (m) => { err.textContent = m; err.hidden = false; };
      err.hidden = true;
      if (!name) { baoLoi(t("studio.need_sk_name")); $("#skName").focus(); return; }
      if (demMoTa()) { desc.focus(); return; }   // câu báo đã đỏ ngay dưới ô mô tả, không lặp lại
      const group = (gSel.value === "__new__" ? gNew.value.trim() : gSel.value) || NHOM_MD;
      const b = $("#skSave"); b.disabled = true; b.textContent = t("settings.saving");
      // Trước 0.75.0 lỗi từ server (vd mô tả quá trần) bị nuốt: form đóng như đã lưu xong.
      const r = await api("/skills", { method: "POST", body: fd({
        name, group, description: desc.value, body: $("#skBody").value,
        slug: sk.slug || "", brain: brain() }) });
      if (!r || r.error || r.ok === false) {
        baoLoi(t("studio.sk_save_err") + " " + ((r && r.error) || t("studio.sk_net_err")));
        b.disabled = false; b.innerHTML = `${ic("save")} ${esc(t("common.save"))}`;
        return;
      }
      quenForm();
      if (sk.slug) delete _skState.bodies[sk.slug];
      loadSkills();
    };
  }

  async function deleteSkill(slug, name) {
    if (!confirm(t("studio.del_sk", { ten: name, slug }))) return;
    await api("/skills/delete", { method: "POST", body: fd({ slug, brain: brain() }) });
    quenForm();
    if (_skState.open === slug) _skState.open = "";
    loadSkills();
  }
})();
