# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Saeed Sabzeh
import subprocess
import sys
from configparser import ConfigParser
from json import loads
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_plugin  # noqa: E402


def test_release_zip_is_independently_importable(tmp_path):
    archive = build_plugin.build(tmp_path)
    root = tmp_path / "profile-plugins"
    with ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {
            f"planrecht_berlin/{name}" for name in build_plugin.RUNTIME_FILES
        }
        meta = ConfigParser(interpolation=None)
        meta.read_string(bundle.read("planrecht_berlin/metadata.txt").decode("utf-8"))
        assert meta["general"]["name"] == "Planrecht Berlin"
        assert archive.name == f"planrecht_berlin-{meta['general']['version']}.zip"
        records = loads(bundle.read("planrecht_berlin/data/plans.json"))
        assert all(not field.endswith("_sha256") for record in records.values() for field in record)
        bundle.extractall(root)
    program = """
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from planrecht_berlin import berlin, classFactory
assert Path(berlin.__file__).resolve().parent == Path(sys.argv[1]) / "planrecht_berlin"
assert callable(classFactory)
result = berlin.lookup_city_point(52.46494611, 13.45485200, fetch=lambda url, timeout: {
    "features": [{"properties": {"planid": "0800002-1", "festsg_am": "2019-05-22"}}],
})
assert result["plans"][0]["point_area"]["area_id"] == "ge"
assert not any(name == "norme_milano" or name.startswith("norme_milano.") for name in sys.modules)
"""
    subprocess.run([sys.executable, "-I", "-c", program, str(root)], cwd=tmp_path, check=True)
