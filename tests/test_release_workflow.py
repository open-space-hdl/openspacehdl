"""Tests of the publishing workflow .github/workflows/release.yml (docs/release.md, section 5): it is the only workflow
that can request an OIDC token, it never builds or checks out code in the job that holds the token, and every action
it uses is pinned to a commit."""

import re
from pathlib import Path

import pytest
import yaml

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"


def release() -> dict:
    return yaml.safe_load(RELEASE.read_text(encoding="utf-8"))


def triggers(workflow: dict) -> dict:
    # PyYAML reads the key `on` as the boolean true (YAML 1.1)
    return workflow.get("on", workflow.get(True))


def steps_using(job: dict) -> list[str]:
    return [step["uses"] for step in job["steps"] if "uses" in step]


def test_only_the_release_workflow_requests_an_oidc_token():
    files = sorted(WORKFLOWS.glob("*.y*ml"))
    assert RELEASE in files
    with_token = [f.name for f in files if "id-token" in f.read_text(encoding="utf-8")]
    assert with_token == ["release.yml"]


def test_the_release_workflow_runs_on_a_published_release_or_by_hand_only():
    on = triggers(release())
    assert sorted(on) == ["release", "workflow_dispatch"]
    assert on["release"] == {"types": ["published"]}
    assert list(on["workflow_dispatch"]["inputs"]) == ["tag"]


def test_the_release_workflow_grants_no_permission_by_default():
    assert release()["permissions"] == {}


def test_the_job_check_reads_only_and_skips_pre_releases():
    check = release()["jobs"]["check"]
    assert check["permissions"] == {"contents": "read"}
    assert "github.event.release.prerelease == false" in check["if"]
    assert "environment" not in check
    assert steps_using(check) == []


def test_the_job_publish_waits_in_the_environment_pypi_and_never_checks_out():
    publish = release()["jobs"]["publish"]
    assert publish["needs"] == "check"
    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    uses = steps_using(publish)
    assert [u.split("@")[0] for u in uses] == ["pypa/gh-action-pypi-publish"]
    assert not any(u.startswith("actions/checkout") for u in uses)


@pytest.mark.parametrize("job", ["check", "publish"])
def test_every_action_of_the_release_workflow_is_pinned_to_a_commit(job):
    for uses in steps_using(release()["jobs"][job]):
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", uses), uses


def test_the_file_limit_of_the_release_workflow_is_that_of_the_project():
    with open(ROOT / "pyproject.toml", "rb") as f:
        limit_mib = tomllib.load(f)["tool"]["openspacehdl"]["pypi-file-limit-mb"]
    assert release()["env"]["FILE_LIMIT_BYTES"] == limit_mib * 1024 * 1024
