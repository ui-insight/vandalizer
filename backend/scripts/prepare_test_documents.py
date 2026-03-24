"""Download real documents and prepare test cases for extraction validation.

Downloads publicly available grant/contract documents (NIH, NSF),
extracts text, and optionally runs the extraction engine to generate
draft expected values for human review.

Usage:
    cd backend
    python -m scripts.prepare_test_documents [--extract]

Flags:
    --extract   Run the extraction engine on each document to generate
                draft expected_values (requires LLM API access).
                Without this flag, only downloads and extracts text.
"""

import asyncio
import json
import logging
import pathlib
import sys
import tempfile
from urllib.request import urlretrieve

logger = logging.getLogger(__name__)

SEEDS_DIR = pathlib.Path(__file__).resolve().parent.parent / "seeds" / "search_sets"
OUTPUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "seeds" / "test_document_texts"

# Real, publicly available documents for NIH and NSF
DOCUMENT_SOURCES = {
    "nih": [
        {
            "label": "NIAID R01 Sample - Jiang",
            "url": "https://www.niaid.nih.gov/sites/default/files/R01_Jiang_Sample_Application.pdf",
        },
        {
            "label": "NIAID R01 Sample - Li",
            "url": "https://www.niaid.nih.gov/sites/default/files/R01_Li_Sample_Application.pdf",
        },
        {
            "label": "NIAID R01 Sample - Gordon",
            "url": "https://www.niaid.nih.gov/sites/default/files/1-R01-AI121500-01A1_Gordon_Application.pdf",
        },
    ],
    "nsf": [
        {
            "label": "NSF Full Proposal - Hoover, Duke",
            "url": "https://www.cellbio.duke.edu/sites/default/files/2022-06/NSF-Full-Proposal-Example-2010.pdf",
        },
        {
            "label": "NSF Official Sample - Bernard",
            "url": "https://nsf-gov-resources.nsf.gov/files/Cover-Sheet-Bernard.pdf",
        },
        {
            "label": "NSF CAREER Proposal - Desai, UW-Madison",
            "url": "https://cdn.serc.carleton.edu/files/NAGTWorkshops/earlycareer/research/desai_career_proposal.pdf",
        },
    ],
}


def download_pdf(url: str, dest: pathlib.Path) -> bool:
    """Download a PDF from a URL. Returns True on success."""
    try:
        print(f"    Downloading {url}...")
        urlretrieve(url, str(dest))
        return True
    except Exception as e:
        print(f"    FAILED: {e}")
        return False


def extract_text_from_pdf(pdf_path: pathlib.Path) -> str:
    """Extract text from a PDF using the project's document reader."""
    try:
        # Try using the project's own reader
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from app.services.document_readers import extract_text_from_pdf as _extract
        return _extract(str(pdf_path))
    except ImportError:
        # Fallback: try pymupdf directly
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(pdf_path))
            text = ""
            for page in doc:
                text += page.get_text() + "\n"
            doc.close()
            return text
        except ImportError:
            print("    ERROR: No PDF reader available. Install pymupdf: uv add pymupdf")
            return ""


async def run_extraction_draft(source_text: str, seed_id: str) -> dict:
    """Run the extraction engine on source text to generate draft expected values."""
    from app.config import Settings
    from app.database import init_db
    from app.models.search_set import SearchSet, SearchSetItem

    settings = Settings()
    await init_db(settings)

    ss = await SearchSet.find_one({"extraction_config.seed_id": seed_id})
    if not ss:
        print(f"    Search set {seed_id} not found in database. Seed catalog first.")
        return {}

    items = await ss.get_items()
    from app.services.extraction_engine import run_extraction
    result = await run_extraction(
        text=source_text,
        fields=[{"searchphrase": it.searchphrase, "is_optional": it.is_optional, "enum_values": it.enum_values} for it in items],
        extraction_config=ss.extraction_config,
    )
    return {r["field"]: r["value"] for r in result if r.get("value")}


async def main():
    run_extract = "--extract" in sys.argv

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for agency, docs in DOCUMENT_SOURCES.items():
        seed_id = {
            "nih": "ss-nih-application",
            "nsf": "ss-nsf-proposal",
        }.get(agency)

        print(f"\n--- {agency.upper()} ---")
        seed_file = SEEDS_DIR / f"{agency}_{'application_extraction' if agency == 'nih' else 'proposal_extraction'}.json"
        seed_data = json.loads(seed_file.read_text()) if seed_file.exists() else None

        test_cases = []

        for doc in docs:
            label = doc["label"]
            url = doc["url"]
            print(f"  {label}")

            # Download
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = pathlib.Path(tmp.name)

            if not download_pdf(url, tmp_path):
                continue

            # Extract text
            text = extract_text_from_pdf(tmp_path)
            if not text.strip():
                print("    WARNING: No text extracted")
                continue

            # Save extracted text for review
            text_file = OUTPUT_DIR / f"{agency}_{label.replace(' ', '_').replace('/', '_')}.txt"
            text_file.write_text(text)
            print(f"    Text saved to {text_file.name} ({len(text)} chars)")

            tc = {
                "label": label,
                "source_type": "text",
                "source_text": text,
                "expected_values": {},
            }

            # Optionally run extraction for draft expected values
            if run_extract and seed_id:
                print("    Running extraction for draft expected values...")
                tc["expected_values"] = await run_extraction_draft(text, seed_id)
                print(f"    Extracted {len(tc['expected_values'])} fields (REVIEW REQUIRED)")

            test_cases.append(tc)

            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

        # Update seed file if we have test cases
        if test_cases and seed_data:
            seed_data["items"][0]["test_cases"] = test_cases
            seed_file.write_text(json.dumps(seed_data, indent=2, ensure_ascii=False) + "\n")
            print(f"  Updated {seed_file.name} with {len(test_cases)} test case(s)")
            if not run_extract:
                print("  NOTE: expected_values are empty. Run with --extract or fill manually.")

    print("\nDone! Review the extracted text and expected values before running validation.")


if __name__ == "__main__":
    asyncio.run(main())
