"""Environment-aware settings loader."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, Type

from fastapi_mail import FastMail

from .settings import Settings


class DevelopmentSettings(Settings):
    """Settings tuned for local development."""

    environment: str = "development"


class ProductionSettings(Settings):
    """Settings tuned for production."""

    environment: str = "production"


class TestSettings(Settings):
    """Settings tuned for automated tests."""

    environment: str = "test"

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        if not self.database_url:
            object.__setattr__(self, "database_url", self.test_database_url)


ENVIRONMENTS: Dict[str, Type[Settings]] = {
    "development": DevelopmentSettings,
    "dev": DevelopmentSettings,
    "production": ProductionSettings,
    "prod": ProductionSettings,
    "test": TestSettings,
    "testing": TestSettings,
}


@lru_cache
def get_settings() -> Settings:
    env = os.getenv("APP_ENV", "production").lower()
    settings_cls = ENVIRONMENTS.get(env, ProductionSettings)
    return settings_cls()


@lru_cache
def get_mail_client() -> FastMail:
    return FastMail(get_settings().mail_config)
