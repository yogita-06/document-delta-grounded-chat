from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    llm_provider: str = "mock"
    llm_model: str = "gpt-4.1-mini"
    openai_api_key: str = ""
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    tesseract_cmd: str = ""
    ocr_min_confidence: float = .50
    page_alignment_min_score: float = .55
    element_alignment_min_score: float = .62
    modification_text_threshold: float = .94
    move_distance_threshold: float = .15
    max_upload_mb: int = 25
    ocr_dpi: int = 300
    data_dir: Path = Path("data")
    def ensure_dirs(self) -> None:
        for name in ("uploads","canonical","reports","markup","traces","indexes","samples"):
            (self.data_dir/name).mkdir(parents=True,exist_ok=True)
settings=Settings()
