"""Background jobs on an API-key engine carry a short rule set instead of CLAUDE.md (token saving, phase 3, 2026-11-18).

Owner, 18/11/2026, chose option 2: a Kanban job, loop or reminder on an API key sends `background_prompt.CONTRACT` in
place of CLAUDE.md, at the saving levels, for a share of jobs first. Checked here:
  1. CLAUDE.md has not changed since the contract was checked against it (a new rule must be read first).
  2. Only the CLAUDE.md head is swapped; the rest of the prompt, an assistant's role included, stays byte for byte.
  3. Only Kanban jobs, loops and reminders; learning, workflows, teams and side work keep their prompt.
  4. The switches: Off level, env, the share of jobs; one Kanban job always gets the same variant.
  5. The contract keeps the rules about acting, and no em dash.
  6. Wired into the API background engine only; subscription engines are untouched.
  7. The real background prompt starts with CLAUDE.md, so the swap happens in practice.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import hashlib
import json
import os
import tempfile
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bgp-")
os.environ.pop("JAVIS_BG_LEAN_PROMPT", None)

import config as cfg  # noqa: E402
import background_prompt as bp  # noqa: E402

fails = []


def check(name, ok, extra=None):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok or extra is None else f"  [{extra}]"))
    if not ok:
        fails.append(name)


# ───────────────────────── 1. CLAUDE.md reviewed ─────────────────────────
_sha = hashlib.sha256((ROOT / "CLAUDE.md").read_bytes()).hexdigest()
check("CLAUDE.md is the one the background contract was checked against "
      "(it changed: read the new rule, carry it into background_prompt.CONTRACT if a background job needs it, then set "
      "REVIEWED_CLAUDE_MD_SHA256 to the new hash)",
      _sha == bp.REVIEWED_CLAUDE_MD_SHA256, _sha)

# ───────────────────────── 2. only the CLAUDE.md head is swapped ─────────────────────────
HEAD = bp.claude_md()
check("CLAUDE.md is read", len(HEAD) > 20_000, len(HEAD))
TAIL = "\n\n# === HỒ SƠ NGƯỜI DÙNG ===\nprofile\n\n# === NGÔN NGỮ ===\nlang rules\n\n# Persona\nYou are Lan."
full = HEAD + TAIL
lean = bp.lean(full)
check("the lean prompt is the contract plus the rest, byte for byte", lean == bp.CONTRACT + TAIL)
check("a prompt not starting with CLAUDE.md is left alone", bp.lean("You are Lan, an assistant.\n" + HEAD) is None)
check("an empty prompt is left alone", bp.lean("") is None)

# ───────────────────────── 3. which jobs ─────────────────────────
with patch.dict(os.environ, {"JAVIS_BG_LEAN_PROMPT": "1"}):
    for tag in ("dispatch:t_1:execute", "dispatch:t_1:specifier", "reminder", "reminder:r_9", "loop", "loop-main"):
        check(f"job '{tag}' gets the short rules", bp.for_api(full, tag, "job text") == bp.CONTRACT + TAIL)
    for tag in ("learn", "curator", "workflow", "team", "next-prompt", "reply-policy", "ingest", "habit-coach",
                "auto-background", "gh-review", "aux", ""):
        check(f"'{tag or 'no tag'}' keeps its prompt", bp.for_api(full, tag, "job text") == full)
    check("a Kanban job given to an assistant keeps the assistant's role",
          bp.for_api(full, "dispatch:t_2:execute").endswith("# Persona\nYou are Lan."))

# ───────────────────────── 4. the switches ─────────────────────────
def set_level(level, source="user"):
    s = cfg.read_settings()
    s.setdefault("context_runtime", {})["preset_choice"] = {"level": level, "source": source}
    cfg.write_settings(s)


def set_bps(bps):
    s = cfg.read_settings()
    s.setdefault("context_runtime", {})["background_prompt"] = {"allocation_basis_points": bps}
    cfg.write_settings(s)


set_level("max")
with patch.dict(os.environ, {"JAVIS_BG_LEAN_PROMPT": "0"}):
    check("JAVIS_BG_LEAN_PROMPT=0 keeps the full prompt", bp.for_api(full, "loop") == full)
set_level("off")
with patch.dict(os.environ, {"JAVIS_BG_LEAN_PROMPT": "1"}):
    check("the Off saving level keeps the full prompt, even with the env on", bp.for_api(full, "loop") == full)
set_level("off", source="auto")
with patch.dict(os.environ, {"JAVIS_BG_LEAN_PROMPT": "1"}):
    check("only the owner's own choice of Off counts", bp.for_api(full, "loop") != full)
set_level("saving")
set_bps(0)
check("a share of 0 keeps every job full", all(bp.for_api(full, f"dispatch:t_{i}:execute") == full for i in range(200)))
set_bps(10_000)
check("a share of 100% makes every job short", all(bp.for_api(full, f"dispatch:t_{i}:execute") != full
                                                   for i in range(200)))
s = cfg.read_settings()
s["context_runtime"].pop("background_prompt", None)
cfg.write_settings(s)
_share = sum(bp.assigned(f"dispatch:t_{i}:execute") for i in range(4000)) / 4000
check("by default about 10% of jobs", 0.07 <= _share <= 0.13, _share)
check("one Kanban job gets the same variant on every run (specifier, execute, retries)",
      len({bp.assigned(f"dispatch:t_77:{x}") for x in ("specifier", "execute", "accept", "execute")}) == 1)
check("one loop gets the same variant every iteration",
      len({bp.assigned("loop", "Mỗi vòng: kiểm tra đơn POS mới" + ("." * 400) + str(i)) for i in range(20)}) == 1)

# ───────────────────────── 5. the contract ─────────────────────────
C = bp.CONTRACT
for need, why in [
    ("`full`", "permission level full"), ("`auto`", "permission level auto"), ("`suggest`", "permission level suggest"),
    ("cannot be undone", "outside actions are final"),
    ("never invent numbers", "real data only"), ("only after the tool returned success", "confirm only on success"),
    ("[[NEEDS_INPUT]]", "a Kanban job's own way to ask"), ("does not ask", "a full reminder does not ask"),
    ("Javis/index.md", "duplicate check"), ("javis-builder", "templates from the skill"),
    ("`agents/<slug>.md`", "flat agent path"), ("never `Javis/agents|workflows`", "old path banned"),
    ("150 characters", "description cap"), ("`enabled: false`", "new loop and plugin off"),
    ("`javis_plugin`", "plugins through the tool"), ("`min_mode`", "plugin permission"),
    ("`owner_chat`", "loop result recipient"), ("`chat_id`", "job result recipient"),
    ("Data Cache", "cache rules"), ("zalo_send_message", "Zalo tools"), ("`threadId`", "Zalo thread check"),
    ("javis_zalo_send", "the old Zalo tool named as banned"), ("javis_generate_image", "images"),
    ("javis_job", "long shell work"), ("I will report back", "no empty promises"),
    ("orchestration is", "queued is not running"), ("JAVIS_LESSON", "agent lessons"),
    ("memory/facts/", "memory rules"), ("U+2014", "the em dash ban"), ("NGÔN NGỮ", "language follows the block"),
]:
    check(f"the contract keeps: {why}", need in C, need)
check("the contract has no em or en dash", chr(0x2014) not in C and chr(0x2013) not in C)
check("the contract is far shorter than CLAUDE.md", len(C) < 0.35 * len(HEAD), (len(C), len(HEAD)))

# ───────────────────────── 6. wiring ─────────────────────────
_aux = (SERVER / "aux_engine.py").read_text(encoding="utf-8")
check("the API background engine sends the result of for_api",
      "sysprompt = background_prompt.for_api(self.system_prompt or \"\", self.tag, prompt)" in _aux)
check("and nothing else in aux_engine calls it (subscription engines keep CLAUDE.md)", _aux.count("for_api(") == 1)

# ───────────────────────── 7. in practice ─────────────────────────
import main  # noqa: E402

_real = main._background_system_prompt("brain")
check("the real background prompt starts with CLAUDE.md", _real.startswith(HEAD))
_short = bp.lean(_real)
check("so the swap happens, and it saves more than half", _short is not None and len(_short) < 0.5 * len(_real),
      (len(_real), len(_short or "")))
check("everything after CLAUDE.md stays", _short is not None and _short.endswith(_real[len(HEAD):]))

set_bps(10_000)
before = (bp.stats().get("loop") or {}).get("runs", 0)
bp.for_api(_real, "loop", "x")
row = bp.stats().get("loop") or {}
check("a short run is tallied with what it saved", row.get("runs") == before + 1
      and row.get("chars_full", 0) - row.get("chars_sent", 0) > 15_000, row)

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
