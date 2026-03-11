# pgh-trash-reminders

PGH.ST trash, recycling, and yard waste pickup reminders synced to Google Calendar on a GitHub Actions schedule.

## Architecture

```text
GitHub Actions (cron or manual)
        |
        v
      main.py
        |
        +-- PGH.ST /locate/{house}/{street}/{zip}
        |
        +-- pickup date generation + holiday delay handling
        |
        +-- Google Calendar API v3
```

## What It Creates

| Event type | Frequency | Color | Summary | Reminders |
| --- | --- | --- | --- | --- |
| Trash | Weekly | Blueberry (`9`) | `🗑️ Trash Pickup` | 8 PM night before, 5 AM day of |
| Recycling | Every other week | Sage (`2`) | `♻️ Recycling Pickup` | 8 PM night before, 5 AM day of |
| Yard waste | Weekly in season | Banana (`5`) | `🌿 Yard Waste Pickup` | 8 PM night before, 5 AM day of |

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
export HOUSE_NUMBER=626
export STREET_NAME="Bellefonte St"
export ZIP_CODE=15232
export CALENDAR_ID=primary
export GOOGLE_SERVICE_ACCOUNT_FILE=./service-account.json
export WEEKS_AHEAD=4
export DRY_RUN=true
```

You can also use `GOOGLE_SERVICE_ACCOUNT_JSON` instead of `GOOGLE_SERVICE_ACCOUNT_FILE`.

### 4. Run locally

Dry run:

```bash
python main.py
```

Real run:

```bash
DRY_RUN=false python main.py
```

## GitHub Actions Setup

Add these GitHub repository secrets:

- `HOUSE_NUMBER`
- `STREET_NAME`
- `ZIP_CODE`
- `CALENDAR_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_CALENDAR_OWNER_EMAIL`

The scheduled workflow lives at `.github/workflows/sync.yml`.

Manual runs are available through `workflow_dispatch`, with `dry_run` and `weeks_ahead` inputs.

## Local Development

Useful commands:

```bash
python -m py_compile main.py
python -c "import main"
DRY_RUN=true HOUSE_NUMBER=626 STREET_NAME="Bellefonte St" ZIP_CODE=15232 python main.py
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

If a listed holiday falls between Monday of a collection week and the scheduled pickup day, the pickup is shifted by one day.

## Troubleshooting

- `HOUSE_NUMBER and STREET_NAME are required`: set the lookup address before running the script.
- `PGH.ST did not return JSON`: verify the address is a City of Pittsburgh pickup address and that `ZIP_CODE` matches.
- `Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE`: add one of the Google credential sources before running with `DRY_RUN=false`.
- Google Calendar 403 or 404 errors: confirm the calendar is shared with the service account and `CALENDAR_ID` is correct.
