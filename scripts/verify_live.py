"""Explicit, billable real-service E2E: inspect message flow, not just answer plausibility."""
import asyncio
import json
import sys
import time
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import DATA
from app.citations import reconcile

QUESTION = '请简短比较 Python 3.13.0 与 Python 3.14.0 的首次正式发布日期，使用 Python 官方发布页面。请先搜索，分别读取两个发布页面并定向提取版本号、发布日期和页面标题；读取后再进行一次搜索核对日期，然后给出中文 Markdown 表格和来源引用。无需讨论其他版本或功能。'

async def main(existing_run=None):
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8765', timeout=60, trust_env=False) as client:
        if existing_run:
            rid = existing_run
            saved = (await client.get(f'/api/runs/{rid}/details')).json()['run']
            assert saved['question'] == QUESTION
            cid = saved['conversation_id']
            models = json.loads((DATA/'model-verification.json').read_text())
            check = {'ok': all(models[r]['verified'] for r in ('main','summary'))}
        else:
            check = (await client.post('/api/check')).json()
            assert check['ok'], check
            cid = (await client.post('/api/conversations')).json()['id']
            started = (await client.post(f'/api/conversations/{cid}/runs', json={'question': QUESTION, 'mode': 'demo', 'memory_mode': 'strict'})).json()
            rid = started['id']
        print('Live research:', rid, flush=True)
        (DATA/'live-run.json').write_text(json.dumps({'conversation_id': cid, 'run_id': rid}))
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            d = (await client.get(f'/api/runs/{rid}/details')).json()
            if d['run']['status'] != 'running': break
            await asyncio.sleep(3)
        assert d['run']['status'] == 'completed', (d['run']['status'], d['run']['error'])
        rows = [(await client.get(f'/api/runs/{rid}/requests/{r["id"]}')).json() for r in d['requests']]
        mains = [r for r in rows if r['role'] == 'main']
        summaries = [r for r in rows if r['role'] == 'summary']
        finals = [r for r in rows if r['purpose'] == 'final']
        history = [r['message'] for r in d['history'] if not r['rolled_back']]
        results = [json.loads(m['content']) for m in history if m['role'] == 'tool']
        extractions = [r for r in results if 'extracted_info' in r and r['success']]
        main_text = json.dumps([r['request']['messages'] for r in mains], ensure_ascii=False)
        checks = {
            'model_ids_verified': check['ok'],
            'demo_keeps_all_tool_results': 'Tool result is omitted to save tokens.' not in main_text,
            'search_results_returned': any(r.get('results') for r in results),
            'two_independent_page_extractions': len(extractions) >= 2,
            'summary_requests_fresh': all(len(r['request']['messages']) == 2 and 'tools' not in r['request'] for r in summaries),
            'summary_does_not_inherit_question': all(QUESTION not in json.dumps(r['request']['messages'], ensure_ascii=False) for r in summaries),
            'summary_contains_web_body': all('CONTENT TO ANALYZE:' in r['request']['messages'][-1]['content'] for r in summaries),
            'main_receives_extracted_info': all(any(json.loads(m['content']).get('extracted_info') == r['extracted_info'] for p in mains for m in p['request']['messages'] if m['role']=='tool') for r in extractions),
            'main_does_not_receive_raw_page_prompt': 'CONTENT TO ANALYZE:' not in main_text,
            'continued_search_after_extraction': any(r['purpose']=='research' and any(m['role']=='tool' and 'extracted_info' in m['content'] for m in r['request']['messages']) and any(c['function']['name']=='search' for c in (r.get('response',{}).get('choices',[{}])[0].get('message',{}).get('tool_calls') or [])) for r in mains),
            'final_tools_disabled': bool(finals) and all('tools' not in r['request'] for r in finals),
            'reference_numbers_match_registered_urls': reconcile(d['run']['answer'], d['run']['sources'])[0] == d['run']['answer'],
            'answer_has_registered_citation': any(f'[{s["id"]}]' in d['run']['answer'] for s in d['run']['sources']),
            'strict_no_followup_background': d['run']['memory_context'] == [],
            'full_input_policy': d['run']['config_snapshot']['input_policy'] == 'full_content_provider_validated',
            'streamed_requests': all(r['request'].get('stream') is True for r in rows),
            'output_uses_verified_maximum': all(
                r['request'].get('max_tokens') == d['run']['config_snapshot'][r['role']+'_model']['max_tokens']
                == 393216 for r in rows),
            'full_page_bodies': all(
                r['scrape_stats']['all_content_displayed']
                and r['scrape_stats']['displayed_char_count'] == r['scrape_stats']['char_count']
                and not r['scrape_stats']['truncation_reasons'] for r in extractions),
        }
        report = {'date': time.strftime('%Y-%m-%d %H:%M:%S'), 'run_id': rid, 'conversation_id': cid,
                  'checks': checks, 'usage': d['run']['usage'], 'end_reason': d['run']['end_reason'],
                  'summary_request_ids': [r['id'] for r in summaries], 'main_request_ids': [r['id'] for r in mains],
                  'answer': d['run']['answer']}
        (DATA/'live-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps({k:v for k,v in report.items() if k!='answer'},ensure_ascii=False,indent=2), flush=True)
        assert all(checks.values()), checks

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', help='Recheck a saved verification run without starting paid research')
    asyncio.run(main(parser.parse_args().run_id))
