"""Tạo file từ chat phải CHÍNH XÁC: ghi đúng thư mục brain, link bấm là mở, mất mạch thì mồi lại.

    python tests/run.py tao_file_tu_chat      (KHÔNG mạng, KHÔNG cần đăng nhập Claude)

Chủ repo báo (2026-09-08) ba chuyện tưởng khác nhau: hỏi "còn bao nhiêu bài chưa hoàn thiện"
lần đầu ra 3, lần sau ra 5; đoạn chat ghi rõ đã viết file mà mở thư mục không thấy; link file
trong chat bấm vào không ra. Điều tra ra CÙNG MỘT GỐC:

  Claude Code trong chat là engine DUY NHẤT trong bốn engine chat còn chạy với cwd = GỐC
  PROJECT (`CLAUDE_CWD`, /app trong Docker) thay vì thư mục brain - Codex, Antigravity, Grok
  và mọi workflow/loop/lint đều đã cwd=brain. Model ghi "bai-viet/x.md" là rơi vào /app (bay
  theo lần dựng lại container kế tiếp); link trong chat lại phân giải theo brain nên bấm không
  ra; "đếm bài" lúc nhìn /app lúc nhìn brain nên lúc 3 lúc 5.

Sửa cwd kéo theo một cái giá đã ĐO trực tiếp trên binary `claude` 2.1.263: transcript nằm ở
~/.claude/projects/<cwd đã mã hoá>/, tạo phiên ở thư mục A rồi `--resume` từ B là "No
conversation found with session ID". Tức mọi phiên cũ resume trượt đúng một lần sau bản này -
và bản trước thì để cái id chết đó được LƯU LẠI rồi resume tiếp ở lượt sau, hội thoại kẹt vĩnh
viễn. Nên file này canh cả ba tầng: cwd, chuẩn hoá link, và khôi phục khi mất mạch.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-taofile-")

import main  # noqa: E402
import claude_sdk_engine  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them)[:200] + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

# ============================================================
# 1. Cả hai đường chat Claude Code chạy TRONG thư mục brain
# ============================================================
check("dashboard: engine Claude dựng với cwd = thư mục brain",
      "claude_engine(system_prompt=SYSTEM_PROMPT, cwd=_brain_root(brain), tag=turn_tag)" in MAIN)
check("CANARY: dashboard KHÔNG còn dựng engine chat với cwd=CLAUDE_CWD (gốc project)",
      "claude_engine(system_prompt=SYSTEM_PROMPT, cwd=CLAUDE_CWD, tag=turn_tag)" not in MAIN)
check("telegram: engine Claude chạy trong brain, và dựng lại khi /brain đổi sang brain khác",
      'getattr(sess["cli"], "cwd", None) != _goc' in MAIN
      and 'cwd=_goc, tag=f"telegram:{chat_id}"' in MAIN)
check("telegram: file vừa ghi được thu theo thư mục brain, không theo gốc project",
      'cwd=_brain_root(brain), exclude=sess["sent"]' in MAIN)
# Ba engine kia đã cwd=brain từ trước - canh để không ai kéo lùi một cái về gốc project.
check("bốn engine chat cùng chạy cwd=brain",
      "CodexCLI(cwd=_brain_root(brain)" in MAIN and "AntigravityCLI(cwd=_brain_root(brain)" in MAIN
      and "GrokCLI(cwd=_brain_root(brain)" in MAIN)

# ============================================================
# 2. Chuẩn hoá link: hành vi THẬT trên đĩa
# ============================================================
brain = Path(tempfile.mkdtemp(prefix="javis-brain-")).resolve()
(brain / "bai-viet").mkdir()
(brain / "bai-viet" / "bai-1.txt").write_text("x", encoding="utf-8")
(brain / "06 - Sources").mkdir()
(brain / "06 - Sources" / "ghi chu.md").write_text("y", encoding="utf-8")
ngoai = Path(tempfile.mkdtemp(prefix="javis-ngoai-")).resolve()
(ngoai / "lac.md").write_text("z", encoding="utf-8")


def H(t, w=None):
    return main._chuan_hoa_link_file(str(brain), t, w)


check("tuyệt đối TRONG brain → tương đối theo gốc brain",
      H(f"[bài 1]({brain}/bai-viet/bai-1.txt)") == "[bài 1](bai-viet/bai-1.txt)",
      H(f"[bài 1]({brain}/bai-viet/bai-1.txt)"))
check("tuyệt đối trong backtick → tương đối (khung chat mới biến thành link bấm được)",
      H(f"Đã lưu `{brain}/bai-viet/bai-1.txt`") == "Đã lưu `bai-viet/bai-1.txt`",
      H(f"Đã lưu `{brain}/bai-viet/bai-1.txt`"))
check("tuyệt đối TRẦN trong brain → bọc backtick tương đối, giữ dấu câu",
      H(f"Đã lưu tại {brain}/bai-viet/bai-1.txt.") == "Đã lưu tại `bai-viet/bai-1.txt`.",
      H(f"Đã lưu tại {brain}/bai-viet/bai-1.txt."))
check("%20 trong link vault được gỡ (tên thật trên đĩa không có %20)",
      H("[ghi chú](06%20-%20Sources/ghi%20chu.md)") == "[ghi chú](06 - Sources/ghi chu.md)",
      H("[ghi chú](06%20-%20Sources/ghi%20chu.md)"))
check("tương đối đúng thì giữ nguyên", H("[bài 1](bai-viet/bai-1.txt)") == "[bài 1](bai-viet/bai-1.txt)")
_giu = "[a](https://x.vn/b.md) [b](#muc) [c](/files/raw?brain=x&path=y.md) [d](mailto:a@b.vn)"
check("URL, anchor, /files/raw, mailto không bị đụng", H(_giu) == _giu, H(_giu))
check("CANARY: tuyệt đối NGOÀI brain giữ nguyên (không bịa một đường vào brain)",
      H(f"[lạc]({ngoai}/lac.md)") == f"[lạc]({ngoai}/lac.md)")
check("sai thư mục nhưng đúng TÊN file vừa ghi trong lượt → trỏ sang file thật",
      H("[bài](nhap/bai-1.txt)", [str(brain / "bai-viet" / "bai-1.txt")]) == "[bài](bai-viet/bai-1.txt)",
      H("[bài](nhap/bai-1.txt)", [str(brain / "bai-viet" / "bai-1.txt")]))
check("sai thư mục mà KHÔNG có file nào trùng tên thì giữ nguyên (đừng đoán)",
      H("[bài](nhap/bai-9.txt)", [str(brain / "bai-viet" / "bai-1.txt")]) == "[bài](nhap/bai-9.txt)")
check("ảnh markdown cũng được chuẩn hoá",
      H(f"![sơ đồ]({brain}/bai-viet/bai-1.txt)") == "![sơ đồ](bai-viet/bai-1.txt)")
check("không có gì để đổi thì trả nguyên văn", H("chào anh, hôm nay 3/5 bài xong rồi") == "chào anh, hôm nay 3/5 bài xong rồi")
check("backtick chứa lệnh/tên tool không bị đụng", H("gọi `javis_write_file` rồi `ls -la`") == "gọi `javis_write_file` rồi `ls -la`")

# ============================================================
# 3. Link trỏ vào hư không → nói ra, không im
# ============================================================
def K(t):
    return main._link_file_khong_thay(str(brain), t)


check("link tới file không có trong brain → báo", K("[x](bai-viet/khong-co.txt)") == ["bai-viet/khong-co.txt"])
check("link đúng → không báo", K("[x](bai-viet/bai-1.txt)") == [])
check("tuyệt đối ngoài brain → báo (khung chat không mở được)",
      K(f"[x]({ngoai}/lac.md)") == [f"{ngoai}/lac.md"])
check("URL, anchor, link chữ (không phải đường dẫn file) không tính",
      K("[x](https://a.vn/b.md) [y](#muc) [z](models)") == [])
check("báo tối đa 5 và không lặp",
      len(K(" ".join(f"[{i}](k/{i % 3}.md)" for i in range(12)))) == 3)
_cau = main._cau_link_khong_thay(["bai-viet/khong-co.txt"])
check("câu báo kể tên file, chỉ chỗ tự kiểm, không dùng em dash",
      "bai-viet/khong-co.txt" in _cau and "Tệp tin" in _cau and "—" not in _cau)

# ============================================================
# 4. File "vừa ghi trong lượt": có thật, trong brain, mtime mới
# ============================================================
_t0 = time.time() - 10
_moi = brain / "bai-viet" / "bai-2.txt"
_moi.write_text("m", encoding="utf-8")
_cu = brain / "bai-viet" / "bai-1.txt"
os.utime(_cu, (_t0 - 100, _t0 - 100))
_r = main._files_vua_ghi(str(brain), ["bai-viet/bai-2.txt", str(_cu), str(ngoai / "lac.md"), "khong/co.txt"], _t0)
check("chỉ giữ file có thật + trong brain + vừa đổi; tương đối ghép theo gốc brain",
      _r == [str(_moi)], _r)

# ============================================================
# 5. Mất mạch: engine cắm cờ, KHÔNG trả session_id chết; main.py mồi lại
# ============================================================
from claude_agent_sdk import ResultMessage  # noqa: E402

_rm = ResultMessage(subtype="error_during_execution", duration_ms=0, duration_api_ms=0, is_error=True,
                    num_turns=0, session_id="id-chet",
                    errors=["No conversation found with session ID: id-chet"])
_evs, _sid = claude_sdk_engine.map_message(_rm)
check("CANARY: resume trượt → sự kiện error mang cờ resume_failed",
      any(e.get("resume_failed") for e in _evs if e["type"] == "error"), _evs)
check("CANARY: không trả session_id chết cho người gọi lưu lại (lưu là lượt sau kẹt tiếp)",
      _sid is None and all(e.get("session_id") is None for e in _evs if e["type"] == "final"))
_rm2 = ResultMessage(subtype="error_during_execution", duration_ms=0, duration_api_ms=0, is_error=True,
                     num_turns=0, session_id="s2", errors=["boom"])
_evs2, _sid2 = claude_sdk_engine.map_message(_rm2)
check("lỗi khác KHÔNG bị nhận nhầm là mất mạch", not any(e.get("resume_failed") for e in _evs2) and _sid2 == "s2")
_rm3 = ResultMessage(subtype="success", duration_ms=0, duration_api_ms=0, is_error=False,
                     num_turns=1, session_id="s3", result="ok")
_evs3, _sid3 = claude_sdk_engine.map_message(_rm3)
check("lượt thường giữ nguyên hợp đồng cũ",
      _sid3 == "s3" and any(e["type"] == "final" and e["content"] == "ok" for e in _evs3))
check("engine: id chết bị bỏ ngay trong vòng đọc sự kiện",
      'elif ev.get("resume_failed"):\n                        self.session_id = None' in
      (ROOT / "server" / "claude_sdk_engine.py").read_text(encoding="utf-8"))
check("dashboard: mất mạch thì mồi lại từ kho phiên (cùng cách Codex)",
      "_resume_failed = await _consume_claude(" in MAIN
      and "Javis đang khôi phục ngữ cảnh từ lịch sử đã lưu" in MAIN)
check("telegram: mất mạch thì mồi lại", "_rf = await _chay_claude(_cli_prompt)" in MAIN)

# ============================================================
# 6. Prompt: dặn ghi file vào TRONG vault, link tương đối, đếm file bằng tool
# ============================================================
check("LỚP AGENTIC dặn ghi FILE THƯỜNG vào trong vault bằng đường dẫn tuyệt đối",
      "FILE KHÁC (bài viết, báo cáo, nháp, dữ liệu): ghi VÀO TRONG vault root" in MAIN)
check("LỚP AGENTIC dặn đếm/liệt kê file bằng tool ngay lúc đó (không nhớ lại lượt trước)",
      "liệt kê lại thư mục bằng tool ngay lúc đó" in MAIN)
# Luật này CỐ Ý không nằm trong CLAUDE.md: file đó đã sát trần 33.600 ký tự (test_prompt_budget),
# còn khối LỚP AGENTIC thì đi cùng mọi engine mỗi lượt và mang đúng đường dẫn gốc brain.
check("luật ghi file mang ĐÚNG gốc brain (f-string {root}), không phải chữ chung chung",
      'f"dẫn TUYỆT ĐỐI `{root}/<thư mục>/<tên file>`' in MAIN)
check("dashboard: link trỏ vào hư không → đẩy một dòng riêng (cùng cách lời hứa suông)",
      "await push_to_chat(conv_sid, _cau_link_khong_thay(_thieu))" in MAIN)
check("telegram: nối dòng đó vào cuối tin", '+ "\\n\\n" + _cau_link_khong_thay(_thieu)' in MAIN)
# Mọi khung `response` của engine chat đều đi qua bước chuẩn hoá link.
_so_cho = len(re.findall(r"_chuan_hoa_link_file\(\s*_brain_root\(brain\),\s*final_text", MAIN))
check("bốn engine CLI + engine API đều chuẩn hoá link trước khung response", _so_cho >= 5, _so_cho)

print("")
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test tao_file_tu_chat đã qua.")
