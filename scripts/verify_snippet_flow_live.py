"""Replay the user's policy question in a new conversation and audit the actual message flow."""
import asyncio,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import httpx
from app import store,config

async def main():
    original=store.get_run('cca594d60774499a8c090ac493b932e6')
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8765',trust_env=False,timeout=60) as client:
        cid=(await client.post('/api/conversations')).json()['id']
        response=await client.post(f'/api/conversations/{cid}/runs',json={'question':original['question'],'memory_mode':'strict'})
        response.raise_for_status();rid=response.json()['id']
        (config.DATA/'snippet-flow-live-run.json').write_text(json.dumps({'run_id':rid,'conversation_id':cid}))
        print('Started original-question verification:',rid,flush=True)
        previous=None
        while True:
            detail=(await client.get(f'/api/runs/{rid}/details?include_history=false&include_events=false')).json()
            run=detail['run'];u=run['usage'];progress=(run['status'],u.get('main_iterations'),u.get('search_calls'),u.get('fetch_calls'),u.get('summary',{}).get('calls'))
            if progress!=previous:print('status, iterations, searches, fetches, summaries:',progress,flush=True);previous=progress
            if run['status']!='running':break
            await asyncio.sleep(10)
        reqs=[(await client.get(f'/api/runs/{rid}/requests/{r["id"]}')).json() for r in detail['requests']]
        mains=[r for r in reqs if r['role']=='main'];summaries=[r for r in reqs if r['role']=='summary']
        search_results=[]
        for r in mains:
            for m in r['request']['messages']:
                if m['role']=='tool':
                    try:d=json.loads(m['content'])
                    except ValueError:continue
                    if 'results' in d:search_results.extend(d['results'])
        raw=(await client.get(f'/api/runs/{rid}/search-responses')).json()
        checks={'completed':run['status']=='completed','snippet_only_search':bool(search_results) and all('summary' not in r and 'content' not in r for r in search_results),
          'summary_saved_server_side':any(item.get('summary') for response in raw for item in response['response'].get('results',[])),
          'model_selected_page_reading':run['usage']['fetch_calls']>0,
          'independent_summary_calls':bool(summaries) and all(len(r['request']['messages'])==2 and 'tools' not in r['request'] for r in summaries),
          'summary_does_not_inherit_original_question':all(original['question'] not in json.dumps(r['request']['messages'],ensure_ascii=False) for r in summaries),
          'main_never_receives_raw_page_prompt':all('CONTENT TO ANALYZE:' not in json.dumps(r['request']['messages']) for r in mains),
          'final_tools_disabled':any(r['purpose']=='final' for r in mains) and all('tools' not in r['request'] for r in mains if r['purpose']=='final')}
        report={'run_id':rid,'conversation_id':cid,'checks':checks,'usage':run['usage'],'end_reason':run['end_reason'],'error':run['error']}
        (config.DATA/'snippet-flow-live-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
        assert all(checks.values()),checks

if __name__=='__main__':asyncio.run(main())
