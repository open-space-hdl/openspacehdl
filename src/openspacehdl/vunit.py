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

import json
import posixpath
import re
import sys
from pathlib import Path

from openspacehdl import lock as _lock
from openspacehdl.errors import OshError
from openspacehdl.installed import Installed, installed  # noqa: F401 (installed: replaced by tests)

# Analysis flags of GHDL for Open Logic FT, UVVM and the simulation models of vendor adapters, as the regressions of
# the cores use them: they declare shared variables of non-protected types. The sources of a core are analysed as
# strict VHDL-2008. A testbench that uses UVVM also needs -frelaxed at elaboration (VUnit sim option ghdl.elab_flags).
RELAXED_GHDL_FLAGS = ("-frelaxed", "-Wno-hide", "-Wno-shared")
# Bench components of the package (docs/design.md, section 6.3) and the cores they instantiate
OSH_TB_LIBRARY = "osh_tb"
OSH_TB_DIR = Path(__file__).resolve().parent / "osh_tb"
OSH_TB_FILES = ("osh_tb_pkg.vhd", "osh_tb_mem_pkg.vhd", "osh_tb_memvar_pkg.vhd", "osh_tb_check_pkg.vhd",
                "osh_tb_axi_mem.vhd", "osh_tb_axilite_master.vhd", "osh_tb_axis_master.vhd", "osh_tb_axis_slave.vhd",
                "osh_tb_rmap_initiator.vhd", "osh_tb_spw_far_end.vhd", "osh_tb_spfi_far_end.vhd")
OSH_TB_CORES = ("openwire", "openrmap", "openspp", "openfibre")
_MARK = "_openspacehdl_libraries"


class UnknownCoreError(OshError):
    """The core is not in the lock manifest of this package version."""


class LibraryConflictError(OshError):
    """The VUnit project already has a library of this name that openspacehdl did not add."""


class OpenLogicConflictError(OshError):
    """The VUnit project already has a library olo that openspacehdl did not add."""


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


def _add_library(vu, name: str, files: list[Path], relaxed: set[Path] | None = None):
    """A new library with these files; GHDL analyses the files in relaxed (all when None) with RELAXED_GHDL_FLAGS."""
    lib = vu.add_library(name, vhdl_standard="2008")
    for f in files:
        source = lib.add_source_file(str(f), vhdl_standard="2008")
        if relaxed is not None and f in relaxed:
            source.add_compile_option("ghdl.a_flags", list(RELAXED_GHDL_FLAGS))
    if relaxed is None:
        lib.add_compile_option("ghdl.a_flags", list(RELAXED_GHDL_FLAGS))
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
    _add_library(vu, name, inst.verified("olo", [inst.lock.olo_file_list] + paths)[1:])
    marks[name] = "olo"


def add_core(vu, core: str, *, models: bool = True):
    """Adds a core and, once, Open Logic FT to the VUnit project; returns the VUnit library of the core.

    The library takes the name from the lock manifest (for example openfibre) and the files of the core's compile
    order, VHDL-2008. With models, the simulation models of the core's vendor adapters are added as well (for
    OpenFibre the entity ofb_pa_gty with its behavioural architecture mdl), so that GHDL simulates the core without
    vendor libraries. GHDL analyses Open Logic FT and the models with RELAXED_GHDL_FLAGS and the sources of the core
    as strict VHDL-2008. Adding the same core again returns its library.
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
    sources = len(paths)
    if models:
        for model_list in c.models.values():
            paths += [model_list] + [p for p in read_list(inst.hdl / c.id / model_list) if p not in paths]
    files = inst.verified(c.id, paths)
    lists = {c.file_list, *c.models.values()}
    model_files = {f for f, p in zip(files[sources:], paths[sources:]) if p not in lists}
    lib = _add_library(vu, c.library, [f for f, p in zip(files, paths) if p not in lists], relaxed=model_files)
    marks[c.library] = c.id
    if c.verified_with and c.verified_with != inst.lock.olo_tag:
        print(f"openspacehdl: {c.name} {c.tag} was verified with Open Logic FT {c.verified_with}; this package uses "
              f"{inst.lock.olo_tag}, the tag the reference systems were verified with")
    return lib


def add_uvvm(vu) -> dict:
    """Adds the UVVM components of the system testbenches, each as its own library; returns name -> library.

    Every component gets the files of its compile order (script/compile_order.txt of UVVM); the VVC components
    compile the target-dependent files of the VVC framework into their own libraries, as UVVM requires. GHDL
    analyses them with RELAXED_GHDL_FLAGS.
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
        lib = _add_library(vu, name, inst.verified("uvvm", [order] + paths)[1:])
        marks[name] = "uvvm"
        out[name] = lib
    return out


def add_osh_tb(vu):
    """Adds the bench components of the package (library osh_tb, docs/design.md section 6.3); returns the library.

    The components are UVVM VVC wrappers, the AXI4 memory responder and the SpaceWire and SpaceFibre far ends, which
    instantiate OpenWire, OpenRMAP, OpenSPP and OpenFibre. UVVM and these cores are added as well (add_uvvm,
    add_core); a core that add_core or add_system added before is used as it is. GHDL analyses osh_tb with
    RELAXED_GHDL_FLAGS. Adding it again returns the library.
    """
    marks = _marks(vu)
    if OSH_TB_LIBRARY in marks:
        return vu.library(OSH_TB_LIBRARY)
    if OSH_TB_LIBRARY in _existing(vu):
        raise LibraryConflictError(f"the VUnit project already has a library {OSH_TB_LIBRARY} that openspacehdl did "
                                   f"not add")
    add_uvvm(vu)
    for core in OSH_TB_CORES:
        add_core(vu, core)
    files = [OSH_TB_DIR / f for f in OSH_TB_FILES]
    missing = [f.name for f in files if not f.is_file()]
    if missing:
        raise OshError(f"the installation of openspacehdl lacks the bench components {', '.join(missing)}")
    lib = _add_library(vu, OSH_TB_LIBRARY, files)
    marks[OSH_TB_LIBRARY] = OSH_TB_LIBRARY
    return lib


def read_compile_order(path: Path) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """The sources (repository -> commit) and the files (library, path) of a compile order exported by the Composer."""
    sources, files = {}, []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "format composer-compile-order 1":
        raise OshError(f"{path.name} is not a compile order of the Composer (format composer-compile-order 1)")
    for line in lines[1:]:
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "source":
            sources[parts[1]] = parts[3]
        elif parts[0] == "file":
            files.append((parts[1], parts[2]))
    return sources, files


def add_system(vu, project):
    """Adds a project written by openspacehdl new (docs/design.md, section 6): returns the library of the system.

    The libraries and files of the system's compile order (hdl/<system>_compile_order.txt, the file set the Composer
    exported) come from the snapshots of the package, checked against the lock manifest; the files of a vendor
    adapter are replaced by its simulation models; the top level and the files of sim/tb/ go into the library of
    the system. UVVM and the bench components are added as well (add_osh_tb, with the cores the far ends
    instantiate). A library that add_core added before is used as it is.
    """
    project = Path(project)
    manifest = project / ".openspacehdl" / "project.json"
    if not manifest.is_file():
        raise OshError(f"{project} is not a project of openspacehdl: .openspacehdl/project.json is missing")
    entity = json.loads(manifest.read_text(encoding="utf-8"))["system"]
    order = project / "hdl" / f"{entity}_compile_order.txt"
    sources, files = read_compile_order(order)
    inst = installed()
    lk = inst.lock
    olo_repo = lk.olo_repository.split("/")[-1]
    cores = {c.repository.split("/")[-1]: c for c in lk.cores}
    for repo, commit in sources.items():
        pinned = lk.olo_commit if repo == olo_repo else cores[repo].commit if repo in cores else None
        if pinned is None:
            raise OshError(f"the compile order of {entity} uses {repo}, which this package does not carry")
        if commit != pinned:
            raise OshError(f"the compile order of {entity} uses {repo} at {commit[:7]}; this package carries "
                           f"{pinned[:7]}; export the system again with the Composer of this package version")
    adapter_dirs = {}
    for c in lk.cores:
        for model_list in c.models.values():
            adapter_dirs[(c.repository.split("/")[-1], posixpath.dirname(model_list) + "/")] = (c, model_list)
    libs: dict[str, list[tuple[Path, bool]]] = {}
    placed = set()
    for lib, path in files:
        repo, _, rel = path.partition("/")
        if rel and repo in sources:
            sid = "olo" if repo == olo_repo else cores[repo].id
            adapter = next((v for (r, d), v in adapter_dirs.items() if r == repo and rel.startswith(d)), None)
            if adapter is not None:
                core, model_list = adapter
                if model_list not in placed:
                    placed.add(model_list)
                    model = read_list(inst.hdl / sid / model_list)
                    for f in inst.verified(sid, [model_list] + model)[1:]:
                        libs.setdefault(lib, []).append((f, True))
                continue
            libs.setdefault(lib, []).append((inst.verified(sid, [rel])[0], sid == "olo"))
        else:
            libs.setdefault(lib, []).append((order.parent / path, False))
    tb = sorted((project / "sim" / "tb").glob("*.vhd"))
    libs.setdefault(entity, []).extend((f, True) for f in tb)
    marks = _marks(vu)
    existing = _existing(vu)
    for lib in libs:
        if lib in marks:
            continue
        if lib in existing:
            if lib == lk.olo_library:
                raise OpenLogicConflictError(f"the VUnit project already has a library {lib} that openspacehdl did "
                                             f"not add")
            raise LibraryConflictError(f"the VUnit project already has a library {lib} that openspacehdl did not "
                                       f"add")
    for lib, entries in libs.items():
        if lib in marks:
            continue
        library = vu.add_library(lib, vhdl_standard="2008")
        for f, relaxed in entries:
            source = library.add_source_file(str(f), vhdl_standard="2008")
            if relaxed:
                source.add_compile_option("ghdl.a_flags", list(RELAXED_GHDL_FLAGS))
        marks[lib] = "system" if lib == entity else lib
    add_osh_tb(vu)
    return vu.library(entity)


def guard_ghdl_generics() -> None:
    """Gives every GHDL simulation its own copy of the option ghdl.sim_flags and checks its generics.

    VUnit 5.0 development builds append the generics of a test to the shared list of ghdl.sim_flags in place, so a
    simulation inherited the generics of the tests started before it. The guard is the one of the regressions of the
    cores; it is installed once and works with VUnit 4.7 as well."""
    from vunit.sim_if.ghdl import GHDLInterface

    if getattr(GHDLInterface._get_command, "_openspacehdl_guard", False):
        return
    original = GHDLInterface._get_command

    def wrapper(self, config, *args, **kwargs):
        config.sim_options = {**config.sim_options,
                              "ghdl.sim_flags": list(config.sim_options.get("ghdl.sim_flags", []))}
        cmd = original(self, config, *args, **kwargs)
        generics = [arg for arg in cmd if arg.startswith("-g")]
        expected = [f"-g{name}={value}" for name, value in config.generics.items()]
        if generics != expected:
            sys.exit(f"GHDL command with the generics {generics}, expected {expected}")
        return cmd

    wrapper._openspacehdl_guard = True
    GHDLInterface._get_command = wrapper
