/* Tab / Shift+Tab thut le trong trinh sua .md, va go "- " / "1. " ra danh sach that.

       node tests/js/test_tab_thut_le.js

   Chu repo yeu cau (2026-10-20): Tab de thut dong vao trong; go gach dau dong, task, so thu tu
   roi Enter thi tu co dau muc moi (phan Enter khoa o test_enter_tiep_task.js).

   Hanh vi DOM da do bang Edge (Chromium) that qua DevTools, phim that: 26 phep thu gom Enter
   noi task/bullet/so, thoat task rong, Tab/Shift+Tab long muc con, go "- " / "3. " ra danh
   sach, va vong Sua -> markdown bang Turndown + GFM. CI chi co node nen test nay khoa phan
   logic thuan cong nhung cho de troi trong ma nguon.

   Nhung cho hong AM THAM phai canh:
     1. Muc con phai nam TRONG li cha. execCommand("indent") cua Chromium dat <ul> con ngang
        hang <li>, Turndown doc kieu do khong ra thut le: luu xong muc con rot ve cap ngoai.
     2. Tab o nguon tho phai thut 4 cach, dung khuon Turndown ghi muc con. Lech khuon thi
        chuyen qua lai giua Sua va Nguon la cap long nhay lung tung.
     3. Go "- " trong ban render ma khong doi thanh danh sach thi Turndown luu ra "\- chu",
        va Enter khong noi duoc gi ca (dung loi trong daily log 2026-10-20 cua chu repo). */
const fs = require("fs");
const path = require("path");
const EC = require("../../dashboard/editor-cmds.js");
const SRC = fs.readFileSync(path.join(__dirname, "../../dashboard/editor-cmds.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

// Ap mo ta thay doi vao chuoi; "[" "]" danh dau doan dang chon, "|" la caret khi khong chon.
function ap(value, s, e, lui) {
  const ed = EC.thutLe(value, s, e, lui);
  if (!ed) return null;
  const v = value.slice(0, ed.s) + ed.text + value.slice(ed.e);
  if (ed.selS === ed.selE) return v.slice(0, ed.selS) + "|" + v.slice(ed.selS);
  return v.slice(0, ed.selS) + "[" + v.slice(ed.selS, ed.selE) + "]" + v.slice(ed.selE);
}

// ============================================================
// 1. Tab o nguon tho
// ============================================================
check("Tab tren dong bullet -> thut ca dong 4 cach, caret di theo",
      ap("- a\n- b", 7, 7, false) === "- a\n    - b|");
check("Tab tren dong task -> thut ca dong", ap("- [ ] viec", 10, 10, false) === "    - [ ] viec|");
check("Tab tren dong so -> thut ca dong", ap("1. a\n2. b", 9, 9, false) === "1. a\n    2. b|");
check("Shift+Tab -> lui 4 cach", ap("    - b", 7, 7, true) === "- b|");
check("Shift+Tab chi lui toi da 4 cach", ap("        - b", 11, 11, true) === "    - b|");
check("Shift+Tab lui duoc dau tab that", ap("\t- b", 4, 4, true) === "- b|");
check("Shift+Tab tren dong khong thut thi khong lam gi", EC.thutLe("- b", 3, 3, true) === null);
check("CANARY: Shift+Tab khong keo caret len dong tren",
      ap("- a\n  - b", 6, 6, true) === "- a\n|- b");

check("Tab tren dong chu thuong -> chen 4 cach tai caret", ap("abc", 1, 1, false) === "a    |bc");
check("Tab tren dong trong -> chen 4 cach", ap("", 0, 0, false) === "    |");

check("chon nhieu dong -> thut tat ca, giu vung chon",
      ap("- a\n- b\nc", 0, 7, false) === "[    - a\n    - b]\nc");
check("chon nhieu dong -> Shift+Tab lui tat ca",
      ap("    - a\n    - b", 0, 15, true) === "[- a\n- b]");
check("CANARY: chon toi dau dong sau thi KHONG thut dong do",
      ap("- a\n- b\n- c", 0, 4, false) === "[    - a\n]- b\n- c");
check("vi tri vo nghia thi tra null",
      EC.thutLe("abc", 5, 5, false) === null && EC.thutLe("abc", 2, 1, false) === null &&
      EC.thutLe("abc", null, null, false) === null);

// Muc vua thut phai doc lai dung la muc con, de Enter tiep theo noi ra muc con cung cap
const sau = "- a\n    - b";
const ed = EC.enterDanhSach(sau, sau.length);
check("Enter sau khi Tab noi ra muc con cung cap",
      ed && sau.slice(0, ed.s) + ed.text === "- a\n    - b\n    - ");

// ============================================================
// 2. Go dau muc o dau doan trong ban render
// ============================================================
const G = EC.dauMucGo;
check("'- ' -> bullet", G("- ").loai === "ul");
check("'* ' va '+ ' -> bullet", G("* ").loai === "ul" && G("+ ").loai === "ul");
check("'1. ' -> danh sach so tu 1", G("1. ").loai === "ol" && G("1. ").batDau === 1);
check("'3) ' -> danh sach so tu 3", G("3) ").batDau === 3);
check("nbsp cua contenteditable van khop", G("- ").loai === "ul" && G("2. ").batDau === 2);
check("CANARY: chu dang go do khong bi doi", G("- viec") === null && G("ab- ") === null);
check("CANARY: '-' chua co dau cach thi chua doi", G("-") === null && G("1.") === null);
check("chu thuong khong phai dau muc", G("") === null && G("x ") === null && G("1 ") === null);

// ============================================================
// 3. Phan DOM (doc ma nguon)
// ============================================================
const iT = SRC.indexOf("Enter noi dong danh sach / task");
const H = SRC.slice(iT);
check("Tab co cho nghe phim", /e\.key !== "Tab"/.test(H));
check("CANARY: Ctrl+Tab / Alt+Tab van la cua trinh duyet va he dieu hanh",
      /if \(e\.ctrlKey \|\| e\.metaKey \|\| e\.altKey \|\| nhuongPhim\(e\)\) return;/.test(H));
check("Tab nhuong bo go tieng Viet va menu dang mo",
      /function nhuongPhim\(e\)/.test(H) && /e\.isComposing \|\| e\.keyCode === 229/.test(H) &&
      /pop \|\| document\.querySelector\("\.ts-pop"\)/.test(H));
check("CANARY: muc con dat TRONG li cha, khong dung execCommand indent",
      /tren\.appendChild\(con\)/.test(H) && !/execCommand\("indent"\)/.test(SRC) && !/execCommand\("outdent"\)/.test(SRC));
check("Shift+Tab dua cac muc dung sau xuong lam con, giu thu tu",
      /while \(li\.nextSibling\) con\.appendChild\(li\.nextSibling\)/.test(H));
check("doi DOM bang tay thi tu bao input de danh dau da sua", /function baoDaSua\(wys\)/.test(H) &&
      /baoDaSua\(ctx\.wys\)/.test(H));
check("go dau muc chi xet o doan thuong, khong o li/code/trich dan",
      /el\.closest\("li,pre,code,blockquote"\)/.test(H));
check("danh sach so go tu so khac 1 giu dung so bat dau", /setAttribute\("start"/.test(H));
check("THUT dung 4 cach", /var THUT = " {4}";/.test(SRC));
check("KHONG dung ky tu em dash", !SRC.includes("—"));

console.log(fails.length ? "\nFAIL: " + fails.length : "\nTat ca deu xanh");
process.exit(fails.length ? 1 : 0);
