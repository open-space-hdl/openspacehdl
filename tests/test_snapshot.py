"""Tests of the snapshot selection and of the licence and path rules (tools/snapshot.py), on in-memory trees."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LICENSES = ROOT / "src" / "openspacehdl" / "licenses"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


snapshot = load("snapshot")
PSI = (LICENSES / "PSI-HDL-1.0.txt").read_bytes()
LGPL = (LICENSES / "LGPL-2.1.txt").read_bytes()
APACHE = (LICENSES / "Apache-2.0.txt").read_bytes()
MIT_FIX = (LICENSES / "MIT-en_cl_fix.md").read_bytes()
EXPRESSION = "MIT AND LicenseRef-PSI-HDL-1.0 AND Apache-2.0"
LICENSE_FILES = ["LICENSE", "src/openspacehdl/licenses/*.txt", "src/openspacehdl/licenses/*.md"]


def core_tree(**extra):
    files = {
        "License.txt": PSI, "LGPL2_1.txt": LGPL, "README.md": b"core\n",
        "compile_order.txt": b"# order\nhdl/x_pkg/src/x_pkg.vhd\nhdl/x_core/src/x_core.vhd  # top\n",
        "hdl/x_pkg/src/x_pkg.vhd": b"pkg", "hdl/x_core/src/x_core.vhd": b"core",
        "hdl/x_core/tb/x_core_tb.vhd": b"tb",
        "hdl/x_pa/compile_order_sim.txt": b"tb/x_tb_pkg.vhd\nhdl/x_pa/sim/m.vhd\n",
        "tb/x_tb_pkg.vhd": b"tbpkg", "hdl/x_pa/sim/m.vhd": b"model", "hdl/x_pa/src/x_pa.vhd": b"vendor",
        "sw/x_regs.h": b"#define X 1\n", "sw/sub/y.h": b"", "tools/run.py": b"",
    }
    files.update(extra)
    return snapshot.Tree(files)


def test_core_selection():
    assert snapshot.select("core", core_tree()) == [
        "LGPL2_1.txt", "License.txt", "compile_order.txt", "hdl/x_core/src/x_core.vhd",
        "hdl/x_pa/compile_order_sim.txt", "hdl/x_pa/sim/m.vhd", "hdl/x_pkg/src/x_pkg.vhd", "sw/x_regs.h",
        "tb/x_tb_pkg.vhd",
    ]


def test_a_listed_file_that_does_not_exist():
    tree = core_tree(**{"compile_order.txt": b"hdl/missing.vhd\n"})
    with pytest.raises(snapshot.InputError, match="hdl/missing.vhd"):
        snapshot.select("core", tree)


def test_only_the_files_format_is_supported():
    with pytest.raises(snapshot.InputError, match="modules"):
        snapshot.select("core", core_tree(), file_list_format="modules")


def test_open_logic_with_the_licence_of_its_submodule():
    tree = snapshot.Tree({"License.txt": PSI, "LGPL2_1.txt": LGPL, "compile_order.txt":
                          b"src/a.vhd\n3rdParty/en_cl_fix/hdl/fix_pkg.vhd\n", "src/a.vhd": b"a",
                          "3rdParty/en_cl_fix/hdl/fix_pkg.vhd": b"fix", "3rdParty/en_cl_fix/LICENSE.md": MIT_FIX,
                          "3rdParty/en_cl_fix/README.md": b"", "doc/a.png": b"png"})
    assert snapshot.select("olo", tree) == ["3rdParty/en_cl_fix/LICENSE.md", "3rdParty/en_cl_fix/hdl/fix_pkg.vhd",
                                            "LGPL2_1.txt", "License.txt", "compile_order.txt", "src/a.vhd"]


def test_reference_systems_selection():
    tree = snapshot.Tree({"License.txt": PSI, "LGPL2_1.txt": LGPL, "systems/s/s.composer.json": b"{}",
                          "sim/tb/rs_far_end.vhd": b"", "sim/README.md": b"", "tools/ghdl.py": b"",
                          "docs/x.md": b"", ".github/workflows/ci.yml": b""})
    assert snapshot.select("refsys", tree) == ["LGPL2_1.txt", "License.txt", "sim/tb/rs_far_end.vhd",
                                               "systems/s/s.composer.json", "tools/ghdl.py"]


def uvvm_tree(**extra):
    files = {"LICENSE": APACHE, "uvvm_util/doc/a.pdf": b"", "bitvis_vip_spi/src/c.vhd": b""}
    for c in snapshot.UVVM_COMPONENTS:
        files[f"{c}/script/compile_order.txt"] = f"# library {c}\n../src/{c}_pkg.vhd\n".encode()
        files[f"{c}/src/{c}_pkg.vhd"] = b""
    files["bitvis_vip_axilite/script/compile_order.txt"] = (
        b"# library bitvis_vip_axilite\n../src/axilite_bfm_pkg.vhd\n"
        b"../../uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd\n")
    files["bitvis_vip_axilite/src/axilite_bfm_pkg.vhd"] = b""
    files["uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd"] = b""
    files["uvvm_vvc_framework/src_target_dependent/td_unused.vhd"] = b""
    files.update(extra)
    return snapshot.Tree(files)


def test_uvvm_selection_follows_the_compile_orders():
    sel = snapshot.select("uvvm", uvvm_tree())
    assert "uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd" in sel
    assert "uvvm_vvc_framework/src_target_dependent/td_unused.vhd" not in sel
    assert "bitvis_vip_axilite/src/bitvis_vip_axilite_pkg.vhd" not in sel
    assert "bitvis_vip_spi/src/c.vhd" not in sel and "uvvm_util/doc/a.pdf" not in sel
    assert "LICENSE" in sel and "uvvm_util/script/compile_order.txt" in sel
    assert snapshot.uvvm_order(uvvm_tree(), "bitvis_vip_axilite") == [
        "bitvis_vip_axilite/src/axilite_bfm_pkg.vhd", "uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd"]


def test_uvvm_without_a_compile_order():
    tree = uvvm_tree()
    files = {p: tree.read(p) for p in tree.paths() if p != "uvvm_util/script/compile_order.txt"}
    with pytest.raises(snapshot.InputError, match="no uvvm_util/script/compile_order.txt"):
        snapshot.select("uvvm", snapshot.Tree(files))


def test_uvvm_compile_order_with_a_missing_file():
    tree = uvvm_tree(**{"uvvm_util/script/compile_order.txt": b"../src/missing.vhd\n"})
    with pytest.raises(snapshot.InputError, match="uvvm_util/src/missing.vhd"):
        snapshot.select("uvvm", tree)


def files_of(**trees):
    return {d: snapshot.hashes(kind, tree) for d, (kind, tree) in trees.items()}


def test_licences_of_a_complete_snapshot():
    files = files_of(x=("core", core_tree()), uvvm=("uvvm", uvvm_tree()))
    assert snapshot.check_licenses(files, EXPRESSION, LICENSE_FILES) == {"LicenseRef-PSI-HDL-1.0", "Apache-2.0"}


def test_a_snapshot_without_licence_file():
    tree = snapshot.Tree({"compile_order.txt": b"a.vhd\n", "a.vhd": b""})
    with pytest.raises(snapshot.SnapshotError, match="L7: x: the snapshot has no licence file"):
        snapshot.check_licenses(files_of(x=("core", tree)), EXPRESSION, LICENSE_FILES)


def test_a_licence_file_with_another_text():
    files = files_of(x=("core", core_tree(**{"License.txt": PSI + b"changed\n"})))
    with pytest.raises(snapshot.SnapshotError, match="L7: x/License.txt differs"):
        snapshot.check_licenses(files, EXPRESSION, LICENSE_FILES)


def test_an_expression_that_misses_a_licence():
    files = files_of(uvvm=("uvvm", uvvm_tree()))
    with pytest.raises(snapshot.SnapshotError, match="does not name Apache-2.0"):
        snapshot.check_licenses(files, "MIT AND LicenseRef-PSI-HDL-1.0", LICENSE_FILES)


def test_licence_files_that_miss_a_text():
    with pytest.raises(snapshot.SnapshotError, match="MIT-en_cl_fix.md"):
        snapshot.check_licenses({}, EXPRESSION, ["LICENSE", "src/openspacehdl/licenses/*.txt"])


def test_path_budget():
    project = {"tool": {"openspacehdl": {"path-limit": 260, "install-prefix": 120}}}
    assert snapshot.path_budget(project) == 139
    assert snapshot.path_budget({}) == 139
    assert snapshot.check_paths(["a" * 139, "b"], 139) == 139
    with pytest.raises(snapshot.SnapshotError, match="L8: .* has 140 characters, the budget is 139"):
        snapshot.check_paths(["a" * 140], 139)


def test_list_file_ignores_comments_and_blank_lines():
    tree = snapshot.Tree({"l.txt": b"# head\n\n a.vhd \nb.vhd # note\n#c.vhd\n"})
    assert snapshot.list_file(tree, "l.txt") == ["a.vhd", "b.vhd"]
