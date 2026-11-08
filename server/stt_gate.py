"""Score a vendor's new speech-to-text model against the one in use before Javis switches to it (2026-11-08).

Owner: "do the self-scoring, in the lean form". stt_models finds a vendor's newest ear model by its name; newest is
not always best, and the risk that matters is a new model tuned for English that hears a Vietnamese sentence with
English words worse than the old one. So before a switch both models hear the same short set of sentences and the
new one is taken only when it is not worse. Runs only when a vendor shows a model Javis has not judged yet (a few
times a year per vendor), never on a schedule, and only between models of the SAME vendor: which vendor's ear goes
first stays the owner's rule (the main brain's vendor first, voice_ear.order).

The set: the sentences of tools/stt_bench/corpus.py (Vietnamese, English, and Vietnamese with English terms, read
whole by a Vietnamese voice, which is how people here speak them), made once with the free Edge voices Javis already
reads aloud with, kept in <STATE_DIR>/stt_gate/. Recordings of a real voice in <STATE_DIR>/stt_bench/real/refs.tsv
(the bench's own format: "file<TAB>exact sentence<TAB>term|term") are used too, and weigh like any other clip.

Scored like tools/stt_bench: word error rate (WER) after lowercasing and dropping punctuation, and how many of the
terms that make a command runnable ("Facebook ads", "ROAS", "John Smith") came through. Cost: about one minute of
audio per model, a few cents on a paid key.
"""
from __future__ import annotations

import asyncio
import re
import sys
import unicodedata
from pathlib import Path

VI_VOICE = "vi-VN-HoaiMyNeural"
EN_VOICE = "en-US-AriaNeural"
LANG_HINT = "vi"            # what most voice messages carry (reply or interface language); both models get the same

# (id, Edge voice, sentence, terms that must come through for the command to run). From tools/stt_bench/corpus.py.
SENTENCES = (
    ("v2", VI_VOICE, "Nhắc anh đi họp lúc ba giờ chiều", ()),
    ("v3", VI_VOICE, "Doanh thu tuần này tăng so với tuần trước", ()),
    ("e1", EN_VOICE, "Open the dashboard and show me the weekly sales report", ()),
    ("e2", EN_VOICE, "Send an email to the customer about the new order", ()),
    ("m1", VI_VOICE, "Mở dashboard Facebook ads rồi báo cáo ROAS tuần này", ("dashboard", "Facebook ads", "ROAS")),
    ("m2", VI_VOICE, "Gửi email cho khách hàng về đơn hàng mới", ("email",)),
    ("m3", VI_VOICE, "Javis ơi check inventory của sản phẩm bulong", ("Javis", "check", "inventory")),
    ("m4", VI_VOICE, "Tạo một workflow mới tên là daily report", ("workflow", "daily report")),
    ("m5", VI_VOICE, "Kết nối MCP của Pancake POS", ("MCP", "Pancake POS")),
    ("m6", VI_VOICE, "Đặt reminder họp team lúc ba giờ chiều", ("reminder", "team")),
    ("m8", VI_VOICE, "Sync dữ liệu sang Google Sheets", ("Sync", "Google Sheets")),
    ("m9", VI_VOICE, "Nhắn tin cho John Smith về deadline của dự án", ("John Smith", "deadline")),
    ("m10", VI_VOICE, "Tăng budget của campaign remarketing lên hai triệu", ("budget", "campaign", "remarketing")),
)

MIN_CLIPS = 8           # fewer clips than this (no Edge voice reachable) is no measure: nothing is decided
MIN_ANSWERED = 0.8      # a model that fails on more than a fifth of the clips is not usable
WER_MARGIN = 0.02       # two runs of the same model differ a little; the new model may be this much worse and win
TERMS_MARGIN = 1        # ... and miss at most one more term than the model in use
GAP_S = {"groq": 3.1}   # Groq's free tier allows ~20 transcriptions a minute (tools/stt_bench GROQ_GAP_S)
NUM = {"hai": "2", "ba": "3"}


# ---------------------------------------------------------------------------
# Scoring (pure)
# ---------------------------------------------------------------------------
def norm(s: str, ref: bool = False) -> list:
    s = unicodedata.normalize("NFC", str(s or "").lower())
    s = re.sub(r"[^\w\s]", " ", s, flags=re.U).replace("_", " ")
    toks = s.split()
    return [NUM.get(w, w) for w in toks] if ref else toks


def edit_distance(a: list, b: list) -> int:
    d = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, d[0] = d[:], i
        for j, y in enumerate(b, 1):
            d[j] = min(prev[j] + 1, d[j - 1] + 1, prev[j - 1] + (x != y))
    return d[-1]


def has_term(hyp: list, term: str) -> bool:
    tt = norm(term)
    n = len(tt)
    if any(hyp[i:i + n] == tt for i in range(len(hyp) - n + 1)):
        return True
    return "".join(tt) in "".join(hyp)


def score(rows: list) -> dict:
    """rows [{"ref", "hyp" (None = the model failed on that clip), "terms"}] ->
    {"wer", "terms", "terms_total", "answered", "clips"}. A failed clip counts every word wrong."""
    err = n = hit = total = answered = 0
    for r in rows:
        ref = norm(r["ref"], True)
        hyp = norm(r["hyp"]) if r.get("hyp") is not None else []
        answered += r.get("hyp") is not None
        err += edit_distance(ref, hyp)
        n += len(ref)
        hits = [has_term(hyp, t) for t in r.get("terms") or ()]
        hit += sum(hits)
        total += len(hits)
    return {"wer": round(err / n, 3) if n else 1.0, "terms": hit, "terms_total": total, "answered": answered,
            "clips": len(rows)}


def verdict(current: dict, candidate: dict) -> tuple:
    """(take the candidate?, reason). Not worse than the model in use is enough: when equal, the newer one wins, so
    Javis keeps up with the vendor."""
    clips = max(1, candidate.get("clips") or 0)
    if candidate.get("answered", 0) / clips < MIN_ANSWERED:
        return False, "candidate_fails"
    if (current.get("answered", 0) / max(1, current.get("clips") or 0)) < MIN_ANSWERED:
        return True, "current_fails"           # the model in use no longer answers (retired): anything working wins
    if candidate["wer"] > current["wer"] + WER_MARGIN:
        return False, "more_word_errors"
    if candidate["terms"] < current["terms"] - TERMS_MARGIN:
        return False, "fewer_terms"
    return True, "not_worse"


# ---------------------------------------------------------------------------
# The clips
# ---------------------------------------------------------------------------
def _dir() -> Path:
    import config as cfgmod
    d = Path(cfgmod.STATE_DIR) / "stt_gate"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _tts(text: str, voice: str) -> bytes:
    import edge_tts
    buf = bytearray()
    async for chunk in edge_tts.Communicate(text, voice).stream():
        if chunk.get("type") == "audio":
            buf.extend(chunk.get("data") or b"")
    return bytes(buf)


def _real_clips() -> list:
    import config as cfgmod
    d = Path(cfgmod.STATE_DIR) / "stt_bench" / "real"
    refs = d / "refs.tsv"
    out = []
    try:
        lines = refs.read_text(encoding="utf-8").splitlines() if refs.exists() else []
    except OSError:
        lines = []
    for line in lines:
        cols = line.split("\t")
        if line.startswith("#") or len(cols) < 2 or not cols[0].strip() or not cols[1].strip():
            continue
        p = d / cols[0].strip()
        if p.is_file():
            terms = tuple(t.strip() for t in (cols[2] if len(cols) > 2 else "").split("|") if t.strip())
            out.append({"id": "real:" + p.name, "text": cols[1].strip(), "terms": terms, "data": p.read_bytes(),
                        "name": p.name})
    return out


def _cached(path: Path) -> bytes:
    """A clip already on disk, b"" when there is none (or it is too short to be one)."""
    try:
        return path.read_bytes() if path.is_file() and path.stat().st_size >= 1000 else b""
    except OSError:
        return b""


def _keep(path: Path, audio: bytes) -> None:
    path.write_bytes(audio)


async def clips() -> list:
    """[{"id", "text", "terms", "data", "name"}]: the synthetic set (made once, then read from disk) plus real
    recordings. [] when fewer than MIN_CLIPS could be had. Disk work runs in a thread, off the event loop."""
    d = await asyncio.to_thread(_dir)
    out = []
    for cid, voice, text, terms in SENTENCES:
        f = d / f"{cid}.mp3"
        try:
            audio = await asyncio.to_thread(_cached, f)
            if not audio:
                audio = await _tts(text, voice)
                if len(audio) < 1000:
                    continue
                await asyncio.to_thread(_keep, f, audio)
            out.append({"id": cid, "text": text, "terms": terms, "data": audio, "name": f.name})
        except Exception as e:  # noqa: BLE001 - a clip we cannot make is one clip less
            print(f"[stt gate] clip {cid}: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
    out += await asyncio.to_thread(_real_clips)
    return out if len(out) >= MIN_CLIPS else []


# ---------------------------------------------------------------------------
# Running both models
# ---------------------------------------------------------------------------
async def _hear_all(vendor: str, key: str, model: str, items: list) -> dict:
    import stt
    rows = []
    gap = GAP_S.get(vendor, 0.3)
    for i, c in enumerate(items):
        if i:
            await asyncio.sleep(gap)
        res = await stt.transcribe_with(vendor, c["data"], c["name"], key, model, LANG_HINT)
        if res.get("ok"):
            hyp = str(res.get("text") or "")
        elif res.get("ly_do") == "khong_nghe_ro":
            hyp = ""                       # answered, heard nothing: every word wrong, but the model works
        else:
            hyp = None
        rows.append({"ref": c["text"], "hyp": hyp, "terms": c["terms"]})
    return score(rows)


async def compare(vendor: str, key: str, current: str, candidate: str) -> dict:
    """{"ok": True | False | None, "reason", "current": score, "candidate": score}. None: nothing could be measured
    (no clips), so nothing is decided."""
    items = await clips()
    if not items:
        return {"ok": None, "reason": "no_clips", "current": {}, "candidate": {}}
    cur = await _hear_all(vendor, key, current, items)
    cand = await _hear_all(vendor, key, candidate, items)
    ok, why = verdict(cur, cand)
    print(f"[stt gate] {vendor}: {current} WER {cur['wer']} terms {cur['terms']}/{cur['terms_total']} | "
          f"{candidate} WER {cand['wer']} terms {cand['terms']}/{cand['terms_total']} -> "
          f"{'switch' if ok else 'keep'} ({why})", file=sys.stderr)
    return {"ok": ok, "reason": why, "current": cur, "candidate": cand}
