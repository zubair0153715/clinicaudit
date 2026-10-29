# ClinicAudit v1 — free clinic digital health report

REA-style glue tool: fragmented public checks + one interface + one unified
report. Built as a **lead magnet** for an AI automation agency: the audit is
free, and any paid setup afterwards is sold by a human, separately. **This
tool itself never sells, contacts, or messages anyone.**

## Install

Python 3.10+ only. No third-party dependencies — standard library only
(`urllib`, `html.parser`, `json`).

```bash
cd clinicaudit
python3 -m clinicaudit --help
```

## Usage

```bash
python3 -m clinicaudit <clinic-website-url> [--out DIR] [--html] \
    [--maps-url URL] [--timeout SECONDS]
```

Example:

```bash
python3 -m clinicaudit https://www.mediclinic.com --out ./audits --html
```

This writes `audit-<domain>-<date>.md` (and `.html` with `--html`) into
`--out` and prints the score + report path. The score is 0–100.

## What each check measures

| Section | What is actually measured |
|---|---|
| Website check | One read-only GET: reachable (HTTP status), final URL after redirects, HTTPS or not, page-load time in ms, page size, page title, mobile `viewport` meta tag, `tel:` links, WhatsApp links (`wa.me` / `whatsapp.com`), forms on the page, and whether any form looks like a booking/contact form. |
| Score | Transparent sum of 6 components: reachable 25, HTTPS 20, viewport 15, load < 3s 15 (7 if < 6s), a contact channel found 15, booking form 10. A component that could not be measured scores 0 and is labelled "not measured" — never guessed. |
| Google reviews sentiment | A rating is reported **only** if it was actually parsed from a public page: either schema.org `aggregateRating` markup published on the clinic's own website, or — if `--maps-url` is given — an explicit "4.5 (1,234 reviews)" pattern on the public Maps page. Otherwise the section says **"Reviews unavailable without API access"** and claims no rating, count, or sentiment. No review text is read and no sentiment is inferred from a bare rating. |
| WhatsApp response test | A **manual checklist** for the owner/auditor to do by hand (message the clinic's published WhatsApp, record reply time/type). The tool sends nothing. |

## Honest limits

- Only the URL given (usually the homepage) is fetched. Inner pages, booking
  flows, and real reply behaviour are not tested by the tool.
- Review coverage is partial without a Google Places API key. Maps pages are
  usually JavaScript-heavy, so a no-key fetch often cannot parse a rating —
  that is reported as unavailable, not faked.
- Scores measure public website facts only. They are not a judgement of
  medical quality, and a high score does not mean a good clinic.
- Network failures (timeouts, proxy errors, bot blocks) are reported as
  "not measured" with the real error, not retried aggressively and never
  bypassed.

## Hard rules (by design)

- **No outbound contact:** no WhatsApp messages, emails, or form submissions
  to any clinic. Research-only. The only network calls are GET requests.
- **No fake data:** no invented scores, ratings, review counts, testimonials,
  or clinic facts. If a check cannot run, it says so.
- **No logins, no bot-check bypasses.** Public pages only.
- **No secrets:** no API keys, passwords, or personal data in code, reports,
  or logs. (Phone numbers found on a site are reported as counts only, never
  copied into the report.)
- **Local only:** no GitHub push, no deploy, no publishing in v1.

## Test

```bash
python3 test_end_to_end.py
```

Runs the CLI end-to-end against a real public clinic-group website
(Mediclinic), verifies the report renders with real measured values, verifies
the reviews section is honestly "unavailable" when nothing parsable exists,
verifies the JSON-LD rating parser on a labelled synthetic fixture, and
verifies graceful failure on an unreachable URL.
