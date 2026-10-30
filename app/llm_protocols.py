"""Shared native protocols with signed continuation and research tool round trips."""
import copy
import json
import uuid


def readable(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ''.join(readable(p) for p in value)
    if isinstance(value, dict) and value.get('type') not in ('reasoning.encrypted', 'redacted_thinking'):
        return value.get('text', '') if isinstance(value.get('text'), str) else ''
    return ''


def normalize_chat(value):
    value = copy.deepcopy(value)
    for choice in value.get('choices', []):
        for field in ('delta', 'message'):
            message = choice.get(field)
            if not isinstance(message, dict):
                continue
            thought = readable(message.get('reasoning_content')) or readable(message.get('reasoning')) or readable(message.get('reasoning_details'))
            if thought:
                message['reasoning_content'] = thought
            if message.get('content') is not None:
                message['content'] = readable(message['content'])
    return value

def text(message):
    value = message.get('content')
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('原生协议目前支持文本与工具消息，不支持图片输入。')
    return value


def native(message, protocol, settings):
    saved = message.get('_provider_native') or {}
    if saved.get('origin') and saved['origin'] != [settings.provider, settings.base_url, settings.model]:
        return None
    if saved.get('protocol') == protocol and saved.get('model') == settings.model:
        return copy.deepcopy(saved['items'])
    return None


def prepare_body(settings, payload, protocol, max_tokens=None):
    messages = payload['messages']
    tools = [t['function'] for t in payload.get('tools', [])]
    head = {}
    body = {'model': settings.model, 'stream': True}
    if protocol == 'chat':
        body.update(messages=[{k: copy.deepcopy(v) for k, v in m.items() if not k.startswith('_')}
                              for m in messages], stream_options={'include_usage': True})
        if tools:
            body['tools'] = copy.deepcopy(payload['tools'])
    elif protocol == 'responses':
        body.update(store=False, input=[], include=['reasoning.encrypted_content'])
        for m in messages:
            if m['role'] == 'tool':
                body['input'].append({'type': 'function_call_output', 'call_id': m['tool_call_id'], 'output': text(m)})
                continue
            saved = native(m, protocol, settings)
            if m['role'] == 'assistant' and saved is not None:
                body['input'].extend(saved)
                continue
            if text(m):
                body['input'].append({'role': m['role'], 'content': text(m)})
            for call in m.get('tool_calls', []):
                body['input'].append({'type': 'function_call', 'call_id': call['id'], **call['function']})
        if tools:
            body['tools'] = [{'type': 'function', **copy.deepcopy(t), 'strict': False} for t in tools]
    elif protocol == 'messages':
        head['anthropic-version'] = '2023-06-01'
        body.update(messages=[], max_tokens=max_tokens)
        system = []
        for m in messages:
            if m['role'] == 'system':
                system.append({'type': 'text', 'text': text(m)})
                continue
            role = 'user' if m['role'] == 'tool' else m['role']
            if m['role'] == 'tool':
                parts = [{'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': text(m)}]
            else:
                parts = native(m, protocol, settings) if role == 'assistant' else None
                if parts is None:
                    parts = [{'type': 'text', 'text': text(m)}] if text(m) else []
                    parts += [{'type': 'tool_use', 'id': c['id'], 'name': c['function']['name'],
                               'input': json.loads(c['function']['arguments'])} for c in m.get('tool_calls', [])]
            if not parts:
                continue
            if body['messages'] and body['messages'][-1]['role'] == role:
                body['messages'][-1]['content'].extend(parts)
            else:
                body['messages'].append({'role': role, 'content': parts})
        if system:
            body['system'] = system
        if tools:
            body['tools'] = [{'name': t['name'], 'description': t.get('description', ''),
                              'input_schema': copy.deepcopy(t['parameters'])} for t in tools]
    else:
        body = {'contents': []}
        system, call_names = [], {}
        for m in messages:
            if m['role'] == 'system':
                system.append({'text': text(m)})
                continue
            role = 'model' if m['role'] == 'assistant' else 'user'
            if m['role'] == 'tool':
                name, ident = call_names[m['tool_call_id']]
                answer = {'name': name, 'response': {'result': text(m)}}
                if ident:
                    answer['id'] = ident
                parts = [{'functionResponse': answer}]
            else:
                parts = native(m, protocol, settings) if role == 'model' else None
                if parts is None:
                    parts = [{'text': text(m)}] if text(m) else []
                    parts += [{'functionCall': {'name': c['function']['name'],
                               'args': json.loads(c['function']['arguments'])}}
                              for c in m.get('tool_calls', [])]
                native_calls = [p['functionCall'] for p in parts if 'functionCall' in p]
                for i, c in enumerate(m.get('tool_calls', [])):
                    call_names[c['id']] = (c['function']['name'], native_calls[i].get('id'))
            if not parts:
                continue
            if body['contents'] and body['contents'][-1]['role'] == role:
                body['contents'][-1]['parts'].extend(parts)
            else:
                body['contents'].append({'role': role, 'parts': parts})
        if system:
            body['systemInstruction'] = {'parts': system}
        if tools:
            body['tools'] = [{'functionDeclarations': [
                {'name': t['name'], 'description': t.get('description', ''),
                 'parametersJsonSchema': copy.deepcopy(t['parameters'])} for t in tools]}]
    for key, value in (('temperature', settings.temperature), ('top_p', settings.top_p)):
        if value is not None:
            if protocol == 'google':
                body.setdefault('generationConfig', {})['topP' if key == 'top_p' else key] = value
            else:
                body[key] = value
    return body, head


def normalize_usage(raw, protocol):
    """Map actual reported fields; absent counts stay absent, never estimated."""
    if protocol == 'chat':
        return copy.deepcopy(raw)
    out = {}
    def number(name):
        v = raw.get(name)
        return v if type(v) is int and v >= 0 else None
    if protocol == 'responses':
        pairs = [('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'), ('total_tokens', 'total_tokens')]
        cached = (raw.get('input_tokens_details') or {}).get('cached_tokens')
        if type(cached) is int and cached >= 0:
            out['prompt_tokens_details'] = {'cached_tokens': cached}
    elif protocol == 'messages':
        pairs = [('output_tokens', 'completion_tokens')]
        # Anthropic input_tokens excludes both cache-read and cache-write input.
        if number('input_tokens') is not None:
            out['prompt_tokens'] = raw['input_tokens'] + (number('cache_read_input_tokens') or 0) + (number('cache_creation_input_tokens') or 0)
        if number('cache_read_input_tokens') is not None:
            out['prompt_tokens_details'] = {'cached_tokens': raw['cache_read_input_tokens']}
    else:
        pairs = [('promptTokenCount', 'prompt_tokens'), ('totalTokenCount', 'total_tokens')]
        if number('candidatesTokenCount') is not None:
            out['completion_tokens'] = raw['candidatesTokenCount'] + (number('thoughtsTokenCount') or 0)
        if number('cachedContentTokenCount') is not None:
            out['prompt_tokens_details'] = {'cached_tokens': raw['cachedContentTokenCount']}
    for source, target in pairs:
        if number(source) is not None:
            out[target] = raw[source]
    thought_tokens = (raw.get('output_tokens_details') or {}).get('reasoning_tokens') if protocol == 'responses' else raw.get('thoughtsTokenCount')
    if type(thought_tokens) is int and thought_tokens >= 0:
        out['completion_tokens_details'] = {'reasoning_tokens': thought_tokens}
    if 'total_tokens' not in out and 'prompt_tokens' in out and 'completion_tokens' in out:
        out['total_tokens'] = out['prompt_tokens'] + out['completion_tokens']
    return out


class Decoder:
    """Native SSE to canonical deltas, retaining signed/native assistant blocks."""
    def __init__(self, protocol, model):
        self.protocol, self.model = protocol, model
        self.blocks, self.parts, self.output = {}, [], []
        self.usage, self.finish, self.stopped = {}, None, False
        self.text, self.thought, self.calls = [], [], []
        self.segments = {}

    def segment(self, event, family, value, complete=False):
        key = (event.get('output_index', -1), family, event.get('summary_index', event.get('content_index', 0)))
        previous = self.segments.get(key, '')
        if complete:
            fallback = (-1, family, key[2])
            if not previous and key[0] != -1 and self.segments.get(fallback) and value.startswith(self.segments[fallback]):
                previous = self.segments.pop(fallback)
            other = (key[0], 'content' if family == 'summary' else 'summary', key[2])
            if family != 'answer' and not previous and (self.segments.get(other) == value or self.segments.get((-1, other[1], other[2])) == value):
                self.segments[key] = value
                return ''
            if previous and not value.startswith(previous):
                return ''
            self.segments[key] = value
            return value[len(previous):]
        self.segments[key] = previous + value
        return value

    def decode(self, event):
        if event.get('error') or event.get('type') in ('error', 'response.failed'):
            raise ValueError('模型服务 返回模型错误，未产生完整响应。')
        if self.protocol == 'chat':
            return event
        kind = event.get('type', '')
        content, thought = '', ''
        if self.protocol == 'responses':
            if kind == 'response.output_text.delta':
                content = self.segment(event, 'answer', event.get('delta', ''))
            if kind == 'response.output_text.done':
                content = self.segment(event, 'answer', event.get('text', ''), True)
            if kind in ('response.reasoning_summary_text.delta', 'response.reasoning_text.delta'):
                thought = self.segment(event, 'summary' if 'summary' in kind else 'content', event.get('delta', ''))
            if kind in ('response.reasoning_summary_text.done', 'response.reasoning_text.done'):
                thought = self.segment(event, 'summary' if 'summary' in kind else 'content', event.get('text', ''), True)
            if kind == 'response.refusal.delta':
                raise ValueError('模型服务 模型拒绝了请求。')
            if kind in ('response.completed', 'response.incomplete') or event.get('object') == 'response':
                response = event.get('response', event)
                self.output = copy.deepcopy(response.get('output') or [])
                self.usage.update(response.get('usage') or {})
                status = response.get('status')
                if status == 'incomplete' and response.get('incomplete_details', {}).get('reason') == 'max_output_tokens':
                    self.finish = 'length'
                elif status == 'completed':
                    self.finish = 'stop'
                else:
                    raise ValueError('模型服务 Responses 未正常结束。')
                for index, item in enumerate(self.output):
                    if item['type'] == 'function_call':
                        self.calls.append({'id': item['call_id'], 'type': 'function',
                                           'function': {'name': item['name'], 'arguments': item['arguments']}})
                    elif item['type'] == 'message':
                        for part_index, part in enumerate(item.get('content') or []):
                            if part['type'] == 'refusal':
                                raise ValueError('模型服务 模型拒绝了请求。')
                            if part['type'] == 'output_text':
                                content += self.segment({'output_index': index, 'content_index': part_index}, 'answer', part['text'], True)
                    elif item['type'] == 'reasoning':
                        for family in ('summary', 'content'):
                            for part_index, part in enumerate(item.get(family) or []):
                                if part.get('type') in ('summary_text', 'reasoning_text', 'text'):
                                    thought += self.segment({'output_index': index, 'content_index': part_index}, family, part.get('text', ''), True)
                    elif item['type'] != 'reasoning':
                        raise ValueError('模型服务 返回未支持的内置工具结果。')
                self.stopped = True
        elif self.protocol == 'messages':
            if kind == 'message_start':
                self.usage.update(event['message'].get('usage') or {})
            elif kind == 'content_block_start':
                block = copy.deepcopy(event['content_block'])
                self.blocks[event['index']] = block
                content, thought = block.get('text', ''), block.get('thinking', '')
            elif kind == 'content_block_delta':
                block = self.blocks[event['index']]
                delta = event['delta']
                for key in ('text', 'thinking', 'signature'):
                    if key in delta:
                        block[key] = block.get(key, '') + delta[key]
                if 'partial_json' in delta:
                    block['_arguments'] = block.get('_arguments', '') + delta['partial_json']
                content, thought = delta.get('text', ''), delta.get('thinking', '')
            elif kind == 'message_delta':
                self.usage.update(event.get('usage') or {})
                self.finish = event.get('delta', {}).get('stop_reason') or self.finish
            elif kind == 'message_stop':
                self.stopped = True
            elif kind == 'message' and 'content' in event:
                self.blocks = dict(enumerate(copy.deepcopy(event['content'])))
                self.usage.update(event.get('usage') or {})
                content = ''.join(b.get('text', '') for b in self.blocks.values())
                thought = ''.join(b.get('thinking', '') for b in self.blocks.values())
                self.finish, self.stopped = event.get('stop_reason'), True
        else:
            if event.get('promptFeedback', {}).get('blockReason'):
                raise ValueError('模型服务 Gemini 拒绝了输入。')
            self.usage.update(event.get('usageMetadata') or {})
            candidate = next((c for c in event.get('candidates', []) if c.get('index', 0) == 0), {})
            parts = copy.deepcopy(candidate.get('content', {}).get('parts', []))
            for part in parts:
                if not any(part.get(k) for k in ('text', 'functionCall', 'functionResponse', 'inlineData', 'fileData', 'executableCode', 'codeExecutionResult')):
                    if part.get('thoughtSignature'):
                        if not self.parts or self.parts[-1].get('thoughtSignature') not in (None, part['thoughtSignature']):
                            raise ValueError('Gemini 思考签名片段无法关联到消息内容')
                        self.parts[-1]['thoughtSignature'] = part['thoughtSignature']
                    continue
                self.parts.append(part)
            for part in parts:
                if part.get('thought'):
                    thought += part.get('text', '')
                else:
                    content += part.get('text', '')
            if candidate.get('finishReason'):
                self.finish, self.stopped = candidate['finishReason'], True
        if content:
            self.text.append(content)
        if thought:
            self.thought.append(thought)
        chunk = {'choices': [{'index': 0, 'delta': {'content': content, 'reasoning_content': thought}}],
                 'provider_event': event}
        if self.usage:
            chunk['usage'] = normalize_usage(self.usage, self.protocol)
        return chunk

    def result(self):
        if not self.stopped or not self.finish:
            raise ValueError('模型服务 连接在有效结束标记前中断；片段已保留。')
        if self.finish in ('max_tokens', 'MAX_TOKENS', 'length'):
            finish = 'length'
        elif self.finish in ('stop', 'STOP', 'end_turn', 'stop_sequence', 'tool_use'):
            finish = 'stop'
        else:
            raise ValueError('模型服务 模型被过滤或未正常完成：' + str(self.finish))
        if self.protocol == 'messages':
            items = [b for _, b in sorted(self.blocks.items())]
            for b in items:
                if b['type'] == 'tool_use':
                    if '_arguments' in b:
                        args = b.pop('_arguments')
                        try:
                            b['input'] = json.loads(args)
                        except ValueError:
                            if finish != 'length':
                                raise
                            b['_partial_arguments'] = args
                            continue
                    self.calls.append({'id': b['id'], 'type': 'function',
                                       'function': {'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)}})
        elif self.protocol == 'google':
            items = self.parts
            for part in items:
                if 'functionCall' in part:
                    call = part['functionCall']
                    # Stable within the saved response; provider-issued IDs take precedence.
                    ident = call.get('id') or 'native_call_' + uuid.uuid4().hex
                    self.calls.append({'id': ident, 'type': 'function',
                                       'function': {'name': call['name'], 'arguments': json.dumps(call.get('args', {}), ensure_ascii=False)}})
        else:
            items = self.output
        message = {'role': 'assistant', 'content': ''.join(self.text),
                   '_provider_native': {'protocol': self.protocol, 'model': self.model, 'items': items}}
        if self.thought:
            message['reasoning_content'] = ''.join(self.thought)
        if self.calls:
            message['tool_calls'] = self.calls
            if finish != 'length':
                finish = 'tool_calls'
        return {'model': self.model, 'choices': [{'message': message, 'finish_reason': finish}],
                'usage': normalize_usage(self.usage, self.protocol), 'provider_usage': self.usage}
