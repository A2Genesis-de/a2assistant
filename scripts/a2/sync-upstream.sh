#!/usr/bin/env bash
# Merge the newest upstream stable release tag (vX.Y.Z) into the fork's main branch.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean." >&2
  exit 1
fi

# Releases are semver tags (v0.23.1); date tags (v2026.9.24) are a legacy scheme and must be ignored.
git fetch upstream '+refs/heads/main:refs/remotes/upstream/main' --tags
latest_tag="$(git tag --list --sort=-v:refname | grep -E '^v[0-9]{1,3}\.[0-9]+\.[0-9]+$' | head -n1)"

if git merge-base --is-ancestor "$latest_tag" main; then
  echo "main already contains $latest_tag."
  exit 0
fi

git switch main
git merge --no-ff -m "Merge upstream release $latest_tag" "$latest_tag"
echo "Merged $latest_tag into main. Review, test and then: git push origin main"
