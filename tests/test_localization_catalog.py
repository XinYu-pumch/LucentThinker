"""Guard application-owned UI metadata and static backend errors against translation gaps."""
import ast
import json
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'app'
source = (APP / 'static/i18n-en.js').read_text()
CATALOG = json.loads(source[source.index('{'):].rstrip().removesuffix(';'))
HAN = re.compile('[\u4e00-\u9fff]')


def assert_translated(text, where):
    if HAN.search(text):
        assert text in CATALOG, (where, text)
        assert not HAN.search(CATALOG[text]), (where, text)


def test_static_backend_errors_and_progress_messages_have_english_entries():
    for path in APP.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            candidates = []
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                candidates = node.exc.args
            elif isinstance(node, ast.keyword) and node.arg in ('text', 'error', 'message', 'note'):
                candidates = [node.value]
            for value in candidates:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    assert_translated(value.value, path)


def test_provider_and_thinking_metadata_has_english_entries():
    def walk(value, path):
        if isinstance(value, dict):
            for child in value.values():
                walk(child, path)
        elif isinstance(value, list):
            for child in value:
                walk(child, path)
        elif isinstance(value, str):
            assert_translated(value, path)
    for path in [APP / 'thinking_presets.json', *(APP / 'llm_providers').rglob('manifest.json')]:
        walk(json.loads(path.read_text()), path)
