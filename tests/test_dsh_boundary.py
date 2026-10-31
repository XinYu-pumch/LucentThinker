import pytest
from fastapi.testclient import TestClient
from app.dsh import PluginBoundary
from app.main import app
from app import config, store, settings_store


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    token = 'a' * 64
    monkeypatch.setattr(config, 'URL_PREFIX', '/dsh/' + token)
    with TestClient(PluginBoundary(app, token, 'http://127.0.0.1:8893')) as client:
        yield client, '/dsh/' + token


def test_plugin_assets_and_api_require_exact_capability_and_retain_origin_checks(plugin):
    client, prefix = plugin
    assert client.get('/api/projects').status_code == 404
    assert client.get('/dsh/' + 'b' * 64 + '/api/projects').status_code == 404
    page = client.get(prefix + '/', headers={'sec-fetch-site': 'cross-site'})
    assert page.status_code == 200
    assert 'frame-ancestors dsh-app://app http://127.0.0.1:8893' in page.headers['content-security-policy']
    assert f'content="{prefix}"' in page.text
    assert f'src="{prefix}/static/app.js?v=' in page.text
    assert client.get(prefix + '/static/dsh.js').status_code == 200
    assert client.get(prefix + '/api/projects', headers={'origin': 'https://evil.invalid'}).status_code == 403
    assert client.post(prefix + '/api/projects', json={'name': 'Attack'}, headers={'sec-fetch-site': 'cross-site'}).status_code == 403


@pytest.mark.parametrize('origin', ['*', 'https://evil.invalid', 'http://127.0.0.1:8893/path', 'http://user@localhost:2', 'http://localhost:2; frame-ancestors *'])
def test_embedding_cannot_be_enabled_for_arbitrary_sites(origin):
    with pytest.raises(ValueError):
        PluginBoundary(app, 'a' * 64, origin)
