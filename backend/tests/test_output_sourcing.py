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

from app.services.output_sourcing import Corpus, stems, trace_sources, values_in, verify
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
    other statement is unsupported. Records the statements it was asked."""

    def __init__(self, *rules, raises=None, reply=None):
        self.rules = rules
        self.raises = raises
        self.reply = reply
        self.asked: list[dict] = []

    def __call__(self, instructions, prompt):
        if self.raises:
            raise self.raises
        if self.reply is not None:
            return self.reply
        passages = dict(_PASSAGE_RE.findall(prompt))
        items = [json.loads(line) for line in prompt.split("STATEMENTS", 1)[1].splitlines() if line.strip()]
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
])
def test_values_compare_as_the_same_value(statement, quote, same):
    want = {v.key for v in values_in(statement)}
    from app.services.output_sourcing import _quote_keys
    assert want and (want <= _quote_keys(values_in(quote))) is same


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
    ("Southern", "quote_too_short"),
])
def test_an_excerpt_must_be_verbatim_and_contiguous(quote, reason):
    judge = Judge(("Southern Utah", "Recipient:", quote))
    result = _trace({"final": {"recipient": "Southern Utah University"}}, judge)
    assert _links(result, "final") == []
    assert result["reasons"] == {reason: 1}


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


def test_an_excerpt_from_another_document_than_the_one_named_is_refused():
    # The judge names the Notice of Award's passage but quotes the record:
    # the excerpt is checked in the passage named, never searched elsewhere.
    judge = Judge(("expense record", "NOTICE OF AWARD", "Award: L24AC00293-00 (BLM, Southern Utah University)"))
    result = _trace({"final": "The expense record charges the purchase to award L24AC00293-00."}, judge)
    assert _links(result, "final") == []
    assert result["reasons"] == {"quote_not_in_passage": 1}


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
