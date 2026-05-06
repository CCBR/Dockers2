#!/bin/bash
REPONAME="ccbr_rose""
BUILD_TAG="v2"
docker push nciccbr/${REPONAME}:${BUILD_TAG} 
docker tag nciccbr/${REPONAME}:${BUILD_TAG} nciccbr/${REPONAME}:latest
docker push nciccbr/${REPONAME}:latest
