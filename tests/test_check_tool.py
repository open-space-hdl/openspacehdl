"""Tests of tools/check.py: the report of a gate and the steps of the real build."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check = load("check")
BASE = ["--real-build", "--site", "site", "--refsys", "rs", "--refsys-tag", "v0.2.0", "--repos", "repos"]


def gate(capsys, code: str, **kw) -> tuple[bool, str]:
    ok = check.run("g", [sys.executable, "-c", code], **kw)
    return ok, capsys.readouterr().out


def test_a_gate_with_summary_reports_the_last_line_of_its_output(capsys):
    assert gate(capsys, "print('collected'); print('308 passed, 1 skipped in 2.0s')", summary=True) == (
        True, "ok   g: 308 passed, 1 skipped in 2.0s\n")


def test_a_gate_without_summary_reports_only_its_name(capsys):
    assert gate(capsys, "print('308 passed')") == (True, "ok   g\n")


def test_a_failing_gate_reports_its_exit_status_and_output(capsys):
    ok, out = gate(capsys, "import sys; print('1 failed'); sys.exit(1)", summary=True)
    assert not ok and out.startswith("FAIL g (exit status 1): ") and out.endswith("1 failed\n")


def test_the_pytest_gate_reports_its_counts(monkeypatch):
    # the CI log shows the counts of pytest (passed, skipped); the first gate that fails stops the run
    seen = []
    monkeypatch.setattr(check, "run", lambda name, cmd, **kw: seen.append((name, cmd[1:3], kw)) or False)
    assert check.main(["--no-markdownlint"]) == 1
    assert seen == [("pytest", ["-m", "pytest"], {"summary": True})]


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
