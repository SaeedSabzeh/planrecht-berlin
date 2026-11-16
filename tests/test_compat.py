# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planrecht_berlin.compat import enum  # noqa: E402


class Scoped:
    class Flag:
        CanCancel = 1


class Unscoped:
    CanCancel = 2


def test_enum_prefers_scoped_name():
    assert enum(Scoped, "Flag", "CanCancel") == 1


def test_enum_falls_back_to_unscoped_name():
    assert enum(Unscoped, "Flag", "CanCancel") == 2
