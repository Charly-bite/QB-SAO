# QB-SAO Project Agents

## DevOps Agent

Purpose: keep CI/CD, release automation, and deployment workflows healthy for QB-SAO.

### Branching Strategy

This project follows a **Git-Flow** branching model:

| Branch | Purpose | Deploys To |
|--------|---------|------------|
| `main` | Production-ready code. Tagged releases only. | Production server |
| `staging` | Pre-production QA gate. Release candidates are tested here. | QA / manual review |
| `develop` | Integration branch. Completed features merge here. | Development server |
| `feature/*` | Short-lived branches for new features. | Local / PR only |
| `hotfix/*` | Emergency production fixes. | Production server |

### Merge Direction (Strict)

```
feature/* → develop → staging → main
hotfix/*  → main (+ cherry-pick into develop)
```

- **Never** push directly to `main` or `staging`.
- **Always** use Pull Requests with CI passing before merge.
- **Delete** feature branches after merge.

### Responsibilities

- Maintain GitHub Actions workflows in `.github/workflows`.
- Keep test pipeline green across supported Python versions.
- Validate deployment jobs for development, staging, and production environments.
- Ensure required GitHub secrets are documented and used safely.
- Enforce branching strategy rules in code reviews.

### Required Checks Before Merge

- CI workflow passes on push and pull request.
- CD workflow syntax is valid and jobs are conditionally gated.
- No secret values are committed to the repository.
- Feature branches must be up-to-date with `develop` before merge.
- `staging` must pass all QA checks before merge into `main`.

### CI/CD Secrets

- DEPLOY_HOST
- DEPLOY_USER
- DEPLOY_SSH_KEY
- DEPLOY_PATH

### Manual Validation Commands

- python -m pip install -r requirements-dev.txt
- python -m pytest tests/ -v --tb=short --cov=. --cov-report=term-missing

### Notes

- Use `main` for production releases (tagged).
- Use `staging` for pre-production validation.
- Use `develop` for development environment deployments.
- Feature branches should be named `feature/<short-description>` (e.g., `feature/kiosk-ui`).
- Hotfix branches should be named `hotfix/<short-description>` (e.g., `hotfix/login-crash`).

---
*Graph Context: Return to [[Home]] (Architecture)*
