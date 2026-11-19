"""Regression tests for selecting the newest installed Codex CLI.

    python tests/run.py codex_cli_moi_nhat

The CLI supplies the model catalog, so a stale binary can hide newer models.
Versions are mocked to keep the test independent of a real Codex installation.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

import claude_cli as cc  # noqa: E402

_fails = []


def check(name, condition):
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        _fails.append(name)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        appdata = Path(tmp) / "appdata"
        desktop = home / ".codex" / ".sandbox-bin" / "codex.exe"
        npm = appdata / "npm" / "codex.cmd"
        path_cli = home / "path-codex"
        local = home / ".local" / "bin" / "codex"
        paths = [desktop, npm]
        if os.name != "nt":
            paths.extend((path_cli, local))
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("mock")

        old_functions = (cc._home_dir, cc.tim_binary, cc._codex_version)
        old_env = {name: os.environ.get(name) for name in ("APPDATA", "JAVIS_CODEX_BIN")}
        versions = {}
        cc._home_dir = lambda: home
        cc._codex_version = lambda path: versions.get(path)
        os.environ["APPDATA"] = str(appdata)
        os.environ.pop("JAVIS_CODEX_BIN", None)
        try:
            if os.name == "nt":
                cc.tim_binary = lambda name: None
                versions.update({str(desktop): (0, 147, 0), str(npm): (0, 160, 0)})
                check("newer npm CLI wins over older Desktop CLI", cc.find_codex_cli() == str(npm))

                versions[str(desktop)] = (0, 161, 0)
                check("newer Desktop CLI wins over npm CLI", cc.find_codex_cli() == str(desktop))

                versions.clear()
                check("unknown versions preserve the prior candidate order", cc.find_codex_cli() == str(desktop))

                npm.unlink()
                check("a single installed CLI is selected", cc.find_codex_cli() == str(desktop))
            else:
                cc.tim_binary = lambda name: str(path_cli)
                versions.update({str(path_cli): (0, 153, 4), str(local): (0, 162, 1)})
                check("newer local CLI wins over stale PATH CLI", cc.find_codex_cli() == str(local))

                versions[str(path_cli)] = (0, 163, 0)
                check("newer PATH CLI remains selected", cc.find_codex_cli() == str(path_cli))

                versions.clear()
                check("unknown POSIX versions preserve PATH precedence", cc.find_codex_cli() == str(path_cli))

                local.unlink()
                versions[str(path_cli)] = (0, 153, 4)
                check("PATH CLI works when no local CLI exists", cc.find_codex_cli() == str(path_cli))

                override = home / "custom-codex"
                override.write_text("mock")
                os.environ["JAVIS_CODEX_BIN"] = str(override)
                check("explicit CLI override remains authoritative", cc.find_codex_cli() == str(override))
        finally:
            cc._home_dir, cc.tim_binary, cc._codex_version = old_functions
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
