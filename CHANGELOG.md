# Changelog

## Unreleased

- Scaffolded the Python project, environment template, and MIT license.
- Added a live PGH.ST client with normalization against the current response fields.
- Implemented pickup date generation, holiday delay handling, and dry-run event planning.
- Added Google Calendar service account auth and idempotent event creation logic.
- Added GitHub Actions workflows for scheduled syncs and validation.
- Switched calendar generation to month-scoped runs with `TARGET_MONTH`.
- Added roommate attendee invites with view-only guest permissions.
- Updated reminder timings to 10 PM the night before and 5 AM on pickup day.
- Added pytest coverage for month filtering, holiday carryover, and attendee payloads.
