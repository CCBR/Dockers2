# Dockers2

Docker container recipes for CCBR

<https://hub.docker.com/u/nciccbr>

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
