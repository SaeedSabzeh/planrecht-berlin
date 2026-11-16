# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Standalone Planrecht Berlin QGIS plugin."""


def classFactory(iface):  # noqa: N802
    from .plugin import PlanrechtBerlinPlugin

    return PlanrechtBerlinPlugin(iface)
