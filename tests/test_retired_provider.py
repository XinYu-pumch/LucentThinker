"""Retire the former built-in provider without rewriting research history."""
import copy
import json
import stat

import pytest
from fastapi.testclient import TestClient
from app import config, main, settings_schema, settings_store as settings, store
from app.llm_providers import registry
from settings_fixtures import legacy_document


@pytest.mark.parametrize('version', [3, 4])
def test_retired_provider_upgrade_backs_up_and_clears_only_its_bindings(tmp_path, monkeypatch, version):
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    old = legacy_document()
    retired = old['profiles']['summary']
    retired.update(provider='fourrouter_argon', base_url='https://4router.net/v1',
                   model='gemini-4-argon', api_key='retired-fixture-key')
    custom = copy.deepcopy(retired)
    custom.update(id='custom', name='User provider', provider='openai')
    old['profiles']['custom'] = custom
    if version == 4:
        # Represent the compact schema saved before the provider was retired.
        old['profiles'].pop('summary')
        old = settings_schema.compact(old)
        old['suppliers']['builtin_fourrouter_argon'] = {
            'id': 'builtin_fourrouter_argon', 'name': '4router', 'provider': 'fourrouter_argon',
            'builtin': True, 'base_url': retired['base_url'], 'api_key': retired['api_key'], 'catalog': [],
        }
        old['profiles']['summary'] = {'id': 'summary', 'name': 'Old model', 'model': retired['model'],
                                      'supplier_id': 'builtin_fourrouter_argon', 'concurrency': 1}
    original = json.dumps(old).encode()
    settings.SETTINGS_FILE.write_bytes(original)
    with TestClient(main.app) as client:
        rid = store.new_run(store.new_conversation(), 'Old question', config_snapshot={'summary_model': retired})
        store.update(rid, status='completed', answer='Historical answer')
        doc = client.get('/api/config').json()['settings']
        assert 'fourrouter_argon' not in doc['providers']
        assert 'summary' not in doc['profiles']
        assert all(s['provider'] != 'fourrouter_argon' for s in doc['suppliers'].values())
        assert doc['active'] == {'main': 'main', 'summary': ''}
        assert doc['profiles']['custom']['provider'] == 'openai'
        assert store.get_run(rid)['answer'] == 'Historical answer'
        assert store.get_run(rid)['config_snapshot']['summary_model']['provider'] == 'fourrouter_argon'
    backups = list((tmp_path / 'backups').glob('settings-*.json'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    assert 'retired-fixture-key' not in json.dumps(settings.public())
    assert 'fourrouter_argon' not in settings.SETTINGS_FILE.read_text()
    settings.ensure()
    assert len(list((tmp_path / 'backups').glob('settings-*.json'))) == 1


def test_fresh_catalog_and_model_creation_reject_retired_adapter():
    assert 'fourrouter_argon' not in registry.enabled()
    assert 'builtin_fourrouter_argon' not in settings.load()['suppliers']
    with pytest.raises(ValueError):
        settings.save_profile({'name': 'Retired', 'provider': 'fourrouter_argon',
                               'model': 'gemini-4-argon', 'base_url': 'https://4router.net/v1'})
