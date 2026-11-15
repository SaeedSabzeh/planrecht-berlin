# Planrecht Berlin for QGIS

Planrecht Berlin is a standalone experimental QGIS plugin. The first release is
`planrecht_berlin-0.1.0.zip` and appears as **Planrecht Berlin** in the Plugin Manager,
toolbar and results dock.

![Planrecht Berlin shows selected figures and provisions for the commercial area of 8-2-1](qgis-preview.png)

## Install and try it

1. In QGIS, open **Plugins → Manage and Install Plugins → Install from ZIP** and choose
   `planrecht_berlin-0.1.0.zip`.
2. Activate **Planrecht Berlin** and click in Berlin. Try **52.46494611, 13.45485200**
   (latitude, longitude) for the commercial area of 8-2-1 or **52.46527898, 13.45485087**
   for the Grenzallee road area.
3. Open the linked official documents for the full provisions and any amendments. If
   Berlin rate-limits a PDF, use the dock's **Official plan page** link.

## What a click shows

1. Check the click against the bundled ALKIS Berlin state boundary, then query Berlin's
   adopted B-Plan WFS with the clicked coordinates and keep each plan whose
   official outline intersects the point.
2. For plan 8-2-1 as adopted on 22 May 2019, compare the point to the GE and Grenzallee
   polygons derived from the published drawing. An interior GE click shows the labelled
   figures and links to the drawing and written provisions 3 and 5. A Grenzallee click shows the
   public road designation and links to provision 7. The location block also points to the
   motorway information on the drawing.
3. When the point is within 2 m of a drawn boundary, the dock withholds area-specific figures
   to avoid assigning the wrong area and asks the user to check the drawing. A missing geometry
   file or a point that matches no single area also leads to the source documents for
   checking. For all three reviewed plans, a missing or different adoption date suppresses
   the curated figures and provisions. The live plan links remain available.
4. When several adopted plans intersect the point, the dock flags them before the summaries.
   The official documents show the full set of provisions and amendments.

The local state boundary comes from the Berlin Senate's **ALKIS Berlin Landesgrenze** WFS
under Datenlizenz Deutschland – Zero – Version 2.0. The bundled GeoJSON is the geometry
from layer `alkis_land:landesgrenze`, requested in EPSG:4326 on 15 November 2026. Its
coordinates, islands and interior ring are preserved. It is used only to route city lookups.
[Dataset and licence](https://daten.berlin.de/datensaetze/alkis-berlin-landesgrenze-wfs-07b1347b)

The WFS provides the plan outline and status. The area geometry represents the internal
designations on the published sheet and is approximate. The 2 m margin is a product choice for
ambiguous clicks. It is larger than the observed fit residual and does not establish survey
accuracy. Berlin directs users to the original or certified plan for binding information.
[Berlin's guidance on plan copies](https://www.berlin.de/sen/stadtentwicklung/planung/bebauungsplanverfahren/bebauungsplanverfahren-in-berlin/bebauungsplaene-online/)

## How the 8-2-1 geometry was built

The public `plu_bplan` WFS capabilities advertised plan and documentation records. The geometry
used here comes from the GE grey fill and the Grenzallee yellow fill on page 1 of the district's
vector PDF. Berlin's `bplan:b_bp_fs` feature with `planid=0800002-1` supplies the reference outline
in EPSG:25833 (ETRS89 / UTM zone 33N). The source PDF has SHA-256
`73402d62127e2a080f6bd16a50953f1d22175e6c0f0c5f8f09577efedfb4ac42`.
[Adopted plan and documents](https://www.berlin.de/ba-neukoelln/politik-und-verwaltung/aemter/stadtentwicklungsamt/stadtplanung/bebauungsplaene/bebauungsplan-festgesetzt/artikel.140405.php) ·
[Official WFS polygon](https://gdi.berlin.de/services/wfs/bplan?service=WFS&version=2.0.0&request=GetFeature&typeNames=bplan%3Ab_bp_fs&outputFormat=application%2Fjson&srsName=EPSG%3A25833&CQL_FILTER=planid%3D%270800002-1%27)

PyMuPDF extracted the paths as PDF page coordinates in points, with the origin at the upper
left. The GE fill was path 1076 and the road fill was path 1075 in the zero-based
`page.get_drawings()` output for the source PDF. The paths share the boundary between
the two uses. The wide grey perimeter printed over both fills was used for visual orientation.

Fit the affine transform from the five rows marked **Fit** using least squares with an intercept.
The other three corners serve as checks. The vertex index is zero-based in the exterior ring
of the WFS polygon from the request above.

| PDF x | PDF y | WFS vertex | Use |
|---:|---:|---:|---|
| 1581.48 | 1059.72 | 0 | Fit |
| 1574.88 | 1063.44 | 1 | Check |
| 1549.56 | 1023.84 | 2 | Fit |
| 1098.12 | 1143.60 | 22 | Fit |
| 1098.48 | 1190.40 | 24 | Check |
| 1204.92 | 1406.76 | 58 | Fit |
| 1646.04 | 1120.80 | 84 | Fit |
| 1602.24 | 1063.68 | 86 | Check |

Close both fill paths, sample the GE curve into eight segments, transform the vertices into
EPSG:25833, then convert to WGS 84 with QGIS. The largest residual at the three check corners
was 0.034 m and the maximum distance from a WFS outline vertex to an extracted area boundary
was 0.035 m. The derived areas are 10,927.6 m² for GE and 2,830.6 m² for the road.
The district's rounded figures are 10,930 m² and 2,830 m². QGIS validated both polygons and
measured less than 0.01 m² of overlap along the shared boundary.
[District explanatory report, section 3.8, p. 49](https://www.berlin.de/ba-neukoelln/_assets/dokumente/bebauungsplaene/bebauungsplan-festgesetzt/begruendung/begruendung_8-2-1.pdf#page=49)

The [GeoJSON](planrecht_berlin/data/8-2-1-areas.geojson) can be opened in QGIS. The
[plan records](planrecht_berlin/data/plans.json) hold adoption and review dates, PDF hashes, source
links, area labels, figures, and written provision references. The ZIP includes both. Point containment uses
the GeoJSON rings and segment distances in local metres, with no additional runtime library.

## Build and verify

From the `berlin/` directory:

```sh
python build_plugin.py
python -m pytest -q tests
```

The build writes `dist/planrecht_berlin-0.1.0.zip`. Set `RUN_LIVE_BERLIN=1` to enable
the live WFS test. To test the actual ZIP in QGIS, run the following with QGIS's bundled
Python. Set `QT_QPA_PLATFORM=offscreen` for headless use. The smoke test loads the ZIP in
a temporary plugin directory and profile.

```sh
python smoke_qgis.py dist/planrecht_berlin-0.1.0.zip
```

The standalone preview was tested in QGIS 3.44.15 LTR on Windows. To also check
the official PDF downloads from the current network, pass `--check-pdfs`. Berlin
occasionally returns HTTP 429 for plan PDFs. The smoke test checks that the dock
contains the expected links even when a separate download request is rate-limited.
The release passed 36 automated tests with the WFS enabled. The independent
Astra High review scored the standalone package 8.9/10.

## Publish

Push the `berlin/` source and upload the matching `planrecht_berlin-0.1.0.zip` through
**Upload a plugin**. This creates the Planrecht Berlin listing with its own plugin ID.
Use the build and test commands above for Berlin releases. If tagging a Berlin release,
use a tag such as `planrecht-berlin-v0.1.0`. The repository's `v*` tag workflow builds
Norme Milano.
[QGIS Plugin Repository upload](https://plugins.qgis.org/plugins/add/)

## Scope and privacy

The point-to-area lookup covers 8-2-1. Plans 3-9 and 5-8 have reviewed plan-level summaries.
For other adopted plans the dock links to the published documents. Building envelopes,
motorway protection areas and the interaction of overlapping plans require checking the
official sources. The tool provides planning guidance. It sends in-city click coordinates
to the Berlin public B-Plan WFS. Outside-Berlin clicks are handled locally.

The Python plugin is GPL-2.0-or-later. The Berlin state boundary and the public B-Plan WFS
use Datenlizenz Deutschland – Zero – Version 2.0. The reviewed records cite their source
plans and retain the version dates and PDF hashes. [Licence](planrecht_berlin/LICENSE)
