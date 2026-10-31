"""Tests of add_core and add_uvvm against a recording stand-in for the VUnit object and an installed snapshot."""

import hashlib
from pathlib import Path

import pytest

import openspacehdl as osh
from openspacehdl import lock, vunit


class Source:
    def __init__(self, name):
        self.name = name
        self.options = []

    def add_compile_option(self, name, value):
        self.options.append((name, value))


class Lib:
    def __init__(self, name):
        self.name = name
        self.files = []
        self.sources = {}
        self.options = []

    def add_source_file(self, file_name, vhdl_standard=None):
        assert vhdl_standard == "2008"
        self.files.append(file_name)
        self.sources[file_name] = Source(file_name)
        return self.sources[file_name]

    def add_compile_option(self, name, value):
        self.options.append((name, value))


class FakeVUnit:
    """Records the calls that openspacehdl makes; the API subset of VUnit 4.7 and 5.0."""

    def __init__(self, *existing):
        self.libs = {n: Lib(n) for n in existing}

    def add_library(self, name, vhdl_standard=None):
        assert name not in self.libs and vhdl_standard == "2008"
        self.libs[name] = Lib(name)
        return self.libs[name]

    def library(self, name):
        return self.libs[name]

    def get_libraries(self, pattern="*", allow_empty=False):
        assert pattern == "*" and allow_empty
        return list(self.libs.values())


RELAXED = ["-frelaxed", "-Wno-hide", "-Wno-shared"]
TREE = {
    "olo": {"compile_order.txt": "src/olo_base_pkg.vhd\n3rdParty/en_cl_fix/hdl/en_cl_fix_pkg.vhd\n",
            "src/olo_base_pkg.vhd": "-- olo\n", "3rdParty/en_cl_fix/hdl/en_cl_fix_pkg.vhd": "-- fix\n"},
    "openwire": {"compile_order.txt": "# order\nhdl/owr_pkg.vhd\nhdl/owr_core.vhd\n", "hdl/owr_pkg.vhd": "-- pkg\n",
                 "hdl/owr_core.vhd": "-- core\n"},
    "openfibre": {"compile_order.txt": "hdl/ofb_core.vhd\n", "hdl/ofb_core.vhd": "-- core\n",
                  "hdl/ofb_pa_gty/compile_order_sim.txt":
                      "tb/ofb_tb_8b10b_pkg.vhd\nhdl/ofb_pa_gty/src/ofb_pa_gty.vhd\n",
                  "tb/ofb_tb_8b10b_pkg.vhd": "-- 8b10b\n", "hdl/ofb_pa_gty/src/ofb_pa_gty.vhd": "-- entity\n"},
    "openrmap": {"compile_order.txt": "hdl/omap_core.vhd\n", "hdl/omap_core.vhd": "-- rmap\n"},
    "openspp": {"compile_order.txt": "hdl/spp_nchar.vhd\n", "hdl/spp_nchar.vhd": "-- nchar\n"},
    "uvvm": {"uvvm_util/script/compile_order.txt": "# library uvvm_util\n../src/types_pkg.vhd\n",
             "uvvm_util/src/types_pkg.vhd": "-- types\n",
             "bitvis_vip_axilite/script/compile_order.txt":
                 "# library bitvis_vip_axilite\n../src/axilite_bfm_pkg.vhd\n"
                 "../../uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd\n",
             "bitvis_vip_axilite/src/axilite_bfm_pkg.vhd": "-- bfm\n",
             "uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd": "-- td\n"},
}


def manifest(files):
    core = {"repository": "x", "commit": "1" * 40, "fileList": "compile_order.txt", "fileListFormat": "files",
            "trl": 3, "license": "PSI"}
    return {
        "format": "openspacehdl-lock", "version": 1, "package": "0.1.0",
        "website": {"commit": "7" * 40, "catalog": "abc", "generator": "0.9.8-beta"},
        "referenceSystems": {"tag": "v0.1.1", "commit": "4" * 40},
        "openLogic": {"tag": "4.7.0-ft.8", "commit": "3" * 40, "library": "olo", "fileList": "compile_order.txt"},
        "uvvm": {"commit": "5" * 40},
        "cores": [
            {**core, "id": "openwire", "name": "OpenWire", "tag": "v0.1.0", "library": "openwire",
             "verifiedWith": "4.7.0-ft.8", "models": {}},
            {**core, "id": "openfibre", "name": "OpenFibre", "tag": "v0.1.1", "library": "openfibre",
             "verifiedWith": "4.7.0-ft.6", "models": {"ofb_pa_gty": "hdl/ofb_pa_gty/compile_order_sim.txt"}},
            {**core, "id": "openrmap", "name": "OpenRMAP", "tag": "v0.1.0", "library": "openrmap",
             "verifiedWith": "4.7.0-ft.8", "models": {}},
            {**core, "id": "openspp", "name": "OpenSPP", "tag": "v0.1.0", "library": "openspp",
             "verifiedWith": "4.7.0-ft.8", "models": {}},
        ],
        "files": files,
    }


@pytest.fixture
def inst(tmp_path, monkeypatch):
    files = {}
    for d, entries in TREE.items():
        files[d] = {}
        for p, text in entries.items():
            f = tmp_path / "hdl" / d / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(text.encode())
            files[d][p] = hashlib.sha256(text.encode()).hexdigest()
    installed = vunit.Installed(lock.Lock.from_dict(manifest(files)), tmp_path / "hdl")
    monkeypatch.setattr(vunit, "installed", lambda: installed)
    return installed


def rel(inst, paths):
    """The added files, relative to the snapshot directory."""
    return [Path(p).relative_to(inst.hdl).as_posix() for p in paths]


def test_add_core_adds_open_logic_and_the_core(inst):
    vu = FakeVUnit()
    lib = osh.add_core(vu, "openwire")
    assert sorted(vu.libs) == ["olo", "openwire"]
    assert rel(inst, vu.libs["olo"].files) == ["olo/src/olo_base_pkg.vhd",
                                               "olo/3rdParty/en_cl_fix/hdl/en_cl_fix_pkg.vhd"]
    assert lib is vu.libs["openwire"]
    assert rel(inst, lib.files) == ["openwire/hdl/owr_pkg.vhd", "openwire/hdl/owr_core.vhd"]
    assert vu.libs["olo"].options == [("ghdl.a_flags", RELAXED)]
    assert lib.options == [] and all(s.options == [] for s in lib.sources.values())


def test_a_second_core_reuses_open_logic(inst, capsys):
    vu = FakeVUnit()
    osh.add_core(vu, "openwire")
    olo_files = list(vu.libs["olo"].files)
    lib = osh.add_core(vu, "OpenFibre")
    assert sorted(vu.libs) == ["olo", "openfibre", "openwire"]
    assert vu.libs["olo"].files == olo_files
    assert rel(inst, lib.files) == ["openfibre/hdl/ofb_core.vhd", "openfibre/tb/ofb_tb_8b10b_pkg.vhd",
                                    "openfibre/hdl/ofb_pa_gty/src/ofb_pa_gty.vhd"]
    relaxed = sorted(rel(inst, [n for n, s in lib.sources.items() if s.options == [("ghdl.a_flags", RELAXED)]]))
    assert relaxed == ["openfibre/hdl/ofb_pa_gty/src/ofb_pa_gty.vhd", "openfibre/tb/ofb_tb_8b10b_pkg.vhd"]
    assert lib.options == []
    out = capsys.readouterr().out
    assert "OpenFibre v0.1.1 was verified with Open Logic FT 4.7.0-ft.6; this package uses 4.7.0-ft.8" in out
    assert "OpenWire" not in out


def test_without_models(inst):
    vu = FakeVUnit()
    lib = osh.add_core(vu, "openfibre", models=False)
    assert rel(inst, lib.files) == ["openfibre/hdl/ofb_core.vhd"]


def test_the_same_core_twice_returns_its_library(inst):
    vu = FakeVUnit()
    first = osh.add_core(vu, "openwire")
    assert osh.add_core(vu, "open-wire") is first
    assert len(first.files) == 2


def test_an_unknown_core(inst):
    with pytest.raises(osh.UnknownCoreError, match="no core 'nosuchcore'.*openwire, openfibre"):
        osh.add_core(FakeVUnit(), "nosuchcore")


def test_a_core_that_is_coming_soon(inst):
    with pytest.raises(osh.UnknownCoreError, match="Open1553 is not released yet"):
        osh.add_core(FakeVUnit(), "open1553")


def test_a_public_core_without_a_release_in_the_catalog(inst):
    with pytest.raises(osh.UnknownCoreError, match="OpenCompact is not in openspacehdl"):
        osh.add_core(FakeVUnit(), "opencompact")


def test_a_foreign_open_logic(inst):
    vu = FakeVUnit("olo")
    with pytest.raises(osh.OpenLogicConflictError, match="never mixes two Open Logic versions"):
        osh.add_core(vu, "openwire")
    assert sorted(vu.libs) == ["olo"]


def test_a_foreign_library_of_the_core_name(inst):
    vu = FakeVUnit("openwire")
    with pytest.raises(osh.LibraryConflictError, match="library openwire"):
        osh.add_core(vu, "openwire")
    assert sorted(vu.libs) == ["openwire"]


@pytest.mark.parametrize("damage", ["change", "delete"])
def test_a_damaged_installation(inst, damage):
    f = inst.hdl / "openwire" / "hdl" / "owr_core.vhd"
    if damage == "change":
        f.write_text("-- changed\n", encoding="utf-8")
    else:
        f.unlink()
    with pytest.raises(osh.OshError, match="openwire/hdl/owr_core.vhd is missing or differs"):
        osh.add_core(FakeVUnit(), "openwire")


def test_a_changed_compile_order_is_a_damaged_installation(inst):
    (inst.hdl / "openwire" / "compile_order.txt").write_text("hdl/owr_core.vhd\n", encoding="utf-8")
    with pytest.raises(osh.OshError, match="openwire/compile_order.txt"):
        osh.add_core(FakeVUnit(), "openwire")


def test_add_uvvm(inst):
    vu = FakeVUnit()
    libs = osh.add_uvvm(vu)
    assert sorted(libs) == ["bitvis_vip_axilite", "uvvm_util"]
    assert rel(inst, libs["bitvis_vip_axilite"].files) == [
        "uvvm/bitvis_vip_axilite/src/axilite_bfm_pkg.vhd",
        "uvvm/uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd"]
    assert rel(inst, libs["uvvm_util"].files) == ["uvvm/uvvm_util/src/types_pkg.vhd"]
    for lib in libs.values():
        assert lib.options == [("ghdl.a_flags", RELAXED)]
    assert osh.add_uvvm(vu)["uvvm_util"] is libs["uvvm_util"]


def test_add_uvvm_with_a_foreign_library(inst):
    with pytest.raises(osh.LibraryConflictError, match="uvvm_util"):
        osh.add_uvvm(FakeVUnit("uvvm_util"))


def test_add_osh_tb_adds_uvvm_the_cores_of_the_far_ends_and_the_bench(inst):
    vu = FakeVUnit()
    lib = osh.add_osh_tb(vu)
    assert lib is vu.libs["osh_tb"]
    assert sorted(vu.libs) == ["bitvis_vip_axilite", "olo", "openfibre", "openrmap", "openspp", "openwire", "osh_tb",
                               "uvvm_util"]
    assert [Path(f).name for f in lib.files] == list(vunit.OSH_TB_FILES)
    assert all(Path(f).is_file() for f in lib.files)
    assert lib.options == [("ghdl.a_flags", RELAXED)]
    # OpenFibre with the model of its adapter, which the SpaceFibre far end instantiates
    assert rel(inst, vu.libs["openfibre"].files)[-1] == "openfibre/hdl/ofb_pa_gty/src/ofb_pa_gty.vhd"
    assert osh.add_osh_tb(vu) is lib


def test_add_osh_tb_uses_a_core_added_before(inst):
    vu = FakeVUnit()
    ow = osh.add_core(vu, "openwire")
    osh.add_osh_tb(vu)
    assert vu.libs["openwire"] is ow and len(ow.files) == 2


def test_add_osh_tb_with_a_foreign_library(inst):
    with pytest.raises(osh.LibraryConflictError, match="library osh_tb"):
        osh.add_osh_tb(FakeVUnit("osh_tb"))


def test_the_bench_components_are_the_files_of_osh_tb():
    assert sorted(f.name for f in vunit.OSH_TB_DIR.glob("*.vhd")) == sorted(vunit.OSH_TB_FILES)


def test_without_a_manifest(monkeypatch):
    with pytest.raises(osh.LockError, match="carries no lock manifest"):
        osh.add_core(FakeVUnit(), "openwire")
