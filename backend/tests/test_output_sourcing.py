"""Sourcing (app.services.output_sourcing): every statement in a workflow's
output is linked to the place it came from only when a judge says the place
states it AND the engine confirms the excerpt, its values, a shared label
word beside each value, and the page. Anything less leaves it plain.

The fake judge below answers from rules, so each test controls exactly what
the model claims and checks what the engine lets through."""

import copy
import json
import re

import pytest

from app.services.output_sourcing import (
    ROLE_INSTRUCTIONS,
    ROLE_VOTES,
    Corpus,
    obligation_differs,
    stems,
    trace_sources,
    values_in,
    verify,
)
from app.services.output_statements import split_output


# ---------------------------------------------------------------------------
# Fixtures: documents shaped like the real ones
# ---------------------------------------------------------------------------

FILLER = ("Recipients shall comply with the general terms of this agreement and maintain "
          "records as described elsewhere in this notice. ") * 8   # ~1,000 chars of nothing


def _doc(uuid, title, pages, approximate=False):
    """A document whose pages are joined in order, with page markers."""
    text, markers = "", []
    for n, page in enumerate(pages, 1):
        m = {"char_offset": len(text), "kind": "page", "value": n}
        if approximate:
            m["approximate"] = True
        markers.append(m)
        text += page
    return {"uuid": uuid, "title": title, "raw_text": text, "text_markers": markers}


# The Notice of Award's form page keeps its labels in one block and its
# figures in another: 96,673.48 is the award total, not the direct costs.
NOA = _doc("noa", "NoA.pdf", [
    "NOTICE OF AWARD\nU.S. Department of the Interior\nBureau of Land Management\n"
    " TOTAL DIRECT COSTS \nINDIRECT COSTS     \nTOTAL APPROVED BUDGET\nFederal Share \n"
    "82,275.30\n14,398.18\n96,673.48\n0.00\n96,673.48\n4. GRANT NO. L24AC00293-00\n" + FILLER,
    "Recipient: Southern Utah University\nThis agreement is administered by the Bureau of "
    "Land Management, Utah State Office.\nProject period: 08/21/2024 through 09/20/2029.\n" + FILLER,
    "Indirect Cost Rate: 17.5% (CESU rate cap).\nThe Bureau of Land Management program "
    "officer approves all budget revisions.\nBudget summary: Total Direct Costs: $82,275.30\n" + FILLER,
])
EXPENSE = {
    "uuid": "exp", "title": "Expense_Record.txt", "text_markers": [],
    "raw_text": (
        "EXPENSE RECORD\nAward: L24AC00293-00 (BLM, Southern Utah University)\n"
        "Vendor: Forestry Suppliers Inc.\nDate: 2025-03-14\n"
        "Description: GPS receivers (2) for field plant surveys\nAmount: $1,240.00\n"
    ),
}
KB_PASSAGE = {
    "chunk_id": "ug_e_10", "kb_title": "OMB Uniform Guidance", "document_title": "Subpart E",
    "label": "OMB Uniform Guidance — Subpart E · part 10", "page": None,
    "content": ("§ 200.404 Reasonable costs.\nA cost is reasonable if, in its nature and amount, "
                "it does not exceed that which would be incurred by a prudent person under the "
                "circumstances prevailing at the time the decision was made to incur the cost."),
}


# ---------------------------------------------------------------------------
# A judge that says what the test tells it to
# ---------------------------------------------------------------------------

_PASSAGE_RE = re.compile(r'<passage id="(P\d+)" source="[^"]*">\n(.*?)\n</passage>', re.S)


class Judge:
    """``rules``: (statement substring, passage substring, quote). For each
    statement whose text contains the first, answer supported with the
    first offered passage containing the second and the given quote. Every
    other statement is unsupported. Records the statements it was asked.

    A role check is answered by ``role(item, n)`` — the item it was shown,
    and how many role items it was shown before — yes unless told
    otherwise; ``role_asked`` records them."""

    def __init__(self, *rules, raises=None, reply=None, role=None, role_raises=None):
        self.rules = rules
        self.raises = raises
        self.reply = reply
        self.role = role or (lambda item, n: True)
        self.role_raises = role_raises
        self.asked: list[dict] = []
        self.role_asked: list[dict] = []

    def __call__(self, instructions, prompt):
        if self.raises:
            raise self.raises
        if self.reply is not None:
            return self.reply
        items = [json.loads(line) for line in prompt.split("STATEMENTS", 1)[1].splitlines() if line.strip()]
        if instructions == ROLE_INSTRUCTIONS:
            if self.role_raises:
                raise self.role_raises
            out = []
            for it in items:
                out.append({"id": it["id"], "passage_says": "", "shown": self.role(it, len(self.role_asked))})
                self.role_asked.append(it)
            return json.dumps({"items": out})
        passages = dict(_PASSAGE_RE.findall(prompt))
        self.asked.extend(items)
        out = []
        for it in items:
            answer = {"id": it["id"], "supported": False}
            for needle, where, quote in self.rules:
                if needle not in it["statement"]:
                    continue
                pid = next((p for p in it["passages"] if where in passages[p]), None)
                if pid is None and where.startswith("@"):
                    pid = where[1:]   # name a passage outright, offered or not
                if pid:
                    answer = {"id": it["id"], "supported": True, "passage": pid, "quote": quote}
                break
            out.append(answer)
        return json.dumps({"items": out})


def _trace(targets, judge, docs=(NOA, EXPENSE), passages=()):
    return trace_sources(targets, list(docs), list(passages), ask=judge, workers=1)


def _links(result, key):
    """[(statement text, source)] for every traced statement of a target."""
    t = result["targets"][key]
    return [(row, result["sources"][row["src"]]) for row in t["statements"] if "src" in row]


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

MARKDOWN = (
    "# Award summary\n\n"
    "**Sponsor:** Bureau of Land Management\n"
    "**Opportunity Number:** Not specified in the document\n"
    "- **Decision:** Pass\n"
    "- Recipients from non‑U.S. Federal entities are excluded. The rate is 17.5%.\n\n"
    "| Deadline / Event | Date / Time | Notes |\n|---|---|---|\n"
    "| Full Applications Due | 2022-07-13 5:00 PM ET | July 13, 2022 |\n"
)


def test_markdown_statements_are_spans_of_what_is_shown():
    fmt, stmts = split_output(MARKDOWN)
    assert fmt == "text"
    shown = [(MARKDOWN[s.start:s.end], s.label, s.kind) for s in stmts]
    assert shown == [
        ("Bureau of Land Management", "Sponsor", "claim"),
        ("Not specified in the document", "Opportunity Number", "absent"),
        ("Pass", "Decision", "verdict"),
        # The abbreviation does not end a sentence; the period does.
        ("Recipients from non‑U.S. Federal entities are excluded.", "", "claim"),
        ("The rate is 17.5%.", "", "claim"),
        ("2022-07-13 5:00 PM ET", "Full Applications Due — Date / Time", "claim"),
        ("July 13, 2022", "Full Applications Due — Notes", "claim"),
    ]


def test_json_text_statements_are_its_leaves_with_their_keys_as_labels():
    text = json.dumps({"award_number": "L24AC00293-00", "amount": 1240.0, "allowable": True,
                       "categories": [{"category": "Total Direct Costs", "approved_amount": 96673.48}],
                       "note": "Uses a \"quoted\" word."}, indent=2)
    fmt, stmts = split_output(text)
    got = [(text[s.start:s.end], s.label, s.kind) for s in stmts]
    assert ("L24AC00293-00", "award number", "claim") in got
    assert ("1240.0", "amount", "claim") in got
    assert ("true", "allowable", "verdict") in got
    assert ("96673.48", "categories — Total Direct Costs — approved amount", "claim") in got
    # A span over an escaped string covers the escapes as written.
    assert ('Uses a \\"quoted\\" word.', "note", "claim") in got


def test_structured_values_address_statements_by_path_and_read_embedded_json():
    """A step's list of JSON strings (the cost workflow's step 1) is shown
    as JSON; each statement is a path plus a span inside that string."""
    value = [json.dumps({"vendor": "Forestry Suppliers Inc.", "quantity": 2}, indent=2), {"rate": "17.5%"}]
    fmt, stmts = split_output(value)
    assert fmt == "json"
    got = []
    for s in stmts:
        leaf = value
        for p in s.path:
            leaf = leaf[p]
        got.append((s.path, leaf[s.start:s.end], s.label))
    assert got == [([0], "Forestry Suppliers Inc.", "vendor"), ([0], "2", "quantity"), ([1, "rate"], "17.5%", "rate")]


def test_identifiers_lead_ins_and_provenance_columns_are_not_statements():
    """Seen in real runs: a check id, an evidence pointer, a "Check
    results:" lead-in and a "Source: Announcement" column are not things a
    reader would check against a document; counting them only pads the
    untraced total."""
    value = {"check_id": "cost-period", "evidence": [{"source_label": "expense:transaction_date", "detail": "2025-03-14"}],
             "status": "needs_info", "pointer": "award_terms:period_of_performance"}
    _, stmts = split_output(value)
    assert [(s.path, s.text, s.kind) for s in stmts] == [
        (["evidence", 0, "detail"], "2025-03-14", "claim"),
        (["status"], "needs_info", "verdict"),
    ]
    md = "Check results:\n\n| Component | Details | Source |\n|---|---|---|\n| Project title | Up to 250 characters | Announcement |\n"
    _, stmts = split_output(md)
    assert [(s.text, s.label) for s in stmts] == [("Up to 250 characters", "Project title — Details")]


def test_a_record_name_labels_its_fields():
    value = [{"source_document": "Expense Record", "currency": "USD"}]
    _, stmts = split_output(value)
    assert [s.label for s in stmts] == ["source document", "Expense Record — currency"]


def test_json_text_rows_also_say_where_each_statement_sits_in_its_leaf():
    """Test Step shows a JSON reply pretty-printed, so a row of a text
    target that is JSON carries its path and leaf offsets too."""
    text = '{"note": "The award is \\"final\\". It runs to 2029.", "n": 2}'
    judge = Judge()
    result = _trace({"final": text}, judge, docs=[])
    rows = result["targets"]["final"]["statements"]
    leaf = json.loads(text)["note"]
    got = [(r["p"], text[r["s"]:r["e"]], leaf[r["ls"]:r["le"]] if "ls" in r else None) for r in rows]
    assert got == [
        (["note"], 'The award is \\"final\\".', 'The award is "final".'),
        (["note"], "It runs to 2029.", "It runs to 2029."),
        (["n"], "2", None),
    ]


def test_a_bold_line_without_a_sentence_is_a_heading():
    """Seen in a real run: "**Allocability of the cost**" heads a section;
    linked to a passage on allocability, it read as a sourced claim."""
    md = "**Allocability of the cost**\n\n- The cost is allocable.\n\n**The award ends in 2029.**\n"
    _, stmts = split_output(md)
    assert [md[s.start:s.end] for s in stmts] == ["The cost is allocable.", "The award ends in 2029."]


ELIGIBILITY_MD = (
    "# RFA Checklist\n\n"
    "## ELIGIBILITY\n\n"
    "### Eligible Individuals\n\n"
    "- **Principal Investigator**\n"
    "  - Criteria: Must be a full-time employee of the lead institution\n\n"
    "- **Co‑Principal Investigator**\n"
    "  - Criteria: Must be a full-time employee of the lead institution\n\n"
    "**Budget**\n\n"
    "- **Unallowable Costs:**\n"
    "  - Post-fire perishable data collection\n"
    "Plain paragraph after the list.\n"
)


def test_a_markdown_statement_carries_the_headings_and_items_above_it():
    _, stmts = split_output(ELIGIBILITY_MD)
    got = [(s.text, s.label, s.context) for s in stmts]
    elig = ("RFA Checklist", "ELIGIBILITY", "Eligible Individuals")
    assert got == [
        ("Principal Investigator", "", elig),
        ("Must be a full-time employee of the lead institution", "Criteria", elig + ("Principal Investigator",)),
        ("Co‑Principal Investigator", "", elig),
        ("Must be a full-time employee of the lead institution", "Criteria", elig + ("Co‑Principal Investigator",)),
        ("Post-fire perishable data collection", "", ("RFA Checklist", "ELIGIBILITY", "Eligible Individuals",
                                                       "Budget", "Unallowable Costs")),
        ("Plain paragraph after the list.", "", ("RFA Checklist", "ELIGIBILITY", "Eligible Individuals", "Budget")),
    ]


def test_the_same_words_under_two_headings_are_judged_apart():
    """Seen in the NSF run: "Criteria: Must be a full-time employee…" under
    the PI and under the co-PI were judged once, by their shared words and
    label, and both linked to the PI rule — the RFA says it of the PI only."""
    doc = _doc("rfa", "RFA.pdf", ["Who May Serve as PI: The PI must be a full-time employee of the lead institution.\n" + FILLER])
    judge = Judge(("full-time", "Who May Serve", "The PI must be a full-time employee of the lead institution."))
    _trace({"final": ELIGIBILITY_MD}, judge, docs=[doc])
    asked = [(it["statement"], it.get("context")) for it in judge.asked if "full-time" in it["statement"]]
    assert asked == [
        ("Must be a full-time employee of the lead institution",
         "RFA Checklist — ELIGIBILITY — Eligible Individuals — Principal Investigator"),
        ("Must be a full-time employee of the lead institution",
         "RFA Checklist — ELIGIBILITY — Eligible Individuals — Co‑Principal Investigator"),
    ]


def test_files_are_not_split():
    assert split_output({"type": "file_download", "filename": "x.pdf"}) == ("none", [])


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("statement, quote, same", [
    ("2022-07-13", "July 13, 2022", True),
    ("2025‑03‑14", "Date: 2025-03-14", True),            # non-breaking hyphens
    ("5:00 PM ET", "at 5:00pm ET", True),
    ("5:00 PM", "at 5:00 a.m.", False),
    ("$300K", "$300,000", True),
    ("17.5%", "17.5 percent", True),
    ("17.5%", "17.5", False),                                       # a rate is not a bare number
    ("2 CFR 200.405", "§ 200.405 Allocable costs", True),           # the title number is not a value
    ("L24AC00293-00", "GRANT NO. L24AC00293-00", True),
    ("L24AC00293-00", "GRANT NO. L24AC00293", False),
    ("Fall 2022", "by November 1, 2022", True),
    ("801-427-9603", "Phone: 801-427-9603", True),
    # A section number is a value: the NSF run's "(Section F.2)" was item 1
    # of Section II.F.
    ("insurance (Section F.2)", "The facility will be responsible for insurance", False),
    ("insurance (Section F.2)", "see Section F.2.", True),
    ("per GPG Section II.C.2.d.iii.", "GPG, Section II.C.2.d.iii.", True),
    ("subsection 2.A", "Include a subsection 2.A, with the heading", True),
    ("subsection 2.A", "Include a subsection 2.B", False),
])
def test_values_compare_as_the_same_value(statement, quote, same):
    want = {v.key for v in values_in(statement)}
    from app.services.output_sourcing import _quote_keys
    assert want and (want <= _quote_keys(values_in(quote))) is same


@pytest.mark.parametrize("text", [
    "5 p.m. ET", "U.S. citizens", "e.g. a budget", "Ph.D. students", "17.5% rate", "WBS level 3 (i.e., 1.2.3)",
    "www.nsf.gov/funding/nsf15-598", "No. 2 of the list", "§ 200.403(h)",
])
def test_abbreviations_and_plain_numbers_are_not_section_numbers(text):
    assert not [v for v in values_in(text) if v.kind == "id" and "." in v.raw]


# ---------------------------------------------------------------------------
# What gets linked
# ---------------------------------------------------------------------------

def test_a_supported_statement_links_to_the_page_the_engine_finds():
    judge = Judge(("Southern Utah", "Recipient:", "Recipient: Southern Utah University"))
    result = _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    [(row, src)] = _links(result, "final")
    assert row["p"] == ["recipient"]
    assert (src["kind"], src["document_uuid"], src["page"]) == ("document", "noa", 2)
    assert src["quote"] == "Recipient: Southern Utah University"
    assert src["excerpt"][src["quote_start"]:src["quote_end"]] == src["quote"]
    assert "page_approximate" not in src


def test_an_estimated_page_keeps_its_hedge():
    scanned = _doc("scan", "Scan.pdf", ["Cover page\n" + FILLER, "Recipient: Southern Utah University\n" + FILLER],
                   approximate=True)
    judge = Judge(("Southern Utah", "Recipient:", "Recipient: Southern Utah University"))
    result = _trace({"final": "The recipient is Southern Utah University."}, judge, docs=[scanned])
    [(_, src)] = _links(result, "final")
    assert (src["page"], src.get("page_approximate")) == (2, True)


@pytest.mark.parametrize("quote, reason", [
    ("Recipient is Southern Utah University", "quote_not_in_passage"),          # paraphrase
    ("Recipient: … Southern Utah University", "quote_not_in_passage"),          # spliced
    ("Recipient: ... Southern Utah University", "quote_not_in_passage"),
    ("Southern", "quote_too_short"),
    ("…Southern…", "quote_too_short"),
])
def test_an_excerpt_must_be_verbatim_and_contiguous(quote, reason):
    judge = Judge(("Southern Utah", "Recipient:", quote))
    result = _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    assert _links(result, "final") == []
    assert result["reasons"] == {reason: 1}


@pytest.mark.parametrize("quote", [
    "Recipient: Southern Utah University...",
    "…Recipient: Southern Utah University",
    "... Recipient: Southern Utah University …",
])
def test_an_ellipsis_at_either_end_only_says_the_passage_goes_on(quote):
    """Seen in the NSF run: "…up to three cross-Awardee activities..." —
    the words are the passage's, word for word; the dots are not."""
    judge = Judge(("Southern Utah", "Recipient:", quote))
    result = _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    [(_, src)] = _links(result, "final")
    assert src["quote"] == "Recipient: Southern Utah University"


def _window_with(corpus, needle):
    return next(i for i, _ in enumerate(corpus.windows) if needle in corpus.window_text(i))


def test_every_value_in_the_statement_must_be_in_the_excerpt():
    from app.services.output_statements import Statement

    corpus = Corpus([NOA], [])
    wi = _window_with(corpus, "Project period: 08/21/2024 through 09/20/2029.")
    st = Statement(0, 0, "08/21/2024 through 09/20/2029", label="period of performance")
    assert verify(st, corpus, wi, "Project period: 08/21/2024 through 09/20/2029.").link is not None
    assert verify(st, corpus, wi, "Project period: 08/21/2024 through").reason == "value_not_in_quote"
    # A statement with a value no passage holds is not even put to the judge.
    judge = Judge(("2023", "Project period", "Project period: 08/21/2024 through 09/20/2029"))
    result = _trace({"final": {"period_of_performance": "08/21/2024 through 09/20/2023"}}, judge)
    assert judge.asked == [] and _links(result, "final") == []


def test_the_award_total_is_not_certified_as_the_direct_costs():
    """The real trap: the form page lists TOTAL DIRECT COSTS, INDIRECT COSTS,
    TOTAL APPROVED BUDGET, then the figures. A judge that reads the block as
    "Total Direct Costs … 96,673.48" quotes text that holds both the label
    and the value — and the engine still refuses it: the label word is four
    lines and two other amounts away from the figure."""
    block = (" TOTAL DIRECT COSTS \nINDIRECT COSTS     \nTOTAL APPROVED BUDGET\nFederal Share \n"
             "82,275.30\n14,398.18\n96,673.48")
    judge = Judge(("96673.48", "TOTAL DIRECT", block), ("82275.3", "TOTAL DIRECT", block))
    wrong = {"approved_budget_categories": [{"category": "Total Direct Costs", "approved_amount": 96673.48}]}
    result = _trace({"final": wrong}, judge, docs=[NOA])
    assert _links(result, "final") == []
    assert result["reasons"].get("value_not_bound_to_label") == 1
    # The right figure from the same block is refused too: which figure goes
    # with which label cannot be read off that layout. No link beats a guess.
    right = {"approved_budget_categories": [{"category": "Total Direct Costs", "approved_amount": 82275.30}]}
    result = _trace({"final": right}, judge, docs=[NOA])
    assert _links(result, "final") == []


def test_a_label_beside_its_figure_is_linked():
    judge = Judge(("82275.3", "Budget summary", "Total Direct Costs: $82,275.30"))
    value = {"approved_budget_categories": [{"category": "Total Direct Costs", "approved_amount": 82275.30}]}
    [(_, src)] = _links(_trace({"final": value}, judge, docs=[NOA]), "final")
    assert (src["page"], src["quote"]) == (3, "Total Direct Costs: $82,275.30")


def test_formatting_marks_do_not_count_but_words_still_must_match():
    """Docling writes "**All grants require …** **funding request.**"; a
    judge copying the words drops or moves the marks. The words, their
    order and everything between them must still match."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "Budget\n- **All grants require matching contributions equal to or greater than the FFAR** "
        "**funding request.** Matching funds must come from a non-U.S. Federal entity.\n"
        "<u>P.I. and Key Personnel Biosketch</u>: three-page limit per individual listed as key personnel\n"
    )}
    judge = Judge(
        ("matching contributions", "All grants", "All grants require matching contributions equal to or greater than the FFAR funding request."),
        ("page limit", "Biosketch", "P.I. and Key Personnel Biosketch: three-page limit per individual"),
    )
    result = _trace({"final": {
        "cost_sharing": "All grants require matching contributions equal to or greater than the FFAR funding request.",
        "biosketch": "Three-page limit per individual",
    }}, judge, docs=[doc])
    quotes = [src["quote"] for _, src in _links(result, "final")]
    assert quotes == [
        "All grants require matching contributions equal to or greater than the FFAR** **funding request.",
        "P.I. and Key Personnel Biosketch</u>: three-page limit per individual",
    ]
    spliced = Judge(("matching contributions", "All grants", "All grants require matching contributions ... funding request."))
    result = _trace({"final": {"cost_sharing": "All grants require matching contributions."}}, spliced, docs=[doc])
    assert _links(result, "final") == []


def test_an_excerpt_must_say_most_of_a_longer_statement():
    """Seen in a real run: advice about matching-fund letters was linked to a
    component's bare name. The excerpt names the subject and nothing else."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "Required attachments\nMatching Fund Verification Letter(s)\nProject timeline (by year)\n"
    )}
    judge = Judge(("acquire letters", "Matching Fund", "Matching Fund Verification Letter(s)"))
    advice = "Obtain matching-fund verification letters before full submission"
    result = _trace({"final": {advice: "The budget component requires documented match evidence; acquire letters from partners early to avoid delays."}},
                    judge, docs=[doc])
    assert _links(result, "final") == []
    assert result["reasons"] == {"quote_covers_too_little": 1}


def test_a_value_does_not_carry_a_statement_the_excerpt_does_not_make():
    """Seen in a real run: a request for documentation of the award was
    linked to the expense record's award line because the award number
    matched. The value is there; the statement is not."""
    judge = Judge(("Documentation", "EXPENSE RECORD", "Award: L24AC00293-00 (BLM, Southern Utah University)"))
    result = _trace({"final": "Documentation confirming the purchase is authorized under award L24AC00293-00 "
                              "and a reasonable allocation method is still needed."}, judge, docs=[EXPENSE])
    assert _links(result, "final") == []
    assert result["reasons"] == {"quote_covers_too_little": 1}


@pytest.mark.parametrize("value, judge_rule, passages", [
    # The expense's currency, sourced to the award's "amounts are in USD".
    ({"source_document": "Expense Record", "currency": "USD"},
     ("USD", "ALL AMOUNTS", "ALL AMOUNTS ARE SHOWN IN USD"), []),
    # An award budget category, sourced to the expense record's own
    # category; the record's "Approved by" is not about a budget.
    ({"approved_budget_categories": [{"category": "Supplies"}]},
     ("Supplies", "Charged to", "Charged to: Supplies"), []),
    # An award budget category, sourced to a rule about trustees' travel.
    ({"approved_budget_categories": [{"category": "Travel"}]},
     ("Travel", "trustees", "Travel and subsistence costs of trustees (or directors) at IHEs are allowable."),
     [{"chunk_id": "e1", "label": "UG — Subpart E · part 30", "kb_title": "UG", "document_title": "Subpart E",
       "content": "§ 200.475 Travel costs. Travel and subsistence costs of trustees (or directors) at IHEs are allowable."}]),
])
def test_a_short_statement_needs_a_passage_about_what_its_label_names(value, judge_rule, passages):
    """Seen in a real run. "USD" or "Travel" alone matches many passages;
    the label says which record or list it belongs to, and the passage the
    judge read must be about that."""
    noa_usd = {"uuid": "noa", "title": "NoA.pdf", "text_markers": [],
               "raw_text": "NOTICE OF AWARD\nTotal Federal Share\nALL AMOUNTS ARE SHOWN IN USD\n"}
    expense = {**EXPENSE, "raw_text": EXPENSE["raw_text"] + "Charged to: Supplies\nApproved by: PI, 2025-03-16\n"}
    result = _trace({"final": value}, Judge(judge_rule), docs=[noa_usd, expense], passages=passages)
    assert _links(result, "final") == []
    assert result["reasons"].get("label_not_in_passage") == 1


CLAUSE = {"uuid": "noa2", "title": "NoA.pdf", "text_markers": [], "raw_text": (
    "Prohibition on Providing Funds to the Enemy.\n2. The recipient may include the substance of this clause "
    "in subawards that have an estimated value over $50,000 and will be performed outside the United States.\n"
)}
CLAUSE_QUOTE = ("The recipient may include the substance of this clause in subawards that have an estimated "
                "value over $50,000 and will be performed outside the United States.")


@pytest.mark.parametrize("statement, linked", [
    ("Subawards over $50,000 performed outside the United States may include this clause.", True),
    # Seen in a real run: the judge said this was stated.
    ("Subawards over $50,000 performed outside the United States must include this clause.", False),
])
def test_an_excerpt_must_ask_as_strongly_as_the_statement_says(statement, linked):
    result = _trace({"final": statement}, Judge(("Subawards", "may include", CLAUSE_QUOTE)), docs=[CLAUSE])
    assert bool(_links(result, "final")) is linked
    assert result["reasons"] == ({"ok": 1} if linked else {"obligation_differs": 1})


@pytest.mark.parametrize("statement, quote, differs", [
    ("must include this clause", "The recipient may include the substance of this clause", True),
    ("Press releases must be coordinated with NIH", "the grantee should notify NIH Communications in advance", True),
    ("Letters of support are optional", "Applicants must include letters of support", True),
    ("Funds may not be moved to other categories", "Funds may be moved to other categories", True),
    # As strong, in other words.
    ("Recipients must maintain SAM registration", "Recipients shall maintain current registration with SAM", False),
    ("Cost sharing is not required", "Applicants may offer cost sharing", False),
    # An excerpt that says both, or nothing either way, is the judge's call.
    ("must be approved by the Communications Director",
     "activities, which may include BLM funding, must be approved by the Communications Director", False),
    ("BLM approval required", "Review and approval by the BLM of modifications or subawards", False),
    # A cap written as leave is the same rule.
    ("Indirect costs must not exceed 10% of the award", "A maximum of 10% of the total award may be used for indirect costs.", False),
    # Not obligation words: the month, funds "obligated", a condition.
    ("The pre-application is required", "Full Application Invitation: May 11, 2022", False),
    ("Unspent funds may be carried forward", "Funds obligated but not expended may be carried forward", False),
    ("A UEI must be included", "Should a subaward be issued under this award, include the UEI.", False),
])
def test_obligation_words_compare_by_strength(statement, quote, differs):
    assert obligation_differs(statement, quote) is differs


# Every word of each statement below is in its excerpt, and in a real run the
# judge said each was stated. What is wrong is the role its label gives it.
AGREEMENT = _doc("agr", "Agreement.pdf", [
    "This cooperative agreement is made and entered into by the Bureau of Land Management (BLM), "
    "and Southern Utah University, the recipient, for the purpose of conducting surveys.\n" + FILLER,
])
UG_FACTORS = {
    "chunk_id": "e3", "label": "UG — Subpart E · part 3", "kb_title": "UG", "document_title": "Subpart E",
    "content": ("§ 200.403 Factors affecting allowability of costs.\n(d) Be accorded consistent treatment. "
                "A cost must not be assigned to a Federal award as a direct cost if any other cost incurred "
                "for the same purpose in like circumstances has been allocated as an indirect cost."),
}


@pytest.mark.parametrize("target, asked, rule, docs, passages", [
    # The university is the recipient, not a sponsor.
    ({"sponsor": "BLM, Southern Utah University"}, ("sponsor", "BLM, Southern Utah University"),
     ("Southern Utah", "Bureau of Land", "Bureau of Land Management (BLM), and Southern Utah University"),
     [AGREEMENT], []),
    # A heading names what an unlabelled list item is.
    ("## Sponsor\n\n- Bureau of Land Management\n", ("Sponsor", "Bureau of Land Management"),
     ("Bureau", "Bureau of Land", "Bureau of Land Management (BLM)"), [AGREEMENT], []),
])
def test_a_label_s_role_must_be_what_the_passage_gives_it(target, asked, rule, docs, passages):
    judge = Judge(rule, role=lambda item, n: False)
    result = _trace({"final": target}, judge, docs=docs, passages=passages)
    assert _links(result, "final") == []
    assert result["reasons"] == {"role_not_shown": 1}
    # Asked apart from the judge, more than once, with the excerpt and the
    # passage around it.
    assert len(judge.role_asked) == ROLE_VOTES
    for item in judge.role_asked:
        assert (item["label"], item["statement"]) == asked
        assert item["excerpt"] == rule[2] and rule[2] in item["passage"]


def test_the_role_check_reads_the_highlighted_excerpt_not_the_passage_around_it():
    """Seen in the NSF run: "Sponsor: National Science Foundation" was linked
    to the NSF's relay service for the hearing-impaired; the text around it
    says the NSF awards grants, and the check counted that."""
    assert "a role the passage gives elsewhere, outside the excerpt, does not count" in ROLE_INSTRUCTIONS
    assert "only describes the organization or person itself" in ROLE_INSTRUCTIONS
    # "The National Science Foundation (NSF) is an independent Federal
    # agency created by…" passed half the time without this; 0 of 10 with it.
    assert "the label names a party" in ROLE_INSTRUCTIONS


def test_a_check_s_name_is_not_a_statement_but_names_its_fields():
    """Seen in the NSF run: {"check": "Cost share / matching required",
    "status": "no", "detail": "…cost sharing is prohibited"} — the name,
    which says the opposite of the finding, was linked to a definition of
    mandatory cost share. The workflow named its check; no passage did."""
    value = [{"check": "Cost share / matching required", "category": "escalation", "status": "no",
              "detail": "Inclusion of voluntary committed cost sharing is prohibited"},
             {"check_name": "Consistent Cost Treatment", "result": "Pass"},
             {"item": "Letter of Intent", "source": "Announcement"}]
    _, stmts = split_output(value)
    assert [(s.text, s.label, s.kind) for s in stmts] == [
        ("escalation", "Cost share / matching required — category", "claim"),
        ("no", "Cost share / matching required — status", "verdict"),
        ("Inclusion of voluntary committed cost sharing is prohibited", "Cost share / matching required — detail", "claim"),
        ("Pass", "Consistent Cost Treatment — result", "verdict"),
        ("Letter of Intent", "item", "claim"),
    ]
    text = json.dumps({"risk_flags": value[:1]})
    assert [s.text for s in split_output(text)[1]] == [
        "escalation", "no", "Inclusion of voluntary committed cost sharing is prohibited",
    ]


def test_a_role_link_needs_every_check_to_say_yes():
    """The model says yes one time and no the next on a statement it finds
    arguable; one no refuses the link."""
    rule = ("Bureau", "Bureau of Land", "Bureau of Land Management (BLM)")
    result = _trace({"final": {"sponsor": "Bureau of Land Management"}}, Judge(rule), docs=[AGREEMENT])
    assert len(_links(result, "final")) == 1
    result = _trace({"final": {"sponsor": "Bureau of Land Management"}},
                    Judge(rule, role=lambda item, n: n == 0), docs=[AGREEMENT])
    assert _links(result, "final") == [] and result["reasons"] == {"role_not_shown": 1}


def test_only_a_short_statement_whose_label_says_what_it_is_gets_a_role_check():
    judge = Judge(
        ("The record shows", "Vendor:",
         "Vendor: Forestry Suppliers Inc.\nDate: 2025-03-14\nDescription: GPS receivers (2) for field plant surveys"),
        ("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."),
        ("GPS", "Description:", "Description: GPS receivers (2) for field plant surveys"),
    )
    result = _trace({
        # Its label names what it is: checked.
        "step:Read": {"vendor": "Forestry Suppliers Inc.",
                      # A slot word ("description") says nothing about its role.
                      "description": "GPS receivers (2) for field plant surveys",
                      # A sentence says what it means itself.
                      "rationale": "The record shows GPS receivers for field plant surveys bought from Forestry Suppliers Inc."},
        # No label at all.
        "final": "Bought from Forestry Suppliers Inc.",
    }, judge, docs=[EXPENSE])
    assert len(_links(result, "step:Read")) == 3 and len(_links(result, "final")) == 1
    assert {item["statement"] for item in judge.role_asked} == {"Forestry Suppliers Inc."}


def test_an_excerpt_needs_a_word_in_common_with_the_statement():
    # "vendor total" finds the record (it says "Vendor"), but the excerpt
    # the judge picked shares no word with the statement or its label.
    judge = Judge(("1240", "Amount:", "Amount: $1,240.00"))
    result = _trace({"final": {"vendor_total": 1240.0}}, judge, docs=[EXPENSE])
    assert _links(result, "final") == []
    assert result["reasons"] == {"no_shared_word": 1}


def test_a_short_quote_found_on_many_pages_links_to_the_passage_the_judge_read():
    """"Bureau of Land Management" is on pages 1, 2 and 3. The link goes to
    the passage the judge was shown and named, not to the first place the
    words occur."""
    judge = Judge(("Bureau of Land Management", "administered by", "administered by the Bureau of Land Management"))
    result = _trace({"final": "The agreement is administered by the Bureau of Land Management."}, judge, docs=[NOA])
    [(_, src)] = _links(result, "final")
    assert src["page"] == 2


def test_an_excerpt_that_occurs_on_two_pages_of_one_passage_is_refused():
    page_end = "Program contact: Bureau of Land Management\n"
    doc = _doc("two", "Two.pdf", ["Intro.\n" + page_end, page_end + "More text.\n"])
    judge = Judge(("Bureau", "Program contact", "Program contact: Bureau of Land Management"))
    result = _trace({"final": {"program_contact": "Bureau of Land Management"}}, judge, docs=[doc])
    assert _links(result, "final") == []
    assert result["reasons"] == {"quote_on_several_pages": 1}


def test_a_value_in_two_documents_links_to_the_one_the_judge_read():
    """The award number is in the Notice of Award and in the expense record.
    A statement about the expense record links to the record."""
    judge = Judge(("expense record", "EXPENSE RECORD", "Award: L24AC00293-00 (BLM, Southern Utah University)"))
    result = _trace({"final": "The expense record charges the purchase to award L24AC00293-00."}, judge)
    [(_, src)] = _links(result, "final")
    assert (src["document_uuid"], src["page"]) == ("exp", None)


def test_an_excerpt_from_another_offered_passage_is_checked_where_it_is():
    """Seen in the NSF run, seven times: the judge names one of a
    statement's passages and copies the excerpt, word for word, from
    another it was offered. The excerpt is checked in full where it is."""
    judge = Judge(("expense record", "NOTICE OF AWARD", "Award: L24AC00293-00 (BLM, Southern Utah University)"))
    result = _trace({"final": "The expense record charges the purchase to award L24AC00293-00."}, judge)
    [(_, src)] = _links(result, "final")
    assert (src["document_uuid"], src["quote"]) == ("exp", "Award: L24AC00293-00 (BLM, Southern Utah University)")
    # Still every check: there, the excerpt has no word of the statement.
    judge = Judge(("purchase", "NOTICE OF AWARD", "Vendor: Forestry Suppliers Inc."))
    result = _trace({"final": "The purchase was approved under award L24AC00293-00."}, judge)
    assert _links(result, "final") == []


def test_an_excerpt_in_two_offered_passages_and_not_the_one_named_is_refused():
    page = "Recipient: Southern Utah University\n" + FILLER
    doc = _doc("rep", "Repeated.pdf", [page, page, "Unrelated recipient text.\n" + FILLER])
    corpus = Corpus([doc], [])
    from app.services.output_sourcing import verify_offered
    from app.services.output_statements import Statement

    st = Statement(0, 0, "Southern Utah University", label="recipient")
    windows = [i for i, _ in enumerate(corpus.windows) if "Recipient: Southern" in corpus.window_text(i)]
    other = next(i for i, _ in enumerate(corpus.windows) if "Unrelated recipient" in corpus.window_text(i))
    assert len({corpus.windows[i].start for i in windows}) >= 2
    v = verify_offered(st, corpus, other, [other, *windows], "Recipient: Southern Utah University")
    assert (v.link, v.reason) == (None, "quote_not_in_passage")


def test_a_statement_copied_word_for_word_links_only_to_where_it_was_copied_from():
    """Seen in the NSF run: "A facility with any resources that can only be
    accessed or used outside the United States" is the RAPID list's, word
    for word, on p. 21; the judge linked another component's list on p. 28,
    which says "equipment"."""
    doc = _doc("nheri", "NHERI.pdf", [
        "RAPID will not support: A facility with any resources that can only be accessed or used outside the "
        "United States.\n" + FILLER,
        "EF will not support: A facility with any equipment that can only be accessed or used outside the "
        "United States.\n" + FILLER,
    ])
    statement = "A facility with any resources that can only be accessed or used outside the United States"
    wrong = Judge(("facility", "EF will not", "A facility with any equipment that can only be accessed or used outside the United States"))
    result = _trace({"final": {"unallowable_costs": [statement]}}, wrong, docs=[doc])
    assert _links(result, "final") == [] and result["reasons"] == {"statement_is_elsewhere": 1}
    right = Judge(("facility", "RAPID will not", statement))
    [(_, src)] = _links(_trace({"final": {"unallowable_costs": [statement]}}, right, docs=[doc]), "final")
    assert src["page"] == 1


def test_a_passage_the_statement_was_not_offered_is_refused():
    judge = Judge(("Southern Utah", "@P999", "Recipient: Southern Utah University"))
    result = _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    assert _links(result, "final") == []
    assert result["reasons"] == {"judge_named_no_passage": 1}


def test_a_knowledge_base_passage_is_a_source_too():
    judge = Judge(("prudent person", "§ 200.404", "it does not exceed that which would be incurred by a prudent person"))
    result = _trace(
        {"final": "A reasonable cost does not exceed what a prudent person would incur."},
        judge, docs=[], passages=[KB_PASSAGE],
    )
    [(_, src)] = _links(result, "final")
    assert (src["kind"], src["chunk_id"], src["kb_title"]) == ("kb", "ug_e_10", "OMB Uniform Guidance")
    assert src["excerpt"][src["quote_start"]:src["quote_end"]] == src["quote"]


PROCUREMENT = {
    "chunk_id": "ug_d_320", "kb_title": "OMB Uniform Guidance", "document_title": "Subpart D",
    "label": "OMB Uniform Guidance — Subpart D · part 41", "page": None,
    "content": ("§ 200.320 Procurement methods.\n(a)(2) Small purchase procedures. If simplified acquisition "
                "procedures are used, price or rate quotations must be obtained from an adequate number of "
                "qualified sources.\n"),
}


def test_advice_is_not_sourced_to_a_rule_that_applies_only_in_some_cases():
    """Seen in a real run: "Obtain vendor quotations…" for a $1,240 purchase
    was linked to the small-purchase rule, which applies only if simplified
    acquisition procedures are used — implying a requirement this purchase,
    under the micro-purchase threshold, does not have. The judge quoted the
    main clause; the condition sits in the rest of the sentence."""
    judge = Judge(("vendor quotations", "Small purchase",
                   "price or rate quotations must be obtained from an adequate number of qualified sources."))
    result = _trace({"final": "Obtain vendor quotations or comparable market price evidence for the GPS receivers."},
                    judge, docs=[], passages=[PROCUREMENT])
    assert _links(result, "final") == []
    assert result["reasons"] == {"rule_applies_only_if": 1}


def test_advice_that_states_the_rule_s_condition_may_cite_it():
    judge = Judge(("simplified acquisition", "Small purchase",
                   "If simplified acquisition procedures are used, price or rate quotations must be obtained "
                   "from an adequate number of qualified sources."))
    value = {"follow_up_actions": [
        "If simplified acquisition procedures are used, obtain price or rate quotations from qualified sources.",
    ]}
    [(_, src)] = _links(_trace({"final": value}, judge, docs=[], passages=[PROCUREMENT]), "final")
    assert src["chunk_id"] == "ug_d_320"


def test_advice_from_the_document_itself_is_still_sourced():
    """An announcement's own instructions apply to its applicants: no
    condition stands between them and the case."""
    rfa = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "Submission\nOnly applications submitted by the deadline through FFAR's Grant Management System "
        "will be accepted and considered eligible for evaluation.\n"
    )}
    judge = Judge(("Submit", "Grant Management", "Only applications submitted by the deadline through FFAR's "
                   "Grant Management System will be accepted"))
    result = _trace({"final": {"submission_details": "Submit applications through FFAR's Grant Management System by the deadline."}},
                    judge, docs=[rfa])
    assert len(_links(result, "final")) == 1


def test_a_transaction_date_is_not_an_action():
    from app.services.output_sourcing import is_action
    from app.services.output_statements import Statement

    assert not is_action(Statement(0, 0, "2025-03-14", label="Expense Record — transaction date"))
    assert is_action(Statement(0, 0, "Vendor quotes", label="Cost Reasonableness — follow up actions"))
    assert is_action(Statement(0, 0, "Obtain itemized invoices.", label=""))


def test_absences_and_verdicts_are_never_judged():
    judge = Judge()
    result = _trace({"final": "**Funding Instrument:** Not specified in the document\n**Decision:** Allowable\n"}, judge)
    assert judge.asked == []
    rows = result["targets"]["final"]["statements"]
    assert [r.get("t") for r in rows] == ["absent", "verdict"]
    assert result["targets"]["final"]["summary"] == {"statements": 2, "traced": 0}


# ---------------------------------------------------------------------------
# Failing closed
# ---------------------------------------------------------------------------

def test_a_judge_that_fails_links_nothing():
    result = _trace({"final": {"recipient": "Southern Utah University"}}, Judge(raises=RuntimeError("timeout")))
    assert result["status"] == "done"
    assert _links(result, "final") == []
    assert result["errors"] == 1


@pytest.mark.parametrize("reply", ["not json", '{"items": [{"id": 1, "supported": "yes", "passage": "P1", "quote": "x"}]}'])
def test_a_judge_reply_that_makes_no_sense_links_nothing(reply):
    result = _trace({"final": {"recipient": "Southern Utah University"}}, Judge(reply=reply))
    assert _links(result, "final") == []


def test_statements_past_the_budget_are_left_unchecked():
    judge = Judge(("Southern Utah", "Recipient:", "Recipient: Southern Utah University"))
    result = trace_sources(
        {"final": {"recipient": "Southern Utah University", "vendor": "Forestry Suppliers Inc."}},
        [NOA, EXPENSE], [], ask=judge, workers=1, max_judged=1,
    )
    assert result["judged"] == 1 and result["unchecked"] == 1


def test_a_deadline_that_has_passed_checks_nothing():
    judge = Judge(("Southern Utah", "Recipient:", "Recipient: Southern Utah University"))
    result = trace_sources(
        {"final": {"recipient": "Southern Utah University"}}, [NOA], [], ask=judge,
        workers=1, deadline=0.0, clock=lambda: 10.0,
    )
    assert _links(result, "final") == [] and result["unchecked"] >= 1


def test_a_role_check_that_fails_links_nothing():
    judge = Judge(("Southern Utah", "Recipient:", "Recipient: Southern Utah University"),
                  role_raises=RuntimeError("timeout"))
    result = _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    assert _links(result, "final") == []
    assert result["reasons"] == {"role_unchecked": 1}
    assert result["errors"] == ROLE_VOTES and result["unchecked"] == 1


def test_a_deadline_that_passes_before_the_role_check_links_nothing():
    judge = Judge(("Southern Utah", "Recipient:", "Recipient: Southern Utah University"))
    times = iter([0.0, 0.0])   # the judge starts in time; the role check does not
    result = trace_sources(
        {"final": {"recipient": "Southern Utah University"}}, [NOA], [], ask=judge,
        workers=1, deadline=5.0, clock=lambda: next(times, 10.0),
    )
    assert judge.asked and not judge.role_asked
    assert _links(result, "final") == []
    assert result["reasons"] == {"role_unchecked": 1} and result["unchecked"] == 1


# ---------------------------------------------------------------------------
# Read-only
# ---------------------------------------------------------------------------

def test_sourcing_never_changes_the_outputs_it_reads():
    targets = {
        "final": MARKDOWN,
        "step:Normalize": [json.dumps({"vendor": "Forestry Suppliers Inc."}), {"rate": "17.5%"}],
        "step:Check": {"recipient": "Southern Utah University", "amount": 1240.0},
    }
    before = json.dumps(targets, sort_keys=True)
    snapshot = copy.deepcopy(targets)
    judge = Judge(("Southern Utah", "Recipient:", "Recipient: Southern Utah University"),
                  ("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."))
    result = _trace(targets, judge)
    assert targets == snapshot and json.dumps(targets, sort_keys=True) == before
    assert len(_links(result, "step:Check")) == 1 and len(_links(result, "step:Normalize")) == 1


def test_candidates_need_every_value_and_a_shared_word():
    corpus = Corpus([NOA, EXPENSE], [])
    from app.services.output_statements import Statement
    st = Statement(0, 0, "L24AC00293-00", label="award number")
    picked = {corpus.sources[corpus.windows[w].src].meta["uuid"] for w in corpus.candidates(st)}
    assert picked == {"noa", "exp"}
    assert corpus.candidates(Statement(0, 0, "99,999.99", label="award total")) == []
    assert "cost" in stems("Costs") and "requir" in stems("required") and stems("require") == {"requir"}


def test_verify_reports_why_a_link_was_refused():
    corpus = Corpus([EXPENSE], [])
    from app.services.output_statements import Statement
    st = Statement(0, 0, "1240.00", label="amount")
    assert verify(st, corpus, 0, "Amount: $1,240.00").link is not None
    assert verify(st, corpus, 0, "Amount: $1,240.00 extra").reason == "quote_not_in_passage"
