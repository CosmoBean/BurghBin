#!/usr/bin/env python3
"""Sync Pittsburgh trash pickup reminders from PGH.ST to Google Calendar."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, TypedDict
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests


def env_bool(name: str, default: bool = False) -> bool:
    """Parse an environment variable as a boolean."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    """Parse an environment variable as an integer."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


HOUSE_NUMBER = os.getenv("HOUSE_NUMBER", "").strip()
STREET_NAME = os.getenv("STREET_NAME", "").strip()
ZIP_CODE = os.getenv("ZIP_CODE", "").strip()
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary").strip() or "primary"
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_CALENDAR_OWNER_EMAIL = os.getenv("GOOGLE_CALENDAR_OWNER_EMAIL", "").strip()
WEEKS_AHEAD = env_int("WEEKS_AHEAD", 4)
DRY_RUN = env_bool("DRY_RUN", default=True)
TZ = ZoneInfo("America/New_York")

PGHST_BASE_URL = "https://pgh.st"
PGHST_LOCATE_URL_TEMPLATE = f"{PGHST_BASE_URL}/locate/{{house}}/{{street}}/"
PGHST_LOCATE_WITH_ZIP_URL_TEMPLATE = (
    f"{PGHST_BASE_URL}/locate/{{house}}/{{street}}/{{zip_code}}"
)
PGHST_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://pgh.st/",
    "User-Agent": "pgh-trash-reminders/1.0",
    "X-Requested-With": "XMLHttpRequest",
}
REQUEST_TIMEOUT_SECONDS = 15
DAY_NAME_TO_INT = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
HOLIDAYS_THAT_DELAY = {
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 11),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 11),
    date(2026, 11, 26),
    date(2026, 12, 25),
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 15),
    date(2027, 3, 26),
    date(2027, 5, 31),
    date(2027, 7, 5),
    date(2027, 9, 6),
    date(2027, 11, 11),
    date(2027, 11, 25),
    date(2027, 12, 24),
}
EVENT_EMOJIS = {
    "refuse": "🗑️",
    "recycling": "♻️",
    "yard": "🌿",
}
EVENT_COLORS = {
    "refuse": "9",
    "recycling": "2",
    "yard": "5",
}
EVENT_TITLES = {
    "refuse": "Trash Pickup",
    "recycling": "Recycling Pickup",
    "yard": "Yard Waste Pickup",
}
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("pgh-trash-reminders")


class NormalizedSchedule(TypedDict):
    """Normalized pickup schedule shape used by the app."""

    address: str
    refuse_day: str | None
    recycling_day: str | None
    recycling_week: str | None
    yard_day: str | None
    yard_season: str | None
    refuse_anchor_date: date | None
    recycling_anchor_date: date | None
    yard_anchor_date: date | None
    raw: dict[str, Any]


def build_locate_url(house: str, street: str, zip_code: str = "") -> str:
    """Build the PGH.ST locate URL."""
    encoded_street = quote(street.strip(), safe="")
    if zip_code.strip():
        return PGHST_LOCATE_WITH_ZIP_URL_TEMPLATE.format(
            house=house.strip(),
            street=encoded_street,
            zip_code=zip_code.strip(),
        )
    return PGHST_LOCATE_URL_TEMPLATE.format(
        house=house.strip(),
        street=encoded_street,
    )


def fetch_schedule(house: str, street: str, zip_code: str = "") -> object:
    """Fetch the raw schedule payload from PGH.ST."""
    candidate_urls = [build_locate_url(house, street, zip_code)]
    if zip_code.strip():
        candidate_urls.append(build_locate_url(house, street))

    last_error: Exception | None = None
    for index, url in enumerate(candidate_urls, start=1):
        LOGGER.info("Fetching PGH.ST schedule from %s", url)
        response = requests.get(
            url,
            headers=PGHST_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            last_error = exc
            LOGGER.warning(
                "PGH.ST returned a non-JSON response for candidate %s/%s; trying the next URL.",
                index,
                len(candidate_urls),
            )
            continue

        LOGGER.info("Raw PGH.ST response: %s", json.dumps(payload, sort_keys=True))
        return payload

    raise RuntimeError("PGH.ST did not return JSON for any locate URL candidate.") from last_error


def parse_pghst_date(value: Any) -> date | None:
    """Parse a PGH.ST month-day-year date string."""
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.strptime(value.strip(), "%m-%d-%Y").date()


def day_index_to_name(value: Any) -> str | None:
    """Convert PGH.ST weekday indexes into human-readable names."""
    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None

    if 0 <= index < len(days):
        return days[index]
    if 1 <= index <= len(days):
        return days[index - 1]
    return None


def extract_day_name(value: Any) -> str | None:
    """Extract a weekday name from a long date string or day label."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if "," in raw:
        raw = raw.split(",", 1)[0]
    cleaned = raw.replace("pickups", "").replace("pickup", "").strip()
    return cleaned.title() if cleaned else None


def json_default(value: Any) -> str:
    """Serialize non-JSON-native values for logging."""
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def normalize_schedule(data: object) -> NormalizedSchedule:
    """Normalize the PGH.ST payload into a stable internal schedule shape."""
    if isinstance(data, list):
        if not data:
            raise ValueError("PGH.ST returned an empty schedule list.")
        record = data[0]
    elif isinstance(data, dict):
        record = data
    else:
        raise ValueError(f"Unsupported PGH.ST payload type: {type(data).__name__}")

    if not isinstance(record, dict):
        raise ValueError("PGH.ST returned a non-dictionary schedule record.")

    lowered = {str(key).lower(): value for key, value in record.items()}

    def find_field(*candidates: str) -> Any:
        for candidate in candidates:
            if candidate.lower() in lowered:
                return lowered[candidate.lower()]
        return None

    address = find_field("address")
    if not isinstance(address, str) or not address.strip():
        number = find_field("number", "house_number")
        street = find_field("street", "street_name")
        zip_code = find_field("zip", "zipcode")
        address = " ".join(str(part).strip() for part in (number, street) if part is not None)
        if zip_code not in (None, ""):
            address = f"{address}, Pittsburgh, PA {zip_code}"

    refuse_day = (
        day_index_to_name(find_field("regular_trash_pickup_day"))
        or extract_day_name(find_field("next_pickup_date_long", "refuse_date_long"))
        or extract_day_name(find_field("refuse_day", "trash_day", "pickup_day"))
    )
    recycling_day = (
        extract_day_name(find_field("next_recycling_date_long", "recycling_date_long"))
        or extract_day_name(find_field("recycling_day"))
        or refuse_day
    )
    yard_day = (
        extract_day_name(find_field("next_yard_date_long", "yard_date_long"))
        or extract_day_name(find_field("yard_day"))
        or refuse_day
    )
    recycling_week = find_field("division_sched", "recycling_week", "recycle_week")

    normalized: NormalizedSchedule = {
        "address": address.strip(),
        "refuse_day": refuse_day,
        "recycling_day": recycling_day,
        "recycling_week": None if recycling_week in (None, "") else str(recycling_week),
        "yard_day": yard_day,
        "yard_season": "March-December" if yard_day else None,
        "refuse_anchor_date": parse_pghst_date(
            find_field("next_pickup_date", "refuse_date", "trash_date")
        ),
        "recycling_anchor_date": parse_pghst_date(
            find_field("next_recycling_date", "recycling_date")
        ),
        "yard_anchor_date": parse_pghst_date(find_field("next_yard_date", "yard_date")),
        "raw": record,
    }
    return normalized


def parse_day(day_str: str | None) -> int | None:
    """Parse a weekday string into Python's weekday integer."""
    if day_str is None:
        return None
    normalized = day_str.strip().lower().replace(".", "")
    if normalized.endswith("s"):
        normalized = normalized[:-1]
    return DAY_NAME_TO_INT.get(normalized)


def get_upcoming_dates(
    day_name: str | None,
    weeks: int,
    every_other: bool = False,
    anchor_date: date | None = None,
) -> list[date]:
    """Get upcoming pickup dates for the requested weekday."""
    target_day = parse_day(day_name)
    if target_day is None or weeks <= 0:
        return []

    today = datetime.now(TZ).date()
    step_days = 14 if every_other else 7
    if anchor_date is not None:
        first_scheduled_date = anchor_date
        weekday_delta = (first_scheduled_date.weekday() - target_day) % 7
        if weekday_delta == 1:
            first_scheduled_date -= timedelta(days=1)
        elif weekday_delta:
            first_scheduled_date -= timedelta(days=weekday_delta)
        while get_actual_pickup_date(first_scheduled_date) < today:
            first_scheduled_date += timedelta(days=step_days)
    else:
        delta_days = (target_day - today.weekday()) % 7
        first_scheduled_date = today + timedelta(days=delta_days)
    return [
        get_actual_pickup_date(first_scheduled_date + timedelta(days=step_days * offset))
        for offset in range(weeks)
    ]


def is_holiday_affected(pickup_date: date) -> bool:
    """Return True when a DPW holiday delays pickup during that week."""
    start_of_week = pickup_date - timedelta(days=pickup_date.weekday())
    return any(start_of_week <= holiday <= pickup_date for holiday in HOLIDAYS_THAT_DELAY)


def get_actual_pickup_date(scheduled_date: date) -> date:
    """Shift a scheduled pickup date when a holiday delay applies."""
    if is_holiday_affected(scheduled_date):
        return scheduled_date + timedelta(days=1)
    return scheduled_date


def build_events_to_create(
    schedule: NormalizedSchedule,
    weeks_ahead: int,
) -> list[tuple[str, date]]:
    """Build the ordered list of pickup events to create."""
    events: list[tuple[str, date]] = []

    for pickup_date in get_upcoming_dates(
        schedule["refuse_day"],
        weeks_ahead,
        anchor_date=schedule["refuse_anchor_date"],
    ):
        events.append(("refuse", pickup_date))

    for pickup_date in get_upcoming_dates(
        schedule["recycling_day"],
        weeks_ahead,
        every_other=True,
        anchor_date=schedule["recycling_anchor_date"],
    ):
        events.append(("recycling", pickup_date))

    yard_dates = get_upcoming_dates(
        schedule["yard_day"],
        weeks_ahead,
        anchor_date=schedule["yard_anchor_date"],
    )
    for pickup_date in yard_dates:
        if 3 <= pickup_date.month <= 12:
            events.append(("yard", pickup_date))

    return sorted(events, key=lambda item: (item[1], item[0]))


def load_service_account_info() -> dict[str, Any]:
    """Load Google service account credentials from env JSON or a local file."""
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        LOGGER.info("Loading Google service account credentials from GOOGLE_SERVICE_ACCOUNT_JSON.")
        return json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

    if GOOGLE_SERVICE_ACCOUNT_FILE:
        LOGGER.info(
            "Loading Google service account credentials from file: %s",
            GOOGLE_SERVICE_ACCOUNT_FILE,
        )
        with open(GOOGLE_SERVICE_ACCOUNT_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)

    raise ValueError(
        "Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE before creating calendar events."
    )


def get_calendar_service() -> Any:
    """Build an authenticated Google Calendar API client."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials_info = load_service_account_info()
    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=[GOOGLE_CALENDAR_SCOPE],
    )
    if GOOGLE_CALENDAR_OWNER_EMAIL:
        credentials = credentials.with_subject(GOOGLE_CALENDAR_OWNER_EMAIL)

    return build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def event_uid(event_type: str, pickup_date: date) -> str:
    """Create a stable Google Calendar event identifier."""
    import hashlib

    raw_uid = f"pghst-{event_type}-{pickup_date.isoformat()}".encode("utf-8")
    return hashlib.md5(raw_uid, usedforsecurity=False).hexdigest()[:24]


def build_event_body(event_type: str, pickup_date: date) -> dict[str, Any]:
    """Build the Google Calendar event payload."""
    start_at = datetime(
        pickup_date.year,
        pickup_date.month,
        pickup_date.day,
        6,
        0,
        tzinfo=TZ,
    )
    end_at = start_at + timedelta(hours=1)
    emoji = EVENT_EMOJIS[event_type]
    title = EVENT_TITLES[event_type]
    return {
        "id": event_uid(event_type, pickup_date),
        "summary": f"{emoji} {title}",
        "description": (
            "Pittsburgh Department of Public Works pickup reminder.\n\n"
            "Set materials out according to local collection guidance.\n"
            "Schedule source: PGH.ST."
        ),
        "start": {
            "dateTime": start_at.isoformat(),
            "timeZone": TZ.key,
        },
        "end": {
            "dateTime": end_at.isoformat(),
            "timeZone": TZ.key,
        },
        "colorId": EVENT_COLORS[event_type],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 600},
                {"method": "popup", "minutes": 60},
            ],
        },
        "transparency": "transparent",
    }


def create_pickup_event(
    service: Any,
    event_type: str,
    pickup_date: date,
    calendar_id: str,
) -> bool | None:
    """Create an event if it does not already exist."""
    from googleapiclient.errors import HttpError

    event_id = event_uid(event_type, pickup_date)
    try:
        service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as exc:
        if getattr(exc, "status_code", None) != 404:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status != 404:
                raise
    else:
        LOGGER.info(
            "Skipping existing calendar event %s for %s on %s.",
            event_id,
            event_type,
            pickup_date.isoformat(),
        )
        return False

    event_body = build_event_body(event_type, pickup_date)
    if DRY_RUN:
        LOGGER.info(
            "DRY_RUN would create calendar event: %s",
            json.dumps(event_body, sort_keys=True),
        )
        return None

    created_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    LOGGER.info(
        "Created calendar event %s for %s on %s.",
        created_event.get("id", event_id),
        event_type,
        pickup_date.isoformat(),
    )
    return True


def main() -> None:
    """Run the application entrypoint."""
    LOGGER.info("pgh-trash-reminders starting...")

    if not HOUSE_NUMBER or not STREET_NAME:
        LOGGER.error(
            "HOUSE_NUMBER and STREET_NAME are required. Set them in your shell, "
            "local .env loader, or GitHub Actions secrets."
        )
        raise SystemExit(1)

    LOGGER.info(
        "Configured lookup address: house=%s street=%s zip=%s dry_run=%s weeks_ahead=%s calendar_id=%s",
        HOUSE_NUMBER,
        STREET_NAME,
        ZIP_CODE or "<not-set>",
        DRY_RUN,
        WEEKS_AHEAD,
        CALENDAR_ID,
    )
    LOGGER.info("Timezone configured: %s", TZ.key)
    LOGGER.info("PGH.ST locate endpoint template: %s", PGHST_LOCATE_URL_TEMPLATE)

    raw_schedule = fetch_schedule(HOUSE_NUMBER, STREET_NAME, ZIP_CODE)
    LOGGER.info("Fetched raw schedule type: %s", type(raw_schedule).__name__)
    print(json.dumps(raw_schedule, indent=2, sort_keys=True))

    normalized_schedule = normalize_schedule(raw_schedule)
    LOGGER.info(
        "Parsed schedule: %s",
        json.dumps(normalized_schedule, default=json_default, sort_keys=True),
    )
    refuse_dates = get_upcoming_dates(normalized_schedule["refuse_day"], WEEKS_AHEAD)
    LOGGER.info(
        "Upcoming refuse dates: %s",
        ", ".join(pickup_date.isoformat() for pickup_date in refuse_dates) or "<none>",
    )
    events_to_create = build_events_to_create(normalized_schedule, WEEKS_AHEAD)
    LOGGER.info("Planned pickup events: %s", len(events_to_create))
    for event_type, pickup_date in events_to_create:
        LOGGER.info("%s %s -> %s", EVENT_EMOJIS[event_type], event_type, pickup_date.isoformat())


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        LOGGER.error("%s", exc)
        sys.exit(1)
