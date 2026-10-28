"""Tests of the package metadata in pyproject.toml: the dependency on pytest and the optional dependency on VUnit."""

from pathlib import Path

import pytest
from packaging.requirements import Requirement

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def project() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]


def pytest_dependency() -> Requirement:
    (req,) = (Requirement(r) for r in project()["dependencies"])
    return req


def vunit_extra() -> Requirement:
    extras = project()["optional-dependencies"]
    assert list(extras) == ["vunit"]
    (req,) = (Requirement(r) for r in extras["vunit"])
    return req


def test_the_only_dependency_is_pytest():
    req = pytest_dependency()
    assert req.name == "pytest" and not req.extras and req.marker is None


@pytest.mark.parametrize("version,allowed", [
    ("9.0.2", True),        # the pytest of the lab machine, the lower bound the workflow CI tests
    ("9.0.0", True),
    ("9.1.1", True),
    ("8.4.2", False),
    ("10.0.0", False),      # not tested
])
def test_the_pytest_dependency_admits_the_tested_versions(version, allowed):
    assert pytest_dependency().specifier.contains(version) is allowed


def test_the_vunit_extra_names_vunit_hdl():
    req = vunit_extra()
    assert req.name == "vunit_hdl" and not req.extras and req.marker is None


@pytest.mark.parametrize("version,allowed", [
    ("4.7.1", True),        # the release from PyPI the package is tested with
    ("5.0.0.dev7", True),   # the 5.0 development line the package is tested with
    ("5.0.0", True),
    ("4.7.0", False),
    ("4.6.0", False),
    ("5.1.0", False),       # not tested
    ("6.0.0", False),
])
def test_the_vunit_extra_admits_the_tested_versions(version, allowed):
    assert vunit_extra().specifier.contains(version, prereleases=True) is allowed
