"""Re-point broken KB URL sources at durable eCFR equivalents.

Companion to ``repair_gov_kb_sources``. That script repairs the *content* for
a source's existing URL — it can't fix a source whose URL is dead (404 / DNS)
or permanently bot-blocked (403). Several such sources are regulation text that
has an official home on ecfr.gov, which the repair script fetches through the
eCFR **versioner API** — the one path that still works from a server whose
outbound access to agency HTML sites is blocked.

This script rewrites those sources' URLs to their eCFR equivalents and marks
them for rebuild (``content=None``, ``status="error"``), so a subsequent
``repair_gov_kb_sources`` run re-embeds them from the API (or, where the URL is
covered by the bundled seed manifest, from local text — no network at all).

It matches by EXACT current URL against the baked-in table below, across every
KnowledgeBaseSource in the database (seeded catalog KBs, clones, and
user-created KBs alike), so it never touches a source it wasn't told about.
Rewrites are fully reversible — re-run with the URLs swapped, or edit in the UI.

Only regulation-backed sources are remapped. Guidance-only pages with no eCFR
home (NSF GC-1/PAPPG, USDA general terms, agency FAQs) are NOT handled here —
those need a live replacement URL or a manual PDF upload and are left untouched.

Usage (inside the backend container / venv on the target server)::

    cd backend
    python -m scripts.remap_kb_source_urls --dry-run   # report what would change
    python -m scripts.remap_kb_source_urls             # apply the rewrites
    # then rebuild the re-pointed sources from eCFR:
    python -m scripts.remap_kb_source_urls --dry-run && \
        python -m scripts.remap_kb_source_urls && \
        python -m scripts.repair_gov_kb_sources
"""

import argparse
import asyncio
import logging

from app.config import Settings
from app.database import init_db
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# Exact current URL -> durable eCFR replacement. Every target is parseable by
# fetch_ecfr_text (needs /title-N/ + /part-P/, or a chapter-level URL) so the
# repair pass can rebuild it via the versioner API. 2 CFR 200 subpart URLs are
# in the bundled seed manifest and rebuild from local text.
REMAP: dict[str, str] = {
    # Human Subjects / Common Rule (HHS OHRP HTML → 403) -> 45 CFR 46
    "https://www.hhs.gov/ohrp/regulations-and-policy/regulations/common-rule/index.html":
        "https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-A/part-46",
    # Financial Conflict of Interest (NSF PAPPG ch-9 → 404) -> 42 CFR 50 Subpart F (PHS FCOI)
    "https://new.nsf.gov/policies/pappg/24-1/ch-9-grantee-standards#ch9D4":
        "https://www.ecfr.gov/current/title-42/chapter-I/subchapter-D/part-50/subpart-F",
    # Export Control EAR (BIS HTML → 404) -> 15 CFR Chapter VII Subchapter C (EAR, parts 730-774)
    "https://www.bis.gov/regulations/export-administration-regulations-ear":
        "https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C",
    # Effort Reporting & Compensation (NIH senior-personnel HTML → 404) ->
    # 2 CFR 200 Subpart E (Cost Principles; compensation is § 200.430-.431)
    "https://grants.nih.gov/grants/policy/senior/index.htm":
        "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-E",
}


async def main(dry_run: bool) -> None:
    settings = Settings()
    await init_db(settings)

    # Cache KB names for readable reporting.
    kb_names: dict[str, str] = {}
    async for kb in KnowledgeBase.find_all():
        kb_names[kb.uuid] = kb.name

    remapped = 0
    for old_url, new_url in REMAP.items():
        sources = await KnowledgeBaseSource.find(
            {"source_type": "url", "url": old_url}
        ).to_list()
        if not sources:
            logger.info("No source matches %s", old_url)
            continue
        for src in sources:
            kb_label = kb_names.get(src.knowledge_base_uuid, src.knowledge_base_uuid)
            logger.info("  [%s]  %s\n        -> %s", kb_label, old_url, new_url)
            if dry_run:
                remapped += 1
                continue
            src.url = new_url
            src.content = None          # force repair_gov_kb_sources to rebuild
            src.status = "error"
            src.error_message = None
            await src.save()
            remapped += 1

    logger.info(
        "Done. %s %d source(s)%s",
        "Would remap" if dry_run else "Remapped",
        remapped,
        " (dry run — nothing written)" if dry_run
        else ". Now run: python -m scripts.repair_gov_kb_sources",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-point dead/blocked regulation KB sources at eCFR URLs"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
