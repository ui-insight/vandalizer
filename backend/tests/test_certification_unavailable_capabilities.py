"""An unavailable product capability never becomes a v5 requirement (GRADE-12).

The palette marks nodes the product does not offer. Read that list from the
editor so a newly disabled node is checked too, then confirm the v5 rubric,
cases and checkers cannot require one. Prose may still tell learners a node is
unavailable; the legacy rubric is preserved as released and is excluded.
"""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / 'backend/certification-data/drafts/v5.0'
PALETTE = ROOT / 'frontend/src/components/workspace/WorkflowEditorPanel.tsx'
CHECKERS = ROOT / 'backend/app/services/certification_versions'


def disabled_nodes():
    entries = re.findall(r"\{ name: '([A-Za-z]+)', label: '([^']+)'[^\n]*enabled: false", PALETTE.read_text())
    assert entries, 'The palette no longer marks disabled nodes the way this check expects'
    return entries


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def test_the_palette_still_lists_the_known_unavailable_nodes():
    assert {'CodeNode', 'PackageBuilder'} <= {name for name, _ in disabled_nodes()}


def test_no_v5_passing_condition_names_an_unavailable_node():
    contract = json.loads((DRAFT / 'outcomes.json').read_text())
    conditions = [condition for module in contract['modules'] for outcome in module['outcomes']
                  for condition in outcome['passing_conditions']]
    assert conditions
    for name, label in disabled_nodes():
        pattern = re.compile('|'.join(re.escape(term) for term in {name, label, label.replace(' ', '')}), re.I)
        assert not [condition for condition in conditions if pattern.search(condition)], name


def test_no_v5_case_or_exercise_uses_an_unavailable_node_as_a_structured_value():
    names = {name for name, _ in disabled_nodes()}
    for path in sorted(DRAFT.glob('*.json')):
        # Single-token strings are identifiers (task types, rules, ids); prose may mention a node.
        tokens = {value for value in strings(json.loads(path.read_text())) if ' ' not in value}
        assert not tokens & names, (path.name, tokens & names)


def test_no_v5_checker_references_an_unavailable_node():
    names = {name for name, _ in disabled_nodes()}
    for path in sorted(CHECKERS.rglob('*.py')):
        if path.parent.name == 'rubrics' and path.name.startswith('legacy_'):
            continue  # legacy grading is preserved exactly as released
        found = {name for name in names if re.search(rf"['\"]{name}['\"]", path.read_text())}
        assert not found, (path.name, found)
