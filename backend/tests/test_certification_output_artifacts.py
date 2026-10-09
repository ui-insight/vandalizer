"""Actual output-node files and product bundle inspection; no providers or DB."""
import base64
from copy import deepcopy
import hashlib
import io
import zipfile

import pytest

from app.services.workflow_engine import DocumentRendererNode, DataExportNode
from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.output_artifacts import capture_generated_artifacts, verify_generated_artifacts
from app.services.certification_versions.output_case import REQUIRED_FIELDS


def record():
    return dict(zip(REQUIRED_FIELDS, [
        'Alpine Ecosystem Response to Climate Change in the Northern Rockies', 'Dr. Sarah Chen',
        'September 1, 2026 - August 31, 2027', '24 plots sampled; 96 soil samples processed.',
        'Two journal publications; one in review, one in press and one submitted.', '9',
        'USD 135500', 'USD 287500', 'USD 197500', 'Complete final monitoring and submit the final report.',
        'Assigned progress-report-year2.pdf, pages 1 and 2.']))


@pytest.fixture
def status():
    data = record()
    pdf = DocumentRendererNode({'format': 'pdf', 'filename': 'progress-report'}).process({'output': data})
    csv = DataExportNode({'format': 'csv', 'filename': 'progress-summary'}).process({'output': data})
    return {'status': 'completed', 'workflow_name': 'Synthetic output assessment', 'final_output': csv,
            'steps_output': {'Report': pdf, 'Summary': csv}, 'output_step_names': ['Report', 'Summary']}


def test_preserves_actual_generated_files_and_product_zip_without_credit(status):
    original = deepcopy(status)
    saved = capture_generated_artifacts(status)
    assert status == original
    assert saved['all_required_files_parseable'] is True
    assert saved['release_authorized'] is saved['delivery_confirmed'] is saved['credit_awarded'] is False
    pdf, csv = saved['files']
    assert pdf['inspection']['pages'] >= 1
    assert 'USD 135500' in pdf['inspection']['text']
    assert csv['inspection']['headers'] == list(REQUIRED_FIELDS)
    assert csv['inspection']['rows'][0][7] == 'USD 287500'
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(saved['download']['data_base64']))) as bundle:
        assert bundle.namelist() == ['progress-report.pdf', 'progress-summary.csv']
        for file in saved['files']:
            assert bundle.read(file['filename']) == base64.b64decode(file['data_base64'])
    assert verify_generated_artifacts(saved) == saved


@pytest.mark.parametrize('change', ['empty', 'malformed_pdf', 'text_fallback', 'invalid_csv', 'missing_labels',
    'missing_columns', 'empty_value', 'duplicate_header', 'unequal_columns', 'formula', 'wrong_extension'])
def test_incorrect_files_remain_inspectable_repair_evidence_not_success(status, change):
    target = status['steps_output']['Summary']['output']
    if change == 'empty':
        target['data_b64'] = ''
    elif change == 'malformed_pdf':
        target = status['steps_output']['Report']['output']
        target['data_b64'] = base64.b64encode(b'%PDF-not-valid').decode()
    elif change == 'text_fallback':
        status['steps_output']['Summary'] = DataExportNode({'format': 'csv', 'filename': 'progress-summary'}).process({'output': 'Prose cannot silently become a table.'})
    elif change == 'invalid_csv':
        target['data_b64'] = base64.b64encode(b'\xff\xfe').decode()
    elif change == 'missing_labels':
        status['steps_output']['Report'] = DocumentRendererNode({'format': 'pdf', 'filename': 'progress-report'}).process({'output': 'Incomplete report with no required labels.'})
    elif change in ('missing_columns', 'empty_value', 'formula'):
        data = record()
        if change == 'missing_columns':
            del data['Year 2 Budget Spent']
        elif change == 'empty_value':
            data['Publications'] = ''
        else:
            data['PI Name'] = '=1+1'
        status['steps_output']['Summary'] = DataExportNode({'format': 'csv', 'filename': 'progress-summary'}).process({'output': data})
    elif change == 'duplicate_header':
        target['data_b64'] = base64.b64encode(b'A,A\n1,2\n').decode()
    elif change == 'unequal_columns':
        target['data_b64'] = base64.b64encode(b'A,B\n1\n').decode()
    elif change == 'wrong_extension':
        target['filename'] = 'summary.txt'
    saved = capture_generated_artifacts(status)
    assert saved['all_required_files_parseable'] is False
    assert any(file['inspection']['issues'] for file in saved['files'])
    assert verify_generated_artifacts(saved) == saved


@pytest.mark.parametrize('change', ['not_completed', 'missing_step', 'duplicate_step', 'no_file', 'invalid_base64',
    'duplicate_filename', 'traversal', 'backslash', 'control_character', 'oversize', 'unsupported_format'])
def test_rejects_ambiguous_unsafe_or_oversize_downloads_before_packaging(status, change):
    target = status['steps_output']['Summary']['output']
    if change == 'not_completed':
        status['status'] = 'executing'
    elif change == 'missing_step':
        del status['steps_output']['Report']
    elif change == 'duplicate_step':
        status['output_step_names'] = ['Report', 'Report']
    elif change == 'no_file':
        status['steps_output']['Summary'] = {'output': 'No file produced'}
    elif change == 'invalid_base64':
        target['data_b64'] = 'bad!'
    elif change == 'duplicate_filename':
        target['filename'] = 'progress-report.pdf'
    elif change in ('traversal', 'backslash', 'control_character'):
        target['filename'] = {'traversal': '../../summary.csv', 'backslash': '..\\summary.csv', 'control_character': 'sum\x00mary.csv'}[change]
    elif change == 'oversize':
        target['data_b64'] = base64.b64encode(b'x' * (1024 * 1024 + 1)).decode()
    elif change == 'unsupported_format':
        target['file_type'] = 'executable'
    with pytest.raises(EnrollmentConflict):
        capture_generated_artifacts(status)


@pytest.mark.parametrize('change', ['file_bytes', 'inspection', 'file_hash', 'download_bytes', 'download_hash',
    'bundle_members', 'parseability_claim', 'credit', 'delivery', 'release'])
def test_rejects_changed_artifact_or_bundle_evidence(status, change):
    saved = capture_generated_artifacts(status)
    if change == 'file_bytes':
        saved['files'][0]['data_base64'] = base64.b64encode(b'changed').decode()
    elif change == 'inspection':
        saved['files'][0]['inspection']['text'] = 'fabricated reviewed text'
    elif change == 'file_hash':
        saved['files'][0]['sha256'] = 'a' * 64
    elif change == 'download_bytes':
        saved['download']['data_base64'] = base64.b64encode(b'changed').decode()
    elif change == 'download_hash':
        saved['download']['sha256'] = 'a' * 64
    elif change == 'bundle_members':
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as bundle:
            bundle.writestr('unrelated.txt', 'unrelated output')
        data = buffer.getvalue()
        saved['download'].update(data_base64=base64.b64encode(data).decode(), size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    elif change == 'parseability_claim':
        saved['all_required_files_parseable'] = False
    else:
        saved[{'credit': 'credit_awarded', 'delivery': 'delivery_confirmed', 'release': 'release_authorized'}[change]] = True
    with pytest.raises(EnrollmentConflict):
        verify_generated_artifacts(saved)


def test_single_file_is_preserved_but_does_not_satisfy_the_bundle_assignment(status):
    status['output_step_names'] = ['Report']
    saved = capture_generated_artifacts(status)
    assert saved['all_required_files_parseable'] is False
    assert saved['download']['data_base64'] == saved['files'][0]['data_base64']
    assert verify_generated_artifacts(saved) == saved


def test_single_file_media_type_cannot_change_after_capture(status):
    status['output_step_names'] = ['Report']
    saved = capture_generated_artifacts(status)
    saved['download']['media_type'] = 'text/html'
    with pytest.raises(EnrollmentConflict):
        verify_generated_artifacts(saved)
