"""Test-only server. Never deploy or mount its sender in the production app."""
from app.config import Settings
from app.main import create_app
settings = Settings()
if settings.app_env != 'development':
    raise RuntimeError('Synthetic sender is development-only')
app = create_app(settings, sender=lambda chat, reply: None)
