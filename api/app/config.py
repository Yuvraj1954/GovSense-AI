from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    DATABASE_URL: str
    DB2_DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    DB2_URL: str = ""
    DB2_SECRET_KEY: str = ""
    DB2_SERVICE_ROLE_KEY: str = ""

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
