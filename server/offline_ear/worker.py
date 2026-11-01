"""Offline Whisper worker (0.435.0). Run by `server/local_stt.py` as a separate process, never imported by the server.

Lives in its own folder on purpose: Python puts the script's folder first on `sys.path`, and `server/` holds modules
whose names could shadow a library faster-whisper needs. Here the only neighbour is this file.

Two modes; the LAST stdout line is the JSON result (install also prints plain progress lines):
  --install   pip-install faster-whisper into --lib, then download --model into --model-dir
  <audio>     transcribe one audio file with the downloaded model
"""
import argparse
import json
import os
import subprocess
import sys

PACKAGE = "faster-whisper>=1.1,<2"


def say(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def load(lib, model, model_dir, threads=0):
    sys.path.insert(0, lib)
    from faster_whisper import WhisperModel
    return WhisperModel(model, device="cpu", compute_type="int8", download_root=model_dir, cpu_threads=threads or 0)


def install(lib, model, model_dir):
    os.makedirs(lib, exist_ok=True)
    os.makedirs(model_dir, exist_ok=True)
    print("Installing " + PACKAGE + " ...", flush=True)
    code = subprocess.call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
                            "--upgrade", "--target", lib, PACKAGE])
    if code != 0:
        say(ok=False, error=f"pip exited with code {code}")
        return 1
    print("Downloading the Whisper model " + model + " ...", flush=True)
    load(lib, model, model_dir)
    say(ok=True)
    return 0


def transcribe(lib, model, model_dir, path, lang, threads):
    m = load(lib, model, model_dir, threads)
    segments, info = m.transcribe(path, language=lang or None, vad_filter=True, beam_size=5)
    text = " ".join(s.text.strip() for s in segments if s.text and s.text.strip())
    say(ok=True, text=text, language=getattr(info, "language", "") or "")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--lib", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--model-dir", required=True)
    p.add_argument("--install", action="store_true")
    p.add_argument("--lang", default="")
    p.add_argument("--threads", type=int, default=0)
    p.add_argument("audio", nargs="?")
    a = p.parse_args(argv)
    try:
        if a.install:
            return install(a.lib, a.model, a.model_dir)
        return transcribe(a.lib, a.model, a.model_dir, a.audio, a.lang, a.threads)
    except Exception as e:      # noqa: BLE001 - the caller reads the JSON line, not a traceback
        say(ok=False, error=f"{type(e).__name__}: {e}"[:300])
        return 1


if __name__ == "__main__":
    sys.exit(main())
