"""Tests of tools/lock.py with small Git repositories: gathering, writing, --check, --report, published tags."""

import json
import shutil

import pytest
import world
from gitrepo import commit, git, publish
from world import PSI, TD, UVVM_COMPONENTS

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def load_tool():
    return world.load_tool("lock")


def args(w, *extra, tag="v0.1.1"):
    return world.lock_args(w, *extra, tag=tag)


def test_writes_the_manifest(world):
    tool = load_tool()
    assert tool.main(args(world)) == 0
    m = json.loads((world["tmp"] / "lock.json").read_text(encoding="utf-8"))
    assert m["website"]["commit"] == world["web"]
    assert m["website"]["generator"] == "0.9.8-beta" and m["website"]["catalog"] == "abcdef012345"
    assert m["referenceSystems"]["tag"] == "v0.1.1"
    assert m["referenceSystems"]["commit"] == git(world["rs"], "rev-parse", "v0.1.1^{commit}")
    assert m["openLogic"]["commit"] == world["olo"]
    assert m["openLogic"]["submodules"] == {"3rdParty/en_cl_fix": world["fix"]}
    assert m["uvvm"]["commit"] == world["uv"]
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


def test_the_manifest_lists_the_snapshot_files(world):
    tool = load_tool()
    assert tool.main(args(world)) == 0
    files = json.loads((world["tmp"] / "lock.json").read_text(encoding="utf-8"))["files"]
    assert sorted(files) == ["olo", "opencompact", "openwire", "refsys", "uvvm"]
    assert sorted(files["openwire"]) == ["LGPL2_1.txt", "License.txt", "compile_order.txt", "hdl/a.vhd",
                                         "sw/owr_regs.h"]
    assert sorted(files["opencompact"]) == ["LGPL2_1.txt", "License.txt", "compile_order.txt", "hdl/b.vhd",
                                            "hdl/ocp_pa/compile_order_sim.txt", "hdl/ocp_pa/sim/m.vhd"]
    assert sorted(files["olo"]) == ["3rdParty/en_cl_fix/LICENSE.md", "3rdParty/en_cl_fix/hdl/en_cl_fix_pkg.vhd",
                                    "LGPL2_1.txt", "License.txt", "compile_order.txt", "src/c.vhd"]
    assert sorted(files["refsys"]) == ["LGPL2_1.txt", "License.txt", "sim/tb/rs_far_end.vhd",
                                       "systems/s/s.composer.json", "tools/composer_ref.txt"]
    assert sorted(files["uvvm"]) == sorted(
        ["LICENSE", TD] + [f"{c}/script/compile_order.txt" for c in UVVM_COMPONENTS]
        + [f"{c}/src/{c}_pkg.vhd" for c in UVVM_COMPONENTS])


def load_snapshot():
    return world.load_tool("snapshot")


def snap_args(w, out, *extra):
    return ["--repos", str(w["repos"]), "--uvvm", str(w["uvvm"]), "--lock", str(w["tmp"] / "lock.json"),
            "--out", str(out), *extra]


def test_snapshot_writes_every_file_byte_for_byte(world):
    assert load_tool().main(args(world)) == 0
    out = world["tmp"] / "hdl"
    (out / "stale").mkdir(parents=True)
    (out / "stale" / "old.vhd").write_text("old", encoding="utf-8")
    assert load_snapshot().main(snap_args(world, out)) == 0
    files = json.loads((world["tmp"] / "lock.json").read_text(encoding="utf-8"))["files"]
    written = sorted(str(f.relative_to(out)).replace("\\", "/") for f in out.rglob("*") if f.is_file())
    assert written == sorted(f"{d}/{p}" for d, e in files.items() for p in e)
    assert (out / "olo" / "3rdParty" / "en_cl_fix" / "hdl" / "en_cl_fix_pkg.vhd").read_bytes() == b"-- fix\n"
    assert (out / "openwire" / "License.txt").read_text(encoding="utf-8") == PSI


def test_snapshot_refuses_a_changed_hash(world, capsys):
    assert load_tool().main(args(world)) == 0
    f = world["tmp"] / "lock.json"
    m = json.loads(f.read_text(encoding="utf-8"))
    m["files"]["openwire"]["hdl/a.vhd"] = "0" * 64
    f.write_text(json.dumps(m), encoding="utf-8")
    assert load_snapshot().main(snap_args(world, world["tmp"] / "hdl")) == 1
    assert "L6: openwire/hdl/a.vhd: the hash differs" in capsys.readouterr().err


def test_snapshot_refuses_a_path_beyond_the_budget(world, capsys):
    repo = world["repos"] / "openwire"
    long_name = "hdl/" + "x" * 120 + ".vhd"
    new = commit(repo, {"compile_order.txt": f"hdl/a.vhd\n{long_name}\n", long_name: "-- long\n"})
    git(repo, "tag", "v0.1.2")
    publish(repo)
    cat_file = world["site"] / "assets/composer/catalog.json"
    catalog = json.loads(cat_file.read_text(encoding="utf-8"))
    catalog["sources"][0]["commit"] = new
    web = commit(world["site"], {"assets/composer/catalog.json": json.dumps(catalog)})
    commit(world["rs"], {"tools/composer_ref.txt": web + "\n"})
    git(world["rs"], "tag", "v0.1.5")
    publish(world["rs"])
    assert load_tool().main(args(world, tag="v0.1.5")) == 0
    assert load_snapshot().main(snap_args(world, world["tmp"] / "hdl")) == 1
    assert "L8: openspacehdl/hdl/openwire/hdl/xxx" in capsys.readouterr().err


def test_a_waived_rule_is_recorded_and_refused_by_the_snapshot(world, capsys):
    rs = world["rs"]
    commit(rs, {}, {"cores/opencompact": world["owr"]})
    git(rs, "tag", "v0.1.2")
    publish(rs)
    tool = load_tool()
    assert tool.main(args(world, "--waive", "L2", tag="v0.1.2")) == 0
    m = json.loads((world["tmp"] / "lock.json").read_text(encoding="utf-8"))
    assert m["waived"] == ["L2"]
    assert "waives L2" in capsys.readouterr().err
    snap = load_snapshot()
    assert snap.main(snap_args(world, world["tmp"] / "hdl")) == 1
    assert "for tests of the build only" in capsys.readouterr().err
    assert snap.main(snap_args(world, world["tmp"] / "hdl", "--allow-waived")) == 0


def test_an_unknown_rule_cannot_be_waived(world, capsys):
    assert load_tool().main(args(world, "--waive", "L99")) == 1
    assert "unknown rules to waive: L99" in capsys.readouterr().err
