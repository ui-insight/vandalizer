"""A knowledge-base chat turn with no evidence refuses instead of recalling
(app.services.kb_no_evidence). The answers below are the shapes the Phase 1
eval (2026-10-23) saw when retrieval returned nothing, and the shapes a
legitimate no-evidence turn takes."""

from app.services import kb_no_evidence as ne

STATUS = (
    "## Attached knowledge bases: current status\n"
    "- **Export Control**: 2 of 3 sources ready; 1 not searchable: DDTC (HTTP 404). Never validated."
)
MANIFEST = "\n\n## Project Document Manifest\n- PART 734—SCOPE OF THE EXPORT ADMINISTRATION REGULATIONS\n"
UG = ("## Attached knowledge bases: current status\n- **OMB Uniform Guidance (2 CFR 200)**: 8 of 9 sources ready.\n"
      "## Project Document Manifest\n- Subpart D—Post Federal Award Requirements\n- Subpart E—Cost Principles\n")
UI = ("## Attached knowledge bases: current status\n- **University of Idaho Office of Sponsored Programs**: 26 of 26 "
      "sources ready.\n## Project Document Manifest\n- APM 45.14 Sponsored Projects Changes Requiring Prior Approval"
      " | University of Idaho\n")
NSFAC = "## Attached knowledge bases: current status\n- **NSF Award Conditions**: 0 of 3 sources ready."
RCR = ("## Attached knowledge bases: current status\n- **Responsible Conduct of Research (RCR)**: 3 of 3 sources "
       "ready.\n## Project Document Manifest\n- 42 CFR Part 93—Public Health Service Policies on Research Misconduct\n")


def leaks(answer, message="Is there a time limit on research misconduct allegations?", carried=()):
    return ne.leaked_statements(answer, message=message, carried=list(carried))


class TestAnswersFromMemoryLeak:
    def test_a_rule_from_memory(self):
        assert leaks("No. Research misconduct allegations have no strict time limit, and institutions "
                     "follow their own policies.")

    def test_a_figure_from_memory(self):
        assert leaks("The equipment threshold is $5,000 per unit.", message="What is the equipment threshold?")

    def test_a_period_from_memory(self):
        assert leaks("Final reports are due within 120 calendar days of the end date.",
                     message="When is the final report due?")

    def test_a_procedure_without_rule_words(self):
        # "PI signs, ORED acceptance officer accepts": a procedure from memory
        # with no figure and no modal verb.
        assert leaks("The PI signs the proposal and the ORED acceptance officer accepts the award on "
                     "behalf of the university.", message="Who signs a proposal at UI?")

    def test_absence_report_followed_by_general_knowledge(self):
        assert leaks("The knowledge base doesn't say, but generally NSF requires prior approval for "
                     "foreign travel.", message="Does foreign travel need prior approval?")

    def test_a_rule_hidden_after_a_report(self):
        assert leaks("Nothing was found in the knowledge base; you must obtain prior approval from the "
                     "program officer.", message="Does foreign travel need prior approval?")

    def test_a_rule_stated_as_not_included(self):
        # A negation without a source word is a rule, not a report of absence.
        assert leaks("Participant support costs are not included in the MTDC base.",
                     message="Are participant support costs in MTDC?")

    def test_a_suggestion_that_states_the_rule(self):
        assert leaks("Check § 200.308, which requires prior approval for budget changes.",
                     message="Do budget changes need approval?")

    def test_beyond_the_sources_label_does_not_excuse(self):
        assert leaks("_Beyond the retrieved sources:_ institutions commonly cap cost sharing at the "
                     "amount the sponsor requires.", message="Is cost sharing capped?")


class TestRefusalsAndCarriedTextPass:
    def test_a_clean_not_found(self):
        assert not leaks("I couldn't find anything about misconduct time limits in the knowledge base "
                         "“Research Integrity”. Try asking with the section number or the regulation's "
                         "own wording.")

    def test_not_covered_with_a_source_word(self):
        assert not leaks("The knowledge base does not state whether prior approval is required for "
                         "foreign travel.", message="Does foreign travel need prior approval?")

    def test_suggestions_with_a_conditional_lead(self):
        assert not leaks("If you’re referring to a particular University of Idaho document (e.g., an APM "
                         "policy), mention the exact document title or upload the file and try again.",
                         carried=[UI])

    def test_what_the_source_list_holds(self):
        assert not ne.leaked_statements(
            "The Export Control knowledge base holds Part 734 (scope of the Export Administration "
            "Regulations) and does not include ITAR.",
            message="What does ITAR say about defense articles?", carried=[STATUS, MANIFEST],
        )

    def test_reshaping_an_earlier_answer(self):
        earlier = ("Prior written approval is required for: (1) a change in the scope or objective of the "
                   "project; (2) a change in a key person specified in the application.")
        assert not ne.leaked_statements(
            "| Change | Prior approval |\n|---|---|\n| Scope or objective of the project | Required |\n"
            "| Key person specified in the application | Required |\n\n"
            "Prior written approval is required for a change in the scope or objective of the project, "
            "and for a change in a key person specified in the application.",
            message="Put that in a table", carried=[earlier],
        )

    def test_a_reshaped_answer_cannot_add_a_figure(self):
        assert ne.leaked_statements(
            "Equipment threshold: $5,000.", message="Make that shorter",
            carried=["Equipment means property with a per-unit acquisition cost of $10,000 or more."],
        )

    def test_drafting_from_the_conversation(self):
        assert not ne.leaked_statements(
            "Subject: Proposal budget\n\nHi Dr. Lee,\n\nCould we meet next week to go over the proposal "
            "budget? I'd like to walk through the personnel lines before routing.\n\nThanks,\nSam",
            message="Draft a short email to my department chair asking to meet about the proposal budget.",
        )

    def test_drafting_cannot_add_a_rule_or_figure(self):
        assert ne.leaked_statements(
            "Hi Dr. Lee, equipment is property costing $10,000 or more per unit, so the centrifuge "
            "must be budgeted as equipment.",
            message="Write a note to the PI explaining the equipment threshold.",
        )

    def test_greetings_and_short_lines(self):
        assert not leaks("You're welcome!", message="thanks")
        assert not leaks("Sure, here it is:", message="Show me again")


class TestModelRefusalsPass:
    """Refusals the model wrote under the new rules on the eval's questions
    (2026-10-24), which an earlier version of the check replaced."""

    def test_reports_of_what_was_not_found(self):
        cases = [
            ("Someone just alleged that one of our NIH-funded faculty fabricated data in a paper published eight "
             "years ago. Is that too old to pursue?",
             "I’m not seeing any passages about the time limits for investigating alleged NIH research misconduct "
             "in the knowledge base."),
            ("Can we move money out of participant support costs into salaries on our NSF grant without asking "
             "NSF first?",
             "I wasn’t able to pull any passages from the knowledge base that address moving participant‑support "
             "costs into salaries on an NSF award."),
            ("Our PI will be away for four months on sabbatical. Does NSF have to approve that, and do we need to "
             "name someone to run the project while she's gone?",
             "The knowledge base is empty, so I can’t confirm the approval requirements or replacement‑PI rules "
             "from them."),
            ("Is there a federal deadline for moving an expense onto a grant after it posts, or is the 90-day "
             "window just a UI rule?",
             "I searched both knowledge bases, but none of those sources yielded a relevant excerpt for the "
             "deadline you’re asking about."),
            ("What if the summer work on the award is teaching rather than research?",
             "I searched the Uniform Guidance, but no passages were returned that address whether summer work on "
             "an award can be classified as teaching instead of research."),
            ("Who has to sign off on a proposal in the routing system before it goes out?",
             "The knowledge base did not return any passages matching that query."),
        ]
        for message, answer in cases:
            assert not leaks(answer, message=message, carried=[UG, UI, NSFAC, RCR]), answer

    def test_suggestions_and_next_steps(self):
        message = "Can that penalty be waived?"
        for answer in (
            "Referring to the specific Uniform Guidance section (e.g., the “Post‑Federal Award Requirements” "
            "subpart) or the exact policy title you want to check.",
            "Mention the specific subpart or section (e.g., “Subpart D—Post Federal Award Requirements”) you want "
            "to focus on.",
            "Using an exact phrase in quotes to force an exact‑text lookup.",
            "Confirm the file has finished indexing and then retry the query.",
            "Verifying that the relevant document has finished indexing before searching again.",
            "If you’re looking for a specific rule, try naming the exact policy (e.g., “APM 45.14 – Sponsored "
            "Projects Changes Requiring Prior Approval”) or quoting the relevant language in double‑quotes so an "
            "exact‑text search can locate it.",
            "That will let me locate the relevant wording and give you the precise answer.",
            "Once the document is identified, we can retrieve the passage and answer your question.",
            "If you need general guidance on NSF procedures, you may need to consult the official NSF website or "
            "your award officer.",
        ):
            assert not leaks(answer, message=message, carried=[UG, UI, NSFAC, RCR]), answer

    def test_second_round_phrasings(self):
        cases = [
            ("Can we move proposal-writing costs from this year's budget into next year's pool?",
             "I wasn’t able to pull any passages that address moving proposal‑writing costs from this year’s "
             "budget into next year’s pool."),
            ("Does the cost-share have to be documented?",
             "Try searching with the exact term used in the source (e.g., “cost‑share requirement”) or quote a "
             "specific sentence from the policy document"),
            ("Does the cost-share have to be documented?", "and ensure the file is fully indexed."),
            ("Does the cost-share have to be documented?",
             "If the file was just added, ensure it has finished indexing before searching again."),
            ("Does the cost-share have to be documented?", "That will help surface the specific passage you need."),
            ("Who accepts awards at UI?", "It looks like the relevant document is in the project"),
            ("Does citing the figure in the application change anything?",
             "Because nothing matched the query, I can’t tell whether the citation changes anything."),
            ("Can a five-month-old salary charge be moved?",
             "so I don’t have the specific policy wording to confirm whether a five‑month‑old salary can be moved "
             "via labor redistribution."),
            ("How do we request a no-cost extension on our NSF award, and how far before the end date?",
             "Checking the current NSF award‑conditions page directly on the NSF website for the most up‑to‑date "
             "procedure and timing requirements."),
        ]
        for message, answer in cases:
            assert not leaks(answer, message=message, carried=[UG, UI, NSFAC, RCR]), answer

    def test_a_no_answer_in_the_questions_own_words_still_leaks(self):
        assert leaks("No, participant support costs cannot be moved into salaries without NSF approval.",
                     message="Can we move money out of participant support costs into salaries on our NSF grant?",
                     carried=[NSFAC])
        assert leaks("I found nothing in the knowledge base but NSF requires prior approval for that.",
                     message="Does a sabbatical need NSF approval?", carried=[NSFAC])


class TestTaskRequests:
    def test_reshaping_and_drafting(self):
        for m in ("Put that in a table", "Could you make it shorter?", "Draft an email to the PI",
                  "please translate that to Spanish", "Summarize your answer in two bullets"):
            assert ne.is_task_request(m), m

    def test_questions_are_not_tasks(self):
        for m in ("What is the equipment threshold?", "Can you summarize the rules on equipment?",
                  "Does foreign travel need prior approval?", "Who signs proposals at UI?"):
            assert not ne.is_task_request(m), m


class TestEnforce:
    def test_a_leaking_answer_becomes_the_refusal(self):
        shown, leaked = ne.enforce(
            "The equipment threshold is $5,000.", message="What is the equipment threshold?",
            carried=[], kb_titles=["OMB Uniform Guidance"],
        )
        assert leaked
        assert shown == ne.refusal(["OMB Uniform Guidance"])
        assert "“OMB Uniform Guidance”" in shown
        assert "$5,000" not in shown
        assert "won't answer it from general knowledge" in shown

    def test_a_clean_answer_is_kept(self):
        answer = "I couldn't find this in the knowledge base. Try naming the section."
        assert ne.enforce(answer, message="What is X?", carried=[], kb_titles=["UG"]) == (answer, [])

    def test_an_empty_answer_becomes_the_refusal(self):
        shown, _ = ne.enforce("  ", message="What is X?", carried=[], kb_titles=["UG"])
        assert shown == ne.refusal(["UG"])

    def test_the_refusal_names_every_knowledge_base(self):
        assert "the knowledge bases “UG” and “UI OSP”" in ne.refusal(["UG", "UI OSP", "UG"])
        assert "their sources" in ne.refusal(["UG", "UI OSP"])
        assert "the attached knowledge base" in ne.refusal(["", ""])
        assert "its sources" in ne.refusal(["UG"])


class TestRules:
    def test_the_empty_retrieval_rules_refuse(self):
        from app.services.llm_service import PROJECT_KB_EMPTY_RULES

        assert "can still answer general questions" not in PROJECT_KB_EMPTY_RULES
        assert "Do not answer a request for information from memory or general knowledge" in PROJECT_KB_EMPTY_RULES
        assert "Do not use web_search" in PROJECT_KB_EMPTY_RULES

    def test_the_agent_tool_says_the_same(self):
        import inspect

        from app.services import chat_tools

        source = " ".join(inspect.getsource(chat_tools.search_knowledge_base).replace('"', " ").split())
        assert "Do not answer from general knowledge instead" in source
        assert "clearly label the answer" not in source


class TestEvidence:
    def test_a_knowledge_base_passage_is_evidence(self):
        assert ne.kb_evidence([{"chunk_id": "src_chunk_3", "document_title": "Part 200"}])

    def test_web_results_and_fetched_pages_are_not(self):
        assert not ne.kb_evidence([{"chunk_id": None, "url": "https://example.org"}])
        assert not ne.kb_evidence([])

    def test_titles_prefer_the_stored_ones(self):
        assert ne.kb_titles_of([{"title": "Export Control"}], [("kb-1", "")]) == ["Export Control"]
        assert ne.kb_titles_of([], [("kb-1", "Policies")]) == ["Policies"]

    def test_web_requests(self):
        assert ne.asks_for_web("Search the web for the current NIH salary cap")
        assert not ne.asks_for_web("What is the NIH salary cap?")


class TestSuggestionsThatStateRules:
    def test_a_rule_outside_the_quoted_example_leaks(self):
        assert leaks("Check with OSP since prior approval is required for that change.",
                     message="Can we rebudget into equipment?", carried=[UI])

    def test_a_suggestion_after_a_dash(self):
        assert not leaks("The relevant policy may be in a document such as the research misconduct "
                         "guidelines—try naming that document (or an exact phrase from it) and re‑ask.",
                         message="Is a fabrication allegation from eight years ago too old to pursue?",
                         carried=[RCR])
