from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    api_key: str = Field(..., alias="API_KEY")
    workspace_root: str = Field("./workspace", alias="WORKSPACE_ROOT")
    database_url: str = Field("postgresql+asyncpg://agent:agent@localhost:5432/agent", alias="DATABASE_URL")
    ollama_host: str = Field("http://host.docker.internal:11434", alias="OLLAMA_HOST")
    model_registry_path: str = Field("./config/models.yaml", alias="MODEL_REGISTRY_PATH")
    ff_smoke_tests: bool = Field(True, alias="FF_SMOKE_TESTS")
    ff_standards_enforce: str = Field("soft", alias="FF_STANDARDS_ENFORCE")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
