# Arcane deployment (tester-env)

Arcane (getarcaneapp/arcane) is a Docker management platform. This environment
runs it **daemon-free from editable source**: the app boots and serves its
database-backed admin UI, while the Docker inventory surfaces (containers,
images, volumes, networks, projects, dashboard aggregates) report connection
errors by design.

## Why daemon-free

Mounting the host `/var/run/docker.sock` would give the UI — and any tester
agent driving it — control over every container on the shared host, including
protected `alevern/chromium-browser` / `chromium-ls*` verification
infrastructure. A privileged dind sidecar was also ruled out by the operator.
So this environment never mounts a Docker socket, never runs privileged, and
`DOCKER_HOST` points at a socket that does not exist inside the container
(`unix:///app/data/no-docker-daemon.sock`) so the lazy Docker client fails fast
instead of reaching a host daemon.

Scenarios must stay on the DB-backed domain (users, roles, API keys, webhooks,
template registries/templates, global variables, git repositories, container
registries, settings, job schedules/activities, backups records,
notifications).

## Quick start

```bash
./tester-env deploy    # build from source, start, wait for health, set creds
./tester-env seed      # idempotent Northwind Labs fixtures (users, roles, ...)
./tester-env verify    # health + admin login + settings + seeded-state assertions
./tester-env status    # container/volume state, URL, credentials
./tester-env logs      # follow container logs
./tester-env reset     # compose down -v: container + data volume removed
```

All commands accept `--run-id <id>` and `--port <port>` (that is how
`scripts/rl-env` invokes them) and honour `IMAGE_TAG`, `RUN_ID`, `PORT` and
`TESTER_ENV_BROWSER_ORIGIN`.

## Tested ref

- Release tag `v2.17.3`, commit `852aa10fe658b4ed61f8b3e51484236c171c292a`
  (2026-11-04, latest stable release, weekly patch cadence).
- Fork: `https://github.com/sma-rl-dev/arcane`, branch `tester-env-baseline`
  (the tag commit plus the tester-env files in this document's directory).
- Submodule: `apps/arcane` in the training corpus, pinned to the
  `tester-env-baseline` commit recorded in `status/apps/arcane.toml`.

## Deterministic credentials

| Stage | Username | Password |
|---|---|---|
| Upstream first boot (raw container) | `arcane` | `arcane-admin` (forces a change) |
| After `./tester-env deploy` | `arcane` | `Tester-env-Password-123` |
| After `./tester-env seed` | `mara.chen`, `dylan.ortiz`, `priya.raman`, `tobias.fenn`, `sana.okafor` | `Tester-env-Password-123` |

`deploy` clears the forced first-login password change using the static admin
API key, so the browser never hits the first-login dialog. Override with
`ARCANE_FINAL_ADMIN_PASSWORD`.

`ADMIN_STATIC_API_KEY` (default `arc_testerenvstaticadminkey0000000000`, must
start with `arc_`) is reconciled onto the default admin at every boot and is
sent as `X-API-Key`. It is used by `deploy`/`seed`/`verify` so routine setup does
not consume the `/api/auth/login` rate limit (5 requests/minute/burst 5 per IP).
`verify` still performs two real password logins: the admin and one seeded
Viewer whose role is then proven to be enforced.

## Fixed environment

| Variable | Value | Why |
|---|---|---|
| `ENCRYPTION_KEY` | `3JDIgolks2tJ9ymm1AdqzlYMWu0DUWyt` | 32-char fixed key (upstream e2e value); secrets must not be generated |
| `JWT_SECRET` | `tester-env-arcane-jwt-secret-fixed-value-0001` | fixed signing key |
| `ADMIN_STATIC_API_KEY` | `arc_testerenvstaticadminkey0000000000` | deterministic admin API access |
| `TZ` | `UTC` | stable cron/UI timestamps |
| `PUID` / `PGID` | `65532` | app re-execs as 65532; volume owned 65532 |
| `UPDATE_CHECK_DISABLED` | `true` | no GitHub update checks |
| `ANALYTICS_DISABLED` | `true` | no telemetry |
| `DATABASE_URL` | SQLite `file:data/arcane.db` (WAL) | only state besides volumes |
| `PROJECTS_DIRECTORY` / `TEMPLATES_DIRECTORY` | `/app/data/projects` / `/app/data/templates` | inside the data volume, not host paths |

`deploy` also writes two settings rows: `pollingEnabled=false` (hourly image
polling) and `autoUpdate=false`.

## Ports and volumes

- Host port `3552` → container `3552` (`PORT` overrides).
- Named volume `arcane-data<RUN_ID suffix>` → `/app/data`: SQLite DB, projects,
  templates, git workdir, docker config dir. No bind mounts, no host paths.
- Container starts as root only to chown the volume and re-exec; `docker top`
  shows the running server as uid `65532`.

## Build

`docker/Dockerfile.tester-env` is upstream's `docker/Dockerfile` with:

- all three bases pinned by digest (resolved 2026-11-14) instead of mutable
  tags:
  - `ghcr.io/voidzero-dev/vite-plus@sha256:eefe84f6…faaa7acc` (was `:latest`)
  - `golang:1.27-trixie@sha256:c47c3fda…c64c39f`
  - `ghcr.io/getarcaneapp/base@sha256:f723de0b…e6bdaf01` (was `:distroless`)
- `-buildvcs=false` added to `go build` (on top of upstream `-trimpath`).

The frontend (SvelteKit via `vp`) is built first and embedded into the single
Go binary; the runtime stage is the distroless base. Upstream's BuildKit cache
mounts (pnpm store, Go module cache, Go build cache) are preserved.

Measured on this host (28 cores):

- Cold build with empty caches: ~6–7 min (Go `mod download` 150 s, frontend
  build 67 s, `go build` 67 s, pnpm install ~47 s, plus image pulls).
- One-file Go source change (what a mutant usually is): **13 s** end-to-end,
  of which ~5.5 s is the recompiled Go build+link.
- Fully cached `reset` + `deploy` + `verify`: ~5 s to healthy, ~10 s total.

`BUILD_TAGS` is empty. Upstream's `playwright` build tag (test-only seed
endpoints) exists and can be enabled via the build arg, but is not enabled
here so the deployed surface is the normal one.

## Oracle map (daemon-free probe, 2026-11-14)

Verified 200 with the admin API key: `/api/users`, `/api/roles`,
`/api/roles/available-permissions`, `/api/api-keys`, `/api/templates`,
`/api/templates/all`, `/api/variables`, `/api/environments/0/webhooks`,
`/api/container-registries`, `/api/customize/git-repositories`,
`/api/environments/0/settings`, `/api/environments/0/job-schedules`,
`/api/environments/0/activities`, `/api/backups`, `/api/events/stats`,
`/api/app-version`.

Expected failures without a daemon: `/api/environments/0/dashboard` → 500, and
the containers/images/volumes/networks/projects/swarm surfaces.

## Seed data (deterministic baseline)

```bash
./tester-env reset     # drop container + data volume
./tester-env deploy    # rebuild/start, set admin password, disable polling
./tester-env seed      # idempotent Northwind Labs fixtures (API calls only)
./tester-env verify    # bootstrap checks + full seeded-state assertions
```

`seed` runs `scripts/tester-env-seed.py` against the app's own admin API with the
static admin key (no browser, no SQL, no network egress). `verify` runs the
bootstrap checks in bash and then `scripts/tester-env-verify.py`.

**Theme:** Northwind Labs, a five-person platform team running its own compose
stacks. Everything lives in the DB-backed admin domain, because the deployment
has no Docker daemon.

| Entity | Count | Stable names / values |
|---|---|---|
| Users | 6 (1 admin + 5) | `arcane` (Admin), `mara.chen` (Editor), `dylan.ortiz` (Deployer), `priya.raman` (Viewer), `tobias.fenn` (Monitor), `sana.okafor` (custom Release Manager) |
| Custom roles | 2 of 8 roles | `Release Manager` (25 permissions, 1 assigned user), `Incident Responder` (13 permissions, 0 users) |
| API keys | 4 (1 deploy-managed) | `Static Admin API Key` (baseline), `CI Pipeline Runner` (expires 2027-06-30), `Grafana Metrics Exporter`, `Nightly Backup Robot` (expired 2026-09-01) |
| Compose templates | 3 | `PostgreSQL 16 with Adminer`, `Redis 7 Cache`, `Nginx Reverse Proxy` |
| Global variables | 4 | `TZ=UTC`, `LOG_LEVEL=info`, `PLATFORM_DOMAIN=northwind-labs.example`, `POSTGRES_SUPERUSER_PASSWORD` (secret, masked) |
| Container registries | 3 | `ghcr.io` (enabled), `docker.io` (enabled), `harbor.northwind-labs.internal` (disabled, insecure) |
| Git repositories | 3 | `platform-compose` (enabled), `checkout-api` (http auth + token, enabled), `legacy-scripts` (disabled) |
| Webhooks (env 0) | 3 | `Weekly Image Update Run` and `Hotfix Update Check` (Enabled), `Legacy Nightly Update Trigger` (Disabled) — target updater / action run |
| Notification channels | 2 | `Email` enabled (`smtp.northwind-labs.internal`, from `arcane@northwind-labs.internal`), `Discord` disabled |
| Events | 7 seed events | 3 × `Git repository created`, 3 × `Webhook created: …`, 1 × `Webhook updated: Legacy Nightly Update Trigger` |

**Seed credentials.** Every seeded human account uses `Tester-env-Password-123`
(strong policy requires ≥ 12 characters). Admin stays `arcane`.

**Determinism.** Two clean `reset → deploy → seed → verify` cycles produced
identical state snapshots (names, counts, flags, scopes, roles, permissions), and
a second `seed` on the same volume reports every record as unchanged (0 created,
28 unchanged). `verify` fails on an unseeded volume, so the data really is
required rather than assumed.

**What is intentionally not deterministic** (do not assert on it):

- Server-generated UUIDs for users, roles, API keys, templates, variables,
  registries, repositories and webhooks change on every reset.
- `createdAt` / `updatedAt` / `Last Used` timestamps are stamped at seed time.
- API key values and prefixes are random per create (`arc_…`, shown once).
- `user.login` events accumulate as people log in; the seeded event types stay
  fixed, the Events total grows.

**Login budget.** `/api/auth/login` is limited to 5/minute. `verify` uses 2
(admin + one seeded Viewer), so keep extra browser logins to ≤ 3 per minute.

**Scenario packing.** When scenarios are authored, their `scenario.meta.json`
`deploy.copy_paths` must list `docker/Dockerfile.tester-env`,
`scripts/tester-env-seed.py` and `scripts/tester-env-verify.py`;
`tester-env` and `docker-compose.tester-env.yml` are included automatically by
`scripts/rl-env`. `rl-env start` runs `reset → deploy → seed` itself, so a
scenario worktree is seeded without extra steps.

**Browser-visible assertions (for browser-checker).** Credentials
`arcane / Tester-env-Password-123`, origin `http://host.docker.internal:3552/`.
Navigate via Settings > Users / Roles / API Keys / Webhooks / Notifications,
Customization > Templates / Container Registries / Variables / Git Repositories,
and the Event Log entry. Routes:

| Page | Expected visible state |
|---|---|
| `/settings/users` | 6 rows: arcane, dylan.ortiz, mara.chen, priya.raman, sana.okafor, tobias.fenn with role badges Admin / Deployer / Editor / Viewer / Release Manager / Monitor |
| `/settings/roles` | 8 rows; `Release Manager` and `Incident Responder` show the blue **Custom** badge with `1 user(s)` and `0 user(s)`, permissions 25 and 13 |
| `/settings/api-keys` | 4 rows; `Nightly Backup Robot` shows a 2026-09-01 `Expires` date and the red **Expired** badge; the other three show **Active** (Static Admin API Key shows `Never`). Date formatting is locale-dependent — assert the badge, not the string. |
| `/settings/webhooks` | 3 rows; `Weekly Image Update Run` and `Hotfix Update Check` **Enabled**, `Legacy Nightly Update Trigger` **Disabled**, Target `Environment updater` |
| `/settings/notifications` | Email tab: switch on, SMTP Host `smtp.northwind-labs.internal`, port 587, from `arcane@northwind-labs.internal`, two recipients; Discord tab switch off |
| `/customize/templates` | 3 cards named `PostgreSQL 16 with Adminer`, `Redis 7 Cache`, `Nginx Reverse Proxy`, each labelled `Local Templates` |
| `/customize/variables` | 4 rows; `POSTGRES_SUPERUSER_PASSWORD` has the amber **Secret** badge and a masked value; every scope reads `All Environments` |
| `/customize/registries` | 3 rows: `ghcr.io` and `docker.io` **Enabled**, `harbor.northwind-labs.internal` **Disabled** |
| `/customize/git-repositories` | 3 rows: `platform-compose` and `checkout-api` **Enabled**, `legacy-scripts` **Disabled** |
| `/events` | Populated list including `Git repository created` and `Webhook updated: Legacy Nightly Update Trigger` with success severity |

The dashboard still errors (it aggregates Docker daemon state), so start browser
verification from `/settings/users`.

## Caveats

- The Docker event stream retries forever and logs a warning every few seconds
  (`failed to connect to Docker event stream … no-docker-daemon.sock`). This is
  the intended daemon-free behaviour, not a failed boot; it backs off over time.
- The runtime image is distroless: there is no shell, so `docker exec … sh`
  fails. Use `docker logs` or `--entrypoint`.
- `/api/auth/login` is rate limited (5/min, burst 5, per IP). `verify` uses 2
  logins (admin + one seeded Viewer), so keep extra browser logins to ≤ 3 per
  minute; do not add CLI logins in a loop.
- Backups: DB rows work, but S3 sync needs minio (not started here).
- The SPA shell is served for every route and renders client-side; static assets
  under `/_app/immutable/*` and `/app.webmanifest` serve correctly.

## Reset

```bash
./tester-env reset   # docker compose -p … down -v + fallback volume removal
./tester-env deploy  # fresh SQLite DB, default admin, same documented creds
```

The image is intentionally preserved (`docker images` may be shared with other
in-flight runs); reclaim with `scripts/rl-env gc --prune-images`.
