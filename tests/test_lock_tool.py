"""Tests of tools/lock.py with small Git repositories: gathering, writing, --check, --report, published tags."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from gitrepo import commit, git, make_repo, publish

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def load_tool():
    spec = importlib.util.spec_from_file_location("lock_tool", ROOT / "tools" / "lock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LICENSE = "PSI HDL Library License, Version 1.0\n======\n"
UVVM = "5" * 40
FIX = "6" * 40


@pytest.fixture
def world(tmp_path):
    """Website, reference-systems, two cores and Open Logic FT, consistent; the clones are in tmp_path/repos."""
    repos = tmp_path / "repos"
    owr = make_repo(repos / "openwire", {"License.txt": LICENSE, "compile_order.txt": "hdl/a.vhd\n"}, {"uvvm": UVVM})
    git(repos / "openwire", "tag", "v0.1.0")
    ocp = make_repo(repos / "opencompact", {"License.txt": LICENSE, "compile_order.txt": "hdl/b.vhd\n",
                                            "hdl/ocp_pa/compile_order_sim.txt": "hdl/ocp_pa/sim/m.vhd\n"},
                    {"uvvm": UVVM})
    git(repos / "opencompact", "tag", "-a", "v0.1.1", "-m", "release")
    olo = make_repo(repos / "open-logic-ft", {"License.txt": LICENSE, "compile_order.txt": "src/c.vhd\n"},
                    {"3rdParty/en_cl_fix": FIX})
    git(repos / "open-logic-ft", "tag", "-a", "4.7.0-ft.8", "-m", "ft.8")
    catalog = {
        "format": "open-space-composer-catalog", "formatVersion": 1, "id": "abcdef012345",
        "sources": [
            {"id": "openwire", "name": "OpenWire", "repo": "openwire", "commit": owr, "library": "openwire",
             "fileList": "compile_order.txt", "fileListFormat": "files", "verifiedWith": "4.7.0-ft.6"},
            {"id": "opencompact", "name": "OpenCompact", "repo": "opencompact", "commit": ocp,
             "library": "opencompact", "fileList": "compile_order.txt", "fileListFormat": "files",
             "verifiedWith": "4.7.0-ft.6"},
            {"id": "olo", "name": "Open Logic FT", "repo": "open-logic-ft", "tag": "4.7.0-ft.8", "commit": olo,
             "library": "olo", "fileList": "compile_order.txt", "fileListFormat": "files"},
        ],
    }
    site = tmp_path / "site"
    web = make_repo(site, {
        "assets/composer/catalog.json": json.dumps(catalog),
        "assets/composer/js/model/serialize.js":
            "export const GENERATOR = { name: 'Open Space Composer', version: '0.9.8-beta' };\n",
        "_data/projects.yml": "- name: OpenWire\n  repo: openwire\n  public: true\n  trl: 3\n"
                              "- name: OpenCompact\n  repo: opencompact\n  public: true\n  trl: 3\n",
    })
    rs = repos / "reference-systems"
    make_repo(rs, {"License.txt": LICENSE, "tools/composer_ref.txt": web + "\n"},
              {"cores/opencompact": ocp, "cores/open-logic-ft": olo})
    git(rs, "tag", "-a", "v0.1.1", "-m", "release")
    for r in ("openwire", "opencompact", "open-logic-ft", "reference-systems"):
        publish(repos / r)
    return {"tmp": tmp_path, "repos": repos, "site": site, "web": web, "owr": owr, "ocp": ocp, "olo": olo, "rs": rs}


def args(w, *extra, tag="v0.1.1"):
    return ["--site", str(w["site"]), "--site-commit", "HEAD", "--refsys", str(w["rs"]), "--refsys-tag", tag,
            "--repos", str(w["repos"]), "--out", str(w["tmp"] / "lock.json"), *extra]


def test_writes_the_manifest(world):
    tool = load_tool()
    assert tool.main(args(world)) == 0
    m = json.loads((world["tmp"] / "lock.json").read_text(encoding="utf-8"))
    assert m["website"]["commit"] == world["web"]
    assert m["website"]["generator"] == "0.9.8-beta" and m["website"]["catalog"] == "abcdef012345"
    assert m["referenceSystems"]["tag"] == "v0.1.1"
    assert m["referenceSystems"]["commit"] == git(world["rs"], "rev-parse", "v0.1.1^{commit}")
    assert m["openLogic"]["commit"] == world["olo"] and m["openLogic"]["submodules"] == {"3rdParty/en_cl_fix": FIX}
    assert m["uvvm"]["commit"] == UVVM
    cores = {c["id"]: c for c in m["cores"]}
    assert cores["opencompact"]["tag"] == "v0.1.1" and cores["openwire"]["tag"] == "v0.1.0"
    assert cores["opencompact"]["models"] == {"ocp_pa": "hdl/ocp_pa/compile_order_sim.txt"}
    assert cores["openwire"]["license"] == "PSI HDL Library License, Version 1.0"


def test_check_compares_with_the_written_manifest(world, capsys):
    tool = load_tool()
    assert tool.main(args(world)) == 0
    assert tool.main(args(world, "--check")) == 0
    f = world["tmp"] / "lock.json"
    f.write_text(f.read_text(encoding="utf-8").replace("0.9.8-beta", "0.9.7-beta"), encoding="utf-8")
    assert tool.main(args(world, "--check")) == 1
    assert "differs" in capsys.readouterr().err


def test_a_mismatch_writes_nothing(world, capsys):
    rs = world["rs"]
    commit(rs, {}, {"cores/opencompact": world["owr"]})
    git(rs, "tag", "v0.1.2")
    publish(rs)
    tool = load_tool()
    assert tool.main(args(world, tag="v0.1.2")) == 1
    assert "L2: opencompact" in capsys.readouterr().err
    assert not (world["tmp"] / "lock.json").exists()


def test_report_lists_the_violations(world, capsys):
    tool = load_tool()
    commit(world["rs"], {"tools/composer_ref.txt": "f" * 40 + "\n"})
    git(world["rs"], "tag", "v0.1.3")
    publish(world["rs"])
    assert tool.main(args(world, "--report", tag="v0.1.3")) == 1
    out = capsys.readouterr().out
    assert "L4: reference-systems v0.1.3 was checked against website fffffff" in out
    assert "1 violation(s)" in out
    assert tool.main(args(world, "--report")) == 0


def test_an_unpublished_tag_breaks_l1_unless_offline(world, capsys):
    repo = world["repos"] / "openwire"
    new = commit(repo, {"hdl/a.vhd": "-- new\n"})
    git(repo, "tag", "v0.2.0")
    cat_file = world["site"] / "assets/composer/catalog.json"
    catalog = json.loads(cat_file.read_text(encoding="utf-8"))
    catalog["sources"][0]["commit"] = new
    commit(world["site"], {"assets/composer/catalog.json": json.dumps(catalog)})
    commit(world["rs"], {"tools/composer_ref.txt": git(world["site"], "rev-parse", "HEAD") + "\n"})
    git(world["rs"], "tag", "v0.1.4")
    publish(world["rs"])
    tool = load_tool()
    assert tool.main(args(world, "--report", tag="v0.1.4")) == 1
    assert "openwire: the release tag v0.2.0 is not on the remote" in capsys.readouterr().out
    assert tool.main(args(world, "--report", "--offline", tag="v0.1.4")) == 0


def test_a_missing_clone_is_an_input_error(world, capsys):
    (world["repos"] / "openwire").rename(world["repos"] / "elsewhere")
    tool = load_tool()
    assert tool.main(args(world)) == 2
    assert "no clone of openwire" in capsys.readouterr().err
