#!/usr/bin/env bash
# Disable the upstream workflows listed under workflows.disabled in a2/brand.yaml on the fork's GitHub repo.
# The files stay untouched (upstream tests read them); GitHub just never runs them. Idempotent.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
repo="${1:-A2Genesis-de/hermes-agent}"

uv run --quiet --with 'pyyaml>=6,<7' python -c '
import yaml
for name in yaml.safe_load(open("a2/brand.yaml", encoding="utf-8-sig"))["workflows"]["disabled"]:
    print(name)
' | while read -r workflow; do
  state="$(gh api "repos/$repo/actions/workflows/$workflow" --jq .state 2>/dev/null || echo missing)"
  case "$state" in
    active) gh api --method PUT "repos/$repo/actions/workflows/$workflow/disable" && echo "disabled $workflow" ;;
    missing) echo "not on GitHub: $workflow" ;;
    *) echo "already $state: $workflow" ;;
  esac
done
