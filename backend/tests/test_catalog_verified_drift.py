"""The catalog's two ``verified`` flags must not drift apart.

A retired seed keeps its row with verified=False; re-seeding re-attaches the
catalog entry and must restore the flag, and the listing must not advertise a
row whose document still says False (prod ticket, 2026-08-26: "Knowledge base
not found or not accessible" on a catalog KB)."""

from unittest.mock import MagicMock

from app.services.verification_service import catalog_row_is_openable
from scripts.seed_catalog import _reinstate_verified


def _doc(verified):
    d = MagicMock()
    d.verified = verified
    return d


def test_reinstate_restores_a_retired_row_and_reports_the_change():
    doc = _doc(False)
    assert _reinstate_verified(doc) is True
    assert doc.verified is True


def test_reinstate_leaves_a_verified_row_alone():
    doc = _doc(True)
    assert _reinstate_verified(doc) is False
    assert doc.verified is True


def test_listing_hides_a_verified_item_whose_document_is_unverified():
    item = MagicMock()
    item.verified = True
    assert catalog_row_is_openable(item, _doc(False)) is False
    assert catalog_row_is_openable(item, _doc(True)) is True


def test_listing_passes_rows_without_a_loaded_document():
    item = MagicMock()
    item.verified = True
    assert catalog_row_is_openable(item, None) is True


def test_listing_passes_unverified_library_items_regardless():
    item = MagicMock()
    item.verified = False
    assert catalog_row_is_openable(item, _doc(False)) is True
