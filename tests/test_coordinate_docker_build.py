"""Test stable-image coordination and its workflow integration."""

import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "coordinate_docker_build.py"


def git(directory, *args):
    """Run Git in a test repository."""
    return subprocess.run(
        ["git", "-C", str(directory), *args],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def coordinate(directory, command, *args, **variables):
    """Run the coordinator and return its outputs."""
    output = directory / "output"
    if output.exists():
        output.unlink()
    env = os.environ.copy()
    env.update(GITHUB_OUTPUT=str(output), GITHUB_REPOSITORY="CCBR/Dockers2", **variables)
    result = subprocess.run(
        ["python3", str(SCRIPT), command, *args],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    outputs = (
        dict(line.split("=", 1) for line in output.read_text().splitlines())
        if output.exists()
        else {}
    )
    return result, outputs


@pytest.fixture
def repository(tmp_path):
    """Create a checkout and a remote main branch."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    git(workspace, "init", "-q", "-b", "main")
    git(workspace, "config", "user.name", "Test")
    git(workspace, "config", "user.email", "test@example.com")
    (workspace / "one" / "image").mkdir(parents=True)
    (workspace / "one" / "image" / "Dockerfile.v1").write_text("FROM scratch\n")
    (workspace / "one" / "image" / "source.txt").write_text("old\n")
    git(workspace, "add", ".")
    git(workspace, "commit", "-qm", "initial image")
    git(workspace, "remote", "add", "origin", str(remote))
    git(workspace, "push", "-u", "origin", "main")
    return workspace


def test_matrix_and_manual_use_the_same_image_key(tmp_path):
    files = [
        "one/image/Dockerfile.v1",
        "two/image/Dockerfile.v1",
        "one/image/Dockerfile.v2",
    ]
    result, output = coordinate(tmp_path, "matrix", FILES_JSON=json.dumps(files))
    assert result.returncode == 0, result.stderr
    matrix = json.loads(output["matrix"])
    assert [item["file"] for item in matrix] == files
    assert matrix[0]["key"] == matrix[1]["key"]
    assert matrix[0]["key"] != matrix[2]["key"]
    result, output = coordinate(tmp_path, "key", "./one/image/Dockerfile.v1")
    assert result.returncode == 0, result.stderr
    assert output["key"] == matrix[0]["key"]


def test_root_dockerfile_uses_repository_name_for_image_key(tmp_path):
    result, root = coordinate(tmp_path, "key", "Dockerfile.v1")
    assert result.returncode == 0, result.stderr
    result, nested = coordinate(tmp_path, "key", "other/dockers2/Dockerfile.v1")
    assert result.returncode == 0, result.stderr
    assert root["key"] == nested["key"]


@pytest.mark.parametrize("path", ["../image/Dockerfile.v1", "/image/Dockerfile.v1", "Dockerfile"])
def test_key_rejects_invalid_paths(tmp_path, path):
    result, output = coordinate(tmp_path, "key", path)
    assert result.returncode != 0
    assert "::error::" in result.stderr
    assert not output


@pytest.mark.parametrize(
    ("changed_file", "expected"),
    [
        ("one/image/Dockerfile.v1", "false"),
        ("one/image/.Dockerfile.v1.source.json", "false"),
        ("one/image/source.txt", "false"),
        ("other/notes.txt", "true"),
        ("two/image/Dockerfile.v1", "false"),
    ],
)
def test_old_checkout_is_rejected_if_matching_context_changed(repository, changed_file, expected):
    old_commit = git(repository, "rev-parse", "HEAD")
    path = repository / changed_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("changed\n")
    git(repository, "add", changed_file)
    git(repository, "commit", "-qm", "later change")
    git(repository, "push", "origin", "main")
    git(repository, "switch", "--detach", old_commit)

    result, output = coordinate(repository, "check", "one/image/Dockerfile.v1")
    assert result.returncode == 0, result.stderr
    assert output["current"] == expected


def test_new_checkout_remains_current_after_an_old_build(repository):
    (repository / "one" / "image" / "Dockerfile.v1").write_text("FROM alpine\n")
    git(repository, "commit", "-qam", "new image")
    git(repository, "push", "origin", "main")
    result, output = coordinate(repository, "check", "one/image/Dockerfile.v1")
    assert result.returncode == 0, result.stderr
    assert output["current"] == "true"


def test_deleted_dockerfile_is_not_published_by_an_old_checkout(repository):
    old_commit = git(repository, "rev-parse", "HEAD")
    (repository / "one" / "image" / "Dockerfile.v1").unlink()
    git(repository, "add", "-A")
    git(repository, "commit", "-qm", "remove image")
    git(repository, "push", "origin", "main")
    git(repository, "switch", "--detach", old_commit)
    result, output = coordinate(repository, "check", "one/image/Dockerfile.v1")
    assert result.returncode == 0, result.stderr
    assert output["current"] == "false"


def test_divergent_checkout_is_not_published(repository):
    git(repository, "switch", "-c", "divergent")
    (repository / "unrelated.txt").write_text("different branch\n")
    git(repository, "add", "unrelated.txt")
    git(repository, "commit", "-qm", "divergent commit")
    result, output = coordinate(repository, "check", "one/image/Dockerfile.v1")
    assert result.returncode == 0, result.stderr
    assert output["current"] == "false"


def test_check_fails_if_main_cannot_be_fetched(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    result, output = coordinate(tmp_path, "check", "image/Dockerfile.v1")
    assert result.returncode != 0
    assert "::error::" in result.stderr
    assert not output


def test_workflows_share_stable_lock_and_guard_publication():
    auto = yaml.safe_load((ROOT / ".github/workflows/build-docker-auto.yml").read_text())
    manual = yaml.safe_load((ROOT / ".github/workflows/build-docker-manual.yml").read_text())
    auto_job = auto["jobs"]["build-docker"]
    manual_job = manual["jobs"]["build-docker"]
    assert auto["jobs"]["get-files"]["outputs"]["matrix"] == (
        "${{ steps.image-matrix.outputs.matrix }}"
    )
    assert auto_job["strategy"]["matrix"]["image"] == (
        "${{ fromJson(needs.get-files.outputs.matrix) }}"
    )
    assert "matrix.image.key" in auto_job["concurrency"]["group"]
    assert "needs.image-key.outputs.key" in manual_job["concurrency"]["group"]
    matrix_step = next(
        step for step in auto["jobs"]["get-files"]["steps"]
        if step.get("id") == "image-matrix"
    )
    key_step = manual["jobs"]["image-key"]["steps"][0]
    assert 'python3 "$coordinator" matrix' in matrix_step["run"]
    assert 'python3 "$coordinator" key "$DOCKERFILE_PATH"' in key_step["run"]
    for job in (auto_job, manual_job):
        assert "docker-stable-{0}" in job["concurrency"]["group"]
        guard = next(step for step in job["steps"] if step.get("id") == "stable-check")
        build = next(
            step for step in job["steps"]
            if step.get("uses", "").startswith("CCBR/actions/build-docker@")
        )
        assert job["steps"].index(guard) < job["steps"].index(build)
        assert 'python3 "$coordinator" check "$DOCKERFILE_PATH"' in guard["run"]
        assert build["if"] == "steps.stable-check.outputs.current != 'false'"
    assert auto_job["concurrency"]["queue"] == (
        "${{ github.event_name == 'pull_request' && 'single' || 'max' }}"
    )
    assert manual_job["concurrency"]["queue"] == "max"
    auto_build = next(
        step for step in auto_job["steps"]
        if step.get("uses", "").startswith("CCBR/actions/build-docker@")
    )
    manual_build = next(
        step for step in manual_job["steps"]
        if step.get("uses", "").startswith("CCBR/actions/build-docker@")
    )
    assert auto_build["with"]["force_build"] == (
        "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
    )
    assert manual_build["with"]["force_build"] == (
        "${{ inputs.suffix == 'main' && inputs.push }}"
    )
