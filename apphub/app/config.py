from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {key}")
    return value


@dataclass(frozen=True)
class Settings:
    app_env: str = _env("APP_ENV", "development")
    app_name: str = _env("APP_NAME", "AppHub")
    app_url: str = _env("APP_URL", "http://localhost:8000")
    apphub_root: str = _env("APPHUB_ROOT", "/apphub")
    secret_key: str = _env("SECRET_KEY")
    database_url: str = _env("DATABASE_URL")
    storage_root: str = _env("STORAGE_ROOT", "/var/www/apphub/storage")
    max_upload_mb: int = int(_env("MAX_UPLOAD_MB", "500"))
    allowed_upload_extensions: list[str] = _env(
        "ALLOWED_UPLOAD_EXTENSIONS",
        ".dmg,.exe,.msi,.pkg,.zip,.tar.gz,.tgz",
    ).split(",")
    allowed_media_extensions: list[str] = _env(
        "ALLOWED_MEDIA_EXTENSIONS", ".png,.jpg,.jpeg,.webp,.gif,.svg"
    ).split(",")
    clamav_enabled: bool = _env("CLAMAV_ENABLED", "false").lower() == "true"
    clamav_socket: str = _env("CLAMAV_SOCKET", "/var/run/clamav/clamd.ctl")


settings = Settings()
