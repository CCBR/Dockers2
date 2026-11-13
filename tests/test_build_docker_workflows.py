"""Check the Docker build workflows' registry and action configuration."""

from pathlib import Path
import os
import re
import subprocess

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WORKFLOW_NAMES = ["auto", "manual", "dispatch"]
RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+")


def load_workflow(name):
    """Load a Docker build workflow."""
    return yaml.safe_load((WORKFLOWS / f"build-docker-{name}.yml").read_text())


def build_step(workflow):
    """Find the composite Docker build step."""
    return next(
        step
        for step in workflow["jobs"]["build-docker"]["steps"]
        if step.get("uses", "").startswith("CCBR/actions/build-docker@")
    )


def ccbr_action_refs(workflow):
    """Collect the refs of all CCBR/actions steps in a workflow."""
    return [
        step["uses"].split("@", 1)[1]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("CCBR/actions/")
    ]


def test_build_workflows_pin_one_ccbr_actions_release():
    refs = {
        ref for name in WORKFLOW_NAMES for ref in ccbr_action_refs(load_workflow(name))
    }
    assert len(refs) == 1, f"CCBR/actions refs differ across workflows: {refs}"
    assert RELEASE_TAG.fullmatch(refs.pop())


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_build_workflows_have_package_permissions(name):
    workflow = load_workflow(name)
    job = workflow["jobs"]["build-docker"]
    assert build_step(workflow)
    assert workflow["permissions"]["packages"] == "write"
    if "permissions" in job:
        assert job["permissions"]["packages"] == "write"


def test_automatic_workflow_handles_forks_and_pushes():
    workflow = load_workflow("auto")
    step = build_step(workflow)
    assert step["with"]["push"] is True
    assert step["with"]["registries"] == (
        "${{ github.event.pull_request.head.repo.fork && 'dockerhub' "
        "|| 'dockerhub,ghcr' }}"
    )
    assert any(
        step.get("uses", "").startswith("CCBR/actions/changed-files@")
        for step in workflow["jobs"]["get-files"]["steps"]
    )
    assert step["with"]["platforms"] == "${{ steps.platforms.outputs.platforms }}"


@pytest.mark.parametrize(
    ("declaration", "expected", "should_succeed"),
    [
        ("", "linux/amd64", True),
        ("# build-platforms: linux/amd64, linux/arm64\n", "linux/amd64,linux/arm64", True),
        ("# build-platforms: linux/arm64\n", "linux/arm64", True),
        ("# build-platforms:\n", "", False),
        ("# build-platforms: linux/amd64,linux/amd64\n", "", False),
        ("# build-platforms: linux/amd64,\n", "", False),
        ("# build-platforms: linux/ppc64le\n", "", False),
        (
            "# build-platforms: linux/amd64\n# build-platforms: linux/arm64\n",
            "",
            False,
        ),
    ],
)
def test_auto_workflow_resolves_dockerfile_platforms(
    tmp_path, declaration, expected, should_succeed
):
    dockerfile = tmp_path / "Dockerfile.v1"
    dockerfile.write_text(f"{declaration}FROM ubuntu:26.04\n")
    output = tmp_path / "github_output"
    step = next(
        step
        for step in load_workflow("auto")["jobs"]["build-docker"]["steps"]
        if step.get("id") == "platforms"
    )
    env = os.environ.copy()
    env.update(
        GITHUB_WORKSPACE=str(tmp_path),
        DOCKERFILE_PATH="Dockerfile.v1",
        GITHUB_OUTPUT=str(output),
    )

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert (result.returncode == 0) is should_succeed, result.stderr
    if should_succeed:
        assert output.read_text() == f"platforms={expected}\n"


def test_manual_workflow_preserves_push_input():
    step = build_step(load_workflow("manual"))
    assert step["with"]["registries"] == "dockerhub,ghcr"
    assert step["with"]["push"] == "${{ github.event.inputs.push }}"


def test_manual_workflow_forwards_optional_platforms_input():
    workflow = load_workflow("manual")
    # PyYAML parses the bare `on` key as boolean True.
    platforms = workflow[True]["workflow_dispatch"]["inputs"]["platforms"]
    assert platforms["required"] is False
    assert platforms["default"] == ""
    step = build_step(workflow)
    assert step["with"]["platforms"] == "${{ github.event.inputs.platforms }}"


def test_dispatch_workflow_requests_app_token_permissions():
    workflow = load_workflow("dispatch")
    step = build_step(workflow)
    assert step["with"]["registries"] == "dockerhub,ghcr"
    assert step["with"]["push"] is True

    token = next(
        step
        for step in workflow["jobs"]["build-docker"]["steps"]
        if step.get("uses", "").startswith("actions/create-github-app-token@")
    )
    assert token["with"]["client-id"] == "${{ vars.CCBR_BOT_CLIENT_ID }}"
    for permission in ("packages", "contents", "pull-requests"):
        assert token["with"][f"permission-{permission}"] == "write"
