/* Test autolink URL tran trong mdToHtml. Chay tay / CI:
       node dashboard/test_chat_render.js
   KHONG can trinh duyet: chi test ham thuan mdToHtml(). */
const { mdToHtml, appFilePath } = require("../../dashboard/chat-render.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
function has(h, s) { return h.indexOf(s) !== -1; }

// ---- 1. URL tran -> link mo tab moi ----
let h = mdToHtml("Xem https://example.com nhe");
check("url tran: thanh the a", has(h, '<a href="https://example.com"'));
check("url tran: mo tab moi", has(h, 'target="_blank"') && has(h, 'rel="noopener"'));
check("url tran: chu link dung URL", has(h, ">https://example.com</a>"));

// ---- 2. Dau cau duoi URL nam NGOAI link ----
h = mdToHtml("Trang chu: https://example.com.");
check("dau cau: href khong dinh dau cham", has(h, '<a href="https://example.com"'));
check("dau cau: dau cham o ngoai the a", has(h, "</a>."));

// ---- 3. Link markdown van chay, KHONG bi linkify 2 lan ----
h = mdToHtml("[Google](https://google.com)");
check("md link: giu chu hien thi", has(h, ">Google</a>"));
check("md link: khong lo URL tho ra ngoai", !has(h, ">https://google.com</a>"));
check("md link: chi 1 the a", (h.match(/<a /g) || []).length === 1);

// ---- 4. URL trong inline code KHONG bi linkify ----
h = mdToHtml("Chay `curl https://api.example.com` di");
check("inline code: URL nam trong <code>", has(h, "<code>") && has(h, "https://api.example.com"));
check("inline code: KHONG tao the a", !has(h, "<a "));

// ---- 5. URL trong code fence KHONG bi linkify ----
h = mdToHtml("```\nfetch('https://api.example.com')\n```");
check("code fence: KHONG tao the a", !has(h, "<a "));

// ---- 6. Hai URL trong 1 doan -> ca hai thanh link ----
h = mdToHtml("A https://one.com va https://two.com");
check("hai url: ca hai thanh link", (h.match(/<a /g) || []).length === 2);
check("hai url: co one.com", has(h, 'href="https://one.com"'));
check("hai url: co two.com", has(h, 'href="https://two.com"'));

// ---- 7. http (khong s) cung nhan ----
h = mdToHtml("Cu http://localhost:8000 nhe");
check("http: thanh link", has(h, '<a href="http://localhost:8000"'));

// ---- 8. Khong co URL -> khong sinh the a ----
h = mdToHtml("Chi la van ban binh thuong.");
check("khong url: khong co the a", !has(h, "<a "));

// ---- 9. Link file vault CO KHOANG TRANG + NGOAC (nhu Javis gui that) ----
h = mdToHtml("[Cach Toi Lam Viec.md](06 - Sources/Cach Toi Lam Viec (Tu Duy Nguoc).md)");
check("path co space+ngoac: bat DUNG ca duong dan",
  has(h, 'data-vault-path="06 - Sources/Cach Toi Lam Viec (Tu Duy Nguoc).md"'));
check("path co space+ngoac: khong ro duoi .md) ra text", !has(h, ".md)</p>") && !has(h, ">.md)"));

// ---- 10. Path co khoang trang (khong ngoac) ----
h = mdToHtml("[ghi chu](06 - Sources/ghi chu.md)");
check("path co space: bat DUNG ca duong dan", has(h, 'data-vault-path="06 - Sources/ghi chu.md"'));

// ---- 11. Title markdown ("...") van bi cat khoi href URL ngoai ----
h = mdToHtml('[Trang](https://x.com "Tieu de")');
check("title md: href sach khong dinh title", has(h, 'href="https://x.com"'));
check("title md: khong lot chu Tieu de vao href", !has(h, 'Tieu de"'));

// ---- 12. Hai link vault tren 1 dong khong nuot lan nhau ----
h = mdToHtml("[a](thu muc/a.md) va [b](thu muc/b.md)");
check("hai link vault: dung 2 link", (h.match(/jv-floc/g) || []).length === 2);
check("hai link vault: path a dung", has(h, 'data-vault-path="thu muc/a.md"'));
check("hai link vault: path b dung", has(h, 'data-vault-path="thu muc/b.md"'));

// ---- 13. Wikilink [[..]] -> link dieu huong ----
h = mdToHtml("Da cap nhat [[business/Danh Muc Du An - Minh Quy]] xong");
check("wikilink: co the a jv-wikilink", has(h, "jv-wikilink"));
check("wikilink: data-vault-path giu target goc", has(h, 'data-vault-path="business/Danh Muc Du An - Minh Quy"'));
check("wikilink: chu hien thi = target", has(h, ">business/Danh Muc Du An - Minh Quy</a>"));

// ---- 14. Wikilink co alias [[path|chu]] ----
h = mdToHtml("Xem [[notes/abc|Ten dep]] nhe");
check("wikilink alias: chu hien thi la alias", has(h, ">Ten dep</a>"));
check("wikilink alias: giu alias cho round-trip", has(h, 'data-wiki-alias="Ten dep"'));
check("wikilink alias: path van dung", has(h, 'data-vault-path="notes/abc"'));

// ---- 15. Anh ![[..]] KHONG bi bat nham thanh wikilink ----
h = mdToHtml("![[attachments/x.png]]");
check("anh vault: van la img", has(h, "<img"));
check("anh vault: khong sinh jv-wikilink", !has(h, "jv-wikilink"));

// ---- 16. [[..]] nam TRONG inline code giu nguyen chu ----
h = mdToHtml("dung cu phap `[[ten note]]` de link");
check("wikilink trong code: khong thanh link", !has(h, "jv-wikilink"));

// ---- 17. Inline code chua duong dan file vault -> bam mo duoc ----
h = mdToHtml("Da tao `Javis/loops/ghi-ho-so.md` cho anh");
check("code path: co link jv-floc", has(h, "jv-fcode") && has(h, 'data-vault-path="Javis/loops/ghi-ho-so.md"'));
check("code path: van hien dang code", has(h, "<code>Javis/loops/ghi-ho-so.md</code>"));

// ---- 18. Inline code thuong / lenh KHONG thanh link ----
h = mdToHtml("Dat `enabled: false` trong frontmatter");
check("code frontmatter: khong link", !has(h, "jv-floc"));
h = mdToHtml("Goi `console.log` de debug");
check("code khong slash khong .md: khong link", !has(h, "jv-floc"));
h = mdToHtml("Chay `curl https://api.example.com/x.md` di");
check("code lenh co URL: khong link", !has(h, "jv-floc"));

// ---- 19. File .md tran (khong thu muc) trong code van bam duoc ----
h = mdToHtml("Sua `MEMORY.md` roi bao em");
check("code .md tran: co link", has(h, 'data-vault-path="MEMORY.md"'));

// ---- 20. Path co khoang trang + tieng Viet trong code ----
h = mdToHtml("Ho so o `07 - Wiki/_entities/Chi Nga - Khach Coaching.md` nhe");
check("code path co space: bat dung ca duong dan",
  has(h, 'data-vault-path="07 - Wiki/_entities/Chi Nga - Khach Coaching.md"'));

// ---- 21. Checkbox task "- [ ]": tick duoc (khong disabled), giu trang thai checked ----
h = mdToHtml("- [ ] viec chua xong\n- [x] viec da xong");
check("task: input md-cb khong disabled", has(h, 'class="md-cb"') && !has(h, "disabled"));
check("task: giu checked cho [x]", has(h, "checked"));

// ---- 22. Fence ```dataview -> khoi jv-dataview mang truy van (dataview.js tu chay) ----
h = mdToHtml('```dataview\nTASK FROM "05 - Viec"\n```');
check("dataview: co khoi jv-dataview", has(h, 'class="jv-dataview"'));
check("dataview: truy van nam trong data-dv-q",
  has(h, encodeURIComponent('TASK FROM "05 - Viec"')));
h = mdToHtml("```dataviewjs\ndv.pages()\n```");
check("dataviewjs: cung vao khoi dataview (bao chua ho tro khi chay)", has(h, "jv-dataview"));
h = mdToHtml("```tasks\nnot done\ndue before today\n```");
check("tasks: fence obsidian-tasks cung thanh khoi song", has(h, 'data-dv-lang="tasks"'));

// ---- 23. Anh het han: the <img> phai co onerror de doi thanh o xam ----
h = mdToHtml("![so hang](attachments/hang.png)");
check("anh: co onerror goi jvImgGone", has(h, 'onerror="jvImgGone(this)"'));
check("anh: van giu class chat-img", has(h, 'class="chat-img"'));
h = mdToHtml("![ngoai](https://example.com/x.png)");
check("anh ngoai: cung co onerror", has(h, 'onerror="jvImgGone(this)"'));

// ---- 24. Link /files/raw toi .md van la file brain -> mo editor noi bo, khong tab moi ----
h = mdToHtml("[ghi chu](/files/raw?brain=brain&path=06%20-%20Sources%2Fghi-chu.md)");
check("raw .md: thanh link vault", has(h, 'class="jv-floc"'));
check("raw .md: giai ma dung path", has(h, 'data-vault-path="06 - Sources/ghi-chu.md"'));
check("raw .md: khong target blank", !has(h, 'target="_blank"'));

// ---- 25. Link export sai kieu /brains/<brain>/... duoc tu sua ve endpoint file that ----
global.currentBrainPath = function () { return "D:\\Vaults\\My Bullet Journal"; };
global.window = {
  location: {
    origin: "https://javis.example.com",
    href: "https://javis.example.com/chat",
  },
};
const brokenExport = "/brains/My%20Bullet%20Journal/exports/javis-tiec-tra-ai-warrior-plus.html";
check("export /brains: giai ma dung path trong brain",
  appFilePath(brokenExport) === "exports/javis-tiec-tra-ai-warrior-plus.html");
h = mdToHtml("[Tải export](" + brokenExport + ")");
check("export /brains: render thanh link tai qua /files/raw",
  has(h, 'class="jv-fdownload"') && has(h, "/files/raw?brain=") && has(h, "dl=1"));
h = mdToHtml("[Tải export](https://javis.example.com" + brokenExport + ")");
check("export URL day du cung domain: cung duoc sua",
  has(h, 'class="jv-fdownload"') && has(h, "/files/raw?brain=") && has(h, "dl=1"));

// ---- 26. Editor nhan ca path goc brain va path da kem home cua Quan ly file ----
const { ceilPath } = require("../../dashboard/file-editor.js");
check("editor: path goc brain duoc ghep home",
  ceilPath("brains/My Brain", "06 - Sources/ghi-chu.md") === "brains/My Brain/06 - Sources/ghi-chu.md");
check("editor: path Quan ly file khong bi ghep home hai lan",
  ceilPath("brains/My Brain", "brains/My Brain/06 - Sources/ghi-chu.md") === "brains/My Brain/06 - Sources/ghi-chu.md");

// ---- 27. File thanh pham/media trong brain -> tai ve; URL ngoai van mo tab moi ----
h = mdToHtml("[trang web](attachments/landing.html)");
check("html noi bo: thanh link tai ve", has(h, 'class="jv-fdownload"') && has(h, "download"));
check("html noi bo: dung endpoint dl=1", has(h, "dl=1") && !has(h, 'target="_blank"'));
// 0.9.285 doi hanh vi CO Y: anh bam vao la XEM PHONG TO (lightbox), khong con tai file ve.
// Tai ve chuyen vao trong lightbox. File khong phai anh (html, pdf...) van tai ve nhu cu -
// hai dong tren van kiem dieu do. Chi tiet o tests/js/test_lightbox_anh.js.
h = mdToHtml("![anh ket qua](attachments/post.png)");
check("anh noi bo: bam la XEM phong to, khong tai ve",
  has(h, 'class="jv-img-link"') && !has(h, "dl=1") && !has(h, 'class="jv-fdownload"'));
h = mdToHtml("[video](attachments/demo.mp4)");
check("video noi bo: bam la tai ve", has(h, 'class="jv-fdownload"') && has(h, "download"));
h = mdToHtml("[note](notes/ke-hoach.md)");
check("note md: van mo editor noi bo", has(h, 'class="jv-floc"') && !has(h, "jv-fdownload"));
h = mdToHtml("[website](https://example.com/demo.html)");
check("URL ngoai duoi html: van mo tab moi", has(h, 'target="_blank"') && !has(h, "jv-fdownload"));

if (fails.length) {
  console.log("\nFAIL - " + fails.length + " test: " + fails.join(", "));
  process.exit(1);
}
console.log("\nOK - test_chat_render: tat ca pass");
