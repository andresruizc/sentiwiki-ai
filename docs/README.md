## Documentation Overview

This `docs/` directory is organized to reflect the way you work on the project: backend-first, with clear separation between architecture, deployment, troubleshooting, and blog content.

```text
docs/
  README.md             # You are here – navigation for all docs
  architecture/         # System & code architecture (formerly THEORY)
  deployment/           # AWS & CI/CD deployment guides (formerly AWS_CI_CD)
  troubleshooting/      # Fixes, gotchas, learnings (formerly LEARNINGS)
  blog/                 # Blog articles about the project (formerly BLOG_SUBSTACK)
  images/               # Shared images used in docs and README
```

### Architecture (`docs/architecture/`)

High-level and detailed architecture notes:

- Core files like:
  - `ARCHITECTURE_REVIEW_CORRECTED.md`
  - `STREAMING_ARCHITECTURE.md`
  - `UNIT_TESTING_FUNDAMENTALS.md`
  - `DEPLOYMENT_WORKFLOW.md`
- Data pipeline details under:
  - `architecture/data_pipeline/` (scraping, chunking, embeddings, etc.)
- Docker & infrastructure theory:
  - `DOCKER_COMPOSE_EXPLAINED.md`
  - `DOCKER_COMMANDS.md`
  - `IAM_PERMISSIONS_REQUIRED.md`

Use this folder when you want to understand or extend how the system is designed.

### Deployment (`docs/deployment/`)

End‑to‑end deployment to AWS and CI/CD:

- `AWS_DEPLOYMENT_GUIDE.md` – narrative overview
- Phase files:
  - `00_COMPLETE_OVERVIEW.md` … `07_PHASE4_ECS_DEPLOYMENT.md`
- GitHub Actions / CI pipeline notes:
  - `01_GITHUB_ACTIONS_BASICS.md`
  - `03_PHASE2_DOCKER_BUILDS.md`

This folder pairs with code under `deployment/aws/` in the repo root.

### Troubleshooting (`docs/troubleshooting/`)

Production issues, fixes, and lessons learned:

- General troubleshooting:
  - `CORS_FIX.md`, `CORS_PREFLIGHT_ERROR.md`
  - `DOCKER_PROBLEMS_SOLVED.md`
  - `PROMETHEUS_GRAFANA_MONITORING.md`
  - `STARTUP_OPTIMIZATION.md`
- Frontend learning path under `troubleshooting/FRONTEND/`
- Higher‑level “learnings”:
  - `LESSONS_LEARNED.md`
  - `REAL_VS_FAKE_STREAMING.md`
  - `QUERY_DECOMPOSITION_*` etc.

Go here when something is broken or you want to revisit past debugging work.

### Blog (`docs/blog/`)

Blog content and publication assets:

- `blog/articles/` – all long‑form articles (originally `BLOG_SUBSTACK/`):
  - `00-TECH-STACK-RATIONALE.md` … `16-PRODUCTION-QUERY-LOGGING-S3.md`
  - Supporting pieces like `READERS-GUIDE.md`, `LESSONS-LEARNED-SYNTHESIS.md`
- `blog/README.md` – small index for blog‑specific navigation
- `LINKEDIN_POST_READY_TO_COPY.txt` – social snippets for sharing the project

Use this folder when writing or updating public‑facing content.

### Images (`docs/images/`)

Shared images (e.g. screenshots for README/blog). Currently:

- `frontend-home.png` – main UI screenshot used in the root `README.md`.


