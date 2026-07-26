/* branding.js - đổi logo/avatar + cấu hình tên miền riêng (HTTPS).
   Tách riêng khỏi app.js (file đó có encoding hỗn hợp, sửa dễ hỏng). Vanilla DOM, không cần Alpine. */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function setStatus(id, msg, isErr) {
    var el = $(id);
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isErr ? "#ff8a8a" : "";
  }

  function esc(s) { return (s || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }

  function _injectDomCss() {
    if (document.getElementById("domCss")) return;
    var s = document.createElement("style"); s.id = "domCss";
    s.textContent =
      ".dom-field{display:flex;gap:6px}.dom-field input{flex:1;min-width:0}" +
      ".dom-status{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}" +
      ".dom-badge{font-size:12.5px;padding:3px 10px;border-radius:20px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#aebbd6;white-space:nowrap}" +
      ".dom-badge.ok{background:rgba(44,122,75,.16);border-color:#2c7a4b;color:#8fe3ad}" +
      ".dom-badge.warn{background:rgba(210,160,60,.14);border-color:rgba(210,160,60,.5);color:#f0cd94}" +
      ".dom-badge.bad{background:rgba(210,70,70,.14);border-color:rgba(210,70,70,.5);color:#ffb0b0}" +
      ".dom-ssl{display:flex;gap:6px;margin-top:9px}.dom-ssl .s-btn{flex:1}" +
      ".dom-guide{margin-top:10px;font-size:13px;line-height:1.55;color:#cdd8ee;display:flex;flex-direction:column;gap:8px}" +
      ".dom-step{display:grid;grid-template-columns:25px minmax(0,1fr);gap:8px;padding:9px 10px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:9px}" +
      ".dom-step.done{border-color:rgba(44,122,75,.5);background:rgba(44,122,75,.09)}" +
      ".dom-step.warn{border-color:rgba(210,160,60,.45);background:rgba(210,160,60,.07)}" +
      ".dom-step-num{width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;border-radius:50%;background:rgba(255,255,255,.08);font-weight:700}" +
      ".dom-step.done .dom-step-num{background:rgba(63,220,134,.2);color:#8fe3ad}" +
      ".dom-step p{margin:3px 0 0;color:#9caac3}.dom-step code{display:inline-block;margin-top:5px;background:rgba(120,180,255,.13);padding:3px 7px;border-radius:5px;font-size:12px;overflow-wrap:anywhere}" +
      ".dom-copy{margin:7px 0 0;padding:5px 9px;border:1px solid rgba(255,255,255,.14);border-radius:7px;background:rgba(255,255,255,.04);color:#cdd8ee;cursor:pointer}" +
      ".dom-copy:hover{border-color:rgba(120,180,255,.55);color:#fff}" +
      ".dom-open{display:inline-block;margin-top:6px;color:#8fe3ad;text-decoration:none}.dom-open:hover{text-decoration:underline}" +
      ".dom-docs{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px;padding-top:9px;border-top:1px solid rgba(255,255,255,.07)}" +
      ".dom-docs a{font-size:12.5px;color:#a9c5ff;text-decoration:none}.dom-docs a:hover{text-decoration:underline}" +
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
    setStatus("brandLogoStatus", "Đang tải lên…", false);
    try {
      var fd = new FormData();
      fd.append("file", file);
      var r = await fetch("/branding/logo", { method: "POST", body: fd });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("brandLogoStatus", j.error || "Tải lên thất bại", true); return; }
      bustLogos();
      setStatus("brandLogoStatus", "Đã cập nhật ảnh ✓", false);
    } catch (e) {
      setStatus("brandLogoStatus", "Lỗi mạng khi tải lên", true);
    }
  }

  async function resetLogo() {
    setStatus("brandLogoStatus", "Đang khôi phục…", false);
    try {
      var r = await fetch("/branding/logo/reset", { method: "POST" });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("brandLogoStatus", (j && j.error) || "Không khôi phục được", true); return; }
      bustLogos();
      setStatus("brandLogoStatus", "Đã về ảnh mặc định.", false);
    } catch (e) {
      setStatus("brandLogoStatus", "Lỗi mạng", true);
    }
  }

  // ---------- Tên miền & SSL ----------
  function _badge(id, text, cls) {
    var e = $(id); if (!e) return;
    e.textContent = text; e.className = "dom-badge " + (cls || "");
  }

  // Vẽ trạng thái tên miền + SSL từ dữ liệu /domain/status.
  function renderDomainStatus(j) {
    var row = $("domStatusRow"), sslRow = $("domSslRow"), guide = $("domainGuide");
    if (!j || !j.domain) {
      if (row) row.style.display = "none";
      if (sslRow) sslRow.style.display = "none";
      if (guide) guide.style.display = "none";
      setStatus("domainStatus", "Chưa đặt tên miền.", false);
      return;
    }
    if (row) row.style.display = "flex";
    if (sslRow) sslRow.style.display = "flex";
    var hostinger = j.deployment_target === "hostinger";
    if (j.dns_ok) _badge("dnsBadge", "DNS: đã trỏ đúng", "ok");
    else if (j.dns_ip) _badge("dnsBadge", "DNS: sai IP (" + j.dns_ip + ")", "bad");
    else _badge("dnsBadge", "DNS: chưa trỏ", "warn");
    if (j.ssl_active) _badge("sslBadge", "SSL: đang bật", "ok");
    else if (hostinger) _badge("sslBadge", "SSL: qua Hostinger", "warn");
    else if (j.ssl_enabled) _badge("sslBadge", "SSL: đang chờ", "warn");
    else _badge("sslBadge", "SSL: tắt", "");
    var tog = $("sslToggle");
    if (tog) {
      tog.style.display = hostinger ? "none" : "";
      tog.textContent = j.ssl_active ? "Kích hoạt lại" : "Bật SSL";
    }
    var check = $("checkDomain");
    if (check) check.textContent = "Kiểm tra lại";
    var ip = j.server_ip || "(IP máy chủ VPS)";
    var dnsRecord = "A · " + j.domain + " · " + ip;
    var steps = '<div class="dom-step done"><span class="dom-step-num">✓</span><div><b>1. Lưu tên miền</b><p>Javis đã ghi nhận <code>' + esc(j.domain) + '</code>.</p></div></div>';
    steps += '<div class="dom-step ' + (j.dns_ok ? "done" : "warn") + '"><span class="dom-step-num">' + (j.dns_ok ? "✓" : "2") + '</span><div><b>2. Trỏ DNS về VPS</b>' +
      '<p>' + (j.dns_ok ? "Bản ghi A đã trỏ đúng IP máy chủ." : "Tạo hoặc sửa bản ghi này tại nơi quản lý tên miền:") + '</p>' +
      '<code>' + esc(dnsRecord) + '</code><br><button class="dom-copy" type="button" data-copy="' + esc(dnsRecord) + '">Sao chép bản ghi</button></div></div>';
    if (hostinger) {
      var envLine = "DOMAIN_NAME=" + j.domain;
      var route = j.route_domain && j.route_domain !== "localhost" ? j.route_domain : "chưa đặt";
      steps += '<div class="dom-step ' + (j.ssl_active && !j.requires_redeploy ? "done" : "warn") + '"><span class="dom-step-num">' + (j.ssl_active && !j.requires_redeploy ? "✓" : "3") + '</span><div><b>3. Kích hoạt route HTTPS trên Hostinger</b>' +
        '<p>Trong hPanel → VPS → Docker Manager, đặt Environment bên dưới rồi bấm <b>Redeploy</b>. Route hiện tại: <b>' + esc(route) + '</b>. Bước này do Traefik của Hostinger quản lý nên app không thể tự sửa label từ trong container.</p>' +
        '<code>' + esc(envLine) + '</code><br><button class="dom-copy" type="button" data-copy="' + esc(envLine) + '">Sao chép biến</button></div></div>';
    } else {
      steps += '<div class="dom-step ' + (j.ssl_active ? "done" : (j.dns_ok ? "warn" : "")) + '"><span class="dom-step-num">' + (j.ssl_active ? "✓" : "3") + '</span><div><b>3. Bật HTTPS</b>' +
        '<p>' + (j.ssl_active ? "Chứng chỉ HTTPS đang hoạt động." : "Khi DNS đã đúng, bấm Bật SSL để Javis xin chứng chỉ.") + '</p>' +
        (j.deploy_mode === "docker" && !j.ssl_active ? '<code>docker compose -f docker-compose.yml -f docker-compose.https.yml up -d</code>' : "") + '</div></div>';
    }
    if (j.ssl_active) steps += '<a class="dom-open" href="https://' + esc(j.domain) + '" target="_blank" rel="noopener">Mở https://' + esc(j.domain) + ' ↗</a>';
    if (guide) { guide.innerHTML = steps; guide.style.display = "block"; }
    if (j.ssl_active) setStatus("domainStatus", "HTTPS đang chạy cho " + j.domain + ".", false);
    else if (hostinger && j.requires_redeploy) setStatus("domainStatus", "Đã lưu trong Javis; còn bước đặt DOMAIN_NAME và Redeploy trên Hostinger.", false);
    else setStatus("domainStatus", j.ssl_reason || "", !!(j.dns_ip && !j.dns_ok));
  }

  async function saveDomain() {
    var input = $("setDomain");
    var d = ((input && input.value) || "").trim();
    var btn = $("saveDomain"); if (btn) btn.disabled = true;
    setStatus("domainStatus", "Đang lưu và kiểm tra…", false);
    try {
      var fd = new FormData(); fd.append("domain", d);
      var r = await fetch("/domain", { method: "POST", body: fd });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("domainStatus", j.error || "Lưu thất bại", true); return; }
      if (j.domain) { setStatus("domainStatus", "Đã lưu. Đang kiểm tra DNS/SSL…", false); checkDomain(); }
      else { renderDomainStatus({ domain: "" }); setStatus("domainStatus", "Đã xoá tên miền.", false); }
    } catch (e) { setStatus("domainStatus", "Lỗi mạng khi lưu", true); }
    finally { if (btn) btn.disabled = false; }
  }

  async function checkDomain() {
    setStatus("domainStatus", "Đang kiểm tra…", false);
    try {
      var r = await fetch("/domain/status");
      var j = await r.json().catch(function () { return {}; });
      renderDomainStatus(j);
    } catch (e) { setStatus("domainStatus", "Không kiểm tra được (lỗi mạng).", true); }
  }

  // Bật SSL: lưu ý định + chủ động xin chứng chỉ (server probe HTTPS), rồi làm mới trạng thái.
  async function toggleSsl() {
    var d = (($("setDomain") || {}).value || "").trim();
    if (!d) { setStatus("domainStatus", "Hãy nhập và lưu tên miền trước.", true); return; }
    var tog = $("sslToggle");
    if (tog) tog.disabled = true;
    setStatus("domainStatus", "Đang bật SSL và xin chứng chỉ… (có thể mất khoảng 10 giây)", false);
    try {
      var fd = new FormData(); fd.append("enabled", "1");
      var r = await fetch("/domain/ssl", { method: "POST", body: fd });
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) { setStatus("domainStatus", j.error || "Bật SSL thất bại", true); return; }
      await checkDomain();
      if (!j.ssl_active) {
        var extra = j.hint_cmd ? (" Chạy trên VPS: " + j.hint_cmd) : "";
        setStatus("domainStatus", (j.ssl_reason || "Chưa bật được SSL") + "." + extra, true);
      }
    } catch (e) { setStatus("domainStatus", "Lỗi mạng khi bật SSL", true); }
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
      setStatus("brandLogoStatus", b.logo_ext ? "Đang dùng ảnh tùy chỉnh." : "Đang dùng ảnh mặc định.", false);
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
        var old = btn.textContent; btn.textContent = "Đã sao chép ✓";
        setTimeout(function () { btn.textContent = old; }, 1300);
      } catch (err) {
        setStatus("domainStatus", "Không sao chép tự động được; hãy chọn và copy dòng phía trên.", true);
      }
    });

    // Controls giờ nằm trong sidebar (luôn hiển thị) → nạp giá trị hiện tại ngay khi tải trang.
    loadExtras();
  }

  // Cho trang Cài đặt (console.js) gọi nạp lại giá trị avatar/tên miền khi mở trang.
  window.__javisRefreshExtras = loadExtras;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
