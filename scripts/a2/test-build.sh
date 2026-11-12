#!/usr/bin/env bash
# Verify a built fork tree: brand layer current, Python suite, JS/TS workspace checks as CI runs them.
#   scripts/a2/test-build.sh                 everything
#   scripts/a2/test-build.sh --python-only   skip the JS/TS checks
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

js=1
if [[ "${1:-}" == "--python-only" ]]; then
  js=0
  shift
fi

if ! uv run --quiet scripts/a2/apply_brand.py --check >/dev/null; then
  echo "The brand layer is stale: run uv run scripts/a2/apply_brand.py --derived and commit the result." >&2
  exit 1
fi

scripts/run_tests.sh -q "$@"

if ((js)); then
  scripts/run-in-hermes-env bash -c 'pnpm install --frozen-lockfile && just check-js-ci'
fi
