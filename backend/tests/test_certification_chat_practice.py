"""M00-02: the scoped chat practice checks the real passage and the unsupported answer."""
import json
import re
from pathlib import Path

import fitz
import pytest

from app.services.certification_versions.chat_practice import ChatPractice, ChatPracticeCheck, check_practice

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'
EXERCISE = json.loads((DRAFT / 'ai-literacy-exercise.json').read_text())
PRACTICE = ChatPractice.model_validate(EXERCISE['chat_practice'])
with fitz.open(DRAFT / 'documents' / PRACTICE.document) as pdf:
    PAGES = [page.get_text() for page in pdf]
HONEST = {'passage_quote': 'Requested Amount: $485,000', 'page': 1, 'value': '$485,000', 'unanswerable_judgment': 'not_stated_in_source'}


def test_the_practice_is_optional_and_uses_only_its_document():
    assert EXERCISE['documents'] == [PRACTICE.document]
    assert EXERCISE['assessment_method'] == 'authenticated_scenario_recognition'
    assert PRACTICE.rule == 'practice_only_no_credit_no_write'
    # The unanswerable question really is unanswerable: amounts, no rate.
    assert 'Indirect Costs' in PAGES[0] and '%' not in PAGES[0] and not re.search(r'\brate\b', PAGES[0], re.I)


def test_an_honest_practice_is_complete_and_saves_nothing():
    result = check_practice(PRACTICE, PAGES, ChatPracticeCheck.model_validate(HONEST))
    assert result['practice_complete'] is True and result['saved'] is False and result['credit_awarded'] is False


@pytest.mark.parametrize('change, failed', [
    ({'passage_quote': 'Requested Amount: $500,000'}, 'passage_found'),
    ({'page': 2}, 'passage_found'),
    ({'passage_quote': 'Principal Investigator: Dr. Sarah Chen'}, 'quote_supports_value'),
    ({'passage_quote': 'Total $177,000', 'value': '177000'}, 'quote_supports_value'),
    ({'unanswerable_judgment': 'supported_by_source'}, 'judgment_correct'),
])
def test_missing_or_misread_evidence_is_named(change, failed):
    result = check_practice(PRACTICE, PAGES, ChatPracticeCheck.model_validate({**HONEST, **change}))
    assert result['practice_complete'] is False and result[failed] is False
    assert result['feedback'] and result['credit_awarded'] is False
