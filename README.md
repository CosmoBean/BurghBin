# pgh-trash-reminders

Monthly GitHub Actions job that reads PGH.ST pickup data and creates that month's Google Calendar reminders.

## What it does

- Creates events only for the selected month.
- Defaults to the current month in `America/New_York`.
- Adds two reminders to each event:
  - `10:00 PM` the night before
  - `5:00 AM` the pickup day
- Optionally invites roommates from `ATTENDEE_EMAILS`.

## Google Service Account Setup

### 1. Create the Google Cloud pieces

1. Create or select a Google Cloud project.
2. Enable the `Google Calendar API`.
3. Create a service account.
4. Create and download a JSON key for that service account.

### 2. Required permissions

For a normal personal/shared calendar setup, the service account needs:

- `Google Calendar API` enabled in the project
- access to the target calendar by sharing the calendar with the service account email
- calendar permission level: `Make changes to events`

Important:

- The service account does not need a special project IAM role just to write calendar events.
- The important permission is calendar sharing, not broad Google Cloud project access.
- If you only want the service account to create/update events, `Make changes to events` is sufficient.

### 3. Optional Google Workspace impersonation

Only use this if you want the service account to act as a Workspace user instead of being directly shared on the calendar.

Required:

- enable domain-wide delegation on the service account
- authorize the scope `https://www.googleapis.com/auth/calendar` in the Workspace admin console
- set `GOOGLE_CALENDAR_OWNER_EMAIL`

If you are using a personal Google account or a directly shared calendar, leave `GOOGLE_CALENDAR_OWNER_EMAIL` empty.

## Configuration

Local env or GitHub secrets:

```bash
HOUSE_NUMBER=320
STREET_NAME="S Craig St"
ZIP_CODE=15213
CALENDAR_ID=primary
GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_CALENDAR_OWNER_EMAIL=
TARGET_MONTH=
ATTENDEE_EMAILS=
DRY_RUN=true
```

Notes:

- Use `GOOGLE_SERVICE_ACCOUNT_FILE` locally.
- Use `GOOGLE_SERVICE_ACCOUNT_JSON` in GitHub Actions.
- Leave `TARGET_MONTH` empty to generate the current month.
- Use `TARGET_MONTH=YYYY-MM` to backfill a specific month.
- `ATTENDEE_EMAILS` is a comma-separated list such as `a@example.com,b@example.com`.

## Local Run

Install:

```bash
python -m pip install -r requirements.txt
```

Dry run:

```bash
TARGET_MONTH=2026-03 DRY_RUN=true python main.py
```

Real run:

```bash
TARGET_MONTH=2026-03 DRY_RUN=false python main.py
```

## GitHub Actions

The monthly workflow is in `.github/workflows/sync.yml`.

Repository secrets to set:

- `HOUSE_NUMBER`
- `STREET_NAME`
- `ZIP_CODE`
- `CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_CALENDAR_OWNER_EMAIL`
- `ATTENDEE_EMAILS`

Behavior:

- scheduled run: first day of each month
- manual run: can override `target_month`, `attendee_emails`, and `dry_run`

## Roommate Invites

If `ATTENDEE_EMAILS` is set:

- every created event gets the same attendee list
- Google Calendar sends normal invite/update emails
- guests can see the event and other guests
- guests cannot modify the event
- guests cannot invite other people

## Troubleshooting

- `HOUSE_NUMBER and STREET_NAME are required`: set the address before running.
- `TARGET_MONTH must use YYYY-MM format`: fix the month override.
- `ATTENDEE_EMAILS contains invalid email(s)`: fix the attendee list.
- `PGH.ST did not return JSON`: verify the address and ZIP code.
- `Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE`: add credentials before running with `DRY_RUN=false`.
- Google Calendar `403` or `404`: confirm the calendar is shared with the service account and that `CALENDAR_ID` is correct.
