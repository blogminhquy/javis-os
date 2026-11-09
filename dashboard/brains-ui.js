// ============================================================
// brains-ui.js - Nhiều second brain trong 1 thư mục (BRAINS_DIR), nạp TỪ SERVER.
// Bổ sung cho app.js, KHÔNG sửa app.js (file UTF-16 dễ hỏng). Chỉ thao tác DOM:
//   - Đổ dropdown #graphSource từ GET /brains (thay vì localStorage).
//   - window.JavisBrains.create / rename / remove / forget / adopt: what the brain picker panel (brain-picker.js)
//     calls from each brain's row (POST /brains/new, /brains/label, /brains/delete; delete needs the folder name typed).
// Vẫn giữ "chọn folder ngoài bất kỳ" (option data-custom do app.js thêm).
// ============================================================
(function () {
  const sel = document.getElementById("graphSource");
  if (!sel) return;

  function label(b) {
    // notes_capped = server dừng đếm ở trần, con số là SÀN chứ không phải tổng thật.
    // Thêm dấu + để không nói dối; brain thường không bao giờ chạm trần này.
    const n = b.notes ? " · " + b.notes + (b.notes_capped ? "+" : "") : "";
    // Không gắn icon: <option> chỉ nhận chữ. Thư mục ngoài được app.js xếp vào
    // <optgroup> riêng nên vẫn phân biệt được mà không cần ký hiệu nào.
    // 0.219.0: tên hiển thị (label) tách khỏi thư mục; server luôn trả label, bản cũ chưa có thì dùng tên thư mục.
    return (b.label || b.name) + n;
  }

  // Chuẩn hoá path để so trùng: bỏ dấu phân cách cuối, \ -> /, thường hoá (Windows không phân biệt hoa/thường).
  function normPath(p) {
    return (p || "").replace(/[\\/]+$/, "").replace(/\\/g, "/").toLowerCase();
  }

  // Hỏi server 1 path còn là thư mục không. FAIL-SAFE: mọi trường hợp không CHẮC CHẮN (lỗi
  // mạng, endpoint thiếu/404 vì server chưa restart, JSON méo) → {is_dir:null} = CHƯA xác định
  // → GIỮ entry. Chỉ dọn khi server trả rõ is_dir=false. Tránh xoá nhầm folder ngoài hợp lệ.
  async function pathExists(p) {
    try {
      const resp = await fetch("/path/exists?path=" + encodeURIComponent(p));
      if (!resp.ok) return { exists: null, is_dir: null };
      const j = await resp.json();
      if (!j || typeof j.is_dir === "undefined") return { exists: null, is_dir: null };
      return j;
    } catch (e) {
      return { exists: null, is_dir: null };
    }
  }

  // Dọn danh sách thư mục ngoài (localStorage) đã hỏng: bỏ entry TRÙNG path với 1 não thật,
  // và entry mà path KHÔNG còn là thư mục (đã xoá khỏi ổ đĩa). Giữ folder ngoài hợp lệ + entry
  // chưa xác định được (tránh xoá nhầm khi server chớp lỗi). Nguồn sự thật là localStorage nên
  // dọn cả nó → lần app.js render sau vẫn đúng, không "sống lại" qua update.
  // Returns true when it moved the selection off a removed folder (it then fired `change` itself).
  async function pruneCustomBrains(realBrains) {
    let moved = false;
    let list;
    try { list = JSON.parse(localStorage.getItem("javis.brains") || "[]"); }
    catch (e) { list = []; }
    if (!Array.isArray(list)) list = [];
    const realPaths = new Set((realBrains || []).map((b) => normPath(b.path)));
    const kept = [];
    for (const b of list) {
      if (!b || !b.path) continue;
      if (realPaths.has(normPath(b.path))) continue;   // đã là não thật -> bỏ thư mục ngoài trùng
      const chk = await pathExists(b.path);
      if (chk && chk.is_dir === true) { kept.push(b); continue; }   // còn thư mục → giữ
      if (chk && chk.exists === null) { kept.push(b); continue; }   // chưa xác định → giữ
      // còn lại: đã bị xoá / không phải thư mục → loại
    }
    if (kept.length !== list.length) {
      localStorage.setItem("javis.brains", JSON.stringify(kept));
    }
    // Gỡ các option thư mục ngoài (do app.js đã render) không còn trong danh sách giữ lại.
    const keepVals = new Set(kept.map((b) => "path:" + b.path));
    [...sel.querySelectorAll("option[data-custom]")].forEach((o) => {
      if (keepVals.has(o.value)) return;
      if (sel.value === o.value) {           // đang chọn đúng cái bị gỡ → về brain mặc định
        sel.value = "brain";
        localStorage.setItem("javis.graphSource", "brain");
        sel.dispatchEvent(new Event("change"));
        moved = true;
      }
      o.remove();
    });
    // Gỡ hết option trong nhóm thì gỡ luôn nhóm, kẻo menu còn trơ lại cái nhãn
    // "Thư mục ngoài" không có gì bên dưới.
    [...sel.querySelectorAll("optgroup")].forEach((g) => {
      if (!g.querySelector || !g.querySelector("option")) g.remove();
    });
    return moved;
  }

  // The first load of the list is retried until it arrives: until then the picker only holds Brain Default, the
  // external folders and the provisional option app.js made for the saved brain, so the owner could not switch brains.
  // Before 08/11/2026 a failed first load (the page opened while the server restarted after an update) was never
  // retried, and the saved brain was never restored for the whole visit.
  const RETRY_MS = [2000, 3000, 5000, 8000, 13000, 20000, 30000];
  let retries = 0, retryTimer = null;

  async function fetchBrains() {
    try {
      const resp = await fetch("/brains");
      if (!resp || resp.ok === false) return null;
      const data = await resp.json();
      return data && Array.isArray(data.brains) ? data : null;
    } catch (e) {
      return null;
    }
  }

  async function loadBrains(selectPath, restoreSaved) {
    const data = await fetchBrains();
    if (!data) {
      // server chưa sẵn sàng → giữ nguyên dropdown. The boot load tries again; a reload asked later keeps the list it has.
      if (restoreSaved && !retryTimer) {
        const wait = RETRY_MS[Math.min(retries, RETRY_MS.length - 1)];
        retries += 1;
        retryTimer = setTimeout(() => { retryTimer = null; loadBrains(selectPath, restoreSaved); }, wait);
      }
      return;
    }
    retries = 0;
    // Another load got the list while the boot load waited to try again: it finishes the boot's job (restore the saved
    // brain) instead of a second fetch later.
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; restoreSaved = true; }
    const brains = data.brains;
    // Redrawing the list is not a brain switch: the brain in use before is selected again afterwards, silently.
    const before = sel.value;
    [...sel.querySelectorAll("option[data-brain]")].forEach((o) => o.remove());

    const defOpt = sel.querySelector('option[value="brain"]');
    const frag = document.createDocumentFragment();
    // 0.431.0: keep the SERVER's order (the owner's own order, then by label; server/brain_order.py), Brain Default
    // included: it no longer sits on top by force. External folders (app.js optgroup) stay after all of these.
    brains.forEach((b) => {
      const opt = b.is_default && defOpt ? defOpt : document.createElement("option");
      if (!b.is_default) {
        opt.value = "path:" + b.path;
        opt.dataset.brain = "1";
      }
      opt.textContent = label(b);
      opt.dataset.brainName = b.name; // tên folder để xoá chính xác, và là khoá của thứ tự đã sắp
      opt.dataset.brainPath = b.path || "";
      opt.dataset.brainLabel = b.label || b.name;
      opt.dataset.notes = String(b.notes || 0) + (b.notes_capped ? "+" : "");
      frag.appendChild(opt);
    });
    const firstOther = sel.querySelector("optgroup");
    if (firstOther) sel.insertBefore(frag, firstOther);
    else sel.appendChild(frag);

    // Dọn folder ngoài hỏng/trùng TRƯỚC khi khôi phục lựa chọn (đừng khôi phục về path đã chết).
    const moved = await pruneCustomBrains(brains);
    const has = (v) => [...sel.options].some((o) => o.value === v);
    if (!moved) {
      if (!before || has(before)) {
        if (before && sel.value !== before) sel.value = before;
      } else {
        // The brain in use is gone from the list: deleted (here or on another device), or the saved choice app.js
        // selected at startup no longer exists. Go to Brain Default and say so, so every page follows.
        sel.value = "brain";
        localStorage.setItem("javis.graphSource", "brain");
        sel.dispatchEvent(new Event("change"));
      }
    }

    if (selectPath) {
      const want = "path:" + selectPath;
      if ([...sel.options].some((o) => o.value === want)) {
        sel.value = want;
        localStorage.setItem("javis.graphSource", want);
        sel.dispatchEvent(new Event("change"));
      }
    } else if (restoreSaved) {
      const saved = localStorage.getItem("javis.graphSource");
      if (saved && saved !== sel.value && [...sel.options].some((o) => o.value === saved)) {
        sel.value = saved;
        sel.dispatchEvent(new Event("change"));
      }
    }
  }

  // ---- what the brain picker (brain-picker.js) asks for (2026-11-09) ----
  // The four buttons beside the picker are gone: create, rename, delete and "outside folder" now live inside the picker
  // panel, on each brain's row. These functions do the work and RETURN {ok, error}; the panel says the result in its own
  // words (no alert, no prompt).
  async function post(url, fields) {
    const fd = new FormData();
    Object.keys(fields).forEach((k) => fd.append(k, fields[k]));
    try {
      const r = await fetch(url, { method: "POST", body: fd });
      const d = await r.json().catch(() => ({}));
      return d && typeof d === "object" ? d : {};
    } catch (e) {
      return { ok: false, error: window.t("bpick.net_err"), net: true };
    }
  }
  function optionOf(value) {
    return [...sel.options].find((o) => o.value === value) || null;
  }

  async function create(name) {
    const r = await post("/brains/new", { name: (name || "").trim() });
    if (!r.ok) return { ok: false, error: r.error || window.t("brains.create_failed") };
    await loadBrains(r.path, false);   // selects the new brain and tells every page
    return r;
  }

  // Rename (0.219.0): only the SHOWN name changes, kept inside the brain (Javis/brain.json). The folder stays, so saved
  // choices, bots, reminders, background work and /brains/<folder>/... links keep pointing right. Brain Default too.
  async function rename(value, label) {
    const r = await post("/brains/label", { brain: value, label: (label || "").trim() });
    if (!r.ok) return { ok: false, error: r.error || window.t("brains.rename_failed") };
    await loadBrains(null, false);
    try { window.dispatchEvent(new CustomEvent("javis:brain-renamed", { detail: { brain: value, label: r.label } })); } catch (e) {}
    return r;
  }

  // Delete = to the local trash for 30 days, and the delete spreads to every synced machine. The panel asks for the
  // folder name typed exactly; the server checks it again.
  async function remove(value, typed) {
    const opt = optionOf(value);
    if (value === "brain") return { ok: false, error: window.t("brains.cannot_delete_default") };
    if (!opt || !opt.dataset.brain) return { ok: false, error: window.t("brains.only_listed") };
    const name = opt.dataset.brainName;
    const r = await post("/brains/delete", { name: name, confirm: (typed || "").trim() });
    if (!r.ok) return { ok: false, error: r.error || window.t("brains.delete_failed") };
    const wasCurrent = sel.value === value;
    if (wasCurrent) {
      sel.value = "brain";
      localStorage.setItem("javis.graphSource", "brain");
    }
    await loadBrains(null, false);
    if (wasCurrent) sel.dispatchEvent(new Event("change"));
    return r;
  }

  // Make another brain the default (2026-11-09): the old default becomes an ordinary brain that can be deleted. The
  // picker's "brain" entry now names the new default, so someone looking at the old default is moved to that same
  // folder by its path: the screen keeps showing the brain it showed.
  async function setDefault(value) {
    const opt = optionOf(value);
    if (!opt || !opt.dataset.brain) return { ok: false, error: window.t("brains.only_listed") };
    const def = optionOf("brain");
    const stayOn = sel.value === "brain" && def && def.dataset.brainPath ? "path:" + def.dataset.brainPath : "";
    const r = await post("/brains/default", { brain: value });
    if (!r.ok) return { ok: false, error: r.error || window.t("brains.default_failed") };
    await loadBrains(null, false);
    if (stayOn && optionOf(stayOn)) {
      sel.value = stayOn;
      localStorage.setItem("javis.graphSource", stayOn);
      sel.dispatchEvent(new Event("change"));
    }
    return r;
  }

  // An outside folder only leaves the list (and this browser's memory); nothing on the disk is touched.
  function forget(value) {
    const opt = optionOf(value);
    if (!opt || !opt.dataset.custom) return { ok: false, error: window.t("brains.only_listed") };
    let list;
    try { list = JSON.parse(localStorage.getItem("javis.brains") || "[]"); } catch (e) { list = []; }
    if (!Array.isArray(list)) list = [];
    list = list.filter((b) => b && ("path:" + b.path) !== value);
    localStorage.setItem("javis.brains", JSON.stringify(list));
    const wasCurrent = sel.value === value;
    if (wasCurrent) {
      sel.value = "brain";
      localStorage.setItem("javis.graphSource", "brain");
    }
    const grp = opt.parentNode;
    opt.remove();
    if (grp && grp.tagName === "OPTGROUP" && !grp.children.length) grp.remove();
    if (wasCurrent) sel.dispatchEvent(new Event("change"));
    return { ok: true };
  }

  // An uploaded brain (POST /brains/import, done by the panel with upload progress): list it and switch to it.
  async function adopt(path) {
    await loadBrains(path, false);
  }

  loadBrains(null, true);

  window.JavisBrains = { reload: () => loadBrains(null, false), create, rename, remove, forget, adopt, setDefault };
})();
