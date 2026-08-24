"""Tests for the document attribution and outcome ladder in citation_accuracy.

The scorer decides which document a `p. N` belongs to by looking back over the
text just before it. Getting that wrong silently converts a correct citation
into a `wrong_page` or `wrong_doc`, which is exactly the number the benchmark
comment quotes — so it needs to be right.

The second half covers `classify`, and specifically the `corroborating` outcome:
a citation to a page that genuinely supports the answer but is not the passage
the key chose as canonical. The whole point of the category is that it is
counted correct *without* being counted `exact`, so both halves of that need a
test — a bug that folded it into `exact` would look like an improvement.

Run: uv --directory backend run pytest \
       ../benchmarks/corpus/CSU-NSF-001/tools/test_citation_accuracy.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import json  # noqa: E402

from citation_accuracy import (  # noqa: E402
    FAILURE_OUTCOMES,
    classify,
    doc_for,
    main,
    page_pairs,
    refuse_merged,
)

KEYS_DIR = Path(__file__).parent.parent


class TestMergedRowsAreRefused:
    """A composite run paginates 1..N across the whole packet.

    The key's pages are per document, so scoring a merged row against them
    compares two different scales and produces a plausible-looking number that
    means nothing. The refusal is the feature: `merged` is still offered by the
    harness, and it used to be scoreable with no warning at all.
    """

    def test_a_merged_row_is_refused(self):
        assert refuse_merged([{"id": "Q001", "got": "p. 30",
                               "mode": "merged"}])

    def test_one_merged_row_condemns_the_file(self):
        """A mixed file cannot be partly scored: the totals would be a blend
        of two page scales."""
        assert refuse_merged([{"id": "Q001", "got": "p. 1", "mode": "attach"},
                              {"id": "Q002", "got": "p. 30", "mode": "merged"}])

    def test_attach_and_kb_rows_are_not_refused(self):
        assert refuse_merged([{"id": "Q001", "got": "p. 1", "mode": "attach"},
                              {"id": "Q002", "got": "p. 2", "mode": "kb"}]) is None

    def test_rows_with_no_mode_are_not_refused(self):
        """Any harness can write these rows; `mode` is the port's extra
        column, and its absence must not block scoring."""
        assert refuse_merged([{"id": "Q001", "got": "p. 1"}]) is None

    def test_the_cli_exits_non_zero_and_scores_nothing(self, tmp_path, capsys):
        raw = tmp_path / "raw_merged_default.json"
        raw.write_text(json.dumps([
            {"id": "Q001", "got": "The total is on p. 30.", "mode": "merged"}]))
        assert main(["--keys", str(KEYS_DIR), str(raw)]) == 2
        out = capsys.readouterr().out
        assert "refusing to score" in out
        assert "citations" not in out

    def test_the_cli_still_scores_an_attach_file(self, tmp_path, capsys):
        raw = tmp_path / "raw_attach_default.json"
        raw.write_text(json.dumps([
            {"id": "Q001", "got": "05_Budget_Justification.pdf, p. 1",
             "mode": "attach"}]))
        assert main(["--keys", str(KEYS_DIR), str(raw)]) == 0
        assert "citations" in capsys.readouterr().out


class TestDocumentAttribution:
    def test_names_the_document_in_the_window(self):
        assert doc_for("stated in 05_Budget_Justification.pdf ") == "05"

    def test_resolves_a_prose_title_with_no_filename(self):
        assert doc_for("as given in the Project Summary ") == "03"

    def test_returns_none_when_no_document_is_named(self):
        assert doc_for("the total is $1,184,398.51 on ") is None

    def test_picks_the_nearest_document_not_the_first_one(self):
        """A bulleted answer names several documents before the citation.

        The document a citation belongs to is the one written immediately
        before it. Scanning forward from the start of the window picks the
        earliest mention instead, which mis-attributes every citation after
        the first in a multi-document answer.
        """
        window = (
            "- 01_CSU_Synthetic_FA_Rate_Agreement.pdf (p. 1): the rate is 58.0%.\n"
            "- 05_Budget_Justification.pdf "
        )
        assert doc_for(window) == "05"

    def test_picks_the_nearest_when_the_titles_are_prose(self):
        window = "confirmed in the Project Summary and in the Budget Justification "
        assert doc_for(window) == "05"

    def test_a_filename_beats_an_earlier_prose_title(self):
        window = "unlike the Project Summary, 12_Current_Pending_PI.pdf "
        assert doc_for(window) == "12"

    def test_an_earlier_filename_loses_to_a_nearer_prose_title(self):
        window = "04_Project_Description.pdf differs; the Budget Justification "
        assert doc_for(window) == "05"

    def test_recognises_a_stem_with_no_file_extension(self):
        """Self-identifying page markers carry the document stem without the
        extension — `[05_Budget_Justification p. 2]` — and the model copies
        that form into its citation. Requiring '.pdf' scores every one of
        those as 'no document named', which is the opposite of the truth.
        """
        assert doc_for("as stated in (05_Budget_Justification ") == "05"

    def test_a_bare_stem_still_loses_to_a_nearer_mention(self):
        window = "01_CSU_Synthetic_FA_Rate_Agreement said X; 05_Budget_Justification "
        assert doc_for(window) == "05"

    def test_a_qualified_title_beats_the_generic_one_inside_it(self):
        """The split documents, and why mentions are compared by where they end.

        v0.5.0 split three documents in two, and every Co-PI title now contains
        the generic title as a substring: "the Co-PI biosketch" holds
        "biosketch", "current and pending (co-pi)" holds "current and pending".
        Comparing mentions by where they *start* hands all three to the generic
        alias — it starts later — and every Co-PI citation is scored against
        the PI's document. Ending position, with the longer alias breaking a
        tie, is what makes the qualified title win.
        """
        assert doc_for("as the Co-PI biosketch ") == "11"
        assert doc_for("in the current and pending (co-pi) ") == "13"
        assert doc_for("listed under Co-PI synergistic activities ") == "15"
        # The generic forms still resolve to the PI's document.
        assert doc_for("as the biosketch ") == "10"
        assert doc_for("in the current and pending ") == "12"
        # Two of the aliases the rename and the new document needed.
        assert doc_for("described in the mentoring plan ") == "09"
        assert doc_for("in the research infrastructure summary ") == "16"

    def test_a_plain_number_is_not_mistaken_for_a_document(self):
        """'$25,000 of' and 'FY27 rate' must not read as document stems."""
        assert doc_for("the first $25,000 of the subaward on ") is None


# Q007 as the key states it: the Project Summary is the canonical source
# for the total NSF request, and five other pages state the same figure. The
# workbook row is included on purpose — it has a null page.
Q007_SOURCES = [
    ["03_Project_Summary.pdf", 1, "Project Summary states the total request"],
]
Q007_CORROBORATING = [
    ["04_Project_Description.pdf", 2, "Section 1 restates the total NSF request"],
    ["05_Budget_Justification.pdf", 1, "Header table, total amount requested"],
    ["05_Budget_Justification.pdf", 3, "Budget Reconciliation, authoritative total"],
    ["12_Current_Pending_PI.pdf", 1, "CSU-PI-001 Pending entry"],
    ["13_Current_Pending_CoPI.pdf", 2, "CSU-COI-001 Pending entry"],
    ["CSU_NSF_001_Budget.xlsx", None, "Budget Detail TOTAL row and NSF Summary line J"],
]
PAIRS = page_pairs(Q007_SOURCES)
PAIRS_CORR = page_pairs(Q007_CORROBORATING)


class TestPagePairs:
    def test_keeps_sources_that_name_a_page(self):
        assert PAIRS == {("03", 1)}

    def test_drops_the_workbook_row_that_has_no_page(self):
        """A spreadsheet has no pagination, so its key entry carries a null
        page. Letting that through would put `("CS", None)` in the pair set:
        never matchable, but it would make the set look non-empty and would
        crash any code that sorts or compares the pages.
        """
        assert ("CS", None) not in PAIRS_CORR
        assert all(isinstance(page, int) for _, page in PAIRS_CORR)
        assert len(PAIRS_CORR) == len(Q007_CORROBORATING) - 1

    def test_an_absent_field_is_an_empty_set_not_an_error(self):
        """Questions with no corroborating pages omit the field entirely."""
        assert page_pairs(None) == set()
        assert page_pairs([]) == set()


class TestClassify:
    def test_a_corroborating_page_is_its_own_outcome(self):
        """The category #628 showed was being punished: a true citation to a
        page the canonical set does not enumerate. `05_Budget_Justification`
        p.3 states the total request; the key just picked the Project Summary.
        """
        assert classify("05", 3, PAIRS, PAIRS_CORR) == "corroborating"

    def test_a_corroborating_page_is_not_counted_exact(self):
        """Correct, but not the canonical passage. Folding it into `exact`
        would loosen the strict metric while looking like an improvement.
        """
        assert classify("05", 3, PAIRS, PAIRS_CORR) != "exact"

    def test_a_corroborating_hit_is_not_a_failure(self):
        """It is correct, so there is nothing for a human to inspect — it must
        not reach the failures list.
        """
        assert classify("05", 3, PAIRS, PAIRS_CORR) not in FAILURE_OUTCOMES

    def test_the_canonical_page_is_still_exact_when_corroborating_exists(self):
        """Adding the new set must not steal citations from the old outcome."""
        assert classify("03", 1, PAIRS, PAIRS_CORR) == "exact"

    def test_exact_wins_when_a_pair_is_in_both_sets(self):
        """The adjudication excludes duplicates, but the ladder should not
        depend on that holding: canonical is checked first either way.
        """
        assert classify("03", 1, PAIRS, PAIRS | {("03", 1)}) == "exact"

    def test_a_bare_citation_to_a_corroborating_page_is_bare_page(self):
        """No document named, so the page is all there is to go on. p.2 is a
        corroborating page only (13_Current_Pending_CoPI), and the old rule
        checked the canonical pages alone, which scored it `bare_miss`.
        """
        assert classify(None, 2, PAIRS, PAIRS_CORR) == "bare_page"

    def test_a_bare_citation_to_a_canonical_page_is_still_bare_page(self):
        assert classify(None, 1, PAIRS, PAIRS_CORR) == "bare_page"

    def test_a_bare_citation_to_no_known_page_is_still_bare_miss(self):
        """Widening the page pool must not make every bare citation correct."""
        assert classify(None, 9, PAIRS, PAIRS_CORR) == "bare_miss"
        assert "bare_miss" in FAILURE_OUTCOMES

    def test_wrong_page_survives_the_new_outcome(self):
        """Right document, a page neither set names — the marker/attribution
        failure this work is actually about.
        """
        assert classify("03", 7, PAIRS, PAIRS_CORR) == "wrong_page"

    def test_wrong_doc_survives_the_new_outcome(self):
        """A document this question cites nowhere, canonical or corroborating."""
        assert classify("08", 1, PAIRS, PAIRS_CORR) == "wrong_doc"

    def test_a_corroborating_document_on_the_wrong_page_is_wrong_doc(self):
        """`05` is corroborating, not canonical, so it is not in `src_docs` and
        a bad page there cannot be `wrong_page`. Documenting the edge rather
        than asserting it is desirable: it is what the ladder does.
        """
        assert classify("05", 9, PAIRS, PAIRS_CORR) == "wrong_doc"

    def test_an_empty_corroborating_set_reproduces_the_old_behaviour(self):
        """Questions with no corroborating pages must score exactly as before."""
        assert classify("05", 3, PAIRS, set()) == "wrong_doc"
        assert classify("03", 1, PAIRS, set()) == "exact"
        assert classify(None, 2, PAIRS, set()) == "bare_miss"
