# Design of openspacehdl, phase A

This document describes the design of phase A of the Python package `openspacehdl`: what the package contains, how
one package version pins one consistent set of cores, and the commands and the Python API that phase A adds. Section
[Open points](#11-open-points) lists the decisions that are still to be taken.

## 1. Purpose and scope

Open Space HDL is a family of VHDL IP cores for spacecraft on-board data handling. The Open Space Composer
(openspacehdl.org/composer/) assembles a system from the cores and saves it as a `.composer.json` file; its button
Export HDL writes the top level, the compile order and the constraints of the system. The package takes the next
steps on the integrator's machine, also without network access:

- it carries the cores, Open Logic FT and the reference systems at the versions one package version pins;
- it adds a core to a VUnit project with one call;
- it turns a saved system into a project with a VUnit simulation, a system testbench and a smoke test that passes as
  generated, so that the integrator starts writing system test cases at once;
- it writes the sources as a plain tree or as Git repositories for a build machine without network;
- it serves the website, the documentation of every core and the Composer locally.

Phase A covers simulation in GHDL. Builds for FPGA boards follow in later phases (section 10).

## 2. Overview

| Command or call | What it does |
| --- | --- |
| `openspacehdl info [project]` | Lists the family (available since 0.0.1). |
| `openspacehdl lock` | Shows the lock manifest of this package version: the cores, their tags and the Open Logic tag. |
| `openspacehdl.add_core(vu, "<core>")` | Adds a core and Open Logic FT to a VUnit project. |
| `openspacehdl new <system>.composer.json [<dir>]` | Writes a project for the system. |
| `openspacehdl update [<dir>]` | Regenerates the generated files of a project after the system changed. |
| `openspacehdl export <dir> [--git]` | Writes the sources as a plain tree, or as Git repositories with their history. |
| `openspacehdl serve` | Serves the website, the documentation and the Composer on 127.0.0.1. |

The flow of a system:

1. The integrator composes the system in the Composer (online, or offline through `openspacehdl serve`), saves the
   `.composer.json` file and exports the HDL.
2. `openspacehdl new` checks that the file and the export belong together and match the pins of the package, and
   writes the project.
3. `python sim/run.py` compiles the system with the sources of the package and runs the smoke test in GHDL.
4. The integrator adds test cases to the testbench of the project. After a change of the system in the Composer,
   `openspacehdl update` regenerates the generated files and leaves the integrator's files alone.

The package consumes the output of the Composer: the saved file and its export. It does not resolve a system itself
and needs no JavaScript runtime.

## 3. Lock manifest

### 3.1 Content

The lock manifest `openspacehdl/data/lock.json` is the single source of truth of a package version. It is generated
at the build of the package and never edited by hand.

| Key | Content |
| --- | --- |
| `format`, `version` | `openspacehdl-lock`, format version 1 |
| `package` | Version of the package |
| `website` | Commit of the website repository, the catalog ID of its `assets/composer/catalog.json` and the generator version of its Composer |
| `referenceSystems` | Release tag of open-space-hdl/reference-systems and its commit |
| `openLogic` | The one Open Logic FT of this version: tag, commit, library `olo`, the commit of its submodule `3rdParty/en_cl_fix` |
| `uvvm` | UVVM commit and the components the system testbenches use |
| `cores[]` | Per core: id, name, repository, release tag, commit, library, file list and its format, `verifiedWith` (the Open Logic tag the core's own regression ran with), simulation models of vendor adapters, TRL, licence |
| `files` | SHA-256 of every file of the source snapshots, per repository |

Example of one entry of `cores[]`:

```json
{
  "id": "openfibre",
  "name": "OpenFibre",
  "repository": "open-space-hdl/openfibre",
  "tag": "v0.1.0",
  "commit": "7726422f8bc85250ab0c82e332614eaf68a90f4b",
  "library": "openfibre",
  "fileList": "compile_order.txt",
  "fileListFormat": "files",
  "verifiedWith": "4.7.0-ft.6",
  "models": { "ofb_pa_gty": "hdl/ofb_pa_gty/compile_order_sim.txt" },
  "trl": 3,
  "license": "PSI HDL Library License 1.0"
}
```

### 3.2 Generation

`tools/lock.py` writes the manifest from three inputs:

1. the website repository at one commit: the pins of `_composer/catalog/sources.yml` (commit, library, file list,
   `verified_with`, the Open Logic tag), the catalog ID and the generator version, and the project cards of
   `_data/projects.yml` (public status, TRL);
2. reference-systems at one release tag: the commits of its submodules in `cores/` and its `tools/composer_ref.txt`
   (the website commit its systems were checked against);
3. the repositories of the cores and of Open Logic FT: the release tags of the pinned commits, the files of the
   snapshots and their hashes.

The same tool with `--check` regenerates the manifest in memory and compares it with the committed one.

### 3.3 Consistency rules

The build of the package stops with an error when one of these rules fails:

| Rule | Check |
| --- | --- |
| L1 | Every pinned commit of a core is the commit of a release tag `vX.Y.Z` of its repository, and the tag is on the remote of the repository; the same holds for the tag of reference-systems. Consumers pin published releases, never `develop`. |
| L2 | Every repository that both the catalog and reference-systems pin has the same commit in both. |
| L3 | There is one Open Logic FT: the tag of the catalog's `olo` source equals the commit of `cores/open-logic-ft` of reference-systems. |
| L4 | The website commit of the manifest equals `tools/composer_ref.txt` of the reference-systems release. |
| L5 | A core enters the manifest only when its card on the website is public and it is a source of the catalog. |
| L6 | The hashes in `files` match the files of the snapshots in the wheel. |
| L7 | The licence files of every snapshot repository are in the wheel, listed in `license-files`, and their licence is named in the licence expression of the wheel (section 4.4). |
| L8 | The longest path in the wheel stays within the path budget of section 4.5. |
| L9 | The wheel stays below the file size limit of the project on PyPI (section 4.3). |
| L10 | Every core pins the same UVVM commit; it is the UVVM of the manifest. |

The `verifiedWith` tag of a core may differ from the Open Logic tag of the manifest: the reference systems are
verified with that tag. `openspacehdl lock` and `add_core` show both.

## 4. Wheel layout and sizes

### 4.1 Layout

```text
openspacehdl/
    __init__.py, cli.py, family.py      command line and family list (0.0.1)
    lock.py                             reads data/lock.json
    vunit.py                            add_core, add_uvvm, add_system
    composer.py                         reads and checks .composer.json files and exports
    project.py                          new, update
    export.py, serve.py
    data/lock.json, data/family.json
    data/schema/system-1.json, system-2.json      Composer schemas at the website commit of the lock
    templates/                          templates of the generated project (MIT)
    hdl/<id>/...                        source snapshots of the cores, Open Logic FT and reference-systems
    hdl/uvvm/...                        UVVM components of the system testbenches, with UVVM's licence
    hdl/osh_tb/...                      bench components of the package (MIT)
    portal/                             website, documentation sites, Composer (see 4.3)
    bundles/<repository>.bundle         Git bundles (see 4.3)
```

The directory of a snapshot is the id of its repository in the lock manifest: `openwire`, `openrmap`, `openspp`,
`openfibre`, `opencrypto`, `opencompact`, `olo` for Open Logic FT and `refsys` for reference-systems. The short names
keep the paths within the budget of section 4.5.

The package finds its files with `importlib.resources`; pip installs a wheel unpacked, so every file has a path that
VUnit and the simulators can read. The file walk of the build takes only the listed files: no `.git` directories, no
CI files, no simulator output.

### 4.2 Content of a source snapshot

A snapshot is a copy of the files of a repository at its pinned commit, without history:

- every file of the compile order (`compile_order.txt`), including the files of Open Logic FT's `3rdParty/en_cl_fix`;
- the files of the simulation models of vendor adapters (for OpenFibre `hdl/ofb_pa_gty/compile_order_sim.txt`, which
  also lists a package of the core's bench, `tb/ofb_tb_8b10b_pkg.vhd`);
- the C register headers (`sw/*.h`), which the generated `<system>_regs.h` includes;
- the licence files.

The testbenches of the cores stay out (section 10). For reference-systems the snapshot is `systems/`, `sim/tb/` and
`tools/`.

UVVM: `uvvm_util`, `uvvm_vvc_framework`, `bitvis_vip_scoreboard`, `bitvis_vip_clock_generator`,
`bitvis_vip_axilite`, `bitvis_vip_axistream` and `bitvis_vip_axi` at the commit the cores use, with UVVM's licence:
the compile order of each component (`script/compile_order.txt`) and every file it lists. The VVC components list
four files of `uvvm_vvc_framework/src_target_dependent/` as well, which each of them compiles into its own library.

### 4.3 Sizes

Measured on the pins of website 1b3d619 and reference-systems v0.1.0 (compressed with deflate as in a wheel):

| Content | Uncompressed | Compressed |
| --- | --- | --- |
| Source snapshots, compile order files of all repositories | 4.2 MB | 0.9 MB |
| Whole trees without testbenches (for comparison; Open Logic FT alone 24 MB, of which 17.5 MB PNG images of its documentation) | 39 MB | 20 MB |
| UVVM components (`src/` only) | 2.6 MB | about 0.6 MB (estimate) |
| Git bundles: each pinned tag with its history (all published branches and tags: 27.3 MB; the tagged commit alone: 20.7 MB) | 26.8 MB | 26.8 MB (already compressed); Open Logic FT 20.2 MB, of which most is the documentation images of the tagged tree; every core 0.45 to 2.1 MB |
| Website (`_site`) | 4.2 MB | about 1.5 MB (estimate) |
| Documentation sites (MkDocs): OpenRMAP measured 5.3 MB; Open Logic FT carries the 17.5 MB of images | about 60 MB for all | about 30 MB (estimate) |

The package is one wheel with all of it, about 60 MB at the current pins, so that one file brings everything to a
machine without network. It is below the default PyPI limit of 100 MB per file and grows by about 5 to 8 MB with
every new core (sources, bundle, documentation). The build checks the size of the wheel against the file limit of
the project on PyPI (rule L9); before the wheel reaches it, the limit is raised on request at PyPI.

A bundle without history (only the tagged commit) would save about 6 MB, because the documentation images of Open
Logic FT are part of the tagged tree itself. The bundles keep the history up to the pinned tag.

### 4.4 Licences

The wheel carries content under three licences:

| Content | Licence | Licence files |
| --- | --- | --- |
| Package code and the templates of generated projects | MIT | `LICENSE` |
| Cores, Open Logic FT, reference-systems | PSI HDL Library License 1.0 | `License.txt` and `LGPL2_1.txt` of each repository |
| `en_cl_fix`, submodule of Open Logic FT | MIT | `LICENSE.md` |
| UVVM components | Apache License 2.0 | `LICENSE` of UVVM |

The PSI HDL Library License has no SPDX identifier, so the expression names it with a `LicenseRef`:

```toml
license = "MIT AND LicenseRef-PSI-HDL-1.0 AND Apache-2.0"
license-files = ["LICENSE", "src/openspacehdl/licenses/*.txt", "src/openspacehdl/licenses/*.md"]
```

The licence texts are part of the package repository, in `src/openspacehdl/licenses/` (`PSI-HDL-1.0.txt`,
`LGPL-2.1.txt`, `Apache-2.0.txt`, `MIT-en_cl_fix.md`, with `licenses.json` naming the SPDX identifier of each), so
the metadata is the same for every build. The snapshots keep the licence files of their repositories as well. Rule
L7 checks that every licence file of a snapshot is byte for byte one of these texts, that the expression names its
identifier and that `license-files` covers every text. setuptools validates the expression with
`packaging.licenses`, writes one `License-File` entry per file into the metadata and copies the files to
`.dist-info/licenses/`; `twine check --strict` passes.

The portal carries content under further licences:

| Portal content | Licence |
| --- | --- |
| Code of the website and the Composer | MIT |
| Texts and images of the website | Creative Commons Attribution 4.0 |
| Logo, favicon and touch icon of Open Space HDL (on the website and in every documentation site) | All rights reserved; no licence is granted |
| Fonts (Sora, JetBrains Mono), each with its licence file | SIL Open Font License 1.1 |
| Documentation sites of the cores | the licence of the core |
| Assets of the MkDocs theme and other third-party files | their own licences |

For the portal, rule L7 works with a licence map: every file of the portal matches exactly one entry of the map (a
path pattern and its licence), every licence of the map is named in the expression with its licence or notice file
in `license-files`, and the build stops when a file matches no entry. The logo files are named with
`LicenseRef-OpenSpaceHDL-Logo` and a notice file that states the reservation; they are never covered by the CC BY
entry. With the portal in the wheel the expression becomes, for example,
`MIT AND LicenseRef-PSI-HDL-1.0 AND Apache-2.0 AND CC-BY-4.0 AND OFL-1.1 AND LicenseRef-OpenSpaceHDL-Logo`, extended
by the licences the map finds for the theme assets. The Git bundles carry the licence files of their repositories in
their trees.

### 4.5 Path length

Windows limits a path to 260 characters unless long paths are enabled, and GHDL and other tools fail beyond it. A
wheel installs below `site-packages`, which is already long: about 70 characters for a per-user Python on Windows,
more in a virtual environment inside a project. The build therefore allows an install prefix of 120 characters and
checks that the longest path in the wheel stays below 260 minus 120, that is at most 139 characters (rule L8).

With the repository names as directories, the longest path at the current pins would be 134 characters, a constraint
file of a reference system:
`openspacehdl/hdl/reference-systems/systems/spfi_compress_encrypt/targets/vck190/constr/...`. With the ids of
section 4.1 it is 123 characters. The paths in `.dist-info/licenses/` are below 100 characters.

## 5. add_core

### 5.1 Use

```python
from vunit import VUnit
import openspacehdl as osh

vu = VUnit.from_argv()
osh.add_core(vu, "openfibre")   # adds the libraries olo and openfibre
osh.add_core(vu, "openrmap")    # reuses olo
vu.main()
```

### 5.2 Behaviour

- `add_core(vu, core, *, models=True)` adds the library of the core (its name from the manifest) with the files of
  its compile order, VHDL-2008, and returns the VUnit library.
- The first call adds the library `olo` with the files of Open Logic FT at the tag of the manifest, including
  `en_cl_fix`; later calls reuse it. Every core in one package version uses this one Open Logic.
- With `models=True` the simulation models of the core's vendor adapters replace the vendor files (for OpenFibre the
  architecture `mdl` of `ofb_pa_gty`), so that GHDL simulates the core without vendor libraries.
- When the core's `verifiedWith` differs from the Open Logic tag of the manifest, `add_core` prints one note with both
  tags; it is not an error.
- `add_uvvm(vu)` adds the UVVM components of section 4.2, each as the library its compile order names, with the
  files of that compile order; it sets the GHDL analysis flags UVVM needs (`-frelaxed`, `-Wno-hide`, `-Wno-shared`)
  on these libraries, as `add_core` does on `olo` and on the simulation models (the regressions of the cores do the
  same; the sources of a core are analysed strictly). A testbench that uses UVVM also needs `-frelaxed` at
  elaboration (`ghdl.elab_flags`); the generated `run.py` of a project sets it.
- Before it adds a file, every call checks it against the SHA-256 of the lock manifest.
- `add_system(vu, project_dir)` adds a generated project (section 6): the libraries and files of the system's compile
  order (`hdl/<system>_compile_order.txt`, the file set the Composer exported), read from the snapshots of the
  package, with the simulation models in place of the vendor files; the top level; the UVVM components; the bench
  components of `osh_tb`; and the harness and testbench of the project. The Open Logic and library rules of `add_core`
  apply.
- The calls work with VUnit 4.7.1 from PyPI and with VUnit 5.0. VUnit is the optional dependency
  `openspacehdl[vunit]`.

### 5.3 Errors

Every error is an `openspacehdl.OshError` with a message that says what to do:

| Error | When |
| --- | --- |
| `UnknownCoreError` | The core is not in the manifest of this version. The message lists the cores it has, and names a core that is on the website but not yet released ("Coming soon"). |
| `OpenLogicConflictError` | The VUnit project already has a library `olo` that the package did not add. The message names the Open Logic tag of the package. There is no override in phase A: one VUnit project never mixes two Open Logic versions. |
| `LibraryConflictError` | The VUnit project already has a library with the name of the core that the package did not add. |
| `OshError` | A file of the snapshot is missing or its hash differs from the manifest (a damaged installation). |

## 6. new and update

### 6.1 Inputs and checks

`openspacehdl new <system>.composer.json [<dir>] [--hdl <export dir>]` reads the saved file and its export. The export
is taken from `--hdl`, else from `hdl/` next to the file, else from the directory of the file. `new` refuses, with
the reason, when:

- the file fails the published schema of its `formatVersion` (system-1 or system-2, stored in the package). The
  package checks it with its own validator of the JSON Schema 2020-12 keywords these schemas use
  (`openspacehdl.jsonschema`), so it needs no dependency; a keyword it does not know is an error of the schema;
- the file has no `resolved` part, `resolved.problems` is not empty, or `checks` has an entry of severity `error`
  (the rule of Export HDL);
- `resolved.version` is unknown to the package. The Composer writes it as the first key of `resolved` from generator
  0.9.8-beta on (layout 1); a file without it has layout 1. For a file of a generator version the package was not
  tested with, `new` warns;
- the SHA-256 of the file differs from the one in the header of `<system>_compile_order.txt`: the export does not
  belong to the file;
- a source of `resolved.compile` has another commit than the manifest. The message names the package version whose
  manifest matches, if one is known, and says that the system can be saved again with the Composer of this package
  version (`openspacehdl serve`);
- an external interface has a type that the generator has no bench component for (section 6.3).

### 6.2 Generated project

```text
<dir>/
    <system>.composer.json        the saved file (copied)
    hdl/                          the export, copied: top level, compile order, constraints, address map, regs.h
    sim/run.py                    seed: VUnit entry point, calls openspacehdl.add_system
    sim/tb/<system>_th.vhd        generated: harness
    sim/tb/<system>_th_pkg.vhd    generated: constants and procedures of the system, the smoke test
    sim/tb/<system>_tb.vhd        seed: the test cases
    README.md                     seed
    .openspacehdl/project.json    manifest of the generated files
```

The files fall into four classes:

| Class | Written by | Changed by `update` |
| --- | --- | --- |
| Input | the Composer: the saved file and its export, copied byte for byte | replaced by `update --from` with a new save and its export |
| Generated | `new` and `update` | yes, unless edited (section 6.4) |
| Seed | `new` only | never |
| User | the integrator | never; the package does not know them |

`sim/run.py` is a seed so that the integrator can add options; the logic it calls lives in the package. It contains
the guard that gives every GHDL simulation its own `sim_flags`, because VUnit 5.0 development builds otherwise carry
generics from one configuration into the next.

### 6.3 Generated testbench

The generator is built in two steps. The first step generates the harness with the system, a clock per clock port
(the period derived from the frequency of its clock domain, `1 sec / <Hz>`), the reset from the testbench
(`osh_reset`, 16 cycles of the slowest clock) and every input of the external interfaces held idle; its smoke test
resets the system and lets it run on its clocks. The second step adds the bench components and the register checks
below.

The harness `<system>_th.vhd` instantiates the system and, for every external port of `resolved.ports`:

- a clock generator for every port of kind `clock`, with the period derived from `frequencyHz` of its clock domain;
- the reset for the port of kind `reset` (asynchronous, high-active);
- a bench component for every external interface, chosen by the interface type. The type comes from
  `port.interface` through `resolved.instances[].block` to `catalogSubset.blocks[].interfaces[]`:

| Interface type | Role at the system | Bench component |
| --- | --- | --- |
| `axi4lite` | slave | UVVM AXI4-Lite VVC |
| `axi4` | master | AXI4 memory responder of the package (`osh_tb_axi_mem`); UVVM has no AXI4 slave VVC |
| `axi4` | slave | UVVM AXI4 VVC |
| streams (`spp.tx`, `byte.stream`, `c123.samples`, ...) | sink | UVVM AXI4-Stream VVC, transmitter; the signals of the type (data, keep, last, user) mapped, absent optional signals tied to their idle value |
| streams (`spp.rx`, ...) | source | UVVM AXI4-Stream VVC, receiver |
| `spw.ds` | pins | SpaceWire far end: an `owr_core` and an `omap_core` with the initiator, the lines joined crosswise |
| `spfi.serial` | pins | SpaceFibre far end: an `ofb_core` with `ofb_pa_gty` (architecture `mdl` in GHDL) and an `omap_core` with the initiator, with the lane count and virtual channels of the system's port, lane i to lane i |

The far ends are bench components of the package (library `osh_tb`), built from the family's own cores as a second
port at the other end of the link; the SpaceFibre far end follows the far end of the reference systems.

The harness package `<system>_th_pkg.vhd` holds the constants of the system (clock periods, register banks with base,
size and ID value, the links and the RMAP target behind each) and the procedures `osh_smoke_test`,
`osh_read_register` and `osh_rmap_read`. The seed testbench `<system>_tb.vhd` is a VUnit runner with UVVM; its first
test case `test_smoke` calls `osh_smoke_test`, and its test end fails on unexpected alerts and on missing expected
alerts, as in the benches of the cores.

The smoke test:

1. starts the clocks, holds the reset for 16 cycles of the slowest clock and releases it;
2. waits until every far end reports its link up (SpaceWire state Run, SpaceFibre link initialised), with a timeout;
3. reads the ID register of every register bank of the address map (offset and value from
   `catalogSubset.blocks[].idRegister` and `resolved.addressMap`) and compares it with the expected value:
   - a bank in an address space of kind `port` through the AXI4-Lite VVC of that port;
   - a bank behind an RMAP target (an address space of kind `master` at the target's memory interface) with an RMAP
     read command from the far end of the link that carries the target;
   - a bank without an ID register with a read of its base address that must complete with an OKAY response;
4. checks that no alert was raised.

Every Composer example has register banks, so step 3 never runs empty for them. Systems whose banks are reachable
only through a link (for example the reference system spfi_encrypt) need the far end with the RMAP initiator.

### 6.4 update

`.openspacehdl/project.json` records the package version, the lock, the SHA-256 of every input (the saved file and the
files of its export) and, per generated file, its path and the SHA-256 of the text the package generated last, also
when that text went to `<file>.new`: taking over `<file>.new` makes the file unchanged for the next `update`. The
integrator saves a changed system over the project's file and exports into `hdl/`, or hands the new save and its export
to `openspacehdl update --from <file> [--hdl <dir>]`, which copies them into the project first; an export file of
before that the new export no longer has is removed when it is unchanged. `openspacehdl update [<dir>]` then reads
the saved file and the export, runs the checks of section 6.1 and regenerates every generated file:

| State of the file on disk | Action |
| --- | --- |
| Unchanged since the package wrote it | Replaced by the new text. |
| Edited by the integrator | Left as it is; the new text goes to `<file>.new`, and `update` lists the file and exits with status 1. |
| Deleted | Not written again; `update` lists it. `--restore` writes it. |
| Not generated any more (an interface removed) | Deleted when unchanged, otherwise left and listed. |
| A file of the integrator where a new generated file belongs | Left as it is; the new text goes to `<file>.new`, as for an edited file. |

Seed files and user files are never touched. `update --dry-run` lists the actions without writing. Running `update`
right after `new` changes nothing, and a second `update` after a change of the system changes nothing more.

### 6.5 File headers

Every generated and seed file starts with a comment that names the package version, the lock and the class of the
file. A generated file of the package carries the MIT notice of the templates (the copyright line and the permission
notice of `LICENSE`). A seed file carries no licence notice: it belongs to the integrator from the start.

Generated (VHDL; Python files use `#`):

```vhdl
-- Generated by openspacehdl 0.1.0 from spfi_encrypt.composer.json
-- Lock: website 1b3d619cb4, reference-systems v0.1.1
-- Class: generated. Regenerated by openspacehdl update; edits are kept and reported.
--
-- Copyright (c) 2026 Julian Schneider
-- Permission is hereby granted, free of charge, to any person obtaining a copy ... (MIT License, full text)
```

Seed:

```vhdl
-- Written by openspacehdl 0.1.0 from spfi_encrypt.composer.json
-- Lock: website 1b3d619cb4, reference-systems v0.1.1
-- Class: seed. Written once by openspacehdl new; openspacehdl update never changes it.
```

The files of the Composer export in `hdl/` keep the header the Composer wrote and are copied byte for byte, because
`new` and `update` check them against the saved file; the project manifest records them as inputs.

## 7. export

- `openspacehdl export <dir> [--core <core> ...]` writes the source snapshots as a plain tree:
  `<dir>/<repository>/...` with the compile order of every repository, UVVM in `<dir>/uvvm`, and
  `<dir>/openspacehdl-lock.json`. Every file is checked against the manifest first. A build flow for Vivado or Libero
  reads the files from there.
- `openspacehdl export <dir> --git [--core <core> ...]` clones every repository from its bundle into
  `<dir>/<repository>`, checked out at the pinned commit, with its history up to that commit. Open Logic FT gets its
  submodule `3rdParty/en_cl_fix` from the bundle of en_cl_fix; reference-systems gets its submodules
  `cores/<repository>` from the neighbouring clones, and the nested en_cl_fix of its Open Logic FT as well. All of it
  works without network (local file transport only). The remote `origin` of every clone and the submodule URLs are
  then set back to the published repositories, so a later `git fetch` works when network is available. The export
  checks that every clone and every submodule is at the commit the manifest and the superproject record. UVVM has no
  bundle; its snapshot is in the tree export.
- With `--core`, only the named cores and Open Logic FT are exported, without reference-systems and UVVM. The target
  directory must be new or empty; the export never writes into a directory with content.

The bundles are `<id>.bundle` in `openspacehdl/bundles/`: one per core, `olo` for Open Logic FT, `en_cl_fix` for its
submodule and `refsys` for reference-systems. Each bundle carries the pinned commit with its history: the branch
`main` (Open Logic FT `fault-tolerant`, en_cl_fix `open-logic`) at the pinned commit and every published tag in that
history. It never carries other branches, later commits of the published branches or local refs of the machine that
built the package. A bundle is made from a temporary bare copy of the clone, so the clone itself is only read. The
manifest records the refs of every bundle, and the wheel check compares them with `git bundle list-heads` (rule L6).

## 8. serve

`openspacehdl serve [--port <n>] [--no-browser]` serves the portal of the package (`openspacehdl/portal/`) with the
standard library's HTTP server and opens the browser:

- it binds to 127.0.0.1 only; phase A has no option for another address;
- `/` is the website, `/<repository>/` the documentation of each core at its pinned tag, `/composer/` the Composer
  with the catalog of the lock, so that a file saved there matches the pins of the package;
- the Composer fetches its catalog and examples by relative URL and needs `http://` rather than `file://`, which is
  why the package serves the files instead of opening them;
- links to GitHub stay links to GitHub and need network.

The package CI builds the portal from the tagged sources: the website with Jekyll at the website commit of the lock,
each documentation site with MkDocs from `tools/docs` of the core at its tag.

## 9. Test strategy

| Level | What | Simulator or tool |
| --- | --- | --- |
| Unit | Lock generation and the rules L1 to L6 with consistent and inconsistent fixture sets; every refusal of section 6.1; the interface type mapping; the update table of section 6.4; `add_core` and its errors against a recording stand-in of the VUnit object; `serve` on an ephemeral port of 127.0.0.1; `export` as a tree and with `--git` | pytest |
| Mutation | Each refusal and each update rule is proven by a mutation of the package that makes a test fail; a system file with a wrong ID value makes the smoke test fail | pytest, GHDL |
| Cores | `add_core` of every core, alone and all in one project, compiles in GHDL | GHDL through VUnit |
| Systems | Every example of the Composer (seven at the website commit of the lock) and the systems of the reference-systems release: `new`, then `python sim/run.py`, the smoke test passes; `update` right after `new` changes nothing | GHDL through VUnit |
| Exports | The exports of the examples come from `tools/composer_hdl.mjs` of the website at the commit of the lock; the CI checks with it that the stored exports are current (exit status 0) | Node.js, CI only |
| Wheel | Build of wheel and sdist with the rules L7 (licences) and L8 (path budget), `twine check --strict`, install without network into fresh environments on Python 3.10 and 3.14, the commands run | pip, twine |
| Deep install | On Windows, an install into a virtual environment whose `site-packages` path is 120 characters long; from there `add_core` of every core compiles in GHDL and one system passes its smoke test | pip, GHDL |
| VUnit versions | The core and system levels with VUnit 4.7.1 and with VUnit 5.0 | VUnit |

The tests run on Windows and Linux. Phase A is complete when every level passes.

## 10. Out of phase A

- Builds for FPGA boards: Vivado for the VCK190 (phase B), Libero for a PolarFire board (phase C), the board data and
  the constraint check of the reference systems.
- Simulation of generated projects in xsim or QuestaSim; phase A runs GHDL.
- The testbenches of the cores and their regression.
- Resolving a system without the Composer, or a port of the Composer's generator.
- Cores that are not public, not released or not in the catalog (today Open1553, OpenCAN, OpenDMA).
- An override of the Open Logic rule of `add_core`.
- `serve` on another address than 127.0.0.1, and any authentication.
- The move of the tools and the board data of reference-systems into the package; reference-systems becomes their
  first consumer later.
- Publishing through GitHub Actions with Trusted Publishing; it comes when the repository is public.

## 11. Open points

| ID | Point | State |
| --- | --- | --- |
| O1 | Distributions: one wheel or three (section 4.3). | Decided: one wheel with the snapshots, the Git bundles and the portal; the bundles keep the history up to the pinned tag. |
| O2 | The first version with content needs a consistent set. With website 3e0f04b and reference-systems v0.1.0, `tools/lock.py --report` finds rule L2 broken for OpenFibre and OpenCompact (catalog v0.1.1, reference-systems v0.1.0) and rule L4 broken (reference-systems v0.1.0 was checked against website f6715ee). | Decided: the first version with content is built on the next reference-systems release that carries the catalog pins. |
| O3 | `resolved.version` of the Composer is decided but not yet written into saved files. | Decided: the Composer writes it from generator 0.9.8-beta on; the package refuses an unknown version. For files of older generators it validates against the schema and warns on a generator version it was not tested with. |
| O4 | Which virtual channel of a SpaceFibre link carries the RMAP target. | Decided: traced in the resolved netlist from the target to the port; `new` refuses when it cannot. |
| O5 | The documentation sites are built at the tags of the cores, with their own MkDocs toolchains. | Decided: every site is built in its own environment with the pinned requirements of `tools/docs` of the core at its tag. |
| O6 | Linux tests while the repository is private and has no CI. | Decided: they run locally in WSL until the CI exists. |
| O7 | The website repository has no licence file, so the licence of the website content and of the Composer in the portal is not stated. | Decided: MIT for the code, CC BY 4.0 for the texts and images; logo, favicon and touch icon stay all rights reserved; third-party fonts and assets keep their licences (section 4.4). The portal enters the wheel once the website repository carries the licence files. |
