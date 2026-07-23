import os
from typing import Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, ".env")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=env_path,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: SecretStr
    openai_api_key: SecretStr
    database_url: str
    admin_ids: set[int] = Field(default_factory=set)
    webapp_base_url: str = "https://localhost:8000"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip("[]'\" ")
            return {int(x.strip()) for x in v.split(",") if x.strip()}
        if isinstance(v, int):
            return {v}
        return v

settings = Settings()
