#!/usr/bin/env python3
"""Verify the deterministic Arcane baseline and its seeded data.

Checks the daemon-free DB-backed domain that ./tester-env seed populates:
users and role assignments, custom roles, scoped API keys, compose templates,
global variables, container registries, git repositories, updater webhooks and
notification channels. Also proves that a seeded non-admin account can log in
and that its role is enforced (Viewer cannot list users).

Usage (invoked at the end of ./tester-env verify):
    python3 scripts/tester-env-verify.py

Environment:
    TESTER_ENV_LOCAL_URL       base URL, default http://127.0.0.1:3552
    ADMIN_STATIC_API_KEY       admin API key, default the documented fixed key
    TESTER_ENV_SEED_PASSWORD   seeded user password, default Tester-env-Password-123
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("TESTER_ENV_LOCAL_URL", "http://127.0.0.1:3552").rstrip("/")
API_KEY = os.environ.get("ADMIN_STATIC_API_KEY", "arc_testerenvstaticadminkey0000000000")
SEED_PASSWORD = os.environ.get("TESTER_ENV_SEED_PASSWORD", "Tester-env-Password-123")
VIEWER_USER = "priya.raman"

failures: list[str] = []


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(BASE_URL + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
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


def admin(method: str, path: str, body: dict | None = None):
    return call(method, path, body, {"X-API-Key": API_KEY})


def data_of(payload) -> list[dict]:
    if isinstance(payload, dict):
        return payload.get("data") or []
    if isinstance(payload, list):
        return payload
    return []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"    ok: {message}")
        return
    failures.append(message)
    print(f"    FAIL: {message}")


def expect_equal(actual, expected, label: str) -> None:
    check(actual == expected, f"{label} == {expected!r} (got {actual!r})")


def expect_set(actual, expected, label: str) -> None:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    check(not missing and not extra, f"{label} == {sorted(expected)!r} (missing={missing}, extra={extra})")


def main() -> int:
    status, _ = admin("GET", "/api/health")
    expect_equal(status, 200, "GET /api/health")

    # Users + role assignments -------------------------------------------------
    status, payload = admin("GET", "/api/users?limit=200")
    users = data_of(payload)
    expect_equal(status, 200, "GET /api/users")
    expect_equal((payload or {}).get("pagination", {}).get("totalItems"), 6, "users totalItems")
    by_username = {user["username"]: user for user in users}
    expect_set(
        by_username,
        {"arcane", "mara.chen", "dylan.ortiz", "priya.raman", "tobias.fenn", "sana.okafor"},
        "user usernames",
    )
    expected_roles = {
        "arcane": "Admin",
        "mara.chen": "Editor",
        "dylan.ortiz": "Deployer",
        "priya.raman": "Viewer",
        "tobias.fenn": "Monitor",
        "sana.okafor": "Release Manager",
    }
    expect_equal((by_username.get("sana.okafor") or {}).get("displayName"), "Sana Okafor", "sana.okafor displayName")
    expect_equal(
        (by_username.get("tobias.fenn") or {}).get("email"),
        "tobias.fenn@northwind-labs.example",
        "tobias.fenn email",
    )

    # Roles -------------------------------------------------------------------
    status, payload = admin("GET", "/api/roles")
    roles = data_of(payload)
    expect_equal(status, 200, "GET /api/roles")
    expect_equal((payload or {}).get("pagination", {}).get("totalItems"), 8, "roles totalItems")
    roles_by_name = {role["name"]: role for role in roles}
    role_ids = {role["name"]: role["id"] for role in roles}
    expect_set(
        roles_by_name,
        {
            "Admin",
            "Deployer",
            "Editor",
            "Monitor",
            "No-Shell Editor",
            "Viewer",
            "Release Manager",
            "Incident Responder",
        },
        "role names",
    )
    release_manager = roles_by_name.get("Release Manager") or {}
    check(release_manager.get("builtIn") is False, "Release Manager is a custom role")
    expect_equal(release_manager.get("assignedUserCount"), 1, "Release Manager assignedUserCount")
    expect_equal(len(release_manager.get("permissions") or []), 25, "Release Manager permission count")
    incident = roles_by_name.get("Incident Responder") or {}
    check(incident.get("builtIn") is False, "Incident Responder is a custom role")
    expect_equal(incident.get("assignedUserCount"), 0, "Incident Responder assignedUserCount")

    for username, role_name in expected_roles.items():
        user = by_username.get(username) or {}
        assigned = {a.get("roleId") for a in user.get("roleAssignments") or [] if not a.get("environmentId")}
        check(role_ids.get(role_name) in assigned, f"user {username} has global role {role_name}")

    # API keys ----------------------------------------------------------------
    status, payload = admin("GET", "/api/api-keys?limit=200")
    keys = data_of(payload)
    expect_equal(status, 200, "GET /api/api-keys")
    expect_equal((payload or {}).get("pagination", {}).get("totalItems"), 4, "api keys totalItems")
    keys_by_name = {key["name"]: key for key in keys}
    expect_set(
        keys_by_name,
        {"Static Admin API Key", "CI Pipeline Runner", "Grafana Metrics Exporter", "Nightly Backup Robot"},
        "api key names",
    )
    expect_equal(
        str((keys_by_name.get("Nightly Backup Robot") or {}).get("expiresAt", ""))[:10],
        "2026-09-01",
        "expired key date",
    )
    check(
        (keys_by_name.get("CI Pipeline Runner") or {}).get("keyPrefix", "").startswith("arc_"),
        "CI Pipeline Runner shows an arc_ key prefix",
    )

    # Templates ---------------------------------------------------------------
    status, payload = admin("GET", "/api/templates/all")
    templates = data_of(payload)
    expect_equal(status, 200, "GET /api/templates/all")
    expect_set(
        {item["name"] for item in templates},
        {"PostgreSQL 16 with Adminer", "Redis 7 Cache", "Nginx Reverse Proxy"},
        "template names",
    )

    # Global variables --------------------------------------------------------
    status, payload = admin("GET", "/api/variables")
    variables = data_of(payload)
    expect_equal(status, 200, "GET /api/variables")
    expect_set(
        {item["key"] for item in variables},
        {"TZ", "LOG_LEVEL", "PLATFORM_DOMAIN", "POSTGRES_SUPERUSER_PASSWORD"},
        "variable keys",
    )
    secret = next((item for item in variables if item["key"] == "POSTGRES_SUPERUSER_PASSWORD"), {})
    check(secret.get("isSecret") is True, "POSTGRES_SUPERUSER_PASSWORD is marked secret")
    expect_equal(secret.get("value"), "", "secret value is never returned by the API")

    # Container registries ----------------------------------------------------
    status, payload = admin("GET", "/api/container-registries?limit=200")
    registries = {item["url"]: item for item in data_of(payload)}
    expect_equal(status, 200, "GET /api/container-registries")
    expect_set(
        registries,
        {"ghcr.io", "docker.io", "harbor.northwind-labs.internal"},
        "registry urls",
    )
    expect_equal(
        set(url for url, item in registries.items() if item.get("enabled")),
        {"ghcr.io", "docker.io"},
        "enabled registry urls",
    )
    expect_equal((registries.get("harbor.northwind-labs.internal") or {}).get("enabled"), False, "harbor registry disabled")
    expect_equal((registries.get("ghcr.io") or {}).get("registryType"), "generic", "ghcr registry type")

    # Git repositories --------------------------------------------------------
    status, payload = admin("GET", "/api/customize/git-repositories?limit=200")
    repos = {item["name"]: item for item in data_of(payload)}
    expect_equal(status, 200, "GET /api/customize/git-repositories")
    expect_set(repos, {"platform-compose", "checkout-api", "legacy-scripts"}, "git repository names")
    expect_equal((repos.get("checkout-api") or {}).get("authType"), "http", "checkout-api authType")
    expect_equal((repos.get("checkout-api") or {}).get("hasToken"), True, "checkout-api stores a token")
    expect_equal((repos.get("legacy-scripts") or {}).get("enabled"), False, "legacy-scripts disabled")

    # Webhooks ----------------------------------------------------------------
    status, payload = admin("GET", "/api/environments/0/webhooks")
    webhooks = {item["name"]: item for item in data_of(payload)}
    expect_equal(status, 200, "GET /api/environments/0/webhooks")
    expect_set(
        webhooks,
        {"Weekly Image Update Run", "Hotfix Update Check", "Legacy Nightly Update Trigger"},
        "webhook names",
    )
    expect_equal(
        set(name for name, item in webhooks.items() if item.get("enabled")),
        {"Weekly Image Update Run", "Hotfix Update Check"},
        "enabled webhook names",
    )

    # Events (written by the seed itself; drives the Events page). Login events
    # add rows, so assert the deterministic seed event types, not the total.
    status, payload = admin("GET", "/api/events?limit=100")
    events = data_of(payload)
    expect_equal(status, 200, "GET /api/events")
    expect_equal(
        sum(1 for event in events if event.get("type") == "git.repository.create"),
        3,
        "git.repository.create event count",
    )
    expect_equal(
        sum(1 for event in events if event.get("type") == "webhook.create"),
        3,
        "webhook.create event count",
    )
    expect_equal(
        sum(1 for event in events if event.get("type") == "webhook.update"),
        1,
        "webhook.update event count",
    )

    # Notification channels ---------------------------------------------------
    status, payload = admin("GET", "/api/environments/0/notifications/settings")
    channels = {item["provider"]: item for item in data_of(payload)}
    expect_equal(status, 200, "GET /api/environments/0/notifications/settings")
    expect_set(channels, {"email", "discord"}, "notification providers")
    expect_equal((channels.get("email") or {}).get("enabled"), True, "email notifications enabled")
    expect_equal((channels.get("discord") or {}).get("enabled"), False, "discord notifications disabled")
    expect_equal(
        ((channels.get("email") or {}).get("config") or {}).get("smtpHost"),
        "smtp.northwind-labs.internal",
        "email smtp host",
    )

    # Seeded credentials and role enforcement ---------------------------------
    status, login = call("POST", "/api/auth/login", {"username": VIEWER_USER, "password": SEED_PASSWORD})
    expect_equal(status, 200, f"seeded user {VIEWER_USER} can log in")
    token = ((login or {}).get("data") or {}).get("token") or ""
    check(bool(token), f"{VIEWER_USER} received an access token")
    if token:
        status, me = call("GET", "/api/auth/me", None, {"Authorization": f"Bearer {token}"})
        expect_equal(status, 200, f"GET /api/auth/me as {VIEWER_USER}")
        expect_equal(((me or {}).get("data") or {}).get("username"), VIEWER_USER, f"identity of {VIEWER_USER}")
        # The Viewer role can list users but cannot create them; this proves the
        # seeded role assignment is actually enforced, not just stored.
        status, _ = call(
            "POST",
            "/api/users",
            {"username": "forbidden.probe", "password": SEED_PASSWORD},
            {"Authorization": f"Bearer {token}"},
        )
        expect_equal(status, 403, "Viewer role cannot create users")

    if failures:
        print(f"==> seed verify FAILED ({len(failures)} check(s))", file=sys.stderr)
        for failure in failures:
            print(f"    - {failure}", file=sys.stderr)
        return 1
    print("==> seed verify OK: baseline users, roles, keys, templates, variables, registries, repos, webhooks, notifications")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
