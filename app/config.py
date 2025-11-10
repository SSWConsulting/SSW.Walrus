from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    azure_openai_api_key: str
    azure_openai_endpoint: str
    azure_openai_deployment_name: str = "gpt-5-nano"
    azure_openai_api_version: str = "2023-12-01-preview"
    
    model_temperature: float = 0.7
    model_max_tokens: int = 2000
    
    output_directory: str = "outputs"
    temp_directory: str = "temp"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    return Settings()

