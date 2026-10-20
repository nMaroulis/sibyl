"""Isolated demo applications that never read developer credentials or network providers."""

import pytest
from fastapi.testclient import TestClient

from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.models import ConnectionCreate
from sibyl.storage import Store


@pytest.fixture
def settings(tmp_path):
    config = Settings(data_dir=tmp_path, _env_file=None)
    repository = Store(config.data_dir)
    repository.save_data_profile("market", {"source": "demo", "profiles": {}})
    repository.add_connection(ConnectionCreate(exchange="demo", label="Demo account"))
    return config


@pytest.fixture
def store(settings):
    return Store(settings.data_dir)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client
