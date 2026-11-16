# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Plan and provision results for the standalone dock."""

from html import escape

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .berlin_view import provision_rows, render_html

TITLE = "Planrecht Berlin"


class PlanDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__(TITLE, parent)
        self.setObjectName("PlanrechtBerlinDock")
        panel = QWidget()
        panel.setMinimumWidth(320)
        layout = QVBoxLayout(panel)
        self.status = QLabel("Click a point in Berlin to find adopted plans.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        split = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(split, 1)
        plans_box = QGroupBox("Adopted plans / Festgesetzte B-Pläne")
        self.findings = QTextBrowser()
        self.findings.setOpenExternalLinks(True)
        QVBoxLayout(plans_box).addWidget(self.findings)
        split.addWidget(plans_box)

        provisions_box = QGroupBox("Selected written provisions / Textliche Festsetzungen")
        self.provisions = QTreeWidget()
        self.provisions.setHeaderHidden(True)
        self.provisions.setWordWrap(True)
        self.provisions.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.provisions.itemExpanded.connect(self._expand_provision)
        QVBoxLayout(provisions_box).addWidget(self.provisions)
        split.addWidget(provisions_box)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        self.setWidget(panel)

    def querying(self, lat, lon):
        self.status.setText(f"Looking up {lat:.5f}, {lon:.5f}…")
        self.findings.clear()
        self.provisions.clear()

    def show_result(self, result):
        point = result["point"]
        self.status.setText(f"Berlin plan lookup at {point['lat']:.5f}, {point['lon']:.5f}.")
        self.findings.setHtml(render_html(result))
        self.provisions.clear()
        rows = provision_rows(result)
        if not rows:
            self.provisions.addTopLevelItem(QTreeWidgetItem(["No selected provisions for this point."]))
        for row in rows:
            item = QTreeWidgetItem([f"{row['cite']} · {row['title']}"])
            item.setData(0, Qt.ItemDataRole.UserRole, row["text"])
            item.addChild(QTreeWidgetItem([""]))
            self.provisions.addTopLevelItem(item)

    def show_error(self, error):
        self.status.setText("Plan lookup stopped.")
        self.findings.setHtml(f"<p>Could not complete the lookup. {escape(error)}</p>")
        self.provisions.clear()

    def _expand_provision(self, item):
        text = item.data(0, Qt.ItemDataRole.UserRole)
        child = item.child(0)
        if text and child is not None and self.provisions.itemWidget(child, 0) is None:
            details = QPlainTextEdit(text)
            details.setReadOnly(True)
            details.setMinimumHeight(165)
            child.setSizeHint(0, details.minimumSize())
            self.provisions.setItemWidget(child, 0, details)
