"""Runtime configuration, loaded from the environment / repo-root .env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), extra="ignore"
    )

    openai_base_url: str = ""
    openai_api_key: str = ""

    # gpt-4.1-mini is the only provided model with reliable tool-calling
    # support; gpt-5.2-chat is chat-tuned and drops tools (see docs/decisions.md).
    model_name: str = "gpt-4.1-mini"

    # The provided clinical database (read + write, schema untouched).
    database_path: Path = REPO_ROOT / "database.db"
    # LangGraph checkpoints live in a separate file so the provided db stays as-is.
    checkpoint_path: Path = REPO_ROOT / "checkpoints.db"


settings = Settings()
