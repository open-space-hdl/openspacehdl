"""Command line of openspacehdl."""

from __future__ import annotations

import argparse
import sys
import textwrap

from openspacehdl import __version__
from openspacehdl.family import Family, Project, load

WIDTH = 100
INDENT = "    "


def _wrap(text: str, indent: str) -> list[str]:
    return textwrap.wrap(text, WIDTH, initial_indent=indent, subsequent_indent=indent)


def _project_lines(family: Family, p: Project) -> list[str]:
    state = "Coming soon" if not p.public else (f"TRL {p.trl}" if p.trl else "")
    head = "  ".join(x for x in (p.name, state) if x)
    lines = [f"  {head}"]
    if p.tagline:
        lines.append(f"{INDENT}{', '.join(p.tagline)}")
    lines += _wrap(p.summary, INDENT)
    if p.public:
        if p.trl and p.trl_status:
            lines += _wrap(f"Status: {p.trl_status}", INDENT)
        docs = family.docs_url(p)
        if docs:
            lines.append(f"{INDENT}Documentation: {docs}")
        lines.append(f"{INDENT}Source: {family.source_url(p)}")
    return lines


def info(family: Family, name: str | None) -> int:
    if name is not None:
        p = family.find(name)
        if p is None:
            names = ", ".join(x.name for x in family.projects)
            print(f"openspacehdl: no project named {name!r}; the family has {names}", file=sys.stderr)
            return 2
        print("\n".join(_project_lines(family, p)))
        return 0

    out = ["Open Space HDL: open-source VHDL IP cores for spacecraft on-board data handling", family.site]
    for g in family.groups:
        members = family.members(g)
        if not members:
            continue
        out += ["", g.title, *_wrap(g.summary, "  ")]
        for p in members:
            out += ["", *_project_lines(family, p)]
    print("\n".join(out))
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="openspacehdl",
        description="Open Space HDL: open-source VHDL IP cores for spacecraft on-board data handling.",
    )
    parser.add_argument("--version", action="version", version=f"openspacehdl {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    p_info = sub.add_parser("info", help="list the projects of the family, as the website shows them")
    p_info.add_argument("project", nargs="?", help="show only this project (name or repository)")
    args = parser.parse_args(argv)

    if args.command == "info":
        return info(load(), args.project)
    parser.print_help()
    return 0
