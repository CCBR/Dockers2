# Dockers2

Docker container recipes for CCBR

<https://hub.docker.com/u/nciccbr>

## Docker build workflows

Develop changes on a branch and open a pull request against `main`. For a
Dockerfile named `Dockerfile.v2`, the workflows use these image tags:

| Trigger | Tag | Publishing |
| --- | --- | --- |
| Pull request to `main` | `v2-dev` | Docker Hub and GHCR for same-repository PRs; fork PRs build without publishing |
| Push to an `autobuild` branch | `v2-dev` | Docker Hub and GHCR |
| Push to `main` | `v2` | Docker Hub and GHCR |

The `-dev` tag is shared by all previews of the same image and version. A
later successful push can overwrite another PR's preview, so use the
unsuffixed version tag for stable images. Existing registry tags are not
renamed or deleted.

The manual build workflow offers `dev` for a preview or `main` for the
unsuffixed version tag. It only permits publishing a stable tag when run from
`main`. The dispatch workflow builds a `-dev` preview and opens a PR to
`main`; merging the Dockerfile triggers the stable build.

For dispatched builds, the workflow records the source repository and its
exact commit in `.Dockerfile.<version>.source.json` next to the Dockerfile.
Automatic and manual builds restore that source checkout into the image's
build context. The source repository must remain accessible to the workflow
token. Source files are overlaid on the Dockerfile directory, preserving the
selected Dockerfile and metadata; other files already in that directory remain.
Changes to the metadata also trigger a rebuild; keep it alongside the
Dockerfile. Older dispatched Dockerfiles do not have this metadata and must be
dispatched again if they need files from their source repository.

### Build platforms

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

### Migrating from `dev`

Changing the workflows does not change GitHub's default branch or existing
pull requests. Integrate the current `dev` changes into `main` first, then
change the default branch and branch protections to `main` and retarget
outstanding PRs. Keep `dev` until its remaining work and integrations have
been accounted for.

The first integration into `main` can trigger builds for many changed
Dockerfiles. Allow time for those builds and ensure both registries grant the
repository permission to publish. Deleted Dockerfiles are skipped.
