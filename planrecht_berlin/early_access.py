# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Quiet invitation to the Pro early-access group.

After the third successful lookup, a one-line strip appears at the bottom of the dock until
the user opens the link or closes it; then it never returns (per QGIS profile). A permanent
link also sits in the footer's Details text.

The plugin collects and sends nothing for this: the link only opens the sign-up page in the
browser, with no user data in the address. Everything stays off until SIGNUP_URL points to a
published page.
"""

from urllib.parse import urlencode

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

SIGNUP_URL = ""  # the website's early-access page, e.g. "https://.../pro"; empty = off
SHOW_AFTER = 3   # successful lookups before the strip appears
PREFIX = "planrecht_berlin/"

STRIP_TEXT = ("Pro is in the works: whole-parcel check, PDF reports and more plans with "
              "reviewed figures.")
LINK_TEXT = "Get free early access"
LINK_TIP = "Opens the sign-up page in your browser. The plugin does not collect your email."
CLOSE_TIP = "Don't show again"
DETAILS_TEXT = "Planrecht Berlin Pro (coming): free early access"
OPEN_FAILED = "The browser could not be opened. Sign-up page: %s"


def enabled():
    return bool(SIGNUP_URL)


def signup_url():
    """The sign-up address with only non-personal hints (source and language)."""
    if not SIGNUP_URL:
        return ""
    sep = "&" if "?" in SIGNUP_URL else "?"
    return SIGNUP_URL + sep + urlencode({"src": "planrecht-berlin", "lang": "en"})


def next_state(count, resolved):
    """(new_count, show_strip) after one more successful lookup. Counting stops once the
    invitation is resolved (opened or closed) or while the feature is off."""
    if resolved or not enabled():
        return count, False
    count = int(count or 0) + 1
    return count, count >= SHOW_AFTER


def read_state():
    """(lookup_count, resolved) from the QGIS profile settings."""
    qs = QgsSettings()
    try:
        count = int(qs.value(PREFIX + "lookup_count", 0) or 0)
    except (TypeError, ValueError):
        count = 0
    resolved = qs.value(PREFIX + "early_access_resolved", False) in (True, "true", "True", 1, "1")
    return count, resolved


def write_count(count):
    QgsSettings().setValue(PREFIX + "lookup_count", int(count))


def resolve():
    QgsSettings().setValue(PREFIX + "early_access_resolved", True)


def open_signup():
    """Open the sign-up page in the browser. True when the browser accepted the request."""
    url = signup_url()
    return bool(url) and bool(QDesktopServices.openUrl(QUrl(url)))
