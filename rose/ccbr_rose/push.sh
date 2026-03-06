#!/bin/bash
REPONAME="ccbr_chipenrich"
BUILD_TAG="v1"
docker push nciccbr/${REPONAME}:${BUILD_TAG} 
docker tag nciccbr/${REPONAME}:${BUILD_TAG} nciccbr/${REPONAME}:latest
docker push nciccbr/${REPONAME}:latest
