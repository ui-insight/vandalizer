"""Generate synthetic sample PDFs for the Vandal Workflow Architect certification.

Uses fpdf2 (pip install fpdf2)  -  zero system dependencies.
Run:  python certification-data/generate_pdfs.py
"""

from __future__ import annotations

import os
from pathlib import Path

from fpdf import FPDF

OUT_DIR = Path(__file__).parent / "documents"


class DocPDF(FPDF):
    """Minimal helper for consistent styling."""

    def header_block(self, title: str, subtitle: str = ""):
        self.set_font("Helvetica", "B", 18)
        self.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.set_font("Helvetica", "", 11)
            self.set_text_color(100, 100, 100)
            self.cell(0, 7, subtitle, new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(0, 0, 0)
        self.ln(4)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def section(self, title: str):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5.5, text)
        self.ln(3)

    def field(self, label: str, value: str):
        self.set_font("Helvetica", "B", 10)
        self.cell(55, 6, f"{label}:", new_x="END")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def table_row(self, cells: list[str], bold: bool = False):
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 9)
        col_w = (self.w - 20) / len(cells)
        for c in cells:
            self.cell(col_w, 6, c, border=1, new_x="END")
        self.ln()


# ---------------------------------------------------------------------------
# 1. NSF Proposal  -  Alpine Ecology
# ---------------------------------------------------------------------------

def gen_nsf_proposal():
    pdf = DocPDF()
    pdf.add_page()
    pdf.header_block(
        "NSF Grant Proposal",
        "Directorate for Biological Sciences - Division of Environmental Biology",
    )

    pdf.field("Proposal Number", "BIO-2024-07821")
    pdf.field("Program", "Ecosystem Science")
    pdf.field("Program Officer", "Dr. Katherine Wells")
    pdf.field("Submission Date", "October 15, 2024")
    pdf.ln(4)

    pdf.section("Project Information")
    pdf.field("Project Title", "Alpine Ecosystem Response to Climate Change in the Northern Rockies")
    pdf.field("Principal Investigator", "Dr. Sarah Chen")
    pdf.field("Co-PI", "Dr. Michael Torres")
    pdf.field("Institution", "University of Idaho")
    pdf.field("Department", "Department of Biological Sciences")
    pdf.field("Requested Amount", "$485,000")
    pdf.field("Project Period", "September 1, 2025 - August 31, 2028")
    pdf.field("Sponsoring Agency", "National Science Foundation")
    pdf.ln(4)

    pdf.section("Project Abstract")
    pdf.body(
        "This project investigates the impacts of climate change on alpine ecosystems in the Northern Rocky "
        "Mountains. Alpine environments are among the most sensitive indicators of climate change, yet remain "
        "understudied compared to lower-elevation systems. Our research combines long-term field monitoring, "
        "remote sensing, and ecological modeling to understand how rising temperatures, shifting precipitation "
        "patterns, and changing snowpack dynamics affect plant community composition, soil microbial diversity, "
        "and ecosystem carbon cycling.\n\n"
        "The study will establish 24 permanent monitoring plots across an elevational gradient (2,200-3,100m) "
        "in the Sawtooth and White Cloud mountain ranges. We will collect seasonal data on vegetation cover, "
        "soil temperature, moisture, and microbial community composition over the three-year project period. "
        "Satellite imagery and drone-based surveys will provide landscape-scale context for plot-level observations."
    )

    pdf.section("Budget Overview")
    pdf.table_row(["Category", "Year 1", "Year 2", "Year 3", "Total"], bold=True)
    pdf.table_row(["Personnel", "$95,000", "$98,000", "$101,000", "$294,000"])
    pdf.table_row(["Equipment", "$35,000", "$5,000", "$5,000", "$45,000"])
    pdf.table_row(["Travel", "$12,000", "$14,000", "$14,000", "$40,000"])
    pdf.table_row(["Supplies", "$10,000", "$8,000", "$8,000", "$26,000"])
    pdf.table_row(["Indirect Costs", "$25,000", "$27,000", "$28,000", "$80,000"])
    pdf.table_row(["Total", "$177,000", "$152,000", "$156,000", "$485,000"])
    pdf.ln(4)

    pdf.section("Broader Impacts")
    pdf.body(
        "This project will train 4 graduate students and 8 undergraduate researchers in alpine ecology and "
        "climate science. Results will be shared with the Sawtooth National Recreation Area and the U.S. Forest "
        "Service to inform land management decisions. We will develop educational materials for Idaho high school "
        "science teachers, reaching an estimated 500 students per year through a summer workshop program."
    )

    pdf.output(str(OUT_DIR / "nsf-proposal-alpine-ecology.pdf"))


# ---------------------------------------------------------------------------
# 2. NIH R01  -  Neuroscience
# ---------------------------------------------------------------------------

def gen_nih_r01():
    pdf = DocPDF()
    pdf.add_page()
    pdf.header_block(
        "NIH Research Project Grant (R01)",
        "National Institute of Neurological Disorders and Stroke (NINDS)",
    )

    pdf.field("Grant Number", "1R01NS123456-01")
    pdf.field("FOA Number", "PA-23-152")
    pdf.field("Study Section", "Neurotransporters, Receptors, and Calcium Signaling (NTRC)")
    pdf.field("Funding Mechanism", "R01  -  Research Project Grant")
    pdf.field("Submission Date", "February 5, 2024")
    pdf.ln(4)

    pdf.section("Project Information")
    pdf.field("Project Title", "Neural Circuit Mechanisms of Working Memory in Prefrontal Cortex")
    pdf.field("Principal Investigator", "Dr. James Park")
    pdf.field("Degree", "Ph.D.")
    pdf.field("Institution", "University of Idaho")
    pdf.field("Department", "Department of Biological Sciences  -  Neuroscience Program")
    pdf.field("Total Budget", "$1,250,000")
    pdf.field("Project Period", "July 1, 2024 - June 30, 2029")
    pdf.field("Sponsoring Agency", "National Institutes of Health")
    pdf.field("Human Subjects", "No")
    pdf.field("Vertebrate Animals", "Yes  -  Mouse model (Mus musculus)")
    pdf.field("Clinical Trial", "No")
    pdf.ln(4)

    pdf.section("Specific Aims")
    pdf.body(
        "Aim 1: Characterize the firing patterns of prefrontal cortex (PFC) neurons during working memory "
        "tasks using two-photon calcium imaging in head-fixed mice.\n\n"
        "Aim 2: Determine the causal role of PFC-to-hippocampal projections in working memory maintenance "
        "using optogenetic manipulation.\n\n"
        "Aim 3: Develop a computational model of PFC circuit dynamics that predicts working memory capacity "
        "from neural population activity patterns."
    )

    pdf.section("Key Personnel")
    pdf.table_row(["Name", "Role", "Effort", "Department"], bold=True)
    pdf.table_row(["Dr. James Park", "PI", "30%", "Biological Sciences"])
    pdf.table_row(["Dr. Lisa Yamamoto", "Co-Investigator", "15%", "Psychology"])
    pdf.table_row(["Dr. Raj Patel", "Co-Investigator", "10%", "Computer Science"])
    pdf.table_row(["TBD", "Postdoctoral Fellow", "100%", "Biological Sciences"])
    pdf.table_row(["TBD", "Graduate Student 1", "50%", "Neuroscience Program"])
    pdf.table_row(["TBD", "Graduate Student 2", "50%", "Neuroscience Program"])
    pdf.ln(4)

    pdf.section("Budget Justification")
    pdf.table_row(["Category", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5", "Total"], bold=True)
    pdf.table_row(["Personnel", "$120,000", "$124,000", "$128,000", "$132,000", "$121,000", "$625,000"])
    pdf.table_row(["Equipment", "$85,000", "$15,000", "$10,000", "$10,000", "$5,000", "$125,000"])
    pdf.table_row(["Travel", "$8,000", "$10,000", "$10,000", "$12,000", "$10,000", "$50,000"])
    pdf.table_row(["Supplies", "$30,000", "$28,000", "$28,000", "$25,000", "$24,000", "$135,000"])
    pdf.table_row(["Other", "$10,000", "$10,000", "$10,000", "$10,000", "$10,000", "$50,000"])
    pdf.table_row(["Indirect (52%)", "$51,000", "$53,000", "$55,000", "$57,000", "$49,000", "$265,000"])
    pdf.table_row(["Total", "$304,000", "$240,000", "$241,000", "$246,000", "$219,000", "$1,250,000"])
    pdf.ln(4)

    pdf.section("Research Strategy")
    pdf.body(
        "Working memory, the ability to transiently hold and manipulate information, is fundamental to "
        "cognition. Deficits in working memory are observed in schizophrenia, ADHD, and age-related cognitive "
        "decline. Despite decades of research, the circuit-level mechanisms by which prefrontal cortex (PFC) "
        "neurons maintain persistent activity during working memory remain poorly understood.\n\n"
        "This project employs state-of-the-art two-photon calcium imaging to record the activity of hundreds "
        "of PFC neurons simultaneously in behaving mice performing a delayed non-match-to-sample task. Combined "
        "with optogenetic manipulation of specific projection pathways and computational modeling, we aim to "
        "provide a comprehensive understanding of how PFC circuits support working memory."
    )

    pdf.section("Vertebrate Animals")
    pdf.body(
        "All procedures will be performed in accordance with the NIH Guide for the Care and Use of Laboratory "
        "Animals and approved by the University of Idaho IACUC (Protocol #2024-015). We will use approximately "
        "200 adult C57BL/6J mice (both sexes, 8-12 weeks old) over the project period. Mice will be housed in "
        "the university vivarium with standard 12h light/dark cycles and ad libitum food and water access."
    )

    pdf.output(str(OUT_DIR / "nih-r01-neuroscience.pdf"))


# ---------------------------------------------------------------------------
# 3. Subaward Agreement
# ---------------------------------------------------------------------------

def gen_subaward():
    pdf = DocPDF()
    pdf.add_page()
    pdf.header_block(
        "Subaward Agreement",
        "Federal Research Subaward under 2 CFR 200",
    )

    pdf.field("Subaward Number", "UI-BSU-2024-0847")
    pdf.field("Prime Award Number", "BIO-2024-07821")
    pdf.field("Prime Sponsor", "National Science Foundation")
    pdf.field("Effective Date", "September 1, 2025")
    pdf.ln(4)

    pdf.section("Parties")
    pdf.field("Prime Recipient (Pass-Through Entity)", "University of Idaho")
    pdf.field("Prime Recipient Address", "875 Perimeter Drive, Moscow, ID 83844")
    pdf.field("Prime PI", "Dr. Sarah Chen")
    pdf.field("Subrecipient", "Boise State University")
    pdf.field("Subrecipient Address", "1910 University Drive, Boise, ID 83725")
    pdf.field("Subrecipient PI", "Dr. Emily Rodriguez")
    pdf.field("DUNS Number (Subrecipient)", "072995848")
    pdf.field("EIN (Subrecipient)", "82-0384947")
    pdf.ln(4)

    pdf.section("Subaward Terms")
    pdf.field("Subaward Amount", "$185,000")
    pdf.field("Performance Period", "September 1, 2025 - August 31, 2028")
    pdf.field("Cost Sharing Required", "No")
    pdf.field("CFDA Number", "47.074  -  Biological Sciences")
    pdf.field("F&A Rate (Subrecipient)", "48% MTDC")
    pdf.ln(4)

    pdf.section("Scope of Work")
    pdf.body(
        "The Subrecipient shall perform the following work in support of the prime project 'Alpine Ecosystem "
        "Response to Climate Change in the Northern Rockies':\n\n"
        "1. Conduct soil microbial community analysis using metagenomic sequencing at 12 monitoring plots.\n"
        "2. Process and analyze soil samples collected by the Prime Recipient's field team.\n"
        "3. Maintain a culture collection of alpine soil microorganisms.\n"
        "4. Contribute to joint publications and annual reports."
    )

    pdf.section("Deliverables")
    pdf.body(
        "D1. Quarterly data summaries of microbial community composition (due 30 days after quarter end).\n"
        "D2. Annual progress report aligned with NSF reporting requirements (due November 30 each year).\n"
        "D3. Final dataset in NCBI Sequence Read Archive format (due within 60 days of project end).\n"
        "D4. Co-authored manuscript(s) submitted to peer-reviewed journal(s)."
    )

    pdf.section("Budget")
    pdf.table_row(["Category", "Year 1", "Year 2", "Year 3", "Total"], bold=True)
    pdf.table_row(["Personnel", "$28,000", "$29,000", "$30,000", "$87,000"])
    pdf.table_row(["Supplies", "$15,000", "$12,000", "$10,000", "$37,000"])
    pdf.table_row(["Travel", "$3,000", "$3,000", "$3,000", "$9,000"])
    pdf.table_row(["Indirect (48%)", "$16,000", "$17,000", "$19,000", "$52,000"])
    pdf.table_row(["Total", "$62,000", "$61,000", "$62,000", "$185,000"])
    pdf.ln(4)

    pdf.section("Reporting Schedule")
    pdf.body(
        "Financial reports: Quarterly, due within 30 days of quarter end.\n"
        "Technical reports: Semi-annually, due January 31 and July 31.\n"
        "Final report: Due within 90 days of subaward end date.\n"
        "Invention disclosures: Within 60 days of conception or first actual reduction to practice."
    )

    pdf.section("Compliance Requirements")
    pdf.body(
        "The Subrecipient agrees to comply with all applicable federal regulations including:\n"
        "- 2 CFR 200 (Uniform Guidance)\n"
        "- NSF Grant General Conditions (GC-1)\n"
        "- NSF Proposal and Award Policies and Procedures Guide (PAPPG)\n"
        "- Institutional policies for responsible conduct of research\n"
        "- Export control regulations (EAR/ITAR) as applicable"
    )

    pdf.output(str(OUT_DIR / "subaward-agreement.pdf"))


# ---------------------------------------------------------------------------
# 4. Budget Justification
# ---------------------------------------------------------------------------

def gen_budget_justification():
    pdf = DocPDF()
    pdf.add_page()
    pdf.header_block(
        "Budget Justification",
        "NSF Proposal BIO-2024-07821  -  Alpine Ecosystem Response to Climate Change",
    )

    pdf.section("A. Senior Personnel")
    pdf.table_row(["Name", "Role", "Months", "Rate", "Requested"], bold=True)
    pdf.table_row(["Dr. Sarah Chen", "PI", "3.0", "$110,000/yr", "$27,500"])
    pdf.table_row(["Dr. Michael Torres", "Co-PI", "2.0", "$95,000/yr", "$15,833"])
    pdf.body("Total Senior Personnel: $43,333")

    pdf.section("B. Other Personnel")
    pdf.table_row(["Position", "Number", "Months", "Rate", "Requested"], bold=True)
    pdf.table_row(["Postdoctoral Researcher", "1", "12.0", "$55,000/yr", "$55,000"])
    pdf.table_row(["Graduate Student (RA)", "2", "12.0", "$28,000/yr", "$56,000"])
    pdf.table_row(["Undergraduate Hourly", "4", "3.0", "$15/hr (480 hrs)", "$28,800"])
    pdf.body("Total Other Personnel: $139,800")

    pdf.section("C. Fringe Benefits")
    pdf.body(
        "Faculty: 32% of salary = $13,867\n"
        "Postdoc: 28% of salary = $15,400\n"
        "Graduate Students: 12% of stipend = $6,720\n"
        "Undergraduates: 8% of wages = $2,304\n"
        "Total Fringe Benefits: $38,291"
    )

    pdf.section("D. Equipment")
    pdf.body(
        "Portable weather station array (6 units): $18,000\n"
        "Soil CO2 flux measurement system: $12,000\n"
        "DJI Matrice 350 RTK drone with multispectral sensor: $15,000\n"
        "Total Equipment: $45,000"
    )

    pdf.section("E. Travel")
    pdf.body(
        "Field site access (Moscow to Sawtooth Range, 300 mi RT):\n"
        "  12 trips x $250 fuel/lodging = $3,000/year x 3 years = $9,000\n"
        "Conference travel (ESA Annual Meeting):\n"
        "  3 attendees x $2,000 = $6,000/year x 3 years = $18,000\n"
        "Collaborator visits to Boise State:\n"
        "  4 trips x $500 = $2,000/year x 3 years = $6,000\n"
        "Workshop travel for broader impacts:\n"
        "  $2,333/year x 3 years = $7,000\n"
        "Total Travel: $40,000"
    )

    pdf.section("F. Supplies")
    pdf.body(
        "Soil sampling kits and consumables: $8,000\n"
        "DNA extraction and sequencing reagents: $10,000\n"
        "Field marking and monitoring equipment: $4,000\n"
        "Computing supplies (drives, cables, batteries): $4,000\n"
        "Total Supplies: $26,000"
    )

    pdf.section("G. Subaward")
    pdf.body(
        "Boise State University (Dr. Emily Rodriguez): $185,000\n"
        "  Microbial community analysis, metagenomic sequencing, and soil sample processing.\n"
        "  (First $25,000 subject to indirect costs per university policy)\n"
        "Total Subawards: $185,000"
    )

    pdf.section("H. Indirect Costs")
    pdf.body(
        "MTDC base: Total direct costs minus equipment and subaward amount over $25,000\n"
        "MTDC base = $542,800 - $45,000 - $160,000 = $337,800\n"
        "UI negotiated rate: 52% MTDC (effective 7/1/2023)\n"
        "Indirect costs not yet applied separately in this justification.\n\n"
        "Note: The total project budget of $542,800 includes all direct costs listed above."
    )

    pdf.section("Budget Summary")
    pdf.table_row(["Category", "Amount"], bold=True)
    pdf.table_row(["Senior Personnel", "$43,333"])
    pdf.table_row(["Other Personnel", "$139,800"])
    pdf.table_row(["Fringe Benefits", "$38,291"])
    pdf.table_row(["Equipment", "$45,000"])
    pdf.table_row(["Travel", "$40,000"])
    pdf.table_row(["Supplies", "$26,000"])
    pdf.table_row(["Subaward", "$185,000"])
    pdf.table_row(["Indirect Costs (estimated)", "$25,376"])
    pdf.table_row(["TOTAL", "$542,800"])

    pdf.output(str(OUT_DIR / "budget-justification.pdf"))


# ---------------------------------------------------------------------------
# 5. Progress Report  -  Year 2
# ---------------------------------------------------------------------------

def gen_progress_report():
    pdf = DocPDF()
    pdf.add_page()
    pdf.header_block(
        "Annual Progress Report  -  Year 2",
        "NSF Award BIO-2024-07821",
    )

    pdf.field("Project Title", "Alpine Ecosystem Response to Climate Change in the Northern Rockies")
    pdf.field("Principal Investigator", "Dr. Sarah Chen")
    pdf.field("Institution", "University of Idaho")
    pdf.field("Reporting Period", "September 1, 2026 - August 31, 2027")
    pdf.field("Award Amount", "$485,000")
    pdf.field("Report Submission Date", "October 15, 2027")
    pdf.ln(4)

    pdf.section("1. Accomplishments")
    pdf.body(
        "Major Activities:\n"
        "- Completed second full year of seasonal monitoring across all 24 permanent plots.\n"
        "- Deployed 6 additional soil moisture sensors at elevations above 2,800m.\n"
        "- Conducted drone-based multispectral surveys in June, August, and October 2027.\n"
        "- Initiated collaboration with USGS Northern Rocky Mountain Science Center.\n\n"
        "Specific Objectives Met:\n"
        "- Objective 1 (Field monitoring): All 24 plots sampled in all four seasons. Data quality >98%.\n"
        "- Objective 2 (Remote sensing): Generated high-resolution NDVI maps for the study area covering 3 survey dates.\n"
        "- Objective 3 (Soil microbiology): Processed 96 soil samples for metagenomic analysis at BSU."
    )

    pdf.section("2. Publications")
    pdf.body(
        "1. Chen, S., Torres, M., & Rodriguez, E. (2027). 'Elevational gradients in alpine soil microbial diversity: "
        "A metagenomic perspective.' Ecology Letters, 30(4), 512-528. DOI: 10.1111/ele.14523\n\n"
        "2. Torres, M. & Chen, S. (2027). 'Drone-based monitoring of alpine vegetation phenology.' "
        "Remote Sensing of Environment, 298, 113842. DOI: 10.1016/j.rse.2027.113842\n\n"
        "3. Park, J.L., Chen, S., & Williams, K. (2027). 'Snowpack decline and its effects on alpine meadow "
        "plant community composition.' Journal of Ecology, 115(2), 234-249. (In review)\n\n"
        "4. Chen, S. (2027). 'Climate change impacts on Northern Rocky Mountain ecosystems: A synthesis.' "
        "Invited chapter in 'Mountain Ecosystems Under Pressure' (Springer). (In press)\n\n"
        "5. Rodriguez, E. & Chen, S. (2027). 'Novel soil bacteria from alpine environments: Potential for "
        "cold-adapted enzyme discovery.' Applied and Environmental Microbiology. (Submitted)"
    )

    pdf.section("3. Students and Training")
    pdf.body(
        "Graduate Students:\n"
        "- Maria Gonzalez (Ph.D., Year 3)  -  Dissertation on alpine plant community dynamics.\n"
        "- Tyler Morrison (M.S., Year 2)  -  Thesis on soil carbon cycling.\n"
        "- Priya Sharma (Ph.D., Year 1)  -  Starting dissertation on microbial functional genomics.\n\n"
        "Undergraduate Researchers:\n"
        "- 6 undergraduates participated in summer field work (REU supplement pending).\n"
        "- 2 undergraduates presented posters at the Idaho Academy of Sciences meeting.\n\n"
        "Total students trained this period: 9"
    )

    pdf.section("4. Budget Expenditures")
    pdf.table_row(["Category", "Year 2 Budget", "Year 2 Spent", "Cumulative Spent"], bold=True)
    pdf.table_row(["Personnel", "$98,000", "$96,500", "$191,500"])
    pdf.table_row(["Equipment", "$5,000", "$4,200", "$39,200"])
    pdf.table_row(["Travel", "$14,000", "$13,800", "$25,800"])
    pdf.table_row(["Supplies", "$8,000", "$7,500", "$17,500"])
    pdf.table_row(["Indirect", "$27,000", "$13,500", "$13,500"])
    pdf.table_row(["Total", "$152,000", "$135,500", "$287,500"])
    pdf.body("Remaining budget: $197,500\nBurn rate is on track for the 3-year project timeline.")
    pdf.ln(2)

    pdf.section("5. Upcoming Milestones (Year 3)")
    pdf.body(
        "- Complete final year of seasonal field monitoring (Sep 2027 - Aug 2028).\n"
        "- Submit 2-3 additional manuscripts for publication.\n"
        "- Host Idaho high school teacher workshop on alpine ecology (Summer 2028).\n"
        "- Prepare and submit final project report to NSF.\n"
        "- Archive all data in the Environmental Data Initiative (EDI) repository.\n"
        "- Present findings at ESA 2028 Annual Meeting."
    )

    pdf.output(str(OUT_DIR / "progress-report-year2.pdf"))


# ---------------------------------------------------------------------------
# 6-8. Batch proposals (3 synthetic NSF proposals)
# ---------------------------------------------------------------------------

def _gen_batch_proposal(filename: str, pi: str, dept: str, title: str, amount: str, abstract: str):
    pdf = DocPDF()
    pdf.add_page()
    pdf.header_block("NSF Grant Proposal", "Directorate for Biological Sciences")

    pdf.field("Proposal Number", f"BIO-2024-{hash(pi) % 90000 + 10000:05d}")
    pdf.field("Submission Date", "November 1, 2024")
    pdf.ln(4)

    pdf.section("Project Information")
    pdf.field("Project Title", title)
    pdf.field("Principal Investigator", pi)
    pdf.field("Institution", "University of Idaho")
    pdf.field("Department", dept)
    pdf.field("Requested Amount", amount)
    pdf.field("Project Period", "January 1, 2026 - December 31, 2028")
    pdf.field("Sponsoring Agency", "National Science Foundation")
    pdf.field("Research Area", dept.replace("Department of ", ""))
    pdf.ln(4)

    pdf.section("Project Abstract")
    pdf.body(abstract)

    pdf.output(str(OUT_DIR / filename))


def gen_batch_proposals():
    _gen_batch_proposal(
        "proposal-batch-1.pdf",
        pi="Dr. Maria Lopez",
        dept="Department of Environmental Science",
        title="Microplastic Transport Dynamics in Pacific Northwest Watersheds",
        amount="$320,000",
        abstract=(
            "This project examines the transport, accumulation, and ecological impacts of microplastic "
            "pollution in freshwater systems of the Pacific Northwest. Using a combination of field sampling, "
            "laboratory analysis, and hydrological modeling, we will characterize microplastic concentrations "
            "across 15 watersheds in Idaho and Washington. The study will identify key transport pathways, "
            "seasonal variation in microplastic loading, and relationships between land use and contamination "
            "levels. Results will inform regional water quality management strategies and contribute to "
            "national databases on freshwater microplastic pollution."
        ),
    )
    _gen_batch_proposal(
        "proposal-batch-2.pdf",
        pi="Dr. Robert Kim",
        dept="Department of Computer Science",
        title="Privacy-Preserving Federated Learning for Rural Healthcare Networks",
        amount="$275,000",
        abstract=(
            "Rural healthcare providers often lack sufficient patient data to train accurate machine learning "
            "models for clinical decision support. This project develops a federated learning framework that "
            "enables multiple rural hospitals and clinics to collaboratively train models without sharing "
            "sensitive patient data. We will implement differential privacy guarantees, develop communication-"
            "efficient protocols for low-bandwidth rural networks, and validate our approach on three clinical "
            "prediction tasks: emergency department triage, readmission risk, and medication interaction "
            "detection. The project includes partnerships with 5 critical access hospitals in Idaho."
        ),
    )
    _gen_batch_proposal(
        "proposal-batch-3.pdf",
        pi="Dr. Amara Okafor",
        dept="Department of Chemistry",
        title="Catalytic Conversion of Agricultural Waste to Sustainable Aviation Fuel",
        amount="$410,000",
        abstract=(
            "Idaho produces over 8 million tons of agricultural residue annually, most of which is burned or "
            "left to decompose. This project develops novel heterogeneous catalysts for the thermochemical "
            "conversion of wheat straw and potato waste into drop-in sustainable aviation fuel (SAF). We will "
            "synthesize and characterize bifunctional zeolite catalysts, optimize pyrolysis and "
            "hydrodeoxygenation conditions, and assess the techno-economic viability of a regional SAF "
            "production facility. The work addresses DOE and FAA targets for 3 billion gallons of SAF by 2030 "
            "while creating economic opportunity for Idaho's agricultural sector."
        ),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gen_nsf_proposal()
    gen_nih_r01()
    gen_subaward()
    gen_budget_justification()
    gen_progress_report()
    gen_batch_proposals()
    print(f"Generated {len(list(OUT_DIR.glob('*.pdf')))} PDFs in {OUT_DIR}/")


if __name__ == "__main__":
    main()
