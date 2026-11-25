"""Put one Javis effort level on one engine, whatever its kind (background work, bots and team
steps run the effort that was picked, never another one). Lives outside main.py so aux_engine can use it too."""
from __future__ import annotations

# Javis level -> Claude Code `--effort` value. "ultra" is Javis's name for the top step, Claude Code calls it "max".
CLAUDE_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh", "ultra": "max"}

# Effort names of the other CLIs, light to heavy, matched against what each CLI declares in its `--help`.
CLI_LADDER = ("low", "medium", "high", "xhigh", "max")
_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "ultra": 4}


def flag_for(mod, level) -> list:
    """The highest effort flag this CLI really declares, from the picked level downward ([] = none). Stepping down
    keeps the order: a top level the CLI lacks becomes the next one it has, never something weaker than that."""
    rank = _RANK.get(level or "")
    if rank is None:
        return []
    for name in reversed(CLI_LADDER[:rank + 1]):
        flag = mod.co_effort(name)
        if flag:
            return flag
    return []


def set_claude(eng, level) -> bool:
    """Claude Code (CLI or SDK engine). False = nothing set (level off, or a build without `--effort`)."""
    import claude_cli
    value = CLAUDE_EFFORT.get(level or "")
    if not value or not claude_cli.co_co("--effort"):
        return False
    eng.effort = value
    return True


def set_codex(eng, level) -> str:
    """Codex CLI: replace the `model_reasoning_effort` override with the one for `level`. Returns the value passed;
    "" = none, and then no earlier override stays behind either."""
    import codex_models
    value = codex_models.effort_arg(getattr(eng, "model", "") or "", level)
    eng.extra_config[:] = [x for x in eng.extra_config if not str(x).startswith("model_reasoning_effort=")]
    if value:
        eng.extra_config.append(f"model_reasoning_effort={value}")
    return value


def set_flag_cli(eng, mod, level) -> bool:
    """Grok Build / Antigravity. A model whose name already fixes the depth gets no flag."""
    locked = getattr(mod, "model_khoa_effort", None)
    if locked and locked(getattr(eng, "model", "") or ""):
        return False
    flag = flag_for(mod, level)
    if flag:
        eng.effort = flag[1]
    return bool(flag)
