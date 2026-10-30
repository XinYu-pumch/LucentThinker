"""Read-only model ID discovery; no credentials or HTTP headers are printed."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.provider import ChatModel

async def main():
    report = {}
    for role in ('main', 'summary'):
        model = ChatModel(config.model_settings(role), role)
        try:
            data = await model.models()
            found = next((m for m in data.get('data', []) if m.get('id') == model.settings.model), None)
            report[role] = {'configured_id': model.settings.model, 'base_url': model.settings.base_url,
                            'verified': found is not None, 'model_metadata': found}
        finally: await model.close()
    path = config.DATA / 'model-verification.json'
    path.write_text(json.dumps(config.redact(report), ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not all(r['verified'] for r in report.values()): raise SystemExit(1)

if __name__ == '__main__': asyncio.run(main())
