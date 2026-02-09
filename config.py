from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Setting(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    # JWT Settings
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Database Settings
    db_user: str = "lokerin"
    db_password: str = "lokerin123"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "lokerin_db"

settings = Setting() 