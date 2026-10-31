"""Server-side configuration. Model limits are capabilities, never local input budgets."""
from dataclasses import dataclass, asdict, field
from pathlib import Path
from urllib.parse import urlsplit
import copy
import hashlib
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if not os.getenv('LUCENT_DATA_DIR'):
    load_dotenv(ROOT / '.env')
DATA = Path(os.environ['LUCENT_DATA_DIR']).resolve() if os.getenv('LUCENT_DATA_DIR') else ROOT / 'data'
DATA.mkdir(parents=True, exist_ok=True)
URL_PREFIX = ''
os.environ.setdefault('TIKTOKEN_CACHE_DIR', str(DATA / 'cache/tiktoken' if os.getenv('LUCENT_DATA_DIR') else ROOT / '.cache/tiktoken'))
UPSTREAM_COMMIT = '1c4253f6774bf40314271a827304b842100e054c'
API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-flash')
BASE_URL = 'https://api.deepseek.com'
SECRETS = set()
PRESETS = {
    'demo': {'label': 'Demo 流程 · 全量输入', 'max_iterations': 50, 'keep_tool_result': -1,
             'context_compress_limit': 0, 'retry_with_summary': True, 'runner': 'gradio_single'},
    'keep5_max200': {'label': 'keep5_max200（显式省略）', 'max_iterations': 200, 'keep_tool_result': 5,
                    'context_compress_limit': 5, 'retry_with_summary': False, 'runner': 'benchmark_retry'},
}
ITERATION_TIERS = {'quick': 10, 'standard': 50, 'deep': 200}


def register_secret(value):
    if value: SECRETS.add(value)
    return value


def normalize_base(url):
    url = url.strip().rstrip('/')
    if url.endswith('/chat/completions'): url = url[:-len('/chat/completions')]
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('请输入不含凭据、query 或 fragment 的 HTTP(S) Base URL。')
    return url


@dataclass(frozen=True)
class ModelSettings:
    model: str
    base_url: str
    api_key: str = field(repr=False)
    credential_source: str = ''
    # These two optional numbers are server-advertised capabilities, not application caps.
    max_tokens: int | None = None
    context_window: int | None = None
    thinking: str | None = None
    reasoning_effort: str | None = None
    thinking_config: dict | None = None
    go_reasoning: str | None = None
    reasoning_budget: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    request_attempts: int = 4
    retry_delay: float = 2.0
    timeout: float | None = None
    profile_id: str = ''
    profile_name: str = ''
    supplier_id: str = ''
    supplier_name: str = ''
    provider: str = 'openai'
    concurrency: int = 1

    def public(self):
        d = asdict(self)
        d.pop('api_key')
        d['configured'] = bool(self.api_key)
        d['generation_parameters'] = self.generation()
        d['output_policy'] = 'server_advertised_max' if self.max_tokens else 'provider_default_no_local_cap'
        if self.thinking_config is not None or self.provider not in ('openai', 'deepseek'):
            from . import llm_thinking
            from .llm_providers import registry
            adapter = registry.get(self.provider)
            if self.thinking_config is not None or not hasattr(adapter, 'prepare'):
                adapter = llm_thinking
            plan = adapter.prepare(self, {'messages': []}, 'omt-capabilities')
            d['protocol'] = plan['protocol']
            d['generation_parameters'] = {k: copy.deepcopy(v) for k, v in plan['body'].items()
                if k not in ('model', 'stream', 'stream_options', 'messages', 'contents', 'input', 'include', 'store')}
            d['output_policy'] = 'native_required_published_max' if plan['protocol'] == 'messages' else 'provider_default_no_local_cap'
        return d

    def generation(self):
        d = {}
        if self.max_tokens is not None: d['max_tokens'] = self.max_tokens
        if self.provider == 'deepseek' and self.thinking:
            d['thinking'] = {'type': self.thinking}
            if self.thinking == 'enabled' and self.reasoning_effort:
                d['reasoning_effort'] = self.reasoning_effort
        if self.temperature is not None and not (self.provider == 'deepseek' and self.thinking == 'enabled'):
            d['temperature'] = self.temperature
        if self.top_p is not None: d['top_p'] = self.top_p
        return d


def verified_metadata(base, model):
    """Use previously verified provider metadata only for the exact endpoint and ID."""
    path = DATA / 'model-verification.json'
    if path.exists():
        import json
        for value in json.loads(path.read_text()).values():
            if value.get('base_url') == base and value.get('configured_id') == model and value.get('verified'):
                return value.get('model_metadata') or {}
    return {}


def env_model_settings(role):
    prefix = 'MAIN_LLM' if role == 'main' else 'SUMMARY_LLM'
    main_base = normalize_base(os.getenv('MAIN_LLM_BASE_URL', BASE_URL))
    main_key = os.getenv('MAIN_LLM_API_KEY') or API_KEY
    base = normalize_base(os.getenv(prefix + '_BASE_URL', main_base))
    key = register_secret(os.getenv(prefix + '_API_KEY') or (main_key if base == main_base else ''))
    model = os.getenv(prefix + '_MODEL_NAME') or os.getenv('MAIN_LLM_MODEL_NAME') or MODEL
    metadata = verified_metadata(base, model)
    deepseek = urlsplit(base).hostname == 'api.deepseek.com'
    return ModelSettings(model=model, base_url=base, api_key=key, credential_source='environment migration',
        max_tokens=metadata.get('max_output_tokens'), context_window=metadata.get('context_window'),
        provider='deepseek' if deepseek else 'openai',
        thinking=os.getenv(prefix + '_THINKING', 'enabled' if role == 'main' else 'disabled') if deepseek else None,
        reasoning_effort=os.getenv(prefix + '_REASONING_EFFORT', 'high') if deepseek else None)


def model_settings(role, document=None):
    if role not in ('main', 'summary'): raise ValueError('Unknown model role')
    from . import settings_store
    doc = document if document is not None else settings_store.load()
    if doc['active'][role] not in doc['profiles']: raise ValueError('请在输入区选择有效的主模型和摘要模型')
    return settings_store.to_model(doc['profiles'][doc['active'][role]])


def redact(value):
    secrets = SECRETS | {API_KEY} | {v for k, v in os.environ.items() if k in ('MAIN_LLM_API_KEY', 'SUMMARY_LLM_API_KEY', 'DEEPSEEK_API_KEY')}
    if isinstance(value, str):
        for secret in sorted(secrets - {''}, key=len, reverse=True): value = value.replace(secret, '[REDACTED]')
        return value
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k.lower() not in ('api_key', 'authorization', 'x-api-key')}
    if isinstance(value, (list, tuple)): return [redact(v) for v in value]
    return value


def snapshot(preset='demo', memory_mode='strict', models=None, execution=None, web=None):
    if preset not in PRESETS or memory_mode not in ('strict', 'followup'):
        raise ValueError('未知上下文预设或历史模式。')
    from .prompts import templates
    from .tool_schema import TOOLS
    models = models or {r: model_settings(r) for r in ('main', 'summary')}
    prompts = templates()
    web_settings = copy.deepcopy(web) if web is not None else {'base_url': BASE_URL, 'search_path': '/v1/tools/search', 'fetch_path': '/v1/tools/fetch', 'configured': bool(API_KEY)}
    web_settings.setdefault('search_count', 10)
    tools = copy.deepcopy(TOOLS)
    search_tool = next(t['function'] for t in tools if t['function']['name'] == 'search')
    search_tool['parameters']['properties'].pop('count', None)
    search_tool['description'] += f" The program requests {web_settings['search_count']} results per search, as configured by the user. Do not supply count; actual results may be fewer."
    settings = copy.deepcopy(PRESETS[preset])
    if execution:
        settings.update(execution)
        if any(settings[k] != PRESETS[preset][k] for k in execution): settings['label'] = '自定义研究'
    return redact({
        'version': 7, 'upstream_commit': UPSTREAM_COMMIT, 'preset': preset, 'memory_mode': memory_mode, **settings,
        'main_model': models['main'].public(), 'summary_model': models['summary'].public(),
        'web': web_settings,
        'protocol': 'openai_native_tools', 'tools': tools, 'max_consecutive_rollbacks': 5,
        'extra_attempts_buffer': 200, 'input_policy': 'full_content_provider_validated',
        'output_policy': 'provider_capability_no_application_cap', 'page_max_chars': None,
        'followup_scope': 'all_completed_qa_and_all_sources', 'extract_max_attempts': models['summary'].request_attempts,
        'search_result_policy': 'metadata_and_snippet_only',
        'fetch_fallback_policy': 'source_id_row_index_current_attempt_content_then_summary_independent_extraction',
        'search_need_content': True, 'action_protocol': 'validated_source_ids_public_progress_explicit_finish',
        'search_context_policy': 'explicit_intent_else_original_if_fits_else_query',
        'search_text_limits': {'query': 128, 'ori_question': 128},
        'prompt_templates': prompts, 'prompt_sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k, v in prompts.items()},
    })
