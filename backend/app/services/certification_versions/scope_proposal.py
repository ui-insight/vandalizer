"""Pinned teaching proposal and explicit source selection for Foundations."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .attempts import encode
from .catalog import CourseCatalogError


class ScopeProposalCase(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1, strict=True)
    module_id: Literal['foundations']
    prompt_id: str = Field(min_length=1, max_length=100)
    task: str = Field(min_length=20, max_length=3000)
    original_source_filename: str = Field(pattern=r'^[a-z0-9][a-z0-9-]*\.pdf$')

    def verify_exercise(self, exercise):
        """Bind the new draft instructions without changing legacy exercises."""
        if (not isinstance(exercise, dict)
                or exercise.get('assessment_method') != 'owned_scoped_extraction'
                or exercise.get('assessment_case_id') != self.id
                or exercise.get('scope_proposal_sha256') != encode(self.model_dump(mode='json'))[1]
                or exercise.get('documents') != ['nsf-proposal-alpine-ecology.pdf']
                or exercise.get('expected_fields') != ['PI Name', 'Institution', 'Total Budget', 'Project Period', 'Sponsoring Agency']
                or exercise.get('expected_values') != {} or exercise.get('star_criteria') != {}):
            raise ValueError('The Foundations exercise must bind its scoped case and all required fields without legacy answer or star criteria')
        if not isinstance(exercise.get('overview'), str) or len(exercise['overview'].strip()) < 20:
            raise ValueError('The Foundations exercise needs a readable task overview')
        for key in ('instructions', 'chat_instructions'):
            if (not isinstance(exercise.get(key), list) or not exercise[key]
                    or any(not isinstance(item, str) or not item.strip() for item in exercise[key])):
                raise ValueError('The Foundations exercise needs readable instructions for both routes')


class ProposalSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    proposal_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_id: str = Field(min_length=1, max_length=200)


def load_proposal_case(package, module_id):
    from .learner_decisions import execution_requirement
    path = f'proposals/{module_id}.json'
    if path not in package.manifest.artifacts:
        return None
    try:
        case = ScopeProposalCase.model_validate(package.json(path))
        exercise = package.json('exercises.json')[module_id]
        assigned = exercise['documents']
        if 'assessment_method' in exercise:
            case.verify_exercise(exercise)
        requirement = execution_requirement(package, module_id)
        if (case.module_id != module_id or len(assigned) != 1
                or case.original_source_filename in assigned
                or 'documents/' + case.original_source_filename not in package.manifest.artifacts
                or requirement is None or case.prompt_id != requirement['prompt_id']):
            raise ValueError('Proposal case must use a packaged unrelated source and the scope approval prompt')
        return case
    except (ValueError, KeyError, TypeError) as exc:
        raise CourseCatalogError('The scope proposal case is invalid') from exc


def capture_proposal(package, snapshot):
    case = load_proposal_case(package, snapshot['module_id'])
    if case is None:
        return None
    unrelated_id = 'course_asset:' + case.original_source_filename
    assigned = snapshot['documents'][0]
    return {'case': case.model_dump(mode='json'), 'case_sha256': encode(case.model_dump(mode='json'))[1],
            'input_snapshot_id': snapshot['uuid'], 'input_snapshot_sha256': encode(snapshot)[1],
            'lab_folder_id': snapshot['lab_folder_id'], 'artifact_sha256': snapshot['artifact_sha256'],
            'original_source_id': unrelated_id,
            'source_options': [
                {'id': unrelated_id, 'title': case.original_source_filename,
                 'assigned_filename': case.original_source_filename,
                 'source_sha256': package.manifest.artifacts['documents/' + case.original_source_filename]},
                {'id': assigned['document_id'], 'title': assigned['title'],
                 'assigned_filename': assigned['assigned_filename'], 'source_sha256': assigned['source_sha256']},
            ]}


def selection_matches_run(proposal, selection, snapshot):
    return (selection is not None and selection.proposal_sha256 == encode(proposal)[1]
            and [selection.source_id] == [item['document_id'] for item in snapshot['documents']])
