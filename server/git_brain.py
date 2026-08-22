"""
git_brain.py - Lớp an toàn dữ liệu cho engine tự học (learn.py / self_improve.py).

Vì sao tồn tại: mọi cơ chế rollback của việc học (snapshot / undo / diff-scope) dựa trên
brain là 1 git repo. NHƯNG mặc định Docker mount `javis-brains:/brains` là named volume
KHÔNG có git (backup git chỉ là bước thủ công comment trong docker-compose). Do đó:

  - Fail-closed: write-mode học CHỈ chạy khi brain là git checkout (is_git_checkout).
    ensure_git_repo() được gọi lúc BẬT học để git-init + commit nền.
  - KHÔNG `git add -A` (tránh commit state bẩn / secret lọt redaction) → chỉ add đúng path
    engine vừa ghi (commit_paths).
  - undo = git revert commit học cuối (revert_last_learn).
  - BrainLock: khoá cấp file (cross-platform) mà MỌI đường ghi (learn worker, curator,
    /reflect, và script backup ngoài nếu hợp tác) phải giành → serialize snapshot→ghi→commit,
    chống đua với tiến trình backup ngoài (asyncio.Lock không bảo vệ được tiến trình khác).

Stdlib-only. Không thêm dependency.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional

# Commit ĐÁNG coi là "học" (hiện ở review + undo được). Baseline dùng "chore:" nên KHÔNG
# lọt vào đây → bấm undo khi chưa học gì sẽ báo "không có commit học" thay vì lỡ revert baseline.
# /reflect ghi qua engine nên commit là "learn:" (không phải "reflect:").
LEARN_COMMIT_PREFIXES = ("learn:", "curator:")


def _no_window():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def has_git() -> bool:
    return shutil.which("git") is not None


def _git(root: str, *args, timeout: int = 30) -> subprocess.CompletedProcess:
    """Chạy git trong <root>. KHÔNG raise; caller đọc returncode/stdout."""
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=_no_window(),
    )


def is_git_checkout(root: str) -> bool:
    """root có phải git repo (có .git)?"""
    try:
        if not (Path(root) / ".git").exists():
            return False
        r = _git(root, "rev-parse", "--is-inside-work-tree")
        return r.returncode == 0 and "true" in (r.stdout or "").lower()
    except Exception:
        return False


# ============================================================
# GIT CHỈ GIỮ CHỮ, KHÔNG GIỮ MEDIA
#
# Vì sao đây là luật cứng chứ không phải một tuỳ chọn: git được thiết kế để NHỚ MÃI MÃI. Mỗi
# lần commit, nội dung file thành một blob nằm vĩnh viễn trong `.git/objects`; xoá file về sau
# chỉ ghi thêm một dòng "từ đây không còn file này", còn blob vẫn phải giữ để quay ngược về
# commit cũ được. `git gc` cũng không đòi lại được, vì blob đó vẫn có chủ là commit cũ.
#
# Với CHỮ thì tính chất đó là ưu điểm: git nén và lưu chênh lệch giữa các phiên bản, nên một
# file .md sửa nhiều lượt gộp lại còn nhẹ hơn cả bản gốc. Với MEDIA thì ngược hẳn: mp4/jpg đã
# nén sẵn bằng codec nên git không nén thêm được và cũng không tìm ra điểm giống nhau giữa hai
# bản render, mỗi lượt xuất lại là thêm nguyên một cục vào kho, vĩnh viễn. Một brain có vài
# trăm MB media và thói quen render vài lượt mỗi clip sẽ đẩy repo lên nhiều GB trong ít tháng,
# clone về máy mới phải tải cả những bản render đã bỏ từ lâu, và cách duy nhất rút xuống là
# viết lại toàn bộ lịch sử - việc đó đổi mã băm mọi commit nên mọi bản sao ở máy khác thành
# không tương thích. Với Javis đang đồng bộ hai chiều nhiều máy thì đó là thảm hoạ chứ không
# phải thao tác bảo trì. Nên cách đúng là ngay từ đầu đừng cho media vào git.
#
# Media vẫn nằm nguyên trên đĩa và vẫn dùng được bình thường; chỉ là nó không đi vào lịch sử
# git. Muốn có bản sao media thì dùng thứ lưu theo TRẠNG THÁI HIỆN TẠI (Drive, ổ ngoài) - xoá
# là mất thật và đòi lại được dung lượng thật.
# ============================================================

# Đuôi file được phép đi vào git: chữ, và chỉ chữ. Danh sách CHO PHÉP chứ không phải danh sách
# cấm - định dạng media mới ra đời thì tự động nằm ngoài, khỏi phải chạy theo vá.
TEXT_EXTS = {
    # tri thức
    ".md", ".markdown", ".txt", ".rst", ".org",
    # trang và dữ liệu có cấu trúc
    ".html", ".htm", ".css", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".xml", ".ini", ".cfg", ".env-example",
    # Obsidian
    ".canvas", ".base",
    # script trong Javis/scripts + plugin
    ".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".bat", ".ps1", ".sql",
    # ảnh vector: là CHỮ, git nén và so sánh được, dung lượng cỡ một trang văn bản
    ".svg",
}

# File không có đuôi nhưng vẫn là chữ và vẫn cần giữ.
TEXT_NAMES = {".gitignore", ".gitattributes", "LICENSE", "README", "CNAME", "Makefile"}


def la_file_chu(rel_or_name: str) -> bool:
    """File này có được vào git không. Dùng chung cho .gitignore lẫn bước chụp sang mirror,
    để hai đường KHÔNG BAO GIỜ nói khác nhau về cùng một file."""
    name = str(rel_or_name or "").replace("\\", "/").rsplit("/", 1)[-1]
    if name in TEXT_NAMES:
        return True
    i = name.rfind(".")
    return i > 0 and name[i:].lower() in TEXT_EXTS


_GI_MO = "# >>> javis giữ khối này, đừng sửa bên trong"
_GI_DONG = "# <<< hết khối của javis - viết luật riêng của bạn ở DƯỚI dòng này"

# Thứ tự trong khối là thứ tự CÓ NGHĨA với git: luật đứng sau thắng luật đứng trước. Chặn hết
# trước, mở lại cho chữ, rồi mới chặn lần nữa mấy thư mục không được vào kể cả khi là chữ.
# Đảo thứ tự này là log thô (có thể chứa secret) lọt vào git dưới dạng .json.
_GITIGNORE_BODY = (
    ["# Javis chỉ đưa CHỮ vào git, không đưa media. Lý do dài nằm ở server/git_brain.py;",
     "# nói gọn: git nhớ mãi mãi, nên một file video commit vào là nằm đó vĩnh viễn, xoá về",
     "# sau cũng không đòi lại được dung lượng. Media vẫn nằm nguyên trên đĩa, chỉ là không",
     "# đi vào lịch sử git.",
     "",
     "# 1. Chặn tất cả...",
     "*",
     "# 2. ...trừ thư mục (để git còn đi vào được) và các đuôi file là CHỮ:",
     "!*/"]
    + [f"!*{e}" for e in sorted(TEXT_EXTS)]
    + [f"!{n}" for n in sorted(TEXT_NAMES)]
    + ["",
       "# 3. Và chặn lần nữa những thứ không được vào kể cả khi là chữ: khoá, log thô (có thể",
       "#    chứa secret), nhật ký nền, hội thoại chưa chưng cất.",
       ".javis-learn.lock",
       "Javis/learn-staging/",
       "Javis/learn-log/",
       "Javis/loop-log/",
       "Javis/skill-usage.json",
       "memory/conversations/",
       "Memory/conversations/",
       "# Nhật ký thô từng lượt chạy agent (memory/agents/<slug>/runs/) cùng loại với",
       "# loop-log: nguyên liệu chưa chưng cất, mỗi bước workflow đẻ thêm - không vào git.",
       "# MEMORY.md của agent (tri thức đã chưng) thì VẪN vào.",
       "memory/agents/*/runs/",
       "Memory/agents/*/runs/",
       ".javis-agy/",
       "# Cấu hình MCP của hai engine CLI Google - chứa hub token của Javis, không phải tri thức.",
       ".agents/mcp_config.json",
       ".antigravity/",
       ".antigravitycli/",
       ".gemini/",
       "*.tmp",
       "# Vùng cache media: ảnh sinh ra + file user gửi lên. Là NGUYÊN LIỆU đi qua, không phải",
       "# tri thức, và media_gc.py tự dọn theo hạn. Bốn dòng attachments vì tên thư mục có thể",
       "# là attachments / Attachments / 05 - attachments (git phân biệt hoa thường trên Linux,",
       "# còn dấu * phủ mọi tiền tố số thứ tự).",
       "attachments/",
       "Attachments/",
       "*attachments/",
       "*Attachments/",
       "inbox/"]
)

_GITIGNORE = "\n".join([_GI_MO] + _GITIGNORE_BODY + [_GI_DONG]) + "\n"

# Mọi dòng mà các bản template TRƯỚC ĐÂY từng ghi ra. Dọn đúng những dòng này khi nâng cấp một
# brain cũ, để chúng không nằm lẫn ngoài khối rồi phá thứ tự luật ở trên.
_GITIGNORE_CU = {
    "# Javis brain - KHÔNG commit: khoá, log thô (có thể chứa secret), nhật ký nền.",
    "# Git chỉ version TRI THỨC ĐÃ CHƯNG CẤT (facts/wiki/skills/MEMORY.md) → undo sạch, an toàn.",
    ".javis-learn.lock", "Javis/learn-staging/", "Javis/learn-log/", "Javis/loop-log/",
    "Javis/skill-usage.json", "memory/conversations/", "Memory/conversations/", "*.tmp",
    "# Vùng cache media: ảnh sinh ra + file user gửi lên. Là NGUYÊN LIỆU đi qua, không phải",
    "# tri thức, và media_gc.py tự dọn theo hạn. Nếu commit thì mỗi tấm ảnh là một blob nằm",
    "# vĩnh viễn trong lịch sử git - xoá file về sau cũng không lấy lại được dung lượng.",
    "# Bốn dòng attachments vì tên thư mục có thể là attachments / Attachments / 05 - attachments",
    "# (git phân biệt hoa thường trên Linux, còn dấu * phủ mọi tiền tố số thứ tự).",
    "attachments/", "Attachments/", "*attachments/", "*Attachments/", "inbox/",
}


def _ensure_gitignore_lines(root) -> bool:
    """Ghi lại KHỐI CỦA JAVIS trong <root>/.gitignore, giữ nguyên mọi dòng user tự thêm.

    Vì sao phải ghi cả khối chứ không chỉ thêm dòng thiếu như bản trước: luật allowlist chỉ
    đúng khi ĐÚNG THỨ TỰ (chặn hết → mở cho chữ → chặn lại mấy thư mục cấm). Bản trước nối
    thêm vào cuối file, nên với một brain cũ thì mấy dòng "chặn lại" nằm TRƯỚC dòng "mở cho
    chữ" và git sẽ hiểu ngược: `Javis/learn-log/*.json` được mở lại. Log thô có thể chứa
    secret, nên đó không phải lỗi thẩm mỹ.

    Khối của Javis đứng TRƯỚC phần của user để user còn viết ngoại lệ đè lên được.
    Trả True nếu file có thay đổi.
    """
    try:
        gi = Path(root) / ".gitignore"
        cur = gi.read_text(encoding="utf-8") if gi.exists() else ""
        rieng = []
        trong_khoi = False
        for dong in cur.splitlines():
            s = dong.strip()
            if s == _GI_MO:
                trong_khoi = True
                continue
            if s == _GI_DONG:
                trong_khoi = False
                continue
            if trong_khoi or s in _GITIGNORE_CU:
                continue          # khối cũ của Javis: bỏ đi, lát nữa ghi lại bản mới
            rieng.append(dong)
        # Bỏ dòng trống thừa ở đầu/cuối phần của user cho file khỏi loang ra sau mỗi lần ghi.
        while rieng and not rieng[0].strip():
            rieng.pop(0)
        while rieng and not rieng[-1].strip():
            rieng.pop()
        moi = _GITIGNORE + (("\n" + "\n".join(rieng) + "\n") if rieng else "")
        if moi == cur:
            return False
        # newline="\n": KHÔNG để Python dịch \n -> os.linesep (CRLF trên Windows). Máy nào chạy
        # core.autocrlf=false thì ghi CRLF lên một file đã commit dạng LF sẽ đẻ diff đổi
        # line-ending TOÀN FILE thay vì đúng phần vừa sửa.
        gi.write_text(moi, encoding="utf-8", newline="\n")
        return True
    except Exception as e:
        print(f"[gitignore] {root}: {type(e).__name__}: {e}", file=__import__('sys').stderr)
        return False


# Cùng luật nhận diện thư mục attachments với media_gc.py và image_gen.py:40.
_ATTACH_RE = r"^(\d+\s*[-_.]\s*)?attachments$"


def untrack_media(root: str) -> int:
    """Gỡ attachments/ + inbox/ khỏi INDEX git, GIỮ NGUYÊN file trên đĩa.

    Vì sao cần: .gitignore không có tác dụng với file git ĐÃ theo dõi từ trước, nên brain cũ
    (đã lỡ commit ảnh) vẫn tiếp tục commit ảnh mới dù template ignore đã vá. Phải gỡ một lần.

    Hệ quả đã được chấp nhận: commit kế tiếp ghi nhận "đã xoá ảnh", và kéo brain về máy khác
    thì ảnh cũ không đi theo. Blob cũ vẫn nằm trong lịch sử - CỐ Ý không viết lại history.

    Idempotent: brain chưa từng commit media thì không có gì để gỡ, trả 0.
    Trả về số thư mục đã thực sự gỡ.
    """
    n = 0
    try:
        for name in sorted(os.listdir(root)):
            if not os.path.isdir(os.path.join(root, name)):
                continue
            ten = name.strip()
            if ten.lower() != "inbox" and not re.match(_ATTACH_RE, ten, re.IGNORECASE):
                continue
            # Hỏi trước bằng ls-files: không có gì được theo dõi thì khỏi gọi git rm, và
            # quan trọng hơn là khỏi đếm nhầm thư mục vốn đã sạch (giữ tính idempotent).
            r = _git(root, "ls-files", "--", name)
            if not (r.stdout or "").strip():
                continue
            _git(root, "rm", "-r", "--cached", "--ignore-unmatch", "-q", "--", name)
            n += 1
    except Exception as e:
        print(f"[untrack_media] {root}: {type(e).__name__}: {e}", file=__import__('sys').stderr)
    return n


def ensure_git_repo(root: str) -> dict:
    """Biến brain thành git repo nếu chưa (gọi khi BẬT học). Idempotent.
    Trả {ok, created, error}. KHÔNG push (backup là việc user chủ động)."""
    root = str(root)
    if not has_git():
        return {"ok": False, "created": False, "error": "Máy chưa cài git"}
    if is_git_checkout(root):
        # Brain ĐÃ là repo: trước đây return thẳng ở đây nên template .gitignore mới không
        # bao giờ tới được brain cũ. Merge dòng còn thiếu rồi commit riêng bằng prefix
        # 'chore:' - KHÔNG dùng 'learn:'/'curator:' (xem LEARN_COMMIT_PREFIXES dòng 31) để
        # một lần vá .gitignore không bị hiện ở UI Review hay bị revert_last_learn undo.
        #
        # BrainLock CHỈ bọc lúc COMMIT, không bọc lúc merge file:
        #  - commit_paths chạy `git commit` = commit CẢ INDEX, không riêng path nó add. Nếu một
        #    learn/curator đang chạy vừa `git add` file của nó thì commit 'chore:' này sẽ cuốn
        #    luôn tri thức đó vào một commit KHÔNG hiện ở Review và revert_last_learn KHÔNG
        #    undo được - đúng thứ LEARN_COMMIT_PREFIXES sinh ra để chặn. Phải giữ khoá.
        #  - Ngược lại việc GHI .gitignore là vô hại + idempotent, nên cố tình để NGOÀI khoá:
        #    git đọc luật ignore từ WORKING TREE, nên chỉ cần file trên đĩa đúng là sidecar bị
        #    ignore NGAY - mục tiêu task đạt được kể cả khi không giành nổi khoá.
        # Không lấy được khoá -> bỏ qua COMMIT (đúng khuôn learn.py:864-867), KHÔNG bỏ merge.
        # Điều kiện commit vì thế KHÔNG chỉ là "merge vừa đổi": còn commit khi .gitignore đang
        # dirty. Nếu chỉ xét giá trị trả về của _ensure_gitignore_lines thì một lần kẹt khoá sẽ
        # để .gitignore vá trên đĩa mà VĨNH VIỄN không được commit (lần sau merge trả False ->
        # không ai commit nữa), vì ensure_git_repo chỉ chạy lúc bật học / bấm /reflect chứ
        # không chạy mỗi tick. Xét thêm dirty -> lần bấm sau tự lành.
        changed = _ensure_gitignore_lines(root)
        dirty = bool((_git(root, "status", "--porcelain", "--", ".gitignore").stdout or "").strip())
        # untrack_media phải nằm TRONG khoá và NGAY TRƯỚC commit_paths: commit_paths chạy
        # `git commit` = commit CẢ INDEX, nên phần gỡ index chỉ được stage khi chắc chắn có
        # người commit nó ngay sau. Không giành được khoá thì bỏ qua cả hai, lần bấm sau lành.
        # Xét thêm con_theo_doi vì brain nào đã có .gitignore đúng rồi (changed và dirty đều
        # False) mà vẫn đang theo dõi media thì nếu không có nó sẽ MÃI MÃI không được gỡ.
        con_theo_doi = bool((_git(root, "ls-files", "--", "inbox").stdout or "").strip())
        if changed or dirty or con_theo_doi:
            # timeout=1.0 (KHÔNG phải mặc định 30s): ensure_git_repo bị gọi THẲNG, không qua
            # asyncio.to_thread, từ 2 handler async (learn.py /learn/enable + main.py /reflect),
            # mà BrainLock.acquire() chờ bằng time.sleep(0.25) CHẶN. Chờ 30s ở đây = đóng băng
            # CẢ event loop 30s (mọi chat, Telegram poller, scheduler, reminders, mọi brain) -
            # đúng lúc đang tranh chấp, tức đúng lúc hệ đang bận nhất. Chờ lâu cũng vô nghĩa vì
            # nhánh `dirty` ở trên đã tự lành: không giành được thì lần bấm /learn/enable hay
            # /reflect kế tiếp commit nốt. Fail nhanh cho cùng một đảm bảo với giá rẻ hơn nhiều.
            # (Cách khác là bọc asyncio.to_thread như learn.py:764 làm với _promote_sync, nhưng
            # đó là thay đổi lớn hơn và không cần khi thời gian chờ đã bị chặn ~1s.)
            with BrainLock(root, timeout=1.0) as lk:
                if getattr(lk, "acquired", False):
                    untrack_media(root)
                    commit_paths(root, [".gitignore"], "chore: cập nhật .gitignore brain")
        return {"ok": True, "created": False}
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
        r = _git(root, "init")
        if r.returncode != 0:
            return {"ok": False, "created": False, "error": (r.stderr or "git init lỗi")[:200]}
        # Cấu hình identity cục bộ (repo có thể chạy trong container không có global config)
        _git(root, "config", "user.email", "javis@localhost")
        _git(root, "config", "user.name", "Javis Learn")
        _ensure_gitignore_lines(root)   # merge chứ không ghi đè (brain có thể đã có .gitignore)
        _git(root, "add", ".gitignore")
        _git(root, "add", "-A")   # commit NỀN duy nhất được phép add -A (baseline, chưa có state học)
        c = _git(root, "commit", "-m", "chore: baseline brain snapshot (bật tự học)")
        return {"ok": True, "created": True, "commit": (c.stdout or "")[:120]}
    except Exception as e:
        return {"ok": False, "created": False, "error": f"{type(e).__name__}: {e}"}


def working_tree_dirty(root: str) -> bool:
    try:
        r = _git(root, "status", "--porcelain")
        return bool((r.stdout or "").strip())
    except Exception:
        return False


def changed_paths(root: str) -> List[str]:
    """Danh sách path đang thay đổi (chưa commit) - dùng cho diff-scope guard."""
    try:
        r = _git(root, "status", "--porcelain")
        out = []
        for line in (r.stdout or "").splitlines():
            # format: 'XY <path>' hoặc 'XY <old> -> <new>'
            p = line[3:].strip() if len(line) > 3 else ""
            if " -> " in p:
                p = p.split(" -> ", 1)[1]
            if p:
                out.append(p.strip('"'))
        return out
    except Exception:
        return []


def paths_within(paths: List[str], allowed_prefixes: List[str]) -> List[str]:
    """Trả path NGOÀI allowed_prefixes (rỗng = hợp lệ). Prefix so theo dạng posix."""
    bad = []
    norm_allowed = [a.replace("\\", "/").rstrip("/") + "/" for a in allowed_prefixes]
    for p in paths:
        pp = p.replace("\\", "/")
        if not any(pp.startswith(a) or (pp + "/").startswith(a) for a in norm_allowed):
            bad.append(p)
    return bad


def commit_paths(root: str, paths: List[str], msg: str) -> Optional[str]:
    """git add ĐÚNG các path (KHÔNG add -A) rồi commit. Trả commit hash ngắn hoặc None.
    An toàn: chỉ đưa vào index những gì engine chủ động ghi."""
    try:
        if not paths:
            return None
        add = _git(root, "add", "--", *paths)
        if add.returncode != 0:
            return None
        c = _git(root, "commit", "-m", msg)
        if c.returncode != 0:
            return None
        h = _git(root, "rev-parse", "--short", "HEAD")
        return (h.stdout or "").strip() or "committed"
    except Exception:
        return None


def hard_reset_paths(root: str, paths: List[str]) -> None:
    """Khôi phục các path về HEAD (dùng khi verify/secret-scan fail sau khi lỡ ghi).
    Chỉ checkout đúng path, không đụng phần còn lại."""
    try:
        if paths:
            _git(root, "checkout", "HEAD", "--", *paths)
            _git(root, "clean", "-fd", "--", *paths)
    except Exception:
        pass


def list_learn_commits(root: str, n: int = 20) -> List[dict]:
    """Liệt kê commit học gần nhất (prefix learn:/curator:/reflect:) + file đổi - cho Review UI."""
    if not is_git_checkout(root):
        return []
    try:
        r = _git(root, "log", "-n", str(n * 3), "--pretty=format:%h\x1f%ct\x1f%s", "--name-only")
        out: List[dict] = []
        blocks = (r.stdout or "").split("\n\n")
        for blk in blocks:
            lines = [l for l in blk.splitlines() if l.strip()]
            if not lines:
                continue
            head = lines[0].split("\x1f")
            if len(head) < 3:
                continue
            h, ct, subj = head[0], head[1], head[2]
            if not any(subj.startswith(p) for p in LEARN_COMMIT_PREFIXES):
                continue
            files = lines[1:]
            out.append({"hash": h, "ts": float(ct or 0), "subject": subj, "files": files})
            if len(out) >= n:
                break
        return out
    except Exception:
        return []


def revert_last_learn(root: str) -> dict:
    """git revert commit HỌC gần nhất (undo 1-click). Trả {ok, reverted, subject, error}."""
    if not is_git_checkout(root):
        return {"ok": False, "error": "Brain chưa phải git repo"}
    try:
        commits = list_learn_commits(root, 1)
        if not commits:
            return {"ok": False, "error": "Không có commit học nào để undo"}
        h = commits[0]["hash"]
        # Chỉ từ chối nếu CHÍNH file trong commit học đó đang bị sửa dở (tránh mất chỉnh tay).
        # File dirty KHÔNG liên quan (conversations/log/note khác) KHÔNG chặn undo.
        target = set(commits[0].get("files") or [])
        overlap = [p for p in changed_paths(root) if p in target]
        if overlap:
            return {"ok": False, "error": f"Các file học đang bị sửa dở, hãy tự xử lý trước: {overlap[:3]}"}
        r = _git(root, "revert", "--no-edit", h)
        if r.returncode != 0:
            _git(root, "revert", "--abort")   # dọn trạng thái revert dở nếu conflict
            return {"ok": False, "error": (r.stderr or "revert lỗi")[:200]}
        return {"ok": True, "reverted": h, "subject": commits[0]["subject"]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ============================================================
# BACKUP lên GitHub (đồng bộ brain lên repo riêng, khôi phục khi mất máy/VPS)
# ============================================================
def _redact(text: str, *secrets: str) -> str:
    """Xoá token khỏi text trước khi trả ra UI/log (git stderr có thể chứa URL kèm token)."""
    out = text or ""
    for s in secrets:
        if s and len(s) >= 6:
            out = out.replace(s, "***")
    return out


def _auth_url(repo_url: str, token: str) -> str:
    """Chèn token vào URL https cho 1 lần push (KHÔNG lưu remote → token không nằm trong .git/config).
    URL scheme khác http(s) (ssh://, git@, file://) để NGUYÊN - dùng key/local, không cần token."""
    u = (repo_url or "").strip()
    if u.startswith(("ssh://", "git@", "file://")):
        return u
    if u.startswith("http://"):
        u = "https://" + u[len("http://"):]
    if not u.startswith("https://"):
        u = "https://" + u
    rest = u[len("https://"):]
    host_part = rest.split("/", 1)[0]
    if "@" in host_part:                       # bỏ cred cũ nếu user dán sẵn
        rest = rest.split("@", 1)[1]
    return f"https://x-access-token:{token}@{rest}"


def remote_reachable(repo_url: str, token: str, timeout: int = 30) -> dict:
    """Kiểm tra token + repo hợp lệ (git ls-remote). Trả {ok, error}. Redact token khỏi lỗi."""
    if not has_git():
        return {"ok": False, "error": "Máy chưa cài git"}
    if not repo_url or not token:
        return {"ok": False, "error": "Thiếu repo URL hoặc token"}
    try:
        r = subprocess.run(["git", "ls-remote", _auth_url(repo_url, token), "HEAD"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=_no_window())
        if r.returncode != 0:
            return {"ok": False, "error": _redact((r.stderr or "không kết nối được").strip()[:250], token)}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": _redact(f"{type(e).__name__}: {e}", token)}


# Path (dạng posix, tương đối) KHÔNG đưa vào backup: git thô của brain (tránh nested-repo),
# hội thoại gốc/log/khoá (có thể chứa secret), file tạm.
_BACKUP_SKIP_DIRS = {".git"}
_BACKUP_SKIP_SUBSTR = ("/memory/conversations/", "/Memory/conversations/",
                       "/Javis/loop-log/", "/Javis/learn-log/", "/Javis/learn-staging/",
                       "/Javis/skill-usage.json/",
                       # File ngữ cảnh Javis ghi tạm cho Antigravity CLI khi prompt dài hơn trần
                       # dòng lệnh. Nó là BẢN SAO của system prompt + MEMORY.md + toàn bộ lịch
                       # sử hội thoại, đuôi .md, nên nếu không chặn ở đây thì nó vừa được chép
                       # sang mirror vừa lọt qua .gitignore (khối 2 mở lại mọi file .md) rồi
                       # được commit và push lên remote sao lưu của người dùng - đúng thứ mà
                       # dòng chặn `Memory/conversations/` ngay trên kia sinh ra để ngăn. Bình
                       # thường file bị xoá ngay cuối lượt, nhưng chỉ cần một lượt đồng bộ chạy
                       # trúng lúc `agy` đang chạy là dính, và git thì giữ blob vĩnh viễn.
                       "/.javis-agy/",
                       # Cấu hình MCP Javis ghi vào brain cho hai engine CLI của Google. Chúng
                       # chứa `Authorization: Bearer <hub token>` và đuôi .json, mà khối 2 của
                       # .gitignore mở lại mọi .json - nên không chặn ở đây là token đi thẳng
                       # lên remote sao lưu của người dùng, và git giữ blob vĩnh viễn. Chặn
                       # ĐÚNG file mcp_config.json chứ không chặn cả `.agents/`: thư mục đó
                       # còn là một trong các chỗ chứa skill của brain, phải được sao lưu.
                       "/.agents/mcp_config.json/",
                       "/.antigravity/", "/.antigravitycli/", "/.gemini/")


def _backup_skip(rel: str) -> bool:
    r = "/" + rel.replace("\\", "/") + "/"
    if any(s in r for s in _BACKUP_SKIP_SUBSTR):
        return True
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    if name == ".javis-learn.lock" or name.endswith(".tmp"):
        return True
    # CHỈ CHỮ mới được sang mirror. Chặn ở đây chứ không trông cả vào .gitignore vì hai việc
    # khác nhau: .gitignore quyết định git COMMIT gì, còn chỗ này quyết định có CHÉP file sang
    # thư mục mirror hay không. Không chặn thì mỗi lượt đồng bộ nhân đôi vài trăm MB media trên
    # đĩa để rồi git bỏ qua hết - tốn chỗ, tốn thời gian chụp, không được gì.
    return not la_file_chu(name)


def _sync_mirror(src: str, mirror: str) -> dict:
    """Đồng bộ src -> mirror: chép file mới/đổi (bỏ .git nested + file nhạy cảm/tạm), xoá file
    thừa trong mirror. Mirror KHÔNG có .git nested nào -> git add -A ở mirror chạy sạch.

    Trả về số file media đã bỏ qua + tổng dung lượng, để chỗ gọi NÓI RA cho người dùng. Bỏ qua
    lặng lẽ thì có ngày ai đó tưởng ảnh của mình đã được sao lưu."""
    src, mirror = Path(src), Path(mirror)
    keep = set()
    bo_qua, bo_qua_bytes = 0, 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in _BACKUP_SKIP_DIRS]
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = str(full.relative_to(src))
            if _backup_skip(rel):
                if not la_file_chu(fn):
                    bo_qua += 1
                    try:
                        bo_qua_bytes += full.stat().st_size
                    except OSError:
                        pass
                continue
            keep.add(rel.replace("\\", "/"))
            dst = mirror / rel
            try:
                if dst.exists() and dst.stat().st_size == full.stat().st_size and \
                        int(dst.stat().st_mtime) >= int(full.stat().st_mtime):
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(full, dst)
            except Exception as e:
                print(f"[backup sync copy] {rel}: {e}", file=__import__('sys').stderr)
    # prune: xoá file trong mirror (trừ .git của mirror) mà src không còn
    for dirpath, dirnames, filenames in os.walk(mirror):
        if ".git" in Path(dirpath).parts:
            continue
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = str(full.relative_to(mirror)).replace("\\", "/")
            if rel not in keep:
                try:
                    full.unlink()
                except Exception:
                    pass
    return {"media_bo_qua": bo_qua, "media_bytes": bo_qua_bytes}


# ============================================================
# ĐỒNG BỘ 2 CHIỀU với GitHub (máy A ⇄ repo ⇄ máy B/VPS)
#
# Thay cơ chế force-push một chiều cũ (2 máy cùng backup sẽ lặng lẽ đè nhau).
# Mỗi lượt sync_brains():
#   1. chụp brains -> mirror (repo git riêng, bỏ .git nested + file nhạy cảm) + commit
#   2. fetch remote; hoà nhập: fast-forward khi được, lệch nhau thì merge
#      - conflict cùng file: BẢN SỬA MỚI HƠN THẮNG (so commit time), bản thua lưu thành
#        <tên>.conflict-<local|remote>-<timestamp> ngay cạnh để người dùng tự quyết
#      - một bên sửa một bên xoá: bản sửa thắng (không mất dữ liệu)
#   3. áp KẾT QUẢ merge ngược về thư mục brains (chỉ đúng các file merge làm đổi,
#      guard mtime: file vừa sinh/sửa trong lúc sync thì không đè/không xoá)
#   4. push THƯỜNG (không force). Bị máy khác chen ngang -> tự fetch/merge/áp lại 1 lần.
# Bất biến an toàn: KHÔNG BAO GIỜ push khi chưa áp xong về máy (áp lỗi -> rollback mirror
# về trước merge rồi báo lỗi) -> mirror không bao giờ chứa dữ liệu remote mà máy chưa có,
# nên bước prune của lần chụp sau không thể biến dữ liệu remote thành "đã xoá".
# ============================================================
import platform
import threading

_SYNC_LOCK = threading.Lock()   # 1 phiên sync mỗi process (nút bấm + scheduler không giẫm nhau)


def _host_tag() -> str:
    """Tên máy ngắn gọn cho commit message / tên file conflict (biết bản nào từ đâu)."""
    try:
        h = (platform.node() or "").strip().lower()
        h = "".join(c if c.isalnum() or c == "-" else "-" for c in h).strip("-")
        return h[:24] or "may"
    except Exception:
        return "may"


def _git_bytes(root: str, *args, timeout: int = 30) -> subprocess.CompletedProcess:
    """git trả stdout BYTES (cho `git show` nội dung file - an toàn với file nhị phân/ảnh)."""
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, timeout=timeout, creationflags=_no_window(),
    )


def _git_lines_z(root: str, *args, timeout: int = 60) -> List[str]:
    """Chạy git với -z (NUL-separated) + quotepath=false → path tiếng Việt trả về NGUYÊN VĂN."""
    r = _git_bytes(root, "-c", "core.quotepath=false", *args, timeout=timeout)
    if r.returncode != 0:
        return []
    return [p.decode("utf-8", "replace") for p in (r.stdout or b"").split(b"\0") if p]


def _last_commit_ts(root: str, ref: str, path: str) -> int:
    try:
        r = _git(root, "log", "-1", "--format=%ct", ref, "--", path)
        return int((r.stdout or "0").strip() or 0)
    except Exception:
        return 0


def _merge_with_policy(root: str) -> dict:
    """Merge FETCH_HEAD vào HEAD của mirror. Conflict xử lý theo chính sách:
    bản có commit MỚI HƠN thắng, bản thua lưu thành file .conflict-* cạnh đó (không mất gì);
    sửa thắng xoá. Trả {merged, conflicts:[{path, winner, saved?}]} hoặc {error}."""
    m = _git(root, "merge", "--no-edit", "FETCH_HEAD", timeout=120)
    if m.returncode != 0 and "unrelated histories" in ((m.stderr or "") + (m.stdout or "")):
        # 2 máy khởi tạo mirror độc lập → lịch sử không chung gốc; merge chéo lần đầu là hợp lệ
        m = _git(root, "merge", "--no-edit", "--allow-unrelated-histories", "FETCH_HEAD", timeout=120)
    if m.returncode == 0:
        return {"merged": True, "conflicts": []}
    # Không phải trạng thái conflict (lỗi khác) → dọn và báo
    if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0:
        _git(root, "merge", "--abort")
        return {"error": "merge lỗi: " + ((m.stderr or m.stdout or "?").strip())[:250]}
    conflicts = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for p in _git_lines_z(root, "diff", "--name-only", "--diff-filter=U", "-z"):
        ours = _git_bytes(root, "show", f":2:{p}")     # stage 2 = bản local
        theirs = _git_bytes(root, "show", f":3:{p}")   # stage 3 = bản remote
        has_o, has_t = ours.returncode == 0, theirs.returncode == 0
        fp = Path(root) / p
        try:
            if has_o and has_t:
                remote_wins = _last_commit_ts(root, "MERGE_HEAD", p) > _last_commit_ts(root, "HEAD", p)
                winner = theirs.stdout if remote_wins else ours.stdout
                loser = ours.stdout if remote_wins else theirs.stdout
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(winner)
                if loser != winner:
                    base, ext = os.path.splitext(p)
                    cpath = f"{base}.conflict-{'local' if remote_wins else 'remote'}-{stamp}{ext or '.md'}"
                    (Path(root) / cpath).write_bytes(loser)
                    _git(root, "add", "--", p, cpath)
                    conflicts.append({"path": p, "winner": "remote" if remote_wins else "local", "saved": cpath})
                else:
                    _git(root, "add", "--", p)
            elif has_o or has_t:
                # một bên xoá, một bên sửa → GIỮ bản sửa (không để sync âm thầm mất dữ liệu)
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes((ours if has_o else theirs).stdout)
                _git(root, "add", "--", p)
                conflicts.append({"path": p, "winner": "local" if has_o else "remote",
                                  "note": "một bên xoá - giữ bản sửa"})
            else:
                _git(root, "rm", "-f", "--", p)
        except Exception as e:
            _git(root, "merge", "--abort")
            return {"error": f"xử lý conflict {p}: {type(e).__name__}: {e}"}
    c = _git(root, "commit", "--no-edit")
    if c.returncode != 0:
        _git(root, "merge", "--abort")
        return {"error": "commit merge lỗi: " + ((c.stderr or "?").strip())[:200]}
    return {"merged": True, "conflicts": conflicts}


def _integrate_remote(root: str, pre_head: Optional[str]) -> dict:
    """Hoà FETCH_HEAD vào mirror: chưa có commit local → nhận nguyên bản remote (khôi phục);
    remote đã nằm trong local → thôi; local nằm trong remote → fast-forward; lệch → merge policy."""
    if pre_head is None:
        r = _git(root, "reset", "--hard", "FETCH_HEAD")
        if r.returncode != 0:   # nhánh chưa sinh (repo rỗng) trên vài bản git → fallback checkout
            r = _git(root, "checkout", "-f", "-B", "javis-sync", "FETCH_HEAD")
            if r.returncode != 0:
                return {"error": "nhận bản remote lỗi: " + ((r.stderr or "?").strip())[:200]}
        return {"merged": True, "conflicts": []}
    head = (_git(root, "rev-parse", "HEAD").stdout or "").strip()
    fh = (_git(root, "rev-parse", "FETCH_HEAD").stdout or "").strip()
    if head == fh or _git(root, "merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD").returncode == 0:
        return {"merged": False, "conflicts": []}
    if _git(root, "merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD").returncode == 0:
        r = _git(root, "merge", "--ff-only", "FETCH_HEAD")
        if r.returncode != 0:
            return {"error": "fast-forward lỗi: " + ((r.stderr or "?").strip())[:200]}
        return {"merged": True, "conflicts": []}
    return _merge_with_policy(root)


def _changed_by_integration(root: str, pre_head: Optional[str]) -> set:
    """Các path mà bước hoà-nhập remote LÀM ĐỔI trong mirror (so pre_head..HEAD).
    Đây chính là danh sách cần áp ngược về brains - không đoán mò bằng mtime."""
    if _git(root, "rev-parse", "-q", "--verify", "HEAD").returncode != 0:
        return set()
    if pre_head is None:
        return set(_git_lines_z(root, "ls-tree", "-r", "--name-only", "-z", "HEAD"))
    return set(_git_lines_z(root, "diff", "--name-only", "-z", pre_head, "HEAD"))


def _apply_back(mirror: str, brains_dir: str, changed: set, sync_start: float) -> dict:
    """Áp các path `changed` (kết quả hoà nhập remote) từ mirror về brains_dir.
    - Copy nguyên tử (tmp + os.replace). File local vừa đổi TRONG lúc sync (mtime >= sync_start)
      thì không đè/không xoá - local thắng, vòng sau tự hoà tiếp.
    - Giữ BrainLock từng brain trong lúc áp để không giẫm engine học; không lấy được lock
      trong 30s vẫn áp (lock học chỉ giữ vài giây - kẹt lâu nghĩa là tiến trình chết)."""
    mirror, brains = Path(mirror), Path(brains_dir)
    rep = {"applied": 0, "deleted": 0, "failed": [], "applied_sample": [], "deleted_sample": []}
    todo = [p for p in sorted(changed) if p and not _backup_skip(p)]
    if not todo:
        return rep
    locks = []
    for top in sorted({p.split("/", 1)[0] for p in todo if "/" in p}):
        d = brains / top
        if d.is_dir():
            lk = BrainLock(str(d), timeout=30)
            if lk.acquire():
                locks.append(lk)
            else:
                print(f"[sync apply] không lấy được lock {top} sau 30s - vẫn áp tiếp",
                      file=__import__('sys').stderr)
    try:
        for rel in todo:
            src, dst = mirror / rel, brains / rel
            try:
                if src.is_file():
                    if dst.exists() and dst.stat().st_mtime >= sync_start:
                        continue   # local vừa sửa trong lúc sync → local thắng vòng này
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    # đuôi .tmp → nằm trong _backup_skip: crash giữa chừng không sinh rác vào backup
                    tmp = dst.parent / (dst.name + ".javis-sync.tmp")
                    shutil.copy2(src, tmp)
                    os.replace(tmp, dst)
                    rep["applied"] += 1
                    if len(rep["applied_sample"]) < 20:
                        rep["applied_sample"].append(rel)
                elif dst.is_file():
                    if dst.stat().st_mtime >= sync_start:
                        continue   # file vừa sinh/sửa local → không xoá
                    dst.unlink()
                    rep["deleted"] += 1
                    if len(rep["deleted_sample"]) < 20:
                        rep["deleted_sample"].append(rel)
            except Exception as e:
                rep["failed"].append(rel)
                print(f"[sync apply] {rel}: {type(e).__name__}: {e}", file=__import__('sys').stderr)
    finally:
        for lk in locks:
            lk.release()
    return rep


def _rollback_mirror(root: str, pre_head: Optional[str]) -> None:
    """Đưa mirror về trạng thái TRƯỚC khi hoà remote (dùng khi áp về máy thất bại) →
    không push, remote còn nguyên dữ liệu, vòng sau fetch/merge/áp lại từ đầu."""
    try:
        if pre_head:
            _git(root, "reset", "--hard", pre_head)
        else:
            br = (_git(root, "symbolic-ref", "--short", "HEAD").stdout or "").strip()
            if br:
                _git(root, "update-ref", "-d", f"refs/heads/{br}")
    except Exception:
        pass


def _brains_has_content(brains_dir: str) -> bool:
    """brains có file NÀO đáng backup không. Trống (máy mới/volume mới) → chế độ KHÔI PHỤC:
    không chụp snapshot (tránh ghi nhận 'xoá sạch' rồi đẩy lên đè mất backup)."""
    for dirpath, dirnames, filenames in os.walk(brains_dir):
        dirnames[:] = [d for d in dirnames if d not in _BACKUP_SKIP_DIRS]
        for fn in filenames:
            rel = str((Path(dirpath) / fn).relative_to(brains_dir))
            if not _backup_skip(rel):
                return True
    return False


def _restore_missing_brains(brains_dir: str, mirror_dir: str, protected_names) -> None:
    """Bảo vệ mặc định 'xóa không thắng' (bổ sung cho _apply_tombstones ngay dưới đây): não là
    con TRỰC TIẾP của mirror_dir (đã biết từ lần sync trước) mà giờ THIẾU khỏi brains_dir và
    KHÔNG có tombstone hợp lệ trong brains_dir (xóa tay ngoài ý muốn, crash, volume lỗi...) thì
    khôi phục NGAY từ mirror về brains_dir - PHẢI chạy TRƯỚC bước _sync_mirror() chụp snapshot ở
    _sync_brains_locked, vì bước đó coi MỌI thứ thiếu trong brains là xóa có chủ đích rồi commit
    + đẩy đi mất - lúc đó thông tin não từng tồn tại KHÔNG còn cách nào lấy lại. Chỉ tombstone
    thật (đọc + xử lý ở _apply_tombstones, chạy SAU trong CÙNG lượt sync này) mới được làm não
    biến mất vĩnh viễn; não mặc định (protected_names) luôn được khôi phục bất kể tombstone."""
    if not is_git_checkout(mirror_dir):
        return
    protected = set(protected_names or ())
    tomb_names = {t.get("name") for t in _read_tombstones(brains_dir)}
    mp = Path(mirror_dir)
    for child in mp.iterdir():
        name = child.name
        if not child.is_dir() or name in (".git", TOMBSTONE_DIR):
            continue
        if name in tomb_names and name not in protected:
            continue   # có tombstone hợp lệ -> để _apply_tombstones xử lý xóa, không khôi phục oan
        bp = Path(brains_dir) / name
        if bp.exists():
            continue
        try:
            shutil.copytree(str(child), str(bp))
        except Exception as e:
            print(f"[sync restore] {name}: {type(e).__name__}: {e}", file=__import__('sys').stderr)


def _apply_tombstones(brains_dir: str, mirror_dir: str, trash_dir: str,
                      protected_names) -> dict:
    """Áp giấy báo tử: xóa DỨT KHOÁT các não có tombstone (ghi đè chính sách 'xóa không thắng'),
    chỉ cho lần xóa cố ý. Đọc tombstone từ MIRROR sau hoà nhập (= union mọi máy).
    - Chốt thời gian: não còn sống mà có file mtime > deleted_at -> dựng/sửa lại có chủ đích ->
      BỎ QUA + gỡ tombstone (superseded, propagate việc gỡ).
    - Xóa: brains_dir/<name> -> thùng rác; mirror/<name> -> git rm -r (stage) để đẩy đi.
    - An toàn: bỏ qua não mặc định (protected_names) + tên phải là con TRỰC TIẾP của brains_dir.
    Trả {deleted, superseded, failed}."""
    rep = {"deleted": [], "superseded": [], "failed": []}
    protected = set(protected_names or ())
    tombs = _read_tombstones(mirror_dir)
    if not tombs:
        return rep
    base = Path(brains_dir).resolve()
    changed_mirror = False
    for t in tombs:
        name = t.get("name") or ""
        deleted_at = int(t.get("deleted_at", 0))
        if not name or name in protected:
            continue
        bp = Path(brains_dir) / name
        mp = Path(mirror_dir) / name
        try:
            if bp.resolve().parent != base:   # chỉ con trực tiếp của brains_dir
                continue
        except Exception:
            continue
        # Chốt thời gian: dựng lại có chủ đích -> giữ + gỡ tombstone
        if bp.is_dir() and _dir_newer_than(str(bp), deleted_at):
            _git(mirror_dir, "rm", "-f", "--", f"{TOMBSTONE_DIR}/{t['_file']}")
            try:
                (Path(brains_dir) / TOMBSTONE_DIR / t["_file"]).unlink()
            except Exception:
                pass
            changed_mirror = True
            rep["superseded"].append(name)
            continue
        # Xóa dứt khoát
        ok = True
        if bp.is_dir():
            try:
                move_to_trash(str(bp), trash_dir, name)
            except Exception as e:
                ok = False
                print(f"[tombstone] move trash {name}: {type(e).__name__}: {e}",
                      file=__import__('sys').stderr)
        if ok and mp.exists():
            # --ignore-unmatch: máy CHỦ (vừa tự xóa não rồi mới sync) đã prune Foo khỏi git qua
            # commit "backup:" đầu vòng sync (_sync_mirror), nên mirror/<name> có thể còn là thư
            # mục RỖNG trên đĩa (mp.exists() = True) nhưng KHÔNG còn gì được git track bên dưới ->
            # `git rm` không -ignore-unmatch sẽ báo "did not match any files" dù việc xóa đã xong.
            r = _git(mirror_dir, "rm", "-r", "-f", "--ignore-unmatch", "--", name)
            if r.returncode == 0:
                changed_mirror = True
            else:
                ok = False
        if ok:
            rep["deleted"].append(name)
        else:
            rep["failed"].append(name)
    if changed_mirror:
        _git(mirror_dir, "commit", "-m", f"sync: áp giấy báo tử ({_host_tag()})")
    return rep


def sync_brains(brains_dir: str, mirror_dir: str, repo_url: str, token: str, branch: str = "main",
                trash_dir: Optional[str] = None, protected_names=None) -> dict:
    """Đồng bộ 2 CHIỀU toàn bộ thư mục brains với repo GitHub. Trả
    {ok, pushed, committed, merged, restored, conflicts, applied, deleted, error?}."""
    if not has_git():
        return {"ok": False, "error": "Máy chưa cài git (cần cài git để đồng bộ)"}
    if not repo_url or not token:
        return {"ok": False, "error": "Chưa cấu hình repo URL hoặc token"}
    if not Path(brains_dir).is_dir():
        return {"ok": False, "error": f"Thư mục brains không tồn tại: {brains_dir}"}
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"ok": False, "error": "Đang có phiên đồng bộ khác chạy - thử lại sau"}
    try:
        return _sync_brains_locked(str(brains_dir), str(mirror_dir), repo_url, token, branch,
                                   trash_dir, protected_names)
    except Exception as e:
        return {"ok": False, "error": _redact(f"{type(e).__name__}: {e}", token)}
    finally:
        _SYNC_LOCK.release()


def _sync_brains_locked(brains_dir: str, mirror_dir: str, repo_url: str, token: str, branch: str,
                        trash_dir: Optional[str] = None, protected_names=None) -> dict:
    rep = {"ok": False, "pushed": False, "committed": False, "merged": False,
           "restored": False, "conflicts": [], "applied": 0, "deleted": 0,
           "applied_sample": [], "deleted_sample": [], "brains_deleted": [],
           # Media KHÔNG lên GitHub (xem khối chú thích "GIT CHỈ GIỮ CHỮ" ở đầu file). Đếm ra
           # đây để giao diện nói thẳng, chứ bỏ qua lặng lẽ thì có ngày ai đó tưởng ảnh của
           # mình đã được sao lưu.
           "media_bo_qua": 0, "media_bytes": 0}
    if not trash_dir:
        trash_dir = str(Path(mirror_dir).parent / "brain-trash")   # cạnh mirror (đều trong STATE_DIR)
    gc_trash(trash_dir, 30)              # dọn thùng rác quá 30 ngày
    gc_tombstones(brains_dir, _TOMBSTONE_TTL)   # dọn giấy báo tử quá 180 ngày
    Path(mirror_dir).mkdir(parents=True, exist_ok=True)
    if not is_git_checkout(mirror_dir):
        r = _git(mirror_dir, "init")
        if r.returncode != 0:
            return {**rep, "error": (r.stderr or "git init lỗi")[:200]}
    _git(mirror_dir, "config", "user.email", "javis@localhost")
    _git(mirror_dir, "config", "user.name", f"Javis Sync ({_host_tag()})")
    # Sync truyền BYTE NGUYÊN VĂN giữa các máy: tắt autocrlf để git Windows không tự đổi
    # LF↔CRLF lúc add/checkout (nếu không, cùng 1 file sẽ lệch byte giữa local và VPS mãi mãi).
    _git(mirror_dir, "config", "core.autocrlf", "false")

    # Khôi phục não thiếu KHÔNG tombstone TRƯỚC khi chụp snapshot (xem docstring
    # _restore_missing_brains) - phải chạy trước dòng _sync_mirror ngay dưới.
    _restore_missing_brains(brains_dir, mirror_dir, protected_names)

    sync_start = time.time()
    if _brains_has_content(brains_dir):
        rep.update(_sync_mirror(brains_dir, mirror_dir))
        _git(mirror_dir, "add", "-A")
        c = _git(mirror_dir, "commit", "-m",
                 f"backup: {time.strftime('%Y-%m-%d %H:%M:%S')} ({_host_tag()})")
        rep["committed"] = c.returncode == 0
    else:
        rep["restored"] = True   # brains trống → chỉ nhận từ remote, không ghi nhận xoá

    hv = _git(mirror_dir, "rev-parse", "-q", "--verify", "HEAD")
    pre_head = (hv.stdout or "").strip() if hv.returncode == 0 else None
    au = _auth_url(repo_url, token)

    for attempt in (1, 2):
        f = _git(mirror_dir, "fetch", au, branch, timeout=180)
        remote_missing = f.returncode != 0 and \
            "couldn't find remote ref" in ((f.stderr or "") + (f.stdout or "")).lower()
        if f.returncode != 0 and not remote_missing:
            return {**rep, "error": _redact("fetch: " + ((f.stderr or "lỗi").strip())[:250], token)}
        changed = set()
        if not remote_missing:
            m = _integrate_remote(mirror_dir, pre_head)
            if m.get("error"):
                return {**rep, "error": _redact(m["error"], token)}
            rep["merged"] = rep["merged"] or bool(m.get("merged"))
            rep["conflicts"].extend(m.get("conflicts", []))
            changed = _changed_by_integration(mirror_dir, pre_head)
        # Áp giấy báo tử: xóa dứt khoát não có tombstone (ghi đè 'xóa không thắng') TRƯỚC khi
        # _apply_back kịp khôi phục chúng về brains. Đặt trước tự-vá + _apply_back là cố ý.
        tomb = _apply_tombstones(brains_dir, mirror_dir, trash_dir, protected_names)
        if tomb["failed"]:
            _rollback_mirror(mirror_dir, pre_head)
            return {**rep, "error": "Áp giấy báo tử lỗi (" + ", ".join(tomb["failed"][:2]) +
                    ") - hoãn push, lần sau tự thử lại"}
        if tomb["deleted"]:
            rep["brains_deleted"] = (rep["brains_deleted"] + tomb["deleted"])[:50]
        # Tự vá: file có trong HEAD mirror nhưng THIẾU trong brains → luôn áp về. Bao trường hợp
        # khôi phục khi mirror đã up-to-date (diff rỗng) + brains bị wipe/volume mới. Chỉ THÊM
        # file thiếu, không bao giờ xoá (xoá chỉ đi qua diff của bước hoà nhập).
        if _git(mirror_dir, "rev-parse", "-q", "--verify", "HEAD").returncode == 0:
            for rel in _git_lines_z(mirror_dir, "ls-tree", "-r", "--name-only", "-z", "HEAD"):
                if not _backup_skip(rel) and not (Path(brains_dir) / rel).exists():
                    changed.add(rel)
        if changed:
            ab = _apply_back(mirror_dir, brains_dir, changed, sync_start)
            rep["applied"] += ab["applied"]
            rep["deleted"] += ab["deleted"]
            rep["applied_sample"] = (rep["applied_sample"] + ab["applied_sample"])[:20]
            rep["deleted_sample"] = (rep["deleted_sample"] + ab["deleted_sample"])[:20]
            if ab["failed"]:
                # BẤT BIẾN AN TOÀN: áp không trọn → rollback mirror + KHÔNG push.
                _rollback_mirror(mirror_dir, pre_head)
                return {**rep, "error": f"Áp bản đồng bộ về máy lỗi {len(ab['failed'])} file "
                        f"(vd {ab['failed'][:2]}) - đã hoãn push, lần sau tự thử lại"}
        hv2 = _git(mirror_dir, "rev-parse", "-q", "--verify", "HEAD")
        if hv2.returncode != 0:
            rep["ok"] = True   # cả local lẫn remote đều trống → không có gì để đồng bộ
            return rep
        p = _git(mirror_dir, "push", au, f"HEAD:refs/heads/{branch}", timeout=180)
        if p.returncode == 0:
            rep["ok"] = True
            rep["pushed"] = True
            return rep
        err = (p.stderr or "").strip()
        if attempt == 1 and any(s in err for s in ("fetch first", "non-fast-forward", "rejected")):
            pre_head = (hv2.stdout or "").strip()   # máy khác vừa đẩy chen → vòng 2 hoà tiếp
            continue
        return {**rep, "error": _redact(("push: " + (err or "lỗi"))[:300], token)}
    return {**rep, "error": "push liên tục bị vượt - thử lại sau"}


# ============================================================
# GIẤY BÁO TỬ (tombstone) - đánh dấu não bị xóa CÓ CHỦ ĐÍCH để lan việc xóa sang mọi máy.
# Một file cho mỗi não trong <brains_dir>/.javis-tombstones/<tên não>.json. Đồng bộ theo repo
# (không nằm trong _backup_skip), KHÔNG hiện thành não (/brains bỏ tên bắt đầu bằng '.').
# ============================================================
TOMBSTONE_DIR = ".javis-tombstones"
_TOMBSTONE_TTL = 180 * 86400   # giữ 180 ngày: lâu hơn thùng rác để máy offline lâu quay lại không hồi sinh


def _tombstone_path(brains_dir: str, name: str) -> Path:
    return Path(brains_dir) / TOMBSTONE_DIR / (name + ".json")


def write_tombstone(brains_dir: str, name: str) -> None:
    """Ghi giấy báo tử cho não <name> (đã bị xóa có chủ đích). Ghi nguyên tử (.tmp -> replace)."""
    if not name:
        return
    p = _tombstone_path(brains_dir, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"name": name, "deleted_at": int(time.time()), "host": _host_tag(), "v": 1}
    tmp = Path(str(p) + ".tmp")   # đuôi .tmp -> nằm trong _backup_skip, không lọt vào backup
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(p))


def clear_tombstone(brains_dir: str, name: str) -> None:
    """Gỡ giấy báo tử của não <name> (khi tạo lại não cùng tên) để không bị xóa oan."""
    try:
        _tombstone_path(brains_dir, name).unlink()
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[tombstone clear] {name}: {e}", file=__import__('sys').stderr)


def _read_tombstones(root: str) -> List[dict]:
    """Đọc mọi giấy báo tử trong <root>/.javis-tombstones/. Bỏ file hỏng. Gắn _file = tên file."""
    d = Path(root) / TOMBSTONE_DIR
    out: List[dict] = []
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(j, dict) and j.get("name"):
                j["_file"] = f.name
                out.append(j)
        except Exception:
            continue
    return out


def gc_tombstones(brains_dir: str, ttl: int = _TOMBSTONE_TTL) -> int:
    """Xóa giấy báo tử quá hạn (mặc định 180 ngày). Trả số file đã xóa."""
    now = int(time.time())
    n = 0
    for t in _read_tombstones(brains_dir):
        if now - int(t.get("deleted_at", now)) > ttl:
            try:
                (Path(brains_dir) / TOMBSTONE_DIR / t["_file"]).unlink()
                n += 1
            except Exception:
                pass
    return n


# ============================================================
# THÙNG RÁC CỤC BỘ - giữ bản sao não đã xóa (30 ngày) để cứu hộ. NGOÀI vùng đồng bộ (không lên git).
# ============================================================
def move_to_trash(brain_dir: str, trash_dir: str, name: str) -> Optional[str]:
    """Chuyển thư mục não vào thùng rác <trash_dir>/<name>__<ts>/. Trả path đích hoặc None nếu
    nguồn không phải thư mục. shutil.move xử lý cả khác ổ đĩa. Retry 3 lần: Windows có thể kẹt
    handle (engine đang mở file trong não) - chờ ngắn rồi thử lại."""
    src = Path(brain_dir)
    if not src.is_dir():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = Path(trash_dir) / f"{name}__{stamp}"
    i = 1
    while dst.exists():
        dst = Path(trash_dir) / f"{name}__{stamp}-{i}"
        i += 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for _ in range(3):
        try:
            shutil.move(str(src), str(dst))
            return str(dst)
        except Exception as e:
            last = e
            time.sleep(0.3)
    raise last


def gc_trash(trash_dir: str, days: int = 30) -> int:
    """Xóa các mục trong thùng rác cũ hơn <days> ngày (theo mtime thư mục). Trả số mục đã xóa."""
    d = Path(trash_dir)
    if not d.is_dir():
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for sub in d.iterdir():
        try:
            if sub.is_dir() and sub.stat().st_mtime < cutoff:
                shutil.rmtree(str(sub))
                n += 1
        except Exception:
            pass
    return n


def _dir_newer_than(root: str, ts: int) -> bool:
    """Có file nào trong root có mtime > ts (dung sai +1s) không? Bỏ .git nested. Dùng cho chốt
    thời gian: não dựng/sửa lại SAU khi có tombstone thì không bị xóa oan."""
    if ts <= 0:
        return False
    for dp, dn, fns in os.walk(root):
        dn[:] = [x for x in dn if x not in _BACKUP_SKIP_DIRS]
        for fn in fns:
            try:
                if os.path.getmtime(os.path.join(dp, fn)) > ts + 1:
                    return True
            except Exception:
                continue
    return False


# ============================================================
# BrainLock - khoá cấp file cross-platform (serialize ghi giữa CÁC tiến trình)
# ============================================================
class BrainLock:
    """Khoá độc quyền theo brain, dựa trên file <root>/.javis-learn.lock.
    POSIX: fcntl.flock; Windows: msvcrt.locking. Non-blocking + retry tới timeout.
    Dùng như context manager (chạy trong worker THREAD, không block event loop)."""

    def __init__(self, root: str, timeout: float = 30.0):
        self.path = Path(root) / ".javis-learn.lock"
        self.timeout = timeout
        self._fh = None
        self._locked = False

    def acquire(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a+")
        except Exception:
            return False
        deadline = time.time() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
                return True
            except OSError:
                if time.time() >= deadline:
                    try:
                        self._fh.close()
                    except Exception:
                        pass
                    self._fh = None
                    return False
                time.sleep(0.25)

    def release(self) -> None:
        if not self._fh:
            return
        try:
            if self._locked:
                if os.name == "nt":
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            self._locked = False

    def __enter__(self):
        self.acquired = self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False
