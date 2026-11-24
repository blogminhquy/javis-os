"""Javis Gate notes open in the brain the owner used last, not in a pinned chat's brain (#1726).

    python tests/run.py gate_note_latest_brain -v      (no network)

`chat_bridge` opened the "From <AI>: <name>" conversation in the brain of `list_sessions(limit=1)`. That list puts
pinned conversations first, so a chat pinned weeks ago in a secondary brain won, and claude.ai notes were written into
that brain (reported twice, 07/11 and 22/11). `sessions.brain_gan_nhat` is the "open brain" the MCP hub already uses
for Gate file tools; notes and transcripts now use it too.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="gate-note-brain-")

import chat_bridge as CB  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  {info!r}"))
    if not cond:
        _fails.append(name)


class FakeStore:
    """Pinned chat in the side brain comes first in the list; the brain used last is the main one."""

    def __init__(self):
        self.created = []

    def list_sessions(self, limit=50, **_kw):
        return [{"id": "pinned", "brain": "Side Brain", "pinned": 1},
                {"id": "recent", "brain": "Main Brain", "pinned": 0}][:limit]

    def brain_gan_nhat(self):
        return "Main Brain"

    def get_session(self, sid):
        return None

    def create_session(self, brain, **kw):
        self.created.append(brain)
        return f"s{len(self.created)}"


CB._doc_so = lambda: {}
CB._ghi_so = lambda d: None

st = FakeStore()
CB._phien_ghi_chep(st, "claude.ai", "Plan")
check("a Gate note opens in the brain used last, not the pinned chat's brain", st.created == ["Main Brain"], st.created)


class OldStore(FakeStore):
    def brain_gan_nhat(self):
        raise AttributeError("older store")


st = OldStore()
check("an older store without the helper still gets a brain", CB._latest_brain(st) == "Side Brain")


class EmptyStore(FakeStore):
    def brain_gan_nhat(self):
        return ""

    def list_sessions(self, limit=50, **_kw):
        return []


check("no conversation at all falls back to the default brain name", CB._latest_brain(EmptyStore()) == "brain")

src = Path(CB.__file__).read_text(encoding="utf-8")
check("no Gate path picks a brain from the pinned-first list any more",
      src.count("brain=_latest_brain(st)") == 2)

if _fails:
    raise SystemExit(f"{len(_fails)} failed")
print("all ok")
