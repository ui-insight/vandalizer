"""Module 0 scoped chat practice: open the supporting passage, notice missing evidence.

The learner selects the assigned training document in chat, asks a bounded
question and opens the passage that answers it, then asks a question the
document cannot answer. This check reads only the packaged document; it saves
nothing, awards nothing and never calls a model. Recognition grading for the
module is unchanged.
"""
import re
from typing import Literal

from pydantic import Field

from .outcomes import ContractModel

PROMPT_ID = 'scoped_chat_practice'


class ChatPractice(ContractModel):
    document: Literal['nsf-proposal-alpine-ecology.pdf']
    bounded_question: str = Field(min_length=20, max_length=300)
    expected_value: str = Field(pattern=r'^[0-9]{1,12}$')
    unanswerable_question: str = Field(min_length=20, max_length=300)
    expected_judgment: Literal['not_stated_in_source']
    rule: Literal['practice_only_no_credit_no_write']


class ChatPracticeCheck(ContractModel):
    passage_quote: str = Field(min_length=5, max_length=500)
    page: int = Field(ge=1, le=20)
    value: str = Field(min_length=1, max_length=100)
    unanswerable_judgment: Literal['supported_by_source', 'not_stated_in_source']


def _spaced(text):
    return ' '.join(text.split()).casefold()


def _amount(value):
    digits = re.sub(r'[^0-9.]', '', value)
    try:
        return str(int(float(digits))) if digits else None
    except ValueError:
        return None


def check_practice(practice: ChatPractice, pages: list[str], body: ChatPracticeCheck) -> dict:
    page_text = pages[body.page - 1] if body.page <= len(pages) else ''
    passage_found = bool(page_text) and _spaced(body.passage_quote) in _spaced(page_text)
    value_matches = _amount(body.value) == practice.expected_value
    quote_supports_value = passage_found and _amount(body.passage_quote) == practice.expected_value
    judgment_correct = body.unanswerable_judgment == practice.expected_judgment
    feedback = []
    if not passage_found:
        feedback.append('That passage is not on the stated page of the assigned document. Open the source and copy the exact sentence that answers the question.')
    elif not quote_supports_value:
        feedback.append('The passage is in the document but does not state the answer. Find the sentence that gives the value itself.')
    if not value_matches:
        feedback.append('The value does not match what the assigned document states for the question you asked.')
    if not judgment_correct:
        feedback.append('The document lists amounts but states no rate. An answer that gives one, without a passage, is unsupported, however confident it sounds.')
    complete = passage_found and quote_supports_value and value_matches and judgment_correct
    return {'prompt_id': PROMPT_ID, 'passage_found': passage_found, 'quote_supports_value': quote_supports_value,
            'value_matches': value_matches, 'judgment_correct': judgment_correct, 'practice_complete': complete,
            'feedback': feedback or ['You opened the passage that supports the answer and noticed the unsupported one.'],
            'saved': False, 'credit_awarded': False}
