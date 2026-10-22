"""No persistence case can disappear or duplicate between deterministic CI shards."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('certification_shards', Path(__file__).resolve().parents[2] / 'scripts/run_certification_integration.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_shards_are_disjoint_exhaustive_stable_and_preserve_parameterized_cases():
    nodes = [f'tests/integration/test_certification_case.py::test_saved_work[{index}]' for index in range(1000)]
    shards = [runner.select_shard(nodes, index, 4) for index in range(4)]
    assert len([node for shard in shards for node in shard]) == len(nodes)
    assert set().union(*(set(shard) for shard in shards)) == set(nodes)
    for index, shard in enumerate(shards):
        assert shard == runner.select_shard(list(reversed(nodes)), index, 4)
        extended = runner.select_shard(nodes + ['tests/integration/test_certification_new.py::test_new'], index, 4)
        assert set(shard) <= set(extended)


@pytest.mark.parametrize('index,count', [(-1, 4), (4, 4), (0, 0), (0, -1)])
def test_invalid_shard_does_not_silently_skip_cases(index, count):
    with pytest.raises(ValueError):
        runner.select_shard(['example'], index, count)


def test_duplicate_collected_cases_are_rejected():
    with pytest.raises(ValueError, match='unique'):
        runner.select_shard(['example', 'example'], 0, 1)
