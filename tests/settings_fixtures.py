"""Explicit pre-v4 settings for migration and configured-research tests."""
import copy
from app import config, research_profiles


def legacy_document():
    profiles = {}
    for role in ('main', 'summary'):
        model = config.env_model_settings(role)
        profiles[role] = {
            'id': role,
            'name': 'DeepSeek 主模型' if role == 'main' else 'DeepSeek 独立提取',
            'base_url': model.base_url, 'api_key': model.api_key,
            'model': model.model, 'provider': model.provider,
            'thinking': model.thinking, 'reasoning_effort': model.reasoning_effort,
            'temperature': model.temperature, 'top_p': model.top_p,
            'concurrency': model.concurrency,
            'models': [config.verified_metadata(model.base_url, model.model)]
            if config.verified_metadata(model.base_url, model.model) else [],
        }
    return {'version': 3, 'profiles': profiles,
            'active': {'main': 'main', 'summary': 'summary'},
            'web': {'api_key': config.API_KEY, 'credential_profile': None, 'search_count': 20},
            'research': copy.deepcopy(research_profiles.DEFAULT)}
