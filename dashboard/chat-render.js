/* chat-render.js - bo render chat "chan that nhu Claude" cho Javis OS.
   Thay bo markdownToHtml regex cu trong app.js: markdown day du (heading h1-h6,
   danh sach co thu tu + long + checkbox, blockquote, duong ke ngang, in nghieng,
   gach ngang, link, anh), code block co nhan ngon ngu + to mau cu phap, render an
   toan khi dang stream (code fence chua dong van hien dep), va ARTIFACT: HTML/SVG/
   mermaid/code dai hien thanh the gon trong chat, bam mo panel ben phai (Xem truoc /
   Ma nguon / Copy / Tai ve). Tach rieng de khong dung logic khac cua app.js.

   An toan XSS: render theo whitelist (moi text deu escape, chi dung dung the ta sinh
   ra), href/src duoc loc; artifact HTML chay trong iframe sandbox co lap (khong
   allow-same-origin), SVG render trong iframe khong cho script. Khong phu thuoc CDN
   tru mermaid (lazy-load khi can, offline thi suy giam nhe nhang thanh ma nguon).
   Ghi chu: KHONG dung ky tu em dash o bat ky dau.

   Placeholder dung 2 ky tu vung private-use  /  lam moc (khong bao gio
   xuat hien trong text AI) -> tranh nuot nham chuoi kieu " 3 " trong cau. */
(function () {
  "use strict";

  var OPEN = String.fromCharCode(0xE000), CLOSE = String.fromCharCode(0xE001);   // sentinel placeholder (private-use, khong xuat hien trong text)

  // ---------------------------------------------------------------- helpers
  // File này chạy hai chế độ: trong trình duyệt và dưới node (test require nó).
  // Dưới node không có window nên không có ic() - trả về chuỗi rỗng để phần logic
  // vẫn test được mà không phải kéo cả tầng icon vào. Trong trình duyệt thì
  // icons.js đã nạp trước (index.html bảo đảm thứ tự, có test canh) nên lấy
  // được hàm thật.
  var ic = (typeof window !== "undefined" && window.ic) ? window.ic : function () { return ""; };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function safeHref(x) {
    x = String(x == null ? "" : x).trim();
    return /^(https?:\/\/|mailto:|\/)/i.test(x) ? x : "";
  }
  // Brain GAN CHO LUOT RENDER hien tai. null = lay brain dang chon tren thanh cong cu.
  // Vi sao can: duong dan anh trong tin nhan la tuong doi ("attachments/x.png"), khong mang
  // brain. Truoc day moi lan ve lai deu ghep voi brain DANG chon, nen mo mot hoi thoai cu
  // trong khi dang o brain khac la anh tro sai cho, 404, roi bi thay bang o xam - nguoi dung
  // tuong Javis tu xoa anh di. Gan brain cua chinh hoi thoai do vao luot render thi het.
  var _brainForRender = null;
  function brainPath() {
    if (_brainForRender != null) return _brainForRender;
    try { return (typeof currentBrainPath === "function") ? currentBrainPath() : ""; }
    catch (e) { return ""; }
  }
  function fileUrl(p, brainOverride) {
    var b = brainOverride == null ? brainPath() : brainOverride;
    return "/files/raw?brain=" + encodeURIComponent(b) +
      "&path=" + encodeURIComponent(String(p || "").replace(/^\.?\//, ""));
  }
  function resolveSrc(s) {
    s = String(s || "").trim();
    return /^(https?:|data:|blob:|\/)/i.test(s) ? s : fileUrl(s);
  }
  // Path tro toi file/thu muc TRONG vault (khong phai URL ngoai / data / o dia)?
  function isVaultRel(p) {
    p = String(p == null ? "" : p).trim();
    return !!p && !/^(https?:|mailto:|data:|blob:|\/)/i.test(p);
  }
  function decodeQueryPart(s) {
    try { return decodeURIComponent(String(s || "").replace(/\+/g, " ")); }
    catch (e) { return ""; }
  }
  // Duong dan trong link/anh markdown la URL-ish: Obsidian, VS Code va ca AI deu ma hoa phan
  // tram khi ghi ra, nen "07 - Wiki/LLM Wiki.md" thanh "07%20-%20Wiki/LLM%20Wiki.md". Ten THAT
  // tren dia khong he co %20. Khong go o day thi ta di hoi server mot file ten "07%20-%20Wiki",
  // khong bao gio co, va cu bam chet IM - dung trieu chung chu repo bao: bam vao link khong
  // mo ra gi ca. Con anh thi te hon mot bac: fileUrl() ma hoa THEM lan nua (%2520) nen server
  // nhan lai dung chuoi %20 sau khi giai ma mot lan, ra 404, o anh thanh o xam.
  //
  // KHONG doi "+" thanh khoang trang: do la luat cua query string, con "+" la ky tu hop le
  // trong ten file. Chuoi khong co %hh thi tra ve nguyen ven, va decodeURIComponent nem loi
  // voi thu nhu "100%.md" - bat lai roi giu nguyen, vi ten that co the co dau % that.
  function decodeVaultPath(s) {
    s = String(s == null ? "" : s);
    if (!/%[0-9a-f]{2}/i.test(s)) return s;
    try { return decodeURIComponent(s); } catch (e) { return s; }
  }
  function currentBrainMatches(name) {
    var b = String(brainPath() || "").replace(/\\/g, "/").replace(/\/+$/, "");
    var base = b === "brain" ? "Brain Default" : b.split("/").pop();
    return String(base || "").toLowerCase() === String(name || "").toLowerCase();
  }
  // Link file noi bo co the do server tao dung (/files/raw), do AI ghi sai theo duong dan dia
  // (/brains/<ten brain>/<file>), hoac la URL day du cung origin. Chuan hoa ve {brain,path};
  // link /brains chi doi khi dung CHINH brain dang chat, tranh mo nham file trung ten o brain khac.
  function appFileRef(href) {
    href = String(href == null ? "" : href).trim();
    if (/^https?:\/\//i.test(href) && typeof window !== "undefined" && window.location) {
      try {
        var u = new URL(href, window.location.href);
        if (u.origin !== window.location.origin) return null;
        href = u.pathname + u.search;
      } catch (e) { return null; }
    }
    if (/^\/files\/(?:raw|download)(?:\?|$)/i.test(href)) {
      var q = href.indexOf("?") >= 0 ? href.slice(href.indexOf("?") + 1) : "";
      var pm = /(?:^|&)path=([^&]*)/i.exec(q);
      if (!pm) return null;
      var bm = /(?:^|&)brain=([^&]*)/i.exec(q);
      var path = decodeQueryPart(pm[1]).replace(/\\/g, "/").replace(/^\.?\//, "");
      return path ? { path: path, brain: bm ? decodeQueryPart(bm[1]) : brainPath() } : null;
    }
    var direct = /^\/brains\/([^/]+)\/(.+)$/i.exec(href);
    if (direct) {
      var brainName = decodeQueryPart(direct[1]);
      var rel = decodeQueryPart(direct[2]).replace(/\\/g, "/").replace(/^\/+/, "");
      if (rel && currentBrainMatches(brainName)) return { path: rel, brain: brainPath() };
    }
    var legacy = /^\/brain\/(.+)$/i.exec(href);
    if (legacy && brainPath() === "brain") {
      var legacyRel = decodeQueryPart(legacy[1]).replace(/\\/g, "/").replace(/^\/+/, "");
      if (legacyRel) return { path: legacyRel, brain: "brain" };
    }
    return null;
  }
  function appFilePath(href) {
    var ref = appFileRef(href);
    return ref ? ref.path : "";
  }
  // File thanh pham/media trong brain: click o chat la TAI VE. Note .md va file nguon text
  // van mo editor; URL http(s) duoc xu ly rieng va luon mo tab moi.
  //
  // .html KHONG con nam trong danh sach nay (0.24.5). No la file NGUON, va bat mot cu bam
  // phai roi file xuong may la duong vong dai nhat: muon xem thi phai mo bang app khac,
  // muon sua mot chu thi phai sua ngoai roi tai len lai. Trinh sua da co san ca hai nut
  // "Mo tab moi" va "Tai ve", nen mo trinh sua la duong ngan hon cho CA hai y dinh.
  var DOWNLOAD_EXT_RE = /\.(?:svg|png|jpe?g|gif|webp|bmp|ico|mp4|webm|mov|avi|mkv|m4v|mp3|wav|m4a|ogg|flac|pdf|docx?|xlsx?|pptx?|zip|rar|7z|tar|gz)$/i;
  function isDownloadFile(rawpath) {
    var clean = String(rawpath || "").split(/[?#]/)[0].replace(/\/+$/, "");
    return DOWNLOAD_EXT_RE.test(clean);
  }
  function vaultDownload(rawpath, extraCls, brainOverride) {
    var clean = String(rawpath || "").replace(/^\.?\//, "");
    return 'href="' + esc(fileUrl(clean, brainOverride) + "&dl=1") + '" data-vault-path="' + esc(clean) +
      '" class="jv-fdownload' + (extraCls ? " " + extraCls : "") +
      '" download title="Tải file về"';
  }
  // Thuoc tinh <a> mo trang Tep tin dung vi tri file/thu muc. Giu href deep-link (#open=..) de
  // Ctrl/giua chuot mo tab trinh duyet moi cung nhay dung cho; bam thuong -> mo trong app.
  // Duoi file MO RA SUA DUOC. Giu khop voi VT_TEXT_EXTS trong console.js - danh sach nay chi
  // dung de dat CHU cho dung, con quyet dinh mo o dau thi console.js lo.
  var EDIT_EXT_RE = /\.(?:md|txt|json|ya?ml|csv|js|ts|py|html?|css|toml|ini|log|sh|bat|xml|svg|env)$/i;
  function vaultLoc(rawpath, extraCls) {
    var clean = String(rawpath || "").replace(/^\.?\//, "");
    // Noi dung chuot dung viec cu bam do LAM: file sua duoc thi mo trinh sua, thu muc thi ve
    // trang Tep tin. Chu cu ghi "Mo vi tri trong Tep tin" cho MOI thu, nen bam vao mot file
    // .html roi thay trinh sua bung ra la mot bat ngo - dung huong nhung sai loi hua.
    var tit = EDIT_EXT_RE.test(clean.split(/[?#]/)[0]) ? "Mở ra sửa" : "Mở vị trí trong Tệp tin";
    return 'href="#open=' + esc(encodeURIComponent(clean)) + '" data-vault-path="' + esc(clean) +
      '" class="jv-floc' + (extraCls ? " " + extraCls : "") + '" title="' + tit + '"';
  }
  function vaultLink(rawpath, extraCls, brainOverride) {
    return isDownloadFile(rawpath)
      ? vaultDownload(rawpath, extraCls, brainOverride)
      : vaultLoc(rawpath, extraCls);
  }
  // Inline code chua DUONG DAN FILE vault (vd `Javis/loops/x.md`)? Tra ve path da chuan hoa, "" neu khong phai.
  // Chi nhan khi trong giong path that: co duoi file + (co thu muc / la .md tran), khong ky tu cam cua ten file
  // Windows (":" loai luon URL va lenh co cong cu), khong leo thang "..".
  function codeFilePath(c) {
    var t = String(c == null ? "" : c).trim().replace(/\\/g, "/").replace(/^\.?\//, "");
    if (t.length < 4 || t.length > 240) return "";
    if (!isVaultRel(t)) return "";
    if (/[:<>"|?*\[\]]/.test(t)) return "";
    if (!/\.[a-z0-9]{1,6}$/i.test(t)) return "";
    if (!(t.indexOf("/") >= 0 || /\.md$/i.test(t))) return "";
    if (/(^|\/)\.\.(\/|$)/.test(t)) return "";
    return t;
  }
  // Wikilink [[target]] / [[target|alias]] -> the <a> dieu huong kieu Wikipedia. data-vault-path giu target GOC
  // (round-trip WYSIWYG -> markdown van ra [[..]]); click se tu TIM file dich trong vault (wkResolve ben duoi).
  function wikiLinkHtml(target, alias) {
    var label = (alias != null && alias.trim()) ? alias.trim() : target;
    return '<a href="#open=' + esc(encodeURIComponent(target)) + '" data-vault-path="' + esc(target) + '"' +
      (label !== target ? ' data-wiki-alias="' + esc(label) + '"' : "") +
      ' class="jv-wikilink" title="Mở note: ' + esc(target) + '">' + esc(label) + "</a>";
  }
  // FNV-1a -> id ngan on dinh cho artifact (cung noi dung -> cung id qua cac lan re-render khi stream)
  function hashId(s) {
    var h = 0x811c9dc5;
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = (h * 0x01000193) >>> 0; }
    return "a" + h.toString(36);
  }

  // ---------------------------------------------------------------- to mau cu phap (nhe, da ngon ngu)
  var KW = ("await async break case catch class const continue debugger default delete do else " +
    "export extends finally for from function if implements import in instanceof interface let " +
    "new package private protected public return static super switch this throw try typeof var " +
    "void while with yield def elif except lambda nonlocal global pass raise as assert del print " +
    "self and or not is None True False func fn fun struct type enum trait impl match where use " +
    "mut pub end then local echo require include namespace foreach when unless begin module").split(/\s+/);
  var KWSET = {}; KW.forEach(function (k) { KWSET[k] = 1; });
  var RE_HASH = /(\/\/[^\n]*|\/\*[\s\S]*?\*\/|#[^\n]*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|(\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|([A-Za-z_$][A-Za-z0-9_$]*)|([\s\S])/g;
  var RE_NOHASH = /(\/\/[^\n]*|\/\*[\s\S]*?\*\/)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|(\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|([A-Za-z_$][A-Za-z0-9_$]*)|([\s\S])/g;
  function highlight(code, lang) {
    lang = (lang || "").toLowerCase();
    var useHash = /^(py|python|sh|bash|zsh|shell|yaml|yml|ruby|rb|toml|ini|conf|r|perl|pl|make|makefile|dockerfile|nginx|env|properties|cmake)$/.test(lang) || /^#!/.test(code);
    var re = useHash ? RE_HASH : RE_NOHASH;
    re.lastIndex = 0;
    var out = "", m;
    while ((m = re.exec(code)) !== null) {
      if (m[1] != null) out += '<span class="tok-c">' + esc(m[1]) + "</span>";
      else if (m[2] != null) out += '<span class="tok-s">' + esc(m[2]) + "</span>";
      else if (m[3] != null) out += '<span class="tok-n">' + esc(m[3]) + "</span>";
      else if (m[4] != null) out += (KWSET[m[4]] ? '<span class="tok-k">' + esc(m[4]) + "</span>" : esc(m[4]));
      else out += esc(m[5]);
      if (re.lastIndex === m.index) re.lastIndex++;   // chong ket vong lap
    }
    return out;
  }

  // ---------------------------------------------------------------- artifact registry + phat hien
  var registry = {};   // id -> { type, lang, code }
  var _choTrinhSua = false;   // dang render cho trinh sua .md (xem mdToHtml)
  function fenceType(lang, code) {
    lang = (lang || "").trim().toLowerCase();
    var head = code.slice(0, 400).replace(/^\s+/, "").toLowerCase();
    if (lang === "mermaid") return "mermaid";
    if (lang === "svg" || /^<svg[\s>]/.test(head)) return "svg";
    if (lang === "html" || lang === "xml" || /^<!doctype html|^<html[\s>]/.test(head)) return "html";
    var lines = code.split("\n").length;
    if (lines >= 24 || code.length >= 800) return "code";   // file code dai -> artifact
    return "";   // code ngan -> khoi code inline
  }
  function artTitle(type, lang) {
    if (type === "html") return "Trang HTML";
    if (type === "svg") return "Anh SVG";
    if (type === "mermaid") return "So do";
    return "Ma " + ((lang || "text").toUpperCase());
  }
  function artIcon(type) {
    return ic(type === "html" ? "globe" : type === "svg" ? "image" : type === "mermaid" ? "chart-column" : "file");
  }
  function artifactCard(type, lang, code) {
    var id = hashId(type + "" + code);
    registry[id] = { type: type, lang: lang, code: code };
    var sub = code.split("\n").length + " dong · bam de xem";
    return '<div class="jv-art" role="button" tabindex="0" data-art="' + id + '">' +
      '<span class="jv-art-ic">' + artIcon(type) + "</span>" +
      '<span class="jv-art-meta"><span class="jv-art-title">' + esc(artTitle(type, lang)) + "</span>" +
      '<span class="jv-art-sub">' + esc(sub) + "</span></span>" +
      '<span class="jv-art-open">Mo ▸</span></div>';
  }

  function codeBlockHtml(lang, code, streaming) {
    var live = streaming ? " code-live" : "";
    return '<div class="code-wrap' + live + '">' +
      '<div class="code-head"><span class="code-lang">' + esc(lang || "text") + "</span>" +
      '<button class="code-copy" type="button">⧉ Copy</button></div>' +
      '<pre class="code-block">' + highlight(code, lang) + "</pre></div>";
  }
  // Khoi ```dataview (cam hung obsidian-dataview): giu truy van trong data-dv-q (encode de an toan
  // attribute), dataview.js tu phat hien va chay. contenteditable=false de trong WYSIWYG khong sua
  // nham ket qua; turndown rule (console.js) tra lai dung fence goc khi luu.
  function dataviewHtml(lang, code) {
    var title = lang === "tasks" ? ic("list-todo") + " Việc (tasks)" : ic("table-2") + " Dataview";
    return '<div class="jv-dataview" contenteditable="false" data-dv-lang="' + esc(lang) +
      '" data-dv-q="' + esc(encodeURIComponent(code)) + '">' +
      '<div class="jv-dv-head"><span class="jv-dv-title">' + title + "</span></div>" +
      '<div class="jv-dv-body"><span class="jv-dv-wait">Đang chạy truy vấn…</span></div></div>';
  }
  function renderFence(info, code, streaming) {
    var lang = (info || "").trim().split(/\s+/)[0] || "";
    code = code.replace(/\n$/, "");
    if (streaming) return codeBlockHtml(lang, code, true);   // fence chua dong: khoi code song, chua thanh artifact
    if (/^(dataview(js)?|tasks)$/i.test(lang)) return dataviewHtml(lang.toLowerCase(), code);
    var type = fenceType(lang, code);
    // Trong TRINH SUA: khoi code dai (type "code") giu nguyen hinh khoi code de con doc va
    // sua duoc tai cho. Thu no thanh the artifact la noi dung "bien mat" giua file - dung
    // canh chu repo bao 27/08 (mot the "Ma TEXT · 30 dong" nam giua .md). Turndown da co
    // luat jvcodewrap nen luu van tra ve dung fence ``` goc.
    // mermaid/svg/html VAN la the: chung co ban xem truoc that su, va tu 0.47.7 bam duoc
    // ca trong trinh sua (xem chot .jv-art trong handler click).
    if (type && !(_choTrinhSua && type === "code")) return artifactCard(type, lang, code);
    return codeBlockHtml(lang, code, false);
  }

  // ---------------------------------------------------------------- anh, link, bang
  // Anh khong tai duoc (404 vi da het han trong vung cache, bi xoa tay, hay doi ten) -> thay
  // bang o xam co chu, thay vi de icon vo tro. Phai xuat ra window (xem cuoi file) vi chuoi
  // onerror noi tuyen chay o pham vi toan cuc, khong thay bien trong IIFE nay.
  // Anh khong tai duoc thi CHUA chac la het han: rat hay gap la ghep sai brain (mo hoi thoai
  // cu trong khi dang chon brain khac). Cau cu do het cho "het han" nen nguoi dung tuong file
  // da bi xoa va di tim nham cho. Noi trung tinh + kem ten file de con lan ra.
  function imgGone(el) {
    var box = document.createElement("span");
    box.className = "chat-img-gone";
    var ten = "";
    try {
      var src = String(el.getAttribute("src") || "");
      var m = src.match(/[?&]path=([^&]*)/);
      ten = m ? decodeQueryPart(m[1]).split("/").pop() : src.split("/").pop();
    } catch (e) { ten = ""; }
    box.textContent = ten ? "Không mở được ảnh: " + ten : "Không mở được ảnh";
    box.title = "File có thể đã bị xoá, hoặc hội thoại này thuộc brain khác với brain đang chọn.";
    el.replaceWith(box);
  }
  function imgHtml(u, alt, rawpath) {
    var img = '<img class="chat-img" src="' + esc(u) + '" alt="' + esc(alt || "") + '"' +
      ' loading="lazy" onerror="jvImgGone(this)">';
    // Bam vao anh = XEM PHONG TO (lightbox), khong phai tai ve. Truoc day anh trong vault duoc
    // boc trong <a download> nen bam mot cai la file rot xuong may - muon xem cho ro thi phai
    // mo file vua tai, rat vong (chu repo bao 2026-07-31). Tai ve van con, nam trong lightbox.
    //
    // VAN giu the <a> tro thang toi anh (khong con dl=1): nho vay Ctrl/Cmd/giua chuot mo anh
    // goc ra tab moi nhu moi link khac - handler o duoi chi chan cu bam THUONG.
    var h = safeHref(rawpath && isVaultRel(rawpath) ? u : u);
    if (!h) return img;
    var vp = (rawpath && isVaultRel(rawpath))
      ? ' data-vault-path="' + esc(String(rawpath).replace(/^\.?\//, "")) + '"' : "";
    return '<a class="jv-img-link" href="' + esc(h) + '"' + vp +
      ' target="_blank" rel="noopener" title="Bấm để xem phóng to">' + img + "</a>";
  }
  // ---------------------------------------------------------------- frontmatter YAML
  // Khoi `---\n...\n---` o DAU mot file .md la METADATA (type, status, created...), khong phai
  // van ban de soan. Truoc ban nay no roi vao luat "--- = duong ke ngang", nen mo mot note trong
  // trinh sua WYSIWYG roi bam Luu la frontmatter bien thanh "* * *" cong may dong chu roi: file
  // hong that su, va moi thu doc metadata (Javis, dataview, Obsidian) doc truot tu do. Chu repo
  // gap dung canh nay 2026-08-13 ("mot so file .md dang khong doc duoc").
  //
  // Cach chua: cat ra thanh MOT khoi rieng, contenteditable=false, va giu NGUYEN VAN trong
  // data-fm. Luat turndown "jvfrontmatter" (console.js) tra lai dung chuoi do khi luu - cung co
  // che ma khoi dataview / code block da dung.
  var FRONTMATTER_RE = /^\uFEFF?---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/;
  function frontmatterHtml(block) {
    var than = String(block)
      .replace(/^\uFEFF?---[ \t]*\r?\n/, "")
      .replace(/\r?\n---[ \t]*\r?\n?$/, "");
    return '<div class="jv-fm" contenteditable="false" data-fm="' + esc(encodeURIComponent(block)) + '">' +
      '<div class="jv-fm-head">' + ic("tag") + " Thuộc tính</div>" +
      '<pre class="jv-fm-body">' + esc(than) + "</pre></div>";
  }
  function tableHtml(tbl) {
    var rows = tbl.trim().split("\n").filter(function (r) { return r.trim(); });
    var cells = function (r) { return r.replace(/^\||\|$/g, "").split("|").map(function (c) { return c.trim(); }); };
    var head = cells(rows[0]);
    var body = rows.slice(2).map(cells);
    var th = head.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("");
    var trs = body.map(function (r) {
      return "<tr>" + r.map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>";
    }).join("");
    return '<table class="md-table"><thead><tr>' + th + "</tr></thead><tbody>" + trs + "</tbody></table>";
  }

  // ---------------------------------------------------------------- inline (dam/nghieng/gach/xuong dong)
  function inline(s) {
    s = esc(s);
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/~~([^~]+)~~/g, "<del>$1</del>")
      .replace(/\b_([^_\n]+)_\b/g, "<em>$1</em>")
      .replace(/\n/g, "<br>");
    // Go dau \ thoat cua markdown (CUOI CUNG, sau khi da bat nhan manh - go truoc thi "\*" lai
    // thanh in nghieng, dung y nghia nguoc lai). Hai cai duoc cung mot nhat:
    //   - Dung chuan markdown: "\*" hien ra dau sao, khong hien ca dau gach cheo.
    //   - CHONG DON BACKSLASH trong trinh sua. Turndown thoat "1." dau dong thanh "1\.", ma neu
    //     o day khong go ra thi lan luu sau turndown lai thoat chinh dau gach do -> "1\\.", roi
    //     "1\\\." - moi lan mo file ra sua la file ban them mot lop (do trong file chu repo gui
    //     2026-08-13). Go ra thi vong lap dung yen: "1." -> "1\." -> "1." -> "1\.".
    // Code (fence lan inline) da nam trong placeholder tu truoc nen KHONG dinh nhat nay.
    return s.replace(/\\([\\`*_{}\[\]()#+\-.!>~|])/g, "$1");
  }

  // ---------------------------------------------------------------- block parse (line-based, ben hon regex)
  function isListLine(s) { return /^(\s*)([-*+]|\d+[.)])\s+/.test(s); }
  function buildList(lines) {
    var items = [];
    for (var k = 0; k < lines.length; k++) {
      var m = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(lines[k]);
      if (m) {
        var indent = m[1].replace(/\t/g, "    ").length;
        var ordered = /\d/.test(m[2]);
        var content = m[3], chk = null;
        var cm = /^\[([ xX])\]\s+(.*)$/.exec(content);
        if (cm) { chk = /[xX]/.test(cm[1]); content = cm[2]; }
        items.push({ indent: indent, ordered: ordered, checked: chk, lines: [content], children: [] });
      } else if (items.length) {
        items[items.length - 1].lines.push(lines[k].trim());   // dong noi tiep cua item tren
      }
    }
    var root = { children: [], indent: -1 }, stack = [root];
    items.forEach(function (it) {
      while (stack.length > 1 && it.indent <= stack[stack.length - 1].indent) stack.pop();
      stack[stack.length - 1].children.push(it);
      stack.push(it);
    });
    return renderList(root.children);
  }
  function renderList(items) {
    if (!items.length) return "";
    var tag = items[0].ordered ? "ol" : "ul";
    var html = "<" + tag + ">";
    items.forEach(function (it) {
      var box = it.checked == null ? "" :
        '<input type="checkbox" class="md-cb" contenteditable="false"' + (it.checked ? " checked" : "") + "> ";
      var cls = it.checked == null ? "" : ' class="task-item"';
      html += "<li" + cls + ">" + box + inline(it.lines.join(" ")) +
        (it.children.length ? renderList(it.children) : "") + "</li>";
    });
    return html + "</" + tag + ">";
  }
  function blockParse(text) {
    var lines = text.split("\n"), out = [], i = 0, n = lines.length, para = [];
    function flushPara() { if (para.length) { out.push("<p>" + inline(para.join("\n")) + "</p>"); para = []; } }
    var BLOCK_ONLY = new RegExp("^\\s*" + OPEN + "\\d+" + CLOSE + "\\s*$");
    while (i < n) {
      var line = lines[i];
      if (/^\s*$/.test(line)) { flushPara(); i++; continue; }
      if (BLOCK_ONLY.test(line)) { flushPara(); out.push(line.trim()); i++; continue; }
      var h = /^(#{1,6})\s+(.*)$/.exec(line);
      if (h) { flushPara(); var lv = h[1].length; out.push("<h" + lv + ">" + inline(h[2].trim()) + "</h" + lv + ">"); i++; continue; }
      if (/^\s*([-*_])\s*(?:\1\s*){2,}$/.test(line)) { flushPara(); out.push("<hr>"); i++; continue; }
      if (/^\s*>\s?/.test(line)) {
        flushPara();
        var q = [];
        while (i < n && /^\s*>\s?/.test(lines[i])) { q.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
        out.push("<blockquote>" + blockParse(q.join("\n")) + "</blockquote>");
        continue;
      }
      if (isListLine(line)) {
        flushPara();
        var block = [];
        while (i < n) {
          if (isListLine(lines[i]) || /^\s+\S/.test(lines[i])) { block.push(lines[i]); i++; continue; }
          if (/^\s*$/.test(lines[i]) && i + 1 < n && (isListLine(lines[i + 1]) || /^\s+\S/.test(lines[i + 1]))) { i++; continue; }
          break;
        }
        out.push(buildList(block));
        continue;
      }
      para.push(line); i++;
    }
    flushPara();
    return out.join("\n");
  }

  // ---------------------------------------------------------------- entry: markdown -> html
  // brain (tuy chon): brain cua HOI THOAI chua tin nhan nay. Bo trong = brain dang chon.
  // Dat quanh phan than de moi duong dan tuong doi trong tin nhan (anh, link file, wikilink)
  // deu phan giai theo dung brain do. mdToHtml chay dong bo nen bien module nay khong dan xen.
  // opts.trinhSua = true: dang render cho TRINH SUA .md chu khong phai bong bong chat.
  // Khac biet duy nhat: khoi code dai giu nguyen hinh khoi code thay vi thu thanh the
  // artifact (xem renderFence) - trong mot trinh sua thi noi dung phai NHIN THAY va sua
  // duoc, khong phai nam sau mot cai the.
  function mdToHtml(raw, brain, opts) {
    var truoc = _brainForRender, truocTS = _choTrinhSua;
    _brainForRender = (brain == null || brain === "") ? null : String(brain);
    _choTrinhSua = !!(opts && opts.trinhSua);
    try { return _mdToHtmlThan(raw); }
    finally { _brainForRender = truoc; _choTrinhSua = truocTS; }
  }
  function _mdToHtmlThan(raw) {
    raw = String(raw == null ? "" : raw);
    // Bo HTML comment (khoi dieu khien JAVIS_* luon vo hinh), ke ca comment chua dong luc stream
    raw = raw.replace(/<!--[\s\S]*?-->/g, "").replace(/<!--[\s\S]*$/, "");

    var ph = [];
    function put(html) { ph.push(html); return OPEN + (ph.length - 1) + CLOSE; }

    // 0) frontmatter YAML o DAU file .md -> khoi rieng, KHONG cho sua, giu nguyen van de luu lai
    //    dung tung ky tu. Xem frontmatterHtml ben duoi de biet vi sao day la mot loi mat du lieu.
    raw = raw.replace(FRONTMATTER_RE, function (m) { return put(frontmatterHtml(m)) + "\n"; });
    // 1) code fence hoan chinh (phai xu ly truoc moi thu)
    raw = raw.replace(/```([^\n]*)\n([\s\S]*?)```/g, function (_m, info, code) {
      return "\n" + put(renderFence(info, code, false)) + "\n";
    });
    // 1b) dang stream: fence mo chua dong o cuoi -> khoi code song
    raw = raw.replace(/```([^\n]*)\n([\s\S]*)$/, function (_m, info, code) {
      return "\n" + put(renderFence(info, code, true)) + "\n";
    });
    // 2) inline code (truoc bang/anh/link va truoc nhan manh). Code chua duong dan file vault
    //    (vd `Javis/loops/x.md`) -> boc link bam mo khung doc/sua luon.
    raw = raw.replace(/`([^`\n]+)`/g, function (_m, c) {
      var code = "<code>" + esc(c) + "</code>";
      var p = codeFilePath(c);
      if (p) return put("<a " + vaultLink(p, "jv-fcode") + ">" + code + "</a>");
      return put(code);
    });
    // 3) anh vault ![[..]] + anh markdown ![]() (giu URL qua placeholder de khong bi escape)
    raw = raw.replace(/!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]/g, function (_m, name) {
      name = name.trim();
      return put(imgHtml(resolveSrc(name), name, name));
    });
    // 3b) wikilink [[target]] / [[target|alias]] (anh ![[..]] da an o tren) -> link dieu huong nhu Wikipedia
    raw = raw.replace(/\[\[([^\[\]\n|]+?)(?:\|([^\[\]\n]*))?\]\]/g, function (_m, target, alias) {
      return put(wikiLinkHtml(target.trim(), alias));
    });
    // Duong dan trong () co the CO KHOANG TRANG + DAU NGOAC (vd "06 - Sources/Ten (Tu Duy Nguoc).md").
    // Bat ca cap ngoac can bang 1 tang, roi cat title markdown tuy chon o duoi ( "tieu de" / 'tieu de').
    raw = raw.replace(/!\[([^\]]*)\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)/g, function (_m, alt, src) {
      src = src.replace(/\s+(["']).*\1\s*$/, "").trim();
      if (isVaultRel(src)) src = decodeVaultPath(src);   // %20 -> khoang trang; xem decodeVaultPath
      return put(imgHtml(resolveSrc(src), alt, src));
    });
    // 4) link []() : URL ngoai -> tab moi; file/thu muc vault -> mo dung vi tri trong Tep tin; con lai giu cu
    raw = raw.replace(/\[([^\]]+)\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)/g, function (_m, t, href) {
      href = href.replace(/\s+(["']).*\1\s*$/, "").trim();
      var appRef = appFileRef(href);
      if (appRef) return put('<a ' + vaultLink(appRef.path, "", appRef.brain) + ">" + esc(t) + "</a>");
      if (/^(https?:|mailto:)/i.test(href)) return put('<a href="' + esc(href) + '" target="_blank" rel="noopener">' + esc(t) + "</a>");
      // URL that thi GIU nguyen ma hoa (do la duong dan mang); chi duong dan trong vault moi go
      // ra, vi no se di thang toi ten file tren dia. Xem decodeVaultPath.
      if (isVaultRel(href)) return put('<a ' + vaultLink(decodeVaultPath(href)) + ">" + esc(t) + "</a>");
      return put('<a href="' + esc(resolveSrc(href)) + '" target="_blank" rel="noopener">' + esc(t) + "</a>");
    });
    // 4b) URL tran (AI go thang, khong boc markdown) -> tu thanh link mo tab moi. Chay SAU khi link/anh/
    //     code da cat vao placeholder (sentinel) nen khong dung vao chung; loai dau cau/ngoac o duoi URL.
    raw = raw.replace(new RegExp("(^|[^\\]\"'=/])(\\bhttps?:\\/\\/[^\\s<>()\\[\\]" + OPEN + CLOSE + "]+)", "g"), function (_m, pre, url) {
      var trail = "", tm = /[.,;:!?)\]}'"]+$/.exec(url);
      if (tm) { trail = tm[0]; url = url.slice(0, url.length - trail.length); }
      return pre + put('<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(url) + "</a>") + trail;
    });
    // 5) bang markdown
    raw = raw.replace(/(^\|.+\|[ \t]*\n\|[ \t:|-]+\|[ \t]*\n(?:\|.*\|[ \t]*\n?)*)/gm, function (tbl) {
      return "\n" + put(tableHtml(tbl)) + "\n";
    });

    // 6) parse block phan con lai
    var html = blockParse(raw);

    // 7) tra lai placeholder (lap vai lan vi co the long: link trong bang, ...)
    var reIns = new RegExp(OPEN + "(\\d+)" + CLOSE, "g");
    var reHas = new RegExp(OPEN + "\\d+" + CLOSE);
    for (var pass = 0; pass < 6 && reHas.test(html); pass++) {
      html = html.replace(reIns, function (_m, idx) { return ph[+idx] != null ? ph[+idx] : ""; });
    }
    return html;
  }

  // ================================================================ ARTIFACT PANEL (chi trong trinh duyet)
  var panel = null, elTitle = null, elBody = null, curArt = null, curTab = "preview";

  function buildPanel() {
    if (panel) return panel;
    panel = document.createElement("div");
    panel.className = "jv-artpanel";
    panel.innerHTML =
      '<div class="jv-ap-head">' +
        '<span class="jv-ap-title">Artifact</span>' +
        '<span class="jv-ap-tabs">' +
          '<button class="jv-ap-tab active" data-tab="preview">Xem truoc</button>' +
          '<button class="jv-ap-tab" data-tab="code">Ma nguon</button>' +
        "</span>" +
        '<span class="jv-ap-actions">' +
          '<button class="jv-ap-btn" data-act="copy" title="Copy ma nguon">⧉</button>' +
          '<button class="jv-ap-btn" data-act="download" title="Tai ve">⇩</button>' +
          '<button class="jv-ap-btn jv-ap-close" data-act="close" title="Dong (Esc)">' + ic("x") + '</button>' +
        "</span>" +
      "</div>" +
      '<div class="jv-ap-body"></div>';
    document.body.appendChild(panel);
    elTitle = panel.querySelector(".jv-ap-title");
    elBody = panel.querySelector(".jv-ap-body");
    panel.addEventListener("click", onPanelClick);
    return panel;
  }
  function syncTabs() {
    if (!panel) return;
    panel.querySelectorAll(".jv-ap-tab").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === curTab);
    });
  }
  function openArtifact(id) {
    var art = registry[id];
    if (!art) return;
    buildPanel();
    curArt = art;
    elTitle.textContent = artTitle(art.type, art.lang);
    var hasPreview = art.type !== "code";
    panel.classList.toggle("no-preview", !hasPreview);
    curTab = hasPreview ? "preview" : "code";
    syncTabs();
    renderTab();
    panel.classList.add("open");
    document.body.classList.add("jv-artpanel-open");
  }
  function closePanel() {
    if (!panel) return;
    panel.classList.remove("open");
    document.body.classList.remove("jv-artpanel-open");
    if (elBody) elBody.innerHTML = "";   // don iframe/srcdoc
    curArt = null;
  }
  function frame(sandbox, srcdoc) {
    var f = document.createElement("iframe");
    f.className = "jv-ap-frame";
    f.setAttribute("sandbox", sandbox);
    f.setAttribute("referrerpolicy", "no-referrer");
    f.srcdoc = srcdoc;
    return f;
  }
  function renderTab() {
    var art = curArt; if (!art || !elBody) return;
    if (curTab === "code" || art.type === "code") {
      elBody.innerHTML = '<pre class="jv-ap-code code-block">' + highlight(art.code, art.lang) + "</pre>";
      return;
    }
    if (art.type === "html") {
      elBody.innerHTML = "";
      elBody.appendChild(frame("allow-scripts allow-forms allow-popups allow-modals", art.code));
      return;
    }
    if (art.type === "svg") {
      elBody.innerHTML = "";
      elBody.appendChild(frame("",   // sandbox rong = KHONG chay script trong svg
        '<!doctype html><meta charset="utf-8"><style>html,body{margin:0;height:100%;display:flex;' +
        "align-items:center;justify-content:center;background:#fff}svg{max-width:100%;max-height:100%}</style>" + art.code));
      return;
    }
    if (art.type === "mermaid") {
      elBody.innerHTML = '<div class="jv-ap-mermaid">Dang ve so do...</div>';
      renderMermaid(art.code, elBody.querySelector(".jv-ap-mermaid"));
      return;
    }
  }
  function onPanelClick(e) {
    var t = e.target.closest ? e.target.closest("[data-tab],[data-act]") : null;
    if (!t) return;
    if (t.dataset.tab) { curTab = t.dataset.tab; syncTabs(); renderTab(); return; }
    var act = t.dataset.act;
    if (act === "close") closePanel();
    else if (act === "copy" && curArt) copyText(curArt.code, t);
    else if (act === "download" && curArt) downloadArt(curArt);
  }
  function copyText(text, btn) {
    var run = (navigator.clipboard && window.isSecureContext)
      ? navigator.clipboard.writeText(text) : Promise.reject();
    run.catch(function () {
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      ta.remove();
    }).then(function () {
      if (btn) { var o = btn.textContent; btn.innerHTML = ic("check", { cls: "ic-ok" }); setTimeout(function () { btn.textContent = o; }, 1000); }
    });
  }
  function extFor(art) {
    if (art.type === "html") return "html";
    if (art.type === "svg") return "svg";
    if (art.type === "mermaid") return "mmd";
    var map = { javascript: "js", js: "js", typescript: "ts", ts: "ts", python: "py", py: "py",
      json: "json", css: "css", bash: "sh", sh: "sh", java: "java", go: "go", rust: "rs",
      c: "c", cpp: "cpp", html: "html", sql: "sql", yaml: "yml", yml: "yml", md: "md" };
    return map[(art.lang || "").toLowerCase()] || "txt";
  }
  function downloadArt(art) {
    var blob = new Blob([art.code], { type: "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = "artifact-" + hashId(art.code).slice(1, 7) + "." + extFor(art);
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 400);
  }

  // ---- mermaid: lazy-load, offline thi suy giam thanh ma nguon ----
  var mmState = 0, mmQueue = [], mmSeq = 0;   // 0 chua nap, 1 dang nap, 2 san sang, 3 hong
  function loadMermaid(cb) {
    if (mmState === 2) return cb(true);
    if (mmState === 3) return cb(false);
    mmQueue.push(cb);
    if (mmState === 1) return;
    mmState = 1;
    var s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js";
    s.onload = function () {
      try { window.mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" }); } catch (e) {}
      mmState = 2; var q = mmQueue; mmQueue = []; q.forEach(function (c) { c(true); });
    };
    s.onerror = function () { mmState = 3; var q = mmQueue; mmQueue = []; q.forEach(function (c) { c(false); }); };
    document.head.appendChild(s);
  }
  function renderMermaid(code, host) {
    if (!host) return;
    loadMermaid(function (ok) {
      if (!ok || !window.mermaid) {
        host.innerHTML = '<div class="jv-ap-note">Khong tai duoc thu vien so do (co the dang offline). Xem ma o tab Ma nguon.</div>' +
          '<pre class="code-block">' + esc(code) + "</pre>";
        return;
      }
      var id = "jvmm" + (++mmSeq);
      try {
        window.mermaid.render(id, code).then(function (res) { host.innerHTML = res.svg; })
          .catch(function () { host.innerHTML = '<div class="jv-ap-note">So do sai cu phap mermaid.</div><pre class="code-block">' + esc(code) + "</pre>"; });
      } catch (e) {
        host.innerHTML = '<div class="jv-ap-note">So do sai cu phap mermaid.</div><pre class="code-block">' + esc(code) + "</pre>";
      }
    });
  }

  // ---------------------------------------------------------------- wikilink resolver (tim file dich trong vault)
  // [[target]] thuong KHONG co duoi .md va co the chi la TEN note (kieu Obsidian) -> phai tim file that:
  // 1) trung ca duong dan (path ket thuc bang "/<target>.md"), 2) trung TEN note o bat ky thu muc nao.
  // Dung /files/search (server quet goc brain); uu tien .md, nhieu ket qua thi lay path ngan nhat.
  var wkHome = null;      // { b: brain, v: home } - tien to 'nha' cua brain theo tran duyet
  var wkCache = {};       // "brain|target" -> hit (chi cache khi TIM THAY)
  function wkNoAccent(s) {
    s = String(s == null ? "" : s);
    try { s = s.normalize("NFD").replace(/[̀-ͯ]/g, ""); } catch (e) {}
    return s.replace(/[đĐ]/g, "d").toLowerCase();
  }
  function wkGetHome(b) {
    if (wkHome && wkHome.b === b) return Promise.resolve(wkHome.v);
    return fetch("/files/list?brain=" + encodeURIComponent(b))
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { var h = (d && d.home) || ""; wkHome = { b: b, v: h }; return h; })
      .catch(function () { return ""; });
  }
  // Chi coi la "co duoi file" voi duoi THAT (ten note co dau cham kieu "Job ads N.bk" van la note .md)
  var WK_EXT = /\.(md|markdown|txt|json|ya?ml|csv|pdf|png|jpe?g|gif|webp|bmp|svg|html?|css|js|ts|py|xlsx?|docx?|pptx?|mp[34]|wav|zip)$/i;
  function wkResolve(target) {
    var b = brainPath();
    var t = String(target || "").split("#")[0].trim().replace(/\\/g, "/").replace(/^\.?\//, "").replace(/\/+$/, "");
    if (!t) return Promise.resolve(null);
    var key = b + "|" + wkNoAccent(t);
    if (wkCache[key]) return Promise.resolve(wkCache[key]);
    var hasExt = WK_EXT.test(t);
    var want = wkNoAccent(t + (hasExt ? "" : ".md"));
    var base = t.split("/").pop();
    var q = hasExt ? base.replace(WK_EXT, "") : base;
    return Promise.all([
      wkGetHome(b),
      fetch("/files/search?brain=" + encodeURIComponent(b) + "&q=" + encodeURIComponent(q) + "&limit=200")
        .then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; }),
    ]).then(function (rs) {
      var home = rs[0] || "";
      var items = (rs[1] && rs[1].items) || [];
      var wantBase = wkNoAccent(q);
      var best = null, bestScore = -1;
      items.forEach(function (it) {
        if (!it || !it.path) return;
        var ceil = String(it.path).replace(/\\/g, "/");
        var rel = (home && ceil.indexOf(home + "/") === 0) ? ceil.slice(home.length + 1) : ceil;
        var n = wkNoAccent(rel);
        var stem = wkNoAccent(String(it.name || "").replace(/\.[a-z0-9]+$/i, ""));
        var score = -1;
        if (n === want || n.slice(-(want.length + 1)) === "/" + want) score = 3;   // trung ca duong dan
        else if (stem === wantBase) score = 2;                                     // trung ten note (khac thu muc)
        if (score < 0) return;
        if ((it.ext || "").toLowerCase() === ".md") score += 0.5;                  // uu tien note .md
        if (score > bestScore || (score === bestScore && best && rel.length < best.rel.length)) {
          best = { ceil: ceil, rel: rel, name: it.name, ext: it.ext }; bestScore = score;
        }
      });
      if (best) wkCache[key] = best;   // miss KHONG cache: note co the duoc tao sau
      return best;
    });
  }
  function openWikilink(wl) {
    if (wl.classList.contains("jv-wl-busy")) return;
    var tgt = wl.getAttribute("data-vault-path") || "";
    if (!tgt) return;
    wl.classList.add("jv-wl-busy");
    // Nhanh .catch KHONG phai trang tri: lop 'jv-wl-busy' chan moi cu bam sau do, nen mot loi
    // duy nhat khong ai bat la link do CHET HAN cho toi khi ve lai ca bai - dung trieu chung
    // "thi thoang bam khong mo duoc file tiep theo". Go lop bận ra roi bao truot nhu khi khong
    // tim thay: bam lai duoc, va thay ro la vua that bai.
    wkResolve(tgt).then(function (hit) {
      wl.classList.remove("jv-wl-busy");
      if (!hit) {
        wl.classList.add("jv-wl-miss");
        wl.title = "Không tìm thấy note này trong vault";
        setTimeout(function () { wl.classList.remove("jv-wl-miss"); }, 1500);
        return;
      }
      moFileVault(hit.rel);
    }).catch(function () {
      wl.classList.remove("jv-wl-busy");
      wl.classList.add("jv-wl-miss");
      wl.title = "Không mở được note này - thử lại";
      setTimeout(function () { wl.classList.remove("jv-wl-miss"); }, 1500);
    });
  }

  // Mo mot FILE cua vault tu link (trong chat hoac trong ban render cua trinh sua).
  //
  // Uu tien TRINH SUA DINH - window.JavisOpenNote, wrapper SAN CO cua console.js (cung cai
  // click node do thi dung): nhan MOT chuoi path tuong doi GOC BRAIN, tu ghep tien to tran +
  // suy ten/duoi, tu so cay toi dung nhanh. O trang Tro chuyen no CHIEM CHO khung chat
  // (#chatPageEdit tu 0.15.2), o man chinh no noi len tren visual nao - cho do rong nen de la
  // hop ly. KHONG duoc goi khac chu ky nay.
  //
  // Popup .jvfe-modal chi con la duong lui, dung hai truong hop: man HEP (duoi 860px thi
  // khong con cho cho khung dinh, ma popup von co @media rieng cho man hep), va luc console.js
  // chua kip nap. Loai file khong sua duoc (pdf, docx, zip...) khong can nhanh rieng: openNote
  // da co san _neRenderDownload hien the file kem nut Mo tab moi / Tai ve.
  // Node dang nam trong BAN RENDER cua mot trinh sua (editor cay, khung sua file bung giua
  // man hinh, hay o ghi chu)? Dung de phan biet "chat chi doc" voi "dang mo file ra sua".
  function trongTrinhSua(node) {
    return !!(node && node.closest &&
              node.closest('[contenteditable="true"], .jvfe-modal, .note-editor'));
  }

  function moFileVault(rel) {
    // Duong CHINH: console.js quyet dinh (file sua duoc -> trinh sua, con lai -> trang Tep tin).
    // Gom ve mot cho vi deep-link `#open=` cung goi dung ham do; hai ban sao luat se lech nhau,
    // ma trieu chung cua lech la "cung mot file luc thi sua duoc luc thi ve thu muc".
    if (typeof window.JavisOpenVaultPath === "function") { window.JavisOpenVaultPath(rel); return; }
    // Duoi day la duong lui cho ban console.js cu chua co ham do.
    var hep = false;
    try { hep = window.matchMedia("(max-width: 860px)").matches; } catch (e) {}
    if (!hep && typeof window.JavisOpenNote === "function") { window.JavisOpenNote(rel); return; }
    if (typeof window.JavisEditFile === "function") { window.JavisEditFile(rel); return; }
    if (typeof window.JavisOpenFiles === "function") window.JavisOpenFiles(rel);
  }

  // ---------------------------------------------------------------- lightbox xem anh
  // Bam anh trong chat -> mo lop xem phong to (kieu ChatGPT): anh vua man, co nut Tai ve,
  // Mo tab moi, Dong; bam nen den hoac Esc de dong; bam vao anh de doi qua lai giua "vua man"
  // va "co that" (1:1) roi keo xem chi tiet.
  var _lb = null, _lbUrl = "", _lbTen = "";

  function _lbTaiVe() {
    if (!_lbUrl) return;
    var a = document.createElement("a");
    // /files/raw?...&dl=1 la duong SERVER ep tai kem dung ten file (ke ca ten tieng Viet).
    // Anh ngoai vault khong co duong do -> dua thuoc tinh download, cung lam gi hon duoc.
    a.href = /\/(files|upload)\/raw\?/.test(_lbUrl) ? _lbUrl + "&dl=1" : _lbUrl;
    a.download = _lbTen || "";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  function dongLightbox() {
    if (!_lb) return;
    _lb.remove(); _lb = null; _lbUrl = ""; _lbTen = "";
    document.body.classList.remove("jv-lb-open");
  }
  function moLightbox(url, ten) {
    dongLightbox();
    _lbUrl = url; _lbTen = ten || "";
    _lb = document.createElement("div");
    _lb.className = "jv-lb";
    _lb.innerHTML =
      '<div class="jv-lb-bar">' +
        '<span class="jv-lb-ten"></span>' +
        '<span class="jv-lb-nut">' +
          '<button type="button" data-lb="tai" title="Tải ảnh về">' + ic("download") + " Tải về</button>" +
          '<button type="button" data-lb="tab" title="Mở ảnh ở tab mới">' + ic("external-link") + "</button>" +
          '<button type="button" data-lb="dong" title="Đóng (Esc)">' + ic("x") + "</button>" +
        "</span>" +
      "</div>" +
      '<div class="jv-lb-khung"><img class="jv-lb-img" alt=""></div>';
    // Ten file dat bang textContent, KHONG noi vao innerHTML: ten do nguoi dung dat, noi thang
    // la mo duong cho HTML la lot vao trang.
    _lb.querySelector(".jv-lb-ten").textContent = _lbTen;
    var img = _lb.querySelector(".jv-lb-img");
    img.src = url;
    img.alt = _lbTen;
    img.addEventListener("click", function (ev) {
      ev.stopPropagation();
      _lb.classList.toggle("that");             // vua man <-> co that (1:1), keo xem chi tiet
    });
    _lb.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("[data-lb]") : null;
      if (b) {
        ev.stopPropagation();
        var act = b.getAttribute("data-lb");
        if (act === "tai") return _lbTaiVe();
        if (act === "tab") return window.open(url, "_blank", "noopener");
        return dongLightbox();
      }
      if (!ev.target.closest(".jv-lb-bar")) dongLightbox();   // bam nen den -> dong
    });
    document.body.appendChild(_lb);
    document.body.classList.add("jv-lb-open");
  }
  // ---------------------------------------------------------------- wiring (chi khi co DOM)
  if (typeof document !== "undefined") {
    // Gan o TRONG khoi nay: file con duoc require duoi node de test ham thuan, ma duoi node
    // khong co `window` - gan o ngoai la module nem ngay luc nap.
    window.JavisLightbox = { open: moLightbox, close: dongLightbox };
    document.addEventListener("keydown", function (e) {
      if (_lb && e.key === "Escape") { e.preventDefault(); dongLightbox(); }
    });
    // Bam anh trong chat -> lightbox. Dang ky o pha CAPTURE va dat TRUOC cac handler khac de
    // an chac khong bi handler link vault (jv-floc/jv-fdownload) cuop mat.
    document.addEventListener("click", function (e) {
      var a = e.target.closest ? e.target.closest("a.jv-img-link") : null;
      if (!a) return;
      // Chua/Ctrl/giua chuot -> de trinh duyet mo tab moi nhu moi link binh thuong.
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button > 0) return;
      // Dang soan trong editor thi de nguoi dung bam vao anh ma sua, dung bung lightbox.
      if (e.target.closest('[contenteditable="true"], .jvfe-modal, .note-editor')) return;
      e.preventDefault();
      e.stopPropagation();
      var img = a.querySelector("img");
      var vp = a.getAttribute("data-vault-path") || "";
      // `data-img-ten` la ten do NGUOI GUI dat, dung cho anh khong nam trong vault (vd file vua
      // dan vao khung chat, phuc vu qua /upload/raw?name=...). Suy ten tu href o day ra chu
      // "raw" - dung ten endpoint lam ten anh, vua sai vua kho hieu.
      var ten = a.getAttribute("data-img-ten") || "";
      if (!ten) ten = vp ? vp.split("/").pop() : (a.getAttribute("href") || "").split("/").pop().split("?")[0];
      moLightbox(a.getAttribute("href") || (img && img.src) || "", ten);
    }, true);
    // Checkbox task "- [ ]" (cam hung obsidian-tasks): trong editor (.ne-wys) tick duoc va tu luu
    // (editor nghe event jv-task-toggle); trong chat/khung chi-doc thi khoa lai (khong co file de ghi).
    // Task trong ket qua dataview co handler rieng (dataview.js) ghi thang vao file goc.
    document.addEventListener("click", function (e) {
      var cb = e.target;
      if (!cb || cb.tagName !== "INPUT" || cb.type !== "checkbox" ||
          !(cb.classList && cb.classList.contains("md-cb"))) return;
      if (cb.closest(".jv-dataview")) return;                     // dataview.js lo
      var wys = cb.closest(".ne-wys");
      if (!wys) { e.preventDefault(); return; }                   // chat / preview: chi doc
      // dong bo ATTRIBUTE theo property de innerHTML -> turndown ra dung [x]/[ ]
      if (cb.checked) cb.setAttribute("checked", ""); else cb.removeAttribute("checked");
      var li = cb.closest("li"); if (li) li.classList.toggle("task-done", cb.checked);
      try { wys.dispatchEvent(new CustomEvent("jv-task-toggle", { bubbles: true })); } catch (err) {}
    });
    document.addEventListener("click", function (e) {
      // Wikilink [[..]]: bam la DI CHUYEN toi note dich - chay CA trong ban render dang sua (ne-wys/.jvfe-modal),
      // vi y nghia cua wikilink la dieu huong; muon sua chu cua link thi dung che do Nguon.
      var wl = e.target.closest ? e.target.closest("a.jv-wikilink") : null;
      if (wl) {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button > 0) return;   // de deep-link #open=.. mo tab moi
        e.preventDefault();
        openWikilink(wl);
        return;
      }
      // Link file/thu muc vault: bam thuong -> mo file. Ctrl/Cmd/Shift/giua chuot -> de trinh
      // duyet dung deep-link href (#open=..) mo tab moi (chat van con o tab cu).
      //
      // Nhanh nay nam TRUOC hang rao contenteditable ben duoi, dung cho voi wikilink. Vi sao:
      // ban render cua trinh sua LA contenteditable, nen truoc day MOI link markdown trong
      // mot file .md deu roi vao hang rao do va bam khong di dau ca - trong khi [[wikilink]]
      // ngay canh no thi di duoc, du hai cai nhin y het nhau. Luat da chon tu truoc cho
      // wikilink: trong ban render, link la de DI, muon sua chu cua link thi bat che do Nguon.
      var loc = e.target.closest ? e.target.closest("a.jv-floc") : null;
      if (loc && loc.getAttribute("data-vault-path") != null) {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button > 0) return;
        var vp = loc.getAttribute("data-vault-path") || "";
        var isImg = !!(loc.querySelector && loc.querySelector("img"));   // anh inline -> giu hanh vi cu
        // Anh trong ban render phai keo tha va xoa duoc nhu mot ky tu -> khong cuop cu bam.
        if (!(isImg && trongTrinhSua(e.target))) {
          e.preventDefault();
          var trimmed = vp.replace(/\/+$/, "");
          var base = trimmed.split("/").pop();
          var isDir = /\/$/.test(vp) || base === "" || base.indexOf(".") < 0;   // co duoi -> FILE (nhu openFilesAt)
          // FILE co duoi -> mo trong trinh sua; THU MUC / anh inline -> mo trang Tep tin dung vi tri.
          if (!isImg && !isDir) { moFileVault(trimmed); return; }
          if (typeof window.JavisOpenFiles === "function") window.JavisOpenFiles(vp);
          else window.open(loc.href, "_blank");   // du phong: mo tab moi neu console.js chua san sang
          return;
        }
      }
      // Link NGOAI trong ban render: trong contenteditable trinh duyet khong tu mo tab moi,
      // no chi dat con tro - nen bam vao mot link http trong file .md xem nhu khong co gi xay
      // ra. Tu mo ho. (Ngoai ban render thi the <a target="_blank"> lo roi, khong dung vao.)
      var ext = e.target.closest ? e.target.closest("a[href]") : null;
      if (ext && trongTrinhSua(e.target) && /^(https?:|mailto:)/i.test(ext.getAttribute("href") || "")) {
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button > 0) return;
        e.preventDefault();
        window.open(ext.getAttribute("href"), "_blank", "noopener");
        return;
      }
      // The artifact (mermaid/svg/html, hay khoi code dai): bam = MO PANEL XEM. Panel chi
      // de XEM (preview + code + copy), khong phai mot editor long nhau, nen nhanh nay phai
      // dung TRUOC chot trongTrinhSua ben duoi. Truoc 0.47.7 no dung SAU, nen trong trinh
      // sua .md the nay chet han: bam khong ra gi ma noi dung thi da bi thu vao the -
      // "khong mo duoc cung khong xem duoc" (chu repo bao 27/08).
      var card = e.target.closest ? e.target.closest(".jv-art") : null;
      if (card && card.dataset.art) { e.preventDefault(); openArtifact(card.dataset.art); return; }
      // Dang SOAN trong editor (contenteditable/.ne-wys) hoac trong khung sua file -> khong mo gi ca,
      // de nguoi dung bam anh ma sua binh thuong (tranh bung editor long nhau).
      if (trongTrinhSua(e.target)) return;
    });
    document.addEventListener("keydown", function (e) {
      if ((e.key === "Enter" || e.key === " ") && document.activeElement &&
          document.activeElement.classList && document.activeElement.classList.contains("jv-art")) {
        e.preventDefault(); openArtifact(document.activeElement.dataset.art);
      }
    });
    // Esc dong panel TRUOC (capture) de khong thu nho luon khung chat phong to
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && panel && panel.classList.contains("open")) {
        e.stopPropagation(); closePanel();
      }
    }, true);
  }

  if (typeof window !== "undefined") {
    window.mdToHtml = mdToHtml;
    // Bo to mau chung: code-hl.js goi lai cho cac ngon ngu kieu C (js/py/sh...) de mot luat
    // chi nam o mot cho. Markup/CSS/JSON thi code-hl tu doc lay (xem chu thich ben do).
    window.JavisHighlight = highlight;
    window.jvImgGone = imgGone;   // goi tu thuoc tinh onerror noi tuyen cua the <img>
    // get(id): cho turndown (console.js) tra artifact card ve lai dung fence ``` khi luu note WYSIWYG
    window.JavisArtifacts = { open: openArtifact, close: closePanel,
      get: function (id) { return registry[id] || null; } };
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { mdToHtml: mdToHtml, highlight: highlight, wkResolve: wkResolve,
      appFilePath: appFilePath, isDownloadFile: isDownloadFile };
  }
})();
