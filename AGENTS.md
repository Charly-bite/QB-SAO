# Open-OMS Agents

## DevOps Agent

Purpose: keep CI/CD, release automation, and deployment workflows healthy for Open-OMS.

### Responsibilities
- Maintain GitHub Actions workflows in .github/workflows.
- Keep test pipeline green across supported Python versions.
- Validate deployment jobs for development and production environments.
- Ensure required GitHub secrets are documented and used safely.

### Required Checks Before Merge
- CI workflow passes on push and pull request.
- CD workflow syntax is valid and jobs are conditionally gated.
- No secret values are committed to the repository.

### CI/CD Secrets
- DEPLOY_HOST
- DEPLOY_USER
- DEPLOY_SSH_KEY
- DEPLOY_PATH

### Manual Validation Commands
- python -m pip install -r requirements-dev.txt
- python -m pytest tests/ -v --tb=short --cov=. --cov-report=term-missing

### Notes
- Use main for production releases.
- Use develop for development environment deployments.
