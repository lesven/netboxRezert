from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    netbox_url: str = "http://localhost:8000"
    netbox_token: str = "changeme"
    netbox_mock: bool = True
    netbox_ssl_verify: bool = True

    database_path: str = "data/tokens.sqlite3"

    base_url: str = "http://localhost:8080"

    contact_search_limit: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
