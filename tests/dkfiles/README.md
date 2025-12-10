# How to build test server

Build the image

```Bash
docker build \
  --build-arg GITLAB_USERNAME=your-gitlab-username \
  --build-arg GITLAB_TOKEN=your-personal-access-token \
  -t my-image .
```
