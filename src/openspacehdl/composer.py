"""Reads and checks a saved system of the Open Space Composer and its export (docs/design.md, section 6.1).

A system file (<system>.composer.json) is accepted only when

- it is valid against the published schema of its formatVersion (system-1 or system-2, at the website commit of the
  lock manifest);
- it has its resolved netlist, without problems, and no check of severity error (the rule of Export HDL);
- the layout of the resolved netlist (resolved.version; a file without it has layout 1) is one the package knows;
- its export (the HDL files of Export HDL) belongs to it: the header of <entity>_compile_order.txt names the SHA-256
  of the file;
- every source of its compile order has the commit (Open Logic FT: the tag) of the lock manifest;
- every external interface has a type the generator has a bench component for.

A generator version the package was not tested with gives a warning, not a refusal.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from openspacehdl import jsonschema
from openspacehdl.errors import OshError

KNOWN_LAYOUTS = (1,)
TESTED_GENERATORS = ("0.9.7-beta", "0.9.8-beta", "0.9.9-beta", "0.9.10-beta", "0.9.11-beta", "0.9.12-beta")
# (type, role) of the external interfaces the generated testbench supports; every stream type is supported as a
# sink or a source (docs/design.md, section 6.3)
BUS_AND_PIN_TYPES = {("axi4lite", "slave"), ("axi4", "master"), ("axi4", "slave"), ("spw.ds", "pins"),
                     ("spfi.serial", "pins")}
STREAM_ROLES = ("sink", "source")


class ComposerError(OshError):
    """The system file or its export is refused; reasons lists every reason."""

    def __init__(self, path: Path, reasons: list[str]):
        self.reasons = reasons
        super().__init__(f"{path.name} is refused:\n" + "\n".join(f"  - {r}" for r in reasons))


@dataclass(frozen=True)
class Port:
    name: str
    dir: str
    type: str
    kind: str
    domain: str | None = None
    signal: str | None = None


@dataclass(frozen=True)
class Interface:
    """An external interface of the system: an endpoint of an instance, with its type, role and ports."""

    endpoint: str
    instance: str
    name: str
    block: str
    type: str
    kind: str
    role: str
    ports: tuple[Port, ...]


@dataclass(frozen=True)
class System:
    path: Path
    hdl: Path
    entity: str
    data: dict
    layout: int
    generator: str
    clocks: tuple[Port, ...]
    resets: tuple[Port, ...]
    interfaces: tuple[Interface, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def schema(format_version: int, directory: Path | None = None) -> dict:
    """The published schema of a format version, from the package (data/schema/) or from directory."""
    name = f"system-{format_version}.json"
    f = (directory / name) if directory else resources.files("openspacehdl").joinpath(f"data/schema/{name}")
    if not f.is_file():
        raise OshError(f"the package carries no schema {name}")
    return json.loads(f.read_text(encoding="utf-8"))


def _export_dir(path: Path, hdl: Path | None, entity: str) -> Path | None:
    name = f"{entity}_compile_order.txt"
    for candidate in ([hdl] if hdl else [path.parent / "hdl", path.parent]):
        if candidate is not None and (candidate / name).is_file():
            return candidate
    return None


def _interfaces(data: dict, reasons: list[str]) -> list[Interface]:
    r = data["resolved"]
    blocks = {b["id"]: b for b in data.get("catalogSubset", {}).get("blocks", [])}
    types = {t["id"]: t for t in data.get("catalogSubset", {}).get("types", [])}
    instances = {i["id"]: i for i in r.get("instances", [])}
    groups: dict[str, list[dict]] = {}
    for p in r["ports"]:
        if p["kind"] == "interface":
            groups.setdefault(p["interface"], []).append(p)
    out = []
    for endpoint, ports in groups.items():
        inst_id, rest = endpoint.split(".", 1)
        name = re.sub(r"\[\d+\]$", "", rest)
        block_id = instances.get(inst_id, {}).get("block")
        spec = next((i for i in blocks.get(block_id, {}).get("interfaces", []) if i.get("name") == name), None)
        if spec is None:
            reasons.append(f"the interface {endpoint} has no description in catalogSubset")
            continue
        type_id, role = spec.get("type"), spec.get("role")
        kind = types.get(type_id, {}).get("kind")
        supported = (type_id, role) in BUS_AND_PIN_TYPES or (kind == "stream" and role in STREAM_ROLES)
        if not supported:
            reasons.append(f"the interface {endpoint} has the type {type_id} ({role}), which the generated testbench "
                           f"does not support")
            continue
        out.append(Interface(endpoint, inst_id, name, block_id, type_id, kind, role,
                             tuple(_port(p) for p in ports)))
    return out


def _port(p: dict) -> Port:
    return Port(p["name"], p["dir"], p["type"], p["kind"], p.get("domain"), p.get("signal"))


def _check_pins(data: dict, lock, reasons: list[str]) -> None:
    cores = {c.library: c for c in lock.cores}
    for c in data["resolved"].get("compile", []):
        lib = c.get("library")
        if lib == lock.olo_library:
            if c.get("tag") != lock.olo_tag or c.get("commit") not in (None, lock.olo_commit):
                reasons.append(f"the system uses Open Logic FT {c.get('tag')} ({str(c.get('commit'))[:7]}); this "
                               f"package carries {lock.olo_tag} ({lock.olo_commit[:7]})")
        elif lib in cores:
            core = cores[lib]
            if c.get("commit") != core.commit:
                reasons.append(f"the system uses {core.name} at {str(c.get('commit'))[:7]}; this package carries "
                               f"{core.tag} ({core.commit[:7]})")
        elif lib != data["resolved"].get("entity"):
            reasons.append(f"the system uses the library {lib}, which this package does not carry")


def load(path: Path, *, hdl: Path | None = None, lock=None, schema_dir: Path | None = None) -> System:
    """The checked system of a .composer.json file; raises ComposerError with every reason of a refusal.

    hdl: the directory of the export (default: hdl/ next to the file, else the directory of the file). lock: the
    lock manifest whose pins the system must use (default: that of the installed package)."""
    path = Path(path)
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ComposerError(path, [f"not a JSON file: {e}"]) from None
    reasons: list[str] = []
    warnings: list[str] = []
    version = data.get("formatVersion") if isinstance(data, dict) else None
    if version not in (1, 2):
        raise ComposerError(path, [f"unknown formatVersion {version!r}; the package reads 1 and 2"])
    reasons += [f"schema system-{version}: {e}" for e in jsonschema.validate(data, schema(version, schema_dir))]
    r = data.get("resolved")
    if r is None:
        reasons.append("the file has no resolved netlist; save the system in the Composer")
        raise ComposerError(path, reasons)
    if r.get("problems"):
        reasons += [f"resolved problem: {p}" for p in r["problems"]]
    errors = [c for c in data.get("checks", []) if c.get("severity") == "error"]
    reasons += [f"check {c.get('rule')}: {c.get('message')}" for c in errors]
    layout = r.get("version", 1)
    if layout not in KNOWN_LAYOUTS:
        reasons.append(f"the resolved netlist has layout {layout}; this package knows {KNOWN_LAYOUTS}")
    generator = data.get("generator", {}).get("version", "")
    if generator not in TESTED_GENERATORS:
        warnings.append(f"the file was written by Composer generator {generator}; this package was tested with "
                        f"{', '.join(TESTED_GENERATORS)}")
    entity = r.get("entity", "")
    export = _export_dir(path, hdl, entity)
    if export is None:
        reasons.append(f"no export of the system: {entity}_compile_order.txt is neither in "
                       f"{hdl or path.parent / 'hdl'} nor next to the file; use Export HDL of the Composer")
    else:
        header = (export / f"{entity}_compile_order.txt").read_text(encoding="utf-8")
        m = re.search(r"^# SHA-256 of .*: ([0-9a-f]{64})$", header, re.MULTILINE)
        digest = hashlib.sha256(raw).hexdigest()
        if m is None or m.group(1) != digest:
            reasons.append(f"the export in {export} belongs to another state of the file (SHA-256 "
                           f"{m.group(1)[:12] if m else 'missing'}, the file has {digest[:12]}); export it again")
    if lock is None:
        from openspacehdl.lock import load as load_lock

        lock = load_lock()
    _check_pins(data, lock, reasons)
    interfaces = _interfaces(data, reasons)
    if reasons:
        raise ComposerError(path, reasons)
    ports = [_port(p) for p in r["ports"]]
    return System(path, export, entity, data, layout, generator,
                  tuple(p for p in ports if p.kind == "clock"), tuple(p for p in ports if p.kind == "reset"),
                  tuple(interfaces), tuple(warnings))
