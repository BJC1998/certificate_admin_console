"""Environment configuration without working-directory-dependent database paths."""

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_url: str
    cors_origins: tuple[str, ...]


def load_settings() -> Settings:
    return Settings(
        app_name="Certificate Admin Console",
        database_url=os.getenv(
            "DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'certificate_admin.db').as_posix()}"
        ),
        cors_origins=tuple(
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if origin.strip()
        ),
    )


settings = load_settings()
