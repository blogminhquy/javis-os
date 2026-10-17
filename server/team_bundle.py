"""Share a whole team as one file, and add it in another brain (0.200.0).

Idea borrowed from OpenMausBot's "Share team": the unit people want to pass on is the TEAM, not one
partner at a time. A team file is an ordinary `javis-bundle` zip (share_bundle.py) holding the
members' partner files and their skills, plus one more entry, `javis-team.json`:

    {"format": "javis-team", "version": 1, "name", "description", "tags", "leader", "members": [slugs],
     "instructions": [pinned team messages, as text]}

Older Javis versions open the same file as a plain bundle (they ignore the extra entry and import
the partners), so a team file never breaks an old install.

What NEVER travels: chat history, keys and passwords, model choices, Auto switches, memory. Text that
looks like a secret (API keys, bearer tokens, JWTs, bot tokens, `password: ...` lines) is replaced
before it is written. A partner file arrives with its model fields and Auto switch removed, so the
person who adds the team picks those themselves.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import fastyaml

TEAM_ENTRY = "javis-team.json"
MAX_INSTRUCTIONS = 20
INSTRUCTION_CHARS = 1500
# Partner frontmatter keys that describe the sender's machine or switch work on: never shared.
DROP_KEYS = ("model", "model_provider", "reasoning", "effort", "auto", "auto_enabled", "auto_max_per_day",
             "pinned", "avatar_image", "workspace")

_SECRET_PATTERNS = [
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:(?:sk|gsk|rk|xai)[_-]|xox[baprs]-|gh[pousr]_|github_pat_|hf_|tvly-|AKIA[0-9A-Z]{16}|"
                r"AIza[0-9A-Za-z_-]{30,}|ya29\.)[A-Za-z0-9_-]*"), "[REDACTED_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED_JWT]"),
    (re.compile(r"\b\d{8,}:[-A-Za-z0-9_]{30,}\b"), "[REDACTED_BOT_TOKEN]"),
    (re.compile(r"(?i)([?&](?:token|access_token|api_?key|key|secret|signature|sig|auth)=)[^&\s\"']{8,}"),
     r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:mật\s*khẩu|password|passwd|api[_\s-]?key|secret|token)\s*[:=]\s*)\S{6,}"),
     r"\1[REDACTED]"),
]


def scrub(text: str) -> str:
    out = str(text or "")
    for pat, rep in _SECRET_PATTERNS:
        out = pat.sub(rep, out)
    return out


def clean_partner_file(text: str) -> str:
    """Drop machine-specific keys from a partner file's frontmatter and scrub secrets from all of it."""
    parts = fastyaml.split_frontmatter(text or "")
    if not parts:
        return scrub(text)
    try:
        meta = fastyaml.safe_load(parts[0]) or {}
    except Exception:
        return scrub(text)
    if not isinstance(meta, dict):
        return scrub(text)
    for k in DROP_KEYS:
        meta.pop(k, None)
    head = _dump(meta)
    return scrub("---\n" + head.strip() + "\n---\n" + parts[1].lstrip("\n"))


def _dump(meta: dict) -> str:
    import yaml
    return yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)


def team_manifest(team: dict, members: List[str], leader: str, instructions: List[str]) -> dict:
    return {
        "format": "javis-team", "version": 1,
        "name": scrub(str(team.get("name") or ""))[:120],
        "description": scrub(str(team.get("description") or ""))[:2000],
        "tags": [str(t)[:40] for t in (team.get("tags") or [])][:10],
        "leader": leader if leader in members else "",
        "members": list(dict.fromkeys(members)),
        "instructions": [scrub(str(t))[:INSTRUCTION_CHARS] for t in instructions if str(t or "").strip()][:MAX_INSTRUCTIONS],
    }


def add_team_entry(zip_bytes: bytes, manifest: dict) -> bytes:
    """Rewrite a bundle zip with every partner file cleaned and the team entry added."""
    src = zipfile.ZipFile(io.BytesIO(zip_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.startswith("agents/") and info.filename.endswith(".md"):
                data = clean_partner_file(data.decode("utf-8", "replace")).encode("utf-8")
            elif info.filename.startswith("skills/") and info.filename.endswith(".md"):
                data = scrub(data.decode("utf-8", "replace")).encode("utf-8")
            out.writestr(info.filename, data)
        out.writestr(TEAM_ENTRY, json.dumps(manifest, ensure_ascii=False, indent=1))
    return buf.getvalue()


def read_team_entry(data: bytes) -> Optional[dict]:
    """The team manifest of a file, or None when it is a plain bundle (or not a zip)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        raw = z.read(TEAM_ENTRY)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        return None
    try:
        m = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    if not isinstance(m, dict) or m.get("format") != "javis-team" or not isinstance(m.get("members"), list):
        return None
    m["members"] = [str(s) for s in m["members"] if str(s or "").strip()][:30]
    m["instructions"] = [str(t)[:INSTRUCTION_CHARS] for t in (m.get("instructions") or [])][:MAX_INSTRUCTIONS]
    m["name"] = str(m.get("name") or "Team")[:120]
    return m


def preview(data: bytes) -> Dict[str, Any]:
    """What the file holds, for the review step before adding it."""
    m = read_team_entry(data)
    if m is None:
        return {"ok": False}
    try:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    except zipfile.BadZipFile:
        names = []
    skills = sorted({n.split("/")[1] for n in names if n.startswith("skills/") and n.count("/") >= 2})
    return {"ok": True, "name": m["name"], "description": m.get("description", ""), "members": m["members"],
            "leader": m.get("leader", ""), "skills": skills, "instructions": len(m["instructions"])}


def resolve_members(manifest: dict, imported: List[str], skipped: List[str], existing: set) -> Tuple[List[str], List[str]]:
    """Members to put in the new team: partners now present in the brain (imported now, or already there
    under that slug). Returns (members, missing)."""
    have = set(existing) | {k.split(":", 1)[1] for k in imported + skipped if k.startswith("agent:")}
    members = [s for s in manifest["members"] if s in have]
    missing = [s for s in manifest["members"] if s not in have]
    return members, missing
