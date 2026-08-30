"""Настройки приложения, читаемые из переменных окружения / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./tmap.db"

    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Тестовый режим: не дёргает Anthropic API вообще, оформляет рапорт
    # простой эвристикой (ключевые слова, regex для адреса). Нужен, чтобы
    # проверять весь путь (превью → правка полей → точка на карте →
    # сохранение дела) без платного ключа. Выключите, когда ключ появится.
    ai_stub_mode: bool = False

    nominatim_user_agent: str = "TMap-internal-ops/1.0"

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "change-me-too"

    cors_origins: str = "http://localhost:8642,http://127.0.0.1:8642"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
