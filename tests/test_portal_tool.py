"""Tests of the portal build (tools/portal.py): inputs, post-processing, the checks of L11 and the licence map (L7),
on small trees; build() runs with the website and documentation builds replaced by writers of fixture sites."""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LICENSES = ROOT / "src" / "openspacehdl" / "licenses"


def load(name, as_name):
    spec = importlib.util.spec_from_file_location(as_name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[as_name] = mod  # the dataclasses of the module look themselves up there
    spec.loader.exec_module(mod)
    return mod


portal = load("portal", "portal_tool")
PSI = "LicenseRef-PSI-HDL-1.0"


def write(root: Path, files: dict[str, str | bytes]) -> Path:
    for name, content in files.items():
        f = root / name
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            f.write_bytes(content)
        else:
            f.write_text(content, encoding="utf-8", newline="")
    return root


def text(name: str) -> bytes:
    return (LICENSES / name).read_bytes()


# Inputs

def test_python_of_the_documentation_workflow(tmp_path):
    write(tmp_path, {
        ".github/workflows/ci.yml": "jobs:\n  t:\n    steps:\n      - uses: actions/setup-python@v6\n"
                                    "        with:\n          python-version: \"3.10\"\n",
        ".github/workflows/docs.yml": "steps:\n  - uses: actions/setup-python@v6\n    with:\n"
                                      "      python-version: '3.11'\n  - run: python -m mkdocs build --strict\n",
    })
    assert portal.workflow_python(tmp_path) == "3.11"


def test_python_falls_back_to_3_12(tmp_path):
    write(tmp_path, {".github/workflows/docs.yml": "steps:\n  - run: mkdocs build\n"})
    assert portal.workflow_python(tmp_path) == "3.12"
    assert portal.workflow_python(tmp_path / "none") == "3.12"


def test_docs_config_of_the_cores_and_of_open_logic_ft(tmp_path):
    write(tmp_path / "core", {"tools/docs/mkdocs.yml": "site_name: x\n"})
    write(tmp_path / "olo", {"tools/ft_docs/mkdocs.yml": "site_name: x\n"})
    assert portal.docs_config(tmp_path / "core") == "tools/docs"
    assert portal.docs_config(tmp_path / "olo") == "tools/ft_docs"
    with pytest.raises(portal.InputError, match="mkdocs.yml"):
        portal.docs_config(write(tmp_path / "bare", {"README.md": "x"}))


def test_an_interpreter_of_another_version_is_refused(monkeypatch):
    import subprocess
    import sys

    with pytest.raises(portal.InputError, match="pass --python 3.1=<interpreter>"):
        portal.interpreter("3.1", {"3.1": sys.executable})
    found = "%d.%d" % sys.version_info[:2]
    assert portal.interpreter(found, {found: sys.executable}) == [sys.executable]
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("missing")))
    with pytest.raises(portal.InputError, match="no Python 3.12"):
        portal.interpreter("3.12", {})


def test_sites_of_the_manifest():
    lock = {"website": {"repository": "open-space-hdl/open-space-hdl.github.io", "commit": "w" * 40},
            "cores": [{"repository": "open-space-hdl/openwire", "commit": "a" * 40}],
            "openLogic": {"repository": "open-space-hdl/open-logic-ft", "commit": "b" * 40}}
    s = portal.sites(lock, Path("site"), Path("repos"))
    assert [(x.path, x.repo, x.commit[0], x.clone.as_posix()) for x in s] == [
        ("", "open-space-hdl.github.io", "w", "site"), ("openwire", "openwire", "a", "repos/openwire"),
        ("open-logic-ft", "open-logic-ft", "b", "repos/open-logic-ft")]


def test_constraints_must_pin_every_installed_package():
    constraints = "# freeze\nmkdocs==1.6.1\nMkDocs_Material==9.7.7\nselectolax==1.0.2\n"
    assert portal.freeze_problems("mkdocs==1.6.1\nmkdocs-material==9.7.7\n", constraints) == []
    assert portal.freeze_problems("mkdocs==1.6.1\nselectolax==1.0.1\n", constraints) == [
        "selectolax 1.0.1 (constraints: 1.0.2)"]
    assert portal.freeze_problems("pymdown-extensions==10.0\n", constraints) == [
        "pymdown-extensions 10.0 (constraints: none)"]


# Post-processing

def test_trim_drops_maps_search_languages_and_cname(tmp_path):
    write(tmp_path, {"CNAME": "openspacehdl.org", "index.html": "x", "assets/javascripts/bundle.js": "b",
                     "assets/javascripts/bundle.js.map": "m", "assets/stylesheets/main.css.map": "m",
                     "assets/javascripts/lunr/min/lunr.de.min.js": "l", "assets/javascripts/lunr/wordcut.js": "w"})
    assert portal.trim(tmp_path) == 5
    assert portal._files(tmp_path) == ["assets/javascripts/bundle.js", "index.html"]


@pytest.fixture
def tree(tmp_path):
    return write(tmp_path, {"index.html": "start", "trl/index.html": "trl", "openwire/index.html": "w",
                            "openwire/docs/user_guide.html": "g", "composer/index.html": "c"})


@pytest.mark.parametrize("before,after", [
    ('<a href="https://openspacehdl.org">', '<a href="/">'),
    ('<a href="https://openspacehdl.org/">', '<a href="/">'),
    ('<a class="x" href="https://openspacehdl.org/openwire/docs/user_guide.html#gen">',
     '<a class="x" href="/openwire/docs/user_guide.html#gen">'),
    ('<a href="https://openspacehdl.org/trl/">', '<a href="/trl/">'),
    ('<a href="https://openspacehdl.org/opendma/">', '<a href="https://openspacehdl.org/opendma/">'),
    ('<a href="/opendma/docs/roadmap.html">', '<a href="https://openspacehdl.org/opendma/docs/roadmap.html">'),
    ('<a href="/openwire/docs/missing.html">', '<a href="/openwire/docs/missing.html">'),
    ('<a href="/#projects">', '<a href="/#projects">'),
    ('<a href="/composer/">', '<a href="/composer/">'),
    ('<a href="//cdn.example.org/x">', '<a href="//cdn.example.org/x">'),
    ('<a href="docs/user_guide.html">', '<a href="docs/user_guide.html">'),
    ('<a href="https://github.com/open-space-hdl">', '<a href="https://github.com/open-space-hdl">'),
    ('<link rel="canonical" href="https://openspacehdl.org/trl/">',
     '<link rel="canonical" href="https://openspacehdl.org/trl/">'),
])
def test_links_between_the_sites(tree, before, after):
    assert portal.rewrite_links(before, tree)[0] == after


def test_link_rewrite_counts(tree):
    html = '<a href="https://openspacehdl.org/trl/">t</a> <a href="/opendma/">d</a> <a href="/trl/">x</a>'
    assert portal.rewrite_links(html, tree)[1:] == (1, 1)


def test_strip_images_removes_only_images_of_another_origin():
    html = ('<li><img alt="issues" src="https://img.shields.io/badge/issues-0-green" /></li>'
            '<p><img src="//example.org/b.svg"><img alt="d" src="img/diagram.svg" /></p>')
    out, n = portal.strip_images(html)
    assert n == 2
    assert out == '<li></li><p><img alt="d" src="img/diagram.svg" /></p>'


def test_postprocess_strips_images_only_on_the_listed_pages(tmp_path, monkeypatch):
    badge = '<img src="https://img.shields.io/b" />'
    write(tmp_path, {"index.html": "s", "olo/Readme.html": badge, "olo/other.html": badge, "CNAME": "x"})
    monkeypatch.setattr(portal, "STRIP_IMAGES", {("open-logic-ft", "c" * 40): ("Readme.html",)})
    site_list = [portal.Site("", "web", "w" * 40, tmp_path), portal.Site("olo", "open-logic-ft", "c" * 40, tmp_path)]
    counts = portal.postprocess(tmp_path, site_list)
    assert counts["images"] == 1 and counts["dropped"] == 1
    assert (tmp_path / "olo/Readme.html").read_text(encoding="utf-8") == ""
    assert (tmp_path / "olo/other.html").read_text(encoding="utf-8") == badge
    assert portal.foreign_requests(tmp_path) == ["olo/other.html: img https://img.shields.io/b"]


# Checks

def test_foreign_requests(tmp_path):
    write(tmp_path, {
        "a.html": '<img src="img/x.png"><img src="https://img.shields.io/b"><script src="//cdn.example/x.js"></script>'
                  '<link rel="stylesheet" href="https://fonts.example/c.css"><link rel="canonical" '
                  'href="https://openspacehdl.org/a/"><link rel="icon" href="/favicon.svg">'
                  '<img srcset="small.png 1x, https://x.example/big.png 2x"><a href="https://github.com">g</a>',
        "s.css": '@font-face { src: url("../fonts/sora.woff2") } .x { background: url(https://x.example/i.png) } '
                 '@import "https://fonts.example/f.css"; .y { background: url(data:image/png;base64,AA) }',
        "m.js": 'fetch("catalog.json"); fetch("https://api.example/x"); import("./a.js")',
    })
    assert sorted(portal.foreign_requests(tmp_path)) == sorted([
        "a.html: img https://img.shields.io/b", "a.html: script //cdn.example/x.js",
        "a.html: link https://fonts.example/c.css", "a.html: img https://x.example/big.png",
        "s.css: css https://x.example/i.png", "s.css: css https://fonts.example/f.css",
        "m.js: js https://api.example/x"])


def test_broken_links(tree):
    write(tree, {"page.html": '<a href="/trl/">t</a><a href="/nothing/">n</a><a href="/openwire/docs/x.html">x</a>'
                              '<a href="https://openspacehdl.org/nothing/">o</a><a href="rel.html">r</a>'})
    assert portal.broken_links(tree) == ["page.html: /nothing/", "page.html: /openwire/docs/x.html"]


def test_documentation_links_of_the_catalog(tree):
    catalog = {"sources": [{"id": "openwire", "doc": "/openwire/"}],
               "blocks": [{"id": "a", "doc": "/openwire/docs/user_guide.html#ports"},
                          {"id": "b", "doc": "/openwire/docs/missing.html"},
                          {"id": "c", "doc": "https://openspacehdl.org/openwire/docs/user_guide.html"},
                          {"id": "d", "registers": {"doc": "docs/register_map.md"}}]}
    assert portal.catalog_links(tree) == []
    write(tree, {"assets/composer/catalog.json": json.dumps(catalog)})
    assert portal.catalog_links(tree) == ["/openwire/docs/missing.html"]


@pytest.mark.parametrize("plugins,used", [
    ("plugins:\n  - search\n  - glightbox  # click on a diagram\n\nvalidation:\n", True),
    ("plugins:\n  - search\n\nmarkdown_extensions:\n  - glightbox_like\n", False),
    ("theme:\n  name: material\n", False),
])
def test_glightbox_plugin(tmp_path, plugins, used):
    write(tmp_path, {"tools/docs/mkdocs.yml": f"site_name: x\n{plugins}"})
    assert portal.uses_glightbox(tmp_path, "tools/docs") is used


def test_glightbox_anchors(tmp_path):
    write(tmp_path, {"a.html": '<a class="glightbox" href="x.svg"><img src="x.svg"></a>' * 2, "b.html": "none"})
    assert portal.glightbox_anchors(tmp_path) == 2


# Licence map and licence texts

def test_first_matching_entry_decides():
    entries = [["assets/images/logo.svg", "LicenseRef-OpenSpaceHDL-Logo"], ["assets/images/*", "{core}"],
               ["assets/*", None], ["*.html", "{core} AND CC-BY-4.0"], ["*", "{core}"]]
    assert portal.licence_of("assets/images/logo.svg", entries, PSI) == "LicenseRef-OpenSpaceHDL-Logo"
    assert portal.licence_of("assets/images/trl-3.svg", entries, PSI) == PSI
    assert portal.licence_of("assets/other/x.js", entries, PSI) is None
    assert portal.licence_of("doc/ft/olo_ft_fifo_sync.html", entries, PSI) == f"{PSI} AND CC-BY-4.0"
    assert portal.licence_of("doc/img/a.png", entries, PSI) == PSI
    assert portal.licence_of("x", [["y", "MIT"]], None) is None


def test_licences_of_the_map(tmp_path):
    lmap = portal.licence_map()
    docs = write(tmp_path / "openwire", {
        "index.html": "", "search/search_index.json": "", "sitemap.xml.gz": "", "docs/img/arch.drawio.svg": "",
        "assets/images/logo.svg": "", "assets/images/favicon.svg": "", "assets/fonts/sora.woff2": "",
        "assets/stylesheets/brand.css": "", "assets/stylesheets/main.ec1eaa64.min.css": "",
        "assets/javascripts/bundle.d7400e89.min.js": "", "assets/javascripts/workers/search.2c215733.min.js": "",
        "assets/javascripts/glightbox.min.js": "", "assets/external/unpkg.com/x.js": ""})
    write(tmp_path, {"index.html": "", "composer/schema/system-2.json": "", "assets/composer/catalog.json": "",
                     "assets/img/composer-teaser.png": "", "assets/img/social-preview.png": "", "favicon.ico": "",
                     "assets/fonts/Sora-OFL.txt": "", "LICENSE-CONTENT": "", "assets/js/new.js": "", "robots.txt": ""})
    site, missing = portal.site_licences(tmp_path, portal.Site("", "web", "w", tmp_path), None, lmap, ("openwire",))
    assert site == {"index.html": "MIT AND CC-BY-4.0", "composer/schema/system-2.json": "MIT",
                    "assets/composer/catalog.json": "MIT", "assets/img/composer-teaser.png": "CC-BY-4.0",
                    "assets/img/social-preview.png": "LicenseRef-OpenSpaceHDL-Logo",
                    "favicon.ico": "LicenseRef-OpenSpaceHDL-Logo", "assets/fonts/Sora-OFL.txt": "OFL-1.1",
                    "LICENSE-CONTENT": "CC-BY-4.0"}
    assert sorted(missing) == ["assets/js/new.js", "robots.txt"]
    lic, missing = portal.site_licences(tmp_path, portal.Site("openwire", "openwire", "a", docs), PSI, lmap)
    assert lic["openwire/index.html"] == f"{PSI} AND CC-BY-4.0 AND Apache-2.0"
    assert lic["openwire/docs/img/arch.drawio.svg"] == PSI
    assert lic["openwire/assets/images/logo.svg"] == "LicenseRef-OpenSpaceHDL-Logo"
    assert lic["openwire/assets/images/favicon.svg"] == "LicenseRef-OpenSpaceHDL-Logo"
    assert lic["openwire/assets/stylesheets/brand.css"] == PSI
    assert {lic[f"openwire/{p}"] for p in ("assets/stylesheets/main.ec1eaa64.min.css",
                                           "assets/javascripts/bundle.d7400e89.min.js",
                                           "assets/javascripts/workers/search.2c215733.min.js",
                                           "assets/javascripts/glightbox.min.js")} == {"MIT"}
    assert missing == ["openwire/assets/external/unpkg.com/x.js"]


def test_the_map_names_only_known_licences_and_texts():
    lmap = portal.licence_map()
    names = json.loads((LICENSES / "licenses.json").read_text(encoding="utf-8"))
    known = set(names.values())
    for kind in ("website", "docs"):
        for pattern, lic in lmap[kind]:
            if lic is not None:
                ids = set(re.findall(r"[A-Za-z0-9.\-+{}]+", lic)) - {"AND", "OR", "WITH", "{core}"}
                assert ids <= known, (pattern, lic)
    for group in lmap["texts"].values():
        assert set(group.values()) <= set(names)
    for n in names:
        assert (LICENSES / n).is_file()


def test_the_expression_of_the_wheel_names_every_licence_of_the_portal():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib
    with open(ROOT / "pyproject.toml", "rb") as f:
        expression = tomllib.load(f)["project"]["license"]
    names = set(re.findall(r"[A-Za-z0-9.\-+]+", expression)) - {"AND", "OR", "WITH"}
    assert set(json.loads((LICENSES / "licenses.json").read_text(encoding="utf-8")).values()) <= names


def test_licence_texts_of_the_sources(tmp_path):
    write(tmp_path, {"LICENSE": text("MIT-website.txt"), "LICENSE-CONTENT": text("CC-BY-4.0.txt") + b"x"})
    pairs = [(tmp_path / "LICENSE", "MIT-website.txt"), (tmp_path / "LICENSE-CONTENT", "CC-BY-4.0.txt"),
             (tmp_path / "missing", "OFL-1.1-Sora.txt"), (tmp_path / "LICENSE", "Unknown.txt")]
    problems = portal.text_problems(pairs)
    assert len(problems) == 3
    assert "LICENSE-CONTENT differs from src/openspacehdl/licenses/CC-BY-4.0.txt" in problems[0]
    assert problems[1].endswith("missing is missing")
    assert problems[2] == "Unknown.txt is not a licence text of src/openspacehdl/licenses/"


def test_the_logo_notice_names_every_reserved_file():
    notice = text("OpenSpaceHDL-Logo.txt").decode("utf-8")
    for pattern, lic in portal.licence_map()["website"] + portal.licence_map()["docs"]:
        if lic == "LicenseRef-OpenSpaceHDL-Logo":
            assert pattern in notice


# build() with fixture sites instead of Jekyll and MkDocs

def fixture_world(tmp_path, monkeypatch, website_extra=None, docs_extra=None):
    lock = {"website": {"repository": "open-space-hdl/open-space-hdl.github.io", "commit": "w" * 40},
            "cores": [{"repository": "open-space-hdl/openwire", "commit": "a" * 40}],
            "openLogic": {"repository": "open-space-hdl/open-logic-ft", "commit": "b" * 40}}
    website = {"index.html": '<a href="https://github.com/x">g</a><a href="/openwire/">w</a><a href="/opendma/">d</a>',
               "assets/css/site.css": "", "LICENSE": text("MIT-website.txt"), "LICENSE-CONTENT": text("CC-BY-4.0.txt"),
               "assets/fonts/Sora-OFL.txt": text("OFL-1.1-Sora.txt"),
               "assets/fonts/JetBrainsMono-OFL.txt": text("OFL-1.1-JetBrainsMono.txt"), "CNAME": "x",
               **(website_extra or {})}
    docs = {"index.html": '<a href="https://openspacehdl.org">home</a><a class="glightbox" href="d.svg"></a>',
            "assets/fonts/Sora-OFL.txt": text("OFL-1.1-Sora.txt"),
            "assets/fonts/JetBrainsMono-OFL.txt": text("OFL-1.1-JetBrainsMono.txt"),
            "assets/javascripts/bundle.1.min.js.map": "m", **(docs_extra or {})}

    monkeypatch.setattr(portal, "clone", lambda src, commit, dest: dest.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(portal, "build_website", lambda src, out, work, pin: write(out, website))
    monkeypatch.setattr(portal, "repo_licence", lambda clone, commit: PSI)

    def docs_build(site, src, out, work, overrides, pin):
        write(out, docs)
        return {"config": "tools/docs", "python": "3.12", "constraints": "c" * 64, "venv": None}

    monkeypatch.setattr(portal, "build_docs", docs_build)
    monkeypatch.setattr(portal, "uses_glightbox", lambda src, cfg: True)
    monkeypatch.setattr(portal, "PINS", write(tmp_path / "pins", {
        "Gemfile.lock": "GEM\n", "licences.json": (ROOT / "tools/portal/licences.json").read_text(encoding="utf-8")}))
    return lock


def test_build_writes_the_portal_and_its_manifest(tmp_path, monkeypatch):
    lock = fixture_world(tmp_path, monkeypatch)
    out, manifest = tmp_path / "out", tmp_path / "data" / "portal.json"
    manifest.parent.mkdir()
    counts = portal.build(lock, tmp_path / "site", tmp_path / "repos", tmp_path / "work", {}, False, out, manifest)
    # CNAME and the source map of each documentation site; the home link of both sites, the OpenDMA link
    assert counts["dropped"] == 3 and counts["relative"] == 2 and counts["absolute"] == 1
    m = json.loads(manifest.read_text(encoding="utf-8"))
    assert m["format"] == "openspacehdl-portal" and m["website"]["commit"] == "w" * 40
    assert m["sites"]["openwire"] == {"repository": "openwire", "commit": "a" * 40, "config": "tools/docs",
                                      "python": "3.12", "constraints": "c" * 64, "glightbox": True}
    assert set(m["files"]) == set(portal._files(out))
    assert m["files"]["index.html"]["license"] == "MIT AND CC-BY-4.0"
    assert m["files"]["openwire/index.html"]["license"] == f"{PSI} AND CC-BY-4.0 AND Apache-2.0"
    assert m["files"]["open-logic-ft/index.html"]["sha256"] == portal.sha256((out / "open-logic-ft/index.html")
                                                                             .read_bytes())
    assert (out / "index.html").read_text(encoding="utf-8") == (
        '<a href="https://github.com/x">g</a><a href="/openwire/">w</a>'
        '<a href="https://openspacehdl.org/opendma/">d</a>')
    assert (out / "openwire/index.html").read_text(encoding="utf-8").startswith('<a href="/">home</a>')
    assert not (out / "CNAME").exists() and not list(out.rglob("*.map"))


@pytest.mark.parametrize("website_extra,docs_extra,message", [
    ({"x.html": '<script src="https://cdn.example/a.js"></script>'}, None, "L11: x.html: script https://cdn.example"),
    ({"openwire/old.html": "x"}, None, "L11: the website has a path openwire/"),
    (None, {"page.html": '<a href="/openwire/missing.html">m</a>'}, "L11: openwire/page.html: /openwire/missing.html"),
    (None, {"assets/external/x.js": ""}, "L7: openwire/assets/external/x.js has no licence"),
    ({"LICENSE": b"changed"}, None, "LICENSE differs from src/openspacehdl/licenses/MIT-website.txt"),
    (None, {"assets/fonts/Sora-OFL.txt": b"other"}, "Sora-OFL.txt differs from src/openspacehdl/licenses/OFL-1.1"),
])
def test_build_stops_on_a_violation_and_writes_nothing(tmp_path, monkeypatch, website_extra, docs_extra, message):
    lock = fixture_world(tmp_path, monkeypatch, website_extra, docs_extra)
    out, manifest = tmp_path / "out", tmp_path / "portal.json"
    write(out, {"old.html": "previous portal"})
    with pytest.raises(portal.Violation) as e:
        portal.build(lock, tmp_path / "site", tmp_path / "repos", tmp_path / "work", {}, False, out, manifest)
    assert message in str(e.value)
    assert portal._files(out) == ["old.html"] and not manifest.exists()


def test_build_stops_when_glightbox_lost_its_anchors(tmp_path, monkeypatch):
    lock = fixture_world(tmp_path, monkeypatch, docs_extra={"index.html": "<p>no anchors</p>"})
    with pytest.raises(portal.Violation, match="openwire uses glightbox but has no glightbox anchor"):
        portal.build(lock, tmp_path / "site", tmp_path / "repos", tmp_path / "work", {}, False, tmp_path / "out",
                     tmp_path / "portal.json")
