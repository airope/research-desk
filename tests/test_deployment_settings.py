"""Production configuration must fail before Django or a database starts."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = {
    "APP_ENV": "production",
    "SECRET_KEY": "test-only-production-setting-not-a-secret-0123456789-abcdef",
    "PGPASSWORD": "test-only-database-password",
    "ALLOWED_HOSTS": "research.example.org",
}


def load_settings(extra):
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME"}}
    env.update(extra)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from srr.settings import *; "
            "print(DEBUG, SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE, SECURE_SSL_REDIRECT)",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_development_remains_local_friendly():
    result = load_settings({})
    assert result.returncode == 0
    assert result.stdout.strip() == "True False False False"


def test_production_enables_transport_protections():
    result = load_settings(PRODUCTION)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False True True True"


@pytest.mark.parametrize(
    "key,value",
    [
        ("SECRET_KEY", ""),
        ("SECRET_KEY", "x" * 60),
        ("PGPASSWORD", "srr-local-only"),
        ("ALLOWED_HOSTS", "*"),
        ("ALLOWED_HOSTS", ""),
        ("DEBUG", "1"),
        ("RESEARCH_CODEX_ENABLED", "1"),
        ("APP_ENV", "typo"),
    ],
)
def test_unsafe_production_configuration_fails_closed(key, value):
    assert load_settings({**PRODUCTION, key: value}).returncode != 0


def test_legacy_debug_zero_also_requires_production_secrets():
    assert load_settings({"DEBUG": "0"}).returncode != 0


def test_env_variants_excluded_from_git_and_docker():
    for name in (".gitignore", ".dockerignore"):
        lines = (ROOT / name).read_text().splitlines()
        assert ".env*" in lines
        assert "!.env.example" in lines


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_resource_limits_must_be_positive(value):
    assert load_settings({"RESEARCH_DAILY_JOBS": value}).returncode != 0
