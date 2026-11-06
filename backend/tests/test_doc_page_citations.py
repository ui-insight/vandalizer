"""An attached-document answer's page references are pointed at the pages
that hold what they cite, and its uncited claims are given their pages —
the off-by-one pages and page-less claims the 2026-11-02 attached-document
eval counted (one cited claim in ten on the wrong page, two claims in five
with no page)."""

from types import SimpleNamespace

from app.services import chat_service
from app.services import doc_page_citations as P

PAGES = [
    "Award notice. Project title: Deep vent ecology. Award number 2316126.\n",
    "Reporting. The annual report must include an estimate of the unobligated funds expected to remain at "
    "the end of the period. If that estimate exceeds 20% of the current-year award, the PI must obtain "
    "NSF EPSCoR approval to carry the funds forward.\n",
    "Budget. International travel: $16,500. Participant support: $4,000.\n",
    "Terms. Letters of commitment are due Oct 5, 2026. Cost sharing is not required.\n",
]


def _doc(pages=PAGES, *, uuid="d1", title="award.pdf", approximate=False, marked=True):
    raw, markers, offset = "", [], 0
    for n, text in enumerate(pages, 1):
        markers.append({"kind": "page", "value": n, "char_offset": offset, "approximate": approximate})
        raw += text
        offset += len(text)
    return SimpleNamespace(uuid=uuid, title=title, raw_text=raw, text_markers=markers if marked else None)


def _fix(answer, docs=None, **kw):
    return P.repair_page_citations(answer, docs if docs is not None else [_doc()], **kw)


# ------------------------------------------------------------------ re-point

def test_a_reference_to_the_page_after_the_text_is_pointed_back_at_the_pages_text():
    text, rec = _fix("- The PI must obtain NSF EPSCoR approval to carry the funds forward (p. 3).")
    assert text == "- The PI must obtain NSF EPSCoR approval to carry the funds forward (p. 2)."
    assert rec["repointed"] == [{"from": 3, "to": 2, "doc": "award.pdf"}] and rec["changed"] is True
    assert rec["refs"] == 1 and rec["checked"] == 1 and rec["kept"] == 0


def test_a_reference_whose_page_holds_the_claim_is_kept():
    answer = "International travel is budgeted at $16,500 (p. 3)."
    text, rec = _fix(answer)
    assert text == answer and rec["kept"] == 1 and rec["repointed"] == [] and rec["changed"] is False


def test_a_figure_decides_over_shared_words():
    """Page 2 and page 4 both talk about the award; only page 3 states $4,000."""
    text, rec = _fix("Participant support for the award is $4,000 [p. 1].")
    assert text == "Participant support for the award is $4,000 [p. 3]."


def test_a_far_page_is_found_when_no_neighbour_holds_the_claim():
    text, _rec = _fix("Letters of commitment are due Oct 5, 2026 (p. 1).")
    assert "(p. 4)" in text


def test_a_claim_no_page_holds_keeps_its_reference():
    answer = "The award caps subawards at $250,000 (p. 2)."
    text, rec = _fix(answer)
    assert text == answer and rec["unresolved"] == 1


def test_a_claim_on_several_pages_is_not_moved_between_them():
    # (page lengths differ: equal lengths read as interpolated markers)
    doc = _doc(["Cost sharing is not required for this program.\n", "Cost sharing is not required for this program. Yes.\n",
                "Cost sharing is not required for this program. Indeed so.\n"])
    answer = "Cost sharing is not required for this program (p. 9)."
    text, rec = _fix(answer, [doc])
    # p. 9 does not exist; three pages pass equally well, so nothing wins.
    assert text == answer and rec["unresolved"] == 1


def test_the_best_page_wins_when_others_hold_only_part_of_the_claim():
    doc = _doc(["Cost sharing is not required for this program.\n", "Reminder: cost sharing is not required.\n",
                "Cost sharing is not required, as stated.\n"])
    text, _rec = _fix("Cost sharing is not required for this program (p. 9).", [doc])
    assert "(p. 1)" in text


def test_a_page_that_shares_only_the_claims_figure_does_not_win():
    """"50%" is on a page about capital-cost targets too; the words are not."""
    doc = _doc(["Cost share. A demonstration phase requires at least 50% cost share from the recipient.\n",
                "Targets. To reach the 2030 goal the industry must cut capital cost by 50% through better materials.\n"])
    answer = "A demonstration phase requires 50 % cost share from the recipient (p. 3)."
    text, rec = _fix(answer, [doc])
    assert "(p. 1)" in text  # the page with the words wins over the one with the figure alone
    # The page the answer cited is judged as the chips judge it: the figure there is enough to keep it.
    kept = "A demonstration phase requires 50 % cost share from the recipient (p. 2)."
    assert _fix(kept, [doc])[0] == kept
    doc2 = _doc(["Cost share. A demonstration phase is described here in general terms.\n",
                 "Targets. To reach the 2030 goal the industry must cut capital cost by 50% through better materials.\n"])
    answer2 = "A demonstration phase requires 50 % cost share from the recipient (p. 3)."
    text2, rec2 = _fix(answer2, [doc2])
    assert text2 == answer2 and rec2["unresolved"] == 1


def test_references_cited_side_by_side_are_left_alone():
    docs = [_doc(uuid="a", title="a.pdf"), _doc(uuid="b", title="b.pdf")]
    answer = "Travel is $16,500 against a $4,000 participant line (a.pdf, p. 3) (b.pdf, p. 1)."
    text, rec = _fix(answer, docs)
    assert text == answer and rec["alongside"] == 2


def test_a_bare_reference_with_several_documents_attached_is_not_touched():
    docs = [_doc(uuid="a", title="a.pdf"), _doc(uuid="b", title="b.pdf")]
    answer = "The PI must obtain NSF EPSCoR approval (p. 3)."
    text, rec = _fix(answer, docs)
    assert text == answer and rec["unattributed"] == 1


def test_a_named_reference_is_re_pointed_within_its_own_document():
    other = _doc(["Nothing here.\n", "Nor here.\n", "Nor here either.\n"], uuid="b", title="notice.pdf")
    text, rec = _fix("The PI must obtain NSF EPSCoR approval to carry the funds forward (award.pdf, p. 3).",
                     [_doc(), other])
    assert "(award.pdf, p. 2)" in text and rec["repointed"][0]["doc"] == "award.pdf"


def test_a_scanned_document_is_left_as_it_is():
    answer = "The PI must obtain NSF EPSCoR approval to carry the funds forward (p. ~3)."
    text, rec = _fix(answer, [_doc(approximate=True)])
    assert text == answer and rec["refs"] == 0


def test_a_reference_that_carries_nothing_to_check_is_kept():
    answer = "See p. 3."
    text, rec = _fix(answer)
    assert text == answer and rec["checked"] == 0


def test_the_pages_form_and_hedge_survive_the_edit():
    text, _rec = _fix("The PI must obtain NSF EPSCoR approval to carry the funds forward (see page 3).")
    assert "(see page 2)" in text


# -------------------------------------------------------------------- attach

def test_an_uncited_claim_is_given_the_page_that_holds_it():
    text, rec = _fix("- International travel is budgeted at **$16,500**.\n- The PI must obtain NSF EPSCoR approval "
                     "to carry the funds forward.")
    assert text == ("- International travel is budgeted at **$16,500** (p. 3).\n- The PI must obtain NSF EPSCoR "
                    "approval to carry the funds forward (p. 2).")
    assert [a["page"] for a in rec["attached"]] == [3, 2] and rec["considered"] == 2


def test_a_claim_that_several_pages_hold_about_equally_gets_no_page():
    doc = _doc(["The award supports deep vent ecology research at sea.\n",
                "Deep vent ecology research at sea is what the award supports.\n"])
    answer = "The award supports deep vent ecology research at sea."
    text, rec = _fix(answer, [doc])
    assert text == answer and rec["attached"] == [] and rec["considered"] == 1


def test_a_sentence_about_what_the_document_does_not_say_is_not_cited():
    answer = "The notice does not state a cost-sharing percentage for the unobligated funds estimate."
    text, rec = _fix(answer)
    assert text == answer and rec["considered"] == 0


def test_headings_questions_summaries_and_thin_sentences_are_not_cited():
    answer = ("## Reporting\n**Key points:**\nIs approval needed for the unobligated funds?\n"
              "In short, the unobligated funds estimate drives the approval.\nApproval needed.\n"
              "Conclusion: the PI must obtain NSF EPSCoR approval to carry the funds forward.\n")
    text, rec = _fix(answer)
    assert text == answer and rec["attached"] == []


def test_a_sentence_that_names_its_pages_in_words_is_not_cited_again():
    answer = "International travel is budgeted at $16,500 (pages 3-4)."
    text, rec = _fix(answer)
    assert text == answer and rec["attached"] == []


def test_a_table_row_gets_its_page_inside_the_last_cell():
    text, _rec = _fix("| Line | Amount |\n|---|---|\n| International travel budgeted | $16,500 |\n")
    assert text == "| Line | Amount |\n|---|---|\n| International travel budgeted | $16,500 (p. 3) |\n"


def test_with_several_documents_the_attached_page_names_its_file():
    other = _doc(["Sponsor notice. Proposals are due Dec 1, 2026.\n"], uuid="b", title="notice.pdf")
    text, _rec = _fix("Proposals are due Dec 1, 2026.", [_doc(), other])
    assert text == "Proposals are due Dec 1, 2026 (notice.pdf, p. 1)."


def test_attaching_can_be_turned_off_on_its_own():
    text, rec = _fix("International travel is budgeted at $16,500.", attach=False)
    assert text == "International travel is budgeted at $16,500." and rec["attached"] == []


def test_running_it_twice_changes_nothing_more():
    once, _ = _fix("- International travel is budgeted at $16,500.\n- The PI must obtain NSF EPSCoR approval "
                   "to carry the funds forward (p. 3).")
    twice, rec = _fix(once)
    assert twice == once and rec["changed"] is False


def test_an_answer_with_no_marked_document_comes_back_untouched():
    answer = "International travel is budgeted at $16,500 (p. 3)."
    assert _fix(answer, [_doc(marked=False)]) == (answer, {**_fix(answer, [_doc(marked=False)])[1]})
    text, rec = _fix(answer, [])
    assert text == answer and rec["changed"] is False


# ------------------------------------------------------------------ settings

def test_the_step_is_off_unless_chat_config_turns_it_on():
    assert P.repair_config(None) is None
    assert P.repair_config({"chat_config": {}}) is None
    assert P.repair_config({"chat_config": {"doc_page_citation_repair_enabled": True}}) == {"attach": True}
    assert P.repair_config({"chat_config": {"doc_page_citation_repair_enabled": True,
                                            "doc_page_citation_attach_enabled": False}}) == {"attach": False}


def test_chat_runs_the_step_only_when_on_and_keeps_the_answer_when_it_raises(monkeypatch):
    on = {"chat_config": {"doc_page_citation_repair_enabled": True}}
    answer = "The PI must obtain NSF EPSCoR approval to carry the funds forward (p. 3)."
    assert chat_service._repair_page_citations(answer, [_doc()], {}) == (answer, None)
    assert chat_service._repair_page_citations(" ", [_doc()], on) == (" ", None)
    text, rec = chat_service._repair_page_citations(answer, [_doc()], on)
    assert "(p. 2)" in text and rec["changed"] is True

    def boom(*a, **kw):
        raise RuntimeError("bug")

    monkeypatch.setattr(P, "repair_page_citations", boom)
    assert chat_service._repair_page_citations(answer, [_doc()], on) == (answer, None)


def test_a_name_with_an_initial_gets_its_page_after_the_name_not_inside_it():
    doc = _doc(["Award notice. Project title: Deep vent ecology.\n",
                "NSF contacts. Managing Grants Official: Marcus T. Hollowell, phone (703) 292-8101, "
                "mhollowell@nsf.gov.\n",
                "Budget. I. Indirect Costs: $393,333 on modified total direct costs.\n"])
    text, rec = _fix("- Grants contact: Marcus T. Hollowell, phone (703) 292-8101.\n"
                     "- Line I. Indirect Costs is $393,333.", [doc])
    assert text == ("- Grants contact: Marcus T. Hollowell, phone (703) 292-8101 (p. 2).\n"
                    "- Line I. Indirect Costs is $393,333 (p. 3).")
    assert [a["page"] for a in rec["attached"]] == [2, 3]
