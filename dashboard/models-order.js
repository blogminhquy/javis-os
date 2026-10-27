/* models-order.js - the Models page usage order (0.351.0, docs/dev/2026-10-model-routing-spec.md 2.1-2.3).
 * Pure parts (moving an item, the swap button) are tested with node; drag and popover placement run only in the browser.
 *
 * Drag: a mouse drags a card from anywhere on its head (or an account row); a finger needs the 6-dot grip or a long
 * press (~350ms), so scrolling the page with a thumb never moves a card by accident.
 */
(function () {
  "use strict";

  /** A copy of `list` with the item at `from` moved to index `to` (`to` counts the other items, as a drop line does). */
  function move(list, from, to) {
    const out = list.slice();
    if (from < 0 || from >= out.length || to == null || to === from) return out;
    const x = out.splice(from, 1)[0];
    out.splice(Math.max(0, Math.min(to, out.length)), 0, x);
    return out;
  }
  /** The "Swap" button between card i-1 and card i. */
  function swapAt(list, i) {
    const out = list.slice();
    if (i < 1 || i >= out.length) return out;
    const x = out[i - 1]; out[i - 1] = out[i]; out[i] = x;
    return out;
  }

  const api = { move: move, swapAt: swapAt };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined") return;

  /** Opens a popover upward like the chat composer; flips down only when there is no room above. Clamped to the
   *  screen sideways and in height, so a phone never gets a list cut off at the bottom edge. */
  function place(pop) {
    if (!pop || !pop.parentElement) return;
    pop.style.left = ""; pop.style.top = ""; pop.style.bottom = ""; pop.style.maxHeight = "";
    const vw = document.documentElement.clientWidth;
    const rc = pop.getBoundingClientRect();
    let dx = 0;
    if (rc.right > vw - 12) dx = vw - 12 - rc.right;
    if (rc.left + dx < 12) dx = 12 - rc.left;
    if (dx) pop.style.left = (pop.offsetLeft + dx) + "px";
    // Room is counted inside the pane that scrolls, not the window: the page header sits over its top edge, and a
    // list measured against the window slid its search box under that header on a phone.
    let sc = pop.parentElement.parentElement;
    while (sc && sc !== document.body && !/(auto|scroll)/.test(getComputedStyle(sc).overflowY)) sc = sc.parentElement;
    const top = sc && sc !== document.body ? Math.max(0, sc.getBoundingClientRect().top) : 0;
    const a = pop.parentElement.getBoundingClientRect(), h = pop.scrollHeight;
    const above = a.top - top - 12, below = window.innerHeight - a.bottom - 12;
    const up = above >= Math.min(h, 320) || above > below;
    if (up) { pop.style.top = "auto"; pop.style.bottom = "calc(100% + 6px)"; }
    else { pop.style.bottom = "auto"; pop.style.top = "calc(100% + 6px)"; }
    pop.style.maxHeight = Math.max(160, (up ? above : below) - 6) + "px";
  }

  /** Binds drag once on `root`. Items carry data-dnd="<group>"; opt.onDrop(group, from, to) saves the new order.
   *  A drop swallows the click that follows, so letting go on a chip does not also open it. */
  function bindDrag(root, opt) {
    if (root._ordDrag) { root._ordDrag.opt = opt; return; }
    const st = root._ordDrag = { opt: opt, pend: null, drag: null, swallow: false };
    const line = document.createElement("div");
    line.className = "ord-drop-line"; line.hidden = true;
    document.body.appendChild(line);

    function begin(ev) {
      const item = st.pend.item, key = item.dataset.dnd;
      const items = Array.prototype.slice.call(root.querySelectorAll('[data-dnd="' + key + '"]'));
      st.drag = { key: key, item: item, from: items.indexOf(item), others: items.filter((x) => x !== item),
                  y0: st.pend.y0, s0: window.scrollY, to: null };
      item.classList.remove("ord-pressing"); item.classList.add("ord-dragging");
      document.body.classList.add("ord-is-dragging");
      try { item.setPointerCapture(st.pend.id); } catch (e) {}
      if (navigator.vibrate) { try { navigator.vibrate(15); } catch (e) {} }
      at(ev ? ev.clientY : st.pend.y0);
    }
    function at(y) {
      const d = st.drag;
      d.item.style.transform = "translateY(" + (y - d.y0 + window.scrollY - d.s0) + "px)";
      const rects = d.others.map((x) => x.getBoundingClientRect());
      d.to = rects.filter((r) => r.top + r.height / 2 < y).length;
      if (!rects.length) return;
      const box = d.item.getBoundingClientRect();
      const ly = d.to < rects.length ? rects[d.to].top - 6 : rects[rects.length - 1].bottom + 4;
      line.style.top = ly + "px"; line.style.left = box.left + "px"; line.style.width = box.width + "px";
      line.hidden = false;
    }
    function forget() {
      if (st.pend && st.pend.timer) clearTimeout(st.pend.timer);
      if (st.pend && st.pend.item) st.pend.item.classList.remove("ord-pressing");
      st.pend = null;
    }
    root.addEventListener("pointerdown", (ev) => {
      if (ev.button > 0) return;
      const grip = ev.target.closest(".ord-grip");
      const zone = grip || ev.target.closest(".ord-head, .ord-acct");
      if (!zone) return;
      if (!grip && ev.target.closest("button, input, select, textarea, a, label, .ord-menu, .ord-chips, .info-body")) return;
      const item = zone.closest("[data-dnd]");
      if (!item || !root.contains(item)) return;
      if (item.parentElement.querySelectorAll('[data-dnd="' + item.dataset.dnd + '"]').length < 2) return;
      st.pend = { item: item, id: ev.pointerId, x0: ev.clientX, y0: ev.clientY, touch: ev.pointerType !== "mouse", timer: null };
      if (grip) { ev.preventDefault(); begin(null); return; }
      if (st.pend.touch) {
        item.classList.add("ord-pressing");
        st.pend.timer = setTimeout(() => { if (st.pend) begin(null); }, 350);
      }
    });
    document.addEventListener("pointermove", (ev) => {
      if (st.drag) {
        if (ev.clientY < 80) window.scrollBy(0, -14); else if (ev.clientY > window.innerHeight - 80) window.scrollBy(0, 14);
        at(ev.clientY); return;
      }
      if (!st.pend) return;
      const d = Math.hypot(ev.clientX - st.pend.x0, ev.clientY - st.pend.y0);
      if (st.pend.touch) { if (d > 8) forget(); } else if (d > 5) begin(ev);
    });
    document.addEventListener("touchmove", (ev) => { if (st.drag) ev.preventDefault(); }, { passive: false });
    root.addEventListener("contextmenu", (ev) => { if (st.drag || st.pend) ev.preventDefault(); });
    root.addEventListener("click", (ev) => {
      if (st.swallow) { st.swallow = false; ev.preventDefault(); ev.stopPropagation(); }
    }, true);
    const end = () => {
      if (!st.drag) { forget(); return; }
      const d = st.drag;
      d.item.style.transform = ""; d.item.classList.remove("ord-dragging");
      document.body.classList.remove("ord-is-dragging");
      line.hidden = true; st.drag = null; forget();
      st.swallow = true; setTimeout(() => { st.swallow = false; }, 0);
      if (d.to != null && d.to !== d.from && st.opt.onDrop) st.opt.onDrop(d.key, d.from, d.to);
    };
    document.addEventListener("pointerup", end);
    document.addEventListener("pointercancel", end);
  }

  api.place = place;
  api.bindDrag = bindDrag;
  window.JavisModelsOrder = api;
})();
