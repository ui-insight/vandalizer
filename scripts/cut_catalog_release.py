#!/usr/bin/env python3
"""Cut a new release of the verified catalog.

Authoring-side companion to backend/scripts/seed_catalog.py. After you edit
backend/seeds/** (add, update, or delete seed files), this script:

  1. Validates the seed tree (JSON parses, every file has a unique
     _seed_meta.seed_id, items carry a title, collection slugs resolve).
  2. Diffs the working tree against a base git ref (default origin/main) and
     reports what servers will see on upgrade: new, refreshed, and — most
     importantly — items that will be RETIRED by the prune pass.
  3. Bumps backend/seeds/VERSION (CI rejects seed changes without a bump).
  4. Optionally creates a release branch and commit (--commit).

Stdlib only — run from anywhere inside the repo:

  python3 scripts/cut_catalog_release.py                  # preview (no writes)
  python3 scripts/cut_catalog_release.py --bump minor     # write VERSION
  python3 scripts/cut_catalog_release.py --set 2.0.0 --commit
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS_DIR = REPO_ROOT / "backend" / "seeds"
VERSION_FILE = SEEDS_DIR / "VERSION"
SEEDS_REL = "backend/seeds"

# type dir -> key in items[0] that holds the entity title (mirrors the
# _PRUNE_SPEC title_key in backend/scripts/seed_catalog.py)
TYPES = {
    "workflows": "name",
    "search_sets": "title",
    "knowledge_bases": "title",
}

RED, GREEN, YELLOW, BOLD, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[1m", "\033[0m"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True,
    ).stdout


def git_show(ref: str, path: str) -> str | None:
    try:
        return git("show", f"{ref}:{path}")
    except subprocess.CalledProcessError:
        return None  # path doesn't exist at that ref


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        sys.exit(f"{RED}Unparseable version {v!r} — expected dotted integers like 1.2.0{RESET}")


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def _entry_from_json(raw: str, type_name: str, fname: str, problems: list[str]) -> tuple[str, dict] | None:
    """Parse one seed file's text into (seed_id, entry). Records problems."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        problems.append(f"{type_name}/{fname}: invalid JSON ({e})")
        return None
    meta = data.get("_seed_meta") or {}
    seed_id = meta.get("seed_id")
    if not seed_id:
        problems.append(f"{type_name}/{fname}: missing _seed_meta.seed_id")
        return None
    items = data.get("items") or []
    title = items[0].get(TYPES[type_name]) if items else None
    if not title:
        problems.append(
            f"{type_name}/{fname}: items[0].{TYPES[type_name]} missing — "
            "prune's legacy title-fallback and the Explore tab both need it"
        )
    # Normalized dump so formatting-only edits don't read as content changes.
    digest = json.dumps(data, sort_keys=True)
    return seed_id, {
        "file": fname,
        "title": title,
        "display_name": meta.get("display_name") or title or fname,
        "collections": meta.get("collections") or [],
        "digest": digest,
    }


def load_worktree_manifest(problems: list[str]) -> dict[str, dict[str, dict]]:
    manifest: dict[str, dict[str, dict]] = {}
    for type_name in TYPES:
        entries: dict[str, dict] = {}
        type_dir = SEEDS_DIR / type_name
        for f in sorted(type_dir.glob("*.json")) if type_dir.exists() else []:
            parsed = _entry_from_json(f.read_text(), type_name, f.name, problems)
            if not parsed:
                continue
            seed_id, entry = parsed
            if seed_id in entries:
                problems.append(
                    f"{type_name}: duplicate seed_id {seed_id!r} "
                    f"({entries[seed_id]['file']} and {f.name})"
                )
                continue
            entries[seed_id] = entry
        manifest[type_name] = entries
    return manifest


def load_ref_manifest(ref: str) -> dict[str, dict[str, dict]]:
    manifest: dict[str, dict[str, dict]] = {t: {} for t in TYPES}
    try:
        listing = git("ls-tree", "-r", "--name-only", ref, "--", SEEDS_REL)
    except subprocess.CalledProcessError:
        sys.exit(f"{RED}Cannot read {SEEDS_REL} at ref {ref!r} — does the ref exist?{RESET}")
    ignored: list[str] = []  # base-ref problems are informational only
    for path in listing.splitlines():
        parts = Path(path).parts  # backend/seeds/<type>/<file>.json
        if len(parts) != 4 or parts[3] == "VERSION" or not parts[3].endswith(".json"):
            continue
        type_name = parts[2]
        if type_name not in TYPES:
            continue
        raw = git_show(ref, path)
        if raw is None:
            continue
        parsed = _entry_from_json(raw, type_name, parts[3], ignored)
        if parsed:
            manifest[type_name][parsed[0]] = parsed[1]
    return manifest


def validate_collections(manifest: dict[str, dict[str, dict]], problems: list[str]) -> None:
    coll_file = SEEDS_DIR / "collections.json"
    if not coll_file.exists():
        problems.append("collections.json is missing")
        return
    try:
        slugs = {c["slug"] for c in json.loads(coll_file.read_text())["collections"]}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        problems.append(f"collections.json: invalid ({e})")
        return
    for type_name, entries in manifest.items():
        for seed_id, entry in entries.items():
            for slug in entry["collections"]:
                if slug not in slugs:
                    problems.append(
                        f"{type_name}/{entry['file']}: unknown collection slug {slug!r}"
                    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main",
                    help="git ref to diff against / the previously released catalog (default: origin/main)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--bump", choices=["major", "minor", "patch"],
                     help="bump backend/seeds/VERSION by this part")
    grp.add_argument("--set", dest="set_version", metavar="X.Y.Z",
                     help="set backend/seeds/VERSION explicitly")
    ap.add_argument("--commit", action="store_true",
                    help="create a catalog/vX.Y.Z branch (if on main) and commit the release")
    args = ap.parse_args()

    # ---- validate working tree -------------------------------------------
    problems: list[str] = []
    work = load_worktree_manifest(problems)
    validate_collections(work, problems)
    if problems:
        print(f"{RED}{BOLD}Seed validation failed:{RESET}")
        for p in problems:
            print(f"  {RED}✗ {p}{RESET}")
        sys.exit(1)
    n_items = sum(len(v) for v in work.values())
    print(f"{GREEN}✓ Seed tree valid{RESET} — "
          + ", ".join(f"{len(work[t])} {t}" for t in TYPES) + f" ({n_items} items)")

    # ---- diff against base ref -------------------------------------------
    base = load_ref_manifest(args.base)
    added, removed, changed = [], [], []
    for t in TYPES:
        for sid, e in work[t].items():
            if sid not in base[t]:
                added.append((t, sid, e))
            elif e["digest"] != base[t][sid]["digest"]:
                changed.append((t, sid, e))
        for sid, e in base[t].items():
            if sid not in work[t]:
                removed.append((t, sid, e))

    print(f"\n{BOLD}Catalog diff vs {args.base}:{RESET}")
    if not (added or removed or changed):
        print("  (no seed content changes)")
    for t, sid, e in added:
        print(f"  {GREEN}+ new      {t[:-1].replace('_', ' ')}: {e['display_name']} ({sid}){RESET}")
    for t, sid, e in changed:
        print(f"  {YELLOW}~ refresh  {t[:-1].replace('_', ' ')}: {e['display_name']} ({sid}){RESET}")
    for t, sid, e in removed:
        print(f"  {RED}- RETIRE   {t[:-1].replace('_', ' ')}: {e['display_name']} ({sid}){RESET}")

    # A removed+added pair sharing a title is usually an accidental seed_id
    # rename — on upgrade the old item is retired and a fresh one created.
    removed_titles = {(t, e["title"]): sid for t, sid, e in removed if e["title"]}
    for t, sid, e in added:
        old_sid = removed_titles.get((t, e["title"]))
        if old_sid:
            print(f"  {YELLOW}! {e['title']!r} looks renamed ({old_sid} → {sid}) — servers will "
                  f"retire the old item and seed a new one. Keep the old seed_id to update in place.{RESET}")

    if removed:
        print(f"\n  {RED}{len(removed)} item(s) will be retired on servers that upgrade with prune.{RESET}")
        print("  Retiring is a soft-archive (verified=False, row kept) and is previewed in-app before apply.")

    # ---- version ----------------------------------------------------------
    base_version_raw = (git_show(args.base, f"{SEEDS_REL}/VERSION") or "").strip()
    current_raw = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else ""
    print(f"\n{BOLD}Version:{RESET} {args.base} = {base_version_raw or '(none)'}, working tree = {current_raw or '(none)'}")

    seeds_changed = bool(added or removed or changed)
    if not args.bump and not args.set_version:
        if seeds_changed and current_raw == base_version_raw:
            print(f"{YELLOW}Preview only — rerun with --bump minor (or --set X.Y.Z) to stamp the release. "
                  f"CI will reject seed changes without a VERSION bump.{RESET}")
        else:
            print("Preview only — no version flag given, nothing written.")
        return

    if args.set_version:
        new_version = args.set_version.strip()
        parse_version(new_version)
    else:
        start = max(parse_version(current_raw or "0.0.0"), parse_version(base_version_raw or "0.0.0"))
        start = (start + (0, 0, 0))[:3]
        idx = ["major", "minor", "patch"].index(args.bump)
        parts = list(start)
        parts[idx] += 1
        parts[idx + 1:] = [0] * (2 - idx)
        new_version = ".".join(str(p) for p in parts)

    if base_version_raw and parse_version(new_version) <= parse_version(base_version_raw):
        sys.exit(f"{RED}New version {new_version} must be greater than {args.base}'s {base_version_raw} — "
                 f"servers compare versions to decide whether an upgrade is available.{RESET}")
    if not seeds_changed:
        print(f"{YELLOW}Note: no seed content changed vs {args.base}; bumping VERSION alone "
              f"will make servers re-seed identical content.{RESET}")

    VERSION_FILE.write_text(new_version + "\n")
    print(f"{GREEN}✓ backend/seeds/VERSION → {new_version}{RESET}")

    # ---- optional branch + commit ----------------------------------------
    if not args.commit:
        print(f"\n{BOLD}Next:{RESET} commit backend/seeds, open a PR to main, deploy, "
              "then apply via Admin → Catalog (or ./setup.sh --seed).")
        return

    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch in ("main", "master"):
        branch = f"catalog/v{new_version}"
        git("checkout", "-b", branch)
        print(f"✓ created branch {branch}")

    git("add", SEEDS_REL)
    staged = git("diff", "--cached", "--name-only", "--", SEEDS_REL).strip()
    if not staged:
        sys.exit(f"{YELLOW}Nothing staged under {SEEDS_REL} — already committed?{RESET}")

    def _lines(label: str, rows: list) -> list[str]:
        return [f"- {label}: {e['display_name']} ({sid})" for _, sid, e in rows]

    msg = "\n".join(
        [f"feat(catalog): release catalog v{new_version}", ""]
        + _lines("add", added) + _lines("refresh", changed) + _lines("retire", removed)
    ) + "\n"
    git("commit", "-m", msg)
    print(f"{GREEN}✓ committed catalog v{new_version} on {branch}{RESET}")
    print(f"\n{BOLD}Next:{RESET} git push -u origin {branch} && gh pr create — "
          "after deploy, apply via Admin → Catalog (or ./setup.sh --seed).")


if __name__ == "__main__":
    main()
