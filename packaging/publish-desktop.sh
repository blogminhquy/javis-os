#!/usr/bin/env bash
# ============================================================
# JAVIS OS - publish the desktop installers on the fixed "desktop" release.
#
#   bash packaging/publish-desktop.sh <folder holding JavisOS-Setup.exe and JavisOS-macOS.dmg>
#
# Called by the publish job of .github/workflows/desktop-installers.yml (needs gh and GH_TOKEN).
#
# The Windows .exe is replaced ONLY when something inside it changed. It is not code-signed
# yet, so Edge, SmartScreen and antivirus engines know it by its file hash alone. Every
# replaced file starts from zero again: "isn't commonly downloaded" in the browser, and an
# approval from an antivirus vendor (a false positive report) is lost. The workflow also runs
# for install.ps1, install.sh and the start scripts, which the smoke tests use but the .exe
# does not carry (it holds bootstrap.ps1, the icon and the wizard pictures, nothing else), and
# customers reported the download being blocked while the file was being replaced for those
# (2026-11-12).
#
# JavisOS-Setup.inputs on the release remembers what the published .exe was built from:
#   <fingerprint> <version>
# FORCE=true (the "Run workflow" button) replaces the .exe no matter what.
# SIGNED=true|false is part of the fingerprint, so the first signed build always goes out.
# ============================================================
set -euo pipefail

out="${1:?usage: publish-desktop.sh <folder with the two installers>}"
exe="$out/JavisOS-Setup.exe"
dmg="$out/JavisOS-macOS.dmg"
for f in "$exe" "$dmg"; do
  [ -f "$f" ] || { echo "missing: $f" >&2; exit 1; }
done
v="$(tr -d ' \r\n' < VERSION)"

# Git blob ids of everything javis-setup.iss packs: the same on every runner, whatever the
# line endings or the checkout time (an Inno build is not byte-for-byte repeatable).
listing="$(git ls-tree -r HEAD -- packaging/windows/javis-setup.iss packaging/windows/bootstrap.ps1 packaging/assets | grep -v '\.icns$')"
tab=$'\t'
for need in packaging/windows/javis-setup.iss packaging/windows/bootstrap.ps1 packaging/assets/javis.ico; do
  # A moved file must not turn the fingerprint into a constant that never republishes.
  grep -q "${tab}${need}\$" <<< "$listing" || { echo "installer input not found in git: $need" >&2; exit 1; }
done
want="$(printf '%s\nsigned=%s\n' "$listing" "${SIGNED:-false}" | git hash-object --stdin)"

have=""
have_v=""
exe_published=0
if gh release view desktop >/dev/null 2>&1; then
  exists=1
  line="$(gh release download desktop --pattern JavisOS-Setup.inputs --output - 2>/dev/null | head -n 1 || true)"
  have="${line%% *}"
  have_v="${line#* }"
  if gh release view desktop --json assets --jq '.assets[].name' | grep -qx 'JavisOS-Setup.exe'; then
    exe_published=1
  fi
else
  exists=0
fi

if [ "${FORCE:-false}" != "true" ] && [ -n "$have" ] && [ "$have" = "$want" ] && [ "$exe_published" = 1 ]; then
  replace_exe=0
  exe_v="$have_v"
  echo "JavisOS-Setup.exe: nothing inside it changed since ${exe_v}, keeping the published file (same hash)"
else
  replace_exe=1
  exe_v="$v"
  echo "JavisOS-Setup.exe: publishing the build from ${v}"
fi

notes="Desktop installers for JAVIS OS. They install the newest Javis on first run.

- Windows 10/11: JavisOS-Setup.exe (built from ${exe_v})
- macOS 11+: JavisOS-macOS.dmg (built from ${v})

Steps: QUICKSTART.md (Tiếng Việt) or QUICKSTART.en.md (English)."
if [ "$exists" = 0 ]; then
  gh release create desktop --title "JAVIS OS - Windows & macOS installers" --notes "$notes" --latest=false
else
  gh release edit desktop --notes "$notes"
fi

gh release upload desktop "$dmg" --clobber
if [ "$replace_exe" = 1 ]; then
  gh release upload desktop "$exe" --clobber
  # Last, and only after the .exe is up: a failed upload must not leave a fingerprint that
  # makes the next run keep the old file.
  printf '%s %s\n' "$want" "$v" > "$out/JavisOS-Setup.inputs"
  gh release upload desktop "$out/JavisOS-Setup.inputs" --clobber
fi

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  if [ "$replace_exe" = 1 ]; then
    echo "Published both installers from ${v}" >> "$GITHUB_STEP_SUMMARY"
  else
    echo "Published the macOS installer from ${v}; kept the Windows installer from ${exe_v} (unchanged)" >> "$GITHUB_STEP_SUMMARY"
  fi
fi
