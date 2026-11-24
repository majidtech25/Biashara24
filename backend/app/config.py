from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    environment: str = "development"
    business_timezone: str = "Africa/Nairobi"
    app_name: str = "Biashara360 API"
    database_url: str = "sqlite:///./biashara360.db"
    secret_key: str = "change-this-secret-in-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    sentry_dsn: str = ""
    # M-Pesa Paybill (Daraja). Payment monitoring and bill QR codes stay off until key, secret,
    # Paybill number, public address and callback token are set. Staff can always enter receipts by hand.
    mpesa_environment: str = "sandbox"  # sandbox or production
    mpesa_base_url: str = ""  # optional override of the Daraja address
    mpesa_consumer_key: str = ""
    mpesa_consumer_secret: str = ""
    mpesa_shortcode: str = ""  # the business Paybill number
    mpesa_business_name: str = ""  # name shown with the QR code; defaults to the app name
    mpesa_callback_url: str = ""  # public HTTPS address of this server, e.g. https://pos.example.co.ke
    mpesa_callback_token: str = ""  # long random secret, part of the address Safaricom posts payments to
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5500"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def production_secret(self):
        if self.environment == "production" and (len(self.secret_key) < 32 or self.secret_key in {"change-this-secret-in-production", "replace-with-a-long-random-secret"}):
            raise ValueError("Production requires a unique SECRET_KEY of at least 32 characters")
        return self

    @property
    def mpesa_enabled(self) -> bool:
        return all((self.mpesa_consumer_key, self.mpesa_consumer_secret, self.mpesa_shortcode,
                    self.mpesa_callback_url, len(self.mpesa_callback_token) >= 16))

    @property
    def origins(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
