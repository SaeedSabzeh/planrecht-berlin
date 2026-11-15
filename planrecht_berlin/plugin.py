"""Standalone toolbar, map tool and background plan lookup."""

from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsProject,
    QgsTask,
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:  # Qt 5
    from qgis.PyQt.QtWidgets import QAction

from . import berlin, network
from .dock import TITLE, PlanDock

MENU = "&Planrecht Berlin"


class PlanClickTool(QgsMapToolEmitPoint):
    point_selected = pyqtSignal(float, float)
    projection_error = pyqtSignal(str)

    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self._marker = None

    def canvasReleaseEvent(self, event):  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self.toMapCoordinates(event.pos())
        settings = self._canvas.mapSettings()
        transform = QgsCoordinateTransform(
            settings.destinationCrs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance(),
        )
        try:
            wgs84 = transform.transform(point)
        except QgsCsException:
            self.projection_error.emit("Check the map coordinate reference system and try again.")
            return
        if self._marker is None:
            self._marker = QgsVertexMarker(self._canvas)
            self._marker.setIconSize(14)
            self._marker.setPenWidth(3)
            self._marker.setColor(QColor("#ad3029"))
            self._marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
        self._marker.setCenter(point)
        self.point_selected.emit(wgs84.y(), wgs84.x())

    def clear_marker(self):
        if self._marker is not None:
            self._canvas.scene().removeItem(self._marker)
            self._marker = None


class PlanQuery(QgsTask):
    def __init__(self, lat, lon, complete):
        super().__init__(f"{TITLE}: lookup", QgsTask.Flag.CanCancel)
        self.lat = lat
        self.lon = lon
        self.complete = complete
        self.result = None
        self.error = ""

    def run(self):
        try:
            self.result = berlin.lookup_city_point(
                self.lat, self.lon, fetch=lambda url, timeout: network.fetch_json(url, timeout, self.isCanceled)
            )
        except Exception as error:
            self.error = str(error)
            return False
        return True

    def finished(self, ok):
        self.complete(self, self.result if ok else None, self.error)


class PlanrechtBerlinPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None
        self.tool = None
        self.query = None

    def initGui(self):  # noqa: N802
        icon = QIcon(str(Path(__file__).with_name("icon.png")))
        window = self.iface.mainWindow()
        self.action = QAction(icon, TITLE, window)
        self.action.setObjectName("PlanrechtBerlinLookup")
        self.action.setToolTip("Planrecht Berlin · click a point in Berlin to look up adopted plans")
        self.action.setCheckable(True)
        self.action.triggered.connect(self._toggle_tool)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(MENU, self.action)

        self.dock = PlanDock(window)
        self.dock.setWindowIcon(icon)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.hide()

        self.tool = PlanClickTool(self.iface.mapCanvas())
        self.tool.setAction(self.action)
        self.tool.point_selected.connect(self._request)
        self.tool.projection_error.connect(self._projection_error)

    def _toggle_tool(self, enabled):
        canvas = self.iface.mapCanvas()
        if enabled:
            canvas.setMapTool(self.tool)
            self.dock.show()
            self.dock.raise_()
        elif canvas.mapTool() is self.tool:
            canvas.unsetMapTool(self.tool)
            self.tool.clear_marker()

    def _cancel_query(self):
        if self.query is not None:
            task = self.query
            self.query = None
            task.cancel()

    def _projection_error(self, error):
        self._cancel_query()
        self.dock.show_error(error)

    def _request(self, lat, lon):
        self._cancel_query()
        self.dock.show()
        self.dock.querying(lat, lon)
        self.query = PlanQuery(lat, lon, self._complete_query)
        if not QgsApplication.taskManager().addTask(self.query):
            self.query = None
            self.dock.show_error("QGIS could not queue the lookup. Try again.")

    def _complete_query(self, task, result, error):
        if task is not self.query:
            return
        self.query = None
        if task.isCanceled():
            self.dock.status.setText("Lookup canceled. Click another point to try again.")
        elif result is None:
            self.dock.show_error(error)
        else:
            self.dock.show_result(result)

    def unload(self):
        self._cancel_query()
        if self.tool is not None:
            canvas = self.iface.mapCanvas()
            if canvas.mapTool() is self.tool:
                canvas.unsetMapTool(self.tool)
            self.tool.clear_marker()
            self.tool = None
        if self.action is not None:
            self.iface.removePluginMenu(MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
