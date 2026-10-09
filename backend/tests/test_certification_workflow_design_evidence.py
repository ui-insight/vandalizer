from copy import deepcopy

import pytest

from app.services.certification_versions.practical_evidence import EvidenceAssemblyUnavailable
from app.services.certification_versions.workflow_design_evidence import require_resolved_configuration


@pytest.fixture
def artifact():
    return {'workflow': {'attachments': [], 'resource_config': {}, 'output_config': {}, 'input_config': {}},
            'steps': [{'step': {'data': {}}, 'tasks': [{'name': 'Prompt', 'data': {'prompt': 'Compare the supplied reports', 'input_sources': ['workflow_documents']}}]}],
            'referenced_extraction_sets': {}}


def test_design_collector_accepts_inline_configuration_without_claiming_quality(artifact):
    require_resolved_configuration(artifact)
    # A bad prompt or wrong connection remains actual evidence for rubric review.
    artifact['steps'][0]['tasks'][0]['data'] = {'prompt': 'Guess missing values', 'input_sources': ['step_input']}
    require_resolved_configuration(artifact)


@pytest.mark.parametrize('change', ['attachments', 'resources', 'output_reference', 'fixed_source', 'unsupported_task',
    'unknown_task_setting', 'selected_document', 'selected_document_source', 'document_ids', 'missing_extraction', 'extra_extraction', 'mismatched_extraction'])
def test_uncaptured_dependencies_cannot_be_replaced_with_current_workspace_or_prose(artifact, change):
    workflow = artifact['workflow']
    task = artifact['steps'][0]['tasks'][0]
    if change == 'attachments':
        workflow['attachments'] = ['uncaptured-attachment']
    elif change == 'resources':
        workflow['resource_config'] = {'external': 'uncaptured'}
    elif change == 'output_reference':
        workflow['output_config'] = {'template_id': 'uncaptured'}
    elif change == 'fixed_source':
        workflow['input_config'] = {'fixed_documents': [{'uuid': 'uncaptured'}]}
    elif change == 'unsupported_task':
        task['name'] = 'APINode'
    elif change == 'unknown_task_setting':
        task['data']['unknown_context_reference'] = 'uncaptured'
    elif change == 'selected_document':
        task['data']['selected_document_uuid'] = 'uncaptured'
    elif change == 'selected_document_source':
        task['data']['input_sources'] = ['selected_document']
    elif change == 'document_ids':
        task.update(name='Document', data={'doc_uuids': ['uncaptured']})
    elif change == 'extra_extraction':
        artifact['referenced_extraction_sets'] = {'unlinked': {'uuid': 'unlinked'}}
    else:
        task.update(name='Extraction', data={'search_set_uuid': 'selected'})
        if change == 'mismatched_extraction':
            artifact['referenced_extraction_sets'] = {'selected': {'uuid': 'other'}}
    with pytest.raises(EvidenceAssemblyUnavailable):
        require_resolved_configuration(artifact)


def test_captured_extraction_must_match_the_actual_task_reference(artifact):
    artifact['steps'][0]['tasks'][0] = {'name': 'Extraction', 'data': {'search_set_uuid': 'selected'}}
    artifact['referenced_extraction_sets'] = {'selected': {'uuid': 'selected', 'fields': [{'searchphrase': 'Milestone'}]}}
    before = deepcopy(artifact)
    require_resolved_configuration(artifact)
    assert artifact == before
