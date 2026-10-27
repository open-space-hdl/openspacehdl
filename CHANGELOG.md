# Changelog

All notable changes of the package. Versions follow [semantic versioning](https://semver.org).

## Unreleased

### Added

- Lock manifest model and consistency rules (`openspacehdl.lock`), `tools/lock.py` to write and check the manifest,
  and `tools/check.py` for the quality gates. No package version carries a manifest yet.
- Source snapshots: the manifest lists every snapshot file with its SHA-256; `tools/snapshot.py` writes the
  snapshots, `tools/wheel_check.py` checks a wheel (rules L6 to L9), `tools/check.py --real-build` builds one.
- The licence expression of the package covers the bundled content: `MIT AND LicenseRef-PSI-HDL-1.0 AND Apache-2.0`,
  with the licence texts in `src/openspacehdl/licenses/`.
- `openspacehdl.add_core(vu, core)` and `openspacehdl.add_uvvm(vu)` for VUnit, with the errors `UnknownCoreError`,
  `OpenLogicConflictError` and `LibraryConflictError`; `openspacehdl lock` shows the lock manifest.

- Git bundles of every repository of the lock manifest (the pinned commit with its history and published tags) and
  `openspacehdl export <dir> [--git] [--core <core>]`: the sources as a plain tree, or as Git repositories with
  their submodules, without network.
- `openspacehdl.composer.load()`: reads a saved system of the Composer with its export and refuses it, with every
  reason, when it breaks the schema, has problems or error checks, an unknown layout, an export of another state,
  pins other than the lock manifest or an external interface the generated testbench does not support;
  `openspacehdl.jsonschema` validates the schema keywords the Composer uses.

- `openspacehdl new` and `openspacehdl update`: the project of a system with its inputs, the generated harness and
  its package, the seeds (`README.md`, `sim/run.py`, the testbench) and the manifest of the generated files;
  `openspacehdl.add_system(vu, project)` and `openspacehdl.guard_ghdl_generics()` for the generated `run.py`.
- The bench components of the generated testbench, library `osh_tb` (`openspacehdl.add_osh_tb`): UVVM VVC wrappers for
  AXI4-Lite ports and streams, the AXI4 memory responder `osh_tb_axi_mem` with a backdoor, the RMAP initiator, and
  the SpaceWire and SpaceFibre far ends built from OpenWire, OpenRMAP, OpenSPP and OpenFibre; unit benches in
  `tests/hdl/`. The generated harness instantiates them for every external interface, and `test_smoke` starts the
  links, waits for them, reads the ID register of every register bank (through its port or with RMAP over a link)
  and checks the memory of every RMAP target behind a link. `new` refuses AXI4 slaves and systems whose testbench
  it cannot make.
- The stream test `test_streams` of the generated testbench (`osh_stream_test`): packets through every send port and
  receive port 0 of OpenSPP, checked byte for byte at the far end of its link and at the port; every processing chain
  of `ocr_framer` and `ocr_core` towards OpenSPP from a byte stream, with a published test key, its chunks checked for
  their framing; the packet and error counters of the cores. A chain from `ocp_core` gets the test case
  `test_image_stream` with one full image, which runs for hours in GHDL. The far ends carry user packets
  (`osh_tb_link_pkg`, `osh_tb_stream_pkg`), and the README of the project lists the streams the tests leave idle.
- The Composer schemas in the package: `tools/lock.py` writes `system-1.json` and `system-2.json` of the website
  commit of the lock to `data/schema/` and records their SHA-256 in the manifest; `tools/wheel_check.py` checks
  them (rule L6).
- The portal and `openspacehdl serve [--port <n>] [--no-browser]`: the website with the Composer and the
  documentation site of every core and of Open Logic FT at the pinned commits, served on 127.0.0.1, port 8765 by
  default (the Composer workspace belongs to the port). `tools/portal.py` builds it with Jekyll and MkDocs at
  pinned gem and package versions, drops what the portal does not need, rewrites the links between the sites and
  checks rule L11 (no request to another origin, the links resolve, the diagrams keep their lightbox) and the licence
  map (rule L7); `data/portal.json` lists every file with its hash and licence, and the wheel check compares the wheel
  with it. The licence expression gains `CC-BY-4.0`, `OFL-1.1` and `LicenseRef-OpenSpaceHDL-Logo`.
- The optional dependency `openspacehdl[vunit]`: VUnit in a version the package is tested with
  (`vunit_hdl>=4.7.1,<5.1`; a development release of 5.0 named explicitly).

### Changed

- `tools/check.py --real-build --site-commit <rev>` builds the lock at that website revision, as a release needs it
  for rule L4 (the commit of `tools/composer_ref.txt` of its reference-systems tag); without it, `origin/main`.
- Composer generator 0.9.9-beta (website 8fa23f0) is a tested generator: `new` reads its files without the warning
  of an untested generator version.
- Composer generator 0.9.10-beta (website 60dee6c) is a tested generator, on the evidence of the CI job `systems`.
- Composer generators 0.9.11-beta (website 8a857de) and 0.9.12-beta (website d736063, catalog 13caffc27875 with
  OpenCompact v0.3.0) are tested generators, on the evidence of the CI job `systems`.
- The SpaceFibre far end `osh_tb_spfi_far_end` joins its core and its adapter with the receiver reset signals of the
  `Phy` interface of OpenFibre v0.1.3, as the Composer export joins a system port, and keeps the settings of the
  standard. New rule L12: the lock refuses an OpenFibre older than v0.1.3.
- The package metadata links the source repository (`Repository`), which is public.
- The portal pins follow catalog 955cea8c7666 (Open Logic FT 4.7.0-ft.11, OpenFibre v0.1.4, OpenRMAP v0.1.1): the
  documentation of OpenRMAP builds with selectolax 1.0.0, its own pin; the portal no longer removes images of Open
  Logic FT, which strips its status badges itself.
- The portal pins follow catalog 64a6eb49ec58 (OpenCompact v0.2.0): the documentation of OpenCompact builds with
  selectolax 1.0.0, its own pin.

### Fixed

- The UVVM snapshot follows the compile order of each component and carries the target-dependent files of the VVC
  framework (it had only the `src/` directories).

## 0.0.1 - 2026-10-22

### Added

- `openspacehdl --version` and `openspacehdl info [project]`: the projects of the family as the website shows them
  (website commit 1b3d619).
