from pathlib import Path
from app.llm_official import OfficialProvider
_adapter = OfficialProvider(Path(__file__).with_name("manifest.json"))
BASE = _adapter.BASE
BASE_URLS = _adapter.BASE_URLS
public_config = _adapter.public_config
validate = _adapter.validate
capabilities = _adapter.capabilities
filter_models = _adapter.filter_models
