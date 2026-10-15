"""A true beginner can finish 5.0 Module 0 (M00-04).

Read from the assembled 5.0 package: the module needs no uploaded files or
earlier artifacts, says so on both surfaces, separates lab training documents
from live records before any lab is mentioned, shows one lesson count in chat,
the panel and the manifest, and does not lean on undefined technical terms.
Resume after interruption is the shared saved-position behavior covered by the
enrollment tests.
"""
import json
import re

from tests.test_certification_outcome_rubric import candidate  # noqa: F401  (fixture)

JARGON = r'\b(?:LLM|RAG|API|JSON|schema|embedding|token|vector|pipeline)\b'


def module_zero(folder):
    chat = json.loads((folder / 'lessons.json').read_text())['ai_literacy']
    panel = next(module for module in json.loads((folder / 'panel-modules.json').read_text()) if module['id'] == 'ai_literacy')
    manifest = next(module for module in json.loads((folder / 'manifest.json').read_text())['modules'] if module['id'] == 'ai_literacy')
    exercise = json.loads((folder / 'exercises.json').read_text())['ai_literacy']
    return chat, panel, manifest, exercise


def test_module_zero_needs_no_files_or_earlier_work_and_says_so(candidate):  # noqa: F811
    chat, panel, manifest, exercise = module_zero(candidate.folder)
    assert manifest['prerequisites'] == []
    assert 'needs no uploaded documents or existing workspace artifacts' in exercise['overview']
    assert 'optional' in exercise['overview'].lower()  # The one lab practice is optional and awards nothing.
    first = chat['lessons'][0]['content']
    assert 'need no files or previous artifacts' in first
    assert 'separate from live institutional records' in first
    assert panel['lessons'][0]['content'] == first


def test_lab_documents_are_separated_from_live_records_before_a_lab_is_used(candidate):  # noqa: F811
    chat, *_ = module_zero(candidate.folder)
    texts = [json.dumps(lesson) for lesson in chat['lessons']]
    boundary = next(index for index, text in enumerate(texts) if 'live institutional records' in text)
    lab = next(index for index, text in enumerate(texts) if re.search(r'Set Up Lab|course lab', text))
    assert boundary < lab


def test_both_surfaces_show_one_lesson_count(candidate):  # noqa: F811
    chat, panel, manifest, _ = module_zero(candidate.folder)
    ids = [lesson['id'] for lesson in chat['lessons']]
    assert ids == [lesson['id'] for lesson in panel['lessons']] == manifest['lesson_ids']
    assert len(ids) == 9


def test_no_undefined_technical_vocabulary(candidate):  # noqa: F811
    chat, panel, *_ = module_zero(candidate.folder)
    for lesson in chat['lessons'] + panel['lessons']:
        assert not re.search(JARGON, json.dumps(lesson)), lesson['id']
