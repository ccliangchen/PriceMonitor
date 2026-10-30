import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        port=0,
        data_dir=tmp_path,
        token="test-token",
        log_level="INFO",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        yield test_client
