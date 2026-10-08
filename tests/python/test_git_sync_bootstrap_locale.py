"""Regression: bootstrap sync vào remote HOÀN TOÀN RỖNG không được chết vì git nói tiếng Việt.

Bug thật 06/10/2026: _sync_brains_locked nhận diện repo-rỗng bằng chuỗi tiếng Anh
"couldn't find remote ref", nhưng git dịch message theo locale - máy macOS đặt ngôn ngữ hệ
tiếng Việt thì libintl (git Homebrew) đọc AppleLanguages NGAY CẢ KHI env locale trống, stderr
thành "không thể tìm thấy tham chiếu máy chủ main" và first sync vào repo GitHub mới FAIL ở
fetch. Fix: _git() ép LC_ALL/LANG/LANGUAGE=C cho riêng subprocess git (xem _git_env).
Test này có 2 tầng: (1) kiểm env _git truyền cho subprocess - có răng trên MỌI máy/CI;
(2) e2e bootstrap bare repo rỗng dưới env locale tiếng Việt - tái hiện bug thật trên máy có
bản dịch vi (macOS dev) và pass trivially ở CI không có catalog vi. Chạy:
    python tests/run.py bootstrap_locale
Cần git trong PATH. KHÔNG mạng thật."""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os, sys, subprocess, tempfile
from pathlib import Path
import git_brain as gb  # noqa: E402

_fails = []
def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond: _fails.append(name)

if not gb.has_git():
    print("SKIP: máy không có git"); sys.exit(0)

# ── 1. _git phải ép locale C cho subprocess git (guard trên mọi máy, kể cả CI tiếng Anh) ──
_seen = {}
_orig_run = gb.subprocess.run
def _spy_run(cmd, **kw):
    _seen["env"] = kw.get("env")
    return _orig_run(cmd, **kw)
gb.subprocess.run = _spy_run
try:
    gb._git(tempfile.gettempdir(), "version")
finally:
    gb.subprocess.run = _orig_run
env = _seen.get("env")
check("_git truyền env riêng cho subprocess", isinstance(env, dict))
check("_git ép LC_ALL=C", bool(env) and env.get("LC_ALL") == "C")
check("_git ép LANG=C", bool(env) and env.get("LANG") == "C")
check("_git ép LANGUAGE=C", bool(env) and env.get("LANGUAGE") == "C")
# Đo THẬT: env tiến trình app trước và sau lời gọi phải y hệt (bản cũ ghi `... or True`, luôn đúng).
_truoc = {k: os.environ.get(k) for k in ("LC_ALL", "LANG", "LANGUAGE")}
gb._git(tempfile.gettempdir(), "version")
check("app KHÔNG bị đổi locale (chỉ subprocess)",
      {k: os.environ.get(k) for k in ("LC_ALL", "LANG", "LANGUAGE")} == _truoc)

# ── 2. E2E: bootstrap vào bare repo RỖNG dưới env locale tiếng Việt ──
TMP = Path(tempfile.mkdtemp(prefix="jv-bootloc-")).resolve()
REMOTE = TMP / "remote.git"
subprocess.run(["git", "init", "--bare", str(REMOTE)], capture_output=True)
URL = "file:///" + str(REMOTE).replace("\\", "/").lstrip("/")
TOKEN = "x"  # file:// không dùng token nhưng sync_brains yêu cầu non-empty

brains = TMP / "brains"; mirror = TMP / "mirror"; trash = TMP / "trash"
(brains / "Brain A").mkdir(parents=True)
(brains / "Brain A" / "note.md").write_text("xin chào", encoding="utf-8")

# Mô phỏng máy tiếng Việt: LANG + LANGUAGE trỏ vi, LC_ALL bỏ trống (đúng điều kiện bug:
# LC_ALL đặt sẵn giá trị khác lại làm libintl macOS BỎ QUA AppleLanguages - thành ra không
# tái hiện được). Restore trong finally để phần sau của test không chạy dưới env giả.
_cu = {k: os.environ.get(k) for k in ("LANG", "LANGUAGE", "LC_ALL")}
os.environ["LANG"] = "vi_VN.UTF-8"
os.environ["LANGUAGE"] = "vi_VN.UTF-8:vi"
os.environ.pop("LC_ALL", None)
try:
    r1 = gb.sync_brains(str(brains), str(mirror), URL, TOKEN, "main",
                        trash_dir=str(trash), protected_names={"Brain Default"})
finally:
    for k, v in _cu.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v

check("bootstrap repo rỗng: ok", bool(r1.get("ok")))
check("bootstrap repo rỗng: đã push", bool(r1.get("pushed")))
check("bootstrap repo rỗng: không error", not r1.get("error"))
ref = gb._git(str(REMOTE), "rev-parse", "refs/heads/main")
check("remote có branch main sau bootstrap", ref.returncode == 0 and len(ref.stdout.strip()) == 40)
tree = gb._git(str(REMOTE), "ls-tree", "-r", "--name-only", "main")
check("file brain nằm trong tree remote", "Brain A/note.md" in (tree.stdout or ""))
head = gb._git(str(mirror), "rev-parse", "HEAD")
check("mirror HEAD khớp remote main", head.stdout.strip() == ref.stdout.strip())

# ── 3. Đường cũ không vỡ: sync lần 2 (remote ĐÃ có ref main) vẫn ok ──
(brains / "Brain A" / "note2.md").write_text("lần hai", encoding="utf-8")
r2 = gb.sync_brains(str(brains), str(mirror), URL, TOKEN, "main",
                    trash_dir=str(trash), protected_names={"Brain Default"})
check("sync lần 2 (remote có ref): ok + push", bool(r2.get("ok")) and bool(r2.get("pushed")))
tree2 = gb._git(str(REMOTE), "ls-tree", "-r", "--name-only", "main")
check("file mới lên remote ở lần 2", "Brain A/note2.md" in (tree2.stdout or ""))

print(); print("TẤT CẢ PASS" if not _fails else f"{len(_fails)} FAIL: {_fails}")
sys.exit(1 if _fails else 0)
