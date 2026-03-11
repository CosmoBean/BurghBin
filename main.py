#!/usr/bin/env python3
"""Sync Pittsburgh trash pickup reminders from PGH.ST to Google Calendar."""

from __future__ import annotations

import logging
import os
import sys
from zoneinfo import ZoneInfo


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
    f"{PGHST_BASE_URL}/locate/{{house}}/{{street}}/{{zip_code}}/"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("pgh-trash-reminders")


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
    LOGGER.info("Phase 2.1 complete; fetch logic will be added next.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        LOGGER.error("%s", exc)
        sys.exit(1)
