/* workspace.js - trang Cộng sự: chat với từng trợ lý và từng quy trình trên cùng khung chat.

   Ba cột: trái = danh sách (Trợ lý | Quy trình), giữa = khung chat MƯỢN của app (console.js
   mượn/trả node, file này chỉ nhận slot), phải = cài đặt trợ lý hoặc tiến độ + lịch sử chạy.

   Mỗi cộng sự có phiên riêng trong kho phiên (kênh agent:<slug> / workflow:<slug>). Gửi tin
   vẫn đi đường WebSocket thường của app.js; server nhìn kênh của phiên mà rẽ nhánh. Khung
   wf_event (tiến độ từng bước) app.js chuyển vào onWfEvent() ở đây.

   Phần thuần (sapXep, loc, tienDoMoi, apDung, phanTram) phơi ra để test bằng node.
   Ghi chú: KHÔNG dùng ký tự em dash. Chữ hiện ra lấy từ từ điển window.t. */
(function () {
  "use strict";
  var t = function (k, v) { return (window.t ? window.t(k, v) : k); };
  var ic = function (n, o) { return (window.ic ? window.ic(n, o) : ""); };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); }
  function khongDau(s) { return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase(); }
  function brain() { try { return window.JavisSessions ? window.JavisSessions.brain() : "brain"; } catch (e) { return "brain"; } }
  async function api(url, opt) { var r = await fetch(url, opt); return r.json(); }
  function fd(o) { var f = new FormData(); Object.keys(o).forEach(function (k) { f.append(k, o[k]); }); return f; }

  function avatar(a, size, state) { return window.JavisAvatar ? window.JavisAvatar.html(a, size, state) : ic("bot"); }
  function agentOf(slug) { return S.agents.find(function (a) { return a.slug === slug || a.name === slug; }) || {slug: slug || ""}; }
  // daTai = đã tải được danh sách ÍT NHẤT MỘT LẦN. Phân biệt "brain mới tinh, chưa có cộng sự
  // nào" với "gọi /agents hỏng nên không biết có gì": cả hai đều để lại mảng rỗng, nhưng cái
  // sau mà bày màn khởi đầu "Chưa có cộng sự nào" là nói dối người dùng về một lỗi mạng.
  var opening = 0, ready = false, active = false, pendingCommand = null, daTai = false;
  // Phiên chat của BỘ NÃO CHÍNH đang mở trước khi vào trang này, để lúc rời trang trả khung
  // chat về đúng cuộc đang dở (xem traKhungChat).
  var _phienTruoc = null;
  function chatReady(value) {
    ready = value;
    var input = document.getElementById("chatInput");
    if (input) input.disabled = !value;
    var files = S.el && S.el.querySelector("#wsFiles"); if (files) files.disabled = !value;
    var run = S.el && S.el.querySelector("#wsRun");
    if (run) run.disabled = !value;
  }
  function onChatState(state) {
    if (!active || !S.el || S.loai !== "agent") return;
    S.el.querySelectorAll(".ws-id .agent-avatar, .aa-preview .agent-avatar, .ws-item.on .agent-avatar").forEach(function (el) { el.dataset.state = state || "idle"; });
  }
  // ---------- phần thuần ----------
  // Xếp theo MỐC GẦN NHẤT chứ không theo tên: cộng sự vừa dùng xong là cộng sự sắp dùng lại.
  // Mục chưa có mốc rơi xuống dưới và xếp theo tên cho ổn định (không nhảy lung tung mỗi lần vẽ).
  // Mục GHIM luôn đứng trước, trong nhóm ghim vẫn xếp theo mốc gần nhất như cũ. Ghim là lời
  // người dùng nói "cái này tôi dùng suốt", nên nó phải thắng mốc thời gian - không thì một
  // cộng sự ghim mà hai tuần không gọi sẽ tụt xuống cuối và cái ghim thành vô nghĩa.
  function sapXep(ds, khoa) {
    return ds.slice().sort(function (a, b) {
      var ga = a.pinned ? 1 : 0, gb = b.pinned ? 1 : 0;
      if (ga !== gb) return gb - ga;
      var ma = Number(a[khoa] || 0), mb = Number(b[khoa] || 0);
      if (ma !== mb) return mb - ma;
      return String(a.name || "").localeCompare(String(b.name || ""), "vi");
    });
  }
  // ---------- NHÓM: gom cộng sự theo field `group`, giống thư mục dự án bên Trò chuyện ----------
  // Chủ repo 20/09: "làm thêm phần gom nhóm giống bên trò chuyện để có thể gom nhiều agent
  // thành nhóm khác nhau". Trước đó cột trái chỉ có Ô LỌC theo nhóm; chọn "Tất cả" thì
  // danh sách phẳng, hai chục cộng sự của năm nhóm trộn vào nhau. Nay ở chế độ "Tất cả"
  // danh sách chia thành từng nhóm có tiêu đề bấm thu gọn/mở, số người bên phải, và nút
  // "..." để đổi tên cả nhóm. Dữ liệu vẫn là field `group` sẵn có trong frontmatter, nên
  // Studio, ô lọc và menu "Chuyển sang nhóm" đều nhìn thấy cùng một thứ.
  var NHOM_MD = "Chung";
  var KHOA_THU = "javis_ws_thu";                 // localStorage: nhóm đang THU GỌN, theo loại
  function nhomCua(x) { return (String((x && x.group) || "").trim()) || NHOM_MD; }
  function docThu() {
    try { return JSON.parse(localStorage.getItem(KHOA_THU) || "{}") || {}; }
    catch (e) { return {}; }
  }
  function luuThu() { try { localStorage.setItem(KHOA_THU, JSON.stringify(S.thu)); } catch (e) {} }
  // Khoá theo BRAIN + loại (như sổ nhóm trống): hai brain có nhóm trùng tên mà dùng chung sổ thu
  // gọn thì thu ở brain này là bên kia cũng thu theo.
  function khoaThu() { return brain() + "|" + S.loai; }
  function daThu(g) { return (S.thu[khoaThu()] || []).indexOf(g) >= 0; }
  function latThu(g) {
    var ds = S.thu[khoaThu()] || (S.thu[khoaThu()] = []);
    var i = ds.indexOf(g); if (i >= 0) ds.splice(i, 1); else ds.push(g);
    luuThu();
  }
  // Chia danh sách (đã lọc, đã sắp) thành các KHỐI theo thứ tự vẽ. Hàm thuần, test được:
  //   - khối "Đã ghim" đứng đầu nếu có mục ghim;
  //   - đang lọc MỘT nhóm thì phần còn lại là một khối duy nhất (nhãn "Còn lại" chỉ khi
  //     có khối ghim phía trên, như trước);
  //   - "Tất cả" thì mỗi nhóm một khối, xếp theo tên (tiếng Việt), "Chung" xuống cuối vì
  //     đó là chỗ của người chưa được xếp vào đâu, giống "Không thuộc dự án" bên Trò chuyện.
  // `nhomTrong`: nhóm vừa tạo bằng "+ Nhóm mới" mà chưa có ai (xem docNhomTrong) - vẫn vẽ
  // tiêu đề với số 0 để người dùng thấy nhóm mình vừa lập rồi kéo cộng sự vào.
  function gomNhom(ds, nhomLoc, nhomTrong) {
    var ghim = (ds || []).filter(function (x) { return x.pinned; });
    var thuong = (ds || []).filter(function (x) { return !x.pinned; });
    var ra = [];
    if (ghim.length) ra.push({ ghim: true, nhom: "", items: ghim });
    if (nhomLoc) {
      if (thuong.length) ra.push({ ghim: false, nhom: nhomLoc, items: thuong, theoNhom: false, tieuDe: !!ghim.length });
      return ra;
    }
    var theo = {};
    thuong.forEach(function (x) { var g = nhomCua(x); (theo[g] = theo[g] || []).push(x); });
    (nhomTrong || []).forEach(function (g) { g = String(g || "").trim(); if (g && g !== NHOM_MD && !theo[g]) theo[g] = []; });
    Object.keys(theo).sort(function (a, b) {
      if (a === NHOM_MD) return 1; if (b === NHOM_MD) return -1;
      return a.localeCompare(b, "vi");
    }).forEach(function (g) { ra.push({ ghim: false, nhom: g, items: theo[g], theoNhom: true, tieuDe: true }); });
    return ra;
  }

  function loc(ds, q, nhom) {
    var nq = khongDau(q || "").trim();
    return ds.filter(function (x) {
      if (nhom && (x.group || "Chung") !== nhom) return false;
      if (!nq) return true;
      var text = khongDau([x.name, x.role, x.description, x.slug, x.group].join(" "));
      return nq.split(/\s+/).every(function (word) { return text.indexOf(word) >= 0; });
    });
  }
  function bucMoi(i) { return { i: i, agent: "", trang_thai: "cho", loi: "" }; }
  function tienDoMoi(n) {
    var buoc = [];
    for (var i = 0; i < n; i++) buoc.push(bucMoi(i));
    return { buoc: buoc, hien_tai: -1, trang_thai: "cho", cho_duyet: null, run_id: "" };
  }
  // Máy trạng thái của MỘT lần chạy, ăn thẳng sự kiện của execute_workflow (server/workflow_chat.py).
  // Tách khỏi phần vẽ để test bằng node: đây là chỗ dễ sai nhất mà nhìn màn hình không ra.
  function apDung(st, ev) {
    var i = Number(ev.i);
    if (ev.type === "start") {
      st.run_id = ev.run_id || "";
      while (st.buoc.length < Number(ev.steps || 0)) st.buoc.push(bucMoi(st.buoc.length));
      st.trang_thai = "dang";
    } else if (ev.type === "step_start") {
      while (st.buoc.length <= i) st.buoc.push(bucMoi(st.buoc.length));
      st.buoc[i].agent = ev.agent || st.buoc[i].agent;
      st.buoc[i].trang_thai = "dang";
      st.hien_tai = i; st.trang_thai = "dang";
    } else if (ev.type === "step_done") {
      // Bước đã mang dấu HỎNG thì không có sự kiện nào sau đó xoá được dấu ấy. Server hiện
      // không còn gửi step_done sau step_error nữa, nhưng luật phải tự đứng được ở đây: máy
      // trạng thái này còn ăn lại sự kiện của phiên cũ, và một tích xanh sai còn tệ hơn
      // không có tích nào.
      if (st.buoc[i] && st.buoc[i].trang_thai !== "loi") st.buoc[i].trang_thai = "xong";
    } else if (ev.type === "step_error") {
      // Bước mà động cơ đã báo lỗi là bước HỎNG, không phải bước "đang làm dở". Trước 0.59.2
      // đây chỉ ghi câu lỗi vào .loi rồi để step_done đè trạng thái thành "xong", nên cột
      // phải hiện tích xanh cho đúng cái bước vừa chết.
      if (st.buoc[i]) { st.buoc[i].trang_thai = "loi"; st.buoc[i].loi = ev.content || st.buoc[i].loi; }
    } else if (ev.type === "wait_user") {
      st.trang_thai = "cho";
      st.cho_duyet = { node: ev.node || "", prompt: ev.prompt || "", task_id: ev.task_id || "", code: ev.code || "" };
    } else if (ev.type === "error") {
      st.trang_thai = "loi";
      // Lỗi của một BƯỚC mang sẵn số bước; lỗi chung (luồng đứt) thì không, lúc đó đánh dấu
      // bước đang chạy. Bước "cho" (chưa tới lượt) giữ nguyên - nó không hỏng, nó không chạy.
      var k = isFinite(i) ? i : st.hien_tai;
      if (k >= 0 && st.buoc[k] && st.buoc[k].trang_thai !== "xong") {
        st.buoc[k].trang_thai = "loi";
        st.buoc[k].loi = ev.content || st.buoc[k].loi;
      }
    } else if (ev.type === "stopped") {
      // Người dùng bấm Dừng giữa chừng. KHÔNG phải lỗi (không có gì hỏng) và cũng không phải
      // xong (chưa ra kết quả), nên nó là một trạng thái thứ ba. Thiếu nhánh này thì máy trạng
      // thái đứng mãi ở "dang": icon bên trái quay không ngừng và cột phải vẫn ghi "Đang chạy
      // Bước 1/3" cho một lần chạy đã chết từ lâu (chủ dự án báo 15/09).
      st.trang_thai = "dung"; st.cho_duyet = null;
      st.buoc.forEach(function (b) { if (b.trang_thai === "dang") b.trang_thai = "cho"; });
    } else if (ev.type === "done") {
      st.trang_thai = "xong"; st.cho_duyet = null;
      // Bước đã hỏng thì KHÔNG đổi thành xong. Server không còn gửi `done` sau một bước hỏng,
      // nhưng luật ở đây phải tự đứng được: máy trạng thái này còn ăn sự kiện của phiên cũ
      // mở lại, và một tích xanh sai còn tệ hơn không có tích nào.
      st.buoc.forEach(function (b) { if (b.trang_thai !== "loi") b.trang_thai = "xong"; });
    }
    return st;
  }
  function phanTram(st) {
    if (!st.buoc.length) return 0;
    if (st.trang_thai === "xong") return 100;
    return Math.round(st.buoc.filter(function (b) { return b.trang_thai === "xong"; }).length / st.buoc.length * 100);
  }

  // ---------- trạng thái trang ----------
  // tabPhai = tab đang mở ở cột phải: "lichsu" (lần chạy + hội thoại cũ của cộng sự này),
  // "files" (cây thư mục MƯỢN của màn chính) hay "cai" (cài đặt trợ lý / tiến độ quy trình).
  //
  // THỨ TỰ (chủ dự án chốt 16/09): Lịch sử trước, rồi Thư mục, Cài đặt sau cùng. Việc hằng
  // ngày là mở lại một hội thoại cũ và mở một file, còn cài đặt trợ lý thì sửa một lần rồi
  // thôi - để nó ở tab đầu là bắt người dùng bấm thêm một cú mỗi lần vào trang.
  // Thứ tự nút là chung, còn tab MỞ SẴN thì khác nhau theo loại: quy trình mở ở Cài đặt vì
  // nút Chạy quy trình nằm ở đó (chủ dự án chốt 17/09) - xem S.tabCua.
  var TAB_PHAI = ["lichsu", "files", "cai"];   // ba tab cột phải, thứ tự đúng như lúc vẽ
  // Danh sách trái chỉ vẽ TRANG mục đầu, bấm "Xem thêm" mở thêm TRANG nữa - đúng cỡ trang của
  // cột lịch sử (sessions-ui.js: PAGE = 20) để cả app cùng một nhịp. Brain của chủ dự án có
  // vài chục trợ lý, vẽ hết một lượt là một cột cuộn dài dằng dặc mà chín phần mười số hàng
  // chẳng ai nhìn tới.
  var TRANG = 20;
  var S = { loai: "agent", q: "", nhom: "", thu: docThu(), agents: [], workflows: [], chon: { agent: null, workflow: null },
            el: null, tienDo: {}, sessionCuaPhien: {}, tabPhai: "lichsu",
            // Tab cột phải NHỚ RIÊNG theo loại. Trợ lý mở ở Lịch sử (chốt 16/09, xem TAB_PHAI);
            // quy trình mở ở Cài đặt vì nút Chạy nằm ở đó (chủ dự án chốt 17/09). Dùng chung
            // một ô nhớ thì vừa xem xong hội thoại của một trợ lý, sang quy trình là Lịch sử
            // đè lên và nút Chạy biến mất.
            tabCua: { agent: "lichsu", workflow: "cai" },
            hien: TRANG, lanChay: {},
            menu: null };   // tienDo[session_id] = tiến độ lần chạy đang xem

  function danhSach() { return S.loai === "agent" ? S.agents : S.workflows; }
  function kenh(item) { return (S.loai === "agent" ? "agent:" : "workflow:") + item.slug; }
  function dangChon() { var slug = S.chon[S.loai]; return danhSach().find(function (x) { return x.slug === slug; }) || null; }
  var VI_TRI_KEY = "javis_workspace_view";
  function docViTri() {
    try {
      var v = JSON.parse(localStorage.getItem(VI_TRI_KEY) || "null");
      return v && v.brain === brain() && v.sessionId ? v : null;
    } catch (e) { return null; }
  }
  function luuViTri(id) {
    var item = dangChon();
    if (!id || !item) return;
    try { localStorage.setItem(VI_TRI_KEY, JSON.stringify({
      brain: brain(), kind: S.loai, slug: item.slug, sessionId: id,
      mainSessionId: _phienTruoc,
    })); } catch (e) {}
  }
  function cacBuoc(item) { return (item && item.steps) || []; }
  // Khổ màn hình mà cột trái là NGĂN KÉO (xem khối .wspage trong console.css) - phải khớp số
  // 900px bên đó, lệch nhau là nút đóng/mở nói một đằng màn hình làm một nẻo.
  function heptLai() { try { return window.matchMedia("(max-width: 900px)").matches; } catch (e) { return false; } }
  // So theo SLUG chứ không so theo địa chỉ object: taiDanhSach() thay cả mảng bằng object mới
  // sau mỗi lần chạy xong, nên một lời gọi vẽ đang chờ mạng sẽ thấy "khác object" dù vẫn đúng
  // cộng sự đang mở, rồi âm thầm bỏ không vẽ.
  function conDangXem(item) { var x = dangChon(); return !!(item && x && x.slug === item.slug); }

  async function taiDanhSach() {
    var b = encodeURIComponent(brain());
    // `prompt=0` = danh sách NHẸ. Đo trên brain 14 trợ lý: kèm system prompt là 366 KB, bỏ ra
    // còn 2.9 KB - 99% số byte là thứ cột trái không bao giờ hiện. Qua mạng nhà, 366 KB là cả
    // giây cột trái trống trơn mỗi lần mở trang (chủ dự án 22/09: mở trang Cộng sự từ linh vật
    // vẫn lag). Prompt của ĐÚNG trợ lý đang sửa do studio.js lấy riêng qua /agents/get.
    var r = await Promise.all([api("/agents?brain=" + b + "&prompt=0"), api("/workflows?brain=" + b)]);
    S.agents = sapXep(r[0].agents || [], "last_chat_at");
    S.workflows = sapXep((r[1].workflows || []).filter(function (w) { return w.status === "active"; }), "last_run_at");
    daTai = true;
  }

  // ---------- dựng khung ----------
  function render(el, opts) {
    S.el = el; active = true; ready = false;
    // DỰNG LẠI TỪ ĐẦU, không nối tiếp lần trước. Trang này còn được dựng lại NGAY TẠI CHỖ khi
    // người dùng đổi bộ não (console.js gọi thẳng renderPage, không đi qua navigateTo nên roi()
    // KHÔNG chạy), và lúc đó mọi thứ còn sót lại đều là của brain cũ:
    //   - một moPhien đang chờ mạng sẽ mở phiên của brain cũ vào khung chat vừa dựng
    //     (chủ dự án 22/09: "khung chat hiển thị dữ liệu của hội thoại cũ") -> opening++ cắt nó;
    //   - _phienTruoc trỏ vào cuộc chính của brain cũ, rời trang là mở nhầm nó ra;
    //   - danh sách cũ mà `daTai` vẫn true thì brain mới chưa tải xong đã bày nhầm màn khởi đầu.
    opening++;
    dongMenu();            // menu nổi của lần dựng trước neo vào <body>, không chết theo DOM cũ
    _phienTruoc = null;
    S.sessionCuaPhien = {}; S.tienDo = {}; S.lanChay = {};
    S.agents = []; S.workflows = []; daTai = false;
    el.innerHTML =
      '<div class="wspage" id="wsPage">' +
        '<aside class="ws-left" id="wsLeft">' +
          '<div class="ws-seg"><button type="button" data-loai="agent">' + ic("bot") + ' ' + esc(t("ws.tab_agent")) + '</button>' +
          '<button type="button" data-loai="workflow">' + ic("workflow") + ' ' + esc(t("ws.tab_workflow")) + '</button></div>' +
          // Ô tìm KHÔNG mở sẵn (chủ repo yêu cầu): cột trái chỉ rộng 210-260px, một ô nhập
          // nằm đó suốt ngày ăn mất một dòng mà chín trên mười lần người dùng không gõ gì.
          // Bấm nút kính lúp mới bung ra, gõ xong xoá hết rồi rời đi là nó tự thu lại.
          '<div class="ws-filters" id="wsFilters">' +
            // Thanh chọn nhóm: ĐÚNG khuôn thanh project của cột trái trang Trò chuyện (nút mở
            // bảng nổi + nút tạo nhóm), thay cho ô <select> cũ. Chủ repo 20/09: "xem phần
            // project trong trò chuyện thì agent làm tương tự".
            '<div class="cside-proj ws-nhom-bar" id="wsGroup"></div>' +
            // Ô nhập được GIEO LẠI từ S.q, và nút mang aria-controls trỏ vào nó: câu đang lọc
            // phải luôn NHÌN THẤY ĐƯỢC. Dựng khung với ô rỗng trong khi S.q còn chữ là danh
            // sách thiếu người mà không có gì trên màn hình giải thích vì sao.
            '<button type="button" class="ws-ico ws-search-btn" id="wsSearchBtn" aria-controls="wsSearch" ' +
            'aria-expanded="' + (S.q ? "true" : "false") + '" ' +
            'title="' + esc(t("ws.search_ph")) + '" aria-label="' + esc(t("ws.search_ph")) + '">' + ic("search") + '</button>' +
            // data-esc: khai với trình sửa note (console.js _neOTextNgoai) rằng ô này TỰ xử
            // Esc. Bộ bắt phím của trình sửa gắn ở mức document + capture nên nếu không khai
            // thì Esc ở đây đóng mất file đang mở thay vì xoá chữ đang gõ.
            '<input class="ws-search" id="wsSearch" data-esc' + (S.q ? "" : " hidden") + ' value="' + esc(S.q) + '" placeholder="' + esc(t("ws.search_ph")) + '">' +
          '</div>' +
          '<div class="ws-list" id="wsList"></div>' +
          '<div class="ws-left-foot"><button type="button" class="ws-btn" id="wsNew">' + ic("plus") + ' ' + esc(t("ws.new_item")) + '</button>' +
          '<button type="button" class="ws-btn" id="wsImport">' + esc(t("ws.upload_agent")) + '</button>' +
          '<button type="button" class="ws-btn" id="wsStore">' + ic("package") + ' Javis Store</button></div>' +
        '</aside>' +
        '<div class="ws-main">' +
          '<div class="ws-bar">' +
            '<button type="button" class="ws-ico" id="wsLeftBtn" title="' + esc(t("ws.toggle_list")) + '">' + ic("panel-left") + '</button>' +
            '<button type="button" class="ws-btn" id="wsFiles">' + ic("paperclip") + ' ' + esc(t("ws.files_links")) + '</button>' +
            '<button type="button" class="ws-btn" id="wsNewChat">' + esc(t("sess.new_chat")) + '</button>' +
            // Bộ icon chưa đóng gói "panel-right" (xem icons.manifest.json) và thêm icon mới
            // phải chạy gen_icons tải mạng - lật gương panel-left bằng CSS rẻ hơn mà cùng nghĩa.
            '<button type="button" class="ws-ico lat" id="wsRightBtn" title="' + esc(t("ws.toggle_panel")) + '">' + ic("panel-left") + '</button>' +
          '</div>' +
          '<div class="ws-id" id="wsIdentity"></div>' +
          // Màn khởi đầu: danh sách rỗng thì không có phiên nào để mở, ô nhập bị khoá, nên
          // chỗ khung chat là hai nút tạo. Nằm TRƯỚC #wsSlot trong DOM cho thuận mắt, còn
          // khung chat thì ẩn đi bằng lớp .onboard-on (xem console.css).
          '<div class="ws-onboard" id="wsOnboard" hidden></div>' +
          '<div class="ws-slot" id="wsSlot"></div>' +
          // Chỗ đứng cho TRÌNH SỬA khi mở một file .md từ chat hay từ cây thư mục, y như
          // #chatPageEdit của trang Trò chuyện. Thiếu nó thì _borrowNoteEditor() không tìm
          // được khung nào để mượn và cú bấm vào link file lặng lẽ không làm gì cả.
          '<div class="ws-edit" id="wsEdit" data-ne-host></div>' +
        '</div>' +
        '<aside class="ws-right" id="wsRight">' +
          '<button type="button" class="ws-ico ws-panel-close" aria-label="' + esc(t("common.close")) + '">' + ic("x") + '</button>' +
          // Hai tab của cột phải: Cài đặt | Thư mục. Dùng lại đúng lớp .cside-tabs/.cside-pane
          // của cột trái trang Trò chuyện - cùng một kiểu tab, không đẻ bộ lớp thứ hai.
          '<div class="cside-tabs ws-rtabs">' +
            '<button type="button" class="cside-tab" data-rtab="lichsu">' + ic("history") + ' ' + esc(t("ws.tab_history")) + '</button>' +
            '<button type="button" class="cside-tab" data-rtab="files">' + ic("folder-tree") + ' ' + esc(t("sess.tab_files")) + '</button>' +
            '<button type="button" class="cside-tab" data-rtab="cai">' + ic("settings") + ' ' + esc(t("ws.tab_settings")) + '</button>' +
          '</div>' +
          '<div class="cside-pane ws-rpane" data-rpane="cai" id="wsRightSet"></div>' +
          '<div class="cside-pane ws-rpane" data-rpane="lichsu" id="wsRightHistory"></div>' +
          '<div class="cside-pane ws-rpane" data-rpane="files" id="wsRightFiles"></div>' +
        '</aside>' +
      '</div>';
    if (opts && opts.borrow) opts.borrow(el.querySelector("#wsSlot"));
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.onclick = function () { S.loai = b.dataset.loai; S.nhom = ""; S.hien = TRANG; luuChon(); veTrai(); chonMacDinh(); }; });
    noiODoTim(el);
    el.querySelectorAll("[data-rtab]").forEach(function (b) { b.onclick = function () { chonTabPhai(b.dataset.rtab); }; });
    el.querySelector(".ws-panel-close").onclick = function () { el.querySelector("#wsPage").classList.remove("right-open"); };
    el.querySelector("#wsNew").onclick = function () { taoMoi(S.loai); };
    el.querySelector("#wsImport").onclick = function () {
      if (window.JavisStudio) window.JavisStudio.importItems(async function () {
        if (!active) return;
        await taiDanhSach(); veTrai(); chonMacDinh();
      });
    };
    // Một ngăn kéo cho cả hai phạm vi (của trợ lý / chỉ cuộc này), công tắc nằm ở đầu ngăn.
    // Quy trình không có tài liệu riêng, nên ở tab Quy trình nút này vẫn mở tài liệu của cuộc.
    el.querySelector("#wsFiles").onclick = function () {
      if (!ready || !window.JavisChatSide) return;
      var x = dangChon();
      if (S.loai === "agent" && x && window.JavisChatSide.moTaiLieu) window.JavisChatSide.moTaiLieu(x.slug, x.name);
      else window.JavisChatSide.moKhungCuoc();
    };
    el.querySelector("#wsStore").onclick = function () { if (window.JavisPacks && window.JavisPacks.moKho) window.JavisPacks.moKho(S.loai, "workspace", t("page.workspace.label")); };
    el.querySelector("#wsNewChat").onclick = function () { var x = dangChon(); if (x) moPhien(x, true); };
    var page = el.querySelector("#wsPage");
    el.querySelector("#wsLeftBtn").onclick = function () { page.classList.toggle("left-open"); };
    el.querySelector("#wsRightBtn").onclick = function () { page.classList.toggle("right-open"); };
    // Chạm NỀN MỜ (pseudo-element của chính .wspage nên cú chạm rơi vào page) = đóng ngăn kéo.
    // Màn hẹp: ngăn kéo che gần hết bề ngang nên nếu không có đường này thì mở ra là kẹt.
    page.addEventListener("click", function (e) {
      if (e.target !== page) return;
      page.classList.remove("left-open"); page.classList.remove("right-open");
    });
    // Nhớ chỗ đang đứng: mở lại trang mà rơi về mục đầu danh sách thì mỗi lần ghé qua trang
    // khác rồi quay lại là mất chỗ, trong khi cộng sự đang dùng thường chỉ là một hai mục.
    try { var l = localStorage.getItem("javis_ws_loai"); if (l === "agent" || l === "workflow") S.loai = l; S.chon.agent = localStorage.getItem("javis_ws_agent"); S.chon.workflow = localStorage.getItem("javis_ws_workflow"); } catch (e) {}
    try { var r = localStorage.getItem("javis_ws_rtab"); S.tabPhai = TAB_PHAI.indexOf(r) >= 0 ? r : "lichsu"; } catch (e) { S.tabPhai = "lichsu"; }
    // Chỉ tab của TRỢ LÝ được nhớ qua localStorage. Quy trình mở trang là về Cài đặt: "khởi
    // đầu vào luôn cài đặt" là điều chủ dự án muốn, nhớ tab cũ qua F5 là làm ngược lại.
    S.tabCua = { agent: S.tabPhai, workflow: "cai" };
    S.tabPhai = S.tabCua[S.loai] || S.tabPhai;
    chonTabPhai(S.tabPhai);
    nhoPhienTruoc();
    taiDanhSach().then(function () { if (pendingCommand) { var cmd = pendingCommand; pendingCommand = null; selectCommand(cmd); } else { veTrai(); chonMacDinh(); } }).catch(function () { if (pendingCommand) { pendingCommand.resolve(false); pendingCommand = null; } veLoi(t("ws.err_list")); });
  }
  async function selectCommand(cmd) {
    S.loai = cmd.kind; S.chon[cmd.kind] = cmd.slug; S.q = ""; S.nhom = "";
    luuChon(); veTrai();
    var item = dangChon();
    if (!item) { cmd.resolve(false); return; }
    cmd.resolve(await moPhien(item, false, cmd.sid));
  }
  // `sid` (tuỳ chọn): mở ĐÚNG hội thoại đó thay vì cuộc gần nhất của cộng sự này. Hòm thư
  // truyền vào, vì mẩu thư trỏ tới một hội thoại CỤ THỂ - kết quả việc nền của tuần trước
  // không nằm ở cuộc mới nhất.
  function openCommand(kind, slug, sid) {
    return new Promise(function (resolve) {
      var cmd = {kind: kind, slug: slug, sid: sid || "", resolve: resolve};
      if (active) { selectCommand(cmd); return; }
      if (!window.JavisNav) { resolve(false); return; }
      if (pendingCommand) pendingCommand.resolve(false);
      pendingCommand = cmd;
      window.JavisNav.go("workspace");
    });
  }
  // Mở trang Cộng sự ở ĐÚNG tab (menu nhanh của linh vật: "Trợ lý" / "Quy trình"). Khác
  // openCommand ở chỗ không nhắm tới một cộng sự cụ thể: chỉ chuyển tab rồi để chonMacDinh()
  // chọn mục gần nhất. Ghi localStorage TRƯỚC khi đổi trang, vì render() dựng lại S.loai từ
  // đó - đặt S.loai xong mới điều hướng thì render() lấy giá trị cũ ghi đè lên ngay.
  function openTab(kind) {
    var loai = kind === "workflow" ? "workflow" : "agent";
    // KHÔNG đụng vào S.q: ô tìm là một node DOM đang hiện chữ, xoá trạng thái mà không xoá ô
    // là danh sách đầy đủ nằm dưới một câu lọc vẫn nhìn thấy được. Nhóm thì khác - veTrai()
    // vẽ lại ô chọn theo S.nhom nên hai bên vẫn khớp.
    S.loai = loai; S.nhom = "";
    luuChon();
    if (active) { veTrai(); chonMacDinh(); return true; }
    if (!window.JavisNav) return false;
    window.JavisNav.go("workspace");
    return true;
  }
  function luuChon() { try { localStorage.setItem("javis_ws_loai", S.loai); if (S.chon.agent) localStorage.setItem("javis_ws_agent", S.chon.agent); if (S.chon.workflow) localStorage.setItem("javis_ws_workflow", S.chon.workflow); } catch (e) {} }

  // ---------- ô tìm thu gọn ----------
  // Nút kính lúp bung ô nhập ra; ô nhập RỖNG mà mất tiêu điểm thì tự thu lại. Esc xoá chữ,
  // vẽ lại danh sách đầy đủ rồi thu - nếu chỉ thu mà không xoá thì danh sách vẫn đang lọc
  // theo một câu không còn nhìn thấy ở đâu, và người dùng tưởng cộng sự của mình biến mất.
  function moODoTim(el, mo) {
    var o = el.querySelector("#wsSearch"), nut = el.querySelector("#wsSearchBtn");
    if (!o || !nut) return;
    o.hidden = !mo;
    nut.setAttribute("aria-expanded", mo ? "true" : "false");
    if (mo) o.focus(); else nut.focus();
  }
  function noiODoTim(el) {
    var o = el.querySelector("#wsSearch"), nut = el.querySelector("#wsSearchBtn");
    if (!o || !nut) return;
    nut.onclick = function () { if (o.hidden) moODoTim(el, true); else if (!o.value.trim()) moODoTim(el, false); else o.focus(); };
    o.oninput = function (e) { S.q = e.target.value; S.hien = TRANG; veDanhSach(); };
    o.onblur = function () { if (!o.value.trim()) { o.hidden = true; nut.setAttribute("aria-expanded", "false"); } };
    o.onkeydown = function (e) {
      if (e.key !== "Escape" && e.key !== "Esc") return;
      e.preventDefault(); e.stopPropagation();
      o.value = ""; S.q = ""; S.hien = TRANG; veDanhSach(); moODoTim(el, false);
    };
  }

  // ---------- tab cột phải ----------
  // Cây thư mục là node MƯỢN của màn chính, chỉ có MỘT bản. Rời tab (hay rời trang) mà không
  // trả thì màn chính và trang Trò chuyện mất hẳn panel Vault - cùng bài học với tab Thư mục
  // của trang Trò chuyện (xem sessions-ui.js chonTab).
  function traCayThuMuc() { try { if (window.JavisVaultPanel) window.JavisVaultPanel.giveBack(); } catch (e) {} }
  function chonTabPhai(tab) {
    var el = S.el; if (!el) return;
    S.tabPhai = TAB_PHAI.indexOf(tab) >= 0 ? tab : "cai";
    if (S.tabCua) S.tabCua[S.loai] = S.tabPhai;
    // Tab của quy trình chỉ sống trong lần mở trang này (xem S.tabCua), không ghi xuống.
    if (S.loai !== "workflow") { try { localStorage.setItem("javis_ws_rtab", S.tabPhai); } catch (e) {} }
    el.querySelectorAll("[data-rtab]").forEach(function (b) { b.classList.toggle("active", b.dataset.rtab === S.tabPhai); });
    el.querySelectorAll("[data-rpane]").forEach(function (p) { p.classList.toggle("on", p.dataset.rpane === S.tabPhai); });
    var host = el.querySelector("#wsRightFiles");
    if (S.tabPhai === "files" && host && window.JavisVaultPanel) window.JavisVaultPanel.borrow(host);
    else traCayThuMuc();
  }

  // (0.62.0 đã bỏ hàm dongBoNhomForm ở đây. Nó tồn tại chỉ để vá một xung đột tự gây ra:
  // form "Cài đặt trợ lý" từng có ô nhóm RIÊNG, nên chuyển nhóm ở cột trái xong bấm Lưu là
  // ô cũ ghi đè ngược. Nay form không còn ô nhóm và server giữ nguyên nhóm khi form không
  // gửi `group`, nên không còn gì để đồng bộ.)
  // ---------- bộ chọn NHÓM: thanh + bảng nổi, cùng khuôn với project bên Trò chuyện ----------
  // Nhóm TRỐNG (tạo bằng "+ Nhóm mới" mà chưa kéo ai vào) không tồn tại ở đâu trên đĩa - nhóm
  // là tập hợp cộng sự có cùng `group` - nên nhớ tạm trong localStorage theo brain và loại; hễ
  // có cộng sự mang tên nhóm đó là xoá khỏi sổ vì nhóm đã "thật".
  var KHOA_NHOM_TRONG = "javis_ws_nhom_trong";
  function khoaTrong() { return brain() + "|" + S.loai; }
  function docNhomTrong() {
    try { var o = JSON.parse(localStorage.getItem(KHOA_NHOM_TRONG) || "{}") || {}; return (o[khoaTrong()] || []).slice(); }
    catch (e) { return []; }
  }
  function luuNhomTrong(ds) {
    try {
      var o = JSON.parse(localStorage.getItem(KHOA_NHOM_TRONG) || "{}") || {};
      o[khoaTrong()] = ds; localStorage.setItem(KHOA_NHOM_TRONG, JSON.stringify(o));
    } catch (e) {}
  }
  function demNhom() { var m = {}; danhSach().forEach(function (x) { var g = nhomCua(x); m[g] = (m[g] || 0) + 1; }); return m; }
  // Mọi nhóm đang có (trừ "Chung"), nhóm thật lẫn nhóm trống, xếp theo tên tiếng Việt.
  function tenCacNhom() {
    var dem = demNhom(), ds = Object.keys(dem).filter(function (g) { return g !== NHOM_MD; });
    docNhomTrong().forEach(function (g) { if (g && g !== NHOM_MD && ds.indexOf(g) < 0) ds.push(g); });
    return ds.sort(function (a, b) { return a.localeCompare(b, "vi"); });
  }
  function nhanNhom(g) { return !g ? t("ws.all_groups") : g === NHOM_MD ? t("ws.group_none") : g; }
  function chonNhom(g) { S.nhom = g || ""; S.hien = TRANG; veTrai(); }
  function taoNhomMoi() {
    var ten = window.prompt(t("ws.group_ask"), "");
    if (ten == null) return;
    ten = String(ten).trim();
    if (!ten) return;
    if (ten !== NHOM_MD && !demNhom()[ten]) {
      var ds = docNhomTrong(); if (ds.indexOf(ten) < 0) { ds.push(ten); luuNhomTrong(ds); }
    }
    chonNhom(ten);
  }
  // Xoá nhóm = đưa mọi cộng sự trong nhóm về "Chưa xếp nhóm" (group mặc định) và bỏ khỏi sổ
  // nhóm trống. Không xoá cộng sự nào.
  async function xoaNhom(g) {
    var ds = danhSach().filter(function (x) { return nhomCua(x) === g; });
    if (ds.length && !window.confirm(t("ws.group_delete_ask", { ten: g, n: ds.length }))) return;
    for (var i = 0; i < ds.length; i++) {
      var r = await api("/capability/meta", { method: "POST", body: fd({ kind: S.loai, slug: ds[i].slug, brain: brain(), group: "" }) });
      if (!r || !r.ok) { veLoi((r && r.error) || t("ws.err_meta")); break; }
    }
    luuNhomTrong(docNhomTrong().filter(function (x) { return x !== g; }));
    var th = S.thu[khoaThu()] || []; var j = th.indexOf(g); if (j >= 0) { th.splice(j, 1); luuThu(); }
    if (S.nhom === g) S.nhom = "";
    await taiDanhSach();
    if (!active) return;
    veTrai(); veGiua(dangChon());
  }
  function moBangNhom(neo) {
    var cs = window.JavisChatSide; if (!cs || !cs.menu) return;
    var dem = demNhom();
    var rows = [
      { label: t("ws.all_groups"), icon: "layers", on: !S.nhom, run: function () { chonNhom(""); } },
      { label: t("ws.group_none"), icon: "circle", right: String(dem[NHOM_MD] || 0), on: S.nhom === NHOM_MD,
        run: function () { chonNhom(NHOM_MD); } },
    ];
    var ds = tenCacNhom();
    if (ds.length) rows.push({ sep: true });
    ds.forEach(function (g) {
      rows.push({ label: g, icon: "folder", right: String(dem[g] || 0), on: S.nhom === g,
                  run: function () { chonNhom(g); },
                  acts: [{ icon: "ellipsis-vertical", title: t("ws.group_acts"),
                           run: function () { moChucNangNhom(neo, g); } }] });
    });
    rows.push({ sep: true });
    rows.push({ label: t("ws.group_new_row"), run: function () { taoNhomMoi(); } });
    cs.menu(neo, rows);
  }
  // Hộp chức năng của MỘT nhóm, đi sâu trong cùng bảng nổi (như project bên Trò chuyện).
  function moChucNangNhom(neo, g) {
    var cs = window.JavisChatSide; if (!cs || !cs.menu) return;
    cs.menu(neo, [
      { label: g, icon: "folder", wrap: true, run: function () { chonNhom(g); } },
      { sep: true },
      { label: t("ws.group_only"), icon: "folder-open", run: function () { chonNhom(g); } },
      { label: t("ws.group_rename"), icon: "pencil", run: function () { doiTenNhom(g); } },
      { label: t("ws.group_delete"), icon: "trash-2", run: function () { xoaNhom(g); } },
    ]);
  }
  function veThanhNhom(el) {
    var bar = el.querySelector("#wsGroup"); if (!bar) return;
    var icNhom = !S.nhom ? "layers" : S.nhom === NHOM_MD ? "circle" : "folder";
    bar.innerHTML =
      '<button type="button" class="cs-proj-cur" title="' + esc(t("ws.group_pick_title")) + '">' +
        '<span class="cs-proj-name">' + ic(icNhom) + ' ' + esc(nhanNhom(S.nhom)) + '</span>' +
        '<span class="cs-proj-caret">' + ic("chevron-down") + '</span></button>' +
      (S.nhom ? '<button type="button" class="cs-proj-x" title="' + esc(t("ws.group_clear_title")) + '">' + ic("x") + '</button>' : '') +
      '<button type="button" class="cs-proj-add" title="' + esc(t("ws.group_add_title")) + '">' + ic("folder-plus") + '</button>';
    var cur = bar.querySelector(".cs-proj-cur"); if (cur) cur.onclick = function (e) { moBangNhom(e.currentTarget); };
    var x = bar.querySelector(".cs-proj-x"); if (x) x.onclick = function () { chonNhom(""); };
    var add = bar.querySelector(".cs-proj-add"); if (add) add.onclick = function () { taoNhomMoi(); };
  }

  function veTrai() {
    var el = S.el; if (!el) return;
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.classList.toggle("on", b.dataset.loai === S.loai); });
    var nhoms = demNhom();
    // Nhóm trống đã có người thì thành nhóm thật, bỏ khỏi sổ.
    var trong = docNhomTrong(), conTrong = trong.filter(function (g) { return !nhoms[g]; });
    if (conTrong.length !== trong.length) luuNhomTrong(conTrong);
    if (S.nhom && !nhoms[S.nhom] && conTrong.indexOf(S.nhom) < 0) S.nhom = "";
    veThanhNhom(el);
    el.querySelector("#wsNew").innerHTML = ic("plus") + " " + esc(S.loai === "agent" ? t("ws.new_agent") : t("ws.new_workflow"));
    el.querySelector("#wsImport").textContent = t(S.loai === "agent" ? "ws.upload_agent" : "ws.upload_workflow");
    veDanhSach();
  }
  // Quy trình này có lần chạy nào ĐANG chạy không? Đọc thẳng từ S.tienDo (máy trạng thái ăn
  // wf_event) chứ không nuôi một cờ riêng: cờ riêng thì lúc chạy xong, lỗi, hay dừng chờ duyệt
  // phải nhớ tắt ở cả ba chỗ, quên một chỗ là icon quay mãi không dừng. apDung() đã đặt
  // trang_thai về "xong"/"loi"/"cho" ở cả ba đường đó, nên chỉ cần so đúng một giá trị.
  function dangChay(slug) {
    return Object.keys(S.tienDo).some(function (sid) {
      return S.sessionCuaPhien[sid] === slug && S.tienDo[sid] && S.tienDo[sid].trang_thai === "dang";
    });
  }
  // Danh sách trái. Ba việc dễ sai gộp ở đây, nên nói rõ từng cái:
  //
  // 1. MỤC ĐÃ GHIM phải NHÌN RA ĐƯỢC. Bản 0.59.14 có ghim (sapXep đưa lên đầu) nhưng dấu ghim
  //    lại nằm BÊN TRONG thẻ <strong> của cái tên, mà thẻ đó cắt chữ bằng ellipsis - tên dài
  //    một chút là dấu ghim bị cắt mất, danh sách trông y như chưa ghim gì (chủ dự án báo
  //    16/09 kèm ảnh). Nay dấu ghim là một ô RIÊNG, không nằm trong phần bị cắt, và phía trên
  //    khối ghim có một dòng nhãn "Đã ghim" như cột lịch sử vẫn làm - liếc một cái là biết
  //    đâu là mục mình kéo lên, đâu là phần xếp theo thời gian.
  // 2. Chỉ vẽ TRANG đầu, còn lại nằm sau nút "Xem thêm".
  // 3. Nhãn nhóm chỉ hiện khi CÓ mục ghim: danh sách không ghim gì mà vẫn đội hai dòng nhãn
  //    thì chỉ tổ chật cột.
  function veDanhSach() {
    var el = S.el; if (!el) return;
    var ds = loc(danhSach(), S.q, S.nhom), chon = S.chon[S.loai];
    var host = el.querySelector("#wsList");
    var trong = (S.q || S.nhom) ? [] : docNhomTrong();
    if (!ds.length && !trong.length) {
      var nhomTrong = !!(S.nhom && !S.q && docNhomTrong().indexOf(S.nhom) >= 0);
      host.innerHTML = '<div class="ws-empty">' + esc(t(nhomTrong ? "ws.group_empty_hint" : "ws.empty")) + '</div>';
      return;
    }
    if (S.hien < TRANG) S.hien = TRANG;
    // Vẽ theo KHỐI (xem gomNhom). Nhóm đang thu gọn chỉ còn hàng tiêu đề, không tính vào
    // trang; phân trang đếm MỤC đã vẽ chứ không đếm tiêu đề.
    var html = "", daVe = 0, tong = 0;
    gomNhom(ds, S.nhom, trong).forEach(function (n) {
      var thu = n.theoNhom && daThu(n.nhom);
      if (n.ghim) html += '<div class="ws-glabel">' + esc(t("ws.grp_pinned")) + '</div>';
      else if (n.theoNhom) html += nhomHtml(n.nhom, n.items.length, thu);
      else if (n.tieuDe) html += '<div class="ws-glabel">' + esc(t("ws.grp_rest")) + '</div>';
      if (thu) return;
      tong += n.items.length;
      n.items.forEach(function (x) { if (daVe < S.hien) { html += mucHtml(x, chon); daVe++; } });
    });
    host.innerHTML = html +
      (tong > S.hien
        ? '<button type="button" class="ws-more" id="wsMore">' +
            esc(t("sess.more", { so: Math.min(TRANG, tong - S.hien) })) + '</button>'
        : "");
    var nutThem = host.querySelector("#wsMore");
    if (nutThem) nutThem.onclick = function () {
      // Giữ chỗ cuộn: vẽ lại cả danh sách mà để nó nhảy về đầu thì bấm "Xem thêm" xong lại
      // phải cuộn tay xuống đúng chỗ vừa đứng.
      var cuon = host.scrollTop;
      S.hien += TRANG; veDanhSach();
      var lai = S.el && S.el.querySelector("#wsList"); if (lai) lai.scrollTop = cuon;
    };
    noiDanhSach(host);
  }
  // Hàng tiêu đề của MỘT nhóm: nút thu gọn/mở (tên + số người) và nút "..." quản lý.
  // Hai nút ngang hàng trong một khối, không lồng nhau (button trong button là HTML sai).
  function nhomHtml(g, n, thu) {
    return '<div class="ws-glabel ws-grp' + (thu ? " thu" : "") + '" data-nhom="' + esc(g) + '">' +
      '<button type="button" class="ws-grp-tog" aria-expanded="' + (thu ? "false" : "true") +
        '" title="' + esc(t("ws.group_toggle")) + '">' + ic("chevron-down") +
        '<span class="ws-grp-name">' + esc(g) + '</span><span class="ws-grp-n">' + n + '</span></button>' +
      '<button type="button" class="ws-grp-more" data-gmore="' + esc(g) + '" title="' + esc(t("ws.group_manage")) +
        '" aria-label="' + esc(t("ws.group_manage")) + '">' + ic("ellipsis-vertical") + '</button>' +
      '</div>';
  }
  // HTML của MỘT hàng. Tách khỏi veDanhSach để chỗ kia chỉ còn lo nhóm - phân trang, và để
  // test dựng được một hàng mà không cần cả trang.
  function mucHtml(x, chon) {
    // "Đang chạy" phải đọc được BẰNG CHỮ, không chỉ bằng icon quay: người tắt hiệu ứng
    // (prefers-reduced-motion, xem style.css) và trình đọc màn hình không thấy vòng quay
    // nào cả, nên thêm một chữ vào dòng phụ và một <title> vào icon.
    var chay = S.loai === "workflow" && dangChay(x.slug);
    var phu = S.loai === "agent" ? (x.group || "Chung") + " · " + (x.role || "") : (x.group || "Chung") + " · " + cacBuoc(x).length + " " + t("studio.steps");
    if (chay) phu += " · " + t("ws.running");
    // Nút "..." KHÔNG được lồng trong nút chọn mục: button trong button là HTML sai và
    // trình duyệt tự tách thẻ ra, làm cú bấm rơi vào chỗ không ai ngờ. Nên bọc cả hai trong
    // một khối và để chúng là hai nút ngang hàng.
    return '<div class="ws-item-wrap' + (x.pinned ? " ghim" : "") + '">' +
      '<button type="button" class="ws-item' + (x.slug === chon ? " on" : "") + '" aria-pressed="' + (x.slug === chon) + '" data-slug="' + esc(x.slug) + '">' +
      '<span class="ws-item-ic">' + (S.loai === "agent" ? avatar(x, 42)
        : (chay ? ic("loader", { cls: "ic-spin", title: t("ws.running") }) : ic("workflow"))) + '</span>' +
      '<span class="ws-item-text"><strong>' + esc(x.name) + '</strong>' +
      '<small>' + esc(phu) + '</small></span>' +
      // Dấu ghim đứng NGOÀI khối chữ: trong đó nó bị ellipsis của cái tên cắt mất.
      (x.pinned ? '<span class="ws-item-pin" title="' + esc(t("ws.pinned")) + '">' + ic("pin") + '</span>' : "") +
      '</button>' +
      '<button type="button" class="ws-item-more" data-more="' + esc(x.slug) + '" title="' +
        esc(t("ws.manage")) + '" aria-label="' + esc(t("ws.manage")) + '">' + ic("ellipsis-vertical") + '</button>' +
      '</div>';
  }
  // Nối dây cho các nút vừa vẽ. Gọi lại sau MỖI lần vẽ: innerHTML mới là node mới, handler cũ
  // chết theo node cũ.
  function noiDanhSach(host) {
    host.querySelectorAll("[data-slug]").forEach(function (b) {
      b.onclick = function () {
        S.chon[S.loai] = b.dataset.slug; luuChon(); veDanhSach(); moPhien(dangChon(), false);
        // Chọn xong thì đóng ngăn kéo - nhưng CHỈ ở khổ màn hình có ngăn kéo. Màn rộng lớp này
        // mang nghĩa ngược (đang ẩn cột), gỡ nó là bày lại cột người dùng vừa cố ý ẩn đi.
        if (heptLai()) S.el.querySelector("#wsPage").classList.remove("left-open");
      };
    });
    host.querySelectorAll("[data-more]").forEach(function (b) {
      b.onclick = function (e) {
        e.stopPropagation();          // đừng để cú bấm chạy tiếp thành "chọn mục"
        var x = danhSach().find(function (m) { return m.slug === b.dataset.more; });
        if (x) moMenuMuc(x, b);
      };
    });
    host.querySelectorAll(".ws-grp-tog").forEach(function (b) {
      b.onclick = function () {
        var cuon = host.scrollTop;    // giữ chỗ cuộn như nút "Xem thêm"
        latThu(b.parentNode.dataset.nhom); veDanhSach();
        var lai = S.el && S.el.querySelector("#wsList"); if (lai) lai.scrollTop = cuon;
      };
    });
    host.querySelectorAll("[data-gmore]").forEach(function (b) {
      b.onclick = function (e) { e.stopPropagation(); moMenuCuaNhom(b.dataset.gmore, b); };
    });
  }

  // ---------- mở FILE trong khung chat cộng sự: TẮT HẲN khung chat ----------
  // Chủ dự án chốt 16/09: "khi mở file trong hội thoại của agent vẫn hiện khung chat, đáng
  // nhẽ nó phải tắt hết khung chat đấy đi". Trước đó bản 0.59.14 cố giữ cả hai bên cạnh nhau
  // và tự canh: đo khoang giữa, thu cột phải, hết chỗ thì xếp dọc. Cách đó sai từ gốc - cột
  // giữa trang Cộng sự đã bị cột danh sách và cột phải ăn mất ~570px, nên chia đôi chỗ còn
  // lại thì trình sửa hẹp mà hội thoại cũng hẹp, canh kiểu gì cũng chỉ là chọn xem bên nào
  // khổ hơn. Nay mở file là trình sửa chiếm TRỌN khoang giữa ở MỌI khổ màn (console.css:
  // `.ws-main.edit-on > .ws-slot { display: none }`), đóng file ra là khung chat về đủ -
  // ẩn bằng display:none nên đoạn chat đang dở còn nguyên, không mất chữ đang gõ.
  //
  // Vì thế ở đây KHÔNG còn hàm canh khung nào: CSS lo hết, không đo, không MutationObserver,
  // không listener resize. Đúng khuôn màn hẹp vẫn chạy từ đầu.

  // ---------- menu quản lý của một mục (ghim / chuyển nhóm / sửa / xoá) ----------
  // Dùng CHUNG cho trợ lý và quy trình: hai loại cùng một bộ động tác, viết hai bản là hai
  // bản trôi lệch nhau ngay lần thêm động tác thứ năm.
  //
  // Vị trí FIXED chứ không absolute trong cột trái: cột đó có `overflow` riêng để cuộn danh
  // sách, nên một menu absolute nằm trong đó bị cắt mất ngay ở mục gần đáy.
  function dongMenu() {
    if (!S.menu) return;
    try { S.menu.remove(); } catch (e) {}
    S.menu = null;
    document.removeEventListener("click", dongMenuNgoai, true);
    document.removeEventListener("keydown", dongMenuEsc, true);
    window.removeEventListener("resize", dongMenu);
    window.removeEventListener("scroll", dongMenu, true);
  }
  function dongMenuNgoai(e) { if (S.menu && !S.menu.contains(e.target)) dongMenu(); }
  function dongMenuEsc(e) { if (e.key === "Escape") { e.stopPropagation(); dongMenu(); } }

  function moMenuMuc(item, neo) { moMenuKhung(neo, function (m) { veMenuGoc(item, m); }); }
  // Menu của MỘT nhóm (nút "..." trên hàng tiêu đề): chỉ xem nhóm này, đổi tên cả
  // nhóm. Tạo nhóm mới vẫn đi qua menu của một cộng sự ("Nhóm mới…"): nhóm
  // là tập hợp cộng sự có cùng `group`, không có nhóm rỗng để mà tạo trước.
  function moMenuCuaNhom(g, neo) {
    moMenuKhung(neo, function (m) {
      var so = danhSach().filter(function (x) { return nhomCua(x) === g; }).length;
      m.innerHTML = '<div class="ws-menu-head">' + esc(g) + ' · ' + so + '</div>' +
        nutMenu("folder-open", t("ws.group_only"), "chi") +
        nutMenu("pencil", t("ws.group_rename"), "ten") +
        nutMenu("trash-2", t("ws.group_delete"), "xoa");
      m.querySelector('[data-act="chi"]').onclick = function () { dongMenu(); chonNhom(g); };
      m.querySelector('[data-act="ten"]').onclick = function () { dongMenu(); doiTenNhom(g); };
      m.querySelector('[data-act="xoa"]').onclick = function () { dongMenu(); xoaNhom(g); };
    });
  }
  // Đổi tên nhóm = đổi `group` của TỪNG cộng sự trong đó qua /capability/meta (cùng đường
  // với "Chuyển sang nhóm"), rồi tải lại một lần. Trạng thái thu gọn và ô lọc đi theo tên mới.
  async function doiTenNhom(g) {
    var moi = window.prompt(t("ws.group_rename_ask", { ten: g }), g);
    if (moi == null) return;
    moi = String(moi).trim();
    if (!moi || moi === g) return;
    var ds = danhSach().filter(function (x) { return nhomCua(x) === g; });
    for (var i = 0; i < ds.length; i++) {
      var r = await api("/capability/meta", { method: "POST", body: fd({ kind: S.loai, slug: ds[i].slug, brain: brain(), group: moi }) });
      if (!r || !r.ok) { veLoi((r && r.error) || t("ws.err_meta")); break; }
    }
    var th = S.thu[khoaThu()] || []; var j = th.indexOf(g); if (j >= 0) { th[j] = moi; luuThu(); }
    var tr = docNhomTrong(); var k = tr.indexOf(g); if (k >= 0) { tr[k] = moi; luuNhomTrong(tr); }
    if (S.nhom === g) S.nhom = moi;
    await taiDanhSach();
    if (!active) return;
    veTrai(); veGiua(dangChon());
  }
  function moMenuKhung(neo, ve) {
    dongMenu();
    var m = document.createElement("div");
    m.className = "ws-menu";
    m.setAttribute("role", "menu");
    S.menu = m;
    document.body.appendChild(m);
    ve(m);
    datChoMenu(m, neo);
    // Gắn listener SAU một nhịp: cú bấm mở menu vẫn đang nổi bọt lên document, gắn ngay là
    // menu tự đóng đúng lúc vừa mở.
    setTimeout(function () {
      if (!S.menu) return;
      document.addEventListener("click", dongMenuNgoai, true);
      document.addEventListener("keydown", dongMenuEsc, true);
      window.addEventListener("resize", dongMenu);
      window.addEventListener("scroll", dongMenu, true);
    }, 0);
  }
  function datChoMenu(m, neo) {
    var r = neo.getBoundingClientRect();
    var w = m.offsetWidth || 220, h = m.offsetHeight || 180;
    var x = Math.min(r.right - w, window.innerWidth - w - 8);
    var y = r.bottom + 4;
    if (y + h > window.innerHeight - 8) y = Math.max(8, r.top - h - 4);   // hết chỗ dưới thì mở lên
    m.style.left = Math.max(8, x) + "px";
    m.style.top = y + "px";
  }
  function nutMenu(icon, chu, cls) {
    return '<button type="button" role="menuitem" class="ws-menu-it' + (cls ? " " + cls : "") +
      '" data-act="' + cls + '">' + ic(icon) + '<span>' + esc(chu) + '</span></button>';
  }
  function veMenuGoc(item, m) {
    var ghim = !!item.pinned;
    m.innerHTML =
      '<div class="ws-menu-head">' + esc(item.name) + '</div>' +
      nutMenu("pin", ghim ? t("ws.unpin") : t("ws.pin"), "ghim") +
      nutMenu("folder", t("ws.move_group"), "nhom") +
      nutMenu("pencil", t("ws.edit"), "sua") +
      nutMenu("trash-2", t("common.delete"), "xoa");
    m.querySelector('[data-act="ghim"]').onclick = function () {
      dongMenu(); datMeta(item, { pinned: ghim ? "0" : "1" });
    };
    m.querySelector('[data-act="nhom"]').onclick = function () { veMenuNhom(item, m); };
    m.querySelector('[data-act="sua"]').onclick = function () { dongMenu(); suaMuc(item); };
    m.querySelector('[data-act="xoa"]').onclick = function () { dongMenu(); xoaMuc(item); };
  }
  // Chọn nhóm NGAY TRONG menu (hai tầng tại chỗ) thay vì menu con nổi ra cạnh: menu con phải
  // tự tính chỗ lần nữa và rất dễ tràn khỏi màn hình hẹp.
  function veMenuNhom(item, m) {
    var nhom = [];
    danhSach().forEach(function (x) {
      var g = (x.group || "Chung").trim();
      if (g && nhom.indexOf(g) < 0) nhom.push(g);
    });
    // Nhóm vừa lập bằng "+ Nhóm mới" (chưa có ai) cũng phải chọn được, không thì không có
    // cách nào đưa cộng sự đầu tiên vào đó.
    docNhomTrong().forEach(function (g) { if (g && nhom.indexOf(g) < 0) nhom.push(g); });
    nhom.sort(function (a, b) { return a.localeCompare(b, "vi"); });
    var hien = (item.group || "Chung").trim();
    m.innerHTML =
      '<button type="button" class="ws-menu-it quay" data-act="quay">' + ic("chevron-left") +
        '<span>' + esc(t("ws.move_group")) + '</span></button>' +
      nhom.map(function (g) {
        return '<button type="button" role="menuitem" class="ws-menu-it' + (g === hien ? " on" : "") +
          '" data-nhom="' + esc(g) + '">' + ic(g === hien ? "folder-open" : "folder") +
          '<span>' + esc(g) + '</span></button>';
      }).join("") +
      '<button type="button" role="menuitem" class="ws-menu-it" data-act="moi">' + ic("folder-plus") +
        '<span>' + esc(t("ws.group_new")) + '</span></button>';
    m.querySelector('[data-act="quay"]').onclick = function () { veMenuGoc(item, m); };
    m.querySelector('[data-act="moi"]').onclick = function () {
      var ten = window.prompt(t("ws.group_ask"), hien);
      dongMenu();
      if (ten && ten.trim() && ten.trim() !== hien) datMeta(item, { group: ten.trim() });
    };
    m.querySelectorAll("[data-nhom]").forEach(function (b) {
      b.onclick = function () {
        dongMenu();
        if (b.dataset.nhom !== hien) datMeta(item, { group: b.dataset.nhom });
      };
    });
  }

  // Sửa MỘT PHẦN frontmatter (ghim / nhóm) rồi tải lại danh sách. Đi đường /capability/meta
  // chứ không POST /agents: endpoint đó nhận cả prompt/steps, gửi thiếu một field là ghi lại
  // file thiếu nội dung.
  async function datMeta(item, fields) {
    var body = { kind: S.loai, slug: item.slug, brain: brain() };
    Object.keys(fields).forEach(function (k) { body[k] = fields[k]; });
    var r = await api("/capability/meta", { method: "POST", body: fd(body) });
    if (!r || !r.ok) { veLoi((r && r.error) || t("ws.err_meta")); return; }
    await taiDanhSach();
    if (!active) return;
    // Vẽ lại DANH SÁCH và thanh tiêu đề, KHÔNG vẽ lại cột phải - cùng lối với sauLuu(). Cột
    // phải đang là trình sửa agent: dựng lại nó là xoá luôn những gì người dùng vừa gõ mà
    // chưa bấm Lưu, chỉ để cập nhật một ô chọn nhóm.
    veTrai(); veGiua(dangChon());
  }
  // Sửa = mở TRÌNH SỬA CỦA STUDIO dạng hộp thoại. Gọi không truyền `host` nên studio.js tự
  // bung modal của nó (xem editAgent: chỉ khi CÓ host nó mới vẽ tại chỗ) - đúng thứ một động
  // tác "Sửa" cần, và cùng đường với nút Sửa quy trình ở cột phải.
  function suaMuc(item) {
    if (!window.JavisStudio) return;
    var xong = { onSaved: async function () { await sauLuu(item, S.loai); } };
    if (S.loai === "agent") window.JavisStudio.editAgent(item, xong);
    else window.JavisStudio.editWorkflow(item, xong);
  }
  async function xoaMuc(item) {
    var hoi = S.loai === "agent" ? t("studio.del_ag", { ten: item.name })
                                 : t("studio.del_wf", { ten: item.name });
    if (!confirm(hoi)) return;
    await api(S.loai === "agent" ? "/agents/delete" : "/workflows/delete",
              { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
    if (S.chon[S.loai] === item.slug) S.chon[S.loai] = null;
    await taiDanhSach();
    if (!active) return;
    veTrai(); chonMacDinh();
  }
  function chonMacDinh() {
    var ds = danhSach();
    // Danh sách RỖNG (brain mới tinh, hay tab Quy trình khi chưa có quy trình nào): không có
    // phiên nào để mở nên phải KHOÁ ô nhập lại. Bỏ quên chốt này thì ô nhập vẫn sáng trong khi
    // `ready` còn false từ render(), người dùng gõ xong bấm gửi và KHÔNG CÓ GÌ xảy ra: canSend()
    // trả false, app.js lặng lẽ quay ra, màn hình không nói một lời nào.
    if (!ds.length) { chatReady(false); veGiua(null, t("ws.none_yet")); vePhai(null); return; }
    if (!ds.some(function (x) { return x.slug === S.chon[S.loai]; })) S.chon[S.loai] = ds[0].slug;
    var v = docViTri();
    var id = v && v.kind === S.loai && v.slug === S.chon[S.loai] ? v.sessionId : null;
    veDanhSach(); return moPhien(dangChon(), false, id);
  }

  // ---------- trả khung chat về bộ não chính khi rời trang ----------
  // Khung chat là node MƯỢN của app: trang Cộng sự, trang Trò chuyện và màn Javis dùng CHUNG
  // một khung. Rời trang mà không làm gì thì đoạn chat với trợ lý còn nằm nguyên ở hai chỗ kia
  // - và tệ hơn hiển thị: `savedSessionId` vẫn là phiên agent:<slug>, nên tin gõ tiếp ở trang
  // Trò chuyện BAY VÀO ĐÚNG PHIÊN CỦA TRỢ LÝ. Đó là hai chức năng chat khác nhau, chủ dự án
  // báo 16/09 là người dùng không hiểu được chuyện gì đang xảy ra.
  //
  // Thứ tự cố ý: XOÁ TRẮNG trước, mở lại cuộc cũ sau. openStoredSession chỉ dọn khung SAU KHI
  // gọi mạng xong, nên nếu phiên cũ đã bị xoá thì nó lặng lẽ không làm gì và đoạn chat trợ lý
  // sẽ còn nằm lại - xoá trắng trước thì trường hợp xấu nhất cũng chỉ là một khung trống.
  function laPhienCongSu(id) { return !!(id && S.sessionCuaPhien[id]); }
  function traKhungChat() {
    if (!window.JavisSessions) return;
    var cur = window.JavisSessions.current();
    // Phiên mở từ tab Lịch sử (sessions-ui gọi thẳng JavisSessions.open) không đi qua moPhien
    // nên không có trong S.sessionCuaPhien, mà nó VẪN là phiên cộng sự: rời trang mà không trả
    // khung chat là tin kế tiếp ở trang Trò chuyện rơi vào phiên trợ lý. Chỉ đúng một trường
    // hợp không đụng: khung chat vẫn đang ở đúng cuộc của bộ não chính lúc vào trang.
    if (!cur || (!laPhienCongSu(cur) && cur === _phienTruoc)) return;
    window.JavisSessions.new();
    if (_phienTruoc && _phienTruoc !== cur && !laPhienCongSu(_phienTruoc)) {
      try { window.JavisSessions.open(_phienTruoc); } catch (e) {}
    }
  }
  // Nhớ cuộc đang dở của bộ não chính NGAY LÚC DỰNG TRANG: lúc này khung chat còn là của
  // trang trước, chưa bị moPhien() đổi sang phiên trợ lý.
  function nhoPhienTruoc() {
    try {
      var cur = window.JavisSessions && window.JavisSessions.current();
      var v = docViTri();
      if (v && cur === v.sessionId) { _phienTruoc = v.mainSessionId || null; return; }
      if (cur && !laPhienCongSu(cur)) _phienTruoc = cur;
    } catch (e) {}
  }

  // ---------- phiên ----------
  // Mở phiên của cộng sự đang chọn: có phiên cũ thì mở tiếp (F5 hay quay lại vẫn còn hội
  // thoại), chưa có thì xin server một phiên TRỐNG đúng kênh. Phải xin trước tin đầu tiên,
  // vì kho phiên phải biết kênh thì lượt đầu mới đi đúng đường (server/main.py: /sessions/new).
  // `sidChiDinh`: mở đúng hội thoại này (đường từ hòm thư). Bỏ trống thì giữ lối cũ - cuộc
  // gần nhất của cộng sự, hoặc mở cuộc mới khi `moiHan`.
  async function moPhien(item, moiHan, sidChiDinh) {
    var ticket = ++opening;
    chatReady(false); veGiua(item);
    if (!item) return false;
    var still = function () { return active && ticket === opening && conDangXem(item); };
    try {
      vePhai(item);
      var b = encodeURIComponent(brain()), ch = kenh(item), id = sidChiDinh || null;
      if (!id && !moiHan) {
        var r = await api("/sessions?brain=" + b + "&channel=" + encodeURIComponent(ch) + "&limit=1");
        if (!still()) return false;
        if (r.sessions && r.sessions[0]) id = r.sessions[0].id;
      }
      if (!id) {
        var n = await api("/sessions/new", { method: "POST", body: fd({ brain: brain(), channel: ch }) });
        if (!still()) return false;
        // Câu lỗi của server (vd "channel phải là agent:<slug>...") là chữ cho NHẬT KÝ, không
        // phải chữ cho màn hình: nó nói về khuôn dữ liệu bên trong, không nói người dùng phải
        // làm gì, và không đi qua từ điển nên bản tiếng Anh vẫn ra tiếng Việt. Ghi ra console
        // cho người sửa lỗi, còn màn hình dùng câu của mình.
        if (!n.id) { try { console.warn("POST /sessions/new:", n.error); } catch (e2) {} throw new Error(t("ws.err_session")); }
        id = n.id;
      }
      S.sessionCuaPhien[id] = item.slug;
      if (window.JavisSessions) await window.JavisSessions.open(id, still);
      if (!still()) return false;
      if (!window.JavisSessions || window.JavisSessions.current() !== id) throw new Error(t("ws.err_session"));
      chatReady(true);
      luuViTri(id);
      if (S.loai === "workflow") veBuoc(item, tienDoHienTai(item));
      return true;
    } catch (e) {
      if (still()) { veLoi(t("ws.err_session")); if (window.JavisSessions) window.JavisSessions.new(); }
      return false;
    }
  }
  async function chayQuyTrinh() {
    var item = dangChon();
    if (!ready || S.loai !== "workflow" || !item || !window.JavisSend) return;
    var td = tienDoHienTai(item);
    if (td.trang_thai === "dang" || td.cho_duyet) return;
    var input = document.getElementById("chatInput");
    // Cờ wfRun: bấm nút Chạy là ý định chạy đã nói rõ bằng một cú bấm, nên server
    // không xét lại xem câu trong ô nhập có phải đang nói về chính quy trình không.
    window.JavisSend((input && input.value.trim()) || t("ws.run_default"), { wfRun: true });
  }
  function veLoi(msg) { var el = S.el && S.el.querySelector("#wsIdentity"); if (el) {
    el.innerHTML += '<small class="ws-err">' + esc(msg) + '</small><button type="button" class="ws-btn" id="wsRetry">' + esc(t("ws.retry_session")) + '</button>';
    el.querySelector("#wsRetry").onclick = lamLai;
  } }
  // Thử lại = tải lại DANH SÁCH rồi mới mở phiên, không phải chỉ mở lại phiên. Hỏng ở bước tải
  // danh sách (gọi /agents trượt) thì cột trái trống trơn và dangChon() trả null, nên cái nút
  // cũ chỉ gọi moPhien(null): nó xoá câu lỗi, thay bằng lời mời chọn một cộng sự ở một cột
  // trái không có gì, và không tải lại thứ vừa hỏng. Chủ dự án gặp đúng màn này (15/09).
  async function lamLai() {
    try { await taiDanhSach(); } catch (e) { if (active) { veGiua(dangChon()); veLoi(t("ws.err_list")); } return; }
    if (!active) return;
    veTrai(); chonMacDinh();
  }
  // `nhac` = câu thay cho lời mời chọn mục, dùng khi danh sách rỗng (chưa có gì để chọn cả).
  function veGiua(item, nhac) {
    var el = S.el && S.el.querySelector("#wsIdentity"); if (!el) return;
    // Không có mục nào để mở VÀ danh sách thật sự rỗng (đã tải xong) = màn khởi đầu.
    veKhoiDau(!item && daTai && !danhSach().length);
    if (!item) {
      el.innerHTML = '<strong>' + esc(nhac || t("ws.pick_one")) + '</strong>';
      if (nhac) { var o = document.getElementById("chatInput"); if (o) o.placeholder = nhac; }
      return;
    }
    el.innerHTML = (S.loai === "agent" ? avatar(item, 24) : ic("workflow")) + '<div><strong>' + esc(item.name) + '</strong></div>';
    var inp = document.getElementById("chatInput");
    if (inp) inp.placeholder = S.loai === "agent" ? t("ws.ph_agent", { ten: item.name }) : t("ws.ph_workflow");
  }

  // ---------- màn khởi đầu ----------
  // Brain mới tinh (hay tab Quy trình khi chưa có quy trình nào): cột giữa không có gì để trò
  // chuyện, ô nhập đã khoá từ chonMacDinh, mà màn hình chỉ nói một câu "chưa có cộng sự nào"
  // rồi để người dùng tự mò sang cột trái. Chủ dự án bấm vào giữa màn hình, không ra gì cả
  // (15/09). Nay chỗ khung chat là chính hai nút TẠO TRỢ LÝ và TẠO QUY TRÌNH, bấm là mở thẳng
  // trình tạo của Studio - kể cả nút của loại KHÁC tab đang đứng.
  function veKhoiDau(hien) {
    var el = S.el; if (!el) return;
    var main = el.querySelector(".ws-main"), host = el.querySelector("#wsOnboard");
    if (main && main.classList) main.classList.toggle("onboard-on", !!hien);
    if (!host) return;
    host.hidden = !hien;
    if (!hien) { host.innerHTML = ""; return; }
    var trong = !S.agents.length && !S.workflows.length;
    var tieu = trong ? t("ws.start_title") : t(S.loai === "agent" ? "ws.start_no_agent" : "ws.start_no_workflow");
    host.innerHTML = ic("bot", { cls: "ws-ob-ic", size: "34px" }) +
      '<h3>' + esc(tieu) + '</h3><p>' + esc(t("ws.start_desc")) + '</p>' +
      '<div class="ws-ob-acts">' +
        '<button type="button" class="ws-btn primary" id="wsObAgent">' + ic("plus") + ' ' + esc(t("ws.new_agent")) + '</button>' +
        '<button type="button" class="ws-btn primary" id="wsObWf">' + ic("plus") + ' ' + esc(t("ws.new_workflow")) + '</button>' +
        '<button type="button" class="ws-btn" id="wsObStore">' + ic("package") + ' Javis Store</button>' +
      '</div>';
    var nut = function (id, fn) { var b = host.querySelector(id); if (b) b.onclick = fn; };
    nut("#wsObAgent", function () { taoMoi("agent"); });
    nut("#wsObWf", function () { taoMoi("workflow"); });
    nut("#wsObStore", function () { if (window.JavisPacks && window.JavisPacks.moKho) window.JavisPacks.moKho(S.loai, "workspace", t("page.workspace.label")); });
  }

  function thuGonCaiDat() {
    var page = S.el && S.el.querySelector("#wsPage");
    if (page) page.classList.toggle("right-open", !window.matchMedia("(max-width: 1060px)").matches);
  }
  async function sauLuu(item, loai) {
    await taiDanhSach();
    if (!active || S.loai !== loai || S.chon[loai] !== item.slug) return;
    veTrai(); veGiua(dangChon());
    // Retry session setup after saving; never unlock a chat bound to the wrong agent.
    if (!ready && !await moPhien(dangChon(), false)) return;
    thuGonCaiDat();
    var input = document.getElementById("chatInput");
    if (input) input.focus();
  }

  // ---------- cột phải ----------
  /** Tab cột phải cho LOẠI đang xem: trợ lý và quy trình nhớ riêng (xem S.tabCua). */
  function tabTheoLoai() { return (S.tabCua && S.tabCua[S.loai]) || S.tabPhai; }
  function vePhai(item) {
    var host = S.el && S.el.querySelector("#wsRightSet"); if (!host) return;
    // TRẢ cây thư mục về trước khi vẽ lại cột phải. Vẽ lại chỉ ghi vào khung Cài đặt, nhưng
    // cây là node mượn và chỉ có một bản: trả rồi mượn lại theo tab đang mở là luật gọn nhất,
    // khỏi phải nhớ chỗ nào được phép ghi đè chỗ nào không.
    traCayThuMuc();
    if (!item) { host.innerHTML = ""; veLichSu(null); chonTabPhai(tabTheoLoai()); return; }
    if (S.loai === "agent") {
      host.innerHTML = '<div class="ws-rtitle">' + esc(t("ws.agent_settings")) + '</div><div class="ws-form" id="wsAgentForm"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>';
      // MƯỢN chính trình sửa agent của Studio (studio.js), không dựng bản thứ hai: chọn model,
      // chọn skill, nhóm... đã nằm ở đó, chép lại là hai bản trôi lệch nhau ngay lần sửa đầu.
      if (window.JavisStudio && window.JavisStudio.editAgent) {
        window.JavisStudio.editAgent(item, { host: host.querySelector("#wsAgentForm"),
          onSaved: async function () { await sauLuu(item, "agent"); } });
      }
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("agent", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_ag", { ten: item.name }))) return;
        await api("/agents/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.agent = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
    } else {
      var td = tienDoHienTai(item);
      host.innerHTML = '<div class="ws-workflow-head">'+ic("workflow")+'<h3>'+esc(item.name)+'</h3><p>'+esc(item.description || t("ws.wf_sub", {n:cacBuoc(item).length}))+'</p>'+
        '<button type="button" class="ws-btn primary ws-run-button" id="wsRun">'+ic("play")+' '+esc(t("ws.run"))+'</button></div>'+ '<div class="ws-rtitle">' + esc(t("ws.wf_progress")) + '</div>' +
        '<div class="ws-prog"><div style="width:' + phanTram(td) + '%"></div></div>' +
        '<div class="ws-status" id="wsWfStatus">' + esc(nhanTienDo(td)) + '</div>' +
        '<div class="ws-steps" id="wsSteps"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsEditWf">' + esc(t("ws.edit_steps")) + '</button>' +
        '<button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>';
      host.querySelector("#wsRun").onclick = chayQuyTrinh;
      veBuoc(item, td);
      host.querySelector("#wsEditWf").onclick = function () { var moi = dangChon() || item; window.JavisStudio && window.JavisStudio.editWorkflow(moi, { onSaved: async function () { await sauLuu(moi, "workflow"); } }); };
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("workflow", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_wf", { ten: item.name }))) return;
        await api("/workflows/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.workflow = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
    }
    veLichSu(item);
    chonTabPhai(tabTheoLoai());
  }
  function tenAgent(slug) { var a = S.agents.find(function (x) { return x.slug === slug; }); return a ? a.name : (slug || ""); }
  // Tiến độ ĐANG XEM: lần chạy sống của phiên đang mở nếu có, không thì khung rỗng dựng từ
  // các bước khai trong file quy trình (để cột phải vẫn nói được quy trình này làm những gì).
  function tienDoHienTai(item) {
    var sid = window.JavisSessions ? window.JavisSessions.current() : null;
    if (sid && S.tienDo[sid]) return S.tienDo[sid];
    var buocs = cacBuoc(item);
    var td = tienDoMoi(buocs.length);
    td.buoc.forEach(function (b, i) { b.agent = tenAgent((buocs[i] || {}).agent); });
    return td;
  }
  function nhanTienDo(td) {
    if (td.trang_thai === "dang") return t("ws.running_step", { a: td.hien_tai + 1, b: td.buoc.length });
    if (td.trang_thai === "xong") return t("ws.done");
    if (td.trang_thai === "loi") return t("ws.failed");
    if (td.trang_thai === "dung") return t("ws.stopped");
    if (td.cho_duyet) return t("ws.waiting");
    return t("ws.ready");
  }
  function veBuoc(item, td) {
    var host = S.el && S.el.querySelector("#wsSteps"); if (!host) return;
    var buocs = cacBuoc(item);
    host.innerHTML = td.buoc.map(function (b, i) {
      var step = buocs[i] || {};
      var task = (step.name || step.title || step.task || "").replace(/\{\{input\}\}/g, t("ws.input_label")).replace(/\{\{prev\}\}/g, t("ws.previous_result"));
      var agent = agentOf(step.agent || b.agent);
      var nhan = { cho: t("ws.step_wait"), dang: t("ws.step_doing"), xong: t("ws.step_done"), loi: t("ws.step_err") }[b.trang_thai];
      return '<div class="ws-step ' + b.trang_thai + '"><span class="ws-num">' + (b.trang_thai === "xong" ? ic("check") : (i + 1)) + '</span>' +
        '<strong>' + esc(task.slice(0, 80) || t("ws.step_n", { n: i + 1 })) + '</strong><small>' + esc(nhan) + (b.loi ? ": " + esc(b.loi) : "") + '</small>' +
        '<div class="ws-who">' + avatar(agent, 26, b.trang_thai === "dang" ? "thinking" : "idle") + ' ' + esc(agent.name || b.agent || step.agent) + '</div></div>';
    }).join("") + (td.cho_duyet ? '<div class="ws-wait">' + esc(t("studio.wait1")) + ' "' + esc(td.cho_duyet.node) + '"' + (td.cho_duyet.prompt ? ": " + esc(td.cho_duyet.prompt) : "") +
      '<div><button type="button" class="ws-btn primary" id="wsApprove">' + esc(t("studio.approve")) + ' ' + esc(td.cho_duyet.code) + '</button><small>' + esc(t("studio.wait_warn")) + '</small></div></div>' : "");
    var ap = host.querySelector("#wsApprove");
    if (ap) ap.onclick = function () {
      ap.disabled = true;
      var sid = window.JavisSessions ? window.JavisSessions.current() : null;
      if (!sid || !window.JavisWsSend) return;
      window.JavisWsSend({ action: "wf_resume", session_id: sid, task_id: td.cho_duyet.task_id, node: td.cho_duyet.node, code: td.cho_duyet.code, brain: brain() });
      td.cho_duyet = null; td.trang_thai = "dang"; veBuoc(item, td);
    };
    var run = S.el.querySelector("#wsRun");
    if (run) { run.disabled = !ready || td.trang_thai === "dang" || !!td.cho_duyet; run.textContent = t(td.trang_thai === "dang" ? "ws.running" : "ws.run"); }
    var stt = S.el.querySelector("#wsWfStatus"); if (stt) stt.textContent = nhanTienDo(td);
    var pg = S.el.querySelector(".ws-prog > div"); if (pg) pg.style.width = phanTram(td) + "%";
  }
  // ---------- tab LỊCH SỬ (cột phải) ----------
  // Trước 0.59.3 lịch sử nằm DƯỚI ĐÁY khung Cài đặt: muốn xem lần chạy hôm qua thì phải cuộn
  // qua hết form sửa trợ lý, qua ba nút Xuất/Xoá, qua danh sách bước. Chủ dự án nói thẳng là
  // không tiện. Nay nó là một TAB riêng, ngang hàng với Cài đặt và Thư mục, đúng kiểu cột lịch
  // sử của trang Trò chuyện: bấm một cái là ra, không phải cuộn tìm.
  //
  // MỘT danh sách, không phải hai (chủ dự án chốt 16/09). Trước đây tab này xếp chồng "LẦN
  // CHẠY" lên trên "HỘI THOẠI", mà mỗi lần chạy quy trình ĐẺ RA đúng một hội thoại: cùng một
  // việc hiện hai lần, hai mốc giờ, hai chỗ để bấm, và bấm vào đâu cũng mở đúng một phiên.
  // Nay chỉ còn danh sách hội thoại - bản mượn của trang Trò chuyện, sẵn ô tìm, ghim, đổi
  // tên, xoá và nút "Xem thêm" - còn thứ RIÊNG của lần chạy thì gắn thẳng vào hàng hội thoại
  // của nó qua hàm trang trí: avatar những trợ lý đã phối hợp, và trạng thái (xong/lỗi/chờ).
  // Nút "Hội thoại mới" cùng ô tìm nhờ vậy đứng ngay đầu tab, không bị một danh sách khác đẩy
  // xuống giữa cột.
  function veLichSu(item) {
    var host = S.el && S.el.querySelector("#wsRightHistory"); if (!host) return;
    S.lanChay = {};
    if (!item) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.pick_one")) + '</div>'; return; }
    host.innerHTML = '<div class="ws-chatside" id="wsSess"></div>';
    // Danh sách hội thoại là CHÍNH cột lịch sử của trang Trò chuyện (sessions-ui.js), gắn vào
    // đây ở chế độ lọc theo kênh: cùng ô tìm, cùng nhóm theo ngày, cùng ghim / đổi tên / xoá,
    // cùng nút "Xem thêm". Chủ dự án yêu cầu đúng trải nghiệm ấy chứ không phải một danh sách
    // rút gọn khác; và một bản thứ hai thì lệch dần khỏi bản gốc ngay từ lần sửa đầu tiên.
    if (window.JavisChatSide && window.JavisChatSide.mount) {
      window.JavisChatSide.mount(host.querySelector("#wsSess"), {
        kenh: kenh(item), chiHoiThoai: true,
        onNew: function () { var x = dangChon(); if (x) moPhien(x, true); },
        trangTri: S.loai === "workflow" ? trangTriHang : null,
      });
    }
    if (S.loai === "workflow") taiLichSu(item);
  }
  // Trang trí một hàng hội thoại bằng dữ liệu LẦN CHẠY của đúng phiên đó. Tra sổ S.lanChay
  // (taiLichSu nạp) chứ không đi hỏi mạng ở đây: hàm này chạy một lần cho MỖI hàng, mỗi lần
  // danh sách vẽ lại.
  function trangTriHang(s) {
    var r = S.lanChay && S.lanChay[s && s.id]; if (!r) return null;
    var slugs = Array.from(new Set((r.steps || []).map(function (b) { return b.agent; }).filter(Boolean))).slice(0, 3);
    var nhan = r.nhan || r.status || "";
    return {
      dau: slugs.length ? '<span class="ws-run-avatars">' + slugs.map(function (sl) { return avatar(agentOf(sl), 18); }).join("") + '</span>' : "",
      meta: nhan ? '<span class="ci-badge ws-run-badge ' + esc(r.status || "") + '">' + esc(nhan) + '</span>' : "",
    };
  }
  // Hàng của phiên ĐANG MỞ do chính cột lịch sử tự tô (lớp .active, mỗi lần
  // JavisChatSide.refresh chạy) - từ 0.59.20 tab này không còn danh sách nào của riêng nó nữa
  // nên ở đây không phải tô gì cả.
  // Nạp SỔ lần chạy: session_id -> lần chạy. Không vẽ danh sách nào cả - dữ liệu này chỉ để
  // trang trí hàng hội thoại tương ứng (xem trangTriHang), nên nạp xong thì bảo cột lịch sử
  // vẽ lại là đủ. Lấy 40 cho khớp hai trang "Xem thêm" của cột đó (mỗi trang 20).
  async function taiLichSu(item) {
    var r = await api("/workflows/runs?brain=" + encodeURIComponent(brain()) + "&slug=" + encodeURIComponent(item.slug) + "&limit=40");
    // Về trễ: người dùng có thể đã đổi sang mục khác trong lúc chờ mạng. Ghi vào sổ lúc này là
    // dán nhãn lần chạy của quy trình A lên hội thoại của quy trình B.
    if (!conDangXem(item)) return;
    var so = {};
    (r.runs || []).forEach(function (x) { if (x.session_id) so[x.session_id] = x; });
    S.lanChay = so;
    if (window.JavisChatSide && window.JavisChatSide.refresh) window.JavisChatSide.refresh();
  }
  // ---------- sự kiện quy trình từ WebSocket ----------
  // app.js chuyển MỌI khung wf_event vào đây, kể cả của phiên đang không mở: ghi theo
  // session_id để mở lại phiên đó là thấy ngay tiến độ, không phải chạy lại từ đầu.
  function onWfEvent(frame) {
    var sid = frame.session_id, ev = frame.event || {}; if (!sid) return;
    var item = dangChon();
    // Phiên mở từ cột LỊCH SỬ đi thẳng qua JavisSessions.open (module lịch sử lo), không qua
    // moPhien nên chưa có tên trong sổ "phiên nào của cộng sự nào". Lần chạy đầu tiên ở đó mà
    // thiếu dòng này thì icon quay ở cột trái không bao giờ bật: dangChay() tra sổ không thấy.
    if (item && !S.sessionCuaPhien[sid] &&
        window.JavisSessions && window.JavisSessions.current() === sid) {
      S.sessionCuaPhien[sid] = item.slug;
    }
    if (!S.tienDo[sid]) {
      var n = (item && S.loai === "workflow" && S.sessionCuaPhien[sid] === item.slug) ? cacBuoc(item).length : Number(ev.steps || 0);
      S.tienDo[sid] = tienDoMoi(n);
    }
    apDung(S.tienDo[sid], ev);
    // Vẽ lại danh sách trái ở MỌI sự kiện, kể cả của phiên đang không mở: icon quay ở hàng
    // quy trình đọc từ S.tienDo, nên không vẽ lại thì bắt đầu chạy mà hàng vẫn đứng im, và
    // chạy xong rồi mà vẫn quay.
    if (S.loai === "workflow") veDanhSach();
    var cur = window.JavisSessions ? window.JavisSessions.current() : null;
    if (item && S.loai === "workflow" && cur === sid) {
      veBuoc(item, S.tienDo[sid]);
      // Xong / lỗi / chờ duyệt = lịch sử chạy vừa có dòng mới và mốc "chạy gần nhất" vừa đổi,
      // nên danh sách bên trái phải xếp lại. Không làm thì quy trình vừa chạy vẫn nằm cuối.
      if (ev.type === "done" || ev.type === "error" || ev.type === "wait_user") { taiLichSu(item); taiDanhSach().then(veTrai); }
    }
  }

  // Lượt của một phiên vừa KẾT THÚC (app.js gọi ở khung turn_done). Đây là lưới an toàn cuối
  // cùng cho tiến độ: server bắn `stopped` khi người dùng bấm Dừng, nhưng lượt còn có thể chết
  // theo những đường không kịp phát sự kiện nào (engine bị giết, WebSocket rớt giữa chừng, tiến
  // trình máy chủ khởi động lại). Lượt xong rồi mà tiến độ vẫn "dang" thì chắc chắn nó sẽ không
  // bao giờ nhúc nhích nữa - đóng nó lại ở đây, đừng để icon quay vĩnh viễn.
  function onTurnDone(sid) {
    if (!sid || !S.tienDo[sid] || S.tienDo[sid].trang_thai !== "dang") return;
    apDung(S.tienDo[sid], { type: "stopped" });
    if (S.loai === "workflow") veDanhSach();
    var item = dangChon();
    var cur = window.JavisSessions ? window.JavisSessions.current() : null;
    if (item && S.loai === "workflow" && cur === sid) veBuoc(item, S.tienDo[sid]);
  }

  // ---------- tạo mới ----------
  // `loai` chỉ rõ tạo TRỢ LÝ hay QUY TRÌNH: màn khởi đầu bày cả hai nút nên nút được bấm mới
  // là thứ quyết định, không phải tab đang đứng. Bỏ trống thì theo tab (nút Tạo mới cột trái).
  function taoMoi(loai) {
    if (!window.JavisStudio) return;
    loai = loai === "agent" || loai === "workflow" ? loai : S.loai;
    var sau = async function (saved) {
      await taiDanhSach(); if (!active) return;
      // Tạo XONG thì chuyển hẳn sang tab của thứ vừa tạo. Bấm "Tạo quy trình" từ màn khởi đầu
      // trong khi tab đang là Trợ lý mà không chuyển thì lưu xong lại nhìn vào một danh sách
      // rỗng khác, tưởng quy trình vừa tạo bốc hơi.
      if (saved && saved.slug) { S.loai = loai; S.nhom = ""; S.chon[loai] = saved.slug; }
      if (S.loai !== loai) return;
      luuChon(); veTrai();
      if (await chonMacDinh()) { thuGonCaiDat(); var o = document.getElementById("chatInput"); if (o) o.focus(); }
    };
    // Không truyền `host`: tạo mới vẫn mở modal của Studio (cột phải đang là form của mục
    // đang chọn, vẽ đè lên đó thì người dùng tưởng mình đang sửa mục cũ).
    if (loai === "agent") window.JavisStudio.editAgent(null, { onSaved: sau });
    else window.JavisStudio.editWorkflow(null, { onSaved: sau });
  }

  // Rời trang: trả ô nhập về lời mời chung. veGiua() đổi placeholder thành "Nhắn cho <trợ lý>",
  // mà ô nhập là node MƯỢN của app - không trả lại thì sang trang Trò chuyện nó vẫn mời người
  // dùng nhắn cho một cộng sự không còn ở đâu trên màn hình. console.js gọi hàm này trong
  // _pageLeave, ngay trước khi trả node chat về HUD.
  // console.js cũng trả cây trong _returnChatNodes, nhưng trả ở đây nữa là đúng chỗ: tab Thư
  // mục là của trang NÀY mượn, nên trang này tự dọn lấy chứ không phó thác cho người gọi.
  // Hàm trả kiểm _vaultSlot trước nên gọi hai lần vẫn vô hại.
  function roi() {
    active = false; opening++; chatReady(true);
    dongMenu(); traCayThuMuc(); traKhungChat();
    // XOÁ câu đang tìm. S.q sống ở mức module còn ô nhập chết theo DOM của trang, nên giữ lại
    // là lần sau quay vào danh sách đã bị lọc mà ô tìm thì rỗng và đang thu: người dùng thấy
    // cộng sự của mình biến mất, không có gì trên màn hình nói vì sao.
    S.q = "";
    var inp = document.getElementById("chatInput");
    if (inp) inp.placeholder = t("bar.input_ph");
  }

  window.JavisWorkspace = { render: render, roi: roi, openCommand: openCommand, openTab: openTab, onTurnDone: onTurnDone, canSend: function () { return !active || ready; }, onChatState: onChatState, chayQuyTrinh: chayQuyTrinh, onWfEvent: onWfEvent, sapXep: sapXep, loc: loc, tienDoMoi: tienDoMoi, apDung: apDung, phanTram: phanTram,
    dangChay: dangChay, tabPhai: chonTabPhai, gomNhom: gomNhom, nhomHtml: nhomHtml, chonNhom: chonNhom, state: function () { return S; } };
  // Sidebar lịch sử mở phiên trực tiếp qua JavisSessions.open, ngoài đường moPhien ở trên.
  // Ghi lại sau khi nó mở xong để lần dựng trang sau vẫn ở đúng cuộc đã chọn.
  window.addEventListener("javis:sessions-changed", function () {
    if (active && ready && window.JavisSessions) luuViTri(window.JavisSessions.current());
  });
})();
