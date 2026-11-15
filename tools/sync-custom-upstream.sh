#!/usr/bin/env bash
# Run on demand before upgrading the custom deployment, never on a timer.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
mode="${1:---check}"
[[ "$mode" == --check || "$mode" == --apply ]] || { echo 'Usage: sync-custom-upstream.sh [--check|--apply]' >&2; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Save all local changes before syncing.' >&2; exit 1; }
[[ "$(git remote get-url origin)" == https://github.com/kk311/javis-os.git ]] || { echo 'Unexpected fork origin.' >&2; exit 1; }
[[ "$(git remote get-url upstream)" == https://github.com/blogminhquy/javis-os.git ]] || { echo 'Unexpected upstream.' >&2; exit 1; }
git fetch origin refs/heads/main:refs/remotes/origin/main refs/heads/custom/zernio-bridge:refs/remotes/origin/custom/zernio-bridge
git fetch upstream refs/heads/main:refs/remotes/upstream/main
git merge-base --is-ancestor origin/main upstream/main || { echo 'Fork main has diverged; inspect without resetting.' >&2; exit 1; }
git merge-base --is-ancestor main upstream/main || { echo 'Local main has diverged; inspect without resetting.' >&2; exit 1; }
[[ "$(git rev-parse custom/zernio-bridge)" == "$(git rev-parse origin/custom/zernio-bridge)" ]] || { echo 'Local and remote custom branches differ; reconcile first.' >&2; exit 1; }
echo "Upstream target: $(git rev-parse upstream/main)"
git log --oneline custom/zernio-bridge..upstream/main
[[ "$mode" == --apply ]] || exit 0
candidate="update/zernio-$(date -u +%Y%m%dT%H%M%SZ)"
git switch -c "$candidate" custom/zernio-bridge
echo "Candidate: $candidate; failures leave the custom branch unchanged."
git merge --no-edit upstream/main
npm --prefix bridges/zernio test
python tools/release.py check
python tests/run.py
# Publish is separate, through the authenticated Javis GitHub gateway.
git switch custom/zernio-bridge
git merge --ff-only "$candidate"
git switch main
git merge --ff-only upstream/main
git switch custom/zernio-bridge
echo 'Checks passed. Review then push main and custom/zernio-bridge atomically through the GitHub gateway.'
echo 'No image was built or deployed. Run runtime integration tests before publishing an image.'
