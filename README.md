# Dockers2

Docker container recipes for CCBR

[![Docker Hub](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhub.docker.com%2Fv2%2Fnamespaces%2Fnciccbr%2Frepositories%3Fpage_size%3D1&query=%24.count&label=Docker%20Hub&suffix=%20repositories&logo=docker&logoColor=white&color=2496ED)](https://hub.docker.com/u/nciccbr)
[![GHCR](https://img.shields.io/badge/GHCR-View%20containers-24292f?logo=github&logoColor=white)](https://github.com/orgs/CCBR/packages?ecosystem=container)

<https://ccbr.github.io/Dockers2/>

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

See the [container catalog](https://ccbr.github.io/Dockers2/) to find images,
available registries, and published platforms. For instructions on adding and
testing a container, preview and stable tags, on-demand builds, and platform
support, see the [contributor guide](docs/contribute.qmd).
