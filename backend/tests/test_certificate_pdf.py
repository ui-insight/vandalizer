"""Downloadable certification certificate (support ticket: banner-only, nothing to print)."""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fitz
import pytest
from fastapi import HTTPException

from app.routers import certification as router
from app.services.certificate_pdf import render_certificate_pdf


def _text(pdf: bytes) -> str:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert doc.page_count == 1
        return doc[0].get_text()


def test_certificate_carries_name_date_and_level():
    pdf = render_certificate_pdf(
        name="Ada Lovelace",
        level="architect",
        certified_at=datetime.datetime(2026, 9, 4, tzinfo=datetime.timezone.utc),
        credential_id="1A2B3C4D",
    )
    text = _text(pdf)
    assert "Ada Lovelace" in text
    assert "September 4, 2026" in text
    assert "Architect level" in text
    assert "Vandal Workflow Architect" in text
    assert "1A2B3C4D" in text


def test_long_name_stays_on_the_page():
    name = "Maximiliana Theodora Wilhelmina Featherstonehaugh-Cholmondeley"
    pdf = render_certificate_pdf(
        name=name, level="architect",
        certified_at=datetime.datetime(2026, 9, 4), credential_id="X",
    )
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        hits = page.search_for(name)
        assert hits, "name not rendered in one piece"
        assert all(page.rect.contains(r) for r in hits)


@pytest.mark.parametrize(
    "name",
    [
        "Ada Lovelace",
        "Nguyễn Văn A",  # Vietnamese: outside Latin-1, garbled by Helvetica (#954)
        "Ада Лавлейс",  # Cyrillic
        "張三",  # CJK: rendered blank by Helvetica (#954)
        "김민준",  # Hangul
        "やまだ たろう",  # Kana
    ],
)
def test_non_latin1_name_round_trips_and_is_drawn(name):
    pdf = render_certificate_pdf(
        name=name, level="architect",
        certified_at=datetime.datetime(2026, 9, 4), credential_id="X",
    )
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        assert name in page.get_text()
        hits = page.search_for(name)
        assert hits, "name not rendered in one piece"
        # Text extraction alone passes for invisible glyphs too, so check the
        # name's box actually has ink: at least some dark pixels.
        box = hits[0]
        pix = page.get_pixmap(clip=box, dpi=72, colorspace=fitz.csGRAY)
        dark = sum(1 for v in pix.samples if v < 128)
        assert dark > 0.05 * pix.width * pix.height, f"name box is blank for {name!r}"


def _user(**kw):
    return SimpleNamespace(user_id="u1", name=None, email=None, **kw)


def _prog(certified: bool):
    return SimpleNamespace(
        id="66f0c0ffee0000000000abcd",
        certified=certified,
        certified_at=datetime.datetime(2026, 9, 4) if certified else None,
        level="architect",
    )


async def test_endpoint_refuses_uncertified_user():
    with patch.object(router.svc, "get_progress", AsyncMock(return_value=_prog(False))):
        with pytest.raises(HTTPException) as exc:
            await router.download_certificate(user=_user())
    assert exc.value.status_code == 404


async def test_endpoint_returns_pdf_named_for_the_user():
    with patch.object(router.svc, "get_progress", AsyncMock(return_value=_prog(True))):
        res = await router.download_certificate(user=SimpleNamespace(user_id="u1", name=None, email="ada@uidaho.edu"))
    assert res.media_type == "application/pdf"
    assert "attachment" in res.headers["content-disposition"]
    text = _text(res.body)
    assert "ada@uidaho.edu" in text
    assert "0000ABCD" in text
