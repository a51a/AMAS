"""Local configuration loaded from environment / .env (never committed)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AMAS_", extra="ignore")

    data_dir: Path = Path("./data")
    host: str = "127.0.0.1"
    port: int = 8000

    frame_fps: float = 1.0
    frame_width: int = 480
    segment_crop_width: float = 0.4
    segment_min_seconds: float = 3.0
    segment_diff_threshold: float = 28.0

    classifier: str = "mock"
    review_confidence_threshold: float = 0.7
    allow_external_providers: bool = False
    anthropic_model: str = "claude-opus-5-5"
    llm_max_frames_per_reel: int = 3

    ocr: str = "auto"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "amas.sqlite"

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.recordings_dir, self.exports_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
