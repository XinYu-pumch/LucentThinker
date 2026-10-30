"""Small paid end-to-end probe; stored results exclude credentials."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app import config, store


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8765',trust_env=False,timeout=60) as client:
        cid=(await client.post('/api/conversations')).json()['id']
        result=await client.post(f'/api/conversations/{cid}/runs',json={
            'question':'核对 Python 3.14.0 首次正式发布日期。搜索并读取 Python 官方发布页，给出日期及来源，简短回答。',
            'mode':'demo','memory_mode':'strict','max_iterations':10,'keep_tool_result':-1,'context_compress_limit':0})
        result.raise_for_status();rid=result.json()['id']
        with store.connect() as db:
            db.execute('UPDATE conversations SET title=? WHERE id=?',('v0.5 · Search content 与显式结束验证',cid))
        (config.DATA/'v5-live-run.json').write_text(json.dumps({'run_id':rid,'conversation_id':cid}))
        print('Run',rid,flush=True)
        prev=None
        while True:
            run=store.get_run(rid)
            progress=(run['status'],run['usage'].get('main_iterations'),run['usage'].get('search_calls'),run['usage'].get('extraction_calls'))
            if progress!=prev: print(progress,flush=True);prev=progress
            if run['status']!='running': break
            await asyncio.sleep(5)
        requests=[store.requests(rid,r['id'])[0] for r in store.requests(rid)]
        mains=[r for r in requests if r['role']=='main']
        summaries=[r for r in requests if r['role']=='summary']
        raw=store.search_responses(rid)
        searches=[]
        for r in mains:
            for m in r['request']['messages']:
                if m['role']=='tool':
                    data=json.loads(m['content'])
                    if 'results' in data: searches.extend(data['results'])
        checks={
          'completed':run['status']=='completed',
          'explicit_finish':any(e['kind']=='finish_requested' for e in store.events(rid)),
          'snapshot_need_content':run['config_snapshot']['search_need_content'] is True,
          'search_received_content':any(isinstance(i.get('content'),str) and i['content'].strip() for r in raw for i in r['response']['results']),
          'main_search_snippet_only':bool(searches) and all('content' not in i and 'summary' not in i for i in searches),
          'independent_extraction':bool(summaries) and all(len(r['request']['messages'])==2 and 'tools' not in r['request'] for r in summaries),
          'final_without_tools':any(r['purpose']=='final' for r in mains) and all('tools' not in r['request'] for r in mains if r['purpose']=='final'),
          'no_unmatched_citations':not any(e['kind']=='citation_warning' and e['data'].get('unmatched_ids') for e in store.events(rid)),
        }
        report={'run_id':rid,'conversation_id':cid,'checks':checks,'usage':run['usage'],'end_reason':run['end_reason'],'error':run['error']}
        (config.DATA/'v5-live-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
        assert all(checks.values()),checks

if __name__=='__main__':asyncio.run(main())
