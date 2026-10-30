import hashlib
import re

from fastapi.testclient import TestClient

from app import config, settings_store, store
from app.main import app, index


def test_current_assets_and_config_are_not_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(config, 'API_KEY', '')
    monkeypatch.setattr(config, 'SECRETS', set())
    with TestClient(app) as client:
        page = client.get('/')
        assert page.headers['cache-control'] == 'no-store'
        assets = re.findall(r'(?:src|href)="(/static/[^\"]+)"', page.text)
        assert assets
        for url in assets:
            path, digest = url.split('?v=')
            content = (config.ROOT / 'app' / path.lstrip('/')).read_bytes()
            assert digest == hashlib.sha256(content).hexdigest()[:16]
            response = client.get(url)
            assert response.content == content
            assert response.headers['cache-control'] == 'no-cache'
            if path.endswith('/settings.js'):
                assert 'renderSupplierSidebar' in response.text
        cfg = client.get('/api/config')
        assert cfg.headers['cache-control'] == 'no-store'
        assert 'providers' in cfg.json()['settings']


def test_asset_change_changes_url_without_changing_html(tmp_path, monkeypatch):
    static = tmp_path / 'app' / 'static'
    static.mkdir(parents=True)
    (static / 'index.html').write_text('<script src="/static/settings.js"></script>')
    script = static / 'settings.js'
    script.write_text('old')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    before = index().body
    script.write_text('new')
    after = index().body
    assert before != after
    assert hashlib.sha256(b'new').hexdigest()[:16].encode() in after
