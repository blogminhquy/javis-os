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
    return st.mode !== "create" || !!st.leader;
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
      '"></details></div></div>' : "";
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
    setStrings: function (o) { FALLBACK = o || {}; } };
  if (typeof window !== "undefined") window.JavisTeamPicker = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
