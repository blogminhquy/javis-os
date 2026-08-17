#!/bin/bash
# Double-click in Finder to stop JAVIS OS.
cd "$(dirname "$0")" || exit 1
bash "bin/javis-stop.sh"
echo ""
echo "You can close this window."
