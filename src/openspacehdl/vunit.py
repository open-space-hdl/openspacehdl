"""VUnit integration: the cores, Open Logic FT and UVVM of this package version as VUnit libraries.

    from vunit import VUnit
    import openspacehdl as osh

    vu = VUnit.from_argv()
    vu.add_vhdl_builtins()
    osh.add_core(vu, "openfibre")   # adds the libraries olo and openfibre
    osh.add_core(vu, "openrmap")    # reuses olo
    osh.add_uvvm(vu)                # the UVVM components of the system testbenches
    vu.main()

The files come from the source snapshots installed with the package (docs/design.md, section 5). The module does not
import VUnit; it works with the VUnit object it is given (VUnit 4.7 and 5.0).
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from openspacehdl import lock as _lock
from openspacehdl.errors import OshError

# Analysis flags of GHDL for UVVM: it uses shared variables of non-protected types. A testbench that uses UVVM also
# needs -frelaxed at elaboration (VUnit sim option ghdl.elab_flags).
UVVM_GHDL_FLAGS = ("-frelaxed", "-Wno-hide", "-Wno-shared")
_MARK = "_openspacehdl_libraries"


class UnknownCoreError(OshError):
    """The core is not in the lock manifest of this package version."""


class LibraryConflictError(OshError):
    """The VUnit project already has a library of this name that openspacehdl did not add."""


class OpenLogicConflictError(OshError):
    """The VUnit project already has a library olo that openspacehdl did not add."""


@dataclass(frozen=True)
class Installed:
    """The lock manifest and the directory of the source snapshots of the installed package."""

    lock: _lock.Lock
    hdl: Path


def installed() -> Installed:
    return Installed(_lock.load(), Path(str(resources.files("openspacehdl").joinpath("hdl"))))


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def read_list(path: Path) -> list[str]:
    """The paths of a list file: one per line, # starts a comment."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _find(inst: Installed, name: str) -> _lock.Core:
    for c in inst.lock.cores:
        if _key(name) in (_key(c.id), _key(c.name)):
            return c
    from openspacehdl import __version__
    from openspacehdl.family import load as family

    available = ", ".join(c.id for c in inst.lock.cores)
    card = family().find(name)
    if card is not None and not card.public:
        raise UnknownCoreError(f"{card.name} is not released yet (Coming soon on openspacehdl.org); "
                               f"openspacehdl {__version__} has {available}")
    if card is not None:
        raise UnknownCoreError(f"{card.name} is not in openspacehdl {__version__}, whose Composer catalog has no "
                               f"release of it; this version has {available}")
    raise UnknownCoreError(f"no core {name!r} in openspacehdl {__version__}; this version has {available}")


def _marks(vu) -> dict[str, str]:
    """Library name -> what openspacehdl added it for, kept on the VUnit object."""
    marks = getattr(vu, _MARK, None)
    if marks is None:
        marks = {}
        setattr(vu, _MARK, marks)
    return marks


def _existing(vu) -> set[str]:
    return {lib.name for lib in vu.get_libraries("*", allow_empty=True)}


def _verified(inst: Installed, snapshot: str, paths: list[str]) -> list[Path]:
    """The installed files of these snapshot paths, each checked against the hash of the manifest."""
    entries = inst.lock.files.get(snapshot, {})
    out = []
    for p in paths:
        f = inst.hdl / snapshot / p
        expected = entries.get(p)
        if expected is None or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != expected:
            raise OshError(f"{snapshot}/{p} is missing or differs from the lock manifest: the installation of "
                           f"openspacehdl is damaged; install the package again")
        out.append(f)
    return out


def _add_library(vu, name: str, files: list[Path]):
    lib = vu.add_library(name, vhdl_standard="2008")
    for f in files:
        lib.add_source_file(str(f), vhdl_standard="2008")
    return lib


def _add_open_logic(vu, inst: Installed) -> None:
    marks = _marks(vu)
    name = inst.lock.olo_library
    if name in marks:
        return
    if name in _existing(vu):
        raise OpenLogicConflictError(f"the VUnit project already has a library {name} that openspacehdl did not add; "
                                     f"openspacehdl uses Open Logic FT {inst.lock.olo_tag} for every core and never "
                                     f"mixes two Open Logic versions in one project")
    paths = read_list(inst.hdl / "olo" / inst.lock.olo_file_list)
    _add_library(vu, name, _verified(inst, "olo", [inst.lock.olo_file_list] + paths)[1:])
    marks[name] = "olo"


def add_core(vu, core: str, *, models: bool = True):
    """Adds a core and, once, Open Logic FT to the VUnit project; returns the VUnit library of the core.

    The library takes the name from the lock manifest (for example openfibre) and the files of the core's compile
    order, VHDL-2008. With models, the simulation models of the core's vendor adapters are added as well (for
    OpenFibre the entity ofb_pa_gty with its behavioural architecture mdl), so that GHDL simulates the core without
    vendor libraries. Adding the same core again returns its library.
    """
    inst = installed()
    c = _find(inst, core)
    marks = _marks(vu)
    if c.library in marks:
        return vu.library(c.library)
    if c.library in _existing(vu):
        raise LibraryConflictError(f"the VUnit project already has a library {c.library} that openspacehdl did not "
                                   f"add")
    _add_open_logic(vu, inst)
    paths = [c.file_list] + read_list(inst.hdl / c.id / c.file_list)
    if models:
        for model_list in c.models.values():
            paths += [model_list] + [p for p in read_list(inst.hdl / c.id / model_list) if p not in paths]
    files = _verified(inst, c.id, paths)
    lists = {c.file_list, *c.models.values()}
    lib = _add_library(vu, c.library, [f for f, p in zip(files, paths) if p not in lists])
    marks[c.library] = c.id
    if c.verified_with and c.verified_with != inst.lock.olo_tag:
        print(f"openspacehdl: {c.name} {c.tag} was verified with Open Logic FT {c.verified_with}; this package uses "
              f"{inst.lock.olo_tag}, the tag the reference systems were verified with")
    return lib


def add_uvvm(vu) -> dict:
    """Adds the UVVM components of the system testbenches, each as its own library; returns name -> library.

    Every component gets the files of its compile order (script/compile_order.txt of UVVM); the VVC components
    compile the target-dependent files of the VVC framework into their own libraries, as UVVM requires. GHDL
    analyses them with UVVM_GHDL_FLAGS.
    """
    inst = installed()
    marks = _marks(vu)
    orders = sorted(p for p in inst.lock.files.get("uvvm", {}) if p.endswith("/script/compile_order.txt"))
    out = {}
    for order in orders:
        component = order.split("/", 1)[0]
        text = (inst.hdl / "uvvm" / order).read_text(encoding="utf-8")
        m = re.search(r"^#\s*library\s+(\w+)", text, re.MULTILINE)
        name = m.group(1) if m else component
        if name in marks:
            out[name] = vu.library(name)
            continue
        if name in _existing(vu):
            raise LibraryConflictError(f"the VUnit project already has a library {name} that openspacehdl did not "
                                       f"add")
        base = posixpath.dirname(order)
        paths = [posixpath.normpath(f"{base}/{p}") for p in read_list(inst.hdl / "uvvm" / order)]
        lib = _add_library(vu, name, _verified(inst, "uvvm", [order] + paths)[1:])
        lib.add_compile_option("ghdl.a_flags", list(UVVM_GHDL_FLAGS))
        marks[name] = "uvvm"
        out[name] = lib
    return out
