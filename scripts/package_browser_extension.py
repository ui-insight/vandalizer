"""Create the dependency-free unpacked-extension download. Run after extension edits."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import io
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "frontend/public/vandalizer-browser.zip"

def package():
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / "chrome-extension").rglob("*")):
            if not path.is_file() or path.suffix not in {".js", ".json", ".html", ".css", ".png"}:
                continue
            info = ZipInfo(str(path.relative_to(ROOT / "chrome-extension")), (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()

if __name__ == "__main__":
    expected = package()
    if "--check" in sys.argv:
        if not DEST.exists() or DEST.read_bytes() != expected:
            sys.exit("Extension download is stale. Run python3 scripts/package_browser_extension.py")
    else:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_bytes(expected)
