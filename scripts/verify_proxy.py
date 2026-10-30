"""Read-only route verification using app clients and the running server; no keys logged."""
import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app import config
from app.provider import DeepSeek, ChatModel

async def main():
    pid = int((config.DATA/'server.pid').read_text())
    report = {'checked_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'server_pid':pid}
    web = DeepSeek()
    model = ChatModel(config.model_settings('main'),'main')
    for name, client in [('fetch_client',web.client),('main_client',model.client)]:
        pool = client._transport_for_url(httpx.URL('https://api.deepseek.com'))._pool
        proxy = getattr(pool,'_proxy_url',None)
        report[name] = {'transport':type(pool).__name__,'proxy':f'{proxy.scheme.decode()}://{proxy.host.decode()}:{proxy.port}' if proxy else None}
    connections = {}
    socket_observed = False
    stop = asyncio.Event()
    async with httpx.AsyncClient(trust_env=False,timeout=10) as local:
        cfg = (await local.get('http://127.0.0.1:9090/configs')).json()
        report['clash_mode'] = cfg.get('mode')
        rules = (await local.get('http://127.0.0.1:9090/rules')).json().get('rules',[])
        report['deepseek_rules'] = [{k:r.get(k) for k in ('type','payload','proxy')} for r in rules if 'deepseek' in r.get('payload','').lower()]
        async def watch():
            nonlocal socket_observed
            while not stop.is_set():
                try:
                    data = (await local.get('http://127.0.0.1:9090/connections')).json()
                    for c in data.get('connections',[]):
                        meta=c.get('metadata',{})
                        if meta.get('host') == 'api.deepseek.com':
                            connections[c['id']] = {'host':meta.get('host'),'source_port':meta.get('sourcePort'),
                                'rule':c.get('rule'),'rule_payload':c.get('rulePayload'),'chains':c.get('chains')}
                    output = subprocess.run(['lsof','-nP','-a','-p',str(pid),'-iTCP'],capture_output=True,text=True).stdout
                    socket_observed |= '->127.0.0.1:7890' in output
                except (httpx.HTTPError,ValueError): pass
                try: await asyncio.wait_for(stop.wait(),timeout=.2)
                except TimeoutError: pass
        watcher=asyncio.create_task(watch())
        async def actual_server():
            settings=(await local.get('http://127.0.0.1:8765/api/settings')).json()
            async with httpx.AsyncClient(trust_env=False,timeout=None) as running:
                r=await running.post('http://127.0.0.1:8765/api/settings/web/test/fetch',json={'credential_profile':settings['web'].get('credential_profile')})
                report['running_app_fetch_test']={'status':r.status_code,'result':r.json()}
        async def wikipedia():
            url='https://en.wikipedia.org/wiki/Python_(programming_language)'
            try:
                result=await web.fetch(url)
                content=result.get('content') or ''
                report['wikipedia_fetch']={'url':url,'title':result.get('title'),'content_chars':len(content),
                    'contains_python': 'Python' in content,'content_preview':content[:400]}
            except Exception as exc: report['wikipedia_fetch']={'url':url,'error':config.redact(str(exc))}
        try:
            await asyncio.wait_for(asyncio.gather(actual_server(),wikipedia()),timeout=180)
        finally:
            stop.set()
            await watcher
            await web.close()
            await model.close()
        report['running_server_connected_to_clash']=socket_observed
        report['deepseek_connections']=list(connections.values())
    safe=config.redact(report)
    (config.DATA/'proxy-verification.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2))
    print(json.dumps(safe,ensure_ascii=False,indent=2))

if __name__=='__main__': asyncio.run(main())
