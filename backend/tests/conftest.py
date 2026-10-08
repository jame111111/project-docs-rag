import hashlib

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings


class OfflineEmbeddings:
    """仅供离线流程测试的确定性向量，不用于真实检索评测。"""
    def encode(self, texts, query=False):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([(byte - 127) / 128 for byte in digest])
        return vectors


@pytest.fixture
def offline_app(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, embedding_model='offline-test',
                        llm_base_url='', llm_api_key='', llm_model='')
    return create_app(settings, embeddings=OfflineEmbeddings())


@pytest.fixture
def client(offline_app):
    return TestClient(offline_app)
