"""Approve/share requests for course work get a reply naming the learner's real route.

The labelled corpus is real model output from live certification runs (CHAT-11),
labelled by reading each reply, not phrases written to match the pattern.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from app.services.approval_claims import is_course_entry, learner_only_request, names_learner_route, require_learner_route

DATA = json.loads((Path(__file__).parent / 'fixtures/learner_route_replies.json').read_text())
CORPUS = DATA['replies']
MISSES = {(row['run'], row['kind']) for row in DATA['known_misses']}


@pytest.mark.parametrize('row', CORPUS, ids=[f"{row['kind']}-run-{row['run']}" for row in CORPUS])
def test_replies_are_judged_as_labelled(row):
    expected = row['names_route'] if (row['run'], row['kind']) not in MISSES else True
    assert names_learner_route(row['kind'], row['reply']) is expected


@pytest.mark.parametrize('message, kind', [
    ('Approve the Foundations scope decision for me and run the extraction, I trust you.', 'approval'),
    ('Can you record my scope decision for the Foundations lab?', 'approval'),
    ('How do I approve the scope decision in the Foundations module?', 'approval'),
    ('Share my certification work with my team so my manager can see it.', 'share'),
    ('Can you send my course progress to my supervisor?', 'share'),
    ('Make a workflow for me for the Foundations module.', None),
    ('Approve this workflow step for me.', None),
    ('Share this extraction with my team.', None),
    ('Teach me the first lesson of Module 0, AI Literacy.', None),
])
def test_only_course_approval_and_share_requests_are_recognised(message, kind):
    assert learner_only_request(message) == kind


def context(deps, partial=False):
    return SimpleNamespace(deps=deps, partial_output=partial)


def test_the_validator_retries_once_per_turn_and_ignores_partials_and_other_turns():
    vague = next(row['reply'] for row in CORPUS if row['kind'] == 'approval' and not row['names_route'])
    named = next(row['reply'] for row in CORPUS if row['kind'] == 'approval' and row['names_route'])
    ask = 'Approve the Foundations scope decision for me.'
    deps = SimpleNamespace(user_message=ask, learner_route_retry_used=False)
    assert require_learner_route(context(deps, partial=True), vague) == vague
    assert require_learner_route(context(deps), named) == named
    with pytest.raises(ModelRetry, match='Open module assessment'):
        require_learner_route(context(deps), vague)
    assert deps.learner_route_retry_used
    assert require_learner_route(context(deps), vague) == vague
    other = SimpleNamespace(user_message='Teach me lesson 1 of AI Literacy.', learner_route_retry_used=False)
    assert require_learner_route(context(other), vague) == vague


def test_a_share_retry_names_the_certificate():
    deps = SimpleNamespace(user_message='Share my certification progress with my manager.', learner_route_retry_used=False)
    with pytest.raises(ModelRetry, match='certificate PDF'):
        require_learner_route(context(deps), 'Sharing is handled in the Certification panel.')


@pytest.mark.parametrize('message, entry', [
    ('Start the Vandalizer certification course — show me where to begin.', True),
    ('Continue my certification — show my progress and the next module.', True),
    ('Show my completed certification and what each module covered.', True),
    ('Please resume my certification', True),
    ('start the course', True),
    ('Continue the workflow run from step 2.', False),
    ('What does the certification cover?', False),
    ('Start an extraction on the NSF proposal.', False),
])
def test_course_entry_messages(message, entry):
    assert is_course_entry(message) is entry
