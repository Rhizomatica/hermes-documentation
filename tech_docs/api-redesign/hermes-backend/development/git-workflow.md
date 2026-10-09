# Git Workflow — Hermes Backend

**Project**: hermes-backend
**Status**: Active
**Related Documents**: [Development Plan](./plan.md), [Setup Guide](./setup.md), [CI/CD](./ci-cd.md)

---

## 1. Overview

All development follows a **phase-based branching model**. Each phase from the [development plan](./plan.md) gets its own feature branch, a single pull request, a squash merge to `main`, and a version tag.

```
main (stable, always deployable)
  │
  ├── feat/phase-0b-tooling       # Scaffolding: package.json, tsconfig, ESLint, Drizzle
  ├── feat/phase-1-core-infra     # Fastify, SQLite, JWT auth, RBAC, i18n
  ├── feat/phase-2-database       # All 15 tables, repositories, migrations
  ├── feat/phase-3-hal-radio      # HAL, sBitx CLI driver, telemetry
  ├── feat/phase-4-messaging      # Conversations, messages, delivery, reactions
  ├── feat/phase-5-websocket      # Real-time gateway, backpressure
  ├── feat/phase-6-attachments    # File upload, GPS, schedules
  ├── feat/phase-7-system         # Setup wizard, clock sync, resilience
  ├── feat/phase-8-security       # Rate limits, helmet, TLS, legacy shim
  └── feat/phase-9-testing        # Coverage, profiling, Pi 4 deployment
```

---

## 2. Branch Naming Convention

| Element | Format | Examples |
|---------|--------|----------|
| Feature branch | `feat/phase-N-short-desc` | `feat/phase-1-core-infra` |
| Hotfix branch | `fix/short-desc` | `fix/jwt-clock-skew` |
| Sub-branch (long phases) | `feat/phase-N-letter-short-desc` | `feat/phase-7a-setup-config` |

### Complete Phase-to-Branch Mapping

| Phase | Branch Name | Est. Duration | Dependencies |
|:-----:|------------|:---:|--------------|
| 0.B | `feat/phase-0b-tooling` | 1 week | Phase 0.A (docs complete) |
| 1 | `feat/phase-1-core-infra` | 2 weeks | Phase 0.B |
| 2 | `feat/phase-2-database` | 2 weeks | Phase 1 |
| 3 | `feat/phase-3-hal-radio` | 2 weeks | Phase 2 |
| 4 | `feat/phase-4-messaging` | 3 weeks | Phase 2 |
| 5 | `feat/phase-5-websocket` | 2 weeks | Phase 4 |
| 6 | `feat/phase-6-attachments` | 2 weeks | Phase 5 |
| 7 | `feat/phase-7-system` | 3 weeks | Phase 6 |
| 8 | `feat/phase-8-security` | 2 weeks | Phase 7 |
| 9 | `feat/phase-9-testing` | 2 weeks | Phase 8 |

### Sub-Branches for Long Phases (3+ weeks)

Phases spanning 3+ weeks should be broken into sub-branches to keep PRs reviewable:

```
Phase 7 (3 weeks):
  feat/phase-7-system (parent, merged from sub-branches)
    ├── feat/phase-7a-setup-config      (Week 1 — setup wizard + config)
    ├── feat/phase-7b-clock-sync        (Week 2 — clock sync + recovery)
    └── feat/phase-7c-observability     (Week 3 — audit logging + /health/stats)
                                   THEN: feat/phase-7-system → main
```

Sub-branch PRs target the parent phase branch. When all sub-branches are merged, the parent phase branch opens a PR to `main`.

---

## 3. Commit Convention

All commits follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
type(scope): description
```

### Types

| Type | Use When |
|------|----------|
| `feat` | New feature or endpoint |
| `fix` | Bug fix |
| `docs` | Documentation only changes |
| `test` | Adding or updating tests |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `chore` | Tooling, dependencies, configuration |
| `style` | Formatting, semicolons, whitespace (no code change) |

### Scopes

| Scope | Area |
|-------|------|
| `auth` | Authentication, JWT, sessions, RBAC |
| `users` | User CRUD, profile management |
| `db` | Database schema, migrations, repositories |
| `radio` | Radio control, telemetry, HAL |
| `messages` | Message CRUD, delivery, reactions |
| `conversations` | Conversation management |
| `ws` | WebSocket gateway, events |
| `attachments` | File upload/download |
| `geo` | Geolocation, GPS |
| `schedules` | Connection schedules |
| `system` | Health, config, clock, setup |
| `i18n` | Internationalization, translations |
| `security` | Rate limiting, helmet, CORS, input validation |
| `ci` | GitHub Actions, CI/CD pipeline |
| `build` | TypeScript config, bundling |

### Examples

```
feat(auth): add POST /auth/login endpoint with JWT RS256 signing
feat(db): add users table and repository with Drizzle ORM
feat(i18n): add Spanish and Portuguese translation files
test(auth): add login rate limiting integration tests
fix(auth): prevent token reuse race condition in refresh flow
refactor(db): extract DatabaseAdapter interface
chore(ci): add GitHub Actions workflow for PR validation
docs(workflow): add git branching strategy documentation
```

---

## 4. Pull Request Workflow

### 4.1 Creating a New Phase

```bash
# 1. Start from latest main
git checkout main
git pull origin main

# 2. Create the phase branch
git checkout -b feat/phase-1-core-infra

# 3. Develop the phase
# ... write code, commit frequently ...

# 4. Push and open PR
git push -u origin feat/phase-1-core-infra
# Open PR on GitHub: feat/phase-1-core-infra → main
```

### 4.2 PR Title Format

```
Phase N: [Title from Development Plan]
```

**Examples**:
- `Phase 0.B: Tooling Setup (package.json, tsconfig, ESLint, Drizzle)`
- `Phase 1: Core Infrastructure & Auth`
- `Phase 3: HAL & Radio Integration`

### 4.3 PR Body Template

Every PR must use this template:

```markdown
## Summary
Brief description of what this phase delivers.

## Tasks Checklist
- [ ] Task D1.1: Fastify server with health endpoint
- [ ] Task D1.2: SQLite connection with WAL PRAGMAs
- [ ] Task D1.3: Configuration loader
- [ ] ...

## Quality Gate
- [ ] `npm run build` passes with zero TypeScript errors
- [ ] `npm test` passes (all unit + integration tests)
- [ ] `npm run lint` passes (ESLint, Prettier)
- [ ] `npm run i18n:check` passes (where applicable)
- [ ] Test coverage ≥ 80% on new modules

## Audit Traceability
| Finding | Severity | Task | Status |
|---------|:---:|------|:---:|
| C-2 | 🔴 | D2.11 — Mandatory job persistence | ✅ |

## Breaking Changes
None / List any breaking changes from the previous phase.

## Screenshots / Test Output
\```
Paste test runner output here
\```
```

### 4.4 PR Lifecycle

```
Create branch → Develop → Push → Open PR
                                    ↓
                              CI runs (lint, test, build)
                                    ↓
                              Code review
                                    ↓
                              Address feedback
                                    ↓
                              Quality gate passes
                                    ↓
                              Squash merge to main
                                    ↓
                              Delete branch
                                    ↓
                              Tag release
```

### 4.5 Merge Strategy

**Squash merge only.** Each phase branch compresses into a single commit on `main`:

```
main:  9f1c2a3 Phase 1: Core Infrastructure & Auth (#42)
```

This keeps `main` clean with one commit per phase — easy to bisect and revert.

---

## 5. Tagging & Releases

After each phase is merged to `main`, tag the release:

```bash
git checkout main
git pull origin main
git tag -a v0.1.0-phase1 -m "Phase 1: Core Infrastructure & Auth"
git push origin v0.1.0-phase1
```

### Tag Format

```
v<major>.<minor>.<patch>-phase<phase-number>
```

| Tag | Phase | Contents |
|-----|:---:|----------|
| `v0.0.1-phase0a` | 0.A | Documentation complete |
| `v0.0.2-phase0b` | 0.B | Tooling setup |
| `v0.1.0-phase1` | 1 | Core infrastructure & auth |
| `v0.2.0-phase2` | 2 | Database layer |
| `v0.3.0-phase3` | 3 | HAL & radio |
| `v0.4.0-phase4` | 4 | Messaging |
| `v0.5.0-phase5` | 5 | WebSocket gateway |
| `v0.6.0-phase6` | 6 | Attachments & geolocation |
| `v0.7.0-phase7` | 7 | System management |
| `v0.8.0-phase8` | 8 | Security hardening |
| `v0.9.0-phase9` | 9 | Testing & deployment |
| `v1.0.0` | Final | Production release |

---

## 6. Code Review Checklist

Reviewers verify the following before approving a PR:

### General

- [ ] All tasks in the checklist are complete (checked in PR body)
- [ ] Code follows project structure conventions (`src/api/v1/`, `src/auth/`, `src/db/`)
- [ ] No commented-out code or `console.log` statements
- [ ] Types are explicit — no `any` without justification

### Architecture

- [ ] Repository pattern used for data access (no raw queries in controllers)
- [ ] Business logic lives in services, not route handlers
- [ ] Dependencies injected via constructor (no singletons or global state)
- [ ] `DatabaseAdapter` interface used (no direct SQLite coupling)

### Security

- [ ] All SQL queries use Drizzle parameterized queries (no raw SQL with interpolation)
- [ ] All request bodies validated via JSON Schema / AJV with `maxLength` constraints
- [ ] CLI commands use `execFile` with argument arrays (no shell interpolation)
- [ ] RBAC guard applies to all protected routes
- [ ] Password never logged or included in error messages

### Testing

- [ ] Unit tests cover all new modules (≥80% coverage)
- [ ] Integration tests cover all new API endpoints
- [ ] Test descriptions follow `it("should ...")` pattern
- [ ] Tests pass against in-memory SQLite (`:memory:`)

### Internationalization

- [ ] All user-facing error messages use `t()` function
- [ ] Translation keys present in all 3 locale files (`en`, `es`, `pt-BR`)
- [ ] `npm run i18n:check` passes (all locales have same keys)

---

## 7. CI/CD Integration

### 7.1 GitHub Actions Workflow (Per PR)

Triggered on every PR against `main`:

```yaml
name: PR Validation

on:
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
      - run: npm ci
      - run: npm run lint        # ESLint + Prettier
      - run: npm run build       # TypeScript compilation
      - run: npm test            # Unit + integration tests
      - run: npm run i18n:check  # Locale key validation (post-Phase 1)
```

### 7.2 Quality Gate Status

| Check | Phase | Requirement |
|-------|:---:|-------------|
| `npm run lint` | All | Zero errors, zero warnings |
| `npm run build` | All | Zero TypeScript errors |
| `npm test` | All | All tests pass |
| `npm run i18n:check` | 1+ | All locales have same keys |
| Test coverage ≥80% | 2+ | On new modules |
| Performance benchmark | 3, 4 | Telemetry < 200ms, conversation list < 50ms |

---

## 8. Common Scenarios

### 8.1 Starting a New Phase

```bash
# 1. Ensure main is up to date
git checkout main
git pull origin main

# 2. Create the new phase branch
git checkout -b feat/phase-2-database

# 3. Work on the phase
git add .
git commit -m "feat(db): add conversations table and repository"

# 4. Push and open PR
git push -u origin feat/phase-2-database
```

### 8.2 Updating a Phase Branch with Latest Main

```bash
git checkout feat/phase-2-database
git fetch origin main
git rebase origin/main

# Resolve conflicts if any, then:
git push --force-with-lease
```

**Prefer rebase over merge** to keep the phase branch history linear before the squash merge.

### 8.3 Hotfix (Between Phases)

If a bug is found in `main` between phases:

```bash
git checkout main
git checkout -b fix/jwt-clock-skew
# ... fix the bug ...
git push -u origin fix/jwt-clock-skew
# Open PR: fix/jwt-clock-skew → main
# After merge:
git tag -a v0.1.1-phase1 -m "Hotfix: JWT clock skew tolerance"
```

Hotfix branches use `fix/` prefix and follow the same PR workflow.

### 8.4 Reverting a Merged Phase

If a phase merge causes issues in production:

```bash
git revert <squash-commit-hash>
git push origin main
git tag -a v0.1.0-reverted -m "Revert Phase 1 due to X"
```

The reverted phase gets its own fix branch and a new PR.

---

## 9. Full Visual Flow

```
                         main
                          │
    Phase 0.A (docs) ──── ✅ merge ──── v0.0.1-phase0a
                          │
    Phase 0.B (tools) ─── feat/phase-0b-tooling
                          │
                          ├── commit "chore: init package.json and tsconfig"
                          ├── commit "chore: set up ESLint, Prettier, Vitest"
                          ├── commit "chore: add Drizzle ORM with SQLite adapter"
                          │
                          ✅ PR #1 squash merge ──── v0.0.2-phase0b
                          │
    Phase 1 (auth) ───── feat/phase-1-core-infra
                          │
                          ├── commit "feat(auth): add users table and repository"
                          ├── commit "feat(auth): add bcrypt password hashing"
                          ├── commit "feat(auth): add JWT RS256 sign/verify"
                          ├── commit "feat(auth): add POST /auth/login endpoint"
                          ├── commit "feat(auth): add token refresh with reuse detection"
                          ├── commit "feat(auth): add RBAC middleware"
                          ├── commit "feat(i18n): add locale detector and resource files"
                          ├── commit "test(auth): add integration tests for all endpoints"
                          │
                          ✅ PR #2 squash merge ──── v0.1.0-phase1
                          │
    Phase 2 (db) ─────── feat/phase-2-database
                          │
                          ├── ... (many commits)
                          │
                          ✅ PR #3 squash merge ──── v0.2.0-phase2
                          │
                          ⋮
                          │
    Phase 9 (testing) ── feat/phase-9-testing
                          │
                          ✅ PR #10 squash merge ─── v0.9.0-phase9
                          │
                          ▼
                        v1.0.0 (production release)
```

---

## 10. Summary Checklist Per Phase

| Step | Command / Action |
|------|-----------------|
| 1. Start branch | `git checkout -b feat/phase-N-desc main` |
| 2. Develop | Write code, commit with Conventional Commits format |
| 3. Run quality gate | `npm run lint && npm run build && npm test` |
| 4. Push | `git push -u origin feat/phase-N-desc` |
| 5. Open PR | Use template, fill checklist, request review |
| 6. CI passes | GitHub Actions: lint, build, test, coverage |
| 7. Code review | Address feedback, push updates |
| 8. Squash merge | Squash all commits into one on `main` |
| 9. Delete branch | `git branch -d feat/phase-N-desc` (remote auto-deleted) |
| 10. Tag | `git tag -a v0.N.0-phaseN && git push origin v0.N.0-phaseN` |

---

## Related Documents

- [Development Plan](./plan.md) — Full phased roadmap with tasks and quality gates
- [CI/CD](./ci-cd.md) — Continuous integration and deployment pipeline
- [Setup Guide](./setup.md) — Local development environment setup
- [Testing Guide](./testing.md) — Testing conventions and strategies
- [Contributing Guide](../../CONTRIBUTING.md) — How to contribute to the project