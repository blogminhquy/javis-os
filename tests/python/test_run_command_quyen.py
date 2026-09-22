"""`javis_run_command`: rào quyền, rào thư mục, rào env, rào thời gian.

    python tests/run.py run_command_quyen

Đây là tool NGUY HIỂM NHẤT mà Javis cấp cho engine không native, nên phần lớn phép thử ở đây
là phép thử CHẶN chứ không phải phép thử chạy.

Ba rào phải giữ, mỗi rào có phép thử riêng:
  - **Không qua shell.** `&&`, `;`, `|`, `$(...)` bị từ chối thẳng. Thiếu rào này thì
    allowlist chỉ cần một dấu chấm phẩy là vô dụng.
  - **Env lọc trắng.** Lệnh do model đặt ra KHÔNG được thấy API key trong env của server.
    Đây đúng là lý do không giao PTY của `terminal.py` cho model.
  - **Ghim trong thư mục làm việc.** `cwd` do model truyền không được trỏ ra ngoài.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-runcmd-")
os.environ["JAVIS_STATE_DIR"] = _TMP
# Biến "bí mật" cắm vào env của tiến trình test, để chứng minh lệnh con KHÔNG thấy nó.
os.environ["JAVIS_TEST_SECRET"] = "KHOA-BI-MAT-KHONG-DUOC-LO"

import run_command as rc  # noqa: E402
from coding_ctx import CodingToolContext  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


WS = Path(_TMP) / "du-an"
(WS / "con").mkdir(parents=True, exist_ok=True)
(WS / "a.txt").write_text("noi dung a", encoding="utf-8")


def ctx(muc="auto", root=None):
    return CodingToolContext(session_id="s", workspace_root=str(root or WS),
                             permission_mode=muc, is_git_repo=False)


# ---- 1. Không qua shell: rào quan trọng nhất ----

for xau in ("ls && rm -rf /", "ls; whoami", "cat a.txt | grep x", "echo $(whoami)",
            "ls > out.txt", "echo `id`"):
    argv, loi = rc.tach(xau)
    check(f"từ chối ký tự shell: {xau[:24]}", not argv and bool(loi))

argv, loi = rc.tach("pytest -q tests/test_a.py")
check("lệnh thường tách được", argv == ["pytest", "-q", "tests/test_a.py"])
argv, loi = rc.tach('grep -r "hello world" .')
check("nháy kép giữ nguyên thành một tham số", argv[2] == "hello world")
argv, loi = rc.tach("")
check("lệnh rỗng bị từ chối", not argv and bool(loi))


# ---- 2. Mức suggest: KHÔNG chạy gì cả ----

kq = rc.chay("ls", ctx("suggest"))
check("suggest: không chạy", not kq.da_chay)
check("suggest: nói rõ vì sao và chỉ cách nâng", "suggest" in kq.error and "auto" in kq.error)


# ---- 3. Mức auto: chỉ allowlist ----

check("auto: cho pytest", rc.kiem_quyen(["pytest"], "auto") == "")
check("auto: cho ls", rc.kiem_quyen(["ls", "-la"], "auto") == "")
check("auto: cho git status", rc.kiem_quyen(["git", "status"], "auto") == "")
check("auto: cho git diff", rc.kiem_quyen(["git", "diff"], "auto") == "")
check("auto: CHẶN git commit", rc.kiem_quyen(["git", "commit", "-m", "x"], "auto") != "")
check("auto: CHẶN git push", rc.kiem_quyen(["git", "push"], "auto") != "")
check("auto: CHẶN git reset", rc.kiem_quyen(["git", "reset", "--hard"], "auto") != "")
check("auto: CHẶN git checkout", rc.kiem_quyen(["git", "checkout", "main"], "auto") != "")
check("auto: cho npm test", rc.kiem_quyen(["npm", "test"], "auto") == "")
check("auto: CHẶN npm install (đụng mạng, ghi ngoài workspace)",
      rc.kiem_quyen(["npm", "install", "left-pad"], "auto") != "")
check("auto: CHẶN chương trình lạ", rc.kiem_quyen(["docker", "ps"], "auto") != "")
check("auto: câu từ chối chỉ đúng cách nâng quyền",
      "full" in rc.kiem_quyen(["docker", "ps"], "auto"))

check("so bằng TÊN CHƯƠNG TRÌNH, không phải chuỗi con: 'gitfoo' không lọt",
      rc.kiem_quyen(["gitfoo"], "auto") != "")
check("đường dẫn đầy đủ vẫn nhận ra tên chương trình",
      rc.kiem_quyen(["/usr/bin/git", "status"], "auto") == "")
check("đuôi .exe của Windows vẫn nhận ra",
      rc.kiem_quyen(["git.exe", "status"], "auto") == "")


# ---- 4. Mức full: rộng hơn, nhưng chặn cứng vẫn giữ ----

check("full: cho git commit", rc.kiem_quyen(["git", "commit", "-m", "x"], "full") == "")
check("full: cho npm install", rc.kiem_quyen(["npm", "install"], "full") == "")
check("full: cho chương trình lạ", rc.kiem_quyen(["docker", "ps"], "full") == "")

for nguy in ("rm", "dd", "mkfs", "shutdown", "sudo", "chmod", "curl", "wget"):
    check(f"CHẶN CỨNG ở MỌI mức kể cả full: {nguy}",
          rc.kiem_quyen([nguy, "-x"], "full") != "")
check("câu chặn cứng nói rõ là rào cứng, không phải thiếu quyền",
      "MỌI mức" in rc.kiem_quyen(["rm", "-rf", "/"], "full"))


# ---- 5. Chạy thật, trong thư mục làm việc ----

kq = rc.chay("python -c \"print('xin chao')\"", ctx("auto"))
check("chạy thật được", kq.da_chay and kq.ok)
check("bắt được stdout", "xin chao" in kq.output)
check("exit code 0", kq.exit_code == 0)

kq = rc.chay("python -c \"import sys; sys.exit(3)\"", ctx("auto"))
check("mã thoát khác 0 -> ok=False nhưng vẫn da_chay", kq.da_chay and not kq.ok)
check("giữ đúng mã thoát", kq.exit_code == 3)

kq = rc.chay("python -c \"import os; print(os.getcwd())\"", ctx("auto"))
check("chạy ĐÚNG trong thư mục làm việc", str(WS.resolve()) in kq.output)

kq = rc.chay("python -c \"import os; print(os.getcwd())\"", ctx("auto"), cwd="con")
check("cwd con được phép", str((WS / "con").resolve()) in kq.output)


# ---- 6. Env lọc trắng: lệnh con KHÔNG thấy bí mật của server ----

kq = rc.chay('python -c "import os; print(os.environ.get(\'JAVIS_TEST_SECRET\', \'KHONG-THAY\'))"',
             ctx("auto"))
check("lệnh con KHÔNG thấy biến bí mật của env server",
      "KHONG-THAY" in kq.output and "KHOA-BI-MAT" not in kq.output)
kq = rc.chay('python -c "import os; print(len(os.environ))"', ctx("auto"))
check("env truyền xuống rất nhỏ, không phải nguyên env server",
      kq.ok and int(kq.output.strip().splitlines()[-1]) < 20)


# ---- 7. Ghim trong thư mục làm việc ----

kq = rc.chay("ls", ctx("auto"), cwd="../..")
check("cwd trỏ ra ngoài workspace -> chặn", not kq.da_chay)
check("câu chặn nêu thư mục làm việc", str(WS.resolve()) in kq.error)
kq = rc.chay("ls", ctx("auto"), cwd="/etc")
check("cwd tuyệt đối ra ngoài -> chặn", not kq.da_chay)
kq = rc.chay("ls", ctx("auto"), cwd="khong-co-thu-muc-nay")
check("cwd không tồn tại -> câu lỗi nói được, không nổ", not kq.da_chay and "thư mục" in kq.error)


# ---- 8. Trần thời gian ----

kq = rc.chay('python -c "import time; time.sleep(30)"', ctx("auto"), timeout_s=1)
check("quá trần thời gian -> bị dừng", not kq.ok)
check("quá trần -> câu lỗi nói rõ số giây", "giây" in kq.error)
check("quá trần -> không treo lâu hơn trần bao nhiêu", kq.elapsed < 10)

kq = rc.chay("python -c \"print(1)\"", ctx("auto"), timeout_s=99999)
check("timeout model tự đặt bị kẹp ở trần trên (không treo cả lượt chat)", kq.ok)


# ---- 9. Trần output: giữ đầu và ĐUÔI ----

kq = rc.chay('python -c "print(\'x\' * 50000); print(\'DONG-CUOI-QUAN-TRONG\')"', ctx("auto"))
check("output quá dài bị cắt", len(kq.output) <= rc.OUTPUT_TOI_DA + 200)
check("cắt output vẫn GIỮ ĐUÔI (lỗi thật thường ở đuôi)",
      "DONG-CUOI-QUAN-TRONG" in kq.output)
check("có nói rõ đã cắt bao nhiêu", "cắt" in kq.output)


# ---- 10. Không có workspace thì không chạy ----

kq = rc.chay("ls", CodingToolContext())
check("phiên không gắn thư mục -> không chạy", not kq.da_chay)
check("câu lỗi chỉ đúng chỗ cần làm", "trang Coding" in kq.error)


# ---- 11. Chương trình không tồn tại: câu lỗi nói được, KHÔNG ném ----

kq = rc.chay("chuong-trinh-khong-co-that --x", ctx("full"))
check("chương trình không có -> không ném, trả câu nói được",
      not kq.da_chay and "Không tìm thấy" in kq.error)


# ---- 12. Gói kết quả cho model ----

kq = rc.chay("python -c \"print('abc')\"", ctx("auto"))
s = rc.ket_qua_cho_model(kq)
check("kết quả cho model: mã thoát đứng TRƯỚC (nén theo spec)", s.startswith("exit=0"))
check("kết quả cho model: có thời gian chạy", "s)" in s)
check("kết quả cho model: có output", "abc" in s)
s2 = rc.ket_qua_cho_model(rc.chay("ls", ctx("suggest")))
check("bị chặn -> gói thành ERROR cho model", s2.startswith("ERROR:"))


# ---- 13. Cắm vào hub: chỉ hiện trong phiên có thư mục làm việc ----

import mcp_hub  # noqa: E402

t_thuong, _ = mcp_hub._builtin_tools("full", str(WS))
check("phiên KHÔNG có thư mục làm việc -> hub KHÔNG cấp javis_run_command",
      "javis_run_command" not in [x["fn"] for x in t_thuong])

t_code, r_code = mcp_hub._builtin_tools("full", str(WS), workspace_root=str(WS),
                                        coding_ctx_cua_phien=ctx("auto"))
check("phiên coding -> hub cấp javis_run_command",
      "javis_run_command" in [x["fn"] for x in t_code])
check("javis_run_command khai effect full (mức quyền cao nhất của hub)",
      r_code["javis_run_command"]["required_mode"] == "full")
check("javis_run_command nằm trong nhóm hạt nhân, không bị tầng lazy giấu",
      "javis_run_command" in mcp_hub.CORE_TOOL_FNS)

t_thieu, _ = mcp_hub._builtin_tools("full", str(WS), workspace_root=str(WS))
check("có workspace nhưng THIẾU ctx -> vẫn không cấp tool chạy lệnh",
      "javis_run_command" not in [x["fn"] for x in t_thieu])

import asyncio  # noqa: E402
_, r_sug = mcp_hub._builtin_tools("full", str(WS), workspace_root=str(WS),
                                  coding_ctx_cua_phien=ctx("suggest"))
_ra = asyncio.run(r_sug["javis_run_command"]["call"]({"command": "ls"}))
check("qua hub, mức suggest vẫn bị chặn (hai lớp quyền, không thay nhau)",
      _ra.startswith("ERROR:"))

_hub_src = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
check("mức quyền của phiên nằm trong khoá cache (hai phiên cùng repo khác chip không lẫn nhau)",
      "_quyen_ctx" in _hub_src and "_ten_goc(workspace_root), _quyen_ctx" in _hub_src)


# ---- 14. Ranh giới mã nguồn ----

_src = (SERVER / "run_command.py").read_text(encoding="utf-8")
check("TUYỆT ĐỐI không shell=True", "shell=True" not in _src)
check("có nói rõ shell=False", "shell=False" in _src)
check("không dùng PTY của terminal.py", "import terminal" not in _src)
check("không thừa kế nguyên env server", "os.environ.copy()" not in _src)
for cam in ("import main", "from main", "fastapi"):
    check(f"module thuần, không '{cam}'", cam not in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_run_command_quyen: tất cả pass")
