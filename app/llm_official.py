"""Official supplier metadata; requests reuse explicit thinking presets."""
import json


class OfficialProvider:
    def __init__(self, path):
        self.meta = json.loads(path.read_text(encoding='utf-8'))
        self.BASE = self.meta['baseUrl']
        self.BASE_URLS = self.meta.get('baseUrls', [self.BASE])

    def public_config(self):
        return {'name': self.meta['name'], 'base_url': self.BASE, 'base_urls': self.BASE_URLS,
                'default_thinking_preset': self.meta['defaultThinkingPreset'], 'models': [],
                'allow_manual_models': True,
                'template': {'model': '', 'provider': self.meta['id']}}

    def validate(self, profile):
        if profile['base_url'] not in self.BASE_URLS:
            raise ValueError('请选择此供应商支持的官方 API 地址')

    def capabilities(self, profile):
        return {'max_tokens': None, 'context_window': None}

    def filter_models(self, data):
        return data
