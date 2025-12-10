#!/bin/bash
target=$1

docker build \
  --build-arg GITLAB_USERNAME=pfqiu \
  --build-arg GITLAB_TOKEN=KcvZCF_FVSehjiqzLsd3 \
  -t "${target}":v1 "./${target}/"