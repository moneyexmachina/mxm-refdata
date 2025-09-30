"""Configuration details for the refData application."""

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    SQL_DB_URL: str = "sqlite:///data/refdata.db"
    REFDATA_FUTURES_PRODUCTS_CSV_PATH: str = "data/futures_products.csv"

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


def load_config() -> Config:
    return Config()
