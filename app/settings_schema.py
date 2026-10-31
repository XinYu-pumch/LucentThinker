"""Supplier-owned credentials; model IDs remain stable across schema migration."""
import copy
from urllib.parse import urlsplit
from .llm_providers import registry
from . import research_profiles

CONNECTION_FIELDS = ('base_url', 'api_key', 'provider')
PROJECTION_FIELDS = (*CONNECTION_FIELDS, 'models', 'models_checked_at', 'supplier_name', 'display_name')


def builtins():
    result = {'deepseek': {'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com', 'provider': 'deepseek'}}
    for kind, module in registry.catalog().items():
        result[kind] = {'name': module['name'], 'base_url': module['base_url'], 'provider': kind}
    return result


def unique_name(suppliers, name, exclude=None):
    used = {s['name'].casefold() for sid, s in suppliers.items() if sid != exclude}
    candidate, n = name, 2
    while candidate.casefold() in used:
        candidate = f'{name} ({n})'; n += 1
    return candidate


def retire_fourrouter(doc):
    """Remove the retired built-in configuration from current settings only."""
    suppliers = doc.get('suppliers', {})
    supplier_ids = {sid for sid, supplier in suppliers.items()
                    if supplier.get('provider') == 'fourrouter_argon'}
    profile_ids = {pid for pid, profile in doc['profiles'].items()
                   if profile.get('provider') == 'fourrouter_argon'
                   or profile.get('supplier_id') in supplier_ids}
    for role, pid in doc['active'].items():
        if pid in profile_ids:
            doc['active'][role] = ''
    if doc['web'].get('credential_profile') in profile_ids:
        doc['web']['credential_profile'] = None
    for pid in profile_ids:
        del doc['profiles'][pid]
    for sid in supplier_ids:
        del suppliers[sid]
    return bool(supplier_ids or profile_ids)


def expand(document):
    doc = copy.deepcopy(document)
    retire_fourrouter(doc)
    templates = builtins()
    if 'suppliers' not in doc:
        doc['suppliers'] = {}
        groups = {}
        for pid, p in doc['profiles'].items():
            original_kind = p.get('provider', 'openai')
            kind = original_kind
            if kind == 'deepseek' and urlsplit(p['base_url']).hostname != 'api.deepseek.com':
                kind = 'openai'
            key = (kind, p['base_url'], p.get('api_key', ''))
            sid = next((s for s in groups.get(key, []) if p['model'] not in {
                q['model'] for q in doc['profiles'].values() if q.get('supplier_id') == s}), None)
            if sid is None:
                builtin_id = 'builtin_' + kind
                use_builtin = kind in templates and builtin_id not in doc['suppliers'] and p['base_url'] == templates[kind]['base_url']
                sid = builtin_id if use_builtin else 'supplier_' + pid
                name = templates[kind]['name'] if use_builtin else p['name']
                supplier = {'id': sid, 'name': unique_name(doc['suppliers'], name), 'provider': kind,
                            'base_url': p['base_url'], 'api_key': p.get('api_key', ''),
                            'builtin': use_builtin, 'catalog': copy.deepcopy(p.get('models', []))}
                if kind != original_kind:
                    supplier['migration_note'] = '旧配置曾启用 DeepSeek 扩展；此地址为普通 OpenAI 兼容供应商，现仅发送通用参数。原设置已备份。'
                if key in groups:
                    supplier['migration_note'] = '为保留同名模型的独立参数与并发额度，此旧配置单独迁移为供应商。'
                doc['suppliers'][sid] = supplier
                groups.setdefault(key, []).append(sid)
            p['supplier_id'] = sid
            if kind == 'openai':
                p['thinking'] = p['reasoning_effort'] = None
    for kind, template in templates.items():
        sid = 'builtin_' + kind
        if sid not in doc['suppliers']:
            doc['suppliers'][sid] = {'id': sid, **template, 'name': unique_name(doc['suppliers'], template['name']),
                                     'api_key': '', 'builtin': True, 'catalog': []}
    doc['version'] = 4
    doc['thinking_schema'] = 1
    for p in doc['profiles'].values():
        supplier = doc['suppliers'][p['supplier_id']]
        p.update({k: supplier[k] for k in CONNECTION_FIELDS})
        p['models'] = copy.deepcopy(supplier.get('catalog', []))
        p['models_checked_at'] = supplier.get('models_checked_at')
        p['supplier_name'] = supplier['name']
        p['display_name'] = supplier['name'] + ' / ' + p['model']
    return research_profiles.expand(doc)


def compact(document):
    doc = expand(document)
    for p in doc['profiles'].values():
        for key in PROJECTION_FIELDS:
            p.pop(key, None)
    return doc
