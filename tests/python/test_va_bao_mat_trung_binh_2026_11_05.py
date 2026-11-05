"""Medium-severity security fixes from the 2026-11-05 audit. Run by hand / CI:

    python tests/python/test_va_bao_mat_trung_binh_2026_11_05.py

No network.

  7. A pack declaring `replaces:` inherits the old pack's "on" state only when it is the official store's release of
     that id (sha256 listed in the default store index), never for a zip from elsewhere.
  8. The Origin check tells localhost ports apart (a page on localhost:3000 cannot POST or open a WebSocket to
     localhost:7777), and the "any localhost origin may read the API" CORS opening is off unless JAVIS_DEV_CORS=1.
  9. docker-publish.yml run by hand only publishes from main.
 12. A share link of a note at the brain root no longer serves media from inbox/, memory/ or dot folders.
 13. Custom connector tools named forward_*, share_*, trash_*, transfer_* ... count as writes, not reads.
"""
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-audit-mid-")
_BRAINS = tempfile.mkdtemp(prefix="javis-audit-mid-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS
os.environ.pop("JAVIS_DEV_CORS", None)

from _paths import ROOT, SERVER  # noqa: E402,F401
from pathlib import Path  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


# ============================================================
# 7. replaces: inherit "on" only for the official store release
# ============================================================
import pack_install  # noqa: E402
import packs_store  # noqa: E402

SHA = "ab" * 32
_cache = {"packs": [{"id": "javis.gate", "download": {"sha256": SHA}}]}
packs_store._doc_cache = lambda: _cache
packs_store.url_kho = lambda: packs_store.STORE_MAC_DINH
bat = pack_install._bat_sau_cai
check("7. the owner's own switch always wins", bat(True, {"enabled": False}, "x.y", "00") is True)
check("7. official release of the id inherits the old pack's 'on'",
      bat(False, {"enabled": True}, "javis.gate", SHA) is True)
check("7. same id but another zip (hash not in the index) stays off",
      bat(False, {"enabled": True}, "javis.gate", "cd" * 32) is False)
check("7. an id the store does not list (third-party 'replaces: javis.zalo') stays off",
      bat(False, {"enabled": True}, "evil.zalo", SHA) is False)
check("7. nothing to inherit stays off", bat(False, {"enabled": False}, "javis.gate", SHA) is False)
packs_store.url_kho = lambda: "https://example.com/index.json"
check("7. a custom store URL does not count as official",
      bat(False, {"enabled": True}, "javis.gate", SHA) is False)
packs_store.url_kho = lambda: packs_store.STORE_MAC_DINH
src_pi = Path(SERVER, "pack_install.py").read_text(encoding="utf-8")
check("7. both the ledger and the reply use the new rule",
      src_pi.count("_bat_sau_cai(enable, thay, pid, sha)") == 2 and 'or thay["enabled"]' not in src_pi)
js = Path(ROOT, "dashboard", "packs.js").read_text(encoding="utf-8")
check("7. the consent screen names the replaced packs", "store.inspect.replaces.body" in js)

# ============================================================
# 8. Origin ports on localhost, CORS opening
# ============================================================
import web_security as w  # noqa: E402

w.invalidate()
check("8. same origin still passes", w.csrf_decision("POST", "localhost:7777", "http://localhost:7777", False) is None)
check("8. localhost:3000 posting to localhost:7777 is refused",
      (w.csrf_decision("POST", "localhost:7777", "http://localhost:3000", False) or (0,))[0] == 403)
check("8. ... with a password too", (w.csrf_decision("POST", "127.0.0.1:7777", "http://127.0.0.1:5173", True)
                                     or (0,))[0] == 403)
check("8. localhost vs 127.0.0.1 on the same port is still this server",
      w.csrf_decision("POST", "127.0.0.1:7777", "http://localhost:7777", True) is None)
check("8. default ports match (Host without port, Origin http://localhost)",
      w.csrf_decision("POST", "localhost", "http://localhost", False) is None)
check("8. https default port matches", w.csrf_decision("POST", "localhost", "https://localhost:443", False) is None)
check("8. IPv6 loopback same port passes", w.csrf_decision("POST", "[::1]:7777", "http://[::1]:7777", False) is None)
check("8. a WebSocket from another localhost port is refused",
      (w.ws_decision("localhost:7777", "http://localhost:5173", False) or (0,))[0] == 403)
check("8. a WebSocket from the dashboard itself passes", w.ws_decision("localhost:7777", "http://localhost:7777", False)
      is None)
check("8. a public domain behind a proxy is unaffected",
      w.csrf_decision("POST", "javis.example.com", "https://javis.example.com", True) is None)

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cors = [m for m in main.app.user_middleware if getattr(m.cls, "__name__", "") == "CORSMiddleware"]
check("8. no CORS opening for other localhost ports by default", not cors)

# ============================================================
# 9. docker-publish from main only
# ============================================================
yml = Path(ROOT, ".github", "workflows", "docker-publish.yml").read_text(encoding="utf-8")
check("9. a manual run publishes only from main",
      "if: github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/main'" in yml)

# ============================================================
# 12. Share assets skip private zones
# ============================================================
BRAIN = Path(_BRAINS, "brain")
for d in ("inbox/telegram", "memory", ".claude", "attachments", "anh"):
    (BRAIN / d).mkdir(parents=True, exist_ok=True)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
for rel in ("inbox/telegram/photo_101.jpg", "memory/x.png", ".claude/y.png", "attachments/a.png", "anh/b.png"):
    (BRAIN / rel).write_bytes(PNG)
(BRAIN / "ghi-chu.md").write_text("# T\n\n![a](attachments/a.png)\n", encoding="utf-8")
(BRAIN / "inbox" / "telegram" / "ghi.md").write_text("# T\n\n![p](photo_101.jpg)\n", encoding="utf-8")
cl = TestClient(main.app, base_url="http://localhost")
tok = cl.post("/share/create", json={"brain": str(BRAIN), "path": "ghi-chu.md"}).json().get("token", "")
check("12. share link created", bool(tok))


def _a(t, p):
    return cl.get(f"/s/{t}/asset", params={"p": p}).status_code


check("12. attachments image still served", _a(tok, "attachments/a.png") == 200)
check("12. an ordinary image next to the note still served", _a(tok, "anh/b.png") == 200)
check("12. inbox/ photo refused", _a(tok, "inbox/telegram/photo_101.jpg") == 404)
check("12. memory/ media refused", _a(tok, "memory/x.png") == 404)
check("12. dot folder media refused", _a(tok, ".claude/y.png") == 404)
tok2 = cl.post("/share/create", json={"brain": str(BRAIN), "path": "inbox/telegram/ghi.md"}).json().get("token", "")
check("12. a note shared from inside inbox/ still shows its own image",
      bool(tok2) and _a(tok2, "photo_101.jpg") == 200)

# ============================================================
# 13. Write hints
# ============================================================
import mcp_catalog  # noqa: E402

for tool in ("forward_email", "share_file", "trash_message", "transfer_funds", "archive_thread", "revoke_token"):
    check(f"13. custom connector '{tool}' counts as write", mcp_catalog.classify({}, tool) == "write")
for tool in ("get_events", "list_messages", "search_threads", "read_file"):
    check(f"13. '{tool}' still reads", mcp_catalog.classify({}, tool) == "read")
check("13. a catalog connector's declared read list still wins",
      mcp_catalog.classify({"tool_meta": {"read": ["share_*"]}}, "share_list") == "read")

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
