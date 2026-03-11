from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


SAMPLE_RAW_SCHEDULE = {
    "division": "EASTERN",
    "division_sched": 0,
    "holiday_cancellation": False,
    "hood": "Shadyside",
    "next_pickup_date": "3-11-2026",
    "next_pickup_date_long": "Wednesday, March 11th",
    "next_recycling": "The next pickup is trash only.",
    "next_recycling_date": "3-11-2026",
    "next_recycling_date_long": "Wednesday, March 11th",
    "next_yard_date": "4-25-2026",
    "next_yard_date_long": "Saturday, April 25th",
    "number": "626",
    "other_cancellation": False,
    "regular_trash_pickup_day": 2,
    "street": "BELLEFONTE ST",
    "zip": 15232,
}


def test_parse_target_month_explicit() -> None:
    month_start, month_end = main.parse_target_month("2026-03")

    assert month_start == date(2026, 3, 1)
    assert month_end == date(2026, 3, 31)


def test_parse_attendee_emails_dedupes_and_trims() -> None:
    attendees = main.parse_attendee_emails(
        " roommate1@example.com,roommate2@example.com,ROOMMATE1@example.com "
    )

    assert attendees == [
        {"email": "roommate1@example.com"},
        {"email": "roommate2@example.com"},
    ]


def test_parse_attendee_emails_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="ATTENDEE_EMAILS contains invalid email"):
        main.parse_attendee_emails("roommate1@example.com,not-an-email")


def test_build_event_body_with_attendees_includes_guest_rules_and_reminders() -> None:
    body = main.build_event_body_with_attendees(
        "refuse",
        date(2026, 3, 11),
        [{"email": "roommate1@example.com"}],
    )

    assert body["attendees"] == [{"email": "roommate1@example.com"}]
    assert body["guestsCanModify"] is False
    assert body["guestsCanInviteOthers"] is False
    assert body["guestsCanSeeOtherGuests"] is True
    assert body["reminders"]["overrides"] == [
        {"method": "popup", "minutes": 480},
        {"method": "popup", "minutes": 60},
    ]


def test_build_events_to_create_limits_results_to_target_month() -> None:
    normalized_schedule = main.normalize_schedule([SAMPLE_RAW_SCHEDULE])

    events = main.build_events_to_create(
        normalized_schedule,
        date(2026, 3, 1),
        date(2026, 3, 31),
    )

    assert events == [
        ("refuse", date(2026, 3, 4)),
        ("recycling", date(2026, 3, 11)),
        ("refuse", date(2026, 3, 11)),
        ("refuse", date(2026, 3, 18)),
        ("recycling", date(2026, 3, 25)),
        ("refuse", date(2026, 3, 25)),
    ]


def test_get_month_pickup_dates_includes_holiday_shifted_pickup() -> None:
    july_pickups = main.get_month_pickup_dates(
        "Monday",
        date(2027, 7, 1),
        date(2027, 7, 31),
    )

    assert july_pickups[0] == date(2027, 7, 6)
