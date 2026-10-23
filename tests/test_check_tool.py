"""Tests of tools/check.py: the steps of the real build."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check = load("check")
BASE = ["--real-build", "--site", "site", "--refsys", "rs", "--refsys-tag", "v0.2.0", "--repos", "repos"]


def steps(monkeypatch, argv):
    """The steps of the real build for a command line, from the arguments main() hands to real_build()."""
    seen = []
    monkeypatch.setattr(check, "real_build", lambda args: seen.append(args) or 0)
    assert check.main(argv) == 0
    return dict(check.build_steps(seen[0], "py"))


def test_the_lock_takes_the_website_commit_of_a_release(monkeypatch):
    # rule L4: the website commit of the lock is the one tools/composer_ref.txt of the reference-systems tag names
    assert steps(monkeypatch, [*BASE, "--site-commit", "8fa23f0"])["lock"] == [
        "py", "tools/lock.py", "--site", "site", "--site-commit", "8fa23f0", "--refsys", "rs", "--refsys-tag", "v0.2.0",
        "--repos", "repos"]


def test_without_a_website_commit_the_lock_keeps_its_default(monkeypatch):
    assert "--site-commit" not in steps(monkeypatch, BASE)["lock"]


def test_only_the_lock_gets_the_website_commit(monkeypatch):
    s = steps(monkeypatch, [*BASE, "--site-commit", "8fa23f0"])
    assert list(s) == ["lock", "snapshot", "portal", "wheel"]
    assert all("--site-commit" not in cmd for name, cmd in s.items() if name != "lock")


def test_waived_rules_reach_the_lock_and_allow_the_later_steps(monkeypatch):
    s = steps(monkeypatch, [*BASE, "--waive", "L2", "--waive", "L4", "--python", "3.12=py312"])
    assert s["lock"][-4:] == ["--waive", "L2", "--waive", "L4"]
    assert s["snapshot"][-1] == "--allow-waived" and s["portal"][-3:] == ["--python", "3.12=py312", "--allow-waived"]
