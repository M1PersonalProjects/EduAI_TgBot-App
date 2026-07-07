import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, ".env")

class Settings(BaseSettings):
    bot_token: SecretStr
    openai_api_key: SecretStr
    database_url: SecretStr
    admin_ids: set[int] = set()

model_config = SettingsConfigDict(
        env_file=env_path, 
        env_file_encoding="utf-8",
        extra="ignore" 
    )
settings = Settings()