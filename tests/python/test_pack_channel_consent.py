"""The install screen says what a pack's inbox channel may do before the owner agrees.

    python tests/run.py pack_channel_consent

No network. Builds a pack zip in memory, runs the real `pack_install.soi` (the /packs/inspect step) on it,
then checks the dashboard draws the four powers from i18n.

Guarded here:
1. `soi` returns `channels` for a pack declaring `provides.channels`, and an empty list for one that does not.
2. packs.js draws the channel block from `d.channels`, with the four lines the maintainer listed.
3. Every string of the block exists in vi.json and en.json.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import io
import json
import os
import tempfile
import zipfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pack-consent-")

import pack_install  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def make_zip(pid: str, channels: list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        prov = f"provides:\n  channels: [{', '.join(channels)}]\n" if channels else ""
        z.writestr(f"{pid}/javis-pack.yaml",
                   f"format: javis-pack\nspec: 1\nid: {pid}\nversion: 1.0.0\n"
                   f'name: {{vi: "{pid}", en: "{pid}"}}\ndescription: {{vi: "Thử"}}\n'
                   f"compat: {{app: \">=0.1.0\"}}\n" + prov)
        for rel in channels:
            z.writestr(f"{pid}/{rel}", "from channels import KenhSpec\nSPEC = KenhSpec(id='demo', nhan='Demo', kind='bot')\n")
    return buf.getvalue()


r = pack_install.soi(make_zip("demo-chan", ["channels/demo.py"]), "demo-chan.zip")
check("inspect succeeds", r.get("ok"), r)
check("inspect lists the pack's channels", r.get("channels") == ["channels/demo.py"], r.get("channels"))
r2 = pack_install.soi(make_zip("plain-pack", []), "plain-pack.zip")
check("a pack without channels lists none", r2.get("ok") and r2.get("channels") == [], r2)

js = (DASHBOARD / "packs.js").read_text(encoding="utf-8")
check("consent screen reads d.channels", "(d.channels || [])" in js)
check("consent screen lists the four powers",
      all(f'tw("store.inspect.channel.{k}")' in js for k in ("inbox", "customers", "webhook", "code")))

keys = ["store.inspect.channel." + k for k in ("title", "inbox", "customers", "webhook", "code")]
for lang in ("vi", "en"):
    d = json.loads((DASHBOARD / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    miss = [k for k in keys if not d.get(k)]
    check(f"{lang}.json has every channel consent string", not miss, miss)
    check(f"{lang}.json title keeps the {{name}} slot", "{name}" in d.get(keys[0], ""))

print()
print("FAILED: " + ", ".join(fails) if fails else "all ok")
raise SystemExit(1 if fails else 0)
