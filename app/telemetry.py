import copy
from . import store


def empty_usage():
    return {'main': {'calls': 0, 'errors': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'usage_missing_calls': 0},
            'summary': {'calls': 0, 'errors': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'usage_missing_calls': 0},
            'main_iterations': 0, 'main_attempts': 0, 'research_attempts': 0,
            'search_calls': 0, 'extraction_calls': 0, 'fetch_calls': 0,
            'original_extractions': 0, 'fallback_extractions': 0,
            'search_http_requests': 0, 'fetch_http_requests': 0, 'web_errors': 0}


class Telemetry:
    def __init__(self, rid):
        self.rid = rid
        self.usage = empty_usage()
        self.characters = {}

    def emit(self, kind, **data):
        if kind in ('done', 'cancelled', 'error', 'incomplete'):
            run = store.get_run(self.rid)
            if run:
                data['timing'] = {k:run[k] for k in ('started_at', 'finished_at', 'duration_seconds')}
        if kind == 'web_request':
            self.usage[data['service'] + '_http_requests'] += 1
        elif kind == 'web_error': self.usage['web_errors'] += 1
        store.event(self.rid, kind, data)
        if kind in ('web_request', 'web_error'):
            self.persist()

    def persist(self):
        store.update(self.rid, usage=self.usage)
        self.emit('usage', usage=copy.deepcopy(self.usage))

    def start(self, role, purpose, attempt, iteration, payload):
        if purpose == 'final': store.update(self.rid, answer='')
        cid = store.begin_request(self.rid, role, purpose, attempt, iteration, payload)
        self.characters[cid] = {'content_chars': 0, 'reasoning_chars': 0}
        self.usage[role]['calls'] += 1
        self.emit('model_start', call_id=cid, role=role, purpose=purpose, attempt=attempt,
                  iteration=iteration, model=payload['model'], message_count=len(payload['messages']))
        self.persist()
        return cid

    def end(self, cid, role, response=None, error='', status='completed'):
        # A stream may report usage before a disconnect/cancellation. Keep that actual
        # provider value even when no complete response could be assembled.
        if response is None:
            for batch in reversed(store.chunks(cid)):
                usage = next((c['usage'] for c in reversed(batch) if c.get('usage')), None)
                if usage is not None:
                    response = {'usage': usage}
                    break
        store.finish_request(cid, response, error, status)
        usage = (response or {}).get('usage')
        valid = {}
        if isinstance(usage, dict):
            for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
                value = usage.get(key)
                if type(value) is int and value >= 0:
                    valid[key] = value
                    self.usage[role][key] += value
        if len(valid) != 3:
            self.usage[role]['usage_missing_calls'] += 1
        if error: self.usage[role]['errors'] += 1
        self.emit('model_end', call_id=cid, role=role, status=status, error=error, usage=usage)
        self.persist()

    def retry(self, role, purpose, retry, error):
        self.emit('model_retry', role=role, purpose=purpose, retry=retry, text=error)

    def chunk(self, cid, role, purpose, chunks):
        store.append_chunks(cid, chunks)
        content = ''.join(c.get('delta',{}).get('content') or '' for chunk in chunks for c in chunk.get('choices',[]) if c.get('index',0)==0)
        thought = ''.join(c.get('delta',{}).get('reasoning_content') or '' for chunk in chunks for c in chunk.get('choices',[]) if c.get('index',0)==0)
        counts = self.characters.setdefault(cid, {'content_chars': 0, 'reasoning_chars': 0})
        counts['content_chars'] += len(content)
        counts['reasoning_chars'] += len(thought)
        if thought:
            self.emit('reasoning_delta', call_id=cid, role=role, purpose=purpose, text=thought)
        self.emit('model_characters', call_id=cid, role=role, **counts)
        if purpose == 'final' and content:
            store.append_answer(self.rid,content)
            self.emit('answer_delta',call_id=cid,text=content)
        elif role == 'main' and purpose == 'research' and content:
            self.emit('note_delta',call_id=cid,text=content)
        else:
            self.emit('model_progress',call_id=cid,role=role,purpose=purpose,chunks=len(chunks),content_chars=len(content))
