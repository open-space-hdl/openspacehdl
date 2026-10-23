"""openspacehdl export: the sources of the package version as a plain tree, or as Git repositories (docs/design.md,
section 7).

    openspacehdl export <dir> [--core <core> ...]          the source snapshots, one directory per repository
    openspacehdl export <dir> --git [--core <core> ...]    Git clones from the bundles, with their history

Without --core every repository of the lock manifest is exported; with --core the named cores and Open Logic FT.
The target directory must not exist or be empty. --git needs git; the clones are checked out at the pinned commits,
Open Logic FT with its submodule en_cl_fix, reference-systems with its submodules cores/<repository> pointing at the
neighbouring clones. The remote origin of every clone is the published repository, so a later git fetch works with
network.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from openspacehdl import vunit
from openspacehdl.errors import OshError
from openspacehdl.installed import Installed, installed  # noqa: F401 (installed: replaced by tests)

EN_CL_FIX = "en_cl_fix"
EN_CL_FIX_PATH = "3rdParty/en_cl_fix"


class ExportError(OshError):
    """The export cannot be written."""


def _empty_target(dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        raise ExportError(f"{dest} is not empty; export writes only into a new or empty directory")
    dest.mkdir(parents=True, exist_ok=True)


def _selection(inst: Installed, cores: list[str] | None) -> list[str]:
    """Snapshot or bundle ids of the cores to export; all cores when cores is None."""
    if cores is None:
        return [c.id for c in inst.lock.cores]
    return [vunit._find(inst, name).id for name in cores]


def _names(inst: Installed) -> dict[str, str]:
    """Snapshot or bundle id -> directory name of the export (the repository name)."""
    out = {c.id: c.repository.split("/")[-1] for c in inst.lock.cores}
    out.update({"olo": inst.lock.olo_repository.split("/")[-1],
                "refsys": inst.lock.refsys_repository.split("/")[-1], "uvvm": "uvvm"})
    return out


def _write_lock(inst: Installed, dest: Path) -> None:
    if inst.manifest is not None:
        shutil.copyfile(inst.manifest, dest / "openspacehdl-lock.json")


def export_tree(dest: Path, cores: list[str] | None = None) -> list[str]:
    """Writes the source snapshots, each file checked against the manifest; returns the exported directories."""
    inst = installed()
    ids = _selection(inst, cores) + ["olo"] + ([] if cores else ["refsys", "uvvm"])
    _empty_target(dest)
    names = _names(inst)
    for sid in ids:
        entries = sorted(inst.lock.files.get(sid, {}))
        for f, p in zip(inst.verified(sid, entries), entries):
            target = dest / names[sid] / p
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
    _write_lock(inst, dest)
    return [names[s] for s in ids]


def _git(repo: Path | None, *args: str) -> str:
    cmd = ["git", *(["-C", str(repo)] if repo else []), *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        raise ExportError("export --git needs git on the PATH") from None
    if r.returncode != 0:
        raise ExportError(f"{' '.join(cmd)}: {r.stderr.strip()}")
    return r.stdout


def _submodules(repo: Path) -> dict[str, tuple[str, str]]:
    """path -> (name, url) of the submodules declared in .gitmodules of the checkout."""
    if not (repo / ".gitmodules").is_file():
        return {}
    out: dict[str, list[str]] = {}
    for line in _git(repo, "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.(path|url)$").splitlines():
        key, value = line.split(" ", 1)
        name, attr = key[len("submodule."):].rsplit(".", 1)
        out.setdefault(name, ["", ""])[0 if attr == "path" else 1] = value
    return {path: (name, url) for name, (path, url) in out.items()}


def _fill_submodule(repo: Path, path: str, source: Path) -> None:
    """Checks out the submodule at path from source (a bundle or a clone) without network; origin stays published."""
    name, url = _submodules(repo)[path]
    _git(repo, "submodule", "init", "--", path)
    _git(repo, "config", f"submodule.{name}.url", str(source))
    _git(repo, "-c", "protocol.file.allow=always", "submodule", "update", "--", path)
    _git(repo, "config", f"submodule.{name}.url", url)
    _git(repo / path, "remote", "set-url", "origin", url)


def _bundle(inst: Installed, bid: str) -> Path:
    f = (inst.bundles or Path()) / f"{bid}.bundle"
    if inst.bundles is None or not f.is_file() or bid not in inst.lock.bundles:
        raise ExportError(f"the bundle {bid} is missing: the installation of openspacehdl is damaged or has no "
                          f"bundles")
    return f


def _clone(inst: Installed, bid: str, target: Path) -> None:
    spec = inst.lock.bundles[bid]
    _git(None, "clone", "-q", "-b", spec["branch"], str(_bundle(inst, bid)), str(target))
    _git(target, "remote", "set-url", "origin", spec["url"])
    head = _git(target, "rev-parse", "HEAD").strip()
    if head != spec["commit"]:
        raise ExportError(f"{target.name}: HEAD is {head[:7]}, the manifest pins {spec['commit'][:7]}")


def _fill_en_cl_fix(inst: Installed, olo: Path) -> None:
    if EN_CL_FIX in inst.lock.bundles and EN_CL_FIX_PATH in _submodules(olo):
        _fill_submodule(olo, EN_CL_FIX_PATH, _bundle(inst, EN_CL_FIX))
        head = _git(olo / EN_CL_FIX_PATH, "rev-parse", "HEAD").strip()
        if head != inst.lock.olo_submodules.get(EN_CL_FIX_PATH):
            raise ExportError(f"{EN_CL_FIX_PATH}: HEAD is {head[:7]}, the manifest pins another commit")


def export_git(dest: Path, cores: list[str] | None = None) -> list[str]:
    """Clones the repositories from their bundles; returns the exported directories."""
    inst = installed()
    ids = _selection(inst, cores)
    _empty_target(dest)
    names = _names(inst)
    olo = dest / names["olo"]
    _clone(inst, "olo", olo)
    _fill_en_cl_fix(inst, olo)
    for cid in ids:
        _clone(inst, cid, dest / names[cid])
    done = [names["olo"]] + [names[c] for c in ids]
    if cores is None:
        rs = dest / names["refsys"]
        _clone(inst, "refsys", rs)
        siblings = {f"cores/{n}": dest / n for n in done}
        for path in sorted(_submodules(rs)):
            if path in siblings:
                _fill_submodule(rs, path, siblings[path])
        nested = rs / "cores" / names["olo"]
        if (nested / ".git").exists():
            _fill_en_cl_fix(inst, nested)
        status = _git(rs, "submodule", "status")
        stale = [line for line in status.splitlines() if line.startswith("+")]
        if stale:
            raise ExportError(f"reference-systems: submodules not at their recorded commits: {stale}")
        done.append(names["refsys"])
    _write_lock(inst, dest)
    return done


def main(dest: str, cores: list[str] | None, git: bool) -> int:
    try:
        done = (export_git if git else export_tree)(Path(dest), cores or None)
    except OshError as e:
        print(f"openspacehdl: {e}", file=sys.stderr)
        return 1
    kind = "Git repositories" if git else "source snapshots"
    print(f"exported {kind} to {dest}: {', '.join(done)}")
    return 0
