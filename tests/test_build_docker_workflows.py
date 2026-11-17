"""Check the Docker build workflows' registry and action configuration."""

from pathlib import Path
import json
import os
import re
import subprocess

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CONTEXT_ACTION = (
    WORKFLOWS.parents[1] / ".github" / "actions" / "restore-docker-context" / "action.yml"
)
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


def run_workflow_script(step, tmp_path, **variables):
    """Run a workflow's Bash step with a temporary output file."""
    output = tmp_path / "github_output"
    env = os.environ.copy()
    env.update(GITHUB_OUTPUT=str(output), **variables)
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        check=False,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        text=True,
    )
    return result, output.read_text() if output.exists() else ""


def test_build_workflows_pin_one_ccbr_actions_release():
    refs = {
        ref for name in WORKFLOW_NAMES for ref in ccbr_action_refs(load_workflow(name))
    }
    assert len(refs) == 1, f"CCBR/actions refs differ across workflows: {refs}"
    ref = refs.pop()
    assert RELEASE_TAG.fullmatch(ref)
    # Multi-registry and platform freshness checks require v0.9.1 or later.
    assert tuple(map(int, ref[1:].split("."))) >= (0, 9, 1)


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_build_workflows_fetch_dockerfile_history(name):
    steps = load_workflow(name)["jobs"]["build-docker"]["steps"]
    checkout = next(
        step
        for step in steps
        if step.get("uses", "").startswith("actions/checkout@")
        and not step.get("with", {}).get("path")
    )
    assert checkout.get("with", {}).get("fetch-depth") == 0


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
    assert workflow[True]["push"]["branches"] == ["main", "**autobuild**"]
    assert workflow[True]["pull_request"]["branches"] == ["main"]
    for event in ("push", "pull_request"):
        assert workflow[True][event]["paths"] == [
            "**/Dockerfile.*",
            "**/.Dockerfile.*.source.json",
        ]
    assert step["with"]["push"] == "${{ steps.build-policy.outputs.push }}"
    assert step["with"]["suffix"] == "${{ steps.build-policy.outputs.suffix }}"
    assert step["with"]["registries"] == "dockerhub,ghcr"
    assert any(
        step.get("uses", "").startswith("CCBR/actions/changed-files@")
        for step in workflow["jobs"]["get-files"]["steps"]
    )
    assert step["with"]["platforms"] == "${{ steps.platforms.outputs.platforms }}"
    assert not workflow["jobs"]["build-docker"].get("continue-on-error", False)
    checkout = next(
        step
        for step in workflow["jobs"]["build-docker"]["steps"]
        if step.get("name") == "Checkout repository"
    )
    assert checkout["with"]["ref"] == (
        "${{ github.event.pull_request.head.sha || github.sha }}"
    )
    branch = next(
        step
        for step in workflow["jobs"]["build-docker"]["steps"]
        if step.get("name") == "Prepare checked-out branch"
    )
    assert branch["env"]["BRANCH_NAME"] == "${{ github.head_ref || github.ref_name }}"


def test_automatic_workflow_keeps_the_event_commit(tmp_path):
    git_command(tmp_path, "init", "-q", "-b", "main")
    git_command(tmp_path, "config", "--local", "user.name", "Test")
    git_command(tmp_path, "config", "--local", "user.email", "test@example.com")
    (tmp_path / "Dockerfile.v2").write_text("FROM ubuntu:24.04\n")
    git_command(tmp_path, "add", ".")
    git_command(tmp_path, "commit", "-qm", "test: event")
    event_commit = git_command(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "Dockerfile.v2").write_text("FROM ubuntu:26.04\n")
    git_command(tmp_path, "commit", "-qam", "test: later")
    git_command(tmp_path, "switch", "--detach", event_commit)
    branch = next(
        step
        for step in load_workflow("auto")["jobs"]["build-docker"]["steps"]
        if step.get("name") == "Prepare checked-out branch"
    )

    result, _ = run_workflow_script(
        branch, tmp_path, BRANCH_NAME="feature/autobuild"
    )

    assert result.returncode == 0, result.stderr
    assert git_command(tmp_path, "rev-parse", "HEAD") == event_commit
    assert git_command(tmp_path, "branch", "--show-current") == "feature/autobuild"
    assert (tmp_path / "Dockerfile.v2").read_text() == "FROM ubuntu:24.04\n"


def test_automatic_workflow_restores_context_from_workflow_revision():
    job = load_workflow("auto")["jobs"]["build-docker"]
    checkout = next(
        step for step in job["steps"] if step.get("name") == "Checkout workflow action"
    )
    assert checkout["if"] == "github.event_name == 'pull_request'"
    assert checkout["with"]["repository"] == "${{ github.repository }}"
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["path"] == ".ccbr-workflow-source"
    for event in ("pull requests", "pushes"):
        step = next(
            step
            for step in job["steps"]
            if step.get("name") == f"Restore source context for {event}"
        )
        assert step["with"]["dockerfile"] == "${{ matrix.file }}"
        assert step["uses"].endswith("/.github/actions/restore-docker-context")


@pytest.mark.parametrize(
    ("event", "ref", "head_repository", "suffix", "push"),
    [
        ("push", "refs/heads/main", "", "main", "true"),
        ("push", "refs/heads/feature-autobuild", "", "dev", "true"),
        ("pull_request", "refs/pull/1/merge", "CCBR/Dockers2", "dev", "true"),
        ("pull_request", "refs/pull/2/merge", "someone/Dockers2", "dev", "false"),
    ],
)
def test_automatic_image_publication_policy(
    tmp_path, event, ref, head_repository, suffix, push
):
    step = next(
        step
        for step in load_workflow("auto")["jobs"]["build-docker"]["steps"]
        if step.get("id") == "build-policy"
    )
    result, output = run_workflow_script(
        step,
        tmp_path,
        EVENT_NAME=event,
        EVENT_REF=ref,
        PR_HEAD_REPOSITORY=head_repository,
        GITHUB_REPOSITORY="CCBR/Dockers2",
    )

    assert result.returncode == 0, result.stderr
    assert output == f"suffix={suffix}\npush={push}\n"


@pytest.mark.parametrize(
    ("event", "head_repository"),
    [("pull_request", ""), ("workflow_dispatch", "")],
)
def test_automatic_image_publication_rejects_invalid_events(
    tmp_path, event, head_repository
):
    step = next(
        step
        for step in load_workflow("auto")["jobs"]["build-docker"]["steps"]
        if step.get("id") == "build-policy"
    )
    result, output = run_workflow_script(
        step,
        tmp_path,
        EVENT_NAME=event,
        EVENT_REF="refs/heads/main",
        PR_HEAD_REPOSITORY=head_repository,
        GITHUB_REPOSITORY="CCBR/Dockers2",
    )

    assert result.returncode != 0
    assert "::error::" in result.stdout
    assert not output


@pytest.mark.parametrize("include_existing", [True, False])
def test_automatic_workflow_excludes_deleted_dockerfiles(tmp_path, include_existing):
    workflow = load_workflow("auto")
    job = workflow["jobs"]["get-files"]
    checkout = next(
        step for step in job["steps"] if step["name"] == "Checkout event source"
    )
    assert checkout["with"]["repository"] == (
        "${{ github.event.pull_request.head.repo.full_name || github.repository }}"
    )
    assert checkout["with"]["ref"] == (
        "${{ github.event.pull_request.head.sha || github.sha }}"
    )
    assert job["outputs"]["json"] == (
        "${{ steps.existing-files.outputs.matched_files_json }}"
    )
    step = next(step for step in job["steps"] if step.get("id") == "existing-files")
    files = ["removed/Dockerfile.v1"]
    expected = []
    if include_existing:
        dockerfile = tmp_path / "image" / "Dockerfile.v2"
        dockerfile.parent.mkdir()
        dockerfile.write_text("FROM ubuntu:26.04\n")
        files.append("image/Dockerfile.v2")
        expected.append("image/Dockerfile.v2")

    result, output = run_workflow_script(
        step, tmp_path, MATCHED_FILES_JSON=json.dumps(files)
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.removeprefix("matched_files_json=")) == expected
    assert "Skipping deleted Dockerfile: removed/Dockerfile.v1" in result.stdout


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
        (
            "pull_request",
            "synchronize",
            "",
            "image/.Dockerfile.v2.source.json",
            '["image/.Dockerfile.v2.source.json"]',
            '["image/.Dockerfile.v2.source.json"]',
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
    steps = job["steps"]
    existing_files = next(step for step in steps if step.get("id") == "existing-files")
    assert existing_files["env"]["MATCHED_FILES_JSON"] == (
        "${{ steps.select-files.outputs.json }}"
    )
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


@pytest.mark.parametrize(
    ("files", "metadata_exists", "warning"),
    [
        (["image/.Dockerfile.v2.source.json"], True, False),
        (["image/Dockerfile.v2", "image/.Dockerfile.v2.source.json"], True, False),
        (["image/.Dockerfile.v2.source.json"], False, True),
    ],
)
def test_automatic_workflow_maps_metadata_to_dockerfiles(
    tmp_path, files, metadata_exists, warning
):
    directory = tmp_path / "image"
    directory.mkdir()
    (directory / "Dockerfile.v2").write_text("FROM ubuntu:26.04\n")
    if metadata_exists:
        (directory / ".Dockerfile.v2.source.json").write_text("{}")
    step = next(
        step
        for step in load_workflow("auto")["jobs"]["get-files"]["steps"]
        if step.get("id") == "existing-files"
    )
    result, output = run_workflow_script(
        step, tmp_path, MATCHED_FILES_JSON=json.dumps(files)
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.removeprefix("matched_files_json=")) == [
        "image/Dockerfile.v2"
    ]
    assert ("::warning::" in result.stdout) is warning


def test_initial_push_includes_metadata_changes_and_deleted_dockerfiles(tmp_path):
    git_command(tmp_path, "init", "-q", "-b", "main")
    git_command(tmp_path, "config", "--local", "user.name", "Test")
    git_command(tmp_path, "config", "--local", "user.email", "test@example.com")
    image = tmp_path / "image"
    image.mkdir()
    (image / "Dockerfile.v2").write_text("FROM ubuntu:26.04\n")
    (image / "Dockerfile.v1").write_text("FROM ubuntu:24.04\n")
    metadata = image / ".Dockerfile.v2.source.json"
    metadata.write_text('{"commit":"old"}\n')
    git_command(tmp_path, "add", ".")
    git_command(tmp_path, "commit", "-qm", "test: seed")
    metadata.write_text('{"commit":"new"}\n')
    (image / "Dockerfile.v1").unlink()
    git_command(tmp_path, "add", "-A")
    git_command(tmp_path, "commit", "-qm", "test: update")
    commit = git_command(tmp_path, "rev-parse", "HEAD")
    step = next(
        step
        for step in load_workflow("auto")["jobs"]["get-files"]["steps"]
        if step.get("id") == "initial-push"
    )

    result, output = run_workflow_script(
        step, tmp_path, FIRST_PUSH_COMMIT=commit, GITHUB_SHA=commit
    )

    assert result.returncode == 0, result.stderr
    assert set(json.loads(output_values(output)["matched_files_json"])) == {
        "image/.Dockerfile.v2.source.json",
        "image/Dockerfile.v1",
    }


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
    restore = next(
        step
        for step in load_workflow("manual")["jobs"]["build-docker"]["steps"]
        if step.get("name") == "Restore source context"
    )
    assert restore["uses"] == "./.github/actions/restore-docker-context"
    assert restore["with"]["dockerfile"] == "${{ inputs.dockerfile }}"


@pytest.mark.parametrize(
    ("suffix", "push", "ref", "should_succeed"),
    [
        ("main", "true", "refs/heads/main", True),
        ("main", "true", "refs/heads/feature", False),
        ("main", "false", "refs/heads/feature", True),
        ("dev", "true", "refs/heads/feature", True),
        ("feat", "false", "refs/heads/main", False),
    ],
)
def test_manual_workflow_validates_image_tags(
    tmp_path, suffix, push, ref, should_succeed
):
    workflow = load_workflow("manual")
    suffix_input = workflow[True]["workflow_dispatch"]["inputs"]["suffix"]
    assert suffix_input["default"] == "dev"
    assert suffix_input["options"] == ["dev", "main"]
    step = next(
        step
        for step in workflow["jobs"]["build-docker"]["steps"]
        if step.get("name") == "Validate tag selection"
    )
    result, _ = run_workflow_script(
        step, tmp_path, SUFFIX=suffix, PUSH=push, GITHUB_REF=ref
    )

    assert (result.returncode == 0) is should_succeed
    if not should_succeed:
        assert "::error::" in result.stdout


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


@pytest.mark.parametrize(
    ("existing_pr", "fail_review"),
    [("", False), ("42", False), ("42", True)],
)
def test_dispatch_workflow_builds_preview_and_targets_main(
    tmp_path, existing_pr, fail_review
):
    workflow = load_workflow("dispatch")
    job = workflow["jobs"]["build-docker"]
    checkout = next(
        step for step in job["steps"] if step.get("name") == "Checkout Dockers2"
    )
    assert checkout["with"]["ref"] == "main"
    assert build_step(workflow)["with"]["suffix"] == "dev"
    step = next(
        step for step in job["steps"] if step.get("name") == "Open or update PR to main"
    )
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/bash\n"
        'echo "$*" >> "$GH_CALLS"\n'
        'if [[ "$1" == "pr" && "$2" == "list" ]]; then echo "$EXISTING_PR"; fi\n'
        'if [[ "$2" == "edit" && "$FAIL_REVIEW" == "true" ]]; then exit 1; fi\n'
    )
    gh.chmod(0o755)
    calls = tmp_path / "calls"

    result, _ = run_workflow_script(
        step,
        tmp_path,
        PATH=f"{tmp_path}:{os.environ['PATH']}",
        GH_CALLS=str(calls),
        EXISTING_PR=existing_pr,
        FAIL_REVIEW=str(fail_review).lower(),
        BRANCH_NAME="update-test-v2",
        DOCKER_IMAGE_NAME="test",
        DOCKER_IMAGE_TAG="v2",
    )

    assert result.returncode == 0, result.stderr
    lines = calls.read_text().splitlines()
    assert "--base main" in lines[0]
    if existing_pr:
        assert lines[1].startswith(f"pr edit {existing_pr} ")
        assert ("::warning::" in result.stdout) is fail_review
    else:
        assert lines[1].startswith("pr create ")
        assert "--base main" in lines[1]


@pytest.mark.parametrize("path", ["combine_prs.sh", "scripts/combine_prs.sh"])
def test_combine_pr_scripts_target_main(path):
    script = (WORKFLOWS.parents[1] / path).read_text()
    assert "--base main" in script
    assert "--base dev" not in script


def context_action_step(name):
    """Find a step in the local source-context action."""
    action = yaml.safe_load(CONTEXT_ACTION.read_text())
    return next(step for step in action["runs"]["steps"] if step.get("name") == name)


def output_values(output):
    """Parse the single-line outputs emitted by the workflow steps."""
    return dict(line.split("=", 1) for line in output.splitlines())


@pytest.mark.parametrize("with_metadata", [False, True])
def test_context_action_reads_optional_source_metadata(tmp_path, with_metadata):
    workspace = tmp_path / "workspace"
    context = workspace / "image"
    context.mkdir(parents=True)
    (context / "Dockerfile.v2").write_text("FROM ubuntu:26.04\n")
    if with_metadata:
        (context / ".Dockerfile.v2.source.json").write_text(
            json.dumps({"repository": "CCBR/example", "commit": "a" * 40})
        )

    result, output = run_workflow_script(
        context_action_step("Read source metadata"),
        tmp_path,
        GITHUB_WORKSPACE=str(workspace),
        DOCKERFILE_INPUT="image/Dockerfile.v2",
    )

    assert result.returncode == 0, result.stderr
    values = output_values(output)
    assert values["repository"] == ("CCBR/example" if with_metadata else "")
    if with_metadata:
        assert values["commit"] == "a" * 40
        assert values["context"] == "image"
        assert values["dockerfile"] == "Dockerfile.v2"
        assert values["metadata"] == ".Dockerfile.v2.source.json"

    checkout = context_action_step("Checkout source repository")
    assert checkout["with"]["repository"] == "${{ steps.source.outputs.repository }}"
    assert checkout["with"]["ref"] == "${{ steps.source.outputs.commit }}"
    assert checkout["with"]["persist-credentials"] is False


@pytest.mark.parametrize(
    "metadata",
    [
        "{",
        "[]",
        json.dumps({"repository": "../example", "commit": "a" * 40}),
        json.dumps({"repository": "CCBR/example", "commit": "abc123"}),
        json.dumps({"repository": "CCBR/example\ninjected=value", "commit": "a" * 40}),
    ],
)
def test_context_action_rejects_invalid_source_metadata(tmp_path, metadata):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "Dockerfile.v2").write_text("FROM ubuntu:26.04\n")
    (workspace / ".Dockerfile.v2.source.json").write_text(metadata)
    result, output = run_workflow_script(
        context_action_step("Read source metadata"),
        tmp_path,
        GITHUB_WORKSPACE=str(workspace),
        DOCKERFILE_INPUT="Dockerfile.v2",
    )

    assert result.returncode != 0
    assert "::error::" in result.stderr
    assert not output


def test_context_action_rejects_dockerfile_outside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("FROM ubuntu:26.04\n")
    (workspace / "Dockerfile.v2").symlink_to(outside)
    result, _ = run_workflow_script(
        context_action_step("Read source metadata"),
        tmp_path,
        GITHUB_WORKSPACE=str(workspace),
        DOCKERFILE_INPUT="Dockerfile.v2",
    )

    assert result.returncode != 0
    assert "::error::" in result.stderr


@pytest.mark.parametrize("context_dir", [".", "image"])
def test_context_action_restores_source_without_overwriting_recipe(
    tmp_path, context_dir
):
    workspace = tmp_path / "workspace"
    context = workspace / context_dir
    context.mkdir(parents=True)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    dockerfile = context / "Dockerfile.v2"
    metadata = context / ".Dockerfile.v2.source.json"
    dockerfile.write_text("FROM ubuntu:26.04\n")
    metadata.write_text('{"repository":"CCBR/example","commit":"' + "a" * 40 + '"}')
    source = workspace / ".ccbr-build-source"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "config").write_text("not part of the build context")
    (source / ".github").mkdir()
    (source / ".github" / ".Rprofile").write_text("source profile")
    (source / ".dockerignore").write_text("ignored-file\n")
    (source / "Dockerfile.v2").write_text("wrong dockerfile")
    (source / metadata.name).write_text("wrong metadata")

    result, _ = run_workflow_script(
        context_action_step("Restore source context"),
        tmp_path,
        GITHUB_WORKSPACE=str(workspace),
        RUNNER_TEMP=str(runner_temp),
        CONTEXT_DIR=context_dir,
        DOCKERFILE_NAME=dockerfile.name,
        METADATA_NAME=metadata.name,
    )

    assert result.returncode == 0, result.stderr
    assert dockerfile.read_text() == "FROM ubuntu:26.04\n"
    assert json.loads(metadata.read_text())["commit"] == "a" * 40
    assert (context / ".github" / ".Rprofile").read_text() == "source profile"
    assert (context / ".dockerignore").read_text() == "ignored-file\n"
    assert not (context / ".git").exists()
    assert not source.exists()
    assert list(runner_temp.glob("ccbr-build-source.*/checkout/.git/config"))


def test_context_action_does_not_replace_existing_checkout_path(tmp_path):
    workspace = tmp_path / "workspace"
    reserved = workspace / ".ccbr-build-source"
    reserved.mkdir(parents=True)
    marker = reserved / "keep"
    marker.write_text("keep")
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    result, _ = run_workflow_script(
        context_action_step("Check source checkout location"),
        tmp_path,
        GITHUB_WORKSPACE=str(workspace),
        RUNNER_TEMP=str(runner_temp),
    )

    assert result.returncode != 0
    assert "::error::" in result.stdout
    assert marker.read_text() == "keep"


@pytest.mark.parametrize("event", ["repository_dispatch", "workflow_dispatch"])
def test_dispatch_payload_selects_and_validates_source(event, tmp_path):
    step = next(
        step
        for step in load_workflow("dispatch")["jobs"]["build-docker"]["steps"]
        if step.get("id") == "process-payload"
    )
    variables = {
        f"{prefix}_{name}": ""
        for prefix in ("PAYLOAD", "INPUT")
        for name in ("OWNER_REPO", "REF", "DOCKERFILE_PATH", "IMAGE_NAME", "IMAGE_TAG")
    }
    prefix = "PAYLOAD" if event == "repository_dispatch" else "INPUT"
    variables.update(
        {
            f"{prefix}_OWNER_REPO": "CCBR/MOSuite",
            f"{prefix}_REF": "main",
            f"{prefix}_DOCKERFILE_PATH": "Dockerfile",
            f"{prefix}_IMAGE_NAME": "mosuite",
            f"{prefix}_IMAGE_TAG": "v0.3.0.9002",
        }
    )
    result, output = run_workflow_script(step, tmp_path, EVENT_NAME=event, **variables)

    assert result.returncode == 0, result.stderr
    values = output_values(output)
    assert values["owner_repo"] == "CCBR/MOSuite"
    assert values["new_dockerfile_path"] == "MOSuite/mosuite/Dockerfile.v0.3.0.9002"
    assert values["new_branch"] == "update-mosuite-v0.3.0.9002"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("OWNER_REPO", "../other"),
        ("REF", "main\ninjected=true"),
        ("DOCKERFILE_PATH", "../outside"),
        ("IMAGE_NAME", "image;command"),
        ("IMAGE_TAG", "v2\ninjected=true"),
    ],
)
def test_dispatch_payload_rejects_invalid_values(tmp_path, field, value):
    step = next(
        step
        for step in load_workflow("dispatch")["jobs"]["build-docker"]["steps"]
        if step.get("id") == "process-payload"
    )
    variables = {
        f"{prefix}_{name}": ""
        for prefix in ("PAYLOAD", "INPUT")
        for name in ("OWNER_REPO", "REF", "DOCKERFILE_PATH", "IMAGE_NAME", "IMAGE_TAG")
    }
    variables.update(
        PAYLOAD_OWNER_REPO="CCBR/example",
        PAYLOAD_REF="main",
        PAYLOAD_DOCKERFILE_PATH="Dockerfile",
        PAYLOAD_IMAGE_NAME="example",
        PAYLOAD_IMAGE_TAG="v2",
    )
    variables[f"PAYLOAD_{field}"] = value
    result, output = run_workflow_script(
        step, tmp_path, EVENT_NAME="repository_dispatch", **variables
    )

    assert result.returncode != 0
    assert "::error::" in result.stdout
    assert not output


def git_command(directory, *arguments):
    """Run Git in a temporary test repository."""
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_dispatch_records_source_commit_without_committing_source_files(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    git_command(workspace, "init", "-q", "-b", "main")
    git_command(workspace, "config", "--local", "user.name", "Test")
    git_command(workspace, "config", "--local", "user.email", "test@example.com")
    (workspace / "seed").write_text("seed")
    git_command(workspace, "add", "seed")
    git_command(workspace, "commit", "-qm", "test: seed")
    git_command(workspace, "remote", "add", "origin", str(origin))
    git_command(workspace, "push", "-u", "origin", "main")

    source = workspace / ".ccbr-dispatch-source"
    source.mkdir()
    git_command(source, "init", "-q", "-b", "main")
    git_command(source, "config", "--local", "user.name", "Test")
    git_command(source, "config", "--local", "user.email", "test@example.com")
    (source / "Dockerfile").write_text("FROM ubuntu:26.04\nCOPY .github/.Rprofile /opt/\n")
    (source / ".github").mkdir()
    (source / ".github" / ".Rprofile").write_text("source profile")
    git_command(source, "add", ".")
    git_command(source, "commit", "-qm", "test: source")
    source_commit = git_command(source, "rev-parse", "HEAD")

    steps = load_workflow("dispatch")["jobs"]["build-docker"]["steps"]
    prepare = next(
        step
        for step in steps
        if step.get("name") == "Prepare update branch and Dockerfile"
    )
    record = next(step for step in steps if step.get("id") == "source-context")
    commit = next(step for step in steps if step.get("name") == "Commit new Dockerfile")
    dockerfile = "example/image/Dockerfile.v2"
    branch = "update-image-v2"
    result, _ = run_workflow_script(
        prepare,
        workspace,
        BRANCH_NAME=branch,
        CONTEXT_DIR="example/image",
        NEW_DOCKERFILE_PATH=dockerfile,
        SRC_DOCKERFILE_PATH="Dockerfile",
    )
    assert result.returncode == 0, result.stderr
    result, output = run_workflow_script(
        record,
        workspace,
        SOURCE_REPOSITORY="CCBR/example",
        NEW_DOCKERFILE_PATH=dockerfile,
    )
    assert result.returncode == 0, result.stderr
    metadata = output_values(output)["metadata"]
    assert json.loads((workspace / metadata).read_text()) == {
        "repository": "CCBR/example",
        "commit": source_commit,
    }
    result, _ = run_workflow_script(
        commit,
        workspace,
        BRANCH_NAME=branch,
        DOCKER_IMAGE_NAME="image",
        DOCKER_IMAGE_TAG="v2",
        NEW_DOCKERFILE_PATH=dockerfile,
        SOURCE_METADATA_PATH=metadata,
    )

    assert result.returncode == 0, result.stderr
    tracked = git_command(
        workspace, "ls-tree", "-r", "--name-only", "HEAD"
    ).splitlines()
    assert dockerfile in tracked
    assert metadata in tracked
    assert "example/image/.github/.Rprofile" not in tracked
    assert (workspace / "example/image/.github/.Rprofile").is_file()
    assert git_command(workspace, "rev-parse", "HEAD") == git_command(
        workspace, "rev-parse", f"origin/{branch}"
    )

    (source / ".github" / ".Rprofile").write_text("updated profile")
    git_command(source, "add", ".github/.Rprofile")
    git_command(source, "commit", "-qm", "test: update source")
    updated_commit = git_command(source, "rev-parse", "HEAD")
    git_command(workspace, "switch", "main")
    result, _ = run_workflow_script(
        prepare,
        workspace,
        BRANCH_NAME=branch,
        CONTEXT_DIR="example/image",
        NEW_DOCKERFILE_PATH=dockerfile,
        SRC_DOCKERFILE_PATH="Dockerfile",
    )
    assert result.returncode == 0, result.stderr
    result, _ = run_workflow_script(
        record,
        workspace,
        SOURCE_REPOSITORY="CCBR/example",
        NEW_DOCKERFILE_PATH=dockerfile,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((workspace / metadata).read_text())["commit"] == updated_commit
    assert git_command(workspace, "diff", "--name-only").splitlines() == [metadata]
