"""Opt-in live smoke checks. Credentials stay in memory; reports contain no keys/text."""
import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config, llm_thinking
from app.llm_diagnostics import Capture
from app.provider import ChatModel, ProviderError

HOSTS = {'api.deepseek.com': 'deepseek', 'api.moonshot.cn': 'moonshot',
         'api.xiaomimimo.com': 'mimo', 'open.bigmodel.cn': 'z_ai',
         'dashscope.aliyuncs.com': 'qwen'}
PRESETS = {'moonshot': 'kimi_k3_openai', 'mimo': 'mimo_v26_openai', 'z_ai': 'glm_openai', 'qwen': 'qwen_openai'}


def credentials(path):
    lines = [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]
    result = {}
    for index, line in enumerate(lines[:-1]):
        urls = re.findall(r'https?://[^\s]+', line)
        if urls and urlsplit(urls[0]).hostname in HOSTS:
            kind = HOSTS[urlsplit(urls[0]).hostname]
            result[kind] = (urls[0].rstrip('/'), config.register_secret(lines[index + 1]))
        elif 'opencode' in line.lower() and 'key' in line.lower():
            result['opencode_go'] = ('https://opencode.ai/inference/go', config.register_secret(lines[index + 1]))
    return result


async def main(args):
    creds = credentials(args.credentials)
    report = []
    for kind, (base, key) in creds.items():
        if args.provider and kind != args.provider: continue
        settings = config.ModelSettings(model='', base_url=base, api_key=key, provider=kind, request_attempts=1)
        client = ChatModel(settings, 'main')
        try:
            async with asyncio.timeout(65):
                data = await client.models()
            ids = [v['id'] for v in data.get('data', []) if isinstance(v, dict) and isinstance(v.get('id'), str)]
            row = {'provider': kind, 'models': ids, 'unmapped_models': data.get('unmapped_models', [])}
        except Exception as exc:
            row = {'provider': kind, 'error_type': type(exc).__name__}
            if isinstance(exc, ProviderError): row.update(error=config.redact(str(exc)), code=exc.code)
        finally:
            await client.close()
        report.append(row)
        print(json.dumps(config.redact(row), ensure_ascii=False), flush=True)
        if not args.model or row.get('error_type'): continue
        selected = llm_thinking.initial(PRESETS[kind]) if kind in PRESETS else None
        if selected and args.level: selected['level'] = args.level
        cfg = replace(settings, model=args.model, thinking_config=selected,
                      thinking='enabled' if kind == 'deepseek' else None,
                      reasoning_effort=args.level or 'low' if kind == 'deepseek' else None,
                      go_reasoning=args.level or '' if kind == 'opencode_go' else None)
        capture = Capture()
        client = ChatModel(cfg, 'summary', observer=capture)
        started = time.monotonic()
        try:
            async with asyncio.timeout(150):
                result = await client.complete([{'role': 'user', 'content':
                    'A box has 17 red and 23 blue beads. Remove 8 red and add 6 blue. What fraction is red? Return only the final fraction.'}], purpose='connection_test')
            diagnostic = capture.report(cfg, result)
            diagnostic.pop('text', None)
            live = {'provider': kind, 'model': args.model, 'finish': result.finish_reason,
                    'answer_chars': len(result.message.get('content') or ''), 'usage': result.usage,
                    'thinking': diagnostic, 'elapsed_seconds': round(time.monotonic() - started, 2)}
        except Exception as exc:
            live = {'provider': kind, 'model': args.model, 'error_type': type(exc).__name__}
            if isinstance(exc, ProviderError): live.update(error=config.redact(str(exc)), code=exc.code)
        finally:
            await client.close()
        report.append(live)
        print(json.dumps(config.redact(live), ensure_ascii=False), flush=True)
    if args.output:
        Path(args.output).write_text(json.dumps(config.redact(report), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--provider')
    parser.add_argument('--model')
    parser.add_argument('--level')
    parser.add_argument('--output')
    asyncio.run(main(parser.parse_args()))
