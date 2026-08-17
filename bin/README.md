# JAVIS OS - macOS launchers

Portable helpers to run JAVIS OS natively on macOS (no Docker), so you can
start it like a normal app.

## Prereqs (once)

1. From the repo root: `./install.sh` - creates `.venv`, installs deps and the
   Claude Code CLI. (On Apple Silicon without Homebrew you can create the
   environment with [uv](https://docs.astral.sh/uv/): `uv venv --python 3.12 .venv`
   then `uv pip install -r requirements.txt`, and install the CLI with
   `npm install -g @anthropic-ai/claude-code`.)
2. Log in to the brain once: `claude auth login --claudeai`.

## Run

- **`JAVIS OS.app`** (repo root) - double-click in Finder to start the server and
  open `http://127.0.0.1:7777`. Keep the `.app` inside the repo folder (it finds
  the repo relative to its own location).
- **`Start JAVIS OS.command`** / **`Stop JAVIS OS.command`** - double-clickable
  Finder alternatives.
- **`bin/javis-start.sh`** / **`bin/javis-stop.sh`** - the underlying scripts.
- **`bin/javis-autostart.sh [install|uninstall]`** - run the server at login via a
  macOS LaunchAgent. The plist is generated with paths for your machine; nothing
  is hardcoded in the repo.

## Notes

- Every script resolves the repo location from its own path, so the repo can live
  anywhere.
- Default port is `7777`; override with the `JAVIS_PORT` environment variable.
- Bound to `127.0.0.1` (local only). Because it's `localhost`, the browser allows
  the microphone, so voice works without HTTPS. Use Chrome or Edge for speech
  recognition.
