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
    ("event_name", "event_action", "initial_files", "api_changed_files", "event_files", "expected"),
    [
        ("pull_request", "synchronize", "", "", '["Dockerfile.v2"]', "[]"),
        (
            "pull_request",
            "synchronize",
            "",
            "Dockerfile.v3",
            '["Dockerfile.v2","Dockerfile.v3"]',
            '["Dockerfile.v2","Dockerfile.v3"]',
        ),
        ("pull_request", "opened", "", "", '["Dockerfile.v2"]', '["Dockerfile.v2"]'),
        ("push", "", '["Dockerfile.v2"]', "", "", '["Dockerfile.v2"]'),
    ],
)
def test_auto_workflow_selects_pr_synchronize_dockerfiles(
    tmp_path,
    event_name,
    event_action,
    initial_files,
    api_changed_files,
    event_files,
    expected,
):
    workflow = load_workflow("auto")
    job = workflow["jobs"]["get-files"]
    assert job["outputs"]["json"] == "${{ steps.select-files.outputs.json }}"
    steps = job["steps"]
    synchronize_check = next(step for step in steps if step.get("id") == "synchronize-files")
    assert synchronize_check["if"] == (
        "github.event_name == 'pull_request' && github.event.action == 'synchronize'"
    )
    assert "github.event.before" in synchronize_check["env"]["BEFORE_SHA"]
    assert "github.event.after" in synchronize_check["env"]["AFTER_SHA"]

    synchronized_files = ""
    if event_name == "pull_request" and event_action == "synchronize":
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            "#!/bin/bash\n"
            '[[ "$1" == "api" ]]\n'
            'printf "%s\\n" "$MOCK_GH_OUTPUT"\n'
        )
        fake_gh.chmod(0o755)
        synchronize_output = tmp_path / "synchronize_output"
        env = os.environ.copy()
        env.update(
            PATH=f"{fake_bin}:{env['PATH']}",
            GH_TOKEN="test-token",
            BEFORE_SHA="before",
            AFTER_SHA="after",
            HEAD_REPOSITORY="owner/repo",
            MOCK_GH_OUTPUT=api_changed_files,
            GITHUB_OUTPUT=str(synchronize_output),
        )
        result = subprocess.run(
            [
                "bash",
                "--noprofile",
                "--norc",
                "-e",
                "-o",
                "pipefail",
                "-c",
                synchronize_check["run"],
            ],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        synchronized_files = synchronize_output.read_text().split("=", 1)[1].strip()

    select_step = next(step for step in steps if step.get("id") == "select-files")
    output = tmp_path / "github_output"
    env = os.environ.copy()
    env.update(
        EVENT_NAME=event_name,
        EVENT_ACTION=event_action,
        INITIAL_PUSH_FILES_JSON=initial_files,
        SYNCHRONIZE_FILES_JSON=synchronized_files,
        EVENT_FILES_JSON=event_files,
        GITHUB_OUTPUT=str(output),
    )
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", select_step["run"]],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.read_text() == f"json={expected}\n"

    build_job = workflow["jobs"]["build-docker"]
    assert "matrix.file" in build_job["concurrency"]["group"]
    assert build_job["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name == 'pull_request' }}"
    )


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
@pytest.mark.parametrize(
    ("declaration", "expected", "should_succeed"),
    [
        ("", "linux/amd64", True),
        ("# build-platforms: linux/amd64, linux/arm64\n", "linux/amd64,linux/arm64", True),
        ("# build-platforms: linux/arm64\n", "linux/arm64", True),
        ("  # build-platforms: linux/arm64, linux/amd64\n", "linux/arm64,linux/amd64", True),
        ("# build-platforms: linux/arm64", "linux/arm64", True),
        ("# build-platforms:\n", "linux/amd64", True),
        ("# build-platforms:   \n", "linux/amd64", True),
        ("# build-platforms: linux/amd64,linux/amd64\n", "", False),
        ("# build-platforms: linux/amd64,\n", "", False),
        ("# build-platforms: linux/ppc64le,linux/arm/v7\n", "linux/ppc64le,linux/arm/v7", True),
        ("# build-platforms: amd64\n", "", False),
        ("# build-platforms: linux/arm/v7/extra\n", "", False),
        (
            "# build-platforms: linux/amd64\n# build-platforms: linux/arm64\n",
            "",
            False,
        ),
    ],
)
def test_workflow_resolves_dockerfile_platforms(
    tmp_path, name, declaration, expected, should_succeed
):
    result, output = run_platform_step(tmp_path, name, declaration)
    assert (result.returncode == 0) is should_succeed, result.stderr
    if should_succeed:
        assert output.read_text() == f"platforms={expected}\n"
    else:
        assert "::error::" in result.stderr
        assert not output.exists()


def run_platform_step(tmp_path, name, declaration, override=""):
    dockerfile = tmp_path / "Dockerfile.v1"
    dockerfile.write_text(f"FROM ubuntu:26.04\n{declaration}")
    output = tmp_path / "github_output"
    workflow = load_workflow(name)
    step = next(
        step
        for step in workflow["jobs"]["build-docker"]["steps"]
        if step.get("id") == "platforms"
    )
    assert step["env"]["WORKFLOW_SHA"] == "${{ github.workflow_sha }}"
    expected_path = {
        "auto": "${{ matrix.file }}",
        "manual": "${{ inputs.dockerfile }}",
        "dispatch": "${{ steps.process-payload.outputs.new_dockerfile_path }}",
    }
    assert step["env"]["DOCKERFILE_PATH"] == expected_path[name]
    assert build_step(workflow)["with"]["platforms"] == (
        "${{ steps.platforms.outputs.platforms }}"
    )
    steps = workflow["jobs"]["build-docker"]["steps"]
    assert steps.index(step) < steps.index(build_step(workflow))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        '[[ "$1" == api ]]\n'
        '[[ "$2" == "repos/owner/repo/contents/scripts/resolve_docker_platforms.py?ref=workflow-sha" ]]\n'
        '[[ "$3" == --header && "$4" == "Accept: application/vnd.github.raw+json" ]]\n'
        'cat "$RESOLVER_SOURCE"\n'
    )
    fake_gh.chmod(0o755)
    env = os.environ.copy()
    env.update(
        PATH=f"{fake_bin}:{env['PATH']}",
        GH_TOKEN="test-token",
        WORKFLOW_SHA="workflow-sha",
        GITHUB_REPOSITORY="owner/repo",
        GITHUB_WORKSPACE=str(tmp_path),
        RUNNER_TEMP=str(tmp_path),
        DOCKERFILE_PATH="Dockerfile.v1",
        PLATFORMS_INPUT=override,
        RESOLVER_SOURCE=str(WORKFLOWS.parents[1] / "scripts" / "resolve_docker_platforms.py"),
        GITHUB_OUTPUT=str(output),
    )

    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    return result, output


@pytest.mark.parametrize(
    ("declaration", "override", "expected", "should_succeed"),
    [
        ("", "linux/arm64", "linux/arm64", True),
        ("# build-platforms: linux/amd64\n", " linux/arm64 ", "linux/arm64", True),
        ("# build-platforms:\n", "linux/amd64", "linux/amd64", True),
        ("", "linux/amd64,linux/arm64", "linux/amd64,linux/arm64", True),
        ("", "linux/ppc64le", "linux/ppc64le", True),
        ("", "linux amd64", "", False),
        ("", "linux/amd64,linux/amd64", "", False),
        ("", "linux/amd64,", "", False),
        ("", " ", "linux/amd64", True),
        ("# build-platforms: linux/arm64\n", " ", "linux/arm64", True),
    ],
)
def test_manual_platform_override(tmp_path, declaration, override, expected, should_succeed):
    result, output = run_platform_step(tmp_path, "manual", declaration, override)
    assert (result.returncode == 0) is should_succeed, result.stderr
    if should_succeed:
        assert output.read_text() == f"platforms={expected}\n"
    else:
        assert "::error::" in result.stderr
        assert not output.exists()


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
    assert step["with"]["platforms"] == "${{ steps.platforms.outputs.platforms }}"
    resolver = next(
        step
        for step in workflow["jobs"]["build-docker"]["steps"]
        if step.get("id") == "platforms"
    )
    assert resolver["env"]["PLATFORMS_INPUT"] == "${{ inputs.platforms }}"


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
