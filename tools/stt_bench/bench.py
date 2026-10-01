"""Bộ đo tai nghe (STT) cho câu Việt pha tiếng Anh.

    .venv/Scripts/python tools/stt_bench/bench.py synth           # sinh 26 clip giọng tổng hợp
    .venv/Scripts/python tools/stt_bench/bench.py run groq        # cho tai Groq nghe hết các clip
    .venv/Scripts/python tools/stt_bench/bench.py score           # bảng điểm mọi tai đã chạy + mốc 01/10

Vì sao có (0.65.15, docs/dev/2026-10-voice-call-spec.md mục 2): đổi tai hay đổi model mà không có số đo
thì chỉ là đoán. Bộ này chấm trên cùng một bộ câu (corpus.py) bằng ba con số:
  - WER: tỉ lệ từ sai (thêm, bớt, thay) sau khi bỏ dấu câu và chữ hoa; "hai"/"ba" coi như 2/3.
  - terms: số thuật ngữ nghe đúng (tên công cụ, tên người, số liệu quảng cáo).
  - commands_full: số câu lệnh đúng TRỌN mọi thuật ngữ, tức là chạy được ngay không cần hỏi lại.

Tai Groq chạy qua ĐÚNG đường của Javis (voice_ear.transcribe_upload: mồi từ vựng, lọc câu bịa,
sửa tên trợ lý), nên số đo là số người dùng nhận được, không phải số của model trần.

Dữ liệu KHÔNG lên git, nằm ở <JAVIS_STATE_DIR>/stt_bench/:
  wav/<uid>.wav            clip sinh bằng Edge TTS
  results/<tai>.jsonl      mỗi dòng {"uid", "text", "seconds"}
  real/refs.tsv            (tuỳ chọn) giọng thật: "tên file<TAB>câu đúng<TAB>thuật ngữ|thuật ngữ"
Đặt STT_BENCH_DIR để dữ liệu nằm chỗ khác. Cần key Groq thì chạy với JAVIS_STATE_DIR trỏ tới
thư mục có settings.json thật, ví dụ
    set JAVIS_STATE_DIR=D:\\Project\\Javis-OS\\server
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402

VI_VOICE = "vi-VN-HoaiMyNeural"
EN_VOICE = "en-US-AriaNeural"
BASELINE = HERE / "baseline_2026-10-01.json"
NUM = {"hai": "2", "ba": "3"}
GROQ_GAP_S = 3.1


def data_dir() -> Path:
    import config as cfgmod
    # STT_BENCH_DIR: để dữ liệu đo ngoài thư mục trạng thái (ví dụ đọc key từ settings.json thật
    # mà không ghi clip vào đó).
    d = Path(os.environ.get("STT_BENCH_DIR") or Path(cfgmod.STATE_DIR) / "stt_bench")
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- chấm điểm
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
    """rows: [{"ref", "hyp", "terms"}] -> {"WER", "terms", "commands_full"}."""
    err = n = hit = total = full = cmds = 0
    for r in rows:
        ref, hyp = norm(r["ref"], True), norm(r["hyp"])
        err += edit_distance(ref, hyp)
        n += len(ref)
        if r["terms"]:
            hits = [has_term(hyp, t) for t in r["terms"]]
            hit += sum(hits)
            total += len(hits)
            cmds += 1
            full += all(hits)
    return {"WER": round(err / n, 3) if n else None,
            "terms": f"{hit}/{total}" if total else "-",
            "commands_full": f"{full}/{cmds}" if cmds else "-"}


# ---------------------------------------------------------------- sinh clip
def _ffmpeg(args: list) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


async def _tts(text: str, voice: str, out: Path) -> None:
    import edge_tts
    if not out.exists():
        await edge_tts.Communicate(text, voice).save(str(out))


async def synth() -> None:
    """26 clip 16 kHz mono, 3 giây im trước và 2 giây im sau (giống mic thật mở trước khi nói)."""
    d = data_dir()
    wav_dir, mp3_dir = d / "wav", d / "mp3"
    wav_dir.mkdir(exist_ok=True)
    mp3_dir.mkdir(exist_ok=True)
    for c in corpus.clips():
        wav = wav_dir / f'{c["uid"]}.wav'
        if wav.exists():
            continue
        if c["variant"] == "a":
            mp3 = mp3_dir / f'{c["uid"]}.mp3'
            await _tts(c["text"], EN_VOICE if c["kind"] == "pure_en" else VI_VOICE, mp3)
            _ffmpeg(["-i", str(mp3), "-ac", "1", "-ar", "16000", "-af", "adelay=3000,apad=pad_dur=2", str(wav)])
            continue
        parts = []
        for i, (lang, text) in enumerate(c["seg"]):
            p = mp3_dir / f'{c["uid"]}_{i}.mp3'
            await _tts(text, VI_VOICE if lang == "v" else EN_VOICE, p)
            parts.append(p)
        ins = []
        for p in parts:
            ins += ["-i", str(p)]
        trim = ("aresample=16000,aformat=channel_layouts=mono,silenceremove=start_periods=1:start_threshold=-45dB,"
                "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,apad=pad_dur=0.12")
        filt = "".join(f"[{i}:a]{trim}[a{i}];" for i in range(len(parts)))
        filt += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1,adelay=3000,apad=pad_dur=2[o]"
        _ffmpeg(ins + ["-filter_complex", filt, "-map", "[o]", "-ar", "16000", "-ac", "1", str(wav)])
    print(f"{len(list(wav_dir.glob('*.wav')))} clip trong {wav_dir}")


# ---------------------------------------------------------------- chạy tai
def _real_clips(d: Path) -> list:
    refs = d / "real" / "refs.tsv"
    if not refs.exists():
        return []
    out = []
    for line in refs.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0].strip() and not line.startswith("#"):
            terms = [t.strip() for t in (cols[2] if len(cols) > 2 else "").split("|") if t.strip()]
            out.append(dict(uid="real:" + cols[0].strip(), kind="real", variant="", text=cols[1].strip(),
                            terms=terms, path=d / "real" / cols[0].strip()))
    return out


async def run_groq() -> None:
    import config as cfgmod
    import voice_ear
    cfg = cfgmod.read_settings()
    if not (cfg.get("model") or {}).get("groq_api_key"):
        raise SystemExit("Chưa có key Groq trong settings.json. Đặt JAVIS_STATE_DIR tới thư mục có settings.json thật.")
    d = data_dir()
    items = [dict(c, path=d / "wav" / f'{c["uid"]}.wav') for c in corpus.clips()] + _real_clips(d)
    out_path = d / "results" / "groq.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fo:
        for c in items:
            if not c["path"].exists():
                print("thiếu", c["path"], "- chạy synth trước")
                continue
            # Groq bậc miễn phí chặn ở 20 lượt mỗi phút: giãn cách, không thì nửa sau ra rỗng.
            await asyncio.sleep(GROQ_GAP_S)
            t0 = time.perf_counter()
            # lang "vi-VN" như dashboard mặc định; draft rỗng: đo chính tai, không đối chiếu nháp.
            res = await voice_ear.transcribe_upload(cfg, c["path"].read_bytes(), c["path"].name, "vi-VN", "")
            dt = time.perf_counter() - t0
            text = res.get("text", "") if res.get("ok") else ""
            fo.write(json.dumps({"uid": c["uid"], "text": text, "seconds": round(dt, 2),
                                 "error": "" if res.get("ok") else res.get("ly_do", "")}, ensure_ascii=False) + "\n")
            print(f'{c["uid"]:8s} {dt:4.1f}s  {text}')
    print("ghi", out_path)


# ---------------------------------------------------------------- bảng điểm
def _load_results(d: Path) -> dict:
    ears = {}
    if BASELINE.exists():
        for name, texts in json.loads(BASELINE.read_text(encoding="utf-8"))["ears"].items():
            ears[f"{name} (01/10)"] = {"texts": texts, "seconds": []}
    for p in sorted((d / "results").glob("*.jsonl")) if (d / "results").exists() else []:
        texts, secs = {}, []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                texts[r["uid"]] = r.get("text", "")
                if r.get("seconds") is not None:
                    secs.append(r["seconds"])
        ears[p.stem] = {"texts": texts, "seconds": secs}
    return ears


def report() -> None:
    d = data_dir()
    clips = corpus.clips() + _real_clips(d)
    groups = [
        ("Câu pha, giọng Việt đọc tiếng Anh (a)", lambda c: c["kind"] == "mixed" and c["variant"] == "a"),
        ("Câu pha, tiếng Anh bản xứ (b)", lambda c: c["kind"] == "mixed" and c["variant"] == "b"),
        ("Câu pha, tất cả", lambda c: c["kind"] == "mixed"),
        ("Tiếng Việt thuần", lambda c: c["kind"] == "pure_vi"),
        ("Tiếng Anh thuần", lambda c: c["kind"] == "pure_en"),
        ("Giọng thật", lambda c: c["kind"] == "real"),
    ]
    ears = _load_results(d)
    for title, pred in groups:
        cs = [c for c in clips if pred(c)]
        if not cs:
            continue
        print(f"\n== {title} (n={len(cs)})")
        for name, ear in ears.items():
            rows = [{"ref": c["text"], "hyp": ear["texts"][c["uid"]], "terms": c["terms"]}
                    for c in cs if c["uid"] in ear["texts"]]
            if rows:
                print(f"   {name:28s} {score(rows)}  ({len(rows)} clip)")
    for name, ear in ears.items():
        secs = sorted(ear["seconds"])
        if secs:
            print(f"\n{name}: thời gian mỗi câu trung vị {secs[len(secs) // 2]:.2f}s, chậm nhất {secs[-1]:.2f}s")


def main(argv: list) -> None:
    cmd = argv[1] if len(argv) > 1 else "score"
    if cmd == "synth":
        asyncio.run(synth())
    elif cmd == "run" and len(argv) > 2 and argv[2] == "groq":
        asyncio.run(run_groq())
    elif cmd == "score":
        report()
    else:
        print(__doc__)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    main(sys.argv)
