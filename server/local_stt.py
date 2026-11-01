"""Offline speech-to-text (0.435.0): Whisper running on the machine itself, no API key, nothing leaves the machine.

Owner, 2026-11-01: hear voice messages and the sound of customers' videos without Groq, with a second road when the
first is not there ("không dùng được cái này thì dùng cái khác"). The API ears (Groq, OpenAI, Gemini) live in `stt.py`;
this is the one that needs no key. It is an OPTIONAL tool (`optional_tools`, card on the Tools page): the library is
~450MB and the model another ~500MB, which most installs never need, so nothing is downloaded until the owner presses
Install. Both land in STATE_DIR, so they survive updates and Docker rebuilds.

How it runs: faster-whisper (CTranslate2, int8 on CPU) in a SEPARATE process (`offline_ear/worker.py`) with the
library on its own path, never imported into the server: its numpy/onnxruntime/huggingface versions cannot clash with
the server's, its memory is returned when it exits, and a stuck run can be killed. One run at a time (`_ONE`): on a
small VPS two at once would starve the server itself.

Cost the owner should know (also on the card): a 30 second clip takes roughly 5 to 30 seconds depending on the CPU,
and the "small" model hears Vietnamese less well than Groq's large Whisper. `JAVIS_LOCAL_STT_MODEL` picks another size
(base, small, medium, large-v3-turbo) for a stronger or weaker machine.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Optional

import localefmt
import winproc
from config import STATE_DIR

ROOT = STATE_DIR / "local-ear"
LIB_DIR = ROOT / "lib"
MODEL_DIR = ROOT / "models"
TMP_DIR = ROOT / "tmp"
WORKER = Path(__file__).resolve().parent / "offline_ear" / "worker.py"
MODEL = (os.getenv("JAVIS_LOCAL_STT_MODEL") or "small").strip() or "small"
TIMEOUT = 600.0          # one transcription; a long clip on a slow CPU, never forever
INSTALL_TIMEOUT = 1800.0  # ~1GB over a slow VPS link
SIZE_HINT = "~1 GB"
_ONE = asyncio.Lock()


def describe() -> dict:
    return {
        "id": "local_ear",
        "ten": localefmt.chu("Bộ nghe offline (Whisper)", "Offline ear (Whisper)"),
        "mo_ta": localefmt.chu(
            "Nghe tin thoại và lời nói trong video khách gửi ngay trên máy này, không cần API key nào. Javis chỉ dùng "
            "khi không có key Groq, OpenAI hay Gemini, hoặc các key đó đang lỗi. Tải về khoảng 1 GB. Máy yếu nghe chậm "
            "hơn (một video 30 giây mất vài chục giây) và nghe tiếng Việt kém hơn Groq.",
            "Hears voice messages and the speech in customers' videos on this machine, with no API key. Javis uses it "
            "only when there is no Groq, OpenAI or Gemini key, or those keys fail. About 1 GB to download. A weak "
            "machine hears slowly (a 30 second video can take tens of seconds) and less accurately than Groq."),
        "dung_luong_uoc": SIZE_HINT,
    }


def _lib_ready() -> bool:
    return (LIB_DIR / "faster_whisper").is_dir()


def _model_ready() -> bool:
    try:
        return any(MODEL_DIR.rglob("model.bin"))
    except OSError:
        return False


def installed() -> bool:
    """Library and model are both on disk: `transcribe` can run."""
    return _lib_ready() and _model_ready()


def _size(p: Path) -> int:
    n = 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                n += f.stat().st_size
    except OSError:
        pass
    return n


def status(d: dict, job: dict) -> dict:
    """Fill the card fields of `optional_tools.trang_thai` for this tool."""
    if job.get("dang_chay"):
        tt, why = "dang_cai", localefmt.chu("Đang tải bộ nghe về, việc này mất vài phút.",
                                            "Downloading the offline ear, this takes a few minutes.")
    elif installed():
        tt, why = "san_sang", localefmt.chu(f"Sẵn sàng, mô hình {MODEL}.", f"Ready, model {MODEL}.")
    elif ROOT.exists():
        tt, why = "chua_cai", localefmt.chu("Bản tải về chưa đủ (thiếu thư viện hoặc mô hình). Bấm cài lại.",
                                            "The download is incomplete (library or model missing). Install again.")
    else:
        tt, why = "chua_cai", localefmt.chu("Chưa cài. Không có key nào thì Javis chưa nghe được tin thoại.",
                                            "Not installed. Without a key Javis cannot hear voice messages yet.")
    d.update({"trang_thai": tt, "ly_do": why, "go_duoc": ROOT.exists() and not job.get("dang_chay"),
              "duong_dan": str(ROOT) if ROOT.exists() else "",
              "dung_luong": _doc_mb(_size(ROOT)) if ROOT.exists() else ""})
    return d


def _doc_mb(n: int) -> str:
    return f"{n / 1024 / 1024:.0f} MB" if n else ""


def install_command() -> tuple:
    """(argv, cwd, env, timeout, error when Python cannot run) for `optional_tools._chay_tai`."""
    ROOT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["HF_HOME"] = str(ROOT / "hf")      # the Docker user's home may not be writable; STATE_DIR is
    return ([sys.executable, "-s", str(WORKER), "--install", "--lib", str(LIB_DIR), "--model", MODEL,
             "--model-dir", str(MODEL_DIR)],
            str(ROOT), env, INSTALL_TIMEOUT,
            localefmt.chu("Không chạy được Python để cài bộ nghe.", "Python could not be run to install the ear."))


def remove() -> dict:
    if not ROOT.exists():
        return {"ok": False, "error": localefmt.chu("Bộ nghe offline chưa được cài.", "The offline ear is not installed.")}
    shutil.rmtree(ROOT, ignore_errors=True)
    return {"ok": True}


def _last_json(out: str) -> dict:
    for line in reversed((out or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


async def transcribe(data: bytes, file_name: str = "audio", lang: Optional[str] = None) -> dict:
    """Same contract as `stt.groq_nghe`: {"ok", "text", "model"} or {"ok": False, "ly_do", "noi_voi_javis"}."""
    import stt
    if not installed():
        return {"ok": False, "ly_do": "thieu_key", "noi_voi_javis": stt.loi_thanh_dong("thieu_key")}
    if not data:
        return {"ok": False, "ly_do": "rong", "noi_voi_javis": stt.loi_thanh_dong("loi", "file rỗng")}
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ext = os.path.splitext(str(file_name or ""))[1][:8] or ".bin"
    src = TMP_DIR / (uuid.uuid4().hex + ext)
    src.write_bytes(data)
    env = dict(os.environ, HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", PYTHONNOUSERSITE="1",
               HF_HOME=str(ROOT / "hf"))
    try:
        async with _ONE:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-s", str(WORKER), "--lib", str(LIB_DIR), "--model", MODEL, "--model-dir",
                str(MODEL_DIR), "--lang", str(lang or ""), str(src),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=str(ROOT), env=env, **winproc.kwargs_no_window())
            try:
                out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {"ok": False, "ly_do": "loi",
                        "noi_voi_javis": stt.loi_thanh_dong("loi", "bộ nghe offline chạy quá lâu")}
        res = _last_json(out.decode("utf-8", "replace"))
        if not res.get("ok"):
            why = str(res.get("error") or err.decode("utf-8", "replace")[-200:] or f"mã {proc.returncode}")
            print(f"[stt local] {why}", file=sys.stderr)
            return {"ok": False, "ly_do": "loi", "noi_voi_javis": stt.loi_thanh_dong("loi", why[:200])}
        text = stt.loc_ao_giac(str(res.get("text") or "").strip())
        if not text:
            return {"ok": False, "ly_do": "khong_nghe_ro", "noi_voi_javis": stt.loi_thanh_dong("khong_nghe_ro")}
        return {"ok": True, "text": text, "model": "whisper-" + MODEL + " (offline)"}
    except Exception as e:      # noqa: BLE001 - a broken ear must never cost the message
        print(f"[stt local] {type(e).__name__}: {e}", file=sys.stderr)
        return {"ok": False, "ly_do": "loi", "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}")}
    finally:
        src.unlink(missing_ok=True)
