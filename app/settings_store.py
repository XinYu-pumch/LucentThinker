"""Atomic project-local settings, explicit key reveal, and immutable per-run selection."""
import copy
import json
import os
import threading
import time
import uuid
from . import config, settings_schema, research_profiles, llm_thinking
from .llm_providers import registry

SETTINGS_FILE = config.DATA / 'settings.json'
LOCK = threading.RLock()
DISCOVERED = {}

DEEPSEEK_TEMPLATE = {
    'name': '默认 DeepSeek', 'base_url': 'https://api.deepseek.com',
    'model': 'deepseek-flash', 'provider': 'deepseek',
    'thinking': 'enabled', 'reasoning_effort': 'high',
    'temperature': None, 'top_p': None, 'concurrency': 1,
}


def default_document():
    return {
        'version': 4,
        'thinking_schema': 1,
        'suppliers': {},
        'profiles': {},
        'active': {'main': '', 'summary': ''},
        'web': {'api_key': config.API_KEY, 'credential_profile': None, 'search_count': 20},
        'research': copy.deepcopy(research_profiles.DEFAULT),
    }


def remember(doc):
    doc['web'].setdefault('search_count', 10)
    for item in doc.get('suppliers', {}).values():
        config.register_secret(item.get('api_key', ''))
    for profile in doc['profiles'].values():
        profile.setdefault('concurrency', 1)
        config.register_secret(profile.get('api_key', ''))
    config.register_secret(doc['web'].get('api_key', ''))
    return doc


def load():
    with LOCK:
        return remember(settings_schema.expand(json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else default_document()))


def write(doc):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_name(SETTINGS_FILE.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(settings_schema.compact(doc), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, SETTINGS_FILE)
        os.chmod(SETTINGS_FILE, 0o600)
    finally:
        if tmp.exists(): tmp.unlink()
    remember(settings_schema.expand(doc))


def ensure():
    with LOCK:
        raw = json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else None
        retired = raw is not None and settings_schema.retire_fourrouter(copy.deepcopy(raw))
        if raw is not None and (retired or raw.get('version', 3) < 4 or 'research_profiles' not in raw or raw.get('thinking_schema', 0) < 1):
            backup = SETTINGS_FILE.parent / 'backups' / ('settings-v' + str(raw.get('version', 3)) + '-' + str(time.time_ns()) + '.json')
            backup.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f: f.write(SETTINGS_FILE.read_bytes())
            write(load())
        elif not SETTINGS_FILE.exists(): write(load())


def public(doc=None):
    doc = settings_schema.expand(doc or load())
    web_configured = bool(web_key(doc))
    for p in doc['profiles'].values():
        p['configured'] = bool(p.pop('api_key', ''))
        try:
            p['capabilities'] = to_model({**p, 'api_key': ''}).public()
        except ValueError as exc:
            p['capabilities'] = {'unavailable': True, 'error': str(exc)}
    doc['web']['configured'] = web_configured
    doc['web']['independent_configured'] = bool(doc['web'].get('api_key'))
    doc['web'].pop('api_key', None)
    for supplier in doc['suppliers'].values():
        supplier['configured'] = bool(supplier.pop('api_key', ''))
        try:
            adapter = registry.get(supplier['provider'])
            supplier['unavailable'] = False
            supplier['module'] = adapter.public_config() if adapter else None
        except ValueError:
            supplier['unavailable'] = True
    doc['templates'] = {'deepseek': copy.deepcopy(DEEPSEEK_TEMPLATE)}
    doc['providers'] = registry.catalog()
    doc['thinking_presets'] = list(llm_thinking.PRESETS.values())
    return config.redact(doc)


def validated_profile(value, old=None):
    old = old or {}
    base = config.normalize_base(value.get('base_url', old.get('base_url', config.BASE_URL)))
    key = value.get('api_key')
    if key is None:
        if old and base != old['base_url']:
            raise ValueError('更换接口地址时请重新输入 API Key，避免将旧凭据发送到新地址。')
        key = old.get('api_key', '')
    config.register_secret(key)
    provider = value.get('provider', old.get('provider', 'openai'))
    adapter = registry.get(provider)
    p = {k: value.get(k, old.get(k)) for k in ('name', 'model', 'thinking', 'reasoning_effort', 'temperature', 'top_p', 'thinking_config', 'go_reasoning', 'reasoning_budget')}
    p.update(id=old.get('id') or uuid.uuid4().hex, base_url=base, api_key=key, provider=provider)
    if provider == 'opencode_go' and 'go_reasoning' not in value and any(value.get(k) is not None for k in ('thinking', 'reasoning_effort')):
        p['go_reasoning'] = None  # Old API clients explicitly editing legacy fields.
    p['concurrency'] = value.get('concurrency', old.get('concurrency', 1))
    if type(p['concurrency']) is not int or p['concurrency'] < 1:
        raise ValueError('模型并发数必须为正整数')
    if not isinstance(p['name'], str) or not p['name'].strip(): raise ValueError('请输入配置名称')
    if not isinstance(p['model'], str): p['model'] = ''
    p['thinking_config'] = llm_thinking.selection(p['thinking_config'])
    if p['thinking_config'] and provider not in llm_thinking.PRESET_PROVIDERS:
        raise ValueError('专用模块使用其自身思考配置，不能叠加普通预设')
    if provider != 'opencode_go' and (p['go_reasoning'] is not None or p['reasoning_budget'] is not None):
        raise ValueError('Go 参数不能用于其他供应商')
    if provider == 'deepseek':
        p['thinking'] = p['thinking'] or 'enabled'
        p['reasoning_effort'] = 'high' if p['reasoning_effort'] is None else p['reasoning_effort']
        if p['thinking'] not in ('enabled', 'disabled') or p['reasoning_effort'] not in ('', 'low', 'high', 'max'):
            raise ValueError('DeepSeek 生成参数无效')
    elif adapter:
        if hasattr(adapter, 'normalize_profile'):
            p.update(adapter.normalize_profile(p))
        else:
            p['thinking'] = None
            p['reasoning_effort'] = p['reasoning_effort'] or getattr(adapter, 'DEFAULT_REASONING_EFFORT', None)
        adapter.validate(p)
    else:
        p['thinking'] = p['reasoning_effort'] = None
    for name in ('temperature', 'top_p'):
        if p[name] is not None:
            p[name] = float(p[name])
            if not 0 <= p[name] <= (2 if name=='temperature' else 1): raise ValueError(name + ' 参数无效')
    p['models'] = copy.deepcopy(DISCOVERED.get((base,key), old.get('models', []) if base == old.get('base_url') and key == old.get('api_key') else []))
    return p


def draft(value):
    doc = load()
    ident = value.get('id')
    if ident and ident not in doc['profiles']: raise ValueError('配置不存在')
    return validated_profile(value, doc['profiles'].get(ident))


def to_model(p):
    metadata = next((m for m in p.get('models', []) if m.get('id') == p.get('model')), {})
    maximum = metadata.get('max_output_tokens')
    if type(maximum) is not int or maximum <= 0: maximum = None
    adapter = registry.get(p['provider'])
    if adapter and hasattr(adapter, 'normalize_profile'):
        p = {**p, **adapter.normalize_profile(p)}
    selected = llm_thinking.selection(p.get('thinking_config'))
    if selected and p['provider'] not in llm_thinking.PRESET_PROVIDERS:
        raise ValueError('专用供应商不能叠加普通预设')
    caps = adapter.capabilities(p) if adapter else {'max_tokens':maximum,'context_window':metadata.get('context_window')}
    if selected:
        caps['max_tokens'] = llm_thinking.PRESETS[selected['preset']].get('maxOutputTokens')
    return config.ModelSettings(model=p.get('model', ''), base_url=p['base_url'], api_key=p.get('api_key', ''),
        credential_source='saved_supplier', profile_id=p['id'], profile_name=p.get('display_name', p['name']),
        supplier_id=p.get('supplier_id',''), supplier_name=p.get('supplier_name',''),
        provider=p['provider'], concurrency=p.get('concurrency', 1),
        max_tokens=caps['max_tokens'], context_window=caps['context_window'], thinking=p.get('thinking'),
        reasoning_effort=p.get('reasoning_effort'), temperature=p.get('temperature'), top_p=p.get('top_p'),
        thinking_config=selected, go_reasoning=p.get('go_reasoning'), reasoning_budget=p.get('reasoning_budget'))


def save_profile(value, role=None):
    with LOCK:
        doc = load()
        if value.get('id') and value['id'] not in doc['profiles']: raise ValueError('配置不存在')
        p = validated_profile(value, doc['profiles'].get(value.get('id')))
        if not p['model'].strip(): raise ValueError('请选择或输入模型 ID')
        old = doc['profiles'].get(p['id'])
        sid = old['supplier_id'] if old else 'supplier_' + p['id']
        if not old:
            doc['suppliers'][sid] = {'id':sid, 'name':settings_schema.unique_name(doc['suppliers'],p['name']), 'builtin':False}
        doc['suppliers'][sid].update({k:p[k] for k in settings_schema.CONNECTION_FIELDS})
        doc['suppliers'][sid]['catalog'] = p.get('models',[])
        p['supplier_id'] = sid
        doc['profiles'][p['id']] = p
        if role:
            if role not in ('main', 'summary'): raise ValueError('角色无效')
            doc['active'][role] = p['id']
        write(doc)
        from .model_queue import update_profile_limit
        update_profile_limit(p['id'], p['concurrency'])
        return p['id']


def cache_models(profile, models):
    """Only update a still-matching saved profile; unsaved credentials never overwrite it."""
    with LOCK:
        doc = load()
        DISCOVERED[(profile['base_url'],profile['api_key'])] = config.redact(models)
        old = doc['profiles'].get(profile['id'])
        if old and old['base_url'] == profile['base_url'] and old['api_key'] == profile['api_key']:
            supplier = doc['suppliers'][old['supplier_id']]
            supplier['catalog'] = config.redact(models)
            supplier['models_checked_at'] = time.time()
            write(doc)


def activate(role, ident):
    with LOCK:
        doc = load()
        if role not in doc['active'] or ident not in doc['profiles']: raise ValueError('角色或配置不存在')
        doc['active'][role] = ident
        write(doc)


def select_models(main, summary):
    """Change both role bindings atomically without editing provider credentials."""
    with LOCK:
        doc = load()
        if any(ident not in doc['profiles'] for ident in (main, summary)):
            raise ValueError('请选择已保存的模型配置')
        doc['active'] = {'main': main, 'summary': summary}
        write(doc)


def delete_profile(ident):
    with LOCK:
        doc = load()
        if ident not in doc['profiles']: raise ValueError('配置不存在')
        if ident in doc['active'].values() or ident == doc['web'].get('credential_profile'):
            raise ValueError('此配置正在被角色或网页服务使用，请先选择替代配置。')
        del doc['profiles'][ident]
        write(doc)


def web_key(doc=None):
    doc = doc or load()
    ident = doc['web'].get('credential_profile')
    if ident and doc['profiles'][ident].get('provider') not in ('openai', 'deepseek'):
        raise ValueError('网页服务需要 DeepSeek 凭据，不能复用专用供应商的 Key。')
    return config.register_secret(doc['profiles'][ident]['api_key'] if ident else doc['web'].get('api_key', ''))


def save_web(value):
    with LOCK:
        doc = load()
        count = value.get('search_count', doc['web']['search_count'])
        if type(count) is not int or count < 1:
            raise ValueError('Search 请求结果数必须为正整数')
        ident = value.get('credential_profile')
        if ident and ident not in doc['profiles']: raise ValueError('凭据配置不存在')
        if ident and doc['profiles'][ident].get('provider') not in ('openai', 'deepseek'):
            raise ValueError('Search / Fetch 请单独配置 DeepSeek Key，不能复用 Go 等专用供应商凭据。')
        doc['web']['credential_profile'] = ident
        if count != doc['research']['search_count']:
            update_active_research(doc, {'search_count': count})
        if value.get('api_key') is not None: doc['web']['api_key'] = config.register_secret(value['api_key'])
        write(doc)


def save_research(value):
    with LOCK:
        doc = load()
        update_active_research(doc, value)
        write(doc)


def research_profile(doc, ident, editable=False):
    profile = doc['research_profiles'].get(ident)
    if not profile: raise ValueError('研究执行配置不存在')
    if editable and profile['builtin']: raise ValueError('默认配置固定保留；请新增配置后修改')
    return profile


def research_name(doc, name, exclude=None):
    if not isinstance(name, str) or not name.strip(): raise ValueError('请输入研究执行配置名称')
    name = name.strip()
    if any(p['name'].casefold() == name.casefold() for pid, p in doc['research_profiles'].items() if pid != exclude):
        raise ValueError('研究执行配置名称已存在')
    return name


def update_active_research(doc, value):
    """Compatibility for old settings endpoints; never overwrite the builtin."""
    pid = doc['active_research_profile']
    old = research_profile(doc, pid)
    values = research_profiles.validate(value, old)
    if old['builtin']:
        if values == research_profiles.DEFAULT: return
        pid = uuid.uuid4().hex
        old = {'id': pid, 'name': settings_schema.unique_name(doc['research_profiles'], '自定义研究'), 'builtin': False}
        doc['active_research_profile'] = pid
    doc['research_profiles'][pid] = {**old, **values}
    research_profiles.expand(doc)


def save_research_profile(value, ident=None):
    with LOCK:
        doc = load()
        old = research_profile(doc, ident, editable=True) if ident else {}
        name = research_name(doc, value.get('name', old.get('name')), ident)
        values = research_profiles.validate(value, old)
        ident = ident or uuid.uuid4().hex
        doc['research_profiles'][ident] = {'id': ident, 'name': name, 'builtin': False, **values}
        doc['active_research_profile'] = ident
        write(doc)
        return ident


def rename_research_profile(ident, name):
    with LOCK:
        doc = load()
        profile = research_profile(doc, ident, editable=True)
        profile['name'] = research_name(doc, name, ident)
        write(doc)


def activate_research_profile(ident):
    with LOCK:
        doc = load()
        research_profile(doc, ident)
        doc['active_research_profile'] = ident
        write(doc)


def delete_research_profile(ident):
    with LOCK:
        doc = load()
        research_profile(doc, ident, editable=True)
        del doc['research_profiles'][ident]
        if doc['active_research_profile'] == ident: doc['active_research_profile'] = research_profiles.DEFAULT_ID
        write(doc)


def supplier(ident, doc=None):
    doc = doc or load()
    if ident not in doc['suppliers']: raise ValueError('供应商不存在')
    return doc['suppliers'][ident]


def save_supplier(value, ident=None):
    with LOCK:
        doc = load()
        old = supplier(ident, doc) if ident else {}
        name = value.get('name', old.get('name', '')).strip()
        if not name: raise ValueError('请输入供应商名称')
        if any(s['name'].casefold() == name.casefold() and sid != ident for sid,s in doc['suppliers'].items()):
            raise ValueError('供应商名称已存在，请使用不同名称')
        kind = old.get('provider', 'openai')
        module = registry.get(kind)
        base = value.get('base_url', old.get('base_url','')).strip()
        if base: base = config.normalize_base(base)
        fixed_base = module.BASE if module else 'https://api.deepseek.com' if kind == 'deepseek' else None
        allowed = getattr(module, 'BASE_URLS', [fixed_base])
        if fixed_base and base not in allowed: raise ValueError('内置模块的接口地址固定，请选择登记的官方地址')
        key = value.get('api_key')
        if key is None:
            if old and base != old['base_url'] and old.get('api_key'):
                raise ValueError('更换地址时请重新输入 Key，或点击清空 Key，避免旧凭据发往新地址')
            key = old.get('api_key','')
        ident = ident or 'supplier_' + uuid.uuid4().hex
        item = {**old, 'id':ident, 'name':name, 'provider':kind, 'base_url':base,
                'api_key':config.register_secret(key), 'builtin':old.get('builtin',False)}
        if base != old.get('base_url') or key != old.get('api_key'):
            item['catalog'] = []; item.pop('models_checked_at',None)
        doc['suppliers'][ident] = item
        write(doc)
        return ident


def supplier_profile(ident, model_id=None, values=None, doc=None):
    doc = doc or load(); s = supplier(ident, doc)
    if not s['base_url']: raise ValueError('请先填写并保存供应商接口地址')
    module = registry.get(s['provider'])
    old = doc['profiles'].get(model_id) if model_id else None
    if model_id and (not old or old['supplier_id'] != ident): raise ValueError('模型不属于此供应商')
    default_model = module.public_config()['template']['model'] if module else ''
    p = validated_profile({**{k:s[k] for k in settings_schema.CONNECTION_FIELDS},
        'name':old['name'] if old else default_model or '模型目录', 'model':old['model'] if old else default_model,
        **(values or {})}, old)
    p.update(supplier_id=ident, supplier_name=s['name'], models=copy.deepcopy(s.get('catalog',[])))
    p['display_name'] = s['name'] + ' / ' + p['model']
    return p


def cache_supplier_models(ident, probe, models):
    with LOCK:
        doc = load(); s = supplier(ident,doc)
        if any(s[k] != probe[k] for k in settings_schema.CONNECTION_FIELDS):
            raise ValueError('拉取期间供应商配置已变化，请重新刷新模型列表')
        unique = {m['id']:m for m in models if isinstance(m,dict) and isinstance(m.get('id'),str) and m['id'].strip()}
        s['catalog'] = config.redact(list(unique.values())); s['models_checked_at'] = time.time()
        write(doc)
        return s['catalog']


def add_supplier_models(ident, model_names, manual=False):
    with LOCK:
        doc = load(); s = supplier(ident,doc)
        known = {m['id'] for m in s.get('catalog',[])}
        module = registry.get(s['provider'])
        if module: known.update(m['id'] for m in module.public_config()['models'])
        existing = {p['model'] for p in doc['profiles'].values() if p['supplier_id']==ident}
        added=[]
        for name in dict.fromkeys(model_names):
            if not isinstance(name, str) or not name.strip(): raise ValueError('请输入有效模型 ID')
            allow_manual = not module or module.public_config().get('allow_manual_models')
            if name not in known and not (manual and allow_manual): raise ValueError('模型不在已拉取列表中，请先刷新模型列表')
            if name in existing: continue
            values = {'name':name, 'model':name}
            preset = module.public_config().get('default_thinking_preset') if module else None
            if preset: values['thinking_config'] = llm_thinking.initial(preset)
            if s['provider'] == 'opencode_go': values['go_reasoning'] = ''
            if s['provider'] == 'deepseek': values.update(thinking='enabled', reasoning_effort='')
            p=supplier_profile(ident, values=values,doc=doc)
            doc['profiles'][p['id']] = p; added.append(p['id'])
        write(doc)
        return added


def update_supplier_model(ident, model_id, values):
    with LOCK:
        doc=load(); p=supplier_profile(ident,model_id,values,doc)
        doc['profiles'][model_id]=p; write(doc)
        from .model_queue import update_profile_limit
        update_profile_limit(model_id,p['concurrency'])


def remove_supplier_models(doc, identifiers):
    identifiers=set(identifiers)
    if doc['web'].get('credential_profile') in identifiers:
        doc['web']['api_key']=web_key(doc)
        doc['web']['credential_profile']=None
    for role, pid in doc['active'].items():
        if pid in identifiers: doc['active'][role]=''
    for pid in identifiers: del doc['profiles'][pid]


def delete_supplier_model(ident, model_id):
    with LOCK:
        doc=load(); supplier(ident,doc)
        p=doc['profiles'].get(model_id)
        if not p or p['supplier_id'] != ident: raise ValueError('模型不属于此供应商')
        remove_supplier_models(doc,[model_id]); write(doc)


def delete_supplier(ident):
    with LOCK:
        doc=load(); s=supplier(ident,doc)
        if s['builtin']: raise ValueError('内置供应商保留在侧栏；可清空 Key 或按 README 停用可拆卸模块')
        remove_supplier_models(doc,[p['id'] for p in doc['profiles'].values() if p['supplier_id']==ident])
        del doc['suppliers'][ident]; write(doc)
