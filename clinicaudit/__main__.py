"""ClinicAudit CLI — free clinic digital-health report (lead magnet).

Usage:
    python -m clinicaudit <clinic-website-url> [--out DIR] [--html]
        [--maps-url URL] [--timeout SECONDS]

The tool only fetches public pages (read-only GET). It never sends a
WhatsApp message, email, or form submission, and never invents a rating,
review count, or score component it did not measure.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from .checks import check_reviews, check_website, whatsapp_checklist
from .report import build_html, build_report, score_website


def _slug(url):
    host = urlparse(url).netloc or "site"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-")
    return slug or "site"


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="clinicaudit",
        description="Free 1-page digital health report for a clinic website.")
    parser.add_argument("url", help="clinic website URL (https://... preferred)")
    parser.add_argument("--out", default=".",
                        help="directory for the report files (default: .)")
    parser.add_argument("--html", action="store_true",
                        help="also write an HTML version of the report")
    parser.add_argument("--maps-url", default=None,
                        help="optional public Google Maps URL to attempt a "
                             "no-key review fetch from (best effort only)")
    parser.add_argument("--timeout", type=int, default=20,
                        help="per-request timeout in seconds (default: 20)")
    args = parser.parse_args(argv)

    url = args.url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url

    web = check_website(url, timeout=args.timeout)
    reviews = check_reviews(web, maps_url=args.maps_url, timeout=args.timeout)
    total, breakdown = score_website(web)
    text = build_report(url, web, reviews, whatsapp_checklist(), total, breakdown)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    base = "audit-%s-%s" % (_slug(url), stamp)
    os.makedirs(args.out, exist_ok=True)
    md_path = os.path.join(args.out, base + ".md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("Score: %d / 100" % total)
    print("Report: %s" % md_path)
    if web.get("error"):
        print("Website note: %s" % web["error"])
    print("Reviews: %s" % reviews["status"])
    if args.html:
        html_path = os.path.join(args.out, base + ".html")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(build_html(text))
        print("HTML report: %s" % html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
