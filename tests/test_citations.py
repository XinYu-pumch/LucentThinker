import re

import pytest

from app.citations import (append_registered_references, cited_ids, normalize_citations,
                           reconcile, refresh_registered_references)

SOURCES = [{'id': n, 'title': f'Source {n}', 'url': f'https://example.org/{n}'}
           for n in (42, 56, 172)]


@pytest.mark.parametrize('marker', [
    '[42, 56]', '[42,56]', '[42][56]', '[42，56]', '[42、56]',
    '[42;56]', '［42，56］', '【４２、５６】', '[４２, ５６]', '[ 42 ,\t56 ]',
])
def test_supported_groups_are_checked_and_all_listed(marker):
    answer, checks = reconcile('Claim ' + marker, SOURCES)
    assert answer == 'Claim [42][56]'
    assert not any(checks.values())
    refs = append_registered_references(answer, SOURCES)
    assert re.findall(r'^- \[(\d+)\]', refs, re.M) == ['42', '56']
    assert cited_ids(marker) == {42, 56}


def test_group_unknown_ids_deduplication_and_link_conflicts():
    answer, checks = reconcile('Claim [42, 999, 56, 42].', SOURCES)
    assert '[引用无法匹配 999]' in answer
    assert checks['unmatched_ids'] == [999]
    assert not checks['missing_citations']
    assert append_registered_references(answer, SOURCES).count('- [42]') == 1
    answer, checks = reconcile('[42, 56](https://wrong.org/page)', SOURCES)
    assert checks['conflicting_ids'] == [42, 56]
    assert '[42](<https://example.org/42>)[56](<https://example.org/56>)' in answer


def test_code_ranges_non_numeric_labels_and_link_destinations_are_not_citations():
    text = ('`[42,56]`\n```text\n【42、56】\n```\n~~~\n[42,56]\n~~~\n'
            '[42-56] [42–56] [^42] [item 42] ［42,56] '
            '[docs](https://example.org/a?q=[42,56]) '
            '<https://example.org/a?q=[42,56]>')
    assert normalize_citations(text) == text
    assert cited_ids(text) == set()
    assert append_registered_references(text, SOURCES) == text
    answer, checks = reconcile(text, SOURCES)
    assert answer == text
    assert checks['unmatched_ids'] == []


def test_numeric_url_parameters_do_not_become_citations():
    text = 'Claim [42](https://example.org/42?ids=[999]).'
    sources = [{'id': 42, 'url': 'https://example.org/42?ids=[999]'}]
    answer, checks = reconcile(text, sources)
    assert not any(checks.values())
    assert cited_ids(answer) == {42}
    assert '?ids=[999]' in answer


def test_historical_generated_tail_is_rebuilt_and_idempotent():
    old = append_registered_references('Claim [42].', SOURCES, 'References')
    old = old.replace('Claim [42].', 'Claim [42]. More [56, 172].')
    fixed = refresh_registered_references(old, SOURCES)
    assert fixed.startswith('Claim [42]. More [56][172].')
    assert re.findall(r'^- \[(\d+)\]', fixed, re.M) == ['42', '56', '172']
    assert fixed.count('### References') == 1
    assert refresh_registered_references(fixed, SOURCES) == fixed
    no_tail = refresh_registered_references('Only [42, 56].', SOURCES, 'References')
    assert '- [42]' in no_tail and '- [56]' in no_tail


def test_custom_bibliography_is_not_discarded():
    text = 'Claim [42, 56].\n\n### References\n\nMy hand-written commentary.'
    assert refresh_registered_references(text, SOURCES) == text


def test_history_and_exports_repair_without_database_rewrite(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import store, settings_store, config
    from app.main import app
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(config, 'API_KEY', '')
    monkeypatch.setattr(config, 'SECRETS', set())
    old = append_registered_references('Claim [42].', SOURCES, 'References').replace(
        'Claim [42].', 'Claim [42]. More [56, 172].')
    with TestClient(app) as client:
        cid = store.new_conversation()
        rid = store.new_run(cid, 'Question', config_snapshot={'version': 7})
        store.update(rid, answer=old, sources=SOURCES, status='completed')
        expected = refresh_registered_references(old, SOURCES)
        assert client.get(f'/api/conversations/{cid}').json()['runs'][0]['answer'] == expected
        assert client.get(f'/api/runs/{rid}/export').text == expected
        assert expected in client.get(f'/api/conversations/{cid}/export').text
        with store.connect() as db:
            assert db.execute('select answer from runs where id=?', (rid,)).fetchone()[0] == old
