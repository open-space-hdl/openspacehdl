"""Writes src/openspacehdl/data/lock.json, the lock manifest of the package version (docs/design.md, section 3).

    python tools/lock.py --site <website clone> --refsys <reference-systems clone> --refsys-tag <tag>
                         --repos <dir> [--site-commit <rev>] [--offline] [--check | --report]

--repos is the directory with one clone per repository of the catalog, named after the repository (openwire,
open-logic-ft, ...); Open Logic FT needs its submodule 3rdParty/en_cl_fix. Every clone must have the tags of its
remote (git fetch --tags). --site-commit defaults to origin/main.

The tool gathers the pins of assets/composer/catalog.json, the project cards of _data/projects.yml and the generator
version of the Composer at the website commit, the submodules and tools/composer_ref.txt of reference-systems at its
tag, and the tags of every repository, and applies the consistency rules of openspacehdl.lock. Without --offline it
also asks the remote of every repository (git ls-remote) which tags are published.

Default: write the manifest; nothing is written when a rule fails. --check: compare the committed manifest with the
one the inputs give. --report: print the violations only. Exit status 0 on success, 1 on a violation or a difference,
2 on an error of the inputs.

Needs PyYAML (development only; the package itself has no dependencies).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openspacehdl import __version__  # noqa: E402
from openspacehdl.errors import LockError  # noqa: E402
from openspacehdl.lock import OLO_ID, REFSYS_REPO, Inputs, build, check, dumps  # noqa: E402

OUT = ROOT / "src" / "openspacehdl" / "data" / "lock.json"
GENERATOR = re.compile(r"export const GENERATOR = \{ name: '[^']*', version: '([^']+)' \}")
OLO_SUBMODULES = ("3rdParty/en_cl_fix",)


class InputError(Exception):
    pass


def git(repo: Path, *args: str, check_rc: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if check_rc and r.returncode != 0:
        raise InputError(f"git -C {repo} {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def show(repo: Path, rev: str, path: str) -> str | None:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, text=True,
                       encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def tags(repo: Path) -> dict[str, str]:
    """Tag -> commit, annotated tags peeled."""
    out = {}
    for line in git(repo, "for-each-ref", "refs/tags", "--format=%(refname:strip=2) %(objectname) %(*objectname)",
                    ).splitlines():
        parts = line.split()
        out[parts[0]] = parts[2] if len(parts) > 2 else parts[1]
    return out


def published_tags(repo: Path) -> set[str]:
    return {line.split("refs/tags/")[1].removesuffix("^{}") for line in git(repo, "ls-remote", "--tags", "origin")
            .splitlines() if "refs/tags/" in line}


def gitlinks(repo: Path, rev: str, path: str) -> dict[str, str]:
    """Submodule commits at rev: path -> commit. A path ending in / lists the entries of that directory."""
    out = {}
    for line in git(repo, "ls-tree", rev, path).splitlines():
        meta, name = line.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind == "commit":
            out[name] = sha
    return out


def gather(site: Path, site_commit: str, refsys: Path, refsys_tag: str, repos: Path, offline: bool) -> Inputs:
    sha = git(site, "rev-parse", "--verify", f"{site_commit}^{{commit}}").strip()
    catalog_text = show(site, sha, "assets/composer/catalog.json")
    if catalog_text is None:
        raise InputError(f"website {sha[:7]} has no assets/composer/catalog.json")
    catalog = json.loads(catalog_text)
    m = GENERATOR.search(show(site, sha, "assets/composer/js/model/serialize.js") or "")
    if not m:
        raise InputError(f"website {sha[:7]}: no generator version in assets/composer/js/model/serialize.js")
    projects = yaml.safe_load(show(site, sha, "_data/projects.yml") or "[]")
    cards = {p["repo"]: {"public": bool(p.get("public")), "trl": p.get("trl")} for p in projects if "repo" in p}

    rs_commit = git(refsys, "rev-parse", "--verify", f"refs/tags/{refsys_tag}^{{commit}}").strip()
    rs_subs = {name.removeprefix("cores/"): c for name, c in gitlinks(refsys, rs_commit, "cores/").items()}
    ref = show(refsys, rs_commit, "tools/composer_ref.txt")
    composer_ref = ref.split()[0] if ref and ref.split() else None

    names = [s["repo"] for s in catalog["sources"]] + [REFSYS_REPO]
    all_tags, published, uvvm, models, licenses = {}, {}, {}, {}, {}
    olo_subs: dict[str, str] = {}
    for name in names:
        repo = refsys if name == REFSYS_REPO else repos / name
        if not (repo / ".git").exists():
            raise InputError(f"no clone of {name} at {repo}")
        all_tags[name] = tags(repo)
        published[name] = set(all_tags[name]) if offline else published_tags(repo)
    for s in catalog["sources"]:
        repo = repos / s["repo"]
        rev = all_tags[s["repo"]].get(s.get("tag")) if s["id"] == OLO_ID and s.get("tag") else s.get("commit")
        if not rev:
            continue
        if git(repo, "cat-file", "-t", rev, check_rc=False).strip() != "commit":
            raise InputError(f"{s['repo']}: commit {rev[:7]} is not in the clone (git fetch)")
        files = git(repo, "ls-tree", "-r", "--name-only", rev).splitlines()
        adapters = {Path(f).parent.name: f for f in files if f.endswith("/compile_order_sim.txt")}
        if adapters:
            models[s["repo"]] = adapters
        lic = show(repo, rev, "License.txt")
        if lic:
            licenses[s["repo"]] = lic.splitlines()[0].strip()
        if s["id"] == OLO_ID:
            for path in OLO_SUBMODULES:
                olo_subs.update(gitlinks(repo, rev, path))
        else:
            u = gitlinks(repo, rev, "uvvm")
            if "uvvm" in u:
                uvvm[s["repo"]] = u["uvvm"]
    lic = show(refsys, rs_commit, "License.txt")
    if lic:
        licenses[REFSYS_REPO] = lic.splitlines()[0].strip()

    return Inputs(
        website_commit=sha,
        catalog_id=catalog["id"],
        generator=m.group(1),
        catalog_sources=catalog["sources"],
        cards=cards,
        refsys_tag=refsys_tag,
        refsys_commit=rs_commit,
        refsys_submodules=rs_subs,
        refsys_composer_ref=composer_ref,
        tags=all_tags,
        published_tags=published,
        olo_submodules=olo_subs,
        uvvm=uvvm,
        models=models,
        licenses=licenses,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, required=True, help="clone of the website repository")
    parser.add_argument("--site-commit", default="origin/main", help="revision of the website (default origin/main)")
    parser.add_argument("--refsys", type=Path, required=True, help="clone of reference-systems")
    parser.add_argument("--refsys-tag", required=True, help="release tag of reference-systems")
    parser.add_argument("--repos", type=Path, required=True, help="directory with the clones of the repositories")
    parser.add_argument("--offline", action="store_true", help="do not ask the remotes which tags are published")
    parser.add_argument("--out", type=Path, default=OUT, help=argparse.SUPPRESS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare with the committed manifest, write nothing")
    mode.add_argument("--report", action="store_true", help="print the violations only, write nothing")
    args = parser.parse_args(argv)

    try:
        inputs = gather(args.site, args.site_commit, args.refsys, args.refsys_tag, args.repos, args.offline)
    except InputError as e:
        print(f"lock: {e}", file=sys.stderr)
        return 2
    if args.report:
        violations = check(inputs)
        for v in violations:
            print(v)
        print(f"{len(violations)} violation(s)")
        return 1 if violations else 0
    try:
        text = dumps(build(inputs, __version__))
    except LockError as e:
        print(f"lock: {e}", file=sys.stderr)
        return 1
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current != text:
            print(f"lock: {args.out.name} differs from the inputs", file=sys.stderr)
            return 1
        print(f"{args.out.name} is current")
        return 0
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
