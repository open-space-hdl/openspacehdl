"""Writes the source snapshots of the lock manifest into src/openspacehdl/hdl/ (docs/design.md, section 4).

    python tools/snapshot.py --repos <dir> [--uvvm <clone>] [--allow-waived]

The files of every repository come from its clone in --repos (named after the repository; reference-systems as
reference-systems, Open Logic FT with its submodule 3rdParty/en_cl_fix) at the commit of the manifest, byte for byte
as Git stores them. UVVM comes from --uvvm, by default the uvvm submodule of the first core clone that has the
commit. The tool empties src/openspacehdl/hdl/ first, writes every file the manifest lists, and stops when:

- L6: the hash of a file differs from the manifest;
- L7: a repository has no licence file, a licence file differs from every licence text of
  src/openspacehdl/licenses/, or the licence expression or license-files of pyproject.toml miss one of them;
- L8: a path in the wheel would be longer than the budget of [tool.openspacehdl] in pyproject.toml.

It then writes the Git bundles of the manifest into src/openspacehdl/bundles/ (tools/bundles.py).

The module also holds the selection of the files (select()), which tools/lock.py uses for the hashes of the manifest.
Exit status 0 on success, 1 on a violation, 2 on an error of the inputs.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import posixpath
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "openspacehdl"
LICENSES = PKG / "licenses"
LOCK = PKG / "data" / "lock.json"
OUT = PKG / "hdl"
BUNDLES_OUT = PKG / "bundles"
WHEEL_PREFIX = "openspacehdl/hdl"

# Snapshot directories (docs/design.md, section 4.1)
OLO = "olo"
REFSYS = "refsys"
UVVM = "uvvm"
UVVM_COMPONENTS = ("uvvm_util", "uvvm_vvc_framework", "bitvis_vip_scoreboard", "bitvis_vip_clock_generator",
                   "bitvis_vip_axilite", "bitvis_vip_axistream", "bitvis_vip_axi")
REFSYS_DIRS = ("systems/", "sim/tb/", "tools/")
ROOT_LICENSES = ("License.txt", "LGPL2_1.txt", "LICENSE", "LICENSE.md")
OLO_SUBMODULE_LICENSES = ("3rdParty/en_cl_fix/LICENSE.md",)


class SnapshotError(Exception):
    def __init__(self, rule: str, message: str):
        super().__init__(f"{rule}: {message}")
        self.rule = rule


class InputError(Exception):
    pass


class Tree:
    """The files of a repository at one commit: the paths and their content."""

    def __init__(self, files: dict[str, bytes] | None = None):
        self._files = dict(files or {})

    def paths(self) -> list[str]:
        return sorted(self._files)

    def read(self, path: str) -> bytes:
        return self._files[path]

    def __contains__(self, path: str) -> bool:
        return path in self._files


def list_file(tree: Tree, path: str) -> list[str]:
    """The paths of a list file: one per line, # starts a comment."""
    out = []
    for line in tree.read(path).decode("utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _listed(tree: Tree, list_path: str, base: str = "") -> list[str]:
    missing = [p for p in list_file(tree, list_path) if base + p not in tree]
    if missing:
        raise InputError(f"{list_path} lists files that do not exist: {', '.join(missing[:5])}")
    return [base + p for p in list_file(tree, list_path)]


def select(kind: str, tree: Tree, file_list: str = "compile_order.txt", file_list_format: str = "files") -> list[str]:
    """The paths of the snapshot of one repository; kind is core, olo, refsys or uvvm."""
    paths = tree.paths()
    out: set[str] = set()
    if kind in ("core", "olo"):
        if file_list_format != "files":
            raise InputError(f"file list format {file_list_format!r} is not supported (only 'files')")
        if file_list not in tree:
            raise InputError(f"no {file_list}")
        out.add(file_list)
        out.update(_listed(tree, file_list))
        for p in paths:
            if PurePosixPath(p).name == "compile_order_sim.txt":
                out.add(p)
                out.update(_listed(tree, p))
            elif re.fullmatch(r"sw/[^/]+\.h", p):
                out.add(p)
        if kind == "olo":
            out.update(p for p in OLO_SUBMODULE_LICENSES if p in tree)
    elif kind == REFSYS:
        out.update(p for p in paths if p.startswith(REFSYS_DIRS))
    elif kind == UVVM:
        # Each component compiles the files of its script/compile_order.txt into its library, the VVC components also
        # four files of uvvm_vvc_framework/src_target_dependent/.
        for c in UVVM_COMPONENTS:
            order = f"{c}/script/compile_order.txt"
            if order not in tree:
                raise InputError(f"no {order}")
            out.add(order)
            out.update(uvvm_order(tree, c))
    else:
        raise ValueError(kind)
    out.update(p for p in ROOT_LICENSES if p in tree)
    return sorted(out)


def uvvm_order(tree: Tree, component: str) -> list[str]:
    """The files of the compile order of a UVVM component, as paths of the UVVM repository."""
    base = f"{component}/script"
    files = [posixpath.normpath(f"{base}/{p}") for p in list_file(tree, f"{base}/compile_order.txt")]
    missing = [p for p in files if p not in tree]
    if missing:
        raise InputError(f"{base}/compile_order.txt lists files that do not exist: {', '.join(missing[:5])}")
    return files


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hashes(kind: str, tree: Tree, **kw) -> dict[str, str]:
    return {p: sha256(tree.read(p)) for p in select(kind, tree, **kw)}


# Licences (L7) and path budget (L8)

def license_texts() -> dict[str, str]:
    """sha256 of every licence text of src/openspacehdl/licenses/ -> its SPDX identifier."""
    names = json.loads((LICENSES / "licenses.json").read_text(encoding="utf-8"))
    return {sha256((LICENSES / n).read_bytes()): spdx for n, spdx in names.items()}


def is_license(path: str) -> bool:
    """A licence file of a snapshot: at the root of the repository, or that of a submodule of Open Logic FT."""
    return path in ROOT_LICENSES or path in OLO_SUBMODULE_LICENSES


def check_licenses(files: dict[str, dict[str, str]], expression: str, license_files: list[str]) -> set[str]:
    """L7 for the snapshot: returns the SPDX identifiers the snapshot needs; raises SnapshotError."""
    texts = license_texts()
    needed: set[str] = set()
    for repo, entries in sorted(files.items()):
        found = [p for p in entries if is_license(p)]
        if not found:
            raise SnapshotError("L7", f"{repo}: the snapshot has no licence file")
        for p in found:
            spdx = texts.get(entries[p])
            if spdx is None:
                raise SnapshotError("L7", f"{repo}/{p} differs from every licence text of src/openspacehdl/licenses/")
            needed.add(spdx)
    names = set(re.findall(r"[A-Za-z0-9.\-+]+", expression)) - {"AND", "OR", "WITH"}
    missing = sorted(needed - names)
    if missing:
        raise SnapshotError("L7", f"the licence expression {expression!r} does not name {', '.join(missing)}")
    for n in json.loads((LICENSES / "licenses.json").read_text(encoding="utf-8")):
        path = f"src/openspacehdl/licenses/{n}"
        if not any(fnmatch.fnmatch(path, pattern) for pattern in license_files):
            raise SnapshotError("L7", f"the licence files of the wheel do not include {path}")
    return needed


def path_budget(project: dict) -> int:
    cfg = project.get("tool", {}).get("openspacehdl", {})
    return int(cfg.get("path-limit", 260)) - 1 - int(cfg.get("install-prefix", 120))


def check_paths(paths: list[str], budget: int) -> int:
    """L8: the length of the longest path; raises SnapshotError when it exceeds the budget."""
    longest = max(paths, key=len, default="")
    if len(longest) > budget:
        raise SnapshotError("L8", f"{longest} has {len(longest)} characters, the budget is {budget}")
    return len(longest)


def pyproject() -> dict:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


# Git access

def git(repo: Path, *args: str) -> bytes:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if r.returncode != 0:
        raise InputError(f"git -C {repo} {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


class GitTree(Tree):
    """The files of a clone at one commit, read with git; submodules mounted below their paths."""

    def __init__(self, repo: Path, commit: str, submodules: dict[str, "GitTree"] | None = None):
        super().__init__()
        if git(repo, "cat-file", "-t", commit).strip() != b"commit":
            raise InputError(f"{commit[:7]} is not a commit in {repo}")
        self.repo, self.commit = repo, commit
        self.subs = submodules or {}
        lines = git(repo, "ls-tree", "-r", "-z", commit).split(b"\0")
        self._own = []
        for line in filter(None, lines):
            meta, name = line.split(b"\t", 1)
            if meta.split()[1] == b"blob":
                self._own.append(name.decode("utf-8"))
        self._own_set = set(self._own)

    def paths(self) -> list[str]:
        out = list(self._own)
        for prefix, sub in self.subs.items():
            out += [f"{prefix}/{p}" for p in sub.paths()]
        return sorted(out)

    def read(self, path: str) -> bytes:
        for prefix, sub in self.subs.items():
            if path.startswith(prefix + "/"):
                return sub.read(path[len(prefix) + 1:])
        return git(self.repo, "cat-file", "blob", f"{self.commit}:{path}")

    def __contains__(self, path: str) -> bool:
        if path in self._own_set:
            return True
        return any(path.startswith(p + "/") and path[len(p) + 1:] in s for p, s in self.subs.items())


def gitlink(repo: Path, commit: str, path: str) -> str | None:
    out = git(repo, "ls-tree", commit, path).decode().split()
    return out[2] if len(out) >= 3 and out[1] == "commit" else None


def trees(lock: dict, repos: Path, uvvm: Path | None, refsys: Path | None = None) -> dict[str, tuple[str, Tree, dict]]:
    """Snapshot directory -> (kind, tree, keyword arguments of select) for every repository of the manifest.

    The clones are below repos, named after their repositories; refsys and uvvm name other clones."""
    out = {}
    for c in lock["cores"]:
        name = c["repository"].split("/")[-1]
        out[c["id"]] = ("core", GitTree(repos / name, c["commit"]),
                        {"file_list": c["fileList"], "file_list_format": c["fileListFormat"]})
    olo = lock["openLogic"]
    olo_repo = repos / olo["repository"].split("/")[-1]
    subs = {p: GitTree(olo_repo / p, sha) for p, sha in olo.get("submodules", {}).items()}
    out[OLO] = ("olo", GitTree(olo_repo, olo["commit"], subs),
                {"file_list": olo["fileList"], "file_list_format": olo["fileListFormat"]})
    rs = lock["referenceSystems"]
    out[REFSYS] = (REFSYS, GitTree(refsys or repos / rs["repository"].split("/")[-1], rs["commit"]), {})
    commit = lock["uvvm"]["commit"]
    if uvvm is None:
        for c in lock["cores"]:
            cand = repos / c["repository"].split("/")[-1] / "uvvm"
            if (cand / ".git").exists() and subprocess.run(["git", "-C", str(cand), "cat-file", "-t", commit],
                                                           capture_output=True).returncode == 0:
                uvvm = cand
                break
    if uvvm is None:
        raise InputError(f"no clone of UVVM with commit {commit[:7]}; pass --uvvm")
    out[UVVM] = (UVVM, GitTree(uvvm, commit), {})
    return out


def _remove(path: Path) -> None:
    def retry(func, p, _):
        Path(p).chmod(stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def write(lock: dict, repos: Path, uvvm: Path | None, out: Path, refsys: Path | None = None) -> int:
    """Writes the snapshots; returns the number of files. Raises SnapshotError or InputError."""
    files = lock.get("files")
    if not files:
        raise InputError("the manifest lists no snapshot files")
    project = pyproject()
    lic = project["project"]
    check_licenses(files, lic["license"], lic.get("license-files", []))
    check_paths([f"{WHEEL_PREFIX}/{d}/{p}" for d, entries in files.items() for p in entries], path_budget(project))
    sources = trees(lock, repos, uvvm, refsys)
    if set(sources) != set(files):
        raise SnapshotError("L6", f"the manifest lists snapshots {sorted(files)}, the repositories give "
                                  f"{sorted(sources)}")
    if out.exists():
        _remove(out)
    n = 0
    for d, entries in sorted(files.items()):
        tree = sources[d][1]
        for p, h in sorted(entries.items()):
            data = tree.read(p)
            if sha256(data) != h:
                raise SnapshotError("L6", f"{d}/{p}: the hash differs from the manifest")
            target = out / d / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repos", type=Path, required=True, help="directory with the clones of the repositories")
    parser.add_argument("--uvvm", type=Path, help="clone of UVVM (default: the uvvm submodule of a core clone)")
    parser.add_argument("--refsys", type=Path, help="clone of reference-systems (default: in --repos)")
    parser.add_argument("--allow-waived", action="store_true", help="accept a manifest that waives rules (tests)")
    parser.add_argument("--lock", type=Path, default=LOCK, help=argparse.SUPPRESS)
    parser.add_argument("--out", type=Path, default=OUT, help=argparse.SUPPRESS)
    parser.add_argument("--bundles-out", type=Path, default=BUNDLES_OUT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.lock.exists():
        print(f"snapshot: no manifest {args.lock}", file=sys.stderr)
        return 2
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    if lock.get("waived") and not args.allow_waived:
        print(f"snapshot: the manifest waives {', '.join(lock['waived'])}; it is for tests of the build only "
              f"(--allow-waived)", file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT / "tools"))
    import bundles

    try:
        n = write(lock, args.repos, args.uvvm, args.out, args.refsys)
        b = bundles.write(lock, args.repos, args.bundles_out, args.refsys)
    except SnapshotError as e:
        print(f"snapshot: {e}", file=sys.stderr)
        return 1
    except (InputError, bundles.BundleError) as e:
        print(f"snapshot: {e}", file=sys.stderr)
        return 2
    print(f"wrote {n} files to {args.out} and {b} bundles to {args.bundles_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
