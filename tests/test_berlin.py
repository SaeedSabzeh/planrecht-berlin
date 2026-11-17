# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planrecht_berlin import berlin, berlin_view  # noqa: E402

# One real feature from the Berlin B-Plan WFS (plan 0100002b, Mitte), trimmed to the fields we use.
REAL_PROPS = {
    "planid": "0100002b",
    "planname": "1-2b",
    "planartname": "Qualifizierter B-Plan",
    "bezirk": "01 - Mitte",
    "bp_rechtsstand": "In Kraft getreten",
    "festsg_am": "2004-09-01",
    "verfahrensart": "Normal",
    "scan_www": "https://mitte.gis-broker.de/bplaene/0100002b.pdf",
    "url_www": None,
    "grund_www": None,
    "inhalt": "Kerngebiet, Straßenverkehrsfläche",
}
NEUKOELLN_PROPS = dict(REAL_PROPS, planid="0800002-1", planname="8-2-1", festsg_am="2019-05-22")
COMMERCIAL_POINT = (52.46494611, 13.45485200)
ROAD_POINT = (52.46527898, 13.45485087)


def fake_fetch(payload):
    def fetch(url, timeout):
        return payload

    return fetch


def test_query_puts_lon_before_lat_and_sets_srid():
    url = berlin.build_point_query(lat=52.5, lon=13.4)
    assert url.startswith(berlin.BPLAN_WFS + "?")
    assert "typeNames=bplan%3Ab_bp_fs" in url
    # The CQL must carry the SRID prefix and lon/lat order (Berlin's layer is EPSG:25833 natively).
    assert "SRID%3D4326%3BPOINT%2813.4+52.5%29" in url


def test_parse_inhalt_splits_categories():
    assert berlin.parse_inhalt("Kerngebiet, Straßenverkehrsfläche") == [
        "Kerngebiet",
        "Straßenverkehrsfläche",
    ]
    assert berlin.parse_inhalt(None) == []
    assert berlin.parse_inhalt("") == []


def test_glossary_loads_baunvo_sections():
    glossary = berlin.load_glossary()
    assert glossary["Kerngebiet"] == "§ 7 BauNVO"
    assert glossary["allgemeines Wohngebiet"] == "§ 4 BauNVO"


def test_lookup_returns_plan_with_categories_and_scan():
    payload = {"type": "FeatureCollection", "features": [{"properties": REAL_PROPS}]}
    result = berlin.lookup(52.5119, 13.4014, fetch=fake_fetch(payload), glossary={"Kerngebiet": "§ 7 BauNVO"})
    assert result["status"] == "plans_found"
    assert result["error"] is None
    plan = result["plans"][0]
    assert plan["planid"] == "0100002b"
    assert plan["district"] == "01 - Mitte"
    assert plan["legal_status"] == "In Kraft getreten"
    assert plan["scan_url"].endswith("0100002b.pdf")
    assert plan["zone_categories"] == [
        {"name": "Kerngebiet", "baunvo": "§ 7 BauNVO"},
        {"name": "Straßenverkehrsfläche", "baunvo": None},
    ]


def test_lookup_without_plan_says_so_and_points_to_34_35():
    result = berlin.lookup(52.5, 13.4, fetch=fake_fetch({"features": []}), glossary={})
    assert result["status"] == "no_binding_plan"
    assert result["plans"] == []
    assert "§ 34 BauGB" in result["note"] and "§ 35 BauGB" in result["note"]


def test_lookup_reports_service_error_without_raising():
    def broken(url, timeout):
        raise OSError("connection reset")

    result = berlin.lookup(52.5, 13.4, fetch=broken, glossary={})
    assert result["status"] == "error"
    assert "OSError" in result["error"]
    assert result["plans"] == []


@pytest.mark.parametrize("payload", [[], {"features": None}, {"features": [None]},
                                     {"features": [{"properties": {}}]}])
def test_lookup_rejects_unexpected_response(payload):
    result = berlin.lookup(52.5, 13.4, fetch=fake_fetch(payload), glossary={})
    assert result["status"] == "error"


def test_official_berlin_boundary():
    assert berlin.in_berlin(52.52, 13.405)  # Alexanderplatz
    assert not berlin.in_berlin(45.46, 9.19)  # Milan Duomo
    assert not berlin.in_berlin(52.10, 13.40)  # south of the box
    assert berlin.is_berlin_candidate(52.389, 13.09)  # Potsdam, within the rectangular extent
    assert not berlin.in_berlin(52.389, 13.09)


def test_outside_berlin_does_not_send_a_wfs_query():
    def unexpected(url, timeout):
        pytest.fail("outside point was sent to the WFS")

    result = berlin.lookup_city_point(52.389, 13.09, fetch=unexpected)
    assert result["status"] == "outside_berlin"
    assert "outside Berlin" in berlin_view.render_html(result)


def test_render_found_escapes_and_links():
    result = {
        "status": "plans_found",
        "plans": [{
            "planid": "0100002b", "planname": "<script>1-2b</script>",
            "legal_status": "In Kraft getreten", "district": "01 - Mitte",
            "zone_categories": [{"name": "Kerngebiet", "baunvo": "§ 7 BauNVO"},
                                {"name": "Straßenverkehrsfläche", "baunvo": None}],
            "scan_url": "https://mitte.gis-broker.de/bplaene/0100002b.pdf",
            "reasons_url": "file:///home/user/example.pdf", "text_url": "javascript:alert(1)",
        }],
    }
    html = berlin_view.render_html(result)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Kerngebiet (" in html and "§ 7 BauNVO" in html
    assert 'href="https://www.gesetze-im-internet.de/baunvo/__7.html"' in html
    assert 'href="https://mitte.gis-broker.de/bplaene/0100002b.pdf"' in html
    assert "file:" not in html and "javascript:" not in html
    assert "Open the drawing to check the building limits" in html
    assert "OFFICIAL DATA ONLY" in html and "B-Plan &lt;script&gt;" in html
    assert "Guidance only, not legal advice" in berlin_view.DETAILS_HTML


def test_render_no_plan_and_error():
    none = berlin_view.render_html({"status": "no_binding_plan", "note": berlin.NO_PLAN_NOTE})
    assert "§ 34 BauGB" in none
    err = berlin_view.render_html({"status": "error", "note": "down", "error": "OSError: reset"})
    assert "down" in err and "OSError: reset" in err


def test_reviewed_figures_are_shown_by_area_and_linked_to_provisions():
    props = dict(REAL_PROPS, planid="0300009", planname="3-9", festsg_am="2011-10-28")
    result = berlin.lookup(52.52102, 13.46418, fetch=fake_fetch({"features": [{"properties": props}]}))
    html = berlin_view.render_html(result)
    assert "Match the clicked location to the area and markings on the drawing." in html
    assert "MK · Kerngebiet (core area)" in html
    assert "REVIEWED FIGURES" in html and "adopted 28.10.2011" in html
    assert "<b>I max.</b>" in html and "<b>1,2 max.</b>" in html  # figures table
    rows = berlin_view.provision_rows(result)
    assert rows[0]["cite"] == "TF 3" and rows[0]["plan"] == "3-9"
    assert "0,9" in rows[0]["text"] and "3-9_Abz.pdf" in rows[0]["url"]


@pytest.mark.parametrize("point,area_id,provisions", [
    (COMMERCIAL_POINT, "ge", [3, 5]),
    (ROAD_POINT, "road", [7]),
])
def test_neukoelln_shows_only_the_matched_area_and_its_sources(point, area_id, provisions):
    result = berlin.lookup(*point, fetch=fake_fetch({"features": [{"properties": NEUKOELLN_PROPS}]}))
    assert result["plans"][0]["point_area"] == {"status": "matched", "area_id": area_id}
    html = berlin_view.render_html(result)
    assert "Area at the clicked point" in html
    assert "8-2-1_tf.pdf?ts=1612451023#page=1" in html
    assert ("57,0 m" in html) == (area_id == "ge")
    assert ("yellow Grenzallee area" in html) == (area_id == "road")
    rows = berlin_view.provision_rows(result)
    assert [row["id"] for row in rows] == [f"0800002-1-{n}" for n in provisions]


@pytest.mark.parametrize("point,adopted_on,expected_status", [
    ((52.46520862, 13.45482235), "2019-05-22", "boundary"),
    ((52.46519594, 13.45482240), "2019-05-22", "boundary"),
    ((52.46522130, 13.45482231), "2019-05-22", "boundary"),
    ((52.46451496, 13.45485346), "2019-05-22", "unmapped"),
])
def test_neukoelln_withholds_area_rules_when_the_match_is_uncertain(point, adopted_on, expected_status):
    props = dict(NEUKOELLN_PROPS, festsg_am=adopted_on)
    result = berlin.lookup(*point, fetch=fake_fetch({"features": [{"properties": props}]}))
    assert result["plans"][0]["point_area"]["status"] == expected_status
    html = berlin_view.render_html(result)
    assert "Check the official drawing" in html
    assert "57,0 m" not in html
    assert not berlin_view.provision_rows(result)


@pytest.mark.parametrize("planid", ["0300009", "0500008", "0800002-1"])
@pytest.mark.parametrize("date", [None, "2099-01-01"])
def test_stale_reviewed_figures_use_live_plan_sources_only(planid, date):
    props = dict(REAL_PROPS, planid=planid, festsg_am=date)
    result = berlin.lookup(*COMMERCIAL_POINT, fetch=fake_fetch({"features": [{"properties": props}]}))
    plan = result["plans"][0]
    assert plan["review_status"] == "version_mismatch"
    assert "review" not in plan and "point_area" not in plan
    html = berlin_view.render_html(result)
    assert REAL_PROPS["scan_www"] in html
    assert "adoption date in the live service" in html
    assert not berlin_view.provision_rows(result)


@pytest.mark.parametrize("source", [None, "{", '{"0300009": {"zones": []}}'])
def test_unavailable_review_file_retains_live_plan(monkeypatch, tmp_path, source):
    path = tmp_path / "plans.json"
    if source is not None:
        path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(berlin, "_REVIEWS", path)
    result = berlin.lookup(*COMMERCIAL_POINT, fetch=fake_fetch({"features": [{"properties": REAL_PROPS}]}))
    assert result["status"] == "plans_found"
    html = berlin_view.render_html(result)
    assert REAL_PROPS["scan_www"] in html
    assert "Reviewed figures are unavailable" in html


@pytest.mark.parametrize("geometry", [None, "{}", '{"type":"FeatureCollection","features":[{"geometry":null}]}'])
def test_unavailable_area_geometry_retains_documents(monkeypatch, tmp_path, geometry):
    if geometry is not None:
        (tmp_path / "8-2-1-areas.geojson").write_text(geometry, encoding="utf-8")
    monkeypatch.setattr(berlin, "DATA_DIR", tmp_path)
    result = berlin.lookup(*COMMERCIAL_POINT, fetch=fake_fetch({"features": [{"properties": NEUKOELLN_PROPS}]}))
    assert result["plans"][0]["point_area"] == {"status": "unavailable"}
    html = berlin_view.render_html(result)
    assert "The area geometry could not be loaded" in html
    assert "8-2-1_tf.pdf" in html and "57,0 m" not in html
    assert not berlin_view.provision_rows(result)


def test_overlapping_plans_are_flagged_before_selected_figures():
    result = berlin.lookup(*COMMERCIAL_POINT, fetch=fake_fetch({
        "features": [{"properties": props} for props in (NEUKOELLN_PROPS, REAL_PROPS)]
    }))
    html = berlin_view.render_html(result)
    assert "2 adopted plans:" in html and "goto:p1" in html
    assert html.index("Several adopted plans intersect this point") < html.index("57,0 m")


def test_german_dates_and_trust_labels():
    assert berlin_view.german_date("2019-05-22") == "22.05.2019"
    assert berlin_view.german_date("") == ""
    stale = berlin_view._plan_html({"planname": "x", "review_status": "version_mismatch"})
    assert "REVIEW OUT OF DATE" in stale


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_BERLIN"), reason="set RUN_LIVE_BERLIN=1 to call the live WFS")
def test_live_point_inside_plan_0100002b():
    result = berlin.lookup(52.511951658333324, 13.40142859916667)
    assert result["status"] == "plans_found"
    assert any(p["planid"] == "0100002b" for p in result["plans"])


def test_early_access_strip_counts_only_while_enabled(monkeypatch):
    pytest.importorskip("qgis")  # early_access reads QgsSettings; runs in the QGIS Python
    from planrecht_berlin import early_access
    assert early_access.next_state(0, False) == (0, False)  # off while no page is set
    monkeypatch.setattr(early_access, "SIGNUP_URL", "https://example.test/pro")
    count, shows = 0, []
    for _ in range(4):
        count, show = early_access.next_state(count, False)
        shows.append(show)
    assert shows == [False, False, True, True]
    assert early_access.next_state(count, True) == (count, False)
    assert early_access.signup_url() == "https://example.test/pro?src=planrecht-berlin&lang=en"
