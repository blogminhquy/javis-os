"""Bí mật và dữ liệu chạy không được lọt vào git lẫn image Docker.

    python tests/run.py ignore_files     (KHÔNG mạng)

Bối cảnh 0.9.241: `Dockerfile:64` là `COPY . .` nên `.dockerignore` là hàng rào DUY NHẤT,
mà nó đã trôi thành bản sao cũ và yếu hơn `.gitignore` nhiều: thiếu `.secret_key`,
`.hub_token`, `.oauth_mcp.json`, `plugins/`, `connector-home/` và mọi file `.db`. Bất kỳ ai
`docker build` cục bộ đều nướng khoá bí mật của chính mình vào image. Build trên GHCR chạy
từ checkout sạch nên không dính - đó là lý do lỗi này sống lâu mà không ai thấy.

Kèm một bẫy riêng của Docker: pattern khớp từ GỐC context chứ KHÔNG tự khớp ở mọi độ sâu
như .gitignore, nên `.staging/` trần không loại được `server/.staging` (114MB). Muốn khớp
mọi độ sâu phải viết `**/`.

LƯU Ý về mức tin cậy: phần .gitignore được kiểm bằng chính `git check-ignore` nên là
CHÂN LÝ. Phần .dockerignore kiểm bằng một bản mô phỏng luật khớp của Docker viết trong file
này - nó bám theo tài liệu (khớp theo từng đoạn, `**` nuốt số đoạn bất kỳ, khớp cả thư mục
cha), nhưng vẫn là MÔ PHỎNG. Giá trị chính của nó là khoá cứng cái bẫy `**/` ở trên.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import fnmatch
import os
import subprocess
import sys
from pathlib import Path


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---------------------------------------------------------------- mô phỏng luật Docker
def _khop_doan(pdoan, fdoan) -> bool:
    if not pdoan:
        return not fdoan
    if pdoan[0] == "**":
        return any(_khop_doan(pdoan[1:], fdoan[i:]) for i in range(len(fdoan) + 1))
    if not fdoan:
        return False
    if not fnmatch.fnmatchcase(fdoan[0], pdoan[0]):
        return False
    return _khop_doan(pdoan[1:], fdoan[1:])


def docker_loai(path: str, patterns: list) -> bool:
    """True nếu Docker sẽ loại path này. Khớp cả khi pattern trúng một thư mục CHA."""
    fdoan = path.split("/")
    for raw in patterns:
        p = raw.strip()
        if not p or p.startswith("#"):
            continue
        pdoan = p.rstrip("/").split("/")
        if any(_khop_doan(pdoan, fdoan[:k]) for k in range(1, len(fdoan) + 1)):
            return True
    return False


DOCKERIGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8").split("\n")

# ---------------------------------------------------------------- 1. Mô phỏng phải đúng
# Tự kiểm bản mô phỏng trước khi dùng nó kết luận điều gì.
check("mô phỏng: pattern trần chỉ khớp gốc, KHÔNG khớp thư mục con",
      docker_loai(".staging/x", [".staging"]) and not docker_loai("server/.staging/x", [".staging"]))
check("mô phỏng: '**/' khớp mọi độ sâu kể cả gốc",
      docker_loai("server/.staging/x", ["**/.staging"]) and docker_loai(".staging/x", ["**/.staging"]))
check("mô phỏng: đường dẫn ghi rõ thì khớp đúng chỗ đó",
      docker_loai("server/.secret_key", ["server/.secret_key"])
      and not docker_loai("other/.secret_key", ["server/.secret_key"]))
check("mô phỏng: ký tự đại diện hoạt động",
      docker_loai("server/usage_index.db-wal", ["server/usage_index.db*"]))
check("mô phỏng: không loại nhầm mã nguồn",
      not docker_loai("server/main.py", DOCKERIGNORE)
      and not docker_loai("dashboard/console.js", DOCKERIGNORE)
      and not docker_loai("system/plugins/datetime-vn/plugin.py", DOCKERIGNORE))

# ---------------------------------------------------------------- 2. Bí mật + trạng thái
NHAY_CAM = [
    "server/.secret_key", "server/.hub_token", "server/.oauth_mcp.json",
    "server/.sessions.json", "server/settings.json", "server/mcp_servers.json",
    "server/.mcp_hub_auto.json", "server/mcp_audit.jsonl", ".env",
]
CHAY = [
    "server/conversations.db", "server/usage_index.db", "server/session_brain.db",
    "server/kanban.sqlite3", "server/tg_brain.json", "server/update_state.json",
    "server/logs/x.jsonl", "server/brain-trash/x/y.md", "server/plugins/p/plugin.py",
    "server/connector-home/x", "server/usage.json", "server/javis.log",
    "server/tools/javis-zalo/node_modules/javis-zalo/src/index.js",
]
NANG = [
    "server/brains-backup/.git/objects/x", "server/.staging/sach.txt", ".staging/x",
    ".learn/hermes/cli.py", ".gitnexus/index.db", "videos/a.mp4", "brains/Brain Default/n.md",
]

for nhom, ten in ((NHAY_CAM, "bí mật"), (CHAY, "trạng thái chạy"), (NANG, "dữ liệu nặng")):
    sot = [p for p in nhom if not docker_loai(p, DOCKERIGNORE)]
    check(f"Docker loại hết {len(nhom)} đường dẫn {ten}" + (f" (SÓT: {sot})" if sot else ""), not sot)

# ---------------------------------------------------------------- 3. git: dùng git thật
def git_ignore(p: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT,
                          capture_output=True).returncode == 0


sot_git = [p for p in NHAY_CAM + CHAY + NANG if not git_ignore(p)]
check(f"git bỏ qua hết {len(NHAY_CAM + CHAY + NANG)} đường dẫn trên"
      + (f" (SÓT: {sot_git})" if sot_git else ""), not sot_git)


# Quy tắc phải nằm trong .gitignore ĐÃ COMMIT, không phải .git/info/exclude của một máy.
# info/exclude không đi theo repo, nên thứ chỉ được che ở đó sẽ hiện ra untracked với mọi
# người clone mới hoặc fork. Đúng lỗi này: .gitnexus/ (106MB index) chỉ nằm trong
# info/exclude nên test xanh trên máy dev mà đỏ trên CI - đó là cách nó bị phát hiện.
def nguon_ignore(p: str) -> str:
    r = subprocess.run(["git", "check-ignore", "-v", p], cwd=ROOT, capture_output=True, text=True)
    return (r.stdout.split("\t")[0] if r.stdout else "")


DEV_ARTIFACT = [".gitnexus/index.db", ".superpowers/sdd/x.diff", ".claude/worktrees/x/y",
                ".learn/hermes/cli.py"]
chi_cuc_bo = [p for p in DEV_ARTIFACT if "info/exclude" in nguon_ignore(p) or not nguon_ignore(p)]
check("artifact dev được che bởi .gitignore đã commit, không phải info/exclude cục bộ"
      + (f" (CHỈ CỤC BỘ: {chi_cuc_bo})" if chi_cuc_bo else ""), not chi_cuc_bo)

# ---------------------------------------------------------------- 4. Không có gì lọt hai lưới
# Artifact đang tồn tại trên đĩa mà KHÔNG track và cũng KHÔNG ignore -> `git add -A` là commit.
lot = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                     cwd=ROOT, capture_output=True, text=True).stdout
chua_theo_doi = [l[3:].strip().strip('"') for l in lot.split("\n") if l.startswith("??")]
dang_ngo = [p for p in chua_theo_doi
            if not p.startswith("docs/")          # tài liệu người dùng tự viết, chờ commit
            and Path(p).suffix not in (".md",)]
check("không artifact chạy nào vừa không track vừa không ignore"
      + (f" ({dang_ngo[:5]})" if dang_ngo else ""), not dang_ngo)

# ---------------------------------------------------------------- 5. Không có gì NHẠY CẢM bị track
theo_doi = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout
xau = [f for f in theo_doi.split("\n")
       if f.endswith((".secret_key", ".hub_token", "conversations.db", "settings.json"))
       or f in ("server/mcp_servers.json", ".env")]
check("không file bí mật nào đang bị git theo dõi" + (f" ({xau})" if xau else ""), not xau)

# ---------------------------------------------------------------- 6. Mã nguồn cần thiết KHÔNG bị loại
CAN_CO = [
    "server/main.py", "server/fastyaml.py", "dashboard/index.html", "dashboard/console.js",
    "system/mcp-catalog.json", "system/plugins/datetime-vn/plugin.yaml",
    "requirements.txt", "CLAUDE.md", "VERSION", ".claude/skills",
]
mat = [p for p in CAN_CO if docker_loai(p, DOCKERIGNORE)]
check("mã nguồn + tầng hệ thống vẫn vào được image" + (f" (BỊ LOẠI: {mat})" if mat else ""),
      not mat)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
