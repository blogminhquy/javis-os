/* branding.js - đổi logo/avatar + cấu hình tên miền riêng (HTTPS).
   Tách riêng khỏi app.js (file đó có encoding hỗn hợp, sửa dễ hỏng). Vanilla DOM, không cần Alpine. */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  // Cả thẻ tên miền (wizard 3 bước + badge DNS/SSL) lẫn dòng trạng thái ảnh đại diện đều
  // được VẼ MỘT LẦN bằng JS, nên đổi ngôn ngữ giao diện là chúng đứng nguyên tiếng cũ.
  // Nhớ lại dữ liệu đã vẽ để lượt "javis:i18n" dựng lại y hệt bằng từ điển mới, khỏi phải
  // gọi lại /domain/status (một lượt tra DNS thật, chậm và vô cớ).
  var _domCache = null;      // JSON /domain/status lần vẽ gần nhất; null = chưa vẽ lần nào
  var _logoCustom = null;    // true/false = đang dùng ảnh riêng / ảnh mặc định; null = chưa biết

  function setStatus(id, msg, isErr) {
    var el = $(id);
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "var(--red)" : "";
  }

  function esc(s) { return (s || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }

  function _injectDomCss() {
    if (document.getElementById("domCss")) return;
    var s = document.createElement("style"); s.id = "domCss";
    s.textContent =
      // Ô nhập: flex-basis auto + grow, KHÔNG dùng flex:1 (basis 0). Với basis 0 thì cỡ
      // mong muốn của ô nhập bằng 0, nên hàng thiếu chỗ là nó teo hết còn nút giữ nguyên.
      // Nút để width:auto (style.css cho nút trong quick-set width:100%, vào flex row là
      // nó đòi trọn hàng). Ô nhập cũng tự khai kiểu vì popover không có kiểu input chung.
      // KHÔNG đặt align-items:center: ở màn hẹp hàng này xoay thành cột, mà center thì con
      // co về bề ngang nội dung thay vì giãn hết hàng - ô nhập lại bé. Để mặc định stretch.
      ".dom-field{display:flex;gap:6px}" +
      ".dom-field input{flex:1 1 auto;min-width:0;width:auto;background:var(--field-bg);" +
      "border:1px solid var(--border);color:var(--text);border-radius:7px;padding:8px 10px;font-size:14px}" +
      ".dom-field input:focus{outline:none;border-color:var(--accent)}" +
      ".dom-field .s-btn{flex:0 0 auto;width:auto;white-space:nowrap}" +
      ".dom-status{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}" +
      ".dom-badge{font-size:12.5px;padding:3px 10px;border-radius:20px;border:1px solid var(--hairline);background:var(--surface-2);color:var(--text2);white-space:nowrap}" +
      ".dom-badge.ok{background:var(--ok-wash);border-color:var(--green);color:var(--green)}" +
      ".dom-badge.warn{background:var(--warn-wash);border-color:var(--warn-line);color:var(--warn-ink)}" +
      ".dom-badge.bad{background:var(--danger-wash);border-color:var(--danger-line);color:var(--red)}" +
      // Hai nút chia đôi hàng: phải khai flex CHO CẢ HAI. Trước đây chỉ .s-btn có flex:1,
      // nút ghost giữ width:100% nên nó nuốt hàng còn nút kia teo - cùng một lỗi.
      ".dom-ssl{display:flex;gap:6px;margin-top:9px}" +
      ".dom-ssl .s-btn,.dom-ssl .s-btn-ghost{flex:1 1 0;width:auto;white-space:nowrap}" +
      ".dom-guide{margin-top:10px;font-size:13px;line-height:1.55;color:var(--text);display:flex;flex-direction:column;gap:8px}" +
      ".dom-step{display:grid;grid-template-columns:25px minmax(0,1fr);gap:8px;padding:9px 10px;background:var(--surface-1);border:1px solid var(--hairline);border-radius:9px}" +
      ".dom-step.done{border-color:var(--ok-line);background:var(--ok-wash)}" +
      ".dom-step.warn{border-color:var(--warn-line);background:var(--warn-wash)}" +
      ".dom-step-num{width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:var(--hairline);font-weight:700}" +
      ".dom-step.done .dom-step-num{background:var(--ok-wash);color:var(--green)}" +
      ".dom-step p{margin:3px 0 0;color:var(--text3)}.dom-step code{display:inline-block;margin-top:5px;background:var(--info-wash);padding:3px 7px;border-radius:5px;font-size:12px;overflow-wrap:anywhere}" +
      ".dom-copy{margin:7px 0 0;padding:5px 9px;border:1px solid var(--hairline);border-radius:7px;background:var(--surface-2);color:var(--text);cursor:pointer}" +
      ".dom-copy:hover{border-color:var(--info-line);color:var(--info-ink)}" +
      ".dom-open{display:inline-block;margin-top:6px;color:var(--green);text-decoration:none}.dom-open:hover{text-decoration:underline}" +
      ".dom-docs{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;padding-top:9px;border-top:1px solid var(--surface-3)}" +
      ".dom-docs a{font-size:12.5px;color:var(--link-ink);text-decoration:none}.dom-docs a:hover{text-decoration:underline}" +
      "@media(max-width:600px){.dom-field,.dom-ssl{flex-direction:column}.dom-field .s-btn,.dom-ssl .s-btn,.dom-ssl .s-btn-ghost{width:100%}}";
    document.head.appendChild(s);
  }

  // Đổi src mọi ảnh logo (header, thanh bên, màn đăng nhập, preview) để thấy ảnh mới ngay.
  function bustLogos() {
    var v = "/brand-logo?v=" + Date.now();
    document.querySelectorAll('img[src^="/brand-logo"]').forEach(function (img) { img.src = v; });
  }

  // ---------- Logo / avatar ----------
  async function uploadLogo(file) {
    if (!file) return;
    setStatus("brandLogoStatus", window.t("brand.uploading"), false);
    try {
      var fd = new FormData();
      fd.append("file", file);
      var r = await fetch("/branding/logo", { method: "POST", body: fd });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("brandLogoStatus", j.error || window.t("brand.upload_failed"), true); return; }
      bustLogos();
      _logoCustom = true;
      setStatus("brandLogoStatus", window.t("brand.image_updated"), false);
    } catch (e) {
      setStatus("brandLogoStatus", window.t("brand.net_err_upload"), true);
    }
  }

  async function resetLogo() {
    setStatus("brandLogoStatus", window.t("brand.restoring"), false);
    try {
      var r = await fetch("/branding/logo/reset", { method: "POST" });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("brandLogoStatus", (j && j.error) || window.t("brand.restore_failed"), true); return; }
      bustLogos();
      _logoCustom = false;
      setStatus("brandLogoStatus", window.t("brand.image_reset"), false);
    } catch (e) {
      setStatus("brandLogoStatus", window.t("app.err_net"), true);
    }
  }

  // ---------- Tên miền & SSL ----------
  function _badge(id, text, cls) {
    var e = $(id); if (!e) return;
    e.textContent = text; e.className = "dom-badge " + (cls || "");
  }

  // Vẽ trạng thái tên miền + SSL từ dữ liệu /domain/status.
  function renderDomainStatus(j) {
    _domCache = j || { domain: "" };
    var row = $("domStatusRow"), sslRow = $("domSslRow"), guide = $("domainGuide");
    if (!j || !j.domain) {
      if (row) row.style.display = "none";
      if (sslRow) sslRow.style.display = "none";
      if (guide) guide.style.display = "none";
      setStatus("domainStatus", window.t("brand.no_domain"), false);
      return;
    }
    if (row) row.style.display = "flex";
    if (sslRow) sslRow.style.display = "flex";
    var hostinger = j.deployment_target === "hostinger";
    if (j.dns_ok) _badge("dnsBadge", window.t("brand.dns_ok"), "ok");
    else if (j.dns_ip) _badge("dnsBadge", window.t("brand.dns_wrong_ip", { ip: j.dns_ip }), "bad");
    else _badge("dnsBadge", window.t("brand.dns_none"), "warn");
    if (j.ssl_active) _badge("sslBadge", window.t("brand.ssl_on"), "ok");
    else if (hostinger) _badge("sslBadge", window.t("brand.ssl_hostinger"), "warn");
    else if (j.ssl_enabled) _badge("sslBadge", window.t("brand.ssl_pending"), "warn");
    else _badge("sslBadge", window.t("brand.ssl_off"), "");
    var tog = $("sslToggle");
    if (tog) {
      tog.style.display = hostinger ? "none" : "";
      tog.textContent = j.ssl_active ? window.t("brand.reactivate") : window.t("qs.ssl_on");
    }
    var check = $("checkDomain");
    if (check) check.textContent = window.t("qs.recheck");
    var ip = j.server_ip || window.t("brand.vps_ip_placeholder");
    var dnsRecord = "A · " + j.domain + " · " + ip;
    var steps = '<div class="dom-step done"><span class="dom-step-num">' + ic("check") + '</span><div><b>1. ' + window.t("brand.step1_title") + '</b><p>' + window.t("brand.step1_desc") + ' <code>' + esc(j.domain) + '</code>.</p></div></div>';
    steps += '<div class="dom-step ' + (j.dns_ok ? "done" : "warn") + '"><span class="dom-step-num">' + (j.dns_ok ? ic("check") : "2") + '</span><div><b>2. ' + window.t("brand.step2_title") + '</b>' +
      '<p>' + (j.dns_ok ? window.t("brand.step2_ok") : window.t("brand.step2_todo")) + '</p>' +
      '<code>' + esc(dnsRecord) + '</code><br><button class="dom-copy" type="button" data-copy="' + esc(dnsRecord) + '">' + window.t("brand.copy_record") + '</button></div></div>';
    if (hostinger) {
      var envLine = "DOMAIN_NAME=" + j.domain;
      var route = j.route_domain && j.route_domain !== "localhost" ? j.route_domain : window.t("brand.route_unset");
      steps += '<div class="dom-step ' + (j.ssl_active && !j.requires_redeploy ? "done" : "warn") + '"><span class="dom-step-num">' + (j.ssl_active && !j.requires_redeploy ? ic("check") : "3") + '</span><div><b>3. ' + window.t("brand.step3_hostinger_title") + '</b>' +
        '<p>' + window.t("brand.step3_hostinger_a") + ' <b>Redeploy</b>. ' + window.t("brand.step3_hostinger_b") + ' <b>' + esc(route) + '</b>. ' + window.t("brand.step3_hostinger_c") + '</p>' +
        '<code>' + esc(envLine) + '</code><br><button class="dom-copy" type="button" data-copy="' + esc(envLine) + '">' + window.t("brand.copy_env") + '</button></div></div>';
    } else {
      steps += '<div class="dom-step ' + (j.ssl_active ? "done" : (j.dns_ok ? "warn" : "")) + '"><span class="dom-step-num">' + (j.ssl_active ? ic("check") : "3") + '</span><div><b>3. ' + window.t("brand.step3_title") + '</b>' +
        '<p>' + (j.ssl_active ? window.t("brand.ssl_active_desc") : window.t("brand.ssl_hint")) + '</p>' +
        (j.deploy_mode === "docker" && !j.ssl_active ? '<code>docker compose -f docker-compose.yml -f docker-compose.https.yml up -d</code>' : "") + '</div></div>';
    }
    if (j.ssl_active) steps += '<a class="dom-open" href="https://' + esc(j.domain) + '" target="_blank" rel="noopener">' + window.t("brand.open") + ' https://' + esc(j.domain) + ' ↗</a>';
    if (guide) { guide.innerHTML = steps; guide.style.display = "block"; }
    if (j.ssl_active) setStatus("domainStatus", window.t("brand.https_running", { domain: j.domain }), false);
    else if (hostinger && j.requires_redeploy) setStatus("domainStatus", window.t("brand.saved_needs_redeploy"), false);
    else setStatus("domainStatus", j.ssl_reason || "", !!(j.dns_ip && !j.dns_ok));
  }

  async function saveDomain() {
    var input = $("setDomain");
    var d = ((input && input.value) || "").trim();
    var btn = $("saveDomain"); if (btn) btn.disabled = true;
    setStatus("domainStatus", window.t("brand.saving_checking"), false);
    try {
      var fd = new FormData(); fd.append("domain", d);
      var r = await fetch("/domain", { method: "POST", body: fd });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("domainStatus", j.error || window.t("brand.save_failed"), true); return; }
      if (j.domain) { setStatus("domainStatus", window.t("brand.saved_checking_dns"), false); checkDomain(); }
      else { renderDomainStatus({ domain: "" }); setStatus("domainStatus", window.t("brand.domain_removed"), false); }
    } catch (e) { setStatus("domainStatus", window.t("brand.net_err_save"), true); }
    finally { if (btn) btn.disabled = false; }
  }

  async function checkDomain() {
    setStatus("domainStatus", window.t("settings.checking"), false);
    try {
      var r = await fetch("/domain/status");
      var j = await r.json().catch(function () { return {}; });
      renderDomainStatus(j);
    } catch (e) { setStatus("domainStatus", window.t("brand.check_failed"), true); }
  }

  // Bật SSL: lưu ý định + chủ động xin chứng chỉ (server probe HTTPS), rồi làm mới trạng thái.
  async function toggleSsl() {
    var d = (($("setDomain") || {}).value || "").trim();
    if (!d) { setStatus("domainStatus", window.t("brand.enter_domain_first"), true); return; }
    var tog = $("sslToggle");
    if (tog) tog.disabled = true;
    setStatus("domainStatus", window.t("brand.enabling_ssl"), false);
    try {
      var fd = new FormData(); fd.append("enabled", "1");
      var r = await fetch("/domain/ssl", { method: "POST", body: fd });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("domainStatus", j.error || window.t("brand.ssl_failed"), true); return; }
      await checkDomain();
      if (!j.ssl_active) {
        var extra = j.hint_cmd ? (" " + window.t("brand.run_on_vps") + " " + j.hint_cmd) : "";
        setStatus("domainStatus", (j.ssl_reason || window.t("brand.ssl_not_on")) + "." + extra, true);
      }
    } catch (e) { setStatus("domainStatus", window.t("brand.net_err_ssl"), true); }
    finally { if (tog) tog.disabled = false; }
  }

  // Nạp giá trị hiện tại khi mở Cài đặt.
  async function loadExtras() {
    try {
      var r = await fetch("/settings");
      var j = await r.json();
      var dom = (j.domain || {}).custom || "";
      var di = $("setDomain"); if (di) di.value = dom;
      var b = j.branding || {};
      _logoCustom = !!b.logo_ext;
      setStatus("brandLogoStatus", _logoCustom ? window.t("brand.using_custom_image") : window.t("brand.using_default_image"), false);
      if (dom) checkDomain(); else renderDomainStatus({ domain: "" });
    } catch (e) { /* im lặng */ }
  }

  function bind() {
    _injectDomCss();
    var sBtn = $("settingsBtn");
    if (sBtn) sBtn.addEventListener("click", function () { setTimeout(loadExtras, 50); });

    var li = $("brandLogoInput");
    if (li) li.addEventListener("change", function (e) {
      var f = e.target.files && e.target.files[0];
      if (f) uploadLogo(f);
      e.target.value = "";   // cho phép chọn lại cùng file
    });
    var lr = $("brandLogoReset");
    if (lr) lr.addEventListener("click", resetLogo);

    var sd = $("saveDomain");
    if (sd) sd.addEventListener("click", saveDomain);
    var di = $("setDomain");
    if (di) di.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); saveDomain(); }
    });
    var cd = $("checkDomain");
    if (cd) cd.addEventListener("click", checkDomain);
    var stg = $("sslToggle");
    if (stg) stg.addEventListener("click", toggleSsl);
    var dg = $("domainGuide");
    if (dg) dg.addEventListener("click", async function (e) {
      var btn = e.target.closest("[data-copy]"); if (!btn) return;
      var text = btn.getAttribute("data-copy") || "";
      try {
        await navigator.clipboard.writeText(text);
        var old = btn.textContent; btn.innerHTML = window.t("brand.copied") + " " + ic("check", { cls: "ic-ok" });
        setTimeout(function () { btn.textContent = old; }, 1300);
      } catch (err) {
        setStatus("domainStatus", window.t("brand.copy_manual"), true);
      }
    });

    // Controls giờ nằm trong sidebar (luôn hiển thị) → nạp giá trị hiện tại ngay khi tải trang.
    loadExtras();
  }

  // Đổi ngôn ngữ giao diện (hoặc từ điển vừa nạp xong): dựng lại phần chữ do JS vẽ.
  // Chỉ dựng lại thứ đã từng vẽ, để không tự dưng in "Chưa đặt tên miền" lên một trang
  // chưa hề mở phần tên miền.
  window.addEventListener("javis:i18n", function () {
    if (_logoCustom !== null) {
      setStatus("brandLogoStatus", _logoCustom ? window.t("brand.using_custom_image") : window.t("brand.using_default_image"), false);
    }
    if (_domCache) renderDomainStatus(_domCache);
  });

  // Cho trang Cài đặt (console.js) gọi nạp lại giá trị avatar/tên miền khi mở trang.
  window.__javisRefreshExtras = loadExtras;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
