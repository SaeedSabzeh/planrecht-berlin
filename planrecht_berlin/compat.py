# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Enum lookups that work on QGIS 3.x (Qt5) and QGIS 4 (Qt6)."""


def enum(cls, scope, name):
    """Return `cls.<scope>.<name>` when the scoped form exists, else `cls.<name>`."""
    holder = getattr(cls, scope, None)
    if holder is not None and hasattr(holder, name):
        return getattr(holder, name)
    return getattr(cls, name)
