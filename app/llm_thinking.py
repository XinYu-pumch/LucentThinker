"""Explicit per-model presets, ported from ScholarNoteLM; no name-based routing."""
import copy
import json
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from . import config, llm_protocols

PRESETS = {p['id']: p for p in json.loads(Path(__file__).with_name('thinking_presets.json').read_text())}
Decoder = llm_protocols.Decoder
PRESET_PROVIDERS = {"openai", "z_ai", "moonshot", "mimo", "qwen", "grok"}


def selection(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {'preset', 'level', 'output', 'budget'}:
        raise ValueError('模型思考预设格式无效')
    preset = PRESETS.get(value.get('preset')) if isinstance(value.get('preset'), str) else None
    if not preset:
        raise ValueError('思考预设不可用，请重新选择')
    level, output = value.get('level', preset['defaultLevel']), value.get('output', 'default')
    if level not in preset['levels'] or output not in preset['output']['modes']:
        raise ValueError('此思考预设不支持所选档位或输出方式')
    result = {'preset': preset['id'], 'level': level, 'output': output}
    if level == 'budget':
        spec, budget = preset['budget'], value.get('budget')
        if type(budget) is not int or not spec['min'] <= budget <= spec['max']:
            raise ValueError('请填写此预设支持的整数思考 token 预算')
        result['budget'] = budget
    return result


def initial(preset_id):
    p = PRESETS[preset_id]
    return {'preset': p['id'], 'level': p['defaultLevel'], 'output': p['output'].get('defaultMode', 'default')}


def endpoint(base, model, protocol):
    base = config.normalize_base(base)
    if protocol == 'chat':
        return base + '/chat/completions'
    parts = urlsplit(base)
    path = parts.path.rstrip('/')
    if protocol in ('messages', 'responses'):
        path = path.removesuffix('/messages').removesuffix('/responses') + '/' + protocol
        return urlunsplit((parts.scheme, parts.netloc, path, '', ''))
    if path.endswith('/v1beta/openai'):
        path = path.removesuffix('/openai')
    elif path.endswith('/v1'):
        path = path[:-3] + '/v1beta'
    elif not path.endswith('/v1beta'):
        raise ValueError('Gemini 原生预设地址须以 /v1 或 /v1beta 结尾，可保留中转前缀')
    path += '/models/' + quote(model.removeprefix('models/'), safe='') + ':streamGenerateContent'
    return urlunsplit((parts.scheme, parts.netloc, path, 'alt=sse', ''))


def prepare(settings, payload, session=None):
    if settings.provider not in PRESET_PROVIDERS:
        raise ValueError('此专用供应商不能使用普通思考预设')
    selected = selection(settings.thinking_config)
    preset = PRESETS[selected['preset']] if selected else None
    protocol = preset['protocol'] if preset else 'chat'
    body, headers = llm_protocols.prepare_body(settings, payload, protocol, (preset or {}).get('maxOutputTokens'))
    if preset:
        level = selected['level']
        if protocol == 'google':
            body.setdefault('generationConfig', {})['thinkingConfig'] = {
                'thinkingLevel': level, 'includeThoughts': selected['output'] != 'off'}
        else:
            body.update(copy.deepcopy(preset['options'][level]))
            if level == 'budget':
                body[preset['budget']['field']] = selected['budget']
        if protocol == 'messages':
            if settings.api_key:
                headers['x-api-key'] = settings.api_key
            if selected['output'] != 'default':
                body['thinking']['display'] = 'summarized' if selected['output'] == 'summary' else 'omitted'
        if preset.get('omitTemperature'):
            body.pop('temperature', None)
    return {'url': endpoint(settings.base_url, settings.model, protocol), 'headers': headers,
            'body': body, 'protocol': protocol}


def output_info(settings):
    if settings.thinking_config:
        return copy.deepcopy(PRESETS[selection(settings.thinking_config)['preset']]['output'])
    if settings.provider == 'opencode_go':
        from .llm_providers import registry
        return copy.deepcopy(registry.get(settings.provider).route(settings.model).get('reasoning', {}).get('output', {}))
    return {'kind': 'summary' if settings.provider == 'fourrouter_argon' else 'provider_defined'}
