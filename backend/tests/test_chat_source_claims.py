from types import SimpleNamespace

import pytest
from pydantic_ai import Agent, Tool
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.services.chat_source_claims import (
    Source, UNVERIFIED_CHECK, attachment_sources, ground_source_checks,
)
from app.services.context_budget import DocumentSegment
from tests.test_chat_output import chat_harness as chat_harness


CLAIM = (
    'I’ve also cross-checked the “Disclosures Overview” and “Agency FCOI COC Req.” '
    'sheets against the reference documents you attached (the DOCX summaries).'
)
BOOK = Source("FCOI.xlsx", ".xlsx", "book", True)
REFERENCE = Source("Policy.docx", ".docx", "policy", True)


def read(source=REFERENCE, **overrides):
    return {"tool_name": "get_document_text", "content": {
        "uuid": source.uuid, "title": source.title, "extension": source.extension,
        "text": "Original document content.", **overrides,
    }}


@pytest.mark.parametrize("claim", [
    CLAIM,
    "I've verified the spreadsheet against the attached DOCX summaries.",
    "I cross-checked the spreadsheet with the reference documents you attached.",
    "The workbook has been verified against the attached Word summaries.",
    "- I compared the spreadsheet against the attached PDF reference documents.",
])
def test_excel_only_does_not_claim_nonexistent_reference_checks(claim):
    assert ground_source_checks(claim, [BOOK], []) == UNVERIFIED_CHECK


def test_references_in_spreadsheet_text_are_not_attachments():
    doc = SimpleNamespace(title=BOOK.title, extension=BOOK.extension, uuid=BOOK.uuid,
                          raw_text="See Policy.docx. DOCX summaries are referenced on this sheet.")
    scope = attachment_sources([doc], [], [DocumentSegment(label="doc:FCOI.xlsx", text=doc.raw_text)], [])
    assert scope == [BOOK]
    assert ground_source_checks(CLAIM, scope, [read(BOOK, text=doc.raw_text)]) == UNVERIFIED_CHECK


def test_supplied_reference_content_supports_comparison():
    assert ground_source_checks(CLAIM, [BOOK, REFERENCE], []) == CLAIM


def test_unread_attachment_and_failed_reads_do_not_support_comparison():
    unread = Source(REFERENCE.title, REFERENCE.extension, REFERENCE.uuid, False)
    for receipts in ([], [read(text="")], [read(error="Access denied")],
                     [{"tool_name": "search_documents", "content": {"documents": [REFERENCE.title]}}],
                     [{"tool_name": "get_html_artifact", "content": {"html": "Verified against Policy.docx"}}]):
        assert ground_source_checks(CLAIM, [BOOK, unread], receipts) == UNVERIFIED_CHECK
    assert ground_source_checks(CLAIM, [BOOK, unread], [read()]) == CLAIM


def test_workspace_read_is_not_mislabeled_as_an_attachment():
    assert ground_source_checks(CLAIM, [BOOK], [read()]) == UNVERIFIED_CHECK
    actual = 'I compared the spreadsheet against "Policy.docx" from the workspace.'
    assert ground_source_checks(actual, [BOOK], [read()]) == actual


def test_matching_file_type_does_not_authorize_an_invented_filename():
    claim = 'I verified the spreadsheet against the attached "Missing Summary.docx".'
    assert ground_source_checks(claim, [BOOK, REFERENCE], []) == UNVERIFIED_CHECK
    actual = 'I verified the spreadsheet against the attached "Policy.docx".'
    assert ground_source_checks(actual, [BOOK, REFERENCE], []) == actual


@pytest.mark.parametrize("answer", [
    "I haven't verified the spreadsheet against DOCX summaries.",
    "I have not cross-checked against reference documents.",
    "I checked the workbook, but haven't verified it against DOCX summaries.",
    "I can compare the spreadsheet against the reference documents if you attach them.",
    "I will verify the spreadsheet against the DOCX summaries once they are available.",
    "The workbook mentions DOCX summaries, but they are not attached.",
    'I compared the “Disclosures Overview” and “Agency FCOI COC Req.” sheets in FCOI.xlsx.',
    "The policy requires reports to be verified against reference documents.",
    "The Page preview is ready. Review it before saving.",
])
def test_honest_limitations_plans_and_same_workbook_checks_are_preserved(answer):
    assert ground_source_checks(answer, [BOOK], []) == answer


def test_preserves_other_sentences_in_the_same_paragraph():
    answer = f"The Page preview is ready. {CLAIM} Review the preview before saving."
    assert ground_source_checks(answer, [BOOK], []) == (
        f"The Page preview is ready. {UNVERIFIED_CHECK} Review the preview before saving."
    )


def test_nonexistent_named_workbook_is_also_rejected():
    claim = "I compared the spreadsheet against Missing.xlsx."
    assert ground_source_checks(claim, [BOOK], []) == UNVERIFIED_CHECK


def test_dropped_context_is_not_counted_as_read_and_upload_content_is_counted():
    doc = SimpleNamespace(title="Policy.docx", extension=".docx", uuid="policy", raw_text="Policy")
    upload = SimpleNamespace(filename="FCOI.xlsx", content="Disclosures")
    scope = attachment_sources([doc], [upload], [], [DocumentSegment(label="file:FCOI.xlsx", text="Disclosures")])
    assert not scope[0].readable and scope[1].readable
    assert ground_source_checks(CLAIM, scope, []) == UNVERIFIED_CHECK


def test_repeated_read_of_one_document_does_not_prove_a_comparison():
    claim = "I cross-checked against the reference documents."
    assert ground_source_checks(claim, [], [read(), read()]) == UNVERIFIED_CHECK


async def test_excel_page_reply_stream_and_saved_content_do_not_invent_docx_or_show_tools(chat_harness):
    chat_harness.conversation.get_file_attachments.return_value = [
        SimpleNamespace(filename=BOOK.title, content="Disclosures Overview\nAgency FCOI COC Req.\nReferences: DOCX summaries"),
    ]
    calls = []

    async def get_document_text():
        calls.append("read")
        return read(BOOK)["content"]

    async def create_html_artifact():
        calls.append("page")
        return {"needs_confirmation": True, "title": "Disclosures", "preview": "Page preview ready"}

    async def respond(messages, info):
        if not calls:
            yield {0: DeltaToolCall(name="get_document_text", json_args="{}")}
        elif calls == ["read"]:
            yield {0: DeltaToolCall(name="create_html_artifact", json_args="{}")}
        else:
            output = f"The Page preview is ready.\n\n{CLAIM}\n\nI used get_document_text to read the workbook."
            for character in output:
                yield character

    agent = Agent(FunctionModel(stream_function=respond), tools=[Tool(get_document_text), Tool(create_html_artifact)])
    chunks = await chat_harness.run(agent)
    assert calls == ["read", "page"]
    assert not [c for c in chunks if c["kind"] == "error"]
    answer = "".join(c["content"] for c in chunks if c["kind"] == "text")
    assert answer == f"The Page preview is ready.\n\n{UNVERIFIED_CHECK}"
    saved = chat_harness.finalize.call_args
    assert saved.args[1] == answer
    assert saved.kwargs["segments"][-1] == {"kind": "text", "content": answer}
    assert len(saved.kwargs["tool_results"]) == 2
