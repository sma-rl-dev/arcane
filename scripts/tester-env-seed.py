#!/usr/bin/env python3
"""Deterministic seed data for the Arcane tester-env deployment.

The deployment is daemon-free, so only the database-backed admin domain is
seeded: users, custom roles and role assignments, scoped API keys, compose
templates, global variables, container registries, git repositories, updater
webhooks and notification channels.

Data theme: "Northwind Labs", a small platform team that runs its own compose
stacks. Names, emails, URLs and tokens are fixed fixtures; nothing here talks to
the network and no record is random.

Idempotent: every record is looked up by its natural name/username/key and only
created when missing (webhook/registry enabled flags and role assignments are
reconciled to the expected state). The script never deletes seeded rows, so a
second run after the first must report "unchanged" for everything.

Usage (normally invoked by ./tester-env seed):
    python3 scripts/tester-env-seed.py

Environment:
    TESTER_ENV_LOCAL_URL       base URL, default http://127.0.0.1:3552
    ADMIN_STATIC_API_KEY       admin API key, default the documented fixed key
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("TESTER_ENV_LOCAL_URL", "http://127.0.0.1:3552").rstrip("/")
API_KEY = os.environ.get("ADMIN_STATIC_API_KEY", "arc_testerenvstaticadminkey0000000000")

# Fixed password for every seeded human account (strong policy: >= 12 chars).
# `./tester-env` passes the deployment's admin password here, so overriding
# ARCANE_FINAL_ADMIN_PASSWORD keeps seeded accounts consistent.
USER_PASSWORD = os.environ.get("TESTER_ENV_SEED_PASSWORD", "Tester-env-Password-123")

ROLE_RELEASE_MANAGER = "Release Manager"
ROLE_INCIDENT_RESPONDER = "Incident Responder"

# Permission resources that are granted per environment rather than globally.
ENV_SCOPED_PREFIXES = (
    "containers:",
    "projects:",
    "images:",
    "volumes:",
    "networks:",
    "swarm:",
    "podman:",
    "gitops:",
    "webhooks:",
    "jobs:",
    "dashboard:",
    "system:",
    "image-updates:",
    "vulnerabilities:",
    "build-workspaces:",
    "activities:",
)


def api_key_grant(permission: str) -> dict:
    """API key grants are objects; environment-scoped permissions need the env id."""
    if permission.startswith(ENV_SCOPED_PREFIXES):
        return {"permission": permission, "environmentId": "0"}
    return {"permission": permission}


def log(message: str) -> None:
    print(f"    {message}")


def api(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(BASE_URL + path, data=data, method=method)
    request.add_header("X-API-Key", API_KEY)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode(errors="replace")
        return error.code, payload


def must(method: str, path: str, body: dict | None = None) -> object:
    status, payload = api(method, path, body)
    if status >= 300:
        raise SystemExit(f"seed: {method} {path} failed with HTTP {status}: {json.dumps(payload)[:800]}")
    return payload


def data_of(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        return payload.get("data") or []
    if isinstance(payload, list):
        return payload
    return []


# --------------------------------------------------------------------------
# Fixed fixtures
# --------------------------------------------------------------------------

USERS = [
    {
        "username": "mara.chen",
        "displayName": "Mara Chen",
        "email": "mara.chen@northwind-labs.example",
        "role": "Editor",
    },
    {
        "username": "dylan.ortiz",
        "displayName": "Dylan Ortiz",
        "email": "dylan.ortiz@northwind-labs.example",
        "role": "Deployer",
    },
    {
        "username": "priya.raman",
        "displayName": "Priya Raman",
        "email": "priya.raman@northwind-labs.example",
        "role": "Viewer",
    },
    {
        "username": "tobias.fenn",
        "displayName": "Tobias Fenn",
        "email": "tobias.fenn@northwind-labs.example",
        "role": "Monitor",
    },
    {
        "username": "sana.okafor",
        "displayName": "Sana Okafor",
        "email": "sana.okafor@northwind-labs.example",
        "role": ROLE_RELEASE_MANAGER,
    },
]

ROLES = [
    {
        "name": ROLE_RELEASE_MANAGER,
        "description": "Deploys and rolls back production compose projects; cannot manage users or global settings.",
        "permissions": [
            "settings:read",
            "environments:list",
            "environments:read",
            "projects:list",
            "projects:read",
            "projects:logs",
            "projects:deploy",
            "projects:down",
            "projects:restart",
            "projects:update",
            "images:list",
            "images:read",
            "images:pull",
            "images:tag",
            "containers:list",
            "containers:read",
            "containers:logs",
            "gitops:list",
            "gitops:read",
            "gitops:sync",
            "gitops:lifecycle",
            "webhooks:list",
            "activities:read",
            "events:read",
            "dashboard:read",
        ],
    },
    {
        "name": ROLE_INCIDENT_RESPONDER,
        "description": "Restarts degraded containers and reads logs during incidents. Not yet assigned to the on-call rotation.",
        "permissions": [
            "settings:read",
            "environments:list",
            "environments:read",
            "containers:list",
            "containers:read",
            "containers:logs",
            "containers:restart",
            "projects:list",
            "projects:read",
            "projects:logs",
            "activities:read",
            "events:read",
            "dashboard:read",
        ],
    },
]

API_KEYS = [
    {
        "name": "CI Pipeline Runner",
        "description": "GitHub Actions deploy pipeline; redeploys the checkout-api stack on every release tag.",
        "expiresAt": "2027-06-30T00:00:00Z",
        "permissions": [
            "settings:read",
            "environments:list",
            "environments:read",
            "projects:list",
            "projects:read",
            "projects:logs",
            "projects:deploy",
            "projects:down",
            "images:list",
            "images:read",
        ],
    },
    {
        "name": "Grafana Metrics Exporter",
        "description": "Read-only inventory access for the Grafana infrastructure dashboards.",
        "permissions": [
            "settings:read",
            "environments:list",
            "environments:read",
            "containers:list",
            "containers:read",
            "images:list",
            "images:read",
            "volumes:list",
            "volumes:read",
            "networks:list",
            "networks:read",
            "dashboard:read",
        ],
    },
    {
        "name": "Nightly Backup Robot",
        "description": "Expired after the Q3 storage migration; kept for audit until the next credential review.",
        "expiresAt": "2026-09-01T00:00:00Z",
        "permissions": [
            "settings:read",
            "system-backups:read",
            "system-backups:manage",
            "s3-destinations:list",
            "s3-destinations:read",
        ],
    },
]

TEMPLATES = [
    {
        "name": "PostgreSQL 16 with Adminer",
        "description": "Postgres 16 database plus the Adminer web console on port 8080, backed by a named volume.",
        "content": (
            "services:\n"
            "  postgres:\n"
            "    image: postgres:16-alpine\n"
            "    container_name: northwind-postgres\n"
            "    restart: unless-stopped\n"
            "    environment:\n"
            "      POSTGRES_DB: ${POSTGRES_DB}\n"
            "      POSTGRES_USER: ${POSTGRES_USER}\n"
            "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}\n"
            "    volumes:\n"
            "      - postgres-data:/var/lib/postgresql/data\n"
            "    ports:\n"
            "      - '5432:5432'\n"
            "  adminer:\n"
            "    image: adminer:4\n"
            "    container_name: northwind-adminer\n"
            "    restart: unless-stopped\n"
            "    depends_on:\n"
            "      - postgres\n"
            "    ports:\n"
            "      - '8080:8080'\n"
            "volumes:\n"
            "  postgres-data:\n"
        ),
        "envContent": (
            "POSTGRES_DB=northwind\n"
            "POSTGRES_USER=northwind\n"
            "POSTGRES_PASSWORD=change-me-before-deploy\n"
        ),
    },
    {
        "name": "Redis 7 Cache",
        "description": "Single-node Redis 7 cache with append-only persistence for the session and queue workloads.",
        "content": (
            "services:\n"
            "  redis:\n"
            "    image: redis:7-alpine\n"
            "    container_name: northwind-redis\n"
            "    restart: unless-stopped\n"
            "    command: ['redis-server', '--appendonly', 'yes']\n"
            "    volumes:\n"
            "      - redis-data:/data\n"
            "    ports:\n"
            "      - '6379:6379'\n"
            "volumes:\n"
            "  redis-data:\n"
        ),
        "envContent": "REDIS_MAXMEMORY=512mb\n",
    },
    {
        "name": "Nginx Reverse Proxy",
        "description": "TLS-terminating Nginx proxy that fronts the compose projects on the platform network.",
        "content": (
            "services:\n"
            "  proxy:\n"
            "    image: nginx:1.27-alpine\n"
            "    container_name: northwind-proxy\n"
            "    restart: unless-stopped\n"
            "    volumes:\n"
            "      - ./nginx.conf:/etc/nginx/nginx.conf:ro\n"
            "      - ./certs:/etc/nginx/certs:ro\n"
            "    ports:\n"
            "      - '80:80'\n"
            "      - '443:443'\n"
            "    networks:\n"
            "      - platform\n"
            "networks:\n"
            "  platform:\n"
            "    name: northwind-platform\n"
        ),
        "envContent": "PLATFORM_DOMAIN=northwind-labs.example\n",
    },
]

VARIABLES = [
    {"key": "TZ", "value": "UTC", "isSecret": False},
    {"key": "LOG_LEVEL", "value": "info", "isSecret": False},
    {"key": "PLATFORM_DOMAIN", "value": "northwind-labs.example", "isSecret": False},
    {"key": "POSTGRES_SUPERUSER_PASSWORD", "value": "seeded-not-a-real-credential", "isSecret": True},
]

REGISTRIES = [
    {
        "url": "ghcr.io",
        "username": "northwind-labs-bot",
        "token": "ghp_seeded_readonly_ghcr_token",
        "description": "GitHub Container Registry mirror for internal base images",
        "insecure": False,
        "enabled": True,
        "registryType": "generic",
        "repositoryNames": ["northwind-labs/base-images"],
        "awsAccessKeyId": "",
        "awsSecretAccessKey": "",
        "awsRegion": "",
    },
    {
        "url": "docker.io",
        "username": "northwindlabs",
        "token": "dckr_seeded_pull_token",
        "description": "Docker Hub account that raises the pull rate limit for public base images",
        "insecure": False,
        "enabled": True,
        "registryType": "generic",
        "repositoryNames": [],
        "awsAccessKeyId": "",
        "awsSecretAccessKey": "",
        "awsRegion": "",
    },
    {
        "url": "harbor.northwind-labs.internal",
        "username": "svc-arcane",
        "token": "harbor_seeded_robot_token",
        "description": "On-prem Harbor mirror, disabled while the datacenter move is in progress",
        "insecure": True,
        "enabled": False,
        "registryType": "generic",
        "repositoryNames": [],
        "awsAccessKeyId": "",
        "awsSecretAccessKey": "",
        "awsRegion": "",
    },
]

GIT_REPOSITORIES = [
    {
        "name": "platform-compose",
        "url": "https://github.com/northwind-labs/platform-compose.git",
        "authType": "none",
        "description": "Shared compose stacks for the platform team",
        "enabled": True,
    },
    {
        "name": "checkout-api",
        "url": "https://github.com/northwind-labs/checkout-api.git",
        "authType": "http",
        "username": "northwind-deploy-bot",
        "token": "ghp_seeded_deploy_token",
        "description": "Checkout API stack deployed by the release pipeline",
        "enabled": True,
        "commitAuthorName": "Dylan Ortiz",
        "commitAuthorEmail": "dylan.ortiz@northwind-labs.example",
    },
    {
        "name": "legacy-scripts",
        "url": "https://gitlab.com/northwind-labs/legacy-scripts.git",
        "authType": "none",
        "description": "Archived maintenance scripts from the 2024 migration",
        "enabled": False,
    },
]

WEBHOOKS = [
    {"name": "Weekly Image Update Run", "targetType": "updater", "actionType": "run", "targetId": "", "enabled": True},
    {"name": "Hotfix Update Check", "targetType": "updater", "actionType": "run", "targetId": "", "enabled": True},
    {"name": "Legacy Nightly Update Trigger", "targetType": "updater", "actionType": "run", "targetId": "", "enabled": False},
]

NOTIFICATIONS = [
    {
        "provider": "email",
        "enabled": True,
        "config": {
            "smtpHost": "smtp.northwind-labs.internal",
            "smtpPort": 587,
            "smtpUsername": "arcane-notifications",
            "smtpPassword": "seeded-smtp-password",
            "fromAddress": "arcane@northwind-labs.internal",
            "toAddresses": [
                "platform-oncall@northwind-labs.internal",
                "dylan.ortiz@northwind-labs.internal",
            ],
            "tlsMode": "starttls",
            "authMode": "auto",
            "events": {
                "image_update": False,
                "container_update": True,
                "vulnerability_found": False,
                "prune_report": False,
                "auto_heal": True,
            },
        },
    },
    {
        "provider": "discord",
        "enabled": False,
        "config": {
            "webhookId": "1098765432109876543",
            "token": "seeded-discord-webhook-token",
            "username": "Arcane",
            "events": {
                "image_update": True,
                "container_update": True,
                "vulnerability_found": True,
                "prune_report": False,
                "auto_heal": True,
            },
        },
    },
]


# --------------------------------------------------------------------------
# Seed steps
# --------------------------------------------------------------------------


def seed_roles() -> None:
    existing = {role["name"]: role for role in data_of(must("GET", "/api/roles"))}
    for spec in ROLES:
        current = existing.get(spec["name"])
        if current:
            log(f"role unchanged: {spec['name']}")
            continue
        must("POST", "/api/roles", spec)
        log(f"role created: {spec['name']}")


def role_id_by_name() -> dict[str, str]:
    return {role["name"]: role["id"] for role in data_of(must("GET", "/api/roles"))}


def seed_users() -> None:
    roles = role_id_by_name()
    existing = {user["username"]: user for user in data_of(must("GET", "/api/users?limit=200"))}
    for spec in USERS:
        username = spec["username"]
        current = existing.get(username)
        if current is None:
            must(
                "POST",
                "/api/users",
                {
                    "username": username,
                    "password": USER_PASSWORD,
                    "displayName": spec["displayName"],
                    "email": spec["email"],
                    "locale": "en",
                },
            )
            log(f"user created: {username}")
            current = next(
                user
                for user in data_of(must("GET", "/api/users?limit=200"))
                if user["username"] == username
            )
        else:
            log(f"user unchanged: {username}")

        expected_role = roles.get(spec["role"])
        if expected_role is None:
            raise SystemExit(f"seed: role {spec['role']!r} is missing for user {username}")
        assignments = current.get("roleAssignments") or []
        if any(a.get("roleId") == expected_role and not a.get("environmentId") for a in assignments):
            continue
        must(
            "PUT",
            f"/api/users/{current['id']}/role-assignments",
            {"assignments": [{"roleId": expected_role}]},
        )
        log(f"role assignment set: {username} -> {spec['role']}")


def seed_api_keys() -> None:
    existing = {item["name"] for item in data_of(must("GET", "/api/api-keys?limit=200"))}
    for spec in API_KEYS:
        if spec["name"] in existing:
            log(f"api key unchanged: {spec['name']}")
            continue
        body = dict(spec)
        body["permissions"] = [api_key_grant(perm) for perm in spec["permissions"]]
        must("POST", "/api/api-keys", body)
        log(f"api key created: {spec['name']}")


def seed_templates() -> None:
    existing = {item["name"] for item in data_of(must("GET", "/api/templates/all"))}
    for spec in TEMPLATES:
        if spec["name"] in existing:
            log(f"template unchanged: {spec['name']}")
            continue
        must("POST", "/api/templates", spec)
        log(f"template created: {spec['name']}")


def seed_variables() -> None:
    existing = {item["key"] for item in data_of(must("GET", "/api/variables"))}
    for spec in VARIABLES:
        if spec["key"] in existing:
            log(f"variable unchanged: {spec['key']}")
            continue
        body = dict(spec)
        body["allEnvironments"] = True
        must("POST", "/api/variables", body)
        log(f"variable created: {spec['key']}")


def seed_registries() -> None:
    existing = {item["url"]: item for item in data_of(must("GET", "/api/container-registries?limit=200"))}
    for spec in REGISTRIES:
        current = existing.get(spec["url"])
        if current is None:
            must("POST", "/api/container-registries", spec)
            log(f"registry created: {spec['url']}")
            continue
        if current.get("enabled") == spec["enabled"]:
            log(f"registry unchanged: {spec['url']}")
            continue
        must("PUT", f"/api/container-registries/{current['id']}", {"enabled": spec["enabled"]})
        log(f"registry enabled={str(spec['enabled']).lower()}: {spec['url']}")


def seed_git_repositories() -> None:
    existing = {item["name"]: item for item in data_of(must("GET", "/api/customize/git-repositories?limit=200"))}
    for spec in GIT_REPOSITORIES:
        current = existing.get(spec["name"])
        if current is None:
            must("POST", "/api/customize/git-repositories", spec)
            log(f"git repository created: {spec['name']}")
            continue
        if current.get("enabled") == spec["enabled"]:
            log(f"git repository unchanged: {spec['name']}")
            continue
        must("PUT", f"/api/customize/git-repositories/{current['id']}", {"enabled": spec["enabled"]})
        log(f"git repository enabled={str(spec['enabled']).lower()}: {spec['name']}")


def seed_webhooks() -> None:
    existing = {item["name"]: item for item in data_of(must("GET", "/api/environments/0/webhooks"))}
    for spec in WEBHOOKS:
        current = existing.get(spec["name"])
        if current is None:
            must(
                "POST",
                "/api/environments/0/webhooks",
                {
                    "name": spec["name"],
                    "targetType": spec["targetType"],
                    "actionType": spec["actionType"],
                    "targetId": spec["targetId"],
                },
            )
            log(f"webhook created: {spec['name']}")
            current = next(
                item
                for item in data_of(must("GET", "/api/environments/0/webhooks"))
                if item["name"] == spec["name"]
            )
        elif current.get("enabled") == spec["enabled"]:
            log(f"webhook unchanged: {spec['name']}")
            continue
        if current.get("enabled") == spec["enabled"]:
            continue
        must("PATCH", f"/api/environments/0/webhooks/{current['id']}", {"enabled": spec["enabled"]})
        log(f"webhook enabled={str(spec['enabled']).lower()}: {spec['name']}")


def seed_notifications() -> None:
    existing = {item["provider"]: item for item in data_of(must("GET", "/api/environments/0/notifications/settings"))}
    for spec in NOTIFICATIONS:
        current = existing.get(spec["provider"])
        if current and current.get("enabled") == spec["enabled"]:
            log(f"notification channel unchanged: {spec['provider']}")
            continue
        must("POST", "/api/environments/0/notifications/settings", spec)
        log(f"notification channel configured: {spec['provider']} enabled={str(spec['enabled']).lower()}")


def main() -> int:
    status, _ = api("GET", "/api/health")
    if status != 200:
        print(f"seed: app is not healthy at {BASE_URL}/api/health (HTTP {status})", file=sys.stderr)
        return 1
    print(f"==> seeding Arcane at {BASE_URL}")
    seed_roles()
    seed_users()
    seed_api_keys()
    seed_templates()
    seed_variables()
    seed_registries()
    seed_git_repositories()
    seed_webhooks()
    seed_notifications()
    print("==> seed complete (idempotent: rerun to confirm no changes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
