"""Check the learner-selected Cedar Creek work sample before saving a capstone receipt."""
from __future__ import annotations

import datetime
from decimal import Decimal
import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from app.models.activity import ActivityEvent
from app.models.chat import ChatConversation
from app.models.project import Project, ProjectJoinLink, ProjectMembership
from .attempts import encode
from .enrollments import EnrollmentConflict


if TYPE_CHECKING:
    from .catalog import CoursePackage
    from .runtime import CourseOperation
    from .scenario_assessment import ScenarioBank


class SampleSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)


class SampleIncomplete(EnrollmentConflict):
    """The learner can correct a work sample before an attempt has been saved."""


def validate_case(package: CoursePackage) -> None:
    case = package.json('work-sample.json')
    required = ('module_id', 'award_module', 'policy_module', 'browser_url', 'browser_value',
                'policy_passage', 'project_title', 'award_value')
    if not isinstance(case, dict) or any(not isinstance(case.get(k), str) or not case[k].strip() for k in required):
        raise ValueError('Core requires a complete work sample definition')
    if len(amounts(case['award_value'])[0]) != 1:
        raise ValueError('The work sample must name one award amount')
    exercises = package.json('exercises.json')
    module_ids = {m.id for m in package.manifest.modules}
    if (case['module_id'] not in module_ids or any(f'assessments/{mid}.json' not in package.manifest.artifacts for mid in module_ids)
            or not all(exercises.get(case[k], {}).get('documents') for k in ('award_module', 'policy_module'))):
        raise ValueError('The work sample must bind the assigned source modules and capstone bank')


def normalized(text: str) -> str:
    return ' '.join(text.split()).casefold()


def link_open(link: ProjectJoinLink, now: datetime.datetime) -> bool:
    """An invite link someone could still use to join the project."""
    return (not link.revoked and not (link.expires_at and now >= link.expires_at)
            and (link.max_uses is None or link.use_count < link.max_uses))


def note_line(text: str) -> str:
    """A saved line without list markers or its final period; its wording is unchanged."""
    return normalized(re.sub(r'^\s*[-*•]\s+', '', text)).rstrip('.').rstrip()


_AMOUNT = re.compile(
    r'(?<![\w.,])(?P<prefix>(?:us)?\$\s?|usd\s?)?(?P<number>\d{1,3}(?:,\d{3})+|\d+)(?P<cents>\.\d+)?(?![\d,]*\d)'
    r'(?:\s?(?P<scale>k|thousand|million|billion)\b)?(?P<suffix>\s?(?:dollars|usd)\b)?', re.IGNORECASE)
_SCALES = {'k': 10 ** 3, 'thousand': 10 ** 3, 'million': 10 ** 6, 'billion': 10 ** 9}


def amounts(text: str) -> tuple[set[Decimal], set[Decimal]]:
    """Every number in ``text`` and, separately, those written as dollar amounts."""
    numbers: set[Decimal] = set()
    dollars: set[Decimal] = set()
    for match in _AMOUNT.finditer(text):
        value = Decimal(match['number'].replace(',', '') + (match['cents'] or ''))
        value *= _SCALES[match['scale'].lower()] if match['scale'] else 1
        numbers.add(value)
        if match['prefix'] or match['suffix']:
            dollars.add(value)
    return numbers, dollars


def states_amount(expected: str, answer: str) -> bool:
    """The answer gives the award amount as a whole value and no other dollar amount."""
    wanted = next(iter(amounts(expected)[0]), None)
    numbers, dollars = amounts(answer)
    return wanted is not None and wanted in numbers and dollars <= {wanted}


def same_page(left: str, right: str) -> bool:
    def parts(url: str) -> tuple[str, str, str, str]:
        split = urlsplit(url.strip())
        return split.scheme.lower(), split.netloc.lower(), split.path.rstrip('/'), split.query
    return parts(left) == parts(right)


def same_value(left: str, right: str) -> bool:
    return left.strip().rstrip('.').strip().casefold() == right.strip().rstrip('.').strip().casefold()


def check_case(case: dict, bank: ScenarioBank, answers: dict[str, str], context: str | None,
               messages: list[dict], award_ids: list[str], policy_ids: list[str]) -> dict:
    # Only the four selected, source-attributed statements belong in this training note.
    lines = [note_line(line) for line in (context or '').splitlines() if line.strip()]
    expected = [note_line(choice.text) for question in bank.questions for choice in question.choices
                if answers.get(question.id) == choice.id]
    if len(expected) != len(bank.questions) or sorted(lines) != sorted(expected):
        raise SampleIncomplete('Save the four selected lines, each on its own line, in the training Project context.')

    award_scoped = False
    observed: dict = {}
    for index, msg in enumerate(messages):
        if msg['role'] == 'user':
            award_scoped = any(row.get('uuid') in award_ids for row in msg.get('source_documents') or [])
            continue
        if msg['role'] != 'assistant' or msg.get('interruption'):
            continue
        if award_scoped and states_amount(case['award_value'], msg.get('content') or ''):
            observed['award'] = index
        award_scoped = False
        skill = msg.get('active_skill')
        if skill and skill.get('uuid') and skill.get('version'):
            observed['skill'] = {'turn': index, 'uuid': skill['uuid'], 'version': skill['version']}
        # An attached Knowledge Base is searched before the reply without a tool
        # call; either way the retrieved passages are saved as the turn's citations.
        for cited in msg.get('citations') or []:
            if (isinstance(cited, dict) and cited.get('document_uuid') in policy_ids
                    and case['policy_passage'] in normalized(cited.get('content_preview') or '')):
                observed['policy'] = {'turn': index, 'document_uuid': cited['document_uuid']}
        for tool in msg.get('tool_results') or []:
            name, value = tool.get('tool_name'), tool.get('content')
            if name == 'search_knowledge_base' and isinstance(value, list):
                for hit in value:
                    if (isinstance(hit, dict) and hit.get('document_uuid') in policy_ids
                            and case['policy_passage'] in normalized(hit.get('content') or '')):
                        observed['policy'] = {'turn': index, 'document_uuid': hit['document_uuid']}
            if not isinstance(value, dict):
                continue
            if (name == 'record_value' and value.get('recorded') is True
                    and isinstance(value.get('url'), str) and isinstance(value.get('value'), str)
                    and same_page(value['url'], case['browser_url']) and same_value(value['value'], case['browser_value'])):
                observed['browser'] = {'turn': index, 'url': value['url'], 'value': value['value']}
                observed.pop('finish', None)
            # Only "closed" shows this chat's tab was released. "none" is also returned
            # when another chat took over the working tab, which can leave this page open.
            if name == 'browser_finish' and value.get('ok') is True and value.get('working_tab') == 'closed' and 'browser' in observed:
                observed['finish'] = index
    needs = {'award': 'Ask for the authorized amount with the assigned award attached.',
             'policy': 'Search the training Knowledge Base for pre-booking approval using the assigned policy.',
             'skill': 'Select a Skill and complete a case-review turn.',
             'browser': 'Read the assigned IANA page with browser controls and record example.org.',
             'finish': 'Finish the browser task and release its working tab after recording the domain. '
                       'If you closed or kept the tab yourself, repeat the lookup and let the assistant close it.'}
    missing = [instruction for key, instruction in needs.items() if key not in observed]
    if missing:
        raise SampleIncomplete(' '.join(missing))
    return {'note_sha256': encode(sorted(lines))[1], 'observations': observed}


async def capture_sample(operation: CourseOperation, selection: SampleSelection, bank: ScenarioBank,
                         answers: dict[str, str], case: dict) -> dict:
    user_id = operation.user_id
    project = await Project.find_one({'uuid': selection.project_id, 'owner_user_id': user_id, 'team_id': None})
    if (project is None or normalized(project.title) != normalized(case['project_title'])
            or await ProjectMembership.find_one({'project_uuid': project.uuid})
            or any(link_open(link, datetime.datetime.now())
                   for link in await ProjectJoinLink.find({'project_uuid': project.uuid}).to_list())):
        raise SampleIncomplete('Choose your personal, unshared Cedar Creek CC-17 training project.')
    identity = {'user_id': user_id, 'project_uuid': project.uuid, 'conversation_id': selection.conversation_id,
                'type': 'conversation'}
    if not await ActivityEvent.find_one(identity):
        raise SampleIncomplete('Choose the chat you used in this Cedar Creek project.')
    conversation = await ChatConversation.find_one({'uuid': selection.conversation_id, 'user_id': user_id})
    if conversation is None:
        raise SampleIncomplete('The selected case chat is unavailable.')
    modules = operation.progress.modules
    evidence = check_case(case, bank, answers, project.context, await conversation.get_messages(),
                          modules.get(case['award_module'], {}).get('provisioned_docs', []),
                          modules.get(case['policy_module'], {}).get('provisioned_docs', []))
    return {**selection.model_dump(), **evidence}
