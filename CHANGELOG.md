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
- The Composer schemas in the package: `tools/lock.py` writes `system-1.json` and `system-2.json` of the website
  commit of the lock to `data/schema/` and records their SHA-256 in the manifest; `tools/wheel_check.py` checks
  them (rule L6).

### Fixed

- The UVVM snapshot follows the compile order of each component and carries the target-dependent files of the VVC
  framework (it had only the `src/` directories).

## 0.0.1 - 2026-10-22

### Added

- `openspacehdl --version` and `openspacehdl info [project]`: the projects of the family as the website shows them
  (website commit 1b3d619).
