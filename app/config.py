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
    detector_repo: str = ""
    detector_revision: str = ""
    detector_local_path: str = "model_int8.onnx"
    detector_filename: str = "model_int8.onnx"
    detector_sha256: str = "C58229F69570BE40698120B31DEFD985C63904575BAACFFAD1A7866FDA6EFCC5"
    detector_calibration_path: str = ""
    job_budget_seconds: int = 90
    max_image_bytes: int = 10 * 1024 * 1024
    max_video_bytes: int = 25 * 1024 * 1024
    max_pixels: int = 16_000_000
    max_image_side: int = 5000
    data_dir: Path = Path("data")
    cors_origins: str = ""
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 30
    cleanup_interval_seconds: int = 3600
    report_ttl_days: int = 30
    job_ttl_days: int = 1
    known_item_phash_threshold: int = 8
    known_item_dhash_threshold: int = 8
    explainer_timeout_seconds: float = 8.0
    explainer_cache_ttl_days: int = 30
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"
    
    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"


settings = Settings()
