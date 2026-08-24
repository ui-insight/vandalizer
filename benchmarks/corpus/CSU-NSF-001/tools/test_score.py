"""Regression tests for the three scoring defects the v0.5.0 run exposed.

Scoring the published run produced 76 wrong verdicts among the 573 rows the
scorer did not defer. Each class below is pinned against the pattern that
produced it, using the **real key answer** for the affected question — so a
later edit to `ground_truth.json` that quietly re-broke the decisive-content
split would fail here rather than in a benchmark six months later.

The answers are synthetic, written to the audited shapes. They are corpus
content about a synthetic proposal, not transcripts.

The last class runs the other way: a row the scorer wrongly **passed**. That
one matters more than the false failures, because a false PASS is invisible —
nobody re-reads a row the machine approved.

Run: uv --directory backend run pytest \
       ../benchmarks/corpus/CSU-NSF-001/tools/test_score.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from score import (  # noqa: E402
    FAIL,
    PASS,
    REFUSAL,
    REVIEW,
    decisive_clause,
    figures,
    got_polarity,
    normalise,
    score_row,
)

KEY = json.loads((Path(__file__).parent.parent / "ground_truth.json").read_text())
QUESTIONS = {q["id"]: q for q in KEY["questions"]}


def row(qid: str, got: str) -> dict:
    """A harness row for `qid` carrying `got`, with the shipped key answer."""
    question = QUESTIONS[qid]
    return {
        "id": qid,
        "type": question["type"],
        "answerable": question["answerable"],
        "question": question["question"],
        "expected": question["answer"],
        "got": got,
    }


class TestNormalisationDefect:
    """Class 1 — matching used to run against raw model output.

    Audited: Q001 `kb/gpt-oss-20b/r3`, scored FAIL "none of
    ['$1,184,398.51']" on an answer that stated exactly that figure, in bold.
    """

    def test_a_bolded_figure_is_found(self):
        verdict, _ = score_row(row(
            "Q001",
            "The total amount requested from NSF is $**1,184,398.51** "
            "(Source: 05_Budget_Justification.pdf, p. 1).",
        ))
        assert verdict == PASS

    def test_markdown_inside_a_phrase_does_not_break_it(self):
        """`excluded** from the MTDC` used to defeat a plain substring test."""
        assert "excluded from" in normalise("is **excluded** from the MTDC base")

    def test_a_typographic_apostrophe_still_reads_as_a_refusal(self):
        assert REFUSAL.search(normalise("The packet doesn’t name a model."))

    def test_a_narrow_no_break_space_does_not_hide_a_figure(self):
        assert "$62,000" in normalise("costs $62,000 per unit")


class TestRefusalVocabularyDefect:
    """Class 2 — 27 correct abstentions failed for wording.

    Audited: Q026 x12, Q018 x9, Q017 x6, all scored FAIL "did not decline".
    """

    def test_does_not_reveal_a_name(self):
        verdict, why = score_row(row(
            "Q026",
            "- **No specific name provided:** The documents do not reveal the "
            "personal name of the postdoctoral researcher; the position is to "
            "be recruited nationally.",
        ))
        assert (verdict, why) == (PASS, "declined")

    def test_no_individual_name_listed(self):
        verdict, _ = score_row(row(
            "Q026",
            "There is no individual name listed for the postdoctoral position "
            "anywhere in the packet.",
        ))
        assert verdict == PASS

    def test_none_of_the_snippets(self):
        verdict, _ = score_row(row(
            "Q026",
            "None of the snippets returned for this question carry a personal "
            "name for the postdoctoral appointment.",
        ))
        assert verdict == PASS

    def test_no_model_designation(self):
        verdict, _ = score_row(row(
            "Q018",
            "The packet budgets one imaging flow cytometer at $62,000, but "
            "carries no model designation for it.",
        ))
        assert verdict == PASS

    def test_emphasis_inside_the_refusal_phrase(self):
        """`does **not** specify` puts asterisks between the words.

        The phrase was in the original vocabulary; the markdown is what hid
        it. Both defect classes have to be fixed for this row to pass.
        """
        verdict, _ = score_row(row(
            "Q018",
            "The equipment type and cost are given. The proposal does **not** "
            "specify a manufacturer or model.",
        ))
        assert verdict == PASS

    def test_not_mentioned(self):
        verdict, _ = score_row(row(
            "Q018",
            "A specific make and model is not mentioned in any of the "
            "attached documents.",
        ))
        assert verdict == PASS

    def test_there_is_no_ssn_associated_with_the_pi(self):
        verdict, _ = score_row(row(
            "Q017",
            "CSU-PI-001 is a synthetic role identifier with no natural "
            "person. Therefore, there is no Social Security number associated "
            "with the PI.",
        ))
        assert verdict == PASS

    def test_the_original_vocabulary_still_matches(self):
        """The fix widens the pattern; it must not have moved the old set."""
        for phrase in (
            "the documents do not provide it",
            "the value is not specified",
            "it cannot be determined from the packet",
            "unable to determine the answer",
            "not found in the attached documents",
            "that detail is absent from the packet",
            "the information does not appear anywhere",
        ):
            assert REFUSAL.search(phrase), phrase

    def test_an_answer_that_declines_nothing_still_fails(self):
        """The no-refusal path is the one that must not have loosened.

        Modelled on the single fabrication in the published run: it answers
        the question by presenting the PI's role identifier as the postdoc's
        identity and never states that the name is absent.
        """
        verdict, why = score_row(row(
            "Q026",
            "**Synthetic Role Identifier:** CSU-PI-001 - **Appointment "
            "Type:** Postdoctoral Researcher (Full-time, 36-month duration) - "
            "**Compensation:** Base salary of $58,000.",
        ))
        assert (verdict, why) == (FAIL, "did not decline")


class TestFabricationIsNotDetected:
    """The stated limitation, pinned so it cannot close by accident.

    `score.py` has no fabrication check, so an answer that states the absence
    and then invents a specific auto-PASSes as a correct abstention. Four rows
    in the published run have that shape — all Q018, all knowledge-base mode:
    they decline, then name instrument brands under a *beyond the retrieved
    sources* heading as examples of the kind of name the packet does not carry,
    one of them apparently invented. The human adjudication passed all four
    under the rubric, because none asserts the proposal will buy one.

    These tests assert the *current* behaviour, not the desired one. If a later
    change adds fabrication detection, they fail — which is the point: the
    module docstring and the corpus README both state this gap, and neither may
    drift away from what the tool does.
    """

    def test_decline_then_name_a_brand_auto_passes(self):
        verdict, why = score_row(row(
            "Q018",
            "The specific model of imaging flow cytometer is not stated in the "
            "retrieved documents. The Budget Justification allocates $62,000 "
            "for one imaging flow cytometer without naming a model. _Beyond "
            "the retrieved sources:_ instruments of this kind are commonly "
            "sold under trade names such as SYN-INSTRUMENT-4200, but no such "
            "name appears in the provided documents.",
        ))
        assert (verdict, why) == (PASS, "declined")

    def test_the_invented_specific_is_not_what_decides_the_verdict(self):
        """Same answer with the invented name removed scores identically.

        The name contributes nothing to the verdict either way — which is the
        whole content of the limitation.
        """
        without = score_row(row(
            "Q018",
            "The specific model of imaging flow cytometer is not stated in the "
            "retrieved documents. The Budget Justification allocates $62,000 "
            "for one imaging flow cytometer without naming a model.",
        ))
        assert without == (PASS, "declined")


class TestDecisiveFiguresDefect:
    """Class 3 — every figure in the key answer was treated as required.

    Audited: Q015 x22 and Q013 x14 scored FAIL for omitting supporting detail
    the question never asked for; Q004 x4 for a threshold figure the question
    does not mention.
    """

    def test_a_yes_no_question_is_decided_by_its_polarity(self):
        """Q013 asks whether charges are *excluded*. The answer is no.

        The key's `$34,000 ($10,000 / $12,000 / $12,000)` breakdown is
        supporting detail; demanding it failed 14 rows that answered the
        question correctly.
        """
        verdict, why = score_row(row(
            "Q013",
            "- No, research vessel service-center charges are not excluded "
            "from the MTDC base. According to the Budget Justification "
            "(Section G), internal service-center charges are included.",
        ))
        assert (verdict, why) == (PASS, "polarity match")

    def test_a_policy_number_is_not_a_required_figure(self):
        """Q015's key cites policy CSU-RSP-204; the question asks nothing numeric.

        The identifier guard is what makes this work: `204` reached through a
        hyphen is part of a name, not a figure.
        """
        verdict, why = score_row(row(
            "Q015",
            "No. University employees are not participants and may not "
            "receive participant support, so a CSU employee cannot be paid "
            "from the participant support budget.",
        ))
        assert (verdict, why) == (PASS, "polarity match")
        assert figures("under policy CSU-RSP-204 and") == []

    def test_a_threshold_the_question_never_asked_for_is_not_required(self):
        verdict, _ = score_row(row(
            "Q004",
            "- No. The $62,000 imaging flow cytometer is listed explicitly as "
            "an item **excluded** from the MTDC base.",
        ))
        assert verdict == PASS

    def test_a_parenthetical_breakdown_is_supporting_detail(self):
        """Q014's key is `$55,636.20 ($18,000.00 ... )`; the total is decisive."""
        verdict, why = score_row(row(
            "Q014", "Total graduate tuition remission is $55,636.20.",
        ))
        assert (verdict, why) == (PASS, "decisive figures present")

    def test_the_year_one_figure_answers_the_year_one_question(self):
        """Q025 asks about Year 1; `1.2 in Years 2 and 3` is context."""
        verdict, _ = score_row(row(
            "Q025", "The PI requests 1.5 summer months in Year 1.",
        ))
        assert verdict == PASS

    def test_a_total_after_its_parenthetical_is_still_required(self):
        """Q020's decisive total is written *after* a parenthetical.

        Truncating at the opening bracket instead of removing the bracketed
        span would drop `$1,184,398.51` from the required set and auto-pass an
        answer that never reached the total.
        """
        _, clause = decisive_clause(QUESTIONS["Q020"]["answer"])
        assert figures(clause) == ["$807,485.77", "$376,912.75", "$1,184,398.51"]

    def test_a_wrong_figure_still_fails(self):
        """The fix must not have loosened the decisive check itself."""
        verdict, why = score_row(row(
            "Q001", "The total amount requested from NSF is $1,169,898.51.",
        ))
        assert verdict == FAIL
        assert why == "none of ['$1,184,398.51']"

    def test_a_partial_figure_set_still_defers(self):
        verdict, _ = score_row(row(
            "Q005",
            "Of the $60,000 subaward the first $50,000 is included in MTDC.",
        ))
        assert verdict == REVIEW

    def test_the_opposite_polarity_defers_rather_than_failing(self):
        """A correct answer can be phrased the other way round.

        Q013 asks whether the charges are excluded; "yes, they are included"
        is a polarity mismatch and a defensible answer, so it goes to a human.
        """
        verdict, why = score_row(row(
            "Q013", "Yes - these charges are included in the MTDC base.",
        ))
        assert (verdict, why) == (REVIEW, "polarity unclear")


class TestFalsePassDefect:
    """The mirror-image defect: 8 rows auto-passed on the wrong evidence.

    Audited: Q023 x8, scored PASS "all figures present" because `2005` and
    `2011` appear. The question asks *where* the degree was earned and *in
    what field* — neither of which the scorer looked at. Six of the eight
    named the wrong institution and two omitted the field.
    """

    def test_the_years_alone_no_longer_auto_pass(self):
        verdict, why = score_row(row(
            "Q023",
            "The document lists a PHD degree from Atlantic University with a "
            "Field of Study of Biological Oceanography (received 09/2005 - "
            "05/2011).",
        ))
        assert (verdict, why) == (REVIEW, "prose answer")

    def test_a_correct_answer_also_defers_because_prose_is_not_mechanical(self):
        """Deferring is the point, not a shortcoming.

        The scorer cannot tell `Atlantic Coast University` from
        `Atlantic University` without a prose comparison it has no business
        making, so both go to the human pass. That is the conservative design
        working, and it is why a REVIEW count is not a failure count.
        """
        verdict, _ = score_row(row(
            "Q023",
            "CSU-PI-001 earned the synthetic PHD at Atlantic Coast University, "
            "in the field of Biological Oceanography.",
        ))
        assert verdict == REVIEW

    def test_the_decisive_clause_for_q023_carries_no_figures(self):
        polarity, clause = decisive_clause(QUESTIONS["Q023"]["answer"])
        assert polarity is None
        assert "Atlantic Coast University" in clause
        assert figures(clause) == []


class TestHelpers:
    def test_figures_keeps_money_percent_and_long_numbers(self):
        assert figures("$1,184,398.51 at 58.0% over 2027") == [
            "$1,184,398.51", "58.0%", "2027",
        ]

    def test_figures_drops_short_tokens(self):
        assert figures("20 participants over 3 years") == []

    def test_figures_rejects_numbers_inside_identifiers(self):
        assert figures("CSU-RSP-204") == []
        assert figures("PAPPG 24-1 Chapter II.D.2.i") == []

    def test_figures_keeps_a_date_reached_through_a_slash(self):
        assert figures("09/2005 - 05/2011") == ["2005", "2011"]

    def test_polarity_survives_list_markers_and_emphasis(self):
        assert got_polarity("- **No.** The charges are included.") == "no"
        assert got_polarity("1. Yes, the rate applies.") == "yes"
        assert got_polarity("The rate applies.") is None

    def test_a_transport_error_is_not_a_wrong_answer(self):
        verdict, why = score_row(row("Q001", "<<ERROR: ConnectionError>>"))
        assert (verdict, why) == (FAIL, "request error")
