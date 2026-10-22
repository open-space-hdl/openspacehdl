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

## 0.0.1 - 2026-10-22

### Added

- `openspacehdl --version` and `openspacehdl info [project]`: the projects of the family as the website shows them
  (website commit 1b3d619).
