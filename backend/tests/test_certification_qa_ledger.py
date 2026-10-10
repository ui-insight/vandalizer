"""Evidence inventory retains failures and never equates captures with acceptance."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('certification_qa_ledger', Path(__file__).resolve().parents[2] / 'scripts/build_certification_qa_ledger.py')
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)


def test_report_preserves_diagnostic_states_and_identifies_missing_files(tmp_path):
    directory = tmp_path / 'artifacts/visual-review' / ledger.BASELINE_RUNS[0]
    directory.mkdir(parents=True)
    manifest = directory / 'manifest.json'
    manifest.write_text(json.dumps({'captures': [{'id': 'example', 'viewport': {'width': 320, 'height': 480}}, {'id': 'blocked'}],
                                    'errors': ['Original recorded failure'], 'sourceFingerprint': 'reported-only'}))
    for name in ('example', 'blocked'):
        (directory / (name + '.png')).write_bytes(b'synthetic-image-placeholder')
        (directory / (name + '.axe.json')).write_text('[]')
    value = ledger.run_row(tmp_path, manifest, [42])
    assert len(value['captures']) == 2 and value['captures'][1]['diagnostic_capture']
    assert value['recorded_errors'] == ['Original recorded failure']
    assert value['captures'][0]['assets']['accessible_snapshot']['available'] is False
    assert value['captures'][0]['assets']['image']['sha256']
    assert value['verified_build_manifest'] is None
    assert value['reported_source_fingerprint'] == 'reported-only'
    assert not any(key in value for key in ('passed', 'accepted', 'grade'))


@pytest.mark.parametrize('identity', ['../private', '/absolute', 'unsafe/name'])
def test_capture_names_cannot_escape_the_evidence_directory(tmp_path, identity):
    with pytest.raises(ValueError, match='Unsafe capture'):
        ledger.capture_row(tmp_path, tmp_path, {'id': identity})


def test_source_reference_does_not_follow_outside_repository_symlink(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    secret = tmp_path / 'outside'
    secret.write_text('must not be hashed or exposed')
    (root / 'source.json').symlink_to(secret)
    result = ledger.reference(root, 'source.json')
    assert result == {'path': 'source.json', 'available': False, 'reason': 'outside_repository'}


def test_capture_markup_is_escaped_in_the_searchable_report():
    value = {'counts': {'accepted': 1, 'items': 2, 'open': 1, 'baseline_selected_captures': 0,
                        'recorded_captures_including_diagnostics_and_repeats': 1, 'browser_runs': 1},
             'limits': ['<script>example</script>'], 'missing_artifacts': [], 'browser_runs': [{
                 'manifest': {'path': 'artifacts/example.json'}, 'captures': [{'viewport': {'width': 320}}],
                 'baseline_run': False, 'checkpoints': [42], 'verified_build_manifest': None,
                 'browser': 'chromium', 'native_profile_zoom': 1, 'reported_text_scale': 1,
                 'reported_scope': '<img src=x onerror=alert(1)>',
             }]}
    html = ledger.render(value)
    assert '<img src=x' not in html and '&lt;img src=x' in html
    assert '<script>example</script>' not in html
    assert '1 of 2 checklist items accepted; 1 open' in html
    assert 'Reported fingerprint only' in html


def test_acceptance_counts_come_from_unique_checked_items():
    checklist = '1/2 items complete; 1 remain open.\n- [x] **C8-QA-01 · Complete\n- [ ] **C8-QA-02 · Pending\n'
    progress = '**Accepted items:** 1/2. **Remaining:** 1.'
    assert [item['accepted'] for item in ledger.checked_items(checklist, progress)] == [True, False]


@pytest.mark.parametrize('failure', ['checklist_count', 'progress_count', 'missing_summary', 'duplicate', 'empty'])
def test_tracking_drift_is_rejected_before_evidence_generation(failure):
    checklist = '1/2 items complete; 1 remain open.\n- [x] **C8-QA-01 · Complete\n- [ ] **C8-QA-02 · Pending\n'
    progress = '**Accepted items:** 1/2. **Remaining:** 1.'
    if failure == 'checklist_count':
        checklist = checklist.replace('1/2', '0/2')
    elif failure == 'progress_count':
        progress = progress.replace('1/2', '0/2')
    elif failure == 'missing_summary':
        progress = 'No current counts'
    elif failure == 'duplicate':
        checklist = checklist.replace('C8-QA-02', 'C8-QA-01')
    else:
        checklist = '0/0 items complete; 0 remain open.'
    with pytest.raises(ValueError, match='summary disagrees|unique acceptance item IDs'):
        ledger.checked_items(checklist, progress)
