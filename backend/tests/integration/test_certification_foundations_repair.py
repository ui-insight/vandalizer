"""M01-04: Foundations shows missing evidence, then grades a repaired re-run on its own run."""
import json
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.search_set import SearchSetItem
from tests.integration import test_certification_enrollments as base

repo = base.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')
REQUIRED = ['PI Name', 'Institution', 'Total Budget', 'Project Period', 'Sponsoring Agency']


async def test_repaired_extraction_reruns_and_each_run_keeps_its_own_evidence(repo):
    source, package, document, snapshot, first = await base.learner_decision_fixture(repo, approved=True)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', return_value=[{'PI Name': 'Synthetic value'}]):
        first = await base.execute_lab(repo, source, package, snapshot['uuid'], first['run_id'])
    # Before any source check the packet names the missing evidence instead of grading the output.
    packet = await base.assemble_practical(repo, source, package, first['run_id'])
    assert packet['missing_evidence']['foundations.verified_values'] == ['source_reference']
    unresolved = await base.submit_learner_decision(repo, source, package,
        base.learner_decision_submission(package, first['run_id'], 'value_review', document=document), 'value_review')
    assert {item['field'] for item in unresolved['submission']['value_checks']} == set(REQUIRED)

    # Repair: the learner revises the same extraction, captures it again and prepares a new run.
    for phrase in REQUIRED:
        await SearchSetItem(searchset=snapshot['artifact_id'], user_id=source.user_id, searchphrase=phrase, searchtype='extraction').insert()
    storage = base.SimpleNamespace(read=base.AsyncMock(return_value=package.read('documents/' + document.title)))
    repaired = await base.capture_lab(repo, source, package, snapshot['artifact_id'], storage)
    assert repaired['artifact_id'] == snapshot['artifact_id'] and repaired['artifact_sha256'] != snapshot['artifact_sha256']
    second = await base.execute_lab(repo, source, package, repaired['uuid'], uuid4().hex, prepare_only=True)
    await base.submit_learner_decision(repo, source, package, base.learner_decision_submission(package, second['run_id']))
    with patch('app.services.extraction_engine.ExtractionEngine.extract', return_value=[{field: 'Synthetic value' for field in REQUIRED}]):
        second = await base.execute_lab(repo, source, package, repaired['uuid'], second['run_id'])
    checked = await base.submit_learner_decision(repo, source, package,
        base.learner_decision_submission(package, second['run_id'], 'value_review', document=document), 'value_review')

    later = await base.assemble_practical(repo, source, package, second['run_id'])
    assert later['provenance']['value_decision_id'] == checked['uuid'] != unresolved['uuid']
    by_kind = {item['kind']: json.loads(item['text']) for item in later['evidence']}
    assert by_kind['output_snapshot']['entities'] == second['result']['entities']
    # The original run, its output and its own source check remain the evidence for that run.
    earlier = await base.assemble_practical(repo, source, package, first['run_id'])
    assert earlier['provenance']['value_decision_id'] == unresolved['uuid']
    assert {item['kind']: json.loads(item['text']) for item in earlier['evidence']}['output_snapshot']['entities'] == first['result']['entities']
    assert first['result']['entities'] != second['result']['entities']
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 0
