"""Lock manifest of a package version (data/lock.json): the cores, Open Logic FT and reference systems it pins.

tools/lock.py gathers the inputs from the repositories and writes the manifest when the package is built. The rules
it applies and the manifest it writes are defined here, on plain data, so that they are tested without git
(docs/design.md, section 3).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources

from openspacehdl.errors import LockError

FORMAT = "openspacehdl-lock"
VERSION = 1
ORG = "open-space-hdl"
WEBSITE_REPO = "open-space-hdl.github.io"
REFSYS_REPO = "reference-systems"
OLO_ID = "olo"
UVVM_REPO = "UVVM/UVVM"
RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.message}"


@dataclass
class Inputs:
    """What the rules check, gathered from the repositories at the pinned states."""

    website_commit: str
    catalog_id: str
    generator: str
    # assets/composer/catalog.json, key "sources": one entry per repository, Open Logic FT with id "olo"
    catalog_sources: list[dict]
    # _data/projects.yml of the website, by repository name: "public", "trl"
    cards: dict[str, dict]
    refsys_tag: str
    refsys_commit: str
    # submodules cores/<repository> of reference-systems at its tag: repository name -> commit
    refsys_submodules: dict[str, str]
    # tools/composer_ref.txt of reference-systems at its tag, None when the file is missing
    refsys_composer_ref: str | None
    # release and other tags of every repository: repository name -> tag -> commit (annotated tags peeled)
    tags: dict[str, dict[str, str]]
    # tags of every repository that exist on its remote: repository name -> tag names
    published_tags: dict[str, set[str]]
    # submodules of Open Logic FT at its tag: path -> commit
    olo_submodules: dict[str, str]
    # commit of the uvvm submodule of every core that has one: repository name -> commit
    uvvm: dict[str, str]
    # simulation models of vendor adapters: repository name -> adapter -> path of its compile_order_sim.txt
    models: dict[str, dict[str, str]] = field(default_factory=dict)
    # first line of the licence file: repository name -> licence
    licenses: dict[str, str] = field(default_factory=dict)


def _short(commit: str | None) -> str:
    return (commit or "none")[:7]


def _tags_of(inputs: Inputs, repo: str, commit: str | None) -> list[str]:
    return sorted(t for t, c in inputs.tags.get(repo, {}).items() if c == commit)


def _release_tag(inputs: Inputs, repo: str, commit: str | None) -> str | None:
    """The release tag vX.Y.Z of this commit; the highest when there are several."""
    tags = [t for t in _tags_of(inputs, repo, commit) if RELEASE_TAG.fullmatch(t)]
    return max(tags, key=lambda t: tuple(int(x) for x in t[1:].split("."))) if tags else None


def _named(inputs: Inputs, repo: str, commit: str | None) -> str:
    tag = _release_tag(inputs, repo, commit)
    return f"{_short(commit)} ({tag})" if tag else _short(commit)


def split_sources(inputs: Inputs) -> tuple[dict | None, list[dict]]:
    """The Open Logic FT source and the cores, in the order of the catalog."""
    olo = next((s for s in inputs.catalog_sources if s["id"] == OLO_ID), None)
    return olo, [s for s in inputs.catalog_sources if s["id"] != OLO_ID]


def check(inputs: Inputs) -> list[Violation]:
    """Every violation of the rules L1 to L5 and L10 (docs/design.md, section 3.3)."""
    out: list[Violation] = []
    olo, cores = split_sources(inputs)

    # L1: release tags only, and published
    for s in cores:
        repo = s["repo"]
        tag = _release_tag(inputs, repo, s.get("commit"))
        if tag is None:
            out.append(Violation("L1", f"{repo}: the catalog pins {_short(s.get('commit'))}, which is not the "
                                       f"commit of a release tag vX.Y.Z"))
        elif tag not in inputs.published_tags.get(repo, set()):
            out.append(Violation("L1", f"{repo}: the release tag {tag} is not on the remote of the repository"))
    if not RELEASE_TAG.fullmatch(inputs.refsys_tag):
        out.append(Violation("L1", f"{REFSYS_REPO}: {inputs.refsys_tag} is not a release tag vX.Y.Z"))
    elif inputs.tags.get(REFSYS_REPO, {}).get(inputs.refsys_tag) != inputs.refsys_commit:
        out.append(Violation("L1", f"{REFSYS_REPO}: the tag {inputs.refsys_tag} is not the commit "
                                   f"{_short(inputs.refsys_commit)}"))
    elif inputs.refsys_tag not in inputs.published_tags.get(REFSYS_REPO, set()):
        out.append(Violation("L1", f"{REFSYS_REPO}: the release tag {inputs.refsys_tag} is not on its remote"))

    # L2: the same commit in the catalog and in reference-systems
    for s in cores:
        repo = s["repo"]
        rs = inputs.refsys_submodules.get(repo)
        if rs is not None and rs != s.get("commit"):
            out.append(Violation("L2", f"{repo}: the catalog pins {_named(inputs, repo, s.get('commit'))}, "
                                       f"{REFSYS_REPO} {inputs.refsys_tag} pins {_named(inputs, repo, rs)}"))

    # L3: one Open Logic FT
    if olo is None:
        out.append(Violation("L3", "the catalog has no Open Logic FT source (id olo)"))
    else:
        repo, tag = olo["repo"], olo.get("tag")
        tag_commit = inputs.tags.get(repo, {}).get(tag) if tag else None
        rs = inputs.refsys_submodules.get(repo)
        if not tag:
            out.append(Violation("L3", f"{repo}: the catalog pins Open Logic FT without a tag"))
        elif tag_commit is None:
            out.append(Violation("L3", f"{repo}: the tag {tag} of the catalog does not exist"))
        elif tag not in inputs.published_tags.get(repo, set()):
            out.append(Violation("L3", f"{repo}: the tag {tag} is not on the remote of the repository"))
        elif olo.get("commit") not in (None, tag_commit):
            out.append(Violation("L3", f"{repo}: the catalog names {tag} with {_short(olo.get('commit'))}, the tag "
                                       f"is {_short(tag_commit)}"))
        if tag_commit is not None and rs != tag_commit:
            out.append(Violation("L3", f"{repo}: the catalog pins {tag} ({_short(tag_commit)}), {REFSYS_REPO} "
                                       f"{inputs.refsys_tag} pins {_short(rs)}"))

    # L4: the website commit the reference systems were checked against
    if inputs.refsys_composer_ref is None:
        out.append(Violation("L4", f"{REFSYS_REPO} {inputs.refsys_tag} has no tools/composer_ref.txt"))
    elif inputs.refsys_composer_ref != inputs.website_commit:
        out.append(Violation("L4", f"{REFSYS_REPO} {inputs.refsys_tag} was checked against website "
                                   f"{_short(inputs.refsys_composer_ref)}, the lock takes website "
                                   f"{_short(inputs.website_commit)}"))

    # L5: public cards only
    for s in cores:
        card = inputs.cards.get(s["repo"])
        if card is None:
            out.append(Violation("L5", f"{s['repo']}: no project card on the website"))
        elif not card.get("public"):
            out.append(Violation("L5", f"{s['repo']}: the project card is not public"))

    # L10: one UVVM
    commits = sorted(set(inputs.uvvm.values()))
    if len(commits) != 1:
        found = ", ".join(f"{r} {_short(c)}" for r, c in sorted(inputs.uvvm.items())) or "none"
        out.append(Violation("L10", f"the cores do not pin one UVVM commit: {found}"))
    return out


def build(inputs: Inputs, package_version: str) -> dict:
    """The manifest of these inputs; raises LockError with every violation when a rule fails."""
    violations = check(inputs)
    if violations:
        raise LockError("the inputs break the consistency rules:\n" + "\n".join(f"  {v}" for v in violations))
    olo, cores = split_sources(inputs)
    assert olo is not None
    return {
        "format": FORMAT,
        "version": VERSION,
        "package": package_version,
        "website": {
            "repository": f"{ORG}/{WEBSITE_REPO}",
            "commit": inputs.website_commit,
            "catalog": inputs.catalog_id,
            "generator": inputs.generator,
        },
        "referenceSystems": {
            "repository": f"{ORG}/{REFSYS_REPO}",
            "tag": inputs.refsys_tag,
            "commit": inputs.refsys_commit,
            "license": inputs.licenses.get(REFSYS_REPO),
        },
        "openLogic": {
            "id": OLO_ID,
            "name": olo.get("name", "Open Logic FT"),
            "repository": f"{ORG}/{olo['repo']}",
            "tag": olo["tag"],
            "commit": inputs.tags[olo["repo"]][olo["tag"]],
            "library": olo["library"],
            "fileList": olo["fileList"],
            "fileListFormat": olo["fileListFormat"],
            "submodules": dict(sorted(inputs.olo_submodules.items())),
            "license": inputs.licenses.get(olo["repo"]),
        },
        "uvvm": {"repository": UVVM_REPO, "commit": next(iter(inputs.uvvm.values()))},
        "cores": [
            {
                "id": s["id"],
                "name": s["name"],
                "repository": f"{ORG}/{s['repo']}",
                "tag": _release_tag(inputs, s["repo"], s["commit"]),
                "commit": s["commit"],
                "library": s["library"],
                "fileList": s["fileList"],
                "fileListFormat": s["fileListFormat"],
                "verifiedWith": s.get("verifiedWith"),
                "models": dict(sorted(inputs.models.get(s["repo"], {}).items())),
                "trl": inputs.cards[s["repo"]].get("trl"),
                "license": inputs.licenses.get(s["repo"]),
            }
            for s in cores
        ],
    }


def dumps(manifest: dict) -> str:
    """The text of data/lock.json."""
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Core:
    id: str
    name: str
    repository: str
    tag: str
    commit: str
    library: str
    file_list: str
    file_list_format: str
    verified_with: str | None
    models: dict[str, str]
    trl: int | None
    license: str | None


@dataclass(frozen=True)
class Lock:
    package: str
    website_commit: str
    catalog: str
    generator: str
    refsys_tag: str
    refsys_commit: str
    olo_tag: str
    olo_commit: str
    uvvm_commit: str
    cores: tuple[Core, ...]

    @staticmethod
    def from_dict(d: dict) -> Lock:
        if d.get("format") != FORMAT or d.get("version") != VERSION:
            raise LockError(f"the lock manifest has format {d.get('format')!r} version {d.get('version')!r}; this "
                            f"package reads {FORMAT} version {VERSION}")
        return Lock(
            package=d["package"],
            website_commit=d["website"]["commit"],
            catalog=d["website"]["catalog"],
            generator=d["website"]["generator"],
            refsys_tag=d["referenceSystems"]["tag"],
            refsys_commit=d["referenceSystems"]["commit"],
            olo_tag=d["openLogic"]["tag"],
            olo_commit=d["openLogic"]["commit"],
            uvvm_commit=d["uvvm"]["commit"],
            cores=tuple(
                Core(
                    id=c["id"], name=c["name"], repository=c["repository"], tag=c["tag"], commit=c["commit"],
                    library=c["library"], file_list=c["fileList"], file_list_format=c["fileListFormat"],
                    verified_with=c.get("verifiedWith"), models=dict(c.get("models", {})), trl=c.get("trl"),
                    license=c.get("license"),
                )
                for c in d["cores"]
            ),
        )


def load() -> Lock:
    """The lock manifest of this package version."""
    f = resources.files("openspacehdl").joinpath("data/lock.json")
    if not f.is_file():
        from openspacehdl import __version__

        raise LockError(f"openspacehdl {__version__} carries no lock manifest: this version lists the family only "
                        f"and contains no cores")
    return Lock.from_dict(json.loads(f.read_text(encoding="utf-8")))
