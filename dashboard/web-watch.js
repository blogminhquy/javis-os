/* Tab "Theo dõi trang" của trang Việc định kỳ (0.239.0): canh một trang web mà không tốn token.
 *
 * Máy chủ (server/web_watch.py) tải trang theo lịch và so chữ, chỉ báo khi có chuyện mới: trang đổi, xuất hiện một
 * cụm chữ, hoặc có giá dưới ngưỡng. Tab này tạo mục theo dõi, liệt kê, tạm dừng, canh ngay và xoá.
 *
 * Hàm vẽ là hàm thuần (test bằng node); `mount` nối API. Không dùng ký tự gạch ngang dài ở bất kỳ đâu. */
(function () {
  "use strict";

  function tw(key, vars) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(key, vars) : key;
    if (vars) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, name) {
        return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m;
      });
    }
    return s;
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var ic = function (n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; };
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(tw("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }

  var COND_KEY = { change: "ww.cond_change", contains: "ww.cond_contains", price_below: "ww.cond_price" };
  var STATUS_KEY = { active: "ww.st_active", paused: "ww.st_paused", stopped: "ww.st_stopped" };

  function fmtTime(ts) {
    if (!ts) return "-";
    var d = new Date(ts * 1000);
    var p = function (n) { return String(n).padStart(2, "0"); };
    return p(d.getHours()) + ":" + p(d.getMinutes()) + " " + p(d.getDate()) + "/" + p(d.getMonth() + 1);
  }

  /* Một thẻ mục theo dõi. Trả chuỗi HTML đã escape. */
  function watchHtml(w) {
    var dk = tw(COND_KEY[w.cond] || "ww.cond_change") + (w.value ? ': "' + w.value + '"' : "");
    var paused = w.status !== "active";
    return '<div class="wf-card ww-card" data-id="' + esc(w.id) + '">'
      + "<b>" + ic(paused ? "circle-stop" : "eye") + " " + esc(w.title) + "</b>"
      + '<div class="ww-url"><a href="' + esc(w.url) + '" target="_blank" rel="noopener noreferrer">' + esc(w.url) + "</a></div>"
      + '<div class="ww-meta">' + esc(dk) + " · " + esc(tw("ww.every", { n: w.interval_min })) + " · "
      + esc(tw(STATUS_KEY[w.status] || "ww.st_active")) + " · " + esc(tw("ww.checked", { n: w.checks || 0, t: fmtTime(w.last_at) }))
      + (w.summarize ? " · " + esc(tw("ww.ai_on")) : "")
      + (w.login_id ? " · " + ic("key") + " " + esc(tw("ww.login")) : "") + "</div>"
      + (w.last_alert ? '<div class="ww-alert">' + esc(String(w.last_alert).slice(0, 300)) + "</div>" : "")
      + (w.last_error ? '<div class="ww-err">' + esc(tw("ww.last_error")) + " " + esc(String(w.last_error).slice(0, 200)) + "</div>" : "")
      + '<div class="wf-actions ww-actions">'
      + '<button class="s-btn-ghost" data-act="check_now">' + esc(tw("ww.check_now")) + "</button>"
      + '<button class="s-btn-ghost" data-act="' + (paused ? "resume" : "pause") + '">' + esc(tw(paused ? "ww.resume" : "ww.pause")) + "</button>"
      + '<button class="s-btn-ghost ww-del" data-act="delete">' + esc(tw("ww.delete")) + "</button>"
      + "</div></div>";
  }

  function formHtml() {
    return '<div class="ww-form">'
      + '<div class="si-field"><label>' + esc(tw("ww.url")) + '</label><input id="wwUrl" type="url" placeholder="' + esc(tw("ww.url_ph")) + '"></div>'
      // 0.251.0: a page behind a sign-in uses one from the Login vault. Shown only when the vault has one.
      + '<div class="si-field" id="wwLoginWrap" hidden><label>' + esc(tw("ww.login")) + '</label>'
      + '<select id="wwLogin" class="ww-login"><option value="">' + esc(tw("ww.login_none")) + "</option></select></div>"
      + '<div class="si-field"><label>' + esc(tw("ww.cond")) + '</label><div class="si-row" id="wwCond">'
      + '<button class="si-chip sel" data-c="change">' + esc(tw("ww.cond_change")) + "</button>"
      + '<button class="si-chip" data-c="contains">' + esc(tw("ww.cond_contains")) + "</button>"
      + '<button class="si-chip" data-c="price_below">' + esc(tw("ww.cond_price")) + "</button></div></div>"
      + '<div class="si-field" id="wwValWrap" hidden><label id="wwValLabel">' + esc(tw("ww.value_text")) + "</label>"
      + '<input id="wwVal"></div>'
      + '<div class="si-row ww-row">'
      + '<div class="si-field"><label>' + esc(tw("ww.title")) + '</label><input id="wwTitle" placeholder="' + esc(tw("ww.title_ph")) + '"></div>'
      + '<div class="si-field"><label>' + esc(tw("ww.interval")) + '</label><input id="wwEvery" type="number" min="5" max="10080" value="60"></div>'
      + "</div>"
      + '<label class="ww-check"><input type="checkbox" id="wwAi"> ' + esc(tw("ww.ai")) + "</label>"
      + '<div class="si-actions"><button class="s-btn" id="wwSave">' + esc(tw("ww.save")) + '</button><span class="ww-msg" id="wwMsg"></span></div>'
      + "</div>";
  }

  async function api(url, body) {
    try {
      var r = await fetch(url, body === undefined ? undefined : {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      return await r.json();
    } catch (e) { return { ok: false, error: tw("ww.err_net") }; }
  }

  function mount(box, brainFn) {
    if (!box) return;
    var brain = function () { try { return (brainFn && brainFn()) || "brain"; } catch (e) { return "brain"; } };
    var cond = "change";
    box.innerHTML = '<div class="lp-group">'
      + '<div class="ww-head"><span>' + ic("eye") + " " + esc(tw("ww.head")) + infoBtn() + "</span></div>"
      + infoBody(esc(tw("ww.intro")))
      + '<div class="ww-warn" id="wwWarn" hidden></div>'
      + formHtml()
      + '<div id="wwList"></div></div>';
    var q = function (s) { return box.querySelector(s); };

    box.querySelectorAll("#wwCond .si-chip").forEach(function (b) {
      b.onclick = function () {
        cond = b.dataset.c;
        box.querySelectorAll("#wwCond .si-chip").forEach(function (x) { x.classList.toggle("sel", x === b); });
        q("#wwValWrap").hidden = cond === "change";
        q("#wwValLabel").textContent = tw(cond === "price_below" ? "ww.value_price" : "ww.value_text");
        q("#wwVal").placeholder = cond === "price_below" ? tw("ww.value_price_ph") : tw("ww.value_text_ph");
      };
    });

    async function load() {
      var d = await api("/watch?brain=" + encodeURIComponent(brain()));
      var warn = q("#wwWarn");
      if (warn) {
        warn.hidden = !d.channels_missing;
        warn.textContent = d.channels_missing ? tw("ww.no_channel", { why: d.channels_missing }) : "";
      }
      var host = q("#wwList");
      if (!host) return;
      var list = d.watches || [];
      host.innerHTML = list.length ? list.map(watchHtml).join("") : '<div class="empty">' + esc(tw("ww.empty")) + "</div>";
      host.querySelectorAll(".ww-actions button[data-act]").forEach(function (b) {
        b.onclick = async function () {
          var act = b.dataset.act;
          if (act === "delete" && !confirm(tw("ww.confirm_delete"))) return;
          b.disabled = true;
          var r = await api("/watch/action", { id: b.closest("[data-id]").dataset.id, action: act });
          b.disabled = false;
          if (!r.ok) { alert(r.error || tw("ww.err_net")); return; }
          load();
        };
      });
    }

    // Sign-ins Javis may use (Login vault, 0.251.0). /logins needs a dashboard session; any error just hides the field.
    (async function () {
      var d = await api("/logins");
      var list = (d && d.ok && d.logins || []).filter(function (x) { return x.allow_ai; });
      var sel = q("#wwLogin");
      if (!sel || !list.length) return;
      sel.innerHTML = '<option value="">' + esc(tw("ww.login_none")) + "</option>" + list.map(function (x) {
        return '<option value="' + esc(x.id) + '">' + esc(x.name) + " (" + esc((x.domains || []).slice(0, 2).join(", ")) + ")</option>";
      }).join("");
      q("#wwLoginWrap").hidden = false;
    })();

    q("#wwSave").onclick = async function () {
      var msg = q("#wwMsg");
      var btn = q("#wwSave");
      btn.disabled = true;
      msg.textContent = "";
      var r = await api("/watch", {
        brain: brain(), url: q("#wwUrl").value.trim(), cond: cond, value: q("#wwVal").value.trim(),
        title: q("#wwTitle").value.trim(), interval_min: Number(q("#wwEvery").value || 60), summarize: q("#wwAi").checked,
        login_id: (q("#wwLogin") && q("#wwLogin").value) || "" });
      btn.disabled = false;
      if (!r.ok) { msg.textContent = r.error || tw("ww.err_net"); return; }
      q("#wwUrl").value = ""; q("#wwVal").value = ""; q("#wwTitle").value = "";
      msg.textContent = tw("ww.saved");
      load();
    };
    load();
  }

  var api_ = { mount: mount, watchHtml: watchHtml, formHtml: formHtml };
  if (typeof window !== "undefined") window.JavisWebWatch = api_;
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
})();
