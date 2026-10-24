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
| `website` | Commit of the website repository, the catalog ID of its `assets/composer/catalog.json`, the generator version of its Composer and the SHA-256 of its Composer schemas (`composer/schema/system-1.json`, `system-2.json`) |
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
   `verified_with`, the Open Logic tag), the catalog ID and the generator version, the project cards of
   `_data/projects.yml` (public status, TRL) and the Composer schemas, which the tool also writes to
   `openspacehdl/data/schema/`;
2. reference-systems at one release tag: the commits of its submodules in `cores/` and its `tools/composer_ref.txt`
   (the website commit its systems were checked against);
3. the repositories of the cores and of Open Logic FT: the release tags of the pinned commits, the files of the
   snapshots and their hashes.

The same tool with `--check` regenerates the manifest and the schemas in memory and compares them with the committed
ones.

### 3.3 Consistency rules

The build of the package stops with an error when one of these rules fails:

| Rule | Check |
| --- | --- |
| L1 | Every pinned commit of a core is the commit of a release tag `vX.Y.Z` of its repository, and the tag is on the remote of the repository; the same holds for the tag of reference-systems. Consumers pin published releases, never `develop`. |
| L2 | Every repository that both the catalog and reference-systems pin has the same commit in both. |
| L3 | There is one Open Logic FT: the tag of the catalog's `olo` source equals the commit of `cores/open-logic-ft` of reference-systems. |
| L4 | The website commit of the manifest equals `tools/composer_ref.txt` of the reference-systems release. |
| L5 | A core enters the manifest only when its card on the website is public and it is a source of the catalog. |
| L6 | The hashes in `files` match the files of the snapshots in the wheel, the refs in `bundles` those of the Git bundles, the hashes of `website.schemas` the Composer schemas in `data/schema/`, and the hashes of `data/portal.json` the files of the portal; the wheel has no other files there, and a wheel with snapshots has a portal. |
| L7 | The licence files of every snapshot repository are in the wheel, listed in `license-files`, and their licence is named in the licence expression of the wheel; every file of the portal has a licence in the licence map, which the expression names, and the licence texts of the sites and of their theme packages equal the copies of the package (section 4.4). |
| L8 | The longest path in the wheel stays within the path budget of section 4.5. |
| L9 | The wheel stays below the file size limit of the project on PyPI (section 4.3). |
| L10 | Every core pins the same UVVM commit; it is the UVVM of the manifest. |
| L11 | No file of the portal loads a resource from another origin (images, scripts, style sheets, fonts, fetches), every link to a path of the portal resolves (in the pages and in the documentation links of the Composer catalog), the website has no path where a documentation site goes, and every documentation site with the glightbox plugin has glightbox anchors (section 8). |
| L12 | Every core that a bench component of the package instantiates is pinned at a release the component works with: OpenFibre v0.1.3 or a later release, whose `Phy` interface carries the receiver reset signals that the SpaceFibre far end joins (section 6.3). |

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
    data/portal.json                    inputs, SHA-256 and licence of every file of the portal (section 8)
    templates/                          templates of the generated project (MIT)
    hdl/<id>/...                        source snapshots of the cores, Open Logic FT and reference-systems
    hdl/uvvm/...                        UVVM components of the system testbenches, with UVVM's licence
    osh_tb/                             bench components of the package (MIT), library osh_tb (section 6.3)
    portal/                             website, documentation sites, Composer (written by tools/portal.py)
    bundles/<repository>.bundle         Git bundles (see 4.3)
```

The bench components are files of the package in `osh_tb/`, not in `hdl/`: `hdl/` holds only the generated snapshots,
which `tools/snapshot.py` writes and cleans and rule L6 checks. The directory of a snapshot is the id of its repository
in the lock manifest: `openwire`, `openrmap`, `openspp`,
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
| Portal, measured on website 95282c0 and the catalog pins, after the drops of section 8: the website 4.0 MiB, Open Logic FT 31.8 MiB (17.8 MB PNG images of its documentation), each core 3.0 to 5.5 MiB | 60.6 MiB | 22.6 MiB (Open Logic FT 16.9 MiB) |

The package is one wheel with all of it, about 50 MB at the current pins (the evidence wheel without the portal has
27.2 MiB), so that one file brings everything to a machine without network. It is below the default PyPI limit of
100 MB per file and grows by about 5 to 8 MB with every new core (sources, bundle, documentation). The build checks
the size of the wheel against the file limit of the project on PyPI (rule L9); before the wheel reaches it, the
limit is raised on request at PyPI.

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
| Code of the website and the Composer, with its catalog, examples and schemas; its style sheets | MIT |
| Pages of the website (the MIT layouts with the texts) | MIT AND CC-BY-4.0 |
| Images of the website (`assets/img/`, apart from the logo files) | Creative Commons Attribution 4.0 |
| Logo, favicon and touch icon of Open Space HDL: on the website `assets/img/logo-horizontal-inverse.svg`, `assets/img/social-preview.png`, `favicon.svg`, `favicon.ico`, `apple-touch-icon.png`; in every documentation site `assets/images/logo.svg`, `assets/images/favicon.svg` | All rights reserved; no licence is granted |
| Fonts (Sora, JetBrains Mono), each with its licence file | SIL Open Font License 1.1 |
| Pages, search index and diagrams of a documentation site, its style sheet `brand.css` | the licence of the core |
| Icons that the theme inlines into every page of a documentation site | Font Awesome Free: CC-BY-4.0 (each icon carries its attribution); Material Design Icons: Apache-2.0 |
| Scripts and style sheets of the theme (mkdocs-material, with lunr, escape-html and clipboard.js, whose notices are inside the files) and of glightbox | MIT |

For the portal, rule L7 works with the licence map `tools/portal/licences.json`: its entries are path patterns with
a licence, in order, and the first pattern that matches a file decides. An entry without a licence matches the places
of third-party files (`assets/` of a site) after the known ones, so that a new file there stops the build, as a file
that matches no entry does. Every licence of the map is named in the expression of the wheel, and the licence texts
of the sources (the website's `LICENSE` and `LICENSE-CONTENT`, the font licences, the licence files of the theme
packages in the build environment) must equal the copies in `src/openspacehdl/licenses/` byte for byte. The logo
files have `LicenseRef-OpenSpaceHDL-Logo` and the notice `OpenSpaceHDL-Logo.txt`, which states the reservation; the
cores carry the logo in their documentation sites as well, and the reservation holds there too. The expression of the
wheel is `MIT AND LicenseRef-PSI-HDL-1.0 AND Apache-2.0 AND CC-BY-4.0 AND OFL-1.1 AND LicenseRef-OpenSpaceHDL-Logo`.
The Git bundles carry the licence files of their repositories in their trees.

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
  `openspacehdl[vunit]`, `vunit_hdl>=4.7.1,<5.1`: a release of the 5.0 development line comes with an explicit pin
  (`vunit_hdl==5.0.0.dev7`), because pip takes a development release only when it is named.

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
- an external interface has a type that the generator has no bench component for, or is an AXI4 slave, which a later
  version serves with the UVVM AXI4 VVC (section 6.3);
- the generated testbench cannot serve the system (section 6.3): an RMAP target that is not reached over a link the
  generator can trace, a link that does not start by itself and whose register file is not an external port, a clock
  of a far end that is not a clock port of the system.

### 6.2 Generated project

```text
<dir>/
    <system>.composer.json        the saved file (copied)
    hdl/                          the export, copied: top level, compile order, constraints, address map, regs.h
    sim/run.py                    seed: VUnit entry point, calls openspacehdl.add_system
    sim/tb/<system>_th.vhd        generated: harness
    sim/tb/<system>_th_pkg.vhd    generated: constants and procedures of the system, the smoke and stream tests
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

The harness `<system>_th.vhd` instantiates the system, the UVVM engine and, for every external port of
`resolved.ports`:

- a clock generator for every port of kind `clock`, with the period derived from `frequencyHz` of its clock domain,
  and for the reference clock pin of a SpaceFibre adapter, with the frequency of the adapter's lane clock;
- the reset for the port of kind `reset` (asynchronous, high-active), driven by the testbench (`osh_reset`, 16 cycles
  of the slowest clock);
- a bench component of the library `osh_tb` for every external interface, chosen by the interface type. The type
  comes from `port.interface` through `resolved.instances[].block` to `catalogSubset.blocks[].interfaces[]`; the
  clock of a VVC is the clock port of the system behind the clock of the interface.

| Interface type | Role at the system | Bench component |
| --- | --- | --- |
| `axi4lite` | slave | `osh_tb_axilite_master`: the UVVM AXI4-Lite VVC (32-bit data) |
| `axi4` | master | `osh_tb_axi_mem`: the AXI4 memory responder of the package (16 KiB from address 0, initial data `osh_mem_byte(address, 1)`) |
| `axi4` | slave | refused in this version; a later version adds the UVVM AXI4 VVC |
| streams (`spp.tx`, `byte.stream`, `c123.samples`, ...) | sink | `osh_tb_axis_master`: the UVVM AXI4-Stream VVC, transmitter; data of a width that is not a multiple of 8 is padded to whole bytes, which the UVVM BFM needs |
| streams (`spp.rx`, ...) | source | `osh_tb_axis_slave`: the UVVM AXI4-Stream VVC, receiver |
| `spw.ds` | pins | `osh_tb_spw_far_end`: an `owr_core` and an RMAP initiator, the lines joined crosswise |
| `spfi.serial` | pins | `osh_tb_spfi_far_end`: an `ofb_core` with `ofb_pa_gty` (architecture `mdl` in GHDL, control record 1 + k of the model for far end k) and an RMAP initiator through an `spp_nchar` on the virtual channel of the system's RMAP target, with the lane count and the virtual channels of the system's port and the other settings at their defaults, lane i to lane i |

Inputs that no component drives are held idle.

The far ends are the second port at the other end of a link, built from the family's own cores; the SpaceFibre far
end follows the far end of the reference systems. Each starts its link itself (LinkStart and AutoStart, LaneStart and
AutoStart) and reports `LinkUp` from its own register file (OpenWire `PORT_STATUS.LINK_STATE` = Run, OpenFibre
`DL_STATUS.LINK_STATE` = Link Initialised). Its RMAP initiator `osh_tb_rmap_initiator` is an `omap_core` with the
Initiator only (one outstanding command, reply timeout 1 ms); the testbench sends it commands through the records of
`osh_tb_pkg` (`osh_rmap_read`, `osh_rmap_write`, `osh_rmap_check_word`). The generator traces the link of an RMAP
target through `connections`: the target's `S_Pkt` directly on `M_Pkt` of an `owr_core`, or on an `spp_nchar` whose
`S_Link` comes from `M_Vc[k]` of an `ofb_core` whose `Phy` goes to an `ofb_pa_gty` with external pins (virtual
channel k). In every Composer example and reference system with a SpaceFibre link the target is on virtual channel 0.

The SpaceFibre far end joins its `ofb_core` and its `ofb_pa_gty` as the Composer export joins them in a system, with
the receiver reset signals of the `Phy` interface (OpenFibre v0.1.3 or a later release, rule L12). It stands for a
remote end with the settings of the standard: its core and its adapter keep their defaults (the initialisation timeout
of 5000 words of ECSS 5.5.2.6b.1 and the receiver reset gap of 400000 cycles of the free-running clock), whatever the
system's port sets. A link of the testbench thus pairs a port with the settings of its board and a remote end that
follows the standard, as a link to such a device does in hardware.

The far ends carry user packets as well. The initiator of the SpaceWire far end passes every packet that is not an
RMAP reply to its user port (`Passthrough_g`); the SpaceFibre far end has a user port at every virtual channel other
than the one of the RMAP initiator. Both put the packets they receive into the receive queue of their far end
(`Index_g`) and virtual channel in `osh_link`, the shared variable of `osh_tb_linkvar_pkg` (protected type of
`osh_tb_link_pkg`, end of packet or error end per packet), and send the packets of the transmit queue. The procedures
of `osh_tb_stream_pkg` use the queues: `osh_link_send`, `osh_link_wait` and `osh_link_check` (length, end of packet
and every byte, one error at the first byte that differs), the packet formats `osh_cptp_header` and
`osh_space_packet`, and `osh_link_check_chunks` for the chunks of a chain.

`add_system` adds `osh_tb` (`openspacehdl.add_osh_tb`) and with it UVVM and the cores the far ends instantiate
(OpenWire, OpenRMAP, OpenSPP and OpenFibre with the model of its adapter), also when the system does not use them.

The harness package `<system>_th_pkg.vhd` holds the constants of the system (clock periods, the number of far ends and
the time each may take for its link), the signals between the testbench and the harness (`osh_rst`; per far end the
RMAP command and result and the link state: `osh_rmap_cmd`, `osh_rmap_res`, `osh_link_up`), the test keys of the
stream test and the procedures `osh_reset`, `osh_bring_up` (the reset, the link starts and every link up),
`osh_smoke_test`, `osh_stream_test` and `osh_image_test`. The seed testbench `<system>_tb.vhd` is a VUnit runner with
UVVM. It starts with `osh_test_start` (the UVVM engine ready, the log of positive checks off, and off the warning
UVVM raises once when a time stamp of the log has more decimals than it shows, which the 156.25 MHz lane clock of
SpaceFibre causes and which says nothing about the system). Its first test case `test_smoke` calls
`osh_smoke_test(osh_rst, AXILITE_VVCT, osh_rmap_cmd, osh_rmap_res, osh_link_up)`, its second `test_streams` calls
`osh_stream_test(osh_rst, AXILITE_VVCT, AXISTREAM_VVCT, osh_link_up)`, the same calls for every system. Its
test end `osh_test_end` fails on unexpected alerts and on expected alerts that did not occur: it compares the counters
of every alert level from WARNING to TB_FAILURE itself and ends a mismatch with an assertion of severity failure. A
test end that signals a mismatch with `alert(TB_ERROR)` cannot stop a test that raised the TB_ERROR stop limit (a
negative test with `increment_expected_alerts_and_stop_limit`), and VUnit then passes it.

The smoke test:

1. holds the reset for 16 cycles of the slowest clock and releases it;
2. starts the links that do not start by themselves. An OpenWire port whose `LinkStart_g` and `AutoStart_g` are false
   (every SpaceWire example of the Composer) gets `PORT_CTRL` = AutoStart, driver and receiver enabled through its
   register file: the programming sequence of OpenWire, which the software of the system must follow as well; the
   README of such a project says so. `new` refuses a port that does not start and whose register file is not an
   external port, and a SpaceFibre port with `LaneStart_g` and `AutoStart_g` false;
3. waits until every far end reports its link up, with a timeout of 5 ms;
4. reads the ID register of every register bank of the address map (offset and value from
   `catalogSubset.blocks[].idRegister` and `resolved.addressMap`) and compares it with the expected value:
   - a bank in an address space of kind `port` through the AXI4-Lite VVC of that port;
   - a bank behind an RMAP target (an address space of kind `master` at the target's memory interface) with an RMAP
     read from the far end of the link that carries the target (Target Logical Address `La0_g` and key `Key_g` of the
     target);
   - a bank without an ID register with a read of its base address that must answer OKAY (with RMAP: status 0);
5. for every RMAP target whose memory interface is external (`osh_tb_axi_mem`): writes 16 bytes with RMAP from 4 bytes
   before a 4 KB boundary (address 0x0FFC) over memory filled with `osh_mem_byte(address, 1)`; the values,
   `osh_mem_byte(address, 2)`, depend on every address bit. It reads them back with RMAP and checks through the
   backdoor of the memory responder that the window holds them and the 16 bytes on each side are unchanged. The
   target has to split its burst at the boundary;
6. waits for the completion of the AXI4-Lite commands; the test end then fails on any alert.

The examples have register banks behind their ports; the reference systems reach theirs only over the SpaceFibre link,
so step 4 runs with RMAP there. The four examples whose RMAP target has an external memory get step 5, so that the far
end and its initiator are exercised beyond the link start in every system with a target.

The stream test:

1. brings the system up as steps 1 to 3 of the smoke test (`osh_bring_up`);
2. waits 2100 cycles of the clock of every `spp_core` of the checks: its APID tables are ready 2048 cycles after the
   reset;
3. lets the AXI4-Stream VVCs wait for a handshake as long as a chunk of a chain may take (`max_wait_cycles`): the links
   pace the streams. `await_completion` with 1 ms bounds every packet, 20 ms every chunk;
4. loads a test key into slot 0 of every `ocr_core` of a chain, with generated IVs (step 3 of the programming sequence
   of OpenCrypto), and checks that `STATUS.BUSY` is '0'. The keys are published test vectors, declared in the harness
   package as test values, not for use in a mission: for AES-128 the key of test case 3 of the GCM specification, for
   AES-192 and AES-256 the keys of NIST SP 800-38A, F.1.3 and F.1.5; the fixed field 0xCAFEBABE and the first
   invocation counter 0xFACEDBADDECAF888 are the IV of GCM test case 3. A test of the package encrypts with each key
   (an AES of the test, FIPS 197) and compares the result with the published ciphertext or hash subkey;
5. checks the paths through OpenSPP exactly, at every `spp_core` in the configuration the checks know (CPTP layer,
   Octet String Service at every port, APID paths enabled at the reset) whose link has a far end:
   - at every send port `S_Tx[k]` two SDUs of 7 and 301 bytes with APID 0x100 + k; the far end must receive each as a
     CPTP packet (`FE 02 00 00`, the reset value of `DEST_CTRL`) with the Space Packet (telemetry, no secondary
     header, unsegmented, sequence count 0 and 1), byte for byte;
   - at receive port 0: the far end sends two Space Packets with SDUs of 5 and 259 bytes, APID 0x200 and the CPTP User
     Application value 0x5A to the `Tla_g` of the core; the port must deliver each SDU with the user field APID and
     User Application value;
   - the data of every packet is `osh_mem_bytes` with its own seed, so it does not repeat with a short period;
6. checks the framing of every processing chain from a byte stream that ends in `ocr_framer` and `ocr_core` (dense
   output) at a send port of an `spp_core` with a fixed APID:
   - into the framer input one message of `ChunkBytes_g` + 259 bytes (4355 bytes with the default): not a multiple of
     16 and longer than one chunk;
   - the far end must receive the chunks as CPTP packets with Space Packets of the APID of the port, counted from 0,
     each with the IV (fixed field, invocation counter + chunk number) and the AAD (the position in bits 7:6 of its
     first byte, every other bit '0'); for the message also the position and length of every chunk and their number;
   - the check ends at the chunk marked last and would take one chunk more, so the position ends it, not the limit;
   - the check does not decrypt: the ciphertext and the tag are not checked (the bench has no AES-GCM model; OpenCrypto
     verifies them in its own regression);
7. reads the counters of every `spp_core` and `ocr_core` of the checked paths through their AXI4-Lite ports:
   `TX_PACKETS` the SDUs sent plus the chunks, `RX_PACKETS` the packets received, `ENCRYPTIONS` the chunks, every error
   counter 0;
8. waits for the completion of the VVCs; the test end then fails on any alert.

A chain from a compressor (`ocp_core`) has a test case of its own, `test_image_stream` (`osh_image_test`), which the
seed testbench has only for a system with such a chain. It brings the system up as the stream test does, loads the
test key and sends one image of `XSize_g` x `YSize_g` x `ZSize_g` samples (`osh_samples`, 8192 samples per VVC command,
every sample depending on every bit of its index); the far end must receive its chunks with the checks of step 6 up to
the last chunk of the image, with at most `ChunkBytes_g` bytes per chunk; then the counters of its cores. The image
takes hours to simulate in GHDL: with samples that depend on every index bit the compressed image is nearly as large
as the input, and the SpaceWire link of the example carries it at about 200 ns per sample, about 50 ms of simulated
time for the image. The README of such a project says so and shows the run without it; the system tests of the
package (section 9) run `test_smoke` and `test_streams`.

A stream the checks do not serve stays idle, and the README of the project says why (another configuration of the
`spp_core`, a receive port other than 0, a chain the generator does not know, a register file that is not an external
port). For a system without a stream the test serves, `osh_stream_test` and `osh_image_test` only log this.

The bench components have unit benches of their own (`tests/hdl/`, VUnit and UVVM in GHDL, run by
`tests/test_osh_tb_hdl.py` with `OPENSPACEHDL_HDL_TESTS=1` on an installation with snapshots): the memory responder with
every burst type and the alerts of the AXI4 rules, the initiator against an `omap_core` target, each far end against a
second port in the place of the system; each with negative tests (a wrong key gives the status "invalid key", a dead
link the timeout), so that the smoke test cannot pass with a far end that never answers. The far end benches send user
packets of several lengths between RMAP transactions and check them at the other end; a changed byte must give one
error, a packet that never arrives the timeout.

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
- `/` is the website, `/<repository>/` the documentation of each core and of Open Logic FT at its pinned commit,
  `/composer/` the Composer with the catalog of the lock, so that a file saved there matches the pins of the package;
- the Composer fetches its catalog and examples by relative URL and needs `http://` rather than `file://`, which is
  why the package serves the files instead of opening them;
- the default port is 8765. The Composer keeps its workspace in the storage of the browser, which belongs to the
  address with its port: the same port finds the same workspace again, another port starts with an empty one, and
  the online Composer has a workspace of its own. Work moves between them as a saved file. `serve` says so when it
  starts, and refuses a port that is in use;
- it sends the media types of the portal itself (on Windows the registry can map `.js` to `text/plain`, and a browser
  does not run a module script of that type) and lists no directories;
- links to GitHub and to other sites stay links and need network.

`tools/portal.py` builds the portal for the wheel (the step after the snapshots), in clones at the pinned commits
that check out without line-end conversion, so that every host writes the same files:

- the website with Jekyll and the gem set of GitHub Pages (`tests/jekyll/Gemfile` of the website) at the website
  commit of the lock, with the gem versions of `tools/portal/Gemfile.lock`;
- each documentation site with MkDocs from `tools/docs/` of its repository (`tools/ft_docs/` in Open Logic FT) at the
  pinned commit, with the requirements of the repository and the versions of
  `tools/portal/constraints/<repository>.txt`, in a virtual environment of the Python version that the documentation
  workflow of the repository names (3.12 when it names none). The build stops when the constraints do not pin every
  installed package; `--pin` writes the Gemfile.lock and the constraints from a fresh resolution, for a change of the
  pins.

Then it drops the source maps, the language files of the search (`assets/javascripts/lunr/`: every site searches in
English, and the search loads these files only for other languages; they come without licence files) and `CNAME`. It
rewrites the links between the sites: a link to `https://openspacehdl.org/<path>` that the portal serves becomes
`/<path>`, a link to `/<path>` outside the portal becomes `https://openspacehdl.org/<path>` (the OpenDMA card,
whose core is not in the lock), and a link to a missing page of a site of the portal stays and fails rule L11. It
removes the third-party status badges that two pages of Open Logic FT 4.7.0-ft.8 still load. Rule L11 (section 3.3)
and the licence map (section 4.4) then check the result, and only a portal that passes replaces
`openspacehdl/portal/`. `data/portal.json` records the inputs (the website commit, per site its commit, its
configuration directory, its Python version and the hash of its constraints) and the SHA-256 and licence of every
file; the wheel check compares the wheel with it (rule L6).

The documentation links of the Composer come from the field `doc` of the catalog. From catalog 75d78f7588f4 (website
8fa23f0, generator 0.9.9-beta) on they are paths of the site, so they stay in the portal, and rule L11 checks that
each resolves; the files the Composer saves still name the full address. An older catalog has full addresses, which
leave the portal; the portal never rewrites the catalog, whose id is the hash of its content. The removal of the
status badges of Open Logic FT ends once its documentation strips them itself.

## 9. Test strategy

| Level | What | Simulator or tool |
| --- | --- | --- |
| Unit | Lock generation and the rules L1 to L6, L10 and L12 with consistent and inconsistent fixture sets; every refusal of section 6.1; the interface type mapping; the update table of section 6.4; `add_core` and its errors against a recording stand-in of the VUnit object; `serve` on an ephemeral port of 127.0.0.1 with its media types; `export` as a tree and with `--git`; the post-processing of the portal, the checks of L11 and the licence map on small trees, and the portal build with the website and documentation builds replaced by fixture sites | pytest |
| Mutation | Each refusal and each update rule is proven by a mutation of the package that makes a test fail; a system file with a wrong ID value makes the smoke test fail | pytest, GHDL |
| Cores | `add_core` of every core, alone and all in one project, compiles in GHDL | GHDL through VUnit |
| Systems | Every example of the Composer (seven at the website commit of the lock) and the systems of the reference-systems release: `new`, then `python sim/run.py`, the smoke test and the stream test pass; `update` right after `new` changes nothing | GHDL through VUnit |
| Exports | The exports of the examples come from `tools/composer_hdl.mjs` of the website at the commit of the lock; the CI checks with it that the stored exports are current (exit status 0) | Node.js, CI only |
| Portal | `tools/portal.py` builds the website and every documentation site at the pins and passes L11 and the licence map; the installed package serves every site with `serve` | Ruby with Bundler, MkDocs |
| Wheel | Build of wheel and sdist with the rules L7 (licences) and L8 (path budget), `twine check --strict`, install without network into fresh environments on Python 3.10 and 3.14, the commands run | pip, twine |
| Deep install | On Windows, an install into a virtual environment whose `site-packages` path is 120 characters long; from there `add_core` of every core compiles in GHDL and one system passes its smoke test | pip, GHDL |
| VUnit versions | The core and system levels with VUnit 4.7.1 and with VUnit 5.0 | VUnit |

The tests run on Windows and Linux. The workflow CI runs the unit level on both, the exports level, and the bench
components of the system testbench in GHDL on every pull request (open point O6). Phase A is complete when every
level passes.

## 10. Out of phase A

- Builds for FPGA boards: Vivado for the VCK190 (phase B, section 10.1), Libero for a PolarFire board (phase C).
- Simulation of generated projects in xsim or QuestaSim; phase A runs GHDL.
- The testbenches of the cores and their regression.
- Resolving a system without the Composer, or a port of the Composer's generator.
- Cores that are not public, not released or not in the catalog (today Open1553, OpenCAN, OpenDMA).
- An override of the Open Logic rule of `add_core`.
- `serve` on another address than 127.0.0.1, and any authentication.
- The move of the tools and the board data of reference-systems into the package; reference-systems becomes their
  first consumer later. The move starts after the hardware bring-up of the reference systems.
- Publishing through GitHub Actions with Trusted Publishing. The repository is public; the publishing workflow and the
  trusted publisher on PyPI come later, with the maintainer.

### 10.1 Board targets (phase B)

The package carries the board targets; the Composer does not. The Composer file format stays as it is: a saved system
names no board, and the Composer has no board catalog, no pin assignment and no vendor files.

**Board data.** One directory `openspacehdl/targets/<board>/` per board, taken from the hardware-tested targets of
reference-systems (today `systems/<system>/targets/vck190/` of each system):

- the part (VCK190: `xcvc1902-vsva2197-2MP-e-S`) and the connector pins;
- the variants of the transceiver reference clock with their pins and frequencies (VCK190: the Si570 or the 8A34001,
  at 100 or 156.25 MHz);
- the fragment of the processing system that every design of the device family needs (Versal: the CIPS block design
  with the programmable logic clock and its reset);
- a template of the board top level (reset generator, clock buffers, the CIPS switch `IncludeCips_g` around the top
  level of the Composer export) and a template of the build script (steps project, rtl, synth, impl and all, the
  check of constraints that do not apply, the results directory).

The GT wizard Tcl of a transceiver adapter stays with its core (`hdl/ofb_pa_gty/tcl/ofb_gtw.tcl` of OpenFibre): the
build script calls it from the OpenFibre snapshot of the package. Today every target of reference-systems repeats the
board data; in the package it exists once per board. The board data carries the licence of its source in
reference-systems, the PSI HDL Library License 1.0, which rule L7 checks like the snapshots.

**Command.** `openspacehdl new <system>.composer.json [<dir>] --target <board>` writes the project of section 6.2 and
the directory `build/<board>/`:

- generated: the board top level and the build script, from the board data, the Composer export and the clock
  domains of the saved file;
- seed: the assignment of the external interfaces of the system to the connectors of the board, for example the lanes
  of `spfi.serial` to a QSFP cage and `spw.ds` to an FMC connector. The integrator checks and edits it; `update`
  never changes it and regenerates the generated files from it.

The project manifest records the target. `new` and `update` refuse, with every reason and before writing anything, an
assignment the board cannot carry: an interface type for which the board has no connector, more lanes than the
connector has, more interfaces on a connector than it has room for, an interface without a connector or a connector
the board does not have.

**Source and maintenance.** Until the move of the reference-systems tools, the package takes the board data from the
reference-systems release that the lock pins (`referenceSystems`, section 3.1). After the move the board data lives in
the package and is maintained there; reference-systems consumes the package, and its targets become projects of
`openspacehdl new --target` with the seed assignment committed. A new board is brought up in reference-systems first,
and its board data then goes into the package.

**Evidence.** pytest for the generated files, the seed assignment, the refusals and the update rules, each proven by a
mutation. On a host with Vivado, the build script runs the steps project and rtl in batch for every system with the
board, and the generated targets of the reference systems give the same part, pins and constraints as their
hand-written targets in reference-systems. Synthesis, implementation and the hardware tests run on the build host, as
reference-systems runs them today.

**Steps of phase B.**

1. The board data of the VCK190 in the package, from the reference-systems release of the lock.
2. `new --target` and `update` for `build/<board>/`, the seed assignment and its checks.
3. The Vivado batch evidence and the comparison with the targets of reference-systems.
4. The move of the reference-systems tools and board data into the package, after the hardware bring-up.

Libero and a PolarFire board form a second board family (phase C).

## 11. Open points

| ID | Point | State |
| --- | --- | --- |
| O1 | Distributions: one wheel or three (section 4.3). | Decided: one wheel with the snapshots, the Git bundles and the portal; the bundles keep the history up to the pinned tag. |
| O2 | The first version with content needs a consistent set. With website 3e0f04b and reference-systems v0.1.0, `tools/lock.py --report` finds rule L2 broken for OpenFibre and OpenCompact (catalog v0.1.1, reference-systems v0.1.0) and rule L4 broken (reference-systems v0.1.0 was checked against website f6715ee). | Decided: the first version with content is built on the next reference-systems release that carries the catalog pins. |
| O3 | `resolved.version` of the Composer is decided but not yet written into saved files. | Decided: the Composer writes it from generator 0.9.8-beta on; the package refuses an unknown version. For files of older generators it validates against the schema and warns on a generator version it was not tested with. |
| O4 | Which virtual channel of a SpaceFibre link carries the RMAP target. | Decided: traced in the resolved netlist from the target to the port; `new` refuses when it cannot. |
| O5 | The documentation sites are built at the tags of the cores, with their own MkDocs toolchains. | Decided: every site is built in its own environment with the requirements of `tools/docs` of the repository at its pin (`tools/ft_docs` in Open Logic FT), the constraints of the package for what they leave open, and the Python version of the documentation workflow of the repository (section 8). |
| O6 | Linux tests while the repository was private and had no CI. | Decided: the workflow CI (`.github/workflows/ci.yml`) runs on every pull request and on `main` and `develop`: the gates of `tools/check.py` without markdownlint (pytest, no em-dash) on Linux and Windows with Python 3.10 and 3.14, markdownlint, the family data against the website, the exports level, and the bench components in GHDL with VUnit 4.7.1 and 5.0.0.dev7 on a lock of the website commit the workflow names (L2 and L4 waived until open point O2 is closed). The offline install and a system of the systems level on Linux stay steps of the release checklist. |
| O7 | The website repository has no licence file, so the licence of the website content and of the Composer in the portal is not stated. | Decided: MIT for the code, CC BY 4.0 for the texts and images; logo, favicon and touch icon stay all rights reserved; third-party fonts and assets keep their licences (section 4.4). The website carries the licence files since b124129, and the portal is in the wheel. |
| O8 | Where the board data of a build target lives: in the Composer file and its catalog, or in the package. | Decided: in the package (section 10.1); the Composer file format is unchanged, and `new --target <board>` writes `build/<board>/` with a seed assignment of the interfaces to the connectors. |
| O9 | The source distribution of a version with content carries the snapshots, the bundles and the portal like the wheel (48.8 MiB at website 8fa23f0 and reference-systems v0.1.0). The wheel is `py3-none-any` and installs on every platform; every uploaded file counts against the storage limit of the project on PyPI. | Open: whether a release uploads the source distribution beside the wheel; decided at the first content release (release checklist, [release.md](release.md)). |
