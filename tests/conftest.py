"""Keep every test's settings writes inside its temporary directory."""
import pytest
from app import settings_store


@pytest.fixture(autouse=True)
def isolate_settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
