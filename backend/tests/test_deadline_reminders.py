"""Deadline reminder stages, settings and calendar files (no database)."""

import datetime
from types import SimpleNamespace

import pytest

from app.models.obligation import Obligation, ObligationSource
from app.services.deadline_reminders import (
    DEFAULT_SETTINGS,
    apply_update,
    calendar_file,
    normalize_settings,
    stage_for,
    upcoming_groups,
)

PREFS = normalize_settings({})


@pytest.mark.parametrize("days,stage", [
    (30, None), (15, None), (14, "before_14"), (10, "before_14"), (4, "before_14"),
    (3, "before_3"), (1, "before_3"), (0, "due"), (-1, "overdue"), (-121, "overdue"),
])
def test_default_stages(days, stage):
    assert stage_for(days, PREFS) == stage


def test_stages_follow_settings():
    prefs = normalize_settings({"days_before": [7], "on_due": False, "overdue": False})
    assert [stage_for(d, prefs) for d in (8, 7, 1, 0, -1)] == [None, "before_7", "before_7", None, None]
    assert stage_for(5, normalize_settings({"days_before": []})) is None


def test_settings_defaults_and_validation():
    assert normalize_settings(None) == DEFAULT_SETTINGS
    assert normalize_settings({"days_before": [3, 14, 3, 0, 999, True], "email": "yes"})["days_before"] == [14, 3]
    assert normalize_settings({"email": "yes"})["email"] is False
    assert apply_update({}, {"days_before": [1, 30, 7]})["days_before"] == [30, 7, 1]
    for bad in ({"days_before": [0]}, {"days_before": [61]}, {"days_before": "14"},
                {"days_before": [1, 2, 3, 4, 5]}, {"email": 1}, {"surprise": True}):
        with pytest.raises(ValueError):
            apply_update({}, bad)


def _ob(uuid, title, due, **kw):
    # model_construct: a Beanie Document can't be built without init_beanie.
    return Obligation.model_construct(
        uuid=uuid, project_uuid="p", kind=kw.pop("kind", "deadline"), title=title,
        due_at=datetime.datetime(due.year, due.month, due.day) if due else None, created_by="u",
        sources=[ObligationSource(document_uuid="d", document_title="Subaward.pdf", page=4,
                                  quote="Results are due within 30 days of each June 30; see § 4.2, Exhibit B.")],
        **kw,
    )


def test_calendar_file_is_valid_ical():
    ob = _ob("o1", "Semi-annual results; Year 1, Q2", datetime.date(2026, 7, 30), due_text="5:00 p.m. PT")
    text = calendar_file(
        [(ob, "NIH Subaward"), (_ob("m", "Letter", None, kind="required_material"), "NIH Subaward")],
        frontend_url="https://vz.example.edu", alarm_days=[14, 3],
        now=datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc),
    )
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == 1, "only dated deadlines become events"
    unfolded = text.replace("\r\n ", "")
    assert "SUMMARY:Semi-annual results\\; Year 1\\, Q2\r\n" in unfolded
    assert "DTSTART;VALUE=DATE:20260730" in unfolded and "DTEND;VALUE=DATE:20260731" in unfolded
    assert "Due: Jul 30\\, 2026\\, 5:00 p.m. PT" in unfolded
    assert "Subaward.pdf\\, p. 4" in unfolded
    assert "https://vz.example.edu/?deadline=o1" in unfolded
    assert unfolded.count("BEGIN:VALARM") == 2 and "TRIGGER:-P3D" in unfolded
    # RFC 5545: no line over 75 octets, every line CRLF-terminated.
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line


def test_folding_never_splits_a_multibyte_character():
    ob = _ob("o2", "Résumé review — “final” é" * 6, datetime.date(2026, 8, 1))
    text = calendar_file([(ob, "Projet")], frontend_url="", alarm_days=[])
    unfolded = text.replace("\r\n ", "")
    assert ("Résumé review — “final” é" * 6) in unfolded
    for line in text.split("\r\n"):
        line.encode("utf-8")  # every line is valid UTF-8 on its own
        assert len(line.encode("utf-8")) <= 75


def test_upcoming_groups():
    today = datetime.date(2026, 7, 16)
    d = datetime.timedelta
    obs = [_ob(str(i), f"t{i}", today + d(days=n)) for i, n in enumerate([-3, 0, 6, 7, 30, 31])]
    groups = upcoming_groups(obs, {"p": SimpleNamespace(title="P")}, today)
    assert {k: [x.ob.uuid for x in v] for k, v in groups.items()} == {
        "overdue": ["0"], "this_week": ["1", "2"], "next_30_days": ["3", "4"], "later": ["5"],
    }
