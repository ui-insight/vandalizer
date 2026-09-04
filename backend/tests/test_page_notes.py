"""The instruction that tells a model how to cite pages.

Two defects, both measured against a live deployment on 2026-08-11.

**The notes were asymmetric.** A document with *measured* page boundaries got
"Cite the page when you quote or reference a specific passage" — conditional,
so a model answering a summary question can decide no citation is owed. A
document with *interpolated* boundaries got "Cite pages as approximate" — an
unconditional directive. The document whose page numbers are trustworthy
carried the weaker instruction. Observed rate on the 30B: the scanned document
was cited, the digital one on 1 of 3 questions.

**The hedge was ignored outright.** Five runs at temperature 0, cleared context,
against a document whose page markers are 100% interpolated: all five stripped
the tilde and wrote "explicitly stated in the budget summary table on page 1".
The note said to cite approximately; the model asserted exactness instead. That
is the failure that matters — an estimated page boundary reaching the reader as
measured fact, with nothing on screen to distinguish the two.

These tests pin the shape of the instruction. They cannot make a model obey it;
`~/vandalizer-workflow/harness/run_matrix.py` measures whether it did.
"""

from app.services.chat_service import page_note_for


# Measured fixtures use irregular offsets: real pages never have identical
# character counts, and perfectly uniform spacing is the interpolator's
# signature — with_marker_provenance would (correctly) hedge a uniform list.
_MEASURED_OFFSETS = [0, 1893, 3121, 5210, 6890, 9012]


def _pages(*, approximate: bool = False, count: int = 3):
    return [
        {"kind": "page", "value": n,
         "char_offset": n * 100 if approximate else _MEASURED_OFFSETS[n - 1],
         **({"approximate": True} if approximate else {})}
        for n in range(1, count + 1)
    ]


class TestNoNote:
    """Promising citations the model cannot make is worse than saying nothing."""

    def test_no_markers_at_all(self):
        assert page_note_for(None, annotated=True) == ""
        assert page_note_for([], annotated=True) == ""

    def test_markers_that_did_not_annotate_anything(self):
        # Offsets outside the text, or a format that carries no pages.
        assert page_note_for(_pages(), annotated=False) == ""

    def test_non_page_markers_do_not_earn_a_note(self):
        markers = [{"kind": "section", "value": "H", "char_offset": 10}]
        assert page_note_for(markers, annotated=True) == ""


class TestMeasuredPages:
    def test_explains_the_marker_syntax(self):
        note = page_note_for(_pages(), annotated=True)
        assert "[p. N]" in note

    def test_directs_citation_rather_than_permitting_it(self):
        """The defect: 'cite when you quote' let summary answers off the hook.

        A model deciding whether a citation is owed will often decide it is
        not, so the instruction must not offer the choice.
        """
        note = page_note_for(_pages(), annotated=True).lower()
        assert "when you quote" not in note
        assert "cite the page for every" in note

    def test_does_not_tell_the_model_to_hedge(self):
        note = page_note_for(_pages(), annotated=True)
        assert "~" not in note
        assert "approximate" not in note.lower()


class TestInterpolatedPages:
    def test_explains_the_tilde(self):
        note = page_note_for(_pages(approximate=True), annotated=True)
        assert "[p. ~N]" in note

    def test_directs_approximate_citation(self):
        note = page_note_for(_pages(approximate=True), annotated=True).lower()
        assert "around p." in note

    def test_forbids_asserting_exactness(self):
        """Aimed squarely at the observed failure.

        The 30B did not merely omit the tilde — it wrote "explicitly stated …
        on page 1". Telling it what to do left room to also do that, so the
        note now rules it out by name.
        """
        note = page_note_for(_pages(approximate=True), annotated=True).lower()
        assert "never" in note
        assert "explicitly" in note

    def test_says_why_so_the_instruction_is_not_arbitrary(self):
        note = page_note_for(_pages(approximate=True), annotated=True).lower()
        assert "scan" in note or "estimat" in note


class TestMixedMarkers:
    def test_a_single_approximate_marker_makes_the_whole_document_approximate(self):
        """Interpolation anywhere means any page number could be off. The
        cautious note has to win, or the answer inherits the wrong confidence."""
        markers = _pages() + [
            {"kind": "page", "value": 4, "char_offset": 400, "approximate": True}
        ]
        note = page_note_for(markers, annotated=True)
        assert "[p. ~N]" in note

    def test_pre_flag_uniform_markers_are_detected_and_hedged(self):
        """`approximate` is absent on documents ingested before it was added.

        The interpolator has always placed page N at exactly N * step, so
        uniform spacing across >= 3 markers is its signature — the NOAA
        proposal's 79 evenly-spread pre-flag markers now hedge instead of
        rendering confident exact pages (the false-negative source the
        previous version of this test documented as accepted).
        """
        legacy = [
            {"kind": "page", "value": n, "char_offset": n * 100}
            for n in range(1, 6)
        ]
        note = page_note_for(legacy, annotated=True)
        assert "[p. ~N]" in note

    def test_pre_flag_irregular_markers_still_read_as_measured(self):
        """Non-uniform offsets are what real measured boundaries look like;
        absence of the flag on those keeps reading as measured."""
        note = page_note_for(_pages(), annotated=True)
        assert "[p. N]" in note and "~" not in note
