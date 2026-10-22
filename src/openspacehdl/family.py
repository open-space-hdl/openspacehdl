"""The projects of the family, as the website shows them (data/family.json, written by tools/family_data.py)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    summary: str


@dataclass(frozen=True)
class Project:
    name: str
    group: str
    tagline: tuple[str, ...]
    summary: str
    public: bool
    repo: str | None = None
    docs: bool = False
    trl: int | None = None
    trl_status: str | None = None


@dataclass(frozen=True)
class Family:
    site: str
    github: str
    source_commit: str
    groups: tuple[Group, ...]
    projects: tuple[Project, ...]

    def docs_url(self, project: Project) -> str | None:
        """Documentation site of a public project, or None."""
        return f"{self.site}/{project.repo}/" if project.public and project.docs else None

    def source_url(self, project: Project) -> str | None:
        """Repository of a public project, or None."""
        return f"{self.github}/{project.repo}" if project.public else None

    def members(self, group: Group) -> list[Project]:
        return [p for p in self.projects if p.group == group.id]

    def find(self, name: str) -> Project | None:
        """The project with this name or repository name, ignoring case, spaces and hyphens."""
        key = _key(name)
        for p in self.projects:
            if key in (_key(p.name), _key(p.repo or "")):
                return p
        return None


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def load() -> Family:
    data = json.loads(resources.files("openspacehdl").joinpath("data/family.json").read_text(encoding="utf-8"))
    return Family(
        site=data["site"],
        github=data["github"],
        source_commit=data["source"]["commit"],
        groups=tuple(Group(**g) for g in data["groups"]),
        projects=tuple(Project(**{**p, "tagline": tuple(p["tagline"])}) for p in data["projects"]),
    )
