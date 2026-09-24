"""A KB source can be marked as amending others.

Support ticket: a KB held NSF PAPPG Chapter IV and a supplement revising it.
Asked plainly — "Which proposal types are excluded from reconsideration under
the current policy?" — chat answered from Chapter IV's list, because that list
is the best semantic match for the question. The supplement's "Chapter
IV.D.2.b.(7) is revised to remove reconsideration for all SBIR/STTR proposals"
only surfaced when the user named the supplement's file. With the relation
recorded, retrieving Chapter IV brings the supplement's passage along, labelled
as the one that governs.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_service, kb_validation_service
from app.services.kb_validation_service import AmendmentLinks, RAGConfig

BASE, SUPP = "src-chapter-iv", "src-supplement-1"


def _chunk(source_id: str, name: str, i: int, text: str = "") -> dict:
    return {
        "content": text or f"{name} passage {i}",
        "metadata": {"source_id": source_id, "source_name": name},
        "chunk_id": f"{source_id}_chunk_{i}",
        "score": 0.1 * i,
        "similarity": 0.9 - 0.05 * i,
    }


BASE_LIST = _chunk(
    BASE, "NSF_PAPPG_24-1_Chapter_IV_snapshot.pdf", 0,
    "Reconsideration is not available for ... Phase I SBIR/STTR proposals ...",
)
SUPP_LINE = _chunk(
    SUPP, "NSF_PAPPG_24-1_Supplement_1_consolidated.pdf", 3,
    "Section 9. Chapter IV.D.2.b.(7) is revised to remove reconsideration for all SBIR/STTR proposals.",
)

LINKS = AmendmentLinks(
    amenders_of={BASE: [SUPP]},
    search_ids={SUPP: [SUPP]},
    amends_names={SUPP: ["NSF PAPPG 24-1 Chapter IV"]},
    amender_name={SUPP: "NSF PAPPG 24-1 Supplement 1"},
)


def _find_returning(*batches):
    """KnowledgeBaseSource.find(...).to_list() returning each batch in turn."""
    calls = iter(batches)

    def find(*_a, **_k):
        return SimpleNamespace(to_list=AsyncMock(return_value=next(calls)))

    return find


def _src(uuid, amends=(), parent=None, name=None):
    return SimpleNamespace(
        uuid=uuid, amends_source_uuids=list(amends), parent_source_uuid=parent,
        custom_name=name, url_title=None, document_title=None, url=None, document_uuid=None,
    )


# ---------------------------------------------------------------------------
# Loading the relation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_links_cover_crawled_children_on_both_sides():
    """A crawled URL's chunks carry its children's uuids, so a link to (or
    from) a crawl parent must reach them too."""
    supp = _src("supp", amends=["base"], name="Supplement 1")
    related = [
        supp, _src("supp-child", parent="supp"),
        _src("base", name="Chapter IV"), _src("base-child", parent="base"),
    ]
    find = _find_returning([supp], related)
    with patch.object(kb_validation_service.KnowledgeBaseSource, "find", side_effect=find):
        links = await kb_validation_service.load_amendment_links("kb-1")

    assert links.amenders_of == {"base": ["supp"], "base-child": ["supp"]}
    assert sorted(links.search_ids["supp"]) == ["supp", "supp-child"]
    assert links.amends_names["supp-child"] == ["Chapter IV"]


@pytest.mark.asyncio
async def test_a_link_to_a_missing_source_is_ignored():
    supp = _src("supp", amends=["gone"])
    find = _find_returning([supp], [supp])
    with patch.object(kb_validation_service.KnowledgeBaseSource, "find", side_effect=find):
        links = await kb_validation_service.load_amendment_links("kb-1")
    assert links.is_empty()


@pytest.mark.asyncio
async def test_a_failed_lookup_degrades_to_plain_retrieval():
    with patch.object(kb_validation_service.KnowledgeBaseSource, "find", side_effect=RuntimeError("mongo down")):
        links = await kb_validation_service.load_amendment_links("kb-1")
    assert links.is_empty()


# ---------------------------------------------------------------------------
# Retrieving amenders
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieving_the_amended_source_searches_its_amender_only():
    dm = MagicMock()
    dm.query_kb.return_value = [SUPP_LINE]
    with patch.object(kb_validation_service, "_get_dm", return_value=dm):
        hits = await kb_validation_service.retrieve_amendment_chunks(
            "kb-1", [BASE_LIST], "excluded from reconsideration?", LINKS, min_similarity=0.2,
        )
    assert hits == [SUPP_LINE]
    dm.query_kb.assert_called_once_with(
        "kb-1", "excluded from reconsideration?", kb_validation_service.AMENDMENT_CHUNKS_PER_SOURCE,
        0.2, where={"source_id": SUPP},
    )


@pytest.mark.asyncio
async def test_nothing_is_searched_when_no_amended_source_was_retrieved():
    dm = MagicMock()
    other = _chunk("src-other", "Chapter III.pdf", 0)
    with patch.object(kb_validation_service, "_get_dm", return_value=dm):
        hits = await kb_validation_service.retrieve_amendment_chunks("kb-1", [other], "q", LINKS)
    assert hits == []
    dm.query_kb.assert_not_called()


# ---------------------------------------------------------------------------
# Chat: the plain question now reaches the supplement
# ---------------------------------------------------------------------------

def _general_pool():
    # What the plain question retrieves: Chapter IV and its neighbours, never
    # the supplement.
    return [BASE_LIST] + [_chunk(BASE, "NSF_PAPPG_24-1_Chapter_IV_snapshot.pdf", i) for i in range(1, 5)] + [
        _chunk(f"src-other-{i}", f"Chapter III part {i}.pdf", i) for i in range(10)
    ]


async def _chat_segment(links: AmendmentLinks, dm_hits: list[dict]):
    dm = MagicMock()
    dm.query_kb.return_value = dm_hits
    with patch.object(kb_validation_service, "_ensure_system_config_loaded", new=AsyncMock()), \
         patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(_general_pool(), RAGConfig(k=8), 0))), \
         patch.object(kb_validation_service, "load_amendment_links", new=AsyncMock(return_value=links)), \
         patch.object(kb_validation_service, "_get_dm", return_value=dm), \
         patch("app.services.knowledge_service.resolve_openable_documents", new=AsyncMock(return_value={})):
        return await chat_service._build_kb_segment(
            "kb-1", "Which proposal types are excluded from reconsideration under the current policy?",
            "test-model",
        )


@pytest.mark.asyncio
async def test_plain_question_brings_the_amending_passage_with_its_label():
    segment, sources = await _chat_segment(LINKS, [SUPP_LINE])

    assert SUPP_LINE["chunk_id"] in [s["chunk_id"] for s in sources]
    assert len(sources) == 8
    text = segment.text
    assert "NSF_PAPPG_24-1_Supplement_1_consolidated.pdf" in text
    assert "amends: NSF PAPPG 24-1 Chapter IV" in text
    assert "amended by: NSF PAPPG 24-1 Supplement 1" in text
    assert "the amending source states the current rule" in text


@pytest.mark.asyncio
async def test_without_the_relation_the_plain_question_misses_the_supplement():
    """The ticket as it was: nothing tells retrieval to look at the supplement."""
    segment, sources = await _chat_segment(AmendmentLinks(), [SUPP_LINE])

    assert SUPP_LINE["chunk_id"] not in [s["chunk_id"] for s in sources]
    assert "amends:" not in segment.text
    assert "the amending source states the current rule" not in segment.text


# ---------------------------------------------------------------------------
# Headless answers (Autovalidate) get the same behaviour, so it can be measured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_headless_answer_includes_amendment_within_k():
    run = MagicMock(output="All SBIR/STTR proposals.")
    run.usage = MagicMock(return_value=None)
    agent = MagicMock()
    agent.run = AsyncMock(return_value=run)
    dm = MagicMock()
    dm.query_kb.return_value = [SUPP_LINE]
    pool = _general_pool()[:4]

    with patch.object(kb_validation_service, "retrieve_kb_chunks",
                      new=AsyncMock(return_value=(pool, RAGConfig(k=4), 0))), \
         patch.object(kb_validation_service, "load_amendment_links", new=AsyncMock(return_value=LINKS)), \
         patch.object(kb_validation_service, "_get_dm", return_value=dm), \
         patch.object(kb_validation_service, "_get_or_build_agent", return_value=agent):
        answer, results, _ = await kb_validation_service._generate_kb_answer(
            "kb-1", "Which proposal types are excluded from reconsideration?", "test-model",
            config=RAGConfig(k=4),
        )

    assert len(results) == 4
    assert results[-1]["chunk_id"] == SUPP_LINE["chunk_id"]
    prompt = agent.run.await_args.args[0]
    assert "amends: NSF PAPPG 24-1 Chapter IV" in prompt
    assert "the amending source states the current rule" in prompt


# ---------------------------------------------------------------------------
# Setting the relation
# ---------------------------------------------------------------------------

def _kb():
    return SimpleNamespace(uuid="kb-1")


def _source_model(find_one_result, find=None):
    """Stand-in for the Beanie model: field expressions need an initialised one."""
    model = MagicMock()
    model.find_one = AsyncMock(return_value=find_one_result)
    if find is not None:
        model.find = find
    return model


@pytest.mark.asyncio
async def test_set_amends_rejects_self_and_foreign_sources():
    from app.services import knowledge_service

    source = _src("supp")
    source.save = AsyncMock()
    with patch.object(knowledge_service, "KnowledgeBaseSource", _source_model(source)):
        with pytest.raises(ValueError, match="cannot amend itself"):
            await knowledge_service.set_source_amends(_kb(), "supp", ["supp"])

    model = _source_model(source, MagicMock(side_effect=_find_returning([_src("base")])))
    with patch.object(knowledge_service, "KnowledgeBaseSource", model):
        with pytest.raises(ValueError, match="other-kb-source"):
            await knowledge_service.set_source_amends(_kb(), "supp", ["base", "other-kb-source"])
    source.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_amends_replaces_the_list_and_dedupes():
    from app.services import knowledge_service

    source = _src("supp", amends=["old"])
    source.save = AsyncMock()
    model = _source_model(source, MagicMock(side_effect=_find_returning([_src("base"), _src("faq")])))
    with patch.object(knowledge_service, "KnowledgeBaseSource", model):
        out = await knowledge_service.set_source_amends(_kb(), "supp", ["base", "faq", "base", ""])

    assert out.amends_source_uuids == ["base", "faq"]
    source.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_empty_list_clears_the_relation_without_a_lookup():
    from app.services import knowledge_service

    source = _src("supp", amends=["base"])
    source.save = AsyncMock()
    model = _source_model(source, MagicMock())
    with patch.object(knowledge_service, "KnowledgeBaseSource", model):
        await knowledge_service.set_source_amends(_kb(), "supp", [])

    assert source.amends_source_uuids == []
    model.find.assert_not_called()


# ---------------------------------------------------------------------------
# Export / import keep the relation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_relinks_amends_to_the_new_source_uuids():
    """The importer mints new uuids, so links are rebuilt through the
    exported ones; a link to a source that did not come across is dropped."""
    import itertools

    from app.services import knowledge_service

    counter = itertools.count(1)
    created: list = []

    def make_source(**kw):
        src = SimpleNamespace(uuid=f"new-{next(counter)}", amends_source_uuids=[], **kw)
        src.save = AsyncMock()
        created.append(src)
        return src

    kb = SimpleNamespace(uuid="kb-new", insert=AsyncMock())
    dm = MagicMock()
    dm.add_to_kb.return_value = 3
    payload = {
        "format_version": 1,
        "title": "NSF PAPPG",
        "sources": [
            {"uuid": "old-base", "source_type": "document", "content": "Chapter IV text", "custom_name": "Chapter IV"},
            {"uuid": "old-supp", "source_type": "document", "content": "Supplement text",
             "custom_name": "Supplement 1", "amends_source_uuids": ["old-base", "old-not-exported"]},
        ],
    }
    user = SimpleNamespace(user_id="u1", current_team=None)

    with patch.object(knowledge_service, "KnowledgeBase", MagicMock(return_value=kb)), \
         patch.object(knowledge_service, "KnowledgeBaseSource", MagicMock(side_effect=make_source)), \
         patch.object(knowledge_service.name_conflicts, "next_available_name", new=AsyncMock(return_value="NSF PAPPG")), \
         patch.object(knowledge_service, "_insert_source_unless_duplicate", new=AsyncMock(return_value=True)), \
         patch.object(knowledge_service, "_get_dm", return_value=dm), \
         patch.object(knowledge_service, "recalculate_stats", new=AsyncMock()), \
         patch.object(knowledge_service.currency, "stamp_ingested"):
        await knowledge_service.import_knowledge_base(payload, user)

    base, supp = created
    assert (base.custom_name, supp.custom_name) == ("Chapter IV", "Supplement 1")
    assert supp.amends_source_uuids == [base.uuid]
    assert base.amends_source_uuids == []


@pytest.mark.asyncio
async def test_export_carries_uuid_and_amends():
    from app.services import knowledge_service

    supp = SimpleNamespace(
        uuid="supp", amends_source_uuids=["base"], source_type="url", document_uuid=None,
        url="https://nsf.gov/supp", url_title="Supplement 1", custom_name=None, content="text",
        crawl_enabled=False, max_crawl_pages=5, parent_source_uuid=None, crawled_urls=None,
    )
    kb = MagicMock(uuid="kb-1", title="NSF", description="", tags=[])
    with patch.object(knowledge_service, "require_kb_sources", new=AsyncMock()), \
         patch.object(knowledge_service, "get_kb_sources", new=AsyncMock(return_value=[supp])), \
         patch.object(knowledge_service.currency, "export_provenance", return_value={}):
        out = await knowledge_service.export_knowledge_base(kb)

    exported = out["sources"][0]
    assert exported["uuid"] == "supp"
    assert exported["amends_source_uuids"] == ["base"]
