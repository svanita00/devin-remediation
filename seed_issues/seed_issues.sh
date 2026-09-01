#!/usr/bin/env bash
# Seed the curated remediation issues onto a Superset fork + create the devin-fix label.
# Reproduces the exact issue set this project remediates, so anyone can run the full flow:
#   fork superset -> seed_issues.sh -> setup_devin.py -> docker compose up -> label/scan
#
# Usage:  REPO="you/superset" bash seed_issues/seed_issues.sh
# Requires: gh (authenticated), issues enabled on the fork.
set -euo pipefail

: "${REPO:?Set REPO, e.g. REPO=you/superset bash seed_issues/seed_issues.sh}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Seeding issues into $REPO"

gh label create devin-fix --repo "$REPO" --color "5319e7" \
  --description "Dispatch this issue to a Devin session for automated remediation" \
  2>/dev/null || echo "label devin-fix already exists (ok)"

for f in "$DIR"/0[1-7]-*.md; do
  title="$(head -n 1 "$f")"
  body="$(tail -n +3 "$f")"
  echo "Creating: $title"
  gh issue create --repo "$REPO" --title "$title" --body "$body" --label devin-fix
done

echo "Done. Label an issue devin-fix (event trigger) or POST /scan to remediate."
