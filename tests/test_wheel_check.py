"""Tests of tools/wheel_check.py (rules L6 to L9) on small synthetic wheels."""

import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LICENSES = ROOT / "src" / "openspacehdl" / "licenses"
sys.path.insert(0, str(ROOT / "tools"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wheel_check = load("wheel_check")
PROJECT = {"tool": {"openspacehdl": {"path-limit": 260, "install-prefix": 120, "pypi-file-limit-mb": 100}}}
DIST = "openspacehdl-0.1.0.dist-info"
TEXTS = ["PSI-HDL-1.0.txt", "LGPL-2.1.txt", "Apache-2.0.txt", "MIT-en_cl_fix.md"]
SCHEMAS = {"system-1.json": b'{"$id": "1"}\n', "system-2.json": b'{"$id": "2"}\n'}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def snapshot_files() -> dict[str, dict[str, bytes]]:
    psi, lgpl = (LICENSES / "PSI-HDL-1.0.txt").read_bytes(), (LICENSES / "LGPL-2.1.txt").read_bytes()
    return {
        "openwire": {"License.txt": psi, "LGPL2_1.txt": lgpl, "compile_order.txt": b"hdl/a.vhd\n", "hdl/a.vhd": b"a"},
        "uvvm": {"LICENSE": (LICENSES / "Apache-2.0.txt").read_bytes(), "uvvm_util/src/u.vhd": b"u"},
    }


def make_wheel(path: Path, *, files=None, lock_files=None, expression="MIT AND LicenseRef-PSI-HDL-1.0 AND Apache-2.0",
               license_files=None, extra=None, waived=None, with_lock=True, bundles=None, schemas=None,
               lock_schemas=None) -> Path:
    files = snapshot_files() if files is None else files
    schemas = (SCHEMAS if with_lock else {}) if schemas is None else schemas
    lock = {"format": "openspacehdl-lock", "version": 1,
            "website": {"schemas": lock_schemas if lock_schemas is not None else
                        {n: sha(b) for n, b in schemas.items()}},
            "files": lock_files if lock_files is not None else
            {d: {p: sha(b) for p, b in e.items()} for d, e in files.items()}}
    if waived:
        lock["waived"] = waived
    bundle_files = {}
    for bid, (spec, data) in (bundles or {}).items():
        lock.setdefault("bundles", {})[bid] = spec
        if data is not None:
            bundle_files[f"openspacehdl/bundles/{bid}.bundle"] = data
    license_files = license_files if license_files is not None else \
        ["LICENSE"] + [f"src/openspacehdl/licenses/{n}" for n in TEXTS]
    meta = "Metadata-Version: 2.4\nName: openspacehdl\nVersion: 0.1.0\n"
    meta += f"License-Expression: {expression}\n" + "".join(f"License-File: {lf}\n" for lf in license_files)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("openspacehdl/__init__.py", "")
        if with_lock:
            z.writestr("openspacehdl/data/lock.json", json.dumps(lock))
        for d, entries in files.items():
            for p, b in entries.items():
                z.writestr(f"openspacehdl/hdl/{d}/{p}", b)
        for n, b in schemas.items():
            z.writestr(f"openspacehdl/data/schema/{n}", b)
        z.writestr(f"{DIST}/METADATA", meta)
        for lf in license_files:
            src = ROOT / lf
            z.writestr(f"{DIST}/licenses/{lf}", src.read_bytes() if src.exists() else b"")
        for name, b in {**bundle_files, **(extra or {})}.items():
            z.writestr(name, b)
    return path


def test_a_good_wheel(tmp_path):
    assert wheel_check.check(make_wheel(tmp_path / "w.whl"), PROJECT) == []


def test_a_wheel_without_snapshots(tmp_path):
    assert wheel_check.check(make_wheel(tmp_path / "w.whl", files={}, with_lock=False), PROJECT) == []


def test_l6_a_changed_file(tmp_path):
    files = snapshot_files()
    lock_files = {d: {p: sha(b) for p, b in e.items()} for d, e in files.items()}
    files["openwire"]["hdl/a.vhd"] = b"changed"
    v = wheel_check.check(make_wheel(tmp_path / "w.whl", files=files, lock_files=lock_files), PROJECT)
    assert v == ["L6: openspacehdl/hdl/openwire/hdl/a.vhd: the hash differs from the manifest"]


def test_l6_a_missing_and_an_extra_file(tmp_path):
    files = snapshot_files()
    lock_files = {d: {p: sha(b) for p, b in e.items()} for d, e in files.items()}
    del files["openwire"]["hdl/a.vhd"]
    files["openwire"]["hdl/b.vhd"] = b"b"
    v = wheel_check.check(make_wheel(tmp_path / "w.whl", files=files, lock_files=lock_files), PROJECT)
    assert v == ["L6: openspacehdl/hdl/openwire/hdl/a.vhd is missing",
                 "L6: openspacehdl/hdl/openwire/hdl/b.vhd is not in the manifest"]


def test_l6_a_waived_manifest(tmp_path):
    w = make_wheel(tmp_path / "w.whl", waived=["L2", "L4"])
    assert wheel_check.check(w, PROJECT) == ["L6: the manifest waives L2, L4; such a wheel is never released"]
    assert wheel_check.check(w, PROJECT, allow_waived=True) == []


def test_l6_a_changed_and_a_missing_schema(tmp_path):
    s1 = SCHEMAS["system-1.json"]
    w = make_wheel(tmp_path / "w.whl", schemas={"system-1.json": s1 + b" "},
                   lock_schemas={n: sha(b) for n, b in SCHEMAS.items()})
    assert wheel_check.check(w, PROJECT) == [
        "L6: openspacehdl/data/schema/system-1.json: the hash differs from the manifest",
        "L6: openspacehdl/data/schema/system-2.json is missing"]


def test_l6_an_extra_schema(tmp_path):
    w = make_wheel(tmp_path / "w.whl", schemas={**SCHEMAS, "system-3.json": b"{}"},
                   lock_schemas={n: sha(b) for n, b in SCHEMAS.items()})
    assert wheel_check.check(w, PROJECT) == ["L6: openspacehdl/data/schema/system-3.json is not in the manifest"]


def test_l6_a_manifest_without_schemas(tmp_path):
    w = make_wheel(tmp_path / "w.whl", schemas={})
    assert wheel_check.check(w, PROJECT) == ["L6: the manifest lists no Composer schemas"]


def test_l7_an_expression_without_apache(tmp_path):
    v = wheel_check.check(make_wheel(tmp_path / "w.whl", expression="MIT AND LicenseRef-PSI-HDL-1.0"), PROJECT)
    assert len(v) == 1 and v[0].startswith("L7:") and "Apache-2.0" in v[0]


def test_l7_a_licence_text_not_in_the_metadata(tmp_path):
    lf = ["LICENSE"] + [f"src/openspacehdl/licenses/{n}" for n in TEXTS[:3]]
    v = wheel_check.check(make_wheel(tmp_path / "w.whl", license_files=lf), PROJECT)
    assert len(v) == 1 and "MIT-en_cl_fix.md" in v[0]


def test_l7_a_licence_file_not_copied(tmp_path):
    w = make_wheel(tmp_path / "w.whl")
    with zipfile.ZipFile(w) as z:
        items = [(i, z.read(i)) for i in z.infolist() if not i.filename.endswith("licenses/LICENSE")]
    with zipfile.ZipFile(w, "w") as z:
        for info, data in items:
            z.writestr(info, data)
    assert wheel_check.check(w, PROJECT) == [f"L7: LICENSE is a License-File but not in {DIST}/licenses/"]


def test_l8_a_long_path(tmp_path):
    name = "openspacehdl/" + "x" * 140
    v = wheel_check.check(make_wheel(tmp_path / "w.whl", extra={name: b""}), PROJECT)
    assert v == [f"L8: {name} has {len(name)} characters, the budget is 139"]


def test_l9_the_size_limit(tmp_path):
    w = make_wheel(tmp_path / "w.whl")
    small = {"tool": {"openspacehdl": {**PROJECT["tool"]["openspacehdl"], "pypi-file-limit-mb": 0.001}}}
    v = wheel_check.check(w, small)
    assert len(v) == 1 and v[0].startswith("L9: the wheel has")


def test_main_reports_and_fails(tmp_path, capsys):
    w = make_wheel(tmp_path / "w.whl", expression="MIT")
    assert wheel_check.main([str(w)]) == 1
    out = capsys.readouterr().out
    assert "L7:" in out and "1 violation(s)" in out
    assert wheel_check.main([str(make_wheel(tmp_path / "ok.whl"))]) == 0


@pytest.mark.parametrize("n", [139])
def test_the_budget_of_the_repository(n):
    assert wheel_check.snapshot.path_budget(wheel_check.snapshot.pyproject()) == n


@pytest.fixture
def bundle(tmp_path):
    """A small bundle and its refs."""
    if shutil.which("git") is None:
        pytest.skip("needs git")
    from gitrepo import git, make_repo

    sha = make_repo(tmp_path / "r", {"a.vhd": "-- a\n"})
    git(tmp_path / "r", "tag", "v0.1.0")
    git(tmp_path / "r", "bundle", "create", "-q", str(tmp_path / "r.bundle"), "refs/heads/main", "refs/tags/v0.1.0")
    return {"branch": "main", "commit": sha, "url": "u", "refs": {"refs/heads/main": sha, "refs/tags/v0.1.0": sha}}, \
        (tmp_path / "r.bundle").read_bytes()


def test_l6_a_good_bundle(tmp_path, bundle):
    assert wheel_check.check(make_wheel(tmp_path / "w.whl", bundles={"openwire": bundle}), PROJECT) == []


def test_l6_a_bundle_with_other_refs(tmp_path, bundle):
    spec, data = bundle
    other = {**spec, "refs": {**spec["refs"], "refs/tags/v0.2.0": spec["commit"]}}
    v = wheel_check.check(make_wheel(tmp_path / "w.whl", bundles={"openwire": (other, data)}), PROJECT)
    assert v == ["L6: openspacehdl/bundles/openwire.bundle: the refs differ from the manifest"]


def test_l6_a_missing_and_an_extra_bundle(tmp_path, bundle):
    spec, data = bundle
    w = make_wheel(tmp_path / "w.whl", bundles={"openwire": (spec, None)},
                   extra={"openspacehdl/bundles/other.bundle": data})
    assert wheel_check.check(w, PROJECT) == ["L6: openspacehdl/bundles/openwire.bundle is missing",
                                             "L6: openspacehdl/bundles/other.bundle is not in the manifest"]
