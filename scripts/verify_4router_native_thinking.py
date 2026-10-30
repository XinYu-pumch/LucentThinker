"""Native Gemini comparison; logs usage/answer only, never keys or thought text."""
import asyncio
import json
import re
import time
import sys
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import config, settings_store
from scripts.verify_4router_thinking import PROMPT

async def main():
    profile=next(p for p in settings_store.load()['profiles'].values() if p['base_url']=='https://4router.net/v1' and p['model']=='gemini-4-argon')
    results=[]
    async def probe(level):
        payload={'contents':[{'role':'user','parts':[{'text':PROMPT}]}], 'generationConfig':{'thinkingConfig':{'thinkingLevel':level,'includeThoughts':True}}}
        result={'case':'native_'+level,'endpoint':'https://4router.net/v1beta/models/gemini-4-argon:generateContent','generationConfig':payload['generationConfig']}
        start=time.monotonic()
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                response=await client.post(result['endpoint'],headers={'Authorization':'Bearer '+profile['api_key']},json=payload)
                result['http_status']=response.status_code
                data=response.json()
                if response.is_error:result['error']=config.redact(str(data.get('error',{})))
                else:
                    result['usage']=data.get('usageMetadata');result['model_version']=data.get('modelVersion')
                    parts=[p for c in data.get('candidates',[]) for p in c.get('content',{}).get('parts',[])]
                    result['answer']=''.join(p.get('text','') for p in parts if not p.get('thought'))
                    result['thought_chars']=sum(len(p.get('text','')) for p in parts if p.get('thought'))
                    matches=re.findall(r'n\s*=\s*(\d+)', result['answer'])
                    if matches:result['answer_correct']=int(matches[-1])==87825
            except Exception as exc:result['error_type']=type(exc).__name__
        result['elapsed_seconds']=round(time.monotonic()-start,2)
        results.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    await asyncio.gather(probe('high'),probe('low'))
    (config.DATA/'verification'/('4router-native-thinking-'+time.strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
