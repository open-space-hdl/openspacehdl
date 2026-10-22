# openspacehdl

Python package of [Open Space HDL](https://openspacehdl.org), a family of open-source VHDL IP cores for spacecraft
on-board data handling.

This is an early release. It lists the projects of the family as the website shows them; it does not contain the
cores or any tools yet.

## Install

```shell
pip install openspacehdl
```

The package needs Python 3.10 or later and has no dependencies. On a machine without network access, copy the wheel
and install it from the file:

```shell
pip install openspacehdl-<version>-py3-none-any.whl
```

## Use

```shell
openspacehdl --version          # version of the package
openspacehdl info               # every project of the family: standard, summary, TRL, documentation and source
openspacehdl info OpenFibre     # one project, by name or repository name
```

`python -m openspacehdl` works the same way.

The list comes from the project cards of [openspacehdl.org](https://openspacehdl.org) at the time of the release.
A project that is not yet public is listed as "Coming soon", without links.

## VUnit (from the first version with cores)

A version with cores carries them with Open Logic FT and UVVM at the versions its lock manifest pins
(`openspacehdl lock` shows them), and adds them to a VUnit project:

```python
from vunit import VUnit
import openspacehdl as osh

vu = VUnit.from_argv()
vu.add_vhdl_builtins()
osh.add_core(vu, "openfibre")   # the libraries olo and openfibre
osh.add_core(vu, "openrmap")    # reuses olo
osh.add_uvvm(vu)                # UVVM components, each as its own library
vu.main()
```

Every core of one package version uses the same Open Logic FT; `add_core` refuses a library `olo` that it did not
add itself.

`openspacehdl export <dir>` writes the sources as a plain tree; `openspacehdl export <dir> --git` writes them as Git
repositories with their history up to the pinned releases, without network.

`openspacehdl new <system>.composer.json [<dir>]` writes a project for a system saved by the Open Space Composer and
its export: the inputs, a VUnit simulation (`sim/run.py`, calling `openspacehdl.add_system`) and a system testbench
with its harness. `openspacehdl update` regenerates the generated files after a change of the system and never
overwrites a file the integrator changed.

## Development

The design of the next phase is in [docs/design.md](docs/design.md).

```shell
pip install -r requirements-dev.txt
pip install -e .
pytest
python tools/family_data.py --site <clone of open-space-hdl.github.io> --check
python -m build
```

`tools/family_data.py` writes `src/openspacehdl/data/family.json` from `_data/projects.yml` and
`_data/project_groups.yml` of the website repository; `--check` only compares.

`tools/lock.py` writes the lock manifest `src/openspacehdl/data/lock.json` from the pins of the Composer catalog,
a release tag of reference-systems and the clones of the repositories, and stops when the pins are not consistent;
`--report` lists the violations, `--check` compares.

`tools/snapshot.py` writes the source snapshots of the manifest into `src/openspacehdl/hdl/` and the Git bundles into
`src/openspacehdl/bundles/` (`tools/bundles.py`; both not tracked) and checks their hashes, licences and path
lengths; `tools/wheel_check.py <wheel>` checks a built wheel against the manifest it carries (rules L6 to L9 of
docs/design.md).

`python tools/check.py [--site <clone of open-space-hdl.github.io>]` runs the quality gates (pytest, markdownlint,
no em-dash, family data) and fails on the exit status of the first gate that fails. `python tools/check.py
--real-build ...` builds and checks a wheel with content from a copy of HEAD, on demand.

## Licence

The package is released under the [MIT License](LICENSE). The IP cores of the family have their own licence (PSI HDL
Library License), stated in each repository.
