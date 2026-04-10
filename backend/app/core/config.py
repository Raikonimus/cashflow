from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str

    # JWT
    jwt_secret_key: str
    jwt_expire_minutes: int = 60

    # App
    frontend_url: str = "http://localhost:5173"
    env: str = "development"

    # SMTP
    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 2525
    smtp_security: str = "starttls"  # starttls | ssl | none
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = ""
    smtp_reply_to: Optional[str] = None

    # Invitation
    invitation_expire_days: int = 7

    # Dev Seed (never set in production)
    seed_admin_email: Optional[str] = None
    seed_admin_password: Optional[str] = None


settings = Settings()
