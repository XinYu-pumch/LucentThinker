"""Go's four native protocols, including round-trip research tool messages.

Transport, credentials, retry and cancellation belong to the shared HTTP client.
Only this optional module knows Go URLs, headers and per-model parameters.
"""
import copy
import json
from pathlib import Path
from app.llm_protocols import Decoder, normalize_usage, prepare_body

MANIFEST = json.loads(Path(__file__).with_name('manifest.json').read_text(encoding='utf-8'))
BASE = MANIFEST['base_url']
USER_AGENT = 'LucentThinker/0.1.0'


def public_config():
    return {'name': 'OpenCode Go', 'base_url': BASE,
            'models': [{'id': k, **v} for k, v in MANIFEST['models'].items()],
            'template': {'name': 'OpenCode Go', 'base_url': BASE, 'model': 'deepseek-v4.1-flash',
                         'provider': 'opencode_go', 'reasoning_effort': None,
                         'temperature': None, 'top_p': None, 'concurrency': 1},
            'checked_at': MANIFEST['checked_at']}


def route(model):
    if model not in MANIFEST['models']:
        raise ValueError('OpenCode Go 尚未登记此模型的官方协议，请刷新列表或更新模块。')
    return MANIFEST['models'][model]


def validate(profile):
    if profile['base_url'] != BASE:
        raise ValueError('OpenCode Go 地址由模块管理，请使用内置地址。')
    if profile.get('model'):
        spec = route(profile['model'])
        if profile.get('go_reasoning') is not None:
            validate_choice(profile['model'], profile['go_reasoning'], profile.get('reasoning_budget'))
            return
        if profile.get('reasoning_effort') and profile['reasoning_effort'] not in spec.get('reasoning_levels', []):
            raise ValueError('此 Go 模型不支持所选思考强度，请选择服务端默认或有效档位。')
        if profile.get('thinking') is not None and profile['thinking'] not in spec.get('thinking_modes', []):
            raise ValueError('此 Go 模型不支持所选思考模式。')


def normalize_profile(profile):
    """Apply only registered model defaults, including legacy unset values."""
    validate(profile)
    if profile.get('go_reasoning') is not None:
        return {'thinking': None, 'reasoning_effort': None}
    spec = MANIFEST['models'].get(profile.get('model'), {})
    return {'thinking': profile.get('thinking') or spec.get('default_thinking'),
            'reasoning_effort': profile.get('reasoning_effort') or spec.get('default_reasoning_effort')}


def headers(session):
    return {'User-Agent': USER_AGENT, 'x-opencode-session': session}


def catalog_request(session):
    return BASE + '/' + MANIFEST['catalog_path'], headers(session)


def filter_models(data):
    known = MANIFEST['models']
    items = data.get('data', [])
    return {**data, 'data': [{**m, **known[m['id']]} for m in items
                             if isinstance(m, dict) and m.get('id') in known],
            'unmapped_models': [m['id'] for m in items if isinstance(m, dict) and m.get('id') not in known]}


def capabilities(profile):
    spec = MANIFEST['models'].get(profile.get('model'), {})
    return {'max_tokens': spec.get('max_output_tokens') if spec.get('protocol') == 'messages' else None,
            'context_window': spec.get('context_window')}


def _legacy_prepare(settings, payload, session):
    params = normalize_profile({'base_url': settings.base_url, 'model': settings.model,
                                'thinking': settings.thinking, 'reasoning_effort': settings.reasoning_effort})
    spec = route(settings.model)
    protocol = spec['protocol']
    body, head = prepare_body(settings, payload, protocol, spec.get('max_output_tokens'))
    head.update(headers(session))
    level = params['reasoning_effort']
    if spec.get('thinking_modes'):
        body['thinking'] = {'type': params['thinking']}
        if params['thinking'] == 'disabled':
            level = None
        else:
            body.pop('temperature', None)
    if level:
        if protocol == 'chat':
            body['reasoning_effort'] = level
            if settings.model.startswith('deepseek-'):
                body['thinking'] = {'type': 'enabled'}
                body.pop('temperature', None)
        elif protocol == 'responses':
            body['reasoning'] = {'effort': level}
        elif protocol == 'messages':
            body['thinking'] = {'type': 'adaptive' if settings.model.startswith('claude-') else 'enabled'}
            body['output_config'] = {'effort': level}
        else:
            body.setdefault('generationConfig', {}).setdefault('thinkingConfig', {})['thinkingLevel'] = level
    if protocol == 'google':
        body.setdefault('generationConfig', {}).setdefault('thinkingConfig', {})['includeThoughts'] = True
    return {'url': spec.get('endpoint') or BASE + '/' + spec['path'], 'headers': head, 'body': body, 'protocol': protocol}


def merge(target, patch):
    for key, value in patch.items():
        if isinstance(value, dict):
            merge(target.setdefault(key, {}), value)
        else:
            target[key] = copy.deepcopy(value)


def validate_choice(model, choice, budget):
    spec = route(model).get('reasoning', {})
    if not isinstance(choice, str) or (choice and choice not in spec.get('options', {})):
        raise ValueError('此 Go 模型不支持所选思考配置，请重新选择')
    if choice == 'budget':
        limits = spec.get('budget', {})
        if type(budget) is not int or budget < limits.get('min', 1) or ('max' in limits and budget > limits['max']):
            raise ValueError('请填写此 Go 模型支持的整数思考 token 预算')


def prepare(settings, payload, session):
    spec = route(settings.model)
    if settings.base_url != BASE:
        raise ValueError('OpenCode Go 地址由模块管理')
    if settings.go_reasoning is None:
        transport = _legacy_prepare(settings, payload, session)
    else:
        validate_choice(settings.model, settings.go_reasoning, settings.reasoning_budget)
        body, head = prepare_body(settings, payload, spec['protocol'], spec.get('max_output_tokens'))
        head.update(headers(session))
        rules = spec.get('reasoning', {})
        merge(body, rules.get('options', {}).get(settings.go_reasoning, {}))
        if settings.go_reasoning == 'budget':
            target = body
            path = rules['budget']['path']
            for key in path[:-1]:
                target = target.setdefault(key, {})
            target[path[-1]] = settings.reasoning_budget
        transport = {'url': spec.get('endpoint') or BASE + '/' + spec['path'],
                     'headers': head, 'body': body, 'protocol': spec['protocol']}
    body = transport['body']
    output = spec.get('reasoning', {}).get('output', {})
    if not (output.get('defaultThinkingType') and body.get('thinking', {}).get('type') == 'disabled'):
        merge(body, output.get('request', {}))
        if output.get('defaultThinkingType'):
            body.setdefault('thinking', {}).setdefault('type', output['defaultThinkingType'])
    return transport
