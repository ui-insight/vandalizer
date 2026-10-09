"""Real Git comparisons catch additions/removals without inspecting workspaces."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('product_changes', Path(__file__).resolve().parents[2] / 'scripts/inspect_certification_product_changes.py')
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode().strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, 'init')
    git(tmp_path, 'config', 'user.name', 'Synthetic QA')
    git(tmp_path, 'config', 'user.email', 'qa@example.test')
    path = tmp_path / changes.REGISTRY
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'releases': {'original': {'state': 'published', 'manifest_sha256': 'a' * 64, 'supported_for_existing': True},
                                          'new-draft': {'state': 'draft', 'manifest_sha256': 'b' * 64, 'supported_for_existing': False}}}))
    git(tmp_path, 'add', '.')
    git(tmp_path, 'commit', '-m', 'Synthetic base')
    return tmp_path, git(tmp_path, 'rev-parse', 'HEAD')


def commit(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Synthetic change')


def test_product_change_requires_review_preserving_exact_course_and_commit_identity(repository):
    root, base = repository
    commit(root, 'backend/app/services/chat_tools.py', 'Changed approval behavior')
    report = changes.inspect(root, base)
    assert report['status'] == 'compatibility_review_required'
    assert report['product_commit'] == git(root, 'rev-parse', 'HEAD') and report['base_commit'] == base
    assert report['changed_paths'][0]['triggers'] == ['agent_tools_approval_or_chat_behavior', 'product_capabilities_or_runtime']
    assert len(report['courses']) == 2 and report['required_evidence']
    assert report['read_only'] and 'Does not verify compatibility' in report['interpretation']
    assert git(root, 'status', '--porcelain') == ''


def test_deleted_and_renamed_controls_remain_in_review_scope(repository):
    root, _ = repository
    commit(root, 'frontend/src/components/OldControl.tsx', 'Saved control')
    base = git(root, 'rev-parse', 'HEAD')
    git(root, 'mv', 'frontend/src/components/OldControl.tsx', 'frontend/src/components/NewControl.tsx')
    git(root, 'commit', '-m', 'Rename control')
    report = changes.inspect(root, base)
    assert [item['path'] for item in report['changed_paths']] == ['frontend/src/components/NewControl.tsx', 'frontend/src/components/OldControl.tsx']


def test_notes_and_uncommitted_files_do_not_become_product_evidence(repository):
    root, base = repository
    commit(root, 'docs/work-notes.md', 'Notes only')
    draft = root / 'frontend/src/Draft.tsx'
    draft.parent.mkdir(parents=True)
    draft.write_text('Uncommitted code is not part of the comparison')
    report = changes.inspect(root, base)
    assert report['status'] == 'no_watched_product_changes'
    assert report['changed_paths'] == [] and report['required_evidence'] == []
    assert 'Uncommitted code' in draft.read_text()


def test_unknown_git_revision_fails_instead_of_returning_no_changes(repository):
    root, _ = repository
    with pytest.raises(subprocess.CalledProcessError):
        changes.inspect(root, 'not-a-commit')


@pytest.mark.parametrize('path', ['backend/app/new_capability.py', 'backend/uv.lock', 'frontend/package-lock.json',
                                 'frontend/public/course.png', 'backend/certification-data/courses/new/lessons.json',
                                 'Dockerfile', 'docker-compose.yml'])
def test_runtime_new_capabilities_course_content_and_visuals_trigger_review(path):
    assert changes.triggers(path)
