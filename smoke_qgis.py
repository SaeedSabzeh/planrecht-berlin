"""Run the published ZIP through QGIS using a temporary profile.

Run with the QGIS-bundled Python. Set QT_QPA_PLATFORM=offscreen for headless use.
    python smoke_qgis.py dist/planrecht_berlin-0.1.0.zip
"""

import argparse
import json
import os
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFillSymbol,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsRendererCategory,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QPoint, Qt
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QMainWindow, QSplitter

NEUKOELLN_PLAN_PAGE = (
    "https://www.berlin.de/ba-neukoelln/politik-und-verwaltung/aemter/stadtentwicklungsamt/"
    "stadtplanung/bebauungsplaene/bebauungsplan-festgesetzt/artikel.140405.php"
)


class TestInterface:
    def __init__(self):
        self.window = QMainWindow()
        self.window.resize(1100, 750)
        self.canvas = QgsMapCanvas()
        self.window.setCentralWidget(self.canvas)
        self.toolbar = self.window.addToolBar("Preview test")

    def mainWindow(self):
        return self.window

    def mapCanvas(self):
        return self.canvas

    def addDockWidget(self, area, widget):
        self.window.addDockWidget(area, widget)

    def removeDockWidget(self, widget):
        self.window.removeDockWidget(widget)

    def addToolBarIcon(self, action):
        self.toolbar.addAction(action)

    def removeToolBarIcon(self, action):
        self.toolbar.removeAction(action)

    def addPluginToMenu(self, menu, action):
        pass

    def removePluginMenu(self, menu, action):
        pass


def click(app, plugin, canvas, lat, lon, *, wait=True):
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        canvas.mapSettings().destinationCrs(),
        QgsProject.instance(),
    )
    point = transform.transform(QgsPointXY(lon, lat))
    canvas.setExtent(QgsRectangle(point.x() - 55, point.y() - 55, point.x() + 55, point.y() + 55))
    canvas.refresh()
    app.processEvents()
    pixel = canvas.getCoordinateTransform().transform(point)
    target = QPoint(round(pixel.x()), round(pixel.y()))
    assert canvas.viewport().rect().contains(target), (target, canvas.viewport().rect())
    start = monotonic()
    QTest.mouseClick(canvas.viewport(), Qt.LeftButton, pos=target)
    assert plugin.query is not None, "Mouse click did not start a query"
    if not wait:
        return None
    while plugin.query is not None:
        assert monotonic() - start < 48, "QGIS query timed out"
        QTest.qWait(15)
    return monotonic() - start


def verify_pdf_links(html, expected):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = set()

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.urls.add(dict(attrs).get("href", ""))

    parser = Links()
    parser.feed(html)
    for source in expected:
        assert source in parser.urls, (source, parser.urls)


def display_reviewed_areas(app, canvas, plugin_directory):
    if sys.platform == "win32" and app.platformName() == "offscreen":
        font_file = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        font_id = QFontDatabase.addApplicationFont(str(font_file))
        if font_id >= 0:
            app.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    geometry_path = plugin_directory / "planrecht_berlin/data/8-2-1-areas.geojson"
    layer = QgsVectorLayer(str(geometry_path), "8-2-1 reviewed areas", "ogr")
    assert layer.isValid()
    colors = {"ge": "#aec9c1", "road": "#f0d68b"}
    categories = [
        QgsRendererCategory(area, QgsFillSymbol.createSimple({
            "color": color, "outline_color": "#586966", "outline_width": "0.3",
        }), area)
        for area, color in colors.items()
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("area_id", categories))
    canvas.setLayers([layer])
    return layer


def run(app, plugin, iface, screenshot, check_pdfs):
    from planrecht_berlin.berlin import DATA_DIR

    records = json.loads((DATA_DIR / "plans.json").read_text(encoding="utf-8"))
    expected = {
        "0800002-1": ("drawing_url", "provisions_url"),
        "0300009": ("drawing_url",),
        "0500008": ("drawing_url",),
    }
    cases = [
        ("Commercial area", 52.46494611, 13.45485200, "0800002-1", [3, 5],
         ("GE · Gewerbegebiet", "0,6", "1,8", "57,0 m above NHN")),
        ("Grenzallee", 52.46527898, 13.45485087, "0800002-1", [7],
         ("Öffentliche Straßenverkehrsfläche",)),
        ("Boundary, GE side", 52.46519594, 13.45482240, "0800002-1", [],
         ("within 2 m of a drawn area boundary",)),
        ("Boundary, road side", 52.46522130, 13.45482231, "0800002-1", [],
         ("within 2 m of a drawn area boundary",)),
        ("Berlin point without an adopted plan", 52.46451496, 13.45485346, None, [],
         ("Berlin’s adopted B-Plan layer returned no match",)),
        ("Outside Berlin", 52.389, 13.09, None, [], ("This point is outside Berlin",)),
        ("Unreviewed plan", 52.51195166, 13.40142860, "0100002b", [],
         ("Open the drawing to check the building limits",)),
        ("Pankow 3-9", 52.521016, 13.464183, "0300009", [3, 4, 5, 6],
         ("Reviewed plan figures by area", "I (maximum one full storey)")),
        ("Spandau 5-8", 52.523149, 13.176414, "0500008", [4, 5, 6],
         ("Reviewed plan figures by area", "1.190 m²")),
    ]
    pdf_urls = set()
    for name, lat, lon, plan_id, provisions, terms in cases:
        elapsed = click(app, plugin, iface.canvas, lat, lon)
        assert plugin.dock.windowTitle() == "Planrecht Berlin"
        assert plugin.dock.findings.openExternalLinks()
        shown = plugin.dock.findings.toPlainText()
        assert "Berlin plan service" not in shown, shown
        assert all(term in shown for term in terms), shown
        assert ("57,0 m" in shown) == (name == "Commercial area"), shown
        if plan_id:
            assert plan_id in shown, shown
        else:
            assert "0800002-1" not in shown and "8-2-1" not in shown, shown
        tree = plugin.dock.provisions
        for index, provision in enumerate(provisions):
            item = tree.topLevelItem(index)
            assert f"Textliche Festsetzungen {provision} ·" in item.text(0), item.text(0)
            tree.expandItem(item)
            assert tree.itemWidget(item.child(0), 0) is not None, provision
        assert tree.topLevelItemCount() == (len(provisions) or 1)
        if not provisions:
            assert "No selected provisions" in tree.topLevelItem(0).text(0)
        if plan_id in expected:
            record_links = [records[plan_id][key] for key in expected[plan_id]]
            if name in {"Commercial area", "Grenzallee"}:
                record_links.extend(url + "#page=1" for url in record_links[:])
                record_links.append(NEUKOELLN_PLAN_PAGE)
            verify_pdf_links(plugin.dock.findings.toHtml(), record_links)
            pdf_urls.update(records[plan_id][key] for key in expected[plan_id])
        if screenshot and name == "Commercial area":
            plugin.dock.findChild(QSplitter).setSizes([410, 240])
            app.processEvents()
            assert iface.window.grab().save(str(screenshot)), screenshot
        print(f"PASS {name} ({elapsed:.2f}s)", flush=True)

    from planrecht_berlin import network

    click(app, plugin, iface.canvas, 52.46494611, 13.45485200, wait=False)
    click(app, plugin, iface.canvas, 52.46527898, 13.45485087)
    assert "Öffentliche Straßenverkehrsfläche" in plugin.dock.findings.toPlainText()
    assert "57,0 m" not in plugin.dock.findings.toPlainText()
    print("PASS consecutive clicks", flush=True)

    click(app, plugin, iface.canvas, 52.46494611, 13.45485200, wait=False)
    plugin.query.cancel()
    limit = monotonic() + 5
    while plugin.query is not None:
        assert monotonic() < limit, "QGIS did not finish the canceled task"
        QTest.qWait(15)
    assert plugin.dock.status.text().startswith("Lookup canceled.")
    print("PASS canceling the current task", flush=True)

    live_fetch = network.fetch_json

    def broken_service(url, timeout, is_canceled):
        raise OSError("simulated WFS outage")

    network.fetch_json = broken_service
    try:
        click(app, plugin, iface.canvas, 52.46494611, 13.45485200)
        assert "The Berlin plan service could not be reached" in plugin.dock.findings.toPlainText()
        assert "No selected provisions" in plugin.dock.provisions.topLevelItem(0).text(0)
        print("PASS Berlin service failure", flush=True)
    finally:
        network.fetch_json = live_fetch

    if check_pdfs:
        check_pdf_availability(pdf_urls, records["0800002-1"]["provisions_url"])


def check_pdf_availability(pdf_urls, provisions_url):
    failed = []
    for url in sorted(pdf_urls):
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=15) as response:
                assert response.read(8).startswith(b"%PDF-"), url
                print(f"PASS PDF HTTP {response.status} {url.rsplit('/', 1)[-1]}", flush=True)
        except HTTPError as error:
            if error.code != 429 or url != provisions_url:
                failed.append((url, str(error)))
                continue
            fallback = Request(NEUKOELLN_PLAN_PAGE, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(fallback, timeout=15) as response:
                assert b"8-2-1_tf.pdf" in response.read(), NEUKOELLN_PLAN_PAGE
                print("PDF HTTP 429; official plan page returned its download link", flush=True)
        except (URLError, TimeoutError, AssertionError) as error:
            failed.append((url, str(error)))
            print(f"FAIL PDF {url.rsplit('/', 1)[-1]}: {error}", flush=True)
    assert not failed, failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("screenshot", type=Path, nargs="?")
    parser.add_argument("--check-pdfs", action="store_true", help="also check live PDF download availability")
    args = parser.parse_args()
    archive = args.archive.resolve()
    screenshot = args.screenshot.resolve() if args.screenshot else None
    with tempfile.TemporaryDirectory(
        prefix="qgis-preview-", dir=archive.parent, ignore_cleanup_errors=True
    ) as test_directory:
        profile = Path(test_directory) / "profile"
        profile.mkdir()
        previous_directory = Path.cwd()
        os.chdir(profile)
        app = QgsApplication([], True, str(profile))
        app.initQgis()
        plugin_directory = Path(test_directory) / "python-plugins"
        with ZipFile(archive) as bundle:
            bundle.extractall(plugin_directory)
        sys.path.insert(0, str(plugin_directory))
        import planrecht_berlin

        assert plugin_directory in Path(planrecht_berlin.__file__).parents
        iface = TestInterface()
        layer = display_reviewed_areas(app, iface.canvas, plugin_directory) if screenshot else None
        iface.canvas.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:25833"))
        iface.window.setWindowTitle("QGIS · Planrecht Berlin preview")
        iface.window.show()
        plugin = planrecht_berlin.classFactory(iface)
        plugin.initGui()
        plugin.action.trigger()
        iface.window.resizeDocks([plugin.dock], [500], Qt.Orientation.Horizontal)
        app.processEvents()
        assert iface.canvas.mapTool() is plugin.tool and plugin.action.text() == "Planrecht Berlin"
        print(f"QGIS {Qgis.QGIS_VERSION}, EPSG:25833, archive {archive.name}", flush=True)
        try:
            run(app, plugin, iface, screenshot, args.check_pdfs)
            click(app, plugin, iface.canvas, 52.46494611, 13.45485200, wait=False)
        finally:
            plugin.unload()
            assert iface.canvas.mapTool() is None and plugin.dock is None and plugin.query is None
            limit = monotonic() + 10
            while tasks := QgsApplication.taskManager().activeTasks():
                assert monotonic() < limit, [(task.description(), task.status()) for task in tasks]
                QTest.qWait(15)
            iface.window.close()
            iface.canvas.setLayers([])
            del layer
            app.processEvents()
            os.chdir(previous_directory)
        print("PASS unloading with an active query", flush=True)


if __name__ == "__main__":
    main()
