from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_deployment_name: str = "gpt-4.1-mini"
    azure_openai_api_version: str = "2024-12-01-preview"
    
    model_temperature: float = 0.7
    model_max_tokens: int = 2000
    
    output_directory: str = "outputs"
    temp_directory: str = "temp"
    
    # SSW Brand Colors
    theme_primary_color: str = "#cc4141"  # Red
    theme_charcoal: str = "#333333"  # Charcoal
    theme_grey: str = "#aaaaaa"  # Grey
    theme_dark_grey: str = "#797979"  # Darker Grey
    theme_white: str = "#ffffff"  # White
    
    # Chart Label Limits (characters before truncation)
    chart_title_max_length: int = 150
    chart_label_max_length: int = 40
    pie_label_max_length: int = 50
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    return Settings()

