"""
AeroSync Application Settings

Central configuration loaded from environment variables using pydantic-settings.
Zero hardcoded values — everything comes from .env or environment.
"""

from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root directory (two levels up from config/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env file into process environment BEFORE any settings classes
# are instantiated. This ensures sub-settings with env_prefix can read values.
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    load_dotenv(_env_file, override=False)


class JWTSettings(BaseSettings):
    """JWT authentication configuration."""

    model_config = SettingsConfigDict(env_prefix="JWT_")

    secret: str = Field(
        ...,
        min_length=32,
        description="Secret key for JWT signing. Must be at least 32 characters.",
    )
    algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    access_token_expire_minutes: int = Field(
        default=1440, description="Access token expiry in minutes (default: 24h)."
    )
    refresh_token_expire_days: int = Field(
        default=30, description="Refresh token expiry in days."
    )


class DatabaseSettings(BaseSettings):
    """Database connection configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{PROJECT_ROOT / 'aerosync.db'}",
        description="Database connection URL. Defaults to local SQLite.",
    )


class SupabaseSettings(BaseSettings):
    """Supabase configuration (optional — falls back to SQLite if not set)."""

    model_config = SettingsConfigDict(env_prefix="SUPABASE_")

    url: Optional[str] = Field(default=None, description="Supabase project URL.")
    anon_key: Optional[str] = Field(default=None, description="Supabase anonymous key.")
    service_role_key: Optional[str] = Field(
        default=None, description="Supabase service role key."
    )
    storage_bucket: str = Field(
        default="session-packages", description="Storage bucket for session packages."
    )

    @property
    def is_configured(self) -> bool:
        """Check if Supabase is fully configured."""
        return all([self.url, self.anon_key, self.service_role_key])


class ServerSettings(BaseSettings):
    """HTTP server configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    port: int = Field(default=8000, description="Server port.")
    host: str = Field(default="0.0.0.0", description="Server bind host.")
    environment: str = Field(
        default="development", description="Runtime environment: development | staging | production."
    )
    log_level: str = Field(default="DEBUG", description="Logging level.")
    allowed_origins: str = Field(
        default="http://localhost:1420,http://localhost:5173,tauri://localhost",
        description="Comma-separated list of allowed CORS origins.",
    )

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse comma-separated origins into a list."""
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


class ClientSettings(BaseSettings):
    """Client-side configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    relay_server_url: str = Field(
        default="http://localhost:8000", description="Relay server URL."
    )
    gesture_engine_port: int = Field(
        default=7878, description="Local gesture engine API port."
    )
    chrome_debug_port: int = Field(
        default=9222, description="Chrome DevTools Protocol debugging port."
    )


class SessionSettings(BaseSettings):
    """Session package configuration."""

    model_config = SettingsConfigDict(env_prefix="SESSION_")

    package_max_size_mb: int = Field(
        default=50, description="Maximum session package size in MB."
    )
    expiry_minutes: int = Field(
        default=30, description="Session expiry time in minutes."
    )
    cleanup_interval_minutes: int = Field(
        default=5, description="Interval between session cleanup runs in minutes."
    )

    @property
    def package_max_size_bytes(self) -> int:
        """Maximum package size in bytes."""
        return self.package_max_size_mb * 1024 * 1024


class AISettings(BaseSettings):
    """Gemini AI and Screen Reader configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    gemini_api_key: Optional[str] = Field(
        default=None, description="Google Gemini API key for vision-based screen content analysis."
    )
    screen_reader_enabled: bool = Field(
        default=True, description="Enable OCR and AI screen analysis during workspace transfer."
    )


class Settings(BaseSettings):
    """
    Master settings class that composes all sub-settings.
    
    Usage:
        from config.settings import get_settings
        settings = get_settings()
        print(settings.jwt.secret)
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt: JWTSettings = Field(default_factory=JWTSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    client: ClientSettings = Field(default_factory=ClientSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    ai: AISettings = Field(default_factory=AISettings)


# Singleton pattern for settings
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the application settings singleton.
    
    Returns:
        Settings: The application settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset settings singleton (useful for testing)."""
    global _settings
    _settings = None
