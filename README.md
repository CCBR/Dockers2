# Dockers2

Docker container recipes for CCBR

[![Docker Hub](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhub.docker.com%2Fv2%2Fnamespaces%2Fnciccbr%2Frepositories%3Fpage_size%3D1&query=%24.count&label=Docker%20Hub&suffix=%20repositories&logo=docker&logoColor=white&color=2496ED)](https://hub.docker.com/u/nciccbr)
[![GHCR](https://img.shields.io/badge/GHCR-View%20containers-24292f?logo=github&logoColor=white)](https://github.com/orgs/CCBR/packages?ecosystem=container)

## Publishing images

Images are published to Docker Hub under
[`nciccbr`](https://hub.docker.com/u/nciccbr)
and to GitHub Container Registry under
[`ghcr.io/ccbr`](https://github.com/orgs/CCBR/packages?ecosystem=container).
Use the same image name and tag with either registry, for example:

```sh
docker pull nciccbr/<image>:<tag>
docker pull ghcr.io/ccbr/<image>:<tag>
```

Develop changes on a branch and open a pull request against `main`. For a
Dockerfile named `Dockerfile.v2`, the
[automatic build workflow](.github/workflows/build-docker-auto.yml) uses these
image tags:

| Trigger | Tag | Publishing |
| --- | --- | --- |
| Pull request to `main` | `v2-dev` | Docker Hub and GHCR for same-repository PRs; fork PRs build without publishing |
| Push to an `autobuild` branch | `v2-dev` | Docker Hub and GHCR |
| Push to `main` | `v2` | Docker Hub and GHCR |

The `-dev` tag is shared by all previews of the same image and version. A
later successful push can overwrite another PR's preview, so use the
unsuffixed version tag for stable images. Existing registry tags are not
renamed or deleted.

To build an image on demand, run the
[manual workflow](.github/workflows/build-docker-manual.yml) from the Actions
tab and select the Dockerfile. Choose `dev` for a preview or `main` for the
unsuffixed version tag; stable tags can only be published from `main`. Enable
**push** to publish to both registries; leave it unchecked to run without
publishing. To add or update an image from another repository, use the
[dispatch workflow](.github/workflows/build-docker-dispatch.yml), which
publishes a `-dev` preview to both registries and opens a PR to `main`;
merging the Dockerfile triggers the stable build.

Stable publications always build, rather than relying on registry timestamps
that do not account for source-context changes. Automatic and manual stable
builds targeting the same image tag share a queue. After entering the queue,
they skip an outdated checkout if a matching image's build context has changed
on `main`; run the manual workflow again from `main` if needed. The queue holds
up to 100 pending jobs per image tag.

Other builds check the image tag in each target registry. They build if a tag
is missing, older than the Dockerfile's latest commit, missing a requested
platform, or cannot be checked; otherwise, they skip the build. The manual
workflow still checks both registries when **push** is disabled, so an
up-to-date image can skip a build-only run.

For dispatched builds, the workflow records the source repository and its
exact commit in `.Dockerfile.<version>.source.json` next to the Dockerfile.
Automatic and manual builds restore that source checkout into the image's
build context. The source repository must remain accessible to the workflow
token. Source files are overlaid on the Dockerfile directory, preserving the
selected Dockerfile and metadata; other files already in that directory remain.
Changes to the metadata also trigger a rebuild; keep it alongside the
Dockerfile. Older dispatched Dockerfiles do not have this metadata and must be
dispatched again if they need files from their source repository.
Dispatch image tags may contain at most 124 characters, leaving room for the
`-dev` suffix within Docker's 128-character tag limit.

## Docker build platforms

The CI workflows read the selected Dockerfile's `build-platforms` declaration.
When the declaration is absent or empty, the image is built for `linux/amd64`.
To opt a Dockerfile into additional architectures, add a comment at the top of
the file:

```dockerfile
# build-platforms: linux/amd64,linux/arm64
FROM ubuntu:26.04
```

List platforms as comma-separated `os/arch[/variant]` values, using any
platform supported by `docker buildx` (for example, `linux/arm/v7` or
`linux/ppc64le`). Duplicates, malformed values, multiple declarations, and
platforms the base image does not provide fail the build rather than silently
publishing an incomplete image.
For manual builds, a nonempty `platforms` input overrides the declaration and
uses the same validation; leave it blank to use the Dockerfile's selection.
Enable `push` when manually building multiple platforms.

Only declare a platform after confirming the base image, packages, downloaded
binaries, and other dependencies support it.
Multi-platform builds use emulation on GitHub's x86 runners and can take
significantly longer.
Published images include the requested platforms; your local container engine
(Docker, Podman, Apptainer) selects the matching one automatically.
