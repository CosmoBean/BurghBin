# pgh-trash-reminders

PGH.ST trash, recycling, and yard waste pickup reminders created in Google Calendar by a monthly GitHub Actions job.

## Architecture

```text
GitHub Actions (monthly cron or manual)
        |
        v
      main.py
        |
        +-- PGH.ST /locate/{house}/{street}/{zip}
        |
        +-- month-scoped pickup date generation + holiday delay handling
        |
        +-- Google Calendar API v3
```

## What It Creates

The workflow creates events only for the selected month. By default, that is the current month in `America/New_York`.

| Event type | Frequency | Color | Summary | Reminders |
| --- | --- | --- | --- | --- |
| Trash | Weekly | Blueberry (`9`) | `🗑️ Trash Pickup` | 10 PM previous night, 5 AM pickup day |
| Recycling | Every other week | Sage (`2`) | `♻️ Recycling Pickup` | 10 PM previous night, 5 AM pickup day |
| Yard waste | Weekly in season | Banana (`5`) | `🌿 Yard Waste Pickup` | 10 PM previous night, 5 AM pickup day |

If `ATTENDEE_EMAILS` is configured, the same roommate invite list is added to every event and Google Calendar sends normal invitation emails.

## Setup

### 1. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 2. Create a Google Cloud service account

1. Create or select a Google Cloud project.
2. Enable the Google Calendar API.
3. Create a service account and download its JSON key.
4. Share your Google Calendar with the service account email.
5. If you need domain-wide delegation, set `GOOGLE_CALENDAR_OWNER_EMAIL`.

### 3. Configure local environment

Copy `.env.example` into your preferred local env loader, or export the values directly:

```bash
export HOUSE_NUMBER=320
export STREET_NAME="S Craig St"
export ZIP_CODE=15213
export CALENDAR_ID=primary
export GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
export TARGET_MONTH=2026-03
export ATTENDEE_EMAILS="roommate1@example.com,roommate2@example.com"
export DRY_RUN=true
```

Notes:

- Leave `TARGET_MONTH` empty to generate the current month automatically.
- Use `GOOGLE_SERVICE_ACCOUNT_JSON` instead of `GOOGLE_SERVICE_ACCOUNT_FILE` in GitHub Actions.
- Leave `ATTENDEE_EMAILS` empty if you do not want to invite roommates.

### 4. Run locally

Dry run for the current month:

```bash
python main.py
```

Dry run for a specific month:

```bash
TARGET_MONTH=2026-03 DRY_RUN=true python main.py
```

Real run:

```bash
TARGET_MONTH=2026-03 DRY_RUN=false python main.py
```

## GitHub Actions Setup

Add these GitHub repository secrets:

- `HOUSE_NUMBER`
- `STREET_NAME`
- `ZIP_CODE`
- `CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_CALENDAR_OWNER_EMAIL`
- `ATTENDEE_EMAILS`

The monthly workflow lives at `.github/workflows/sync.yml`.

Behavior:

- Scheduled run: creates events for the current month on the first day of each month.
- Manual run: can override `target_month`, `attendee_emails`, and `dry_run`.

## Local Development

Useful commands:

```bash
python -m py_compile main.py
python -c "import main"
pytest
TARGET_MONTH=2026-03 ATTENDEE_EMAILS="roommate1@example.com,roommate2@example.com" DRY_RUN=true HOUSE_NUMBER=320 STREET_NAME="S Craig St" ZIP_CODE=15213 python main.py
```

## Holiday Handling

The script includes Pittsburgh DPW holiday delays for 2025 through 2027:

- New Year's Day
- Martin Luther King Jr. Day
- Presidents' Day
- Good Friday
- Memorial Day
- Independence Day
- Labor Day
- Veterans Day
- Thanksgiving
- Christmas

If a listed holiday falls between Monday of a collection week and the scheduled pickup day, the pickup is shifted by one day. Month filtering is based on the actual shifted pickup date.

## Roommate Invites

Attendee behavior:

- The same `ATTENDEE_EMAILS` list is applied to every created event.
- Guests can see the event and other guests.
- Guests cannot modify the event.
- Guests cannot invite other people.
- Google Calendar sends normal invitation/update emails when events are created.

If you change the attendee list after events already exist, rerunning the workflow will skip those existing events because event IDs remain stable.

## Troubleshooting

- `HOUSE_NUMBER and STREET_NAME are required`: set the lookup address before running the script.
- `TARGET_MONTH must use YYYY-MM format`: fix the manual month override before rerunning.
- `ATTENDEE_EMAILS contains invalid email(s)`: correct the attendee list formatting before rerunning.
- `PGH.ST did not return JSON`: verify the address is a City of Pittsburgh pickup address and that `ZIP_CODE` matches.
- `Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE`: add one of the Google credential sources before running with `DRY_RUN=false`.
- Google Calendar 403 or 404 errors: confirm the calendar is shared with the service account and `CALENDAR_ID` is correct.
