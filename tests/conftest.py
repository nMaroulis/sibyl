"""Isolated demo applications that never read developer credentials or network providers."""

import pytest
from fastapi.testclient import TestClient

from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.storage import Store


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, _env_file=None)


@pytest.fixture
def store(settings):
    return Store(settings.data_dir)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client
