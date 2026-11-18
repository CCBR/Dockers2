"""Generate Quarto listing metadata from versioned Dockerfiles."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from coordinate_docker_build import image_identity


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "CCBR/Dockers2"
IMAGE_NAME = re.compile(r"[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*")
IMAGE_TAG = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}")
MANIFEST_TYPES = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


class RegistryRedirectHandler(HTTPRedirectHandler):
    """Keep registry bearer tokens off redirected blob-storage requests."""

    def redirect_request(self, request, response, code, message, headers, url):
        redirected = super().redirect_request(
            request, response, code, message, headers, url
        )
        if redirected is not None and (
            urlsplit(redirected.full_url)[:2] != urlsplit(request.full_url)[:2]
        ):
            redirected.remove_header("Authorization")
        return redirected


def read_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = Request(url, headers=headers or {})
    with build_opener(RegistryRedirectHandler()).open(request, timeout=30) as response:
        return json.load(response)


def platform_name(platform: dict) -> str | None:
    os_name, architecture = platform.get("os"), platform.get("architecture")
    if os_name == "unknown" or architecture == "unknown":
        return None
    if not os_name or not architecture:
        raise ValueError(f"Registry returned an incomplete platform: {platform!r}")
    parts = [os_name, architecture]
    if platform.get("variant"):
        parts.append(platform["variant"])
    return "/".join(parts)


def dockerhub_platforms(image: str, tag: str) -> set[str] | None:
    url = (
        f"https://hub.docker.com/v2/namespaces/nciccbr/repositories/"
        f"{quote(image, safe='')}/tags/{quote(tag, safe='')}"
    )
    try:
        payload = read_json(url)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    platforms = {
        name for entry in payload["images"] if (name := platform_name(entry)) is not None
    }
    if not platforms:
        raise ValueError(f"Docker Hub returned no image platforms for {image}:{tag}")
    return platforms


def dockerhub_latest_tag(image: str) -> str | None:
    """Return the most recently pushed Docker Hub tag for an image."""
    url = (
        f"https://hub.docker.com/v2/namespaces/nciccbr/repositories/"
        f"{quote(image, safe='')}/tags?"
        + urlencode({"page_size": 1, "ordering": "last_updated"})
    )
    try:
        payload = read_json(url)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    results = payload.get("results") or []
    return results[0]["name"] if results else None


def ghcr_platforms(image: str, tag: str) -> set[str] | None:
    repository = f"ccbr/{image}"
    token_url = "https://ghcr.io/token?" + urlencode(
        {"scope": f"repository:{repository}:pull", "service": "ghcr.io"}
    )
    try:
        token = read_json(token_url)["token"]
    except HTTPError as error:
        if error.code == 403:
            payload = json.load(error)
            if any(item.get("code") == "DENIED" for item in payload.get("errors", [])):
                print(f"GHCR package is not public: {repository}", file=sys.stderr)
                return None
        raise
    headers = {"Authorization": f"Bearer {token}", "Accept": MANIFEST_TYPES}
    base = f"https://ghcr.io/v2/{repository}"
    try:
        manifest = read_json(f"{base}/manifests/{quote(tag, safe='')}", headers)
    except HTTPError as error:
        if error.code == 404:
            return None
        raise
    if "manifests" in manifest:
        platforms = {
            name
            for entry in manifest["manifests"]
            if entry.get("annotations", {}).get("vnd.docker.reference.type")
            != "attestation-manifest"
            and (name := platform_name(entry["platform"])) is not None
        }
    else:
        config = read_json(f"{base}/blobs/{manifest['config']['digest']}", headers)
        name = platform_name(config)
        platforms = {name} if name is not None else set()
    if not platforms:
        raise ValueError(f"GHCR returned no image platforms for {image}:{tag}")
    return platforms


def registry_platforms(image: str, tag: str) -> dict[str, set[str] | None]:
    return {
        "Docker Hub": dockerhub_platforms(image, tag),
        "GHCR": ghcr_platforms(image, tag),
    }


def dockerfiles(root: Path) -> list[PurePosixPath]:
    """Find versioned Dockerfiles tracked by Git or not yet ignored."""
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "**/Dockerfile.*",
            "Dockerfile.*",
        ],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = (PurePosixPath(os.fsdecode(path)) for path in result.stdout.split(b"\0") if path)
    return sorted(
        path
        for path in paths
        if path.name.startswith("Dockerfile.") and (root / path).is_file()
    )


def version_key(tag: str) -> tuple:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)(?:-([a-zA-Z0-9_.-]+))?", tag)
    if not match:
        raise ValueError(f"Cannot determine the latest numeric version for tag {tag!r}")
    numbers = tuple(int(part) for part in match[1].split("."))
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers = numbers[:-1]
    suffix = match[2]
    prerelease = tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in re.split(r"(\d+)", suffix or "")
    )
    return numbers, suffix is None, prerelease, tag


def latest_dockerfiles(root: Path) -> list[PurePosixPath]:
    latest = {}
    for path in dockerfiles(root):
        image, tag = image_identity(path.as_posix(), REPOSITORY)
        key = version_key(tag)
        if image in latest and key == latest[image][0]:
            raise ValueError(f"Multiple Dockerfiles define {image}:{tag}")
        if image not in latest or key > latest[image][0]:
            latest[image] = key, path
    return [latest[image][1] for image in sorted(latest)]


def badge(label: str, tag: str, color: str, logo: str, href: str) -> str:
    """Create a linked badge displaying a published image tag."""
    escaped_tag = quote(tag.replace("_", "__").replace("-", "--"), safe="")
    image = (
        f"https://img.shields.io/badge/{quote(label, safe='')}-{escaped_tag}-{color}.svg"
        f"?logo={logo}&logoColor=white"
    )
    return f"[![{label}: {tag}]({image})]({href})"


def listing_item(
    dockerfile: PurePosixPath,
    root: Path,
    registries: dict[str, set[str] | None],
    tag: str | None = None,
) -> dict[str, str]:
    """Describe the published image and source corresponding to a Dockerfile."""
    image, release_tag = image_identity(dockerfile.as_posix(), REPOSITORY)
    tag = tag or release_tag
    if not IMAGE_NAME.fullmatch(image):
        raise ValueError(f"Invalid image repository name for {dockerfile}: {image!r}")
    if not IMAGE_TAG.fullmatch(tag):
        raise ValueError(f"Invalid image tag for {dockerfile}: {tag!r}")

    image_url = quote(image, safe="")
    dockerhub = (
        f"https://hub.docker.com/r/nciccbr/{image_url}/tags?"
        f"{urlencode({'name': tag})}"
    )
    ghcr = (
        f"https://github.com/orgs/CCBR/packages/container/package/{image_url}?"
        f"{urlencode({'tag': tag})}"
    )
    source_path = quote(dockerfile.as_posix(), safe="/")
    source = f"https://github.com/{REPOSITORY}/blob/main/{source_path}"
    badges = []
    if registries["Docker Hub"] is not None:
        badges.append(badge("Docker Hub", tag, "2496ED", "docker", dockerhub))
    if registries["GHCR"] is not None:
        badges.append(badge("GHCR", tag, "24292f", "github", ghcr))
    published = {
        registry: platforms
        for registry, platforms in registries.items()
        if platforms is not None
    }
    if not published:
        platforms = "Not published"
    elif len({frozenset(platforms) for platforms in published.values()}) == 1:
        platforms = ", ".join(
            f"`{platform}`" for platform in sorted(next(iter(published.values())))
        )
    else:
        platforms = "<br>".join(
            f"{registry}: " + ", ".join(f"`{platform}`" for platform in sorted(platforms))
            for registry, platforms in published.items()
        )
    item = {
        "title": image,
        "tag": tag,
        "registries": " ".join(badges),
        "platforms": platforms,
        "source": f"[{dockerfile.name}]({source})",
    }
    readme = dockerfile.with_name(f"{tag}.README.md")
    if (root / readme).is_file():
        item["readme"] = (
            f"https://github.com/{REPOSITORY}/blob/main/{quote(readme.as_posix(), safe='/')}"
        )
    return item


def generate_listing(
    root: Path,
    output: Path,
    lookup=registry_platforms,
    latest_pushed=dockerhub_latest_tag,
) -> None:
    """Write deterministic YAML-compatible metadata for the Quarto listing."""
    def describe(path):
        image, tag = image_identity(path.as_posix(), REPOSITORY)
        registries = lookup(image, tag)
        if all(platforms is None for platforms in registries.values()):
            # The release tag is unpublished; show the newest pushed tag instead.
            fallback = latest_pushed(image)
            if fallback and fallback != tag:
                tag, registries = fallback, lookup(image, fallback)
        return listing_item(path, root, registries, tag)

    with ThreadPoolExecutor(max_workers=6) as executor:
        items = list(executor.map(describe, latest_dockerfiles(root)))
    output.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    generate_listing(ROOT, ROOT / "docs" / "containers.yml")
