"""Measured checks for ClinicAudit.

Everything in here either measures a real, public fact about a website or
reports "not measured" with a reason. Nothing here sends a message, submits
a form, or contacts any clinic. Network access is read-only GET requests
via urllib (stdlib only).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

USER_AGENT = "ClinicAudit/1.0 (free clinic digital-health audit; read-only)"

PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
BOOKING_WORDS = re.compile(r"book|appointment|reserve|consult|contact", re.I)


class FetchResult:
    def __init__(self, url, final_url=None, status=None, elapsed_ms=None,
                 headers=None, body="", error=None):
        self.url = url
        self.final_url = final_url
        self.status = status
        self.elapsed_ms = elapsed_ms
        self.headers = headers or {}
        self.body = body
        self.error = error

    @property
    def ok(self):
        return self.error is None and self.status is not None and 200 <= self.status < 400


def fetch(url, timeout=20):
    """One read-only GET. Never POSTs, never submits anything."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000)  # cap at ~2 MB
            elapsed = (time.monotonic() - started) * 1000
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                body = raw.decode(charset, errors="replace")
            except (LookupError, ValueError):
                body = raw.decode("utf-8", errors="replace")
            return FetchResult(url, resp.geturl(), resp.status, elapsed,
                               dict(resp.headers), body)
    except urllib.error.HTTPError as exc:
        elapsed = (time.monotonic() - started) * 1000
        try:
            body = exc.read(500_000).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return FetchResult(url, exc.geturl(), exc.code, elapsed,
                           dict(exc.headers or {}), body,
                           error="HTTP %s" % exc.code)
    except Exception as exc:  # URLError, timeout, SSL, proxy failure, ...
        elapsed = (time.monotonic() - started) * 1000
        return FetchResult(url, None, None, elapsed, {},
                           error="%s: %s" % (type(exc).__name__, exc))


class _PageParser(HTMLParser):
    """Collects only structural facts: title, viewport, links, forms, JSON-LD."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self.viewport = False
        self.links = []          # href strings
        self.forms = []          # dicts: action, text
        self._in_form = False
        self._form_text = ""
        self._form_action = ""
        self._in_jsonld = False
        self._jsonld_text = ""
        self.jsonld_blocks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and attrs.get("name", "").lower() == "viewport":
            self.viewport = True
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        elif tag == "form":
            self._in_form = True
            self._form_text = ""
            self._form_action = attrs.get("action", "")
        elif tag == "script" and attrs.get("type", "") == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_text = ""

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "form" and self._in_form:
            self.forms.append({"action": self._form_action,
                               "text": self._form_text.strip()})
            self._in_form = False
        elif tag == "script" and self._in_jsonld:
            self.jsonld_blocks.append(self._jsonld_text)
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_form:
            self._form_text += " " + data
        if self._in_jsonld:
            self._jsonld_text += data


def _find_aggregate_rating(blocks):
    """Return (rating, review_count) from schema.org JSON-LD, or (None, None).

    Only data the site itself publishes is used. Malformed blocks are skipped.
    """
    for block in blocks:
        try:
            data = json.loads(block.strip())
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            agg = item.get("aggregateRating")
            if isinstance(agg, dict):
                try:
                    rating = float(agg.get("ratingValue"))
                except (TypeError, ValueError):
                    continue
                try:
                    count = int(str(agg.get("reviewCount")).replace(",", ""))
                except (TypeError, ValueError):
                    count = None
                return rating, count
    return None, None


def check_website(url, timeout=20):
    """Section 1: website check. All values measured from one GET."""
    fetched = fetch(url, timeout=timeout)
    result = {
        "requested_url": url,
        "reachable": fetched.ok,
        "status": fetched.status,
        "final_url": fetched.final_url,
        "https": bool(fetched.final_url
                       and urlparse(fetched.final_url).scheme == "https"),
        "load_time_ms": (round(fetched.elapsed_ms)
                         if fetched.elapsed_ms is not None else None),
        "page_bytes": len(fetched.body.encode("utf-8", errors="ignore")),
        "error": fetched.error,
    }
    if not fetched.ok or not fetched.body:
        result.update({
            "title": None, "viewport": None, "phone_link_found": None,
            "whatsapp_link_found": None, "form_count": None,
            "booking_form_found": None,
        })
        return result

    parser = _PageParser()
    try:
        parser.feed(fetched.body)
    except Exception:
        pass  # malformed HTML: keep whatever was collected before the error

    tel_links = [h for h in parser.links if h.lower().startswith("tel:")]
    wa_links = [h for h in parser.links
                if "wa.me" in h.lower() or "whatsapp.com" in h.lower()
                or "whatsapp:" in h.lower()]
    booking_forms = [f for f in parser.forms
                     if BOOKING_WORDS.search(f["action"] or "")
                     or BOOKING_WORDS.search(f["text"] or "")]
    result.update({
        "title": parser.title.strip() or None,
        "viewport": parser.viewport,
        "phone_link_found": bool(tel_links),
        "phone_link_count": len(tel_links),
        "whatsapp_link_found": bool(wa_links),
        "whatsapp_link_count": len(wa_links),
        "form_count": len(parser.forms),
        "booking_form_found": bool(booking_forms),
        "jsonld_aggregate_rating": _find_aggregate_rating(parser.jsonld_blocks),
    })
    return result


def check_reviews(website_result, maps_url=None, timeout=20):
    """Section 2: Google reviews sentiment.

    Honest rule: a rating is reported ONLY if it was actually parsed from a
    public page. Otherwise this returns status 'unavailable' with the reason,
    and no rating, count, or sentiment is invented.
    """
    rating, count = website_result.get("jsonld_aggregate_rating") or (None, None)
    if rating is not None:
        return {
            "status": "measured",
            "source": "clinic website schema.org aggregateRating markup",
            "rating": rating,
            "review_count": count,
            "sentiment": None,  # a bare rating is not a sentiment analysis
            "note": ("Rating/count copied exactly from the site's own published "
                     "markup; no review text was read and no sentiment was "
                     "inferred."),
        }
    if maps_url:
        fetched = fetch(maps_url, timeout=timeout)
        if fetched.ok and fetched.body:
            # Google Maps pages are JS-heavy; only accept an explicit,
            # human-readable "4.5 (1,234 reviews)" style pattern.
            m = re.search(
                r"([0-5](?:\.[0-9])?)\s*\(\s*([\d,]+)\s+reviews?\s*\)",
                fetched.body)
            if m:
                try:
                    return {
                        "status": "measured",
                        "source": "public Google Maps page (no login, no API key)",
                        "rating": float(m.group(1)),
                        "review_count": int(m.group(2).replace(",", "")),
                        "sentiment": None,
                        "note": ("Parsed from the public page text; no review "
                                 "text was read and no sentiment inferred."),
                    }
                except ValueError:
                    pass
            return {
                "status": "unavailable",
                "source": "public Google Maps page (no login, no API key)",
                "rating": None, "review_count": None, "sentiment": None,
                "note": ("Page fetched but no parsable rating/review count was "
                         "found (Maps pages usually need JavaScript or a "
                         "Places API key for full review data)."),
            }
        return {
            "status": "unavailable",
            "source": "public Google Maps page (no login, no API key)",
            "rating": None, "review_count": None, "sentiment": None,
            "note": "Maps page could not be fetched: %s" % (fetched.error,),
        }
    return {
        "status": "unavailable",
        "source": None,
        "rating": None, "review_count": None, "sentiment": None,
        "note": ("Reviews unavailable without API access: no rating markup was "
                 "published on the clinic website, and no public Maps URL was "
                 "supplied. Use the Google Places API (needs a key) for full "
                 "review coverage. No rating, count, or sentiment is claimed."),
    }


def whatsapp_checklist():
    """Section 3: manual checklist. The tool NEVER sends a WhatsApp message."""
    return [
        "Open the clinic's own published WhatsApp link/number (from its "
        "website or listing) in your own WhatsApp app.",
        "Send a short test message as a prospective patient, e.g. asking for "
        "appointment timings. Do this yourself — ClinicAudit sends nothing.",
        "Record the time you sent it and the time of the first human reply.",
        "Note whether you got an auto-reply, a human reply, or no reply "
        "within 2 hours / 24 hours.",
        "Score the experience yourself: reply speed, clarity, and whether "
        "booking was offered. This section is a manual record, not a tool "
        "measurement.",
    ]
