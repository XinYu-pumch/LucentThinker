"""Optional adapters are explicitly registered local code, never guessed from URLs."""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
_loaded = {}


def enabled():
    path = ROOT / 'registry.json'
    return json.loads(path.read_text()).get('providers', []) if path.exists() else []


def get(ident):
    if ident in ('openai', 'deepseek'):
        return None
    if not re.fullmatch(r'[a-z][a-z0-9_]*', ident or ''):
        raise ValueError('无效的供应商模块标识')
    path = ROOT / ident / 'adapter.py'
    manifest = path.with_name('manifest.json')
    if ident not in enabled() or not path.is_file() or not manifest.is_file():
        raise ValueError(f'供应商模块 {ident} 已停用或移除，请选择其他模型配置。')
    stamp = (str(path), path.stat().st_mtime_ns, manifest.stat().st_mtime_ns)
    if stamp not in _loaded:
        spec = importlib.util.spec_from_file_location('LucentThinker_provider_' + ident, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _loaded[stamp] = module
    return _loaded[stamp]


def catalog():
    result = {}
    for ident in enabled():
        try:
            module = get(ident)
            result[ident] = module.public_config()
        except (ValueError, OSError):
            continue
    return result
