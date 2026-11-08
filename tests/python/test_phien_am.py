"""Phiên âm từ tiếng Anh ra âm tiết Việt (phien_am) và hai chỗ dùng nó.

    python tests/run.py phien_am

Vì sao file này tồn tại (0.64.68): chủ dự án chốt đọc từ tiếng Anh theo kiểu người Việt nói,
cả câu MỘT giọng đã chọn ("Micro" là "mi cờ rô", "Emma" là "em ma", "GitHub Action" là "ghít
hắp ác sừn"), thay cho cách ghép hai giọng của 0.64.67 (nghe lúc Anh lúc Việt, và chọn giọng
khác vẫn ra Hoài My). Cùng bộ phiên âm đó giúp chốt kiểm tra câu diễn giải so âm đúng: máy nghe
chép "GitHub Actions" thành "huyết áp Action", so mặt chữ tiếng Anh thì chặn, so cách đọc thì
khớp. Không chạm mạng: edge_tts bị thay bằng module giả.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import types

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-phien-am-"))

import phien_am as P  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Đúng mấy ví dụ chủ dự án đưa ----
check("Micro -> mi cờ rô", P.doc_tu("Micro") == "mi cờ rô")
check("Emma -> em ma", P.doc_tu("Emma") == "em ma")
check("GitHub Actions -> ghít hắp ác sừn",
      P.doc_viet("Mở GitHub Actions nhé") == "Mở ghít hắp ác sừn nhé")

# ---- 2. Từ điển CMU nạp được, tra được, và luật đổi âm tiết ----
check("từ điển CMU nạp được (file data_phien_am/cmudict.txt.gz)", P.tra_cmu("action") == ["AE1", "K", "SH", "AH0", "N"])
check("từ không có trong CMU trả None", P.tra_cmu("zzqxv") is None)
for tu, doc in [("deploy", "đi pờ lôi"), ("check", "chéc"), ("pass", "pát"), ("quick", "quých"),
                ("street", "sờ trít"), ("network", "nét uớc"), ("python", "pai thon"),
                ("computer", "cừm piu tờ"), ("customer", "cắt tờ mờ"), ("discount", "đít cao")]:
    check(f"{tu} -> {doc}", P.doc_tu(tu) == doc)
check("chữ viết tắt đọc từng chữ cái kiểu Việt", P.doc_tu("VPS") == "vi pi ét" and P.doc_tu("MCP") == "em xi pi")
check("từ ghép viết hoa giữa tách ra đọc", P.doc_tu("NodeRunner").count(" ") >= 2)
check("từ lạ vẫn ra chữ, không rỗng, không ném lỗi", bool(P.doc_tu("Zxqtrom")))
check("âm tiết tắc mang dấu sắc, âm chêm dấu huyền", "ác" in P.doc_tu("action") and "cờ" in P.doc_tu("micro"))

# ---- 3. doc_viet: chỉ đổi từ tiếng Anh, còn lại giữ nguyên ----
C = "Em đã chạy lại workflow trên GitHub Actions, build pass rồi, anh có thể deploy lên VPS."
out = P.doc_viet(C)
check("câu trộn: mọi từ tiếng Anh đã được thay",
      not any(w in out for w in ("workflow", "GitHub", "Actions", "build", "pass", "deploy", "VPS")))
check("câu trộn: giữ nguyên phần tiếng Việt và dấu câu",
      out.startswith("Em đã chạy lại ") and ", anh có thể " in out and out.endswith(".") and "rồi," in out)
check("câu thuần tiếng Anh giữ nguyên (để giọng đọc như tiếng Anh)",
      P.doc_viet("The build passed on GitHub Actions.") == "The build passed on GitHub Actions.")
V = "Anh cứ nói to lên, em in hoá đơn rồi so sánh nhé, ai cũng được."
check("từ tiếng Việt không dấu (to, in, so, ai) không bị phiên âm", P.doc_viet(V) == V)
check("số, đường dẫn và khoảng trắng giữ nguyên",
      P.doc_viet("Giá 12.500 đồng,  xem ở trang chủ nhé") == "Giá 12.500 đồng,  xem ở trang chủ nhé")
check("chuỗi rỗng", P.doc_viet("") == "" and P.doc_viet(None) == "")

# ---- 3b. Whole English sentences are not respelled (Vinglish report, 2026-11-08) ----
EMMA, HOAIMY = "en-US-EmmaMultilingualNeural", "vi-VN-HoaiMyNeural"
Q = "Mình tóm tắt nhé: Artificial intelligence is transforming how businesses operate every day."
check("an English sentence inside a Vietnamese answer stays English", P.doc_viet(Q, EMMA) == Q)
Q2 = "Đây là kết quả. The quick brown fox jumps over the lazy dog."
check("an English sentence after a Vietnamese one stays English", P.doc_viet(Q2, EMMA) == Q2)
E = "Open the Hội thoại page to see your chats."
check("an English answer naming a Vietnamese page stays English", P.doc_viet(E, EMMA) == E)
check("terms inside Vietnamese are still respelled with a multilingual voice",
      P.doc_viet("Mở GitHub Actions nhé", EMMA) == "Mở ghít hắp ác sừn nhé"
      and P.doc_viet(C, EMMA) == P.doc_viet(C))
N = "Javis hỗ trợ Claude Code, ChatGPT, Grok Build, OpenRouter."
check("a list of product names is not mistaken for an English sentence",
      not any(w in P.doc_viet(N, EMMA) for w in ("Claude", "ChatGPT", "OpenRouter")))
check("a Vietnamese-only voice still respells everything (it cannot speak English)",
      "quick" not in P.doc_viet(Q2, HOAIMY) and "intelligence" not in P.doc_viet(Q, HOAIMY))

# ---- 4. Chốt kiểm tra câu diễn giải so âm theo cách đọc ----
import voice_brain as vb  # noqa: E402

NHAN = [("vẫn không nhận ra huyết áp Action luôn", "vẫn không nhận ra GitHub Actions luôn"),
        ("anh hỏi về khít half action", "anh hỏi về GitHub Actions"),
        ("Cho anh hỏi về phía SH Action thì", "Cho anh hỏi về GitHub Actions thì"),
        ("mở trang mên", "mở trang main"),
        ("xin chào David", "xin chào Javis")]
for cu, moi in NHAN:
    check(f"nhận câu sửa đúng: {cu!r}", vb.safe_transcript_rewrite(cu, moi) == moi)
CHAN = [("trả lời khách đi", "trở thành khách đi"), ("gửi email cho sếp", "gửi Zalo cho sếp"),
        ("không gửi nữa", "có gửi nữa"), ("xoá file báo cáo", "sửa file báo cáo"),
        ("chuyển năm triệu", "chuyển nam triệu"), ("vâng em hiểu", "Vân em hiểu"),
        ("bán cho anh", "ban cho anh"), ("nhắn cho khách là mai giao", "nhắn cho khách là mai giao hàng")]
for cu, moi in CHAN:
    check(f"chặn câu sửa sai nghĩa: {cu!r} -> {moi!r}", vb.safe_transcript_rewrite(cu, moi) == cu)


# ---- 5. /tts: Edge nhận câu đã phiên âm, đúng giọng người dùng chọn, gọi một lần ----
class _FakeCommunicate:
    goi = []

    def __init__(self, text, voice, rate="+0%", **kw):
        _FakeCommunicate.goi.append((text, voice))

    async def stream(self):
        yield {"type": "audio", "data": b"ID3abc"}


fake = types.ModuleType("edge_tts")
fake.Communicate = _FakeCommunicate
sys.modules["edge_tts"] = fake

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_cfg_goc = main.cfgmod.read_settings
main.cfgmod.read_settings = lambda: {"voice": {"tts_provider": "edge"}, "model": {}}
try:
    for giong in ("vi-VN-HoaiMyNeural", "en-US-AndrewMultilingualNeural"):
        _FakeCommunicate.goi = []
        r = client.get("/tts", params={"text": "Mở GitHub Actions nhé", "voice": giong})
        check(f"/tts {giong}: 200 và gọi Edge MỘT lần đúng giọng đã chọn",
              r.status_code == 200 and [v for _, v in _FakeCommunicate.goi] == [giong])
        check(f"/tts {giong}: Edge nhận câu đã phiên âm",
              _FakeCommunicate.goi and _FakeCommunicate.goi[0][0] == "Mở ghít hắp ác sừn nhé")
    _FakeCommunicate.goi = []
    client.get("/tts", params={"text": "The build passed.", "voice": "en-US-EmmaMultilingualNeural"})
    check("/tts câu thuần tiếng Anh: giữ nguyên chữ", _FakeCommunicate.goi[0][0] == "The build passed.")
    _FakeCommunicate.goi = []
    client.get("/tts", params={"text": Q2, "voice": "en-US-EmmaMultilingualNeural"})
    check("/tts English sentence inside Vietnamese reaches Emma unchanged", _FakeCommunicate.goi[0][0] == Q2)
finally:
    main.cfgmod.read_settings = _cfg_goc

check("main.py không còn đường ghép hai giọng (0.64.67)",
      "tts_tron_tieng" not in (SERVER / "main.py").read_text(encoding="utf-8"))
check("giấy phép dữ liệu CMU đi kèm file dữ liệu",
      (SERVER / "data_phien_am" / "LICENSE-cmudict").is_file()
      and "Carnegie Mellon" in (SERVER / "data_phien_am" / "LICENSE-cmudict").read_text(encoding="utf-8"))

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - phien_am")
