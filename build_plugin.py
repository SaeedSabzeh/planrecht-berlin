# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
"""Build the standalone Planrecht Berlin ZIP from the runtime files."""

import argparse
import re
from configparser import ConfigParser
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from planrecht_berlin.berlin import validate_preview_data

ROOT = Path(__file__).resolve().parent
PLUGIN_ID = "planrecht_berlin"
PACKAGE = ROOT / PLUGIN_ID
RUNTIME_FILES = (
    "__init__.py", "berlin.py", "berlin_view.py", "compat.py", "dock.py", "network.py", "plugin.py",
    "urlcheck.py", "metadata.txt", "icon.png", "LICENSE", "data/8-2-1-areas.geojson",
    "data/inhalt_baunvo.json", "data/landesgrenze.geojson", "data/plans.json",
)


def build(output):
    metadata = ConfigParser(interpolation=None)
    metadata.read(PACKAGE / "metadata.txt", encoding="utf-8")
    version = metadata["general"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Planrecht Berlin expects a numeric major.minor.patch version.")
    validate_preview_data(lambda name: (PACKAGE / "data" / name).read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{PLUGIN_ID}-{version}.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for name in RUNTIME_FILES:
            bundle.write(PACKAGE / name, f"{PLUGIN_ID}/{name}")
    with ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("The Planrecht Berlin ZIP contains a corrupt file.")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    options = parser.parse_args()
    print(build(options.dist).resolve())
