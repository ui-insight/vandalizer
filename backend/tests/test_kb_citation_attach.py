"""An uncited claim in a knowledge-base answer is given the passage that
holds it, when one section holds it outright (kb_citation_attach)."""

from app.services import kb_citation_attach as A

POOL = [
    {"ref": 1, "label": "Subpart E—Cost Principles · § 200.421 · part 3", "chunk_id": "c1",
     "content": "(e) Unallowable advertising and public relations costs include the following: (1) All advertising "
                "and public relations costs other than as specified in paragraphs (b) and (d); (3) Costs of promotional "
                "items and memorabilia, including models, gifts, and souvenirs;"},
    {"ref": 2, "label": "Subpart E—Cost Principles · § 200.475 · part 2", "chunk_id": "c2",
     "content": "(e) Commercial air travel. (1) Airfare costs in excess of the basic least expensive unrestricted "
                "accommodations class offered by commercial airlines are unallowable except when such accommodations "
                "would require circuitous routing, require travel during unreasonable hours, or excessively prolong "
                "travel. The recipient must justify and document these conditions."},
    {"ref": 3, "label": "Subpart E—Cost Principles · § 200.475 · part 3", "chunk_id": "c3",
     "content": "(2) Unless a pattern of avoidance is detected, the Federal Government will generally not question a "
                "recipient's determinations that customary standard airfare or other discount airfare is unavailable."},
]


def test_an_uncited_claim_gets_the_passage_that_holds_it():
    text, rec = A.attach_citations("- Costs of promotional items and memorabilia, including gifts and souvenirs, "
                                   "are unallowable public relations costs.", POOL)
    assert text.endswith("are unallowable public relations costs [Source: Subpart E—Cost Principles · § 200.421 · part 3].")
    assert rec["attached"][0]["ref"] == 1 and rec["claims"] == 1 and rec["changed"] is True


def test_a_sentence_that_already_cites_is_left_alone():
    answer = "Promotional items and memorabilia are unallowable [Source: Subpart E—Cost Principles · § 200.421 · part 3]."
    text, rec = A.attach_citations(answer, POOL)
    assert text == answer and rec["claims"] == 0 and rec["changed"] is False


def test_a_claim_several_sections_hold_about_equally_is_not_attached():
    pool = POOL + [{"ref": 4, "label": "Subpart D · § 200.318 · part 1", "chunk_id": "c4",
                    "content": "Costs of promotional items and memorabilia, including gifts and souvenirs, are "
                               "unallowable public relations costs under the procurement standards."}]
    text, rec = A.attach_citations("- Costs of promotional items and memorabilia, including gifts and souvenirs, "
                                   "are unallowable public relations costs.", pool)
    assert "[Source:" not in text and rec["ambiguous"] == 1


def test_two_passages_of_the_same_section_are_one_citation():
    answer = ("Airfare above the basic least expensive unrestricted accommodations class is unallowable unless it "
              "would require circuitous routing or excessively prolong travel.")
    text, rec = A.attach_citations(answer, POOL)
    assert text.endswith("[Source: Subpart E—Cost Principles · § 200.475 · part 2].")
    assert rec["attached"][0]["ref"] == 2


def test_a_thin_match_stays_uncited_under_the_bar():
    text, rec = A.attach_citations("The recipient must justify airfare choices carefully every time.", POOL)
    assert "[Source:" not in text


def test_headings_questions_negatives_and_summaries_are_skipped():
    answer = ("**Advertising costs:**\nIs business class allowable?\nThe passages do not state a per diem for "
              "memorabilia purchases.\nIn short, promotional items and memorabilia including gifts and souvenirs "
              "are unallowable public relations costs.")
    text, rec = A.attach_citations(answer, POOL)
    assert text == answer and rec["claims"] == 0


def test_the_step_is_off_unless_chat_config_turns_it_on():
    assert A.config(None) is None and A.config({"chat_config": {}}) is None
    cfg = A.config({"chat_config": {"kb_citation_attach_enabled": True, "kb_citation_attach_min_share": "0.8"}})
    assert cfg == {"min_share": 0.8, "anchored_min_share": A.ANCHORED_MIN_SHARE, "margin": A.MARGIN}


def test_section_of_drops_the_part():
    assert A.section_of("Subpart E—Cost Principles · § 200.475 · part 3") == "subpart e—cost principles · § 200.475"
