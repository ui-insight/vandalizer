#!/usr/bin/env bash
# Cut a release tag in the form vMAJOR.MINOR.PATCH (semver), continuing the
# v4.x line. Defaults to a minor bump (v4.9.0 -> v4.10.0); pass --major for the
# next major (-> v5.0.0) or --patch for a hotfix (-> v4.9.1). Pushes the tag,
# which triggers .github/workflows/release.yaml (release-check, then publish).
#
# Run AFTER stamping CHANGELOG.md ([Unreleased] -> [vX.Y.Z] + a fresh empty
# [Unreleased]) and committing — the stamp is a deliberate human step so the
# release notes get reviewed before the tag is cut. See RELEASE_CHECKLIST.md.
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: scripts/cut_release.sh [--major|--minor|--patch] [--dry-run]

  --minor     (default) bump the minor version: v4.9.0 -> v4.10.0
  --major     bump the major version:           v4.9.0 -> v5.0.0
  --patch     bump the patch version (hotfix):  v4.9.0 -> v4.9.1
  --dry-run   print the computed tag and release notes; do not tag or push
EOF
}

DRY_RUN=0
BUMP=minor
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --major)   BUMP=major ;;
    --minor)   BUMP=minor ;;
    --patch)   BUMP=patch ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $arg" >&2; usage; exit 1 ;;
  esac
done

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

# Latest release tag on the vX.Y[.Z] line (sorted by version, so v4.9.0 > v4.0).
prev_tag="$(git tag --list 'v[0-9]*' --sort=-v:refname | head -n1 || true)"
ver="${prev_tag#v}"
IFS='.' read -r maj min pat <<< "$ver"
maj="${maj:-0}"; min="${min:-0}"; pat="${pat:-0}"

case "$BUMP" in
  major) maj=$((maj + 1)); min=0; pat=0 ;;
  minor) min=$((min + 1)); pat=0 ;;
  patch) pat=$((pat + 1)) ;;
esac
tag="v${maj}.${min}.${pat}"

if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
  echo "error: tag ${tag} already exists" >&2
  exit 1
fi

# Warn if the CHANGELOG hasn't been stamped for this version yet.
if [[ -f CHANGELOG.md ]] && ! grep -q "\[${tag}\]" CHANGELOG.md; then
  echo "warning: CHANGELOG.md has no [${tag}] section — stamp the release notes first." >&2
fi

# Build release notes from non-merge commit subjects since the previous tag.
if [[ -n "$prev_tag" ]]; then
  range="${prev_tag}..HEAD"
else
  range="HEAD"
fi
subjects="$(git log --no-merges --pretty=format:'- %s' "$range")"

echo "Bump:       $BUMP"
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
