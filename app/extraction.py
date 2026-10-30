"""Independent extraction from the complete Fetch response, without local truncation."""
import json
from .provider import ProviderError, valid_url


async def scrape_and_extract_info(url, info_to_extract, *, web, summary, snapshot, telemetry,
                                  source_id, iteration, attempt, fallback_loader=None):
    result = {'success':False,'url':url,'source_id':source_id,'extracted_info':'','error':'',
              'scrape_stats':{},'model_used':None,'tokens_used':None,
              'content_source':'fetch_body','degraded':False,'fetch_error':''}
    if not valid_url(url) or not isinstance(info_to_extract,str) or not info_to_extract.strip():
        result['error'] = 'url 和 info_to_extract 必须有效。'
        return result
    emit = telemetry.emit
    telemetry.usage['extraction_calls'] += 1
    telemetry.usage['fetch_calls'] += 1
    emit('fetch_start',url=url,info_to_extract=info_to_extract,source_id=source_id)
    try:
        page = await web.fetch(url)
        content = page.get('content') or ''
        if not isinstance(content,str) or not content.strip(): raise ProviderError('抓取未返回可用正文。')
    except ProviderError as exc:
        result['fetch_error'] = str(exc)
        emit('fetch_error',url=url,text=str(exc))
        fallback = fallback_loader() if fallback_loader else None
        if not fallback:
            result['error'] = str(exc) + '；当前研究尝试没有该 URL 的可用 Search content 或 summary。'
            return result
        content = fallback['text']
        page = {'title': fallback['title']}
        result.update(content_source=fallback['content_source'], degraded=True,
                      fallback_search_response_id=fallback['search_response_id'],
                      fallback_query=fallback['query'], fallback_result_index=fallback['result_index'])
        telemetry.usage['fallback_extractions'] = telemetry.usage.get('fallback_extractions', 0) + 1
        emit('fetch_fallback',url=url,info_to_extract=info_to_extract,fetch_error=str(exc),
             search_response_id=fallback['search_response_id'],query=fallback['query'],
             content_source=result['content_source'], supplied_chars=len(content),
             text='Fetch 失败，使用同一 URL 的 '+result['content_source']+' 进入独立提取；并非 Fetch 成功。')
    stats = {'char_count':len(content),'line_count':content.count('\n')+1,
             'displayed_char_count':len(content),'all_content_displayed':True,'truncation_reasons':[],
             'content_source':result['content_source']}
    result['scrape_stats'] = stats
    if not result['degraded']: emit('fetch_done',url=url,title=page.get('title',''),scrape_stats=stats)
    tokens_before = telemetry.usage['summary']['total_tokens']
    missing_before = telemetry.usage['summary']['usage_missing_calls']
    metadata = {'url':url,'title':page.get('title') or '','source_id':source_id,'content_truncated':False,
                'original_char_count':len(content) if not result['degraded'] else None,
                'supplied_char_count':len(content),'content_source':result['content_source'],
                'degraded':result['degraded'],'fetch_error':result['fetch_error']}
    labels = ('来源元信息：', '提取任务：', '待分析正文：') if snapshot.get('language') == 'zh' else ('SOURCE METADATA:', 'INFORMATION TO EXTRACT:', 'CONTENT TO ANALYZE:')
    messages = [{'role':'system','content':snapshot['prompt_templates']['extraction']},
        {'role':'user','content':labels[0]+'\n'+json.dumps(metadata,ensure_ascii=False)
         +'\n\n'+labels[1]+'\n'+info_to_extract+'\n\n'+labels[2]+'\n'+content}]
    try:
        emit('extraction_start',url=url,info_to_extract=info_to_extract,model=summary.settings.model,supplied_chars=len(content))
        completion = await summary.complete(messages,purpose='page_extraction',iteration=iteration,attempt=attempt)
        result['model_used'] = completion.model
        result['extracted_info'] = completion.message.get('content') or ''
        if completion.finish_reason == 'length':
            result['incomplete'] = True
            raise ProviderError('提取模型报告输出达到服务端上限；部分结果已保留，不视为完整提取。')
        if completion.message.get('tool_calls') or not result['extracted_info'].strip():
            raise ProviderError('提取模型没有返回可用文本。')
        result['success'] = True
    except ProviderError as exc:
        result['error'] = str(exc)
    known = telemetry.usage['summary']['total_tokens']-tokens_before
    result['tokens_used'] = known if telemetry.usage['summary']['usage_missing_calls']==missing_before else None
    result['tokens_known'] = known
    emit('extraction_done' if result['success'] else 'extraction_error',url=url,info_to_extract=info_to_extract,result=result)
    return result
