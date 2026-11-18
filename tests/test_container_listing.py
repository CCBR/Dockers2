"""Test the Dockerfile-derived Quarto container catalog."""

import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_container_listing as catalog


PUBLISHED = {
    "Docker Hub": {"linux/amd64", "linux/arm64"},
    "GHCR": {"linux/amd64", "linux/arm64"},
}


def published(image, tag):
    return PUBLISHED


def write_file(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("FROM scratch\n", encoding="utf-8")
    return path


def test_dockerfile_discovery_includes_only_existing_versioned_files(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    tracked = write_file(tmp_path, "one/ccbr_tool/Dockerfile.v1.2.3")
    deleted = write_file(tmp_path, "one/ccbr_tool/Dockerfile.v0")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(tracked), str(deleted)], check=True)
    deleted.unlink()
    write_file(tmp_path, "Dockerfile.v9")
    write_file(tmp_path, "two/new-image/Dockerfile.v2")
    write_file(tmp_path, "ignored/image/Dockerfile.v3")
    write_file(tmp_path, "two/new-image/Dockerfile")
    write_file(tmp_path, "two/new-image/failing.Dockerfile.v4")
    write_file(tmp_path, "two/new-image/.Dockerfile.v5.source.json")

    assert catalog.dockerfiles(tmp_path) == [
        PurePosixPath("Dockerfile.v9"),
        PurePosixPath("one/ccbr_tool/Dockerfile.v1.2.3"),
        PurePosixPath("two/new-image/Dockerfile.v2"),
    ]


def test_item_contains_matching_tags_readme_and_source(tmp_path):
    readme = write_file(tmp_path, "spac/spac-gpu/v1.0.1.README.md")
    item = catalog.listing_item(
        PurePosixPath("spac/spac-gpu/Dockerfile.v1.0.1"), tmp_path, PUBLISHED
    )

    assert item["title"] == "spac-gpu"
    assert item["tag"] == "v1.0.1"
    assert "[![Docker Hub: v1.0.1]" in item["registries"]
    assert "v1.0.1-2496ED.svg?logo=docker&logoColor=white" in item["registries"]
    assert "hub.docker.com/r/nciccbr/spac-gpu/tags?name=v1.0.1" in item["registries"]
    assert "[![GHCR: v1.0.1]" in item["registries"]
    assert "v1.0.1-24292f.svg?logo=github&logoColor=white" in item["registries"]
    assert (
        "github.com/orgs/CCBR/packages/container/package/spac-gpu?tag=v1.0.1"
        in item["registries"]
    )
    assert item["source"] == (
        "[Dockerfile.v1.0.1](https://github.com/CCBR/Dockers2/blob/main/"
        "spac/spac-gpu/Dockerfile.v1.0.1)"
    )
    assert item["readme"] == (
        "https://github.com/CCBR/Dockers2/blob/main/"
        "spac/spac-gpu/v1.0.1.README.md"
    )
    assert item["platforms"] == "`linux/amd64`, `linux/arm64`"
    readme.unlink()
    assert "readme" not in catalog.listing_item(
        PurePosixPath("spac/spac-gpu/Dockerfile.v1.0.1"), tmp_path, PUBLISHED
    )


def test_root_dockerfile_and_badge_escaping(tmp_path):
    item = catalog.listing_item(PurePosixPath("Dockerfile.v1-beta_2"), tmp_path, PUBLISHED)

    assert item["title"] == "dockers2"
    assert item["tag"] == "v1-beta_2"
    assert "v1--beta__2" in item["registries"]
    assert "name=v1-beta_2" in item["registries"]
    assert "tag=v1-beta_2" in item["registries"]


def test_source_url_escapes_parent_directories(tmp_path):
    item = catalog.listing_item(
        PurePosixPath("a directory/tool/Dockerfile.v1"), tmp_path, PUBLISHED
    )
    assert "/a%20directory/tool/Dockerfile.v1" in item["source"]


@pytest.mark.parametrize(
    "path",
    ["tool/Dockerfile.", "tool/Dockerfile.v1+invalid", "Invalid/Dockerfile.v1"],
)
def test_invalid_image_names_or_tags_fail(path, tmp_path):
    with pytest.raises(ValueError):
        catalog.listing_item(PurePosixPath(path), tmp_path, PUBLISHED)


@pytest.mark.parametrize(
    "tags,expected",
    [
        (["v9", "v11", "v10"], "v11"),
        (["v1.9", "v1.10", "v1.2"], "v1.10"),
        (["v0.9.3", "v1", "v2"], "v2"),
        (["v1.0.0-rc.2", "v1", "v1.0.0-rc.10"], "v1"),
        (["v1", "v1.0.1"], "v1.0.1"),
    ],
)
def test_latest_tag_uses_numeric_version_order(tags, expected):
    assert max(tags, key=catalog.version_key) == expected


def test_missing_registry_and_platform_differences(tmp_path):
    path = PurePosixPath("image/Dockerfile.v1")
    item = catalog.listing_item(
        path, tmp_path, {"Docker Hub": {"linux/amd64"}, "GHCR": None}
    )
    assert "Docker Hub:" in item["registries"] and "GHCR:" not in item["registries"]
    assert item["platforms"] == "`linux/amd64`"
    item = catalog.listing_item(
        path, tmp_path, {"Docker Hub": None, "GHCR": {"linux/arm/v7"}}
    )
    assert "Docker Hub:" not in item["registries"] and "GHCR:" in item["registries"]
    assert item["platforms"] == "`linux/arm/v7`"
    item = catalog.listing_item(
        path, tmp_path, {"Docker Hub": {"linux/amd64"}, "GHCR": {"linux/arm64"}}
    )
    assert item["platforms"] == "Docker Hub: `linux/amd64`<br>GHCR: `linux/arm64`"
    item = catalog.listing_item(path, tmp_path, {"Docker Hub": None, "GHCR": None})
    assert item["registries"] == ""
    assert item["platforms"] == "Not published"


def test_generator_writes_sorted_metadata(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write_file(tmp_path, "z/image-b/Dockerfile.v2")
    write_file(tmp_path, "z/image-b/Dockerfile.v1")
    write_file(tmp_path, "a/image-a/Dockerfile.v1")
    output = tmp_path / "containers.yml"

    catalog.generate_listing(tmp_path, output, lookup=published)

    items = json.loads(output.read_text(encoding="utf-8"))
    assert [(item["title"], item["tag"]) for item in items] == [
        ("image-a", "v1"),
        ("image-b", "v2"),
    ]


def test_unpublished_release_falls_back_to_latest_pushed_tag(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write_file(tmp_path, "chip/ccbr_chip/Dockerfile.v1")
    write_file(tmp_path, "chip/ccbr_chip/v1-dev.README.md")
    write_file(tmp_path, "done/ccbr_done/Dockerfile.v2")
    write_file(tmp_path, "none/ccbr_none/Dockerfile.v1")
    output = tmp_path / "containers.yml"
    pushed = {"ccbr_chip": "v1-dev", "ccbr_done": "v2-dev", "ccbr_none": None}
    looked_up = []

    def lookup(image, tag):
        looked_up.append((image, tag))
        if (image, tag) in {("ccbr_chip", "v1-dev"), ("ccbr_done", "v2")}:
            return {"Docker Hub": {"linux/amd64"}, "GHCR": None}
        return {"Docker Hub": None, "GHCR": None}

    catalog.generate_listing(tmp_path, output, lookup=lookup, latest_pushed=pushed.get)

    items = {item["title"]: item for item in json.loads(output.read_text())}
    assert items["ccbr_chip"]["tag"] == "v1-dev"
    assert "[![Docker Hub: v1-dev]" in items["ccbr_chip"]["registries"]
    assert "tags?name=v1-dev" in items["ccbr_chip"]["registries"]
    assert items["ccbr_chip"]["readme"].endswith("chip/ccbr_chip/v1-dev.README.md")
    assert items["ccbr_chip"]["source"].endswith("chip/ccbr_chip/Dockerfile.v1)")
    assert items["ccbr_done"]["tag"] == "v2"
    assert ("ccbr_done", "v2-dev") not in looked_up
    assert items["ccbr_none"]["tag"] == "v1"
    assert items["ccbr_none"]["platforms"] == "Not published"


def test_dockerhub_latest_tag_requests_newest_tag(monkeypatch):
    def get(url):
        assert "/repositories/tool/tags?" in url
        assert "ordering=last_updated" in url and "page_size=1" in url
        return {"results": [{"name": "v1-dev"}]}

    monkeypatch.setattr(catalog, "read_json", get)
    assert catalog.dockerhub_latest_tag("tool") == "v1-dev"
    monkeypatch.setattr(catalog, "read_json", lambda url: {"results": []})
    assert catalog.dockerhub_latest_tag("tool") is None
    monkeypatch.setattr(
        catalog, "read_json", lambda url: (_ for _ in ()).throw(http_error(url, 404))
    )
    assert catalog.dockerhub_latest_tag("tool") is None


def http_error(url, code, payload=None):
    return HTTPError(
        url, code, "Registry error", {}, io.BytesIO(json.dumps(payload or {}).encode())
    )


def test_dockerhub_reports_real_platforms_and_filters_attestations(monkeypatch):
    def get(url):
        assert url.endswith("/repositories/tool/tags/v1")
        return {
            "images": [
                {"os": "linux", "architecture": "amd64"},
                {"os": "linux", "architecture": "arm", "variant": "v7"},
                {"os": "unknown", "architecture": "unknown"},
            ]
        }

    monkeypatch.setattr(catalog, "read_json", get)
    assert catalog.dockerhub_platforms("tool", "v1") == {"linux/amd64", "linux/arm/v7"}


@pytest.mark.parametrize("code", [404, 429, 500])
def test_dockerhub_only_treats_not_found_as_unavailable(monkeypatch, code):
    def get(url):
        raise http_error(url, code)

    monkeypatch.setattr(catalog, "read_json", get)
    if code == 404:
        assert catalog.dockerhub_platforms("tool", "v1") is None
    else:
        with pytest.raises(HTTPError):
            catalog.dockerhub_platforms("tool", "v1")


def test_ghcr_manifest_index_platforms(monkeypatch):
    def get(url, headers=None):
        if "/token?" in url:
            return {"token": "public-pull-token"}
        assert headers["Authorization"] == "Bearer public-pull-token"
        assert url.endswith("/manifests/v1")
        return {
            "manifests": [
                {"platform": {"os": "linux", "architecture": "amd64"}},
                {"platform": {"os": "linux", "architecture": "arm64", "variant": "v8"}},
                {"platform": {"os": "unknown", "architecture": "unknown"}},
                {"annotations": {"vnd.docker.reference.type": "attestation-manifest"}},
            ]
        }

    monkeypatch.setattr(catalog, "read_json", get)
    assert catalog.ghcr_platforms("tool", "v1") == {"linux/amd64", "linux/arm64/v8"}


def test_ghcr_single_manifest_uses_image_config(monkeypatch):
    def get(url, headers=None):
        if "/token?" in url:
            return {"token": "public-pull-token"}
        if "/manifests/" in url:
            return {"config": {"digest": "sha256:example"}}
        assert url.endswith("/blobs/sha256:example")
        return {"os": "linux", "architecture": "amd64"}

    monkeypatch.setattr(catalog, "read_json", get)
    assert catalog.ghcr_platforms("tool", "v1") == {"linux/amd64"}


def test_ghcr_missing_or_private_package_has_no_badge(monkeypatch, capsys):
    def get(url, headers=None):
        raise http_error(url, 403, {"errors": [{"code": "DENIED"}]})

    monkeypatch.setattr(catalog, "read_json", get)
    assert catalog.ghcr_platforms("tool", "v1") is None
    assert "not public" in capsys.readouterr().err


@pytest.mark.parametrize("code", [404, 429, 500])
def test_ghcr_only_treats_missing_tag_as_unavailable(monkeypatch, code):
    def get(url, headers=None):
        if "/token?" in url:
            return {"token": "public-pull-token"}
        raise http_error(url, code)

    monkeypatch.setattr(catalog, "read_json", get)
    if code == 404:
        assert catalog.ghcr_platforms("tool", "v1") is None
    else:
        with pytest.raises(HTTPError):
            catalog.ghcr_platforms("tool", "v1")


def test_registry_connection_failure_is_not_hidden(monkeypatch):
    def get(url, headers=None):
        raise URLError("Connection failed")

    monkeypatch.setattr(catalog, "read_json", get)
    with pytest.raises(URLError):
        catalog.registry_platforms("tool", "v1")


@pytest.mark.parametrize(
    "destination",
    ["https://storage.example/blob", "http://ghcr.io/blob"],
)
def test_blob_redirect_does_not_forward_registry_token(destination):
    request = Request("https://ghcr.io/blob", headers={"Authorization": "Bearer example"})
    redirected = catalog.RegistryRedirectHandler().redirect_request(
        request, None, 307, "Redirect", {}, destination
    )
    assert not redirected.has_header("Authorization")


def test_docs_workflow_rebuilds_after_listing_inputs_change():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docs-quarto.yml").read_text())
    paths = workflow[True]["push"]["paths"]

    assert "docs/**" in paths
    assert "**/Dockerfile.*" in paths
    assert "scripts/generate_container_listing.py" in paths
    assert "scripts/coordinate_docker_build.py" in paths
    trigger = workflow[True]["workflow_run"]
    assert trigger["workflows"] == [
        "build-docker-auto",
        "build-docker-manual",
        "build-docker-dispatch",
    ]
    assert trigger["branches"] == ["main"]
    assert trigger["types"] == ["completed"]
    assert "github.event.workflow_run.conclusion == 'success'" in (
        workflow["jobs"]["build-deploy"]["if"]
    )


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
def test_quarto_renders_the_catalog_table(tmp_path):
    (tmp_path / "docs").mkdir()
    for name in ("_quarto.yml", "index.qmd", "styles.css", "_containers.ejs.md"):
        shutil.copy2(ROOT / "docs" / name, tmp_path / "docs" / name)
    shutil.copytree(ROOT / "docs" / "_extensions", tmp_path / "docs" / "_extensions")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    write_file(tmp_path, "spac/spac-gpu/Dockerfile.v1.0.1")
    write_file(tmp_path, "spac/spac-gpu/Dockerfile.v1.0.0")
    write_file(tmp_path, "spac/spac-gpu/v1.0.1.README.md")
    write_file(tmp_path, "base/ccbr_ubuntu/Dockerfile.v2")
    write_file(tmp_path, "base/ccbr_ubuntu/failing.Dockerfile.v3")

    def available(image, tag):
        if image == "spac-gpu":
            return PUBLISHED
        return {"Docker Hub": {"linux/amd64"}, "GHCR": None}

    catalog.generate_listing(tmp_path, tmp_path / "docs/containers.yml", lookup=available)
    config_path = tmp_path / "docs/_quarto.yml"
    config = yaml.safe_load(config_path.read_text())
    assert config["project"].pop("pre-render") == (
        "python3 ../scripts/generate_container_listing.py"
    )
    config["website"] = {"title": config["website"]["title"]}
    config_path.write_text(yaml.safe_dump(config))

    result = subprocess.run(
        ["quarto", "render", "docs", "--quiet"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    html = (tmp_path / "docs" / "_site" / "index.html").read_text(encoding="utf-8")
    search = json.loads((tmp_path / "docs" / "_site" / "search.json").read_text())

    assert html.count("<tr data-index=") == 2
    assert not list((tmp_path / "docs" / "_site").glob("*containers.ejs.html"))
    assert not any("containers.ejs" in entry["href"] for entry in search)
    assert 'class="quarto-listing-table table table-striped"' in html
    assert 'value="listing-title"' in html
    assert 'value="listing-tag"' not in html
    assert 'value="listing-dockerhub"' not in html
    assert "<th>Tag</th>" not in html
    assert "<th>Registries</th>" in html and "<th>Platforms</th>" in html
    assert (
        'class="listing-title" href="https://github.com/CCBR/Dockers2/blob/main/'
        'spac/spac-gpu/v1.0.1.README.md"'
    ) in html
    assert '<span class="listing-title">ccbr_ubuntu</span>' in html
    assert "<code>linux/amd64</code>" in html and "<code>linux/arm64</code>" in html
    assert html.count('alt="Docker Hub:') == 2
    assert html.count('alt="GHCR:') == 1
    assert (
        'src="https://img.shields.io/badge/Docker%20Hub-v1.0.1-2496ED.svg?'
        'logo=docker&amp;logoColor=white"'
    ) in html
    assert (
        'src="https://img.shields.io/badge/GHCR-v1.0.1-24292f.svg?'
        'logo=github&amp;logoColor=white"'
    ) in html
    assert (
        'href="https://hub.docker.com/r/nciccbr/spac-gpu/tags?name=v1.0.1"'
    ) in html
    assert (
        'href="https://github.com/orgs/CCBR/packages/container/package/'
        'spac-gpu?tag=v1.0.1"'
    ) in html
    assert (
        'href="https://github.com/CCBR/Dockers2/blob/main/'
        'spac/spac-gpu/Dockerfile.v1.0.1"'
    ) in html
