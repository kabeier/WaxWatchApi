from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "watch-wax-api"
    environment: str = "dev"

    database_url: str 
    # redis_url: str
    database_url: str
    dev_auto_create_users: bool = True  # set false in prod

    # defaults
    log_level: str = "INFO"


settings = Settings()
