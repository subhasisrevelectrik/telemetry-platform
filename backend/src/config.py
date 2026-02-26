"""Configuration management using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Local development mode
    local_mode: bool = False

    # AWS configuration
    aws_region: str = "us-east-1"
    athena_database: str = "telemetry_db"
    athena_results_bucket: str = ""
    s3_data_bucket: str = ""

    # Cognito (optional)
    cognito_user_pool_id: str = ""
    cognito_region: str = "us-east-1"

    # Local mode configuration
    local_data_dir: str = "./data/decoded"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="",
    )


# Global settings instance
settings = Settings()
