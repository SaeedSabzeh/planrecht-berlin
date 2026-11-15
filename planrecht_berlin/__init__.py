"""Standalone Planrecht Berlin QGIS plugin."""


def classFactory(iface):  # noqa: N802
    from .plugin import PlanrechtBerlinPlugin

    return PlanrechtBerlinPlugin(iface)
