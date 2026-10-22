"""Runs the quality gates of the repository and judges each by its exit status only.

    python tools/check.py [--site <website clone>] [--no-markdownlint]
    python tools/check.py --real-build --site <website clone> --refsys <reference-systems clone> --refsys-tag <tag>
                          --repos <dir> [--uvvm <clone>] [--waive <rule> ...]

Gates, in this order; the first one that fails stops the run with exit status 1:

1. pytest with the running Python;
2. markdownlint (npx markdownlint-cli2) over the Markdown files; --no-markdownlint skips it;
3. no em-dash in a text file of the repository (tracked, or new and not ignored);
4. with --site: tools/family_data.py --check against origin/main of the website.

--real-build runs the build of a wheel with content instead, on demand: in a copy of HEAD below build/real-build/, it
writes the lock manifest (tools/lock.py), the snapshots (tools/snapshot.py), builds the wheel (python -m build) and
checks it (tools/wheel_check.py). --waive passes rules to waive to the lock and allows the waived manifest in the
later steps; such a wheel is evidence of the build only and is never released.

Exit status 0 only when every gate passed.
"""

from __future__ import annotations

import argparse
import io
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)


def run(name: str, cmd: list[str]) -> bool:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"FAIL {name} (exit status {r.returncode}): {' '.join(cmd)}")
        print((r.stdout + r.stderr).rstrip())
        return False
    print(f"ok   {name}")
    return True


def no_em_dash() -> bool:
    files = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                           capture_output=True, check=True).stdout.split(b"\0")
    hits = []
    for name in filter(None, files):
        try:
            text = (ROOT / name.decode()).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        hits += [f"{name.decode()}:{i}" for i, line in enumerate(text.splitlines(), 1) if EM_DASH in line]
    if hits:
        print("FAIL em-dash: " + ", ".join(hits))
        return False
    print("ok   em-dash")
    return True


def _remove(path: Path) -> None:
    def retry(func, p, _):
        Path(p).chmod(stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def real_build(args) -> int:
    missing = [o for o in ("site", "refsys", "refsys_tag", "repos") if getattr(args, o) is None]
    if missing:
        print("FAIL real build: needs " + ", ".join("--" + m.replace("_", "-") for m in missing))
        return 1
    dest = ROOT / "build" / "real-build"
    if dest.exists():
        _remove(dest)
    dest.mkdir(parents=True)
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, capture_output=True, check=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # Python 3.10 before 3.10.12
            tar.extractall(dest)
    print(f"ok   copy of HEAD in {dest}")
    py = sys.executable
    waive = [x for w in args.waive for x in ("--waive", w)]
    allow = ["--allow-waived"] if args.waive else []
    uvvm = ["--uvvm", str(args.uvvm)] if args.uvvm else []
    steps = [
        ("lock", [py, "tools/lock.py", "--site", str(args.site), "--refsys", str(args.refsys), "--refsys-tag",
                  args.refsys_tag, "--repos", str(args.repos), *uvvm, *waive]),
        ("snapshot", [py, "tools/snapshot.py", "--repos", str(args.repos), "--refsys", str(args.refsys), *uvvm,
                      *allow]),
        ("wheel", [py, "-m", "build", "--wheel", "--outdir", "dist"]),
    ]
    for name, cmd in steps:
        r = subprocess.run(cmd, cwd=dest, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"FAIL {name} (exit status {r.returncode}): {' '.join(cmd)}")
            print((r.stdout + r.stderr).rstrip()[-4000:])
            return 1
        print(f"ok   {name}")
    wheels = sorted((dest / "dist").glob("*.whl"))
    r = subprocess.run([py, "tools/wheel_check.py", str(wheels[-1]), *allow], cwd=dest, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    print((r.stdout + r.stderr).rstrip())
    if r.returncode != 0:
        print(f"FAIL wheel check (exit status {r.returncode})")
        return 1
    note = f" (waived: {', '.join(args.waive)}; evidence of the build only)" if args.waive else ""
    print(f"ok   wheel check{note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, help="clone of the website repository, for the family data check")
    parser.add_argument("--no-markdownlint", action="store_true", help="skip markdownlint")
    parser.add_argument("--real-build", action="store_true", help="build and check a wheel with content")
    parser.add_argument("--refsys", type=Path, help="clone of reference-systems (--real-build)")
    parser.add_argument("--refsys-tag", help="release tag of reference-systems (--real-build)")
    parser.add_argument("--repos", type=Path, help="directory with the clones of the repositories (--real-build)")
    parser.add_argument("--uvvm", type=Path, help="clone of UVVM (--real-build)")
    parser.add_argument("--waive", action="append", default=[], metavar="RULE",
                        help="rule the lock may break (--real-build, evidence only)")
    args = parser.parse_args(argv)
    if args.real_build:
        return real_build(args)

    gates = [lambda: run("pytest", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])]
    if not args.no_markdownlint:
        npx = shutil.which("npx")
        if npx is None:
            print("FAIL markdownlint: npx not found (install Node.js, or pass --no-markdownlint)")
            return 1
        gates.append(lambda: run("markdownlint", [npx, "--yes", "markdownlint-cli2", "--config", ".markdownlint.json",
                                                  "*.md", "docs/**/*.md"]))
    gates.append(no_em_dash)
    if args.site:
        gates.append(lambda: run("family data", [sys.executable, "tools/family_data.py", "--site", str(args.site),
                                                 "--check"]))
    for gate in gates:
        if not gate():
            return 1
    print("all gates passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
