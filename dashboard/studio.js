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
  window.openStudio = (tab) => { if (window.Alpine) Alpine.store("nav").go(tab || "workflows"); };
  window.JavisStudio = {
    workflows: loadWorkflows, agents: loadAgents, skills: loadSkills,
  };
  const _studioBtn = document.getElementById("studioOpenBtn");
  if (_studioBtn) _studioBtn.addEventListener("click", () => window.openStudio("workflows"));

  const refreshStats = () => { if (window.loadBrainStats) window.loadBrainStats(); };

  function switchTab(tab) {
    document.querySelectorAll(".stab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
    ["workflows", "agents", "skills"].forEach(t => document.getElementById("panel-" + t).hidden = (t !== tab));
    if (tab === "workflows") loadWorkflows();
    else if (tab === "agents") loadAgents();
    else loadSkills();
  }

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

  async function loadWorkflows() {
    const panel = document.getElementById("panel-workflows");
    panel.innerHTML = `<div class="panel-bar"><h3>Workflows</h3><div class="pb-actions"><button class="s-btn-ghost" id="wfSelAll" title="${esc(t("studio.selall_title"))}">${esc(t("studio.selall"))}</button><button class="s-btn-ghost" id="wfDl" disabled title="${esc(t("studio.dl_title"))}">${esc(t("studio.dl_sel"))}</button><button class="s-btn-ghost" id="wfImport">${esc(t("studio.import"))}</button><button class="s-btn-ghost" id="seedBtn">${esc(t("studio.seed"))}</button><button class="s-btn" id="newWf">+ Workflow</button></div></div><div class="wf-list" id="wfCards">${esc(t("common.loading"))}</div>`;
    document.getElementById("newWf").onclick = () => editWorkflow(null);
    document.getElementById("wfImport").onclick = () => importItems(loadWorkflows);
    document.getElementById("seedBtn").onclick = async () => { await api("/studio/seed", { method: "POST", body: fd({ brain: brain() }) }); loadWorkflows(); };
    document.getElementById("wfDl").onclick = () => taiDaChon("workflow");
    const d = await api(`/workflows?brain=${encodeURIComponent(brain())}`);
    const wfs = d.workflows || [];
    _sel.workflow.clear();   // nạp lại trang là làm mới lựa chọn (danh sách có thể đã đổi)
    document.getElementById("wfSelAll").onclick = () => chonTatCa("workflow", "wfDl", "wf-sel", wfs.map(w => w.slug));
    refreshStats();
    const cards = document.getElementById("wfCards");
    if (!wfs.length) { cards.innerHTML = `<div class="empty">${esc(t("studio.wf_empty"))}</div>`; return; }
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
  async function editWorkflow(w) {
    const ad = await api(`/agents?brain=${encodeURIComponent(brain())}`);
    agentsCache = ad.agents || [];
    if (!agentsCache.length) { alert(t("studio.no_agents")); return; }
    const box = document.getElementById("editorBox");
    const steps = w ? JSON.parse(JSON.stringify(w.steps || [])) : [{ agent: agentsCache[0].slug, task: "" }];
    const opts = (sel) => agentsCache.map(a => `<option value="${a.slug}" ${a.slug === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
    const optsV = (sel) => `<option value="">${esc(t("studio.no_verify"))}</option>` + agentsCache.map(a => `<option value="${a.slug}" ${a.slug === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
    const agentName = (slug) => { const a = agentsCache.find(x => x.slug === slug); return a ? a.name : (slug || "?"); };
    // Bước gập lại để thấy toàn cảnh; bấm vào bước nào thì mở bước đó ra sửa. Workflow mới
    // chỉ có 1 bước nên mở sẵn. Các ô input VẪN nằm trong DOM khi gập (chỉ ẩn bằng CSS) -
    // captureSteps() đọc value của chúng, render kiểu chỉ-vẽ-bước-đang-mở sẽ làm nó vỡ.
    let openIdx = w ? null : 0;
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
        <label>${esc(t("studio.name"))}</label><input id="wfName" value="${esc(w ? w.name : "")}">
        <label>${esc(t("studio.desc"))}</label><input id="wfDesc" value="${esc(w ? w.description : "")}">
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
      box.querySelector("#saveWf").onclick = async () => {
        const name = box.querySelector("#wfName").value.trim(); if (!name) return alert(t("studio.need_name"));
        captureSteps();
        await api("/workflows", { method: "POST", body: fd({ name, description: box.querySelector("#wfDesc").value, steps: JSON.stringify(steps), status: w ? w.status : "active", slug: w ? w.slug : "", brain: brain() }) });
        editor.classList.remove("open"); loadWorkflows();
      };
    }
    function captureSteps() {
      box.querySelectorAll(".step-row").forEach((r, i) => {
        const va = r.querySelector(".st-verify-agent").value;
        steps[i] = { agent: r.querySelector(".st-agent").value, task: r.querySelector(".st-task").value };
        if (va) { steps[i].verify_agent = va; steps[i].max_retries = parseInt(r.querySelector(".st-retries").value, 10) || 0; }
      });
    }
    render(); editor.classList.add("open");
  }

  // ===== Agents =====
  async function loadAgents() {
    const panel = document.getElementById("panel-agents");
    panel.innerHTML = `<div class="panel-bar"><h3>Agents</h3><div class="pb-actions"><button class="s-btn-ghost" id="agSelAll" title="${esc(t("studio.selall_title"))}">${esc(t("studio.selall"))}</button><button class="s-btn-ghost" id="agDl" disabled title="${esc(t("studio.dl_title"))}">${esc(t("studio.dl_sel"))}</button><button class="s-btn-ghost" id="agImport">${esc(t("studio.import"))}</button><button class="s-btn" id="newAgent">+ Agent</button></div></div><div class="cards" id="agCards">${esc(t("common.loading"))}</div>`;
    document.getElementById("newAgent").onclick = () => editAgent(null);
    document.getElementById("agImport").onclick = () => importItems(loadAgents);
    document.getElementById("agDl").onclick = () => taiDaChon("agent");
    const d = await api(`/agents?brain=${encodeURIComponent(brain())}`);
    _sel.agent.clear();
    document.getElementById("agSelAll").onclick = () =>
      chonTatCa("agent", "agDl", "ag-sel", (d.agents || []).map(a => a.slug));
    refreshStats();
    const cards = document.getElementById("agCards");
    if (!(d.agents || []).length) { cards.innerHTML = `<div class="empty">${esc(t("studio.ag_empty"))}</div>`; return; }
    cards.innerHTML = "";
    d.agents.forEach(a => {
      const div = document.createElement("div"); div.className = "ag-card";
      div.innerHTML = `<div class="ag-name"><input type="checkbox" class="ag-sel" data-slug="${esc(a.slug)}" title="${esc(t("studio.sel_one"))}"> ${ic("bot")} ${esc(a.name)} <span class="ag-model">${esc(a.model || "")}</span></div><div class="ag-role">${esc(a.role)}</div><div class="ag-skills">${(a.skills || []).map(s => `<span class="chip-skill">${esc(s)}</span>`).join("") || `<span class="dim">${esc(t("studio.no_skills"))}</span>`}</div><div class="wf-actions"><button class="s-btn-ghost edit">${esc(t("common.edit"))}</button><button class="s-btn-ghost exp" title="${esc(t("studio.export_title"))}">${esc(t("studio.export"))}</button><button class="s-btn-ghost del">${esc(t("common.delete"))}</button></div>`;
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

  async function editAgent(a) {
    const [sd, st] = await Promise.all([
      api(`/skills?brain=${encodeURIComponent(brain())}`),
      api("/settings"),
    ]);
    const skills = sd.skills || [];
    const uniq = (xs) => [...new Set((xs || []).filter(Boolean))];
    // CÙNG nguồn với trình chọn model chính (/settings → model.providers), nên thêm nhà mới
    // ở trang Models là ô này có ngay. Lọc `agent_ok`: server chỉ dựng nổi engine agent cho
    // một số nhà (xem AGENT_PROVIDERS), bày thêm là hứa suông. Lọc `configured`: chưa cắm
    // key thì chọn vào cũng không chạy.
    const provs = ((st.model || {}).providers || []).filter(p => p.agent_ok && p.configured);
    // Danh sách LIVE cho nhà có catalog rỗng/đổi liên tục (Codex, Gemini CLI, Groq...).
    // Hỏng một nhà thì chỉ nhà đó rơi về catalog, không kéo cả ô chọn chết theo.
    const live = await Promise.all(provs.map(p =>
      api(`/provider/models?provider=${encodeURIComponent(p.id)}` + (p.id === "openai-oauth" ? "&refresh=1" : ""))
        .then(d => uniq(d.models)).catch(() => [])));
    const nhom = provs.map((p, i) => ({ id: p.id, label: p.label, models: uniq(live[i].concat(p.models || [])) }))
                      .filter(g => g.models.length);
    const val = (pid, m) => pid + MODEL_SEP + m;
    // Agent đang lưu một model không còn trong danh sách nào (nhà đã ngắt key, model bị gỡ):
    // vẫn bày ra để mở form lên KHÔNG âm thầm đổi model của agent thành "Mặc định".
    const dangCo = a && a.model && !nhom.some(g => (!a.model_provider || g.id === a.model_provider) && g.models.includes(a.model));
    const currentOnly = dangCo
      ? `<optgroup label="${esc(t("studio.model_saved"))}"><option value="${esc(val(a.model_provider || "", a.model))}">${esc(a.model)} ${esc(t("studio.saved_suffix"))}</option></optgroup>` : "";
    const modelOptions = (g) =>
      `<optgroup label="${esc(g.label)}">${g.models.map(m => `<option value="${esc(val(g.id, m))}">${esc(m)}</option>`).join("")}</optgroup>`;
    const box = document.getElementById("editorBox");
    box.innerHTML = `<h3>${esc(a ? t("studio.edit") : t("studio.create"))} Agent</h3>
      <label>${esc(t("studio.name"))}</label><input id="agName" value="${esc(a ? a.name : "")}">
      <label>${esc(t("studio.role"))}</label><input id="agRole" value="${esc(a ? a.role : "")}">
      <label>${esc(t("studio.sys_prompt"))}</label><textarea id="agPrompt" rows="4">${esc(a ? (a.prompt || "") : "")}</textarea>
      <label>Skills</label>
      ${skills.length ? `<div class="sp-box">
        <div class="sp-bar"><input id="spSearch" placeholder="${esc(t("studio.sp_search_ph"))}">
          <span class="sp-count" id="spCount"></span>
          <button type="button" class="s-btn-ghost sp-clear" id="spClear">${esc(t("studio.sp_clear"))}</button></div>
        <div class="sp-groups" id="skillPick"></div>
      </div>` : `<div class="skill-pick"><span class="dim">${esc(t("studio.sp_none"))}</span></div>`}
      <label>Model</label><select id="agModel">
        <option value="">${esc(t("studio.model_default"))}</option>
        ${currentOnly}
        ${nhom.map(modelOptions).join("")}
      </select>
      <div class="dim" style="font-size:12px;margin-top:4px">${esc(nhom.length
        ? t("studio.model_hint")
        : t("studio.model_none"))}</div>
      <div class="editor-actions"><button class="s-btn-ghost" id="cancelEd">${esc(t("common.cancel"))}</button><button class="s-btn" id="saveAg">${esc(t("common.save"))}</button></div>`;
    if (a && a.model) {
      const sel = box.querySelector("#agModel");
      sel.value = val(a.model_provider || "", a.model);
      // Agent CŨ lưu mỗi tên model (chưa có trường nhà): dò dòng đầu tiên trùng tên để form
      // mở lên vẫn hiện đúng model đang chạy, thay vì nhảy về "Mặc định" rồi bấm Lưu là mất.
      if (!sel.value) {
        const hit = [...sel.options].find(o => o.value.split(MODEL_SEP).slice(1).join(MODEL_SEP) === a.model);
        if (hit) sel.value = hit.value;
      }
    }
    // Trạng thái chọn giữ trong Set, DOM chỉ là HÌNH CHIẾU của nó. Đây là chỗ dễ hỏng nhất của
    // khung có bộ lọc: vẽ lại theo bộ lọc rồi lúc lưu mới đi đọc DOM thì mọi skill đang bị lọc
    // ra khỏi màn hình sẽ mất tick, im lặng, và người dùng chỉ phát hiện sau khi agent chạy sai.
    const chosen = new Set(a ? (a.skills || []) : []);
    renderSkillPick(box, skills, chosen);
    box.querySelector("#cancelEd").onclick = () => editor.classList.remove("open");
    box.querySelector("#saveAg").onclick = async () => {
      const name = box.querySelector("#agName").value.trim(); if (!name) return alert(t("studio.need_name"));
      const sk = [...chosen].join(",");
      const raw = box.querySelector("#agModel").value;
      const cut = raw.indexOf(MODEL_SEP);
      const mProv = cut === -1 ? "" : raw.slice(0, cut);
      const mName = cut === -1 ? raw : raw.slice(cut + MODEL_SEP.length);
      await api("/agents", { method: "POST", body: fd({ name, role: box.querySelector("#agRole").value, prompt: box.querySelector("#agPrompt").value, skills: sk, model: mName, model_provider: mProv, slug: a ? a.slug : "", brain: brain() }) });
      editor.classList.remove("open"); loadAgents();
    };
    editor.classList.add("open");
  }

  // ===== Khung chọn skill trong màn sửa Agent =====
  // Brain thật đang có 55+ skill, nên danh sách checkbox phẳng là dò bằng mắt qua cả trang.
  // Ở đây: ô tìm + gom nhóm theo field `group` sẵn có của skill (đúng nhóm mà trang Skills
  // dùng, không đẻ cách phân loại thứ hai), mỗi nhóm sổ ra thu vào được.
  function _spNoAccent(s) {
    s = String(s == null ? "" : s);
    try { s = s.normalize("NFD").replace(/[̀-ͯ]/g, ""); } catch (e) {}
    return s.replace(/[đĐ]/g, "d").toLowerCase();
  }

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
      const hop = (s) => !nq || _spNoAccent(`${s.name} ${s.slug} ${s.group || ""} ${s.description || ""}`).includes(nq);
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
  const _skState = { cat: "ALL", q: "", skills: [] };
  function _injectSkillCss() {
    if (window._skCss) return; window._skCss = true;
    const css = `
    .sk2{display:flex;gap:16px;align-items:flex-start}
    .sk2-selwrap{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:var(--text3);cursor:pointer;white-space:nowrap}
    .sk2-side{width:210px;flex:none;border:1px solid var(--hairline);border-radius:10px;padding:8px;max-height:72vh;overflow:auto}
    .sk2-side .sec{font-size:12px;letter-spacing:.08em;color:var(--text3);padding:8px 10px 4px;text-transform:uppercase}
    .sk2-side .cat{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 10px;border-radius:7px;cursor:pointer;font-size:15px;color:var(--text)}
    .sk2-side .cat:hover{background:rgba(120,180,255,.08)} .sk2-side .cat.sel{background:var(--info-wash);color:var(--info-ink)}
    .sk2-side .cat .n{color:var(--text3);font-size:13px;flex:none}
    .sk2-main{flex:1;min-width:0}
    .sk2-bar{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
    .sk2-bar h4{margin:0;font-size:17px;color:var(--text)} .sk2-bar .cnt{color:var(--text3);font-size:14px}
    .sk2-bar input{flex:1;min-width:160px;max-width:340px;padding:7px 11px;border-radius:8px;border:1px solid var(--hairline);background:var(--field-bg);color:var(--text);font-size:15px;outline:none}
    .sk2-list{display:flex;flex-direction:column;gap:8px}
    .sk2-card{display:flex;gap:12px;align-items:flex-start;padding:11px 13px;border:1px solid var(--hairline);border-radius:10px}
    .sk2-card:hover{border-color:var(--info-line);background:var(--info-wash)}
    .sk2-card.off{opacity:.5} .sk2-tog{flex:none;margin-top:3px;width:16px;height:16px;cursor:pointer;accent-color:var(--accent)}
    .sk2-info{flex:1;min-width:0} .sk2-info .nm{color:var(--text);font-size:15px;font-weight:600}
    .sk2-info .ds{color:var(--text3);font-size:14px;margin-top:3px;line-height:1.45}
    .sk2-info .gp{color:var(--text3);font-size:13px;margin-top:4px}
    .sk2-act{display:flex;gap:5px;opacity:0;transition:.15s;flex:none} .sk2-card:hover .sk2-act{opacity:1}
    .sk2-act button{background:var(--surface-2);border:1px solid var(--hairline);color:var(--text2);border-radius:6px;cursor:pointer;font-size:13px;padding:3px 9px} .sk2-act button:hover{color:var(--text-hi);border-color:rgba(120,180,255,.5)}
    .sk2-act button.danger:hover{color:var(--red);border-color:rgba(255,120,120,.5)}
    .sysb{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:20px;font-size:11px;font-weight:600;letter-spacing:.02em;color:var(--link-ink);background:var(--info-wash);border:1px solid var(--info-line);vertical-align:2px}
    .sk-usage{font-size:11px;color:var(--text3);margin-left:8px}
    .sk-stale{opacity:.75;font-style:italic;cursor:help}
    /* ===== Mobile (<=860px) ===== xep DOC: nhom thanh dai chip cuon ngang o tren, danh sach
       skill full-width ben duoi (truoc day cot nhom 210px bop cot skill con ~150px -> chu vo
       tung tu). Nut thao tac luon hien (truoc day opacity:0 + chi hien khi :hover -> tren dien
       thoai khong co hover nen Sua/Xuat/Xoa khong bao gio bam duoc). */
    @media (max-width:860px){
      .sk2{flex-direction:column;gap:12px}
      .sk2-side{width:auto;max-height:none;display:flex;flex-direction:row;gap:6px;padding:6px;
        overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch}
      .sk2-side::-webkit-scrollbar{height:0}
      .sk2-side .sec{display:none}
      .sk2-side .cat{flex:none;padding:8px 13px;border:1px solid var(--hairline);
        border-radius:999px;white-space:nowrap}
      .sk2-side .cat .n{padding:1px 6px;border-radius:9px;background:var(--surface-3)}
      .sk2-side .cat.sel{border-color:var(--info-line)}
      .sk2-bar input{max-width:none;font-size:16px}   /* 16px: chan iOS tu zoom khi focus */
      .sk2-tog{width:20px;height:20px;margin-top:2px}  /* vung cham lon hon */
      .sk2-card{flex-wrap:wrap;padding:12px 13px}
      .sk2-info .nm{font-size:16px}
      .sk2-act{flex:1 1 100%;opacity:1;margin-top:11px;padding-top:11px;gap:8px;
        border-top:1px solid var(--surface-2);justify-content:flex-end}
      .sk2-act button{padding:7px 14px;font-size:14px}
    }`;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  }

  async function loadSkills() {
    _injectSkillCss();
    const panel = document.getElementById("panel-skills");
    panel.innerHTML = `<div class="empty">${esc(t("common.loading"))}</div>`;
    let d; try { d = await api(`/skills?brain=${encodeURIComponent(brain())}`); } catch (e) { panel.innerHTML = `<div class="empty">${esc(t("studio.sk_load_err"))}</div>`; return; }
    refreshStats();
    _skState.skills = d.skills || [];
    _sel.skill.clear();   // nạp lại là làm mới lựa chọn (danh sách có thể đã đổi)
    renderSkillUI();
  }

  function _skFiltered() {
    const q = _skState.q.toLowerCase();
    let list = _skState.skills;
    if (_skState.cat !== "ALL") list = list.filter(s => (s.group || "Chung") === _skState.cat);
    if (q) list = list.filter(s => (s.name || "").toLowerCase().includes(q) || (s.description || "").toLowerCase().includes(q) || (s.slug || "").toLowerCase().includes(q));
    return list;
  }

  function renderSkillUI() {
    const panel = document.getElementById("panel-skills");
    const all = _skState.skills;
    const groups = {};
    all.forEach(s => { const g = s.group || "Chung"; groups[g] = (groups[g] || 0) + 1; });
    const enabledN = all.filter(s => s.enabled !== false).length;
    const cats = ["ALL"].concat(Object.keys(groups).sort());
    const catHtml = cats.map(c => `<div class="cat ${_skState.cat === c ? "sel" : ""}" data-cat="${esc(c)}"><span>${c === "ALL" ? esc(t("studio.all")) : esc(c)}</span><span class="n">${c === "ALL" ? all.length : groups[c]}</span></div>`).join("");
    panel.innerHTML = `
      <div class="panel-bar"><h3>Skills <span class="dim">${enabledN}/${all.length} ${esc(t("studio.on_count"))} · ${esc(t("studio.source"))} <code>skills/</code></span></h3>
        <div class="pb-actions"><button class="s-btn-ghost" id="skSelAll" title="${esc(t("studio.selall_sk_title"))}">${esc(t("studio.selall"))}</button><button class="s-btn-ghost" id="skDl" disabled title="${esc(t("studio.dl_title"))}">${esc(t("studio.dl_sel"))}</button><button class="s-btn-ghost" id="skImport">${esc(t("studio.import"))}</button><button class="s-btn" id="skNew">+ Skill</button></div></div>
      ${all.length ? `<div class="sk2">
        <div class="sk2-side"><div class="sec">${esc(t("studio.groups"))}</div>${catHtml}</div>
        <div class="sk2-main">
          <div class="sk2-bar"><h4>${_skState.cat === "ALL" ? esc(t("studio.all")) : esc(_skState.cat)}</h4><span class="cnt"></span>
            <input id="skSearch" placeholder="${esc(t("studio.sk_search_ph"))}" value="${esc(_skState.q)}"></div>
          <div class="sk2-list" id="skList"></div>
        </div></div>`
      : `<div class="empty">${esc(t("studio.sk_empty"))}</div>`}`;
    document.getElementById("skNew").onclick = () => openSkillForm(null);
    document.getElementById("skImport").onclick = () => importItems(loadSkills);
    document.getElementById("skDl").onclick = () => taiDaChon("skill");
    // Chọn tất cả = toàn bộ danh sách ĐANG HIỆN (đúng nhóm + đúng ô tìm), trừ skill hệ
    // thống - chúng không xuất được (server bỏ qua) vì brain nào cũng có sẵn theo app.
    document.getElementById("skSelAll").onclick = () =>
      chonTatCa("skill", "skDl", "sk2-sel", _skFiltered().filter(s => !s.system).map(s => s.slug));
    capNhatNutTai("skill", "skDl");
    if (!all.length) return;
    panel.querySelectorAll(".sk2-side .cat").forEach(c => c.onclick = () => { _skState.cat = c.dataset.cat; renderSkillUI(); });
    const search = document.getElementById("skSearch");
    search.oninput = () => { _skState.q = search.value; renderSkillList(); };
    renderSkillList();
  }

  function renderSkillList() {
    const box = document.getElementById("skList"); if (!box) return;
    const list = _skFiltered();
    const cntEl = document.querySelector(".sk2-bar .cnt"); if (cntEl) cntEl.textContent = list.length + " skill";
    if (!list.length) { box.innerHTML = `<div class="empty">${esc(t("studio.sk_no_match"))}</div>`; return; }
    box.innerHTML = "";
    list.forEach(s => {
      const on = s.enabled !== false;
      const div = document.createElement("div"); div.className = "sk2-card" + (on ? "" : " off");
      const sysBadge = s.system ? ` <span class="sysb" title="${esc(t("studio.sys_title"))}">${esc(t("studio.sys"))}</span>` : "";
      // Telemetry: use_count là tín hiệu DƯƠNG một chiều. Skill nạp native qua .claude/skills
      // không đi qua bộ đếm, nên "chưa thấy dùng" là tham khảo, KHÔNG phải phán quyết.
      let usageHtml = "";
      if (s.use_count > 0) {
        const when = s.last_used_at ? new Date(s.last_used_at * 1000).toLocaleDateString(LOC()) : "";
        usageHtml = ` · <span class="sk-usage">${esc(t("studio.used", { n: s.use_count }))}${when ? ", " + esc(t("studio.last_used")) + " " + when : ""}</span>`;
      } else if (s.stale) {
        usageHtml = ` · <span class="sk-usage sk-stale" title="${esc(t("studio.unused_title"))}">${esc(t("studio.unused"))}</span>`;
      }
      div.innerHTML = `<input type="checkbox" class="sk2-tog" ${on ? "checked" : ""} title="${esc(on ? t("studio.tog_on") : t("studio.tog_off"))}">
        <div class="sk2-info"><div class="nm">${ic("puzzle")} ${esc(s.name)}${sysBadge}</div><div class="ds">${esc(s.description || "")}</div><div class="gp">${ic("folder-open")} ${esc(s.group || "Chung")} · ${esc(s.slug)}${s.source === ".agents" ? " · .agents" : ""}${usageHtml}</div></div>
        <div class="sk2-act">${s.system ? "" : `<label class="sk2-selwrap" title="${esc(t("studio.sel_one"))}"><input type="checkbox" class="sk2-sel" data-slug="${esc(s.slug)}"> ${esc(t("studio.pick"))}</label>`}<button class="edit">${esc(t("common.edit"))}</button>${s.system ? "" : `<button class="exp" title="${esc(t("studio.export_title"))}">${esc(t("studio.export"))}</button><button class="del danger">${esc(t("common.delete"))}</button>`}</div>`;
      div.querySelector(".sk2-tog").onchange = (e) => toggleSkill(s, e.target.checked);
      const selBox = div.querySelector(".sk2-sel");
      if (selBox) noiSel("skill", "skDl", selBox, s.slug);
      div.querySelector(".edit").onclick = () => openSkillForm(s.slug);
      const expBtn = div.querySelector(".exp");
      if (expBtn) expBtn.onclick = () => exportItem("skill", s.slug);
      const delBtn = div.querySelector(".del");
      if (delBtn) delBtn.onclick = () => deleteSkill(s.slug, s.name);
      box.appendChild(div);
    });
  }

  async function toggleSkill(s, enabled) {
    const r = await api("/skills/toggle", { method: "POST", body: fd({ slug: s.slug, enabled: enabled ? "1" : "0", brain: brain() }) });
    if (r && r.error) { alert(t("studio.toggle_err") + " " + r.error); }
    s.enabled = enabled;
    renderSkillUI(); refreshStats();
  }

  async function openSkillForm(slug) {
    const panel = document.getElementById("panel-skills");
    let sk = { slug: "", name: "", group: "Chung", description: "", body: "" };
    if (slug) { try { sk = await api(`/skills/get?slug=${encodeURIComponent(slug)}&brain=${encodeURIComponent(brain())}`); } catch (e) {} }
    const groupOpts = [...new Set(_skState.skills.map(s => s.group || "Chung"))].map(g => `<option value="${esc(g)}">`).join("");
    panel.innerHTML = `<div class="panel-bar"><h3>${esc(slug ? t("studio.sk_edit") : t("studio.sk_new"))}</h3></div>
      <div style="display:flex;flex-direction:column;gap:12px;max-width:660px">
        <div><label>${esc(t("studio.sk_name"))}</label><input id="skName" class="js-input" value="${esc(sk.name)}" placeholder="${esc(t("studio.sk_name_ph"))}"></div>
        <div><label>${esc(t("studio.groups"))}</label><input id="skGroup" class="js-input" list="skGroupList" value="${esc(sk.group || "Chung")}" placeholder="${esc(t("studio.sk_group_ph"))}">
          <datalist id="skGroupList">${groupOpts}</datalist></div>
        <div><label>${esc(t("studio.sk_desc"))}</label><textarea id="skDesc" class="js-input" style="min-height:60px">${esc(sk.description || "")}</textarea></div>
        <div><label>${esc(t("studio.sk_body"))}</label><textarea id="skBody" class="js-input" style="min-height:200px;font-family:ui-monospace,monospace">${esc(sk.body || "")}</textarea></div>
        <div style="display:flex;gap:10px"><button class="s-btn" id="skSave">${ic("save")} ${esc(t("common.save"))}</button><button class="s-btn-ghost" id="skCancel">${esc(t("common.cancel"))}</button></div>
      </div>`;
    panel.querySelector("#skCancel").onclick = () => loadSkills();
    panel.querySelector("#skSave").onclick = async () => {
      const name = panel.querySelector("#skName").value.trim();
      if (!name) { alert(t("studio.need_sk_name")); return; }
      const b = panel.querySelector("#skSave"); b.disabled = true; b.textContent = t("settings.saving");
      await api("/skills", { method: "POST", body: fd({
        name, group: panel.querySelector("#skGroup").value.trim() || "Chung",
        description: panel.querySelector("#skDesc").value, body: panel.querySelector("#skBody").value,
        slug: sk.slug || "", brain: brain() }) });
      loadSkills();
    };
  }

  async function deleteSkill(slug, name) {
    if (!confirm(t("studio.del_sk", { ten: name, slug }))) return;
    await api("/skills/delete", { method: "POST", body: fd({ slug, brain: brain() }) });
    loadSkills();
  }
})();
