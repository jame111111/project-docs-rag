from pathlib import Path
from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

from .products import load_product

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / 'backend/.env', extra='ignore')
    product_config: Path = ROOT / 'products/knowledge-base/product.json'
    data_dir: Path | None = None
    embedding_model: str = 'BAAI/bge-small-zh-v1.5'
    embedding_revision: str = '7999e1d3359715c523056ef9478215996d62a620'
    embedding_local_only: bool = True
    embedding_device: str = 'cpu'
    llm_base_url: str = ''
    llm_api_key: str = ''
    llm_model: str = ''
    llm_timeout_seconds: float = 60
    context_budget: int = 4000
    upload_max_bytes: int = 1048576

    @cached_property
    def product(self):
        return load_product(self.product_config)

    @model_validator(mode='after')
    def resolve_paths(self):
        if not self.product_config.is_absolute():
            self.product_config = ROOT / self.product_config
        self.product_config = self.product_config.resolve()
        self.data_dir = self.data_dir or ROOT / 'data/runtime' / self.product.id
        if not self.data_dir.is_absolute():
            self.data_dir = ROOT / self.data_dir
        self.data_dir = self.data_dir.resolve()
        return self

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)
