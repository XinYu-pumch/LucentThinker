"""Real settings/model/search protocol checks. Never print credentials."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import httpx
from app import config
from app.provider import DeepSeek, ProviderError

async def main():
    report={}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8765',trust_env=False,timeout=None) as client:
        settings=(await client.get('/api/settings')).json()
        fields=('id','name','base_url','model','provider','thinking','reasoning_effort','temperature','top_p')
        for role in ('main','summary'):
            p=settings['profiles'][settings['active'][role]]
            draft={k:p.get(k) for k in fields}
            models=(await client.post('/api/settings/models',json=draft)).json()
            reply=(await client.post('/api/settings/test',json=draft)).json()
            assert models['ok'] and reply['ok'], (models,reply)
            report[role]={'model_list_ok':models['ok'],'models':[m['id'] for m in models['models']],
                          'hello':reply}
            if role=='main':
                tool=(await client.post('/api/settings/test-tools',json=draft)).json()
                assert tool['ok'],tool
                report[role]['native_tools']=tool
            print(role,'models + hellow verified',flush=True)
        for service in ('search','fetch'):
            result=(await client.post('/api/settings/web/test/'+service,json={'credential_profile':settings['web']['credential_profile']})).json()
            assert result['ok'],result
            report[service]=result
            print(service,'verified',flush=True)
    # User-approved query boundary; never shorten either query or original question.
    web=DeepSeek()
    try:
        query=('Python official releases documentation ' * 4)[:128]
        result=await web.search(query,'Python official release dates',2)
        report['query_128']={'query_chars':len(query),'accepted':True,'results':len(result.get('results',[]))}
        try:
            await web.search(query+'x','Python official release dates',2)
        except ValueError as exc:
            report['query_129']={'query_chars':129,'accepted':False,'local_validation':str(exc),'local_truncation':False}
        else: raise AssertionError('129-character query must be rejected locally')
        question='请研究 Python 官方发布信息，并核实发布日期。' * 20
        try:
            result=await web.search('Python official releases',question,2)
            report['long_ori_question']={'question_chars':len(question),'accepted':True,'results':len(result.get('results',[]))}
        except (ProviderError, ValueError) as exc:
            report['long_ori_question']={'question_chars':len(question),'accepted':False,'error':str(exc),'local_validation':isinstance(exc,ValueError),'local_truncation':False}
    finally: await web.close()
    (config.DATA/'settings-live-verification.json').write_text(json.dumps(config.redact(report),ensure_ascii=False,indent=2))
    print(json.dumps(config.redact(report),ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
