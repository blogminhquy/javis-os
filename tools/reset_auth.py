"""Forget the Javis login password on this machine, so the owner can set a new one from scratch.

For an owner who forgot the current password: the dashboard asks for the current one before it changes anything, so
the way back starts on the machine itself. reset-auth.bat (Windows) and reset-auth.command (macOS) run this file; the
Account page reveals the right one in Explorer / Finder.

What it clears:
  - the whole `auth` block of settings.json: username, password and 2FA. The old password is simply gone; the owner
    opens Javis and sets a new one on the Account page (or in the account form Javis shows when login is required);
  - JAVIS_ADMIN_PASSWORD / JAVIS_ADMIN_USER in the install's .env. install.sh writes them on macOS and Linux, and Javis
    re-applies them at boot when the account has no marker of them, so leaving them would bring the old password back
    on the next start.

What it keeps: `setup_done` and everything else (models, channels, keys), so Javis does NOT reopen the first-run
wizard, which would also ask for the AI brain again.

It writes the file directly and leaves .auth_stamp.json alone on purpose: a running Javis sees the account block
change outside the app and ends every signed-in session (config.auth_guard_check). Nothing needs a restart.

    python tools/reset_auth.py                  # settings.json in server/, or $JAVIS_STATE_DIR
    python tools/reset_auth.py --state-dir /data/state
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = ("JAVIS_ADMIN_PASSWORD", "JAVIS_ADMIN_USER")


def settings_path(state_dir: str = "") -> Path:
    base = state_dir or os.environ.get("JAVIS_STATE_DIR", "") or str(ROOT / "server")
    return Path(base) / "settings.json"


def clear_auth(data: dict) -> dict:
    """`data` without a login account. Every other key, setup_done included, is kept."""
    out = dict(data)
    out["auth"] = {}
    return out


def strip_env(text: str) -> tuple[str, bool]:
    """`text` (a .env file) without the admin account lines. Returns (new text, whether anything was removed)."""
    kept, removed = [], False
    for line in text.splitlines(keepends=True):
        key = line.strip()
        if key.startswith("export "):
            key = key[len("export "):].lstrip()
        if any(key.startswith(k + "=") for k in ENV_KEYS):
            removed = True
            continue
        kept.append(line)
    return "".join(kept), removed


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.reset.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def say(vi: str, en: str) -> None:
    print(f"  {vi}\n  {en}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Forget the Javis login password on this machine.")
    ap.add_argument("--state-dir", default="", help="folder that holds settings.json")
    ap.add_argument("--env-file", default=str(ROOT / ".env"), help="the install's .env")
    args = ap.parse_args(argv)
    path = settings_path(args.state_dir)
    print("")
    print("  ==========================================")
    print("  JAVIS OS - xoá mật khẩu / reset password")
    print("  ==========================================")
    print("")
    if not path.is_file():
        say(f"Không thấy {path}. Javis đã chạy lần nào trên máy này chưa?",
            f"{path} not found. Has Javis run on this computer yet?")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except Exception as e:  # noqa: BLE001 - never overwrite a file we could not read
        say(f"Không đọc được {path} ({e}). Không sửa gì cả.", f"Could not read {path} ({e}). Nothing changed.")
        return 1
    write_atomic(path, json.dumps(clear_auth(data), ensure_ascii=False, indent=2))
    env = Path(args.env_file)
    if env.is_file():
        try:
            text, removed = strip_env(env.read_text(encoding="utf-8"))
            if removed:
                write_atomic(env, text)
        except Exception as e:  # noqa: BLE001 - the account is already cleared; say what is left to do
            say(f"Chưa xoá được mật khẩu cũ trong {env} ({e}). Hãy xoá dòng JAVIS_ADMIN_PASSWORD bằng tay.",
                f"Could not remove the old password from {env} ({e}). Delete the JAVIS_ADMIN_PASSWORD line by hand.")
    say("Xong, mật khẩu cũ đã bị xoá. Mọi thiết bị đang đăng nhập bị đăng xuất.",
        "Done, the old password is gone. Every signed-in device is signed out.")
    say("Mở lại Javis rồi vào Tài khoản để đặt mật khẩu mới.",
        "Open Javis again and set a new password on the Account page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
