"""A knowledge-base chunk that holds only items of a list is read with the
sentence earlier in its section that says what the list is — the lead-in a
chat answer once missed, reading § 200.308(f)'s prior-approval list as
things allowed without approval."""

import pytest

from app.services import chat_service, kb_grounding
from app.services.kb_lead_in import attach_lead_ins, lead_in, with_lead_in

SOURCE = "Subpart D—Post Federal Award Requirements"

LEAD_F = (
    "(f) Revisions Requiring Prior Approval. A recipient or subrecipient must request prior written approval "
    "from the Federal agency or pass-through entity for the following program and budget-related reasons:"
)
PART_3 = (
    "(e) Limitation on other prior approval requirements. Unless specified in this guidance, the Federal agency "
    "must not impose additional prior approval requirements without OMB approval.\n"
    f"{LEAD_F}\n"
    "(1) Change in the scope or the objective of the project or program.\n"
    "(2) Change in key personnel that are identified by name or position in the Federal award.\n"
    "(3) The disengagement from a project for more than three months."
)
PART_4 = (
    "(4) The inclusion, unless waived by the Federal agency, of costs that require prior approval.\n"
    "(5) The transfer of funds budgeted for participant support costs to other budget categories."
)
LEAD_G = (
    "(g) Waiver of certain prior approvals. Except for the requirements listed in paragraphs (f)(1) through (10), "
    "the Federal agency is authorized to waive other cost-related and administrative prior written approval "
    "requirements contained in subparts D and E. Such waivers may include authorizing recipients to do one or "
    "more of the following:"
)
PART_8 = (
    "(2) One-time extensions. Initiate a one-time extension of the period of performance by up to 12 months. "
    "One-time extensions require prior approval from the Federal agency when:"
)
PART_9 = (
    "(i) The terms and conditions of the Federal award prohibit the extension;\n"
    "(ii) The extension requires additional Federal funds; or\n"
    "(iii) The extension involves any change in the approved scope of the project.\n"
    "(3) Unobligated Balances. Carry forward unobligated balances to subsequent budget periods.\n"
    "(h) Prior approvals for research awards. The prior approval requirements are automatically waived."
)


def _chunk(n: int, part: int, content: str, key: str = "200.308") -> dict:
    return {
        "content": content,
        "metadata": {"source_name": SOURCE, "source_id": "src", "section_key": key,
                     "section_part": part, "section_parts": 10},
        "chunk_id": f"src_chunk_{n}",
    }


class FakeDM:
    def __init__(self, chunks):
        self.by_id = {c["chunk_id"]: c for c in chunks}
        self.calls = 0

    def get_kb_chunks_by_ids(self, kb_uuid, ids):
        self.calls += 1
        return [self.by_id[i] for i in ids if i in self.by_id]


SECTION = [
    _chunk(33, 1, "§ 200.308 Revision of budget and program plans.\n(a) Approved budget in general. The approved budget."),
    _chunk(34, 2, "(c) Requesting approval for budget revisions. The recipient must use the same format."),
    _chunk(35, 3, PART_3),
    _chunk(36, 4, PART_4),
    _chunk(37, 5, "(8) The need arises for additional Federal funds.\n(9) Transferring funds between construction."),
    _chunk(38, 6, LEAD_G),
    _chunk(39, 7, "(1) Pre-award costs. Incur project costs 90 calendar days before the Federal award date."),
    _chunk(40, 8, PART_8),
    _chunk(41, 9, PART_9),
    _chunk(42, 10, "(i) Transfer of funds. The Federal agency must not permit a transfer of funds that would cause."),
]


def _lead(n: int) -> str | None:
    passage = dict(next(c for c in SECTION if c["chunk_id"] == f"src_chunk_{n}"))
    attach_lead_ins(FakeDM(SECTION), "kb", [passage])
    return passage.get("lead_in")


class TestLeadIn:
    def test_a_later_item_of_the_prior_approval_list_gets_its_lead_in(self):
        assert _lead(36) == LEAD_F
        assert _lead(37) == LEAD_F

    def test_the_first_item_of_a_list_gets_the_line_right_above_it(self):
        assert _lead(39).startswith("(g) Waiver of certain prior approvals.")

    def test_a_nested_list_gets_its_own_lead_in_and_its_parents(self):
        lead = _lead(41)
        assert lead.split("\n")[0].startswith("(g) Waiver of certain prior approvals.")
        assert lead.split("\n")[1].endswith("One-time extensions require prior approval from the Federal agency when:")

    def test_a_long_lead_in_keeps_its_opening_and_the_sentence_with_the_colon(self):
        lead = _lead(39)
        assert " … " in lead and lead.endswith("one or more of the following:")
        assert len(lead) < len(LEAD_G)

    def test_a_lettered_paragraph_after_h_is_not_read_as_a_roman_numeral(self):
        assert _lead(42) is None

    def test_a_chunk_that_opens_with_a_paragraph_of_the_section_gets_none(self):
        # "(c)" sits under the section heading, which is no lead-in.
        assert _lead(34) is None
        assert _lead(35) is None

    def test_the_first_part_of_a_section_and_a_section_passage_read_nothing(self):
        dm = FakeDM(SECTION)
        first = dict(SECTION[0])
        section = {**SECTION[3], "_section": "200.308"}
        attach_lead_ins(dm, "kb", [first, section])
        assert dm.calls == 0 and "lead_in" not in first and "lead_in" not in section

    def test_a_chunk_of_another_section_is_not_read(self):
        other = [_chunk(35, 3, PART_3, key="200.307"), _chunk(36, 4, PART_4)]
        passage = dict(other[1])
        attach_lead_ins(FakeDM(other), "kb", [passage])
        assert "lead_in" not in passage

    def test_a_failed_read_leaves_the_passage_as_it_was(self):
        class Broken:
            def get_kb_chunks_by_ids(self, kb_uuid, ids):
                raise RuntimeError("chroma down")

        passage = dict(SECTION[3])
        attach_lead_ins(Broken(), "kb", [passage])
        assert "lead_in" not in passage

    def test_the_store_is_opened_only_when_a_passage_needs_it(self):
        opened = []
        attach_lead_ins(lambda: opened.append(1), "kb", [dict(SECTION[0])])
        assert opened == []
        passage = dict(SECTION[3])
        attach_lead_ins(lambda: FakeDM(SECTION), "kb", [passage])
        assert passage["lead_in"] == LEAD_F


class TestListShapes:
    def test_an_item_inside_a_numbered_parent_with_no_words_gets_none(self):
        before = (
            "(5)(i) Time logs are not required for lobbying costs during a calendar month when:\n"
            "(A) The employee engages in lobbying 25 percent or less of the compensated hours; and\n"
            "(B) Within the preceding five-year period, the organization has not materially misstated time.\n"
            "(ii) When conditions are met, the organization is not required to establish records."
        )
        assert lead_in(before, "(iii) In consultation with OMB, the Federal agency must establish procedures.") is None

    def test_a_policy_sub_heading_belongs_to_its_letter_not_to_the_next(self):
        before = (
            "E. Procedure.\nE-3. Financial set-up. After the award is executed the following steps will be completed:\n"
            "- An account is created.\n- The PI is notified."
        )
        assert lead_in(before, "F. Contact information. Any questions go to OSP.") is None

    def test_a_table_of_contents_above_the_body_is_another_list(self):
        before = "Contents:\nA. Definitions\nB. Policy\nC. Procedure"
        assert lead_in(before, "A. Definitions.\nA-1. Prize Competition. Any competition.") is None

    def test_bullets_under_a_colon_line(self):
        before = "Examples of program income include:\n- Fees for services performed;"
        assert lead_in(before, "- Sale of software, tapes or publications,") == "Examples of program income include:"

    def test_a_lead_in_must_introduce_what_follows(self):
        before = "(a) Title. Title to equipment vests in the recipient.\n(1) Use the equipment for the project."
        assert lead_in(before, "(2) While the equipment is used, the recipient must not encumber it.") is None


def test_rendered_passages_carry_the_lead_in_above_the_chunk():
    passage = {**SECTION[3], "lead_in": LEAD_F}
    text, sources = kb_grounding.render_passages([passage], queries=["participant support"])
    assert f"[Lead-in, earlier in this section: {LEAD_F}]\n(4) The inclusion" in text
    assert sources[0]["lead_in"] == LEAD_F
    assert sources[0]["content"] == PART_4
    assert with_lead_in(PART_4, None) == PART_4


@pytest.mark.asyncio
async def test_chat_shows_the_model_the_lead_in_and_keeps_it_for_the_popover(monkeypatch):
    async def none(*a, **k):
        return {}

    monkeypatch.setattr("app.services.knowledge_service.resolve_openable_documents", none)
    passage = {**SECTION[3], "lead_in": LEAD_F}
    segment, sources = await chat_service._render_kb_segment([passage], "participant support to travel?")
    assert f"[Lead-in, earlier in this section: {LEAD_F}]\n(4) The inclusion" in segment.text
    assert sources[0]["lead_in"] == LEAD_F
    assert sources[0]["content"] == PART_4
