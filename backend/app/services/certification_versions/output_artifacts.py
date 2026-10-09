"""Preserve and inspect real output-node bytes and the product download bundle.

Parseability and required-field checks support learner inspection; they never
establish source correctness, authorization, delivery, a grade or completion.
"""
import base64
import csv
import hashlib
import io
import json
from pathlib import PurePosixPath
import zipfile

import fitz

from .attempts import encode
from .enrollments import EnrollmentConflict
from .output_case import REQUIRED_FIELDS

MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 2 * MAX_FILE_BYTES
MAX_RECORD_BYTES = 6 * MAX_FILE_BYTES
MAX_TEXT = 100_000
FILE_TYPES = {'pdf', 'csv', 'txt', 'md', 'json', 'docx', 'zip'}
MEDIA_TYPES = {'pdf': 'application/pdf', 'csv': 'text/csv', 'json': 'application/json',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'zip': 'application/zip'}


def _bytes(value):
    try:
        if not isinstance(value, str) or len(value) > (MAX_TOTAL_BYTES + 65536) * 4 // 3 + 8:
            raise ValueError('Unsupported encoding size')
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise EnrollmentConflict('Generated file encoding is invalid or too large') from exc


def _filename(name):
    if (not isinstance(name, str) or not name.strip() or len(name) > 180 or name != name.strip()
            or name in ('.', '..') or name.startswith('.') or '/' in name or '\\' in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name) or PurePosixPath(name).name != name):
        raise EnrollmentConflict('Generated file requires a safe, distinct filename before download')
    return name


def inspect_file(filename, file_type, data):
    """Read the exact bytes; retain invalid output as repair evidence."""
    issues, text, details = [], '', {}
    if not data:
        issues.append('empty_file')
    elif file_type == 'pdf':
        try:
            if not data.startswith(b'%PDF-'):
                raise ValueError('Not a PDF')
            with fitz.open(stream=data, filetype='pdf') as pdf:
                if pdf.needs_pass or not 1 <= len(pdf) <= 12:
                    raise ValueError('Encrypted or unsupported page count')
                pages = [page.get_text() for page in pdf]
                text = '\n\n'.join(pages)
                details = {'pages': len(pdf)}
                if not text.strip():
                    issues.append('no_readable_text')
                if any(not page.strip() for page in pages):
                    issues.append('empty_page')
        except Exception:
            issues.append('unreadable_pdf')
    elif file_type == 'csv':
        try:
            text = data.decode('utf-8-sig')
            reader = csv.reader(io.StringIO(text), strict=True)
            rows = []
            for row in reader:
                if len(rows) >= 101 or len(row) > 40 or any(len(cell) > 20_000 for cell in row):
                    raise ValueError('Unsupported table size')
                rows.append(row)
            if len(rows) < 2 or not rows[0] or len(set(rows[0])) != len(rows[0]) or any(not h.strip() for h in rows[0]):
                issues.append('missing_rows_or_ambiguous_headers')
            elif any(len(row) != len(rows[0]) for row in rows[1:]):
                issues.append('inconsistent_column_count')
            else:
                details = {'headers': rows[0], 'rows': rows[1:]}
                if not set(REQUIRED_FIELDS) <= set(rows[0]):
                    issues.append('missing_required_columns')
                if any(not row[i].strip() for row in rows[1:] for i, header in enumerate(rows[0]) if header in REQUIRED_FIELDS):
                    issues.append('empty_required_value')
            if any(cell.lstrip().startswith(('=', '+', '-', '@')) for row in rows for cell in row):
                issues.append('spreadsheet_formula_risk')
        except (ValueError, UnicodeError, csv.Error):
            issues.append('unreadable_csv')
    else:
        issues.append('unexpected_file_format')
        try:
            text = data.decode('utf-8')
        except UnicodeError:
            issues.append('unreadable_text')
    if len(text) > MAX_TEXT:
        raise EnrollmentConflict('Generated file text exceeds the preserved inspection limit')
    if file_type == 'pdf' and text and any(field not in ' '.join(text.split()) for field in REQUIRED_FIELDS):
        issues.append('missing_required_labels')
    if not filename.lower().endswith('.' + file_type):
        issues.append('filename_format_mismatch')
    return {'parseable_and_fields_present': not issues, 'issues': sorted(set(issues)), 'text': text, **details,
            'source_correctness_verified': False, 'visual_inspection_required': True}


def _file_record(name, kind, data):
    if not isinstance(kind, str) or kind not in FILE_TYPES:
        raise EnrollmentConflict('Unsupported generated file type')
    if len(data) > MAX_FILE_BYTES:
        raise EnrollmentConflict('Generated file exceeds the preserved size limit')
    return {'filename': _filename(name), 'file_type': kind, 'sha256': hashlib.sha256(data).hexdigest(),
            'size_bytes': len(data), 'data_base64': base64.b64encode(data).decode('ascii'),
            'inspection': inspect_file(name, kind, data)}


def capture_generated_artifacts(status):
    """Internal trusted engine result only; no endpoint accepts a supplied status."""
    from app.routers.workflows import _render_workflow_output, _step_output_value
    if not isinstance(status, dict) or status.get('status') != 'completed':
        raise EnrollmentConflict('A completed owned generation is required before file inspection')
    names, steps = status.get('output_step_names'), status.get('steps_output')
    if (not isinstance(names, list) or not 1 <= len(names) <= 8 or len(set(names)) != len(names)
            or not isinstance(steps, dict) or any(name not in steps for name in names)):
        raise EnrollmentConflict('Every declared output step requires its original result')
    files = []
    for name in names:
        value = _step_output_value(steps[name])
        if not isinstance(value, dict) or value.get('type') != 'file_download':
            raise EnrollmentConflict('A marked output step did not produce file bytes')
        kind = value.get('file_type')
        if not isinstance(kind, str) or kind not in FILE_TYPES:
            raise EnrollmentConflict('Unsupported generated file type')
        files.append({'step_name': name, **_file_record(value.get('filename'), kind, _bytes(value.get('data_b64')))})
    if len({f['filename'] for f in files}) != len(files):
        raise EnrollmentConflict('Generated file names must be distinct before packaging')
    if sum(f['size_bytes'] for f in files) > MAX_TOTAL_BYTES:
        raise EnrollmentConflict('Generated files exceed the total preserved size limit')
    bundle, media_type, extension, explicit_name = _render_workflow_output(status, 'json', False)
    if len(bundle) > MAX_TOTAL_BYTES + 65536:
        raise EnrollmentConflict('Generated download exceeds the preserved size limit')
    result = {'schema_version': 1, 'record_kind': 'generated_output_artifacts', 'files': files,
        'download': {'filename': _filename(explicit_name or 'progress-deliverables.' + extension),
            'file_type': extension, 'media_type': media_type, 'sha256': hashlib.sha256(bundle).hexdigest(),
            'size_bytes': len(bundle), 'data_base64': base64.b64encode(bundle).decode('ascii')},
        'all_required_files_parseable': len(files) == 2 and {f['file_type'] for f in files} == {'pdf', 'csv'}
            and all(f['inspection']['parseable_and_fields_present'] for f in files),
        'learner_inspection_required': True, 'release_authorized': False, 'delivery_confirmed': False, 'credit_awarded': False}
    if len(encode(result)[0].encode()) > MAX_RECORD_BYTES:
        raise EnrollmentConflict('Generated artifact record exceeds the preserved size limit')
    verify_generated_artifacts(result)
    return result


def verify_generated_artifacts(record):
    """Verify original bytes without regenerating a timestamped ZIP or files."""
    try:
        if (set(record) != {'schema_version', 'record_kind', 'files', 'download', 'all_required_files_parseable',
                           'learner_inspection_required', 'release_authorized', 'delivery_confirmed', 'credit_awarded'}
                or type(record['schema_version']) is not int or record['schema_version'] != 1 or record['record_kind'] != 'generated_output_artifacts'
                or record['learner_inspection_required'] is not True
                or any(record[key] is not False for key in ('release_authorized', 'delivery_confirmed', 'credit_awarded'))):
            raise ValueError('Invalid record authority')
        files = record['files']
        if not isinstance(files, list) or not 1 <= len(files) <= 8 or len({f['step_name'] for f in files}) != len(files):
            raise ValueError('Invalid file identities')
        contents = {}
        for file in files:
            data = _bytes(file['data_base64'])
            if file != {'step_name': file['step_name'], **_file_record(file['filename'], file['file_type'], data)} or file['filename'] in contents:
                raise ValueError('Changed file evidence')
            contents[file['filename']] = data
        if sum(map(len, contents.values())) > MAX_TOTAL_BYTES:
            raise ValueError('Oversize files')
        valid = len(files) == 2 and {f['file_type'] for f in files} == {'pdf', 'csv'} and all(f['inspection']['parseable_and_fields_present'] for f in files)
        if record['all_required_files_parseable'] is not valid:
            raise ValueError('Changed file inspection')
        download = record['download']
        data = _bytes(download['data_base64'])
        if (set(download) != {'filename', 'file_type', 'media_type', 'sha256', 'size_bytes', 'data_base64'}
                or len(data) > MAX_TOTAL_BYTES + 65536 or download['sha256'] != hashlib.sha256(data).hexdigest()
                or download['size_bytes'] != len(data)):
            raise ValueError('Changed download evidence')
        _filename(download['filename'])
        if len(files) > 1:
            if (download['file_type'], download['media_type'], download['filename']) != ('zip', 'application/zip', 'progress-deliverables.zip'):
                raise ValueError('Missing original bundle')
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                members = bundle.infolist()
                if len(members) != len(files) or {m.filename for m in members} != set(contents):
                    raise ValueError('Changed bundle members')
                for member in members:
                    if member.file_size != len(contents[member.filename]) or member.flag_bits & 1 or bundle.read(member) != contents[member.filename]:
                        raise ValueError('Changed bundle bytes')
        elif data != next(iter(contents.values())) or download['filename'] != files[0]['filename'] or download['file_type'] != files[0]['file_type'] or download['media_type'] != MEDIA_TYPES.get(files[0]['file_type'], 'application/octet-stream'):
            raise ValueError('Changed single-file download')
        if len(json.dumps(record).encode()) > MAX_RECORD_BYTES:
            raise ValueError('Oversize record')
        return record
    except (ValueError, KeyError, TypeError, AttributeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise EnrollmentConflict('The original generated file evidence is invalid') from exc


def verify_artifacts_for_events(artifacts, events, plan):
    """Bind the preserved files to the actual approved renderer/export results."""
    from app.routers.workflows import _step_output_value
    verify_generated_artifacts(artifacts)
    completed = {item['receipt']['output_key']: item['receipt']['result'] for item in events
                 if item['receipt']['kind'] == 'stage_completed'}
    expected = []
    for key in plan['output_step_keys']:
        value = _step_output_value(completed[key])
        if not isinstance(value, dict) or value.get('type') != 'file_download':
            raise EnrollmentConflict('A completed output step did not preserve original file bytes')
        expected.append({'step_name': key, **_file_record(value.get('filename'), value.get('file_type'), _bytes(value.get('data_b64')))})
    if artifacts['files'] != expected:
        raise EnrollmentConflict('Preserved artifacts differ from the original completed output steps')
    return artifacts
