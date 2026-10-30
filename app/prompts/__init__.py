"""Reviewable prompt files adapted from Apache-2.0 MiroThinker Demo; see NOTICE."""
from pathlib import Path
import json
import hashlib

DIR = Path(__file__).parent

def templates(locale=None):
    directory = DIR / 'zh' if locale == 'zh' else DIR
    bundle = {name: (directory / filename).read_text() for name, filename in (
        ('main', 'main.txt'), ('extraction', 'extraction.txt'), ('final', 'final.txt'), ('control', 'control.json'))}
    if locale in ('zh', 'en'):
        bundle['response_language'] = '简体中文' if locale == 'zh' else 'English'
    if locale == 'en':
        bundle['main'] = bundle['main'].replace("the user's language", 'English').replace('the user language', 'English')
        bundle['main'] += '\nUse English for public progress, extraction objectives, completion status and the final answer. Search queries may use the language best suited to finding original sources; preserve original source names and quotations.\n'
        bundle['extraction'] = bundle['extraction'].replace('using the language appropriate to the extraction task', 'in English')
    return bundle


def apply_language(snapshot, locale):
    """Freeze prompt language per run; old snapshots keep their original behavior."""
    if locale not in ('zh', 'en'):
        raise ValueError('Unsupported language')
    snapshot['language'] = locale
    snapshot['prompt_templates'] = templates(locale)
    snapshot['prompt_sha256'] = {k: hashlib.sha256(v.encode()).hexdigest()
                               for k, v in snapshot['prompt_templates'].items()}
    if locale == 'zh':
        descriptions = json.loads((DIR / 'zh' / 'tools.json').read_text())
        for tool in snapshot['tools']:
            function = tool['function']
            translated = descriptions[function['name']]
            function['description'] = translated['description']
            for name, spec in function['parameters']['properties'].items():
                if name in translated:
                    spec['description'] = translated[name]
            if function['name'] == 'search':
                function['description'] += f" 程序按用户配置请求 {snapshot['web']['search_count']} 条结果，实际可能更少。不要提交 count 参数。"
    else:
        for tool in snapshot['tools']:
            for spec in tool['function']['parameters']['properties'].values():
                if 'description' in spec:
                    spec['description'] = spec['description'].replace('the user language', 'English')


def reference_heading(snapshot, question):
    locale = snapshot.get('language')
    return ('参考来源' if locale == 'zh' else 'References') if locale else (
        '参考来源' if any('\u4e00' <= c <= '\u9fff' for c in question) else 'References')

def language(text):
    total = max(1, len(text.replace(' ', '')))
    if sum('\u4e00' <= c <= '\u9fff' for c in text) / total > .1:
        return 'Chinese (Simplified)'
    if sum('\u3040' <= c <= '\u30ff' for c in text) / total > .1:
        return 'Japanese'
    if sum('\uac00' <= c <= '\ud7af' for c in text) / total > .1:
        return 'Korean'
    return "the same language as the user's question"

def final_prompt(bundle, question):
    return bundle['final'].replace('{language}', bundle.get('response_language') or language(question)).replace('{question}', question)

def controls(bundle):
    return json.loads(bundle['control'])
