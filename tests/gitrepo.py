"""Small Git repositories for the tests of the tools."""

import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def make_repo(path: Path, files: dict[str, str], links: dict[str, str] | None = None) -> str:
    """A new repository with one commit of these files and submodule links; returns the commit."""
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.org")
    git(path, "config", "commit.gpgsign", "false")
    return commit(path, files, links)


def commit(path: Path, files: dict[str, str], links: dict[str, str] | None = None) -> str:
    """Writes the files and submodule links and commits them; returns the commit."""
    for name, text in files.items():
        f = path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        git(path, "add", name)
    for name, sha in (links or {}).items():
        git(path, "update-index", "--add", "--cacheinfo", f"160000,{sha},{name}")
    git(path, "commit", "-q", "--allow-empty", "-m", "state")
    return git(path, "rev-parse", "HEAD")


def publish(path: Path) -> None:
    """Pushes the branch and every tag that exists now to the remote origin, a bare repository next to the clone."""
    bare = path.with_name(path.name + ".git")
    if not bare.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        git(path, "remote", "add", "origin", str(bare))
    git(path, "push", "-q", "origin", "main", "--tags")
