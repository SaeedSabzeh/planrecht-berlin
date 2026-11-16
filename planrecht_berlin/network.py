# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Read the Berlin WFS through the QGIS network manager and proxy settings."""

import json
from threading import Event, Thread
from time import monotonic

from qgis.core import QgsFeedback, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from .compat import enum
from .urlcheck import check_url


def fetch_json(url, timeout, is_canceled):
    if is_canceled():
        raise OSError("Request canceled")

    request = QNetworkRequest(QUrl(check_url(url)))
    if hasattr(request, "setTransferTimeout"):
        request.setTransferTimeout(int(timeout * 1000))
    feedback = QgsFeedback()
    complete = Event()
    deadline = monotonic() + timeout + 1

    def cancel_or_time_out():
        while not complete.wait(0.1):
            if is_canceled() or monotonic() >= deadline:
                if feedback.isCanceled():
                    # A cancellation during setup can predate QGIS connecting the reply.
                    feedback.canceled.emit()
                else:
                    feedback.cancel()

    watchdog = Thread(target=cancel_or_time_out, daemon=True)
    watchdog.start()
    try:
        reply = QgsNetworkAccessManager.instance().blockingGet(request, feedback=feedback)
    finally:
        complete.set()
        watchdog.join()

    status = reply.attribute(enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute"))
    if feedback.isCanceled():
        raise OSError("Request timed out or was canceled")
    if status is None or not 200 <= int(status) < 300:
        raise OSError(f"Berlin WFS returned HTTP {status}" if status else reply.errorString())
    try:
        return json.loads(bytes(reply.content()))
    except ValueError as error:
        raise ValueError("Berlin WFS returned unreadable JSON") from error
