"""Runs the quality gates of the repository and judges each by its exit status only.

    python tools/check.py [--site <website clone>] [--no-markdownlint]

Gates, in this order; the first one that fails stops the run with exit status 1:

1. pytest with the running Python;
2. markdownlint (npx markdownlint-cli2) over the Markdown files; --no-markdownlint skips it;
3. no em-dash in a text file of the repository (tracked, or new and not ignored);
4. with --site: tools/family_data.py --check against origin/main of the website.

Exit status 0 only when every gate passed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, help="clone of the website repository, for the family data check")
    parser.add_argument("--no-markdownlint", action="store_true", help="skip markdownlint")
    args = parser.parse_args(argv)

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
