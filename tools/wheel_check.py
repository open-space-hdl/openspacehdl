"""Checks a built wheel against the lock manifest it carries: rules L6 to L9 (docs/design.md, sections 3.3 and 4).

    python tools/wheel_check.py <wheel> [--allow-waived]

- L6: every snapshot file of the manifest is in the wheel below openspacehdl/hdl/ with its SHA-256, every Git bundle
  below openspacehdl/bundles/ with the refs of the manifest (git bundle list-heads), and the wheel has no other file
  there;
- L7: the licence expression of the wheel names every licence of the snapshots, and its License-File entries list
  every licence text of src/openspacehdl/licenses/, each copied to .dist-info/licenses/;
- L8: the longest path in the wheel stays within the budget of [tool.openspacehdl] in pyproject.toml;
- L9: the wheel stays below the PyPI file limit of [tool.openspacehdl] (pypi-file-limit-mb, in MiB).

A wheel without a manifest (no snapshots) is checked for L7 to L9. A manifest that waives rules is refused unless
--allow-waived. Exit status 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from email.parser import HeaderParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import bundles  # noqa: E402
import snapshot  # noqa: E402

LOCK_NAME = "openspacehdl/data/lock.json"
HDL = "openspacehdl/hdl/"
BUNDLES = "openspacehdl/bundles/"


def metadata(z: zipfile.ZipFile) -> tuple[str, list[str], str]:
    name = next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))
    msg = HeaderParser().parsestr(z.read(name).decode("utf-8"))
    return msg.get("License-Expression", ""), msg.get_all("License-File") or [], name.rsplit("/", 1)[0]


def check(wheel: Path, project: dict, allow_waived: bool = False) -> list[str]:
    """Every violation, as "Ln: message"."""
    out: list[str] = []
    cfg = project.get("tool", {}).get("openspacehdl", {})
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        lock = json.loads(z.read(LOCK_NAME)) if LOCK_NAME in names else None
        if lock and lock.get("waived") and not allow_waived:
            out.append(f"L6: the manifest waives {', '.join(lock['waived'])}; such a wheel is never released")
        files = (lock or {}).get("files", {})
        expected = {f"{HDL}{d}/{p}": h for d, entries in files.items() for p, h in entries.items()}
        for name, h in sorted(expected.items()):
            if name not in names:
                out.append(f"L6: {name} is missing")
            elif snapshot.sha256(z.read(name)) != h:
                out.append(f"L6: {name}: the hash differs from the manifest")
        extra = sorted(n for n in names if n.startswith(HDL) and not n.endswith("/") and n not in expected)
        out += [f"L6: {n} is not in the manifest" for n in extra[:20]]
        specs = (lock or {}).get("bundles", {})
        wanted = {f"{BUNDLES}{b}.bundle": spec for b, spec in specs.items()}
        with tempfile.TemporaryDirectory(prefix="osh-wheel-") as tmp:
            for name, spec in sorted(wanted.items()):
                if name not in names:
                    out.append(f"L6: {name} is missing")
                    continue
                f = Path(tmp) / Path(name).name
                f.write_bytes(z.read(name))
                try:
                    if bundles.list_heads(f) != spec["refs"]:
                        out.append(f"L6: {name}: the refs differ from the manifest")
                except bundles.BundleError as e:
                    out.append(f"L6: {name}: {e}")
        extra = sorted(n for n in names if n.startswith(BUNDLES) and not n.endswith("/") and n not in wanted)
        out += [f"L6: {n} is not in the manifest" for n in extra]

        expression, license_files, dist_info = metadata(z)
        try:
            snapshot.check_licenses(files, expression, license_files)
        except snapshot.SnapshotError as e:
            out.append(str(e))
        for lf in license_files:
            if f"{dist_info}/licenses/{lf}" not in names:
                out.append(f"L7: {lf} is a License-File but not in {dist_info}/licenses/")

        budget = snapshot.path_budget(project)
        longest = max(names, key=len)
        if len(longest) > budget:
            out.append(f"L8: {longest} has {len(longest)} characters, the budget is {budget}")

    limit = float(cfg.get("pypi-file-limit-mb", 100)) * 1024 * 1024
    size = wheel.stat().st_size
    if size > limit:
        out.append(f"L9: the wheel has {size / 1024 / 1024:.1f} MiB, the limit is {limit / 1024 / 1024:.0f} MiB")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--allow-waived", action="store_true", help="accept a manifest that waives rules (tests)")
    args = parser.parse_args(argv)
    violations = check(args.wheel, snapshot.pyproject(), args.allow_waived)
    for v in violations:
        print(v)
    with zipfile.ZipFile(args.wheel) as z:
        longest = max(len(n) for n in z.namelist())
        count = len(z.namelist())
    print(f"{args.wheel.name}: {args.wheel.stat().st_size / 1024 / 1024:.2f} MiB, {count} files, longest path "
          f"{longest} characters, {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
