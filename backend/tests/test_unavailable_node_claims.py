"""Replies that explain how to add an unavailable workflow node are sent back once.

The labelled corpus is real model output from live certification runs, not
phrases written to match the pattern.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from app.services.approval_claims import describes_unavailable_node, require_available_nodes

CORPUS = json.loads((Path(__file__).parent / 'fixtures/unavailable_node_replies.json').read_text())['replies']


@pytest.mark.parametrize('row', CORPUS, ids=[f"run-{row['run']}" for row in CORPUS])
def test_only_fabricated_instructions_are_flagged(row):
    assert describes_unavailable_node(row['reply']) is row['fabricated_instructions']


def test_other_unavailable_nodes_and_unrelated_replies():
    assert describes_unavailable_node('Click **+ Add Step** and choose the Package Builder step to bundle the files.')
    assert not describes_unavailable_node('Package Builder is not available, so use a Data Export step instead.')
    assert not describes_unavailable_node('Add an extraction step, then a prompt step that formats the table.')


def context(output_deps=None, partial=False):
    return SimpleNamespace(deps=output_deps, partial_output=partial)


def test_the_validator_retries_once_per_turn_and_ignores_partials():
    fabricated = next(row['reply'] for row in CORPUS if row['fabricated_instructions'])
    honest = next(row['reply'] for row in CORPUS if not row['fabricated_instructions'])
    deps = SimpleNamespace(unavailable_node_retry_used=False)
    assert require_available_nodes(context(deps, partial=True), fabricated) == fabricated
    assert require_available_nodes(context(deps), honest) == honest
    with pytest.raises(ModelRetry, match='not available'):
        require_available_nodes(context(deps), fabricated)
    assert deps.unavailable_node_retry_used is True
    assert require_available_nodes(context(deps), fabricated) == fabricated
