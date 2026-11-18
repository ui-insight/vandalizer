"""Award highlights for a PI: fixed facts, real sources, no guessed address.

Support ticket #1200 (email highlights of an FDP subaward to the PI).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import award_highlights as ah
from app.services.extraction_sources import SOURCE_KEY

DOC_TEXT = (
    "FDP Cost Reimbursement Subaward. Pass-through Entity: Colorado State University. "
    "PTE Principal Investigator: Dr. Ana Ruiz, ana.ruiz@colostate.edu. "
    "Subrecipient: University of Idaho. Subrecipient Principal Investigator: Dr. Lee Park, lpark@uidaho.edu. "
    "Amount Funded This Action: $148,500. Period of Performance 09/01/2025 to 08/31/2027."
)


def _src(page: int, support: str = "supported") -> dict:
    return {"quote": "q", "page": page, "verified": support != "unverified", "support": support}


def _entity(**overrides) -> dict:
    values = {
        "Total award amount": "$148,500",
        "Period of performance start": "09/01/2025",
        "Period of performance end": "08/31/2027",
        "Pass-through entity institution": "Colorado State University",
        "Pass-through entity principal investigator name": "Dr. Ana Ruiz",
        "Pass-through entity principal investigator email": "ana.ruiz@colostate.edu",
        "Subrecipient institution": "University of Idaho",
        "Subrecipient principal investigator name": "Dr. Lee Park",
        "Subrecipient principal investigator email": "lpark@uidaho.edu",
    }
    values.update(overrides)
    entity = {k: v for k, v in values.items() if v is not None}
    entity[SOURCE_KEY] = {k: _src(1) for k in entity}
    return entity


def _doc(text: str = DOC_TEXT):
    return SimpleNamespace(uuid="DOC1", title="FDP Subaward.pdf", raw_text=text, text_markers=[], processing=False)


def _reader(email="rita@uidaho.edu", institutions=("University of Idaho",)):
    return {"name": "Rita Admin", "email": email, "institutions": list(institutions)}


def _result(entity=None, reader=None, doc=None):
    return ah.build_result(entity if entity is not None else _entity(), doc or _doc(), reader or _reader())


def test_the_same_facts_are_asked_for_every_time_in_email_order():
    assert [f["label"] for f in _result()["facts"]] == [
        "Award amount", "Start date", "End date", "Reporting deadlines", "Invoicing rules", "Key terms",
    ]
    assert ah.extract_keys()[:6] == [k for k, _l, _d in ah.FACT_FIELDS]


def test_a_found_fact_carries_its_page_and_a_missing_one_is_not_found():
    facts = {f["label"]: f for f in _result()["facts"]}
    assert facts["Award amount"]["value"] == "$148,500"
    assert facts["Award amount"]["page"] == 1
    assert facts["Reporting deadlines"]["value"] is None


def test_a_value_with_no_passage_in_the_document_is_not_found_not_shown():
    entity = _entity()
    entity[SOURCE_KEY]["Total award amount"] = _src(1, "unverified")
    del entity[SOURCE_KEY]["Period of performance start"]
    facts = {f["label"]: f for f in _result(entity)["facts"]}
    assert facts["Award amount"]["value"] is None
    assert facts["Start date"]["value"] is None
    assert facts["End date"]["value"] == "08/31/2027"


@pytest.mark.parametrize("stated", ["Not found", "N/A", "", None])
def test_the_models_own_not_found_answers_stay_not_found(stated):
    facts = {f["label"]: f for f in _result(_entity(**{"Total award amount": stated}))["facts"]}
    assert facts["Award amount"]["value"] is None


def test_the_pi_at_the_readers_institution_is_suggested():
    result = _result()
    assert [p["role"] for p in result["pis"]] == ["pass_through", "recipient"]
    assert result["suggested_pi"] == 1
    assert result["suggestion_reason"] == "your_institution"
    assert result["pis"][1]["email"] == "lpark@uidaho.edu"


def test_the_institution_name_alone_is_enough_to_suggest():
    entity = _entity(**{"Subrecipient principal investigator email": None,
                        "Pass-through entity principal investigator email": None})
    result = _result(entity, _reader(email="rita@gmail.com", institutions=["The University of Idaho"]))
    assert result["suggested_pi"] == 1
    assert result["pis"][1]["email"] is None


def test_the_reader_chooses_when_neither_or_both_pis_match():
    assert _result(reader=_reader(email="x@example.org", institutions=[]))["suggested_pi"] is None
    both = _entity(**{"Pass-through entity principal investigator email": "ana@uidaho.edu"})
    text = DOC_TEXT.replace("ana.ruiz@colostate.edu", "ana@uidaho.edu")
    assert _result(both, doc=_doc(text))["suggested_pi"] is None


def test_a_single_pi_is_the_one_addressed():
    entity = _entity(**{"Pass-through entity principal investigator name": None})
    result = _result(entity, _reader(email="x@example.org", institutions=[]))
    assert len(result["pis"]) == 1
    assert (result["suggested_pi"], result["suggestion_reason"]) == (0, "only_one")


def test_an_address_that_is_not_written_in_the_document_is_never_offered():
    entity = _entity(**{"Subrecipient principal investigator email": "lee.park@uidaho.edu"})  # plausible, invented
    assert _result(entity)["pis"][1]["email"] is None


def test_something_that_is_not_an_address_is_never_offered():
    entity = _entity(**{"Subrecipient principal investigator email": "see contact page"})
    assert _result(entity)["pis"][1]["email"] is None


@pytest.mark.asyncio
async def test_build_reads_one_document_with_sources_and_meters_the_call():
    engine = MagicMock()
    engine.extract.return_value = [_entity()]
    user = SimpleNamespace(user_id="u1", name="Rita Admin", email="rita@uidaho.edu", organization_id=None, current_team=None)
    scope = MagicMock()
    scope.__aenter__ = AsyncMock()
    scope.__aexit__ = AsyncMock(return_value=False)
    config = MagicMock()
    config.model_dump.return_value = {}
    with patch("app.services.extraction_engine.ExtractionEngine", return_value=engine), \
         patch("app.services.config_service.get_user_model_name", AsyncMock(return_value="model-x")), \
         patch("app.models.system_config.SystemConfig.get_config", AsyncMock(return_value=config)), \
         patch("app.services.metering.metered_async", return_value=scope) as metered:
        result = await ah.build(_doc(), user)

    kwargs = engine.extract.call_args.kwargs
    assert kwargs["capture_sources"] is True
    assert kwargs["doc_texts"] == [DOC_TEXT]
    assert kwargs["doc_metadata"][0]["uuid"] == "DOC1"
    assert metered.call_args.args[0] == "award_highlights"
    assert result["document"] == {"uuid": "DOC1", "title": "FDP Subaward.pdf"}
    assert result["sender_name"] == "Rita Admin"


@pytest.mark.asyncio
async def test_a_document_that_is_still_being_read_says_so():
    doc = SimpleNamespace(uuid="D", title="t", raw_text="", text_markers=[], processing=True)
    with pytest.raises(ah.HighlightsError) as err:
        await ah.build(doc, SimpleNamespace(user_id="u1"))
    assert err.value.status == 409
    assert "still being read" in err.value.message
