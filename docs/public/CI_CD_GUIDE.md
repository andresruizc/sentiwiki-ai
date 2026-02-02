# CI/CD Guide: GitHub Actions Workflow

This guide explains how the CI/CD pipeline works for SentiWiki AI using GitHub Actions.

## Overview

The project uses **GitHub Actions** to automate testing, building Docker images, pushing to AWS ECR, and deploying to AWS ECS. The workflow is defined in `.github/workflows/test.yml`.

## Workflow Structure

The CI/CD pipeline consists of **4 phases** that run automatically on code pushes:

### Phase 1: Automated Testing
- **Job**: `test`
- **Triggers**: Runs on pushes to `main` or `develop` branches, and on pull requests to `main`
- **What it does**:
  - Sets up Python 3.11 environment
  - Installs project dependencies using `uv`
  - Runs pytest test suite
  - Generates coverage reports
- **Purpose**: Catch bugs and regressions before deployment

### Phase 2: Docker Build
- **Jobs**: `build-api`, `build-frontend`
- **Triggers**: Runs after tests pass (or immediately if tests are disabled)
- **What it does**:
  - Builds Docker images for API and Frontend
  - Uses Docker Buildx with GitHub Actions cache for faster builds
  - Verifies images are built successfully
- **Purpose**: Ensure Docker images can be built correctly

### Phase 3: Push to ECR
- **Jobs**: `push-api`, `push-frontend`
- **Triggers**: Only runs on pushes to `main` branch (not on PRs or `develop`)
- **What it does**:
  - Configures AWS credentials from GitHub Secrets
  - Logs into Amazon ECR (Elastic Container Registry)
  - Builds and pushes Docker images to ECR with tags:
    - `latest` (always points to most recent)
    - `${{ github.sha }}` (commit-specific tag for versioning)
- **Purpose**: Store Docker images in AWS for ECS deployment

### Phase 4: Deploy to ECS
- **Jobs**: `deploy-api`, `deploy-frontend`
- **Triggers**: Only runs on pushes to `main` branch after successful ECR push
- **What it does**:
  - Updates ECS services to force new deployment
  - ECS automatically pulls the new images and restarts containers
- **Purpose**: Automatically deploy new code to production

## Workflow File Location

The workflow is defined in:
```
.github/workflows/test.yml
```

## Required GitHub Secrets

Before the CI/CD pipeline can work, you must configure these secrets in your GitHub repository:

### AWS Credentials
- `AWS_ACCESS_KEY_ID` - AWS access key for ECR push and ECS deployment
- `AWS_SECRET_ACCESS_KEY` - AWS secret key for ECR push and ECS deployment
- `AWS_REGION` - AWS region (e.g., `us-east-1`, `eu-west-1`)
- `AWS_ACCOUNT_ID` - Your AWS account ID

### LLM API Keys (Optional)
- `ANTHROPIC_API_KEY` - If using Anthropic for LLM
- `OPENAI_API_KEY` - If using OpenAI for LLM
- (Other provider keys as needed)

**How to add secrets:**
1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret with its corresponding value

## Workflow Triggers

The workflow runs automatically in these scenarios:

| Event | Branches | What Runs |
|-------|----------|-----------|
| **Push to `main`** | `main` | All phases: Test → Build → Push → Deploy |
| **Push to `develop`** | `develop` | Test → Build only (no push/deploy) |
| **Pull Request to `main`** | Any → `main` | Test → Build only (no push/deploy) |

**Key Points:**
- **Only `main` branch** triggers ECR push and ECS deployment
- **PRs and `develop` branch** only run tests and builds (safe for testing)
- This prevents accidental deployments from feature branches

## Pipeline Flow Diagram

```
┌─────────────┐
│ Push to Git │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ Phase 1: Test   │ ← Runs on all branches/PRs
│ (pytest)        │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│ Phase 2: Build  │ ← Runs after tests
│ (Docker images) │
└──────┬──────────┘
       │
       ▼ (Only on main branch)
┌─────────────────┐
│ Phase 3: Push   │ ← Only on main branch
│ (ECR)           │
└──────┬──────────┘
       │
       ▼ (Only on main branch)
┌─────────────────┐
│ Phase 4: Deploy │ ← Only on main branch
│ (ECS)            │
└─────────────────┘
```

## Understanding the Workflow File

The workflow file (`.github/workflows/test.yml`) is written in YAML and defines:

1. **When to run** (`on:` section):
   ```yaml
   on:
     push:
       branches: [main, develop]
     pull_request:
       branches: [main]
   ```

2. **What jobs to run** (`jobs:` section):
   - Each job runs in parallel or sequentially (using `needs:`)
   - Jobs can have conditions (using `if:`)

3. **Job steps**:
   - Each step is a discrete action (checkout code, install dependencies, run commands, etc.)
   - Steps use GitHub Actions (reusable actions from the marketplace)

## Customizing the Workflow

### Disable Tests Temporarily

If you need to skip tests (e.g., for urgent hotfixes), you can modify the workflow:

```yaml
# In .github/workflows/test.yml
test:
  # ... job definition ...
  if: false  # This disables the test job
```

**Note**: The build jobs have `needs: test`, so you'll also need to remove that dependency:

```yaml
build-api:
  needs: []  # Remove dependency on test
```

### Change Deployment Branch

To deploy from a different branch (e.g., `production`):

```yaml
# In push-api and push-frontend jobs
if: github.ref == 'refs/heads/production' && github.event_name == 'push'
```

### Add Manual Trigger

To allow manual workflow runs:

```yaml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  workflow_dispatch:  # Add this for manual triggers
```

Then you can trigger the workflow from GitHub Actions UI → "Run workflow".

## Monitoring Workflow Runs

1. **View workflow runs**: Go to your GitHub repository → **Actions** tab
2. **See job status**: Each job shows as ✅ (success), ❌ (failure), or ⏳ (running)
3. **View logs**: Click on any job to see detailed logs
4. **Debug failures**: Check the logs for error messages

## Common Issues

### Workflow Fails at "Configure AWS credentials"
- **Cause**: Missing or incorrect AWS secrets
- **Fix**: Verify `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION` are set correctly

### Workflow Fails at "Login to Amazon ECR"
- **Cause**: ECR repository doesn't exist or AWS credentials don't have ECR permissions
- **Fix**: 
  1. Create ECR repositories: `esa-iagen-api` and `esa-iagen-frontend`
  2. Ensure AWS credentials have `ecr:GetAuthorizationToken` and `ecr:*` permissions

### Workflow Fails at "Deploy to ECS"
- **Cause**: ECS service doesn't exist or AWS credentials don't have ECS permissions
- **Fix**: 
  1. Ensure ECS cluster and services are created (see AWS Deployment Guide)
  2. Verify AWS credentials have `ecs:UpdateService` permission

### Tests Fail
- **Cause**: Code changes broke tests or dependencies are missing
- **Fix**: Run tests locally first: `uv run pytest tests/ -v`

## Best Practices

1. **Test locally first**: Always run tests before pushing to avoid CI failures
2. **Use feature branches**: Create PRs to `main` to test the workflow without deploying
3. **Monitor deployments**: Check AWS ECS console after deployment to verify services are healthy
4. **Keep secrets secure**: Never commit secrets to the repository; always use GitHub Secrets
5. **Review workflow changes**: Test workflow changes on a feature branch before merging to `main`

## Related Documentation

- **GitHub Secrets Setup**: See [README.md](../../README.md#cicd-configuration-github-secrets)
- **AWS Deployment Guide**: See [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)
- **AWS IAM Requirements**: See [AWS_IAM_REQUIREMENTS.md](AWS_IAM_REQUIREMENTS.md)

