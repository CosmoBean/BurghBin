#!/usr/bin/env python3
"""Sync Pittsburgh trash pickup reminders from PGH.ST to Google Calendar."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime
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


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        LOGGER.error("%s", exc)
        sys.exit(1)
