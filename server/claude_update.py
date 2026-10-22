"""Giữ Claude Code trên máy luôn ở bản mới, để model mới tự hiện trong Javis.

Danh sách model của gói Claude Code đọc từ CHÍNH binary `claude` (`claude_cli.list_models`),
nên Javis chỉ thấy model mới khi Claude Code đã lên bản biết model đó. Lỗi thật chủ repo báo
29/09/2026: Sonnet 5.5 ra rồi mà Javis không có. Binary trên máy đứng ở 2.1.232 (14/08) suốt
sáu tuần, vì:

- Claude Code chỉ tự cập nhật khi người ta mở nó gõ tay. Javis gọi nó chạy ngầm, nên không
  bao giờ kích hoạt được đường đó. Máy chỉ dùng Claude qua Javis là kẹt vĩnh viễn.
- `~/.claude.json` có thể mang `autoUpdates: false`, và app Claude Desktop đặt
  `DISABLE_AUTOUPDATER=1` cho các tiến trình nó đẻ ra.

Nên Javis tự chạy `claude update` mỗi ngày một lần, và có nút bấm để chạy ngay.

Bản Docker KHÔNG đi đường này: CLI cài bằng `npm -g` dưới quyền root trong ảnh, tiến trình
Javis chạy bằng user `javis` nên không ghi đè được. Ở đó Claude Code mới tới theo ảnh Javis mới
(CI ép lấy bản mới nhất mỗi lần build, xem `.github/workflows/docker-publish.yml`).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import claude_cli
import config as cfgmod
import deploy_info
import localefmt

CHU_KY = 24 * 3600
_TRANG_THAI = "claude-update.json"
_RX_BAN = re.compile(r"(\d+\.\d+\.\d+)")


_ENV = "JAVIS_CLAUDE_AUTO_UPDATE"
_OFF_VALUES = ("0", "false", "no", "off")
SETTING_KEY = "claude_auto_update"   # under settings["model"]; the switch on the Models page


def env_off() -> bool:
    """True when JAVIS_CLAUDE_AUTO_UPDATE=0 (or false/no/off) forces the daily update off.

    The env var only ever turns the updater OFF and then wins over the switch on the Models page,
    so an admin who pinned it off in a service file keeps it off whatever someone clicks.
    """
    return (os.environ.get(_ENV) or "").strip().lower() in _OFF_VALUES


def setting_on(cfg: dict | None = None) -> bool:
    """The saved switch (Models page, Claude Code card). Missing or unreadable = on, the old default."""
    try:
        cfg = cfgmod.read_settings() if cfg is None else cfg
        return ((cfg or {}).get("model") or {}).get(SETTING_KEY, True) is not False
    except Exception:
        return True


def bat(cfg: dict | None = None) -> bool:
    """Is the daily `claude update` on. Read at EVERY run of the loop, so the switch takes
    effect without a restart (customer report 0.270, code 18)."""
    return not env_off() and setting_on(cfg)


def _file_trang_thai() -> Path:
    return Path(cfgmod.STATE_DIR) / _TRANG_THAI


def doc_trang_thai() -> dict:
    try:
        return json.loads(_file_trang_thai().read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _ghi_trang_thai(d: dict) -> None:
    try:
        p = _file_trang_thai()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    except Exception:
        pass


def den_han(now: float | None = None) -> bool:
    """Đã quá một chu kỳ kể từ lần THỬ gần nhất chưa (thử hỏng cũng tính, khỏi thử dồn dập)."""
    now = time.time() if now is None else now
    return (now - float(doc_trang_thai().get("ts") or 0)) >= CHU_KY


def _chay(cmd: list, timeout: int):
    env = dict(os.environ)
    # App Claude Desktop đặt biến này cho tiến trình con; để nguyên thì `claude update` từ chối.
    env.pop("DISABLE_AUTOUPDATER", None)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=env, stdin=subprocess.DEVNULL,
                          creationflags=claude_cli._no_window())


def phien_ban(cli: str) -> str:
    try:
        r = _chay([cli, "--version"], 30)
        m = _RX_BAN.search((r.stdout or "") + (r.stderr or ""))
        return m.group(1) if m else ""
    except Exception:
        return ""


def cap_nhat(ly_do: str = "tay") -> dict:
    """Chạy `claude update`. Không bao giờ ném lỗi: mọi hỏng hóc trả về trong `error`.

    `doi` = phiên bản thật sự đổi, tức caller nên đọc lại danh sách model.
    """
    now = time.time()
    if deploy_info.deploy_mode() == "docker":
        return {"ok": False, "docker": True,
                "error": localefmt.chu("Bản Docker nhận Claude Code mới theo mỗi bản cập nhật Javis, "
                                       "không cập nhật riêng được.",
                                       "The Docker build gets a new Claude Code with each Javis update; "
                                       "it cannot be updated on its own.")}
    cli = claude_cli.find_claude_cli()
    if not cli:
        return {"ok": False, "error": localefmt.chu("Chưa thấy Claude Code trên máy.",
                                                    "Claude Code was not found on this machine.")}
    truoc = phien_ban(cli)
    try:
        r = _chay([cli, "update"], 300)
        rc, ra = r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        rc, ra = -1, localefmt.chu("quá 5 phút chưa xong", "not done after 5 minutes")
    except Exception as e:
        rc, ra = -1, f"{type(e).__name__}: {e}"
    sau = phien_ban(cli) or truoc
    kq = {"ok": rc == 0, "truoc": truoc, "sau": sau, "doi": bool(sau and sau != truoc),
          "ts": now, "ly_do": ly_do}
    if rc != 0:
        # Dòng cuối là câu CLI tự giải thích (vd "managed by Homebrew"), đủ cho người đọc.
        dong = [x for x in ra.splitlines() if x.strip()]
        kq["error"] = (dong[-1] if dong else localefmt.chu("không rõ lỗi", "unknown error"))[:300]
    _ghi_trang_thai(kq)
    return kq
