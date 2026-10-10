#!/usr/bin/env python3
"""Record product changes requiring course review; never approve compatibility.

Uses committed Git trees only. A clean report means no watched paths changed,
not that a course is current or that grading has been calibrated.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 'backend/certification-data/courses/registry.json'
DEPLOYMENT_FILES = {
    '.dockerignore', '.env.example', 'setup.sh', 'upgrade.sh',
    'frontend/vite.config.ts', 'scripts/cut_release.sh',
}


def triggers(path):
    reasons = set()
    if path.startswith(('backend/certification-data/', 'backend/app/services/certification',
                        'backend/app/models/certification', 'backend/app/routers/certification',
                        'frontend/src/components/certification/', 'frontend/src/api/certification')):
        reasons.add('course_content_assessment_or_history')
    if path.startswith(('backend/app/services/chat', 'backend/app/services/tool',
                        'frontend/src/components/chat/', 'backend/app/prompts/')):
        reasons.add('agent_tools_approval_or_chat_behavior')
    if path.startswith(('backend/app/services/extraction', 'backend/app/services/workflow',
                        'backend/app/services/document', 'backend/app/services/llm',
                        'backend/app/services/model', 'backend/app/services/knowledge')):
        reasons.add('lab_execution_sources_or_model_behavior')
    if path.startswith(('frontend/src/', 'frontend/public/')):
        reasons.add('learner_controls_or_teaching_visuals')
    if (path.startswith(('backend/app/', 'backend/pyproject.toml', 'backend/uv.lock',
                         'frontend/package.json', 'frontend/package-lock.json', 'docker/', 'deploy/',
                         'charts/'))
            or path in DEPLOYMENT_FILES
            or (Path(path).name.startswith('compose.') and Path(path).suffix in ('.yaml', '.yml'))
            or Path(path).name.startswith(('Dockerfile', 'docker-compose'))):
        reasons.add('product_capabilities_or_runtime')
    return sorted(reasons)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE)


def inspect(root, base_ref, head_ref='HEAD'):
    base = git(root, 'rev-parse', '--verify', '--end-of-options', base_ref + '^{commit}').decode().strip()
    head = git(root, 'rev-parse', '--verify', '--end-of-options', head_ref + '^{commit}').decode().strip()
    changed = git(root, 'diff', '--no-renames', '--name-only', '-z', base, head, '--').decode().split('\0')
    affected = [{'path': path, 'triggers': triggers(path)} for path in sorted(filter(None, changed)) if triggers(path)]
    # Missing or invalid registry evidence is an error, not an empty course list.
    registry = json.loads(git(root, 'show', f'{head}:{REGISTRY}'))
    courses = []
    for release_id, entry in sorted(registry['releases'].items()):
        courses.append({'release_id': release_id, 'manifest_sha256': entry['manifest_sha256'],
                        'state': entry['state'], 'supported_for_existing': entry['supported_for_existing']})
    return {
        'schema_version': 1, 'kind': 'certification_product_change_review_scope',
        'base_commit': base, 'product_commit': head, 'read_only': True,
        'status': 'compatibility_review_required' if affected else 'no_watched_product_changes',
        'changed_paths': affected, 'courses': courses,
        'responsibility': {
            'accountable': 'Product release owner',
            'course_review': 'Certification maintainer for that release',
            'execution': 'Automated compatibility, assessment and visual checks; targeted review of failures',
        },
        'required_evidence': [
            'Exact product commit, course manifest and supported deployment/model configuration',
            'Affected lessons, visible controls and screenshots checked against the product',
            'Affected labs and rubrics exercised, including unavailable tools and rejected evidence',
            'Original enrollment and credential preservation verified for supported courses',
            'Recorded outcome, unresolved limits and release owner before advertising current compatibility',
        ] if affected else [],
        'interpretation': 'Review scope only. Does not verify compatibility, authorize publication, migrate learners, or create staff grading tasks. Existing release gates remain in force.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref', required=True)
    parser.add_argument('--head-ref', default='HEAD')
    args = parser.parse_args()
    try:
        report = inspect(ROOT, args.base_ref, args.head_ref)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError):
        print('Cannot establish the product comparison and course registry. No compatibility finding was produced.', file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
