# openspacehdl

Python package of [Open Space HDL](https://openspacehdl.org), a family of open-source VHDL IP cores for spacecraft
on-board data handling.

> **0.1.0rc2 is a preliminary build** for the first hardware tests of the spfi_compress reference system. It is built
> from development commits, not from releases:
>
> - reference-systems 1c1976ef4b93;
> - the Composer catalog fd594297bc51 of website commit fb1823aaa9c7;
> - OpenCompact dd94c8395a81.
>
> It is not published on PyPI. Install it from the wheel of the GitHub pre-release v0.1.0rc2:
> `pip install openspacehdl-0.1.0rc2-py3-none-any.whl`. Its lock manifest waives the rule that every pin is a release
> tag, so every `openspacehdl` command needs the environment variable `OPENSPACEHDL_ALLOW_WAIVED=1`: in cmd
> `set OPENSPACEHDL_ALLOW_WAIVED=1`, in PowerShell `$env:OPENSPACEHDL_ALLOW_WAIVED = "1"`.
>
> Unlike 0.1.0rc1, it carries the portal: `openspacehdl serve` serves the website, the Composer with this catalog and
> the documentation of every core at its pinned commit on `http://127.0.0.1:8765/`, also without network. The formal
> 0.1.0 follows with the released versions; it is the first upload to PyPI.

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
(`openspacehdl lock` shows them), and adds them to a VUnit project. The optional dependency `vunit` installs VUnit
with it, in a version the package is tested with (4.7.1 up to the 5.0 line):

```shell
pip install "openspacehdl[vunit]"
pip install "openspacehdl[vunit]" vunit_hdl==5.0.0.dev7   # the 5.0 development line, named explicitly
```

The source archive of VUnit 5.0.0.dev7 builds only with `setuptools<81` and `setuptools_scm>=8` installed first and
`--no-build-isolation`.

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
with its harness. The harness puts a bench component at every external interface (UVVM VVCs, an AXI4 memory, and at
every SpaceWire or SpaceFibre link a far end with an RMAP initiator). The smoke test brings the links up and reads
the ID register of every register bank; the stream test sends packets through OpenSPP and its processing chains and
checks them at the far ends. `openspacehdl update` regenerates the generated files after a change of the
system and never overwrites a file the integrator changed.

`openspacehdl serve` serves the website, the Composer and the documentation of every core and of Open Logic FT, at
the versions the package pins, on `http://127.0.0.1:8765/`, also without network (`--port` chooses another port,
`--no-browser` does not open the browser). The Composer keeps its workspace in the browser storage of that address:
on another port, and on openspacehdl.org, it starts with an empty one, and a saved file moves the work.

## Offline use (from the first version with cores)

A version with cores brings what a machine without network access needs in its one wheel: the sources of the cores,
Open Logic FT and UVVM at the pinned versions, their Git history, and the portal with the Composer. VUnit and GHDL
are not part of it.

On a machine with network access, collect the wheels in one directory. VUnit is published as a source archive only;
`pip wheel` takes the wheel of the package and builds one of VUnit, with its dependency:

```shell
pip wheel "openspacehdl[vunit]==<version>" -w wheels
```

Copy the directory to the machine without network and install from it alone:

```shell
pip install --no-index --find-links wheels "openspacehdl[vunit]"
```

Install GHDL on that machine as well and put it on the `PATH`, where VUnit finds it. Then, still without network:

1. `openspacehdl serve` opens the portal on `http://127.0.0.1:8765/`: the website, the Composer and the documentation
   of every core, at the versions of the package.
2. In the Composer, compose the system, save it and use Export HDL. It downloads `<system>_hdl.zip` with the top
   level, its compile order, its constraints and the system file; unpack it into one directory.
3. `openspacehdl new <directory>/<system>.composer.json <project>` writes the project, and `python sim/run.py` in
   the project runs its tests in GHDL.
4. `openspacehdl export <dir> --git` writes the sources as Git repositories, for a build machine.

The Composer of the portal uses the block catalog of the website commit the package pins, so a system saved with it
has the pins of the package and `new` accepts it. A system saved on openspacehdl.org after a newer release of a core
may pin other versions; `new` then refuses it and names the package version whose pins match, if one is known.

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

`tools/portal.py` builds the portal into `src/openspacehdl/portal/` (not tracked): the website with Jekyll (Ruby
with Bundler) and every documentation site with MkDocs in the Python version of its documentation workflow
(`--python <version>=<interpreter>`), at the gem and package versions of `tools/portal/`; it checks rule L11 and the
licence map `tools/portal/licences.json`. `--pin` writes those versions afresh.

`python tools/check.py [--site <clone of open-space-hdl.github.io>]` runs the quality gates (pytest, markdownlint,
no em-dash, family data) and fails on the exit status of the first gate that fails. `python tools/check.py
--real-build ...` builds and checks a wheel with content from a copy of HEAD, on demand. The workflow CI
(`.github/workflows/ci.yml`) runs the gates on Linux and Windows, checks the stored Composer exports of the tests and
runs the bench components in GHDL on every pull request.

[docs/release.md](docs/release.md) is the checklist of a release.

## Licence

The package is released under the [MIT License](LICENSE). The IP cores of the family have their own licence (PSI HDL
Library License), stated in each repository. The portal carries the website (code under MIT, texts and images under
CC BY 4.0, the Open Space HDL logo with all rights reserved), the fonts under the SIL Open Font License, and the
documentation sites under the licences of their repositories and of their theme; section 4.4 of
[docs/design.md](docs/design.md) lists them, and `src/openspacehdl/licenses/` has every licence text.
