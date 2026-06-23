"""Application configuration loaded from environment."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os
from dotenv import load_dotenv


class Settings(BaseSettings):
    if os.getenv("RENDER"):
        pass
    else:
        load_dotenv(".env.example")
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # Database
    database_url: str = "postgresql://pragati:pragati@localhost:5432/pragati_sales"

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

    # Zoho
    # zoho_client_id: str = "1000.RWK99OIJQIYPKB8WMPLT1YCM0142LL"
    # zoho_client_secret: str = "cf93079323600910dc24b6c9eab80617f8767b900b"
    # zoho_refresh_token: str = "1000.36287bcbf371abcf9156f8621081b1a6.c8223677ef6fd6a83544672316ce58a5"
    # zoho_org_id: str = "60043759810"
    # zoho_dc: str = "in"

    zoho_client_id: str = os.getenv("ZOHO_CLIENT_ID")
    zoho_client_secret: str = os.getenv("ZOHO_CLIENT_SECRET")
    zoho_refresh_token: str = os.getenv("ZOHO_REFRESH_TOKEN")
    zoho_org_id: str = os.getenv("ZOHO_ORG_ID")
    zoho_dc: str = os.getenv("ZOHO_DC")

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
