"""A small, consistent world of Git repositories for the tests of the tools: website, reference-systems, two cores,
Open Logic FT with its submodule en_cl_fix, and UVVM. conftest.py builds it once per session and copies it per test.
"""

import importlib.util
import json
import shutil
from pathlib import Path

from gitrepo import commit, git, make_repo, publish

ROOT = Path(__file__).resolve().parent.parent
LIC = ROOT / "src" / "openspacehdl" / "licenses"
PSI = (LIC / "PSI-HDL-1.0.txt").read_text(encoding="utf-8")
LGPL = (LIC / "LGPL-2.1.txt").read_text(encoding="utf-8")
APACHE = (LIC / "Apache-2.0.txt").read_text(encoding="utf-8")
MIT_FIX = (LIC / "MIT-en_cl_fix.md").read_text(encoding="utf-8")
LICENSES = {"License.txt": PSI, "LGPL2_1.txt": LGPL}
UVVM_COMPONENTS = ("uvvm_util", "uvvm_vvc_framework", "bitvis_vip_scoreboard", "bitvis_vip_clock_generator",
                   "bitvis_vip_axilite", "bitvis_vip_axistream", "bitvis_vip_axi")
TD = "uvvm_vvc_framework/src_target_dependent/td_queue_pkg.vhd"
FIX_URL = "https://github.com/open-logic/en_cl_fix.git"
OLO_GITMODULES = f'[submodule "3rdParty/en_cl_fix"]\n\tpath = 3rdParty/en_cl_fix\n\turl = {FIX_URL}\n'
RS_GITMODULES = (
    '[submodule "cores/opencompact"]\n\tpath = cores/opencompact\n'
    '\turl = https://github.com/open-space-hdl/opencompact.git\n'
    '[submodule "cores/open-logic-ft"]\n\tpath = cores/open-logic-ft\n'
    '\turl = https://github.com/open-space-hdl/open-logic-ft.git\n'
)
# The published Composer schemas, as the website carries them in composer/schema/
SCHEMAS = {n: (ROOT / "tests" / "fixtures" / "composer" / "schema" / n).read_text(encoding="utf-8")
           for n in ("system-1.json", "system-2.json")}
# Clones with a bare remote origin next to them, relative to the repos directory
REMOTES = ("openwire", "opencompact", "open-logic-ft", "open-logic-ft/3rdParty/en_cl_fix", "reference-systems")


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_tool", ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def uvvm_files() -> dict[str, str]:
    """A UVVM repository: every component with its compile order; the VVC of axilite also uses a target file."""
    files = {"LICENSE": APACHE, "uvvm_util/doc/manual.txt": "doc\n", TD: "-- td\n"}
    for c in UVVM_COMPONENTS:
        extra = f"../../{TD}\n" if c == "bitvis_vip_axilite" else ""
        files[f"{c}/script/compile_order.txt"] = f"# library {c}\n../src/{c}_pkg.vhd\n{extra}"
        files[f"{c}/src/{c}_pkg.vhd"] = f"-- {c}\n"
    return files


def build(tmp_path: Path) -> dict:
    """The world in tmp_path: the clones in tmp_path/repos, UVVM in tmp_path/uvvm, the website in tmp_path/site."""
    repos = tmp_path / "repos"
    uvvm = tmp_path / "uvvm"
    uv = make_repo(uvvm, uvvm_files())
    owr = make_repo(repos / "openwire", {**LICENSES, "compile_order.txt": "hdl/a.vhd\n", "hdl/a.vhd": "-- a\n",
                                         "sw/owr_regs.h": "#define OWR 1\n", "hdl/a_tb.vhd": "-- tb\n"},
                    {"uvvm": uv})
    git(repos / "openwire", "tag", "v0.1.0")
    ocp = make_repo(repos / "opencompact", {**LICENSES, "compile_order.txt": "hdl/b.vhd\n", "hdl/b.vhd": "-- b\n",
                                            "hdl/ocp_pa/compile_order_sim.txt": "hdl/ocp_pa/sim/m.vhd\n",
                                            "hdl/ocp_pa/sim/m.vhd": "-- model\n"},
                    {"uvvm": uv})
    git(repos / "opencompact", "tag", "-a", "v0.1.0", "-m", "first release")
    ocp = commit(repos / "opencompact", {"hdl/b.vhd": "-- b, fixed\n"})
    git(repos / "opencompact", "tag", "-a", "v0.1.1", "-m", "release")
    olo_dir = repos / "open-logic-ft"
    make_repo(olo_dir, {**LICENSES, "doc/readme.md": "doc\n"})
    git(olo_dir, "branch", "-m", "fault-tolerant")
    fix_dir = olo_dir / "3rdParty" / "en_cl_fix"
    fix = make_repo(fix_dir, {"LICENSE.md": MIT_FIX, "hdl/en_cl_fix_pkg.vhd": "-- fix\n"})
    git(fix_dir, "branch", "-m", "open-logic")
    olo = commit(olo_dir, {".gitmodules": OLO_GITMODULES,
                           "compile_order.txt": "3rdParty/en_cl_fix/hdl/en_cl_fix_pkg.vhd\nsrc/c.vhd\n",
                           "src/c.vhd": "-- c\n"}, {"3rdParty/en_cl_fix": fix})
    git(olo_dir, "tag", "-a", "4.7.0-ft.8", "-m", "ft.8")
    catalog = {
        "format": "open-space-composer-catalog", "formatVersion": 1, "id": "abcdef012345",
        "sources": [
            {"id": "openwire", "name": "OpenWire", "repo": "openwire", "commit": owr, "library": "openwire",
             "fileList": "compile_order.txt", "fileListFormat": "files", "verifiedWith": "4.7.0-ft.6"},
            {"id": "opencompact", "name": "OpenCompact", "repo": "opencompact", "commit": ocp,
             "library": "opencompact", "fileList": "compile_order.txt", "fileListFormat": "files",
             "verifiedWith": "4.7.0-ft.6"},
            {"id": "olo", "name": "Open Logic FT", "repo": "open-logic-ft", "tag": "4.7.0-ft.8", "commit": olo,
             "library": "olo", "fileList": "compile_order.txt", "fileListFormat": "files"},
        ],
    }
    site = tmp_path / "site"
    web = make_repo(site, {
        "assets/composer/catalog.json": json.dumps(catalog),
        "assets/composer/js/model/serialize.js":
            "export const GENERATOR = { name: 'Open Space Composer', version: '0.9.8-beta' };\n",
        "_data/projects.yml": "- name: OpenWire\n  repo: openwire\n  public: true\n  trl: 3\n"
                              "- name: OpenCompact\n  repo: opencompact\n  public: true\n  trl: 3\n",
        **{f"composer/schema/{n}": text for n, text in SCHEMAS.items()},
    })
    rs = repos / "reference-systems"
    make_repo(rs, {**LICENSES, ".gitmodules": RS_GITMODULES, "tools/composer_ref.txt": web + "\n",
                   "systems/s/s.composer.json": "{}\n", "sim/tb/rs_far_end.vhd": "-- far end\n",
                   "docs/notes.md": "notes\n"},
              {"cores/opencompact": ocp, "cores/open-logic-ft": olo})
    git(rs, "tag", "-a", "v0.1.1", "-m", "release")
    for r in REMOTES:
        publish(repos / r)
    return {"tmp": tmp_path, "web": web, "owr": owr, "ocp": ocp, "olo": olo, "uv": uv, "fix": fix}


def copy(template: dict, tmp_path: Path) -> dict:
    """A copy of the template world in tmp_path, with the remotes pointing at the copies."""
    for name in ("repos", "site", "uvvm"):
        shutil.copytree(template["tmp"] / name, tmp_path / name)
    for r in REMOTES:
        git(tmp_path / "repos" / r, "remote", "set-url", "origin", str((tmp_path / "repos" / r).with_name(
            Path(r).name + ".git")))
    return {**template, "tmp": tmp_path, "repos": tmp_path / "repos", "site": tmp_path / "site",
            "rs": tmp_path / "repos" / "reference-systems", "uvvm": tmp_path / "uvvm"}


def lock_args(w: dict, *extra: str, tag: str = "v0.1.1", out: Path | None = None) -> list[str]:
    return ["--site", str(w["site"]), "--site-commit", "HEAD", "--refsys", str(w["rs"]), "--refsys-tag", tag,
            "--repos", str(w["repos"]), "--uvvm", str(w["uvvm"]), "--out", str(out or w["tmp"] / "lock.json"),
            *extra]
