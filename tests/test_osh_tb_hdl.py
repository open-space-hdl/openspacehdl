"""The unit benches of the bench components (tests/hdl/run.py) in GHDL, when OPENSPACEHDL_HDL_TESTS=1.

They need an installation of openspacehdl with its source snapshots, VUnit and GHDL, and they take several minutes, so
the quality gates (tools/check.py) do not run them. A bench test passes only when every test case passed and none was
skipped (VUnit marks the test cases of a configuration that fails to elaborate as skipped).
"""

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

RUN = Path(__file__).resolve().parent / "hdl" / "run.py"

pytestmark = pytest.mark.skipif(os.environ.get("OPENSPACEHDL_HDL_TESTS") != "1",
                                reason="the GHDL unit benches run with OPENSPACEHDL_HDL_TESTS=1")


def test_the_unit_benches_of_osh_tb(tmp_path):
    pytest.importorskip("vunit")
    if shutil.which("ghdl") is None:
        pytest.skip("needs GHDL")
    from openspacehdl.installed import installed

    if not installed().hdl.is_dir():
        pytest.skip("needs an installation with source snapshots")
    xml = tmp_path / "results.xml"
    r = subprocess.run([sys.executable, str(RUN), "-p", "2", "-o", str(tmp_path / "vunit_out"), "-x", str(xml)],
                       cwd=tmp_path)
    cases = list(ET.parse(xml).getroot().iter("testcase"))
    bad = [c.get("name") for c in cases if c.find("failure") is not None or c.find("error") is not None
           or c.find("skipped") is not None]
    assert r.returncode == 0 and cases and not bad, f"failed or skipped: {bad}"
