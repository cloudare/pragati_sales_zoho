"""Application configuration loaded from environment."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
from dotenv import load_dotenv


class Settings(BaseSettings):
    # if os.getenv("RENDER"):
    #     pass
    # else:
    #     load_dotenv(".env.example")
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # Database
    database_url: str = "postgresql://pragati:pragati@localhost:5432/pragati_sales"
    # database_url: str = "postgresql://pragati:admin@localhost:5432/pragati_sales"

    # App
    app_secret_key: str = "change-me"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Auth — short access tokens + long refresh tokens for revocation
    access_token_expire_minutes: int = 30        # was 480 (8 hrs); short to limit stolen-token blast radius
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"

    # Password policy
    password_min_length: int = 10

    # Account lockout (anti brute-force on top of rate limit)
    max_failed_login_attempts: int = 10
    lockout_minutes: int = 15

    # Login rate limit (per IP)
    login_rate_limit: str = "5/minute"

    # 2FA — list of roles for which 2FA is required (still allow users to enable it)
    # Empty string = optional for all. "admin,accounts" = required for those roles.
    require_2fa_for_roles: str = ""

    # Tally
    tally_api_key: str = "pragati-tally-shared-key-change-me"
    # Outbound (PRD M14: Zoho → Tally) — HTTP endpoint of the Tally machine's gateway
    tally_endpoint: str = ""                # e.g. http://192.168.1.50:9000
    tally_company_name: str = "Pragati Sales"
    tally_sync_enabled: bool = True

    # Zoho webhooks - shared secret for verifying webhook authenticity
    zoho_webhook_secret: str = "change-me-zoho-webhook-shared-secret"

    # Celery / Redis (for async tasks and scheduled jobs)
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = ""              # falls back to redis_url
    celery_result_backend: str = ""          # falls back to redis_url
    celery_eager: bool = False               # True = run tasks inline (no worker needed; for tests)

    # Zoho
    # zoho_client_id: str = ""
    # zoho_client_secret: str = ""
    # zoho_refresh_token: str = ""
    # zoho_org_id: str = ""
    # zoho_dc: str = "in"
    zoho_client_id: str 
    zoho_client_secret: str
    zoho_refresh_token: str
    zoho_org_id: str
    zoho_dc: str

    # Files
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def require_2fa_roles_list(self) -> List[str]:
        return [r.strip() for r in self.require_2fa_for_roles.split(",") if r.strip()]

    @property
    def zoho_accounts_url(self) -> str:
        if self.zoho_dc == "local-mock":
            return "http://localhost:9000"
        return f"https://accounts.zoho.{self.zoho_dc}"

    @property
    def zoho_api_base(self) -> str:
        if self.zoho_dc == "local-mock":
            return "http://localhost:9000"
        return f"https://www.zohoapis.{self.zoho_dc}"


settings = Settings()
