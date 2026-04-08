"""First-session onboarding — provision a sample document and look up seed content."""

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.models.document import SmartDocument
from app.models.knowledge import KnowledgeBase
from app.models.search_set import SearchSet
from app.models.user import User

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).resolve().parent.parent.parent / "seeds"
NSF_SEED_FILE = SEEDS_DIR / "search_sets" / "nsf_proposal_extraction.json"


@dataclass
class OnboardingContext:
    """Resources provisioned for the first-session agentic demo."""

    sample_doc_uuid: str
    sample_doc_title: str
    extraction_set_uuid: Optional[str]
    extraction_set_title: Optional[str]
    kb_uuid: Optional[str]
    kb_title: Optional[str]


async def provision_onboarding_sample(user: User) -> Optional[OnboardingContext]:
    """Create a sample document and look up verified seed content for the demo.

    Idempotent — reuses an existing sample doc if one was already created.
    Returns ``None`` if the seed file or verified content isn't available
    (graceful fallback to text-only onboarding).
    """
    try:
        # Reuse existing sample doc if already provisioned
        existing = await SmartDocument.find_one(
            SmartDocument.user_id == user.user_id,
            SmartDocument.is_onboarding_sample == True,  # noqa: E712
        )
        if existing:
            sample_doc = existing
        else:
            # Load NSF proposal test case from seed file
            if not NSF_SEED_FILE.exists():
                logger.warning("NSF seed file not found at %s", NSF_SEED_FILE)
                return None

            seed_data = json.loads(NSF_SEED_FILE.read_text())
            test_cases = seed_data.get("items", [{}])[0].get("test_cases", [])
            if not test_cases:
                logger.warning("No test cases in NSF seed file")
                return None

            source_text = test_cases[0].get("source_text", "")
            if not source_text:
                logger.warning("Empty source_text in first NSF test case")
                return None

            label = test_cases[0].get("label", "NSF Proposal")
            title = f"Sample: {label}"

            team_id = str(user.current_team) if user.current_team else None

            sample_doc = SmartDocument(
                path="",
                downloadpath="",
                title=title,
                uuid=str(uuid.uuid4()),
                user_id=user.user_id,
                team_id=team_id,
                raw_text=source_text,
                extension="txt",
                num_pages=2,
                is_onboarding_sample=True,
                classification="unrestricted",
            )
            await sample_doc.insert()
            logger.info(
                "Provisioned onboarding sample doc %s for user %s",
                sample_doc.uuid, user.user_id,
            )

        # Look up verified NSF extraction set
        extraction_set = await SearchSet.find_one(
            SearchSet.title == "NSF Grant Proposal",
            SearchSet.verified == True,  # noqa: E712
        )

        # Look up verified NSF PAPPG knowledge base
        kb = await KnowledgeBase.find_one(
            KnowledgeBase.title == "NSF PAPPG Reference",
            KnowledgeBase.verified == True,  # noqa: E712
        )

        # If no extraction set is seeded, the demo can't run
        if not extraction_set:
            logger.info("No verified NSF extraction set found — skipping agentic onboarding")
            return None

        return OnboardingContext(
            sample_doc_uuid=sample_doc.uuid,
            sample_doc_title=sample_doc.title,
            extraction_set_uuid=extraction_set.uuid,
            extraction_set_title=extraction_set.title,
            kb_uuid=kb.uuid if kb else None,
            kb_title=kb.title if kb else None,
        )

    except Exception as e:
        logger.error("Failed to provision onboarding sample: %s", e)
        return None
