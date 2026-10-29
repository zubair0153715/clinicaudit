"""End-to-end test for ClinicAudit v1.

Runs the real CLI against a real public website and asserts the report
contains real measured values — and that nothing is invented where a check
could not be measured. Also unit-tests the JSON-LD rating parser on a
clearly labelled SYNTHETIC fixture (parser test only, never a report).

Exit 0 = all checks pass. No message, email, or form is sent anywhere;
the CLI only performs GET requests.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REAL_SITE = "https://www.mediclinic.com"


def run_cli(*args):
    proc = subprocess.run(
        [sys.executable, "-m", "clinicaudit", *args],
        cwd=HERE, capture_output=True, text=True, timeout=120)
    return proc


def check(name, cond, detail=""):
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        raise AssertionError(name)


def main():
    # --- 1. Real site, Markdown + HTML -------------------------------
    with tempfile.TemporaryDirectory(prefix="clinicaudit-test-") as tmp:
        proc = run_cli(REAL_SITE, "--out", tmp, "--html")
        check("CLI exits 0 on real site", proc.returncode == 0, proc.stderr[-300:])
        reports = sorted(Path(tmp).glob("*.md"))
        check("Markdown report written", len(reports) == 1, str(reports))
        text = reports[0].read_text(encoding="utf-8")
        m = re.search(r"Overall score: (\d+) / 100", text)
        check("Score present and in 0-100", bool(m) and 0 <= int(m.group(1)) <= 100)
        check("Real HTTP status measured", "HTTP 200" in text)
        check("Real load time measured (ms)", bool(re.search(r"\d+ ms", text)))
        check("HTTPS result measured", "Served over HTTPS | Yes" in text
              or "Served over HTTPS | No" in text)
        check("Final URL after redirects measured",
              "https://www.mediclinic.com" in text)
        check("WhatsApp checklist present and states tool sends nothing",
              "WhatsApp response test" in text and "sends NO message" in text)
        # Reviews honesty: either a parsed rating OR the unavailable statement,
        # never both, and never a bare invented number.
        if "Reviews unavailable without API access" in text:
            check("Reviews honestly unavailable (no invented rating)",
                  "Rating (as published)" not in text)
            print("INFO reviews section: unavailable (no parsable public data)")
        else:
            check("Reviews measured with a source line",
                  "Rating (as published)" in text and "Source:" in text)
        html_reports = sorted(Path(tmp).glob("*.html"))
        check("HTML report written", len(html_reports) == 1)
        html_text = html_reports[0].read_text(encoding="utf-8")
        check("HTML report renders tables and heading",
              "<table>" in html_text and "<h1>" in html_text)
        print("INFO real-site report: %s (score %s)"
              % (reports[0].name, m.group(1)))

    # --- 2. JSON-LD parser on a SYNTHETIC fixture ---------------------
    sys.path.insert(0, str(HERE))
    from clinicaudit.checks import check_reviews
    fixture_web = {"jsonld_aggregate_rating": (4.5, 1234)}
    rev = check_reviews(fixture_web)
    check("Parser extracts fixture rating exactly",
          rev["status"] == "measured" and rev["rating"] == 4.5
          and rev["review_count"] == 1234, str(rev))
    check("Parser does not invent sentiment",
          rev["sentiment"] is None)

    # --- 3. Unreachable URL fails gracefully ---------------------------
    with tempfile.TemporaryDirectory(prefix="clinicaudit-test-") as tmp:
        proc = run_cli("https://nonexistent.invalid.example", "--out", tmp)
        check("CLI exits 0 even on unreachable site", proc.returncode == 0,
              proc.stderr[-300:])
        reports = sorted(Path(tmp).glob("*.md"))
        check("Report still written for unreachable site", len(reports) == 1)
        text = reports[0].read_text(encoding="utf-8")
        check("Unreachable site scores 0, labelled not measured",
              "Overall score: 0 / 100" in text
              and "not measured" in text)

    print("\nAll ClinicAudit end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
