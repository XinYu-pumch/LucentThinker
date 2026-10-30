"""OpenAI-compatible streamed models and full-payload DeepSeek web services."""
import asyncio
import copy
import json
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit
import httpx
from . import config, llm_thinking, llm_protocols
from .search_policy import validate_search_text
from .model_queue import model_slot
from .llm_providers import registry


class ProviderError(Exception):
    def __init__(self, message, *, retryable=False, code=None):
        super().__init__(message)
        self.retryable, self.code = retryable, code

class ContextLimitError(ProviderError): pass

class OutputLimitError(ProviderError):
    def __init__(self, message, partial=''):
        super().__init__(message)
        self.partial = partial


def valid_url(url):
    if not isinstance(url, str): return False
    try:
        p = urlsplit(url)
        return p.scheme in ('https', 'http') and bool(p.hostname) and not p.username and not p.password
    except ValueError: return False


def checked_json(response):
    if response.is_error:
        try:
            raw = response.json()
            error = raw.get('error', raw.get('message', '')) if isinstance(raw, dict) else ''
            detail = error.get('message', '') if isinstance(error, dict) else str(error)
        except ValueError: detail = ''
        detail = config.redact(detail)
        lower = response.text.lower()
        if response.status_code in (400, 413, 422) and 'context' in lower and any(s in lower for s in ('length','exceed','token','long')):
            raise ContextLimitError('服务报告上下文超长；完整输入未裁剪。' + detail, code=response.status_code)
        descriptions = {400:'请求参数或协议不匹配',401:'API Key 无效',402:'账户余额不足',403:'接口或页面访问被拒绝',404:'接口或网页不可用',413:'请求过大',422:'参数校验失败',429:'请求过于频繁'}
        code = response.status_code
        raise ProviderError(f'服务 HTTP {code}：{descriptions.get(code,"服务暂时不可用")}' + (' · '+detail if detail else ''),
                            retryable=code >= 500 or code in (408,409,425,429), code=code)
    try:
        result = response.json()
        if not isinstance(result,dict): raise ValueError()
        return result
    except ValueError: raise ProviderError('服务返回了无法解析的 JSON 对象。', retryable=True) from None


@dataclass
class Completion:
    message: dict
    usage: dict
    finish_reason: str
    model: str
    request_id: int | None = None


class ChatModel:
    def __init__(self, settings, role, observer=None, client=None):
        self.settings, self.role, self.observer = settings, role, observer
        self.session = 'omt-' + uuid.uuid4().hex
        config.register_secret(settings.api_key)
        self.client = client or httpx.AsyncClient(base_url=settings.base_url+'/',
            headers={'Authorization':f'Bearer {settings.api_key}'} if settings.api_key else {},
            timeout=httpx.Timeout(None,connect=30,write=300,pool=30),follow_redirects=False)

    async def close(self): await self.client.aclose()

    async def models(self):
        try:
            adapter = registry.get(self.settings.provider)
            url, headers = adapter.catalog_request(self.session) if adapter and hasattr(adapter, 'catalog_request') else ('models', {})
            result = checked_json(await self.client.get(url, headers=headers, timeout=60))
            return adapter.filter_models(result) if adapter else result
        except ValueError as exc: raise ProviderError(str(exc)) from None
        except httpx.HTTPError: raise ProviderError('读取模型列表失败。') from None

    async def receive(self, payload, call_id, purpose, transport=None, adapter=None):
        """Accumulate complete content; persist streamed deltas without repeated full serialization."""
        decoder = adapter.Decoder(transport['protocol'], self.settings.model) if transport else None
        native_protocol = decoder and transport['protocol'] != 'chat'
        async with self.client.stream('POST', transport['url'] if transport else 'chat/completions',
                                      json=transport['body'] if transport else payload,
                                      headers=transport['headers'] if transport else None) as response:
            if response.is_error or 'text/event-stream' not in response.headers.get('content-type',''):
                await response.aread()
                data = checked_json(response)
                if native_protocol:
                    converted = decoder.decode(data)
                    if self.observer: self.observer.chunk(call_id, self.role, purpose, [converted])
                    return self.native_result(decoder)
                data = llm_protocols.normalize_chat(data)
                if self.observer:
                    self.observer.chunk(call_id, self.role, purpose, [{**data, 'choices': [
                        {**c, 'delta': c.get('message', {})} for c in data.get('choices', [])]}])
                return data
            content, reasoning, calls, reasoning_details = [], [], {}, []
            metadata, usage, finish, pending = {}, {}, None, []
            last_flush, pending_size = time.monotonic(), 0
            def flush():
                nonlocal pending, pending_size, last_flush
                if pending and self.observer: self.observer.chunk(call_id,self.role,purpose,pending)
                pending, pending_size, last_flush = [], 0, time.monotonic()
            try:
                async for line in response.aiter_lines():
                    if not line.startswith('data:'): continue
                    data = line[5:].strip()
                    if data == '[DONE]': break
                    try: chunk = json.loads(data)
                    except ValueError: raise ProviderError('无法解析模型流式响应。') from None
                    if 'error' in chunk:
                        raise ProviderError('模型流返回错误：'+config.redact(str(chunk['error'])))
                    if native_protocol: chunk = decoder.decode(chunk)
                    else: chunk = llm_protocols.normalize_chat(chunk)
                    pending.append(chunk)
                    pending_size += len(data)
                    for key in ('id','model','created','object','system_fingerprint'):
                        if key in chunk: metadata[key] = chunk[key]
                    if chunk.get('usage'): usage = chunk['usage']
                    for choice in chunk.get('choices',[]):
                        if choice.get('index',0) != 0: continue
                        delta = choice.get('delta') or {}
                        if delta.get('content'): content.append(delta['content'])
                        if delta.get('reasoning_content'): reasoning.append(delta['reasoning_content'])
                        if delta.get('reasoning_details'): reasoning_details.extend(delta['reasoning_details'])
                        for tc in delta.get('tool_calls') or []:
                            entry = calls.setdefault(tc.get('index',0),{'id':'','type':'function','function':{'name':'','arguments':''}})
                            if tc.get('id'): entry['id'] = tc['id']
                            for key in ('name','arguments'):
                                value = tc.get('function',{}).get(key)
                                if value: entry['function'][key] += value
                        if choice.get('finish_reason') is not None: finish = choice['finish_reason']
                    if pending_size >= 65536 or time.monotonic()-last_flush >= .7: flush()
            finally:
                flush()
            if native_protocol: return self.native_result(decoder)
            if finish is None: raise ProviderError('模型连接在结束标记前中断；已收到的片段已保存。')
            message = {'role':'assistant','content':''.join(content)}
            if reasoning: message['reasoning_content'] = ''.join(reasoning)
            if reasoning_details: message['reasoning_details'] = reasoning_details
            if calls: message['tool_calls'] = [calls[k] for k in sorted(calls)]
            return {**metadata,'choices':[{'message':message,'finish_reason':finish,'index':0}], 'usage':usage}

    def native_result(self, decoder):
        result = decoder.result()
        for choice in result.get('choices', []):
            native = choice.get('message', {}).get('_provider_native')
            if native is not None:
                native['origin'] = [self.settings.provider, self.settings.base_url, self.settings.model]
        return result

    async def complete(self, messages, tools=None, *, purpose='research', iteration=0, attempt=1, max_attempts=None, request_transform=None):
        if not self.settings.model: raise ProviderError('请选择模型。')
        attempts = min(self.settings.request_attempts,max_attempts) if max_attempts else self.settings.request_attempts
        # Each extraction is a new conversation, even if the same client/model is reused.
        session = 'omt-' + uuid.uuid4().hex if self.role == 'summary' else self.session + '-' + str(attempt)
        try:
            adapter = registry.get(self.settings.provider)
            if self.settings.thinking_config is not None or (adapter and not hasattr(adapter, 'prepare')):
                if adapter: adapter.validate({'base_url': self.settings.base_url, 'model': self.settings.model})
                adapter = llm_thinking
        except ValueError as exc:
            raise ProviderError(str(exc)) from None
        for retry in range(attempts):
            payload = {'model':self.settings.model,'messages':copy.deepcopy(messages),'stream':True,
                       'stream_options':{'include_usage':True}, **self.settings.generation()}
            if tools: payload['tools'] = copy.deepcopy(tools)
            call_id = None
            response_data = None
            try:
                transport = adapter.prepare(self.settings, payload, session) if adapter else None
                if not transport:
                    payload['messages'] = [{k: v for k, v in m.items() if not k.startswith('_')} for m in payload['messages']]
                if request_transform:
                    request_transform(transport['body'] if transport else payload)
                audit = {**payload, 'wire_request': copy.deepcopy(transport)} if transport else payload
                async with model_slot(self.settings,self.observer,self.role,purpose,iteration,attempt):
                    call_id = self.observer.start(self.role,purpose,attempt,iteration,audit) if self.observer else None
                    try: response_data = await self.receive(payload,call_id,purpose,transport,adapter) if transport else await self.receive(payload,call_id,purpose)
                    except (httpx.TimeoutException,httpx.NetworkError,httpx.RemoteProtocolError):
                        raise ProviderError('连接模型服务失败；已接收的流片段保留在请求详情中。',retryable=True) from None
                choices = response_data.get('choices') or []
                if not choices or not isinstance(choices[0].get('message'),dict): raise ProviderError('模型未返回有效消息。')
                choice = choices[0]
                reason = choice.get('finish_reason','stop')
                if adapter and choice.get('finish_reason') not in ('stop', 'tool_calls', 'length'):
                    raise ProviderError('供应商未返回有效结束状态，不能视为完整模型响应。')
                if self.observer:
                    self.observer.end(call_id,self.role,response_data,
                        error='服务端输出达到上限；部分输出已保留。' if reason=='length' else '',
                        status='incomplete' if reason=='length' else 'completed')
                return Completion(choice['message'],response_data.get('usage') or {},reason,response_data.get('model',self.settings.model),call_id)
            except asyncio.CancelledError:
                if self.observer and call_id is not None: self.observer.end(call_id,self.role,error='已取消；已收到的流片段保留。',status='cancelled')
                raise
            except ProviderError as exc:
                if self.observer and call_id is not None: self.observer.end(call_id,self.role,response_data,error=str(exc),status='failed')
                if not exc.retryable or retry+1 >= attempts: raise
                if self.observer: self.observer.retry(self.role,purpose,retry+1,str(exc))
                await asyncio.sleep(self.settings.retry_delay*min(2**retry,8))
            except ValueError as exc:
                if self.observer and call_id is not None: self.observer.end(call_id,self.role,response_data,error=config.redact(str(exc)),status='failed')
                raise ProviderError(config.redact(str(exc))) from None
            except Exception as exc:
                if self.observer and call_id is not None: self.observer.end(call_id,self.role,error='响应协议解析失败：'+type(exc).__name__,status='failed')
                raise ProviderError('模型响应协议解析失败：'+type(exc).__name__) from None
        raise ProviderError('模型请求重试次数已用尽。')


class DeepSeek:
    def __init__(self,client=None,emit=None,api_key=None):
        if api_key is None:
            from .settings_store import web_key
            api_key = web_key()
        self.api_key = config.register_secret(api_key)
        self.emit = emit or (lambda *args,**kwargs:None)
        self.client = client or httpx.AsyncClient(base_url=config.BASE_URL,
            headers={'Authorization':f'Bearer {self.api_key}'},timeout=httpx.Timeout(None,connect=30,write=300,pool=30),follow_redirects=False)
    async def close(self): await self.client.aclose()
    async def request(self,path,payload=None,method='POST'):
        if not self.api_key: raise ProviderError('请在设置 → 搜索与抓取中输入 DeepSeek API Key。')
        for attempt in range(4):
            self.emit('web_request',service='search' if path.endswith('/search') else 'fetch',attempt=attempt+1)
            try:
                try: return checked_json(await self.client.request(method,path,json=payload))
                except (httpx.TimeoutException,httpx.NetworkError,httpx.RemoteProtocolError):
                    raise ProviderError('连接 DeepSeek 网页服务失败。',retryable=True) from None
            except ProviderError as exc:
                self.emit('web_error',service='search' if path.endswith('/search') else 'fetch',text=str(exc))
                if not exc.retryable or attempt==3: raise
                self.emit('web_retry',attempt=attempt+1,text=str(exc))
                await asyncio.sleep(2**attempt)
    async def search(self,query,question,count=10):
        validate_search_text(query, 'query')
        validate_search_text(question, 'ori_question')
        if type(count) is not int or count<1: raise ValueError('搜索结果数量应为正整数。')
        return await self.request('/v1/tools/search',{'query':query,'count':count,'ori_question':question,'need_content':True})
    async def fetch(self,url):
        if not valid_url(url): raise ValueError('请输入不含账号密码的 HTTP(S) 网页地址。')
        return await self.request('/v1/tools/fetch',{'url':url})
