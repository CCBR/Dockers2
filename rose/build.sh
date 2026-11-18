#!/bin/bash
REPONAME="ccbr_rose"
BUILD_TAG="v3"
docker buildx build \
  --build-arg REPONAME="${REPONAME}" \
  --build-arg BUILD_TAG="${BUILD_TAG}" \
  --build-arg DOCKERFILE="Dockerfile.${BUILD_TAG}" \
  --build-arg BUILD_DATE=$(date +%Y%m%d) \
  -t nciccbr/${REPONAME}:${BUILD_TAG} \
  -f Dockerfile.${BUILD_TAG} \
  --load .
