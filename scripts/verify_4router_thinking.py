"""Read-only live diagnostic: synthetic prompt, no credentials or reasoning text logged."""
import asyncio
import json
import time
import re
import sys
from pathlib import Path
from dataclasses import replace
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, settings_store
from app.provider import ChatModel

OUT = config.DATA / 'verification' / ('4router-thinking-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
PROMPT = 'Find the smallest positive integer n such that n mod 17 = 3, n mod 19 = 7, n mod 23 = 11, and n mod 29 = 13. Return only n and the four remainders to verify it. Do not describe your reasoning.'

class Overrides:
    def __init__(self, original, parameters): self.original, self.parameters = original, parameters
    def __getattr__(self, key): return getattr(self.original, key)
    def generation(self): return self.parameters

async def main():
    profiles = [p for p in settings_store.load()['profiles'].values() if p['base_url']=='https://4router.net/v1' and p['model']=='gemini-4-argon']
    if len(profiles)!=1: raise RuntimeError('Expected one matching profile')
    original = replace(settings_store.to_model(profiles[0]), request_attempts=1)
    variants = [('app_current', original.generation()), ('default', {}), ('effort_high', {'reasoning_effort':'high'}), ('effort_low', {'reasoning_effort':'low'}), ('invalid_effort', {'reasoning_effort':'invalid_diagnostic_value'}), ('thinking_disabled', {'thinking':{'type':'disabled'}})]
    variants += [('google_high', {'extra_body':{'google':{'thinking_config':{'thinking_level':'high','include_thoughts':True}}}}), ('google_low', {'extra_body':{'google':{'thinking_config':{'thinking_level':'low','include_thoughts':True}}}})]
    if len(sys.argv)>1:
        variants = [v for v in variants if v[0] in sys.argv[1:]]
    report={'model':original.model,'base_url':original.base_url,'saved_provider':original.provider,'prompt':PROMPT,'results':[]}
    sem = asyncio.Semaphore(2)
    async def probe(label, parameters):
        async with sem:
            start=time.monotonic(); result={'case':label,'parameters':parameters}
            async def on_request(request):
                body=json.loads(request.content)
                result['sent_parameters']={k:v for k,v in body.items() if k not in ('messages','tools')}
                result['endpoint']=str(request.url)
            async def on_response(response): result['http_status']=response.status_code
            client=httpx.AsyncClient(base_url=original.base_url+'/',headers={'Authorization':'Bearer '+original.api_key},timeout=httpx.Timeout(None,connect=30,write=60,pool=30),event_hooks={'request':[on_request],'response':[on_response]})
            model=ChatModel(original if label=='app_current' else Overrides(original,parameters),'main',client=client)
            try:
                reply=await asyncio.wait_for(model.complete([{'role':'user','content':PROMPT}],purpose='connection_test'),180)
                result.update(ok=True,usage=reply.usage,model_returned=reply.model,finish_reason=reply.finish_reason,answer=reply.message.get('content'),reasoning_chars=len(reply.message.get('reasoning_content') or ''))
            except Exception as exc: result.update(ok=False,error=config.redact(str(exc)),error_type=type(exc).__name__)
            finally: await model.close()
            matches = re.findall(r'n\s*=\s*(\d+)', result.get('answer') or '')
            if matches:
                n = int(matches[-1]); result['verified_remainders'] = [n % v for v in (17,19,23,29)]
                result['answer_correct'] = n == 87825
            result['elapsed_seconds']=round(time.monotonic()-start,2)
            report['results'].append(result)
            OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(json.dumps(result,ensure_ascii=False),flush=True)
    await asyncio.gather(*(probe(*v) for v in variants))

if __name__=='__main__': asyncio.run(main())
