"""Domain-specific extraction prompt templates for research administration.

Provides hardcoded knowledge for NSF, NIH, DOD, DOE grant types.
Admin can override via SystemConfig.extraction_config.domain_templates.
"""

DOMAIN_TEMPLATES = {
    "nsf": {
        "name": "National Science Foundation (NSF)",
        "system_supplement": (
            "You are extracting data from an NSF grant proposal or award document.\n\n"
            "Key NSF terminology:\n"
            "- Award Number: NSF award numbers follow the format XXXXXXX (7 digits)\n"
            "- Program Officer: NSF staff managing the award\n"
            "- PI/Co-PI: Principal Investigator / Co-Principal Investigator\n"
            "- Award Amount: Total federal funding amount\n"
            "- Award Period: Start date to end date\n"
            "- NSF Organization: Directorate and Division (e.g., BIO/DEB, CISE/CCF)\n"
            "- PAPPG: Proposal & Award Policies & Procedures Guide\n"
            "- GPG: Grant Proposal Guide\n\n"
            "Budget categories (NSF standard):\n"
            "- Senior Personnel, Other Personnel, Fringe Benefits\n"
            "- Equipment (>$5,000 per item), Travel (domestic/foreign)\n"
            "- Participant Support Costs (stipends, travel, subsistence, other)\n"
            "- Other Direct Costs (materials, publication, consulting, subawards, other)\n"
            "- Indirect Costs (F&A rate applied to MTDC)\n"
            "- Total Direct Costs, Total Indirect Costs, Total Project Cost\n"
        ),
        "field_hints": {
            "award_number": "7-digit NSF award number (e.g., 2345678)",
            "pi_name": "Full name of the Principal Investigator",
            "total_budget": "Sum of all budget categories including indirect costs",
            "start_date": "Award start date in MM/DD/YYYY format",
            "end_date": "Award end date in MM/DD/YYYY format",
            "indirect_cost_rate": "F&A rate as percentage applied to MTDC",
        },
    },
    "nih": {
        "name": "National Institutes of Health (NIH)",
        "system_supplement": (
            "You are extracting data from an NIH grant application or award document.\n\n"
            "Key NIH terminology:\n"
            "- Grant Number: Format is ActivityCode InstituteCode SerialNumber-SuffixYear (e.g., R01 GM123456-01A1)\n"
            "- Activity Code: R01, R21, K99/R00, U01, P01, T32, F31, etc.\n"
            "- Study Section: SRG (Scientific Review Group) that reviewed the application\n"
            "- IRG: Integrated Review Group\n"
            "- Impact/Priority Score: 10-90 scale (lower is better)\n"
            "- Percentile: Ranking within study section\n"
            "- PD/PI: Program Director / Principal Investigator\n"
            "- eRA Commons ID: Unique NIH researcher identifier\n"
            "- FOA: Funding Opportunity Announcement (PA, PAR, RFA)\n\n"
            "Budget categories (NIH PHS 398):\n"
            "- Personnel (name, role, % effort, salary, fringe)\n"
            "- Equipment, Travel, Patient Care (inpatient/outpatient)\n"
            "- Alterations and Renovations\n"
            "- Consortium/Contractual (direct + F&A)\n"
            "- Other Expenses\n"
            "- Direct Costs, Indirect Costs (F&A), Total Costs\n"
            "- Modular budget: $25,000 modules for R01 direct costs ≤$250K/year\n"
        ),
        "field_hints": {
            "grant_number": "NIH grant number (e.g., R01 GM123456-01A1)",
            "activity_code": "NIH activity code (e.g., R01, R21, K99)",
            "impact_score": "Score 10-90, lower is better",
            "total_direct_costs": "Total direct costs per year or entire project",
        },
    },
    "dod": {
        "name": "Department of Defense (DOD)",
        "system_supplement": (
            "You are extracting data from a DOD grant, contract, or research agreement.\n\n"
            "Key DOD terminology:\n"
            "- Contract/Award Number: DAXXXXXXXX or W9XXXXXXXXX format\n"
            "- BAA: Broad Agency Announcement\n"
            "- DARPA: Defense Advanced Research Projects Agency\n"
            "- ONR: Office of Naval Research\n"
            "- ARO: Army Research Office\n"
            "- AFOSR: Air Force Office of Scientific Research\n"
            "- CAGE Code: Commercial and Government Entity code\n"
            "- DUNS Number: Data Universal Numbering System\n"
            "- CDRL: Contract Data Requirements List\n"
            "- SOW: Statement of Work\n"
            "- DFARS: Defense FAR Supplement\n\n"
            "Cost categories (DOD standard):\n"
            "- Direct Labor (by labor category and hours)\n"
            "- Fringe Benefits, Overhead (G&A rate)\n"
            "- Subcontracts, Consultants\n"
            "- Materials/Supplies, Equipment, Travel\n"
            "- Other Direct Costs\n"
            "- Total Direct Costs, Total Indirect Costs, Fee/Profit\n"
            "- Total Estimated Cost\n\n"
            "IMPORTANT: DOD documents may contain CUI or ITAR data. Be precise about markings.\n"
        ),
        "field_hints": {
            "contract_number": "DOD contract or award number",
            "cage_code": "5-character CAGE code",
            "security_classification": "Unclassified, CUI, or classified marking",
        },
    },
    "doe": {
        "name": "Department of Energy (DOE)",
        "system_supplement": (
            "You are extracting data from a DOE grant, cooperative agreement, or lab contract.\n\n"
            "Key DOE terminology:\n"
            "- Award Number: DE-XXXX-XXXXXXXX format\n"
            "- FOA: Funding Opportunity Announcement\n"
            "- BES: Basic Energy Sciences\n"
            "- ASCR: Advanced Scientific Computing Research\n"
            "- FES: Fusion Energy Sciences\n"
            "- HEP: High Energy Physics\n"
            "- NP: Nuclear Physics\n"
            "- ARPA-E: Advanced Research Projects Agency–Energy\n"
            "- National Lab: DOE-funded national laboratories\n"
            "- NEPA: National Environmental Policy Act review\n\n"
            "Budget categories (DOE standard SF-424A):\n"
            "- Personnel, Fringe Benefits\n"
            "- Equipment, Travel (domestic/foreign)\n"
            "- Supplies, Contractual (subawards)\n"
            "- Construction, Other\n"
            "- Indirect Charges\n"
            "- Total Direct Costs, Total Project Costs\n"
            "- Cost Sharing (if required)\n"
        ),
        "field_hints": {
            "award_number": "DOE award number (DE-XXXX-XXXXXXXX format)",
            "program_office": "DOE program office (BES, ASCR, ARPA-E, etc.)",
            "cost_sharing": "Amount or percentage of cost sharing commitment",
        },
    },
}


def get_domain_template(domain: str, admin_overrides: dict | None = None) -> dict | None:
    """Get domain template, with admin overrides taking precedence."""
    if admin_overrides and domain in admin_overrides:
        return admin_overrides[domain]
    return DOMAIN_TEMPLATES.get(domain)


def get_field_hint(domain: str, field_name: str, admin_overrides: dict | None = None) -> str | None:
    """Get a per-field hint for a specific domain."""
    template = get_domain_template(domain, admin_overrides)
    if not template:
        return None
    hints = template.get("field_hints", {})
    # Try exact match, then fuzzy
    if field_name in hints:
        return hints[field_name]
    lower = field_name.lower().replace(" ", "_")
    for key, val in hints.items():
        if key.lower().replace(" ", "_") == lower:
            return val
    return None
