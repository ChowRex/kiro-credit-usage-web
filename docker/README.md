# Docker deployment assets

This directory keeps the container deployment assets together:

- `Dockerfile` builds the dashboard image from the repository-root build context.
- `compose.yaml` runs the long-lived `web` service and the one-shot `refresh` service.
- `container.env.example` documents the required private host paths and image tag.
- `kiro-credit-usage.crontab.template` starts the one-shot refresh container at Beijing 10:00.

Keep `.dockerignore` at the repository root because the Docker build context is the repository root. It prevents private runtime configuration, AWS credentials, tokens, snapshots, and development-only files from entering the image build context.

For complete English and Chinese setup instructions, including local builds, Docker Hub pulls, host crontab, volume ownership, and security constraints, see the repository [README](../README.md).
