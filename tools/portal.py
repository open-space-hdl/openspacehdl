"""Builds the portal of the lock manifest into src/openspacehdl/portal/ (docs/design.md, section 8).

    python tools/portal.py --site <website clone> --repos <dir> [--work <dir>] [--python <version>=<interpreter> ...]
                           [--allow-waived] [--pin]

The portal is the website of the lock manifest with the Composer and its catalog at the root, and the documentation
site of every core and of Open Logic FT at its pinned commit below /<repository>/. The tool builds them below --work
(default build/portal/) in clones of --site and of the clones in --repos, which are only read. The clones check out
without line-end conversion, so that every host writes the same files.

- The website is built with Jekyll and the gem set of GitHub Pages: tests/jekyll/Gemfile of the website with the gem
  versions of tools/portal/Gemfile.lock.
- Every documentation site is built with MkDocs from tools/docs/ of its repository (tools/ft_docs/ in Open Logic FT):
  the requirements of the repository with the versions of tools/portal/constraints/<repository>.txt, in a virtual
  environment of the Python version that the documentation workflow of the repository names (3.12 when it names
  none). --python names the interpreter of a version; by default it is `py -<version>` on Windows and
  `python<version>` elsewhere.

Then the tool post-processes the sites:

- it drops the source maps, the language files of the search (assets/javascripts/lunr/, which a site that searches
  in English never loads) and CNAME;
- it rewrites the links between the sites: a link to https://openspacehdl.org/<path> that the portal serves becomes
  /<path>, and a link to /<path> outside the portal (a site it does not carry) becomes
  https://openspacehdl.org/<path>;
- it removes the third-party images of STRIP_IMAGES.

It then checks:

- L11: no file of the portal loads a resource from another origin, every link to a path of the portal resolves (in
  the pages and the documentation links of the Composer catalog), and every site with the glightbox plugin has
  glightbox anchors;
- L7: every file has a licence in the map of tools/portal/licences.json (the first matching pattern decides; a match
  without a licence stops the build), and every licence text of the sources and of the theme packages equals its
  copy in src/openspacehdl/licenses/.

Only then does it replace src/openspacehdl/portal/ and write src/openspacehdl/data/portal.json, with the inputs and the
SHA-256 and licence of every file. --pin resolves the gems and the Python packages afresh and writes the Gemfile.lock
and the constraints instead of checking against them, for a change of the pins; review the change before committing
it.

Exit status 0 on success, 1 on a violation, 2 on an error of the inputs or of a build.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "openspacehdl"
LICENSES = PKG / "licenses"
LOCK = PKG / "data" / "lock.json"
OUT = PKG / "portal"
MANIFEST = PKG / "data" / "portal.json"
PINS = ROOT / "tools" / "portal"
WORK = ROOT / "build" / "portal"

FORMAT, VERSION = "openspacehdl-portal", 1
ORIGIN = "https://openspacehdl.org"
GEMFILE = "tests/jekyll/Gemfile"
DOCS_CONFIGS = ("tools/docs", "tools/ft_docs")
DEFAULT_PYTHON = "3.12"
DROPPED_DIRS = ("assets/javascripts/lunr",)
DROPPED_FILES = ("CNAME",)

# Third-party images that a documentation site still loads at its pinned commit, removed from the listed pages until
# the repository drops them: Open Logic FT 4.7.0-ft.8 keeps status badges inside lines that its strip patterns miss.
STRIP_IMAGES = {
    ("open-logic-ft", "f9e7f596e5e4c547e17087d89e3ce1289514d42d"): ("Readme.html",
                                                                    "doc/base/olo_base_pkg_attribute.html"),
}


class Violation(Exception):
    """A violation of L7 or L11; with an empty rule the message holds several, each line with its rule."""

    def __init__(self, rule: str, message: str):
        super().__init__(f"{rule}: {message}" if rule else message)
        self.rule = rule


class InputError(Exception):
    pass


@dataclass(frozen=True)
class Site:
    """A site of the portal. path is its directory in the portal: "" for the website, else the repository name."""

    path: str
    repo: str
    commit: str
    clone: Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _remove(path: Path) -> None:
    def retry(func, p, _):
        Path(p).chmod(stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def _files(root: Path) -> list[str]:
    """Every file below root, as POSIX paths relative to it."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# Inputs

def sites(lock: dict, site: Path, repos: Path) -> list[Site]:
    """The website and the documentation site of every core and of Open Logic FT, from the manifest."""
    web = lock["website"]
    out = [Site("", web["repository"].split("/")[-1], web["commit"], site)]
    for c in [*lock["cores"], lock["openLogic"]]:
        name = c["repository"].split("/")[-1]
        out.append(Site(name, name, c["commit"], repos / name))
    return out


def docs_config(clone: Path) -> str:
    """The directory of mkdocs.yml in a repository: tools/docs, or tools/ft_docs in Open Logic FT."""
    for d in DOCS_CONFIGS:
        if (clone / d / "mkdocs.yml").is_file():
            return d
    raise InputError(f"{clone.name} has no {' or '.join(d + '/mkdocs.yml' for d in DOCS_CONFIGS)}")


def workflow_python(clone: Path) -> str:
    """The python-version of the workflow that runs MkDocs, or DEFAULT_PYTHON when it names none."""
    for wf in sorted((clone / ".github" / "workflows").glob("*.y*ml")):
        text = wf.read_text(encoding="utf-8")
        if "mkdocs" in text:
            m = re.search(r"python-version:\s*['\"]?([0-9]+\.[0-9]+)", text)
            if m:
                return m.group(1)
    return DEFAULT_PYTHON


def interpreter(version: str, overrides: dict[str, str]) -> list[str]:
    """The command of the Python of a version, checked to be that version."""
    if version in overrides:
        cmd = [overrides[version]]
    elif sys.platform == "win32":
        cmd = ["py", f"-{version}"]
    else:
        cmd = [f"python{version}"]
    try:
        r = subprocess.run([*cmd, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], capture_output=True,
                           text=True)
    except OSError as e:
        raise InputError(f"no Python {version} ({' '.join(cmd)}: {e}); pass --python {version}=<interpreter>")
    if r.returncode != 0 or r.stdout.strip() != version:
        raise InputError(f"no Python {version} ({' '.join(cmd)} gives {r.stdout.strip() or r.stderr.strip()!r}); "
                         f"pass --python {version}=<interpreter>")
    return cmd


def licence_map() -> dict:
    return json.loads((PINS / "licences.json").read_text(encoding="utf-8"))


def package_texts() -> dict[str, str]:
    """sha256 of every licence text of src/openspacehdl/licenses/ -> its file name."""
    names = json.loads((LICENSES / "licenses.json").read_text(encoding="utf-8"))
    return {sha256((LICENSES / n).read_bytes()): n for n in names}


def spdx_of(name: str) -> str:
    return json.loads((LICENSES / "licenses.json").read_text(encoding="utf-8"))[name]


def repo_licence(clone: Path, commit: str) -> str:
    """The SPDX identifier of the licence of a repository: its License.txt, matched against the package texts."""
    r = subprocess.run(["git", "-C", str(clone), "cat-file", "blob", f"{commit}:License.txt"], capture_output=True)
    if r.returncode != 0:
        raise Violation("L7", f"{clone.name} has no License.txt at {commit[:7]}")
    name = package_texts().get(sha256(r.stdout))
    if name is None:
        raise Violation("L7", f"{clone.name}/License.txt differs from every licence text of src/openspacehdl/licenses/")
    return spdx_of(name)


# Builds

def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, log: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if log is not None:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"$ {' '.join(cmd)}\n{r.stdout}{r.stderr}\n")
    if r.returncode != 0:
        raise InputError(f"{' '.join(cmd)} (exit status {r.returncode}):\n{(r.stdout + r.stderr).rstrip()[-3000:]}")


def clone(src: Path, commit: str, dest: Path) -> None:
    """A clone of src at commit in dest, sharing its objects (src is only read), without line-end conversion."""
    if dest.exists():
        _remove(dest)
    run(["git", "clone", "-q", "--shared", "--no-checkout", str(src), str(dest)])
    run(["git", "-C", str(dest), "config", "core.autocrlf", "false"])
    run(["git", "-C", str(dest), "checkout", "-q", "--detach", commit])


def build_website(src: Path, out: Path, work: Path, pin: bool) -> None:
    lockfile = PINS / "Gemfile.lock"
    target = src / (GEMFILE + ".lock")
    if not pin:
        if not lockfile.is_file():
            raise InputError(f"{lockfile} is missing; write it with --pin")
        shutil.copyfile(lockfile, target)
    bundle = shutil.which("bundle")
    if bundle is None:
        raise InputError("Ruby's bundle is not on the PATH (the website needs Jekyll)")
    env = {**os.environ, "BUNDLE_GEMFILE": GEMFILE, "BUNDLE_PATH": str(work / "gems"), "JEKYLL_ENV": "production"}
    if not pin:
        env["BUNDLE_FROZEN"] = "true"
    log = work / "website.log"
    run([bundle, "install", "--jobs", "4"], cwd=src, env=env, log=log)
    if pin:
        run([bundle, "lock", "--add-platform", "x86_64-linux", "x64-mingw-ucrt"], cwd=src, env=env, log=log)
        shutil.copyfile(target, lockfile)
    run([bundle, "exec", "jekyll", "build", "-d", str(out)], cwd=src, env=env, log=log)


def freeze_problems(freeze: str, constraints: str) -> list[str]:
    """The installed packages (pip freeze) that the constraints do not pin to the installed version."""
    pinned = {}
    for line in constraints.splitlines():
        line = line.split("#")[0].strip()
        if "==" in line:
            name, ver = line.split("==", 1)
            pinned[name.strip().lower().replace("_", "-")] = ver.strip()
    out = []
    for line in freeze.splitlines():
        if "==" not in line:
            continue
        name, ver = line.split("==", 1)
        key = name.strip().lower().replace("_", "-")
        if pinned.get(key) != ver.strip():
            out.append(f"{name.strip()} {ver.strip()} (constraints: {pinned.get(key, 'none')})")
    return out


def build_docs(site: Site, src: Path, out: Path, work: Path, overrides: dict[str, str], pin: bool) -> dict:
    """Builds one documentation site; returns its inputs for the manifest."""
    cfg = docs_config(src)
    version = workflow_python(src)
    py = interpreter(version, overrides)
    venv = work / "venv" / site.repo
    if venv.exists():
        _remove(venv)
    log = work / f"{site.repo}.log"
    run([*py, "-m", "venv", str(venv)], log=log)
    vpy = str(venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
    constraints = PINS / "constraints" / f"{site.repo}.txt"
    req = ["-r", str(src / cfg / "requirements.txt")]
    if not pin:
        if not constraints.is_file():
            raise InputError(f"{constraints} is missing; write it with --pin")
        req += ["-c", str(constraints)]
    run([vpy, "-m", "pip", "install", "-q", *req], log=log)
    freeze = subprocess.run([vpy, "-m", "pip", "freeze"], capture_output=True, text=True, check=True).stdout
    if pin:
        constraints.parent.mkdir(parents=True, exist_ok=True)
        constraints.write_text(f"# pip freeze of the documentation site of {site.repo} at {site.commit[:7]} "
                               f"(Python {version}), written by tools/portal.py --pin\n{freeze}", encoding="utf-8",
                               newline="\n")
    else:
        stale = freeze_problems(freeze, constraints.read_text(encoding="utf-8"))
        if stale:
            raise InputError(f"{constraints.name} does not pin every installed package: {', '.join(stale)}; "
                             f"update it with --pin")
    run([vpy, "-m", "mkdocs", "build", "--strict", "-f", str(src / cfg / "mkdocs.yml"), "-d", str(out)], log=log)
    return {"config": cfg, "python": version, "constraints": sha256(constraints.read_bytes()), "venv": venv}


# Post-processing

def trim(root: Path) -> int:
    """Drops the source maps, the language files of the search and CNAME; returns the number of files dropped."""
    n = 0
    for p in list(root.rglob("*.map")):
        p.unlink()
        n += 1
    for d in DROPPED_DIRS:
        if (root / d).is_dir():
            n += len(_files(root / d))
            _remove(root / d)
    for f in DROPPED_FILES:
        if (root / f).is_file():
            (root / f).unlink()
            n += 1
    return n


A_HREF = re.compile(r"(<a\b[^>]*?\bhref=\")([^\"]*)(\")", re.IGNORECASE)


def served(portal: Path, path: str) -> bool:
    """Whether the portal has a file for the site path (/<path>, without query and fragment)."""
    rel = re.sub(r"[?#].*", "", path).lstrip("/")
    target = portal / rel
    if rel == "" or target.is_dir():
        return (target / "index.html").is_file()
    return target.is_file()


def outside(portal: Path, path: str) -> bool:
    """Whether a site path lies outside the portal: its first segment is no file or directory of the portal."""
    first = re.sub(r"[?#].*", "", path).lstrip("/").split("/")[0]
    return first != "" and not (portal / first).exists()


def rewrite_links(html: str, portal: Path) -> tuple[str, int, int]:
    """The page with its links rewritten: a link to https://openspacehdl.org/<path> that the portal serves becomes
    /<path>, a link to /<path> outside the portal becomes https://openspacehdl.org/<path>. A link to a missing file of
    a site of the portal stays, for L11. Returns the page and the counts made relative and made absolute."""
    inward = outward = 0

    def sub(m: re.Match) -> str:
        nonlocal inward, outward
        url = m.group(2)
        if url == ORIGIN or url.startswith(ORIGIN + "/"):
            path = url[len(ORIGIN):] or "/"
            if served(portal, path):
                inward += 1
                return m.group(1) + path + m.group(3)
        elif url.startswith("/") and not url.startswith("//"):
            if outside(portal, url):
                outward += 1
                return m.group(1) + ORIGIN + url + m.group(3)
        return m.group(0)

    return A_HREF.sub(sub, html), inward, outward


IMG = re.compile(r"<img\b[^>]*?\bsrc=\"(?:https?:)?//[^\"]*\"[^>]*>", re.IGNORECASE)


def strip_images(html: str) -> tuple[str, int]:
    """The page without its images from another origin; returns the page and the number removed."""
    out, n = IMG.subn("", html)
    return out, n


def postprocess(portal: Path, site_list: list[Site]) -> dict[str, int]:
    counts = {"dropped": 0, "relative": 0, "absolute": 0, "images": 0}
    for s in site_list:
        counts["dropped"] += trim(portal / s.path if s.path else portal)
    strip = {f"{s.path}/{p}" for s in site_list for p in STRIP_IMAGES.get((s.repo, s.commit), ())}
    for rel in _files(portal):
        if not rel.endswith(".html"):
            continue
        f = portal / rel
        html = f.read_text(encoding="utf-8")
        html, inward, outward = rewrite_links(html, portal)
        if rel in strip:
            html, n = strip_images(html)
            counts["images"] += n
        counts["relative"] += inward
        counts["absolute"] += outward
        f.write_text(html, encoding="utf-8", newline="")
    return counts


# Checks

FETCH = re.compile(r"<(img|script|iframe|source|video|audio|embed|object|link)\b[^>]*>", re.IGNORECASE)
ATTR = re.compile(r"\b(src|href|data|srcset)=\"([^\"]*)\"", re.IGNORECASE)
REL = re.compile(r"\brel=\"([^\"]*)\"", re.IGNORECASE)
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)|@import\s+['\"]([^'\"]+)")
JS_FETCH = re.compile(r"(?:fetch|import)\(\s*['\"`]((?:https?:)?//[^'\"`]+)")
FOREIGN = re.compile(r"^(?:https?:)?//", re.IGNORECASE)
LOADED_RELS = ("stylesheet", "icon", "preload", "modulepreload", "prefetch", "manifest")


def foreign_requests(portal: Path) -> list[str]:
    """Every resource a file of the portal loads from another origin, as "<file>: <tag> <url>"."""
    out = []
    for rel in _files(portal):
        p = portal / rel
        if rel.endswith(".html"):
            for m in FETCH.finditer(p.read_text(encoding="utf-8", errors="replace")):
                tag = m.group(1).lower()
                if tag == "link":
                    r = REL.search(m.group(0))
                    if not r or not any(x in r.group(1).lower().split() for x in LOADED_RELS):
                        continue
                for a in ATTR.finditer(m.group(0)):
                    if tag == "link" and a.group(1).lower() != "href":
                        continue
                    urls = [u.strip().split()[0] for u in a.group(2).split(",")] if a.group(1).lower() == "srcset" \
                        else [a.group(2)]
                    out += [f"{rel}: {tag} {u}" for u in urls if u and FOREIGN.match(u)]
        elif rel.endswith(".css"):
            for m in CSS_URL.finditer(p.read_text(encoding="utf-8", errors="replace")):
                u = m.group(1) or m.group(2)
                if FOREIGN.match(u.strip()):
                    out.append(f"{rel}: css {u.strip()}")
        elif rel.endswith((".js", ".mjs")):
            out += [f"{rel}: js {m.group(1)}" for m in JS_FETCH.finditer(p.read_text(encoding="utf-8",
                                                                                     errors="replace"))]
    return out


def broken_links(portal: Path) -> list[str]:
    """Every link of a page to a path of the portal (/<path>) that the portal does not serve."""
    out = []
    for rel in _files(portal):
        if rel.endswith(".html"):
            for m in A_HREF.finditer((portal / rel).read_text(encoding="utf-8", errors="replace")):
                url = m.group(2)
                if url.startswith("/") and not url.startswith("//") and not served(portal, url):
                    out.append(f"{rel}: {url}")
    return out


CATALOG = "assets/composer/catalog.json"


def catalog_links(portal: Path) -> list[str]:
    """Every documentation link of the Composer catalog that is a site path (/<path>) the portal does not serve."""
    f = portal / CATALOG
    if not f.is_file():
        return []
    out: list[str] = []

    def walk(x) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "doc" and isinstance(v, str) and v.startswith("/") and not served(portal, v):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(json.loads(f.read_text(encoding="utf-8")))
    return sorted(set(out))


def uses_glightbox(src: Path, cfg: str) -> bool:
    text = (src / cfg / "mkdocs.yml").read_text(encoding="utf-8")
    m = re.search(r"^plugins:\s*\n((?:[ \t]+.*\n?)*)", text, re.MULTILINE)
    return bool(m and re.search(r"^\s*-\s*glightbox\b", m.group(1), re.MULTILINE))


def glightbox_anchors(root: Path) -> int:
    return sum(len(re.findall(r"class=\"glightbox\"", (root / rel).read_text(encoding="utf-8", errors="replace")))
               for rel in _files(root) if rel.endswith(".html"))


def licence_of(rel: str, entries: list[list], core: str | None) -> str | None:
    """The licence of a file of a site by the first matching entry of the map; None when no entry gives one."""
    for pattern, lic in entries:
        if fnmatch.fnmatchcase(rel, pattern):
            return lic.replace("{core}", core) if lic and core else lic
    return None


def site_licences(portal: Path, s: Site, core: str | None, lmap: dict,
                  docs_dirs: tuple[str, ...] = ()) -> tuple[dict[str, str], list[str]]:
    """Path in the portal -> licence for every file of a site, and the files without one. The website skips the
    directories of the documentation sites (docs_dirs)."""
    root = portal / s.path if s.path else portal
    entries = lmap["website" if not s.path else "docs"]
    out, missing = {}, []
    for rel in _files(root):
        if not s.path and rel.split("/")[0] in docs_dirs:
            continue
        lic = licence_of(rel, entries, core)
        name = f"{s.path}/{rel}" if s.path else rel
        if lic is None:
            missing.append(name)
        else:
            out[name] = lic
    return out, missing


def text_problems(pairs: list[tuple[Path, str]]) -> list[str]:
    """The licence texts of the sources that differ from their package copy: (file, package text name)."""
    texts = {n: sha256((LICENSES / n).read_bytes()) for n in
             json.loads((LICENSES / "licenses.json").read_text(encoding="utf-8"))}
    out = []
    for f, name in pairs:
        if name not in texts:
            out.append(f"{name} is not a licence text of src/openspacehdl/licenses/")
        elif not f.is_file():
            out.append(f"{f} is missing")
        elif sha256(f.read_bytes()) != texts[name]:
            out.append(f"{f} differs from src/openspacehdl/licenses/{name}")
    return out


def venv_site_packages(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Lib" / "site-packages"
    return next((venv / "lib").glob("python*/site-packages"))


def licence_text_pairs(portal: Path, s: Site, lmap: dict, venv: Path | None) -> list[tuple[Path, str]]:
    root = portal / s.path if s.path else portal
    pairs = [(root / rel, name) for rel, name in lmap["texts"]["website" if not s.path else "docs"].items()]
    if venv is not None:
        sp = venv_site_packages(venv)
        for pattern, name in lmap["texts"]["packages"].items():
            dist = pattern.split("/")[0]
            if not list(sp.glob(dist)):
                continue  # the site does not use this package
            hits = list(sp.glob(pattern))
            pairs += [(h, name) for h in hits] or [(sp / pattern, name)]
    return pairs


# Manifest and main

def write_manifest(path: Path, lock: dict, inputs: dict, files: dict[str, str], portal: Path) -> None:
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "website": {"commit": lock["website"]["commit"], "gems": sha256((PINS / "Gemfile.lock").read_bytes())},
        "sites": {k: {x: v for x, v in d.items() if x != "venv"} for k, d in sorted(inputs.items())},
        "files": {rel: {"sha256": sha256((portal / rel).read_bytes()), "license": lic}
                  for rel, lic in sorted(files.items())},
    }
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build(lock: dict, site: Path, repos: Path, work: Path, overrides: dict[str, str], pin: bool,
          out: Path = OUT, manifest: Path = MANIFEST) -> dict[str, int]:
    """Builds, post-processes and checks the portal, then writes out and manifest. Raises Violation (with every
    violation of the checks in its message) or InputError."""
    work.mkdir(parents=True, exist_ok=True)
    stage = work / "portal"
    if stage.exists():
        _remove(stage)
    lmap = licence_map()
    site_list = sites(lock, site, repos)
    docs_dirs = tuple(s.path for s in site_list[1:])
    collide: list[str] = []
    inputs: dict[str, dict] = {}
    for s in site_list:
        src = work / "src" / s.repo
        clone(s.clone, s.commit, src)
        if not s.path:
            build_website(src, stage, work, pin)
            collide = [d for d in docs_dirs if (stage / d).exists()]
        else:
            inputs[s.path] = {"repository": s.repo, "commit": s.commit,
                              **build_docs(s, src, stage / s.path, work, overrides, pin)}
            inputs[s.path]["glightbox"] = uses_glightbox(src, inputs[s.path]["config"])
    counts = postprocess(stage, site_list)

    violations = [f"L11: the website has a path {c}/, the place of the documentation site {c}" for c in collide]
    violations += [f"L11: {x} loads from another origin" for x in foreign_requests(stage)]
    violations += [f"L11: {x} is a link the portal does not serve" for x in broken_links(stage)]
    violations += [f"L11: {CATALOG}: the documentation link {x} is a path the portal does not serve"
                   for x in catalog_links(stage)]
    for path, d in inputs.items():
        if d["glightbox"] and glightbox_anchors(stage / path) == 0:
            violations.append(f"L11: {path} uses glightbox but has no glightbox anchor (images lost in the build)")
    files: dict[str, str] = {}
    for s in site_list:
        core = repo_licence(s.clone, s.commit) if s.path else None
        lic, missing = site_licences(stage, s, core, lmap, docs_dirs)
        files.update(lic)
        violations += [f"L7: {m} has no licence in tools/portal/licences.json" for m in missing]
        venv = inputs.get(s.path, {}).get("venv")
        violations += [f"L7: {p}" for p in text_problems(licence_text_pairs(stage, s, lmap, venv))]
    if violations:
        raise Violation("", "\n".join(violations))

    if out.exists():
        _remove(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(stage, out)
    write_manifest(manifest, lock, inputs, files, out)
    counts["files"] = len(files)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--site", type=Path, required=True, help="clone of the website repository")
    parser.add_argument("--repos", type=Path, required=True, help="directory with the clones of the repositories")
    parser.add_argument("--work", type=Path, default=WORK, help="build directory (default build/portal)")
    parser.add_argument("--python", action="append", default=[], metavar="VERSION=INTERPRETER",
                        help="the interpreter of a Python version for the documentation builds")
    parser.add_argument("--pin", action="store_true", help="write the Gemfile.lock and the constraints afresh")
    parser.add_argument("--allow-waived", action="store_true", help="accept a manifest that waives rules (tests)")
    parser.add_argument("--lock", type=Path, default=LOCK, help=argparse.SUPPRESS)
    parser.add_argument("--out", type=Path, default=OUT, help=argparse.SUPPRESS)
    parser.add_argument("--manifest", type=Path, default=MANIFEST, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.lock.exists():
        print(f"portal: no manifest {args.lock}", file=sys.stderr)
        return 2
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    if lock.get("waived") and not args.allow_waived:
        print(f"portal: the manifest waives {', '.join(lock['waived'])}; it is for tests of the build only "
              f"(--allow-waived)", file=sys.stderr)
        return 1
    overrides = {}
    for item in args.python:
        version, _, exe = item.partition("=")
        if not exe:
            print(f"portal: --python takes VERSION=INTERPRETER, not {item!r}", file=sys.stderr)
            return 2
        overrides[version] = exe
    try:
        counts = build(lock, args.site, args.repos, args.work.resolve(), overrides, args.pin, args.out,
                       args.manifest)
    except Violation as e:
        print(f"portal:\n{e}", file=sys.stderr)
        return 1
    except InputError as e:
        print(f"portal: {e}", file=sys.stderr)
        return 2
    print(f"wrote {counts['files']} files to {args.out} ({counts['dropped']} dropped, {counts['relative']} links made "
          f"relative, {counts['absolute']} made absolute, {counts['images']} third-party images removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
