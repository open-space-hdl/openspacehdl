"""Runs the quality gates of the repository and judges each by its exit status only.

    python tools/check.py [--site <website clone>] [--no-markdownlint]
    python tools/check.py --real-build --site <website clone> --refsys <reference-systems clone> --refsys-tag <tag>
                          --repos <dir> [--uvvm <clone>] [--waive <rule> ...]
                          [--deep <dir> --deep-python <python> --vunit-install "<pip arguments>" ...]

Gates, in this order; the first one that fails stops the run with exit status 1:

1. pytest with the running Python;
2. markdownlint (npx markdownlint-cli2) over the Markdown files; --no-markdownlint skips it;
3. no em-dash in a text file of the repository (tracked, or new and not ignored);
4. with --site: tools/family_data.py --check against origin/main of the website.

--real-build runs the build of a wheel with content instead, on demand: in a copy of HEAD below build/real-build/, it
writes the lock manifest (tools/lock.py), the snapshots (tools/snapshot.py), builds the wheel (python -m build) and
checks it (tools/wheel_check.py). --waive passes rules to waive to the lock and allows the waived manifest in the
later steps; such a wheel is evidence of the build only and is never released.

--deep adds the deep install test (docs/design.md, section 9): a virtual environment of --deep-python below <dir>
whose site-packages path is exactly as long as the install prefix of [tool.openspacehdl] (120 characters), the wheel
installed into it without network, VUnit installed with each --vunit-install (arguments of pip install), and a VUnit
project that adds every core of the lock and UVVM and compiles them in GHDL (VUNIT_SIMULATOR=ghdl, 2 parallel jobs),
then openspacehdl export into <dir>/export-tree and openspacehdl export --git into <dir>/export-git.

Exit status 0 only when every gate passed.
"""

from __future__ import annotations

import argparse
import io
import os
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


DEEP_RUN = """import sys

from vunit import VUnit

import openspacehdl as osh
from openspacehdl import lock

try:
    vu = VUnit.from_argv(compile_builtins=False)
except TypeError:
    vu = VUnit.from_argv()
vu.add_vhdl_builtins()
for core in lock.load().cores:
    osh.add_core(vu, core.id)
osh.add_uvvm(vu)
vu.main()
"""


def deep_install(args, wheel: Path, project: dict) -> int:
    prefix = int(project.get("tool", {}).get("openspacehdl", {}).get("install-prefix", 120))
    base = args.deep.resolve()
    base.mkdir(parents=True, exist_ok=True)
    tail = "\\Lib\\site-packages" if sys.platform == "win32" else "/lib/python3.x/site-packages"
    pad = prefix - len(str(base)) - 1 - len(tail)
    if pad < 4:
        print(f"FAIL deep install: {base} is too long for a site-packages path of {prefix} characters")
        return 1
    venv = base / ("v" + "e" * (pad - 1))
    if venv.exists():
        _remove(venv)
    steps = [("deep venv", [str(args.deep_python), "-m", "venv", str(venv)])]
    vpy = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    steps.append(("deep wheel", [str(vpy), "-m", "pip", "install", "-q", "--no-index", str(wheel)]))
    for spec in args.vunit_install:
        steps.append(("deep vunit", [str(vpy), "-m", "pip", "install", "-q", *spec.split()]))
    for name, cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"FAIL {name} (exit status {r.returncode}): {' '.join(cmd)}")
            print((r.stdout + r.stderr).rstrip()[-4000:])
            return 1
        print(f"ok   {name}")
    site = subprocess.run([str(vpy), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True, check=True).stdout.strip()
    longest = subprocess.run([str(vpy), "-c", "import os, openspacehdl; r = os.path.dirname(openspacehdl.__file__); "
                              "print(max((len(os.path.join(d, f)) for d, _, fs in os.walk(r) for f in fs)))"],
                             capture_output=True, text=True, check=True).stdout.strip()
    print(f"ok   site-packages has {len(site)} characters, the longest installed file {longest}")
    run_dir = base / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "run.py").write_text(DEEP_RUN, encoding="utf-8")
    env = {**os.environ, "VUNIT_SIMULATOR": "ghdl"}
    if args.waive:
        env["OPENSPACEHDL_ALLOW_WAIVED"] = "1"
    r = subprocess.run([str(vpy), "run.py", "--compile", "-p", "2"], cwd=run_dir, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    version = subprocess.run([str(vpy), "-c", "import vunit; print(vunit.__version__)"], capture_output=True,
                             text=True).stdout.strip()
    if r.returncode != 0:
        print(f"FAIL deep compile with VUnit {version} (exit status {r.returncode})")
        print((r.stdout + r.stderr).rstrip()[-6000:])
        return 1
    print(f"ok   deep compile with VUnit {version}: every core of the lock and UVVM compiled in GHDL")
    for name, extra in (("export-tree", []), ("export-git", ["--git"])):
        target = base / name
        if target.exists():
            _remove(target)
        cmd = [str(vpy), "-m", "openspacehdl", "export", str(target), *extra]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"FAIL deep {name} (exit status {r.returncode}): {' '.join(cmd)}")
            print((r.stdout + r.stderr).rstrip()[-4000:])
            return 1
        print(f"ok   deep {name}: {r.stdout.strip()}")
    return 0


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
    if args.deep:
        if args.deep_python is None or not args.vunit_install:
            print("FAIL deep install: needs --deep-python and --vunit-install")
            return 1
        sys.path.insert(0, str(ROOT / "tools"))
        import snapshot
        return deep_install(args, wheels[-1], snapshot.pyproject())
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
    parser.add_argument("--deep", type=Path, help="directory of the deep install test (--real-build)")
    parser.add_argument("--deep-python", type=Path, help="Python of the deep install test")
    parser.add_argument("--vunit-install", action="append", default=[], metavar="ARGS",
                        help="arguments of a pip install of VUnit in the deep install test")
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
