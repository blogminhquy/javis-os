/* limit-resume.js - the "het luot goi thue bao, tu chay lai luc HH:MM" trong khung chat.

   Claude Code, Codex, Grok Build hay Antigravity bao het luot thi server (limit_resume.py)
   ghi mot muc cho va tu chay lai dung cau hoi do khi han muc mo. File nay chi VE trang thai
   cua muc cho do duoi bong bong bao loi, va gui hai hanh dong len server:
     - o tick "Tu tiep tuc khi han muc reset"  -> {action:"resume_auto", session_id, enabled}
     - nut "Chay lai ngay"                       -> {action:"resume_now",  session_id}

   Server la nguoi giu gio. Trang nay khong tu gui lai tin nhan khi den gio: tab dong, dien
   thoai tat man hinh thi lich van chay, va mo lai tab thi khung `hello` mang danh sach muc
   cho de dung lai the.

   Cac ham thuan (describe, fmtWhen, fmtLeft) tach rieng de test bang node, khong can DOM.
   KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  var TICK_MS = 20000;         // nhip cap nhat dong "con X phut"
  var ENGINE_LABEL = {
    "claude-code": "Claude Code", "codex": "ChatGPT (Codex)", "grok-cli": "Grok Build",
    "antigravity-cli": "Antigravity CLI",
  };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  // "13:01" neu cung ngay, "13:01 ngay 06/09" neu khac ngay. Gio theo may cua nguoi xem.
  function fmtWhen(epoch, now) {
    if (!epoch) return "";
    var d = new Date(epoch * 1000);
    var n = new Date((now == null ? Date.now() / 1000 : now) * 1000);
    var hm = pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    if (d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate()) return hm;
    return hm + " ngày " + pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1);
  }

  // "con 1 gio 5 phut" / "con 3 phut" / "con duoi 1 phut". Am hoac 0 -> "".
  function fmtLeft(seconds) {
    var s = Math.floor(Number(seconds) || 0);
    if (s <= 0) return "";
    if (s < 60) return "còn dưới 1 phút";
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    if (h <= 0) return "còn " + m + " phút";
    return "còn " + h + " giờ" + (m ? " " + m + " phút" : "");
  }

  /* Tu mot muc cho (payload cua server) suy ra chu de ve. Tra:
       { text, left, auto, showAuto, showNow, busy }
     - text: dong chinh; left: phan "(con X phut)" cap nhat theo nhip;
     - showAuto: co ve o tick khong; auto: o tick dang bat;
     - showNow: co ve nut "Chay lai ngay" khong; busy: dang chay (khoa het nut). */
  function describe(info, now) {
    info = info || {};
    now = now == null ? Date.now() / 1000 : now;
    var state = info.state || "pending";
    var at = Number(info.resume_at) || 0;
    var when = fmtWhen(at, now);
    var leftS = at ? at - now : 0;
    var out = { text: "", left: "", auto: !!info.auto, showAuto: false, showNow: true, busy: false };

    if (state === "running") {
      out.text = "Đang chạy lại câu hỏi này...";
      out.busy = true; out.showNow = false;
      return out;
    }
    if (state === "done") {
      out.text = "Đã chạy lại lúc " + fmtWhen(info.done_at || now, now) + ".";
      out.showNow = false;
      return out;
    }
    if (state === "cancelled") {
      out.text = "Đã bỏ lịch chạy lại vì bạn gửi tin mới.";
      out.showNow = false;
      return out;
    }
    if (state === "gone") {
      out.text = "Không còn lịch chạy lại (máy chủ vừa khởi động lại?). Bấm Gửi lại ở tin của bạn nếu vẫn cần.";
      out.showNow = false;
      return out;
    }
    if (state === "pending") {
      // Khung error vua toi, server chua noi co hen hay khong. Chi nhac moc mo lai.
      out.text = when ? "Hạn mức mở lại lúc " + when + "." : "";
      out.showNow = false;
      return out;
    }
    // scheduled | off
    if (state === "scheduled" && info.auto) {
      out.showAuto = true;
      if (leftS > 0) {
        out.text = "Tự chạy lại lúc " + when;
        out.left = fmtLeft(leftS);
      } else {
        out.text = "Đến giờ rồi, đang chờ máy chủ chạy lại...";
      }
      return out;
    }
    var reason = info.reason || "off";
    if (reason === "no_reset") {
      out.text = "Nhà cung cấp không nói lúc nào mở lại, nên không hẹn giờ được.";
    } else if (reason === "too_far") {
      out.text = "Hạn mức mở lại lúc " + when + ", quá xa để hẹn tự chạy.";
    } else if (reason === "max_attempts") {
      out.text = "Đã tự chạy lại " + (info.max_attempts || 3) + " lần mà vẫn hết lượt, thôi không hẹn nữa.";
    } else if (reason === "off") {
      out.showAuto = true;
      out.text = when ? "Hạn mức mở lại lúc " + when + ". Không tự chạy lại." : "Không tự chạy lại.";
    } else {
      out.text = when ? "Hạn mức mở lại lúc " + when + "." : "";
    }
    return out;
  }

  // ---------------- DOM ----------------
  var pending = {};      // sid -> info (payload server + state)
  var cards = {};        // sid -> phan tu .jv-resume dang ve
  var timer = null;

  function send(obj) {
    try { if (typeof window.JavisWsSend === "function") return window.JavisWsSend(obj); } catch (e) {}
    return false;
  }

  function html(sid, info) {
    var d = describe(info);
    var eng = ENGINE_LABEL[info.engine] || "";
    var h = '<div class="jv-resume-line">' +
      (d.busy ? '<span class="jv-resume-spin"></span>' : '<span class="jv-resume-dot' + (info.state === "scheduled" && info.auto ? " on" : "") + '"></span>') +
      '<span class="jv-resume-text">' + esc(d.text) + '</span>' +
      (d.left ? ' <span class="jv-resume-left">(' + esc(d.left) + ')</span>' : "") +
      '</div>';
    if (d.showAuto) {
      h += '<label class="jv-resume-auto"><input type="checkbox"' + (d.auto ? " checked" : "") +
        (d.busy ? " disabled" : "") + '> Tự tiếp tục khi hạn mức reset</label>';
    }
    if (d.showNow) {
      h += '<div class="jv-resume-row"><button type="button" class="jv-resume-now"' + (d.busy ? " disabled" : "") +
        '>Chạy lại ngay</button>' +
        (eng ? '<span class="jv-resume-eng">' + esc(eng) + '</span>' : "") + '</div>';
    }
    return h;
  }

  function paint(sid) {
    var el = cards[sid], info = pending[sid];
    if (!el || !info) return;
    el.innerHTML = html(sid, info);
    var cb = el.querySelector("input[type=checkbox]");
    if (cb) cb.addEventListener("change", function () {
      info.auto = !!cb.checked;
      info.state = info.auto ? "scheduled" : "off";
      info.reason = info.auto ? "" : "off";
      paint(sid);
      send({ action: "resume_auto", session_id: sid, enabled: info.auto });
    });
    var btn = el.querySelector(".jv-resume-now");
    if (btn) btn.addEventListener("click", function () {
      if (!send({ action: "resume_now", session_id: sid })) return;
      info.state = "running";
      paint(sid);
    });
    armTimer();
  }

  function tick() {
    var alive = false;
    Object.keys(cards).forEach(function (sid) {
      var el = cards[sid], info = pending[sid];
      if (!el || !info || !el.isConnected) { delete cards[sid]; return; }
      if (info.state !== "scheduled" || !info.auto) return;
      alive = true;
      var d = describe(info);
      var t = el.querySelector(".jv-resume-text"), l = el.querySelector(".jv-resume-left");
      if (t) t.textContent = d.text;
      if (l) { if (d.left) l.textContent = "(" + d.left + ")"; else l.remove(); }
    });
    if (!alive && timer) { clearInterval(timer); timer = null; }
  }
  function armTimer() { if (!timer) timer = setInterval(tick, TICK_MS); }

  // Gan the vao mot bong bong Javis (thuong la bong bong bao loi vua ve).
  function attach(msgEl, sid, limit) {
    if (!msgEl || !sid) return null;
    var bubble = msgEl.querySelector(".bubble") || msgEl;
    var old = cards[sid];
    if (old && old !== bubble.querySelector(".jv-resume")) { try { old.remove(); } catch (e) {} }
    var el = bubble.querySelector(".jv-resume");
    if (!el) {
      el = document.createElement("div");
      el.className = "jv-resume";
      el.setAttribute("data-sid", sid);
      bubble.appendChild(el);
    }
    var info = pending[sid] || {};
    if (limit) {
      info.engine = limit.engine || info.engine || "";
      info.scope = limit.scope || info.scope || "";
      if (limit.reset_epoch) info.resume_at = Number(limit.reset_epoch) || 0;
      if (limit.resume_at) info.resume_at = Number(limit.resume_at) || 0;
      if (!info.state) info.state = "pending";
    }
    pending[sid] = info;
    cards[sid] = el;
    paint(sid);
    return el;
  }

  // Khung {type:"resume"} tu server: cap nhat muc cho, ve lai neu the dang hien.
  function onFrame(data) {
    var sid = data && data.session_id;
    if (!sid) return;
    var info = pending[sid] || (pending[sid] = {});
    Object.keys(data).forEach(function (k) { if (k !== "type") info[k] = data[k]; });
    if (data.state === "cancelled" || data.state === "gone") {
      // Muc cho khong con tren server; giu the de nguoi dung doc ly do, nhung thoi theo doi.
      paint(sid);
      delete pending[sid];
      delete cards[sid];
      return;
    }
    paint(sid);
  }

  // Luot chay lai vua ket thuc (turn_done): the dang "running" chuyen sang "done".
  function turnDone(sid) {
    var info = pending[sid];
    if (!info || info.state !== "running") return;
    info.state = "done";
    info.done_at = Date.now() / 1000;
    paint(sid);
    delete pending[sid];
    delete cards[sid];
  }

  // Khung hello: danh sach muc cho cua server thay cho bo nho cua trang.
  function fromHello(list, activeSid) {
    var next = {};
    (list || []).forEach(function (it) {
      if (!it || !it.session_id) return;
      it.state = it.auto ? "scheduled" : "off";
      next[it.session_id] = it;
    });
    // Giu the dang "running" (luot chay lai dang chay: server khong con muc cho, nhung the
    // van phai noi "dang chay" cho toi turn_done).
    Object.keys(pending).forEach(function (sid) {
      if (pending[sid].state === "running" && !next[sid]) next[sid] = pending[sid];
    });
    pending = next;
    Object.keys(cards).forEach(function (sid) { if (!pending[sid]) delete cards[sid]; });
    if (activeSid) renderFor(activeSid);
  }

  // Phien vua mo (F5 hoac chon o Lich su): co muc cho thi gan the vao bong bong Javis cuoi.
  // Cau "het luot" luon la tin cuoi cua phien khi con muc cho (gui tin moi la server huy muc).
  function renderFor(sid) {
    var info = pending[sid];
    if (!info) return null;
    var area = document.getElementById("chatArea");
    if (!area) return null;
    var have = area.querySelector('.jv-resume[data-sid="' + sid + '"]');
    if (have) { cards[sid] = have; paint(sid); return have; }
    var msgs = area.querySelectorAll(".msg.msg-javis");
    var last = msgs.length ? msgs[msgs.length - 1] : null;
    if (!last) return null;
    return attach(last, sid, null);
  }

  var api = {
    describe: describe, fmtWhen: fmtWhen, fmtLeft: fmtLeft,
    attach: attach, onFrame: onFrame, turnDone: turnDone, fromHello: fromHello, renderFor: renderFor,
    _pending: function () { return pending; },
  };
  if (typeof window !== "undefined") window.JavisResume = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
