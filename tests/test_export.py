"""Tests of the Git bundles (tools/bundles.py) and of openspacehdl export, on the world of tests/world.py."""

import hashlib
import json
import shutil

import pytest
import world as worldlib
from gitrepo import commit, git

from openspacehdl import cli, export, lock
from openspacehdl.installed import Installed


@pytest.fixture(scope="module")
def package(world_template, tmp_path_factory):
    """An installed package built from the world: lock manifest, snapshots and bundles in <dir>/pkg."""
    pkg = tmp_path_factory.mktemp("pkg")
    w = {**world_template, "repos": world_template["tmp"] / "repos", "site": world_template["tmp"] / "site",
         "rs": world_template["tmp"] / "repos" / "reference-systems", "uvvm": world_template["tmp"] / "uvvm"}
    manifest = pkg / "data" / "lock.json"
    manifest.parent.mkdir(parents=True)
    assert worldlib.load_tool("lock").main(worldlib.lock_args(w, out=manifest)) == 0
    assert worldlib.load_tool("snapshot").main(["--repos", str(w["repos"]), "--uvvm", str(w["uvvm"]), "--lock",
                                             str(manifest), "--out", str(pkg / "hdl"), "--bundles-out",
                                             str(pkg / "bundles")]) == 0
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    return {"world": w, "dir": pkg, "raw": raw,
            "inst": Installed(lock.Lock.from_dict(raw), pkg / "hdl", pkg / "bundles", manifest)}


@pytest.fixture
def inst(package, monkeypatch):
    monkeypatch.setattr(export, "installed", lambda: package["inst"])
    return package["inst"]


def test_the_manifest_lists_the_bundles(package):
    b = package["raw"]["bundles"]
    assert sorted(b) == ["en_cl_fix", "olo", "opencompact", "openwire", "refsys"]
    w = package["world"]
    ocp_tags = {n for n in b["opencompact"]["refs"] if n.startswith("refs/tags/")}
    assert ocp_tags == {"refs/tags/v0.1.0", "refs/tags/v0.1.1"}
    assert b["opencompact"]["refs"]["refs/heads/main"] == w["ocp"] == b["opencompact"]["commit"]
    assert b["olo"]["branch"] == "fault-tolerant" and "refs/tags/4.7.0-ft.8" in b["olo"]["refs"]
    assert b["en_cl_fix"] == {"branch": "open-logic", "commit": w["fix"], "url": worldlib.FIX_URL,
                              "refs": {"refs/heads/open-logic": w["fix"]}}
    assert b["refsys"]["url"] == "https://github.com/open-space-hdl/reference-systems.git"


def test_the_bundles_carry_the_refs_of_the_manifest(package):
    bundles = worldlib.load_tool("bundles")
    for bid, spec in package["raw"]["bundles"].items():
        assert bundles.list_heads(package["dir"] / "bundles" / f"{bid}.bundle") == spec["refs"]


def test_an_unpublished_tag_stays_out_of_the_bundle(world):
    bundles = worldlib.load_tool("bundles")
    repo = world["repos"] / "opencompact"
    git(repo, "tag", "local-only")
    refs = bundles.refs(repo, world["ocp"], "main", bundles.published_tags(repo))
    assert "refs/tags/local-only" not in refs and "refs/tags/v0.1.1" in refs
    assert "refs/tags/local-only" in bundles.refs(repo, world["ocp"], "main", None)


def test_the_clone_is_only_read(world):
    bundles = worldlib.load_tool("bundles")
    repo = world["repos"] / "opencompact"
    before = git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    spec = {"refs": bundles.refs(repo, world["ocp"], "main", None)}
    bundles.create(repo, spec, world["tmp"] / "out" / "x.bundle")
    assert git(repo, "for-each-ref", "--format=%(refname) %(objectname)") == before
    assert bundles.list_heads(world["tmp"] / "out" / "x.bundle") == spec["refs"]


def files_under(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_export_tree(inst, tmp_path):
    dest = tmp_path / "export"
    assert export.export_tree(dest) == ["openwire", "opencompact", "open-logic-ft", "reference-systems", "uvvm"]
    names = {"openwire": "openwire", "opencompact": "opencompact", "olo": "open-logic-ft",
             "refsys": "reference-systems", "uvvm": "uvvm"}
    expected = sorted([f"{names[d]}/{p}" for d, e in inst.lock.files.items() for p in e] + ["openspacehdl-lock.json"])
    assert files_under(dest) == expected
    for d, entries in inst.lock.files.items():
        for p, h in entries.items():
            assert hashlib.sha256((dest / names[d] / p).read_bytes()).hexdigest() == h
    assert json.loads((dest / "openspacehdl-lock.json").read_text(encoding="utf-8"))["format"] == "openspacehdl-lock"


def test_export_tree_of_one_core(inst, tmp_path):
    dest = tmp_path / "export"
    assert export.export_tree(dest, ["OpenCompact"]) == ["opencompact", "open-logic-ft"]
    assert sorted(p.name for p in dest.iterdir()) == ["open-logic-ft", "opencompact", "openspacehdl-lock.json"]


def test_export_refuses_a_directory_that_is_not_empty(inst, tmp_path):
    (tmp_path / "x").write_text("user data", encoding="utf-8")
    with pytest.raises(export.ExportError, match="not empty"):
        export.export_tree(tmp_path)
    with pytest.raises(export.ExportError, match="not empty"):
        export.export_git(tmp_path)
    assert (tmp_path / "x").read_text(encoding="utf-8") == "user data"


def test_export_git(inst, package, tmp_path):
    dest = tmp_path / "export"
    w = package["world"]
    assert export.export_git(dest) == ["open-logic-ft", "openwire", "opencompact", "reference-systems"]
    for name, commit, branch in (("openwire", w["owr"], "main"), ("opencompact", w["ocp"], "main"),
                                 ("open-logic-ft", w["olo"], "fault-tolerant")):
        assert git(dest / name, "rev-parse", "HEAD") == commit
        assert git(dest / name, "rev-parse", "--abbrev-ref", "HEAD") == branch
        assert git(dest / name, "remote", "get-url", "origin") == f"https://github.com/open-space-hdl/{name}.git"
    assert git(dest / "opencompact", "tag").split() == ["v0.1.0", "v0.1.1"]
    assert int(git(dest / "opencompact", "rev-list", "--count", "HEAD")) == 2
    fix = dest / "open-logic-ft" / "3rdParty" / "en_cl_fix"
    assert git(fix, "rev-parse", "HEAD") == w["fix"]
    assert git(fix, "remote", "get-url", "origin") == worldlib.FIX_URL
    assert (fix / "hdl" / "en_cl_fix_pkg.vhd").is_file()
    rs = dest / "reference-systems"
    status = git(rs, "submodule", "status").splitlines()
    assert len(status) == 2 and not any(line.startswith(("+", "-", "U")) for line in status), status
    assert git(rs / "cores" / "opencompact", "rev-parse", "HEAD") == w["ocp"]
    assert git(rs / "cores" / "open-logic-ft" / "3rdParty" / "en_cl_fix", "rev-parse", "HEAD") == w["fix"]
    assert git(rs, "config", "submodule.cores/opencompact.url") == "https://github.com/open-space-hdl/opencompact.git"
    assert (dest / "openspacehdl-lock.json").is_file()


def test_export_git_of_one_core(inst, tmp_path):
    dest = tmp_path / "export"
    assert export.export_git(dest, ["openwire"]) == ["open-logic-ft", "openwire"]
    assert sorted(p.name for p in dest.iterdir()) == ["open-logic-ft", "openspacehdl-lock.json", "openwire"]


def test_export_git_without_a_bundle(package, monkeypatch, tmp_path):
    inst = package["inst"]
    missing = Installed(inst.lock, inst.hdl, tmp_path / "no-bundles", inst.manifest)
    monkeypatch.setattr(export, "installed", lambda: missing)
    with pytest.raises(export.ExportError, match="the bundle olo is missing"):
        export.export_git(tmp_path / "export")


def test_the_command(inst, tmp_path, capsys):
    assert cli.main(["export", str(tmp_path / "t"), "--core", "openwire"]) == 0
    assert "exported source snapshots" in capsys.readouterr().out
    assert cli.main(["export", str(tmp_path / "t")]) == 1
    assert "not empty" in capsys.readouterr().err


def test_a_bundle_with_other_refs_than_its_spec_is_refused(world, monkeypatch):
    bundles = worldlib.load_tool("bundles")
    repo = world["repos"] / "opencompact"
    spec = {"refs": bundles.refs(repo, world["ocp"], "main", None)}
    monkeypatch.setattr(bundles, "list_heads", lambda _: {})
    with pytest.raises(bundles.BundleError, match="the refs of the bundle differ"):
        bundles.create(repo, spec, world["tmp"] / "out" / "x.bundle")


def test_export_tree_of_a_damaged_installation(package, monkeypatch, tmp_path):
    inst = package["inst"]
    hdl = tmp_path / "hdl"
    shutil.copytree(inst.hdl, hdl)
    (hdl / "opencompact" / "hdl" / "b.vhd").write_text("-- changed\n", encoding="utf-8")
    damaged = Installed(inst.lock, hdl, inst.bundles, inst.manifest)
    monkeypatch.setattr(export, "installed", lambda: damaged)
    with pytest.raises(export.OshError, match="opencompact/hdl/b.vhd is missing or differs"):
        export.export_tree(tmp_path / "export")


def test_the_bundle_branch_is_at_the_pinned_commit_when_the_clone_is_ahead(world):
    bundles = worldlib.load_tool("bundles")
    repo = world["repos"] / "opencompact"
    newer = commit(repo, {"hdl/b.vhd": "-- after the release\n"})
    spec = {"refs": bundles.refs(repo, world["ocp"], "main", None)}
    target = world["tmp"] / "out" / "x.bundle"
    bundles.create(repo, spec, target)
    heads = bundles.list_heads(target)
    assert heads["refs/heads/main"] == world["ocp"] != newer
    assert git(repo, "rev-parse", "main") == newer
