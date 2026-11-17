# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Berlin: which binding development plan (Bebauungsplan, B-Plan) covers a point.

Standard library only, like core/services.py. The network call is injectable (`fetch`) so tests
and a later QGIS shell can swap it out.

Data source: the Senate's open WFS of Berlin's development plans
(https://gdi.berlin.de/services/wfs/bplan, layer bplan:b_bp_fs, licence Datenlizenz
Deutschland - Zero 2.0). The service returns plan boundaries and metadata. Reviewed plan
figures are stored separately and describe areas on the drawing.
"""

import json
import math
import urllib.parse
import urllib.request
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import urlcheck

BPLAN_WFS = "https://gdi.berlin.de/services/wfs/bplan"
BINDING_LAYER = "bplan:b_bp_fs"  # festgesetzte (adopted, binding) Bebauungspläne

DEFAULT_TIMEOUT = 20

DATA_DIR = Path(__file__).resolve().parent / "data"
_GLOSSARY = DATA_DIR / "inhalt_baunvo.json"
_REVIEWS = DATA_DIR / "plans.json"
CITY_BOUNDARY_FILE = "landesgrenze.geojson"
BERLIN_BBOX = (52.33, 52.69, 13.08, 13.77)
REVIEW_UNAVAILABLE = "Reviewed figures are unavailable. Use the official plan documents below."

NO_PLAN_NOTE = (
    "Berlin’s adopted B-Plan layer returned no match. For a site in Berlin, check the "
    "Baunutzungsplan and Fluchtlinien where applicable, and consult the district planning "
    "office about § 34 BauGB (built-up areas) or § 35 BauGB (outside those areas)."
)


def load_glossary(path=_GLOSSARY):
    """Return {German category: BauNVO reference or None}. Missing file -> {}."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_point_query(lat: float, lon: float, layer: str = BINDING_LAYER) -> str:
    """WFS 2.0 GetFeature URL for plans whose polygon contains (lat, lon).

    The CQL filter needs the SRID prefix. Without it the coordinates are read as the layer's
    native EPSG:25833 and nothing matches (checked against the live service).
    """
    cql = f"INTERSECTS(geom,SRID=4326;POINT({lon} {lat}))"
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": layer,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "propertyName": "planid,planname,planartname,bezirk,bp_rechtsstand,festsg_am,"
        "scan_www,url_www,grund_www,inhalt,verfahrensart",
        "CQL_FILTER": cql,
    }
    return f"{BPLAN_WFS}?{urllib.parse.urlencode(params)}"


def fetch_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Default fetch: GET `url` and decode JSON. https only (see urlcheck)."""
    urlcheck.check_url(url)
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
        return json.load(resp)


def parse_inhalt(text):
    """Split the `inhalt` field ("Kerngebiet, Straßenverkehrsfläche") into a list."""
    if not text:
        return []
    return [part.strip() for part in str(text).split(",") if part.strip()]


def _plan_from_properties(props, glossary):
    categories = parse_inhalt(props.get("inhalt"))
    return {
        "planid": props.get("planid"),
        "planname": props.get("planname"),
        "plan_type": props.get("planartname"),
        "district": props.get("bezirk"),
        "legal_status": props.get("bp_rechtsstand"),
        "adopted_on": props.get("festsg_am"),
        "procedure": props.get("verfahrensart"),
        "scan_url": props.get("scan_www"),
        "text_url": props.get("url_www"),
        "reasons_url": props.get("grund_www"),  # Begründung (explanatory report), if linked
        "zone_categories": [
            {"name": name, "baunvo": glossary.get(name)} for name in categories
        ],
        "inhalt_raw": props.get("inhalt"),
    }


def _is_ring(coordinates):
    return (isinstance(coordinates, list) and len(coordinates) >= 4
            and coordinates[0] == coordinates[-1]
            and all(isinstance(point, list) and len(point) == 2
                    and type(point[0]) in (int, float) and -180 <= point[0] <= 180
                    and type(point[1]) in (int, float) and -90 <= point[1] <= 90
                    for point in coordinates))


def _read_area_rings(source, area_ids):
    geometry = json.loads(source)
    try:
        rings = {
            feature["properties"]["area_id"]: feature["geometry"]["coordinates"][0]
            for feature in geometry["features"]
            if feature["geometry"]["type"] == "Polygon"
            and len(feature["geometry"]["coordinates"]) == 1
        }
        valid = (geometry["type"] == "FeatureCollection"
                 and len(geometry["features"]) == len(rings)
                 and rings.keys() == area_ids
                 and all(_is_ring(ring) for ring in rings.values()))
    except (KeyError, IndexError, TypeError):
        valid = False
    if not valid:
        raise ValueError("invalid reviewed area geometry")
    return rings


def _read_city_boundary(source):
    geometry = json.loads(source)
    try:
        polygons = geometry["coordinates"]
        valid = (geometry["type"] == "MultiPolygon" and polygons
                 and all(polygon and all(_is_ring(ring) for ring in polygon)
                         for polygon in polygons))
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise ValueError("invalid Berlin state boundary")
    return polygons


@lru_cache(maxsize=1)
def _city_boundary(path):
    return _read_city_boundary(path.read_text(encoding="utf-8"))


def is_berlin_candidate(lat, lon):
    """Cheap extent check before loading the local boundary."""
    min_lat, max_lat, min_lon, max_lon = BERLIN_BBOX
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def in_berlin(lat, lon):
    """Check the official Berlin state boundary, including its islands and holes."""
    if not is_berlin_candidate(lat, lon):
        return False
    for outer, *holes in _city_boundary(DATA_DIR / CITY_BOUNDARY_FILE):
        inside, on_edge = _check_area_ring(lat, lon, outer, 0)
        if on_edge or (inside and not any(_check_area_ring(lat, lon, hole, 0)[0] for hole in holes)):
            return True
    return False


def _read_reviews(source):
    reviews = json.loads(source)
    if not isinstance(reviews, dict):
        raise ValueError("invalid reviewed plan records")
    for plan_id, review in reviews.items():
        try:
            date.fromisoformat(review["adopted_on"])
            date.fromisoformat(review["reviewed_on"])
            urlcheck.check_url(review["drawing_url"])
            if review.get("provisions_url"):
                urlcheck.check_url(review["provisions_url"])
            zones = review["zones"]
            provisions = review["provisions"]
            numbers = {p["number"] for p in provisions}
            valid = (isinstance(zones, list) and zones and isinstance(provisions, list)
                     and all(isinstance(z["label"], str) and isinstance(z["rules"], list) and z["rules"]
                                   and all(isinstance(rule, str) for rule in z["rules"])
                                   and isinstance(z.get("figures", []), list)
                                   and all(isinstance(row, list) and len(row) == 3
                                           and all(isinstance(cell, str) for cell in row)
                                           for row in z.get("figures", []))
                                   for z in zones)
                     and len(numbers) == len(provisions)
                     and all(type(p["number"]) is int and isinstance(p["title"], str)
                             and isinstance(p["text"], str) and type(p["page"]) is int
                             and p["page"] > 0 for p in provisions))
            if coverage := review.get("point_lookup"):
                ids = {z["id"] for z in zones}
                filename = coverage["geometry_file"]
                valid = (valid and len(ids) == len(zones) and filename == Path(filename).name
                         and filename.endswith(".geojson")
                         and type(coverage["boundary_buffer_m"]) in (int, float)
                         and 0 < coverage["boundary_buffer_m"] < 100
                         and all(isinstance(z["drawing_location"], str)
                                 and set(z["provision_numbers"]) <= numbers for z in zones))
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError(f"invalid reviewed plan {plan_id}")
    return reviews


def validate_preview_data(read_file):
    """Use the runtime readers to check Berlin data extracted from the release ZIP."""
    _read_city_boundary(read_file(CITY_BOUNDARY_FILE))
    for review in _read_reviews(read_file("plans.json")).values():
        if coverage := review.get("point_lookup"):
            _read_area_rings(read_file(coverage["geometry_file"]), {z["id"] for z in review["zones"]})


def _check_area_ring(lat, lon, ring, boundary_buffer_m):
    """Return whether the point is inside the ring and within the boundary buffer.

    Offsets in longitude and latitude are converted to local metres for this small site.
    The ring is closed and uses GeoJSON coordinate order (longitude, latitude).
    """
    metres_per_lon_degree = 111320 * math.cos(math.radians(lat))
    vertices = [((x - lon) * metres_per_lon_degree, (y - lat) * 111200) for x, y in ring]
    inside = False
    for (x1, y1), (x2, y2) in zip(vertices, vertices[1:]):
        dx, dy = x2 - x1, y2 - y1
        length_squared = dx * dx + dy * dy
        if length_squared:
            t = max(0, min(1, -(x1 * dx + y1 * dy) / length_squared))
            if (x1 + t * dx) ** 2 + (y1 + t * dy) ** 2 <= boundary_buffer_m ** 2:
                return False, True
        if (y1 > 0) != (y2 > 0) and x1 - y1 * dx / dy > 0:
            inside = not inside
    return inside, False


def _point_area(lat, lon, review):
    coverage = review["point_lookup"]
    try:
        path = DATA_DIR / coverage["geometry_file"]
        rings = _read_area_rings(path.read_text(encoding="utf-8"), {z["id"] for z in review["zones"]})
    except (OSError, ValueError):
        return {"status": "unavailable"}
    buffer_m = coverage["boundary_buffer_m"]
    matches = []
    for area_id, ring in rings.items():
        inside, near_boundary = _check_area_ring(lat, lon, ring, buffer_m)
        if near_boundary:
            return {"status": "boundary", "buffer_m": buffer_m}
        if inside:
            matches.append(area_id)
    if len(matches) == 1:
        return {"status": "matched", "area_id": matches[0]}
    return {"status": "unmapped"}


def lookup_city_point(lat, lon, fetch=None):
    """QGIS entry point for a click in the Berlin region."""
    try:
        inside = in_berlin(lat, lon)
    except (OSError, ValueError):
        status = "boundary_unavailable"
        note = "The preview could not load the Berlin state boundary. Reinstall the plugin ZIP."
    else:
        if inside:
            return lookup(lat, lon, fetch=fetch)
        status = "outside_berlin"
        note = "This point is outside Berlin. Choose a point within the city for the Berlin preview."
    return {"point": {"lat": lat, "lon": lon}, "status": status, "plans": [], "note": note}


def lookup(lat: float, lon: float, fetch=None, timeout=DEFAULT_TIMEOUT, glossary=None):
    """Return the binding plans at (lat, lon).

    Result::

        {"point": {"lat": .., "lon": ..},
         "status": "plans_found" | "no_binding_plan" | "error",
         "plans": [plan dict, ...],
         "note": str,            # always set when there is no plan, or an error
         "error": str | None}

    Never raises for a network or service error; the error is reported in the result.
    """
    fetch = fetch or fetch_json
    glossary = load_glossary() if glossary is None else glossary
    point = {"lat": lat, "lon": lon}
    try:
        data = fetch(build_point_query(lat, lon), timeout)
    except Exception as exc:
        return {"point": point, "status": "error", "plans": [], "error": f"{type(exc).__name__}: {exc}",
                "note": "The Berlin plan service could not be reached. Try again later."}
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list) or any(
        not isinstance(feature, dict)
        or not isinstance(feature.get("properties"), dict)
        or not feature["properties"].get("planid")
        for feature in features
    ):
        return {"point": point, "status": "error", "plans": [], "error": "unexpected response",
                "note": "The Berlin plan service returned an unexpected response."}

    if not features:
        return {"point": point, "status": "no_binding_plan", "plans": [], "error": None,
                "note": NO_PLAN_NOTE}

    plans = [_plan_from_properties(feature["properties"], glossary) for feature in features]
    note = ""
    try:
        reviews = _read_reviews(_REVIEWS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        reviews = {}
        note = REVIEW_UNAVAILABLE
    for plan in plans:
        review = reviews.get(str(plan["planid"]))
        if not review:
            continue
        if plan["adopted_on"] != review["adopted_on"]:
            plan["review_status"] = "version_mismatch"
            continue
        plan["review"] = review
        if review.get("point_lookup"):
            plan["point_area"] = _point_area(lat, lon, review)
    return {"point": point, "status": "plans_found", "plans": plans, "error": None, "note": note}
