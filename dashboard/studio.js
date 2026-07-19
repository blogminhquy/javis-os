// ============================================
// JAVIS OS - Studio: Agents / Skills / Workflows
// ============================================
(function () {
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
  const exportUrl = (kind, slug) => `/export?kind=${kind}&slug=${encodeURIComponent(slug)}&brain=${encodeURIComponent(brain())}&deps=1`;
  function exportItem(kind, slug) { window.open(exportUrl(kind, slug), "_blank"); }
  function importItems(reload) {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".zip,.md,.skill,application/zip";
    inp.onchange = async () => {
      if (!inp.files || !inp.files.length) return;
      const ow = confirm("Nếu đã có agent/skill/workflow TRÙNG TÊN thì GHI ĐÈ bằng bản mới?\n\nOK = ghi đè · Huỷ = giữ bản cũ (chỉ nhập cái chưa có).");
      const f = new FormData();
      f.append("file", inp.files[0]); f.append("brain", brain()); f.append("overwrite", ow ? "1" : "0");
      let r;
      try { r = await (await fetch("/import", { method: "POST", body: f })).json(); }
      catch (e) { alert("Lỗi tải lên: " + e.message); return; }
      if (r && r.error) { alert("Nhập thất bại: " + r.error); return; }
      const show = (a) => (a && a.length) ? a.join(", ") : "(không)";
      alert(`Nhập xong.\n• Đã nhập: ${show(r.imported)}\n• Bỏ qua (đã có): ${show(r.skipped)}`
        + ((r.errors && r.errors.length) ? `\n• Lỗi: ${r.errors.join("; ")}` : ""));
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
  const WF_VARS = { input: "đầu vào", prev: "kết quả bước trước" };
  function renderPipeline(steps) {
    return (steps || []).map((s, i) => {
      const task = (s.task || "").replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (m, v) => WF_VARS[v] || v);
      return `<div class="wf-pstep" data-i="${i}">
          <div class="wps-num">${String(i + 1).padStart(2, "0")}</div>
          ${task ? `<div class="wps-task" title="${esc(task)}">${esc(task)}</div>` : ''}
          <div class="wps-name">${esc(s.agent)}</div>
        </div>`;
    }).join('');
  }

  async function loadWorkflows() {
    const panel = document.getElementById("panel-workflows");
    panel.innerHTML = `<div class="panel-bar"><h3>Workflows</h3><div class="pb-actions"><button class="s-btn-ghost" id="wfImport">⤒ Nhập</button><button class="s-btn-ghost" id="seedBtn">Tạo mẫu</button><button class="s-btn" id="newWf">+ Workflow</button></div></div><div class="wf-list" id="wfCards">Đang tải...</div>`;
    document.getElementById("newWf").onclick = () => editWorkflow(null);
    document.getElementById("wfImport").onclick = () => importItems(loadWorkflows);
    document.getElementById("seedBtn").onclick = async () => { await api("/studio/seed", { method: "POST", body: fd({ brain: brain() }) }); loadWorkflows(); };
    const d = await api(`/workflows?brain=${encodeURIComponent(brain())}`);
    const wfs = d.workflows || [];
    refreshStats();
    const cards = document.getElementById("wfCards");
    if (!wfs.length) { cards.innerHTML = `<div class="empty">Chưa có workflow. Bấm <b>Tạo mẫu</b> để có ví dụ Research → Write, hoặc <b>+ Workflow</b>.</div>`; return; }
    cards.innerHTML = "";
    wfs.forEach(w => {
      const active = w.status === "active";
      const div = document.createElement("div");
      div.className = "wf-row" + (active ? "" : " archived");
      div.dataset.slug = w.slug;
      div.innerHTML = `
        <div class="wf-header">
          <div class="wf-name">${esc(w.name)}</div>
          <span class="wf-badge ${active ? "ready" : "off"}">${active ? "● Sẵn sàng" : "Lưu trữ"}</span>
          <span class="wf-count">${(w.steps || []).length} bước</span>
          <div class="wf-spacer"></div>
          <div class="wf-actions">
            <button class="s-btn run" ${active ? "" : "disabled"}>▶ Chạy</button>
            <button class="s-btn-ghost edit">Sửa</button>
            <button class="s-btn-ghost archive">${active ? "Lưu trữ" : "Kích hoạt"}</button>
            <button class="s-btn-ghost exp" title="Xuất gói .zip (kèm agent + skill phụ thuộc) để chia sẻ">⤓ Xuất</button>
            <button class="s-btn-ghost del">Xoá</button>
          </div>
        </div>
        ${w.description ? `<div class="wf-desc">${esc(w.description)}</div>` : ''}
        <div class="wf-pipeline">${renderPipeline(w.steps)}</div>`;
      div.querySelector(".exp").onclick = () => exportItem("workflow", w.slug);
      div.querySelector(".archive").onclick = async () => { await api("/workflows/toggle", { method: "POST", body: fd({ slug: w.slug, brain: brain() }) }); loadWorkflows(); };
      div.querySelector(".run").onclick = () => runWorkflow(w, div);
      div.querySelector(".edit").onclick = () => editWorkflow(w);
      div.querySelector(".del").onclick = async () => { if (confirm(`Xoá workflow "${w.name}"?`)) { await api("/workflows/delete", { method: "POST", body: fd({ slug: w.slug, brain: brain() }) }); loadWorkflows(); } };
      cards.appendChild(div);
    });
  }

  // ===== Run workflow (SSE) =====
  function runWorkflow(w, card) {
    const input = prompt(`Đầu vào cho "${w.name}" (vd: chủ đề bài viết):`, "");
    if (input === null) return;

    // Card chuyển sang trạng thái running
    const badge = card && card.querySelector(".wf-badge");
    if (card) { card.classList.add("running"); }
    if (badge) { badge.className = "wf-badge running"; badge.textContent = "⏳ Đang chạy..."; }

    const endRun = () => {
      if (card) { card.classList.remove("running"); }
      if (badge) { badge.className = "wf-badge ready"; badge.textContent = "● Sẵn sàng"; }
      card && card.querySelectorAll(".wf-pstep").forEach(el => el.classList.remove("active"));
    };

    const drawer = document.getElementById("runDrawer");
    const stepsEl = document.getElementById("runSteps");
    document.getElementById("runTitle").textContent = `▶ ${w.name}`;
    stepsEl.innerHTML = `<div class="run-info">Đang khởi động...</div>`;
    drawer.classList.add("open");
    const url = `/workflows/run?slug=${encodeURIComponent(w.slug)}&brain=${encodeURIComponent(brain())}&input=${encodeURIComponent(input)}`;
    const es = new EventSource(url);
    const stepDivs = {};
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d.type === "start") {
        stepsEl.innerHTML = `<div class="run-info">${d.steps} bước · workflow ${esc(d.workflow)}</div>`;
      } else if (d.type === "step_start") {
        // Pipeline card: sáng bước đang chạy
        if (card) {
          card.querySelectorAll(".wf-pstep").forEach(el => el.classList.remove("active"));
          const ps = card.querySelector(`.wf-pstep[data-i="${d.i}"]`);
          if (ps) ps.classList.add("active");
          if (badge) badge.textContent = `⏳ Bước ${d.i + 1}/${w.steps.length}`;
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
        if (div) div.querySelector(".rs-head").insertAdjacentHTML("beforeend", `<span class="rs-tool">⚙ ${esc(d.tool)}</span>`);
      } else if (d.type === "step_verify") {
        const div = stepDivs[d.i];
        if (div) div.querySelector(".rs-head").insertAdjacentHTML("beforeend",
          `<span class="rs-verify" id="rs-vf-${d.i}">🔍 ${esc(d.agent)} đang kiểm chứng${d.attempt ? ` (lần ${d.attempt + 1})` : ""}...</span>`);
      } else if (d.type === "step_verify_result") {
        const vf = document.getElementById(`rs-vf-${d.i}`);
        if (vf) { vf.className = "rs-verify " + (d.passed ? "ok" : "fail"); vf.textContent = (d.passed ? "✓ Đạt" : "✗ Chưa đạt") + (d.reason ? ": " + d.reason : ""); vf.removeAttribute("id"); }
      } else if (d.type === "step_retry") {
        const out = document.getElementById(`rs-out-${d.i}`);
        if (out) out.insertAdjacentHTML("beforebegin", `<div class="rs-retry">↻ Sửa lại lần ${d.attempt}...</div>`);
      } else if (d.type === "step_done") {
        // Pipeline card: bước xong → xanh
        if (card) {
          const ps = card.querySelector(`.wf-pstep[data-i="${d.i}"]`);
          if (ps) { ps.classList.remove("active"); ps.classList.add("done"); }
        }
        const div = stepDivs[d.i];
        if (div) {
          div.classList.add("done");
          const sp = div.querySelector(".rs-spin"); if (sp) sp.outerHTML = `<span class="rs-ok">✓</span>`;
          if (d.verified === false) div.insertAdjacentHTML("beforeend", `<div class="rs-warn">⚠ Chưa đạt kiểm chứng sau số lần thử - xem lại kết quả</div>`);
          const out = document.getElementById(`rs-out-${d.i}`); if (out && !out.textContent.trim()) out.textContent = d.output;
        }
      } else if (d.type === "step_error") {
        const out = document.getElementById(`rs-out-${d.i}`); if (out) out.innerHTML += `<div class="rs-err">⚠ ${esc(d.content)}</div>`;
      } else if (d.type === "done") {
        es.close();
        endRun();
        stepsEl.insertAdjacentHTML("beforeend", `<div class="run-info done">✓ Workflow hoàn tất</div>`);
        stepsEl.scrollTop = stepsEl.scrollHeight;
      }
    };
    es.onerror = () => { es.close(); endRun(); };
    document.getElementById("runClose").onclick = () => { es.close(); endRun(); drawer.classList.remove("open"); };
  }

  // ===== Workflow editor =====
  let agentsCache = [];
  async function editWorkflow(w) {
    const ad = await api(`/agents?brain=${encodeURIComponent(brain())}`);
    agentsCache = ad.agents || [];
    if (!agentsCache.length) { alert("Chưa có agent nào. Hãy tạo Agent trước (tab Agents) hoặc bấm Tạo mẫu."); return; }
    const box = document.getElementById("editorBox");
    const steps = w ? JSON.parse(JSON.stringify(w.steps || [])) : [{ agent: agentsCache[0].slug, task: "" }];
    const opts = (sel) => agentsCache.map(a => `<option value="${a.slug}" ${a.slug === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
    const optsV = (sel) => `<option value="">- không kiểm chứng -</option>` + agentsCache.map(a => `<option value="${a.slug}" ${a.slug === sel ? "selected" : ""}>${esc(a.name)}</option>`).join("");
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
        <h3>${w ? "Sửa" : "Tạo"} Workflow</h3>
        <label>Tên</label><input id="wfName" value="${esc(w ? w.name : "")}">
        <label>Mô tả</label><input id="wfDesc" value="${esc(w ? w.description : "")}">
        <label>Các bước (mỗi bước = 1 agent · dùng {{input}} và {{prev}})</label>
        <div id="stepList"></div>
        <button class="s-btn-ghost" id="addStep">+ Bước</button>
        <div class="editor-actions"><button class="s-btn-ghost" id="cancelEd">Huỷ</button><button class="s-btn" id="saveWf">Lưu</button></div>`;
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
            <button class="st-move" data-d="-1" title="Lên" ${i === 0 ? "disabled" : ""}>↑</button>
            <button class="st-move" data-d="1" title="Xuống" ${i === steps.length - 1 ? "disabled" : ""}>↓</button>
            <button class="st-del" title="Xoá bước">✕</button>
          </div>
          <div class="step-body">
            <textarea class="st-task" rows="3" placeholder="Nhiệm vụ... dùng {{input}} = đầu vào, {{prev}} = kết quả bước trước">${esc(st.task)}</textarea>
            <div class="st-verify">
              <span class="stv-lbl">Kiểm chứng:</span>
              <select class="st-verify-agent">${optsV(st.verify_agent || "")}</select>
              <input class="st-retries" type="number" min="0" max="5" value="${st.max_retries != null ? st.max_retries : 1}">
              <span class="stv-lbl">lần</span>
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
        const name = box.querySelector("#wfName").value.trim(); if (!name) return alert("Nhập tên");
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
    panel.innerHTML = `<div class="panel-bar"><h3>Agents</h3><div class="pb-actions"><button class="s-btn-ghost" id="agImport">⤒ Nhập</button><button class="s-btn" id="newAgent">+ Agent</button></div></div><div class="cards" id="agCards">Đang tải...</div>`;
    document.getElementById("newAgent").onclick = () => editAgent(null);
    document.getElementById("agImport").onclick = () => importItems(loadAgents);
    const d = await api(`/agents?brain=${encodeURIComponent(brain())}`);
    refreshStats();
    const cards = document.getElementById("agCards");
    if (!(d.agents || []).length) { cards.innerHTML = `<div class="empty">Chưa có agent. Bấm <b>+ Agent</b> để tạo (vai trò + skills + bộ nhớ riêng).</div>`; return; }
    cards.innerHTML = "";
    d.agents.forEach(a => {
      const div = document.createElement("div"); div.className = "ag-card";
      div.innerHTML = `<div class="ag-name">🤖 ${esc(a.name)} <span class="ag-model">${esc(a.model || "")}</span></div><div class="ag-role">${esc(a.role)}</div><div class="ag-skills">${(a.skills || []).map(s => `<span class="chip-skill">${esc(s)}</span>`).join("") || '<span class="dim">chưa gán skill</span>'}</div><div class="wf-actions"><button class="s-btn-ghost edit">Sửa</button><button class="s-btn-ghost exp" title="Xuất gói .zip (kèm skill) để chia sẻ">⤓ Xuất</button><button class="s-btn-ghost del">Xoá</button></div>`;
      div.querySelector(".exp").onclick = () => exportItem("agent", a.slug);
      div.querySelector(".edit").onclick = () => editAgent(a);
      div.querySelector(".del").onclick = async () => { if (confirm(`Xoá agent "${a.name}"?`)) { await api("/agents/delete", { method: "POST", body: fd({ slug: a.slug, brain: brain() }) }); loadAgents(); } };
      cards.appendChild(div);
    });
  }

  async function editAgent(a) {
    const sd = await api(`/skills?brain=${encodeURIComponent(brain())}`);
    const skills = sd.skills || [];
    const box = document.getElementById("editorBox");
    box.innerHTML = `<h3>${a ? "Sửa" : "Tạo"} Agent</h3>
      <label>Tên</label><input id="agName" value="${esc(a ? a.name : "")}">
      <label>Vai trò (mô tả ngắn)</label><input id="agRole" value="${esc(a ? a.role : "")}">
      <label>System prompt (cách làm việc chi tiết)</label><textarea id="agPrompt" rows="4">${esc(a ? (a.prompt || "") : "")}</textarea>
      <label>Skills</label><div class="skill-pick" id="skillPick">${skills.length ? skills.map(s => `<label class="sp"><input type="checkbox" value="${esc(s.slug)}" ${a && (a.skills || []).includes(s.slug) ? "checked" : ""}> ${esc(s.name)}</label>`).join("") : '<span class="dim">Vault chưa có skill trong skills/ - vẫn tạo agent được, gán skill sau.</span>'}</div>
      <label>Model</label><select id="agModel">
        <option value="">Mặc định (theo CLI)</option>
        <optgroup label="Claude (Claude Code)"><option value="sonnet">Sonnet</option><option value="opus">Opus</option><option value="haiku">Haiku</option><option value="fable">Fable</option></optgroup>
        <optgroup label="ChatGPT (Codex - cần đăng nhập ChatGPT)"><option value="gpt-5.5">GPT-5.5</option><option value="gpt-5.4">GPT-5.4</option><option value="gpt-5.3-codex">GPT-5.3 Codex</option></optgroup>
      </select>
      <div class="dim" style="font-size:12px;margin-top:4px">Agent chạy qua CLI của nhà cung cấp: chọn Claude → Claude Code; chọn ChatGPT → Codex (cần đã đăng nhập ChatGPT ở máy/VPS). Cả hai đều đọc/ghi file vault + dùng MCP.</div>
      <div class="editor-actions"><button class="s-btn-ghost" id="cancelEd">Huỷ</button><button class="s-btn" id="saveAg">Lưu</button></div>`;
    if (a && a.model) box.querySelector("#agModel").value = a.model;
    box.querySelector("#cancelEd").onclick = () => editor.classList.remove("open");
    box.querySelector("#saveAg").onclick = async () => {
      const name = box.querySelector("#agName").value.trim(); if (!name) return alert("Nhập tên");
      const sk = [...box.querySelectorAll("#skillPick input:checked")].map(c => c.value).join(",");
      await api("/agents", { method: "POST", body: fd({ name, role: box.querySelector("#agRole").value, prompt: box.querySelector("#agPrompt").value, skills: sk, model: box.querySelector("#agModel").value, slug: a ? a.slug : "", brain: brain() }) });
      editor.classList.remove("open"); loadAgents();
    };
    editor.classList.add("open");
  }

  // ===== Skills (quản lý kiểu Hermes: cột nhóm + tìm kiếm + bật/tắt) =====
  const _skState = { cat: "ALL", q: "", skills: [] };
  function _injectSkillCss() {
    if (window._skCss) return; window._skCss = true;
    const css = `
    .sk2{display:flex;gap:16px;align-items:flex-start}
    .sk2-side{width:210px;flex:none;border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:8px;max-height:72vh;overflow:auto}
    .sk2-side .sec{font-size:12px;letter-spacing:.08em;color:#6b7894;padding:8px 10px 4px;text-transform:uppercase}
    .sk2-side .cat{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:7px 10px;border-radius:7px;cursor:pointer;font-size:15px;color:#cdd8ee}
    .sk2-side .cat:hover{background:rgba(120,180,255,.08)} .sk2-side .cat.sel{background:rgba(120,180,255,.16);color:#fff}
    .sk2-side .cat .n{color:#7d8aa6;font-size:13px;flex:none}
    .sk2-main{flex:1;min-width:0}
    .sk2-bar{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
    .sk2-bar h4{margin:0;font-size:17px;color:#e7eefc} .sk2-bar .cnt{color:#7d8aa6;font-size:14px}
    .sk2-bar input{flex:1;min-width:160px;max-width:340px;padding:7px 11px;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:#070b16;color:#dce6fb;font-size:15px;outline:none}
    .sk2-list{display:flex;flex-direction:column;gap:8px}
    .sk2-card{display:flex;gap:12px;align-items:flex-start;padding:11px 13px;border:1px solid rgba(255,255,255,.08);border-radius:10px}
    .sk2-card:hover{border-color:rgba(120,180,255,.25);background:rgba(120,180,255,.04)}
    .sk2-card.off{opacity:.5} .sk2-tog{flex:none;margin-top:3px;width:16px;height:16px;cursor:pointer;accent-color:#ff8a3c}
    .sk2-info{flex:1;min-width:0} .sk2-info .nm{color:#e7eefc;font-size:15px;font-weight:600}
    .sk2-info .ds{color:#9fb0cf;font-size:14px;margin-top:3px;line-height:1.45}
    .sk2-info .gp{color:#6b7894;font-size:13px;margin-top:4px}
    .sk2-act{display:flex;gap:5px;opacity:0;transition:.15s;flex:none} .sk2-card:hover .sk2-act{opacity:1}
    .sk2-act button{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.12);color:#aebbd6;border-radius:6px;cursor:pointer;font-size:13px;padding:3px 9px} .sk2-act button:hover{color:#fff;border-color:rgba(120,180,255,.5)}
    .sk2-act button.danger:hover{color:#ff9a9a;border-color:rgba(255,120,120,.5)}
    .sysb{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:20px;font-size:11px;font-weight:600;letter-spacing:.02em;color:#8fd0ff;background:rgba(90,170,255,.12);border:1px solid rgba(90,170,255,.35);vertical-align:2px}
    .sk-usage{font-size:11px;color:var(--muted,#888);margin-left:8px}
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
      .sk2-side .cat{flex:none;padding:8px 13px;border:1px solid rgba(255,255,255,.1);
        border-radius:999px;white-space:nowrap}
      .sk2-side .cat .n{padding:1px 6px;border-radius:9px;background:rgba(255,255,255,.07)}
      .sk2-side .cat.sel{border-color:rgba(120,180,255,.4)}
      .sk2-bar input{max-width:none;font-size:16px}   /* 16px: chan iOS tu zoom khi focus */
      .sk2-tog{width:20px;height:20px;margin-top:2px}  /* vung cham lon hon */
      .sk2-card{flex-wrap:wrap;padding:12px 13px}
      .sk2-info .nm{font-size:16px}
      .sk2-act{flex:1 1 100%;opacity:1;margin-top:11px;padding-top:11px;gap:8px;
        border-top:1px solid rgba(255,255,255,.06);justify-content:flex-end}
      .sk2-act button{padding:7px 14px;font-size:14px}
    }`;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  }

  async function loadSkills() {
    _injectSkillCss();
    const panel = document.getElementById("panel-skills");
    panel.innerHTML = `<div class="empty">Đang tải...</div>`;
    let d; try { d = await api(`/skills?brain=${encodeURIComponent(brain())}`); } catch (e) { panel.innerHTML = `<div class="empty">Lỗi tải skill.</div>`; return; }
    refreshStats();
    _skState.skills = d.skills || [];
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
    const catHtml = cats.map(c => `<div class="cat ${_skState.cat === c ? "sel" : ""}" data-cat="${esc(c)}"><span>${c === "ALL" ? "Tất cả" : esc(c)}</span><span class="n">${c === "ALL" ? all.length : groups[c]}</span></div>`).join("");
    panel.innerHTML = `
      <div class="panel-bar"><h3>Skills <span class="dim">${enabledN}/${all.length} bật · nguồn <code>skills/</code></span></h3>
        <div class="pb-actions"><button class="s-btn-ghost" id="skImport">⤒ Nhập</button><button class="s-btn" id="skNew">+ Skill</button></div></div>
      ${all.length ? `<div class="sk2">
        <div class="sk2-side"><div class="sec">Nhóm</div>${catHtml}</div>
        <div class="sk2-main">
          <div class="sk2-bar"><h4>${_skState.cat === "ALL" ? "Tất cả" : esc(_skState.cat)}</h4><span class="cnt"></span>
            <input id="skSearch" placeholder="Tìm skill…" value="${esc(_skState.q)}"></div>
          <div class="sk2-list" id="skList"></div>
        </div></div>`
      : `<div class="empty">Brain chưa có skill. Bấm <b>+ Skill</b> để tạo (tự lưu vào <code>skills/</code> + xếp nhóm).</div>`}`;
    document.getElementById("skNew").onclick = () => openSkillForm(null);
    document.getElementById("skImport").onclick = () => importItems(loadSkills);
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
    if (!list.length) { box.innerHTML = `<div class="empty">Không có skill khớp.</div>`; return; }
    box.innerHTML = "";
    list.forEach(s => {
      const on = s.enabled !== false;
      const div = document.createElement("div"); div.className = "sk2-card" + (on ? "" : " off");
      const sysBadge = s.system ? ` <span class="sysb" title="Skill hệ thống Javis OS - có ở mọi brain, tự cập nhật theo phiên bản app. Sửa nội dung thì giữ bản của bạn (ngừng tự cập nhật). Không xoá được - chỉ tắt.">hệ thống</span>` : "";
      // Telemetry: use_count là tín hiệu DƯƠNG một chiều. Skill nạp native qua .claude/skills
      // không đi qua bộ đếm, nên "chưa thấy dùng" là tham khảo, KHÔNG phải phán quyết.
      let usageHtml = "";
      if (s.use_count > 0) {
        const when = s.last_used_at ? new Date(s.last_used_at * 1000).toLocaleDateString("vi-VN") : "";
        usageHtml = ` · <span class="sk-usage">đã dùng ${s.use_count} lần${when ? ", gần nhất " + when : ""}</span>`;
      } else if (s.stale) {
        usageHtml = ` · <span class="sk-usage sk-stale" title="Javis chỉ đếm được skill nạp qua tool javis_use_skill. Claude Code nạp native qua .claude/skills thì không đếm được, nên đây chỉ là tham khảo - không có nghĩa skill vô dụng.">chưa thấy dùng</span>`;
      }
      div.innerHTML = `<input type="checkbox" class="sk2-tog" ${on ? "checked" : ""} title="${on ? "Đang bật - bấm để tắt" : "Đang tắt - bấm để bật"}">
        <div class="sk2-info"><div class="nm">🧩 ${esc(s.name)}${sysBadge}</div><div class="ds">${esc(s.description || "")}</div><div class="gp">📂 ${esc(s.group || "Chung")} · ${esc(s.slug)}${s.source === ".agents" ? " · .agents" : ""}${usageHtml}</div></div>
        <div class="sk2-act"><button class="edit">Sửa</button>${s.system ? "" : `<button class="exp" title="Xuất gói .zip để chia sẻ">⤓ Xuất</button><button class="del danger">Xoá</button>`}</div>`;
      div.querySelector(".sk2-tog").onchange = (e) => toggleSkill(s, e.target.checked);
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
    if (r && r.error) { alert("Không đổi được trạng thái: " + r.error); }
    s.enabled = enabled;
    renderSkillUI(); refreshStats();
  }

  async function openSkillForm(slug) {
    const panel = document.getElementById("panel-skills");
    let sk = { slug: "", name: "", group: "Chung", description: "", body: "" };
    if (slug) { try { sk = await api(`/skills/get?slug=${encodeURIComponent(slug)}&brain=${encodeURIComponent(brain())}`); } catch (e) {} }
    const groupOpts = [...new Set(_skState.skills.map(s => s.group || "Chung"))].map(g => `<option value="${esc(g)}">`).join("");
    panel.innerHTML = `<div class="panel-bar"><h3>${slug ? "Sửa skill" : "Skill mới"}</h3></div>
      <div style="display:flex;flex-direction:column;gap:12px;max-width:660px">
        <div><label>Tên skill</label><input id="skName" class="js-input" value="${esc(sk.name)}" placeholder="VD: Viết email bán hàng"></div>
        <div><label>Nhóm</label><input id="skGroup" class="js-input" list="skGroupList" value="${esc(sk.group || "Chung")}" placeholder="VD: Marketing">
          <datalist id="skGroupList">${groupOpts}</datalist></div>
        <div><label>Mô tả (description - quyết định khi nào skill kích hoạt)</label><textarea id="skDesc" class="js-input" style="min-height:60px">${esc(sk.description || "")}</textarea></div>
        <div><label>Nội dung (SKILL.md - hướng dẫn cho AI)</label><textarea id="skBody" class="js-input" style="min-height:200px;font-family:ui-monospace,monospace">${esc(sk.body || "")}</textarea></div>
        <div style="display:flex;gap:10px"><button class="s-btn" id="skSave">💾 Lưu</button><button class="s-btn-ghost" id="skCancel">Huỷ</button></div>
      </div>`;
    panel.querySelector("#skCancel").onclick = () => loadSkills();
    panel.querySelector("#skSave").onclick = async () => {
      const name = panel.querySelector("#skName").value.trim();
      if (!name) { alert("Nhập tên skill"); return; }
      const b = panel.querySelector("#skSave"); b.disabled = true; b.textContent = "Đang lưu...";
      await api("/skills", { method: "POST", body: fd({
        name, group: panel.querySelector("#skGroup").value.trim() || "Chung",
        description: panel.querySelector("#skDesc").value, body: panel.querySelector("#skBody").value,
        slug: sk.slug || "", brain: brain() }) });
      loadSkills();
    };
  }

  async function deleteSkill(slug, name) {
    if (!confirm(`Xoá skill "${name}"? Sẽ xoá cả thư mục skills/${slug}.`)) return;
    await api("/skills/delete", { method: "POST", body: fd({ slug, brain: brain() }) });
    loadSkills();
  }
})();
