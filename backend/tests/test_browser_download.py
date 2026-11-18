"""The shipped install artifact must match the reviewed extension source."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_browser_download_is_current_and_identity_matches():
    spec = importlib.util.spec_from_file_location("browser_package", ROOT / "scripts/package_browser_extension.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DEST.read_bytes() == module.package()
    manifest = json.loads((ROOT / "chrome-extension/manifest.json").read_text())
    assert not manifest.get("host_permissions")
    assert "<all_urls>" not in manifest.get("permissions", [])
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    extension_id = "".join(chr(ord("a") + int(char, 16)) for char in digest)
    assert extension_id in (ROOT / "frontend/src/lib/browserSetup.ts").read_text()


def test_example_is_an_ordinary_importable_skill():
    from app.services.export_import_service import validate_export_data

    source = ROOT / "frontend/src/data/browser-demo-skill.json"
    download = ROOT / "frontend/public/skills/browser-demo.json"
    assert source.read_bytes() == download.read_bytes()
    data = json.loads(source.read_text())
    assert validate_export_data(data) is None
    skill = data["items"][0]
    assert skill["set_type"] == "prompt"
    instructions = skill["items"][0]["searchphrase"]
    assert instructions == skill["extraction_config"]["content"]
    for required in ("record_value", "calculate", "login_required", "unapproved_site", "rankings-facts", "economic-impact"):
        assert required in instructions
    assert "localhost" not in instructions
