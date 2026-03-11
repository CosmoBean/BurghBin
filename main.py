#!/usr/bin/env python3
"""Sync Pittsburgh trash pickup reminders from PGH.ST to Google Calendar."""

from __future__ import annotations

import json
import logging
import os
import sys
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


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        LOGGER.error("%s", exc)
        sys.exit(1)
