from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    PROJECT_NAME: str = "Alert Fatigue Buster API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/alert_buster"
    POSTGRES_USER: Optional[str] = "postgres"
    POSTGRES_PASSWORD: Optional[str] = "postgres"
    POSTGRES_DB: Optional[str] = "alert_buster"
    POSTGRES_HOST: Optional[str] = "localhost"
    POSTGRES_PORT: Optional[int] = 5432

    # Phase 2 Intelligence Parameters
    DEDUP_WINDOW_SECONDS: int = 300       # 5-minute sliding deduplication window
    STORM_WINDOW_SECONDS: int = 60        # 1-minute alert storm velocity window
    STORM_ALERT_THRESHOLD: int = 20       # Alert count within window triggering storm flag
    CORRELATION_WINDOW_SECONDS: int = 900 # 15-minute incident correlation window

    # Phase 3 Decision, Suppression & Notification Parameters
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_CHANNEL: str = "#alerts"
    SLACK_ENABLED: bool = False
    ALERT_COOLDOWN_SECONDS: int = 300          # 5-minute cooldown for repeated notifications
    ESCALATION_THRESHOLD_SECONDS: int = 600    # 10 minutes unresolved critical threshold
    ESCALATION_OCCURRENCE_THRESHOLD: int = 10  # 10 duplicate bursts triggering escalation


settings = Settings()
