from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    takeone_env: str = "local"
    database_url: str = "postgresql+psycopg://takeone:takeone@localhost:5432/takeone"
    temporal_address: str = "localhost:7233"
    temporal_task_queue: str = "takeone-generation"


settings = Settings()
