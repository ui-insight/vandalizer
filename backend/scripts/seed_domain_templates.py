"""Seed verified SearchSets for common grant types (NSF, NIH, DOD, DOE).

Usage:
    cd backend
    python -m scripts.seed_domain_templates
"""

import asyncio
import uuid

from app.config import Settings
from app.database import init_db
from app.models.search_set import SearchSet, SearchSetItem


DOMAIN_TEMPLATES = {
    "nsf": {
        "title": "NSF Grant Proposal (Verified Template)",
        "fields": [
            "Award Number", "PI Name", "Co-PI Names", "Institution",
            "NSF Directorate", "NSF Division", "Program Officer",
            "Award Amount", "Award Start Date", "Award End Date",
            "Project Title", "Abstract",
            "Senior Personnel Costs", "Other Personnel Costs", "Fringe Benefits",
            "Equipment", "Travel Domestic", "Travel Foreign",
            "Participant Support Costs", "Other Direct Costs",
            "Total Direct Costs", "Indirect Costs", "Indirect Cost Rate",
            "Total Project Cost",
        ],
    },
    "nih": {
        "title": "NIH Grant Application (Verified Template)",
        "fields": [
            "Grant Number", "Activity Code", "PI Name", "Co-Investigators",
            "Institution", "NIH Institute/Center", "Study Section",
            "Impact Score", "Percentile",
            "FOA Number", "Project Title", "Project Period Start", "Project Period End",
            "Total Direct Costs Year 1", "Total Indirect Costs Year 1",
            "Total Costs Year 1", "Total Project Costs",
            "Specific Aims", "Human Subjects", "Vertebrate Animals",
        ],
    },
    "dod": {
        "title": "DOD Contract/Grant (Verified Template)",
        "fields": [
            "Contract Number", "Award Number", "Contractor Name",
            "CAGE Code", "PI Name", "Program Manager",
            "Statement of Work Summary", "Period of Performance Start",
            "Period of Performance End", "Total Estimated Cost",
            "Direct Labor", "Fringe Benefits", "Overhead",
            "Subcontracts", "Materials and Supplies", "Equipment",
            "Travel", "Other Direct Costs", "G&A Rate",
            "Fee/Profit", "Security Classification",
        ],
    },
    "doe": {
        "title": "DOE Award (Verified Template)",
        "fields": [
            "Award Number", "FOA Number", "PI Name", "Institution",
            "DOE Program Office", "Project Title",
            "Project Start Date", "Project End Date",
            "Total Federal Funding", "Cost Sharing Amount",
            "Personnel Costs", "Fringe Benefits", "Equipment",
            "Travel", "Supplies", "Contractual/Subawards",
            "Other Costs", "Indirect Charges",
            "Total Direct Costs", "Total Project Costs",
            "NEPA Status",
        ],
    },
}


async def seed():
    settings = Settings()
    await init_db(settings)

    for domain, template in DOMAIN_TEMPLATES.items():
        # Check if already exists
        existing = await SearchSet.find_one(
            SearchSet.title == template["title"],
            SearchSet.verified == True,  # noqa: E712
        )
        if existing:
            print(f"  Skipping {domain}: already exists (uuid={existing.uuid})")
            continue

        ss_uuid = str(uuid.uuid4())
        ss = SearchSet(
            title=template["title"],
            uuid=ss_uuid,
            space="global",
            status="active",
            set_type="extraction",
            is_global=True,
            verified=True,
            domain=domain,
        )
        await ss.insert()

        item_order = []
        for field_name in template["fields"]:
            item = SearchSetItem(
                searchphrase=field_name,
                searchset=ss_uuid,
                searchtype="extraction",
            )
            await item.insert()
            item_order.append(str(item.id))

        ss.item_order = item_order
        await ss.save()

        print(f"  Created {domain} template: {template['title']} (uuid={ss_uuid}, {len(template['fields'])} fields)")

    print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
