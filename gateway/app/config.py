"""
Configuration management for the API Gateway.

This module handles loading and accessing configuration from environment
variables and YAML files.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        models_config_path: Path to the models YAML configuration file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        gateway_host: Host address to bind the gateway
        gateway_port: Port number for the gateway
    """

    # Configuration paths
    models_config_path: str = "gateway/config/models.yaml"

    # Logging
    log_level: str = "INFO"
    log_dir: str = "./logs"

    # Server settings
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000

    # Timeouts (seconds)
    model_timeout_seconds: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
