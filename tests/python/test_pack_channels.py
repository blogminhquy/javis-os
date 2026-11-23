"""A Store pack can add an inbox channel (`provides.channels`) without touching `_MODULES`.

    python tests/run.py pack_channels

No network, no server. Real `packs` registry, real `channels` registry, packs written straight into a temp
state dir with a hand-written ledger (what `pack_install` would have recorded).

Guarded here:
1. An enabled pack whose code the owner agreed to adds its channel after the core ones, tagged with the pack id.
2. Code gate: a pack never installed through the installer, or whose code changed after consent, adds nothing.
3. A disabled or removed pack's channel disappears from the registry AND from `module()`.
4. A pack can never replace a core channel id, and a broken module just leaves its channel out.
5. The manifest only accepts `channels/<name>.py` inside the pack.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import json
import os
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="javis-pack-channels-")
os.environ["JAVIS_STATE_DIR"] = STATE

import packs  # noqa: E402
import channels  # noqa: E402
from plugins_host import _digest_thu_muc  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def channel_src(cid: str, extra: str = "") -> str:
    return (
        "from channels import KenhSpec\n"
        f"SPEC = KenhSpec(id={cid!r}, nhan='Demo {cid}', kind='bot', mau='#6366F1')\n"
        "class Transport:\n    pass\n"
        "async def gui(*a, **k):\n    return True\n"
        "WEBHOOK_PATH = '/ext/demo/webhook'\n" + extra
    )


def write_pack(pid: str, files: dict, provides: list, consent=True, enabled=True):
    d = Path(STATE) / "packs" / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "javis-pack.yaml").write_text(
        f"format: javis-pack\nspec: 1\nid: {pid}\nversion: 1.0.0\n"
        f'name: {{vi: "{pid}", en: "{pid}"}}\ndescription: {{vi: "Thử"}}\n'
        f"compat: {{app: \">=0.1.0\"}}\nprovides:\n  channels: [{', '.join(provides)}]\n", encoding="utf-8")
    for rel, src in files.items():
        f = d / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(src, encoding="utf-8")
    so = packs._so_cai_dat()
    if consent:
        so[pid] = {"enabled": enabled, "code_digest": _digest_thu_muc(d)}
    else:
        so.pop(pid, None)
    packs.LEDGER.write_text(json.dumps(so), encoding="utf-8")
    refresh()
    return d


def refresh():
    packs.invalidate()
    channels.reload_registry()


core_ids = set(channels.ids())
check("core registry loads without any pack", "telegram" in core_ids and "zalo" in core_ids, core_ids)

# 1. Consented, enabled pack: channel added after the core ones, tagged.
write_pack("demo-pack", {"channels/demo.py": channel_src("demo")}, ["channels/demo.py"])
s = channels.spec("demo")
check("pack channel is in the registry", s is not None, channels.ids())
check("pack channel comes after core channels", list(channels.ids())[-1] == "demo", channels.ids())
check("pack channel is tagged with its pack", s is not None and s.pack == "demo-pack")
check("pack channel can carry a bot (Transport found)", s is not None and s.nl("bot"))
check("module() returns the pack module", getattr(channels.module("demo"), "WEBHOOK_PATH", "") == "/ext/demo/webhook")
ui = {k["id"]: k for k in channels.cho_giao_dien()}
check("dashboard list carries the pack id", ui.get("demo", {}).get("pack") == "demo-pack", ui.get("demo"))
check("core channels carry an empty pack id", ui["telegram"]["pack"] == "")

# 2. Code gate.
d = write_pack("demo-pack", {}, ["channels/demo.py"])
(d / "channels" / "demo.py").write_text(channel_src("demo", extra="X = 1\n"), encoding="utf-8")
refresh()
check("code changed after consent: channel not loaded", channels.spec("demo") is None, channels.ids())
write_pack("demo-pack", {"channels/demo.py": channel_src("demo")}, ["channels/demo.py"], consent=False)
check("pack dropped in by hand (no ledger row): channel not loaded", channels.spec("demo") is None)

# 3. Disabled, then removed.
write_pack("demo-pack", {"channels/demo.py": channel_src("demo")}, ["channels/demo.py"], enabled=False)
check("disabled pack: channel gone", channels.spec("demo") is None and channels.module("demo") is None)
write_pack("demo-pack", {"channels/demo.py": channel_src("demo")}, ["channels/demo.py"])
check("enabled again: channel back", channels.spec("demo") is not None)
import shutil  # noqa: E402
shutil.rmtree(Path(STATE) / "packs" / "demo-pack")
refresh()
check("removed pack: channel and module gone", channels.spec("demo") is None and channels.module("demo") is None)

# 4. No override of a core id; a broken module is just missing.
tele_before = channels.module("telegram")
write_pack("evil-pack", {"channels/telegram.py": channel_src("telegram"),
                         "channels/boom.py": "raise RuntimeError('boom')\n",
                         "channels/ok2.py": channel_src("ok2")},
           ["channels/telegram.py", "channels/boom.py", "channels/ok2.py"])
check("pack cannot replace a core channel", channels.module("telegram") is tele_before
      and channels.spec("telegram").pack == "", channels.spec("telegram"))
check("broken module leaves the others loaded", channels.spec("ok2") is not None
      and set(core_ids) <= set(channels.ids()), channels.ids())

# 5. Manifest paths.
loi = []
m = {"provides": {"channels": ["channels/x.py", "../x.py", "channels/../../x.py", "plugins/x.py",
                               "channels/Bad.py", "channels/sub/x.py", 5]}}
ok_paths = packs._check_channels(m, Path(STATE) / "packs" / "nope", loi)
check("manifest keeps only channels/<name>.py", ok_paths == [] or ok_paths == ["channels/x.py"], ok_paths)
check("bad manifest paths are reported", len(loi) >= 5, loi)

print()
print("FAILED: " + ", ".join(fails) if fails else "all ok")
raise SystemExit(1 if fails else 0)
