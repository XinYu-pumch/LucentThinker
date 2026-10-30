"""Safe request diagnostics and explicitly requested, nonpersistent negative probes."""
import copy
from . import llm_thinking
from .provider import ProviderError

PATHS = [('reasoning_effort',), ('generationConfig', 'thinkingConfig', 'thinkingLevel'),
         ('output_config', 'effort'), ('reasoning', 'effort'), ('thinking_budget',),
         ('thinking', 'budget_tokens'), ('thinking', 'type'), ('enable_thinking',)]


def fields(body):
    result = {k: copy.deepcopy(body[k]) for k in ('thinking', 'reasoning', 'reasoning_effort',
        'enable_thinking', 'thinking_budget', 'reasoning_split', 'output_config') if k in body}
    if (body.get('generationConfig') or {}).get('thinkingConfig') is not None:
        result['generationConfig.thinkingConfig'] = copy.deepcopy(body['generationConfig']['thinkingConfig'])
    return result


class Capture:
    def __init__(self):
        self.body, self.protocol, self.endpoint = {}, 'chat', ''

    def start(self, role, purpose, attempt, iteration, payload):
        wire = payload.get('wire_request') or {}
        self.body = copy.deepcopy(wire.get('body', payload))
        self.protocol, self.endpoint = wire.get('protocol', 'chat'), wire.get('url', '')
        return 0

    def chunk(self, *args): pass
    def end(self, *args, **kwargs): pass
    def retry(self, *args): pass
    def emit(self, *args, **kwargs): pass

    def report(self, settings, response):
        text = response.message.get('reasoning_content') or ''
        return {'parameters': fields(self.body), 'protocol': self.protocol,
                'endpoint': self.endpoint or settings.base_url + '/chat/completions',
                'output': llm_thinking.output_info(settings), 'text': text, 'characters': len(text),
                'reasoning_tokens': (response.usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
                'note': '只统计实际返回的可读文本；token 用量和 HTTP 成功不证明摘要返回或强度生效。'}


async def negative_probe(client, body, messages):
    path = None
    for candidate in PATHS:
        value = body
        for key in candidate:
            value = value.get(key) if isinstance(value, dict) else None
        if value is not None:
            path = candidate
            break
    if path is None:
        return {'status': 'not_applicable', 'message': '当前没有可对照的显式思考参数，未发送额外请求。'}
    def transform(request):
        target = request
        for key in path[:-1]: target = target[key]
        target[path[-1]] = '__invalid_probe__'
    name = '.'.join(path)
    try:
        result = await client.complete(messages, purpose='parameter_probe', max_attempts=1, request_transform=transform)
        status = 'possibly_ignored' if result.finish_reason == 'stop' and (result.message.get('content') or '').strip() else 'inconclusive'
    except ProviderError as exc:
        status = 'validated' if exc.code in (400, 422) and any(k.lower() in str(exc).lower() for k in (name, path[-1])) else 'inconclusive'
    return {'field': name, 'status': status, 'message': {
        'validated': '服务端校验了该参数；不证明合法档位的实际计算强度。',
        'possibly_ignored': '错误参数仍返回正文，可能被忽略、移除或替换。',
        'inconclusive': '本次对照无法判断参数是否被校验。'}[status]}
