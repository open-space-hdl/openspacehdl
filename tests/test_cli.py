"""Tests of the command line: --version and info."""

import json
import re
import subprocess
import sys
from importlib import resources

import pytest

from openspacehdl import __version__
from openspacehdl.cli import main
from openspacehdl.family import Family, Group, Project, load

URL = re.compile(r"https?://")


def data() -> dict:
    return json.loads(resources.files("openspacehdl").joinpath("data/family.json").read_text(encoding="utf-8"))


def blocks(text: str) -> dict[str, str]:
    """The text of each project in the output of info, keyed by its name."""
    names = [p["name"] for p in data()["projects"]]
    found = {}
    for block in text.split("\n\n"):
        first = block.splitlines()[0].strip()
        for n in names:
            if first == n or first.startswith(n + "  "):
                found[n] = block
    return found


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == f"openspacehdl {__version__}"


def test_version_is_semantic():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_python_m():
    r = subprocess.run([sys.executable, "-m", "openspacehdl", "--version"], capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == f"openspacehdl {__version__}"


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "info" in capsys.readouterr().out


def test_info_lists_every_card_in_group_order(capsys):
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    d = data()
    assert set(blocks(out)) == {p["name"] for p in d["projects"]}
    # Groups in the order of project_groups.yml, projects in the order of projects.yml within a group.
    expected = [p["name"] for g in d["groups"] for p in d["projects"] if p["group"] == g["id"]]
    assert [n for n in sorted(expected, key=out.index)] == expected
    for g in d["groups"]:
        if any(p["group"] == g["id"] for p in d["projects"]):
            assert g["title"] in out


def test_public_projects_show_trl_and_links(capsys):
    main(["info"])
    out = blocks(capsys.readouterr().out)
    for p in data()["projects"]:
        if not p["public"]:
            continue
        b = out[p["name"]]
        assert f"Source: https://github.com/open-space-hdl/{p['repo']}" in b
        assert ("Documentation: https://openspacehdl.org/" + p["repo"] + "/" in b) == p["docs"]
        if p.get("trl"):
            assert f"TRL {p['trl']}" in b.splitlines()[0]


def test_coming_soon_projects_have_no_links_and_no_trl(capsys):
    main(["info"])
    out = blocks(capsys.readouterr().out)
    hidden = [p for p in data()["projects"] if not p["public"]]
    assert hidden, "the data has no Coming soon card to test"
    for p in hidden:
        b = out[p["name"]]
        assert "Coming soon" in b.splitlines()[0]
        assert not URL.search(b)
        assert "TRL" not in b
        assert "Source:" not in b and "Documentation:" not in b and "Status:" not in b


def test_coming_soon_data_keeps_only_card_fields():
    for p in data()["projects"]:
        if not p["public"]:
            assert set(p) == {"name", "group", "tagline", "summary", "public"}


@pytest.mark.parametrize("name", ["OpenFibre", "openfibre", "OPENFIBRE", "Open Logic FT", "open-logic-ft"])
def test_info_one_project(capsys, name):
    assert main(["info", name]) == 0
    out = capsys.readouterr().out
    expected = load().find(name)
    assert expected is not None
    assert out.splitlines()[0].strip().startswith(expected.name)
    assert len(blocks(out)) == 1


def test_info_unknown_project(capsys):
    assert main(["info", "NoSuchCore"]) == 2
    err = capsys.readouterr().err
    assert "NoSuchCore" in err
    assert "OpenFibre" in err


def test_data_names_the_website_commit():
    d = data()
    assert d["source"]["repository"] == "open-space-hdl/open-space-hdl.github.io"
    assert re.fullmatch(r"[0-9a-f]{40}", d["source"]["commit"])


def test_find_by_repository_name():
    g = Group("g", "G", "")
    p = Project(name="Example Core", group="g", tagline=(), summary="", public=True, repo="excore")
    f = Family(
        site="https://example.org", github="https://example.org/gh", source_commit="0" * 40, groups=(g,), projects=(p,)
    )
    assert f.find("excore") is p
    assert f.find("example-core") is p
    assert f.find("other") is None
    assert f.docs_url(p) is None
    assert f.source_url(p) == "https://example.org/gh/excore"
    hidden = Project(name="Hidden", group="g", tagline=(), summary="", public=False, repo="hidden", docs=True)
    assert f.source_url(hidden) is None
    assert f.docs_url(hidden) is None
