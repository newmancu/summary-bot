import logging

import sys
from functools import cache
from pathlib import Path
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings


LOGGING_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class EnvSettings(BaseSettings):
    """The settings for real sys / docker environment
    it is not for dotenv..."""

    name: str = ".env"
    ignore: bool = False

    @property
    def is_env_path_abs(self):
        return Path(self.name).is_absolute()


class App(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_prefix = "server_"


class Logging(BaseSettings):
    level: Literal[LOGGING_LEVELS] = "DEBUG"  # type: ignore
    level_root: Literal[LOGGING_LEVELS] = "INFO"  # type: ignore

    @property
    def int_root_log_level(self):
        return getattr(logging, "_nameToLevel")[self.level_root]

    @property
    def int_log_level(self):
        return getattr(logging, "_nameToLevel")[self.level]

    @property
    def need_to_set_root(self):
        return (
            self.int_root_log_level
            <= getattr(logging, "_nameToLevel")["DEBUG"]
        )

    class Config:
        env_prefix = "log_"


class PostgresSettings(BaseSettings):
    user: str = "postgres"
    password: str = "postgres"
    db: str = "mats"

    class Config:
        env_prefix = "postgres_"


class DbSettings(BaseSettings):
    pg_creds: PostgresSettings = Field(default_factory=PostgresSettings)
    host: str = "localhost"
    port: str = "5432"
    pool_size: int = 1  # just for async_session context

    driver_schema: str = "postgresql+asyncpg"

    class Config:
        env_prefix = "database_"

    @property
    def db_url(self) -> PostgresDsn:
        return (
            f"{self.driver_schema}://"
            f"{self.pg_creds.user}:{self.pg_creds.password}@"
            f"{self.host}:{self.port}"
            f"/{self.pg_creds.db}"
        )


class Api(BaseSettings):
    versions: list[int] = [1]
    base_version: int = 1
    api_prefix: str = "/api"
    docs_disable: bool = False

    @field_validator("api_prefix")
    def api_prefix_cvt(cls, value: str):
        if not value:
            return value
        if not value.startswith("/"):
            value = "/" + value
        return value.rstrip("/")

    @model_validator(mode="after")
    def check_default_version(self):
        assert self.base_version in self.versions
        return self

    class Config:
        env_prefix = "api_"


class Settings(BaseSettings):
    app: App = Field(default_factory=App)
    logging: Logging = Field(default_factory=Logging)
    db: DbSettings = Field(default_factory=DbSettings)
    api: Api = Field(default_factory=Api)

    @property
    def uvicorn_kwargs(self) -> dict:
        result = self.app.model_dump(include={"host", "port"})
        result["log_level"] = self.logging.level_root.lower()
        return result

    @property
    def debug(self) -> bool:
        return self.logging.level == "DEBUG"


class AlembicSettings(BaseSettings):
    db: DbSettings = Field(default_factory=DbSettings)


@cache
def get_settings():
    if (env_settings := EnvSettings()).ignore:
        dotenv_path = None
    elif env_settings.is_env_path_abs:
        dotenv_path = env_settings.name
    else:
        dotenv_path = find_dotenv(env_settings.name)
    load_dotenv(dotenv_path)
    if "alembic" in sys.argv[0]:
        return AlembicSettings()
    _settings = Settings()
    if _settings.logging.need_to_set_root:
        logging.getLogger().setLevel(_settings.logging.int_root_log_level)
    return _settings
