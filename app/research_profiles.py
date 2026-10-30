"""Named execution profiles, independent of model suppliers and credentials."""
import copy

DEFAULT_ID = 'default'
DEFAULT = {'iteration_tier': 'deep', 'max_iterations': 200, 'keep_tool_result': -1,
           'context_compress_limit': 5, 'memory_mode': 'strict', 'preset': 'demo', 'search_count': 20}
FIELDS = tuple(DEFAULT)


def expand(doc):
    builtin = {'id': DEFAULT_ID, 'name': '默认配置', 'builtin': True, **DEFAULT}
    if 'research_profiles' not in doc:
        # Preserve existing choices as a named profile on upgrade.
        old = {'iteration_tier': 'standard', 'max_iterations': 50, 'keep_tool_result': -1,
               'context_compress_limit': 0, 'memory_mode': 'strict', 'preset': 'demo',
               'search_count': doc.get('web', {}).get('search_count', 10)}
        old.update({k: v for k, v in doc.get('research', {}).items() if k in FIELDS})
        doc['research_profiles'] = {}
        doc['active_research_profile'] = DEFAULT_ID
        if old != DEFAULT:
            doc['research_profiles']['legacy'] = {'id': 'legacy', 'name': '原研究配置', 'builtin': False, **old}
            doc['active_research_profile'] = 'legacy'
    doc['research_profiles'] = {DEFAULT_ID: builtin, **{k: v for k, v in doc['research_profiles'].items() if k != DEFAULT_ID}}
    active = doc.get('active_research_profile', DEFAULT_ID)
    if active not in doc['research_profiles']: active = DEFAULT_ID
    doc['active_research_profile'] = active
    profile = doc['research_profiles'][active]
    doc['research'] = {k: copy.deepcopy(profile[k]) for k in FIELDS}
    # Compatibility projection for old clients and existing run snapshots.
    doc['web']['search_count'] = profile['search_count']
    return doc


def validate(value, old=None):
    values = {**DEFAULT, **(old or {}), **value}
    for key, label in [('max_iterations', '迭代上限'), ('search_count', 'Search 请求结果数')]:
        if type(values[key]) is not int or values[key] < 1: raise ValueError(label + '必须为正整数')
    for key, choices, error in [
        ('keep_tool_result', (-1, 5), '请选择全部保留或 keep5'),
        ('context_compress_limit', (0, 5), '请选择单次研究或 benchmark 重试')]:
        if type(values[key]) is not int or values[key] not in choices: raise ValueError(error)
    if values['memory_mode'] not in ('strict', 'followup'): raise ValueError('提问模式无效')
    if values['preset'] not in ('demo', 'keep5_max200'): raise ValueError('预设无效')
    tiers = {'quick': 10, 'standard': 50, 'deep': 200}
    if values['iteration_tier'] not in (*tiers, 'custom'): raise ValueError('档位无效')
    if values['iteration_tier'] in tiers and tiers[values['iteration_tier']] != values['max_iterations']:
        raise ValueError('迭代次数与档位不一致，请选择自定义档位')
    return {k: values[k] for k in FIELDS}
