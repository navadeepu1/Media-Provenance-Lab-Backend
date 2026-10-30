from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/mpl.db"
    admin_api_key: str = ""
    ai_provider: str = "none"
    gemini_api_key: str = ""
    groq_api_key: str = ""
    hf_token: str = ""
    job_budget_seconds: int = 90
    max_image_bytes: int = 10 * 1024 * 1024
    max_video_bytes: int = 25 * 1024 * 1024
    max_pixels: int = 16_000_000
    max_image_side: int = 5000
    data_dir: Path = Path("data")
    cors_origins: str = ""
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"


settings = Settings()

