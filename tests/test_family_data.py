"""Tests of tools/family_data.py with a small website repository: writing and --check."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from gitrepo import commit, make_repo

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

CONFIG = "url: https://example.org\ngithub_org: https://github.com/example\n"
GROUPS = "- id: g1\n  title: Group one\n  summary: The first group.\n"
PROJECTS = (
    "- name: Alpha\n  repo: alpha\n  group: g1\n  tagline: [STD-1]\n  summary: Alpha core.\n  public: true\n"
    "  docs: true\n  trl: 3\n  trl_status: Verified by simulation.\n"
    "- name: Beta\n  repo: beta\n  group: g1\n  tagline: [STD-2]\n  summary: Beta core.\n  public: false\n"
    "- name: Hidden\n  repo: hidden\n  group: nogroup\n  summary: Not shown.\n  public: true\n"
)


def load_tool():
    spec = importlib.util.spec_from_file_location("family_tool", ROOT / "tools" / "family_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def site(tmp_path):
    path = tmp_path / "site"
    make_repo(path, {"_config.yml": CONFIG, "_data/project_groups.yml": GROUPS, "_data/projects.yml": PROJECTS})
    return path


def args(site, out, *extra):
    return ["--site", str(site), "--commit", "HEAD", "--out", str(out), *extra]


def test_writes_only_card_fields(site, tmp_path):
    out = tmp_path / "family.json"
    assert load_tool().main(args(site, out)) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["site"] == "https://example.org" and d["github"] == "https://github.com/example"
    assert [p["name"] for p in d["projects"]] == ["Alpha", "Beta"]
    assert d["projects"][1] == {"name": "Beta", "group": "g1", "tagline": ["STD-2"], "summary": "Beta core.",
                                "public": False}
    assert d["projects"][0]["trl"] == 3 and d["projects"][0]["repo"] == "alpha"


def test_check_passes_on_a_newer_commit_with_the_same_cards(site, tmp_path, capsys):
    tool = load_tool()
    out = tmp_path / "family.json"
    assert tool.main(args(site, out)) == 0
    first = json.loads(out.read_text(encoding="utf-8"))["source"]["commit"]
    commit(site, {"index.html": "<p>other page</p>\n"})
    assert tool.main(args(site, out, "--check")) == 0
    assert f"equal those of {first[:7]}" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["source"]["commit"] == first


def test_check_fails_when_a_card_changes(site, tmp_path, capsys):
    tool = load_tool()
    out = tmp_path / "family.json"
    assert tool.main(args(site, out)) == 0
    commit(site, {"_data/projects.yml": PROJECTS.replace("trl: 3", "trl: 4")})
    assert tool.main(args(site, out, "--check")) == 1
    assert "differ" in capsys.readouterr().err


def test_check_fails_without_the_file(site, tmp_path):
    assert load_tool().main(args(site, tmp_path / "missing.json", "--check")) == 1
