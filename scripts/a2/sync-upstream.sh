#!/usr/bin/env bash
# Merge the newest upstream stable release tag (vX.Y.Z) into the fork's a2 branch.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean." >&2
  exit 1
fi

git fetch upstream --tags --prune
latest_tag="$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n1)"

if git merge-base --is-ancestor "$latest_tag" a2; then
  echo "a2 already contains $latest_tag."
  exit 0
fi

git switch a2
git merge --no-ff -m "Merge upstream release $latest_tag" "$latest_tag"
echo "Merged $latest_tag into a2. Review, test and then: git push origin a2"
