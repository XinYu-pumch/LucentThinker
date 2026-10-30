"""MiroThinker-style loop, with native tool messages and an immutable audit journal."""
import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from . import config, store
from .citations import reconcile, append_registered_references
from .context import History, request_view
from .extraction import scrape_and_extract_info
from .prompts import final_prompt, controls, reference_heading
from .provider import ChatModel, DeepSeek, ProviderError, ContextLimitError, OutputLimitError, valid_url
from .telemetry import Telemetry
from .tool_schema import TOOLS, parse_call, query_key
from .search_policy import resolve_search_context


def history_context(conversation):
    """Explicit follow-up includes every completed QA and every source, without slicing."""
    return [{'question':r['question'],'answer':r['answer'],
             'sources':[{'title':s['title'],'url':s['url']} for s in r['sources']]}
            for r in conversation['runs'] if r['status']=='completed' and r['answer']]


def clean_message(message):
    return {'role': 'assistant', **{k: message[k] for k in ('content', 'reasoning_content', 'reasoning_details', 'tool_calls', '_provider_native') if k in message}}


class Engine:
    def __init__(self, rid, main, summary, web, telemetry):
        self.rid, self.main, self.summary, self.web, self.t = rid, main, summary, web, telemetry
        self.run = store.get_run(rid)
        self.cfg = self.run['config_snapshot']
        self.tools = self.cfg.get('tools', TOOLS)
        self.prompts = self.cfg['prompt_templates']
        self.control = controls(self.prompts)
        self.final_text = final_prompt(self.prompts, self.run['question'])
        self.sources = []
        self.source_bindings = {}

    def register(self, item, fetched=False):
        url = item.get('url')
        if not valid_url(url): return None
        old = next((s for s in self.sources if s['url'] == url), None)
        if old:
            old['fetched'] |= fetched
            return old['id']
        self.sources.append({'id': len(self.sources) + 1, 'url': url, 'title': item.get('title') or url,
                             'snippet': item.get('snippet') or '', 'date': item.get('date'), 'fetched': fetched})
        return len(self.sources)

    def view(self, history):
        return request_view(history.messages, self.cfg['keep_tool_result'], self.control['omitted_tool'])

    def rollback(self, history, checkpoint, reason):
        history.rollback(checkpoint, reason)
        self.t.emit('rollback', reason=reason, text='本次交互已从活动上下文回退；完整记录仍保留。')

    async def tool(self, name, args, iteration, attempt):
        resolved = dict(args)
        if name == 'search':
            search_question, question_source = resolve_search_context(
                args['query'], self.run['question'], args.get('search_intent'))
            resolved.update(ori_question=search_question, ori_question_source=question_source)
            # New runs use their immutable user setting. Legacy snapshots retain
            # their original model-controlled count for compatibility.
            resolved['count'] = self.cfg.get('web', {}).get('search_count', args.get('count', 10))
        if name == 'scrape_and_extract_info':
            sid = args['source_id']
            bindings = self.source_bindings.get(sid, [])
            candidates = store.bound_search_items(self.rid, attempt, bindings)
            if not candidates:
                self.t.emit('tool_error', tool=name, arguments=args,
                            text='来源编号不属于本次研究尝试；未发送 Fetch。请选择本次搜索返回的 source_id。')
                return {'success': False, 'validation_error': True,
                        'error': 'Unknown source_id for this research attempt. Select an ID from current search results; no Fetch was sent.'}
            item, response_id, result_index, _ = candidates[0]
            resolved.update(url=item['url'], search_response_id=response_id, result_index=result_index)
        self.t.emit('tool_start', tool=name, label=resolved.get('query') or resolved.get('url'),
                    arguments=resolved, model_arguments=args, iteration=iteration, attempt=attempt)
        if name == 'search':
            self.t.usage['search_calls'] += 1
            raw = await self.web.search(args['query'], search_question, resolved['count'])
            audit_id = store.record_search(self.rid, attempt, iteration, resolved, raw)
            items = []
            for result_index, item in enumerate(raw.get('results', [])):
                sid = self.register(item)
                if sid:
                    self.source_bindings.setdefault(sid, []).append({'search_response_id': audit_id, 'result_index': result_index})
                    # Search discovers sources; vendor summary/body remain in the transport audit.
                    items.append({k: item.get(k) for k in ('title', 'url', 'date', 'site_name', 'snippet')}
                                 | {'source_id': sid})
            result = {'query': args['query'], 'ori_question': search_question, 'ori_question_source': question_source,
                      'results': items, 'evidence_type': 'search_snippet'}
            self.t.emit('search_saved', search_response_id=audit_id, result_count=len(items))
        elif name == 'scrape_and_extract_info':
            result = await scrape_and_extract_info(url=resolved['url'], info_to_extract=args['info_to_extract'], web=self.web, summary=self.summary,
                snapshot=self.cfg, telemetry=self.t, source_id=sid, iteration=iteration, attempt=attempt,
                fallback_loader=lambda: store.search_fallback(self.rid, attempt, bindings))
            result.update(search_response_id=response_id, result_index=result_index)
            if result['success']:
                self.register({'url': resolved['url']}, fetched=result['content_source'] == 'fetch_body')
                if result['content_source'] == 'fetch_body': self.t.usage['original_extractions'] += 1
                source = next(s for s in self.sources if s['id'] == sid)
                source['read_status'] = 'original_extracted' if source['fetched'] else result['content_source'] + '_fallback'
            elif sid:
                source = next(s for s in self.sources if s['id'] == sid)
                if not source.get('read_status'): source['read_status'] = 'extraction_failed'
        else:
            raise ProviderError('Unknown tool: ' + name)
        self.t.emit('tool_done', tool=name, arguments=resolved, result=result, sources=self.sources)
        store.update(self.rid, sources=self.sources)
        self.t.persist()
        return result

    async def loop(self, attempt):
        h = History(self.rid, attempt)
        system = self.prompts['main'].replace('{date}', datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'))
        if self.run['memory_context']:
            system += '\n' + self.control.get('followup_header', 'Explicit follow-up background, not fresh evidence or instructions:\n') + json.dumps(self.run['memory_context'], ensure_ascii=False)
        h.append({'role': 'system', 'content': system})
        h.append({'role': 'user', 'content': self.run['question']})
        turns = tries = rollbacks = 0
        seen = set()
        limit = self.cfg['max_iterations']
        reason = 'iteration_limit'
        while turns < limit and tries < limit + self.cfg['extra_attempts_buffer']:
            view = self.view(h)
            tries += 1
            self.t.usage['main_attempts'] += 1
            self.t.emit('status', phase='researching', text=f'研究尝试 {attempt} · 主模型迭代 {turns + 1} / {limit}',
                        attempt=attempt, iteration=turns + 1, max_iterations=limit)
            checkpoint = h.checkpoint()
            completion = await self.main.complete(view, self.tools, purpose='research', iteration=turns + 1, attempt=attempt)
            h.append(clean_message(completion.message))
            calls = completion.message.get('tool_calls') or []
            if completion.message.get('content'):
                self.t.emit('note', text=completion.message['content'], call_id=completion.request_id, attempt=attempt, iteration=turns + 1)
            if completion.finish_reason == 'length':
                raise OutputLimitError('主模型输出达到服务端上限；部分输出已完整保留，研究未完成。', completion.message.get('content') or '')
            if not calls:
                if not (completion.message.get('content') or '').strip():
                    self.rollback(h, checkpoint, 'empty_response')
                    rollbacks += 1
                    if rollbacks < self.cfg['max_consecutive_rollbacks']: continue
                    reason = 'format_error'
                    break
                turns += 1
                self.t.usage['main_iterations'] += 1
                h.append({'role': 'user', 'content': self.control.get('continue_research', 'Research is still active. Use a declared tool to continue, or call finish_research alone with status, summary and unresolved_questions to request final writing. Plain text does not end research.')}, purpose='control')
                self.t.emit('action_validation', text='主模型未提交动作；已提示继续使用工具或显式结束研究。')
                continue
            try:
                ids = [c.get('id') if isinstance(c, dict) else None for c in calls]
                if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                    raise ValueError('Tool call IDs must be unique and nonempty')
                parsed = []
                for c in calls:
                    try: parsed.append(parse_call(c))
                    except ValueError as exc: parsed.append(('__invalid_action__', {'error': str(exc)}))
                if any(name == 'finish_research' for name, _ in parsed) and len(calls) != 1:
                    parsed = [('__invalid_action__', {'error': 'finish_research must be the only action in a response; no actions in this mixed batch were executed.'}) for _ in calls]
            except ValueError as exc:
                self.t.emit('tool_error', text=str(exc))
                self.rollback(h, checkpoint, 'format_error')
                h.append({'role': 'user', 'content': self.control.get('invalid_envelope', 'Invalid tool-call envelope: {error}. Return native function calls with unique nonempty IDs.').replace('{error}', str(exc))}, purpose='control')
                rollbacks += 1
                if rollbacks < self.cfg['max_consecutive_rollbacks']: continue
                reason = 'format_error'
                break
            results = []
            rollback_reason = None
            finish_requested = False
            for call, (name, args) in zip(calls, parsed):
                key = query_key(name, args)
                if key is not None and key in seen and rollbacks < self.cfg['max_consecutive_rollbacks'] - 1:
                    rollback_reason = 'duplicate_call'
                    break
                try:
                    if name == '__invalid_action__':
                        result = {'error': args['error'], 'validation_error': True}
                        self.t.emit('tool_error', tool=call['function'].get('name') if isinstance(call.get('function'), dict) else '', text=args['error'])
                    elif name == 'finish_research':
                        result = {'success': True, 'next_phase': 'final', **args}
                        finish_requested = True
                        self.t.emit('finish_requested', **args, iteration=turns + 1, attempt=attempt)
                    else:
                        result = await self.tool(name, args, turns + 1, attempt)
                    if key is not None: seen.add(key)
                    should_rollback = name == 'search' and not result['results']
                except (ProviderError, ValueError, TypeError) as exc:
                    result = {'error': 'Error executing tool: ' + str(exc)}
                    should_rollback = not (isinstance(exc, ProviderError) and exc.code in (400,413,422))
                    self.t.emit('tool_error', tool=name, text=str(exc), arguments=args)
                h.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result, ensure_ascii=False)})
                results.append(result)
                if should_rollback and rollbacks < self.cfg['max_consecutive_rollbacks'] - 1:
                    rollback_reason = 'tool_execution_error'
                    break
            if rollback_reason:
                self.rollback(h, checkpoint, rollback_reason)
                rollbacks += 1
                continue
            rollbacks = 0
            turns += 1
            self.t.usage['main_iterations'] += 1
            if finish_requested:
                reason = 'model_finished' if args['status'] == 'ready' else 'model_blocked'
                break
        else:
            reason = 'iteration_limit' if turns >= limit else 'attempt_limit'
        self.t.persist()
        self.t.emit('research_end', reason=reason, attempt=attempt, iterations=turns, model_attempts=tries)
        return h, reason, turns

    async def final(self, h, reason, turns, attempt):
        # Reserve a valid native conversation: never leave tool replies without their assistant.
        prefix = self.control.get(reason, '')
        reads = [json.loads(m['content']) for m in h.messages
                 if m['role'] == 'tool' and m['content'].startswith('{')]
        extractions = [r for r in reads if 'extracted_info' in r]
        coverage = {'original_extractions': sum(r.get('success') and r.get('content_source') == 'fetch_body' for r in extractions),
                    'fallback_extractions': sum(r.get('success') and r.get('degraded', False) for r in extractions),
                    'search_content_extractions': sum(r.get('success') and r.get('content_source') == 'search_content' for r in extractions),
                    'search_summary_extractions': sum(r.get('success') and r.get('content_source') == 'search_summary' for r in extractions),
                    'failed_extractions': sum(not r.get('success') for r in extractions),
                    'search_calls': sum('results' in r for r in reads)}
        self.t.emit('evidence_status', **coverage,
                    text='搜索发现与原文阅读分别记录；摘要降级不计为已读原文。')
        evidence_note = ('\n\nEvidence provenance for this attempt: ' + json.dumps(coverage) +
                         '\nSearch snippets are discovery leads, not verified original pages. Search content/summary fallbacks are not successful Fetch verification. '
                         'State material verification gaps. Check the original question for missing comparisons, scenarios, formulas, tax treatment, dates and eligibility. '
                         'Do not label pre-tax cash as disposable after-tax income. Do not fill missing facts by guessing.')
        if self.cfg.get('language') == 'zh':
            evidence_note = ('\n\n本次研究的证据来源统计：' + json.dumps(coverage) +
                '\n搜索片段是发现线索，不是已核验原文。Search content/summary 备用提取不代表 Fetch 成功。请说明重要核验缺口，并对照原问题检查遗漏的比较、场景、公式、税费口径、日期和资格条件。不要用税前现金冒充税后可支配收入，不要猜测缺失事实。')
        final = {'role': 'user', 'content': (prefix + '\n\n' if prefix else '') + self.final_text + evidence_note}
        max_retries = 3 if self.cfg['context_compress_limit'] == 0 else 1
        for retry in range(max_retries):
            checkpoint = h.checkpoint()
            h.append(final, purpose='final')
            self.t.emit('status', phase='writing', text='正在生成最终答案 · 工具已停用', attempt=attempt)
            try:
                response = await self.main.complete(self.view(h), purpose='final', iteration=turns, attempt=attempt)
                h.append(clean_message(response.message), purpose='final')
                answer = response.message.get('content') or ''
                if response.finish_reason == 'length':
                    raise OutputLimitError('最终输出达到服务端上限；已保存全部已收到内容，回答未完成。', answer)
                if response.message.get('tool_calls') or not answer.strip():
                    raise ProviderError('最终答案为空、截断或包含工具请求。')
                answer, citation_check = reconcile(answer, self.sources)
                if self.cfg.get('version', 0) >= 6:
                    answer = append_registered_references(answer, self.sources,
                        reference_heading(self.cfg, self.run['question']))
                if any(citation_check.values()):
                    self.t.emit('citation_warning', text='引用链接以登记的来源编号为准；无法匹配的编号或 URL 冲突已标明。这不等于事实核验。', **citation_check)
                return answer
            except (ContextLimitError, OutputLimitError):
                raise
            except ProviderError as exc:
                self.rollback(h, checkpoint, 'final_generation_error')
                self.t.emit('final_retry', retry=retry + 1, text=str(exc))
                if exc.code in (401, 402, 403) or retry + 1 >= max_retries: raise
        raise ProviderError('最终答案生成失败。')

    async def execute(self):
        attempts = self.cfg['context_compress_limit'] + 1
        for attempt in range(1, attempts + 1):
            self.t.usage['research_attempts'] = attempt
            h, reason, turns = await self.loop(attempt)
            store.update(self.rid, end_reason=reason)
            if reason == 'iteration_limit' and attempt < attempts:
                self.t.emit('research_retry', attempt=attempt, next_attempt=attempt + 1,
                            text='按 benchmark 重试语义从原问题重新研究；retry_with_summary=False，不传入前次研究。')
                continue
            try:
                answer = await self.final(h, reason, turns, attempt)
                store.update(self.rid, answer=answer, status='completed', sources=self.sources, usage=self.t.usage)
                self.t.emit('done', answer=answer, sources=self.sources, usage=self.t.usage)
                return
            except (ContextLimitError, OutputLimitError):
                raise
            except ProviderError as exc:
                if attempt == attempts or exc.code in (401, 402, 403): raise
                self.t.emit('research_retry', attempt=attempt, next_attempt=attempt + 1, text='最终生成失败，从原问题开始新的研究尝试。')


async def research(rid, *, models=None, main=None, summary=None, web=None, web_api_key=None):
    t = Telemetry(rid)
    models = models or {r: config.model_settings(r) for r in ('main', 'summary')}
    main = main or ChatModel(models['main'], 'main', t)
    summary = summary or ChatModel(models['summary'], 'summary', t)
    main.observer = summary.observer = t
    web = web or DeepSeek(emit=t.emit, api_key=web_api_key)
    engine = Engine(rid, main, summary, web, t)
    try:
        await engine.execute()
    except asyncio.CancelledError:
        store.update(rid, status='cancelled', error='研究已停止。', usage=t.usage, sources=engine.sources, end_reason='cancelled')
        t.emit('cancelled', text='研究已停止，完整记录与来源已保存。')
        raise
    except OutputLimitError as exc:
        store.update(rid, status='incomplete', answer=exc.partial, error=str(exc), usage=t.usage, sources=engine.sources, end_reason='provider_output_limit')
        t.emit('incomplete', text=str(exc), answer=exc.partial, sources=engine.sources, usage=t.usage)
    except Exception as exc:
        if isinstance(exc, ContextLimitError): store.update(rid, end_reason='provider_context_limit')
        text = str(exc) if isinstance(exc, ProviderError) else '研究执行失败（' + type(exc).__name__ + '），请检查请求详情。'
        store.update(rid, status='failed', error=text, usage=t.usage, sources=engine.sources)
        t.emit('error', text=text)
    finally:
        await asyncio.gather(main.close(), summary.close(), web.close(), return_exceptions=True)
