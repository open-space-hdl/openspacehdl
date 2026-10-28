# Release checklist

This is the checklist of a version of openspacehdl with content (the cores, their Git history and the portal), first
0.1.0. Every step is judged by its exit status, and a reported result names the completed run it comes from. The
sections of [design.md](design.md) define the rules and the test levels this checklist refers to.

## 1. Inputs

The lock manifest of a version comes from one website commit and one release tag of reference-systems (design.md,
section 3). A release branch starts only when:

- every repository the catalog pins is at a published release tag (rule L1);
- reference-systems has a release tag whose submodules carry the catalog pins (rule L2) and whose
  `tools/composer_ref.txt` names the website commit of the lock (rule L4). For 0.1.0 this is the reference-systems
  release after the OpenFibre release and the catalog pin it waits for (open point O2);
- `python tools/lock.py --site <website> --site-commit <commit of composer_ref.txt> --refsys <reference-systems>
  --refsys-tag <tag> --repos <dir> --report` lists no violation, with clones that have the tags of their remotes;
- the generator version of the Composer at that website commit is in `TESTED_GENERATORS`
  (`src/openspacehdl/composer.py`). A version joins it in the pull request that moves the pins of the workflow CI to
  a website commit with that generator, after the CI job `systems` of that pull request passed with files written by
  it; that job, not a local run, is the evidence of a generator version;
- the pins of the portal still apply: `tools/portal.py` builds against `tools/portal/Gemfile.lock` and
  `tools/portal/constraints/`. A changed `tests/jekyll/Gemfile` of the website, or a changed requirements file of a
  documentation site, needs a run with `--pin` and a review of its changes in a pull request to `develop`.

## 2. Release branch

`release/<version>` starts from `develop` and changes:

- `__version__` in `src/openspacehdl/__init__.py`;
- `CHANGELOG.md`: the heading `## <version> - <date of the tag>` over the entries of Unreleased;
- the description in `pyproject.toml` and the first paragraph of `README.md`, which describe 0.0.1 (a list of the
  family); the headings of `README.md` that say "from the first version with cores" lose that note;
- the classifier `Development Status` in `pyproject.toml`, if the content warrants another one;
- the pins of the workflow CI (`.github/workflows/ci.yml`): `SITE_COMMIT` and `REFSYS_TAG` take the inputs of the
  lock of the release, and the jobs `package`, `bench-components` and `systems` drop the waived rules and
  `OPENSPACEHDL_ALLOW_WAIVED`.

## 3. Evidence on the head of the release branch

Every level of design.md, section 9, on the head of the release branch, with Python 3.10 and 3.14 and with VUnit 4.7.1
and 5.0 where a level uses VUnit:

| Level | Run | Passes when |
| --- | --- | --- |
| Gates | `python tools/check.py --site <website>` on both Python versions | exit status 0: pytest, markdownlint, no em-dash, family data |
| Wheel | `python tools/check.py --real-build --site <website> --site-commit <commit of composer_ref.txt> --refsys <reference-systems> --refsys-tag <tag> --repos <dir> --python 3.12=<interpreter>`, without `--waive` (without `--site-commit` the lock takes `origin/main` of the website, and rule L4 fails once the website has moved past that commit) | lock, snapshots, portal, wheel and wheel check pass (rules L1 to L12); the report records size, file count, longest path and SHA-256 of the wheel |
| Deep install | the same with `--deep <dir> --deep-python <python> --vunit-install "<VUnit>"`, once per VUnit version | every core of the lock and UVVM compile in GHDL from a `site-packages` path of 120 characters; `export` writes the tree and the Git repositories |
| Offline install | fresh virtual environments of both Python versions with the wheel and its dependencies: `pip download <wheel> -d <dir>`, then `pip install --no-index --find-links <dir> <wheel>` | `openspacehdl --version`, `info` and `lock` exit with 0 and show the lock of the version |
| Cores | a VUnit project per core with `add_core`, and one with every core | each compiles in GHDL |
| Bench components | `python tests/hdl/run.py` with the installed wheel | every test passes, none skipped |
| Systems | every system of the reference-systems release, with its committed export: `openspacehdl new`, `python sim/run.py "*.test_smoke" "*.test_streams"`, `openspacehdl update` (the examples of the Composer, with their export by `node tools/composer_hdl.mjs`, run in the CI job `systems`, level CI) | `new` writes the project without a warning; every test passes and none is skipped; `update` reports nothing to update and changes no file |
| Portal | `openspacehdl serve --no-browser` from the installed wheel | the website, the Composer and its catalog, every documentation path of the catalog and the start page of every documentation site are served; scripts as `text/javascript` |
| Lab | the offline install, `openspacehdl export <dir> --git` into an absolute and into a relative directory, then in `<dir>/reference-systems`, for every reference system with a hardware test, the commands of its procedure without hardware, run with `python -s -B`: `-m pytest systems/<system>/sw/hwtest --help` and `-m pytest systems/<system>/sw/hwtest --target model --profile sim --results <directory outside the export>`; the probe `systems/<system>/sw/hardware_test.py --check-environment` for information | every command exits with 0; every `junit.xml` of the results has tests and no failure, error or skip; `reference-systems` is at the commit of the lock; `git status --porcelain --ignored` is empty in it and in every submodule |
| CI | the workflow CI on the head of the release branch (open point O6): pytest on Linux and Windows, markdownlint, the family data, the exports, the bench components, and the systems level for every example of the Composer at the website commit of the lock | every job passes |
| Linux | the offline install and one system of the systems level on Linux (WSL or a Linux machine) | as above |
| Distribution | `twine check --strict` on the wheel to upload | passes |

The test case `test_image_stream` is not part of the systems level: one image takes hours in GHDL, as the README of a
generated project states.

A commit on the release branch after these runs repeats the levels it touches. A last commit that changes only
documentation keeps the evidence.

## 4. Merge, tag and files

1. A pull request from `release/<version>` to `main` carries the evidence of section 3; the maintainer merges it.
2. The maintainer sets the annotated tag `v<version>` on the merge commit. Its tree equals the head of the evidence
   (`git diff --quiet <head> v<version>`).
3. The wheel to upload is built from a clean clone of the tag with `tools/check.py --real-build` as in section 3. The
   wheel check, the offline install and the portal level run again on that wheel.

A release uploads the wheel only (open point O9 of design.md). The source distribution would carry the snapshots,
the bundles and the portal like the wheel (48.8 MiB at website 8fa23f0 and reference-systems v0.1.0) and count a
second time against the storage limit of the project on PyPI. The wheel is `py3-none-any` and installs on every
platform; the source of the package is its tagged repository.

## 5. Upload

- The maintainer uploads the wheel with twine from their own terminal, with a token scoped to the project. The token
  is entered only there. Publishing through GitHub Actions with Trusted Publishing comes later, with a publishing
  workflow and the trusted publisher on PyPI set up by the maintainer.
- The wheel stays below the file limit of the project on PyPI (rule L9, 100 MB by default).
- After the upload, the SHA-256 of the wheel on PyPI equals the local file, and fresh virtual environments of both
  Python versions install the version from PyPI and run `openspacehdl --version`, `info` and `lock`.
- The Lab level runs once more on the version from PyPI: a fresh virtual environment, `pip install
  openspacehdl==<version>`, then the export and the hardware test commands of section 3. This is the route of the
  hardware tests; the run before the upload installs the built wheel without network.

## 6. After the release

- A pull request merges `main` back into `develop`, from a branch of its own (not from `main` itself, which a delete on
  merge would remove).
- A GitHub release for the tag names the SHA-256 of the uploaded files.
