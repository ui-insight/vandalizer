#!/usr/bin/env python3
"""Verify downloaded release assets against the sha256 digests in manifest.json.

This runs before anything is unpacked or scanned: every later check reads the
contents of these tarballs, so a tampered or truncated download must fail here
rather than be parsed. Each manifest asset is reported OK / MISSING / MISMATCH.

The download pattern and the unpack glob are both wider than the manifest, so
anything else attached to the release would be parsed unhashed. The manifest is
the authority on what the release *is*, so a tarball present in the directory
but absent from `release_assets` is UNEXPECTED and fails the run too.

Standard library only, so it runs before any environment is built.

Run: python3 benchmarks/corpus/CSU-NSF-001/tools/verify_assets.py \\
       --manifest benchmarks/corpus/CSU-NSF-001/manifest.json \\
       --assets-dir /tmp/corpus-assets
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True,
                        help="manifest.json carrying release_assets.assets[].sha256")
    parser.add_argument("--assets-dir", type=pathlib.Path, required=True,
                        help="directory holding the downloaded tarballs")
    args = parser.parse_args()

    assets_dir = args.assets_dir
    manifest = json.loads(args.manifest.read_text())
    ok = True
    for asset in manifest["release_assets"]["assets"]:
        path = assets_dir / asset["name"]
        if not path.exists():
            print(f"MISSING: {asset['name']}"); ok = False; continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        status = "OK" if digest == asset["sha256"] else f"MISMATCH (got {digest})"
        print(f"{asset['name']}: {status}")
        ok = ok and digest == asset["sha256"]
    # The download pattern and the unpack glob are both wider than the
    # manifest, so anything else attached to the release would be parsed
    # unhashed. The manifest is the authority on what the release *is*.
    expected = {asset["name"] for asset in manifest["release_assets"]["assets"]}
    for extra in sorted(p.name for p in assets_dir.glob("*.tar.gz") if p.name not in expected):
        print(f"UNEXPECTED (not listed in manifest release_assets): {extra}"); ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
