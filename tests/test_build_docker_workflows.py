"""Check the Docker build workflows' registry and action configuration."""

from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
ACTION_REF = "copilot/update-build-docker-action"


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


@pytest.mark.parametrize("name", ["auto", "manual", "dispatch"])
def test_build_workflows_use_test_branch_and_package_permissions(name):
    workflow = load_workflow(name)
    job = workflow["jobs"]["build-docker"]
    assert build_step(workflow)["uses"] == f"CCBR/actions/build-docker@{ACTION_REF}"
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
        step.get("uses") == f"CCBR/actions/changed-files@{ACTION_REF}"
        for step in workflow["jobs"]["get-files"]["steps"]
    )


def test_manual_workflow_preserves_push_input():
    step = build_step(load_workflow("manual"))
    assert step["with"]["registries"] == "dockerhub,ghcr"
    assert step["with"]["push"] == "${{ github.event.inputs.push }}"


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
