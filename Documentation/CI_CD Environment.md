# Open-OMS CI/CD Environment

This repository uses GitHub Actions for CI and CD.

## Workflows

- CI: .github/workflows/ci.yml
- CD: .github/workflows/cd.yml

## CI behavior

- Runs on push and pull requests for main and develop.
- Runs tests with Python 3.12 and 3.13.
- Runs Python syntax validation.
- Uploads coverage.xml as an artifact.

## CD behavior

- Builds and uploads a deploy artifact (zip) on main/develop push or manual dispatch.
- Deploys to development when develop is updated (or manual dispatch target=development).
- Deploys to production when main is updated (or manual dispatch target=production).

## Required GitHub Secrets

- DEPLOY_HOST
- DEPLOY_USER
- DEPLOY_SSH_KEY
- DEPLOY_PATH

## Recommended GitHub Environments

Create these environments in GitHub:

- development
- production

For production, enable required reviewers if you want a manual approval gate.

## Deployment note

The workflow uploads a zip artifact and unpacks it on the remote host into:

- ${DEPLOY_PATH}/open-oms

After extraction, add your service restart command in .github/workflows/cd.yml in the "Run remote deploy command" step.


---
*Graph Context: Return to [[Home]] (Architecture)*
