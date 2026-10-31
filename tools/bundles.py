"""Git bundles of the lock manifest (docs/design.md, sections 4.3 and 7): one per repository.

Each bundle carries the pinned commit with its history: the branch main (Open Logic FT: fault-tolerant; en_cl_fix:
open-logic) at the pinned commit, and every published tag in that history. tools/lock.py records the refs of every
bundle in the manifest (specs()); tools/snapshot.py writes the bundles (write()); tools/wheel_check.py compares the
refs of the bundles in the wheel with the manifest (list_heads()).

A bundle is made from a temporary bare copy of the clone, so the clone itself is only read.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

EN_CL_FIX = "en_cl_fix"
EN_CL_FIX_PATH = "3rdParty/en_cl_fix"
BRANCHES = {"olo": "fault-tolerant", EN_CL_FIX: "open-logic"}


class BundleError(Exception):
    pass


def git(repo: Path | None, *args: str) -> str:
    cmd = ["git", *(["-C", str(repo)] if repo else []), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise BundleError(f"{' '.join(cmd)}: {r.stderr.strip()}")
    return r.stdout


def _remove(path: Path) -> None:
    def retry(func, p, _):
        Path(p).chmod(stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def published_tags(repo: Path) -> set[str]:
    out = set()
    for line in git(repo, "ls-remote", "--tags", "origin").splitlines():
        if "refs/tags/" in line:
            out.add(line.split("refs/tags/")[1].removesuffix("^{}"))
    return out


def refs(repo: Path, commit: str, branch: str, published: set[str] | None) -> dict[str, str]:
    """The refs of the bundle: the branch at the commit, and every tag in its history (only published ones, unless
    published is None)."""
    out = {f"refs/heads/{branch}": commit}
    for line in git(repo, "for-each-ref", "--merged", commit, "refs/tags", "--format=%(refname) %(objectname)"
                    ).splitlines():
        name, obj = line.split()
        if published is None or name.removeprefix("refs/tags/") in published:
            out[name] = obj
    return dict(sorted(out.items()))


def _url(repository: str) -> str:
    return f"https://github.com/{repository}.git"


def sources(lock: dict, repos: Path, refsys: Path | None = None) -> dict[str, dict]:
    """Bundle id -> clone, commit, branch and remote URL, for every repository of the manifest."""
    out = {}
    for c in lock["cores"]:
        name = c["repository"].split("/")[-1]
        out[c["id"]] = {"clone": repos / name, "commit": c["commit"], "url": _url(c["repository"])}
    olo = lock["openLogic"]
    olo_clone = repos / olo["repository"].split("/")[-1]
    out["olo"] = {"clone": olo_clone, "commit": olo["commit"], "url": _url(olo["repository"])}
    fix = olo.get("submodules", {}).get(EN_CL_FIX_PATH)
    if fix:
        gitmodules = git(olo_clone, "show", f"{olo['commit']}:.gitmodules")
        url = next((line.split("=", 1)[1].strip() for line in gitmodules.splitlines()
                    if line.strip().startswith("url") and EN_CL_FIX in line), None)
        out[EN_CL_FIX] = {"clone": olo_clone / EN_CL_FIX_PATH, "commit": fix, "url": url}
    rs = lock["referenceSystems"]
    out["refsys"] = {"clone": refsys or repos / rs["repository"].split("/")[-1], "commit": rs["commit"],
                     "url": _url(rs["repository"])}
    for bid, s in out.items():
        s["branch"] = BRANCHES.get(bid, "main")
    return out


def specs(lock: dict, repos: Path, refsys: Path | None = None, offline: bool = False) -> dict[str, dict]:
    """The bundle section of the manifest: bundle id -> branch, commit, remote URL and refs."""
    out = {}
    for bid, s in sources(lock, repos, refsys).items():
        published = None if offline else published_tags(s["clone"])
        out[bid] = {"branch": s["branch"], "commit": s["commit"], "url": s["url"],
                    "refs": refs(s["clone"], s["commit"], s["branch"], published)}
    return out


def list_heads(bundle: Path) -> dict[str, str]:
    out = {}
    for line in git(None, "bundle", "list-heads", str(bundle)).splitlines():
        obj, name = line.split()
        out[name] = obj
    return dict(sorted(out.items()))


def create(clone: Path, spec: dict, target: Path) -> None:
    """Writes the bundle of spec from a temporary bare copy of clone and checks its refs."""
    with tempfile.TemporaryDirectory(prefix="osh-bundle-") as tmp:
        bare = Path(tmp) / "copy.git"
        try:
            git(None, "clone", "-q", "--bare", "--no-local", str(clone), str(bare))
            # The copy takes the refs of the bundle (the branch at the pinned commit); git bundle create then carries
            # only the refs it is given.
            wanted = spec["refs"]
            for name, obj in wanted.items():
                git(bare, "update-ref", name, obj)
            target.parent.mkdir(parents=True, exist_ok=True)
            git(bare, "bundle", "create", "-q", str(target), *wanted)
        finally:
            if bare.exists():
                _remove(bare)
    heads = list_heads(target)
    if heads != spec["refs"]:
        raise BundleError(f"{target.name}: the refs of the bundle differ from the manifest")


def write(lock: dict, repos: Path, out: Path, refsys: Path | None = None) -> int:
    """Writes every bundle of the manifest into out (emptied first); returns the number of bundles."""
    specs_ = lock.get("bundles") or {}
    if not specs_:
        raise BundleError("the manifest lists no bundles")
    if out.exists():
        _remove(out)
    src = sources(lock, repos, refsys)
    if set(src) != set(specs_):
        raise BundleError(f"the manifest lists bundles {sorted(specs_)}, the repositories give {sorted(src)}")
    for bid, spec in sorted(specs_.items()):
        create(src[bid]["clone"], spec, out / f"{bid}.bundle")
    return len(specs_)
