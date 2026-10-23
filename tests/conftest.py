"""Fixtures shared by the tests of the tools."""

import shutil

import pytest

import world as world_module


@pytest.fixture(scope="session")
def world_template(tmp_path_factory):
    """The world of tests/world.py, built once per session."""
    if shutil.which("git") is None:
        pytest.skip("needs git")
    return world_module.build(tmp_path_factory.mktemp("world"))


@pytest.fixture
def world(world_template, tmp_path):
    """A copy of the world in tmp_path, for one test."""
    return world_module.copy(world_template, tmp_path)
