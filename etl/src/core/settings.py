import datetime as dt
import json
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    base_dir: Path = Path(__file__).parent.parent
    debug: bool = False
    log_level: str = "DEBUG" if debug else "INFO"

    etl_interval: dt.timedelta = dt.timedelta(seconds=20)

    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    batch_size: int = 100

    elastic_search_host: str
    elastic_search_port: int
    elastic_search_movies_index_name: str = "movies"
    elastic_search_movies_index_schema: dict = json.loads(
        (base_dir / "core" / "movies_index_schema.json").read_text()
    )

    redis_host: str
    redis_port: int
    redis_db: int

    @property
    def postgres_dsn(self) -> str:
        return f"postgres://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def elastic_dsn(self) -> str:
        return f"http://{self.elastic_search_host}:{self.elastic_search_port}"

    @property
    def elastic_index(self) -> tuple[str, dict]:
        return self.elastic_search_movies_index_name, self.elastic_search_movies_index_schema

    @property
    def redis_dsn(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"