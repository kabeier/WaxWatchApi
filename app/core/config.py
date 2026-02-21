from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "watch-wax-api"
    environment: str = "dev"

    database_url: str 
    database_url: str
    dev_auto_create_users: bool = True  
    dev_backfill_on_rule_change: bool = True
    dev_backfill_days: int = 7
    dev_backfill_limit: int = 500
    
    discogs_user_agent: str
    discogs_token: str
    
    log_level: str = "INFO"


settings = Settings()
