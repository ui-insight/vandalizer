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
    CONFIRM_INSTRUCTIONS,
    RETRY_NOTE,
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

    def __init__(self, *rules, raises=None, reply=None, role=None, role_raises=None, confirm=None, retry_rules=None):
        self.rules = rules
        self.raises = raises
        self.reply = reply
        self.role = role or (lambda item, n: True)
        self.role_raises = role_raises
        self.confirm = confirm or (lambda item: True)
        # What the judge answers on a second look; by default what it said the first time.
        self.retry_rules = rules if retry_rules is None else retry_rules
        self.asked: list[dict] = []
        self.retried: list[dict] = []
        self.role_asked: list[dict] = []
        self.confirm_asked: list[dict] = []

    def __call__(self, instructions, prompt):
        if self.raises:
            raise self.raises
        if self.reply is not None:
            return self.reply
        items = [json.loads(line) for line in prompt.split("STATEMENTS", 1)[1].splitlines() if line.strip()]
        if instructions == CONFIRM_INSTRUCTIONS:
            self.confirm_asked.extend(items)
            return json.dumps({"items": [{"id": it["id"], "stated": self.confirm(it)} for it in items]})
        if instructions == ROLE_INSTRUCTIONS:
            if self.role_raises:
                raise self.role_raises
            out = []
            for it in items:
                out.append({"id": it["id"], "passage_says": "", "shown": self.role(it, len(self.role_asked))})
                self.role_asked.append(it)
            return json.dumps({"items": out})
        passages = dict(_PASSAGE_RE.findall(prompt))
        retry = instructions.endswith(RETRY_NOTE)
        for it in items:
            it["offered"] = [passages[p] for p in it["passages"]]
        (self.retried if retry else self.asked).extend(items)
        out = []
        for it in items:
            answer = {"id": it["id"], "supported": False}
            for needle, where, quote in (self.retry_rules if retry else self.rules):
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
    # A pointer to another part of the report is not a statement either.
    md = "| Component | Special Requirements |\n|---|---|\n| Project Description | **See required structure below.** |\n"
    assert split_output(md)[1] == []


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


def test_a_statement_that_strings_facts_together_is_checked_one_clause_at_a_time():
    """Seen in the NSF run: "PI must be a full‑time employee of the lead
    institution; each individual receiving support must be funded for at
    least one month per year; …" — every fact is in the RFA, on different
    pages; no one excerpt states them all, so none was linked."""
    md = ("- **Personnel Effort:** PI must be a full-time employee; each individual must be funded for at least "
          "one month per year; postdoctoral researchers (U.S. citizens; nationals) may be funded only on the "
          "SimCenter award.\n"
          "- **Unallowable Costs:** Budget; Travel\n")
    _, stmts = split_output(md)
    assert [(md[s.start:s.end], s.text, s.label) for s in stmts] == [
        ("PI must be a full-time employee", "PI must be a full-time employee", "Personnel Effort"),
        ("each individual must be funded for at least one month per year",
         "each individual must be funded for at least one month per year", "Personnel Effort"),
        # A semicolon inside brackets is part of the clause.
        ("postdoctoral researchers (U.S. citizens; nationals) may be funded only on the SimCenter award.",
         "postdoctoral researchers (U.S. citizens; nationals) may be funded only on the SimCenter award.",
         "Personnel Effort"),
        # A piece of one word: a list, not facts strung together.
        ("Budget; Travel", "Budget; Travel", "Unallowable Costs"),
    ]
    # JSON values too, as written and as a structured value.
    detail = "Maximum 2 proposals per institution; only one per each of NCO, SimCenter, RAPID categories"
    text = json.dumps({"risk_flags": [{"check": "Limited submission", "detail": detail}]})
    assert [text[s.start:s.end] for s in split_output(text)[1]] == [
        "Maximum 2 proposals per institution", "only one per each of NCO, SimCenter, RAPID categories",
    ]
    value = [{"check": "Limited submission", "detail": detail}]
    got = [(s.path, value[0]["detail"][s.start:s.end]) for s in split_output(value)[1]]
    assert got == [([0, "detail"], "Maximum 2 proposals per institution"),
                   ([0, "detail"], "only one per each of NCO, SimCenter, RAPID categories")]


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


def test_an_excerpt_cut_with_an_ellipsis_is_checked_piece_by_piece_and_confirmed_whole():
    """Seen in the NSF NHERI run, on seven of its section summaries: "Each
    Awardee will operate with a Science Plan that supports the NHERI vision
    ... The Science Plan should outline: …" — what the report condensed
    runs over several sentences, and the judge cut the excerpt to fit. Each
    piece must be the passage's, word for word and in order; the highlight
    covers the whole stretch, and a separate call must confirm it states
    the statement."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "Budget\n- **All grants require matching contributions equal to or greater than the FFAR** "
        "**funding request.** Matching funds must come from a non-U.S. Federal entity.\n"
    )}
    cut = "All grants require matching contributions ... funding request."
    statement = {"cost_sharing": "All grants require matching contributions."}
    judge = Judge(("matching contributions", "All grants", cut))
    [(_, src)] = _links(_trace({"final": statement}, judge, docs=[doc]), "final")
    assert src["quote"] == "All grants require matching contributions equal to or greater than the FFAR** **funding request."
    assert [it["excerpt"] for it in judge.confirm_asked] == [src["quote"]]
    assert "pieced" not in src and "judge_quote" not in src
    refused = Judge(("matching contributions", "All grants", cut), confirm=lambda item: False)
    result = _trace({"final": statement}, refused, docs=[doc])
    assert _links(result, "final") == [] and result["reasons"] == {"not_confirmed": 1}
    # Pieces out of order, or a piece of one word, are not the passage's.
    for bad in ("funding request ... All grants require matching contributions",
                "All grants require matching contributions ... request."):
        result = _trace({"final": statement}, Judge(("matching contributions", "All grants", bad)), docs=[doc])
        assert _links(result, "final") == [] and result["reasons"] == {"quote_not_in_passage": 1}


def test_an_excerpt_must_say_most_of_a_longer_statement():
    """Seen in a real run: advice about matching-fund letters was linked to a
    component's bare name. The excerpt names the subject and nothing else."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "Required attachments\nMatching Fund Verification Letter(s)\nProject timeline (by year)\n"
    )}
    judge = Judge(("acquire letters", "Matching Fund", "Matching Fund Verification Letter(s)"))
    advice = "Obtain matching-fund verification letters before full submission"
    result = _trace({"final": {advice: "The budget component requires documented match evidence, so acquire letters from partners early to avoid delays."}},
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


NHERI_ELIG = _doc("nheri2", "NHERI.pdf", [
    "Who May Serve as PI:\n\nThe PI must be a full-time employee of the lead institution by the start date of the "
    "NSF cooperative agreement award.\n\nAn individual may appear as PI or co-PI in no more than one proposal.\n" + FILLER,
])


def test_a_rule_for_the_pi_does_not_source_the_co_investigator_s_criterion():
    """Seen in a fresh NSF NHERI run: "Criteria: Must be a full-time employee
    of the lead institution…" under the co-investigator was linked to "The PI
    must be a full-time employee…" — the RFA says it of the PI alone. Its
    context named the co-investigator; the judge linked it anyway."""
    md = ("### Eligible Individuals\n\n"
          "- **Principal Investigator**\n  - Criteria: Must be a full-time employee of the lead institution\n"
          "- **Co‑Investigator**\n  - Criteria: Must be a full-time employee of the lead institution\n"
          "  - Conditions: May appear as PI or co-PI in no more than one proposal\n")
    judge = Judge(("full-time", "Who May Serve", "The PI must be a full-time employee of the lead institution"),
                  ("appear as", "no more than one", "An individual may appear as PI or co-PI in no more than one proposal."))
    result = _trace({"final": md}, judge, docs=[NHERI_ELIG])
    linked = [md[r["s"]:r["e"]] for r, _ in _links(result, "final")]
    assert linked.count("Must be a full-time employee of the lead institution") == 1   # the PI's only
    assert "May appear as PI or co-PI in no more than one proposal" in linked          # names both
    assert result["reasons"]["subject_differs"] == 1
    rows = result["targets"]["final"]["statements"]
    under_co = [r for r in rows if md[r["s"]:r["e"]].startswith("Must be")][1]
    assert "src" not in under_co


@pytest.mark.parametrize("sentence, linked", [
    ("The Foundation for Food & Agriculture Research (FFAR) announces the 2022 Seeding Solutions program.", True),
    ("This cooperative agreement is made and entered into by the Bureau of Land Management and the recipient.", True),
    ("The National Science Foundation (NSF) is an independent Federal agency created by the National Science "
     "Foundation Act of 1950.", False),
    ("The National Science Foundation has Telephonic Device for the Deaf (TDD) capabilities about NSF programs.", False),
])
def test_a_sponsor_needs_a_sentence_that_ties_it_to_this_opportunity(sentence, linked):
    """Seen on every NSF solicitation: "Sponsor: National Science Foundation"
    linked to the agency's description of itself."""
    from app.services.output_statements import Statement
    from app.services.output_sourcing import party_unbound

    assert party_unbound(Statement(0, 0, "x", label="Sponsor"), sentence) is not linked
    assert party_unbound(Statement(0, 0, "x", label="sponsor name"), sentence) is not linked
    # Only a sponsor's or funder's label asks it.
    assert party_unbound(Statement(0, 0, "x", label="Recipient"), sentence) is False


# The NSF NHERI solicitation: the proposal's required documents in one
# list (p. 2), and a facility's duty that uses the same words (p. 1).
NHERI_PARTS = _doc("nheri3", "NHERI.pdf", [
    "*Data Management Infrastructure:* Implement a facility data management plan*,* which meets the CI Awardee "
    "requirements for data and metadata protocols and formats, archiving, curating, and retrieval.\n" + FILLER,
    "The GPG requires submission of: Project Summary; Project Description; References Cited; Budget; Budget "
    "Justification; Current and Pending Support; Data Management Plan; and Postdoctoral Mentoring Plan, if "
    "applicable.\n" + FILLER,
    "**Budget Preparation Instructions:**\n\nIn the budget justification, provide a list of all organizations that "
    "will receive less than $50,000 annually and the annual support provided to each organization.\n" + FILLER,
])
PARTS_TABLE = (
    "## APPLICATION COMPONENTS\n\n| Component | Description / Details |\n|---|---|\n"
    "| Data Management Plan | Data Management Plan |\n"
    "| Subaward Documents (if applicable) | Budget Justification; Specific Scope of Work |\n"
)


def test_a_part_of_a_submission_links_only_where_the_passage_gives_it_as_one():
    """Seen in the NSF NHERI run: "Data Management Plan", a required
    component, was linked to a facility's duty to "Implement a facility data
    management plan"; "Budget Justification", one of a subaward's documents,
    to "In the budget justification, provide a list of all organizations…".
    A name in the report's list of parts links where the passage lists it,
    heads a section with it, or asks for it. A refusal earns a second look,
    never at the refused passage — here it finds the list."""
    judge = Judge(
        ("Data Management Plan", "Implement a facility",
         "Implement a facility data management plan, which meets the CI Awardee requirements"),
        ("Budget Justification", "In the budget justification",
         "In the budget justification, provide a list of all organizations"),
        retry_rules=(
            ("Data Management Plan", "GPG requires", "Current and Pending Support; Data Management Plan; and Postdoctoral"),
            ("Budget Justification", "GPG requires", "Budget; Budget Justification; Current and Pending Support"),
        ),
    )
    result = _trace({"final": PARTS_TABLE}, judge, docs=[NHERI_PARTS])
    linked = {PARTS_TABLE[r["s"]:r["e"]]: src for r, src in _links(result, "final")}
    # The component, on its second look, from the list.
    assert linked["Data Management Plan"]["page"] == 2
    assert not any("Implement a facility" in p for it in judge.retried for p in it["offered"])
    # The subaward's document: the list is the proposal's, not a subaward's.
    assert "Budget Justification" not in linked
    assert result["reasons"].get("label_not_in_passage") == 1


@pytest.mark.parametrize("part, passage, presented", [
    ("Data Management Plan",
     "The GPG requires submission of: Project Summary; Budget; Data Management Plan; and Postdoctoral Mentoring Plan.", True),
    ("Facilities, Equipment & Other Resources", "…Supplementary Documentation sections. **FACILITIES, EQUIPMENT, AND "
     "OTHER RESOURCES** In this section of the proposal, include the descriptions below.", True),
    ("Budget Justification", "**2. Budget and Budget Justification.** Provide standard yearly budgets.", True),
    ("Data Management Plan", "- Data Management Plan", True),
    ("Budget Form", "(*up to 5000 words)* o <u>Budget Form</u> o <u>P.I. and Key Personnel Biosketch</u>: three-page limit", True),
    ("P.I. and Key Personnel Biosketch", "o <u>Budget Form</u> o <u>P.I. and Key Personnel Biosketch</u>: three-page limit", True),
    ("Mentoring Plan", "Data Management Plan; and Postdoctoral Mentoring Plan, if applicable.", True),
    ("Project Personnel and Partner Institutions",
     "*1. (required) A list of Project Personnel and Partner Institutions (required. Note: …):*", True),
    ("Broadening Participation in Computing (BPC) Plan",
     "*5. Broadening Participation in Computing (BPC) Plans for projects with budgets greater than $600,000:*", True),
    ("Data Management Plan", "The full proposal must include a data management plan for each of the five years.", True),
    ("Data Management Plan", "A Data Management Plan (DMP) is required for all proposals.", True),
    ("Data Management Plan", "In the Data Management Plan section, describe how data will be shared.", True),
    ("Data Management Plan",
     "*Data Management Infrastructure:* Implement a facility data management plan*,* which meets the CI requirements.", False),
    ("Data Management Plan", "Reviewers will read the data management plan as part of intellectual merit.", False),
    ("Data Management Plan", "Data management plan costs are allowable.", False),
    ("Principal Investigator", "Any individual with the skills necessary may apply as Program "
     "Director(s)/Principal Investigator(s) through their home institution.", True),
    ("Co-Principal Investigator", "Eligible individuals: Co-Principal Investigators; Senior Personnel.", True),
    # The subject of a sentence about something else.
    ("Principal Investigator", "Pre-award costs. Principal Investigator or organization that makes financial "
     "commitments in the absence of a grant does so at their own risk.", False),
    ("Budget", "**The budget request must be commensurate with the** **complexity of the project.**", False),
    ("Mentoring Plan", "reviewers will also review the Data Management and Sharing Plan and the Mentoring Plan, as appropriate.", False),
])
def test_how_a_passage_gives_a_part_of_a_submission(part, passage, presented):
    from app.services.output_sourcing import item_name, presented_as_item
    from app.services.output_statements import Statement

    name = item_name(Statement(0, 0, part, label="required components — name"))
    assert name and presented_as_item(name, passage, 0, len(passage)) is presented


def test_only_a_bare_name_in_a_list_of_parts_is_a_part():
    from app.services.output_sourcing import item_name
    from app.services.output_statements import Statement

    def name(text, label, context=()):
        return item_name(Statement(0, 0, text, label=label, context=context))

    assert name("Data Management Plan", "Data Management Plan — Description / Details", ("APPLICATION COMPONENTS",))
    assert name("Budget Justification", "required components — name")
    assert name("Facilities/Equipment if applicable", "Subaward Documents (if applicable) — Description / Details")
    # Who may take part is a list of names too.
    assert name("Principal Investigator", "", ("ELIGIBILITY", "Eligible Individuals"))
    # A sentence, a description, a value, or a list that is not of parts.
    assert not name("Proposals may be submitted via Research.gov", "SUBMISSION DETAILS — required components")
    assert not name("Biographical Sketch(es) following NSF GPG format", "required components — description")
    assert not name("Form 1 (two pages)", "required components — name")
    assert not name("Bureau of Land Management", "Sponsor")


def test_values_under_one_label_are_bound_to_it():
    """Seen on the NSF solicitations. Docling writes the label, a blank line,
    then the values; a range's start sits between its end and its label;
    one submission window per line sits under one heading; and a list of
    CFDA numbers runs down the page under "Number(s):"."""
    from app.services.output_sourcing import _bound, values_in

    def bound(statement, label, quote):
        shared = (stems(statement) | stems(label)) & stems(quote)
        return _bound(values_in(statement), shared, quote, values_in(quote))

    cfda = "**Applicable Catalog of Federal Domestic Assistance (CFDA) Number(s):**\n\n47.041 --- Engineering"
    assert bound("47.041", "CFDA Number", cfda)
    window = "Submission Window Date(s) (due by 5 p.m. submitter's local time): January 16, 2023 - February 21, 2023"
    assert bound("2023-02-21", "Submission Window End — Date / Time", window)
    windows = ("Submission Window Date(s) (due by 5 p.m. submitter's local time):\n\n"
               "January 16, 2023 - February 21, 2023\n\nOctober 16, 2023 - November 15, 2023\n\n"
               "October 15, 2024 - November 15, 2024")
    assert bound("2024-10-15", "Submission Window Start — Date / Time", windows)
    # The MRI solicitation writes them on one line.
    assert bound("2024-10-15", "Submission Window Start — Date / Time", windows.replace("\n\n", " "))
    many = cfda + "\n47.049 --- Mathematical and Physical Sciences\n47.050 --- Geosciences"
    assert bound("47.041, 47.049, 47.050", "CFDA Number", many)
    # Still refused: labels in one block and figures in another…
    form = " TOTAL DIRECT COSTS \nINDIRECT COSTS     \nTOTAL APPROVED BUDGET\nFederal Share \n82,275.30\n14,398.18\n96,673.48"
    assert not bound("96,673.48", "Total Direct Costs", form)
    # …a list under a heading of one thing, and a figure the statement does not name.
    assert not bound("2024-10-15", "Submission Window Start — Date / Time", windows.replace("Date(s)", "Date"))
    assert not bound("47.050", "CFDA Number", many)


def test_bare_figures_are_read_with_the_label_line_above_them():
    """Seen in three NSF solicitations: the judge copied "47.041 ---
    Engineering…" and not "Applicable Catalog of Federal Domestic
    Assistance (CFDA) Number(s):" above it — no word of the label, so no
    link. The label line above figures copied alone is read with them."""
    doc = {"uuid": "nsf", "title": "nsf14579.pdf", "text_markers": [], "raw_text": (
        "Cognizant Program Officer(s): see the program page.\n\n"
        "**Applicable Catalog of Federal Domestic Assistance (CFDA) Number(s):**\n\n"
        "47.041 --- Engineering\n47.049 --- Mathematical and Physical Sciences\n\n**Award Information**\n"
    )}
    judge = Judge(("47.041", "47.041", "47.041 --- Engineering\n47.049 --- Mathematical and Physical Sciences"))
    result = _trace({"final": "**CFDA Number:** 47.041, 47.049\n"}, judge, docs=[doc])
    [(_, src)] = _links(result, "final")
    assert src["quote"].startswith("**Applicable Catalog of Federal Domestic Assistance (CFDA) Number(s):**")
    # Not for a statement that says more than a figure.
    judge = Judge(("Engineering", "47.041", "47.041 --- Engineering"))
    result = _trace({"final": "The CFDA number for the engineering directorate is 47.041 and it covers design."}, judge, docs=[doc])
    assert _links(result, "final") == []


def test_a_pointer_glued_onto_a_cell_is_not_part_of_its_statement():
    """Seen in the SaTC run: the checklist appends "**See required structure
    below.**" to a component's requirements with no period between, so
    the page limit could never be traced."""
    md = ("| Component | Special Requirements |\n|---|---|\n"
          "| Project Description | Page limit: 15 pages (RES/EDU), 10 pages (SEED) **See required structure below.** |\n")
    _, stmts = split_output(md)
    assert [(s.text, md[s.start:s.end]) for s in stmts] == [
        ("Page limit: 15 pages (RES/EDU), 10 pages (SEED)", "Page limit: 15 pages (RES/EDU), 10 pages (SEED)"),
    ]


@pytest.mark.parametrize("text, keys", [
    ("up to five pages", ["num:5"]),
    ("maximum of two proposals", ["num:2"]),
    ("twenty-five percent", ["num:25"]),
    ("Two-page biographical sketches", ["num:2"]),
    ("no longer than a single page", ["num:1"]),
    ("someone often", []),
])
def test_a_number_written_as_a_word_is_its_figure(text, keys):
    assert [v.key for v in values_in(text) if v.kind == "num"] == keys


def test_a_figure_the_excerpt_writes_in_words_needs_no_digits():
    """Seen in the SaTC solicitation: "Required if budget >$600,000 and >1 PI"
    against "required for all projects with more than one PI and a budget of
    more than $600,000" — the same values; the digit check had refused it."""
    from app.services.output_sourcing import _values_supported

    quote = "required for all projects with more than one PI and a budget of more than $600,000"
    assert _values_supported(values_in("Required if budget >$600,000 and >1 PI"), quote, values_in(quote))
    assert not _values_supported(values_in("Required if budget >$600,000 and >2 PIs"), quote, values_in(quote))


def test_a_statement_s_number_word_is_found_as_a_figure():
    """Seen on the Seeding Solutions and NHERI solicitations: "references up
    to 5 pages" against "…up to five pages", and "maximum of two proposals
    per institution" against "Limit on Number of Proposals per
    Organization: 2"."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "**Limit on Number of Proposals per Organization:** 2\n\nAn academic institution may submit proposals.\n"
    )}
    judge = Judge(("two proposals", "Limit on Number", "Limit on Number of Proposals per Organization:** 2"))
    result = _trace({"final": {"limited_submission": "maximum of two proposals per institution"}}, judge, docs=[doc])
    assert len(_links(result, "final")) == 1
    judge = Judge(("two proposals", "Limit on Number", "Limit on Number of Proposals per Organization:** 2"))
    result = _trace({"final": {"limited_submission": "maximum of three proposals per institution"}}, judge, docs=[doc])
    assert _links(result, "final") == []


def test_a_field_named_in_the_announcement_s_own_words_is_about_its_label():
    """Seen in the NSF NHERI run: "Funding Instrument: Cooperative Agreement"
    against "Anticipated Type of Award: Cooperative Agreement" — no word of
    the label in the passage, so the short statement was refused."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "**Anticipated Type of Award:** Cooperative Agreement **Estimated Number of Awards:** 3\n"
    )}
    judge = Judge(("Cooperative", "Type of Award", "Anticipated Type of Award:** Cooperative Agreement"))
    result = _trace({"final": {"funding_instrument": "Cooperative Agreement"}}, judge, docs=[doc])
    assert len(_links(result, "final")) == 1
    result = _trace({"final": {"sponsor_contact": "Cooperative Agreement"}}, judge, docs=[doc])
    assert _links(result, "final") == []


def test_a_sentence_is_not_role_checked_against_the_heading_it_sits_under():
    """Seen on the NSF RUI solicitation: "Proposals may be submitted via
    Research.gov or Grants.gov", under "SUBMISSION DETAILS", was asked
    whether the passage made it a submission detail — twice no."""
    from app.services.output_sourcing import label_names_role
    from app.services.output_statements import Statement

    assert not label_names_role(Statement(0, 0, "Proposals may be submitted via Research.gov or Grants.gov",
                                          context=("SUBMISSION DETAILS",)))
    assert label_names_role(Statement(0, 0, "Bureau of Land Management", label="Sponsor"))
    assert label_names_role(Statement(0, 0, "Not required", label="Cost sharing"))


# The NSF NHERI solicitation defines its components, then lists each one's
# milestones in the same words: the RAPID Facility's on p. 2, the EF's on
# p. 3.
NHERI_MILESTONES = _doc("nheri4", "NHERI.pdf", [
    "NHERI comprises a Network Coordination Office (NCO), Experimental Facilities (EF), and a Post-Disaster, "
    "Rapid Response Research (RAPID) Facility.\n" + FILLER,
    "*Key Milestones*\n\nWithin three months of award, External Steering Committee formed and held its first meeting. "
    "By end of fourth month of award, Software Development and Lifecycle Management Plan updated. By end of sixth "
    "month of award, Scheduling process implemented with the NCO.\n" + FILLER,
    "Submission to the NSF of the user fees and recharge rates for the EF. By end of fourth month of award, Software "
    "Development and Lifecycle Management Plan updated. By end of sixth month of award, EF scheduling implemented "
    "with the NCO.\n" + FILLER,
])


def test_a_component_s_row_links_only_where_the_text_names_that_component():
    """Seen in the NSF NHERI run: rows for one component were linked to
    another's milestones, written in the same words. A bare time ("by end of
    sixth month of award") scoped to the EF, and a statement that names the
    EF, need the EF named where they are linked."""
    table = ("| Milestone | Date / Time | Notes |\n|---|---|---|\n"
             "| By end of sixth month of award (EF) | by end of sixth month of award | — |\n"
             "| By end of fourth month of award | — | Milestone: Software Development and Lifecycle Management Plan updated for EF |\n")
    wrong = Judge(("sixth month", "Scheduling process", "By end of sixth month of award, Scheduling process implemented with the NCO."),
                  ("updated for EF", "Steering Committee", "By end of fourth month of award, Software Development and Lifecycle Management Plan updated."),
                  retry_rules=())
    result = _trace({"final": table}, wrong, docs=[NHERI_MILESTONES])
    assert _links(result, "final") == []
    assert result["reasons"] == {"scope_missing": 2}
    right = Judge(("sixth month", "EF scheduling", "By end of sixth month of award, EF scheduling implemented with the NCO."),
                  ("updated for EF", "recharge rates", "By end of fourth month of award, Software Development and Lifecycle Management Plan updated."))
    result = _trace({"final": table}, right, docs=[NHERI_MILESTONES])
    assert sorted(src["page"] for _, src in _links(result, "final")) == [3, 3]


@pytest.mark.parametrize("label, scopes", [
    ("By end of sixth month of award (EF) — Notes", [{"EF"}]),
    ("Within three months of award (Rapid Facility) — Date / Time", [{"rapid"}]),
    ("Full Proposal Target Date (September recurring) — Notes", []),
    ("Collaborators & Other Affiliations (COA) — Description", []),
    ("Eligible institutions — Predominantly Undergraduate Institutions (PUIs)", []),
])
def test_what_a_label_s_brackets_scope_it_to(label, scopes):
    from app.services.output_sourcing import _scopes

    assert _scopes(label) == scopes


def test_a_kind_of_party_is_not_sourced_to_its_negation():
    """Seen in the MRI solicitation: "Accredited colleges and universities",
    under Ph.D.-granting institutions, was linked to the Non-Ph.D.-granting
    definition, which opens with the same words."""
    doc = {"uuid": "rfa", "title": "MRI.pdf", "text_markers": [], "raw_text": (
        "***Ph.D.-granting institutions of higher education*** are accredited colleges and universities that have "
        "awarded more than 20 Ph.D. or D.Sc. degrees in NSF-supported fields.\n\n"
        "***Non-Ph.D.-granting institutions of higher education*** are accredited colleges and universities "
        "(including two-year community colleges) that award Associate's degrees.\n"
    )}
    md = ("### Eligible Institutions\n- **Ph.D.-granting institutions of higher education**\n"
          "  - Compliance: Accredited colleges and universities\n")
    wrong = Judge(("Accredited", "two-year", "accredited colleges and universities (including two-year community colleges)"),
                  retry_rules=())
    result = _trace({"final": md}, wrong, docs=[doc])
    assert _links(result, "final") == [] and result["reasons"].get("subject_differs") == 1
    right = Judge(("Accredited", "more than 20", "accredited colleges and universities that have awarded more than 20"))
    assert len(_links(_trace({"final": md}, right, docs=[doc]), "final")) == 1


def test_a_deadline_for_one_stage_is_not_sourced_to_another_s():
    """Seen in the NSF NHERI run: the full proposal deadline's "Due by 5 p.m.
    proposer's local time" linked to the letter of intent's due date — the
    separate role check said yes, twice."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "**Letter of Intent Due Date(s) *(required)*** (due by 5 p.m. proposer's local time)***:*** October 16, 2015 "
        "**Full Proposal Deadline(s)** (due by 5 p.m. proposer's local time): November 04, 2015\n"
    )}
    md = "| Deadline | Notes |\n|---|---|\n| Full Proposal Deadline | Due by 5 p.m. proposer's local time |\n"
    loi = Judge(("Due by", "Letter of Intent", "Letter of Intent Due Date(s) *(required)*** (due by 5 p.m. proposer's local time)***:*** October 16, 2015"),
                retry_rules=())
    result = _trace({"final": md}, loi, docs=[doc])
    assert _links(result, "final") == [] and result["reasons"] == {"stage_differs": 1}
    full = Judge(("Due by", "Full Proposal", "Full Proposal Deadline(s)** (due by 5 p.m. proposer's local time): November 04, 2015"))
    assert len(_links(_trace({"final": md}, full, docs=[doc]), "final")) == 1


def test_how_strongly_a_clause_asks_is_read_from_its_whole_sentence():
    """Seen in the NSF NHERI run: "Full proposal must be received by FastLane
    no later than 4:59 p.m." linked to the clause "to receive a FastLane
    submittal stamped time no later than … 4:59 pm" of a sentence that says
    proposers are "strongly encouraged" to — a confirmation said yes."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "To ensure that this deadline is met, proposers are strongly encouraged to submit the full proposal to receive "
        "a FastLane submittal stamped time no later than November 4, 2015, 4:59 pm proposer's local time.\n"
    )}
    judge = Judge(("must be received", "FastLane submittal",
                   "to receive a FastLane submittal stamped time no later than November 4, 2015, 4:59 pm proposer's local time"))
    result = _trace({"final": {"notes": "Full proposal must be received by FastLane no later than 4:59 p.m. local time"}},
                    judge, docs=[doc])
    assert _links(result, "final") == [] and result["reasons"] == {"obligation_differs": 1}


def test_an_excerpt_may_run_a_little_past_its_passage_s_edge():
    """Seen in the NSF NHERI run: the passage the judge read ended at "…for up
    to ten additional project", and its excerpt finished the sentence. Mostly
    inside the passage and the rest word for word, it is checked there."""
    from app.services.output_statements import Statement

    sentence = "Two-page biographical sketches, following the NSF GPG format, for up to ten additional project personnel."
    text = ("Recipients shall comply with the general terms of this agreement. " * 9 + "Applicants must read this notice. "
            + sentence + " " + "More text follows on this same line without a break. " * 5 + "\n" + FILLER)
    corpus = Corpus([{"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": text}], [])
    w = corpus.windows[0]
    at = text.index(sentence)
    assert at < w.end < at + len(sentence)
    st = Statement(0, 0, "Biographical Sketch(es) following NSF GPG format",
                   label="required components — Biographical Sketch(es) — description")
    assert verify(st, corpus, 0, sentence).link["quote"] == sentence
    # Mostly past the edge, it is not this passage's.
    assert verify(st, corpus, 0, text[w.end - 10:w.end + 140]).reason == "quote_not_in_passage"


def test_a_short_cell_needs_its_row_named_where_it_links():
    """Seen in the NSF RUI solicitation: the RUI Impact Statement's "PDF
    format" was linked to the Certification of RUI/ROA Eligibility's "…should
    be scanned and included as a searchable PDF file"; a separate check said
    yes, twice."""
    doc = {"uuid": "rfa", "title": "RFA.pdf", "text_markers": [], "raw_text": (
        "**Certification of RUI/ROA Eligibility.** A current, signed Certification should be scanned and included "
        "in searchable PDF format.\n\n**RUI Impact Statement.** The RUI Impact Statement must be uploaded in PDF "
        "format, up to five pages.\n"
    )}
    md = "| Component | Special Requirements |\n|---|---|\n| RUI Impact Statement | PDF format |\n"
    wrong = Judge(("PDF format", "Certification", "should be scanned and included in searchable PDF format"), retry_rules=())
    result = _trace({"final": md}, wrong, docs=[doc])
    assert _links(result, "final") == [] and result["reasons"] == {"label_not_in_passage": 1}
    right = Judge(("PDF format", "Impact Statement must", "The RUI Impact Statement must be uploaded in PDF format"))
    assert len(_links(_trace({"final": md}, right, docs=[doc]), "final")) == 1


def test_a_highlight_grows_back_to_the_label_it_sits_under_before_the_next_field():
    """Seen in the NSF RUI solicitation: "There are no restrictions or
    limits." grew into the next field's "Limit on Number of Proposals per PI
    or co-PI: …" rather than its own "…per Organization:"."""
    from app.services.output_sourcing import widen_to_statement

    text = ("**Limit on Number of Proposals per Organization:** There are no restrictions or limits. "
            "**Limit on Number of Proposals per PI or co-PI:** The number of allowed proposals per PI varies by program.")
    start = text.index("There are")
    end = start + len("There are no restrictions or limits.")
    a, b = widen_to_statement(text, start, end, 0, len(text),
                              stems("no restrictions or limits on number of proposals per institution"),
                              same_page=lambda _: True)
    assert text[a:b] == "**Limit on Number of Proposals per Organization:** There are no restrictions or limits."


def test_a_numbered_track_is_not_advice():
    """Seen in the MRI solicitation: "Track 1 requests >$100,000 and
    <$1,400,000…" read as the imperative "Track", then refused for the
    condition in its own rule."""
    from app.services.output_sourcing import is_action
    from app.services.output_statements import Statement

    assert not is_action(Statement(0, 0, "Track 1 requests >$100,000 and <$1,400,000", label="Funding Limits"))
    assert is_action(Statement(0, 0, "Track the purchase against the award", label=""))


MRI = _doc("mri", "MRI.pdf", [
    "Note: A Data Management Plan is required for MRI proposals. Researchers are expected to share with other "
    "researchers, at no more than incremental cost and within a reasonable amount of time, the primary data. "
    "As a result MRI budgets may include incremental costs associated with the implementation of this plan.\n"
    + FILLER,
])


def test_the_highlight_takes_in_the_sentence_the_statement_rests_on():
    """Seen in the MRI solicitation: "Data management plan incremental
    costs" highlighted the sentence about sharing data at incremental cost;
    the next sentence is the one that says budgets may include them."""
    judge = Judge(("incremental", "incremental cost", "share with other researchers, at no more than incremental cost"))
    result = _trace({"final": {"allowable_costs": ["Data management plan incremental costs"]}}, judge, docs=[MRI])
    [(_, src)] = _links(result, "final")
    assert src["quote"].startswith("share with other researchers, at no more than incremental cost")
    assert src["quote"].endswith("MRI budgets may include incremental costs associated with the implementation of this plan.")
    assert src["excerpt"][src["quote_start"]:src["quote_end"]] == src["quote"]
    # The judge's own excerpt said little of the statement: a separate call confirmed it.
    assert [it["excerpt"] for it in judge.confirm_asked] == [src["quote"]]
    assert "judge_quote" not in src


def test_the_sentence_around_an_excerpt_at_the_start_of_a_text_keeps_its_first_letter():
    from app.services.output_sourcing import sentence_around

    assert sentence_around("EXPENSE RECORD for the award", 8, 14) == "EXPENSE RECORD for the award"
    assert sentence_around("One. Two words here. Three.", 5, 8) == "Two words here."


def test_a_highlight_already_saying_the_statement_is_left_as_the_judge_copied_it():
    judge = Judge(RECIPIENT)
    [(_, src)] = _links(_trace({"final": "The recipient is Southern Utah University."}, judge), "final")
    assert src["quote"] == "Recipient: Southern Utah University"


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
    # The highlight also takes in the record's title, which the statement names.
    assert (src["document_uuid"], src["quote"]) == ("exp", "EXPENSE RECORD\nAward: L24AC00293-00 (BLM, Southern Utah University)")
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


TRAINING = {"uuid": "noa2", "title": "NoA.pdf", "text_markers": [], "raw_text": (
    "Special Conditions\n"
    "D. Recipient staff will be required to complete a BLM-approved Defensive Driving Course if driving a "
    "Government-owned vehicle (GOV).\n"
    "E. Recipient staff will be required to complete a BLM-approved Four-wheel ATV safety and training "
    "program if using Government-furnished ATVs.\n"
)}


def test_a_requirement_is_not_sourced_to_one_that_applies_only_in_a_case():
    """Seen on the BLM award: "Mandatory BLM‑approved safety and training
    courses" was linked to training the award requires only if staff drive a
    Government vehicle or use its ATVs. A statement that keeps the case is
    stated."""
    quote = ("Recipient staff will be required to complete a BLM-approved Four-wheel ATV safety and training "
             "program if using Government-furnished ATVs.")
    judge = Judge(("training", "Four-wheel", quote))
    result = _trace({"final": {"special_conditions": ["Mandatory BLM‑approved safety and training courses"]}},
                    judge, docs=[TRAINING])
    assert _links(result, "final") == []
    assert result["reasons"] == {"condition_dropped": 1}
    kept = {"special_conditions": ["BLM-approved ATV safety and training required when using Government-furnished ATVs"]}
    assert len(_links(_trace({"final": kept}, judge, docs=[TRAINING]), "final")) == 1


@pytest.mark.parametrize("statement,label,text,dropped", [
    # A label's "required" does not make a page limit a requirement.
    ("Maximum 2 pages", "required components — Collaboration Plan",
     "If more than one PI is involved, a collaboration plan (up to 2 pages) must be provided.", False),
    ("A collaboration plan must be provided", "", "If more than one PI is involved, a collaboration plan "
     "(up to 2 pages) must be provided.", True),
    ("A collaboration plan must be provided when more than one PI is involved", "",
     "If more than one PI is involved, a collaboration plan (up to 2 pages) must be provided.", False),
])
def test_what_counts_as_a_requirement_stated_without_its_case(statement, label, text, dropped):
    from app.services.output_sourcing import condition_dropped
    from app.services.output_statements import Statement

    assert condition_dropped(Statement(0, 0, statement, label=label), text) is dropped


SECURITY_TRAINING = (
    "C. \nFederal Information Systems Security Awareness Training.  Before the recipient,  \nor any of its "
    "employees or subrecipients, are granted access to the BLM Federal  \ncomputer system, they must first "
    "successfully complete the U.S. Department of  \nthe Interior's (DOI) Federal Information Systems Security "
    "Awareness Online  \nCourse."
)


def test_a_requirement_is_not_sourced_to_a_precondition_it_leaves_out():
    """Seen on the BLM award: "Requirement to complete DOI Federal
    Information Systems Security Awareness training" was linked to the
    training required before access to the BLM computer system. The case
    shares "Federal" and "system" with the statement — words the award uses
    throughout — and a duty stated as a noun is a duty."""
    from app.services.output_sourcing import common_words, condition_dropped, dropped_condition
    from app.services.output_statements import Statement

    common = common_words(" ".join(["Federal system"] * 10))
    st = Statement(0, 0, "Requirement to complete DOI Federal Information Systems Security Awareness training.")
    assert condition_dropped(st, SECURITY_TRAINING, common)
    assert "granted access to the BLM Federal computer system" in dropped_condition(st, SECURITY_TRAINING, common)
    # Without knowing those words are everywhere, the shared words keep the case.
    assert not condition_dropped(st, SECURITY_TRAINING)
    kept = Statement(0, 0, "DOI security awareness training is required before access to BLM computer systems")
    assert not condition_dropped(kept, SECURITY_TRAINING, common)


@pytest.mark.parametrize("statement,text,dropped", [
    # A threshold in the statement is its own case; "$600,000" is one figure.
    ("Required for proposals > $600,000 with multiple PIs",
     "If a proposal with a budget exceeding $600,000 and more than one investigator does not include a "
     "Collaboration Plan, that proposal will be returned without review.", False),
    # A date is not a case.
    ("Annual reports must be submitted", "Annual reports must be submitted before December 31, 2025.", False),
    ("Recipients must complete the training", "Before travelling abroad, recipients must complete the training.",
     True),
])
def test_cases_with_figures_dates_and_preconditions(statement, text, dropped):
    from app.services.output_sourcing import condition_dropped
    from app.services.output_statements import Statement

    assert condition_dropped(Statement(0, 0, statement), text) is dropped


@pytest.mark.parametrize("text,expected", [
    ("Requirement to complete DOI training", (True, False, False)),
    ("Requirements that apply to subawards", (True, False, False)),
    ("No requirement for cost sharing", (False, False, True)),
    ("Program requirements", (False, False, False)),
])
def test_a_duty_stated_as_a_noun(text, expected):
    from app.services.output_sourcing import obligation

    assert obligation(text) == expected


@pytest.mark.parametrize("text", [
    # "Even if" says the rule holds regardless.
    "a collaboration plan must be provided for all projects, even if all investigators are affiliated "
    "with the same organization.",
    # "Unless" is usually the rule itself.
    "No funds may be obligated for infrastructure unless all of the iron and steel is produced in the "
    "United States.",
    # A hedge is not a case.
    "Include a collaboration plan, if applicable.",
])
def test_what_is_not_a_case_a_rule_applies_in(text):
    from app.services.output_sourcing import dropped_condition
    from app.services.output_statements import Statement

    assert dropped_condition(Statement(0, 0, "A collaboration plan is required"), text) is None


PRIOR_APPROVAL = {
    "chunk_id": "ug_d_308", "kb_title": "OMB Uniform Guidance", "document_title": "Subpart D",
    "label": "OMB Uniform Guidance — Subpart D · § 200.308", "page": None,
    "content": ("§ 200.308 Revision of budget and program plans.\n(c)(1) The recipient must request prior "
                "approval from the Federal agency for the following program or budget-related reasons:\n"
                "(1) Change in the scope or the objective of the project or program.\n"
                "(5) The transfer of funds budgeted for participant support costs to other budget categories.\n"),
}


def _readings(*answers):
    """A confirmation that answers each reading in turn."""
    said = list(answers)
    return lambda item: said.pop(0)


def test_a_rule_whose_excerpt_adds_a_limit_is_confirmed_by_a_majority_of_three_readings():
    """Seen on the BLM award: "Transfer of funds between budget categories"
    under "prior approval requirements" was linked to § 200.308(c)(1)(5),
    which is about funds budgeted for participant support costs only. Every
    word of the statement is in the excerpt, so no word count could see it;
    one reading of a borderline link flips with what it is batched with, so
    three are asked and a majority decides."""
    quote = "The transfer of funds budgeted for participant support costs to other budget categories."
    value = {"prior_approval_requirements": ["Transfer of funds between budget categories"]}
    refused = Judge(("Transfer of funds", "participant support", quote), confirm=_readings(True, False, False))
    result = _trace({"final": value}, refused, docs=[], passages=[PRIOR_APPROVAL])
    assert _links(result, "final") == [] and result["reasons"] == {"not_confirmed": 1}
    assert len(refused.confirm_asked) == 3
    kept = Judge(("Transfer of funds", "participant support", quote), confirm=_readings(False, True, True))
    assert len(_links(_trace({"final": value}, kept, docs=[], passages=[PRIOR_APPROVAL]), "final")) == 1


def test_an_excerpt_that_adds_nothing_the_statement_lacks_is_not_confirmed_again():
    quote = "The transfer of funds budgeted for participant support costs to other budget categories."
    judge = Judge(("participant support", "participant support", quote))
    value = {"prior_approval_requirements": ["Transfer of funds budgeted for participant support costs to other budget categories"]}
    assert len(_links(_trace({"final": value}, judge, docs=[], passages=[PRIOR_APPROVAL]), "final")) == 1
    assert judge.confirm_asked == []


def test_what_may_say_less_than_its_statement():
    from app.services.output_sourcing import narrows
    from app.services.output_statements import Statement

    excerpt = "The transfer of funds budgeted for participant support costs to other budget categories."
    link = {"quote": excerpt, "excerpt": excerpt, "quote_start": 0, "quote_end": len(excerpt)}
    rule = Statement(0, 0, "Transfer of funds between budget categories", label="prior approval requirements")
    assert narrows(rule, link)
    # Only a statement of a rule is read for words added inside it.
    assert not narrows(Statement(0, 0, "Transfer of funds between budget categories", label="topics"), link)
    # A case in the excerpt's sentence that the statement leaves out, whatever it is.
    sentence = "Staff must complete the course if using Government-furnished ATVs."
    near = {"quote": "Staff must complete the course", "excerpt": sentence, "quote_start": 0, "quote_end": 30}
    assert narrows(Statement(0, 0, "Course completion", label="topics"), near)


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
    # The first look and its second look.
    assert result["errors"] == 2


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
    # The judge starts in time; the role check does not.
    result = trace_sources(
        {"final": {"recipient": "Southern Utah University"}}, [NOA], [], ask=judge,
        workers=1, deadline=5.0, clock=lambda: 10.0 if judge.asked else 0.0,
    )
    assert judge.asked and not judge.role_asked
    assert _links(result, "final") == []
    assert result["reasons"] == {"role_unchecked": 1} and result["unchecked"] == 1


# ---------------------------------------------------------------------------
# Second looks, order, and results while tracing
# ---------------------------------------------------------------------------

RECIPIENT = ("Southern Utah", "Recipient:", "Recipient: Southern Utah University")


def test_a_second_look_links_only_what_a_separate_check_confirms():
    """The first look said no; a second look, with more passages, finds the
    excerpt. A second chance to say yes is not a second opinion: a separate
    call, asked only whether the excerpt states the statement, must agree."""
    statement = "The recipient is Southern Utah University."
    judge = Judge(retry_rules=(RECIPIENT,))
    result = _trace({"final": statement}, judge)
    [(_, src)] = _links(result, "final")
    assert src["quote"] == "Recipient: Southern Utah University"
    assert [it["statement"] for it in judge.asked] == [statement]
    assert [it["statement"] for it in judge.retried] == [statement]
    assert [(it["statement"], it["excerpt"]) for it in judge.confirm_asked] == [(statement, RECIPIENT[2])]
    assert (result["retried"], result["rescued"]) == (1, 1)

    judge = Judge(retry_rules=(RECIPIENT,), confirm=lambda item: False)
    result = _trace({"final": statement}, judge)
    assert _links(result, "final") == [] and result["reasons"] == {"not_confirmed": 1}


def test_a_statement_that_says_more_than_its_excerpt_is_confirmed_apart():
    """Seen in the NSF run: "Include the required single-copy PDFs (…) and
    adhere to file-format and naming rules of the chosen system", linked to
    an excerpt that says nothing of formats or names. Every check passed;
    only a separate call asked whether the excerpt states all of it caught
    it."""
    statement = "The recipient is Southern Utah University and it must file quarterly vendor reports."
    judge = Judge(RECIPIENT, confirm=lambda item: False)
    result = _trace({"final": statement}, judge, docs=[NOA])
    assert _links(result, "final") == [] and result["reasons"] == {"not_confirmed": 1}
    assert [it["statement"] for it in judge.confirm_asked] == [statement]
    # Confirmed, it links.
    judge = Judge(RECIPIENT)
    assert len(_links(_trace({"final": statement}, judge, docs=[NOA]), "final")) == 1


def test_a_link_the_first_look_found_needs_no_confirmation():
    judge = Judge(RECIPIENT)
    result = _trace({"final": "The recipient is Southern Utah University."}, judge)
    assert len(_links(result, "final")) == 1
    assert judge.retried == [] and judge.confirm_asked == []


def test_only_a_miss_the_judge_could_have_avoided_gets_a_second_look():
    # A refusal on how strongly the excerpt asks is not tried again: the
    # same excerpt would be found.
    judge = Judge(("Subawards", "may include", CLAUSE_QUOTE))
    result = _trace({"final": "Subawards over $50,000 performed outside the United States must include this clause."},
                    judge, docs=[CLAUSE])
    assert judge.retried == [] and result["reasons"] == {"obligation_differs": 1}
    # Nor is a link.
    judge = Judge(RECIPIENT)
    _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    assert judge.retried == []


def test_a_link_refused_for_what_its_passage_is_about_gets_a_second_look_elsewhere():
    """A role, a sponsor or a part of a submission the refused passage does
    not give may be given by another. The second look is never offered the
    refused passage; when nothing else states it, the refusal stands."""
    judge = Judge(RECIPIENT, role=lambda item, n: False)
    result = _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    assert result["reasons"] == {"role_not_shown": 1}
    assert not any("Recipient: Southern Utah University" in p for it in judge.retried for p in it["offered"])


def test_the_deliverable_is_checked_first_and_from_the_top():
    """Underlines appear while the trace runs: the deliverable's, from the
    top down, before any step's."""
    judge = Judge(RECIPIENT, ("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."))
    trace_sources({
        "step:Read": {"vendor": "Forestry Suppliers Inc."},
        "final": "The recipient is Southern Utah University.\n\nIt bought from Forestry Suppliers Inc.\n",
    }, [NOA, EXPENSE], [], ask=judge, workers=1, first={"final"})
    assert [it["statement"] for it in judge.asked][:2] == [
        "The recipient is Southern Utah University.", "It bought from Forestry Suppliers Inc.",
    ]
    assert judge.asked[-1]["statement"] == "Forestry Suppliers Inc."


def test_other_outputs_wait_until_the_deliverable_is_settled():
    """The model server is shared: a step's statements checked alongside the
    deliverable's would slow the underlines the reader is waiting for."""
    calls = []
    inner = Judge(RECIPIENT, ("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."))

    def judge(instructions, prompt):
        kind = "role" if instructions == ROLE_INSTRUCTIONS else "judge"
        calls.append((kind, "Forestry" in prompt.split("STATEMENTS", 1)[1]))
        return inner(instructions, prompt)

    trace_sources({"step:Read": {"vendor": "Forestry Suppliers Inc."},
                   "final": {"recipient": "Southern Utah University"}},
                  [NOA, EXPENSE], [], ask=judge, workers=4, first={"final"})
    step_at = calls.index(("judge", True))
    assert calls[:step_at] == [("judge", False)] + [("role", False)] * ROLE_VOTES


def test_checks_that_settle_a_link_run_before_the_next_judge_call():
    calls = []
    inner = Judge(RECIPIENT, ("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."))

    def judge(instructions, prompt):
        calls.append("role" if instructions == ROLE_INSTRUCTIONS else "judge")
        return inner(instructions, prompt)

    from app.services import output_sourcing as O
    old = O.BATCH_STATEMENTS
    O.BATCH_STATEMENTS = 1
    try:
        trace_sources({"final": {"recipient": "Southern Utah University", "vendor": "Forestry Suppliers Inc."}},
                      [NOA, EXPENSE], [], ask=judge, workers=1)
    finally:
        O.BATCH_STATEMENTS = old
    assert calls[:2 + ROLE_VOTES] == ["judge"] + ["role"] * ROLE_VOTES + ["judge"]


def test_results_while_tracing_mark_what_is_still_being_checked():
    published = []
    judge = Judge(RECIPIENT, ("Forestry", "Vendor:", "Vendor: Forestry Suppliers Inc."))
    from app.services import output_sourcing as O
    old = (O.BATCH_STATEMENTS, O.PUBLISH_EVERY)
    O.BATCH_STATEMENTS, O.PUBLISH_EVERY = 1, 0.0
    try:
        result = trace_sources(
            {"final": "The recipient is Southern Utah University.\n\nIt bought from Forestry Suppliers Inc.\n"},
            [NOA, EXPENSE], [], ask=judge, workers=1, publish=published.append,
        )
    finally:
        O.BATCH_STATEMENTS, O.PUBLISH_EVERY = old
    assert published and all(p["status"] == "running" for p in published)
    rows = published[0]["targets"]["final"]["statements"]
    assert [("src" in r, r.get("w")) for r in rows] == [(True, None), (False, 1)]
    # A source keeps its index: the final result extends what was shown.
    assert result["status"] == "done"
    assert result["sources"][:len(published[0]["sources"])] == published[0]["sources"]
    assert [r.get("src") for r in result["targets"]["final"]["statements"]] == [0, 1]
    assert all("w" not in r for r in result["targets"]["final"]["statements"])


def test_a_judge_reply_with_a_line_break_inside_a_quote_is_read():
    """gpt-oss and others copy a passage's line break into the quote as a
    raw character: invalid JSON, and every statement of the call lost."""
    reply = '{"items": [{"id": 1, "supported": true, "passage": "P1", "quote": "Recipient: Southern\nUtah University"}]}'
    result = _trace({"final": "The recipient is Southern Utah University."}, Judge(reply=reply), docs=[NOA])
    [(_, src)] = _links(result, "final")
    assert src["quote"] == "Recipient: Southern Utah University"


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


@pytest.mark.parametrize("statement,quote,differs", [
    # Seen on the NSF NHERI solicitation: a deliverable wrote every section's
    # "up to N pages" as "≥N pages", and the links stood.
    ("Summarize cybersecurity plan (≥1 page).", "Section 14. Cybersecurity Plan-Summary (all proposals, up to one page)", True),
    ("Optional additional information (at least 2 pages)", "(optional for all proposals, up to two pages)", True),
    ("Maximum 55 pages", "Project Description must not exceed 55 pages", False),
    ("Up to $10,000 per year", "Up to $10,000 should be budgeted annually", False),
    ("Minimum award of $50,000", "awards may be up to $50,000", True),
    ("Budget no more than $500,000", "budgets of at least $100,000 and up to $500,000", False),
    ("Font 11pt", "font size of at least 11 points", False),
])
def test_a_limit_turned_around_is_not_linked(statement, quote, differs):
    from app.services.output_sourcing import limit_direction_differs

    assert limit_direction_differs(statement, quote) is differs
