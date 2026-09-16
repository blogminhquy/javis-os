"""Làn nhanh rơi về bộ não chính thì phải NÓI RA, không được lặng lẽ (0.59.23).

    python tests/run.py lan_nhanh_roi_ve

Vì sao file này tồn tại: chủ dự án báo 16/09 "sau vài lần cập nhật, bật mic là bỏ qua lớp nói
chuyện nhanh, đi thẳng vào lớp suy luận". Soi mã thì đường rẽ vào làn nhanh không đổi từ 0.57.7;
thứ đổi được trải nghiệm mà KHÔNG để lại dấu vết nào trên màn hình là nhánh rơi về bộ não chính
khi bộ não giọng lỗi: nó chỉ in stderr và gửi một `status` bị "Javis đang suy nghĩ..." đè lên
ngay. Bốn lớp canh:
  1. voice_brain nhớ lỗi gần nhất, xoá khi chạy lại tốt, và soạn câu báo gọi đúng tên bộ não.
  2. run_voice_turn: nhánh except gửi bong bóng `system` (ở lại trong khung chat) TRƯỚC khi gọi
     run_turn, và đường trót lọt xoá lỗi cũ.
  3. GET /voice/options trả `last_error` để thẻ Giọng nói ở Cài đặt hiện lại.
  4. Tin từ mic không đi làn nhanh thì ghi log đúng MỘT lần cho mỗi cấu hình.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import json
import os
import re
import tempfile
from contextlib import redirect_stderr

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-voicefb-")

from fastapi.testclient import TestClient   # noqa: E402
import voice_brain as vb   # noqa: E402
import main                # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. voice_brain nhớ lỗi và soạn câu báo ----
vb.xoa_loi_lan_nhanh()
check("chưa có lỗi thì loi_lan_nhanh_gan_nhat rỗng", vb.loi_lan_nhanh_gan_nhat() == {})
rec = vb.ghi_loi_lan_nhanh("claude", RuntimeError("Chưa cài hoặc  chưa đăng nhập\nClaude Code (claude)."), now=1000.0)
check("ghi lỗi: đúng provider", rec["provider"] == "claude")
check("ghi lỗi: nhãn là nhãn ở thẻ cài đặt", rec["label"] == vb.BRAIN_PROVIDERS["claude"]["label"])
check("ghi lỗi: gom khoảng trắng, không xuống dòng", rec["error"] == "Chưa cài hoặc chưa đăng nhập Claude Code (claude).")
check("ghi lỗi: có mốc giờ", rec["at"] == 1000.0)
check("lỗi gần nhất đọc lại được", vb.loi_lan_nhanh_gan_nhat()["error"] == rec["error"])
vb.ghi_loi_lan_nhanh("groq", "x" * 1000)
check("lỗi dài bị cắt", len(vb.loi_lan_nhanh_gan_nhat()["error"]) <= 300)
check("ghi lỗi mới thay lỗi cũ", vb.loi_lan_nhanh_gan_nhat()["provider"] == "groq")
vb.xoa_loi_lan_nhanh()
check("xoá xong thì rỗng", vb.loi_lan_nhanh_gan_nhat() == {})
check("provider lạ vẫn có tên", vb.ten_bo_nao("bo-nao-la") == "bo-nao-la")

cau = vb.cau_roi_ve_bo_nao_chinh("antigravity", RuntimeError("Chưa cài Antigravity CLI (agy)."))
check("câu báo gọi đúng tên bộ não", vb.BRAIN_PROVIDERS["antigravity"]["label"] in cau)
check("câu báo chép lại lỗi thật", "Chưa cài Antigravity CLI (agy)." in cau)
check("câu báo nói lượt này đi bộ não chính", "bộ não chính" in cau)
check("câu báo chỉ chỗ sửa (Cài đặt, Giọng nói)", "Cài đặt" in cau and "Giọng nói" in cau)
check("câu báo không có gạch dài", "—" not in cau and "–" not in cau)
check("lỗi rỗng vẫn ra câu đọc được", "không rõ lỗi" in vb.cau_roi_ve_bo_nao_chinh("groq", ""))

# ---- 2. run_voice_turn: nhánh except nói ra TRƯỚC khi rơi về run_turn ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
i0 = src.index("async def run_voice_turn(")
i1 = src.index("noi, ui = voice_brain.parse_ui(text)", i0)
doan = src[i0:i1]
m_exc = re.search(r"except Exception as e:(.*?)await run_turn\(", doan, re.S)
check("nhánh except của run_voice_turn vẫn rơi về run_turn", m_exc is not None)
than = m_exc.group(1) if m_exc else ""
check("nhánh except NHỚ lỗi (ghi_loi_lan_nhanh)", "voice_brain.ghi_loi_lan_nhanh(" in than)
check("nhánh except gửi bong bóng `system` (ở lại khung chat) trước run_turn",
      '"type": "system"' in than and "cau_roi_ve_bo_nao_chinh(" in than)
sau_exc = doan[doan.index("except Exception as e:"):] if m_exc else ""
check("đường trót lọt XOÁ lỗi cũ trước khi đọc marker", "voice_brain.xoa_loi_lan_nhanh()" in sau_exc)

# ---- 3. /voice/options trả last_error ----
cl = TestClient(main.app, base_url="http://127.0.0.1:7777")
vb.xoa_loi_lan_nhanh()
r = cl.get("/voice/options")
check("GET /voice/options 200", r.status_code == 200)
o = r.json() if r.status_code == 200 else {}
check("chưa lỗi: last_error là dict rỗng", o.get("last_error") == {})
vb.ghi_loi_lan_nhanh("codex", "Chưa kết nối ChatGPT (OAuth) ở trang Models.", now=2000.0)
o = cl.get("/voice/options").json()
le = o.get("last_error") or {}
check("có lỗi: last_error mang provider, label, error, at",
      le.get("provider") == "codex" and le.get("label") and "ChatGPT" in le.get("error", "") and le.get("at") == 2000.0)
vb.xoa_loi_lan_nhanh()

# ---- 3b. thẻ Cài đặt và i18n ----
cjs = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("console.js vẽ last_error vào thẻ Giọng nói", "o.last_error" in cjs and "v2LastErr" in cjs)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    txt = d.get("settings.v2_last_error", "")
    check(f"i18n {lang} có settings.v2_last_error đủ 3 chỗ trống", all(k in txt for k in ("{brain}", "{error}", "{min}")))
    check(f"i18n {lang} không có gạch dài", "—" not in txt and "–" not in txt)

# ---- 4. tin từ mic không đi làn nhanh: log MỘT lần cho mỗi cấu hình ----
main._LAN_NHANH_DA_BAO.clear()
buf = io.StringIO()
with redirect_stderr(buf):
    a = main._bao_lan_nhanh_bo_qua({"mode": "standard", "provider": ""})
    b = main._bao_lan_nhanh_bo_qua({"mode": "standard", "provider": ""})
    c = main._bao_lan_nhanh_bo_qua({"mode": "fast", "provider": ""})
    d = main._bao_lan_nhanh_bo_qua(None)
    e = main._bao_lan_nhanh_bo_qua({"mode": "fast", "provider": "claude"})
log = buf.getvalue()
check("chế độ chuẩn: không đi làn nhanh", a is True and b is True)
check("chế độ chuẩn: chỉ log MỘT lần", log.count("[voice lane]") == 3 and "'standard'" in log)
check("Làn nhanh nhưng chưa chọn bộ não: log nói đúng", c is True and "chưa chọn bộ não giọng" in log)
check("không đọc được cài đặt: log nói đúng", d is True and "không đọc được" in log)
check("Làn nhanh có bộ não: đi làn nhanh, không log", e is False)

print()
if _fails:
    print("FAIL:", len(_fails), "->", "; ".join(_fails))
    raise SystemExit(1)
print("OK - lan_nhanh_roi_ve_noi_ro")
