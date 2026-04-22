#!/usr/bin/env bash
# Cut a release tag in the form vYYYY.MM.N (CalVer).
# Pushes the tag, which triggers .github/workflows/release.yaml.
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

# Must be on main with a clean tree and up to date with origin.
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  echo "error: must be on main (currently on $branch)" >&2
  exit 1
fi
if ! git diff-index --quiet HEAD --; then
  echo "error: working tree has uncommitted changes" >&2
  exit 1
fi
git fetch origin main --tags --quiet
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse origin/main)"
if [[ "$local_sha" != "$remote_sha" ]]; then
  echo "error: local main ($local_sha) is not in sync with origin/main ($remote_sha)" >&2
  exit 1
fi

# Compute next CalVer tag: vYYYY.MM.N where N increments within the month.
year_month="$(date +%Y.%m)"
prefix="v${year_month}."
last_n="$(git tag --list "${prefix}*" | sed "s/^${prefix}//" | sort -n | tail -n1 || true)"
if [[ -z "${last_n}" ]]; then
  next_n=1
else
  next_n=$((last_n + 1))
fi
tag="${prefix}${next_n}"

# Build release notes from merged PR subjects since the previous tag.
prev_tag="$(git tag --list 'v*.*.*' --sort=-v:refname | head -n1 || true)"
if [[ -n "$prev_tag" ]]; then
  range="${prev_tag}..HEAD"
else
  range="HEAD"
fi
subjects="$(git log --no-merges --pretty=format:'- %s' "$range")"

echo "Next tag:   $tag"
echo "Previous:   ${prev_tag:-<none>}"
echo "Commits since previous tag:"
echo "${subjects:-  <none>}"
echo

if [[ $DRY_RUN -eq 1 ]]; then
  echo "--dry-run: not tagging or pushing."
  exit 0
fi

read -r -p "Create and push tag $tag? [y/N] " reply
if [[ "$reply" != "y" && "$reply" != "Y" ]]; then
  echo "aborted."
  exit 1
fi

git tag -a "$tag" -m "Release $tag"
git push origin "$tag"
echo "Pushed $tag. Watch: https://github.com/$(git config --get remote.origin.url | sed -E 's#.*[:/]([^/]+/[^/.]+)(\.git)?#\1#')/actions"
