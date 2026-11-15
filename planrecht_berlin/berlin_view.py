"""Berlin: where the Berlin lookup applies, and how its result is shown as HTML.

Pure Python (no Qt), so it can be tested without QGIS. The dock calls `render_html` and shows
the string in its findings box.
"""

from html import escape
from urllib.parse import urlsplit

# The bounding box routes the click. The WFS determines plan coverage.
BERLIN_GUIDANCE_URL = ("https://www.berlin.de/sen/stadtentwicklung/planung/bebauungsplanverfahren/"
                       "bebauungsplanverfahren-in-berlin/bebauungsplaene-online/")
BAUGB_URL = "https://www.gesetze-im-internet.de/bbaug/__%d.html"
BAUNVO_URL = "https://www.gesetze-im-internet.de/baunvo/__%s.html"
DISCLAIMER = "Guidance only, not legal advice. Check the certified plan and any amendments."


def _link(url, label):
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return ""
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username is not None:
        return ""
    return '<a href="%s">%s</a>' % (escape(parts.geturl(), quote=True), escape(label))


def _visible_zones(review, point_area):
    if point_area is None:
        return review["zones"]
    if point_area["status"] == "matched":
        return [zone for zone in review["zones"] if zone["id"] == point_area["area_id"]]
    return []


def _visible_provisions(review, point_area):
    if point_area is None:
        return review["provisions"]
    numbers = {n for zone in _visible_zones(review, point_area) for n in zone["provision_numbers"]}
    return [provision for provision in review["provisions"] if provision["number"] in numbers]


def _provision_url(review, provision):
    source = review.get("provisions_url") or review["drawing_url"]
    page = provision.get("page")
    return "%s#page=%d" % (source, page) if page else source


def _review_html(review, point_area):
    zones = _visible_zones(review, point_area)
    if point_area is None:
        parts = ["<p>%s</p>" % escape(review.get("summary", "")),
                 "<p><b>Reviewed plan figures by area</b><br>"
                 "Match the clicked location to the area and markings on the drawing.</p>"]
    else:
        if not zones:
            status = point_area["status"]
            reason = {
                "boundary": "The point is within %s m of a drawn area boundary."
                            % point_area.get("buffer_m"),
                "unavailable": "The area geometry could not be loaded.",
            }.get(status, "The point could not be matched to a mapped area on the drawing.")
            return "<p>%s Check the official drawing for the zone and rules.</p>" % escape(reason)
        parts = ["<p><b>Area at the clicked point</b><br>"
                 "Approximate match from the georeferenced plan drawing.</p>"]
    for zone in zones:
        parts.append("<p><b>%s</b></p><ul>" % escape(zone["label"]))
        parts.extend("<li>%s</li>" % escape(rule) for rule in zone["rules"])
        parts.append("</ul>")
        if point_area:
            sources = [_link(review["drawing_url"] + "#page=1", zone["drawing_location"])]
            for provision in _visible_provisions(review, point_area):
                label = "Textliche Festsetzung %d, p. %d" % (provision["number"], provision["page"])
                sources.append(_link(_provision_url(review, provision), label))
            parts.append("<p>%s</p>" % " &nbsp;|&nbsp; ".join(sources))
    if point_area and review.get("point_note"):
        parts.append("<p>%s</p>" % escape(review["point_note"]))
    return "".join(parts)


def provision_rows(result):
    """Summaries of selected written provisions for the dock's existing article tree."""
    rows = []
    for plan in result.get("plans", []):
        review = plan.get("review")
        if not review:
            continue
        for provision in _visible_provisions(review, plan.get("point_area")):
            number = provision["number"]
            rows.append({
                "id": "%s-%s" % (plan["planid"], number),
                "cite": "%s · Textliche Festsetzungen %s" % (plan["planname"], number),
                "title": provision["title"],
                "roles": ["summary of written provision"],
                "text": provision["text"] + "\n\nOfficial source: "
                + _provision_url(review, provision),
            })
    return rows


def _plan_html(plan):
    parts = ["<h3>%s &middot; %s</h3>" % (
        escape(str(plan.get("planname") or "?")), escape(str(plan.get("planid") or "")))]
    review = plan.get("review")
    point_area = plan.get("point_area")
    if review and point_area:
        parts.append(_review_html(review, point_area))
    rows = [
        ("Status", plan.get("legal_status")),
        ("Type", plan.get("plan_type")),
        ("District", plan.get("district")),
        ("Adopted", plan.get("adopted_on")),
    ]
    parts.append("<ul>")
    for label, value in rows:
        if value:
            parts.append("<li><b>%s:</b> %s</li>" % (label, escape(str(value))))
    parts.append("</ul>")

    cats = plan.get("zone_categories") or []
    if cats and (point_area is None or point_area["status"] != "matched"):
        parts.append("<p><b>Uses listed across the plan</b><br>"
                     "Federal links are category references. Check the BauNVO version cited "
                     "on the plan.</p><ul>")
        for c in cats:
            ref = c.get("baunvo")
            section = ref.split()[1] if ref else None
            suffix = " (%s)" % _link(BAUNVO_URL % section, ref) if section else ""
            parts.append("<li>%s%s</li>" % (escape(c.get("name") or ""), suffix))
        parts.append("</ul>")

    links = [
        _link(review["drawing_url"] if review else plan.get("scan_url"), "Plan drawing"),
        _link(review.get("provisions_url"), "Written provisions") if review else "",
        _link(plan.get("reasons_url"), "Explanatory report (Begründung)"),
        _link(plan.get("text_url"), "Official plan page"),
    ]
    links = [x for x in links if x]
    if links:
        parts.append("<p>%s</p>" % " &nbsp;|&nbsp; ".join(links))
    if review and point_area is None:
        parts.append(_review_html(review, point_area))
    elif plan.get("review_status") == "version_mismatch":
        parts.append("<p>The adoption date in the live service is missing or differs from the "
                     "reviewed version. Check the official drawing for the zone and rules.</p>")
    elif not review:
        parts.append("<p>Open the drawing to check the building limits and any numeric rules.</p>")
    return "".join(parts)


def render_html(result: dict) -> str:
    """HTML for a `core.berlin.lookup` result. Every value is escaped."""
    status = result.get("status")
    if status == "plans_found":
        plans = result.get("plans", [])
        body = ("<p><b>Planrecht Berlin preview</b><br>"
                "The dock shows selected figures and provisions. Open the official documents "
                "for the full plan and check any amendments.</p>")
        if len(plans) > 1:
            body += ("<p><b>Several adopted plans intersect this point.</b> Check which "
                     "provisions apply together and whether later plans supersede earlier ones.</p>")
        if result.get("note"):
            body += "<p>%s</p>" % escape(result["note"])
        body += "".join(_plan_html(plan) for plan in plans)
        body += "<p>Federal framework %s and %s.</p>" % (
            _link(BAUGB_URL % 30, "§ 30 BauGB (development plans)"),
            _link(BAUGB_URL % 31, "§ 31 BauGB (exceptions and exemptions)"),
        )
    elif status in {"outside_berlin", "boundary_unavailable"}:
        body = "<p>%s</p>" % escape(result["note"])
    elif status == "no_binding_plan":
        body = "<p>%s</p>" % escape(result.get("note") or "No binding plan found.")
        body += "<p>%s &nbsp;|&nbsp; %s</p>" % (
            _link(BAUGB_URL % 34, "§ 34 BauGB"),
            _link(BAUGB_URL % 35, "§ 35 BauGB"),
        )
    else:
        body = "<p>%s</p>" % escape(result.get("note") or "The Berlin lookup failed.")
        if result.get("error"):
            body += "<p><small>%s</small></p>" % escape(str(result["error"]))
    return body + "<p><small>%s %s</small></p>" % (
        escape(DISCLAIMER), _link(BERLIN_GUIDANCE_URL, "Berlin’s plan guidance"))
