# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Plan cards and written provisions in the dock.

Results get the height; the legal notes sit behind a one-line footer with Details.
"""

from html import escape

from qgis.PyQt.QtCore import Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QDesktopServices, QFont
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import early_access
from .berlin_view import DETAILS_HTML, provision_rows, render_html
from .compat import enum

TITLE = "Planrecht Berlin"
MUTED = "#5f6368"
LINK_STYLE = "a { color: #1a5fb4; text-decoration: none; }"


class PlanDock(QDockWidget):
    earlyAccessRequested = pyqtSignal()
    earlyAccessDismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(TITLE, parent)
        self.setObjectName("PlanrechtBerlinDock")
        self._details_open = False
        panel = QWidget()
        panel.setMinimumWidth(280)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self.status = QLabel("Click a point in Berlin to find adopted plans.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: %s;" % MUTED)
        layout.addWidget(self.status)

        self.outside = QLabel()
        self.outside.setWordWrap(True)
        self.outside.setAlignment(enum(Qt, "AlignmentFlag", "AlignCenter"))
        self.outside.setVisible(False)
        layout.addWidget(self.outside, 1)

        self.split = QSplitter(enum(Qt, "Orientation", "Vertical"))
        self.split.setChildrenCollapsible(False)
        layout.addWidget(self.split, 1)

        self.findings = QTextBrowser()
        self.findings.setOpenExternalLinks(True)
        self.findings.setOpenLinks(False)  # links go through _on_anchor
        self.findings.anchorClicked.connect(self._on_anchor)
        self.findings.document().setDefaultStyleSheet(LINK_STYLE)
        self.findings.setMinimumHeight(160)
        self.plans_section = self._section("Adopted plans (B-Pläne)", self.findings)

        self.provisions = QTreeWidget()
        self.provisions.setHeaderHidden(True)
        self.provisions.setWordWrap(False)
        self.provisions.setTextElideMode(enum(Qt, "TextElideMode", "ElideRight"))
        self.provisions.setFont(self.findings.font())
        self.provisions.itemExpanded.connect(self._expand_provision)
        self.provisions.itemExpanded.connect(lambda _item: self._balance())
        self.provisions.itemCollapsed.connect(lambda _item: self._balance())
        self.provisions_section = self._section(
            "Written provisions (Textliche Festsetzungen)", self.provisions)
        self.split.setStretchFactor(0, 4)
        self.split.setStretchFactor(1, 1)

        # early-access strip (hidden until plugin.py shows it)
        self.ea_strip = QFrame()
        self.ea_strip.setObjectName("eaStrip")
        self.ea_strip.setStyleSheet(
            "QFrame#eaStrip { background: #eef4fb; border: 1px solid #c9dcf2; border-radius: 4px; }")
        strip = QHBoxLayout(self.ea_strip)
        strip.setContentsMargins(8, 3, 2, 3)
        strip.setSpacing(4)
        self.ea_label = QLabel("%s <a href='ea' style='color:#1a5fb4'>%s</a>" % (
            escape(early_access.STRIP_TEXT),
                                                          escape(early_access.LINK_TEXT)))
        self.ea_label.setWordWrap(True)
        self.ea_label.setToolTip(early_access.LINK_TIP)
        self.ea_label.linkActivated.connect(lambda _link: self.earlyAccessRequested.emit())
        strip.addWidget(self.ea_label, 1)
        self.ea_close = QToolButton()
        self.ea_close.setText("\u00d7")
        self.ea_close.setAutoRaise(True)
        self.ea_close.setToolTip(early_access.CLOSE_TIP)
        self.ea_close.clicked.connect(self.earlyAccessDismissed.emit)
        strip.addWidget(self.ea_close)
        self.ea_strip.setVisible(False)
        layout.addWidget(self.ea_strip)

        self.footer = QLabel()
        self.footer.setWordWrap(True)
        self.footer.setStyleSheet("color: %s;" % MUTED)
        self.footer.linkActivated.connect(self._toggle_details)
        layout.addWidget(self.footer)
        details = DETAILS_HTML
        if early_access.enabled():
            details += "<br><br><a href='ea'>%s</a>" % escape(early_access.DETAILS_TEXT)
        self.details = QLabel("<small>%s</small>" % details)
        self.details.setWordWrap(True)
        self.details.setOpenExternalLinks(False)  # links go through _on_details_link
        self.details.linkActivated.connect(self._on_details_link)
        self.details.setStyleSheet("color: %s;" % MUTED)
        self.details.setVisible(False)
        layout.addWidget(self.details)
        self._render_footer()
        self.setWidget(panel)

    # ------------------------------------------------------------------ building blocks
    def _section(self, title, widget):
        box = QWidget()
        box.head = None
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(3)
        head = QLabel(title)
        head.setTextFormat(enum(Qt, "TextFormat", "PlainText"))  # plan names come from the WFS
        head.setStyleSheet("font-weight: bold;")
        box.head = head
        lay.addWidget(head)
        lay.addWidget(widget, 1)
        self.split.addWidget(box)
        return box

    def _render_footer(self):
        link = "Hide" if self._details_open else "Details"
        self.footer.setText("Guidance only, not legal advice. <a href='details' style='color:"
                            "#1a5fb4; text-decoration:none'>%s</a>" % link)
        self.details.setVisible(self._details_open)

    def _toggle_details(self, _link=""):
        self._details_open = not self._details_open
        self._render_footer()

    def _on_details_link(self, link):
        if link == "ea":
            self.earlyAccessRequested.emit()  # opens the page and resolves the strip
        elif link.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(link))

    def _on_anchor(self, url):
        target = url.toString()
        if target.startswith("goto:"):
            self.findings.scrollToAnchor(target[5:])
        elif target.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(target))

    def _show_outside(self, message):
        self.split.setVisible(message is None)
        self.outside.setVisible(message is not None)
        if message is not None:
            self.outside.setText("<p><b>Outside Berlin</b></p><p style='color:%s'>%s</p>"
                                 % (MUTED, escape(message)))

    # ------------------------------------------------------------------ results
    def querying(self, lat, lon):
        self.status.setText(f"Looking up {lat:.5f}, {lon:.5f}…")
        self._show_outside(None)
        self.findings.clear()
        self.provisions.clear()

    def show_result(self, result):
        point = result["point"]
        self.status.setText(f"Point {point['lat']:.5f}, {point['lon']:.5f}")
        if result.get("status") == "outside_berlin":
            self._show_outside(result.get("note", ""))
            self.findings.setHtml(render_html(result))  # kept for tools that read the text
            self._fill_provisions([])
            return
        self._show_outside(None)
        self.findings.setHtml(render_html(result))
        self._fill_provisions(provision_rows(result))
        self._balance()

    def _fill_provisions(self, rows):
        self.provisions.clear()
        if not rows:
            self.provisions.addTopLevelItem(QTreeWidgetItem(["No selected provisions for this point."]))
            self.provisions_section.setVisible(False)
            return
        plans = list(dict.fromkeys(row["plan"] for row in rows))
        self.provisions_section.head.setText(
            "Written provisions (Textliche Festsetzungen)" if len(plans) > 1
            else "Written provisions of B-Plan %s" % plans[0])
        for plan in plans:
            if len(plans) > 1:
                head = QTreeWidgetItem(["B-Plan %s" % plan])
                font = QFont()
                font.setBold(True)
                head.setFont(0, font)
                head.setForeground(0, QBrush(QColor(MUTED)))
                head.setFlags(enum(Qt, "ItemFlag", "NoItemFlags"))
                self.provisions.addTopLevelItem(head)
            for row in (r for r in rows if r["plan"] == plan):
                item = QTreeWidgetItem([f"{row['cite']} · {row['title']}"])
                item.setToolTip(0, f"B-Plan {row['plan']} · Textliche Festsetzung "
                                   f"{row['number']}: {row['title']}")
                item.setData(0, enum(Qt, "ItemDataRole", "UserRole"), row)
                item.addChild(QTreeWidgetItem([""]))
                self.provisions.addTopLevelItem(item)
        self.provisions_section.setVisible(True)
        rows_shown = self.provisions.topLevelItemCount()
        row_height = max(self.provisions.sizeHintForRow(0), 18)
        self.provisions.setMinimumHeight(min(rows_shown, 4) * row_height + 8)

    def _balance(self):
        """Give the plan pane the height its cards need and the provisions the rest."""
        total = sum(self.split.sizes())
        if total <= 0:
            return
        if self.provisions_section.isHidden():
            self.split.setSizes([total, 0])
            return
        self.findings.document().setTextWidth(self.findings.viewport().width())
        cards = int(self.findings.document().size().height()) + 30
        tree = self.provisions
        need = 34  # header label and frame
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            need += max(tree.sizeHintForRow(0), 18)
            if item.isExpanded() and item.childCount():
                widget = tree.itemWidget(item.child(0), 0)
                need += widget.minimumHeight() if widget is not None else 0
        low = 4 * max(tree.sizeHintForRow(0), 18) + 34
        prov = max(low, min(need, total - 160))
        plan = max(160, min(cards, total - prov))
        self.split.setSizes([plan, total - plan])

    def show_early_access(self, visible):
        self.ea_strip.setVisible(bool(visible))

    def show_error(self, error):
        self.status.setText("Plan lookup stopped.")
        self._show_outside(None)
        self.findings.setHtml(f"<p>Could not complete the lookup. {escape(error)}</p>")
        self._fill_provisions([])

    def _expand_provision(self, item):
        row = item.data(0, enum(Qt, "ItemDataRole", "UserRole"))
        child = item.child(0)
        if not row or child is None or self.provisions.itemWidget(child, 0) is not None:
            return
        details = QTextBrowser()
        details.setOpenExternalLinks(True)
        details.setFrameShape(enum(QFrame, "Shape", "NoFrame"))
        details.setStyleSheet("background: transparent;")
        details.document().setDefaultStyleSheet(LINK_STYLE)
        source = '<a href="%s">Official source (PDF, p. %s)</a>' % (
            escape(row["url"], quote=True), escape(str(row.get("page") or "1")))
        details.setHtml("<p style='margin:0 0 4px 0'>%s</p><p style='margin:0'>%s</p>" % (
            source, escape(row["text"])))
        details.setMinimumHeight(130)
        child.setSizeHint(0, details.minimumSize())
        self.provisions.setItemWidget(child, 0, details)
