"""Tests of openspacehdl.composer (reading and checking a system file and its export) and of openspacehdl.jsonschema."""

import copy
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from openspacehdl import composer, jsonschema, lock

FIX = Path(__file__).resolve().parent / "fixtures" / "composer"
SCHEMAS = FIX / "schema"
EXAMPLE = FIX / "spw_rmap_node" / "spw_rmap_node.composer.json"
DATA = json.loads(EXAMPLE.read_text(encoding="utf-8"))
# formatVersion 3: a system with a reset group (Composer 0.10.0-beta)
V3 = FIX / "spw_compression_node_pipeline_reset" / "spw_compression_node_pipeline_reset.composer.json"
DATA3 = json.loads(V3.read_text(encoding="utf-8"))


def lock_for(data=DATA, **change):
    """A lock manifest with the pins of the system (cores by library), changed by change: library -> commit."""
    cores, olo = [], None
    for c in data["resolved"]["compile"]:
        if c["library"] == "olo":
            olo = c
        elif c["library"] != data["resolved"]["entity"]:
            cores.append({"id": c["library"], "name": c["library"].title(), "repository": f"x/{c['library']}",
                          "tag": "v0.1.0", "commit": change.get(c["library"], c["commit"]), "library": c["library"],
                          "fileList": "compile_order.txt", "fileListFormat": "files", "models": {}})
    return lock.Lock.from_dict({
        "format": "openspacehdl-lock", "version": 1, "package": "0.1.0",
        "website": {"commit": "7" * 40, "catalog": "x", "generator": "0.9.8-beta"},
        "referenceSystems": {"tag": "v0.1.1", "commit": "4" * 40},
        "openLogic": {"tag": change.get("olo_tag", olo["tag"]), "commit": olo["commit"], "library": "olo",
                      "fileList": "compile_order.txt"},
        "uvvm": {"commit": "5" * 40}, "cores": [c for c in cores if c["library"] not in change.get("drop", ())],
    })


def load(path=EXAMPLE, **kw):
    return composer.load(path, lock=kw.pop("lock", None) or lock_for(), schema_dir=kw.pop("schema_dir", SCHEMAS), **kw)


def variant(tmp_path, mutate, keep_sha=False, source=EXAMPLE):
    """A copy of source with mutate applied, and its export; the header names the new SHA-256 unless keep_sha."""
    data = json.loads(source.read_text(encoding="utf-8"))
    mutate(data)
    target = tmp_path / source.name
    target.write_text(json.dumps(data, indent=1), encoding="utf-8")
    shutil.copytree(source.parent / "hdl", tmp_path / "hdl")
    if not keep_sha:
        order = tmp_path / "hdl" / f"{source.name.removesuffix('.composer.json')}_compile_order.txt"
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        text = re.sub(r"(# SHA-256 of .*: )[0-9a-f]{64}", lambda m: m.group(1) + digest,
                      order.read_text(encoding="utf-8"))
        order.write_text(text, encoding="utf-8", newline="\n")
    return target


def reasons(path, **kw):
    with pytest.raises(composer.ComposerError) as e:
        load(path, **kw)
    return e.value.reasons


def test_the_example_is_accepted():
    s = load()
    assert s.entity == "spw_rmap_node" and s.layout == 1 and s.generator == "0.9.9-beta"
    assert s.hdl == EXAMPLE.parent / "hdl" and s.warnings == ()
    assert len(s.clocks) == 2 and len(s.resets) == 1
    found = {(i.endpoint, i.type, i.role) for i in s.interfaces}
    assert found == {("spw0.S_AxiLite", "axi4lite", "slave"), ("rmap0.S_AxiLite", "axi4lite", "slave"),
                     ("rmap0.M_Axi", "axi4", "master"), ("spw0.Spw", "spw.ds", "pins")}
    axi = next(i for i in s.interfaces if i.endpoint == "rmap0.M_Axi")
    assert axi.block == "openrmap/omap_core" and axi.kind == "bus" and len(axi.ports) > 10
    assert s.reset_groups == ()


def test_the_export_next_to_the_file(tmp_path):
    target = variant(tmp_path, lambda d: None)
    for f in (tmp_path / "hdl").iterdir():
        shutil.move(str(f), tmp_path / f.name)
    (tmp_path / "hdl").rmdir()
    assert load(target).hdl == tmp_path


def test_an_explicit_export_directory(tmp_path):
    target = tmp_path / "s.composer.json"
    shutil.copy(EXAMPLE, target)
    assert load(target, hdl=EXAMPLE.parent / "hdl").hdl == EXAMPLE.parent / "hdl"


def test_not_json(tmp_path):
    f = tmp_path / "x.composer.json"
    f.write_text("{ not json", encoding="utf-8")
    assert reasons(f)[0].startswith("not a JSON file")


@pytest.mark.parametrize("version", [0, 4, 5, "3", None])
def test_an_unknown_format_version(tmp_path, version):
    assert reasons(variant(tmp_path, lambda d: d.update(formatVersion=version))) == [
        f"unknown formatVersion {version!r}; the package reads 1, 2 and 3"]


# formatVersion 3: reset groups

def load3(path=V3, **kw):
    return load(path, lock=kw.pop("lock", None) or lock_for(DATA3), **kw)


def reasons3(path, **kw):
    with pytest.raises(composer.ComposerError) as e:
        load3(path, **kw)
    return e.value.reasons


def test_a_version_3_file_is_accepted():
    s = load3()
    assert s.entity == "spw_compression_node_pipeline_reset" and s.layout == 1 and s.generator == "0.10.0-beta"
    assert s.hdl == V3.parent / "hdl"
    assert s.reset_groups == (composer.ResetGroup(
        "pipe", "prst0.RstOut", ("och0", "frm0", "ocr0"), "prst0_RstOut_s", "sys", ("och0.Rst", "frm0.Rst", "ocr0.Rst")),)
    assert ("prst0.S_AxiLite", "axi4lite", "slave") in {(i.endpoint, i.type, i.role) for i in s.interfaces}


def test_a_version_3_file_without_a_reset_group(tmp_path):
    assert reasons3(variant(tmp_path, lambda d: d.pop("resetGroups"), source=V3)) == [
        "schema system-3: (root): the key 'resetGroups' is missing",
        "the resolved netlist has the reset group pipe, which the system does not define; save the system in the "
        "Composer"]


def test_reset_groups_in_a_version_2_file(tmp_path):
    r = reasons3(variant(tmp_path, lambda d: d.update(formatVersion=2), source=V3))
    assert "schema system-2: (root): unknown key 'resetGroups'" in r


def test_a_member_named_twice(tmp_path):
    def mutate(d):
        d["resetGroups"][0]["members"].append("och0")
    assert reasons3(variant(tmp_path, mutate, source=V3)) == [
        "schema system-3: resetGroups[0].members: item 3 repeats an earlier item"]


def test_a_reset_group_missing_in_the_resolved_netlist(tmp_path):
    assert reasons3(variant(tmp_path, lambda d: d["resolved"].pop("resetGroups"), source=V3)) == [
        "the reset group pipe (prst0.RstOut) is not in the resolved netlist with this source; save the system in the "
        "Composer"]


def test_a_reset_group_with_another_source_in_the_resolved_netlist(tmp_path):
    def mutate(d):
        d["resolved"]["resetGroups"][0]["source"] = "edac0.RstOut"
    assert reasons3(variant(tmp_path, mutate, source=V3)) == [
        "the reset group pipe (prst0.RstOut) is not in the resolved netlist with this source; save the system in the "
        "Composer"]


def test_a_reset_group_only_in_the_resolved_netlist(tmp_path):
    def mutate(d):
        d["resolved"]["resetGroups"].append({**d["resolved"]["resetGroups"][0], "group": "other"})
    assert reasons3(variant(tmp_path, mutate, source=V3)) == [
        "the resolved netlist has the reset group other, which the system does not define; save the system in the "
        "Composer"]


def test_a_package_without_the_schema_of_version_3(tmp_path):
    schemas = tmp_path / "schema"
    schemas.mkdir()
    for n in ("system-1.json", "system-2.json"):
        shutil.copy(SCHEMAS / n, schemas / n)
    assert reasons3(V3, schema_dir=schemas) == [
        "formatVersion 3 needs the schema system-3.json, which this package does not carry (the website commit of its "
        "lock manifest predates it)"]
    assert load(schema_dir=schemas).entity == "spw_rmap_node"


def test_a_schema_violation(tmp_path):
    r = reasons(variant(tmp_path, lambda d: d["system"].pop("name")))
    assert r == ["schema system-1: system: the key 'name' is missing"]


def test_no_resolved_netlist(tmp_path):
    r = reasons(variant(tmp_path, lambda d: d.pop("resolved")))
    assert r[-1] == "the file has no resolved netlist; save the system in the Composer"


def test_resolved_problems(tmp_path):
    assert "resolved problem: a port without a driver" in reasons(
        variant(tmp_path, lambda d: d["resolved"]["problems"].append("a port without a driver")))


def test_a_check_of_severity_error(tmp_path):
    def mutate(d):
        d["checks"].append({"severity": "error", "rule": "width", "message": "widths differ"})
    assert "check width: widths differ" in reasons(variant(tmp_path, mutate))


def test_an_unknown_layout(tmp_path):
    r = reasons(variant(tmp_path, lambda d: d["resolved"].update(version=2)))
    assert "the resolved netlist has layout 2; this package knows (1,)" in r


def test_a_file_without_resolved_version_has_layout_1(tmp_path):
    assert load(variant(tmp_path, lambda d: d["resolved"].pop("version"))).layout == 1


def test_an_untested_generator_is_a_warning(tmp_path):
    s = load(variant(tmp_path, lambda d: d["generator"].update(version="0.9.13-beta")))
    assert s.warnings == ("the file was written by Composer generator 0.9.13-beta; this package was tested with "
                          "0.9.7-beta, 0.9.8-beta, 0.9.9-beta, 0.9.10-beta, 0.9.11-beta, 0.9.12-beta",)


def test_no_export(tmp_path):
    target = tmp_path / "s.composer.json"
    shutil.copy(EXAMPLE, target)
    assert any(r.startswith("no export of the system") for r in reasons(target))


def test_an_export_of_another_state(tmp_path):
    target = variant(tmp_path, lambda d: d["system"].update(description="changed"), keep_sha=True)
    assert any("belongs to another state of the file" in r for r in reasons(target))


def test_a_core_at_another_commit():
    r = reasons(EXAMPLE, lock=lock_for(openwire="a" * 40))
    assert len(r) == 1 and r[0].startswith("the system uses Openwire at 09e4b1f; this package carries v0.1.0 (aaaaaaa)")


def test_another_open_logic():
    r = reasons(EXAMPLE, lock=lock_for(olo_tag="4.7.0-ft.99"))
    assert len(r) == 1 and r[0].startswith("the system uses Open Logic FT 4.7.0-ft.")


def test_a_library_the_package_does_not_carry():
    assert reasons(EXAMPLE, lock=lock_for(drop=("openrmap",))) == [
        "the system uses the library openrmap, which this package does not carry"]


def test_an_unsupported_interface_type(tmp_path):
    def mutate(d):
        block = next(b for b in d["catalogSubset"]["blocks"] if b["id"] == "openwire/owr_core")
        next(i for i in block["interfaces"] if i["name"] == "Spw")["role"] = "slave"
    r = reasons(variant(tmp_path, mutate))
    assert r == ["the interface spw0.Spw has the type spw.ds (slave), which the generated testbench does not support"]


# The validator against the reference implementation (the package jsonschema, a development dependency)

def _variants():
    yield "example", lambda d: None
    yield "missing key", lambda d: d["system"].pop("name")
    yield "wrong enum", lambda d: d["resolved"]["ports"][0].update(kind="nonsense")
    yield "unknown key", lambda d: d.update(extra=1)
    yield "wrong type", lambda d: d.update(formatVersion="1")
    yield "wrong const", lambda d: d.update(format="other")
    yield "bool for integer", lambda d: d["resolved"].update(version=True)


def _variants3():
    yield "example", lambda d: None
    yield "no reset group", lambda d: d.update(resetGroups=[])
    yield "no member", lambda d: d["resetGroups"][0].update(members=[])
    yield "member twice", lambda d: d["resetGroups"][0]["members"].append("och0")
    yield "member instance.port", lambda d: d["resetGroups"][0]["members"].append("och0.Rst")
    yield "source without interface", lambda d: d["resetGroups"][0].update(source="prst0")
    yield "unknown key in a group", lambda d: d["resetGroups"][0].update(extra=1)
    yield "wrong const", lambda d: d.update(formatVersion=2)


@pytest.mark.parametrize("version, name, mutate", [(1, n, m) for n, m in _variants()]
                         + [(3, n, m) for n, m in _variants3()])
def test_the_validator_agrees_with_the_reference(version, name, mutate):
    ref = pytest.importorskip("jsonschema")
    schema = json.loads((SCHEMAS / f"system-{version}.json").read_text(encoding="utf-8"))
    data = copy.deepcopy(DATA if version == 1 else DATA3)
    mutate(data)
    ours = jsonschema.validate(data, schema)
    theirs = list(ref.Draft202012Validator(schema).iter_errors(data))
    assert bool(ours) == bool(theirs), (ours, [e.message for e in theirs][:3])


@pytest.mark.parametrize("schema, value, ok", [
    ({"type": ["string", "null"]}, None, True),
    ({"type": "integer"}, 1.5, False),
    ({"minimum": 2}, 1, False),
    ({"maximum": 2}, 3, False),
    ({"exclusiveMinimum": 0}, 0, False),
    ({"maxLength": 2}, "abc", False),
    ({"minItems": 1}, [], False),
    ({"uniqueItems": True}, ["a", "b"], True),
    ({"uniqueItems": True}, ["a", "b", "a"], False),
    ({"uniqueItems": True}, [1, 1.0], False),
    ({"uniqueItems": True}, [True, 1], True),
    ({"uniqueItems": True}, [{"a": [1], "b": 2}, {"b": 2, "a": [1]}], False),
    ({"uniqueItems": False}, [1, 1], True),
    ({"pattern": "^v[0-9]$"}, "v1", True),
    ({"pattern": "^v[0-9]$"}, "x", False),
    ({"propertyNames": {"pattern": "^[a-z]+$"}}, {"Ab": 1}, False),
    ({"additionalProperties": {"type": "integer"}}, {"a": "x"}, False),
    ({"oneOf": [{"type": "integer"}, {"minimum": 0}]}, 3, False),
    ({"oneOf": [{"type": "integer"}, {"type": "string"}]}, "s", True),
    ({"$defs": {"n": {"type": "integer"}}, "items": {"$ref": "#/$defs/n"}}, [1, "x"], False),
])
def test_the_keywords(schema, value, ok):
    assert (jsonschema.validate(value, schema) == []) == ok


def test_an_unsupported_keyword_is_an_error_of_the_schema():
    with pytest.raises(jsonschema.SchemaError, match="anyOf"):
        jsonschema.validate(1, {"anyOf": [{"type": "integer"}]})
