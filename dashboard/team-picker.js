/* Hộp chọn thành viên nhóm kiểu Zalo (0.142.0): dùng cho Tạo nhóm và Thêm thành viên ở trang Nhóm.
 *
 * Máy tính: hộp giữa màn hình. Điện thoại (<= 640px): màn đầy đủ, footer cố định ở đáy. Gồm:
 * - ô tìm KHÔNG CẦN DẤU (tên, vai, mã, tag);
 * - hàng chip tag lấy từ trang Cộng sự (cùng tag của trợ lý), lọc một tag mỗi lần, đổi lọc KHÔNG mất người đã chọn;
 * - dòng trợ lý có ảnh, tên, vai; hàng chip người đã chọn (bấm x để bỏ);
 * - người tạo tự hiện "Bạn · Người tạo nhóm/quản lý", tách khỏi Điều phối (AI); Điều phối chọn ngay trên chip người đã
 *   chọn, bỏ người đang Điều phối thì báo rõ, không âm thầm giao cho người khác;
 * - Thêm thành viên: người đã ở nhóm hiện "Đã tham gia", không chọn lại được, không tính vào số người mới;
 * - footer cố định: số đã chọn, Huỷ, nút chính.
 * - Create only (2026-11-12): a "documents" block under the name. Files already in the brain (found by name), files from
 *   the device and links are picked here and go to the server with the create request, so the team has them from
 *   its first message. Nothing is attached before Create is pressed.
 *
 * File này chỉ có hàm THUẦN (trạng thái vào, HTML ra). teams.js giữ trạng thái, gọi API và gắn sự kiện.
 */
(function () {
  "use strict";

  function tw(khoa, bien) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(khoa, bien) : khoa;
    if (s === khoa && typeof module !== "undefined" && module.exports && FALLBACK[khoa]) s = FALLBACK[khoa];
    if (bien) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return Object.prototype.hasOwnProperty.call(bien, ten) ? String(bien[ten]) : m;
      });
    }
    return s;
  }
  var FALLBACK = {};   // test dưới node nạp vi.json vào đây qua setStrings

  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var ic = function (n, o) { return (typeof window !== "undefined" && window.ic) ? window.ic(n, o) : ""; };

  // Bỏ dấu tiếng Việt và hoa thường để tìm "khong dau" ra "Không dấu". "đ" không phải dấu ghép nên đổi tay.
  function fold(s) {
    s = String(s == null ? "" : s);
    if (s.normalize) s = s.normalize("NFD").replace(/[̀-ͯ]/g, "");
    return s.replace(/\u0111/g, "d").replace(/\u0110/g, "D").toLowerCase().trim();
  }

  var NO_TAG = "__none";   // chip "Chưa có tag"

  function live(roster) {
    return (roster || []).filter(function (a) { return a && a.slug && a.status !== "retired" && a.status !== "missing"; });
  }

  // Tag của trang Cộng sự, theo khoá host cấp (`tag_keys`) để "Bán hàng" và "bán hàng" là một chip. Đếm số trợ lý.
  function tagsOf(roster) {
    var by = {}, order = [];
    live(roster).forEach(function (a) {
      (a.tags || []).forEach(function (t, i) {
        var key = (a.tag_keys || [])[i] || fold(t);
        if (!by[key]) { by[key] = { key: key, label: t, count: 0 }; order.push(key); }
        by[key].count++;
      });
    });
    return order.map(function (k) { return by[k]; }).sort(function (x, y) { return y.count - x.count || (x.label < y.label ? -1 : 1); });
  }

  function hasTag(a, key) {
    if (key === NO_TAG) return !(a.tags || []).length;
    return (a.tags || []).some(function (t, i) { return ((a.tag_keys || [])[i] || fold(t)) === key; });
  }

  function joined(st, slug) { return (st.exclude || []).indexOf(slug) >= 0; }

  // Trợ lý hiện trong danh sách: theo tag đang lọc và chữ đang tìm. Người đã chọn VẪN được giữ trong `st.selected` dù bị
  // lọc khỏi danh sách (đổi bộ lọc không làm mất lựa chọn). Ở Thêm thành viên, người đã ở nhóm vẫn hiện (nhãn "Đã tham
  // gia") nhưng xếp sau người chưa ở nhóm.
  function visible(roster, st) {
    var q = fold(st.query);
    var rows = live(roster).filter(function (a) {
      if (st.tag && !hasTag(a, st.tag)) return false;
      if (!q) return true;
      return [a.name, a.role, a.slug].concat(a.tags || []).some(function (x) { return fold(x).indexOf(q) >= 0; });
    });
    if (!(st.exclude || []).length) return rows;
    return rows.filter(function (a) { return !joined(st, a.slug); }).concat(rows.filter(function (a) { return joined(st, a.slug); }));
  }

  function bySlug(roster, slug) {
    var all = roster || [];
    for (var i = 0; i < all.length; i++) if (all[i].slug === slug) return all[i];
    return null;
  }

  // Bật/tắt một người (người đã ở nhóm thì không). Trả trạng thái MỚI, không sửa trạng thái cũ.
  function toggle(st, slug) {
    if (joined(st, slug)) return st;
    var sel = (st.selected || []).slice();
    var i = sel.indexOf(slug);
    if (i >= 0) sel.splice(i, 1); else sel.push(slug);
    return normalize(Object.assign({}, st, { selected: sel }));
  }

  function setLeader(st, slug) {
    if ((st.selected || []).indexOf(slug) < 0) return st;
    return normalize(Object.assign({}, st, { leader: slug, leaderTouched: true, leaderDropped: false }));
  }

  // Điều phối luôn là một người ĐÃ CHỌN:
  // - chưa ai tự chọn: mặc định người đầu tiên (hiện rõ nhãn Điều phối trên chip);
  // - còn đúng một người: người đó (mặc định rõ ràng, không còn ai khác để chọn);
  // - bỏ chọn đúng người đang Điều phối khi còn nhiều người: Điều phối để TRỐNG và cờ `leaderDropped` để hộp báo rõ, chủ
  //   chọn lại trên chip. Không âm thầm chuyển cho người khác.
  function normalize(st) {
    var sel = st.selected || [];
    var leader = st.leader || "";
    var dropped = !!st.leaderDropped;
    if (leader && sel.indexOf(leader) < 0) {
      leader = "";
      dropped = sel.length > 1;
    }
    if (!leader && sel.length === 1) { leader = sel[0]; dropped = false; }
    else if (!leader && !st.leaderTouched && !dropped) leader = sel[0] || "";
    if (!sel.length) dropped = false;
    return Object.assign({}, st, { leader: leader, leaderDropped: dropped });
  }

  // Tên nhóm để trống: như Zalo, ghép tên ba người đầu.
  function autoName(st, roster) {
    return (st.selected || []).slice(0, 3).map(function (s) { var a = bySlug(roster, s); return a ? (a.name || a.slug) : s; })
      .join(", ");
  }

  // Tạo nhóm cần một người điều phối trong số người đã chọn (review 0.142.0, #9): bỏ điều phối thì nút Tạo khoá cho tới
  // khi chủ chọn lại, thay vì tạo một nhóm mà mọi tin chung đều không ai trả lời.
  function canSubmit(st) {
    if (st.saving || !(st.selected || []).length) return false;
    if (docsBusy(st)) return false;          // a file still uploading would be left out of the team
    return st.mode !== "create" || !!st.leader;
  }

  // ───────────── documents picked in the create box (2026-11-12) ─────────────
  // st.docs:  [{ name, brain_path, dir }] for a file or a whole folder (`dir`) of the brain, [{ name, path, uid, busy, err }] for an upload
  //           (`path` is the staged path /upload returned; empty while it uploads or when it failed).
  // st.links: ["https://..."]
  var DOCS_MAX = 10;         // files, and links: the server takes at most this many at creation (team_api.CREATE_DOCS_MAX)

  function docsBusy(st) { return (st.docs || []).some(function (d) { return d.busy; }); }

  function hasDoc(st, brainPath) {
    return (st.docs || []).some(function (d) { return d.brain_path && d.brain_path === brainPath; });
  }

  // Add one file. The same brain file twice, or one more than DOCS_MAX, changes nothing. Returns the NEW state.
  function addDoc(st, doc) {
    var docs = (st.docs || []).slice();
    if (!doc || docs.length >= DOCS_MAX || (doc.brain_path && hasDoc(st, doc.brain_path))) return st;
    docs.push(doc);
    return Object.assign({}, st, { docs: docs });
  }

  function removeDoc(st, i) {
    var docs = (st.docs || []).slice();
    docs.splice(Number(i), 1);
    return Object.assign({}, st, { docs: docs });
  }

  // A typed address as a link the server accepts: "example.com/a" gets https://. "" when it cannot be one.
  function cleanLink(raw) {
    var u = String(raw == null ? "" : raw).trim();
    if (!u || /\s/.test(u)) return "";
    if (!/^https?:\/\//i.test(u)) {
      if (/^[a-z][a-z0-9+.-]*:(?!\d)/i.test(u)) return "";      // another scheme (mailto:, javascript:); "host:8080" is not one
      u = "https://" + u;
    }
    return /^https?:\/\/[^\/.]+(\.[^\/.]+)+(\/.*)?$/i.test(u) || /^https?:\/\/localhost(:\d+)?(\/.*)?$/i.test(u) ? u : "";
  }

  // { st, ok }: ok false when the text is not a link (the state then carries `linkBad` so the box can say so).
  function addLink(st, raw) {
    var u = cleanLink(raw);
    var links = (st.links || []).slice();
    if (!u) return { st: Object.assign({}, st, { linkBad: !!String(raw || "").trim() }), ok: false };
    if (links.indexOf(u) < 0 && links.length < DOCS_MAX) links.push(u);
    return { st: Object.assign({}, st, { links: links, linkDraft: "", linkBad: false }), ok: true };
  }

  function removeLink(st, i) {
    var links = (st.links || []).slice();
    links.splice(Number(i), 1);
    return Object.assign({}, st, { links: links });
  }

  // What goes to POST /teams: files that have somewhere to come from (a failed upload is left out), and the links.
  function docPayload(st) {
    return {
      attachments: (st.docs || []).filter(function (d) { return d.brain_path || d.path; }).map(function (d) {
        return d.brain_path ? { brain_path: d.brain_path, name: d.name } : { path: d.path, name: d.name };
      }),
      links: (st.links || []).slice()
    };
  }

  // /files/search rows as the box keeps them. A folder's path gets ONE trailing "/": the spelling the server stores for
  // a folder document, so "already added" is one string comparison, here and in the team's Info tab.
  function searchRows(items) {
    return (items || []).map(function (it) {
      var dir = it.type === "dir";
      return { path: dir ? String(it.path || "").replace(/\/+$/, "") + "/" : it.path, name: it.name, dir: dir };
    });
  }

  function docsCount(st) { return (st.docs || []).length + (st.links || []).length; }

  function docChipsHtml(st) {
    var docs = st.docs || [], links = st.links || [];
    if (!docs.length && !links.length) return "";
    return docs.map(function (d, i) {
      var state = d.busy ? tw("teams.pick.doc_uploading") : d.err ? tw("teams.pick.doc_failed") : "";
      return '<span class="tmp-doc' + (d.err ? " is-err" : "") + (d.busy ? " is-busy" : "") + '">' +
        ic(d.dir ? "folder" : d.brain_path ? "file-text" : "upload-cloud") +
        '<span class="tmp-doc-name" title="' + esc(d.brain_path || d.name) + '">' + esc(d.name) + "</span>" +
        (state ? '<span class="tmp-doc-state">' + esc(state) + "</span>" : "") +
        '<button type="button" class="tmp-sel-x" data-doc-del="' + i + '" aria-label="' + esc(tw("teams.pick.doc_remove", { name: d.name })) +
        '">' + ic("x") + "</button></span>";
    }).join("") + links.map(function (u, i) {
      return '<span class="tmp-doc">' + ic("link") + '<span class="tmp-doc-name" title="' + esc(u) + '">' + esc(u.replace(/^https?:\/\//i, "")) +
        '</span><button type="button" class="tmp-sel-x" data-link-del="' + i + '" aria-label="' + esc(tw("teams.pick.doc_remove", { name: u })) +
        '">' + ic("x") + "</button></span>";
    }).join("");
  }

  // Search results: files and folders of the brain whose name matches (a folder row has `dir`, and its path ends in
  // "/"). One already picked says so and cannot be added twice.
  function docResultsHtml(st) {
    if (!String(st.docQuery || "").trim()) return "";
    if (st.docState === "searching") return '<div class="tmp-doc-note" role="status">' + esc(tw("teams.pick.doc_searching")) + "</div>";
    var rows = st.docResults || [];
    if (!rows.length) return '<div class="tmp-doc-note">' + esc(tw("teams.pick.doc_none")) + "</div>";
    var full = (st.docs || []).length >= DOCS_MAX;
    return rows.map(function (r, i) {
      var have = hasDoc(st, r.path);
      return '<div class="tmp-doc-res">' + ic(r.dir ? "folder" : "file-text") + '<span class="tmp-doc-res-text"><b>' + esc(r.name) + "</b><i>" + esc(r.path) +
        '</i></span><button type="button" class="ws-btn tmp-doc-pick" data-doc-add="' + i + '"' + (have || full ? " disabled" : "") + ">" +
        esc(tw(have ? "teams.pick.doc_added" : "teams.pick.doc_add")) + "</button></div>";
    }).join("");
  }

  function docsSummaryHtml(st) {
    var n = docsCount(st);
    return esc(tw("teams.pick.docs_add")) + (n ? ' <span class="tmp-chip-n">' + n + "</span>" : "");
  }

  function docsHtml(st) {
    var open = !!(st.docsOpen || docsCount(st) || st.docQuery || st.linkDraft);
    return '<details class="tmp-desc tmp-docs"' + (open ? " open" : "") + '><summary class="tmp-docs-sum">' + docsSummaryHtml(st) +
      '</summary><p class="tmp-docs-help">' + esc(tw("teams.pick.docs_help")) + '</p><div class="tmp-docs-chips">' + docChipsHtml(st) +
      '</div><div class="tmp-docs-row"><input class="tmp-doc-search" type="search" value="' + esc(st.docQuery || "") + '" placeholder="' +
      esc(tw("teams.pick.doc_search_ph")) + '" aria-label="' + esc(tw("teams.pick.doc_search_ph")) + '">' +
      '<button type="button" class="ws-btn tmp-doc-upload">' + ic("upload-cloud") + " " + esc(tw("teams.pick.doc_upload")) + "</button></div>" +
      '<div class="tmp-doc-results">' + docResultsHtml(st) + '</div><div class="tmp-docs-row"><input class="tmp-link-input" type="url" value="' +
      esc(st.linkDraft || "") + '" placeholder="' + esc(tw("teams.pick.link_ph")) + '" aria-label="' + esc(tw("teams.pick.link_ph")) + '">' +
      '<button type="button" class="ws-btn tmp-link-add">' + esc(tw("teams.pick.link_add")) + "</button></div>" +
      (st.linkBad ? '<div class="tmp-doc-note tmp-doc-warn" role="alert">' + esc(tw("teams.pick.link_bad")) + "</div>" : "") + "</details>";
  }

  function face(a, size) {
    var A = typeof window !== "undefined" && window.JavisAvatar;
    if (A && A.html && a && a.slug) {
      return '<span class="tmp-face" aria-hidden="true">' + A.html({ slug: a.slug, avatar: a.avatar || undefined }, size) + "</span>";
    }
    var n = String((a && (a.name || a.slug)) || "?").trim();
    return '<span class="tmp-face tmp-initial" aria-hidden="true">' + esc(n.charAt(0).toUpperCase()) + "</span>";
  }

  // Ảnh nhóm xem trước: ghép từ những trợ lý đã chọn (tối đa bốn), giống ảnh nhóm ở danh sách. Chưa chọn ai thì là ô trống.
  function previewHtml(roster, st) {
    var sel = (st.selected || []).slice(0, 4);
    if (!sel.length) return '<span class="tmp-preview tmp-preview-empty" aria-hidden="true">' + ic("users") + "</span>";
    return '<span class="tmp-preview tmp-preview-' + sel.length + '" role="img" aria-label="' +
      esc(tw("teams.pick.preview", { n: (st.selected || []).length })) + '">' + sel.map(function (s) {
        return face(bySlug(roster, s) || { slug: s, name: s }, sel.length === 1 ? 48 : 24);
      }).join("") + "</span>";
  }

  function tagsHtml(roster, st) {
    var tags = tagsOf(roster);
    if (!tags.length) return "";
    var untagged = live(roster).filter(function (a) { return !(a.tags || []).length; }).length;
    var chip = function (key, label, n) {
      var on = (st.tag || "") === key;
      return '<button type="button" class="tmp-chip' + (on ? " is-on" : "") + '" data-pick-tag="' + esc(key) + '" aria-pressed="' +
        (on ? "true" : "false") + '">' + esc(label) + (n != null ? ' <span class="tmp-chip-n">' + n + "</span>" : "") + "</button>";
    };
    return '<div class="tmp-tags" role="group" aria-label="' + esc(tw("teams.pick.tags")) + '">' +
      chip("", tw("teams.pick.all"), null) + tags.map(function (t) { return chip(t.key, t.label, t.count); }).join("") +
      (untagged ? chip(NO_TAG, tw("teams.pick.untagged"), untagged) : "") + "</div>";
  }

  function selectedHtml(roster, st) {
    var sel = st.selected || [];
    var create = st.mode === "create";
    if (!sel.length) return '<div class="tmp-selected tmp-selected-empty">' + esc(tw("teams.pick.none_selected")) + "</div>";
    var many = create && sel.length > 1;
    return '<div class="tmp-selected" aria-label="' + esc(tw("teams.pick.selected_label")) + '">' + sel.map(function (s) {
      var a = bySlug(roster, s) || { slug: s, name: s };
      var name = a.name || a.slug;
      var lead = create && st.leader === s;
      // Điều phối chọn ngay trên chip: nhiều người thì mỗi chip có nút; một người thì chip mang sẵn nhãn Điều phối.
      var leadCtl = !create ? "" : many ? '<button type="button" class="tmp-lead' + (lead ? " is-on" : "") + '" data-pick-leader="' +
        esc(s) + '" aria-pressed="' + (lead ? "true" : "false") + '" title="' + esc(tw("teams.pick.make_leader", { name: name })) +
        '">' + esc(tw("teams.pick.leader_short")) + "</button>" : lead ? '<span class="tmp-lead is-on">' +
        esc(tw("teams.pick.leader_short")) + "</span>" : "";
      return '<span class="tmp-sel' + (lead ? " is-lead" : "") + '">' + face(a, 24) + '<span class="tmp-sel-name">' + esc(name) +
        "</span>" + leadCtl + '<button type="button" class="tmp-sel-x" data-pick-toggle="' + esc(s) + '" aria-label="' +
        esc(tw("teams.pick.unselect", { name: name })) + '">' + ic("x") + "</button></span>";
    }).join("") + "</div>" + leaderHtml(roster, st);
  }

  function listHtml(roster, st) {
    var sel = st.selected || [];
    var owner = st.mode === "create" ? '<div class="tmp-row tmp-owner"><span class="tmp-face tmp-initial tmp-you" aria-hidden="true">' +
      esc(tw("teams.pick.you").charAt(0)) + '</span><span class="tmp-text"><span class="tmp-name">' + esc(tw("teams.pick.you")) +
      '</span><span class="tmp-role">' + esc(tw("teams.pick.you_role")) + '</span></span><span class="tmp-badge">' +
      esc(tw("teams.pick.owner_badge")) + "</span></div>" : "";
    if (st.rosterState === "loading" && !live(roster).length) {
      return owner + '<div class="tmp-empty tmp-loading" role="status">' + esc(tw("teams.pick.loading")) + "</div>";
    }
    if (st.rosterState === "error" && !live(roster).length) {
      return owner + '<div class="tmp-empty tmp-load-error" role="alert">' + esc(tw("teams.pick.load_error")) +
        ' <button type="button" class="ws-btn tmp-reload">' + esc(tw("teams.pick.reload")) + "</button></div>";
    }
    var rows = visible(roster, st);
    if (!rows.length) {
      return owner + '<div class="tmp-empty">' + esc(tw(live(roster).length ? "teams.pick.no_match" : "teams.pick.no_agents")) + "</div>";
    }
    return owner + rows.map(function (a) {
      var already = joined(st, a.slug);
      var on = already || sel.indexOf(a.slug) >= 0;
      var sub = a.role || (a.tags || []).join(" · ");
      return '<label class="tmp-row' + (on ? " is-on" : "") + (already ? " is-joined" : "") + '"><input type="checkbox" class="tmp-check" data-pick-slug="' +
        esc(a.slug) + '"' + (on ? " checked" : "") + (already ? " disabled" : "") + ">" + face(a, 40) +
        '<span class="tmp-text"><span class="tmp-name">' + esc(a.name || a.slug) + "</span>" +
        (already ? '<span class="tmp-role tmp-joined">' + esc(tw("teams.pick.joined")) + "</span>" :
          sub ? '<span class="tmp-role">' + esc(sub) + "</span>" : "") +
        '</span><span class="tmp-tick" aria-hidden="true">' + (on ? ic("check") : "") + "</span></label>";
    }).join("");
  }

  // Dòng giải thích Điều phối dưới các chip đã chọn (thay ô chọn riêng). Bỏ người đang Điều phối thì báo rõ.
  function leaderHtml(roster, st) {
    if (st.mode !== "create" || !(st.selected || []).length) return "";
    if (st.leaderDropped && !st.leader) {
      return '<div class="tmp-leader tmp-leader-warn" role="status">' + esc(tw("teams.pick.leader_dropped")) + "</div>";
    }
    if (!st.leader) return '<div class="tmp-leader tmp-leader-warn" role="status">' + esc(tw("teams.pick.leader_empty")) + "</div>";
    var a = bySlug(roster, st.leader) || { name: st.leader };
    return '<div class="tmp-leader">' + esc(tw((st.selected || []).length > 1 ? "teams.pick.leader_many" : "teams.pick.leader_one",
      { name: a.name || a.slug || st.leader })) + "</div>";
  }

  function footerHtml(st) {
    var n = (st.selected || []).length;
    var main = st.mode === "create" ? tw(st.saving ? "teams.pick.creating" : "teams.pick.create")
      : tw(st.saving ? "teams.pick.adding" : "teams.pick.add", { n: n });
    return '<div class="tmp-foot"><span class="tmp-count">' + esc(tw(st.mode === "create" ? "teams.pick.count" : "teams.pick.count_new",
      { n: n })) + "</span>" +
      '<button type="button" class="ws-btn tmp-cancel">' + esc(tw("teams.pick.cancel")) + "</button>" +
      '<button type="button" class="ws-btn tm-primary tmp-submit"' + (canSubmit(st) ? "" : " disabled") + ">" + esc(main) +
      "</button></div>";
  }

  function html(st, roster) {
    var create = st.mode === "create";
    var title = tw(create ? "teams.pick.title_create" : "teams.pick.title_add");
    var head = '<div class="tmp-head"><h2 class="tmp-title" id="tmp-title">' + esc(title) + "</h2>" +
      '<button type="button" class="tmp-close tmp-cancel" aria-label="' + esc(tw("teams.pick.close")) + '">' + ic("x") +
      "</button></div>";
    // Không có nút đổi ảnh nhóm: ảnh nhóm ghép từ ảnh trợ lý, chưa có chức năng lưu ảnh riêng.
    var descOpen = !!(st.desc || st.descOpen);
    var name = create ? '<div class="tmp-namebox"><span class="tmp-preview-box">' + previewHtml(roster, st) + "</span>" +
      '<div class="tmp-namecol"><label class="tmp-field"><span>' + esc(tw("teams.name")) + "</span>" +
      '<input class="tmp-name-input" maxlength="120" value="' + esc(st.name || "") + '" placeholder="' +
      esc(tw("teams.pick.name_ph")) + '"></label><details class="tmp-desc"' + (descOpen ? " open" : "") + '>' +
      '<summary class="tmp-desc-sum">' + esc(tw("teams.pick.desc_add")) + '</summary><input class="tmp-desc-input" maxlength="2000" value="' +
      esc(st.desc || "") + '" placeholder="' + esc(tw("teams.pick.desc_ph")) + '" aria-label="' + esc(tw("teams.description")) +
      '"></details></div></div>' + '<div class="tmp-docs-box">' + docsHtml(st) + "</div>" : "";
    var err = st.error ? '<div class="tmp-error" role="alert">' + esc(st.error) + "</div>" : "";
    return '<div class="tmp-layer"><div class="tmp-scrim tmp-cancel"></div><div class="tmp-dialog" role="dialog" aria-modal="true" ' +
      'aria-labelledby="tmp-title">' + head + '<div class="tmp-body">' + name +
      '<div class="tmp-search"><span class="tmp-search-ico" aria-hidden="true">' + ic("search") + "</span>" +
      '<input class="tmp-search-input" type="search" value="' + esc(st.query || "") + '" placeholder="' +
      esc(tw("teams.pick.search_ph")) + '" aria-label="' + esc(tw("teams.pick.search_ph")) + '"></div>' +
      '<div class="tmp-tags-box">' + tagsHtml(roster, st) + "</div>" +
      '<div class="tmp-selected-box">' + selectedHtml(roster, st) + "</div>" +
      '<div class="tmp-list" role="list">' + listHtml(roster, st) + "</div>" + err + "</div>" +
      '<div class="tmp-foot-box">' + footerHtml(st) + "</div></div></div>";
  }

  var api = { fold: fold, tagsOf: tagsOf, visible: visible, toggle: toggle, normalize: normalize, autoName: autoName,
    canSubmit: canSubmit, html: html, listHtml: listHtml, selectedHtml: selectedHtml, tagsHtml: tagsHtml,
    leaderHtml: leaderHtml, footerHtml: footerHtml, previewHtml: previewHtml, setLeader: setLeader, NO_TAG: NO_TAG,
    DOCS_MAX: DOCS_MAX, docsBusy: docsBusy, hasDoc: hasDoc, addDoc: addDoc, removeDoc: removeDoc, cleanLink: cleanLink,
    addLink: addLink, removeLink: removeLink, docPayload: docPayload, docsCount: docsCount, docsHtml: docsHtml,
    docChipsHtml: docChipsHtml, docResultsHtml: docResultsHtml, docsSummaryHtml: docsSummaryHtml, searchRows: searchRows,
    setStrings: function (o) { FALLBACK = o || {}; } };
  if (typeof window !== "undefined") window.JavisTeamPicker = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
