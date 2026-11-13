# Dockers2

Docker container recipes for CCBR

<https://hub.docker.com/u/nciccbr>

## Automatic Docker builds

The `build-docker-auto` workflow builds changed `Dockerfile.*` files for
`linux/amd64` by default. To opt a Dockerfile into additional architectures,
add a `build-platforms` comment, usually near the top of the file:

```dockerfile
# build-platforms: linux/amd64,linux/arm64
FROM ubuntu:26.04
```

The workflow supports `linux/amd64` and `linux/arm64`. List one or both as a
comma-separated value; duplicates, empty declarations, and unsupported
platforms fail the build rather than silently publishing an incomplete image.
Only declare a platform after confirming the base image, packages, downloaded
binaries, and other dependencies support it. Multi-platform builds use
emulation on GitHub's x86 runners and can take significantly longer. Published
images include the requested platforms; local Docker or Podman selects the
matching one automatically.
