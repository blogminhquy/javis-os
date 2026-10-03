"""Regression 0.71.1: máy có nhiều bản Codex thì Javis phải hỏi bản MỚI NHẤT.

    python tests/run.py codex_cli_moi_nhat

Chủ repo đo 03/10/2026: ~/.codex/.sandbox-bin (Codex Desktop) kẹt ở 0.147, npm đã 0.160.
`find_codex_cli` lấy bản đứng đầu nên `model/list` chỉ trả đời GPT-5.6, thiếu GPT-6.1-Sol.
Không chạy Codex thật: số phiên bản được giả lập.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

import claude_cli as cc  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def main():
    if os.name != "nt":
        print("skip (chỉ Windows mới gom nhiều bản; POSIX vẫn theo PATH)")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        appdata = Path(tmp) / "appdata"
        desktop = home / ".codex" / ".sandbox-bin" / "codex.exe"
        npm = appdata / "npm" / "codex.cmd"
        for p in (desktop, npm):
            p.parent.mkdir(parents=True)
            p.write_text("x")
        phien_ban = {str(desktop): (0, 147, 0), str(npm): (0, 160, 0)}

        old = (cc._home_dir, cc.tim_binary, cc._codex_version, os.environ.get("APPDATA"),
               os.environ.pop("JAVIS_CODEX_BIN", None))
        cc._home_dir = lambda: home
        cc.tim_binary = lambda ten: None
        cc._codex_version = lambda p: phien_ban.get(p)
        os.environ["APPDATA"] = str(appdata)
        try:
            check("bản npm mới hơn thắng bản Codex Desktop cũ", cc.find_codex_cli() == str(npm))

            phien_ban[str(desktop)] = (0, 161, 0)
            check("Codex Desktop mới hơn thì lấy Codex Desktop", cc.find_codex_cli() == str(desktop))

            phien_ban.clear()
            check("không đọc được phiên bản thì giữ thứ tự cũ", cc.find_codex_cli() == str(desktop))

            npm.unlink()
            check("chỉ một bản thì lấy bản đó", cc.find_codex_cli() == str(desktop))
        finally:
            cc._home_dir, cc.tim_binary, cc._codex_version = old[0], old[1], old[2]
            if old[3] is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old[3]
            if old[4] is not None:
                os.environ["JAVIS_CODEX_BIN"] = old[4]
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
