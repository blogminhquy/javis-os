// ============================================
// JAVIS OS - 3D Graph (V.A.U.L.T. nebula HUD)
// Node = sprite phát sáng additive (glow) → khối cầu tinh vân như chase.h.ai.
// Dùng window.THREE global (load trước 3d-force-graph) + ForceGraph3D UMD.
// ============================================

const _texCache = {};
function glowTexture(THREE, hex) {
  if (_texCache[hex]) return _texCache[hex];
  const s = 96;
  const cv = document.createElement("canvas");
  cv.width = cv.height = s;
  const ctx = cv.getContext("2d");
  const g = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  g.addColorStop(0, "rgba(255,255,255,0.7)");    // lõi trắng DỊU (bớt gắt để đa màu không cộng dồn thành trắng)
  g.addColorStop(0.12, hexA(hex, 0.9));          // màu danh mục ra sớm → giữ đúng hue thay vì cháy trắng
  g.addColorStop(0.42, hexA(hex, 0.4));
  g.addColorStop(1, hexA(hex, 0));               // viền tan vào nền
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, s, s);
  const tex = new THREE.CanvasTexture(cv);
  _texCache[hex] = tex;
  return tex;
}

function particleGlowTexture(THREE) {
  const key = "__particle_orange";
  if (_texCache[key]) return _texCache[key];
  const s = 128;
  const cv = document.createElement("canvas");
  cv.width = cv.height = s;
  const ctx = cv.getContext("2d");
  const g = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  g.addColorStop(0,    "rgba(255,255,255,1)");    // lõi trắng nóng - rất nhỏ
  g.addColorStop(0.06, "rgba(255,210,120,0.95)"); // cam sáng ấm
  g.addColorStop(0.18, "rgba(255,140,40,0.75)");  // cam đậm
  g.addColorStop(0.40, "rgba(255,90,10,0.30)");   // cam mờ
  g.addColorStop(0.70, "rgba(200,60,0,0.08)");    // đỏ cam tan dần
  g.addColorStop(1,    "rgba(180,40,0,0)");       // trong suốt
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, s, s);
  const tex = new THREE.CanvasTexture(cv);
  _texCache[key] = tex;
  return tex;
}
function hexA(hex, a) {
  const m = hex.replace("#", "");
  const r = parseInt(m.substring(0, 2), 16);
  const g = parseInt(m.substring(2, 4), 16);
  const b = parseInt(m.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// Lực hút về tâm 3D (x,y,z) → cả tinh vân co tròn lại, node lẻ/cụm xa bị kéo vào gần.
function centerGravity3D(strength) {
  let _nodes = [];
  const force = (alpha) => {
    const k = strength * alpha;
    for (let i = 0; i < _nodes.length; i++) { const n = _nodes[i]; n.vx -= n.x * k; n.vy -= n.y * k; n.vz -= (n.z || 0) * k; }
  };
  force.initialize = (ns) => { _nodes = ns; };
  return force;
}

class JavisGraph3D {
  constructor(container, tooltip) {
    this.container = container;
    this.tooltip = tooltip;
    this.graph = null;
    this.level = 0;
    this._smooth = 0;
    this._raf = null;
    this._sprites = [];
    this._thinking = false;
    this._firingNodes = new Map();
    this._births = new Map();   // sprite -> frames còn lại của hiệu ứng "nảy sinh"
    this._paused = false;
    this._fitTimer = null;
    // Expose để Console (console.js) gọi pause()/wake() khi chuyển trang - không cần sửa app.js.
    window.__javisGraph = this;
    window.dispatchEvent(new Event("javis-graph-created"));
  }

  async load(query = "source=all") {
    const res = await fetch(`/graph?${query}`);
    const data = await res.json();
    if (window.JavisCatColorize) window.JavisCatColorize(data.nodes);   // tô màu theo danh mục như 2D
    const links = data.edges.map(e => ({ source: e.source, target: e.target }));
    const THREE = window.THREE;

    if (!this.graph) {
      if (!window.ForceGraph3D) throw new Error("Thư viện 3D chưa tải (kiểm tra mạng)");
      if (!THREE) throw new Error("THREE chưa tải");

      this.graph = ForceGraph3D()(this.container)
        .backgroundColor("rgba(0,0,0,0)")
        .showNavInfo(false)
        .onEngineStop(() => {
          this._settled = true;
          // 3D ForceGraph giữ camera khởi tạo khá gần. Trên desktop khối node tự co
          // nên nhìn như đã fit, nhưng viewport mobile thấp vẫn giữ trạng thái phóng to.
          // Chỉ canh lại camera mobile sau khi physics đã lắng để không thay đổi desktop.
          this._scheduleMobileFit(60);
        })
        .nodeThreeObject(n => {
          const mat = new THREE.SpriteMaterial({
            map: glowTexture(THREE, n.color || "#b98cff"),
            blending: THREE.AdditiveBlending,
            depthWrite: false,
            transparent: true,
          });
          const sp = new THREE.Sprite(mat);
          const base = 5 + Math.min(26, (n.links || 0) * 1.8);
          sp.scale.set(base, base, 1);
          sp.__base = base;
          n.__sprite = sp;
          return sp;
        })
        .nodeThreeObjectExtend(false)
        .linkColor(() => "rgba(170,150,255,0.5)")
        .linkWidth(0)
        .linkOpacity(0.11)
        .linkDirectionalParticles(0)
        .linkDirectionalParticleWidth(4)
        .linkDirectionalParticleColor(() => "rgba(255,165,50,0.95)")
        .linkDirectionalParticleSpeed(0.007)
        .onNodeHover(n => {
          this.container.style.cursor = n ? "pointer" : "grab";
          if (n && this.tooltip) {
            this.tooltip.style.display = "block";
            this.tooltip.innerHTML = `<strong>${n.label}</strong><br><span class="tt-path">${n.path}</span><br><span class="tt-links">${n.links} kết nối · click để mở</span>`;
          } else if (this.tooltip) {
            this.tooltip.style.display = "none";
          }
        })
        .onNodeClick(n => {
          const dist = 90;
          const r = 1 + dist / Math.hypot(n.x || 1, n.y || 1, n.z || 1);
          this.graph.cameraPosition({ x: (n.x || 0) * r, y: (n.y || 0) * r, z: (n.z || 0) * r }, n, 800);
          if (window.onGraphNodeClick) window.onGraphNodeClick(n);
        });

      // Layout cầu chặt: lực đẩy vừa, link ngắn, + hút về tâm cho co TRÒN lại (kéo cụm/node xa vào)
      this.graph.d3Force("charge").strength(-45);
      const linkForce = this.graph.d3Force("link");
      if (linkForce) linkForce.distance(28);
      this.graph.d3Force("gravity", centerGravity3D(0.06));

      const controls = this.graph.controls();
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.6;   // quay nhẹ liên tục - luôn "sống"

      this._animate();
    }

    this._settled = false;
    if (this._fitTimer) clearTimeout(this._fitTimer);
    this._slowFrame = 0;
    this.graph.graphData({ nodes: data.nodes, links });
    // Gom sprite refs + dựng adjacency (để lan truyền firing theo synapse)
    setTimeout(() => this._rebuildRefs(), 200);
    this.resize();
    return data;
  }

  // Gom lại sprite refs + adjacency từ graphData hiện tại (gọi sau mỗi lần đổi data)
  _rebuildRefs() {
    if (!this.graph) return;
    const nodes = this.graph.graphData().nodes;
    this._sprites = nodes.filter(n => n.__sprite).map(n => n.__sprite);
    const idToIdx = {};
    let k = 0;
    nodes.forEach(n => { if (n.__sprite) { idToIdx[n.id] = k; k++; } });
    this._adj = this._sprites.map(() => []);
    this.graph.graphData().links.forEach(l => {
      const s = typeof l.source === "object" ? l.source.id : l.source;
      const t = typeof l.target === "object" ? l.target.id : l.target;
      const si = idToIdx[s], ti = idToIdx[t];
      if (si != null && ti != null) { this._adj[si].push(ti); this._adj[ti].push(si); }
    });
  }

  nodeStats() {
    if (!this.graph) return { nodes: 0, links: 0 };
    const d = this.graph.graphData();
    return { nodes: d.nodes.length, links: d.links.length };
  }

  // Thêm/cập nhật 1 node realtime (brain vừa sinh ra hoặc sửa note).
  // linkTargets = stem (lowercase) các wikilink trong note đó.
  addOrUpdate(node, linkTargets, isNew) {
    if (!this.graph || !node || !node.id) return { created: false };
    const data = this.graph.graphData();
    const byId = new Map(data.nodes.map(n => [n.id, n]));
    let target = byId.get(node.id);
    let created = false;

    if (!target) {
      // Mọc ra cạnh 1 node hàng xóm đã có (nếu link tới) → trông như nảy từ mạng
      let px = 0, py = 0, pz = 0;
      const nb = (linkTargets || []).map(s => byId.get(s)).find(Boolean);
      if (nb) { px = (nb.x || 0) + (Math.random() - 0.5) * 10; py = (nb.y || 0) + (Math.random() - 0.5) * 10; pz = (nb.z || 0) + (Math.random() - 0.5) * 10; }
      target = Object.assign({}, node, { x: px, y: py, z: pz, links: 0 });
      data.nodes.push(target);
      byId.set(target.id, target);
      created = true;
    } else {
      if (node.color) target.color = node.color;
      if (node.path) target.path = node.path;
    }

    // Chuẩn hoá link về dạng id-string + tập key để khử trùng
    const keyOf = (a, b) => (a < b ? a + "|" + b : b + "|" + a);
    const links = data.links.map(l => ({
      source: typeof l.source === "object" ? l.source.id : l.source,
      target: typeof l.target === "object" ? l.target.id : l.target,
    }));
    const seen = new Set(links.map(l => keyOf(l.source, l.target)));

    (linkTargets || []).forEach(stem => {
      const tgt = byId.get(stem);
      if (!tgt || tgt.id === target.id) return;
      const k = keyOf(target.id, tgt.id);
      if (seen.has(k)) return;
      seen.add(k);
      links.push({ source: target.id, target: tgt.id });
      target.links = (target.links || 0) + 1;
      tgt.links = (tgt.links || 0) + 1;
    });

    this.graph.graphData({ nodes: data.nodes, links });
    // Sau khi sprite của node mới dựng xong → rebuild refs + bật hiệu ứng nảy sinh
    setTimeout(() => {
      this._rebuildRefs();
      if (created && target.__sprite) this._births.set(target.__sprite, 36);
    }, 60);

    return { created };
  }

  setLevel(l) { this.level = l; }

  setThinking(active) {
    this._thinking = active;
    if (!this.graph) return;
    if (active) {
      this._buildThinkingSprites();
    } else {
      this._clearThinkingSprites();
      this._firingNodes.clear();
    }
  }

  _buildThinkingSprites() {
    this._clearThinkingSprites();
    const THREE = window.THREE;
    if (!THREE || !this.graph) return;
    const scene = this.graph.scene && this.graph.scene();
    if (!scene) return;
    const links = this.graph.graphData().links;
    if (!links || !links.length) return;
    // Lấy tối đa 60 link ngẫu nhiên để không quá nặng
    const pool = links.length > 100 ? links.filter(() => Math.random() < 100 / links.length) : links;
    this._thinkSprites = [];
    pool.forEach(link => {
      const count = 2 + (Math.random() < 0.5 ? 1 : 0);
      for (let i = 0; i < count; i++) {
        const mat = new THREE.SpriteMaterial({
          map: particleGlowTexture(THREE),
          blending: THREE.AdditiveBlending,
          depthWrite: false,
          transparent: true,
          opacity: 0.8,
        });
        const sp = new THREE.Sprite(mat);
        const size = 3.5 + Math.random() * 3;
        sp.scale.set(size, size, 1);
        scene.add(sp);
        this._thinkSprites.push({ sp, link, t: Math.random(), speed: 0.007 + Math.random() * 0.008 });
      }
    });
  }

  _clearThinkingSprites() {
    if (!this._thinkSprites || !this._thinkSprites.length) return;
    const scene = this.graph && this.graph.scene && this.graph.scene();
    this._thinkSprites.forEach(({ sp }) => {
      if (scene) scene.remove(sp);
      if (sp.material) sp.material.dispose();
    });
    this._thinkSprites = [];
  }

  _animate() {
    const tick = () => {
      if (this._paused) { this._raf = null; return; }   // pause: dừng hẳn vòng lặp (kể cả khi load() vừa gọi lại)
      this._raf = requestAnimationFrame(tick);
      if (!this.graph) return;
      // Không render khi tab ẩn - tiết kiệm CPU/GPU hoàn toàn
      if (document.hidden) return;
      // Sau khi physics settle: giảm còn ~15fps (bỏ qua 3/4 frame)
      if (this._settled) {
        this._slowFrame = (this._slowFrame || 0) + 1;
        if (this._slowFrame % 4 !== 0) return;
      }
      const t = this.level || 0;
      if (t > this._smooth) this._smooth += (t - this._smooth) * 0.5;
      else this._smooth += (t - this._smooth) * 0.12;
      const lvl = this._smooth;

      // Pulse từng sprite: phồng + sáng theo nhịp giọng
      const pulse = 1 + lvl * 1.6;
      // Nền để DỊU (0.5) - vừa hết chói (đa màu cộng dồn không còn cháy trắng),
      // vừa cho node "suy nghĩ" loé lên nổi bật trở lại (tương phản với nền tối).
      const op = Math.min(1, 0.5 + lvl * 0.6);
      for (const sp of this._sprites) {
        if (!sp) continue;
        const b = sp.__base;
        sp.scale.set(b * pulse, b * pulse, 1);
        if (sp.material) sp.material.opacity = op;
      }

      // --- BIRTH: node vừa sinh ra → loé sáng to rồi co về kích thước thật ---
      if (this._births.size) {
        for (const [sp, fr] of this._births) {
          if (!sp) { this._births.delete(sp); continue; }
          const t = fr / 36;                       // 1 → 0
          const grow = 1 + t * 3.2;                // bắt đầu to (pop) → settle
          const b = sp.__base || 5;
          sp.scale.set(b * grow, b * grow, 1);
          if (sp.material) sp.material.opacity = Math.min(1, 0.5 + (1 - t) * 0.6 + t * 0.4);
          const next = fr - 1;
          if (next <= 0) this._births.delete(sp);
          else this._births.set(sp, next);
        }
      }

      // Quay tròn nhẹ liên tục - tự xoay scene
      const scene = this.graph.scene && this.graph.scene();
      if (scene) scene.rotation.y += 0.0018 + lvl * 0.012;

      this._frame = (this._frame || 0) + 1;

      // --- THINKING PARTICLES: đốm sáng bay dọc link ---
      if (this._thinking && this._thinkSprites && this._thinkSprites.length) {
        for (const p of this._thinkSprites) {
          p.t = (p.t + p.speed) % 1;
          const src = p.link.source;
          const tgt = p.link.target;
          if (!src || !tgt || src.x == null) continue;
          p.sp.position.set(
            src.x + (tgt.x - src.x) * p.t,
            src.y + (tgt.y - src.y) * p.t,
            src.z + (tgt.z - src.z) * p.t,
          );
          // Fade in từ nguồn, fade out gần đích - trông như bong bóng sáng trôi
          p.sp.material.opacity = Math.sin(p.t * Math.PI) * 0.85 + 0.1;
        }
      }

      // --- THINKING: nơron kích hoạt + LAN TRUYỀN theo synapse ---
      if (this._thinking) {
        const n = this._sprites.length;
        // Điểm khởi phát: 1-2 node "loé" lên thưa thớt (ý nghĩ mới) - chậm cho đỡ rối
        if (n > 0 && this._frame % 14 === 0) {
          const seeds = Math.max(2, Math.floor(n * 0.02));
          for (let i = 0; i < seeds; i++) {
            this._firingNodes.set(Math.floor(Math.random() * n), 14);
          }
        }
        // Lan truyền chậm: node cháy mạnh kích hoạt hàng xóm → sóng dịu chạy qua mạng
        if (this._adj && this._frame % 4 === 0) {
          const toAdd = [];
          for (const [idx, frames] of this._firingNodes) {
            if (frames >= 9) {
              const nb = this._adj[idx];
              if (nb) for (const j of nb) {
                if (!this._firingNodes.has(j) && Math.random() < 0.06) toAdd.push(j);
              }
            }
          }
          for (const j of toAdd) this._firingNodes.set(j, 12);
        }
        // Animate firing nodes - sáng lên rồi tắt dần
        for (const [idx, frames] of this._firingNodes) {
          const sp = this._sprites[idx];
          if (sp) {
            const t = Math.min(1, frames / 14);
            const s = sp.__base * (pulse + t * 2.0);   // phồng dịu hơn
            sp.scale.set(s, s, 1);
            if (sp.material) sp.material.opacity = Math.min(1, 0.6 + t * 0.5);
          }
          const next = frames - 1;
          if (next <= 0) this._firingNodes.delete(idx);
          else this._firingNodes.set(idx, next);
        }
      }
    };
    tick();
  }

  resize() {
    if (this.graph) {
      this.graph.width(this.container.clientWidth);
      this.graph.height(this.container.clientHeight);
      // Safari/Chrome mobile có thể đổi chiều cao visual viewport sau khi thanh địa chỉ
      // co lại. Fit lại trên kích thước cuối, nhưng chỉ khi layout node đã ổn định.
      if (this._settled) this._scheduleMobileFit(140);
    }
  }

  _isMobileViewport() {
    return !!(window.matchMedia && window.matchMedia("(max-width: 860px)").matches);
  }

  _scheduleMobileFit(delay) {
    if (!this.graph || !this._isMobileViewport()) return;
    if (this._fitTimer) clearTimeout(this._fitTimer);
    this._fitTimer = setTimeout(() => {
      this._fitTimer = null;
      if (!this.graph || !this._settled || !this._isMobileViewport()) return;
      try {
        // Padding nhỏ vì người dùng có thể ẩn toàn bộ HUD để ngắm brain trọn khung.
        this.graph.zoomToFit(650, 24);
      } catch (e) {}
    }, delay == null ? 0 : delay);
  }

  stop() { if (this._raf) cancelAnimationFrame(this._raf); this._raf = null; }
  resume() { if (!this._raf) this._animate(); }

  // Pause SÂU - dùng khi rời cockpit (mở Console): dừng vòng render + engine vật lý +
  // autorotate → CPU/GPU về ~0, nhưng giữ context để bật lại tức thì. Đảo bằng wake().
  pause() {
    if (this._paused) return;
    this._paused = true;
    this.stop();                                  // dừng RAF render glow/firing
    if (this.graph) {
      try { this.graph.pauseAnimation(); } catch (e) {}   // dừng vòng render của force-graph
      try { const c = this.graph.controls(); if (c) c.autoRotate = false; } catch (e) {}
    }
  }
  wake() {
    if (!this._paused) return;
    this._paused = false;
    if (this.graph) {
      try { this.graph.resumeAnimation(); } catch (e) {}
      try { const c = this.graph.controls(); if (c) c.autoRotate = true; } catch (e) {}
      this.resize();                              // khung có thể đã đổi kích thước khi ẩn
    }
    this.resume();                                // chạy lại RAF
  }
  isPaused() { return !!this._paused; }
}

window.JavisGraph3D = JavisGraph3D;
window.dispatchEvent(new Event("javis-graph3d-ready"));
