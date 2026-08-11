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
if ! git fetch origin main --quiet; then
  echo "error: could not fetch origin/main" >&2
  exit 1
fi
# Fetch tags separately and report failures explicitly. A local tag that has
# diverged from origin (e.g. a lightweight tag left over from an older cut)
# makes this fail with "would clobber existing tag" — and under `set -e` that
# would otherwise abort this script with no output at all, which reads as
# "nothing happened" rather than "your tags are wrong".
if ! fetch_err="$(git fetch origin --tags 2>&1)"; then
  echo "error: could not fetch tags from origin:" >&2
  echo "$fetch_err" >&2
  echo "hint: a local tag has diverged from origin. Compare with" >&2
  echo "        git ls-remote --tags origin" >&2
  echo "        git rev-parse <tag>^{commit}" >&2
  echo "      and repair with: git tag -d <tag> && git fetch origin tag <tag>" >&2
  exit 1
fi
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse origin/main)"
if [[ "$local_sha" != "$remote_sha" ]]; then
  echo "error: local main ($local_sha) is not in sync with origin/main ($remote_sha)" >&2
  exit 1
fi

# Latest release tag on the vX.Y[.Z] line (sorted by version, so v4.9.0 > v4.0).
prev_tag="$(git tag --list 'v[0-9]*' --sort=-v:refname | head -n1 || true)"

# The next tag and the release-notes range are both derived from prev_tag, so a
# local-only tag (a leftover experiment, or one never pushed) would silently
# compute the wrong version and the wrong commit list. Require it on origin.
if [[ -n "$prev_tag" ]] && ! git ls-remote --exit-code --tags origin "$prev_tag" >/dev/null 2>&1; then
  echo "error: latest local tag ${prev_tag} does not exist on origin." >&2
  echo "       Version and release notes are computed from it, so this would" >&2
  echo "       produce the wrong tag and commit list." >&2
  echo "hint:  delete the stray local tag (git tag -d ${prev_tag}) or push it." >&2
  exit 1
fi

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
