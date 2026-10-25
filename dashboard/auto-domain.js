// auto-domain.js - opened by IP, move to this VPS's https link (0.302.0).
//
// Owner 24/10/2026: "khi cài nó tự cài 1 đường dẫn của vps hostinger sẵn để khách hàng mở luôn" (like a Hostinger
// catalog app that opens on <app>.srv<id>.hstgr.cloud). A pasted compose cannot learn the VPS name at install time, so
// hPanel's Open button lands on http://<ip>:7777. This page then asks /domain/auto; the server answers with the https
// link only when that link already answers as THIS Javis over a valid certificate (routes/domain.py), so the move never
// lands on a dead or foreign page. Only from a bare IP over http, never on localhost or a domain. Add ?stay=1 to stay.
(function () {
  "use strict";
  try {
    var h = location.hostname || "";
    var ip = /^\d{1,3}(\.\d{1,3}){3}$/.test(h) || h.indexOf(":") !== -1;
    if (!ip || location.protocol !== "http:" || h === "127.0.0.1") return;
    if (/[?&]stay=1(&|$)/.test(location.search)) {
      try { sessionStorage.setItem("javis.stayIp", "1"); } catch (e) { /* private mode */ }
      return;
    }
    try { if (sessionStorage.getItem("javis.stayIp")) return; } catch (e) { /* private mode */ }
    fetch("/domain/auto", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var url = d && d.url;
        if (typeof url === "string" && /^https:\/\/[a-z0-9.-]+$/i.test(url)) {
          location.replace(url + location.pathname + location.search + location.hash);
        }
      })
      .catch(function () { /* stay on the IP */ });
  } catch (e) { /* stay on the IP */ }
})();
