#!/usr/bin/env bash
set -euo pipefail

MSG="${1:-chore: sync updates}"
RUN_TEST="${2:-}"

echo "==> git add -A"
git add -A

if git diff --cached --quiet; then
  echo "==> Nothing staged to commit, skipping commit/push."
else
  echo "==> git commit -m \"$MSG\""
  git commit -m "$MSG"

  echo "==> git push origin main"
  git push origin main
fi

echo "==> Push complete. Vercel will redeploy api/index.py automatically."

if [ "$RUN_TEST" == "--test" ]; then
  echo "==> Running local Docker functional test..."
  ./docker-test-local.sh
else
  echo "==> Skipping local Docker test. Re-run with --test as 2nd arg to include it."
fi
