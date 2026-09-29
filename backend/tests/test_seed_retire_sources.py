"""Catalog upgrades remove the sources a seed retires — and only those."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from scripts.seed_catalog import retire_dropped_sources

SEED_KBS = Path(__file__).resolve().parents[1] / "seeds" / "knowledge_bases"


def _src(uuid, url, parent=None):
    return SimpleNamespace(uuid=uuid, url=url, parent_source_uuid=parent)


@pytest.mark.asyncio
async def test_removes_retired_urls_and_their_crawl_children():
    kb = SimpleNamespace(uuid="kb-1")
    sources = [
        _src("s1", "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-F"),
        _src("s2", "https://www.grants.gov/web/grants/learn-grants/grant-policies.html"),
        _src("s3", "https://www.grants.gov/some/crawled/child", parent="s2"),
        _src("s4", "https://www.cfo.gov/resources/uniform-guidance/"),
        _src("s5", "https://admin.example.edu/added-by-an-admin"),
    ]
    meta = {"retired_source_urls": [
        "https://www.cfo.gov/resources/uniform-guidance/",
        "https://www.grants.gov/web/grants/learn-grants/grant-policies.html",
    ]}
    remove = AsyncMock(return_value=True)
    with patch("app.services.knowledge_service.remove_source", remove):
        kept = await retire_dropped_sources(kb, meta, sources)

    assert sorted(c.args[1] for c in remove.await_args_list) == ["s2", "s3", "s4"]
    assert [s.uuid for s in kept] == ["s1", "s5"]


@pytest.mark.asyncio
async def test_no_retired_list_touches_nothing():
    kb = SimpleNamespace(uuid="kb-1")
    sources = [_src("s1", "https://www.cfo.gov/resources/uniform-guidance/")]
    remove = AsyncMock()
    with patch("app.services.knowledge_service.remove_source", remove):
        kept = await retire_dropped_sources(kb, {}, sources)
    remove.assert_not_awaited()
    assert kept == sources


def test_a_seed_never_retires_a_source_it_still_ships():
    for path in SEED_KBS.glob("*.json"):
        data = json.loads(path.read_text())
        retired = set(data.get("_seed_meta", {}).get("retired_source_urls") or [])
        shipped = {s.get("url") for item in data["items"] for s in item.get("sources", [])}
        assert not retired & shipped, path.name


def test_uniform_guidance_retires_the_ticketed_sources():
    data = json.loads((SEED_KBS / "uniform_guidance.json").read_text())
    retired = data["_seed_meta"]["retired_source_urls"]
    assert "https://www.cfo.gov/resources/uniform-guidance/" in retired
    assert "https://www.grants.gov/web/grants/learn-grants/grant-policies.html" in retired
