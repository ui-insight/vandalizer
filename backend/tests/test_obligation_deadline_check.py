"""A deadline is checked against its source in full: year, time and zone (#1013 §2).

``check_deadline`` is pure; the MongoDB-backed path through ``propose`` and
``save_checked`` is covered in tests/integration/test_obligations_mongodb.py.
"""

import datetime

import pytest

from app.services.obligation_service import check_deadline

NOTICE = "The sponsor submission deadline is November 19, 2026 at 5:00 p.m. Pacific Time."


def _ok(due, quotes, due_text=None):
    checked, reason = check_deadline(due, due_text, quotes)
    assert reason is None, reason
    return checked


def _rejected(due, quotes, due_text=None):
    checked, reason = check_deadline(due, due_text, quotes)
    assert checked is None
    return reason


def test_the_issue_reproduction_is_rejected():
    # Wrong year and wrong time, despite a real quote: used to be accepted.
    reason = _rejected("2027-11-19T09:00:00+00:00", NOTICE)
    assert "not the time the quote states" in reason


def test_wrong_year_is_rejected():
    assert "November 19, 2026, not 2027" in _rejected("2027-11-19", NOTICE)
    assert "not 2027" in _rejected("2027-11-19T17:00", NOTICE)


def test_wrong_time_is_rejected():
    assert "does not state 09:00" in _rejected("2026-11-19T09:00", NOTICE)


def test_stated_date_and_time_are_kept_as_written():
    checked = _ok("2026-11-19T17:00", NOTICE)
    assert checked["due_at"] == datetime.datetime(2026, 11, 19, 17, 0)
    assert checked["due_text"] == "5:00 p.m. Pacific Time"


@pytest.mark.parametrize("due", [
    "2026-11-20T01:00:00+00:00",  # 5 p.m. PST is 01:00 UTC the next day
    "2026-11-19T20:00:00-05:00",  # the same instant in Eastern
])
def test_an_equivalent_instant_in_another_zone_is_accepted_and_stored_in_the_sources_zone(due):
    checked = _ok(due, NOTICE)
    # Stored as the source writes it, so the inbox shows Nov 19, not Nov 20.
    assert checked["due_at"] == datetime.datetime(2026, 11, 19, 17, 0)
    assert checked["due_at"].tzinfo is None


def test_daylight_time_uses_the_offset_in_force_on_that_date():
    quote = "Proposals are due June 3, 2026 by 5:00 PM ET."
    assert _ok("2026-06-03T21:00:00+00:00", quote)["due_at"] == datetime.datetime(2026, 6, 3, 17, 0)
    assert "not the time" in _rejected("2026-06-03T22:00:00+00:00", quote)


def test_an_offset_is_not_accepted_when_the_source_names_no_zone():
    quote = "Applications are due November 19, 2026 at 5:00 p.m."
    assert "without a time zone" in _rejected("2026-11-20T01:00:00+00:00", quote)
    assert "without a time zone" in _rejected("2026-11-19T17:00:00-08:00", quote)
    # As written, without inventing the zone, is fine.
    assert _ok("2026-11-19T17:00", quote)["due_text"] == "5:00 p.m."


def test_local_time_is_not_a_resolvable_zone():
    quote = "Due November 19, 2026 at 5:00 p.m. local time."
    assert "without a time zone" in _rejected("2026-11-19T17:00:00-08:00", quote)
    assert _ok("2026-11-19T17:00", quote)["due_text"] == "5:00 p.m. local time"


def test_a_time_the_source_does_not_give_is_not_added():
    quote = "Final reports are due December 31, 2026."
    assert "states no time of day" in _rejected("2026-12-31T17:00", quote)
    checked = _ok("2026-12-31", quote)
    assert checked["due_at"] == datetime.datetime(2026, 12, 31)
    assert checked["due_text"] is None


def test_a_missing_year_is_not_invented():
    quote = "Letters of intent are due November 2 at noon Eastern Time."
    assert "without a year" in _rejected("2026-11-02T12:00", quote)
    # A publication year alone does not establish the deadline's year.
    assert _rejected("2026-11-02T12:00", quote + " Program Solicitation NSF 26-512, issued 2026.")


def test_day_month_and_numeric_forms_carry_their_year():
    assert _ok("2026-11-19", "Deadline: 19 November 2026.")
    assert "not 2027" in _rejected("2027-11-19", "Deadline: 19 November 2026.")
    assert _ok("2026-11-19", "Due 11/19/2026.")
    assert "not 2027" in _rejected("2027-11-19", "Due 11/19/26.")


def test_noon_and_24_hour_times():
    assert _ok("2026-11-09T12:00", "The institutional review deadline is November 9, 2026 at noon Pacific Time.")
    assert _ok("2026-11-09T17:00", "Due 2026-11-09 17:00 UTC.")


def test_an_amendment_is_checked_against_its_own_quote():
    amended = "The new sponsor deadline is November 19, 2026 at 5:00 p.m. Pacific Time."
    original = "The sponsor deadline is November 12, 2026 at 5:00 p.m. Pacific Time."
    assert _ok("2026-11-19T17:00", amended)
    assert "does not state November 19" in _rejected("2026-11-19T17:00", original)


def test_due_text_must_come_from_the_quote():
    assert "copied from the quote" in _rejected("2026-11-19T17:00", NOTICE, due_text="5:00 p.m. Eastern Time")
    assert _ok("2026-11-19T17:00", NOTICE, due_text="5:00 p.m. Pacific Time")["due_text"] == "5:00 p.m. Pacific Time"


def test_does_not_borrow_a_time_from_another_deadline():
    quote = ('Internal approval is November 12, 2026 at noon Pacific Time. '
             'Sponsor submission is November 19, 2026 at 5:00 p.m. Pacific Time.')
    assert 'multiple' in _rejected('2026-11-19T12:00', quote)


def test_unrelated_year_does_not_establish_the_deadline_year():
    quote = 'Letters are due November 2 at noon Eastern Time. This program was established in 2026.'
    assert 'year' in _rejected('2026-11-02T12:00', quote)


def test_does_not_add_seconds_the_quote_never_gave():
    assert 'precision' in _rejected('2026-11-19T17:00:59', NOTICE)


def test_does_not_accept_a_different_time_from_due_text():
    quote = 'Due November 19, 2026 at 5:00 p.m. Pacific Time. Help desk closes at noon Pacific Time.'
    assert _rejected('2026-11-19T17:00', quote, 'noon Pacific Time')


def test_explicit_standard_time_is_not_silently_changed_to_daylight_time():
    quote = 'Due June 3, 2026 at 5:00 PM PST.'
    assert _rejected('2026-06-04T00:00:00+00:00', quote)
    assert _ok('2026-06-04T01:00:00+00:00', quote)['due_at'] == datetime.datetime(2026, 6, 3, 17)


def test_invalid_iso_suffix_is_not_discarded():
    assert _rejected('2026-11-19garbage', 'Due November 19, 2026 at midnight Pacific Time.')
