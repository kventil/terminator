# Termin_ator CLI

CLI to interact with the onlinepraxistermine.de (from https://med.blackt-cms.de/) iframe portal using endpoints captured in `spec.html`.

## Install

- Python 3.9+
- Install deps and entrypoint:

```
pip install -e .
```

## Usage

You can run after install (`termin-ator ...`) or without install:
`PYTHONPATH=src python3 -m termin_ator.cli ...`

No subcommand provided defaults to `availability` (lists available dates per doctor):
```
termin-ator --portal S55299BD3
```

Environment variables:
- `TERMIN_PORTAL` – portal code (default `S55299BD3`)
- `TERMIN_COOKIE` – full Cookie header if required (session + `XSRF-TOKEN`)
- `TERMIN_XSRF_TOKEN` – value for header `X-XSRF-TOKEN`

Common commands:
- List doctors:
```
termin-ator --portal S55299BD3 doctors
```
- List available dates per doctor (quick overview):
```
termin-ator --portal S55299BD3 availability
```
- Fetch available dates for one doctor:
```
termin-ator --portal S55299BD3 \
  --doctor USER-1-DOC-1 --insurance Gesetzlich --visitreason Spezial dates
```
- Confirm a booking for an appointment id:
```
termin-ator 314602 --portal S55299BD3 \
  --xsrf "$TERMIN_XSRF_TOKEN" --cookie "$TERMIN_COOKIE" confirm
```

Tips:
- Add `--dry-run` to print the request without sending.
- The CLI automatically bootstraps cookies and the XSRF token by visiting the iframe page; if that fails or you get 403/419, pass `--cookie` and `--xsrf` manually (grab from your browser).
- If you hit TLS issues during local testing, try `--insecure` (not recommended for production).

Notes:
- Base host is `https://onlinepraxistermine.de`; portal path is `/<PORTAL>`.
- Slot/time-of-day endpoints vary and may require authenticated flows; this CLI currently focuses on listing dates and confirming bookings captured in `spec.html`.

## Fetch cookies & XSRF token

Use the helper script to bootstrap headers automatically from the iframe page:

```
# Prints shell exports
python3 scripts/get_tokens.py --portal S55299BD3

# Export into current shell
eval "$(python3 scripts/get_tokens.py --portal S55299BD3)"

# JSON output
python3 scripts/get_tokens.py --portal S55299BD3 --format json
```

Then pass them to the CLI (optional if auto-auth works in your environment):

```
termin-ator dates --portal S55299BD3 --doctor USER-1-DOC-1 \
  --insurance Gesetzlich --visitreason Spezial \
  --xsrf "$TERMIN_XSRF_TOKEN" --cookie "$TERMIN_COOKIE"
```

## Examples

- All available dates for a specific doctor:
```
termin-ator dates --portal S55299BD3 \
  --doctor USER-1-DOC-1 --insurance Gesetzlich --visitreason Spezial
```

- Check for new available dates every 30 minutes (shell script):
```
bash scripts/check_dates.sh \
  PORTAL=S55299BD3 \
  DOCTOR=USER-1-DOC-1 \
  INSURANCE=Gesetzlich \
  VISITREASON=Spezial
```
The script prints current dates initially, then prints only newly appeared dates on subsequent checks. Set `INTERVAL=900` to check every 15 minutes, and set `INSECURE=1` to skip TLS verification if needed.

- macOS notifications on new dates:
```
bash scripts/check_dates.sh PORTAL=S55299BD3 DOCTOR=USER-1-DOC-1 NOTIFY=1
```
Shows a system notification listing newly available dates (up to 5) with the doctor name as subtitle. Requires `osascript` (built into macOS).

## Book an Appointment

This portal splits booking into two phases: creating an appointment (selecting a slot) and confirming it. The provided spec includes the confirmation endpoint; slot selection/creation varies per portal.

1) Discover options
- List doctors:
```
termin-ator --portal S55299BD3 doctors
```
- Find available dates for your doctor:
```
termin-ator --portal S55299BD3 \
  --doctor USER-1-DOC-1 --insurance Gesetzlich --visitreason Spezial dates
```

2) Create an appointment (get `appointment_id`)
- Use the website UI to select a time slot, then copy the `appointment_id` from your browser’s DevTools → Network (the response of the booking/create request).
- Alternatively, provide the API endpoint for slot creation (from a HAR) and we can add a `book` command to automate this step.

3) Confirm the appointment
```
termin-ator  --portal S55299BD3 \
  --xsrf "$TERMIN_XSRF_TOKEN" --cookie "$TERMIN_COOKIE" confirm <APPOINTMENT_ID>
```
- Tokens are usually auto-fetched; if you see 403/419, run:
```
eval "$(python3 scripts/get_tokens.py --portal S55299BD3)"
```

If you share the slot selection endpoint (from a HAR capture), we will extend the CLI with a `book` command to perform step 2 programmatically.
