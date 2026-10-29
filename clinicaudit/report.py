"""Score + report rendering for ClinicAudit.

The score is a transparent sum of measured components only. Any component
that could not be measured scores 0 and is labelled "not measured" — it is
never guessed.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

# (label, max points, how it is earned)
COMPONENTS = [
    ("Website reachable", 25),
    ("Served over HTTPS", 20),
    ("Mobile viewport meta present", 15),
    ("Page loads in under 3s (partial under 6s)", 15),
    ("A contact channel found (phone, WhatsApp, or form)", 15),
    ("Booking/contact form found", 10),
]


def score_website(web):
    """Return (total, breakdown) where breakdown is a list of dicts."""
    breakdown = []
    if not web.get("reachable"):
        for label, max_pts in COMPONENTS:
            breakdown.append({"component": label, "points": 0, "max": max_pts,
                              "detail": "not measured — site did not load: %s"
                              % (web.get("error") or "unknown error",)})
        return 0, breakdown

    load = web.get("load_time_ms")
    load_pts = 15 if (load is not None and load < 3000) \
        else 7 if (load is not None and load < 6000) else 0
    contact = bool(web.get("phone_link_found")
                   or web.get("whatsapp_link_found")
                   or (web.get("form_count") or 0) > 0)
    points = {
        "Website reachable": 25,
        "Served over HTTPS": 20 if web.get("https") else 0,
        "Mobile viewport meta present": 15 if web.get("viewport") else 0,
        "Page loads in under 3s (partial under 6s)": load_pts,
        "A contact channel found (phone, WhatsApp, or form)": 15 if contact else 0,
        "Booking/contact form found": 10 if web.get("booking_form_found") else 0,
    }
    details = {
        "Website reachable": "HTTP %s" % web.get("status"),
        "Served over HTTPS": ("final URL is HTTPS" if web.get("https")
                              else "final URL is not HTTPS"),
        "Mobile viewport meta present": ("viewport meta found" if web.get("viewport")
                                         else "no viewport meta tag found"),
        "Page loads in under 3s (partial under 6s)":
            ("%s ms" % load) if load is not None else "not measured",
        "A contact channel found (phone, WhatsApp, or form)":
            ("phone link: %s, WhatsApp link: %s, forms: %s"
             % (web.get("phone_link_found"), web.get("whatsapp_link_found"),
                web.get("form_count"))),
        "Booking/contact form found": ("booking/contact form found"
                                       if web.get("booking_form_found")
                                       else "no booking/contact form found"),
    }
    for label, max_pts in COMPONENTS:
        breakdown.append({"component": label, "points": points[label],
                          "max": max_pts, "detail": details[label]})
    return sum(points.values()), breakdown


def _yn(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "not measured"


def build_report(url, web, reviews, checklist, total, breakdown):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append("# Clinic Digital Health Report")
    lines.append("")
    lines.append("- **Website audited:** %s" % url)
    lines.append("- **Audit date:** %s" % now)
    lines.append("- **Overall score: %d / 100**" % total)
    lines.append("")
    lines.append("Score = sum of the measured components below. Unmeasured "
                 "components score 0 and are labelled, never guessed.")
    lines.append("")
    lines.append("## Score breakdown")
    lines.append("")
    lines.append("| Component | Points | Detail |")
    lines.append("|---|---|---|")
    for row in breakdown:
        lines.append("| %s | %d / %d | %s |"
                     % (row["component"], row["points"], row["max"],
                        row["detail"]))
    lines.append("")
    lines.append("## 1. Website check (measured)")
    lines.append("")
    lines.append("| Check | Result |")
    lines.append("|---|---|")
    lines.append("| Reachable | %s |" % _yn(web.get("reachable")))
    lines.append("| HTTP status | %s |"
                 % (web.get("status") if web.get("status") is not None
                    else "not measured"))
    lines.append("| Final URL after redirects | %s |"
                 % (web.get("final_url") or "not measured"))
    lines.append("| Served over HTTPS | %s |" % _yn(web.get("https")))
    lines.append("| Page-load time | %s |"
                 % (("%d ms" % web["load_time_ms"])
                    if web.get("load_time_ms") is not None else "not measured"))
    lines.append("| Page size fetched | %s |"
                 % (("%d bytes" % web["page_bytes"])
                    if web.get("page_bytes") else "not measured"))
    lines.append("| Page title found | %s |"
                 % (web.get("title") or "not measured"))
    lines.append("| Mobile viewport meta | %s |" % _yn(web.get("viewport")))
    lines.append("| Phone link found | %s |" % _yn(web.get("phone_link_found")))
    lines.append("| WhatsApp link found | %s |"
                 % _yn(web.get("whatsapp_link_found")))
    lines.append("| Forms on page | %s |"
                 % (web.get("form_count")
                    if web.get("form_count") is not None else "not measured"))
    lines.append("| Booking/contact form found | %s |"
                 % _yn(web.get("booking_form_found")))
    if web.get("error"):
        lines.append("| Load error | %s |" % web["error"])
    lines.append("")
    lines.append("## 2. Google reviews sentiment")
    lines.append("")
    if reviews["status"] == "measured":
        lines.append("- **Rating (as published):** %s" % reviews["rating"])
        lines.append("- **Review count (as published):** %s"
                     % (reviews["review_count"]
                        if reviews["review_count"] is not None
                        else "not published"))
        lines.append("- **Source:** %s" % reviews["source"])
        lines.append("- **Sentiment:** not analysed (a bare rating is not a "
                     "sentiment analysis).")
        lines.append("- Note: %s" % reviews["note"])
    else:
        lines.append("- **Reviews unavailable without API access.**")
        lines.append("- No rating, review count, or sentiment is claimed in "
                     "this report.")
        lines.append("- Reason: %s" % reviews["note"])
    lines.append("")
    lines.append("## 3. WhatsApp response test — manual checklist")
    lines.append("")
    lines.append("ClinicAudit sends NO message. The clinic owner (or auditor) "
                 "does these steps by hand and records the result:")
    lines.append("")
    for i, step in enumerate(checklist, 1):
        lines.append("%d. [ ] %s" % (i, step))
    lines.append("")
    lines.append("Record here: reply time __________ · reply type "
                 "(auto / human / none) __________ · booking offered "
                 "(yes / no) __________")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Honest limits")
    lines.append("")
    lines.append("- This is a free first-touch audit, not a full review "
                 "analysis. Review data needs Google Places API access for "
                 "full coverage.")
    lines.append("- Only the homepage (the URL given) was fetched. Inner pages, "
                 "booking flows, and actual reply behaviour were not tested "
                 "by the tool.")
    lines.append("- No message, email, or form submission was sent to the "
                 "clinic by this tool. Any contact afterwards is a separate, "
                 "human decision.")
    lines.append("- Scores measure public website facts only; they are not a "
                 "judgement of medical quality.")
    return "\n".join(lines) + "\n"


def build_html(markdown_text, title="Clinic Digital Health Report"):
    """Minimal HTML rendering of the Markdown report (no external deps)."""
    body = []
    in_table = False
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if set(cells) <= {""} or all(set(c) <= {"-", " "} for c in cells):
                continue
            if not in_table:
                body.append("<table>")
                in_table = True
            tag = "th" if stripped.startswith("| Component") \
                or stripped.startswith("| Check") else "td"
            body.append("<tr>" + "".join(
                "<%s>%s</%s>" % (tag, html.escape(c), tag) for c in cells)
                + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if stripped.startswith("# "):
            body.append("<h1>%s</h1>" % html.escape(stripped[2:]))
        elif stripped.startswith("## "):
            body.append("<h2>%s</h2>" % html.escape(stripped[3:]))
        elif stripped.startswith("- "):
            body.append("<p>• %s</p>" % html.escape(stripped[2:]))
        elif stripped.startswith("---"):
            body.append("<hr>")
        elif stripped:
            body.append("<p>%s</p>" % html.escape(stripped))
    if in_table:
        body.append("</table>")
    return ("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>%s</title>\n"
            "<style>body{font-family:system-ui,sans-serif;max-width:760px;"
            "margin:2em auto;padding:0 1em;line-height:1.5}"
            "table{border-collapse:collapse;width:100%%}"
            "th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}"
            "th{background:#f0f0f0}</style>\n</head>\n<body>\n%s\n</body>\n</html>\n"
            % (html.escape(title), "\n".join(body)))
