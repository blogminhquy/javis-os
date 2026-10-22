/* note-images.js - insert images into a .md note: PASTE (Ctrl+V) / DROP / toolbar file picker ->
   re-compress -> save into `images/` -> embed `![[images/2026-09-11-15-04-22.webp]]` at the
   caret. Also a drag grip to resize an image right in the render pane, saved as an
   Obsidian-style "|300".

   Runs in BOTH .md editors - the tree editor on the Files page (console.js) and the editor opened
   from chat (file-editor.js) - because both use the same .ne-wys / .ne-src classes, so one set of
   document-level listeners covers both; nothing has to be installed wherever an editor opens.

   WHY IMAGES DO NOT GO INTO `attachments/`: media_gc.media_dirs() treats `attachments/` and
   `inbox/` as a CACHE AREA and by default deletes every file older than 30 days, or when the area
   grows past 300MB. A note image IS referenced by someone - sweeping it means the note later
   shows a grey "image is gone" box, silent data loss with no warning. `images/` is outside the
   sweeper's reach, so images stay for good.

   Compression happens in the BROWSER with a canvas, not on the server: the repo deliberately
   does NOT depend on Pillow (see the note in requirements.txt), and compressing before sending
   also saves bandwidth.

   The file runs BOTH under node (tests require it) and in the browser: the DOM part is wrapped in
   `if (typeof document !== "undefined")`, the pure logic sits at the top level for tests.
   Note: never use the em dash character anywhere. */
(function () {
  "use strict";

  // ---------------------------------------------------------------- limits
  var MAX_EDGE = 1920;           // longest edge after compression (sharp enough for a 2K screen)
  var QUALITY = 0.82;            // webp/jpeg quality: the loss is invisible to the eye
  var MAX_MB = 25;               // bigger than this is refused up front, not compressed in the tab

  function tw(key, params) {
    if (typeof window !== "undefined" && window.t) return window.t(key, params);
    try {
      var s = require("./i18n/vi.json")[key] || key;
      if (params) for (var k in params) s = s.split("{" + k + "}").join(params[k]);
      return s;
    } catch (e) { return key; }
  }

  // ---------------------------------------------------------------- pure functions (testable)
  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  // Image name from LOCAL time (not UTC): in the evening in Vietnam, UTC time would push the name
  // back to the previous day and sorting the folder by name would be off by a day. The owner
  // settled on yyyy-mm-dd-hh-mm-ss.
  function timestampName(d, ext) {
    d = d || new Date();
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + "-" +
      pad2(d.getHours()) + "-" + pad2(d.getMinutes()) + "-" + pad2(d.getSeconds()) +
      (ext || ".png");
  }

  var EXT_BY_TYPE = {
    "image/webp": ".webp", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/gif": ".gif", "image/bmp": ".bmp", "image/avif": ".avif",
    "image/heic": ".heic", "image/heif": ".heif",
  };
  // Extensions the server stores in images/ (files_upload in server/main.py checks the same set).
  var STORABLE_EXTS = [".webp", ".jpg", ".jpeg", ".png", ".gif", ".avif", ".bmp"];
  // Extension from the MIME type; when the type is unknown (the clipboard sometimes sends an
  // empty one) the original name's extension counts only if it is a storable one. Null = unknown.
  function knownExt(mime, origName) {
    var m = String(mime == null ? "" : mime).toLowerCase().split(";")[0].trim();
    if (EXT_BY_TYPE[m]) return EXT_BY_TYPE[m];
    var t = /(\.[a-z0-9]{2,5})$/i.exec(String(origName == null ? "" : origName));
    var x = t ? t[1].toLowerCase() : "";
    return STORABLE_EXTS.indexOf(x) >= 0 ? x : null;
  }
  function extForType(mime, origName) {
    return knownExt(mime, origName) || ".png";
  }
  // Extension to upload the ORIGINAL file under, or null when it may not be stored as-is
  // (HEIC, or a type we cannot vouch for).
  function storableExt(mime, origName) {
    var x = knownExt(mime, origName);
    return x && STORABLE_EXTS.indexOf(x) >= 0 ? x : null;
  }
  // SVG is never treated as an image here: it can carry script, so it is never stored.
  function isImage(mime, origName) {
    var m = String(mime || "");
    if (/^image\/svg/i.test(m)) return false;
    if (/^image\//i.test(m)) return true;
    return /\.(png|jpe?g|gif|webp|bmp|avif|heic|heif)$/i.test(String(origName || ""));
  }
  // iPhone HEIC/HEIF photos: Safari can decode them (they compress to webp as usual), Chrome/Edge
  // on Windows CANNOT. Uploading the raw .heic shows a grey box in every browser but Safari, so
  // when decoding fails it must be refused with a clear message, not silently stored unviewable.
  function isHeic(mime, origName) {
    if (/^image\/hei[cf]/i.test(String(mime || ""))) return true;
    return /\.hei[cf]$/i.test(String(origName || ""));
  }
  // Formats that must NOT go through the canvas: a gif would lose its animation.
  function skipCompress(mime, origName) {
    var m = String(mime || "").toLowerCase();
    if (m === "image/gif") return true;
    return /\.gif$/i.test(String(origName || ""));
  }
  // New box after shrinking by the longest edge. NEVER upscales a small image.
  function fitBox(w, h, max) {
    w = Math.max(1, Math.round(w || 0)); h = Math.max(1, Math.round(h || 0));
    max = max || MAX_EDGE;
    var edge = Math.max(w, h);
    if (edge <= max) return { w: w, h: h, resized: false };
    var k = max / edge;
    return { w: Math.max(1, Math.round(w * k)), h: Math.max(1, Math.round(h * k)), resized: true };
  }
  // Only after compressing do we know whether it paid off: a small, already optimized PNG comes
  // out HEAVIER. Then keep the ORIGINAL - compression is there to save space, not add to it.
  function pickSmaller(origSize, compressedSize, shrunk) {
    if (!compressedSize) return "original";
    if (shrunk) return "compressed";            // pixel count went down: keep the compressed one
    return compressedSize < origSize ? "compressed" : "original";
  }
  // New width while dragging: kept in a readable range, rounded to whole px.
  function dragWidth(startWidth, dx, frameWidth) {
    var w = Math.round((startWidth || 0) + (dx || 0));
    var cap = Math.max(80, Math.round(frameWidth || 0) || 2000);
    return Math.max(40, Math.min(w, cap));
  }

  var api = {
    timestampName: timestampName, extForType: extForType, storableExt: storableExt, isImage: isImage,
    skipCompress: skipCompress, isHeic: isHeic, fitBox: fitBox, pickSmaller: pickSmaller, dragWidth: dragWidth,
    MAX_EDGE: MAX_EDGE, MAX_MB: MAX_MB,
  };

  // ---------------------------------------------------------------- DOM part
  if (typeof document !== "undefined") {
    function currentBrain() {
      try { return (window.currentBrainPath && window.currentBrainPath()) || "brain"; }
      catch (e) { return "brain"; }
    }
    function contextFor(target) {
      var EC = window.JavisEditorCmds;
      return (EC && EC.contextFor) ? EC.contextFor(target) : null;
    }

    // ----- small status toast in the screen corner -----
    var toast = null, toastTimer = null;
    function showStatus(text, kind) {
      if (!toast) {
        toast = document.createElement("div");
        toast.className = "ni-status";
        document.body.appendChild(toast);
      }
      toast.textContent = text;
      toast.className = "ni-status show" + (kind ? " ni-" + kind : "");
      clearTimeout(toastTimer);
      // Errors stay longer: the user needs time to read why the image did not go in.
      toastTimer = setTimeout(function () { if (toast) toast.className = "ni-status"; },
                              kind === "err" ? 5000 : 1800);
    }

    // ----- compress with a canvas -----
    function decodeImage(file) {
      if (window.createImageBitmap) {
        // imageOrientation "from-image": rotate by the EXIF tag. A phone photo taken upright stores
        // its pixels landscape plus a rotation tag; drawing straight to the canvas while ignoring
        // the tag leaves the image on its side, and the canvas drops EXIF so nothing can rotate it
        // later. (Going through the canvas also drops GPS coordinates, a plus when sharing notes.)
        var open = function (options) {
          return window.createImageBitmap(file, options).then(function (bm) {
            return { source: bm, w: bm.width, h: bm.height, close: function () { try { bm.close(); } catch (e) {} } };
          });
        };
        return open({ imageOrientation: "from-image" }).catch(function () { return open(); })
          .catch(function () { return decodeWithTag(file); });
      }
      return decodeWithTag(file);
    }
    // Fallback: an <img> tag (CSS image-orientation defaults to from-image, so it rotates right too).
    function decodeWithTag(file) {
      return new Promise(function (res, rej) {
        var url = URL.createObjectURL(file);
        var im = new Image();
        im.onload = function () {
          res({ source: im, w: im.naturalWidth, h: im.naturalHeight,
                close: function () { URL.revokeObjectURL(url); } });
        };
        im.onerror = function () { URL.revokeObjectURL(url); rej(new Error("decode")); };
        im.src = url;
      });
    }
    function canvasToBlob(canvas, type, quality) {
      return new Promise(function (res) {
        if (canvas.toBlob) canvas.toBlob(function (b) { res(b); }, type, quality);
        else res(null);
      });
    }
    // Returns { blob, ext, original } - original=true means the original file is kept as-is.
    function compressImage(file) {
      // Null when the original may not be uploaded as-is: then only a re-encoded copy goes up.
      var origExt = storableExt(file.type, file.name);
      if (skipCompress(file.type, file.name)) {
        return Promise.resolve({ blob: file, ext: ".gif", original: true });
      }
      return decodeImage(file).then(function (a) {
        var k = fitBox(a.w, a.h, MAX_EDGE);
        var cv = document.createElement("canvas");
        cv.width = k.w; cv.height = k.h;
        var ct = cv.getContext("2d");
        ct.drawImage(a.source, 0, 0, k.w, k.h);
        a.close();
        return canvasToBlob(cv, "image/webp", QUALITY).then(function (b) {
          if (!b) return origExt ? { blob: file, ext: origExt, original: true } : { unsupported: true };
          // A browser without webp support returns png WITHOUT an error - the extension must
          // follow the REAL blob type, or a .webp file would hold a png.
          var ext = extForType(b.type, "") || ".webp";
          // An original that may not be stored as-is (e.g. HEIC) always goes up re-encoded.
          if (origExt && pickSmaller(file.size, b.size, k.resized) === "original") {
            return { blob: file, ext: origExt, original: true };
          }
          return { blob: b, ext: ext, original: false };
        });
      }).catch(function () {
        // Could not decode: HEIC is refused (see isHeic). Another type goes up as-is only when its
        // extension is a storable one; an unknown type is not uploaded.
        if (isHeic(file.type, file.name)) return { heic: true };
        if (!origExt) return { unsupported: true };
        return { blob: file, ext: origExt, original: true };
      });
    }

    // ----- upload -----
    function upload(blob, name) {
      var fd = new FormData();
      fd.append("file", blob, name);
      fd.append("brain", currentBrain());
      fd.append("folder", "images");          // the server finds/creates the real folder
      return fetch("/files/upload", { method: "POST", body: fd })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (d) {
          if (!d || !d.ok || !d.path) throw new Error((d && d.error) || tw("nimg.upload_failed"));
          return d.path;
        });
    }

    // ----- insert into the editor -----
    // Render pane: use EXACTLY the markup mdToHtml produces for ![[..]], so the turndown rule
    // "wikiimg" recognizes it and saves it back to the same ![[..]].
    function imageHtml(path) {
      var md = "![[" + path + "]]";
      var h = window.mdToHtml ? window.mdToHtml(md) : "";
      var box = document.createElement("div");
      box.innerHTML = h;
      // mdToHtml wraps in <p>; inserting a whole <p> in the middle of a paragraph splits it.
      var inner = (box.children.length === 1 && box.firstElementChild.tagName === "P")
        ? box.firstElementChild.innerHTML : box.innerHTML;
      return inner || null;
    }
    function insertLink(ctx, path) {
      if (!ctx) return false;
      // The upload takes a while: if that note was closed or another one opened meanwhile, the
      // editor body was rebuilt and this host is detached. Bail out so the link never lands in
      // another note (and no success is reported).
      var host = ctx.mode() === "source" ? ctx.ta : ctx.wys;
      if (!host || !host.isConnected) return false;
      if (ctx.mode() === "source") {
        var ta = ctx.ta;
        if (!ta) return false;
        var t = "![[" + path + "]]";
        try { ta.focus(); } catch (e) {}
        var ok = false;
        try { ok = document.execCommand("insertText", false, t); } catch (e) {}
        if (!ok) {
          var s = ta.selectionStart, e2 = ta.selectionEnd;
          ta.value = ta.value.slice(0, s) + t + ta.value.slice(e2);
          var p = s + t.length;
          try { ta.setSelectionRange(p, p); } catch (e) {}
          try { ta.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
        }
        return true;
      }
      var wys = ctx.wys;
      if (!wys) return false;
      var html = imageHtml(path);
      if (!html) return false;
      try { wys.focus(); } catch (e) {}
      // The caret may be outside (a toolbar button was just clicked): move it to the end of the
      // note so the image does not go nowhere.
      try {
        var sel = window.getSelection();
        var outside = !sel || !sel.rangeCount ||
          !(sel.anchorNode && (sel.anchorNode === wys || wys.contains(sel.anchorNode)));
        if (outside) {
          var r = document.createRange(); r.selectNodeContents(wys); r.collapse(false);
          sel.removeAllRanges(); sel.addRange(r);
        }
      } catch (e) {}
      try { document.execCommand("insertHTML", false, html + "&nbsp;"); } catch (e) { return false; }
      // Autosave: insert an image without saving, close the editor, and the link is gone while
      // the file stays in images/ with nothing pointing at it.
      try { wys.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
      return true;
    }

    // ----- main path: file -> compress -> upload -> insert -----
    function handleFile(ctx, file) {
      if (!isImage(file.type, file.name)) return Promise.resolve(false);
      if (file.size > MAX_MB * 1024 * 1024) {
        showStatus(tw("nimg.too_large", { mb: MAX_MB }), "err");
        return Promise.resolve(false);
      }
      showStatus(tw("nimg.working"));
      return compressImage(file).then(function (res) {
        if (res.heic) { showStatus(tw("nimg.heic"), "err"); return false; }
        if (res.unsupported) { showStatus(tw("nimg.unsupported"), "err"); return false; }
        return upload(res.blob, timestampName(new Date(), res.ext)).then(function (path) {
          if (!insertLink(ctx, path)) throw new Error(tw("nimg.no_place"));
          showStatus(tw("nimg.done", { kb: Math.max(1, Math.round(res.blob.size / 1024)) }), "ok");
          return true;
        });
      }).catch(function (err) {
        showStatus(tw("nimg.failed", { error: (err && err.message) || "?" }), "err");
        return false;
      });
    }
    // Several images at once: run them IN SEQUENCE so they land in the order the user picked,
    // and so per-second names within one batch do not collide.
    function handleFiles(ctx, files) {
      var list = [];
      for (var i = 0; i < files.length; i++) if (isImage(files[i].type, files[i].name)) list.push(files[i]);
      if (!list.length) return Promise.resolve(0);
      var n = 0;
      return list.reduce(function (chain, f) {
        return chain.then(function () {
          return handleFile(ctx, f).then(function (ok) { if (ok) n++; });
        });
      }, Promise.resolve()).then(function () { return n; });
    }

    // ----- PASTE (Ctrl+V) -----
    document.addEventListener("paste", function (e) {
      var ctx = contextFor(e.target);
      if (!ctx) return;
      var dt = e.clipboardData;
      if (!dt) return;
      var files = [];
      // dt.files is empty in some Firefox versions when pasting a screenshot -> read items too.
      if (dt.files && dt.files.length) {
        for (var i = 0; i < dt.files.length; i++) files.push(dt.files[i]);
      } else if (dt.items) {
        for (var j = 0; j < dt.items.length; j++) {
          if (dt.items[j].kind === "file") {
            var f = dt.items[j].getAsFile();
            if (f) files.push(f);
          }
        }
      }
      var images = files.filter(function (f) { return isImage(f.type, f.name); });
      if (!images.length) return;          // pasting TEXT: leave it to the editor as usual
      e.preventDefault();
      handleFiles(ctx, images);
    }, true);

    // ----- DROP files into the editor -----
    document.addEventListener("dragover", function (e) {
      var ctx = contextFor(e.target);
      if (!ctx) return;
      var dt = e.dataTransfer;
      if (!dt || !dt.types || Array.prototype.indexOf.call(dt.types, "Files") < 0) return;
      e.preventDefault();
      try { dt.dropEffect = "copy"; } catch (err) {}
    });
    document.addEventListener("drop", function (e) {
      var ctx = contextFor(e.target);
      if (!ctx) return;
      var dt = e.dataTransfer;
      if (!dt || !dt.files || !dt.files.length) return;
      var images = [];
      for (var i = 0; i < dt.files.length; i++) {
        if (isImage(dt.files[i].type, dt.files[i].name)) images.push(dt.files[i]);
      }
      if (!images.length) return;
      e.preventDefault();
      // Not every browser can place the caret at the drop point, so insert at the current caret.
      // Click where the image should go, then drop.
      handleFiles(ctx, images);
    }, true);

    // ----- toolbar button: pick files -----
    function pickFiles(ctx) {
      var inp = document.createElement("input");
      inp.type = "file"; inp.accept = "image/*"; inp.multiple = true;
      inp.style.display = "none";
      document.body.appendChild(inp);
      inp.addEventListener("change", function () {
        var fs = inp.files;
        inp.remove();
        if (fs && fs.length) handleFiles(ctx, fs);
      });
      inp.click();
    }

    // ================================================================ RESIZE GRIP
    // Chromium NO LONGER has a built-in image grip in contenteditable (Firefox does, through
    // enableObjectResizing), so we draw our own floating grip on the image.
    var grip = null, hoverImg = null, drag = null;

    function editorImage(el) {
      if (!el || el.tagName !== "IMG") return null;
      var wys = el.closest ? el.closest(".ne-wys") : null;
      return wys ? el : null;
    }
    function placeGrip() {
      if (!hoverImg || !hoverImg.isConnected) return hideGrip();
      var r = hoverImg.getBoundingClientRect();
      if (!r.width && !r.height) return hideGrip();
      grip.style.left = (r.right - 7) + "px";
      grip.style.top = (r.bottom - 7) + "px";
      grip.classList.add("show");
    }
    function hideGrip() {
      hoverImg = null;
      if (grip) grip.classList.remove("show");
    }
    function showGrip(img) {
      if (!grip) {
        grip = document.createElement("div");
        grip.className = "ni-grip";
        grip.title = tw("nimg.resize_grip");
        document.body.appendChild(grip);
        grip.addEventListener("mousedown", startDrag);
        // Double-click the grip = back to ORIGINAL size (drop "|300"), no need to edit the note by hand.
        grip.addEventListener("dblclick", function (e) {
          e.preventDefault();
          if (!hoverImg) return;
          hoverImg.style.width = ""; hoverImg.style.height = "";
          hoverImg.removeAttribute("data-img-size");
          fireInput(hoverImg);
          placeGrip();
        });
      }
      hoverImg = img;
      placeGrip();
    }
    function fireInput(img) {
      try {
        var wys = img.closest(".ne-wys");
        if (wys) wys.dispatchEvent(new Event("input", { bubbles: true }));
      } catch (e) {}
    }
    function startDrag(e) {
      if (!hoverImg) return;
      e.preventDefault(); e.stopPropagation();
      var wys = hoverImg.closest(".ne-wys");
      drag = {
        img: hoverImg, x: e.clientX,
        w: hoverImg.getBoundingClientRect().width,
        cap: wys ? wys.clientWidth - 28 : 0,
      };
      document.body.classList.add("ni-dragging");
      document.addEventListener("mousemove", onDrag, true);
      document.addEventListener("mouseup", endDrag, true);
    }
    function onDrag(e) {
      if (!drag) return;
      e.preventDefault();
      var w = dragWidth(drag.w, e.clientX - drag.x, drag.cap);
      drag.img.style.width = w + "px";
      drag.img.style.height = "";           // keep the aspect ratio: set one dimension only
      drag.img.setAttribute("data-img-size", String(w));
      placeGrip();
    }
    function endDrag() {
      document.removeEventListener("mousemove", onDrag, true);
      document.removeEventListener("mouseup", endDrag, true);
      document.body.classList.remove("ni-dragging");
      if (drag) fireInput(drag.img);        // new size -> autosave
      drag = null;
      placeGrip();
    }

    document.addEventListener("mouseover", function (e) {
      if (drag) return;
      if (grip && (e.target === grip || (grip.contains && grip.contains(e.target)))) return;
      var img = editorImage(e.target);
      if (img) showGrip(img);
      else if (hoverImg) hideGrip();
    });
    // Scrolling or resizing the window moves the image under the fixed grip -> redraw.
    window.addEventListener("scroll", function () { if (hoverImg && !drag) placeGrip(); }, true);
    window.addEventListener("resize", function () { if (hoverImg) hideGrip(); });

    api.pickFiles = pickFiles;
    api.handleFiles = handleFiles;
    window.JavisNoteImages = api;
  }

  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
