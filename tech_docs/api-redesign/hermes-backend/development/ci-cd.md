# CI/CD Strategy — Hermes Backend

## Overview

The CI/CD pipeline automates linting, testing, building, and deployment for the Hermes Backend. The pipeline runs on **GitHub Actions** and targets two distinct deployment environments:

| Environment | Target | Trigger |
|-------------|--------|---------|
| **CI (PR)** | Every pull request to `main` or `develop` | `pull_request` |
| **CI (Push)** | Every push to `main` or `develop` | `push` |
| **Deploy** | Raspberry Pi 4 (sBitx v2 hardware) | Manual workflow dispatch or tag push |

## Pipeline Architecture

```
Pull Request / Push to main, develop
        │
        ├──▶ Lint (ESLint)
        │
        ├──▶ Format Check (Prettier)
        │
        ├──▶ Unit Tests (Vitest)
        │
        ├──▶ Integration Tests (SQLite in-memory)
        │
        ├──▶ Build (TypeScript → dist/)
        │
        └──▶ (on main tag) → Deploy to Pi 4
```

## GitHub Actions Workflows

### 1. CI Pipeline (`.github/workflows/ci.yml`)

Triggered on: `pull_request` to `main`/`develop`, `push` to `main`/`develop`

```yaml
name: CI

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  lint:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run lint

  format-check:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run format:check

  test:
    needs: [lint, format-check]
    runs-on: ubuntu-24.04
    strategy:
      matrix:
        node-version: [20]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: npm
      - run: npm ci
      - run: npm test

  coverage:
    needs: [test]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run test:coverage
      - uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage/

  build:
    needs: [test]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

### 2. Deploy to Pi 4 (`.github/workflows/deploy.yml`)

Triggered on: push of a version tag (`v*`), or manual `workflow_dispatch`

```yaml
name: Deploy to Raspberry Pi 4

on:
  push:
    tags: ['v*']
  workflow_dispatch:
    inputs:
      environment:
        description: 'Deployment target'
        required: true
        type: choice
        options:
          - staging
          - production

jobs:
  build-and-deploy:
    runs-on: ubuntu-24.04
    environment: ${{ inputs.environment || 'production' }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci --omit=dev
      - run: npm run build

      # Deploy via rsync over SSH to Raspberry Pi 4
      - name: Deploy to Pi 4
        uses: easingthemes/ssh-deploy@v5
        with:
          SSH_PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
          REMOTE_HOST: ${{ secrets.PI4_HOST }}
          REMOTE_USER: ${{ secrets.PI4_USER }}
          TARGET: /opt/hermes-backend/
          EXCLUDE: |
            node_modules/
            .git/
            tests/
            docs/
            prompts/

      # Restart the systemd service on the Pi
      - name: Restart service
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PI4_HOST }}
          username: ${{ secrets.PI4_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/hermes-backend
            npm ci --omit=dev
            npm run db:migrate
            sudo systemctl restart hermes-backend
            sudo systemctl status hermes-backend
```

### 3. Nightly Security Scan (`.github/workflows/security-scan.yml`)

```yaml
name: Nightly Security Scan

on:
  schedule:
    - cron: '0 3 * * *'  # Daily at 3 AM UTC

jobs:
  audit:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm audit --audit-level=high
```

## Docker Strategy

A `Dockerfile` is maintained for local testing and potential containerized deployment:

```dockerfile
# Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
RUN apk add --no-cache sqlite-libs
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
USER node
EXPOSE 3000
CMD ["node", "--max-old-space-size=384", "dist/server.js"]
```

**Note**: Docker is primarily for CI testing and local development. Production sBitx v2 deployments run the Node.js process directly (no container) to minimize memory overhead on the Raspberry Pi 4.

## Required Secrets

| Secret | Purpose |
|--------|---------|
| `SSH_PRIVATE_KEY` | SSH key for deploying to Raspberry Pi 4 |
| `PI4_HOST` | Hostname or IP of the target Pi 4 |
| `PI4_USER` | SSH username on the Pi 4 |

## Environment Strategy

| Environment | Purpose | Branch Protection |
|-------------|---------|:---:|
| `development` | Local dev; `.env` from `.env.example` | — |
| `staging` | Pi 4 test station; manual deploy | Requires review |
| `production` | Field-deployed Pi 4 stations; tag-triggered only | Requires review + tag |

## Quality Gates

| Gate | Threshold | Enforced In |
|------|:---:|---|
| ESLint errors | 0 | CI lint job |
| Prettier violations | 0 | CI format-check job |
| Unit test coverage | ≥ 80% lines | CI coverage job |
| Integration tests pass | 100% | CI test job |
| `npm audit` high/critical | 0 | Nightly scan (alerts, non-blocking) |

## Pre-Commit Hooks (Recommended)

Use [husky](https://typicode.github.io/husky/) + [lint-staged](https://github.com/lint-staged/lint-staged) for pre-commit checks:

```bash
# .husky/pre-commit
npx lint-staged
```

```json
// package.json
{
  "lint-staged": {
    "*.ts": ["eslint --fix", "prettier --write"],
    "*.md": ["prettier --write"]
  }
}
```

## Manual Verification Checklist

Before tagging a release for Pi 4 deployment:

- [ ] All tests pass on `ubuntu-24.04` CI runner
- [ ] `npm run build` produces clean `dist/` output
- [ ] Memory usage tested on actual Pi 4 hardware (< 384 MB V8 heap)
- [ ] SD card write endurance tested (72-hour run)
- [ ] Power-loss simulation passed (WAL recovery verified)
- [ ] `CHANGELOG.md` updated with version entry
- [ ] Version tag pushed (`git tag vX.Y.Z && git push --tags`)