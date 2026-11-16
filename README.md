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

The [automatic build workflow](.github/workflows/build-docker-auto.yml) builds
changed `Dockerfile.*` files on matching pushes and pull requests, and
publishes to both registries. Pull requests from forks publish only to Docker
Hub because their tokens cannot write to GHCR.

To build an image on demand, run the
[manual workflow](.github/workflows/build-docker-manual.yml) from the Actions
tab and select the Dockerfile. Enable **push** to publish to both registries;
leave it unchecked to build without publishing. To add or update an image from
another repository, use the
[dispatch workflow](.github/workflows/build-docker-dispatch.yml), which
publishes to both registries.

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
