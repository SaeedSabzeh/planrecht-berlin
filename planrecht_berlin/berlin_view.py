# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Berlin: how a lookup result is shown as HTML (plan cards).

Pure Python (no Qt), so it can be tested without QGIS. The dock calls `render_html` and shows
the string in its results browser; `DETAILS_HTML` is the text behind the footer's Details link.
"""

from html import escape
from urllib.parse import urlsplit

BERLIN_GUIDANCE_URL = ("https://www.berlin.de/sen/stadtentwicklung/planung/bebauungsplanverfahren/"
                       "bebauungsplanverfahren-in-berlin/bebauungsplaene-online/")
BAUGB_URL = "https://www.gesetze-im-internet.de/bbaug/__%d.html"
BAUNVO_URL = "https://www.gesetze-im-internet.de/baunvo/__%s.html"
DISCLAIMER = "Guidance only, not legal advice. Check the certified plan and any amendments."

MUTED = "#5f6368"
AMBER_BG, AMBER_FG = "#fff1c2", "#6b4a00"
TRUST = {  # colour bar, label colour, label
    "reviewed": ("#2e7d4f", "#2e7d4f", "REVIEWED FIGURES"),
    "official": ("#8a8f98", "#5f6368", "OFFICIAL DATA ONLY"),
    "outdated": ("#b7791f", "#8a5a12", "REVIEW OUT OF DATE"),
}


def _link(url, label):
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return ""
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username is not None:
        return ""
    return '<a href="%s">%s</a>' % (escape(parts.geturl(), quote=True), escape(label))


DETAILS_HTML = (
    "Planrecht Berlin shows selected figures and provisions for a few reviewed plans and the "
    "official documents for every adopted plan. Open the official documents for the full plan "
    "and check any amendments.<br><br>%s %s<br><br>Federal framework: %s · %s"
    % (escape(DISCLAIMER), _link(BERLIN_GUIDANCE_URL, "Berlin’s plan guidance"),
       _link(BAUGB_URL % 30, "§ 30 BauGB (development plans)"),
       _link(BAUGB_URL % 31, "§ 31 BauGB (exceptions and exemptions)")))


def _small(text, color=MUTED, margin="2px 0 0 0"):
    return "<p style='margin:%s; color:%s; font-size:small'>%s</p>" % (margin, color, text)


def _note(text, bottom=0):
    """An amber caution as a full-width block."""
    return ("<table width='100%%' cellspacing='0' cellpadding='4' style='margin:4px 0 %dpx 0'>"
            "<tr><td bgcolor='%s' style='color:%s'>%s</td></tr></table>"
            % (bottom, AMBER_BG, AMBER_FG, escape(text)))


def german_date(value):
    """"22.05.2019" for "2019-05-22"; anything else unchanged."""
    text = str(value or "")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return "%s.%s.%s" % (text[8:10], text[5:7], text[:4])
    return text


def _district(value):
    text = str(value or "")
    return text.split(" - ", 1)[1] if " - " in text else text


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


def _figures_table(zone):
    rows = zone.get("figures") or []
    if not rows:
        return ""
    cells = "".join(
        "<tr><td width='110' valign='middle' style='padding:1px 10px 1px 0'>%s</td>"
        "<td width='150' valign='middle' style='padding:1px 10px 1px 0'><b>%s</b></td>"
        "<td valign='middle' style='color:%s; font-size:small'>%s</td></tr>"
        % (escape(label), escape(value), MUTED, escape(gloss)) for label, value, gloss in rows)
    return "<table cellspacing='0' cellpadding='0' style='margin:4px 0 2px 0'>%s</table>" % cells


def _zone_html(zone):
    parts = ["<p style='margin:6px 0 0 0'><b>%s</b></p>" % escape(zone["label"]),
             _figures_table(zone)]
    parts.extend(_small(escape(rule)) for rule in zone["rules"])
    return "".join(parts)


def _review_html(review, point_area):
    """Reviewed figures: the matched area (point lookup) or every area (plan-level summary)."""
    zones = _visible_zones(review, point_area)
    if point_area is None:
        parts = [_small(escape(review.get("summary", "")), color="#202124", margin="6px 0 0 0"),
                 "<p style='margin:6px 0 0 0'><b>All areas of this plan</b></p>",
                 _note("Figures for the whole plan. Match the clicked location to the area and "
                       "markings on the drawing.")]
        parts.extend(_zone_html(zone) for zone in zones)
        return "".join(parts)
    if not zones:
        reason = {
            "boundary": "The point is within %s m of a drawn area boundary."
                        % point_area.get("buffer_m"),
            "unavailable": "The area geometry could not be loaded.",
        }.get(point_area["status"], "The point could not be matched to a mapped area on the drawing.")
        return _note(reason + " Check the official drawing for the zone and rules.")
    parts = ["<p style='margin:6px 0 0 0'><b>Area at the clicked point</b></p>",
             _note("Approximate match from the georeferenced plan drawing.")]
    for zone in zones:
        parts.append(_zone_html(zone))
        sources = [_link(review["drawing_url"] + "#page=1", "Drawing, p.\u00a01")]
        for provision in _visible_provisions(review, point_area):
            sources.append(_link(_provision_url(review, provision),
                                 "TF\u00a0%d" % provision["number"]))
        parts.append("<p style='margin:4px 0 0 0'>Sources for these figures: %s</p>"
                     % " · ".join(x for x in sources if x))
        parts.append(_small("On the drawing: " + escape(zone["drawing_location"])))
    if review.get("point_note"):
        parts.append(_small(escape(review["point_note"])))
    return "".join(parts)


def provision_rows(result):
    """Summaries of the selected written provisions, for the dock's provisions tree."""
    rows = []
    for plan in result.get("plans", []):
        review = plan.get("review")
        if not review:
            continue
        for provision in _visible_provisions(review, plan.get("point_area")):
            number = provision["number"]
            rows.append({
                "id": "%s-%s" % (plan["planid"], number),
                "plan": plan["planname"],
                "number": number,
                "cite": "TF %s" % number,
                "title": provision["title"],
                "roles": ["summary of written provision"],
                "text": provision["text"],
                "url": _provision_url(review, provision),
                "page": provision.get("page"),
            })
    return rows


def _trust(plan):
    if plan.get("review_status") == "version_mismatch":
        return "outdated"
    return "reviewed" if plan.get("review") else "official"


def _plan_html(plan, index=0):
    review = plan.get("review")
    point_area = plan.get("point_area")
    bar, label_color, label = TRUST[_trust(plan)]
    body = ["<a name='p%d'></a><p style='margin:0'><span style='color:%s; font-size:small'>"
            "<b>%s</b></span></p>" % (index, label_color, label),
            "<p style='margin:1px 0 0 0'><b>B-Plan %s</b> <span style='color:%s; font-size:small'>"
            "%s</span></p>" % (escape(str(plan.get("planname") or "?")), MUTED,
                               escape(str(plan.get("planid") or "")))]
    meta = [plan.get("legal_status"), plan.get("plan_type"), _district(plan.get("district"))]
    if plan.get("adopted_on"):
        meta.append("adopted %s" % german_date(plan["adopted_on"]))
    meta = [escape(str(x)) for x in meta if x]
    if meta:
        body.append(_small(" · ".join(meta)))

    if review:
        body.append(_review_html(review, point_area))

    cats = plan.get("zone_categories") or []
    if cats and (point_area is None or point_area["status"] != "matched"):
        uses = []
        for c in cats:
            ref = c.get("baunvo")
            section = ref.split()[1] if ref else None
            suffix = " (%s)" % _link(BAUNVO_URL % section, ref) if section else ""
            uses.append("%s%s" % (escape(c.get("name") or ""), suffix))
        body.append("<p style='margin:6px 0 0 0'>Uses: %s</p>" % " · ".join(uses))

    docs = [
        _link(review["drawing_url"] if review else plan.get("scan_url"), "Plan drawing"),
        _link(review.get("provisions_url"), "Written provisions") if review else "",
        _link(plan.get("reasons_url"), "Explanatory report"),
        _link(plan.get("text_url"), "Official plan page"),
    ]
    docs = [x for x in docs if x]
    if docs:
        body.append("<p style='margin:6px 0 0 0'>Documents: %s</p>" % " · ".join(docs))

    if plan.get("review_status") == "version_mismatch":
        body.append(_note("The adoption date in the live service is missing or differs from the "
                          "reviewed version."))
        body.append(_small("Check the official drawing for the zone and rules."))
    elif not review:
        body.append(_small("Open the drawing to check the building limits and any numeric rules."))
    return ("<table width='100%%' cellspacing='0' cellpadding='0' style='margin-bottom:14px'>"
            "<tr><td width='4' bgcolor='%s'></td><td width='8'></td><td>%s</td></tr></table>"
            % (bar, "".join(body)))


def summary_html(plans):
    """"2 adopted plans: 8-2-1 · 1-2b", each name jumping to its card."""
    names = " · ".join("<a href='goto:p%d'>%s</a>%s" % (
        i, escape(str(p.get("planname") or "?")),
        " (reviewed)" if _trust(p) == "reviewed" else "") for i, p in enumerate(plans))
    return "<p style='margin:0 0 8px 0; color:%s'>%d adopted plans: %s</p>" % (
        MUTED, len(plans), names)


def render_html(result: dict) -> str:
    """HTML for a `berlin.lookup` result. Every value is escaped."""
    status = result.get("status")
    if status == "plans_found":
        plans = result.get("plans", [])
        body = ""
        if len(plans) > 1:
            body += summary_html(plans)
            body += _note("Several adopted plans intersect this point. Check which provisions "
                          "apply together and whether later plans supersede earlier ones.", 8)
        if result.get("note"):
            body += _note(result["note"], 8)
        body += "".join(_plan_html(plan, i) for i, plan in enumerate(plans))
        return body
    if status in {"outside_berlin", "boundary_unavailable"}:
        return "<p>%s</p>" % escape(result["note"])
    if status == "no_binding_plan":
        steps = (
            "<p style='margin:6px 0 0 0'>1. Check the Baunutzungsplan and the Fluchtlinien "
            "where they apply.</p><p style='margin:4px 0 0 0'>2. Ask the district planning "
            "office whether %s (built-up areas) or %s (outside them) applies.</p>"
            % (_link(BAUGB_URL % 34, "§ 34 BauGB"), _link(BAUGB_URL % 35, "§ 35 BauGB")))
        return ("<table width='100%%' cellspacing='0' cellpadding='0'><tr><td width='4' "
                "bgcolor='%s'></td><td width='8'></td><td><p style='margin:0'><b>No adopted "
                "B-Plan at this point</b></p>%s%s</td></tr></table>"
                % (TRUST["official"][0], _small("Berlin’s adopted B-Plan layer has no match "
                                                "here. Next steps:"), steps))
    body = "<p>%s</p>" % escape(result.get("note") or "The Berlin lookup failed.")
    if result.get("error"):
        body += "<p><small>%s</small></p>" % escape(str(result["error"]))
    return body
