"""Live checks of the installed optional adapter; never edits saved profiles."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import config,settings_store
from app.settings_api import ProfileDraft, run_test
from app.provider import ChatModel
from app.llm_providers import registry

async def main():
    old=next(p for p in settings_store.load()['profiles'].values() if p['base_url']=='https://4router.net/v1' and p['model']=='gemini-4-argon')
    template=registry.get('fourrouter_argon').public_config()['template']
    body=ProfileDraft(**{**template,'id':old['id'],'api_key':None})
    report={}
    for name,tools in [('connection',False),('tool_roundtrip',True)]:
        result=await asyncio.wait_for(run_test(body,tools),180)
        report[name]=result
        print(json.dumps({name:result},ensure_ascii=False),flush=True)
    draft=settings_store.draft(body.model_dump())
    model=ChatModel(settings_store.to_model(draft),'main')
    try:
        data=await model.models()
        report['models']=[m['id'] for m in data.get('data',[])]
    finally:await model.close()
    (config.DATA/'verification'/'fourrouter-module-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if not all(report[k].get('ok') for k in ('connection','tool_roundtrip')):raise RuntimeError('Live module verification failed')

if __name__=='__main__':asyncio.run(main())
