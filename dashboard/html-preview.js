/* html-preview.js - an .html file opens as a live page first, its code one tab away (0.430.2).

   Owner, 2026-11-01: an .html file opened from a chat link or from the brain should open "like a Claude
   artifact": the PREVIEW by default, with a switch to the code. Before this both file viewers
   (file-editor.js for chat links, console.js for the brain) showed only the source.

   How the preview stays safe and still looks right:
   - It runs in an iframe sandboxed WITHOUT allow-same-origin: the page's scripts run, but in an opaque
     origin that cannot read Javis's cookies, API or storage. Same rule as the chat's HTML artifact.
   - Because of that sandbox, the page cannot load files from the brain by itself (no session cookie).
     So before drawing, inline() fetches each RELATIVE asset (img, video, audio, source, poster,
     stylesheet, script, CSS url()) through the dashboard, with the session, and writes it into the
     document: images as data: URLs, stylesheets and scripts as inline text. Absolute URLs (https://,
     data:, //cdn) are left alone. A runtime fetch("./data.json") inside the page still cannot reach the
     brain; "Open in new tab" or a share link covers that case.
   - The preview draws from the code currently in the editor, so an edit shows up on the next switch to
     Preview without saving first.

   Shared by file-editor.js and console.js. The pure parts (isHtmlPath, resolveRel, isRelativeUrl) are
   tested in node by tests/js/test_html_preview.js. No em dash in this file. */
(function (root) {
  "use strict";

  var SANDBOX = "allow-scripts allow-forms allow-popups allow-modals";
  var MAX_ASSET = 6 * 1024 * 1024;     // one image or script bigger than this stays unresolved
  var MAX_TOTAL = 24 * 1024 * 1024;    // all inlined assets together

  function isHtmlPath(p) {
    return /\.html?$/i.test(String(p || "").split(/[?#]/)[0]);
  }
  // A URL the brain should answer: no scheme, not protocol-relative, not a fragment or a template slot.
  function isRelativeUrl(u) {
    u = String(u || "").trim();
    if (!u || u.charAt(0) === "#" || /^[a-z][a-z0-9+.-]*:/i.test(u) || u.indexOf("//") === 0) return false;
    if (/[{}]|\$\{/.test(u)) return false;
    return true;
  }
  // "img/a.png" seen from "site/index.html" -> "site/img/a.png"; "/x.png" -> "x.png" (brain root).
  function resolveRel(fileDir, url) {
    var clean = String(url || "").split(/[?#]/)[0];
    try { clean = decodeURIComponent(clean); } catch (e) {}
    var parts = clean.charAt(0) === "/" ? [] : String(fileDir || "").split("/").filter(Boolean);
    clean.split("/").forEach(function (seg) {
      if (!seg || seg === ".") return;
      if (seg === "..") { parts.pop(); return; }
      parts.push(seg);
    });
    return parts.join("/");
  }
  function dirOf(path) {
    var p = String(path || "").replace(/\\/g, "/");
    return p.indexOf("/") >= 0 ? p.slice(0, p.lastIndexOf("/")) : "";
  }

  function blobToDataUrl(blob) {
    return new Promise(function (ok, bad) {
      var r = new FileReader();
      r.onload = function () { ok(String(r.result || "")); };
      r.onerror = function () { bad(r.error); };
      r.readAsDataURL(blob);
    });
  }

  // Rewrite relative assets so the sandboxed page shows them. rawUrl(pathFromRoot) -> dashboard URL of that file.
  // Resolves to the finished HTML string; a missing asset is left as it was, never fails the whole preview.
  function inline(code, filePath, rawUrl) {
    if (typeof DOMParser === "undefined" || typeof fetch === "undefined") return Promise.resolve(code);
    var doc;
    try { doc = new DOMParser().parseFromString(String(code || ""), "text/html"); }
    catch (e) { return Promise.resolve(code); }
    var dir = dirOf(filePath);
    var total = 0;
    var cache = {};
    function get(url, asText) {
      var key = (asText ? "t:" : "b:") + url;
      if (cache[key]) return cache[key];
      var path = resolveRel(dir, url);
      cache[key] = fetch(rawUrl(path), { credentials: "same-origin" }).then(function (r) {
        if (!r.ok) return null;
        return asText ? r.text() : r.blob();
      }).then(function (v) {
        if (v == null) return null;
        var size = asText ? v.length : v.size;
        if (size > MAX_ASSET || total + size > MAX_TOTAL) return null;
        total += size;
        return asText ? v : blobToDataUrl(v);
      }).catch(function () { return null; });
      return cache[key];
    }
    // url(...) inside CSS text, resolved against the CSS file's own folder.
    function cssUrls(css, cssDir) {
      var jobs = [];
      var out = String(css).replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, function (m, q, u) {
        if (!isRelativeUrl(u)) return m;
        var mark = "\u0000jvcss" + jobs.length + "\u0000";
        var full = resolveRel(cssDir, u);
        jobs.push(get("/" + full, false).then(function (d) { return d ? 'url("' + d + '")' : m; }));
        return mark;
      });
      return Promise.all(jobs).then(function (vals) {
        return out.replace(/\u0000jvcss(\d+)\u0000/g, function (_, i) { return vals[+i]; });
      });
    }
    var jobs = [];
    Array.prototype.forEach.call(doc.querySelectorAll("img[src],video[src],audio[src],source[src],track[src],input[type=image][src]"), function (el) {
      var u = el.getAttribute("src");
      if (!isRelativeUrl(u)) return;
      jobs.push(get(u, false).then(function (d) { if (d) el.setAttribute("src", d); }));
    });
    Array.prototype.forEach.call(doc.querySelectorAll("img[srcset],source[srcset]"), function (el) {
      // A srcset with relative entries: keep the first one that loads, which is what the preview needs.
      var first = String(el.getAttribute("srcset") || "").split(",")[0].trim().split(/\s+/)[0];
      if (!isRelativeUrl(first)) return;
      jobs.push(get(first, false).then(function (d) { if (d) el.setAttribute("srcset", d); }));
    });
    Array.prototype.forEach.call(doc.querySelectorAll("video[poster]"), function (el) {
      var u = el.getAttribute("poster");
      if (!isRelativeUrl(u)) return;
      jobs.push(get(u, false).then(function (d) { if (d) el.setAttribute("poster", d); }));
    });
    Array.prototype.forEach.call(doc.querySelectorAll("link[rel~=stylesheet][href]"), function (el) {
      var u = el.getAttribute("href");
      if (!isRelativeUrl(u)) return;
      jobs.push(get(u, true).then(function (css) {
        if (css == null) return;
        return cssUrls(css, dirOf(resolveRel(dir, u))).then(function (fixed) {
          var st = doc.createElement("style");
          st.textContent = fixed;
          el.parentNode.replaceChild(st, el);
        });
      }));
    });
    Array.prototype.forEach.call(doc.querySelectorAll("link[rel~=icon][href]"), function (el) {
      var u = el.getAttribute("href");
      if (!isRelativeUrl(u)) return;
      jobs.push(get(u, false).then(function (d) { if (d) el.setAttribute("href", d); }));
    });
    Array.prototype.forEach.call(doc.querySelectorAll("script[src]"), function (el) {
      var u = el.getAttribute("src");
      if (!isRelativeUrl(u)) return;
      jobs.push(get(u, true).then(function (js) {
        if (js == null) return;
        el.removeAttribute("src");
        // A literal </script> inside the file would end the inline block early.
        el.textContent = js.replace(/<\/script/gi, "<\\/script");
      }));
    });
    Array.prototype.forEach.call(doc.querySelectorAll("style"), function (el) {
      if (!/url\(/i.test(el.textContent || "")) return;
      jobs.push(cssUrls(el.textContent, dir).then(function (fixed) { el.textContent = fixed; }));
    });
    Array.prototype.forEach.call(doc.querySelectorAll("[style]"), function (el) {
      var s = el.getAttribute("style") || "";
      if (!/url\(/i.test(s)) return;
      jobs.push(cssUrls(s, dir).then(function (fixed) { el.setAttribute("style", fixed); }));
    });
    if (!jobs.length) return Promise.resolve(code);
    return Promise.all(jobs).then(function () {
      var dt = doc.doctype ? "<!DOCTYPE " + doc.doctype.name + ">\n" : "";
      return dt + doc.documentElement.outerHTML;
    }).catch(function () { return code; });
  }

  // Draw `code` into `host` as a sandboxed page. Returns a Promise of the iframe.
  function render(host, code, filePath, rawUrl) {
    var frame = document.createElement("iframe");
    frame.className = "jv-html-frame";
    frame.setAttribute("sandbox", SANDBOX);
    frame.setAttribute("referrerpolicy", "no-referrer");
    frame.setAttribute("title", filePath ? String(filePath).split("/").pop() : "preview");
    host.innerHTML = "";
    host.appendChild(frame);
    return inline(code, filePath, rawUrl).then(function (html) {
      if (frame.isConnected) frame.srcdoc = html;
      return frame;
    });
  }

  var api = { SANDBOX: SANDBOX, isHtmlPath: isHtmlPath, isRelativeUrl: isRelativeUrl,
    resolveRel: resolveRel, dirOf: dirOf, inline: inline, render: render };
  if (root) root.JavisHtmlPreview = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : null);
