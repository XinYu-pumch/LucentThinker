"""Removable 4router Argon adapter; independent of the OpenCode Go module."""
import copy
import json
import uuid
from pathlib import Path

MANIFEST = json.loads(Path(__file__).with_name('manifest.json').read_text())
BASE, MODEL = MANIFEST['base_url'], MANIFEST['model']
DEFAULT_REASONING_EFFORT = MANIFEST['default_reasoning_effort']


def public_config():
    return {'name': MANIFEST['name'], 'base_url': BASE, 'fixed_model': MODEL,
            'default_reasoning_effort': DEFAULT_REASONING_EFFORT,
            'reasoning_source': MANIFEST['reasoning_source'],
            'models': [{'id': MODEL, 'protocol': 'google', 'reasoning_levels': MANIFEST['reasoning_levels']}],
            'template': {'name': MANIFEST['name'], 'base_url': BASE, 'model': MODEL,
                         'provider': 'fourrouter_argon', 'reasoning_effort': DEFAULT_REASONING_EFFORT,
                         'temperature': None, 'top_p': None, 'concurrency': 1},
            'checked_at': MANIFEST['checked_at']}


def validate(profile):
    if profile['base_url'] != BASE or profile.get('model') != MODEL:
        raise ValueError('4router Argon 模块固定使用内置地址和 gemini-4-argon。')
    if (profile.get('reasoning_effort') or DEFAULT_REASONING_EFFORT) not in MANIFEST['reasoning_levels']:
        raise ValueError('4router Argon 思考档位仅支持 low、medium、high。')


def capabilities(profile):
    return {'max_tokens': None, 'context_window': None}


def catalog_request(session):
    return MANIFEST['catalog_path'], {}


def filter_models(data):
    metadata = public_config()['models'][0]
    return {**data, 'data': [{**m, **metadata} for m in data.get('data', [])
                            if isinstance(m, dict) and m.get('id') == MODEL]}


def text(message):
    value = message.get('content')
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('4router Argon 模块目前支持文本与工具消息。')
    return value


def prepare(settings, payload, session):
    validate({'base_url': settings.base_url, 'model': settings.model, 'reasoning_effort': settings.reasoning_effort})
    body, system, names = {'contents': []}, [], {}
    for message in payload['messages']:
        role = message['role']
        if role == 'system':
            system.append({'text': text(message)})
            continue
        native_role = 'model' if role == 'assistant' else 'user'
        if role == 'tool':
            name, ident = names[message['tool_call_id']]
            answer = {'name': name, 'response': {'result': text(message)}}
            if ident:
                answer['id'] = ident
            parts = [{'functionResponse': answer}]
        else:
            saved = message.get('_provider_native') or {}
            if role == 'assistant' and saved.get('provider') == 'fourrouter_argon' and saved.get('model') == MODEL:
                parts = copy.deepcopy(saved['items'])
            else:
                parts = [{'text': text(message)}] if text(message) else []
                parts += [{'functionCall': {'name': call['function']['name'], 'args': json.loads(call['function']['arguments'])}}
                          for call in message.get('tool_calls', [])]
            native_calls = [p['functionCall'] for p in parts if 'functionCall' in p]
            for i, call in enumerate(message.get('tool_calls', [])):
                names[call['id']] = (call['function']['name'], native_calls[i].get('id'))
        if parts:
            if body['contents'] and body['contents'][-1]['role'] == native_role:
                body['contents'][-1]['parts'].extend(parts)
            else:
                body['contents'].append({'role': native_role, 'parts': parts})
    if system:
        body['systemInstruction'] = {'parts': system}
    if payload.get('tools'):
        body['tools'] = [{'functionDeclarations': [
            {'name': t['function']['name'], 'description': t['function'].get('description', ''),
             'parametersJsonSchema': copy.deepcopy(t['function']['parameters'])} for t in payload['tools']]}]
    generation = {'thinkingConfig': {'thinkingLevel': settings.reasoning_effort or DEFAULT_REASONING_EFFORT,
                                     'includeThoughts': True}}
    for source, target in (('temperature', 'temperature'), ('top_p', 'topP')):
        value = getattr(settings, source)
        if value is not None:
            generation[target] = value
    body['generationConfig'] = generation
    return {'url': MANIFEST['endpoint'], 'headers': {}, 'body': body, 'protocol': 'google'}


def normalize_usage(raw):
    out = {}
    def number(key):
        value = raw.get(key)
        return value if type(value) is int and value >= 0 else None
    for source, target in (('promptTokenCount', 'prompt_tokens'), ('totalTokenCount', 'total_tokens')):
        if number(source) is not None:
            out[target] = raw[source]
    if number('candidatesTokenCount') is not None:
        out['completion_tokens'] = raw['candidatesTokenCount'] + (number('thoughtsTokenCount') or 0)
    if number('thoughtsTokenCount') is not None:
        out['completion_tokens_details'] = {'reasoning_tokens': raw['thoughtsTokenCount']}
    if number('cachedContentTokenCount') is not None:
        out['prompt_tokens_details'] = {'cached_tokens': raw['cachedContentTokenCount']}
    return out


class Decoder:
    def __init__(self, protocol, model):
        self.model, self.parts, self.usage, self.finish = model, [], {}, None

    def decode(self, event):
        if event.get('error'):
            raise ValueError('4router Gemini 返回模型错误，未产生完整响应。')
        if event.get('promptFeedback', {}).get('blockReason'):
            raise ValueError('4router Gemini 拒绝了输入。')
        self.usage.update(event.get('usageMetadata') or {})
        candidate = next((c for c in event.get('candidates', []) if c.get('index', 0) == 0), {})
        parts = copy.deepcopy(candidate.get('content', {}).get('parts', []))
        for part in parts:
            # 4router can emit a trailing {"text":""}. Its request converter
            # drops that empty string and Gemini then rejects the data-less Part.
            # Keep all actual text/calls and signatures; discard only empty framing.
            if not any(part.get(k) for k in ('text', 'functionCall', 'functionResponse',
                                             'inlineData', 'fileData', 'executableCode', 'codeExecutionResult')):
                if part.get('thoughtSignature'):
                    if not self.parts or (self.parts[-1].get('thoughtSignature') not in (None, part['thoughtSignature'])):
                        raise ValueError('4router Gemini 思考签名片段无法关联到消息内容。')
                    self.parts[-1]['thoughtSignature'] = part['thoughtSignature']
                continue
            self.parts.append(part)
        if candidate.get('finishReason'):
            self.finish = candidate['finishReason']
        return {'choices': [{'index': 0, 'delta': {
                    'content': ''.join(p.get('text', '') for p in parts if not p.get('thought')),
                    'reasoning_content': ''.join(p.get('text', '') for p in parts if p.get('thought'))}}],
                'usage': normalize_usage(self.usage), 'provider_event': event}

    def result(self):
        if self.finish not in ('STOP', 'MAX_TOKENS'):
            raise ValueError('4router Gemini 未正常结束：' + str(self.finish or '缺少结束标记'))
        message = {'role': 'assistant', 'content': ''.join(p.get('text', '') for p in self.parts if not p.get('thought')),
                   '_provider_native': {'provider': 'fourrouter_argon', 'protocol': 'google', 'model': self.model,
                                        'items': copy.deepcopy(self.parts)}}
        thought = ''.join(p.get('text', '') for p in self.parts if p.get('thought'))
        if thought:
            message['reasoning_content'] = thought
        calls = []
        for part in self.parts:
            if 'functionCall' in part:
                call = part['functionCall']
                calls.append({'id': call.get('id') or 'argon_call_' + uuid.uuid4().hex, 'type': 'function',
                              'function': {'name': call['name'], 'arguments': json.dumps(call.get('args', {}), ensure_ascii=False)}})
        if calls:
            message['tool_calls'] = calls
        return {'model': self.model, 'choices': [{'message': message,
                'finish_reason': 'length' if self.finish == 'MAX_TOKENS' else 'tool_calls' if calls else 'stop'}],
                'usage': normalize_usage(self.usage), 'provider_usage': self.usage}
