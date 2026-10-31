"""Writes src/openspacehdl/data/family.json from the project cards of the website.

The cards come from _data/projects.yml and _data/project_groups.yml of the website repository
(open-space-hdl/open-space-hdl.github.io) at one commit. The file keeps only what a card shows: a project that is
not public keeps its name, group, tagline and summary, without repository, links or TRL, as its "Coming soon" card.

    python tools/family_data.py --site <clone of the website> [--commit <rev>] [--check]

--commit defaults to origin/main. --check compares the cards in the file with the cards at the commit and writes
nothing; the exit status is 1 when they differ. A newer website commit with the same cards passes the check, and the
file keeps the commit it was written from.

Needs PyYAML (development only; not a dependency of the package).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "openspacehdl" / "data" / "family.json"
SITE_REPO = "open-space-hdl/open-space-hdl.github.io"


def git(site: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(site), *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def card(project: dict) -> dict:
    """The fields a card of the website shows (_includes/project-card.html)."""
    out = {
        "name": project["name"],
        "group": project["group"],
        "tagline": list(project.get("tagline") or []),
        "summary": project["summary"],
        "public": bool(project.get("public")),
    }
    if out["public"]:
        out["repo"] = project["repo"]
        out["docs"] = bool(project.get("docs"))
        if project.get("trl"):
            out["trl"] = int(project["trl"])
            out["trl_status"] = project.get("trl_status", "")
    return out


def build(site: Path, commit: str) -> dict:
    sha = git(site, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
    config = yaml.safe_load(git(site, "show", f"{sha}:_config.yml"))
    groups = yaml.safe_load(git(site, "show", f"{sha}:_data/project_groups.yml"))
    projects = yaml.safe_load(git(site, "show", f"{sha}:_data/projects.yml"))
    ids = [g["id"] for g in groups]
    return {
        "source": {"repository": SITE_REPO, "commit": sha},
        "site": config["url"],
        "github": config["github_org"],
        "groups": [{"id": g["id"], "title": g["title"], "summary": g["summary"]} for g in groups],
        # The start page shows a project only under a known group, in the order of projects.yml.
        "projects": [card(p) for p in projects if p.get("group") in ids],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, required=True, help="clone of the website repository")
    parser.add_argument("--commit", default="origin/main", help="revision of the website (default origin/main)")
    parser.add_argument("--check", action="store_true", help="compare only, write nothing")
    parser.add_argument("--out", type=Path, default=OUT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    data = build(args.site, args.commit)
    if args.check:
        current = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
        recorded = current.get("source", {}).get("commit")
        if recorded:
            data["source"]["commit"] = recorded
        if current != data:
            print(f"{args.out.name}: the cards at {args.commit} of the website differ", file=sys.stderr)
            return 1
        print(f"{args.out.name} is current: the cards at {args.commit} equal those of {str(recorded)[:7]}")
        return 0
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
