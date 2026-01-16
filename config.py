"""Configuration management for the Job Search Agent."""
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

# Load environment variables
load_dotenv()


class Config:
    """Application configuration."""
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini/gemini-1.5-flash")
    
    # Scraping Configuration
    SCRAPER_HEADLESS: bool = os.getenv("SCRAPER_HEADLESS", "true").lower() == "true"
    SCRAPER_TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "30"))
    SCRAPER_DELAY: float = float(os.getenv("SCRAPER_DELAY", "2"))
    
    # Output Configuration
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "./output"))
    JOBS_CSV_FILE: str = os.getenv("JOBS_CSV_FILE", "jobs_tracker.csv")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        if not cls.GEMINI_API_KEY and cls.LLM_PROVIDER == "gemini":
            raise ValueError("GEMINI_API_KEY is required when using Gemini provider")
        return True
    
    @classmethod
    def setup_output_dir(cls) -> None:
        """Create output directory if it doesn't exist."""
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
