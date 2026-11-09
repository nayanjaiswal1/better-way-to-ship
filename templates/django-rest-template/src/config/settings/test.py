"""Test settings — fast, isolated, no external services."""
from __future__ import annotations

from .base import *  # noqa: F401, F403

SECRET_KEY = "test-secret-key-not-for-production"  # noqa: S105

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable password hashing for speed
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Disable Celery tasks in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
