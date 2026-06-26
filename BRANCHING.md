# QB-SAO Branching & Contributing Guide

This document describes the Git branching strategy, daily workflow, and recommended GitHub settings for **QB-SAO**.

---

## Branch Hierarchy

```
main          ← Production. Tagged releases only.
  └── staging     ← QA gate. Release candidates tested here.
        └── develop   ← Integration. Completed features land here.
              └── feature/*  ← Your working branch (short-lived).
```

| Branch | Created From | Merges Into | Protected? |
|--------|-------------|-------------|------------|
| `main` | — | — | ✅ Yes |
| `staging` | `develop` | `main` | ✅ Yes |
| `develop` | `main` (initially) | `staging` | ✅ Yes |
| `feature/*` | `develop` | `develop` | ❌ No |
| `hotfix/*` | `main` | `main` + `develop` | ❌ No |

---

## Daily Workflow

### 1. Start a New Feature

```bash
# Always start from an up-to-date develop
git checkout develop
git pull origin develop
git checkout -b feature/my-feature-name
```

**Naming conventions:**
- Features: `feature/kiosk-redesign`, `feature/billing-export`
- Bug fixes: `feature/fix-login-redirect`, `feature/fix-order-filter`
- Experiments: `feature/experiment-sse-polling`

### 2. Work and Commit

```bash
# Make small, focused commits
git add .
git commit -m "feat: add kiosk order display"

# Push your branch to GitHub
git push -u origin feature/my-feature-name
```

**Commit message conventions:**
| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `refactor:` | Code restructuring (no behavior change) |
| `chore:` | Maintenance, dependencies, CI/CD |
| `docs:` | Documentation only |
| `test:` | Adding or updating tests |

### 3. Create a Pull Request (feature → develop)

1. Go to GitHub → **Pull Requests** → **New Pull Request**
2. Base: `develop` ← Compare: `feature/my-feature-name`
3. Write a clear description of what changed and why
4. Wait for **CI to pass** (tests + syntax check)
5. Merge using **"Squash and merge"** for a clean history
6. **Delete the feature branch** after merge

### 4. Promote to Staging (develop → staging)

When a set of features is ready for QA:

```bash
# Create a PR: develop → staging
# Title: "Release candidate: v0.X.0"
```

1. Go to GitHub → **Pull Requests** → **New Pull Request**
2. Base: `staging` ← Compare: `develop`
3. Review the full diff — this is your release candidate
4. CI must pass
5. Merge using **"Create a merge commit"** to preserve history

### 5. Release to Production (staging → main)

After QA validation on staging:

```bash
# Create a PR: staging → main
# Title: "Release v0.X.0"
```

1. Go to GitHub → **Pull Requests** → **New Pull Request**
2. Base: `main` ← Compare: `staging`
3. Review carefully — this goes to production
4. CI must pass
5. Merge using **"Create a merge commit"**
6. **Tag the release** on `main`:

```bash
git checkout main
git pull origin main
git tag -a v0.X.0 -m "Release v0.X.0: short description"
git push origin v0.X.0
```

---

## Hotfix Procedure

For **emergency fixes** that can't wait for the normal flow:

```bash
# Branch from main (production)
git checkout main
git pull origin main
git checkout -b hotfix/fix-critical-bug

# Fix, commit, push
git add .
git commit -m "hotfix: fix critical payment crash"
git push -u origin hotfix/fix-critical-bug

# Create PR: hotfix → main
# After merge, ALSO cherry-pick into develop:
git checkout develop
git pull origin develop
git cherry-pick <hotfix-commit-hash>
git push origin develop
```

> ⚠️ **Always** propagate hotfixes back to `develop` to avoid regression.

---

## Release Tagging Convention

Use [Semantic Versioning](https://semver.org/):

```
vMAJOR.MINOR.PATCH
```

| Part | When to increment |
|------|------------------|
| **MAJOR** | Breaking changes (e.g., API changes, DB schema changes) |
| **MINOR** | New features, backward-compatible |
| **PATCH** | Bug fixes, minor tweaks |

Examples: `v1.0.0`, `v1.1.0`, `v1.1.1`

---

## Recommended GitHub Branch Protection Rules

Apply these settings via **GitHub → Settings → Branches → Add rule** for each protected branch.

### `main` (Production) — Strictest

| Setting | Value |
|---------|-------|
| **Require a pull request before merging** | ✅ Enabled |
| Require approvals | 1 approval minimum |
| Dismiss stale pull request approvals when new commits are pushed | ✅ Enabled |
| **Require status checks to pass before merging** | ✅ Enabled |
| Required checks | `Tests (Python 3.12)`, `Tests (Python 3.13)`, `Syntax Check` |
| Require branches to be up to date before merging | ✅ Enabled |
| **Require conversation resolution before merging** | ✅ Enabled |
| **Do not allow bypassing the above settings** | ✅ Enabled |
| **Restrict who can push to matching branches** | ✅ Only via PR |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |

### `staging` (QA Gate) — Strict

| Setting | Value |
|---------|-------|
| **Require a pull request before merging** | ✅ Enabled |
| Require approvals | 1 approval minimum |
| **Require status checks to pass before merging** | ✅ Enabled |
| Required checks | `Tests (Python 3.12)`, `Tests (Python 3.13)`, `Syntax Check` |
| Require branches to be up to date before merging | ✅ Enabled |
| **Require conversation resolution before merging** | ✅ Enabled |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |

### `develop` (Integration) — Moderate

| Setting | Value |
|---------|-------|
| **Require a pull request before merging** | ✅ Enabled |
| Require approvals | 0 (self-merge OK for solo dev) |
| **Require status checks to pass before merging** | ✅ Enabled |
| Required checks | `Tests (Python 3.12)`, `Tests (Python 3.13)`, `Syntax Check` |
| Require branches to be up to date before merging | ✅ Enabled |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |

> **Note:** Since you're currently a solo developer, `develop` allows self-merge (0 approvals required). As the team grows, increase this to 1.

---

## Quick Reference Card

```
╔═══════════════════════════════════════════════════════╗
║              QB-SAO Git Flow Cheat Sheet              ║
╠═══════════════════════════════════════════════════════╣
║                                                       ║
║  New feature?                                         ║
║    git checkout develop                               ║
║    git checkout -b feature/name                       ║
║    ... work ... commit ... push ...                   ║
║    → PR into develop                                  ║
║                                                       ║
║  Ready for QA?                                        ║
║    → PR: develop → staging                            ║
║                                                       ║
║  Ready for production?                                ║
║    → PR: staging → main                               ║
║    → Tag: git tag -a v1.0.0 -m "Release v1.0.0"      ║
║                                                       ║
║  Emergency hotfix?                                    ║
║    git checkout main                                  ║
║    git checkout -b hotfix/name                        ║
║    → PR into main, then cherry-pick into develop      ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝
```
