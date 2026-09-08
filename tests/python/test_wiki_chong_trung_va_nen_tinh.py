"""Hai lỗi người dùng báo 06/09: wiki đẻ trùng trang, và app load chậm sau cập nhật.

    python tests/run.py wiki_chong_trung

Hai vấn đề độc lập hoàn toàn, gộp một file test vì cùng một đợt vá.

=== (A) WIKI ĐẺ TRÙNG ===

Chống trùng có ba tầng, và tầng bắt được trùng KHÁI NIỆM là do MODEL quyết (nó đọc danh mục
rồi khai `same_as`). Hai tầng Python chỉ là lưới cuối. Cả ba đều thủng theo cách riêng:

1. Model bị bịt mắt. `_read_index` đọc index.md rồi cắt `[:6000]`, trong khi `_merge_wiki_index`
   NỐI dòng mới xuống CUỐI. Nên thứ bị cắt là các trang MỚI NHẤT - đúng nhóm dễ bị tạo lại
   nhất. Mỗi dòng khoảng 97 ký tự, brain 203 note chỉ lọt ~30% danh mục.
2. Model dedup ĐÚNG nhưng code vứt tín hiệu. `(wiki_dir / f"{same}.md").exists()` là ghép
   chuỗi thô: lệch dấu, lệch hoa thường, hoặc trang nằm trong thư mục con là trả False, rồi
   code chạy thẳng xuống ghi trang mới. Im lặng hoàn toàn.
3. Lưới cuối mù thư mục con. `_wiki_dupe` dùng `glob("*.md")` không đệ quy, trong khi
   `_wiki_scan` cùng file đã dùng `rglob`, và vault thì chủ động dạy "tạo subfolder khi một
   chủ đề đủ dày".

=== (B) LOAD CHẬM ===

Đo thật: 42 file tĩnh, 1.631 KB, KHÔNG nén. Cộng với việc `root()` đóng dấu `?v=<phiên bản>`
lên mọi file, mỗi lần bump VERSION là 42 URL đổi một lượt, cache `immutable` trượt sạch,
trình duyệt kéo lại trọn 1,6 MB. Đó là câu "update xong vào chậm".

CÁI BẪY khi vá, và là lý do file test này tồn tại: bật `GZipMiddleware` toàn cục thì
Starlette NUỐT TRỌN response streaming. Đo trên SSE 5 chunk cách nhau 0,3 giây:
    không nén: 0,01s / 0,31s / 0,61s / 0,91s / 1,21s
    có nén   : CẢ NĂM cùng về ở 1,50s
Javis có 4 endpoint text/event-stream. Bật nén toàn cục là người dùng gõ câu hỏi rồi nhìn
màn hình trống tới khi trả lời xong - đổi lỗi chậm lấy lỗi nặng hơn hẳn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-wikidup-")
os.environ.setdefault("JAVIS_STATE_DIR", _TMP)

import learn  # noqa: E402

fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them)[:300] + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        fails.append(ten)


BRAIN = str(Path(_TMP) / "brain")
WIKI = Path(BRAIN) / "Wiki"
WIKI.mkdir(parents=True, exist_ok=True)


def note(rel, than="noi dung", aliases=None):
    f = WIKI / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    fm = "---\ntype: wiki\n"
    if aliases:
        fm += "aliases: [" + ", ".join(aliases) + "]\n"
    fm += "---\n"
    f.write_text(fm + than + "\n", encoding="utf-8")
    return f


deps = learn.LearnDeps(
    build_system_prompt=lambda b: "SYS",
    brain_root=lambda b: b,
    brain_memory_dir=lambda b: Path(b) / "Memory",
    resolve_subfolder=lambda root, pat, default: str(Path(root) / "Wiki"),
    aux_model=lambda: None,
    atomic_write_text=lambda p, t: Path(p).write_text(t, encoding="utf-8"),
    sessions_store=None,
    state_dir=Path(_TMP),
    readonly_tools=["Read", "Glob", "Grep"],
)
feat = learn.LearnFeature(deps)

# ============================================================
# 1. Mục lục wiki: thấy thư mục con, thấy aliases
# ============================================================
note("Phễu bán hàng 8+2.md")
note("Marketing/Value Proposition Design.md", aliases=["VPD", "Canvas giá trị"])
note("index.md")
note("log.md")
note("_open-questions.md")

ml = feat._wiki_muc_luc(WIKI)

# Đây là lỗ VÔ ĐIỀU KIỆN của bản cũ: glob("*.md") không đệ quy, mà vault thì dạy tạo subfolder.
check("thấy trang trong THƯ MỤC CON", feat._wiki_trung(ml, "Value Proposition Design") is not None)
check("thấy trang ở gốc wiki", feat._wiki_trung(ml, "Phễu bán hàng 8+2") is not None)
# aliases là bảng tra đồng nghĩa mà skill ingest-source bắt buộc ghi, trước nay không ai đọc.
check("tra được qua ALIASES viết tắt", feat._wiki_trung(ml, "VPD") is not None)
check("tra được qua ALIASES tiếng Việt", feat._wiki_trung(ml, "Canvas giá trị") is not None)
check("bỏ qua index/log/_open-questions",
      feat._wiki_trung(ml, "index") is None and feat._wiki_trung(ml, "log") is None
      and feat._wiki_trung(ml, "open-questions") is None)

# ============================================================
# 2. Khớp mềm, và RÀO SỐ HIỆU
# ============================================================
check("khớp tuyệt đối sau chuẩn hoá (bỏ dấu, thường hoá)",
      feat._wiki_trung(ml, "PHỄU BÁN HÀNG 8+2") is not None)
check("khớp MỀM với biến tấu nhẹ về dấu cách",
      feat._wiki_trung(ml, "Phễu bán hàng 8 + 2") is not None)

# Rào số hiệu: hai tên chỉ khác con số thì KHÔNG BAO GIỜ là một. Không có rào này, khớp mềm
# sẽ nuốt đúng loại tài liệu mà người ta cần phân biệt nhất.
note("IFRS 7.md")
note("Nghị định 254.md")
ml2 = feat._wiki_muc_luc(WIKI)
check("IFRS 9 KHÔNG bị coi là trùng IFRS 7", feat._wiki_trung(ml2, "IFRS 9") is None)
check("Nghị định 255 KHÔNG bị coi là trùng Nghị định 254",
      feat._wiki_trung(ml2, "Nghị định 255") is None)
check("nhưng IFRS 7 vẫn tự khớp chính nó", feat._wiki_trung(ml2, "IFRS 7") is not None)
# Khác hẳn về nghĩa thì không được khớp, dù cùng vài chữ.
check("khái niệm khác hẳn thì không khớp", feat._wiki_trung(ml2, "Email marketing") is None)

# ============================================================
# 3. Danh mục nạp vào prompt: dựng từ HỆ THỐNG FILE, giữ được trang mới
# ============================================================
idx = feat._read_index(BRAIN)
check("danh mục có trang ở gốc", "Phễu bán hàng 8+2" in idx, idx[:200])
# Bản cũ đọc index.md nên chỉ biết trang do chính vòng học ghi; trang skill ingest-source
# hay người dùng tự tạo thì vô hình.
check("danh mục có trang trong thư mục con (bản cũ đọc index.md nên mù)",
      "Marketing/Value Proposition Design" in idx, idx[:300])
check("không liệt kê index/log/_open-questions",
      "\n- index\n" not in idx and "\n- log\n" not in idx)

# Điểm CỐT LÕI: bản cũ cắt [:6000] giữ phần ĐẦU trong khi note mới nối xuống CUỐI, nên note
# mới nhất chính là thứ bị vứt. Dựng lại nhiều note rồi kiểm note cuối cùng có mặt.
# Đủ nhiều để VƯỢT trần thật, không chỉ chạm. Tên dài như tên trang đời thật.
for i in range(1400):
    note(f"Chu de nghiep vu chi tiet so {i:04d}.md")
idx2 = feat._read_index(BRAIN)
check("vượt trần thì NÓI RA là đã lược bớt, không im lặng cắt",
      "còn" in idx2 and "không liệt kê hết" in idx2, idx2[-200:])
check(f"tôn trọng trần {learn.LearnFeature.WIKI_INDEX_MAX} ký tự",
      len(idx2) <= learn.LearnFeature.WIKI_INDEX_MAX + 200, len(idx2))
# Chỉ chứa TÊN nên cùng ngân sách chứa được nhiều hơn hẳn bản có kèm mô tả.
check("chứa được >200 tên trong ngân sách (bản cũ 6000 ký tự chỉ ~62 dòng)",
      idx2.count("\n- ") > 200, idx2.count("\n- "))

print("")

# ============================================================
# 4. (B) Nén tài sản tĩnh - CỔNG CHẶN THEO ĐƯỜNG DẪN
# ============================================================
_src_main = (SERVER / "main.py").read_text(encoding="utf-8")

check("có middleware nén cho tài sản tĩnh", "class _NenTinh" in _src_main)
# CANARY quan trọng nhất của cả file: nếu ai đó "đơn giản hoá" thành add_middleware thẳng,
# chat streaming chết câm. Chặn ngay tại đây.
# Bắt LỆNH GỌI ở đầu dòng, không bắt chuỗi trong chú thích - chính chú thích của bản vá này
# giải thích vì sao không được gọi như vậy, và nó phải được phép nhắc tới cú pháp đó.
import re as _re  # noqa: E402
check("CANARY: KHÔNG bật GZip toàn cục (sẽ nuốt trọn SSE, chết chat streaming)",
      not _re.search(r"^app\.add_middleware\(GZipMiddleware", _src_main, _re.M))
check("cổng chặn theo ĐƯỜNG DẪN /static/, không theo content-type",
      'scope.get("path", "").startswith("/static/")' in _src_main)
check("chú thích ghi lại số đo SSE để người sau không gỡ nhầm",
      "CẢ NĂM chunk cùng về" in _src_main)

# Kiểm THẬT hành vi định tuyến của middleware, không chỉ đọc chữ.
import asyncio  # noqa: E402
import main as main_mod  # noqa: E402


def _di_qua(path):
    """Trả True nếu request đi vào nhánh GZIP, False nếu đi thẳng app gốc."""
    dau = {"gzip": False, "thang": False}

    async def app_goc(scope, receive, send):
        dau["thang"] = True

    mw = main_mod._NenTinh(app_goc, minimum_size=1024)

    class _GiaGzip:
        async def __call__(self, scope, receive, send):
            dau["gzip"] = True
    mw._gzip = _GiaGzip()
    asyncio.get_event_loop().run_until_complete(
        mw({"type": "http", "path": path}, None, None))
    return dau


d = _di_qua("/static/console.js")
check("/static/* ĐI QUA nén", d["gzip"] and not d["thang"])
for p in ("/chat/stream", "/usage/bao-cao", "/ollama-local/search", "/settings", "/"):
    d = _di_qua(p)
    check(f"{p} KHÔNG đi qua nén", d["thang"] and not d["gzip"])
# WebSocket không được chạm tới, kể cả nếu đường dẫn có tiền tố lạ.
dau = {"thang": False}


async def _ws_goc(scope, receive, send):
    dau["thang"] = True


mw = main_mod._NenTinh(_ws_goc, minimum_size=1024)
asyncio.get_event_loop().run_until_complete(mw({"type": "websocket", "path": "/ws"}, None, None))
check("websocket đi thẳng, không đụng nén", dau["thang"])

# ============================================================
# 5. (B) Khoá cache theo VÂN TAY TỪNG FILE
# ============================================================
# Bump VERSION mà đổi khoá cả 42 file là bắt tải lại 1,6 MB cho một sửa đổi một dòng.
check("root() đóng dấu ?v= bằng vân tay từng file, không bằng số phiên bản chung",
      'fps.get(m.group(2)) or ver' in _src_main, "")
check("vẫn rơi về số phiên bản khi không băm được file",
      "or ver" in _src_main)
_fresh = (ROOT / "dashboard" / "freshness.js").read_text(encoding="utf-8")
# freshness.js tải lại từng file để so nội dung. Nếu nó dùng khoá KHÁC khoá trang đã dùng thì
# nó đo file trên máy chủ chứ không phải file trình duyệt đang chạy - đúng cái bẫy mà chú
# thích taiNhuTrang trong chính file đó cảnh báo.
check("freshness.js dùng CÙNG khoá vân tay với trang, không lệch sang số phiên bản",
      "m.assets[rel]" in _fresh and "var khoa" in _fresh)

# ============================================================
# 6. (B) /claude/status không được lặp vòng chờ vô hạn
# ============================================================
_src_cli = (SERVER / "claude_cli.py").read_text(encoding="utf-8")
# Nhánh except cũ trả bản nhớ cũ nhưng không dời mốc, nên claude hỏng = mỗi lượt mở trang
# Models lại đẻ tiến trình và chờ đủ timeout, lặp mãi.
check("có cache ÂM cho ca hỏi hỏng", "_AUTH_LOI" in _src_cli and "_AUTH_TTL_LOI" in _src_cli)
check("nhánh except ghi mốc lỗi", '_AUTH_LOI["ts"] = now' in _src_cli)
check("đường vẽ trang có timeout ngắn hơn nút Kiểm tra lại",
      "timeout=25 if bo_qua_cache else 8" in _src_cli)
# Vừa đăng nhập xong mà cổng nghỉ-vì-lỗi còn hiệu lực là thẻ bày trạng thái cũ thêm 30 giây,
# đúng lúc người dùng đang nhìn xem đăng nhập có ăn không.
check("quên cache thì quên CẢ cache âm",
      '_AUTH_LOI["ts"] = 0.0' in _src_cli)

# ============================================================
# 7. (B) Trang Models không chặn màn hình
# ============================================================
_con = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
_cloud = _con[_con.index("async function renderModelsCloudTab"):]
_cloud = _cloud[:_cloud.index("\n  async function", 10)]
# Vẫn hỏi /claude/status (thứ tự thẻ cần nó - xem test_prov_order), nhưng phải CÓ TRẦN CHỜ.
# Bản cũ gọi trần trụi: `claude` treo là màn hình kẹt vĩnh viễn, vì fetch treo không reject
# nên `catch` không cứu được. freshSettings ngay trên đã có AbortController từ lâu.
check("lượt gọi /claude/status chặn màn hình phải có AbortController",
      "new AbortController()" in _cloud and "ac.abort()" in _cloud, _cloud[:400])
check("và trần chờ phải được dọn (clearTimeout) để không rò hẹn giờ",
      "clearTimeout(hen)" in _cloud)
check("quá hạn thì VẼ TIẾP chứ không dừng (claudeOn khởi tạo false)",
      "let claudeOn = false;" in _cloud)
# refreshClaudeCard vẫn phải hỏi, chỉ là bất đồng bộ và không chặn nét vẽ đầu.
check("refreshClaudeCard vẫn hỏi trạng thái (bất đồng bộ, không chặn)",
      "/claude/status" in _con)

print("")
if fails:
    print(f"ĐỎ {len(fails)} mục")
    sys.exit(1)
print("Tất cả xanh.")
