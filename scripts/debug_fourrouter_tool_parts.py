"""Inspect native streaming part shapes without logging thought text or credentials."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app import settings_store,config
from app.provider import ChatModel
from app.llm_providers import registry
async def main():
 old=next(p for p in settings_store.load()['profiles'].values() if p['base_url']=='https://4router.net/v1' and p['model']=='gemini-4-argon')
 draft=settings_store.validated_profile(registry.get('fourrouter_argon').public_config()['template'],old)
 model=ChatModel(settings_store.to_model(draft),'main')
 schema=[{'type':'function','function':{'name':'connection_echo','description':'Echo the input to verify native tool calling.','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}}}]
 try:
  out=await asyncio.wait_for(model.complete([{'role':'user','content':'Call connection_echo with text hellow. Do not answer in prose.'}],schema),150)
  shapes=[]
  for part in out.message['_provider_native']['items']:
   shapes.append({k:len(v) if isinstance(v,str) else v if k=='functionCall' else type(v).__name__ for k,v in part.items()})
  print(json.dumps({'parts':shapes,'tool_calls':out.message.get('tool_calls'),'usage':out.usage},ensure_ascii=False),flush=True)
  (config.DATA/'verification'/'fourrouter-tool-parts.json').write_text(json.dumps(shapes,indent=2))
 finally:await model.close()
asyncio.run(main())
