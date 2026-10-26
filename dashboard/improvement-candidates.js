/* Exact private skill review. All returned text is data, never HTML or Markdown. */
(function () {
  "use strict";
  let active = null, epoch = 0;
  const enc = new TextEncoder();
  const tr = key => t(["improve", key].join("."));
  function node(tag, text, action) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = String(text);
    if (action) el.setAttribute("data-action", action);
    return el;
  }
  function button(label, action, fn) {
    const el = node("button", label, action); el.type = "button"; el.onclick = fn; return el;
  }
  function alive(s, version = s.version) {
    return active === s && s.version === version && (!s.isCurrent || s.isCurrent())
      && (!window.currentBrainPath || window.currentBrainPath() === s.brain);
  }
  function close() {
    if (!active) return;
    invalidate(active); clearInterval(active.watch); active.panel.remove(); active = null; epoch++;
  }
  function invalidate(s) {
    s.version++;
    if (s.experiments) { s.experiments.dispose(); s.experiments = null; }
    for (const controller of s.requests) controller.abort(); s.requests.clear();
    s.review?.replaceChildren(); s.form?.replaceChildren(); s.applied?.replaceChildren();
  }
  function info(parent, text) {
    const toggle = button(tr("explanation"), "explanation", null);
    toggle.className = "info-i with-text"; toggle.setAttribute("aria-expanded", "false");
    const body = node("div", text); body.className = "info-body"; body.hidden = true;
    parent.append(toggle, body); // info-tip.js owns the delegated disclosure behavior.
  }
  function failure(s, error) {
    if (!alive(s)) return;
    const key = error.status === 409 ? "stale" : error.status === 400 ? "rejected" : "unavailable";
    s.status.textContent = tr(key);
  }
  async function request(s, path, body) {
    if (!alive(s)) throw Error("stale_panel");
    const version = s.version;
    const suffix = (path.includes("?") ? "&" : "?") + "brain=" + encodeURIComponent(s.brain);
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 30000);
    s.requests.add(controller);
    try {
      const response = await fetch(path + suffix, {credentials:"same-origin", signal:controller.signal,
        ...(body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)})});
      const value = await response.json();
      if (!alive(s, version)) throw Error("stale_panel");
      if (!response.ok || value.ok !== true) { const error = Error("request_unavailable"); error.status = response.status; throw error; }
      return value;
    } finally { clearTimeout(timer); s.requests.delete(controller); }
  }
  function event(s, operation, payload) {
    const fingerprint = operation + JSON.stringify(payload);
    if (!s.events.has(fingerprint)) s.events.set(fingerprint, "candidate-ui-" + crypto.randomUUID());
    return s.events.get(fingerprint); // Preserve the exact event through an uncertain transport retry.
  }
  async function write(s, path, payload, operation) {
    const fingerprint = operation + JSON.stringify(payload), key = event(s, operation, payload);
    const value = await request(s, path, {...payload, event_key:key});
    // An acknowledged operation is complete; the next explicit click is a new
    // intent. Unknown transport outcomes retain their key for an exact retry.
    if (s.events.get(fingerprint) === key) s.events.delete(fingerprint);
    return value;
  }
  async function exact(value) {
    if (!value || typeof value.text !== "string" || !/^[a-f0-9]{64}$/.test(value.hash)) throw Error("exact_text_required");
    const bytes = enc.encode(value.text);
    if (bytes.length !== value.byte_size || bytes.length > 1048576) throw Error("exact_size_changed");
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), x=>x.toString(16).padStart(2,"0")).join("");
    if (digest !== value.hash) throw Error("exact_hash_changed");
    return bytes;
  }
  function content(s, parent, name, value, bytes, action) {
    const version = s.version;
    parent.append(node("h4", name), node("p", `${value.byte_size} ${tr("bytes")} · SHA-256 ${value.hash}`, action + "-facts"));
    const pre = node("pre", value.text, action + "-text"); pre.tabIndex = 0; parent.append(pre);
    parent.append(button(tr("download"), action + "-download", () => {
      if (!alive(s, version)) return;
      const url = URL.createObjectURL(new Blob([bytes], {type:"application/octet-stream"}));
      const link = node("a"); link.href = url; link.download = action + ".txt"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }));
  }
  function contextActive(s) {
    return s.context && s.context.grant_status === "active" && s.context.base_generation === s.context.current_generation;
  }
  async function rows(s) {
    const data = await request(s, "/improvement-candidates?experiment_id=" + encodeURIComponent(s.context.experiment_id));
    if (!Array.isArray(data.candidates)) throw Error("candidate_metadata_required");
    s.rows = data.candidates;
    s.list.replaceChildren();
    for (const row of s.rows) {
      const card = node("div"); card.append(node("p", `${tr("proposal")} ${row.ordinal} · ${tr("semantic_pending")}`));
      if (row.edit_authority) card.append(node("p", tr(row.edit_authority.status === "active" ? "edit_authorized" : "edit_revoked")));
      card.append(button(tr("review"), "review-" + row.candidate_id, () => review(s, row.candidate_id)));
      s.list.append(card);
    }
    if (!s.rows.length) s.list.append(node("p", tr("no_candidates")));
    await activations(s);
    return s.rows;
  }
  // M2E: pointers that apply a candidate to one assistant chat. Labels come from server state.
  async function activations(s) {
    const version = s.version;
    const data = await request(s, "/improvement-activations?target_id=" + encodeURIComponent(s.context.target_id));
    if (!alive(s, version) || !Array.isArray(data.activations)) return;
    s.applied.replaceChildren(node("h3", tr("activations_title")));
    for (const row of data.activations) {
      const card = node("div", null, "activation-" + row.activation_id);
      const who = (row.selector && (row.selector.agent_slug || row.selector.agent_key)) || "";
      card.append(node("p", `${who} · ${tr("state_" + row.state)}`));
      card.append(node("p", tr(row.evidence_level === "qualified" ? "qualified" : "manual_trial")));
      if (row.state === "suspended") card.append(node("p", tr("reason_" + row.reason)));
      if (row.canary) {
        card.append(node("p", `${tr("canary")} ${row.canary.allocation_pct}% · ${tr("canary_state_" + row.canary.state)}`));
        if (row.canary.state === "canary") card.append(button(tr("canary_open"), "canary-" + row.activation_id, () => canary(s, row, card)));
      }
      if (row.state === "active") {
        const revert = button(tr("revert"), "revert-" + row.activation_id, async () => {
          if (!alive(s, version) || revert.disabled) return;
          revert.disabled = true;
          try {
            await write(s, "/improvement-activations/" + encodeURIComponent(row.activation_id) + "/revert",
              {expected_generation:row.generation}, "revert-" + row.activation_id);
            s.status.textContent = tr("reverted_ok");
            await activations(s);
          } catch (error) { failure(s, error); revert.disabled = false; }
        });
        card.append(revert);
      }
      s.applied.append(card);
    }
    if (!data.activations.length) s.applied.append(node("p", tr("no_activations")));
    await grants(s, version);
    await routing(s, version);
    await procedures(s, version);
    await governance(s, version);
  }
  // M8: pause every live improvement of the brain at once (skill fixes, procedures, descriptions, bundles).
  async function governance(s, version) {
    const data = await request(s, "/improvement-governance");
    if (!alive(s, version)) return;
    const live = data.live || [];
    const box = node("div", null, "governance"); box.append(node("h3", tr("governance_title")));
    info(box, tr("governance_hint"));
    box.append(node("p", tr("governance_live").replace("{n}", String(live.length)), "governance-count"));
    const pause = button(tr("governance_pause"), "governance-pause", async () => {
      if (!alive(s, version) || pause.disabled || !live.length) return;
      pause.disabled = true;
      try {
        const result = await write(s, "/improvement-governance/suspend-all", {}, "governance-pause-" + live.length);
        s.status.textContent = tr(result.remaining && result.remaining.length ? "governance_partial" : "governance_done");
        await activations(s);
      } catch (error) { failure(s, error); pause.disabled = false; }
    });
    pause.disabled = !live.length;
    box.append(pause);
    s.applied.append(box);
  }
  // M4: a description candidate is measured against intent cases with Javis's own router, then
  // applied to the brain's main chat (API engines). Each case line: kind | expected skill | question.
  async function routing(s, version) {
    const data = await request(s, "/improvement-routing?target_id=" + encodeURIComponent(s.context.target_id));
    if (!alive(s, version)) return;
    const box = node("div", null, "routing"); box.append(node("h3", tr("routing_title")));
    info(box, tr("routing_hint"));
    for (const overlay of (data.overlays || []).filter(x => x.state === "active")) {
      const line = node("div", null, "routing-overlay-" + overlay.overlay_id);
      line.append(node("p", tr("routing_active") + ": " + overlay.description));
      line.append(button(tr("revert"), "routing-revert-" + overlay.overlay_id, async () => {
        try { await write(s, "/improvement-routing-overlays/" + encodeURIComponent(overlay.overlay_id) + "/revert",
          {expected_generation: overlay.generation}, "routing-revert-" + overlay.overlay_id); await activations(s); }
        catch (error) { failure(s, error); }
      }));
      box.append(line);
    }
    const description = field(box, "routing_description"); description.rows = 2;
    const cases = field(box, "routing_cases"); cases.rows = 6;
    const result = node("div", null, "routing-result");
    box.append(button(tr("routing_evaluate"), "routing-evaluate", async () => {
      if (!alive(s, version)) return;
      try {
        // Split on the first two bars only, so a question may itself contain "|".
        const parsed = cases.value.split(/\r?\n/).map(line => line.split("|")).filter(x => x.length >= 3)
          .map(([kind, expected, ...rest]) => ({kind: kind.trim(), expected: kind.trim() === "negative" ? "" : expected.trim(), query: rest.join("|").trim()}))
          .filter(x => x.query);
        const value = (await write(s, "/improvement-routing/evaluate", {target_id: s.context.target_id,
          description: description.value, cases: parsed}, "routing-evaluate")).routing;
        const report = value.report, o = report.outcomes;
        result.replaceChildren(node("p", `${tr("routing_verdict")}: ${tr("routing_verdict_" + value.verdict)}`),
          node("p", `${tr("routing_wins")}: ${o.win} · ${tr("routing_losses")}: ${o.loss} · ${tr("routing_ties")}: ${o.tie}`),
          node("p", tr("routing_cli_not_measured")));
        if (value.verdict !== "rejected") result.append(button(tr("routing_apply"), "routing-apply", async () => {
          try { await write(s, "/improvement-routing/" + encodeURIComponent(value.candidate_id) + "/apply", {}, "routing-apply-" + value.candidate_id); await activations(s); }
          catch (error) { failure(s, error); }
        }));
      } catch (error) { failure(s, error); }
    }));
    box.append(result);
    s.applied.append(box);
  }
  // M5: an owner-approved procedure added to one assistant's prompt on the surfaces the owner ticks.
  // The text is shown back exactly; applying needs the owner's own confirmation box.
  const SURFACES = ["dm", "team", "kanban", "workflow"];
  async function procedures(s, version) {
    const box = node("div", null, "procedures"); box.append(node("h3", tr("procedure_title")));
    info(box, tr("procedure_hint"));
    const label = node("label", tr("apply_agent")), choose = node("select", null, "procedure-agent");
    label.append(choose); box.append(label);
    const agents = (await request(s, "/agents?prompt=0")).agents || [];
    if (!alive(s, version)) return;
    for (const agent of agents) { const option = node("option", agent.name || agent.slug); option.value = agent.slug; choose.append(option); }
    const current = node("div", null, "procedure-current");
    const text = field(box, "procedure_text"); text.rows = 5;
    const ticks = {};
    for (const surface of SURFACES) {
      const tick = node("label", tr("procedure_surface_" + surface)), input = node("input", null, "procedure-surface-" + surface);
      input.type = "checkbox"; input.checked = surface === "dm"; ticks[surface] = input; tick.prepend(input); box.append(tick);
    }
    const confirmLabel = node("label", tr("procedure_confirm")), confirm = node("input", null, "procedure-confirm");
    confirm.type = "checkbox"; confirmLabel.prepend(confirm); box.append(confirmLabel);
    // M6: apply together with the skill fix under review, as one bundle (private chat only).
    const bundleLabel = node("label", tr("bundle_with_skill")), together = node("input", null, "procedure-bundle");
    together.type = "checkbox"; bundleLabel.prepend(together); box.append(bundleLabel);
    async function load() {
      current.replaceChildren();
      if (!choose.value) return;
      const data = await request(s, "/improvement-agent-procedures?agent=" + encodeURIComponent(choose.value));
      const packs = (await request(s, "/improvement-agent-bundles?agent=" + encodeURIComponent(choose.value))).bundles || [];
      if (!alive(s, version)) return;
      const bundled = new Set(packs.filter(x => x.state === "active").flatMap(x => x.members.map(m => m.pointer_id)));
      for (const pack of packs.filter(x => x.state === "active" || x.state === "suspended")) {
        const line = node("div", null, "bundle-" + pack.bundle_id);
        line.append(node("p", `${tr("bundle_title")} · ${tr("state_" + pack.state)}`));
        if (pack.state === "suspended") line.append(node("p", tr("bundle_reason_" + pack.reason)));
        if (pack.state === "active") line.append(button(tr("revert"), "bundle-revert-" + pack.bundle_id, async () => {
          try { await write(s, "/improvement-agent-bundles/" + encodeURIComponent(pack.bundle_id) + "/revert",
            {expected_generation: pack.generation}, "bundle-revert-" + pack.bundle_id); s.status.textContent = tr("reverted_ok"); await load(); }
          catch (error) { failure(s, error); }
        }));
        current.append(line);
      }
      for (const overlay of (data.overlays || []).filter(x => x.state !== "reverted")) {
        const procedure = (data.procedures || []).find(x => x.procedure_id === overlay.procedure_id);
        const line = node("div", null, "procedure-overlay-" + overlay.overlay_id);
        line.append(node("p", `${tr("state_" + overlay.state)} · ${overlay.surfaces.map(x => tr("procedure_surface_" + x)).join(", ")}`));
        if (overlay.state === "suspended") line.append(node("p", tr("procedure_reason_" + overlay.reason)));
        if (procedure) line.append(node("pre", procedure.text, "procedure-overlay-text-" + overlay.overlay_id));
        if (overlay.state === "active" && !bundled.has(overlay.overlay_id)) line.append(button(tr("revert"), "procedure-revert-" + overlay.overlay_id, async () => {
          try { await write(s, "/improvement-agent-overlays/" + encodeURIComponent(overlay.overlay_id) + "/revert",
            {expected_generation: overlay.generation}, "procedure-revert-" + overlay.overlay_id); s.status.textContent = tr("reverted_ok"); await load(); }
          catch (error) { failure(s, error); }
        }));
        current.append(line);
      }
      // Saved candidates never applied (owner drafts, learned additions held while a procedure is active).
      const used = new Set((data.overlays || []).map(x => x.procedure_id));
      for (const procedure of (data.procedures || []).filter(x => !used.has(x.procedure_id)).slice(0, 5)) {
        const line = node("div", null, "procedure-staged-" + procedure.procedure_id);
        line.append(node("p", tr("procedure_source_" + procedure.source)), node("pre", procedure.text));
        line.append(button(tr("procedure_use_draft"), "procedure-staged-draft-" + procedure.procedure_id, () => { text.value = procedure.text; }));
        current.append(line);
      }
      // Self-review ideas outside what review may change itself: the owner can start from one, then edits and confirms.
      for (const proposal of data.review_proposals || []) {
        const line = node("div", null, "procedure-proposal-" + proposal.id);
        line.append(node("p", tr("procedure_proposal")), node("pre", proposal.text));
        line.append(button(tr("procedure_use_draft"), "procedure-draft-" + proposal.id, () => { text.value = proposal.text; }));
        current.append(line);
      }
    }
    choose.onchange = () => load().catch(error => failure(s, error));
    const apply = button(tr("procedure_apply"), "procedure-apply", async () => {
      const surfaces = SURFACES.filter(x => ticks[x].checked);
      if (!alive(s, version) || apply.disabled || !choose.value || !surfaces.length || !confirm.checked) return;
      apply.disabled = true;
      try {
        if (together.checked && (!s.bundleCandidate || surfaces.join() !== "dm")) {
          s.status.textContent = tr(s.bundleCandidate ? "bundle_dm_only" : "bundle_needs_skill"); apply.disabled = false; return;
        }
        const staged = (await write(s, "/improvement-agent-procedures", {agent: choose.value, text: text.value},
          "procedure-stage-" + choose.value)).procedure;
        if (together.checked) {
          const manifest = {members: [{key: "skill", kind: "skill", candidate_id: s.bundleCandidate},
            {key: "procedure", kind: "procedure", procedure_id: staged.procedure_id, surfaces}], depends_on: {procedure: ["skill"]}};
          await write(s, "/improvement-agent-bundles", {agent: choose.value, manifest, owner_confirmed: true},
            "bundle-apply-" + staged.procedure_id + "-" + s.bundleCandidate);
          together.checked = false;
        } else {
          await write(s, "/improvement-agent-procedures/" + encodeURIComponent(staged.procedure_id) + "/apply",
            {surfaces, owner_confirmed: true}, "procedure-apply-" + staged.procedure_id);
        }
        confirm.checked = false; s.status.textContent = tr("applied_ok"); await load();
      } catch (error) { failure(s, error); }
      apply.disabled = false;
    });
    apply.disabled = !agents.length;
    box.append(apply, current);
    s.applied.append(box);
    await load();
  }
  // M3: observation of one canary. Only explicit owner verdicts count; the server decides sufficiency.
  async function canary(s, row, card) {
    const version = s.version;
    const value = (await request(s, "/improvement-canaries/" + encodeURIComponent(row.activation_id))).canary;
    if (!alive(s, version)) return;
    card.querySelector('[data-action="canary-panel-' + row.activation_id + '"]')?.remove();
    const box = node("div", null, "canary-panel-" + row.activation_id); card.append(box);
    const o = value.observation, arms = o.arms;
    box.append(node("p", `${tr("canary_days")}: ${o.days} / ${o.required.days}`));
    box.append(node("p", `${tr("canary_arm_canary")}: ${arms.canary.pass} ${tr("verdict_pass")} · ${arms.canary.fail} ${tr("verdict_fail")} · ${arms.canary.exposures} ${tr("canary_exposures")}`));
    box.append(node("p", `${tr("canary_arm_control")}: ${arms.control.pass} ${tr("verdict_pass")} · ${arms.control.fail} ${tr("verdict_fail")} · ${arms.control.exposures} ${tr("canary_exposures")}`));
    box.append(node("p", tr(o.sufficient ? "canary_sufficient" : "canary_insufficient")));
    for (const exposure of value.exposures.filter(x => !x.verdict).slice(0, 20)) {
      const line = node("div", null, "exposure-" + exposure.session_id + "-" + exposure.message_id);
      line.append(node("span", new Date(exposure.at * 1000).toLocaleString() + " · " + tr("canary_arm_" + exposure.arm)));
      for (const verdict of ["pass", "fail"]) {
        line.append(button(tr("verdict_" + verdict), "verdict-" + verdict + "-" + exposure.session_id + "-" + exposure.message_id, async () => {
          try {
            await write(s, "/improvement-canaries/" + encodeURIComponent(row.activation_id) + "/verdicts",
              {session_id: exposure.session_id, message_id: exposure.message_id, verdict}, "verdict-" + row.activation_id + exposure.session_id + exposure.message_id);
            await activations(s);
          } catch (error) { failure(s, error); }
        }));
      }
      box.append(line);
    }
    const promote = button(tr("canary_promote"), "promote-" + row.activation_id, async () => {
      if (!alive(s, version) || promote.disabled) return;
      promote.disabled = true;
      try {
        await write(s, "/improvement-canaries/" + encodeURIComponent(row.activation_id) + "/promote",
          {expected_generation: value.generation}, "promote-" + row.activation_id);
        await activations(s);
      } catch (error) { failure(s, error); promote.disabled = false; }
    });
    promote.disabled = !o.sufficient || value.state !== "canary";
    box.append(promote);
  }
  async function grants(s, version) {
    const data = await request(s, "/improvement-auto-scopes?target_id=" + encodeURIComponent(s.context.target_id));
    if (!alive(s, version)) return;
    for (const grant of (data.grants || []).filter(x => x.status === "active")) {
      const line = node("div", null, "grant-" + grant.grant_id);
      line.append(node("p", `${tr("auto_scope")}: ${grant.selector.agent_slug || grant.selector.agent_key} · ${grant.allocation_pct}%`));
      line.append(button(tr("auto_scope_revoke"), "revoke-grant-" + grant.grant_id, async () => {
        try { await write(s, "/improvement-auto-scopes/" + encodeURIComponent(grant.grant_id) + "/revoke", {expected_generation: grant.generation}, "revoke-grant-" + grant.grant_id); await activations(s); }
        catch (error) { failure(s, error); }
      }));
      s.applied.append(line);
    }
  }
  async function applyBlock(s, current, version) {
    const authority = current.edit_authority;
    s.bundleCandidate = null; // set again below only for an exact approved candidate now on screen
    if (current.keep_base || !authority || authority.status !== "active" || authority.kind !== "exact_diff") return;
    s.bundleCandidate = current.candidate_id; // M6: the skill half of an assistant bundle
    const box = node("div", null, "apply"); box.append(node("h4", tr("apply_title")));
    info(box, tr("apply_hint"));
    const label = node("label", tr("apply_agent")), choose = node("select", null, "apply-agent");
    label.append(choose); box.append(label);
    const shareLabel = node("label", tr("apply_share")), share = node("select", null, "apply-share");
    for (const value of [100, 10, 25, 50]) { const option = node("option", value === 100 ? tr("apply_share_all") : tr("canary") + " " + value + "%"); option.value = String(value); share.append(option); }
    share.value = "100"; // Default: the assistant's whole chat, the M2E manual apply.
    shareLabel.append(share); box.append(shareLabel);
    const agents = (await request(s, "/agents?prompt=0")).agents || [];
    if (!alive(s, version)) return;
    for (const agent of agents) {
      const option = node("option", agent.name || agent.slug); option.value = agent.slug;
      if (agent.description) option.setAttribute("data-desc", agent.description);
      option.setAttribute("data-name", agent.name || agent.slug);
      choose.append(option);
    }
    const apply = button(tr("apply_button"), "apply-candidate", async () => {
      if (!alive(s, version) || apply.disabled || !choose.value) return;
      apply.disabled = true;
      try {
        const pct = Number(share.value) || 100;
        await write(s, "/improvement-activations", {candidate_id:current.candidate_id, agent_slug:choose.value,
          ...(pct < 100 ? {allocation_pct: pct} : {})}, "apply-" + current.candidate_id + "-" + choose.value + "-" + pct);
        s.status.textContent = tr("applied_ok");
        await activations(s);
      } catch (error) { failure(s, error); }
      apply.disabled = false;
    });
    apply.disabled = !agents.length;
    box.append(apply);
    const grant = button(tr("auto_scope_grant"), "grant-auto", async () => {
      if (!alive(s, version) || grant.disabled || !choose.value) return;
      grant.disabled = true;
      try {
        await write(s, "/improvement-auto-scopes", {target_id: s.context.target_id, agent_slug: choose.value, allocation_pct: 10},
          "grant-" + s.context.target_id + "-" + choose.value);
        await activations(s);
      } catch (error) { failure(s, error); }
      grant.disabled = false;
    });
    grant.disabled = !agents.length;
    box.append(grant);
    info(box, tr("auto_scope_hint"));
    if (!agents.length) box.append(node("p", tr("no_agents")));
    s.review.append(box);
    if (window.JavisAgentPicker) window.JavisAgentPicker.enhance(choose, {title: t("ap.title")});
  }
  async function review(s, candidateId) {
    const version = s.version;
    s.review.replaceChildren(); s.status.textContent = tr("loading");
    s.bundleCandidate = null; // a bundle only ever takes the candidate on screen
    try {
      const value = (await request(s, "/improvement-candidates/" + encodeURIComponent(candidateId) + "/review", {})).review;
      const before = await exact(value.before), after = await exact(value.after);
      const current = (await rows(s)).find(row=>row.candidate_id === candidateId);
      if (!alive(s, version)) return;
      if (!current || value.candidate_id !== current.candidate_id || value.before.hash !== current.base_hash || value.after.hash !== current.content_hash
          || value.metadata.base_generation !== current.base_generation) throw Error("candidate_metadata_changed");
      content(s, s.review, tr("before"), value.before, before, "before");
      content(s, s.review, tr("after"), value.after, after, "after");
      for (const key of ["hypothesis", "failure_signature", "expected_behavior", "possible_regressions"]) {
        s.review.append(node("h4", tr(key)), node("pre", Array.isArray(value[key]) ? value[key].join("\n") : value[key]));
      }
      s.review.append(node("p", tr("semantic_pending")));
      const authorize = button(tr("authorize"), "authorize", async () => {
        if (!alive(s, version) || authorize.disabled) return;
        authorize.disabled = true;
        try {
          await write(s, "/improvement-candidates/" + encodeURIComponent(candidateId) + "/authorize", {
            expected_generation:current.base_generation, before_hash:value.before.hash, after_hash:value.after.hash}, "authorize-" + candidateId);
          await review(s, candidateId); // Read current authority, never render a historical event as current.
        } catch (error) { failure(s, error); }
      });
      authorize.disabled = !contextActive(s) || current.context_grant.status !== "active" || !!current.edit_authority;
      s.review.append(authorize);
      if (current.edit_authority && current.edit_authority.status === "active") {
        const authority = current.edit_authority;
        const revoke = button(tr("revoke"), "revoke", async () => {
          if (!alive(s, version) || revoke.disabled) return;
          revoke.disabled = true;
          try {
            await write(s, "/improvement-edit-authorities/" + encodeURIComponent(authority.authority_id) + "/revoke",
              {expected_generation:authority.generation}, "revoke-" + authority.authority_id);
            await review(s, candidateId);
          } catch (error) { failure(s, error); }
        });
        s.review.append(revoke);
      }
      await applyBlock(s, current, version);
      if (!alive(s, version)) return;
      s.status.textContent = tr(current.edit_authority ? (current.edit_authority.status === "active" ? "edit_authorized" : "edit_revoked") : "proposal");
    } catch (error) { if (alive(s, version)) { s.review.replaceChildren(); failure(s, error); } }
  }
  function field(parent, key, kind = "textarea") {
    const label = node("label", tr(key)), input = node(kind, null, key);
    if (kind === "input") input.type = "number";
    label.append(input); parent.append(label); return input;
  }
  // Textarea selection counts UTF-16 with LF-normalized newlines. Map it back to
  // the original string first, then count UTF-8 bytes; reject split surrogates.
  function selection(raw, shown, start, end) {
    let normalized = "", positions = [0];
    for (let i = 0; i < raw.length;) {
      if (raw[i] === "\r" && raw[i + 1] === "\n") { normalized += "\n"; i += 2; positions.push(i); }
      else { normalized += raw[i++]; positions.push(i); }
    }
    if (shown !== normalized || !Number.isInteger(start) || !Number.isInteger(end) || start > end || positions[end] === undefined) throw Error("selection_changed");
    const boundary = n => n === 0 || n === raw.length || !(/[\uD800-\uDBFF]/.test(raw[n - 1]) && /[\uDC00-\uDFFF]/.test(raw[n]));
    if (!boundary(positions[start]) || !boundary(positions[end])) throw Error("split_character");
    return [enc.encode(raw.slice(0, positions[start])).length, enc.encode(raw.slice(0, positions[end])).length];
  }
  async function baseline(s) {
    const version = s.version;
    s.form.replaceChildren();
    try {
      if (!contextActive(s)) throw Error("context_unavailable");
      const base = (await request(s, "/improvement-candidate-baselines/" + encodeURIComponent(s.context.experiment_id) + "/review", {target_id:s.context.target_id})).review;
      const bytes = await exact(base.baseline);
      if (!alive(s, version)) return;
      if (base.target_id !== s.context.target_id || base.base_generation !== s.context.base_generation) throw Error("baseline_changed");
      content(s, s.form, tr("before"), base.baseline, bytes, "baseline");
      const select = field(s.form, "baseline-selection"); select.value = base.baseline.text; select.readOnly = true; select.rows = 8;
      const start = field(s.form, "start", "input"), end = field(s.form, "end", "input");
      start.value = String(base.editable_start); end.value = String(base.baseline.byte_size);
      const replacement = field(s.form, "replacement");
      s.form.append(button(tr("use_selection"), "use-selection", () => {
        if (!alive(s, version)) return;
        try { const bounds = selection(base.baseline.text, select.value, select.selectionStart, select.selectionEnd); start.value = String(bounds[0]); end.value = String(bounds[1]); }
        catch (error) { failure(s, error); }
      }));
      const fields = {};
      for (const key of ["hypothesis", "failure_signature", "expected_behavior", "possible_regressions"]) fields[key] = field(s.form, key);
      const angle = node("select", null, "angle");
      for (const key of ["execution", "domain_process"]) { const option = node("option", tr(key)); option.value = key; angle.append(option); }
      angle.value = "execution"; const angleLabel = node("label", tr("angle")); angleLabel.append(angle); s.form.append(angleLabel);
      const payload = () => ({experiment_id:s.context.experiment_id, patch:{version:1,target_id:base.target_id,base_revision_id:base.base_revision_id,
        before_hash:base.baseline.hash,operation:"replace_body_region",start:Number(start.value),end:Number(end.value),replacement:replacement.value,
        hypothesis:fields.hypothesis.value,failure_signature:fields.failure_signature.value,expected_behavior:fields.expected_behavior.value,
        possible_regressions:fields.possible_regressions.value.split(/\r?\n/).filter(x=>x.trim()),evidence_refs:[],angle:angle.value}});
      const stage = button(tr("stage"), "stage", async () => {
        if (!alive(s, version) || stage.disabled) return;
        stage.disabled = true;
        let committed = false;
        try {
          const data = await write(s, "/improvement-candidates", payload(), "stage");
          committed = true;
          await rows(s); s.form.replaceChildren(); await review(s, data.candidate.candidate_id);
        } catch (error) {
          if (alive(s, version)) {
            if (committed) s.status.textContent = tr("staged_refresh_required");
            else { failure(s, error); stage.disabled = false; }
          }
        }
      });
      stage.disabled = s.rows.length >= 2; s.form.append(stage);
      s.form.append(button(tr("declare_region"), "declare-region", async () => {
        if (!alive(s, version)) return;
        try {
          await write(s, "/improvement-edit-regions", {experiment_id:s.context.experiment_id,base_revision_id:base.base_revision_id,
            start:Number(start.value),end:Number(end.value),expected_target_generation:base.base_generation}, "region");
          s.status.textContent = tr("region_authorized");
        } catch (error) { failure(s, error); }
      }));
      s.status.textContent = tr("semantic_pending");
    } catch (error) { if (alive(s, version)) failure(s, error); }
  }
  async function load(s) {
    if (s.more) { s.more.remove(); s.more = null; }
    try {
      const data = (await request(s, "/improvement-candidate-contexts?slug=" + encodeURIComponent(s.slug))).contexts;
      s.contexts = data.items; s.choose.replaceChildren();
      for (let i = 0; i < s.contexts.length; i++) {
        const row = s.contexts[i], date = new Date(row.created_at * 1000).toLocaleDateString();
        const option = node("option", (row.objectives.map(x=>x.objective).join(" · ") || tr("prepared_context")) + " · " + date);
        option.value = String(i); s.choose.append(option);
      }
      s.choose.value = "0";
      const change = async () => {
        invalidate(s); s.context = s.contexts[Number(s.choose.value)];
        const version = s.version;
        s.prepare.disabled = !contextActive(s);
        if (s.context) await rows(s); else s.list.replaceChildren();
        if (!alive(s, version)) return;
        if (s.context && window.JavisImprovementExperiments) {
          s.experiments = window.JavisImprovementExperiments.mount({parent:s.experimentArea,brain:s.brain,context:s.context,
            isCurrent:()=>alive(s, version),review:id=>review(s,id),refreshCandidates:()=>rows(s)});
          await s.experiments.ready;
          if (!alive(s, version)) return;
        }
        s.status.textContent = tr(!s.context ? "no_contexts" : !contextActive(s) ? "stale" : "semantic_pending");
      };
      s.choose.onchange = async () => { try { await change(); } catch (error) { failure(s, error); } };
      await change();
      if (data.next_cursor) {
        const more = button(tr("more_contexts"), "more-contexts", async () => {
          try {
            const next = (await request(s, "/improvement-candidate-contexts?slug=" + encodeURIComponent(s.slug) + "&cursor=" + encodeURIComponent(data.next_cursor))).contexts;
            data.next_cursor = next.next_cursor;
            for (const row of next.items) { const option = node("option", (row.objectives.map(x=>x.objective).join(" · ") || tr("prepared_context")) + " · " + new Date(row.created_at * 1000).toLocaleDateString()); option.value = String(s.contexts.length); s.contexts.push(row); s.choose.append(option); }
            more.disabled = !data.next_cursor;
          } catch (error) { failure(s, error); }
        }); s.more = more; s.panel.append(more);
      }
    } catch (error) { failure(s, error); }
  }
  function shell(brain, slug, isCurrent) {
    close();
    const panel = node("section"); panel.className = "improvement-candidate-panel"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-label", tr("title"));
    const s = {brain,slug,isCurrent,panel,version:++epoch,events:new Map(),rows:[],requests:new Set()}; active = s;
    panel.append(node("h2", tr("title")), button(tr("close"), "close", close));
    info(panel, tr("scope_hint"));
    s.status = node("p", tr("loading"), "status"); s.status.setAttribute("role", "status"); panel.append(s.status);
    document.body.append(panel);
    s.watch = setInterval(() => { if (active === s && !alive(s)) close(); }, 250);
    panel.onkeydown = e => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const controls = Array.from(panel.querySelectorAll("button, input, textarea, select, a[href], [tabindex='0']")).filter(x=>!x.disabled && !x.hidden);
        const first = controls[0], last = controls[controls.length - 1];
        if (controls.length && ((e.shiftKey && document.activeElement === first) || (!e.shiftKey && document.activeElement === last))) {
          e.preventDefault(); (e.shiftKey ? last : first).focus();
        }
      }
    };
    s.status.tabIndex = -1; s.status.focus();
    return s;
  }
  // Self-learning run for this skill: examples next to the skill, Javis proposes, tests and picks; the owner applies.
  // Independent of the context section below, whose reloads bump s.version: it only checks that the panel lives.
  async function selfLearning(s) {
    let data;
    try { data = await request(s, "/improvement-loops?slug=" + encodeURIComponent(s.slug)); }
    catch (error) {
      if (error && error.status) return; // older server or refused: no section
      if (alive(s)) setTimeout(() => { if (alive(s)) selfLearning(s); }, 5000); // aborted by a context reload: retry
      return;
    }
    if (!alive(s)) return;
    const box = s.loop; box.replaceChildren(node("h3", tr("loop_title")));
    info(box, tr("loop_hint"));
    const run = (data.runs || [])[0];
    const running = run && run.state === "running";
    if (data.protected) box.append(node("p", tr("loop_protected"), "loop-protected"));
    else if (!data.examples.ok) box.append(node("p", tr(data.examples.reason === "examples_need_fresh_sealed"
      ? "loop_examples_fresh" : "loop_examples_missing"), "loop-examples"));
    else box.append(node("p", tr("loop_examples").replace("{t}", data.examples.tuning).replace("{q}", data.examples.qualification)
      .replace("{n}", data.examples.estimated_calls), "loop-examples"));
    const start = button(tr("loop_start"), "loop-start", async () => {
      if (!alive(s) || start.disabled) return;
      start.disabled = true;
      try { await write(s, "/improvement-loops", {slug: s.slug}, "loop-start-" + s.slug); }
      catch (error) { failure(s, error); }
      await selfLearning(s);
    });
    start.disabled = !!(data.protected || !data.examples.ok || running);
    box.append(start);
    if (!run) return;
    if (running) {
      const last = (run.progress || []).slice(-1)[0];
      box.append(node("p", tr(run.cancel_requested ? "loop_stopping" : "loop_running") +
        (last && last.version ? " · " + last.version : ""), "loop-state"));
      if (!run.cancel_requested) box.append(button(tr("loop_cancel"), "loop-cancel", async () => {
        try { await write(s, "/improvement-loops/" + encodeURIComponent(run.run_id) + "/cancel", {}, "loop-cancel-" + run.run_id);
          await selfLearning(s); }
        catch (error) { failure(s, error); }
      }));
      setTimeout(() => { if (alive(s)) selfLearning(s); }, 5000);
      return;
    }
    if (run.state === "failed" || run.state === "cancelled") {
      box.append(node("p", tr(run.state === "cancelled" ? "loop_cancelled" : String(run.error || "").startsWith("engine_unavailable")
        ? "loop_engine_unavailable" : "loop_failed"), "loop-state"));
      return;
    }
    const result = run.result || {}, report = result.report || {};
    box.append(node("p", tr(report.reason === "sealed_set_reused" ? "loop_sealed_reused" : "loop_verdict_" + (report.verdict || "keep_base")), "loop-state"));
    if (report.outcomes) {
      box.append(node("p", tr("loop_outcomes").replace("{w}", report.outcomes.win).replace("{t}", report.outcomes.tie)
        .replace("{l}", report.outcomes.loss).replace("{b}", Math.round(100 * report.base_pass_rate))
        .replace("{c}", Math.round(100 * report.candidate_pass_rate)), "loop-outcomes"));
    }
    if (result.chosen && result.chosen !== "base" && report.verdict === "helped" && !run.applied_at) {
      box.append(node("pre", result.chosen_text, "loop-text"));
      const apply = button(tr("loop_apply"), "loop-apply", async () => {
        if (!alive(s) || apply.disabled) return;
        apply.disabled = true;
        try { await write(s, "/improvement-loops/" + encodeURIComponent(run.run_id) + "/apply", {}, "loop-apply-" + run.run_id);
          s.status.textContent = tr("loop_applied"); await selfLearning(s); }
        catch (error) { failure(s, error); apply.disabled = false; }
      });
      box.append(apply);
    } else if (run.applied_at) box.append(node("p", tr("loop_applied"), "loop-applied"));
  }
  // Automatic learning from chat (0.341.0): what Javis changed on its own, brain-wide, with undo. Nothing to start.
  async function autoLearned(s) {
    let data;
    try { data = await request(s, "/auto-learning"); }
    catch (error) { return; } // older server or refused: no section
    if (!alive(s)) return;
    const box = s.auto; box.replaceChildren(node("h3", tr("auto_title")));
    info(box, tr("auto_hint"));
    const stats = data.stats || {};
    const open = Object.values(stats.mistakes || {}).reduce((a, b) => a + b, 0);
    box.append(node("p", tr("auto_stats").replace("{p}", String(stats.pending || 0)).replace("{m}", String(open)), "auto-stats"));
    const rows = (data.history || []).slice(0, 10);
    if (!rows.length) { box.append(node("p", tr("auto_empty"), "auto-empty")); return; }
    for (const row of rows) {
      const line = node("div", null, "auto-run-" + row.id);
      const what = tr("auto_kind_" + row.kind) + " " + row.slug + (row.kind === "workflow" ? " #" + (row.step + 1) : "");
      const state = row.undone_at ? "auto_undone" : row.applied ? "auto_applied" : row.proposed ? "auto_proposed" : row.state === "running" ? "auto_running"
        : row.state === "failed" ? "auto_failed" : row.state === "skipped" ? "auto_skipped" : "auto_kept";
      line.append(node("p", new Date(row.started_at * 1000).toLocaleString() + " · " + what + " · " + tr(state)));
      if (row.proposed) line.append(button(tr("auto_apply"), "auto-apply-" + row.id, async () => {
        try { await write(s, "/auto-learning/" + encodeURIComponent(row.id) + "/apply", {}, "auto-apply-" + row.id);
          s.status.textContent = tr("auto_apply_done"); await autoLearned(s); }
        catch (error) { failure(s, error); }
      }));
      if (row.applied && !row.undone_at) line.append(button(tr("auto_undo"), "auto-undo-" + row.id, async () => {
        try { await write(s, "/auto-learning/" + encodeURIComponent(row.id) + "/undo", {}, "auto-undo-" + row.id);
          s.status.textContent = tr("auto_undo_done"); await autoLearned(s); }
        catch (error) { failure(s, error); }
      }));
      box.append(line);
    }
  }
  async function open({brain, slug, isCurrent}) {
    const s = shell(brain, slug, isCurrent);
    s.auto = node("div", null, "auto-learning"); s.panel.append(s.auto);
    await autoLearned(s);
    s.loop = node("div", null, "self-learning"); s.panel.append(s.loop);
    await selfLearning(s);
    const contextLabel = node("label", tr("context")); s.choose = node("select", null, "context"); contextLabel.append(s.choose); s.panel.append(contextLabel);
    s.prepare = button(tr("load_baseline"), "load-baseline", () => baseline(s)); s.prepare.disabled = true; s.panel.append(s.prepare);
    s.panel.append(button(tr("capture"), "capture", async () => {
      if (!alive(s)) return;
      invalidate(s); s.prepare.disabled = true;
      try { await write(s, "/improvement-targets/capture", {kind:"skill",slug:s.slug}, "capture"); await load(s); }
      catch (error) { failure(s, error); }
    }));
    s.list = node("div"); s.form = node("div"); s.review = node("div"); s.applied = node("div", null, "activations");
    s.panel.append(s.list, s.applied, s.form, s.review);
    s.experimentArea = node("div"); s.panel.append(s.experimentArea);
    const artifacts = node("details"); artifacts.append(node("summary", tr("artifact")));
    const trial = field(artifacts, "trial_id", "input"); trial.type = "text";
    const attempt = field(artifacts, "attempt", "input"); attempt.value = "1"; attempt.min = "1";
    artifacts.append(button(tr("review_artifact"), "review-artifact", () => {
      if (alive(s) && trial.value.trim() && Number.isSafeInteger(Number(attempt.value)) && Number(attempt.value) > 0) {
        return openArtifact({brain:s.brain,trialId:trial.value.trim(),attempt:Number(attempt.value),isCurrent:s.isCurrent});
      }
      failure(s, {status:400});
    }));
    s.panel.append(artifacts);
    await load(s);
  }
  async function openArtifact({brain, trialId, attempt, isCurrent}) {
    const s = shell(brain, "", isCurrent);
    try {
      const value = (await request(s, "/improvement-trials/" + encodeURIComponent(trialId) + "/artifact-review", {attempt})).review;
      const bytes = await exact(value.artifact);
      const fixtures = [];
      for (const entry of value.fixtures) fixtures.push([entry, await exact({text:entry.text,hash:entry.fixture_hash,byte_size:entry.byte_size})]);
      if (!alive(s)) return;
      s.panel.append(node("h3", tr("task")), node("pre", value.task), node("h3", tr("contract")), node("pre", JSON.stringify(value.contract, null, 2)));
      content(s, s.panel, tr("artifact"), value.artifact, bytes, "artifact");
      for (let i = 0; i < fixtures.length; i++) {
        const [entry, raw] = fixtures[i];
        const metadata = Object.fromEntries(["source_ref", "source_version", "timezone", "data_period", "cutoff", "schema"].map(key=>[key, entry[key]]));
        s.panel.append(node("pre", JSON.stringify(metadata, null, 2), "fixture-" + i + "-metadata"));
        content(s, s.panel, tr("fixture"), {text:entry.text,hash:entry.fixture_hash,byte_size:entry.byte_size}, raw, "fixture-" + i);
      }
      s.status.textContent = tr("artifact_review_only");
    } catch (error) { failure(s, error); }
  }
  window.JavisImprovementCandidates = {open, openArtifact, close};
})();
